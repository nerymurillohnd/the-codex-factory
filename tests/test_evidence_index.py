"""Reviewers discover supporting evidence from scoped metadata, without guessing paths."""

import asyncio
import json

from agent_context_audit.discovery import discover_sources
from agent_context_audit.evidence import collect_repository_facts, read_evidence
from agent_context_audit.models import DomainResult, KnowledgeBundle, RunOptions
from agent_context_audit.review import review_domains
from agent_context_audit.snapshot import build_snapshot, compare_sources

from tests.conftest import put
from tests.test_contracts import finding
from tests.test_runtime import make_runtime


def test_file_index_exposes_test_and_migration_paths_without_secret_files(context_tree):
    target, roots = context_tree
    put(target.root / "tests/unusual-test-name.py", "def test_case(): pass\n")
    put(target.root / "docs/CHANGE-POLICY.md", "Current verification policy.\n")
    put(target.root / ".env", "PRIVATE_FIXTURE_VALUE=must-not-read\n")
    snapshot = build_snapshot(discover_sources(target, roots), target)
    collect_repository_facts(snapshot)
    index = read_evidence(
        snapshot, {"path": "index:*", "line_start": 1, "line_end": 200, "reason": "locate evidence"}
    )
    assert "tests/unusual-test-name.py" in index["text"]
    assert "docs/CHANGE-POLICY.md" in index["text"]
    assert ".env" not in index["text"]
    assert "must-not-read" not in index["text"]
    put(target.root / "new-test.py", "pass\n")
    assert any(
        "file inventory" in change
        for change in compare_sources(snapshot, discover_sources(target, roots))
    )


def test_pending_finding_can_obtain_evidence_before_final_validation(context_tree, tmp_path):
    target, roots = context_tree
    put(target.root / "AGENTS.md", "Run npm absent\n")
    put(target.root / "verification.txt", "scripts already enforce formatting\n")
    snapshot = build_snapshot(discover_sources(target, roots), target)
    options = RunOptions(target, roots, tmp_path / "reports", tmp_path / "auth", tmp_path / "codex")
    calls = []

    async def reviewer(runtime, request):
        data = json.loads(request.prompt.split("\nAUDIT_DATA_JSON\n")[1])
        calls.append(request.job_id)
        source = snapshot.inventory.sources[0].source_id
        item = finding()
        item.update(source_id=source, category="redundant-with-defaults")
        if len(calls) == 1:
            item["evidence"] = [
                {"kind": "related-directive", "ref": source, "quote": "Run npm absent"}
            ]
            status = "needs-evidence"
            requests = [
                {
                    "path": "verification.txt",
                    "line_start": 1,
                    "line_end": 1,
                    "reason": "verify the mechanism",
                }
            ]
        else:
            item["evidence"] = [
                {"kind": "repository-fact", "ref": "repo:verification.txt:1-1", "quote": "scripts"}
            ]
            status = "complete"
            requests = []
        return DomainResult(
            request.job_id,
            "D1",
            status,
            {
                "status": status,
                "findings": [item],
                "receipts": [
                    {"chunk_id": c["chunk_id"], "payload_sha256": c["payload_sha256"]}
                    for c in data["chunks"]
                ],
                "dispositions": [
                    {
                        "directive_id": d["directive_id"],
                        "disposition": "revise",
                        "rationale": "Evidence confirms revision",
                        "evidence_refs": [source],
                    }
                    for d in data["directives"]
                ],
                "evidence_requests": requests,
                "limitations": [],
                "notes": [],
            },
        )

    results = asyncio.run(
        review_domains(
            snapshot, make_runtime(tmp_path), options, KnowledgeBundle({}), reviewer=reviewer
        )
    )
    assert len(calls) == 2
    assert results[0].status == "complete"
