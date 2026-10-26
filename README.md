# NeoMundi Python SDK 2

![REST](https://img.shields.io/badge/transport-REST-blue) ![SSE](https://img.shields.io/badge/transport-SSE-blue) ![Status](https://img.shields.io/badge/status-experimental-orange)

**Version 2.0.0 — Experimental / Pilot Evaluation.**

Integrate NeoMundi measurements into your infrastructure, or
[explore Station](https://github.com/neomundi-io/neomundi-station-public).
Check Station's current access and availability; its dashboard evolves separately.
[Understand the measurements](https://github.com/neomundi-io/neomundi-metric-contract) ·
[Data flows and confidentiality](https://github.com/neomundi-io/neomundi-io-data-protection)

## Choose the right path

| Your need | Method | API route |
|---|---|---|
| Measure an execution you already produced | `client.govern(...)` | `POST /v1/govern` |
| Generate an answer through the API and receive live checks | `client.stream(...)` | `POST /v1/govern/stream` |

These routes have different request bodies and result envelopes. SSE is
not a subscription to REST results. The synchronous Python client supports
both; an async/await client is not part of this release.

NeoMundi provides measurements and their provenance, including unavailable
measurements. Interpretation and execution authority remain with your
application. The SDK does not add decision thresholds or replace null with zero.

## Install

Python 3.9+; `httpx` is the only runtime dependency. Not published on PyPI.
The licence decision remains documented in [LICENSE_NOTICE.md](LICENSE_NOTICE.md).

```sh
python -m pip install .
# Or install a locally built package:
python -m pip install dist/neomundi_sdk-2.0.0-py3-none-any.whl
```

No API or provider credentials are included, read automatically or persisted.
Select the API environment explicitly through `base_url`.

## REST: measure an existing execution

```python
import os
from neomundi import NeoMundiClient

with NeoMundiClient(
    api_key=os.environ["NEOMUNDI_API_KEY"],
    base_url=os.environ["NEOMUNDI_BASE_URL"],
) as client:
    result = client.govern(
        token_count=128,          # actual observed usage
        latency_ms=842.0,        # actual measured latency
        llm_prompt="What is the capital of France?",
        llm_response="Paris.",
    )
    print(result.request_id, result.format_score("g_score"))
```

This call submits an existing answer; it does not generate one. Sending only
metrics remains possible, but does not establish that semantic checks were
performed. Optional fields left as None are omitted, not silently set to zero.

## SSE: receive an answer and checks live

```python
import os
from neomundi import NeoMundiClient, StreamError

with NeoMundiClient(
    api_key=os.environ["NEOMUNDI_API_KEY"],
    base_url=os.environ["NEOMUNDI_BASE_URL"],
) as client:
    try:
        with client.stream(
            prompt="Explain the chosen topic.",
            model=os.environ["LLM_MODEL"],
            provider=os.environ["LLM_PROVIDER"],
            provider_api_key=os.environ["LLM_PROVIDER_API_KEY"],
            max_tokens=256,
        ) as stream:
            for event in stream:
                if event.event == "chunk":
                    print(event.content, end="", flush=True)
            result = stream.result
            assert result is not None
            print(result.request_id, result.integrity_verified)
    except StreamError as error:
        print(type(error).__name__)  # no automatic retry
```

The streaming API receives the provider key in its JSON body and calls the
selected provider. This can incur provider cost and a NeoMundi quota charge.
The SDK does not select OpenAI or any model by default.

Use `with` to close early when needed. `done.response_text` repeats the whole
answer: **do not append it to chunks**. The SDK verifies assembly and supplied
length/byte/hash metadata. Errors after HTTP 200, missing terminal events and
truncated streams fail explicitly. No stream is reconnected or retried,
including when REST retries were explicitly enabled.

## Verification and limits

The V2 streaming contract is derived from inspected backend source at
`aeff13c`; tests use synthetic, fragmented streams with a mock transport.
No new hosted SDK call or provider generation was run for V2. This does
not certify a live deployment or all providers. Existing REST compatibility
evidence and backend limitations remain qualified and dated.

The SSE `StreamResult` preserves its own raw envelope; it is not cast into
REST `GovernResult`. A complete transport can carry an incomplete measurement.
Integrity checks do not establish scientific validity. The SDK does not repair
backend metric, trajectory, quota or evaluator defects.

## Documentation

- [SSE lifecycle, errors, integrity and limits](docs/STREAMING.md)
- [Migration from v0.1](docs/MIGRATION_V2.md)
- [Audit and repair plan](docs/AUDIT_SDK_V2.md)
- [Known backend and SDK limitations](KNOWN_LIMITATIONS.md)
- [REST pilot guide](PILOT_INTEGRATION_GUIDE.md)
- [Inspected REST contract](docs/CONTRAT_API.md) · [Measurement limits](docs/LIMITES.md)
- [Offline SSE example](examples/04_streaming_sse.py)

```sh
python -m pip install -e ".[dev]"
python -m pytest tests
python examples/04_streaming_sse.py
python -m build
```

SDK version 2.0.0 is a client release, not measurement version 2.0.0.
Check the measurement version actually returned by your deployment before
comparing observations.
