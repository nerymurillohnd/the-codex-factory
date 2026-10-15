"""Discover host source locations without executing target code."""

import hashlib
import json
import os
import re
import shlex
import tomllib
from pathlib import Path

from agent_context_audit.models import (
    Inventory,
    KnowledgeBundle,
    Reference,
    SourceRecord,
    SourceRoots,
    Target,
)
from agent_context_audit.paths import BlockedSource, read_source_bytes, resolve_local, within
from agent_context_audit.privacy import redact, sanitize_urls
from agent_context_audit.source_views import build_claude_state_view, claude_state_path

SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "__pycache__",
    ".superpowers",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".tox",
}
MANAGED = (
    Path("/etc/codex"),
    Path("/etc/claude-code"),
    Path("/Library/Application Support/ClaudeCode"),
)
IMPORT = re.compile(r'(?<![\w@])@((?:\\ |[^\s\'"<>])+)')


def _without_code(text: str) -> str:
    tick = chr(96)
    pattern = re.compile(rf"{tick}{{3}}[\s\S]*?{tick}{{3}}|~~~[\s\S]*?~~~|{tick}[^{tick}\n]*{tick}")
    return pattern.sub(lambda m: "".join("\n" if char == "\n" else " " for char in m.group()), text)


def _config(path: Path, inventory: Inventory) -> dict:
    try:
        path = resolve_local(path)
        if not path.is_file():
            return {}
        allowed = (
            inventory.target.root,
            inventory.roots.codex,
            inventory.roots.claude,
            *inventory.roots.additional,
            claude_state_path(inventory.roots),
        )
        if not within(path, allowed):
            raise BlockedSource("outside-authorized-roots")
        content = read_source_bytes(path).decode("utf-8-sig")
        if path == resolve_local(claude_state_path(inventory.roots)):
            selected = build_claude_state_view(content, inventory.target.root).configuration
            return json.loads(redact(json.dumps(selected), ".json")[0])
        content, _ = redact(content, path.suffix)
        value = tomllib.loads(content) if path.suffix == ".toml" else json.loads(content)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError) as exc:
        inventory.gaps.append(f"Configuration metadata unavailable: {path}: {type(exc).__name__}")
        return {}


