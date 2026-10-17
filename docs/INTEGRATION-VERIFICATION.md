# Source integration verification

Evidence date: 2026-10-17 UTC. The owner requested staging all pending Codex Factory source, signed commits, pushes and a pull request. Source publication is authorized; merging the PR, release tags and release assets are separate actions.

## Integrated scope

- Project Records: original Factory templates with path-only adaptation, native Codex procedures and project-local lazy document creation. Source commit cfbeedd.
- Session Handoff and project consistency guard: independently installable native handoff plugin, exact-outgoing-object checks and contextual pre-push review. Source commit 2c3b820.
- Shared catalog, README, packaging API and CI now support all three plugins without discarding either implementation branch. Existing positional and keyword package calls, generic sidecars and plugin-prefixed sidecar consumers remain supported. Different archives require separate output directories.
- Existing dated verification reports retain their original source-stage evidence and limitations. See REPOSITORY-STATE.md for the current publication authorization.

## Current local evidence

Ruff passes; its owned Python format check reports 75 unchanged files. Basedpyright through nvm Node reports 0 errors, 0 warnings and 0 notes. The complete suite with explicit native Codex 0.162.1 passed **265 tests**. Marketplace validation and deterministic project consistency pass for all three packages. LSP is unavailable: Missing executable: mcpls; no runtime was installed.

The source branches separately passed 170 and 234 tests before signed commits. The first combined packaging check reproduced 11 failures with a one-branch-only packager; the merged implementation passes all original tests unchanged. Independent read-only review verified both API forms and all six reproducibility builds. Its duplicate README catalog-link finding was reproduced and fixed without changing the audit rule.

## Real pre-push findings and corrections

The first authenticated SSH push was blocked by the actual native reviewer before remote refs changed. It identified that the final Agent Context Audit run schema rejected findings.observation_ids and decisions.adjudicated_finding_ids produced and persisted by the hybrid pipeline.

Two positive contract tests failed before the correction, while seven negative/legacy tests passed. The schema now admits only the two declared arrays of strings. Existing required fields and additionalProperties=false remain intact; run-v1.json is unchanged. All nine regressions pass, and an independent reviewer checked correspondence with pipeline.py and adjudication.py. These regressions validate persisted contract objects; they do not claim a new complete live-model adjudication run.

The repository-local guard was reinstalled from reviewed integrated source with all 11 resource hashes checked. The previous installation and reports were preserved in the common Git history directory. No global Git/Codex configuration changed and no hook bypass was used. Fresh outgoing-object review is still required on each push.

## Changed-source coverage and bounded review

A later real pre-push review correctly blocked the CI-only update because the
controller supplied previous workflow/report text while omitting their current
versions. Three new regression cases reproduced the missing current evidence;
private paths are excluded before reads. Public changed source files now enter the
exact digest-bound review scope, including workflows, maintainer tools and reports.

A complete tracked-source preview then reproduced the existing 512 KiB limit.
Whole-file batching preserves that limit, shared manifest/documentation/schema
anchors and current/previous pairs. All sources must be covered and every packet
must pass. Oversized single-file evidence blocks explicitly; it is not truncated.
Synthetic tests cover complete current/previous coverage, private no-read behavior,
oversized evidence rejection and a nonpassing packet preventing aggregate approval.
The full-source preview fits in three packets. This is controller/transport evidence;
actual outgoing-object model review is performed again by each push.

## Current package evidence

| Plugin | Files | SHA256 |
| --- | ---: | --- |
| Agent Context Audit 0.1.0 | 50 | 6c0f97f738be1244bfa04fef1abf36f452908328380f0a7e6b3b43153ae990bb |
| Session Handoff 0.1.0 | 11 | 6a558128ba1234890263d0194ae6261deeb349df7833288a48e56925f82a122a |
| Project Records 0.1.0 | 12 | c101aff9aabcbc577d56bac942330193e935cce491d74115845744ec15f2c8f7 |

The deterministic auditor built every archive twice and checked exact bytes, inventories, checksums and source members. Maintainer tests/tools/reports, development environments and credentials remain outside plugin packages and commits. The Agent Context Audit checksum differs from earlier dated reports because its persisted schema and exact native-runtime read grant are corrected.

## Publication boundaries

The first remote Ubuntu 24.04 job reached the native sandbox canary but could not start it; macOS CI passed. Linux CI now installs bubblewrap and the distribution's scoped AppArmor user-namespace profile, with a real bwrap preflight before the unchanged native tests. This follows https://learn.chatgpt.com/docs/sandboxing. The global AppArmor restriction is not disabled and no sandbox assertion is skipped. The preparation and its bwrap preflight passed on Ubuntu, but the native canary still could not start. The native synthetic fixture now retains bounded, redacted subprocess stderr on assertion failure to identify the remaining cause. This does not skip or relax the isolation assertions. The diagnostic identified `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`. A CI-only AppArmor namespace exception is now attached to the exact pinned native Codex executable, following https://github.com/openai/codex/issues/15057. It does not change the global user-namespace restriction, and native sandbox startup plus all four canary checks remain mandatory. The corrected native preflight passed. The strict canary then exposed a missing read grant for the native executable during Linux re-exec. The runtime now grants that exact file, not its parent directory or audited sources; a policy regression failed before the fix. CI resolves the actual native payload from the pinned platform package on both operating systems rather than passing its JavaScript launcher. All isolation assertions remain in place. The final remote result remains visible in the PR checks.

All source worktrees must be clean after the signed source commits and integration merge. Ignored build/runtime/evidence directories are retained under the project's existing policy, not forced into source control. The final remote branch/PR/CI state is verified directly on GitHub rather than inferred from local checks.

Session Handoff's interactive trusted-hook and authenticated benchmark release checks remain incomplete as documented in SESSION-HANDOFF-VERIFICATION.md. Project Records' installed discovery and model behavior were verified in separate layers as documented in PROJECT-RECORDS-VERIFICATION.md. No plugin release, platform-wide semantic acceptance or remote CI success is asserted by these local results.
