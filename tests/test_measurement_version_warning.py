"""Le SDK applique enfin la comparaison qu'il déclarait.

`API_CONTRACT["verified_measurement_versions"]` existait depuis la 2.0 et
**aucun chemin de code ne le lisait** : la constante apparaissait deux fois
dans le paquet, sa définition et son nom dans `__all__`. La comparaison
vivait donc chez les consommateurs, et des cinq intégrations publiées seule
`langchain-neomundi` l'implémentait.

Ces tests épinglent le contrat du nouveau garde-fou. Ils tiennent à une
exigence : **il avertit et ne bloque jamais**. Un écart de version est une
information pour l'appelant, pas une erreur du SDK — un résultat reste un
résultat, et rien n'est levé, modifié ni retenu.
"""

from __future__ import annotations

import warnings

import pytest

import neomundi
from neomundi import models


@pytest.fixture(autouse=True)
def _forget_warned_versions():
    """Chaque test repart d'un processus qui n'a encore rien signalé."""
    saved = set(models._warned_versions)
    models._warned_versions.clear()
    yield
    models._warned_versions.clear()
    models._warned_versions.update(saved)


def _warnings_for(version, **kwargs):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        emitted = models.warn_on_measurement_version(version, **kwargs)
    return emitted, caught


@pytest.mark.parametrize("version", models.VERIFIED_MEASUREMENT_VERSIONS)
def test_une_version_verifiee_ne_dit_rien(version):
    emitted, caught = _warnings_for(version)
    assert emitted is False
    assert caught == []


def test_une_version_non_verifiee_avertit_une_fois():
    emitted, caught = _warnings_for("3.9.0")
    assert emitted is True
    assert len(caught) == 1
    assert caught[0].category is RuntimeWarning
    message = str(caught[0].message)
    # Le message doit nommer la version servie ET les versions vérifiées :
    # un avertissement qui ne dit pas de quoi l'écart s'écarte n'est pas
    # actionnable.
    assert "3.9.0" in message
    for verified in models.VERIFIED_MEASUREMENT_VERSIONS:
        assert verified in message
    assert "not comparable" in message


def test_la_meme_version_n_avertit_pas_deux_fois():
    """Une boucle de mille mesures ne doit pas rendre mille avertissements.

    L'exemple est `3.9.0` et non `3.5.0` : cette derniere a ete qualifiee le
    2026-11-26 et figure desormais dans la liste verifiee, donc elle ne
    declenche plus rien. Un test doit porter sur une version reellement non
    verifiee, sinon il ne teste plus la regle.
    """
    first, caught_first = _warnings_for("3.9.0")
    second, caught_second = _warnings_for("3.9.0")
    assert first is True and len(caught_first) == 1
    assert second is False and caught_second == []


def test_une_seconde_version_differente_avertit_quand_meme():
    """Se taire après le premier écart masquerait le suivant."""
    _warnings_for("3.9.0")
    emitted, caught = _warnings_for("4.0.0")
    assert emitted is True
    assert len(caught) == 1
    assert "4.0.0" in str(caught[0].message)


@pytest.mark.parametrize("absent", [None, ""])
def test_une_version_absente_n_est_pas_un_ecart(absent):
    """Aucune version servie n'est une information, pas une incompatibilité.

    Avertir ici produirait un avertissement sur toute réponse dont le bloc
    d'audit manque, ce qui est déjà signalé par ailleurs.
    """
    emitted, caught = _warnings_for(absent)
    assert emitted is False
    assert caught == []


def test_la_declaration_est_unique():
    """`API_CONTRACT` réexporte la constante, il n'en garde pas une copie.

    Deux copies dériveraient, et c'est exactement le défaut que ce
    changement corrige.
    """
    assert (
        neomundi.API_CONTRACT["verified_measurement_versions"]
        is models.VERIFIED_MEASUREMENT_VERSIONS
    )


def test_la_surface_publique_du_paquet_est_inchangee():
    """La correction n'élargit pas l'API publiée de `neomundi`.

    `test_contract_drift` épingle cette surface à juste titre ; la constante
    est importée sous alias privé parce qu'`API_CONTRACT` l'expose déjà.
    """
    assert not hasattr(neomundi, "VERIFIED_MEASUREMENT_VERSIONS")
    assert not hasattr(neomundi, "warn_on_measurement_version")


def test_il_avertit_et_ne_bloque_pas():
    """L'exigence centrale, énoncée comme un test.

    Rien n'est levé, et l'appel rend la main normalement même sur une
    version inconnue.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        with pytest.raises(RuntimeWarning):
            # Sous `-W error` c'est l'appelant qui a choisi de promouvoir
            # l'avertissement en erreur : le SDK, lui, n'a fait qu'avertir.
            models.warn_on_measurement_version("9.9.9")
    models._warned_versions.clear()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert models.warn_on_measurement_version("9.9.9") is True
