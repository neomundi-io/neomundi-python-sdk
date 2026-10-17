"""Client HTTP synchrone pour l'API NeoMundi.

Périmètre v0.1 : `POST /v1/govern` uniquement. Le streaming SSE fait
l'objet d'une mission séparée — voir `README.md`, section « Limites ».
"""

from __future__ import annotations

import json
import time
from types import TracebackType
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Type

import httpx

from ._retry import NO_RETRY, RetryPolicy
from .errors import (
    ConfigurationError,
    InvalidResponseError,
    NetworkError,
    RateLimitError,
    TimeoutError,
    api_error_for_status,
)
from .models import GovernResult

__all__ = ["NeoMundiClient", "GOVERN_PATH", "KEY_PREFIXES"]

#: Chemin de la route, relevé de `app/main.py` (préfixe `/v1`) et de
#: `app/api/v1/governance.py:94` (préfixe de routeur `/govern`).
GOVERN_PATH = "/v1/govern"

#: Préfixes acceptés par le serveur — `app/auth/api_key.py:83-88`.
KEY_PREFIXES = ("ct_live_", "ct_test_", "ct_trial_")

_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)

_USER_AGENT_BASE = "neomundi-python-sdk"


class NeoMundiClient:
    """Client synchrone de l'API NeoMundi.

    Exemple :

        from neomundi import NeoMundiClient

        with NeoMundiClient(api_key="ct_test_...", base_url="https://...") as c:
            result = c.govern(
                token_count=128,
                latency_ms=842.0,
                llm_response="La capitale de la France est Paris.",
                llm_prompt="Quelle est la capitale de la France ?",
            )
            print(result.governance.decision, result.format_score("g_score"))

    Args:
        api_key: clé NeoMundi. Son **format** est vérifié localement, pour
            qu'une clé manifestement invalide ne consomme pas un
            aller-retour — et surtout pas un quota.
        base_url: racine de l'API, sans le `/v1`. Aucune valeur par
            défaut : le SDK ne suppose pas d'hôte, afin qu'aucun appel ne
            parte vers un environnement non choisi.
        timeout: `httpx.Timeout`, ou un flottant appliqué aux quatre
            phases. Le défaut en lecture est de 60 s, dérivé du backend :
            les trois évaluateurs tournent en parallèle sur un Ollama CPU
            et `/v1/govern` les attend tous.
        retry: politique de réessai. **`NO_RETRY` par défaut** — la route
            n'est pas idempotente, voir `neomundi._retry`.
        transport: transport httpx injectable, pour les tests. Fourni, il
            est utilisé pour construire le client interne.
        http_client: client httpx déjà construit. Fourni, il est utilisé
            tel quel et **n'est pas fermé** par ce SDK : on ne ferme pas
            ce qu'on n'a pas créé.
        user_agent: suffixe ajouté à l'en-tête `User-Agent`.

    Raises:
        ConfigurationError: si la clé, l'URL ou le délai sont invalides.
            Levée à la construction, avant tout réseau.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        *,
        timeout: "httpx.Timeout | float | None" = None,
        retry: RetryPolicy = NO_RETRY,
        transport: Optional[httpx.BaseTransport] = None,
        http_client: Optional[httpx.Client] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        self._api_key = _validate_api_key(api_key)
        self._base_url = _validate_base_url(base_url)
        self._timeout = _coerce_timeout(timeout)
        if not isinstance(retry, RetryPolicy):
            raise ConfigurationError(
                "retry doit être une RetryPolicy. Activer des réessais sur une "
                "route non idempotente est une décision explicite : construire "
                "RetryPolicy(max_attempts=...) plutôt que de passer un booléen."
            )
        self._retry = retry

        from . import __version__

        ua = f"{_USER_AGENT_BASE}/{__version__}"
        if user_agent:
            ua = f"{ua} {user_agent}"
        self._headers = {
            "X-API-Key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": ua,
        }

        if http_client is not None:
            self._client = http_client
            self._owns_client = False
        else:
            self._client = httpx.Client(
                base_url=self._base_url,
                timeout=self._timeout,
                transport=transport,
            )
            self._owns_client = True

    # ------------------------------------------------------------------
    # Cycle de vie
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Ferme le client HTTP interne, s'il a été créé par ce SDK."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "NeoMundiClient":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        self.close()

    @property
    def is_closed(self) -> bool:
        return bool(self._client.is_closed)

    @property
    def base_url(self) -> str:
        return self._base_url

    def __repr__(self) -> str:
        """Représentation **sans la clé**.

        Seuls le préfixe et les quatre derniers caractères sont montrés,
        pour permettre de distinguer deux clés sans en révéler aucune.
        """
        return (
            f"NeoMundiClient(base_url={self._base_url!r}, "
            f"api_key={_mask_key(self._api_key)!r}, "
            f"retry={'on' if self._retry.enabled else 'off'})"
        )

    # ------------------------------------------------------------------
    # POST /v1/govern
    # ------------------------------------------------------------------

    def govern(
        self,
        *,
        token_count: int,
        latency_ms: float,
        cost: Optional[float] = None,
        semantic_risk: Optional[float] = None,
        prompt_length: Optional[int] = None,
        response_length: Optional[int] = None,
        model_name: Optional[str] = None,
        llm_response: Optional[str] = None,
        llm_prompt: Optional[str] = None,
        source_type: str = "llm",
        mode: str = "OBS",
        rag_context: Optional[Sequence[str]] = None,
        documents: Optional[Iterable[Mapping[str, str]]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> GovernResult:
        """Soumet une observation à `POST /v1/govern`.

        **Appel post-call** : l'appelant a déjà interrogé son modèle, puis
        envoie ici les métriques réelles de la réponse obtenue.

        Les noms de paramètres reprennent **exactement** ceux du contrat
        serveur (`GovernRequest` / `RawMetrics`). Aucun renommage : un
        troisième vocabulaire, après celui du serveur et celui du
        glossaire, serait la pire option.

        Args:
            token_count: nombre de tokens de la réponse. **Requis.**
            latency_ms: latence observée, en millisecondes. **Requis.**
            cost: coût de l'opération, **dans l'unité de l'appelant**. Le
                serveur n'y attache aucune devise : la valeur est divisée
                par un plafond par type de source pour produire un ratio
                sans dimension. L'exigence est donc la **cohérence** —
                utiliser la même unité pour toutes les requêtes d'une même
                intégration, sinon `cost_proxy` ne compare rien.
            semantic_risk: risque sémantique déclaré par l'appelant,
                dans `[0,1]`. **Écrasé par la mesure serveur** si
                `llm_response` est fourni et que la modération aboutit.
            prompt_length: longueur du prompt, **en caractères** (c'est la
                convention à laquelle la description du champ serveur
                s'engage). Attention : la route la lit comme `tokens_in`
                pour calculer `volumetric_density`, qui est donc un ratio
                tokens/caractères — ce que le champ
                `density.volumetric_density_basis` déclare.
            response_length: longueur de la réponse, **en caractères**. Ce
                champ **entre dans un calcul** côté serveur : au-delà de
                2000, il participe à la classification « long-form safe »,
                qui peut transformer un FLAG en ALLOW.
            model_name: identifiant du modèle interrogé par l'appelant.
            llm_response: texte de la réponse. **C'est ce paramètre qui
                déclenche les contrôles sémantiques serveur** (modération,
                cohérence, factualité). Sans lui, aucun signal n'est
                mesuré et `measurement.status` vaut `not_attempted`.
            llm_prompt: texte du prompt, utilisé pour la cohérence et pour
                le contexte du juge.
            source_type: `llm` | `iot` | `financial`. Détermine les
                plafonds de normalisation du bloc runtime.
            mode: `OBS`, seule valeur acceptée par le serveur.
            rag_context: passages documentaires (chemin historique).
            documents: corpus `{"title": ..., "text": ...}` pour le juge
                d'ancrage. Requiert le palier TIER_02+ côté serveur.
            metadata: dictionnaire opaque, transmis pour le traçage.
            extra: clés supplémentaires fusionnées à la racine du corps.
                Échappatoire de compatibilité ascendante, pour exploiter
                un champ de requête ajouté au serveur sans attendre une
                version du SDK. **Non validé.**

        Les paramètres laissés à `None` **ne sont pas envoyés** : le
        serveur applique alors ses propres valeurs par défaut, documentées
        dans son modèle. Le SDK ne décide pas qu'un coût absent vaut
        `0.0`.

        Returns:
            GovernResult — jamais `None`, jamais partiellement construit.

        Raises:
            ConfigurationError: paramètre invalide, détecté avant l'appel.
            AuthenticationError: 401.
            PaymentRequiredError: 402 (quota, solde ou budget de clé).
            PayloadTooLargeError: 413.
            ValidationError: 422.
            RateLimitError: 429, avec `retry_after`.
            ServerError: 5xx.
            TimeoutError / NetworkError: aucune réponse obtenue.
            InvalidResponseError: réponse 2xx inexploitable.
        """
        body = _build_request_body(
            token_count=token_count,
            latency_ms=latency_ms,
            cost=cost,
            semantic_risk=semantic_risk,
            prompt_length=prompt_length,
            response_length=response_length,
            model_name=model_name,
            llm_response=llm_response,
            llm_prompt=llm_prompt,
            source_type=source_type,
            mode=mode,
            rag_context=rag_context,
            documents=documents,
            metadata=metadata,
            extra=extra,
        )
        response = self._request("POST", GOVERN_PATH, body)
        return _parse_govern_response(response)

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _request(
        self, method: str, path: str, body: Optional[Dict[str, Any]]
    ) -> httpx.Response:
        """Émet la requête et applique la politique de réessai.

        Générique sur la méthode et le chemin, pour qu'une route
        supplémentaire n'impose pas de réécrire cette couche.
        """
        attempt = 0
        while True:
            attempt += 1
            try:
                response = self._client.request(
                    method,
                    path,
                    json=body,
                    headers=self._headers,
                )
            except httpx.TimeoutException as exc:
                # JAMAIS réessayé, quelle que soit la politique : la
                # requête a peut-être été exécutée et facturée.
                raise TimeoutError(
                    f"Délai dépassé sur {method} {path} : {type(exc).__name__}. "
                    "La requête a peut-être été traitée par le serveur — ne pas "
                    "la rejouer sans avoir vérifié si l'observation existe."
                ) from exc
            except httpx.HTTPError as exc:
                raise NetworkError(
                    f"Échec de transport sur {method} {path} : "
                    f"{type(exc).__name__}: {exc}"
                ) from exc

            if response.status_code < 400:
                return response

            error = _build_api_error(response)

            if self._retry.should_retry(response.status_code, attempt):
                retry_after = getattr(error, "retry_after", None)
                time.sleep(self._retry.delay_for(attempt, retry_after))
                continue

            raise error

    # ------------------------------------------------------------------
    # Exposé pour les tests et la réutilisation
    # ------------------------------------------------------------------

    @staticmethod
    def build_request_body(**kwargs: Any) -> Dict[str, Any]:
        """Construit le corps de requête sans l'envoyer.

        Fonction pure, exposée pour l'inspection, les tests et un futur
        client asynchrone.
        """
        return _build_request_body(**kwargs)


# ---------------------------------------------------------------------
# Fonctions pures — séparées du transport pour un futur client async
# ---------------------------------------------------------------------

def _build_request_body(
    *,
    token_count: int,
    latency_ms: float,
    cost: Optional[float] = None,
    semantic_risk: Optional[float] = None,
    prompt_length: Optional[int] = None,
    response_length: Optional[int] = None,
    model_name: Optional[str] = None,
    llm_response: Optional[str] = None,
    llm_prompt: Optional[str] = None,
    source_type: str = "llm",
    mode: str = "OBS",
    rag_context: Optional[Sequence[str]] = None,
    documents: Optional[Iterable[Mapping[str, str]]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
    extra: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Assemble le corps de `GovernRequest`.

    Les champs laissés à `None` sont **omis**, afin que le serveur
    applique ses propres valeurs par défaut documentées. Le SDK n'en
    invente aucune.
    """
    if isinstance(token_count, bool) or not isinstance(token_count, int):
        raise ConfigurationError("token_count doit être un entier.")
    if token_count < 0:
        raise ConfigurationError("token_count doit être >= 0.")
    if isinstance(latency_ms, bool) or not isinstance(latency_ms, (int, float)):
        raise ConfigurationError("latency_ms doit être un nombre.")
    if latency_ms < 0:
        raise ConfigurationError("latency_ms doit être >= 0.")

    raw_metrics: Dict[str, Any] = {
        "token_count": token_count,
        "latency_ms": float(latency_ms),
    }

    if cost is not None:
        if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0:
            raise ConfigurationError("cost doit être un nombre >= 0.")
        raw_metrics["cost"] = float(cost)

    if semantic_risk is not None:
        if (
            isinstance(semantic_risk, bool)
            or not isinstance(semantic_risk, (int, float))
            or not 0.0 <= semantic_risk <= 1.0
        ):
            raise ConfigurationError("semantic_risk doit être un nombre dans [0, 1].")
        raw_metrics["semantic_risk"] = float(semantic_risk)

    for name, value in (
        ("prompt_length", prompt_length),
        ("response_length", response_length),
    ):
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ConfigurationError(f"{name} doit être un entier >= 0.")
        raw_metrics[name] = value

    if model_name is not None:
        if not isinstance(model_name, str) or not model_name:
            raise ConfigurationError("model_name doit être une chaîne non vide.")
        raw_metrics["model_name"] = model_name

    body: Dict[str, Any] = {
        "source_type": source_type,
        "mode": mode,
        "raw_metrics": raw_metrics,
    }

    if llm_response is not None:
        if not isinstance(llm_response, str):
            raise ConfigurationError("llm_response doit être une chaîne.")
        body["llm_response"] = llm_response
    if llm_prompt is not None:
        if not isinstance(llm_prompt, str):
            raise ConfigurationError("llm_prompt doit être une chaîne.")
        body["llm_prompt"] = llm_prompt
    if rag_context is not None:
        body["rag_context"] = list(rag_context)
    if documents is not None:
        body["documents"] = [dict(d) for d in documents]
    if metadata is not None:
        body["metadata"] = dict(metadata)
    if extra:
        body.update(dict(extra))

    return body


def _parse_govern_response(response: httpx.Response) -> GovernResult:
    """Décode une réponse 2xx en `GovernResult`.

    Une réponse 2xx dont le corps n'est pas du JSON exploitable est une
    `InvalidResponseError`, et non un résultat vide : rendre un résultat
    aux champs tous nuls serait indistinguable d'une mesure complètement
    non effectuée, ce qui est exactement la confusion que ce SDK existe
    pour empêcher.
    """
    request_id = response.headers.get("X-Request-ID")
    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError) as exc:
        raise InvalidResponseError(
            "Le corps de la réponse n'est pas du JSON valide "
            f"({type(exc).__name__}).",
            body=_safe_text(response),
            status_code=response.status_code,
            request_id=request_id,
        ) from exc

    result = GovernResult.from_dict(payload)
    if result.request_id is None and request_id:
        # Le contrat déclare `request_id` requis dans le corps. S'il
        # manque, l'en-tête que le middleware pose sur toute réponse est
        # une information réelle, pas une invention.
        result = _with_request_id(result, request_id)
    return result


