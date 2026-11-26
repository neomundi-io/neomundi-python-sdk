"""SDK Python NeoMundi — client de l'API de mesure du comportement des IA.

SDK v2 : parcours INSTALL -> TRACE -> MEASURE -> VERIFY.

* **TRACE** — `client.trace()` instrumente l'appel de l'application :
  latence mesurée, identifiant de corrélation, soumission explicite. Il
  n'existe **aucune route de traçage** sur l'API ; ce module ne prétend
  pas le contraire. Voir `neomundi.trace`.
* **MEASURE** — `client.govern()` (REST post-call) et `client.stream()`
  (proxy de génération SSE), inchangés.
* **VERIFY** — `client.verify()` et `client.verify_audit_certificate()`
  interrogent les routes **publiques et non facturées** de vérification
  d'émission ; `verify_evidence_archive()` délègue l'intégrité au
  vérificateur Evidence **indépendant**, qui n'est pas réimplémenté ici.
  Les trois questions — intégrité, authenticité, véracité — sont
  distinguées dans `neomundi.verification`.

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

#: `2.1.0` ajoute `trace()` et `verify()` à la surface publiée. La
#: publication reste verrouillée par un flux manuel épinglé sur un tag
#: exact (`sdk-v2.2.0`), une phrase de confirmation et l'environnement
#: GitHub `pypi` : le numéro a été re-pointé, aucun verrou n'a été retiré.
__version__ = "2.2.0"

# Importe tot, et volontairement avant `API_CONTRACT` qui s'en sert :
# `models` ne depend que de `.errors`, donc aucune circularite.
from .models import (
    VERIFIED_MEASUREMENT_VERSIONS as _VERIFIED_MEASUREMENT_VERSIONS,
)

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
    # Reexporte la declaration unique de `models`, que
    # `warn_on_measurement_version` applique desormais. Ce champ etait
    # auparavant la seule copie, et aucun chemin de code ne la lisait.
    "verified_measurement_versions": _VERIFIED_MEASUREMENT_VERSIONS,
    "normalizer_version": "1.0.0",
    "route": "POST /v1/govern",
    "stream_route": "POST /v1/govern/stream",
    "stream_backend_commit": "aeff13cca717205c9ebbc83c5755ba6a22b284bb",
    "stream_verification": "local_backend_source_and_offline_tests_only",
    "contract_source": "govern-v3/app/models/responses.py, requests.py",
    "openapi_frozen": False,
    # Routes de vérification publiques, sans clé et non facturées.
    # Sondées en production le 2026-11-15 : les deux rendent le 404
    # documenté sur un identifiant inexistant.
    "rgc_verify_route": "GET /v1/rgc/verify/{request_id}",
    "audit_verify_route": "GET /v1/audit/verify/{audit_trail_id}",
    # Les deux schémas de fil publiés par la production. Relevés le
    # 2026-11-15 sur `GET /v1/contracts/<nom>` : octet pour octet
    # identiques aux fichiers du dépôt backend, ce qui est la seule
    # preuve disponible que ce SDK se réfère au contrat DÉPLOYÉ et non à
    # une copie locale. `/docs` et `/openapi.json` rendent 404 en
    # production : il n'y a pas d'autre schéma à lire.
    #
    # L'empreinte REST a changé le 2026-11-15 avec le déploiement de la
    # révision `03e2b344` de `govern` : `POST /v1/govern` publie
    # désormais `log_persisted` et `log_write`, comme la route SSE le
    # faisait déjà. Ajout strictement additif — `required` identique —
    # donc les deux champs arrivent dans `unknown_fields` et restent
    # lisibles par `result.get("log_persisted")`. **Les exposer comme
    # champs typés serait une évolution du SDK, pas une
    # synchronisation : ce n'est volontairement pas fait ici.**
    # `govern-sse-1.0.json` est INCHANGÉ.
    "wire_contracts": {
        # Re-epinglees le 2026-11-26 sur les contrats du backend
        # `ec9a57646`, republies publiquement par
        # `neomundi-measurement-mcp`. Les precedentes valeurs etaient l'etat
        # `03e2b344` du 2026-11-15 : la production avait derive le 21/11.
        "govern-rest-1.0.json": (
            "8e27a9110298a9b9ff31d6379daefddb1f068fa0b17452ed7b65e341e16d84c3"
        ),
        "govern-sse-1.0.json": (
            "d05caa8d48c6f64f0124a53f8977914e9e5fe0558ff6172031d3131d36c4c165"
        ),
    },
}

from ._retry import NO_RETRY, RetryPolicy
from .verification import (
    AUDIT_VERIFY_PATH,
    EVIDENCE_COMMAND,
    EVIDENCE_EXIT_CODES,
    RGC_VERIFY_PATH,
    AuditCertificateVerification,
    ContractVerification,
    EvidenceVerification,
    EvidenceVerifierUnavailable,
    verify_evidence_archive,
)
from .trace import TRACE_OUTCOMES, Trace, TraceRecord
from .streaming import (
    GOVERN_STREAM_PATH,
    GovernStream,
    StreamError,
    StreamEvent,
    StreamInterruptedError,
    StreamProtocolError,
    StreamResult,
    StreamServerError,
)
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
    "GOVERN_STREAM_PATH",
    "GovernStream",
    "StreamEvent",
    "StreamResult",
    "StreamError",
    "StreamInterruptedError",
    "StreamProtocolError",
    "StreamServerError",
    "__version__",
    "API_CONTRACT",
    # client
    "NeoMundiClient",
    "GOVERN_PATH",
    "KEY_PREFIXES",
    # retry
    "RetryPolicy",
    "NO_RETRY",
    # trace
    "Trace",
    "TraceRecord",
    "TRACE_OUTCOMES",
    # verify
    "ContractVerification",
    "AuditCertificateVerification",
    "EvidenceVerification",
    "EvidenceVerifierUnavailable",
    "verify_evidence_archive",
    "EVIDENCE_COMMAND",
    "EVIDENCE_EXIT_CODES",
    "RGC_VERIFY_PATH",
    "AUDIT_VERIFY_PATH",
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
