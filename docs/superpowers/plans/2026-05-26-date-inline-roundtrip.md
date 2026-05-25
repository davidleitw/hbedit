# Date inline node round-trip (v0.1.4 candidate) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Heptabase `date` inline nodes (`{"type": "date", "attrs": {"date": "YYYY-MM-DD"}}`) round-trip losslessly through `hb pull` → edit → `hb push`. Pull emits a strict `[[date:YYYY-MM-DD]]` placeholder; push reverses it with `substitute_date_placeholders`. Defensive on both ends: invalid / non-strict shapes fall back to the existing `<!-- UNCONVERTED inline date -->` HTML comment so we never claim a round-trip we cannot honor.

**Architecture:** Bidirectional mirror of v0.1.2 card-embed mechanism. `pm2md.to_markdown` gains a `date`-typed branch in `_inline_node` that emits the placeholder only after strict-regex + `datetime.date.fromisoformat` validation. A new pure function `substitute_date_placeholders` (parallel to `substitute_card_placeholders`) post-processes the ProseMirror that `heptabase note create` returns on push. The shared `_walk_substitute` is refactored to accept a `splitter` parameter so both substitutions share the walker. Push wiring extends the v0.1.2 fast-path gate from `if "[[card:" in body:` to `if "[[card:" in body or "[[date:" in body:`, runs `substitute_card_placeholders` then `substitute_date_placeholders` (two deepcopies — acceptable cost for clarity).

**Tech Stack:** Python 3.9+ stdlib (re, copy, json, datetime, unittest). No new dependencies.

---

## File structure

| Path | Action | Responsibility |
|---|---|---|
| `skills/hbedit/scripts/pm2md.py` | Modify | Refactor `_walk_substitute` to accept `splitter`; rename `_split_text_on_placeholder` → `_split_text_on_card`; add `substitute_date_placeholders` + `_split_text_on_date` (with calendar validation); modify `Converter._inline_node` to emit `[[date:...]]` (with defensive fallback). |
| `skills/hbedit/scripts/hbedit.py` | Modify | Extend `_push_create` fast-path gate to include `"[[date:" in body`; generalize substitution-failure detail wording; add `substitute_date_placeholders` call in `_push_create` (post-substitute_card) and `_push_update` (post-substitute_card, pre-transplant). |
| `tests/test_pm2md.py` | Modify | Add `TestToMarkdownDate` class (~6 tests) and `TestSubstituteDatePlaceholders` class (~12 tests). |
| `tests/test_push_date_refs.py` | Create | Integration tests for date push paths (~5 tests). |
| `README.md` | Modify | Update Known Limitations date bullet to point at v0.1.4 syntax; amend the "Card references round-trip" subsection trailing paragraph to drop `date` from the unsupported list; add migration note about already-pulled comments. |
| `README.zh.md` | Modify | Same as above, in Chinese. |

**Untouched (verify no diff at end):** `htb.py`, `transplant.py`, `vault.py`, `local_state.py`, `tagsync.py`, `errors.py`, all SOPs in `skills/hbedit/references/`, `skills/hbedit/SKILL.md` (the "Verified against Heptabase CLI: 0.3.x" line MUST stay), `.claude-plugin/plugin.json` (no version bump), `INSTALL.md`, `CLAUDE.md`. No new Changelog entry in either README.

---

## Pre-flight checks (must run before any task)

```bash
cd /Users/leiweicheng/Desktop/HeptaSync
python3 -m pytest tests/ -q          # baseline: 88 passed
git status                            # working tree clean
git log --oneline -1                  # last commit: eab31fd (spec) or earlier
```

If baseline isn't 88 green, stop and investigate before touching code.

---

## Task 1: Empirical preflight — confirm `[[date:YYYY-MM-DD]]` survives `note create`

**Files:**
- No file changes — this is a one-shot verification.

The whole design assumes Heptabase's markdown parser preserves `[[date:YYYY-MM-DD]]` as plain text (analogous to how `[[card:UUID]]` survives, verified in v0.1.2). If this assumption fails, **stop and revisit the spec** — likely fallback to HTML-comment syntax. This is a hard gate.

- [ ] **Step 1: Write a self-cleaning preflight script and run it**

Run (a single shell pipeline; trashes the test card on the way out):

```bash
python3 - <<'PY'
import json, subprocess, sys, tempfile, os

md = "preflight\n\n[[date:2026-05-26]] tail\n"
with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
    f.write(md)
    md_path = f.name

try:
    create = json.loads(subprocess.check_output(
        ["heptabase", "note", "create", "-f", md_path]))
    card_id = create["id"]
    try:
        read = json.loads(subprocess.check_output(
            ["heptabase", "note", "read", card_id]))
        pm = json.loads(read["content"])

        # Walk and confirm: no `date` node anywhere; the literal
        # placeholder string is present in some text node.
        types_seen, joined_text = set(), []
        def walk(n):
            if isinstance(n, dict):
                t = n.get("type")
                if t: types_seen.add(t)
                if t == "text":
                    joined_text.append(n.get("text", ""))
                for v in n.values(): walk(v)
            elif isinstance(n, list):
                for x in n: walk(x)
        walk(pm)

        assert "date" not in types_seen, (
            "PREFLIGHT FAILED: Heptabase's parser produced a date node "
            "from [[date:...]] text. Types seen: %s. Design must be "
            "revisited (consider HTML-comment syntax)." % types_seen)
        joined = "".join(joined_text)
        assert "[[date:2026-05-26]]" in joined, (
            "PREFLIGHT FAILED: literal placeholder not found in text. "
            "Concatenated text: %r" % joined)
        print("PREFLIGHT OK: placeholder preserved as plain text. "
              "Types seen: %s" % sorted(types_seen))
    finally:
        subprocess.check_call(["heptabase", "card", "trash", card_id])
        print("Cleaned up test card %s" % card_id)
finally:
    os.unlink(md_path)
PY
```

Expected output ends with `PREFLIGHT OK: ...` and `Cleaned up test card ...`.

If the script prints `PREFLIGHT FAILED`: **stop**. Do NOT proceed. Report back to the user with the script output so the spec can be revised.

If `heptabase card trash` errors with "command not found", check whether the project's CLI wrapper uses a different subcommand (look at `htb.py` `card_trash`). Adjust the cleanup line and re-run.

- [ ] **Step 2: Note the preflight outcome — no commit needed**

This is a verification-only task. Nothing is committed. Note that preflight passed in the task tracking and proceed.

---

## Task 2: Audit grep — identify references to the old UNCONVERTED-date emission

**Files:**
- Audit: `tests/`, `skills/`, `docs/`, `README.md`, `README.zh.md`, `INSTALL.md`, `CLAUDE.md`

Any test fixture asserting `<!-- UNCONVERTED inline date -->` as expected output, or any user-facing doc that mentions an unwrapped literal `[[date:...]]` placeholder, will be affected by this change.

- [ ] **Step 1: Audit grep for old UNCONVERTED-date emission references**

Run:

```bash
grep -rn '<!-- UNCONVERTED inline date -->' tests/ skills/ docs/ \
  README.md README.zh.md INSTALL.md CLAUDE.md 2>/dev/null
```

Expected: hits will include the two READMEs (Known Limitations bullets — those are handled in Task 11) and possibly the spec doc itself (inside markdown code spans — fine). Any hit in `tests/` MUST be cataloged: that test fixture asserts the old behavior and will need updating in Task 4.

If `tests/` has hits, list them in a scratch note and update each fixture's expected string when Task 4 changes the `_inline_node` branch.

- [ ] **Step 2: Audit grep for unwrapped `[[date:` literals**

Run:

```bash
grep -rn '\[\[date:' tests/ skills/ docs/ README.md README.zh.md \
  INSTALL.md CLAUDE.md 2>/dev/null
```

Expected: hits will include the spec doc (`docs/superpowers/specs/2026-05-26-date-inline-roundtrip-design.md`) inside code fences / inline code — those are fine. Any hit in user-facing docs outside backticks must be backtick-wrapped before this PR lands, otherwise the doc itself round-trips into a broken date node when pushed via hbedit. Use `Edit` on each hit individually.

