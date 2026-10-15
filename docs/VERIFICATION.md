# Release-candidate verification

Status: **local candidate; publication gates remain open**. Evidence dates: 2026-10-14–15 UTC. No repository commit, push, public repository creation, release tag or release publication has been performed.

## Observed evidence

| Layer | Observed result | Scope and limits |
| --- | --- | --- |
| Python behavior | 115 local checks passed, including native Codex and optional native Claude version fixtures | Synthetic repositories and homes; includes negative paths, process cancellation, complete coverage, citation checks, privacy, baseline changes and output handling |
| Native runtime | Codex CLI 0.162.1 on macOS arm64 passed the read/write/network capability canaries | Allowed evidence read; external reads, writes and command networking denied |
| Native exec transport | Actual Codex binary completed requests against a synthetic local Responses server and authenticated model service | The synthetic test isolates transport assertions; authenticated fixture runs establish separate semantic evidence |
| Tool surface | Native transport exposes only request_user_input after the configured capability switches | Execution, browsing, MCP, plugin, goal and sleep tools were absent in the captured request; a question tool can still fail/stall, so timeout/completion gates remain necessary |
| Marketplace | Native local registration, installation, identity and enabled skill discovery passed in a clean test home | Discovered `agent-context-audit:audit-agent-context`; a persisted disabled-plugin setting produced zero enabled audit skills |
| Portable schema | plugin.json passed the primary Agent Plugins 1.0.0 JSON Schema | Native compatibility overlay also exercised by local installation |
| Runtime setup | Isolated uv setup and non-editable wheel installation succeeded | Source checkout and extracted ZIP both installed into external test runtimes; existing user environments/auth stores were not copied |
| Platform knowledge | All 11 official article hashes matched the freshly retrieved baseline | Freshness proof at this date; future changes/unavailable documents produce a limitation |
| Diagnostics | Ruff and native Basedpyright gates run locally | LSP MCP route returned `Missing executable: mcpls`; no runtime was installed to bypass that limitation. Basedpyright uses nvm Node |
| Workflow security | Zizmor 1.30.1 offline pedantic inspection passes without suppressions | CI was inspected locally, not executed on GitHub |
| Dependencies | 21 Python runtime/dev/build packages checked through OSV with no known advisories; npm CI lock resolution reported zero known vulnerabilities | Point-in-time advisory lookup, not proof that dependencies contain no defects |
| Distribution | ZIP generation is deterministic and rejects symlinks, unexpected files and secret stores | Generated Python bytecode and Finder metadata are not product inputs. Package inventory and checksum accompany the candidate |
| Mode contract | Real headless, scheduled-labelled and installed-skill entry runs completed with stable findings; all four entry labels also have controller tests | Native installed-skill entry returned the required interactive exposure limitation; actual timer/app triggering and desktop UI remain open |

## Independent review and corrections

A fresh read-only review found six material defects. Each received a concrete regression and correction:

1. Repository Git filters could run during status observation. Repositories declaring clean/process filters now receive an explicit unavailable passive-Git observation before status execution; no target filter is invoked in the regression.
2. Credentials in MCP arguments/commands could survive redaction. Separate and equals-form sensitive arguments are now masked in JSON/TOML while retaining parseable configuration and source lines.
3. Reconciliation could mark a finding kept while omitting it. Retained/merged decisions now require real destinations, citation relationships and stable finding IDs; final array positions are remapped after sorting/batching.
4. Configured Codex agent files could be omitted. config_file references are classified and included, with explicit limitations for unavailable or unauthorized destinations.
5. Failed challenge groups could leave sibling reviewers running. All sibling tasks are cancelled and awaited before reconciliation returns.
6. Repository mechanisms were wrongly rejected as evidence for redundant-with-defaults. Verified script/linter/CI facts are accepted alongside documented platform defaults; unsupported model-only deletion remains invalid.

The additional review observation about an unauthorized configured auto-memory directory was also corrected: the blocked source is now an explicit coverage gap. The review's initial verdict was not-ready; the author verified these corrections with regressions and the full suite. There has been no second independent review claiming release readiness.

## Open acceptance gates

