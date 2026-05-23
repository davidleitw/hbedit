# hbedit v2 redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hbedit v0.1's frontmatter-based card↔file binding with a three-layer state-file design (`state.json` in git, `local-state.json` + `sidecar/` per-machine), exposing 7 JSON-output commands with stable error codes for AI-agent consumption.

**Architecture:** `.md` files become pure markdown content (no embedded metadata). `.hbedit/state.json` holds the `path→cardId` registry (committed to git). `.hbedit/local-state.json` holds per-machine sync cache (gitignored). `hb pull` does a *smart compare* between local and remote before overwriting, preventing data loss on fresh-clone scenarios.

**Tech Stack:** Python 3 stdlib only (no external deps). Heptabase desktop's `heptabase` CLI as the sole upstream API. Markdown content; ProseMirror JSON for transport.

**Reference spec:** [`docs/superpowers/specs/2026-05-24-hbedit-redesign-design.md`](../specs/2026-05-24-hbedit-redesign-design.md)

---

## File structure

After this plan completes, `skills/hbedit/scripts/` looks like:

```
errors.py        (NEW)    Error code constants + JSON output helpers
vault.py         (REWRITE) state.json v2 + init_vault + file-map operations
local_state.py   (NEW)    local-state.json read/write/get/set
hbedit.py        (REWRITE) Main entry, all command implementations, dispatch
htb.py           (unchanged) Heptabase CLI wrapper
pm2md.py         (unchanged) ProseMirror → Markdown converter
transplant.py    (unchanged) Block-ID transplant
tagsync.py       (TRIM)   Keep find_similar_tag, drop merge_tags
frontmatter.py   (DELETE) entire file gone
```

Test files:

```
tests/test_errors.py        (NEW)
tests/test_vault.py         (REWRITE)
tests/test_local_state.py   (NEW)
tests/test_tagsync.py       (TRIM)
tests/test_pm2md.py         (unchanged)
tests/test_doctor.py        (probably unchanged)
tests/test_htb_args.py      (unchanged)
tests/test_frontmatter.py   (DELETE)
```

Plus:

```
skills/hbedit/SKILL.md      (REWRITE end-to-end)
.gitignore                  (UPDATE: add .hbedit/local-state.json + .hbedit/sidecar/)
```

---

## Task ordering rationale

Pure-function modules first(errors / vault / local_state / tagsync trim)so they can be TDD'd with unit tests. Then the command implementations layer on top. SKILL.md is last because it documents the final CLI shape. The manual test suite runs after everything else.

The old `frontmatter.py` stays on disk(but unused)until task 11 deletes it — keeps the working tree consistent during the rewrite. Same for `tests/test_frontmatter.py`.

---

### Task 1: Create `errors.py` — error code constants + JSON output helpers

**Files:**
- Create: `skills/hbedit/scripts/errors.py`
- Test: `tests/test_errors.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_errors.py`:

```python
"""Tests for the errors module."""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "skills", "hbedit", "scripts"))

import errors


def test_error_codes_constants_exist():
    # Every code referenced by SKILL.md / spec must be a module-level constant.
    expected = {
        "CLI_MISSING", "CLI_VERSION_UNSUPPORTED", "APP_NOT_RUNNING",
        "NOT_IN_VAULT", "FILE_NOT_FOUND", "PATH_EXISTS_UNTRACKED",
        "PATH_NOT_TRACKED", "NO_BASELINE", "CONTENT_CONFLICT",
        "TAG_AMBIGUITY", "CARD_NOT_FOUND", "TAG_NOT_ON_CARD",
        "CARDID_ALREADY_TRACKED", "STATE_SCHEMA_UNSUPPORTED",
        "STATE_CORRUPT", "VAULT_NESTED", "LOCAL_HAS_CHANGES",
    }
    for name in expected:
        assert hasattr(errors, name), name


def test_error_codes_are_kebab_case():
    # Constants hold the wire string used in JSON output.
    assert errors.NO_BASELINE == "no-baseline"
    assert errors.PATH_NOT_TRACKED == "path-not-tracked"
    assert errors.CARDID_ALREADY_TRACKED == "cardId-already-tracked"


def test_emit_ok():
    s = errors.emit_ok("push", action="updated", cardId="abc", path="p.md")
    obj = json.loads(s)
    assert obj == {
        "command": "push", "status": "ok",
        "action": "updated", "cardId": "abc", "path": "p.md",
    }


def test_emit_error():
    s = errors.emit_error("pull", errors.NO_BASELINE, path="p.md", detail="msg")
    obj = json.loads(s)
    assert obj == {
        "command": "pull", "status": "error",
        "code": "no-baseline", "path": "p.md", "detail": "msg",
    }


def test_emit_error_skips_none_fields():
    s = errors.emit_error("init", errors.VAULT_NESTED, detail="hi", path=None)
    obj = json.loads(s)
    assert "path" not in obj
    assert obj["detail"] == "hi"
```

- [ ] **Step 2: Run test, verify it fails**

```
cd /Users/leiweicheng/Desktop/HeptaSync
python3 -m pytest tests/test_errors.py -v
```

Expected: ImportError or ModuleNotFoundError for `errors`.

- [ ] **Step 3: Write `errors.py`**

Create `skills/hbedit/scripts/errors.py`:

```python
"""Stable error-code identifiers and JSON output helpers for hbedit.

Every CLI command outputs a JSON object to stdout (one per invocation).
Agents key off `status` and `code` to decide what to do — see SKILL.md
for per-code SOPs.
"""
from __future__ import annotations

import json


# -- error codes -----------------------------------------------------------
# Doctor / environment
CLI_MISSING = "cli-missing"
CLI_VERSION_UNSUPPORTED = "cli-version-unsupported"
APP_NOT_RUNNING = "app-not-running"

# Vault / filesystem
NOT_IN_VAULT = "not-in-vault"
VAULT_NESTED = "vault-nested"
FILE_NOT_FOUND = "file-not-found"
PATH_EXISTS_UNTRACKED = "path-exists-untracked"

# State files
STATE_SCHEMA_UNSUPPORTED = "state-schema-unsupported"
STATE_CORRUPT = "state-corrupt"

# Path tracking
PATH_NOT_TRACKED = "path-not-tracked"
CARDID_ALREADY_TRACKED = "cardId-already-tracked"

# Sync / conflict
NO_BASELINE = "no-baseline"
CONTENT_CONFLICT = "content-conflict"
LOCAL_HAS_CHANGES = "local-has-changes"

# Card / tag
CARD_NOT_FOUND = "card-not-found"
TAG_AMBIGUITY = "tag-ambiguity"
TAG_NOT_ON_CARD = "tag-not-on-card"


# -- JSON output helpers ---------------------------------------------------
def _serialize(obj):
    """Emit a single-line JSON string with stable key order, UTF-8 safe."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def emit_ok(command, **fields):
    """Produce the success JSON string for a command. Drop None fields."""
    out = {"command": command, "status": "ok"}
    for k, v in fields.items():
        if v is not None:
            out[k] = v
    return _serialize(out)


def emit_error(command, code, **fields):
    """Produce the error JSON string for a command. Drop None fields."""
    out = {"command": command, "status": "error", "code": code}
    for k, v in fields.items():
        if v is not None:
            out[k] = v
    return _serialize(out)
```

- [ ] **Step 4: Run test to verify it passes**

```
python3 -m pytest tests/test_errors.py -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add skills/hbedit/scripts/errors.py tests/test_errors.py
git commit -m "feat(hbedit): add errors module with stable codes and JSON helpers

Centralizes error-code identifiers and JSON output formatting for the
v2 redesign. Codes are kebab-case strings matching the SKILL.md SOPs."
```

---

### Task 2: Rewrite `vault.py` — state.json v2 schema + init_vault

**Files:**
- Modify: `skills/hbedit/scripts/vault.py` (heavy rewrite, ~150 lines)
- Test: `tests/test_vault.py` (rewrite)

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_vault.py` contents with:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```
python3 -m pytest tests/test_vault.py -v
```

Expected: most fail because the API doesn't exist yet.

- [ ] **Step 3: Rewrite `vault.py`**

Replace `skills/hbedit/scripts/vault.py` contents with:

```python
"""hbedit v2 — vault discovery, state.json (v2 schema), init.

The vault root is the nearest ancestor directory containing `.hbedit/`
(same idea as git locating `.git/`). state.json maps `path -> {cardId,
tags}`; it's the single source of truth for which `.md` is bound to
which card.
"""
from __future__ import annotations

import json
import os
import tempfile