- [ ] **Step 3: Commit audit fixes (only if Step 2 made edits)**

```bash
git add <only-files-edited-in-step-2>
git commit -m "docs: backtick-wrap [[date:...]] literals before v0.1.4"
```

If Step 2 made no edits, skip this commit.

---

## Task 3: Internal refactor — parametrize `_walk_substitute`

**Files:**
- Modify: `skills/hbedit/scripts/pm2md.py`
- Test: existing `tests/test_pm2md.py` (no test changes; verifies green)

Refactor the v0.1.2 walker so both card and date substitutions share it. Pure internal change; `substitute_card_placeholders` public signature unchanged.

- [ ] **Step 1: Modify `pm2md.py` — parametrize walker and rename splitter**

Find this block at the bottom of `skills/hbedit/scripts/pm2md.py`:

```python
def substitute_card_placeholders(doc):
    """Return a new ProseMirror doc with `[[card:<uuid>]]` text occurrences
    replaced by `card` nodes. The input is not mutated."""
    return _walk_substitute(_copy_module.deepcopy(doc))


def _walk_substitute(node):
    if not isinstance(node, dict):
        return node
    # Do not descend into code_block subtrees.
    if node.get("type") == "code_block":
        return node
    children = node.get("content")
    if not children:
        return node
    new_children = []
    for child in children:
        if isinstance(child, dict) and child.get("type") == "text":
            new_children.extend(_split_text_on_placeholder(child))
        else:
            new_children.append(_walk_substitute(child))
    node["content"] = new_children
    return node


def _split_text_on_placeholder(text_node):
```

Replace with:

```python
def substitute_card_placeholders(doc):
    """Return a new ProseMirror doc with `[[card:<uuid>]]` text occurrences
    replaced by `card` nodes. The input is not mutated."""
    return _walk_substitute(_copy_module.deepcopy(doc), _split_text_on_card)


def _walk_substitute(node, splitter):
    if not isinstance(node, dict):
        return node
    # Do not descend into code_block subtrees.
    if node.get("type") == "code_block":
        return node
    children = node.get("content")
    if not children:
        return node
    new_children = []
    for child in children:
        if isinstance(child, dict) and child.get("type") == "text":
            new_children.extend(splitter(child))
        else:
            new_children.append(_walk_substitute(child, splitter))
    node["content"] = new_children
    return node


def _split_text_on_card(text_node):
```

(The third change is the function rename only — its body stays identical.)

- [ ] **Step 2: Run full suite to verify the refactor is contract-preserving**

Run: `python3 -m pytest tests/ -q 2>&1 | tail -3`

Expected: `88 passed`.

If any test fails: the refactor broke a private symbol some test reached into. Find the failing test, update its import / reference to use the new name `_split_text_on_card`, and re-run.

- [ ] **Step 3: Commit**

```bash
git add skills/hbedit/scripts/pm2md.py
git commit -m "refactor(pm2md): parametrize _walk_substitute with splitter

Rename _split_text_on_placeholder to _split_text_on_card and have
_walk_substitute take the splitter as an argument. Prep for adding
a date placeholder splitter without duplicating the walker. Public
API (substitute_card_placeholders) unchanged."
```

---

## Task 4: `to_markdown` date emission — strict regex + calendar validation + UNCONVERTED fallback

**Files:**
- Modify: `tests/test_pm2md.py` (append `TestToMarkdownDate` class)
- Modify: `skills/hbedit/scripts/pm2md.py` (`_inline_node`)

TDD: tests first, then implementation. Six fixtures cover happy path, surrounding context, multiple instances, missing/empty/non-strict/calendar-invalid `attrs.date` (all fall back to UNCONVERTED comment).

- [ ] **Step 1: Append test class to `tests/test_pm2md.py`**

Locate the file. Find the existing `TestSubstituteCardPlaceholders` class. Append the following AFTER its last test, BEFORE the `if __name__ == "__main__":` line at the bottom. Indent at the top level (peer to other test classes).

```python
class TestToMarkdownDate(unittest.TestCase):
    """to_markdown emits `[[date:YYYY-MM-DD]]` for valid date nodes and
    falls back to `<!-- UNCONVERTED inline date -->` when the date
    attribute is missing, malformed, or calendar-invalid."""

    def test_pure_date_emits_placeholder(self):
        doc = {"type": "doc", "content": [
            {"type": "paragraph", "attrs": {"id": "p"}, "content": [
                {"type": "date", "attrs": {"date": "2026-05-26"}}]}]}
        md, conv = pm2md.to_markdown(doc)
        self.assertEqual(md, "[[date:2026-05-26]]")
        self.assertNotIn("date", conv.unknown_nodes)

    def test_date_with_surrounding_text(self):
        doc = {"type": "doc", "content": [
            {"type": "paragraph", "attrs": {"id": "p"}, "content": [
                {"type": "text", "text": "today is "},
                {"type": "date", "attrs": {"date": "2026-05-26"}},
                {"type": "text", "text": " ok"}]}]}
        md, _ = pm2md.to_markdown(doc)
        self.assertEqual(md, "today is [[date:2026-05-26]] ok")

    def test_multiple_dates_in_paragraph(self):
        doc = {"type": "doc", "content": [
            {"type": "paragraph", "attrs": {"id": "p"}, "content": [
                {"type": "date", "attrs": {"date": "2026-05-26"}},
                {"type": "text", "text": " then "},
                {"type": "date", "attrs": {"date": "2026-12-25"}}]}]}
        md, _ = pm2md.to_markdown(doc)
        self.assertEqual(md,
            "[[date:2026-05-26]] then [[date:2026-12-25]]")

    def test_missing_date_attr_falls_back(self):
        doc = {"type": "doc", "content": [
            {"type": "paragraph", "attrs": {"id": "p"}, "content": [
                {"type": "date", "attrs": {}}]}]}
        md, conv = pm2md.to_markdown(doc)
        self.assertEqual(md, "<!-- UNCONVERTED inline date -->")
        self.assertIn("date", conv.unknown_nodes)

    def test_non_strict_date_falls_back(self):
        # Future Heptabase shape with time — strict regex rejects.
        doc = {"type": "doc", "content": [
            {"type": "paragraph", "attrs": {"id": "p"}, "content": [
                {"type": "date", "attrs": {"date": "2026-05-26T10:30"}}]}]}
        md, conv = pm2md.to_markdown(doc)
        self.assertEqual(md, "<!-- UNCONVERTED inline date -->")
        self.assertIn("date", conv.unknown_nodes)

    def test_calendar_invalid_date_falls_back(self):
        # Regex shape passes but calendar rejects.
        doc = {"type": "doc", "content": [
            {"type": "paragraph", "attrs": {"id": "p"}, "content": [
                {"type": "date", "attrs": {"date": "2026-13-99"}}]}]}
        md, conv = pm2md.to_markdown(doc)
        self.assertEqual(md, "<!-- UNCONVERTED inline date -->")
        self.assertIn("date", conv.unknown_nodes)
```

- [ ] **Step 2: Run the new tests — verify they FAIL**

Run: `python3 -m pytest tests/test_pm2md.py::TestToMarkdownDate -v 2>&1 | tail -15`

Expected: 6 failures. The current `_inline_node` falls through to the catch-all `<!-- UNCONVERTED inline date -->`, so:
- `test_pure_date_emits_placeholder`, `test_date_with_surrounding_text`, `test_multiple_dates_in_paragraph` FAIL (output is the UNCONVERTED comment, not the placeholder).
- `test_missing_date_attr_falls_back`, `test_non_strict_date_falls_back`, `test_calendar_invalid_date_falls_back` may pass accidentally (current behavior already falls back) — that's fine; they lock the invariant for the implementation step.

If all 6 PASS already, something is off — re-read the current `_inline_node`; you might have grabbed the wrong file.

- [ ] **Step 3: Modify `_inline_node` in `pm2md.py`**

Open `skills/hbedit/scripts/pm2md.py`. Find this block (around line 145-156):

