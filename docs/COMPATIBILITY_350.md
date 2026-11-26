# Measurement version 3.5.0 — SDK V2 compatibility assessment (in progress)

**Status: PARTIALLY QUALIFIED; DO NOT add 3.5.0 to `verified_measurement_versions` yet.**

## Evidence from the controlled live run of 2026-11-13

The operator's **private** qualification report, stored locally under
`NEOMUNDI_PRIVATE/QUALIFICATION_SDK_V2_20261113/`, reports:
- Installed wheel built at commit `b453e972`, not imported from the source tree.
- One authenticated REST `POST /v1/govern`: successful, measured coverage 1.0 with five measured signals, zero parse warnings.
- One authenticated SSE `POST /v1/govern/stream`: successful; seven events, terminal done, verified assembly/integrity.
- Both paths reportedly served `measurement_version = 3.5.0`.
- REST reported four additional root fields: `contract_version`, `token_count_source`, `token_count_scope`, `token_count_unit`. The SDK retained them inside `raw` and enumerated them in `unknown_fields`.
- Ten existing response blocks were reported to match expected shape. The independent verification of every live field, schema hashes and authenticated backend revision is **not** part of this repository.

**Provenance boundary:** those live findings are from an operator-supplied private report; no raw live response, private secret or proof of complete deployed contract identity has been checked into GitHub. This document does **not** upgrade that report into an independently reproduced audit.

## What the new offline regression establishes

`tests/test_350_wire_extension_synthetic.py` changes a *sanitised historical 3.3.1 fixture* by inserting a synthetic 3.5.0 version value and four illustrative root fields.

It tests only that the SDK (a) preserves extra fields and values exactly; (b) exposes them as unknown; (c) preserves `null` versus numeric zero; (d) keeps the version mismatch visible. **It cannot establish their production types, normative semantics, or 3.5.0 compatibility.**

## Contract-source comparison (repository evidence, not deployed parity)

The named backend contract source was located at
`neomundi-io/Backend_plateforme_v2/govern-v3/app/contracts/schemas/`
and the matching public MCP schema copies at
`neomundi-io/neomundi-measurement-mcp/runtime/schemas/contracts/`.
Both define REST `govern-rest-1.0.json` and SSE
`govern-sse-1.0.json`; the corresponding GitHub file blob SHAs match.

From these versioned schema sources:

- REST requires `contract_version = neomundi.govern.rest/1.0` and
  `token_count_source = caller_declared`,
  `token_count_scope = caller_declared`,
  `token_count_unit = tokens`. An additional
  `stream_contract_metadata` may be an object or null on a REST replay.
- SSE done requires `contract_version = neomundi.govern.sse/1.0`,
  plus `audit`, `measurement`, `response_sha256`, `counter_units`,
  source/scope/unit declarations and the other schema-required fields.
- SSE with provider usage counts provider tokens; absent provider usage
  permits a chunk-count fallback, explicitly expressed in `counter_units`.
  A field named `total_tokens` in the fallback case is NOT evidence of
  provider token consumption.
- The SSE schema governs the **named done payload**, not each chunk/event.
  An intact checksum verifies stream assembly, not scientific validity.
- Both schemas allow additional future root fields.

The SDK now exposes the four REST string fields and optional stream replay
metadata directly, preserves the raw response, and reports invalid types.
The legacy 3.3.1 payload remains valid; no version is silently upgraded.

### Deployment parity gate (read-only)

Run `python scripts/check_live_wire_schemas.py` on an authorised local
machine with public HTTPS access. It fetches each public deployed schema
and compares bytes/SHA-256 to a pinned public GitHub reference at
`43482c070364dde9830e51aa227b8c8627c48249`.
No key, observation credits, LLM call or write is required.

**Updated 2026-11-13:** Direct access from the assistant's execution
container remains unavailable, but the GitHub Actions runner successfully
executed the read-only deployed-schema comparison. See the exact evidence
and hashes above. Synthetic SDK tests remain distinct from this proof.

## Observed deployed schema parity — 2026-11-13 23:18 UTC

