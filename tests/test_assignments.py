"""Coherent source packages retain byte coverage and never read originals for context."""

from collections import Counter

import pytest
from agent_context_audit.discovery import discover_sources
from agent_context_audit.models import KnowledgeBundle
from agent_context_audit.snapshot import build_snapshot

from tests.conftest import put


def test_full_source_is_one_assignment_even_with_multiple_chunks(context_tree):
    from agent_context_audit.assignments import build_review_packages

    target, roots = context_tree
    put(target.root / "AGENTS.md", "\n".join(f"Policy number {n}." for n in range(300)))
    snapshot = build_snapshot(discover_sources(target, roots), target)
    assert len(snapshot.chunks) == 2
    packages = build_review_packages(snapshot, [], KnowledgeBundle({}))
    assert len(packages) == 1
    assert len(packages[0].chunk_ids) == 2
    assert len(packages[0].directive_ids) == 300


def test_split_packages_cover_every_chunk_and_directive_exactly_once(context_tree):
    from agent_context_audit.assignments import build_review_packages, package_payload
    from agent_context_audit.review import prompt_for

    target, roots = context_tree
    put(target.root / "AGENTS.md", "\n".join(f"Instruction number {n}." for n in range(1000)))
    snapshot = build_snapshot(discover_sources(target, roots), target)
    packages = build_review_packages(snapshot, [], KnowledgeBundle({}), max_prompt_bytes=100_000)
    assert len(packages) > 1
    assert Counter(c for p in packages for c in p.chunk_ids) == Counter(
        c.chunk_id for c in snapshot.chunks
    )
    assert Counter(d for p in packages for d in p.directive_ids) == Counter(
        d.directive_id for d in snapshot.directives
    )
    for package in packages:
        assert (
            len(
                prompt_for(
                    "specialist", package_payload(package, snapshot, KnowledgeBundle({}))
                ).encode()
            )
            <= 100_000
        )


def test_source_context_uses_snapshot_even_after_original_changes(context_tree):
    from agent_context_audit.evidence import read_source_evidence

    target, roots = context_tree
    path = put(roots.codex / "AGENTS.md", "Original protected instruction.\n")
    snapshot = build_snapshot(discover_sources(target, roots), target)
    sid = snapshot.inventory.sources[0].source_id
    path.write_text("Changed original must not be read.\n")
    item = read_source_evidence(snapshot, sid, 1, 1)
    assert item["text"] == "Original protected instruction."
    with pytest.raises(ValueError):
        read_source_evidence(snapshot, "missing", 1, 1)
    with pytest.raises(ValueError):
        read_source_evidence(snapshot, sid, 1, 201)
