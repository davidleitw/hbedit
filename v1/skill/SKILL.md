---
name: hbedit
description: Edit and reorganize existing Heptabase note cards via a local-markdown workflow — pull a card to a .md file, edit it as plain text, push it back. Handles edits to the middle of a card, which the raw heptabase CLI cannot do. Use when rewriting, restructuring, or cleaning up existing Heptabase notes. UNOFFICIAL — not affiliated with Heptabase.
---

# hbedit (unofficial)

> UNOFFICIAL community tool. hbedit is built only on the official
> `heptabase` CLI; it never reads or writes Heptabase's database, storage,
> or internal files. If asked whether it is official: it is not.

## Step 0 — preflight (MANDATORY)

Before any sync, run `hb doctor`. It prints JSON with a `status` field. If
`status` is not `ok`, STOP and relay its `detail` to the user:

| doctor `status` | meaning → what you do |
|---|---|
| `ok` | environment is good — proceed |
| `cli-missing` | the `heptabase` CLI is not installed — tell the user to install it |
| `cli-version-unsupported` | CLI version is outside `0.3.x` — tell the user to update |
| `app-not-running` | the Heptabase desktop app is closed — tell the user to run `heptabase start` |

## Workflow

hbedit exists to **edit the middle of an existing card** — something the
raw `heptabase` CLI cannot do. To create a plain new card or append to one,
use the official `heptabase` CLI directly; it is simpler.

1. `hb pull <cardId> <vault>` — pulls the card into `<vault>/notes/` as a
   `.md` file. Find the cardId first with `heptabase card list -q "<title>"`.
2. Edit the `.md` body with ordinary file tools. Never edit the hidden
   `heptabase:` frontmatter block — it ties the file to its card.
3. `hb push <file>` — pushes the edited `.md` back into the same card.

> Caution: `hb pull` overwrites the working `.md` file with the card's
> remote content. If the file has un-pushed local edits, `hb push` them
> first — a direct `hb pull` does not back them up (only a conflict
> detected during `hb push` creates a `.conflict.md` backup).

## Reacting to push outcomes

`hb push` overwrites real card content. Watch its output:

- **`push: updated [...]; tags +N -M  -> card ...`** — success.
- **`push: conflict (local saved to <name>.conflict.md) -> card ...`** —
  the card changed in Heptabase since it was pulled. `hb` saved the user's
  version to `<name>.conflict.md` and re-pulled the remote latest over the
  working file. Tell the user; they reconcile the two by hand.
- **exits non-zero with `tag '...' is close to existing '...'`** — a
  frontmatter tag looks like a typo of an existing tag. STOP; ask the user
  whether it is intentional, then fix the `tags:` line and push again.
- **exits non-zero with `has no contentMd5`** — the file was never pulled
  by hbedit; `hb pull` the card first.

## Limitations

- Card-to-card references cannot be created from markdown — preserve
  existing ones, never try to author them.
- A push is capped at ~100,000 characters of Heptabase-internal JSON; a
  very large card may fail to push.
- No event stream — remote changes are found only when you pull.
