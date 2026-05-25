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


class TestPushCreateWithDatePlaceholder(unittest.TestCase):
    """_push_create: when body contains [[date:...]] (no [[card:),
    the fast-path gate triggers the intermediate read+save path and
    the saved payload contains a date node."""

    def test_date_only_triggers_substitute_and_save(self):
        with tempfile.TemporaryDirectory() as root:
            vaultlib.init_vault(root)
            rel = "a.md"
            abs_path = os.path.join(root, rel)
            with open(abs_path, "w") as f:
                f.write(f"# t\n\ntoday [[date:{_DATE_A}]] ok")

            from vault import find as vault_find
            info = vault_find(abs_path)
            vault, cd = info.root, info.cache_dir

            intermediate_pm = _scratch_pm_with_date_placeholder_text()
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
                                    f"# t\n\ntoday [[date:{_DATE_A}]] ok")

            self.assertEqual(len(saved_payloads), 1)
            card_id_arg, content, lock = saved_payloads[0]
            self.assertEqual(card_id_arg, "new-card-id")
            self.assertEqual(lock, "intermediate-md5")
            self.assertIn('"type": "date"', content)
            self.assertIn(_DATE_A, content)
            self.assertEqual(nr.call_count, 2)


class TestPushCreateWithBothPlaceholders(unittest.TestCase):
    """A body with both [[card:UUID]] and [[date:...]] in one paragraph
    must have both substitutions applied in the saved payload."""

    def test_both_placeholders_in_one_save(self):
        with tempfile.TemporaryDirectory() as root:
            vaultlib.init_vault(root)
            rel = "a.md"
            abs_path = os.path.join(root, rel)
            body = (f"# t\n\nsee [[card:{_UUID_C}]] on "
                    f"[[date:{_DATE_A}]]")
            with open(abs_path, "w") as f:
                f.write(body)

            from vault import find as vault_find
            info = vault_find(abs_path)
            vault, cd = info.root, info.cache_dir

            intermediate_pm = {
                "type": "doc",
                "content": [
                    {"type": "heading",
                     "attrs": {"id": "h", "level": 1},
                     "content": [{"type": "text", "text": "t"}]},
                    {"type": "paragraph",
                     "attrs": {"id": "p"},
                     "content": [{"type": "text",
                                  "text": (f"see [[card:{_UUID_C}]] on "
                                           f"[[date:{_DATE_A}]]")}]}
                ]
            }
            saved_payloads = []

            def fake_save(card_id_arg, content, content_md5):
                saved_payloads.append(content)
                return {"id": card_id_arg, "title": "t",
                        "contentMd5": "after-md5"}

            with mock.patch.object(hbedit.htb, "note_create",
                                   return_value={"id": "new-id",
                                                 "title": "t"}), \
                 mock.patch.object(hbedit.htb, "note_read",
                                   side_effect=[
                                       {"id": "new-id", "title": "t",
                                        "content": json.dumps(intermediate_pm),
                                        "contentMd5": "im-md5"},
                                       {"id": "new-id", "title": "t",
                                        "content": json.dumps(intermediate_pm),
                                        "contentMd5": "after-md5"},
                                   ]), \
                 mock.patch.object(hbedit.htb, "note_save",
                                   side_effect=fake_save):
                hbedit._push_create(vault, cd, rel, body)

            self.assertEqual(len(saved_payloads), 1)
            saved = saved_payloads[0]
            self.assertIn('"type": "card"', saved)
            self.assertIn('"type": "date"', saved)
            self.assertIn(_UUID_C, saved)
            self.assertIn(_DATE_A, saved)


class TestPushCreateNoPlaceholderFastPathStillHolds(unittest.TestCase):
    """Regression: body with no [[card: and no [[date: must not trigger
    an intermediate read+save (byte-identical to v0.1.1 / v0.1.2
    embed-free behavior)."""

    def test_no_extra_round_trip_when_no_placeholders(self):
        with tempfile.TemporaryDirectory() as root:
            vaultlib.init_vault(root)
            rel = "a.md"
            abs_path = os.path.join(root, rel)
            with open(abs_path, "w") as f:
                f.write("# plain\n\nno placeholders here")

            from vault import find as vault_find
            info = vault_find(abs_path)
            vault, cd = info.root, info.cache_dir

            with mock.patch.object(hbedit.htb, "note_create",
                                   return_value={"id": "new-card-id",
                                                 "title": "plain"}), \
                 mock.patch.object(hbedit.htb, "note_save") as ns, \
                 mock.patch.object(hbedit.htb, "note_read",
                                   return_value={
                                       "id": "new-card-id",
                                       "title": "plain",
                                       "content": json.dumps(
                                           {"type": "doc", "content": []}),
                                       "contentMd5": "deadbeef"
                                   }) as nr:
                hbedit._push_create(vault, cd, rel,
                                    "# plain\n\nno placeholders here")

            self.assertEqual(ns.call_count, 0)
            self.assertEqual(nr.call_count, 1)


class TestPushCreateSubstitutionFailureGeneralized(unittest.TestCase):
    """If the substitution save fails on a date-only body, the
    create-failed detail must use generalized 'placeholder' wording
    (not 'card-ref') and must mention the cardId."""

    def test_date_only_save_failure_reports_placeholder(self):
        with tempfile.TemporaryDirectory() as root:
            vaultlib.init_vault(root)
            rel = "a.md"
            abs_path = os.path.join(root, rel)
            with open(abs_path, "w") as f:
                f.write(f"# t\n\n[[date:{_DATE_A}]]")

            from vault import find as vault_find
            info = vault_find(abs_path)
            vault, cd = info.root, info.cache_dir

            intermediate_pm = _scratch_pm_with_date_placeholder_text()

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
                                              f"# t\n\n[[date:{_DATE_A}]]")

            self.assertEqual(rc, 2)
            obj = json.loads(out)
            self.assertEqual(obj["status"], "error")
            self.assertEqual(obj["code"], "create-failed")
            self.assertIn("placeholder", obj["detail"])
            self.assertNotIn("card-ref", obj["detail"])
            self.assertIn("new-card-id", obj["detail"])


if __name__ == "__main__":
    unittest.main()