A dedicated GitHub Actions Ubuntu runner performed the unauthenticated,
read-only HTTPS comparison on the exact deployed `api.neomundi.io` endpoints,
against the pinned public MCP schema source commit
`43482c070364dde9830e51aa227b8c8627c48249`.

**Both checks passed with byte-identical HTTP response bodies:**

> ⚠ **Dated record.** The REST digest below is the one served **before**
> 2026-11-15. On that day the deployment of `03e2b344` added `log_persisted`
> and `log_write` to the published REST contract — an additive change that
> left `required` untouched — and the REST digest became
> `46b0579f1d413ca75616d01eed1bef0dc317ff5e507dbcabc1dd146b7faab59c`.
> The SSE digest is unchanged. Parity was re-established and re-measured
> (`BYTE_MATCH` on both) against the updated pinned mirror; the current
> values live in `API_CONTRACT["wire_contracts"]`, measured by the test
> suite on every run.

| Published schema | Deployed SHA-256 = pinned SHA-256 |
| --- | --- |
| `govern-rest-1.0.json` | `bcd5588edc92376f59d57ad9ae155b09f5ab3fe49e15ece6cb2fe5adbf4835ef` |
| `govern-sse-1.0.json` | `358fc2ec1869471896d08c8e2cc0855b15def6433340a0506dae180733c7fefe` |

