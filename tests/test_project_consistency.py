"""Known-answer marketplace discrepancies, independent of the model reviewer."""

import json
import shutil
from pathlib import Path

import pytest

from tools.project_consistency import audit_project

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def marketplace(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    shutil.copytree(ROOT / "plugins/session-handoff", root / "plugins/session-handoff")
    catalog = root / ".agents/plugins/marketplace.json"
    catalog.parent.mkdir(parents=True)
    catalog.write_text(
        json.dumps(
            {
                "name": "the-codex-factory",
                "plugins": [
                    {
                        "name": "session-handoff",
                        "source": {"source": "local", "path": "./plugins/session-handoff"},
                        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                        "category": "Productivity",
                    }
                ],
            }
        )
    )
    (root / "README.md").write_text(
        "| [Session Handoff](plugins/session-handoff/README.md) | 0.1.0 candidate | Handoff |\n"
    )
    return root


def codes(root: Path) -> set[str]:
    return {finding.code for finding in audit_project(root).findings}


def test_coherent_marketplace_passes(marketplace: Path) -> None:
    report = audit_project(marketplace)
    assert report.status == "PASS", report.to_dict()
    assert report.packages["session-handoff"]["reproducible"] is True


@pytest.mark.parametrize("name", ["README.md", "LICENSE", "CHANGELOG.md"])
def test_missing_plugin_document_blocks(marketplace: Path, name: str) -> None:
    (marketplace / "plugins/session-handoff" / name).unlink()
    assert "required-document" in codes(marketplace)
    assert audit_project(marketplace).status == "BLOCKED"


def test_root_readme_catalog_entry_is_required(marketplace: Path) -> None:
    (marketplace / "README.md").write_text("# Factory\n")
    assert "readme-catalog" in codes(marketplace)


def test_root_readme_version_must_match(marketplace: Path) -> None:
    path = marketplace / "README.md"
    path.write_text(path.read_text().replace("0.1.0", "9.9.9"))
    assert "readme-version" in codes(marketplace)


def test_unregistered_plugin_is_not_silently_omitted(marketplace: Path) -> None:
    shutil.copytree(
        marketplace / "plugins/session-handoff", marketplace / "plugins/forgotten-plugin"
    )
    assert "unregistered-plugin" in codes(marketplace)


@pytest.mark.parametrize("value", [None, [], {"name": []}, {"plugins": "invalid"}])
def test_malformed_catalog_returns_findings(marketplace: Path, value: object) -> None:
    (marketplace / ".agents/plugins/marketplace.json").write_text(json.dumps(value))
    assert audit_project(marketplace).status == "BLOCKED"


def test_duplicate_json_keys_are_not_accepted(marketplace: Path) -> None:
    path = marketplace / "plugins/session-handoff/.codex-plugin/plugin.json"
    path.write_text('{"name":"session-handoff","name":"different"}')
    assert "invalid-document" in codes(marketplace)


def test_skill_directory_and_frontmatter_identity_must_match(marketplace: Path) -> None:
    path = marketplace / "plugins/session-handoff/skills/write-handoff/SKILL.md"
    path.write_text(path.read_text().replace("name: write-handoff", "name: wrong-name"))
    assert "skill-identity" in codes(marketplace)


def test_invalid_native_agent_is_flagged(marketplace: Path) -> None:
    path = marketplace / ".codex/agents/auditor.toml"
    path.parent.mkdir(parents=True)
    path.write_text('name = "auditor"\ndescription = 7\n')
    assert "agent-fields" in codes(marketplace)


def test_declared_license_must_match_text(marketplace: Path) -> None:
    (marketplace / "plugins/session-handoff/LICENSE").write_text("Apache License 2.0\n")
    assert "license-mismatch" in codes(marketplace)


def test_credential_filename_is_blocked_without_reading_it(marketplace: Path) -> None:
    path = marketplace / "plugins/session-handoff/.env"
    path.write_text("SYNTHETIC_CANARY=never-read\n")
    report = audit_project(marketplace)
    assert "private-file" in {f.code for f in report.findings}
    assert "never-read" not in json.dumps(report.to_dict())


def test_unsupported_field_spelling_is_flagged(marketplace: Path) -> None:
    for relative in ("metadata/plugin.json", ".codex-plugin/plugin.json"):
        path = marketplace / "plugins/session-handoff" / relative
        value = json.loads(path.read_text())
        interface = (
            value["interface"]
            if relative.startswith(".codex")
            else (value["extensions"]["com.openai"]["interface"])
        )
        interface["short_description"] = interface.pop("shortDescription")
        path.write_text(json.dumps(value))
    assert "manifest-fields" in codes(marketplace)


def test_catalog_enum_value_is_validated(marketplace: Path) -> None:
    path = marketplace / ".agents/plugins/marketplace.json"
    value = json.loads(path.read_text())
    value["plugins"][0]["policy"]["authentication"] = "oninstall"
    path.write_text(json.dumps(value))
    assert "catalog-fields" in codes(marketplace)


def test_skill_interface_metadata_is_validated(marketplace: Path) -> None:
    path = marketplace / "plugins/session-handoff/skills/write-handoff/agents/openai.yaml"
    path.parent.mkdir()
    path.write_text("interface:\n  display_name: 12\n  short_description: null\n")
    assert "skill-interface" in codes(marketplace)


def test_duplicate_frontmatter_keys_are_rejected(marketplace: Path) -> None:
    path = marketplace / "plugins/session-handoff/skills/write-handoff/SKILL.md"
    path.write_text("---\nname: wrong\nname: write-handoff\ndescription: Test\n---\n")
    assert "skill-frontmatter" in codes(marketplace)


def test_hook_duplicate_json_fields_are_flagged(marketplace: Path) -> None:
    path = marketplace / "plugins/session-handoff/hooks/hooks.json"
    path.write_text('{"hooks":{},"hooks":{}}')
    assert "invalid-document" in codes(marketplace)


def test_skipped_native_agent_hook_handler_is_flagged(marketplace: Path) -> None:
    path = marketplace / "plugins/session-handoff/hooks/hooks.json"
    value = json.loads(path.read_text())
    value["hooks"]["SessionStart"][0]["hooks"][0] = {"type": "agent", "prompt": "Audit"}
    path.write_text(json.dumps(value))
    assert "hook-fields" in codes(marketplace)


def test_documented_null_skill_policy_is_supported(marketplace: Path) -> None:
    path = marketplace / "plugins/session-handoff/skills/write-handoff/agents/openai.yaml"
    path.parent.mkdir()
    path.write_text("policy:\n  allow_implicit_invocation: null\n  products: null\n")
    assert audit_project(marketplace).status == "PASS"


def test_runtime_toml_must_parse(marketplace: Path) -> None:
    shutil.copytree(
        ROOT / "plugins/agent-context-audit", marketplace / "plugins/agent-context-audit"
    )
    catalog = marketplace / ".agents/plugins/marketplace.json"
    value = json.loads(catalog.read_text())
    value["plugins"].append(
        {
            "name": "agent-context-audit",
            "source": {"source": "local", "path": "./plugins/agent-context-audit"},
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
            "category": "Productivity",
        }
    )
    catalog.write_text(json.dumps(value))
    readme = marketplace / "README.md"
    readme.write_text(
        readme.read_text() + "| [Agent Context Audit](plugins/agent-context-audit/README.md) "
        "| 0.1.0 candidate | Audit |\n"
    )
    assert audit_project(marketplace).status == "PASS"
    (marketplace / "plugins/agent-context-audit/pyproject.toml").write_text("broken = [\n")
    assert "invalid-document" in codes(marketplace)


def test_catalog_source_and_category_types_are_checked(marketplace: Path) -> None:
    path = marketplace / ".agents/plugins/marketplace.json"
    value = json.loads(path.read_text())
    value["plugins"][0]["source"]["source"] = 12
    value["plugins"][0]["category"] = ["invalid"]
    path.write_text(json.dumps(value))
    assert audit_project(marketplace).status == "BLOCKED"


@pytest.mark.parametrize("name", [".npmrc", ".netrc", ".pypirc", ".git-credentials"])
def test_credential_store_names_are_not_read(marketplace: Path, name: str) -> None:
    path = marketplace / "plugins/session-handoff" / name
    path.write_text("SYNTHETIC_PRIVATE_CANARY=must-not-be-read\n")
    report = audit_project(marketplace)
    assert any(f.code == "private-file" for f in report.findings)
    assert "must-not-be-read" not in json.dumps(report.to_dict())


@pytest.mark.parametrize("field,value", [("keywords", "invalid"), ("unexpectedField", True)])
def test_portable_manifest_field_contract_is_checked(marketplace: Path, field, value) -> None:
    path = marketplace / "plugins/session-handoff/metadata/plugin.json"
    data = json.loads(path.read_text())
    data[field] = value
    path.write_text(json.dumps(data))
    assert "manifest-fields" in codes(marketplace)


def test_readme_catalog_display_identity_must_match(marketplace: Path) -> None:
    path = marketplace / "README.md"
    path.write_text(path.read_text().replace("[Session Handoff]", "[Wrong Product]"))
    assert "readme-identity" in codes(marketplace)
