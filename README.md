# The Codex Factory

A public-by-design marketplace of independently versioned Codex plugins, maintained by Nery Samuel Murillo with Codex as a co-maintainer.

**Current state:** local implementation and release-candidate verification. The GitHub repository and release have not been published. Installation commands below become public installation instructions after owner approval and publication.

## Plugins

| Plugin | Version | Purpose |
| --- | --- | --- |
| [Agent Context Audit](plugins/agent-context-audit/README.md) | 0.1.0 candidate | Parallel and cross-domain audits of the instructions, memory, rules, agents, workflows and configuration governing coding agents |

## Installation

After publication:

```sh
codex plugin marketplace add nerymurillohnd/the-codex-factory --ref plugin/agent-context-audit/v0.1.0
codex plugin add agent-context-audit@the-codex-factory
```

For local verification, add the absolute path of this checkout instead of the GitHub source. Read the plugin's setup instructions before running an audit. Installing a skill does not prepare its isolated Python runtime or authenticate its dedicated Codex profile.

## Development

Use Python through uv and Node through nvm. Dependencies are pinned in pyproject.toml and uv.lock. The Python version is pinned in .python-version. Run:

```sh
uv sync --locked
uv run --locked --no-env-file ruff check .
uv run --locked --no-env-file ruff format --check plugins/agent-context-audit/src plugins/agent-context-audit/scripts tools tests
node .venv/lib/python3.14/site-packages/basedpyright/index.js
uv run --locked --no-env-file pytest tests --native-codex "$(command -v codex)"
uv run --locked --no-env-file python -m tools.validate_marketplace
uv run --locked --no-env-file python -m tools.package_plugin --output-dir dist
```

The Basedpyright JavaScript entry point deliberately uses the nvm Node executable. Do not run its Python wrapper, which selects its bundled Node dependency. Source/configuration/instruction Markdown is not formatter-owned.

See [maintenance](docs/MAINTAINING.md), [security](SECURITY.md), the [approved implementation plan](docs/superpowers/plans/2026-10-14-agent-context-audit.md), and the [verification matrix](docs/VERIFICATION.md). Local fixture gates, model accuracy, native isolation, clean installation, operating-system coverage and public-source installation are separate evidence layers.
