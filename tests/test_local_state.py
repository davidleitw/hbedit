"""Tests for local_state.py."""
import json
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "skills", "hbedit", "scripts"))

import local_state


def test_load_missing_returns_empty():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".hbedit"))
        assert local_state.load_local_state(root) == \
            {"schemaVersion": 1, "files": {}}


def test_round_trip():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".hbedit"))
        seed = {"schemaVersion": 1,
                "files": {"docs/a.md": {
                    "contentMd5": "abc", "localMd5": "def",
                    "syncedAt": "2026-01-01T00:00:00Z"}}}
        local_state.save_local_state(root, seed)
        assert local_state.load_local_state(root) == seed


def test_get_set_remove_entry():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".hbedit"))
        assert local_state.get_local_entry(root, "docs/a.md") is None
        local_state.set_local_entry(
            root, "docs/a.md",
            content_md5="cmd", local_md5="lmd", synced_at="2026-01-01T00:00:00Z")
        assert local_state.get_local_entry(root, "docs/a.md") == {
            "contentMd5": "cmd", "localMd5": "lmd",
            "syncedAt": "2026-01-01T00:00:00Z",
        }
        local_state.remove_local_entry(root, "docs/a.md")
        assert local_state.get_local_entry(root, "docs/a.md") is None


def test_load_local_state_tolerates_corrupt_json():
    # local-state.json is per-machine cache; if it's corrupt we can rebuild
    # by re-pulling, so we treat it as missing rather than aborting like
    # state.json does.
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".hbedit"))
        with open(os.path.join(root, ".hbedit", "local-state.json"), "w") as f:
            f.write("{not json")
        assert local_state.load_local_state(root) == \
            {"schemaVersion": 1, "files": {}}
