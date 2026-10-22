"""Compatibilité du SDK avec la version de mesure **3.3.1** du backend.

Ce module existe parce que le déploiement de production sert `3.3.1`
tandis que le SDK a été dérivé de `68d6057` / `3.3.0`. Il répond à une
question précise, et à une seule :

    la surface REST que ce SDK modélise est-elle la même sous 3.3.1 ?

**Ce que ces tests établissent.** Le SDK lit sans perte ni avertissement
une réponse `POST /v1/govern` réellement émise par la production sous
`3.3.1`, et le consommateur reste capable de détecter l'écart de version.

**Ce qu'ils n'établissent pas.** Ils ne sont pas un appel du SDK contre le
service hébergé : la charge est **rejouée** par transport simulé. Aucun
test de ce dépôt ne peut établir le comportement live, et aucun ne le
prétend — voir `KNOWN_LIMITATIONS.md` §6.

**La fixture est assainie.** Identifiants et identité des évaluateurs ont
été remplacés par des valeurs factices ; structure, types, nullité et
toutes les valeurs de mesure sont conservées telles qu'émises. La charge
d'origine ne porte aucun texte de prompt ni de réponse. Les champs
remplacés sont énumérés dans `_fixture_redacted`.

Pourquoi un module séparé de `test_captured_fixtures.py` : celui-ci
exige, à juste titre, que chaque capture porte exactement la version
déclarée par `API_CONTRACT`. Mêler les deux campagnes dans un même
dossier effacerait cette garantie-là. Ici l'écart de version **est** le
sujet.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import json_responder, make_client
from neomundi import API_CONTRACT, AggregateWithheldError, MeasurementState
from neomundi.models import _KNOWN_ROOT_KEYS

PROD_331 = Path(__file__).parent / "fixtures" / "production_331"

_FILES = sorted(PROD_331.glob("*.json"))

#: La version servie par le déploiement observé le 2026-10-21.
SERVED_VERSION = "3.3.1"


def _load(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in payload.items() if not k.startswith("_fixture_")}


def _result(path: Path):
    with make_client(json_responder(_load(path))) as client:
        return client.govern(token_count=1, latency_ms=1.0)


IDS = [p.stem for p in _FILES]


def test_la_campagne_331_porte_au_moins_une_charge():
    """Un dossier vide ferait passer tous les tests paramétrés sans rien
    vérifier. Le dire explicitement évite une validation fantôme."""
    assert _FILES, f"aucune charge 3.3.1 dans {PROD_331}"


@pytest.mark.parametrize("path", _FILES, ids=IDS)
def test_la_charge_331_annonce_bien_3_3_1(path):
    assert _result(path).audit.measurement_version == SERVED_VERSION


@pytest.mark.parametrize("path", _FILES, ids=IDS)
def test_la_charge_331_se_parse_sans_aucun_avertissement(path):
    """Le test décisif de ce module.

    Un `parse_warning` signifierait que 3.3.1 émet un type que le contrat
    relevé à `68d6057` ne déclare pas. Il n'y en a aucun : c'est ce qui
    fonde la compatibilité du périmètre REST.
    """
    r = _result(path)
    assert r.parse_warnings == [], [
        (w.path, w.expected, w.received_type, w.received_repr)
        for w in r.parse_warnings
    ]


@pytest.mark.parametrize("path", _FILES, ids=IDS)
def test_3_3_1_n_ajoute_aucun_champ_racine(path):
    """Si 3.3.1 avait étendu la surface REST, un champ racine inconnu
    apparaîtrait ici. Aucun n'apparaît."""
    unknown = sorted(set(_load(path)) - _KNOWN_ROOT_KEYS)
    assert not unknown, f"champs non modélisés sous 3.3.1 : {unknown}"


@pytest.mark.parametrize("path", _FILES, ids=IDS)
def test_un_aller_retour_ne_perd_rien_sous_331(path):
    payload = _load(path)
    assert _result(path).to_dict() == payload


@pytest.mark.parametrize("path", _FILES, ids=IDS)
def test_les_quatre_blocs_requis_sont_presents_sous_331(path):
    payload = _load(path)
    for block in ("governance", "metrics", "baseline", "audit"):
        assert isinstance(payload.get(block), dict), f"{block} absent"


@pytest.mark.parametrize("path", _FILES, ids=IDS)
def test_les_alias_racine_concordent_sous_331(path):
    r = _result(path)
    if r.quality is not None:
        assert r.g_score == r.quality.g_score
    if r.esi is not None:
        assert r.g_final == r.esi.g_final


@pytest.mark.parametrize("path", _FILES, ids=IDS)
def test_la_couverture_reste_re_derivable_sous_331(path):
    r = _result(path)
    m = r.measurement
    assert m is not None and m.checks_attempted
    assert round(m.checks_succeeded / m.checks_attempted, 6) == m.coverage


@pytest.mark.parametrize("path", _FILES, ids=IDS)
def test_l_ecart_de_version_reste_detectable_par_le_consommateur(path):
    """La vérification que la documentation prescrit doit **fonctionner**,
    pas seulement exister.

    `API_CONTRACT["measurement_version"]` nomme le commit de dérivation,
    pas la liste des versions vérifiées : une simple inégalité se
    déclenche donc ici. C'est voulu — mais elle ne doit pas être lue comme
    une incompatibilité du périmètre REST, et
    `verified_measurement_versions` est le champ qui tranche.
    """
    served = _result(path).audit.measurement_version
    assert served != API_CONTRACT["measurement_version"]
    assert served in API_CONTRACT["verified_measurement_versions"]


