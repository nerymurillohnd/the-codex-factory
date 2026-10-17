"""A bad catalog must not silently omit or misidentify a plugin."""

import json
from pathlib import Path

from tools.validate_marketplace import validate_marketplace


def write_catalog(root: Path, source: str = "./plugins/example") -> Path:
    plugin = root / "plugins/example"
    skill = plugin / "skills/example/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: example\ndescription: Test workflow.\n---\nTest.\n")
    manifest = {
        "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
        "name": "example",
        "version": "0.1.0",
        "description": "Test plugin",
        "author": {"name": "Example"},
        "license": "MIT",
    }
    (plugin / "plugin.json").write_text(json.dumps(manifest))
    overlay = plugin / ".codex-plugin/plugin.json"
    overlay.parent.mkdir()
    overlay.write_text(json.dumps({k: v for k, v in manifest.items() if k != "$schema"}))
    catalog = root / ".agents/plugins/marketplace.json"
    catalog.parent.mkdir(parents=True)
    catalog.write_text(
        json.dumps(
            {
                "name": "example",
                "plugins": [
                    {
                        "name": "example",
                        "source": {"source": "local", "path": source},
                        "category": "Productivity",
                        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                    }
                ],
            }
        )
    )
    return plugin


def test_catalog_rejects_escape(tmp_path: Path) -> None:
    write_catalog(tmp_path, "../outside")
    assert any("escape" in issue for issue in validate_marketplace(tmp_path))


def test_catalog_rejects_missing_skill(tmp_path: Path) -> None:
    plugin = write_catalog(tmp_path)
    (plugin / "skills/example/SKILL.md").unlink()
    assert any("skill" in issue for issue in validate_marketplace(tmp_path))


def test_overlay_identity_matches_canonical(tmp_path: Path) -> None:
    plugin = write_catalog(tmp_path)
    overlay = plugin / ".codex-plugin/plugin.json"
    overlay.write_text('{"name":"different","version":"0.2.0"}')
    assert any("overlay" in issue for issue in validate_marketplace(tmp_path))


def test_valid_catalog(tmp_path: Path) -> None:
    write_catalog(tmp_path)
    assert validate_marketplace(tmp_path) == []


def test_native_hook_plugin_uses_inactive_portable_metadata(tmp_path: Path) -> None:
    plugin = write_catalog(tmp_path)
    (plugin / "metadata").mkdir()
    (plugin / "plugin.json").rename(plugin / "metadata/plugin.json")
    assert validate_marketplace(tmp_path) == []


def test_catalog_checks_declared_skill_directory(tmp_path: Path) -> None:
    plugin = write_catalog(tmp_path)
    overlay = plugin / ".codex-plugin/plugin.json"
    value = json.loads(overlay.read_text())
    value["skills"] = "./../../outside"
    overlay.write_text(json.dumps(value))
    assert any("skills" in issue for issue in validate_marketplace(tmp_path))


def test_catalog_rejects_declared_empty_skill_directory(tmp_path: Path) -> None:
    plugin = write_catalog(tmp_path)
    (plugin / "empty-skills").mkdir()
    overlay = plugin / ".codex-plugin/plugin.json"
    value = json.loads(overlay.read_text())
    value["skills"] = "./empty-skills/"
    overlay.write_text(json.dumps(value))
    assert any("no skill" in issue for issue in validate_marketplace(tmp_path))


def test_catalog_checks_hook_overlay_and_containment(tmp_path: Path) -> None:
    plugin = write_catalog(tmp_path)
    manifest = plugin / "plugin.json"
    value = json.loads(manifest.read_text())
    value["extensions"] = {"com.openai": {"hooks": "./../outside.json"}}
    manifest.write_text(json.dumps(value))
    errors = validate_marketplace(tmp_path)
    assert any("overlay hooks" in issue for issue in errors)
    assert any("hooks" in issue and "escape" in issue for issue in errors)


def test_catalog_checks_hook_script_exists(tmp_path: Path) -> None:
    plugin = write_catalog(tmp_path)
    hooks = plugin / "hooks/hooks.json"
    hooks.parent.mkdir()
    hooks.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": 'bash "${PLUGIN_ROOT}/hooks/missing.sh"',
                                }
                            ]
                        }
                    ]
                }
            }
        )
    )
    assert any("missing.sh" in issue for issue in validate_marketplace(tmp_path))
