# Pilot Integration Guide

**Status: v0.1.0 — Experimental / Pilot Evaluation**

This guide takes a pilot developer from zero to a first correctly read
measurement. It assumes you have been granted access to this private
repository and have received a test API key through a separate channel.

**Read [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) before you quote any
number this SDK returns.** Three backend defects are open: BL-001, BL-002
and BL-003. One of them (BL-001) may stop your very first call, and the
error message it produces is misleading — §7 tells you how to recognise
it.

---

## 1. Install from the private repository

### Access

This repository is **private**. Access is granted **individually to
authorized pilots** — there is no organization-wide access, no public
mirror, and no anonymous clone. If `git clone` fails with a 404, the
likely cause is that your GitHub account has not been added yet, not that
the URL is wrong. Contact your NeoMundi point of contact.

**The package is not on PyPI.** `pip install neomundi-sdk` will not
install this SDK. Install it from the repository.

### Authenticate to GitHub

Pick whichever you already use:

- **SSH** — your public key registered on your GitHub account.
- **HTTPS + personal access token** — a token with `repo` scope, stored
  in your platform credential helper.
- **GitHub CLI** — `gh auth login`, then `gh auth setup-git`.

Do not embed a token in a URL that ends up in `requirements.txt`, a
Dockerfile, or shell history.

### Install

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate

# SSH - replace <commit-sha> with the SHA supplied to you
pip install "git+ssh://git@github.com/neomundi-io/neomundi-python-sdk.git@<commit-sha>"

# or HTTPS, with credentials supplied by your credential helper
pip install "git+https://github.com/neomundi-io/neomundi-python-sdk.git@<commit-sha>"
```

**There is no git tag and no GitHub release** for this version: pin the
commit SHA your contact gives you, never a branch. `main` moves, and a
measurement should be attributable to one exact client version. Record
the SHA you installed alongside your results (section 6).

If you prefer a working copy:

```bash
git clone git@github.com:neomundi-io/neomundi-python-sdk.git
cd neomundi-python-sdk
git checkout <commit-sha>
pip install -e .
```

### Requirements

| | |
|---|---|
| Python | **3.9 or later** (tested on 3.9, 3.11, 3.12, 3.13) |
| Runtime dependency | **`httpx` only** |

No pydantic, no requests, no plugin system. `httpx` is deliberately the
single runtime dependency — see §6 of `KNOWN_LIMITATIONS.md` for why
pydantic was rejected.

### Verify the install

```bash
python -c "import neomundi; print(neomundi.__version__); print(neomundi.API_CONTRACT)"
```

Expected:

```
0.1.0
{'backend_commit': '68d6057cf620e430e6488da3cfcec9c471c75ed6',
 'measurement_version': '3.3.0',
 'normalizer_version': '1.0.0',
 'route': 'POST /v1/govern',
 'contract_source': 'govern-v3/app/models/responses.py, requests.py',
 'openapi_frozen': False}
```

`API_CONTRACT` names the exact backend commit this client was built
against. Keep it in your notes — §6 explains why.

---

## 2. Configure your environment

### Your API key

You will receive a key with one of these prefixes:

| Prefix | Meaning |
|---|---|
| `ct_test_` | test environment |
| `ct_trial_` | trial quota |
| `ct_live_` | **production. Do not use one for pilot evaluation.** |

The client rejects anything that does not start with one of the three,
and raises `ConfigurationError` before any network call.

**No real key appears anywhere in this repository, and none should
appear in yours.** Put it in the environment:

```bash
export NEOMUNDI_API_KEY="ct_test_..."      # value supplied to you separately
export NEOMUNDI_BASE_URL="https://..."     # URL supplied to you separately
```

On Windows PowerShell:

```powershell
$env:NEOMUNDI_API_KEY = "ct_test_..."
$env:NEOMUNDI_BASE_URL = "https://..."
```

Checklist before your first commit:

- [ ] the key is **not** in source, a notebook, a test fixture, or a
      container image layer;
- [ ] `.env` is in your `.gitignore`;
- [ ] the key is not in a CI log (`echo $NEOMUNDI_API_KEY` in a build
      step publishes it to everyone who can read the build);
- [ ] you know who else holds a copy of it.

The SDK masks the key in every `repr`, exception message and log record,
and a dedicated test enforces that (`tests/test_no_secret_leak.py`). That
protects you from the SDK leaking it. It cannot protect you from your own
code printing it.

### Construct the client

```python
import os
from neomundi import NeoMundiClient

