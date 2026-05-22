"""hbedit v1 — frontmatter schema.

An hbedit note file is plain Markdown with a YAML frontmatter block holding
the metadata that ties the file back to a Heptabase card. All managed keys live
under a single `heptabase:` mapping so the block is unambiguous and easy to
strip before pushing content to Heptabase.

    ---
    heptabase:
      schemaVersion: 1
      cardId: 7301c5b4-ee45-4b10-bb31-7cc50b92dc4f
      type: note
      tags:
        - LeetCode
      contentMd5: 7d960abeac141347ff200a6f59991de9
      syncedAt: 2026-05-22T00:00:00Z
    ---
    # My note

    Body markdown...

Standard markdown previewers hide the `---` frontmatter, so the metadata is
invisible while reading.

This module implements a *minimal* YAML subset — exactly the shapes this schema
uses (one nesting level, scalars and lists). The minimal subset is intentional:
the tool stays stdlib-only (zero external dependencies). Round-trip is verified
by experiment E19.
"""
from __future__ import annotations

MANAGED_KEY = "heptabase"
SCHEMA_VERSION = 1

# The managed keys, in canonical emit order.
SCHEMA_FIELDS = ["schemaVersion", "cardId", "type", "tags",
                 "contentMd5", "syncedAt"]


# -- public API ------------------------------------------------------------
def parse(text):
    """Split note text into (meta, body).

    meta is the parsed frontmatter dict; body is the markdown after it.
    Returns ({}, text) when there is no frontmatter block.
    """
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 3)
    if end == -1:
        return {}, text
    return _parse_block(text[4:end]), text[end + 5:]


def serialize(meta, body):
    """Render (meta, body) back into a note file string."""
    lines = ["---"]
    for key, val in meta.items():
        lines += _emit(key, val, 0)
    lines.append("---")
    return "\n".join(lines) + "\n" + body


def build_note_meta(card_record, tags=None, synced_at=None):
    """Build the managed frontmatter dict for a note card.

    card_record: a dict from `heptabase note read` (id, contentMd5).
    The card title is NOT stored — its source of truth is the body's first H1
    (see DESIGN.md §8.3). The dict insertion order below IS the emit order and
    must match SCHEMA_FIELDS.
    """
    hb = {
        "schemaVersion": SCHEMA_VERSION,
        "cardId": card_record.get("id"),
        "type": "note",
        "tags": list(tags or []),
        "contentMd5": card_record.get("contentMd5"),
        "syncedAt": synced_at,
    }
    return {MANAGED_KEY: hb}


# -- minimal YAML-subset parser / emitter ---------------------------------
def _parse_block(block):
    root = {}
    container = root      # mapping currently receiving keys
    current_list = None   # list currently receiving `- ` items
    for raw in block.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        line = raw.strip()
        if line.startswith("- "):
            if current_list is not None:
                current_list.append(_scalar(line[2:]))
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        current_list = None
        target = root if indent == 0 else container
        if val == "[]":
            target[key] = []
        elif val == "{}":
            target[key] = {}
        elif val == "":
            if indent == 0:
                target[key] = {}
                container = target[key]
            else:
                current_list = []
                target[key] = current_list
        else:
            target[key] = _scalar(val)
    return root


def _emit(key, val, indent):
    pad = "  " * indent
    if isinstance(val, dict):
        rows = [pad + key + ":"]
        for k, v in val.items():
            rows += _emit(k, v, indent + 1)
        return rows
    if isinstance(val, list):
        if not val:
            return [pad + key + ": []"]
        rows = [pad + key + ":"]
        for item in val:
            rows.append(pad + "  - " + _dump_scalar(item))
        return rows
    return [pad + key + ": " + _dump_scalar(val)]


def _scalar(token):
    token = token.strip()
    if len(token) >= 2 and token[0] == '"' and token[-1] == '"':
        return token[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if token == "true":
        return True
    if token == "false":
        return False
    if token in ("null", "~", ""):
        return None
    if token.lstrip("-").isdigit():
        return int(token)
    return token


def _dump_scalar(val):
    if val is True:
        return "true"
    if val is False:
        return "false"
    if val is None:
        return "null"
    if isinstance(val, int):
        return str(val)
    s = str(val)
    # YAML only needs quoting for a colon *followed by space* (mapping
    # ambiguity); a colon inside e.g. a timestamp is fine unquoted.
    needs_quote = (s == "" or s.strip() != s
                   or s in ("true", "false", "null", "~")
                   or ": " in s or s.endswith(":")
                   or any(c in s for c in '#"\n')
                   or s[0] in "-?:[]{}>|*&!%@`,")
    if needs_quote:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s
