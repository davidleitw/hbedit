# Card-embed round-trip (v0.1.2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `[[card:UUID]]` placeholder round-trip losslessly through `hb push` so existing Heptabase card embeds survive pull → edit → push, and new embeds can be authored via the placeholder syntax.

**Architecture:** Add a pure function `substitute_card_placeholders(doc)` to `pm2md.py` that walks ProseMirror, replaces matching text nodes with `card` nodes (skipping `code`-marked text and `code_block` subtrees). Wire it into `_push_create` (gated on `"[[card:" in body` to preserve byte-identical behavior for embed-free pushes) and `_push_update` (in-memory, before `transplant.transplant_ids`). No `htb.py` changes, no new error codes — substitution failures borrow `create-failed` with descriptive `detail`.

**Tech Stack:** Python 3.9+ stdlib (re, copy, json, unittest). No new dependencies.

---

## File structure

| Path | Action | Responsibility |
|---|---|---|
| `skills/hbedit/scripts/pm2md.py` | Modify | Add `substitute_card_placeholders` pure function. Existing `to_markdown` untouched. |
| `skills/hbedit/scripts/hbedit.py` | Modify | Hook substitute into `_push_create` (fast-path-gated) and `_push_update` (in-memory, before transplant). |
| `tests/test_pm2md.py` | Modify | Add `TestSubstituteCardPlaceholders` class (~20 tests). |
| `tests/test_push_card_refs.py` | Create | Integration tests for push paths (~6 tests). |
| `README.md` | Modify | New "Card references round-trip" subsection under Architecture; update "Current limitations"; add v0.1.2 changelog entry. |
| `README.zh.md` | Modify | Same as above in Chinese. |
| `.claude-plugin/plugin.json` | Modify | Bump version 0.1.1 → 0.1.2. |

**Untouched (verify no diff at end):** `htb.py`, `transplant.py`, `vault.py`, `local_state.py`, `tagsync.py`, `errors.py`, all SOPs in `references/`, SKILL.md (CLAUDE.md gets a touch only via the spec doc reference, not in this PR).

---

## Pre-flight checks (must run before any task)

```bash
cd /Users/leiweicheng/Desktop/HeptaSync
python3 -m pytest tests/ -q          # baseline must be 63 passed
git status                            # working tree must be clean
git log --oneline -1                  # last commit: 56ae50d (spec) or 1a82be9 (v0.1.1)
```

If baseline isn't green, stop and investigate before touching code.

---

## Task 1: Audit grep + wrap unwrapped placeholders

**Files:**
- Audit: `tests/`, `skills/`, `docs/`, `README.md`, `README.zh.md`, `INSTALL.md`, `CLAUDE.md`
- Modify (if hits found): whichever doc/file contains an unwrapped `[[card:` literal

The new feature converts unwrapped `[[card:<UUID>]]` text into card embeds on push. Any existing doc/test that mentions the placeholder literally (e.g. when describing the syntax) must wrap it in backticks first, otherwise the documentation itself starts round-tripping into broken embeds when it's stored in Heptabase or pushed via hbedit.

- [ ] **Step 1: Run audit grep against the test tree**

Run: `grep -rn '\[\[card:' tests/`

Expected: **no output** (no existing test depends on prior behavior).

If there ARE hits: read each one, decide whether the test depends on the buggy "preserves as text" behavior. If yes, that test will need updating in the affected task. If it's just illustrative, wrap the literal in backticks within the test string.

- [ ] **Step 2: Run audit grep against docs / READMEs / SKILL.md**

Run: `grep -rn '\[\[card:' skills/ docs/ README.md README.zh.md INSTALL.md CLAUDE.md 2>/dev/null`

Expected: hits will likely include `docs/superpowers/specs/2026-05-25-card-embed-roundtrip-design.md` (the spec itself) — those are inside markdown code fences / inline code, fine.

Any hit OUTSIDE a backtick / fenced block in user-facing docs (README, INSTALL, SKILL.md) must be backtick-wrapped. Use `Edit` tool, one hit at a time.

- [ ] **Step 3: Verify the v0.1.0 backlog card on Heptabase**

Run: `heptabase note read b375e20a-f49e-47b6-8479-ada0bd11136a | grep -c '\[\[card:'`

Expected: `0`. If non-zero, the user's own backlog card contains placeholders that will start round-tripping into embeds — warn the user; they need to backtick-wrap or accept that those will become embeds (likely dangling refs).

- [ ] **Step 4: Commit audit fixes (only if Step 2 made edits)**

```bash
git add <only-files-edited-in-step-2>
git commit -m "docs: backtick-wrap [[card:UUID]] literals before v0.1.2"
```

If Step 2 made no edits, skip this commit.

---

## Task 2: Set up `TestSubstituteCardPlaceholders` test scaffolding + happy-path tests

**Files:**
- Modify: `tests/test_pm2md.py` (append new class + helpers)
- Test: `tests/test_pm2md.py`

Add a new test class with helper builders and the four most basic substitution tests. Implementation lands in Task 3.

- [ ] **Step 1: Add test helpers and the four basic happy-path tests**

Append to `tests/test_pm2md.py` (after the existing `TestNumbering` class, before `if __name__ == "__main__":`):

```python
# --- helpers for substitute_card_placeholders tests --------------------
_UUID_A = "25cac23e-d3fd-466d-8a6b-70721047ab9b"
_UUID_B = "f20c620f-f442-4fc5-acf8-0d94c4d8391b"


def _doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


def _txt(text, marks=None):
    node = {"type": "text", "text": text}
    if marks:
        node["marks"] = marks
    return node


def _para_with(*children):
    return {"type": "paragraph",
            "attrs": {"id": "para-id-fixed"},
            "content": list(children)}


def _card_node(card_id):
    return {"type": "card", "attrs": {"cardId": card_id}}


class TestSubstituteCardPlaceholders(unittest.TestCase):
    """Substitution of `[[card:UUID]]` text into ProseMirror `card` nodes.

    Pure function — every test should assert the output structure
    exactly, never modify the input."""

    def test_pure_placeholder_becomes_card(self):
        doc = _doc(_para_with(_txt(f"[[card:{_UUID_A}]]")))
        out = pm2md.substitute_card_placeholders(doc)
        self.assertEqual(
            out["content"][0]["content"],
            [_card_node(_UUID_A)])

    def test_prefix_placeholder_suffix_split(self):
        doc = _doc(_para_with(_txt(f"見 [[card:{_UUID_A}]] 那張")))
        out = pm2md.substitute_card_placeholders(doc)
        self.assertEqual(
            out["content"][0]["content"],
            [_txt("見 "), _card_node(_UUID_A), _txt(" 那張")])

    def test_placeholder_at_start(self):
        doc = _doc(_para_with(_txt(f"[[card:{_UUID_A}]] tail")))
        out = pm2md.substitute_card_placeholders(doc)
        self.assertEqual(
            out["content"][0]["content"],
            [_card_node(_UUID_A), _txt(" tail")])

    def test_placeholder_at_end(self):
        doc = _doc(_para_with(_txt(f"head [[card:{_UUID_A}]]")))
        out = pm2md.substitute_card_placeholders(doc)
        self.assertEqual(
            out["content"][0]["content"],
            [_txt("head "), _card_node(_UUID_A)])
```