client = NeoMundiClient(
    api_key=os.environ["NEOMUNDI_API_KEY"],
    base_url=os.environ["NEOMUNDI_BASE_URL"],
)
```

Use it as a context manager so the underlying HTTP connection pool is
closed:

```python
with NeoMundiClient(api_key=..., base_url=...) as client:
    result = client.govern(...)
```

### Timeouts

Defaults: `connect=10s`, `read=60s`, `write=10s`, `pool=10s`.

The 60-second read timeout is not padding. A complete measurement calls
three evaluators; on a loaded instance the end-to-end call can take tens
of seconds. Lowering the read timeout will turn slow measurements into
`TimeoutError` without producing any measurement.

```python
client = NeoMundiClient(api_key=..., base_url=..., timeout=120)
```

### Retries — read this before adding any

**`POST /v1/govern` is not idempotent and there is no
`Idempotency-Key`.** Each accepted call creates an observation, debits
quota or wallet, writes a usage event, and overwrites the server-side
`delta_g` reference.

The SDK therefore **never retries a timeout**, by design, even if you
configure a retry policy. A timeout means you do not know whether the
server processed the call. Retrying would risk double-charging and a
duplicate observation.

```python
from neomundi import RetryPolicy

# Retries 503 only — a status that means "not processed".
client = NeoMundiClient(..., retry=RetryPolicy(max_attempts=3, on=(503,)))
```

Do not wrap `client.govern()` in your own retry loop for timeouts. If you
need at-most-once semantics, keep your own request log and reconcile.

---

## 3. Your first REST call

```python
import os
from neomundi import NeoMundiClient

PROMPT = "How many sides does an equilateral triangle have?"
ANSWER = "An equilateral triangle has three sides of equal length."

with NeoMundiClient(
    api_key=os.environ["NEOMUNDI_API_KEY"],
    base_url=os.environ["NEOMUNDI_BASE_URL"],
) as client:
    result = client.govern(
        # Required.
        token_count=18,
        latency_ms=410.0,
        # Strongly recommended: without the texts, the semantic
        # evaluators have nothing to measure.
        llm_prompt=PROMPT,
        llm_response=ANSWER,
        # Optional context.
        cost=0.0004,
        prompt_length=len(PROMPT),
        response_length=len(ANSWER),
        model_name="your-model-name",
    )

print(result.governance.decision)        # ALLOW / FLAG / BLOCK
print(result.governance.decision_basis)  # how that decision was reached
print(result.format_score("g_score"))    # never raises
```

### This is a post-call API

You call your own model first, then send the **observed** metrics of the
response you actually got. NeoMundi does not call your model and does not
sit in your request path.

### Parameter names

Parameter names are **exactly** the server contract's names
(`GovernRequest` / `RawMetrics`). The SDK introduces no third vocabulary
on top of the server's and the glossary's.

### Two parameters that behave in ways worth knowing

| Parameter | Behaviour |
|---|---|
| `cost` | **Unitless as far as the server is concerned.** It is divided by a per-source-type ceiling to produce a dimensionless ratio. The requirement is **consistency**: use the same unit for every call of one integration, or `cost_proxy` compares nothing. |
| `semantic_risk` | A value you declare — **overwritten by the server's own measurement** when `llm_response` is supplied and moderation succeeds. Supplying it does not pin it. |

### Omit `llm_response` and you get no semantic measurement

Without `llm_prompt` / `llm_response`, the three evaluators have no text.
The call succeeds, but `decision_basis` will be `no_check_attempted` —
a decision reached without any semantic check. That is a legitimate mode,
and it is explicitly declared rather than silently degraded. Just do not
read such a result as "nothing wrong was found".

---

## 4. Read the results correctly

### The three access patterns

| Pattern | Use when |
|---|---|
| `result.g_score` | plain read; returns `None` if the aggregate was withheld |
| `result.require("g_score")` | you need the number and want a clear `AggregateWithheldError` otherwise |
| `result.format_score("g_score")` | display; **never raises**, returns a readable string in every case |

For display, use `format_score`. For logic, use `require` and catch:

```python
from neomundi import AggregateWithheldError

try:
    score = result.require("g_score")
except AggregateWithheldError as exc:
    # The measurement was incomplete. This is information, not an error
    # in your code.
    log.info("aggregate withheld: %s", exc)
    score = None
