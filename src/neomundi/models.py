"""Modèles typés de la réponse `POST /v1/govern`.

Relevés de `govern-v3/app/models/responses.py` au commit
`68d6057cf620e430e6488da3cfcec9c471c75ed6` (version de mesure 3.3.0).

Trois règles gouvernent tout ce module.

**1. Rien n'est converti.** Le parsing *vérifie* le type, il ne le
*coerce* pas. Une chaîne `"0.5"` là où un nombre est attendu ne devient
pas `0.5` : le champ typé vaut `None`, la valeur brute reste accessible
dans `raw`, et un avertissement est consigné dans `parse_warnings`. Le
backend s'applique la même rigueur (`hallucination_detector._has_numeric`
refuse un booléen et accepte une chaîne numérique de façon explicite) ;
un SDK qui convertirait masquerait une dérive de contrat.

**2. `None` n'est jamais remplacé.** Aucune valeur par défaut numérique
n'existe dans ce module. Un `0.0` est une mesure ; un `None` est une
absence. Les confondre est le défaut que le backend a mis six chantiers
à fermer.

**3. Rien n'est interprété.** Aucun seuil, aucun verdict dérivé, aucun
raccourci sur un champ ambigu. Quand la sémantique d'un champ est
douteuse, il est exposé sous son chemin complet avec un avertissement.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .errors import AggregateWithheldError, InvalidResponseError

__all__ = [
    "MeasurementState",
    "COVERAGE_SIGNALS",
    "AGGREGATE_FIELDS",
    "ParseWarning",
    "Governance",
    "Measurement",
    "SuspectPhrase",
    "Quality",
    "Runtime",
    "Metrics",
    "Baseline",
    "Esi",
    "Density",
    "Citation",
    "UngroundedSnippet",
    "RagGrounding",
    "Audit",
    "GovernResult",
]


#: Les cinq signaux que le backend considère mesurables.
#: Relevé de `govern-v3/app/rgc/models.py:77-83` (`COVERAGE_SIGNALS`).
COVERAGE_SIGNALS: Tuple[str, ...] = (
    "stability_score",
    "coherence_score",
    "factual_hallucination_score",
    "semantic_instability_score",
    "semantic_risk",
)

#: Les agrégats que le backend publie `null` quand un signal requis n'a
#: pas pu être mesuré. Relevé de `governance.py:1360-1364, 1638-1648`.
AGGREGATE_FIELDS: Tuple[str, ...] = (
    "g_score",
    "g_final",
    "quality.g_score",
    "quality.stability_score",
    "metrics.energy_score",
    "metrics.stability_score",
    "esi.g_final",
    "esi.s_value",
    "esi.p_value",
    "esi.q_value",
    "esi.c_value",
    "esi.s_component",
    "esi.p_component",
    "esi.q_component",
    "esi.c_component",
)


class MeasurementState(str, Enum):
    """État de mesure d'un signal, tel que le serveur permet de l'établir.

    `NOT_ATTEMPTED_OR_GATED` est **délibérément ambigu**, parce que
    l'ambiguïté est dans le contrat et non dans le SDK : un signal absent
    de `measured_signals` **et** de `unmeasured_signals` peut être

    * un contrôle qui n'a jamais été lancé (désactivé pour le compte ou
      pour la plateforme) — le backend publie alors parfois une valeur de
      convention, par exemple `coherence_score: 1.0` ;
    * un signal masqué par le palier commercial — le backend publie alors
      `null`.

    Le serveur ne distingue pas ces deux cas sur le fil. Le SDK ne les
    invente donc pas. Lire `measurement.status` et `measurement.
    checks_attempted` pour lever une partie de l'ambiguïté.
    """

    MEASURED = "measured"
    NOT_MEASURED = "not_measured"
    NOT_ATTEMPTED_OR_GATED = "not_attempted_or_gated"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ParseWarning:
    """Un champ que le SDK n'a pas pu lire au type attendu.

    Sa présence ne fait jamais échouer un appel : un champ périphérique
    d'un type inattendu ne doit pas empêcher d'exploiter le reste de
    l'observation. Mais elle est exposée, pour qu'une dérive de contrat
    soit visible plutôt que silencieuse.
    """

    path: str
    expected: str
    received_type: str
    received_repr: str


# ---------------------------------------------------------------------
# Lecteurs non coercitifs
# ---------------------------------------------------------------------

def _warn(
    warnings: List[ParseWarning], path: str, expected: str, value: Any
) -> None:
    warnings.append(
        ParseWarning(
            path=path,
            expected=expected,
            received_type=type(value).__name__,
            received_repr=repr(value)[:120],
        )
    )


def _num(
    data: Mapping[str, Any], key: str, warnings: List[ParseWarning], path: str
) -> Optional[float]:
    """Un nombre, ou `None`. Ne convertit jamais une chaîne.

    `bool` est refusé explicitement : `True` est un `int` en Python, et un
    serveur qui répondrait `{"semantic_risk": true}` n'aurait rien mesuré.
    """
    if key not in data:
        return None
    value = data[key]
    if value is None:
        return None
    if isinstance(value, bool):
        _warn(warnings, f"{path}.{key}", "number", value)
        return None
    if isinstance(value, (int, float)):
        return float(value)
    _warn(warnings, f"{path}.{key}", "number", value)
    return None


def _int(
    data: Mapping[str, Any], key: str, warnings: List[ParseWarning], path: str
) -> Optional[int]:
    if key not in data:
        return None
    value = data[key]
    if value is None:
        return None
    if isinstance(value, bool):
        _warn(warnings, f"{path}.{key}", "integer", value)
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    _warn(warnings, f"{path}.{key}", "integer", value)
    return None


def _str(
    data: Mapping[str, Any], key: str, warnings: List[ParseWarning], path: str
) -> Optional[str]:
    if key not in data:
        return None
    value = data[key]
    if value is None:
        return None
    if isinstance(value, str):
        return value
    _warn(warnings, f"{path}.{key}", "string", value)
    return None


def _bool(
    data: Mapping[str, Any], key: str, warnings: List[ParseWarning], path: str
) -> Optional[bool]:
    if key not in data:
        return None
    value = data[key]
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    _warn(warnings, f"{path}.{key}", "boolean", value)
    return None


def _str_list(
    data: Mapping[str, Any], key: str, warnings: List[ParseWarning], path: str
) -> Optional[List[str]]:
    """Une liste de chaînes, ou `None`.

    `None` et `[]` sont distincts et le restent : le backend l'énonce
    explicitement pour `missing_required_signals` — « NULL, et non [],
    quand la ligne lue ne porte pas ce champ ; une liste vide serait
    l'affirmation que rien ne manquait ».
    """
    if key not in data:
        return None
    value = data[key]
    if value is None:
        return None
    if isinstance(value, list):
        out = [v for v in value if isinstance(v, str)]
        if len(out) != len(value):
            _warn(warnings, f"{path}.{key}", "list[string]", value)
        return out
    _warn(warnings, f"{path}.{key}", "list[string]", value)
    return None


def _num_list(
    data: Mapping[str, Any], key: str, warnings: List[ParseWarning], path: str
) -> Optional[List[float]]:
    if key not in data:
        return None
    value = data[key]
    if value is None:
        return None
    if isinstance(value, list):
        out: List[float] = []
        ok = True
        for v in value:
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                ok = False
                continue
            out.append(float(v))
        if not ok:
            _warn(warnings, f"{path}.{key}", "list[number]", value)
        return out
    _warn(warnings, f"{path}.{key}", "list[number]", value)
    return None


def _str_dict(
    data: Mapping[str, Any], key: str, warnings: List[ParseWarning], path: str
) -> Optional[Dict[str, str]]:
    if key not in data:
        return None
    value = data[key]
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items()}
    _warn(warnings, f"{path}.{key}", "dict[string,string]", value)
    return None


def _num_dict(
    data: Mapping[str, Any], key: str, warnings: List[ParseWarning], path: str
) -> Optional[Dict[str, float]]:
    if key not in data:
        return None
    value = data[key]
    if value is None:
        return None
    if isinstance(value, dict):
        out: Dict[str, float] = {}
        for k, v in value.items():
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                _warn(warnings, f"{path}.{key}.{k}", "number", v)
                continue
            out[str(k)] = float(v)
        return out
    _warn(warnings, f"{path}.{key}", "dict[string,number]", value)
    return None


def _block(
    data: Mapping[str, Any], key: str, warnings: List[ParseWarning], path: str
) -> Optional[Dict[str, Any]]:
    """Un sous-objet, ou `None` s'il est absent ou nul."""
    if key not in data:
        return None
    value = data[key]
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    _warn(warnings, f"{path}.{key}", "object", value)
    return None


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    """Analyse un horodatage ISO 8601, ou renvoie `None`.

    Le serveur produit `datetime.utcnow().isoformat()`, donc **sans
    fuseau**. Aucun fuseau n'est supposé ici : la valeur est rendue telle
    qu'elle a été analysée, et la chaîne brute reste disponible.
    """
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


