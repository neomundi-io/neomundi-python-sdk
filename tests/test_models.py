"""Parsing des réponses : mesure complète, partielle, `null`, champs inconnus.

Couvre les points 4, 5, 6, 7 et 12 de la Phase C.
"""

from __future__ import annotations

import pytest

from conftest import json_responder, load_fixture, make_client
from neomundi import GovernResult, InvalidResponseError, MeasurementState


def _result(payload):
    with make_client(json_responder(payload)) as client:
        return client.govern(token_count=128, latency_ms=842.0)


# ---------------------------------------------------------------------
# 4. Réponse entièrement mesurée
# ---------------------------------------------------------------------

def test_mesure_complete_tous_les_blocs_sont_peuples(full_payload):
    r = _result(full_payload)
    assert r.request_id == "11111111-2222-3333-4444-555555555555"
    assert r.mode == "OBS"
    assert r.governance.decision == "ALLOW"
    assert r.governance.decision_basis == "measured_thresholds"
    assert r.quality is not None
    assert r.runtime is not None
    assert r.measurement is not None
    assert r.density is not None
    assert r.esi is not None
    assert r.audit.measurement_version == "3.3.0"


def test_mesure_complete_les_valeurs_sont_celles_du_serveur(full_payload):
    r = _result(full_payload)
    assert r.g_score == 0.492
    assert r.quality.stability_score == 0.82
    assert r.quality.coherence_score == 0.72
    assert r.quality.factual_hallucination_score == 0.12
    assert r.esi.g_final == 0.870878
    assert r.esi.betas["beta_s"] == 0.4
    assert r.density.risk_coefficient == 3


def test_les_cinq_signaux_sont_mesures(full_payload):
    r = _result(full_payload)
    for signal in (
        "stability_score",
        "coherence_score",
        "semantic_risk",
        "factual_hallucination_score",
        "semantic_instability_score",
    ):
        assert r.is_measured(signal) is True
        assert r.measurement_state(signal) is MeasurementState.MEASURED
        assert r.unmeasured_reason(signal) is None


def test_l_horodatage_est_conserve_en_brut_et_analyse(full_payload):
    r = _result(full_payload)
    assert r.timestamp_raw == "2026-10-17T09:14:22.481233"
    assert r.timestamp is not None
    assert r.timestamp.year == 2026
    # Le serveur n'envoie pas de fuseau ; le SDK n'en suppose aucun.
    assert r.timestamp.tzinfo is None


def test_la_provenance_expose_les_empreintes_de_configuration(full_payload):
    """Les trois empreintes sont le seul moyen de vérifier que deux
    observations ont été produites sous la même configuration."""
    r = _result(full_payload)
    ev = r.evaluator_of("factual_hallucination_score")
    assert ev["model_used"] == "llama3.2:3b"
    assert ev["served_by"] == "primary"
    assert ev["config_fingerprint"] == "c40d9e71bb2a6f08"
    assert ev["prompt_template_hash"] == "9f2c41ab77d0e513"


def test_les_alias_racine_concordent_avec_les_blocs(full_payload):
    """Le serveur promet « même valeur, jamais différente »."""
    r = _result(full_payload)
    assert r.g_score == r.quality.g_score
    assert r.g_final == r.esi.g_final


def test_aucun_avertissement_de_parsing_sur_une_charge_nominale(full_payload):
    r = _result(full_payload)
    assert r.parse_warnings == []
    assert r.unknown_fields == []


# ---------------------------------------------------------------------
# 5. Réponse partiellement mesurée · 7. Signal non mesuré
# ---------------------------------------------------------------------

def test_mesure_partielle_les_agregats_sont_null(partial_payload):
    r = _result(partial_payload)
    assert r.g_score is None
    assert r.g_final is None
    assert r.v_score is None
    assert r.quality.stability_score is None
    assert r.quality.g_score is None
    assert r.esi.g_final is None
    assert r.metrics.energy_score is None
    assert r.metrics.stability_score is None


