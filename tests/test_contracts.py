"""Incomplete or unsupported model output must not become a clean report."""

import pytest
from agent_context_audit.contracts import provider_schema, validate_output
from jsonschema import ValidationError


def empty_result() -> dict[str, object]:
    return {
        "status": "complete",
        "receipts": [],
        "dispositions": [],
        "findings": [],
        "evidence_requests": [],
        "limitations": [],
        "notes": [],
        "observation_decisions": [],
    }


def finding() -> dict[str, object]:
    return {
        "category": "wrong",
        "severity": "medium",
        "confidence": "high",
        "title": "Command does not exist",
        "source_id": "src-1",
        "line_start": 1,
        "line_end": 1,
        "excerpt": "Run npm absent",
        "related": [],
        "conflicts_with": "package.json has no absent script",
        "evidence": [{"kind": "repository-fact", "ref": "repo:package.json:1", "quote": "scripts"}],
        "impact": ["correctness"],
        "disposition": "revise",
        "target_location": None,
        "replacement": "Run npm test",
        "rationale": "The named script is absent",
        "tradeoffs": "The replacement requires the existing test script",
        "tags": ["testing"],
        "subject": "test-command",
        "observation_ids": [],
    }


def test_contract_rejects_missing_conflicts_with() -> None:
    result = empty_result()
    item = finding()
    item.pop("conflicts_with")
    result["findings"] = [item]
    with pytest.raises(ValidationError):
        validate_output(result)


def test_contract_rejects_unknown_output_fields() -> None:
    result = empty_result()
    result["shell_command"] = "touch arbitrary-file"
    with pytest.raises(ValidationError):
        validate_output(result)


def test_contract_rejects_model_only_removal() -> None:
    result = empty_result()
    item = finding()
    item.update(
        category="redundant-with-defaults",
        confidence="low",
        disposition="remove",
        evidence=[{"kind": "model-judgment", "ref": "model", "quote": "seems obvious"}],
    )
    result["findings"] = [item]
    with pytest.raises(ValueError, match="removal"):
        validate_output(result)


def test_provider_schema_keeps_local_duplicate_validation():
    adapted = provider_schema("reconciliation")
    indexes = adapted["properties"]["decisions"]["items"]["properties"]["final_finding_indexes"]
    assert "uniqueItems" not in indexes
    duplicate = {
        "findings": [finding()],
        "dispositions": [],
        "considered_job_ids": ["D1-0"],
        "contested": [],
        "limitations": [],
        "notes": [],
        "decisions": [
            {
                "finding_key": "D1-0:finding:0",
                "decision": "kept",
                "rationale": "Retain supported finding",
                "evidence_refs": ["src-1"],
                "final_finding_indexes": [0, 0],
            }
        ],
    }
    with pytest.raises(ValidationError, match="non-unique"):
        validate_output(duplicate, "reconciliation")
