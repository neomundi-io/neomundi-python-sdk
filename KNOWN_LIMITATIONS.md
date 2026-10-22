# Known Limitations — NeoMundi Python SDK v0.1.0

**Status: v0.1.0 — Experimental / Pilot Evaluation**

Last updated: 2026-10-22
Audited backend reference: commit `68d6057cf620e430e6488da3cfcec9c471c75ed6`, measurement version `3.3.0`
REST surface additionally verified against measurement version **`3.3.1`** (deployed commit `aeff13c`) — see §6

This document is for developers evaluating the SDK in a pilot context. It
states what works, what was verified and how, and which backend defects
were observed. Nothing here is softened: a measurement instrument that
hides its limits cannot be trusted with the measurements it reports.

> **Reading rule.** Where this document says *observed*, a value was
> recorded from a running instance and the conditions are stated. Where it
> says *derived from code*, the statement comes from reading the backend
> source at the commit above. The two are never mixed.

---

## 1. SDK status

| | |
|---|---|
Version | `0.1.0` |
Maturity | **Experimental.** Suitable for pilot evaluation, not for production reliance. |
Scope | **REST only** — `POST /v1/govern` (post-call mode) |
Runtime dependency | `httpx` only |
Python | ≥ 3.9 (verified on 3.9, 3.11, 3.12, 3.13 in CI) |
Distribution | **Not on PyPI.** Install from this private repository. |
Licence | **Not settled** — see `LICENSE_NOTICE.md` |

### What "locally validated" means, precisely

Two distinct test scopes exist, and conflating them would overstate what
has been verified.

| Scope | Count | What it establishes |
|---|---|---|
**Reference suite** (what CI runs) | **225 passed, 12 skipped** | the SDK behaves correctly against payloads **derived from reading** the backend contract, and against the sanitised `3.3.1` production payload shipped in `tests/fixtures/production_331/` |
**Local suite** (reference + captured payloads) | **347 passed** | the same, **plus** that the modelled contract matches what a running instance actually emitted |

The 12 skips are the `3.3.0` captured-payload tests. Those captures are
execution data and are **excluded from this repository**
(`tests/fixtures/captured/` is in `.gitignore`), so those tests skip
wherever the directory is absent — including CI. They are not optional
checks that were turned off; they are checks that require data this
repository deliberately does not carry.

The `3.3.1` payload is the exception, and deliberately so: it carries no
prompt, no response text and no evaluator identity, so it could be
sanitised and shipped. What was replaced is listed field by field in its
`_fixture_redacted` key.

### Deployment compatibility — the central caveat

The SDK's models were derived from the backend's request and response
models **at one named commit**. No frozen OpenAPI specification exists
server-side, and `/openapi.json` is disabled in production builds.

Compatibility was verified against **a local instance built from that
commit**, and the REST contract was additionally verified against
measurement version **`3.3.1`** by source comparison and by replaying a
real production response (§6). It has **not** been verified by this SDK
**calling** any hosted deployment. A deployment serving a
`measurement_version` outside the verified list, or carrying fields added
since, may behave differently.

```python
import neomundi
result = client.govern(...)

served = result.audit.measurement_version

if served not in neomundi.API_CONTRACT["verified_measurement_versions"]:
    # Unverified contract: fields may have changed meaning. Stop here.
    ...
elif served != neomundi.API_CONTRACT["measurement_version"]:
    # Parsing is safe, but the series is not comparable with one produced
    # under a different measurement version. Record `served` alongside
    # every observation.
    ...
```

**The two checks answer different questions, and collapsing them is the
mistake this split exists to prevent.** The first asks *can this client
read the response correctly* — a transport question. The second asks *may
these two numbers sit in the same series* — a scientific one. `3.3.1`
passes the first and fails the second against a `3.3.0` series.

---

## 2. Supported functionality

### Verified by execution against a running instance

A campaign of ten REST calls was run against a local instance built from
the reference commit, at tier `TIER_02`, with all three evaluators live
(Llama Guard 3 1B, nomic-embed-text, Llama 3.2 3B on a local Ollama).

| Capability | Result |
|---|---|
`POST /v1/govern`, request construction and response parsing | 10/10 calls parsed |
**Zero type discrepancies** (`parse_warnings`) | 0 across all captured payloads |
**Zero unmodelled fields** (`unknown_fields`) | 0 across all captured payloads |
`measurement_version` served | `3.3.0`, matching the SDK's declared contract |
Round-trip fidelity (`to_dict()` returns the payload unchanged) | verified on every captured payload |
Root aliases agree with their blocks (`g_score`/`g_final`) | verified on every captured payload |
Coverage is re-derivable from the published counters | verified on every captured payload |
Three decision bases exercised | `measured_thresholds`, `incomplete_measurement`, `no_check_attempted` |
**Degraded path**: all three evaluators unreachable | aggregates `null`, decision `FLAG`, basis `incomplete_measurement`, coverage `0/3`, each cause named (`moderation_service_unavailable`, `coherence_service_unavailable`, `hallucination_judge_unavailable`) |
Partial coverage | observed at `2/3` (missing coherence) and `0/3` |
No secrets in responses | the redaction pass found **nothing to redact** in any captured payload |

