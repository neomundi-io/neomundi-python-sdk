# REST and SSE in SDK 2

The SDK is synchronous. SSE is a streaming transport, not an async Python
client. Python async/await support is not included in this release.

| API | Python | What happens | Final result |
|---|---|---|---|
| `POST /v1/govern` | `client.govern(...)` | Submit an execution already produced by your application | `GovernResult` |
| `POST /v1/govern/stream` | `client.stream(...)` / `client.govern_stream(...)` | The NeoMundi API calls the selected provider and streams generation and checks | `StreamResult` after `done` |

REST does not generate a new LLM answer. Omitting `llm_response` remains
possible in REST, but does not establish that semantic checks were measured.
SSE requires a provider key and model; it is not a metrics-only subscription.
The NeoMundi key is sent in `X-API-Key`; the provider key is sent in the
JSON request body to the selected NeoMundi API. Both costs and privacy
implications differ from post-call REST.

## Read live events

```python
import os
from neomundi import NeoMundiClient, StreamError

with NeoMundiClient(
    api_key=os.environ["NEOMUNDI_API_KEY"],
    base_url=os.environ["NEOMUNDI_BASE_URL"],
) as client:
    try:
        with client.stream(
            prompt="Your question",
            provider=os.environ["LLM_PROVIDER"],
            model=os.environ["LLM_MODEL"],
            provider_api_key=os.environ["LLM_PROVIDER_API_KEY"],
            max_tokens=256,
            temperature=0,
        ) as stream:
            for event in stream:
                if event.event == "chunk":
                    print(event.content, end="", flush=True)
                # Other checks remain accessible through event.data.
            result = stream.result
            assert result is not None
            print(result.request_id, result.decision_basis)
            # The envelope preserves explicit null and unknown fields.
            payload = result.to_dict()
    except StreamError as error:
        # error.partial_text is only a partial answer, not a measurement.
        # Store it only according to your own data-handling policy.
        print(type(error).__name__)
```

Creating the stream validates parameters, but does not contact a server.
Entering its context or requesting its first event starts exactly one POST.
An unconsumed context still opens the request, which may consume quota.
`collect()` consumes the stream and returns the terminal `StreamResult`.

## Completion and integrity

The backend sends the answer in `chunk.content`, then again in
`done.response_text`. **The latter is a complete recap, not a trailing delta.**
The SDK compares the two; it never appends the recap to the chunk buffer.

When provided, `response_length` (Python Unicode characters),
`response_bytes` (UTF-8 bytes), and `response_sha256` are checked. If any
supplied check disagrees, `StreamProtocolError` is raised and no result is
published. `integrity_verified` is true only when all three metadata fields
were supplied and matched. Missing metadata is not invented. Equality of
the chunk assembly and final recap is always checked.

Transport integrity is not scientific validity, evaluator availability,
or authorization to execute an action. Null scores remain null. An
`incomplete` measurement can be a completely delivered SSE response.
Conversely, an interrupted transport is not an incomplete measurement:
there is no successful terminal result to interpret.

`StreamResult.payload` is the actual SSE done envelope; it is not coerced
into REST. Reading `result.to_dict()` gives an independent deep copy.
The SDK preserves units and provisional check fields, including counters
whose historical names count chunks rather than tokens.

## Failures and resource handling

- HTTP failures before streaming use the existing REST HTTP error classes.
- An SSE `error` event raises `StreamServerError`, even after HTTP 200.
- EOF without `done`, midstream network errors and server-declared
  interruption raise `StreamInterruptedError`, with explicit `partial_text`.
- Invalid UTF-8, non-object/non-finite JSON, invalid chunk or done fields,
  assembly mismatch and size limits raise `StreamProtocolError`.
- Context exit, terminal completion and failures close the HTTP response.
  If stopping early without `with`, call `stream.close()` explicitly.
- A caller-owned `httpx.Client` is not closed by the SDK. Redirects are not
  followed for this credential-bearing POST.

There is **no automatic reconnect or retry**, even when the REST client has
a `RetryPolicy`. Receiving `retry:` or `id:` metadata does not authorize
replaying the request. A replay can create a second generation, measure,
quota charge and provider bill. The SDK does not implement Last-Event-ID
resumption for an endpoint with no documented resumable POST contract.

Default bounds are 1 MiB per decoded event and 16 MiB of assembled answer
text, configurable with `max_event_bytes` and `max_response_bytes`. The
event bound can be the first limit reached because `done` repeats the full
answer. Stored results and partial text can contain sensitive application
content; they are never automatically persisted or logged by this SDK.

Known submitted credentials are withheld if echoed in successful events,
and redacted from HTTP/SSE error diagnostics. User-created logging, HTTPX
event hooks or a caller-supplied transport remain the caller's responsibility.

## Contract and verification scope

Implementation inspected locally at backend commit
`aeff13cca717205c9ebbc83c5755ba6a22b284bb`:
`app/models/requests.py` (`StreamRequest`) and `app/api/v1/streaming.py`.
Their SHA-256 hashes are recorded in [the audit](AUDIT_SDK_V2.md).
Offline fixtures are synthetic and derived from those sources; they are
not live production captures. No new hosted SSE call or provider generation
was performed for this release. Deployment compatibility still requires
a separately controlled test against the intended environment.

Parser references: [HTML SSE interpretation](https://html.spec.whatwg.org/multipage/server-sent-events.html#event-stream-interpretation)
and [HTTPX streaming](https://www.python-httpx.org/quickstart/#streaming-responses).
