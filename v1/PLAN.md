# HeptaSync v1 — POC 修正實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修掉 `DESIGN.md` §8.7 的程式級 bug,讓 `hs pull` / `hs push` 完全符合 §8 的語意設計。

**Architecture:** 在既有 POC 之上,新增 `v1/skill/scripts/vault.py`(vault 探測 / 以 cardId 找檔 / `state.json`)與 `v1/skill/scripts/tagsync.py`(3-way tag 合併、模糊比對),修正 `v1/skill/scripts/frontmatter.py`、`v1/skill/scripts/pm2md.py`、`v1/skill/scripts/htb.py`,並重寫 `v1/skill/scripts/hs.py` 的 `pull` / `push`。純邏輯走 TDD(stdlib `unittest`);`pull` / `push` / 衝突走對真實 Heptabase 的整合驗證。

**Tech Stack:** Python 3.9+ stdlib only;官方 `heptabase` CLI 0.3.x;測試用 stdlib `unittest`。

---

## 前置

- 此 repo 目前**不是** git repository。**Task 0** 會 `git init`,並在改結構前先 commit 一次現狀(把 `poc/` 留在 git 歷史)。
- 整合驗證 Task(7–12)需 Heptabase desktop app 開著(`heptabase start`),且 `heptabase --version` 落在 `0.3.x`。
- 純邏輯 Task(0–6)多數不需 Heptabase,可離線完成。

## 範圍

本計畫分三階段:

- **Phase 0 — 結構落定**(Task 0):`git init`、解散 `poc/`、產品程式就位到 `v1/skill/scripts/`(DESIGN.md §9.3)。
- **Phase 1 — 引擎修正(§8.7)**(Task 1–11):修掉 §8.7 的 8 條程式級修正事項(第 2 條為純文件修正,已完成),讓 `hs pull` / `hs push` 對 note 卡片雙向同步正確、有衝突偵測與處理、有 tag 3-way 同步。
- **Phase 2 — 封裝與多平台(§9)**(Task 12–14):加 `hs doctor` 環境 preflight、寫三平台通用 `SKILL.md`、寫好各平台安裝。`v1/skill/` 在 Task 0 後即出貨形狀,**無 build 步驟**。

**仍不在範圍內**:新指令(`hs sync` / `status` / `trash` / `tags` / `init`),以及 §9.2 的全面結構化輸出(本計畫僅 `hs doctor` 先採結構化)。

§8.7 對應:

| §8.7 修正事項 | Task |
|---|---|
| 1. `_vault_root` 改探測 `.heptasync/` | Task 4, Task 7 |
| 3. push 樂觀鎖失效 + 無衝突處理 | Task 8, Task 9 |
| 4. `frontmatter.py` 配合新 schema | Task 1 |
| 5. `pm2md.py` 有序清單序號 | Task 2 |
| 6. `pull` 重複檔(無 cardId→檔案對應) | Task 4, Task 7 |
| 7. tag 同步雙向皆未實作 | Task 5, Task 6, Task 7, Task 10 |
| 8. `htb.tag_remove` 用錯參數 | Task 3 |

§9 對應:

| §9 章節 | Task |
|---|---|
| §9.3 結構落定(skill 目錄即 repo 目錄、`poc/` 解散) | Task 0 |
| §9.4 `hs doctor` preflight | Task 12 |
| §9.3 通用 `SKILL.md` | Task 13 |
| §9.3 三平台安裝 | Task 14 |

## File Structure

| 檔案 | 動作 | 責任 |
|---|---|---|
| `v1/skill/scripts/` | 新增(Task 0) | `poc/` 解散後,7 個產品模組 + `hs` shim 的家 |
| `v1/EXPERIMENTS.md` | 移入(Task 0) | 由 `poc/EXPERIMENTS.md` 搬入,保留實驗佐證 |
| `v1/skill/scripts/frontmatter.py` | 修改 | v1 schema:`schemaVersion`、移除 `title` |
| `v1/skill/scripts/pm2md.py` | 修改 | 有序清單序號遞增 |
| `v1/skill/scripts/htb.py` | 修改 | `tag_remove` 改用 `--tag-id` |
| `v1/skill/scripts/vault.py` | 新增 | vault 探測、以 cardId 找檔、`state.json` 讀寫 |
| `v1/skill/scripts/tagsync.py` | 新增 | tag 3-way 合併、模糊比對 |
| `v1/skill/scripts/hs.py` | 修改 | 重寫 `pull` / `push`,接上 `vault` / `tagsync`,加 `doctor` |
| `v1/skill/scripts/hs` | 新增(Task 0) | `#!/usr/bin/env python3` shim,import 同目錄 `hs.py` |
| `v1/tests/test_*.py` | 新增 | `frontmatter` / `pm2md` / `htb` / `vault` / `tagsync` / `doctor` 單元測試 |
| `v1/skill/SKILL.md` | 重寫 | 三平台通用 skill:合約本體 + preflight 規範(Phase 2) |
| `v1/INSTALL.md` | 新增 | 三平台安裝說明(Phase 2) |
| `.claude-plugin/plugin.json`、`marketplace.json` | 新增 | Claude Code plugin 一鍵安裝(Phase 2,選配) |

測試慣例:測試檔放 `v1/tests/`,開頭以 `sys.path` 接上 `v1/skill/scripts/`,結尾 `unittest.main()`,以 `python3 v1/tests/test_X.py` 執行。

---

# Phase 0 — 結構落定

## Task 0: 解散 `poc/`,產品程式就位到 `v1/skill/`

**Files:**
- Create: `v1/skill/scripts/`
- Move: `v1/hs.py`、`v1/frontmatter.py`、`poc/pm2md.py`、`poc/transplant.py`、`poc/htb.py` → `v1/skill/scripts/`
- Move: `poc/EXPERIMENTS.md` → `v1/EXPERIMENTS.md`;Delete: `poc/` 其餘實驗腳本
- Create: `v1/skill/scripts/hs`
- Modify: `v1/skill/scripts/hs.py`(import bootstrap)

DESIGN.md §9.3:`v1/skill/` 直接以可出貨形狀存在於 repo,無 build 步驟;產品程式放 `scripts/`(Anthropic skill 慣例);POC 已完成,`poc/` 解散。(`DESIGN.md` 內的 `poc/` 引用已於設計階段更新。)

- [ ] **Step 1: `git init` 並保存現狀**

```bash
git init
git add -A
git commit -m "chore: snapshot before v1 restructure (preserves poc/ in history)"
```

- [ ] **Step 2: 建立 skill 目錄、搬移檔案**