def test_le_contrat_declare_les_deux_versions_verifiees():
    """`3.3.0` est la version de dérivation ; `3.3.1` a été vérifiée par
    rejeu d'une réponse de production. Les deux, et rien d'autre."""
    assert API_CONTRACT["verified_measurement_versions"] == ("3.3.0", "3.3.1")
    assert API_CONTRACT["measurement_version"] == "3.3.0"


@pytest.mark.parametrize("path", _FILES, ids=IDS)
def test_la_provenance_par_evaluateur_est_exposee_sous_331(path):
    """Les douze champs de provenance par signal sont la seule façon de
    vérifier que deux observations partagent une configuration. Le SDK les
    transporte en l'état, y compris leurs `null`."""
    r = _result(path)
    assert r.evaluators is not None
    for signal in ("factual_hallucination_score", "semantic_instability_score"):
        ev = r.evaluator_of(signal)
        assert ev is not None, signal
        for key in (
            "evaluator",
            "model_used",
            "model_configured",
            "status",
            "reason",
            "served_by",
            "attempts",
            "latency_ms",
            "evaluator_runtime",
            "prompt_template_hash",
            "inference_config_hash",
            "config_fingerprint",
        ):
            assert key in ev, f"{signal}.{key} absent"


@pytest.mark.parametrize("path", _FILES, ids=IDS)
def test_une_empreinte_absente_reste_absente_sous_331(path):
    """**Constat de production, pas un défaut du SDK.**

    Sous 3.3.1, seuls les signaux produits par le juge de factualité
    portent les trois empreintes de configuration ; `stability_score`,
    `coherence_score` et `semantic_risk` les publient à `null`. Deux
    observations ne sont donc **pas** comparables empreinte par empreinte
    sur ces trois signaux-là. Le SDK l'expose ; il n'invente aucune
    valeur de remplacement.
    """
    r = _result(path)
    for signal in ("stability_score", "coherence_score", "semantic_risk"):
        ev = r.evaluator_of(signal)
        if ev is None:
            continue
        if ev.get("status") == "measured":
            assert ev["config_fingerprint"] is None, (
                f"{signal} porte désormais une empreinte : le constat ci-dessus "
                "a changé, et la documentation doit suivre"
            )


@pytest.mark.parametrize("path", _FILES, ids=IDS)
def test_les_homonymes_restent_inverses_sous_331(path):
    """`quality.stability_score` = G/0.60 et `metrics.stability_score`
    = 1 − G/0.60 coexistent toujours sous 3.3.1. Le SDK garde les deux
    chemins complets et n'expose aucun raccourci."""
    r = _result(path)
    if r.quality is None or r.quality.stability_score is None:
        pytest.skip("aucune valeur de stabilité publiée sur cette charge")
    assert r.metrics.stability_score is not None
    assert round(r.quality.stability_score + r.metrics.stability_score, 6) == 1.0


@pytest.mark.parametrize("path", _FILES, ids=IDS)
def test_le_signe_de_delta_E_reste_celui_de_l_implementation_sous_331(path):
    """BL hérité, non refermé par 3.3.1 : la description serveur annonce
    `observed − reference`, l'implémentation calcule `reference −
    observed`. La charge le confirme encore. Le SDK ne recalcule rien."""
    b = _result(path).baseline
    if None in (b.reference_energy, b.observed_energy, b.delta_E):
        pytest.skip("énergies non publiées sur cette charge")
    assert round(b.delta_E, 6) == round(b.reference_energy - b.observed_energy, 6)


@pytest.mark.parametrize("path", _FILES, ids=IDS)
def test_un_agregat_publie_sous_331_est_lisible_par_require(path):
    r = _result(path)
    if r.g_score is None:
        with pytest.raises(AggregateWithheldError):
            r.require("g_score")
    else:
        assert r.require("g_score") == r.g_score
    assert isinstance(r.format_score("g_score"), str)


@pytest.mark.parametrize("path", _FILES, ids=IDS)
def test_les_champs_sans_objet_sur_REST_restent_nuls_sous_331(path):
    """`trajectory_points` et `provider` sont « sans objet ici », pas
    « zéro ». 3.3.1 ne change rien à cela sur le chemin REST."""
    r = _result(path)
    assert r.trajectory_points is None
    assert r.provider is None


@pytest.mark.parametrize("path", _FILES, ids=IDS)
def test_un_signal_mesure_sous_331_est_declare_mesure(path):
    r = _result(path)
    for signal in r.measured_signals or []:
        assert r.measurement_state(signal) is MeasurementState.MEASURED
        assert r.unmeasured_reason(signal) is None


@pytest.mark.parametrize("path", _FILES, ids=IDS)
def test_la_fixture_331_ne_porte_aucun_texte_d_execution(path):
    """Garde-fou de confidentialité, vérifié mécaniquement : cette
    campagne ne doit jamais versionner de prompt, de réponse ou
    d'extrait."""
    payload = _load(path)
    assert payload.get("quality", {}).get("suspect_phrases") in (None, [])
    assert payload.get("rag_grounding") is None
    for absent in ("llm_response", "llm_prompt", "documents", "rag_context"):
        assert absent not in payload


def test_la_fixture_331_declare_ce_qui_a_ete_assaini():
    """Une fixture issue de la production doit dire ce qu'on lui a retiré,
    sans quoi un lecteur la croirait verbatim."""
    for path in _FILES:
        meta = json.loads(path.read_text(encoding="utf-8"))
        assert meta.get("_fixture_origin") == "captured", path.name
        redacted = meta.get("_fixture_redacted")
        assert isinstance(redacted, list) and redacted, path.name
        assert "request_id" in redacted, path.name
        assert "audit.trace_id" in redacted, path.name