```python
    def _inline_node(self, node):
        t = node.get("type")
        if t == "text":
            return self._apply_marks(node.get("text", ""), node.get("marks", []))
        if t == "card":
            return "[[card:" + node.get("attrs", {}).get("cardId", "?") + "]]"
        if t in ("hard_break", "br"):
            return "\n"
        if t == "math_inline":
            return "$" + self._plain(node.get("content", [])) + "$"
        self.unknown_nodes.add(t)
        return "<!-- UNCONVERTED inline " + str(t) + " -->"
```

Insert a `date` branch immediately after the `card` branch:

```python
    def _inline_node(self, node):
        t = node.get("type")
        if t == "text":
            return self._apply_marks(node.get("text", ""), node.get("marks", []))
        if t == "card":
            return "[[card:" + node.get("attrs", {}).get("cardId", "?") + "]]"
        if t == "date":
            raw = (node.get("attrs", {}).get("date") or "")
            if _STRICT_DATE_RE.fullmatch(raw):
                import datetime as _dt
                try:
                    _dt.date.fromisoformat(raw)
                    return "[[date:" + raw + "]]"
                except ValueError:
                    pass
            # Fall through to UNCONVERTED so we never claim a round-trip
            # we cannot honor.
            self.unknown_nodes.add("date")
            return "<!-- UNCONVERTED inline date -->"
        if t in ("hard_break", "br"):
            return "\n"
        if t == "math_inline":
            return "$" + self._plain(node.get("content", [])) + "$"
        self.unknown_nodes.add(t)
        return "<!-- UNCONVERTED inline " + str(t) + " -->"
```

Now find the existing `_CARD_PLACEHOLDER_RE` definition near the bottom of the file:

```python
_CARD_PLACEHOLDER_RE = _re_module.compile(
    r"\[\[card:([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
    r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\]\]"
)
```

Add the new regex constants RIGHT AFTER it (still at module top-level near the bottom of the file):

```python
_STRICT_DATE_RE = _re_module.compile(r"\d{4}-\d{2}-\d{2}")

_DATE_PLACEHOLDER_RE = _re_module.compile(
    r"\[\[date:(\d{4}-\d{2}-\d{2})\]\]"
)
```

(`_DATE_PLACEHOLDER_RE` is used by Task 5; defining both regexes together keeps related constants colocated.)

- [ ] **Step 4: Run the new tests — verify they PASS**

Run: `python3 -m pytest tests/test_pm2md.py::TestToMarkdownDate -v 2>&1 | tail -10`

Expected: 6 passed.

- [ ] **Step 5: Run full suite**

Run: `python3 -m pytest tests/ -q 2>&1 | tail -3`

Expected: `94 passed` (88 baseline + 6 new).

