"""The controller accounts for every contribution and validates actual evidence."""

import asyncio
import json
import time

import pytest
from agent_context_audit.discovery import discover_sources
from agent_context_audit.models import DomainResult, KnowledgeBundle, RunOptions
from agent_context_audit.review import review_domains, validate_findings
from agent_context_audit.snapshot import build_snapshot, validate_coverage

from tests.conftest import put
from tests.test_contracts import finding
from tests.test_runtime import make_runtime


def test_parallel_jobs_overlap_and_receipt_assignment_is_enforced(context_tree, tmp_path):
    target, roots = context_tree
    put(target.root / "AGENTS.md", "Run the test suite.\n")
    put(target.root / "CLAUDE.md", "Validate every change.\n")
    snapshot = build_snapshot(discover_sources(target, roots), target)
    options = RunOptions(target, roots, tmp_path / "reports", tmp_path / "auth", tmp_path / "bin")
    intervals = []

    async def reviewer(runtime, request):
        payload = json.loads(request.prompt.split("\nAUDIT_DATA_JSON\n", 1)[1])
        start = time.monotonic()
        await asyncio.sleep(0.05)
        intervals.append((start, time.monotonic()))
        return DomainResult(
            request.job_id,
            request.domain,
            "complete",
            {
                "status": "complete",
                "findings": [],
                "evidence_requests": [],
                "limitations": [],
                "receipts": [
                    {"chunk_id": c["chunk_id"], "payload_sha256": c["payload_sha256"]}
                    for c in payload["chunks"]
                ],
                "dispositions": [
                    {
                        "directive_id": d["directive_id"],
                        "disposition": "keep",
                        "rationale": "Applicable local policy",
                        "evidence_refs": [d["source_id"]],
                    }
                    for d in payload["directives"]
                ],
            },
        )

    results = asyncio.run(
        review_domains(
            snapshot, make_runtime(tmp_path), options, KnowledgeBundle({}), reviewer=reviewer
        )
    )
    assert len(results) == 2
    assert max(start for start, _ in intervals) < min(end for _, end in intervals)
    assert validate_coverage(snapshot, results).complete
    results[0].output["receipts"] = results[1].output["receipts"]
    assert not validate_coverage(snapshot, results).complete


def test_finding_rejects_invented_excerpt_or_evidence(context_tree):
    target, roots = context_tree
    put(target.root / "AGENTS.md", "Run npm absent\n")
    snapshot = build_snapshot(discover_sources(target, roots), target)
    item = finding()
    item["source_id"] = snapshot.inventory.sources[0].source_id
    with pytest.raises(ValueError, match="evidence"):
        validate_findings([item], snapshot, KnowledgeBundle({}))
    item["excerpt"] = "invented instruction"
    with pytest.raises(ValueError, match="excerpt"):
        validate_findings([item], snapshot, KnowledgeBundle({}))


def test_review_cannot_silently_drop_missing_worker(context_tree):
    target, roots = context_tree
    put(target.root / "AGENTS.md", "Keep legitimate business policy.\n")
    snapshot = build_snapshot(discover_sources(target, roots), target)
    assert not validate_coverage(snapshot, []).complete
