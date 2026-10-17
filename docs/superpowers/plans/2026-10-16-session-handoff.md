# Session Handoff for Codex — Native-First Implementation Plan

Status: approved for implementation by the owner on 2026-10-16.

Implementation amendment: native probes reproduced Codex issue 47925 on 0.162.1
and 0.163.0: a root portable plugin.json suppresses hooks. The same extracted
plugin exposes SessionStart when that root file is absent. Preserve the requested
native workflow by activating .codex-plugin/plugin.json and retaining synchronized
portable source metadata at metadata/plugin.json, outside the active root slot.
Agent Context Audit keeps its existing layout. No runtime upgrade is required.

Goal: adapt the Claude Session Handoff plugin into an independently installable
Codex 0.1.0 candidate, stopping before commit, push, tagging, upload or publication.

Execution: inline using Superpowers Executing Plans; preserve all review evidence.
Use Codex skills, filesystem tools, Bash lifecycle hooks, native plugin installation
and the installed Plugin Eval workflow. Do not add a Python runtime or MCP server.

## Task 1: Package and adapt

- [x] Record source revision and hashes; retain MIT attribution; leave Claude unchanged.
- [x] Create canonical/compatibility manifests, write-handoff skill, references,
  startup hook, README, CHANGELOG and LICENSE.
- [x] Register the plugin without changing Agent Context Audit behavior/version.
- [x] Preserve inspect, authorized Git settlement, reconciliation, full draft review,
  approval, exclusive append-only save and confirmation.

## Task 2: Continuity and lifecycle

- [x] Bind inspection/storage to the explicit absolute session workspace directory.
- [x] Read the newest matching record completely; distinguish absence from failures.
- [x] Preserve every inherited item, opening dates, evidence and stale markers.
- [x] Adapt the Bash hook to session cwd and PLUGIN_ROOT; startup/clear only.
- [x] Keep absent-handoff sessions silent and preserve the initial user request.
- [x] Treat records as historical data; never promote their embedded instructions.
- [x] Keep noninteractive fallback, native hook trust and manual recovery.

## Task 3: Existing evaluation workflow

- [x] Evaluate the completed plugin and skill using Plugin Eval JSON reports.
- [x] Inspect findings and distinguish heuristics from functional defects.
- [x] Prepare synthetic benchmark scenarios outside the package; attempt dry-run
  and real execution through the existing harness without copying credentials.
- [x] Cover first save, reconciliation, unauthorized drop, unreadable previous
  record, current-request preservation and noninteractive behavior.
- [x] Inspect saved outputs; keep model behavior and hook delivery separate.

## Task 4: Validation and release preparation

- [x] Add failing tests, then implement hook and package/validation support.
- [x] Cover special paths, errors, selection, collisions and record preservation.
- [x] Extend the existing packager with plugin selection and separate sidecars;
  preserve existing API/default behavior and use plugin-specific allowlists.
- [x] Run existing gates and supported LSP queries; do not weaken any gates.
- [x] Build twice, compare bytes/hashes, inspect contents, and test installation
  from extracted source in a disposable Codex home.
- [x] Update CI definitions and report local/remote, model/hook and OS coverage
  separately. Deliver the actual diff, package inventory, checksum and limitations.

## Acceptance

Required local gates, clean installation and actual behavioral acceptance must pass
before calling the result locally release-ready. Missing authentication or interactive
hook verification remains a release blocker. Remote CI, public installation and
untested operating systems are separate unverified layers.

Implementation tasks completed; terminal release acceptance remains incomplete as stated above. Native-model samples are supplemental, and actual authenticated CLI/interactive-hook acceptance remains pending.
