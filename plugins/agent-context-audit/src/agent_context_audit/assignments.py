"""Pack complete sources where possible while retaining exact primary ownership."""

from dataclasses import asdict, replace

from agent_context_audit.models import (
    AuditSnapshot,
    JsonObject,
    KnowledgeBundle,
    Observation,
    ReviewPackage,
)


def package_payload(
    package: ReviewPackage, snapshot: AuditSnapshot, knowledge: KnowledgeBundle
) -> JsonObject:
    source = next(s for s in snapshot.inventory.sources if s.source_id == package.source_id)
    return {
        "domain": source.domain,
        "sources": [asdict(source)],
        "source_catalog": [
            {
                "source_id": s.source_id,
                "path": str(s.path),
                "domain": s.domain,
                "line_count": s.line_count,
                "contexts": s.contexts,
            }
            for s in snapshot.inventory.sources
        ],
        "chunks": [asdict(c) for c in snapshot.chunks if c.chunk_id in package.chunk_ids],
        "directives": [
            asdict(d) for d in snapshot.directives if d.directive_id in package.directive_ids
        ],
        "observations": [
            asdict(o) for o in snapshot.observations if o.observation_id in package.observation_ids
        ],
        "supporting_context": package.context,
        "repository_facts": snapshot.facts,
        "platform": knowledge.data,
        "limitations": knowledge.gaps,
        "evidence_history": [],
    }


def build_review_packages(
    snapshot: AuditSnapshot,
    observations: list[Observation],
    knowledge: KnowledgeBundle,
    *,
    max_prompt_bytes: int = 160_000,
) -> list[ReviewPackage]:
    from agent_context_audit.review import prompt_for

    # An observation belongs to the first chunk intersecting its primary location.
    owners = {}
    for observation in observations:
        location = next(
            loc
            for loc in observation.locations
            if loc["source_id"] == observation.primary_source_id
        )
        chunk = next(
            (
                c
                for c in snapshot.chunks
                if c.source_id == observation.primary_source_id
                and c.line_start <= location["line_start"] <= c.line_end
            ),
            None,
        )
        if chunk:
            owners[observation.observation_id] = chunk.chunk_id

    def package(chunks) -> ReviewPackage:
        ids = [c.chunk_id for c in chunks]
        return ReviewPackage(
            f"pkg-{chunks[0].source_id}-{chunks[0].byte_start}",
            chunks[0].source_id,
            ids,
            [d.directive_id for d in snapshot.directives if d.chunk_id in ids],
            [identifier for identifier, owner in owners.items() if owner in ids],
        )

    def fits(candidate: ReviewPackage) -> bool:
        try:
            return (
                len(
                    prompt_for(
                        "specialist", package_payload(candidate, snapshot, knowledge)
                    ).encode()
                )
                <= max_prompt_bytes
            )
        except ValueError:
            return False

    result = []
    for source in snapshot.inventory.sources:
        chunks = [c for c in snapshot.chunks if c.source_id == source.source_id]
        pending = []
        for chunk in chunks:
            if pending and not fits(package([*pending, chunk])):
                result.append(package(pending))
                pending = []
            pending.append(chunk)
        if pending:
            result.append(package(pending))
    indexed = {c.chunk_id: c for c in snapshot.chunks}
    enriched = []
    for item in result:
        first, last = indexed[item.chunk_ids[0]].line_start, indexed[item.chunk_ids[-1]].line_end
        lines = snapshot.texts[item.source_id].splitlines()
        chosen = item
        for width in range(40, 0, -1):
            context = []
            for start, end in (
                (max(1, first - width), first - 1),
                (last + 1, min(len(lines), last + width)),
            ):
                if start <= end:
                    context.append(
                        {
                            "source_id": item.source_id,
                            "line_start": start,
                            "line_end": end,
                            "text": "\n".join(lines[start - 1 : end]),
                        }
                    )
            candidate = replace(item, context=context)
            if fits(candidate):
                chosen = candidate
                break
        enriched.append(chosen)
    return enriched
