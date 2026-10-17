"""Garde-fous structurels : le SDK ne doit pas réintroduire les défauts
que le backend a corrigés.

Ces tests ne vérifient pas un comportement d'appel : ils vérifient des
propriétés du code source et de la cohérence du contrat déclaré. Ils
existent parce qu'une règle que personne ne vérifie est un commentaire.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import neomundi
from conftest import json_responder, load_fixture, make_client
from neomundi.models import _KNOWN_ROOT_KEYS

SRC = Path(neomundi.__file__).parent


def _source_files():
    return sorted(p for p in SRC.rglob("*.py"))


# ---------------------------------------------------------------------
# R1 du plan : aucune valeur par défaut numérique dans les sources
# ---------------------------------------------------------------------

#: Motifs qui réintroduiraient la confusion `null` / `0`.
_FORBIDDEN = [
    (re.compile(r"\bor\s+0\.0\b"), "`or 0.0` remplace un null par un zéro"),
    (re.compile(r"\bor\s+0\b(?!\.)"), "`or 0` remplace un null par un zéro"),
    (re.compile(r"\.get\([^)]*,\s*0\.0\s*\)"), "`get(..., 0.0)` invente une mesure"),
    (re.compile(r"\.get\([^)]*,\s*0\s*\)(?!\.)"), "`get(..., 0)` invente une mesure"),
]


def _code_lines(path: Path):
    """Les lignes de code d'un fichier, docstrings et commentaires exclus.

    Nécessaire parce que les docstrings de ce paquet *parlent* des motifs
    interdits pour expliquer qu'il ne les emploie pas. Une recherche
    textuelle naïve les signalerait à tort — ce qui est arrivé à la
    première version de ces tests.
    """
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source, filename=str(path))

    docstring_spans = []
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            doc = ast.get_docstring(node, clean=False)
            if doc is None:
                continue
            body = node.body[0]
            docstring_spans.append(
                (body.lineno, getattr(body, "end_lineno", body.lineno))
            )
        # Les chaînes « nues » utilisées comme commentaires d'attribut
        # (le motif `#:` de ce paquet) sont déjà des commentaires.
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                docstring_spans.append(
                    (node.lineno, getattr(node, "end_lineno", node.lineno))
                )

    def in_docstring(lineno: int) -> bool:
        return any(start <= lineno <= end for start, end in docstring_spans)

    for lineno, line in enumerate(lines, start=1):
        if in_docstring(lineno):
            continue
        yield lineno, line.split("#", 1)[0]


def test_aucune_valeur_par_defaut_numerique_dans_les_sources():
    """Le défaut central que le backend a mis six chantiers à fermer.

    Un `or 0.0` côté client annulerait tout ce travail : une absence de
    mesure redeviendrait un zéro rassurant.
    """
    offenders = []
    for path in _source_files():
        for lineno, code in _code_lines(path):
            for pattern, why in _FORBIDDEN:
                if pattern.search(code):
                    offenders.append(f"{path.name}:{lineno} — {why} : {code.strip()}")
    assert not offenders, "\n".join(offenders)


def test_le_garde_fou_des_valeurs_par_defaut_a_des_dents():
    """Un garde-fou qu'on ne teste pas est une supposition.

    Vérifie que les motifs interdits attrapent bien ce qu'ils visent.
    """
    samples = [
        "    return value or 0.0",
        "    return value or 0",
        '    x = data.get("g_score", 0.0)',
        '    x = data.get("g_score", 0)',
    ]
    for sample in samples:
        assert any(
            pattern.search(sample) for pattern, _ in _FORBIDDEN
        ), f"non détecté : {sample}"
    # Et qu'ils ne se déclenchent pas sur du code légitime.
    for safe in [
        "    return value if found else None",
        '    x = data.get("g_score")',
        "    delay = self.backoff_initial * 2.0",
        "    if token_count < 0:",
    ]:
        assert not any(
            pattern.search(safe) for pattern, _ in _FORBIDDEN
        ), f"faux positif : {safe}"


def test_aucun_import_du_backend_neomundi():
    """Le SDK doit être une bibliothèque cliente indépendante.

    Aucun import de `app.*` (le paquet du serveur), aucune dépendance au
    code interne du backend.
    """
    forbidden = re.compile(r"^\s*(from|import)\s+(app|govern_v3|govern)\b", re.M)
    offenders = [
        path.name
        for path in _source_files()
        if forbidden.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"Import du backend détecté dans : {offenders}"


def test_les_seules_dependances_de_production_sont_declarees():
    """httpx est la seule dépendance de production.

    Un import de pydantic, requests ou respx dans `src/` serait une
    dépendance non déclarée dans `pyproject.toml`.
    """
    banned = re.compile(r"^\s*(from|import)\s+(pydantic|requests|respx|numpy)\b", re.M)
    offenders = [
        path.name
        for path in _source_files()
        if banned.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"Dépendance non déclarée dans : {offenders}"


def test_aucun_seuil_ni_verdict_derive_dans_le_code():
    """Le SDK n'interprète pas : aucun seuil, aucun verdict dérivé.

    Analysé par **AST** et non par recherche textuelle : les docstrings de
    ce paquet parlent de seuils pour expliquer qu'il n'y en a pas. Ce qui
    compte est le code — un nom de fonction, de classe ou de constante qui
    trahirait une interprétation.

    Les constantes de transport (timeouts, backoff) sont légitimes :
    elles ne portent aucun jugement sur une mesure.
    """
    banned = re.compile(
        r"(THRESHOLD|SEUIL|is_safe|is_good|is_healthy|is_reliable|"
        r"is_acceptable|quality_level|severity_of|verdict_of)",
        re.I,
    )
    offenders = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                names.append(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        names.append(target.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(
                node.target, ast.Name
            ):
                names.append(node.target.id)
            for name in names:
                if banned.search(name):
                    offenders.append(f"{path.name}:{node.lineno} : {name}")
    assert not offenders, "\n".join(offenders)


# ---------------------------------------------------------------------
# Cohérence entre le contrat déclaré et les fixtures
# ---------------------------------------------------------------------

_FIXTURES = [
    "full_measurement.json",
    "partial_measurement.json",
    "gated_tier01.json",
    "no_check_attempted.json",
]


@pytest.mark.parametrize("name", _FIXTURES)
def test_les_cles_des_fixtures_nominales_sont_toutes_connues(name):
    """Une fixture relevée du code ne doit contenir aucune clé que le SDK
    ignore : si le relevé du contrat a oublié un champ, ce test le dit.
    """
    payload = load_fixture(name)
    unknown = sorted(set(payload) - _KNOWN_ROOT_KEYS)
    assert not unknown, f"{name} : clés non modélisées {unknown}"


@pytest.mark.parametrize("name", _FIXTURES)
def test_les_fixtures_nominales_portent_les_quatre_blocs_requis(name):
    payload = load_fixture(name)
    for block in ("governance", "metrics", "baseline", "audit"):
        assert isinstance(payload.get(block), dict), f"{name} : {block} manquant"


@pytest.mark.parametrize("name", _FIXTURES)
def test_les_fixtures_nominales_se_parsent_sans_avertissement(name):
    """Si une fixture relevée du code produit un avertissement, soit la
    fixture est fausse, soit le relevé du contrat l'est."""
    payload = load_fixture(name)
    with make_client(json_responder(payload)) as client:
        result = client.govern(token_count=1, latency_ms=1.0)
    assert result.parse_warnings == [], [
        (w.path, w.expected, w.received_type) for w in result.parse_warnings
    ]
    assert result.unknown_fields == []