```bash
mkdir -p v1/skill/scripts
git mv v1/hs.py v1/frontmatter.py v1/skill/scripts/
git mv poc/pm2md.py poc/transplant.py poc/htb.py v1/skill/scripts/
git mv poc/EXPERIMENTS.md v1/EXPERIMENTS.md
git rm -r poc
```

- [ ] **Step 3: 修 `hs.py` 的 import bootstrap**

`v1/skill/scripts/hs.py` 開頭現行(約 :23-30):

```python
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)                                 # frontmatter.py
sys.path.insert(0, os.path.join(_HERE, "..", "poc"))      # htb, pm2md, transplant
```

所有模組現在同在 `scripts/`,替換為:

```python
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)                                 # all modules co-located
```

- [ ] **Step 4: 建立 `v1/skill/scripts/hs` 可執行 shim**

`scripts/hs`(無副檔名)以 `realpath` 自我定位、把自己的目錄加進 `sys.path`、import 同目錄的 `hs.py` 並呼叫 `main`:

```bash
cat > v1/skill/scripts/hs <<'EOF'
#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import hs
sys.exit(hs.main(sys.argv))
EOF
chmod +x v1/skill/scripts/hs
```

- [ ] **Step 5: 驗證**

```bash
python3 v1/skill/scripts/hs.py 2>&1 | head -3
./v1/skill/scripts/hs 2>&1 | head -3
test ! -d poc && echo "poc/ removed"
```

Expected:`hs.py` 與 `bin/hs` 都印出用法說明、無 `ImportError`;`poc/` 已不存在。

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: dissolve poc/, product code lives in v1/skill/"
```

---

# Phase 1 — 引擎修正(§8.7)

## Task 1: `frontmatter.py` 採用 v1 schema

**Files:**
- Modify: `v1/skill/scripts/frontmatter.py`(`SCHEMA_FIELDS` 約在 :36;`build_note_meta` 約在 :64-79)
- Test: `v1/tests/test_frontmatter.py`

- [ ] **Step 1: 寫失敗測試**

建立 `v1/tests/test_frontmatter.py`:

```python
import os, sys, unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "v1", "skill", "scripts"))
import frontmatter


class TestV1Schema(unittest.TestCase):
    def test_build_note_meta_has_schema_version_not_title(self):
        rec = {"id": "abc", "title": "T", "contentMd5": "m"}
        meta = frontmatter.build_note_meta(
            rec, tags=["x"], synced_at="2026-01-01T00:00:00Z")
        hb = meta[frontmatter.MANAGED_KEY]
        self.assertEqual(hb["schemaVersion"], 1)
        self.assertNotIn("title", hb)
        self.assertEqual(hb["cardId"], "abc")
        self.assertEqual(hb["tags"], ["x"])
        self.assertEqual(hb["contentMd5"], "m")

    def test_round_trip_new_schema(self):
        src = ("---\n"
               "heptabase:\n"
               "  schemaVersion: 1\n"
               "  cardId: abc\n"
               "  type: note\n"
               "  tags:\n"
               "    - HeptaSync\n"
               "  whiteboards: []\n"
               "  contentMd5: m\n"
               "  syncedAt: 2026-01-01T00:00:00Z\n"
               "---\n"
               "# Title\n\nbody\n")
        meta, body = frontmatter.parse(src)
        self.assertEqual(meta["heptabase"]["schemaVersion"], 1)
        self.assertEqual(body, "# Title\n\nbody\n")
        meta2, body2 = frontmatter.parse(frontmatter.serialize(meta, body))
        self.assertEqual(meta, meta2)
        self.assertEqual(body, body2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 執行,確認失敗**

Run: `python3 v1/tests/test_frontmatter.py`
Expected: FAIL — `build_note_meta` 目前產出含 `title`、無 `schemaVersion`。

- [ ] **Step 3: 改 `frontmatter.py`**

在 `MANAGED_KEY = "heptabase"` 下方加常數,並替換 `SCHEMA_FIELDS`:

```python
MANAGED_KEY = "heptabase"
SCHEMA_VERSION = 1

# The managed keys, in canonical emit order.
SCHEMA_FIELDS = ["schemaVersion", "cardId", "type", "tags", "whiteboards",
                 "contentMd5", "syncedAt"]
```

整個替換 `build_note_meta`:

```python
def build_note_meta(card_record, tags=None, whiteboards=None, synced_at=None):
    """Build the managed frontmatter dict for a note card.

    card_record: a dict from `heptabase note read` (id, contentMd5).
    The card title is NOT stored — its source of truth is the body's first H1
    (see DESIGN.md §8.3). `dict` insertion order below IS the emit order and
    must match SCHEMA_FIELDS.
    """
    hb = {
        "schemaVersion": SCHEMA_VERSION,
        "cardId": card_record.get("id"),
        "type": "note",
        "tags": list(tags or []),
        "whiteboards": list(whiteboards or []),
        "contentMd5": card_record.get("contentMd5"),
        "syncedAt": synced_at,
    }
    return {MANAGED_KEY: hb}
```

- [ ] **Step 4: 執行,確認通過**

Run: `python3 v1/tests/test_frontmatter.py`
Expected: PASS（2 tests）。

- [ ] **Step 5: Commit**

```bash
git add v1/skill/scripts/frontmatter.py v1/tests/test_frontmatter.py
git commit -m "fix(frontmatter): adopt v1 schema (schemaVersion, drop title)"
```

---

## Task 2: `pm2md.py` 有序清單序號遞增

**Files:**
- Modify: `v1/skill/scripts/pm2md.py`(`convert` :24-39;`_block` :42-72;`_list_item` :74-92)
- Test: `v1/tests/test_pm2md.py`

- [ ] **Step 1: 寫失敗測試**

建立 `v1/tests/test_pm2md.py`:

```python
import os, sys, unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "v1", "skill", "scripts"))
import pm2md


def _num(text):
    return {"type": "numbered_list_item",
            "content": [{"type": "paragraph",
                         "content": [{"type": "text", "text": text}]}]}


def _para(text):
    return {"type": "paragraph",
            "content": [{"type": "text", "text": text}]}


class TestNumbering(unittest.TestCase):
    def test_consecutive_items_increment(self):
        doc = {"type": "doc", "content": [_num("a"), _num("b"), _num("c")]}
        md, _ = pm2md.to_markdown(doc)
        self.assertEqual(md, "1. a\n2. b\n3. c")

    def test_run_resets_after_non_numbered(self):
        doc = {"type": "doc", "content": [_num("a"), _para("x"), _num("b")]}
        md, _ = pm2md.to_markdown(doc)
        self.assertIn("1. a", md)
        self.assertIn("1. b", md)
        self.assertNotIn("2. b", md)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 執行,確認失敗**

Run: `python3 v1/tests/test_pm2md.py`
Expected: FAIL — `test_consecutive_items_increment` 得到 `1. a\n1. b\n1. c`。

- [ ] **Step 3: 改 `v1/skill/scripts/pm2md.py`**

在 `_LIST_ITEM_TYPES` 字典下方加:

```python
# Numbered-list node types — their marker is computed per run, not from the
# table above (the "1. " entries are only used for membership checks).
_NUMBERED_TYPES = {"numbered_list_item", "ordered_list_item"}
```

整個替換 `convert`:

```python
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
```

把 `_block` 的簽名改為帶 `ordinal`,並把它傳進 `_list_item`:

```python
    def _block(self, node, depth, ordinal=1):
```

且把 `_block` 內這一行:

```python
        if t in _LIST_ITEM_TYPES:
            return self._list_item(t, node, depth)
```

改為:

```python
        if t in _LIST_ITEM_TYPES:
            return self._list_item(t, node, depth, ordinal)
```

整個替換 `_list_item`:

```python
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
```

- [ ] **Step 4: 執行,確認通過**

Run: `python3 v1/tests/test_pm2md.py`
Expected: PASS（2 tests）。

- [ ] **Step 5: Commit**

```bash
git add v1/skill/scripts/pm2md.py v1/tests/test_pm2md.py
git commit -m "fix(pm2md): emit sequential ordinals for numbered lists"
```

---

## Task 3: `htb.tag_remove` 改用 `--tag-id`

**Files:**
- Modify: `v1/skill/scripts/htb.py`(`tag_remove` :152-153)
- Test: `v1/tests/test_htb_args.py`

- [ ] **Step 1: 寫失敗測試**

建立 `v1/tests/test_htb_args.py`(以 monkeypatch `_run` 攔截參數,不碰真實 CLI):

```python
import os, sys, unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "v1", "skill", "scripts"))
import htb


