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
        # state.json must exist for find_vault_root to recognize the dir.
        with open(os.path.join(root, ".hbedit", "state.json"), "w") as f:
            f.write('{"schemaVersion": 2, "files": {}}')
        assert vaultlib.find_vault_root(root) == root


def test_find_vault_root_walks_up():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".hbedit"))
        with open(os.path.join(root, ".hbedit", "state.json"), "w") as f:
            f.write('{"schemaVersion": 2, "files": {}}')
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
        # The empty skeleton has no vaultId; vaultId is added only at
        # init_vault time. load_state of an absent file just returns the
        # bare shape.
        assert state == {"schemaVersion": 3, "files": {}}


def test_load_state_round_trip():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".hbedit"))
        seed = {"schemaVersion": 3,
                "vaultId": "v-uuid-rt",
                "files": {"docs/foo.md": {"cardId": "abc", "tags": ["x"]}}}
        vaultlib.save_state(root, seed)
        assert vaultlib.load_state(root) == seed


def test_load_state_rejects_legacy_schema():
    """Pre-v2 had {cards: {cardId: {...}}} keyed by cardId, no schemaVersion.
    v3 still rejects it."""
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".hbedit"))
        with open(os.path.join(root, ".hbedit", "state.json"), "w") as f:
            f.write('{"cards": {"abc": {"tags": []}}}')
        try:
            vaultlib.load_state(root)
        except vaultlib.StateSchemaError:
            return
        raise AssertionError("expected StateSchemaError for pre-v2 schema")


def test_load_state_rejects_v2_schema():
    """v2 schemaVersion 2 is no longer supported in v3."""
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".hbedit"))
        with open(os.path.join(root, ".hbedit", "state.json"), "w") as f:
            f.write('{"schemaVersion": 2, "files": {}}')
        try:
            vaultlib.load_state(root)
        except vaultlib.StateSchemaError:
            return
        raise AssertionError("expected StateSchemaError for v2 schema")


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
def test_init_vault_creates_state_with_vaultid_and_no_gitignore():
    with tempfile.TemporaryDirectory() as root:
        result = vaultlib.init_vault(root)
        assert result == "created"
        assert os.path.isdir(os.path.join(root, ".hbedit"))
        state = vaultlib.load_state(root)
        assert state["schemaVersion"] == 3
        assert state["files"] == {}
        # vaultId is a UUID string (36 chars including hyphens).
        assert isinstance(state["vaultId"], str)
        assert len(state["vaultId"]) == 36
        # No .gitignore is written by hb init in v3.
        assert not os.path.exists(os.path.join(root, ".gitignore"))
        # v3: cache directory + sidecar/ must be created eagerly.
        cache_d = vaultlib.cache_dir(state["vaultId"])
        assert os.path.isdir(cache_d), \
            "cache_dir not created by init_vault: %s" % cache_d
        assert os.path.isdir(os.path.join(cache_d, "sidecar")), \
            "sidecar/ not created by init_vault under %s" % cache_d
        # Cleanup so this test doesn't leave global state behind.
        import shutil
        shutil.rmtree(cache_d, ignore_errors=True)


def test_init_vault_idempotent_in_own_root():
    with tempfile.TemporaryDirectory() as root:
        vaultlib.init_vault(root)
        result = vaultlib.init_vault(root)
        assert result == "already-initialized"


def test_init_vault_refuses_inside_existing_vault():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".hbedit"))  # the parent vault
        with open(os.path.join(root, ".hbedit", "state.json"), "w") as f:
            f.write('{"schemaVersion": 2, "files": {}}')
        sub = os.path.join(root, "sub")
        os.makedirs(sub)
        try:
            vaultlib.init_vault(sub)
        except vaultlib.NestedVaultError:
            return
        raise AssertionError("expected NestedVaultError")



# -- VaultInfo / find() -----------------------------------------------------
def test_find_returns_none_when_no_vault():
    with tempfile.TemporaryDirectory() as root:
        assert vaultlib.find(root) is None


def test_find_returns_vault_info_with_root_state_cache_dir():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".hbedit"))
        seed = {"schemaVersion": 3,
                "files": {"docs/a.md": {"cardId": "c1", "tags": []}}}
        vaultlib.save_state(root, seed)
        # Inject vaultId by hand so this test runs even before schema bump.
        # (Task 4 will add vaultId via init_vault; here we set it directly.)
        path = os.path.join(root, ".hbedit", "state.json")
        import json as _json
        with open(path, "r") as f:
            data = _json.load(f)
        data["vaultId"] = "v-uuid-1"
        with open(path, "w") as f:
            _json.dump(data, f)
        info = vaultlib.find(root)
        assert info.root == root
        assert info.state["files"]["docs/a.md"]["cardId"] == "c1"
        assert info.cache_dir == os.path.join(
            os.path.expanduser("~"), ".hbedit", "cache", "v-uuid-1")


def test_find_walks_up_like_find_vault_root():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".hbedit"))
        seed = {"schemaVersion": 3,
                "vaultId": "v-uuid-2",
                "files": {}}
        # Write state.json directly with vaultId.
        import json as _json
        path = os.path.join(root, ".hbedit", "state.json")
        with open(path, "w") as f:
            _json.dump(seed, f)
        sub = os.path.join(root, "a", "b")
        os.makedirs(sub)
        info = vaultlib.find(sub)
        assert info.root == root
        assert info.state["vaultId"] == "v-uuid-2"


def test_find_vault_root_ignores_empty_dotdir():
    """A .hbedit/ directory without state.json must not count as a vault.

    This is the latent bug exposed by the v3 global-cache layout
    (~/.hbedit/cache/...): any file under $HOME walking up would
    otherwise false-positive at $HOME.
    """
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".hbedit"))  # no state.json inside
        sub = os.path.join(root, "a")
        os.makedirs(sub)
        # Walk-up from sub finds the empty .hbedit/ at root in v2 (bug),
        # must return None after the fix.
        assert vaultlib.find_vault_root(sub) is None
