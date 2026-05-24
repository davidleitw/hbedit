"""Tests for vault.py: vault discovery, state.json v2, init."""
import json
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "skills", "hbedit", "scripts"))

import vault as vaultlib


# -- find_vault_root --------------------------------------------------------
def test_find_vault_root_finds_self():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".hbedit"))
        assert vaultlib.find_vault_root(root) == root


def test_find_vault_root_walks_up():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".hbedit"))
        sub = os.path.join(root, "a", "b", "c")
        os.makedirs(sub)
        assert vaultlib.find_vault_root(sub) == root


def test_find_vault_root_returns_none_when_no_vault():
    with tempfile.TemporaryDirectory() as root:
        assert vaultlib.find_vault_root(root) is None


# -- load_state / save_state ------------------------------------------------
def test_load_state_returns_empty_skeleton_when_missing():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".hbedit"))
        state = vaultlib.load_state(root)
        assert state == {"schemaVersion": 2, "files": {}}


def test_load_state_round_trip():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".hbedit"))
        seed = {"schemaVersion": 2,
                "files": {"docs/foo.md": {"cardId": "abc", "tags": ["x"]}}}
        vaultlib.save_state(root, seed)
        assert vaultlib.load_state(root) == seed


def test_load_state_rejects_v1_schema():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".hbedit"))
        with open(os.path.join(root, ".hbedit", "state.json"), "w") as f:
            f.write('{"cards": {"abc": {"tags": []}}}')
        try:
            vaultlib.load_state(root)
        except vaultlib.StateSchemaError:
            return
        raise AssertionError("expected StateSchemaError for v1 schema")


def test_load_state_rejects_corrupt_json():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".hbedit"))
        with open(os.path.join(root, ".hbedit", "state.json"), "w") as f:
            f.write("{not json")
        try:
            vaultlib.load_state(root)
        except vaultlib.StateCorruptError:
            return
        raise AssertionError("expected StateCorruptError for malformed JSON")


# -- cache_dir --------------------------------------------------------------
def test_cache_dir_resolves_under_home():
    expected = os.path.join(os.path.expanduser("~"), ".hbedit", "cache",
                            "abc-123")
    assert vaultlib.cache_dir("abc-123") == expected


def test_cache_dir_is_string():
    # Other helpers in vault.py return strings (not Path); cache_dir must
    # match so callers don't end up mixing Path and str.
    result = vaultlib.cache_dir("any-id")
    assert isinstance(result, str)


# -- file entry ops ---------------------------------------------------------
def test_set_get_remove_file_entry():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".hbedit"))
        vaultlib.set_file_entry(root, "docs/a.md", "card-1", ["t1"])
        assert vaultlib.get_file_entry(root, "docs/a.md") == \
            {"cardId": "card-1", "tags": ["t1"]}
        vaultlib.remove_file_entry(root, "docs/a.md")
        assert vaultlib.get_file_entry(root, "docs/a.md") is None


def test_find_path_by_card_id():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".hbedit"))
        vaultlib.set_file_entry(root, "docs/a.md", "card-1", [])
        vaultlib.set_file_entry(root, "docs/b.md", "card-2", [])
        assert vaultlib.find_path_by_card_id(root, "card-1") == "docs/a.md"
        assert vaultlib.find_path_by_card_id(root, "card-2") == "docs/b.md"
        assert vaultlib.find_path_by_card_id(root, "card-3") is None


def test_set_file_entry_rejects_duplicate_cardid():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".hbedit"))
        vaultlib.set_file_entry(root, "docs/a.md", "card-1", [])
        try:
            vaultlib.set_file_entry(root, "docs/b.md", "card-1", [])
        except vaultlib.DuplicateCardIdError:
            return
        raise AssertionError("expected DuplicateCardIdError")


# -- init_vault -------------------------------------------------------------
def test_init_vault_creates_state_and_gitignore():
    with tempfile.TemporaryDirectory() as root:
        result = vaultlib.init_vault(root)
        assert result == "created"
        assert os.path.isdir(os.path.join(root, ".hbedit"))
        state = vaultlib.load_state(root)
        assert state == {"schemaVersion": 2, "files": {}}
        with open(os.path.join(root, ".gitignore")) as f:
            text = f.read()
        assert ".hbedit/local-state.json" in text
        assert ".hbedit/sidecar/" in text


def test_init_vault_idempotent_in_own_root():
    with tempfile.TemporaryDirectory() as root:
        vaultlib.init_vault(root)
        result = vaultlib.init_vault(root)
        assert result == "already-initialized"


def test_init_vault_refuses_inside_existing_vault():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".hbedit"))  # the parent vault
        sub = os.path.join(root, "sub")
        os.makedirs(sub)
        try:
            vaultlib.init_vault(sub)
        except vaultlib.NestedVaultError:
            return
        raise AssertionError("expected NestedVaultError")


def test_init_vault_appends_to_existing_gitignore_without_duplicates():
    with tempfile.TemporaryDirectory() as root:
        with open(os.path.join(root, ".gitignore"), "w") as f:
            f.write("# existing\nnode_modules\n")
        vaultlib.init_vault(root)
        vaultlib.init_vault(root)  # second call must not duplicate
        with open(os.path.join(root, ".gitignore")) as f:
            text = f.read()
        # Existing content preserved
        assert "node_modules" in text
        # New entries present exactly once
        assert text.count(".hbedit/local-state.json") == 1
        assert text.count(".hbedit/sidecar/") == 1