If any audit-identified tests from Task 2 fail because they asserted the old `<!-- UNCONVERTED inline date -->` emission for a valid date node, update their expected string to `[[date:YYYY-MM-DD]]` now (or to the UNCONVERTED comment if the test's date is intentionally invalid). Re-run.

- [ ] **Step 6: Commit**

```bash
git add skills/hbedit/scripts/pm2md.py tests/test_pm2md.py
git commit -m "feat(pm2md): emit [[date:YYYY-MM-DD]] placeholder on pull

to_markdown's _inline_node now handles date nodes with strict
YYYY-MM-DD regex + datetime.date.fromisoformat validation. Anything
else (missing attr, time-bearing shape, calendar-invalid) falls back
to the existing <!-- UNCONVERTED inline date --> comment — we never
claim round-trippability for a shape we cannot reverse. unknown_nodes
still records 'date' on the fallback path for diagnostic continuity."
```

---

## Task 5: `substitute_date_placeholders` — scaffolding + happy-path tests

**Files:**
- Modify: `tests/test_pm2md.py` (append `TestSubstituteDatePlaceholders` class)

Set up the test class with helpers (reusing `_doc`, `_txt`, `_para_with` from `TestSubstituteCardPlaceholders` if defined module-scope; otherwise define local equivalents) and four happy-path tests. Implementation lands in Task 6.

- [ ] **Step 1: Inspect existing helpers in `tests/test_pm2md.py`**

Run: `grep -n '^def _doc\|^def _txt\|^def _para_with\|^def _card_node' tests/test_pm2md.py`

If module-scope helpers (`_doc`, `_txt`, `_para_with`) exist (from v0.1.2): reuse. If they live inside `TestSubstituteCardPlaceholders` only, you'll need a `_date_node` helper at module scope alongside; add it next to wherever `_card_node` lives (likely module-scope).

- [ ] **Step 2: Add a `_date_node` helper**

Locate the module-scope `_card_node` helper in `tests/test_pm2md.py` (added in v0.1.2). Immediately after it, add:

```python
def _date_node(date_str):
    return {"type": "date", "attrs": {"date": date_str}}
```

- [ ] **Step 3: Append `TestSubstituteDatePlaceholders` class**

After `TestToMarkdownDate` (from Task 4), before `if __name__ == "__main__":`:

```python
_DATE_A = "2026-05-26"
_DATE_B = "2026-12-25"


class TestSubstituteDatePlaceholders(unittest.TestCase):
    """Substitution of `[[date:YYYY-MM-DD]]` text into ProseMirror
    `date` nodes. Pure function — assert structure exactly; never
    mutate input."""

    def test_pure_placeholder_becomes_date(self):
        doc = _doc(_para_with(_txt(f"[[date:{_DATE_A}]]")))
        out = pm2md.substitute_date_placeholders(doc)
        self.assertEqual(
            out["content"][0]["content"],
            [_date_node(_DATE_A)])

    def test_prefix_placeholder_suffix_split(self):
        doc = _doc(_para_with(_txt(f"today [[date:{_DATE_A}]] ok")))
        out = pm2md.substitute_date_placeholders(doc)
        self.assertEqual(
            out["content"][0]["content"],
            [_txt("today "), _date_node(_DATE_A), _txt(" ok")])

    def test_placeholder_at_start(self):
        doc = _doc(_para_with(_txt(f"[[date:{_DATE_A}]] tail")))
        out = pm2md.substitute_date_placeholders(doc)
        self.assertEqual(
            out["content"][0]["content"],
            [_date_node(_DATE_A), _txt(" tail")])

    def test_placeholder_at_end(self):
        doc = _doc(_para_with(_txt(f"head [[date:{_DATE_A}]]")))
        out = pm2md.substitute_date_placeholders(doc)
        self.assertEqual(
            out["content"][0]["content"],
            [_txt("head "), _date_node(_DATE_A)])
```

- [ ] **Step 4: Run the new tests — verify they fail with `AttributeError`**

Run: `python3 -m pytest tests/test_pm2md.py::TestSubstituteDatePlaceholders -v 2>&1 | tail -15`

Expected: 4 errors — each "AttributeError: module 'pm2md' has no attribute 'substitute_date_placeholders'".

---

## Task 6: Implement minimal `substitute_date_placeholders`

**Files:**
- Modify: `skills/hbedit/scripts/pm2md.py`
- Test: `tests/test_pm2md.py::TestSubstituteDatePlaceholders`

Minimum implementation: pure function, deep-copies input, reuses `_walk_substitute(doc, splitter)` from Task 3 with a new date splitter. No code/code_block protection yet — those land via tests in Task 8.

- [ ] **Step 1: Add the public function + splitter to `pm2md.py`**

Find the bottom of `skills/hbedit/scripts/pm2md.py` (right after `_split_text_on_card`). Append:

```python
def substitute_date_placeholders(doc):
    """Return a new ProseMirror doc with `[[date:<YYYY-MM-DD>]]` text
    occurrences replaced by `date` nodes. Only strict `YYYY-MM-DD`
    that also passes `datetime.date.fromisoformat` validation is
    substituted; anything else stays as text. The input is not mutated."""
    return _walk_substitute(_copy_module.deepcopy(doc), _split_text_on_date)


def _split_text_on_date(text_node):
    # Text with `code` mark is treated as opaque — never substitute.
    for mark in text_node.get("marks") or []:
        if mark.get("type") == "code":
            return [text_node]
    text = text_node.get("text", "")
    matches = list(_DATE_PLACEHOLDER_RE.finditer(text))
    if not matches:
        return [text_node]
    import datetime as _dt
    marks = text_node.get("marks")
    result = []
    cursor = 0
    for m in matches:
        raw = m.group(1)
        # Calendar validation: defend against shapes regex passes but
        # are not real dates (e.g. 2026-13-99). Failed matches stay as
        # part of the surrounding text run.
        try:
            _dt.date.fromisoformat(raw)
        except ValueError:
            continue
        start, end = m.span()
        if start > cursor:
            seg = {"type": "text", "text": text[cursor:start]}
            if marks:
                seg["marks"] = marks
            result.append(seg)
        result.append({"type": "date", "attrs": {"date": raw}})
        cursor = end
    if cursor == 0:
        # Every match was calendar-invalid → no substitution at all.
        return [text_node]
    if cursor < len(text):
        seg = {"type": "text", "text": text[cursor:]}
        if marks:
            seg["marks"] = marks
        result.append(seg)
    return result
```

- [ ] **Step 2: Run Task 5's four tests**

Run: `python3 -m pytest tests/test_pm2md.py::TestSubstituteDatePlaceholders -v 2>&1 | tail -10`

Expected: 4 passed.

- [ ] **Step 3: Run the full test suite**

Run: `python3 -m pytest tests/ -q 2>&1 | tail -3`

Expected: `98 passed` (94 from Task 4 + 4 new).

- [ ] **Step 4: Commit**

```bash
git add skills/hbedit/scripts/pm2md.py tests/test_pm2md.py
git commit -m "feat(pm2md): substitute_date_placeholders basic split

DFS the ProseMirror doc via the shared _walk_substitute; for each text
node, regex-split on [[date:YYYY-MM-DD]] (strict shape) and emit
interleaved text/date nodes. Calendar-validates each match via
datetime.date.fromisoformat; calendar-invalid matches stay as part
of the surrounding text run. Input is deep-copied on entry — pure
function. No code-mark / code_block protection yet (next commit)."
```

---

## Task 7: Multi-match, adjacency, invalid-format tests

**Files:**
- Modify: `tests/test_pm2md.py::TestSubstituteDatePlaceholders` (append tests)

The current implementation should already handle these via `finditer` + the calendar guard. Tests lock the behavior in.

- [ ] **Step 1: Append tests**

Inside `TestSubstituteDatePlaceholders`:

```python
    def test_multiple_placeholders_in_one_text(self):
        doc = _doc(_para_with(_txt(
            f"start [[date:{_DATE_A}]] mid [[date:{_DATE_B}]] end")))
        out = pm2md.substitute_date_placeholders(doc)
        self.assertEqual(
            out["content"][0]["content"],
            [_txt("start "), _date_node(_DATE_A),
             _txt(" mid "), _date_node(_DATE_B),
             _txt(" end")])

    def test_adjacent_placeholders_no_space(self):
        doc = _doc(_para_with(_txt(
            f"[[date:{_DATE_A}]][[date:{_DATE_B}]]")))
        out = pm2md.substitute_date_placeholders(doc)
        self.assertEqual(
            out["content"][0]["content"],
            [_date_node(_DATE_A), _date_node(_DATE_B)])

    def test_no_placeholder_returns_equivalent_doc(self):
        doc = _doc(_para_with(_txt("plain text, no dates")))
        out = pm2md.substitute_date_placeholders(doc)
        self.assertEqual(out, doc)
        self.assertIsNot(out, doc)

    def test_non_strict_format_kept_as_text(self):
        # Non-padded month, slash separator, year-only — none match
        # the strict regex.
        for raw in ("2026-5-26", "2026/05/26", "2026"):
            with self.subTest(raw=raw):
                doc = _doc(_para_with(_txt(f"[[date:{raw}]]")))
                out = pm2md.substitute_date_placeholders(doc)
                self.assertEqual(
                    out["content"][0]["content"],
                    [_txt(f"[[date:{raw}]]")])

    def test_unclosed_placeholder_kept_as_text(self):
        doc = _doc(_para_with(_txt(f"[[date:{_DATE_A}")))
        out = pm2md.substitute_date_placeholders(doc)
        self.assertEqual(
            out["content"][0]["content"],
            [_txt(f"[[date:{_DATE_A}")])

    def test_calendar_invalid_kept_as_text(self):
        # 2026-13-99: regex shape passes; calendar rejects.
        doc = _doc(_para_with(_txt("[[date:2026-13-99]]")))
        out = pm2md.substitute_date_placeholders(doc)
        self.assertEqual(
            out["content"][0]["content"],
            [_txt("[[date:2026-13-99]]")])

    def test_calendar_invalid_feb_30_kept_as_text(self):
        doc = _doc(_para_with(_txt("[[date:2026-02-30]]")))
        out = pm2md.substitute_date_placeholders(doc)
        self.assertEqual(
            out["content"][0]["content"],
            [_txt("[[date:2026-02-30]]")])
```

- [ ] **Step 2: Run**

Run: `python3 -m pytest tests/test_pm2md.py::TestSubstituteDatePlaceholders -v 2>&1 | tail -15`

Expected: 11 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_pm2md.py
git commit -m "test(pm2md): date placeholder multi-match, adjacency, invalid"
```

---

## Task 8: `code` / `code_block` protection + structural invariants

**Files:**
- Modify: `tests/test_pm2md.py::TestSubstituteDatePlaceholders` (append tests)

The `_walk_substitute` change in Task 3 already enforces `code_block` skip (the walker is shared). The `code`-mark guard is the first lines of `_split_text_on_date` from Task 6. Tests confirm both.

- [ ] **Step 1: Append protection + invariant tests**

Inside `TestSubstituteDatePlaceholders`:

```python
    def test_code_mark_text_not_substituted(self):
        doc = _doc(_para_with(
            _txt(f"[[date:{_DATE_A}]]", marks=[{"type": "code"}])))
        out = pm2md.substitute_date_placeholders(doc)
        self.assertEqual(
            out["content"][0]["content"],
            [_txt(f"[[date:{_DATE_A}]]", marks=[{"type": "code"}])])

    def test_code_block_subtree_not_substituted(self):
        doc = _doc({
            "type": "code_block",
            "attrs": {"id": "cb", "params": "python"},
            "content": [_txt(f"[[date:{_DATE_A}]]")]
        })
        out = pm2md.substitute_date_placeholders(doc)
        self.assertEqual(
            out["content"][0]["content"],
            [_txt(f"[[date:{_DATE_A}]]")])

    def test_strong_mark_preserved_on_split_segments(self):
        doc = _doc(_para_with(
            _txt(f"a [[date:{_DATE_A}]] b",
                 marks=[{"type": "strong"}])))
        out = pm2md.substitute_date_placeholders(doc)
        self.assertEqual(
            out["content"][0]["content"],
            [_txt("a ", marks=[{"type": "strong"}]),
             _date_node(_DATE_A),
             _txt(" b", marks=[{"type": "strong"}])])

    def test_paragraph_attrs_id_preserved(self):
        doc = _doc(_para_with(_txt(f"[[date:{_DATE_A}]]")))
        out = pm2md.substitute_date_placeholders(doc)
        self.assertEqual(
            out["content"][0]["attrs"]["id"], "para-id-fixed")

    def test_input_not_mutated(self):
        import copy
        doc = _doc(_para_with(_txt(f"[[date:{_DATE_A}]]")))
        before = copy.deepcopy(doc)
        pm2md.substitute_date_placeholders(doc)
        self.assertEqual(doc, before)

    def test_substitution_in_heading(self):
        doc = _doc({
            "type": "heading",
            "attrs": {"id": "h1", "level": 2},
            "content": [_txt(f"prefix [[date:{_DATE_A}]] suffix")]
        })
        out = pm2md.substitute_date_placeholders(doc)
        self.assertEqual(
            out["content"][0]["content"],
            [_txt("prefix "), _date_node(_DATE_A), _txt(" suffix")])
```

- [ ] **Step 2: Run new tests, verify pass**

Run: `python3 -m pytest tests/test_pm2md.py::TestSubstituteDatePlaceholders -v 2>&1 | tail -15`

Expected: 17 passed.

- [ ] **Step 3: Run full suite**

Run: `python3 -m pytest tests/ -q 2>&1 | tail -3`

Expected: `111 passed` (98 from Task 6 + 7 from Task 7 + 6 from this task).

- [ ] **Step 4: Commit**

```bash
git add tests/test_pm2md.py
git commit -m "test(pm2md): date placeholder protection + invariants

Code-mark text + code_block subtree skipped (inherited from shared
_walk_substitute). Strong mark preserved on split segments; date
node carries no marks. Paragraph attrs.id preserved across split;
input not mutated; substitution works in heading contexts."
```

---

## Task 9: Wire `substitute_date_placeholders` into `_push_update`

**Files:**
- Modify: `skills/hbedit/scripts/hbedit.py` (one-line insert after the v0.1.2 card substitute)
- Modify: `tests/test_push_date_refs.py` (create file with first integration test)

In-memory substitution, no extra IO, runs before `transplant.transplant_ids`.

- [ ] **Step 1: Create `tests/test_push_date_refs.py` with the first integration test**

Write to `tests/test_push_date_refs.py`:

```python
"""Integration tests for date-placeholder substitution in push paths.

Mocks the htb wrapper so a real Heptabase CLI is not required; verifies
that substitute_date_placeholders is wired into _push_create and
_push_update at the correct points and with the right inputs.
"""
import copy
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "skills", "hbedit", "scripts"))

