"""Exemple 1 — Première mesure avec NeoMundi.

SERVEUR SIMULÉ. Cet exemple ne contacte aucun serveur : il branche le
client sur un transport httpx simulé qui répond une charge figée. Il est
exécutable tel quel et sert de test de bout en bout du SDK.

    python examples/01_premiere_mesure.py

Pour l'équivalent avec une vraie clé, voir `examples/90_cle_reelle.py.disabled`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from neomundi import NeoMundiClient  # noqa: E402

FIXTURE = Path(__file__).parent.parent / "tests/fixtures/full_measurement.json"


def serveur_simule() -> httpx.MockTransport:
    """Un transport qui répond une mesure complète, sans réseau."""
    payload = {
        k: v
        for k, v in json.loads(FIXTURE.read_text(encoding="utf-8")).items()
        if not k.startswith("_fixture_")
    }

    def handler(request: httpx.Request) -> httpx.Response:
        print(f"  [serveur simulé] {request.method} {request.url.path}")
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


def main() -> int:
    print("=" * 70)
    print("Exemple 1 — Première mesure (serveur simulé)")
    print("=" * 70)

    client = NeoMundiClient(
        api_key="ct_test_0000000000000000000000000000",
        base_url="https://example.invalid",
        transport=serveur_simule(),
    )

    with client:
        # L'appelant a DÉJÀ interrogé son modèle. Il envoie ici les
        # métriques réelles de la réponse obtenue.
        result = client.govern(
            token_count=128,
            latency_ms=842.0,
            cost=0.0031,
            prompt_length=480,       # en CARACTÈRES
            response_length=1200,    # en CARACTÈRES
            model_name="gpt-4o-mini",
            llm_prompt="Quelle est la capitale de la France ?",
            llm_response="La capitale de la France est Paris.",
        )

    print("\n--- Identité de l'observation ---")
    print(f"  request_id         : {result.request_id}")
    print(f"  horodatage         : {result.timestamp_raw}")
    print(f"  version de mesure  : {result.audit.measurement_version}")

    print("\n--- Verdict ---")
    print(f"  décision           : {result.governance.decision}")
    print(f"  base de la décision: {result.governance.decision_basis}")
    for reason in result.governance.reasons:
        print(f"    · {reason}")

    print("\n--- Complétude de la mesure ---")
    m = result.measurement
    print(f"  statut             : {m.status}")
    print(f"  contrôles lancés   : {m.checks_attempted}")
    print(f"  contrôles réussis  : {m.checks_succeeded}")
    print(f"  couverture         : {m.coverage}")
    # La couverture est re-dérivable : le consommateur peut la vérifier.
    print(
        f"  vérification       : {m.checks_succeeded}/{m.checks_attempted} "
        f"= {m.checks_succeeded / m.checks_attempted:.6f}"
    )

    print("\n--- Signaux, un par un ---")
    for signal in (
        "coherence_score",
        "semantic_risk",
        "factual_hallucination_score",
        "semantic_instability_score",
    ):
        etat = result.measurement_state(signal).value
        valeur = result.format_score(f"quality.{signal}", nd=4)
        ev = result.evaluator_of(signal) or {}
        modele = ev.get("model_used") or "—"
        print(f"  {signal:30} {valeur:>10}  [{etat}]  modèle={modele}")

    print("\n--- Agrégats ---")
    # `format_score` ne lève JAMAIS, même si la valeur est null.
    print(f"  g_score            : {result.format_score('g_score', nd=4)}")
    print(f"  stability_score    : {result.format_score('quality.stability_score')}")
    print(f"  g_final            : {result.format_score('g_final')}")
    print(f"  publiables         : {result.aggregates_publishable}")

    print("\n--- À savoir avant d'interpréter ces nombres ---")
    print("  · stability_score vit en pratique dans [0.60 ; 1.00], pas [0 ; 1].")
    print("  · g_final vit en pratique dans [0.40 ; 1.00].")
    print("  · metrics.stability_score est l'ÉCHELLE INVERSE :")
    print(
        f"      quality.stability_score = {result.quality.stability_score}  (1 = stable)"
    )
    print(
        f"      metrics.stability_score = {result.metrics.stability_score}  (0 = stable)"
    )
    print("  · Voir docs/LIMITES.md avant toute communication d'un score.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
