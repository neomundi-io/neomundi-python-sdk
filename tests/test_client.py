"""Construction du client, authentification, requête, ressources.

Couvre les points 1, 2, 3 et 13 de la Phase C.
"""

from __future__ import annotations

import httpx
import pytest

import neomundi
from conftest import (
    TEST_API_KEY,
    TEST_BASE_URL,
    json_responder,
    make_client,
)
from neomundi import ConfigurationError, NeoMundiClient, RetryPolicy


# ---------------------------------------------------------------------
# 1. Création du client
# ---------------------------------------------------------------------

def test_client_construit_avec_des_parametres_valides():
    with NeoMundiClient(api_key=TEST_API_KEY, base_url=TEST_BASE_URL) as client:
        assert client.base_url == TEST_BASE_URL


@pytest.mark.parametrize("prefix", ["ct_live_", "ct_test_", "ct_trial_"])
def test_les_trois_prefixes_du_serveur_sont_acceptes(prefix):
    """Relevé de `app/auth/api_key.py:83-88`."""
    client = NeoMundiClient(api_key=prefix + "x" * 20, base_url=TEST_BASE_URL)
    client.close()


@pytest.mark.parametrize(
    "bad_key",
    ["", "   ", "sk-proj-abc", "ct_unknown_abc", "abc123"],
)
def test_une_cle_de_format_invalide_est_refusee_avant_tout_reseau(bad_key):
    """Lever ici évite de consommer un appel, et surtout un quota."""
    with pytest.raises(ConfigurationError):
        NeoMundiClient(api_key=bad_key, base_url=TEST_BASE_URL)


def test_une_cle_non_textuelle_est_refusee():
    with pytest.raises(ConfigurationError):
        NeoMundiClient(api_key=None, base_url=TEST_BASE_URL)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_url", ["", "   ", "example.invalid", "ftp://x.y"])
def test_une_base_url_invalide_est_refusee(bad_url):
    with pytest.raises(ConfigurationError):
        NeoMundiClient(api_key=TEST_API_KEY, base_url=bad_url)


def test_aucune_base_url_par_defaut_n_est_supposee():
    """Le SDK ne doit jamais choisir un environnement à la place de l'appelant."""
    with pytest.raises(TypeError):
        NeoMundiClient(api_key=TEST_API_KEY)  # type: ignore[call-arg]


@pytest.mark.parametrize("bad_timeout", [0, -1, "30", True])
def test_un_timeout_invalide_est_refuse(bad_timeout):
    with pytest.raises(ConfigurationError):
        NeoMundiClient(
            api_key=TEST_API_KEY, base_url=TEST_BASE_URL, timeout=bad_timeout
        )


def test_un_timeout_numerique_est_accepte():
    client = NeoMundiClient(api_key=TEST_API_KEY, base_url=TEST_BASE_URL, timeout=5)
    client.close()


def test_retry_doit_etre_une_politique_explicite():
    """Pas de `retry=True` : activer des réessais est une décision."""
    with pytest.raises(ConfigurationError):
        NeoMundiClient(
            api_key=TEST_API_KEY, base_url=TEST_BASE_URL, retry=True  # type: ignore[arg-type]
        )


def test_le_retry_est_desactive_par_defaut():
    assert neomundi.NO_RETRY.max_attempts == 1
    assert neomundi.NO_RETRY.enabled is False
    assert RetryPolicy().enabled is False


# ---------------------------------------------------------------------
# 2. Authentification · 3. Requête valide
# ---------------------------------------------------------------------

def test_l_entete_x_api_key_est_envoye(full_payload, recorder):
    with make_client(json_responder(full_payload), recorder=recorder) as client:
        client.govern(token_count=128, latency_ms=842.0)
    assert recorder.last.headers["x-api-key"] == TEST_API_KEY


def test_la_requete_cible_la_bonne_route_et_la_bonne_methode(full_payload, recorder):
    with make_client(json_responder(full_payload), recorder=recorder) as client:
        client.govern(token_count=128, latency_ms=842.0)
    assert recorder.last.method == "POST"
    assert recorder.last.url.path == "/v1/govern"
    assert neomundi.GOVERN_PATH == "/v1/govern"


def test_le_user_agent_identifie_le_sdk_et_sa_version(full_payload, recorder):
    with make_client(json_responder(full_payload), recorder=recorder) as client:
        client.govern(token_count=1, latency_ms=1.0)
    ua = recorder.last.headers["user-agent"]
    assert "neomundi-python-sdk" in ua
    assert neomundi.__version__ in ua


def test_le_corps_reprend_la_structure_de_GovernRequest(full_payload, recorder):
    with make_client(json_responder(full_payload), recorder=recorder) as client:
        client.govern(
            token_count=128,
            latency_ms=842.0,
            cost=0.0031,
            semantic_risk=0.0,
            prompt_length=480,
            response_length=1200,
            model_name="gpt-4o-mini",
            llm_response="La capitale de la France est Paris.",
            llm_prompt="Quelle est la capitale de la France ?",
        )
    body = recorder.last_json()
    assert body["source_type"] == "llm"
    assert body["mode"] == "OBS"
    assert body["llm_response"].startswith("La capitale")
    assert body["llm_prompt"].startswith("Quelle est")
    rm = body["raw_metrics"]
    assert rm["token_count"] == 128
    assert rm["latency_ms"] == 842.0
    assert rm["cost"] == 0.0031
    assert rm["prompt_length"] == 480
    assert rm["response_length"] == 1200
    assert rm["model_name"] == "gpt-4o-mini"