def discover_sources(
    target: Target, roots: SourceRoots, knowledge: KnowledgeBundle | None = None
) -> Inventory:
    inventory = Inventory(target, roots)
    target_root = resolve_local(target.root)
    codex_home, claude_home = resolve_local(roots.codex), resolve_local(roots.claude)
    permitted = (
        target_root,
        codex_home,
        claude_home,
        *(resolve_local(p) for p in roots.additional),
    )
    plugin_roots = [
        codex_home / "plugins",
        claude_home / "plugins",
        Path(__file__).resolve().parents[2],
    ]
    seen: dict[tuple[Path, str], SourceRecord] = {}
    texts: dict[str, str] = {}

    def exclude(path: Path, reason: str) -> None:
        entry = {"path": str(path), "reason": reason}
        if entry not in inventory.exclusions:
            inventory.exclusions.append(entry)
        if reason in {"outside-authorized-roots", "network-path", "symlink-cycle"}:
            gap = f"Potential context could not be verified: {path}: {reason}"
            if gap not in inventory.gaps:
                inventory.gaps.append(gap)

    def classify(path: Path) -> Path:
        canonical = resolve_local(path)
        if within(canonical, plugin_roots):
            raise BlockedSource("plugin-provided")
        if within(canonical, MANAGED) or canonical.name.startswith("managed-"):
            raise BlockedSource("managed")
        skill_roots = (
            codex_home / "skills",
            claude_home / "skills",
            roots.user_home / ".agents/skills",
        )
        native_skill_path = any(
            canonical.parts[i : i + 2]
            in {(".agents", "skills"), (".claude", "skills"), (".codex", "skills")}
            for i in range(len(canonical.parts) - 1)
        )
        if canonical.name == "SKILL.md" or within(canonical, skill_roots) or native_skill_path:
            raise BlockedSource("skill-package")
        if not within(canonical, permitted):
            raise BlockedSource("outside-authorized-roots")
        return canonical

    # Local-linked installs can live outside the cache. Only path fields are used.
    for record in (
        codex_home / "plugins/installed_plugins.json",
        claude_home / "plugins/installed_plugins.json",
    ):
        if record.is_file():
            data = _config(record, inventory)

            def register(value: object) -> None:
                if isinstance(value, dict):
                    for key, item in value.items():
                        if key in {"installPath", "install_path"} and isinstance(item, str):
                            try:
                                plugin_roots.append(resolve_local(Path(item)))
                            except (ValueError, OSError):
                                inventory.gaps.append("Unresolvable installed-plugin provenance")
                        elif isinstance(item, (dict, list)):
                            register(item)
                elif isinstance(value, list):
                    for item in value:
                        register(item)

            register(data)

    def add(
        path: Path,
        scope: str,
        domain: str,
        hosts: list[str],
        mode: str = "always",
        depth: int = 0,
        chain: tuple[Path, ...] = (),
    ) -> SourceRecord | None:
        canonical = path.absolute()
        try:
            canonical = classify(path)
            if not canonical.is_file():
                return None
            key = (path, domain)
            if key in seen:
                existing = seen[key]
                existing.hosts = sorted(set(existing.hosts + hosts))
                return existing
            raw = read_source_bytes(canonical)
            text = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
            state_view = None
            if canonical == resolve_local(claude_state_path(roots)):
                state_view = build_claude_state_view(text, target.root)
                if not state_view.configuration:
                    return None
                text = state_view.text
        except BlockedSource as exc:
            exclude(path, str(exc))
            return None
        except (OSError, UnicodeError, ValueError) as exc:
            inventory.gaps.append(f"Unreadable source: {path}: {type(exc).__name__}")
            source_id = "src-" + hashlib.sha256(f"{domain}:{path}".encode()).hexdigest()[:20]
            record = SourceRecord(source_id, path, canonical, scope, domain, hosts, mode)
            record.status = "unreadable"
            record.reason = type(exc).__name__
            seen[(path, domain)] = record
            inventory.sources.append(record)
            return None
        label = next(
            (
                f"{prefix}:{path.relative_to(base).as_posix()}"
                for prefix, base in (
                    ("repo", target.root),
                    ("codex-user", roots.codex),
                    ("claude-user", roots.claude),
                )
                if path.is_relative_to(base)
            ),
            str(path),
        )
        source_id = "src-" + hashlib.sha256(f"{domain}:{label}".encode()).hexdigest()[:20]
        record = SourceRecord(source_id, path, canonical, scope, domain, hosts, mode)
        record.sha256 = state_view.digest if state_view else hashlib.sha256(raw).hexdigest()
        if state_view:
            record.reason = "Filtered Claude MCP view; original line coordinates retained"
            record.redacted_lines = state_view.redacted_lines
        record.line_count = len(text.splitlines())
        record.byte_count = len(raw)
        record.contexts = [f"{host}:{scope}:{mode}" for host in hosts]
        seen[key] = record
        texts[source_id] = text
        inventory.sources.append(record)
        if "claude" in hosts and (
            domain == "D2" or path.name in {"CLAUDE.md", "CLAUDE.local.md", "AGENTS.md"}
        ):
            stripped = _without_code(text)
            for match in IMPORT.finditer(stripped):
                name = match.group(1).rstrip(".,;:)")
                name = name.replace("\\ ", " ")
                if name.startswith("~/"):
                    imported = roots.user_home / name[2:]
                else:
                    imported = Path(name) if Path(name).is_absolute() else path.parent / name
                line = stripped.count("\n", 0, match.start()) + 1
                reference = Reference(name, line, "claude-import", "resolved")
                record.references.append(reference)
                try:
                    imported_real = classify(imported)
                    reference.resolved = str(imported_real)
                    if imported_real in (*chain, canonical):
                        reference.state = "cycle"
                    elif depth >= 4:
                        reference.state = "depth-limit"
                    elif not imported_real.is_file():
                        reference.state = "missing"
                    else:
                        add(imported, scope, "D2", ["claude"], mode, depth + 1, (*chain, canonical))
                except BlockedSource as exc:
                    reference.state = f"blocked-{exc}"
                    exclude(imported, str(exc))
                    if str(exc) not in {"secret", "plugin-provided", "skill-package", "managed"}:
                        inventory.gaps.append(f"Unverified external import: {imported}")
                except OSError:
                    reference.state = "unreadable"
                    inventory.gaps.append(f"Unreadable import: {imported}")
        # Local Markdown references are checked, not recursively treated as host imports.
        for match in re.finditer(r"\[[^\]]*\]\(([^)\s]+)(?:\s+[^)]*)?\)", _without_code(text)):
            link = match.group(1)
            line = text.count("\n", 0, match.start()) + 1
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", link):
                record.references.append(Reference(sanitize_urls(link), line, "url", "unverified"))
                continue
            destination = link.split("#", 1)[0]
            if not destination:
                continue
            linked = path.parent / destination
            try:
                resolved = classify(linked)
                state = "resolved" if resolved.exists() else "missing"
                record.references.append(Reference(link, line, "local-link", state, str(resolved)))
            except (BlockedSource, OSError) as exc:
                record.references.append(Reference(link, line, "local-link", f"blocked-{exc}"))
        return record

    def walk(directory: Path):
        stack = [directory]
        visited: set[Path] = set()
        while stack:
            logical = stack.pop()
            try:
                actual = classify(logical)
                if not actual.is_dir() or actual in visited:
                    continue
                visited.add(actual)
                with os.scandir(actual) as entries:
                    children = sorted(entries, key=lambda e: e.name)
                for entry in children:
                    child = logical / entry.name
                    if entry.name in SKIP_DIRS:
                        continue
                    try:
                        resolved = classify(child)
                        if resolved.is_dir():
                            if resolved != target_root and (resolved / ".git").exists():
                                exclude(child, "nested-repository")
                            else:
                                stack.append(child)
                        elif resolved.is_file():
                            yield child
                    except (BlockedSource, OSError) as exc:
                        exclude(child, str(exc))
            except BlockedSource as exc:
                exclude(logical, str(exc))
            except OSError as exc:
                inventory.gaps.append(f"Directory unavailable: {logical}: {type(exc).__name__}")

    project_files = list(walk(target.root))
    inventory.repository_files = sorted(
        str(path.relative_to(target.root)) for path in project_files if path.name != ".DS_Store"
    )
    config = _config(codex_home / "config.toml", inventory)
    config.update(_config(target.root / ".codex/config.toml", inventory))
    fallback = config.get("project_doc_fallback_filenames", [])
    if not isinstance(fallback, list):
        inventory.gaps.append(
            "Configured fallback filenames are not an array; intended fallback scope is unverified"
        )
        fallback = []
    elif any(not isinstance(value, str) or Path(value).name != value for value in fallback):
        inventory.gaps.append(
            "A configured fallback filename is not a supported basename; "
            "its loading scope is unverified"
        )
    fallback_names = [v for v in fallback if isinstance(v, str) and Path(v).name == v]
    conditional_fallbacks: set[str] = set()

    def extra_fallbacks(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "project_doc_fallback_filenames" and isinstance(item, list):
                    conditional_fallbacks.update(
                        name for name in item if isinstance(name, str) and Path(name).name == name
                    )
                elif isinstance(item, dict):
                    extra_fallbacks(item)

    extra_fallbacks(config.get("profiles", {}))
    for configuration in project_files:
        if configuration.name == "config.toml" and configuration.parent.name == ".codex":
            extra_fallbacks(_config(configuration, inventory))
    conditional_fallbacks.difference_update(fallback_names)
    codex_names = {"AGENTS.md", "AGENTS.override.md", *fallback_names}
    codex_names.update(conditional_fallbacks)
    for filename in ("AGENTS.override.md", "AGENTS.md", "config.toml", "hooks.json"):
        add(roots.codex / filename, "user", "D1" if filename.endswith(".md") else "D4", ["codex"])
    codex_files = [
        path
        for name in ("agents", "rules", "memories", "memories_v2")
        for path in walk(roots.codex / name)
    ]
    codex_files.extend(roots.codex.glob("*.config.toml"))
    for path in codex_files:
        relative = path.relative_to(roots.codex)
        if relative.parts[0] in {"agents", "rules"}:
            add(
                path,
                "user",
                "D3" if relative.parts[0] == "agents" else "D4",
                ["codex"],
                "on-demand",
            )
        elif relative.parts[0] in {"memories", "memories_v2"} and path.suffix == ".md":
            add(path, "user", "D1", ["codex"], "conditional")
        elif path.parent == roots.codex and path.name.endswith(".config.toml"):
            add(path, "user", "D4", ["codex"], "conditional")

    claude_candidates: list[Path] = []
    global_claude = claude_state_path(roots)
    permitted = (*permitted, global_claude)
    add(global_claude, "user", "D4", ["claude"], "config-only")
    for filename in ("CLAUDE.md", "settings.json", "settings.local.json"):
        item = add(
            roots.claude / filename, "user", "D2" if filename.endswith(".md") else "D4", ["claude"]
        )
        if item:
            claude_candidates.append(item.path)
    claude_files = [
        path
        for name in (
            "rules",
            "agent-memory",
            "agent-memory-local",
            "agents",
            "commands",
            "workflows",
            "output-styles",
        )
        for path in walk(roots.claude / name)
    ]
    for path in claude_files:
        rel = path.relative_to(roots.claude)
        head = rel.parts[0]
        if head in {"rules", "agent-memory", "agent-memory-local"} and path.suffix == ".md":
            add(path, "user", "D2", ["claude"], "conditional" if head == "rules" else "on-demand")
            claude_candidates.append(path)
        elif head in {"agents", "commands", "workflows", "output-styles"}:
            add(path, "user", "D3", ["claude"], "on-demand")
            claude_candidates.append(path)
    # Project memory uses the encoded project path; do not scan unrelated project histories.
    memory_root = target_root
    git_entry = target_root / ".git"
    if git_entry.is_file():
        try:
            pointer = read_source_bytes(git_entry).decode().strip()
            if pointer.startswith("gitdir: "):
                gitdir = resolve_local(target_root / pointer[8:])
                common_file = gitdir / "commondir"
                if common_file.is_file():
                    common = resolve_local(gitdir / read_source_bytes(common_file).decode().strip())
                    memory_root = common.parent
        except (OSError, ValueError, UnicodeError):
            inventory.gaps.append("Shared-worktree memory identity could not be verified")
    project_slug = re.sub(r"[^a-zA-Z0-9]", "-", str(memory_root))
    configured_slug = os.environ.get("CLAUDE_CODE_PROJECT_DIR_NAME")
    if os.environ.get("CLAUDE_CONFIG_DIR") and configured_slug:
        if Path(configured_slug).name == configured_slug and configured_slug not in {".", ".."}:
            project_slug = configured_slug
        else:
            inventory.gaps.append("Unsafe CLAUDE_CODE_PROJECT_DIR_NAME cannot select a memory root")
    memory_dirs = [roots.claude / "projects" / project_slug / "memory"]
    claude_config = _config(roots.claude / "settings.json", inventory)
    for settings in (
        target.root / ".claude/settings.json",
        target.root / ".claude/settings.local.json",
    ):
        claude_config.update(_config(settings, inventory))
    memory_dir = claude_config.get("autoMemoryDirectory")
    if isinstance(memory_dir, str):
        candidate = (
            roots.user_home / memory_dir[2:] if memory_dir.startswith("~/") else Path(memory_dir)
        )
        if candidate.is_absolute():
            memory_dirs.append(candidate)
        else:
            inventory.gaps.append("autoMemoryDirectory must be absolute or start with ~/")
    for directory in memory_dirs:
        for path in walk(directory):
            if path.suffix == ".md":
                add(path, "project-memory", "D2", ["claude"], "on-demand")
                claude_candidates.append(path)
    for path in project_files:
        relative = path.relative_to(target.root)
        parts = relative.parts
        if path.name in codex_names:
            add(
                path,
                "project",
                "D1",
                ["codex"],
                "always"
                if path.parent == target.root and path.name not in conditional_fallbacks
                else "conditional",
            )
        if path.name in {"CLAUDE.md", "CLAUDE.local.md"}:
            add(
                path,
                "project",
                "D2",
                ["claude"],
                "always"
                if path.parent in {target.root, target.root / ".claude"}
                else "conditional",
            )
            claude_candidates.append(path)
        if ".codex" in parts:
            host_index = parts.index(".codex")
            tail = parts[host_index + 1 :]
            if tail and tail[0] in {"agents", "rules"}:
                add(path, "project", "D3" if tail[0] == "agents" else "D4", ["codex"], "on-demand")
            elif path.name in {"config.toml", "hooks.json"}:
                add(path, "project", "D4", ["codex"], "conditional")
        if ".claude" in parts:
            host_index = parts.index(".claude")
            tail = parts[host_index + 1 :]
            if (
                tail
                and tail[0] in {"rules", "agent-memory", "agent-memory-local"}
                and path.suffix == ".md"
            ):
                add(path, "project", "D2", ["claude"], "conditional")
                claude_candidates.append(path)
            elif tail and tail[0] in {"agents", "commands", "workflows", "output-styles"}:
                add(path, "project", "D3", ["claude"], "on-demand")
                claude_candidates.append(path)
            elif path.name in {"settings.json", "settings.local.json"}:
                add(path, "project", "D4", ["claude"], "conditional")
                claude_candidates.append(path)
        if path.name == ".mcp.json" or path.name == ".worktreeinclude":
            add(path, "project", "D4", ["claude"], "config-only")
            claude_candidates.append(path)
        if relative.as_posix() == ".agents/plugins/marketplace.json":
            add(path, "project", "D4", ["codex"], "config-only")

    # Claude's ancestors are different from Codex's project-root chain.
    for ancestor in target.root.parents:
        for name in ("CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md"):
            candidate = ancestor / name
            if candidate.is_file():
                # Only explicit native ancestor instruction files are eligible here.
                permitted = (*permitted, candidate)
                add(candidate, "ancestor", "D2", ["claude"])
                claude_candidates.append(candidate)
    claude_present = bool(claude_candidates) or bool(
        knowledge and knowledge.data.get("claude_present")
    )
    if claude_present and not any(
        p.name in {"CLAUDE.md", "CLAUDE.local.md"}
        and (
            p.parent == target.root
            or p.parent == target.root / ".claude"
            or p.parent in target.root.parents
        )
        for p in claude_candidates
    ):
        for path in project_files:
            if path.name == "AGENTS.md":
                add(path, "project", "D2", ["claude"], "conditional")

    # Inspect literal helper paths declared by configuration, never execute commands.
    expanded_configurations: set[tuple[Path, str]] = set()
    for source in inventory.sources:
        if source.domain not in {"D3", "D4"} or source.path.suffix not in {".toml", ".json"}:
            continue
        identity = (source.canonical_path, source.domain)
        if identity in expanded_configurations:
            continue
        expanded_configurations.add(identity)
        configuration = _config(source.path, inventory)
        declared: list[tuple[str, str]] = []

        def paths_in(
            value: object,
            declared: list[tuple[str, str]],
            source_path: Path,
            hosts=tuple(source.hosts),
        ) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == "model_instructions_file" and isinstance(item, str):
                        declared.append((item, "instruction-file"))
                    elif key == "config_file" and isinstance(item, str) and "codex" in hosts:
                        declared.append((item, "agent-config"))
                    elif key == "command" and isinstance(item, str):
                        try:
                            tokens = shlex.split(item)
                            if not any(token in {"-c", "-e", "--eval"} for token in tokens):
                                declared.extend(
                                    (token, "configured-helper")
                                    for token in tokens
                                    if Path(token).suffix in {".py", ".sh", ".js", ".mjs", ".ts"}
                                )
                        except ValueError:
                            inventory.gaps.append(f"Unparseable helper command in {source_path}")
                    elif key == "args" and isinstance(item, list):
                        declared.extend(
                            (token, "configured-helper")
                            for token in item
                            if isinstance(token, str)
                            and Path(token).suffix in {".py", ".sh", ".js", ".mjs", ".ts"}
                        )
                    elif key not in {"env", "headers", "auth", "oauthAccount"}:
                        paths_in(item, declared, source_path)
            elif isinstance(value, list):
                for item in value:
                    paths_in(item, declared, source_path)

        paths_in(configuration, declared, source.path)
        for literal, kind in declared:
            resolved_text = literal.replace("${CODEX_HOME}", str(roots.codex))
            resolved_text = resolved_text.replace("${CLAUDE_CONFIG_DIR}", str(roots.claude))
            resolved_text = resolved_text.replace("${HOME}", str(roots.user_home))
            if resolved_text.startswith("~/"):
                resolved_text = str(roots.user_home / resolved_text[2:])
            line = (
                texts.get(source.source_id, "").count(
                    "\n", 0, max(0, texts.get(source.source_id, "").find(literal))
                )
                + 1
            )
            if "$" in resolved_text or "://" in resolved_text:
                source.references.append(Reference(literal, line, kind, "dynamic-unverified"))
                continue
            declared_path = Path(resolved_text)
            if not declared_path.is_absolute():
                base = (
                    source.path.parent
                    if kind in {"instruction-file", "agent-config"}
                    else target.cwd
                )
                declared_path = base / declared_path
            try:
                actual = classify(declared_path)
                state = "resolved" if actual.is_file() else "missing"
                source.references.append(Reference(literal, line, kind, state, str(actual)))
                if state == "resolved":
                    add(
                        declared_path,
                        source.scope,
                        "D1"
                        if kind == "instruction-file"
                        else "D3"
                        if kind == "agent-config"
                        else "D4",
                        source.hosts,
                        "config-only",
                    )
                elif kind == "agent-config":
                    inventory.gaps.append(f"Configured agent file is unavailable: {declared_path}")
            except (BlockedSource, OSError) as exc:
                source.references.append(Reference(literal, line, kind, f"blocked-{exc}"))
                inventory.gaps.append(f"Helper reference not verified: {declared_path}")

    # Preserve shadowed files as audit candidates, with the actual selected loader noted.
    for source in inventory.sources:
        if source.domain != "D1" or source.path.name not in codex_names:
            continue
        if source.path.name in conditional_fallbacks:
            source.reason = (
                "Configured by a nested layer or profile; activation depends on invocation"
            )
            continue
        priority = ["AGENTS.override.md", "AGENTS.md", *fallback_names]
        for name in priority:
            active = seen.get((source.path.parent / name, "D1"))
            if active and texts.get(active.source_id, "").strip():
                if active.path != source.path:
                    source.load_mode = "dead"
                    source.reason = f"Shadowed by {active.path.name} override/fallback precedence"
                break
    inventory.sources.sort(key=lambda s: (str(s.path), s.domain))
    return inventory
