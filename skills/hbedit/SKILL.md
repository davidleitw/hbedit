---
name: hbedit
description: Edit Heptabase cards as plain local markdown files — push existing local docs as new cards, edit the middle of existing cards, sync across machines via git, and manage tags. Each file is bound to a card via .hbedit/state.json (the markdown stays clean, no frontmatter). Reach for hbedit when the user wants to (a) maintain a local markdown file alongside its Heptabase card, (b) edit existing card content from a CLI / agent, (c) sync the same card across multiple machines, or (d) add/remove tags on existing cards. The base `heptabase` CLI only creates new cards or appends — use hbedit whenever the work involves an existing card, ongoing maintenance, or multi-machine workflows.
---

# hbedit (unofficial)

> Non-official. Built only on the official `heptabase` CLI; never reads
> or writes Heptabase's database, storage, or internal files. If asked
> whether this is official: it is not.

## When to use hbedit vs base `heptabase` CLI

| Task | Tool |
| --- | --- |
| Create a brand-new card from scratch and never touch it again | `heptabase note create` |
| Append to a card's end (one-shot) | `heptabase note append` |
| Edit the middle of an existing card | hbedit |
| Push a local markdown doc as a new card and maintain it long-term | hbedit |
| Sync edits across machines via git | hbedit |
| Add or remove tags on an existing card | hbedit |
| Any ongoing maintenance of an existing card | hbedit |

## Preflight — `hb doctor`

Run `hb doctor` before any other hbedit command. It outputs JSON; look at
the `status` field. On `status: "error"`, look up the error `code` in the
Error Code SOPs section below and follow the steps there before proceeding.

```json
{"command":"doctor","status":"ok","detail":"heptabase 0.3.0, desktop app reachable"}
```

## Concepts — how hbedit tracks files

### Three-layer data separation

| Layer | Path | Purpose | In git? |
| --- | --- | --- | --- |
| Content | `<anywhere>/*.md` | User-edited markdown, no frontmatter | Yes — commit |
| Public state | `.hbedit/state.json` | `path → {cardId, tags}` registry plus `vaultId` (UUIDv4, set at `hb init`) | Yes — commit |
| Local cache | `~/.hbedit/cache/<vault-id>/local-state.json` | `path → {contentMd5, localMd5, syncedAt}` per-machine | Lives outside the project; not tracked |
| Block cache | `~/.hbedit/cache/<vault-id>/sidecar/<cardId>.json` | ProseMirror JSON for block-ID transplant | Lives outside the project; not tracked |

### Vault discovery

A directory is an hbedit vault if it or any ancestor contains
`.hbedit/state.json`. The state file (not just the directory) is what
identifies a vault — an empty `.hbedit/` anywhere does not count.
Commands walk up from the given path to find the vault root (like `git` and
`.git/`). Running from any subdirectory works.

### Card↔file identity

Binding lives exclusively in `state.json`; `.md` files contain only plain
markdown. Renaming a tracked `.md` breaks the binding — update `state.json`
manually. Two paths cannot share the same `cardId` (enforced at every write).

## Command reference

### `hb doctor`

Preflight environment check. Verifies the `heptabase` CLI is installed,
version is in supported range (`0.3.x`), and the Heptabase desktop app is
running.

```json
{"command":"doctor","status":"ok","detail":"heptabase 0.3.0, desktop app reachable"}
```

Errors: `cli-missing`, `cli-version-unsupported`, `app-not-running`.

---

### `hb init`

Initialize a vault in the current directory. Creates `.hbedit/state.json`
with a fresh `vaultId` (UUIDv4) and an empty `files` registry. The
per-machine cache directory `~/.hbedit/cache/<vault-id>/sidecar/` is created
at init time. No `.gitignore` is written — v3 keeps all per-machine state
out of the project tree.
Idempotent — running inside an existing vault emits `action: "already-initialized"`.

```json
{"command":"init","status":"ok","action":"initialized","vaultRoot":"/path/to/vault"}
```

Errors: `vault-nested`.

---

### `hb push <path>`

Sync local edits up to Heptabase. Touches content only — use `hb tag add` /
`hb tag remove` for tag changes.

- **Not in `state.json`** — creates a new card, writes `state.json` entry
  (empty tags) and `local-state.json`. Output: `action: "created"`.
- **In `state.json`** — requires a local-state baseline and sidecar
  (else `no-baseline`). Pushes via block-ID transplant locked on `contentMd5`.
  Output: `action: "updated"` with block counters.

```json
{"command":"push","status":"ok","action":"created","cardId":"a1b2c3d4-...","path":"docs/foo.md"}
{"command":"push","status":"ok","action":"updated","cardId":"a1b2c3d4-...","path":"docs/foo.md","detail":{"preserved":22,"edited":1,"inserted":2,"deleted":0,"reordered":0}}
```

