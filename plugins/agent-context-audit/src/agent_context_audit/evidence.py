"""Repository facts are read as data through the same source boundary."""

import asyncio
import fnmatch
import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit

from agent_context_audit.models import AuditSnapshot, JsonObject
from agent_context_audit.network import fetch_document, validate_destination
from agent_context_audit.paths import resolve_local, secret_path, within
from agent_context_audit.privacy import redact
from agent_context_audit.processes import run_process
from agent_context_audit.snapshot import read_source_bytes
from agent_context_audit.source_views import claude_state_path


def read_evidence(snapshot: AuditSnapshot, request: JsonObject) -> JsonObject:
    relative = request.get("path")
    if isinstance(relative, str) and relative.startswith("source:"):
        first, last = request.get("line_start"), request.get("line_end")
        if not isinstance(first, int) or not isinstance(last, int):
            raise ValueError("Source context ranges must be integers")
        return read_source_evidence(
            snapshot,
            relative.removeprefix("source:"),
            first,
            last,
        )
    if isinstance(relative, str) and relative.startswith("index:"):
        pattern = relative.removeprefix("index:")
        if not pattern or len(pattern) > 256:
            raise ValueError("Invalid repository-index query")
        matches = [
            path
            for path in snapshot.inventory.repository_files
            if fnmatch.fnmatchcase(path, pattern)
        ]
        first, last = request.get("line_start"), request.get("line_end")
        if (
            type(first) is not int
            or type(last) is not int
            or first < 1
            or last < first
            or last - first >= 200
        ):
            raise ValueError("Index requests require a range of at most 200 entries")
        text = json.dumps(
            {
                "pattern": pattern,
                "matched_paths": len(matches),
                "first_entry": first,
                "paths": matches[first - 1 : last],
                "all_matches_delivered": first == 1 and last >= len(matches),
                "scope": (
                    "Eligible repository paths only; secret stores and excluded trees are omitted"
                ),
            },
            indent=2,
        )
        if len(text.encode()) > 65536:
            raise ValueError("Index response exceeds input bound; request a smaller range")
        result = {
            "id": f"index:{pattern}:{first}-{last}",
            "text": text,
            "provenance": "controller repository-file metadata",
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
        }
        if not any(item["id"] == result["id"] for item in snapshot.facts):
            snapshot.facts.append(result)
        return result
    if (
        not isinstance(relative, str)
        or Path(relative).is_absolute()
        or ".." in Path(relative).parts
    ):
        raise ValueError("Evidence must be a repository-relative path")
    root = snapshot.inventory.target.root.resolve()
    path = resolve_local(root / relative)
    if not path.is_relative_to(root) or ".git" in path.parts:
        raise ValueError("Evidence request escapes repository scope")
    excluded = (
        snapshot.inventory.roots.codex / "plugins",
        snapshot.inventory.roots.claude / "plugins",
    )
    if within(path, excluded):
        raise ValueError("Plugin-provided evidence requires a declared provenance reference")
    captured = next((s for s in snapshot.inventory.sources if s.canonical_path == path), None)
    if captured:
        first, last = request.get("line_start"), request.get("line_end")
        if not isinstance(first, int) or not isinstance(last, int):
            raise ValueError("Source context ranges must be integers")
        return read_source_evidence(snapshot, captured.source_id, first, last)
    if path == resolve_local(claude_state_path(snapshot.inventory.roots)):
        raise ValueError("Application state has no eligible protected source view")
    raw = read_source_bytes(path)
    text = raw.decode("utf-8-sig").replace("\r\n", "\n")
    if "\x00" in text:
        raise ValueError("Binary evidence is unsupported")
    sanitized, redacted = redact(text, path.suffix)
    lines = sanitized.splitlines()
    first, last = request.get("line_start"), request.get("line_end")
    if (
        not isinstance(first, int)
        or not isinstance(last, int)
        or isinstance(first, bool)
        or isinstance(last, bool)
    ):
        raise ValueError("Evidence ranges must be integer line numbers")
    if first < 1 or last < first or first > len(lines):
        raise ValueError("Invalid evidence range")
    last = min(last, len(lines))
    selected = "\n".join(lines[first - 1 : last])
    if len(selected.encode()) > 65536:
        raise ValueError("Evidence request exceeds input size; request a smaller range")
    result = {
        "id": f"repo:{relative}:{first}-{last}",
        "path": relative,
        "line_start": first,
        "line_end": last,
        "text": selected,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "redacted_lines": redacted,
    }
    if not any(item["id"] == result["id"] for item in snapshot.facts):
        snapshot.facts.append(result)
    return result


