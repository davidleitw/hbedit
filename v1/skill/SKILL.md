---
name: heptasync
description: Edit and reorganize EXISTING Heptabase cards via a local-markdown
  workflow — pull a card to a .md file, edit it as plain text, push it back.
  Handles edits to the middle of a card, which the raw heptabase CLI cannot do.
  Use when the user wants to rewrite, restructure, clean up, or bulk-edit
  existing Heptabase notes. UNOFFICIAL — not affiliated with Heptabase.
---

# HeptaSync (unofficial)

> **This is an UNOFFICIAL community tool.** HeptaSync is not made by, endorsed
> by, or affiliated with Heptabase. It is a thin wrapper built entirely on top
> of the official `heptabase` CLI. If the user asks whether this is official:
> say no — it is a third-party tool; the official surfaces are the `heptabase`
> CLI and the Heptabase app. HeptaSync only ever calls the official CLI; it
> never touches Heptabase's database, storage, or internal files.

## What it is for

The official `heptabase` CLI can **create** cards and **append** to them, but it
cannot edit the middle of an existing card from markdown (`note save` needs
Heptabase's internal ProseMirror JSON). HeptaSync closes that gap:

- **pull** — a card → a local `.md` file (plain markdown + a hidden `heptabase:`
  frontmatter block).
- **edit** — change the `.md` body with ordinary file tools.
- **push** — the edited `.md` → back into the same card, same identity.

For a plain "new card" or "append to a card", use the official `heptabase` CLI
directly — it is simpler. Reach for HeptaSync when the job is *rewriting or
restructuring* existing notes.

## Prerequisites

- The official `heptabase` CLI installed and the desktop app running
  (`heptabase start`). HeptaSync sits on top of it.
- `heptabase --version` within the supported range (`0.3.x`). Outside it: STOP
  and ask the user to update before continuing.
- Python 3.9+ (the converters are stdlib-only Python).

## Workflow

1. **Pull** — `hs pull <cardId>`: reads the card, converts ProseMirror JSON →
   Markdown, writes `<slug>.md` (with a `heptabase:` frontmatter block) and a
   sidecar `.heptasync/<cardId>.json` (the raw JSON — required for push).
2. **Edit** — change the `.md` body with ordinary tools. Never edit the
   `heptabase:` frontmatter.
3. **Push** — `hs push <file>`: builds a throwaway scratch card from the edited
   body so Heptabase performs the markdown→ProseMirror conversion, transplants
   the original card's block IDs onto the surviving blocks, `note save`s it back
   guarded by `contentMd5`, trashes the scratch card, refreshes the sidecar and
   frontmatter.

## Decision rules

Run these checks on every push:

- **Size pre-flight.** Estimate the resulting ProseMirror JSON. `note save` is
  capped at 100,000 chars (≈ 700 lines of mixed-content markdown). Over that →
  see "Oversized card".
- **Conflict.** If `note save` returns `Content conflict`, the card also changed
  in Heptabase since it was pulled. Do not overwrite: save the local body as
  `<slug>.conflict.md`, re-pull, and tell the user.
- **Oversized card.** If the change is append-only (content only added at the
  end) → use `heptabase note append`, no split needed. If it edits the middle of
  an oversized card → do NOT auto-fix: tell the user the concrete reason and
  propose splitting the card at a natural heading boundary. On approval, split
  the local file in two (the first part keeps the cardId; the second gets no
  cardId → becomes a new card); copy the original card's tags and whiteboard
  memberships onto the new card. Never split silently.
- **References.** Card-to-card references cannot be authored from markdown.
  Preserve existing ones; never try to create them from a `.md` file.

## Known limitations

- Card-to-card references can only be created inside the Heptabase app.
- Push is limited to ~100,000 chars of ProseMirror JSON per card.
- No event stream — remote changes are found by polling `card list`.
- Whiteboard position is not controllable (membership only).
- Journals are date-keyed and handled separately from notes.

## Warnings

- `push` overwrites real card content. When unsure, confirm with the user first.
- Only ever go through the official `heptabase` CLI. Never read or write
  Heptabase's database, storage, or cache directly.
- Splitting a card changes the user's knowledge structure — always propose it,
  never do it silently.