```

### What the main fields mean

| Field | Meaning |
|---|---|
| `result.governance.decision` | `ALLOW`, `FLAG` or `BLOCK` |
| `result.governance.decision_basis` | **how** it was reached — see table below |
| `result.g_score` | `G`, the quality aggregate |
| `result.g_final` | the ESI composite |
| `result.aggregates_publishable` | `False` → aggregates are withheld |
| `result.missing_required_signals` | names the signals that stopped publication |
| `result.measured_signals` / `result.unmeasured_signals` | per-signal state |
| `result.audit.measurement_version` | the measurement version that produced this row |

`decision_basis` is the field that tells you how much the decision is
worth:

| Value | Meaning |
|---|---|
| `measured_thresholds` | decided against thresholds on **measured** signals |
| `incomplete_measurement` | a required signal was not measured; aggregates withheld |
| `no_check_attempted` | no semantic check was run at all |

**Log `decision_basis` next to every decision you record.** An `ALLOW`
under `no_check_attempted` and an `ALLOW` under `measured_thresholds` are
not the same statement, and nothing else in your log will distinguish
them later.

### Five homonym traps

Different blocks reuse the same field name with **different, sometimes
inverted** meanings. Always keep the full path.

| Name | The trap |
|---|---|
| `stability_score` | `result.quality.stability_score`: **1 = stable**. `result.metrics.stability_score`: **0 = stable** — the same concept on an inverted scale. |
| density | two different densities in two blocks |
| `Q` | `result.esi.q_value` and `result.baseline.esi_q` are not the same quantity |
| `delta_E` | two definitions; and see BL-003 on its sign |
| counters named "tokens" | some count **chunks**, not tokens |

Never write `score = r.get("stability_score")` against a flattened dict.
Write `r.quality.stability_score` or `r.metrics.stability_score`, and know
which scale you are on.

### What the scores do not do

They do not use the whole `[0, 1]` range. In practice
`stability_score ∈ [0.60 ; 1.00]` and `g_final ∈ [0.40 ; 1.00]`. A
`g_final` of 0.45 is near the floor, not "slightly below average". §3 of
the README and `docs/LIMITES.md` give the derivation.

**And the headline caveat:** a stability score is not evidence of truth,
safety, absence of hallucination, or predictive capability. It is a
measurement of specified signals under stated conditions. Nothing more
is claimed, and nothing more should be reported.

### Parse warnings — the field to monitor

```python
for w in result.parse_warnings:
    log.warning("contract drift: %s expected %s got %s = %s",
                w.path, w.expected, w.received_type, w.received_repr)
```

The SDK **never coerces**. It will not turn `"0.5"` into `0.5`, nor read
a boolean as a number. When the server sends a type the contract does not
declare, the SDK records a `ParseWarning` and leaves the field unset
rather than guessing.

A non-empty `parse_warnings` is **not an SDK bug**. It means the server
emitted something the contract does not declare — a finding to report
(§7), not something to work around.

In the validation campaign against an instance built from commit
`68d6057`, `parse_warnings` was empty on all 11 captured responses. If
you see entries, something differs on your deployment and that is worth
knowing.

---

## 5. Recognise a partially measured result

This is the part of NeoMundi that distinguishes it, and the part most
easily misread.

### The discipline

The backend does not publish aggregates built on signals it could not
measure. When a required signal is missing, `g_score` is `null` and the
response says so. The SDK transports that faithfully and does not fill
the gap with a zero or a default.

### Detecting it

```python
if result.aggregates_publishable is False:
    print("aggregates withheld")
    print("missing:", result.missing_required_signals)
    print("basis:", result.governance.decision_basis)
```

Or per signal:

```python
from neomundi import MeasurementState

for signal in ("coherence_score", "semantic_risk",
               "factual_hallucination_score", "semantic_instability_score"):
    state = result.measurement_state(signal)
    if state is MeasurementState.NOT_MEASURED:
        print(f"{signal}: not measured — {result.unmeasured_reason(signal)}")
    elif state is MeasurementState.MEASURED:
        print(f"{signal}: measured")
    else:
        print(f"{signal}: {state.value}")
