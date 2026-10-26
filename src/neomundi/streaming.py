"""Bounded, single-request SSE transport for POST /v1/govern/stream.

This is the generation proxy, not a streaming encoding of govern().
No reconnect, retry, or automatic second measurement is performed.
"""

from __future__ import annotations

import codecs
import copy
import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Iterator, Mapping, Optional, Tuple

import httpx

from .errors import ConfigurationError, NeoMundiError, NetworkError, TimeoutError

GOVERN_STREAM_PATH = "/v1/govern/stream"
DEFAULT_MAX_EVENT_BYTES = 1024 * 1024
DEFAULT_MAX_RESPONSE_BYTES = 16 * 1024 * 1024


class StreamError(NeoMundiError):
    """Stream failure, with already received text and an optional request ID.

    No partial response is represented as a successful measurement.
    Partial text is available explicitly; it is excluded from str/repr.
    """

    def __init__(
        self,
        message: str,
        *,
        partial_text: str = "",
        request_id: Optional[str] = None,
        event: Optional["StreamEvent"] = None,
    ) -> None:
        super().__init__(message)
        self.partial_text = partial_text
        self.request_id = request_id
        self.event = event


class StreamInterruptedError(StreamError):
    """EOF/transport failure or server-declared interruption before success."""


class StreamProtocolError(StreamError):
    """Malformed frame, invalid terminal payload, size limit or assembly mismatch."""


class StreamServerError(StreamError):
    """The server emitted an SSE error event after HTTP headers were sent."""


@dataclass(frozen=True)
class StreamEvent:
    """One event. Unknown event names and JSON fields are preserved."""

    event: str
    data: Dict[str, Any] = field(repr=False)
    id: Optional[str] = None
    retry_ms: Optional[int] = None
    raw_data: str = field(default="", repr=False)

    @property
    def content(self) -> Optional[str]:
        """Text delta for a chunk, never the complete done.response_text."""
        return self.data.get("content") if self.event == "chunk" else None


@dataclass(frozen=True)
class StreamResult:
    """The SSE done envelope, kept separate from the REST GovernResult.

    Nullable fields, evaluator states, units and unknown fields remain in
    payload. No missing REST blocks are invented to coerce this into REST.
    """

    payload: Dict[str, Any] = field(repr=False)
    response_text: str = field(repr=False)
    integrity_verified: bool

    @property
    def request_id(self) -> Optional[str]:
        value = self.payload.get("request_id")
        return value if isinstance(value, str) else None

    @property
    def decision(self) -> Optional[str]:
        value = self.payload.get("decision")
        return value if isinstance(value, str) else None

    @property
    def decision_basis(self) -> Optional[str]:
        value = self.payload.get("decision_basis")
        return value if isinstance(value, str) else None

    @property
    def measurement(self) -> Optional[Mapping[str, Any]]:
        value = self.payload.get("measurement")
        return value if isinstance(value, dict) else None

    def to_dict(self) -> Dict[str, Any]:
        return copy.deepcopy(self.payload)


