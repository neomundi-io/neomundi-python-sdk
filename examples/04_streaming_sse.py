"""SERVEUR SIMULÉ — synthetic SSE transport; no real provider or API call."""

import hashlib
import json

import httpx

from neomundi import NeoMundiClient


def example():
    text = "Réponse de démonstration."
    final = dict(
        response_text=text,
        response_length=len(text),
        response_bytes=len(text.encode("utf-8")),
        response_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        decision="FLAG",
        decision_basis="incomplete_measurement",
        stability_score=None,
        measurement={"status": "incomplete"},
    )
    wire = (
        "event: chunk\ndata: "
        + json.dumps({"content": text})
        + "\n\n"
        + "event: done\ndata: "
        + json.dumps(final)
        + "\n\n"
    )
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=wire.encode()
        )
    )
    with NeoMundiClient(
        api_key="ct_test_00000000000000000000",
        base_url="https://example.invalid",
        transport=transport,
    ) as client:
        with client.stream(
            prompt="Question de démonstration",
            model="synthetic-model",
            provider="anthropic",
            provider_api_key="provider_TEST_000000000000",
        ) as stream:
            for event in stream:
                if event.event == "chunk":
                    print(event.content)
            assert stream.result is not None
            print("integrity_verified:", stream.result.integrity_verified)
            print("measurement:", stream.result.measurement)


if __name__ == "__main__":
    example()
