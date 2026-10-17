# Project Records verification

Final source-faithful local candidate, 2026-10-16. Version **0.1.0**. No commit, push, global installation or publication was performed.

## Source and scope

Destination: The Codex Factory, branch `work/project-records`, worktree `.superpowers/worktrees/project-records` based on `ea7bd0a`.

Source: `~/Claude/the-claude-factory/.claude/skills/project-records`, path revision `fb86ddb226c3543fce491a70f4575107e6479341`. The source remains unchanged. MIT license and attribution are retained.

The three assets preserve the original content, formatting, tables, notices, icons, reusable entry blocks and fields. **Their only change is `.claude/maintainer` to `docs/maintainer` in documented paths.** Exact comparison and hashes are in `.superpowers/project-records/template-fidelity.json`.

The skill and references preserve the original structure and workflows. Changes adapt Claude-specific question/file tools, paths and fixed personal names, explicitly define target-project folder creation, and retain verified correctness safeguards. The full source comparison is `.superpowers/project-records/source-adaptation.patch`.

## First use and output location

Paths are relative to the selected user project, never the installed plugin directory. Explicit user/project paths take precedence.

| First action | Created when needed |
| --- | --- |
| Record an ADR | `docs/maintainer/decisions/ADR_<YYYY-MM-DD>_<slug>.md` |
| Open the first debt item | `docs/maintainer/technical-debt/pending-debt.md` |
| Resolve the first debt item | `docs/maintainer/technical-debt/resolved-debt.md` |

Installation alone creates none of these project documents. Configured protected/unwritable paths return a draft and blocker without automatic relocation or broader permissions. The default uses docs because native workspace-write protects .codex; see [official protected-path guidance](https://learn.chatgpt.com/docs/agent-approvals-security#protected-paths-in-writable-roots).

When creating ledgers, the complete original template body is preserved. Reusable Entry format comments remain intentional template material; completed entries contain no unfilled placeholders. Responsible people come from the actual decision/evidence, not the plugin author's identity.

## Local verification

Runtime: Python 3.14.8 through uv 0.13.0; nvm Node 26.11.1; explicit native Codex 0.162.1 binary. Locked dependencies unchanged.

| Gate | Result |
| --- | --- |
| Full pytest with explicit native binary | **170 passed**, no omitted native tests |
| Ruff | PASS |
| Python format check | 69 files unchanged |
| Basedpyright through nvm Node | 0 errors, 0 warnings, 0 notes |
| Marketplace validation | PASS |
| System Skill Creator validation | Valid skill |
| Isolated ZIP installation and native discovery | `project-records:project-records` enabled; no credentials copied |
| Original-template comparison | All three assets match after path-only substitution |
| Two final archive builds | Identical bytes, 12 current source files |

Evidence: `.superpowers/project-records/final-fidelity-*.txt`, `template-fidelity.json`, and native installation assertions in `tests/test_project_records.py`.

## Behavioral verification and corrections

The native corpus covers **20 distinct scenarios**: ADR, supersession, proposed replacement, collision, implicit invocation, generic accountable person, missing facts, grouping questions, default/custom/protected paths, first debt, second open debt before any resolution, duplicate prevention, DEBT-1000 allocation, corrupt IDs, verified resolution, failed regression, recurrence, partial move and existing issue tracking. The trivial-edit negative case is also represented within this coverage; scenario names and exact results are in `source-faithful-contract-checks.json`.

The machine report contains 20 named cases: adr, implicit, custom-path, generic-owner, supersede, proposed-replacement, collision, debt-new, second-open-debt, duplicate, resolve, failed-verification, partial-move, recurrence, missing-facts, batch, trivial, corrupt-ledger, tracked-issue and protected-override. Coordinator review checked actual resulting documents and relevant command events; schema/assertion results alone are not semantic acceptance.

Evidence is revision-bound, not a claim that every model call used identical inputs:

- `semantic-source-faithful/`: baseline after restoring original assets/reference structure. Exact tested source retained in `tested-source-faithful/`. One supersession failure and shortened-ledger behavior were found; retain those attempts.
- `semantic-final-fidelity/`: eight focused cases after clarifying full-template copying and confirmed-absent ledgers. Includes creation, debt, successful/failed resolution, recurrence, partial moves, second debt and Ada as accountable person. Exact tested source in `tested-final-fidelity/`.
- `semantic-supersession-fix/`: exact final product skill tested for reciprocal supersession filenames. The final installed source matches this candidate's seven input hashes.
- `source-faithful-contract-checks.json`: accepted observations for all 20 scenarios, mapping each to its actual evidence revision.

Specific findings and results:

1. Original generic no-template-comments wording caused new ledgers to omit sections/reusable blocks. Clarified copying the entire original template body and retaining the intended entry block. Targeted native debt output preserves criteria, maintenance, status legend, index and reusable block.
2. Read-both-ledgers wording was ambiguous before the first resolution. The baseline second-debt case already succeeded; no failing behavior is claimed. Clarified reading each existing ledger and treating confirmed absence as empty. Final case creates DEBT-002, preserves DEBT-001 and does not create resolved-debt.md.
3. Supersession metadata used ADR IDs without .md. Native failure retained; explicit filename instructions verified by a new native case. Reciprocal filenames now include .md and old reasoning/date remain intact.
4. The final resolution case ran both uv checks, saved and reread the complete resolution, and only then removed the pending entry. The failed regression kept debt pending; partial-move reconciliation preserved evidence.
5. Ada's ADR names Ada, with no attribution to Nery. Generic templates and procedures work independently of the maintainer's identity.

Earlier packaging findings remain corrected: strict allowlist, source symlink rejection and separate output directories to avoid overwriting another archive's checksum/inventory. Agent Context Audit default packaging remains covered by regression tests. Independent read-only review and coordinator rulings are retained under `.superpowers/project-records/`.

## Final package

Archive: `dist/project-records-source-first/project-records-0.1.0.zip`.

SHA256:

```text
c101aff9aabcbc577d56bac942330193e935cce491d74115845744ec15f2c8f7
```

Second build: `dist/project-records-source-second/`, byte-identical. Each includes PACKAGE-CONTENTS.txt and SHA256SUMS. Exactly 12 files: portable/native manifests, README, LICENSE, CHANGELOG, one skill, three references and three templates. No fixtures, tests, maintainer tools, reports, credentials, caches or generated project records are installed.

## Evaluation and limits

Plugin Eval was rerun on final source: plugin 58/100, skill 72/100. The generic rubric flags absent legal URLs, the full deferred-resource estimate, and a valid Markdown fragment link that its file-only link check does not resolve. The referenced file and Choose how to register heading exist and native invocation follows that reference. Coverage artifacts are unavailable for the instructions-only package.

Those numeric results are retained as tool output, not hidden or called passing. Owner direction is source fidelity and native Codex function; privacy/terms documents and score-driven source deletion are outside scope. No evaluator rules were changed or disabled.

LSP was unavailable (`Missing executable: mcpls`); no runtime was installed. Native Ruff/Basedpyright provide diagnostics. Behavioral runs used synthetic projects and a native default model, without a controlled repeated/model-cost benchmark. Installed-plugin discovery was tested separately from authenticated model behavior with repository-exposed copies of exact skill files. Interactive desktop behavior, other operating systems, remote CI and public installation were not tested. Skills guide model behavior and do not guarantee automatic invocation on every request.

The previous report and all earlier attempts remain under `.superpowers/project-records/verification-pre-fidelity.md` and sibling evidence folders; their checksums and scores are historical, not claims about this final package.
