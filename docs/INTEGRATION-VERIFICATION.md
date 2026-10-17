# Source integration verification

Evidence date: 2026-10-17 UTC. The owner requested staging all pending Codex Factory source, signed commits, pushes and a pull request. Source publication is authorized; merging the PR, release tags and release assets are separate actions.

## Integrated scope

- Project Records: original Factory templates with path-only adaptation, native Codex procedures and project-local lazy document creation. Source commit cfbeedd.
- Session Handoff and project consistency guard: independently installable native handoff plugin, exact-outgoing-object checks and contextual pre-push review. Source commit 2c3b820.
- Shared catalog, README, packaging API and CI now support all three plugins without discarding either implementation branch. Existing positional and keyword package calls, generic sidecars and plugin-prefixed sidecar consumers remain supported. Different archives require separate output directories.
- Existing dated verification reports retain their original source-stage evidence and limitations. See REPOSITORY-STATE.md for the current publication authorization.

## Current local evidence

Ruff passes; its owned Python format check reports 75 unchanged files. Basedpyright through nvm Node reports 0 errors, 0 warnings and 0 notes. The complete suite with explicit native Codex 0.162.1 passed **257 tests**. Marketplace validation and deterministic project consistency pass for all three packages. LSP is unavailable: Missing executable: mcpls; no runtime was installed.

The source branches separately passed 170 and 234 tests before signed commits. The first combined packaging check reproduced 11 failures with a one-branch-only packager; the merged implementation passes all original tests unchanged. Independent read-only review verified both API forms and all six reproducibility builds. Its duplicate README catalog-link finding was reproduced and fixed without changing the audit rule.

## Real pre-push findings and corrections

The first authenticated SSH push was blocked by the actual native reviewer before remote refs changed. It identified that the final Agent Context Audit run schema rejected findings.observation_ids and decisions.adjudicated_finding_ids produced and persisted by the hybrid pipeline.

Two positive contract tests failed before the correction, while seven negative/legacy tests passed. The schema now admits only the two declared arrays of strings. Existing required fields and additionalProperties=false remain intact; run-v1.json is unchanged. All nine regressions pass, and an independent reviewer checked correspondence with pipeline.py and adjudication.py. These regressions validate persisted contract objects; they do not claim a new complete live-model adjudication run.

The repository-local guard was reinstalled from reviewed integrated source with all 11 resource hashes checked. The previous installation and reports were preserved in the common Git history directory. No global Git/Codex configuration changed and no hook bypass was used. Fresh outgoing-object review is still required on each push.

## Current package evidence

| Plugin | Files | SHA256 |
| --- | ---: | --- |
| Agent Context Audit 0.1.0 | 50 | 2f143e0616cb720a32eb7f16b0559131cbe764226f4500beabadfe5dbb8998d2 |
| Session Handoff 0.1.0 | 11 | 6a558128ba1234890263d0194ae6261deeb349df7833288a48e56925f82a122a |
| Project Records 0.1.0 | 12 | c101aff9aabcbc577d56bac942330193e935cce491d74115845744ec15f2c8f7 |

The deterministic auditor built every archive twice and checked exact bytes, inventories, checksums and source members. Maintainer tests/tools/reports, development environments and credentials remain outside plugin packages and commits. The Agent Context Audit checksum differs from earlier dated reports because its persisted schema is corrected.

## Publication boundaries

The first remote Ubuntu 24.04 job reached the native sandbox canary but could not start it; macOS CI passed. Linux CI now installs bubblewrap and the distribution's scoped AppArmor user-namespace profile, with a real bwrap preflight before the unchanged native tests. This follows https://learn.chatgpt.com/docs/sandboxing. The global AppArmor restriction is not disabled and no sandbox assertion is skipped. Final remote outcomes remain visible in the PR checks.

All source worktrees must be clean after the signed source commits and integration merge. Ignored build/runtime/evidence directories are retained under the project's existing policy, not forced into source control. The final remote branch/PR/CI state is verified directly on GitHub rather than inferred from local checks.

Session Handoff's interactive trusted-hook and authenticated benchmark release checks remain incomplete as documented in SESSION-HANDOFF-VERIFICATION.md. Project Records' installed discovery and model behavior were verified in separate layers as documented in PROJECT-RECORDS-VERIFICATION.md. No plugin release, platform-wide semantic acceptance or remote CI success is asserted by these local results.