# ---------------------------------------------------------------------
# Blocs
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class Governance:
    """Bloc `governance` — REQUIS dans le contrat."""

    #: `ALLOW` | `FLAG`. Mode OBS : jamais `DENY`.
    decision: Optional[str]
    #: `measured_thresholds` | `incomplete_measurement` | `no_check_attempted`.
    #:
    #: Ce n'est **pas** une sévérité. Un `FLAG` avec
    #: `incomplete_measurement` ne dit rien du contenu : il dit que la
    #: mesure ne s'est pas terminée. `None` pour une observation
    #: antérieure à la version 3.3.0 du backend — jamais présumé
    #: `measured_thresholds`.
    decision_basis: Optional[str]
    #: Taux de couverture instrumentale, PAS une confiance statistique.
    #: Égal à `measurement.coverage`. Dénominateur ≤ 3, donc valeurs
    #: possibles : 0, 1/3, 1/2, 2/3, 1.
    confidence: Optional[float]
    #: Quand `decision_basis == "incomplete_measurement"`, la première
    #: entrée est la raison d'incomplétude : l'ordre fait partie du
    #: contrat.
    reasons: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(
        cls, data: Mapping[str, Any], warnings: List[ParseWarning]
    ) -> "Governance":
        return cls(
            decision=_str(data, "decision", warnings, "governance"),
            decision_basis=_str(data, "decision_basis", warnings, "governance"),
            confidence=_num(data, "confidence", warnings, "governance"),
            reasons=_str_list(data, "reasons", warnings, "governance") or [],
        )


