"""Stable error-code identifiers and JSON output helpers for hbedit.

Every CLI command outputs a JSON object to stdout (one per invocation).
Agents key off `status` and `code` to decide what to do — see SKILL.md
for per-code SOPs.
"""
from __future__ import annotations

import json


# -- error codes -----------------------------------------------------------
# Doctor / environment
CLI_MISSING = "cli-missing"
CLI_VERSION_UNSUPPORTED = "cli-version-unsupported"
APP_NOT_RUNNING = "app-not-running"

# Vault / filesystem
NOT_IN_VAULT = "not-in-vault"
VAULT_NESTED = "vault-nested"
FILE_NOT_FOUND = "file-not-found"
PATH_EXISTS_UNTRACKED = "path-exists-untracked"

# State files
STATE_SCHEMA_UNSUPPORTED = "state-schema-unsupported"
STATE_CORRUPT = "state-corrupt"

# Path tracking
PATH_NOT_TRACKED = "path-not-tracked"
CARD_ID_ALREADY_TRACKED = "cardId-already-tracked"

# Sync / conflict
NO_BASELINE = "no-baseline"
CONTENT_CONFLICT = "content-conflict"
LOCAL_HAS_CHANGES = "local-has-changes"

# Card / tag
CARD_NOT_FOUND = "card-not-found"
TAG_AMBIGUITY = "tag-ambiguity"
TAG_NOT_ON_CARD = "tag-not-on-card"


# -- JSON output helpers ---------------------------------------------------
def serialize(obj):
    """Emit a single-line JSON string with stable key order, UTF-8 safe."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def emit_ok(command, **fields):
    """Produce the success JSON string for a command. Drop None fields."""
    out = {"command": command, "status": "ok"}
    for k, v in fields.items():
        if v is not None:
            out[k] = v
    return serialize(out)


def emit_error(command, code, **fields):
    """Produce the error JSON string for a command. Drop None fields."""
    out = {"command": command, "status": "error", "code": code}
    for k, v in fields.items():
        if v is not None:
            out[k] = v
    return serialize(out)