- [ ] **Step 2: Run the new tests and verify they fail with `AttributeError`**

Run: `python3 -m pytest tests/test_pm2md.py::TestSubstituteCardPlaceholders -v 2>&1 | head -20`

Expected: 4 errors, each "AttributeError: module 'pm2md' has no attribute 'substitute_card_placeholders'".

This proves the tests exercise the right entry point before the function exists.

---

## Task 3: Implement minimal `substitute_card_placeholders` to pass Task 2 tests

**Files:**
- Modify: `skills/hbedit/scripts/pm2md.py`
- Test: `tests/test_pm2md.py::TestSubstituteCardPlaceholders`

Minimum implementation: regex, deep-copy input, DFS, text-node split. No protection logic yet — that comes in Task 4.

- [ ] **Step 1: Add the function to `pm2md.py`**

Find the end of `pm2md.py` (after `def to_markdown(doc):` and its body, near the bottom). Add at the end of the file:

```python
# ---------------------------------------------------------------------
# Card placeholder substitution: `[[card:UUID]]` text → `card` node
# ---------------------------------------------------------------------

import copy as _copy_module
import re as _re_module

_CARD_PLACEHOLDER_RE = _re_module.compile(
    r"\[\[card:([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
    r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\]\]"
)


def substitute_card_placeholders(doc):
    """Return a new ProseMirror doc with `[[card:<uuid>]]` text occurrences
    replaced by `card` nodes. The input is not mutated."""
    return _walk_substitute(_copy_module.deepcopy(doc))


def _walk_substitute(node):
    if not isinstance(node, dict):
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
    text = text_node.get("text", "")
    matches = list(_CARD_PLACEHOLDER_RE.finditer(text))
    if not matches:
        return [text_node]
    marks = text_node.get("marks")
    result = []
    cursor = 0
    for m in matches:
        start, end = m.span()
        if start > cursor:
            seg = {"type": "text", "text": text[cursor:start]}
            if marks:
                seg["marks"] = marks
            result.append(seg)
        result.append({"type": "card",
                       "attrs": {"cardId": m.group(1).lower()}})
        cursor = end
    if cursor < len(text):
        seg = {"type": "text", "text": text[cursor:]}
        if marks:
            seg["marks"] = marks
        result.append(seg)
    return result
```

- [ ] **Step 2: Run Task 2's four tests**

Run: `python3 -m pytest tests/test_pm2md.py::TestSubstituteCardPlaceholders -v 2>&1 | tail -10`

Expected: 4 passed.

- [ ] **Step 3: Run the full test suite**

Run: `python3 -m pytest tests/ -q 2>&1 | tail -5`

Expected: `67 passed` (63 baseline + 4 new).

- [ ] **Step 4: Commit**

```bash
git add skills/hbedit/scripts/pm2md.py tests/test_pm2md.py
git commit -m "feat(pm2md): substitute_card_placeholders basic split

DFS the ProseMirror doc; for each text node, regex-split on
[[card:<uuid>]] and emit interleaved text/card nodes. Input is
deep-copied on entry — pure function. No mark or code_block
protection yet (next commit)."
```

---

## Task 4: Multi-match and adjacency tests + verify implementation handles them

**Files:**
- Modify: `tests/test_pm2md.py::TestSubstituteCardPlaceholders` (append tests)

The current implementation should already handle these — Task 4 confirms via tests.

- [ ] **Step 1: Add four tests for multi-match / adjacency / boundary cases**

Append inside `TestSubstituteCardPlaceholders`:

```python
    def test_multiple_placeholders_in_one_text(self):
        doc = _doc(_para_with(_txt(
            f"見 [[card:{_UUID_A}]] 跟 [[card:{_UUID_B}]] 兩張")))
        out = pm2md.substitute_card_placeholders(doc)
        self.assertEqual(
            out["content"][0]["content"],
            [_txt("見 "), _card_node(_UUID_A),
             _txt(" 跟 "), _card_node(_UUID_B),
             _txt(" 兩張")])

    def test_adjacent_placeholders_no_space(self):
        doc = _doc(_para_with(_txt(
            f"[[card:{_UUID_A}]][[card:{_UUID_B}]]")))
        out = pm2md.substitute_card_placeholders(doc)
        self.assertEqual(
            out["content"][0]["content"],
            [_card_node(_UUID_A), _card_node(_UUID_B)])

    def test_uppercase_uuid_lowercased(self):
        upper = _UUID_A.upper()
        doc = _doc(_para_with(_txt(f"[[card:{upper}]]")))
        out = pm2md.substitute_card_placeholders(doc)
        # output cardId is lowercase canonical
        self.assertEqual(
            out["content"][0]["content"],
            [_card_node(_UUID_A)])

    def test_no_placeholder_returns_equivalent_doc(self):
        doc = _doc(_para_with(_txt("plain text, no placeholders")))
        out = pm2md.substitute_card_placeholders(doc)
        self.assertEqual(out, doc)
        # And it's NOT the same object (deepcopy contract)
        self.assertIsNot(out, doc)
        self.assertIsNot(out["content"][0], doc["content"][0])
```

- [ ] **Step 2: Run these tests**

Run: `python3 -m pytest tests/test_pm2md.py::TestSubstituteCardPlaceholders -v 2>&1 | tail -10`

Expected: 8 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_pm2md.py
git commit -m "test(pm2md): multi-match, adjacency, case, no-op cases"
```

---

## Task 5: UUID format strictness and unclosed/partial tests

**Files:**
- Modify: `tests/test_pm2md.py::TestSubstituteCardPlaceholders` (append tests)

Confirm the regex doesn't over-match. Implementation already enforces strict UUID v4 shape — these tests lock that in.

- [ ] **Step 1: Add tests for invalid placeholder variants**

Append inside `TestSubstituteCardPlaceholders`:

```python
    def test_invalid_uuid_kept_as_text(self):
        # Wrong format inside brackets
        doc = _doc(_para_with(_txt("[[card:not-a-uuid]]")))
        out = pm2md.substitute_card_placeholders(doc)
        self.assertEqual(
            out["content"][0]["content"],
            [_txt("[[card:not-a-uuid]]")])

    def test_short_uuid_kept_as_text(self):
        doc = _doc(_para_with(_txt("[[card:abc]]")))
        out = pm2md.substitute_card_placeholders(doc)
        self.assertEqual(
            out["content"][0]["content"],
            [_txt("[[card:abc]]")])

    def test_unclosed_placeholder_kept_as_text(self):
        doc = _doc(_para_with(_txt(f"[[card:{_UUID_A}")))
        out = pm2md.substitute_card_placeholders(doc)
        self.assertEqual(
            out["content"][0]["content"],
            [_txt(f"[[card:{_UUID_A}")])

    def test_whitespace_inside_placeholder_kept_as_text(self):
        doc = _doc(_para_with(_txt(f"[[card: {_UUID_A}]]")))
        out = pm2md.substitute_card_placeholders(doc)
        self.assertEqual(
            out["content"][0]["content"],
            [_txt(f"[[card: {_UUID_A}]]")])
