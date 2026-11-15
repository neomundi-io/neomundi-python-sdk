"""Étape VERIFY — trois questions distinctes, trois verdicts distincts.

Ce fichier verrouille les confusions qui coûtent le plus cher :

* `valid: null` n'est pas `valid: false` — « rien n'a été vérifié » n'est
  pas « la vérification a échoué » ;
* un 404 de vérification n'est pas une erreur d'intégration : c'est
  « aucun enregistrement de ce genre » ;
* un vérificateur **absent** ne rend aucun verdict ;
* les codes 3 et 4 du vérificateur Evidence déclarent qu'**aucune
  vérification n'a eu lieu**, là où 0 et 1 en rapportent une.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import httpx
import pytest

from conftest import RequestRecorder, make_client
from neomundi import (
    APIError,
    ConfigurationError,
    EvidenceVerifierUnavailable,
    verify_evidence_archive,
)
from neomundi import verification as V

REQUEST_ID = "11111111-2222-3333-4444-555555555555"


def _handler(payload, status=200, path_attendu=None, recorder=None):
    def _h(request: httpx.Request) -> httpx.Response:
        if recorder is not None:
            recorder.requests.append(request)
        if path_attendu is not None:
            assert request.url.path == path_attendu, request.url.path
        return httpx.Response(status, json=payload)

    return _h


# ---------------------------------------------------------------------
# GET /v1/rgc/verify/{request_id}
# ---------------------------------------------------------------------

def test_un_contrat_rgc_valide_est_rapporte_avec_ses_deux_controles():
    """Le serveur recalcule l'empreinte **et** vérifie la signature. Les
    deux sous-verdicts sont exposés : un `valid: true` dont on ne peut pas
    dire ce qui a été vérifié n'est pas une preuve."""
    recorder = RequestRecorder()
    client = make_client(
        _handler(
            {
                "valid": True,
                "request_id": REQUEST_ID,
                "payload_hash_match": True,
                "signature_valid": True,
                "key_id": "neomundi-rgc-2026-01",
                "verified_at": "2026-11-15T10:00:00+00:00",
            },
            path_attendu=f"/v1/rgc/verify/{REQUEST_ID}",
            recorder=recorder,
        )
    )
    with client:
        verdict = client.verify(REQUEST_ID)

    assert verdict.valid is True
    assert verdict.verification_performed is True
    assert verdict.payload_hash_match is True
    assert verdict.signature_valid is True
    assert verdict.key_id == "neomundi-rgc-2026-01"
    assert verdict.http_status == 200
    assert recorder.last.method == "GET"
    # Une requête GET de vérification ne porte aucun corps.
    assert not recorder.last.content


def test_une_signature_invalide_est_un_echec_de_verification():
    client = make_client(
        _handler(
            {
                "valid": False,
                "request_id": REQUEST_ID,
                "payload_hash_match": True,
                "signature_valid": False,
                "key_id": "neomundi-rgc-2026-01",
            }
        )
    )
    with client:
        verdict = client.verify(REQUEST_ID)
    assert verdict.valid is False
    assert verdict.verification_performed is True
    assert verdict.signature_valid is False


def test_aucun_contrat_emis_n_est_pas_un_echec_de_verification():
    """🔴 La distinction centrale de cette étape.

    404 = aucun contrat RGC émis pour cette observation. Il n'y a rien à
    vérifier, donc `valid is None`. Le rendre `False` ferait passer
    « jamais signé » pour « signature invalide » — et l'émission d'un
    contrat est un appel distinct, réservé au palier TIER_03.
    """
    client = make_client(
        _handler(
            {
                "error": "not_found",
                "detail": "No RGC contract on record for this request_id.",
            },
            status=404,
        )
    )
    with client:
        verdict = client.verify(REQUEST_ID)

    assert verdict.valid is None
    assert verdict.verification_performed is False
    assert verdict.reason == "no_contract_on_record"
    assert verdict.http_status == 404


def test_le_journal_source_disparu_est_rapporte_tel_quel():
    """Le serveur répond `valid: false` avec un motif nommé : republié
    sans retouche, parce que la cause change la conduite à tenir."""
    client = make_client(
        _handler(
            {
                "valid": False,
                "request_id": REQUEST_ID,
                "reason": "source_governance_log_no_longer_available",
            }
        )
    )
    with client:
        verdict = client.verify(REQUEST_ID)
    assert verdict.valid is False
    assert verdict.reason == "source_governance_log_no_longer_available"


def test_un_500_de_verification_leve_toujours():
    """Seul le 404 est toléré. Un 500 reste une erreur, pas un verdict."""
    client = make_client(_handler({"error": "internal"}, status=500))
    with client:
        with pytest.raises(APIError):
            client.verify(REQUEST_ID)