def test_mesure_partielle_les_signaux_mesures_gardent_leur_valeur(partial_payload):
    """L'invariant central : ce qui a été mesuré n'est pas perdu."""
    r = _result(partial_payload)
    assert r.quality.coherence_score == 0.81
    assert r.quality.semantic_risk == 0.0
    assert r.is_measured("coherence_score") is True
    assert r.is_measured("semantic_risk") is True


def test_mesure_partielle_la_cause_est_lisible(partial_payload):
    r = _result(partial_payload)
    assert r.is_measured("factual_hallucination_score") is False
    assert (
        r.measurement_state("factual_hallucination_score")
        is MeasurementState.NOT_MEASURED
    )
    assert (
        r.unmeasured_reason("factual_hallucination_score")
        == "hallucination_judge_unavailable"
    )
    ev = r.evaluator_of("factual_hallucination_score")
    assert ev["status"] == "not_measured"
    # Un appel qui n'a pas abouti n'a pas de modèle à nommer…
    assert ev["model_used"] is None
    # …mais la cible de l'appel reste un fait de configuration.
    assert ev["model_configured"] == "llama3.2:3b"
    assert ev["attempts"] == 1


def test_mesure_partielle_est_declaree_explicitement(partial_payload):
    r = _result(partial_payload)
    assert r.measurement_incomplete is True
    assert r.aggregates_publishable is False
    assert r.missing_required_signals == ["hallucination_score"]
    assert r.governance.decision == "FLAG"
    assert r.governance.decision_basis == "incomplete_measurement"


def test_la_raison_d_incompletude_est_en_premiere_position(partial_payload):
    """L'ordre fait partie du contrat : un affichage qui montre une ligne
    doit montrer la bonne."""
    r = _result(partial_payload)
    assert "Measurement incomplete" in r.governance.reasons[0]


def test_le_bloc_measurement_permet_de_recalculer_la_confidence(partial_payload):
    r = _result(partial_payload)
    m = r.measurement
    assert m.checks_attempted == 3
    assert m.checks_succeeded == 2
    assert round(m.checks_succeeded / m.checks_attempted, 6) == m.coverage
    assert m.degraded_g_inputs == ["hallucination_score"]
    assert m.failed_checks == {"hallucination": "hallucination_judge_unavailable"}


def test_density_declare_que_son_entree_factuelle_n_est_pas_mesuree(partial_payload):
    """Un Di de 1.0 dérivé d'un juge muet n'est pas une preuve de pureté."""
    r = _result(partial_payload)
    assert r.density.informational_density == 1.0
    assert r.density.factual_input_measured is False
    assert r.density.unmeasured_reason == "hallucination_judge_unavailable"


# ---------------------------------------------------------------------
# 6. Valeurs null — la distinction centrale
# ---------------------------------------------------------------------

def test_zero_et_null_sont_distinguables(full_payload, partial_payload):
    """Le défaut que le backend a mis six chantiers à fermer ne doit pas
    être réintroduit côté client."""
    complete = _result(full_payload)
    partial = _result(partial_payload)

    # Un 0.0 mesuré reste 0.0, et le signal est déclaré mesuré.
    assert complete.quality.semantic_risk == 0.0
    assert complete.is_measured("semantic_risk") is True

    # Un signal non mesuré est None, et il porte une cause.
    assert partial.quality.factual_hallucination_score is None
    assert partial.is_measured("factual_hallucination_score") is False

    # Et les deux états ne se confondent jamais : un 0.0 mesuré n'est pas
    # None, et un None n'est pas un 0.0. `==` et non `is` : comparer un
    # flottant par identité n'a pas de sens, et levait un SyntaxWarning.
    assert complete.quality.semantic_risk is not None
    assert complete.quality.semantic_risk == 0.0
    assert partial.quality.factual_hallucination_score is None
    assert partial.quality.factual_hallucination_score != 0.0


