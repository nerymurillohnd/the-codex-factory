# Hybrid Evidence and Semantic Audit Implementation Plan

> Approved in conversation; execute with `superpowers:executing-plans`. Development-agent delegation requires separate owner authorization. No commit, push or publication is included.

**Goal:** Python prepares protected evidence and observations; agents independently review every source, resolve candidates, discover additional defects and justify final decisions.

**Architecture:** Extend the existing Codex controller with typed observations, file-oriented packages, independent semantic verification and final reconciler adjudication. Preserve isolation, coverage and private artifacts.

**Tech Stack:** Existing uv-managed Python, JSON Schema, pytest, Ruff, Basedpyright via nvm Node and native Codex workers. No new runtime dependencies.

**Spec:** User-approved requirements and choices in this conversation, reproduced below.

## Decisions and constraints

- Include the hybrid core and three known privacy/discovery fixes; exclude new external-claim research and changes to either Claude alternative.
- Specialists resolve automatic observations and independently inspect every assigned source, including sources without observations.
- Prefer complete files; split oversized sources without dropping bytes or directive ownership. Context comes only from protected snapshots and authorized evidence.
- Independently assess every final finding and observation decision. The reconciler may uphold a challenged conclusion with explicit evidence and counterevidence. Disagreement alone is not partial; missing verification, essential evidence or coverage is.
- Sequence: provisional reconciliation, verification, adjudication, one delta verification, terminal selection among assessed versions. No unreviewed semantic rewrite at terminal selection.
- Preserve four concurrent jobs, 600-second job timeout, 1,800-second total timeout, 160,000-byte prompts, existing evidence limits and response repair.
- Same selected model/effort for every role; fresh contexts provide independence. No target hooks, commands, workflows or MCP execution.
- Preserve source/directive/finding IDs when meaning is unchanged. Keep current toolchain pins, English artifacts, external fixtures and private outputs.
- Preserve the unborn branch and existing untracked work. Capture before-state; no initial commit or worktree requiring history creation. Show actual diff, package contents, checksum and verification before any signed commit/push/publication.

## Review focus

1. Identical instructions with different activation can be intentional (Tasks 2, 4, 7).
2. An unflagged source and its final line can contain a semantic defect (Tasks 3, 4, 7).
3. Context requests must not reach originals, secrets or excluded roots (Tasks 1, 3).
4. A real quotation may not support the claim (Task 5).
5. Disagreement is not missing verification (Tasks 5, 6).

## Interfaces

- `Observation`: stable ID, kind, primary source, source ranges, evidence refs and factual text; no severity/remediation.
- `ObservationDecision`: observation ID, outcome (`confirmed`, `dismissed`, `reframed`, `unresolved`), rationale, evidence refs and associated findings.
- `ReviewPackage`: ID, source ID, owned chunk/directive/observation IDs.
- `SemanticAssessment`: target ID and digest, verdict (`supported`, `challenged`, `unverifiable`), rationale, evidence and counterevidence.
- `VerificationResult`: assessments, jobs and missing/unavailable checks.
- Exact ownership; positive observation decisions need real finding destinations; independent findings have empty observation IDs. Assessments bind to exact content. Context does not count as a primary assignment.

## Task 1: Privacy and source views

Create `source_views.py` and `tests/test_source_views.py`; modify privacy, discovery, snapshots, CLI and models.

- [x] RED: PAT, bearer and PEM in prose/structured formats; line preservation and innocent-policy controls.
- [x] RED: default/custom Claude home, including explicit override equal to conventional home.
- [x] RED: global and target-project MCP retained; other projects/personal state excluded from discovery, snapshots and requests.
- [x] GREEN: `resolve_claude_state_path(user_home, claude_home, *, overridden)` and `build_claude_state_view(text, target_root)`; preserve line provenance, label the filtered view, compare the same view at integrity check, reject malformed configuration.
- [x] Verify privacy/source-view/discovery/snapshot/reference tests and the full suite.

## Task 2: Observations and decisions

Create `observations.py` and `tests/test_observations.py`; extend models and domain/reconciliation contracts.

- [x] RED: stable IDs under line drift, aliases, separate scopes, unverified references and redacted placeholders.
- [x] GREEN: `build_observations(snapshot)` for `identical-text`, `unresolved-reference`, `shadowed-source`; normalized whitespace only, canonical aliases excluded, no inferred defects.
- [x] Add finding `observation_ids` and output `observation_decisions`; transport uses local indexes, persistence stable IDs.
- [x] Validate exact ownership, destinations, references and independent discoveries with `validate_observation_decisions(...)`.
- [x] Verify observation/contract tests and the full suite.

