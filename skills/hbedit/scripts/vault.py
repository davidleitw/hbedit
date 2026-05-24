"""hbedit v3 — vault discovery, state.json (v3 schema), init.

The vault root is the nearest ancestor directory containing `.hbedit/`
(same idea as git locating `.git/`). state.json maps `path -> {cardId,
tags}`; it's the single source of truth for which `.md` is bound to
which card.
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import dataclass

@dataclass
class VaultInfo:
    """Bundle returned by `find()`. Single source of truth for cache_dir."""
    root: str        # vault root path (the dir containing .hbedit/)
    state: dict      # parsed state.json
    cache_dir: str   # ~/.hbedit/cache/<vault-id>/


STATE_DIR = ".hbedit"
STATE_FILE = "state.json"
SCHEMA_VERSION = 3


# -- exceptions ------------------------------------------------------------
class StateSchemaError(Exception):
    """state.json has a schemaVersion other than 3."""


class StateCorruptError(Exception):
    """state.json is unparseable JSON or violates invariants."""


class NestedVaultError(Exception):
    """init_vault called inside an existing vault's tree."""


class DuplicateCardIdError(Exception):
    """set_file_entry would map a cardId already used by another path."""


# -- vault discovery -------------------------------------------------------
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


# -- load / save -----------------------------------------------------------
def load_state(vault):
    """Return parsed state.json. Returns the empty-v3 skeleton when the
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
