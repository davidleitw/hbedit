"""HeptaSync feasibility POC — runner.

Runs the full experiment suite against a live Heptabase (desktop app must be
open), writes EXPERIMENTS.md, and publishes that log to a single persistent
Heptabase card (so it can be reviewed inside the app).

    cd poc && python3 poc.py

Every *test* card created during the run is trashed at the end. The one card
that survives is the published experiment log; its ID is stored in
`poc/.result_card` so re-runs update the same card.
"""
from __future__ import annotations

import os
import sys

# v1/ holds the frontmatter schema module, imported by experiments E18/E19.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "v1"))

import experiments  # noqa: E402
import harness      # noqa: E402
import htb          # noqa: E402

RESULT_ID_FILE = os.path.join(_HERE, ".result_card")


def publish_to_card():
    """Publish the experiment log + v1 design to one Heptabase card.

    The card is recreated each run rather than updated in place: `note save`
    validates the ProseMirror JSON, which exceeds the 100K-char limit for a
    document this size (see E21), whereas `note create` validates the markdown
    input, which is well under the limit.
    """
    parts = [open(os.path.join(_HERE, "EXPERIMENTS.md")).read()]
    design = os.path.join(_HERE, "..", "v1", "DESIGN.md")
    if os.path.exists(design):
        parts.append("\n\n---\n\n" + open(design).read())
    markdown = "".join(parts)

    if os.path.exists(RESULT_ID_FILE):
        with open(RESULT_ID_FILE) as f:
            old = f.read().strip()
        if old:
            try:
                htb.card_trash(old)
            except htb.HtbError:
                pass
    created = htb.note_create(markdown)
    with open(RESULT_ID_FILE, "w") as f:
        f.write(created["id"])
    return created["id"]


def main():
    cli = htb.version()
    print("HeptaSync POC — full suite (Heptabase CLI %s)\n" % cli)

    suite = harness.Suite()
    pool = experiments.CardPool()
    state = {}
    try:
        for fn in experiments.ALL:
            print("  running %s ..." % fn.__name__)
            fn(suite, pool, state)
    finally:
        trashed = pool.cleanup()
        print("\n  cleanup: trashed %d test card(s)" % trashed)

    suite.print_console()

    out = os.path.join(_HERE, "EXPERIMENTS.md")
    suite.write_markdown(out, cli)
    print("\nExperiment log written to %s" % out)

    try:
        card_id = publish_to_card()
        print("Published experiment log + v1 design to Heptabase card: %s"
              % card_id)
    except htb.HtbError as e:
        print("Could not publish to a card: %s" % e)

    fails = sum(1 for e in suite.experiments if e.status == harness.FAIL)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
