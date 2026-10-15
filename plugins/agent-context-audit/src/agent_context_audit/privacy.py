"""Redact configuration values without renumbering the original source."""

import json
import re
from collections.abc import MutableMapping, MutableSequence
from urllib.parse import unquote, urlsplit, urlunsplit

import tomlkit
from tomlkit.items import Item

SENSITIVE = re.compile(
    r"(?i)(?:api[_-]?key|token|password|secret|authorization|cookie|credential|private[_-]?key|oauth)"
)
TOKEN = re.compile(
    r"\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{16,}"
    r"|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{20,}"
    r"|xox[abprs]-[A-Za-z0-9-]{10,})\b"
)
BEARER = re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/=-]{12,}")
PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?"
    r"(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|$)"
)
STRING = re.compile(r'"(?:\\.|[^"\\])*"')
ASSIGNMENT = re.compile(r"""(?m)^(\s*["']?([\w.-]+)["']?\s*[:=]\s*)(.*)$""")
QUOTED_SECRET = re.compile(
    r"""(?i)(["']?(?:[\w.-]*(?:api[_-]?key|token|password|secret|authorization|cookie|credential|oauth)[\w.-]*)["']?\s*[:=]\s*)(["'])(.*?)(\2)"""
)
URL = re.compile(r"https?://[^\s\"'<>\\]+")
COMMAND_SECRET = re.compile(
    r"""(?i)(--[\w-]*(?:api[-_]?key|token|password|secret|credential|authorization)[\w-]*(?:=|\s+))('(?:[^']*)'|"(?:[^"]*)"|[^\s'";,]+)"""
)


def command_flag(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("--")
        and "=" not in value
        and bool(SENSITIVE.search(value))
    )


def sanitize_command(text: str) -> str:
    return COMMAND_SECRET.sub(lambda match: match.group(1) + "<redacted>", text)


def sanitize_embedded(text: str) -> str:
    text = PRIVATE_KEY.sub(
        lambda match: "\n".join("<redacted>" if line else "" for line in match.group().split("\n")),
        text,
    )
    text = TOKEN.sub("<redacted>", text)
    text = BEARER.sub(lambda match: match.group(1) + "<redacted>", text)
    return sanitize_command(text)


def sanitize_urls(text: str) -> str:
    """Remove all URL credentials/query values, including opaque signed links."""

    def clean(match: re.Match[str]) -> str:
        try:
            url = urlsplit(match.group())
            if TOKEN.search(unquote(url.path)):
                return "<redacted-url>"
            host = url.netloc.rsplit("@", 1)[-1]
            return urlunsplit((url.scheme, host, url.path, "redacted" if url.query else "", ""))
        except ValueError:
            return "<redacted-url>"

    return URL.sub(clean, text)


def _toml(text: str) -> str:
    document = tomlkit.parse(text)

    def visit(value: object, sensitive: bool = False) -> object:
        if isinstance(value, MutableMapping):
            for key in list(value):
                value[key] = visit(
                    value[key], sensitive or key == "env" or bool(SENSITIVE.search(str(key)))
                )
        elif isinstance(value, MutableSequence):
            preceding_flag = False
            for index in range(len(value)):
                current = value[index]
                value[index] = visit(current, sensitive or preceding_flag)
                preceding_flag = command_flag(current)
        elif sensitive and isinstance(value, Item):
            count = value.as_string().count("\n")
            replacement = tomlkit.string("<redacted>" + "\n" * count, multiline=count > 0)
            return replacement
        elif isinstance(value, str):
            sanitized = sanitize_embedded(value)
            if sanitized != value:
                return tomlkit.string(
                    sanitized, multiline=isinstance(value, Item) and "\n" in value.as_string()
                )
        return value

    visit(document)
    result = tomlkit.dumps(document)
    if result.count("\n") != text.count("\n"):
        raise ValueError("Redaction could not preserve source line numbers")
    return result


