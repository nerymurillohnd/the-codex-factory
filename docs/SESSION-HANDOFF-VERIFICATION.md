# Session Handoff verification

Date: 2026-10-16. Status: **implemented local candidate; release acceptance incomplete**.
No commit, push, release tag, account upload or publication was performed.

## Result and boundaries

Session Handoff 0.1.0 is implemented as a native Codex plugin with the original
reviewed-draft workflow, complete prior-record reading, explicit reconciliation,
exclusive append-only saving, read-back checks and a Bash startup/clear hook.
It has no Python/Node/uv runtime dependency or MCP server. Maintainer validation
continues to use the repository's pinned uv environment and nvm Node.

The Claude source revision is 96008f1e18eefbaad6d0361d6cb07404c42ded37. SHA-256
inventory comparisons confirmed the referenced source files were unchanged.
The MIT attribution and handoff template are retained, with an added explicit
nonrepository conditional to prevent contradictory Git fields.

## Native manifest decision

The planned root portable manifest conflicted with observed native behavior:
Codex 0.162.1 and the already-installed 0.163.0 app-server binary returned empty
plugin hooks with a root plugin.json. Path, array, inline and default declarations
did not change that result. In a controlled extracted-package probe, removing only
the root manifest made SessionStart discoverable.

This independently reproduces the behavior reported in
[Codex issue 47925](https://github.com/openai/codex/issues/47925). It conflicts with
the hook declaration support described in
[OpenAI packaging guidance](https://developers.openai.com/plugins/build/plugins).
The issue report alone is not the proof; native before/after probes are retained.

The active manifest is therefore .codex-plugin/plugin.json. Canonical portable
metadata remains synchronized at metadata/plugin.json, where it does not shadow
native hook loading. Do not place a portable plugin.json at this plugin's root
until that behavior is reverified. Agent Context Audit retains its existing layout.

## Verification matrix

| Layer | Observed result | Limit |
| --- | --- | --- |
| Baseline pytest with native Codex 0.162.1 | 156 passed | Before implementation |
| Final full pytest with explicit native Codex 0.162.1 | 177 passed | Local macOS arm64 |
| Ruff check | Passed | Repository scope |
| Ruff format check | Passed, 69 files | Existing formatter-owned Python paths only |
| Basedpyright through nvm Node | 0 errors, 0 warnings, 0 notes | Project type gate |
| Marketplace validation | Passed | Metadata, declared skills, contained hook resources |
| Shell hook fixtures | Passed | Direct script execution; no model compliance claim |
| Exclusive save fixture | Passed | Two competing writers: exactly one succeeds; later overwrite refused |
| Clean native archive installation | Passed | Disposable home; no copied credentials |
| Native skill and hook discovery | Passed on 0.162.1 and 0.163.0 | Hook remains untrusted; trust was not bypassed |
| LSP Intelligence | Unavailable: Missing executable: mcpls | No LSP runtime installed; native project gates used |
| Plugin Eval static plugin report | 58/100 | Missing public listing URLs; not runtime acceptance |
| Plugin Eval static skill report | 86/100 | Deferred-reference budget heuristic; no measured usage |
| Plugin Eval dry-run | Unsupported by installed implementation | Its skill documentation advertises a rejected option |
| Plugin Eval real benchmark attempt | Failed before model execution: HTTP 401 | Isolated generated home is unauthenticated |
| Native-model instruction scenarios | Six cases exercised; three draft cases repeated after correction | Explicit installed-file loading by native subagents; not codex exec or actual hook delivery |
| Actual interactive startup/clear delivery | Not verified | Requires native trust review and a real interactive session |
| Remote CI, public tagged installation, Linux/Windows | Not run | CI definitions were updated; no remote operation performed |

The benchmark reports zero token counters as usage present even though the turn
failed with no model response. Those counters are **not** measured successful
usage or semantic evidence. The owner's normal native login reports ChatGPT
authentication; this failure applies to the isolated benchmark home.

## Evaluation and review

Plugin Eval was run through its installed CLI with JSON retained as primary
evidence. Its trigger-description warning was corrected. Its remaining plugin
deductions concern website/privacy/terms URLs. No unpublished URLs or policy
declarations were invented to improve the score. The skill retains required
inspection/save details despite the static deferred-budget alert; no thresholds,
assertions or gates were weakened.

A fresh reviewer reproduced two defects: validating skills in the default rather
than declared directory, and startup recovery omitting metadata/calendar/scope
validation. Both were independently reproduced by failing tests, corrected and
followed by passing targeted and full-suite runs.

Native subagents explicitly loaded the installed skill for first-draft creation,
reconciliation, unauthorized-drop prevention, unreadable-record handling,
noninteractive request preservation and an approved save. Principal review caught
that all three initial drafts included Git fields despite the nonrepository
contract. The template and entrypoint were clarified, reinstalled in a fresh home,
and the three scenarios repeated with a fresh model context. Principal inspection
confirmed the corrected section shape, item/date/stale-marker preservation and
unchanged fixture hashes. The approved save was compared byte-for-byte, allowing
only its authorized Written update, and its filename timestamp was checked.

Every attempt is retained. These are bounded model samples, not guarantees of
universal behavior. The draft scenarios isolate nonrepositories with
GIT_CEILING_DIRECTORIES; real-repository Git/remote/PR semantic behavior remains
untested by these model samples. They do not replace an actual codex exec benchmark
or interactive hook-delivery test.

## Package

Both plugins were built twice and their archive bytes compared. The Session Handoff
package contains 11 allowlisted files: native and inactive portable manifests,
README, CHANGELOG, LICENSE, hook declaration/script, skill and three references.
The ZIP contains no tests, benchmark configurations, model reports, credentials,
caches, development environment or maintainer tools.

Session Handoff archive: session-handoff-0.1.0.zip

SHA-256:

```text
6a558128ba1234890263d0194ae6261deeb349df7833288a48e56925f82a122a
```

## Retained evidence and remaining work

Evidence is under .superpowers/session-handoff/ in the implementation worktree:

- source-provenance.json; red/green test logs and full final-tests.txt.
- ruff.txt, format.txt, types.txt, marketplace.txt.
- plugin-eval-final.json and skill-eval-final.json.
- native-compatibility-only-probe.json and native-0.163.0.txt.
- Six synthetic benchmark configurations, the retained failed attempt and raw logs.
- acceptance/ for separate native-agent scenarios, retained first/repeated attempts
  and principal-review-attempt-1.json/principal-review-attempt-2.json.
- review artifacts, progress.md and the complete public diff.

Build outputs are in dist/first and dist/second with package inventories and SHA-256.
Before calling this locally release-ready, complete authenticated behavioral
acceptance and interactive trusted-hook delivery. Authenticate through the native
login flow in a disposable test profile; never copy real auth files. Plugin Eval's
default credential/config seeding must remain disabled. Its generated benchmark
home can be authenticated natively for a separately recorded direct Codex run;
rerunning the harness provisions a different home.

Publication, signed commit/tag creation and public-source installation remain
owner-controlled later actions. This report is evidence of the checks listed,
not approval or evidence for those actions.
