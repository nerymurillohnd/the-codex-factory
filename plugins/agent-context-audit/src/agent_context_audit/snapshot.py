"""Complete, redacted source reads and mechanically checked coverage."""

import hashlib
import re

from agent_context_audit.models import (
    AuditSnapshot,
    Chunk,
    CoverageResult,
    Directive,
    DomainResults,
    Inventory,
    RunState,
    Target,
)
from agent_context_audit.paths import read_source_bytes, resolve_local
from agent_context_audit.privacy import redact
from agent_context_audit.source_views import build_claude_state_view, claude_state_path

CHUNK_BYTES = 16384
CHUNK_LINES = 200


def make_chunks(source_id: str, text: str) -> list[Chunk]:
    data = text.encode()
    offset, line = 0, 1
    chunks: list[Chunk] = []
    while offset < len(data):
        end = min(offset + CHUNK_BYTES, len(data))
        while True:
            try:
                segment = data[offset:end].decode()
                break
            except UnicodeDecodeError:
                end -= 1
        newlines = [m.end() for m in re.finditer("\n", segment)]
        if len(newlines) >= CHUNK_LINES:
            segment = segment[: newlines[CHUNK_LINES - 1]]
        elif end < len(data) and newlines and not segment.endswith("\n"):
            segment = segment[: newlines[-1]]
        payload = segment.encode()
        digest = hashlib.sha256(payload).hexdigest()
        end = offset + len(payload)
        last_line = line + segment.count("\n") - int(segment.endswith("\n"))
        chunks.append(
            Chunk(
                f"{source_id}:{offset}-{end}",
                source_id,
                line,
                max(line, last_line),
                offset,
                end,
                segment,
                digest,
            )
        )
        line += segment.count("\n")
        offset = end
    return chunks


def _directives(chunks: list[Chunk]) -> list[Directive]:
    directives: list[Directive] = []
    occurrences: dict[tuple[str, str], int] = {}
    for chunk in chunks:
        for index, line in enumerate(chunk.text.splitlines()):
            if not line.strip() or re.fullmatch(r"[\s{}\[\],#]+", line):
                continue
            normalized = " ".join(line.split())
            fingerprint = hashlib.sha256(normalized.encode()).hexdigest()[:20]
            key = (chunk.source_id, fingerprint)
            occurrence = occurrences.get(key, 0)
            occurrences[key] = occurrence + 1
            directive_id = f"{chunk.source_id}:{fingerprint}:{occurrence}"
            number = chunk.line_start + index
            directives.append(
                Directive(directive_id, chunk.source_id, number, number, line, chunk.chunk_id)
            )
    return directives


def build_snapshot(
    inventory: Inventory, target: Target, run: RunState | None = None
) -> AuditSnapshot:
    texts: dict[str, str] = {}
    chunks: list[Chunk] = []
    for source in inventory.sources:
        try:
            canonical = resolve_local(source.path)
            if canonical != source.canonical_path:
                raise ValueError("Source identity changed")
            raw = read_source_bytes(canonical)
            text = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
            view = (
                build_claude_state_view(text, target.root)
                if canonical == resolve_local(claude_state_path(inventory.roots))
                else None
            )
            digest = view.digest if view else hashlib.sha256(raw).hexdigest()
            if source.sha256 and digest != source.sha256:
                source.status = "changed-during-audit"
                source.reason = "Changed after inventory"
                inventory.gaps.append(f"Changed source: {source.path}")
                continue
            if "\x00" in text:
                raise ValueError("Binary source")
            source.sha256 = digest
            source.line_count = len(text.splitlines())
            source.byte_count = len(raw)
            if view:
                text, source.redacted_lines = view.text, view.redacted_lines
            else:
                text, source.redacted_lines = redact(text, source.path.suffix)
            for reference in source.references:
                reference.target, _ = redact(reference.target, ".log")
                if reference.resolved is not None:
                    reference.resolved, _ = redact(reference.resolved, ".log")
            texts[source.source_id] = text
            source.status = "pending"
            chunks.extend(make_chunks(source.source_id, text))
        except (OSError, ValueError, UnicodeError) as exc:
            source.status = "unreadable"
            source.reason = type(exc).__name__
            inventory.gaps.append(f"Unreadable source: {source.path}: {type(exc).__name__}")
    return AuditSnapshot(inventory, texts, chunks, _directives(chunks))


