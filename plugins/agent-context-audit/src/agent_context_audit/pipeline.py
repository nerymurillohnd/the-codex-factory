"""One pipeline for direct, interactive, and scheduled invocations."""

import asyncio
import json
import time
from dataclasses import asdict
from pathlib import Path

from jsonschema import ValidationError

from agent_context_audit import __version__
from agent_context_audit.baseline import compare_baseline, scope_fingerprint
from agent_context_audit.contracts import validate_output
from agent_context_audit.discovery import discover_sources
from agent_context_audit.evidence import (
    check_references,
    collect_repository_facts,
    compare_evidence,
    observe_git,
)
from agent_context_audit.isolation import (
    inspect_claude_version,
    inspect_runtime,
    prepare_runtime,
    probe_isolation,
    runtime_authenticated,
    validate_effective_config,
)
from agent_context_audit.knowledge import load_knowledge
from agent_context_audit.models import (
    AuditSnapshot,
    Baseline,
    DomainResult,
    Inventory,
    KnowledgeBundle,
    ReconciledAudit,
    RunOptions,
    RunOutcome,
)
from agent_context_audit.paths import read_source_bytes
from agent_context_audit.privacy import redact
from agent_context_audit.reconcile import reconcile, topic_candidates
from agent_context_audit.report import create_run, select_status, write_artifacts
from agent_context_audit.review import review_domains
from agent_context_audit.snapshot import build_snapshot, compare_sources, validate_coverage
from agent_context_audit.verification import complete_semantic_review, verification_targets


