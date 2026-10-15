"""The release archive is deterministic and excludes maintainer material."""

import hashlib
import shutil
import zipfile
from pathlib import Path

import pytest

from tools.package_plugin import package_plugin


def test_package_is_reproducible_and_has_no_private_or_dev_files(tmp_path):
    root = Path(__file__).resolve().parents[1]
    first = package_plugin(root, tmp_path / "first")
    second = package_plugin(root, tmp_path / "second")
    assert (
        hashlib.sha256(first.read_bytes()).digest() == hashlib.sha256(second.read_bytes()).digest()
    )
    with zipfile.ZipFile(first) as archive:
        names = archive.namelist()
        assert "agent-context-audit/scripts/audit.py" in names
        assert "agent-context-audit/LICENSE" in names
        assert all(
            not any(
                part in name.split("/")
                for part in ["tests", ".superpowers", ".venv", "__pycache__"]
            )
            for name in names
        )


def test_package_refuses_source_symlinks(tmp_path):
    root = tmp_path / "repo"
    plugin = root / "plugins/agent-context-audit"
    plugin.mkdir(parents=True)
    (plugin / "plugin.json").symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError, match="symlink"):
        package_plugin(root, tmp_path / "out")


def test_generated_finder_metadata_is_not_a_product_input(tmp_path):
    source = Path(__file__).resolve().parents[1] / "plugins/agent-context-audit"
    root = tmp_path / "repo"
    shutil.copytree(source, root / "plugins/agent-context-audit")
    metadata = root / "plugins/agent-context-audit/.DS_Store"
    metadata.write_text("synthetic Finder metadata")
    package = package_plugin(root, tmp_path / "out")
    with zipfile.ZipFile(package) as archive:
        assert not any(name.endswith(".DS_Store") for name in archive.namelist())
    (root / "plugins/agent-context-audit/.env").write_text("SYNTHETIC_PRIVATE_VALUE=canary\n")
    with pytest.raises(ValueError):
        package_plugin(root, tmp_path / "blocked")