def read_source_evidence(
    snapshot: AuditSnapshot, source_id: str, first: int, last: int
) -> JsonObject:
    text = snapshot.texts.get(source_id)
    if text is None:
        raise ValueError("Source is not available in the protected snapshot")
    lines = text.splitlines()
    if (
        type(first) is not int
        or type(last) is not int
        or first < 1
        or last < first
        or last - first >= 200
        or first > len(lines)
    ):
        raise ValueError("Source context requires a range of at most 200 valid lines")
    last = min(last, len(lines))
    selected = "\n".join(lines[first - 1 : last])
    if len(selected.encode()) > 65536:
        raise ValueError("Source context exceeds the bounded response size")
    result = {
        "id": f"source-context:{source_id}:{first}-{last}",
        "source_id": source_id,
        "line_start": first,
        "line_end": last,
        "text": selected,
        "sha256": hashlib.sha256(selected.encode()).hexdigest(),
        "provenance": "protected source snapshot",
        "kind": "source-context",
    }
    if not any(item["id"] == result["id"] for item in snapshot.facts):
        snapshot.facts.append(result)
    return result


def collect_repository_facts(snapshot: AuditSnapshot) -> None:
    read_evidence(
        snapshot,
        {
            "path": "index:*",
            "line_start": 1,
            "line_end": 200,
            "reason": "Locate supporting repository evidence",
        },
    )
    root = snapshot.inventory.target.root
    candidates = [
        "package.json",
        "pyproject.toml",
        "Cargo.toml",
        "go.mod",
        "Makefile",
        "biome.json",
        "biome.jsonc",
        ".prettierrc.json",
        "tsconfig.json",
        ".nvmrc",
        ".python-version",
        "ruff.toml",
        ".ruff.toml",
    ]
    workflow_directory = root / ".github/workflows"
    if workflow_directory.is_dir() and not workflow_directory.is_symlink():
        candidates.extend(
            str(path.relative_to(root)) for path in sorted(workflow_directory.glob("*.y*ml"))
        )
    for relative in candidates:
        path = root / relative
        if path.is_file():
            try:
                read_evidence(
                    snapshot,
                    {
                        "path": relative,
                        "line_start": 1,
                        "line_end": 200,
                        "reason": "Repository tooling and declared behavior",
                    },
                )
            except (OSError, ValueError, UnicodeError) as exc:
                snapshot.inventory.gaps.append(
                    f"Repository fact unavailable: {relative}: {type(exc).__name__}"
                )


def compare_evidence(snapshot: AuditSnapshot) -> list[str]:
    changes: list[str] = []
    for item in snapshot.facts:
        if "path" not in item:
            continue
        try:
            current = hashlib.sha256(
                read_source_bytes(snapshot.inventory.target.root / item["path"])
            ).hexdigest()
            if current != item["sha256"]:
                changes.append(f"Repository evidence changed during audit: {item['path']}")
        except (OSError, ValueError):
            changes.append(f"Repository evidence unavailable after audit: {item['path']}")
    return sorted(set(changes))


async def check_references(snapshot: AuditSnapshot, allowed_domains: tuple[str, ...]) -> None:
    semaphore = asyncio.Semaphore(4)

    async def check(source, reference):
        if reference.kind == "url" and urlsplit(reference.target).hostname in allowed_domains:
            try:
                validate_destination(reference.target, set(allowed_domains))
                async with semaphore:
                    document = await asyncio.to_thread(
                        fetch_document, reference.target, set(allowed_domains)
                    )
                reference.state = (
                    "http-confirmed-missing"
                    if document.status in {404, 410}
                    else "http-reachable"
                    if document.status == 200
                    else f"http-unverified-{document.status}"
                )
            except (OSError, ValueError, TimeoutError):
                reference.state = "restricted-or-unavailable"
        text = json.dumps(
            {
                "source_id": source.source_id,
                "line": reference.line,
                "target": reference.target,
                "kind": reference.kind,
                "state": reference.state,
            },
            sort_keys=True,
        )
        snapshot.facts.append(
            {
                "id": "reference:" + hashlib.sha256(text.encode()).hexdigest()[:20],
                "text": text,
                "provenance": "controller reference observation",
            }
        )

    await asyncio.gather(
        *(
            check(source, reference)
            for source in snapshot.inventory.sources
            for reference in source.references
        )
    )


