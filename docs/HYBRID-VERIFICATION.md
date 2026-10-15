# Hybrid audit implementation verification

Status: **local implementation ready for authenticated semantic testing**. The owner requested notification when ready; the fifteen live-model runs are deferred until dedicated authentication is prepared. No commit, push or publication was performed.

## Implemented behavior

- Python produces protected snapshots and mechanical observations; every observation has a traceable semantic decision, and sources without observations still receive independent review.
- Assignments prefer complete source files, preserving exact chunk/directive coverage when splitting is necessary. Context requests use protected snapshots, including global sources.
- Independent verifiers assess proposed findings and observation decisions at exact content digests. The reconciler owns final decisions and can uphold objections with evidence and counterevidence.
- New or revised conclusions receive a bounded delta-verification pass; terminal adjudication cannot introduce unassessed rewrites. Missing verification remains incomplete, while a completed disagreement alone does not force partial status.
- Run schema 1.1 stores observation, assessment and adjudication ledgers. Legacy 1.0 reports remain readable. Baseline scope mismatches produce unassessed prior findings rather than false resolutions.
- Privacy corrections cover embedded PAT/bearer/PEM material, selected Claude MCP state, relocated state files, and preventing credential arguments from becoming helper references. Selected state views retain eligible scope headers and original line coordinates; integrity accounts for changes in those coordinates.
- `--source-claude-state` is an additive override used by schedule recipes to preserve the actual selected state file.

## Observed local checks

| Check | Result |
| --- | --- |
| Full pytest suite with native Codex 0.162.1 | 156 passed in 10.51 seconds |
| Ruff lint | Passed |
| Ruff format check | 68 files already formatted |
| Basedpyright via nvm Node | 0 errors, 0 warnings, 0 notes |
| Marketplace validation | Passed |
| Two independent ZIP builds | Byte-for-byte identical |
| Package contents | 50 files; maintainer tests, fixtures, caches and development environments excluded |
| LSP Intelligence | Unavailable: Missing executable: mcpls; no runtime installation attempted |

The native tests cover actual isolation/transport and the optional isolated Claude version probe. Their model transport fixture is synthetic; they do not establish semantic diagnostic accuracy.

## Review evidence

Implementation and review regressions were exercised before and after fixes. These include scoped-state privacy bypasses, helper-reference credential leakage, stale assessment digests, missing observation decisions, stale dispositions after rejected findings, revision without replacement, and unsupported modification recommendations hidden outside the findings list.

The final code review was performed by the implementer. No independent development reviewer was dispatched, following the approved delegation restriction. Runtime verifier independence is implemented but is not a substitute for an independent code review or the pending live semantic tests.

Evidence is retained under `.superpowers/sdd/2026-10-14-hybrid-semantic-audit/`:

- `progress.md`: task state, rulings and exceptions.
- `final-native-tests.txt`: full native-enabled suite output.
- `implementation.diff` and `changed-files.json`: scoped actual changes against the preserved initial tree.
- `package-first/PACKAGE-CONTENTS.txt` and `package-first/SHA256SUMS`: installable inventory and checksum.
- `package-verification.json`: package size, file count and deterministic comparison.

Package SHA-256: `7fb1b64abca44355aa281f9f9b3451141546f6ee7aec630fc657f1b83456d132`.

## Pending semantic acceptance

Five synthetic scenarios are prepared: intentional duplicate dismissal, discovery without a mechanical alert, policy preservation despite violating code, cross-source paraphrased contradiction, and requesting additional evidence before concluding. The runner schedules three repetitions each and retains every attempt.

Run from the repository's prepared uv environment after native authentication is available:

```sh
uv run --locked --no-env-file python -m tools.run_semantic_acceptance \
  /absolute/new-evaluation-directory \
  --model <explicit-model> --effort high \
  --auth-home /absolute/dedicated-auth-home \
  --codex-bin /absolute/native-codex
```

The destination must be new. Expectations remain outside audited source roots. A successful machine check requires an independent review of actual report meaning before semantic acceptance is claimed; the runner deliberately does not equate structural checks with factual correctness.

No live model requests, installed-skill behavior evaluation, Linux/WSL execution, OS timer firing, remote CI or publication was verified in this implementation phase. The existing dedicated default auth directory and supported credential variables were absent; credentials were never read or copied.
