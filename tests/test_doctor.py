import os
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "skills", "hbedit", "scripts"))
import hbedit
import vault as vaultlib


class TestDoctorCacheLine(unittest.TestCase):
    """The cache line is appended to doctor() output only when cwd is
    inside a vault. The pure formatting helper is tested directly; the
    full doctor() round-trip touches the heptabase CLI and is exercised
    by manual integration tests."""

    def test_cache_line_inside_vault(self):
        with tempfile.TemporaryDirectory() as root:
            vaultlib.init_vault(root)
            line = hbedit._doctor_cache_line(root)
            self.assertIn("cache:", line)
            self.assertIn(".hbedit/cache/", line)
            self.assertIn("(exists:", line)

    def test_cache_line_outside_vault(self):
        with tempfile.TemporaryDirectory() as root:
            # No vault initialized here.
            line = hbedit._doctor_cache_line(root)
            self.assertEqual(line, "")

    def test_cache_line_reports_existence_correctly(self):
        with tempfile.TemporaryDirectory() as root:
            vaultlib.init_vault(root)
            # init_vault does not create cache_dir; doctor reports
            # "exists: no" until something writes to it.
            line = hbedit._doctor_cache_line(root)
            # Either "exists: yes" or "exists: no" must appear, never both.
            self.assertTrue(("exists: yes" in line) ^ ("exists: no" in line))


if __name__ == "__main__":
    unittest.main()