```

- [ ] **Step 2: Run**

Run: `python3 -m pytest tests/test_pm2md.py::TestSubstituteCardPlaceholders -v 2>&1 | tail -10`

Expected: 12 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_pm2md.py
git commit -m "test(pm2md): invalid placeholder variants stay as text"
```

---

## Task 6: Code-mark and code-block protection — add tests + implement

**Files:**
- Modify: `tests/test_pm2md.py::TestSubstituteCardPlaceholders` (append tests)
- Modify: `skills/hbedit/scripts/pm2md.py` (add protection logic)

This is the only Task that needs new implementation beyond Task 3. Tests written first (TDD red), implementation written second (TDD green).

- [ ] **Step 1: Add protection tests (these will FAIL against current impl)**

Append inside `TestSubstituteCardPlaceholders`:

```python
    def test_code_mark_text_not_substituted(self):
        # Text with code mark stays as-is
        doc = _doc(_para_with(
            _txt(f"[[card:{_UUID_A}]]", marks=[{"type": "code"}])))
        out = pm2md.substitute_card_placeholders(doc)
        self.assertEqual(
            out["content"][0]["content"],
            [_txt(f"[[card:{_UUID_A}]]", marks=[{"type": "code"}])])

    def test_code_block_subtree_not_substituted(self):
        # text inside code_block stays as-is
        doc = _doc({
            "type": "code_block",
            "attrs": {"id": "cb", "params": "python"},
            "content": [_txt(f"[[card:{_UUID_A}]]")]
        })
        out = pm2md.substitute_card_placeholders(doc)
        self.assertEqual(
            out["content"][0]["content"],
            [_txt(f"[[card:{_UUID_A}]]")])

    def test_strong_mark_preserved_on_split_segments(self):
        # Text with strong (non-code) mark: substitute, segments keep mark,
        # card carries no mark.
        doc = _doc(_para_with(
            _txt(f"a [[card:{_UUID_A}]] b",
                 marks=[{"type": "strong"}])))
        out = pm2md.substitute_card_placeholders(doc)
        self.assertEqual(
            out["content"][0]["content"],
            [_txt("a ", marks=[{"type": "strong"}]),
             _card_node(_UUID_A),
             _txt(" b", marks=[{"type": "strong"}])])
```

- [ ] **Step 2: Run new tests and verify they FAIL**

Run: `python3 -m pytest tests/test_pm2md.py::TestSubstituteCardPlaceholders -v 2>&1 | tail -20`

Expected: 2 failures (`test_code_mark_text_not_substituted`, `test_code_block_subtree_not_substituted`); 1 passing (`test_strong_mark_preserved_on_split_segments` — already works via existing marks-pass-through).

If `test_strong_mark_preserved_on_split_segments` fails: investigate `_split_text_on_placeholder` mark handling — should already preserve marks on split segments.

- [ ] **Step 3: Update `_walk_substitute` and `_split_text_on_placeholder` in `pm2md.py`**

Find `_walk_substitute` and replace:

```python
def _walk_substitute(node):
    if not isinstance(node, dict):
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
```

With:

```python
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
```

Find `_split_text_on_placeholder` and add the code-mark guard at the top:

```python
def _split_text_on_placeholder(text_node):
    # Text with `code` mark is treated as opaque — never substitute.
    for mark in text_node.get("marks") or []:
        if mark.get("type") == "code":
            return [text_node]
    text = text_node.get("text", "")
    matches = list(_CARD_PLACEHOLDER_RE.finditer(text))
    if not matches:
        return [text_node]
    marks = text_node.get("marks")
    result = []
    cursor = 0
    for m in matches:
        start, end = m.span()
        if start > cursor:
            seg = {"type": "text", "text": text[cursor:start]}
            if marks:
                seg["marks"] = marks
            result.append(seg)
        result.append({"type": "card",
                       "attrs": {"cardId": m.group(1).lower()}})
        cursor = end
    if cursor < len(text):
        seg = {"type": "text", "text": text[cursor:]}
        if marks:
            seg["marks"] = marks
        result.append(seg)
    return result
```

- [ ] **Step 4: Run new tests, verify pass**

Run: `python3 -m pytest tests/test_pm2md.py::TestSubstituteCardPlaceholders -v 2>&1 | tail -10`

Expected: 15 passed.

- [ ] **Step 5: Run full suite**

Run: `python3 -m pytest tests/ -q 2>&1 | tail -5`

Expected: `78 passed`.

- [ ] **Step 6: Commit**

```bash
git add skills/hbedit/scripts/pm2md.py tests/test_pm2md.py
git commit -m "feat(pm2md): skip code marks and code_block subtrees

substitute_card_placeholders now protects two contexts: text nodes
with a 'code' mark, and any descendant of a 'code_block' node.
Strong/em/link marks on non-code text are preserved on split
segments; card nodes never inherit marks."
```

---

## Task 7: Structural invariant tests (paragraph id preservation, input non-mutation)

**Files:**
- Modify: `tests/test_pm2md.py::TestSubstituteCardPlaceholders` (append tests)

These pin down regression-safety contracts.

- [ ] **Step 1: Add invariant tests**

Append inside `TestSubstituteCardPlaceholders`:

