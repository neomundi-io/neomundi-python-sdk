# Live SDK V2 qualification — controlled execution

**Not yet executed against a hosted service.** This is an opt-in test protocol, not a production compatibility claim. The SDK 2.0.0 REST/SSE tests so far use mocks and historical contract evidence; the current production API may differ. In particular, verify whether `POST /v1/govern/stream` is enabled on the target environment before testing SSE.

## Safety and scope

- Run only when there is **no active pilot campaign affected**, with an isolated NeoMundi test/trial key and enough observation credits. The script does not modify API configuration or measurement versions.
- Exactly **one REST request** and, separately, **one SSE request** at most, only when each is deliberately launched. Never automatic in CI. Never retry a timed-out POST without first reconciling observation records and charges.
- REST sends an explicitly labelled **synthetic demo observation**. Its `token_count`/`latency_ms` values are fixtures, *not* measured usage and cannot qualify scientific accuracy.
- SSE is a separate generation route. It requires an authorised provider key; the `max_tokens=16` cap bounds requested output tokens, **not** provider cost, server evaluation cost, latency, nor the overall observation charge. Check that SSE is actually deployed and permitted before attempting it. The SDK's current read timeout is explicitly set to 30 seconds; a timeout is not proof that the backend did not charge.
- Credentials must be supplied via **local environment variables**, never committed, put in PR comments or uploaded to GitHub Actions. The script prints only limited categorical statuses and counts and intentionally omits request IDs, prompts, generated text, scores and raw responses. Exception messages are not printed.
- No automated action may read local production keys or charge pilots. Test evidence must be recorded privately with approved sanitisation. Do not record live API keys or provider keys even in private reports.

## Commands (run locally, not on GitHub CI)

Install the built wheel in a clean Python environment. Confirm `import neomundi` comes from that installed wheel and not from the source tree.

```sh
python scripts/qualify_live_sdk.py --mode rest
python scripts/qualify_live_sdk.py --mode sse
```

These are **preflight only**: no network calls. For execution, set `NEOMUNDI_BASE_URL`, `NEOMUNDI_API_KEY` and `NEOMUNDI_SDK_LIVE_APPROVED=YES` in your local environment, then deliberately run:

```sh
python scripts/qualify_live_sdk.py --mode rest --execute
```

After the REST outcome is reconciled, **only if SSE is enabled, approved and provider cost is acceptable**, also set `LLM_PROVIDER`, `LLM_MODEL`, `LLM_PROVIDER_API_KEY` and run:

```sh
python scripts/qualify_live_sdk.py --mode sse --execute
```

The Python script performs no checks on whether pilots are active and cannot determine billing balance. Those must be confirmed externally before execution.

## Evidence and verdict

Record in a controlled private qualification report: tested commit/wheel hash, date/time, authorised target environment, API/measurement version actually returned, request IDs retained privately where permitted, REST parse warnings, unknown fields, measured/unmeasured coverage, SSE event completion/integrity, whether the route is enabled, observed quota/credits before and after, and errors without secrets. Distinguish transport compatibility from measurement completeness, and label all synthetic inputs explicitly. A completed REST transport does not guarantee measurements were available.

**Do not change the SDK compatibility contract or measurement version simply to make tests pass.** A server-side protocol change, disabled SSE or unexpected score representation requires separate diagnosis. Do not publish to PyPI until contractual compatibility, rights and protected release workflow are verified.
