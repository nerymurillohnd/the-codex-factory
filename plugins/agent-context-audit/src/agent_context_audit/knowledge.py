"""Versioned primary-source knowledge with visible live freshness limits."""

import asyncio
import hashlib
import json
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit

from agent_context_audit.contracts import resource_path
from agent_context_audit.models import KnowledgeBundle
from agent_context_audit.network import fetch_document


class ArticleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.blocks: list[str] = []
        self.ignored = 0
        self.main = 0
        self.found_main = False
        self.all_blocks: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "nav", "footer"}:
            self.ignored += 1
        if tag in {"main", "article"}:
            self.main += 1
            self.found_main = True

    def handle_endtag(self, tag):
        if tag in {"script", "style", "nav", "footer"}:
            self.ignored = max(0, self.ignored - 1)
        if tag in {"main", "article"}:
            self.main = max(0, self.main - 1)

    def handle_data(self, data):
        if not self.ignored:
            self.all_blocks.append(data)
            if self.main:
                self.blocks.append(data)


def document_text(body: str) -> str:
    if re.search(r"<(?:html|body|main)\b", body, re.I):
        parser = ArticleText()
        parser.feed(body)
        body = " ".join(parser.blocks if parser.found_main else parser.all_blocks)
    return " ".join(body.split())


async def load_knowledge(
    codex_version: str, *, offline: bool = False, claude_present: bool = False
) -> KnowledgeBundle:
    data = json.loads(resource_path("references", "platform-knowledge.json").read_text())
    bundle = KnowledgeBundle(data)
    data["claude_present"] = claude_present
    if codex_version != data["versions"]["codex"]:
        bundle.gaps.append(f"Codex {codex_version} is outside the verified knowledge baseline")
    sources = [s for s in data["sources"] if s["host"] == "codex" or claude_present]
    if offline:
        bundle.gaps.append("Offline knowledge baseline: current platform behavior was not verified")
        return bundle
    semaphore = asyncio.Semaphore(4)

    async def check(source):
        async with semaphore:
            observation = {
                "id": source["id"],
                "url": source["url"],
                "checked_at": datetime.now(UTC).isoformat(),
            }
            try:
                domains = {urlsplit(s["url"]).hostname for s in data["sources"]}
                document = await asyncio.to_thread(
                    fetch_document, source["url"], {d for d in domains if d}
                )
                normalized = document_text(document.text)
                digest = hashlib.sha256(normalized.encode()).hexdigest()
                observation.update(http_status=document.status, sha256=digest)
                if document.status != 200 or not normalized:
                    raise ValueError("Official documentation unavailable")
                bundle.documents[source["id"]] = normalized
                if digest != source["text_sha256"]:
                    observation["state"] = "changed"
                    bundle.gaps.append(
                        f"Official documentation changed: {source['id']}; baseline needs review"
                    )
                else:
                    observation["state"] = "verified"
            except (OSError, ValueError, TimeoutError) as exc:
                observation.update(state="unavailable", error=type(exc).__name__)
                bundle.gaps.append(f"Official documentation unavailable: {source['id']}")
            bundle.observations.append(observation)

    await asyncio.gather(*(check(source) for source in sources))
    bundle.observations.sort(key=lambda item: item["id"])
    return bundle


def read_document_evidence(bundle: KnowledgeBundle, path: str) -> dict:
    """Resolve a fixed-document ID and local search term; never fetch model-generated URLs."""
    identifier, separator, term = path.removeprefix("doc:").partition("#")
    if not separator or not term.strip() or len(term) > 200:
        raise ValueError("Use doc:<source-id>#<literal search term>")
    text = bundle.documents.get(identifier)
    if text is None:
        raise ValueError("Official document is unavailable in this run")
    position = text.casefold().find(term.casefold())
    if position < 0:
        raise ValueError("Requested term is not present in the retrieved official document")
    excerpt = text[max(0, position - 500) : position + 2500]
    reference = "doc:" + identifier + ":" + hashlib.sha256(excerpt.encode()).hexdigest()[:16]
    source = next(s for s in bundle.data["sources"] if s["id"] == identifier)
    item = {
        "id": reference,
        "host": source["host"],
        "url": source["url"],
        "text": excerpt,
        "provenance": "live official document excerpt",
        "document_sha256": hashlib.sha256(text.encode()).hexdigest(),
    }
    if not any(claim["id"] == reference for claim in bundle.data["claims"]):
        bundle.data["claims"].append(item)
    return item