```python
    def test_paragraph_attrs_id_preserved(self):
        doc = _doc(_para_with(_txt(f"[[card:{_UUID_A}]]")))
        out = pm2md.substitute_card_placeholders(doc)
        self.assertEqual(
            out["content"][0]["attrs"]["id"], "para-id-fixed")

    def test_input_not_mutated(self):
        import copy
        doc = _doc(_para_with(_txt(f"[[card:{_UUID_A}]]")))
        before = copy.deepcopy(doc)
        pm2md.substitute_card_placeholders(doc)
        # Input identical to its pre-call deep copy.
        self.assertEqual(doc, before)

    def test_substitution_in_heading(self):
        doc = _doc({
            "type": "heading",
            "attrs": {"id": "h1", "level": 2},
            "content": [_txt(f"前綴 [[card:{_UUID_A}]] 後綴")]
        })
        out = pm2md.substitute_card_placeholders(doc)
        self.assertEqual(
            out["content"][0]["content"],
            [_txt("前綴 "), _card_node(_UUID_A), _txt(" 後綴")])

    def test_substitution_in_list_item(self):
        doc = _doc({
            "type": "bullet_list_item",
            "content": [_para_with(_txt(f"見 [[card:{_UUID_A}]]"))]
        })
        out = pm2md.substitute_card_placeholders(doc)
        self.assertEqual(
            out["content"][0]["content"][0]["content"],
            [_txt("見 "), _card_node(_UUID_A)])

    def test_empty_doc_returns_equivalent(self):
        doc = {"type": "doc"}
        out = pm2md.substitute_card_placeholders(doc)
        self.assertEqual(out, {"type": "doc"})
```

- [ ] **Step 2: Run**

Run: `python3 -m pytest tests/test_pm2md.py::TestSubstituteCardPlaceholders -v 2>&1 | tail -10`

Expected: 20 passed.

- [ ] **Step 3: Run full suite**

Run: `python3 -m pytest tests/ -q 2>&1 | tail -5`

Expected: `83 passed`.

- [ ] **Step 4: Commit**

```bash
git add tests/test_pm2md.py
git commit -m "test(pm2md): structural invariants — id preservation, non-mutation, block contexts"
```

---

## Task 8: Integration tests scaffolding — create `test_push_card_refs.py`

**Files:**
- Create: `tests/test_push_card_refs.py`

Set up the file with imports, mock helpers, and two-test happy-path coverage for `_push_create` and `_push_update`. More tests follow in Task 9.

- [ ] **Step 1: Create the file with two integration tests**

Write to `tests/test_push_card_refs.py`:

