import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "skills", "hbedit", "scripts"))
import pm2md


def _num(text):
    return {"type": "numbered_list_item",
            "content": [{"type": "paragraph",
                         "content": [{"type": "text", "text": text}]}]}


def _para(text):
    return {"type": "paragraph",
            "content": [{"type": "text", "text": text}]}


class TestNumbering(unittest.TestCase):
    def test_consecutive_items_increment(self):
        doc = {"type": "doc", "content": [_num("a"), _num("b"), _num("c")]}
        md, _ = pm2md.to_markdown(doc)
        self.assertEqual(md, "1. a\n2. b\n3. c")

    def test_run_resets_after_non_numbered(self):
        doc = {"type": "doc", "content": [_num("a"), _para("x"), _num("b")]}
        md, _ = pm2md.to_markdown(doc)
        self.assertIn("1. a", md)
        self.assertIn("1. b", md)
        self.assertNotIn("2. b", md)


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


def _date_node(date_str):
    return {"type": "date", "attrs": {"date": date_str}}


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
        doc = {"type": "doc", "content": [
            {"type": "paragraph", "attrs": {"id": "p"}, "content": [
                {"type": "date", "attrs": {"date": "2026-05-26T10:30"}}]}]}
        md, conv = pm2md.to_markdown(doc)
        self.assertEqual(md, "<!-- UNCONVERTED inline date -->")
        self.assertIn("date", conv.unknown_nodes)

    def test_calendar_invalid_date_falls_back(self):
        doc = {"type": "doc", "content": [
            {"type": "paragraph", "attrs": {"id": "p"}, "content": [
                {"type": "date", "attrs": {"date": "2026-13-99"}}]}]}
        md, conv = pm2md.to_markdown(doc)
        self.assertEqual(md, "<!-- UNCONVERTED inline date -->")
        self.assertIn("date", conv.unknown_nodes)


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


if __name__ == "__main__":
    unittest.main()
