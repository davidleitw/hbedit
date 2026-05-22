"""HeptaSync POC — the experiment suite.

Each `eNN` function runs one experiment and records what / how / result into the
harness. `ALL` is the ordered list the runner executes. Every card created here
is tracked in a `CardPool` and trashed at the end.
"""
from __future__ import annotations

import datetime
import json
import os
import time
import uuid

import frontmatter
import htb
import pm2md
import transplant

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


# -- shared helpers --------------------------------------------------------
class CardPool:
    """Tracks every note created during the run so it can be trashed after."""

    def __init__(self):
        self.cards = []

    def note(self, markdown):
        created = htb.note_create(markdown)
        self.cards.append(created["id"])
        return created["id"]

    def track(self, card_id):
        self.cards.append(card_id)
        return card_id

    def cleanup(self):
        trashed = 0
        for cid in reversed(self.cards):
            try:
                htb.card_trash(cid)
                trashed += 1
            except htb.HtbError:
                pass
        return trashed


def read_doc(card_id):
    r = htb.note_read(card_id)
    return json.loads(r["content"]), r["contentMd5"]


def top_ids(doc):
    return [n.get("attrs", {}).get("id") for n in doc.get("content", [])]


def histogram(doc):
    counts = {}

    def visit(n):
        if isinstance(n, dict):
            t = n.get("type")
            if t:
                counts[t] = counts.get(t, 0) + 1
            for c in n.get("content", []) or []:
                visit(c)
            for m in n.get("marks") or []:
                k = "mark:" + m.get("type", "?")
                counts[k] = counts.get(k, 0) + 1
        elif isinstance(n, list):
            for c in n:
                visit(c)

    visit(doc)
    return counts


def has_type(doc, *substrings):
    types = histogram(doc)
    for t in types:
        for s in substrings:
            if s in t:
                return t
    return None


def new_paragraph(text):
    return {"type": "paragraph", "attrs": {"id": str(uuid.uuid4())},
            "content": [{"type": "text", "text": text}]}


def norm(md):
    """Normalise markdown for comparison: trim trailing space, drop blank lines."""
    return "\n".join(ln.rstrip() for ln in md.splitlines() if ln.strip())


# -- E01 -------------------------------------------------------------------
E01_FIXTURE = """# E01 Extended Schema

## Todo

- [ ] unchecked task
- [x] checked task

## Divider

---

## Table

| Name | Value |
| ---- | ----- |
| a    | 1     |
| b    | 2     |

## Math

Inline math $a^2 + b^2 = c^2$ here.

$$
\\sum_{i=1}^{n} i
$$

## Image

![sample](https://example.com/sample.png)

## Mixed nested list

- bullet one
  1. numbered child
  2. another child
- bullet two
"""


def e01(suite, pool, state):
    with suite.experiment(
            "E01", "進階 schema 探索",
            "探索 Heptabase 對 todo、分隔線、表格、行內/區塊數學、圖片、混合巢狀清單等"
            "進階 markdown 會產生哪些 ProseMirror node/mark 類型 —— 這是轉換器必須"
            "支援的完整詞彙表。") as exp:
        exp.step("用一份涵蓋上述 7 類進階語法的 markdown 建立一張 note。")
        cid = pool.note(E01_FIXTURE)
        doc, _ = read_doc(cid)
        exp.step("`note read` 讀回,統計所有 node type 與 mark type。")
        hist = histogram(doc)
        state["e01_doc"] = doc
        with open(os.path.join(FIXTURE_DIR, "schema_extended.json"), "w") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
        exp.step("把完整 JSON 存到 fixtures/schema_extended.json 供檢視。")
        exp.info("node/mark 詞彙表", ", ".join(sorted(hist)))

        probes = [
            ("todo / checkbox", ("todo", "check", "task")),
            ("分隔線 horizontal rule", ("horizontal", "divider", "rule")),
            ("表格 table", ("table",)),
            ("數學 math", ("math", "equation", "katex")),
            ("圖片 image", ("image",)),
        ]
        for label, subs in probes:
            found = has_type(doc, *subs)
            if found:
                exp.check(label + " 有對應 node", True, "node type: " + found)
            else:
                exp.warn(label + " 無對應 node",
                         "Heptabase 未為此語法產生獨立 node(可能降級為純文字)")


