"""Offline SSE protocol/lifecycle tests; no sockets or real credentials."""

from __future__ import annotations

import hashlib
import json

import httpx
import pytest
from conftest import TEST_API_KEY, TEST_BASE_URL

from neomundi import (
    APIError,
    AuthenticationError,
    ConfigurationError,
    NeoMundiClient,
    RetryPolicy,
    ServerError,
    StreamInterruptedError,
    StreamProtocolError,
    StreamServerError,
    TimeoutError,
)
from neomundi.streaming import _frames

PROVIDER_KEY = "provider_TEST_SECRET_00000000"
ARGS = dict(
    prompt="Une question",
    provider_api_key=PROVIDER_KEY,
    provider="anthropic",
    model="model-under-test",
)


def frame(name, payload, newline="\n"):
    return (
        f"event: {name}{newline}data: "
        + json.dumps(payload, ensure_ascii=False)
        + newline
        + newline
    ).encode("utf-8")


def done(text="Bonjour 👋", **overrides):
    data = dict(
        response_text=text,
        response_length=len(text),
        response_bytes=len(text.encode("utf-8")),
        response_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        request_id="test-request",
        decision="FLAG",
        decision_basis="incomplete_measurement",
        stream_interrupted=False,
        stability_score=None,
        g_final=None,
        measurement={"status": "incomplete", "coverage": 2 / 3},
        unmeasured_signals={"coherence_score": "service_unavailable"},
    )
    data.update(overrides)
    return data


class Wire(httpx.SyncByteStream):
    def __init__(self, parts):
        self.parts = parts
        self.closed = False
        self.reads = 0

    def __iter__(self):
        for part in self.parts:
            self.reads += 1
            if isinstance(part, Exception):
                raise part
            yield part

    def close(self):
        self.closed = True


def client_for(parts, *, status=200, headers=None, retry=None):
    wire = Wire(parts)
    requests = []

    def responder(request):
        requests.append(request)
        return httpx.Response(
            status, headers=headers or {"Content-Type": "text/event-stream"}, stream=wire
        )

    client = NeoMundiClient(
        api_key=TEST_API_KEY,
        base_url=TEST_BASE_URL,
        transport=httpx.MockTransport(responder),
        **({"retry": retry} if retry else {}),
    )
    return client, wire, requests


def test_rest_and_sse_are_distinct_routes_and_sse_body_does_not_contain_fake_metrics():
    c, wire, requests = client_for(
        [frame("chunk", {"content": "Bonjour 👋"}), frame("done", done())]
    )
    with c:
        stream = c.stream(**ARGS)
        assert requests == []  # validation/building the request is pure
        with stream:
            events = list(stream)
        body = json.loads(requests[0].content)
        assert requests[0].method == "POST"
        assert requests[0].url.path == "/v1/govern/stream"
        assert requests[0].headers["Accept"] == "text/event-stream"
        assert requests[0].headers["X-API-Key"] == TEST_API_KEY
        assert body == {**ARGS, "mode": "OBS"}
        assert "raw_metrics" not in body
        assert stream.response_text == "Bonjour 👋"  # done is NOT a delta
        assert len(events) == 2
        assert stream.result.integrity_verified
        assert stream.result.to_dict()["g_final"] is None
        assert stream.result.measurement["status"] == "incomplete"
        assert stream.result.decision_basis == "incomplete_measurement"
        assert wire.closed and stream.is_closed


def test_first_event_arrives_before_reading_the_rest_of_the_stream():
    c, wire, _ = client_for(
        [
            frame("chunk", {"content": "first"}),
            httpx.ReadError("must not be read for the first event"),
        ]
    )
    with c, c.stream(**ARGS) as stream:
        event = next(stream)
        assert event.content == "first"
        assert wire.reads == 1
    assert wire.closed
    assert stream.result is None


