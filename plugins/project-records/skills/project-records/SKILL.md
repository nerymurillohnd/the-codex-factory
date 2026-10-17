---
name: project-records
description: Use when an important project decision is made, confirmed technical debt remains unfixed, or logged debt is resolved.
---

# Project records

Keep the maintainers' decisions and unfixed technical debt in files, so nobody has to rediscover why the project is the way it is. Each kind of record has a procedure in `references/` and a template in `assets/`.

## Where records live

- Decisions: `docs/maintainer/decisions/ADR_<YYYY-MM-DD>_<slug>.md`, one file per decision.
- Pending debt: `docs/maintainer/technical-debt/pending-debt.md`.
- Resolved debt: `docs/maintainer/technical-debt/resolved-debt.md`.
- Create a folder or ledger the first time it is needed. There is no setup step. Paths are relative to the explicitly selected user project, never the installed plugin. Explicit user/project path overrides prevail.

Create `docs/maintainer/decisions/` when writing the first ADR. Create `docs/maintainer/technical-debt/` and `pending-debt.md` when opening the first debt item; create `resolved-debt.md` when resolving the first item. Installation alone creates none of these project documents.

Check destinations stay within the authorized project, including symlinks. If a configured path is protected or unwritable, return the pending draft and exact blocker; do not relocate records or broaden permissions. The default uses `docs/` because Codex protects `.codex/` in workspace-write. Do not migrate existing Claude records or change global configuration automatically.

## When to act

Act before finishing the task, not after. Follow explicit user instructions and existing authorization. Do not ask again merely to record an authorized task. When there are several decisions to record, first ask the user how to register them: [choose how to register](references/decision-records.md#choose-how-to-register). Otherwise ask only for facts you are missing. Then tell the user in one line what you recorded and where.

1. An important decision is made: read [decision records](references/decision-records.md), then write the ADR.
2. A problem is found that cannot be fixed now: read [debt ledger: open and update](references/debt-ledger-open.md), then log it.
3. A logged problem is fixed: read [debt ledger: resolve](references/debt-ledger-resolve.md), verify the fix, then move the entry to resolved.

## What counts as an important decision

Record a decision that:

- chooses one approach over another, with consequences that last,
- changes the architecture, a process, a dependency, security, or how the project is built, released or distributed,
- sets the scope or shape of a plugin, such as integrating into an existing plugin or creating an independent one,
- would be hard to undo, or that someone may later question with "why did we do it this way?".

Do not record renames, typos, formatting, comments, a small refactor that keeps behavior, or a choice an existing ADR already covers.

## Do

- Search the existing records before adding one. Update the match instead of duplicating it.
- Write only what is verified or what the user said. Mark the rest as an inference or as pending, because a record that guesses misleads the next reader.
- Mention a record elsewhere by its ID only: the ADR file name without `.md`, or `DEBT-<NNN>`.
- Keep each ledger index equal to its entries.
- Use today's local date, from `date +%F`.

## Do not

- Do not rewrite an accepted ADR or a resolved entry. Supersede it, so the history stays true.
- Do not log a problem that can be fixed now. Fix it.
- Do not write a decision or a debt item into a README, changelog, code comment, commit message, task list or memory.
- Do not leave unfilled placeholders or copied template instructions in a completed entry. Keep the reusable Entry format comment in each ledger as its template specifies.

When creating a ledger, copy the complete template body, preserving its sections, notices, status legend and reusable Entry format block. Then add the filled entry and index row. Remove only the initial template instruction comment and the applicable empty-state marker.

Use native filesystem tools and the available question tool, or plain chat. In a noninteractive session, return unanswered questions and leave dependent records pending. This workflow does not authorize unrelated repairs, commits or publication. Read only the applicable procedure and template.

## References

- [Decision records](references/decision-records.md): write, supersede and check an ADR. Template: [ADR template](assets/ADR_YYYY-MM-DD_decision-slug.md).
- [Debt ledger: open and update](references/debt-ledger-open.md): what belongs in the ledger, how to log and update an item. Template: [pending debt](assets/pending-debt.md).
- [Debt ledger: resolve](references/debt-ledger-resolve.md): verify a fix, move the item, keep history. Template: [resolved debt](assets/resolved-debt.md).
