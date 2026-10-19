"""Project Records must ship complete, reproducible and isolated from maintainer files."""

import asyncio
import hashlib
import json
import os
import re
import shutil
import zipfile
from pathlib import Path

import pytest
import yaml
from agent_context_audit.processes import run_process

from tools.package_plugin import package_plugin
from tools.validate_marketplace import validate_marketplace

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/project-records"


def fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(PLUGIN, root / "plugins/project-records")
    return root


def test_project_records_archive_is_complete_and_reproducible(tmp_path: Path) -> None:
    first = package_plugin(ROOT, tmp_path / "first", plugin_name="project-records")
    second = package_plugin(ROOT, tmp_path / "second", plugin_name="project-records")
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
        for relative in [
            "plugin.json",
            ".codex-plugin/plugin.json",
            "README.md",
            "LICENSE",
            "CHANGELOG.md",
            "skills/project-records/SKILL.md",
            "skills/project-records/references/decision-records.md",
            "skills/project-records/references/debt-ledger-open.md",
            "skills/project-records/references/debt-ledger-resolve.md",
            "skills/project-records/assets/ADR_YYYY-MM-DD_decision-slug.md",
            "skills/project-records/assets/pending-debt.md",
            "skills/project-records/assets/resolved-debt.md",
        ]:
            assert "project-records/" + relative in names
        assert len(names) == 12
        inventory = (first.parent / "PACKAGE-CONTENTS.txt").read_text().splitlines()
        assert {"project-records/" + name for name in inventory} == names
        digest = hashlib.sha256(first.read_bytes()).hexdigest()
        assert (first.parent / "SHA256SUMS").read_text() == f"{digest}  {first.name}\n"


@pytest.mark.parametrize(
    "relative",
    [
        ".env",
        "auth.json",
        "tests/leak.md",
        "skills/project-records/notes.md",
        "skills/project-records/references/unreviewed.md",
    ],
)
def test_project_records_refuses_unreviewed_files(tmp_path: Path, relative: str) -> None:
    root = fixture_root(tmp_path)
    path = root / "plugins/project-records" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("synthetic excluded evidence")
    with pytest.raises(ValueError, match="Unexpected|Private"):
        package_plugin(root, tmp_path / "output", plugin_name="project-records")


def test_project_records_refuses_missing_required_file(tmp_path: Path) -> None:
    root = fixture_root(tmp_path)
    (root / "plugins/project-records/LICENSE").unlink()
    with pytest.raises(ValueError, match="Missing"):
        package_plugin(root, tmp_path / "output", plugin_name="project-records")


def test_project_records_refuses_symlink_without_reading_it(tmp_path: Path) -> None:
    root = fixture_root(tmp_path)
    path = root / "plugins/project-records/skills/project-records/assets/pending-debt.md"
    path.unlink()
    path.symlink_to(tmp_path / "does-not-exist")
    with pytest.raises(ValueError, match="symlink"):
        package_plugin(root, tmp_path / "output", plugin_name="project-records")


def test_package_refuses_symlinked_plugins_directory(tmp_path: Path) -> None:
    root = fixture_root(tmp_path)
    (root / "plugins").rename(tmp_path / "outside-plugins")
    (root / "plugins").symlink_to(tmp_path / "outside-plugins", target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        package_plugin(root, tmp_path / "output", plugin_name="project-records")


def test_unknown_plugin_cannot_escape_package_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown plugin"):
        package_plugin(ROOT, tmp_path, plugin_name="../outside")


def test_package_refuses_output_with_another_archive(tmp_path: Path) -> None:
    first = package_plugin(ROOT, tmp_path)
    checksum = (tmp_path / "SHA256SUMS").read_bytes()
    inventory = (tmp_path / "PACKAGE-CONTENTS.txt").read_bytes()
    with pytest.raises(ValueError, match="distinct output directory"):
        package_plugin(ROOT, tmp_path, plugin_name="project-records")
    assert first.is_file()
    assert (tmp_path / "SHA256SUMS").read_bytes() == checksum
    assert (tmp_path / "PACKAGE-CONTENTS.txt").read_bytes() == inventory
    assert not (tmp_path / "project-records-0.1.0.zip").exists()


def test_project_records_catalog_and_manifests_align() -> None:
    assert validate_marketplace(ROOT) == []
    catalog = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
    assert any(entry["name"] == "project-records" for entry in catalog["plugins"])
    canonical = json.loads((PLUGIN / "plugin.json").read_text())
    native = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text())
    for field in ["name", "version", "description", "author", "license", "repository"]:
        assert canonical[field] == native[field]
    assert canonical["extensions"]["com.openai"]["interface"] == native["interface"]
    assert len(native["interface"]["shortDescription"]) <= 30
    assert canonical["name"] == "project-records"
    assert native["skills"] == "./skills/"
    assert canonical["version"] in (PLUGIN / "CHANGELOG.md").read_text()
    assert "plugins/project-records/README.md" in (ROOT / "README.md").read_text()