def validate_coverage(snapshot: AuditSnapshot, results: DomainResults) -> CoverageResult:
    expected = {chunk.chunk_id: chunk for chunk in snapshot.chunks}
    received: set[str] = set()
    dispositions: set[str] = set()
    observation_ids: list[str] = []
    errors: list[str] = list(snapshot.inventory.gaps)
    incomplete_chunks: set[str] = set()
    for result in results:
        observed = [d["observation_id"] for d in result.output.get("observation_decisions", [])]
        if set(observed) != set(result.assigned_observations) or len(observed) != len(
            set(observed)
        ):
            errors.append(f"Observation assignment mismatch: {result.job_id}")
        observation_ids.extend(observed)
        if result.status != "complete":
            errors.append(f"Incomplete job: {result.job_id}")
            incomplete_chunks.update(
                result.assigned_chunks
                or [receipt.get("chunk_id", "") for receipt in result.output.get("receipts", [])]
            )
        receipt_ids = [item.get("chunk_id") for item in result.output.get("receipts", [])]
        if result.assigned_chunks and (
            set(receipt_ids) != set(result.assigned_chunks)
            or len(receipt_ids) != len(set(receipt_ids))
        ):
            errors.append(f"Receipt assignment mismatch: {result.job_id}")
        directive_ids = [item.get("directive_id") for item in result.output.get("dispositions", [])]
        if result.assigned_directives and (
            set(directive_ids) != set(result.assigned_directives)
            or len(directive_ids) != len(set(directive_ids))
        ):
            errors.append(f"Disposition assignment mismatch: {result.job_id}")
        for receipt in result.output.get("receipts", []):
            chunk_id = receipt.get("chunk_id")
            chunk = expected.get(chunk_id)
            if chunk is None or receipt.get("payload_sha256") != chunk.payload_sha256:
                errors.append(f"Invalid receipt in {result.job_id}")
            else:
                received.add(chunk_id)
        dispositions.update(
            d.get("directive_id", "") for d in result.output.get("dispositions", [])
        )
    for missing in expected.keys() - received:
        errors.append(f"Missing chunk receipt: {missing}")
    expected_directives = {d.directive_id for d in snapshot.directives}
    if set(observation_ids) != {o.observation_id for o in snapshot.observations}:
        errors.append("Observation coverage is incomplete or foreign")
    if len(observation_ids) != len(set(observation_ids)):
        errors.append("Observation decisions have duplicate owners")
    for missing in expected_directives - dispositions:
        errors.append(f"Missing disposition: {missing}")
    for unknown in dispositions - expected_directives:
        errors.append(f"Unknown directive: {unknown}")
    for source in snapshot.inventory.sources:
        source_chunks = [chunk for chunk in snapshot.chunks if chunk.source_id == source.source_id]
        position = 0
        for chunk in source_chunks:
            if (
                chunk.byte_start != position
                or hashlib.sha256(chunk.text.encode()).hexdigest() != chunk.payload_sha256
            ):
                errors.append(f"Non-contiguous or altered payload: {source.source_id}")
            position = chunk.byte_end
        text = snapshot.texts.get(source.source_id)
        if text is not None and position != len(text.encode()):
            errors.append(f"Incomplete source bytes: {source.source_id}")
        if source.status not in {"unreadable", "changed-during-audit"}:
            source.status = (
                (
                    "review-incomplete"
                    if any(chunk.chunk_id in incomplete_chunks for chunk in source_chunks)
                    else "analyzed"
                )
                if text is not None
                and all(chunk.chunk_id in received for chunk in source_chunks)
                and all(
                    d.directive_id in dispositions
                    for d in snapshot.directives
                    if d.source_id == source.source_id
                )
                else "failed"
            )
    return CoverageResult(not errors, sorted(set(errors)))


def compare_sources(snapshot: AuditSnapshot, current: Inventory) -> list[str]:
    original = {(str(s.path), s.domain): s for s in snapshot.inventory.sources}
    latest = {(str(s.path), s.domain): s for s in current.sources}
    changes: list[str] = []
    if snapshot.inventory.repository_files != current.repository_files:
        changes.append("Repository file inventory changed during audit")
    for key in original.keys() | latest.keys():
        previous, new = original.get(key), latest.get(key)
        if previous is None:
            changes.append(f"Added source during audit: {key[0]}")
        elif new is None:
            previous.status = "changed-during-audit"
            changes.append(f"Removed source during audit: {key[0]}")
        elif (previous.sha256, previous.canonical_path) != (new.sha256, new.canonical_path):
            previous.status = "changed-during-audit"
            changes.append(f"Changed source during audit: {key[0]}")
    return changes
