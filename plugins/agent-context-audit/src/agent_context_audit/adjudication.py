"""The final reconciler may disagree, but cannot silently replace unreviewed content."""

import copy
import uuid

from jsonschema import ValidationError

from agent_context_audit.baseline import assign_ids
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
from agent_context_audit.observations import (
    remap_observation_decisions,
    validate_observation_decisions,
)
from agent_context_audit.review import Reviewer, prompt_for, validate_findings
from agent_context_audit.runtime import run_review_job
from agent_context_audit.semantic_context import (
    build_semantic_payload,
    pack_semantic_targets,
    validate_semantic_evidence,
    verification_targets,
)


def _apply(audit, outputs, snapshot, knowledge, terminal):
    candidate = copy.deepcopy(audit)
    findings = {f["id"]: f for f in candidate.findings}
    observations = {d["observation_id"]: d for d in candidate.observation_decisions}
    aliases = {}
    for batch_index, output in enumerate(outputs):
        for index, finding in enumerate(output["additional_findings"]):
            item = copy.deepcopy(finding)
            assign_ids([item])
            aliases[f"{batch_index}:new:{index}"] = item["id"]
            findings[item["id"]] = item
        for decision in output["decisions"]:
            target = decision["target_id"]
            identifier = target.split(":", 1)[1]
            if decision["action"] == "rejected":
                findings.pop(identifier)
            elif decision["action"] == "revised":
                if target.startswith("finding:"):
                    item = copy.deepcopy(decision["finding"])
                    assign_ids([item])
                    findings.pop(identifier)
                    findings[item["id"]] = item
                    aliases[identifier] = item["id"]
                else:
                    item = copy.deepcopy(decision["observation_decision"])
                    item["finding_ids"] = [
                        aliases.get(f"{batch_index}:{fid}", fid) for fid in item["finding_ids"]
                    ]
                    observations[identifier] = item
            candidate.adjudications.append(copy.deepcopy(decision))
        candidate.limitations.extend(output["limitations"])
        candidate.notes.extend(output["notes"])
    candidate.findings = [findings[key] for key in sorted(findings)]
    candidate.observation_decisions = list(observations.values())
    for decision in candidate.observation_decisions:
        decision["finding_ids"] = [aliases.get(fid, fid) for fid in decision.get("finding_ids", [])]
        if any(fid not in findings for fid in decision["finding_ids"]):
            raise ValueError("Adjudication left a dangling observation destination")
    remap_observation_decisions(candidate)
    validate_output(
        {
            "status": "complete",
            "receipts": [],
            "dispositions": [],
            "findings": [
                {k: v for k, v in item.items() if k != "id"} for item in candidate.findings
            ],
            "evidence_requests": [],
            "limitations": [],
            "notes": [],
            "observation_decisions": [],
        }
    )
    validate_findings(candidate.findings, snapshot, knowledge)
    validate_observation_decisions(
        {"findings": candidate.findings, "observation_decisions": candidate.observation_decisions},
        [o.observation_id for o in snapshot.observations],
        snapshot,
        knowledge,
    )
    # Earlier reconciliation decisions remain a historical ledger, never stale live indexes.
    for decision in candidate.decisions:
        decision["adjudicated_finding_ids"] = [
            aliases.get(fid, fid)
            for fid in decision.get("final_finding_ids", [])
            if aliases.get(fid, fid) in findings
        ]
    changed_ranges = [
        item
        for item in audit.findings
        if any(
            d["target_id"] == "finding:" + item["id"] and d["action"] in {"rejected", "revised"}
            for output in outputs
            for d in output["decisions"]
        )
    ]
    directives = {d.directive_id: d for d in snapshot.directives}
    for disposition in candidate.dispositions:
        directive = directives[disposition["directive_id"]]
        if not any(
            f["source_id"] == directive.source_id
            and f["line_start"] <= directive.line_start <= f["line_end"]
            for f in changed_ranges
        ):
            continue
        remaining = [
            f
            for f in candidate.findings
            if f["source_id"] == directive.source_id
            and f["line_start"] <= directive.line_start <= f["line_end"]
        ]
        choices = {f["disposition"] for f in remaining}
        disposition["disposition"] = (
            next(iter(choices)) if len(choices) == 1 else "investigate" if choices else "keep"
        )
        disposition["rationale"] = "Final adjudication: " + (
            "; ".join(f["rationale"] for f in remaining)
            if remaining
            else "The proposed defect was rejected; retain the instruction"
        )
        disposition["evidence_refs"] = [directive.source_id]
    return candidate


