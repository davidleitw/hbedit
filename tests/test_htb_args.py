import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "skills", "hbedit", "scripts"))
import htb


class TestTagRemoveArgs(unittest.TestCase):
    def test_tag_remove_uses_tag_id(self):
        captured = []
        original = htb._run
        htb._run = lambda args: captured.append(args)
        try:
            htb.tag_remove("card-1", "tag-uuid-1")
        finally:
            htb._run = original
        self.assertEqual(
            captured[0],
            ["tag", "remove", "--card-id", "card-1", "--tag-id", "tag-uuid-1"])


if __name__ == "__main__":
    unittest.main()
