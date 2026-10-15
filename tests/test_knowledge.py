"""Knowledge freshness and evidence retrieval are explicit, bounded, and local."""

import asyncio

import pytest
from agent_context_audit.knowledge import load_knowledge, read_document_evidence
from agent_context_audit.models import KnowledgeBundle


def test_offline_cannot_claim_current_platform_verification():
    knowledge = asyncio.run(load_knowledge("0.162.1", offline=True))
    assert knowledge.gaps
    assert not knowledge.observations


def test_future_version_is_outside_verified_baseline():
    knowledge = asyncio.run(load_knowledge("999.0.0", offline=True))
    assert any("outside" in gap for gap in knowledge.gaps)


def test_document_evidence_cannot_expand_network_scope():
    knowledge = KnowledgeBundle(
        {
            "sources": [{"id": "official", "host": "codex", "url": "https://example.test"}],
            "claims": [],
        },
        documents={"official": "A documented configuration option is hooks."},
    )
    evidence = read_document_evidence(knowledge, "doc:official#hooks")
    assert evidence["document_sha256"]
    assert "hooks" in evidence["text"]
    with pytest.raises(ValueError):
        read_document_evidence(knowledge, "doc:https://attacker.test#hooks")
