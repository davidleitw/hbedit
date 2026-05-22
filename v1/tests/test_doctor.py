import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "v1", "skill", "scripts"))
import hs


class TestVersionGate(unittest.TestCase):
    def test_supported_minor(self):
        self.assertTrue(hs._version_supported("0.3.0"))
        self.assertTrue(hs._version_supported("0.3.9"))

    def test_unsupported_minor(self):
        self.assertFalse(hs._version_supported("0.2.9"))
        self.assertFalse(hs._version_supported("0.4.0"))

    def test_garbage(self):
        self.assertFalse(hs._version_supported(""))
        self.assertFalse(hs._version_supported("not-a-version"))


if __name__ == "__main__":
    unittest.main()