def test_les_champs_non_fournis_ne_sont_pas_envoyes(full_payload, recorder):
    """Le serveur applique SES valeurs par défaut documentées.

    Le SDK ne décide pas qu'un coût absent vaut 0.0 : envoyer un 0.0 serait
    affirmer une mesure de coût que l'appelant n'a pas faite.
    """
    with make_client(json_responder(full_payload), recorder=recorder) as client:
        client.govern(token_count=10, latency_ms=20.0)
    rm = recorder.last_json()["raw_metrics"]
    assert set(rm) == {"token_count", "latency_ms"}
    assert "cost" not in rm
    assert "semantic_risk" not in rm
    body = recorder.last_json()
    assert "llm_response" not in body
    assert "metadata" not in body


def test_un_zero_explicite_est_transmis(full_payload, recorder):
    """`cost=0.0` est une mesure de l'appelant : elle doit partir."""
    with make_client(json_responder(full_payload), recorder=recorder) as client:
        client.govern(token_count=10, latency_ms=20.0, cost=0.0, semantic_risk=0.0)
    rm = recorder.last_json()["raw_metrics"]
    assert rm["cost"] == 0.0
    assert rm["semantic_risk"] == 0.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"token_count": -1, "latency_ms": 1.0},
        {"token_count": 1.5, "latency_ms": 1.0},
        {"token_count": True, "latency_ms": 1.0},
        {"token_count": 1, "latency_ms": -1.0},
        {"token_count": 1, "latency_ms": "fast"},
        {"token_count": 1, "latency_ms": 1.0, "cost": -0.1},
        {"token_count": 1, "latency_ms": 1.0, "semantic_risk": 1.5},
        {"token_count": 1, "latency_ms": 1.0, "prompt_length": -5},
        {"token_count": 1, "latency_ms": 1.0, "model_name": ""},
        {"token_count": 1, "latency_ms": 1.0, "llm_response": 42},
    ],
)
def test_les_parametres_invalides_sont_refuses_avant_le_reseau(
    full_payload, recorder, kwargs
):
    with make_client(json_responder(full_payload), recorder=recorder) as client:
        with pytest.raises(ConfigurationError):
            client.govern(**kwargs)
    assert recorder.count == 0, "aucune requête ne doit partir"


def test_documents_et_rag_context_sont_transmis(full_payload, recorder):
    with make_client(json_responder(full_payload), recorder=recorder) as client:
        client.govern(
            token_count=1,
            latency_ms=1.0,
            rag_context=["passage A", "passage B"],
            documents=[{"title": "Doc", "text": "contenu"}],
            metadata={"trace": "abc"},
        )
    body = recorder.last_json()
    assert body["rag_context"] == ["passage A", "passage B"]
    assert body["documents"] == [{"title": "Doc", "text": "contenu"}]
    assert body["metadata"] == {"trace": "abc"}


def test_extra_permet_d_envoyer_un_champ_futur(full_payload, recorder):
    """Compatibilité ascendante : exploiter un champ serveur récent sans
    attendre une version du SDK."""
    with make_client(json_responder(full_payload), recorder=recorder) as client:
        client.govern(
            token_count=1, latency_ms=1.0, extra={"champ_futur": {"a": 1}}
        )
    assert recorder.last_json()["champ_futur"] == {"a": 1}


def test_build_request_body_est_une_fonction_pure():
    body = NeoMundiClient.build_request_body(token_count=5, latency_ms=10.0)
    assert body == {
        "source_type": "llm",
        "mode": "OBS",
        "raw_metrics": {"token_count": 5, "latency_ms": 10.0},
    }


# ---------------------------------------------------------------------
# 13. Fermeture des ressources
# ---------------------------------------------------------------------

def test_le_gestionnaire_de_contexte_ferme_le_client(full_payload):
    client = make_client(json_responder(full_payload))
    with client:
        client.govern(token_count=1, latency_ms=1.0)
    assert client.is_closed is True


def test_close_est_idempotent(full_payload):
    client = make_client(json_responder(full_payload))
    client.close()
    client.close()
    assert client.is_closed is True


def test_un_client_httpx_injecte_n_est_pas_ferme(full_payload):
    """On ne ferme pas ce qu'on n'a pas créé.

    Un appelant qui fournit son propre `httpx.Client` (pool partagé,
    configuration d'entreprise) ne doit pas le voir fermé par le SDK.
    """
    transport = httpx.MockTransport(json_responder(full_payload))
    external = httpx.Client(base_url=TEST_BASE_URL, transport=transport)
    client = NeoMundiClient(
        api_key=TEST_API_KEY, base_url=TEST_BASE_URL, http_client=external
    )
    with client:
        client.govern(token_count=1, latency_ms=1.0)
    assert external.is_closed is False
    external.close()


def test_le_contrat_api_declare_le_commit_de_reference():
    """Aucun OpenAPI figé n'existe : nommer le commit est le seul moyen de
    dire à quoi ce SDK correspond."""
    contract = neomundi.API_CONTRACT
    assert contract["backend_commit"] == "68d6057cf620e430e6488da3cfcec9c471c75ed6"
    assert contract["measurement_version"] == "3.3.0"
    assert contract["route"] == "POST /v1/govern"
    assert contract["openapi_frozen"] is False
