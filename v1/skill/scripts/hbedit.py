#!/usr/bin/env python3
"""hbedit — minimal CLI entry point (v1).

  hb push <file.md>        sync a local hbedit note up to Heptabase
  hb pull <cardId> <vault> pull a card down into <vault>/notes/

UNOFFICIAL — not affiliated with Heptabase. Talks only to the official
`heptabase` CLI; never touches Heptabase's database or internal files.

An hbedit note is plain markdown with a `heptabase:` frontmatter block.
- No `cardId` in the frontmatter  -> push creates a new card.
- A `cardId` present              -> push updates that card via the transplant
                                      strategy (block IDs are preserved).
"""
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)                                 # all modules co-located

import frontmatter   # noqa: E402
import htb           # noqa: E402
import pm2md         # noqa: E402
import transplant    # noqa: E402
import vault as vaultlib   # noqa: E402
import tagsync             # noqa: E402


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _sidecar_path(vault, card_id):
    d = os.path.join(vault, ".hbedit", "sidecar")
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
    """Sync a local hbedit note file up to Heptabase."""
    with open(path, encoding="utf-8") as fh:
        meta, body = frontmatter.parse(fh.read())
    hb = meta.get(frontmatter.MANAGED_KEY, {})
    card_id = hb.get("cardId")
    vault = vaultlib.find_vault_root(path)
    if vault is None:
        raise SystemExit("push: %s is not inside an hbedit vault" % path)

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
            try:
                htb.note_save(card_id, json.dumps(new_doc), lock_md5)
            except htb.HtbError as exc:
                # Heptabase server signal; substring match is fragile —
                # revisit if upstream changes the wording.
                if "content conflict" in htb.error_detail(exc).lower():
                    # _handle_conflict re-pulls, which writes the sidecar +
                    # frontmatter itself; the persist block below is then
                    # correctly skipped via this early return.
                    return _handle_conflict(path, body, vault, card_id)
                raise
        finally:
            htb.card_trash(scratch["id"])
        action = "updated [%s]" % " ".join(
            "%s=%d" % (k, len(report[k]))
            for k in ("preserved", "edited", "reordered", "inserted", "deleted"))

    # Persist content-sync state FIRST — sidecar + frontmatter with a fresh
    # contentMd5, using the user's frontmatter tags for now. Doing this before
    # tag sync means an aborted tag sync (TagAmbiguityError) cannot leave a
    # stale lock that would trigger a spurious conflict on the next push, and
    # it leaves the user's tags: edit visible so they can fix the typo.
    rec = htb.note_read(card_id)
    _write(_sidecar_path(vault, card_id), rec["content"])
    new_meta = frontmatter.build_note_meta(
        rec, tags=hb.get("tags"), synced_at=_now())
    _write(path, frontmatter.serialize(new_meta, body))

    # sync tags (3-way); a typo aborts here, after content state is saved
    tag_summary = _sync_tags(vault, card_id, hb.get("tags"))
    action = action + "; " + tag_summary

    # tag sync settled the real tag set — refresh the frontmatter tags
    new_meta[frontmatter.MANAGED_KEY]["tags"] = vaultlib.get_tag_base(
        vault, card_id)
    _write(path, frontmatter.serialize(new_meta, body))
    return card_id, action