### Verified by replaying a production response served under `3.3.1`

One response really emitted by the production deployment on **2026-10-21**
under `measurement_version 3.3.1` was replayed through the client over a
simulated transport on **2026-10-22**. A sanitised copy ships as
`tests/fixtures/production_331/rest_complete_allow.json` and is exercised
by `tests/test_measurement_version_331.py`.

| Checked on the `3.3.1` payload | Result |
|---|---|
`parse_warnings` | **0** |
`unknown_fields` — a root field `3.3.1` would have added | **0** |
Round-trip (`to_dict()` returns the payload unchanged) | exact |
Root aliases agree with their blocks (`g_score`, `g_final`) | yes |
Coverage re-derivable from the published counters (`3/3 → 1.0`) | yes |
Four required blocks present | yes |
Twelve per-signal provenance fields exposed, `null` included | yes |
`trajectory_points` and `provider` still `None` on REST | yes |
`quality.stability_score` + `metrics.stability_score` = 1.0 — the inverted homonyms still coexist | yes |
`baseline.delta_E` still equals `reference − observed` (the implementation, not the description) | yes |
`decision` / `decision_basis` | `ALLOW` / `measured_thresholds` |

**This is a replay, not a live call.** The SDK did not reach the hosted
service: the payload was served to it by `httpx.MockTransport`. What it
establishes is that the contract this client models is the contract the
production deployment emitted — not that an end-to-end call succeeds.
See §6 for what remains missing and why.

**One finding worth carrying into any comparison.** On that response, the
three configuration fingerprints (`prompt_template_hash`,
`inference_config_hash`, `config_fingerprint`) were populated **only for
the two signals produced by the factuality judge**. `stability_score`,
`coherence_score` and `semantic_risk` carried `status: "measured"` with
all three fingerprints `null`. Two observations therefore cannot be shown
to share an evaluator configuration on those three signals — the data to
check it is not published. The SDK exposes the `null`s; it invents
nothing. A test holds this observation so that a change to it is noticed.

### Verified by the test suite, without a running instance

| Capability | Where |
|---|---|
`X-API-Key` authentication; key **format** validated before any network call | `test_client.py` |
Nine error families: 401, 402, 413, 422, 429, 5xx, timeout, network, invalid response | `test_errors.py` (39 tests) |
**No automatic retry**, on any status; a timeout is never retried even with an explicit policy | `test_retry.py` (26 tests) |
`null` preserved; `None` never substituted by `0.0`; `None` distinct from `[]` | `test_models.py` |
Unknown fields preserved in `raw` and listed, never fatal | `test_models.py` |
No numeric default anywhere in the sources (AST-checked, and the guard is itself tested) | `test_contract_drift.py` |
No backend import, no undeclared dependency, no embedded threshold | `test_contract_drift.py` |
No key in `repr`, exception messages, logs, request body or URL; repository-wide key sweep | `test_no_secret_leak.py` (11 tests) |
The three offline examples run and exit 0 | `test_examples.py` |

### Not verified

- **any call made by this SDK to a hosted deployment** — no end-to-end
  call has ever been executed, under `3.3.0` or `3.3.1`. The credential
  needed for one was not available to the verification session;
- consequently: authentication, error statuses, timeouts, rate limiting
  and quota behaviour **against production** — all nine error families
  are exercised against a simulated transport only;
- behaviour under concurrency or sustained load;
- behaviour against a measurement version outside
  `API_CONTRACT["verified_measurement_versions"]`;
- the `3.3.1` **incomplete-measurement** path: the single `3.3.1`
  response available is a complete measurement, so the withheld-aggregate
  behaviour has been re-verified at `3.3.1` **by source identity only**,
  not by observation;
- repeat-call variance of the factuality judge (see SL-005).

---

## 3. Known backend limitations

These are **backend** defects observed or derived at the reference commit.
The SDK does not work around them — it surfaces them. Working around a
measurement defect in a client would make the defect invisible without
making it go away.

> **All three were re-read against the deployed commit `aeff13c` /
> `3.3.1` on 2026-10-22.** The method was source comparison between
> `68d6057` and `aeff13c`, plus the replayed production response. **A
> version number changing is not evidence that a defect closed**, and no
> entry below was weakened on that basis: BL-001 and BL-003 live in files
> that are byte-identical between the two commits, so they stand
> unchanged. BL-002 is the one entry that moves, because an actual
> correction was shipped — and it closes one named class, not the entry.

