"""Repository-local, fail-closed pre-push audit using trusted installed tooling."""

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import signal
import sys
import tempfile
import tomllib
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

import jsonschema

from tools.project_consistency import IGNORED, audit_project, private_path, strict_json

SOURCE = Path(__file__).resolve().parents[1]
MAX_FILE = 8 * 1024 * 1024
MAX_TREE = 64 * 1024 * 1024
MAX_EVIDENCE = 512 * 1024
MARKER = "# factory-push-audit managed v1"
ROLE = ".codex/agents/project-consistency-auditor.toml"
SKILL = ".agents/skills/audit-project-consistency/SKILL.md"
SCHEMA = "tools/schemas/project-review.schema.json"


@dataclass
class CommandResult:
    returncode: int
    stdout: bytes
    stderr: bytes


def run_command(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    input_data: bytes | None = None,
    timeout: int = 240,
) -> CommandResult:
    async def execute() -> CommandResult:
        process = await asyncio.create_subprocess_exec(
            *args,
            cwd=cwd,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(input_data), timeout)
            if len(stdout) + len(stderr) > 96 * 1024 * 1024:
                raise ValueError("Command output limit exceeded")
            return CommandResult(process.returncode or 0, stdout, stderr)
        finally:
            if process.returncode is None:
                os.killpg(process.pid, signal.SIGKILL)
                await process.wait()

    return asyncio.run(execute())


def git(root: Path, *args: str, input_data: bytes | None = None) -> bytes:
    binary = shutil.which("git")
    if binary is None:
        raise ValueError("Git executable unavailable")
    result = run_command(
        [binary, "--no-replace-objects", "-c", "core.fsmonitor=false", "-C", str(root), *args],
        cwd=root,
        input_data=input_data,
        timeout=30,
    )
    if result.returncode:
        raise ValueError(f"Git command failed: {args[0]}")
    return result.stdout


@dataclass(frozen=True)
class RefUpdate:
    local_ref: str
    local_oid: str
    remote_ref: str
    remote_oid: str


def parse_updates(text: str) -> list[RefUpdate]:
    if len(text) > 1024 * 1024:
        raise ValueError("Push update input exceeds limit")
    updates = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) != 4:
            raise ValueError("Malformed pre-push reference input")
        local_ref, local_oid, remote_ref, remote_oid = fields
        if (
            not re.fullmatch(r"(?:[a-f0-9]{40}|[a-f0-9]{64})", local_oid)
            or not re.fullmatch(r"(?:[a-f0-9]{40}|[a-f0-9]{64})", remote_oid)
            or len(local_oid) != len(remote_oid)
            or not remote_ref.startswith("refs/")
        ):
            raise ValueError("Invalid pre-push reference/object identity")
        updates.append(RefUpdate(local_ref, local_oid, remote_ref, remote_oid))
    if len({u.remote_ref for u in updates}) != len(updates):
        raise ValueError("Duplicate destination reference")
    return updates


def zero(oid: str) -> bool:
    return not oid.strip("0")


def snapshot(root: Path, oid: str, destination: Path) -> tuple[str, dict[str, str]]:
    tree = git(root, "rev-parse", "--verify", "--end-of-options", f"{oid}^{{tree}}")
    tree_oid = tree.decode().strip()
    listing = git(root, "ls-tree", "-rz", "--full-tree", tree_oid)
    files: dict[str, str] = {}
    total = 0
    destination.mkdir(parents=True)
    destination.chmod(0o700)
    for entry in listing.split(b"\0"):
        if not entry:
            continue
        header, filename = entry.split(b"\t", 1)
        mode, kind, blob = header.decode().split()
        name = filename.decode("utf-8")
        relative = Path(name)
        if relative.is_absolute() or any(p in {".", "..", ".git"} for p in relative.parts):
            raise ValueError("Unsafe Git tree path")
        if mode not in {"100644", "100755"} or kind != "blob":
            raise ValueError(f"Unsupported symlink/submodule in outgoing tree: {name}")
        if private_path(relative):
            raise ValueError(f"Prohibited credential/environment filename: {name}")
        if any(part in IGNORED for part in relative.parts):
            raise ValueError(f"Tracked development/private directory: {name}")
        size = int(git(root, "cat-file", "-s", blob))
        total += size
        if size > MAX_FILE or total > MAX_TREE:
            raise ValueError("Outgoing snapshot exceeds audit size limits")
        data = git(root, "cat-file", "blob", blob)
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o600)
        files[name] = hashlib.sha256(data).hexdigest()
    return tree_oid, files


