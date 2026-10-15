"""A reconciler cannot hide a domain or silently discard its findings."""

import asyncio
import json

from agent_context_audit.discovery import discover_sources
from agent_context_audit.models import DomainResult, KnowledgeBundle
from agent_context_audit.reconcile import reconcile
from agent_context_audit.snapshot import build_snapshot

from tests.conftest import put
from tests.test_runtime import make_runtime


def test_lost_reconciliation_contribution_is_partial(context_tree, tmp_path):
    target, roots = context_tree
    put(target.root / "AGENTS.md", "Retain applicable policy.\n")
    snapshot = build_snapshot(discover_sources(target, roots), target)
    contribution = DomainResult("D1-0", "D1", "complete", {"findings": [], "dispositions": []})

    async def drops_job(runtime, request):
        return DomainResult(
            request.job_id,
            "reconciliation",
            "complete",
            {
                "findings": [],
                "dispositions": [],
                "considered_job_ids": [],
                "decisions": [],
                "contested": [],
                "limitations": [],
            },
        )

    audit = asyncio.run(
        reconcile(
            [contribution],
            snapshot,
            make_runtime(tmp_path),
            KnowledgeBundle({}),
            reviewer=drops_job,
        )
    )
    assert audit.limitations
    assert not audit.considered_job_ids


def test_reconciler_receives_complete_cross_domain_text(context_tree, tmp_path):
    target, roots = context_tree
    put(target.root / "AGENTS.md", "Use npm for packages.\n")
    put(target.root / "CLAUDE.md", "Use pnpm for packages.\n")
    snapshot = build_snapshot(discover_sources(target, roots), target)
    contributions = [
        DomainResult("D1-0", "D1", "complete", {"findings": [], "dispositions": []}),
        DomainResult("D2-0", "D2", "complete", {"findings": [], "dispositions": []}),
    ]

    async def inspect(runtime, request):
        data = json.loads(request.prompt.split("\nAUDIT_DATA_JSON\n")[1])
        assert "Use npm" in request.prompt and "Use pnpm" in request.prompt
        assert len(data["contributions"]) == 2
        return DomainResult(
            request.job_id,
            "reconciliation",
            "complete",
            {
                "findings": [],
                "dispositions": [
                    {
                        "directive_id": d.directive_id,
                        "disposition": "keep",
                        "rationale": "Fixture control",
                        "evidence_refs": [d.source_id],
                    }
                    for d in snapshot.directives
                ],
                "considered_job_ids": [r.job_id for r in contributions],
                "decisions": [],
                "contested": [],
                "limitations": [],
            },
        )

    audit = asyncio.run(
        reconcile(
            contributions, snapshot, make_runtime(tmp_path), KnowledgeBundle({}), reviewer=inspect
        )
    )
    assert not audit.limitations
    assert len(audit.considered_job_ids) == 2


def test_final_decision_positions_follow_sorted_finding_ids():
    from agent_context_audit.models import ReconciledAudit
    from agent_context_audit.reconcile import remap_decisions

    audit = ReconciledAudit(
        [{"id": "ACA-a"}, {"id": "ACA-z"}],
        [],
        decisions=[
            {
                "finding_key": "source:0",
                "final_finding_indexes": [0],
                "final_finding_ids": ["ACA-z"],
            }
        ],
    )
    remap_decisions(audit)
    assert audit.decisions[0]["final_finding_indexes"] == [1]


def test_bounded_reconciliation_compares_every_complete_pair(context_tree, tmp_path, monkeypatch):
    target, roots = context_tree
    for name in ("AGENTS.md", "CLAUDE.md", "nested/AGENTS.md"):
        put(target.root / name, "Keep the applicable policy.\n")
    snapshot = build_snapshot(discover_sources(target, roots), target)
    contributions = [
        DomainResult(
            f"worker-{i}",
            "D1",
            "complete",
            {"findings": [], "dispositions": []},
            assigned_chunks=[chunk.chunk_id],
        )
        for i, chunk in enumerate(snapshot.chunks)
    ]
    from agent_context_audit.review import prompt_for as original

    def bounded(name, payload):
        if len(payload["contributions"]) > 2:
            raise ValueError("Synthetic context bound")
        return original(name, payload)

    monkeypatch.setattr("agent_context_audit.reconcile.prompt_for", bounded)
    observed = []

    async def reviewer(runtime, request):
        payload = json.loads(request.prompt.split("\nAUDIT_DATA_JSON\n")[1])
        ids = sorted(c["job_id"] for c in payload["contributions"])
        observed.append(ids)
        return DomainResult(
            request.job_id,
            "reconciliation",
            "complete",
            {
                "findings": [],
                "dispositions": [
                    {
                        "directive_id": d["directive_id"],
                        "disposition": "keep",
                        "rationale": "Applicable policy",
                        "evidence_refs": [d["source_id"]],
                    }
                    for d in payload["directives"]
                ],
                "considered_job_ids": ids,
                "decisions": [],
                "contested": [],
                "limitations": [],
            },
        )

    audit = asyncio.run(
        reconcile(
            contributions, snapshot, make_runtime(tmp_path), KnowledgeBundle({}), reviewer=reviewer
        )
    )
    assert len(observed) == 3
    assert len({tuple(pair) for pair in observed}) == 3
    assert len(audit.dispositions) == 3
    assert not audit.limitations
