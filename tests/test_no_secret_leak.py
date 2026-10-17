"""Aucune clé API ne doit apparaître ailleurs que dans l'en-tête HTTP.

Point 14 de la Phase C. La clé de test est volontairement reconnaissable
pour qu'une fuite soit détectable par simple recherche de sous-chaîne.
"""

from __future__ import annotations

import logging

import httpx
import pytest

from conftest import (
    TEST_BASE_URL,
    json_responder,
    load_fixture,
    make_client,
    raising_responder,
)
from neomundi import NeoMundiClient

#: Clé factice au format valide, reconnaissable, et assez longue pour que
#: le masquage soit observable.
SECRET = "ct_live_SECRET_NE_DOIT_PAS_FUIR_9999"


def _err(name):
    return load_fixture(f"errors/{name}")


def test_le_repr_du_client_ne_contient_pas_la_cle():
    client = NeoMundiClient(api_key=SECRET, base_url=TEST_BASE_URL)
    text = repr(client)
    client.close()
    assert SECRET not in text
    assert "NE_DOIT_PAS_FUIR" not in text
    # Le préfixe et les 4 derniers caractères suffisent à distinguer deux
    # clés sans en révéler aucune.
    assert "ct_live_***9999" in text


def test_le_str_du_client_ne_contient_pas_la_cle():
    client = NeoMundiClient(api_key=SECRET, base_url=TEST_BASE_URL)
    text = str(client)
    client.close()
    assert SECRET not in text


def test_une_cle_courte_est_masquee_sans_fuite_partielle():
    short = "ct_test_abc"
    client = NeoMundiClient(api_key=short, base_url=TEST_BASE_URL)
    text = repr(client)
    client.close()
    assert "abc" not in text.replace("ct_test_", "")


@pytest.mark.parametrize("status", [401, 402, 413, 422, 429, 500, 503])
def test_aucun_message_d_erreur_ne_contient_la_cle(status):
    handler = json_responder({"error": "x", "detail": "y"}, status)
    with make_client(handler, api_key=SECRET) as client:
        with pytest.raises(Exception) as exc:
            client.govern(token_count=1, latency_ms=1.0)
    assert SECRET not in str(exc.value)
    assert SECRET not in repr(exc.value)
    body = getattr(exc.value, "body", None)
    assert SECRET not in str(body)


def test_le_message_de_timeout_ne_contient_pas_la_cle():
    handler = raising_responder(httpx.ReadTimeout("trop long"))
    with make_client(handler, api_key=SECRET) as client:
        with pytest.raises(Exception) as exc:
            client.govern(token_count=1, latency_ms=1.0)
    assert SECRET not in str(exc.value)


def test_le_message_de_reponse_invalide_ne_contient_pas_la_cle():
    def handler(_request):
        return httpx.Response(200, text="pas du json")

    with make_client(handler, api_key=SECRET) as client:
        with pytest.raises(Exception) as exc:
            client.govern(token_count=1, latency_ms=1.0)
    assert SECRET not in str(exc.value)


def test_le_sdk_ne_journalise_rien_qui_contienne_la_cle(caplog, full_payload):
    """Le SDK n'émet aucun journal du tout à la v0.1 ; ce test fige cette
    propriété, afin qu'un futur ajout de journalisation ne fasse pas fuir
    la clé par accident."""
    with caplog.at_level(logging.DEBUG):
        with make_client(json_responder(full_payload), api_key=SECRET) as client:
            client.govern(token_count=1, latency_ms=1.0)
    text = "\n".join(record.getMessage() for record in caplog.records)
    assert SECRET not in text


def test_le_resultat_ne_contient_pas_la_cle(full_payload):
    with make_client(json_responder(full_payload), api_key=SECRET) as client:
        result = client.govern(token_count=1, latency_ms=1.0)
    assert SECRET not in repr(result)
    assert SECRET not in str(result.to_dict())


def test_le_corps_de_requete_ne_contient_pas_la_cle(full_payload, recorder):
    """La clé voyage dans l'en-tête, jamais dans le corps."""
    with make_client(
        json_responder(full_payload), api_key=SECRET, recorder=recorder
    ) as client:
        client.govern(
            token_count=1, latency_ms=1.0, llm_response="texte", llm_prompt="q"
        )
    body = recorder.last.content.decode("utf-8")
    assert SECRET not in body


def test_la_cle_est_bien_dans_l_entete_et_nulle_part_ailleurs(
    full_payload, recorder
):
    with make_client(
        json_responder(full_payload), api_key=SECRET, recorder=recorder
    ) as client:
        client.govern(token_count=1, latency_ms=1.0)
    request = recorder.last
    assert request.headers["x-api-key"] == SECRET
    assert SECRET not in str(request.url)
    assert SECRET not in request.content.decode("utf-8")


def test_aucune_vraie_cle_dans_les_sources_ni_les_fixtures():
    """Garde-fou de dépôt : aucune clé `ct_live_` plausible ne doit être
    committée. Les clés de test sont `ct_test_000…` ou contiennent un
    marqueur explicite."""
    import re
    from pathlib import Path

    root = Path(__file__).parent.parent
    pattern = re.compile(r"ct_(live|test|trial)_[A-Za-z0-9_\-]{8,}")
    allowed_markers = ("0000", "SECRET_NE_DOIT_PAS_FUIR", "xxxx", "XXXX")

    offenders = []
    for path in list(root.rglob("*.py")) + list(root.rglob("*.json")) + list(
        root.rglob("*.md")
    ):
        if ".venv" in path.parts or "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in pattern.findall(text):
            for found in pattern.finditer(text):
                token = found.group(0)
                if not any(marker in token for marker in allowed_markers):
                    offenders.append(f"{path.name}: {token[:24]}…")
    assert not offenders, f"Clés suspectes trouvées : {sorted(set(offenders))}"
