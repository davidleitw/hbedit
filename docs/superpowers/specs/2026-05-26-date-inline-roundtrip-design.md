# Date-inline-node round-trip — v0.1.4 candidate design

**Status:** draft, pending user review
**Date:** 2026-05-26
**Target release:** TBD — not bundled with a release on its own; will ship together with the upcoming errors.md / release work
**Author:** session 2026-05-26 (Claude + davidlei)

## Problem

`pm2md.to_markdown` does not encode the data inside Heptabase's `date`
inline node. Currently it falls through to the catch-all and emits
`<!-- UNCONVERTED inline date -->`. The HTML comment carries no date,
and on push:

1. `heptabase note create` parses the comment into whatever its
   markdown parser does with HTML comments (likely a text node with
   the literal comment, or stripped entirely).
2. Either way, the original `date` node is destroyed.

A user who pulls a card containing a date inline node, makes any edit,
and pushes loses the date silently — same shape as the v0.1.2 card
embed bug. The known-limitations bullet about this is in both READMEs;
this design closes the gap.

Empirical evidence (Test 01 / card `f20c620f-f442-4fc5-acf8-0d94c4d8391b`):

```
DATE NODE: {"type": "date", "attrs": {"date": "2026-05-26"}}
```

The structure is minimal — a single ISO `YYYY-MM-DD` string in
`attrs.date`. No time, no timezone, no other fields. The design treats
this as the only currently-supported shape.

## Goal

Make `date` inline nodes round-trip losslessly through `hb pull` →
edit → `hb push`. As a side effect, users gain the ability to author
or edit dates by writing the placeholder syntax in markdown directly.

**Non-goals:**

- `mention` and other unhandled inline node types. Same mechanism would
  work; out of scope.
- Time-of-day or timezone support in dates. The current Heptabase date
  node schema does not carry these fields; if it ever does, that is a
  separate placeholder revision (e.g. `[[datetime:...]]`).
- Migrating already-pulled `.md` files that still contain
  `<!-- UNCONVERTED inline date -->` comments. Users re-pull to refresh.
- Releasing on its own. This work bundles with the errors.md / release
  work; no `plugin.json` bump, no Changelog entry, no SKILL.md
  "Verified against" bump in this PR.

## Mechanism

Identical pattern to v0.1.2 card embed round-trip, but **bidirectional**:

**Pull (new `to_markdown` behavior):**

Inside `_inline_node`, when the node is `type == "date"`, emit
`[[date:YYYY-MM-DD]]` if and only if `attrs.date` matches the strict
`YYYY-MM-DD` regex AND `datetime.date.fromisoformat(s)` accepts it.
Otherwise fall back to the existing `<!-- UNCONVERTED inline date -->`
emission. Falling back is deliberate: a placeholder we cannot round-trip
losslessly should not look like one.

**Push (new post-processor):**

After `heptabase note create` returns ProseMirror with the placeholder
preserved as plain text (see "Key assumption" below), walk the doc and
substitute each `[[date:<valid-date>]]` text occurrence with a real
`date` inline node. Same code-mark / `code_block` protection as the
card placeholder substitution.

## Key assumption — empirical preflight required

The v0.1.2 mechanism relies on `heptabase note create` preserving the
literal `[[card:UUID]]` text as a plain text node in ProseMirror. We
verified this empirically for `[[card:...]]` before designing v0.1.2.

For `[[date:YYYY-MM-DD]]` we have **not** yet verified the same. The
parser might recognize date-shaped strings or `[[...]]`-shaped strings
in some way we haven't tested.

Task 1 of the implementation plan is a preflight script:

```
# Pseudocode for the preflight task
md = "preflight\n\n[[date:2026-05-26]] tail\n"
card = heptabase note create -f <md>
pm = heptabase note read <card.id>
# Expected: a text node containing the literal "[[date:2026-05-26]] tail"
# (or similar with surrounding splits), with NO date node.
# Cleanup: heptabase card trash <card.id>
assert "date" not in [n["type"] for n in walk(pm)]
assert "[[date:2026-05-26]]" in concatenated_text(pm)
```