def test_project_records_references_and_templates_are_self_contained() -> None:
    skill = PLUGIN / "skills/project-records"
    entry = (skill / "SKILL.md").read_text()
    metadata = yaml.safe_load(entry.split("---", 2)[1])
    assert metadata["name"] == skill.name
    assert metadata["description"].startswith("Use when")
    for path in skill.rglob("*.md"):
        text = path.read_text()
        assert "CLAUDE_SKILL_DIR" not in text
        assert "AskUserQuestion" not in text
        for relative in re.findall(r"\]\(([^)]+)\)", text):
            if "://" not in relative:
                target = (path.parent / relative.split("#", 1)[0]).resolve()
                assert target.is_relative_to(PLUGIN)
                assert target.is_file(), (path, relative)


def test_native_install_discovers_project_records(tmp_path: Path, native_codex: Path) -> None:
    """Inspect actual installed ZIP discovery without credentials or a model."""
    archive_path = package_plugin(ROOT, tmp_path / "archive", plugin_name="project-records")
    marketplace = tmp_path / "marketplace"
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(marketplace / "plugins")
    catalog = marketplace / ".agents/plugins/marketplace.json"
    catalog.parent.mkdir(parents=True)
    catalog.write_text(
        json.dumps(
            {
                "name": "records-fixture",
                "plugins": [
                    {
                        "name": "project-records",
                        "source": {"source": "local", "path": "./plugins/project-records"},
                        "category": "Productivity",
                        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                    }
                ],
            }
        )
    )
    home = tmp_path / "codex-home"
    home.mkdir()
    environment = dict(os.environ, CODEX_HOME=str(home))

    async def exercise() -> None:
        for args in [
            ["plugin", "marketplace", "add", str(marketplace)],
            ["plugin", "add", "project-records@records-fixture"],
        ]:
            result = await run_process(
                [str(native_codex), *args], cwd=marketplace, env=environment, timeout=30
            )
            assert result.returncode == 0, result.stderr.decode()
        process = await asyncio.create_subprocess_exec(
            str(native_codex),
            "app-server",
            cwd=marketplace,
            env=environment,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        async def request(ident: int, method: str, params: dict) -> dict:
            assert process.stdin is not None and process.stdout is not None
            process.stdin.write(
                (json.dumps({"id": ident, "method": method, "params": params}) + "\n").encode()
            )
            await process.stdin.drain()
            while True:
                line = await asyncio.wait_for(process.stdout.readline(), timeout=20)
                assert line, "Native app server closed before replying"
                response = json.loads(line)
                if response.get("id") == ident:
                    return response

        try:
            await request(
                0,
                "initialize",
                {
                    "clientInfo": {"name": "records_fixture", "version": "0.1.0"},
                    "capabilities": {"experimentalApi": True},
                },
            )
            skills = await request(1, "skills/list", {"cwds": [str(marketplace)]})
            assert any(
                skill["name"] == "project-records:project-records" and skill["enabled"]
                for entry in skills["result"]["data"]
                for skill in entry["skills"]
            ), skills
        finally:
            if process.stdin is not None:
                process.stdin.close()
            try:
                await asyncio.wait_for(process.wait(), timeout=2)
            except TimeoutError:
                process.kill()
                await process.wait()

    asyncio.run(exercise())