def _preserve_newlines(value: str, replacement: str = '"<redacted>"') -> str:
    return replacement + "\n" * value.count("\n")


def _json_spans(text: str) -> list[tuple[int, int]]:
    """Walk validated JSON token spans; retain all keys, redact sensitive leaf values."""
    decoder = json.JSONDecoder()
    spans: list[tuple[int, int]] = []

    def white(i: int) -> int:
        while i < len(text) and text[i].isspace():
            i += 1
        return i

    def visit(i: int, sensitive: bool = False) -> int:
        i = white(i)
        start = i
        if text[i] == "{":
            i = white(i + 1)
            while text[i] != "}":
                key, end = decoder.raw_decode(text, i)
                i = white(end)
                if text[i] != ":" or not isinstance(key, str):
                    raise ValueError("Invalid JSON object")
                i = visit(i + 1, sensitive or bool(SENSITIVE.search(key)) or key == "env")
                i = white(i)
                if text[i] == ",":
                    i = white(i + 1)
                elif text[i] != "}":
                    raise ValueError("Invalid JSON separator")
            return i + 1
        if text[i] == "[":
            i = white(i + 1)
            preceding_flag = False
            while text[i] != "]":
                current, _ = decoder.raw_decode(text, i)
                i = white(visit(i, sensitive or preceding_flag))
                preceding_flag = command_flag(current)
                if text[i] == ",":
                    i = white(i + 1)
                elif text[i] != "]":
                    raise ValueError("Invalid JSON separator")
            return i + 1
        _, end = decoder.raw_decode(text, i)
        if sensitive:
            spans.append((start, end))
        return end

    json.loads(text)
    visit(0)
    return spans


def redact(text: str, suffix: str) -> tuple[str, list[int]]:
    original = text
    if suffix == ".toml":
        try:
            text = _toml(text)
        except (ValueError, TypeError) as exc:
            raise ValueError("Cannot safely redact malformed TOML configuration") from exc
    text = sanitize_urls(text)
    if suffix == ".json":
        text = STRING.sub(
            lambda match: (
                json.dumps(sanitize_embedded(json.loads(match.group())))
                if sanitize_embedded(json.loads(match.group())) != json.loads(match.group())
                else match.group()
            ),
            text,
        )
    elif suffix != ".toml":
        text = sanitize_embedded(text)
    spans: list[tuple[int, int]] = []
    if suffix == ".json":
        try:
            spans = _json_spans(text)
        except (ValueError, IndexError, RecursionError) as exc:
            raise ValueError("Cannot safely redact malformed JSON configuration") from exc
    elif suffix != ".toml":
        env_table = False
        offset = 0
        for line in text.splitlines(keepends=True):
            stripped = line.strip()
            if stripped.startswith("["):
                env_table = bool(re.search(r"(?:^|[.\s])env(?:[.\s\]]|$)", stripped))
            match = ASSIGNMENT.match(line.rstrip("\r\n"))
            if match and (env_table or SENSITIVE.search(match.group(2))):
                spans.append((offset + match.start(3), offset + match.end(3)))
            offset += len(line)
        spans.extend((m.start(2), m.end(4)) for m in QUOTED_SECRET.finditer(text))
    token_spans = {(m.start(), m.end()) for m in TOKEN.finditer(text)}
    spans.extend(token_spans)
    # Merge overlaps so nested patterns cannot corrupt the replacement positions.
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    redacted_lines: set[int] = set()
    for start, end in merged:
        first = text.count("\n", 0, start) + 1
        redacted_lines.update(range(first, first + text[start:end].count("\n") + 1))
    result = text
    for start, end in reversed(merged):
        replacement = "<redacted>" if (start, end) in token_spans else '"<redacted>"'
        result = result[:start] + _preserve_newlines(text[start:end], replacement) + result[end:]
    redacted_lines.update(
        i
        for i, (before, after) in enumerate(
            zip(original.splitlines(), result.splitlines(), strict=True), 1
        )
        if before != after
    )
    return result, sorted(redacted_lines)
