"""Aucun réessai non autorisé — point 15 de la Phase C.

`POST /v1/govern` n'est pas idempotent : chaque appel crée une
observation, débite un quota ou un portefeuille, écrit une ligne de
métrologie et écrase la référence `delta_g` du compte. Le compteur du
transport simulé est la preuve directe du nombre d'appels réellement
émis.
"""

from __future__ import annotations

import httpx
import pytest

from conftest import (
    json_responder,
    load_fixture,
    make_client,
    raising_responder,
    sequence_responder,
)
from neomundi import (
    NO_RETRY,
    RateLimitError,
    RetryPolicy,
    ServerError,
    TimeoutError,
)


def _err(name):
    return load_fixture(f"errors/{name}")


# ---------------------------------------------------------------------
# Par défaut : exactement une tentative, quel que soit l'échec
# ---------------------------------------------------------------------

def test_par_defaut_un_succes_emet_une_seule_requete(full_payload, recorder):
    with make_client(json_responder(full_payload), recorder=recorder) as client:
        client.govern(token_count=1, latency_ms=1.0)
    assert recorder.count == 1


@pytest.mark.parametrize("status", [401, 402, 413, 422, 429, 500, 502, 503])
def test_par_defaut_aucun_statut_d_erreur_n_est_reessaye(recorder, status):
    handler = json_responder({"error": "x", "detail": "y"}, status)
    with make_client(handler, recorder=recorder) as client:
        with pytest.raises(Exception):
            client.govern(token_count=1, latency_ms=1.0)
    assert recorder.count == 1, f"le statut {status} a été réessayé"


def test_par_defaut_un_timeout_n_est_pas_reessaye(recorder):
    handler = raising_responder(httpx.ReadTimeout("trop long"))
    with make_client(handler, recorder=recorder) as client:
        with pytest.raises(TimeoutError):
            client.govern(token_count=1, latency_ms=1.0)
    assert recorder.count == 1


def test_par_defaut_une_panne_reseau_n_est_pas_reessayee(recorder):
    handler = raising_responder(httpx.ConnectError("dns"))
    with make_client(handler, recorder=recorder) as client:
        with pytest.raises(Exception):
            client.govern(token_count=1, latency_ms=1.0)
    assert recorder.count == 1


# ---------------------------------------------------------------------
# Un timeout n'est JAMAIS réessayé, même avec une politique active
# ---------------------------------------------------------------------

def test_un_timeout_n_est_jamais_reessaye_meme_avec_une_politique(recorder):
    """Le seul cas où le SDK ne peut pas savoir si la requête a été
    exécutée côté serveur. La répétition produirait une seconde mesure
    facturée."""
    policy = RetryPolicy(max_attempts=5, on=(503,), backoff_initial=0.0)
    handler = raising_responder(httpx.ReadTimeout("trop long"))
    with make_client(handler, recorder=recorder, retry=policy) as client:
        with pytest.raises(TimeoutError):
            client.govern(token_count=1, latency_ms=1.0)
    assert recorder.count == 1


def test_une_panne_reseau_n_est_jamais_reessayee_meme_avec_une_politique(recorder):
    policy = RetryPolicy(max_attempts=5, on=(503,), backoff_initial=0.0)
    handler = raising_responder(httpx.ConnectError("dns"))
    with make_client(handler, recorder=recorder, retry=policy) as client:
        with pytest.raises(Exception):
            client.govern(token_count=1, latency_ms=1.0)
    assert recorder.count == 1


# ---------------------------------------------------------------------
# Une politique explicite fait ce qu'elle annonce, et rien de plus
# ---------------------------------------------------------------------

def test_une_politique_explicite_reessaye_les_statuts_declares(
    full_payload, recorder
):
    policy = RetryPolicy(max_attempts=3, on=(503,), backoff_initial=0.0)
    handler = sequence_responder(
        [
            httpx.Response(503, json=_err("e503.json")),
            httpx.Response(503, json=_err("e503.json")),
            httpx.Response(200, json=full_payload),
        ]
    )
    with make_client(handler, recorder=recorder, retry=policy) as client:
        result = client.govern(token_count=1, latency_ms=1.0)
    assert recorder.count == 3
    assert result.governance.decision == "ALLOW"


def test_une_politique_explicite_respecte_son_plafond(recorder):
    policy = RetryPolicy(max_attempts=2, on=(503,), backoff_initial=0.0)
    handler = json_responder(_err("e503.json"), 503)
    with make_client(handler, recorder=recorder, retry=policy) as client:
        with pytest.raises(ServerError):
            client.govern(token_count=1, latency_ms=1.0)
    assert recorder.count == 2


def test_un_statut_hors_de_la_liste_n_est_pas_reessaye(recorder):
    policy = RetryPolicy(max_attempts=5, on=(503,), backoff_initial=0.0)
    handler = json_responder(_err("e500.json"), 500)
    with make_client(handler, recorder=recorder, retry=policy) as client:
        with pytest.raises(ServerError):
            client.govern(token_count=1, latency_ms=1.0)
    assert recorder.count == 1


def test_429_n_est_pas_dans_la_liste_par_defaut(recorder):
    """Une limite de débit demande d'attendre `Retry-After`, ce que
    l'appelant maîtrise mieux que le SDK."""
    policy = RetryPolicy(max_attempts=3, backoff_initial=0.0)
    assert 429 not in policy.on
    handler = json_responder(_err("e429.json"), 429)
    with make_client(handler, recorder=recorder, retry=policy) as client:
        with pytest.raises(RateLimitError):
            client.govern(token_count=1, latency_ms=1.0)
    assert recorder.count == 1


def test_retry_after_prime_sur_le_backoff_exponentiel():
    policy = RetryPolicy(
        max_attempts=3, on=(429,), backoff_initial=5.0, respect_retry_after=True
    )
    assert policy.delay_for(1, retry_after=0.25) == 0.25
    assert policy.delay_for(1, retry_after=None) == 5.0


def test_le_backoff_est_exponentiel_et_plafonne():
    policy = RetryPolicy(
        max_attempts=9, backoff_initial=1.0, backoff_multiplier=2.0, backoff_max=8.0
    )
    assert policy.delay_for(1) == 1.0
    assert policy.delay_for(2) == 2.0
    assert policy.delay_for(3) == 4.0
    assert policy.delay_for(4) == 8.0
    assert policy.delay_for(9) == 8.0


def test_should_retry_respecte_le_plafond_de_tentatives():
    policy = RetryPolicy(max_attempts=3, on=(503,))
    assert policy.should_retry(503, attempt=1) is True
    assert policy.should_retry(503, attempt=2) is True
    assert policy.should_retry(503, attempt=3) is False
    assert policy.should_retry(500, attempt=1) is False


def test_NO_RETRY_ne_reessaye_rien():
    assert NO_RETRY.should_retry(503, attempt=1) is False
    assert NO_RETRY.enabled is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_attempts": 0},
        {"max_attempts": -1},
        {"backoff_initial": -1.0},
        {"backoff_max": -1.0},
        {"backoff_multiplier": 0.5},
    ],
)
def test_une_politique_incoherente_est_refusee(kwargs):
    with pytest.raises(ValueError):
        RetryPolicy(**kwargs)