class TestTagRemoveArgs(unittest.TestCase):
    def test_tag_remove_uses_tag_id(self):
        captured = []
        original = htb._run
        htb._run = lambda args: captured.append(args)
        try:
            htb.tag_remove("card-1", "tag-uuid-1")
        finally:
            htb._run = original
        self.assertEqual(
            captured[0],
            ["tag", "remove", "--card-id", "card-1", "--tag-id", "tag-uuid-1"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 執行,確認失敗**

Run: `python3 v1/tests/test_htb_args.py`
Expected: FAIL — 目前傳的是 `--tag-name`。

- [ ] **Step 3: 改 `v1/skill/scripts/htb.py`**

整個替換 `tag_remove`:

```python
def tag_remove(card_id, tag_id):
    """Remove a tag from a card. `tag_id` is the tag's UUID (resolve a tag
    name to its id via `tag_list` first)."""
    return _run(["tag", "remove", "--card-id", card_id, "--tag-id", tag_id])
```

- [ ] **Step 4: 執行,確認通過**

Run: `python3 v1/tests/test_htb_args.py`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add v1/skill/scripts/htb.py v1/tests/test_htb_args.py
git commit -m "fix(htb): tag_remove must pass --tag-id, not --tag-name"
```

---

## Task 4: `vault.py` — vault 探測與以 cardId 找檔

**Files:**
- Create: `v1/skill/scripts/vault.py`
- Test: `v1/tests/test_vault.py`

- [ ] **Step 1: 寫失敗測試**

建立 `v1/tests/test_vault.py`:

```python
import os, sys, tempfile, unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "v1", "skill", "scripts"))
import vault