# -- E02 -------------------------------------------------------------------
def e02(suite, pool, state):
    with suite.experiment(
            "E02", "Pull 保真度(進階 schema)",
            "驗證 pm2md 轉換器能否無損地把 E01 的進階 schema 轉回 markdown,"
            "並誠實回報任何無法處理的 node/mark。") as exp:
        doc = state.get("e01_doc")
        if doc is None:
            exp.warn("前置條件", "E01 未提供卡片,略過")
            return
        exp.step("取 E01 卡片的 ProseMirror JSON。")
        md_out, conv = pm2md.to_markdown(doc)
        exp.step("用 pm2md 轉成 markdown。")
        with open(os.path.join(FIXTURE_DIR, "roundtrip_extended.md"), "w") as f:
            f.write(md_out)
        exp.step("輸出存到 fixtures/roundtrip_extended.md。")
        if conv.unknown_nodes:
            exp.warn("有未處理的 node 類型", ", ".join(sorted(conv.unknown_nodes)))
        else:
            exp.check("所有 node 類型都能處理", True)
        if conv.unknown_marks:
            exp.warn("有未處理的 mark 類型", ", ".join(sorted(conv.unknown_marks)))
        else:
            exp.check("所有 mark 類型都能處理", True)
        if "UNCONVERTED" in md_out:
            exp.warn("輸出含 UNCONVERTED 標記", "部分內容無 markdown 對應")
        else:
            exp.check("輸出無資料遺失標記", True)


# -- E03 -------------------------------------------------------------------
def e03(suite, pool, state):
    with suite.experiment(
            "E03", "卡片引用能否由 markdown 建立",
            "Heptabase 的卡片對卡片引用是 inline `card` node。測試能否透過 "
            "`note create` 的 markdown 建立這種引用 —— 若不行,daemon 將無法從"
            "本地 markdown 同步引用關係。") as exp:
        target = pool.note("# E03 Target Card\n\nReferenced by E03.")
        exp.step("建立目標卡 A (E03 Target Card),id=%s。" % target)
        syntaxes = [
            ("wiki-link 標題", "[[E03 Target Card]]"),
            ("wiki-link cardId", "[[%s]]" % target),
            ("markdown link 指向 cardId", "[E03 Target Card](%s)" % target),
        ]
        any_ref = False
        for label, snippet in syntaxes:
            cid = pool.note("# E03 probe\n\nRef: " + snippet)
            doc, _ = read_doc(cid)
            # an inline card-to-card reference shows up as a node of type "card"
            is_ref = histogram(doc).get("card", 0) > 0
            exp.step("嘗試語法「%s」:`%s`。" % (label, snippet))
            if is_ref:
                any_ref = True
                exp.check(label + " 產生 card 引用 node", True)
            else:
                exp.warn(label + " 未產生引用",
                         "被當成純文字 / 一般連結")
        if not any_ref:
            exp.warn("結論:markdown 無法建立卡片引用",
                     "引用關係需在 app 內建立;daemon 對引用只能唯讀")


# -- E04 -------------------------------------------------------------------
def e04(suite, pool, state):
    with suite.experiment(
            "E04", "append 語意",
            "確認 `note append` 如何與既有內容互動:是否保留既有 block 的 ID、"
            "多次 append 是否都生效。") as exp:
        cid = pool.note("# E04 Append\n\nOriginal paragraph.")
        doc0, _ = read_doc(cid)
        ids0 = set(top_ids(doc0))
        exp.step("建卡,記錄既有 %d 個 block ID。" % len(ids0))
        htb.note_append(cid, "\n## Section Two\n\nFirst appended block.")
        exp.step("append 第一段 markdown。")
        htb.note_append(cid, "\n## Section Three\n\nSecond appended block.")
        exp.step("append 第二段 markdown。")
        doc1, _ = read_doc(cid)
        ids1 = set(top_ids(doc1))
        text = json.dumps(doc1, ensure_ascii=False)
        exp.check("既有 block ID 全數保留", ids0.issubset(ids1),
                  "%d/%d 保留" % (len(ids0 & ids1), len(ids0)))
        exp.check("第一次 append 內容存在", "First appended block." in text)
        exp.check("第二次 append 內容存在", "Second appended block." in text)
        exp.check("append 確實新增了 block", len(ids1) > len(ids0),
                  "%d -> %d 個 block" % (len(ids0), len(ids1)))


