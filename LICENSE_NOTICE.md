# Licensing boundaries — NeoMundi SDK and hosted Runtime Measurement

**SDK licence chosen: Apache License 2.0.** The SDK source in this repository is intended to be distributed under the terms of the root [LICENSE](LICENSE). The permissive licence permits use, modification, and redistribution of SDK code (including commercial use), subject to its conditions. Public distribution still requires confirmation that NeoMundi has the rights to license all included contributions and third-party material.

**Distinct scope: NeoMundi hosted Runtime Measurement remains a proprietary, commercial service.** The SDK's Apache-2.0 licence does not grant hosted API access, observation credits, service capacity, credentials, use of hosted models, or rights to private backend code. Hosted usage requires an authorised account/API key and applicable commercial terms and available credits/quotas. Pricing and operational terms are governed separately, not by this repository.

The same separation applies to Station and Evidence unless and until they receive their own explicit licensing or product terms. A future community runtime is a roadmap possibility, not a grant of rights to the currently private engine.

## Release status

- **No PyPI upload is authorised yet**; `Private :: Do Not Upload` stays in `pyproject.toml` until the separate publication release approval.
- The package's installed distribution name is being prepared as `neomundi`, distinct from the hosted service.
- Before merging the licensing change, verify ownership of SDK files, contributions and copyright notices; record the correct rights holder in a separate NOTICE if needed.
- Before publication, verify clean distribution artifacts, CI, compatibility with the current API, and the PyPI Trusted Publisher configuration.
- The sole runtime dependency declared by this SDK, `httpx`, uses the BSD-3-Clause licence. Its licence remains its own.

**Important:** A public repository or open-source SDK does not make the proprietary NeoMundi hosted API open source or free.
