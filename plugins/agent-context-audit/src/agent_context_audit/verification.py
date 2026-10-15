"""Independent semantic assessments, bounded revision, and terminal adjudication."""

import asyncio
import copy
import uuid

from jsonschema import ValidationError

from agent_context_audit.adjudication import adjudicate_audit
from agent_context_audit.contracts import validate_output
from agent_context_audit.models import (
    AuditSnapshot,
    CodexRuntime,
    KnowledgeBundle,
    ReconciledAudit,
    ReviewRequest,
    RunOptions,
    VerificationResult,
)
from agent_context_audit.review import Reviewer, prompt_for
from agent_context_audit.runtime import run_review_job
from agent_context_audit.semantic_context import (
    build_semantic_payload,
    pack_semantic_targets,
    supply_semantic_evidence,
    validate_semantic_evidence,
    verification_targets,
)


async def verify_audit(
    audit: ReconciledAudit,
    snapshot: AuditSnapshot,
    runtime: CodexRuntime,
    options: RunOptions,
    knowledge: KnowledgeBundle,
    *,
    reviewer: Reviewer = run_review_job,
) -> VerificationResult:
    result = VerificationResult()
    targets = verification_targets(audit)
    prefix = "verify-" + uuid.uuid4().hex[:10]
    semaphore = asyncio.Semaphore(options.jobs)

    async def run(index, batch):
        expected = {t["target_id"]: t["target_digest"] for t in batch}
        payload = build_semantic_payload(batch, snapshot, knowledge)
        payload["prior_disagreements"] = audit.dissent

        def validate(value):
            if value.get("evidence_requests"):
                return
            assessments = value["assessments"]
            actual = [a["target_id"] for a in assessments]
            if set(actual) != set(expected) or len(actual) != len(set(actual)):
                raise ValueError("Semantic assessment assignment is incomplete or duplicated")
            for item in assessments:
                if item["target_digest"] != expected[item["target_id"]]:
                    raise ValueError("Semantic assessment uses a stale target digest")
                if not item["evidence"] or (
                    item["verdict"] == "challenged" and not item["counterevidence"]
                ):
                    raise ValueError("Semantic assessment lacks evidence or counterevidence")
                validate_semantic_evidence(
                    [*item["evidence"], *item["counterevidence"]], snapshot, knowledge
                )

        async with semaphore:
            try:
                for round_number in range(3):
                    request = ReviewRequest(
                        f"{prefix}-{index}-e{round_number}",
                        "verification",
                        prompt_for("verifier", payload),
                        "verification",
                        validate,
                    )
                    job = await reviewer(runtime, request)
                    result.jobs.append(job)
                    if job.status == "failed":
                        raise ValueError("Independent verifier failed: " + job.error)
                    validate_output(job.output, "verification")
                    requests = job.output["evidence_requests"]
                    if requests:
                        if round_number == 2 or len(requests) > 8:
                            raise ValueError("Semantic verifier evidence request limit reached")
                        for item in requests:
                            try:
                                payload["evidence_history"].append(
                                    {
                                        "request": item,
                                        "result": supply_semantic_evidence(
                                            item, snapshot, knowledge
                                        ),
                                    }
                                )
                            except (OSError, ValueError, UnicodeError) as exc:
                                payload["evidence_history"].append(
                                    {"request": item, "error": type(exc).__name__}
                                )
                        continue
                    if job.status != "complete":
                        raise ValueError("Independent verification remained incomplete")
                    validate(job.output)
                    result.assessments.extend(job.output["assessments"])
                    result.limitations.extend(job.output["limitations"])
                    for item in job.output["assessments"]:
                        if item["verdict"] == "unverifiable":
                            result.limitations.append(
                                "Essential semantic evidence unavailable: " + item["target_id"]
                            )
                    break
            except (ValueError, OSError, ValidationError) as exc:
                result.limitations.append(
                    f"Verification batch {index} incomplete: {type(exc).__name__}"
                )

    tasks = [
        asyncio.create_task(run(i, batch))
        for i, batch in enumerate(pack_semantic_targets(targets, snapshot, knowledge, "verifier"))
    ]
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    result.assessments.sort(key=lambda a: a["target_id"])
    result.limitations = sorted(set(result.limitations))
    return result


async def complete_semantic_review(
    audit: ReconciledAudit,
    snapshot: AuditSnapshot,
    runtime: CodexRuntime,
    options: RunOptions,
    knowledge: KnowledgeBundle,
    *,
    reviewer: Reviewer = run_review_job,
) -> ReconciledAudit:
    before = {(t["target_id"], t["target_digest"]) for t in verification_targets(audit)}
    verification = await verify_audit(
        audit, snapshot, runtime, options, knowledge, reviewer=reviewer
    )
    audit = await adjudicate_audit(
        audit, verification, snapshot, runtime, options, knowledge, reviewer=reviewer
    )
    after = {(t["target_id"], t["target_digest"]) for t in verification_targets(audit)}
    if after - before:
        # Reuse exact matching assessments; independently review only new semantic versions.
        pending = copy.deepcopy(audit)
        existing = {(a["target_id"], a["target_digest"]) for a in verification.assessments}
        new_ids = {
            t["target_id"]
            for t in verification_targets(audit)
            if (t["target_id"], t["target_digest"]) not in existing
        }
        pending.findings = [f for f in pending.findings if "finding:" + f["id"] in new_ids]
        pending.observation_decisions = [
            d
            for d in pending.observation_decisions
            if "observation:" + d["observation_id"] in new_ids
        ]
        delta = await verify_audit(
            pending, snapshot, runtime, options, knowledge, reviewer=reviewer
        )
        current_keys = {(t["target_id"], t["target_digest"]) for t in verification_targets(audit)}
        delta.assessments.extend(
            a
            for a in verification.assessments
            if (a["target_id"], a["target_digest"]) in current_keys
        )
        audit = await adjudicate_audit(
            audit, delta, snapshot, runtime, options, knowledge, reviewer=reviewer, terminal=True
        )
    verified = {(a["target_id"], a["target_digest"]) for a in audit.assessments}
    if any(
        (t["target_id"], t["target_digest"]) not in verified for t in verification_targets(audit)
    ):
        audit.limitations.append("Final result contains unassessed semantic content")
    audit.limitations = sorted(set(audit.limitations))
    return audit