async def observe_git(root: Path) -> JsonObject:
    git = shutil.which("git")
    if not git or Path(git).resolve().is_relative_to(root.resolve()):
        return {"available": False, "reason": "Trusted Git executable unavailable"}
    working = next((parent for parent in (root, *root.parents) if (parent / ".git").exists()), None)
    if working is None:
        return {"available": True, "kind": "not-repository", "head": None, "dirty": None}
    try:
        git_entry = resolve_local(working / ".git")
        if git_entry.is_dir():
            git_dir = git_entry
        else:
            value = read_source_bytes(git_entry).decode().strip()
            if not value.startswith("gitdir: "):
                raise ValueError("Invalid gitdir reference")
            git_dir = resolve_local(working / value[8:])
        common_file = git_dir / "commondir"
        common = (
            resolve_local(git_dir / read_source_bytes(common_file).decode().strip())
            if common_file.is_file()
            else git_dir
        )
        for config in (common / "config", git_dir / "config.worktree"):
            if config.is_file():
                if not within(resolve_local(config), (common, git_dir)):
                    raise ValueError("Git config path escape")
                content = read_source_bytes(config).decode()
                if re.search(r"(?im)^\s*\[\s*include", content):
                    raise ValueError("Repository Git includes require separate verification")
                if re.search(r"(?im)^\s*\[\s*filter(?:\s|[.\]])", content):
                    raise ValueError("Repository Git filters prevent passive status verification")
        metadata: dict[str, str] = {}
        for item in (git_dir / "HEAD", git_dir / "index", common / "packed-refs"):
            if item.is_file():
                actual = resolve_local(item)
                if not within(actual, (git_dir, common)):
                    raise ValueError("Git metadata path escape")
                metadata[
                    str(item.relative_to(git_dir))
                    if item.is_relative_to(git_dir)
                    else "common:packed-refs"
                ] = hashlib.sha256(read_source_bytes(actual)).hexdigest()
        environment = {
            key: os.environ[key] for key in ("PATH", "HOME", "LANG") if key in os.environ
        }
        environment.update(
            GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_OPTIONAL_LOCKS="0"
        )
        prefix = [
            git,
            "--no-pager",
            "--no-optional-locks",
            f"--git-dir={git_dir}",
            f"--work-tree={working}",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.untrackedCache=false",
            "-c",
            f"core.hooksPath={os.devnull}",
            "-c",
            f"core.attributesFile={os.devnull}",
        ]
        head_result = await run_process(
            prefix + ["rev-parse", "--verify", "HEAD"], cwd=working, env=environment, timeout=10
        )
        tracked = await run_process(
            prefix + ["ls-files", "--cached", "-z"], cwd=working, env=environment, timeout=10
        )
        if tracked.returncode:
            raise ValueError("Tracked-file metadata is unavailable")
        if any(secret_path(Path(name)) for name in tracked.stdout.decode().split("\0") if name):
            raise ValueError("Tracked secret stores prevent passive Git working-tree verification")
        head_text = head_result.stdout.decode().strip()
        head = head_text if re.fullmatch(r"[0-9a-f]{40,64}", head_text) else None
        status = await run_process(
            prefix + ["status", "--porcelain=v2", "-z", "--ignore-submodules=all"],
            cwd=working,
            env=environment,
            timeout=10,
        )
        if status.returncode:
            raise ValueError("Git status unavailable")
        return {
            "available": True,
            "kind": "repository" if head else "unborn",
            "head": head,
            "dirty": bool(status.stdout),
            "status_sha256": hashlib.sha256(status.stdout).hexdigest(),
            "metadata_sha256": hashlib.sha256(
                json.dumps(metadata, sort_keys=True).encode()
            ).hexdigest(),
            "submodules": "not traversed",
        }
    except (OSError, ValueError, TimeoutError, UnicodeError) as exc:
        return {
            "available": False,
            "reason": str(exc) if isinstance(exc, ValueError) else type(exc).__name__,
        }
