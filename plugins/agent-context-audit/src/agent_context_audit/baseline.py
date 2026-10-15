"""Deterministic finding identities and explicit historical states."""

import hashlib
import json
import unicodedata
from dataclasses import asdict

from agent_context_audit.models import (
    Baseline,
    BaselineChanges,
    JsonObject,
    ReconciledAudit,
    RunOptions,
)
from agent_context_audit.source_views import claude_state_path


def scope_fingerprint(options: RunOptions) -> str:
    roots = asdict(options.roots)
    roots["claude_state"] = str(claude_state_path(options.roots))
    roots["additional"] = sorted({str(path) for path in options.roots.additional})
    value = {
        "policy": "agent-context-scope-1.1",
        "target": str(options.target.root),
        "roots": roots,
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def assign_ids(findings: list[JsonObject]) -> None:
    for finding in findings:
        identity = [
            finding["source_id"],
            finding["category"],
            normalized(finding["excerpt"]),
            sorted({related["source_id"] for related in finding["related"]}),
        ]
        finding["id"] = "ACA-" + hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:20]


def compare_baseline(
    current: ReconciledAudit, baseline: Baseline | None, *, scope_fingerprint: str | None = None
) -> BaselineChanges:
    ids = {f["id"] for f in current.findings}
    previous = {f["id"] for f in baseline.findings} if baseline else set()
    history = baseline.history if baseline else {}
    regressed = {
        identifier for identifier in ids - previous if history.get(identifier) == "resolved"
    }
    changes = BaselineChanges(
        sorted(ids - previous - regressed),
        sorted(previous - ids),
        sorted(ids & previous),
        sorted(regressed),
    )
    if (
        baseline
        and scope_fingerprint is not None
        and baseline.scope_fingerprint != scope_fingerprint
    ):
        changes.unassessed = changes.resolved
        changes.resolved = []
        changes.new = sorted(set(changes.new + changes.regressed))
        changes.regressed = []
    return changes