import hbedit
import vault as vaultlib
import local_state


_DATE_A = "2026-05-26"
_DATE_B = "2026-12-25"
_UUID_C = "25cac23e-d3fd-466d-8a6b-70721047ab9b"


def _scratch_pm_with_date_placeholder_text():
    """ProseMirror as Heptabase's parser would return for a markdown
    body containing `[[date:2026-05-26]]` (the placeholder is text, no
    date node)."""
    return {
        "type": "doc",
        "content": [
            {"type": "heading",
             "attrs": {"id": "h-new", "level": 1},
             "content": [{"type": "text", "text": "Title"}]},
            {"type": "paragraph",
             "attrs": {"id": "p-new"},
             "content": [{"type": "text",
                          "text": f"today is [[date:{_DATE_A}]] ok"}]}
        ]
    }


class TestPushUpdateWithDatePlaceholder(unittest.TestCase):
    """_push_update: when scratch PM contains [[date:...]] text, the
    final note_save payload must contain a date node."""

    def test_placeholder_in_scratch_becomes_date_in_save(self):
        with tempfile.TemporaryDirectory() as root:
            vaultlib.init_vault(root)
            rel = "a.md"
            abs_path = os.path.join(root, rel)
            with open(abs_path, "w") as f:
                f.write(f"# t\n\ntoday is [[date:{_DATE_A}]] ok")

            from vault import find as vault_find
            info = vault_find(abs_path)
            vault, cd = info.root, info.cache_dir
            card_id = _UUID_C

            vaultlib.set_file_entry(vault, rel, card_id, [])
            sidecar_dir = os.path.join(cd, "sidecar")
            os.makedirs(sidecar_dir, exist_ok=True)
            old_doc = {"type": "doc", "content": [
                {"type": "heading",
                 "attrs": {"id": "h-old", "level": 1},
                 "content": [{"type": "text", "text": "t"}]},
                {"type": "paragraph",
                 "attrs": {"id": "p-old"},
                 "content": [
                     {"type": "text", "text": "today is "},
                     {"type": "date", "attrs": {"date": _DATE_A}},
                     {"type": "text", "text": " ok"}]}]}
            with open(os.path.join(sidecar_dir, card_id + ".json"), "w") as f:
                json.dump(old_doc, f)
            local_state.set_local_entry(cd, rel,
                                        content_md5="lock-md5",
                                        local_md5="local-md5",
                                        synced_at="2026-05-26T00:00:00Z")

            saved_payloads = []
            scratch_pm = _scratch_pm_with_date_placeholder_text()
            final_pm = copy.deepcopy(scratch_pm)
            # Post-save remote PM would have the date node; any valid
            # JSON suffices for the post-save read.
            final_pm["content"][1]["content"] = [
                {"type": "text", "text": "today is "},
                {"type": "date", "attrs": {"date": _DATE_A}},
                {"type": "text", "text": " ok"}]

            def fake_save(card_id_arg, content, content_md5):
                saved_payloads.append(content)
                return {"id": card_id_arg, "title": "t",
                        "contentMd5": "new-md5"}

            with mock.patch.object(hbedit.htb, "note_create",
                                   return_value={"id": "scratch-id",
                                                 "title": "t"}), \
                 mock.patch.object(hbedit.htb, "note_read",
                                   side_effect=[
                                       {"id": "scratch-id", "title": "t",
                                        "content": json.dumps(scratch_pm),
                                        "contentMd5": "s"},
                                       {"id": card_id, "title": "t",
                                        "content": json.dumps(final_pm),
                                        "contentMd5": "new-md5"}
                                   ]), \
                 mock.patch.object(hbedit.htb, "note_save",
                                   side_effect=fake_save), \
                 mock.patch.object(hbedit.htb, "card_trash"):
                hbedit._push_update(vault, cd, rel,
                                    f"# t\n\ntoday is [[date:{_DATE_A}]] ok",
                                    card_id)

            self.assertEqual(len(saved_payloads), 1)
            payload = json.loads(saved_payloads[0])
            # The wrapping paragraph must contain a date node now.
            wrapping_para = payload["content"][1]
            self.assertEqual(wrapping_para["type"], "paragraph")
            # Find the date node among children
            types = [c.get("type") for c in wrapping_para["content"]]
            self.assertIn("date", types)
            date_node = next(c for c in wrapping_para["content"]
                             if c.get("type") == "date")
            self.assertEqual(date_node["attrs"]["date"], _DATE_A)
            # Transplant should preserve the wrapping paragraph's id
            # since both old and new paragraphs have identical
            # block_text ("today is  ok") around the date.
            self.assertEqual(wrapping_para["attrs"]["id"], "p-old")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run new test — verify it FAILS**

Run: `python3 -m pytest tests/test_push_date_refs.py::TestPushUpdateWithDatePlaceholder -v 2>&1 | tail -15`

