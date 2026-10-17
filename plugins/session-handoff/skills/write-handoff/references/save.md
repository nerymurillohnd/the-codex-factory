# Save an approved handoff

Use only the explicit PROJECT from the skill and the exact user-approved draft.
Saving does not authorize any other workspace edits.

1. Reject symlinked .codex, STORE or selected record paths. If storage cannot be
   listed, stop. Create STORE with `mkdir -p "$PROJECT/.codex/session-handoff"`
   only after approval. Do not change .gitignore or permissions.
2. Take `date -u +%Y-%m-%d-%H%M` once for the initial candidate filename.
   Its timestamp must also appear in `Written:` as YYYY-MM-DD HH:MM UTC.
3. If the candidate exists (including a symlink), advance by one calendar minute.
   On GNU date, `date -u -d '<YYYY-MM-DD HH:MM> UTC + 1 minute' +%Y-%m-%d-%H%M`;
   on BSD date, `date -u -j -v+1M -f '%Y-%m-%d-%H%M' '<candidate>' +%Y-%m-%d-%H%M`.
   Continue until unused, handling day/month/year rollover. Update Written to match.
4. Use the native shell tool's **exclusive creation**, not an editing tool that can
   overwrite an existing file. Set HANDOFF_FILE to that quoted absolute filename
   and pass the approved Markdown on stdin to this Bash command:

```bash
(set -o noclobber; cat > "$HANDOFF_FILE")
```

   Supply stdin with a single-quoted heredoc whose unique delimiter does not occur
   in the content. Never interpolate Markdown into executable shell text.
   A collision detected at creation requires a new candidate and matching Written;
   permission/disk failures require stopping. Never force an overwrite. A failed
   write may leave a partial new file: report its path, do not declare success, and
   do not overwrite/delete it automatically.
5. Read the saved file whole and compare every line with the approved draft. Report
   any mismatch as failure. Only then confirm the path and unresolved items.

Exclusive creation protects against ordinary competing writers. It does not make
an attacker-controlled directory safe; symlink checks are not a transactional
filesystem sandbox. Stop if the project directory is being modified unexpectedly.
