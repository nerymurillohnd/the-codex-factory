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
