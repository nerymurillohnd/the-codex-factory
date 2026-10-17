# Project Records Implementation Plan

## Owner clarification: source-faithful package

- [x] Restore original assets with path-only changes; verify against source bytes.
- [x] Restore original procedure structure, adapt Claude tools and personal names, explicitly define lazy target-project folder creation.
- [x] Verify the revised package with native semantic cases, fresh gates and reproducible archives; replace superseded verification claims with current evidence.

> **For agentic workers:** Use superpowers:executing-plans to implement this plan inline, with an independent final review.

**Goal:** Adapt Factory's ADR/debt skill as an installable Codex Factory plugin.

**Architecture:** One skill routes to three procedures and templates. Native Codex performs record work; maintainer tools package and verify the plugin.

**Tech Stack:** Markdown, JSON, Python through uv, Node through nvm, installed native Codex.

**Spec:** `docs/superpowers/specs/2026-10-16-project-records-design.md`

## Global Constraints

- Plugin version 0.1.0, retained MIT attribution.
- Source is the Factory skill; Essentials and Session Handoff are out of scope.
- No global installation, commit, push or publication.
- Preserve existing package API/default and other plugin behavior.

## Review Focus

- Unreadable or malformed ledgers must not reset identifiers.
- Same-day ADR filename collisions must not overwrite history.
- Explicit user/project path and permission instructions prevail.
- Partial debt moves must not delete the only remaining record.
- Existing issue/ADR tracking must not be duplicated as debt.

### Task 1: Establish baseline and package contract

**Files:** `tests/test_project_records.py`, `tools/package_plugin.py`.
**Interfaces:** Preserve `package_plugin(root: Path, output_dir: Path) -> Path`; add keyword `plugin_name: str = "agent-context-audit"`.

- [x] Run root baseline tests with explicit native binary.
- [x] Run a synthetic ADR request without the skill and retain observed behavior.
- [x] Write failing tests for Project Records archive inventory, two equal builds, unknown plugin, symlink/private/unexpected file rejection.
- [x] Run and confirm the intended failures.

### Task 2: Implement the package and native skill

**Files:** `plugins/project-records/{plugin.json,.codex-plugin/plugin.json,README.md,LICENSE,CHANGELOG.md,skills/project-records/SKILL.md}`; three procedures under `references/`, three templates under `assets/`.
**Interfaces:** Public invocation `$project-records`; default ADR/debt paths from spec.

- [x] Adapt procedures and templates, preserve source contract and repair Codex-specific interactions.
- [x] Add canonical/native metadata and package documentation.
- [x] Extend package tool with strict per-plugin allowlist and CLI `--plugin project-records`.
- [x] Run package tests and inspect archives.

### Task 3: Integrate and evaluate

**Files:** `.agents/plugins/marketplace.json`, `README.md`, `docs/PROJECT-RECORDS-VERIFICATION.md`; maintainer semantic acceptance evidence.

- [x] Register plugin and root documentation.
- [x] Validate skill, relative paths and marketplace; run Plugin Eval router and JSON analysis.
- [x] Verify native discovery in an isolated home.
- [x] Exercise the spec's positive, negative and partial-state scenarios with native Codex; inspect files and decisions.
- [x] Address supported findings and rerun affected checks.

### Task 4: Verify and deliver

- [x] Run full locked Ruff, format check, Basedpyright, pytest with explicit native binary, marketplace validation.
- [x] Build twice into distinct directories; compare archive bytes/checksums and inspect every member.
- [x] Obtain independent read-only review, adjudicate findings against source, fix actionable defects with regression evidence.
- [x] Review complete diff; write exact evidence and remaining limitations.
- [x] Deliver local source/package without committing or publishing.
