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
sys.path.insert(0, _HERE)                                 # all modules co-located

import frontmatter   # noqa: E402
import htb           # noqa: E402
import pm2md         # noqa: E402
import transplant    # noqa: E402
import vault as vaultlib   # noqa: E402
import tagsync             # noqa: E402,F401  # used by push in Task 10


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _sidecar_path(vault, card_id):
    d = os.path.join(vault, ".heptasync", "sidecar")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, card_id + ".json")


def _slug(title):
    s = re.sub(r"[^\w一-鿿 -]", "", title or "").strip().lower()
    return re.sub(r"\s+", "-", s) or "note"


def _slug_path(notes_dir, title, card_id):
    """First-pull file path for a card. On slug collision, disambiguate with
    a short cardId prefix so two cards never claim one file. If even the
    disambiguated path is taken, fail loudly rather than overwrite."""
    slug = _slug(title)
    path = os.path.join(notes_dir, slug + ".md")
    if not os.path.exists(path):
        return path
    disambig = os.path.join(notes_dir, slug + "-" + card_id[:8] + ".md")
    if os.path.exists(disambig):
        raise FileExistsError(
            "cannot place a first-pull file for card %s: both %s and %s "
            "are already taken" % (card_id, path, disambig))
    return disambig


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def push(path):
    """Sync a local HeptaSync note file up to Heptabase."""
    with open(path, encoding="utf-8") as fh:
        meta, body = frontmatter.parse(fh.read())
    hb = meta.get(frontmatter.MANAGED_KEY, {})
    card_id = hb.get("cardId")
    vault = vaultlib.find_vault_root(path)
    if vault is None:
        raise SystemExit("push: %s is not inside a HeptaSync vault" % path)

    if not card_id:
        # --- new note: Heptabase converts the markdown for us ------------
        card_id = htb.note_create(body)["id"]
        action = "created"
    else:
        # --- existing note: transplant block IDs, then save -------------
        with open(_sidecar_path(vault, card_id), encoding="utf-8") as fh:
            old_doc = json.load(fh)
        lock_md5 = hb.get("contentMd5")          # the last-pull md5 = the lock
        if lock_md5 is None:
            raise SystemExit(
                "push: %s has no contentMd5 — re-pull the card before "
                "pushing (without the lock a push could silently overwrite "
                "remote changes)" % path)
        scratch = htb.note_create(body)          # Heptabase does md -> JSON
        try:
            new_doc = json.loads(htb.note_read(scratch["id"])["content"])
            report = transplant.transplant_ids(old_doc, new_doc)
            htb.note_save(card_id, json.dumps(new_doc), lock_md5)
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
    """Pull a Heptabase card into the vault as a HeptaSync note.

    If a file for this cardId already exists, it is updated in place (the
    filename never auto-changes — DESIGN.md §8.3). Otherwise a slug-named
    file is created. Tags are synced down from the card.
    """
    rec = htb.note_read(card_id)
    body, _ = pm2md.to_markdown(json.loads(rec["content"]))

    # tags currently on the card
    props = htb.card_properties(card_id)
    tags = sorted({t["tagName"] for t in props.get("tags", [])})

    # locate the existing file for this card, or pick a first-pull path
    path = vaultlib.find_file_by_card_id(vault, card_id)
    whiteboards = []
    if path is None:
        notes = os.path.join(vault, "notes")
        os.makedirs(notes, exist_ok=True)
        path = _slug_path(notes, rec["title"], card_id)
    else:
        # preserve the user-editable whiteboards field across a pull
        with open(path, encoding="utf-8") as fh:
            old_meta, _ = frontmatter.parse(fh.read())
        whiteboards = old_meta.get(frontmatter.MANAGED_KEY, {}).get(
            "whiteboards", [])

    meta = frontmatter.build_note_meta(
        rec, tags=tags, whiteboards=whiteboards, synced_at=_now())
    _write(path, frontmatter.serialize(meta, body))
    _write(_sidecar_path(vault, card_id), rec["content"])
    vaultlib.set_tag_base(vault, card_id, tags)
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
