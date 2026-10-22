"""SDK Python NeoMundi — client de l'API de mesure du comportement des IA.

Périmètre v0.1 : `POST /v1/govern` (appel post-call) uniquement.

Principe directeur, qui explique chaque choix de ce paquet :

    Le SDK transporte et expose les mesures. Il ne les interprète pas.

Concrètement :

* aucun seuil n'est embarqué — pas de `is_safe()`, pas de niveau de
  qualité dérivé ;
* `null` reste `None` : aucune valeur par défaut numérique n'existe dans
  le code source ;
* un champ dont la sémantique est ambiguë est exposé sous son chemin
  complet, avec l'ambiguïté documentée, plutôt que converti.

Lire `docs/LIMITES.md` avant d'interpréter un score.
"""

from __future__ import annotations

__version__ = "0.1.0"

#: Le contrat backend auquel ce SDK se réfère.
#:
#: `backend_commit` est le commit où les modèles de requête et de réponse
#: ont été relevés. Il est inscrit ici parce qu'aucun OpenAPI figé
#: n'existe côté serveur : nommer le commit est le seul moyen de dire à
#: quoi ce SDK correspond.
#:
#: `measurement_version` est le seul numéro qui ait un sens scientifique :
#: deux résultats produits sous deux valeurs différentes ne sont pas
#: comparables pour une même entrée. Comparer la valeur ci-dessous à
#: `result.audit.measurement_version` avertit d'un écart.
#:
#: `verified_measurement_versions` est une liste **plus large**, et la
#: distinction compte. `measurement_version` dit de quel commit ce SDK a
#: été dérivé ; `verified_measurement_versions` dit sous quelles versions
#: de mesure la surface REST a été vérifiée identique à celle-là. Un
#: écart entre les deux n'est donc pas une incompatibilité tant que la
#: version servie figure dans cette liste — mais il reste un écart, et il
#: reste décisif pour la **comparabilité** de deux séries.
#:
#: `3.3.1` y figure depuis le 2026-10-22, sur deux preuves énoncées en
#: entier dans `KNOWN_LIMITATIONS.md` §6 : les fichiers de contrat du
#: backend sont **inchangés** entre `68d6057` et le commit déployé
#: `aeff13c`, et une réponse réellement émise par la production sous
#: `3.3.1` a été rejouée sans avertissement ni champ inconnu. **Aucune
#: des deux n'est un appel de ce SDK contre le service hébergé.**
API_CONTRACT = {
    "backend_commit": "68d6057cf620e430e6488da3cfcec9c471c75ed6",
    "measurement_version": "3.3.0",
    "verified_measurement_versions": ("3.3.0", "3.3.1"),
    "normalizer_version": "1.0.0",
    "route": "POST /v1/govern",
    "contract_source": "govern-v3/app/models/responses.py, requests.py",
    "openapi_frozen": False,
}

from ._retry import NO_RETRY, RetryPolicy
from .client import GOVERN_PATH, KEY_PREFIXES, NeoMundiClient
from .errors import (
    AggregateWithheldError,
    APIError,
    AuthenticationError,
    ConfigurationError,
    InvalidResponseError,
    NeoMundiError,
    NetworkError,
    PaymentRequiredError,
    PayloadTooLargeError,
    RateLimitError,
    ServerError,
    TimeoutError,
    TransportError,
    ValidationError,
)
from .models import (
    AGGREGATE_FIELDS,
    COVERAGE_SIGNALS,
    Audit,
    Baseline,
    Citation,
    Density,
    Esi,
    Governance,
    GovernResult,
    Measurement,
    MeasurementState,
    Metrics,
    ParseWarning,
    Quality,
    RagGrounding,
    Runtime,
    SuspectPhrase,
    UngroundedSnippet,
)

__all__ = [
    "__version__",
    "API_CONTRACT",
    # client
    "NeoMundiClient",
    "GOVERN_PATH",
    "KEY_PREFIXES",
    # retry
    "RetryPolicy",
    "NO_RETRY",
    # modèles
    "GovernResult",
    "MeasurementState",
    "COVERAGE_SIGNALS",
    "AGGREGATE_FIELDS",
    "ParseWarning",
    "Governance",
    "Measurement",
    "Quality",
    "Runtime",
    "Metrics",
    "Baseline",
    "Esi",
    "Density",
    "RagGrounding",
    "Audit",
    "SuspectPhrase",
    "Citation",
    "UngroundedSnippet",
    # erreurs
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
]