@dataclass(frozen=True)
class Measurement:
    """Bloc `measurement` — complétude de la mesure serveur."""

    #: `complete` | `partial` | `not_attempted`.
    status: Optional[str]
    #: Contrôles réellement LANCÉS. Un contrôle désactivé n'est pas
    #: compté : rien n'était attendu de lui.
    checks_attempted: Optional[int]
    checks_succeeded: Optional[int]
    #: `checks_succeeded / checks_attempted`, et la valeur de
    #: `confidence`. Vaut 1.0 quand rien n'a été tenté : à lire avec
    #: `status`, jamais seul.
    coverage: Optional[float]
    #: `measurement_coverage` | `no_server_check`.
    confidence_basis: Optional[str]
    #: Termes de G alimentés par une convention plutôt que par une mesure.
    degraded_g_inputs: List[str] = field(default_factory=list)
    #: Nom du contrôle -> cause lisible par machine.
    failed_checks: Dict[str, str] = field(default_factory=dict)
    #: `None`, et non `[]`, quand la ligne ne porte pas le champ : une
    #: liste vide serait l'affirmation que rien ne manquait.
    missing_required_signals: Optional[List[str]] = None
    #: `False` quand des signaux requis manquent. `None` — jamais `True`
    #: par défaut — quand la ligne ne le dit pas.
    aggregates_publishable: Optional[bool] = None

    @classmethod
    def from_dict(
        cls, data: Mapping[str, Any], warnings: List[ParseWarning]
    ) -> "Measurement":
        p = "measurement"
        return cls(
            status=_str(data, "status", warnings, p),
            checks_attempted=_int(data, "checks_attempted", warnings, p),
            checks_succeeded=_int(data, "checks_succeeded", warnings, p),
            coverage=_num(data, "coverage", warnings, p),
            confidence_basis=_str(data, "confidence_basis", warnings, p),
            degraded_g_inputs=_str_list(data, "degraded_g_inputs", warnings, p) or [],
            failed_checks=_str_dict(data, "failed_checks", warnings, p) or {},
            missing_required_signals=_str_list(
                data, "missing_required_signals", warnings, p
            ),
            aggregates_publishable=_bool(data, "aggregates_publishable", warnings, p),
        )


@dataclass(frozen=True)
class SuspectPhrase:
    """Extrait signalé par le juge de factualité (palier TIER_02+).

    AVERTISSEMENT hérité du backend. Quand le juge note une fausseté
    supérieure à 0,3 **sans** renvoyer d'extrait, le serveur publie les
    trois premières phrases de la réponse avec `category: "factual_error"`
    et une explication générique. **Aucun évaluateur n'a désigné ces
    phrases** : leur position dans le texte est leur seule qualification.
    Voir `hallucination_detector._extract_fallback_phrases`.

    Le SDK transporte ces extraits tels quels. Il ne peut pas distinguer
    un extrait désigné par le juge d'un extrait auto-extrait : le serveur
    ne le signale pas sur le fil.
    """

    text: Optional[str]
    severity: Optional[str]
    category: Optional[str]
    explanation: Optional[str]
    #: Index en CARACTÈRES dans la réponse, ou -1.
    offset: Optional[int]

    @classmethod
    def from_dict(
        cls, data: Mapping[str, Any], warnings: List[ParseWarning], index: int
    ) -> "SuspectPhrase":
        p = f"quality.suspect_phrases[{index}]"
        return cls(
            text=_str(data, "text", warnings, p),
            severity=_str(data, "severity", warnings, p),
            category=_str(data, "category", warnings, p),
            explanation=_str(data, "explanation", warnings, p),
            offset=_int(data, "offset", warnings, p),
        )


@dataclass(frozen=True)
class Quality:
    """Bloc `quality` — décomposition de G. Optionnel dans le contrat."""

    #: G brut. `None` quand un signal requis n'a pas été mesuré.
    g_score: Optional[float]
    #: `G / 0.60`. **1 = stable.**
    #:
    #: ATTENTION : `metrics.stability_score` porte le même nom avec
    #: l'échelle INVERSE (0 = stable). Les deux coexistent dans la même
    #: réponse. Voir `Metrics.stability_score`.
    #:
    #: Plage effective `[0.60 ; 1.00]` pour une réponse de longueur
    #: réaliste, et non `[0 ; 1]` : une hallucination maximale mesurée
    #: publie 0,667. Voir `docs/LIMITES.md`.
    stability_score: Optional[float]
    confidence: Optional[float]
    #: Similarité cosinus prompt↔réponse selon le modèle de plongement
    #: configuré. `None` quand le contrôle a tourné sans produire de
    #: mesure. Peut valoir 1.0 quand le contrôle n'a **jamais été lancé**
    #: — cas que le serveur ne signale dans aucune des deux listes de
    #: signaux.
    coherence_score: Optional[float]
    #: Verdict de modération. **Binaire** : 0.0 (`safe`) ou 0.85
    #: (`unsafe`). Ce n'est pas un score graduel.
    semantic_risk: Optional[float]
    #: Note de fausseté attribuée par un LLM-juge. `0.0` signifie « le
    #: juge n'a rien trouvé », jamais « il n'y a pas d'hallucination ».
    factual_hallucination_score: Optional[float]
    #: Ambiguïté estimée du **prompt**, et non instabilité de la réponse.
    #: Ce n'est pas la variance entre répétitions.
    semantic_instability_score: Optional[float]
    #: Densité de texte (TTR + compression + remplissage), dans [0,1].
    #: **N'entre dans aucun agrégat.** À ne pas confondre avec
    #: `density.informational_density`, qui alimente le terme P de
    #: `g_final`.
    information_density: Optional[float]
    suspect_phrases: Optional[List[SuspectPhrase]] = None

    @classmethod
    def from_dict(
        cls, data: Mapping[str, Any], warnings: List[ParseWarning]
    ) -> "Quality":
        p = "quality"
        phrases: Optional[List[SuspectPhrase]] = None
        raw_phrases = data.get("suspect_phrases")
        if isinstance(raw_phrases, list):
            phrases = [
                SuspectPhrase.from_dict(item, warnings, i)
                for i, item in enumerate(raw_phrases)
                if isinstance(item, dict)
            ]
        elif raw_phrases is not None:
            _warn(warnings, "quality.suspect_phrases", "list[object]", raw_phrases)
        return cls(
            g_score=_num(data, "g_score", warnings, p),
            stability_score=_num(data, "stability_score", warnings, p),
            confidence=_num(data, "confidence", warnings, p),
            coherence_score=_num(data, "coherence_score", warnings, p),
            semantic_risk=_num(data, "semantic_risk", warnings, p),
            factual_hallucination_score=_num(
                data, "factual_hallucination_score", warnings, p
            ),
            semantic_instability_score=_num(
                data, "semantic_instability_score", warnings, p
            ),
            information_density=_num(data, "information_density", warnings, p),
            suspect_phrases=phrases,
        )