---

### BL-001 — TRIAL account and key status inconsistency

| | |
|---|---|
**Status** | Open — observed |
**Affected version** | backend commit `68d6057`; measurement version `3.3.0`. **Re-read at `aeff13c` / `3.3.1` on 2026-10-22: unchanged, still open** |
**Scope** | accounts whose `tier` is `TRIAL` **and** whose `status` is `ACTIVE` |
**Severity for a pilot** | **High** — blocks use of a trial key |
**SDK impact** | none; the SDK reports the server's responses faithfully |

> **Re-read at `3.3.1`.** `app/auth/api_key.py` is **byte-identical**
> between `68d6057` and the deployed `aeff13c`. The quota debit still
> carries `AND status = 'TRIAL'`, and the statement that suspends the
> account's keys still carries no equivalent guard. The defect therefore
> stands at `3.3.1`, established by **source comparison** — the account
> journey was not re-run, and no trial key was available to re-observe it.

**What was observed.** On a local instance built from the reference
commit, a freshly provisioned trial account was taken through the
documented journey (registration, e-mail verification, administrator
approval). The resulting key was accepted by an authenticated non-metered
endpoint. The **first** `POST /v1/govern` call then returned
**HTTP 402** with a payload stating the trial quota was exhausted, and
**every subsequent call returned HTTP 401**.

Database state immediately afterwards:

| Field | Value |
|---|---|
`accounts.status` | `ACTIVE` |
`accounts.tier` | `TRIAL` |
`accounts.trial_requests_remaining` | `500` |
`accounts.trial_requests_total` | `500` |
`api_keys.status` | **`SUSPENDED`** |

The quota was **not** exhausted — none of it had been consumed — yet the
key was permanently suspended.

**Conditions reproduced.** One account, one local instance, the documented
provisioning journey. **Not generalised**: this was not tested against any
hosted deployment, nor against accounts provisioned by other means, nor
against accounts whose `status` is something other than `ACTIVE`. Whether
hosted deployments carry the same account state is unverified.

**Technical cause (confirmed by reading the source).** The quota debit is
guarded by a condition on `accounts.status`:

```sql
UPDATE accounts
SET trial_requests_remaining = trial_requests_remaining - 1
WHERE id = :account_id
  AND status = 'TRIAL'                 -- the condition in question
  AND trial_requests_remaining > 0
RETURNING trial_requests_remaining
```

A database migration included at the reference commit records that trial
detection was moved from `status` to `tier`, stating that `status`
describes whether an account is running and that *"trial detection
everywhere now keys off `tier=='TRIAL'`"*. The portal consequently writes
`status='ACTIVE'`, `tier='TRIAL'`. The `UPDATE` above therefore matches no
row; an empty result is interpreted as an exhausted quota; the suspension
branch then runs, and the statement that suspends the keys carries no
equivalent guard, so the keys are suspended while the account is not.

**Workaround for a pilot.** None available from the client side. A pilot
needs a key on an account the server's quota path accepts — in practice a
paid tier with a funded wallet, or an account whose state the operator has
adjusted. **Request this from your NeoMundi contact rather than working
around it.**

**Internal tracking.** Backend correction plan, item BL-001.

---

### BL-002 — SSE chunking-dependent governance decision

| | |
|---|---|
**Status** | **Partly corrected in `3.3.1` — `Fixed — pending verification` for the named class; the entry stays open for the residue** |
**Affected version** | observed at backend commit `68d6057` / `3.3.0`. **Corrected at `aeff13c` / `3.3.1`, for one class only** |
**Scope** | `POST /v1/govern/stream` only. **REST is unaffected.** |
**Severity for a pilot** | **High for streaming**, none for this SDK |
**SDK impact** | **none — the SDK v0.1 does not implement SSE** |

> **The Python SDK v0.1 does not cover SSE streaming and does not correct
> this defect.** It is documented here because a pilot may reach the
> streaming route directly, and because it is the reason streaming was
> excluded from this version rather than merely deferred.

#### What `3.3.1` changed, and what it did not

**`3.3.1` exists for this defect, and for nothing else.** Between
`68d6057` and the deployed `aeff13c`, one application file changed —
`app/api/v1/streaming.py` — plus the version string in `app/config.py`.
The trajectory rules R1/R2/R3 now read **only** the trajectory points
whose coherence *and* risk were really measured, plus the final point.
The published trajectory itself (`series`, `profile`, `total_variation`,
`min_stability`, `max_stability`) is unchanged, so no stored series is
reinterpreted.

Measured in the backend's own regression suite, on one text with one set
of judge verdicts and only the slicing varying:

| Fragments | Decision before | Decision after |
|---:|---|---|
| 1 | `ALLOW` | `ALLOW` |
| 10 | `ALLOW` | `ALLOW` |
| 20 | **`FLAG`** | `ALLOW` |
| 50 | **`FLAG`** | `ALLOW` |
| 300 | **`FLAG`** | `ALLOW` |

