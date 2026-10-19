# Session Handoff

Carry a project's working state between Codex sessions. Write a reviewed handoff
when stopping; a trusted startup hook asks the next session to read it completely,
report pending work and let you choose what to do next.

**Status:** 0.1.0 local release candidate, not published. See the marketplace's
verification report for actual checks and gaps.

## Requirements and compatibility

- A Codex session with access to the project's directory and native file/shell tools.
- Bash for the hook and exclusive file creation; Git for repository inspection.
  GitHub CLI is optional. No Python, Node, uv, MCP server or API key is required by
  the installed plugin.
- Codex CLI 0.162.1 is the local test target, not a verified minimum version.
- The active native manifest is `.codex-plugin/plugin.json`. Synchronized portable
  metadata is kept inactive at `metadata/plugin.json`. Do not move it to the root:
  native probes on Codex 0.162.1/0.163.0 show root portable manifests suppress
  plugin hooks. See [Codex issue 47925](https://github.com/openai/codex/issues/47925).
- Hooks require explicit native trust review. Installation does not grant trust.
  Use Codex's `/hooks` controls; do not bypass them.
- Hook-bearing plugins currently require manual Codex installation and are excluded
  from the public plugin directory. Web installation does not deploy local scripts.
  See [OpenAI packaging guidance](https://developers.openai.com/plugins/build/plugins)
  and [hooks](https://learn.chatgpt.com/docs/hooks).
- macOS, Linux, Windows, CLI and desktop results are separate evidence layers.
  Do not infer platform coverage from this source layout or the CI matrix.

## Local installation

Replace /absolute/marketplace with this checkout's absolute path. For archive
verification, extract outside the source tree and point a local test marketplace
entry at the extracted session-handoff directory.

```sh
codex plugin marketplace add /absolute/marketplace
codex plugin add session-handoff@the-codex-factory
```

Use a disposable Codex home when testing. These commands register/install the
plugin; they do not establish hook trust or behavioral correctness.
Start a new session, inspect the skill in `/skills` and hooks in `/hooks`, and review
the hook before trusting it. Exact desktop availability remains separately verified.

## Use

Ask: **Write a handoff for this project before I stop.** You can also select
`write-handoff` through the native skills picker.

The skill inspects repository state, offers separately authorized Git actions,
reconciles every inherited open item and presents a complete draft for approval.
It creates one new UTC record in
`.codex/session-handoff/YYYY-MM-DD-HHMM.md`, using exclusive creation to protect
earlier records. It reads the saved result back before reporting success.

Open the next session in the **same directory**. On startup or clear, the trusted
hook asks Codex to read the newest matching record in full, summarize it, retain
your current request and ask which work to prioritize. The hook emits fixed
instructions, never the handoff's contents. Model compliance is checked separately.

Without handoffs the hook is silent. It does not run on resume or compaction.
To recover manually, ask Codex to read the latest handoff completely. If the session
directory changes, that directory has its own handoff scope, even inside one Git repo.
Existing Claude handoffs are not imported or modified automatically.

## Boundaries and failure recovery

- Only you may drop inherited work. Partial/open items keep their original dates.
  Items older than 30 days are marked for confirmation.
- Git fetch updates remote-tracking refs. Commit, push and PR creation need scoped
  authorization. Failed remote checks are labeled unverified.
- A noninteractive invocation returns a draft; it cannot treat silence as approval
  to save that draft. The startup protocol proceeds with the initial request.
- Unreadable, malformed or symlinked storage is an explicit failure, not absence.
  Native sandbox/permission restrictions still apply.
- A failed save can leave a partial new record. The skill reports it and stops;
  review that file before authorizing any repair or removal.
- Handoffs can contain private project details. Review them before sharing.
  The plugin does not modify .gitignore, instructions, memory or prior records.

## Updating and removing

Use the native plugin management controls to update from the reviewed source.
To remove the local installation:

```sh
codex plugin remove session-handoff@the-codex-factory
```

Uninstalling leaves project handoffs intact. No remote release/update URL is
claimed until publication is approved.

## Provenance and license

Adapted from Session Handoff 0.1.0 in The Claude Factory, source revision
`96008f1e18eefbaad6d0361d6cb07404c42ded37`. This is an independently versioned Codex
adaptation: Codex lifecycle variables, native tools and installation replace Claude
integration points. The template and MIT attribution are retained.

[Changelog](CHANGELOG.md) · [MIT license](LICENSE)
