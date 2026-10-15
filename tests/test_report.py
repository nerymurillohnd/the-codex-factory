"""Report integrity, private destinations, and honest exit semantics."""

import pytest
from agent_context_audit.models import Target
from agent_context_audit.report import create_run, escape, select_status, write_artifacts


def test_exit_precedence():
    assert select_status(findings=0, gaps=[], fatal=False) == ("complete-clean", 0)
    assert select_status(findings=2, gaps=[], fatal=False) == ("complete-with-findings", 1)
    assert select_status(findings=2, gaps=["missing shard"], fatal=False) == ("partial", 2)
    assert select_status(findings=2, gaps=["missing shard"], fatal=True) == ("failed", 3)


def test_report_does_not_label_a_stale_assessment_as_verified():
    from agent_context_audit.baseline import assign_ids
    from agent_context_audit.report import finding_review_state
    from agent_context_audit.semantic_context import target_digest

    from tests.test_contracts import finding

    item = finding()
    assign_ids([item])
    target = "finding:" + item["id"]
    digest = target_digest(item)
    result = {
        "schema_version": "1.1",
        "semantic_assessments": [
            {"target_id": target, "target_digest": digest, "verdict": "challenged"}
        ],
        "adjudications": [
            {"target_id": target, "target_digest": digest, "action": "upheld-over-objection"}
        ],
    }
    assert finding_review_state(item, result) == "upheld-over-objection"
    item["replacement"] = "Different unreviewed obligation."
    assert finding_review_state(item, result) == "unverified"


def test_run_directories_are_unique_private_and_external(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    target = Target(root, root)
    first = create_run(target, tmp_path / "state")
    second = create_run(target, tmp_path / "state")
    assert first.directory != second.directory
    assert first.directory.stat().st_mode & 0o777 == 0o700
    with pytest.raises(ValueError, match="target"):
        create_run(target, root / "audits")


def test_symlinked_output_parent_is_refused(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (tmp_path / "real").mkdir()
    (tmp_path / "alias").symlink_to(tmp_path / "real")
    with pytest.raises(ValueError, match="symlink"):
        create_run(Target(root, root), tmp_path / "alias" / "reports")


def test_explicit_in_target_reports_keep_review_work_outside_target(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "external-state"))
    run = create_run(Target(root, root), root / "audits", allow_in_target=True)
    assert run.directory.is_relative_to(root)
    assert not run.work_directory.is_relative_to(root)
    assert run.work_directory.is_dir()


def test_untrusted_markdown_cannot_render_images_or_html():
    output = escape('<img src="https://attacker.test"> ![x](https://attacker.test) @all\n# Heading')
    assert "<img" not in output
    assert "![" not in output
    assert "\n# Heading" not in output


def test_missing_report_is_not_published_as_success(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    run = create_run(Target(root, root), tmp_path / "state")

    def fail(*args, **kwargs):
        raise OSError("synthetic disk failure")

    monkeypatch.setattr("agent_context_audit.report.render", fail)
    with pytest.raises(OSError):
        write_artifacts(run, {"status": "complete-clean"})
    assert not (run.directory / "status.json").exists()