```python
"""Integration tests for card-embed substitution in push paths.

Mocks the htb wrapper so we don't need a real Heptabase CLI; verifies
that substitute_card_placeholders is wired into _push_create and
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


_UUID_A = "25cac23e-d3fd-466d-8a6b-70721047ab9b"
_UUID_B = "f20c620f-f442-4fc5-acf8-0d94c4d8391b"


def _scratch_pm_with_placeholder_text():
    """ProseMirror as Heptabase's parser would return for a markdown
    body containing `[[card:_UUID_A]]` (the placeholder is text, no card
    node)."""
    return {
        "type": "doc",
        "content": [
            {"type": "heading",
             "attrs": {"id": "h-new", "level": 1},
             "content": [{"type": "text", "text": "Title"}]},
            {"type": "paragraph",
             "attrs": {"id": "p-new"},
             "content": [{"type": "text", "text": f"[[card:{_UUID_A}]]"}]}
        ]
    }


class TestPushCreateNoPlaceholderFastPath(unittest.TestCase):
    """When body has no `[[card:` substring, _push_create must not call
    note_read+note_save extras — byte-identical to v0.1.1 behavior."""

    def test_no_extra_round_trip(self):
        with tempfile.TemporaryDirectory() as root:
            vaultlib.init_vault(root)
            rel = "a.md"
            abs_path = os.path.join(root, rel)
            with open(abs_path, "w") as f:
                f.write("# plain\n\nno embed here")

            # State setup
            from vault import find as vault_find
            info = vault_find(abs_path)
            vault, cd = info.root, info.cache_dir

            # Mock htb
            with mock.patch.object(hbedit.htb, "note_create",
                                   return_value={"id": "new-card-id",
                                                 "title": "plain"}) as nc, \
                 mock.patch.object(hbedit.htb, "note_save") as ns, \
                 mock.patch.object(hbedit.htb, "note_read",
                                   return_value={
                                       "id": "new-card-id",
                                       "title": "plain",
                                       "content": json.dumps({"type":"doc","content":[]}),
                                       "contentMd5": "deadbeef"
                                   }) as nr:
                hbedit._push_create(vault, cd, rel,
                                    "# plain\n\nno embed here")

            # note_save must never be called in the fast path
            self.assertEqual(ns.call_count, 0)
            # note_read is called once (final sidecar refresh)
            self.assertEqual(nr.call_count, 1)


class TestPushUpdateNoPlaceholder(unittest.TestCase):
    """_push_update always calls substitute (no fast-path) — but with
    no placeholders, the substituted doc should structurally match the
    pre-substitute doc."""

    def test_no_placeholder_no_card_nodes_in_save(self):
        with tempfile.TemporaryDirectory() as root:
            vaultlib.init_vault(root)
            rel = "a.md"
            abs_path = os.path.join(root, rel)
            with open(abs_path, "w") as f:
                f.write("# plain\n\nedited body")

            from vault import find as vault_find
            info = vault_find(abs_path)
            vault, cd = info.root, info.cache_dir
            card_id = _UUID_A

            # Register binding and sidecar
            vaultlib.set_file_entry(vault, rel, card_id, [])
            sidecar_dir = os.path.join(cd, "sidecar")
            os.makedirs(sidecar_dir, exist_ok=True)
            old_doc = {"type": "doc", "content": [
                {"type": "heading",
                 "attrs": {"id": "h-old", "level": 1},
                 "content": [{"type": "text", "text": "plain"}]}]}
            with open(os.path.join(sidecar_dir, card_id + ".json"), "w") as f:
                json.dump(old_doc, f)
            local_state.set_local_entry(cd, rel,
                                        content_md5="lock-md5",
                                        local_md5="local-md5",
                                        synced_at="2026-05-25T00:00:00Z")

            scratch_pm = {"type": "doc", "content": [
                {"type": "heading",
                 "attrs": {"id": "h-new", "level": 1},
                 "content": [{"type": "text", "text": "plain"}]}]}
            saved_payloads = []

            def fake_save(card_id_arg, content, content_md5):
                saved_payloads.append(content)
                return {"id": card_id_arg, "title": "x",
                        "contentMd5": "new-md5"}

            with mock.patch.object(hbedit.htb, "note_create",
                                   return_value={"id": "scratch-id",
                                                 "title": "x"}), \
                 mock.patch.object(hbedit.htb, "note_read",
                                   side_effect=[
                                       {"id": "scratch-id",
                                        "title": "x",
                                        "content": json.dumps(scratch_pm),
                                        "contentMd5": "s"},
                                       {"id": card_id, "title": "x",
                                        "content": json.dumps(scratch_pm),
                                        "contentMd5": "new-md5"}
                                   ]), \
                 mock.patch.object(hbedit.htb, "note_save",
                                   side_effect=fake_save), \
                 mock.patch.object(hbedit.htb, "card_trash"):
                hbedit._push_update(vault, cd, rel,
                                    "# plain\n\nedited body", card_id)

            self.assertEqual(len(saved_payloads), 1)
            # The saved JSON must contain no `card` nodes
            self.assertNotIn('"type":"card"', saved_payloads[0])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the new file (tests will fail since wiring isn't done yet)**

Run: `python3 -m pytest tests/test_push_card_refs.py -v 2>&1 | tail -15`

Expected: 2 PASSED.

(Why pass? Because before any wiring, `_push_create` and `_push_update` already do roughly the right thing for the no-placeholder cases — substitute hasn't been added yet, but Task 8's tests are designed to assert behavior that the CURRENT code already satisfies. They lock down the "no regression" guarantee.)

If they fail, the current `_push_create` / `_push_update` flow disagrees with our model — investigate before proceeding.

- [ ] **Step 3: Commit**

```bash
git add tests/test_push_card_refs.py
git commit -m "test: push paths preserve no-placeholder behavior (baseline)"
```

---

## Task 9: Wire `substitute_card_placeholders` into `_push_update`

**Files:**
- Modify: `skills/hbedit/scripts/hbedit.py` (between `note_read(scratch.id)` and `transplant.transplant_ids`)
- Modify: `tests/test_push_card_refs.py` (add a test that exercises substitution)

In-memory substitution, no extra IO, no fast-path needed.

- [ ] **Step 1: Add a test that drives _push_update with a placeholder in the scratch PM**

Append to `tests/test_push_card_refs.py` before `if __name__ == "__main__":`:

```python
class TestPushUpdateWithPlaceholder(unittest.TestCase):
    """_push_update: when scratch PM contains [[card:UUID]] text, the
    final note_save payload must contain a card node, not text."""

    def test_placeholder_in_scratch_becomes_card_in_save(self):
        with tempfile.TemporaryDirectory() as root:
            vaultlib.init_vault(root)
            rel = "a.md"
            abs_path = os.path.join(root, rel)
            with open(abs_path, "w") as f:
                f.write(f"# t\n\n[[card:{_UUID_A}]]")

            from vault import find as vault_find
            info = vault_find(abs_path)
            vault, cd = info.root, info.cache_dir
            card_id = _UUID_B

            vaultlib.set_file_entry(vault, rel, card_id, [])
            sidecar_dir = os.path.join(cd, "sidecar")
            os.makedirs(sidecar_dir, exist_ok=True)
            old_doc = {"type": "doc", "content": [
                {"type": "heading",
                 "attrs": {"id": "h-old", "level": 1},
                 "content": [{"type": "text", "text": "t"}]},
                {"type": "paragraph",
                 "attrs": {"id": "p-old"},
                 "content": [{"type": "card",
                              "attrs": {"cardId": _UUID_A}}]}]}
            with open(os.path.join(sidecar_dir, card_id + ".json"), "w") as f:
                json.dump(old_doc, f)
            local_state.set_local_entry(cd, rel,
                                        content_md5="lock-md5",
                                        local_md5="local-md5",
                                        synced_at="2026-05-25T00:00:00Z")

            saved_payloads = []
            scratch_pm = _scratch_pm_with_placeholder_text()
            final_pm = copy.deepcopy(scratch_pm)
            # final remote PM after our save would contain card node;
            # we just need ANY valid JSON for the post-save read.
            final_pm["content"][1]["content"] = [
                {"type": "card", "attrs": {"cardId": _UUID_A}}]

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
                                    f"# t\n\n[[card:{_UUID_A}]]", card_id)

            self.assertEqual(len(saved_payloads), 1)
            payload = json.loads(saved_payloads[0])
            # Find the card node in the saved payload
            self.assertIn('"type":"card"', saved_payloads[0])
            # Paragraph wrapping the card has its id preserved by transplant
            # (since old paragraph had block_text "" and substituted-new
            # paragraph also has block_text "" — signatures match)
            wrapping_para = payload["content"][1]
            self.assertEqual(wrapping_para["type"], "paragraph")
            self.assertEqual(wrapping_para["content"][0],
                             {"type": "card",
                              "attrs": {"cardId": _UUID_A}})
            # The transplanted id should match the old paragraph id
            self.assertEqual(wrapping_para["attrs"]["id"], "p-old")
```

- [ ] **Step 2: Run the new test — verify it FAILS**

Run: `python3 -m pytest tests/test_push_card_refs.py::TestPushUpdateWithPlaceholder -v 2>&1 | tail -10`

Expected: FAIL — the saved payload contains the placeholder as text (no card node) because substitute isn't wired in yet.

- [ ] **Step 3: Wire the substitution call into `_push_update`**

Open `skills/hbedit/scripts/hbedit.py`. Find this block (around line 200-205):

```python
    try:
        scratch = htb.note_create(body)
        try:
            new_doc = json.loads(htb.note_read(scratch["id"])["content"])
            report = transplant.transplant_ids(old_doc, new_doc)
```

Replace it with:

```python
    try:
        scratch = htb.note_create(body)
        try:
            new_doc = json.loads(htb.note_read(scratch["id"])["content"])
            new_doc = pm2md.substitute_card_placeholders(new_doc)
            report = transplant.transplant_ids(old_doc, new_doc)
```

(One line added; substitute runs BEFORE transplant — critical for block-ID preservation across card-wrapping paragraphs.)

- [ ] **Step 4: Run the new test — verify it PASSES**

Run: `python3 -m pytest tests/test_push_card_refs.py::TestPushUpdateWithPlaceholder -v 2>&1 | tail -10`

Expected: PASS.

- [ ] **Step 5: Run full suite**

Run: `python3 -m pytest tests/ -q 2>&1 | tail -5`

Expected: `86 passed` (63 baseline + 20 substitute units + 2 integration baseline from Task 8 + 1 from this task).

- [ ] **Step 6: Commit**

```bash
git add skills/hbedit/scripts/hbedit.py tests/test_push_card_refs.py
git commit -m "feat(hbedit): substitute card placeholders in _push_update

In the scratch flow, run substitute_card_placeholders on the
ProseMirror returned by Heptabase's parser before transplant.
This preserves block IDs on paragraphs wrapping card embeds
(matching signatures: both old and new have block_text == '')."
```

---

## Task 10: Wire `substitute_card_placeholders` into `_push_create` (with fast-path)

**Files:**
- Modify: `skills/hbedit/scripts/hbedit.py` (`_push_create`)
- Modify: `tests/test_push_card_refs.py` (add tests for placeholder path + failure path)

`_push_create` gets the fast-path gate to keep byte-identical behavior for embed-free pushes.

- [ ] **Step 1: Add two tests — happy path with placeholder, and substitution save failure**

Append to `tests/test_push_card_refs.py` before `if __name__ == "__main__":`:

```python
class TestPushCreateWithPlaceholder(unittest.TestCase):
    """_push_create: when body contains [[card:UUID]], an intermediate
    read+save is performed to replace the placeholder with a card node."""

    def test_placeholder_triggers_substitute_and_save(self):
        with tempfile.TemporaryDirectory() as root:
            vaultlib.init_vault(root)
            rel = "a.md"
            abs_path = os.path.join(root, rel)
            with open(abs_path, "w") as f:
                f.write(f"# t\n\n[[card:{_UUID_A}]]")

            from vault import find as vault_find
            info = vault_find(abs_path)
            vault, cd = info.root, info.cache_dir

            intermediate_pm = _scratch_pm_with_placeholder_text()
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
                                    f"# t\n\n[[card:{_UUID_A}]]")

            # save was called once with the intermediate's md5 as lock
            self.assertEqual(len(saved_payloads), 1)
            card_id_arg, content, lock = saved_payloads[0]
            self.assertEqual(card_id_arg, "new-card-id")
            self.assertEqual(lock, "intermediate-md5")
            # saved payload contains a card node
            self.assertIn('"type":"card"', content)
            # note_read was called TWICE (intermediate + final-for-sidecar)
            self.assertEqual(nr.call_count, 2)


