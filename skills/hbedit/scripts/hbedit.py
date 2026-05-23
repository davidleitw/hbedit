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


def main(argv):
    if len(argv) == 2 and argv[1] == "doctor":
        out, rc = doctor()
        print(out)
        return rc
    # Other commands land in subsequent tasks.
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
