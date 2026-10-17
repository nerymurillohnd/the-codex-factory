"""Run the packaged Bash hook against synthetic session directories."""

import asyncio
import json
import os
import shutil
from pathlib import Path

import pytest
from agent_context_audit.processes import ProcessResult, run_process

from tools.package_plugin import package_plugin

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/session-handoff"
HOOK = PLUGIN / "hooks/session-bootstrap.sh"


def run_hook(project: Path) -> ProcessResult:
    bash = shutil.which("bash")
    assert bash
    return asyncio.run(
        run_process(
            [bash, str(HOOK)],
            cwd=project,
            env=dict(os.environ),
            input_data=b'{"source":"startup","cwd":"ignored-untrusted-payload"}',
            timeout=10,
        )
    )


def test_hook_is_silent_without_handoffs(tmp_path: Path) -> None:
    result = run_hook(tmp_path)
    assert result.returncode == 0
    assert result.stdout == b""


def test_hook_ignores_unrelated_names_and_empty_store(tmp_path: Path) -> None:
    store = tmp_path / ".codex/session-handoff"
    store.mkdir(parents=True)
    (store / "notes.md").write_text("Not a handoff")
    (store / "２０２６-10-16-1230.md").write_text("Not ASCII")
    assert run_hook(tmp_path).stdout == b""


def test_hook_returns_fixed_context_without_promoting_record_contents(tmp_path: Path) -> None:
    project = tmp_path / "project [x] * \\ with spaces"
    store = project / ".codex/session-handoff"
    store.mkdir(parents=True)
    (store / "2026-10-15-1230.md").write_text("OLD_PRIVATE_CANARY")
    (store / "2026-10-16-1230.md").write_text("INSTRUCTION_INJECTION_CANARY")
    result = run_hook(project)
    assert result.returncode == 0
    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert output["hookEventName"] == "SessionStart"
    assert "Read" in output["additionalContext"]
    assert "initial request" in output["additionalContext"]
    assert "non-interactive" in output["additionalContext"]
    assert b"CANARY" not in result.stdout
    assert str(project).encode() not in result.stdout


@pytest.mark.parametrize("component", [".codex", ".codex/session-handoff"])
def test_hook_refuses_symlinked_storage(tmp_path: Path, component: str) -> None:
    target = tmp_path / "outside"
    target.mkdir()
    link = tmp_path / component
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target, target_is_directory=True)
    result = run_hook(tmp_path)
    assert result.returncode != 0
    assert b"symlink" in result.stderr


def test_hook_refuses_symlinked_record(tmp_path: Path) -> None:
    store = tmp_path / ".codex/session-handoff"
    store.mkdir(parents=True)
    (store / "2026-10-16-1200.md").symlink_to(tmp_path / "missing")
    result = run_hook(tmp_path)
    assert result.returncode != 0
    assert b"symlink" in result.stderr


def test_hook_reports_unreadable_store(tmp_path: Path) -> None:
    store = tmp_path / ".codex/session-handoff"
    store.mkdir(parents=True)
    store.chmod(0)
    try:
        if os.access(store, os.R_OK):
            pytest.skip("Current user can bypass permission bits")
        result = run_hook(tmp_path)
        assert result.returncode != 0
        assert b"read" in result.stderr
    finally:
        store.chmod(0o700)


def test_hook_uses_session_directory_not_parent_repository(tmp_path: Path) -> None:
    store = tmp_path / ".codex/session-handoff"
    store.mkdir(parents=True)
    (store / "2026-10-16-1200.md").write_text("Parent session")
    child = tmp_path / "child"
    child.mkdir()
    assert run_hook(child).stdout == b""


def test_hook_declares_only_startup_and_clear() -> None:
    hooks = json.loads((PLUGIN / "hooks/hooks.json").read_text())
    assert set(hooks["hooks"]) == {"SessionStart"}
    group = hooks["hooks"]["SessionStart"][0]
    assert group["matcher"] == "^(startup|clear)$"
    assert group["hooks"][0]["command"] == 'bash "${PLUGIN_ROOT}/hooks/session-bootstrap.sh"'