- **Semantic scope limit:** authentication and real-model fixture runs now pass. The combined fixture produces findings across all eleven categories, but its external deployment-script rule remains provisional because its existence and intended scope are outside the supplied evidence. This partial result is retained; no blanket 11/11 factual-accuracy claim is made.
- **Linux x86_64:** the CI matrix is prepared. No local Linux runtime/container was available, and remote CI cannot run before the separately authorized push.
- **Public/Git-backed installation:** a local marketplace installation passed. Git-backed/tagged-source installation remains pending the owner's commit/push/publication approval and actual remote availability.
- **Interactive execution and schedulers:** a real model invoked the installed skill in an isolated entry project and returned the real child report/status. The parent used the same full-access permission context as this desktop task; audit children retained their independent read-only profiles. Restricted parent sandboxes and desktop UI interaction remain untested. The packaged launcher generated a launchd plist that passed native plutil validation. Generated launchd ProgramArguments were executed once with a reduced environment and produced a complete-with-findings report. A second run verified the explicit in-target report override while review evidence stayed outside the target and all original files remained unchanged. Actual OS timer firing, systemd execution and app-scheduler triggering remain pending. Recipe generation does not install a schedule.
- **Higher-order semantic interactions:** bounded reconciliation compares every shard pair and preserves disagreement. Pairwise coverage cannot prove the absence of every interaction involving three or more sources.
- **Privacy/integrity limits:** mechanical redaction and boundary tests do not establish perfect semantic understanding or provider retention guarantees. Concurrent user/source changes are reported without assigning causation.

These limits must remain visible in any candidate review. Publication approval should follow completion of the applicable gates, not replace their evidence.

## Authenticated semantic results

- Codex-only negative control: headless and scheduled-labelled runs both returned complete-clean with full coverage. Signed-commit, customer-privacy and honest-uncertainty policies were retained.
- Confirmed command defect: two final runs returned complete-with-findings. Both produced finding ACA-49297959262167ed18f6 with the same proposed correction, `Run npm test before delivering changes.` The scheduled-labelled repeat classified it as persisting, with no new/resolved/regressed findings. Both preserved Git state and all valid policy obligations.
- Combined Codex/Claude fixture: twelve findings represented all eleven primary categories. Ten categories had high-confidence findings; the misplaced external deployment rule remained low-confidence and provisional. All other specialist contributions completed after source-ID/citation repair. Native Claude 2.1.300 was verified in a read-only sandbox. The source requiring external evidence kept the overall audit partial.
- Installed-skill entry: the model loaded the packaged skill, ran its launcher, preserved the supplied source roots and interactive entry label, and returned the real report/status paths. The child completed coverage and produced the same finding ID and replacement as the direct runs. Source hashes remained unchanged after the parent finished. The expected parent-exposure limitation kept the status partial.
- Adversarial fixture: all assigned sources were reviewed and coverage validated. The requested exfiltration file and hook marker were absent; the synthetic private canary was absent from every captured request/response/report artifact; secret-file metadata and Git state were unchanged. The run remained partial because an unrelated temporary hook's intended scope was unresolved.

Real-model QA also exposed and corrected a strict-provider schema incompatibility, premature validation of evidence-pending findings, missing repository path discovery, ambiguous citation identifiers, a stale local-wheel cache, and loss of valid timing constraints in a proposed removal. The controller keeps full local validation, supplies scoped source metadata, preserves prior assessments across evidence rounds and requires semantic repairs to remain within the original assignment.

Raw native runs and their reports are retained privately in the task's ignored evidence workspace. These results establish specific fixture behavior; they do not prove perfect semantic completeness, arbitrary-policy correctness or cross-platform readiness.

## Final launcher and storage checks

- Scheduled recipes retain the selected source/auth/output roots and the non-secret runtime environment needed without an interactive shell.
- Bootstrap uses a trusted absolute Python interpreter with isolated/no-site startup. Regression fixtures verified that PYTHONPATH customization and a target virtualenv wrapper are not executed.
- A missing runtime or backend exit without valid report/status artifacts is a failure (exit 3), never completed findings (exit 1).
- Explicit in-target output requires --allow-output-in-target; model work/raw evidence remain external and the report labels the intentional publication writes.
- Reference URLs are sanitized in metadata as well as source text, including recognized encoded credential-bearing paths. Config-reference expansion terminates cycles and preserves symlink/parent traversal semantics. Malformed fallback metadata is recorded without a controller crash.
