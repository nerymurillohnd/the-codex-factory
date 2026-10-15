"""Profiles, worktrees and configured memory locations retain their host semantics."""

from agent_context_audit.discovery import discover_sources

from tests.conftest import put


def test_nested_profile_fallback_is_discovered_conditionally(context_tree):
    target, roots = context_tree
    put(
        target.root / "nested/.codex/config.toml",
        '[profiles.team]\nproject_doc_fallback_filenames=["TEAM.md"]\n',
    )
    custom = put(target.root / "nested/TEAM.md", "Apply the team policy.\n")
    inventory = discover_sources(target, roots)
    assert any(
        source.path == custom and source.load_mode == "conditional" for source in inventory.sources
    )


def test_worktree_memory_uses_shared_repository_identity(context_tree, tmp_path):
    target, roots = context_tree
    main = tmp_path / "main"
    metadata = main / ".git/worktrees/feature"
    put(metadata / "commondir", "../..\n")
    put(target.root / ".git", f"gitdir: {metadata}\n")
    import re

    slug = re.sub(r"[^a-zA-Z0-9]", "-", str(main))
    memory = put(roots.claude / "projects" / slug / "memory/MEMORY.md", "Shared worktree memory.\n")
    inventory = discover_sources(target, roots)
    assert any(source.path == memory for source in inventory.sources)


def test_relative_auto_memory_directory_is_not_silently_used(context_tree):
    target, roots = context_tree
    put(target.root / ".claude/settings.json", '{"autoMemoryDirectory":"relative/path"}')
    inventory = discover_sources(target, roots)
    assert any("autoMemoryDirectory" in gap for gap in inventory.gaps)
