"""Strict contracts for untrusted model output."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator


def resource_path(directory: str, name: str) -> Path:
    """Locate resources in both source plugins and installed wheels."""
    package = Path(__file__).resolve().parent
    bundled = package / "data" / directory / name
    return bundled if bundled.is_file() else package.parent.parent / directory / name


def load_schema(name: str) -> dict[str, object]:
    if name not in {
        "domain",
        "reconciliation",
        "run",
        "source",
        "verification",
        "adjudication",
        "run-v1",
    }:
        raise ValueError("Unknown schema")
    value: object = json.loads(resource_path("schemas", f"{name}.json").read_text())
    if not isinstance(value, dict):
        raise ValueError("Schema must be an object")
    return value


def provider_schema(name: str) -> dict[str, object]:
    """Adapt provider transport constraints; validate final output against the full local schema."""
    schema = load_schema(name)

    def visit(node: object) -> None:
        if not isinstance(node, dict):
            return
        # Native Responses rejects this assertion in strict schemas. It remains mandatory
        # in the packaged schema and local validator, including after every model attempt.
        node.pop("uniqueItems", None)
        for keyword in ("properties", "$defs", "definitions"):
            entries = node.get(keyword, {})
            if isinstance(entries, dict):
                for child in entries.values():
                    visit(child)
        for keyword in ("items", "additionalProperties", "not"):
            visit(node.get(keyword))
        for keyword in ("allOf", "anyOf", "oneOf", "prefixItems"):
            entries = node.get(keyword, [])
            if isinstance(entries, list):
                for child in entries:
                    visit(child)

    visit(schema)
    return schema


def validate_output(value: object, schema_name: str = "domain") -> None:
    """Validate model output before any downstream use."""
    if schema_name == "run" and isinstance(value, dict) and value.get("schema_version") == "1.0":
        schema_name = "run-v1"
    Draft202012Validator(load_schema(schema_name)).validate(value)
    if not isinstance(value, dict):
        raise ValueError("Output must be an object")
    for finding in value.get("findings", []):
        if finding["line_end"] < finding["line_start"]:
            raise ValueError("Reversed finding range")
        evidence = finding["evidence"]
        if not evidence:
            raise ValueError("Finding requires evidence")
        if finding["disposition"] in {"revise", "merge"} and not finding["replacement"]:
            raise ValueError("Revision/merge requires replacement text")
        if finding["disposition"] == "move" and not finding["target_location"]:
            raise ValueError("Move requires target location")
        if finding["disposition"] == "remove" and (
            finding["confidence"] == "low" or all(e["kind"] == "model-judgment" for e in evidence)
        ):
            raise ValueError("Unsupported removal recommendation")
