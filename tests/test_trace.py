"""Étape TRACE — et surtout ce qu'elle refuse d'affirmer.

Ces tests ne vérifient pas seulement que `trace()` fonctionne : ils
verrouillent les quatre refus qui font la différence entre une trace et
une fausse trace.

1. aucune valeur de substitution pour `token_count` ;
2. aucune requête quand l'appel applicatif a échoué ;
3. aucune requête du tout quand `submit=False` ;
4. jamais « enregistré » sans que le serveur l'ait dit.
"""

from __future__ import annotations

import json

import httpx
import pytest

from conftest import RequestRecorder, json_responder, make_client
from neomundi import ConfigurationError, TraceRecord
from neomundi.streaming import StreamResult


# ---------------------------------------------------------------------
# Le chemin nominal
# ---------------------------------------------------------------------

def test_la_trace_mesure_la_latence_au_lieu_de_la_demander(full_payload):
    """La latence envoyée est celle du bloc, pas une valeur fournie.

    C'est la seule simplification réelle que le contrat déployé autorise :
    `latency_ms` reste requis par le serveur, mais plus par l'appelant.
    """
    recorder = RequestRecorder()
    client = make_client(json_responder(full_payload), recorder=recorder)

    with client:
        with client.trace(model_name="gpt-4o") as t:
            t.record(prompt="Question ?", response="Réponse.", token_count=42)

    corps = recorder.last_json()
    assert corps["raw_metrics"]["token_count"] == 42
    envoyee = corps["raw_metrics"]["latency_ms"]
    assert isinstance(envoyee, float)
    # `>= 0.0` et non `> 0.0` : sur Windows, `time.monotonic()` a une
    # granularité d'environ 15,6 ms, et un bloc instantané mesure donc
    # réellement 0,0. Arrondir vers le haut pour « faire joli » serait
    # fabriquer une mesure. Le test suivant éprouve une vraie durée.
    assert envoyee >= 0.0
    # La même valeur, à l'identique, est republiée dans la trace.
    assert t.record_.latency_ms == pytest.approx(envoyee)
    assert corps["raw_metrics"]["model_name"] == "gpt-4o"
    # Longueurs en CARACTÈRES, convention du contrat serveur.
    assert corps["raw_metrics"]["prompt_length"] == len("Question ?")
    assert corps["raw_metrics"]["response_length"] == len("Réponse.")


def test_une_duree_reelle_est_mesuree_et_transmise(full_payload):
    """Un bloc qui dure vraiment produit une latence strictement positive.

    La borne est volontairement très basse : ce test éprouve que
    l'horloge est bien lue autour du bloc, pas la précision de l'horloge
    de la machine de CI.
    """
    import time as _time

    recorder = RequestRecorder()
    client = make_client(json_responder(full_payload), recorder=recorder)
    with client:
        with client.trace() as t:
            _time.sleep(0.05)
            t.record(response="ok", token_count=1)

    envoyee = recorder.last_json()["raw_metrics"]["latency_ms"]
    assert envoyee >= 25.0, envoyee
    assert t.record_.latency_ms == pytest.approx(envoyee)


def test_la_trace_rend_l_identifiant_serveur_et_le_couple_de_correlation(full_payload):
    client = make_client(json_responder(full_payload))
    with client:
        with client.trace(client_trace_id="commande-4711") as t:
            t.record(response="ok", token_count=1)

    record = t.record_
    assert record.outcome == "submitted"
    assert record.submitted is True
    assert record.acknowledged is True
    assert record.request_id == full_payload["request_id"]
    assert record.client_trace_id == "commande-4711"
    assert record.transport == "rest"
    assert record.result is not None


def test_l_identifiant_de_correlation_part_dans_metadata(full_payload):
    """Le contrat expose le champ ; la route déployée ne le conserve pas.

    Il est envoyé quand même — le champ existe et un backend futur peut
    le retenir — mais aucun test, aucune docstring et aucun README ne doit
    présenter cela comme une corrélation côté serveur.
    """
    recorder = RequestRecorder()
    client = make_client(json_responder(full_payload), recorder=recorder)
    with client:
        with client.trace(client_trace_id="abc-123") as t:
            t.record(response="ok", token_count=7)
    assert recorder.last_json()["metadata"]["client_trace_id"] == "abc-123"


