# Card-embed round-trip — v0.1.2 design

**Status:** approved, pending implementation
**Date:** 2026-05-25
**Target release:** v0.1.2
**Author:** session 2026-05-25 (Claude + davidlei)

## Problem

`hb push` on a card that contains a Heptabase card embed (a `card` node in
the underlying ProseMirror) silently destroys the embed. The embed gets
serialized by `pm2md` to a `[[card:UUID]]` text placeholder, the user pushes
back, and Heptabase's markdown parser turns the placeholder into plain text
in a new `text` node — no embed, no warning, no error. README v0.1.1 calls
this out as "No card-to-card references from markdown" but the wording
understates the impact: the round-trip pull → no-op edit → push degrades
existing embeds even when the user never touched them.

Empirical evidence: created a card "Test 02" containing an embed of
"Test 01", piped its ProseMirror through `pm2md.to_markdown` and then
`heptabase note create -f <md>`. The round-tripped card's ProseMirror
contains **0** `card` nodes; the cardId survives only as literal text
inside a paragraph.

Test 01 also confirms Heptabase supports **inline** card embeds
(paragraph: `[text "詳細請參考 ", card, text " 這張卡片"]`), so any fix
has to handle inline positions, not just block-only.

## Goal

Make `[[card:UUID]]` round-trip losslessly through `hb push`, so a user
can pull a card with embeds, edit the markdown, push it back, and the
embeds survive (along with any new ones they add via the same syntax).

Non-goals (explicitly):

- Date inline nodes (`<!-- UNCONVERTED inline date -->`). Same mechanism
  will work; out of scope for v0.1.2.
- `mention` or other Heptabase-specific node types not in pm2md's current
  output. Out of scope.
- Pre-validating that the referenced cardId actually exists in Heptabase.
  Heptabase UI already shows "missing card" placeholders for dangling
  refs; pre-validation costs a network round-trip per placeholder for
  marginal UX gain.
- Markdown-side escape syntax beyond what already exists (backtick code
  marks). No new `\[\[` syntax.

## Mechanism (the technical principle to be documented in README)

`heptabase note create -f <md>` runs the user's markdown through
Heptabase's official parser. That parser knows nothing about
`[[card:UUID]]` — our placeholder — so it preserves it as plain text.
There's no way to get a card embed in via this path.

But `heptabase note save <cardId> -f <pm.json>` accepts arbitrary
ProseMirror JSON and stores it as-is. So hbedit can:

1. Let `heptabase note create` parse the markdown into ProseMirror
   (with `[[card:UUID]]` as text).
2. Post-process the resulting ProseMirror locally: walk the doc, find
   text nodes containing `[[card:<valid uuid>]]`, replace each match
   with a `card` node (and split the surrounding text accordingly).
3. `heptabase note save` the modified ProseMirror back.

This is exactly the same trick hbedit already uses for block-ID
transplant (create scratch → mutate → save), applied to a different
mutation. The CLI surface stays read/write-as-documented; no
undocumented APIs.

## Substitution rules (Option B from brainstorm)

| Where in PM | Substitute? |
|---|---|
| Plain text node, no `code` mark, not inside `code_block` | **Yes** |
| Text node with `code` mark | No (preserved as text) |
| Any descendant of a `code_block` node | No (preserved as text) |
| Inside `strong` / `em` / `link` marks | Yes; card node carries no marks, surrounding text segments keep their marks |
| Inside `heading` / `list_item` / `blockquote` / `todo_list_item` / etc. | Yes; let Heptabase reject if its schema doesn't allow that position |
| Inline (text + card + text in one paragraph) | Yes — Heptabase's PM schema supports this (proven via Test 01) |

UUID regex (case-insensitive, normalized to lowercase before storing):

```
[[card:([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})]]
```

Anything not matching — typos, partial UUIDs, whitespace inside,
unclosed brackets — is left as plain text.

## Architecture

### New code

```
skills/hbedit/scripts/
└── pm2md.py
    + substitute_card_placeholders(doc: dict) -> dict
      DFS over PM doc; for each text node, if no `code` mark and not
      inside `code_block`, regex-split on the placeholder pattern;
      emit interleaved text/card sequence. Pure function; deep-copies
      input on entry.
```

### Touched code

