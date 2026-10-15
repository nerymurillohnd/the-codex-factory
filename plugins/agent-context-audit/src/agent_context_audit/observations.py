"""Mechanical observations carry facts and provenance, never semantic verdicts."""

import hashlib
import json

from agent_context_audit.models import AuditSnapshot, JsonObject, KnowledgeBundle, Observation


def build_observations(snapshot: AuditSnapshot) -> list[Observation]:
    sources = {s.source_id: s for s in snapshot.inventory.sources}
    output: list[Observation] = []

    def add(kind: str, identity: object, locations: list[JsonObject], text: str) -> None:
        locations.sort(key=lambda loc: (loc["source_id"], loc["line_start"]))
        identifier = hashlib.sha256(
            json.dumps([kind, identity], sort_keys=True).encode()
        ).hexdigest()
        output.append(
            Observation(
                "obs-" + identifier[:20],
                kind,
                locations[0]["source_id"],
                locations,
                sorted({loc["source_id"] for loc in locations}),
                text,
            )
        )

    groups: dict[str, list[JsonObject]] = {}
    for directive in snapshot.directives:
        source = sources[directive.source_id]
        if directive.line_start in source.redacted_lines:
            continue
        normalized = " ".join(directive.text.split())
        groups.setdefault(normalized, []).append(
            {
                "source_id": directive.source_id,
                "line_start": directive.line_start,
                "line_end": directive.line_end,
            }
        )
    for normalized, locations in groups.items():
        if len({sources[loc["source_id"]].canonical_path for loc in locations}) < 2:
            continue
        identity = [normalized, sorted({loc["source_id"] for loc in locations})]
        add("identical-text", identity, locations, "Identical text: " + normalized)
    for source in snapshot.inventory.sources:
        if source.source_id not in snapshot.texts:
            continue
        for reference in source.references:
            if reference.state not in {"missing", "cycle", "depth-limit"}:
                continue
            add(
                "unresolved-reference",
                [source.source_id, reference.kind, reference.target, reference.state],
                [
                    {
                        "source_id": source.source_id,
                        "line_start": reference.line,
                        "line_end": reference.line,
                    }
                ],
                f"{reference.kind}: {reference.target}: {reference.state}",
            )
        if source.load_mode == "dead" and source.reason.startswith("Shadowed by"):
            add(
                "shadowed-source",
                [source.source_id, source.reason],
                [
                    {
                        "source_id": source.source_id,
                        "line_start": 1,
                        "line_end": max(1, source.line_count),
                    }
                ],
                source.reason,
            )
    # Repeated pointers have one observation with every location retained.
    unique: dict[str, Observation] = {}
    for item in output:
        previous = unique.get(item.observation_id)
        if previous:
            previous.locations.extend(
                loc for loc in item.locations if loc not in previous.locations
            )
        else:
            unique[item.observation_id] = item
    return [unique[key] for key in sorted(unique)]


def validate_observation_decisions(
    output: JsonObject, assigned_ids: list[str], snapshot: AuditSnapshot, knowledge: KnowledgeBundle
) -> None:
    from agent_context_audit.review import evidence_catalog

    decisions = output.get("observation_decisions", [])
    ids = [d["observation_id"] for d in decisions]
    if set(ids) != set(assigned_ids) or len(ids) != len(set(ids)):
        raise ValueError("Observation decision assignment is incomplete or duplicated")
    catalog = evidence_catalog(snapshot, knowledge)
    observations = {o.observation_id: o for o in snapshot.observations}
    findings = output.get("findings", [])
    decisions_by_id = {d["observation_id"]: d for d in decisions}
    for index, finding in enumerate(findings):
        if any(identifier not in observations for identifier in finding.get("observation_ids", [])):
            raise ValueError("Unknown finding observation")
        for identifier in finding.get("observation_ids", []):
            decision = decisions_by_id.get(identifier)
            if decision is None or index not in decision["finding_indexes"]:
                raise ValueError("Finding observation link has no matching decision")
    for decision in decisions:
        identifier = decision["observation_id"]
        if identifier not in observations:
            raise ValueError("Unknown observation assignment")
        if decision["outcome"] not in {"confirmed", "dismissed", "reframed", "unresolved"}:
            raise ValueError("Unknown observation outcome")
        if not decision["rationale"].strip() or not decision["evidence_refs"]:
            raise ValueError("Observation decision requires rationale and evidence")
        if any(ref not in catalog for ref in decision["evidence_refs"]):
            raise ValueError("Unknown observation evidence")
        indexes = decision["finding_indexes"]
        if len(indexes) != len(set(indexes)) or any(
            type(index) is not int or index < 0 or index >= len(findings) for index in indexes
        ):
            raise ValueError("Invalid observation finding destination")
        if decision["outcome"] in {"confirmed", "reframed"} and not indexes:
            raise ValueError("Confirmed observation has no finding destination")
        if decision["outcome"] == "dismissed" and indexes:
            raise ValueError("Dismissed observation cannot retain a finding destination")
        for index in indexes:
            if identifier not in findings[index].get("observation_ids", []):
                raise ValueError("Observation decision points to an unrelated finding")


def normalize_decisions(audit) -> None:
    """Bind transport positions to stable finding IDs before sorting or persistence."""
    for decision in audit.observation_decisions:
        decision["finding_ids"] = [
            audit.findings[index]["id"] for index in decision["finding_indexes"]
        ]


def remap_observation_decisions(audit) -> None:
    positions = {item["id"]: i for i, item in enumerate(audit.findings)}
    for decision in audit.observation_decisions:
        identifiers = decision.get("finding_ids", [])
        if any(identifier not in positions for identifier in identifiers):
            audit.limitations.append("Observation destination disappeared")
        decision["finding_indexes"] = [positions[i] for i in identifiers if i in positions]