Expected: FAIL — saved payload contains `[[date:...]]` as text (substitute_date_placeholders isn't wired in yet).

- [ ] **Step 3: Wire substitute_date into `_push_update`**

Open `skills/hbedit/scripts/hbedit.py`. Find this block (around line 222-225):

```python
        try:
            new_doc = json.loads(htb.note_read(scratch["id"])["content"])
            new_doc = pm2md.substitute_card_placeholders(new_doc)
            report = transplant.transplant_ids(old_doc, new_doc)
```

Insert the new line:

```python
        try:
            new_doc = json.loads(htb.note_read(scratch["id"])["content"])
            new_doc = pm2md.substitute_card_placeholders(new_doc)
            new_doc = pm2md.substitute_date_placeholders(new_doc)
            report = transplant.transplant_ids(old_doc, new_doc)
```

Order: card before date (no real dependency between the two — different regexes match disjoint substrings — but keeping a canonical order makes review easier). Both must run BEFORE transplant.

- [ ] **Step 4: Run new test — verify it PASSES**

Run: `python3 -m pytest tests/test_push_date_refs.py::TestPushUpdateWithDatePlaceholder -v 2>&1 | tail -10`

Expected: PASS.

- [ ] **Step 5: Full suite**

Run: `python3 -m pytest tests/ -q 2>&1 | tail -3`

Expected: `112 passed` (111 from Task 8 + 1 new).

- [ ] **Step 6: Commit**

```bash
git add skills/hbedit/scripts/hbedit.py tests/test_push_date_refs.py
git commit -m "feat(hbedit): substitute date placeholders in _push_update

After substitute_card_placeholders, run substitute_date_placeholders
on the ProseMirror returned by Heptabase's parser before transplant.
date nodes contribute 0 to block_text (no descendants with text), so
running substitute first keeps signatures aligned with the sidecar
old_doc — block IDs on date-wrapping paragraphs are preserved."
```

---

## Task 10: Wire into `_push_create` — extend fast-path + generalize error wording

**Files:**
- Modify: `skills/hbedit/scripts/hbedit.py` (`_push_create`)
- Modify: `tests/test_push_date_refs.py` (add tests for date-only, combined, failure paths)

Extend the fast-path gate to trigger on either placeholder substring; run both substitutes; generalize the failure-detail string so it remains accurate when only dates were involved.

- [ ] **Step 1: Append three integration tests to `tests/test_push_date_refs.py`**

Insert before `if __name__ == "__main__":`:

```python
class TestPushCreateWithDatePlaceholder(unittest.TestCase):
    """_push_create: when body contains [[date:...]] (no [[card:),
    the fast-path gate triggers the intermediate read+save path and
    the saved payload contains a date node."""

    def test_date_only_triggers_substitute_and_save(self):
        with tempfile.TemporaryDirectory() as root:
            vaultlib.init_vault(root)
            rel = "a.md"
            abs_path = os.path.join(root, rel)
            with open(abs_path, "w") as f:
                f.write(f"# t\n\ntoday [[date:{_DATE_A}]] ok")

            from vault import find as vault_find
            info = vault_find(abs_path)
            vault, cd = info.root, info.cache_dir

            intermediate_pm = _scratch_pm_with_date_placeholder_text()
            saved_payloads = []

            def fake_save(card_id_arg, content, content_md5):
                saved_payloads.append((card_id_arg, content, content_md5))
                return {"id": card_id_arg, "title": "t",
                        "contentMd5": "after-save-md5"}

            with mock.patch.object(hbedit.htb, "note_create",
                                   return_value={"id": "new-card-id",
                                                 "title": "t"}), \
                 mock.patch.object(hbedit.htb, "note_read",
                                   side_effect=[
                                       {"id": "new-card-id", "title": "t",
                                        "content": json.dumps(intermediate_pm),
                                        "contentMd5": "intermediate-md5"},
                                       {"id": "new-card-id", "title": "t",
                                        "content": json.dumps(intermediate_pm),
                                        "contentMd5": "after-save-md5"},
                                   ]) as nr, \
                 mock.patch.object(hbedit.htb, "note_save",
                                   side_effect=fake_save) as ns:
                hbedit._push_create(vault, cd, rel,
                                    f"# t\n\ntoday [[date:{_DATE_A}]] ok")

            self.assertEqual(len(saved_payloads), 1)
            card_id_arg, content, lock = saved_payloads[0]
            self.assertEqual(card_id_arg, "new-card-id")
            self.assertEqual(lock, "intermediate-md5")
            self.assertIn('"type":"date"', content)
            self.assertIn(_DATE_A, content)
            self.assertEqual(nr.call_count, 2)


class TestPushCreateWithBothPlaceholders(unittest.TestCase):
    """A body with both [[card:UUID]] and [[date:...]] in one paragraph
    must have both substitutions applied in the saved payload."""

    def test_both_placeholders_in_one_save(self):
        with tempfile.TemporaryDirectory() as root:
            vaultlib.init_vault(root)
            rel = "a.md"
            abs_path = os.path.join(root, rel)
            body = (f"# t\n\nsee [[card:{_UUID_C}]] on "
                    f"[[date:{_DATE_A}]]")
            with open(abs_path, "w") as f:
                f.write(body)

            from vault import find as vault_find
            info = vault_find(abs_path)
            vault, cd = info.root, info.cache_dir

            intermediate_pm = {
                "type": "doc",
                "content": [
                    {"type": "heading",
                     "attrs": {"id": "h", "level": 1},
                     "content": [{"type": "text", "text": "t"}]},
                    {"type": "paragraph",
                     "attrs": {"id": "p"},
                     "content": [{"type": "text",
                                  "text": (f"see [[card:{_UUID_C}]] on "
                                           f"[[date:{_DATE_A}]]")}]}
                ]
            }
            saved_payloads = []

            def fake_save(card_id_arg, content, content_md5):
                saved_payloads.append(content)
                return {"id": card_id_arg, "title": "t",
                        "contentMd5": "after-md5"}

            with mock.patch.object(hbedit.htb, "note_create",
                                   return_value={"id": "new-id",
                                                 "title": "t"}), \
                 mock.patch.object(hbedit.htb, "note_read",
                                   side_effect=[
                                       {"id": "new-id", "title": "t",
                                        "content": json.dumps(intermediate_pm),
                                        "contentMd5": "im-md5"},
                                       {"id": "new-id", "title": "t",
                                        "content": json.dumps(intermediate_pm),
                                        "contentMd5": "after-md5"},
                                   ]), \
                 mock.patch.object(hbedit.htb, "note_save",
                                   side_effect=fake_save):
                hbedit._push_create(vault, cd, rel, body)

            self.assertEqual(len(saved_payloads), 1)
            saved = saved_payloads[0]
            self.assertIn('"type":"card"', saved)
            self.assertIn('"type":"date"', saved)
            self.assertIn(_UUID_C, saved)
            self.assertIn(_DATE_A, saved)


class TestPushCreateNoPlaceholderFastPathStillHolds(unittest.TestCase):
    """Regression: body with no [[card: and no [[date: must not trigger
    an intermediate read+save (byte-identical to v0.1.1 / v0.1.2
    embed-free behavior)."""

    def test_no_extra_round_trip_when_no_placeholders(self):
        with tempfile.TemporaryDirectory() as root:
            vaultlib.init_vault(root)
            rel = "a.md"
            abs_path = os.path.join(root, rel)
            with open(abs_path, "w") as f:
                f.write("# plain\n\nno placeholders here")

            from vault import find as vault_find
            info = vault_find(abs_path)
            vault, cd = info.root, info.cache_dir

            with mock.patch.object(hbedit.htb, "note_create",
                                   return_value={"id": "new-card-id",
                                                 "title": "plain"}), \
                 mock.patch.object(hbedit.htb, "note_save") as ns, \
                 mock.patch.object(hbedit.htb, "note_read",
                                   return_value={
                                       "id": "new-card-id",
                                       "title": "plain",
                                       "content": json.dumps(
                                           {"type": "doc", "content": []}),
                                       "contentMd5": "deadbeef"
                                   }) as nr:
                hbedit._push_create(vault, cd, rel,
                                    "# plain\n\nno placeholders here")

            self.assertEqual(ns.call_count, 0)
            self.assertEqual(nr.call_count, 1)


class TestPushCreateSubstitutionFailureGeneralized(unittest.TestCase):
    """If the substitution save fails on a date-only body, the
    create-failed detail must use generalized 'placeholder' wording
    (not 'card-ref') and must mention the cardId."""

    def test_date_only_save_failure_reports_placeholder(self):
        with tempfile.TemporaryDirectory() as root:
            vaultlib.init_vault(root)
            rel = "a.md"
            abs_path = os.path.join(root, rel)
            with open(abs_path, "w") as f:
                f.write(f"# t\n\n[[date:{_DATE_A}]]")

            from vault import find as vault_find
            info = vault_find(abs_path)
            vault, cd = info.root, info.cache_dir

            intermediate_pm = _scratch_pm_with_date_placeholder_text()

            with mock.patch.object(hbedit.htb, "note_create",
                                   return_value={"id": "new-card-id",
                                                 "title": "t"}), \
                 mock.patch.object(hbedit.htb, "note_read",
                                   return_value={
                                       "id": "new-card-id", "title": "t",
                                       "content": json.dumps(intermediate_pm),
                                       "contentMd5": "im"}), \
                 mock.patch.object(hbedit.htb, "note_save",
                                   side_effect=hbedit.htb.HtbError(
                                       "heptabase note save failed: boom")):
                out, rc = hbedit._push_create(vault, cd, rel,
                                              f"# t\n\n[[date:{_DATE_A}]]")

            self.assertEqual(rc, 2)
            obj = json.loads(out)
            self.assertEqual(obj["status"], "error")
            self.assertEqual(obj["code"], "create-failed")
            self.assertIn("placeholder", obj["detail"])
            self.assertNotIn("card-ref", obj["detail"])
            self.assertIn("new-card-id", obj["detail"])
```

- [ ] **Step 2: Run new tests — verify FAILURES**

Run: `python3 -m pytest tests/test_push_date_refs.py::TestPushCreateWithDatePlaceholder tests/test_push_date_refs.py::TestPushCreateWithBothPlaceholders tests/test_push_date_refs.py::TestPushCreateSubstitutionFailureGeneralized -v 2>&1 | tail -20`

Expected failures:
- `TestPushCreateWithDatePlaceholder.test_date_only_triggers_substitute_and_save`: FAIL — body has no `[[card:` so the v0.1.2 gate skips the substitute path entirely; `note_save` is never called.
- `TestPushCreateWithBothPlaceholders.test_both_placeholders_in_one_save`: FAIL — only card substitute runs; the date placeholder text remains in the saved payload.
- `TestPushCreateSubstitutionFailureGeneralized.test_date_only_save_failure_reports_placeholder`: FAIL — gate skips substitute path so failure path never triggers; AND even if it did, current detail says "card-ref".

`TestPushCreateNoPlaceholderFastPathStillHolds.test_no_extra_round_trip_when_no_placeholders` should already PASS (it asserts current behavior).

- [ ] **Step 3: Modify `_push_create` in `skills/hbedit/scripts/hbedit.py`**

Find this block (around lines 160-178):

```python
    # Fast-path: only re-process if the body contains the placeholder
    # syntax. Embed-free pushes are byte-identical to v0.1.1 behavior.
    if "[[card:" in body:
        try:
            intermediate = htb.note_read(card_id)
            new_doc = pm2md.substitute_card_placeholders(
                json.loads(intermediate["content"]))
            htb.note_save(card_id,
                          json.dumps(new_doc),
                          intermediate["contentMd5"])
        except htb.HtbUnexpectedResponse:
            raise
        except htb.HtbError as exc:
            return errors.emit_error(
                "push", "create-failed", path=rel_path,
                detail=("card created (id=%s) but card-ref substitution "
                        "failed: %s. The card exists on Heptabase with "
                        "placeholders unresolved."
                        % (card_id, htb.error_detail(exc)))), 2
```

Replace with:

```python
    # Fast-path: only re-process if the body contains a placeholder
    # syntax we substitute. Placeholder-free pushes are byte-identical
    # to v0.1.1 behavior.
    if "[[card:" in body or "[[date:" in body:
        try:
            intermediate = htb.note_read(card_id)
            new_doc = json.loads(intermediate["content"])
            new_doc = pm2md.substitute_card_placeholders(new_doc)
            new_doc = pm2md.substitute_date_placeholders(new_doc)
            htb.note_save(card_id,
                          json.dumps(new_doc),
                          intermediate["contentMd5"])
        except htb.HtbUnexpectedResponse:
            raise
        except htb.HtbError as exc:
            return errors.emit_error(
                "push", "create-failed", path=rel_path,
                detail=("card created (id=%s) but placeholder "
                        "substitution failed: %s. The card exists on "
                        "Heptabase with placeholders unresolved."
                        % (card_id, htb.error_detail(exc)))), 2
```

Changes:
1. Gate: `"[[card:" in body` → `"[[card:" in body or "[[date:" in body`
2. Both substitutes run (card first, then date — same order as `_push_update`).
3. Detail wording: "card-ref substitution failed" → "placeholder substitution failed".

- [ ] **Step 4: Run new tests — verify PASS**

Run: `python3 -m pytest tests/test_push_date_refs.py -v 2>&1 | tail -15`

Expected: 5 passed (4 new + the from-Task-9 update test).

- [ ] **Step 5: Full suite**

Run: `python3 -m pytest tests/ -q 2>&1 | tail -3`

Expected: `116 passed` (112 from Task 9 + 4 new — note the no-placeholder test was already passing implicitly through other coverage but is now part of explicit test count).

If the count comes out at `115` because `TestPushCreateNoPlaceholderFastPathStillHolds` was already counted in Task 9's import (it isn't — Task 9 created the file fresh, so by Task 10 the new test classes are 4 + the 1 Task 9 wrote), recount and reconcile by listing collected tests:

