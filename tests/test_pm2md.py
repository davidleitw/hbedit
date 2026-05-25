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


if __name__ == "__main__":
    unittest.main()