@pytest.mark.parametrize("name", _FIXTURES)
def test_un_aller_retour_ne_perd_rien(name):
    payload = load_fixture(name)
    with make_client(json_responder(payload)) as client:
        result = client.govern(token_count=1, latency_ms=1.0)
    assert result.to_dict() == payload


@pytest.mark.parametrize("name", _FIXTURES)
def test_la_version_de_mesure_des_fixtures_correspond_au_contrat_declare(name):
    """Si le backend monte sa version de mesure, les fixtures et
    `API_CONTRACT` doivent bouger ensemble — sinon le SDK se réfère à un
    contrat qu'il ne modélise plus."""
    payload = load_fixture(name)
    assert (
        payload["audit"]["measurement_version"]
        == neomundi.API_CONTRACT["measurement_version"]
    ), name


def test_les_cinq_signaux_declares_sont_ceux_du_backend():
    """Relevé de `app/rgc/models.py:77-83`."""
    assert set(neomundi.COVERAGE_SIGNALS) == {
        "stability_score",
        "coherence_score",
        "factual_hallucination_score",
        "semantic_instability_score",
        "semantic_risk",
    }


def test_la_surface_publique_est_explicite():
    """Tout ce que `__all__` annonce doit exister, et réciproquement pour
    les noms publics du paquet."""
    for name in neomundi.__all__:
        assert hasattr(neomundi, name), f"{name} annoncé mais absent"
    # `annotations` vient de `from __future__ import annotations` ; les
    # trois sous-modules sont des détails d'implémentation accessibles
    # mais non annoncés dans la surface publique.
    not_public = {"client", "errors", "models", "annotations"}
    public = {
        n for n in dir(neomundi) if not n.startswith("_") and n not in not_public
    }
    missing = public - set(neomundi.__all__)
    assert not missing, f"Noms publics hors de __all__ : {sorted(missing)}"


def test_le_marqueur_de_typage_est_present():
    """PEP 561 : sans `py.typed`, les annotations ne sont pas vues par les
    outils de typage des intégrateurs."""
    assert (SRC / "py.typed").exists()
