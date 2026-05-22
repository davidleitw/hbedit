"""Push strategy: ID transplant.

The problem: `note save` needs ProseMirror JSON, but our local source of truth
is markdown an agent edited. Hand-writing a Markdown -> ProseMirror converter
that matches Heptabase's exact custom schema (every node type, every attr) is
fragile and lossy.

The strategy here avoids that entirely:

  1. Let Heptabase convert the edited markdown -> ProseMirror, by creating a
     throwaway "scratch" card from it (`note create`). That conversion is
     always schema-correct for every node type Heptabase supports.
  2. The scratch card has fresh block IDs. We *transplant* the original card's
     block IDs onto the blocks that survived the edit, so unchanged blocks keep
     their identity (and any Heptabase-internal block references stay valid).
  3. `note save` the result onto the real card; trash the scratch card.

This module is only step 2: align old vs new top-level blocks and copy IDs.
Alignment uses difflib (stdlib) over a per-block (type, plain-text) signature.
"""
from __future__ import annotations

import difflib


def block_text(node):
    """Concatenated plain text of every text leaf under a node."""
    out = []

    def visit(n):
        if isinstance(n, dict):
            if n.get("type") == "text":
                out.append(n.get("text", ""))
            for c in n.get("content", []) or []:
                visit(c)
        elif isinstance(n, list):
            for c in n:
                visit(c)

    visit(node)
    return "".join(out)


def _sig(node):
    return (node.get("type"), block_text(node))


def _bid(node):
    return node.get("attrs", {}).get("id")


def _copy_ids(old, new):
    """Copy IDs from `old` onto `new` recursively, where structure lines up."""
    oid = _bid(old)
    if oid:
        new.setdefault("attrs", {})["id"] = oid
    oc = old.get("content", []) or []
    nc = new.get("content", []) or []
    for o, n in zip(oc, nc):
        if isinstance(o, dict) and isinstance(n, dict) \
                and o.get("type") == n.get("type"):
            _copy_ids(o, n)


def transplant_ids(old_doc, new_doc, similarity=0.5):
    """Mutate new_doc in place: give surviving blocks their old IDs.

    Returns a report dict:
      preserved -- block IDs kept verbatim (unchanged blocks)
      edited    -- block IDs kept across an in-place text edit
      reordered -- block IDs kept across a position change
      inserted  -- IDs of genuinely new blocks (fresh)
      deleted   -- IDs of old blocks that no longer exist

    Algorithm: diff old vs new block signatures with difflib. `equal` regions
    transplant 1:1. Inside a `replace` region, old/new blocks are paired *by
    position* (a slot edited in place) — never across regions, so a new block
    can't steal a deleted block's ID just because they share boilerplate text.
    Leftovers are cross-matched only on *identical* signature, i.e. true
    reorder.
    """
    old = old_doc.get("content", [])
    new = new_doc.get("content", [])
    old_sigs = [_sig(n) for n in old]
    new_sigs = [_sig(n) for n in new]

    report = {"preserved": [], "edited": [], "reordered": [],
              "inserted": [], "deleted": []}
    leftover_old = []   # old indices still unmatched
    leftover_new = []   # new indices still unmatched

    matcher = difflib.SequenceMatcher(None, old_sigs, new_sigs, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                _copy_ids(old[i1 + k], new[j1 + k])
                report["preserved"].append(_bid(old[i1 + k]))
        elif tag == "delete":
            leftover_old += list(range(i1, i2))
        elif tag == "insert":
            leftover_new += list(range(j1, j2))
        elif tag == "replace":
            for off in range(max(i2 - i1, j2 - j1)):
                oi = i1 + off if off < i2 - i1 else None
                nj = j1 + off if off < j2 - j1 else None
                paired = (
                    oi is not None and nj is not None
                    and old[oi].get("type") == new[nj].get("type")
                    and difflib.SequenceMatcher(
                        None, block_text(old[oi]),
                        block_text(new[nj])).ratio() >= similarity)
                if paired:
                    _copy_ids(old[oi], new[nj])
                    report["edited"].append(_bid(old[oi]))
                else:
                    if oi is not None:
                        leftover_old.append(oi)
                    if nj is not None:
                        leftover_new.append(nj)

    # Reorder pass: a moved block keeps identical text+type, so match leftovers
    # only on an exact signature — never on fuzzy similarity.
    used = set()
    for nj in list(leftover_new):
        for oi in leftover_old:
            if oi not in used and _sig(old[oi]) == _sig(new[nj]):
                _copy_ids(old[oi], new[nj])
                report["reordered"].append(_bid(old[oi]))
                used.add(oi)
                leftover_new.remove(nj)
                break

    for nj in leftover_new:
        report["inserted"].append(_bid(new[nj]))   # fresh ID from `note create`
    for oi in leftover_old:
        if oi not in used:
            report["deleted"].append(_bid(old[oi]))
    return report
