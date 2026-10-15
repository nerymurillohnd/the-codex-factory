"""Same controller and identities across modes; doubles do not establish model accuracy."""

import asyncio
import json
from dataclasses import replace
from pathlib import Path

from agent_context_audit.models import CapabilityReport, DomainResult, KnowledgeBundle, RunOptions
from agent_context_audit.pipeline import audit
from agent_context_audit.reconcile import reconcile
from agent_context_audit.review import review_domains

from tests.conftest import put
from tests.test_runtime import make_runtime


def test_mode_pipeline_equivalence_and_parent_exposure(context_tree, tmp_path, monkeypatch):
    target, roots = context_tree
    put(target.root / "AGENTS.md", "Keep commits signed.\n")
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
        dispositions = [
            {
                "directive_id": d["directive_id"],
                "disposition": "keep",
                "rationale": "Applicable explicit policy",
                "evidence_refs": [d["source_id"]],
            }
            for d in data["directives"]
        ]
        if request.schema_name == "reconciliation":
            output = {
                "findings": [],
                "dispositions": dispositions,
                "decisions": [],
                "contested": [],
                "considered_job_ids": [c["job_id"] for c in data["contributions"]],
                "limitations": [],
            }
        else:
            output = {
                "status": "complete",
                "findings": [],
                "dispositions": dispositions,
                "limitations": [],
                "evidence_requests": [],
                "receipts": [
                    {"chunk_id": c["chunk_id"], "payload_sha256": c["payload_sha256"]}
                    for c in data["chunks"]
                ],
            }
        return DomainResult(request.job_id, request.domain, "complete", output)

    async def domains(snapshot, runtime, options, knowledge):
        return await review_domains(snapshot, runtime, options, knowledge, reviewer=reviewer)

    async def merged(results, snapshot, runtime, knowledge, **kwargs):
        return await reconcile(results, snapshot, runtime, knowledge, reviewer=reviewer, **kwargs)

    for name, function in {
        "prepare_runtime": prepare,
        "probe_isolation": probe,
        "runtime_authenticated": authenticated,
        "load_knowledge": knowledge,
        "inspect_runtime": inspect,
        "review_domains": domains,
        "reconcile": merged,
        "validate_effective_config": lambda *args: [],
    }.items():
        monkeypatch.setattr("agent_context_audit.pipeline." + name, function)
    options = RunOptions(target, roots, tmp_path / "runs", runtime.auth_home, runtime.binary)
    outputs = [
        asyncio.run(audit(replace(options, entry_mode=mode)))
        for mode in ("headless", "scheduled", "interactive", "app-scheduled")
    ]
    assert [result.exit_code for result in outputs] == [0, 0, 2, 2]
    assert all(
        result.result["dispositions"] == outputs[0].result["dispositions"] for result in outputs
    )
    assert all(result.report_path.is_file() for result in outputs)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "external-state"))
    inside = asyncio.run(
        audit(replace(options, output_dir=target.root / "audits", allow_output_in_target=True))
    )
    assert inside.exit_code == 0
    assert inside.result["output_in_target"]
    assert not Path(inside.result["evidence_path"]).is_relative_to(target.root)
    assert "Before publication" in inside.result["validators"]["git_preservation_scope"]
    assert (target.root / "AGENTS.md").read_text() == "Keep commits signed.\n"
