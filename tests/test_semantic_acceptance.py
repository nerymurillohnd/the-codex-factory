"""The evaluation runner uses synthetic scope and records every attempt honestly."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from agent_context_audit.models import RunOutcome


def test_runner_help_works_outside_pytest_import_configuration(tmp_path):
    done = subprocess.run(
        [sys.executable, "-B", "-m", "tools.run_semantic_acceptance", "--help"],
        cwd=Path(__file__).resolve().parents[1],
        env={"PATH": os.environ["PATH"], "HOME": str(tmp_path)},
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert done.returncode == 0, done.stderr
    assert "--model" in done.stdout


def test_runner_requires_explicit_model_and_preserves_existing_destination(tmp_path):
    from tools.run_semantic_acceptance import execute_acceptance

    with pytest.raises(ValueError, match="model"):
        asyncio.run(
            execute_acceptance(tmp_path / "new", "", "high", tmp_path / "auth", tmp_path / "codex")
        )
    with pytest.raises(ValueError, match="exists"):
        asyncio.run(
            execute_acceptance(
                tmp_path, "fixture-model", "high", tmp_path / "auth", tmp_path / "codex"
            )
        )


def test_runner_schedules_fifteen_isolated_audits_without_expected_answers(tmp_path):
    from tools.run_semantic_acceptance import execute_acceptance

    seen = []

    async def runner(options):
        seen.append(options)
        assert options.model == "fixture-model"
        assert options.roots.user_home.is_relative_to(tmp_path / "evaluation")
        assert not (options.target.root / "fixture-manifest.json").exists()
        return RunOutcome(
            "complete-clean",
            0,
            None,
            {
                "status": "complete-clean",
                "findings": [],
                "sources": [],
                "observations": [],
                "observation_decisions": [],
                "validators": {},
                "jobs": [],
                "limitations": [],
            },
        )

    result = asyncio.run(
        execute_acceptance(
            tmp_path / "evaluation",
            "fixture-model",
            "high",
            tmp_path / "auth",
            tmp_path / "codex",
            audit_runner=runner,
        )
    )
    assert len(seen) == 15
    assert len({str(o.output_dir) for o in seen}) == 15
    assert len(result["attempts"]) == 15
    assert result["semantic_review"] == "required"
    assert result["status"] != "passed"


def test_authentication_failure_is_blocked_not_a_semantic_pass(tmp_path):
    from tools.run_semantic_acceptance import execute_acceptance

    async def runner(options):
        return RunOutcome(
            "failed",
            3,
            None,
            {
                "status": "failed",
                "findings": [],
                "validators": {},
                "jobs": [],
                "limitations": ["Dedicated audit profile is not authenticated"],
            },
        )

    result = asyncio.run(
        execute_acceptance(
            tmp_path / "evaluation",
            "fixture-model",
            "high",
            tmp_path / "auth",
            tmp_path / "codex",
            audit_runner=runner,
        )
    )
    assert result["status"] == "blocked"
    assert len(result["attempts"]) == 1
    assert result["scheduled_runs"] == 15
