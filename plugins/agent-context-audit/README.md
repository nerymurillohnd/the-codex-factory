# Agent Context Audit

Audit the operating context that governs Codex and optional Claude Code sources. The controller inventories and reads eligible files, sanitizes sensitive configuration values, runs parallel Codex specialists, reconciles their contributions, validates citations and coverage, and writes one report with proposed corrections. It does not apply corrections.

Version 0.1.0 is a release candidate pending the repository's verification and publication gates.

## Hybrid review

Python prepares protected source views, repository evidence and mechanical observations. Specialists resolve each observation and independently review every assigned source, including sources without observations. Assignments prefer complete files; oversized sources retain exact chunk ownership and can request protected source context. An observation is not automatically a defect.

Every proposed final finding and observation decision receives a separate semantic assessment. The final reconciler may accept, revise, reject or uphold a conclusion over an objection, recording the evidence and counterevidence. New or revised conclusions receive one bounded delta-verification pass. Terminal adjudication cannot introduce an unassessed rewrite. Disagreement alone does not make a run partial; missing verification, coverage or essential evidence does.

Run schema 1.1 records observations, decisions, semantic assessments, adjudications and the metadata of supporting evidence reads. Existing 1.0 reports remain readable and are labelled as lacking independent semantic verification. Baselines from a different or unknown scope leave unmatched findings unassessed instead of declaring them resolved.

Claude application state is filtered to global MCP entries and the audited project's MCP entries before helper discovery and model delivery. Unrelated projects and application metadata are omitted; the view retains original line coordinates. `--source-claude-state` explicitly selects that state file, and generated schedules preserve the selected path. Other Claude behavioral settings remain separate audited sources.

## Scope

Included: user, project and nested instructions; editable memory; rules; custom agents; legacy commands; saved workflows; output styles; behavior configuration; hook definitions and relevant user-owned helper files referenced by configuration. Both user and project scope remain relevant regardless of where the plugin is installed.

Excluded as remediation targets: skill packages, installed plugin-provided components, the auditor itself, and managed policy. Secret stores, .env files and .dev.vars are never eligible reads. Mixed configuration is redacted while retaining source line numbering. Source text, helpers and reviewer responses are untrusted data. Hooks, workflows and MCP servers from the target are never executed by the audit.

Checks cover false, wrong, obsolete, dead, ambiguous, duplicated, overlapping, misplaced, contradictory, redundant-with-defaults and non-conformant guidance. Legitimate explicit policy is preserved. A recommendation to remove a rule requires evidence beyond model familiarity.

## Setup

Prerequisites: uv, a trusted Python 3.14.8 installation discoverable with `uv python find --system` (prepare it with `uv python install --no-config 3.14.8` if needed), Codex CLI 0.162.1, and native Codex authentication available to the user. The maintained knowledge baseline covers Codex 0.162.1 and Claude Code 2.1.300. Other Codex versions require successful capability probes and remain outside the verified knowledge baseline. macOS arm64 is the development platform; consult the verification matrix before assuming another platform is tested.

On Linux, pass the actual trusted native executable with `--codex-bin /absolute/native-codex` when your package manager exposes a JavaScript launcher. The deny-by-default sandbox grants read access to that exact executable for its internal re-exec, without exposing its parent directory. The capability canary remains mandatory.

Resolve the installed plugin root from the loaded skill's location. Substitute that absolute directory for `/absolute/plugin` below. Python is managed by uv; setup creates a separate locked environment under the user's data directory. Setup is the only dependency-installing operation.

```sh
audit_python="$(uv python find --system --no-project --no-config 3.14.8)" &&
env -u VIRTUAL_ENV -u CONDA_PREFIX uv run --isolated --no-project --no-config --no-env-file --python "$audit_python" python -I -S /absolute/plugin/scripts/audit.py setup
```

The command prints the native device-login command for a dedicated authentication home. Complete that login yourself. The controller never reads or copies existing authentication files. Existing CODEX_API_KEY or CODEX_ACCESS_TOKEN variables can also be passed to native Codex without displaying their values. The dedicated profile must contain no foreign instructions, hooks or behavioral configuration.

## Run an audit

```sh
audit_python="$(uv python find --system --no-project --no-config 3.14.8)" &&
env -u VIRTUAL_ENV -u CONDA_PREFIX uv run --isolated --no-project --no-config --no-env-file --offline --python "$audit_python" python -I -S /absolute/plugin/scripts/audit.py audit --root /absolute/repository
```

Here the outer uv `--offline` prevents dependency downloads; it does not disable the auditor's official-document checks. Add `--offline` after `audit` to use only bundled platform knowledge, which produces a visible freshness limitation.

Within Codex, explicitly invoke `$audit-agent-context` or request an audit of the repository's agent context. The skill uses the same launcher with `--entry-mode interactive`. An interactive parent may already have consumed instructions or executed hooks; isolation of child reviewers does not retroactively isolate that parent, and the result reports that limit.

Defaults: four concurrent jobs, one challenge round, 600 seconds per job and 1,800 seconds overall. Configure `--jobs`, `--challenge-rounds` (0–2), `--job-timeout`, `--timeout`, `--model` and `--effort` explicitly as needed. All specialists, challenges and reconciliation jobs share the requested model/effort. No target provider/model configuration is imported into the audit runtime.

