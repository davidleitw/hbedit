"""Best-effort ProseMirror JSON -> Markdown converter for Heptabase cards.

Handles the node/mark types observed so far and *records* anything it does not
recognise (instead of silently dropping it) so round-trip fidelity can be
measured honestly.
"""
from __future__ import annotations
import copy as _copy_module
import re as _re_module

# Heptabase list-item node type -> markdown marker. Lists are flat node
# sequences (each item carries its own type), not wrapped in a list container.
_LIST_ITEM_TYPES = {
    "bullet_list_item": "- ",
    "numbered_list_item": "1. ",
    "ordered_list_item": "1. ",
    "todo_list_item": "- [ ] ",
}

# Numbered-list node types — their marker is computed per run, not from the
# table above (the "1. " entries are only used for membership checks).
_NUMBERED_TYPES = {"numbered_list_item", "ordered_list_item"}


class Converter:
    def __init__(self):
        self.unknown_nodes = set()
        self.unknown_marks = set()

    def convert(self, doc):
        """doc: parsed {"type": "doc", "content": [...]}. Returns markdown."""
        pieces = []          # (node_type, rendered_text)
        ordinal = 0          # running number for a numbered-list run
        prev = None
        for node in doc.get("content", []):
            ntype = node.get("type")
            if ntype in _NUMBERED_TYPES:
                ordinal = ordinal + 1 if prev == ntype else 1
            else:
                ordinal = 0
            rendered = self._block(node, depth=0, ordinal=ordinal)
            if rendered is not None:
                pieces.append((ntype, rendered))
            prev = ntype
        out = []
        for i, (ntype, text) in enumerate(pieces):
            if i > 0:
                prevt = pieces[i - 1][0]
                # Same-type adjacent list items form one tight list.
                tight = (ntype in _LIST_ITEM_TYPES and ntype == prevt)
                out.append("\n" if tight else "\n\n")
            out.append(text)
        return "".join(out)

    # -- block-level -------------------------------------------------------
    def _block(self, node, depth, ordinal=1):
        t = node.get("type")
        attrs = node.get("attrs", {})
        content = node.get("content", [])
        indent = "  " * depth

        if t == "heading":
            return "#" * attrs.get("level", 1) + " " + self._inline(content)
        if t == "paragraph":
            return indent + self._inline(content)
        if t in _LIST_ITEM_TYPES:
            return self._list_item(t, node, depth, ordinal)
        if t == "code_block":
            lang = attrs.get("params") or attrs.get("language") or attrs.get("lang") or ""
            return "```" + lang + "\n" + self._plain(content) + "\n```"
        if t in ("quote", "blockquote"):
            inner_blocks = [self._block(c, 0) for c in content]
            inner = "\n\n".join(b for b in inner_blocks if b is not None)
            return "\n".join(("> " + ln) if ln else ">" for ln in inner.split("\n"))
        if t in ("horizontal_rule", "divider"):
            return "---"
        if t in ("math", "math_block", "math_display"):
            return "$$\n" + (attrs.get("formula") or self._plain(content)) + "\n$$"
        if t == "image":
            return "![" + (attrs.get("alt") or "") + "](" + \
                   (attrs.get("src") or "") + ")"
        if t == "table":
            return self._table(content)

        self.unknown_nodes.add(t)
        return indent + "<!-- UNCONVERTED " + str(t) + ": " + self._inline(content) + " -->"

    def _list_item(self, t, node, depth, ordinal=1):
        indent = "  " * depth
        if t == "todo_list_item":
            marker = "- [x] " if node.get("attrs", {}).get("checked") else "- [ ] "
        elif t in _NUMBERED_TYPES:
            marker = "%d. " % ordinal
        else:
            marker = _LIST_ITEM_TYPES[t]
        # A Heptabase list item holds a paragraph plus any nested list items.
        own_text = ""
        nested = []
        nested_ord = 0       # running number for a nested numbered run
        prev_ct = None
        for child in node.get("content", []):
            ct = child.get("type")
            if ct == "paragraph" and not own_text:
                own_text = self._inline(child.get("content", []))
                prev_ct = ct
                continue
            if ct in _NUMBERED_TYPES:
                nested_ord = nested_ord + 1 if prev_ct == ct else 1
            else:
                nested_ord = 0
            if ct in _LIST_ITEM_TYPES:
                nested.append(self._list_item(ct, child, depth + 1, nested_ord))
            else:
                nested.append(self._block(child, depth + 1))
            prev_ct = ct
        line = indent + marker + own_text
        return "\n".join([line] + nested) if nested else line

    def _table(self, rows_nodes):
        rows = []
        for row in rows_nodes:
            if row.get("type") != "table_row":
                continue
            cells = []
            for cell in row.get("content", []):
                para = next((c for c in cell.get("content", [])
                             if c.get("type") == "paragraph"), None)
                cells.append(self._inline(para.get("content", []))
                             if para else "")
            rows.append(cells)
        if not rows:
            return ""
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        lines = ["| " + " | ".join(rows[0]) + " |",
                 "| " + " | ".join(["---"] * width) + " |"]
        for r in rows[1:]:
            lines.append("| " + " | ".join(r) + " |")
        return "\n".join(lines)

    # -- inline ------------------------------------------------------------
    def _inline(self, nodes):
        return "".join(self._inline_node(n) for n in nodes)

    def _inline_node(self, node):
        t = node.get("type")
        if t == "text":
            return self._apply_marks(node.get("text", ""), node.get("marks", []))
        if t == "card":
            return "[[card:" + node.get("attrs", {}).get("cardId", "?") + "]]"
        if t in ("hard_break", "br"):
            return "\n"
        if t == "math_inline":
            return "$" + self._plain(node.get("content", [])) + "$"
        self.unknown_nodes.add(t)
        return "<!-- UNCONVERTED inline " + str(t) + " -->"

    def _apply_marks(self, text, marks):
        href = None
        wrappers = []
        for mark in marks:
            mt = mark.get("type")
            if mt == "code":
                wrappers.append("`")
            elif mt in ("strong", "bold"):
                wrappers.append("**")
            elif mt in ("em", "italic"):
                wrappers.append("*")
            elif mt in ("strike", "strikethrough"):
                wrappers.append("~~")
            elif mt == "highlight":
                wrappers.append("==")
            elif mt == "link":
                href = mark.get("attrs", {}).get("href", "")
            else:
                self.unknown_marks.add(mt)
        for w in wrappers:
            text = w + text + w
        if href is not None:
            text = "[" + text + "](" + href + ")"
        return text

    def _plain(self, nodes):
        out = []
        for n in nodes:
            if n.get("type") == "text":
                out.append(n.get("text", ""))
            elif n.get("content"):
                out.append(self._plain(n["content"]))
        return "".join(out)


