"""Integration tests for card-embed substitution in push paths.

Mocks the htb wrapper so we don't need a real Heptabase CLI; verifies
that substitute_card_placeholders is wired into _push_create and
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


_UUID_A = "25cac23e-d3fd-466d-8a6b-70721047ab9b"
_UUID_B = "f20c620f-f442-4fc5-acf8-0d94c4d8391b"


def _scratch_pm_with_placeholder_text():
    """ProseMirror as Heptabase's parser would return for a markdown
    body containing `[[card:_UUID_A]]` (the placeholder is text, no card
    node)."""
    return {
        "type": "doc",
        "content": [
            {"type": "heading",
             "attrs": {"id": "h-new", "level": 1},
             "content": [{"type": "text", "text": "Title"}]},
            {"type": "paragraph",
             "attrs": {"id": "p-new"},
             "content": [{"type": "text", "text": f"[[card:{_UUID_A}]]"}]}
        ]
    }


class TestPushCreateNoPlaceholderFastPath(unittest.TestCase):
    """When body has no `[[card:` substring, _push_create must not call
    note_read+note_save extras — byte-identical to v0.1.1 behavior."""

    def test_no_extra_round_trip(self):
        with tempfile.TemporaryDirectory() as root:
            vaultlib.init_vault(root)
            rel = "a.md"
            abs_path = os.path.join(root, rel)
            with open(abs_path, "w") as f:
                f.write("# plain\n\nno embed here")

            # State setup
            from vault import find as vault_find
            info = vault_find(abs_path)
            vault, cd = info.root, info.cache_dir

            # Mock htb
            with mock.patch.object(hbedit.htb, "note_create",
                                   return_value={"id": "new-card-id",
                                                 "title": "plain"}) as nc, \
                 mock.patch.object(hbedit.htb, "note_save") as ns, \
                 mock.patch.object(hbedit.htb, "note_read",
                                   return_value={
                                       "id": "new-card-id",
                                       "title": "plain",
                                       "content": json.dumps({"type":"doc","content":[]}),
                                       "contentMd5": "deadbeef"
                                   }) as nr:
                hbedit._push_create(vault, cd, rel,
                                    "# plain\n\nno embed here")

            # note_save must never be called in the fast path
            self.assertEqual(ns.call_count, 0)
            # note_read is called once (final sidecar refresh)
            self.assertEqual(nr.call_count, 1)


class TestPushUpdateNoPlaceholder(unittest.TestCase):
    """_push_update always calls substitute (no fast-path) — but with
    no placeholders, the substituted doc should structurally match the
    pre-substitute doc."""

    def test_no_placeholder_no_card_nodes_in_save(self):
        with tempfile.TemporaryDirectory() as root:
            vaultlib.init_vault(root)
            rel = "a.md"
            abs_path = os.path.join(root, rel)
            with open(abs_path, "w") as f:
                f.write("# plain\n\nedited body")

            from vault import find as vault_find
            info = vault_find(abs_path)
            vault, cd = info.root, info.cache_dir
            card_id = _UUID_A

            # Register binding and sidecar
            vaultlib.set_file_entry(vault, rel, card_id, [])
            sidecar_dir = os.path.join(cd, "sidecar")
            os.makedirs(sidecar_dir, exist_ok=True)
            old_doc = {"type": "doc", "content": [
                {"type": "heading",
                 "attrs": {"id": "h-old", "level": 1},
                 "content": [{"type": "text", "text": "plain"}]}]}
            with open(os.path.join(sidecar_dir, card_id + ".json"), "w") as f:
                json.dump(old_doc, f)
            local_state.set_local_entry(cd, rel,
                                        content_md5="lock-md5",
                                        local_md5="local-md5",
                                        synced_at="2026-05-25T00:00:00Z")

            scratch_pm = {"type": "doc", "content": [
                {"type": "heading",
                 "attrs": {"id": "h-new", "level": 1},
                 "content": [{"type": "text", "text": "plain"}]}]}
            saved_payloads = []

            def fake_save(card_id_arg, content, content_md5):
                saved_payloads.append(content)
                return {"id": card_id_arg, "title": "x",
                        "contentMd5": "new-md5"}

            with mock.patch.object(hbedit.htb, "note_create",
                                   return_value={"id": "scratch-id",
                                                 "title": "x"}), \
                 mock.patch.object(hbedit.htb, "note_read",
                                   side_effect=[
                                       {"id": "scratch-id",
                                        "title": "x",
                                        "content": json.dumps(scratch_pm),
                                        "contentMd5": "s"},
                                       {"id": card_id, "title": "x",
                                        "content": json.dumps(scratch_pm),
                                        "contentMd5": "new-md5"}
                                   ]), \
                 mock.patch.object(hbedit.htb, "note_save",
                                   side_effect=fake_save), \
                 mock.patch.object(hbedit.htb, "card_trash"):
                hbedit._push_update(vault, cd, rel,
                                    "# plain\n\nedited body", card_id)

            self.assertEqual(len(saved_payloads), 1)
            # The saved JSON must contain no `card` nodes
            self.assertNotIn('"type":"card"', saved_payloads[0])


class TestPushUpdateWithPlaceholder(unittest.TestCase):
    """_push_update: when scratch PM contains [[card:UUID]] text, the
    final note_save payload must contain a card node, not text."""

    def test_placeholder_in_scratch_becomes_card_in_save(self):
        with tempfile.TemporaryDirectory() as root:
            vaultlib.init_vault(root)
            rel = "a.md"
            abs_path = os.path.join(root, rel)
            with open(abs_path, "w") as f:
                f.write(f"# t\n\n[[card:{_UUID_A}]]")

            from vault import find as vault_find
            info = vault_find(abs_path)
            vault, cd = info.root, info.cache_dir
            card_id = _UUID_B

            vaultlib.set_file_entry(vault, rel, card_id, [])
            sidecar_dir = os.path.join(cd, "sidecar")
            os.makedirs(sidecar_dir, exist_ok=True)
            old_doc = {"type": "doc", "content": [
                {"type": "heading",
                 "attrs": {"id": "h-old", "level": 1},
                 "content": [{"type": "text", "text": "t"}]},
                {"type": "paragraph",
                 "attrs": {"id": "p-old"},
                 "content": [{"type": "card",
                              "attrs": {"cardId": _UUID_A}}]}]}
            with open(os.path.join(sidecar_dir, card_id + ".json"), "w") as f:
                json.dump(old_doc, f)
            local_state.set_local_entry(cd, rel,
                                        content_md5="lock-md5",
                                        local_md5="local-md5",
                                        synced_at="2026-05-25T00:00:00Z")

            saved_payloads = []
            scratch_pm = _scratch_pm_with_placeholder_text()
            final_pm = copy.deepcopy(scratch_pm)
            # final remote PM after our save would contain card node;
            # we just need ANY valid JSON for the post-save read.
            final_pm["content"][1]["content"] = [
                {"type": "card", "attrs": {"cardId": _UUID_A}}]

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
                                    f"# t\n\n[[card:{_UUID_A}]]", card_id)

            self.assertEqual(len(saved_payloads), 1)
            payload = json.loads(saved_payloads[0])
            # Find the card node in the saved payload
            self.assertEqual(payload["content"][1]["content"][0]["type"], "card")
            # Paragraph wrapping the card has its id preserved by transplant
            # (since old paragraph had block_text "" and substituted-new
            # paragraph also has block_text "" — signatures match)
            wrapping_para = payload["content"][1]
            self.assertEqual(wrapping_para["type"], "paragraph")
            self.assertEqual(wrapping_para["content"][0],
                             {"type": "card",
                              "attrs": {"cardId": _UUID_A}})
            # The transplanted id should match the old paragraph id
            self.assertEqual(wrapping_para["attrs"]["id"], "p-old")


class TestPushCreateWithPlaceholder(unittest.TestCase):
    """_push_create: when body contains [[card:UUID]], an intermediate
    read+save is performed to replace the placeholder with a card node."""

    def test_placeholder_triggers_substitute_and_save(self):
        with tempfile.TemporaryDirectory() as root:
            vaultlib.init_vault(root)
            rel = "a.md"
            abs_path = os.path.join(root, rel)
            with open(abs_path, "w") as f:
                f.write(f"# t\n\n[[card:{_UUID_A}]]")

            from vault import find as vault_find
            info = vault_find(abs_path)
            vault, cd = info.root, info.cache_dir

            intermediate_pm = _scratch_pm_with_placeholder_text()
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
                                    f"# t\n\n[[card:{_UUID_A}]]")

            # save was called once with the intermediate's md5 as lock
            self.assertEqual(len(saved_payloads), 1)
            card_id_arg, content, lock = saved_payloads[0]
            self.assertEqual(card_id_arg, "new-card-id")
            self.assertEqual(lock, "intermediate-md5")
            # saved payload contains a card node — structural check
            saved_doc = json.loads(content)
            # The paragraph (content[1]) should contain a card node after substitution
            self.assertEqual(
                saved_doc["content"][1]["content"][0]["type"], "card")
            # note_read was called TWICE (intermediate + final-for-sidecar)
            self.assertEqual(nr.call_count, 2)


class TestPushCreateSubstitutionFailure(unittest.TestCase):
    """If the substitution save fails, emit create-failed with detail
    that mentions the card was created and substitution did not complete."""

    def test_save_failure_reports_create_failed(self):
        with tempfile.TemporaryDirectory() as root:
            vaultlib.init_vault(root)
            rel = "a.md"
            abs_path = os.path.join(root, rel)
            with open(abs_path, "w") as f:
                f.write(f"# t\n\n[[card:{_UUID_A}]]")

            from vault import find as vault_find
            info = vault_find(abs_path)
            vault, cd = info.root, info.cache_dir

            intermediate_pm = _scratch_pm_with_placeholder_text()

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
                                              f"# t\n\n[[card:{_UUID_A}]]")

            self.assertEqual(rc, 2)
            obj = json.loads(out)
            self.assertEqual(obj["status"], "error")
            self.assertEqual(obj["code"], "create-failed")
            self.assertIn("substitution", obj["detail"])
            self.assertIn("new-card-id", obj["detail"])


if __name__ == "__main__":
    unittest.main()
