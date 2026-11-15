"""Le SDK est-il aligné sur le contrat de fil RÉELLEMENT DÉPLOYÉ ?

Les deux fichiers de `tests/fixtures/contracts/` ne sont pas des copies
du dépôt backend : ils ont été **téléchargés depuis la production** le
2026-11-15 sur `GET /v1/contracts/<nom>`, une route publique, non
facturée et sans configuration (`app/api/v1/contracts.py`). Ils se sont
révélés identiques **octet pour octet** aux fichiers du dépôt backend —
c'est ce qui autorise à parler du contrat déployé plutôt que d'une copie
locale.

Pourquoi ces tests existent : `/openapi.json` et `/docs` rendent **404**
en production. Ces deux schémas sont donc la seule description du fil que
le service publie, et un champ racine qu'ils déclarent `required` et que
le SDK ignore est une dérive silencieuse — elle ne casse rien, elle
*cache* quelque chose. La qualification du 2026-11-13 avait relevé
quatre champs requis inconnus du SDK ; ces tests interdisent qu'ils y
retournent sans que personne ne le voie.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import neomundi
from neomundi.models import _KNOWN_ROOT_KEYS

CONTRACTS = Path(__file__).parent / "fixtures" / "contracts"

REST = json.loads((CONTRACTS / "govern-rest-1.0.json").read_text(encoding="utf-8"))
SSE = json.loads((CONTRACTS / "govern-sse-1.0.json").read_text(encoding="utf-8"))


def test_les_empreintes_des_contrats_sont_celles_declarees():
    """`API_CONTRACT["wire_contracts"]` doit nommer ces fichiers-ci.

    Une empreinte recopiée de mémoire est une empreinte fausse : elle est
    mesurée ici, à chaque exécution.
    """
    import hashlib

    for name, declared in neomundi.API_CONTRACT["wire_contracts"].items():
        measured = hashlib.sha256((CONTRACTS / name).read_bytes()).hexdigest()
        assert measured == declared, (
            f"{name} : empreinte mesurée {measured}, déclarée {declared}. "
            "Soit la fixture a changé, soit la déclaration est périmée — "
            "mesurer avant de corriger."
        )


def test_tout_champ_racine_requis_par_le_contrat_rest_est_connu_du_sdk():
    """Un champ requis inconnu tomberait dans `unknown_fields`.

    Ce n'est pas fatal — c'est précisément la garantie de compatibilité
    ascendante du SDK — mais pour un champ que le contrat déclare
    **requis**, c'est un retard du SDK, pas une extension du serveur.
    """
    inconnus = sorted(set(REST["required"]) - _KNOWN_ROOT_KEYS)
    assert not inconnus, (
        "Champs requis par le contrat déployé et inconnus du SDK : "
        f"{inconnus}. Les ajouter à `_KNOWN_ROOT_KEYS` et à `GovernResult`, "
        "ou documenter pourquoi ils restent dans `unknown_fields`."
    )


def test_une_reponse_portant_les_cinq_champs_declares_ne_laisse_rien_d_inconnu(
    full_payload,
):
    """La charge complète + les cinq racines du contrat : zéro inconnu."""
    payload = dict(full_payload)
    payload.update(
        {
            "contract_version": "neomundi.govern.rest/1.0",
            "token_count_source": "caller_declared",
            "token_count_scope": "caller_declared",
            "token_count_unit": "tokens",
            "stream_contract_metadata": None,
        }
    )
    result = neomundi.GovernResult.from_dict(payload)

    assert result.unknown_fields == []
    assert result.parse_warnings == []
    assert result.contract_version == "neomundi.govern.rest/1.0"
    assert result.token_count_unit == "tokens"
    assert result.stream_contract_metadata is None


def test_le_sdk_republie_que_le_decompte_de_tokens_vient_de_l_appelant():
    """`token_count_source` est un `const` du contrat REST déployé.

    C'est la raison pour laquelle `token_count` ne peut pas devenir
    optionnel : le serveur ne compte rien sur cette route, il republie ce
    que l'appelant a déclaré. Un champ de provenance qui dit
    `caller_declared` et une valeur rendue optionnelle seraient
    contradictoires.
    """
    assert REST["properties"]["token_count_source"]["const"] == "caller_declared"
    assert REST["properties"]["token_count_unit"]["const"] == "tokens"
    for champ in ("contract_version", "token_count_source", "token_count_unit"):
        assert champ in REST["required"]


def test_le_contrat_sse_mesure_ou_se_rabat_et_le_dit():
    """Sur SSE le serveur compte — mais pas toujours en tokens.

    `chunk_count_fallback` + `chunks` : un consommateur qui lirait
    `total_tokens` sans lire ces champs comparerait des chunks à des
    tokens. Les propriétés de `StreamResult` existent pour ça.
    """
    assert SSE["properties"]["token_count_source"]["enum"] == [
        "provider_usage",
        "chunk_count_fallback",
    ]
    assert SSE["properties"]["token_count_unit"]["enum"] == ["tokens", "chunks"]


def test_seule_la_route_sse_publie_une_confirmation_d_enregistrement():
    """Le fait qui gouverne toute l'étape TRACE.

    `log_persisted` existe dans le contrat SSE et **pas** dans le contrat
    REST. Un SDK qui annoncerait « interaction enregistrée » après un 200
    de `POST /v1/govern` inventerait une confirmation que le serveur n'a
    jamais donnée.
    """
    assert "log_persisted" in SSE["properties"]
    assert "log_write" in SSE["properties"]
    assert "log_persisted" not in REST["properties"]
    assert "log_write" not in REST["properties"]


@pytest.mark.parametrize("nom", ["govern-rest-1.0.json", "govern-sse-1.0.json"])
def test_les_fixtures_de_contrat_sont_en_lf(nom):
    """`.gitattributes` impose `*.json text eol=lf`.

    Un CRLF changerait l'empreinte, donc la preuve. Le contrôle est ici
    parce qu'il ne se voit nulle part ailleurs.
    """
    octets = (CONTRACTS / nom).read_bytes()
    assert b"\r\n" not in octets
    assert octets.endswith(b"\n")