STATE_DIR = ".hbedit"
STATE_FILE = "state.json"
SCHEMA_VERSION = 2
GITIGNORE_LINES = [".hbedit/local-state.json", ".hbedit/sidecar/"]


# -- exceptions ------------------------------------------------------------
class StateSchemaError(Exception):
    """state.json has a schemaVersion other than 2."""


class StateCorruptError(Exception):
    """state.json is unparseable JSON or violates invariants."""


class NestedVaultError(Exception):
    """init_vault called inside an existing vault's tree."""


class DuplicateCardIdError(Exception):
    """set_file_entry would map a cardId already used by another path."""


# -- vault discovery -------------------------------------------------------
def find_vault_root(start):
    """Walk up from `start` (a file or dir) to the dir holding `.hbedit/`.
    Returns the vault root path, or None if no vault encloses `start`."""
    d = os.path.abspath(start)
    if os.path.isfile(d):
        d = os.path.dirname(d)
    while True:
        if os.path.isdir(os.path.join(d, STATE_DIR)):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def _state_path(vault):
    return os.path.join(vault, STATE_DIR, STATE_FILE)


def _atomic_write(path, text):
    """Write to a temp file in the same dir, then rename. Prevents
    leaving a half-written state.json on a crash mid-write."""
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix=".hbedit-state-", dir=d)
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


# -- load / save -----------------------------------------------------------
def load_state(vault):
    """Return parsed state.json. Returns the empty-v2 skeleton when the
    file is absent. Raises StateSchemaError on a wrong schemaVersion and
    StateCorruptError on malformed JSON or invariant violations."""
    path = _state_path(vault)
    if not os.path.exists(path):
        return {"schemaVersion": SCHEMA_VERSION, "files": {}}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except ValueError as exc:
        raise StateCorruptError("state.json is not valid JSON: %s" % exc)
    if not isinstance(data, dict):
        raise StateCorruptError("state.json must be a JSON object")
    if data.get("schemaVersion") != SCHEMA_VERSION:
        raise StateSchemaError(
            "state.json schemaVersion is %r, expected %d"
            % (data.get("schemaVersion"), SCHEMA_VERSION))
    if not isinstance(data.get("files"), dict):
        raise StateCorruptError("state.json `files` must be an object")
    # invariant: no two paths share a cardId
    seen = {}
    for p, entry in data["files"].items():
        if not isinstance(entry, dict):
            raise StateCorruptError("files[%r] must be an object" % p)
        cid = entry.get("cardId")
        if cid in seen:
            raise StateCorruptError(
                "duplicate cardId %s on paths %s and %s" % (cid, seen[cid], p))
        seen[cid] = p
    return data


def save_state(vault, state):
    """Atomically write state.json. Ensures `.hbedit/` exists."""
    os.makedirs(os.path.join(vault, STATE_DIR), exist_ok=True)
    _atomic_write(_state_path(vault),
                  json.dumps(state, ensure_ascii=False, indent=2))


# -- file entry ops --------------------------------------------------------
def get_file_entry(vault, path):
    """Return {cardId, tags} for `path` (relative to vault), or None."""
    state = load_state(vault)
    return state["files"].get(path)


def set_file_entry(vault, path, card_id, tags):
    """Register `path -> {cardId, tags}`. Raises DuplicateCardIdError
    if `card_id` is already mapped to a different path."""
    state = load_state(vault)
    for p, entry in state["files"].items():
        if p != path and entry.get("cardId") == card_id:
            raise DuplicateCardIdError(
                "cardId %s already mapped to %s" % (card_id, p))
    state["files"][path] = {"cardId": card_id, "tags": list(tags)}
    save_state(vault, state)


def remove_file_entry(vault, path):
    """Drop the entry for `path`. No-op if not present."""
    state = load_state(vault)
    if path in state["files"]:
        del state["files"][path]
        save_state(vault, state)


def find_path_by_card_id(vault, card_id):
    """Return the path mapped to `card_id`, or None."""
    state = load_state(vault)
    for p, entry in state["files"].items():
        if entry.get("cardId") == card_id:
            return p
    return None


# -- init_vault ------------------------------------------------------------
def init_vault(cwd):
    """Create a vault at `cwd`. Returns one of:
       - "created" — vault freshly created
       - "already-initialized" — cwd already has its own .hbedit/
    Raises NestedVaultError if cwd is inside another vault's tree."""
    own = os.path.join(cwd, STATE_DIR)
    if os.path.isdir(own):
        # cwd is the vault root already
        return "already-initialized"
    # check ancestors for an existing vault
    ancestor = find_vault_root(cwd)
    if ancestor is not None:
        raise NestedVaultError("vault already exists at %s" % ancestor)
    os.makedirs(own)
    save_state(cwd, {"schemaVersion": SCHEMA_VERSION, "files": {}})
    _update_gitignore(cwd)
    return "created"


def _update_gitignore(cwd):
    """Append our gitignore lines if not present. Creates .gitignore if
    absent. Idempotent: lines are only added if missing."""
    path = os.path.join(cwd, ".gitignore")
    existing = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            existing = f.read()
    needed = []
    existing_lines = {line.strip() for line in existing.splitlines()}
    for line in GITIGNORE_LINES:
        if line not in existing_lines:
            needed.append(line)
    if not needed:
        return
    sep = "" if not existing or existing.endswith("\n") else "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(sep + "\n".join(needed) + "\n")
```

- [ ] **Step 4: Run tests to verify they pass**

```
python3 -m pytest tests/test_vault.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add skills/hbedit/scripts/vault.py tests/test_vault.py
git commit -m "feat(hbedit): rewrite vault.py with state.json v2 schema

- New path->cardId file map (was per-cardId-tag-base in v1)
- Atomic writes via temp+rename
- StateSchemaError / StateCorruptError / DuplicateCardIdError /
  NestedVaultError exceptions for the new error code surface
- init_vault creates .hbedit/, seeds state.json, idempotently updates
  .gitignore"
```

---

### Task 3: Create `local_state.py` — per-machine sync cache

**Files:**
- Create: `skills/hbedit/scripts/local_state.py`
- Test: `tests/test_local_state.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_local_state.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```
python3 -m pytest tests/test_local_state.py -v
```

Expected: ModuleNotFoundError for `local_state`.

- [ ] **Step 3: Write `local_state.py`**

Create `skills/hbedit/scripts/local_state.py`:

```python
"""hbedit v2 — per-machine sync cache (`.hbedit/local-state.json`).

This file is gitignored. It records, for each tracked path:
- contentMd5: the remote ProseMirror md5 at last sync (push lock)
- localMd5:   the md5 of the local .md body at last sync (used to detect
              uncommitted local changes before a pull would overwrite)
- syncedAt:   ISO-8601 UTC timestamp of the last sync

Corruption recovery: unlike state.json (authoritative, fail-loud on
corruption), local-state.json is rebuildable by re-pulling each tracked
card, so we silently treat a corrupt file as empty.
"""
from __future__ import annotations

import json
import os
import tempfile

LOCAL_STATE_FILE = "local-state.json"
SCHEMA_VERSION = 1


def _path(vault):
    return os.path.join(vault, ".hbedit", LOCAL_STATE_FILE)


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


def load_local_state(vault):
    """Return the parsed file, or the empty skeleton if missing or corrupt."""
    p = _path(vault)
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


def save_local_state(vault, state):
    os.makedirs(os.path.join(vault, ".hbedit"), exist_ok=True)
    _atomic_write(_path(vault),
                  json.dumps(state, ensure_ascii=False, indent=2))


def get_local_entry(vault, path):
    """Return {contentMd5, localMd5, syncedAt} for path, or None."""
    return load_local_state(vault)["files"].get(path)


def set_local_entry(vault, path, content_md5, local_md5, synced_at):
    state = load_local_state(vault)
    state["files"][path] = {
        "contentMd5": content_md5,
        "localMd5": local_md5,
        "syncedAt": synced_at,
    }
    save_local_state(vault, state)


def remove_local_entry(vault, path):
    state = load_local_state(vault)
    if path in state["files"]:
        del state["files"][path]
        save_local_state(vault, state)
```

- [ ] **Step 4: Run tests to verify they pass**

```
python3 -m pytest tests/test_local_state.py -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add skills/hbedit/scripts/local_state.py tests/test_local_state.py
git commit -m "feat(hbedit): add local_state.py for per-machine sync cache

Stores contentMd5 + localMd5 + syncedAt per tracked path. Tolerates
corrupt JSON (returns empty) because the cache is rebuildable by
re-pulling — contrast with state.json which fails loud on corruption."
```

---