def test_startup_protocol_requires_validation_before_inheriting_record(tmp_path: Path) -> None:
    store = tmp_path / ".codex/session-handoff"
    store.mkdir(parents=True)
    (store / "9999-99-99-9999.md").write_text("Malformed newest candidate")
    context = json.loads(run_hook(tmp_path).stdout)["hookSpecificOutput"]["additionalContext"]
    assert "calendar" in context
    assert "Project" in context
    assert "metadata" in context
    assert "sections" in context
    assert "stop recovery" in context


def test_documented_save_is_exclusive_even_for_concurrent_writers(tmp_path: Path) -> None:
    reference = PLUGIN / "skills/write-handoff/references/save.md"
    command = reference.read_text().split("```bash\n")[1].split("\n```")[0]
    destination = tmp_path / "2026-10-16-1230.md"
    bash = shutil.which("bash")
    assert bash
    environment = dict(os.environ, HANDOFF_FILE=str(destination))

    async def exercise() -> None:
        results = await asyncio.gather(
            *(
                run_process(
                    [bash, "-c", command],
                    cwd=tmp_path,
                    env=environment,
                    input_data=content,
                    timeout=10,
                )
                for content in (b"first approved draft\n", b"second approved draft\n")
            )
        )
        assert sorted(result.returncode == 0 for result in results) == [False, True]
        original = destination.read_bytes()
        assert original in (b"first approved draft\n", b"second approved draft\n")
        repeated = await run_process(
            [bash, "-c", command],
            cwd=tmp_path,
            env=environment,
            input_data=b"replacement\n",
            timeout=10,
        )
        assert repeated.returncode != 0
        assert destination.read_bytes() == original

    asyncio.run(exercise())


def test_native_install_discovers_skill_and_untrusted_hook(tmp_path: Path, native_codex) -> None:
    """Exercise the real manifest loader without granting trust or calling a model."""
    import zipfile

    archive_path = package_plugin(ROOT, tmp_path / "archives", plugin_name="session-handoff")
    marketplace = tmp_path / "marketplace"
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(marketplace / "plugins")
    catalog = marketplace / ".agents/plugins/marketplace.json"
    catalog.parent.mkdir(parents=True)
    catalog.write_text(
        json.dumps(
            {
                "name": "handoff-fixture",
                "plugins": [
                    {
                        "name": "session-handoff",
                        "source": {"source": "local", "path": "./plugins/session-handoff"},
                        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                        "category": "Productivity",
                    }
                ],
            }
        )
    )
    home = tmp_path / "codex-home"
    home.mkdir()
    environment = dict(os.environ, CODEX_HOME=str(home))

    async def exercise() -> None:
        for arguments in (
            ["plugin", "marketplace", "add", str(marketplace)],
            ["plugin", "add", "session-handoff@handoff-fixture"],
        ):
            result = await run_process(
                [str(native_codex), *arguments], cwd=marketplace, env=environment, timeout=30
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
                line = await asyncio.wait_for(process.stdout.readline(), timeout=15)
                assert line, "Native app server closed before replying"
                response = json.loads(line)
                if response.get("id") == ident:
                    return response

        try:
            await request(
                0,
                "initialize",
                {
                    "clientInfo": {"name": "handoff_fixture", "version": "0.1.0"},
                    "capabilities": {"experimentalApi": True},
                },
            )
            skills = await request(1, "skills/list", {"cwds": [str(marketplace)]})
            assert any(
                skill["name"] == "session-handoff:write-handoff" and skill["enabled"]
                for entry in skills["result"]["data"]
                for skill in entry["skills"]
            )
            hooks = await request(2, "hooks/list", {"cwds": [str(marketplace)]})
            plugin_hooks = [
                hook
                for entry in hooks["result"]["data"]
                for hook in entry["hooks"]
                if hook.get("pluginId") == "session-handoff@handoff-fixture"
            ]
            assert len(plugin_hooks) == 1
            assert plugin_hooks[0]["trustStatus"] == "untrusted"
            assert plugin_hooks[0]["matcher"] == "^(startup|clear)$"
        finally:
            if process.stdin is not None:
                process.stdin.close()
            try:
                await asyncio.wait_for(process.wait(), timeout=2)
            except TimeoutError:
                process.kill()
                await process.wait()

    asyncio.run(exercise())