def _with_request_id(result: GovernResult, request_id: str) -> GovernResult:
    import dataclasses

    return dataclasses.replace(result, request_id=request_id)


def _build_api_error(response: httpx.Response) -> Exception:
    """Construit l'exception correspondant à une réponse d'erreur.

    N'exige **aucune** forme de corps. Le 413 du backend ne porte que
    `error` et `detail` — ni `request_id`, ni `timestamp` —, et un parsing
    qui exigerait quatre clés échouerait là où il doit informer.
    """
    status = response.status_code
    cls = api_error_for_status(status)

    body: Any
    try:
        body = response.json()
    except (json.JSONDecodeError, ValueError):
        body = _safe_text(response)

    error_code: Optional[str] = None
    detail: Any = None
    request_id: Optional[str] = None
    server_timestamp: Optional[str] = None

    if isinstance(body, dict):
        raw_error = body.get("error")
        error_code = raw_error if isinstance(raw_error, str) else None
        detail = body.get("detail")
        raw_rid = body.get("request_id")
        request_id = raw_rid if isinstance(raw_rid, str) else None
        raw_ts = body.get("timestamp")
        server_timestamp = raw_ts if isinstance(raw_ts, str) else None

    if request_id is None:
        # Posé par le middleware sur TOUTE réponse (`app/main.py`), y
        # compris celles dont le corps ne le porte pas.
        request_id = response.headers.get("X-Request-ID")

    message = _error_message(detail) or f"Le serveur a répondu HTTP {status}."

    return cls(
        message,
        status_code=status,
        error_code=error_code,
        detail=detail,
        request_id=request_id,
        server_timestamp=server_timestamp,
        body=body,
        headers=response.headers,
    )