@dataclass(frozen=True)
class Runtime:
    """Bloc `runtime` — santé d'infrastructure (R).

    **Strictement informatif** : R n'entre dans aucune décision. Absent
    (`None`) pour les paliers TRIAL et TIER_01.
    """

    r_score: Optional[float]
    latency_score: Optional[float]
    cost_score: Optional[float]
    e_token: Optional[float]
    energy_score: Optional[float]

    @classmethod
    def from_dict(
        cls, data: Mapping[str, Any], warnings: List[ParseWarning]
    ) -> "Runtime":
        p = "runtime"
        return cls(
            r_score=_num(data, "r_score", warnings, p),
            latency_score=_num(data, "latency_score", warnings, p),
            cost_score=_num(data, "cost_score", warnings, p),
            e_token=_num(data, "e_token", warnings, p),
            energy_score=_num(data, "energy_score", warnings, p),
        )


@dataclass(frozen=True)
class Metrics:
    """Bloc `metrics` — REQUIS dans le contrat, tous champs nullables.

    Bloc de compatibilité historique. Ses deux premiers champs sont une
    renormalisation de G **en risque**.
    """

    #: `1 − G/0.60`. **0 = pas de risque.** Orientation inverse de
    #: `quality.stability_score`.
    energy_score: Optional[float]
    e_token: Optional[float]
    cost_proxy: Optional[float]
    latency_proxy: Optional[float]
    #: **ÉCHELLE INVERSÉE.** Même valeur que `energy_score`, soit
    #: `1 − G/0.60` : ici **0 = stable**, alors que
    #: `quality.stability_score` vaut `G/0.60`, où **1 = stable**.
    #:
    #: Les deux champs portent le même nom dans la même réponse. Le SDK
    #: conserve les deux chemins complets et n'en expose aucun raccourci :
    #: choisir l'un des deux sens serait trancher une ambiguïté du
    #: contrat.
    stability_score: Optional[float]

    @classmethod
    def from_dict(
        cls, data: Mapping[str, Any], warnings: List[ParseWarning]
    ) -> "Metrics":
        p = "metrics"
        return cls(
            energy_score=_num(data, "energy_score", warnings, p),
            e_token=_num(data, "e_token", warnings, p),
            cost_proxy=_num(data, "cost_proxy", warnings, p),
            latency_proxy=_num(data, "latency_proxy", warnings, p),
            stability_score=_num(data, "stability_score", warnings, p),
        )


@dataclass(frozen=True)
class Baseline:
    """Bloc `baseline` — REQUIS dans le contrat, tous champs nullables."""

    reference_energy: Optional[float]
    observed_energy: Optional[float]
    #: **AVERTISSEMENT — signe ambigu.** La description du champ côté
    #: serveur annonce `observed_energy - reference_energy`
    #: (`responses.py:504-511`), tandis que l'implémentation calcule
    #: `reference − observed` (`governance.py:1552`), soit l'OPPOSÉ.
    #:
    #: Le SDK expose la valeur **telle quelle** et ne recalcule rien.
    #: Divergence signalée à l'équipe backend ; tant qu'elle n'est pas
    #: tranchée, ne pas déduire de signe de ce champ.
    delta_E: Optional[float]
    #: `calibrating` | `calibrated` | `None`.
    calibration_status: Optional[str]
    #: Stabilité en fenêtre glissante de `observed_energy`, calculée EN
    #: MÉMOIRE PAR PROCESSUS côté serveur et perdue au redémarrage.
    #: **Sans rapport avec `esi.q_value`**, qui est `min(1, N/E)`.
    esi_q: Optional[float]
    esi_bootstrap: Optional[bool]

    @classmethod
    def from_dict(
        cls, data: Mapping[str, Any], warnings: List[ParseWarning]
    ) -> "Baseline":
        p = "baseline"
        return cls(
            reference_energy=_num(data, "reference_energy", warnings, p),
            observed_energy=_num(data, "observed_energy", warnings, p),
            delta_E=_num(data, "delta_E", warnings, p),
            calibration_status=_str(data, "calibration_status", warnings, p),
            esi_q=_num(data, "esi_q", warnings, p),
            esi_bootstrap=_bool(data, "esi_bootstrap", warnings, p),
        )


