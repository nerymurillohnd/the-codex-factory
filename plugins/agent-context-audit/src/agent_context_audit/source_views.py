"""Select eligible application-state evidence before discovery or model delivery."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from agent_context_audit.models import JsonObject, SourceRoots
from agent_context_audit.privacy import redact


@dataclass(frozen=True)
class SourceView:
    text: str
    configuration: JsonObject
    digest: str
    redacted_lines: list[int]


def resolve_claude_state_path(user_home: Path, claude_home: Path, *, overridden: bool) -> Path:
    return (claude_home if overridden else user_home) / ".claude.json"


def claude_state_path(roots: SourceRoots) -> Path:
    return roots.claude_state or resolve_claude_state_path(
        roots.user_home, roots.claude, overridden=roots.claude != roots.user_home / ".claude"
    )


def _project(text: str, targets: set[tuple[str, ...]]) -> str:
    """Keep only selected member spans; all omitted characters become inert whitespace."""
    decoder = json.JSONDecoder()
    spans: list[tuple[int, int]] = []

    def white(index: int) -> int:
        while index < len(text) and text[index].isspace():
            index += 1
        return index

    def visit(index: int, path: tuple[str, ...]) -> None:
        if text[index] != "{":
            return
        index = white(index + 1)
        while text[index] != "}":
            start = index
            key, end = decoder.raw_decode(text, index)
            value_start = white(white(end) + 1)
            _, end = decoder.raw_decode(text, value_start)
            member = (*path, key)
            if member in targets:
                spans.append((start, end))
            elif any(target[: len(member)] == member for target in targets):
                # Retain eligible ancestor keys so global and project MCP scopes remain distinct.
                spans.append((start, value_start + 1))
                visit(value_start, member)
            index = white(end)
            if text[index] == ",":
                index = white(index + 1)

    visit(white(0), ())
    output = ["\n" if char == "\n" else " " for char in text]
    for start, end in spans:
        output[start:end] = text[start:end]
    return "\n".join(line.rstrip() for line in "".join(output).split("\n"))


def build_claude_state_view(text: str, target_root: Path) -> SourceView:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate application-state key")
            result[key] = value
        return result

    document = json.loads(text, object_pairs_hook=unique)
    if not isinstance(document, dict):
        raise ValueError("Claude application state must be an object")
    configuration = {}
    targets: set[tuple[str, ...]] = set()
    if isinstance(document.get("mcpServers"), dict):
        configuration["mcpServers"] = document["mcpServers"]
        targets.add(("mcpServers",))
    projects = document.get("projects", {})
    local = projects.get(str(target_root), {}) if isinstance(projects, dict) else {}
    if isinstance(local, dict) and isinstance(local.get("mcpServers"), dict):
        configuration["projects"] = {str(target_root): {"mcpServers": local["mcpServers"]}}
        targets.add(("projects", str(target_root), "mcpServers"))
    protected, redacted_lines = redact(text, ".json")
    provenance = [
        (number, line.strip())
        for number, line in enumerate(_project(text, targets).splitlines(), 1)
        if line.strip()
    ]
    return SourceView(
        _project(protected, targets),
        configuration,
        hashlib.sha256(
            json.dumps([configuration, provenance], sort_keys=True).encode()
        ).hexdigest(),
        redacted_lines,
    )
