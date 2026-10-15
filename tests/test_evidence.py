"""Additional evidence requests cannot widen filesystem scope."""

import asyncio
import os
import shutil

import pytest
from agent_context_audit.discovery import discover_sources
from agent_context_audit.evidence import read_evidence
from agent_context_audit.snapshot import build_snapshot

from tests.conftest import put


def test_tracked_secret_store_prevents_worktree_content_inspection(tmp_path, monkeypatch):
    from agent_context_audit.evidence import observe_git
    from agent_context_audit.processes import run_process

    root = tmp_path / "repo"
    root.mkdir()
    git = shutil.which("git")
    assert git
    commands = []

    async def observed(args, **kwargs):
        commands.append(args)
        return await run_process(args, **kwargs)

    async def exercise():
        environment = {
            key: os.environ[key] for key in ("PATH", "HOME", "LANG") if key in os.environ
        }
        created = await run_process(
            [git, "init", "--quiet", str(root)], cwd=root, env=environment, timeout=10
        )
        assert created.returncode == 0
        put(root / ".env", "SYNTHETIC_FIXTURE_SECRET=private\n")
        staged = await run_process([git, "add", ".env"], cwd=root, env=environment, timeout=10)
        assert staged.returncode == 0
        monkeypatch.setattr("agent_context_audit.evidence.run_process", observed)
        result = await observe_git(root)
        assert not result["available"]
        assert not any("status" in command for command in commands)

    asyncio.run(exercise())


def test_evidence_rejects_secret_and_outside_paths(context_tree) -> None:
    target, roots = context_tree
    snapshot = build_snapshot(discover_sources(target, roots), target)
    for name in [".env", "../outside.txt", "/etc/passwd"]:
        with pytest.raises(ValueError):
            read_evidence(
                snapshot, {"path": name, "line_start": 1, "line_end": 10, "reason": "test"}
            )


def test_evidence_returns_cited_lines_and_hash(context_tree) -> None:
    target, roots = context_tree
    put(target.root / "package.json", '{\n  "scripts": {"test":"test-runner"}\n}\n')
    snapshot = build_snapshot(discover_sources(target, roots), target)
    evidence = read_evidence(
        snapshot,
        {"path": "package.json", "line_start": 2, "line_end": 2, "reason": "verify command"},
    )
    assert evidence["id"] == "repo:package.json:2-2"
    assert evidence["text"] == '  "scripts": {"test":"test-runner"}'
    assert evidence["sha256"]
