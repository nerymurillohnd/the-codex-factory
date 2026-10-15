"""Exercise the actual pipeline with injected model/runtime boundaries."""

import asyncio

from agent_context_audit.models import CapabilityReport, RunOptions
from agent_context_audit.pipeline import audit

from tests.conftest import put
from tests.test_runtime import make_runtime


def test_unauthenticated_run_writes_failed_report_without_model_calls(
    context_tree, tmp_path, monkeypatch
):
    target, roots = context_tree
    put(target.root / "AGENTS.md", "A real policy.\n")
    runtime = make_runtime(tmp_path)

    async def prepare(options, run):
        return runtime

    async def probe(runtime):
        return CapabilityReport(True, {"fixture": True})

    async def authenticated(runtime):
        return False

    monkeypatch.setattr("agent_context_audit.pipeline.prepare_runtime", prepare)
    monkeypatch.setattr("agent_context_audit.pipeline.probe_isolation", probe)
    monkeypatch.setattr("agent_context_audit.pipeline.runtime_authenticated", authenticated)
    options = RunOptions(target, roots, tmp_path / "reports", runtime.auth_home, runtime.binary)
    outcome = asyncio.run(audit(options))
    assert outcome.exit_code == 3
    assert outcome.report_path.is_file()
    assert "not authenticated" in outcome.report_path.read_text()
    assert not outcome.result["jobs"]
    assert (target.root / "AGENTS.md").read_text() == "A real policy.\n"


def test_invalid_baseline_is_a_controlled_failure_without_payload_echo(context_tree, tmp_path):
    target, roots = context_tree
    baseline = put(
        tmp_path / "invalid-baseline.json", '{"private_payload":"SYNTHETIC_PRIVATE_CANARY"}'
    )
    options = RunOptions(
        target,
        roots,
        tmp_path / "runs",
        tmp_path / "auth",
        tmp_path / "unused-codex",
        baseline=baseline,
    )
    outcome = asyncio.run(audit(options))
    assert outcome.exit_code == 3
    assert "SYNTHETIC_PRIVATE_CANARY" not in outcome.report_path.read_text()
    assert "schema validation" in outcome.report_path.read_text()
