"""Le banc d'audit de distribution doit juger la METADATA, pas la plateforme.

Ces tests existent parce que la CI ne construit le paquet que sur Ubuntu :
une roue construite sur Windows porte des CRLF dans sa `METADATA`, et
`scripts/audit_distribution.py` la refusait alors sur un commit par
ailleurs identique. Le défaut n'était donc visible sur aucun runner.
"""
from __future__ import annotations

import pathlib
import sys
import zipfile

import pytest

_SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import audit_distribution as ad  # noqa: E402

_METADATA_LINES = (
    "Metadata-Version: 2.4",
    "Name: neomundi",
    "Version: 2.0.0",
    "Summary: Client Python NeoMundi",
    "License-Expression: Apache-2.0",
)


def _wheel(path: pathlib.Path, newline: str) -> pathlib.Path:
    """Une roue minimale, valide, dont la METADATA utilise `newline`."""
    metadata = newline.join(_METADATA_LINES) + newline
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("neomundi/__init__.py", "__version__ = '2.0.0'\n")
        z.writestr("neomundi/py.typed", "")
        z.writestr("neomundi-2.0.0.dist-info/METADATA", metadata)
        z.writestr("neomundi-2.0.0.dist-info/licenses/LICENSE", "Apache License 2.0\n")
    return path


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_le_verdict_ne_depend_pas_des_fins_de_ligne(tmp_path, newline):
    """LF et CRLF décrivent la MÊME métadonnée : le verdict doit être le même.

    C'est l'invariant que le défaut violait. Avec `\\r\\n`, l'ancienne
    version levait `AssertionError: Distribution name mismatch`.
    """
    ad.check_archive(_wheel(tmp_path / "neomundi-2.0.0-py3-none-any.whl", newline))


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_un_nom_de_distribution_faux_est_refuse_dans_les_deux_cas(tmp_path, newline):
    """La normalisation ne doit pas affaiblir le contrôle qu'elle répare."""
    wheel = tmp_path / "neomundi-2.0.0-py3-none-any.whl"
    metadata = newline.join(
        line.replace("Name: neomundi", "Name: not-neomundi") for line in _METADATA_LINES
    ) + newline
    with zipfile.ZipFile(wheel, "w") as z:
        z.writestr("neomundi/__init__.py", "")
        z.writestr("neomundi-2.0.0.dist-info/METADATA", metadata)
        z.writestr("neomundi-2.0.0.dist-info/licenses/LICENSE", "Apache License 2.0\n")
    with pytest.raises(AssertionError, match="Distribution name mismatch"):
        ad.check_archive(wheel)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_une_licence_fausse_est_refusee_dans_les_deux_cas(tmp_path, newline):
    """Même exigence pour la licence : Apache-2.0 reste obligatoire."""
    wheel = tmp_path / "neomundi-2.0.0-py3-none-any.whl"
    metadata = newline.join(
        line.replace("License-Expression: Apache-2.0", "License-Expression: MIT")
        for line in _METADATA_LINES
    ) + newline
    with zipfile.ZipFile(wheel, "w") as z:
        z.writestr("neomundi/__init__.py", "")
        z.writestr("neomundi-2.0.0.dist-info/METADATA", metadata)
        z.writestr("neomundi-2.0.0.dist-info/licenses/LICENSE", "Apache License 2.0\n")
    with pytest.raises(AssertionError, match="Licence mismatch"):
        ad.check_archive(wheel)


def test_read_metadata_normalise_sans_rien_perdre(tmp_path):
    """La lecture normalise les CRLF et ne touche à rien d'autre."""
    wheel = _wheel(tmp_path / "w.whl", "\r\n")
    with zipfile.ZipFile(wheel) as z:
        text = ad.read_metadata(z, "neomundi-2.0.0.dist-info/METADATA")
    assert "\r" not in text
    assert text.splitlines() == list(_METADATA_LINES)
