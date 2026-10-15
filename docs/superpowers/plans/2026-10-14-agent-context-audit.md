# Agent Context Audit Implementation Plan

> **For agentic workers:** Implement this approved plan task by task with `superpowers:executing-plans`. Use checkbox steps to track progress. Additional implementation agents require the owner's authorization. The product's parallel audit workers are part of the approved product design, not authorization to delegate development.

**Goal:** Establish the public The Codex Factory marketplace and release Agent Context Audit: a parallel, cross-domain, read-only audit of the user-owned operating context that governs Codex and Claude Code.

**Architecture:** One packaged skill invokes a deterministic local controller. The controller inventories and snapshots eligible sources, launches isolated Codex review jobs in parallel, reconciles every completed contribution, and validates and renders one report with machine-readable status.

**Tech stack:** Python through uv; standard-library filesystem, hashing, process, JSON, TOML, and reporting facilities; PyYAML for YAML frontmatter; jsonschema for contract validation; Codex CLI for model execution. No product MCP server, hooks, remote service, or custom UI.

**Spec:** This document, especially sections 1–6, implements the owner's instruction-audit brief and subsequent decisions. Input brief: `instruction-audit-codex-plugin-prompt.md`, SHA-256 `04e426f0094beb6257acc1042e8f1b4bb60bb53d62fabe1de874ac102a6dcdd1`.

**Approval status:** Approved by the owner on 2026-10-14. Local implementation and testing are authorized. Show the final diff and package before any commit, push, or release publication.

## 1. Decisions and global constraints

| Item | Decision |
| --- | --- |
| Marketplace / repository | `the-codex-factory`, public repository `https://github.com/nerymurillohnd/the-codex-factory` |
| Catalog defaults | Display name **The Codex Factory**; category `Productivity`; installation policy `AVAILABLE`; authentication policy `ON_INSTALL`, without inventing an MCP/OAuth connection for a skills-only package |
| Plugin | **Agent Context Audit**, identifier `agent-context-audit` |
| Skill | `audit-agent-context` |
| First release | `0.1.0`; tag `plugin/agent-context-audit/v0.1.0` |
| License | MIT for repository-owned code and documentation; preserve applicable third-party notices |
| Owner and maintainer | Nery is the owner. Codex acts as co-maintainer: build, review, test, prepare releases, triage issues, and draft replies |
| Language | English for product code, configuration, documentation, fixtures, and release materials |
| Audit hosts | Codex primary; Claude Code optional as an audited host |
| Runtime | Codex CLI `0.162.1` baseline; uv-managed Python `>=3.11`; development interpreter `3.14.8` |
| Platforms | Release targets: macOS arm64 and Linux x86_64. WSL2 is documented but unverified until exercised; native Windows is outside v0.1.0's support promise |
| Invocation | Interactive local Codex skill, direct non-interactive local launcher, and scheduled execution of that same launcher |
| Parallelism | Up to four domain jobs concurrently by default; `--jobs 1..4` permits resource control |
| Authentication | Dedicated audit Codex home with native ChatGPT login; existing `CODEX_API_KEY` / `CODEX_ACCESS_TOKEN` environment authentication also supported |
| Report location | `${XDG_STATE_HOME:-~/.local/state}/the-codex-factory/agent-context-audit/runs/<repository-id>/<UTC-timestamp>-<UUID>/` |
| External links | Fixed official knowledge URLs may be fetched without local content in requests. Other HTTP(S) destinations require explicit per-domain authorization; this question was unanswered, so this is the conservative default |
| Approval gates | Approval of this written plan before implementation. A later review of the concrete diff and package before commits, pushes, or publication |

### Scope

- Audit eligible user-owned instructions, rules, memory, custom agents, legacy command files, saved workflows, output styles, configuration, hook definitions, and relevant user-owned files they reference.
- Include user-level sources affecting the target project regardless of where the plugin is installed. Resolve actual source homes before starting isolated workers; never substitute the audit home for the user's source home.
- Preserve the agreed distinction: legacy `commands/*.md` and saved workflows are in scope; `skills/` packages are excluded. This source-format boundary is intentional even where Claude uses the same mechanism for commands and skills.
- Exclude all plugin-provided components, this plugin, managed policy, credentials, environment-secret files, transcripts, ordinary application logs, and unrelated repositories as audit targets. Eligible user-owned plugin enablement entries remain in scope. Enabled plugins are not defects merely because they are enabled.
- Excluded components may support a finding about an eligible source. They cannot receive findings or remediation recommendations themselves. Uncertain provenance is reported explicitly rather than guessed.
- Inspect declarative sources and referenced user-owned scripts without executing them. Do not start configured MCP servers, run hooks, import workflow JavaScript, or execute repository-defined commands to discover their behavior.
- If Claude is absent and no eligible Claude sources exist, skip that domain cleanly. If sources exist without the CLI, perform a labeled file-only review against the documented knowledge version and disclose missing runtime evidence.

### Review focus

1. A symlink aliases an excluded plugin, a secret file, or a network path: classify before following; prevent source-boundary escape. Tested in Task 2.
2. A large file has its only defect on the last line: account for every chunk and reject silent truncation. Tested in Tasks 2 and 4.
3. A worker, report, or contribution is missing despite exit code zero: emit a visible non-success result. Tested in Tasks 3–5.
4. User edits or a second audit occur concurrently: preserve both runs and report changed inputs without attributing them to the auditor. Tested in Tasks 2 and 5.
5. Host instructions, hooks, skills, or policy enter an audit unexpectedly: reject an unsafe isolated run and disclose parent-session exposure. Tested in Tasks 3 and 6.

## 2. Research, corrections, and evidence

Research date: **2026-10-14**. Development observations are not third-party compatibility claims. The directory is empty and not a Git repository; the selected GitHub repository was not found in the owner's account. Installed tools observed: Codex CLI `0.162.1`, Claude Code `2.1.300`, uv `0.13.0`, and uv-managed Python `3.14.8`. Git is configured for SSH-signed commits and tags; actual signing remains untested.