async def adjudicate_audit(
    audit: ReconciledAudit,
    verification: VerificationResult,
    snapshot: AuditSnapshot,
    runtime: CodexRuntime,
    options: RunOptions,
    knowledge: KnowledgeBundle,
    *,
    reviewer: Reviewer = run_review_job,
    terminal: bool = False,
) -> ReconciledAudit:
    targets = verification_targets(audit)
    assessments = {(a["target_id"], a["target_digest"]): a for a in verification.assessments}
    audit.assessments.extend(copy.deepcopy(verification.assessments))
    audit.jobs.extend(verification.jobs)
    audit.limitations.extend(verification.limitations)
    if any((t["target_id"], t["target_digest"]) not in assessments for t in targets):
        audit.limitations.append("Final adjudication lacks independent assessments")
        return audit
    prefix = "adjudicate-" + uuid.uuid4().hex[:10]
    outputs = []
    try:
        for index, batch in enumerate(
            pack_semantic_targets(
                targets, snapshot, knowledge, "adjudicator", verification.assessments, terminal
            )
        ):
            expected = {t["target_id"]: t["target_digest"] for t in batch}
            selected = [a for a in verification.assessments if a["target_id"] in expected]

            def validate(value, expected=expected):
                actual = [d["target_id"] for d in value["decisions"]]
                if set(actual) != set(expected) or len(actual) != len(set(actual)):
                    raise ValueError("Adjudication did not decide every assessed target")
                if terminal and value["additional_findings"]:
                    raise ValueError("Terminal adjudication cannot introduce unassessed findings")
                for decision in value["decisions"]:
                    key = (decision["target_id"], decision["target_digest"])
                    if decision["target_digest"] != expected[decision["target_id"]]:
                        raise ValueError("Adjudication uses a stale assessment")
                    action = decision["action"]
                    if not decision["evidence"]:
                        raise ValueError("Adjudication requires evidence")
                    validate_semantic_evidence(
                        [*decision["evidence"], *decision["counterevidence"]], snapshot, knowledge
                    )
                    if action == "kept" and assessments[key]["verdict"] == "challenged":
                        raise ValueError("A challenged conclusion needs an explicit override")
                    if action == "upheld-over-objection" and not decision["counterevidence"]:
                        raise ValueError("An override must retain counterevidence")
                    is_finding = decision["target_id"].startswith("finding:")
                    if action == "rejected" and not is_finding:
                        raise ValueError("An observation cannot disappear")
                    if action == "revised":
                        if terminal:
                            raise ValueError(
                                "Terminal adjudication cannot rewrite assessed content"
                            )
                        field = "finding" if is_finding else "observation_decision"
                        other = "observation_decision" if is_finding else "finding"
                        if decision[field] is None or decision[other] is not None:
                            raise ValueError("Invalid revised target")
                        if (
                            not is_finding
                            and decision[field]["observation_id"]
                            != decision["target_id"].split(":", 1)[1]
                        ):
                            raise ValueError("Observation identity changed")
                    elif (
                        decision["finding"] is not None
                        or decision["observation_decision"] is not None
                    ):
                        raise ValueError("Unchanged target carries an unassessed rewrite")

            payload = build_semantic_payload(batch, snapshot, knowledge, selected, terminal)
            payload["prior_disagreements"] = audit.dissent
            job = await reviewer(
                runtime,
                ReviewRequest(
                    f"{prefix}-{index}",
                    "adjudication",
                    prompt_for("adjudicator", payload),
                    "adjudication",
                    validate,
                ),
            )
            audit.jobs.append(job)
            if job.status != "complete":
                raise ValueError("Final reconciler failed")
            validate_output(job.output, "adjudication")
            validate(job.output)
            outputs.append(job.output)
        candidate = _apply(audit, outputs, snapshot, knowledge, terminal)
        for assessment in verification.assessments:
            if assessment["verdict"] != "supported":
                candidate.dissent.append({"semantic_assessment": copy.deepcopy(assessment)})
        return candidate
    except (ValueError, OSError, KeyError, ValidationError) as exc:
        audit.limitations.append("Final adjudication incomplete: " + type(exc).__name__)
        return audit