**What is still true at `3.3.1`, and the backend locks it with tests so
that it stays visible:**

- **ΔG is still not invariant to the slicing.** The published `series`,
  `profile` and `total_variation` still vary with fragmentation; a
  backend test *requires* that they do, so the residue stays measured
  rather than presumed gone;
- **a stream sliced too coarsely has no measured trajectory at all** —
  with default intervals the first window carrying both signals arrives
  at fragment 120. Below that, no rule can fire, so whether a drift is
  *observable* still depends on the framing;
- the asynchronous race between evaluators subsists; the correction
  discards windows whose signals had not landed, it does not make their
  arrival deterministic;
- four decision thresholds remain hard-coded, and two of them appear in
  the production environment template **without being read by any line of
  code**.

**Consequences for a pilot using SSE directly — unchanged.** Do not
compare `delta_g.profile` or `delta_g.total_variation` across providers,
clients or versions. Prefer REST for anything that must be reproducible.

**Evidence, and its limits.** The above is **derived from the backend
source and its regression suite at `aeff13c`** — read on 2026-10-22. No
SSE stream has been observed on the production deployment under `3.3.1`,
by this session or any other. The correction is therefore
`Fixed — pending verification`, and the entry as a whole stays open.

**What was observed.** Four streams were run against a local instance,
each with a correct answer, each with the factuality judge reporting
`factual_hallucination_score = 0.0` — that is, no hallucination measured —
and final stability between 0.86 and 0.94.

| Content fragments | ΔG profile | Total variation | **Decision** |
|---:|---|---:|---|
1 | `FLAT` | 0.0 | **ALLOW** |
1 | `FLAT` | 0.0 | **ALLOW** |
10 | `FLAT` | 0.0 | **ALLOW** |
300 | `DROP` | 0.158 | **FLAG** |

The measured quality was equivalent across all four. The decision was
not.

**Mechanism (observed).** Intermediate governance windows fire every
*N* **network fragments**, not every *N* tokens. Each window computes a
provisional stability from whichever rolling signals have reported by that
point; the factuality judge runs only at end of stream, so intermediate
windows use a neutral default for it. The published trajectory of one
300-fragment stream:

```
fragment  20 → stability 1.0000   delta 0.0000
fragment  40 → stability 1.0000   delta 0.0000
fragment  60 → stability 0.8896   delta −0.1104   ← coherence reports here
fragment  80 → stability 0.8896   delta  0.0000
fragment 100 → stability 0.8867   delta −0.0029
```

The "drop" is the coherence measurement **arriving**, not a degradation
during generation. A profile rule then reads that drop as instability and
escalates the decision.

A stream short enough that no intermediate window fires produces a
single-point trajectory, classified `FLAT`, and no escalation occurs.

**Two further observations on the same responses.** On a flagged stream,
the published `reasons` array contained both
*"all metrics within bounds"* and *"possible hallucination or drift in
progress"*, while the judge had measured no hallucination at all; and
`decision_basis` was `measured_thresholds` — the field that exists to
explain why a decision was taken classified this escalation as resting on
measured thresholds.

**Guidance for a pilot using SSE directly.**

- Do not compare `delta_g.profile`, `delta_g.total_variation` or the
  streaming `decision` across providers, SDK versions or client libraries:
  fragmentation differs between them.
- Treat intermediate `governance_check` and `stability_check` events as
  **provisional** — the backend marks them `provisional: true` and that
  flag is meaningful.
- Prefer the REST route for anything that must be reproducible.

**Internal tracking.** Backend correction plan, item BL-002.

---

### BL-003 — `delta_g` published while the aggregate is withheld

| | |
|---|---|
**Status** | Open — observed. **Contract interpretation under review.** |
**Affected version** | backend commit `68d6057`; measurement version `3.3.0`. **Re-read at `aeff13c` / `3.3.1` on 2026-10-22: unchanged, still open** |
**Scope** | `POST /v1/govern`, when a required signal was not measured |
**Severity for a pilot** | **Medium** — a misread field, not a corrupted measurement |
**SDK impact** | none; the SDK exposes the raw value and documents the caveat |

> **Re-read at `3.3.1`.** `app/api/v1/governance.py` and everything under
> `app/models/` are **byte-identical** between `68d6057` and `aeff13c`:
> the code that publishes `delta_g` and the code that withholds the
> aggregates are the same code. The limitation therefore stands,
> established by **source comparison**. It was **not** re-observed: the
> only `3.3.1` response available is a complete measurement, so it
> exhibits neither the withheld aggregate nor the hazard. A `3.3.1`
> response with an unmeasured required signal would be needed to
> re-observe it, and none exists.