async def audit(options: RunOptions) -> RunOutcome:
    started = time.monotonic()
    run = create_run(
        options.target, options.output_dir, allow_in_target=options.allow_output_in_target
    )
    snapshot = AuditSnapshot(Inventory(options.target, options.roots), {}, [], [])
    knowledge = KnowledgeBundle({})
    results: list[DomainResult] = []
    merged = ReconciledAudit([], [])
    gaps: list[str] = []
    validators = {}
    baseline = None
    fatal = False
    git_after = {}
    runtime = None
    claude_version = None
    scope_id = scope_fingerprint(options)
    try:
        async with asyncio.timeout(options.timeout):
            if options.baseline:
                previous = json.loads(read_source_bytes(options.baseline))
                validate_output(previous, "run")
                if previous["repository_id"] != run.repository_id:
                    raise ValueError("Baseline belongs to a different target repository")
                if previous["status"] not in {"complete-clean", "complete-with-findings"}:
                    raise ValueError("A partial/failed audit cannot establish resolved findings")
                baseline = Baseline(
                    previous["findings"],
                    previous["baseline_history"],
                    previous.get("scope_fingerprint"),
                )
            runtime = await prepare_runtime(options, run)
            capabilities = await probe_isolation(runtime)
            validators["isolation"] = asdict(capabilities)
            if not capabilities.verified:
                raise ValueError(
                    "Required isolation preflight failed: " + "; ".join(capabilities.limitations)
                )
            if not await runtime_authenticated(runtime):
                raise ValueError(
                    "Dedicated audit profile is not authenticated; complete native Codex login"
                )
            inventory = discover_sources(options.target, options.roots)
            snapshot = build_snapshot(inventory, options.target, run)
            for name, path in (("Codex", options.roots.codex), ("user", options.roots.user_home)):
                if not path.is_dir():
                    gaps.append(f"Expected {name} source root is unavailable")
            claude_present = any("claude" in s.hosts for s in inventory.sources)
            knowledge = await load_knowledge(
                runtime.version, offline=options.offline, claude_present=claude_present
            )
            if claude_present:
                observation = await inspect_claude_version(runtime, options.target.root)
                validators["claude_version_probe"] = observation
                if observation["verified"]:
                    claude_version = observation["version"]
                    if claude_version != knowledge.data["versions"]["claude"]:
                        gaps.append(
                            f"Claude {claude_version} is outside the verified knowledge baseline"
                        )
                else:
                    gaps.append(observation["reason"])
            snapshot.initial_git = await observe_git(options.target.root)
            if not snapshot.initial_git.get("available"):
                gaps.append("Initial Git state could not be verified")
            collect_repository_facts(snapshot)
            await check_references(snapshot, options.allow_domains)
            if options.entry_mode in {"interactive", "app-scheduled"}:
                gaps.append(
                    "Interactive parent may already have loaded target instructions or hooks; "
                    "parent non-interference is unverified"
                )
            results = await review_domains(snapshot, runtime, options, knowledge)
            coverage = validate_coverage(snapshot, results)
            validators["coverage"] = asdict(coverage)
            gaps.extend(coverage.errors)
            if snapshot.chunks:
                merged = await reconcile(
                    results,
                    snapshot,
                    runtime,
                    knowledge,
                    challenge_rounds=options.challenge_rounds,
                    jobs=options.jobs,
                )
                if not any(result.status in {"complete", "needs-evidence"} for result in results):
                    fatal = True
                merged = await complete_semantic_review(
                    merged, snapshot, runtime, options, knowledge
                )
                expected = {
                    (t["target_id"], t["target_digest"]) for t in verification_targets(merged)
                }
                assessed = {(a["target_id"], a["target_digest"]) for a in merged.assessments}
                adjudicated = {(a["target_id"], a["target_digest"]) for a in merged.adjudications}
                validators["semantic_verification"] = expected <= assessed
                validators["final_adjudication"] = expected <= adjudicated
                for decision in merged.observation_decisions:
                    if decision["outcome"] == "unresolved":
                        gaps.append(
                            "Unresolved observation evidence: " + decision["observation_id"]
                        )
            current = discover_sources(options.target, options.roots)
            gaps.extend(compare_sources(snapshot, current))
            gaps.extend(current.gaps)
            gaps.extend(compare_evidence(snapshot))
            git_after = await observe_git(options.target.root)
            validators["git_preserved"] = snapshot.initial_git == git_after
            if run.directory.is_relative_to(options.target.root):
                validators["git_preservation_scope"] = (
                    "Before publication of explicitly requested in-target reports"
                )
            if snapshot.initial_git != git_after:
                gaps.append("Git state changed during audit; causation is unverified")
            effective = await inspect_runtime(runtime)
            profile = json.loads(
                next(
                    v.split("=", 1)[1]
                    for v in runtime.config
                    if v.startswith("default_permissions=")
                )
            )
            final_issues = validate_effective_config(
                effective["configuration"], effective["layers"], profile
            )
            if any(
                entry.get("errors") or any(s.get("enabled") for s in entry.get("skills", []))
                for entry in effective["skills"]
            ):
                final_issues.append("Skill surface changed during audit")
            validators["final_isolation"] = not final_issues
            gaps.extend(final_issues)
    except asyncio.CancelledError:
        fatal = True
        gaps.append("Audit cancelled; owned reviewer processes were stopped")
    except (OSError, ValueError, RuntimeError, TimeoutError, ValidationError) as exc:
        fatal = True
        message, _ = redact(
            "Structured output failed schema validation"
            if isinstance(exc, ValidationError)
            else str(exc),
            ".log",
        )
        gaps.append(f"Audit failed: {message}")
    gaps.extend(snapshot.inventory.gaps)
    gaps.extend(knowledge.gaps)
    gaps.extend(merged.limitations)
    for result in results:
        gaps.extend(result.output.get("limitations", []))
        if result.error:
            gaps.append(f"{result.job_id}: {result.error}")
    gaps = sorted(set(gaps))
    status, code = select_status(findings=len(merged.findings), gaps=gaps, fatal=fatal)
    changes = compare_baseline(merged, baseline, scope_fingerprint=scope_id)
    # Incomplete audits cannot establish that an old finding was resolved.
    if code >= 2:
        changes.unassessed = sorted(set(changes.unassessed + changes.resolved))
        changes.resolved = []
    history = dict(baseline.history) if baseline else {}
    history.update({f["id"]: "persisting" for f in merged.findings})
    history.update(dict.fromkeys(changes.resolved, "resolved"))
    result = {
        "schema_version": "1.1",
        "scope_fingerprint": scope_id,
        "observations": [asdict(o) for o in snapshot.observations],
        "observation_decisions": merged.observation_decisions,
        "semantic_assessments": merged.assessments,
        "adjudications": merged.adjudications,
        "repository_evidence": [
            {key: value for key, value in fact.items() if key != "text"} for fact in snapshot.facts
        ],
        "plugin_version": __version__,
        "run_id": run.run_id,
        "repository_id": run.repository_id,
        "created_at": run.created_at,
        "target": str(options.target.root),
        "cwd": str(options.target.cwd),
        "invocation_cwd": str(Path.cwd()),
        "entry_mode": options.entry_mode,
        "status": status,
        "exit_code": code,
        "report_path": str(run.directory / "report.md"),
        "evidence_path": str(run.work_directory),
        "output_in_target": run.directory.is_relative_to(options.target.root),
        "sources": [asdict(s) for s in snapshot.inventory.sources],
        "exclusions": snapshot.inventory.exclusions,
        "chunks": [{k: v for k, v in asdict(c).items() if k != "text"} for c in snapshot.chunks],
        "findings": merged.findings,
        "dispositions": merged.dispositions,
        "considered_job_ids": merged.considered_job_ids,
        "decisions": merged.decisions,
        "candidate_count": len(topic_candidates(snapshot)),
        "dissent": merged.dissent,
        "limitations": gaps,
        "notes": sorted(
            set(merged.notes + [note for job in results for note in job.output.get("notes", [])])
        ),
        "validators": validators,
        "baseline_changes": asdict(changes),
        "baseline_history": history,
        "knowledge": knowledge.data,
        "knowledge_observations": knowledge.observations,
        "git_before": snapshot.initial_git,
        "git_after": git_after,
        "model_requested": options.model,
        "effort_requested": options.effort,
        "model_resolved": "unavailable",
        "codex_version": runtime.version if runtime else None,
        "claude_version": claude_version,
        "jobs": [
            {key: value for key, value in asdict(job).items() if key != "output"}
            for job in [*results, *merged.jobs]
        ],
        "wall_seconds": time.monotonic() - started,
    }
    # Convert Paths before schema validation; no credentials or raw source bodies enter status.
    result = json.loads(json.dumps(result, default=str))
    validate_output(result, "run")
    write_artifacts(run, result)
    return RunOutcome(status, code, run.directory / "report.md", result)