@pytest.mark.parametrize("size", [1, 2, 3, 7, 4096])
def test_arbitrary_network_fragmentation_utf8_bom_comments_crlf_and_multiline(size):
    raw = (
        b"\xef\xbb\xbf: keepalive\r\nid: abc\r\nretry: 1000\r\nevent: future_event\r\n"
        b'data: {"unknown":\r\ndata: null}\r\n\r\n'
        + frame("chunk", {"content": "Bonjour 👋"}, "\r\n")
        + frame("done", done(), "\r\n")
    )
    c, wire, _ = client_for([raw[i : i + size] for i in range(0, len(raw), size)])
    with c, c.stream(**ARGS) as stream:
        events = list(stream)
    assert events[0].event == "future_event"
    assert events[0].data == {"unknown": None}
    assert events[0].id == "abc"
    assert events[0].retry_ms == 1000
    assert stream.result.response_text == "Bonjour 👋"
    assert wire.closed


def test_cr_only_line_endings_and_last_cr():
    c, _, _ = client_for([frame("chunk", {"content": "x"}, "\r"), frame("done", done("x"), "\r")])
    with c:
        assert c.govern_stream(**ARGS).collect().response_text == "x"


@pytest.mark.parametrize(
    "tail",
    [
        b"",
        b'event: done\ndata: {"response_text":"x"}',
        httpx.ReadError("network"),
        httpx.ReadTimeout("slow"),
    ],
)
def test_interruption_preserves_partial_text_and_never_replays(tail):
    c, wire, requests = client_for(
        [frame("chunk", {"content": "x"}), tail], retry=RetryPolicy(max_attempts=3)
    )
    with c, pytest.raises(StreamInterruptedError) as err:
        c.stream(**ARGS).collect()
    assert err.value.partial_text == "x"
    assert len(requests) == 1 and wire.closed


@pytest.mark.parametrize(
    "patch",
    [
        dict(response_text="duplicated"),
        dict(response_length=999),
        dict(response_length=True),
        dict(response_bytes=999),
        dict(response_sha256="bad"),
        dict(stream_interrupted="false"),
    ],
)
def test_bad_done_cannot_be_presented_as_success(patch):
    c, wire, _ = client_for([frame("chunk", {"content": "x"}), frame("done", done("x", **patch))])
    with c, pytest.raises(StreamProtocolError):
        stream = c.stream(**ARGS)
        stream.collect()
    assert stream.result is None and wire.closed


def test_server_declared_interruption_is_not_a_success():
    c, _, _ = client_for(
        [frame("chunk", {"content": "x"}), frame("done", done("x", stream_interrupted=True))]
    )
    with c, pytest.raises(StreamInterruptedError):
        c.stream(**ARGS).collect()


def test_missing_integrity_metadata_is_explicit_and_does_not_fabricate_a_hash():
    payload = done("")
    for field in ("response_length", "response_bytes", "response_sha256"):
        del payload[field]
    c, _, _ = client_for([frame("done", payload)])
    with c:
        result = c.stream(**ARGS).collect()
    assert not result.integrity_verified
    assert "response_sha256" not in result.to_dict()


def test_error_event_after_http_200_is_a_typed_failure_and_redacts_credentials():
    c, wire, _ = client_for(
        [
            frame("chunk", {"content": "x"}),
            frame("error", {"error": PROVIDER_KEY, "nested": [TEST_API_KEY]}),
        ]
    )
    with c, pytest.raises(StreamServerError) as err:
        c.stream(**ARGS).collect()
    assert err.value.partial_text == "x"
    assert PROVIDER_KEY not in str(err.value.event.data)
    assert TEST_API_KEY not in str(err.value.event.data)
    assert wire.closed


@pytest.mark.parametrize("status,cls", [(401, AuthenticationError), (503, ServerError)])
def test_pre_stream_http_errors_keep_rest_error_types_and_do_not_retry(status, cls):
    body = json.dumps({"detail": PROVIDER_KEY, "error": TEST_API_KEY}).encode()
    c, wire, requests = client_for([body], status=status, retry=RetryPolicy(max_attempts=3))
    with c, pytest.raises(cls) as err:
        c.stream(**ARGS).collect()
    assert PROVIDER_KEY not in str(err.value)
    assert TEST_API_KEY not in str(err.value.body)
    assert len(requests) == 1 and wire.closed


@pytest.mark.parametrize(
    "status,headers,expected",
    [
        (200, {"Content-Type": "application/json"}, StreamProtocolError),
        (307, {"Location": "https://elsewhere.invalid"}, APIError),
    ],
)
def test_wrong_content_type_and_redirects_are_not_followed(status, headers, expected):
    c, wire, requests = client_for([b"{}"], status=status, headers=headers)
    with c, pytest.raises(expected):
        c.stream(**ARGS).collect()
    assert wire.closed and len(requests) == 1