class TestVaultDiscovery(unittest.TestCase):
    def test_find_vault_root_walks_up_to_heptasync_dir(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, ".heptasync"))
            deep = os.path.join(root, "notes", "sub")
            os.makedirs(deep)
            f = os.path.join(deep, "x.md")
            open(f, "w").close()
            self.assertEqual(vault.find_vault_root(f), root)
            self.assertEqual(vault.find_vault_root(deep), root)

    def test_find_vault_root_returns_none_when_absent(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertIsNone(vault.find_vault_root(root))

    def test_find_file_by_card_id_matches_frontmatter(self):
        with tempfile.TemporaryDirectory() as root:
            notes = os.path.join(root, "notes", "deep")
            os.makedirs(notes)
            hit = os.path.join(notes, "a.md")
            with open(hit, "w", encoding="utf-8") as fh:
                fh.write("---\nheptabase:\n  cardId: CID-1\n---\n# a\n")
            miss = os.path.join(root, "notes", "b.md")
            with open(miss, "w", encoding="utf-8") as fh:
                fh.write("---\nheptabase:\n  cardId: CID-2\n---\n# b\n")
            self.assertEqual(vault.find_file_by_card_id(root, "CID-1"), hit)
            self.assertIsNone(vault.find_file_by_card_id(root, "CID-MISSING"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 執行,確認失敗**

Run: `python3 v1/tests/test_vault.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'vault'`。

- [ ] **Step 3: 建立 `v1/skill/scripts/vault.py`**

```python
"""HeptaSync v1 — vault layer: discovery, card->file lookup, sync state.

The vault root is the nearest ancestor directory containing `.heptasync/`
(the same idea as git locating `.git/`). See DESIGN.md §8.2.
"""
from __future__ import annotations

import json
import os

import frontmatter

STATE_DIR = ".heptasync"
STATE_FILE = "state.json"


def find_vault_root(start):
    """Walk up from `start` (a file or dir) to the dir holding `.heptasync/`.
    Returns the vault root path, or None if no vault encloses `start`."""
    d = os.path.abspath(start)
    if os.path.isfile(d):
        d = os.path.dirname(d)
    while True:
        if os.path.isdir(os.path.join(d, STATE_DIR)):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def find_file_by_card_id(vault, card_id):
    """Scan `vault/notes/**` for the .md whose frontmatter cardId matches.
    Returns the file path, or None on first sync of this card."""
    notes = os.path.join(vault, "notes")
    for root, _dirs, files in os.walk(notes):
        for name in sorted(files):
            if not name.endswith(".md"):
                continue
            path = os.path.join(root, name)
            try:
                text = open(path, encoding="utf-8").read()
            except OSError:
                continue
            meta, _ = frontmatter.parse(text)
            hb = meta.get(frontmatter.MANAGED_KEY, {})
            if hb.get("cardId") == card_id:
                return path
    return None
```

- [ ] **Step 4: 執行,確認通過**

Run: `python3 v1/tests/test_vault.py`
Expected: PASS（3 tests）。

- [ ] **Step 5: Commit**

```bash
git add v1/skill/scripts/vault.py v1/tests/test_vault.py
git commit -m "feat(vault): vault discovery and card-id file lookup"
```

---

## Task 5: `vault.py` — `state.json` 存 tag base

**Files:**
- Modify: `v1/skill/scripts/vault.py`
- Test: `v1/tests/test_vault.py`

- [ ] **Step 1: 加失敗測試**

在 `v1/tests/test_vault.py` 的 `TestVaultDiscovery` 之後追加類別:

```python
class TestVaultState(unittest.TestCase):
    def test_tag_base_round_trips(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, ".heptasync"))
            self.assertEqual(vault.get_tag_base(root, "CID-1"), [])
            vault.set_tag_base(root, "CID-1", ["work", "urgent"])
            self.assertEqual(
                sorted(vault.get_tag_base(root, "CID-1")), ["urgent", "work"])
            # a second card does not disturb the first
            vault.set_tag_base(root, "CID-2", ["q2"])
            self.assertEqual(
                sorted(vault.get_tag_base(root, "CID-1")), ["urgent", "work"])
```

- [ ] **Step 2: 執行,確認失敗**

Run: `python3 v1/tests/test_vault.py`
Expected: FAIL — `vault` 無 `get_tag_base` / `set_tag_base`。

- [ ] **Step 3: 加進 `v1/skill/scripts/vault.py`**

在檔尾追加:

```python
# -- sync state (.heptasync/state.json) -----------------------------------
def _state_path(vault):
    return os.path.join(vault, STATE_DIR, STATE_FILE)


def load_state(vault):
    """Return the parsed state.json, or a fresh skeleton if absent/corrupt."""
    try:
        with open(_state_path(vault), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"cards": {}}


def save_state(vault, state):
    path = _state_path(vault)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_tag_base(vault, card_id):
    """The tag set recorded at the last sync — the base for 3-way tag merge."""
    return list(load_state(vault).get("cards", {})
                .get(card_id, {}).get("tags", []))


def set_tag_base(vault, card_id, tags):
    state = load_state(vault)
    state.setdefault("cards", {}).setdefault(card_id, {})["tags"] = list(tags)
    save_state(vault, state)
```

- [ ] **Step 4: 執行,確認通過**

Run: `python3 v1/tests/test_vault.py`
Expected: PASS（4 tests）。

- [ ] **Step 5: Commit**

```bash
git add v1/skill/scripts/vault.py v1/tests/test_vault.py
git commit -m "feat(vault): state.json stores per-card tag base"
```

---

## Task 6: `tagsync.py` — 3-way 合併與模糊比對

**Files:**
- Create: `v1/skill/scripts/tagsync.py`
- Test: `v1/tests/test_tagsync.py`

- [ ] **Step 1: 寫失敗測試**

建立 `v1/tests/test_tagsync.py`:

```python
import os, sys, unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "v1", "skill", "scripts"))
import tagsync


class TestMergeTags(unittest.TestCase):
    def test_design_example_keeps_remote_addition(self):
        # DESIGN.md §8.5: base [work], local +urgent, remote +q2
        to_add, to_remove, final = tagsync.merge_tags(
            ["work"], ["work", "urgent"], ["work", "q2"])
        self.assertEqual(to_add, ["urgent"])
        self.assertEqual(to_remove, [])
        self.assertEqual(final, ["q2", "urgent", "work"])

    def test_local_removal_is_applied(self):
        to_add, to_remove, final = tagsync.merge_tags(["a"], [], ["a"])
        self.assertEqual(to_remove, ["a"])
        self.assertEqual(final, [])

    def test_local_add_to_untagged_card(self):
        to_add, to_remove, final = tagsync.merge_tags([], ["x"], [])
        self.assertEqual(to_add, ["x"])
        self.assertEqual(final, ["x"])


class TestFuzzy(unittest.TestCase):
    def test_typo_finds_similar(self):
        self.assertEqual(
            tagsync.find_similar_tag("Heptasync", ["HeptaSync", "work"]),
            "HeptaSync")

    def test_exact_match_is_not_ambiguous(self):
        self.assertIsNone(
            tagsync.find_similar_tag("HeptaSync", ["HeptaSync", "work"]))

    def test_genuinely_new_tag_has_no_match(self):
        self.assertIsNone(
            tagsync.find_similar_tag("quarterly", ["HeptaSync", "work"]))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 執行,確認失敗**

Run: `python3 v1/tests/test_tagsync.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'tagsync'`。

- [ ] **Step 3: 建立 `v1/skill/scripts/tagsync.py`**

```python
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
    """If `name` is not an exact existing tag but is close to one, return that
    closest tag (a likely typo); otherwise return None."""
    if name in existing:
        return None
    low = name.lower()
    best, best_score = None, 0.0
    for candidate in existing:
        score = difflib.SequenceMatcher(None, low, candidate.lower()).ratio()
        if score > best_score:
            best, best_score = candidate, score
    return best if best_score >= threshold else None
```

- [ ] **Step 4: 執行,確認通過**

Run: `python3 v1/tests/test_tagsync.py`
Expected: PASS（6 tests）。

- [ ] **Step 5: Commit**

```bash
git add v1/skill/scripts/tagsync.py v1/tests/test_tagsync.py
git commit -m "feat(tagsync): 3-way tag merge and fuzzy-match guard"
```

---

## Task 7: `hs.py` 重寫 `pull` — 就地更新 + tag + 新 schema

**Files:**
- Modify: `v1/skill/scripts/hs.py`(imports :27-30;`_vault_root` :38-41;`_slug` :50-52;`pull` :96-106)

修正 §8.7 第 1、6、7(pull 方向)條:`pull` 改以 cardId 找既有檔就地更新、補同步 tag、用新 schema。

- [ ] **Step 1: 接上 `vault` / `tagsync` 模組**

在 `v1/skill/scripts/hs.py` 的 import 區(`import transplant` 之後)加入:

```python
import vault as vaultlib   # noqa: E402
import tagsync             # noqa: E402
```

舊的 `_vault_root`(:38-41)**暫時保留** —— `pull` 用不到它,但舊 `push` 仍在用;Task 8 重寫 `push` 後才刪,以確保每個 Task 之間程式都可運作。`_sidecar_path` 維持不變。

- [ ] **Step 2: 加 slug 撞名處理 helper**

在 `_slug` 之後加入(§8.3:撞名加 cardId 短前綴):

```python
def _slug_path(notes_dir, title, card_id):
    """First-pull file path for a card. On slug collision, disambiguate with
    a short cardId prefix so two cards never claim one file."""
    slug = _slug(title)
    path = os.path.join(notes_dir, slug + ".md")
    if not os.path.exists(path):
        return path
    return os.path.join(notes_dir, slug + "-" + card_id[:8] + ".md")
```

- [ ] **Step 3: 整個替換 `pull`**

```python
def pull(card_id, vault):
    """Pull a Heptabase card into the vault as a HeptaSync note.

    If a file for this cardId already exists, it is updated in place (the
    filename never auto-changes — DESIGN.md §8.3). Otherwise a slug-named
    file is created. Tags are synced down from the card.
    """
    rec = htb.note_read(card_id)
    body, _ = pm2md.to_markdown(json.loads(rec["content"]))

    # tags currently on the card
    props = htb.card_properties(card_id)
    tags = sorted({t["tagName"] for t in props.get("tags", [])})

    # locate the existing file for this card, or pick a first-pull path
    path = vaultlib.find_file_by_card_id(vault, card_id)
    whiteboards = []
    if path is None:
        notes = os.path.join(vault, "notes")
        os.makedirs(notes, exist_ok=True)
        path = _slug_path(notes, rec["title"], card_id)
    else:
        # preserve the user-editable whiteboards field across a pull
        old_meta, _ = frontmatter.parse(open(path, encoding="utf-8").read())
        whiteboards = old_meta.get(frontmatter.MANAGED_KEY, {}).get(
            "whiteboards", [])

    meta = frontmatter.build_note_meta(
        rec, tags=tags, whiteboards=whiteboards, synced_at=_now())
    _write(path, frontmatter.serialize(meta, body))
    _write(_sidecar_path(vault, card_id), rec["content"])
    vaultlib.set_tag_base(vault, card_id, tags)
    return path
```

- [ ] **Step 4: 整合驗證 — 重複檔不再產生、tag 拉回**

需 Heptabase app 開著。對 `vault/notes/semantics-design.md`(cardId `993aa0e2-9af8-4897-98b5-35b5a334cf3b`,已掛 `HeptaSync` tag)執行:

```bash
ls vault/notes/
python3 v1/skill/scripts/hs.py pull 993aa0e2-9af8-4897-98b5-35b5a334cf3b vault
ls vault/notes/
grep -A2 "tags:" vault/notes/semantics-design.md
```

Expected:
- pull 後 `vault/notes/` **沒有**新增 `heptasync-v1-…白話版.md` —— 仍是 `heptasync.md` 與 `semantics-design.md`。
- `semantics-design.md` 的 frontmatter `tags:` 列出 `HeptaSync`(非 `[]`)。
- `vault/.heptasync/state.json` 出現該 cardId 的 `tags` 條目。

- [ ] **Step 5: Commit**

```bash
git add v1/skill/scripts/hs.py
git commit -m "fix(hs): pull updates the existing file in place and syncs tags down"
```

---

## Task 8: `hs.py` 重寫 `push` — 修正樂觀鎖

**Files:**
- Modify: `v1/skill/scripts/hs.py`(`push` :60-93)

修正 §8.7 第 3 條(鎖):樂觀鎖改用 frontmatter 裡「上次 pull 的 `contentMd5`」,不再重新 `note read` 取當下值。本 Task 先不做衝突處理(讓 `HtbError` 往上拋),Task 9 補。

- [ ] **Step 1: 整個替換 `push`**

```python
def push(path):
    """Sync a local HeptaSync note file up to Heptabase."""
    meta, body = frontmatter.parse(open(path, encoding="utf-8").read())
    hb = meta.get(frontmatter.MANAGED_KEY, {})
    card_id = hb.get("cardId")
    vault = vaultlib.find_vault_root(path)
    if vault is None:
        raise SystemExit("push: %s is not inside a HeptaSync vault" % path)

    if not card_id:
        # --- new note: Heptabase converts the markdown for us ------------
        card_id = htb.note_create(body)["id"]
        action = "created"
    else:
        # --- existing note: transplant block IDs, then save -------------
        old_doc = json.load(open(_sidecar_path(vault, card_id), encoding="utf-8"))
        lock_md5 = hb.get("contentMd5")          # the last-pull md5 = the lock
        scratch = htb.note_create(body)          # Heptabase does md -> JSON
        try:
            new_doc = json.loads(htb.note_read(scratch["id"])["content"])
            report = transplant.transplant_ids(old_doc, new_doc)
            htb.note_save(card_id, json.dumps(new_doc), lock_md5)
        finally:
            htb.card_trash(scratch["id"])
        action = "updated [%s]" % " ".join(
            "%s=%d" % (k, len(report[k]))
            for k in ("preserved", "edited", "reordered", "inserted", "deleted"))

    # persist sync state: sidecar JSON + refreshed frontmatter
    rec = htb.note_read(card_id)
    _write(_sidecar_path(vault, card_id), rec["content"])
    new_meta = frontmatter.build_note_meta(
        rec, tags=hb.get("tags"), whiteboards=hb.get("whiteboards"),
        synced_at=_now())
    _write(path, frontmatter.serialize(new_meta, body))
    return card_id, action
```

替換後,舊的 `_vault_root` 函式(:38-41)已無人使用 —— 一併刪除。

- [ ] **Step 2: 整合驗證 — 鎖能擋下 stale push**

需 Heptabase app 開著。製造「本地的 frontmatter `contentMd5` 已過時」的狀態並 push:

```bash
python3 - <<'EOF'
import subprocess, sys
sys.path.insert(0, "poc")
import htb
# 用官方 CLI 改遠端,使遠端 md5 前進、本地 frontmatter 的 md5 變 stale
htb.note_append("993aa0e2-9af8-4897-98b5-35b5a334cf3b",
                "\n樂觀鎖驗證行。\n")
print("remote advanced")
EOF
python3 v1/skill/scripts/hs.py push vault/notes/semantics-design.md ; echo "exit=$?"
```

Expected: `push` **失敗**並拋出含 `Content conflict` 的 `HtbError`(exit 非 0)—— 證明鎖已生效(對比修正前會靜默成功覆寫)。Task 9 會把這個錯誤轉成正常的衝突處理。

- [ ] **Step 3: Commit**

```bash
git add v1/skill/scripts/hs.py
git commit -m "fix(hs): push optimistic lock uses the last-pull contentMd5"
```

---

## Task 9: `hs.py` `push` — 衝突處理

**Files:**
- Modify: `v1/skill/scripts/hs.py`(`push`)

修正 §8.7 第 3 條(處理):偵測 `Content conflict` → 備份 `<slug>.conflict.md`、重新 pull 遠端覆蓋工作檔、回報(DESIGN.md §8.4)。

- [ ] **Step 1: 加 `_conflict_path` 與 `_handle_conflict`**

在 `pull` 之後加入:

```python
def _conflict_path(path):
    """`notes/foo.md` -> `notes/foo.conflict.md`."""
    stem, ext = os.path.splitext(path)
    return stem + ".conflict" + ext


def _handle_conflict(path, local_body, vault, card_id):
    """Remote changed since last pull: back up the local body, then re-pull
    the remote latest over the working file. The user reconciles by hand."""
    backup = _conflict_path(path)
    _write(backup, local_body)
    pull(card_id, vault)            # overwrites `path` with remote latest
    return card_id, "conflict (local saved to %s)" % os.path.basename(backup)
```

- [ ] **Step 2: 在 `push` 的 `note_save` 外包住衝突偵測**

把 Task 8 `push` 裡這一段:

```python
        try:
            new_doc = json.loads(htb.note_read(scratch["id"])["content"])
            report = transplant.transplant_ids(old_doc, new_doc)
            htb.note_save(card_id, json.dumps(new_doc), lock_md5)
        finally:
            htb.card_trash(scratch["id"])
```

替換為:

```python
        try:
            new_doc = json.loads(htb.note_read(scratch["id"])["content"])
            report = transplant.transplant_ids(old_doc, new_doc)
            try:
                htb.note_save(card_id, json.dumps(new_doc), lock_md5)
            except htb.HtbError as exc:
                if "Content conflict" in htb.error_detail(exc):
                    return _handle_conflict(path, body, vault, card_id)
                raise
        finally:
            htb.card_trash(scratch["id"])
```

- [ ] **Step 3: 整合驗證 — 衝突被偵測並處理**

需 Heptabase app 開著。沿用 Task 8 Step 2 製造的 stale 狀態(若已乾淨,先 `note_append` 改遠端再本地 `Edit` 一行):

```bash
python3 v1/skill/scripts/hs.py push vault/notes/semantics-design.md ; echo "exit=$?"
ls vault/notes/
```

Expected:
- `push` 回報 `conflict (local saved to semantics-design.conflict.md)`,exit 0。
- `vault/notes/semantics-design.conflict.md` 存在,內容是 push 前的本地 body。
- `vault/notes/semantics-design.md` 已被遠端最新版覆蓋,其 frontmatter `contentMd5` = 遠端現值。

- [ ] **Step 4: Commit**

```bash
git add v1/skill/scripts/hs.py
git commit -m "feat(hs): push detects Content conflict and backs up to .conflict.md"
```

---

## Task 10: `hs.py` `push` — tag 3-way 同步

**Files:**
- Modify: `v1/skill/scripts/hs.py`(`push`)

修正 §8.7 第 7 條(push 方向):push 成功後做 tag 3-way 同步。新 tag 與既有 tag 模糊相近時中止並回報(§8.5 防呆;互動式詢問屬 §9 後續計畫)。

- [ ] **Step 1: 加 `TagAmbiguityError` 與 `_sync_tags`**

在 `_handle_conflict` 之後加入:

```python
class TagAmbiguityError(SystemExit):
    """A frontmatter tag is suspiciously close to an existing one — likely a
    typo. Per DESIGN.md §8.5 we stop rather than silently create a new tag."""


def _sync_tags(vault, card_id, local_tags):
    """3-way sync the card's tags toward frontmatter `tags:`. Returns a short
    summary string. Raises TagAmbiguityError on a suspected typo."""
    base = vaultlib.get_tag_base(vault, card_id)
    props = htb.card_properties(card_id)
    remote = sorted({t["tagName"] for t in props.get("tags", [])})
    to_add, to_remove, final = tagsync.merge_tags(base, local_tags or [], remote)

    all_tags = [t["name"] for t in (htb.tag_list().get("tags") or [])]
    for name in to_add:
        similar = tagsync.find_similar_tag(name, all_tags)
        if similar:
            raise TagAmbiguityError(
                "tag '%s' is close to existing '%s' — fix the frontmatter "
                "tags: and push again (or keep it if it is intentional)"
                % (name, similar))
        htb.tag_add(card_id, name)

    id_by_name = {t["name"]: t["id"] for t in (htb.tag_list().get("tags") or [])}
    for name in to_remove:
        if name in id_by_name:
            htb.tag_remove(card_id, id_by_name[name])

    vaultlib.set_tag_base(vault, card_id, final)
    return "tags +%d -%d" % (len(to_add), len(to_remove))
```

- [ ] **Step 2: 在 `push` 內呼叫 `_sync_tags`**

把 `push` 從 `# persist sync state` 註解到結尾 `return` 的整段(Task 8 寫入的那段),整段替換為下列 —— 它在持久化之前先做 tag 3-way 同步,並讓回寫的 frontmatter `tags:` 以同步後的真實結果為準。此處 `card_id` / `action` / `body` / `vault` / `hb` 皆為 `push` 既有的區域變數,衝突情況已在 Task 9 提前 `return`,故到這裡內容必定已安全寫回:

```python
    # sync tags (3-way) now that content is safely saved
    tag_summary = _sync_tags(vault, card_id, hb.get("tags"))
    action = action + "; " + tag_summary

    # persist sync state: sidecar JSON + refreshed frontmatter
    rec = htb.note_read(card_id)
    _write(_sidecar_path(vault, card_id), rec["content"])
    final_tags = vaultlib.get_tag_base(vault, card_id)
    new_meta = frontmatter.build_note_meta(
        rec, tags=final_tags, whiteboards=hb.get("whiteboards"),
        synced_at=_now())
    _write(path, frontmatter.serialize(new_meta, body))
    return card_id, action
```

- [ ] **Step 3: 整合驗證 — tag 雙向、3-way、防呆**

需 Heptabase app 開著。

```bash
# (a) 正常同步:在 frontmatter tags: 加一個全新 tag,push,確認卡片掛上
#     先用編輯器在 vault/notes/semantics-design.md 的 tags: 下加 "- pushtagtest"
python3 v1/skill/scripts/hs.py push vault/notes/semantics-design.md ; echo "exit=$?"
heptabase card properties 993aa0e2-9af8-4897-98b5-35b5a334cf3b | grep -i tag

# (b) 防呆:把 tags: 的 "HeptaSync" 改成 "Heptasync"(小寫 s),push
python3 v1/skill/scripts/hs.py push vault/notes/semantics-design.md ; echo "exit=$?"
```

Expected:
- (a):exit 0,`action` 含 `tags +1 -0`;`card properties` 列出 `pushtagtest`。
- (b):`push` 中止,印出 `tag 'Heptasync' is close to existing 'HeptaSync' …`,exit 非 0,卡片 tag **未被更動**。
- 還原:把 frontmatter tags: 改回正確值再 push 一次。

- [ ] **Step 4: Commit**

```bash
git add v1/skill/scripts/hs.py
git commit -m "feat(hs): push syncs tags 3-way with fuzzy-match guard"
```

---

## Task 11: 端到端驗證 — push / pull / 撞車

**Files:** 無(驗證用,需 Heptabase app 開著)

以一張全新乾淨的卡跑完整一圈,確認 8 條修正在真實環境中成立。

- [ ] **Step 1: 建立乾淨測試檔並首次 push**

```bash
mkdir -p vault-e2e/.heptasync vault-e2e/notes
cat > vault-e2e/notes/e2e.md <<'EOF'
# HeptaSync E2E 測試卡

## 步驟
1. 第一步
2. 第二步
3. 第三步
EOF
python3 v1/skill/scripts/hs.py push vault-e2e/notes/e2e.md ; echo "exit=$?"
```

Expected:exit 0、回報 `created`;`e2e.md` 取得 `heptabase:` frontmatter,含 `schemaVersion: 1`、新 `cardId`、無 `title` 欄位。

- [ ] **Step 2: pull 回來,驗證有序清單與身分**

```bash
CID=$(python3 -c "import sys; sys.path.insert(0,'v1/skill/scripts'); import frontmatter; m,_=frontmatter.parse(open('vault-e2e/notes/e2e.md').read()); print(m['heptabase']['cardId'])")
python3 v1/skill/scripts/hs.py pull "$CID" vault-e2e
ls vault-e2e/notes/
grep -n "步" vault-e2e/notes/e2e.md
```

Expected:`vault-e2e/notes/` 仍只有 `e2e.md`(無重複檔);內文有序清單為 `1. / 2. / 3.`(非 `1. / 1. / 1.`)。

- [ ] **Step 3: 撞車 — 確認衝突被偵測、不再靜默覆寫**

```bash
# 遠端改一行(用官方 CLI)
python3 -c "import sys; sys.path.insert(0,'v1/skill/scripts'); sys.path.insert(0,'v1/skill/scripts'); \
import frontmatter, htb; \
m,_=frontmatter.parse(open('vault-e2e/notes/e2e.md').read()); \
htb.note_append(m['heptabase']['cardId'], '\n遠端撞車行。\n')"
# 本地也改一行
printf '\n本地撞車行。\n' >> vault-e2e/notes/e2e.md
python3 v1/skill/scripts/hs.py push vault-e2e/notes/e2e.md ; echo "exit=$?"
ls vault-e2e/notes/
```

Expected:`push` 回報 `conflict (local saved to e2e.conflict.md)`;`e2e.conflict.md` 存在且含「本地撞車行。」;`e2e.md` 為遠端最新(含「遠端撞車行。」)。**遠端那行沒有被靜默吃掉** —— 與 dogfood 時的 Bug C 行為相反。

- [ ] **Step 4: 跑全部單元測試**

```bash
for t in v1/tests/test_*.py; do echo "== $t =="; python3 "$t" || exit 1; done
```

Expected:全部 PASS。

- [ ] **Step 5: 清理測試資料並 commit**

```bash
# trash 兩張測試卡(e2e 卡;撞車測試殘留)
python3 -c "import sys; sys.path.insert(0,'v1/skill/scripts'); sys.path.insert(0,'v1/skill/scripts'); \
import frontmatter, htb; \
m,_=frontmatter.parse(open('vault-e2e/notes/e2e.md').read()); \
htb.card_trash(m['heptabase']['cardId']); print('e2e card trashed')"
rm -rf vault-e2e
git add -A
git commit -m "test: end-to-end verification of v1 push/pull/conflict fixes"
```

---

# Phase 2 — 封裝與多平台(§9)

> Phase 2 在 Phase 1 完成(引擎正確)後進行。產物:三平台(Claude Code / Codex CLI / opencode)通用、可安裝的 HeptaSync Agent Skill。Task 0 後 `v1/skill/` 已是出貨形狀,故 Phase 2 只剩 preflight、`SKILL.md`、安裝三件事。

## Task 12: `hs doctor` 環境 preflight

**Files:**
- Modify: `v1/skill/scripts/hs.py`(加 `_version_supported`、`doctor`,並在 `main` 加子指令)
- Test: `v1/tests/test_doctor.py`

DESIGN.md §9.4:同步前檢查 Heptabase CLI 是否安裝、版本相容、app 是否運行。

- [ ] **Step 1: 寫失敗測試(版本判斷為純邏輯)**

建立 `v1/tests/test_doctor.py`:

```python
import os, sys, unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "v1", "skill", "scripts"))
import hs


class TestVersionGate(unittest.TestCase):
    def test_supported_minor(self):
        self.assertTrue(hs._version_supported("0.3.0"))
        self.assertTrue(hs._version_supported("0.3.9"))

    def test_unsupported_minor(self):
        self.assertFalse(hs._version_supported("0.2.9"))
        self.assertFalse(hs._version_supported("0.4.0"))

    def test_garbage(self):
        self.assertFalse(hs._version_supported(""))
        self.assertFalse(hs._version_supported("not-a-version"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 執行,確認失敗**

Run: `python3 v1/tests/test_doctor.py`
Expected: FAIL — `hs` 無 `_version_supported`(`AttributeError`)。

- [ ] **Step 3: 在 `hs.py` 加 `_version_supported` 與 `doctor`**

在 `main` 之前加入(`SUPPORTED_RANGE` 與官方 `heptabase-cli` skill 的 `0.3.x` 一致):

```python
SUPPORTED_RANGE = "0.3."          # accept 0.3.x


def _version_supported(version):
    """True if a `heptabase --version` string is within the supported range."""
    return bool(version) and version.strip().startswith(SUPPORTED_RANGE)


def doctor():
    """Preflight: verify the Heptabase CLI is installed, compatible, and the
    desktop app is running. Returns (status, detail). See DESIGN.md §9.4."""
    import shutil
    if shutil.which("heptabase") is None:
        return "cli-missing", "heptabase CLI not found on PATH"
    version = htb.version()
    if not _version_supported(version):
        return ("cli-version-unsupported",
                "heptabase %s is outside the supported %sx range"
                % (version or "?", SUPPORTED_RANGE))
    try:
        htb.card_list(limit=1)
    except htb.HtbError as exc:
        return "app-not-running", htb.error_detail(exc)
    return "ok", "heptabase %s, desktop app reachable" % version
```

在 `main` 中,於現有 `if len(argv) == 3 and argv[1] == "push":` **之前**插入:

```python
    if len(argv) == 2 and argv[1] == "doctor":
        status, detail = doctor()
        print(json.dumps({"command": "doctor", "status": status,
                          "detail": detail}, ensure_ascii=False))
        return 0 if status == "ok" else 2
```

- [ ] **Step 4: 執行單元測試,確認通過**

Run: `python3 v1/tests/test_doctor.py`
Expected: PASS（3 tests）。

- [ ] **Step 5: 整合驗證**

需 Heptabase app 開著。

```bash
python3 v1/skill/scripts/hs.py doctor ; echo "exit=$?"
```

Expected:印出 `{"command": "doctor", "status": "ok", "detail": "heptabase 0.3.0, ..."}`,exit 0。(可選:關掉 app 再跑 → `status` 為 `app-not-running`、exit 2。)

- [ ] **Step 6: Commit**

```bash
git add v1/skill/scripts/hs.py v1/tests/test_doctor.py
git commit -m "feat(hs): hs doctor preflight (CLI presence, version, app reachability)"
```

---

## Task 13: 重寫通用 `SKILL.md`

**Files:**
- Rewrite: `v1/skill/SKILL.md`

DESIGN.md §9.3:`v1/skill/` 即產品,Task 0 已就位 `lib/` 與 `bin/hs`;本 Task 只剩把 `SKILL.md` 寫成三平台通用的決策合約。**無 build 步驟、無 `dist/`。**

- [ ] **Step 1: 重寫 `v1/skill/SKILL.md` 為通用合約**

`SKILL.md` 內文即決策合約(§9.1/§9.2)。frontmatter 用三平台共通的 `name` / `description`。開頭強制 preflight:

```markdown
---
name: heptasync
description: Edit and reorganize existing Heptabase note cards via a local-markdown workflow — pull a card to a .md file, edit it as plain text, push it back. Handles edits to the middle of a card, which the raw heptabase CLI cannot do. UNOFFICIAL — not affiliated with Heptabase.
---

# HeptaSync (unofficial)

> UNOFFICIAL community tool. Built only on the official `heptabase` CLI;
> never touches Heptabase's database or internal files.

## Step 0 — preflight (MANDATORY)

Before any sync, run `hs doctor`. If `status` is not `ok`, STOP and tell the
user what its `detail` says (install the CLI / update it / start the app).
Never attempt a pull or push when doctor is not `ok`.

## Workflow

- `hs pull <cardId>` — card → a local `.md` file.
- edit the `.md` body with ordinary file tools (never edit the `heptabase:`
  frontmatter).
- `hs push <file>` — the edited `.md` → back into the same card.

For a plain new card or an append, use the official `heptabase` CLI directly.

## hs status → action contract

| `hs` status | agent action |
|---|---|
| `ok` | proceed |
| `cli-missing` / `cli-version-unsupported` / `app-not-running` | STOP; relay `detail` to the user |
| `conflict` | tell the user: their version was saved to `<slug>.conflict.md`, the working file now holds the remote latest; they reconcile by hand |
| `oversized` | do NOT auto-split; explain the reason and propose splitting at a heading boundary |
| `tag-ambiguous` | STOP; ask the user whether the new tag is intentional or a typo |

(完整 status 清單隨 §9.2 全面結構化輸出實作時補齊。)
```

- [ ] **Step 2: 驗證 skill 目錄完整可用**

```bash
./v1/skill/scripts/hs doctor ; echo "exit=$?"
head -4 v1/skill/SKILL.md
ls v1/skill v1/skill/lib v1/skill/scripts
```

Expected:`bin/hs doctor` 跑得起來(app 開著回 `status: ok`);`SKILL.md` 開頭是 `name` / `description` frontmatter;`v1/skill/` 含 `SKILL.md` + `lib/`(7 個 `.py`)+ `bin/hs` —— 已是完整、可直接安裝的 skill 目錄。

- [ ] **Step 3: Commit**

```bash
git add v1/skill/SKILL.md
git commit -m "feat(skill): universal SKILL.md decision contract"
```

---

## Task 14: 三平台安裝

**Files:**
- Create: `v1/INSTALL.md`
- Create(選配): `.claude-plugin/plugin.json`、`.claude-plugin/marketplace.json`

`v1/skill/` 本身就是要安裝的目錄。安裝 = 複製它到各工具的 skill 路徑 + 讓 `bin/hs` 上 PATH。

- [ ] **Step 1: Claude Code plugin manifest**

建立 `.claude-plugin/plugin.json`:

```json
{
  "name": "heptasync",
  "description": "Edit and reorganize existing Heptabase note cards via a local-markdown pull/edit/push workflow. UNOFFICIAL — not affiliated with Heptabase.",
  "version": "0.1.0",
  "author": { "name": "davidleitw", "email": "davidleitw@gmail.com" },
  "license": "MIT",
  "keywords": ["heptabase", "notes", "sync"]
}
```

建立 `.claude-plugin/marketplace.json`:

```json
{
  "name": "heptasync-marketplace",
  "owner": { "name": "davidleitw" },
  "description": "HeptaSync — unofficial Heptabase note-editing skill",
  "plugins": [
    {
      "name": "heptasync",
      "source": { "source": "github", "repo": "davidleitw/heptasync", "ref": "main" },
      "description": "Pull / edit / push existing Heptabase note cards"
    }
  ]
}
```

- [ ] **Step 2: 寫 `v1/INSTALL.md`**

```markdown
# 安裝 HeptaSync

先決:Python 3.9+、官方 `heptabase` CLI(0.3.x)、Heptabase 桌面 app。
HeptaSync 的 skill 目錄就是 repo 裡的 `v1/skill/` —— 沒有 build 步驟。

## Claude Code
手動:`cp -r v1/skill ~/.claude/skills/heptasync`。
或用 plugin marketplace(見 Step 1 的 manifest):
`/plugin marketplace add davidleitw/heptasync` →
`/plugin install heptasync@heptasync-marketplace`。

## Codex CLI
    cp -r v1/skill ~/.agents/skills/heptasync
    ln -s ~/.agents/skills/heptasync/bin/hs ~/.local/bin/hs

## opencode
    cp -r v1/skill ~/.config/opencode/skills/heptasync
    ln -s ~/.config/opencode/skills/heptasync/bin/hs ~/.local/bin/hs

裝完在任一工具裡跑 `hs doctor`,確認回 `status: ok`。
```

- [ ] **Step 3: 驗證 manifest 合法**

```bash
test -f .claude-plugin/plugin.json && test -f .claude-plugin/marketplace.json \
  && echo "manifests present"
python3 -c "import json; json.load(open('.claude-plugin/plugin.json')); \
json.load(open('.claude-plugin/marketplace.json')); print('json valid')"
```

Expected:印出 `manifests present` 與 `json valid`。

- [ ] **Step 4: Commit**

```bash
git add .claude-plugin/ v1/INSTALL.md
git commit -m "feat(dist): Claude Code plugin manifest and multi-tool install guide"
```
