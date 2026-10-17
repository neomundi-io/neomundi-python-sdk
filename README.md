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
> Three backend defects are open and documented: **BL-001** (a trial key is
> suspended on its first call), **BL-002** (a streaming decision depends on
> network fragmentation), **BL-003** (`delta_g` is published while the
> aggregate is withheld). None is worked around by this SDK — all three are
> surfaced.

> **Not published on PyPI.** Install from source only — see
> [Installation](#installation).
>
> **Compatibility verified against a local instance** built from backend
> commit `68d6057`, measurement version `3.3.0` — and **against no hosted
> deployment**. Verify compatibility with your own deployment before relying
> on results: see [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) §6.

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

## v0.1.0 feature set

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
print(result.audit.measurement_version)  # '3.3.0'
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

## Known limitations

Read before communicating any figure produced by this SDK. The complete
register is [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md); methodological
detail is in [`docs/LIMITES.md`](docs/LIMITES.md).

### Live compatibility: verified locally, not against any deployment

The SDK **has** been exercised against a running NeoMundi instance — a
local one, built from backend commit
`68d6057cf620e430e6488da3cfcec9c471c75ed6`. Ten REST calls at tier
`TIER_02` with all three evaluators live, plus a fully degraded run, were
captured and replayed through the test suite: **zero type discrepancies,
zero unmodelled fields**, measurement version `3.3.0` as declared.

What that establishes: the modelled contract matches what an instance
built from the reference commit actually emits.

What it does **not** establish: behaviour against any hosted or shared
deployment, under load, or on another backend version. No frozen OpenAPI
specification exists server-side, so verification against your own
deployment remains necessary — [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) §6
gives the minimum check.

**Three backend defects were observed during that campaign** and are
documented as BL-001, BL-002 and BL-003. The SDK surfaces them; it does
not work around them.

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

### `confidence` is not statistical confidence

It is instrumental coverage: `checks_succeeded / checks_attempted`, with a
denominator ≤ 3. Its only possible values are `0`, `1/3`, `1/2`, `2/3`,
`1`.

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
`test_no_secret_leak.py` | no key in `repr`, messages, logs, body or URL; repository-wide key sweep |
`test_examples.py` | the three examples run and exit 0 |

Every fixture declares its origin: `derived_from_code` (structure and
values taken from the backend contract), `synthetic` (a payload the
backend does not emit, built to exercise SDK robustness), or `captured`
(a real response recorded from a running instance).

**Two suite scopes, deliberately distinguished:**

| Scope | Fixtures | Result |
|---|---|---|
| Repository / CI | `derived_from_code` + `synthetic` | **206 passed, 12 skipped** |
| Local, with captures | the above + 11 `captured` | **328 passed** |

The 12 skipped tests are `test_captured_fixtures.py`, which replays real
recorded payloads. `tests/fixtures/captured/` is excluded from the
repository — recorded responses are execution data, not source — so those
tests skip with a stated reason wherever the directory is absent, CI
included. They are not a weaker part of the suite; they are the only part
that can observe a divergence between the contract as read and the
contract as served.

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

If `result.audit.measurement_version` differs from
`API_CONTRACT["measurement_version"]`, results are not comparable with a
series produced under the expected version, and fields may have changed
meaning.

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

### Open — what would change the status next

| # | Action | What it would establish |
|---|---|---|
| 1 | Replay the same campaign against a **hosted** test deployment | That the contract holds outside a locally built instance |
| 2 | Backend publishes a **frozen OpenAPI document** | Contract drift becomes detectable mechanically instead of by capture |
| 3 | Resolve **BL-001** (SSE decision invariance) | A prerequisite to any streaming support in this SDK |
| 4 | Backend exposes an **`Idempotency-Key`** on `POST /v1/govern` | Would make retry-on-timeout safe; until then no retry is performed |
| 5 | A pilot integration reports back | First evidence from outside this repository — **none recorded to date** |

**Criterion for promotion beyond "Experimental / Pilot Evaluation"**:
items 1 and 2 above, plus at least one pilot integration whose results
have actually been observed. Local verification alone is not sufficient,
and no such pilot observation exists yet.

---

## Repository documentation

| Document | Language | Contents |
|---|---|---|
`docs/CONTRAT_API.md` | French | the backend contract as surveyed, field by field, with the three recorded discrepancies between description and implementation |
`docs/LIMITES.md` | French | inherited methodological limits, with the computed value tables |
`PLAN_IMPLEMENTATION.md` | French | design rationale: why no pydantic, why no retry, why `null` is preserved |
`CHANGELOG.md` | French | v0.1.0 contents and design decisions |
`LICENSE_NOTICE.md` | French | licence status — **not settled**, see below |

The developer documentation is in French, matching the audit corpus it
derives from. This README is the English entry point.

## Licence

**Not settled.** See [`LICENSE_NOTICE.md`](LICENSE_NOTICE.md).

No `LICENSE` file is shipped, because the licence choice is a product
decision that has not been made. `Private :: Do Not Upload` is declared in
`pyproject.toml` so that an accidental PyPI upload is refused by the index.