def to_markdown(doc):
    c = Converter()
    return c.convert(doc), c


# ---------------------------------------------------------------------
# Card placeholder substitution: `[[card:UUID]]` text → `card` node
# ---------------------------------------------------------------------

_CARD_PLACEHOLDER_RE = _re_module.compile(
    r"\[\[card:([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
    r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\]\]"
)


def substitute_card_placeholders(doc):
    """Return a new ProseMirror doc with `[[card:<uuid>]]` text occurrences
    replaced by `card` nodes. The input is not mutated."""
    return _walk_substitute(_copy_module.deepcopy(doc))


def _walk_substitute(node):
    if not isinstance(node, dict):
        return node
    # Do not descend into code_block subtrees.
    if node.get("type") == "code_block":
        return node
    children = node.get("content")
    if not children:
        return node
    new_children = []
    for child in children:
        if isinstance(child, dict) and child.get("type") == "text":
            new_children.extend(_split_text_on_placeholder(child))
        else:
            new_children.append(_walk_substitute(child))
    node["content"] = new_children
    return node


def _split_text_on_placeholder(text_node):
    # Text with `code` mark is treated as opaque — never substitute.
    for mark in text_node.get("marks") or []:
        if mark.get("type") == "code":
            return [text_node]
    text = text_node.get("text", "")
    matches = list(_CARD_PLACEHOLDER_RE.finditer(text))
    if not matches:
        return [text_node]
    marks = text_node.get("marks")
    result = []
    cursor = 0
    for m in matches:
        start, end = m.span()
        if start > cursor:
            seg = {"type": "text", "text": text[cursor:start]}
            if marks:
                seg["marks"] = marks
            result.append(seg)
        result.append({"type": "card",
                       "attrs": {"cardId": m.group(1).lower()}})
        cursor = end
    if cursor < len(text):
        seg = {"type": "text", "text": text[cursor:]}
        if marks:
            seg["marks"] = marks
        result.append(seg)
    return result