**What was observed.** On responses where a required signal could not be
measured, the server correctly withheld the aggregates — `g_score`,
`quality.stability_score` and `g_final` were all `null`, the decision was
`FLAG`, and `decision_basis` was `incomplete_measurement` — while
`delta_g` carried a number. Two of ten REST captures showed this, as did
the fully degraded capture (`g_score: null`, `delta_g: −0.56199`).

**What the contract says, and why this is stated carefully.** `delta_g` is
documented as the variation in `G` since the account's previous request.
It is a **separate field** from the aggregates, and the withholding rule
that the backend documents applies explicitly to `g_score`,
`quality.stability_score` and `g_final` — `delta_g` is not named in it.
On that reading, a populated `delta_g` beside a null `g_score` is the
contract behaving as written rather than a violation of it.

**What is nonetheless a real hazard, independent of that reading.** The
value is computed from the current request's internal `G`, which in this
case is precisely the figure the withholding rule exists to suppress —
and the reference stored for the *next* request is that same unpublished
figure. A series of `delta_g` values spanning a degraded request is
therefore not interpretable, whatever the contract intends. That is why
this is listed rather than dismissed.

**Guidance — this is the part that matters for your integration.**

Respect statuses, coverage and the aggregate publication rule rather than
reading numbers directly:

```python
if result.measurement_incomplete:
    # Aggregates are withheld. Do not read delta_g as a quality signal
    # for this observation, and do not chain it with neighbouring
    # observations.
    result.missing_required_signals     # which signals were not measured
    result.measurement.coverage         # how much of the measurement happened
    result.governance.decision_basis    # 'incomplete_measurement'
```

And in general: **do not read `delta_g` as a drift measurement.** It
compares one request to whatever the account's previous request happened
to be, whatever question that request asked, within a one-hour window.
Two unrelated tasks from the same account produce a `delta_g` that
describes the change of task, not a change in the system.

**Internal tracking.** Backend correction plan, item BL-003.

---

## 4. SDK-specific limitations

These are deliberate scope decisions for v0.1, not defects.

| ID | Not included | Why |
|---|---|---|
**SL-001** | **SSE streaming** | not deferred for convenience: see BL-002. **Still gated at `3.3.1`, and the gate has moved rather than opened.** `3.3.1` makes the published *decision* invariant to the slicing for a given observation; it leaves the published *trajectory* — `series`, `profile`, `total_variation` — varying with it, and a backend test requires that it still does. A streaming client would therefore carry a reproducible verdict alongside a non-reproducible trajectory, which is a subtler trap than the one that was closed, not an absence of one. |
**SL-002** | **TypeScript / JavaScript SDK** | requires a frozen OpenAPI specification, which does not exist server-side |
**SL-003** | **Longitudinal processing** — series, trends, drift | comparing two observations requires conditions the SDK cannot verify for you (same measurement version, same coverage, same evaluator models, same β weights, same route). Deciding that a series is valid is a methodological judgement, not a transport concern. |
**SL-004** | **Automatic score interpretation** — no `is_safe()`, no quality level, no embedded threshold | thresholds are server-side configuration and are not publicly calibrated. A client-side threshold would be an invention. Verified absent by AST analysis of the sources. |
**SL-005** | **Correction of backend defects** | the SDK surfaces BL-001 to BL-003; it does not compensate for them. Related: the factuality judge runs at a non-zero sampling temperature, so two identical calls can return different scores. **That spread has not been measured.** Until it is, no difference between two observations is interpretable. |
| | Also absent | asynchronous client, other REST routes (replay, exports, RGC), caching, pagination, PDF certificate verification |

---

## 5. Developer guidance

### 5.1 Check measurement coverage before reading any score

This is the first thing to read in a response, not the last.

```python
result = client.govern(..., llm_response=text, llm_prompt=prompt)

if result.measurement_incomplete:
    print("incomplete:", result.missing_required_signals)
    # The FLAG you are about to see is NOT a statement about the content.

m = result.measurement
m.status            # 'complete' | 'partial' | 'not_attempted'
m.checks_attempted  # checks actually launched
m.checks_succeeded  # of those, how many produced a usable result
m.coverage          # the ratio — and the value of `confidence`
```

**`coverage == 1.0` does not mean "fully measured".** It is `1.0` when
nothing was attempted. Always read it together with `status`:

```python
if m.status == "not_attempted":
    # No server-side check ran. coverage 1.0 means "nothing was expected",
    # not "everything was measured".
    ...
```

`coverage` is re-derivable, so you can verify it rather than trust it:

```python
assert round(m.checks_succeeded / m.checks_attempted, 6) == m.coverage
```

### 5.2 Handling `null`

**Never substitute a number for a `null`.** The SDK contains no numeric
default anywhere in its sources, and a test enforces that. Do not
reintroduce one in your integration.

