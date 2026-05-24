---
name: hbedit
description: Edit Heptabase cards through local markdown files with `state.json`
  binding. Only path for editing the middle of an existing card (block-ID
  transplant), pushing a local md as a tracked card, maintaining a card↔file
  binding across machines via git, or precise tag changes on existing cards.
  Use when the user wants to edit existing card content, continue editing
  after git clone, push a local markdown file to Heptabase, change tags on
  an existing card, or remove a card's local binding. Base `heptabase` CLI
  handles one-shot creates, appends, reads, searches — hbedit owns ongoing
  maintenance.
allowed-tools: Bash(hb *) Bash(heptabase *)
---

# hbedit (unofficial)

> Non-official. Built only on the official `heptabase` CLI; never reads
> or writes Heptabase's database, storage, or internal files. If asked
> whether this is official: it is not.

## What hbedit uniquely does

- Edit the middle of an existing card via block-ID transplant (base CLI cannot).
- Maintain a card↔file binding committed in `.hbedit/state.json` so the same
  card can be edited from multiple machines via git.
- Push a local markdown file as a tracked card with bidirectional sync.
- Add/remove tags on an existing card without disturbing other tags.

## Default behavior

| Situation | Default | Escape hatch |
|---|---|---|
| User asks markdown→card, in a vault | `hb push <path>` (tracked) | Explicit «一次性» / «不用追蹤» / «隨手» / «丟上去就好» → `heptabase note create` |
| User points at existing tracked file (by cardId or path) | hbedit (`hb pull` if stale, edit, `hb push`) | None — hbedit is the only correct tool |
| User says «剛 clone 進來» / «另一台機器» | `hb pull <path>` smart-sync first | None |
| Pure read / search / list | base CLI | None — hbedit adds no value |
| Generic «Heptabase 設置 OK 嗎» | base CLI's `heptabase --version` | User specifically asks about vault/sync state → `hb doctor` |
| Not in a vault, user wants to push | base CLI's `heptabase note create` | User explicitly wants to start syncing → `hb init` first |

Mistake recovery: if `hb push` ran when the user actually wanted
fire-and-forget, run `hb unlink <path>` to drop the binding cleanly
(local md and remote card both untouched).

## Preflight

`hb doctor` runs once before any other hb command. On error, look up the
`code` field in `references/errors.md`.

## Vault model

`.hbedit/state.json` (committed, git-tracked) binds `path → {cardId, tags}`
plus `vaultId` (UUIDv4, set at `hb init`). Per-machine cache at
`~/.hbedit/cache/<vaultId>/` (`local-state.json` + `sidecar/<cardId>.json`).
A directory is an hbedit vault if it or any ancestor contains
`.hbedit/state.json` (the *file* — an empty `.hbedit/` does not count).

## Commands

Run `hb <cmd> --help` for flags, output JSON shape, and command-specific
error codes.

- `hb doctor` — preflight + per-vault cache state report
- `hb init` — initialize a vault in the current directory
- `hb push <path>` — create new card or update existing (block-ID transplant)
- `hb pull <cardId> <path>` — first-time bind by cardId
- `hb pull <path>` — smart-sync a tracked path (baseline / noop / updated / conflict)
- `hb tag add|remove <path> <name>` — round-trip safe tag edits
- `hb unlink <path>` — remove binding without deleting local md or remote card

## Limitations

- Card-to-card references can't be authored from markdown.
- ~100,000 char ProseMirror push cap; very large cards may fail.
- Note cards only — no journal, PDF, or whiteboard.
- No `hb mv`: renaming a tracked .md requires manual `state.json` edit.

## Look up

- Workflow SOPs (edit / multi-machine / split / merge / batch / conflict
  resolution): `references/workflows.md`
- Error code handling per `code`: `references/errors.md`
- Per-command detail: `hb <cmd> --help`