@dataclass(frozen=True)
class Esi:
    """Bloc `esi` — agrégat `g_final`. Optionnel (TIER_02+).

    `g_final = β_S·S + β_P·P + β_Q·Q + β_C·C`.

    AVERTISSEMENTS hérités, voir `docs/LIMITES.md` :

    * les quatre termes ne sont **pas indépendants** : `p_value` et
      `q_value` sont la même expression `N/(N+3H)`, dérivée du score de
      fausseté qui alimente déjà `s_value` ; `c_value` est la cohérence,
      qui alimente aussi `s_value` ;
    * `p_value` et `q_value` sont **saturés à ≈1** dès qu'une réponse
      dépasse quelques dizaines de tokens — leur amplitude totale est de
      0,006 à 500 tokens ;
    * la plage effective de `g_final` est donc `[0.40 ; 1.00]`, et non
      `[0 ; 1]`.
    """

    g_final: Optional[float]
    s_component: Optional[float]
    p_component: Optional[float]
    q_component: Optional[float]
    c_component: Optional[float]
    s_value: Optional[float]
    p_value: Optional[float]
    q_value: Optional[float]
    c_value: Optional[float]
    #: Poids effectivement appliqués. Peuvent être personnalisés par
    #: compte (TIER_02+) : **deux comptes aux β différents produisent des
    #: `g_final` non comparables**, et rien d'autre dans la réponse ne le
    #: signale.
    betas: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], warnings: List[ParseWarning]) -> "Esi":
        p = "esi"
        return cls(
            g_final=_num(data, "g_final", warnings, p),
            s_component=_num(data, "s_component", warnings, p),
            p_component=_num(data, "p_component", warnings, p),
            q_component=_num(data, "q_component", warnings, p),
            c_component=_num(data, "c_component", warnings, p),
            s_value=_num(data, "s_value", warnings, p),
            p_value=_num(data, "p_value", warnings, p),
            q_value=_num(data, "q_value", warnings, p),
            c_value=_num(data, "c_value", warnings, p),
            betas=_num_dict(data, "betas", warnings, p) or {},
        )


@dataclass(frozen=True)
class Density:
    """Bloc `density` — Dv, E, Di. Optionnel (TIER_02+)."""

    #: Ratio tokens de sortie / **caractères** de prompt. Les deux termes
    #: ne sont pas dans la même unité ; `volumetric_density_basis` le
    #: déclare.
    volumetric_density: Optional[float]
    volumetric_density_basis: Optional[str]
    #: `E = N + 3H`. Le terme de risque est borné par 3, quelle que soit
    #: la longueur de la réponse.
    informational_energy: Optional[float]
    #: `Di = (N + 3H)/N`, dans `[1, +∞[`. Alimente le terme P de
    #: `g_final` via `P = 1/Di`. **À ne pas confondre avec
    #: `quality.information_density`**, qui mesure une densité de texte et
    #: n'entre dans aucun agrégat.
    informational_density: Optional[float]
    #: Coefficient appliqué au terme de risque, déclaré côté backend comme
    #: un choix architectural fondateur et non un paramètre réglable.
    risk_coefficient: Optional[int]
    #: `False` quand E et Di ont été dérivés d'un score de fausseté qui
    #: n'a pas été mesuré : un `Di` de 1.0 n'est alors **pas** une preuve
    #: de pureté.
    factual_input_measured: Optional[bool]
    unmeasured_reason: Optional[str]

    @classmethod
    def from_dict(
        cls, data: Mapping[str, Any], warnings: List[ParseWarning]
    ) -> "Density":
        p = "density"
        return cls(
            volumetric_density=_num(data, "volumetric_density", warnings, p),
            volumetric_density_basis=_str(
                data, "volumetric_density_basis", warnings, p
            ),
            informational_energy=_num(data, "informational_energy", warnings, p),
            informational_density=_num(data, "informational_density", warnings, p),
            risk_coefficient=_int(data, "risk_coefficient", warnings, p),
            factual_input_measured=_bool(data, "factual_input_measured", warnings, p),
            unmeasured_reason=_str(data, "unmeasured_reason", warnings, p),
        )


@dataclass(frozen=True)
class Citation:
    """Citation produite par le juge d'ancrage documentaire."""

    text: Optional[str]
    document_title: Optional[str]

    @classmethod
    def from_dict(
        cls, data: Mapping[str, Any], warnings: List[ParseWarning], index: int
    ) -> "Citation":
        p = f"rag_grounding.citations[{index}]"
        return cls(
            text=_str(data, "text", warnings, p),
            document_title=_str(data, "document_title", warnings, p),
        )


@dataclass(frozen=True)
class UngroundedSnippet:
    """Phrase de la réponse non retrouvée dans le corpus fourni."""

    quote: Optional[str]
    max_similarity: Optional[float]

    @classmethod
    def from_dict(
        cls, data: Mapping[str, Any], warnings: List[ParseWarning], index: int
    ) -> "UngroundedSnippet":
        p = f"rag_grounding.ungrounded[{index}]"
        return cls(
            quote=_str(data, "quote", warnings, p),
            max_similarity=_num(data, "max_similarity", warnings, p),
        )


@dataclass(frozen=True)
class RagGrounding:
    """Bloc `rag_grounding` — ancrage documentaire. Optionnel (TIER_02+)."""

    grounding_score: Optional[float]
    is_grounded: Optional[bool]
    best_doc_index: Optional[int]
    best_doc_snippet: Optional[str]
    per_doc_scores: List[float] = field(default_factory=list)
    model_used: Optional[str] = None
    #: `chat` (juge conversationnel) | `rerank` (juge de reclassement ou
    #: repli par plongements).
    judge_mode: Optional[str] = None
    ungrounded: List[UngroundedSnippet] = field(default_factory=list)
    citations: List[Citation] = field(default_factory=list)
    ungrounded_claims: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(
        cls, data: Mapping[str, Any], warnings: List[ParseWarning]
    ) -> "RagGrounding":
        p = "rag_grounding"
        raw_ung = data.get("ungrounded")
        ungrounded = [
            UngroundedSnippet.from_dict(item, warnings, i)
            for i, item in enumerate(raw_ung or [])
            if isinstance(item, dict)
        ]
        raw_cit = data.get("citations")
        citations = [
            Citation.from_dict(item, warnings, i)
            for i, item in enumerate(raw_cit or [])
            if isinstance(item, dict)
        ]
        return cls(
            grounding_score=_num(data, "grounding_score", warnings, p),
            is_grounded=_bool(data, "is_grounded", warnings, p),
            best_doc_index=_int(data, "best_doc_index", warnings, p),
            best_doc_snippet=_str(data, "best_doc_snippet", warnings, p),
            per_doc_scores=_num_list(data, "per_doc_scores", warnings, p) or [],
            model_used=_str(data, "model_used", warnings, p),
            judge_mode=_str(data, "judge_mode", warnings, p),
            ungrounded=ungrounded,
            citations=citations,
            ungrounded_claims=_str_list(data, "ungrounded_claims", warnings, p) or [],
        )


