import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "v1", "skill", "scripts"))
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


if __name__ == "__main__":
    unittest.main()