def redactor():
    """Load the existing reviewed privacy implementation, never code from the target."""
    path = SOURCE / "plugins/agent-context-audit/src/agent_context_audit/privacy.py"
    spec = importlib.util.spec_from_file_location("factory_audit_privacy", path)
    if spec is None or spec.loader is None:
        raise ValueError("Trusted privacy implementation is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.redact


def collect_evidence(
    root: Path,
    files: dict[str, str],
    changed: list[str],
    deterministic: dict,
    context: dict | None = None,
    previous_sources: dict | None = None,
) -> dict:
    redact = redactor()
    required = []
    sources = {}
    for name in files:
        path = Path(name)
        if private_path(path) or any(part in IGNORED for part in path.parts):
            continue
        metadata = (
            path.name
            in {
                "README.md",
                "LICENSE",
                "CHANGELOG.md",
                "SKILL.md",
                "openai.yaml",
                "plugin.json",
                "marketplace.json",
                "AGENTS.md",
                "MAINTAINING.md",
                "SECURITY.md",
            }
            or path.parts[:2] == (".codex", "agents")
            or (
                path.parts[0] == "plugins"
                and path.suffix in {".py", ".sh", ".json", ".toml", ".md", ".yml", ".yaml"}
            )
        )
        changed_text = name in changed and path.suffix in {
            ".py",
            ".sh",
            ".json",
            ".toml",
            ".md",
            ".yml",
            ".yaml",
        }
        if not metadata and not changed_text:
            continue
        text = (root / path).read_text(encoding="utf-8")
        sanitized, lines = redact(text, path.suffix)
        sources[name] = {"sha256": files[name], "text": sanitized, "redacted_lines": lines}
        required.append(name)
    value = {
        "required_files": sorted(required),
        "sources": sources,
        "changed_files": changed,
        "deterministic": deterministic,
        "context": context or {"mode": "working-copy; not push approval"},
        "previous_sources": previous_sources or {},
    }
    encoded = json.dumps(value, sort_keys=True).encode()
    if len(encoded) > MAX_TREE:
        raise ValueError("Contextual evidence exceeds total audit limit")
    value["scope_digest"] = hashlib.sha256(encoded).hexdigest()
    return value


def review_evidence(*args, **kwargs) -> dict:
    """Compatibility entry point for a single bounded review packet."""
    value = collect_evidence(*args, **kwargs)
    if (
        len(
            json.dumps(
                {k: v for k, v in value.items() if k != "scope_digest"}, sort_keys=True
            ).encode()
        )
        > MAX_EVIDENCE
    ):
        raise ValueError("Contextual evidence exceeds limit; review is incomplete")
    return value


def review_batches(*args, **kwargs) -> list[dict]:
    """Keep full files and prior counterparts together, with shared contract anchors."""
    full = collect_evidence(*args, **kwargs)
    sources, previous = full["sources"], full["previous_sources"]
    anchors = {
        name
        for name in sources
        if Path(name).name
        in {
            "README.md",
            "LICENSE",
            "CHANGELOG.md",
            "SKILL.md",
            "openai.yaml",
            "plugin.json",
            "marketplace.json",
        }
        or "/schemas/" in name
    }
    context = dict(
        full["context"],
        full_scope_digest=full["scope_digest"],
        review_mode=(
            "bounded whole-file batches; shared identity, documentation and schema "
            "anchors; request missing cross-file evidence rather than infer it"
        ),
    )

    def packet(owned):
        selected = anchors | set(owned)
        value = {
            **full,
            "sources": {n: sources[n] for n in sorted(selected & set(sources))},
            "previous_sources": {n: previous[n] for n in sorted(selected & set(previous))},
            "required_files": sorted(selected & set(sources)),
            "context": context,
        }
        value.pop("scope_digest")
        encoded = json.dumps(value, sort_keys=True).encode()
        value["scope_digest"] = hashlib.sha256(encoded).hexdigest()
        return value, len(json.dumps(value, sort_keys=True).encode())

    # Keep the outgoing change coherent across packets whenever its complete
    # current/prior evidence fits alongside the shared contracts.
    contract_anchors = anchors.copy()
    anchors |= set(full["changed_files"]) & (set(sources) | set(previous))
    remaining = (set(sources) | set(previous)) - anchors
    if packet([])[1] > MAX_EVIDENCE or any(
        packet([name])[1] > MAX_EVIDENCE for name in sorted(remaining)
    ):
        anchors = contract_anchors
    names = sorted((set(sources) | set(previous)) - anchors)

    batches, owned = [], []
    for name in names:
        candidate, size = packet([*owned, name])
        if size > MAX_EVIDENCE:
            if not owned:
                raise ValueError(f"Whole source and shared anchors cannot fit review limit: {name}")
            batches.append(packet(owned)[0])
            owned = [name]
            if packet(owned)[1] > MAX_EVIDENCE:
                raise ValueError(f"Whole source and shared anchors cannot fit review limit: {name}")
        else:
            owned.append(name)
    last, size = packet(owned)
    if size > MAX_EVIDENCE:
        raise ValueError("Shared anchors cannot fit review limit")
    batches.append(last)
    if set().union(*(set(b["sources"]) for b in batches)) != set(sources) or set().union(
        *(set(b["previous_sources"]) for b in batches)
    ) != set(previous):
        raise ValueError("Review batch source coverage is incomplete")
    return batches


def review_all(batches: list[dict], binary: Path, directory: Path, prefix: str) -> dict:
    """Every bounded packet must pass; retain findings and exact packet evidence."""
    reviews = []
    for index, evidence in enumerate(batches):
        (directory / f"{prefix}-evidence-{index}.json").write_text(
            json.dumps(evidence, indent=2) + "\n"
        )
        reviews.append(native_review(evidence, binary, directory / f"{prefix}-review-{index}.json"))
    status = (
        "ERROR"
        if any(r["status"] == "ERROR" for r in reviews)
        else "BLOCKED"
        if any(r["status"] != "PASS" for r in reviews)
        else "PASS"
    )
    return {
        "status": status,
        "findings": [f for r in reviews for f in r["findings"]],
        "batches": reviews,
        "scope_digest": batches[0]["context"]["full_scope_digest"],
    }


def previous_evidence(root: Path, oid: str, changed: list[str]) -> dict:
    """Read selected previous blobs directly; no filters or historic secret-file reads."""
    redact = redactor()
    evidence = {}
    total = 0
    for entry in git(root, "ls-tree", "-rz", "--full-tree", oid).split(b"\0"):
        if not entry:
            continue
        header, filename = entry.split(b"\t", 1)
        name = filename.decode()
        path = Path(name)
        if name not in changed or private_path(path) or any(p in IGNORED for p in path.parts):
            continue
        if path.suffix not in {".json", ".toml", ".md", ".py", ".sh", ".yml", ".yaml"}:
            continue
        mode, kind, blob = header.decode().split()
        if kind != "blob" or mode not in {"100644", "100755"}:
            evidence[name] = {"unavailable": "Previous symlink/submodule was not followed."}
            continue
        size = int(git(root, "cat-file", "-s", blob))
        total += size
        if size > MAX_FILE or total > MAX_TREE:
            raise ValueError("Previous source evidence exceeds audit limits")
        raw = git(root, "cat-file", "blob", blob)
        try:
            text, lines = redact(raw.decode(), path.suffix)
            evidence[name] = {
                "text": text,
                "redacted_lines": lines,
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        except (ValueError, UnicodeError):
            evidence[name] = {"unavailable": "Previous malformed/non-UTF-8 source withheld."}
    return evidence


def native_review(evidence: dict, binary: Path, output: Path) -> dict:
    schema = json.loads((SOURCE / SCHEMA).read_text())
    role = tomllib.loads((SOURCE / ROLE).read_text())["developer_instructions"]
    instructions = role + "\n\n" + (SOURCE / SKILL).read_text()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="factory-readonly-review-") as directory:
        workspace = Path(directory)
        command = [
            str(binary),
            "exec",
            "--ignore-user-config",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--cd",
            str(workspace),
            "--json",
            "--output-schema",
            str(SOURCE / SCHEMA),
            "--output-last-message",
            str(output),
            "-c",
            "developer_instructions=" + json.dumps(instructions),
            "-c",
            'approval_policy="never"',
        ]
        for feature in ("shell_tool", "apps", "plugins", "memories", "multi_agent", "hooks"):
            command += ["--disable", feature]
        command += ["-"]
        result = run_command(
            command, cwd=workspace, input_data=json.dumps(evidence).encode(), timeout=240
        )
    if result.returncode or not output.is_file():
        raise ValueError("Native reviewer failed or unauthenticated; no approval issued")
    completed = 0
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError:
            raise ValueError("Malformed native reviewer stream") from None
        if not isinstance(event, dict):
            raise ValueError("Malformed reviewer event")
        item = event.get("item", {})
        if (
            isinstance(item, dict)
            and item.get("type") is not None
            and item["type"]
            not in {
                "agent_message",
                "reasoning",
                "todo_list",
            }
        ):
            raise ValueError("Reviewer attempted a prohibited tool/action")
        if event.get("type") in {"turn.failed", "error"}:
            raise ValueError("Native reviewer emitted an error")
        if event.get("type") == "turn.completed":
            completed += 1
    if completed != 1:
        raise ValueError("Native reviewer did not complete exactly one successful turn")
    verdict = strict_json(output.read_text())
    jsonschema.validate(verdict, schema)
    if not isinstance(verdict, dict):
        raise ValueError("Invalid reviewer verdict")
    if verdict["scope_digest"] != evidence["scope_digest"]:
        raise ValueError("Reviewer scope digest differs")
    if sorted(verdict["reviewed_files"]) != evidence["required_files"]:
        raise ValueError("Reviewer coverage is incomplete or duplicated")
    if verdict["status"] == "PASS" and any(f["severity"] == "error" for f in verdict["findings"]):
        raise ValueError("Reviewer PASS contradicts blocking findings")
    verdict["_controller"] = {
        "command": "codex exec --ignore-user-config --ephemeral --sandbox read-only",
        "exit_code": result.returncode,
        "tools_disabled": True,
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
    }
    return verdict


def audit_push(
    root: Path,
    updates: list[RefUpdate],
    runs: Path,
    codex_bin: Path,
    *,
    remote_digest: str | None = None,
) -> dict:
    root = root.resolve()
    report = {
        "status": "PASS",
        "repository": str(root),
        "updates": [asdict(u) for u in updates],
        "findings": [],
        "tips": [],
        "auditor_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "remote_digest": remote_digest,
    }
    run = runs / uuid.uuid4().hex
    run.mkdir(parents=True)
    run.chmod(0o700)
    try:
        if len(updates) > 1024:
            raise ValueError("Too many outgoing references")
        for index, update in enumerate(updates):
            if zero(update.local_oid):
                report["findings"].append(
                    {
                        "code": "reference-deletion",
                        "severity": "warning",
                        "path": update.remote_ref,
                        "message": "Deletion has no new content to certify.",
                    }
                )
                deletion = {
                    "operation": "delete; no new content is transmitted",
                    "update": asdict(update),
                    "repository": str(root),
                    "remote_digest": remote_digest,
                    "auditor_sha256": report["auditor_sha256"],
                }
                evidence = {
                    "required_files": ["push-updates.json"],
                    "sources": {
                        "push-updates.json": {
                            "text": json.dumps(deletion),
                            "redacted_lines": [],
                        }
                    },
                    "changed_files": [],
                    "deterministic": {"status": "PASS"},
                    "context": deletion,
                }
                evidence["scope_digest"] = hashlib.sha256(
                    json.dumps(evidence, sort_keys=True).encode()
                ).hexdigest()
                verdict = native_review(evidence, codex_bin, run / f"review-{index}.json")
                report["tips"].append({"operation": "delete", "review": verdict})
                report["findings"].extend(verdict["findings"])
                if verdict["status"] != "PASS":
                    report["status"] = verdict["status"]
                continue
            current = (
                git(
                    root,
                    "rev-parse",
                    "--verify",
                    "--end-of-options",
                    f"{update.local_ref}^{{object}}",
                )
                .decode()
                .strip()
            )
            if current != update.local_oid:
                raise ValueError("Outgoing reference changed before audit")
            if not zero(update.remote_oid):
                git(root, "cat-file", "-e", f"{update.remote_oid}^{{commit}}")
            rev_args = [update.local_oid]
            if not zero(update.remote_oid):
                rev_args.append("^" + update.remote_oid)
            commits = git(root, "rev-list", *rev_args).decode().splitlines()
            for commit in commits:
                try:
                    git(root, "verify-commit", commit)
                except ValueError:
                    report["findings"].append(
                        {
                            "code": "commit-signature",
                            "severity": "error",
                            "path": commit,
                            "message": "Outgoing commit signature is missing or unverifiable.",
                        }
                    )
            release = re.fullmatch(r"refs/tags/plugin/([a-z0-9-]+)/v(.+)", update.remote_ref)
            if release:
                try:
                    git(root, "verify-tag", update.local_oid)
                except ValueError:
                    report["findings"].append(
                        {
                            "code": "tag-signature",
                            "severity": "error",
                            "path": update.remote_ref,
                            "message": "Release tag must be annotated and verifiably signed.",
                        }
                    )
            with tempfile.TemporaryDirectory(prefix="factory-push-snapshot-") as temporary:
                snapshot_root = Path(temporary) / "tree"
                tree, files = snapshot(root, update.local_oid, snapshot_root)
                deterministic = audit_project(snapshot_root).to_dict()
                if release:
                    name, version = release.groups()
                    manifest = snapshot_root / "plugins" / name / "plugin.json"
                    if not manifest.exists():
                        manifest = snapshot_root / "plugins" / name / "metadata/plugin.json"
                    if json.loads(manifest.read_text()).get("version") != version:
                        report["findings"].append(
                            {
                                "code": "tag-version",
                                "severity": "error",
                                "path": update.remote_ref,
                                "message": "Release tag and target plugin version differ.",
                            }
                        )
                report["findings"].extend(deterministic["findings"])
                changed = (
                    sorted(files)
                    if zero(update.remote_oid)
                    else git(
                        root,
                        "diff-tree",
                        "--no-commit-id",
                        "--name-only",
                        "-r",
                        "-z",
                        update.remote_oid,
                        update.local_oid,
                    )
                    .decode()
                    .rstrip("\0")
                    .split("\0")
                )
                tip = {"tree": tree, "files": files, "deterministic": deterministic}
                report["tips"].append(tip)
                if any(f["severity"] == "error" for f in report["findings"]):
                    report["status"] = "BLOCKED"
                    continue
                context = {
                    "repository": str(root),
                    "updates": report["updates"],
                    "tree": tree,
                    "remote_digest": remote_digest,
                    "auditor_sha256": report["auditor_sha256"],
                }
                previous = (
                    previous_evidence(root, update.remote_oid, changed)
                    if not zero(update.remote_oid)
                    else {}
                )
                batches = review_batches(
                    snapshot_root, files, changed, deterministic, context, previous
                )
                verdict = review_all(batches, codex_bin, run, f"tip-{index}")
                tip["scope_digest"] = verdict["scope_digest"]
                tip["review"] = verdict
                report["findings"].extend(verdict["findings"])
                if verdict["status"] != "PASS":
                    report["status"] = verdict["status"]
            after = (
                git(
                    root,
                    "rev-parse",
                    "--verify",
                    "--end-of-options",
                    f"{update.local_ref}^{{object}}",
                )
                .decode()
                .strip()
            )
            if after != update.local_oid:
                raise ValueError("Outgoing reference changed during audit")
        for update in updates:
            if not zero(update.local_oid):
                current = (
                    git(
                        root,
                        "rev-parse",
                        "--verify",
                        "--end-of-options",
                        f"{update.local_ref}^{{object}}",
                    )
                    .decode()
                    .strip()
                )
                if current != update.local_oid:
                    raise ValueError("Outgoing reference changed before final approval")
    except (
        ValueError,
        OSError,
        TimeoutError,
        UnicodeError,
        KeyError,
        TypeError,
        jsonschema.ValidationError,
    ) as exc:
        report["status"] = "ERROR"
        report["findings"].append(
            {
                "code": "audit-error",
                "severity": "error",
                "path": "",
                "message": str(exc) if isinstance(exc, ValueError) else type(exc).__name__,
            }
        )
    if any(f["severity"] == "error" for f in report["findings"]) and report["status"] == "PASS":
        report["status"] = "BLOCKED"
    (run / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    report["report_path"] = str(run / "report.json")
    return report


def install_guard(root: Path, source: Path, codex_bin: Path) -> Path:
    common = Path(
        git(root, "rev-parse", "--path-format=absolute", "--git-common-dir").decode().strip()
    )
    hooks_path = run_command(
        [shutil.which("git") or "git", "-C", str(root), "config", "--get", "core.hooksPath"],
        cwd=root,
    )
    if hooks_path.stdout.strip():
        raise ValueError(
            "Existing core.hooksPath requires explicit safe integration; not overwritten"
        )
    hooks = common / "hooks"
    if hooks.is_symlink() or not hooks.resolve().is_relative_to(common.resolve()):
        raise ValueError("Existing hooks directory is a symlink/escape; not modified")
    hook = hooks / "pre-push"
    if hook.is_symlink() or (hook.exists() and not hook.is_file()):
        raise ValueError("Existing hook is a symlink/non-file; not modified")
    state = common / "factory-push-audit"
    if state.exists():
        raise ValueError(
            "Guard already installed; review an explicit update instead of overwriting"
        )
    uv = shutil.which("uv")
    if uv is None or not codex_bin.is_file():
        raise ValueError("uv and an explicit native Codex executable are required")
    runtime = state / "runtime"
    runtime.mkdir(parents=True)
    runtime.chmod(0o700)
    resources = [
        "pyproject.toml",
        "uv.lock",
        ".python-version",
        "tools/project_consistency.py",
        "tools/validate_marketplace.py",
        "tools/package_plugin.py",
        "tools/push_audit.py",
        SCHEMA,
        ROLE,
        SKILL,
        "plugins/agent-context-audit/src/agent_context_audit/privacy.py",
    ]
    hashes = {}
    for name in resources:
        original = source / name
        if original.is_symlink():
            raise ValueError("Installation source symlink refused")
        target = runtime / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    prepared = run_command([uv, "sync", "--locked", "--project", str(runtime)], cwd=runtime)
    if prepared.returncode:
        raise ValueError("Guard environment setup failed; hook not activated")
    config = {
        "common_dir": str(common),
        "codex_bin": str(codex_bin.resolve()),
        "resources": hashes,
    }
    (runtime / "installation.json").write_text(json.dumps(config, indent=2) + "\n")
    hook.parent.mkdir(exist_ok=True)
    if hook.exists() or hook.is_symlink():
        if hook.is_symlink() or not hook.is_file():
            raise ValueError("Existing hook cannot be safely chained; not replaced")
        shutil.copy2(hook, state / "previous-pre-push")
    wrapper = (
        "#!/bin/sh\nunset VIRTUAL_ENV\n"
        + MARKER
        + "\n"
        + "exec "
        + shlex.quote(uv)
        + " --directory "
        + shlex.quote(str(runtime))
        + " run --offline --locked --no-env-file --project "
        + shlex.quote(str(runtime))
        + ' python -m tools.push_audit pre-push --root "$PWD" -- "$@"\n'
    )
    candidate = state / "pre-push.new"
    candidate.write_text(wrapper)
    candidate.chmod(0o700)
    os.replace(candidate, hook)
    return hook


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "install", "pre-push"):
        command = commands.add_parser(name)
        command.add_argument("--root", type=Path, default=Path.cwd())
        if name != "pre-push":
            command.add_argument("--codex-bin", type=Path, default=None)
        if name == "check":
            command.add_argument("--deterministic", action="store_true")
        if name == "pre-push":
            command.add_argument("remote", nargs="*")
    args = parser.parse_args()
    args.root = args.root.resolve()
    try:
        if args.command == "install":
            binary = args.codex_bin or Path(shutil.which("codex") or "")
            print(install_guard(args.root, SOURCE, binary))
            return
        if args.command == "check":
            report = audit_project(args.root).to_dict()
            report["mode"] = "working-copy; not push approval"
            if not args.deterministic and report["status"] == "PASS":
                files = {
                    path.relative_to(args.root).as_posix(): hashlib.sha256(
                        path.read_bytes()
                    ).hexdigest()
                    for path in args.root.rglob("*")
                    if path.is_file()
                    and not path.is_symlink()
                    and not any(p in IGNORED for p in path.relative_to(args.root).parts)
                    and not private_path(path.relative_to(args.root))
                }
                with tempfile.TemporaryDirectory(prefix="factory-working-review-") as tmp:
                    batches = review_batches(args.root, files, sorted(files), report)
                    verdict = review_all(
                        batches,
                        args.codex_bin or Path(shutil.which("codex") or ""),
                        Path(tmp),
                        "working",
                    )
                    report["review"] = verdict
                    report["status"] = verdict["status"]
            print(json.dumps(report, indent=2))
            raise SystemExit(0 if report["status"] == "PASS" else 1)
        config = json.loads((SOURCE / "installation.json").read_text())
        common = str(
            Path(
                git(args.root, "rev-parse", "--path-format=absolute", "--git-common-dir")
                .decode()
                .strip()
            )
        )
        if common != config["common_dir"]:
            raise ValueError("Guard installation belongs to another repository")
        for name, expected in config["resources"].items():
            if hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() != expected:
                raise ValueError("Installed auditor changed; reviewed reinstall required")
        raw = sys.stdin.read(1024 * 1024 + 1)
        updates = parse_updates(raw)
        state = SOURCE.parent
        previous = state / "previous-pre-push"
        if previous.is_file() and os.access(previous, os.X_OK):
            chained = run_command(
                [str(previous), *args.remote], cwd=args.root, input_data=raw.encode()
            )
            if chained.returncode:
                raise ValueError("Existing pre-push hook rejected the push")
        remote_digest = hashlib.sha256(json.dumps(args.remote).encode()).hexdigest()
        report = audit_push(
            args.root,
            updates,
            state / "runs",
            Path(config["codex_bin"]),
            remote_digest=remote_digest,
        )
        print(f"Project push audit: {report['status']} — {report['report_path']}", file=sys.stderr)
        for finding in report["findings"]:
            print(f"  {finding['code']}: {finding['path']} — {finding['message']}", file=sys.stderr)
        raise SystemExit(0 if report["status"] == "PASS" else 1)
    except (ValueError, OSError, TimeoutError, KeyError, jsonschema.ValidationError) as exc:
        print(f"Project push audit: ERROR — {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