### Task 4: Trim `tagsync.py` — drop `merge_tags`, keep `find_similar_tag`

**Files:**
- Modify: `skills/hbedit/scripts/tagsync.py`
- Modify: `tests/test_tagsync.py`

- [ ] **Step 1: Update the test file to drop merge_tags tests**

Read the current `tests/test_tagsync.py` first to understand what to remove:

```
cat tests/test_tagsync.py
```

Replace its contents with(only `find_similar_tag` tests; drop any
`merge_tags` tests):

```python
"""Tests for tagsync.py (v2: only find_similar_tag survives)."""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "skills", "hbedit", "scripts"))

import tagsync


def test_exact_match_returns_none():
    assert tagsync.find_similar_tag("foo", ["foo", "bar"]) is None


def test_close_misspelling_returns_existing():
    assert tagsync.find_similar_tag("leetcod", ["leetcode", "other"]) == "leetcode"


def test_case_difference_is_caught():
    # Heptabase tags are case-sensitive; "Hbedit" vs "hbedit" would create
    # a near-duplicate, so we surface this.
    assert tagsync.find_similar_tag("Hbedit", ["hbedit"]) == "hbedit"


def test_far_returns_none():
    assert tagsync.find_similar_tag("xyz", ["completely-different-name"]) is None


def test_empty_existing():
    assert tagsync.find_similar_tag("anything", []) is None
```

- [ ] **Step 2: Replace `tagsync.py`**

Replace `skills/hbedit/scripts/tagsync.py` contents with:

```python
"""hbedit v2 — fuzzy-match guard for tag typos.

Tag merge logic moved into the command implementations as simple
fetch-modify-push (no 3-way merge in v2). What remains here is the
typo guard used by `hb tag add` to refuse near-duplicate tag names.
"""
from __future__ import annotations

import difflib


def find_similar_tag(name, existing, threshold=0.8):
    """If `name` is not a case-sensitive exact member of `existing` but is
    close to one (case-folded difflib ratio >= threshold), return that
    closest tag; otherwise return None.

    A case-only difference (e.g. "hbedit" vs "Hbedit") IS surfaced as a
    hit — Heptabase tag names are case-sensitive, so `tag add` on the
    wrong casing would spawn a near-duplicate.
    """
    if name in existing:
        return None
    low = name.lower()
    best, best_score = None, 0.0
    for candidate in existing:
        score = difflib.SequenceMatcher(None, low, candidate.lower()).ratio()
        if score > best_score:
            best, best_score = candidate, score
    return best if best_score >= threshold else None
```

- [ ] **Step 3: Run tests**

```
python3 -m pytest tests/test_tagsync.py -v
```

Expected: 5 tests pass.

- [ ] **Step 4: Commit**

```bash
git add skills/hbedit/scripts/tagsync.py tests/test_tagsync.py
git commit -m "refactor(hbedit): trim tagsync.py to only find_similar_tag

The v1 3-way merge_tags is unused in v2; tag commands do simple
fetch-modify-push of remote tags. Typo guard (find_similar_tag) is
still needed for tag-ambiguity errors."
```

---

### Task 5: Add `body_md5` helper to local_state(or wherever it fits)

To detect local divergence in smart pull, we need a stable md5 of the
local `.md` body. The smart-pull logic in `hbedit.py` will call this.
Put the helper next to where it's most used: `local_state.py`.

**Files:**
- Modify: `skills/hbedit/scripts/local_state.py`
- Modify: `tests/test_local_state.py`

- [ ] **Step 1: Add tests for `body_md5`**

Append to `tests/test_local_state.py`:

```python
def test_body_md5_deterministic():
    text = "# Hello\n\nWorld\n"
    a = local_state.body_md5(text)
    b = local_state.body_md5(text)
    assert a == b
    assert isinstance(a, str)
    assert len(a) == 32  # md5 hex


def test_body_md5_normalizes_line_endings():
    # Don't generate spurious diffs because of CRLF.
    a = local_state.body_md5("a\r\nb\r\n")
    b = local_state.body_md5("a\nb\n")
    assert a == b
```

- [ ] **Step 2: Add `body_md5` to `local_state.py`**

Append to `skills/hbedit/scripts/local_state.py`:

```python
import hashlib


def body_md5(text):
    """Stable md5 of a markdown body.

    Line endings are normalized to LF before hashing — local files may
    arrive via git with CRLF (Windows / autocrlf) but we want a single
    canonical hash. UTF-8 encoding is forced.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()
```

(Add the `import hashlib` at the top of the file alongside other imports.)

- [ ] **Step 3: Run tests**

```
python3 -m pytest tests/test_local_state.py -v
```

Expected: 6 tests pass (4 original + 2 new).

- [ ] **Step 4: Commit**

```bash
git add skills/hbedit/scripts/local_state.py tests/test_local_state.py
git commit -m "feat(hbedit): add body_md5 helper for local divergence detection

Used by smart pull to detect whether the working .md body has changed
since last sync. Normalizes line endings to LF before hashing so CRLF
git checkouts don't trigger spurious 'local-has-changes' errors."
```

---

### Task 6: Rewrite `hbedit.py` skeleton — argv dispatch + doctor

Begin the big rewrite. Land doctor first (smallest, mostly preserved
from v1). Subsequent tasks add the other commands.

**Files:**
- Modify: `skills/hbedit/scripts/hbedit.py` (complete rewrite, in stages)

- [ ] **Step 1: Replace `hbedit.py` with skeleton + doctor**

Replace `skills/hbedit/scripts/hbedit.py` with:

```python
#!/usr/bin/env python3
"""hbedit v2 — minimal CLI entry point.

  hb doctor                              preflight check
  hb init                                initialize a vault in cwd
  hb push <path>                         sync local edits to Heptabase
  hb pull <cardId> <path>                first-time pull of a card
  hb pull <path>                         smart-compare pull of a tracked path
  hb tag add <path> <name>               add a tag to the bound card
  hb tag remove <path> <name>            remove a tag from the bound card

UNOFFICIAL — talks only to the official `heptabase` CLI.
"""
from __future__ import annotations

import os
import shutil
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import errors                 # noqa: E402
import htb                    # noqa: E402


SUPPORTED_RANGE = "0.3."


def _version_supported(version):
    return bool(version) and version.strip().startswith(SUPPORTED_RANGE)


def doctor():
    """Returns the JSON output string for `hb doctor` and an exit code."""
    if shutil.which("heptabase") is None:
        return errors.emit_error("doctor", errors.CLI_MISSING,
                                 detail="heptabase CLI not found on PATH"), 2
    try:
        version = htb.version()
    except OSError as exc:
        return errors.emit_error("doctor", errors.CLI_MISSING,
                                 detail="could not run heptabase: %s" % exc), 2
    if not _version_supported(version):
        return errors.emit_error(
            "doctor", errors.CLI_VERSION_UNSUPPORTED,
            detail="heptabase %s is outside the supported %sx range"
                   % (version or "?", SUPPORTED_RANGE)), 2
    try:
        htb.card_list(limit=1)
    except htb.HtbError as exc:
        return errors.emit_error(
            "doctor", errors.APP_NOT_RUNNING,
            detail=htb.error_detail(exc)), 2
    except OSError as exc:
        return errors.emit_error("doctor", errors.CLI_MISSING,
                                 detail="could not run heptabase: %s" % exc), 2
    return errors.emit_ok("doctor",
                          detail="heptabase %s, desktop app reachable"
                                 % version), 0


def main(argv):
    if len(argv) == 2 and argv[1] == "doctor":
        out, rc = doctor()
        print(out)
        return rc
    # Other commands land in subsequent tasks.
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 2: Smoke test doctor**

```
python3 skills/hbedit/scripts/hbedit.py doctor
```

Expected (with Heptabase desktop running):
```
{"command":"doctor","status":"ok","detail":"heptabase 0.3.0, desktop app reachable"}
```

If Heptabase isn't running, expected:
```
{"command":"doctor","status":"error","code":"app-not-running","detail":"..."}
```

- [ ] **Step 3: Commit**

```bash
git add skills/hbedit/scripts/hbedit.py
git commit -m "feat(hbedit): start v2 rewrite — skeleton + doctor command

