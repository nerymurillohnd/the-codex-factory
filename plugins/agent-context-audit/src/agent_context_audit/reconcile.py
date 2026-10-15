"""Central reconciliation with explicit contribution, decision, and dissent ledgers."""

import asyncio
import itertools
import re
from dataclasses import asdict, replace

from agent_context_audit.baseline import assign_ids
from agent_context_audit.models import (
    AuditSnapshot,
    CodexRuntime,
    DomainResult,
    JsonObject,
    KnowledgeBundle,
    ReconciledAudit,
    ReviewRequest,
)
from agent_context_audit.observations import (
    normalize_decisions,
    remap_observation_decisions,
    validate_observation_decisions,
)
from agent_context_audit.review import (
    Reviewer,
    evidence_catalog,
    prompt_for,
    validate_dispositions,
    validate_findings,
)
from agent_context_audit.runtime import run_review_job


def topic_candidates(snapshot: AuditSnapshot) -> list[JsonObject]:
    """An exhaustive pair ledger; token overlap prioritizes work but never drops a pair."""
    groups = {}
    for chunk in snapshot.chunks:
        groups.setdefault(chunk.source_id, set()).update(
            re.findall(r"[a-z]{4,}", chunk.text.lower())
        )
    return [
        {"left": a, "right": b, "shared_terms": sorted(groups[a] & groups[b])[:40]}
        for a, b in itertools.combinations(sorted(groups), 2)
    ]


def _payload(usable: list[DomainResult], snapshot: AuditSnapshot, knowledge: KnowledgeBundle):
    contributions = [
        {
            "job_id": r.job_id,
            "domain": r.domain,
            "controller_status": r.status,
            "validation_error": r.error,
            "output": r.output,
            "finding_keys": [
                f"{r.job_id}:finding:{i}" for i in range(len(r.output.get("findings", [])))
            ],
        }
        for r in usable
    ]
    return {
        "sources": [asdict(s) for s in snapshot.inventory.sources],
        "chunks": [asdict(c) for c in snapshot.chunks],
        "directives": [asdict(d) for d in snapshot.directives],
        "contributions": contributions,
        "candidates": topic_candidates(snapshot),
        "platform": knowledge.data,
        "repository_facts": snapshot.facts,
        "challenges": [],
        "observations": [asdict(o) for o in snapshot.observations],
    }


