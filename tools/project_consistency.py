"""Project-specific consistency audit; targets are data, never executable helpers."""

import argparse
import hashlib
import json
import re
import tempfile
import tomllib
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from tools.package_plugin import package_plugin
from tools.validate_marketplace import validate_marketplace

IGNORED = {
    ".git",
    ".superpowers",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".DS_Store",
}
SEMVER = r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?"


def private_path(path: Path) -> bool:
    """Check names only; never open environment/auth/key files."""
    return any(
        (part.startswith(".env") and part != ".env.example")
        or part.startswith(".dev.vars")
        or part
        in {
            "auth.json",
            "credentials.json",
            "id_rsa",
            "id_ed25519",
            ".npmrc",
            ".netrc",
            ".pypirc",
            ".git-credentials",
            "application_default_credentials.json",
        }
        or part.endswith((".pem", ".key", ".p12"))
        for part in path.parts
    )


def strict_json(text: str) -> object:
    def pairs(values: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in values:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(text, object_pairs_hook=pairs)


def strict_yaml(text: str) -> object:
    visited: set[int] = set()

    def inspect(node: yaml.Node | None, depth: int = 0) -> None:
        if node is None or id(node) in visited:
            return
        if depth > 64:
            raise ValueError("YAML nesting exceeds limit")
        visited.add(id(node))
        if isinstance(node, yaml.MappingNode):
            keys: set[str] = set()
            for key, value in node.value:
                if not isinstance(key, yaml.ScalarNode) or key.value in keys:
                    raise ValueError("Duplicate/non-scalar YAML key")
                keys.add(key.value)
                inspect(value, depth + 1)
        elif isinstance(node, yaml.SequenceNode):
            for child in node.value:
                inspect(child, depth + 1)

    inspect(yaml.compose(text))
    return yaml.safe_load(text)


@dataclass
class Finding:
    code: str
    path: str
    message: str
    severity: str = "error"


@dataclass
class AuditReport:
    root: str
    findings: list[Finding] = field(default_factory=list)
    packages: dict = field(default_factory=dict)
    reviewed_files: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "BLOCKED" if any(f.severity == "error" for f in self.findings) else "PASS"

    def to_dict(self) -> dict:
        return {"status": self.status, **asdict(self)}


def audit_project(root: Path, *, build_packages: bool = True) -> AuditReport:
    root = root.resolve()
    report = AuditReport(str(root))

    def finding(code: str, path: Path, message: str, severity: str = "error") -> None:
        location = str(path.relative_to(root)) if path.is_relative_to(root) else path.name
        report.findings.append(Finding(code, location, message, severity))

    def read(path: Path) -> str | None:
        if private_path(path.relative_to(root)):
            finding(
                "private-file", path, "Credential/environment file is prohibited; content not read."
            )
            return None
        if not path.resolve().is_relative_to(root) or any(
            (root.joinpath(*path.relative_to(root).parts[:i])).is_symlink()
            for i in range(1, len(path.relative_to(root).parts) + 1)
        ):
            finding("resource-escape", path, "Symlinked/escaping audit resource; content not read.")
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            finding("invalid-document", path, "Missing, unreadable or non-UTF-8 document.")
            return None
        relative_name = path.relative_to(root).as_posix()
        if relative_name not in report.reviewed_files:
            report.reviewed_files.append(relative_name)
        return text

    def document(path: Path) -> dict | None:
        text = read(path)
        if text is None:
            return None
        try:
            data = strict_json(text)
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object")
        except ValueError as exc:
            finding("invalid-document", path, str(exc))
            return None
        return data

    catalog_path = root / ".agents/plugins/marketplace.json"
    catalog = document(catalog_path)
    if catalog is None:
        return report
    entries = catalog.get("plugins")
    if not isinstance(catalog.get("name"), str) or not isinstance(entries, list) or not entries:
        finding(
            "catalog-fields", catalog_path, "Catalog requires a name and nonempty plugins array."
        )
        return report
    if any(
        not isinstance(e, dict)
        or not isinstance(e.get("name"), str)
        or not isinstance(e.get("source"), (dict, str))
        or not isinstance(e.get("policy"), dict)
        for e in entries
    ):
        finding("catalog-fields", catalog_path, "Malformed catalog entry fields/types.")
        return report
    root_readme = read(root / "README.md") or ""
    registered = {e["name"] for e in entries}
    plugins_root = root / "plugins"
    if plugins_root.is_dir():
        for plugin in plugins_root.iterdir():
            if (
                plugin.is_dir()
                and not plugin.name.startswith(".")
                and plugin.name not in registered
            ):
                finding(
                    "unregistered-plugin", plugin, "Plugin directory is absent from the catalog."
                )
    unsafe = False
    if plugins_root.exists():
        for path in plugins_root.rglob("*"):
            relative = path.relative_to(root)
            if any(part in IGNORED for part in relative.parts):
                continue
            if private_path(relative) or path.is_symlink():
                unsafe = True
                finding(
                    "private-file" if private_path(relative) else "resource-escape",
                    path,
                    "Prohibited path; content not read.",
                )
    if unsafe:
        return report
    runtime_toml: dict[Path, dict] = {}
    for path in plugins_root.rglob("*"):
        if not path.is_file() or any(part in IGNORED for part in path.relative_to(root).parts):
            continue
        if path.suffix != ".toml" and path.name != "uv.lock":
            continue
        text = read(path)
        if text is None:
            continue
        try:
            runtime_toml[path] = tomllib.loads(text)
        except ValueError:
            finding("invalid-document", path, "Plugin runtime TOML/lock syntax is invalid.")
    for path in plugins_root.rglob("*.json"):
        if any(part in IGNORED for part in path.relative_to(root).parts):
            continue
        text = read(path)
        if text is None:
            continue
        try:
            value = strict_json(text)
        except ValueError:
            finding("invalid-document", path, "Invalid JSON or duplicate keys.")
            continue
        if "hooks" not in path.relative_to(plugins_root).parts:
            continue
        if not isinstance(value, dict) or not isinstance(value.get("hooks"), dict):
            finding("hook-fields", path, "Hook configuration requires a hooks object.")
            continue
        for groups in value["hooks"].values():
            if not isinstance(groups, list):
                finding("hook-fields", path, "Hook groups must be arrays.")
                continue
            for group in groups:
                if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                    finding("hook-fields", path, "Invalid hook group.")
                    continue
                matcher = group.get("matcher", "")
                try:
                    if not isinstance(matcher, str):
                        raise ValueError("Invalid matcher")
                    if matcher not in ("", "*"):
                        re.compile(matcher)
                except (ValueError, re.error):
                    finding("hook-fields", path, "Invalid hook matcher.")
                for handler in group["hooks"]:
                    if (
                        not isinstance(handler, dict)
                        or not isinstance(handler.get("type"), str)
                        or handler.get("type")
                        not in {
                            "command",
                            "mcp_tool",
                        }
                    ):
                        finding("hook-fields", path, "Unsupported/skipped native hook handler.")
                        continue
                    required = ("command",) if handler["type"] == "command" else ("server", "tool")
                    if any(
                        not isinstance(handler.get(k), str) or not handler[k].strip()
                        for k in required
                    ):
                        finding("hook-fields", path, "Missing native hook command/tool.")
    try:
        for issue in validate_marketplace(root):
            finding("marketplace", catalog_path, issue)
    except (AttributeError, TypeError, ValueError, OSError):
        finding("invalid-document", catalog_path, "Malformed metadata prevented base validation.")

    for entry in entries:
        name = entry["name"]
        policy = entry["policy"]
        if (
            not isinstance(entry.get("category"), str)
            or not entry["category"].strip()
            or (isinstance(entry["source"], dict) and entry["source"].get("source") != "local")
        ):
            finding("catalog-fields", catalog_path, f"{name}: invalid category/local source type.")
        if (
            not isinstance(policy.get("installation"), str)
            or policy.get("installation")
            not in {
                "NOT_AVAILABLE",
                "AVAILABLE",
                "INSTALLED_BY_DEFAULT",
            }
            or not isinstance(policy.get("authentication"), str)
            or policy.get("authentication") not in {"ON_INSTALL", "ON_USE"}
        ):
            finding("catalog-fields", catalog_path, f"{name}: invalid native policy enum values.")
        source = entry["source"]
        source_path = source if isinstance(source, str) else source.get("path")
        if (
            not isinstance(source_path, str)
            or source_path != f"./plugins/{name}"
            or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)
        ):
            finding("plugin-identity", catalog_path, "Catalog name/path must match plugins/<slug>.")
            continue
        plugin = root / "plugins" / name
        canonical_path = plugin / "plugin.json"
        if not canonical_path.exists():
            canonical_path = plugin / "metadata/plugin.json"
        canonical = document(canonical_path)
        native = document(plugin / ".codex-plugin/plugin.json")
        documents: dict[str, str] = {}
        for filename in ("README.md", "LICENSE", "CHANGELOG.md"):
            text = read(plugin / filename)
            if not text or not text.strip():
                finding(
                    "required-document", plugin / filename, "Required nonempty plugin document."
                )
            else:
                documents[filename] = text
        if canonical is None or native is None:
            continue
        supported_portable = {
            "$schema",
            "name",
            "version",
            "description",
            "author",
            "homepage",
            "repository",
            "license",
            "keywords",
            "extensions",
        }
        if canonical.keys() - supported_portable:
            finding(
                "manifest-fields",
                canonical_path,
                f"Unknown portable fields: {sorted(canonical.keys() - supported_portable)}",
            )
        keywords = canonical.get("keywords", [])
        if not isinstance(keywords, list) or any(not isinstance(k, str) for k in keywords):
            finding("manifest-fields", canonical_path, "keywords must be an array of strings.")
        for key in ("name", "version", "description", "license"):
            if not isinstance(canonical.get(key), str) or not canonical[key].strip():
                finding("manifest-fields", canonical_path, f"{key} must be a nonempty string.")
        version = canonical.get("version")
        if not isinstance(version, str) or not re.fullmatch(SEMVER, version):
            finding("manifest-version", canonical_path, "Invalid semantic version.")
            continue
        if canonical.get("$schema") != "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json":
            finding("manifest-schema", canonical_path, "Unexpected portable manifest schema.")
        forbidden = {"skills", "mcpServers", "apps", "interface"} & canonical.keys()
        if forbidden:
            finding(
                "manifest-fields",
                canonical_path,
                f"Host fields belong in the OpenAI extension: {sorted(forbidden)}",
            )
        author = canonical.get("author")
        if not isinstance(author, dict) or not isinstance(author.get("name"), str):
            finding("manifest-fields", canonical_path, "author.name must be a string.")
        for key in (
            "name",
            "version",
            "description",
            "author",
            "license",
            "homepage",
            "repository",
        ):
            if canonical.get(key) != native.get(key):
                finding("manifest-alignment", canonical_path, f"Native/canonical {key} differs.")
        extension = canonical.get("extensions", {})
        extension = extension.get("com.openai", {}) if isinstance(extension, dict) else None
        if not isinstance(extension, dict):
            finding("manifest-fields", canonical_path, "OpenAI extension must be an object.")
            continue
        for key in ("interface", "hooks", "apps"):
            if extension.get(key) != native.get(key):
                finding("manifest-alignment", canonical_path, f"OpenAI/native {key} differs.")
        interface = extension.get("interface", {})
        if not isinstance(interface, dict):
            finding("manifest-fields", canonical_path, "interface must be an object.")
        else:
            supported = {
                "displayName",
                "shortDescription",
                "longDescription",
                "developerName",
                "category",
                "capabilities",
                "defaultPrompt",
                "websiteURL",
                "privacyPolicyURL",
                "termsOfServiceURL",
                "supportURL",
                "logo",
                "logoDark",
                "composerIcon",
                "composerIconDark",
                "screenshots",
                "brandColor",
                "brandColorDark",
            }
            if interface.keys() - supported:
                finding(
                    "manifest-fields",
                    canonical_path,
                    f"Unsupported interface fields: {sorted(interface.keys() - supported)}",
                )
            for key, value in interface.items():
                if key == "capabilities" and (
                    not isinstance(value, list)
                    or any(not isinstance(v, str) or not v.strip() for v in value)
                ):
                    finding("manifest-fields", canonical_path, "capabilities must be string array.")
                if key in {
                    "displayName",
                    "shortDescription",
                    "longDescription",
                    "developerName",
                    "category",
                } and (not isinstance(value, str) or not value.strip()):
                    finding("manifest-fields", canonical_path, f"Invalid interface.{key}.")
            short = interface.get("shortDescription")
            if isinstance(short, str) and len(short) > 30:
                finding("listing-length", canonical_path, "shortDescription exceeds 30 characters.")
        matching_rows = [
            line for line in root_readme.splitlines() if f"](plugins/{name}/README.md)" in line
        ]
        if len(matching_rows) != 1:
            finding(
                "readme-catalog",
                root / "README.md",
                f"{name} needs exactly one linked catalog entry.",
            )
        elif version not in matching_rows[0]:
            finding(
                "readme-version",
                root / "README.md",
                f"{name} catalog version does not match {version}.",
            )
        if len(matching_rows) == 1 and isinstance(interface, dict):
            display = interface.get("displayName")
            label = re.search(r"\[([^\]]+)\]\(plugins/", matching_rows[0])
            if (
                isinstance(display, str)
                and label
                and (
                    "".join(c for c in display if c.isalnum()).casefold()
                    != "".join(c for c in label[1] if c.isalnum()).casefold()
                )
            ):
                finding(
                    "readme-identity",
                    root / "README.md",
                    f"{name}: linked display name differs from canonical displayName.",
                )
        license_text = documents.get("LICENSE", "")
        if canonical.get("license") == "MIT":
            if not all(
                t in license_text
                for t in (
                    "MIT License",
                    "Permission is hereby granted",
                    "THE SOFTWARE IS PROVIDED",
                    "Copyright",
                )
            ):
                finding(
                    "license-mismatch", plugin / "LICENSE", "Declared MIT license is incomplete."
                )
        elif license_text:
            finding(
                "license-review",
                plugin / "LICENSE",
                "License identifier/text needs an explicit supported verification rule.",
            )
        changelog = documents.get("CHANGELOG.md", "")
        if changelog and not re.search(
            rf"^##\s+(?:\[?Unreleased\]?|\[?{re.escape(version)}(?:\]|\s|$))",
            changelog,
            re.MULTILINE | re.IGNORECASE,
        ):
            finding(
                "changelog-version",
                plugin / "CHANGELOG.md",
                "No unreleased section or section for the declared version.",
            )
        if build_packages:
            try:
                with tempfile.TemporaryDirectory(prefix="factory-package-") as tmp:
                    first = package_plugin(root, Path(tmp) / "first", name)
                    second = package_plugin(root, Path(tmp) / "second", name)
                    if first.read_bytes() != second.read_bytes():
                        raise ValueError("Package builds differ")
                    prefix = "" if name == "agent-context-audit" else f"{name}-"
                    inventory = (first.parent / f"{prefix}PACKAGE-CONTENTS.txt").read_text()
                    digest = hashlib.sha256(first.read_bytes()).hexdigest()
                    sums = (first.parent / f"{prefix}SHA256SUMS").read_text()
                    if sums != f"{digest}  {first.name}\n":
                        raise ValueError("Package checksum sidecar mismatch")
                    with zipfile.ZipFile(first) as archive:
                        members = archive.namelist()
                        expected = [f"{name}/{p}" for p in inventory.splitlines()]
                        if members != expected or archive.testzip() is not None:
                            raise ValueError("Package inventory/integrity mismatch")
                        for member in members:
                            relative = Path(member).relative_to(name)
                            if archive.read(member) != (plugin / relative).read_bytes():
                                raise ValueError(f"Package/source mismatch: {relative}")
                    report.packages[name] = {
                        "sha256": digest,
                        "files": members,
                        "reproducible": True,
                    }
            except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
                finding("package", plugin, str(exc))

    skill_paths = list(root.glob("plugins/*/skills/*/SKILL.md"))
    skill_paths += list(root.glob(".agents/skills/*/SKILL.md"))
    identities: set[tuple[str, str]] = set()
    for path in skill_paths:
        text = read(path)
        if text is None:
            continue
        try:
            if not text.startswith("---\n"):
                raise ValueError("Frontmatter is missing")
            parts = text.split("---", 2)
            if len(parts) != 3:
                raise ValueError("Frontmatter is unterminated")
            metadata = strict_yaml(parts[1])
            if not isinstance(metadata, dict) or any(
                not isinstance(metadata.get(k), str) or not metadata[k].strip()
                for k in ("name", "description")
            ):
                raise ValueError("name/description must be nonempty strings")
            identity = (str(path.parents[2]), metadata["name"])
            if metadata["name"] != path.parent.name or identity in identities:
                finding(
                    "skill-identity",
                    path,
                    "Skill identity differs from its directory or duplicates.",
                )
            identities.add(identity)
        except (ValueError, yaml.YAMLError):
            finding("skill-frontmatter", path, "Invalid frontmatter fields or types.")
        presentation = path.parent / "agents/openai.yaml"
        if presentation.exists():
            raw = read(presentation)
            try:
                data = strict_yaml(raw or "")
                if not isinstance(data, dict):
                    raise ValueError("Invalid skill interface object")
                interface = data.get("interface")
                if interface is not None and (
                    not isinstance(interface, dict)
                    or any(
                        not isinstance(interface.get(k), str) or not interface[k].strip()
                        for k in ("display_name", "short_description")
                    )
                    or (
                        "default_prompt" in interface
                        and not isinstance(interface["default_prompt"], str)
                    )
                ):
                    raise ValueError("Invalid skill interface fields")
                policy = data.get("policy") or {}
                if not isinstance(policy, dict) or (
                    "allow_implicit_invocation" in policy
                    and policy["allow_implicit_invocation"] is not None
                    and not isinstance(policy["allow_implicit_invocation"], bool)
                ):
                    raise ValueError("Invalid skill invocation policy")
                products = policy.get("products")
                if products is not None and (
                    not isinstance(products, list)
                    or any(
                        not isinstance(p, str) or p not in {"CHAT", "CODEX", "HERMES"}
                        for p in products
                    )
                ):
                    raise ValueError("Invalid skill product policy")
            except (ValueError, yaml.YAMLError):
                finding("skill-interface", presentation, "Invalid native skill interface metadata.")
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
            if "://" in target or target.startswith("#"):
                continue
            linked = path.parent / target.split("#", 1)[0]
            if not linked.resolve().is_relative_to(root) or not linked.is_file():
                finding("resource-link", path, f"Broken or escaping skill link: {target}")
    for path in root.glob(".codex/agents/*.toml"):
        text = read(path)
        if text is None:
            continue
        try:
            data = tomllib.loads(text)
            if any(
                not isinstance(data.get(k), str) or not data[k].strip()
                for k in ("name", "description", "developer_instructions")
            ):
                raise ValueError("Missing native agent fields")
            if data["name"] != path.stem:
                raise ValueError("Agent filename/name mismatch")
            if any(k in data for k in ("sandbox_mode", "approval_policy", "mcp_servers")):
                raise ValueError("Agent settings cannot override inherited permissions/providers")
        except ValueError:
            finding("agent-fields", path, "Invalid native agent identity, fields or settings.")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    report = audit_project(args.root)
    print(json.dumps(report.to_dict(), indent=2))
    raise SystemExit(0 if report.status == "PASS" else 1)


if __name__ == "__main__":
    main()
