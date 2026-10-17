"""Build deterministic installable archives without development or private artifacts."""

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT_FILES = {"plugin.json", "pyproject.toml", "uv.lock", "README.md", "CHANGELOG.md", "LICENSE"}
DIRECTORIES = {".codex-plugin", "skills", "scripts", "src", "schemas", "references"}
SUFFIXES = {".json", ".toml", ".md", ".yaml", ".yml", ".py"}
SESSION_FILES = {
    "metadata/plugin.json",
    ".codex-plugin/plugin.json",
    "README.md",
    "CHANGELOG.md",
    "LICENSE",
    "hooks/hooks.json",
    "hooks/session-bootstrap.sh",
    "skills/write-handoff/SKILL.md",
    "skills/write-handoff/references/handoff-template.md",
    "skills/write-handoff/references/inspection.md",
    "skills/write-handoff/references/save.md",
}
SESSION_OPTIONAL_FILES = {"skills/write-handoff/agents/openai.yaml"}
RECORDS_FILES = {
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
}


def package_plugin(root: Path, output_dir: Path, plugin_name: str = "agent-context-audit") -> Path:
    if plugin_name not in {"agent-context-audit", "session-handoff", "project-records"}:
        raise ValueError(f"Unknown plugin: {plugin_name}")
    plugin = root / "plugins" / plugin_name
    if (
        (root / "plugins").is_symlink()
        or plugin.is_symlink()
        or not plugin.resolve().is_relative_to(root.resolve())
    ):
        raise ValueError(f"Package source symlink/escape: {plugin_name}")
    required = {"session-handoff": SESSION_FILES, "project-records": RECORDS_FILES}.get(
        plugin_name, ROOT_FILES
    )
    files = []
    for path in sorted(plugin.rglob("*")):
        relative = path.relative_to(plugin)
        if "__pycache__" in relative.parts:
            continue
        if path.is_symlink():
            raise ValueError(f"Package source symlink: {relative}")
        if path.name == ".DS_Store":
            continue
        if not path.is_file():
            continue
        if plugin_name == "session-handoff":
            if relative.as_posix() not in SESSION_FILES | SESSION_OPTIONAL_FILES:
                raise ValueError(f"Unexpected installable file: {relative}")
        elif plugin_name == "project-records":
            if relative.as_posix() not in RECORDS_FILES:
                raise ValueError(f"Unexpected installable file: {relative}")
        else:
            if relative.parts[0] not in DIRECTORIES and relative.as_posix() not in ROOT_FILES:
                raise ValueError(f"Unexpected installable file: {relative}")
            if len(relative.parts) > 1 and path.suffix not in SUFFIXES:
                raise ValueError(f"Unsupported installable file: {relative}")
        if any(
            part in {"tests", "fixtures", ".env", ".dev.vars", "auth.json"}
            for part in relative.parts
        ):
            raise ValueError(f"Private/development artifact: {relative}")
        files.append(path)
    missing = required - {path.relative_to(plugin).as_posix() for path in files}
    if missing:
        raise ValueError(f"Missing package files: {sorted(missing)}")
    canonical = "metadata/plugin.json" if plugin_name == "session-handoff" else "plugin.json"
    manifest = json.loads((plugin / canonical).read_text())
    version = manifest["version"]
    if (
        manifest.get("name") != plugin_name
        or not isinstance(version, str)
        or not re.fullmatch(r"\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?", version)
    ):
        raise ValueError(f"Invalid plugin identity/version: {plugin_name}")
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f"{plugin_name}-{version}.zip"
    if any(path != archive for path in output_dir.glob("*.zip")):
        raise ValueError("Use a distinct output directory for each plugin/version archive")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for path in files:
            info = zipfile.ZipInfo(
                plugin_name + "/" + path.relative_to(plugin).as_posix(),
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o100755 if path.suffix == ".sh" else 0o100644) << 16
            output.writestr(info, path.read_bytes())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    prefixes = {""} if plugin_name == "agent-context-audit" else {"", f"{plugin_name}-"}
    for prefix in sorted(prefixes):
        (output_dir / f"{prefix}SHA256SUMS").write_text(f"{digest}  {archive.name}\n")
        (output_dir / f"{prefix}PACKAGE-CONTENTS.txt").write_text(
            "\n".join(str(p.relative_to(plugin)) for p in files) + "\n"
        )
    return archive


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path, default=Path("dist"))
    parser.add_argument(
        "--plugin",
        choices=["agent-context-audit", "session-handoff", "project-records"],
        default="agent-context-audit",
    )
    arguments = parser.parse_args()
    archive = package_plugin(arguments.root, arguments.output_dir, arguments.plugin)
    print(archive.resolve())
    prefix = "" if arguments.plugin == "agent-context-audit" else f"{arguments.plugin}-"
    print((arguments.output_dir / f"{prefix}SHA256SUMS").read_text().strip())


if __name__ == "__main__":
    main()
