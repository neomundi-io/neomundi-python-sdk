"""Exceptions du SDK NeoMundi.

Hiérarchie, du général au particulier :

    NeoMundiError                   base, jamais levée directement
    ├── ConfigurationError          clé / URL / timeout invalides (avant tout réseau)
    ├── TransportError              aucune réponse HTTP obtenue
    │   ├── TimeoutError
    │   └── NetworkError
    ├── InvalidResponseError        réponse obtenue, inexploitable
    ├── AggregateWithheldError      `require()` sur un agrégat déclaré non publiable
    └── APIError                    le serveur a répondu un statut d'erreur
        ├── AuthenticationError     401
        ├── PaymentRequiredError    402
        ├── PayloadTooLargeError    413
        ├── ValidationError         422
        ├── RateLimitError          429
        └── ServerError             5xx

Règle tenue dans tout ce module : **aucun message, aucun `repr`, ne contient
la clé API**. Voir `tests/test_no_secret_leak.py`.

Règle de robustesse : le parsing d'un corps d'erreur **n'exige jamais** une
forme particulière. Le backend émet quatre clés sur la plupart des statuts
(`error`, `detail`, `request_id`, `timestamp`) mais seulement deux sur le
413 — ni `request_id`, ni `timestamp`, parce que le middleware qui les pose
n'a pas encore tourné. Un SDK qui suppose quatre clés sur toute erreur est
faux aujourd'hui, et le resterait silencieusement.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

__all__ = [
    "NeoMundiError",
    "ConfigurationError",
    "TransportError",
    "TimeoutError",
    "NetworkError",
    "InvalidResponseError",
    "AggregateWithheldError",
    "APIError",
    "AuthenticationError",
    "PaymentRequiredError",
    "PayloadTooLargeError",
    "ValidationError",
    "RateLimitError",
    "ServerError",
    "api_error_for_status",
]


class NeoMundiError(Exception):
    """Base de toutes les exceptions du SDK."""


class ConfigurationError(NeoMundiError):
    """Paramètre de client invalide, détecté AVANT tout appel réseau.

    Lever ici plutôt qu'au premier appel évite qu'une clé mal formée
    consomme un aller-retour, et surtout qu'elle consomme un quota.
    """


# ---------------------------------------------------------------------
# Transport — aucune réponse HTTP n'a été obtenue
# ---------------------------------------------------------------------

class TransportError(NeoMundiError):
    """Aucune réponse HTTP n'a été obtenue.

    Distinction importante pour `POST /v1/govern`, qui n'est pas
    idempotent : une requête sans réponse **a peut-être été exécutée et
    facturée** côté serveur. Le SDK ne réessaie donc jamais de lui-même
    dans ce cas — voir `neomundi._retry`.
    """


class TimeoutError(TransportError):  # noqa: A001 - masque volontairement le builtin
    """Le délai imparti a expiré.

    Le serveur a peut-être traité la requête. **Ne pas réessayer** sans
    savoir si l'observation a été créée : la répétition produirait une
    seconde mesure, un second débit, et écraserait la référence `delta_g`
    du compte.
    """


class NetworkError(TransportError):
    """Échec de transport : DNS, connexion, TLS, protocole."""


# ---------------------------------------------------------------------
# Réponse obtenue mais inexploitable
# ---------------------------------------------------------------------

class InvalidResponseError(NeoMundiError):
    """Le serveur a répondu 2xx, mais la réponse est inexploitable.

    Deux cas :

    * le corps n'est pas du JSON ;
    * le corps est du JSON mais ne porte pas un bloc que le contrat
      déclare REQUIS (`governance`, `metrics`, `baseline`, `audit`).

    Le second est traité comme une erreur et non comme une donnée
    manquante : ces quatre blocs sont non-`Optional` dans le modèle du
    serveur. Leur absence est une violation de contrat, pas un signal non
    mesuré — et les confondre est exactement ce que ce SDK existe pour
    éviter.

    `body` conserve ce qui a été reçu, tronqué, pour le diagnostic.
    """

    def __init__(
        self,
        message: str,
        *,
        body: Any = None,
        status_code: Optional[int] = None,
        request_id: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.body = body
        self.status_code = status_code
        self.request_id = request_id


class AggregateWithheldError(NeoMundiError):
    """`require()` a été appelé sur un agrégat que le serveur a retenu.

    Ce n'est pas une erreur du serveur : c'est le comportement déclaré.
    Quand un signal requis n'a pas pu être mesuré, `g_score`,
    `stability_score` et `g_final` sont publiés `null`, la décision est
    `FLAG` et `decision_basis` vaut `incomplete_measurement`.

    Cette exception existe pour qu'un intégrateur qui écrit
    `f"{result.require('g_score'):.2f}"` obtienne un message qui nomme la
    cause, au lieu du `TypeError: unsupported format string passed to
    NoneType.__format__` que produit un accès direct.

    `missing_required_signals` nomme les signaux manquants quand le
    serveur les a publiés.
    """

    def __init__(
        self,
        message: str,
        *,
        field: str,
        missing_required_signals: Optional[List[str]] = None,
        decision_basis: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.field = field
        self.missing_required_signals = missing_required_signals
        self.decision_basis = decision_basis


# ---------------------------------------------------------------------
# Erreurs renvoyées par l'API
# ---------------------------------------------------------------------

class APIError(NeoMundiError):
    """Le serveur a répondu avec un statut d'erreur.

    Tous les attributs sont facultatifs **par conception** : voir la note
    sur le 413 en tête de module. `body` conserve toujours ce qui a été
    reçu, pour qu'aucune information serveur ne soit perdue.
    """

    #: Renseigné par les sous-classes ; None pour la classe générique.
    status: Optional[int] = None

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        error_code: Optional[str] = None,
        detail: Any = None,
        request_id: Optional[str] = None,
        server_timestamp: Optional[str] = None,
        body: Any = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.detail = detail
        self.request_id = request_id
        #: Chaîne brute. Le serveur produit `datetime.utcnow().isoformat()`,
        #: donc SANS fuseau : le convertir imposerait de supposer UTC.
        self.server_timestamp = server_timestamp
        self.body = body
        self.headers = dict(headers) if headers else {}

    def __str__(self) -> str:
        parts = [f"HTTP {self.status_code}"]
        if self.error_code:
            parts.append(str(self.error_code))
        base = super().__str__()
        if base:
            parts.append(base)
        if self.request_id:
            parts.append(f"request_id={self.request_id}")
        return " | ".join(parts)


class AuthenticationError(APIError):
    """401 — clé absente, de format invalide, révoquée ou suspendue."""

    status = 401


class PaymentRequiredError(APIError):
    """402 — paiement requis.

    Le backend renvoie ce statut pour **trois causes distinctes** qu'il ne
    sépare pas sur le fil :

    * quota TRIAL épuisé ;
    * solde de portefeuille insuffisant pour le prix unitaire du palier ;
    * plafond de budget de la clé atteint.

    Le SDK ne devine pas laquelle. `detail` et `body` conservent ce que le
    serveur a dit. Un sous-code serveur serait nécessaire pour les
    distinguer de façon fiable.
    """

    status = 402


class PayloadTooLargeError(APIError):
    """413 — corps de requête au-delà de 1 048 576 octets.

    Deux composants peuvent l'émettre : le middleware applicatif (avant
    toute validation) et `client_max_body_size` de nginx. Dans les deux
    cas le corps ne porte que `error` et `detail` — **ni `request_id`, ni
    `timestamp`**. Quand c'est possible, `request_id` est récupéré de
    l'en-tête `X-Request-ID`, que le middleware pose sur toute réponse.
    """

    status = 413


class ValidationError(APIError):
    """422 — la requête n'a pas passé la validation du serveur.

    `detail` est ici une **liste** d'objets `{field, message, type}`, et
    non une chaîne. `field_errors` l'expose normalisée ; `detail`
    conserve la valeur brute.
    """

    status = 422

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.field_errors: List[Dict[str, Any]] = _normalise_field_errors(self.detail)


class RateLimitError(APIError):
    """429 — limite de débit atteinte.

    `retry_after` vient de l'en-tête `Retry-After` quand il est présent et
    lisible comme un entier de secondes. Le SDK **n'attend pas et ne
    réessaie pas** : l'appelant décide, parce qu'un réessai sur cette
    route crée une seconde mesure facturée.

    `rate_limit`, `rate_limit_remaining` et `rate_limit_reset` reprennent
    les en-têtes `X-RateLimit-*`.
    """

    status = 429

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = _header_int(self.headers, "retry-after")
        self.rate_limit = _header_int(self.headers, "x-ratelimit-limit")
        self.rate_limit_remaining = _header_int(self.headers, "x-ratelimit-remaining")
        self.rate_limit_reset = _header_int(self.headers, "x-ratelimit-reset")


class ServerError(APIError):
    """5xx — erreur côté serveur (500, 503, et tout autre 5xx).

    Un 5xx **reçu** prouve que la requête n'a pas abouti, contrairement à
    un timeout. C'est la seule famille d'erreurs qu'une politique de
    retry explicite peut raisonnablement couvrir.
    """

    status = 500


_STATUS_MAP = {
    401: AuthenticationError,
    402: PaymentRequiredError,
    413: PayloadTooLargeError,
    422: ValidationError,
    429: RateLimitError,
}


def api_error_for_status(status_code: int) -> type:
    """La classe d'exception correspondant à un statut HTTP.

    Tout 5xx non répertorié devient `ServerError` ; tout autre statut
    d'erreur non répertorié devient `APIError`, afin qu'un nouveau code
    côté serveur ne se perde pas dans une classe trompeuse.
    """
    mapped = _STATUS_MAP.get(status_code)
    if mapped is not None:
        return mapped
    if 500 <= status_code < 600:
        return ServerError
    return APIError


# ---------------------------------------------------------------------
# Utilitaires internes
# ---------------------------------------------------------------------

def _normalise_field_errors(detail: Any) -> List[Dict[str, Any]]:
    """Normalise le `detail` d'un 422 sans jamais en perdre le contenu.

    Renvoie une liste vide si `detail` n'a pas la forme attendue : le brut
    reste disponible dans `detail` et dans `body`.
    """
    if not isinstance(detail, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in detail:
        if isinstance(item, dict):
            out.append(
                {
                    "field": item.get("field"),
                    "message": item.get("message"),
                    "type": item.get("type"),
                }
            )
    return out


def _header_int(headers: Mapping[str, str], name: str) -> Optional[int]:
    """Lit un en-tête entier, sans jamais inventer de valeur par défaut.

    Renvoie `None` quand l'en-tête est absent ou illisible — jamais 0,
    qui signifierait « réessayez immédiatement ».
    """
    for key, value in headers.items():
        if key.lower() == name:
            try:
                return int(str(value).strip())
            except (TypeError, ValueError):
                return None
    return None
