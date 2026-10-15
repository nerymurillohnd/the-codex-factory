"""Independent assessment is required; the reconciler still owns the final judgment."""

import asyncio

import pytest
from agent_context_audit.baseline import assign_ids
from agent_context_audit.discovery import discover_sources
from agent_context_audit.models import DomainResult, KnowledgeBundle, ReconciledAudit, RunOptions
from agent_context_audit.snapshot import build_snapshot

from tests.conftest import put
from tests.test_contracts import finding
from tests.test_runtime import make_runtime


def setup_case(context_tree, tmp_path):
    target, roots = context_tree
    put(target.root / "AGENTS.md", "Run npm absent\n")
    snapshot = build_snapshot(discover_sources(target, roots), target)
    sid = snapshot.inventory.sources[0].source_id
    item = finding()
    item.update(
        source_id=sid,
        evidence=[{"kind": "related-directive", "ref": sid, "quote": "Run npm absent"}],
    )
    assign_ids([item])
    audit = ReconciledAudit(
        [item],
        [
            {
                "directive_id": d.directive_id,
                "disposition": "revise",
                "rationale": "Candidate",
                "evidence_refs": [sid],
            }
            for d in snapshot.directives
        ],
    )
    runtime = make_runtime(tmp_path)
    options = RunOptions(target, roots, tmp_path / "reports", runtime.auth_home, runtime.binary)
    return audit, snapshot, runtime, options


@pytest.mark.parametrize("mode", ["missing", "stale"])
def test_missing_or_stale_semantic_assessment_is_incomplete(context_tree, tmp_path, mode):
    from agent_context_audit.verification import verify_audit

    audit, snapshot, runtime, options = setup_case(context_tree, tmp_path)

    async def absent(runtime, request):
        import json

        data = json.loads(request.prompt.split("\nAUDIT_DATA_JSON\n")[1])
        assessments = (
            []
            if mode == "missing"
            else [
                {
                    "target_id": data["targets"][0]["target_id"],
                    "target_digest": "0" * 64,
                    "verdict": "supported",
                    "rationale": "Stale evidence",
                    "evidence": audit.findings[0]["evidence"],
                    "counterevidence": [],
                }
            ]
        )
        return DomainResult(
            request.job_id,
            request.domain,
            "complete",
            {
                "status": "complete",
                "assessments": assessments,
                "evidence_requests": [],
                "limitations": [],
                "notes": [],
            },
        )

    result = asyncio.run(
        verify_audit(audit, snapshot, runtime, options, KnowledgeBundle({}), reviewer=absent)
    )
    assert result.limitations
    assert not result.assessments


def test_supported_reconciler_override_is_visible_without_becoming_partial(context_tree, tmp_path):
    import json

    from agent_context_audit.verification import adjudicate_audit, verify_audit

    audit, snapshot, runtime, options = setup_case(context_tree, tmp_path)
    evidence = audit.findings[0]["evidence"]

    async def reviewer(runtime, request):
        data = json.loads(request.prompt.split("\nAUDIT_DATA_JSON\n")[1])
        targets = data["targets"]
        if request.schema_name == "verification":
            value = {
                "status": "complete",
                "assessments": [
                    {
                        "target_id": t["target_id"],
                        "target_digest": t["target_digest"],
                        "verdict": "challenged",
                        "rationale": "The excerpt alone does not establish absence",
                        "evidence": evidence,
                        "counterevidence": evidence,
                    }
                    for t in targets
                ],
                "evidence_requests": [],
                "limitations": [],
                "notes": [],
            }
        else:
            value = {
                "decisions": [
                    {
                        "target_id": t["target_id"],
                        "target_digest": t["target_digest"],
                        "action": "upheld-over-objection",
                        "rationale": "Keep the proposed investigation with the recorded objection",
                        "evidence": evidence,
                        "counterevidence": evidence,
                        "finding": None,
                        "observation_decision": None,
                    }
                    for t in targets
                ],
                "additional_findings": [],
                "limitations": [],
                "notes": [],
            }
        return DomainResult(request.job_id, request.domain, "complete", value)

    async def run():
        verified = await verify_audit(
            audit, snapshot, runtime, options, KnowledgeBundle({}), reviewer=reviewer
        )
        assert not verified.limitations
        final = await adjudicate_audit(
            audit, verified, snapshot, runtime, options, KnowledgeBundle({}), reviewer=reviewer
        )
        assert not final.limitations
        assert final.findings
        assert final.adjudications[0]["action"] == "upheld-over-objection"
        assert final.dissent

    asyncio.run(run())


def test_semantic_digest_changes_when_recommendation_changes(context_tree, tmp_path):
    from agent_context_audit.verification import verification_targets

    audit, _, _, _ = setup_case(context_tree, tmp_path)
    before = verification_targets(audit)[0]
    audit.findings[0]["replacement"] = "A different obligation."
    after = verification_targets(audit)[0]
    assert before["target_id"] == after["target_id"]
    assert before["target_digest"] != after["target_digest"]