Run: `python3 -m pytest tests/test_push_date_refs.py --collect-only -q 2>&1 | tail -10`

Expected: 5 test methods listed.

- [ ] **Step 6: Commit**

```bash
git add skills/hbedit/scripts/hbedit.py tests/test_push_date_refs.py
git commit -m "feat(hbedit): substitute date placeholders in _push_create

Extend the v0.1.2 fast-path gate to trigger on either [[card: or
[[date: substring. Both substitutions run in canonical order
(card first, then date) on the same intermediate read. Failure
detail wording generalized from 'card-ref substitution failed' to
'placeholder substitution failed' so the message stays accurate
when only dates were involved."
```

---

## Task 11: README updates — Known Limitations + migration note

**Files:**
- Modify: `README.md` (Known Limitations bullet; round-trip-paragraph tail; new migration note)
- Modify: `README.zh.md` (mirror translations)

No version bump, no Changelog entry. This is documentation correctness only.

- [ ] **Step 1: Update `README.md` — round-trip section trailing paragraph**

Find this text (lines around 219-221):

```markdown
`date` inline nodes and `mention` nodes don't yet round-trip; pm2md
serializes them as `<!-- UNCONVERTED ... -->` markers and pushing back
loses them.
```

Replace with:

```markdown
`date` inline nodes round-trip via the same mechanism, using the
strict `[[date:YYYY-MM-DD]]` placeholder syntax (calendar-validated on
both ends; non-strict shapes such as time-bearing dates fall back to
`<!-- UNCONVERTED inline date -->` so the markdown never claims a
round-trip the tool cannot honor). `mention` nodes still don't
round-trip — they serialize as `<!-- UNCONVERTED inline mention -->`
and pushing loses them.

**Migrating older pulls:** `.md` files in your vault that still
contain `<!-- UNCONVERTED inline date -->` from a prior version do NOT
auto-upgrade. Re-pull the affected card (`hb pull <path>`) to refresh
the markdown with the new placeholder. If you push without re-pulling,
the date is lost — the same behavior as the prior version.
```

- [ ] **Step 2: Update `README.md` — Known Limitations bullet**

Find this bullet (lines around 242-243):

```markdown
- **`date` inline nodes don't round-trip.** They serialize as
  `<!-- UNCONVERTED inline date -->` and pushing loses them.
```

Replace with:

```markdown
- **Date inline nodes round-trip** via the `[[date:YYYY-MM-DD]]`
  placeholder syntax (same mechanism as card embeds; see "Card
  references round-trip" above). If you want literal
  `[[date:YYYY-MM-DD]]` text in your markdown, wrap it in backticks
  (`` `[[date:2026-05-26]]` ``). Future Heptabase additions such as
  time-of-day or timezone fall back to the `<!-- UNCONVERTED inline
  date -->` comment until a future placeholder revision adds support.
```

- [ ] **Step 3: Update `README.zh.md` — trailing paragraph**

Find this text (lines around 193-194):

```markdown
`date` inline node 跟 `mention` node 目前還不能 round-trip,pm2md
序列化成 `<!-- UNCONVERTED ... -->`,push 回去會掉。
```

Replace with:

```markdown
`date` inline node 透過同一個機制 round-trip,使用嚴格
`[[date:YYYY-MM-DD]]` placeholder 語法(兩端都會做行事曆驗證;非
嚴格格式例如帶時間的會 fall back 回 `<!-- UNCONVERTED inline date -->`,
markdown 不會假裝可以 round-trip 一個工具其實處理不了的形態)。
`mention` node 還是不能 round-trip,序列化成
`<!-- UNCONVERTED inline mention -->`,push 回去會掉。

**舊 pull 的遷移**:vault 裡仍含 `<!-- UNCONVERTED inline date -->`
的 `.md` 不會自動升級。請對那張卡片重新 `hb pull <path>`,markdown
才會更新成新 placeholder。沒重 pull 就 push 一樣會掉 date,行為跟舊版相同。
```

- [ ] **Step 4: Update `README.zh.md` — Known Limitations bullet**

Find this bullet (lines around 213-214):

