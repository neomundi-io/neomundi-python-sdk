"""Outillage de test — aucun accès réseau, aucune vraie clé.

Tous les tests passent par `httpx.MockTransport`, intégré à httpx. Aucune
dépendance de test supplémentaire n'est nécessaire, et aucun test ne peut
atteindre un serveur réel : le transport simulé ne fait pas de socket.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import httpx
import pytest

from neomundi import NeoMundiClient

#: Clé de test évidente. Format valide côté serveur (préfixe `ct_test_`),
#: valeur manifestement factice. **Aucune vraie clé n'existe dans ce
#: dépôt.**
TEST_API_KEY = "ct_test_0000000000000000000000000000"

#: Hôte réservé par la RFC 2606 : toute résolution DNS échouerait, ce qui
#: est une seconde ligne de défense si un transport simulé était oublié.
TEST_BASE_URL = "https://example.invalid"

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Dict[str, Any]:
    """Charge une fixture JSON et retire les métadonnées `_fixture_*`.

    Les clés `_fixture_origin` / `_fixture_note` documentent l'origine de
    la charge (relevée du code, ou synthétique) et ne font pas partie du
    contrat : elles sont retirées avant d'être servies au SDK, pour
    qu'aucun test ne dépende de leur présence.
    """
    path = FIXTURES / name
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in payload.items() if not k.startswith("_fixture_")}


def fixture_metadata(name: str) -> Dict[str, Any]:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return {k: v for k, v in payload.items() if k.startswith("_fixture_")}


class RequestRecorder:
    """Mémorise les requêtes vues par le transport simulé.

    Sert notamment à prouver qu'aucun réessai non autorisé n'a lieu :
    `len(recorder.requests)` est le nombre réel d'appels émis.
    """

    def __init__(self) -> None:
        self.requests: List[httpx.Request] = []

    @property
    def count(self) -> int:
        return len(self.requests)

    @property
    def last(self) -> httpx.Request:
        if not self.requests:
            raise AssertionError("Aucune requête n'a été émise.")
        return self.requests[-1]

    def last_json(self) -> Dict[str, Any]:
        return json.loads(self.last.content.decode("utf-8"))


def make_client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    api_key: str = TEST_API_KEY,
    base_url: str = TEST_BASE_URL,
    recorder: Optional[RequestRecorder] = None,
    **kwargs: Any,
) -> NeoMundiClient:
    """Construit un client branché sur un transport simulé."""

    def _wrapped(request: httpx.Request) -> httpx.Response:
        if recorder is not None:
            recorder.requests.append(request)
        return handler(request)

    return NeoMundiClient(
        api_key=api_key,
        base_url=base_url,
        transport=httpx.MockTransport(_wrapped),
        **kwargs,
    )


def json_responder(
    payload: Dict[str, Any],
    status_code: int = 200,
    headers: Optional[Dict[str, str]] = None,
) -> Callable[[httpx.Request], httpx.Response]:
    """Un gestionnaire qui répond toujours la même charge JSON."""

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload, headers=headers or {})

    return _handler


def sequence_responder(
    responses: List[httpx.Response],
) -> Callable[[httpx.Request], httpx.Response]:
    """Répond les réponses dans l'ordre ; répète la dernière si épuisée."""
    state = {"i": 0}

    def _handler(_request: httpx.Request) -> httpx.Response:
        i = min(state["i"], len(responses) - 1)
        state["i"] += 1
        return responses[i]

    return _handler


def raising_responder(
    exc: BaseException,
) -> Callable[[httpx.Request], httpx.Response]:
    """Un gestionnaire qui lève, pour simuler timeout et panne réseau."""

    def _handler(_request: httpx.Request) -> httpx.Response:
        raise exc

    return _handler


@pytest.fixture
def recorder() -> RequestRecorder:
    return RequestRecorder()


@pytest.fixture
def full_payload() -> Dict[str, Any]:
    return load_fixture("full_measurement.json")


@pytest.fixture
def partial_payload() -> Dict[str, Any]:
    return load_fixture("partial_measurement.json")


@pytest.fixture
def gated_payload() -> Dict[str, Any]:
    return load_fixture("gated_tier01.json")


@pytest.fixture
def not_attempted_payload() -> Dict[str, Any]:
    return load_fixture("no_check_attempted.json")


@pytest.fixture
def drift_payload() -> Dict[str, Any]:
    return load_fixture("synthetic_drift.json")
