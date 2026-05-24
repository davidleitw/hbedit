"""Unit tests for `hb unlink <path>` — removes a path's binding from
state.json + per-machine cache without touching local md or remote card."""
import json
import os
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "skills", "hbedit", "scripts"))
import hbedit
import vault as vaultlib
import local_state


def _make_vault_with_tracked_file(root, rel_path="notes/foo.md",
                                  card_id="card-abc-123"):
    """Set up a vault with one tracked file. Returns (vault_info, abs_path)."""
    vaultlib.init_vault(root)
    info = vaultlib.find(root)
    abs_path = os.path.join(root, rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write("# Foo\n\nBody.\n")
    # Register in state.json
    vaultlib.set_file_entry(info.root, rel_path, card_id, [])
    # Populate local-state and sidecar
    local_state.set_local_entry(
        info.cache_dir, rel_path,
        content_md5="dummy-content-md5",
        local_md5="dummy-local-md5",
        synced_at="2026-05-24T00:00:00Z")
    sidecar = hbedit._sidecar_path(info.cache_dir, card_id)
    with open(sidecar, "w", encoding="utf-8") as f:
        f.write('{"type":"doc","content":[]}')
    return info, abs_path


class TestUnlinkBasic(unittest.TestCase):
    def test_unlink_removes_state_entry(self):
        with tempfile.TemporaryDirectory() as root:
            info, _ = _make_vault_with_tracked_file(root)
            out, rc = hbedit.unlink(os.path.join(root, "notes/foo.md"))
            self.assertEqual(rc, 0)
            payload = json.loads(out)
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["action"], "unlinked")
            self.assertEqual(payload["path"], "notes/foo.md")
            self.assertEqual(payload["cardId"], "card-abc-123")
            # state.json should no longer have the entry
            state = vaultlib.load_state(info.root)
            self.assertNotIn("notes/foo.md", state["files"])

    def test_unlink_removes_local_state_entry(self):
        with tempfile.TemporaryDirectory() as root:
            info, _ = _make_vault_with_tracked_file(root)
            hbedit.unlink(os.path.join(root, "notes/foo.md"))
            entry = local_state.get_local_entry(info.cache_dir, "notes/foo.md")
            self.assertIsNone(entry)

    def test_unlink_removes_sidecar(self):
        with tempfile.TemporaryDirectory() as root:
            info, _ = _make_vault_with_tracked_file(root, card_id="card-xyz")
            sidecar = hbedit._sidecar_path(info.cache_dir, "card-xyz")
            self.assertTrue(os.path.exists(sidecar))
            hbedit.unlink(os.path.join(root, "notes/foo.md"))
            self.assertFalse(os.path.exists(sidecar))

    def test_unlink_leaves_local_md_alone(self):
        with tempfile.TemporaryDirectory() as root:
            info, abs_path = _make_vault_with_tracked_file(root)
            original_body = open(abs_path).read()
            hbedit.unlink(abs_path)
            self.assertTrue(os.path.exists(abs_path))
            self.assertEqual(open(abs_path).read(), original_body)


class TestUnlinkErrors(unittest.TestCase):
    def test_unlink_path_not_tracked(self):
        with tempfile.TemporaryDirectory() as root:
            vaultlib.init_vault(root)
            os.makedirs(os.path.join(root, "notes"))
            untracked = os.path.join(root, "notes/never-pushed.md")
            with open(untracked, "w") as f:
                f.write("# Foo\n")
            out, rc = hbedit.unlink(untracked)
            self.assertEqual(rc, 2)
            payload = json.loads(out)
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["code"], "path-not-tracked")

    def test_unlink_idempotent_second_call_errors(self):
        # Second unlink on a path that's already gone returns the same
        # path-not-tracked error — agent / user can infer it's already done.
        with tempfile.TemporaryDirectory() as root:
            _make_vault_with_tracked_file(root)
            abs_path = os.path.join(root, "notes/foo.md")
            out1, rc1 = hbedit.unlink(abs_path)
            self.assertEqual(rc1, 0)
            out2, rc2 = hbedit.unlink(abs_path)
            self.assertEqual(rc2, 2)
            self.assertEqual(json.loads(out2)["code"], "path-not-tracked")

    def test_unlink_not_in_vault(self):
        with tempfile.TemporaryDirectory() as root:
            # No vault init
            os.makedirs(os.path.join(root, "notes"))
            target = os.path.join(root, "notes/orphan.md")
            with open(target, "w") as f:
                f.write("# Foo\n")
            out, rc = hbedit.unlink(target)
            self.assertEqual(rc, 2)
            self.assertEqual(json.loads(out)["code"], "not-in-vault")


if __name__ == "__main__":
    unittest.main()
