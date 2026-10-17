"""Politique de réessai — **désactivée par défaut**, et c'est une décision de fond.

`POST /v1/govern` n'est pas idempotent. Relevé dans le backend au commit
`68d6057` :

* une **nouvelle observation** est créée à chaque appel —
  `request_id = str(uuid.uuid4())`, `runtime_engine.py:162` ;
* le **quota ou le portefeuille est débité** avant le travail —
  `enforce_trial_quota(client)`, `governance.py:172` ;
* une **ligne de métrologie** est écrite — `usage_events`,
  `governance.py:586-626` ;
* la **référence `delta_g` du compte est écrasée** dans Redis —
  `governance.py:2088`.

Aucun en-tête d'idempotence n'existe sur cette route : la recherche de
`Idempotency-Key` dans `govern-v3/` ne renvoie aucune occurrence.

Conséquence : un réessai automatique produirait une **seconde mesure
facturée** et faussserait le `delta_g` de l'appel suivant. Le SDK ne
réessaie donc rien de lui-même. Il expose `Retry-After` sur
`RateLimitError` et laisse l'appelant décider.

Une politique explicite reste disponible pour qui l'assume, avec un
garde-fou qui n'est pas négociable : **un délai dépassé n'est jamais
réessayé**. C'est le seul cas où le SDK ne peut pas savoir si la requête
a été exécutée côté serveur. Un `503` *reçu*, lui, prouve qu'elle n'a pas
abouti.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

__all__ = ["RetryPolicy", "NO_RETRY"]


@dataclass(frozen=True)
class RetryPolicy:
    """Réessais sur les statuts HTTP que l'appelant juge sûrs.

    À construire **explicitement**. Il n'existe pas de `retry=True` ni
    d'entier magique : activer des réessais sur une route non idempotente
    est une décision, pas une option de confort.

    Args:
        max_attempts: nombre total de tentatives, réessais inclus. `1`
            signifie « aucun réessai ». Doit être ≥ 1.
        on: statuts HTTP réessayables. Par défaut `(503,)` — un service
            indisponible a répondu, donc il n'a pas traité la requête.
            **429 n'y est pas par défaut** : une limite de débit atteinte
            demande d'attendre `Retry-After`, ce que l'appelant maîtrise
            mieux que le SDK.
        backoff_initial: délai de la première attente, en secondes.
        backoff_multiplier: facteur appliqué à chaque nouvelle attente.
        backoff_max: plafond d'une attente, en secondes.
        respect_retry_after: quand le serveur envoie `Retry-After`, ce
            délai prime sur le calcul exponentiel.

    Jamais réessayé, quelle que soit la politique :

    * un **délai dépassé** (`TimeoutError`) — la requête a peut-être été
      exécutée et facturée ;
    * une **erreur réseau** (`NetworkError`) — même raison ;
    * tout statut absent de `on`.
    """

    max_attempts: int = 1
    on: Tuple[int, ...] = field(default=(503,))
    backoff_initial: float = 0.5
    backoff_multiplier: float = 2.0
    backoff_max: float = 8.0
    respect_retry_after: bool = True

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts doit être >= 1 (1 = aucun réessai).")
        if self.backoff_initial < 0 or self.backoff_max < 0:
            raise ValueError("Les délais de backoff doivent être positifs.")
        if self.backoff_multiplier < 1:
            raise ValueError("backoff_multiplier doit être >= 1.")

    @property
    def enabled(self) -> bool:
        """`True` seulement si plus d'une tentative est autorisée."""
        return self.max_attempts > 1

    def should_retry(self, status_code: int, attempt: int) -> bool:
        """`True` si un statut peut être réessayé à cette tentative.

        `attempt` est le numéro de la tentative qui vient d'échouer, à
        partir de 1.
        """
        if not self.enabled:
            return False
        if attempt >= self.max_attempts:
            return False
        return status_code in self.on

    def delay_for(self, attempt: int, retry_after: "float | None" = None) -> float:
        """Le délai à attendre après la tentative `attempt`.

        `retry_after`, quand le serveur le fournit et que
        `respect_retry_after` est actif, prime : le serveur sait mieux que
        nous quand il acceptera la requête suivante.
        """
        if retry_after is not None and self.respect_retry_after:
            return max(0.0, float(retry_after))
        delay = self.backoff_initial * (self.backoff_multiplier ** max(0, attempt - 1))
        return min(delay, self.backoff_max)


#: La politique par défaut : aucune tentative supplémentaire.
NO_RETRY = RetryPolicy(max_attempts=1)