```

### The three states, and the honest ambiguity in the third

| State | Meaning |
|---|---|
| `MEASURED` | measured; a value is published |
| `NOT_MEASURED` | attempted and failed; **a named cause is always present** |
| `NOT_ATTEMPTED_OR_GATED` | either never attempted, or gated by tier |

The third name is deliberately ambiguous because **the response does not
let you tell those two apart**. A tidier-looking name would have implied
a distinction the data does not support.

### Every unmeasured signal names its cause

Causes you will encounter, and what they mean:

| Cause | Meaning |
|---|---|
| `*_service_unavailable` | the evaluator could not be reached — **or timed out**; see below |
| `*_malformed_response` | the evaluator replied with something unparseable |
| `*_no_input_text` | no text was supplied for that signal to be measured on |
| `*_empty_verdict`, `*_unparsed_verdict` | the judge answered, but not usefully |
| `*_no_score_key`, `*_no_instability_key` | the expected key was missing from the verdict |

**A timeout and an unreachable service report the same cause.** The
backend collapses both into `*_service_unavailable`, so you cannot tell a
slow evaluator from a dead one. This is tracked internally and is not
something the SDK can resolve. If you see a rising rate of that cause
under load, suspect timeouts rather than an outage.

### Note on `measurement_degraded`

If you have seen that term in any document or conversation: **it does not
exist in the API.** The vocabulary is `measured` / `not_measured` /
`not_attempted`, and `decision_basis`. Do not key logic off a field by
that name — there isn't one.

### What to do with a partial result

| Do | Do not |
|---|---|
| Record it as a partial measurement, with its cause | Treat a withheld aggregate as a passing score |
| Keep the missing-signal names | Substitute a default, a zero, or the previous value |
| Decide for yourself whether to retry later | Retry immediately inside the same request (the call is not idempotent) |
| Count partials in your rate of successful measurement | Silently drop them from your statistics |

A partial measurement is **not a failed call**. It is a successful call
whose answer is "this much could be measured, and here is why not more".
Dropping partials from your statistics will make your measurement
coverage look better than it is.

---

## 6. Preserve the evidence

A measurement you cannot attribute to a version, an instance and a moment
is not reusable. Store the following with **every** result you intend to
keep or cite.

### Minimum record

| What | Where to get it |
|---|---|
| Complete raw response | `result.raw` — the unmodified payload |
| Request id | `result.request_id` |
| Measurement version | `result.audit.measurement_version` |
| Decision + basis | `result.governance.decision`, `.decision_basis` |
| Withholding state | `result.aggregates_publishable`, `result.missing_required_signals` |
| Parse warnings | `result.parse_warnings` (store even when empty — "empty" is a fact) |
| SDK version | `neomundi.__version__` |
| Client's contract reference | `neomundi.API_CONTRACT` |
| Your own timestamp and environment label | your side |

```python
import json, neomundi

record = {
    "raw": result.raw,
    "request_id": result.request_id,
    "measurement_version": result.audit.measurement_version,
    "decision": result.governance.decision,
    "decision_basis": result.governance.decision_basis,
    "aggregates_publishable": result.aggregates_publishable,
    "missing_required_signals": result.missing_required_signals,
    "parse_warnings": [
        {"path": w.path, "expected": w.expected,
         "received_type": w.received_type, "received_repr": w.received_repr}
        for w in result.parse_warnings
    ],
    "sdk_version": neomundi.__version__,
    "sdk_contract": neomundi.API_CONTRACT,
    "observed_at": your_timestamp,
    "environment": "pilot-test",
}
```

`result.to_dict()` round-trips losslessly: the payload you store is the
payload the server sent.

### Why `measurement_version` matters most

If `result.audit.measurement_version` differs from
`API_CONTRACT["measurement_version"]`, your results are **not comparable**
with a series produced under the expected version, and fields may have
changed meaning. Check it on your first call and alert on change:

```python
expected = neomundi.API_CONTRACT["measurement_version"]
actual = result.audit.measurement_version
if actual != expected:
    log.error("measurement version drift: server=%s client=%s", actual, expected)
