"""Candidates are traceable observations, never automatic semantic findings."""

from dataclasses import asdict

import pytest
from agent_context_audit.discovery import discover_sources
from agent_context_audit.models import KnowledgeBundle
from agent_context_audit.snapshot import build_snapshot

from tests.conftest import put


def test_duplicate_observation_groups_locations_and_survives_line_drift(context_tree):
    from agent_context_audit.observations import build_observations

    target, roots = context_tree
    put(target.root / "AGENTS.md", "Retain signed commits.\n")
    other = put(target.root / "nested/AGENTS.md", "Retain signed commits.\n")
    snapshot = build_snapshot(discover_sources(target, roots), target)
    observations = build_observations(snapshot)
    assert len(observations) == 1
    assert observations[0].kind == "identical-text"
    assert len(observations[0].locations) == 2
    assert "severity" not in asdict(observations[0])
    other.write_text("\nRetain signed commits.\n")
    moved = build_observations(build_snapshot(discover_sources(target, roots), target))
    assert moved[0].observation_id == observations[0].observation_id


def test_aliases_and_masked_values_are_not_independent_duplicates(context_tree):
    from agent_context_audit.observations import build_observations

    target, roots = context_tree
    path = put(target.root / "AGENTS.md", "Retain applicable policies.\n")
    (target.root / "CLAUDE.md").symlink_to(path)
    put(target.root / ".claude/agents/a.md", "token = 'SECRET_A'\n")
    put(target.root / ".claude/agents/b.md", "token = 'SECRET_B'\n")
    observations = build_observations(build_snapshot(discover_sources(target, roots), target))
    assert not any(o.kind == "identical-text" for o in observations)


def test_observation_decisions_require_coverage_and_real_finding_destinations(context_tree):
    from agent_context_audit.observations import build_observations, validate_observation_decisions

    target, roots = context_tree
    put(target.root / "CLAUDE.md", "@missing.md\n")
    snapshot = build_snapshot(discover_sources(target, roots), target)
    snapshot.observations = build_observations(snapshot)
    ids = [o.observation_id for o in snapshot.observations]
    assert ids
    with pytest.raises(ValueError, match="assignment"):
        validate_observation_decisions({}, ids, snapshot, KnowledgeBundle({}))
    decision = {
        "observation_id": ids[0],
        "outcome": "confirmed",
        "rationale": "Missing import",
        "evidence_refs": [snapshot.observations[0].primary_source_id],
        "finding_indexes": [],
    }
    with pytest.raises(ValueError, match="destination"):
        validate_observation_decisions(
            {"observation_decisions": [decision], "findings": []},
            ids,
            snapshot,
            KnowledgeBundle({}),
        )
    decision["outcome"] = "dismissed"
    validate_observation_decisions(
        {"observation_decisions": [decision], "findings": []}, ids, snapshot, KnowledgeBundle({})
    )
    from tests.test_contracts import finding

    item = finding()
    item["observation_ids"] = ids
    with pytest.raises(ValueError, match="link"):
        validate_observation_decisions(
            {"observation_decisions": [decision], "findings": [item]},
            ids,
            snapshot,
            KnowledgeBundle({}),
        )
