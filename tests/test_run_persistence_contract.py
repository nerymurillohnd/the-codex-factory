"""Persisted hybrid findings and adjudication ledgers must remain valid strict output."""

import pytest
from agent_context_audit.contracts import load_schema
from jsonschema import Draft202012Validator, ValidationError

from tests.test_contracts import finding


def persisted_validator(field: str) -> Draft202012Validator:
    return Draft202012Validator(load_schema("run")["properties"][field]["items"])


def decision() -> dict:
    return {
        "finding_key": "D1-0:finding:0",
        "decision": "kept",
        "rationale": "The verified finding remains supported.",
        "evidence_refs": ["src-1"],
        "final_finding_indexes": [0],
        "final_finding_ids": ["finding-1"],
        "adjudicated_finding_ids": ["finding-1"],
    }


def test_run_accepts_hybrid_finding_with_observation_provenance() -> None:
    item = dict(finding(), id="finding-1", observation_ids=["observation-1"])
    persisted_validator("findings").validate(item)


def test_run_accepts_nonempty_adjudicated_decision_ledger() -> None:
    persisted_validator("decisions").validate(decision())


@pytest.mark.parametrize("invalid", ["observation-1", [12]])
def test_run_rejects_malformed_observation_ids(invalid: object) -> None:
    item = dict(finding(), id="finding-1", observation_ids=invalid)
    with pytest.raises(ValidationError):
        persisted_validator("findings").validate(item)


@pytest.mark.parametrize("invalid", ["finding-1", [12]])
def test_run_rejects_malformed_adjudicated_ids(invalid: object) -> None:
    item = decision()
    item["adjudicated_finding_ids"] = invalid
    with pytest.raises(ValidationError):
        persisted_validator("decisions").validate(item)


@pytest.mark.parametrize("field", ["findings", "decisions"])
def test_persisted_items_still_reject_undeclared_fields(field: str) -> None:
    item = dict(finding(), id="finding-1") if field == "findings" else decision()
    item["arbitrary_unreviewed_field"] = True
    with pytest.raises(ValidationError):
        persisted_validator(field).validate(item)


def test_legacy_finding_without_observation_ids_remains_readable() -> None:
    item = dict(finding(), id="legacy-finding")
    item.pop("observation_ids")
    schema = load_schema("run-v1")["properties"]["findings"]["items"]
    Draft202012Validator(schema).validate(item)