def test_un_identifiant_est_genere_quand_l_appelant_n_en_donne_pas(full_payload):
    client = make_client(json_responder(full_payload))
    with client:
        with client.trace() as t:
            t.record(response="ok", token_count=1)
    assert t.record_.client_trace_id
    assert len(t.record_.client_trace_id) == 32


def test_les_metadonnees_de_l_appelant_sont_preservees(full_payload):
    recorder = RequestRecorder()
    client = make_client(json_responder(full_payload), recorder=recorder)
    with client:
        with client.trace(metadata={"tenant": "acme"}) as t:
            t.record(response="ok", token_count=1, metadata={"etape": "resume"})
    envoye = recorder.last_json()["metadata"]
    assert envoye["tenant"] == "acme"
    assert envoye["etape"] == "resume"
    assert "client_trace_id" in envoye


def test_l_identifiant_de_l_appelant_n_est_pas_ecrase(full_payload):
    """Si l'appelant pose lui-même `metadata["client_trace_id"]`, il gagne."""
    recorder = RequestRecorder()
    client = make_client(json_responder(full_payload), recorder=recorder)
    with client:
        with client.trace(metadata={"client_trace_id": "le-mien"}) as t:
            t.record(response="ok", token_count=1)
    assert recorder.last_json()["metadata"]["client_trace_id"] == "le-mien"


# ---------------------------------------------------------------------
# Les quatre refus
# ---------------------------------------------------------------------

def test_sans_token_count_rien_n_est_envoye(full_payload):
    """Refus n°1 : aucune estimation de tokens.

    Le serveur l'exige, et il ne compte rien lui-même
    (`token_count_source: "caller_declared"`). Une valeur inventée
    entrerait dans `cost_proxy` et dans la densité volumétrique, donc
    dans des chiffres présentés comme mesurés.
    """
    recorder = RequestRecorder()
    client = make_client(json_responder(full_payload), recorder=recorder)
    with client:
        with pytest.raises(ConfigurationError) as exc:
            with client.trace() as t:
                t.record(response="une réponse sans décompte")
    assert "token_count" in str(exc.value)
    assert recorder.count == 0, "une requête a été émise sans décompte de tokens"


def test_un_echec_applicatif_ne_produit_aucune_observation(full_payload):
    """Refus n°2 : pas d'interaction complète, pas de mesure.

    Et l'exception de l'appelant n'est pas masquée.
    """
    recorder = RequestRecorder()
    client = make_client(json_responder(full_payload), recorder=recorder)
    with client:
        with pytest.raises(RuntimeError, match="le fournisseur est tombé"):
            with client.trace() as t:
                t.record(token_count=10)
                raise RuntimeError("le fournisseur est tombé")

    assert recorder.count == 0
    assert t.record_.outcome == "not_submitted_application_error"
    assert t.record_.submitted is False
    assert t.record_.acknowledged is False
    assert t.record_.request_id is None
    # La latence a quand même été mesurée : elle décrit l'échec.
    assert t.record_.latency_ms is not None


def test_submit_false_n_ouvre_aucune_socket(full_payload):
    """Refus n°3 : une instrumentation locale reste locale."""
    recorder = RequestRecorder()
    client = make_client(json_responder(full_payload), recorder=recorder)
    with client:
        with client.trace(submit=False) as t:
            t.record(response="ok", token_count=3)

    assert recorder.count == 0
    assert t.record_.outcome == "not_submitted_local_only"
    assert t.record_.submitted is False
    assert t.record_.token_count == 3
    assert t.record_.latency_ms is not None
    assert t.record_.result is None


def test_registered_reste_none_sur_rest(full_payload):
    """Refus n°4, le plus important.

    `POST /v1/govern` répond 200 **même quand l'écriture du journal a
    échoué** : la route journalise l'erreur et continue. Son contrat ne
    publie donc aucun champ de persistance, et le SDK n'a pas le droit
    d'en déduire un.
    """
    client = make_client(json_responder(full_payload))
    with client:
        with client.trace() as t:
            t.record(response="ok", token_count=1)

    assert t.record_.acknowledged is True, "le serveur a bien accusé réception"
    assert t.record_.registered is None, (
        "REST ne confirme aucun enregistrement : `registered` doit rester None"
    )


