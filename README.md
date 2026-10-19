# The Codex Factory

A public-by-design marketplace of independently versioned Codex plugins, maintained by Nery Samuel Murillo with Codex as a co-maintainer.

**Current state:** source repository initialized on GitHub; plugins remain release candidates. No plugin release tags or release assets have been published. Tagged installation commands below become usable after owner-approved plugin releases.

See [repository publication state](docs/REPOSITORY-STATE.md) for the distinction between source publication and earlier dated verification snapshots.

The [integration verification](docs/INTEGRATION-VERIFICATION.md) records the combined source checks, current package hashes and remaining release limits.

## Plugins

| Plugin | Version | Purpose |
| --- | --- | --- |
| [Project Records](plugins/project-records/README.md) | 0.1.0 candidate | Project-local ADRs and technical debt ledgers with verified resolutions and preserved history |
| [Agent Context Audit](plugins/agent-context-audit/README.md) | 0.1.0 candidate | Parallel and cross-domain audits of the instructions, memory, rules, agents, workflows and configuration governing coding agents |
| [Session Handoff](plugins/session-handoff/README.md) | 0.1.0 candidate | Reviewed project handoffs, pending-item reconciliation and trusted session-start context recovery |

## Installation

Project Records has a separate [local verification report](docs/PROJECT-RECORDS-VERIFICATION.md).

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
uv run --locked --no-env-file python -m tools.package_plugin --plugin session-handoff --output-dir dist/session-handoff
uv run --locked --no-env-file python -m tools.package_plugin --plugin project-records --output-dir dist/project-records
```

The Basedpyright JavaScript entry point deliberately uses the nvm Node executable. Do not run its Python wrapper, which selects its bundled Node dependency. Source/configuration/instruction Markdown is not formatter-owned.

Session Handoff uses Bash and Codex's native tools at runtime; the Python
environment above is maintainer tooling. See its
[verification report](docs/SESSION-HANDOFF-VERIFICATION.md) for local installation,
Plugin Eval, behavioral acceptance and remaining release blockers.

See [maintenance](docs/MAINTAINING.md), [security](SECURITY.md), the [approved implementation plan](docs/superpowers/plans/2026-10-14-agent-context-audit.md), and the [verification matrix](docs/VERIFICATION.md). Local fixture gates, model accuracy, native isolation, clean installation, operating-system coverage and public-source installation are separate evidence layers.

## Project consistency before push

The project-local audit skill, native reviewer and Git pre-push guard check plugin
metadata, documentation and package alignment against the actual outgoing commits.
Run the deterministic check with:

```sh
uv run --locked --no-env-file python -m tools.push_audit check --root "$PWD" --deterministic
```

See [setup, native review and recovery](docs/PROJECT-CONSISTENCY.md). Installation
is local to this repository; no global Git/Codex configuration is changed.
