"""`token_count` et `latency_ms` peuvent être omis — sans substitution.

BL-V1-001 les a rendus facultatifs côté serveur le 2026-11-11. La signature
de ce SDK les exigeait encore, si bien que les trois cas d'omission de la
qualification 3.5.0 levaient `TypeError` **avant toute requête** : le SDK ne
pouvait pas produire le cas même que le serveur a introduit
`absent_runtime_metrics` pour décrire.

🔴 L'enjeu est énoncé par le contrat serveur lui-même : fournir zéro est **la
valeur la plus favorable** que leur terme puisse prendre — `latency_ms = 0`
produit un `latency_score` parfait. Un SDK qui substituerait zéro à une
métrique non mesurée publierait donc un chiffre flatteur que personne n'a
mesuré. Ces tests fixent l'inverse : un champ absent est **omis**, et le
serveur y répond en le **nommant** dans `measurement.absent_runtime_metrics`.

Et ils fixent l'absence de régression : un appelant qui fournit les deux
valeurs obtient exactement le même corps et exactement les mêmes refus
qu'avant.
"""

from __future__ import annotations

import math

import pytest

from neomundi.client import _build_request_body
from neomundi.errors import ConfigurationError

BASE = {"llm_prompt": "Name the capital of France.", "llm_response": "Paris."}


def _raw(**kwargs):
    return _build_request_body(**BASE, **kwargs)["raw_metrics"]


# --------------------------------------------------------------- omission --
def test_les_deux_fournis_restent_inchanges():
    """Le cas de l'appelant existant. Aucune dérive tolérée."""
    assert _raw(token_count=12, latency_ms=240.0) == {
        "token_count": 12,
        "latency_ms": 240.0,
    }


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"latency_ms": 240.0}, {"latency_ms": 240.0}),
        ({"token_count": 12}, {"token_count": 12}),
        ({}, {}),
    ],
    ids=["token_count omis", "latency_ms omise", "les deux omises"],
)
def test_une_metrique_omise_est_absente_du_corps(kwargs, expected):
    assert _raw(**kwargs) == expected


@pytest.mark.parametrize("field", ["token_count", "latency_ms"])
def test_une_metrique_omise_n_est_JAMAIS_remplacee_par_zero(field):
    """Le test central.

    Zéro n'est pas une valeur neutre : le contrat serveur dit qu'il est le
    plus favorable. Le confondre avec l'absence inventerait une mesure.
    """
    raw = _raw()
    assert field not in raw, f"{field} a été substitué : {raw[field]!r}"
    assert raw.get(field) is None


def test_zero_explicitement_fourni_est_transmis_tel_quel():
    """Omettre et envoyer zéro sont deux déclarations différentes.

    Un appelant qui a réellement mesuré zéro jeton a le droit de le dire ;
    ce SDK ne doit ni le refuser ni le convertir en absence.
    """
    raw = _raw(token_count=0, latency_ms=0.0)
    assert raw == {"token_count": 0, "latency_ms": 0.0}


def test_raw_metrics_reste_present_meme_vide():
    """`GovernRequest.raw_metrics` est requis par le contrat ; ses champs non.

    Omettre l'objet entier serait une requête invalide, pas une omission.
    """
    body = _build_request_body(**BASE)
    assert "raw_metrics" in body
    assert body["raw_metrics"] == {}


# ---------------------------------------------------- non-régression -------
@pytest.mark.parametrize(
    "kwargs",
    [
        {"token_count": -1},
        {"token_count": True},
        {"token_count": 1.5},
        {"token_count": "12"},
        {"latency_ms": -1.0},
        {"latency_ms": True},
        {"latency_ms": math.inf},
        {"latency_ms": math.nan},
        {"latency_ms": "240"},
    ],
    ids=[
        "token_count negatif",
        "token_count booleen",
        "token_count flottant",
        "token_count chaine",
        "latency_ms negative",
        "latency_ms booleenne",
        "latency_ms infinie",
        "latency_ms NaN",
        "latency_ms chaine",
    ],
)
def test_une_valeur_fournie_est_validee_comme_avant(kwargs):
    """Rendre un champ facultatif ne doit rien relâcher sur une valeur donnée."""
    with pytest.raises(ConfigurationError):
        _build_request_body(**BASE, **kwargs)


def test_la_signature_publique_accepte_l_omission():
    """`govern()` ne doit plus lever `TypeError` quand on omet les deux.

    C'est la régression inverse à surveiller : l'appel doit arriver jusqu'à
    la validation, pas mourir sur la signature.
    """
    import inspect

    from neomundi import NeoMundiClient

    signature = inspect.signature(NeoMundiClient.govern)
    for name in ("token_count", "latency_ms"):
        parameter = signature.parameters[name]
        assert parameter.default is None, f"{name} est encore obligatoire"
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
