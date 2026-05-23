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