def test_null_n_est_jamais_remplace_par_zero(partial_payload):
    r = _result(partial_payload)
    for value in (
        r.g_score,
        r.g_final,
        r.v_score,
        r.quality.stability_score,
        r.esi.s_value,
        r.metrics.energy_score,
    ):
        assert value is None


def test_une_liste_vide_et_une_liste_absente_sont_distinctes(
    full_payload, partial_payload
):
    """`missing_required_signals` : `None` ≠ `[]`. Le backend l'énonce
    explicitement — une liste vide serait l'affirmation que rien ne
    manquait."""
    complete = _result(full_payload)
    assert complete.missing_required_signals == []
    payload = dict(partial_payload)
    payload["measurement"] = {
        k: v
        for k, v in payload["measurement"].items()
        if k != "missing_required_signals"
    }
    legacy = _result(payload)
    assert legacy.missing_required_signals is None


def test_aggregates_publishable_absent_reste_none(full_payload):
    """Jamais `True` par défaut : cela ferait prétendre à une observation
    ancienne que ses agrégats étaient complets."""
    payload = dict(full_payload)
    payload["measurement"] = {
        k: v
        for k, v in payload["measurement"].items()
        if k != "aggregates_publishable"
    }
    r = _result(payload)
    assert r.aggregates_publishable is None
    assert r.measurement_incomplete is False  # non déclaré ≠ garanti complet


def test_le_cas_non_tente_est_distinct_du_cas_non_mesure(not_attempted_payload):
    r = _result(not_attempted_payload)
    assert r.measurement.status == "not_attempted"
    assert r.measurement.coverage == 1.0
    assert r.measurement.confidence_basis == "no_server_check"
    assert r.governance.decision_basis == "no_check_attempted"
    # Les agrégats SONT publiés : rien n'était attendu des contrôles.
    assert r.g_score == 0.6
    # Et le signal non lancé n'est dans AUCUNE des deux listes.
    assert (
        r.measurement_state("coherence_score")
        is MeasurementState.NOT_ATTEMPTED_OR_GATED
    )
    assert r.unmeasured_reason("coherence_score") is None


def test_un_signal_masque_par_le_palier_n_est_pas_declare_mesure(gated_payload):
    """Le SDK ne tranche pas entre « masqué » et « jamais lancé » : le
    serveur ne les distingue pas sur le fil."""
    r = _result(gated_payload)
    assert r.quality.coherence_score is None
    assert (
        r.measurement_state("coherence_score")
        is MeasurementState.NOT_ATTEMPTED_OR_GATED
    )
    # Alors que la mesure, elle, était complète côté serveur.
    assert r.measurement.status == "complete"
    assert r.aggregates_publishable is True


def test_les_blocs_absents_valent_none(gated_payload):
    r = _result(gated_payload)
    assert r.runtime is None
    assert r.density is None
    assert r.esi is None
    assert r.rag_grounding is None
    # Mais les blocs requis sont là.
    assert r.governance is not None
    assert r.metrics is not None
    assert r.baseline is not None
    assert r.audit is not None


def test_l_etat_est_unknown_sans_listes_de_signaux(full_payload):
    payload = {
        k: v
        for k, v in full_payload.items()
        if k not in ("measured_signals", "unmeasured_signals")
    }
    r = _result(payload)
    assert r.measurement_state("coherence_score") is MeasurementState.UNKNOWN


# ---------------------------------------------------------------------
# Lecture sûre : require / format_score / get / field_present
# ---------------------------------------------------------------------

def test_require_leve_une_exception_explicative_sur_un_agregat_retenu(
    partial_payload,
):
    """Contre le `TypeError` opaque de `f"{r.g_score:.2f}"`."""
    from neomundi import AggregateWithheldError

    r = _result(partial_payload)
    with pytest.raises(AggregateWithheldError) as exc:
        r.require("g_score")
    assert exc.value.field == "g_score"
    assert exc.value.missing_required_signals == ["hallucination_score"]
    assert exc.value.decision_basis == "incomplete_measurement"
    assert "hallucination_score" in str(exc.value)


