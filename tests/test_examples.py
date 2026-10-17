"""Les exemples de la documentation sont exécutés, pas seulement affichés.

Un exemple qui ne tourne pas est un piège : l'exemple officiel du backend
(`GUIDE_CLIENT.md`) lève un `TypeError` dès qu'un agrégat est retenu, et
personne ne s'en est aperçu parce qu'il n'était pas exécuté.

Ces tests garantissent que les trois exemples du SDK tournent, sans
réseau, et sortent en code 0.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).parent.parent / "examples"

#: Les exemples exécutables. Chacun branche le client sur un transport
#: httpx simulé : aucun n'ouvre de socket.
RUNNABLE = [
    "01_premiere_mesure.py",
    "02_mesure_partielle.py",
    "03_gestion_erreurs.py",
]


@pytest.mark.parametrize("name", RUNNABLE)
def test_l_exemple_s_execute_et_sort_en_zero(name):
    result = subprocess.run(
        [sys.executable, str(EXAMPLES / name)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(EXAMPLES.parent),
    )
    assert result.returncode == 0, (
        f"{name} a échoué (code {result.returncode})\n"
        f"--- stdout ---\n{result.stdout[-3000:]}\n"
        f"--- stderr ---\n{result.stderr[-3000:]}"
    )
    assert result.stdout.strip(), f"{name} n'a rien affiché"


@pytest.mark.parametrize("name", RUNNABLE)
def test_l_exemple_annonce_qu_il_utilise_un_serveur_simule(name):
    """Exigence Phase D : distinguer les exemples sur serveur simulé de
    ceux qui demandent une vraie clé."""
    text = (EXAMPLES / name).read_text(encoding="utf-8")
    assert "SERVEUR SIMULÉ" in text, name


@pytest.mark.parametrize("name", RUNNABLE)
def test_l_exemple_n_utilise_aucune_cle_plausible(name):
    text = (EXAMPLES / name).read_text(encoding="utf-8")
    assert "ct_live_" not in text, name
    # La seule clé admise est la clé de test manifestement factice.
    for token in text.split('"'):
        if token.startswith("ct_"):
            assert token.startswith("ct_test_0000"), f"{name}: {token[:20]}"


def test_l_exemple_a_cle_reelle_n_est_pas_executable():
    """Son extension `.disabled` empêche tout lancement accidentel vers un
    vrai serveur."""
    candidates = list(EXAMPLES.glob("90_cle_reelle*"))
    assert candidates, "l'exemple à clé réelle est absent"
    for path in candidates:
        assert path.suffix == ".disabled", path.name
        assert not path.name.endswith(".py"), path.name


def test_aucun_exemple_executable_ne_contacte_un_hote_reel():
    """Tous les exemples exécutables pointent sur `example.invalid`, un
    domaine réservé par la RFC 2606 dont la résolution DNS échoue
    toujours — seconde ligne de défense si un transport simulé était
    oublié."""
    for name in RUNNABLE:
        text = (EXAMPLES / name).read_text(encoding="utf-8")
        assert "https://example.invalid" in text, name
        assert "api.neomundi.io" not in text, name
        assert "MockTransport" in text, name
