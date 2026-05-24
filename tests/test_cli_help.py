"""Smoke tests for `hb <cmd> --help` — every sub-command must accept
--help without erroring out, so SKILL.md can reliably point agents at
'run hb <cmd> --help for details'."""
import os
import subprocess
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HB = os.path.join(_ROOT, "skills", "hbedit", "scripts", "hbedit.py")


def _run(args):
    """Run hb with the given args; return (stdout, stderr, rc)."""
    proc = subprocess.run(
        [sys.executable, _HB] + args,
        capture_output=True, text=True)
    return proc.stdout, proc.stderr, proc.returncode


class TestSubcommandHelp(unittest.TestCase):
    """Each sub-command's --help must exit 0 and print usage to stdout."""

    def test_doctor_help(self):
        out, err, rc = _run(["doctor", "--help"])
        self.assertEqual(rc, 0, "stderr=%s" % err)
        self.assertIn("doctor", out.lower())

    def test_init_help(self):
        out, err, rc = _run(["init", "--help"])
        self.assertEqual(rc, 0, "stderr=%s" % err)
        self.assertIn("init", out.lower())

    def test_push_help(self):
        out, err, rc = _run(["push", "--help"])
        self.assertEqual(rc, 0, "stderr=%s" % err)
        self.assertIn("push", out.lower())
        self.assertIn("path", out.lower())

    def test_pull_help(self):
        out, err, rc = _run(["pull", "--help"])
        self.assertEqual(rc, 0, "stderr=%s" % err)
        self.assertIn("pull", out.lower())

    def test_tag_help(self):
        out, err, rc = _run(["tag", "--help"])
        self.assertEqual(rc, 0, "stderr=%s" % err)
        self.assertIn("tag", out.lower())

    def test_tag_add_help(self):
        out, err, rc = _run(["tag", "add", "--help"])
        self.assertEqual(rc, 0, "stderr=%s" % err)
        self.assertIn("add", out.lower())

    def test_tag_remove_help(self):
        out, err, rc = _run(["tag", "remove", "--help"])
        self.assertEqual(rc, 0, "stderr=%s" % err)
        self.assertIn("remove", out.lower())

    def test_unlink_help(self):
        out, err, rc = _run(["unlink", "--help"])
        self.assertEqual(rc, 0, "stderr=%s" % err)
        self.assertIn("unlink", out.lower())


class TestTopLevelHelp(unittest.TestCase):
    def test_top_level_help(self):
        out, err, rc = _run(["--help"])
        self.assertEqual(rc, 0, "stderr=%s" % err)
        # Top-level help should mention each sub-command.
        for cmd in ("doctor", "init", "push", "pull", "tag", "unlink"):
            self.assertIn(cmd, out, "missing %s in top-level help" % cmd)


if __name__ == "__main__":
    unittest.main()
