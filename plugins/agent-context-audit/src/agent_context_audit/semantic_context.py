"""Bounded protected context and content identities for semantic review."""

import copy
import hashlib
import json
from dataclasses import asdict

from agent_context_audit.evidence import read_evidence
from agent_context_audit.knowledge import read_document_evidence
from agent_context_audit.models import JsonObject, ReconciledAudit
from agent_context_audit.review import evidence_catalog, prompt_for


def target_digest(value: JsonObject) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def verification_targets(audit: ReconciledAudit) -> list[JsonObject]:
    targets = []
    for finding in audit.findings:
        value = copy.deepcopy(finding)
        targets.append(
            {
                "target_id": "finding:" + finding["id"],
                "target_digest": target_digest(value),
                "value": value,
            }
        )
    for decision in audit.observation_decisions:
        value = {k: copy.deepcopy(v) for k, v in decision.items() if k != "finding_indexes"}
        if "finding_ids" not in value:
            value["finding_ids"] = [
                audit.findings[i]["id"] for i in decision.get("finding_indexes", [])
            ]
        targets.append(
            {
                "target_id": "observation:" + decision["observation_id"],
                "target_digest": target_digest(value),
                "value": value,
            }
        )
    return targets


def build_semantic_payload(
    targets, snapshot, knowledge, assessments=(), terminal=False
) -> JsonObject:
    refs = set()
    locations = []
    observations = {o.observation_id: o for o in snapshot.observations}
    for target in targets:
        value = target["value"]
        refs.update(value.get("evidence_refs", []))
        refs.update(e["ref"] for e in value.get("evidence", []))
        if "source_id" in value:
            locations.extend([value, *value.get("related", [])])
        else:
            observation = observations[value["observation_id"]]
            refs.update(observation.evidence_refs)
            locations.extend(observation.locations)
    excerpts = []
    for location in locations:
        sid = location["source_id"]
        lines = snapshot.texts.get(sid, "").splitlines()
        first = max(1, location["line_start"] - 40)
        last = min(len(lines), location["line_end"] + 40, first + 199)
        selected = "\n".join(lines[first - 1 : last])
        # Label bounded context explicitly; full content stays requestable by source ID.
        while len(selected.encode()) > 65536 and last >= first:
            last -= 1
            selected = "\n".join(lines[first - 1 : last])
        excerpts.append(
            {
                "source_id": sid,
                "line_start": first,
                "line_end": last,
                "text": selected,
                "complete_source": first == 1 and last == len(lines),
            }
        )
    catalog = evidence_catalog(snapshot, knowledge)
    return {
        "targets": targets,
        "assessments": list(assessments),
        "terminal": terminal,
        "source_excerpts": excerpts,
        "source_catalog": [
            {
                "source_id": s.source_id,
                "line_count": s.line_count,
                "path": str(s.path),
                "contexts": s.contexts,
            }
            for s in snapshot.inventory.sources
        ],
        "observations": [
            asdict(observations[t["value"]["observation_id"]])
            for t in targets
            if t["target_id"].startswith("observation:")
        ],
        "evidence": [
            {"ref": ref, "text": catalog[ref][:4000], "complete": len(catalog[ref]) <= 4000}
            for ref in sorted(refs)
            if ref in catalog
        ],
        "evidence_history": [],
    }


def pack_semantic_targets(targets, snapshot, knowledge, name, assessments=(), terminal=False):
    batches = []
    pending = []
    for target in targets:
        proposed = [*pending, target]
        ids = {t["target_id"] for t in proposed}
        selected = [a for a in assessments if a["target_id"] in ids]
        try:
            prompt_for(
                name, build_semantic_payload(proposed, snapshot, knowledge, selected, terminal)
            )
        except ValueError:
            if pending:
                batches.append(pending)
                pending = []
        pending.append(target)
    if pending:
        batches.append(pending)
    return batches


def validate_semantic_evidence(items, snapshot, knowledge) -> None:
    catalog = evidence_catalog(snapshot, knowledge)
    source_refs = set(snapshot.texts) | {d.directive_id for d in snapshot.directives}
    source_refs.update(f["id"] for f in snapshot.facts if f.get("kind") == "source-context")
    document_refs = {c["id"] for c in knowledge.data.get("claims", [])}
    for item in items:
        ref, quote = item["ref"], item["quote"]
        kinds = (
            {"related-directive"}
            if ref in source_refs
            else {"official-document", "native-default"}
            if ref in document_refs
            else {"repository-fact"}
        )
        if (
            ref not in catalog
            or not quote.strip()
            or quote not in catalog[ref]
            or item["kind"] not in kinds
        ):
            raise ValueError("Unverified semantic assessment evidence")


def supply_semantic_evidence(request, snapshot, knowledge):
    path = request["path"]
    if path.startswith("doc:"):
        return read_document_evidence(knowledge, path)
    if path.startswith("catalog:"):
        ref = path.removeprefix("catalog:")
        catalog = evidence_catalog(snapshot, knowledge)
        if ref not in catalog:
            raise ValueError("Unknown protected evidence reference")
        first, last = request["line_start"], request["line_end"]
        lines = catalog[ref].splitlines()
        if first < 1 or last < first or last - first >= 200 or first > len(lines):
            raise ValueError("Invalid protected catalog range")
        selected = "\n".join(lines[first - 1 : last])
        if len(selected.encode()) > 65536:
            raise ValueError("Protected catalog response exceeds bound")
        return {"id": ref, "text": selected, "line_start": first, "line_end": min(last, len(lines))}
    return read_evidence(snapshot, request)
