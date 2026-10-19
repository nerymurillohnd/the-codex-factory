# Project Records

Record architecture decisions and confirmed technical debt in your project. This Codex-native adaptation of the Project Records skill from The Claude Factory preserves accepted history, avoids duplicate records, and resolves debt only after verification.

**Version:** 0.1.0 candidate. Local verification is recorded in the repository's `docs/PROJECT-RECORDS-VERIFICATION.md`. This package has not been published.

## Use

Install from The Codex Factory's local marketplace using your Codex plugin controls. Select Project Records and invoke `$project-records:project-records`, or describe the decision or debt work in your request. Automatic skill selection depends on the host; it is not a guaranteed event trigger.

With the native CLI, point at the checkout containing this plugin:

```sh
codex plugin marketplace add /absolute/path/to/the-codex-factory
codex plugin add project-records@the-codex-factory
```

Installation copies the package into the host's plugin cache. Reload or reinstall through the host after changing source; do not edit the cached copy.

Examples:

- "Record Nery's decision to use SQLite for this local inventory app."
- "Log this confirmed compatibility problem: the vendor fix requires external access."
- "The logged retry failure is fixed; verify the original failure and resolve its debt entry."

The skill records important decisions and eligible deferred debt during authorized work. It asks for missing facts and, for multiple decisions, asks once whether to use individual, grouped or classified ADRs. It does not ask again merely to write an already authorized record. Explicit user instructions and project permissions always prevail.

## Project files

The three bundled templates retain the original Factory content and layout; only their documented output paths change. The procedures retain the original structure, with Codex tool equivalents and the accountable user in place of a fixed personal name.

Defaults, relative to the explicitly selected target project:

| Record | Location |
| --- | --- |
| Decisions | `docs/maintainer/decisions/ADR_<YYYY-MM-DD>_<slug>.md` |
| Pending debt | `docs/maintainer/technical-debt/pending-debt.md` |
| Resolved debt | `docs/maintainer/technical-debt/resolved-debt.md` |

Explicit user paths or project instructions override these defaults. Folders and ledgers are created only when needed. Existing Claude records are not automatically migrated. No global configuration is changed.

The first ADR creates `docs/maintainer/decisions/`. The first pending item creates `docs/maintainer/technical-debt/` and `pending-debt.md`; the first resolution creates `resolved-debt.md`. These are files in the user's target project, separate from the installed plugin's templates. Installation alone does not create project records.

The default uses `docs/maintainer/` because Codex protects `.codex/` in workspace-write mode. An unwritable configured path leaves the record pending; the skill does not silently move it or broaden permissions.

Accepted ADR reasoning and resolved entries remain historical evidence. Later changes create superseding records. Debt closure requires both evidence that the fix works and evidence that the original failure no longer reproduces. Unavailable checks leave the item open.

## Requirements and boundaries

A Codex host with local project read/write tools is required. There is no Python/Node runtime, MCP server, hook or mandatory subagent in the installable plugin. Native interaction uses the available question tool or plain chat if it is unavailable. Noninteractive sessions return pending questions without inventing answers.

Session handoffs belong to the separate Session Handoff plugin. This skill does not create handoffs, commit, push, publish, change permissions or repair unrelated code on its own. Record verification may require project-specific test tools.

## Source and license

Adapted from `the-claude-factory/.claude/skills/project-records` at revision `fb86ddb226c3543fce491a70f4575107e6479341`. The source remains unchanged. This is an independently versioned Codex Factory plugin, licensed under [MIT](LICENSE); it does not claim the version or release history of another package.
