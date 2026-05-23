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
            "push", errors.CARD_ID_ALREADY_TRACKED, path=rel_path,
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
    # Other commands land in subsequent tasks.
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