## Task 3: Coherent packages and protected context

Create `assignments.py` and `tests/test_assignments.py`; update review/evidence.

- [x] RED: complete source fits one assignment, oversized source preserves every chunk/directive, context is not double-counted, unflagged sources assigned.
- [x] GREEN: `build_review_packages(...)` packs contiguous chunks against actual serialized prompt size; up to 40 neighboring lines per side when space permits. No silent truncation.
- [x] Implement `read_source_evidence(snapshot, source_id, first, last)` through `source:<id>` requests: immutable snapshots only, <=200 lines and <=65,536 bytes.
- [x] Test unknown/unavailable IDs, oversized ranges and no original reads; impossible minimal input becomes incomplete.
- [x] Verify assignment/evidence/snapshot tests and the full suite.

## Task 4: Candidate resolution and independent discovery

Update specialist/reconciler prompts, review, coverage and tests.

- [x] RED: dismiss intentional duplicate, discover a finding without an observation, revise an assessment after evidence.
- [x] GREEN: require both semantic passes, policy/activation/exception checks, immutable observations and traceable revised assessments.
- [x] Validate observations as well as receipts/dispositions; repair then report incompleteness if necessary.
- [x] Reconcile sources and retained guidance, not only defects.
- [x] Verify review/reconciliation/evidence/regression tests and the full suite.

## Task 5: Independent verification and final authority

Create `verification.py`, verification/adjudication schemas and prompts, and verification tests; extend contracts/reconciliation.

- [x] RED: non-entailing quote, unjustified dismissal, missing/stale assessment.
- [x] GREEN: `verify_audit(...) -> VerificationResult` for every finding and observation decision with fresh bounded contexts and controlled evidence retrieval.
- [x] GREEN: `adjudicate_audit(...) -> ReconciledAudit`; explicit dispositions over all assessments, one delta verification, no unassessed terminal edits.
- [x] Test supported disagreement can complete; missing verification cannot; changed/new findings cannot bypass verification.
- [x] Verify verification/reconciliation/contracts and full suite.

## Task 6: Pipeline, reporting, compatibility

Update pipeline/report/baseline/CLI/models; preserve run schema 1.0 as `run-v1.json`, write 1.1.

- [x] RED: full lifecycle, legacy reports, partial results, scoped state, output boundaries.
- [x] GREEN: persist observation decisions, assessments/adjudications/dissent; distinguish confirmed, retained, unresolved and upheld-over-objection cases.
- [x] Preserve 0/1/2/3 statuses; disagreement alone is not incomplete.
- [x] Keep latest reading 1.0 with a legacy-verification label. Preserve finding IDs. Scope fingerprint mismatch/legacy missing scope means unmatched prior findings are unassessed, not resolved.
- [x] Update skill/product docs; verify integration/report/baseline/CLI and full suite.

## Task 7: Semantic acceptance and review package

Extend fixture definitions/materializer; add `tools/run_semantic_acceptance.py` and runner tests.

- [x] Five known-answer cases: intentional duplicate dismissed; unflagged semantic defect found; policy retained despite code violation; cross-source paraphrased contradiction; extra evidence requested before concluding.
- [x] Negative fixtures: unread tail, missing verifier, bad citations, injection, forbidden context, source changes and privacy canaries.
- [x] Runner uses explicit model, synthetic homes, records all attempts, usage, time and artifacts; expectations never enter worker inputs.
- [ ] Run five cases three times (15 real runs). Authentication unavailable is blocked semantic acceptance, not a pass. Assess meaning/evidence and preserved policy, not exact prose.
- [x] Run locked Ruff lint/format, nvm Node Basedpyright, complete pytest with native Codex, marketplace validation and two deterministic ZIP builds. Show diff/package/checksum/evidence for owner review.

## Acceptance

All sources and observations accounted for; independent discoveries allowed; all final items independently assessed at their exact digest; final reconciler authority with visible counterevidence; incomplete evidence never clean; privacy canaries absent across boundaries; legacy reports readable; fifteen semantic runs meet fixed criteria. Preserve failed attempts. Keep evidence under `.superpowers/`; no automatic remediation, commit, push or publication.