# ---------------------------------------------------------------------
# Rejeu, idempotence, erreurs
# ---------------------------------------------------------------------

def test_refermer_deux_fois_n_emet_qu_une_requete(full_payload):
    """La route n'est pas idempotente : un second envoi créerait une
    seconde observation facturée pour une seule interaction."""
    recorder = RequestRecorder()
    client = make_client(json_responder(full_payload), recorder=recorder)
    with client:
        trace = client.trace()
        with trace as t:
            t.record(response="ok", token_count=1)
        premier = t.record_
        assert trace.close() is premier
        assert trace.close() is premier
    assert recorder.count == 1


def test_une_erreur_api_remonte_sans_trace_fabriquee():
    """Un 402 doit remonter. Rendre une trace « soumise » serait pire que
    l'erreur elle-même."""
    from neomundi import PaymentRequiredError

    client = make_client(
        json_responder({"error": "payment_required", "detail": "quota"}, 402)
    )
    with client:
        with pytest.raises(PaymentRequiredError):
            with client.trace() as t:
                t.record(response="ok", token_count=1)
    assert t.record_.outcome == "open"
    assert t.record_.submitted is False


def test_un_timeout_n_est_jamais_rejoue_par_la_trace():
    """Le timeout de `govern()` traverse la trace sans réessai : la
    requête a peut-être été traitée et facturée."""
    from neomundi import TimeoutError as NeoTimeoutError

    recorder = RequestRecorder()

    def _timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("trop long", request=_request)

    client = make_client(_timeout, recorder=recorder)
    with client:
        with pytest.raises(NeoTimeoutError):
            with client.trace() as t:
                t.record(response="ok", token_count=1)
    assert recorder.count == 1


def test_une_trace_jamais_ouverte_refuse_de_supposer_la_latence(full_payload):
    recorder = RequestRecorder()
    client = make_client(json_responder(full_payload), recorder=recorder)
    with client:
        trace = client.trace(token_count=5)
        with pytest.raises(ConfigurationError, match="jamais été ouverte"):
            trace.close()
    assert recorder.count == 0


@pytest.mark.parametrize("valeur", ["", "   ", 7, b"x"])
def test_un_identifiant_de_correlation_invalide_est_refuse(valeur, full_payload):
    client = make_client(json_responder(full_payload))
    with client:
        with pytest.raises(ConfigurationError):
            client.trace(client_trace_id=valeur)


def test_submit_doit_etre_un_booleen(full_payload):
    client = make_client(json_responder(full_payload))
    with client:
        with pytest.raises(ConfigurationError):
            client.trace(submit="oui")


# ---------------------------------------------------------------------
# Confidentialité de la trace
# ---------------------------------------------------------------------

def test_la_trace_ne_porte_ni_prompt_ni_reponse(full_payload):
    """Propriété tenue **par construction** : `to_dict()` ne peut pas
    fuir le contenu, parce que `TraceRecord` ne le porte pas.

    C'est la même règle que le serveur s'applique à son propre journal.
    """
    secret_prompt = "numero-de-carte-4111-1111-1111-1111"
    secret_reponse = "le-diagnostic-confidentiel-du-patient"

    client = make_client(json_responder(full_payload))
    with client:
        with client.trace() as t:
            t.record(prompt=secret_prompt, response=secret_reponse, token_count=9)

    serialise = json.dumps(t.record_.to_dict(), ensure_ascii=False)
    assert secret_prompt not in serialise
    assert secret_reponse not in serialise
    assert repr(t.record_).find(secret_prompt) == -1
    assert repr(t.record_).find(secret_reponse) == -1
    # Les longueurs, elles, sont conservées : ce sont des métadonnées.
    assert t.record_.to_dict()["prompt_length"] == len(secret_prompt)
    assert t.record_.to_dict()["response_length"] == len(secret_reponse)