```
skills/hbedit/scripts/hbedit.py
  _push_create:
    after `note_create`, if "[[card:" in body:
        intermediate = note_read(card_id)
        substituted = substitute_card_placeholders(json.loads(intermediate.content))
        note_save(card_id, json.dumps(substituted), intermediate.contentMd5)
    on save failure: emit "create-failed" with detail noting that the
    card exists but substitution failed.

  _push_update:
    in the scratch-card flow, immediately after `note_read(scratch.id)`
    and before `transplant.transplant_ids`:
        new_doc = substitute_card_placeholders(new_doc)
    No new round-trips; pure in-memory.
```

### Untouched code

- `htb.py` — stays a thin CLI wrapper. Placeholder logic is hbedit
  business, not htb.
- `transplant.py`, `vault.py`, `local_state.py`, `tagsync.py` — unchanged.
- `pm2md.to_markdown` — unchanged.
- `errors.py` — no new error codes. Substitution failure in
  `_push_create` borrows the existing `create-failed` code with a
  descriptive `detail`.
- All pull paths, `hb doctor`, `hb init`, `hb tag *`, `hb unlink` — unchanged.

### Why substitute BEFORE transplant (not after)

`transplant.transplant_ids` matches blocks across old/new docs using
`(type, block_text)` signatures, where `block_text` is the concatenated
text of all descendants. A `card` node contributes 0 to that text. So:

- A paragraph wrapping a `card` node has `block_text == ""`.
- A paragraph wrapping the same content as a `text` node (`"[[card:UUID]]"`)
  has `block_text == "[[card:UUID]]"`.

The user's `old_doc` (sidecar) holds the previous state — already with
`card` nodes (empty block_text). The fresh `scratch_doc` from Heptabase's
parser has the placeholder as `text` (non-empty block_text). If we ran
transplant before substituting, the paragraph signatures would diverge,
transplant would mark old as deleted + new as inserted, fresh block IDs
get assigned, and any cross-card block references pointing at those
paragraphs would break.

By substituting first, both old and new paragraphs around card embeds
have `block_text == ""`; transplant sees identical signatures and
correctly preserves block IDs.

## Regression safety

| Scenario | v0.1.1 | v0.1.2 |
|---|---|---|
| `hb doctor`, `init`, `pull`, `tag *`, `unlink` | works | identical |
| `hb push` body contains no `[[card:` | works | **byte-for-byte identical** (fast-path in `_push_create`; `_push_update` does a deepcopy + no-op substitute that produces a structurally identical JSON serialization) |
| `hb push` body had a card embed (pull-then-push round-trip) | silent data loss | **embed preserved** (intended fix) |
| User wrote literal `[[card:UUID]]` text without backtick escape | preserved as text | **becomes embed (breaking)** — only known regression, called out in README and changelog |
| `[[card:not-a-uuid]]` or other invalid match | preserved | preserved (regex miss) |
| `` `[[card:UUID]]` `` (backticked) | preserved as code text | preserved as code text |
| Existing 63 unit tests | green | green (verified post-implementation) |

The one explicit behavior change — literal-placeholder-becomes-embed — is
inherent to the feature and called out in both READMEs and the changelog.

## Edge cases (resolved)

Every case identified during brainstorming, with the resolved handling:

| # | Case | Handling |
|---|---|---|
| 1.1 | Multiple placeholders in one text node | regex `finditer`; emit interleaved sequence |
| 1.2 | Adjacent placeholders, no space | empty interstitial text segment dropped (`if start > cursor`) |
| 1.3 | Placeholder at text start | no leading text segment emitted |
| 1.4 | Placeholder at text end | no trailing text segment emitted |
| 1.5 | Whole text node IS the placeholder | sequence = `[card]` |
| 1.6 | Invalid UUID format | regex miss → preserved |
| 1.7 | Uppercase UUID | accepted; `.lower()` before storing |
| 1.8 | Nonexistent cardId | no pre-validation; Heptabase shows "missing card" |
| 1.9 | Inside `code` mark | text node skipped entirely |
| 1.10 | Inside `code_block` subtree | recursion stops at `code_block` |
| 1.11 | Inside `strong` / `em` / `link` marks | substitute; card node carries no marks; surrounding text segments keep marks |
| 1.12 | In heading / list / blockquote / todo / table | substitute; Heptabase's schema is source of truth |
| 1.13 | Self-reference (`[[card:<own-id>]]`) | not specially handled |
| 1.14 | Unclosed (`[[card:abc`) | regex miss → preserved |
| 1.15 | Escape for literal text | use backtick code mark; no new escape syntax |
| 2.1 | `_push_create` extra round-trip cost | fast-path: skip read+save when `"[[card:" not in body` |
| 2.2 | Substitute position in `_push_update` | before transplant (justified above) |
| 2.3 | `_push_create` save fails after substitute | emit `create-failed`; card exists with placeholder text; user decides to trash/fix |
| 2.4 | `_push_update` save fails | unchanged from current logic; scratch trashed in `finally` |
| 2.5 | Heptabase rejects substituted PM (schema) | `note_save` error bubbles up via existing handlers |
| 3.1 | Pull→edit→push round-trip with embeds | works (the fix) |
| 3.2 | Sidecar / md5 / cache update | existing post-save `note_read` already refreshes; no change needed |
| 3.3 | Conflict detection (`--content-md5`) | unaffected; substitution doesn't touch lock_md5 |
| 3.4 | Concurrent third-party edit | unchanged; Heptabase server-side md5 check |
| 3.5 | Date / mention / other node types | out of scope; document as known limitation |
| 4.1 | Cards with no placeholder | no-op; byte-identical save payload |
| 4.2 | Existing tests | audit grep (`tests/`); none expected to depend on prior behavior |
| 4.3 | User wrote `[[card:UUID]]` as plain text | becomes embed (only behavior change; called out) |
| 4.4 | hbedit's own documentation cards | audit; require backtick wrapping where the placeholder is mentioned literally |

