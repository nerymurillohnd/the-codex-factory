"""An unsafe configuration must fail before any real source reaches a model."""

from agent_context_audit.isolation import validate_effective_config


def test_isolation_rejects_enabled_hooks() -> None:
    issues = validate_effective_config({"features": {"hooks": True}}, [], "audit")
    assert any("hooks" in issue for issue in issues)


def test_isolation_rejects_foreign_project_configuration() -> None:
    layers = [{"name": {"type": "project", "dotCodexFolder": "/other/.codex"}, "config": {}}]
    assert any("project" in issue for issue in validate_effective_config({}, layers, "audit"))


def test_isolation_rejects_enabled_mcp_server() -> None:
    config = {"mcp_servers": {"external": {"enabled": True}}}
    assert any("MCP" in issue for issue in validate_effective_config(config, [], "audit"))
