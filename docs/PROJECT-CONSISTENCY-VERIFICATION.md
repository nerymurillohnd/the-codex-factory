# Project consistency verification

Local verification on 2026-10-16, macOS arm64, Python 3.14.8 through uv,
nvm Node 26.11.1 and native Codex 0.162.1. Worktree: work/session-handoff.
This report covers the project consistency guard; Session Handoff release
acceptance remains separately documented in SESSION-HANDOFF-VERIFICATION.md.

## Results

- Locked environment synchronization succeeded.
- Ruff check passed; Ruff format check passed for all 73 configured Python files.
- Basedpyright reported 0 errors, 0 warnings and 0 notes.
- The full suite passed: 234 tests in 26.22 seconds, including explicit native
  Codex transport tests. No native binary omission or skipped-test claim substitutes
  for this execution.
- Marketplace validation passed. Working-copy deterministic consistency validation
  passed with no findings and reproducible packages for both plugins.
- The system skill validator accepted audit-project-consistency. Static plugin-eval
  scored the skill 100; that score is a static rubric result, not semantic proof.
- Native app-server skills/list discovered audit-project-consistency, enabled with
  repo scope, using an empty temporary Codex home without copied authentication.
- LSP diagnostics could not start: Missing executable: mcpls. The project's pinned
  Basedpyright and Ruff supplied the native static checks; no LSP runtime was installed.

## Actual native push acceptance

Signed synthetic commits were pushed to a local bare remote through the installed
Git guard and actual authenticated native Codex reviewer. Credentials were not
copied into the synthetic repository, review workspace or evidence.

The coherent commit 274613d28d9983156e24c6980c1f7e648d97e512 was accepted (exit 0).
The next commit c298ebe69921254409cde1cfb0b77d61a093e19f added a README assertion
that the plugin never creates files, contradicting its documented save workflow.
Deterministic metadata validation passed, but contextual review returned BLOCKED
with CONTRADICTORY_FILE_BEHAVIOR. The actual push exited 1 and the bare remote
remained at the first commit. The coordinator inspected the finding against the
README, skill and save reference.

Evidence: .superpowers/push-audit/native-final-transport/result.json and its
referenced PASS/BLOCKED reports. Additional working-copy native coherent and
contradictory reviews are retained alongside this evidence.

## Independent review and negative cases

Independent review identified unsafe symlinked hooks directories, incomplete
implementation evidence for README-only changes, unchecked plugin TOML/catalog
types, and incomplete or malformed native event streams. The coordinator
reproduced the failures, corrected them, and reran the regression suite.

Fixtures also cover malformed metadata/frontmatter, missing documents, private
paths, signatures, release-tag versions, multiple/deleted refs, changed refs,
existing hooks, invalid review status/digests/coverage, runtime failures and
timeouts. A real subprocess timeout test confirms owned children are terminated.
Synthetic reviewers isolate controller failure cases; the local push acceptance
above supplies the separate real-model evidence.

## Installation and current commit

The guard is active in the repository's common .git/hooks/pre-push, shared by the
main checkout and its worktrees. All 11 installed source-resource hashes match
the reviewed worktree. The runtime is independent of that worktree. No global Git
or Codex configuration was changed.

A direct invocation of the installed hook, without any network transport, rejected
the current HEAD ea7bd0ad4ede33de27cf46f0487e0a2e96735ac7: its canonical listing
summary exceeds 30 characters. The prepared worktree corrects both canonical and
native summaries to "Audit agent operating context" and records the change in
the plugin changelog. This manual correction is not committed; dirty files do
not certify outgoing objects. Evidence: installation-verification.json under
.superpowers/push-audit/ and the referenced common-Git report.

## Packages and remaining boundaries

Both plugins were built twice into distinct directories, with identical ZIP bytes,
valid inventories and no maintainer tools/tests in their archives:

| Archive | Files | SHA-256 |
| --- | ---: | --- |
| agent-context-audit-0.1.0.zip | 50 | 141cbb9432a457ea227126e1c6e2aabc64294496b8c15639e310750ffa18dd88 |
| session-handoff-0.1.0.zip | 11 | 6a558128ba1234890263d0194ae6261deeb349df7833288a48e56925f82a122a |

Inventories and checksums are retained in dist/push-audit-first and
dist/push-audit-second; final-packages.json retains the comparison.

No project commit, public remote push, tag or publication was performed. Remote
CI, other operating systems and server-side enforcement were not verified. Git
allows deliberate local hook bypass; this is an ordinary-push consistency control,
not an absolute security boundary or proof that every application behavior is correct.
The agent definition was parsed and its instructions exercised by the dedicated
native controller; interactive agent-type dispatch was not separately tested.
