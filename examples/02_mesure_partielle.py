"""Exemple 2 — Lire un résultat partiellement mesuré.

SERVEUR SIMULÉ. Aucun réseau.

    python examples/02_mesure_partielle.py

C'est le cas qui distingue NeoMundi : quand un évaluateur n'a rien pu
produire, les agrégats sont publiés `null`, le verdict passe à `FLAG`, et
la cause est nommée. **Un `FLAG` d'incomplétude ne dit rien du contenu.**

C'est aussi le cas sur lequel le code d'exemple officiel du backend se
casse : `f"{score:.2f}"` sur un `null` lève un `TypeError`. Cet exemple
montre les deux manières correctes de le gérer.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from neomundi import AggregateWithheldError, MeasurementState, NeoMundiClient  # noqa: E402

FIXTURE = Path(__file__).parent.parent / "tests/fixtures/partial_measurement.json"


def serveur_simule() -> httpx.MockTransport:
    payload = {
        k: v
        for k, v in json.loads(FIXTURE.read_text(encoding="utf-8")).items()
        if not k.startswith("_fixture_")
    }
    return httpx.MockTransport(lambda _r: httpx.Response(200, json=payload))


def main() -> int:
    print("=" * 70)
    print("Exemple 2 — Mesure partielle : le juge de factualité est muet")
    print("=" * 70)

    with NeoMundiClient(
        api_key="ct_test_0000000000000000000000000000",
        base_url="https://example.invalid",
        transport=serveur_simule(),
    ) as client:
        result = client.govern(
            token_count=140,
            latency_ms=915.0,
            llm_prompt="Résume ce contrat en trois points.",
            llm_response="Le contrat prévoit trois obligations principales…",
        )

    # ------------------------------------------------------------------
    # 1. Toujours commencer par là : la mesure est-elle complète ?
    # ------------------------------------------------------------------
    print("\n--- 1. La mesure est-elle complète ? ---")
    print(f"  measurement_incomplete   : {result.measurement_incomplete}")
    print(f"  aggregates_publishable   : {result.aggregates_publishable}")
    print(f"  missing_required_signals : {result.missing_required_signals}")
    print(f"  decision                 : {result.governance.decision}")
    print(f"  decision_basis           : {result.governance.decision_basis}")

    if result.governance.decision_basis == "incomplete_measurement":
        print("\n  >>> Ce FLAG ne porte PAS sur le contenu de la réponse.")
        print("      Il dit que la mesure ne s'est pas terminée.")
        print(f"      Raison : {result.governance.reasons[0][:90]}…")

    # ------------------------------------------------------------------
    # 2. Signal par signal : ce qui a été mesuré n'est pas perdu
    # ------------------------------------------------------------------
    print("\n--- 2. Signal par signal ---")
    for signal in (
        "coherence_score",
        "semantic_risk",
        "factual_hallucination_score",
        "semantic_instability_score",
    ):
        etat = result.measurement_state(signal)
        valeur = result.format_score(f"quality.{signal}", when_none="null")
        cause = result.unmeasured_reason(signal) or ""
        marque = {
            MeasurementState.MEASURED: "mesuré",
            MeasurementState.NOT_MEASURED: "NON MESURÉ",
            MeasurementState.NOT_ATTEMPTED_OR_GATED: "non tenté ou masqué",
            MeasurementState.UNKNOWN: "indéterminé",
        }[etat]
        print(f"  {signal:30} {valeur:>8}  {marque:<22} {cause}")

    print("\n  >>> La cohérence et le risque, eux, ONT été mesurés :")
    print(f"      coherence_score = {result.quality.coherence_score}")
    print(f"      semantic_risk   = {result.quality.semantic_risk}")
    print("      Ces valeurs restent exploitables. Seuls les AGRÉGATS sont retenus.")

    # ------------------------------------------------------------------
    # 3. Deux manières correctes de lire un agrégat retenu
    # ------------------------------------------------------------------
    print("\n--- 3. Lire un agrégat qui peut être null ---")

    # (a) Pour l'AFFICHAGE : format_score ne lève jamais.
    print(f"  (a) affichage : g_score = {result.format_score('g_score')}")

    # (b) Pour un CALCUL : require() lève une exception qui nomme la cause.
    try:
        valeur = result.require("g_score")
        print(f"  (b) calcul    : g_score = {valeur}")
    except AggregateWithheldError as exc:
        print(f"  (b) calcul    : refusé — {exc}")
        print(f"      champ                    : {exc.field}")
        print(f"      missing_required_signals : {exc.missing_required_signals}")

    # (c) Ce qu'il NE FAUT PAS faire — l'erreur de l'exemple officiel.
    print("\n  (c) Ce qu'il ne faut pas faire :")
    try:
        print(f"      {result.g_score:.2f}")
    except TypeError as exc:
        print(f"      TypeError: {exc}")
        print("      >>> C'est exactement le défaut de l'exemple de GUIDE_CLIENT.md.")

    # ------------------------------------------------------------------
    # 4. Le piège dérivé : un Di de 1.0 qui ne prouve rien
    # ------------------------------------------------------------------
    print("\n--- 4. Les valeurs dérivées déclarent leur entrée ---")
    d = result.density
    print(f"  informational_density  : {d.informational_density}")
    print(f"  factual_input_measured : {d.factual_input_measured}")
    print(f"  unmeasured_reason      : {d.unmeasured_reason}")
    if d.factual_input_measured is False:
        print("  >>> Ce Di de 1.0 est dérivé d'un score que personne n'a mesuré.")
        print("      Ce n'est PAS une preuve d'absence de dissipation.")

    # ------------------------------------------------------------------
    # 5. Un champ à ne pas lire comme une dérive
    # ------------------------------------------------------------------
    print("\n--- 5. Avertissement sur delta_g ---")
    print(f"  delta_g = {result.delta_g}   (alors que g_score = {result.g_score})")
    print("  >>> Le serveur publie un delta_g numérique sur une réponse dont")
    print("      l'agrégat est retenu, et mémorise 0.0 comme référence : le")
    print("      delta suivant en sera faussé. Ne pas lire ce champ comme une")
    print("      mesure de dérive. Voir docs/LIMITES.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
