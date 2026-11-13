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
    assert "3.5.0" not in API_CONTRACT["verified_measurement_versions"]


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