def test_require_renvoie_la_valeur_quand_elle_existe(full_payload):
    r = _result(full_payload)
    assert r.require("g_score") == 0.492
    assert r.require("quality.coherence_score") == 0.72
    assert r.require("esi.betas.beta_s") == 0.4


def test_require_sur_un_champ_absent_le_dit(full_payload):
    from neomundi import AggregateWithheldError

    r = _result(full_payload)
    with pytest.raises(AggregateWithheldError, match="absent"):
        r.require("quality.champ_inexistant")


def test_format_score_ne_leve_jamais(partial_payload, full_payload):
    assert _result(full_payload).format_score("g_score", nd=2) == "0.49"
    assert _result(partial_payload).format_score("g_score") == "non mesuré"
    assert (
        _result(partial_payload).format_score("g_score", when_none="n/a") == "n/a"
    )
    assert _result(full_payload).format_score("chemin.inexistant") == "non mesuré"


def test_get_distingue_absent_et_nul(partial_payload):
    r = _result(partial_payload)
    assert r.get("g_score") is None
    assert r.get("champ_absent", default="sentinelle") == "sentinelle"
    assert r.field_present("g_score") is True
    assert r.field_present("champ_absent") is False


def test_to_dict_rend_la_charge_integrale(full_payload):
    r = _result(full_payload)
    assert r.to_dict() == full_payload


# ---------------------------------------------------------------------
# 12. Champs inconnus et dérive de type
# ---------------------------------------------------------------------

def test_un_champ_racine_inconnu_est_conserve_et_signale(drift_payload):
    r = _result(drift_payload)
    assert "un_champ_que_le_sdk_ignore" in r.unknown_fields
    assert "autre_champ_inconnu" in r.unknown_fields
    assert r.raw["autre_champ_inconnu"] == 123
    assert r.get("un_champ_que_le_sdk_ignore.ajoute") == (
        "par une version future du backend"
    )


def test_un_champ_inconnu_ne_fait_jamais_echouer_l_appel(drift_payload):
    """Un backend qui ajoute un champ ne doit pas casser une intégration."""
    r = _result(drift_payload)
    assert isinstance(r, GovernResult)
    assert r.governance.decision == "ALLOW"


def test_une_chaine_numerique_n_est_jamais_convertie(drift_payload):
    """Convertir `"0.492"` en `0.492` masquerait une dérive de contrat."""
    r = _result(drift_payload)
    assert r.g_score is None
    assert r.raw["g_score"] == "0.492"
    paths = [w.path for w in r.parse_warnings]
    assert "root.g_score" in paths


def test_un_booleen_n_est_jamais_lu_comme_un_nombre(drift_payload):
    """`True` est un `int` en Python ; un serveur qui répondrait
    `{"semantic_risk": true}` n'aurait rien mesuré."""
    r = _result(drift_payload)
    assert r.g_final is None
    assert r.quality.semantic_risk is None
    paths = [w.path for w in r.parse_warnings]
    assert "root.g_final" in paths
    assert "quality.semantic_risk" in paths


def test_un_horodatage_illisible_ne_fait_pas_echouer(drift_payload):
    r = _result(drift_payload)
    assert r.timestamp_raw == "pas-une-date"
    assert r.timestamp is None


def test_les_avertissements_portent_le_chemin_et_le_type_recu(drift_payload):
    r = _result(drift_payload)
    assert r.parse_warnings
    w = next(w for w in r.parse_warnings if w.path == "root.g_score")
    assert w.expected == "number"
    assert w.received_type == "str"
    assert "0.492" in w.received_repr