def _positive_limit(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ConfigurationError(name + " must be a positive integer.")


def build_stream_request_body(
    *,
    prompt: str,
    provider_api_key: str,
    model: str,
    provider: Optional[str] = None,
    system_prompt: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    mode: str = "OBS",
    metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Validate the inspected StreamRequest contract without network access.

    Model selection is explicit: the SDK never silently selects OpenAI.
    Unspecified optional parameters are omitted so server defaults apply.
    """
    if not isinstance(prompt, str) or not 1 <= len(prompt) <= 50000:
        raise ConfigurationError("prompt must contain 1 to 50000 characters.")
    if not isinstance(model, str) or not 1 <= len(model.strip()) <= 100:
        raise ConfigurationError("model must be explicitly provided (1 to 100 characters).")
    if not isinstance(provider_api_key, str) or len(provider_api_key.strip()) < 10:
        raise ConfigurationError(
            "provider_api_key must be a provider credential of at least 10 characters."
        )
    if provider_api_key.strip().startswith(("ct_live_", "ct_test_", "ct_trial_")):
        raise ConfigurationError("provider_api_key must not be a NeoMundi API key.")
    if mode != "OBS":
        raise ConfigurationError("The inspected streaming contract accepts mode OBS only.")
    body: Dict[str, Any] = {
        "prompt": prompt,
        "provider_api_key": provider_api_key.strip(),
        "model": model,
        "mode": mode,
    }
    if provider is not None:
        if not isinstance(provider, str) or not 1 <= len(provider.strip()) <= 50:
            raise ConfigurationError("provider must contain 1 to 50 characters.")
        body["provider"] = provider.strip().lower()
    if system_prompt is not None:
        if not isinstance(system_prompt, str) or len(system_prompt) > 10000:
            raise ConfigurationError("system_prompt must contain at most 10000 characters.")
        body["system_prompt"] = system_prompt
    if max_tokens is not None:
        if (
            isinstance(max_tokens, bool)
            or not isinstance(max_tokens, int)
            or not 1 <= max_tokens <= 16384
        ):
            raise ConfigurationError("max_tokens must be an integer between 1 and 16384.")
        body["max_tokens"] = max_tokens
    if temperature is not None:
        if (
            isinstance(temperature, bool)
            or not isinstance(temperature, (int, float))
            or not math.isfinite(temperature)
            or not 0 <= temperature <= 2
        ):
            raise ConfigurationError("temperature must be a finite number between 0 and 2.")
        body["temperature"] = temperature
    if metadata is not None:
        if not isinstance(metadata, Mapping):
            raise ConfigurationError("metadata must be a mapping.")
        body["metadata"] = dict(metadata)
    try:
        json.dumps(body, allow_nan=False, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        raise ConfigurationError(
            "Streaming request must be JSON serializable with finite numbers."
        ) from None
    return body


def _lines(chunks: Iterable[bytes], max_bytes: int) -> Iterator[str]:
    decoder = codecs.getincrementaldecoder("utf-8-sig")("strict")
    buffer = ""
    try:
        for chunk in chunks:
            buffer += decoder.decode(chunk)
            while True:
                match = re.search(r"\r\n|\r|\n", buffer)
                if match is None or (match.group() == "\r" and match.end() == len(buffer)):
                    break
                line, buffer = buffer[: match.start()], buffer[match.end() :]
                if len(line.encode("utf-8")) > max_bytes:
                    raise StreamProtocolError("SSE line exceeds max_event_bytes.")
                yield line
            if len(buffer.encode("utf-8")) > max_bytes:
                raise StreamProtocolError("SSE line exceeds max_event_bytes.")
        buffer += decoder.decode(b"", final=True)
        # A final CR is a real line ending; an unterminated final line is
        # discarded. A final event still needs its blank-line delimiter.
        if buffer.endswith("\r"):
            yield buffer[:-1]
    except UnicodeDecodeError:
        raise StreamProtocolError("SSE contains invalid UTF-8.") from None


def _frames(
    chunks: Iterable[bytes], max_bytes: int
) -> Iterator[Tuple[str, str, Optional[str], Optional[int]]]:
    name, data, event_id, retry, size = "message", [], None, None, 0
    for line in _lines(chunks, max_bytes):
        size += len(line.encode("utf-8")) + 1
        if size > max_bytes:
            raise StreamProtocolError("SSE event exceeds max_event_bytes.")
        if line == "":
            if data:
                yield name or "message", "\n".join(data), event_id, retry
            name, data, size = "message", [], 0
            continue
        if line.startswith(":"):
            continue
        key, sep, value = line.partition(":")
        if sep and value.startswith(" "):
            value = value[1:]
        if key == "event":
            name = value
        elif key == "data":
            data.append(value)
        elif key == "id" and "\x00" not in value:
            event_id = value
        elif key == "retry" and value and all("0" <= c <= "9" for c in value):
            # Metadata only. It never authorizes a reconnect on this POST.
            retry = int(value) if len(value) < 10 else None


def _redact(value: Any, secrets: Tuple[str, ...]) -> Any:
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, dict):
        return {_redact(k, secrets): _redact(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v, secrets) for v in value]
    return value


def _reject_constant(_value: str) -> Any:
    raise ValueError("Non-finite JSON number")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite JSON number")
    return number


class GovernStream(Iterator[StreamEvent]):
    """Lazy, closeable SSE iterator; use it as a context manager.

    The HTTP response closes on done, failure or context exit. If stopping
    iteration early outside a with block, call close() explicitly.
    An externally supplied httpx.Client is never closed by this object.
    """

    def __init__(
        self,
        http_client: httpx.Client,
        url: str,
        body: Dict[str, Any],
        headers: Mapping[str, str],
        timeout: httpx.Timeout,
        *,
        max_event_bytes: int = DEFAULT_MAX_EVENT_BYTES,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    ) -> None:
        _positive_limit(max_event_bytes, "max_event_bytes")
        _positive_limit(max_response_bytes, "max_response_bytes")
        self._http_client, self._url, self._body = http_client, url, body
        self._headers = dict(headers, Accept="text/event-stream")
        self._timeout = timeout
        self._max_event_bytes, self._max_response_bytes = max_event_bytes, max_response_bytes
        self._secrets = (headers["X-API-Key"], body["provider_api_key"])
        self._context: Any = None
        self._iterator: Any = None
        self._started, self._closed = False, False
        self._chunks: list[str] = []
        self._response_bytes = 0
        self.request_id: Optional[str] = None
        self.result: Optional[StreamResult] = None

    def __repr__(self) -> str:
        return f"GovernStream(started={self._started}, closed={self._closed}, completed={self.result is not None})"

    @property
    def response_text(self) -> str:
        return self.result.response_text if self.result else "".join(self._chunks)

    @property
    def is_closed(self) -> bool:
        return self._closed

    def __enter__(self) -> "GovernStream":
        if self._closed:
            raise StreamProtocolError("A closed stream cannot be reopened.")
        if not self._started:
            self._open()
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self._context is not None:
                self._context.__exit__(None, None, None)
        finally:
            self._body = {}
            self._headers = {}
            self._secrets = ()

    def _open(self) -> None:
        self._started = True
        try:
            self._context = self._http_client.stream(
                "POST",
                self._url,
                json=self._body,
                headers=self._headers,
                timeout=self._timeout,
                follow_redirects=False,
            )
            response = self._context.__enter__()
            request_id = response.headers.get("x-request-id")
            self.request_id = (
                request_id if _redact(request_id, self._secrets) == request_id else None
            )
            if not 200 <= response.status_code < 300:
                from .client import _build_api_error

                # Bound and sanitize diagnostics: servers may echo a submitted
                # provider key in a validation error or a proxy error page.
                content = bytearray()
                for part in response.iter_bytes():
                    if len(content) + len(part) > self._max_event_bytes:
                        break
                    content.extend(part)
                try:
                    payload = _redact(json.loads(content), self._secrets)
                    safe = httpx.Response(
                        response.status_code,
                        json=payload,
                        headers=_redact(dict(response.headers), self._secrets),
                    )
                except (ValueError, UnicodeError):
                    safe = httpx.Response(
                        response.status_code,
                        text=_redact(content.decode("utf-8", "replace"), self._secrets),
                        headers=_redact(dict(response.headers), self._secrets),
                    )
                raise _build_api_error(safe)
            if (
                response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                != "text/event-stream"
            ):
                raise StreamProtocolError("Expected Content-Type text/event-stream.")
            # Do not pass a fixed chunk_size: httpx would buffer small SSE
            # events until that size or EOF, defeating live delivery.
            self._iterator = iter(_frames(response.iter_bytes(), self._max_event_bytes))
        except httpx.TimeoutException:
            self.close()
            raise TimeoutError(
                "Timeout opening SSE; the request may have been processed. No retry performed."
            ) from None
        except httpx.HTTPError:
            self.close()
            raise NetworkError("Transport failure opening SSE. No retry performed.") from None
        except BaseException:
            self.close()
            raise

    def __next__(self) -> StreamEvent:
        if self._closed:
            raise StopIteration
        if not self._started:
            self._open()
        try:
            name, raw, event_id, retry = next(self._iterator)
            try:
                payload = json.loads(
                    raw, parse_constant=_reject_constant, parse_float=_finite_float
                )
                json.dumps(payload, ensure_ascii=False).encode("utf-8")
            except (ValueError, RecursionError):
                raise StreamProtocolError("SSE data is not valid finite JSON.") from None
            if not isinstance(payload, dict):
                raise StreamProtocolError("SSE data must be a JSON object.")
            # Never expose known credentials echoed by a server. Successful
            # measurement payloads otherwise remain unmodified.
            if _redact(payload, self._secrets) != payload:
                if name == "error":
                    payload = _redact(payload, self._secrets)
                    raw = json.dumps(payload, ensure_ascii=False)
                else:
                    raise StreamProtocolError("Server echoed a credential; event withheld.")
            event = StreamEvent(name, payload, event_id, retry, raw)
            if name == "chunk":
                content = payload.get("content")
                if not isinstance(content, str):
                    raise StreamProtocolError("chunk.content must be a string.")
                self._response_bytes += len(content.encode("utf-8"))
                if self._response_bytes > self._max_response_bytes:
                    raise StreamProtocolError("Response text exceeds max_response_bytes.")
                self._chunks.append(content)
            elif name == "error":
                raise StreamServerError(
                    "Server emitted an SSE error; no successful result.", event=event
                )
            elif name == "done":
                self._finish(payload)
                self.close()
            return event
        except StopIteration:
            error = StreamInterruptedError(
                "SSE ended without done or error; no retry performed.",
                partial_text=self.response_text,
                request_id=self.request_id,
            )
            self.close()
            raise error from None
        except StreamError as exc:
            exc.partial_text = self.response_text
            exc.request_id = exc.request_id or self.request_id
            self.close()
            raise
        except httpx.HTTPError:
            error = StreamInterruptedError(
                "SSE transport interrupted; no retry performed.",
                partial_text=self.response_text,
                request_id=self.request_id,
            )
            self.close()
            raise error from None
        except BaseException:
            self.close()
            raise

    def _finish(self, payload: Dict[str, Any]) -> None:
        if "stream_interrupted" in payload and not isinstance(payload["stream_interrupted"], bool):
            raise StreamProtocolError("stream_interrupted must be a boolean.")
        if payload.get("stream_interrupted") is True:
            raise StreamInterruptedError("Server declared an interrupted stream.")
        complete = payload.get("response_text")
        assembled = "".join(self._chunks)
        if not isinstance(complete, str) or complete != assembled:
            raise StreamProtocolError("done.response_text does not match the chunk assembly.")
        for key, expected in (
            ("response_length", len(complete)),
            ("response_bytes", len(complete.encode("utf-8"))),
        ):
            if key in payload:
                value = payload[key]
                if isinstance(value, bool) or not isinstance(value, int) or value != expected:
                    raise StreamProtocolError("Invalid " + key + " in done.")
        if "response_sha256" in payload:
            digest = payload["response_sha256"]
            if (
                not isinstance(digest, str)
                or digest.lower() != hashlib.sha256(complete.encode("utf-8")).hexdigest()
            ):
                raise StreamProtocolError("Invalid response_sha256 in done.")
        verified = all(
            key in payload for key in ("response_length", "response_bytes", "response_sha256")
        )
        self.result = StreamResult(copy.deepcopy(payload), complete, verified)
        if self.result.request_id:
            self.request_id = self.result.request_id

    def collect(self) -> StreamResult:
        """Consume the remaining events and return a verified terminal result."""
        for _event in self:
            pass
        if self.result is None:
            raise StreamInterruptedError(
                "Stream was closed without a terminal result.",
                partial_text=self.response_text,
                request_id=self.request_id,
            )
        return self.result