Known limitations (carry-forward):

- Adjacent text nodes splitting a placeholder
  (`[{text:"[[card:"}, {text:"A]]"}]`) won't substitute. Heptabase's
  parser doesn't produce this in practice; no auto-merge.
- Deeply nested docs (>1000 levels) would hit Python's recursion limit.
  Not encountered in practice.
- Inline `date` nodes still serialize to `<!-- UNCONVERTED inline date -->`
  and don't round-trip. Same mechanism would address this in a future
  release.

## Testing strategy

### Layer 1 — `substitute_card_placeholders` unit tests

`tests/test_pm2md.py` (new or extended). One test per edge case from
the table above. ~20 tests covering basic split, marks, code protection,
multiple matches, boundary positions, invalid UUIDs, structure preservation,
input non-mutation.

### Layer 2 — Push integration tests

`tests/test_push_card_refs.py` (new). Mock `htb.note_create` /
`note_read` / `note_save`; drive `_push_create` and `_push_update` end
to end:

- `_push_create` fast-path: no `[[card:` in body → `note_read` called
  once (final sidecar refresh) and no extra `note_save`.
- `_push_create` with placeholder: `note_read` called twice
  (intermediate + final), `note_save` called once with substituted PM
  containing a `card` node.
- `_push_create` substitution save failure: emit `create-failed` with
  detail mentioning the cardId and that substitution failed.
- `_push_update` substitution position: intermediate scratch read
  returns text-form placeholder → save payload contains `card` node
  with paragraph IDs inherited from `old_doc`.
- `_push_update` no-placeholder regression: save payload byte-identical
  to v0.1.1 path.

~6 integration tests.

### Layer 3 — Manual TCs (human-driven)

To run before tagging v0.1.2. Required (must pass):

- **M1**: pull a real card that contains a card embed → edit unrelated
  text → push → embed survives in Heptabase UI.
- **M5**: push a brand-new markdown file containing `[[card:<real UUID>]]`
  → new card has working embed.
- **M6** (regression): pull a card with **no** embeds → edit → push →
  visual diff in Heptabase only reflects the user's edits.

Nice-to-have (run if time):

- **M2**: add a new `[[card:<UUID>]]` to an existing tracked card → push
  → new embed appears.
- **M3**: backtick-wrap an existing placeholder → push → embed becomes
  plain text (explicit opt-out works).
- **M4**: delete a placeholder line → push → embed gone from Heptabase.
- **M7**: push markdown with `[[card:not-a-real-id]]` (invalid format)
  → stays as text in Heptabase.
- **M8**: push markdown with `[[card:<valid-format-but-nonexistent>]]`
  → Heptabase renders dangling-ref placeholder.

### Audit grep (one-time, pre-implementation)

```sh
grep -rn '\[\[card:' tests/
# expect: no hits — no existing test depends on prior behavior

grep -rn '\[\[card:' skills/ docs/ README.md README.zh.md INSTALL.md CLAUDE.md
# expect: any hits must already be backtick-wrapped; otherwise wrap them

heptabase note read b375e20a-f49e-47b6-8479-ada0bd11136a | grep -c '\[\[card:'
# expect: 0 — confirm own backlog card doesn't contain unwrapped placeholders
```

### CI

Existing GitHub Actions workflow runs `pytest tests/`. New test files
auto-pick up. **No workflow changes.**

## README updates

### `README.md` and `README.zh.md`

