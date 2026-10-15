"""Materialize synthetic benchmark sources without running any target code."""

import argparse
import json
from pathlib import Path


def create_fixtures(destination: Path, *, suite: str = "original") -> list[dict]:
    if destination.exists():
        raise ValueError("Fixture destination already exists; preserve prior runs")
    data = json.loads(
        (Path(__file__).resolve().parents[1] / "tests/fixtures/semantic-cases.json").read_text()
    )
    destination.mkdir(parents=True, mode=0o700)
    scenarios = []
    if suite not in {"original", "hybrid"}:
        raise ValueError("Unknown semantic fixture suite")
    repositories = data["hybrid_repositories" if suite == "hybrid" else "repositories"]
    for name, files in repositories.items():
        base = destination / name
        for root in ("repo", "codex", "claude", "home"):
            (base / root).mkdir(parents=True, mode=0o700)
        for relative, content in files.items():
            path = base / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        scenarios.append(
            {
                "name": name,
                "root": str((base / "repo").resolve()),
                "source_codex_home": str((base / "codex").resolve()),
                "source_claude_home": str((base / "claude").resolve()),
                "source_user_home": str((base / "home").resolve()),
            }
        )
    (destination / "fixture-manifest.json").write_text(
        json.dumps(
            {
                "scenarios": scenarios,
                "expected_topics": data["expected_topics"],
                "negative_expectations": data["negative_expectations"],
                "semantic_execution": "not-run",
                "suite": suite,
                "expectations": data.get("hybrid_expectations", {}) if suite == "hybrid" else {},
            },
            indent=2,
        )
        + "\n"
    )
    return scenarios


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(json.dumps(create_fixtures(args.destination), indent=2))