@dataclass(frozen=True)
class Audit:
    """Bloc `audit` — REQUIS dans le contrat.

    `measurement_version` est **le seul numéro qui ait un sens
    scientifique** : deux résultats produits sous deux valeurs
    différentes ne sont pas comparables pour une même entrée.

    Il peut valoir `"unknown"` : une observation enregistrée avant que ce
    bloc ne soit persisté ne peut pas dire sous quelle version elle a été
    produite, et le serveur refuse d'y apposer la version du jour.
    """

    measurement_version: Optional[str]
    normalizer_version: Optional[str]
    #: `trace-{request_id[:8]}`. **Non unique par construction** : huit
    #: caractères hexadécimaux.
    trace_id: Optional[str]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], warnings: List[ParseWarning]) -> "Audit":
        p = "audit"
        return cls(
            measurement_version=_str(data, "measurement_version", warnings, p),
            normalizer_version=_str(data, "normalizer_version", warnings, p),
            trace_id=_str(data, "trace_id", warnings, p),
        )


# ---------------------------------------------------------------------
# Résultat
# ---------------------------------------------------------------------

#: Blocs que le contrat déclare non-`Optional`. Leur absence est une
#: violation de contrat, pas une donnée manquante.
_REQUIRED_BLOCKS = ("governance", "metrics", "baseline", "audit")

_KNOWN_ROOT_KEYS = frozenset(
    {
        "request_id",
        "timestamp",
        "system_id",
        "mode",
        "g_score",
        "g_final",
        "v_score",
        "delta_g",
        "checks_emitted",
        "trajectory_points",
        "measured_signals",
        "measurement",
        "unmeasured_signals",
        "processing_time_ms",
        "latency_ms",
        "model",
        "evaluators",
        "provider",
        "governance",
        "quality",
        "runtime",
        "metrics",
        "baseline",
        "audit",
        "density",
        "esi",
        "rag_grounding",
    }
)


