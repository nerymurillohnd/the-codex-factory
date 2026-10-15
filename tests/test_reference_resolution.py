"""Reference traversal preserves filesystem semantics and terminates cycles."""

from agent_context_audit.discovery import discover_sources
from agent_context_audit.paths import resolve_local

from tests.conftest import put


def test_parent_after_symlink_uses_the_resolved_directory(tmp_path):
    (tmp_path / "real/branch").mkdir(parents=True)
    (tmp_path / "alias").symlink_to(tmp_path / "real/branch", target_is_directory=True)
    expected = put(tmp_path / "real/policy.md", "Expected policy.\n")
    put(tmp_path / "policy.md", "Unrelated policy.\n")
    assert resolve_local(tmp_path / "alias/../policy.md") == expected


def test_config_reference_cycles_terminate_across_logical_aliases(context_tree, monkeypatch):
    from agent_context_audit import discovery

    target, roots = context_tree
    put(roots.codex / "config.toml", '[agents.reviewer]\nconfig_file="roles/reviewer.toml"\n')
    put(roots.codex / "roles/reviewer.toml", '[agents.parent]\nconfig_file="../config.toml"\n')
    original = discovery._config
    reads = []

    def bounded(path, inventory):
        reads.append(path)
        assert len(reads) <= 20, "Configured-reference expansion did not terminate"
        return original(path, inventory)

    monkeypatch.setattr(discovery, "_config", bounded)
    inventory = discover_sources(target, roots)
    assert len(inventory.sources) <= 5
