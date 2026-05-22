#!/usr/bin/env python3
"""HeptaSync — minimal sync entry point (v1).

  hs.py push <file.md>        sync a local HeptaSync note up to Heptabase
  hs.py pull <cardId> <vault> pull a card down into <vault>/notes/

UNOFFICIAL — not affiliated with Heptabase. Talks only to the official
`heptabase` CLI; never touches Heptabase's database or internal files.

A HeptaSync note is plain markdown with a `heptabase:` frontmatter block.
- No `cardId` in the frontmatter  -> push creates a new card.
- A `cardId` present              -> push updates that card via the transplant
                                      strategy (block IDs are preserved).
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)                                 # frontmatter.py
sys.path.insert(0, os.path.join(_HERE, "..", "poc"))      # htb, pm2md, transplant

import frontmatter   # noqa: E402
import htb           # noqa: E402
import pm2md         # noqa: E402
import transplant    # noqa: E402


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _vault_root(path):
    """Vault root = the directory holding `notes/`; fall back to the file's dir."""
    d = os.path.dirname(os.path.abspath(path))
    return os.path.dirname(d) if os.path.basename(d) == "notes" else d


def _sidecar_path(vault, card_id):
    d = os.path.join(vault, ".heptasync", "sidecar")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, card_id + ".json")


def _slug(title):
    s = re.sub(r"[^\w一-鿿 -]", "", title or "").strip().lower()
    return re.sub(r"\s+", "-", s) or "note"


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def push(path):
    """Sync a local HeptaSync note file up to Heptabase."""
    meta, body = frontmatter.parse(open(path, encoding="utf-8").read())
    hb = meta.get(frontmatter.MANAGED_KEY, {})
    card_id = hb.get("cardId")
    vault = _vault_root(path)

    if not card_id:
        # --- new note: Heptabase converts the markdown for us ------------
        card_id = htb.note_create(body)["id"]
        action = "created"
    else:
        # --- existing note: transplant block IDs, then save -------------
        old_doc = json.load(open(_sidecar_path(vault, card_id), encoding="utf-8"))
        before = htb.note_read(card_id)
        scratch = htb.note_create(body)              # Heptabase does md -> JSON
        try:
            new_doc = json.loads(htb.note_read(scratch["id"])["content"])
            report = transplant.transplant_ids(old_doc, new_doc)
            htb.note_save(card_id, json.dumps(new_doc), before["contentMd5"])
        finally:
            htb.card_trash(scratch["id"])
        action = "updated [%s]" % " ".join(
            "%s=%d" % (k, len(report[k]))
            for k in ("preserved", "edited", "reordered", "inserted", "deleted"))

    # persist sync state: sidecar JSON + refreshed frontmatter
    rec = htb.note_read(card_id)
    _write(_sidecar_path(vault, card_id), rec["content"])
    new_meta = frontmatter.build_note_meta(
        rec, tags=hb.get("tags"), whiteboards=hb.get("whiteboards"),
        synced_at=_now())
    _write(path, frontmatter.serialize(new_meta, body))
    return card_id, action


def pull(card_id, vault):
    """Pull a Heptabase card down into <vault>/notes/ as a HeptaSync note."""
    rec = htb.note_read(card_id)
    body, _ = pm2md.to_markdown(json.loads(rec["content"]))
    notes = os.path.join(vault, "notes")
    os.makedirs(notes, exist_ok=True)
    path = os.path.join(notes, _slug(rec["title"]) + ".md")
    meta = frontmatter.build_note_meta(rec, synced_at=_now())
    _write(path, frontmatter.serialize(meta, body))
    _write(_sidecar_path(vault, card_id), rec["content"])
    return path


def main(argv):
    if len(argv) == 3 and argv[1] == "push":
        card_id, action = push(argv[2])
        print("push: %s  ->  card %s" % (action, card_id))
        return 0
    if len(argv) == 4 and argv[1] == "pull":
        print("pull: wrote %s" % pull(argv[2], argv[3]))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
