import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "v1", "skill", "scripts"))
import frontmatter


class TestV1Schema(unittest.TestCase):
    def test_build_note_meta_has_schema_version_not_title(self):
        rec = {"id": "abc", "title": "T", "contentMd5": "m"}
        meta = frontmatter.build_note_meta(
            rec, tags=["x"], synced_at="2026-01-01T00:00:00Z")
        hb = meta[frontmatter.MANAGED_KEY]
        self.assertEqual(hb["schemaVersion"], 1)
        self.assertNotIn("title", hb)
        self.assertEqual(hb["cardId"], "abc")
        self.assertEqual(hb["tags"], ["x"])
        self.assertEqual(hb["contentMd5"], "m")

    def test_round_trip_new_schema(self):
        src = ("---\n"
               "heptabase:\n"
               "  schemaVersion: 1\n"
               "  cardId: abc\n"
               "  type: note\n"
               "  tags:\n"
               "    - hbedit\n"
               "  contentMd5: m\n"
               "  syncedAt: 2026-01-01T00:00:00Z\n"
               "---\n"
               "# Title\n\nbody\n")
        meta, body = frontmatter.parse(src)
        self.assertEqual(meta["heptabase"]["schemaVersion"], 1)
        self.assertEqual(body, "# Title\n\nbody\n")
        meta2, body2 = frontmatter.parse(frontmatter.serialize(meta, body))
        self.assertEqual(meta, meta2)
        self.assertEqual(body, body2)


if __name__ == "__main__":
    unittest.main()
