"""Modes share the same validated pipeline and schedulers have no install effects."""

import asyncio
import os
import plistlib
import shlex
import shutil
import sys
from pathlib import Path

import pytest
from agent_context_audit.cli import parse_options, target_for
from agent_context_audit.models import CalendarSpec, RuntimePaths, Target
from agent_context_audit.processes import run_process
from agent_context_audit.scheduling import render_schedule_example


def test_schedule_keeps_the_selected_state_file_when_serializing_default_roots(
    tmp_path, monkeypatch, capsys
):
    from agent_context_audit.cli import main

    home = tmp_path / "home"
    home.mkdir()
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    plugin = Path(__file__).resolve().parents[1] / "plugins/agent-context-audit"
    monkeypatch.setenv("ACA_PLUGIN_ROOT", str(plugin))
    assert main(["schedule-example", "--scheduler", "launchd", "--root", str(root)]) == 0
    data = plistlib.loads(capsys.readouterr().out.encode())
    arguments = data["ProgramArguments"]
    parsed = parse_options(arguments[arguments.index("audit") :])
    assert parsed.roots.claude_state == home / ".claude.json"


def test_explicit_root_uses_project_context_when_launched_elsewhere(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert target_for(root).cwd == root
    nested = root / "nested"
    nested.mkdir()
    monkeypatch.chdir(nested)
    assert target_for(root).cwd == nested


@pytest.mark.parametrize(
    "flag,value",
    [("--jobs", "0"), ("--challenge-rounds", "3"), ("--job-timeout", "0"), ("--timeout", "-1")],
)
def test_invalid_execution_limits_are_rejected(flag, value, tmp_path):
    with pytest.raises((ValueError, SystemExit)):
        parse_options(["audit", "--root", str(tmp_path), flag, value])


def test_schedule_plist_uses_argument_vector_and_absolute_paths(tmp_path):
    root = tmp_path / "repo with spaces"
    runtime = RuntimePaths(Path("/opt/bin/codex"), Path("/opt/bin/uv"), Path("/opt/plugin"))
    recipe = render_schedule_example(
        "launchd", Target(root, root), runtime, CalendarSpec(9, 15, "mon")
    )
    data = plistlib.loads(recipe.encode())
    arguments = data["ProgramArguments"]
    assert arguments[:6] == [
        "/usr/bin/env",
        "-u",
        "VIRTUAL_ENV",
        "-u",
        "CONDA_PREFIX",
        "/opt/bin/uv",
    ]
    assert arguments[arguments.index("--root") + 1] == str(root)
    assert data["StartCalendarInterval"] == {"Hour": 9, "Minute": 15, "Weekday": 1}
    assert not root.exists()


def test_systemd_escapes_percent_and_quotes(tmp_path):
    root = tmp_path / 'repo%with"quotes'
    runtime = RuntimePaths(Path("/opt/bin/codex"), Path("/opt/bin/uv"), Path("/opt/plugin"))
    recipe = render_schedule_example("systemd", Target(root, root), runtime, CalendarSpec())
    assert 'repo%%with\\"quotes' in recipe
    assert "SuccessExitStatus=1" in recipe


def test_scheduler_captures_runtime_environment_and_custom_audit_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("UNRELATED_SECRET", "never-copy-this-value")
    root = tmp_path / "repo"
    runtime = RuntimePaths(Path("/opt/native/codex"), Path("/opt/uv/uv"), Path("/opt/plugin"))
    recipe = render_schedule_example(
        "launchd",
        Target(root, root),
        runtime,
        CalendarSpec(),
        audit_arguments=[
            "--auth-home",
            str(tmp_path / "auth"),
            "--output-dir",
            str(tmp_path / "reports"),
        ],
    )
    data = plistlib.loads(recipe.encode())
    assert "/opt/uv" in data["EnvironmentVariables"]["PATH"].split(":")
    assert data["EnvironmentVariables"]["XDG_DATA_HOME"] == str(tmp_path / "data")
    assert data["EnvironmentVariables"]["XDG_STATE_HOME"] == str(tmp_path / "state")
    assert data["ProgramArguments"][data["ProgramArguments"].index("--auth-home") + 1] == str(
        tmp_path / "auth"
    )
    assert "UNRELATED_SECRET" not in recipe and "never-copy-this-value" not in recipe


def test_scheduler_bootstrap_does_not_execute_pythonpath_customization(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    injected = tmp_path / "injected"
    injected.mkdir()
    marker = tmp_path / "site-customization-ran"
    (injected / "sitecustomize.py").write_text(
        "from pathlib import Path\nPath(" + repr(str(marker)) + ").write_text('unexpected')\n"
    )
    uv = shutil.which("uv")
    assert uv
    plugin = Path(__file__).resolve().parents[1] / "plugins/agent-context-audit"
    runtime = RuntimePaths(Path("/usr/bin/false"), Path(uv), plugin)
    recipe = plistlib.loads(
        render_schedule_example("launchd", Target(root, root), runtime, CalendarSpec()).encode()
    )
    arguments = recipe["ProgramArguments"]
    position = arguments.index(str(plugin / "scripts/audit.py"))
    arguments = arguments[: position + 1] + ["--help"]
    environment = {
        key: os.environ[key] for key in ("HOME", "USER", "LANG", "TMPDIR") if key in os.environ
    }
    environment.update(recipe["EnvironmentVariables"])
    environment["PYTHONPATH"] = str(injected)
    observed = asyncio.run(run_process(arguments, cwd=root, env=environment, timeout=20))
    assert (
        b"Audit runtime is not prepared" in observed.stderr
        or observed.returncode == 0
        and b"Audit agent context" in observed.stdout
    )
    assert not marker.exists()


def test_scheduler_bootstrap_ignores_an_active_target_virtualenv(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    uv = shutil.which("uv")
    assert uv
    marker = tmp_path / "target-interpreter-ran"
    plugin = Path(__file__).resolve().parents[1] / "plugins/agent-context-audit"
    runtime = RuntimePaths(Path("/usr/bin/false"), Path(uv), plugin)
    recipe = plistlib.loads(
        render_schedule_example("launchd", Target(root, root), runtime, CalendarSpec()).encode()
    )
    environment = {
        key: os.environ[key] for key in ("HOME", "USER", "LANG", "TMPDIR") if key in os.environ
    }
    environment.update(recipe["EnvironmentVariables"])

    async def exercise():
        created = await run_process(
            [uv, "venv", "--python", sys.executable, str(root / ".venv")],
            cwd=root,
            env=environment,
            timeout=30,
        )
        assert created.returncode == 0, created.stderr.decode()
        executable = root / ".venv/bin/python"
        executable.unlink()
        executable.write_text(
            "#!/bin/sh\nprintf unexpected > "
            + shlex.quote(str(marker))
            + "\nexec "
            + shlex.quote(sys.executable)
            + ' "$@"\n'
        )
        executable.chmod(0o700)
        environment["VIRTUAL_ENV"] = str(root / ".venv")
        arguments = recipe["ProgramArguments"]
        position = arguments.index(str(plugin / "scripts/audit.py"))
        observed = await run_process(
            arguments[: position + 1] + ["--help"], cwd=root, env=environment, timeout=20
        )
        assert not marker.exists(), observed.stderr.decode()

    asyncio.run(exercise())