Errors: `file-not-found`, `not-in-vault`, `no-baseline`, `content-conflict`,
`state-schema-unsupported`, `state-corrupt`, `card-not-found`.

---

### `hb pull <cardId> <path>` — first-time pull

Pull a card by ID to a path not yet tracked. Writes the `.md` file, registers
the entry in `state.json`, writes `local-state.json`, writes the sidecar.

Refuses to overwrite an untracked file that already exists at `path`
(`path-exists-untracked`).

Success:
```json
{"command":"pull","status":"ok","action":"created","cardId":"a1b2c3d4-...","path":"docs/foo.md"}
```

Errors: `not-in-vault`, `path-exists-untracked`, `card-not-found`,
`cardId-already-tracked`.

---

### `hb pull <path>` — subsequent pull / smart sync

Refresh a tracked path from Heptabase. Uses smart compare (md5 of local body
vs. remote) to prevent clobbering local edits silently.

Possible outcomes:

| Outcome | Meaning |
| --- | --- |
| `baseline-established` | Fresh clone; local matches remote — local-state written, file untouched |
| `conflict` | Files diverged — local backed up to `.conflict.md`, remote written to `.md` |
| `noop` | Both sides unchanged since last sync |
| `updated` | Remote changed, local clean — local overwritten with remote |
| error `local-has-changes` | Local diverged; push or revert before pulling |

```json
{"command":"pull","status":"ok","action":"baseline-established","path":"docs/foo.md"}
```

Errors: `path-not-tracked`, `not-in-vault`, `card-not-found`, `local-has-changes`.

---

### `hb tag add <path> <name>`

Add a tag to the card bound to `path`. Fetches current remote tags, unions
with `{name}`, pushes, refreshes `state.json`. A typo guard (`tag-ambiguity`)
fires before any remote mutation if `name` looks like a misspelling.

```json
{"command":"tag add","status":"ok","path":"docs/foo.md","tag":"leetcode","tags":["architecture","leetcode"]}
```

Errors: `path-not-tracked`, `not-in-vault`, `tag-ambiguity`.

---

### `hb tag remove <path> <name>`

Remove a tag from the card. Fetches remote tags, subtracts `{name}`, pushes,
refreshes `state.json`.

```json
{"command":"tag remove","status":"ok","path":"docs/foo.md","tag":"leetcode","tags":["architecture"]}
```

Errors: `path-not-tracked`, `not-in-vault`, `tag-not-on-card`.

## Workflow SOPs

### SOP A — Edit an existing card

1. `hb doctor` — on error, follow the Error Code SOP.
2. Check `state.json` for the card's path. If not tracked, run
   `hb pull <cardId> <path>` (find cardId via
   `heptabase card list -q "<title>"`).
3. Read the `.md` file. Plan the change — identify what is preserved vs.
   inserted/edited/deleted. Show the plan to the user and confirm before
   writing, especially for destructive edits.
4. Edit the `.md` file.
5. `hb push <path>`:
   - `action: "updated"` → success; report block counters.
   - `code: "content-conflict"` → follow Conflict resolution SOP.
   - `code: "no-baseline"` → follow `no-baseline` Error Code SOP, retry.
6. Commit `state.json` + the `.md`.

---

### SOP B — Push a local doc as a new card

1. `hb doctor`.
2. Confirm a vault exists (`.hbedit/state.json` in the tree). If absent,
   run `hb init` in the project root.
3. Read the `.md` and confirm intent with the user if there is any ambiguity.
4. `hb push <path>` — on `action: "created"`, report the new `cardId`.
5. Commit the `.md` and `state.json` together so other machines inherit the
   binding.

---

### SOP C — Continue editing on a second machine after git clone

After `git clone`, the per-machine cache (`~/.hbedit/cache/<vault-id>/`) is
absent on the new machine — only `.hbedit/state.json` is committed.
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

### SOP D — Read-only access to a card

1. `hb doctor`.
2. If already tracked, read the `.md` directly.
3. If not tracked, `hb pull <cardId> <path>`, then read the resulting `.md`.

---

### SOP E — Edit tags on an existing card

1. `hb doctor`.
2. Verify path is in `state.json`. If not, pull first (SOP A steps 1–2).
3. To add: `hb tag add <path> <name>`. On `tag-ambiguity`, show the warning
   and ask the user to confirm before retrying.
4. To remove: `hb tag remove <path> <name>`. On `tag-not-on-card`, no action
   needed.
5. Commit `state.json`.

---

### SOP F — Multi-step composites (split / merge / batch)

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
   want to trash it manually.
5. Commit.

**Batch push (multiple files):**
1. List all candidate files; show the user the batch and confirm before
   starting.
2. Push files one at a time, collecting results. On any error, stop and
   report — do not continue past a `state-corrupt` error.

---

### Conflict resolution (referenced by SOPs A and C)