```

**There is no frozen OpenAPI specification server-side**
(`openapi_frozen: False`), so the named commit and this version string are
the only things you can point at to say what a measurement corresponds
to. Do not discard them.

### Minimum verification against your own deployment

Before you build on it, replay a handful of calls and check:

1. `parse_warnings` is empty on every one;
2. `result.audit.measurement_version` equals `3.3.0`;
3. no root field in `result.raw` is unknown to this SDK version;
4. a deliberately incomplete call (omit `llm_response`) produces
   `decision_basis == "no_check_attempted"` and no fabricated aggregate.

If 1, 2 or 3 fails, stop and report (§7) before collecting data. The SDK
is the detector here — that is the point of its non-coercive parsing.

### Do not store this

- your API key, in any form, in any record;
- end-user personal data in `metadata` that you would not want in a
  measurement archive.

The API responses themselves carried **no secret material** in the
validation campaign: zero fields required redaction.

---

## 7. Report an anomaly

### What is worth reporting

| Observation | Report it |
|---|---|
| A non-empty `parse_warnings` | **Yes — highest value.** It means the contract drifted. |
| An unknown root field in `result.raw` | **Yes.** The backend evolved past this SDK version. |
| `measurement_version` other than `3.3.0` | **Yes.** |
| An aggregate that is `null` **without** any declaration | **Yes.** That invariant should always hold. |
| A `TypeError` or `AttributeError` from inside the SDK | **Yes.** `require()` exists so you never get an opaque one. |
| `decision_basis` absent or outside the three known values | **Yes.** |
| Two identical REST calls producing different decisions | **Yes**, with both raw payloads. |
| A documented limitation behaving as documented | No — check `KNOWN_LIMITATIONS.md` first. |

### What to include

1. **The complete raw payload** (`result.raw`), with your own content
   removed if needed — but keep the measurement fields intact;
2. `result.request_id`;
3. `neomundi.__version__` and `neomundi.API_CONTRACT`;
4. the exact call you made, **with the key removed**;
5. what you expected and what you observed;
6. whether it reproduces, and how often.

**Never include your API key in a report**, not even partially. A prefix
plus a few characters is still a disclosure. The SDK masks it in its own
output; copy-pasted shell history does not.

### How to report

Open an issue on this private repository, or use the channel your
NeoMundi contact gave you. Follow whichever your contact specified — do
not post measurement payloads to a public tracker.

### One framing worth keeping

A discrepancy between what this SDK expects and what your server emits
is an **audit finding**, not necessarily a defect in either. Three
backend defects were found exactly this way during validation. Reporting
them is more useful than working around them, and a workaround in your
code hides the signal from everyone else.

---

## 8. The known-limitations notice

**[`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) is required reading
before you communicate any figure from this SDK.** It contains:

| Section | Contents |
|---|---|
| §1 | SDK status, and the exact test scopes behind it |
| §2 | What is verified **by execution** versus **by suite** — and what is not verified at all |
| §3 | **BL-001, BL-002, BL-003** — the three open backend defects, each with status, scope, severity, reproduction conditions, cause, and guidance |
| §4 | SL-001 … SL-005 — limitations of this client itself |
| §5 | Developer guidance |
| §6 | Version compatibility, and the minimum check against your deployment |
| §7 | The lifecycle of a known limitation, and the status vocabulary |

Related documents:

| Document | Language | Contents |
|---|---|---|
| [`README.md`](README.md) | English | API surface, installation, full reference |
| [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) | English | **the register of what is and is not known to work** |
| [`docs/LIMITES.md`](docs/LIMITES.md) | French | methodological limits inherited from the backend — what the instrument measures and does not measure |
| [`docs/CONTRAT_API.md`](docs/CONTRAT_API.md) | French | the response contract, field by field |

### The three open defects in one line each

| | Summary | Does it affect you? |
|---|---|---|
| **BL-001** | TRIAL account/key status inconsistency | **Possibly your first call.** A trial-tier account in the canonical state receives HTTP 402 claiming the quota is exhausted when it is not, and its keys are suspended. Subsequent calls return 401. If this happens, your key is not at fault — report it (§7). |
| **BL-002** | SSE governance decisions depend on network chunking | **Not through this SDK** — v0.1 does not implement SSE. It matters if you call the streaming endpoint directly. |
| **BL-003** | `delta_g` is published even when the aggregate is withheld | **Yes, if you read `delta_g`.** Check `aggregates_publishable` before interpreting it. |

None of these is worked around in the client. The SDK reports what the
server says.

---

## Status, stated plainly

This SDK is at **v0.1.0 — Experimental / Pilot Evaluation**.

**What has been verified.** 328 tests pass locally against fixtures that
include 11 responses captured from a running instance built from backend
commit `68d6057`; 206 pass with 12 skipped in CI, where captured fixtures
are absent by design. The capture campaign produced zero type
discrepancies and zero unmodelled fields, at `measurement_version 3.3.0`,
exercising all three values of `decision_basis`.

**What has not.** No hosted or shared deployment has been exercised. No
behaviour under load has been characterised. The variance of the
factuality judge at constant input has never been measured, which means
**no difference between two `stability_score` values can presently be
called significant**. And no pilot has yet installed or validated this
SDK — if you are reading this, you may be the first; that has not
happened yet and is not claimed.

This is not production-validated software and it is not described as
such. It is an honest experimental client for a measurement instrument
whose known defects are written down rather than hidden.