def test_une_liste_mixte_est_filtree_et_signalee(drift_payload):
    r = _result(drift_payload)
    assert r.measured_signals == ["coherence_score"]
    assert "root.measured_signals" in [w.path for w in r.parse_warnings]


# ---------------------------------------------------------------------
# Blocs requis : leur absence est une violation de contrat
# ---------------------------------------------------------------------

@pytest.mark.parametrize("block", ["governance", "metrics", "baseline", "audit"])
def test_un_bloc_requis_absent_leve(full_payload, block):
    payload = {k: v for k, v in full_payload.items() if k != block}
    with pytest.raises(InvalidResponseError, match=block):
        _result(payload)


def test_une_charge_non_objet_leve():
    with pytest.raises(InvalidResponseError):
        GovernResult.from_dict([1, 2, 3])  # type: ignore[arg-type]


# ---------------------------------------------------------------------
# Les pièges de nommage sont conservés, pas lissés
# ---------------------------------------------------------------------

def test_les_deux_stability_score_restent_deux_attributs_distincts(full_payload):
    """`quality.stability_score` = G/0.60 (1 = stable).
    `metrics.stability_score` = 1 − G/0.60 (0 = stable).

    Le SDK n'expose aucun raccourci : choisir un des deux sens serait
    trancher une ambiguïté du contrat.
    """
    r = _result(full_payload)
    assert r.quality.stability_score == 0.82
    assert r.metrics.stability_score == 0.18
    assert round(r.quality.stability_score + r.metrics.stability_score, 6) == 1.0
    assert not hasattr(r, "stability_score")


def test_les_deux_q_restent_distincts(full_payload):
    r = _result(full_payload)
    assert r.esi.q_value == 0.997195  # min(1, N/E)
    assert r.baseline.esi_q == 0.9413  # CV en fenêtre glissante
    assert r.esi.q_value != r.baseline.esi_q


def test_les_deux_densites_restent_distinctes(full_payload):
    r = _result(full_payload)
    assert r.quality.information_density == 0.6412  # TTR + gzip, n'entre nulle part
    assert r.density.informational_density == 1.002813  # alimente P de g_final


def test_delta_E_est_expose_brut_sans_recalcul(full_payload):
    """La description serveur annonce `observed - reference`, le code
    calcule `reference - observed`. Le SDK n'arbitre pas."""
    r = _result(full_payload)
    assert r.baseline.delta_E == -0.015012
    # Ce n'est PAS reference - observed tel que le SDK le recalculerait…
    assert r.baseline.reference_energy == 0.05
    assert r.baseline.observed_energy == 0.065012
    # …et le SDK ne corrige rien : il rend la valeur du serveur.


def test_trajectory_points_et_provider_sont_nuls_en_rest(full_payload):
    """`None` signifie « sans objet ici », pas « zéro »."""
    r = _result(full_payload)
    assert r.trajectory_points is None
    assert r.provider is None


def test_le_resultat_est_immuable(full_payload):
    import dataclasses

    r = _result(full_payload)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.g_score = 1.0  # type: ignore[misc]


def test_les_fixtures_declarent_leur_origine():
    """Exigence Phase C §7 : une fixture est relevée du code, ou
    explicitement synthétique."""
    import json
    from pathlib import Path

    fixtures = Path(__file__).parent / "fixtures"
    files = sorted(fixtures.rglob("*.json"))
    assert files, "aucune fixture trouvée"
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        origin = payload.get("_fixture_origin")
        assert origin in {"derived_from_code", "synthetic"}, path.name


def test_les_fixtures_nominales_sont_derivees_du_code():
    import json
    from pathlib import Path

    fixtures = Path(__file__).parent / "fixtures"
    for name in (
        "full_measurement.json",
        "partial_measurement.json",
        "gated_tier01.json",
        "no_check_attempted.json",
    ):
        payload = json.loads((fixtures / name).read_text(encoding="utf-8"))
        assert payload["_fixture_origin"] == "derived_from_code", name