```markdown
- **`date` inline node 不能 round-trip**。會被序列化成
  `<!-- UNCONVERTED inline date -->`,push 回去會掉。
```

Replace with:

```markdown
- **Date inline node round-trip 支援**,使用 `[[date:YYYY-MM-DD]]`
  placeholder 語法(機制跟 card embed 相同;見上方「Card 引用
  round-trip」)。如果要在 markdown 裡寫純文字的
  `[[date:YYYY-MM-DD]]`,用 backtick 包起來
  (`` `[[date:2026-05-26]]` ``)。Heptabase 未來如果加 time-of-day
  或 timezone,在未支援前會 fall back 回
  `<!-- UNCONVERTED inline date -->` 註解。
```

- [ ] **Step 5: Verify no other stale references**

Run:

```bash
grep -n "date.*round-trip\|UNCONVERTED.*date\|date.*UNCONVERTED" README.md README.zh.md
```

Expected: hits should all match the updated wording (no remaining "don't round-trip" claims for date).

- [ ] **Step 6: Commit**

```bash
git add README.md README.zh.md
git commit -m "docs: README known-limitations now lists date as round-trip

Both READMEs updated to reflect [[date:YYYY-MM-DD]] support and the
strict-format / calendar-validation policy. Added a migration note
about older pulls retaining the UNCONVERTED comment. No Changelog
entry, no version bump — bundles with the upcoming errors.md release."
```

---

## Task 12: Final regression check + smoke test

**Files:**
- No file changes — verification only.

Confirm test suite and CLI integration are healthy before manual TCs.

- [ ] **Step 1: Full test suite**

Run: `python3 -m pytest tests/ -q 2>&1 | tail -3`

Expected: `116 passed` (or whatever the cumulative target ended up being from Task 10; the exact number depends on collection from earlier tasks).

- [ ] **Step 2: Smoke `hb doctor`**

Run: `/Users/leiweicheng/Desktop/HeptaSync/bin/hb doctor`

Expected: `{"command":"doctor","status":"ok",...}` — `heptabase 0.3.x, desktop app reachable`.

If status is "error": investigate before doing manual TCs.

- [ ] **Step 3: Cross-check untouched files**

Run:

```bash
git status
git diff master --stat
```

Expected diff stat (cumulative across this PR):
- `skills/hbedit/scripts/pm2md.py` modified
- `skills/hbedit/scripts/hbedit.py` modified
- `tests/test_pm2md.py` modified
- `tests/test_push_date_refs.py` created
- `README.md` modified
- `README.zh.md` modified
- `docs/superpowers/specs/2026-05-26-date-inline-roundtrip-design.md` (committed earlier)
- `docs/superpowers/plans/2026-05-26-date-inline-roundtrip.md` (this plan)

NOT modified: `htb.py`, `transplant.py`, `vault.py`, `local_state.py`, `tagsync.py`, `errors.py`, anything in `skills/hbedit/references/`, `skills/hbedit/SKILL.md`, `.claude-plugin/plugin.json`, `INSTALL.md`, `CLAUDE.md`.

- [ ] **Step 4: Confirm SKILL.md "Verified against" line untouched**

Run: `grep "Verified against" skills/hbedit/SKILL.md`

Expected: line still says `Verified against Heptabase CLI: 0.3.x` (or whatever the current value is). MUST NOT have changed.

---

## Task 13: Manual TCs against real Heptabase

**Files:**
- No file changes — human verification only.

These require a working Heptabase desktop + CLI. The implementing engineer should pause and request the user perform each one.

### Required:

- [ ] **TC-D1 — Round-trip Test 01 (the empirical reference card)**

Ask user: "Pull card `f20c620f-f442-4fc5-acf8-0d94c4d8391b` (Test 01). Confirm the pulled .md contains `[[date:2026-05-26]]` somewhere (not the old UNCONVERTED comment). Edit one piece of unrelated text. Push. Then run `heptabase note read f20c620f-f442-4fc5-acf8-0d94c4d8391b` and confirm a `date` node with `attrs.date == "2026-05-26"` is still present in the ProseMirror."

Expected: yes.

- [ ] **TC-D2 — Author a new card with a date from scratch**

Ask user: "Create a new .md file containing `# Date test\n\nThe date is [[date:2026-12-25]].\n`. Run `hb push <path>`. Open the resulting card in Heptabase. Does the date render as a date inline node (not literal `[[date:2026-12-25]]` text)?"

Expected: yes.

### Optional (run if time):

- [ ] **TC-D3** — Pull a card containing zero date nodes. Edit some text. Push. Confirm no behavior change (regression check on the fast-path).

- [ ] **TC-D4** — Push a .md containing `[[date:2026-13-99]]` (calendar invalid) → stays as literal text in Heptabase.

- [ ] **TC-D5** — Push a .md containing both `[[card:<real UUID>]]` and `[[date:2026-05-26]]` in the same paragraph → both render correctly in Heptabase.

If any required TC fails: stop. Diagnose and file a follow-up subtask; do NOT consider the feature complete.

---

## Task 14: Stage for release (no release in this PR)

**Files:**
- No file changes.

Per the spec: this work does NOT ship on its own. It bundles with the upcoming errors.md / release work. So:

- [ ] **Step 1: Confirm NO release artifacts have been touched**

Run:

```bash
grep "0.1.3" .claude-plugin/plugin.json
grep "^### v0.1" README.md | head -3
grep "^### v0.1" README.zh.md | head -3
grep "Verified against" skills/hbedit/SKILL.md
```

Expected:
- `plugin.json`: still `"version": "0.1.3"`.
- READMEs: newest changelog entry is still `### v0.1.3 — ...` (no `### v0.1.4` added).
- SKILL.md: `Verified against` line unchanged.

If any of those drifted, undo the unintended change.

- [ ] **Step 2: Push commits to master (no tag)**

The work lives on `master` (per project convention — no feature branch). When user is ready:

```bash
git log --oneline -10   # review what landed
git push origin master
```

Do NOT create a tag. The bundled release work will tag a single `v0.1.4` (or whatever the merged release picks) when ready.

- [ ] **Step 3: Confirm CI**

Wait for GitHub Actions to run (~3-5 min). Confirm `pytest tests/` green on Linux and macOS × supported Python versions.

If red: file a follow-up fix; do NOT revert.

---

## Done

Date inline node round-trip is wired end-to-end. Spec at
`docs/superpowers/specs/2026-05-26-date-inline-roundtrip-design.md`,
plan here. Manual TCs in Task 13 recorded; release deferred to the
bundled errors.md work in Task 14.

---

## Self-review (writing-plans skill)

- **Spec coverage:** every section of the spec maps to a task:
  - Preflight (spec "Key assumption") → Task 1
  - `to_markdown` defensive emit → Task 4
  - `substitute_date_placeholders` → Tasks 5–8
  - Internal refactor (`_walk_substitute` parametrize) → Task 3
  - `_push_update` wiring → Task 9
  - `_push_create` wiring + error wording → Task 10
  - README Known Limitations + migration note → Task 11
  - Manual TC D1 (Test 01) + D2 (new card) → Task 13
  - No release / no version bump / SKILL.md unchanged → Task 14 verifies
- **Placeholder scan:** no TBD / TODO / "fill in" / "add appropriate".
  Each step has actual code.
- **Type / signature consistency:** `_walk_substitute(node, splitter)`,
  `_split_text_on_card`, `_split_text_on_date`, `substitute_card_placeholders`,
  `substitute_date_placeholders`, `_STRICT_DATE_RE`, `_DATE_PLACEHOLDER_RE` —
  same names used throughout. `_date_node(date_str)` helper consistent
  across test classes.
- **Test counts:** baseline 88 → after Task 4: 94 (+6) → Task 6: 98 (+4)
  → Task 7: 105 (+7) → Task 8: 111 (+6) → Task 9: 112 (+1) → Task 10: 116 (+4).
  Each step's expected count derives from the prior + the new tests it
  introduces.
- **Plan is artifact-clean:** all code blocks contain only what the
  engineer should paste; no warnings, no "use this version instead"
  fallbacks.