# -- E05 -------------------------------------------------------------------
def e05(suite, pool, state):
    with suite.experiment(
            "E05", "save:JSON 層級的 block 增 / 刪 / 重排",
            "確認 `note save` 能可靠處理 ProseMirror JSON 層級的 block 新增、"
            "刪除、重排,且未動到的 block 其 ID 維持不變。") as exp:
        cid = pool.note("# E05 Save\n\nAlpha.\n\nBeta.\n\nGamma.")
        # add ------------------------------------------------------------
        doc, md5 = read_doc(cid)
        before = top_ids(doc)
        doc["content"].append(new_paragraph("Delta (added via JSON)."))
        htb.note_save(cid, json.dumps(doc), md5)
        doc, md5 = read_doc(cid)
        exp.step("讀 JSON,在尾端插入一個自帶新 UUID 的 paragraph 後 save。")
        exp.check("新增的 block 出現", "Delta (added via JSON)." in json.dumps(doc))
        exp.check("新增後既有 ID 不變",
                  set(before).issubset(set(top_ids(doc))))
        # delete ---------------------------------------------------------
        doc["content"] = [n for n in doc["content"]
                          if transplant.block_text(n) != "Beta."]
        htb.note_save(cid, json.dumps(doc), md5)
        doc, md5 = read_doc(cid)
        exp.step("移除 'Beta.' 那個 block 後 save。")
        exp.check("刪除的 block 消失", "Beta." not in json.dumps(doc))
        # reorder --------------------------------------------------------
        content = doc["content"]
        if len(content) >= 3:
            content[1], content[2] = content[2], content[1]
        htb.note_save(cid, json.dumps(doc), md5)
        doc, _ = read_doc(cid)
        exp.step("交換第 2、3 個 block 的順序後 save。")
        texts = [transplant.block_text(n) for n in doc["content"]]
        exp.check("重排後順序生效", texts.index("Gamma.") < texts.index("Alpha."),
                  " / ".join(t for t in texts if t))


# -- E06 -------------------------------------------------------------------
E06_FIXTURE = """# E06 Push Transplant

Paragraph one is unchanged.

Paragraph two will be modified.

Paragraph three will be deleted.

Paragraph four is unchanged.
"""


def e06(suite, pool, state):
    with suite.experiment(
            "E06", "Push:編輯過的 markdown 經 transplant 推回",
            "核心實驗。一份被 agent 編輯過(改一段、刪一段、加一段)的 markdown,"
            "能否在保留未變更 block ID 的前提下推回 Heptabase。"
            "策略:讓 Heptabase 把編輯後 markdown 轉成 ProseMirror(scratch 卡),"
            "再把原卡的 block ID 移植到存活的 block 上。") as exp:
        cid = pool.note(E06_FIXTURE)
        old_doc, md5 = read_doc(cid)
        id_by_text = {transplant.block_text(n): n.get("attrs", {}).get("id")
                      for n in old_doc["content"]}
        exp.step("建立原始卡 C(標題 + 4 段),記錄每段的 block ID。")

        md_pulled, _ = pm2md.to_markdown(old_doc)
        edited = md_pulled.replace(
            "Paragraph two will be modified.",
            "Paragraph two has now been modified.")
        edited = edited.replace("\n\nParagraph three will be deleted.", "")
        edited = edited + "\n\nParagraph five is brand new."
        exp.step("用 pm2md 把 C 拉成 markdown,模擬 agent 編輯:"
                 "改第 2 段、刪第 3 段、文末新增第 5 段。")

        scratch = pool.note(edited)
        new_doc, _ = read_doc(scratch)
        exp.step("用編輯後 markdown 建 scratch 卡 S(由 Heptabase 做 MD→PM)。")

        report = transplant.transplant_ids(old_doc, new_doc)
        exp.step("transplant_ids() 把舊 ID 移植到存活的 block。")
        htb.note_save(cid, json.dumps(new_doc), md5)
        exp.step("`note save` 把移植後的 JSON 寫回 C。")

        final_doc, _ = read_doc(cid)
        final_ids = set(top_ids(final_doc))
        final_md, _ = pm2md.to_markdown(final_doc)

        def old_id(needle):
            return id_by_text[_match(id_by_text, needle)]

        kept = all(old_id(n) in final_ids
                   for n in ("E06 Push", "one is unchanged",
                             "four is unchanged"))
        exp.check("未變更的 3 個 block 保留原 ID", kept,
                  "preserved=%d" % len(report["preserved"]))
        p2_old = old_id("two will be modified")
        exp.check("被編輯的第 2 段保留原 ID(edited)",
                  p2_old in report["edited"] and p2_old in final_ids,
                  "edited=%s" % report["edited"])
        p3_old = old_id("three will be deleted")
        exp.check("被刪除的第 3 段舊 ID 已消失",
                  p3_old in report["deleted"] and p3_old not in final_ids)
        exp.check("新增的第 5 段為全新 ID",
                  len(report["inserted"]) == 1
                  and report["inserted"][0] not in id_by_text.values())
        exp.check("最終卡片內容等於編輯後 markdown",
                  norm(final_md) == norm(edited))


def _match(mapping, needle):
    for k in mapping:
        if needle in k:
            return k
    raise KeyError(needle)


