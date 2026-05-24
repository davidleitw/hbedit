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
import vault as vaultlib      # noqa: E402
import datetime    # noqa: E402
import json        # noqa: E402

import local_state                  # noqa: E402
import pm2md                        # noqa: E402
import tagsync                      # noqa: E402
import transplant                   # noqa: E402


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


def init(cwd):
    """Initialize a vault in `cwd`. Returns (json_output, exit_code)."""
    try:
        result = vaultlib.init_vault(cwd)
    except vaultlib.NestedVaultError as exc:
        return errors.emit_error("init", errors.VAULT_NESTED,
                                 detail=str(exc)), 2
    return errors.emit_ok("init", action=result), 0


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _sidecar_path(cache_dir, card_id):
    """ProseMirror block-ID cache path for `card_id` in this vault's
    per-machine cache directory."""
    d = os.path.join(cache_dir, "sidecar")
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


def _conflict_path(path):
    stem, ext = os.path.splitext(path)
    return stem + ".conflict" + ext


def push(path):
    """Implement `hb push <path>`. Returns (json_output, exit_code)."""
    # File must exist.
    if not os.path.exists(path):
        return errors.emit_error("push", errors.FILE_NOT_FOUND,
                                 path=path,
                                 detail="%s does not exist" % path), 2
    # Locate vault and load state in one shot.
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
    entry = state["files"].get(rel)
    body = _read_body(path)

    if entry is None:
        return _push_create(vault, cd, rel, body)
    return _push_update(vault, cd, rel, body, entry["cardId"])


def _push_create(vault, cd, rel_path, body):
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
            "push", errors.CARD_ID_ALREADY_TRACKED, path=rel_path,
            detail=str(exc)), 2
    # Pull fresh metadata to capture contentMd5 + cache sidecar.
    rec = htb.note_read(card_id)
    # Normalize: rewrite local file with round-tripped content and use its
    # md5 for localMd5, so the file exactly matches what Heptabase stores.
    abs_path = os.path.join(vault, rel_path)
    round_trip_md, _ = pm2md.to_markdown(json.loads(rec["content"]))
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(round_trip_md)
    with open(_sidecar_path(cd, card_id), "w", encoding="utf-8") as f:
        f.write(rec["content"])
    local_state.set_local_entry(
        cd, rel_path,
        content_md5=rec["contentMd5"],
        local_md5=local_state.body_md5(round_trip_md),
        synced_at=_now_iso())
    return errors.emit_ok(
        "push", action="created", cardId=card_id, path=rel_path), 0


