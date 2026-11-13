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