# -- E07 -------------------------------------------------------------------
def e07(suite, pool, state):
    with suite.experiment(
            "E07", "Push:純重排 block 順序",
            "測試只是調換 block 順序(內容不變)時,transplant 能否讓 ID 跟著 "
            "block 走,而不是被當成刪除 + 新增。") as exp:
        cid = pool.note("# E07 Reorder\n\nBlock A.\n\nBlock B.\n\nBlock C.")
        old_doc, md5 = read_doc(cid)
        id_by_text = {transplant.block_text(n): n.get("attrs", {}).get("id")
                      for n in old_doc["content"]}
        exp.step("建卡(A / B / C 三段),記錄各段 ID。")

        edited = "# E07 Reorder\n\nBlock C.\n\nBlock A.\n\nBlock B."
        scratch = pool.note(edited)
        new_doc, _ = read_doc(scratch)
        exp.step("把順序改為 C / A / B,建 scratch 卡。")

        report = transplant.transplant_ids(old_doc, new_doc)
        htb.note_save(cid, json.dumps(new_doc), md5)
        exp.step("transplant + save。")

        final_doc, _ = read_doc(cid)
        final_ids = set(top_ids(final_doc))
        kept_ids = set(report["preserved"]) | set(report["reordered"])
        for letter in ("A", "B", "C"):
            bid = id_by_text["Block %s." % letter]
            exp.check("Block %s 保留原 ID" % letter,
                      bid in kept_ids and bid in final_ids)
        texts = [transplant.block_text(n) for n in final_doc["content"]]
        order = [t for t in texts if t.startswith("Block")]
        exp.check("最終順序為 C / A / B",
                  order == ["Block C.", "Block A.", "Block B."],
                  " ".join(order))


# -- E08 -------------------------------------------------------------------
def e08(suite, pool, state):
    with suite.experiment(
            "E08", "衝突偵測與樂觀鎖復原",
            "驗證 `--content-md5` 樂觀鎖:合法 save 成功、過期 md5 被拒、"
            "重新 read 後重試可成功復原 —— 這是 daemon 衝突處理的基礎。") as exp:
        cid = pool.note("# E08 Conflict\n\nFirst version.")
        _, md5_1 = read_doc(cid)
        exp.step("建卡,read 取得 md5_1。")

        doc, _ = read_doc(cid)
        doc["content"][1]["content"][0]["text"] = "Second version."
        htb.note_save(cid, json.dumps(doc), md5_1)
        exp.check("帶正確 md5 的 save 成功", True)
        exp.step("用 md5_1 做一次合法編輯 save(內容變更);md5_1 自此過期。")

        _, md5_2 = read_doc(cid)
        doc, _ = read_doc(cid)
        doc["content"][1]["content"][0]["text"] = "Stale write attempt."
        try:
            htb.note_save(cid, json.dumps(doc), md5_1)
            exp.warn("過期 md5 應被拒", "竟然成功 —— 樂觀鎖未生效")
        except htb.HtbError as e:
            exp.check("過期 md5 的 save 被拒", True, htb.error_detail(e))
        exp.step("再用已過期的 md5_1 嘗試 save → 預期被拒。")

        try:
            htb.note_save(cid, json.dumps(doc), md5_2)
            exp.check("重新 read 取得新 md5 後重試成功", True)
        except htb.HtbError:
            exp.check("重新 read 取得新 md5 後重試成功", False)
        exp.step("復原:重新 read 取得 md5_2,帶 md5_2 重試 → 預期成功。")


# -- E09 -------------------------------------------------------------------
def e09(suite, pool, state):
    with suite.experiment(
            "E09", "Tag 與 property 讀寫",
            "測試 tag 與結構化 property 能否經 CLI 讀寫 —— 對應把 tag / property "
            "放進本地 markdown frontmatter 並同步的構想。") as exp:
        tags = (htb.tag_list() or {}).get("tags", [])
        if tags:
            tag = tags[0]
            exp.step("沿用既有 tag「%s」(不新增,避免汙染)。" % tag["name"])
            exp.info("CLI 無 tag 刪除指令", "故 POC 不主動建立 tag")
        else:
            tag = htb.tag_create("HeptaSync-POC-Tag")
            exp.step("使用者沒有任何 tag,建立「HeptaSync-POC-Tag」。")
            exp.warn("建立了一個無法經 CLI 刪除的 tag", "請在 app 內手動刪除")

        cid = pool.note("# E09 Tag Test\n\nThrowaway card for tag test.")
        htb.tag_add(cid, tag["name"])
        exp.step("把該 tag 加到一張 throwaway 卡上。")
        props = htb.tag_properties(tag["id"]) or {}
        plist = props.get("properties", [])
        exp.check("可讀取 tag 的 property schema", True,
                  "%d 個欄位" % len(plist))
        cardprops = htb.card_properties(cid) or {}
        exp.check("可讀取卡片的結構化屬性", "tags" in cardprops,
                  "卡片掛了 %d 個 tag" % len(cardprops.get("tags", [])))

        text_prop = next((p for p in plist
                          if (p.get("type") or "").lower() in ("text", "string")),
                         None)
        if text_prop:
            htb.card_set_property(cid, text_prop["id"], value="set-by-poc")
            after = htb.card_properties(cid) or {}
            hit = "set-by-poc" in json.dumps(after, ensure_ascii=False)
            exp.check("set-property 寫入文字屬性並可讀回", hit)
            exp.step("對文字屬性「%s」set-property 後重讀驗證。"
                     % text_prop.get("name"))
        else:
            exp.info("略過 set-property", "此 tag 無文字型 property 可測")