async def _reconcile_batch(
    results: list[DomainResult],
    snapshot: AuditSnapshot,
    runtime: CodexRuntime,
    knowledge: KnowledgeBundle,
    *,
    challenge_rounds: int = 1,
    jobs: int = 4,
    reviewer: Reviewer = run_review_job,
    prefix: str = "global",
) -> ReconciledAudit:
    usable = [r for r in results if r.status in {"complete", "needs-evidence"}]
    audit = ReconciledAudit([], [])
    audit.limitations.extend(
        f"Unusable contribution: {r.job_id}" for r in results if r not in usable
    )
    if not usable and snapshot.chunks:
        audit.limitations.append("No usable specialist analysis")
        return audit
    payload = _payload(usable, snapshot, knowledge)
    expected_keys = {
        key for contribution in payload["contributions"] for key in contribution["finding_keys"]
    }
    # Never summarize away original sources or contributions to fit a context window.
    # Oversized global input fails visibly while retaining every specialist's findings.
    try:
        for round_number in range(challenge_rounds + 1):
            request = ReviewRequest(
                f"{prefix}-reconcile-{round_number}",
                "reconciliation",
                prompt_for("reconciler", payload),
                "reconciliation",
            )
            result = await reviewer(runtime, request)
            audit.jobs.append(result)
            if result.status != "complete":
                raise ValueError(f"Reconciliation failed: {result.error or result.status}")
            output = result.output
            if set(output["considered_job_ids"]) != {r.job_id for r in usable}:
                raise ValueError("Reconciliation did not consider every contribution")
            decisions = output.get("decisions", [])
            if {d["finding_key"] for d in decisions} != expected_keys or len(decisions) != len(
                expected_keys
            ):
                raise ValueError("Reconciliation did not decide every contributed finding")
            catalog = evidence_catalog(snapshot, knowledge)
            for item in [*decisions, *output["contested"]]:
                if not item["evidence_refs"] and expected_keys:
                    raise ValueError("Reconciliation decision lacks evidence")
                if any(ref not in catalog for ref in item["evidence_refs"]):
                    raise ValueError("Unknown reconciliation evidence")
            validate_findings(output["findings"], snapshot, knowledge)
            originals = {
                f"{r.job_id}:finding:{index}": finding
                for r in usable
                for index, finding in enumerate(r.output.get("findings", []))
            }
            for decision in decisions:
                indexes = decision["final_finding_indexes"]
                if any(index < 0 or index >= len(output["findings"]) for index in indexes):
                    raise ValueError("Reconciliation decision points to a missing final finding")
                if decision["decision"] in {"kept", "merged"} and not indexes:
                    raise ValueError("Retained finding disappeared from reconciliation")
                original = originals[decision["finding_key"]]
                for index in indexes:
                    final = output["findings"][index]
                    same_source = original["source_id"] == final["source_id"]
                    related = any(
                        item["source_id"] == original["source_id"]
                        and item["line_start"] <= original["line_start"]
                        and item["line_end"] >= original["line_end"]
                        for item in final["related"]
                    )
                    if not same_source and not related:
                        raise ValueError("Decision points to an unrelated final finding")
                    if decision["decision"] == "kept" and (
                        not same_source or original["excerpt"].strip() != final["excerpt"].strip()
                    ):
                        raise ValueError("Kept finding changed identity without a merge decision")
                if decision["decision"] == "rejected" and indexes:
                    raise ValueError("Rejected finding cannot name a retained destination")
                if decision["decision"] == "contested":
                    owner = decision["finding_key"].split(":finding:", 1)[0]
                    if not any(item["job_id"] == owner for item in output["contested"]):
                        raise ValueError("Contested finding has no recorded disagreement")
                    audit.dissent.append({"original_finding": original, "decision": decision})
            validate_dispositions(
                output, [d.directive_id for d in snapshot.directives], snapshot, knowledge
            )
            validate_observation_decisions(
                output, [o.observation_id for o in snapshot.observations], snapshot, knowledge
            )
            audit.findings = output["findings"]
            assign_ids(audit.findings)
            audit.observation_decisions = output.get("observation_decisions", [])
            normalize_decisions(audit)
            for decision in decisions:
                decision["final_finding_ids"] = [
                    audit.findings[index]["id"] for index in decision["final_finding_indexes"]
                ]
            audit.dispositions = output["dispositions"]
            audit.considered_job_ids = sorted(output["considered_job_ids"])
            audit.decisions = decisions
            audit.limitations.extend(output["limitations"])
            audit.notes.extend(output.get("notes", []))
            contested = output["contested"]
            if not contested:
                break
            audit.dissent.extend({"round": round_number, **item} for item in contested)
            if round_number == challenge_rounds:
                audit.notes.append("Reviewer disagreement retained for final adjudication")
                break
            owners = {r.job_id: r for r in usable}
            semaphore = asyncio.Semaphore(jobs)

            async def challenge(
                owner: str,
                items: list[JsonObject],
                owners=owners,
                semaphore=semaphore,
                catalog=catalog,
                round_number=round_number,
            ):
                if owner not in owners:
                    raise ValueError("Contested contribution references an unknown reviewer")
                async with semaphore:
                    data = {
                        "contribution": asdict(owners[owner]),
                        "contested": items,
                        "evidence": catalog,
                        "platform": knowledge.data,
                    }
                    reply = await reviewer(
                        runtime,
                        ReviewRequest(
                            f"{prefix}-challenge-{round_number}-{owner}",
                            owners[owner].domain,
                            prompt_for("challenge", data),
                        ),
                    )
                    audit.jobs.append(reply)
                    if reply.status != "complete":
                        raise ValueError("Challenge review failed")
                    validate_findings(reply.output.get("findings", []), snapshot, knowledge)
                    return {"owner": owner, "output": reply.output}

            grouped = {
                owner: [item for item in contested if item["job_id"] == owner]
                for owner in sorted({item["job_id"] for item in contested})
            }
            tasks = [
                asyncio.create_task(challenge(owner, items)) for owner, items in grouped.items()
            ]
            try:
                replies = await asyncio.gather(*tasks)
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
            payload["challenges"].extend(replies)
    except (OSError, ValueError, KeyError) as exc:
        audit.limitations.append(str(exc))
        # Retain useful original analysis; never promote an incomplete merge to complete.
        audit.findings = [
            *audit.findings,
            *(f for r in usable for f in r.output.get("findings", [])),
        ]
        audit.dispositions = [d for r in usable for d in r.output.get("dispositions", [])]
    assign_ids(audit.findings)
    unique = {}
    for finding in audit.findings:
        identifier = finding["id"]
        if identifier in unique and unique[identifier] != finding:
            audit.dissent.append(
                {"finding_id": identifier, "alternatives": [unique[identifier], finding]}
            )
            audit.notes.append(
                f"Conflicting finding variants retained for adjudication: {identifier}"
            )
        unique.setdefault(identifier, finding)
    audit.findings = [unique[key] for key in sorted(unique)]
    remap_decisions(audit)
    remap_observation_decisions(audit)
    audit.limitations = sorted(set(audit.limitations))
    return audit


def remap_decisions(audit: ReconciledAudit) -> None:
    """Model array positions must not survive sorting or merging as stale references."""
    positions = {finding["id"]: index for index, finding in enumerate(audit.findings)}
    for decision in audit.decisions:
        identifiers = decision.get("final_finding_ids", [])
        if any(identifier not in positions for identifier in identifiers):
            audit.limitations.append("Final decision references a missing retained finding")
        decision["final_finding_indexes"] = [
            positions[identifier] for identifier in identifiers if identifier in positions
        ]


