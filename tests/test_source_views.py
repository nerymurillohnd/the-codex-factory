"""Application state must not widen the target or expose unrelated data."""

import json
from dataclasses import replace

from agent_context_audit.discovery import discover_sources
from agent_context_audit.snapshot import build_snapshot

from tests.conftest import put


def test_unrelated_state_changes_do_not_change_selected_view_digest(context_tree):
    from agent_context_audit.source_views import build_claude_state_view

    target, _ = context_tree
    before = '{"personal":"small","mcpServers":{"x":{"command":"server"}}}'
    after = '{"personal":"much-longer-unrelated-state","mcpServers":{"x":{"command":"server"}}}'
    assert (
        build_claude_state_view(before, target.root).digest
        == build_claude_state_view(after, target.root).digest
    )
    moved = before.replace(',"mcpServers"', ',\n"mcpServers"')
    assert (
        build_claude_state_view(before, target.root).digest
        != build_claude_state_view(moved, target.root).digest
    )


def test_claude_state_excludes_other_projects_and_helpers(context_tree):
    target, roots = context_tree
    state = roots.user_home / ".claude.json"
    original = json.dumps(
        {
            "mcpServers": {"global": {"command": "global-server"}},
            "projects": {
                str(target.root): {"mcpServers": {"local": {"command": "target-server"}}},
                "/unrelated": {"mcpServers": {"other": {"command": "OTHER_PRIVATE_CANARY.py"}}},
            },
            "personal": "PERSONAL_PRIVATE_CANARY",
        },
        indent=2,
    )
    put(state, original)
    inventory = discover_sources(target, roots)
    snapshot = build_snapshot(inventory, target)
    text = "\n".join(snapshot.texts.values())
    assert "target-server" in text and "global-server" in text
    assert '"projects"' in text and str(target.root) in text
    assert "PRIVATE_CANARY" not in text
    assert "/unrelated" not in text
    assert not any("OTHER_PRIVATE_CANARY" in str(s.references) for s in inventory.sources)
    selected = next(s for s in inventory.sources if s.path == state)
    source_text = snapshot.texts[selected.source_id]
    assert source_text.splitlines().index(
        '      "command": "global-server"'
    ) == original.splitlines().index('      "command": "global-server"')


def test_relocated_claude_state_is_included(context_tree):
    target, roots = context_tree
    custom = roots.user_home / "custom-claude"
    custom.mkdir()
    roots = replace(roots, claude=custom)
    put(custom / ".claude.json", '{"mcpServers":{"x":{"command":"custom-state-server"}}}')
    snapshot = build_snapshot(discover_sources(target, roots), target)
    assert any("custom-state-server" in text for text in snapshot.texts.values())


def test_repository_evidence_cannot_bypass_a_filtered_state_snapshot(context_tree):
    from agent_context_audit.evidence import read_evidence

    target, roots = context_tree
    custom = target.root / "state"
    custom.mkdir()
    roots = replace(roots, claude=custom)
    put(
        custom / ".claude.json",
        '{"mcpServers":{"x":{"command":"server"}},"personal":"PRIVATE_APP_CANARY"}',
    )
    snapshot = build_snapshot(discover_sources(target, roots), target)
    result = read_evidence(snapshot, {"path": "state/.claude.json", "line_start": 1, "line_end": 1})
    assert "PRIVATE_APP_CANARY" not in result["text"]
    assert "server" in result["text"]


def test_secret_command_arguments_cannot_become_helper_references(context_tree):
    from dataclasses import asdict

    target, roots = context_tree
    put(
        target.root / ".mcp.json",
        '{"mcpServers":{"x":{"command":"server","args":["--api-key","SYNTHETIC_PRIVATE_VALUE.py"]}}}',
    )
    inventory = discover_sources(target, roots)
    snapshot = build_snapshot(inventory, target)
    encoded = json.dumps([asdict(s) for s in snapshot.inventory.sources], default=str)
    assert "SYNTHETIC_PRIVATE_VALUE" not in encoded
    assert not any("SYNTHETIC_PRIVATE_VALUE" in gap for gap in inventory.gaps)


def test_explicit_default_directory_override_selects_its_own_state(context_tree):
    from agent_context_audit.source_views import resolve_claude_state_path

    _, roots = context_tree
    assert (
        resolve_claude_state_path(roots.user_home, roots.claude, overridden=True)
        == roots.claude / ".claude.json"
    )
    assert (
        resolve_claude_state_path(roots.user_home, roots.claude, overridden=False)
        == roots.user_home / ".claude.json"
    )