# -- E10 -------------------------------------------------------------------
def e10(suite, pool, state):
    with suite.experiment(
            "E10", "遠端變更偵測(輪詢)",
            "CLI 沒有事件推送,daemon 只能輪詢。測試 `card list` 的 "
            "lastEditedTime 是否能用來偵測遠端變更。") as exp:
        cid = pool.note("# E10 Polling\n\nBefore edit.")
        listing = htb.card_list(sort="lastUpdatedTime", limit=50) or {}
        before = _find(listing, cid)
        exp.step("建卡,`card list` 取得其 lastEditedTime。")

        doc, md5 = read_doc(cid)
        doc["content"][1]["content"][0]["text"] = "After edit."
        htb.note_save(cid, json.dumps(doc), md5)
        exp.step("save 一次編輯。")

        listing2 = htb.card_list(sort="lastUpdatedTime", limit=50) or {}
        after = _find(listing2, cid)
        exp.step("再次 `card list`,比對 lastEditedTime。")
        exp.check("card list 查得到該卡", before is not None and after is not None)
        if before and after:
            exp.check("lastEditedTime 在編輯後前進",
                      after["lastEditedTime"] >= before["lastEditedTime"],
                      "%s -> %s" % (before["lastEditedTime"],
                                    after["lastEditedTime"]))
        ranked = [c["id"] for c in listing2.get("results", [])]
        exp.check("剛編輯的卡排在 lastUpdatedTime 前段",
                  cid in ranked[:5],
                  "排名第 %s" % (ranked.index(cid) + 1 if cid in ranked else "?"))


def _find(listing, cid):
    for c in (listing or {}).get("results", []):
        if c["id"] == cid:
            return c
    return None


# -- E11 -------------------------------------------------------------------
def e11(suite, pool, state):
    with suite.experiment(
            "E11", "Whiteboard 成員關係",
            "測試卡片加入 / 移出 whiteboard 是否可由 CLI 控制 —— 對應 frontmatter "
            "的 `whiteboard:` 欄位。") as exp:
        boards = (htb.whiteboard_list() or {}).get("whiteboards", [])
        if not boards:
            exp.warn("環境無 whiteboard", "略過此實驗")
            return
        board = boards[0]
        exp.step("沿用既有 whiteboard「%s」。" % board["name"])
        cid = pool.note("# E11 Whiteboard\n\nCard for whiteboard test.")

        htb.whiteboard_add_card(board["id"], cid)
        cards = (htb.whiteboard_cards(board["id"]) or {}).get("cards", [])
        on_board = any(c.get("cardId") == cid for c in cards)
        exp.check("add-card 後卡片出現在 whiteboard 上", on_board)
        exp.step("`whiteboard add-card` 後用 `whiteboard cards` 確認。")

        htb.whiteboard_remove_card(board["id"], cid)
        cards2 = (htb.whiteboard_cards(board["id"]) or {}).get("cards", [])
        still = any(c.get("cardId") == cid for c in cards2)
        exp.check("remove-card 後卡片已移除", not still)
        exp.step("`whiteboard remove-card` 後再確認。")
        exp.info("CLI 無法控制座標", "frontmatter 只能表達『屬於哪個白板』,不能定位")


# -- E12 -------------------------------------------------------------------
def e12(suite, pool, state):
    with suite.experiment(
            "E12", "邊界情況:CJK / emoji / 空內容 / 多 block",
            "測試非 ASCII 內容、空內容、以及較多 block 的卡片是否正常。") as exp:
        cjk = ("# E12 邊界測試 🚀\n\n繁體中文段落,含 emoji 😀 與特殊字元 "
               "`code` *斜體* **粗體**。\n\n第二段:符號 < > & \" ' 測試。")
        cid = pool.note(cjk)
        doc, _ = read_doc(cid)
        md_out, _ = pm2md.to_markdown(doc)
        exp.step("建立含繁中、emoji、markdown 特殊字元的卡並 round-trip。")
        exp.check("CJK 與 emoji 正確 round-trip",
                  "繁體中文段落" in md_out and "🚀" in md_out)

        try:
            empty = htb.note_create("")
            pool.track(empty["id"])
            exp.warn("空 markdown 也能建卡", "建出 id=%s" % empty["id"])
        except htb.HtbError as e:
            exp.check("空內容被拒(符合預期)", True, htb.error_detail(e))
        exp.step("嘗試用空 markdown 建卡,觀察行為。")

        big = "# E12 Many Blocks\n\n" + "\n\n".join(
            "Paragraph number %d with some filler text." % i
            for i in range(120))
        big_id = pool.note(big)
        bdoc, _ = read_doc(big_id)
        exp.step("建立一張 ~120 個 block 的卡,確認 create + read 正常。")
        exp.check("多 block 卡片正常建立並讀回",
                  len(bdoc.get("content", [])) >= 120,
                  "%d 個 block" % len(bdoc.get("content", [])))


