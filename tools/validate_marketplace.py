"""Validate every marketplace entry before packaging or installation."""

import json
import re
from pathlib import Path

import yaml


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
        try:
            manifest = json.loads((path / "plugin.json").read_text())
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
        skills = list((path / "skills").glob("*/SKILL.md"))
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