JSON-only output, error codes via the errors module. Other commands
land in follow-up commits — main() currently dispatches only doctor."
```

---

### Task 7: Implement `hb init`

**Files:**
- Modify: `skills/hbedit/scripts/hbedit.py`

- [ ] **Step 1: Add init function and dispatch**

Edit `skills/hbedit/scripts/hbedit.py`:

After the `import htb` line, add:

```python
import vault as vaultlib    # noqa: E402
```

After `doctor()`, add:

```python
def init(cwd):
    """Initialize a vault in `cwd`. Returns (json_output, exit_code)."""
    try:
        result = vaultlib.init_vault(cwd)
    except vaultlib.NestedVaultError as exc:
        return errors.emit_error("init", errors.VAULT_NESTED,
                                 detail=str(exc)), 2
    return errors.emit_ok("init", action=result), 0
```

In `main()`, before the fallthrough, add:

```python
    if len(argv) == 2 and argv[1] == "init":
        out, rc = init(os.getcwd())
        print(out)
        return rc
```

- [ ] **Step 2: Smoke test init**

```
mkdir -p /tmp/hbedit-smoke-task7
cd /tmp/hbedit-smoke-task7
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py init
```

Expected:
```
{"command":"init","status":"ok","action":"created"}
```

Verify:
```
test -f /tmp/hbedit-smoke-task7/.hbedit/state.json && echo OK
cat /tmp/hbedit-smoke-task7/.gitignore
```

Then test idempotency:
```
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py init
```

Expected:
```
{"command":"init","status":"ok","action":"already-initialized"}
```

Then test nested:
```
mkdir sub && cd sub
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py init
```

Expected:
```
{"command":"init","status":"error","code":"vault-nested","detail":"vault already exists at /tmp/hbedit-smoke-task7"}
```

Clean up:
```
cd / && rm -rf /tmp/hbedit-smoke-task7
```

- [ ] **Step 3: Commit**

```bash
cd /Users/leiweicheng/Desktop/HeptaSync
git add skills/hbedit/scripts/hbedit.py
git commit -m "feat(hbedit): add hb init command

Creates .hbedit/ with empty state.json (schemaVersion 2), updates
.gitignore. Idempotent in own root, errors with vault-nested if cwd
is inside an existing vault's tree."
```

---

### Task 8: Implement `hb push <path>` — create + update paths

This is the most involved task. Push has two paths: create-new (no
state.json entry) and update-existing (with baseline check + conflict
detection).

**Files:**
- Modify: `skills/hbedit/scripts/hbedit.py`
- Modify: `skills/hbedit/scripts/htb.py` (small addition if needed)

- [ ] **Step 1: Add datetime/json/sidecar helpers**

Edit `skills/hbedit/scripts/hbedit.py`:

Add to the imports section:

```python
import datetime    # noqa: E402
import json        # noqa: E402

import local_state                  # noqa: E402
import pm2md                        # noqa: E402
import tagsync                      # noqa: E402
import transplant                   # noqa: E402
```

Add helper functions (place after the `init()` function):

```python
def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _sidecar_path(vault, card_id):
    d = os.path.join(vault, ".hbedit", "sidecar")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, card_id + ".json")


