"""Bounded live SDK qualification. Defaults to preflight; NEVER automatic in CI.

Use an isolated, authorised account. Each --execute call sends exactly one
request with no retries. Output is intentionally minimal and never includes
keys, prompts, response text, request ids or raw server payloads.
"""
from __future__ import annotations

import argparse
import os
import sys
from importlib.metadata import distribution

from neomundi import API_CONTRACT, NeoMundiClient

_PREFIX = ("ct_test_", "ct_trial_", "ct_live_")


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Missing environment variable: {name}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("rest", "sse"), required=True)
    parser.add_argument("--execute", action="store_true", help="Opt-in to exactly one live request")
    args = parser.parse_args()
    print("SDK distribution:", distribution("neomundi").metadata["Name"])
    print("SDK version:", distribution("neomundi").version)
    print("Selected mode:", args.mode)
    print("Automatic retries: disabled")
    print("Max live attempts: 1")
    if not args.execute:
        print("PREFLIGHT ONLY: no network request, no observation credits consumed")
        return 0

    try:
        url = _required("NEOMUNDI_BASE_URL")
        key = _required("NEOMUNDI_API_KEY")
        if not key.startswith(_PREFIX):
            raise ValueError("NeoMundi API key prefix not recognised")
        if not url.startswith("https://"):
            raise ValueError("An HTTPS API base URL is required")
        # Explicit permission gate also ensures this script cannot run in
        # a standard CI checkout merely because credentials exist.
        if os.environ.get("NEOMUNDI_SDK_LIVE_APPROVED") != "YES":
            raise ValueError("Explicit NEOMUNDI_SDK_LIVE_APPROVED=YES is required")
        if args.mode == "sse":
            provider = _required("LLM_PROVIDER")
            model = _required("LLM_MODEL")
            provider_key = _required("LLM_PROVIDER_API_KEY")
        print("LIVE ATTEMPT: exactly one", args.mode.upper(), "request")
        with NeoMundiClient(api_key=key, base_url=url, timeout=30.0) as client:
            if args.mode == "rest":
                # Synthetic fixture, explicitly not a scientific calibration
                # result. Never record these synthetic usage figures as facts.
                result = client.govern(
                    token_count=2, latency_ms=1.0,
                    llm_prompt="What is the capital of France?",
                    llm_response="Paris.",
                    metadata={"qualification": "sdk_v2_synthetic_transport_check"},
                )
                print("Transport: completed")
                print("Measurement version:", result.audit.measurement_version)
                print("Version in previously verified set:",
                      result.audit.measurement_version in API_CONTRACT["verified_measurement_versions"])
                print("Measurement status:", result.measurement.status if result.measurement else "missing")
                print("Measured signal count:", len(result.measured_signals or []))
                print("Unmeasured signal count:", len(result.unmeasured_signals or {}))
                print("Parse warning count:", len(result.parse_warnings))
                print("Unknown field count:", len(result.unknown_fields))
            else:
                # This path is NOT a REST observation: it performs a provider
                # generation and can consume provider spend plus API credits.
                # No SSE call occurs unless --mode sse --execute is given.
                with client.stream(
                    prompt="Reply with one word: Paris",
                    provider=provider, model=model, provider_api_key=provider_key,
                    max_tokens=16, temperature=0,
                    metadata={"qualification": "sdk_v2_sse_transport_check"},
                ) as stream:
                    for _event in stream:
                        pass
                    result = stream.result
                if result is None:
                    raise RuntimeError("No terminal SSE result")
                print("Transport: completed")
                print("SSE integrity verified:", result.integrity_verified)
                print("Measurement status:", result.measurement.get("status") if result.measurement else "missing")
                print("Returned response character count:", len(result.response_text))
        print("QUALIFICATION ATTEMPT RECORDED; assess contract and measurement separately")
        return 0
    except Exception as exc:
        # No str(exc): an upstream failure might echo secrets or user data.
        print("QUALIFICATION FAILED:", type(exc).__name__, file=sys.stderr)
        print("Do not retry until the request and quota state are reconciled", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
