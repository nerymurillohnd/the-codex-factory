"""Bounded parallel specialists with source-bound evidence and complete assignments."""

import asyncio
import json
from collections.abc import Awaitable, Callable

from agent_context_audit.assignments import build_review_packages, package_payload
from agent_context_audit.contracts import resource_path
from agent_context_audit.evidence import read_evidence
from agent_context_audit.knowledge import read_document_evidence
from agent_context_audit.models import (
    AuditSnapshot,
    CodexRuntime,
    DomainResult,
    JsonObject,
    KnowledgeBundle,
    ReviewRequest,
    RunOptions,
)
from agent_context_audit.observations import build_observations, validate_observation_decisions
from agent_context_audit.runtime import run_review_job

Reviewer = Callable[[CodexRuntime, ReviewRequest], Awaitable[DomainResult]]
MAX_PROMPT_BYTES = 160_000


def prompt_for(name: str, payload: JsonObject) -> str:
    instructions = resource_path("references", name + ".md").read_text()
    prompt = (
        instructions + "\nAUDIT_DATA_JSON\n" + json.dumps(payload, ensure_ascii=False, default=str)
    )
    if len(prompt.encode()) > MAX_PROMPT_BYTES:
        raise ValueError(
            "Complete review input exceeds bounded model context; no truncation allowed"
        )
    return prompt


def source_excerpt(snapshot: AuditSnapshot, source: str, first: int, last: int) -> str:
    text = snapshot.texts.get(source)
    if text is None or first < 1 or last < first or last > len(text.splitlines()):
        raise ValueError(
            f"Invalid source citation range: source_id={source!r}, lines={first}-{last}"
        )
    return "\n".join(text.splitlines()[first - 1 : last])


def evidence_catalog(snapshot: AuditSnapshot, knowledge: KnowledgeBundle) -> dict[str, str]:
    catalog = dict(snapshot.texts)
    catalog.update({d.directive_id: d.text for d in snapshot.directives})
    catalog.update({item["id"]: item["text"] for item in snapshot.facts})
    catalog.update({item["id"]: item["text"] for item in knowledge.data.get("claims", [])})
    return catalog


def validate_findings(
    findings: list[JsonObject], snapshot: AuditSnapshot, knowledge: KnowledgeBundle
) -> None:
    catalog = evidence_catalog(snapshot, knowledge)
    kinds = {source: {"related-directive"} for source in snapshot.texts}
    kinds.update({d.directive_id: {"related-directive"} for d in snapshot.directives})
    kinds.update(
        {
            item["id"]: {
                "related-directive" if item.get("kind") == "source-context" else "repository-fact"
            }
            for item in snapshot.facts
        }
    )
    kinds.update(
        {
            item["id"]: {"official-document", "native-default"}
            for item in knowledge.data.get("claims", [])
        }
    )
    for finding in findings:
        excerpt = source_excerpt(
            snapshot, finding["source_id"], finding["line_start"], finding["line_end"]
        )
        if not finding["excerpt"].strip() or finding["excerpt"] not in excerpt:
            raise ValueError("Finding excerpt is not present in the cited source range")
        for related in finding["related"]:
            source_excerpt(
                snapshot, related["source_id"], related["line_start"], related["line_end"]
            )
        for evidence in finding["evidence"]:
            if evidence["kind"] == "model-judgment":
                if finding["confidence"] == "high" or finding["disposition"] == "remove":
                    raise ValueError("Unsupported high-confidence model-only evidence")
                continue
            if (
                evidence["ref"] not in catalog
                or not evidence["quote"].strip()
                or evidence["quote"] not in catalog[evidence["ref"]]
                or evidence["kind"] not in kinds[evidence["ref"]]
            ):
                raise ValueError("Unverified finding evidence reference, kind, or quotation")
        if finding["category"] == "redundant-with-defaults" and not any(
            e["kind"] in {"native-default", "official-document", "repository-fact"}
            for e in finding["evidence"]
        ):
            raise ValueError("Default redundancy requires platform or concrete repository evidence")


def validate_dispositions(
    output: JsonObject, expected: list[str], snapshot: AuditSnapshot, knowledge: KnowledgeBundle
) -> None:
    dispositions = output.get("dispositions", [])
    actual = [d["directive_id"] for d in dispositions]
    if set(actual) != set(expected) or len(actual) != len(set(actual)):
        raise ValueError("Directive disposition assignment is incomplete or duplicated")
    catalog = evidence_catalog(snapshot, knowledge)
    directives = {d.directive_id: d for d in snapshot.directives}
    for item in dispositions:
        if not item["rationale"].strip() or not item["evidence_refs"]:
            raise ValueError("Disposition requires rationale and evidence")
        if any(ref not in catalog for ref in item["evidence_refs"]):
            raise ValueError("Unknown disposition evidence")
        if item["disposition"] in {"remove", "merge", "move", "revise"}:
            directive = directives[item["directive_id"]]
            if not any(
                finding["disposition"] in {"remove", "merge", "move", "revise"}
                and any(
                    location["source_id"] == directive.source_id
                    and location["line_start"] <= directive.line_start <= location["line_end"]
                    for location in [finding, *finding.get("related", [])]
                )
                for finding in output.get("findings", [])
            ):
                raise ValueError(
                    "Modifying disposition requires a corresponding reviewable finding"
                )


