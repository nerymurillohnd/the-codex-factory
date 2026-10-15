"""An updated source package must not install an older cached wheel of the same version."""

import asyncio
import os
import shutil
import sys
import zipfile
from pathlib import Path

from agent_context_audit.processes import run_process

from tools.package_plugin import package_plugin


def test_setup_rebuilds_changed_resources_without_a_version_change(tmp_path):
    root = Path(__file__).resolve().parents[1]
    package = package_plugin(root, tmp_path / "archives")
    with zipfile.ZipFile(package) as archive:
        archive.extractall(tmp_path / "source")
    plugin = tmp_path / "source/agent-context-audit"
    resource = plugin / "references/specialist.md"
    original = resource.read_text()
    codex = tmp_path / "fake-codex"
    codex.write_text("#!/bin/sh\nexit 0\n")
    codex.chmod(0o700)
    data = tmp_path / "data"
    environment = dict(os.environ, XDG_DATA_HOME=str(data))
    uv = shutil.which("uv")
    assert uv
    command = [
        uv,
        "run",
        "--no-project",
        "--no-config",
        "--no-env-file",
        "--python",
        sys.executable,
        str(plugin / "scripts/audit.py"),
        "setup",
        "--auth-home",
        str(tmp_path / "auth"),
        "--codex-bin",
        str(codex),
    ]

    async def exercise():
        first = await run_process(command, cwd=tmp_path, env=environment, timeout=120)
        assert first.returncode == 0, first.stderr.decode()
        runtimes = data / "the-codex-factory/agent-context-audit/runtimes"
        before = set(runtimes.iterdir())
        assert len(before) == 1
        resource.write_text(original + "\nSynthetic changed resource for cache regression.\n")
        second = await run_process(command, cwd=tmp_path, env=environment, timeout=120)
        assert second.returncode == 0, second.stderr.decode()
        created = set(runtimes.iterdir()) - before
        assert len(created) == 1
        installed = (
            next(iter(created))
            / "lib/python3.14/site-packages/agent_context_audit/data/references/specialist.md"
        )
        assert installed.read_text() == resource.read_text()

    asyncio.run(exercise())
