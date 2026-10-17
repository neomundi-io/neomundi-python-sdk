"""Erreurs HTTP, transport, réponses invalides.

Couvre les points 8, 9, 10 et 11 de la Phase C.
"""

from __future__ import annotations

import httpx
import pytest

from conftest import (
    TEST_BASE_URL,
    json_responder,
    load_fixture,
    make_client,
    raising_responder,
)
from neomundi import (
    APIError,
    AuthenticationError,
    InvalidResponseError,
    NetworkError,
    PaymentRequiredError,
    PayloadTooLargeError,
    RateLimitError,
    ServerError,
    TimeoutError,
    TransportError,
    ValidationError,
)


def _call(handler, **kwargs):
    with make_client(handler, **kwargs) as client:
        return client.govern(token_count=1, latency_ms=1.0)


def _error_fixture(name):
    return load_fixture(f"errors/{name}")


# ---------------------------------------------------------------------
# 8. Codes HTTP
# ---------------------------------------------------------------------

def test_401_leve_AuthenticationError():
    with pytest.raises(AuthenticationError) as exc:
        _call(json_responder(_error_fixture("e401.json"), 401))
    e = exc.value
    assert e.status_code == 401
    assert e.error_code == "unauthorized"
    assert e.request_id == "err-401-0000"
    assert "revoked" in e.detail


def test_402_leve_PaymentRequiredError_et_conserve_le_detail():
    """Le backend couvre TROIS causes sous ce statut ; le SDK ne devine
    pas laquelle, il conserve ce que le serveur a dit."""
    with pytest.raises(PaymentRequiredError) as exc:
        _call(json_responder(_error_fixture("e402.json"), 402))
    assert exc.value.status_code == 402
    assert "TRIAL quota" in exc.value.detail
    assert isinstance(exc.value.body, dict)


def test_413_est_lu_malgre_ses_deux_cles_seulement():
    """Le 413 ne porte ni `request_id` ni `timestamp` : le middleware qui
    les pose n'a pas encore tourné. Un parsing qui exigerait quatre clés
    échouerait là où il doit informer."""
    with pytest.raises(PayloadTooLargeError) as exc:
        _call(json_responder(_error_fixture("e413.json"), 413))
    e = exc.value
    assert e.status_code == 413
    assert e.error_code == "payload_too_large"
    assert e.server_timestamp is None
    assert e.request_id is None


def test_413_recupere_le_request_id_depuis_l_entete():
    """L'en-tête `X-Request-ID` est posé sur TOUTE réponse : c'est une
    information réelle, pas une invention."""
    handler = json_responder(
        _error_fixture("e413.json"), 413, headers={"X-Request-ID": "hdr-413"}
    )
    with pytest.raises(PayloadTooLargeError) as exc:
        _call(handler)
    assert exc.value.request_id == "hdr-413"


def test_422_expose_les_erreurs_de_champ_normalisees():
    with pytest.raises(ValidationError) as exc:
        _call(json_responder(_error_fixture("e422.json"), 422))
    e = exc.value
    assert e.status_code == 422
    assert len(e.field_errors) == 2
    assert e.field_errors[0]["field"] == "body.raw_metrics.token_count"
    assert e.field_errors[1]["type"] == "missing"
    # Le brut est conservé.
    assert isinstance(e.detail, list)
    # Et le message agrège les champs, sans les perdre.
    assert "token_count" in str(e)


def test_429_expose_retry_after_et_les_entetes_de_limite():
    handler = json_responder(
        _error_fixture("e429.json"),
        429,
        headers={
            "Retry-After": "42",
            "X-RateLimit-Limit": "60",
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": "1760000000",
        },
    )
    with pytest.raises(RateLimitError) as exc:
        _call(handler)
    e = exc.value
    assert e.retry_after == 42
    assert e.rate_limit == 60
    assert e.rate_limit_remaining == 0
    assert e.rate_limit_reset == 1760000000


def test_429_sans_retry_after_renvoie_none_jamais_zero():
    """Zéro signifierait « réessayez immédiatement » — une invention."""
    with pytest.raises(RateLimitError) as exc:
        _call(json_responder(_error_fixture("e429.json"), 429))
    assert exc.value.retry_after is None


def test_429_avec_un_retry_after_illisible_renvoie_none():
    handler = json_responder(
        _error_fixture("e429.json"), 429, headers={"Retry-After": "bientot"}
    )
    with pytest.raises(RateLimitError) as exc:
        _call(handler)
    assert exc.value.retry_after is None


def test_500_leve_ServerError():
    with pytest.raises(ServerError) as exc:
        _call(json_responder(_error_fixture("e500.json"), 500))
    assert exc.value.status_code == 500


def test_503_leve_ServerError():
    with pytest.raises(ServerError) as exc:
        _call(json_responder(_error_fixture("e503.json"), 503))
    assert exc.value.status_code == 503