def _push_update(vault, cd, rel_path, body, card_id):
    """Update an existing card using block-ID transplant from sidecar."""
    sidecar = _sidecar_path(cd, card_id)
    entry = local_state.get_local_entry(cd, rel_path)
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
                    return _handle_conflict(vault, cd, rel_path, body, card_id)
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
    # Compute localMd5 from the round-tripped markdown (what Heptabase
    # actually stores) rather than from `body`.  Heptabase normalizes
    # content (e.g. strips trailing newlines) during md→ProseMirror→md
    # conversion, so using `body` would produce a stale localMd5 that
    # mis-triggers "conflict" on the next fresh-clone smart pull.
    # Also rewrite the local file with normalized content so it matches
    # exactly what Heptabase stores — keeping LL == RR on fresh clones.
    round_trip_md, _ = pm2md.to_markdown(json.loads(rec["content"]))
    abs_path = os.path.join(vault, rel_path)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(round_trip_md)
    with open(sidecar, "w", encoding="utf-8") as f:
        f.write(rec["content"])
    local_state.set_local_entry(
        cd, rel_path,
        content_md5=rec["contentMd5"],
        local_md5=local_state.body_md5(round_trip_md),
        synced_at=_now_iso())
    detail = {k: len(report[k]) for k in
              ("preserved", "edited", "reordered", "inserted", "deleted")}
    return errors.emit_ok(
        "push", action="updated", cardId=card_id, path=rel_path,
        detail=detail), 0


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

    # Refuse if cardId is already mapped elsewhere.
    existing = vaultlib.find_path_by_card_id(vault, card_id)
    if existing and existing != rel:
        return errors.emit_error(
            "pull", errors.CARD_ID_ALREADY_TRACKED, path=rel,
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
    with open(_sidecar_path(cd, card_id), "w", encoding="utf-8") as f:
        f.write(rec["content"])
    props = htb.card_properties(card_id)
    tags = sorted({t["tagName"] for t in props.get("tags", [])})
    vaultlib.set_file_entry(vault, rel, card_id, tags)
    local_state.set_local_entry(
        cd, rel,
        content_md5=rec["contentMd5"],
        local_md5=local_state.body_md5(remote_md),
        synced_at=_now_iso())
    return errors.emit_ok(
        "pull", action="created", cardId=card_id, path=rel,
        detail={"tags": tags}), 0


def pull_smart(path):
    """Implement `hb pull <path>` — smart-compare pull of a tracked path."""
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

    local_entry = local_state.get_local_entry(cd, rel)
    ls = local_entry["localMd5"] if local_entry else None

    # Refresh remote tags into state.json
    props = htb.card_properties(card_id)
    tags = sorted({t["tagName"] for t in props.get("tags", [])})
    vaultlib.set_file_entry(vault, rel, card_id, tags)

    # Smart-compare matrix:
    if ls is None:
        # Fresh-clone case (or first pull-by-path after a state.json edit).
        if ll == rr:
            return _baseline_established(vault, cd, rel, card_id, rec, remote_md, tags)
        # Differ or local missing.
        if ll is not None:
            _backup_local(abs_path, local_md)
        return _write_remote_and_baseline(
            vault, cd, rel, abs_path, card_id, rec, remote_md, tags,
            action="conflict" if ll is not None else "created")
    # Has baseline:
    if ll == ls:
        # Local clean.
        if rr == ls:
            return _refresh_synced_at(cd, rel, card_id, rec, tags,
                                      action="noop")
        return _write_remote_and_baseline(
            vault, cd, rel, abs_path, card_id, rec, remote_md, tags,
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
        vault, cd, rel, abs_path, card_id, rec, remote_md, tags,
        action="conflict")


def _baseline_established(vault, cd, rel, card_id, rec, remote_md, tags):
    """Write local-state + sidecar without touching the working file."""
    with open(_sidecar_path(cd, card_id), "w", encoding="utf-8") as f:
        f.write(rec["content"])
    local_state.set_local_entry(
        cd, rel,
        content_md5=rec["contentMd5"],
        local_md5=local_state.body_md5(remote_md),
        synced_at=_now_iso())
    return errors.emit_ok("pull", action="baseline-established",
                          cardId=card_id, path=rel,
                          detail={"tags": tags}), 0


def _refresh_synced_at(cd, rel, card_id, rec, tags, action):
    entry = local_state.get_local_entry(cd, rel)
    local_state.set_local_entry(
        cd, rel,
        content_md5=entry["contentMd5"],
        local_md5=entry["localMd5"],
        synced_at=_now_iso())
    return errors.emit_ok("pull", action=action,
                          cardId=card_id, path=rel,
                          detail={"tags": tags}), 0


def _write_remote_and_baseline(vault, cd, rel, abs_path, card_id, rec,
                               remote_md, tags, action):
    os.makedirs(os.path.dirname(abs_path) or ".", exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(remote_md)
    with open(_sidecar_path(cd, card_id), "w", encoding="utf-8") as f:
        f.write(rec["content"])
    local_state.set_local_entry(
        cd, rel,
        content_md5=rec["contentMd5"],
        local_md5=local_state.body_md5(remote_md),
        synced_at=_now_iso())
    return errors.emit_ok("pull", action=action,
                          cardId=card_id, path=rel,
                          detail={"tags": tags}), 0


def tag_add(path, name):
    """Implement `hb tag add <path> <name>`."""
    return _tag_op(path, name, action="add")


def tag_remove(path, name):
    """Implement `hb tag remove <path> <name>`."""
    return _tag_op(path, name, action="remove")


def _tag_op(path, name, action):
    try:
        info = vaultlib.find(path) or vaultlib.find(os.getcwd())
    except vaultlib.StateSchemaError as exc:
        return errors.emit_error("tag", errors.STATE_SCHEMA_UNSUPPORTED,
                                 detail=str(exc)), 2
    except vaultlib.StateCorruptError as exc:
        return errors.emit_error("tag", errors.STATE_CORRUPT,
                                 detail=str(exc)), 2
    if info is None:
        return errors.emit_error(
            "tag", errors.NOT_IN_VAULT, path=path,
            detail="no .hbedit/ found at or above %s" % path), 2
    vault, state, cd = info.root, info.state, info.cache_dir
    rel = _resolve_vault_relative(vault, path)

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


def _handle_conflict(vault, cd, rel_path, local_body, card_id):
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
    with open(_sidecar_path(cd, card_id), "w", encoding="utf-8") as f:
        f.write(rec["content"])
    local_state.set_local_entry(
        cd, rel_path,
        content_md5=rec["contentMd5"],
        local_md5=local_state.body_md5(remote_body),
        synced_at=_now_iso())
    return errors.emit_error(
        "push", errors.CONTENT_CONFLICT, path=rel_path,
        detail="remote changed since last pull. Local saved to %s; "
               "working file overwritten with remote latest. Reconcile "
               "the two and push the merged result."
               % os.path.relpath(backup, vault)), 2


def main(argv):
    if len(argv) == 2 and argv[1] == "doctor":
        out, rc = doctor()
        print(out)
        return rc
    if len(argv) == 2 and argv[1] == "init":
        out, rc = init(os.getcwd())
        print(out)
        return rc
    if len(argv) == 3 and argv[1] == "push":
        out, rc = push(argv[2])
        print(out)
        return rc
    if len(argv) == 3 and argv[1] == "pull":
        # 3 args = hb pull <path>
        out, rc = pull_smart(argv[2])
        print(out)
        return rc
    if len(argv) == 4 and argv[1] == "pull":
        # 4 args = hb pull <cardId> <path>
        out, rc = pull_first_time(argv[2], argv[3])
        print(out)
        return rc
    if len(argv) == 5 and argv[1] == "tag" and argv[2] == "add":
        out, rc = tag_add(argv[3], argv[4])
        print(out)
        return rc
    if len(argv) == 5 and argv[1] == "tag" and argv[2] == "remove":
        out, rc = tag_remove(argv[3], argv[4])
        print(out)
        return rc
    # Other commands land in subsequent tasks.
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
