"""HeptaSync v1 — tag 3-way merge and fuzzy-match guard. See DESIGN.md §8.5."""
from __future__ import annotations

import difflib


def merge_tags(base, local, remote):
    """3-way merge of tag-name sets.

    base   — tags recorded at the last sync (state.json).
    local  — tags now in the file's frontmatter.
    remote — tags now on the Heptabase card.

    Returns (to_add, to_remove, final): the tags to `tag add` / `tag remove`
    on the card, and the resulting set. Tags are sets, so the merge never
    conflicts: local additions/removals apply, remote-only additions survive.
    """
    base, local, remote = set(base), set(local), set(remote)
    added_local = local - base
    removed_local = base - local
    final = (remote | added_local) - removed_local
    to_add = final - remote
    to_remove = remote - final
    return sorted(to_add), sorted(to_remove), sorted(final)


def find_similar_tag(name, existing, threshold=0.8):
    """If `name` is not a case-sensitive exact member of `existing` but is
    close to one (case-folded difflib ratio >= threshold), return that
    closest tag; otherwise return None.

    A case-only difference (e.g. "heptasync" vs "HeptaSync") IS surfaced as a
    hit — Heptabase tag names are case-sensitive, so `tag add` on the wrong
    casing would spawn a near-duplicate; the caller stops and asks either way.
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