class TestPushCreateSubstitutionFailure(unittest.TestCase):
    """If the substitution save fails, emit create-failed with detail
    that mentions the card was created and substitution did not complete."""

    def test_save_failure_reports_create_failed(self):
        with tempfile.TemporaryDirectory() as root:
            vaultlib.init_vault(root)
            rel = "a.md"
            abs_path = os.path.join(root, rel)
            with open(abs_path, "w") as f:
                f.write(f"# t\n\n[[card:{_UUID_A}]]")

            from vault import find as vault_find
            info = vault_find(abs_path)
            vault, cd = info.root, info.cache_dir

            intermediate_pm = _scratch_pm_with_placeholder_text()

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
                                              f"# t\n\n[[card:{_UUID_A}]]")

            self.assertEqual(rc, 2)
            obj = json.loads(out)
            self.assertEqual(obj["status"], "error")
            self.assertEqual(obj["code"], "create-failed")
            self.assertIn("substitution", obj["detail"])
            self.assertIn("new-card-id", obj["detail"])
```

- [ ] **Step 2: Run new tests — verify FAILURES**

Run: `python3 -m pytest tests/test_push_card_refs.py::TestPushCreateWithPlaceholder tests/test_push_card_refs.py::TestPushCreateSubstitutionFailure -v 2>&1 | tail -15`

Expected: both FAIL — `_push_create` doesn't do the substitution path yet.

- [ ] **Step 3: Wire the substitution block into `_push_create`**

Open `skills/hbedit/scripts/hbedit.py`. Find `_push_create` (around line 148). Find this block (around line 158, right after `card_id = result["id"]`):

```python
    card_id = result["id"]
    try:
        vaultlib.set_file_entry(vault, rel_path, card_id, [])
```

Insert the substitution block between them:

```python
    card_id = result["id"]

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

    try:
        vaultlib.set_file_entry(vault, rel_path, card_id, [])
```

- [ ] **Step 4: Run new tests — verify PASS**

Run: `python3 -m pytest tests/test_push_card_refs.py::TestPushCreateWithPlaceholder tests/test_push_card_refs.py::TestPushCreateSubstitutionFailure -v 2>&1 | tail -10`

Expected: both PASS.

- [ ] **Step 5: Full suite**

Run: `python3 -m pytest tests/ -q 2>&1 | tail -5`

Expected: `88 passed` (86 from Task 9 + 2 new in this task).

- [ ] **Step 6: Commit**

```bash
git add skills/hbedit/scripts/hbedit.py tests/test_push_card_refs.py
git commit -m "feat(hbedit): substitute card placeholders in _push_create

Fast-path gated on '[[card:' substring presence in body — no-op
for embed-free pushes. When triggered: read fresh card content,
substitute placeholders, save back. On save failure: emit
create-failed with detail noting that the card exists but
substitution did not complete; user decides recovery."
```

---

## Task 11: Smoke-test the real CLI end-to-end

**Files:**
- No file changes — purely verification.

Run `hb` against real Heptabase to confirm the wiring doesn't break in practice.

- [ ] **Step 1: Run `hb doctor`**

Run: `/Users/leiweicheng/Desktop/HeptaSync/bin/hb doctor`

Expected: `{"command":"doctor","status":"ok","detail":"heptabase 0.3.0, desktop app reachable"}`

If status is "error": investigate before continuing. Manual TCs in Task 12 require a working CLI.

- [ ] **Step 2: Run the full pytest one more time**

Run: `python3 -m pytest tests/ -q 2>&1 | tail -5`

Expected: `88 passed`.

If any test fails: stop, fix the regression, re-run all tasks from the point of regression.

---

## Task 12: Manual TCs — coordinate with user

**Files:**
- No file changes — purely human-driven verification against real Heptabase.

The implementing engineer should ask the user to perform these (they require Heptabase desktop interaction). Required (must pass before tagging); optional (run if time allows). The engineer should pause and request the user run each one, observe the result, and confirm.

### Required:

- [ ] **TC-M1 — Round-trip an existing embed:**

  Ask user: "Pull a card you have in Heptabase that contains a card embed (any existing card with `[[card:...]]`-style content). Edit one unrelated piece of text in the local md. Push. Open the card in Heptabase. Does the original card embed still appear and link correctly?"

  Expected: yes.

- [ ] **TC-M5 — Create a new card with embed via placeholder:**

  Ask user: "Pick any existing card id from your Heptabase as the target. Create a new local .md file containing a `[[card:<that UUID>]]` line. Run `hb push <path>`. Open the resulting new card in Heptabase. Does the embed render and link to the target card?"

  Expected: yes.

- [ ] **TC-M6 — Regression: no behavior change for cards without embeds:**

  Ask user: "Pull a card that contains NO card embeds. Edit some text. Push. Compare the result in Heptabase against what you wrote — any difference beyond your intended edit (e.g. unexpected formatting changes, content shifts)?"

  Expected: no unexpected difference.

### Optional (run if time):

- [ ] **TC-M2** — Add a new `[[card:<existing UUID>]]` to a previously-embed-free tracked card → push → new embed appears.

- [ ] **TC-M3** — Backtick-wrap an existing placeholder in the md → push → embed becomes text in Heptabase (explicit opt-out works).

- [ ] **TC-M4** — Delete a placeholder line → push → embed gone.

- [ ] **TC-M7** — Push with `[[card:not-a-real-id]]` (invalid format) → stays as text in Heptabase.

- [ ] **TC-M8** — Push with `[[card:00000000-0000-0000-0000-000000000000]]` (valid format, nonexistent) → Heptabase shows dangling-ref placeholder.

If any required TC fails: stop. The implementation has a bug; do not proceed to release. Diagnose, file a follow-up subtask, and only proceed when all required TCs pass.

---

## Task 13: Update README.md

**Files:**
- Modify: `README.md`

Two locations:
1. New subsection under `## Architecture & how it works`.
2. Replacement in `## Current limitations`.

