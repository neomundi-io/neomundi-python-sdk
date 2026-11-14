# PyPI readiness — distribution `neomundi` (candidate only)

**Status: ACTIVATION CANDIDATE — NOT APPROVED FOR PUBLICATION.** This file documents the release gates; it does not authorise a PyPI upload or imply that the project name is reserved.

## Intended scope

- Distribution name: `neomundi` (subject to PyPI acceptance).
- Python import: `from neomundi import NeoMundiClient` (unchanged).
- Source package: existing REST + SSE SDK v2.0.0; no new backend engine, evaluator implementation, Station client or Evidence verifier.
- Runtime dependency: `httpx`.
- This candidate branch removes `Private :: Do Not Upload` for a future approved release. It does not publish; merging the activation PR alone cannot dispatch the manual release workflow.

## Mandatory gates before first release

1. **Licence and rights:** the SDK licence has been selected as Apache-2.0; verify copyright ownership, contributors’ grants and third-party material before merging and before publication. The hosted Runtime Measurement service remains separately proprietary and commercially metered. See `LICENSE` and `LICENSE_NOTICE.md`.
2. **Distribution identity:** verify the proposed `neomundi` name on PyPI when publishing. Search results and pending trusted-publisher registration are not a reservation. Confirm authorised PyPI project ownership.
3. **Version and compatibility:** see [the 3.5.0 compatibility assessment](COMPATIBILITY_350.md): the installed 2.0.0 wheel passed one real REST and SSE call on 2026-11-13; both deployed REST/SSE JSON schemas matched their pinned public references byte-for-byte. An actual degraded/null 3.5.0 run, all providers, and scientific comparability have NOT been established. Do not add 3.5.0 to the verified list without evidence. SDK version `2.0.0` and server measurement version `3.5.0` identify different components.
4. **Offline tests:** run the full suite and inspect skips, lint warnings and secret guards on the final commit, not only prior reports. The CI must build source and wheel distributions, pass `twine check`, install the wheel in a fresh environment, and assert `importlib.metadata.distribution("neomundi")` resolves the installed name.
5. **Live, bounded qualification:** the 2026-11-13 installed-wheel REST/SSE checks passed, as recorded in the private operator qualification report. Review the actual request/response evidence and confirm the limited claims made in the README; the test used a live campaign-account key, so do not repeat it casually. Any further degraded-path test needs isolated pilot-safe credentials and explicit approval. Keep private identifiers and raw data out of GitHub.
6. **Public package inspection:** review `sdist` and wheel file inventories for proprietary backend material, secrets, captured observations, personal paths and nonredistributable fixtures. Reconcile `LICENSE_NOTICE.md`, package metadata, README examples and explicit availability warnings.
7. **Trusted publication:** after steps 1–6 are approved, configure PyPI Trusted Publishing (OIDC) for `neomundi-io/neomundi-python-sdk`, workflow `publish-pypi.yml` and environment `pypi`; configure that environment's required reviewers and deployment-branch rules in GitHub. Use minimal `id-token: write` on the publish job only, never on PRs; require approval for release. Do not add an API token to GitHub.
8. **Final release approval:** the release workflow is prepared but is **manual only** (`workflow_dispatch` on `main` with exact `sdk-v2.0.0` tag and confirmation phrase). This activation candidate removes `Private :: Do Not Upload` **only on its review branch**. The GitHub `pypi` environment and PyPI pending Trusted Publisher have been configured by the owner (screenshots supplied on 2026-11-14); their protection and account state must be rechecked before final dispatch. The owner must separately authorise PR merge and eventual publication, after licensing and provenance review. Then run final CI, protect the `pypi` environment, create the exact release tag at reviewed main HEAD, and manually dispatch the workflow. Do not merge unrelated code between tag and dispatch; the workflow verifies tag matches main HEAD. Then verify `pip install neomundi==2.0.0` from the actual index in a fresh environment.

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

**This activation-candidate PR only removes the packaging upload blocker and adjusts the release tests/docs. There is still no PyPI credential, tag, publication, auto-trigger, measurement-version change or production deployment.**


## Owner release checklist — activation candidate

1. **GitHub setup reported complete on 2026-11-14:** screenshots show environment `pypi`, required reviewer `Neomundi-Labs`, administrator bypass disabled, and deployment restricted to `main`. Reconfirm those settings before publishing. Note that GitHub branch `main` alone is allowed; no tag rule was configured, and the workflow is manually dispatched *from main*, then checks out a tag in its build job.
2. **PyPI Pending Trusted Publisher reported complete on 2026-11-14:** screenshot shows pending project name `neomundi`, GitHub owner `neomundi-io`, repository `neomundi-python-sdk`, workflow `publish-pypi.yml`, environment `pypi`. Pending publishing does not reserve the project name. Check that it still belongs to the correct PyPI account when ready.
3. Record code-licensing rights and any contributor permissions; verify no proprietary engine, keys or unredistributable material are present in built distributions. Complete any outstanding compatibility wording review, **without silently asserting scientific comparability**.
4. **Current PR is the separate activation PR:** it removes `Private :: Do Not Upload`. Do not merge or create the release tag until code-rights review, exact CI evidence, and the owner's explicit merge approval. The configured job remains manual; removing the classifier alone does not publish.
5. At final approved main HEAD, create release tag `sdk-v2.0.0` and invoke GitHub Actions **PyPI release (manual, gated)** from `main`, entering `sdk-v2.0.0` and the exact confirmation `PUBLISH_NEOMUNDI_TO_PYPI`. The workflow builds, audits, installs and uploads via short-lived OIDC credentials only after any environment protection approval.
6. Validate the resulting PyPI project page, upload files and metadata, then perform a fresh `python -m pip install neomundi==2.0.0` and basic import/smoke test outside the source tree.

**Important:** only the separately authorised manual GitHub Actions release job can upload to PyPI. Neither opening nor merging this PR uploads or reserves the package. Do not approve the publish job if reviewer bypass, account identity, or licensing rights are unclear.
