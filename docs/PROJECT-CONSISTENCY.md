# Project consistency audit

The Codex Factory has a project skill, a native audit role and a repository-local
Git pre-push guard. This is maintainer infrastructure, never plugin runtime content.
It supplements the existing lint/type/test gates and release acceptance.

## Manual checks

From the explicit project directory, with nvm Node and the pinned uv environment:

```sh
uv run --locked --no-env-file python -m tools.push_audit check --root "$PWD" --deterministic
uv run --locked --no-env-file python -m tools.push_audit check --root "$PWD"
```

The first command performs deterministic validation and reproducible packaging.
The second also invokes native Codex for contextual review. A working-copy report
does not certify a future commit or authorize a push.

The project skill is audit-project-consistency; its native agent definition is
project-consistency-auditor. The automatic controller applies the same reviewed
instructions through a dedicated codex exec invocation. It does not rely on
unsupported agent-type lifecycle hook handlers.

## Local installation

```sh
uv run --locked --no-env-file python -m tools.push_audit install --root "$PWD" --codex-bin /absolute/native-codex
```

The installer copies the reviewed auditor, role, skill, schema, pinned environment
and existing privacy helper into the repository's Git common directory. It prepares
that environment through uv and activates hooks/pre-push only after setup succeeds.
The launcher is independent of disposable worktrees and is shared by this
repository's worktrees. No global Git/Codex configuration is changed.

An existing executable pre-push hook is preserved and run with the original
arguments and identical stdin. Both hooks must pass. Existing core.hooksPath
configuration, symlinked hooks or an existing guard installation require explicit
reviewed integration/update; the installer does not overwrite them silently.

## What happens on push

Git supplies the real outgoing refs and object IDs. The controller verifies commit
signatures, checks signed release tags against plugin versions, and materializes
protected temporary snapshots directly from Git objects. It does not use checkout
filters, dirty working-copy files, source hooks or target commands.

Each outgoing tip is audited for catalog/inventory, manifest identity/version/type
alignment, skill frontmatter, agent definitions, required documents, license text,
root README entries and actual package source/inventory/checksum reproducibility.
Deletion-only updates receive a contextual ref review without pretending a new
content tree exists. Publication/deletion authorization remains separate.

Large scopes are reviewed in bounded whole-file batches. Each batch stays below
512 KiB and repeats shared identity, README, license, changelog, skill and schema
anchors. A current source and its previous version remain together. Every packet
is bound to the full redacted scope digest and its own exact content digest; the
controller verifies complete current/previous source coverage before invoking any
reviewer. Every batch must pass. Missing cross-file evidence must be reported as
incomplete rather than inferred; a source that cannot fit with the shared anchors
blocks review. Evidence is never truncated to obtain a pass.

The contextual reviewer receives redacted evidence, exact scope hashes and changed
paths. It runs with native read-only sandbox, ignored user config, and shell, apps,
plugins, memories, multi-agent and lifecycle hooks disabled for that reviewer
subprocess. The outer Git guard remains active. Authentication uses the normal
native credential store; credentials are never copied into snapshots or reports.

PASS requires complete coverage, a matching scope digest and no blocking findings.
BLOCKED is a discrepancy; ERROR is missing/unreliable execution or review. Either
rejects the push. Unsupported runtime/authentication, limits, timeouts, malformed
results and changed refs never become success. Approvals are not cached.

Reports are stored below factory-push-audit/runs in the Git common directory and
identify refs, trees, source hashes, reviewer coverage, findings and package hashes.
Remote locations are not included; their identity is represented by a digest.

## Verification and recovery

Confirm the local pre-push launcher contains its factory-push-audit managed marker.
Use the behavioral fixtures to prove allow/reject behavior; file existence alone
does not establish activation.

If a push is blocked, inspect its report and resolve the reported discrepancy using
the normal authorized workflow. Then rerun on the new commit. For an execution
error, restore the required native runtime/login or review the installed auditor
before updating it. Do not weaken the validator or use --no-verify to obtain a pass.

For a reviewed removal/update, first preserve the existing installation as evidence.
Restore previous-pre-push from the guard state if there was a previous hook;
otherwise remove only the managed pre-push launcher after checking its marker.
Then install the newly reviewed source. Do not delete unrelated Git hooks.

Local Git hooks can be deliberately bypassed with --no-verify or changed by an
equally privileged local user. This control prevents ordinary mistakes; it is not
a server-enforced security boundary. Remote CI and publication policies remain
separate controls.
