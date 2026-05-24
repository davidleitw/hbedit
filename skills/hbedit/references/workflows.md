# hbedit Workflow SOPs

Step-by-step recipes for hbedit operations. Each SOP covers a complete
end-to-end scenario including preflight, user confirmation, and commit.

## Contents

- SOP A — Edit an existing card
- SOP B — Push a local doc as a new tracked card
- SOP C — Continue editing on another machine after git clone
- SOP D — Read-only access to a card
- SOP E — Edit tags on an existing card
- SOP F — Multi-step composites (split / merge / batch push)
- Conflict resolution (referenced by SOPs A and C)

---

## SOP A — Edit an existing card

1. `hb doctor` — on error, follow the matching code in `errors.md`.
2. Check `state.json` for the card's path. If not tracked, run
   `hb pull <cardId> <path>` (find cardId via
   `heptabase card list -q "<title>"`).
3. Read the `.md` file. Plan the change — identify what is preserved vs.
   inserted/edited/deleted. Show the plan to the user and confirm before
   writing, especially for destructive edits.
4. Edit the `.md` file.
5. `hb push <path>`:
   - `action: "updated"` → success; report block counters.
   - `code: "content-conflict"` → follow Conflict resolution below.
   - `code: "no-baseline"` → follow `no-baseline` in `errors.md`, retry.
6. Commit `state.json` + the `.md`.

---

## SOP B — Push a local doc as a new tracked card

1. `hb doctor`.
2. Confirm a vault exists (`.hbedit/state.json` in the tree). If absent,
   run `hb init` in the project root.
3. Read the `.md` and confirm intent with the user if there is any ambiguity.
4. `hb push <path>` — on `action: "created"`, report the new `cardId`.
5. Commit the `.md` and `state.json` together so other machines inherit
   the binding.

If the user later realizes they wanted a fire-and-forget card (no
tracking), `hb unlink <path>` removes the binding cleanly (local md and
remote card untouched).

---

## SOP C — Continue editing on a second machine after git clone

After `git clone`, the per-machine cache (`~/.hbedit/cache/<vault-id>/`)
is absent on the new machine — only `.hbedit/state.json` is committed.
The first operation on each tracked file must be `hb pull <path>`.

1. `hb doctor`.
2. `hb pull <path>` (one-argument form). Inspect the outcome:
   - `action: "baseline-established"` — file matches remote; continue to step 3.
   - `action: "conflict"` — local file diverged from remote; a `.conflict.md`
     backup was created, working file now holds remote. Reconcile via the
     Conflict resolution SOP before continuing.
   - `code: "local-has-changes"` — file was edited before pull; run
     `hb push <path>` first, then retry the pull.
3. Plan changes, confirm destructive edits with the user.
4. Edit `.md` and `hb push <path>`.
5. Commit `state.json` + `.md`.

---

## SOP D — Read-only access to a card

1. `hb doctor`.
2. If already tracked, read the `.md` directly.
3. If not tracked, `hb pull <cardId> <path>`, then read the resulting `.md`.

For pure reads with no intent to maintain, prefer `heptabase note read
<cardId>` (base CLI) instead of hbedit — no state.json binding gets
created.

---

## SOP E — Edit tags on an existing card

1. `hb doctor`.
2. Verify path is in `state.json`. If not, pull first (SOP A steps 1–2).
3. To add: `hb tag add <path> <name>`. On `tag-ambiguity`, show the warning
   and ask the user to confirm before retrying.
4. To remove: `hb tag remove <path> <name>`. On `tag-not-on-card`, no action
   needed.
5. Commit `state.json`.

---

## SOP F — Multi-step composites (split / merge / batch)

These operations are built from primitives, not single commands.

**Split one card into two:**

1. Pull the source card (SOP A steps 1–3).
2. Plan the split — show the user which content goes where and confirm.
3. Edit source `.md` to its portion; write a new `.md` for the second part.
4. `hb push <source-path>` (updated) then `hb push <new-path>` (created).
5. Commit both `.md` files and `state.json`.

**Merge two cards into one:**

1. Pull both cards. Plan + confirm the merge layout with the user.
2. Append second card's content into the first `.md`.
3. `hb push <primary-path>`.
4. Inform the user the second card still exists in Heptabase; ask if they
   want to trash it manually and `hb unlink <second-path>` to drop its
   binding.
5. Commit.

**Batch push (multiple files):**

1. List all candidate files; show the user the batch and confirm before
   starting.
2. Push files one at a time, collecting results. On any error, stop and
   report — do not continue past a `state-corrupt` error.

---

## Conflict resolution (referenced by SOPs A and C)

When `hb push` returns `code: "content-conflict"` or `hb pull` returns
`action: "conflict"`, a `.conflict.md` backup of local edits has been
created and the working `.md` now holds the remote version.

1. Present both files to the user.
2. Produce a merged version (semantic merge) and confirm with the user.
3. Write the merged content to the working `.md`.
4. `hb push <path>`.
