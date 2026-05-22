"""Thin wrapper around the Heptabase CLI.

Every command shells out to `heptabase` and returns parsed JSON. Content is
passed via temp files (`--content-file`) to avoid arg-length limits and any
shell-escaping issues with large ProseMirror JSON payloads.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import tempfile


class HtbError(RuntimeError):
    """A `heptabase` invocation failed or returned something unparseable."""


def error_detail(err):
    """Pull the server's error message out of an HtbError for display."""
    text = err.args[0] if err.args else str(err)
    match = re.search(r'"error"\s*:\s*"([^"]*)"', text)
    if match:
        return match.group(1)
    return " ".join(text.split())[-140:]


@contextlib.contextmanager
def _tmp(text):
    fd, path = tempfile.mkstemp(suffix=".txt")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        yield path
    finally:
        os.unlink(path)


def _run(args):
    proc = subprocess.run(["heptabase", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise HtbError(
            "heptabase " + " ".join(args) + " failed:\n" + (proc.stderr or proc.stdout)
        )
    out = proc.stdout.strip()
    if not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"_raw": out}


def version():
    return subprocess.run(
        ["heptabase", "--version"], capture_output=True, text=True
    ).stdout.strip()


# -- notes -----------------------------------------------------------------
def note_create(markdown):
    """Create a note from markdown. Returns {id, title}."""
    with _tmp(markdown) as path:
        return _run(["note", "create", "-f", path])


def note_read(card_id):
    """Read a note. Returns {id, title, content (ProseMirror JSON str), contentMd5}."""
    return _run(["note", "read", card_id])


def note_save(card_id, content_json_str, content_md5=None):
    """Replace a note's content with a ProseMirror JSON string."""
    args = ["note", "save", card_id]
    if content_md5:
        args += ["--content-md5", content_md5]
    with _tmp(content_json_str) as path:
        return _run(args + ["-f", path])


def note_append(card_id, markdown, content_md5=None):
    """Append markdown to a note."""
    args = ["note", "append", card_id]
    if content_md5:
        args += ["--content-md5", content_md5]
    with _tmp(markdown) as path:
        return _run(args + ["-f", path])


# -- cards -----------------------------------------------------------------
def card_list(query=None, card_types=None, sort="lastUpdatedTime",
              direction="descending", limit=20, offset=0):
    args = ["card", "list", "--sort", sort, "--direction", direction,
            "--limit", str(limit), "--offset", str(offset)]
    if query:
        args += ["-q", query]
    if card_types:
        args += ["--card-types", card_types]
    return _run(args)


def card_trash(card_id):
    return _run(["card", "trash", card_id])


def card_restore(card_id):
    return _run(["card", "restore", card_id])


def card_properties(card_id):
    return _run(["card", "properties", card_id])


def card_set_property(card_id, property_id, value=None, json_value=None):
    args = ["card", "set-property", card_id, "--property-id", property_id]
    if json_value is not None:
        args += ["--json-value", json_value]
    else:
        args += ["--value", value]
    return _run(args)


# -- tags ------------------------------------------------------------------
def tag_create(name):
    return _run(["tag", "create", "--name", name])


def tag_list(name_filter=None):
    args = ["tag", "list"]
    if name_filter:
        args += ["--name-filter", name_filter]
    return _run(args)


def tag_properties(tag_id):
    return _run(["tag", "properties", tag_id])


def tag_cards(tag_id, include_properties=False):
    args = ["tag", "cards", tag_id]
    if include_properties:
        args += ["--include-properties"]
    return _run(args)


def tag_add(card_id, tag_name):
    return _run(["tag", "add", "--card-id", card_id, "--tag-name", tag_name])


def tag_remove(card_id, tag_id):
    """Remove a tag from a card. `tag_id` is the tag's UUID (resolve a tag
    name to its id via `tag_list` first)."""
    return _run(["tag", "remove", "--card-id", card_id, "--tag-id", tag_id])


# -- whiteboards -----------------------------------------------------------
def whiteboard_list(limit=20):
    return _run(["whiteboard", "list", "--limit", str(limit)])


def whiteboard_cards(whiteboard_id):
    return _run(["whiteboard", "cards", whiteboard_id])


def whiteboard_add_card(whiteboard_id, card_id):
    return _run(["whiteboard", "add-card",
                 "--whiteboard-id", whiteboard_id, "--card-id", card_id])


def whiteboard_remove_card(whiteboard_id, card_id):
    return _run(["whiteboard", "remove-card",
                 "--whiteboard-id", whiteboard_id, "--card-id", card_id])


# -- journals (read-only here, to avoid touching real journals) ------------
def journal_read(date):
    return _run(["journal", "read", date])
