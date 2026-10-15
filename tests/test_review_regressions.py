"""Reproductions from the independent final review; no real user data."""

import asyncio
import json
import shutil

import pytest
from agent_context_audit.discovery import discover_sources
from agent_context_audit.evidence import observe_git
from agent_context_audit.models import DomainResult, KnowledgeBundle
from agent_context_audit.privacy import redact
from agent_context_audit.processes import run_process
from agent_context_audit.reconcile import reconcile
from agent_context_audit.review import validate_findings
from agent_context_audit.snapshot import build_snapshot

from tests.conftest import put
from tests.test_contracts import finding
from tests.test_runtime import make_runtime


@pytest.mark.parametrize("filter_type", ["clean", "process"])
def test_git_observation_never_executes_repository_clean_filter(tmp_path, filter_type):
    root = tmp_path / "repo"
    root.mkdir()
    git = shutil.which("git")
    assert git

    async def exercise():
        env = {
            "PATH": "/usr/bin:/bin",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
        }
        for args in (
            ["init", str(root)],
            ["config", "user.name", "Synthetic Fixture"],
            ["config", "user.email", "fixture@example.invalid"],
        ):
            result = await run_process([git, *args], cwd=root, env=env, timeout=10)
            assert result.returncode == 0
        put(root / "test.txt", "before\n")
        put(root / ".gitattributes", "test.txt filter=evil\n")
        staged = await run_process(
            [git, "add", "test.txt", ".gitattributes"], cwd=root, env=env, timeout=10
        )
        assert staged.returncode == 0
        configured = await run_process(
            [git, "config", f"filter.evil.{filter_type}", f"touch '{tmp_path}/EXECUTED'; cat"],
            cwd=root,
            env=env,
            timeout=10,
        )
        assert configured.returncode == 0
        put(root / "test.txt", "AFTER!\n")
        await observe_git(root)
        assert not (tmp_path / "EXECUTED").exists()

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "suffix,text",
    [
        (".json", '{"mcpServers":{"x":{"args":["--api-key","OPAQUE_CANARY_CREDENTIAL"]}}}'),
        (".toml", '[mcp_servers.x]\nargs=["--api-key", "OPAQUE_CANARY_CREDENTIAL"]\n'),
        (".json", '{"hooks":{"command":"tool --password OPAQUE_CANARY_CREDENTIAL"}}'),
        (".json", '{"args":["--api-key=OPAQUE_CANARY_CREDENTIAL"]}'),
        (".toml", 'command="tool --password=OPAQUE_CANARY_CREDENTIAL"\n'),
    ],
)
def test_command_credentials_are_redacted(suffix, text):
    sanitized, _ = redact(text, suffix)
    assert "OPAQUE_CANARY_CREDENTIAL" not in sanitized


def test_expected_external_memory_is_a_coverage_gap(context_tree, tmp_path):
    target, roots = context_tree
    external = tmp_path / "external-memory"
    put(external / "MEMORY.md", "Required context.\n")
    put(target.root / ".claude/settings.json", json.dumps({"autoMemoryDirectory": str(external)}))
    inventory = discover_sources(target, roots)
    assert inventory.gaps


def test_configured_codex_agent_role_is_included(context_tree):
    target, roots = context_tree
    put(roots.codex / "config.toml", '[agents.reviewer]\nconfig_file="roles/reviewer.toml"\n')
    role = put(
        roots.codex / "roles/reviewer.toml", 'developer_instructions="Review changes carefully."\n'
    )
    inventory = discover_sources(target, roots)
    assert any(source.path == role and source.domain == "D3" for source in inventory.sources)


def test_kept_finding_cannot_disappear_from_reconciliation(context_tree, tmp_path):
    target, roots = context_tree
    put(target.root / "AGENTS.md", "Run npm absent\n")
    snapshot = build_snapshot(discover_sources(target, roots), target)
    item = finding()
    source_id = snapshot.inventory.sources[0].source_id
    item.update(
        source_id=source_id,
        evidence=[{"kind": "related-directive", "ref": source_id, "quote": "Run npm absent"}],
    )
    contribution = DomainResult("D1-0", "D1", "complete", {"findings": [item], "dispositions": []})

    async def dropped(runtime, request):
        return DomainResult(
            request.job_id,
            "reconciliation",
            "complete",
            {
                "findings": [],
                "dispositions": [
                    {
                        "directive_id": d.directive_id,
                        "disposition": "keep",
                        "rationale": "Unchanged",
                        "evidence_refs": [source_id],
                    }
                    for d in snapshot.directives
                ],
                "considered_job_ids": ["D1-0"],
                "decisions": [
                    {
                        "finding_key": "D1-0:finding:0",
                        "decision": "kept",
                        "rationale": "Valid finding",
                        "evidence_refs": [source_id],
                        "final_finding_indexes": [],
                    }
                ],
                "contested": [],
                "limitations": [],
            },
        )

    result = asyncio.run(
        reconcile(
            [contribution], snapshot, make_runtime(tmp_path), KnowledgeBundle({}), reviewer=dropped
        )
    )
    assert result.limitations
    assert result.findings


def test_repository_mechanism_can_support_default_redundancy(context_tree):
    target, roots = context_tree
    put(target.root / "AGENTS.md", "Run npm absent\n")
    snapshot = build_snapshot(discover_sources(target, roots), target)
    snapshot.facts.append(
        {"id": "repo:package.json:1", "text": "scripts already enforce formatting"}
    )
    item = finding()
    item.update(
        category="redundant-with-defaults", source_id=snapshot.inventory.sources[0].source_id
    )
    validate_findings([item], snapshot, KnowledgeBundle({}))


def test_failed_challenge_cancels_and_waits_for_siblings(context_tree, tmp_path):
    target, roots = context_tree
    put(target.root / "AGENTS.md", "Keep applicable policy.\n")
    snapshot = build_snapshot(discover_sources(target, roots), target)
    source = snapshot.inventory.sources[0].source_id
    results = [
        DomainResult(name, "D1", "complete", {"findings": [], "dispositions": []})
        for name in ("owner-a", "owner-b")
    ]
    cancelled = []

    async def reviewer(runtime, request):
        if request.schema_name == "reconciliation":
            return DomainResult(
                request.job_id,
                "reconciliation",
                "complete",
                {
                    "findings": [],
                    "decisions": [],
                    "considered_job_ids": [r.job_id for r in results],
                    "dispositions": [
                        {
                            "directive_id": d.directive_id,
                            "disposition": "keep",
                            "rationale": "Preserve policy",
                            "evidence_refs": [source],
                        }
                        for d in snapshot.directives
                    ],
                    "contested": [
                        {
                            "job_id": r.job_id,
                            "subject": "policy",
                            "reason": "Needs review",
                            "evidence_refs": [source],
                        }
                        for r in results
                    ],
                    "limitations": [],
                },
            )
        if request.job_id.endswith("owner-a"):
            await asyncio.sleep(0.01)
            return DomainResult(request.job_id, "D1", "failed", error="Synthetic failure")
        try:
            await asyncio.sleep(1)
            raise AssertionError("Sibling should not outlive failed challenge")
        except asyncio.CancelledError:
            cancelled.append(request.job_id)
            raise

    async def exercise():
        result = await reconcile(
            results, snapshot, make_runtime(tmp_path), KnowledgeBundle({}), reviewer=reviewer
        )
        assert result.limitations
        assert len(cancelled) == 1
        pending = [
            task
            for task in asyncio.all_tasks()
            if task is not asyncio.current_task() and not task.done()
        ]
        assert pending == []

    asyncio.run(exercise())
