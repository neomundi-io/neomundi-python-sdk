"""La suite rejouée contre des charges CAPTURÉES depuis une instance réelle.

C'est la différence entre « le SDK est cohérent avec le contrat tel que je
l'ai lu » et « le SDK est cohérent avec ce qu'un serveur émet ». Les
fixtures `derived_from_code` établissent la première ; celles-ci
établissent la seconde.

`tests/fixtures/captured/` est **exclu du dépôt** (`.gitignore`) : ce sont
des données d'exécution, versionnées seulement après relecture explicite.
Ces tests sont donc **ignorés** quand le dossier est absent, et aucune CI
publique ne les exige.

Les fixtures sont produites par le harnais de capture interne
(hors dépôt) ; voir `KNOWN_LIMITATIONS.md` section 6 pour la
vérification minimale à mener contre un déploiement.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import json_responder, make_client
from neomundi import API_CONTRACT, MeasurementState
from neomundi.models import _KNOWN_ROOT_KEYS

CAPTURED = Path(__file__).parent / "fixtures" / "captured"

_FILES = sorted(CAPTURED.glob("*.json")) if CAPTURED.is_dir() else []

pytestmark = pytest.mark.skipif(
    not _FILES,
    reason=(
        "aucune fixture capturée — ce dossier est exclu du dépôt. "
        "Ces tests ne tournent que sur un poste qui a capturé des charges "
        "depuis une instance de test."
    ),
)


def _load(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in payload.items() if not k.startswith("_fixture_")}


def _result(path: Path):
    with make_client(json_responder(_load(path))) as client:
        return client.govern(token_count=1, latency_ms=1.0)


IDS = [p.stem for p in _FILES]


@pytest.mark.parametrize("path", _FILES, ids=IDS)
def test_la_charge_capturee_se_parse_sans_avertissement(path):
    """Le test décisif.

    Un `parse_warning` ici signifie que l'instance émet autre chose que ce
    que le contrat relevé déclare. Ce n'est **pas** un bug du SDK : c'est
    un constat d'audit, et il doit être remonté au backend plutôt
    qu'absorbé en élargissant le parsing.
    """
    r = _result(path)
    assert r.parse_warnings == [], [
        (w.path, w.expected, w.received_type, w.received_repr)
        for w in r.parse_warnings
    ]


@pytest.mark.parametrize("path", _FILES, ids=IDS)
def test_aucun_champ_racine_inconnu(path):
    """Un champ inconnu signifie que le backend a évolué depuis le commit
    de référence. Il faut alors étendre le SDK et incrémenter sa version,
    pas ignorer le champ."""
    payload = _load(path)
    unknown = sorted(set(payload) - _KNOWN_ROOT_KEYS)
    assert not unknown, f"champs non modélisés : {unknown}"


@pytest.mark.parametrize("path", _FILES, ids=IDS)
def test_les_quatre_blocs_requis_sont_presents(path):
    payload = _load(path)
    for block in ("governance", "metrics", "baseline", "audit"):
        assert isinstance(payload.get(block), dict), f"{block} absent"


@pytest.mark.parametrize("path", _FILES, ids=IDS)
def test_un_aller_retour_ne_perd_rien(path):
    payload = _load(path)
    assert _result(path).to_dict() == payload


@pytest.mark.parametrize("path", _FILES, ids=IDS)
def test_la_version_de_mesure_est_celle_que_le_sdk_modelise(path):
    """Si l'instance sert une autre version, les résultats ne sont pas
    comparables et des champs peuvent avoir changé de sens."""
    r = _result(path)
    assert r.audit.measurement_version == API_CONTRACT["measurement_version"], (
        f"instance={r.audit.measurement_version} "
        f"SDK={API_CONTRACT['measurement_version']}"
    )


@pytest.mark.parametrize("path", _FILES, ids=IDS)
def test_les_alias_racine_concordent_avec_les_blocs(path):
    r = _result(path)
    if r.quality is not None:
        assert r.g_score == r.quality.g_score
    if r.esi is not None:
        assert r.g_final == r.esi.g_final


@pytest.mark.parametrize("path", _FILES, ids=IDS)
def test_un_agregat_retenu_est_declare_comme_tel(path):
    """L'invariant central du produit, vérifié sur des charges réelles.

    Quand `g_score` est null, le serveur doit le DÉCLARER — par
    `decision_basis`, par `aggregates_publishable`, ou en nommant les
    signaux manquants. Un null non déclaré serait indistinguable d'une
    lacune de sérialisation.
    """
    r = _result(path)
    if r.g_score is not None:
        return
    declared = (
        r.governance.decision_basis == "incomplete_measurement"
        or r.aggregates_publishable is False
        or bool(r.missing_required_signals)
    )
    assert declared, (
        "g_score est null sans aucune déclaration : "
        f"basis={r.governance.decision_basis!r} "
        f"publishable={r.aggregates_publishable!r} "
        f"missing={r.missing_required_signals!r}"
    )


@pytest.mark.parametrize("path", _FILES, ids=IDS)
def test_un_signal_non_mesure_porte_toujours_une_cause(path):
    r = _result(path)
    for signal in (
        "coherence_score",
        "semantic_risk",
        "factual_hallucination_score",
        "semantic_instability_score",
    ):
        if r.measurement_state(signal) is MeasurementState.NOT_MEASURED:
            assert r.unmeasured_reason(signal), f"{signal} sans cause"


@pytest.mark.parametrize("path", _FILES, ids=IDS)
def test_un_signal_mesure_ne_porte_jamais_de_cause(path):
    r = _result(path)
    for signal in (
        "coherence_score",
        "semantic_risk",
        "factual_hallucination_score",
        "semantic_instability_score",
    ):
        if r.measurement_state(signal) is MeasurementState.MEASURED:
            assert r.unmeasured_reason(signal) is None, signal


@pytest.mark.parametrize("path", _FILES, ids=IDS)
def test_la_couverture_est_re_derivable(path):
    """`coverage` doit être recalculable depuis les deux compteurs
    publiés — c'est ce que le contrat promet au consommateur."""
    r = _result(path)
    m = r.measurement
    if m is None or not m.checks_attempted:
        return
    assert round(m.checks_succeeded / m.checks_attempted, 6) == m.coverage


@pytest.mark.parametrize("path", _FILES, ids=IDS)
def test_require_leve_proprement_sur_un_agregat_retenu(path):
    """Jamais de `TypeError` opaque : c'est la raison d'être de
    `require()`."""
    from neomundi import AggregateWithheldError

    r = _result(path)
    if r.g_score is not None:
        assert r.require("g_score") == r.g_score
    else:
        with pytest.raises(AggregateWithheldError):
            r.require("g_score")
    # `format_score` ne lève jamais, dans les deux cas.
    assert isinstance(r.format_score("g_score"), str)


def test_la_campagne_couvre_les_trois_familles_de_mesure():
    """Une capture qui ne couvrirait que le cas nominal ne validerait
    rien de ce qui distingue NeoMundi."""
    bases = set()
    for path in _FILES:
        r = _result(path)
        bases.add(r.governance.decision_basis)
    attendues = {
        "measured_thresholds",
        "incomplete_measurement",
        "no_check_attempted",
    }
    manquantes = attendues - bases
    assert not manquantes, f"familles non couvertes par les captures : {manquantes}"
