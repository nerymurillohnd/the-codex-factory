"""Explicit setup, one audit pipeline, latest artifacts, and schedule recipes."""

import argparse
import asyncio
import json
import os
import shlex
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from jsonschema import ValidationError

from agent_context_audit.contracts import validate_output
from agent_context_audit.models import CalendarSpec, RunOptions, RuntimePaths, SourceRoots, Target
from agent_context_audit.paths import read_source_bytes, resolve_local
from agent_context_audit.pipeline import audit
from agent_context_audit.report import private_directory, repository_id
from agent_context_audit.scheduling import render_schedule_example
from agent_context_audit.source_views import resolve_claude_state_path


def data_root() -> Path:
    return (
        Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
        / "the-codex-factory/agent-context-audit"
    )


def state_root() -> Path:
    return (
        Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
        / "the-codex-factory/agent-context-audit/runs"
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="Audit agent context without changing audited sources."
    )
    commands = root.add_subparsers(dest="command", required=True)
    setup = commands.add_parser(
        "setup", help="Prepare native authentication home and print login command"
    )
    setup.add_argument("--auth-home", type=Path, default=data_root() / "auth")
    setup.add_argument("--codex-bin", type=Path)
    for name in ("audit", "latest", "schedule-example"):
        command = commands.add_parser(name)
        command.add_argument("--root", type=Path)
        command.add_argument("--output-dir", type=Path, default=state_root())
        command.add_argument("--codex-bin", type=Path)
        if name != "latest":
            command.add_argument(
                "--allow-output-in-target",
                action="store_true",
                help=(
                    "Explicitly allow private reports inside the target; review work stays external"
                ),
            )
            command.add_argument(
                "--source-codex-home",
                type=Path,
                default=Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))),
            )
            command.add_argument(
                "--source-claude-home",
                type=Path,
                default=Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))),
            )
            command.add_argument("--source-user-home", type=Path, default=Path.home())
            command.add_argument("--source-claude-state", type=Path)
            command.add_argument("--allow-source-root", type=Path, action="append", default=[])
            command.add_argument("--auth-home", type=Path, default=data_root() / "auth")
        if name == "schedule-example":
            command.add_argument(
                "--scheduler", choices=["app", "launchd", "systemd"], required=True
            )
            command.add_argument("--hour", type=int, default=9)
            command.add_argument("--minute", type=int, default=0)
            command.add_argument(
                "--weekday", choices=["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
            )
            continue
        if name == "latest":
            command.add_argument("--completed-only", action="store_true")
            continue
        command.add_argument("--baseline", type=Path)
        command.add_argument("--model")
        command.add_argument(
            "--effort", choices=["minimal", "low", "medium", "high", "xhigh", "max", "ultra"]
        )
        command.add_argument("--jobs", type=int, default=4)
        command.add_argument("--challenge-rounds", type=int, default=1)
        command.add_argument("--job-timeout", type=int, default=600)
        command.add_argument("--timeout", type=int, default=1800)
        command.add_argument("--offline", action="store_true")
        command.add_argument("--allow-domain", action="append", default=[])
        command.add_argument(
            "--entry-mode",
            choices=["headless", "interactive", "scheduled", "app-scheduled"],
            default="headless",
        )
    return root


def target_for(path: Path | None) -> Target:
    cwd = resolve_local(Path.cwd())
    root = (
        resolve_local(path)
        if path
        else next((parent for parent in (cwd, *cwd.parents) if (parent / ".git").exists()), cwd)
    )
    if not root.is_dir():
        raise ValueError("Target root is not an accessible directory")
    return Target(root, cwd if cwd.is_relative_to(root) else root)


def executable(path: Path | None, name: str, target: Path | None = None) -> Path:
    found = str(path) if path else shutil.which(name)
    if not found:
        raise ValueError(f"Required executable is unavailable: {name}")
    resolved = resolve_local(Path(found))
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise ValueError(f"Executable is unavailable: {name}")
    if target and resolved.is_relative_to(target):
        raise ValueError(f"Executable must be outside the audited target: {name}")
    return resolved


def parse_options(argv: Sequence[str]) -> RunOptions:
    args = parser().parse_args(argv)
    if args.command != "audit":
        raise ValueError("Expected audit command")
    if not 1 <= args.jobs <= 16 or not 0 <= args.challenge_rounds <= 2:
        raise ValueError("jobs must be 1–16; challenge rounds must be 0–2")
    if args.job_timeout < 1 or args.timeout < 1:
        raise ValueError("Timeouts must be positive")
    target = target_for(args.root)
    roots = SourceRoots(
        resolve_local(args.source_codex_home),
        resolve_local(args.source_claude_home),
        resolve_local(args.source_user_home),
        tuple(resolve_local(p) for p in args.allow_source_root),
        resolve_local(args.source_claude_state)
        if args.source_claude_state
        else resolve_claude_state_path(
            resolve_local(args.source_user_home),
            resolve_local(args.source_claude_home),
            overridden=bool(os.environ.get("CLAUDE_CONFIG_DIR"))
            or any(arg.split("=", 1)[0] == "--source-claude-home" for arg in argv),
        ),
    )
    auth = args.auth_home.absolute()
    if auth.resolve() in {roots.codex, roots.claude} or auth.resolve().is_relative_to(target.root):
        raise ValueError(
            "Use a dedicated authentication home outside audited source homes and target"
        )
    return RunOptions(
        target,
        roots,
        args.output_dir.absolute(),
        auth,
        executable(args.codex_bin, "codex", target.root),
        args.jobs,
        args.model,
        args.effort,
        args.challenge_rounds,
        args.job_timeout,
        args.timeout,
        args.offline,
        tuple(args.allow_domain),
        args.baseline,
        args.entry_mode,
        args.allow_output_in_target,
    )


def latest(target: Target, output_parent: Path, completed_only: bool = False) -> dict:
    directory = resolve_local(output_parent / repository_id(target.root))
    for status in sorted(directory.glob("*/status.json"), reverse=True):
        try:
            result = json.loads(read_source_bytes(status))
            validate_output(result, "run")
            if result["repository_id"] != repository_id(target.root):
                continue
            if completed_only and result["exit_code"] >= 2:
                continue
            report = resolve_local(Path(result["report_path"]))
            if report.parent != status.parent or not report.is_file():
                continue
            return {
                "status": result["status"],
                "created_at": result["created_at"],
                "exit_code": result["exit_code"],
                "report_path": str(report),
                "status_path": str(status),
                "semantic_verification": "legacy-unverified"
                if result["schema_version"] == "1.0"
                else result.get("validators", {}).get("semantic_verification", False),
            }
        except (ValueError, OSError, ValidationError):
            continue
    raise ValueError("No matching finalized report is available")


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(argv if argv is not None else sys.argv[1:])
    args = parser().parse_args(arguments)
    try:
        if args.command == "setup":
            profile = private_directory(args.auth_home)
            codex = executable(args.codex_bin, "codex")
            print("Complete native login in the dedicated audit home:")
            print(
                shlex.join(
                    [
                        "env",
                        f"CODEX_HOME={profile}",
                        str(codex),
                        "-c",
                        'cli_auth_credentials_store="file"',
                        "login",
                        "--device-auth",
                    ]
                )
            )
            return 0
        if args.command == "latest":
            print(json.dumps(latest(target_for(args.root), args.output_dir, args.completed_only)))
            return 0
        if args.command == "schedule-example":
            target = target_for(args.root)
            plugin = Path(os.environ["ACA_PLUGIN_ROOT"])
            runtime = RuntimePaths(
                executable(args.codex_bin, "codex", target.root),
                executable(None, "uv", target.root),
                plugin,
            )
            audit_arguments = []
            for flag, path in (
                ("--output-dir", args.output_dir),
                ("--auth-home", args.auth_home),
                ("--source-codex-home", args.source_codex_home),
                ("--source-claude-home", args.source_claude_home),
                ("--source-user-home", args.source_user_home),
            ):
                audit_arguments.extend((flag, str(path.absolute())))
            for path in args.allow_source_root:
                audit_arguments.extend(("--allow-source-root", str(path.absolute())))
            state = args.source_claude_state or resolve_claude_state_path(
                args.source_user_home.absolute(),
                args.source_claude_home.absolute(),
                overridden=bool(os.environ.get("CLAUDE_CONFIG_DIR"))
                or any(arg.split("=", 1)[0] == "--source-claude-home" for arg in arguments),
            )
            audit_arguments.extend(("--source-claude-state", str(state.absolute())))
            if args.allow_output_in_target:
                audit_arguments.append("--allow-output-in-target")
            print(
                render_schedule_example(
                    args.scheduler,
                    target,
                    runtime,
                    CalendarSpec(args.hour, args.minute, args.weekday),
                    audit_arguments=audit_arguments,
                )
            )
            return 0
        outcome = asyncio.run(audit(parse_options(arguments)))
        print(
            json.dumps(
                {
                    "status": outcome.status,
                    "exit_code": outcome.exit_code,
                    "report_path": str(outcome.report_path),
                    "status_path": str(outcome.report_path.parent / "status.json")
                    if outcome.report_path
                    else None,
                }
            )
        )
        return outcome.exit_code
    except (OSError, ValueError, RuntimeError, KeyError, ValidationError) as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "exit_code": 3,
                    "error": "Structured output failed schema validation"
                    if isinstance(exc, ValidationError)
                    else str(exc),
                }
            ),
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
