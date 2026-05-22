import os
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "v1", "skill", "scripts"))
import vault


class TestVaultDiscovery(unittest.TestCase):
    def test_find_vault_root_walks_up_to_heptasync_dir(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, ".heptasync"))
            deep = os.path.join(root, "notes", "sub")
            os.makedirs(deep)
            f = os.path.join(deep, "x.md")
            open(f, "w").close()
            self.assertEqual(vault.find_vault_root(f), root)
            self.assertEqual(vault.find_vault_root(deep), root)

    def test_find_vault_root_returns_none_when_absent(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertIsNone(vault.find_vault_root(root))

    def test_find_file_by_card_id_matches_frontmatter(self):
        with tempfile.TemporaryDirectory() as root:
            notes = os.path.join(root, "notes", "deep")
            os.makedirs(notes)
            hit = os.path.join(notes, "a.md")
            with open(hit, "w", encoding="utf-8") as fh:
                fh.write("---\nheptabase:\n  cardId: CID-1\n---\n# a\n")
            miss = os.path.join(root, "notes", "b.md")
            with open(miss, "w", encoding="utf-8") as fh:
                fh.write("---\nheptabase:\n  cardId: CID-2\n---\n# b\n")
            self.assertEqual(vault.find_file_by_card_id(root, "CID-1"), hit)
            self.assertIsNone(vault.find_file_by_card_id(root, "CID-MISSING"))


if __name__ == "__main__":
    unittest.main()