If the assumption fails — Heptabase's parser does something special with
the placeholder — this design must be scrapped and reconsidered (likely
moving to HTML-comment syntax instead). Preflight is a hard gate before
any code change.

## Substitution rules

Identical to v0.1.2 card embed, with the date placeholder replacing the
card one:

| Where in PM | Substitute? |
|---|---|
| Plain text node, no `code` mark, not inside `code_block` | **Yes** (if date validates) |
| Text node with `code` mark | No (preserved as text) |
| Any descendant of a `code_block` node | No (preserved as text) |
| Inside `strong` / `em` / `link` marks | Yes; date node carries no marks; surrounding text segments keep their marks |
| Inside `heading` / `list_item` / `blockquote` / table cell | Yes; Heptabase's schema is source of truth |
| `[[date:not-a-real-date]]` (regex passes but date invalid, e.g. `2026-13-99`) | No (calendar validation fails → preserved as text) |
| `[[date:2026-5-26]]` / `[[date:2026/05/26]]` / partial / unclosed | No (regex miss → preserved) |

Validation regex (strict):

```
\[\[date:(\d{4}-\d{2}-\d{2})\]\]
```

Followed by `datetime.date.fromisoformat(match.group(1))` for calendar
sanity (rejects `2026-02-30`, `2026-13-01`, etc.). Both sides must pass.

## Architecture

### New code

```
skills/hbedit/scripts/pm2md.py
  + substitute_date_placeholders(doc: dict) -> dict
    Same DFS shape as substitute_card_placeholders; calls a date-
    specific splitter. Pure function; deep-copies input on entry.

  + _split_text_on_date(text_node) -> list[dict]
    Skips text with `code` mark. Regex-finditer the strict date
    pattern. For each match, validate via datetime.date.fromisoformat;
    if invalid, skip that match (leave as text). Emit interleaved
    text/date sequence.
```

### Internal refactor (touched but contract-preserving)

```
skills/hbedit/scripts/pm2md.py
  ~ _walk_substitute(node) -> _walk_substitute(node, splitter)
    Parametrize the text-node transformation. Both card and date
    substitute go through the same walker.

  ~ _split_text_on_placeholder renamed to _split_text_on_card
    Pure rename. Reflects that it is one of multiple splitters now.
    No public symbol changes; substitute_card_placeholders signature
    unchanged.
```

Existing card unit tests (~20) should all stay green without
modification. If any reference the private `_split_text_on_placeholder`
symbol directly, update those references — that is the only acceptable
test diff for the refactor task.

### Modified to_markdown

```
skills/hbedit/scripts/pm2md.py :: Converter._inline_node
  Branch `t == "date"`:
    raw = node.get("attrs", {}).get("date") or ""
    if matches strict regex AND datetime.date.fromisoformat(raw) ok:
        return "[[date:" + raw + "]]"
    else:
        self.unknown_nodes.add("date")
        return "<!-- UNCONVERTED inline date -->"
    # The unknown_nodes accounting on the fallback path keeps
    # existing pull-time diagnostics intact for genuinely unhandled
    # date variants (e.g. future Heptabase additions).
```

### Touched wiring

```
skills/hbedit/scripts/hbedit.py
  _push_create:
    Fast-path gate:
        if "[[card:" in body or "[[date:" in body:
            ... intermediate read ...
            new_doc = pm2md.substitute_card_placeholders(new_doc)
            new_doc = pm2md.substitute_date_placeholders(new_doc)
            ... save ...
    Error detail string: generalize from "card-ref substitution failed"
    to "placeholder substitution failed" so the message is accurate
    when only date placeholders were involved.

  _push_update:
    In the scratch flow, after note_read(scratch.id) and before
    transplant.transplant_ids:
        new_doc = pm2md.substitute_card_placeholders(new_doc)
        new_doc = pm2md.substitute_date_placeholders(new_doc)
```

