"""Stable identities do not depend on source line drift or presentation."""

from agent_context_audit.baseline import assign_ids, compare_baseline
from agent_context_audit.models import Baseline, ReconciledAudit

from tests.test_contracts import finding


def test_line_drift_and_severity_do_not_change_identity():
    first = finding()
    second = dict(first, line_start=23, line_end=23, severity="high", title="Changed prose")
    assign_ids([first])
    assign_ids([second])
    assert first["id"] == second["id"]


def test_baseline_distinguishes_new_resolved_persisting_and_regressed():
    current = [finding(), dict(finding(), source_id="src-2"), dict(finding(), source_id="src-3")]
    previous = [finding(), dict(finding(), source_id="src-4")]
    assign_ids(current)
    assign_ids(previous)
    baseline = Baseline(previous, {current[2]["id"]: "resolved"})
    changes = compare_baseline(ReconciledAudit(current, []), baseline)
    assert changes.persisting == [current[0]["id"]]
    assert changes.new == [current[1]["id"]]
    assert changes.regressed == [current[2]["id"]]
    assert changes.resolved == [previous[1]["id"]]


def test_legacy_or_different_scope_does_not_manufacture_resolutions():
    item = finding()
    assign_ids([item])
    previous = Baseline([item])
    changes = compare_baseline(ReconciledAudit([], []), previous, scope_fingerprint="scope-new")
    assert changes.resolved == []
    assert changes.unassessed == [item["id"]]


def test_scope_identity_depends_on_effective_state_path_not_option_spelling(context_tree, tmp_path):
    from dataclasses import replace

    from agent_context_audit.baseline import scope_fingerprint
    from agent_context_audit.models import RunOptions

    target, roots = context_tree
    options = RunOptions(target, roots, tmp_path / "runs", tmp_path / "auth", tmp_path / "codex")
    equivalent = replace(
        options, roots=replace(roots, claude_state=roots.user_home / ".claude.json")
    )
    assert scope_fingerprint(options) == scope_fingerprint(equivalent)