def _subset(snapshot: AuditSnapshot, results: list[DomainResult]) -> AuditSnapshot:
    assigned = {identifier for result in results for identifier in result.assigned_chunks}
    if not assigned:
        domains = {r.domain for r in results}
        source_ids = {s.source_id for s in snapshot.inventory.sources if s.domain in domains}
        assigned = {c.chunk_id for c in snapshot.chunks if c.source_id in source_ids}
    chunks = [c for c in snapshot.chunks if c.chunk_id in assigned]
    ids = {c.source_id for c in chunks}
    inventory = replace(
        snapshot.inventory, sources=[s for s in snapshot.inventory.sources if s.source_id in ids]
    )
    return replace(
        snapshot,
        inventory=inventory,
        chunks=chunks,
        directives=[d for d in snapshot.directives if d.chunk_id in assigned],
        observations=[o for o in snapshot.observations if o.primary_source_id in ids],
    )


async def reconcile(
    results: list[DomainResult],
    snapshot: AuditSnapshot,
    runtime: CodexRuntime,
    knowledge: KnowledgeBundle,
    *,
    challenge_rounds: int = 1,
    jobs: int = 4,
    reviewer: Reviewer = run_review_job,
) -> ReconciledAudit:
    usable = [r for r in results if r.status in {"complete", "needs-evidence"}]
    try:
        prompt_for("reconciler", _payload(usable, snapshot, knowledge))
        fits = True
    except ValueError:
        fits = False
    if fits or len(usable) < 2:
        return await _reconcile_batch(
            results,
            snapshot,
            runtime,
            knowledge,
            challenge_rounds=challenge_rounds,
            jobs=jobs,
            reviewer=reviewer,
        )
    # Compare every complete shard pair. This preserves semantic comparisons even if
    # differently worded instructions have no terms in common. No summaries replace input.
    pairs = list(itertools.combinations(usable, 2))
    semaphore = asyncio.Semaphore(jobs)

    async def batch(index, pair):
        async with semaphore:
            return await _reconcile_batch(
                list(pair),
                _subset(snapshot, list(pair)),
                runtime,
                knowledge,
                challenge_rounds=challenge_rounds,
                jobs=1,
                reviewer=reviewer,
                prefix=f"pair-{index}",
            )

    tasks = [asyncio.create_task(batch(index, pair)) for index, pair in enumerate(pairs)]
    try:
        batches = await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    audit = ReconciledAudit([], [])
    findings: dict[str, JsonObject] = {}
    dispositions: dict[str, JsonObject] = {}
    observation_decisions: dict[str, JsonObject] = {}
    for index, result in enumerate(batches):
        audit.jobs.extend(result.jobs)
        audit.decisions.extend({"batch": index, **decision} for decision in result.decisions)
        audit.dissent.extend(result.dissent)
        audit.limitations.extend(result.limitations)
        audit.notes.extend(result.notes)
        audit.considered_job_ids.extend(result.considered_job_ids)
        for item in result.observation_decisions:
            previous = observation_decisions.get(item["observation_id"])
            if previous and previous != item:
                audit.dissent.append(
                    {"observation_id": item["observation_id"], "variants": [previous, item]}
                )
            observation_decisions.setdefault(item["observation_id"], item)
        for item in result.findings:
            previous = findings.get(item["id"])
            keys = ("disposition", "replacement", "target_location")
            if previous and any(previous[key] != item[key] for key in keys):
                audit.dissent.append({"finding_id": item["id"], "variants": [previous, item]})
                audit.notes.append(f"Batch disagreement retained for adjudication: {item['id']}")
            findings.setdefault(item["id"], item)
        for item in result.dispositions:
            previous = dispositions.get(item["directive_id"])
            if previous and previous["disposition"] != item["disposition"]:
                audit.dissent.append(
                    {"directive_id": item["directive_id"], "variants": [previous, item]}
                )
                audit.notes.append(f"Batch disposition disagreement: {item['directive_id']}")
            dispositions.setdefault(item["directive_id"], item)
    audit.findings = [findings[key] for key in sorted(findings)]
    audit.observation_decisions = [
        observation_decisions[key] for key in sorted(observation_decisions)
    ]
    remap_decisions(audit)
    remap_observation_decisions(audit)
    audit.dispositions = [dispositions[key] for key in sorted(dispositions)]
    audit.considered_job_ids = sorted(set(audit.considered_job_ids))
    if set(audit.considered_job_ids) != {r.job_id for r in usable}:
        audit.limitations.append("Batched reconciliation omitted a contribution")
    if set(dispositions) != {d.directive_id for d in snapshot.directives}:
        audit.limitations.append("Batched reconciliation omitted a directive")
    if set(observation_decisions) != {o.observation_id for o in snapshot.observations}:
        audit.limitations.append("Batched reconciliation omitted an observation")
    audit.limitations.extend(
        f"Unusable contribution: {r.job_id}" for r in results if r not in usable
    )
    audit.limitations = sorted(set(audit.limitations))
    return audit
