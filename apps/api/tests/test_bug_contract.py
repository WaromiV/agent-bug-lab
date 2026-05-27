"""The BugContract is the single source of truth for a bug on the wire.
These tests pin down what it accepts and rejects."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.bug import BugContract

VALID = {
    "id": "bug_000001",
    "severity": "high",
    "scope_id": "scope_memory_safety",
    "description": "a real description",
    "repro_path": "poc/x",
    "repro_usage": "run it",
    "missing_for_full_chain": "nothing",
}


def test_valid_contract_round_trips():
    assert BugContract.model_validate(VALID).severity == "high"


@pytest.mark.parametrize(
    "sev", ["critical", "high", "medium", "low", "info", "unknown"]
)
def test_all_documented_severities_accepted(sev):
    assert BugContract.model_validate({**VALID, "severity": sev}).severity == sev


def test_unknown_severity_rejected():
    with pytest.raises(ValidationError):
        BugContract.model_validate({**VALID, "severity": "spicy"})


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        BugContract.model_validate({**VALID, "exploitability": 9000})


@pytest.mark.parametrize(
    "field",
    ["id", "scope_id", "description", "repro_path", "repro_usage", "missing_for_full_chain"],
)
def test_required_string_fields_reject_empty(field):
    with pytest.raises(ValidationError):
        BugContract.model_validate({**VALID, field: ""})


@pytest.mark.parametrize(
    "field",
    ["id", "severity", "scope_id", "description", "repro_path", "repro_usage",
     "missing_for_full_chain"],
)
def test_every_field_is_required(field):
    payload = {k: v for k, v in VALID.items() if k != field}
    with pytest.raises(ValidationError):
        BugContract.model_validate(payload)
