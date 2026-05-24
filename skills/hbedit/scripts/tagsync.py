"""hbedit v3 — fuzzy-match guard for tag typos.

Tag merge logic moved into the command implementations as simple
fetch-modify-push (no 3-way merge in v2). What remains here is the
typo guard used by `hb tag add` to refuse near-duplicate tag names.
"""
from __future__ import annotations

import difflib


def find_similar_tag(name, existing, threshold=0.8):
    """If `name` is not a case-sensitive exact member of `existing` but is
    close to one (case-folded difflib ratio >= threshold), return that
    closest tag; otherwise return None.

    A case-only difference (e.g. "hbedit" vs "Hbedit") IS surfaced as a
    hit — Heptabase tag names are case-sensitive, so `tag add` on the
    wrong casing would spawn a near-duplicate.
    """
    if name in existing:
        return None
    low = name.lower()
    best, best_score = None, 0.0
    for candidate in existing:
        score = difflib.SequenceMatcher(None, low, candidate.lower()).ratio()
        if score > best_score:
            best, best_score = candidate, score
    return best if best_score >= threshold else None
