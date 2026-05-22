import os
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "v1", "skill", "scripts"))
import vault


class TestVaultDiscovery(unittest.TestCase):
    def test_find_vault_root_walks_up_to_hbedit_dir(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, ".hbedit"))
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


class TestVaultState(unittest.TestCase):
    def test_tag_base_round_trips(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, ".hbedit"))
            self.assertEqual(vault.get_tag_base(root, "CID-1"), [])
            vault.set_tag_base(root, "CID-1", ["work", "urgent"])
            self.assertEqual(
                sorted(vault.get_tag_base(root, "CID-1")), ["urgent", "work"])
            # a second card does not disturb the first
            vault.set_tag_base(root, "CID-2", ["q2"])
            self.assertEqual(
                sorted(vault.get_tag_base(root, "CID-1")), ["urgent", "work"])

    def test_set_tag_base_creates_state_dir_on_fresh_vault(self):
        with tempfile.TemporaryDirectory() as root:
            # no .hbedit/ pre-created — save_state must makedirs it
            vault.set_tag_base(root, "CID-1", ["a"])
            self.assertEqual(vault.get_tag_base(root, "CID-1"), ["a"])

    def test_load_state_recovers_from_corrupt_file(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, ".hbedit"))
            with open(os.path.join(root, ".hbedit", "state.json"),
                      "w", encoding="utf-8") as f:
                f.write("{not valid json")
            self.assertEqual(vault.get_tag_base(root, "CID-1"), [])


if __name__ == "__main__":
    unittest.main()
