# hbedit v3 (Global Cache) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move hbedit's per-machine caches (`local-state.json`, `sidecar/`) from project-local `.hbedit/` to global `~/.hbedit/cache/<vault-id>/`, leaving only the git-tracked `state.json` in each project. Bump state schema 2→3 with new `vaultId` field. Fix a latent vault-discovery bug exposed by the new global cache layout.

**Architecture:** Three coordinated changes — (1) `vault.py` adds a `cache_dir()` helper, a `VaultInfo` dataclass, and a `find(start)` function that returns root+state+cache_dir as one unit; bumps `SCHEMA_VERSION` 2→3; tightens `find_vault_root()` to check for `state.json` file (not just `.hbedit/` directory); `init_vault()` writes `vaultId` and stops touching `.gitignore`. (2) `local_state.py` switches its public API from `(vault, ...)` to `(cache_dir, ...)`. (3) `hbedit.py`'s `_sidecar_path()` switches to `cache_dir`, all call sites switch from the `find_vault_root + load_state` pair to `find()` returning `VaultInfo`, and `doctor()` reports the cache directory when invoked inside a vault. `state.json`'s `files` shape is unchanged.

**Tech Stack:** Python 3 stdlib (`json`, `os`, `uuid`, `dataclasses`, `pathlib`). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-05-24-hbedit-global-cache-design.md`

**Branch:** `oneclick-install` (continuing the same branch as v2)

---

## File map

| File | Action |
|---|---|
| `skills/hbedit/scripts/vault.py` | Modify (~50 LoC change) |
| `skills/hbedit/scripts/local_state.py` | Modify (~15 LoC change) |
| `skills/hbedit/scripts/hbedit.py` | Modify (~40 LoC change) |
| `skills/hbedit/SKILL.md` | Modify (~20 LoC change in vault-layout + init sections) |
| `tests/test_vault.py` | Modify + add (~70 LoC change) |
| `tests/test_local_state.py` | Modify (~10 LoC change) |
| `tests/test_doctor.py` | Add (~30 LoC new test class) |
| `.hbedit/` (HeptaSync repo root) | Delete (untracked) |
| `TESTING-NOTES.md` | Delete (tracked) |
| `skills/hbedit/scripts/errors.py`, `htb.py`, `pm2md.py`, `tagsync.py`, `transplant.py` | Unchanged |
| `tests/test_errors.py`, `test_htb_args.py`, `test_pm2md.py`, `test_tagsync.py` | Unchanged |

---

## Task 1: Add `cache_dir()` helper to vault.py

**Goal:** Pure additive change. Introduces the one function that knows where a vault's per-machine cache lives. No existing behavior touched.

**Files:**
- Modify: `skills/hbedit/scripts/vault.py` (top-level addition near other helpers)
- Test: `tests/test_vault.py` (add new test function)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_vault.py` (just before the `# -- file entry ops` section header, around line 73):

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_vault.py::test_cache_dir_resolves_under_home -v
```

Expected: FAIL with `AttributeError: module 'vault' has no attribute 'cache_dir'`.

- [ ] **Step 3: Add the helper to `vault.py`**

In `skills/hbedit/scripts/vault.py`, after the `_atomic_write` function (around line 72), add:

```python
# -- global cache location -------------------------------------------------
def cache_dir(vault_id):
    """Return the per-machine cache directory for `vault_id`.

    Layout: ~/.hbedit/cache/<vault-id>/
    Contains:
      - local-state.json (per-machine md5 cache)
      - sidecar/<cardId>.json (per-machine ProseMirror block cache)

    This directory is *not* created here; callers that write into it use
    os.makedirs(..., exist_ok=True) as needed.
    """
    return os.path.join(os.path.expanduser("~"), ".hbedit", "cache", vault_id)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_vault.py -v
```

Expected: PASS for both new tests; all existing `test_vault.py` tests still pass (no behavior change to existing code).

- [ ] **Step 5: Commit**

```bash
git add skills/hbedit/scripts/vault.py tests/test_vault.py
git commit -m "feat(hbedit): add vault.cache_dir() helper for global cache path

Returns ~/.hbedit/cache/<vault-id>/ as a string. Pure addition; no
existing call sites changed yet."
```

---

## Task 2: Add `VaultInfo` dataclass and `find()` function

**Goal:** Pure additive change. `find()` bundles `(root, state, cache_dir)` so future call sites don't independently compute the cache path (the drift-prevention goal from the spec).

**Files:**
- Modify: `skills/hbedit/scripts/vault.py`
- Test: `tests/test_vault.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_vault.py`:

```python
# -- VaultInfo / find() -----------------------------------------------------
def test_find_returns_none_when_no_vault():
    with tempfile.TemporaryDirectory() as root:
        assert vaultlib.find(root) is None