Two deepcopies (one per substitute) is wasteful but acceptable; real
docs are small. Not worth chaining splitters into a single walk.

### Untouched code

- `htb.py`, `transplant.py`, `vault.py`, `local_state.py`,
  `tagsync.py`, `errors.py` — no changes.
- All SOPs in `references/` — no changes.
- `SKILL.md` — no changes (in particular, the "Verified against
  Heptabase CLI" line stays at `0.3.x`).
- `.claude-plugin/plugin.json` — no version bump.
- `README.md` / `README.zh.md` Changelog — no new entry. The Known
  Limitations sections get edited (see below); that's documentation
  correctness, not release-worthy.

### Why substitute BEFORE transplant

Same reasoning as v0.1.2 card embed. `transplant.transplant_ids`
matches blocks by `(type, block_text)` signature where `block_text`
is concatenated descendant text. A `date` inline node contributes 0
to that text (no `content`, no `text`). So a paragraph wrapping
`text("abc ") + date + text(" xyz")` has `block_text == "abc  xyz"`
(double-space where the date node sat).

The old sidecar doc already has the date node form (`block_text` =
`"abc  xyz"`). The fresh scratch doc from Heptabase's parser has
the placeholder as text inside the surrounding run
(`block_text == "abc [[date:2026-05-26]] xyz"` — different).

If we ran transplant before substituting, paragraph signatures would
diverge and block IDs on date-wrapping paragraphs would be lost.

## Regression safety

| Scenario | v0.1.3 | After this change |
|---|---|---|
| `hb doctor`, `init`, `tag *`, `unlink` | works | identical |
| `hb pull` of card with no date nodes | works | **byte-identical** (no code path touched for non-date nodes) |
| `hb pull` of card with date nodes | wrote `<!-- UNCONVERTED inline date -->` | writes `[[date:YYYY-MM-DD]]` (new behavior, fixed) |
| `hb push` body contains no `[[card:` and no `[[date:` | works | **byte-identical** (fast-path) |
| `hb push` body contains only `[[card:...]]` | works | identical (card substitute path unchanged) |
| `hb push` body contains `[[date:...]]` (round-trip) | silent date loss | **date preserved** (intended fix) |
| `hb push` body contains both `[[card:...]]` and `[[date:...]]` | card path worked, date lost | both preserved |
| `hb push` body contains `[[date:2026-13-99]]` | preserved as text (no match) | preserved as text (calendar validation rejects) |
| `hb push` body contains user-authored `[[date:2026-05-27]]` from scratch | preserved as text | **becomes date node (breaking)** — same shape as v0.1.2's card literal break |
| Already-pulled `.md` files with old `<!-- UNCONVERTED inline date -->` comment | date already lost on next push | still lost on next push (no auto-migration); user re-pulls to fix |
| Existing 88 unit + integration tests | green | green (verified post-implementation) |

The one explicit behavior change — literal `[[date:YYYY-MM-DD]]` text
becomes a date node — is inherent to the feature and called out in both
READMEs' Known Limitations.

## Edge cases (resolved)

| # | Case | Handling |
|---|---|---|
| 1.1 | Multiple `[[date:...]]` in one text node | regex `finditer`; emit interleaved sequence |
| 1.2 | Adjacent `[[date:A]][[date:B]]` | empty interstitial dropped |
| 1.3 | Date placeholder at text start / end / whole node | sequence omits empty segments |
| 1.4 | `[[date:not-a-uuid-shape]]` / `[[date:abc]]` / `[[date:2026/05/26]]` | regex miss → preserved as text |
| 1.5 | `[[date:2026-13-99]]` (regex passes, calendar invalid) | calendar validation rejects → preserved as text |
| 1.6 | `[[date:0001-01-01]]` / `[[date:9999-12-31]]` (extreme but valid) | accepted as date node |
| 1.7 | Inside `code` mark | text node skipped entirely |
| 1.8 | Inside `code_block` subtree | recursion stops at `code_block` |
| 1.9 | Inside `strong` / `em` / `link` marks | substitute; date carries no marks; surrounding segments keep marks |
| 1.10 | In heading / list / blockquote / table cell | substitute; Heptabase schema is source of truth |
| 1.11 | Date and card placeholder in same paragraph | both substitutes run; order does not matter (different regexes, disjoint matches) |
| 1.12 | Date and card placeholder in same text node | substitute_card runs first, splits the text node; substitute_date then runs on the remaining text segments |
| 1.13 | `to_markdown` on `{"type": "date"}` with no `attrs` | `attrs.date` empty → fallback to UNCONVERTED comment |
| 1.14 | `to_markdown` on `{"type": "date", "attrs": {"date": "2026-05-26T10:30"}}` (future Heptabase shape) | strict regex fails → fallback to UNCONVERTED comment, `unknown_nodes` records `date` |
| 1.15 | User authors `[[date:2026-05-27]]` in markdown from scratch | becomes date node (bonus emergent feature) |
| 1.16 | User edits existing `[[date:2026-05-26]]` to a different date | new date is what gets stored (bonus emergent feature) |
| 2.1 | `_push_create` fast-path now triggers on `[[date:` too | extra read+save when only dates are present; acceptable cost |
| 2.2 | `_push_create` substitute failure message | generalize wording to "placeholder substitution failed" |
| 2.3 | `_push_update` order matters | substitute before transplant (justified above) |
| 2.4 | Two deepcopies in sequence (card then date) | acceptable perf; not worth chaining |
| 3.1 | Pull-then-push round-trip with dates | works (the fix) |
| 3.2 | Sidecar / md5 / cache update | post-save `note_read` already refreshes; no change needed |
| 3.3 | Conflict detection via `--content-md5` | unaffected; substitution does not touch lock_md5 |
| 3.4 | Vault contains old `<!-- UNCONVERTED inline date -->` comments | no auto-migration; user re-pulls to refresh (documented) |
| 4.1 | Cards with no `[[date:` substring | no-op; byte-identical save payload (fast-path) |
| 4.2 | Existing tests for `to_markdown` date emission | audit grep `<!-- UNCONVERTED inline date -->` across tests/, update fixtures |
| 4.3 | Existing docs / SKILL.md / README that mention date as unsupported | update narrative; Known Limitations sections in both READMEs |

Known limitations (carry-forward, same as v0.1.2):

- Date placeholder split across adjacent text nodes
  (`[{text:"[[date:"}, {text:"2026-05-26]]"}]`) won't substitute.
  Heptabase's parser doesn't produce this in practice.
- Deeply nested docs (>1000 levels) hit Python recursion limit.
- `mention` inline nodes still emit
  `<!-- UNCONVERTED inline mention -->` and don't round-trip.

## Testing strategy

### Layer 0 — preflight (one-time, before any code change)

Manual script (see "Key assumption" above). Confirms
`[[date:YYYY-MM-DD]]` survives `heptabase note create` as plain text.
Must self-clean (`card_trash` the test card).

If preflight fails, **stop** — design needs revisiting.

### Layer 1 — `to_markdown` unit tests for date

`tests/test_pm2md.py` (extended). New tests:

- Single date node in paragraph → `[[date:YYYY-MM-DD]]` emitted
- Date with surrounding text → text + placeholder + text inline output
- Multiple dates in one paragraph
- Date in heading / list item / table cell
- Date node with missing / empty `attrs.date` → UNCONVERTED fallback,
  `unknown_nodes` records `date`
- Date node with non-`YYYY-MM-DD` `attrs.date` (e.g. ISO with time) →
  UNCONVERTED fallback
- Date node with calendar-invalid `attrs.date` (e.g. `2026-13-99`) →
  UNCONVERTED fallback (defense in depth — Heptabase shouldn't store
  these but we should not propagate them as round-trippable claims)

~6 tests.

### Layer 2 — `substitute_date_placeholders` unit tests

`tests/test_pm2md.py` (extended). New `TestSubstituteDatePlaceholders`
class. Mirrors `TestSubstituteCardPlaceholders`:

- Pure placeholder → single date node
- Prefix + placeholder + suffix split
- Placeholder at start / end / whole-node positions
- Multiple placeholders in one text node
- Adjacent placeholders (no separator)
- Invalid format variants (no-dash, wrong-length, partial, unclosed,
  whitespace inside) → preserved as text
- Calendar-invalid date (`2026-13-99`, `2026-02-30`) → preserved
- `code` mark text not substituted
- `code_block` subtree not substituted
- `strong` mark preserved on split segments; date carries no mark
- Paragraph `attrs.id` preserved
- Input not mutated
- Substitution in heading / list_item contexts

~12 tests.

### Layer 3 — Push integration tests

`tests/test_push_date_refs.py` (new, parallel to `test_push_card_refs.py`).
Mocks `htb.note_create` / `note_read` / `note_save`:

- `_push_create` fast-path: body with no `[[card:` and no `[[date:` →
  no extra read+save
- `_push_create` with only `[[date:...]]` body → substitution path
  triggers, saved payload contains date node
- `_push_create` with both `[[card:...]]` and `[[date:...]]` in one
  body → saved payload contains both card and date nodes
- `_push_create` substitution save failure → emits `create-failed`
  with generalized "placeholder substitution failed" detail
- `_push_update` placeholder in scratch PM → final save contains date
  node; surrounding paragraph keeps its block ID via transplant

~5 tests.

### Layer 4 — Manual TC against real Heptabase

Required (must pass before considering work shippable):

- **D1**: Pull Test 01 (`f20c620f-f442-4fc5-acf8-0d94c4d8391b`),
  confirm pulled .md contains `[[date:2026-05-26]]` (not the old
  comment). Edit unrelated text. Push. Re-read via
  `heptabase note read`; assert the date node is still present with
  the same `attrs.date`.
- **D2**: Create a brand-new .md containing
  `# title\n\nThe date is [[date:2026-12-25]].\n`. Push. Open in
  Heptabase; the date should render as a date inline node.

Optional:

- **D3**: Pull a card with no date nodes, edit, push → no behavior
  change (regression check on the fast-path).
- **D4**: Push a card containing `[[date:2026-13-99]]` (calendar
  invalid) → stays as text in Heptabase.
- **D5**: Push a card containing both card embed and date in the same
  paragraph → both render.

### Audit grep (one-time, pre-implementation)

```sh
grep -rn '<!-- UNCONVERTED inline date -->' tests/ skills/ docs/ \
  README.md README.zh.md INSTALL.md CLAUDE.md
# Any test fixture asserting the literal comment is the expected
# pull-time emission for a date node must update its expectation.

grep -rn '\[\[date:' tests/ skills/ docs/ README.md README.zh.md \
  INSTALL.md CLAUDE.md
# Any non-backticked literal placeholder in user-facing docs must be
# wrapped, same policy as v0.1.2 for [[card:.
```

### CI

Existing workflow runs `pytest tests/`. New test classes / files
auto-pick up. **No workflow changes.**

## Documentation updates

### `README.md` and `README.zh.md`

**Known Limitations section** — update the existing date bullet:

Before:

> - **`date` inline nodes don't round-trip.** They serialize as
>   `<!-- UNCONVERTED inline date -->` and pushing loses them.

After:

> - **Date inline nodes round-trip** via the `[[date:YYYY-MM-DD]]`
>   placeholder (same mechanism as card embeds). If you want a literal
>   `[[date:YYYY-MM-DD]]` string in your markdown, wrap it in backticks
>   (`` `[[date:2026-05-26]]` ``). Future Heptabase additions like
>   time-of-day or timezone are NOT yet supported — those would round-
>   trip as the old `<!-- UNCONVERTED inline date -->` comment until a
>   future placeholder revision.

(Equivalent Chinese wording in `README.zh.md`.)

**Card references round-trip subsection** (v0.1.2-added) — add a short
note that the same mechanism now also handles dates, with the date
placeholder shape called out.

**Migration note** (small addition to the Known Limitations section
or the Architecture subsection):

> Already-pulled `.md` files in your vault that contain
> `<!-- UNCONVERTED inline date -->` comments from prior versions will
> NOT auto-upgrade. Re-pull those cards (`hb pull <path>`) to refresh
> the markdown with the new placeholder syntax. If you push without
> re-pulling, the date is lost — the same behavior as the prior
> version.

**Changelog** — **no entry**. This work bundles with the upcoming
errors.md / release work; the bundled release will carry its own
Changelog entry covering both.

### `SKILL.md`

No changes. The "Verified against Heptabase CLI: 0.3.x" line stays.

### `.claude-plugin/plugin.json`

No version bump.

## Implementation order (high-level — detailed plan to follow)

1. **Preflight**: verify `[[date:YYYY-MM-DD]]` survives `note create`
   as plain text. Self-cleaning script. **Hard gate** — if it fails,
   stop and revisit design.
2. **Audit grep**: identify any test/doc that asserts the literal old
   `<!-- UNCONVERTED inline date -->` emission or unwrapped literal
   placeholder mentions.
3. **Refactor `_walk_substitute`** to accept a `splitter` argument;
   rename `_split_text_on_placeholder` → `_split_text_on_card`. Full
   test suite stays green (88 passed).
4. **TDD `to_markdown` date emission** with strict regex + calendar
   validation + UNCONVERTED fallback. Update any audit-identified
   fixtures.
5. **TDD `substitute_date_placeholders`** in `pm2md.py`. Mirror the
   `TestSubstituteCardPlaceholders` test shape.
6. **Wire** `_push_update` (substitute_date after substitute_card,
   before transplant).
7. **Wire** `_push_create` (extend fast-path gate; generalize error
   detail wording).
8. **TDD integration tests** in `tests/test_push_date_refs.py`.
9. **Update READMEs** Known Limitations + Card-references-round-trip
   subsection + migration note (both languages).
10. **Manual TC**: D1 (Test 01 round-trip) and D2 (new card with date).
11. **Stage for release**: leave uncommitted-or-committed-but-unreleased
    until the bundled errors.md release picks it up.

## Open questions resolved during this brainstorm

- Placeholder syntax → `[[date:YYYY-MM-DD]]` for consistency with
  `[[card:UUID]]` (Q1.A).
- Forward-compat for time/tz → **no**; strict YYYY-MM-DD only
  (Q2.A). Future Heptabase shape would need a separate placeholder
  revision.
- Defensive `to_markdown` fallback → **yes**. Strict regex + calendar
  validation on `attrs.date`; otherwise fall back to the existing
  UNCONVERTED comment.
- Defensive `substitute_date_placeholders` calendar validation →
  **yes**. Regex match plus `datetime.date.fromisoformat`.
- `_push_create` fast-path → extend with `or "[[date:" in body`; no
  dispatcher refactor.
- `_push_update` order → substitute before transplant; date after card
  (or before — no ordering dependency between the two substitutes).
- Internal refactor (`_walk_substitute` splitter parameter) → **yes**;
  cleaner than duplicating the walker.
- Release bundling → **no standalone release**; ships with errors.md
  work. No `plugin.json` bump, no Changelog entry.
- "Verified against" line → **no change**; stays at `0.3.x`.

## Open questions deferred to implementation

None. All decisions resolved in this spec.