```python
# For display — never raises.
result.format_score("g_score", nd=4)              # '0.4920' | 'non mesuré'
result.format_score("g_score", when_none="n/a")

# For a computation — raises an exception that names the cause.
from neomundi import AggregateWithheldError
try:
    value = result.require("g_score")
except AggregateWithheldError as exc:
    exc.missing_required_signals
    exc.decision_basis

# What not to do:
f"{result.g_score:.2f}"    # TypeError as soon as the aggregate is withheld
```

A `null` has **three** possible meanings. Distinguish them:

| Meaning | How to recognise it |
|---|---|
**not measured** — the check ran, produced nothing | the signal is in `unmeasured_signals`, with its cause |
**not sold at your tier** | the signal is in neither signal list, and `measurement.status` is `complete` |
**not applicable on this route** | `trajectory_points` and `provider` are always `None` on REST — "not applicable here", not "zero" |

### 5.3 "Measured as zero" is not "not measured"

This distinction is the product. In every failure mode, the backend's
instruments return the **most reassuring value they can** — risk `0.0`,
coherence `1.0`, factuality `0.0`. A signal's validity is therefore
**never** readable from its numeric value.

```python
# A measured zero:
result.quality.semantic_risk            # 0.0  -> measured, nothing detected
result.is_measured("semantic_risk")     # True

# An absence:
result.quality.factual_hallucination_score   # None -> not measured
result.unmeasured_reason("factual_hallucination_score")
# 'hallucination_judge_unavailable'

# Four states, and the SDK does not collapse them:
result.measurement_state("coherence_score")
#   MeasurementState.MEASURED
#   MeasurementState.NOT_MEASURED            -> a cause is available
#   MeasurementState.NOT_ATTEMPTED_OR_GATED  -> not launched OR gated by tier
#   MeasurementState.UNKNOWN                 -> the response does not say
```

`NOT_ATTEMPTED_OR_GATED` is **deliberately ambiguous**: the server does not
distinguish "never launched" from "withheld by commercial tier" on the
wire. The SDK does not invent that distinction. Read
`measurement.status` and `measurement.checks_attempted` to narrow it.

One observed consequence worth knowing: when no check is launched at all,
the response carried `quality.coherence_score = 1.0` as a value while the
factuality fields were `null`, and the aggregates were published at their
maximum. A `1.0` coherence is therefore not always an observation.

### 5.4 Keep the audit and version metadata

Keep these with every observation you intend to use as evidence or compare
later. Without them an observation is a number without provenance.

```python
result.request_id                      # the observation's identity
result.timestamp_raw                   # the server's instant, as sent
result.audit.measurement_version       # the only version with scientific meaning
result.audit.normalizer_version
result.measurement.coverage            # how much of the measurement happened
result.evaluators                      # per-signal instrument, model, cause

# The three fingerprints are the only way to verify that two observations
# were produced under the same evaluator configuration — `measurement_version`
# does not cover evaluator identity.
ev = result.evaluator_of("factual_hallucination_score")
ev["model_used"], ev["config_fingerprint"], ev["prompt_template_hash"]

result.esi.betas if result.esi else None   # the weights actually applied
result.to_dict()                           # the full raw payload
```

Two results are comparable only under **all** of: same
`measurement_version`, same coverage, same evaluator models, same β
weights, same route. The SDK gives you what you need to check that; it
does not check it for you (SL-003).

### 5.5 A `FLAG` is not evidence of hallucination

A `FLAG` is **advisory**. NeoMundi grants, refuses, suspends and modifies
no execution, and the signed contract format states this as a structural
invariant.

Read `decision_basis` before acting on a decision:

| Value | What the FLAG means |
|---|---|
`measured_thresholds` | a measured value crossed a configured threshold. The FLAG is about the content. |
`incomplete_measurement` | a required signal could not be measured. **The FLAG is not about the content** — it says the measurement did not complete. |
`no_check_attempted` | no server-side check ran. Nothing here was measured by the service. |
`None` | the observation predates this field. **Do not assume `measured_thresholds`.** |

Two further cautions, both grounded in observations above:

- the factuality judge is a language model scoring a text with no external
  source, at a non-zero temperature. A high score is its opinion, traceable
  and reproducible to the configuration — not a verified fact;
- `decision_basis` was observed reporting `measured_thresholds` on a
  streaming escalation that came from the ΔG profile rule (BL-002). On the
  streaming route, read `reasons` as well as `decision_basis`.

### 5.6 Reporting a discrepancy

The SDK is built so that a contract discrepancy is **visible rather than
absorbed**. Two fields carry it:

```python
result.parse_warnings   # a field could not be read at the expected type
result.unknown_fields   # a root field this SDK version does not model
```

