# NeoMundi Python SDK

[English](README.md) · [Français](README_FR.md)

[![PyPI version](https://img.shields.io/pypi/v/neomundi?style=flat-square)](https://pypi.org/project/neomundi/) ![REST](https://img.shields.io/badge/transport-REST-blue) ![SSE](https://img.shields.io/badge/transport-SSE-blue) ![Live](https://img.shields.io/badge/live_qualification-REST_%2B_SSE_passed_2026--11--13-green) ![Tests](https://img.shields.io/badge/offline_tests-395_passed-green)

NeoMundi product chain — **INSTALL** → TRACE → MEASURE → VERIFY → ACT. This repository is the **Python client**: it installs the chain into your application, instruments your own call, and exposes the measurements without interpreting them. It embeds no threshold and derives no verdict.

[Product architecture](https://github.com/neomundi-io/.github/blob/main/docs/PRODUCT_ARCHITECTURE.md) · [Capability audit](https://github.com/neomundi-io/.github/blob/main/docs/V2_FUNCTIONAL_AUDIT_2026-11-15.md) · [All components](https://github.com/neomundi-io/.github)

---

> **Connect your AI application. Trace every interaction. Measure its behavior.
> Verify the evidence.**

**INSTALL → TRACE → MEASURE → VERIFY** — the four steps this SDK touches. **ACT**
is the fifth step of the chain and is served by the platform's exports and
attestations, not by this package. For each step below, this README tells you
what is real today, what is partial, and what is still to be built. A promise you cannot reproduce is worse than no promise.

## What each step actually does

| Step | What it is | Status |
|---|---|---|
| **INSTALL** | `pip install neomundi` — `2.1.0` published 2026-11-15 | **Real** — `trace()` and `verify()` ship in the published wheel |
| **TRACE** | `client.trace()` — local stopwatch, correlation id, explicit submission | **Partial** — there is **no trace-only route on the API**; closing a trace submits one metered measurement |
| **MEASURE** | `client.govern()` (post-call REST) and `client.stream()` (SSE generation proxy) | **Real** — live-qualified against the hosted API on 2026-11-13, REST and SSE both passed |
| **VERIFY** | `client.verify()` / `client.verify_audit_certificate()` (public, unmetered API routes) and `verify_evidence_archive()` (independent Evidence verifier) | **Real for emission authenticity. Archive integrity needs a second package.** |

What **no** step does: establish that an AI answer is **true**. See
[the three meanings of "verify"](#verify).

## INSTALL

Python 3.9+. `httpx` is the only runtime dependency.

```sh
# The published release: everything documented below.
python -m pip install --upgrade neomundi

# Or from source, for contributors.
git clone https://github.com/neomundi-io/neomundi-python-sdk.git
cd neomundi-python-sdk
python -m pip install -e ".[dev]"
```

`neomundi` **2.1.0** was uploaded to PyPI on **2026-11-15**, and it is the
first published wheel to carry `trace()` and `verify()`. `2.0.0`
(2026-11-14) carried `govern()` and `stream()` only and remains installable.
Publication stays gated by an explicit manual workflow: exact tag, typed
confirmation, GitHub `pypi` environment and Trusted Publishing — **the
version was re-pointed, no guard was removed.**

The SDK code is licensed under [Apache-2.0](LICENSE), subject to
contributor-rights review; see the
[licensing boundaries](LICENSE_NOTICE.md). The **hosted Runtime Measurement
API remains proprietary and commercially metered** (authorised key, applicable
credits/quotas and service terms). An open-source SDK does not include free
hosted API access.

No API or provider credential is bundled, read implicitly or persisted. The
API environment is always explicit, through `base_url`: the SDK assumes no
host, so no call can leave for an environment you did not choose.

## TRACE

```python
import os
from neomundi import NeoMundiClient

with NeoMundiClient(
    api_key=os.environ["NEOMUNDI_API_KEY"],
    base_url=os.environ["NEOMUNDI_BASE_URL"],
) as client:

    with client.trace(client_trace_id="order-4711", model_name="gpt-4o") as trace:
        answer, usage = my_application(question)      # your own provider call
        trace.record(
            prompt=question,
            response=answer,
            token_count=usage.total_tokens,           # never guessed for you
        )

    record = trace.record_
    record.latency_ms     # MEASURED around your call, not declared by hand
    record.request_id     # the server's id — the only reliable correlation key
    record.acknowledged   # the server processed it
    record.registered     # None on REST: see below
    record.to_dict()      # safe to log: carries no prompt and no response
```

**What TRACE gives you, and nothing more:**

- the latency is **measured** with `time.monotonic()` around your block, where
  2.0.0 made you supply it by hand;
- a correlation id of yours, paired with the id the server returns;
- a record that is safe to log: `TraceRecord` holds prompt and response
  **lengths**, never their text — by construction, not by convention.

**What it refuses to pretend:**

- 🔴 **There is no trace-only route on the API.** All eight deployed routers
  were read on 2026-11-15: none accepts an interaction without measuring it.
  Closing a trace therefore issues `POST /v1/govern` — one metered call.
  `submit=False` opens no socket at all.
- 🔴 **The token count is never invented.** Without `token_count`, nothing is
  sent and a `ConfigurationError` is raised. The deployed contract requires it
  and the deployed response republishes it as
  `token_count_source: "caller_declared"` — the server counts nothing on this
  route.
- 🔴 **`registered` stays `None` on REST — and that is now an SDK choice, not
  a server gap.** Until 2026-11-15, `POST /v1/govern` answered 200 even when
  the log write had failed, and its wire contract published no persistence
  field at all. Since the deployment of `03e2b344` **both routes publish
  `log_persisted` and `log_write`**, and a real call was verified in
  production. This SDK does **not** interpret the REST pair yet: it arrives in
  `unknown_fields` and stays readable as `result.get("log_persisted")`.
  Typing it would be a new feature, not a documentation fix, so
  `TraceRecord.from_stream` remains the only path where `registered` carries
  a value. Read the raw field if you need the REST answer today.
- 🔴 **Your `client_trace_id` is not retained by the server.** The `metadata`
  field is accepted by the contract and dropped by the route. Correlation is
  therefore yours to keep: store the `(client_trace_id, request_id)` pair.
- ⚠ "Trace every interaction" means **you** instrument your application. This
  SDK does not hook your framework, and nothing is traced that you do not
  record.

## MEASURE

`govern()` and `stream()` are **unchanged**, and no existing call signature
moved. `token_count` and `latency_ms` stay required: the deployed contract
declares them required and the server derives neither.

```python
result = client.govern(
    token_count=128,                               # actual observed usage
    latency_ms=842.0,                              # actual measured latency
    llm_prompt="What is the capital of France?",
    llm_response="Paris.",
)
result.governance.decision          # ALLOW / FLAG
result.format_score("g_score")      # None stays None
result.measured_signals             # what was actually measured
result.unmeasured_signals           # and why the rest was not
result.audit.measurement_version    # the only number with scientific meaning
result.token_count_source           # "caller_declared" — not a server count
result.contract_version             # "neomundi.govern.rest/1.0"
```

Sending metrics only is allowed, and then no semantic check runs:
`measurement.status` reports `not_attempted`. An absent value stays `None` — no
numeric default exists anywhere in this package. A complete transport can
carry an incomplete measurement, and the two are reported separately.

For the SSE generation proxy — which calls your provider with your provider
key, and can incur provider cost and a NeoMundi charge — see
[the streaming guide](docs/STREAMING.md). Two fields are new there and matter:

```python
stream_result.log_persisted      # server-side registration confirmation (REST has it too since 2026-11-15)
stream_result.log_write          # already_exists / already_exists_divergent / failed
stream_result.token_count_source # provider_usage, or chunk_count_fallback
stream_result.token_count_unit   # "tokens", or "chunks" on the fallback path
```

`log_persisted` is `True` when the key is **absent**: the backend emits it only
on the non-nominal path. And on the fallback path `total_tokens` counts
**chunks**, not tokens — read the unit before comparing two observations.

## VERIFY

Three different questions wear the same verb. Mixing them is the most
expensive mistake in this whole journey.

**1. Emission authenticity — real, public, unmetered.**

```python
verdict = client.verify(result.request_id)
verdict.valid                 # True / False / None
verdict.payload_hash_match    # the canonical hash, recomputed server-side
verdict.signature_valid       # the Ed25519 JWS signature
```

`GET /v1/rgc/verify/{request_id}` recomputes the canonical hash from the source
log **and** verifies the stored signature, instead of trusting either. It needs
no API key and costs nothing. `valid is None` means **nothing was verified**:
no RGC contract has been emitted for that observation — which is a separate,
TIER_03-only call this SDK does not make. Reading that `None` as a failure
would turn "never signed" into "invalid signature".

The same tri-state rule governs audit certificates, and there it bites harder:

```python
cert = client.verify_audit_certificate("AT-2026-0001", sha256=printed_on_the_pdf)
```

**Without `sha256`, `valid` is `None` and nothing was verified.** No digest is
stored at issue time, so the value printed on the holder's document is the only
thing the service can compare against.

**2. Archive integrity — delegated to the independent verifier.**

```sh
python -m pip install neomundi-evidence-verify
```

```python
from neomundi import verify_evidence_archive

outcome = verify_evidence_archive("archive.zip")
outcome.exit_code              # 0, 1, 2, 3 or 4 — the program's own
outcome.verification_performed # False for 3 and 4: nothing ran
outcome.passed                 # True / False / None
```

This SDK **verifies nothing itself**: it invokes `neomundi-evidence` and
republishes its verdict and exit code without retranslating them, and a test
enforces that it imports no hashing, archive or cryptography module. A missing
verifier raises instead of returning a verdict — an absent tool produces no
"valid". Exit codes 3 and 4 exist precisely so that "nothing failed" and
"nothing ran" cannot return the same answer.

⚠ The conformance corpus is **not** in the PyPI wheel. `pip install` lets you
verify **your** archives; replaying the published corpus needs a `git clone` of
the [Evidence Gateway](https://github.com/neomundi-io/neomundi-evidence-gateway).

**3. Truthfulness of the AI answer — 🔴 none of the above.**

A verified measurement is a measurement you know was not altered. It says
nothing about whether the measured content is correct.
`factual_hallucination_score` is a signal produced by a judge, with its own
documented limits — not a verdict of truth. No certificate issued here
certifies an AI answer.

## Where we stand

| Item | State |
|---|---|
| REST + SSE implementation | Complete, unchanged by this branch |
| Live qualification of the installed SDK | **Done 2026-11-13: REST passed, SSE passed** against the hosted API |
| REST persistence declaration | **Verified in production 2026-11-15**: one authorised call returned `log_persisted: true` / `log_write: "inserted"`, and `GET /v1/govern/{request_id}` found the observation. Replaying that stored row returns `log_persisted: null` — a replay states no persistence verdict. |
| Offline tests | 395 passed; 12 optional historical captures skipped |
| CI | Python 3.9, 3.11, 3.12, 3.13 |
| Deployed schema parity | Measured byte-for-byte in [GitHub Actions](https://github.com/neomundi-io/neomundi-python-sdk/actions/runs/43526131929), and re-measured offline by this branch's fixtures |
| `trace()` / `verify()` | Published in `2.1.0` (2026-11-15). Absent from `2.0.0`. |
| Published measurement version | The SDK declares `3.3.0`, verified for `3.3.0` and `3.3.1`. **Production serves `3.5.0`**, which is deliberately *not* declared verified: nobody has verified it. The warning you will see is correct. |

That live qualification exercised a complete measurement and a progressive
stream. It did **not** exercise a withheld aggregate, a real error path
(402, 429…) or more than one SSE provider. Passing offline tests establishes
neither service availability nor compatibility with every provider.
See [the 3.5.0 compatibility scope](docs/COMPATIBILITY_350.md) and
[the executed checks](docs/VERIFICATION_V2.md).

## Data flows, briefly

`llm_prompt` and `llm_response` are transmitted to the measurement service and
processed in memory. Of them the platform persists: **never the prompt** (only
its length), and **extracts of the response** inside
`quality.suspect_phrases` when the factuality score passes its threshold.
`rag_context` and `documents` are never persisted. Three of five signals run on
models hosted on the service's own machine; factuality and semantic
instability call one subcontractor. Everything is hosted in Switzerland.
`TraceRecord` never carries content, so logging a trace cannot leak a prompt.

Full detail and retention:
[data flows and confidentiality](https://github.com/neomundi-io/neomundi-io-data-protection)
and [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

## Documentation

- [What this branch audited, and what it changed](docs/AUDIT_INSTALL_TRACE_MEASURE_VERIFY.md)
- [SSE lifecycle, errors, integrity and limits](docs/STREAMING.md) · [Français](docs/STREAMING_FR.md)
- [Known backend and SDK limitations](KNOWN_LIMITATIONS.md) · [Français](KNOWN_LIMITATIONS_FR.md)
- [Inspected REST contract](docs/CONTRAT_API.md) · [Measurement limits](docs/LIMITES.md)
- [Verification results and live qualification](docs/VERIFICATION_V2.md) · [3.5.0 compatibility scope](docs/COMPATIBILITY_350.md)
- [Migration from v0.1](docs/MIGRATION_V2.md) · [Audit and repairs delivered](docs/AUDIT_SDK_V2.md)
- [REST pilot guide](PILOT_INTEGRATION_GUIDE.md) · [Français](PILOT_INTEGRATION_GUIDE_FR.md)

## Run it

Every example runs offline against a mock transport and exits 0.

```sh
python -m pip install -e ".[dev]"
python -m pytest tests
python examples/05_parcours_complet.py    # INSTALL -> TRACE -> MEASURE -> VERIFY
python -m build
```

SDK version is a **client** version, not a measurement version. Check the
measurement version your deployment actually returns before comparing two
observations.

---

*Internal: NeoMundi crews start from the
[workspace cockpit](https://github.com/Neomundi-Labs/neomundi-workspace/blob/main/START_HERE.md),
pick the chantier in `CHANTIERS.md`, and come back to it afterwards to record
the result, the evidence and the next action. This document stays the detailed
entry point for the SDK itself.*