def test_un_corps_illisible_ne_devient_pas_un_verdict():
    def _h(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>passerelle</html>")

    client = make_client(_h)
    with client:
        verdict = client.verify(REQUEST_ID)
    assert verdict.valid is None
    assert verdict.verification_performed is False
    assert verdict.reason == "response_not_an_object"


@pytest.mark.parametrize("valeur", ["", "   ", None, 7])
def test_un_request_id_invalide_est_refuse_avant_tout_reseau(valeur):
    recorder = RequestRecorder()
    client = make_client(_handler({}, recorder=recorder))
    with client:
        with pytest.raises(ConfigurationError):
            client.verify(valeur)
    assert recorder.count == 0


# ---------------------------------------------------------------------
# GET /v1/audit/verify/{audit_trail_id}
# ---------------------------------------------------------------------

def test_sans_sha256_la_route_d_audit_ne_verifie_rien():
    """🔴 Le piège que la route elle-même a fermé en 2026.

    Aucune empreinte n'est conservée à l'émission : sans celle imprimée
    sur le certificat, la route recalcule et dit, par `valid: null`, que
    rien n'a été vérifié. Un SDK qui lirait ce `null` comme un succès
    annoncerait une vérification inexistante.
    """
    client = make_client(
        _handler(
            {
                "valid": None,
                "verification": "no sha256 supplied: pass ?sha256=...",
                "record_found": True,
                "audit_trail_id": "AT-2026-0001",
                "request_id": REQUEST_ID,
                "sha256": "a" * 64,
                "issuer": "neomundi-controltower-api",
            },
            path_attendu="/v1/audit/verify/AT-2026-0001",
        )
    )
    with client:
        verdict = client.verify_audit_certificate("AT-2026-0001")

    assert verdict.valid is None
    assert verdict.verification_performed is False
    assert verdict.record_found is True
    assert verdict.sha256 == "a" * 64
    assert verdict.issuer == "neomundi-controltower-api"


def test_avec_sha256_la_route_d_audit_verifie_vraiment():
    recorder = RequestRecorder()
    client = make_client(
        _handler(
            {
                "valid": True,
                "verification": "the supplied sha256 matches the stored observation",
                "record_found": True,
                "audit_trail_id": "AT-2026-0001",
                "sha256": "b" * 64,
            },
            recorder=recorder,
        )
    )
    with client:
        verdict = client.verify_audit_certificate("AT-2026-0001", sha256="b" * 64)

    assert verdict.valid is True
    assert verdict.verification_performed is True
    assert recorder.last.url.params["sha256"] == "b" * 64


def test_une_empreinte_qui_ne_correspond_pas_est_un_echec():
    client = make_client(
        _handler(
            {
                "valid": False,
                "verification": "the supplied sha256 does NOT match the stored observation",
                "record_found": True,
            }
        )
    )
    with client:
        verdict = client.verify_audit_certificate("AT-2026-0001", sha256="c" * 64)
    assert verdict.valid is False
    assert verdict.verification_performed is True


def test_un_certificat_inconnu_rend_record_found_faux():
    client = make_client(
        _handler(
            {"error": "not_found", "detail": "audit_trail_id=X not found."},
            status=404,
        )
    )
    with client:
        verdict = client.verify_audit_certificate("X")
    assert verdict.valid is None
    assert verdict.record_found is False
    assert verdict.http_status == 404
    # Le `detail` du serveur est conservé : il nomme les deux causes
    # possibles (document expiré, ou identifiant invalide).
    assert verdict.verification and "not found" in verdict.verification


@pytest.mark.parametrize("sha", ["", "  "])
def test_un_sha256_vide_est_refuse(sha):
    recorder = RequestRecorder()
    client = make_client(_handler({}, recorder=recorder))
    with client:
        with pytest.raises(ConfigurationError):
            client.verify_audit_certificate("AT-1", sha256=sha)
    assert recorder.count == 0


# ---------------------------------------------------------------------
# Le vérificateur Evidence indépendant
# ---------------------------------------------------------------------

def test_un_verificateur_absent_ne_rend_aucun_verdict(monkeypatch):
    """Absence d'outil ≠ archive invalide ≠ archive valide."""
    monkeypatch.setattr(V.shutil, "which", lambda _name: None)
    with pytest.raises(EvidenceVerifierUnavailable) as exc:
        verify_evidence_archive("archive.zip")
    message = str(exc.value)
    assert "neomundi-evidence-verify" in message
    assert "ne vérifie pas lui-même" in message


@pytest.mark.parametrize(
    ("code", "attendu", "effectuee", "passe"),
    [
        (0, "verification_passed", True, True),
        (1, "verification_failed", True, False),
        (2, "verification_incomplete_missing_dependency", True, None),
        (3, "engine_unavailable_no_verification_performed", False, None),
        (4, "request_refused_no_verification_performed", False, None),
    ],
)
def test_les_cinq_codes_de_sortie_sont_republies_sans_traduction(
    monkeypatch, code, attendu, effectuee, passe
):
    """Les codes 3 et 4 existent précisément pour que « rien n'a échoué »
    et « rien n'a tourné » ne rendent pas le même verdict."""
    monkeypatch.setattr(V.shutil, "which", lambda _n: "/usr/bin/neomundi-evidence")

    def _run(command, **_kwargs):
        return subprocess.CompletedProcess(command, code, stdout="", stderr="")

    monkeypatch.setattr(V.subprocess, "run", _run)
    verdict = verify_evidence_archive("archive.zip")

    assert verdict.exit_code == code
    assert verdict.outcome == attendu
    assert verdict.verification_performed is effectuee
    assert verdict.passed is passe


def test_un_code_de_sortie_inconnu_n_est_pas_absorbe(monkeypatch):
    monkeypatch.setattr(V.shutil, "which", lambda _n: "/usr/bin/neomundi-evidence")
    monkeypatch.setattr(
        V.subprocess,
        "run",
        lambda command, **_k: subprocess.CompletedProcess(command, 99, "", ""),
    )
    verdict = verify_evidence_archive("archive.zip")
    assert verdict.outcome == "unknown_exit_code_99"
    assert verdict.passed is None


def test_le_rapport_json_du_verificateur_est_conserve(monkeypatch):
    monkeypatch.setattr(V.shutil, "which", lambda _n: "/usr/bin/neomundi-evidence")
    monkeypatch.setattr(
        V.subprocess,
        "run",
        lambda command, **_k: subprocess.CompletedProcess(
            command, 0, '{"archive_sha256": "deadbeef", "checks": 22}', ""
        ),
    )
    verdict = verify_evidence_archive("archive.zip")
    assert verdict.report == {"archive_sha256": "deadbeef", "checks": 22}


def test_une_sortie_non_json_n_est_pas_fatale(monkeypatch):
    monkeypatch.setattr(V.shutil, "which", lambda _n: "/usr/bin/neomundi-evidence")
    monkeypatch.setattr(
        V.subprocess,
        "run",
        lambda command, **_k: subprocess.CompletedProcess(
            command, 0, "[neomundi-evidence] 22 controles OK", ""
        ),
    )
    verdict = verify_evidence_archive("archive.zip")
    assert verdict.report is None
    assert verdict.passed is True
    assert "22 controles OK" in verdict.stdout


def test_strict_est_transmis_au_verificateur(monkeypatch):
    """⚠ Sans `cryptography`, `--strict` fait sortir en code 2 :
    vérification *incomplète*, et non échouée."""
    vues = {}
    monkeypatch.setattr(V.shutil, "which", lambda _n: "/usr/bin/neomundi-evidence")

    def _run(command, **_kwargs):
        vues["command"] = command
        return subprocess.CompletedProcess(command, 2, "", "")

    monkeypatch.setattr(V.subprocess, "run", _run)
    verdict = verify_evidence_archive("a.zip", strict=True, extra_args=["--json"])

    assert vues["command"] == [
        "/usr/bin/neomundi-evidence",
        "verify",
        "a.zip",
        "--strict",
        "--json",
    ]
    assert verdict.passed is None
    assert verdict.verification_performed is True


def test_un_delai_depasse_n_est_pas_un_echec_de_verification(monkeypatch):
    monkeypatch.setattr(V.shutil, "which", lambda _n: "/usr/bin/neomundi-evidence")

    def _run(command, **_kwargs):
        raise subprocess.TimeoutExpired(command, 1.0)

    monkeypatch.setattr(V.subprocess, "run", _run)
    with pytest.raises(EvidenceVerifierUnavailable, match="Aucune"):
        verify_evidence_archive("a.zip", timeout=1.0)


def test_aucun_shell_n_est_employe(monkeypatch):
    """Un chemin d'archive est une donnée d'entrée : il ne doit jamais
    traverser un interpréteur de commandes."""
    vus = {}
    monkeypatch.setattr(V.shutil, "which", lambda _n: "/usr/bin/neomundi-evidence")

    def _run(command, **kwargs):
        vus.update(kwargs)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(V.subprocess, "run", _run)
    verify_evidence_archive("a.zip; rm -rf /")
    assert vus["shell"] is False


def test_aucune_cle_n_est_transmise_au_sous_processus(monkeypatch):
    """Le vérificateur est hors ligne et n'a besoin d'aucun secret.

    Les retirer évite qu'une clé se retrouve dans un journal d'erreur ou
    un rapport de plantage du programme appelé.
    """
    # Volontairement SANS préfixe de clé : la garde anti-fuite du dépôt
    # refuse tout littéral `ct_live_…`, et elle a raison de le faire.
    monkeypatch.setenv("NEOMUNDI_API_KEY", "valeur-sensible-du-magasin")
    monkeypatch.setenv("MISTRAL_API_KEY", "valeur-fournisseur-factice")
    monkeypatch.setenv("GITHUB_TOKEN", "jeton-github-factice")
    monkeypatch.setenv("PGPASSWORD", "mot-de-passe-factice")
    monkeypatch.setenv("CHEMIN_NEUTRE", "garde-moi")

    env = V._child_env()
    for interdit in ("NEOMUNDI_API_KEY", "MISTRAL_API_KEY", "GITHUB_TOKEN", "PGPASSWORD"):
        assert interdit not in env, interdit
    assert env["CHEMIN_NEUTRE"] == "garde-moi"
    assert "valeur-sensible-du-magasin" not in "".join(env.values())


@pytest.mark.parametrize("valeur", ["", "   ", None, 3])
def test_un_chemin_d_archive_invalide_est_refuse(valeur):
    with pytest.raises(ConfigurationError):
        verify_evidence_archive(valeur)


@pytest.mark.parametrize("valeur", [0, -1, "x", True])
def test_un_delai_invalide_est_refuse(valeur, monkeypatch):
    monkeypatch.setattr(V.shutil, "which", lambda _n: "/usr/bin/neomundi-evidence")
    with pytest.raises(ConfigurationError):
        verify_evidence_archive("a.zip", timeout=valeur)


def test_le_sous_processus_est_reellement_lance(tmp_path):
    """Un vrai programme, un vrai code de sortie.

    Les tests ci-dessus simulent `subprocess.run` : celui-ci éprouve que
    la commande est bien exécutée et que son code remonte intact.
    """
    if os.name == "nt":
        faux = tmp_path / "faux-verificateur.cmd"
        faux.write_text("@echo off\r\necho {\"ok\": true}\r\nexit /b 1\r\n", encoding="ascii")
    else:
        faux = tmp_path / "faux-verificateur.sh"
        faux.write_text('#!/bin/sh\necho \'{"ok": true}\'\nexit 1\n', encoding="ascii")
        faux.chmod(0o755)

    verdict = verify_evidence_archive("archive.zip", executable=str(faux))
    assert verdict.exit_code == 1
    assert verdict.outcome == "verification_failed"
    assert verdict.passed is False
    assert verdict.report == {"ok": True}
    assert verdict.command[1:] == ("verify", "archive.zip")


def test_un_executable_inexistant_ne_rend_aucun_verdict(tmp_path):
    absent = tmp_path / "ce-programme-n-existe-pas"
    with pytest.raises(EvidenceVerifierUnavailable):
        verify_evidence_archive("a.zip", executable=str(absent))


# ---------------------------------------------------------------------
# Les trois questions ne se confondent pas
# ---------------------------------------------------------------------

def test_le_module_distingue_integrite_authenticite_et_veracite():
    """La distinction est documentée **dans le code**, pas seulement dans
    un README qu'un intégrateur ne lira pas."""
    doc = V.__doc__ or ""
    assert "Intégrité" in doc
    assert "Authenticité" in doc
    assert "Véracité" in doc


def test_le_sdk_ne_reimplemente_aucune_verification():
    """Aucun calcul d'empreinte, aucune vérification de signature dans ce
    module : il appelle, il ne recalcule pas.

    C'est la règle que le gateway Evidence s'applique aussi, et qu'il
    mesure de son côté.
    """
    source = Path(V.__file__).read_text(encoding="utf-8")
    # Des *mentions* de JWS ou de sha256 sont attendues : le module
    # documente ce que le serveur et le vérificateur font. Ce qui est
    # interdit, c'est d'en importer les outils — c'est-à-dire d'être en
    # mesure de calculer un verdict soi-même.
    for interdit in (
        "import hashlib",
        "import zipfile",
        "import hmac",
        "import base64",
        "from cryptography",
        "import cryptography",
    ):
        assert interdit not in source, (
            f"`{interdit}` apparaît dans verification.py : ce module ne doit "
            "pas être en mesure de vérifier lui-même."
        )
    # Et aucune constante de verdict fabriquée : les verdicts viennent du
    # serveur ou du programme appelé.
    assert '"PASS"' not in source
    assert '"FAIL"' not in source


def test_les_chemins_de_verification_sont_ceux_du_backend():
    assert V.RGC_VERIFY_PATH == "/v1/rgc/verify/{request_id}"
    assert V.AUDIT_VERIFY_PATH == "/v1/audit/verify/{audit_trail_id}"
    assert V.EVIDENCE_COMMAND == "neomundi-evidence"
    assert set(V.EVIDENCE_EXIT_CODES) == {0, 1, 2, 3, 4}