# -- E13 -------------------------------------------------------------------
def e13(suite, pool, state):
    with suite.experiment(
            "E13", "Push:純標記變更(加粗體)",
            "若 agent 只是把某個字加粗(純文字不變),transplant 的 signature "
            "是 type + 純文字,該 block 會被判為 equal。驗證:即使判為 equal,"
            "save 寫入的仍是 scratch 卡內容(含粗體),所以標記變更不會遺失。") as exp:
        cid = pool.note("# E13 Marks\n\nMake the word important here.")
        old_doc, md5 = read_doc(cid)
        old_pid = old_doc["content"][1]["attrs"]["id"]
        exp.step("建卡,內容含一個普通段落。")
        scratch = pool.note("# E13 Marks\n\nMake the word **important** here.")
        new_doc, _ = read_doc(scratch)
        exp.step("把 'important' 加粗,建 scratch 卡。")
        report = transplant.transplant_ids(old_doc, new_doc)
        htb.note_save(cid, json.dumps(new_doc), md5)
        exp.step("transplant + save 回原卡。")
        final_doc, _ = read_doc(cid)
        txt = json.dumps(final_doc, ensure_ascii=False)
        exp.check("粗體標記確實寫入(變更未遺失)",
                  '"strong"' in txt or '"bold"' in txt)
        exp.check("段落 block 保留原 ID", old_pid in set(top_ids(final_doc)),
                  "transplant 分類:%s" %
                  ("preserved" if old_pid in report["preserved"] else "其他"))


# -- E14 -------------------------------------------------------------------
def e14(suite, pool, state):
    with suite.experiment(
            "E14", "Push:標題層級變更與巢狀清單編輯",
            "測試 transplant 對(a)標題層級改變(## → ###)與(b)巢狀清單"
            "子項目文字編輯的處理。") as exp:
        cid = pool.note("# E14\n\n## A heading\n\n- parent\n  - child item\n")
        old_doc, md5 = read_doc(cid)
        exp.step("建卡:含一個 H2 與一個帶子項目的清單。")
        scratch = pool.note(
            "# E14\n\n### A heading\n\n- parent\n  - child item edited\n")
        new_doc, _ = read_doc(scratch)
        transplant.transplant_ids(old_doc, new_doc)
        htb.note_save(cid, json.dumps(new_doc), md5)
        exp.step("把 H2 改成 H3、子項目文字加上 'edited',transplant + save。")
        final_md, _ = pm2md.to_markdown(read_doc(cid)[0])
        exp.check("標題層級變更生效(### 出現)", "### A heading" in final_md)
        exp.check("巢狀子項目文字變更生效", "child item edited" in final_md)
        exp.info("標題層級存在 attrs.level", "type 不變,transplant 視為 equal 並存回新 level")


# -- E15 -------------------------------------------------------------------
def e15(suite, pool, state):
    with suite.experiment(
            "E15", "Push:含表格 / 數學的卡片局部編輯",
            "在同時含表格與數學的卡片上只編輯其中一段文字。驗證 transplant "
            "後表格、數學等複雜 node 完整保留,且只有被編輯的段落改變。") as exp:
        src = ("# E15 Rich\n\nIntro paragraph.\n\n"
               "| K | V |\n| - | - |\n| a | 1 |\n\n"
               "Inline math $x^2$ stays.\n\n$$\na+b\n$$\n")
        cid = pool.note(src)
        old_doc, md5 = read_doc(cid)
        exp.step("建卡:段落 + 表格 + 行內數學段 + 區塊數學。")
        pulled, _ = pm2md.to_markdown(old_doc)
        scratch = pool.note(
            pulled.replace("Intro paragraph.", "Intro paragraph EDITED."))
        new_doc, _ = read_doc(scratch)
        transplant.transplant_ids(old_doc, new_doc)
        htb.note_save(cid, json.dumps(new_doc), md5)
        exp.step("只把第一段文字改掉,transplant + save。")
        final_doc, _ = read_doc(cid)
        h = histogram(final_doc)
        exp.check("表格 node 完整保留", h.get("table", 0) >= 1)
        exp.check("區塊數學 node 完整保留", h.get("math_display", 0) >= 1)
        exp.check("行內數學 node 完整保留", h.get("math_inline", 0) >= 1)
        final_md, _ = pm2md.to_markdown(final_doc)
        exp.check("被編輯的段落內容已更新", "Intro paragraph EDITED." in final_md)


