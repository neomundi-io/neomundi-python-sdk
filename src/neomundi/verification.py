"""Étape VERIFY du parcours — et les trois choses qu'elle ne confond pas.

Trois questions distinctes portent le même verbe en français courant, et
les mélanger est l'erreur la plus coûteuse de tout ce parcours :

1. **Intégrité** — « cet artefact est-il celui qui a été scellé ? »
   Répondue hors ligne par le **vérificateur Evidence indépendant**, un
   programme séparé (`neomundi-evidence-verify` sur PyPI). Ce SDK **ne
   vérifie rien lui-même** : il invoque ce programme et republie son
   verdict et son code de sortie sans les retraduire
   (`verify_evidence_archive`).

2. **Authenticité d'émission** — « cette plateforme a-t-elle bien émis
   cet enregistrement, et son empreinte correspond-elle ? » Répondue par
   deux routes **publiques, sans clé, non facturées** de l'API :
   `GET /v1/rgc/verify/{request_id}` (empreinte canonique recalculée
   + signature JWS Ed25519) et
   `GET /v1/audit/verify/{audit_trail_id}` (certificat PDF de palier 03).

3. **Véracité de la réponse de l'IA** — « ce que le modèle a répondu
   est-il vrai ? » 🔴 **Aucune de ces routes n'y répond, et ce SDK n'en
   approche pas.** Une mesure vérifiée est une mesure dont on sait qu'elle
   n'a pas été altérée ; elle ne dit rien de la justesse du contenu
   mesuré. `factual_hallucination_score` est un signal mesuré par un
   juge, avec ses propres limites — pas un verdict de vérité.

Rien ici ne réimplémente le moteur Evidence : ce module appelle, il ne
recalcule pas. Le gateway Evidence applique la même règle, et la mesure
(`tests/test_no_verification_logic.py`, côté gateway).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .errors import ConfigurationError, NeoMundiError

__all__ = [
    "ContractVerification",
    "AuditCertificateVerification",
    "EvidenceVerification",
    "EvidenceVerifierUnavailable",
    "EVIDENCE_EXIT_CODES",
    "RGC_VERIFY_PATH",
    "AUDIT_VERIFY_PATH",
    "verify_evidence_archive",
]

#: Routes publiques et non facturées. Relevées de
#: `app/api/v1/rgc.py:140` et `app/api/v1/exports.py:666`, et sondées en
#: production le 2026-11-15 : les deux rendent le 404 documenté sur un
#: identifiant inexistant.
RGC_VERIFY_PATH = "/v1/rgc/verify/{request_id}"
AUDIT_VERIFY_PATH = "/v1/audit/verify/{audit_trail_id}"

#: Les codes de sortie du vérificateur Evidence, republiés tels quels.
#: Les trois premiers viennent du moteur, les deux derniers du gateway,
#: qui existe précisément pour distinguer « rien n'a échoué » de « rien
#: n'a tourné ».
EVIDENCE_EXIT_CODES = {
    0: "verification_passed",
    1: "verification_failed",
    2: "verification_incomplete_missing_dependency",
    3: "engine_unavailable_no_verification_performed",
    4: "request_refused_no_verification_performed",
}

#: Le nom de la commande installée par `neomundi-evidence-verify`.
EVIDENCE_COMMAND = "neomundi-evidence"


@dataclass(frozen=True)
class ContractVerification:
    """Verdict de `GET /v1/rgc/verify/{request_id}`.

    `valid` est **tri-état**, et les trois états ne se replient pas :

    * `True` — empreinte canonique recalculée identique **et** signature
      JWS valide ;
    * `False` — l'une des deux a échoué, ou le journal source n'est plus
      lisible : `reason` le nomme ;
    * `None` — **aucune vérification n'a eu lieu** parce qu'aucun contrat
      RGC n'a été émis pour cette observation (404). Ce n'est pas un
      échec de vérification : c'est l'absence d'objet à vérifier. Les
      confondre ferait passer « jamais signé » pour « signature
      invalide ».
    """

    request_id: str
    valid: Optional[bool]
    #: Motif, quand le serveur en donne un, ou `no_contract_on_record`.
    reason: Optional[str] = None
    payload_hash_match: Optional[bool] = None
    signature_valid: Optional[bool] = None
    key_id: Optional[str] = None
    verified_at: Optional[str] = None
    http_status: Optional[int] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def verification_performed(self) -> bool:
        """`False` tant qu'il n'y a rien à vérifier."""
        return self.valid is not None

    @classmethod
    def from_payload(
        cls, request_id: str, payload: Any, status_code: int
    ) -> "ContractVerification":
        if not isinstance(payload, dict):
            return cls(
                request_id=request_id,
                valid=None,
                reason="response_not_an_object",
                http_status=status_code,
                raw={},
            )
        if status_code == 404:
            return cls(
                request_id=request_id,
                valid=None,
                reason="no_contract_on_record",
                http_status=404,
                raw=dict(payload),
            )
        valid = payload.get("valid")
        return cls(
            request_id=request_id,
            valid=valid if isinstance(valid, bool) else None,
            reason=payload.get("reason") if isinstance(payload.get("reason"), str) else None,
            payload_hash_match=_opt_bool(payload, "payload_hash_match"),
            signature_valid=_opt_bool(payload, "signature_valid"),
            key_id=payload.get("key_id") if isinstance(payload.get("key_id"), str) else None,
            verified_at=(
                payload.get("verified_at")
                if isinstance(payload.get("verified_at"), str)
                else None
            ),
            http_status=status_code,
            raw=dict(payload),
        )


@dataclass(frozen=True)
class AuditCertificateVerification:
    """Verdict de `GET /v1/audit/verify/{audit_trail_id}`.

    🔴 **`valid is None` est le cas nominal quand on n'a pas fourni
    `sha256`** : aucune empreinte n'est conservée à l'émission, donc la
    seule chose contre laquelle le service peut comparer est celle
    imprimée sur le document. Sans elle, la route recalcule l'empreinte
    courante et dit, par `valid: null`, que **rien n'a été vérifié**.
    Lire ce `null` comme un succès est le piège que la route elle-même a
    fermé en 2026.
    """

    audit_trail_id: str
    valid: Optional[bool]
    #: La phrase du serveur, conservée telle quelle.
    verification: Optional[str] = None
    record_found: bool = False
    request_id: Optional[str] = None
    #: Empreinte **recalculée** depuis l'observation stockée.
    sha256: Optional[str] = None
    issuer: Optional[str] = None
    timestamp: Optional[str] = None
    decision: Optional[str] = None
    verified_at: Optional[str] = None
    http_status: Optional[int] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def verification_performed(self) -> bool:
        return self.valid is not None

    @classmethod
    def from_payload(
        cls, audit_trail_id: str, payload: Any, status_code: int
    ) -> "AuditCertificateVerification":
        if not isinstance(payload, dict):
            return cls(
                audit_trail_id=audit_trail_id,
                valid=None,
                verification="response_not_an_object",
                http_status=status_code,
            )
        valid = payload.get("valid")
        return cls(
            audit_trail_id=audit_trail_id,
            valid=valid if isinstance(valid, bool) else None,
            verification=_opt_str(payload, "verification") or _opt_str(payload, "detail"),
            record_found=payload.get("record_found") is True,
            request_id=_opt_str(payload, "request_id"),
            sha256=_opt_str(payload, "sha256"),
            issuer=_opt_str(payload, "issuer"),
            timestamp=_opt_str(payload, "timestamp"),
            decision=_opt_str(payload, "decision"),
            verified_at=_opt_str(payload, "verified_at"),
            http_status=status_code,
            raw=dict(payload),
        )


class EvidenceVerifierUnavailable(NeoMundiError):
    """Le vérificateur Evidence indépendant n'est pas installé.

    Levée **au lieu** de rendre un verdict : un vérificateur absent ne
    produit pas « valide », il ne produit rien.
    """


@dataclass(frozen=True)
class EvidenceVerification:
    """Ce que le vérificateur Evidence indépendant a répondu.

    Republié sans retraduction : `exit_code` est celui du programme,
    `outcome` son nom dans `EVIDENCE_EXIT_CODES`, `report` son rapport
    JSON quand il en a émis un. Ce SDK ne recalcule aucune empreinte et
    ne dérive aucun verdict de son cru — il n'y a pas de champ
    `valid: True` fabriqué ici.
    """

    exit_code: int
    outcome: str
    command: Sequence[str] = field(default_factory=tuple)
    stdout: str = field(default="", repr=False)
    stderr: str = field(default="", repr=False)
    report: Optional[Dict[str, Any]] = field(default=None, repr=False)

    @property
    def verification_performed(self) -> bool:
        """Les codes 3 et 4 déclarent qu'**aucune vérification n'a eu lieu**."""
        return self.exit_code not in (3, 4)

    @property
    def passed(self) -> Optional[bool]:
        """`True`/`False` seulement si une vérification a eu lieu."""
        if not self.verification_performed:
            return None
        if self.exit_code == 0:
            return True
        if self.exit_code == 1:
            return False
        # Code 2 : la vérification est partielle, une dépendance
        # optionnelle manquait. Ni réussie, ni échouée.
        return None


def verify_evidence_archive(
    archive_path: str,
    *,
    strict: bool = False,
    extra_args: Optional[Sequence[str]] = None,
    executable: Optional[str] = None,
    timeout: float = 300.0,
) -> EvidenceVerification:
    """Vérifie une archive Evidence en invoquant le vérificateur indépendant.

    Le moteur Evidence **n'a aucune API** : c'est une collection de
    programmes en ligne de commande, et il n'est pas installable par
    `pip`. La surface publique installable est
    `pip install neomundi-evidence-verify`, qui pose la commande
    `neomundi-evidence`. Cette fonction l'invoque en sous-processus.

    ⚠ **Le corpus de conformité n'est pas dans la roue PyPI.** Les
    chemins de fixtures cités par la documentation du vérificateur
    n'existent qu'après un `git clone` du gateway. Un `pip install` seul
    permet de vérifier **vos** archives, pas de rejouer leur corpus.

    Args:
        archive_path: chemin de l'archive à vérifier.
        strict: ajoute `--strict`. ⚠ Sans la dépendance optionnelle
            `cryptography`, le vérificateur sort alors en **code 2** —
            vérification *incomplète*, et non échouée.
        extra_args: arguments supplémentaires passés tels quels.
        executable: chemin explicite du programme, si la commande n'est
            pas sur le `PATH`.
        timeout: délai en secondes.

    Raises:
        EvidenceVerifierUnavailable: programme absent, ou délai dépassé.
        ConfigurationError: argument invalide.
    """
    if not isinstance(archive_path, str) or not archive_path.strip():
        raise ConfigurationError("archive_path doit être une chaîne non vide.")
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
        raise ConfigurationError("timeout doit être un nombre > 0.")

    program = executable or shutil.which(EVIDENCE_COMMAND)
    if not program:
        raise EvidenceVerifierUnavailable(
            "Le vérificateur Evidence indépendant est absent : la commande "
            f"`{EVIDENCE_COMMAND}` n'est pas sur le PATH. "
            "Installer `pip install neomundi-evidence-verify`, puis contrôler "
            f"l'installation par `{EVIDENCE_COMMAND} doctor`. "
            "Aucun verdict n'est rendu : ce SDK ne vérifie pas lui-même."
        )

    command: List[str] = [program, "verify", archive_path]
    if strict:
        command.append("--strict")
    if extra_args:
        command.extend(str(a) for a in extra_args)

    try:
        completed = subprocess.run(  # noqa: S603 - programme nommé, pas de shell
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            env=_child_env(),
        )
    except FileNotFoundError as exc:
        raise EvidenceVerifierUnavailable(
            f"`{program}` est introuvable à l'exécution : {exc}."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise EvidenceVerifierUnavailable(
            f"Le vérificateur n'a pas répondu en {timeout} s. Aucune "
            "vérification n'a abouti ; ne pas lire ce délai comme un échec "
            "de vérification."
        ) from exc

    return EvidenceVerification(
        exit_code=completed.returncode,
        outcome=EVIDENCE_EXIT_CODES.get(
            completed.returncode, f"unknown_exit_code_{completed.returncode}"
        ),
        command=tuple(command),
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
        report=_first_json_object(completed.stdout or ""),
    )


# ---------------------------------------------------------------------
# Utilitaires internes
# ---------------------------------------------------------------------

def _child_env() -> Dict[str, str]:
    """L'environnement du sous-processus, **sans les clés d'API**.

    Le vérificateur est hors ligne et n'a besoin d'aucun secret. Les
    retirer évite qu'une clé se retrouve dans la ligne de commande, dans
    un journal d'erreur du programme appelé, ou dans un rapport de plantage.
    """
    blocked = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
    return {
        name: value
        for name, value in os.environ.items()
        if not any(marker in name.upper() for marker in blocked)
    }


def _first_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Le rapport JSON, s'il y en a un. Jamais fatal s'il n'y en a pas."""
    stripped = text.strip()
    if not stripped.startswith("{"):
        return None
    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _opt_bool(payload: Dict[str, Any], key: str) -> Optional[bool]:
    value = payload.get(key)
    return value if isinstance(value, bool) else None


def _opt_str(payload: Dict[str, Any], key: str) -> Optional[str]:
    value = payload.get(key)
    return value if isinstance(value, str) else None
