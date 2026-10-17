"""Validate every marketplace entry before packaging or installation."""

import json
import re
from pathlib import Path

import yaml


def contained_resource(
    plugin: Path, value: object, label: str, errors: list[str], *, directory: bool = False
) -> Path | None:
    """Resolve packaged resources without following symlinks or accepting escapes."""
    if not isinstance(value, str) or not value.startswith("./"):
        errors.append(f"{label}: resource must start with ./")
        return None
    relative = Path(value)
    candidate = plugin / relative
    if ".." in relative.parts or not candidate.resolve().is_relative_to(plugin.resolve()):
        errors.append(f"{label}: resource path escape")
        return None
    if any(part.is_symlink() for part in [candidate, *candidate.parents] if part != plugin.parent):
        errors.append(f"{label}: resource symlink")
        return None
    if not (candidate.is_dir() if directory else candidate.is_file()):
        errors.append(f"{label}: missing resource {value}")
        return None
    return candidate


def validate_hooks(plugin: Path, declaration: object, label: str, errors: list[str]) -> None:
    """Validate hook files/inline definitions and packaged script references, never execute them."""
    if isinstance(declaration, list):
        for value in declaration:
            validate_hooks(plugin, value, label, errors)
        return
    if isinstance(declaration, str):
        resource = contained_resource(plugin, declaration, label, errors)
        if resource is None:
            return
        try:
            config = json.loads(resource.read_text())
        except (OSError, ValueError) as exc:
            errors.append(f"{label}: unreadable hooks: {exc}")
            return
    else:
        config = declaration
    if not isinstance(config, dict) or not isinstance(config.get("hooks"), dict):
        errors.append(f"{label}: invalid hooks object")
        return
    for groups in config["hooks"].values():
        if not isinstance(groups, list):
            errors.append(f"{label}: invalid hook groups")
            continue
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                errors.append(f"{label}: invalid hook group")
                continue
            for handler in group["hooks"]:
                if not isinstance(handler, dict):
                    errors.append(f"{label}: invalid hook handler")
                    continue
                command = handler.get("command")
                if handler.get("type") == "command" and not isinstance(command, str):
                    errors.append(f"{label}: missing hook command")
                if isinstance(command, str):
                    for match in re.finditer(r'\$\{PLUGIN_ROOT\}/([^\s"\x27]+)', command):
                        contained_resource(plugin, "./" + match[1], label, errors)


def validate_marketplace(root: Path) -> list[str]:
    """Return validation errors for a marketplace root."""
    errors: list[str] = []
    root = root.resolve()
    try:
        catalog = json.loads((root / ".agents/plugins/marketplace.json").read_text())
    except (OSError, ValueError) as exc:
        return [f"catalog: {exc}"]
    names: set[str] = set()
    entries = catalog.get("plugins", [])
    if not entries:
        errors.append("catalog: no plugins")
    for entry in entries:
        name = entry.get("name", "")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or name in names:
            errors.append(f"catalog: invalid or duplicate name {name!r}")
        names.add(name)
        source = entry.get("source", {})
        source_path = source if isinstance(source, str) else source.get("path", "")
        path = (root / source_path).resolve()
        if not source_path.startswith("./") or not path.is_relative_to(root):
            errors.append(f"{name}: source path escape")
            continue
        for field in ("installation", "authentication"):
            if field not in entry.get("policy", {}):
                errors.append(f"{name}: missing policy.{field}")
        if not entry.get("category"):
            errors.append(f"{name}: missing category")
        native_metadata = path / "metadata/plugin.json"
        root_manifest = path / "plugin.json"
        if native_metadata.exists() and root_manifest.exists():
            errors.append(f"{name}: native metadata layout requires absent root plugin.json")
        canonical = "./plugin.json" if root_manifest.exists() else "./metadata/plugin.json"
        canonical_path = contained_resource(path, canonical, f"{name}: manifest", errors)
        if canonical_path is None:
            continue
        try:
            manifest = json.loads(canonical_path.read_text())
            overlay = json.loads((path / ".codex-plugin/plugin.json").read_text())
        except (OSError, ValueError) as exc:
            errors.append(f"{name}: manifest/overlay unreadable: {exc}")
            continue
        if manifest.get("name") != name:
            errors.append(f"{name}: catalog identity differs from manifest")
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?", manifest.get("version", "")):
            errors.append(f"{name}: invalid version")
        for field in ("name", "version", "description", "author", "license"):
            if overlay.get(field) != manifest.get(field):
                errors.append(f"{name}: overlay {field} differs from canonical manifest")
        extension = manifest.get("extensions", {}).get("com.openai", {})
        for field in ("hooks", "interface"):
            if overlay.get(field) != extension.get(field):
                errors.append(f"{name}: overlay {field} differs from canonical manifest")
        skills_directory = contained_resource(
            path, overlay.get("skills", "./skills/"), f"{name}: skills", errors, directory=True
        )
        hook_declaration = extension.get("hooks")
        if hook_declaration is None and (path / "hooks/hooks.json").exists():
            hook_declaration = "./hooks/hooks.json"
        if hook_declaration is not None:
            validate_hooks(path, hook_declaration, f"{name}: hooks", errors)
        skills = list(skills_directory.glob("*/SKILL.md")) if skills_directory is not None else []
        if not skills:
            errors.append(f"{name}: no skill entrypoint")
        for skill in skills:
            if not skill.resolve().is_relative_to(path):
                errors.append(f"{name}: skill path escape")
                continue
            text = skill.read_text()
            try:
                metadata = (
                    yaml.safe_load(text.split("---", 2)[1]) if text.startswith("---\n") else {}
                )
                if not isinstance(metadata, dict) or not all(
                    metadata.get(k) for k in ("name", "description")
                ):
                    errors.append(f"{name}: invalid skill metadata: {skill.name}")
            except (IndexError, yaml.YAMLError):
                errors.append(f"{name}: invalid skill frontmatter")
    return errors


if __name__ == "__main__":
    import sys

    problems = validate_marketplace(Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd())
    for problem in problems:
        print(problem)
    print(f"Marketplace validation: {'FAIL' if problems else 'PASS'}")
    raise SystemExit(1 if problems else 0)