def _error_message(detail: Any) -> Optional[str]:
    """Un message lisible tiré de `detail`, sans en perdre le contenu."""
    if isinstance(detail, str) and detail:
        return detail
    if isinstance(detail, list) and detail:
        parts: List[str] = []
        for item in detail:
            if isinstance(item, dict):
                field_name = item.get("field")
                msg = item.get("message")
                if field_name or msg:
                    parts.append(f"{field_name}: {msg}")
        if parts:
            return "; ".join(parts)
    return None


def _safe_text(response: httpx.Response) -> str:
    """Le corps en texte, tronqué, pour le diagnostic."""
    try:
        return response.text[:2000]
    except Exception:  # pragma: no cover - corps illisible
        return "<corps illisible>"


# ---------------------------------------------------------------------
# Validation de configuration
# ---------------------------------------------------------------------

def _validate_api_key(api_key: str) -> str:
    if not isinstance(api_key, str) or not api_key.strip():
        raise ConfigurationError("api_key est requis et doit être une chaîne non vide.")
    key = api_key.strip()
    if not any(key.startswith(p) for p in KEY_PREFIXES):
        raise ConfigurationError(
            "Format de api_key invalide. Préfixes attendus : "
            + ", ".join(KEY_PREFIXES)
            + ". Vérifié localement pour qu'une clé invalide ne consomme pas "
            "un appel, ni un quota."
        )
    return key


def _validate_base_url(base_url: str) -> str:
    if not isinstance(base_url, str) or not base_url.strip():
        raise ConfigurationError(
            "base_url est requis. Le SDK ne suppose aucun hôte par défaut, "
            "afin qu'aucun appel ne parte vers un environnement non choisi."
        )
    url = base_url.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        raise ConfigurationError("base_url doit commencer par http:// ou https://.")
    return url


def _coerce_timeout(timeout: "httpx.Timeout | float | None") -> httpx.Timeout:
    if timeout is None:
        return _DEFAULT_TIMEOUT
    if isinstance(timeout, httpx.Timeout):
        return timeout
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise ConfigurationError("timeout doit être un nombre ou un httpx.Timeout.")
    if timeout <= 0:
        raise ConfigurationError("timeout doit être > 0.")
    return httpx.Timeout(float(timeout))


def _mask_key(api_key: str) -> str:
    """Masque une clé pour l'affichage : préfixe + 4 derniers caractères."""
    for prefix in KEY_PREFIXES:
        if api_key.startswith(prefix):
            return f"{prefix}***{api_key[-4:]}" if len(api_key) > len(prefix) + 4 else f"{prefix}***"
    return "***"
