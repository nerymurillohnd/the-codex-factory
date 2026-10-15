"""Private unique runs, inert Markdown, and atomic report/status publication."""

import hashlib
import html
import json
import os
import re
import stat
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from agent_context_audit.models import JsonObject, RunState, Target
from agent_context_audit.runtime import private_write
from agent_context_audit.semantic_context import target_digest


def repository_id(root: Path) -> str:
    return hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:24]


def private_directory(path: Path) -> Path:
    """Create with no-follow directory descriptors, including intermediate components."""
    path = Path(os.path.abspath(path))
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            with suppress(FileExistsError):
                os.mkdir(part, 0o700, dir_fd=descriptor)
            try:
                child = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
                )
            except OSError as exc:
                raise ValueError("Output path contains a symlink or non-directory") from exc
            os.close(descriptor)
            descriptor = child
        metadata = os.fstat(descriptor)
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
            raise ValueError("Output parent must be owned by the current user with mode 0700")
        return path
    finally:
        os.close(descriptor)


def create_run(target: Target, output_parent: Path, *, allow_in_target: bool = False) -> RunState:
    parent = output_parent.absolute()
    inside = parent.resolve().is_relative_to(target.root.resolve())
    if inside and not allow_in_target:
        raise ValueError("Report destination is inside the audited target")
    parent = private_directory(parent)
    repo_id = repository_id(target.root)
    repository_runs = private_directory(parent / repo_id)
    now = datetime.now(UTC)
    identifier = now.strftime("%Y%m%dT%H%M%S%fZ") + "-" + str(uuid.uuid4())
    directory = repository_runs / identifier
    directory.mkdir(mode=0o700)
    if inside:
        neutral = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
        neutral = neutral / "the-codex-factory/agent-context-audit/evidence" / repo_id / identifier
        if neutral.resolve().is_relative_to(target.root.resolve()):
            raise ValueError(
                "In-target reports require an external XDG_STATE_HOME for isolated review work"
            )
        work = private_directory(neutral)
    else:
        work = directory / "evidence"
        work.mkdir(mode=0o700)
    return RunState(directory, work, identifier, repo_id, now.isoformat())


def select_status(*, findings: int, gaps: list[str], fatal: bool) -> tuple[str, int]:
    if fatal:
        return "failed", 3
    if gaps:
        return "partial", 2
    return ("complete-with-findings", 1) if findings else ("complete-clean", 0)


def escape(value: object) -> str:
    """Never interpret source/model strings as Markdown, links, HTML, or app directives."""
    text = html.escape(str(value), quote=False)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"([\\`*_{}\[\]()#+.!|>@:~-])", r"\\\1", text)
    return text.replace("\r", "").replace("\n", "<br>")


def finding_review_state(finding: JsonObject, result: JsonObject) -> str:
    if result.get("schema_version") == "1.0":
        return "legacy-unverified"
    target, digest = "finding:" + finding["id"], target_digest(finding)
    assessments = [
        a
        for a in result.get("semantic_assessments", [])
        if (a["target_id"], a["target_digest"]) == (target, digest)
    ]
    decisions = [
        a
        for a in result.get("adjudications", [])
        if (a["target_id"], a["target_digest"]) == (target, digest)
    ]
    if not assessments:
        return "unverified"
    if not decisions:
        return "unadjudicated"
    if assessments[-1]["verdict"] == "unverifiable":
        return "unverifiable"
    if decisions[-1]["action"] == "upheld-over-objection":
        return "upheld-over-objection"
    return "reviewed"