- [ ] **Step 1: Add the "Card references round-trip" subsection**

Open `README.md`. Find the `### Safety guarantees` heading (around line 187). The new subsection goes RIGHT BEFORE it, after the `### The block-ID transplant trick` section.

Insert:

```markdown
### Card references round-trip

Heptabase cards can embed other cards — a `card` node in the underlying
ProseMirror, rendered as an inline or block-level reference in the UI.
`pm2md` serializes such an embed as the placeholder string
`[[card:<UUID>]]` in markdown. On push, hbedit converts the placeholder
back into a real `card` node, but it can't do that through
`heptabase note create` alone: that CLI's markdown parser doesn't know
about `[[card:<UUID>]]` and would keep it as plain text.

Instead hbedit uses a two-step trick:

1. Let `heptabase note create` parse the markdown normally. The
   placeholder lands as plain text inside the resulting ProseMirror.
2. Read that ProseMirror back, walk it, replace each
   `[[card:<valid-uuid>]]` text occurrence with a real `card` node,
   and `heptabase note save` the modified ProseMirror.

Step 2 only runs when the source markdown contains the literal
substring `[[card:`. Cards without any embeds get the original
single-call path — no extra round-trips.

Two consequences worth knowing:

- **If you write `[[card:<UUID>]]` as literal text** (e.g. in
  documentation about hbedit itself), wrap it in backticks
  (`` `[[card:<UUID>]]` ``) or put it inside a fenced code block.
  Unwrapped, hbedit will convert it on push — and if the UUID isn't
  a real card, you'll end up with a dangling reference in Heptabase.
- **The placeholder syntax is case-insensitive** on the way in but
  lowercased before storage. `[[card:ABC...]]` works.

`date` inline nodes and `mention` nodes don't yet round-trip; pm2md
serializes them as `<!-- UNCONVERTED ... -->` markers and pushing back
loses them.
```

- [ ] **Step 2: Update the "Current limitations" section**

In the same file, find this bullet (around line 202):

```markdown
- **No card-to-card references from markdown.** Block references into
  other cards can't be expressed in plain markdown, so they can't round-trip.
```

Replace with:

```markdown
- **Card embed round-trip works since v0.1.2** via the `[[card:<UUID>]]`
  placeholder syntax (see "Card references round-trip" above). Block-level
  cross-card *block references* (pointing at a specific block inside
  another card) still don't round-trip — only whole-card embeds.
- **`date` inline nodes don't round-trip.** They serialize as
  `<!-- UNCONVERTED inline date -->` and pushing loses them.
```

- [ ] **Step 3: Add the v0.1.2 changelog entry**

Find the `## Changelog` heading. Add this new block immediately after the line `Versions follow [SemVer](https://semver.org). Newest first.` and BEFORE the existing `### v0.1.1 — 2026-05-25`:

```markdown
### v0.1.2 — 2026-05-25

- Card embeds (`card` nodes in ProseMirror) now round-trip through
  `hb push`. The placeholder `[[card:<UUID>]]` in markdown is
  converted back to a real card embed before the card is saved.
  Mechanism: post-process the ProseMirror that Heptabase's parser
  returns from `note create`, then `note save` the modified version.
  See **Architecture → Card references round-trip**.
- **Breaking** for anyone who relied on `[[card:<UUID>]]` being
  preserved as plain text on push: it now becomes a real card embed.
  Wrap such literal text in backticks (`` `[[card:<UUID>]]` ``) to
  keep it as text.
- No behavior change for cards without any `[[card:` substring in
  their markdown: the new code path is gated behind a string check
  and skipped entirely.
```

- [ ] **Step 4: Re-read README.md to catch any other stale references**

Run: `grep -n 'card-to-card\|round-trip\|card embed' README.md`

Look at each hit — any other place that still implies card embeds don't work? Fix inline. Common candidate: the `## What hbedit actually does` section may need a touch if it claims hbedit "doesn't support card refs".

---

## Task 14: Update README.zh.md

**Files:**
- Modify: `README.zh.md`

Same three edits as Task 13, in Chinese.

- [ ] **Step 1: Add the 「Card references round-trip」subsection in Chinese**

Find the `### 架構與運作` (or equivalent) section structure. Locate the position equivalent to README.md's insertion point (before `### Safety guarantees` / `### 安全保證`).

Insert:

```markdown
### Card 引用 round-trip

Heptabase 的卡片可以內嵌其他卡片 — 底層 ProseMirror 是一個 `card`
node,UI 上呈現為 inline 或 block-level 的卡片引用。`pm2md` 把這種
embed 序列化成 markdown 裡的 `[[card:<UUID>]]` placeholder。push 時
hbedit 要把它轉回真正的 `card` node,但**沒辦法**只靠
`heptabase note create` 達成:它的 markdown parser 不認識
`[[card:<UUID>]]`,會把它留成純文字。

hbedit 用兩步驟解決:

1. 讓 `heptabase note create` 照常 parse markdown,placeholder 會
   被當成純文字落到 ProseMirror 裡。
2. 把這份 ProseMirror 讀回來,DFS 走一遍,把每個
   `[[card:<valid-uuid>]]` text node 替換成真正的 `card` node,
   再用 `heptabase note save` 把改過的 ProseMirror 存回去。

第 2 步只在 markdown 包含字串 `[[card:` 時才跑。沒有 embed 的卡片
走原本的單次呼叫路徑,沒有額外 round-trip。

兩個要知道的影響:

- **如果你要在卡片裡寫純文字的 `[[card:<UUID>]]`**(例如寫 hbedit
  本身的說明文件),請用 backtick 包起來 `` `[[card:<UUID>]]` ``,
  或寫進 fenced code block。沒包的話 hbedit 會在 push 時把它變成
  真的 card embed,UUID 不存在就會變成 dangling reference。
- **placeholder 大小寫不敏感**,但會 normalize 成小寫存。
  `[[card:ABC...]]` 也可以。

`date` inline node 跟 `mention` node 目前還不能 round-trip,pm2md
序列化成 `<!-- UNCONVERTED ... -->`,push 回去會掉。
```

- [ ] **Step 2: Update the Chinese limitations section**

Find the bullet about no card-to-card references (around line 182, but exact line varies). Replace with:

```markdown
- **卡片內嵌 (card embed) round-trip 自 v0.1.2 起支援**,使用
  `[[card:<UUID>]]` placeholder 語法(見上方「Card 引用
  round-trip」)。針對特定 block 的 cross-card *block reference*
  仍然不能 round-trip — 只有整張卡片的 embed 可以。
- **`date` inline node 不能 round-trip**。會被序列化成
  `<!-- UNCONVERTED inline date -->`,push 回去會掉。
```

- [ ] **Step 3: Add the v0.1.2 changelog entry**

Insert after `版本依 [SemVer](https://semver.org) 命名,新版在上。` and before `### v0.1.1 — 2026-05-25`:

```markdown
### v0.1.2 — 2026-05-25

- Card embed(ProseMirror 裡的 `card` node)現在可以透過 `hb push`
  完整 round-trip。markdown 裡的 `[[card:<UUID>]]` placeholder 會
  在卡片儲存前被轉回真正的 card 引用。機制:讓 Heptabase 的 md
  parser 先 parse 一次,我們再 post-process 出來的 ProseMirror,
  最後 `note save` 改過的版本。詳見 **架構 → Card 引用 round-trip**。
- **Breaking** — 之前依賴「`[[card:<UUID>]]` 會被當純文字 push」
  這個行為的人,現在會變成真的 card embed。要保留純文字請改用
  backtick 包 (`` `[[card:<UUID>]]` ``)。
- 沒有 `[[card:` 字串的 markdown 行為 byte-for-byte 不變:fast-path
  字串檢查不通過就完全 skip 新邏輯。
```

- [ ] **Step 4: Verify with grep**

Run: `grep -n 'card.*round-trip\|card embed\|card 引用' README.zh.md`

Confirm no stale claims remain.

---

## Task 15: Bump plugin.json version

**Files:**
- Modify: `.claude-plugin/plugin.json`

- [ ] **Step 1: Bump version**

Open `.claude-plugin/plugin.json`. Change:

```json
  "version": "0.1.1",
```

To:

```json
  "version": "0.1.2",
```

- [ ] **Step 2: Verify no other version drift**

Run:
```bash
grep -H '"version"' .claude-plugin/plugin.json
grep -H "^### v0.1.2" README.md README.zh.md
```

Expected: plugin.json says 0.1.2; both READMEs have `### v0.1.2 — 2026-05-25` headers.

---

## Task 16: Final regression check + release commit

**Files:**
- Commit all changes.

Final verification before commit + tag.

- [ ] **Step 1: Full test suite**

Run: `python3 -m pytest tests/ -q 2>&1 | tail -5`

Expected: `88 passed`.

- [ ] **Step 2: Sweep for orphan symbols / inconsistencies**

Run:
```bash
echo "=== version consistency ==="
git diff master --stat | grep -E "plugin.json|README"
grep -H '"version"' .claude-plugin/plugin.json
echo "=== no stale 'cli-version' or old symbol references ==="
grep -rn 'cli-version-unsupported\|SUPPORTED_RANGE' skills/ tests/ docs/ README.md README.zh.md 2>/dev/null || echo "  (none — good)"
echo "=== Verified against still says 0.3.x ==="
grep "Verified against" skills/hbedit/SKILL.md
```

All should look consistent (version 0.1.2, no orphan refs, SKILL.md unchanged for verified version).

- [ ] **Step 3: Smoke-test the actual hb command one more time**

Run: `/Users/leiweicheng/Desktop/HeptaSync/bin/hb doctor`

Expected: ok status.

- [ ] **Step 4: Commit**

```bash
git add -A
git status   # review the diff list — should ONLY be the files in Task 1 list
git diff --stat
git commit -m "$(cat <<'EOF'
chore(release): v0.1.2

Card embeds in Heptabase cards now round-trip through hb push. The
[[card:UUID]] placeholder in markdown is converted back to a real
ProseMirror card node before saving — fixing the silent data loss
where pull → no-op edit → push was destroying existing card embeds.

Mechanism (see README: Architecture → Card references round-trip):
heptabase note create parses the markdown normally (placeholder
ends up as plain text); hbedit reads the resulting ProseMirror back,
runs substitute_card_placeholders to swap the placeholder text nodes
for card nodes, then heptabase note save commits the modified
ProseMirror. The substitution is gated on the literal substring
"[[card:" so cards without any embeds take the original code path
unchanged.

Code structure:
- pm2md.py: new pure function substitute_card_placeholders(doc).
  Protects text with code mark and code_block subtrees. UUID v4
  regex strict; non-matching variants left as text. Marks on
  surrounding text segments preserved; card nodes never inherit
  marks.
- hbedit.py _push_create: fast-path gated on "[[card:" in body;
  when triggered, intermediate read + substitute + save before
  set_file_entry. Save failure surfaces as create-failed with
  detail noting the card exists but substitution did not complete.
- hbedit.py _push_update: substitute runs in-memory before
  transplant.transplant_ids — order matters because transplant
  matches blocks by (type, plain_text) signature and a card node
  has 0 plain_text contribution; running substitute first keeps
  signatures of card-wrapping paragraphs aligned across old/new
  docs so block IDs transplant correctly.

Tests:
- tests/test_pm2md.py: 20 unit tests for substitute (basic splits,
  multi-match, adjacency, boundaries, UUID format/case, mark and
  code_block protection, structural invariants, block contexts).
- tests/test_push_card_refs.py: 6 integration tests for the wired
  push paths (fast-path no-op, placeholder triggers substitute+save,
  substitution save failure path, transplant ID preservation).
- Full suite: 88 passed.

Breaking change for users who relied on [[card:UUID]] being preserved
as plain text on push — it now becomes a real card embed. Wrap such
literals in backticks. Called out in both READMEs.
EOF
)"
```

- [ ] **Step 5: Tag**

```bash
git tag v0.1.2
git tag -l v0.1.2
```

- [ ] **Step 6: Verify before push**

```bash
git log --oneline -3
git rev-parse v0.1.2
git rev-parse HEAD
# v0.1.2 and HEAD should be the same commit hash
```

- [ ] **Step 7: Push branch + tag**

Ask the user to confirm push (release is shared-state). Show them the diff summary:

```bash
git diff origin/master --stat
```

Then on user confirmation:

```bash
git push origin master && git push origin v0.1.2
```

- [ ] **Step 8: Verify CI**

Wait for GitHub Actions to run (~3-5 min). Confirm `pytest tests/` green on both Linux and macOS × Python 3.9-3.13. If red, file a follow-up fix; do NOT delete the tag.

---

## Done

Tag `v0.1.2` shipped. Spec at `docs/superpowers/specs/2026-05-25-card-embed-roundtrip-design.md` describes the design; this plan describes the implementation. Manual TCs are recorded as part of Task 12.