def test_adjudicator_cannot_publish_revision_without_replacement(context_tree, tmp_path):
    import json

    from agent_context_audit.models import VerificationResult
    from agent_context_audit.verification import adjudicate_audit, verification_targets

    audit, snapshot, runtime, options = setup_case(context_tree, tmp_path)
    target = verification_targets(audit)[0]
    proof = audit.findings[0]["evidence"]
    verified = VerificationResult(
        [
            {
                **{k: target[k] for k in ("target_id", "target_digest")},
                "verdict": "supported",
                "rationale": "checked",
                "evidence": proof,
                "counterevidence": [],
            }
        ]
    )

    async def reviewer(runtime, request):
        data = json.loads(request.prompt.split("\nAUDIT_DATA_JSON\n")[1])
        item = {k: v for k, v in data["targets"][0]["value"].items() if k != "id"}
        item["replacement"] = None
        value = {
            "decisions": [
                {
                    "target_id": target["target_id"],
                    "target_digest": target["target_digest"],
                    "action": "revised",
                    "rationale": "Incomplete rewrite",
                    "evidence": proof,
                    "counterevidence": [],
                    "finding": item,
                    "observation_decision": None,
                }
            ],
            "additional_findings": [],
            "limitations": [],
            "notes": [],
        }
        return DomainResult(request.job_id, request.domain, "complete", value)

    final = asyncio.run(
        adjudicate_audit(
            audit, verified, snapshot, runtime, options, KnowledgeBundle({}), reviewer=reviewer
        )
    )
    assert final.limitations
    assert final.findings[0]["replacement"] == "Run npm test"


def test_rejected_finding_does_not_leave_a_stale_revision_disposition(context_tree, tmp_path):
    from agent_context_audit.models import VerificationResult
    from agent_context_audit.verification import adjudicate_audit, verification_targets

    audit, snapshot, runtime, options = setup_case(context_tree, tmp_path)
    target = verification_targets(audit)[0]
    proof = audit.findings[0]["evidence"]
    verified = VerificationResult(
        [
            {
                **{k: target[k] for k in ("target_id", "target_digest")},
                "verdict": "challenged",
                "rationale": "No evidence of defect",
                "evidence": proof,
                "counterevidence": proof,
            }
        ]
    )

    async def reviewer(runtime, request):
        value = {
            "decisions": [
                {
                    "target_id": target["target_id"],
                    "target_digest": target["target_digest"],
                    "action": "rejected",
                    "rationale": "Withdraw unsupported revision",
                    "evidence": proof,
                    "counterevidence": proof,
                    "finding": None,
                    "observation_decision": None,
                }
            ],
            "additional_findings": [],
            "limitations": [],
            "notes": [],
        }
        return DomainResult(request.job_id, request.domain, "complete", value)

    final = asyncio.run(
        adjudicate_audit(
            audit, verified, snapshot, runtime, options, KnowledgeBundle({}), reviewer=reviewer
        )
    )
    assert not final.findings
    assert final.dispositions[0]["disposition"] == "keep"


def test_delta_observation_uses_stable_ids_not_filtered_batch_positions():
    from agent_context_audit.verification import verification_targets

    audit = ReconciledAudit(
        [],
        [],
        observation_decisions=[
            {
                "observation_id": "obs-x",
                "outcome": "confirmed",
                "rationale": "Existing finding",
                "evidence_refs": ["src-x"],
                "finding_ids": ["ACA-existing"],
                "finding_indexes": [4],
            }
        ],
    )
    assert verification_targets(audit)[0]["value"]["finding_ids"] == ["ACA-existing"]


def test_revised_conclusion_gets_delta_verification_and_terminal_cannot_rewrite(
    context_tree, tmp_path
):
    import json

    from agent_context_audit.verification import complete_semantic_review

    audit, snapshot, runtime, options = setup_case(context_tree, tmp_path)
    evidence = audit.findings[0]["evidence"]
    assessed = []

    async def reviewer(runtime, request):
        data = json.loads(request.prompt.split("\nAUDIT_DATA_JSON\n")[1])
        target = data["targets"][0]
        if request.schema_name == "verification":
            assessed.append(target["value"]["replacement"])
            value = {
                "status": "complete",
                "assessments": [
                    {
                        "target_id": target["target_id"],
                        "target_digest": target["target_digest"],
                        "verdict": "supported",
                        "rationale": "Checked the obligation",
                        "evidence": evidence,
                        "counterevidence": [],
                    }
                ],
                "evidence_requests": [],
                "limitations": [],
                "notes": [],
            }
        else:
            replacement = {k: v for k, v in target["value"].items() if k != "id"}
            replacement["replacement"] = (
                "Unreviewed terminal rewrite"
                if data["terminal"]
                else "Run npm test before delivery."
            )
            value = {
                "decisions": [
                    {
                        "target_id": target["target_id"],
                        "target_digest": target["target_digest"],
                        "action": "revised",
                        "rationale": "Preserve the deadline",
                        "evidence": evidence,
                        "counterevidence": [],
                        "finding": replacement,
                        "observation_decision": None,
                    }
                ],
                "additional_findings": [],
                "limitations": [],
                "notes": [],
            }
        return DomainResult(request.job_id, request.domain, "complete", value)

    final = asyncio.run(
        complete_semantic_review(
            audit, snapshot, runtime, options, KnowledgeBundle({}), reviewer=reviewer
        )
    )
    assert assessed == ["Run npm test", "Run npm test before delivery."]
    assert final.findings[0]["replacement"] == "Run npm test before delivery."
    assert final.limitations