def pull(card_id, vault):
    """Pull a Heptabase card into the vault as an hbedit note.

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
    if path is None:
        notes = os.path.join(vault, "notes")
        os.makedirs(notes, exist_ok=True)
        path = _slug_path(notes, rec["title"], card_id)

    meta = frontmatter.build_note_meta(rec, tags=tags, synced_at=_now())
    _write(path, frontmatter.serialize(meta, body))
    _write(_sidecar_path(vault, card_id), rec["content"])
    vaultlib.set_tag_base(vault, card_id, tags)
    return path


def _conflict_path(path):
    """`notes/foo.md` -> `notes/foo.conflict.md`."""
    stem, ext = os.path.splitext(path)
    return stem + ".conflict" + ext


def _handle_conflict(path, local_body, vault, card_id):
    """Remote changed since last pull: back up the local body (never
    clobbering an earlier unreconciled backup), then re-pull the remote
    latest over the working file. The user reconciles by hand."""
    backup = _conflict_path(path)
    stem, ext = os.path.splitext(backup)
    n = 2
    while os.path.exists(backup):
        backup = "%s.%d%s" % (stem, n, ext)
        n += 1
    _write(backup, local_body)
    try:
        pull(card_id, vault)        # overwrites `path` with remote latest
    except Exception as exc:
        raise RuntimeError(
            "conflict backup saved to %s, but the re-pull failed: %s"
            % (backup, exc)) from exc
    return card_id, "conflict (local saved to %s)" % os.path.basename(backup)


class TagAmbiguityError(SystemExit):
    """A frontmatter tag is suspiciously close to an existing one — likely a
    typo. Per DESIGN.md §8.5 we stop rather than silently create a new tag."""


def _sync_tags(vault, card_id, local_tags):
    """3-way sync the card's tags toward frontmatter `tags:`. Returns a short
    summary string. Raises TagAmbiguityError on a suspected typo."""
    base = vaultlib.get_tag_base(vault, card_id)
    props = htb.card_properties(card_id)
    remote = sorted({t["tagName"] for t in props.get("tags", [])})
    to_add, to_remove, final = tagsync.merge_tags(base, local_tags or [], remote)

    # one tag_list snapshot: to_remove tags already exist in it, and every
    # new tag is validated against it before any mutation happens.
    tag_index = htb.tag_list().get("tags") or []
    all_names = [t["name"] for t in tag_index]
    # validate EVERY new tag before touching Heptabase — a typo must abort
    # before any partial tag_add leaves the recorded base stale.
    for name in to_add:
        similar = tagsync.find_similar_tag(name, all_names)
        if similar:
            raise TagAmbiguityError(
                "tag '%s' is close to existing '%s' — fix the frontmatter "
                "tags: and push again (or keep it if it is intentional)"
                % (name, similar))
    for name in to_add:
        htb.tag_add(card_id, name)

    id_by_name = {t["name"]: t["id"] for t in tag_index}
    for name in to_remove:
        if name in id_by_name:
            htb.tag_remove(card_id, id_by_name[name])

    vaultlib.set_tag_base(vault, card_id, final)
    return "tags +%d -%d" % (len(to_add), len(to_remove))


SUPPORTED_RANGE = "0.3."          # accept 0.3.x


def _version_supported(version):
    """True if a `heptabase --version` string is within the supported range."""
    return bool(version) and version.strip().startswith(SUPPORTED_RANGE)


def doctor():
    """Preflight: verify the Heptabase CLI is installed, compatible, and the
    desktop app is running. Returns (status, detail). See DESIGN.md §9.4.

    Always returns a structured status — never lets a subprocess/OS error
    escape as a traceback, since `hb doctor` is consumed as machine output."""
    if shutil.which("heptabase") is None:
        return "cli-missing", "heptabase CLI not found on PATH"
    try:
        version = htb.version()
    except OSError as exc:
        return "cli-missing", "heptabase CLI could not be run: %s" % exc
    if not _version_supported(version):
        return ("cli-version-unsupported",
                "heptabase %s is outside the supported %sx range"
                % (version or "?", SUPPORTED_RANGE))
    try:
        htb.card_list(limit=1)
    except htb.HtbError as exc:
        return "app-not-running", htb.error_detail(exc)
    except OSError as exc:
        return "cli-missing", "heptabase CLI could not be run: %s" % exc
    return "ok", "heptabase %s, desktop app reachable" % version


def main(argv):
    if len(argv) == 2 and argv[1] == "doctor":
        status, detail = doctor()
        print(json.dumps({"command": "doctor", "status": status,
                          "detail": detail}, ensure_ascii=False))
        return 0 if status == "ok" else 2
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