def _read_body(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _resolve_vault_relative(vault, path):
    """Make `path` relative to `vault`. `path` may be relative to cwd or
    absolute. Returns the relative form used as state.json key."""
    abs_path = os.path.abspath(path)
    abs_vault = os.path.abspath(vault)
    rel = os.path.relpath(abs_path, abs_vault)
    return rel
```

- [ ] **Step 2: Add push() function**

After the helpers, add:

```python
def push(path):
    """Implement `hb push <path>`. Returns (json_output, exit_code)."""
    # File must exist.
    if not os.path.exists(path):
        return errors.emit_error("push", errors.FILE_NOT_FOUND,
                                 path=path,
                                 detail="%s does not exist" % path), 2
    # Locate vault.
    vault = vaultlib.find_vault_root(path)
    if vault is None:
        return errors.emit_error(
            "push", errors.NOT_IN_VAULT, path=path,
            detail="%s is not inside an hbedit vault. Run `hb init` in "
                   "the project root." % path), 2
    rel = _resolve_vault_relative(vault, path)

    # Load state.json (may raise StateSchemaError / StateCorruptError).
    try:
        state = vaultlib.load_state(vault)
    except vaultlib.StateSchemaError as exc:
        return errors.emit_error("push", errors.STATE_SCHEMA_UNSUPPORTED,
                                 detail=str(exc)), 2
    except vaultlib.StateCorruptError as exc:
        return errors.emit_error("push", errors.STATE_CORRUPT,
                                 detail=str(exc)), 2

    entry = state["files"].get(rel)
    body = _read_body(path)

    if entry is None:
        return _push_create(vault, rel, body)
    return _push_update(vault, rel, body, entry["cardId"])


def _push_create(vault, rel_path, body):
    """Create a new card from `body`, register in state.json + local-state."""
    try:
        result = htb.note_create(body)
    except htb.HtbError as exc:
        return errors.emit_error(
            "push", "create-failed", path=rel_path,
            detail=htb.error_detail(exc)), 2
    card_id = result["id"]
    try:
        vaultlib.set_file_entry(vault, rel_path, card_id, [])
    except vaultlib.DuplicateCardIdError as exc:
        # Shouldn't normally happen (fresh cardId), but guard.
        htb.card_trash(card_id)
        return errors.emit_error(
            "push", errors.CARDID_ALREADY_TRACKED, path=rel_path,
            detail=str(exc)), 2
    # Pull fresh metadata to capture contentMd5 + cache sidecar.
    rec = htb.note_read(card_id)
    with open(_sidecar_path(vault, card_id), "w", encoding="utf-8") as f:
        f.write(rec["content"])
    local_state.set_local_entry(
        vault, rel_path,
        content_md5=rec["contentMd5"],
        local_md5=local_state.body_md5(body),
        synced_at=_now_iso())
    return errors.emit_ok(
        "push", action="created", cardId=card_id, path=rel_path), 0


def _push_update(vault, rel_path, body, card_id):
    """Update an existing card using block-ID transplant from sidecar."""
    sidecar = _sidecar_path(vault, card_id)
    entry = local_state.get_local_entry(vault, rel_path)
    if entry is None or not os.path.exists(sidecar):
        return errors.emit_error(
            "push", errors.NO_BASELINE, path=rel_path,
            detail="local cache missing for %s. Run `hb pull %s` first."
                   % (rel_path, rel_path)), 2
    lock_md5 = entry["contentMd5"]
    with open(sidecar, "r", encoding="utf-8") as f:
        old_doc = json.load(f)
    # Build a scratch card so Heptabase performs the md->JSON conversion.
    try:
        scratch = htb.note_create(body)
        try:
            new_doc = json.loads(htb.note_read(scratch["id"])["content"])
            report = transplant.transplant_ids(old_doc, new_doc)
            try:
                htb.note_save(card_id, json.dumps(new_doc), lock_md5)
            except htb.HtbError as exc:
                if "content conflict" in htb.error_detail(exc).lower():
                    return _handle_conflict(vault, rel_path, body, card_id)
                if "card not found" in htb.error_detail(exc).lower():
                    return errors.emit_error(
                        "push", errors.CARD_NOT_FOUND, path=rel_path,
                        detail="card %s not found on Heptabase (trashed?)"
                               % card_id), 2
                raise
        finally:
            htb.card_trash(scratch["id"])
    except htb.HtbError as exc:
        return errors.emit_error(
            "push", "remote-error", path=rel_path,
            detail=htb.error_detail(exc)), 2
    # Refresh sidecar + local-state from the saved card.
    rec = htb.note_read(card_id)
    with open(sidecar, "w", encoding="utf-8") as f:
        f.write(rec["content"])
    local_state.set_local_entry(
        vault, rel_path,
        content_md5=rec["contentMd5"],
        local_md5=local_state.body_md5(body),
        synced_at=_now_iso())
    detail = {k: len(report[k]) for k in
              ("preserved", "edited", "reordered", "inserted", "deleted")}
    return errors.emit_ok(
        "push", action="updated", cardId=card_id, path=rel_path,
        detail=detail), 0


def _handle_conflict(vault, rel_path, local_body, card_id):
    """Remote changed since last pull: back up local body, re-pull remote
    over the working file, return a content-conflict response."""
    abs_path = os.path.join(vault, rel_path)
    backup = _conflict_path(abs_path)
    # Don't clobber an earlier unreconciled backup.
    stem, ext = os.path.splitext(backup)
    n = 2
    while os.path.exists(backup):
        backup = "%s.%d%s" % (stem, n, ext)
        n += 1
    with open(backup, "w", encoding="utf-8") as f:
        f.write(local_body)
    # Re-pull remote latest over the working file.
    rec = htb.note_read(card_id)
    remote_body, _ = pm2md.to_markdown(json.loads(rec["content"]))
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(remote_body)
    with open(_sidecar_path(vault, card_id), "w", encoding="utf-8") as f:
        f.write(rec["content"])
    local_state.set_local_entry(
        vault, rel_path,
        content_md5=rec["contentMd5"],
        local_md5=local_state.body_md5(remote_body),
        synced_at=_now_iso())
    return errors.emit_error(
        "push", errors.CONTENT_CONFLICT, path=rel_path,
        detail="remote changed since last pull. Local saved to %s; "
               "working file overwritten with remote latest. Reconcile "
               "the two and push the merged result."
               % os.path.relpath(backup, vault)), 2


def _conflict_path(path):
    stem, ext = os.path.splitext(path)
    return stem + ".conflict" + ext
```

- [ ] **Step 3: Wire push into main()**

In `main()`, before the fallthrough:

```python
    if len(argv) == 3 and argv[1] == "push":
        out, rc = push(argv[2])
        print(out)
        return rc
```

- [ ] **Step 4: Smoke test push-as-new + push-update**

```
mkdir -p /tmp/hbedit-smoke-task8
cd /tmp/hbedit-smoke-task8
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py init
echo "# Smoke push test
This is body content." > foo.md
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py push foo.md
```

Expected:
```
{"command":"push","status":"ok","action":"created","cardId":"<uuid>","path":"foo.md"}
```

Verify:
```
cat .hbedit/state.json
cat .hbedit/local-state.json
cat foo.md   # should be unchanged (no frontmatter)
ls .hbedit/sidecar/
```

Now edit and re-push:

```
echo "

Added a new paragraph." >> foo.md
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py push foo.md
```

Expected:
```
{"command":"push","status":"ok","action":"updated","cardId":"<uuid>","path":"foo.md","detail":{"preserved":N,"edited":0,"reordered":0,"inserted":1,"deleted":0}}
```

Clean up:

Use the cardId from the output to trash the test card:
```
heptabase card trash <cardId>
```

Then:
```
cd / && rm -rf /tmp/hbedit-smoke-task8
```

- [ ] **Step 5: Commit**

```bash
cd /Users/leiweicheng/Desktop/HeptaSync
git add skills/hbedit/scripts/hbedit.py
git commit -m "feat(hbedit): implement hb push (create + update paths)

Push touches content only — never tags. New file auto-creates a card,
existing file uses block-ID transplant with contentMd5 lock for
conflict detection. local-state.json + sidecar refreshed after every
successful sync."
```

---

### Task 9: Implement `hb pull <cardId> <path>`(first-time pull)

**Files:**
- Modify: `skills/hbedit/scripts/hbedit.py`

- [ ] **Step 1: Add pull-by-cardId helper + function**

Edit `skills/hbedit/scripts/hbedit.py`, add after the push helpers:

```python
def pull_first_time(card_id, path):
    """Implement `hb pull <cardId> <path>` — first-time pull to a new path."""
    vault = vaultlib.find_vault_root(path) or vaultlib.find_vault_root(os.getcwd())
    if vault is None:
        return errors.emit_error(
            "pull", errors.NOT_IN_VAULT, path=path,
            detail="no .hbedit/ found at or above %s" % path), 2
    rel = _resolve_vault_relative(vault, path)

    # Load state.json (validates schema + invariants).
    try:
        state = vaultlib.load_state(vault)
    except vaultlib.StateSchemaError as exc:
        return errors.emit_error("pull", errors.STATE_SCHEMA_UNSUPPORTED,
                                 detail=str(exc)), 2
    except vaultlib.StateCorruptError as exc:
        return errors.emit_error("pull", errors.STATE_CORRUPT,
                                 detail=str(exc)), 2

    # Refuse if cardId is already mapped elsewhere.
    existing = vaultlib.find_path_by_card_id(vault, card_id)
    if existing and existing != rel:
        return errors.emit_error(
            "pull", errors.CARDID_ALREADY_TRACKED, path=rel,
            detail="card %s is already linked to %s. Use `hb pull %s` to "
                   "refresh that one, or remove its state.json entry first."
                   % (card_id, existing, existing)), 2

    # Refuse if path exists and is not the same already-tracked entry.
    abs_path = os.path.abspath(path)
    if os.path.exists(abs_path) and state["files"].get(rel, {}).get("cardId") != card_id:
        return errors.emit_error(
            "pull", errors.PATH_EXISTS_UNTRACKED, path=rel,
            detail="%s already exists and is not tracked by this card. "
                   "Pick a different path or remove the file first." % rel), 2

    # Fetch + write.
    try:
        rec = htb.note_read(card_id)
    except htb.HtbError as exc:
        if "not found" in htb.error_detail(exc).lower():
            return errors.emit_error(
                "pull", errors.CARD_NOT_FOUND, path=rel,
                detail="card %s not found on Heptabase" % card_id), 2
        raise
    remote_md, _ = pm2md.to_markdown(json.loads(rec["content"]))
    os.makedirs(os.path.dirname(abs_path) or ".", exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(remote_md)
    with open(_sidecar_path(vault, card_id), "w", encoding="utf-8") as f:
        f.write(rec["content"])
    props = htb.card_properties(card_id)
    tags = sorted({t["tagName"] for t in props.get("tags", [])})
    vaultlib.set_file_entry(vault, rel, card_id, tags)
    local_state.set_local_entry(
        vault, rel,
        content_md5=rec["contentMd5"],
        local_md5=local_state.body_md5(remote_md),
        synced_at=_now_iso())
    return errors.emit_ok(
        "pull", action="created", cardId=card_id, path=rel,
        detail={"tags": tags}), 0
```

- [ ] **Step 2: Wire into main()**

In `main()`, before the fallthrough:

```python
    if len(argv) == 4 and argv[1] == "pull":
        # 4 args = hb pull <cardId> <path>
        out, rc = pull_first_time(argv[2], argv[3])
        print(out)
        return rc
```

- [ ] **Step 3: Smoke test first-time pull**

Use the test card we already have from earlier testing:
`330c7cd7-552c-49c4-8c07-df5c273b00b2`

```
mkdir -p /tmp/hbedit-smoke-task9
cd /tmp/hbedit-smoke-task9
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py init
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py pull 330c7cd7-552c-49c4-8c07-df5c273b00b2 notes/test.md
```

Expected:
```
{"command":"pull","status":"ok","action":"created","cardId":"330c7cd7-...","path":"notes/test.md","detail":{"tags":[]}}
```

Verify:
```
cat notes/test.md | head    # should NOT have frontmatter, just markdown
cat .hbedit/state.json      # files entry for notes/test.md
cat .hbedit/local-state.json
ls .hbedit/sidecar/
```

Test path-exists-untracked:
```
echo "preexisting" > notes/conflict.md
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py pull 5fd00975-8e78-45dc-bb96-db5cc0ee3994 notes/conflict.md
```

Expected:
```
{"command":"pull","status":"error","code":"path-exists-untracked",...}
```

Test cardId-already-tracked:
```
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py pull 330c7cd7-552c-49c4-8c07-df5c273b00b2 notes/other.md
```

Expected:
```
{"command":"pull","status":"error","code":"cardId-already-tracked",...}
```

Clean up:
```
cd / && rm -rf /tmp/hbedit-smoke-task9
```

- [ ] **Step 4: Commit**

```bash
cd /Users/leiweicheng/Desktop/HeptaSync
git add skills/hbedit/scripts/hbedit.py
git commit -m "feat(hbedit): implement hb pull <cardId> <path> (first-time)

Writes pure-markdown body, registers in state.json (with current
remote tags), populates local-state.json + sidecar. Rejects
overwriting an existing untracked file (path-exists-untracked) and
duplicate cardId mappings (cardId-already-tracked)."
```

---

### Task 10: Implement `hb pull <path>`(smart-compare pull)

This is the high-stakes case: pull must not silently clobber local
edits. Implements the 6-case decision matrix from spec § CLI > pull.

**Files:**
- Modify: `skills/hbedit/scripts/hbedit.py`

- [ ] **Step 1: Add smart-compare pull function**

Edit `skills/hbedit/scripts/hbedit.py`, add after `pull_first_time`:

```python
def pull_smart(path):
    """Implement `hb pull <path>` — smart-compare pull of a tracked path."""
    vault = vaultlib.find_vault_root(path) or vaultlib.find_vault_root(os.getcwd())
    if vault is None:
        return errors.emit_error(
            "pull", errors.NOT_IN_VAULT, path=path,
            detail="no .hbedit/ found at or above %s" % path), 2
    rel = _resolve_vault_relative(vault, path)

    try:
        state = vaultlib.load_state(vault)
    except vaultlib.StateSchemaError as exc:
        return errors.emit_error("pull", errors.STATE_SCHEMA_UNSUPPORTED,
                                 detail=str(exc)), 2
    except vaultlib.StateCorruptError as exc:
        return errors.emit_error("pull", errors.STATE_CORRUPT,
                                 detail=str(exc)), 2

    entry = state["files"].get(rel)
    if entry is None:
        return errors.emit_error(
            "pull", errors.PATH_NOT_TRACKED, path=rel,
            detail="%s is not registered in state.json. To start tracking "
                   "an existing card, use `hb pull <cardId> %s`. To push a "
                   "new card from this file, use `hb push %s`."
                   % (rel, rel, rel)), 2
    card_id = entry["cardId"]
    abs_path = os.path.abspath(path)

    # Fetch remote.
    try:
        rec = htb.note_read(card_id)
    except htb.HtbError as exc:
        if "not found" in htb.error_detail(exc).lower():
            return errors.emit_error(
                "pull", errors.CARD_NOT_FOUND, path=rel,
                detail="card %s is gone from Heptabase (trashed?)"
                       % card_id), 2
        raise
    remote_md, _ = pm2md.to_markdown(json.loads(rec["content"]))
    rr = local_state.body_md5(remote_md)

    # Compute local md5 (file may not exist if user deleted it).
    if os.path.exists(abs_path):
        with open(abs_path, "r", encoding="utf-8") as f:
            local_md = f.read()
        ll = local_state.body_md5(local_md)
    else:
        local_md = None
        ll = None

    local_entry = local_state.get_local_entry(vault, rel)
    ls = local_entry["localMd5"] if local_entry else None

    # Refresh remote tags into state.json
    props = htb.card_properties(card_id)
    tags = sorted({t["tagName"] for t in props.get("tags", [])})
    vaultlib.set_file_entry(vault, rel, card_id, tags)

    # Smart-compare matrix:
    if ls is None:
        # Fresh-clone case (or first pull-by-path after a state.json edit).
        if ll == rr:
            return _baseline_established(vault, rel, card_id, rec, remote_md, tags)
        # Differ or local missing.
        if ll is not None:
            _backup_local(abs_path, local_md)
        return _write_remote_and_baseline(
            vault, rel, abs_path, card_id, rec, remote_md, tags,
            action="conflict" if ll is not None else "created")
    # Has baseline:
    if ll == ls:
        # Local clean.
        if rr == ls:
            return _refresh_synced_at(vault, rel, card_id, rec, tags,
                                      action="noop")
        return _write_remote_and_baseline(
            vault, rel, abs_path, card_id, rec, remote_md, tags,
            action="updated")
    # Local diverged from baseline.
    if rr == ls:
        return errors.emit_error(
            "pull", errors.LOCAL_HAS_CHANGES, path=rel,
            detail="%s has local edits not in last sync. Push these "
                   "first (or revert manually) before pulling." % rel), 2
    # Both diverged.
    _backup_local(abs_path, local_md)
    return _write_remote_and_baseline(
        vault, rel, abs_path, card_id, rec, remote_md, tags,
        action="conflict")


def _baseline_established(vault, rel, card_id, rec, remote_md, tags):
    """Write local-state + sidecar without touching the working file."""
    with open(_sidecar_path(vault, card_id), "w", encoding="utf-8") as f:
        f.write(rec["content"])
    local_state.set_local_entry(
        vault, rel,
        content_md5=rec["contentMd5"],
        local_md5=local_state.body_md5(remote_md),
        synced_at=_now_iso())
    return errors.emit_ok("pull", action="baseline-established",
                          cardId=card_id, path=rel,
                          detail={"tags": tags}), 0


def _refresh_synced_at(vault, rel, card_id, rec, tags, action):
    entry = local_state.get_local_entry(vault, rel)
    local_state.set_local_entry(
        vault, rel,
        content_md5=entry["contentMd5"],
        local_md5=entry["localMd5"],
        synced_at=_now_iso())
    return errors.emit_ok("pull", action=action,
                          cardId=card_id, path=rel,
                          detail={"tags": tags}), 0


def _write_remote_and_baseline(vault, rel, abs_path, card_id, rec,
                               remote_md, tags, action):
    os.makedirs(os.path.dirname(abs_path) or ".", exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(remote_md)
    with open(_sidecar_path(vault, card_id), "w", encoding="utf-8") as f:
        f.write(rec["content"])
    local_state.set_local_entry(
        vault, rel,
        content_md5=rec["contentMd5"],
        local_md5=local_state.body_md5(remote_md),
        synced_at=_now_iso())
    return errors.emit_ok("pull", action=action,
                          cardId=card_id, path=rel,
                          detail={"tags": tags}), 0


def _backup_local(abs_path, body):
    """Write `body` to <abs_path>.conflict.md, disambiguating with a
    numeric suffix if a backup already exists."""
    backup = _conflict_path(abs_path)
    stem, ext = os.path.splitext(backup)
    n = 2
    while os.path.exists(backup):
        backup = "%s.%d%s" % (stem, n, ext)
        n += 1
    with open(backup, "w", encoding="utf-8") as f:
        f.write(body)
```

- [ ] **Step 2: Wire into main()**

In `main()`, before the fallthrough, add the 3-arg `pull` dispatch (the
4-arg case was added in Task 9):

```python
    if len(argv) == 3 and argv[1] == "pull":
        # 3 args = hb pull <path>
        out, rc = pull_smart(argv[2])
        print(out)
        return rc
```

- [ ] **Step 3: Smoke test the matrix**

Set up a vault with one tracked file:

```
mkdir -p /tmp/hbedit-smoke-task10
cd /tmp/hbedit-smoke-task10
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py init
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py pull 330c7cd7-552c-49c4-8c07-df5c273b00b2 notes/test.md
```

**3a. Both synced** (re-pull, no changes anywhere):

```
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py pull notes/test.md
```

Expected: `"action":"noop"`

**3b. Local diverged**:

```
echo "
LOCAL EDIT" >> notes/test.md
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py pull notes/test.md
```

Expected: `"code":"local-has-changes"`

Revert local change:

```
# Re-pull is what would happen via the conflict SOP, but for this smoke
# test we just push to make local the baseline, then revert.
# Easier: just nuke local-state to simulate fresh clone next.
```

**3c. Fresh-clone, local matches remote**:

```
rm -rf .hbedit/local-state.json .hbedit/sidecar/
# Restore notes/test.md to remote latest by deleting local edits manually:
# (easier: re-edit it to what we know is on remote, or just delete +
# re-pull via cardId)
# For this smoke test we'll delete and re-pull-by-cardId:
rm notes/test.md
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py pull 330c7cd7-552c-49c4-8c07-df5c273b00b2 notes/test.md
# Now simulate fresh clone again
rm -rf .hbedit/local-state.json .hbedit/sidecar/
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py pull notes/test.md
```

Expected: `"action":"baseline-established"`

**3d. Fresh-clone with divergence**:

```
rm -rf .hbedit/local-state.json .hbedit/sidecar/
echo "
LOCAL CHANGE BEFORE PULL" >> notes/test.md
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py pull notes/test.md
ls notes/    # should have notes/test.md AND notes/test.conflict.md
```

Expected: `"action":"conflict"`, working file overwritten, `.conflict.md` created.

Clean up:
```
cd / && rm -rf /tmp/hbedit-smoke-task10
```

- [ ] **Step 4: Commit**

```bash
cd /Users/leiweicheng/Desktop/HeptaSync
git add skills/hbedit/scripts/hbedit.py
git commit -m "feat(hbedit): implement smart-compare hb pull <path>

Six-case decision matrix prevents silent clobber of local edits on
fresh-clone scenarios and post-edit-without-push scenarios. Refreshes
state.json tags from remote on every pull."
```

---

### Task 11: Implement `hb tag add` / `hb tag remove`

**Files:**
- Modify: `skills/hbedit/scripts/hbedit.py`

- [ ] **Step 1: Add tag commands**

Edit `skills/hbedit/scripts/hbedit.py`, add after the pull functions:

```python
def tag_add(path, name):
    """Implement `hb tag add <path> <name>`."""
    return _tag_op(path, name, action="add")


def tag_remove(path, name):
    """Implement `hb tag remove <path> <name>`."""
    return _tag_op(path, name, action="remove")


def _tag_op(path, name, action):
    vault = vaultlib.find_vault_root(path) or vaultlib.find_vault_root(os.getcwd())
    if vault is None:
        return errors.emit_error(
            "tag", errors.NOT_IN_VAULT, path=path,
            detail="no .hbedit/ found at or above %s" % path), 2
    rel = _resolve_vault_relative(vault, path)

    try:
        state = vaultlib.load_state(vault)
    except vaultlib.StateSchemaError as exc:
        return errors.emit_error("tag", errors.STATE_SCHEMA_UNSUPPORTED,
                                 detail=str(exc)), 2
    except vaultlib.StateCorruptError as exc:
        return errors.emit_error("tag", errors.STATE_CORRUPT,
                                 detail=str(exc)), 2

    entry = state["files"].get(rel)
    if entry is None:
        return errors.emit_error(
            "tag", errors.PATH_NOT_TRACKED, path=rel,
            detail="%s is not tracked. Push or pull it first." % rel), 2
    card_id = entry["cardId"]

    # Read current remote tags.
    try:
        props = htb.card_properties(card_id)
    except htb.HtbError as exc:
        if "not found" in htb.error_detail(exc).lower():
            return errors.emit_error(
                "tag", errors.CARD_NOT_FOUND, path=rel,
                detail="card %s is gone from Heptabase" % card_id), 2
        raise
    remote_tags = sorted({t["tagName"] for t in props.get("tags", [])})

    if action == "add":
        if name in remote_tags:
            # Idempotent: already on the card. Refresh state, return ok.
            vaultlib.set_file_entry(vault, rel, card_id, remote_tags)
            return errors.emit_ok("tag", action="noop", cardId=card_id,
                                  path=rel,
                                  detail={"tags": remote_tags}), 0
        # Typo guard against the whole tag library.
        tag_index = htb.tag_list().get("tags") or []
        all_names = [t["name"] for t in tag_index]
        similar = tagsync.find_similar_tag(name, all_names)
        if similar:
            return errors.emit_error(
                "tag", errors.TAG_AMBIGUITY, path=rel,
                detail="tag %r is close to existing %r — fix or confirm "
                       "by retrying with the exact desired name."
                       % (name, similar)), 2
        htb.tag_add(card_id, name)
        new_tags = sorted(remote_tags + [name])
        vaultlib.set_file_entry(vault, rel, card_id, new_tags)
        return errors.emit_ok("tag", action="added", cardId=card_id,
                              path=rel,
                              detail={"tags": new_tags}), 0

    # action == "remove"
    if name not in remote_tags:
        return errors.emit_error(
            "tag", errors.TAG_NOT_ON_CARD, path=rel,
            detail="card has no tag %r (tags: %s)"
                   % (name, remote_tags)), 2
    tag_index = htb.tag_list().get("tags") or []
    by_name = {t["name"]: t["id"] for t in tag_index}
    tag_id = by_name.get(name)
    if tag_id is None:
        # Shouldn't happen if remote claims it's there — defensive.
        return errors.emit_error(
            "tag", "tag-id-not-found", path=rel,
            detail="tag %r reported on card but not found in tag library"
                   % name), 2
    htb.tag_remove(card_id, tag_id)
    new_tags = [t for t in remote_tags if t != name]
    vaultlib.set_file_entry(vault, rel, card_id, new_tags)
    return errors.emit_ok("tag", action="removed", cardId=card_id,
                          path=rel,
                          detail={"tags": new_tags}), 0
```

- [ ] **Step 2: Wire into main()**

In `main()`, before the fallthrough:

```python
    if len(argv) == 5 and argv[1] == "tag" and argv[2] == "add":
        out, rc = tag_add(argv[3], argv[4])
        print(out)
        return rc
    if len(argv) == 5 and argv[1] == "tag" and argv[2] == "remove":
        out, rc = tag_remove(argv[3], argv[4])
        print(out)
        return rc
```

- [ ] **Step 3: Smoke test tag commands**

```
mkdir -p /tmp/hbedit-smoke-task11
cd /tmp/hbedit-smoke-task11
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py init
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py pull 330c7cd7-552c-49c4-8c07-df5c273b00b2 notes/test.md
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py tag add notes/test.md smoke-test-tag
```

Expected: `"action":"added","detail":{"tags":[...,"smoke-test-tag"]}`

```
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py tag remove notes/test.md smoke-test-tag
```

Expected: `"action":"removed"`

```
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py tag remove notes/test.md nonexistent
```

Expected: `"code":"tag-not-on-card"`

Clean up:
```
cd / && rm -rf /tmp/hbedit-smoke-task11
```

- [ ] **Step 4: Commit**

```bash
cd /Users/leiweicheng/Desktop/HeptaSync
git add skills/hbedit/scripts/hbedit.py
git commit -m "feat(hbedit): implement hb tag add / hb tag remove

Simple fetch-modify-push semantics. tag add includes a typo guard
(tag-ambiguity) using fuzzy match against the full tag library. tag
remove resolves tag name to id via heptabase tag list."
```

---

### Task 12: Delete `frontmatter.py` + its test

**Files:**
- Delete: `skills/hbedit/scripts/frontmatter.py`
- Delete: `tests/test_frontmatter.py`

- [ ] **Step 1: Verify no other module imports frontmatter**

```
cd /Users/leiweicheng/Desktop/HeptaSync
grep -rn "import frontmatter" skills/ tests/ bin/
```

Expected: no matches (or only matches inside frontmatter.py itself).
If there's a stray reference, fix it in the importing file before deletion.

- [ ] **Step 2: Delete both files**

```
git rm skills/hbedit/scripts/frontmatter.py tests/test_frontmatter.py
```

- [ ] **Step 3: Run the whole unit test suite**

```
python3 -m pytest tests/ -v
```

Expected: all remaining tests pass; no ImportError from a dangling
reference.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore(hbedit): drop frontmatter.py — replaced by state.json

v2 binds .md to card via .hbedit/state.json (path map). The
frontmatter module is no longer used; its 168 lines and its tests
are deleted."
```

---

### Task 13: Rewrite `SKILL.md`

This task takes the longest single sitting because the SKILL.md is the
agent-facing API. Follow the structure from spec § 7 closely.

**Files:**
- Modify: `skills/hbedit/SKILL.md` (rewrite end-to-end)

- [ ] **Step 1: Draft the new SKILL.md**

Replace `skills/hbedit/SKILL.md` with a document following the spec
outline. Section-by-section content:

**[1] Frontmatter:**

```yaml
---
name: hbedit
description: Edit Heptabase cards as plain local markdown files — push existing local docs as new cards, edit the middle of existing cards, sync across machines via git, and manage tags. Each file is bound to a card via .hbedit/state.json (the markdown stays clean, no frontmatter). Reach for hbedit when the user wants to (a) maintain a local markdown file alongside its Heptabase card, (b) edit existing card content from a CLI / agent, (c) sync the same card across multiple machines, or (d) add/remove tags on existing cards. The base `heptabase` CLI only creates new cards or appends — use hbedit whenever the work involves an existing card, ongoing maintenance, or multi-machine workflows.
---
```

**[2] Header & disclaimer:**

```markdown
# hbedit (unofficial)

> Non-official. Built only on the official `heptabase` CLI; never reads
> or writes Heptabase's database, storage, or internal files. If asked
> whether this is official: it is not.
```

**[3] When to use hbedit vs the base `heptabase` CLI:**

Decision table:

| Task | Tool |
| --- | --- |
| Create a brand-new card from scratch and never touch it again | `heptabase note create` |
| Append to a card's end (one-shot) | `heptabase note append` |
| Anything else (edit middle, multi-machine, ongoing maintenance, tags) | hbedit |

**[4] Preflight — `hb doctor`:**

Always run first. Output:

```json
{"command":"doctor","status":"ok","detail":"..."}
```

If `status != "ok"`, look up `code` in the Error Code SOPs section
below before doing anything else.

**[5] Concepts — how hbedit tracks your files:**

Three-layer data table (copy from spec § Architecture). Mention vault
auto-discovery (walks up to find `.hbedit/`).

**[6] Command reference** (one short subsection per command —
semantics, success JSON, error codes):

For each of: doctor / init / push / pull-cardId-path / pull-path /
tag-add / tag-remove.

Each subsection example:

````markdown
### `hb push <path>`

Sync local edits up. Auto-creates a new Heptabase card if the path is
not yet registered in `state.json`; otherwise updates the linked card.
**Push touches content only — never tags. Use `hb tag add/remove` for
tag changes.**

Success (new card):
```json
{"command":"push","status":"ok","action":"created","cardId":"...","path":"docs/foo.md"}
```

Success (update):
```json
{"command":"push","status":"ok","action":"updated","cardId":"...","path":"docs/foo.md","detail":{"preserved":22,"edited":1,"inserted":2,"deleted":0,"reordered":0}}
```

Errors: `file-not-found`, `not-in-vault`, `no-baseline`,
`content-conflict`, `state-schema-unsupported`, `state-corrupt`,
`card-not-found`.
````

**[7] Workflow SOPs** — the agent-facing playbook. One subsection per
use case. Each SOP is numbered steps. Example:

````markdown
### SOP: edit an existing card ("fix a typo / restructure a section")

1. Run `hb doctor`. STOP and follow the doctor error SOP if not `ok`.
2. Find the card's path in `state.json`:
   ```
   cat .hbedit/state.json | python3 -c "import json,sys; print(json.load(sys.stdin)['files'])"
   ```
   If the card isn't tracked, search Heptabase by title:
   `heptabase card list -q "<title>"`, confirm with the user, then
   `hb pull <cardId> <path>` to start tracking.
3. **Tell the user what you intend to change.** Describe the diff in
   plain language ("I'll rewrite the ## API section to mention X and
   add a paragraph after ## Examples"). Wait for ack.
4. Edit the `.md` file using your editor tools.
5. Run `hb push <path>`.
6. If `status:"ok"`, report `action` + block counters to the user.
   If `status:"error"`, look up `code` in the Error Code SOPs section.
````

Repeat for: push as new card / continue on second machine / read-only
access / edit tags / split-merge-batch / plan-before-push (cross-cuts
all destructive SOPs) / recover from state-corrupt.

**[8] Error code SOPs** — agent-facing reactions per code. Copy the
table from spec § Error codes, expanding each row into a numbered SOP
the agent can follow.

**[9] Limitations:**

- Card-to-card references can't be authored from markdown — preserve
  existing ones, never try to create new ones.
- A push is capped at ~100,000 characters of Heptabase-internal JSON;
  a very large card may fail.
- No remote event stream — remote changes are detected only on pull.
- Only note cards (no journal, pdf, etc.).
- Renaming a tracked `.md` file: there's no `hb mv`; edit
  `state.json` manually to update the path key.

- [ ] **Step 2: Verify SKILL.md size**

```
wc -l skills/hbedit/SKILL.md
```

Expected: between 200 and 280 lines. If over 500 lines, split content
into a `references/` directory per the spec.

- [ ] **Step 3: Smoke test agent triggering**

Open a fresh Claude Code session with this plugin loaded:

```
cd /Users/leiweicheng/Desktop/HeptaSync
claude --plugin-dir .
```

Drop a test prompt:

> 「幫我新建一張 Heptabase 卡片,內容是這份本地 doc:`/tmp/test.md`」

Verify the agent:
- Loads `hbedit:hbedit`
- Runs `hb doctor`
- Reasons about `hb push` for the new-card case (per SOP)
- Doesn't reach for `heptabase note create` directly

If the agent picks the wrong command, refine the description /
SOPs.

- [ ] **Step 4: Commit**

```bash
cd /Users/leiweicheng/Desktop/HeptaSync
git add skills/hbedit/SKILL.md
git commit -m "docs(hbedit): rewrite SKILL.md for v2

New structure: concepts (three-layer state files), command reference
(7 JSON-output commands), workflow SOPs (one per use case), error
code SOPs (one per code). Description rewritten to surface multi-
machine + push-as-new use cases."
```

---

### Task 14: Run the manual integration tests from the spec

After all code changes, run through every TC in spec § Test strategy.
This is **manual** per the user's request — work down the list
systematically.

**Files:** none directly modified. May surface bugs that prompt
revisions in earlier tasks.

- [ ] **Step 1: Set up a fresh integration sandbox**

```
mkdir -p /tmp/hbedit-integ
cd /tmp/hbedit-integ
alias hb='python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py'
```

(Or set up the `bin/hb` wrapper to be on PATH so `hb` works directly.)

- [ ] **Step 2: Execute each TC from spec § Test strategy**

Work through TC1 through TC16. For each:
1. Read the test case from the spec
2. Run the setup
3. Execute the action
4. Verify the expected JSON output and filesystem state
5. Note pass/fail in `TESTING-NOTES.md`

Suggested order (groups related to each other):
- TC1, TC1b, TC1c (init variants)
- TC2, TC15 (push-create + not-in-vault)
- TC3, TC3b, TC7 (first-time pull variants)
- TC4, TC5, TC9 (push-update + idempotent + conflict)
- TC6, TC6b, TC6c, TC8, TC8b, TC8c (smart pull matrix + no-baseline)
- TC10, TC10b (tags)
- TC11 (doctor variants — turn off Heptabase desktop briefly)
- TC12 (end-to-end multi-machine simulation)
- TC13, TC14, TC16 (corruption / discovery / schema-version)

- [ ] **Step 3: Triage and fix issues**

If any TC fails:
1. Capture the actual output
2. Decide if it's a bug in implementation (fix the relevant earlier task's
   code) or a misunderstanding in the spec (update the spec)
3. Re-run the TC
4. Continue

Document fixes as additional commits, each with a clear message
referencing which TC surfaced the issue.

- [ ] **Step 4: Append manual test results to TESTING-NOTES.md**

After the run, append a section:

```markdown
## v2 redesign — manual test pass (YYYY-MM-DD)

| TC | Result | Notes |
| --- | --- | --- |
| TC1  | ✅ pass | |
| TC1b | ✅ pass | |
...
```

- [ ] **Step 5: Final commit**

```bash
cd /Users/leiweicheng/Desktop/HeptaSync
git add TESTING-NOTES.md
git commit -m "test: complete manual integration test pass for hbedit v2

All 19 manual TCs from the spec's test strategy section verified
against a real Heptabase desktop. Detailed results appended to
TESTING-NOTES.md."
```

Clean up:

```bash
rm -rf /tmp/hbedit-integ
```

---

## Self-review (writing-plans skill checklist)

**1. Spec coverage:**

| Spec section | Implementing task(s) |
| --- | --- |
| Architecture > 3-layer data | Tasks 2 (state.json), 3 (local-state.json), implicit (sidecar via push/pull) |
| Architecture > state.json schema v2 | Task 2 |
| Architecture > local-state.json schema | Tasks 3, 5 |
| Architecture > vault discovery | Task 2 |
| Architecture > card↔file identity (no two paths share cardId) | Task 2 (DuplicateCardIdError) |
| Architecture > multi-machine flow + smart pull | Task 10 |
| CLI > doctor | Task 6 |
| CLI > init | Task 7 |
| CLI > push | Task 8 |
| CLI > pull (first-time) | Task 9 |
| CLI > pull (smart) | Task 10 |
| CLI > tag add / remove | Task 11 |
| CLI > JSON output | Task 1 + applied throughout |
| Error codes (17 of them) | Task 1 (constants) + applied in commands |
| SKILL.md structure | Task 13 |
| Code changes summary > files removed | Task 12 |
| Code changes summary > files modified | Tasks 2, 6-11 |
| Code changes summary > files added | Tasks 1, 3 |
| Test strategy > unit tests | Tasks 1, 2, 3, 4, 5 |
| Test strategy > manual TCs | Task 14 |

All spec sections covered.

**2. Placeholder scan:** No "TBD" / "TODO" / generic "add appropriate error
handling" / "implement later" left in the plan. Every code block contains
runnable Python or shell. Every test contains real assertions.

**3. Type consistency:**
- Function names: `find_vault_root`, `init_vault`, `load_state`,
  `save_state`, `get_file_entry`, `set_file_entry`, `remove_file_entry`,
  `find_path_by_card_id`, `load_local_state`, `save_local_state`,
  `get_local_entry`, `set_local_entry`, `remove_local_entry`, `body_md5`,
  `emit_ok`, `emit_error` — used consistently across tasks.
- Error code constants: `CLI_MISSING`, `NO_BASELINE`, `PATH_NOT_TRACKED`,
  `LOCAL_HAS_CHANGES` etc. — defined in Task 1, used by name in Tasks
  6-11.
- State.json schemaVersion: `2` everywhere.
- local-state.json schemaVersion: `1` everywhere.
- Field names: `cardId`, `tags`, `contentMd5`, `localMd5`, `syncedAt` —
  consistent across tasks 2, 3, 5, 8, 9, 10.
- Exception classes: `StateSchemaError`, `StateCorruptError`,
  `NestedVaultError`, `DuplicateCardIdError` — defined in Task 2,
  caught by name in Tasks 8, 9, 10, 11.

No naming drift detected.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-24-hbedit-v2-redesign.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration. Good for catching issues in isolation.

**2. Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints. Good if you want to watch every step.

Which approach?
