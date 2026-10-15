"""Real controller behavior with bounded synthetic model responses."""

import asyncio
import json

from agent_context_audit.discovery import discover_sources
from agent_context_audit.models import DomainResult, KnowledgeBundle, RunOptions
from agent_context_audit.review import review_domains
from agent_context_audit.snapshot import build_snapshot, validate_coverage

from tests.conftest import put
from tests.test_contracts import empty_result, finding
from tests.test_runtime import make_runtime


def test_modifying_disposition_cannot_bypass_a_reviewable_finding(context_tree):
    import pytest
    from agent_context_audit.review import validate_dispositions

    target, roots = context_tree
    put(target.root / "AGENTS.md", "Keep signed commits.\n")
    snapshot = build_snapshot(discover_sources(target, roots), target)
    directive = snapshot.directives[0]
    output = {
        "findings": [],
        "dispositions": [
            {
                "directive_id": directive.directive_id,
                "disposition": "remove",
                "rationale": "Unjustified removal",
                "evidence_refs": [directive.source_id],
            }
        ],
    }
    with pytest.raises(ValueError, match="finding"):
        validate_dispositions(output, [directive.directive_id], snapshot, KnowledgeBundle({}))


def response(data):
    value = empty_result()
    value["receipts"] = [
        {"chunk_id": c["chunk_id"], "payload_sha256": c["payload_sha256"]} for c in data["chunks"]
    ]
    value["dispositions"] = [
        {
            "directive_id": d["directive_id"],
            "disposition": "keep",
            "rationale": "Intentional policy",
            "evidence_refs": [d["source_id"]],
        }
        for d in data["directives"]
    ]
    return value


def test_review_resolves_candidates_and_discovers_unflagged_findings(context_tree, tmp_path):
    target, roots = context_tree
    put(target.root / "AGENTS.md", "Keep signed commits.\nRun npm absent\n")
    put(target.root / "nested/AGENTS.md", "Keep signed commits.\n")
    snapshot = build_snapshot(discover_sources(target, roots), target)
    options = RunOptions(target, roots, tmp_path / "runs", tmp_path / "auth", tmp_path / "codex")
    saw_observations = []

    async def reviewer(runtime, request):
        data = json.loads(request.prompt.split("\nAUDIT_DATA_JSON\n")[1])
        value = response(data)
        for observation in data.get("observations", []):
            saw_observations.append(observation["observation_id"])
            value["observation_decisions"].append(
                {
                    "observation_id": observation["observation_id"],
                    "outcome": "dismissed",
                    "rationale": "The nested rule intentionally restates policy",
                    "evidence_refs": observation["evidence_refs"],
                    "finding_indexes": [],
                }
            )
        if "Run npm absent" in data["chunks"][0]["text"]:
            item = finding()
            item.update(
                source_id=data["sources"][0]["source_id"],
                line_start=2,
                line_end=2,
                evidence=[
                    {
                        "kind": "related-directive",
                        "ref": data["sources"][0]["source_id"],
                        "quote": "Run npm absent",
                    }
                ],
            )
            value["findings"] = [item]
        return DomainResult(request.job_id, request.domain, "complete", value)

    results = asyncio.run(
        review_domains(
            snapshot, make_runtime(tmp_path), options, KnowledgeBundle({}), reviewer=reviewer
        )
    )
    assert len(saw_observations) == 1
    assert validate_coverage(snapshot, results).complete
    found = [f for result in results for f in result.output["findings"]]
    assert len(found) == 1 and found[0]["observation_ids"] == []


def test_missing_observation_decision_prevents_complete_coverage(context_tree, tmp_path):
    target, roots = context_tree
    put(target.root / "CLAUDE.md", "@missing.md\n")
    snapshot = build_snapshot(discover_sources(target, roots), target)
    options = RunOptions(target, roots, tmp_path / "runs", tmp_path / "auth", tmp_path / "codex")

    async def reviewer(runtime, request):
        data = json.loads(request.prompt.split("\nAUDIT_DATA_JSON\n")[1])
        return DomainResult(request.job_id, request.domain, "complete", response(data))

    results = asyncio.run(
        review_domains(
            snapshot, make_runtime(tmp_path), options, KnowledgeBundle({}), reviewer=reviewer
        )
    )
    assert not validate_coverage(snapshot, results).complete
    assert results[0].status == "failed"