Source overrides: `--source-codex-home`, `--source-claude-home`, and `--source-user-home`. A referenced source outside those roots requires an explicit `--allow-source-root`. Configuration alone cannot authorize wider reads. Partial source mounts in CI cannot establish full local coverage. When a trusted native Claude CLI is available, the controller reads its version inside the audit sandbox with an empty isolated Claude home. Target hooks and configuration are not executed. Without a usable CLI probe, source-only analysis remains available with an explicit version-verification limitation.

External links are unverified by default. `--allow-domain example.org` permits checks on that exact public domain without credentials or query strings. Private destinations, unsafe redirects and TLS downgrades are blocked. The fixed official documentation map is retrieved independently without audit content. Unavailable or changed official documentation produces a freshness limitation.

## Artifacts and exit status

Runs default to `${XDG_STATE_HOME:-~/.local/state}/the-codex-factory/agent-context-audit/runs/<repository-id>/<unique-run>/`. `--output-dir` selects an external parent by default; existing runs are never overwritten. Writing reports inside the target requires the explicit `--allow-output-in-target` flag. Review processes and raw evidence still run outside the target under XDG_STATE_HOME. The report labels the intentional artifact writes and the scope of Git checks; avoid committing private global-context excerpts inadvertently. Directories use mode 0700 and files use 0600. Each run contains one primary `report.md`, canonical `status.json`, and private supporting evidence. Retain or delete your run directories explicitly; the plugin does not prune history.

| Exit | Status | Meaning |
| ---: | --- | --- |
| 0 | complete-clean | Applicable coverage and integrity checks pass; no findings |
| 1 | complete-with-findings | Applicable checks pass; findings exist |
| 2 | partial | Findings may be useful, but coverage, freshness, evidence or an isolation guarantee is incomplete |
| 3 | failed | Preflight or analysis is unusable, or output integrity failed |

Use `latest --root /absolute/repository` to locate the newest finalized report, including failures. Add `--completed-only` to select only a complete audit. Use `audit --baseline /absolute/previous/status.json` to compare new, persisting, resolved and regressed findings. Partial audits never establish a finding as resolved. Exact source-content identities are stable across line drift; ambiguous moves or rewrites are not silently declared equivalent.

Full source delivery, chunk receipts, dispositions and citations are mechanically checked. They cannot prove that a model reasoned perfectly. Preserve the report's uncertainty and inspect proposed edits before implementing them. When global reconciliation input exceeds the context bound, the controller compares every complete shard pair in bounded batches and preserves a contribution ledger. Unresolved batch disagreements or an oversized individual pair produce a partial run; input is never silently truncated. Pairwise checks do not prove the absence of every possible higher-order interaction.

## Scheduling

Print a recipe; this does not install any schedule:

```sh
audit_python="$(uv python find --system --no-project --no-config 3.14.8)" &&
env -u VIRTUAL_ENV -u CONDA_PREFIX uv run --isolated --no-project --no-config --no-env-file --offline --python "$audit_python" python -I -S /absolute/plugin/scripts/audit.py schedule-example --scheduler launchd --root /absolute/repository --hour 9 --minute 0
```

Supported recipe types: `app`, `launchd`, `systemd`. The default is daily 09:00 in local time; `--weekday mon` selects a day. Use the original local checkout to include uncommitted/local-only files. Keep the local host available. For systemd, save the service and timer sections in separate files. Exit 1 means completed findings; exits 2 and 3 need attention.

## Data boundary

Sanitized audit context is sent to the selected Codex model provider through native authentication. Controllable telemetry exporters, tools, hooks, plugins, shell, network tools and automatic skills are disabled and checked. Command-sandbox read/write/network canaries must pass. Provider retention and externally managed host telemetry are outside this plugin's control. Restricted policies that prevent the required isolation are a failure, not a reason to broaden permissions.

The source map, maintained platform paraphrases and review prompts ship under references/. Per-run document text and model artifacts stay private. Development tests, known-answer fixtures and maintainer tools are excluded from the installable archive.

## Evidence and review status

Specialists can request bounded repository evidence using the controller's scoped file index and literal paths, or retrieve excerpts from already-fetched official documents. Evidence requests do not grant shell access or authorize additional roots. A completed source read can remain review-incomplete when essential evidence is unavailable; valid receipts are retained rather than reported missing. Ordinary assessment notes are separate from unmet requirements, which still make the run partial.

The provider receives a compatible structured-output schema. The controller validates the response against the full packaged schema, including assertions unsupported by the provider transport, and permits one bounded repair attempt for malformed output or invalid assignment citations. Setup rebuilds the plugin package so a same-version local source update cannot silently reuse an older cached wheel.

Git observation refuses repositories with executable filters/includes or tracked secret stores when passive working-tree verification cannot be established. It does not execute a repository filter or inspect tracked secret-file contents to obtain a clean result.

When an explicit target root is outside the launcher's current directory, helper-path interpretation uses that target root. The original invocation directory is retained separately in status.json. Launching from a descendant of the target preserves that more specific directory context.

Schedule recipes capture the selected source roots, authentication home, output directory and required non-secret runtime paths. Their Python bootstrap runs in isolated, no-site mode; audit commands do not inherit Python startup customizations. Regenerate recipes after moving or updating the installed plugin or toolchain, and keep their runtime and native authentication prepared.
