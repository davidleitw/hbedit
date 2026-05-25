import os
import sys
import unittest
from unittest import mock

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "skills", "hbedit", "scripts"))
import htb


class TestUnexpectedResponse(unittest.TestCase):
    """Non-JSON stdout from `heptabase` should raise HtbUnexpectedResponse,
    not silently return a `_raw` placeholder dict. Callers depend on the
    raised exception to surface `cli-response-unexpected`."""

    def test_non_json_stdout_raises(self):
        fake_proc = mock.Mock(returncode=0, stdout="not json at all", stderr="")
        with mock.patch("htb.subprocess.run", return_value=fake_proc):
            with self.assertRaises(htb.HtbUnexpectedResponse):
                htb._run(["note", "read", "x"])

    def test_unexpected_response_is_htberror_subclass(self):
        # Callers that catch HtbError must also catch this — keeps the
        # existing handlers compatible until they're tightened.
        self.assertTrue(issubclass(htb.HtbUnexpectedResponse, htb.HtbError))


class TestPushPropagatesUnexpectedResponse(unittest.TestCase):
    """Generic `except htb.HtbError` blocks in push paths must not swallow
    HtbUnexpectedResponse — otherwise upstream JSON drift would be
    relabeled as `create-failed` / `remote-error` instead of the
    `cli-response-unexpected` agents are taught to look up.
    """

    def test_push_create_propagates(self):
        import hbedit
        with mock.patch.object(
                hbedit.htb, "note_create",
                side_effect=htb.HtbUnexpectedResponse("non-JSON")):
            with self.assertRaises(htb.HtbUnexpectedResponse):
                hbedit._push_create(
                    vault="/tmp/v", cd="/tmp/c",
                    rel_path="x.md", body="body")


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