def render(result: JsonObject) -> str:
    lines = [
        "# Agent Context Audit",
        "",
        f"**Status:** {escape(result['status'])}",
        "",
        f"Run: {escape(result['run_id'])}  ",
        f"Target: {escape(result['target'])}  ",
        f"Created: {escape(result['created_at'])}  ",
        f"Plugin: {escape(result['plugin_version'])}  ",
        f"Mode: {escape(result['entry_mode'])}",
        "",
        *(
            [
                "Report publication inside the target was explicitly requested. "
                "These private artifacts may change Git status "
                "after the recorded integrity checks; "
                "audited source files were not edited.",
                "",
                f"Isolated review evidence: {escape(result.get('evidence_path', 'unavailable'))}",
                "",
            ]
            if result.get("output_in_target")
            else []
        ),
        "## Executive summary",
        "",
        f"{len(result['findings'])} findings; {len(result['sources'])} sources; "
        f"{len(result['dispositions'])} directive dispositions.",
        "",
        "Recommendations are proposals. The audit does not apply source edits.",
        "",
        "## Coverage and integrity",
        "",
        "| Source ID | Path | Domain / scope / mode | Lines | State | SHA-256 |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for source in result["sources"]:
        lines.append(
            f"| {escape(source['source_id'])} | {escape(source['path'])} | "
            f"{escape(source['domain'])} / "
            f"{escape(source['scope'])} / {escape(source['load_mode'])} | "
            f"{source['line_count']} | {escape(source['status'])} | {source['sha256']} |"
        )
    for source in result["sources"]:
        if source["reason"] or source["redacted_lines"]:
            lines.append(
                f"\nSource note: {escape(source['reason'])}; redacted lines "
                f"{escape(source['redacted_lines'])}.\n"
            )
    lines += ["", "Validator outcomes:", ""]
    for name, value in result["validators"].items():
        lines.append(f"- {escape(name)}: {escape(value)}")
    lines += ["", "Excluded candidates:", ""]
    lines.extend(
        f"- {escape(item['path'])}: {escape(item['reason'])}" for item in result["exclusions"]
    )
    lines += [
        "",
        "## Automatic observations",
        "",
        "Observations are evidence candidates, not automatically confirmed defects.",
        "",
    ]
    decisions = {d["observation_id"]: d for d in result.get("observation_decisions", [])}
    for observation in result.get("observations", []):
        decision = decisions.get(observation["observation_id"])
        lines.append(f"- {escape(observation['observation_id'])}: {escape(observation['text'])}")
        lines.append(f"  - Decision: {escape(decision or 'Unresolved: no completed decision')}")
    lines += ["", "## Independent semantic verification", ""]
    for assessment in result.get("semantic_assessments", []):
        lines.append(f"- {escape(assessment)}")
    lines += [
        "",
        "## Final reconciler adjudication",
        "",
        "The reconciler owns the decision. An upheld objection is not consensus.",
        "",
    ]
    for decision in result.get("adjudications", []):
        lines.append(f"- {escape(decision)}")
    lines += ["", "## Findings and proposed remediation", ""]
    priority = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    findings = sorted(result["findings"], key=lambda f: (priority[f["severity"]], f["id"]))
    for finding in findings:
        review_state = finding_review_state(finding, result)
        lines += [
            f"### {escape(finding['id'])}: {escape(finding['title'])}",
            "",
            f"{escape(finding['category'])}; severity {escape(finding['severity'])}; "
            f"confidence {escape(finding['confidence'])}; {escape(finding['disposition'])}.",
            f"Semantic review: {escape(review_state)}. "
            + (
                "Inspect the retained counterevidence."
                if review_state == "upheld-over-objection"
                else "Provisional: review evidence is incomplete."
                if review_state != "reviewed"
                else "Independent assessment and final adjudication are recorded."
            ),
            "",
            f"Source: {escape(finding['source_id'])}, lines "
            f"{finding['line_start']}–{finding['line_end']}.",
            "",
            f"Excerpt: {escape(finding['excerpt'])}",
            "",
            f"Conflicts with: {escape(finding['conflicts_with'])}",
            "",
            f"Impact: {escape(', '.join(finding['impact']))}. {escape(finding['rationale'])}",
            "",
            f"Trade-offs: {escape(finding['tradeoffs'])}",
            "",
            "Evidence:",
            "",
        ]
        for evidence in finding["evidence"]:
            lines.append(
                f"- {escape(evidence['kind'])} / {escape(evidence['ref'])}: "
                f"{escape(evidence['quote'])}"
            )
        if finding["target_location"]:
            lines += ["", f"Proposed destination: {escape(finding['target_location'])}"]
        if finding["replacement"]:
            # Indented code prevents embedded fences/HTML from escaping into active report markup.
            lines += ["", "Proposed replacement:", ""]
            lines += ["    " + line for line in finding["replacement"].splitlines()]
        lines += ["", f"Related source dependencies: {escape(finding['related'])}", ""]
    lines += [
        "## Per-instruction dispositions",
        "",
        "| Directive | Disposition | Rationale | Evidence |",
        "| --- | --- | --- | --- |",
    ]
    for disposition in result["dispositions"]:
        lines.append(
            "| "
            + " | ".join(
                escape(disposition[key])
                for key in ("directive_id", "disposition", "rationale", "evidence_refs")
            )
            + " |"
        )
    lines += [
        "",
        "## Cross-domain reconciliation",
        "",
        f"Considered contributions: {escape(result['considered_job_ids'])}",
        "",
        f"Compared source pairs: {result['candidate_count']}",
        "",
    ]
    for decision in result["decisions"]:
        lines.append(f"- {escape(decision)}")
    lines += ["", "## Baseline changes", ""]
    lines.extend(
        f"- {escape(key)}: {escape(value)}" for key, value in result["baseline_changes"].items()
    )
    lines += ["", "## Limitations and disagreement", ""]
    lines.extend(f"- {escape(gap)}" for gap in result["limitations"])
    lines.extend(f"- Disagreement: {escape(item)}" for item in result["dissent"])
    lines += ["", "## Assessment notes", ""]
    lines.extend(f"- {escape(note)}" for note in result["notes"])
    lines += ["", "## Platform knowledge", ""]
    lines.extend(f"- {escape(item)}" for item in result["knowledge_observations"])
    lines += [
        "",
        "Knowledge claims are maintained paraphrases with source provenance in status.json.",
        "",
        "## Timing and usage",
        "",
        "| Job | State | Seconds | Usage |",
        "| --- | --- | ---: | --- |",
    ]
    for job in result["jobs"]:
        lines.append(
            f"| {escape(job['job_id'])} | {escape(job['status'])} | "
            f"{job['wall_seconds']:.3f} | {escape(job['usage'] or 'unavailable')} |"
        )
    lines += [
        "",
        f"Total elapsed seconds: {result['wall_seconds']:.3f}",
        "",
        "Consult the recorded validators for observed coverage and citation checks. "
        "Those checks cannot prove model attentiveness or semantic completeness.",
        "",
    ]
    return "\n".join(lines)


def write_artifacts(run: RunState, result: JsonObject) -> None:
    report = render(result)
    private_write(run.directory / ".report.tmp", report)
    os.replace(run.directory / ".report.tmp", run.directory / "report.md")
    if not (run.directory / "report.md").is_file():
        raise OSError("Primary report missing")
    private_write(
        run.directory / ".status.tmp", json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    )
    os.replace(run.directory / ".status.tmp", run.directory / "status.json")
