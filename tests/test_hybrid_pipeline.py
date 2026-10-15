"""One pipeline must publish the observation and independent-assessment evidence."""

import asyncio
import json

from agent_context_audit.models import CapabilityReport, DomainResult, KnowledgeBundle, RunOptions
from agent_context_audit.pipeline import audit
from agent_context_audit.reconcile import reconcile
from agent_context_audit.review import review_domains
from agent_context_audit.verification import complete_semantic_review

from tests.conftest import put
from tests.test_hybrid_review import response
from tests.test_runtime import make_runtime


def test_pipeline_publishes_observations_verification_and_final_decisions(
    context_tree, tmp_path, monkeypatch
):
    target, roots = context_tree
    put(target.root / "AGENTS.md", "Keep signed commits.\n")
    put(target.root / "nested/AGENTS.md", "Keep signed commits.\n")
    runtime = make_runtime(tmp_path)
    runtime.config = ['default_permissions="fixture"']

    async def prepare(*args):
        return runtime

    async def probe(*args):
        return CapabilityReport(True, {"fixture": True})

    async def authenticated(*args):
        return True

    async def knowledge(*args, **kwargs):
        return KnowledgeBundle({})

    async def inspect(*args):
        return {"configuration": {}, "layers": [], "skills": []}

    async def reviewer(runtime, request):
        data = json.loads(request.prompt.split("\nAUDIT_DATA_JSON\n")[1])
        if request.schema_name in {"verification", "adjudication"}:
            refs = data["targets"][0]["value"]["evidence_refs"]
            proof = [{"kind": "related-directive", "ref": refs[0], "quote": "Keep signed commits."}]
            if request.schema_name == "verification":
                value = {
                    "status": "complete",
                    "assessments": [
                        {
                            "target_id": t["target_id"],
                            "target_digest": t["target_digest"],
                            "verdict": "supported",
                            "rationale": "Distinct scope is intentional",
                            "evidence": proof,
                            "counterevidence": [],
                        }
                        for t in data["targets"]
                    ],
                    "evidence_requests": [],
                    "limitations": [],
                    "notes": [],
                }
            else:
                value = {
                    "decisions": [
                        {
                            "target_id": t["target_id"],
                            "target_digest": t["target_digest"],
                            "action": "kept",
                            "rationale": "Retain intentional guidance",
                            "evidence": proof,
                            "counterevidence": [],
                            "finding": None,
                            "observation_decision": None,
                        }
                        for t in data["targets"]
                    ],
                    "additional_findings": [],
                    "limitations": [],
                    "notes": [],
                }
        else:
            value = response(data)
            value["observation_decisions"] = [
                {
                    "observation_id": o["observation_id"],
                    "outcome": "dismissed",
                    "rationale": "Nested activation is intentional",
                    "evidence_refs": o["evidence_refs"],
                    "finding_indexes": [],
                }
                for o in data["observations"]
            ]
            if request.schema_name == "reconciliation":
                value = {
                    k: v
                    for k, v in value.items()
                    if k not in {"status", "receipts", "evidence_requests"}
                }
                value.update(
                    considered_job_ids=[c["job_id"] for c in data["contributions"]],
                    decisions=[],
                    contested=[],
                )
        return DomainResult(request.job_id, request.domain, "complete", value)

    async def domains(snapshot, runtime, options, knowledge):
        return await review_domains(snapshot, runtime, options, knowledge, reviewer=reviewer)

    async def merged(results, snapshot, runtime, knowledge, **kwargs):
        return await reconcile(results, snapshot, runtime, knowledge, reviewer=reviewer, **kwargs)

    async def semantic(merged, snapshot, runtime, options, knowledge):
        return await complete_semantic_review(
            merged, snapshot, runtime, options, knowledge, reviewer=reviewer
        )

    for name, function in {
        "prepare_runtime": prepare,
        "probe_isolation": probe,
        "runtime_authenticated": authenticated,
        "load_knowledge": knowledge,
        "inspect_runtime": inspect,
        "review_domains": domains,
        "reconcile": merged,
        "complete_semantic_review": semantic,
        "validate_effective_config": lambda *args: [],
    }.items():
        monkeypatch.setattr("agent_context_audit.pipeline." + name, function, raising=False)
    options = RunOptions(target, roots, tmp_path / "runs", runtime.auth_home, runtime.binary)
    outcome = asyncio.run(audit(options))
    assert outcome.exit_code == 0, outcome.result["limitations"]
    assert outcome.result["schema_version"] == "1.1"
    assert len(outcome.result["observations"]) == 1
    assert outcome.result["observation_decisions"][0]["outcome"] == "dismissed"
    assert outcome.result["semantic_assessments"][0]["verdict"] == "supported"
    assert outcome.result["adjudications"][0]["action"] == "kept"
    assert "Automatic observations" in outcome.report_path.read_text()
    assert "Independent semantic verification" in outcome.report_path.read_text()

    # Legacy states remain readable but carry no claim of independent verification.
    from agent_context_audit.cli import latest
    from agent_context_audit.contracts import load_schema, validate_output

    legacy_schema = load_schema("run-v1")
    legacy = {k: v for k, v in outcome.result.items() if k in legacy_schema["properties"]}
    legacy["schema_version"] = "1.0"
    legacy["baseline_changes"] = {
        k: v for k, v in legacy["baseline_changes"].items() if k != "unassessed"
    }
    validate_output(legacy, "run")
    (outcome.report_path.parent / "status.json").write_text(json.dumps(legacy))
    shown = latest(target, options.output_dir)
    assert shown["semantic_verification"] == "legacy-unverified"
