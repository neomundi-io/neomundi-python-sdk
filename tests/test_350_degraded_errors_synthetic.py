"""Synthetic 3.5.0 degraded/error-path regression, entirely offline.

These cases combine historical sanitized 3.3.x fixture shapes with the
published REST 1.0 provenance declarations. They are NOT production
captures of degraded measurements under 3.5.0. All requests go through
httpx.MockTransport; no genuine API key, credits, network or provider call.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import httpx
import pytest

from conftest import RequestRecorder, json_responder, make_client, raising_responder
from neomundi import (
    AggregateWithheldError,
    AuthenticationError,
    InvalidResponseError,
    MeasurementState,
    ServerError,
    TimeoutError,
)

FIXTURE_ROOT = Path(__file__).parent / "fixtures"
REST_CONTRACT = {
    "contract_version": "neomundi.govern.rest/1.0",
    "token_count_source": "caller_declared",
    "token_count_scope": "caller_declared",
    "token_count_unit": "tokens",
}


def synthetic_350(name: str):
    historical = json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))
    historical = {k: v for k, v in historical.items() if not k.startswith("_fixture_")}
    payload = copy.deepcopy(historical)
    payload["audit"]["measurement_version"] = "3.5.0"
    payload.update(REST_CONTRACT)
    return payload


def call(payload, *, recorder=None):
    with make_client(json_responder(payload), recorder=recorder) as client:
        return client.govern(token_count=1, latency_ms=1.0)


def test_synthetic_partial_350_cannot_be_promoted_to_measured():
    payload = synthetic_350("partial_measurement.json")
    recorder = RequestRecorder()
    result = call(payload, recorder=recorder)
    assert recorder.count == 1
    assert result.to_dict() == payload
    assert result.audit.measurement_version == "3.5.0"
    assert result.contract_version == REST_CONTRACT["contract_version"]
    assert not result.unknown_fields
    assert not result.parse_warnings
    assert result.measurement_incomplete is True
    assert result.aggregates_publishable is False
    assert result.missing_required_signals == ["hallucination_score"]
    assert result.g_score is None and result.g_final is None
    assert result.is_measured("factual_hallucination_score") is False
    assert result.measurement_state("factual_hallucination_score") is MeasurementState.NOT_MEASURED
    assert result.unmeasured_reason("factual_hallucination_score") == "hallucination_judge_unavailable"
    assert result.governance.decision_basis == "incomplete_measurement"
    assert result.format_score("g_score", when_none="not measured") == "not measured"
    with pytest.raises(AggregateWithheldError) as exc:
        result.require("g_score")
    assert "hallucination_score" in str(exc.value)


@pytest.mark.parametrize(
    "fixture",
    ["full_measurement.json", "partial_measurement.json", "no_check_attempted.json"],
)
def test_synthetic_350_invariants_preserve_distinct_states(fixture):
    payload = synthetic_350(fixture)
    result = call(payload)
    assert result.to_dict() == payload
    assert result.audit.measurement_version == "3.5.0"
    assert result.token_count_source == "caller_declared"
    assert not result.parse_warnings
    assert result.measurement.status == payload["measurement"]["status"]
    if fixture == "no_check_attempted.json":
        assert result.governance.decision_basis == "no_check_attempted"
        assert result.measurement_state("coherence_score") is MeasurementState.NOT_ATTEMPTED_OR_GATED
    if fixture == "full_measurement.json":
        assert result.aggregates_publishable is True
        assert result.missing_required_signals == []


@pytest.mark.parametrize("required", ["governance", "metrics", "baseline", "audit"])
def test_synthetic_350_missing_required_block_must_raise(required):
    payload = synthetic_350("partial_measurement.json")
    del payload[required]
    recorder = RequestRecorder()
    with make_client(json_responder(payload), recorder=recorder) as client:
        with pytest.raises(InvalidResponseError):
            client.govern(token_count=1, latency_ms=1.0)
    assert recorder.count == 1


@pytest.mark.parametrize("status,exception", [(401, AuthenticationError), (503, ServerError)])
def test_350_http_error_is_not_misclassified_as_missing_measurement(status, exception):
    recorder = RequestRecorder()
    with make_client(
        json_responder({"error": "synthetic_failure", "detail": "synthetic only"}, status_code=status),
        recorder=recorder,
    ) as client:
        with pytest.raises(exception) as caught:
            client.govern(token_count=1, latency_ms=1.0)
    assert caught.value.status_code == status
    assert recorder.count == 1


def test_350_timeout_is_not_automatically_retried():
    recorder = RequestRecorder()
    with make_client(raising_responder(httpx.ReadTimeout("synthetic timeout")), recorder=recorder) as client:
        with pytest.raises(TimeoutError):
            client.govern(token_count=1, latency_ms=1.0)
    assert recorder.count == 1


def test_declared_null_is_not_a_zero_or_a_healthy_measurement():
    payload = synthetic_350("partial_measurement.json")
    assert payload["g_score"] is None
    result = call(payload)
    assert result.field_present("g_score")
    assert result.get("g_score") is None
    assert result.g_score is None
    assert result.require("quality.semantic_risk") == payload["quality"]["semantic_risk"]


def test_350_provenance_is_never_inferred_when_absent():
    payload = synthetic_350("partial_measurement.json")
    del payload["token_count_source"]
    result = call(payload)
    assert result.token_count_source is None
    assert result.field_present("token_count_source") is False
    assert result.to_dict() == payload
    # The SDK is a lossless parser, not a substitute for schema validation:
    # required-field absence must be detected by a schema validator separately.
