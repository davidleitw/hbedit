# Follow-ups & known gaps

Last updated: 2026-05-26 (post v0.1.4)

Things that are NOT done, with enough context to pick up later. Each
entry says: what it is, why it wasn't done in the release that
exposed it, and what would trigger doing it.

Nothing in this file is blocking general usage of v0.1.4. Items are
ordered by likely priority for the next patch / minor release.

---

## 1. `remote-error` code missing from errors.md SOP

**What:** `hbedit.py:243` emits `errors.emit_error("push", "remote-error", ...)`
inside the `_push_update` catch-all path (when `htb.HtbError` is not
content-conflict, not card-not-found, but some other CLI failure).
This code is **not** documented in `skills/hbedit/references/errors.md`,
even though all other emitted codes are.

**Why it wasn't fixed in v0.1.4:** Pre-existing since v0.1.0 — not
introduced by date round-trip or by the new `create-failed` SOP. The
v0.1.4 spec deliberately scoped to date round-trip + the create-failed
SOP only; documenting an unrelated pre-existing gap would have widened
the release.

**When to do it:** Next patch release. Just write the SOP entry —
follow the shape of `create-failed` sub-case A (CLI error surfaced;
underlying cause must be addressed; no orphan to worry about since
the update path doesn't create new cards on its failure path).
Cross-reference `state.json` / sidecar do **not** mutate before the
save call in `_push_update`, so a `remote-error` leaves local state
unchanged — the SOP should make that explicit so agents know retry is
safe (unlike `create-failed` sub-case B).

**Audit grep to run when fixing:**
```
grep -n '"remote-error"' skills/hbedit/scripts/
grep -n '## remote-error' skills/hbedit/references/errors.md
```

---

## 2. `mention` inline node round-trip

**What:** Heptabase ProseMirror has a `mention` inline node type
(used for @-mentioning people / cards in some workflows). `pm2md`
currently emits `<!-- UNCONVERTED inline mention -->` for it, same
shape as the pre-v0.1.4 date handling. Push loses the mention.

**Why it wasn't fixed in v0.1.4:** Scope discipline — v0.1.4 spec
explicitly listed mention as a non-goal. The mechanism is identical
to card + date (placeholder + post-process), so adding mention is
mechanical, but we had not yet verified the underlying `mention`
node schema (what attrs it carries — `userId`? `cardId`? both?).
Without that empirical preflight, designing the placeholder would
have been speculative.

**When to do it:** v0.1.5 candidate. Repeat the v0.1.4 process:

1. **Preflight:** find a card in Heptabase that contains a mention.
   Read its ProseMirror via `heptabase note read <id>` and inspect
   the `mention` node structure. Decide a strict placeholder shape
   based on what fields actually exist.
2. **Spec + plan** in `docs/superpowers/`, mirroring
   `2026-05-26-date-inline-roundtrip-design.md` /
   `2026-05-26-date-inline-roundtrip.md`.
3. **Implementation** can reuse the existing `_walk_substitute(node,
   splitter)` walker as-is — add a third splitter `_split_text_on_mention`
   and a third `substitute_mention_placeholders` public function.
   Wire into `_push_create` / `_push_update` after the date substitute,
   extend the fast-path gate to `or "[[mention:" in body`.
4. **Manual TC** against a real mention-bearing card.

**Caveat:** Heptabase's mention node may reference user IDs that are
opaque to non-owners (mentions in shared cards) — if so, the
placeholder might need to ship as opaque-but-stable text rather than
something a user can author by hand. That's a design call, not a
mechanism question.

---

## 3. `date` node forward-compat for time / timezone

**What:** v0.1.4's date placeholder accepts only strict `YYYY-MM-DD`.
If Heptabase ever extends the `date` node schema to include time or
timezone (e.g. `attrs.date == "2026-05-26T10:30:00+08:00"`), pull
falls back to the existing `<!-- UNCONVERTED inline date -->`
comment — round-trip stops working for the extended shapes.

**Why it wasn't built now:** Heptabase 0.3.x does NOT carry these
fields. Designing a wider regex / parser for a shape we cannot
empirically observe would mean encoding strings Heptabase might not
accept on push, producing broken date nodes.

**When to do it:** If/when Heptabase ships a date-with-time variant.
Likely shape: introduce a separate `[[datetime:...]]` placeholder
(don't widen `[[date:...]]` — keeps the v0.1.4 contract
backward-compatible) with its own strict regex + ISO 8601 validation
via `datetime.fromisoformat`. Add a parallel
`substitute_datetime_placeholders` splitter.

**Trigger:** observe a real Heptabase card whose `date` node carries
time / timezone fields, OR official Heptabase release notes
announcing it.

---

## 4. `hb doctor` warning for stale UNCONVERTED-date comments

**What:** v0.1.4 ships with a migration note (in both READMEs): if
you have `.md` files in your vault pulled before v0.1.4, they
contain `<!-- UNCONVERTED inline date -->` rather than the new
placeholder. Pushing them loses the date silently — same as v0.1.3.
The fix is to re-pull (`hb pull <path>`).

**Gap:** Users won't know they need to re-pull unless they read the
changelog. `hb doctor` could grep tracked `.md` files for the old
comment and warn:

> Found N tracked files containing `<!-- UNCONVERTED inline date -->`
> (pre-v0.1.4 placeholder). Push will lose date nodes from these
> files. Run `hb pull <path>` for each to refresh.

**Why not in v0.1.4:** Pure ergonomics — not a correctness gap, and
the README + changelog already document it. `hb doctor` currently
only checks CLI reachability + app status; adding vault-scan
behavior would expand its scope. Wanted to ship the actual
round-trip first.

**When to do it:** Whenever someone reports "I upgraded and my dates
disappeared." If we get even one such report, prioritize this.

---

## 5. `.hbedit/state.json` schema migration policy

**What:** `state.json` carries a `schemaVersion` field; v3 is current.
The SOP `state-schema-unsupported` (in `errors.md`) tells agents to
ask the user before doing anything destructive — `.hbedit/` reset is
on the table but only with explicit user consent. v3 does NOT
auto-migrate from v2; CLAUDE.md release-discipline policy says this
stays unless a future version "explicitly takes on migration as a
feature."

**Observed friction:** During v0.1.4 manual TCs, the project's own
`.vault/.hbedit/state.json` was on a pre-v3 schema (no
`schemaVersion` field). The test agent correctly refused to touch it
and used a throwaway `.tcvault/` for testing. But this hints that
silent legacy vaults may exist in the wild.

**Why not in v0.1.4:** Schema migration as a feature is its own
spec — needs to decide forward-only vs. bidirectional, decide
whether to migrate sidecar layout, etc. Out of scope for date
round-trip.

**When to do it:** When a v0.1.x user reports being stuck on
`state-schema-unsupported`. Until then the SOP-driven manual
recovery is acceptable.

---

## 6. (Style) `hbedit.py` `_push_create` / `_push_update` are growing

**What:** Both functions now carry: the original create/save logic,
the v0.1.2 card substitute, the v0.1.4 date substitute, the
fast-path gate string check, the generalized error wording, and the
post-save sidecar refresh. They've grown from short procedures into
~40-line blocks each.

**Why not refactored now:** YAGNI. There are only two substitutes
today (card, date). If we add mention (item 2 above), the
inline-substitute block hits three. At that point it might be worth
extracting:

```python
def _apply_push_substitutes(doc):
    doc = pm2md.substitute_card_placeholders(doc)
    doc = pm2md.substitute_date_placeholders(doc)
    # doc = pm2md.substitute_mention_placeholders(doc)
    return doc
```

…and similarly a `_body_has_any_placeholder(body) -> bool` helper to
clean up the fast-path gate. Not worth it for two — refactoring two
into one helper is the kind of speculative abstraction CLAUDE.md
warns against.

**When to do it:** During the v0.1.5 mention work. Add the helper as
part of that spec, not as a standalone refactor PR.
