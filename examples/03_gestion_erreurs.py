"""Exemple 3 — Gestion robuste des erreurs.

SERVEUR SIMULÉ. Aucun réseau.

    python examples/03_gestion_erreurs.py

Montre les neuf familles d'échec, et la règle la plus importante du SDK :
**aucun réessai automatique sur `POST /v1/govern`**, parce que la route
n'est pas idempotente — chaque appel crée une observation et débite un
quota ou un portefeuille.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from neomundi import (  # noqa: E402
    APIError,
    AuthenticationError,
    InvalidResponseError,
    NeoMundiClient,
    NetworkError,
    PaymentRequiredError,
    PayloadTooLargeError,
    RateLimitError,
    RetryPolicy,
    ServerError,
    TimeoutError,
    TransportError,
    ValidationError,
)

ROOT = Path(__file__).parent.parent
ERRORS = ROOT / "tests/fixtures/errors"
API_KEY = "ct_test_0000000000000000000000000000"
BASE_URL = "https://example.invalid"


def _fixture(name: str) -> dict:
    payload = json.loads((ERRORS / name).read_text(encoding="utf-8"))
    return {k: v for k, v in payload.items() if not k.startswith("_fixture_")}


def _client(handler, **kwargs) -> NeoMundiClient:
    return NeoMundiClient(
        api_key=API_KEY,
        base_url=BASE_URL,
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def _appel(handler, **kwargs):
    with _client(handler, **kwargs) as client:
        return client.govern(token_count=1, latency_ms=1.0)


def _responder(payload, status, headers=None):
    return lambda _r: httpx.Response(status, json=payload, headers=headers or {})


# ---------------------------------------------------------------------
# Le gestionnaire que vous écririez en production
# ---------------------------------------------------------------------

def gouverner_avec_gestion_complete(client: NeoMundiClient, **kwargs):
    """Montre le traitement recommandé de chaque famille d'échec.

    Renvoie `(resultat, None)` ou `(None, diagnostic)`.
    """
    try:
        return client.govern(**kwargs), None

    except AuthenticationError as exc:
        # Ne pas réessayer : la clé ne redeviendra pas valide seule.
        return None, f"clé invalide ou révoquée (request_id={exc.request_id})"

    except PaymentRequiredError as exc:
        # TROIS causes possibles sous ce statut, que le serveur ne sépare
        # pas : quota d'essai épuisé, solde insuffisant, budget de clé.
        return None, f"paiement requis — {exc.detail}"

    except PayloadTooLargeError:
        # Le corps dépasse 1 Mio. Tronquer `llm_response` et rappeler.
        return None, "charge trop volumineuse : tronquer llm_response"

    except ValidationError as exc:
        champs = ", ".join(
            str(e.get("field")) for e in exc.field_errors
        ) or "inconnus"
        return None, f"requête invalide, champs : {champs}"

    except RateLimitError as exc:
        # `retry_after` vient du serveur. Le SDK ne dort PAS à votre place.
        attente = exc.retry_after if exc.retry_after is not None else "inconnu"
        return None, f"limite de débit — réessayer dans {attente} s"

    except ServerError as exc:
        # Un 5xx REÇU prouve que la requête n'a pas abouti : réessayer est
        # sûr, si vous le décidez explicitement.
        return None, f"erreur serveur {exc.status_code} — réessai possible"

    except TimeoutError:
        # Le cas délicat : la requête a PEUT-ÊTRE été traitée et facturée.
        # Ne pas rejouer à l'aveugle.
        return None, "délai dépassé — l'observation existe peut-être déjà"

    except NetworkError as exc:
        return None, f"panne réseau — {exc}"

    except InvalidResponseError as exc:
        # Réponse 2xx inexploitable : le SDK refuse de rendre un résultat
        # vide, qui serait indistinguable d'une mesure non effectuée.
        return None, f"réponse inexploitable (statut {exc.status_code})"

    except APIError as exc:
        # Filet pour un statut que cette version du SDK ne connaît pas.
        return None, f"statut inattendu {exc.status_code}"


def main() -> int:
    print("=" * 70)
    print("Exemple 3 — Gestion robuste des erreurs (serveur simulé)")
    print("=" * 70)

    cas = [
        ("401 clé invalide", _responder(_fixture("e401.json"), 401)),
        ("402 quota / solde", _responder(_fixture("e402.json"), 402)),
        ("413 charge trop grande", _responder(_fixture("e413.json"), 413)),
        ("422 validation", _responder(_fixture("e422.json"), 422)),
        (
            "429 limite de débit",
            _responder(_fixture("e429.json"), 429, {"Retry-After": "42"}),
        ),
        ("500 erreur serveur", _responder(_fixture("e500.json"), 500)),
        ("503 indisponible", _responder(_fixture("e503.json"), 503)),
        (
            "timeout",
            lambda _r: (_ for _ in ()).throw(httpx.ReadTimeout("trop long")),
        ),
        (
            "panne réseau",
            lambda _r: (_ for _ in ()).throw(httpx.ConnectError("dns")),
        ),
        ("JSON invalide", lambda _r: httpx.Response(200, text="<html>oops")),
    ]

    print("\n--- Les dix familles d'échec ---")
    for libelle, handler in cas:
        with _client(handler) as client:
            _, diagnostic = gouverner_avec_gestion_complete(
                client, token_count=1, latency_ms=1.0
            )
        print(f"  {libelle:26} -> {diagnostic}")

    # ------------------------------------------------------------------
    # 429 : tout ce dont vous avez besoin est exposé
    # ------------------------------------------------------------------
    print("\n--- 429 : les en-têtes de limite sont exposés ---")
    handler = _responder(
        _fixture("e429.json"),
        429,
        {
            "Retry-After": "42",
            "X-RateLimit-Limit": "60",
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": "1760000000",
        },
    )
    try:
        _appel(handler)
    except RateLimitError as exc:
        print(f"  retry_after           : {exc.retry_after} s")
        print(f"  rate_limit            : {exc.rate_limit} req/min")
        print(f"  rate_limit_remaining  : {exc.rate_limit_remaining}")
        print(f"  rate_limit_reset      : {exc.rate_limit_reset}")
        print("  >>> Le SDK ne dort pas à votre place : vous décidez.")

    # ------------------------------------------------------------------
    # Le 413, qui n'a que deux clés
    # ------------------------------------------------------------------
    print("\n--- 413 : forme de corps différente, gérée sans supposition ---")
    try:
        _appel(_responder(_fixture("e413.json"), 413))
    except PayloadTooLargeError as exc:
        print(f"  error_code       : {exc.error_code}")
        print(f"  request_id       : {exc.request_id}  (absent du corps)")
        print(f"  server_timestamp : {exc.server_timestamp}  (absent du corps)")
        print("  >>> Un SDK qui exigerait quatre clés échouerait ici.")

    # ------------------------------------------------------------------
    # Aucun réessai par défaut — la propriété la plus importante
    # ------------------------------------------------------------------
    print("\n--- Aucun réessai automatique ---")
    appels = {"n": 0}

    def compteur(_request):
        appels["n"] += 1
        return httpx.Response(503, json=_fixture("e503.json"))

    try:
        _appel(compteur)
    except ServerError:
        pass
    print(f"  par défaut, un 503 -> {appels['n']} appel émis")

    appels["n"] = 0
    try:
        _appel(compteur, retry=RetryPolicy(max_attempts=3, on=(503,), backoff_initial=0.0))
    except ServerError:
        pass
    print(f"  avec RetryPolicy(max_attempts=3) -> {appels['n']} appels émis")

    appels["n"] = 0
    try:
        _appel(
            lambda _r: (_ for _ in ()).throw(httpx.ReadTimeout("x")),
            retry=RetryPolicy(max_attempts=5, on=(503,), backoff_initial=0.0),
        )
    except TimeoutError:
        pass
    print(f"  un timeout, MÊME avec une politique -> 1 appel émis (jamais rejoué)")

    print("\n  >>> Pourquoi : POST /v1/govern n'est pas idempotent.")
    print("      Chaque appel crée une observation, débite un quota ou un")
    print("      portefeuille, écrit une ligne de métrologie, et écrase la")
    print("      référence delta_g du compte.")

    # ------------------------------------------------------------------
    # La hiérarchie permet d'attraper large quand c'est voulu
    # ------------------------------------------------------------------
    print("\n--- Attraper par famille ---")
    print(f"  TimeoutError est un TransportError : {issubclass(TimeoutError, TransportError)}")
    print(f"  NetworkError est un TransportError : {issubclass(NetworkError, TransportError)}")
    print(f"  ServerError  est un APIError       : {issubclass(ServerError, APIError)}")
    print(f"  TimeoutError est un APIError       : {issubclass(TimeoutError, APIError)}")
    print("  >>> Un timeout n'est PAS une APIError : aucune réponse n'a été reçue.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
