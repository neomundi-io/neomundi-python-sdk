# NeoMundi Python SDK

**Status: v0.1.0 — Experimental / Pilot Evaluation**

Python client for the NeoMundi measurement API.

> ### Read this before anything else
>
> **📋 [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) — known backend
> limitations, verified functionality, and developer guidance.**
> **🚀 [`PILOT_INTEGRATION_GUIDE.md`](PILOT_INTEGRATION_GUIDE.md) — setup
> and first integration for pilot developers.**
>
> Three backend limitations are documented: **BL-001** (a trial key is
> suspended on its first call) and **BL-003** (`delta_g` is published while
> the aggregate is withheld) are **open and unchanged at `3.3.1`**;
> **BL-002** (a streaming decision depends on network fragmentation) is
> **partly corrected in `3.3.1`** — the decision no longer depends on the
> slicing, the published trajectory still does. None is worked around by
> this SDK — all three are surfaced.

> **Not published on PyPI.** Install from source only — see
> [Installation](#installation).
>
> **Compatibility, stated once.** REST contract compatibility of
> `POST /v1/govern` with measurement version **`3.3.1`** is verified by
> local tests and by replaying a production capture. **A direct call of
> the SDK against production has not been performed.** Verify
> compatibility with your own deployment before relying on results:
> [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) §6 gives the minimum
> check.

---

## Contents

| | |
|---|---|
| 1 | [What NeoMundi is](#what-neomundi-is) · [what this SDK does](#what-this-sdk-does) |
| 2 | [Requirements](#requirements) and [installation](#installation) |
| 3 | [First REST call](#first-rest-call) — the minimal one, then the real one |
| 4 | [Supported functionality](#supported-functionality-v010) |
| 5 | [Compatibility](#compatibility) and [known limitations](#known-limitations) |
| 6 | [Pilot guide and detailed documentation](#repository-documentation) |

---

## What NeoMundi is

NeoMundi is an independent **measurement** layer for the runtime behaviour
of AI systems. When your model produces a response, NeoMundi has that
response examined by automated instruments, records what each one said —
**and, critically, records when an instrument could not say anything** —
then derives indicators and an advisory verdict.

| Instrument | What it looks at | Signal |
|---|---|---|
Moderation | does the content fall into a hazard category | `semantic_risk` |
Coherence | is the response close to the prompt's subject | `coherence_score` |
Factuality (LLM judge) | does the response appear factually wrong | `factual_hallucination_score`, `semantic_instability_score` |

Those signals are aggregated into `stability_score` and `g_final`, and
yield an `ALLOW` or `FLAG` decision.

**Measurement is kept distinct from interpretation.** NeoMundi measures;
it does not decide for you, and it grants, refuses, suspends or modifies
no execution. A `FLAG` is advisory.

---

## What this SDK does

- calls `POST /v1/govern` — the **post-call** mode: you invoke your own
  model, then submit the response metrics;
- handles `X-API-Key` authentication, granular timeouts, and nine families
  of error;
- exposes **typed models** in which every nullable field is `Optional`;
- preserves the distinction between **"measured as 0"** and **"not
  measured"**, which is where NeoMundi's value lies;
- keeps the **full raw payload**, including fields this SDK version does
  not know about.

### What it deliberately does not do

| Not provided | Why |
|---|---|
**no score interpretation** — no `is_safe()`, no quality level | thresholds are server-side configuration choices and are not publicly calibrated. A client-side threshold would be an invention. |
**no numeric defaults** | an `or 0.0` would turn a missing measurement back into a reassuring zero. That is the defect the backend spent six remediation passes closing. A test verifies mechanically that no such default exists in the sources. |
**no automatic retry** | `POST /v1/govern` is not idempotent: each call creates an observation and debits a quota. See [Retries](#retries). |
**no SSE streaming** | separate workstream. The **decision** published by the SSE route is not invariant to how the provider slices its stream, so an SSE client would faithfully carry a non-reproducible verdict. |
**no longitudinal series** | comparing two observations requires strict conditions the SDK cannot verify on your behalf. See `docs/LIMITES.md`. |
**no PDF certificate verification** | the server-side proof mechanism has known limits. |

---

## Requirements

- **Python ≥ 3.9**
- a NeoMundi API key (`ct_live_…`, `ct_test_…` or `ct_trial_…`)
- the URL of your NeoMundi instance — **no default is provided**, so that
  no call can reach an environment you did not choose

## Installation

Not published. Install from source:

```bash
git clone https://github.com/neomundi-io/neomundi-python-sdk.git
cd neomundi-python-sdk

# build the wheel
python -m pip wheel . --no-deps --no-build-isolation -w dist

# install into an isolated virtual environment
python -m venv .venv
.venv/Scripts/python -m pip install dist/neomundi_sdk-0.1.0-py3-none-any.whl   # Windows
# .venv/bin/python   -m pip install dist/neomundi_sdk-0.1.0-py3-none-any.whl   # Linux / macOS
```

Or in development mode:

```bash
python -m pip install -e ".[dev]"
python -m pytest tests
```

---

## First REST call

### The minimal one

Four arguments. Two are required by the server (`token_count`,
`latency_ms`); the other two are what make it measure anything at all.

```python
from neomundi import NeoMundiClient

with NeoMundiClient(api_key="ct_test_...", base_url="https://your-instance") as client:
    result = client.govern(
        token_count=128,
        latency_ms=842.0,
        llm_prompt="What is the capital of France?",
        llm_response="The capital of France is Paris.",
    )

print(result.governance.decision)       # 'ALLOW' | 'FLAG'
print(result.format_score("g_score"))   # never raises, even when withheld
```

Want to see it run before you have a key? The three examples in
`examples/` use a simulated server and need neither key nor network:

```bash
python examples/01_premiere_mesure.py
```

### The real one

```python
from neomundi import NeoMundiClient

with NeoMundiClient(
    api_key="ct_test_...",
    base_url="https://your-instance",
) as client:
    result = client.govern(
        token_count=128,          # tokens in YOUR model's response
        latency_ms=842.0,         # observed latency
        cost=0.0031,              # in YOUR OWN unit — no currency is attached
        prompt_length=480,        # in CHARACTERS
        response_length=1200,     # in CHARACTERS
        model_name="gpt-4o-mini",
        llm_prompt="What is the capital of France?",
        llm_response="The capital of France is Paris.",
    )

print(result.governance.decision)        # 'ALLOW' | 'FLAG'
print(result.governance.decision_basis)  # why — see below
print(result.request_id)
print(result.audit.measurement_version)  # '3.3.1' on production today
```

**`llm_response` is the parameter that triggers the server-side checks.**
Without it no semantic signal is measured and `measurement.status` is
`not_attempted`.

Parameters left at `None` are **not sent**: the server applies its own
documented defaults. The SDK does not decide that an absent cost means
`0.0`.

### Reading the measurement, in the order that avoids misreadings

```python
# 1. Is the measurement complete? ALWAYS start here.
if result.measurement_incomplete:
    print("Incomplete:", result.missing_required_signals)
    print("This FLAG is NOT a statement about the response content.")

# 2. Why the decision is what it is.
result.governance.decision_basis
#   'measured_thresholds'     -> a threshold was crossed. The FLAG is about content.
#   'incomplete_measurement'  -> a required signal could not be measured.
#                                The FLAG is NOT about content.
#   'no_check_attempted'      -> no server-side check ran at all.
#   None                      -> observation predates backend version 3.3.0.

# 3. Signal by signal.
result.measurement_state("coherence_score")
#   MeasurementState.MEASURED
#   MeasurementState.NOT_MEASURED             -> a cause is available
#   MeasurementState.NOT_ATTEMPTED_OR_GATED   -> not launched OR gated by tier
#   MeasurementState.UNKNOWN                  -> the response does not say

result.is_measured("coherence_score")        # bool
result.unmeasured_reason("coherence_score")  # str | None
result.evaluator_of("coherence_score")       # instrument, model, fingerprints
```

### Reading an aggregate that may be `null`

```python
# FOR DISPLAY — never raises.
result.format_score("g_score", nd=4)              # '0.4920' | 'non mesuré'
result.format_score("g_score", when_none="n/a")

# FOR A COMPUTATION — raises an exception that NAMES the cause.
from neomundi import AggregateWithheldError
try:
    value = result.require("g_score")
except AggregateWithheldError as exc:
    print(exc.missing_required_signals)   # ['hallucination_score']
    print(exc.decision_basis)             # 'incomplete_measurement'

# WHAT NOT TO DO
f"{result.g_score:.2f}"   # TypeError as soon as the aggregate is withheld
```

### Unmeasured signals

**When an instrument fails, the backend returns the most reassuring value
it can**: `risk_score = 0.0`, `coherence_score = 1.0`, `factual = 0.0`. A
signal's validity is therefore **never** readable from its numeric value.

```python
# A measured 0.0 and a null are two different things.
result.quality.semantic_risk            # 0.0  -> measured, nothing detected
result.is_measured("semantic_risk")     # True

result.quality.factual_hallucination_score   # None -> not measured
result.unmeasured_reason("factual_hallucination_score")
# 'hallucination_judge_unavailable'
```

A `null` has **three possible meanings**, distinguishable as follows:

| Meaning | How to recognise it |
|---|---|
**not measured** — the check ran, produced nothing | the signal appears in `unmeasured_signals`, with its cause |
**not sold at this tier** | the signal is in neither list, and `measurement.status` is `complete` |
**not applicable on this route** | `trajectory_points` and `provider` are always `None` on REST — "not applicable here", not "zero" |

### Error handling

```
NeoMundiError
├── ConfigurationError        invalid parameter (before any network call)
├── TransportError            no HTTP response obtained
│   ├── TimeoutError
│   └── NetworkError
├── InvalidResponseError      2xx response that cannot be used
├── AggregateWithheldError    require() on a withheld aggregate
└── APIError                  the server returned an error status
    ├── AuthenticationError   401
    ├── PaymentRequiredError  402
    ├── PayloadTooLargeError  413
    ├── ValidationError       422  (+ field_errors)
    ├── RateLimitError        429  (+ retry_after, rate_limit_*)
    └── ServerError           5xx
```

Every `APIError` carries `status_code`, `error_code`, `detail`,
`request_id`, `server_timestamp`, **`body`** (the full raw body) and
`headers`. Nothing the server said is discarded.

Three backend quirks, handled without assumptions:

- **`402` covers three causes** the server does not separate: trial quota
  exhausted, wallet balance insufficient, per-key budget reached. Read
  `detail`.
- **`413` carries only two keys** (`error`, `detail`) — no `request_id`,
  no `timestamp`, because the middleware that sets them has not run. The
  SDK recovers `request_id` from the `X-Request-ID` header instead.
- **`422` has a `detail` that is a list** of objects, exposed normalised
  in `ValidationError.field_errors`.

### Retries

**No automatic retry.** `POST /v1/govern` is not idempotent:

| Effect of repeating a call | Mechanism |
|---|---|
a **new observation** is created | `request_id` is a fresh UUID per call |
the **quota or wallet is debited** | the debit precedes the work |
a **metering row** is written | `usage_events` table |
the account's **`delta_g` reference is overwritten** | per-account Redis key |

No idempotency header exists on this route.

```python
# On 429 the SDK gives you everything and does not sleep on your behalf.
except RateLimitError as exc:
    exc.retry_after            # seconds, from the Retry-After header — or None
    exc.rate_limit
    exc.rate_limit_remaining
    exc.rate_limit_reset

# An explicit policy, for those who accept the consequences:
from neomundi import RetryPolicy
client = NeoMundiClient(..., retry=RetryPolicy(max_attempts=3, on=(503,)))
```

**A timeout is NEVER retried, even with an active policy**: it is the one
case where the SDK cannot know whether the request was executed
server-side. A *received* `503`, by contrast, proves it was not.

---

## Supported functionality (v0.1.0)

| Area | Detail |
|---|---|
**Route** | `POST /v1/govern` (post-call) — the only route in scope |
**Auth** | `X-API-Key`; key **format** validated locally before any network call, so an invalid key consumes neither a request nor a quota unit |
**Models** | 11 immutable dataclasses (`frozen=True`): `GovernResult` + `Governance`, `Measurement`, `Quality`, `Runtime`, `Metrics`, `Baseline`, `Esi`, `Density`, `RagGrounding`, `Audit`, plus `SuspectPhrase`, `Citation`, `UngroundedSnippet` |
**Parsing** | **non-coercive**: a `"0.5"` string is never converted to `0.5`. The typed field becomes `None`, the raw value stays in `raw`, and a `ParseWarning` is recorded. A boolean is never read as a number. |
**Measurement state** | `MeasurementState` with four values, including a deliberately ambiguous `NOT_ATTEMPTED_OR_GATED` — the server does not distinguish "never launched" from "gated by tier" on the wire, and the SDK does not invent it |
**Traceability** | `is_measured()`, `unmeasured_reason()`, `measurement_state()`, `evaluator_of()`, `aggregates_publishable`, `missing_required_signals`, `measurement_incomplete` |
**Safe reads** | `require()` raises naming the cause; `format_score()` never raises; `get()`, `field_present()` |
**Forward compatibility** | unknown root fields are preserved in `raw` and listed in `unknown_fields`; a new backend field never breaks an integration |
**Errors** | 14 exception classes, raw server body and headers preserved, `request_id` recovered from the `X-Request-ID` header when the body omits it |
**Retries** | `RetryPolicy`, explicit, **disabled by default** |
**Typing** | PEP 561 marker (`py.typed`) shipped |
**Dependencies** | **`httpx` only** in production; `pytest` for development |
**Python** | ≥ 3.9 |

---

## Compatibility

> **REST contract compatibility of `POST /v1/govern` with measurement
> version `3.3.1` is verified by local tests and by replaying a
> production capture. A direct call of the SDK against production has not
> been performed.**

### Live compatibility: the contract is verified, the call is not

Two campaigns, and the distinction between them is the whole point of
this section.

**Against a local instance, `3.3.0`.** The SDK was exercised against a
running NeoMundi instance — a local one, built from backend commit
`68d6057cf620e430e6488da3cfcec9c471c75ed6`. Ten REST calls at tier
`TIER_02` with all three evaluators live, plus a fully degraded run, were
captured and replayed through the test suite: **zero type discrepancies,
zero unmodelled fields**, measurement version `3.3.0` as declared.

**Against the production contract, `3.3.1` — 2026-10-22.** Production
serves `3.3.1`, not `3.3.0`. Two independent checks closed that gap for
the REST route:

| Check | Nature of the evidence | Result |
|---|---|---|
Source comparison `68d6057` → deployed `aeff13c` | code inspection | **nothing under `app/models/` changed**, and the REST route did not change. One application file differs — the SSE path — plus the version string |
Replay of a real `3.3.1` production response through the client | replay of a production capture | **0 `parse_warnings`, 0 unknown root fields**, exact round-trip, aliases agreeing, coverage re-derivable |

A sanitised copy of that response ships as
`tests/fixtures/production_331/rest_complete_allow.json` and is exercised
by `tests/test_measurement_version_331.py`, so the check is reproducible
rather than merely reported.

What all of that establishes: **the contract this client models is the
contract production emits**.

What it does **not** establish, and this is not a formality — **no call
made by this SDK has ever reached a hosted deployment**, under `3.3.0` or
`3.3.1`. Every error family, every timeout and every authentication path
in this client has been exercised against a simulated transport only.
Behaviour under load is uncharacterised. No frozen OpenAPI specification
exists server-side, so verification against your own deployment remains
necessary — [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) §6 gives the
minimum check.

**Three backend limitations were observed during the first campaign** and
are documented as BL-001, BL-002 and BL-003. All three were re-read
against `3.3.1` on 2026-10-22: BL-001 and BL-003 live in files that are
byte-identical between the two commits and stand unchanged; BL-002 is the
reason `3.3.1` exists and is partly corrected by it. The SDK surfaces
them; it does not work around them.

### Which version number means what

Three numbers circulate, they are not the same number, and confusing them
is the most common way to reach a wrong conclusion about this SDK.

| | Value today | Where you read it | What it tells you |
|---|---|---|---|
| **SDK version** | `0.1.0` | `neomundi.__version__` | which client you installed |
| **Measurement version** | `3.3.1` | `result.audit.measurement_version` — **a response, nowhere else** | which formula produced the numbers. **The only one with scientific meaning**: two results under two different values are not comparable for the same input |
| **Application version** | `3.0.0` | `GET /v1/health`, field `version` | which service build is running — **and nothing about the measurement** |

```python
import neomundi
neomundi.__version__                 # '0.1.0'   — the client
result.audit.measurement_version     # '3.3.1'   — the formula
# GET /v1/health -> {"version": "3.0.0", ...}    — the service build
```

**`GET /v1/health` does not publish the measurement version**, and no
other endpoint does either: `/openapi.json`, `/docs`, `/v1/version` and
`/version` all answer `404`. Reading the measurement version therefore
costs one metered observation. There is no free way to get it.

```python
import neomundi
served = result.audit.measurement_version

if served not in neomundi.API_CONTRACT["verified_measurement_versions"]:
    ...   # unverified contract — stop, and report
elif served != neomundi.API_CONTRACT["measurement_version"]:
    ...   # parsing is safe; the SERIES is not comparable. Record `served`.
```

---

## Known limitations

Read before communicating any figure produced by this SDK. The complete
register is [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md); methodological
detail is in [`docs/LIMITES.md`](docs/LIMITES.md).

### The scores do not use the whole `[0, 1]` range

| Measured situation | `stability_score` | `g_final` |
|---|---|---|
perfect response | 1.00 | 1.00 |
hallucination scored 0.73 | 0.76 | **0.90** |
content judged unsafe | 0.72 | **0.89** |
**maximal hallucination (1.0)** | **0.67** | **0.86** |

Effective range: `stability_score ∈ [0.60 ; 1.00]` and
`g_final ∈ [0.40 ; 1.00]` for a response of realistic length. Two of
`g_final`'s four terms are numerically saturated and contribute a near
constant ≈ 0.3988.

**The verdict (`decision`) is more informative than the score.**

The documented numeric floor is a property of the reference formula, not
a percentage of factual correctness. When required signals are
unmeasured, aggregates may instead be withheld as `null`. The floor alone
does not establish the cause of a historical `0.40` result; its version,
measurement status and trace must also be checked.

```python
result.audit.measurement_version     # which formula produced it
result.measurement.status            # complete | partial | not_attempted
result.audit.trace_id                # the record to pull
```

### `stability_score` exists twice, with inverted scales

```python
result.quality.stability_score   # G / 0.60       -> 1 = stable
result.metrics.stability_score   # 1 − G / 0.60   -> 0 = stable
```

The SDK keeps both full paths and **exposes no shortcut**: picking one of
the two senses would settle an ambiguity in the contract. There is no
`result.stability_score`.

### Other homonyms preserved as-is

- `esi.q_value` (`min(1, N/E)`) ≠ `baseline.esi_q` (sliding-window
  variability, in-process server memory)
- `quality.information_density` (text density, enters no aggregate) ≠
  `density.informational_density` (feeds `g_final`'s `P` term)

### `baseline.delta_E` — ambiguous sign

The server-side field description states
`observed_energy - reference_energy`; the implementation computes
`reference − observed`, the opposite. **Reported, not settled.** The SDK
exposes the raw value and recomputes nothing.

### `delta_g` does not measure drift

It is the `G` difference against the **previous request from the same
account**, whatever question was asked. It may carry a number while
`g_score` is `None`. Do not read it as a drift signal.

Requests from different users or sessions sharing an account also share
the previous-request reference. A change between unrelated requests is
not evidence of drift. Session-level comparisons would require an
explicitly scoped reference and comparable inputs; the SDK does not
provide that isolation.

**Separate API keys do not isolate it either.** The reference is stored
per **account**, so every key issued to one account writes to and reads
from the same slot. Separate accounts, or a reference you scope yourself,
are the only isolations available today.

### `confidence` is not statistical confidence

It is instrumental coverage: `checks_succeeded / checks_attempted`, with a
denominator ≤ 3. Its only possible values are `0`, `1/3`, `1/2`, `2/3`,
`1`.

For display, use **"check coverage"**, ideally alongside the counts (for
example, `3/3`), rather than "100% confidence". This is not a probability
that the response is correct. Read it together with
`measurement.status`: a coverage of `1.0` when **no checks were
attempted** does not establish successful evaluation.

```python
result.measurement.coverage          # 1.0 — but of what?
result.measurement.status            # 'not_attempted' -> nothing ran
result.measurement.confidence_basis  # 'no_server_check' vs 'measurement_coverage'
```

`confidence_basis` is the field that names the difference outright.

### Two results are only comparable under conditions

Same `measurement_version`, same coverage, same evaluator models, same β
weights, same route. The SDK exposes what is needed to check this:

```python
result.audit.measurement_version
result.esi.betas
result.evaluator_of("factual_hallucination_score")["config_fingerprint"]
result.measurement.coverage
```

### What NeoMundi does not demonstrate

A high score does **not** demonstrate that a response is true, that
content is safe, that there is no hallucination, or that drift is under
way. The factuality judge is a language model scoring a text, with no
external source, at a non-zero temperature — **two identical calls can
produce two different scores, and that spread has not yet been measured.**

---

## Confidentiality requirements

| Requirement | How this SDK honours it |
|---|---|
**no real API key in the repository** | fixtures use `ct_test_0000…`; `tests/test_no_secret_leak.py` sweeps the whole repository and fails on any plausible key |
**the key never leaves the header** | 11 tests verify it is absent from `repr`, `str`, exception messages, logs, the request body and the URL |
**the key is masked in diagnostics** | `repr(client)` shows `ct_live_***9999` — prefix and last four characters only |
**no logging** | the SDK emits no log records at all in v0.1; a test freezes this property so a future addition cannot leak the key by accident |
**no network access in tests** | every test goes through `httpx.MockTransport`; examples target `example.invalid`, an RFC 2606 reserved domain whose DNS resolution always fails |
**the real-key example cannot run** | `examples/90_cle_reelle.py.disabled` carries a non-executable extension, verified by test |
**synthetic data only** | no real text, no client data, no personal data anywhere in the repository |

If you capture real responses for validation, **redact them before
committing**: `.gitignore` excludes `tests/fixtures/captured/` precisely
so that execution data is never versioned automatically.

---

## Tests

```bash
python -m pytest tests
```

| Module | Scope |
|---|---|
`test_client.py` | client construction, authentication, request shape, parameter validation, resource closing |
`test_models.py` | complete / partial / gated / not-attempted measurements; `null`; signals; unknown fields; type drift; homonyms; immutability |
`test_errors.py` | 401, 402, 413, 422, 429, 500, 502, 503, 418; timeouts; network failures; invalid JSON; empty body |
`test_retry.py` | no retry by default on any status; a timeout is never retried even with a policy |
`test_contract_drift.py` | no numeric default; no backend import; no undeclared dependency; no embedded threshold (AST-checked); fixture ↔ contract consistency |
`test_measurement_version_331.py` | the REST surface under measurement version `3.3.1`: no parse warning, no unknown root field, exact round-trip, provenance exposed, version gap still detectable |
`test_no_secret_leak.py` | no key in `repr`, messages, logs, body or URL; repository-wide key sweep |
`test_examples.py` | the three examples run and exit 0 |

Every fixture declares its origin: `derived_from_code` (structure and
values taken from the backend contract), `synthetic` (a payload the
backend does not emit, built to exercise SDK robustness), or `captured`
(a real response recorded from a running instance).

**Two suite scopes, deliberately distinguished:**

| Scope | Fixtures | Result |
|---|---|---|
| Repository / CI | `derived_from_code` + `synthetic` + the sanitised `3.3.1` production payload | **225 passed, 12 skipped** |
| Local, with captures | the above + 11 `3.3.0` `captured` | **347 passed** |

The 12 skipped tests are `test_captured_fixtures.py`, which replays the
`3.3.0` recorded payloads. `tests/fixtures/captured/` is excluded from
the repository — recorded responses are execution data, not source — so
those tests skip with a stated reason wherever the directory is absent,
CI included. They are not a weaker part of the suite; they are the only
part that can observe a divergence between the contract as read and the
contract as served.

`tests/fixtures/production_331/` is the one exception that **is**
shipped: the `3.3.1` production response it holds carries no prompt, no
response text and no evaluator identity, so it could be sanitised safely.
Its `_fixture_redacted` key lists every field that was replaced.
`tests/test_measurement_version_331.py` runs against it in CI.

**A pass on simulated transport does not validate production behaviour**,
and a pass on captured fixtures validates one instance at one commit, not
a deployment. See [Known limitations](#known-limitations).

### Examples

| Example | Server | Run |
|---|---|---|
`examples/01_premiere_mesure.py` | **simulated** | `python examples/01_premiere_mesure.py` |
`examples/02_mesure_partielle.py` | **simulated** | `python examples/02_mesure_partielle.py` |
`examples/03_gestion_erreurs.py` | **simulated** | `python examples/03_gestion_erreurs.py` |
`examples/90_cle_reelle.py.disabled` | **real** | **not executable** — read its header |

---

## Reference contract

```python
import neomundi
neomundi.API_CONTRACT
# {'backend_commit': '68d6057cf620e430e6488da3cfcec9c471c75ed6',
#  'measurement_version': '3.3.0',
#  'verified_measurement_versions': ('3.3.0', '3.3.1'),
#  'normalizer_version': '1.0.0',
#  'route': 'POST /v1/govern',
#  'contract_source': 'govern-v3/app/models/responses.py, requests.py',
#  'openapi_frozen': False}
```

**`openapi_frozen: False` matters.** No frozen OpenAPI specification
exists server-side, and `/openapi.json` is disabled in production. This
SDK's models were derived from reading the backend response and request
models **at that precise commit**, then confirmed against responses
captured from an instance built from that same commit. Naming the commit
is the only way to state what this SDK corresponds to: absent a published
specification, there is nothing else to point at.

**The two version keys answer two different questions.**
`measurement_version` names the commit this client was derived from.
`verified_measurement_versions` names every measurement version whose
REST surface has been verified identical to it — `3.3.1` was added on
2026-10-22, on the evidence set out in
[`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) §6.

A served version **outside** the verified list means fields may have
changed meaning: stop and report. A served version **inside** it but
different from `measurement_version` means parsing is safe while the
series is not comparable — record the served version with every
observation.

---

## Next steps

### Done — live capture against a local instance

The capture campaign that previously stood here has been run. Against a
local stack built from backend commit `68d6057`, ten `TIER_02` calls with
all three evaluators live plus one fully degraded run were recorded,
redacted, and replayed through the suite: **0 `parse_warnings`, 0
unmodelled root fields**, `measurement_version 3.3.0`, and all three
values of `decision_basis` exercised (`measured_thresholds`,
`incomplete_measurement`, `no_check_attempted`).

Discrepancies were treated as information rather than as SDK bugs. Three
of them turned out to be backend defects and are recorded as BL-001,
BL-002 and BL-003 in [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md). None
has been worked around in the client.

### Done — contract verification against production's `3.3.1`

2026-10-22. Production serves measurement version `3.3.1`; this SDK was
derived from `3.3.0`. The gap was closed for the REST route by source
comparison between the two commits and by replaying a real `3.3.1`
production response through the client — **0 `parse_warnings`, 0
unmodelled root fields**. `3.3.1` is now listed in
`API_CONTRACT["verified_measurement_versions"]`, a sanitised copy of the
response ships as a fixture, and the three backend limitations were
re-read against it rather than assumed closed by the version bump.

**This did not involve a call made by this SDK**, and the item below
stays open because of that.

### Open — what would change the status next

| # | Action | What it would establish |
|---|---|---|
| 1 | **One `POST /v1/govern` made by this SDK against the hosted deployment** | The only missing piece: that an end-to-end call works, not merely that the contract matches. Blocked on a credential, not on the code — see below |
| 2 | Backend publishes a **frozen OpenAPI document** | Contract drift becomes detectable mechanically instead of by capture |
| 3 | Resolve the residue of **BL-002** (ΔG invariance to slicing) | A prerequisite to any streaming support in this SDK. **`3.3.1` closed the decision half; the trajectory half is still open, and a backend test requires that it stay visible** |
| 4 | Backend exposes an **`Idempotency-Key`** on `POST /v1/govern` | Would make retry-on-timeout safe; until then no retry is performed |
| 5 | A pilot integration reports **results** back | First evidence from outside this repository — **feedback received 2026-10-20, integration results still pending** |

**On item 1, precisely.** The verification session of 2026-10-22 could
not execute it: the production credential is sealed in an operator-side
key store whose decryption the session was not permitted to perform, and
a `POST /v1/govern` creates an observation and debits a quota, so it is
not something to attempt speculatively. The call itself is one request.
Everything that can be verified without it has been.

**First external pilot feedback received — 20 October 2026.** A pilot
reviewed the SDK, reported straightforward installation, and highlighted
clarification needs around `g_final`, check coverage and the account
scope of `delta_g`. Those three points are addressed in
[Known limitations](#known-limitations) above. **Integration results and
the paired-control detection experiment remain pending.**

**Criterion for promotion beyond "Experimental / Pilot Evaluation"**:
items 1 and 2 above, plus at least one pilot integration whose results
have actually been observed. Local verification alone is not sufficient.
**A documentation review is not an integration**: no pilot integration
result has been observed to date, so the criterion is not met.

---

## Repository documentation

**Start here, in this order.**

| Document | Language | Read it for |
|---|---|---|
[`PILOT_INTEGRATION_GUIDE.md`](PILOT_INTEGRATION_GUIDE.md) | English | **zero to a first correctly read measurement.** Access, install, configure, call, read the result, report an anomaly |
[`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) | English | **what is verified, how, and what is not.** The BL/SL register, and §6 — the version-compatibility rules and the minimum check against your own deployment |
[`docs/CONTRAT_API.md`](docs/CONTRAT_API.md) | French | the backend contract as surveyed, field by field, with the three recorded discrepancies between description and implementation |
[`docs/LIMITES.md`](docs/LIMITES.md) | French | inherited methodological limits, with the computed value tables |
[`PLAN_IMPLEMENTATION.md`](PLAN_IMPLEMENTATION.md) | French | design rationale: why no pydantic, why no retry, why `null` is preserved |
[`CHANGELOG.md`](CHANGELOG.md) | French | what changed, when, and on what evidence |
[`LICENSE_NOTICE.md`](LICENSE_NOTICE.md) | French | licence status — **not settled**, see below |

The developer documentation is in French, matching the audit corpus it
derives from; the README and the pilot guide are the English entry
points. **The two languages state the same facts** — the measurement
version verified, the evidence behind it, and the missing live call —
and any divergence between them is a defect worth reporting (§7 of the
pilot guide).

## Licence

**Not settled.** See [`LICENSE_NOTICE.md`](LICENSE_NOTICE.md).

No `LICENSE` file is shipped, because the licence choice is a product
decision that has not been made. `Private :: Do Not Upload` is declared in
`pyproject.toml` so that an accidental PyPI upload is refused by the index.