When `hb push` returns `code: "content-conflict"` or `hb pull` returns
`action: "conflict"`, a `.conflict.md` backup of local edits has been
created and the working `.md` now holds the remote version.

1. Present both files to the user.
2. Produce a merged version (semantic merge) and confirm with the user.
3. Write the merged content to the working `.md`.
4. `hb push <path>`.

## Error Code SOPs

| Code | What happened | Agent steps |
| --- | --- | --- |
| `cli-missing` | `heptabase` binary not on PATH | 1. Inform user the Heptabase CLI is not installed. 2. Direct them to install it (heptabase.com or `npm i -g @heptabase/cli`). 3. Pause; do not continue until `hb doctor` returns ok. |
| `cli-version-unsupported` | CLI version outside `0.3.x` | 1. Tell user the installed CLI version is unsupported. 2. Ask them to update (`npm update -g @heptabase/cli` or reinstall). 3. Pause. |
| `app-not-running` | Desktop app closed | 1. Tell user the Heptabase desktop app is not running. 2. Ask them to launch it (or run `heptabase start`). 3. Pause. |
| `not-in-vault` | No `.hbedit/` ancestor found | 1. Tell user there is no hbedit vault for this path. 2. Ask: "Want me to run `hb init` here?" 3. If yes, run `hb init` and retry. |
| `file-not-found` | `path` doesn't exist on disk | 1. Inform user the path was not found. 2. Ask them to confirm the path or correct any typo. 3. Retry with the confirmed path. |
| `path-exists-untracked` | First-time pull would overwrite an untracked file | 1. Tell user the path is already occupied by an untracked file. 2. Ask: choose an alternative path, or confirm removal of the existing file. 3. Proceed based on user choice. |
| `path-not-tracked` | `state.json` has no entry for `path` | 1. Tell user this file is not tracked. 2. Ask: "Create a new card for it?" (use `hb push`) or "Link it to an existing card?" (get cardId, use `hb pull <cardId> <path>`). |
| `no-baseline` | Tracked path has no local sync state (fresh clone or partial deletion) | 1. Tell user the local cache for this card is missing. 2. Run `hb pull <path>` — smart pull will safely establish baseline or surface a conflict. 3. Follow the outcome (SOP C step 2). |
| `content-conflict` | Remote changed since last pull | 1. Tell user the remote was edited concurrently. 2. Follow the Conflict resolution SOP. |
| `tag-ambiguity` | New tag name looks like a typo of an existing tag | 1. Show the user the warning (which tag it resembles). 2. Ask: typo or intentional new tag? 3. If intentional, rerun `hb tag add` with the confirmed name. |
| `card-not-found` | cardId in state.json doesn't exist on Heptabase (possibly trashed) | 1. Tell user the card may have been trashed remotely. 2. Ask whether to remove the `state.json` entry and treat the file as untracked. 3. If yes, remove the entry manually and proceed. |
| `tag-not-on-card` | `hb tag remove` for a tag the card doesn't have | 1. Inform user the tag was not present on the card. 2. No further action needed. |
| `cardId-already-tracked` | First-time pull for a cardId already mapped to a different path | 1. Tell user the card is already linked to `<other-path>`. 2. Ask: edit there instead, or unlink first by removing the `state.json` entry? |
| `state-schema-unsupported` | `state.json` has `schemaVersion` other than 3 | 1. Inform user the state file is from an incompatible older version. 2. Advise running `hb init` in a fresh directory, or removing `.hbedit/` and starting over. v3 does not migrate v2 state files automatically. 3. Do not run any other hb command until resolved. |
| `state-corrupt` | `state.json` is invalid JSON or violates schema invariants | 1. Stop immediately. Do not run any other hb command. 2. Show user the corrupt content. 3. Ask them to fix it by hand or restore from git history. |
| `vault-nested` | `hb init` called inside an existing vault's tree | 1. Tell user there is already a vault at `<ancestor-path>`. 2. Ask: use that one, or remove the ancestor's `.hbedit/` if a separate vault is intentional? |
| `local-has-changes` | `hb pull` would overwrite a file with uncommitted local edits | 1. Tell user the local file diverges from the last sync. 2. Ask: push these changes first (`hb push <path>`), or discard them? 3. Proceed based on user choice; if discarding, revert the file manually before retrying pull. |

## Limitations

- **Card-to-card references** cannot be authored from markdown. Preserve
  existing references in card content; do not attempt to create new ones.
- **Push size cap** — a push is limited to approximately 100,000 characters
  of ProseMirror JSON. Very large cards may fail.
- **No remote event stream** — remote changes are detected only when `hb pull`
  is run. hbedit has no background sync.
- **Note cards only** — journal entries, PDFs, and other card types are not
  supported. Only `note` cards work with hbedit.
- **No `hb mv`** — renaming a tracked `.md` file requires manually editing
  the `path` key in `state.json`. The old path breaks the binding; the CLI
  will not auto-detect the rename.
