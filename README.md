# NeoMundi Python SDK 2

[English](README.md) · [Français](README_FR.md)

[![PyPI version](https://img.shields.io/pypi/v/neomundi?style=flat-square)](https://pypi.org/project/neomundi/) ![REST](https://img.shields.io/badge/transport-REST-blue) ![SSE](https://img.shields.io/badge/transport-SSE-blue) ![Status](https://img.shields.io/badge/qualification-REST_SSE_live_pass-green)

**Version 2.0.0 — published on [PyPI](https://pypi.org/project/neomundi/). REST and SSE available; pilot-level live qualification.**

Integrate NeoMundi measurements into your infrastructure, or
[explore Station](https://github.com/neomundi-io/neomundi-station-public).
Check Station's current access and availability; its dashboard evolves separately.
[Understand the measurements](https://github.com/neomundi-io/neomundi-metric-contract) ·
[Data flows and confidentiality](https://github.com/neomundi-io/neomundi-io-data-protection)

## Where we stand

The V2 development work is complete and [merged into main](https://github.com/neomundi-io/neomundi-python-sdk/pull/3).
Both REST and SSE are available in the SDK source.

| Step | Status |
|---|---|
| Public PyPI distribution | Published 2026-11-14; Windows Python 3.12.10 install and import verified |\n| REST and SSE implementation | Complete |
| Offline regression suite | Passing in GitHub CI; historical capture skips are tracked separately |
| CI | Passed on Python 3.9, 3.11, 3.12 and 3.13 |
| Live REST and SSE qualification using the installed V2 SDK | Both passed on 2026-11-13; see evidence limits below |

On 2026-11-13 an installed wheel was tested against the deployed API:
one REST observation (complete, coverage 1.0, five measured signals) and
one SSE generation (seven events, terminal done, verified integrity).
The full operator report and request identifiers remain private.
The two public REST/SSE versioned JSON schemas were subsequently compared
byte-for-byte against the deployed API via
[GitHub Actions](https://github.com/neomundi-io/neomundi-python-sdk/actions/runs/43526131929).
These checks establish transport success and schema parity at that time,
not scientific validity, all providers or a genuine degraded 3.5.0 capture.
See [3.5.0 compatibility scope](docs/COMPATIBILITY_350.md).
PyPI publication is complete; Station integration remains a separate step.

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

Python 3.9+; `httpx` is the only runtime dependency. **Published on [PyPI](https://pypi.org/project/neomundi/)** as `neomundi` (version `2.0.0`); Python imports use `import neomundi`.
The SDK code is licensed under [Apache-2.0](LICENSE), subject to contributor-rights review; see the [licensing boundaries](LICENSE_NOTICE.md). The **hosted Runtime Measurement API remains proprietary and commercially metered** (authorised key, applicable credits/quotas and service terms). An open-source SDK does not include free hosted API access.

```sh
python -m pip install neomundi==2.0.0
# For contributors installing from source instead:
git clone https://github.com/neomundi-io/neomundi-python-sdk.git
cd neomundi-python-sdk
python -m pip install .
# Or install a locally built package:
python -m pip install dist/neomundi-2.0.0-py3-none-any.whl
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
A bounded hosted SDK REST and SSE qualification was carried out on
2026-11-13; see the exact evidence scope in
[the compatibility assessment](docs/COMPATIBILITY_350.md).
It does not certify all providers, degraded paths or scientific comparability.

The SSE `StreamResult` preserves its own raw envelope; it is not cast into
REST `GovernResult`. A complete transport can carry an incomplete measurement.
Integrity checks do not establish scientific validity. The SDK does not repair
backend metric, trajectory, quota or evaluator defects.

## Documentation

- [SSE lifecycle, errors, integrity and limits](docs/STREAMING.md) · [Français](docs/STREAMING_FR.md)
- [Migration from v0.1](docs/MIGRATION_V2.md)
- [Audit and repairs delivered](docs/AUDIT_SDK_V2.md)
- [Verification results and live qualification status](docs/VERIFICATION_V2.md)
- [Known backend and SDK limitations](KNOWN_LIMITATIONS.md) · [Français](KNOWN_LIMITATIONS_FR.md)
- [REST pilot guide](PILOT_INTEGRATION_GUIDE.md) · [Français](PILOT_INTEGRATION_GUIDE_FR.md)
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
