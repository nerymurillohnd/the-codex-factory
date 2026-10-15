"""Exercise the adapter with a strict process double, separate from native runtime tests."""

import asyncio
import os
import sys
from pathlib import Path

from agent_context_audit.models import CodexRuntime, ReviewRequest
from agent_context_audit.runtime import child_environment, run_review_job

FAKE = r"""
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
required = ["exec","--ignore-user-config","--ignore-rules","--ephemeral","--json","--output-schema"]
if any(flag not in args for flag in required):
    sys.exit(12)
if "--allowedTools" in args or "--output-format" in args:
    sys.exit(13)
sys.stdin.read()
mode = os.environ.get("ACA_TEST_MODE", "valid")
if mode == "missing":
    print(json.dumps({"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}))
    sys.exit(0)
output = Path(args[args.index("--output-last-message")+1])
output.write_text("not JSON" if mode == "malformed" else json.dumps({
    "status":"complete","receipts":[],"dispositions":[],"findings":[],
    "evidence_requests":[],"limitations":[],"notes":[],"observation_decisions":[]}))
print(json.dumps({"type":"turn.completed","usage":{"input_tokens":21,"output_tokens":8}}))
"""


def make_runtime(tmp_path: Path, mode: str = "valid") -> CodexRuntime:
    client = tmp_path / "fake-codex"
    client.write_text(f"#!{sys.executable}\n" + FAKE)
    client.chmod(0o700)
    work = tmp_path / "work"
    work.mkdir()
    profile = tmp_path / "auth"
    profile.mkdir()
    environment = dict(os.environ, ACA_TEST_MODE=mode)
    return CodexRuntime(client, profile, work, [], environment, "0.162.1", timeout=5)


def test_environment_does_not_forward_unrelated_secrets(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UNRELATED_SECRET", "synthetic-private-value")
    monkeypatch.setenv("CODEX_API_KEY", "synthetic-api-value")
    environment = child_environment(tmp_path)
    assert "UNRELATED_SECRET" not in environment
    assert environment.get("CODEX_API_KEY") == "synthetic-api-value"
    assert environment.get("CODEX_HOME") == str(tmp_path)


def test_exit_zero_without_final_output_is_failure(tmp_path) -> None:
    result = asyncio.run(
        run_review_job(
            make_runtime(tmp_path, "missing"), ReviewRequest("D1-0", "D1", "Read synthetic input.")
        )
    )
    assert result.status == "failed"
    assert result.error


def test_malformed_output_is_not_a_complete_contribution(tmp_path) -> None:
    result = asyncio.run(
        run_review_job(
            make_runtime(tmp_path, "malformed"),
            ReviewRequest("D1-0", "D1", "Read synthetic input."),
        )
    )
    assert result.status == "failed"


def test_validated_output_and_observed_usage_are_returned(tmp_path) -> None:
    result = asyncio.run(
        run_review_job(make_runtime(tmp_path), ReviewRequest("D1-0", "D1", "Read synthetic input."))
    )
    assert result.status == "complete"
    assert result.output["findings"] == []
    assert result.usage["input_tokens"] == 21
    assert result.input_digest


def test_context_validation_gets_one_bounded_repair(tmp_path):
    calls = []

    def validate(value):
        calls.append(value)
        if len(calls) == 1:
            raise ValueError("Source citation does not match the delivered assignment")

    request = ReviewRequest(
        "context-repair", "D1", "Review the assigned evidence.", validator=validate
    )
    result = asyncio.run(run_review_job(make_runtime(tmp_path), request))
    assert result.status == "complete"
    assert len(calls) == 2
    assert result.usage["input_tokens"] == 42
