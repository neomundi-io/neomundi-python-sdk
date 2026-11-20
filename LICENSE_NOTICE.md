# Licensing boundaries — NeoMundi SDK and hosted Runtime Measurement

**SDK licence chosen: Apache License 2.0.** The SDK source in this repository is intended to be distributed under the terms of the root [LICENSE](LICENSE). The permissive licence permits use, modification, and redistribution of SDK code (including commercial use), subject to its conditions. Public distribution still requires confirmation that NeoMundi has the rights to license all included contributions and third-party material.

**Distinct scope: NeoMundi hosted Runtime Measurement remains a proprietary, commercial service.** The SDK's Apache-2.0 licence does not grant hosted API access, observation credits, service capacity, credentials, use of hosted models, or rights to private backend code. Hosted usage requires an authorised account/API key and applicable commercial terms and available credits/quotas. Pricing and operational terms are governed separately, not by this repository.

The same separation applies to Station and Evidence unless and until they receive their own explicit licensing or product terms. A future community runtime is a roadmap possibility, not a grant of rights to the currently private engine.

## Release status

- **No PyPI upload is authorised yet.** The `Private :: Do Not Upload` classifier has been removed from `pyproject.toml`, because PEP 639 metadata and the activation candidate require its absence; `tests/test_pypi_release_guard.py` asserts it stays absent. Publication is held instead by `.github/workflows/publish-pypi.yml`: manual `workflow_dispatch` only, on `main`, with the exact `sdk-v2.0.0` tag, the `PUBLISH_NEOMUNDI_TO_PYPI` confirmation phrase and the protected `pypi` environment. Removing the classifier does not authorise an upload.
- The package's installed distribution name is being prepared as `neomundi`, distinct from the hosted service.
- The rights holder is recorded in the root [NOTICE](NOTICE): Copyright 2026 Sébastien FAVRE. The Association NeoMundi Recherche holds a technical and scientific right of use; that mention is informative and adds no restriction to the Apache-2.0 grant. Ownership of contributions and third-party material still has to be verified before public distribution.
- Before publication, verify clean distribution artifacts, CI, compatibility with the current API, and the PyPI Trusted Publisher configuration.
- The sole runtime dependency declared by this SDK, `httpx`, uses the BSD-3-Clause licence. Its licence remains its own.

**Important:** A public repository or open-source SDK does not make the proprietary NeoMundi hosted API open source or free.
