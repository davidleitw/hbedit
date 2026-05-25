"""Tests for the errors module."""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "skills", "hbedit", "scripts"))

import errors


def test_error_codes_constants_exist():
    # Every code referenced by SKILL.md / spec must be a module-level constant.
    expected = {
        "CLI_MISSING", "CLI_RESPONSE_UNEXPECTED", "APP_NOT_RUNNING",
        "NOT_IN_VAULT", "FILE_NOT_FOUND", "PATH_EXISTS_UNTRACKED",
        "PATH_NOT_TRACKED", "NO_BASELINE", "CONTENT_CONFLICT",
        "TAG_AMBIGUITY", "CARD_NOT_FOUND", "TAG_NOT_ON_CARD",
        "CARD_ID_ALREADY_TRACKED", "STATE_SCHEMA_UNSUPPORTED",
        "STATE_CORRUPT", "VAULT_NESTED", "LOCAL_HAS_CHANGES",
    }
    for name in expected:
        assert hasattr(errors, name), name


def test_error_codes_are_kebab_case():
    # Constants hold the wire string used in JSON output.
    assert errors.NO_BASELINE == "no-baseline"
    assert errors.PATH_NOT_TRACKED == "path-not-tracked"
    assert errors.CARD_ID_ALREADY_TRACKED == "cardId-already-tracked"
    assert errors.CLI_RESPONSE_UNEXPECTED == "cli-response-unexpected"


def test_emit_ok():
    s = errors.emit_ok("push", action="updated", cardId="abc", path="p.md")
    obj = json.loads(s)
    assert obj == {
        "command": "push", "status": "ok",
        "action": "updated", "cardId": "abc", "path": "p.md",
    }


def test_emit_error():
    s = errors.emit_error("pull", errors.NO_BASELINE, path="p.md", detail="msg")
    obj = json.loads(s)
    assert obj == {
        "command": "pull", "status": "error",
        "code": "no-baseline", "path": "p.md", "detail": "msg",
    }


def test_emit_error_skips_none_fields():
    s = errors.emit_error("init", errors.VAULT_NESTED, detail="hi", path=None)
    obj = json.loads(s)
    assert "path" not in obj
    assert obj["detail"] == "hi"


def test_emit_ok_skips_none_fields():
    s = errors.emit_ok("init", action="created", path=None)
    obj = json.loads(s)
    assert "path" not in obj
    assert obj["action"] == "created"