**New subsection under "Architecture & how it works":**

> ### Card references round-trip
>
> Heptabase cards can embed other cards (a `card` node in the underlying
> ProseMirror, rendered as an inline or block-level reference in the UI).
> `pm2md` serializes such an embed as the placeholder string
> `[[card:<UUID>]]` in markdown. On push, hbedit converts the placeholder
> back into a real `card` node — but it can't do this through
> `heptabase note create`, whose markdown parser doesn't understand the
> placeholder. Instead it uses a two-step trick:
>
> 1. Let `heptabase note create` parse the markdown normally. The
>    placeholder ends up as plain text.
> 2. Read the resulting ProseMirror back, walk it, replace each
>    `[[card:<valid-uuid>]]` text occurrence with a `card` node, and
>    `heptabase note save` the modified ProseMirror.
>
> Step 2 only runs when the source markdown contains the literal string
> `[[card:`. For cards without embeds the extra round-trip is skipped.
>
> Two consequences worth knowing:
>
> - **If you write `[[card:<UUID>]]` as literal text** (e.g. when writing
>   documentation about hbedit), wrap it in backticks. Unwrapped, hbedit
>   treats it as a real card reference on push — and if the UUID isn't
>   a real cardId, you'll get a dangling reference in Heptabase's UI.
> - **The placeholder syntax is case-insensitive** but lowercased before
>   storage. `[[card:ABC...]]` works.
>
> `date` inline nodes and `mention` nodes don't yet round-trip; pm2md
> emits `<!-- UNCONVERTED ... -->` markers and pushing back loses them.

**Update "Current limitations":**

Replace:

> - **No card-to-card references from markdown.** Block references into
>   other cards can't be expressed in plain markdown, so they can't round-trip.

With:

> - **Card embed round-trip works since v0.1.2** via the
>   `[[card:<UUID>]]` placeholder syntax (see "Card references
>   round-trip" above). Block-level cross-card *block references*
>   (pointing at a specific block inside another card) still don't
>   round-trip — only whole-card embeds.
> - **`date` inline nodes don't round-trip.** They serialize as
>   `<!-- UNCONVERTED inline date -->` and pushing loses them.

(Equivalent rewording in `README.zh.md`.)

**Update `## Changelog`:**

```markdown
### v0.1.2 — <ship date>

- Card embeds (`card` nodes in ProseMirror) now round-trip through
  `hb push`. The placeholder syntax `[[card:<UUID>]]` in markdown
  is converted to a real card node before saving. Mechanism: post-
  process the ProseMirror that Heptabase's parser returns from
  `note create`, then `note save` the modified version. See
  Architecture → Card references round-trip.
- **Breaking** for anyone who relied on the previous behavior of
  `[[card:<UUID>]]` being preserved as plain text on push: it now
  becomes a real card embed. Wrap such literal text in backticks
  (`` `[[card:<UUID>]]` ``) to keep it as text.
- No behavior change for cards without any `[[card:` substring in
  their markdown: the new code path is gated behind a string check
  and skipped entirely.
```

(zh translation in `README.zh.md`.)

## Implementation order

1. **Audit grep** — confirm no existing tests/docs depend on prior
   behavior; wrap any literal placeholder mentions found.
2. **Add `substitute_card_placeholders` to `pm2md.py`** with full unit
   test coverage (Layer 1). All ~20 unit tests pass before touching
   hbedit.py.
3. **Wire `_push_update`** — one-line insert. Run integration tests
   for update path.
4. **Wire `_push_create`** — fast-path + substitution block. Run
   integration tests for create path.
5. **Run full `pytest tests/`** — confirm 63 baseline + new tests all
   green.
6. **Run manual TCs M1, M5, M6** against real Heptabase.
7. **Update READMEs and CLAUDE.md changelog** per the wording above.
8. **Bump `plugin.json` to 0.1.2.**
9. **Commit, tag `v0.1.2`, push** following the release discipline in
   CLAUDE.md.

## Open questions resolved during brainstorm

- Substitute placement scope (block-only / non-code / everything) →
  **non-code** (Option B). Justified by Test 01 confirming inline
  embeds are valid Heptabase PM and by the need to protect
  documentation text.
- cardId existence pre-check → **no**. Heptabase handles dangling refs;
  pre-check adds latency for marginal gain.
- New error code for substitution failure → **no**. Reuse
  `create-failed` with descriptive `detail`.
- Date / mention support → **out of scope for v0.1.2**.

## Open questions deferred to implementation

None. All decisions resolved in this spec.
