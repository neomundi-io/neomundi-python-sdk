"""Exemple 5 — le parcours complet : INSTALL → TRACE → MEASURE → VERIFY.

SERVEUR SIMULÉ. Cet exemple ne contacte aucun serveur : il branche le
client sur un transport httpx simulé qui répond des charges figées. Il est
exécutable tel quel.

    python examples/05_parcours_complet.py

Ce qu'il montre, étape par étape, **et ce que chaque étape n'établit
pas** — parce que c'est la moitié utile de la démonstration.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from neomundi import (  # noqa: E402
    EvidenceVerifierUnavailable,
    NeoMundiClient,
    verify_evidence_archive,
)

RACINE = Path(__file__).parent.parent
FIXTURE = RACINE / "tests/fixtures/full_measurement.json"


def mon_application(question: str) -> tuple[str, int]:
    """L'appel que l'application fait à SON fournisseur.

    NeoMundi n'intervient pas ici : c'est l'appelant qui interroge son
    modèle, et c'est lui qui connaît le décompte de tokens rendu par le
    fournisseur. Le SDK ne l'invente jamais.
    """
    # Un fournisseur réel met du temps à répondre. Sans cette pause, le
    # bloc est plus court qu'un tic de `time.monotonic()` (~15,6 ms sur
    # Windows) et la latence mesurée vaut réellement 0,0 — ce que le SDK
    # transmettrait tel quel, parce qu'il ne corrige pas une mesure.
    time.sleep(0.05)
    reponse = "La capitale de la France est Paris."
    tokens_rendus_par_le_fournisseur = 9
    return reponse, tokens_rendus_par_le_fournisseur


def serveur_simule() -> httpx.MockTransport:
    """Répond à la mesure ET aux deux routes publiques de vérification."""
    mesure = {
        k: v
        for k, v in json.loads(FIXTURE.read_text(encoding="utf-8")).items()
        if not k.startswith("_fixture_")
    }
    # Les cinq racines que le contrat de fil déployé publie.
    mesure.update(
        {
            "contract_version": "neomundi.govern.rest/1.0",
            "token_count_source": "caller_declared",
            "token_count_scope": "caller_declared",
            "token_count_unit": "tokens",
            "stream_contract_metadata": None,
        }
    )
    request_id = mesure["request_id"]

    def handler(request: httpx.Request) -> httpx.Response:
        chemin = request.url.path
        print(f"  [serveur simulé] {request.method} {chemin}")
        if chemin == "/v1/govern":
            return httpx.Response(200, json=mesure)
        if chemin == f"/v1/rgc/verify/{request_id}":
            return httpx.Response(
                200,
                json={
                    "valid": True,
                    "request_id": request_id,
                    "payload_hash_match": True,
                    "signature_valid": True,
                    "key_id": "neomundi-rgc-2026-01",
                    "verified_at": "2026-11-15T10:00:00+00:00",
                },
            )
        if chemin.startswith("/v1/audit/verify/"):
            # Sans `?sha256=`, le serveur réel répond `valid: null`.
            return httpx.Response(
                200,
                json={
                    "valid": None,
                    "verification": "no sha256 supplied: pass ?sha256=<...>",
                    "record_found": True,
                    "audit_trail_id": "AT-2026-0001",
                    "request_id": request_id,
                    "sha256": "0" * 64,
                    "issuer": "neomundi-controltower-api",
                },
            )
        return httpx.Response(404, json={"error": "not_found", "detail": chemin})

    return httpx.MockTransport(handler)


def main() -> int:
    print("=" * 70)
    print("Exemple 5 - INSTALL -> TRACE -> MEASURE -> VERIFY (serveur simule)")
    print("=" * 70)

    client = NeoMundiClient(
        api_key="ct_test_0000000000000000000000000000",
        base_url="https://example.invalid",
        transport=serveur_simule(),
    )

    with client:
        # ---------------------------------------------------------------
        # TRACE + MEASURE — une seule requête, et elle est nommée
        # ---------------------------------------------------------------
        print("\n--- TRACE (réel : chronomètre local + corrélation) ---")
        question = "Quelle est la capitale de la France ?"

        with client.trace(
            client_trace_id="commande-4711",
            model_name="mon-modele",
        ) as trace:
            reponse, tokens = mon_application(question)
            trace.record(prompt=question, response=reponse, token_count=tokens)

        record = trace.record_
        print(f"  issue                : {record.outcome}")
        print(f"  latence MESURÉE      : {record.latency_ms:.3f} ms")
        print(f"  tokens DÉCLARÉS      : {record.token_count}")
        print(f"  mon identifiant      : {record.client_trace_id}")
        print(f"  identifiant serveur  : {record.request_id}")
        print(f"  accusé de traitement : {record.acknowledged}")
        print(f"  ENREGISTRÉ ?         : {record.registered}  "
              "<- None : cette route ne publie AUCUNE confirmation d'écriture")
        print(f"  trace_id serveur     : {record.server_trace_id}  "
              "<- dérivé, tronqué, NON unique : ne jamais s'en servir comme clé")
        print("\n  La trace est journalisable telle quelle — elle ne porte "
              "ni le prompt ni la réponse :")
        print("  " + json.dumps(record.to_dict(), ensure_ascii=False)[:160] + "…")

        # ---------------------------------------------------------------
        # MEASURE — la mesure, inchangée depuis la 2.0.0
        # ---------------------------------------------------------------
        print("\n--- MEASURE (réel) ---")
        resultat = record.result
        assert resultat is not None
        print(f"  décision             : {resultat.governance.decision}")
        print(f"  g_score              : {resultat.format_score('g_score')}")
        print(f"  version de mesure    : {resultat.audit.measurement_version}")
        print(f"  contrat de fil       : {resultat.contract_version}")
        print(f"  provenance du compte : {resultat.token_count_source} "
              f"({resultat.token_count_unit})")
        print(f"  signaux mesurés      : {resultat.measured_signals}")
        print(f"  signaux non mesurés  : {resultat.unmeasured_signals}")
        print(f"  champs inconnus      : {resultat.unknown_fields}")
        print(f"  avertissements       : {resultat.parse_warnings}")

        # ---------------------------------------------------------------
        # VERIFY — trois questions distinctes
        # ---------------------------------------------------------------
        print("\n--- VERIFY 1/3 : authenticité d'émission (réel, non facturé) ---")
        verdict = client.verify(record.request_id or "")
        print(f"  valid                : {verdict.valid}")
        print(f"  empreinte recalculée : {verdict.payload_hash_match}")
        print(f"  signature JWS        : {verdict.signature_valid}")
        print(f"  clé de signature     : {verdict.key_id}")
        print("  Ce que cela établit  : l'enregistrement a bien été émis par "
              "cette plateforme et n'a pas été altéré.")
        print("  Ce que cela n'établit PAS : que la réponse de l'IA soit vraie.")

        print("\n--- VERIFY 2/3 : certificat d'audit (palier 03) ---")
        certificat = client.verify_audit_certificate("AT-2026-0001")
        print(f"  valid                : {certificat.valid}  "
              "<- None, et c'est correct : aucun sha256 fourni")
        print(f"  vérification faite ? : {certificat.verification_performed}")
        print(f"  dit par le serveur   : {certificat.verification}")

    print("\n--- VERIFY 3/3 : intégrité d'une archive Evidence (vérificateur "
          "INDÉPENDANT) ---")
    try:
        integrite = verify_evidence_archive("une-archive-inexistante.zip")
    except EvidenceVerifierUnavailable as exc:
        print("  Vérificateur absent — et donc AUCUN verdict :")
        print(f"  {exc}")
    else:
        print(f"  code de sortie       : {integrite.exit_code}")
        print(f"  issue                : {integrite.outcome}")
        print(f"  vérification faite ? : {integrite.verification_performed}")
        print(f"  verdict              : {integrite.passed}")

    print("\n" + "=" * 70)
    print("Les quatre étapes sont passées. Les limites qu'elles portent sont "
          "dans KNOWN_LIMITATIONS.md.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