@pytest.mark.parametrize(
    "payload",
    [
        b"data: []\n\n",
        b"data: NaN\n\n",
        b'data: {"n": 1e999}\n\n',
        b'event: chunk\ndata: {"content":"\\ud800"}\n\n',
        b"data: not-json\n\n",
        b"data: \xff\n\n",
        frame("chunk", {"content": None}),
    ],
)
def test_malformed_events_fail_explicitly_and_close(payload):
    c, wire, _ = client_for([payload])
    with c, pytest.raises(StreamProtocolError):
        c.stream(**ARGS).collect()
    assert wire.closed


@pytest.mark.parametrize("limit", ["max_event_bytes", "max_response_bytes"])
def test_limits_are_bounded_and_close_the_response(limit):
    c, wire, _ = client_for([frame("chunk", {"content": "x" * 200})])
    with c, pytest.raises(StreamProtocolError):
        c.stream(**ARGS, **{limit: 100}).collect()
    assert wire.closed


def test_new_frame_name_defaults_do_not_leak_previous_event_type():
    events = list(_frames([b"event: custom\ndata: {}\n\ndata: {}\n\n"], 1000))
    assert [e[0] for e in events] == ["custom", "message"]


def test_client_owned_by_the_caller_is_not_closed():
    wire = Wire([frame("done", done(""))])
    http = httpx.Client(
        base_url="https://unrelated.invalid",
        follow_redirects=True,
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                200, headers={"content-type": "text/event-stream"}, stream=wire
            )
        ),
    )
    with NeoMundiClient(api_key=TEST_API_KEY, base_url=TEST_BASE_URL, http_client=http) as c:
        c.stream(**ARGS).collect()
    assert wire.closed and not http.is_closed
    http.close()


def test_known_secret_echoed_in_success_is_withheld_and_repr_is_safe():
    c, wire, _ = client_for([frame("chunk", {"content": PROVIDER_KEY})])
    with c:
        stream = c.stream(**ARGS)
        assert PROVIDER_KEY not in repr(stream) and TEST_API_KEY not in repr(stream)
        with pytest.raises(StreamProtocolError) as err:
            stream.collect()
        assert PROVIDER_KEY not in str(err.value)
    assert wire.closed


def test_open_timeout_is_typed_without_echoing_transport_secrets():
    def fail(_):
        raise httpx.ReadTimeout(PROVIDER_KEY)

    with NeoMundiClient(
        api_key=TEST_API_KEY, base_url=TEST_BASE_URL, transport=httpx.MockTransport(fail)
    ) as c:
        with pytest.raises(TimeoutError) as err:
            c.stream(**ARGS).collect()
    assert PROVIDER_KEY not in str(err.value)


@pytest.mark.parametrize(
    "patch",
    [
        dict(prompt=""),
        dict(prompt="\ud800"),
        dict(model=""),
        dict(provider=""),
        dict(provider_api_key=TEST_API_KEY),
        dict(provider_api_key="short"),
        dict(max_tokens=True),
        dict(max_tokens=16385),
        dict(mode="EXEC"),
        dict(temperature=float("nan")),
        dict(metadata={"bad": float("inf")}),
    ],
)
def test_invalid_stream_parameters_fail_before_a_request(patch):
    c, _, requests = client_for([])
    with c, pytest.raises(ConfigurationError):
        c.stream(**{**ARGS, **patch})
    assert requests == []


@pytest.mark.parametrize("field", ["latency_ms", "cost"])
@pytest.mark.parametrize("value", [float("inf"), float("nan")])
def test_rest_nonfinite_metrics_are_rejected_before_http(field, value):
    c, _, requests = client_for([])
    with c, pytest.raises(ConfigurationError):
        c.govern(**{**dict(token_count=1, latency_ms=1), field: value})
    assert requests == []


def test_closed_iterator_cannot_be_reopened_or_fabricate_a_result():
    c, _, requests = client_for([])
    with c:
        stream = c.stream(**ARGS)
        stream.close()
        assert list(stream) == []
        with pytest.raises(StreamInterruptedError):
            stream.collect()
        with pytest.raises(StreamProtocolError):
            stream.__enter__()
    assert requests == []