| What you see | What it means | What to do |
|---|---|---|
`parse_warnings` non-empty | the instance emits something other than what the modelled contract declares | **report it.** This is an audit finding, not a client bug. Do not widen the parsing to make it go away. |
`unknown_fields` non-empty | the backend has gained a field since the reference commit | report it; the SDK needs extending and its version incrementing |
`InvalidResponseError` on a 2xx | a required block is missing, or the body is not JSON | report it with the exception's `body` |
`measurement_version` **outside** `verified_measurement_versions` | you are talking to a contract this SDK has not been checked against | **report it before relying on anything**, parsing included |
`measurement_version` in the verified list but ≠ `measurement_version` | parsing is safe; the **series** is not comparable with one produced under the declared version | record it with every observation; no report needed |

When reporting, include: the `request_id`, `result.audit.measurement_version`,
the `parse_warnings` entries verbatim, the base URL's **environment**
(not its credentials), and the SDK version. **Never include your API key**,
and redact any response content you are not permitted to share.

Report through your NeoMundi technical contact. No public issue tracker is
offered for this SDK at v0.1.

---

## 6. Version compatibility

> **REST contract compatibility of `POST /v1/govern` with measurement
> version `3.3.1` is verified by local tests and by replaying a
> production capture. A direct call of the SDK against production has not
> been performed.**

| | |
|---|---|
**Audited reference** | backend commit `68d6057cf620e430e6488da3cfcec9c471c75ed6` |
**Measurement version of that reference** | `3.3.0` |
**Measurement versions whose REST surface is verified** | **`3.3.0` and `3.3.1`** |
**Normalizer version** | `1.0.0` — unchanged across both |
**Contract source** | the backend's request and response models at that commit |
**Frozen OpenAPI specification** | **none exists** — this is why a commit is named |

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

### Four version numbers, and they are not interchangeable

Confusing them is the most common way to reach a wrong conclusion about
this SDK, so they are named apart:

| | Value observed | Where it is read |
|---|---|---|
**Application build** | `3.0.0` | `GET /v1/health`, field `version` |
**Measurement version** | `3.3.1` | `result.audit.measurement_version` — **a response, and nowhere else** |
**Normalizer version** | `1.0.0` | `result.audit.normalizer_version` |
**RGC contract schema** | `0.1.0` | the signed contract, a route this SDK does not cover |

**`GET /v1/health` does not publish the measurement version.** Verified
again on 2026-10-22 against the production deployment: `HTTP 200`,
`version: 3.0.0`, `environment: production`, and no
`measurement_version` anywhere in the body. `/openapi.json`, `/docs`,
`/v1/version` and `/version` were all recorded as `404` on 2026-10-21.
**Establishing the measurement version therefore costs one metered
observation. There is no free way to read it.**

### Why `3.3.1` is in the verified list — the evidence, in full

Two pieces, both dated 2026-10-22, and **neither is a call made by this
SDK**.

**1. Source comparison, `68d6057` → `aeff13c` (the deployed commit).**
Seven files differ in total. Of the application code, exactly **two**:
`app/api/v1/streaming.py` and the version string in `app/config.py`. The
remaining five are documentation and tests. Specifically:

- **nothing under `app/models/`** — the declared source of this SDK's
  contract — changed;
- `app/api/v1/governance.py`, the REST route itself, did not change;
- `app/auth/`, `app/core/`, `app/rgc/` and `app/main.py` did not change;
- the backend's own 1 266-line golden file locking its measurement
  surface differs by **one line**: the version string. Every signal,
  coverage state, gated field and provenance entry in it is identical.

The backend states the consequence itself, and it is worth having
verbatim: under `3.3.0` and `3.3.1` results differ for the same input
**only** on a streaming observation left at `ALLOW` by the measured
signals that produced a `DROP` or `OSCILLATING` profile from unmeasured
points. *"Everywhere else — the whole REST path, every SSE observation
whose decision came from the measured signals, every aggregate, every
coverage status, every gated field — the two are identical."*

**2. Replay of a real `3.3.1` production response.** One response emitted
by the production deployment on 2026-10-21 was replayed through the
client: **0 `parse_warnings`, 0 unknown root fields**, exact round-trip,
aliases agreeing, coverage re-derivable. Details and the full check list
are in §2.

**A note on which process produced it.** The deployment's `uptime` read
on 2026-10-22 places the start of the running process at
`2026-10-20T21:16:45`, the same instant computed from an independent
reading on 2026-10-21. The process that produced the replayed response is
therefore **the process still serving today** — it has not been restarted
since. That removes one doubt. It does not create an end-to-end call.

### What the verified list does *not* mean

- it does **not** mean an end-to-end call has succeeded. **No call by
  this SDK to any hosted deployment has ever been made**, under either
  version. Authentication, error statuses, timeouts and quota behaviour
  against production remain unverified;
- it does **not** make two observations comparable across the two
  versions. Comparability is a separate question, answered below;
