"""HeptaSync v1 — vault layer: discovery, card->file lookup, sync state.

The vault root is the nearest ancestor directory containing `.heptasync/`
(the same idea as git locating `.git/`). See DESIGN.md §8.2.
"""
from __future__ import annotations

import json
import os

import frontmatter

STATE_DIR = ".heptasync"
STATE_FILE = "state.json"


def find_vault_root(start):
    """Walk up from `start` (a file or dir) to the dir holding `.heptasync/`.
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


def find_file_by_card_id(vault, card_id):
    """Scan `vault/notes/**` for the .md whose frontmatter cardId matches.
    Returns the file path, or None if no match is found (including when
    `vault/notes/` does not exist — e.g. the first sync of any card)."""
    notes = os.path.join(vault, "notes")
    for root, _dirs, files in os.walk(notes):
        for name in sorted(files):
            if not name.endswith(".md"):
                continue
            path = os.path.join(root, name)
            try:
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
            except OSError:
                continue
            # frontmatter.parse is a hand-rolled parser; a malformed file
            # must not abort the whole scan.
            try:
                meta, _ = frontmatter.parse(text)
            except Exception:
                continue
            hb = meta.get(frontmatter.MANAGED_KEY, {})
            if hb.get("cardId") == card_id:
                return path
    return None