OpenAI Docs MCP was used first to search and fetch official pages. It subsequently returned HTTP 403 challenges; later checks used the official web pages and local CLI help. The Docs MCP is a development aid, not a runtime dependency.

### Claim-verification table

`verified` means the stated narrow claim has direct documentary, source-code, or local evidence; the **evidence level** column distinguishes these. It does not mean the complete plugin or invocation mode has passed an end-to-end test.

| Claim | Status / evidence level | Exact supporting excerpt | Source | Version / date checked | Dependent components |
| --- | --- | --- | --- | --- | --- |
| Codex accepts a GitHub marketplace source | verified; documented and CLI help observed; registration not yet tested | `codex plugin marketplace add owner/repo` | [Packaging](https://developers.openai.com/plugins/build/plugins#add-a-marketplace-from-the-cli) | CLI 0.162.1 / 2026-10-14 | Public distribution and clean install |
| A portable package may retain a Codex compatibility fallback | verified; documented, install pending | “Existing `.codex-plugin/plugin.json` files remain supported as a compatibility fallback.” | [Packaging](https://developers.openai.com/plugins/build/plugins) | 2026-10-14 | Portable manifest and generated compatibility overlay |
| Local catalog paths resolve from the marketplace root | verified; documented, install pending | “relative to the marketplace root” | [Marketplace metadata](https://developers.openai.com/plugins/build/plugins#marketplace-metadata) | 2026-10-14 | Catalog path validation |
| Exec emits JSONL and can write its final response separately | verified; documentation and CLI help observed | “newline-delimited JSON events” | [Non-interactive execution](https://learn.chatgpt.com/docs/non-interactive-mode) | CLI 0.162.1 / 2026-10-14 | Runtime adapter, metrics, report transport |
| `--allowedTools` and `--output-format` are not Codex exec options | corrected; both parser failures observed, exit 2 | `unexpected argument '--allowedTools' found`; `unexpected argument '--output-format' found` | Local `codex exec` parser; [Codex reference](https://learn.chatgpt.com/docs/developer-commands#codex-exec), [Claude reference](https://code.claude.com/docs/en/cli-reference) | CLI 0.162.1 / 2026-10-14 | Launcher examples and scheduler recipes |
| Global AGENTS instructions are loaded separately from the project byte budget and user TOML | corrected; official source inspected; full isolation test pending | `load_from_codex_home`; `tokio::fs::read(path.as_path())` | [Global instruction provider](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/codex-home/src/instructions/mod.rs), [project assembly](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/core/src/agents_md.rs) | 0.162.1 / 2026-10-14 | Dedicated audit home; no claim that `--ignore-user-config` alone isolates instructions |
| Hooks can be disabled, subject to managed requirements | verified; documented; hook canary pending | `hooks = false` | [Hooks](https://learn.chatgpt.com/docs/hooks#turn-hooks-off) | 2026-10-14 | Isolated process configuration and policy refusal |
| Custom-agent sandbox settings do not independently override the parent | corrected; documented | “don't override the parent configuration” | [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents#custom-agent-file-schema) | 2026-10-14 | Use independently configured worker processes |
| Permission profiles are beta; restricted reads work in the local macOS probe | verified for the read probe only; profile facility is beta; Linux/writes untested | “Permission profiles are under active development and may change.” | [Permissions](https://learn.chatgpt.com/docs/permissions); local output `allowed_read=passed`, `outside_read=blocked` | 0.162.1 / 2026-10-14 | Mandatory capability probes; no legacy-sandbox/profile mixing |
| Native authentication can use a separate Codex home without copying credentials | verified; documented; dedicated login pending | “file stores credentials in auth.json under CODEX_HOME” | [Authentication](https://learn.chatgpt.com/docs/auth#credential-storage) | 2026-10-14 | One-time setup and isolated auth profile |
| Codex supports explicit skill invocation | verified; documented; packaged invocation pending | “explicit `$skill` invocation still works” | [Skills](https://learn.chatgpt.com/docs/build-skills) | 2026-10-14 | `audit-agent-context` skill |
| Claude imports have bounded depth and AGENTS behavior is version-dependent | verified; documented; selected fixtures pending | “maximum depth of four hops”; “requires Claude Code v2.1.277 or later” | [Claude memory](https://code.claude.com/docs/en/memory) | 2.1.300 reference / 2026-10-14 | Versioned host loaders and import graph |
| Legacy commands and skill packages share a Claude mechanism | corrected; documented; owner settled the scope boundary | “same mechanism as skills” | [Claude directory reference](https://code.claude.com/docs/en/claude-directory) | 2026-10-14 | Include legacy commands; exclude skill packages |
| Saved Claude workflows are user/project source files; their runtime is not a Codex API | verified; documented; workflows are read, never run | “No direct filesystem or shell access from the workflow itself” | [Claude workflows](https://code.claude.com/docs/en/workflows) | 2026-10-14 | D3 discovery and architecture comparison |
| Local app schedules need an available local host | verified; documented; scheduled execution pending | “Keep the computer on and the app running” | [Scheduled tasks](https://learn.chatgpt.com/docs/automations) | 2026-10-14 | Local schedule documentation and coverage labels |
| uv supports no-dotenv, no-sync, and frozen execution | verified; CLI help observed and official reference opened | “Avoid reading environment variables from a .env file”; “Avoid syncing the virtual environment” | [uv CLI](https://docs.astral.sh/uv/reference/cli/#uv-run) | uv 0.13.0 / 2026-10-14 | Setup/runtime separation and lock preservation |
| Native user schedulers have calendar-based triggers | verified as documentation only; recipe execution pending | `StartCalendarInterval`; `OnCalendar=` | [Apple launchd guide](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html), [official systemd timer source](https://github.com/systemd/systemd/blob/main/man/systemd.timer.xml) | 2026-10-14 | Printed scheduler recipes and one-shot verification |

All other behavior below is a product decision or an implementation acceptance requirement, not a claim of an already verified implementation. No unverified host capability is treated as an unconditional release promise.

### Release-note review

- Codex installed baseline: [0.162.1](https://github.com/openai/codex/releases/tag/rust-v0.162.1). The eight preceding stable releases reviewed were [0.162.0](https://github.com/openai/codex/releases/tag/rust-v0.162.0), [0.161.0](https://github.com/openai/codex/releases/tag/rust-v0.161.0), [0.160.1](https://github.com/openai/codex/releases/tag/rust-v0.160.1), [0.160.0](https://github.com/openai/codex/releases/tag/rust-v0.160.0), [0.159.3](https://github.com/openai/codex/releases/tag/rust-v0.159.3), [0.159.2](https://github.com/openai/codex/releases/tag/rust-v0.159.2), [0.159.1](https://github.com/openai/codex/releases/tag/rust-v0.159.1), and [0.159.0](https://github.com/openai/codex/releases/tag/rust-v0.159.0).
- Later published Codex prereleases inspected: `0.163.0-alpha.1`, `.2`, `.4`, `.5`, `.8`, `.9`, `.10`, `.10.1`, `.11`. Their release entries contained no detailed change notes; do not infer stable compatibility from their presence.
- Relevant changes: 0.159.0 removed the bundled plugin-creator skill; 0.160.0 changed plugin-loading caching; 0.161.0 clarified credential backends and changed permission propagation; 0.162.0 changed plugin/skill snapshots and Linux sandbox behavior; 0.162.1 fixed startup compatibility checks around explicit feature overrides. Use supported manual packaging and a controlled local runtime, not an assumed bundled scaffold.
- Claude installed baseline: [2.1.300](https://github.com/anthropics/claude-code/releases/tag/v2.1.300). The eight preceding releases reviewed were [2.1.299](https://github.com/anthropics/claude-code/releases/tag/v2.1.299), [2.1.296](https://github.com/anthropics/claude-code/releases/tag/v2.1.296), [2.1.295](https://github.com/anthropics/claude-code/releases/tag/v2.1.295), [2.1.294](https://github.com/anthropics/claude-code/releases/tag/v2.1.294), [2.1.293](https://github.com/anthropics/claude-code/releases/tag/v2.1.293), [2.1.292](https://github.com/anthropics/claude-code/releases/tag/v2.1.292), [2.1.291](https://github.com/anthropics/claude-code/releases/tag/v2.1.291), and [2.1.290](https://github.com/anthropics/claude-code/releases/tag/v2.1.290). No later release appeared in the checked list.
- Relevant Claude changes concern settings and symlink read restrictions, restored scheduled wakeups, disabled MCP entries in headless sessions, hook input validation, and hook/model behavior. These justify version-specific knowledge and static inspection; the auditor must not launch Claude to execute audited customizations.
- Refresh release/issue checks before implementation relies on a changed capability and again before publication. Record the exact evidence version in the runtime knowledge bundle.

### Issue tracker and prior art

| Source and checked status | Consequence for this design |
| --- | --- |
| [Codex #45482](https://github.com/openai/codex/issues/45482), open | Do not rely on per-agent `sandbox_mode`; current official agent documentation describes parent inheritance. Configure each isolated exec worker directly |
| [Codex #42172](https://github.com/openai/codex/issues/42172), open | A successful process exit can accompany unusable reads on reported Windows versions. Validate contributions and read capabilities; no native Windows promise |
| [Codex #51546](https://github.com/openai/codex/issues/51546), open | Root-only portable manifests have a reported namespace-discovery defect. Keep a generated matching compatibility overlay and prove clean discovery; the workaround is not yet locally validated |
| [Codex #22078](https://github.com/openai/codex/issues/22078), open | Enablement or catalog presence does not prove skill availability. Fresh-session invocation is a release gate |
| [Codex #31654](https://github.com/openai/codex/issues/31654), open | Validate actual component existence and catalog path resolution instead of trusting a scaffold |
| [Claude #94463](https://github.com/anthropics/claude-code/issues/94463), open | Preserve logical loaders and canonical file identities; distinguish duplicate loading from duplicate physical files |
| [Claude #97500](https://github.com/anthropics/claude-code/issues/97500), open | First-turn headless mentions have a reported duplicate-load case. Report source semantics without asserting that a fresh headless transcript proves normal loading |
| [Claude #73335](https://github.com/anthropics/claude-code/issues/73335), closed | The exact fixing release was not established; do not treat closure as proof that every symlink case is fixed |
| [Claude #100410](https://github.com/anthropics/claude-code/issues/100410), open feature request | A Claude workflow controller cannot directly perform deterministic filesystem work. Its runtime is a design reference, not a dependency for this Codex product |

Prior art inspected: [agnix](https://github.com/agent-sh/agnix), [Instruction Audit](https://github.com/iU688/instruction-audit), and Claude's native [`/doctor prompt-audit`](https://code.claude.com/docs/en/memory#audit-your-instruction-files). Adapt the ideas of explicit integrity status and independently checked evidence, not unsupported generic-removal rules. Implement independently; credit any later code adaptation and preserve its verified license. No prior-art executable becomes a product dependency by default.

## 3. Architecture and contracts

### Alternatives

These are design-fit estimates, not measured benchmark scores. Scale: 1–5, higher is better. **Eff** means lower token/runtime cost; **Modes** covers interactive, headless, and scheduling; **Dist** covers portability/distribution.

| Option | Coverage / precision | Isolation | Parallelism | Eff | Reproducibility | Failure handling | Modes | Dist | Maintenance |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| One skill/model pass | 2 | 1 | 1 | 5 | 2 | 2 | 3 | 5 | 5 |
| Prompt-led coordinator and domain auditors | 4 | 2 | 5 | 3 | 2 | 3 | 3 | 4 | 3 |
| Native Codex custom-agent workflow | 4 | 3 | 5 | 3 | 3 | 3 | 4 | 3 | 3 |
| **Deterministic controller + isolated parallel model reviews** | **5** | **4** | **4** | **3** | **5** | **5** | **5** | **4** | **3** |

Choose the hybrid. It makes scope, scheduling, output validation, and failure handling code-controlled while retaining semantic review. Every review and reconciliation job uses the caller's audit `--model`/`--effort` when supplied, otherwise the isolated CLI's defaults. Do not import the audited project's model/provider configuration as execution policy. Report the resolved model/usage when observable, otherwise mark it unavailable. Claude's dynamic workflow runtime is not packaged as a Codex capability. Do not discard failed reviewers with `filter(Boolean)` or its equivalent.

### Pipeline

1. **Preflight:** validate target, output boundaries, authenticated audit runtime, knowledge coverage, and effective isolation. Capture the original source homes and invocation assumptions.
2. **Inventory:** enumerate all eligible sources, provenance, loaders, load mode, imports/references, hashes, and line counts. Include ignored/uncommitted local sources. Account for exclusions and unreadable candidates.
3. **Snapshot and evidence:** read eligible sources completely in bounded chunks, redact sensitive configuration values, preserve original line numbering, and record exact chunk hashes. Collect repository facts without executing repository commands.
4. **Parallel review:** D1 Codex instructions/memory; D2 Claude instructions/rules/memory; D3 custom agents/legacy commands/workflows/output styles; D4 behavior-shaping configuration and user-owned referenced helpers. Skip absent domains explicitly; shard only for context limits.
5. **Reconciliation:** consume every completed domain result and deterministic topic-index candidate. When results exceed the context bound, reconcile bounded topic/source batches and merge them with an explicit contribution/candidate ledger; no input may disappear through summarization or truncation. Compare hosts, scope, precedence, duplication, overlap, and placement. For disputed findings, return only contested items and evidence to the owning reviewer: one challenge round by default, two maximum if explicitly requested. Retain unresolved disagreement and both evidence trails.
6. **Validation and rendering:** re-inventory for added/deleted sources, re-hash all original sources, compare Git metadata, validate coverage and citations, assign stable IDs and baseline changes, then atomically write one report and status.

The controller may satisfy bounded structured requests for additional eligible local evidence; model jobs never receive arbitrary command or network execution. Allow two evidence-request rounds per job and one repair attempt for malformed structured output. If proof is still missing, preserve `investigate`/partial status rather than inventing it. Default job timeout: 600 seconds; overall timeout: 1,800 seconds; both configurable. Cancellation stops and waits for all owned children before final status is written.

### Source and knowledge handling

- Preserve logical path, canonical identity, ownership/provenance, applicable hosts, load conditions, and reference edges separately. One physical file may have several host contexts.
- Use the hosts' versioned discovery rules, including configured roots, profiles, trust, fallbacks, imports, and conditional scopes. Do not infer Claude precedence from Codex or mark an optional source dead merely because it is inactive in the assumed invocation.
- Codex knowledge covers global/project AGENTS selection, configured fallbacks/root discovery, user/project config, custom agents, exec-policy sources, hooks, MCP declarations, and applicable editable memory artifacts. Claude knowledge includes local/global/nested instructions, rules/imports, agents and agent memory, legacy commands, saved workflows, output styles, settings, MCP declarations, and auto memory.
- Never read credential stores, `.env`, `.dev.vars`, or equivalent secret files. In mixed behavior configuration, redact credential-like values before any model or report output and identify redacted ranges. If a redaction hides a fact necessary to decide an issue, disclose that verification gap.
- Do not follow network symlinks or contact discovered URLs by default. Authorized external checks send no source excerpts or credentials, reject private/local destinations and unsafe redirects, and distinguish restricted/unverified links from proven broken links.
- Keep platform rules, documented source maps, coverage versions, short supporting excerpts, source URLs, and checked dates in one runtime `references/platform-knowledge.json`. Private per-run document caches stay outside the product. No copied documentation corpus is published.
- Default to live retrieval of the fixed official source map plus the bundled versioned baseline. Fetches contain no audit content. Unavailable, materially changed, contradictory, or out-of-version knowledge is visible in the report and cannot support an unconditional complete status. `--offline` uses the baseline explicitly and reports its freshness limits.

### Core data contracts

Use strict JSON Schemas with version `1.0`, reject unknown structural fields, and apply semantic validators after schema validation. Define the corresponding Python types in `models.py`.

- **SourceRecord:** `source_id`, logical/canonical path, `provenance`, `scope`, host/load-context array, `load_mode`, `sha256`, byte/line counts, redacted ranges, reference edges, assigned domain/shards, and analysis status/reason. Load modes: `always`, `conditional`, `on-demand`, `config-only`, `dead`.
- **ChunkReceipt:** source/context ID, original line range, fragment index where necessary, payload digest, actual submission digest, reviewer/job ID, and result acknowledgement. Bound chunks at 200 lines or 16 KiB; split oversized individual lines into byte fragments without dropping data. Bound each review input at 64 KiB of source payload and retain overlap for cross-chunk context.
- **DirectiveDisposition:** source/context ID, line range, normalized topic/subject, disposition, and evidence/reason. Every identified instruction gets `keep`, `remove`, `merge`, `move`, `revise`, or `investigate`; headings/comments need not be invented as instructions.
- **Finding:** stable ID; primary category and tags; severity/confidence; source/line/excerpt; related references; `conflicts_with`; evidence with provenance; impact; disposition; rationale/trade-offs; move destination; proposed replacement for revise/merge; dissent where present.
- **DomainResult:** domain/shard/job identifiers, input digests, completion state, receipts, dispositions, findings, evidence requests, unresolved gaps, and observed usage/timing. Missing jobs and extra/unassigned claims cannot pass silently.
- **RunResult:** metadata, source manifest, domain states, knowledge/capability labels, all validator results, reconciled findings/dispositions, baseline changes, cost/usage, report path, and final status.

Supported finding categories are all eleven from the brief: `false`, `wrong`, `obsolete`, `dead`, `ambiguous`, `duplicated`, `overlapping`, `misplaced`, `contradictory`, `redundant-with-defaults`, and `non-conformant`. Impact values are `correctness`, `reliability`, `context-cost`, and `maintenance`.

Severity values are `critical`, `high`, `medium`, `low`, and `info`; confidence is `high`, `medium`, or `low`. Provenance is `user-owned`, `plugin-provided`, `managed`, or `unknown`. Domain completion is `complete`, `skipped-absent`, `partial`, or `failed`; source analysis is `analyzed`, `excluded`, `skipped`, `unreadable`, `changed-during-audit`, or `failed`. None of these states substitutes for the final integrity gates.

For default-redundancy findings, require repository evidence or a current official native-default reference. Model-only judgment is low confidence and cannot recommend removal. Preserve instructions expressing user intent, policy, security boundaries, or non-obvious constraints.

Coverage validation proves complete source reads and chunk delivery/acknowledgement, not a model's private attention or reasoning. Reject `analyzed` when ranges or byte fragments are missing. Citation ranges must exist and excerpts must match the corresponding sanitized snapshot.

Stable IDs must not depend on line numbers, severity, run time, or directory iteration order. Base fingerprints on normalized source context, category/subject, and conflict relationship; preserve existing IDs for validated baseline matches. Ambiguous moved/rewritten matches remain explicit candidates rather than asserted identities. Unchanged inputs must produce stable IDs and materially equivalent findings, not necessarily identical prose.

## 4. Runtime, entry points, and report behavior

### Public launcher

Implement `plugins/agent-context-audit/scripts/audit.py` and importable `agent_context_audit.cli:main` with these commands:

| Command | Contract |
| --- | --- |
| `setup` | Prepare the isolated uv runtime and dedicated authentication home only when explicitly invoked. Print the native Codex login command; the user completes authentication. Never copy/read an existing auth file or install into the owner's normal setup |
| `audit --root PATH` | Run the single pipeline; without `--root`, use the caller's Git top-level directory, or the caller's directory outside Git. Preserve launch CWD separately for loading assumptions |
| `latest --root PATH` | Print the newest run's status and absolute report path without rerunning an audit or modifying a repository |
| `schedule-example --scheduler app\|launchd\|systemd --root PATH` | Print a recipe only, using resolved absolute executable/target paths and output handling. Template options: `--hour` (default 9), `--minute` (default 0), and optional `--weekday` (`mon`…`sun`). The default is a daily 09:00 local-time example, not an installed schedule |

Audit options: `--output-dir`, `--baseline`, `--source-codex-home`, `--source-claude-home`, `--codex-bin`, `--model`, `--effort`, `--jobs`, `--challenge-rounds`, `--job-timeout`, `--timeout`, `--offline`, and repeatable `--allow-domain`. Defaults are fixed above; validate before creating a run. The repository ID is the first 24 hex characters of SHA-256 over the canonical target-root path; worktrees retain distinct run histories. Stable finding IDs use relative source identity rather than this output key. `--output-dir` remains a parent for a unique run directory and never overwrites a previous report. A destination inside the target repository requires the caller's explicit override and is labeled as such.

Do not install a launcher on PATH implicitly. Documentation and the skill resolve the installed plugin root and use its absolute entrypoint. After explicit setup, use the locked uv environment without syncing, downloading, reading dotenv files, or inheriting unrelated uv project selection. Resolve executables outside the audited repository and pass arguments as arrays rather than shell-generated commands.

### Isolation and authentication

- Capture source roots first. Give each analysis process the dedicated audit `CODEX_HOME` through its child environment only; never repurpose or overwrite the calling session's `HOME`/`CODEX_HOME` variables.
- Keep the persistent native authentication profile separate from per-run runtime files. Initialize it through Codex's supported login flow or existing environment credentials. Native authentication refreshes remain confined to that profile; the audit controller never parses credential values.
- Use a private neutral working directory with no applicable project config from the target or ancestor repositories. Reject unexpected config origins. The audit home must contain no user AGENTS instructions or foreign customizations.
- Run exec with `--ignore-user-config`, `--ignore-rules`, `--ephemeral`, `--strict-config`, `--json`, `--output-schema`, and explicit non-interactive approval policy. Disable hooks, memories, plugins, apps, browser/computer-use, web search, shell execution, and native nested delegation for review jobs. Disable bundled skills and host skills by documented path selectors; omit automatic skill instructions. Verify the effective skill/config surface using supported local inspection before analysis. Do not depend on the under-development `skip_host_skill_discovery` feature.
- Configure a permission profile with denied default filesystem access, necessary runtime reads, and read-only sanitized evidence; model-command networking is disabled. Do not combine this profile with legacy `--sandbox`/`sandbox_mode` settings, which can override profile selection.
- Before using real audit payloads, run harmless read/write/network and hook canaries in owned temporary paths. Refuse an unsupported sandbox or enforced policy that prevents isolation. Never bypass managed policy, broaden permissions automatically, or silently downgrade to an exposed worker.
- Only the trusted renderer writes report/status/evidence files in the private run directory. Use private directory/file modes, safe non-symlink output boundaries, and atomic replacement within a run. Reject model-generated destinations and active content in quoted source excerpts.
- Treat every audited source and repository excerpt as untrusted data. Reviewer instructions must explicitly reject embedded attempts to change the task, claim higher authority, reveal unrelated data, execute helpers, or redirect output/network access. Typed evidence requests cannot grant new capabilities.
- A parent interactive session may already have loaded instructions or executed hooks before the plugin is invoked. Record that exposure explicitly. Full isolation validation requires a clean entry session or the direct isolated launcher; an exposed/unverified parent cannot receive an unqualified isolation guarantee. An interactive entry may still provide findings, with non-success status if an applicable non-interference guarantee cannot be verified.
- Host-managed telemetry and model-provider retention are outside this plugin's control. Disable controllable prompt/response exporters; disclose or refuse a strict mode when managed settings prevent the stated data boundary. Do not claim absolute privacy from a shell sandbox alone.

### Invocation modes

| Mode | Source access and behavior | Release verification |
| --- | --- | --- |
| Interactive Codex CLI skill | Resolve installed skill, call the same launcher, show report/status; parent exposure is labeled | Fresh-session explicit invocation in an isolated test home, then a complete fixture run |
| Local desktop Codex skill | Same local launcher and contracts when local execution and the CLI are available; no cloud-orchestrator assumption | Verify supported loading and invocation through the local runtime; label untested desktop UI separately and do not present it as an observed UI result |
| Direct headless launcher | Original working tree, local-only files, and eligible user roots are data; workers run separately | Real isolated `codex exec` workers and validator-negative cases |
| Local app schedule | Choose the local project/original path, not an incomplete worktree substitute; local host/app must be available | Manual scheduler-equivalent run plus a one-shot test schedule in the isolated test environment |
| launchd / systemd user schedule | Execute the same absolute launcher against the original path; scheduling is user installed | Validate generated configuration and execute a one-shot isolated scheduled run on the corresponding OS before calling that recipe tested |
| CI or remote/cloud-only checkout | Only mounted/available sources can be audited. Missing user/local-only sources are reported | Restricted-coverage fixture; never advertise a repository checkout as full local coverage |

The skill has one entry and supports normal audit/latest/setup guidance. Its instructions stay focused; schemas and long reference material live outside `SKILL.md`. Do not assume a Claude `/plugin:command` string is a Codex invocation API. A free-form prompt is not a validator or an orchestration contract.

### Report and status

Write exactly one primary `report.md` and a canonical `status.json` with the machine-readable RunResult. Per-domain JSON/evidence inside the private run directory is supporting material, not additional primary reports. Preserve completed reports; remove only temporary files owned by the current run according to the documented retention policy. Do not automatically prune history.

The Markdown report contains metadata; full coverage manifest and validators; executive summary; all evidence-backed findings; per-instruction dispositions; cross-domain topic/precedence analysis; a prioritized dependency-aware remediation plan; limitations/dissent; new/resolved/persisting/regressed baseline findings; and wall time/token usage by role when available. Missing metrics are `unavailable`, not zero. Proposed edits are report text only.

| Exit | Machine status | Meaning |
| ---: | --- | --- |
| 0 | `complete-clean` | All applicable completeness and integrity gates pass; no findings |
| 1 | `complete-with-findings` | All applicable gates pass; findings exist |
| 2 | `partial` | Useful results exist, but a source, contribution, verification, freshness, or applicable isolation guarantee is incomplete |
| 3 | `failed` | Unsafe/unusable preflight, invalid run, no usable analysis, missing primary report, or fatal integrity/rendering failure |

Priority is failed > partial > findings > clean. No eligible-source discovery can silently count as a successful audit when expected roots were inaccessible. User-caused concurrent source/Git changes produce explicit changed-during-audit evidence and partial status; do not claim causation or overwrite the user's work.

## 5. File structure and implementation tasks

The repository is a multi-plugin marketplace; plugins are independently versioned and distributable. Keep maintainer tooling, fixtures, and development reports outside the installed plugin.

| Area | Files and responsibility |
| --- | --- |
| Marketplace | `.agents/plugins/marketplace.json`; root README, MIT license, contribution/security/release guidance, issue/PR templates and labels |
| Plugin identity | `plugins/agent-context-audit/plugin.json` is canonical; `.codex-plugin/plugin.json` inside that plugin is a generated, matching compatibility overlay; plugin README/changelog |
| User entry | `skills/audit-agent-context/SKILL.md`, optional UI-only `agents/openai.yaml`, and `scripts/audit.py` under the plugin root |
| Runtime | Plugin `src/agent_context_audit/`: `cli.py`, `models.py`, `discovery.py`, `snapshot.py`, `knowledge.py`, `runtime.py`, `review.py`, `reconcile.py`, `report.py`, `baseline.py`, `scheduling.py` |
| Contracts and knowledge | Plugin `schemas/` for source, domain, and run contracts; `references/platform-knowledge.json` and concise reviewer/reconciler prompts |
| Environments | Root maintainer `pyproject.toml`/`uv.lock`; standalone plugin `pyproject.toml`/`uv.lock`. Lock compatible published dependency versions after primary-source verification; no root-workspace dependency in the installed package |
| Validation and delivery | Root `tools/validate_marketplace.py`, `tools/package_plugin.py`, `tests/`, synthetic fixture repositories/homes, and GitHub validation/release workflows |

No runtime module may call the output writer with an audited path. Domain prompts are resources, not unsupported packaged Codex agent definitions. Avoid speculative helper components.

All runtime filenames and signatures in the tasks below refer to the declared `plugins/agent-context-audit/src/agent_context_audit/` modules. All contract/support types are defined in that directory's `models.py` before later tasks consume them.

### Task 1: Foundation, package identity, and strict contracts

**Interfaces:** Define `Target`, `SourceRoots`, `KnowledgeBundle`, `Inventory`, `AuditSnapshot`, `RunOptions`, `DomainResult`, `DomainResults`, `ReconciledAudit`, `RunState`, `RunOutcome`, `ValidationError`, `CoverageResult`, `CodexRuntime`, `ReviewRequest`, `CapabilityReport`, `Baseline`, `BaselineChanges`, `RuntimePaths`, and `CalendarSpec` in `models.py`, with JSON Schemas matching section 3. `Target` preserves canonical root, launch CWD, and observed Git state. `Baseline` carries finding history needed to distinguish regression from a new finding. `CalendarSpec` holds validated hour/minute and an optional weekday in local time. `validate_marketplace(root: Path) -> list[ValidationError]` checks every catalog/component path and version.

- [ ] Initialize local Git after plan approval, without an initial commit. Create the root maintainer environment, standalone plugin environment, canonical metadata, generated overlay, and schema files.
- [ ] Write and run failing tests `test_catalog_rejects_escape`, `test_catalog_rejects_missing_skill`, `test_overlay_identity_matches_canonical`, and `test_contract_rejects_missing_conflicts_with`. Assert rejection of each seeded invalid input.
- [ ] Implement validators/generation and run those tests to passing; verify that a deliberately invalid fixture still fails for its intended reason.
- [ ] Validate both manifests against current applicable schema/guidance and inspect the installable file list. No account-private plugin creation or installation into the owner's normal environment.

### Task 2: Full inventory, snapshots, and coverage

**Interfaces:** `discover_sources(target: Target, roots: SourceRoots, knowledge: KnowledgeBundle) -> Inventory`; `build_snapshot(inventory: Inventory, target: Target, run: RunState) -> AuditSnapshot`; `validate_coverage(snapshot: AuditSnapshot, results: DomainResults) -> CoverageResult`.

- [ ] Add failing discovery fixtures for both hosts, user/project/nested roots, fallback/override precedence, configured profiles, imports and cycles, shared files, scoped rules, legacy commands, workflows, subagent memory, mixed configurations, plugin/managed exclusions, symlink aliases, network links, untracked sources, no Git, and unborn HEAD.
- [ ] Add `test_last_line_is_in_coverage`, `test_oversized_line_has_all_fragments`, `test_secret_paths_never_open`, `test_plugin_alias_is_excluded`, `test_new_source_during_run_is_detected`, and `test_redaction_preserves_line_numbers` with concrete source/receipt/hash assertions.
- [ ] Implement discovery/snapshotting, exact duplicate indexing, reference checks, source re-inventory, and Git observation. Invoke trusted Git without optional index writes, external diff/text conversion, or fsmonitor execution; never run a project alias or hook.
- [ ] Run the focused tests and independently inspect the generated manifest and chunk ledger. Validate union coverage `1..N` and every long-line fragment; do not accept a model's coverage claim by itself.

### Task 3: Isolated Codex execution and controlled setup

**Interfaces:** `prepare_runtime(options: RunOptions, run: RunState) -> CodexRuntime`; `run_review_job(runtime: CodexRuntime, request: ReviewRequest) -> DomainResult`; `probe_isolation(runtime: CodexRuntime) -> CapabilityReport`.

- [ ] Add failing adapter tests for unsupported flags, missing auth, managed-policy refusal, inherited AGENTS/hooks/skills/MCP, malformed JSONL, nonzero exits, exit-zero missing output, timeouts, cancellation, and unexpected write/network attempts.
- [ ] Implement explicit setup, stable authentication-backend selection, clean subprocess environments, neutral working directories, documented capability disabling, permission-profile selection, JSONL parsing, strict structured outputs, and owned-child cleanup.
- [ ] Prove allowed evidence reads and denied out-of-scope reads/writes/network access with canaries before using private payloads. Verify hooks/helpers were not executed and no real configuration was changed.
- [ ] Run real authenticated smoke checks in a throwaway audit home. A native login in that isolated home may require the owner's browser/device action; do not obtain a token by reading existing secret stores. Until this passes, runtime isolation is pending, not complete.

### Task 4: Parallel domain review and transversal reconciliation

**Interfaces:** `review_domains(snapshot: AuditSnapshot, runtime: CodexRuntime, options: RunOptions) -> DomainResults`; `reconcile(results: DomainResults, snapshot: AuditSnapshot, baseline: Baseline | None) -> ReconciledAudit`.

- [ ] Add known-answer fixtures across all eleven categories, including the four specifically required cases: cross-host semantic duplication, dead import, globally misplaced path rule, and duplication of a repository script. Include legitimate policy/default-looking constraints as negative cases.
- [ ] Test actual concurrent job overlap, deterministic assignment, every expected contribution, evidence-request bounds, malformed/missing shards, and a conflict only detectable after combining domains. Assert that a lost contribution cannot return exit 0 or 1.
- [ ] Implement specialist prompts, parallel process control, topic candidate indexing, structured dispositions/findings, complete reconciliation, bounded challenge rounds, and preserved dissent. Do not manufacture agent debate or a fixed number of agents where a domain is absent.
- [ ] Execute the real fixture pipeline and inspect cited excerpts and underlying evidence. Repeat unchanged inputs to verify stable IDs and materially equivalent detection; record variable prose or unresolved semantic uncertainty honestly.

### Task 5: Report, baseline, privacy, and failure semantics

**Interfaces:** `compare_baseline(current: ReconciledAudit, baseline: Baseline | None) -> BaselineChanges`; `write_run(audit: ReconciledAudit, run: RunState) -> RunOutcome`.

- [ ] Add failing cases for invalid ranges/excerpts, missing evidence/conflict fields, low-confidence removal recommendations, output escape/symlinks, duplicate run names, concurrent edits, missing report, stale knowledge, unsafe report markup, and all four exit statuses.
- [ ] Implement one canonical result, deterministic Markdown rendering, atomic output, baseline matching, complete validator summaries, and honest per-role timing/usage.
- [ ] Confirm two simultaneous audits preserve separate artifacts and `latest` selects a completed status explicitly. Preserve previous reports and do not silently discard failed runs.
- [ ] Compare all in-scope before/after hashes and Git state in normal and injected-write tests. Inspect the actual final report, not just schema success.

### Task 6: Skill and scheduled invocation

**Interfaces:** `main(argv: Sequence[str] | None = None) -> int`; `render_schedule_example(kind: str, target: Target, runtime: RuntimePaths, calendar: CalendarSpec) -> str`.

- [ ] Author the skill with the current skill-creator guidance and validate activation, explicit invocation, negative triggers, setup/latest guidance, and absolute launcher resolution after installation. Keep development fixtures/runners outside the package.
- [ ] Test interactive, headless, and scheduled entry points against the same fixture state and compare inventory, stable IDs, dispositions, and status. A report path or a green CLI exit alone is insufficient.
- [ ] Generate app, launchd, and systemd user recipes with no installation side effects. Verify syntax with native facilities where available and execute one-shot schedules only in the isolated test environment. Do not change the owner's actual scheduled tasks or OS scheduler.
- [ ] Test an untrusted workspace, a local worktree with missing local-only files, an unavailable CLI, a closed/unavailable local host, and a restricted CI checkout. Surface reduced coverage and parent exposure explicitly.

### Task 7: Quality gates and clean distribution test

- [ ] Lock verified compatible tool/dependency versions; run `uv run --locked ruff check .`, `uv run --locked ruff format --check` on formatter-owned Python files, `uv run --locked basedpyright`, and `uv run --locked pytest`. Do not format instruction/configuration/memory files or suppress a failing check.
- [ ] Use available LSP diagnostics for supported Python files with this repository's explicit absolute root and paths; verify readiness/change observation. If unavailable, record the exact limitation and use native project gates without installing/updating LSP merely for a query.
- [ ] Run manifest/catalog/schema and installable-file validation, dependency/security checks appropriate to the actual files, and GitHub workflow validation. Pin external actions to verified full commit SHAs and keep validation tokens read-only.
- [ ] Test the runtime and installation on macOS arm64 and Linux x86_64. Use at least two independent synthetic repositories/homes, with and without Claude, including Claude files without a CLI.
- [ ] Test both local and Git-backed marketplace sources in clean throwaway configuration. Verify plugin identity, enabled state, skill discovery, explicit invocation, and a real completed audit. Include disabled-plugin visibility as a negative case.
- [ ] Run applicable plugin/skill evaluation as supplemental evidence; retain raw fixture results. Formal scores do not replace factual/evidence/runtime validation.
- [ ] Build the distributable twice, compare deterministic package content/checksums, inspect the archive manually, and confirm no private reports, fixtures, credentials, absolute personal paths, or unrelated tools entered it.

### Task 8: Owner review, public repository, release, and end-user verification

- [ ] Present the concrete diff, package inventory/checksum, quality-gate results, known-answer reports, capability matrix, and unresolved limitations for the owner's publication approval. Do not commit/push before that approval; this overrides the planning skill's generic frequent-commit advice.
- [ ] After approval, create the public GitHub repository without a generated unsigned initial commit. Make explicitly scoped signed commits, verify their signatures, push, and inspect GitHub validation results. Label every PR if a PR is created and attach it to the chat.
- [ ] Configure repository labels/templates and the documented maintenance/release workflow. Issue triage may classify issues and prepare drafts; posting replies requires an explicit instruction to send.
- [ ] Once remote gates pass, create and verify the signed release tag and publish **Agent Context Audit v0.1.0** with the installable plugin archive, SHA-256 checksums, tested capability matrix, install/update instructions, changelog, and privacy/runtime requirements.
- [ ] Fresh-install from the actual public tagged source into a new throwaway configuration; execute the fixture audit and inspect the report/status. Do not substitute the local source or a hand-built archive for this public-source test.
- [ ] Close out with exact repository/tag/release links, commits, package hash, local/CI/runtime evidence, tested and untested behavior, deviations, and remaining limitations. Mark the overall goal complete only after every acceptance item below has authoritative proof.

## 6. Release acceptance and approval

| Requirement | Required evidence |
| --- | --- |
| Full eligible scope, independent of installation scope | Inspected manifests from both fixture repositories, user/project installations, known roots/exclusions, and added/deleted-source tests |
| Complete reads | Mechanically checked source/fragment/chunk digests and gap-free ledgers for every analyzed context |
| All eleven defect categories and meaningful negatives | Known-answer expected findings matched to actual excerpts/evidence; legitimate policy preserved |
| Parallel and transversal audit | Observed overlapping domain jobs plus a cross-domain-only defect and full reconciliation input accounting |
| Every instruction has a disposition | Validated instruction coverage/disposition records, including kept instructions |
| Read-only behavior and Git preservation | Enforced denial canaries, no hook/helper execution, complete start/end hashes and Git observations, concurrent-edit attribution |
| Prompt-injection and data boundaries | Adversarial source fixtures cannot cause writes, unapproved network calls, scope changes, credential access, or active report content |
| No silent partial result | Missing jobs, missing report, bad citations, unavailable references, unsupported isolation, and restricted roots produce appropriate non-success status |
| Repeatability and change tracking | Unchanged-input stable IDs; new/resolved/persisting/regressed baseline tests; uncertainty for ambiguous identity matches |
| Interactive, headless, scheduled modes | Actual per-mode execution against the same inputs and reviewed equivalent results; explicit surface/coverage limits |
| Claude optional | Passing no-Claude run and labeled file-only case without executing Claude customizations |
| Portable product and clean install | Validated manifests/overlay/catalog, clean package inspection, macOS/Linux gates, local/Git source tests |
| Public release usable by third parties | Public repository, signed verified commits/tag, remote gates, release assets/checksums, and fresh tagged-source installation plus completed fixture audit |
| Maintenance workflow | Owner/co-maintainer policy, labeled PR process, issue templates/triage and draft-reply boundaries, documented release controls |

### Known limits and stop conditions

- This plan approves no existing implementation by implication. Permission-profile write/network behavior, authenticated workers, clean installs, Linux execution, and scheduler/UI behavior remain acceptance work.
- Model reasoning cannot be mechanically proven attentive or perfectly deterministic. The product must prove reads, delivery, evidence validity, output completeness, and controlled effects while preserving semantic uncertainty.
- If the supported runtime cannot isolate required context, policy requires incompatible hooks/telemetry, or a promised mode cannot see required sources, report the verified blocker. Do not replace the objective with a static linter, silently drop a domain, or call partial coverage complete.
- The external-domain default is an explicit assumption because the last preference question was unanswered. The owner can change it during plan review without reopening settled naming, licensing, or distribution decisions.
- The first distribution channel is the public GitHub marketplace and release. Universal plugin-directory submission is a separate publication route and is not part of this release approval.

**Approval requested:** Approve this written design/implementation plan so Tasks 1–7 may begin. Task 8 retains its separate approval of the concrete diff and publication artifacts, as required by the owner's brief.