def test_un_5xx_non_repertorie_reste_un_ServerError():
    with pytest.raises(ServerError) as exc:
        _call(json_responder({"error": "bad_gateway", "detail": "upstream"}, 502))
    assert exc.value.status_code == 502


def test_un_statut_d_erreur_inconnu_ne_se_perd_pas_dans_une_classe_trompeuse():
    with pytest.raises(APIError) as exc:
        _call(json_responder({"error": "teapot", "detail": "I am a teapot"}, 418))
    assert exc.value.status_code == 418
    assert not isinstance(exc.value, ServerError)


def test_un_corps_d_erreur_non_json_est_conserve_en_texte():
    def handler(_request):
        return httpx.Response(500, text="<html>502 Bad Gateway</html>")

    with pytest.raises(ServerError) as exc:
        _call(handler)
    assert "Bad Gateway" in exc.value.body


def test_un_corps_d_erreur_vide_ne_fait_pas_echouer_le_parsing():
    def handler(_request):
        return httpx.Response(500)

    with pytest.raises(ServerError) as exc:
        _call(handler)
    assert exc.value.status_code == 500
    assert exc.value.error_code is None


def test_toutes_les_erreurs_api_descendent_de_APIError():
    for cls in (
        AuthenticationError,
        PaymentRequiredError,
        PayloadTooLargeError,
        ValidationError,
        RateLimitError,
        ServerError,
    ):
        assert issubclass(cls, APIError)


# ---------------------------------------------------------------------
# 9. Timeout · 10. Erreur réseau
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "exc",
    [
        httpx.ReadTimeout("lecture trop longue"),
        httpx.ConnectTimeout("connexion trop longue"),
        httpx.WriteTimeout("ecriture trop longue"),
        httpx.PoolTimeout("pool sature"),
    ],
)
def test_les_timeouts_levent_TimeoutError(exc):
    with pytest.raises(TimeoutError) as caught:
        _call(raising_responder(exc))
    assert "ne pas la rejouer" in str(caught.value)


@pytest.mark.parametrize(
    "exc",
    [
        httpx.ConnectError("dns"),
        httpx.ReadError("socket"),
        httpx.RemoteProtocolError("protocole"),
    ],
)
def test_les_pannes_reseau_levent_NetworkError(exc):
    with pytest.raises(NetworkError):
        _call(raising_responder(exc))


def test_timeout_et_network_descendent_de_TransportError():
    assert issubclass(TimeoutError, TransportError)
    assert issubclass(NetworkError, TransportError)


def test_un_timeout_n_est_pas_une_APIError():
    """Distinction de fond : aucune réponse n'a été obtenue, donc la
    requête a peut-être été exécutée et facturée."""
    assert not issubclass(TimeoutError, APIError)


# ---------------------------------------------------------------------
# 11. Réponse JSON invalide
# ---------------------------------------------------------------------

def test_un_corps_2xx_non_json_leve_InvalidResponseError():
    def handler(_request):
        return httpx.Response(200, text="pas du json")

    with pytest.raises(InvalidResponseError) as exc:
        _call(handler)
    assert exc.value.status_code == 200
    assert "pas du json" in exc.value.body


def test_un_corps_2xx_vide_leve_InvalidResponseError():
    def handler(_request):
        return httpx.Response(200, text="")

    with pytest.raises(InvalidResponseError):
        _call(handler)


def test_un_json_2xx_qui_n_est_pas_un_objet_leve():
    with pytest.raises(InvalidResponseError):
        _call(json_responder([1, 2, 3]))


def test_une_reponse_invalide_n_est_jamais_rendue_comme_un_resultat_vide():
    """Rendre un résultat aux champs tous nuls serait indistinguable d'une
    mesure non effectuée — exactement la confusion que ce SDK empêche."""

    def handler(_request):
        return httpx.Response(200, json={"request_id": "x"})

    with pytest.raises(InvalidResponseError):
        _call(handler)


def test_une_reponse_invalide_conserve_le_request_id_de_l_entete():
    def handler(_request):
        return httpx.Response(
            200, text="boom", headers={"X-Request-ID": "hdr-inv"}
        )

    with pytest.raises(InvalidResponseError) as exc:
        _call(handler)
    assert exc.value.request_id == "hdr-inv"


# ---------------------------------------------------------------------
# Le corps brut n'est jamais perdu
# ---------------------------------------------------------------------

def test_le_corps_serveur_est_toujours_conserve():
    payload = _error_fixture("e401.json")
    with pytest.raises(AuthenticationError) as exc:
        _call(json_responder(payload, 401))
    assert exc.value.body == payload


def test_les_entetes_de_reponse_sont_conserves():
    handler = json_responder(
        _error_fixture("e500.json"), 500, headers={"X-Process-Time": "0.0042"}
    )
    with pytest.raises(ServerError) as exc:
        _call(handler)
    assert exc.value.headers.get("x-process-time") == "0.0042"
