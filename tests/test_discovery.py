"""Inventory must respect actual source provenance and host boundaries."""

from agent_context_audit.discovery import discover_sources

from tests.conftest import put


def test_link_lines_remain_correct_after_fenced_code_and_crlf(context_tree):
    target, roots = context_tree
    tick = chr(96)
    text = (
        tick * 3
        + "sh\r\n"
        + "echo an intentionally long code example\r\n"
        + tick * 3
        + "\r\n\r\n[Policy](missing.md)\r\n"
    )
    put(target.root / "AGENTS.md", text)
    inventory = discover_sources(target, roots)
    source = next(s for s in inventory.sources if s.path == target.root / "AGENTS.md")
    assert source.references[0].line == 5


def test_invalid_fallback_metadata_is_accounted_for_without_crashing(context_tree):
    target, roots = context_tree
    put(roots.codex / "config.toml", "project_doc_fallback_filenames = true\n")
    inventory = discover_sources(target, roots)
    assert any("fallback" in gap.lower() for gap in inventory.gaps)
    assert any(source.path == roots.codex / "config.toml" for source in inventory.sources)


def test_inventory_includes_user_nested_and_workflow_sources(context_tree) -> None:
    target, roots = context_tree
    paths = [
        put(roots.codex / "AGENTS.md", "Use signed commits.\n"),
        put(target.root / "AGENTS.md", "Run tests.\n"),
        put(target.root / "src/AGENTS.md", "Keep module invariants.\n"),
        put(roots.claude / "CLAUDE.md", "Global user policy.\n"),
        put(target.root / ".claude/workflows/review.js", "export const meta = {name:'review'};\n"),
        put(target.root / ".claude/commands/review.md", "Review the current changes.\n"),
        put(roots.claude / "agent-memory/reviewer/MEMORY.md", "Remember review preferences.\n"),
    ]
    inventory = discover_sources(target, roots)
    assert set(paths) <= {source.path for source in inventory.sources}


def test_override_does_not_hide_the_shadowed_source(context_tree) -> None:
    target, roots = context_tree
    put(target.root / "AGENTS.override.md", "Active override.\n")
    normal = put(target.root / "AGENTS.md", "Shadowed guidance.\n")
    record = next((s for s in discover_sources(target, roots).sources if s.path == normal), None)
    assert record is not None
    assert record.load_mode == "dead"
    assert "override" in record.reason


def test_plugin_alias_is_excluded(context_tree) -> None:
    target, roots = context_tree
    supplied = put(roots.codex / "plugins/cache/vendor/AGENTS.md", "Plugin-provided policy.\n")
    alias = target.root / ".claude/rules/vendor.md"
    alias.parent.mkdir(parents=True)
    alias.symlink_to(supplied)
    inventory = discover_sources(target, roots)
    assert not any(s.canonical_path == supplied for s in inventory.sources)
    assert any(entry["reason"] == "plugin-provided" for entry in inventory.exclusions)


def test_skill_packages_and_secret_imports_are_excluded(context_tree) -> None:
    target, roots = context_tree
    put(target.root / ".agents/skills/deploy/SKILL.md", "Excluded skill.\n")
    secret = put(target.root / ".env", "API_KEY=SYNTHETIC_SECRET\n")
    put(target.root / "CLAUDE.md", "Read @.env and @missing.md\n")
    inventory = discover_sources(target, roots)
    assert all(s.canonical_path != secret for s in inventory.sources)
    assert any(r.state == "blocked-secret" for s in inventory.sources for r in s.references)
    assert any(r.state == "missing" for s in inventory.sources for r in s.references)


def test_claude_imports_follow_depth_and_ignore_code(context_tree) -> None:
    target, roots = context_tree
    tick = chr(96)
    put(
        target.root / "CLAUDE.md",
        f"@one.md\n{tick}@ignored.md{tick}\n{tick * 3}\n@also-ignored.md\n{tick * 3}\n",
    )
    put(target.root / "one.md", "@two.md\n")
    put(target.root / "two.md", "Nested instructions.\n")
    inventory = discover_sources(target, roots)
    assert {s.path.name for s in inventory.sources} >= {"CLAUDE.md", "one.md", "two.md"}
    refs = [r.target for s in inventory.sources for r in s.references]
    assert "ignored.md" not in refs and "also-ignored.md" not in refs


def test_missing_claude_is_a_clean_empty_domain(context_tree) -> None:
    target, roots = context_tree
    put(target.root / "AGENTS.md", "Codex instructions only.\n")
    inventory = discover_sources(target, roots)
    assert inventory.sources
    assert not any(s.domain == "D2" and s.path.name == "CLAUDE.md" for s in inventory.sources)


def test_regular_directory_named_skills_keeps_its_instructions(context_tree) -> None:
    target, roots = context_tree
    path = put(target.root / "src/skills/AGENTS.md", "Rules for the skills domain of this app.\n")
    assert any(s.path == path for s in discover_sources(target, roots).sources)


def test_project_config_registers_fallback_filename(context_tree) -> None:
    target, roots = context_tree
    put(target.root / ".codex/config.toml", 'project_doc_fallback_filenames = ["TEAM.md"]\n')
    path = put(target.root / "TEAM.md", "Fallback project guidance.\n")
    assert any(s.path == path for s in discover_sources(target, roots).sources)


def test_discovery_does_not_walk_session_transcripts(context_tree, monkeypatch) -> None:
    import os

    target, roots = context_tree
    put(roots.codex / "sessions/deep/file.jsonl", "Unrelated history.\n")
    visited = []
    original = os.scandir

    def track(path):
        visited.append(str(path))
        return original(path)

    monkeypatch.setattr(os, "scandir", track)
    discover_sources(target, roots)
    assert not any("/sessions" in p for p in visited)


def test_referenced_hook_script_is_read_as_data(context_tree) -> None:
    import json

    target, roots = context_tree
    script = put(target.root / ".codex/hooks/start.py", "raise RuntimeError('MUST_NOT_RUN')\n")
    put(
        roots.codex / "hooks.json",
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {"hooks": [{"type": "command", "command": "python .codex/hooks/start.py"}]}
                    ]
                }
            }
        ),
    )
    inventory = discover_sources(target, roots)
    assert any(s.path == script and s.domain == "D4" for s in inventory.sources)


def test_unreadable_source_remains_in_inventory(context_tree) -> None:
    target, roots = context_tree
    path = target.root / "AGENTS.md"
    path.write_bytes(b"\xff\xfeinvalid")
    inventory = discover_sources(target, roots)
    assert any(s.path == path and s.status == "unreadable" for s in inventory.sources)
    assert inventory.gaps


def test_global_claude_config_is_accounted_for(context_tree) -> None:
    target, roots = context_tree
    path = put(roots.user_home / ".claude.json", '{"mcpServers":{}}')
    assert any(s.path == path and s.domain == "D4" for s in discover_sources(target, roots).sources)