def test_la_trace_ne_porte_aucune_cle(full_payload):
    client = make_client(json_responder(full_payload))
    with client:
        with client.trace() as t:
            t.record(response="ok", token_count=1)
    assert "ct_test_" not in json.dumps(t.record_.to_dict())
    assert "ct_test_" not in repr(t.record_)
    assert "ct_test_" not in repr(t)


# ---------------------------------------------------------------------
# L'identifiant de trace du serveur
# ---------------------------------------------------------------------

def test_le_trace_id_du_serveur_est_republie_tel_quel(full_payload):
    """`trace-{request_id[:8]}` : dérivé, tronqué, **non unique**.

    Le SDK le republie sans en faire une clé, et `request_id` reste le
    seul identifiant de corrélation.
    """
    client = make_client(json_responder(full_payload))
    with client:
        with client.trace() as t:
            t.record(response="ok", token_count=1)

    attendu = full_payload["audit"]["trace_id"]
    assert t.record_.server_trace_id == attendu
    assert t.record_.request_id != attendu


# ---------------------------------------------------------------------
# Le seul chemin où l'enregistrement est confirmé : SSE
# ---------------------------------------------------------------------

def _stream_result(payload_extra=None, texte="bonjour"):
    payload = {
        "request_id": "11111111-2222-3333-4444-555555555555",
        "total_tokens": 12,
        "latency_ms": 1234.5,
        "model": "mistral-small-latest",
        "audit": {"trace_id": "trace-11111111"},
        "response_text": texte,
    }
    if payload_extra:
        payload.update(payload_extra)
    return StreamResult(payload, texte, True)


def test_une_trace_sse_porte_la_confirmation_d_enregistrement():
    """Absence de `log_persisted` = insertion nominale, et c'est le
    serveur qui l'a décidé (`streaming.py:1650-1653` n'émet la clé que
    sur le chemin non nominal)."""
    record = TraceRecord.from_stream(_stream_result())
    assert record.transport == "sse"
    assert record.registered is True
    assert record.acknowledged is True
    assert record.token_count == 12
    assert record.latency_ms == 1234.5
    assert record.response_length == len("bonjour")
    assert record.server_trace_id == "trace-11111111"


def test_une_trace_sse_rapporte_un_echec_d_enregistrement():
    record = TraceRecord.from_stream(
        _stream_result({"log_persisted": False, "log_write": "failed"})
    )
    assert record.registered is False
    assert record.stream_result is not None
    assert record.stream_result.log_write == "failed"


def test_un_doublon_absorbe_reste_un_enregistrement():
    """`already_exists` : une ligne identique est là, donc
    `log_persisted` reste vrai — et `log_write` dit ce qui s'est passé."""
    resultat = _stream_result({"log_write": "already_exists"})
    assert resultat.log_persisted is True
    assert resultat.log_write == "already_exists"


def test_une_divergence_de_doublon_n_est_pas_un_enregistrement():
    resultat = _stream_result(
        {"log_persisted": False, "log_write": "already_exists_divergent"}
    )
    record = TraceRecord.from_stream(resultat)
    assert record.registered is False


def test_un_log_persisted_mal_type_ne_devient_pas_un_verdict():
    """Une valeur non booléenne rend `None` : ni enregistré, ni non
    enregistré. C'est la seule façon de ne rien inventer."""
    resultat = _stream_result({"log_persisted": "yes"})
    assert resultat.log_persisted is None
    assert TraceRecord.from_stream(resultat).registered is None


def test_les_champs_de_provenance_du_flux_sont_exposes():
    resultat = _stream_result(
        {
            "contract_version": "neomundi.govern.sse/1.0",
            "token_count_source": "chunk_count_fallback",
            "token_count_scope": "content_chunks",
            "token_count_unit": "chunks",
        }
    )
    assert resultat.contract_version == "neomundi.govern.sse/1.0"
    assert resultat.token_count_source == "chunk_count_fallback"
    assert resultat.token_count_scope == "content_chunks"
    # 🔴 `total_tokens` compte alors des CHUNKS, pas des tokens.
    assert resultat.token_count_unit == "chunks"
