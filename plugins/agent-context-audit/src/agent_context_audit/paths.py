"""Classify paths before reading bytes or following potentially remote links."""

import os
import stat
from collections import deque
from pathlib import Path

SECRET_NAMES = {
    ".env",
    ".dev.vars",
    "auth.json",
    ".credentials.json",
    "credentials.json",
    ".npmrc",
    ".pypirc",
    ".netrc",
}
SECRET_DIRS = {".ssh", ".aws", ".gnupg"}
NETWORK_PREFIXES = ("/net/", "/Network/", "//", "\\\\")


class BlockedSource(ValueError):
    """A source cannot authorize its own expansion of access."""


def secret_path(path: Path) -> bool:
    name = path.name.lower()
    return (
        name in SECRET_NAMES
        or (name.startswith((".env.", ".dev.vars.")) and not name.endswith((".example", ".sample")))
        or bool(SECRET_DIRS.intersection(path.parts))
        or path.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}
    )


def resolve_local(path: Path) -> Path:
    """Resolve links component by component, refusing remote and credential paths first."""
    if str(path).startswith(NETWORK_PREFIXES):
        raise BlockedSource("network-path")
    anchored = path if path.is_absolute() else Path.cwd() / path
    pending = deque(anchored.parts[1:])
    resolved = Path("/")
    links: set[Path] = set()
    while pending:
        part = pending.popleft()
        if part in {"", "."}:
            continue
        if part == "..":
            resolved = resolved.parent
            continue
        candidate = resolved / part
        if str(candidate).startswith(NETWORK_PREFIXES):
            raise BlockedSource("network-path")
        if secret_path(candidate):
            raise BlockedSource("secret")
        try:
            metadata = candidate.lstat()
        except FileNotFoundError:
            resolved = candidate
            continue
        if stat.S_ISLNK(metadata.st_mode):
            if candidate in links or len(links) >= 40:
                raise BlockedSource("symlink-cycle")
            links.add(candidate)
            target = os.readlink(candidate)
            if target.startswith(NETWORK_PREFIXES):
                raise BlockedSource("network-path")
            linked = Path(target)
            if linked.is_absolute():
                resolved = Path("/")
                parts = linked.parts[1:]
            else:
                parts = linked.parts
            pending.extendleft(reversed(parts))
        else:
            resolved = candidate
    return resolved


def within(path: Path, roots: tuple[Path, ...] | list[Path]) -> bool:
    return any(path.is_relative_to(root) for root in roots)


def read_source_bytes(path: Path) -> bytes:
    """Read a regular file through a no-follow descriptor chain."""
    path = resolve_local(path)
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(
            path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("Not a regular source file")
            data = stream.read()
            after = os.fstat(stream.fileno())
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError("Source changed during read")
            return data
    finally:
        os.close(directory)