def test_find_returns_vault_info_with_root_state_cache_dir():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".hbedit"))
        seed = {"schemaVersion": 2,
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
        seed = {"schemaVersion": 2,
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_vault.py::test_find_returns_none_when_no_vault -v
```

Expected: FAIL with `AttributeError: module 'vault' has no attribute 'find'`.

- [ ] **Step 3: Add `VaultInfo` and `find()` to `vault.py`**

At the top of `skills/hbedit/scripts/vault.py`, after the imports block (around line 13), add:

```python
from dataclasses import dataclass


@dataclass
class VaultInfo:
    """Bundle returned by `find()`. Single source of truth for cache_dir."""
    root: str        # vault root path (the dir containing .hbedit/)
    state: dict      # parsed state.json
    cache_dir: str   # ~/.hbedit/cache/<vault-id>/
```

Then after `cache_dir()` (added in Task 1), add:

```python
def find(start):
    """High-level vault lookup. Returns a VaultInfo bundling root, state
    and per-machine cache_dir. Returns None if `start` is not inside a
    vault. Raises StateSchemaError / StateCorruptError just like
    load_state() if the state.json is unreadable.
    """
    root = find_vault_root(start)
    if root is None:
        return None
    state = load_state(root)
    cd = cache_dir(state["vaultId"])
    return VaultInfo(root=root, state=state, cache_dir=cd)
```

Note: in Tasks 1–3 the on-disk state.json still has `schemaVersion: 2` and may lack `vaultId`. The test above writes `vaultId` by hand. `find()` will KeyError on `state["vaultId"]` if it's missing — but no production caller uses `find()` yet (Task 7 introduces them, and by then Task 4 has bumped `init_vault` to always write `vaultId`).

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_vault.py -v
```

Expected: PASS for new tests; existing tests still pass.

- [ ] **Step 5: Commit**

```bash
git add skills/hbedit/scripts/vault.py tests/test_vault.py
git commit -m "feat(hbedit): add VaultInfo dataclass and vault.find()

find(start) bundles root, parsed state, and computed cache_dir into one
return so call sites don't re-derive paths. Pure addition; existing
find_vault_root / load_state remain untouched."
```

---

## Task 3: Tighten `find_vault_root` to require state.json file

**Goal:** Fix the latent bug exposed by introducing `~/.hbedit/cache/`. A bare `.hbedit/` directory anywhere (notably at `$HOME` once cache lives there) must not satisfy vault discovery.

**Files:**
- Modify: `skills/hbedit/scripts/vault.py`
- Test: `tests/test_vault.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_vault.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_vault.py::test_find_vault_root_ignores_empty_dotdir -v
```

Expected: FAIL — `find_vault_root` returns `root` because the directory check is too loose.

- [ ] **Step 3: Tighten the check**

In `skills/hbedit/scripts/vault.py`, replace the body of `find_vault_root` (lines 38–50):

```python
def find_vault_root(start):
    """Walk up from `start` (a file or dir) to the dir holding
    `.hbedit/state.json`. Returns the vault root path, or None if no
    vault encloses `start`.

    Checks for the state.json *file*, not just the .hbedit directory —
    an empty .hbedit/ anywhere (notably ~/.hbedit/cache/...) must not
    fool discovery.
    """
    d = os.path.abspath(start)
    if os.path.isfile(d):
        d = os.path.dirname(d)
    while True:
        if os.path.isfile(os.path.join(d, STATE_DIR, STATE_FILE)):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_vault.py -v
```

Expected: PASS for new test. Existing tests that pre-create only `.hbedit/` (without state.json) and expect `find_vault_root` to succeed must now also write a state.json. Check each existing test that creates `.hbedit/` directly with `os.makedirs`:

In `tests/test_vault.py`:

- `test_find_vault_root_finds_self` (line 14–17): currently passes because `os.makedirs(.hbedit)` is enough. **Must update** — write a minimal state.json after the mkdir:

  Replace:
  ```python
  def test_find_vault_root_finds_self():
      with tempfile.TemporaryDirectory() as root:
          os.makedirs(os.path.join(root, ".hbedit"))
          assert vaultlib.find_vault_root(root) == root
  ```
  With:
  ```python
  def test_find_vault_root_finds_self():
      with tempfile.TemporaryDirectory() as root:
          os.makedirs(os.path.join(root, ".hbedit"))
          # state.json must exist for find_vault_root to recognize the dir.
          with open(os.path.join(root, ".hbedit", "state.json"), "w") as f:
              f.write('{"schemaVersion": 2, "files": {}}')
          assert vaultlib.find_vault_root(root) == root
  ```

- `test_find_vault_root_walks_up` (line 20–25): same fix.

  Replace:
  ```python
  def test_find_vault_root_walks_up():
      with tempfile.TemporaryDirectory() as root:
          os.makedirs(os.path.join(root, ".hbedit"))
          sub = os.path.join(root, "a", "b", "c")
          os.makedirs(sub)
          assert vaultlib.find_vault_root(sub) == root
  ```
  With:
  ```python
  def test_find_vault_root_walks_up():
      with tempfile.TemporaryDirectory() as root:
          os.makedirs(os.path.join(root, ".hbedit"))
          with open(os.path.join(root, ".hbedit", "state.json"), "w") as f:
              f.write('{"schemaVersion": 2, "files": {}}')
          sub = os.path.join(root, "a", "b", "c")
          os.makedirs(sub)
          assert vaultlib.find_vault_root(sub) == root
  ```

- `test_init_vault_refuses_inside_existing_vault` (line 127–136): the parent vault check uses `os.makedirs(.hbedit)` only. Update similarly:

  Replace the `os.makedirs(os.path.join(root, ".hbedit"))` line with:
  ```python
  os.makedirs(os.path.join(root, ".hbedit"))
  with open(os.path.join(root, ".hbedit", "state.json"), "w") as f:
      f.write('{"schemaVersion": 2, "files": {}}')
  ```

Other tests in `test_vault.py` that create state via `vaultlib.save_state` or `vaultlib.init_vault` write state.json automatically and need no update.

- [ ] **Step 5: Re-run tests**

```bash
python3 -m pytest tests/test_vault.py -v
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add skills/hbedit/scripts/vault.py tests/test_vault.py
git commit -m "fix(hbedit): vault discovery requires state.json file, not just .hbedit dir

Latent bug: an empty .hbedit/ anywhere fooled find_vault_root. v3's
global cache lives at ~/.hbedit/cache/, which would otherwise cause
every file under \$HOME to false-positive at \$HOME. Now the walk-up
loop checks for the state.json file directly."
```

---

## Task 4: Bump `SCHEMA_VERSION` 2→3, write `vaultId` on init, drop `.gitignore` writes

**Goal:** Land the schema cutover. After this commit, only `schemaVersion: 3` state.json files are valid; `hb init` writes a UUIDv4 `vaultId` and never touches `.gitignore`.

**Files:**
- Modify: `skills/hbedit/scripts/vault.py`
- Test: `tests/test_vault.py`

- [ ] **Step 1: Update test for empty-skeleton schema**

In `tests/test_vault.py`, locate `test_load_state_returns_empty_skeleton_when_missing` (line 34–38). Replace:

```python
def test_load_state_returns_empty_skeleton_when_missing():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".hbedit"))
        state = vaultlib.load_state(root)
        assert state == {"schemaVersion": 2, "files": {}}
```

With:

```python
def test_load_state_returns_empty_skeleton_when_missing():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".hbedit"))
        state = vaultlib.load_state(root)
        # The empty skeleton has no vaultId; vaultId is added only at
        # init_vault time. load_state of an absent file just returns the
        # bare shape.
        assert state == {"schemaVersion": 3, "files": {}}
```

- [ ] **Step 2: Update round-trip test schema**

Locate `test_load_state_round_trip` (line 41–47). Replace:

```python
def test_load_state_round_trip():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".hbedit"))
        seed = {"schemaVersion": 2,
                "files": {"docs/foo.md": {"cardId": "abc", "tags": ["x"]}}}
        vaultlib.save_state(root, seed)
        assert vaultlib.load_state(root) == seed
```

With:

```python
def test_load_state_round_trip():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".hbedit"))
        seed = {"schemaVersion": 3,
                "vaultId": "v-uuid-rt",
                "files": {"docs/foo.md": {"cardId": "abc", "tags": ["x"]}}}
        vaultlib.save_state(root, seed)
        assert vaultlib.load_state(root) == seed
```

- [ ] **Step 3: Expand the schema-rejection test to cover both pre-v3 schemas**

Locate `test_load_state_rejects_v1_schema` (line 50–59). Replace with two tests:

```python
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
```

- [ ] **Step 4: Update init test for new behavior (no .gitignore, vaultId present)**

Locate `test_init_vault_creates_state_and_gitignore` (line 107–117). Replace:

```python
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
```

With:

```python
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
```

- [ ] **Step 5: Delete the .gitignore-dedup test (no longer applicable)**

Delete `test_init_vault_appends_to_existing_gitignore_without_duplicates` (line 139–151) entirely. In v3 `hb init` never writes `.gitignore`, so there is no append-or-dedup behavior to test.

- [ ] **Step 6: Run tests to verify the suite now fails on the still-v2 implementation**

```bash
python3 -m pytest tests/test_vault.py -v
```

Expected: FAILs in the tests modified above — `assert state["schemaVersion"] == 3` fails because the module still has `SCHEMA_VERSION = 2`, and `vaultId` assertions fail because init doesn't write it yet.

- [ ] **Step 7: Bump `SCHEMA_VERSION` in `vault.py`**

In `skills/hbedit/scripts/vault.py`, change line 16:

```python
SCHEMA_VERSION = 2
```

to:

```python
SCHEMA_VERSION = 3
```

- [ ] **Step 8: Add `uuid` import**

In `skills/hbedit/scripts/vault.py`, add to the imports block near line 8:

```python
import uuid
```

- [ ] **Step 9: Update `init_vault` to write `vaultId` and skip `.gitignore`**

In `skills/hbedit/scripts/vault.py`, replace the `init_vault` function (lines 152–168):

```python
def init_vault(cwd):
    """Create a vault at `cwd`. Returns one of:
       - "created" — vault freshly created
       - "already-initialized" — cwd already has its own .hbedit/
    Raises NestedVaultError if cwd is inside another vault's tree.

    v3 changes (relative to v2):
      - state.json gets a `vaultId` (UUIDv4) that travels with the repo.
      - .gitignore is NOT written: there are no per-machine files left in
        the project tree.
    """
    own = os.path.join(cwd, STATE_DIR)
    if os.path.isdir(own):
        return "already-initialized"
    ancestor = find_vault_root(cwd)
    if ancestor is not None:
        raise NestedVaultError("vault already exists at %s" % ancestor)
    os.makedirs(own)
    save_state(cwd, {
        "schemaVersion": SCHEMA_VERSION,
        "vaultId": str(uuid.uuid4()),
        "files": {},
    })
    return "created"
```

- [ ] **Step 10: Remove the now-unused `_update_gitignore` and `GITIGNORE_LINES`**

In `skills/hbedit/scripts/vault.py`:

- Delete line 17 (`GITIGNORE_LINES = [".hbedit/local-state.json", ".hbedit/sidecar/"]`).
- Delete the entire `_update_gitignore` function (lines 171–188).

- [ ] **Step 11: Run tests, expect green**

```bash
python3 -m pytest tests/test_vault.py -v
```

Expected: All tests PASS.

- [ ] **Step 12: Commit**

```bash
git add skills/hbedit/scripts/vault.py tests/test_vault.py
git commit -m "feat(hbedit)!: state.json schema v3 — vaultId field, no .gitignore on init

Bumps SCHEMA_VERSION 2→3. init_vault now writes vaultId (UUIDv4) into
state.json so per-machine caches can key off it. .gitignore is no
longer written — v3 caches live under ~/.hbedit/cache/<vault-id>/ and
nothing in the project tree needs to be ignored.

state.json schemaVersion 2 is rejected (no released v2 to migrate)."
```

---

## Task 5: Refactor `local_state.py` to take `cache_dir` instead of `vault`

**Goal:** Move local-state.json reads/writes out of the project tree. All public functions switch their first parameter from `vault` to `cache_dir`. Callers in `hbedit.py` (which still pass `vault`) start failing — they're fixed in this same task.

**Files:**
- Modify: `skills/hbedit/scripts/local_state.py`
- Modify: `skills/hbedit/scripts/hbedit.py` (all `local_state.*` call sites)
- Test: `tests/test_local_state.py`

- [ ] **Step 1: Rewrite `test_local_state.py` to pass `cache_dir`**

The tests currently pass `root` (a tempdir) where `vault` was expected, and the code looked for `<root>/.hbedit/local-state.json`. In v3, callers pass a cache_dir directly, and the file lives at `<cache_dir>/local-state.json`. Rewrite each test.

Replace the entire contents of `tests/test_local_state.py` with:

```python
"""Tests for local_state.py."""
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "skills", "hbedit", "scripts"))

import local_state


def test_load_missing_returns_empty():
    with tempfile.TemporaryDirectory() as cache_dir:
        assert local_state.load_local_state(cache_dir) == \
            {"schemaVersion": 1, "files": {}}


def test_round_trip():
    with tempfile.TemporaryDirectory() as cache_dir:
        seed = {"schemaVersion": 1,
                "files": {"docs/a.md": {
                    "contentMd5": "abc", "localMd5": "def",
                    "syncedAt": "2026-01-01T00:00:00Z"}}}
        local_state.save_local_state(cache_dir, seed)
        assert local_state.load_local_state(cache_dir) == seed


def test_get_set_remove_entry():
    with tempfile.TemporaryDirectory() as cache_dir:
        assert local_state.get_local_entry(cache_dir, "docs/a.md") is None
        local_state.set_local_entry(
            cache_dir, "docs/a.md",
            content_md5="cmd", local_md5="lmd",
            synced_at="2026-01-01T00:00:00Z")
        assert local_state.get_local_entry(cache_dir, "docs/a.md") == {
            "contentMd5": "cmd", "localMd5": "lmd",
            "syncedAt": "2026-01-01T00:00:00Z",
        }
        local_state.remove_local_entry(cache_dir, "docs/a.md")
        assert local_state.get_local_entry(cache_dir, "docs/a.md") is None


def test_load_local_state_tolerates_corrupt_json():
    # local-state.json is per-machine cache; if it's corrupt we can rebuild
    # by re-pulling, so we treat it as missing rather than aborting like
    # state.json does.
    with tempfile.TemporaryDirectory() as cache_dir:
        with open(os.path.join(cache_dir, "local-state.json"), "w") as f:
            f.write("{not json")
        assert local_state.load_local_state(cache_dir) == \
            {"schemaVersion": 1, "files": {}}


def test_save_creates_cache_dir_if_missing():
    with tempfile.TemporaryDirectory() as parent:
        cache_dir = os.path.join(parent, "nonexistent", "cache")
        local_state.save_local_state(cache_dir, {
            "schemaVersion": 1, "files": {}})
        assert os.path.isfile(os.path.join(cache_dir, "local-state.json"))


def test_body_md5_deterministic():
    text = "# Hello\n\nWorld\n"
    a = local_state.body_md5(text)
    b = local_state.body_md5(text)
    assert a == b
    assert isinstance(a, str)
    assert len(a) == 32  # md5 hex


def test_body_md5_normalizes_line_endings():
    a = local_state.body_md5("a\r\nb\r\n")
    b = local_state.body_md5("a\nb\n")
    assert a == b
```

- [ ] **Step 2: Run the test file, expect failure**

```bash
python3 -m pytest tests/test_local_state.py -v
```

Expected: FAILs — `local_state.load_local_state(cache_dir)` tries to read `<cache_dir>/.hbedit/local-state.json` which doesn't exist; tests expecting an empty skeleton still get the right answer but `test_save_creates_cache_dir_if_missing` will fail because the current implementation creates `<cache_dir>/.hbedit/` instead of `<cache_dir>/`.

- [ ] **Step 3: Rewrite `local_state.py` to use `cache_dir`**

Replace the entire contents of `skills/hbedit/scripts/local_state.py` with:

```python
"""hbedit v3 — per-machine sync cache (`~/.hbedit/cache/<vault-id>/local-state.json`).

For each tracked path this file records:
- contentMd5: the remote ProseMirror md5 at last sync (push lock)
- localMd5:   the md5 of the local .md body at last sync (used to detect
              uncommitted local changes before a pull would overwrite)
- syncedAt:   ISO-8601 UTC timestamp of the last sync

Cache lives outside the project tree (under the user's home), keyed by
vault-id from state.json so machine A and machine B share the same key
after a git clone.

Corruption recovery: unlike state.json (authoritative, fail-loud on
corruption), local-state.json is rebuildable by re-pulling each tracked
card, so we silently treat a corrupt file as empty.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile

LOCAL_STATE_FILE = "local-state.json"
SCHEMA_VERSION = 1


def body_md5(text):
    """Stable md5 of a markdown body.

    Line endings are normalized to LF before hashing — local files may
    arrive via git with CRLF (Windows / autocrlf) but we want a single
    canonical hash. UTF-8 encoding is forced.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


def _path(cache_dir):
    return os.path.join(cache_dir, LOCAL_STATE_FILE)


def _atomic_write(path, text):
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix=".hbedit-local-", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _empty():
    return {"schemaVersion": SCHEMA_VERSION, "files": {}}


def load_local_state(cache_dir):
    """Return the parsed file, or the empty skeleton if missing or corrupt."""
    p = _path(cache_dir)
    if not os.path.exists(p):
        return _empty()
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return _empty()
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        return _empty()
    return data


def save_local_state(cache_dir, state):
    os.makedirs(cache_dir, exist_ok=True)
    _atomic_write(_path(cache_dir),
                  json.dumps(state, ensure_ascii=False, indent=2))


def get_local_entry(cache_dir, path):
    """Return {contentMd5, localMd5, syncedAt} for path, or None."""
    return load_local_state(cache_dir)["files"].get(path)


def set_local_entry(cache_dir, path, content_md5, local_md5, synced_at):
    state = load_local_state(cache_dir)
    state["files"][path] = {
        "contentMd5": content_md5,
        "localMd5": local_md5,
        "syncedAt": synced_at,
    }
    save_local_state(cache_dir, state)


def remove_local_entry(cache_dir, path):
    state = load_local_state(cache_dir)
    if path in state["files"]:
        del state["files"][path]
        save_local_state(cache_dir, state)
```

- [ ] **Step 4: Update every `local_state.*` call site in `hbedit.py`**

`hbedit.py` currently has these call sites (line numbers from the post-Task-4 file; offsets may vary slightly):

- Line 172: `local_state.set_local_entry(vault, rel_path, ...)`
- Line 184: `entry = local_state.get_local_entry(vault, rel_path)`
- Line 231: `local_state.set_local_entry(vault, rel_path, ...)`
- Line 297: `local_state.set_local_entry(vault, rel, ...)`
- Line 358: `local_entry = local_state.get_local_entry(vault, rel)`
- Line 403: `local_state.set_local_entry(vault, rel, ...)`
- Line 414: `entry = local_state.get_local_entry(vault, rel)`
- Line 415: `local_state.set_local_entry(vault, rel, ...)`
- Line 432: `local_state.set_local_entry(vault, rel, ...)`
- Line 567: `local_state.set_local_entry(vault, rel_path, ...)`

At each call site, replace `vault` with `vaultlib.cache_dir(state["vaultId"])`. The simplest mechanical change: compute `cd = vaultlib.cache_dir(state["vaultId"])` once after `state = vaultlib.load_state(vault)` in each enclosing function, then pass `cd` instead of `vault`. (Task 7 will replace this idiom with `info = vaultlib.find(path); cd = info.cache_dir` — for now use the explicit form so this task stays narrow.)

Concretely, for `push()` (lines 111–142), after `state = vaultlib.load_state(vault)` on line 129, add:

```python
    cd = vaultlib.cache_dir(state["vaultId"])
```

and pass `cd` instead of `vault` into every `local_state.*` call inside `push()` and the helpers it threads through (`_push_create`, `_push_update`). Since those helpers don't currently take a cache_dir, give them one as a new parameter (no other choice without falling back to `find()` early). Update the signatures and call sites of `_push_create` and `_push_update` to accept and pass `cd`.

Apply the same idiom to `pull_first_time`, `pull_smart`, `_baseline_established`, `_refresh_synced_at`, `_write_remote_and_baseline`, `_tag_op`, and `_handle_conflict` — every function that calls `local_state.*` gets `cd` either from its own `load_state` or from its caller as a new parameter.

After the refactor every `local_state.set_local_entry(vault, ...)` reads `local_state.set_local_entry(cd, ...)` and every `local_state.get_local_entry(vault, ...)` reads `local_state.get_local_entry(cd, ...)`.

- [ ] **Step 5: Run all tests**

```bash
python3 -m pytest tests/ -v
```

Expected: All tests PASS. `test_local_state.py` exercises the new cache_dir-based API; the existing hbedit.py call sites compile cleanly because all of them now pass `cd` derived from the state dict.

- [ ] **Step 6: Commit**

```bash
git add skills/hbedit/scripts/local_state.py skills/hbedit/scripts/hbedit.py tests/test_local_state.py
git commit -m "refactor(hbedit)!: local-state.json moves to ~/.hbedit/cache/<vault-id>/

local_state.py public API switches from (vault, ...) to (cache_dir, ...);
all callers in hbedit.py thread cache_dir derived from state[\"vaultId\"]
through their helpers. No behavior change beyond the file location."
```

---

## Task 6: Move `_sidecar_path` to use `cache_dir`

**Goal:** Move the ProseMirror block-ID cache from `.hbedit/sidecar/` to `~/.hbedit/cache/<vault-id>/sidecar/`. Touches only `hbedit.py`.

**Files:**
- Modify: `skills/hbedit/scripts/hbedit.py`

(No test changes needed — `_sidecar_path` is an internal helper with no dedicated unit test; its behavior is covered by integration tests run in Task 11.)

- [ ] **Step 1: Replace `_sidecar_path` to take `cache_dir`**

In `skills/hbedit/scripts/hbedit.py`, replace `_sidecar_path` (lines 86–89):

```python
def _sidecar_path(vault, card_id):
    d = os.path.join(vault, ".hbedit", "sidecar")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, card_id + ".json")
```

With:

```python
def _sidecar_path(cache_dir, card_id):
    """ProseMirror block-ID cache path for `card_id` in this vault's
    per-machine cache directory."""
    d = os.path.join(cache_dir, "sidecar")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, card_id + ".json")
```

- [ ] **Step 2: Update every `_sidecar_path` call site in `hbedit.py`**

`_sidecar_path` is called from (line numbers from post-Task-5 hbedit.py):

- `_push_create` (used to be `_sidecar_path(vault, card_id)`)
- `_push_update` (twice — read + write)
- `pull_first_time` (write)
- `_baseline_established` (write)
- `_write_remote_and_baseline` (write)
- `_handle_conflict` (write)

At each site replace `_sidecar_path(vault, card_id)` with `_sidecar_path(cd, card_id)` where `cd` is the cache_dir variable threaded in via Task 5.

- [ ] **Step 3: Run all tests**

```bash
python3 -m pytest tests/ -v
```

Expected: All tests PASS (no signature change visible from tests; only call-site path computation differs).

- [ ] **Step 4: Manual sanity smoke**

```bash
cd /tmp && rm -rf hbedit-smoke && mkdir hbedit-smoke && cd hbedit-smoke
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py init
ls -la .hbedit/                        # expected: state.json only
ls -la ~/.hbedit/cache/                 # expected: a <uuid>/ subdirectory
cat .hbedit/state.json                  # expected: schemaVersion 3 + vaultId + empty files
cd / && rm -rf /tmp/hbedit-smoke
```

Expected: `.hbedit/` contains only `state.json` (no `local-state.json`, no `sidecar/`, no `.gitignore`). `~/.hbedit/cache/<uuid>/` exists.

- [ ] **Step 5: Commit**

```bash
git add skills/hbedit/scripts/hbedit.py
git commit -m "refactor(hbedit)!: sidecar cache moves to ~/.hbedit/cache/<vault-id>/sidecar/

_sidecar_path now takes cache_dir (already threaded through callers from
the previous commit). No project-tree files written by sidecar code
anymore."
```

---

## Task 7: Replace `find_vault_root + load_state` pairs with `find()`

**Goal:** Tidy up `hbedit.py` so each command uses one `vaultlib.find(path)` call returning a `VaultInfo` instead of a `find_vault_root + load_state + cache_dir(...)` triple. Pure refactor — no behavior change.

**Files:**
- Modify: `skills/hbedit/scripts/hbedit.py`

- [ ] **Step 1: Replace the idiom in `push()`**

In `skills/hbedit/scripts/hbedit.py`, in `push()` (lines 111–142), replace the vault-lookup block:

```python
    vault = vaultlib.find_vault_root(path)
    if vault is None:
        return errors.emit_error(
            "push", errors.NOT_IN_VAULT, path=path,
            detail="%s is not inside an hbedit vault. Run `hb init` in "
                   "the project root." % path), 2
    rel = _resolve_vault_relative(vault, path)

    try:
        state = vaultlib.load_state(vault)
    except vaultlib.StateSchemaError as exc:
        return errors.emit_error("push", errors.STATE_SCHEMA_UNSUPPORTED,
                                 detail=str(exc)), 2
    except vaultlib.StateCorruptError as exc:
        return errors.emit_error("push", errors.STATE_CORRUPT,
                                 detail=str(exc)), 2

    cd = vaultlib.cache_dir(state["vaultId"])
```

With:

```python
    try:
        info = vaultlib.find(path)
    except vaultlib.StateSchemaError as exc:
        return errors.emit_error("push", errors.STATE_SCHEMA_UNSUPPORTED,
                                 detail=str(exc)), 2
    except vaultlib.StateCorruptError as exc:
        return errors.emit_error("push", errors.STATE_CORRUPT,
                                 detail=str(exc)), 2
    if info is None:
        return errors.emit_error(
            "push", errors.NOT_IN_VAULT, path=path,
            detail="%s is not inside an hbedit vault. Run `hb init` in "
                   "the project root." % path), 2
    vault, state, cd = info.root, info.state, info.cache_dir
    rel = _resolve_vault_relative(vault, path)
```

- [ ] **Step 2: Apply the same refactor to `pull_first_time` (lines 243–305), `pull_smart` (lines 307–397), and `_tag_op` (lines 452–531)**

In each function, replace the `vault = ... or vaultlib.find_vault_root(os.getcwd())` + `load_state(...)` + `cd = vaultlib.cache_dir(state["vaultId"])` triple with the `try / except / info is None` pattern shown above. Adjust the fallback when `path` doesn't enclose a vault — call `vaultlib.find(path)` first, then if it returns `None` try `vaultlib.find(os.getcwd())` before reporting `NOT_IN_VAULT` (matches existing pull/tag behavior).

For example, `pull_first_time` becomes:

```python
def pull_first_time(card_id, path):
    """Implement `hb pull <cardId> <path>` — first-time pull to a new path."""
    try:
        info = vaultlib.find(path) or vaultlib.find(os.getcwd())
    except vaultlib.StateSchemaError as exc:
        return errors.emit_error("pull", errors.STATE_SCHEMA_UNSUPPORTED,
                                 detail=str(exc)), 2
    except vaultlib.StateCorruptError as exc:
        return errors.emit_error("pull", errors.STATE_CORRUPT,
                                 detail=str(exc)), 2
    if info is None:
        return errors.emit_error(
            "pull", errors.NOT_IN_VAULT, path=path,
            detail="no .hbedit/ found at or above %s" % path), 2
    vault, state, cd = info.root, info.state, info.cache_dir
    rel = _resolve_vault_relative(vault, path)
    # ... rest of function unchanged, but uses `cd` for local_state /
    # sidecar paths.
```

- [ ] **Step 3: Run all tests**

```bash
python3 -m pytest tests/ -v
```

Expected: All tests PASS (refactor preserves behavior; no test changes needed).

- [ ] **Step 4: Commit**

```bash
git add skills/hbedit/scripts/hbedit.py
git commit -m "refactor(hbedit): use vault.find() for all command entry points

Each command was doing find_vault_root + load_state + cache_dir(...)
by hand. Collapse into a single vault.find() returning VaultInfo so
the cache_dir derivation has one home."
```

---

## Task 8: Add cache-line to `hb doctor` output

**Goal:** When `hb doctor` runs inside a vault, report the per-machine cache directory and whether it exists. Skipped silently outside vaults (doctor must still work without a vault).

**Files:**
- Modify: `skills/hbedit/scripts/hbedit.py`
- Test: `tests/test_doctor.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_doctor.py`, append a new test class for the cache-reporting helper. The whole `doctor()` function calls real `heptabase` CLI which can't run in tests; isolate the new logic in a helper that tests CAN reach:

```python
import os
import tempfile
import sys
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
            # _doctor_cache_line takes the cwd and returns a string
            # (possibly empty if not in a vault).
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
```

- [ ] **Step 2: Run test, expect failure**

```bash
python3 -m pytest tests/test_doctor.py::TestDoctorCacheLine -v
```

Expected: FAIL — `AttributeError: module 'hbedit' has no attribute '_doctor_cache_line'`.

- [ ] **Step 3: Add the helper and wire it into `doctor()`**

In `skills/hbedit/scripts/hbedit.py`, after `_now_iso` (around line 84), add:

```python
def _doctor_cache_line(cwd):
    """Return ` cache: <path> (exists: yes|no)` when cwd is inside a vault.
    Returns "" when cwd has no enclosing vault, so doctor still works
    outside any project."""
    try:
        info = vaultlib.find(cwd)
    except (vaultlib.StateSchemaError, vaultlib.StateCorruptError):
        return ""
    if info is None:
        return ""
    exists = "yes" if os.path.isdir(info.cache_dir) else "no"
    return "cache: %s (exists: %s)" % (info.cache_dir, exists)
```

Then update `doctor()` (lines 42–68) so the success branch appends the cache line into the `detail` string. Replace the final `return errors.emit_ok(...)` block:

```python
    return errors.emit_ok("doctor",
                          detail="heptabase %s, desktop app reachable"
                                 % version), 0
```

With:

```python
    summary = "heptabase %s, desktop app reachable" % version
    cache_line = _doctor_cache_line(os.getcwd())
    if cache_line:
        summary = summary + "\n" + cache_line
    return errors.emit_ok("doctor", detail=summary), 0
```

- [ ] **Step 4: Run tests, expect pass**

```bash
python3 -m pytest tests/ -v
```

Expected: All tests PASS. `test_doctor.py::TestDoctorCacheLine` is now green.

- [ ] **Step 5: Commit**

```bash
git add skills/hbedit/scripts/hbedit.py tests/test_doctor.py
git commit -m "feat(hbedit): hb doctor reports per-vault cache directory

When run inside a vault, doctor appends a 'cache: <path> (exists: y/n)'
line so multi-machine sync debugging starts with cache visibility for
free. Silent outside a vault (doctor still works without a project)."
```

---

## Task 9: Update `SKILL.md` for v3

**Goal:** Replace v2 vault-layout references with v3. Drop `.gitignore` mentions. Note `vaultId`.

**Files:**
- Modify: `skills/hbedit/SKILL.md`

- [ ] **Step 1: Update the description frontmatter (optional, only if needed)**

Inspect line 3 (the `description:` field). It currently mentions `.hbedit/state.json`. Keep that mention but ensure nothing implies per-machine files in the project tree. If the description mentions gitignored caches or "files travel via git", verify it remains accurate for v3 (binding still travels via git; only the binding does).

If no change needed, skip this step.

- [ ] **Step 2: Update the "Vault layout" section**

Locate the table around line 41 with rows for "Public state", "Local cache", "Block cache". Replace with:

```markdown
| Public state | `.hbedit/state.json` | `path → {cardId, tags}` registry plus `vaultId` (UUIDv4, set at `hb init`) | Yes — commit |
| Local cache | `~/.hbedit/cache/<vault-id>/local-state.json` | `path → {contentMd5, localMd5, syncedAt}` per-machine | Lives outside the project; not tracked |
| Block cache | `~/.hbedit/cache/<vault-id>/sidecar/<cardId>.json` | ProseMirror JSON for block-ID transplant | Lives outside the project; not tracked |
```

- [ ] **Step 3: Remove `.gitignore` references**

Search the file for `.gitignore` mentions (likely in the `hb init` description, and any "what gets created" prose). Delete those mentions — v3 `hb init` never touches `.gitignore`.

The `hb init` section (around line 77) currently says something like "Initialize a vault in the current directory. Creates `.hbedit/state.json`...". Update to mention `vaultId`:

```markdown
Initialize a vault in the current directory. Creates `.hbedit/state.json`
with a fresh `vaultId` (UUIDv4) and an empty `files` registry. Also
ensures the per-machine cache directory `~/.hbedit/cache/<vault-id>/`
exists. No `.gitignore` is written — v3 keeps all per-machine state
out of the project tree.
```

- [ ] **Step 4: Update the vault-discovery sentence**

The sentence at line 49 ("A directory is an hbedit vault if it or any ancestor contains `.hbedit/`.") needs tightening to match the discovery fix:

```markdown
A directory is an hbedit vault if it or any ancestor contains
`.hbedit/state.json`. The state file (not just the directory) is what
identifies a vault — an empty `.hbedit/` anywhere does not count.
```

- [ ] **Step 5: Update the `state-schema-unsupported` error row**

Locate the row mentioning `state.json` has `schemaVersion` other than 2 (around line 302). Replace `2` with `3`. Update the remediation to mention the lack of v2/v3 migration support:

```markdown
| `state-schema-unsupported` | `state.json` has `schemaVersion` other than 3 | 1. Inform user the state file is from an incompatible older version. 2. Advise running `hb init` in a fresh directory, or removing `.hbedit/` and starting over. v3 does not migrate v2 state files automatically. 3. Do not run any other hb command until resolved. |
```

- [ ] **Step 6: Commit**

```bash
git add skills/hbedit/SKILL.md
git commit -m "docs(hbedit): SKILL.md for v3 — global cache layout, vaultId, no .gitignore

Vault-layout table now shows the per-machine caches living under
~/.hbedit/cache/<vault-id>/. hb init creates vaultId and never writes
.gitignore. Vault discovery requires state.json file, not just dir."
```

---

## Task 10: Cleanup local v1/v2 test artifacts

**Goal:** Wipe the pre-v2 residue at HeptaSync repo root and delete the v2 testing log. Out-of-band housekeeping but bundled with the v3 branch.

**Files:**
- Delete: `.hbedit/` (entire untracked directory at HeptaSync repo root)
- Delete: `TESTING-NOTES.md` (tracked, 388 lines)

- [ ] **Step 1: Confirm what's about to be deleted**

```bash
ls -la .hbedit/
cat .hbedit/state.json
git status -- TESTING-NOTES.md
```

Expected output: `.hbedit/state.json` shows the pre-v2 shape (`{"cards": {"330c7cd7-...": {"tags": []}}}`), `.hbedit/sidecar/` has one sidecar JSON. `TESTING-NOTES.md` is tracked (no modification flag in status).

- [ ] **Step 2: Delete the untracked residue**

```bash
rm -rf .hbedit/
```

- [ ] **Step 3: Remove the tracked testing log**

```bash
git rm TESTING-NOTES.md
```

- [ ] **Step 4: Verify status**

```bash
git status --short
```

Expected: `TESTING-NOTES.md` shown as `D ` (staged deletion). No `.hbedit/` line (it's gone).

- [ ] **Step 5: Commit**

```bash
git commit -m "chore(hbedit): remove pre-v2 .hbedit/ residue and v2 testing notes

The .hbedit/ at HeptaSync repo root was leftover from very early v1
testing (still using the pre-v2 cards-keyed-by-id shape). The 388-line
TESTING-NOTES.md captured the v2 manual-test pass; the test results
section already lives in the v2 spec / plan, and the design discussion
is preserved in git history. Per v3 spec out-of-band cleanup section.

Remote Heptabase card 330c7cd7-... is handled separately by the user."
```

---

## Task 11: End-to-end verification matching spec acceptance criteria

**Goal:** Run a clean smoke test confirming each of the 8 acceptance criteria from the spec.

**Files:** None modified — verification only.

- [ ] **Step 1: AC #1 — `hb init` writes v3 schema, vaultId, no .gitignore**

```bash
cd /tmp && rm -rf hbedit-ac && mkdir hbedit-ac && cd hbedit-ac
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py init
cat .hbedit/state.json
ls -la .gitignore 2>/dev/null && echo "FAIL: .gitignore exists" || echo "OK: no .gitignore"
ls -la ~/.hbedit/cache/
```

Expected:
- `state.json` shows `"schemaVersion": 3`, `"vaultId": "<uuid>"`, `"files": {}`.
- `.gitignore` does not exist → prints `OK: no .gitignore`.
- `~/.hbedit/cache/<uuid>/sidecar/` exists.

- [ ] **Step 2: AC #2 — `hb push` writes only state.json under .hbedit/, caches go global**

Still in `/tmp/hbedit-ac`:

```bash
mkdir docs && echo "# Hello\n\nFirst paragraph." > docs/foo.md
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py push docs/foo.md
ls -la .hbedit/                       # expected: state.json only
ls -la ~/.hbedit/cache/*/              # expected: local-state.json + sidecar/
cat .hbedit/state.json                 # expected: state.files["docs/foo.md"] populated
```

Expected:
- `.hbedit/` contains only `state.json`. No `local-state.json`, no `sidecar/`.
- `~/.hbedit/cache/<uuid>/` contains `local-state.json` and `sidecar/<cardId>.json`.
- `state.json` now has the new file binding.

Note the cardId. We'll trash it at the end.

- [ ] **Step 3: AC #4 — vault discovery skips empty .hbedit/ at $HOME**

```bash
cd /tmp && mkdir -p outside_vault_test && cd outside_vault_test && echo "# Not in a vault" > foo.md
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py push foo.md
```

Expected: JSON output with `"error": "not-in-vault"`. Critically NOT `state-corrupt` (which is what v2 with the latent bug would have produced when walking up to `$HOME` and seeing `~/.hbedit/cache/...`).

- [ ] **Step 4: AC #5 — v2 schema rejected**

```bash
cd /tmp/hbedit-ac
# Save and corrupt the schemaVersion to 2.
cp .hbedit/state.json .hbedit/state.json.bak
python3 -c "import json; d = json.load(open('.hbedit/state.json')); d['schemaVersion']=2; json.dump(d, open('.hbedit/state.json','w'))"
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py push docs/foo.md
mv .hbedit/state.json.bak .hbedit/state.json
```

Expected: JSON output with `"error": "state-schema-unsupported"` mentioning `schemaVersion is 2, expected 3`. Final `mv` restores the v3 state.json.

- [ ] **Step 5: AC #6 — `hb doctor` cache line**

```bash
cd /tmp/hbedit-ac
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py doctor
```

Expected: JSON output with `"detail"` containing two lines — the heptabase version line AND `cache: /Users/<you>/.hbedit/cache/<uuid>/ (exists: yes)`.

```bash
cd /tmp/outside_vault_test
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py doctor
```

Expected: only the heptabase version line in `detail`, no cache line (outside any vault).

- [ ] **Step 6: AC #7 — unit test suite green**

```bash
cd /Users/leiweicheng/Desktop/HeptaSync
python3 -m pytest tests/ -v
```

Expected: All tests PASS. No skips other than ones marked from earlier work.

- [ ] **Step 7: AC #3 — multi-machine sync simulation**

```bash
cd /tmp && rm -rf machine_a machine_b && mkdir machine_a machine_b
cd machine_a
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py init
mkdir docs && echo "# Multi-machine test\n\nMachine A version." > docs/mm.md
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py push docs/mm.md
# Capture the cardId from state.json:
CARD=$(python3 -c "import json; d = json.load(open('.hbedit/state.json')); print(list(d['files'].values())[0]['cardId'])")
echo "cardId: $CARD"
# Simulate clone to machine_b: copy the project tree (which includes state.json).
cp -r .hbedit /tmp/machine_b/
cp -r docs /tmp/machine_b/
cd /tmp/machine_b
# Clear this machine's cache for that vault-id to mimic a fresh clone:
VAULT_ID=$(python3 -c "import json; print(json.load(open('.hbedit/state.json'))['vaultId'])")
rm -rf ~/.hbedit/cache/$VAULT_ID
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py pull docs/mm.md
```

Expected: Final pull returns `"action": "baseline-established"`. `~/.hbedit/cache/<vault-id>/local-state.json` is populated. The local `docs/mm.md` is unchanged.

- [ ] **Step 8: Cleanup test artifacts and remote cards**

```bash
cd /
rm -rf /tmp/hbedit-ac /tmp/outside_vault_test /tmp/machine_a /tmp/machine_b
# Trash the test cards created during AC #2 and AC #3 — replace with the
# real cardIds captured during the run.
# heptabase card trash <cardId-from-ac2>
# heptabase card trash <cardId-from-ac3>
```

Expected: clean temp tree. Manually trash the two real Heptabase cards created during AC #2 and AC #3 (their IDs were printed during the runs above).

- [ ] **Step 9: Confirm AC #8 — final repo state**

```bash
cd /Users/leiweicheng/Desktop/HeptaSync
git status --short
ls -la .hbedit/ 2>/dev/null && echo "FAIL: .hbedit/ still exists" || echo "OK: .hbedit/ gone"
ls TESTING-NOTES.md 2>/dev/null && echo "FAIL: TESTING-NOTES.md still exists" || echo "OK: TESTING-NOTES.md gone"
```

Expected: `git status --short` is clean (modulo any pre-existing modifications from before this work). `.hbedit/` and `TESTING-NOTES.md` both gone.

- [ ] **Step 10: No commit — verification is read-only**

This task produces no commit. The deliverable is the verified-green run.

---

## Plan Summary

11 tasks, each committable:

1. Add `cache_dir()` helper (additive)
2. Add `VaultInfo` + `find()` (additive)
3. Tighten `find_vault_root` to require state.json file (bug fix)
4. Bump SCHEMA_VERSION 2→3, write vaultId, drop .gitignore (breaking schema change)
5. Refactor local_state.py to take cache_dir; thread cd through hbedit.py callers (breaking API)
6. Move `_sidecar_path` to use cache_dir (internal refactor)
7. Replace find_vault_root + load_state pairs with find() (cleanup)
8. Add `cache:` line to `hb doctor` output (feature)
9. Update SKILL.md for v3 (docs)
10. Cleanup local v1/v2 artifacts (housekeeping)
11. End-to-end acceptance verification (no commit)

Total expected commits: 10. End state matches all 8 acceptance criteria in the spec.