Evidence: GitHub Actions run
[43526131929](https://github.com/neomundi-io/neomundi-python-sdk/actions/runs/43526131929),
job `Compare production REST and SSE public schemas` (PASS).
No credential, billable observation, LLM provider call or production mutation.

This **resolves the deployed schema-parity gate** from the prior audit.
It establishes only that those two versioned public JSON Schema artifacts
match the pinned source **at that observation time**. It does **not**
establish full SDK error-path/degraded-path coverage, exact server runtime
commit, or scientific comparability across measurement versions.

## Synthetic degraded/error-path safety net — 2026-11-14

The SDK already had dedicated partial/null, gating, SSE interruption,
HTTP error and timeout tests. The added
`tests/test_350_degraded_errors_synthetic.py` exercises these critical
states while labelling the measurement version `3.5.0` and exposing
the REST 1.0 source/scope/unit declarations. It reuses historical
**sanitized 3.3.x fixtures** with synthetic additions, through a
**mock transport**: it is NOT a capture or a live test from 3.5.0.

This covers:
- Complete, partial and no-check-attempted cases without conflation;
- Explicit `null` aggregate and withheld-error propagation;
- Exact `3.5.0` version exposure, not forced into the verified list;
- Required core REST blocks missing, auth/server failures, and timeout;
- Exactly one simulated HTTP request per case, no automatic retry.

It does **not** cover a genuinely degraded 3.5.0 server response,
SSE provider-specific error behavior in deployed production, full
deployed-schema runtime validation of all response variants,
measurement-comparability evidence, nor provider/instrument scientific
accuracy. A passing suite must not authorize publishing a blanket
3.5.0 compatibility statement.

## Required before a verified-compatibility declaration

1. Obtain the authoritative deployed REST/SSE wire contracts and exact schema identifiers/hashes from `/v1/contracts/*` in the authorised environment; compare with the SDK's parsed fields and the actual deployed backend commit. Do not guess endpoint paths or schema content.
2. Compare **every required/optional field, types, nullability, invariants and SSE done/chunk/error semantics**, not just the ten familiar REST blocks. Explicitly specify the four new root fields and whether they should become first-class properties or remain `raw`.
3. Verify that the single REST/SSE live examples were not exceptional; test a **bounded representative degraded/null path** with a separate qualification key and no active campaign interference, only if this can be safely exercised.
4. Distinguish **wire/API compatibility** from **measurement comparability**. A client that parses a 3.5.0 response does not imply that 3.5.0 numeric observations are comparable to 3.3.0/3.3.1.
5. Capture a sanitized, rights-cleared evidence summary with exact time, revision, version, schema hashes and results. Any sensitive raw payloads and credentials remain private.
6. Only after steps 1–5 may a separate reviewed PR update `API_CONTRACT["verified_measurement_versions"]` with a precise scope and test evidence. If 3.5.0 requires significant contract changes, release the corresponding SDK update rather than quietly widening a compatibility claim.

## Separate investigation

The private report also notes a mismatch between the health endpoint's configured factuality judge and the per-observation served-by indication, as well as an unexpected backend restart. Neither can be resolved by editing SDK metadata. These require a separate backend operational investigation.

**No release/publish workflow is introduced, and `Private :: Do Not Upload` stays in place.**

---

## Measured again on 2026-11-26 — the reference itself is now stale

Re-ran the repository's own gate, `scripts/check_live_wire_schemas.py`. It
exits 1 and prints its verdict:

```
govern-rest-1.0.json BYTE_MISMATCH
  live   SHA256: 8e27a9110298a9b9ff31d6379daefddb1f068fa0b17452ed7b65e341e16d84c3
  pinned SHA256: 46b0579f1d413ca75616d01eed1bef0dc317ff5e507dbcabc1dd146b7faab59c
govern-sse-1.0.json BYTE_MISMATCH
  live   SHA256: d05caa8d48c6f64f0124a53f8977914e9e5fe0558ff6172031d3131d36c4c165
  pinned SHA256: 358fc2ec1869471896d08c8e2cc0855b15def6433340a0506dae180733c7fefe
STOP: schema parity not established; do not claim 3.5.0 verified
```

### What drifted, field by field

Both documents gained **exactly one property**, in `$defs/MeasurementBlock`:

```json
"absent_runtime_metrics": {
  "anyOf": [ { "items": { "type": "string" }, "type": "array" },
             { "type": "null" } ]
}
```

`+271 bytes` in each file. `required` is **untouched** in both
(`status`, `checks_attempted`, `checks_succeeded`, `coverage`,
`confidence_basis`). No property removed, none made required, no type
narrowed. **The drift is strictly additive**, so the SDK's unknown-field
machinery absorbs it and no parser is broken.

⚠ A first pass of this comparison reported "0 fields added" because the
flattener did not traverse `$defs`. A textual diff caught it. Recorded
because a fabricated "nothing changed" is worse than no comparison.

### 🔴 Why the digests are NOT re-pinned here

`neomundi-measurement-mcp` at `main` (`cfd5fb8e`) serves **the same
digests this SDK pins** — `46b0579f` and `358fc2ec`. So production is
**ahead of the public schema source**, not merely ahead of this SDK.

There is therefore no public, independently-versioned reference that
matches what production serves. Re-pinning to production's own bytes would
make the gate compare production to itself, which proves nothing and would
quietly destroy the only parity evidence the SDK has.

**The action is upstream:** `neomundi-measurement-mcp` must republish the
contracts that production now serves. Only then can `SOURCE_COMMIT` move
and the digests be re-pinned with real evidence.

### 🔴 The gate is dormant, and that is why nobody noticed

`.github/workflows/live-schema-parity.yml` triggers on
`pull_request` **restricted by `paths`** to its own two files, plus
`workflow_dispatch`. There is no `schedule`. Production can drift
arbitrarily and nothing turns red — which is exactly what happened.

A `schedule:` trigger is **deliberately not added in this pull request**:
today it would be red immediately for a cause only the backend and the MCP
repository can fix, and a permanently red workflow teaches people to ignore
it. Wake it in the same change that republishes the schemas.

Note also that `SOURCE_COMMIT` is a **pull-request branch commit**
(`3e200b33`), carrying its own comment asking for it to be re-pointed at
the merge commit before that branch is deleted. It still resolves today;
it is a dangling reference and should move when the schemas are
republished.

### Verdict on requirement 1 of the six below

**Not met, and for a new reason.** It is no longer "partially qualified
pending independent verification": the authoritative public reference is
itself behind production, so there is nothing to compare the deployed
contract against. `verified_measurement_versions` is therefore left
unchanged at `("3.3.0", "3.3.1")`.

### What this pull request does change

The SDK now **performs** the comparison it has only ever declared. See
`models.warn_on_measurement_version`. That is the duplication worth
removing: of the five published integrations, only `langchain-neomundi`
implemented the check, and a direct user of this SDK got nothing at all.

