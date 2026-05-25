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
            wrapping_para = payload["content"][1]
            self.assertEqual(wrapping_para["type"], "paragraph")
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
