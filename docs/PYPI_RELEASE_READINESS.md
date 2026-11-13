# PyPI readiness — distribution `neomundi` (candidate only)

**Status: NOT APPROVED FOR PUBLICATION.** This file documents the release gates; it does not authorise a PyPI upload or imply that the project name is reserved.

## Intended scope

- Distribution name: `neomundi` (subject to PyPI acceptance).
- Python import: `from neomundi import NeoMundiClient` (unchanged).
- Source package: existing REST + SSE SDK v2.0.0; no new backend engine, evaluator implementation, Station client or Evidence verifier.
- Runtime dependency: `httpx`.
- `Private :: Do Not Upload` remains enabled to prevent unintended upload.

## Mandatory gates before first release

1. **Licence and rights:** the SDK licence has been selected as Apache-2.0; verify copyright ownership, contributors’ grants and third-party material before merging and before publication. The hosted Runtime Measurement service remains separately proprietary and commercially metered. See `LICENSE` and `LICENSE_NOTICE.md`.
2. **Distribution identity:** verify the proposed `neomundi` name on PyPI when publishing. Search results and pending trusted-publisher registration are not a reservation. Confirm authorised PyPI project ownership.
3. **Version and compatibility:** see [the partial 3.5.0 compatibility assessment](COMPATIBILITY_350.md) and its evidence gaps; do not add 3.5.0 to the verified list just because a live round trip passed. Confirm that distribution version `2.0.0` is the intended *SDK* release, distinct from the server's measurement version. Review how the SDK handles the *currently served* REST and SSE contracts; its documented verification references measurement versions 3.3.0/3.3.1 and older backend commits, not a fresh production qualification.
4. **Offline tests:** run the full suite and inspect skips, lint warnings and secret guards on the final commit, not only prior reports. The CI must build source and wheel distributions, pass `twine check`, install the wheel in a fresh environment, and assert `importlib.metadata.distribution("neomundi")` resolves the installed name.
5. **Live, bounded qualification:** with explicit approval and pilot-safe credentials, run an installed-wheel REST request and SSE request against an identified live environment, recording *only sanitised* request/result metadata, served version, completeness, transport integrity, actual quotas and any missing evaluator signals. No secrets or prompt/response text in public reports. No claim of production compatibility before this passes.
6. **Public package inspection:** review `sdist` and wheel file inventories for proprietary backend material, secrets, captured observations, personal paths and nonredistributable fixtures. Reconcile `LICENSE_NOTICE.md`, package metadata, README examples and explicit availability warnings.
7. **Trusted publication:** after steps 1–6 are approved, configure PyPI Trusted Publishing (OIDC) for a narrowly scoped, protected GitHub release environment/tag. Use minimal `id-token: write` on the publish job only, never on PRs; require approval for release. Do not add a password or long-lived API token to the repository.
8. **Final release approval:** only then remove `Private :: Do Not Upload` and add a separate release PR/CI workflow. Dry-run on TestPyPI where appropriate and verify installation and metadata before the production PyPI upload.

## Commands for the packaging qualification

```sh
python -m pip install -e ".[dev]"
python -m pytest tests -v
python -m pip install build twine
python -m build
python -m twine check dist/*
# The resulting wheel should have a name like neomundi-2.0.0-py3-none-any.whl.
# The CI also installs it into a clean environment and checks the metadata.
```

**No release workflow, PyPI credentials, automatic tag publication, measurement-version change or production deployment are part of this preparation.**
