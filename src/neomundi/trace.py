"""Étape TRACE du parcours : instrumenter l'appel de l'application.

Ce module n'ajoute **aucune route**. Il n'en existe pas : l'audit du
2026-11-15 a relevé les huit routeurs de l'API déployée
(`app/main.py:_include_routers`) et **aucun point d'entrée de traçage
indépendant de la mesure**. Prétendre le contraire serait exactement la
fausse traçabilité que l'issue #20 interdit.

Ce que TRACE est donc ici, et rien de plus :

* un **chronomètre local** (`time.monotonic`) autour de l'appel que
  l'application fait à son propre fournisseur. La latence devient une
  valeur **mesurée**, là où la version 2.0.0 obligeait l'appelant à la
  fournir à la main. ⚠ La granularité de `time.monotonic()` est
  d'environ **15,6 ms sur Windows** : un bloc plus court qu'un tic
  d'horloge mesure `0.0`, et cette valeur est transmise telle quelle.
  Arrondir vers le haut fabriquerait une mesure ;
* un **identifiant de corrélation** côté appelant, apparié à l'identifiant
  que le serveur renvoie ;
* une **soumission explicite** à `POST /v1/govern`, dont le résultat est
  conservé tel quel.

Ce que TRACE n'est pas, et que ce module refuse de laisser croire :

* 🔴 **le décompte de tokens n'est jamais inventé.** Sans
  `token_count`, rien n'est envoyé et une `ConfigurationError` est levée.
  Le contrat déployé le déclare requis (`app/models/requests.py:36`) et
  la réponse déployée le republie sous `token_count_source:
  "caller_declared"` — le serveur ne compte rien sur cette route ;
* 🔴 **`registered` reste `None` sur REST.** La route ne publie aucune
  confirmation d'écriture : son 200 est émis même quand l'insertion en
  base a échoué (`governance.py` journalise l'échec et continue). Seule
  la route SSE publie `log_persisted`. Voir `TraceRecord.from_stream`.
* 🔴 **`client_trace_id` n'est pas conservé par le serveur.** Le champ
  `metadata` est accepté par le contrat (« opaque metadata forwarded for
  tracing ») mais la route déployée ne le lit, ne le republie et ne le
  persiste nulle part : l'objet persisté est la réponse plus les seules
  *longueurs* du prompt et de la réponse. La corrélation est donc
  établie **chez l'appelant**, en appariant `client_trace_id` et
  `request_id`.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from types import TracebackType
from typing import TYPE_CHECKING, Any, Dict, Iterable, Mapping, Optional, Sequence, Type

from .errors import ConfigurationError
from .models import GovernResult

if TYPE_CHECKING:  # pragma: no cover - import circulaire à l'exécution
    from .client import NeoMundiClient
    from .streaming import StreamResult

__all__ = ["Trace", "TraceRecord", "TRACE_OUTCOMES"]

#: Les issues possibles d'une trace. Vocabulaire **fermé** : un état
#: nouveau doit être ajouté ici, pas improvisé dans une chaîne.
TRACE_OUTCOMES = (
    #: Mesure soumise, réponse exploitable obtenue.
    "submitted",
    #: Rien n'a été envoyé : `submit=False` à la construction.
    "not_submitted_local_only",
    #: Rien n'a été envoyé : le bloc applicatif a levé une exception.
    "not_submitted_application_error",
    #: Rien n'a été envoyé : la trace n'a jamais été refermée.
    "open",
)


@dataclass(frozen=True)
class TraceRecord:
    """Ce qui a été constaté d'une interaction, une fois la trace refermée.

    Immuable. **Ne porte ni le prompt ni la réponse** : seules leurs
    longueurs. `to_dict()` est donc sûr à journaliser — la propriété
    tient par construction, pas par discipline de l'appelant. C'est la
    même règle que le serveur s'applique à son propre journal
    (`governance.py:539` : « MUST NEVER contain the raw llm_prompt or
    llm_response text »).
    """

    #: Identifiant de corrélation **de l'appelant**. Le serveur ne le
    #: conserve pas : c'est à l'appelant de stocker le couple
    #: (`client_trace_id`, `request_id`).
    client_trace_id: str
    #: Issue de la trace, parmi `TRACE_OUTCOMES`.
    outcome: str
    #: Latence réellement mesurée autour du bloc applicatif, en
    #: millisecondes. `None` si la trace n'a jamais été refermée.
    latency_ms: Optional[float] = None
    #: Décompte de tokens **déclaré par l'appelant**. Jamais calculé ici.
    token_count: Optional[int] = None
    model_name: Optional[str] = None
    #: Longueurs en caractères, comme le contrat serveur les attend.
    prompt_length: Optional[int] = None
    response_length: Optional[int] = None
    #: `True` si une requête a effectivement été émise.
    submitted: bool = False
    #: `True` si le serveur a répondu 2xx **et** fourni un `request_id`.
    #: C'est un accusé de traitement, pas une preuve d'enregistrement.
    acknowledged: bool = False
    #: Identifiant serveur. **Le seul identifiant de corrélation fiable
    #: de la plateforme.**
    request_id: Optional[str] = None
    #: L'observation est-elle enregistrée côté serveur ?
    #:
    #: `None` sur REST, et ce `None` est une mesure de l'absence : la
    #: route ne publie aucune confirmation d'écriture. `True`/`False`
    #: uniquement par `from_stream`, où le serveur publie
    #: `log_persisted`.
    registered: Optional[bool] = None
    #: `audit.trace_id` du serveur, soit `trace-{request_id[:8]}`
    #: (`governance.py:1573`). **Dérivé et tronqué à 8 caractères
    #: hexadécimaux : il n'est pas unique par construction.** Ne jamais
    #: s'en servir comme clé — corréler sur `request_id`.
    server_trace_id: Optional[str] = None
    #: Transport employé : `rest` ou `sse`.
    transport: str = "rest"
    #: Le résultat complet, quand il y en a un.
    result: Optional[GovernResult] = None
    #: Le résultat SSE complet, quand la trace vient d'un flux.
    stream_result: Optional["StreamResult"] = field(default=None, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        """Un dictionnaire journalisable : **aucun contenu client**."""
        return {
            "client_trace_id": self.client_trace_id,
            "outcome": self.outcome,
            "latency_ms": self.latency_ms,
            "token_count": self.token_count,
            "model_name": self.model_name,
            "prompt_length": self.prompt_length,
            "response_length": self.response_length,
            "submitted": self.submitted,
            "acknowledged": self.acknowledged,
            "request_id": self.request_id,
            "registered": self.registered,
            "server_trace_id": self.server_trace_id,
            "transport": self.transport,
        }

    @classmethod
    def from_stream(
        cls,
        stream_result: "StreamResult",
        *,
        client_trace_id: Optional[str] = None,
        latency_ms: Optional[float] = None,
    ) -> "TraceRecord":
        """Construit une trace depuis un flux SSE déjà consommé.

        C'est **le seul chemin où `registered` porte une valeur** : la
        route SSE publie `log_persisted`, et son absence dans l'enveloppe
        `done` déclare une insertion nominale (voir
        `StreamResult.log_persisted`).
        """
        payload = stream_result.payload
        response_text = stream_result.response_text
        audit = payload.get("audit")
        server_trace_id = None
        if isinstance(audit, dict) and isinstance(audit.get("trace_id"), str):
            server_trace_id = audit["trace_id"]

        token_count = payload.get("total_tokens")
        if isinstance(token_count, bool) or not isinstance(token_count, int):
            token_count = None

        payload_latency = payload.get("latency_ms")
        if latency_ms is None and isinstance(payload_latency, (int, float)):
            if not isinstance(payload_latency, bool):
                latency_ms = float(payload_latency)

        model = payload.get("model")
        return cls(
            client_trace_id=client_trace_id or uuid.uuid4().hex,
            outcome="submitted",
            latency_ms=latency_ms,
            token_count=token_count,
            model_name=model if isinstance(model, str) else None,
            prompt_length=None,
            response_length=len(response_text),
            submitted=True,
            acknowledged=stream_result.request_id is not None,
            request_id=stream_result.request_id,
            registered=stream_result.log_persisted,
            server_trace_id=server_trace_id,
            transport="sse",
            result=None,
            stream_result=stream_result,
        )


class Trace:
    """Chronomètre l'appel de l'application, puis le soumet à la mesure.

    Usage :

        with client.trace(model_name="gpt-4o") as t:
            reply = my_llm(question)                    # appel de l'appelant
            t.record(prompt=question, response=reply,
                     token_count=usage.total_tokens)    # jamais deviné

        print(t.record_.request_id, t.record_.latency_ms)

    La latence couvre **uniquement** le bloc `with` : elle mesure l'appel
    de l'application à son fournisseur, pas l'aller-retour vers NeoMundi.

    ⚠ **Refermer la trace émet un appel facturé** à `POST /v1/govern`
    (débit de quota, voir `enforce_trial_quota`). `submit=False` en fait
    une instrumentation purement locale, qui n'ouvre aucune socket.

    Args:
        client: le client qui soumettra la mesure.
        client_trace_id: identifiant de corrélation de l'appelant. Généré
            (uuid4) s'il est omis. **Non conservé par le serveur.**
        submit: `False` pour ne rien envoyer.
        Les autres arguments sont ceux de `NeoMundiClient.govern`, et
        portent exactement les mêmes noms.
    """

    def __init__(
        self,
        client: "NeoMundiClient",
        *,
        client_trace_id: Optional[str] = None,
        submit: bool = True,
        token_count: Optional[int] = None,
        prompt: Optional[str] = None,
        response: Optional[str] = None,
        model_name: Optional[str] = None,
        cost: Optional[float] = None,
        source_type: str = "llm",
        mode: str = "OBS",
        prompt_length: Optional[int] = None,
        response_length: Optional[int] = None,
        rag_context: Optional[Sequence[str]] = None,
        documents: Optional[Iterable[Mapping[str, str]]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> None:
        if client_trace_id is not None and (
            not isinstance(client_trace_id, str) or not client_trace_id.strip()
        ):
            raise ConfigurationError(
                "client_trace_id doit être une chaîne non vide, ou être omis."
            )
        if not isinstance(submit, bool):
            raise ConfigurationError("submit doit être un booléen.")

        self._client = client
        self._submit = submit
        self.client_trace_id = (
            client_trace_id.strip() if client_trace_id else uuid.uuid4().hex
        )

        self._token_count = token_count
        self._prompt = prompt
        self._response = response
        self._model_name = model_name
        self._cost = cost
        self._source_type = source_type
        self._mode = mode
        self._prompt_length = prompt_length
        self._response_length = response_length
        self._rag_context = rag_context
        self._documents = documents
        self._metadata = dict(metadata) if metadata else {}
        self._extra = extra

        self._started: Optional[float] = None
        self._elapsed_ms: Optional[float] = None
        self._closed = False

        #: La trace, une fois refermée. `outcome == "open"` avant.
        self.record_ = TraceRecord(
            client_trace_id=self.client_trace_id, outcome="open"
        )

    # ------------------------------------------------------------------
    # Enregistrement, pendant le bloc
    # ------------------------------------------------------------------

    def record(
        self,
        *,
        response: Optional[str] = None,
        prompt: Optional[str] = None,
        token_count: Optional[int] = None,
        model_name: Optional[str] = None,
        cost: Optional[float] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> "Trace":
        """Consigne ce que l'appel de l'application a réellement produit.

        Appelable plusieurs fois ; seules les valeurs non `None` sont
        retenues. Renvoie `self`, pour permettre l'enchaînement.
        """
        if response is not None:
            self._response = response
        if prompt is not None:
            self._prompt = prompt
        if token_count is not None:
            self._token_count = token_count
        if model_name is not None:
            self._model_name = model_name
        if cost is not None:
            self._cost = cost
        if metadata:
            self._metadata.update(dict(metadata))
        return self

    # ------------------------------------------------------------------
    # Cycle de vie
    # ------------------------------------------------------------------

    def __enter__(self) -> "Trace":
        self._started = time.monotonic()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        self._stop_clock()
        if exc_type is not None:
            # Le bloc applicatif a échoué : il n'y a pas d'interaction
            # complète à mesurer, et une mesure partielle serait une
            # observation fabriquée. L'exception de l'appelant n'est pas
            # masquée (ce `__exit__` ne renvoie jamais `True`).
            self.record_ = self._build_record("not_submitted_application_error")
            return None
        self.close()
        return None

    def _stop_clock(self) -> None:
        if self._elapsed_ms is None and self._started is not None:
            self._elapsed_ms = (time.monotonic() - self._started) * 1000.0

    @property
    def latency_ms(self) -> Optional[float]:
        """La latence mesurée, disponible avant la fermeture."""
        if self._elapsed_ms is not None:
            return self._elapsed_ms
        if self._started is None:
            return None
        return (time.monotonic() - self._started) * 1000.0

    def close(self) -> TraceRecord:
        """Referme la trace et, si `submit`, soumet la mesure.

        Idempotent : un second appel renvoie la même trace sans
        réémettre la requête. La route n'est pas idempotente côté
        serveur ; rejouer la soumission créerait une seconde observation
        facturée pour une seule interaction.
        """
        if self._closed:
            return self.record_
        self._stop_clock()
        self._closed = True

        if not self._submit:
            self.record_ = self._build_record("not_submitted_local_only")
            return self.record_

        if self._token_count is None:
            # Jamais de valeur de substitution : une estimation de tokens
            # entrerait dans `cost_proxy` et dans la densité volumétrique,
            # donc dans des chiffres présentés comme mesurés.
            raise ConfigurationError(
                "token_count est requis avant de refermer la trace : le "
                "contrat déployé l'exige et le serveur ne compte rien sur "
                "cette route (`token_count_source: \"caller_declared\"`). "
                "Appeler record(token_count=...) avec la valeur rendue par "
                "le fournisseur, ou construire la trace avec submit=False "
                "pour n'émettre aucune requête."
            )
        if self._elapsed_ms is None:
            raise ConfigurationError(
                "la trace n'a jamais été ouverte : utiliser "
                "`with client.trace(...) as t:` pour que la latence soit "
                "mesurée au lieu d'être supposée."
            )

        metadata = dict(self._metadata)
        # Envoyé parce que le contrat expose le champ ; la route déployée
        # ne le conserve pas. La corrélation utile est le couple
        # (client_trace_id, request_id) rendu ci-dessous.
        metadata.setdefault("client_trace_id", self.client_trace_id)

        result = self._client.govern(
            token_count=self._token_count,
            latency_ms=self._elapsed_ms,
            cost=self._cost,
            prompt_length=self._resolved_prompt_length(),
            response_length=self._resolved_response_length(),
            model_name=self._model_name,
            llm_response=self._response,
            llm_prompt=self._prompt,
            source_type=self._source_type,
            mode=self._mode,
            rag_context=self._rag_context,
            documents=self._documents,
            metadata=metadata,
            extra=self._extra,
        )
        self.record_ = self._build_record("submitted", result=result)
        return self.record_

    # ------------------------------------------------------------------
    # Construction de la trace
    # ------------------------------------------------------------------

    def _resolved_prompt_length(self) -> Optional[int]:
        if self._prompt_length is not None:
            return self._prompt_length
        return len(self._prompt) if self._prompt is not None else None

    def _resolved_response_length(self) -> Optional[int]:
        if self._response_length is not None:
            return self._response_length
        return len(self._response) if self._response is not None else None

    def _build_record(
        self, outcome: str, *, result: Optional[GovernResult] = None
    ) -> TraceRecord:
        request_id = result.request_id if result is not None else None
        server_trace_id = result.audit.trace_id if result is not None else None
        return TraceRecord(
            client_trace_id=self.client_trace_id,
            outcome=outcome,
            latency_ms=self._elapsed_ms,
            token_count=self._token_count,
            model_name=self._model_name,
            prompt_length=self._resolved_prompt_length(),
            response_length=self._resolved_response_length(),
            submitted=result is not None,
            acknowledged=request_id is not None,
            request_id=request_id,
            # REST ne publie aucune confirmation d'écriture : l'absence
            # reste une absence.
            registered=None,
            server_trace_id=server_trace_id,
            transport="rest",
            result=result,
        )

    def __repr__(self) -> str:
        return (
            f"Trace(client_trace_id={self.client_trace_id!r}, "
            f"outcome={self.record_.outcome!r}, submit={self._submit})"
        )
