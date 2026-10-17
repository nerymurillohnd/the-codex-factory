# Project Records for Codex Factory

## Scope and source

Create an independently installable `project-records` plugin in The Codex Factory. Adapt the skill at `~/Claude/the-claude-factory/.claude/skills/project-records`, revision `fb86ddb226c3543fce491a70f4575107e6479341`. The originally named Factory plugin directory is absent. Essentials is outside this task. The owner clarified that this work belongs to Codex Factory.

## Functional contract

Owner clarification: preserve the original three assets and the structure/content of references. Assets change only the documented output path. References change provider-specific tools, output paths and fixed personal names, retaining verified correctness safeguards. Do not add privacy/terms documents or remove source content to satisfy a generic evaluator score.

One automatically discoverable skill handles important decisions, deferred confirmed debt, and verified debt resolutions. Default records live under `docs/maintainer/decisions/` and `docs/maintainer/technical-debt/` in the explicitly selected target project. Explicit project/user path and authorization instructions prevail. No first-use setup, automatic migration, global configuration changes, hooks, MCP server, mandatory agents, or handoff feature.

Keep source behavior: record proactively during authorized work, ask only for missing facts, ask once how to register multiple decisions (individual, single package, classified), deduplicate, preserve accepted ADR reasoning, and supersede through reciprocal links. Use local dates. Never infer an accepted decision or invent rejected alternatives.

Debt requires observed evidence, real impact, a reason it cannot be fixed now, and a next action/review condition. Do not duplicate an issue or ADR follow-up. IDs are allocated numerically across both ledgers without reuse. Failed reads or malformed records are blockers, not empty ledgers. Resolutions require positive and original-failure negative checks. Write and verify the resolved entry before removing pending; preserve the ID and logged date. Recurrence gets a new ID and historical backlink.

Write from bundled templates, remove template instructions and fill fields. Preserve indexes and empty-state markers. Do not overwrite existing ADR filenames. Use native Codex filesystem and question capabilities without Claude-specific tool names. Read only the relevant procedure/template. Record evidence provenance, uncertainty and verification limits without secrets.

## Package and integration

Version `0.1.0`, MIT attribution retained from Factory. Portable root `plugin.json` is canonical; matching `.codex-plugin/plugin.json` provides Codex compatibility. Include one skill, three references and three templates, README, LICENSE, CHANGELOG. Register in the project marketplace and root README.

Extend the existing package tool with an explicit plugin selector while retaining the Agent Context Audit default/API. Use a strict per-plugin allowlist for Project Records; exclude tools/tests/reports/private files. Emit deterministic archive, inventory and checksum per build. Keep separate from pending Session Handoff changes.

## Verification

Native acceptance exposed Codex's protection of `.codex/` under workspace-write. The default was corrected to `docs/maintainer/`; preserve explicit overrides and report unwritable paths without relocating records. Evidence: initial semantic-v1 attempts and official protected-path documentation. An accepted decision remains active while its replacement is merely proposed.

Test packaging reproducibility, all required files, symlink/private/unexpected-file rejection, metadata/catalog alignment and reference targets. Run locked root diagnostics and tests with explicit native Codex. Use native discovery with isolated configuration. Test actual model behavior in synthetic projects for creation, supersession, duplicate debt, resolution, recurrence, incomplete facts, batch decisions, corrupt ledgers and trivial work. Inspect resulting records against the contract; static Plugin Eval scores are not semantic acceptance. Keep evidence under `.superpowers/project-records/`.

## Delivery boundary

Deliver reviewed source, archive and verification report. Do not commit, push, publish, install globally, or mark remote CI/public installation verified. Owner approval controls publication.
