"""Run synthetic hybrid-audit acceptance; machine checks are not semantic judgment."""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from tools.make_semantic_fixture import create_fixtures


def check_case(result: dict, expectation: dict) -> dict:
    findings = result.get("findings", [])
    categories = {item["category"] for item in findings}
    checks = {
        "completed_audit": result.get("status") in {"complete-clean", "complete-with-findings"},
        "coverage": result.get("validators", {}).get("coverage", {}).get("complete") is True,
        "semantic_verification": result.get("validators", {}).get("semantic_verification") is True,
        "adjudication": result.get("validators", {}).get("final_adjudication") is True,
        "expected_categories": set(expectation["expected_categories"]) <= categories,
    }
    sources = {s["source_id"]: s["path"] for s in result.get("sources", [])}
    protected = expectation.get("protected_paths", [])
    checks["protected_obligations"] = not any(
        any(
            sources.get(f["source_id"], "").endswith(path.removeprefix("repo/"))
            for path in protected
        )
        and (f["disposition"] in {"remove", "merge", "move", "revise"} or f["category"] == "false")
        for f in findings
    )
    if expectation.get("require_dismissal"):
        checks["candidate_dismissed"] = any(
            d["outcome"] == "dismissed" for d in result.get("observation_decisions", [])
        )
    if expectation.get("require_no_observations"):
        checks["independent_discovery"] = not result.get("observations") and bool(findings)
    path = expectation.get("required_evidence_path")
    if path:
        # The controller records the actual scoped read, not a claim that a tool was consulted.
        checks["supporting_evidence_read"] = any(
            f.get("path") == path for f in result.get("repository_evidence", [])
        )
    return checks


async def execute_acceptance(
    destination: Path,
    model: str,
    effort: str,
    auth_home: Path,
    codex_bin: Path,
    *,
    audit_runner=None,
) -> dict:
    from agent_context_audit.models import RunOptions, SourceRoots, Target
    from agent_context_audit.pipeline import audit
    from agent_context_audit.runtime import private_write

    audit_runner = audit if audit_runner is None else audit_runner
    if not model.strip():
        raise ValueError("An explicit model is required")
    if destination.exists():
        raise ValueError("Evaluation destination already exists; preserve previous attempts")
    destination.mkdir(parents=True, mode=0o700)
    scenarios = create_fixtures(destination / "fixtures", suite="hybrid")
    manifest = json.loads((destination / "fixtures/fixture-manifest.json").read_text())
    result = {
        "model_requested": model,
        "effort_requested": effort,
        "scheduled_runs": len(scenarios) * 3,
        "attempts": [],
        "status": "running",
        "semantic_review": "required",
        "limits": "Machine checks do not establish factual entailment or semantic completeness.",
    }
    started = time.monotonic()
    for scenario in scenarios:
        for repeat in range(1, 4):
            name = f"{scenario['name']}-repeat-{repeat}"
            target = Path(scenario["root"])
            options = RunOptions(
                Target(target, target),
                SourceRoots(
                    Path(scenario["source_codex_home"]),
                    Path(scenario["source_claude_home"]),
                    Path(scenario["source_user_home"]),
                ),
                destination / "runs" / name,
                auth_home,
                codex_bin,
                model=model,
                effort=effort,
            )
            outcome = await audit_runner(options)
            checks = check_case(outcome.result, manifest["expectations"][scenario["name"]])
            row = {
                "case": scenario["name"],
                "repeat": repeat,
                "audit_status": outcome.status,
                "exit_code": outcome.exit_code,
                "report": str(outcome.report_path) if outcome.report_path else None,
                "machine_checks": checks,
                "limitations": outcome.result.get("limitations", []),
                "jobs": outcome.result.get("jobs", []),
            }
            result["attempts"].append(row)
            private_write(destination / f"{name}.json", json.dumps(row, indent=2) + "\n")
            if outcome.exit_code == 3 and any(
                "authenticat" in message.lower()
                for message in outcome.result.get("limitations", [])
            ):
                result["status"] = "blocked"
                result["reason"] = "Dedicated native audit authentication unavailable"
                break
        if result["status"] == "blocked":
            break
    if result["status"] != "blocked":
        result["status"] = (
            "awaiting-semantic-review"
            if all(all(row["machine_checks"].values()) for row in result["attempts"])
            else "failed-checks"
        )
    result["wall_seconds"] = time.monotonic() - started
    private_write(destination / "acceptance.json", json.dumps(result, indent=2) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", default="high")
    parser.add_argument("--auth-home", type=Path, required=True)
    parser.add_argument("--codex-bin", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins/agent-context-audit/src"))
    result = asyncio.run(
        execute_acceptance(
            args.destination.resolve(),
            args.model,
            args.effort,
            args.auth_home.resolve(),
            args.codex_bin.resolve(),
        )
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "attempts": len(result["attempts"]),
                "result": str(args.destination / "acceptance.json"),
            }
        )
    )
    return 2 if result["status"] == "blocked" else 1 if result["status"] == "failed-checks" else 0


if __name__ == "__main__":
    raise SystemExit(main())