async def review_domains(
    snapshot: AuditSnapshot,
    runtime: CodexRuntime,
    options: RunOptions,
    knowledge: KnowledgeBundle,
    *,
    reviewer: Reviewer = run_review_job,
) -> list[DomainResult]:
    semaphore = asyncio.Semaphore(options.jobs)
    sources = {source.source_id: source for source in snapshot.inventory.sources}
    snapshot.observations = build_observations(snapshot)
    packages = build_review_packages(snapshot, snapshot.observations, knowledge)
    chunks_by_id = {chunk.chunk_id: chunk for chunk in snapshot.chunks}

    async def run(package):
        identifier = package.package_id
        domain = sources[package.source_id].domain
        chunks = [chunks_by_id[key] for key in package.chunk_ids]
        directives = [d for d in snapshot.directives if d.directive_id in package.directive_ids]
        payload = package_payload(package, snapshot, knowledge)
        result = DomainResult(identifier, domain, "failed", error="Review did not start")

        def validate_assignment(output: JsonObject) -> None:
            if output.get("evidence_requests"):
                return
            if any(
                finding["source_id"] != package.source_id for finding in output.get("findings", [])
            ):
                raise ValueError(
                    "Primary finding source_id must identify the assigned source; "
                    "use source_catalog IDs for related citations"
                )
            validate_findings(output.get("findings", []), snapshot, knowledge)
            validate_dispositions(output, [d.directive_id for d in directives], snapshot, knowledge)
            expected = [
                {"chunk_id": c.chunk_id, "payload_sha256": c.payload_sha256} for c in chunks
            ]
            validate_observation_decisions(output, package.observation_ids, snapshot, knowledge)
            if output.get("receipts") != expected:
                raise ValueError("Missing or foreign chunk receipt")

        async with semaphore:
            try:
                for round_number in range(3):
                    request = ReviewRequest(
                        f"{identifier}-e{round_number}",
                        domain,
                        prompt_for("specialist", payload),
                        validator=validate_assignment,
                    )
                    current = await reviewer(runtime, request)
                    current.assigned_chunks = package.chunk_ids
                    current.assigned_observations = package.observation_ids
                    current.assigned_directives = [d.directive_id for d in directives]
                    current.usage = {
                        key: current.usage.get(key, 0) + result.usage.get(key, 0)
                        for key in current.usage.keys() | result.usage.keys()
                    }
                    current.wall_seconds += result.wall_seconds
                    result = current
                    if result.status == "failed":
                        break
                    requests = result.output.get("evidence_requests", [])
                    if requests:
                        if round_number == 2 or len(requests) > 8:
                            result.status = "needs-evidence"
                            result.error = "Evidence request limit reached"
                            validate_findings(
                                result.output.get("findings", []), snapshot, knowledge
                            )
                            break
                        for evidence_request in requests:
                            try:
                                item = (
                                    read_document_evidence(knowledge, evidence_request["path"])
                                    if evidence_request["path"].startswith("doc:")
                                    else read_evidence(snapshot, evidence_request)
                                )
                                payload["evidence_history"].append(
                                    {"request": evidence_request, "result": item}
                                )
                            except (OSError, ValueError, UnicodeError) as exc:
                                payload["evidence_history"].append(
                                    {"request": evidence_request, "error": type(exc).__name__}
                                )
                        payload["repository_facts"] = snapshot.facts
                        payload["previous_assessment"] = result.output
                        continue
                    validate_findings(result.output.get("findings", []), snapshot, knowledge)
                    validate_assignment(result.output)
                    validate_dispositions(
                        result.output, result.assigned_directives, snapshot, knowledge
                    )
                    expected = [
                        {"chunk_id": c.chunk_id, "payload_sha256": c.payload_sha256} for c in chunks
                    ]
                    if result.output.get("receipts") != expected:
                        raise ValueError("Missing or foreign chunk receipt")
                    break
            except (OSError, ValueError) as exc:
                result.status = "failed"
                result.error = str(exc)
        result.assigned_chunks = package.chunk_ids
        result.assigned_observations = package.observation_ids
        result.assigned_directives = [d.directive_id for d in directives]
        return result

    tasks = [asyncio.create_task(run(package)) for package in packages]
    try:
        return list(await asyncio.gather(*tasks))
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