# -- E16 -------------------------------------------------------------------
def e16(suite, pool, state):
    with suite.experiment(
            "E16", "Journal 讀取(date-keyed 卡片)",
            "Journal 用日期當 key 而非 UUID。讀取今天的 journal,確認其結構"
            "與 note 相同(ProseMirror JSON + contentMd5),可納入同步模型。"
            "為避免汙染使用者的真實 journal,本實驗只做唯讀。") as exp:
        today = datetime.date.today().isoformat()
        try:
            j = htb.journal_read(today)
            exp.step("`journal read %s`。" % today)
            doc = json.loads(j["content"])
            exp.check("journal 內容也是 ProseMirror JSON",
                      isinstance(doc, dict) and doc.get("type") == "doc")
            exp.check("journal 也回傳 contentMd5(可做樂觀鎖)", "contentMd5" in j)
            exp.info("journal 的 key 是日期", "date=%s,非 UUID" % j.get("date"))
        except htb.HtbError as e:
            exp.warn("今天尚無 journal 或讀取失敗", htb.error_detail(e))


# -- E17 -------------------------------------------------------------------
def e17(suite, pool, state):
    with suite.experiment(
            "E17", "Card trash / restore 往返",
            "確認 trash 是軟刪除、可被 restore。這讓 daemon 的刪除同步是安全"
            "的(本地刪檔導致的遠端 trash 可復原)。") as exp:
        cid = htb.note_create(
            "# E17 Trash\n\nWill be trashed then restored.")["id"]
        exp.step("建卡。")
        htb.card_trash(cid)
        exp.step("trash 該卡。")
        htb.card_restore(cid)
        exp.step("restore 該卡。")
        back = htb.note_read(cid)
        exp.check("trash 後可 restore 並重新讀取", back.get("id") == cid,
                  "標題:%s" % back.get("title"))
        pool.track(cid)


# -- E18 -------------------------------------------------------------------
def e18(suite, pool, state):
    with suite.experiment(
            "E18", "端到端同步循環(pull → 本地 .md → 編輯 → push)",
            "模擬 v1 daemon 完整一輪:把一張卡 pull 成帶 frontmatter 的本地 "
            ".md、編輯 body、再 push 回去。這是把所有零件串起來的總驗證。") as exp:
        cid = pool.note("# E18 Roundtrip\n\nThe quick brown fox.\n\n"
                        "Second paragraph here.")
        rec = htb.note_read(cid)
        old_doc = json.loads(rec["content"])
        exp.step("建立來源卡 C。")

        body, _ = pm2md.to_markdown(old_doc)
        meta = frontmatter.build_note_meta(rec, tags=["HeptaSync"],
                                           synced_at="2026-05-22T00:00:00Z")
        local_file = frontmatter.serialize(meta, body)
        exp.step("pull:pm2md 轉成 markdown body,加上 heptabase frontmatter,"
                 "組成本地 .md 檔內容。")
        exp.check("本地 .md 以 frontmatter 開頭且含 cardId",
                  local_file.startswith("---") and cid in local_file)

        m2, b2 = frontmatter.parse(local_file)
        edited_body = b2.replace("The quick brown fox.",
                                 "The quick RED fox jumps.")
        exp.step("agent 編輯:解析出 body,改第一段文字(frontmatter 不動)。")
        exp.check("解析回的 cardId 與原卡一致",
                  m2[frontmatter.MANAGED_KEY]["cardId"] == cid)

        scratch = pool.note(edited_body)
        new_doc, _ = read_doc(scratch)
        transplant.transplant_ids(old_doc, new_doc)
        htb.note_save(cid, json.dumps(new_doc), rec["contentMd5"])
        exp.step("push:用編輯後 body 建 scratch 卡、transplant block ID、"
                 "save 回 C。")

        final_doc, _ = read_doc(cid)
        final_body, _ = pm2md.to_markdown(final_doc)
        exp.check("編輯後內容成功 push 回原卡",
                  "The quick RED fox jumps." in final_body)
        exp.check("未編輯的第二段保留原 block ID",
                  old_doc["content"][2]["attrs"]["id"]
                  in set(top_ids(final_doc)))
        exp.check("完整循環不丟資料(第二段仍在)",
                  "Second paragraph here." in final_body)