- it does **not** cover the streaming route, which this SDK does not
  implement and where the two versions genuinely differ.

### Minimum check before a pilot campaign

1. call `GET /v1/health` — unauthenticated, consumes no quota — and
   record the build version and the state of the three evaluators.
   **Do not read a measurement version from it; it does not carry one.**
   Note also that a `degraded` on `judge_factuality` is a known
   catalogue-probe artefact: the probe compares the *configured* model
   name against the provider's catalogue, so a model served under an
   alias reports `degraded` while measuring correctly. The replayed
   `3.3.1` response was produced by a deployment reporting exactly that,
   with the judge's own `status` reading `measured`;
2. make one `POST /v1/govern` call and record
   `result.audit.measurement_version`;
3. confirm it is in `API_CONTRACT["verified_measurement_versions"]`;
4. confirm `result.parse_warnings` and `result.unknown_fields` are both
   empty;
5. record `result.evaluator_of(...)["config_fingerprint"]` and confirm it
   does not change during the campaign — noting that on `3.3.1` only the
   factuality judge's two signals publish one at all (§2).

### Comparability — the rule, and where `3.3.1` sits in it

The backend documents its own rule, and it is worth repeating verbatim:
results under measurement versions `3.2.0` and `3.3.0` are **not**
comparable for the same input wherever the observation came from the
streaming path, a required signal went unmeasured, or the client is on an
entry tier. Any longitudinal study must sit entirely on one side of that
boundary.

For `3.3.0` against `3.3.1` the backend's statement is narrower, and
quoted above: on the REST path the two are identical. **Treat that as the
backend's claim about its own formula, not as a licence to mix series.**
The conservative practice holds and costs nothing: record
`result.audit.measurement_version` with every observation, and keep a
series on one side of the boundary. A measurement whose version is not
recorded cannot be rescued later.

---

## 7. Known limitations lifecycle

Each entry carries a stable identifier. Identifiers are never reused or
renumbered; a resolved entry keeps its identifier and changes status.

**Status vocabulary**

| Status | Meaning |
|---|---|
`Open — observed` | reproduced on a running instance; conditions stated |
`Open — derived from code` | established by reading the source; not yet reproduced |
`Under review` | the intended contract is being clarified before any fix |
`Fixed — pending verification` | corrected, not yet re-verified against an instance |
`Fixed — verified` | corrected **and** re-verified, with evidence referenced |
`By design` | not a defect; a documented scope decision |

### Register

| ID | Title | Status | Affected version | Scope | Internal plan |
|---|---|---|---|---|---|
**BL-001** | TRIAL account and key status inconsistency | `Open — observed` · **re-read at `3.3.1`, unchanged** | backend `68d6057` / `3.3.0`, **and `aeff13c` / `3.3.1`** | accounts with `tier=TRIAL` and `status=ACTIVE`, on a local instance | plan item BL-001 |
**BL-002** | SSE chunking-dependent governance decision | **one class `Fixed — pending verification` at `3.3.1`; entry stays `Open` for the residue** | observed at `68d6057` / `3.3.0`; corrected at `aeff13c` / `3.3.1` | `POST /v1/govern/stream` only; REST unaffected | plan item BL-002 |
**BL-003** | `delta_g` published while the aggregate is withheld | `Open — observed`, contract `Under review` · **re-read at `3.3.1`, unchanged** | backend `68d6057` / `3.3.0`, **and `aeff13c` / `3.3.1`** | `POST /v1/govern` when a required signal is unmeasured | plan item BL-003 |
**SL-001** | SSE streaming not implemented | `By design`, gated on BL-002 — **gate not lifted by `3.3.1`** | SDK `0.1.0` | SDK scope | — |
**SL-002** | No TypeScript SDK | `By design` | SDK `0.1.0` | SDK scope | — |
**SL-003** | No longitudinal processing | `By design` | SDK `0.1.0` | SDK scope | — |
**SL-004** | No automatic score interpretation | `By design` | SDK `0.1.0` | SDK scope | — |
**SL-005** | Backend defects not worked around; judge variance unmeasured | `By design` / `Open` | SDK `0.1.0`; backend `3.3.0` | SDK scope; measurement methodology | plan, additional risks |

**Internal plan.** Each `BL-*` entry maps to an item in an internal
backend correction plan holding reproduction steps, source locations,
candidate corrections, regression tests and acceptance criteria. That plan
is **not published in this repository** and is not distributed to pilots.
Its existence is recorded here so that a reader knows these items are
tracked rather than merely noted.

**Keeping this document honest.** An entry moves to `Fixed — verified`
only when a re-run against an instance demonstrates it, and the evidence
is referenced. No entry is removed, softened or silently reworded. If you
find a limitation that is not listed, that omission is itself worth
reporting (§5.6).