@dataclass(frozen=True)
class GovernResult:
    """Résultat d'un appel `POST /v1/govern`.

    Une observation est immuable (`frozen=True`) : elle décrit ce qui a
    été constaté à un instant, elle ne se modifie pas.

    `raw` conserve **toujours** la charge JSON intégrale, y compris les
    champs que cette version du SDK ne connaît pas.
    """

    # --- identité ---
    request_id: Optional[str]
    #: Chaîne brute. Le serveur l'émet sans fuseau horaire.
    timestamp_raw: Optional[str]
    #: Analyse de `timestamp_raw`, ou `None` si elle échoue. **Aucun
    #: fuseau n'est supposé.**
    timestamp: Optional[datetime]
    system_id: Optional[str]
    mode: Optional[str]

    # --- alias racine ---
    #: Alias de `quality.g_score`. Le serveur garantit la même valeur,
    #: y compris quand elle est `None`.
    g_score: Optional[float]
    #: Alias de `esi.g_final`.
    g_final: Optional[float]
    #: `1 − factual_hallucination_score`. `None` quand le juge n'a rien
    #: mesuré.
    v_score: Optional[float]
    #: Écart de G avec la requête PRÉCÉDENTE DU MÊME COMPTE, quelle que
    #: soit la question posée. Fenêtre d'une heure côté serveur.
    #:
    #: AVERTISSEMENT : ce champ peut porter un nombre alors que `g_score`
    #: vaut `None`, et le serveur mémorise 0.0 comme référence quand
    #: l'agrégat est retenu — le delta suivant en est alors faussé. Ne pas
    #: lire ce champ comme une mesure de dérive.
    delta_g: Optional[float]

    # --- compteurs ---
    #: Analyses serveur ayant produit un résultat exploitable.
    checks_emitted: Optional[int]
    #: Toujours `None` sur cette route : il n'y a pas de trajectoire sur
    #: un appel unique. `None` signifie « sans objet ici », pas « zéro ».
    trajectory_points: Optional[int]

    # --- provenance ---
    measured_signals: Optional[List[str]]
    unmeasured_signals: Optional[Dict[str, str]]
    #: Provenance par signal : instrument, modèle, statut, cause, et les
    #: empreintes `prompt_template_hash`, `inference_config_hash`,
    #: `config_fingerprint`. Ces trois empreintes sont le seul moyen de
    #: vérifier que deux observations ont été produites sous la même
    #: configuration d'évaluateur.
    evaluators: Optional[Dict[str, Dict[str, Any]]]

    # --- divers ---
    processing_time_ms: Optional[float]
    latency_ms: Optional[float]
    model: Optional[str]
    #: Toujours `None` sur cette route : l'appelant a invoqué son
    #: fournisseur lui-même.
    provider: Optional[str]

    # --- blocs ---
    governance: Governance
    metrics: Metrics
    baseline: Baseline
    audit: Audit
    quality: Optional[Quality] = None
    runtime: Optional[Runtime] = None
    measurement: Optional[Measurement] = None
    density: Optional[Density] = None
    esi: Optional[Esi] = None
    rag_grounding: Optional[RagGrounding] = None

    # --- diagnostic ---
    #: Charge JSON intégrale, telle que reçue.
    raw: Dict[str, Any] = field(default_factory=dict)
    #: Clés racine que cette version du SDK ne connaît pas. Conservées
    #: dans `raw`. Leur présence n'est jamais une erreur : un backend qui
    #: ajoute un champ ne doit pas casser une intégration.
    unknown_fields: List[str] = field(default_factory=list)
    #: Champs qui n'ont pas pu être lus au type attendu. Jamais fatal,
    #: toujours exposé.
    parse_warnings: List[ParseWarning] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "GovernResult":
        """Construit un résultat depuis une charge JSON déjà décodée.

        Lève `InvalidResponseError` si la charge n'est pas un objet ou si
        un bloc requis manque.
        """
        if not isinstance(payload, dict):
            raise InvalidResponseError(
                "La réponse n'est pas un objet JSON.", body=payload
            )

        missing = [b for b in _REQUIRED_BLOCKS if not isinstance(payload.get(b), dict)]
        if missing:
            raise InvalidResponseError(
                "Bloc(s) requis absent(s) ou non conforme(s) dans la réponse : "
                + ", ".join(missing)
                + ". Le contrat les déclare obligatoires ; leur absence est une "
                "violation de contrat, pas un signal non mesuré.",
                body=payload,
                request_id=payload.get("request_id")
                if isinstance(payload.get("request_id"), str)
                else None,
            )

        w: List[ParseWarning] = []
        root = "root"

        ts_raw = _str(payload, "timestamp", w, root)
        quality_raw = _block(payload, "quality", w, root)
        runtime_raw = _block(payload, "runtime", w, root)
        measurement_raw = _block(payload, "measurement", w, root)
        density_raw = _block(payload, "density", w, root)
        esi_raw = _block(payload, "esi", w, root)
        rag_raw = _block(payload, "rag_grounding", w, root)

        evaluators: Optional[Dict[str, Dict[str, Any]]] = None
        ev = payload.get("evaluators")
        if isinstance(ev, dict):
            evaluators = {
                str(k): dict(v) for k, v in ev.items() if isinstance(v, dict)
            }
            if len(evaluators) != len(ev):
                _warn(w, "root.evaluators", "dict[string,object]", ev)
        elif ev is not None:
            _warn(w, "root.evaluators", "dict[string,object]", ev)

        return cls(
            request_id=_str(payload, "request_id", w, root),
            timestamp_raw=ts_raw,
            timestamp=_parse_dt(ts_raw),
            system_id=_str(payload, "system_id", w, root),
            mode=_str(payload, "mode", w, root),
            g_score=_num(payload, "g_score", w, root),
            g_final=_num(payload, "g_final", w, root),
            v_score=_num(payload, "v_score", w, root),
            delta_g=_num(payload, "delta_g", w, root),
            checks_emitted=_int(payload, "checks_emitted", w, root),
            trajectory_points=_int(payload, "trajectory_points", w, root),
            measured_signals=_str_list(payload, "measured_signals", w, root),
            unmeasured_signals=_str_dict(payload, "unmeasured_signals", w, root),
            evaluators=evaluators,
            processing_time_ms=_num(payload, "processing_time_ms", w, root),
            latency_ms=_num(payload, "latency_ms", w, root),
            model=_str(payload, "model", w, root),
            provider=_str(payload, "provider", w, root),
            governance=Governance.from_dict(payload["governance"], w),
            metrics=Metrics.from_dict(payload["metrics"], w),
            baseline=Baseline.from_dict(payload["baseline"], w),
            audit=Audit.from_dict(payload["audit"], w),
            quality=Quality.from_dict(quality_raw, w) if quality_raw else None,
            runtime=Runtime.from_dict(runtime_raw, w) if runtime_raw else None,
            measurement=(
                Measurement.from_dict(measurement_raw, w) if measurement_raw else None
            ),
            density=Density.from_dict(density_raw, w) if density_raw else None,
            esi=Esi.from_dict(esi_raw, w) if esi_raw else None,
            rag_grounding=RagGrounding.from_dict(rag_raw, w) if rag_raw else None,
            raw=dict(payload),
            unknown_fields=sorted(set(payload) - _KNOWN_ROOT_KEYS),
            parse_warnings=w,
        )

    # ------------------------------------------------------------------
    # Lecture de l'état de mesure
    # ------------------------------------------------------------------

    def measurement_state(self, signal: str) -> MeasurementState:
        """L'état de mesure d'un signal, déduit de ce que le serveur publie.

        Dérivé **uniquement** de `measured_signals` et
        `unmeasured_signals`. Le SDK n'invente rien : voir
        `MeasurementState` pour la raison du cas ambigu.
        """
        if self.measured_signals is None and self.unmeasured_signals is None:
            return MeasurementState.UNKNOWN
        if self.measured_signals and signal in self.measured_signals:
            return MeasurementState.MEASURED
        if self.unmeasured_signals and signal in self.unmeasured_signals:
            return MeasurementState.NOT_MEASURED
        return MeasurementState.NOT_ATTEMPTED_OR_GATED

    def is_measured(self, signal: str) -> bool:
        """`True` seulement si le serveur a déclaré ce signal mesuré.

        N'interroge jamais la valeur numérique : en panne, chaque
        instrument du backend renvoie la valeur la plus rassurante
        possible, et c'est précisément pourquoi la validité ne se lit pas
        sur le nombre.
        """
        return self.measurement_state(signal) is MeasurementState.MEASURED

    def unmeasured_reason(self, signal: str) -> Optional[str]:
        """La cause publiée par le serveur, ou `None` s'il n'y en a pas.

        `None` ne signifie pas « mesuré » : un signal jamais lancé n'a pas
        de cause. Utiliser `measurement_state()` pour distinguer.
        """
        if not self.unmeasured_signals:
            return None
        return self.unmeasured_signals.get(signal)

    def evaluator_of(self, signal: str) -> Optional[Dict[str, Any]]:
        """Le bloc de provenance d'un signal, ou `None`."""
        if not self.evaluators:
            return None
        entry = self.evaluators.get(signal)
        return dict(entry) if isinstance(entry, dict) else None

    @property
    def aggregates_publishable(self) -> Optional[bool]:
        """`False` quand un signal requis n'a pas été mesuré.

        `None` — jamais `True` par défaut — quand le serveur ne le dit
        pas : un `True` ferait prétendre à toute observation ancienne que
        ses agrégats étaient complets.
        """
        return self.measurement.aggregates_publishable if self.measurement else None

    @property
    def missing_required_signals(self) -> Optional[List[str]]:
        """Les signaux requis que cette requête n'a pas pu mesurer.

        `None`, et non `[]`, quand le serveur ne porte pas l'information.
        """
        if self.measurement is None:
            return None
        signals = self.measurement.missing_required_signals
        return list(signals) if signals is not None else None

    @property
    def measurement_incomplete(self) -> bool:
        """`True` seulement si le serveur l'a déclaré explicitement.

        Deux déclarations équivalentes sont acceptées :
        `decision_basis == "incomplete_measurement"` et
        `measurement.aggregates_publishable is False`. En l'absence des
        deux, renvoie `False` — ce qui veut dire « non déclaré », et non
        « garanti complet ». Lire `aggregates_publishable` pour
        distinguer.
        """
        if self.governance.decision_basis == "incomplete_measurement":
            return True
        return self.aggregates_publishable is False

    # ------------------------------------------------------------------
    # Lecture sûre des valeurs
    # ------------------------------------------------------------------

    def get(self, path: str, default: Any = None) -> Any:
        """Lit un chemin pointé dans la charge **brute**.

        Exemples : `get("quality.stability_score")`,
        `get("esi.betas.beta_s")`.

        `default` n'est renvoyé que si le chemin est **absent**. Un `null`
        présent dans la charge renvoie `None` — la distinction entre
        « champ absent » et « champ nul » est préservée. Utiliser
        `field_present()` pour la tester directement.
        """
        found, value = _resolve(self.raw, path)
        return value if found else default

    def field_present(self, path: str) -> bool:
        """`True` si le chemin existe dans la charge, même à `null`."""
        found, _ = _resolve(self.raw, path)
        return found

    def require(self, path: str) -> Any:
        """La valeur d'un champ, ou une exception qui en nomme la cause.

        Conçu contre l'erreur d'intégration la plus courante :
        `f"{result.g_score:.2f}"`, qui lève un `TypeError` opaque dès
        qu'un agrégat est retenu.

        Lève `AggregateWithheldError` quand la valeur est `None`, en y
        joignant `missing_required_signals` et `decision_basis` lorsque le
        serveur les publie. **N'invente aucune valeur de remplacement.**
        """
        found, value = _resolve(self.raw, path)
        if not found:
            raise AggregateWithheldError(
                f"Le champ '{path}' est absent de la réponse.",
                field=path,
                missing_required_signals=self.missing_required_signals,
                decision_basis=self.governance.decision_basis,
            )
        if value is None:
            missing = self.missing_required_signals
            if missing:
                why = (
                    "la mesure est incomplète : signal(s) requis non mesuré(s) "
                    f"({', '.join(missing)})"
                )
            elif self.governance.decision_basis == "incomplete_measurement":
                why = "le serveur a déclaré la mesure incomplète"
            else:
                why = (
                    "le serveur a publié null — signal non mesuré, non tenté, "
                    "ou masqué par le palier commercial"
                )
            raise AggregateWithheldError(
                f"Le champ '{path}' vaut null : {why}.",
                field=path,
                missing_required_signals=missing,
                decision_basis=self.governance.decision_basis,
            )
        return value

    def format_score(
        self, path: str, nd: int = 4, when_none: str = "non mesuré"
    ) -> str:
        """Formate un champ numérique, ou renvoie `when_none`.

        Ne lève jamais. À utiliser pour l'affichage ; `require()` pour un
        calcul qui a besoin d'une valeur.
        """
        found, value = _resolve(self.raw, path)
        if not found or value is None:
            return when_none
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return when_none
        return f"{float(value):.{nd}f}"

    def to_dict(self) -> Dict[str, Any]:
        """La charge brute, telle que reçue.

        Volontairement la charge d'origine et non une re-sérialisation des
        dataclasses : un aller-retour ne doit rien perdre, pas même un
        champ que cette version du SDK ignore.
        """
        return dict(self.raw)

    def __repr__(self) -> str:
        return (
            f"GovernResult(request_id={self.request_id!r}, "
            f"decision={self.governance.decision!r}, "
            f"decision_basis={self.governance.decision_basis!r}, "
            f"g_score={self.g_score!r}, "
            f"measurement_version={self.audit.measurement_version!r})"
        )


def _resolve(payload: Mapping[str, Any], path: str) -> Tuple[bool, Any]:
    """Résout un chemin pointé. Renvoie `(trouvé, valeur)`."""
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


# Garde-fou : `dataclasses` est importé pour que les outils de typage
# reconnaissent le module comme un module de dataclasses ; cette
# référence empêche un linter de supprimer l'import.
_ = dataclasses.fields
