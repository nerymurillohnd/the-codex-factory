"""Print user-installable schedule recipes; never install or start a scheduler."""

import os
import plistlib
import shlex
import shutil
import sys
from pathlib import Path

from agent_context_audit.models import CalendarSpec, RuntimePaths, Target
from agent_context_audit.paths import resolve_local
from agent_context_audit.report import repository_id

WEEKDAYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]


def render_schedule_example(
    kind: str,
    target: Target,
    runtime: RuntimePaths,
    calendar: CalendarSpec,
    *,
    audit_arguments: list[str] | None = None,
) -> str:
    if not 0 <= calendar.hour <= 23 or not 0 <= calendar.minute <= 59:
        raise ValueError("Invalid local calendar time")
    if calendar.weekday and calendar.weekday not in WEEKDAYS:
        raise ValueError("Invalid weekday")
    arguments = [
        "/usr/bin/env",
        "-u",
        "VIRTUAL_ENV",
        "-u",
        "CONDA_PREFIX",
        str(runtime.uv),
        "run",
        "--isolated",
        "--no-project",
        "--no-config",
        "--no-env-file",
        "--offline",
        "--python",
        str(
            (
                Path(sys.base_prefix)
                / "bin"
                / f"python{sys.version_info.major}.{sys.version_info.minor}"
            ).resolve()
        ),
        "python",
        "-I",
        "-S",
        str(runtime.plugin / "scripts/audit.py"),
        "audit",
        "--root",
        str(target.root),
        "--codex-bin",
        str(runtime.codex),
        "--entry-mode",
        "scheduled",
    ]
    arguments.extend(audit_arguments or [])
    if any(any(char in argument for char in "\r\n\x00") for argument in arguments):
        raise ValueError("Scheduler arguments must be single-line values")
    directories = [str(runtime.uv.parent), str(runtime.codex.parent)]
    for name in ("node", "git", "claude"):
        executable = shutil.which(name)
        if executable:
            logical = Path(executable).absolute()
            actual = resolve_local(logical)
            if not actual.is_relative_to(target.root.resolve()) and not logical.is_relative_to(
                target.root.resolve()
            ):
                directories.append(str(logical.parent))
    directories.extend(os.defpath.split(os.pathsep))
    environment = {
        "PATH": os.pathsep.join(dict.fromkeys(directories)),
        "XDG_DATA_HOME": os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")),
        "XDG_CACHE_HOME": os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")),
        "XDG_STATE_HOME": os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")),
        "UV_PYTHON_INSTALL_DIR": os.environ.get(
            "UV_PYTHON_INSTALL_DIR", str(Path(sys.base_prefix).parent)
        ),
    }
    if any(any(char in value for char in "\r\n\x00") for value in environment.values()):
        raise ValueError("Scheduler environment paths must be single-line values")
    for path in (runtime.uv, runtime.codex, runtime.plugin, target.root):
        if not path.is_absolute() or any(char in str(path) for char in "\r\n\x00"):
            raise ValueError("Scheduler paths must be absolute single-line paths")
    label = "com.the-codex-factory.agent-context-audit." + repository_id(target.root)
    if kind == "launchd":
        interval = {"Hour": calendar.hour, "Minute": calendar.minute}
        if calendar.weekday:
            interval["Weekday"] = WEEKDAYS.index(calendar.weekday)
        return plistlib.dumps(
            {
                "Label": label,
                "ProgramArguments": arguments,
                "StartCalendarInterval": interval,
                "WorkingDirectory": str(target.root),
                "EnvironmentVariables": environment,
                "RunAtLoad": False,
            },
            sort_keys=True,
        ).decode()
    if kind == "systemd":

        def quote(value, *, dollar=True):
            value = value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
            if dollar:
                value = value.replace("$", "$$")
            return '"' + value + '"'

        calendar_value = (calendar.weekday.title() + " ") if calendar.weekday else ""
        calendar_value += f"*-*-* {calendar.hour:02}:{calendar.minute:02}:00"
        return (
            f"# {label}.service\n[Unit]\nDescription=Agent Context Audit\n\n[Service]\n"
            f"Type=oneshot\nWorkingDirectory={quote(str(target.root), dollar=False)}\n"
            + "".join(
                f"Environment={quote(key + '=' + value, dollar=False)}\n"
                for key, value in environment.items()
            )
            + f"ExecStart={' '.join(quote(value) for value in arguments)}\n"
            "SuccessExitStatus=1\n\n"
            f"# {label}.timer (save as a separate file)\n[Unit]\n"
            "Description=Scheduled Agent Context Audit\n\n[Timer]\n"
            f"OnCalendar={calendar_value}\nPersistent=true\nUnit={label}.service\n\n"
            "[Install]\nWantedBy=timers.target\n"
        )
    if kind == "app":
        arguments[arguments.index("--entry-mode") + 1] = "app-scheduled"
        return (
            "Create a local Codex scheduled task in the original project directory. "
            "The computer and local runtime must be available. Run this command and report "
            "its status.json and report.md; do not modify audited sources.\n\n"
            + shlex.join(
                [
                    "/usr/bin/env",
                    *(key + "=" + value for key, value in environment.items()),
                    *arguments,
                ]
            )
            + "\n\n"
            f"Suggested local time: {calendar.weekday or 'daily'} "
            f"{calendar.hour:02}:{calendar.minute:02}. No schedule has been installed.\n"
        )
    raise ValueError("Unknown scheduler")
