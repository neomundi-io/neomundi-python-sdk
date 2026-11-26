"""Conservative 3.5.0 wire-extension regression, without claiming verified compatibility.

This is an intentionally SYNTHETIC mutation of the existing redacted 3.3.1
fixture, NOT a captured 3.5.0 response and NOT a schema authority.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from neomundi import API_CONTRACT, GovernResult

FIXTURE = Path(__file__).parent / "fixtures" / "production_331" / "rest_complete_allow.json"
NEW_FIELDS = {
    "contract_version": "synthetic-contract-version",
    "token_count_source": "synthetic-source",
    "token_count_scope": "synthetic-scope",
    "token_count_unit": "synthetic-unit",
}


def _synthetic_350():
    source = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source = {k: v for k, v in source.items() if not k.startswith("_fixture_")}
    obj = copy.deepcopy(source)
    obj["audit"]["measurement_version"] = "3.5.0"
    obj.update(NEW_FIELDS)
    return obj


def test_350_synthetic_new_fields_are_preserved_exactly_and_not_reinterpreted():
    payload = _synthetic_350()
    result = GovernResult.from_dict(payload)
    assert result.to_dict() == payload
    assert result.audit.measurement_version == "3.5.0"
    assert not result.parse_warnings
    assert not (set(NEW_FIELDS) & set(result.unknown_fields))
    for name, value in NEW_FIELDS.items():
        assert result.raw[name] == value
        assert getattr(result, name) == value


def test_350_must_not_be_declared_verified_from_synthetic_replay_alone():
    """The fixtures in this file are SYNTHETIC and justify no declaration.

    Until 2026-11-26 this asserted that `3.5.0` was absent from the verified
    set, because the only 3.5.0 material in the repository was the synthetic
    replay above. It is now present -- on a live authenticated REST call --
    so the assertion states the rule it always meant: a version may appear
    in that list only if this repository carries the live evidence for it.

    The tests above are unchanged and remain what they always were: parser
    coverage, not qualification. This one makes sure they can never be
    mistaken for it.
    """
    if "3.5.0" not in API_CONTRACT["verified_measurement_versions"]:
        return
    evidence = (
        Path(__file__).resolve().parents[1] / "docs" / "COMPATIBILITY_350.md"
    ).read_text(encoding="utf-8")
    assert "Live authenticated REST qualification" in evidence, (
        "3.5.0 is declared verified but docs/COMPATIBILITY_350.md records no "
        "live REST qualification. Synthetic replay cannot justify it."
    )
    assert "parse_warnings: 0" in evidence
    assert "read back             HTTP 200, persisted" in evidence
    proof = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "evidence"
        / "rest_qualification_350_20261126.json"
    )
    assert proof.is_file(), f"the cited evidence file is missing: {proof.name}"


def test_new_fields_keep_null_and_zero_distinct():
    payload = _synthetic_350()
    payload["token_count_source"] = None
    payload["token_count_scope"] = 0
    result = GovernResult.from_dict(payload)
    assert result.to_dict() == payload
    assert result.raw["token_count_source"] is None
    assert result.raw["token_count_scope"] == 0
    assert result.token_count_source is None
    assert result.token_count_scope is None
    assert [w.path for w in result.parse_warnings] == ["root.token_count_scope"]


def test_stream_replay_metadata_preserves_empty_dict_null_and_invalid_type():
    payload = _synthetic_350()
    payload["stream_contract_metadata"] = {}
    result = GovernResult.from_dict(payload)
    assert result.stream_contract_metadata == {}
    assert result.to_dict() == payload

    payload["stream_contract_metadata"] = None
    result = GovernResult.from_dict(payload)
    assert result.stream_contract_metadata is None
    assert result.to_dict() == payload

    payload["stream_contract_metadata"] = "invalid"
    result = GovernResult.from_dict(payload)
    assert result.stream_contract_metadata is None
    assert any(w.path == "root.stream_contract_metadata" for w in result.parse_warnings)
    assert result.to_dict() == payload


def test_legacy_331_fixture_keeps_absent_contract_fields_missing():
    original = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source = {k: v for k, v in original.items() if not k.startswith("_fixture_")}
    result = GovernResult.from_dict(source)
    assert result.contract_version is None
    assert result.token_count_source is None
    assert result.stream_contract_metadata is None
    assert result.to_dict() == source
