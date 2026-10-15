"""Standard-library bootstrap; setup is the only dependency-installing operation."""

import asyncio
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import NoReturn


async def run_child(
    arguments: list[str],
    environment: dict[str, str],
    cwd: str | None = None,
    *,
    audit_protocol: bool = False,
) -> int:
    process = await asyncio.create_subprocess_exec(
        *arguments,
        env=environment,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE if audit_protocol else None,
    )
    try:
        if not audit_protocol:
            return await process.wait()
        if process.stdout is None:
            raise RuntimeError("Audit result transport unavailable")
        blocks = []
        size = 0
        while block := await process.stdout.read(65536):
            size += len(block)
            if size > 1024 * 1024:
                raise ValueError("Audit result transport exceeded its bound")
            blocks.append(block)
        code = await process.wait()
        output = b"".join(blocks).decode("utf-8", errors="replace")
        if code == 3:
            if output:
                print(output, end="")
            return 3
        try:
            result = json.loads(output)
            expected = {0: "complete-clean", 1: "complete-with-findings", 2: "partial"}
            if (
                code not in expected
                or not isinstance(result, dict)
                or result.get("status") != expected.get(code)
                or result.get("exit_code") != code
            ):
                raise ValueError("Invalid audit result envelope")
            for key, name in (("report_path", "report.md"), ("status_path", "status.json")):
                path = Path(result[key])
                if path.name != name or not path.is_file() or path.stat().st_size == 0:
                    raise ValueError("Audit artifact missing")
        except (ValueError, KeyError, TypeError, OSError):
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "exit_code": 3,
                        "error": "Audit process did not produce a valid report/status result",
                    }
                ),
                file=sys.stderr,
            )
            return 3
        print(output, end="")
        return code
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 5)
            except TimeoutError:
                process.kill()
                await process.wait()


def fail(message: str) -> NoReturn:
    print(json.dumps({"status": "failed", "exit_code": 3, "error": message}), file=sys.stderr)
    raise SystemExit(3)


def main() -> None:
    plugin = Path(__file__).resolve().parents[1]
    arguments = sys.argv[1:]
    uv = shutil.which("uv")
    if not uv:
        fail("uv is required; install it using the official uv instructions")
    uv = str(Path(uv).resolve())
    target = Path.cwd().resolve()
    if "--root" in arguments:
        index = arguments.index("--root")
        if index + 1 < len(arguments):
            target = Path(arguments[index + 1]).resolve()
    if arguments and arguments[0] == "audit" and Path(uv).is_relative_to(target):
        fail("uv must be installed outside the audited target")
    lock = plugin / "uv.lock"
    if not lock.is_file():
        fail("Packaged uv.lock is missing")
    digest = hashlib.sha256()
    files = [lock, plugin / "pyproject.toml"]
    for name in ("src", "scripts", "schemas", "references"):
        files.extend(
            path
            for path in (plugin / name).rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.name != ".DS_Store"
        )
    for path in sorted(files):
        digest.update(path.relative_to(plugin).as_posix().encode())
        digest.update(path.read_bytes())
    identity = digest.hexdigest()[:20]
    data = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    environment_path = data / "the-codex-factory/agent-context-audit/runtimes" / identity
    # Discard unrelated uv settings without changing the caller's environment.
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("UV_") and key not in {"VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME"}
    }
    environment["UV_PROJECT_ENVIRONMENT"] = str(environment_path)
    environment["ACA_PLUGIN_ROOT"] = str(plugin)
    environment["UV_NO_ENV_FILE"] = "1"
    if arguments and arguments[0] == "setup":
        with tempfile.TemporaryDirectory(prefix="aca-setup-") as temporary:
            returncode = asyncio.run(
                run_child(
                    [
                        uv,
                        "sync",
                        "--no-config",
                        "--project",
                        str(plugin),
                        "--frozen",
                        "--no-dev",
                        "--no-editable",
                        "--reinstall-package",
                        "agent-context-audit",
                        "--python",
                        sys.executable if sys.version_info[:3] == (3, 14, 8) else "3.14.8",
                    ],
                    environment,
                    cwd=temporary,
                )
            )
        if returncode:
            fail("Runtime setup failed; inspect the dependency-manager diagnostics")
    elif not (environment_path / "pyvenv.cfg").is_file():
        fail("Audit runtime is not prepared. Run this launcher with setup first.")
    command = [
        uv,
        "run",
        "--no-config",
        "--project",
        str(plugin),
        "--frozen",
        "--no-sync",
        "--offline",
        "--no-env-file",
        "python",
        "-I",
        "-m",
        "agent_context_audit",
        *arguments,
    ]
    protocol = bool(
        arguments and arguments[0] == "audit" and not {"--help", "-h"}.intersection(arguments)
    )
    raise SystemExit(asyncio.run(run_child(command, environment, audit_protocol=protocol)))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        fail(f"Bootstrap failure: {type(error).__name__}")
