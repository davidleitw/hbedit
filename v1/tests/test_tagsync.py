import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "v1", "skill", "scripts"))
import tagsync


class TestMergeTags(unittest.TestCase):
    def test_design_example_keeps_remote_addition(self):
        # base [work], local +urgent, remote +q2
        to_add, to_remove, final = tagsync.merge_tags(
            ["work"], ["work", "urgent"], ["work", "q2"])
        self.assertEqual(to_add, ["urgent"])
        self.assertEqual(to_remove, [])
        self.assertEqual(final, ["q2", "urgent", "work"])

    def test_local_removal_is_applied(self):
        to_add, to_remove, final = tagsync.merge_tags(["a"], [], ["a"])
        self.assertEqual(to_remove, ["a"])
        self.assertEqual(final, [])

    def test_local_add_to_untagged_card(self):
        to_add, to_remove, final = tagsync.merge_tags([], ["x"], [])
        self.assertEqual(to_add, ["x"])
        self.assertEqual(final, ["x"])

    def test_remote_only_removal_is_not_re_added(self):
        # base=[a,b], local unchanged, remote dropped b -> b stays gone
        to_add, to_remove, final = tagsync.merge_tags(
            ["a", "b"], ["a", "b"], ["a"])
        self.assertEqual(to_add, [])
        self.assertEqual(final, ["a"])

    def test_concurrent_local_and_remote_add(self):
        # both sides added x -> no double-add
        to_add, to_remove, final = tagsync.merge_tags([], ["x"], ["x"])
        self.assertEqual(to_add, [])
        self.assertEqual(final, ["x"])


class TestFuzzy(unittest.TestCase):
    def test_typo_finds_similar(self):
        self.assertEqual(
            tagsync.find_similar_tag("Hbedit", ["hbedit", "work"]),
            "hbedit")

    def test_exact_match_is_not_ambiguous(self):
        self.assertIsNone(
            tagsync.find_similar_tag("hbedit", ["hbedit", "work"]))

    def test_genuinely_new_tag_has_no_match(self):
        self.assertIsNone(
            tagsync.find_similar_tag("quarterly", ["hbedit", "work"]))


if __name__ == "__main__":
    unittest.main()
