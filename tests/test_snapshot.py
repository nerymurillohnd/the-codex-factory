"""Coverage receipts must match complete reads, including long Unicode lines."""

import hashlib

from agent_context_audit.discovery import discover_sources
from agent_context_audit.models import DomainResult
from agent_context_audit.snapshot import build_snapshot, validate_coverage

from tests.conftest import put


def result_for(snapshot) -> DomainResult:
    return DomainResult(
        "D1-0",
        "D1",
        "complete",
        {
            "receipts": [
                {"chunk_id": c.chunk_id, "payload_sha256": c.payload_sha256}
                for c in snapshot.chunks
            ],
            "dispositions": [
                {
                    "directive_id": d.directive_id,
                    "disposition": "keep",
                    "rationale": "policy",
                    "evidence_refs": [],
                }
                for d in snapshot.directives
            ],
        },
    )


def test_complete_read_receipts_are_retained_for_incomplete_analysis(context_tree):
    target, roots = context_tree
    put(target.root / "AGENTS.md", "Investigate a referenced external tool.\n")
    snapshot = build_snapshot(discover_sources(target, roots), target)
    result = result_for(snapshot)
    result.status = "needs-evidence"
    result.assigned_chunks = [chunk.chunk_id for chunk in snapshot.chunks]
    result.assigned_directives = [directive.directive_id for directive in snapshot.directives]
    coverage = validate_coverage(snapshot, [result])
    assert not coverage.complete
    assert not any(
        "Missing chunk receipt" in error or "Missing disposition" in error
        for error in coverage.errors
    )
    assert snapshot.inventory.sources[0].status == "review-incomplete"


def test_reference_metadata_is_sanitized_before_model_delivery(context_tree):
    target, roots = context_tree
    put(
        roots.codex / "config.toml",
        'model_instructions_file="https://account:PRIVATE_CANARY@example.test/rules?token=QUERY_CANARY"\n',
    )
    snapshot = build_snapshot(discover_sources(target, roots), target)
    import json
    from dataclasses import asdict

    metadata = json.dumps([asdict(source) for source in snapshot.inventory.sources], default=str)
    assert "PRIVATE_CANARY" not in metadata
    assert "QUERY_CANARY" not in metadata


def test_last_line_is_in_coverage(context_tree) -> None:
    target, roots = context_tree
    text = "".join(f"Instruction {n}.\n" for n in range(603))
    put(target.root / "AGENTS.md", text)
    snapshot = build_snapshot(discover_sources(target, roots), target)
    assert snapshot.chunks
    assert "".join(c.text for c in snapshot.chunks) == text
    assert snapshot.chunks[-1].line_end == 603
    assert validate_coverage(snapshot, [result_for(snapshot)]).complete


def test_oversized_line_has_all_fragments(context_tree) -> None:
    target, roots = context_tree
    text = "á" * 20000 + "\nLast instruction.\n"
    put(target.root / "AGENTS.md", text)
    snapshot = build_snapshot(discover_sources(target, roots), target)
    assert len(snapshot.chunks) >= 3
    assert "".join(c.text for c in snapshot.chunks) == text
    assert all(len(c.text.encode()) <= 16384 for c in snapshot.chunks)
    assert validate_coverage(snapshot, [result_for(snapshot)]).complete


def test_missing_receipt_never_counts_as_analyzed(context_tree) -> None:
    target, roots = context_tree
    put(target.root / "AGENTS.md", "Use signed commits.\n")
    snapshot = build_snapshot(discover_sources(target, roots), target)
    result = result_for(snapshot)
    result.output["receipts"] = []
    assert not validate_coverage(snapshot, [result]).complete


def test_redaction_preserves_line_numbers(context_tree) -> None:
    target, roots = context_tree
    text = '[mcp_servers.example.env]\nODD_NAME = "SYNTHETIC_SECRET_VALUE"\n'
    path = put(roots.codex / "config.toml", text)
    snapshot = build_snapshot(discover_sources(target, roots), target)
    assert "SYNTHETIC_SECRET_VALUE" not in "".join(c.text for c in snapshot.chunks)
    assert "ODD_NAME" in "".join(c.text for c in snapshot.chunks)
    source = next(s for s in snapshot.inventory.sources if s.path == path)
    assert source.line_count == 2
    assert source.sha256 == hashlib.sha256(text.encode()).hexdigest()
    assert source.redacted_lines == [2]


def test_alias_to_secret_is_never_read(context_tree, monkeypatch) -> None:
    target, roots = context_tree
    secret = put(target.root / ".env", "DO_NOT_READ_SYNTHETIC\n")
    (target.root / "AGENTS.md").symlink_to(secret)
    original = type(secret).read_bytes
    opened = []

    def track(path):
        opened.append(path)
        return original(path)

    monkeypatch.setattr(type(secret), "read_bytes", track)
    inventory = discover_sources(target, roots)
    build_snapshot(inventory, target)
    assert secret not in opened
    assert inventory.exclusions