# -- E19 -------------------------------------------------------------------
def e19(suite, pool, state):
    with suite.experiment(
            "E19", "Frontmatter schema 往返",
            "驗證 v1 的 frontmatter 模組:serialize → parse 能無損往返 schema "
            "中所有欄位類型(字串、清單、空清單、含特殊字元的標題)。") as exp:
        meta = {frontmatter.MANAGED_KEY: {
            "cardId": "7301c5b4-ee45-4b10-bb31-7cc50b92dc4f",
            "type": "note",
            "title": 'Tricky: title with "quotes" & colon',
            "tags": ["LeetCode", "Algorithms / DP"],
            "whiteboards": [],
            "contentMd5": "7d960abeac141347ff200a6f59991de9",
            "syncedAt": "2026-05-22T00:00:00Z",
        }}
        body = "# Heading\n\nBody text, and a line with --- dashes.\n"
        exp.step("構造一份含特殊字元標題、清單、空清單的 meta。")
        text = frontmatter.serialize(meta, body)
        m2, b2 = frontmatter.parse(text)
        exp.step("serialize 後再 parse。")
        exp.check("frontmatter 往返後 meta 完全一致", m2 == meta,
                  "" if m2 == meta else "got: %s" % m2)
        exp.check("body 往返後完全一致", b2 == body)
        plain = "# just markdown\n\nno frontmatter here"
        exp.check("無 frontmatter 的純 markdown 也能安全解析",
                  frontmatter.parse(plain) == ({}, plain))


# -- E20 -------------------------------------------------------------------
def e20(suite, pool, state):
    with suite.experiment(
            "E20", "寫入吞吐量(daemon 同步速率估算)",
            "寫操作是序列化的。量測連續 N 次 note 寫入的耗時,估算 daemon "
            "同步一個 vault 的速率上限。") as exp:
        n = 8
        t0 = time.time()
        for i in range(n):
            pool.track(htb.note_create(
                "# E20-%d\n\nThroughput probe %d." % (i, i))["id"])
        elapsed = time.time() - t0
        per = elapsed / n
        exp.step("連續建立 %d 張卡並計時。" % n)
        exp.info("總耗時 / 平均單次",
                 "%.2fs 共 %d 次,平均 %.0f ms/次" % (elapsed, n, per * 1000))
        exp.check("單次寫入在合理範圍(< 2s)", per < 2.0,
                  "%.0f ms/次" % (per * 1000))
        exp.info("vault 同步速率推估",
                 "約 %.0f 張卡/分鐘(僅寫入,序列化)"
                 % (60 / per if per else 0))


# -- E21 -------------------------------------------------------------------
def e21(suite, pool, state):
    with suite.experiment(
            "E21", "內容大小上限",
            "探測單張卡片 markdown 內容的大小上限。skill 文件記載 request "
            "body 上限為 1MB,但實測有更嚴格的字元數限制 —— 這對 daemon 處理"
            "超長卡片是關鍵約束。") as exp:
        def body_of(chars):
            unit = "Filler sentence for the size probe. "
            text = "# E21 Size\n\n" + unit * (chars // len(unit) + 1)
            return text[:chars]

        exp.step("建立一張約 95,000 字元的卡(預期低於上限)。")
        try:
            cid = pool.note(body_of(95000))
            doc, _ = read_doc(cid)
            exp.check("95K 字元的卡片可正常建立", True,
                      "%d 個 block" % len(doc.get("content", [])))
        except htb.HtbError as e:
            exp.check("95K 字元的卡片可正常建立", False, htb.error_detail(e))

        exp.step("建立一張約 120,000 字元的卡(預期被拒)。")
        try:
            pool.note(body_of(120000))
            exp.warn("120K 字元竟可建立", "未觸及預期上限")
        except htb.HtbError as e:
            exp.check("超過上限的 create 被拒", True, htb.error_detail(e))

        exp.step("建一張 900-block 的卡(markdown 僅約 12K,但其 ProseMirror "
                 "JSON 會超過 100K),讀回 JSON 後嘗試 save。")
        many = "# E21 Save Limit\n\n" + "\n\n".join(
            "Block number %d here." % i for i in range(900))
        mid = pool.note(many)
        rec = htb.note_read(mid)
        json_len = len(rec["content"])
        try:
            htb.note_save(mid, rec["content"], rec["contentMd5"])
            exp.info("該卡仍可被 save", "JSON 長 %d 字元" % json_len)
        except htb.HtbError as e:
            exp.check("save 的 100K 上限作用在 ProseMirror JSON payload 上",
                      "100000" in htb.error_detail(e),
                      "markdown 僅約 12K,但 JSON 長 %d 字元而被拒" % json_len)

        exp.info("實測上限與意涵",
                 "create 驗證 markdown、save 驗證 ProseMirror JSON,各有 "
                 "100,000 字元上限。JSON 約為 markdown 的數倍,故 push"
                 "(note save)能推送的卡片遠小於 100K markdown;daemon 需對"
                 "超長卡片分段或拒絕同步")


ALL = [e01, e02, e03, e04, e05, e06, e07, e08, e09, e10, e11, e12,
       e13, e14, e15, e16, e17, e18, e19, e20, e21]
