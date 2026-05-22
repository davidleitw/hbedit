---
heptabase:
  cardId: ef0ae6fe-f198-46c2-873f-83640a89198e
  type: note
  title: HeptaSync — 專案總覽
  tags:
    - HeptaSync
  whiteboards: []
  contentMd5: 6db607e7b50034f07da62f7ce756d2dd
  syncedAt: 2026-05-22T13:18:47Z
---
# HeptaSync — 專案總覽

> 非官方社群工具,不隸屬 Heptabase。完全建構在官方 `heptabase` CLI 之上,不直接碰 Heptabase 的資料庫或內部檔案。

本文件由 HeptaSync 自己同步上 Heptabase —— 這張卡片就是工具運作的活見證。

## 1. 這是什麼

讓 AI agent(或你自己)可以**像編輯純文字檔一樣**整理 Heptabase 筆記:改本地的 `.md` 檔,變更就同步回 Heptabase。

## 2. 解決的問題

官方 `heptabase` CLI 能**新建**卡片、能在卡片**尾端追加**,但**不能用純文字(markdown)修改既有卡片的中間**(`note save` 要的是 Heptabase 內部的 ProseMirror 格式)。結果:agent 只能幫你「加」,不能幫你「改寫 / 整理」。HeptaSync 補的就是這個洞。

## 3. 運作方式

**Pull(拉下來):** 卡片 → 讀出 ProseMirror JSON → 轉成 Markdown → 寫成本地 `.md`。

**Push(推上去):** 用「移植 (transplant)」這招繞過格式問題 ——

1. 把編輯後的 markdown 丟給 Heptabase,讓它自己建一張暫時卡(借它的手做格式轉換)。
2. 把原卡的 block 編號「移植」到沒被改動的 block 上 —— Heptabase 才知道「還是同一塊,只是內容改了」。
3. 存回原卡,刪掉暫時卡。

好處:**我們完全不用自己懂 Heptabase 的內部格式。**

每個本地 `.md` 檔最上面有一段隱藏的 `heptabase:` frontmatter,記住它對應哪張卡片。預覽 markdown 時看不見。

## 4. POC 驗證了什麼

對真實 Heptabase 跑了 21 個實驗(E01–E21,完整記錄在卡片「HeptaSync POC — 實驗記錄」)。結論:

- **Pull 無損** —— 標題、清單、表格、數學、巢狀清單都能正確還原。
- **Push 可行** —— 改一段、刪一段、加一段、調順序、加粗體、改標題層級、含表格/數學的局部編輯,推回去之後都正確,未變更的 block 保留原編號。
- **機制可靠** —— `contentMd5` 樂觀鎖可偵測衝突;trash 是軟刪除可復原;輪詢可偵測遠端變更。
- **端到端** —— pull → 本地編輯 → push 完整一圈不掉資料。

## 5. 三個已知限制

1. **卡片引用無法從 markdown 建立** —— 只能在 Heptabase app 內建,對引用只能唯讀。
2. **內容大小上限 100,000 字元** —— `create` 看 markdown、`save` 看 ProseMirror JSON(約 markdown 數倍大);換算約 700 行混合內容的卡片就可能 push 不回去。
3. **沒有事件推送** —— 只能輪詢偵測遠端變更。

## 6. 批判性檢視與建議路線

核心價值是對的:HeptaSync 讓 AI 終於能「改寫」既有筆記,而不只是「往後加」。但**不要一開始就做全自動背景 daemon** —— 引用與超大卡片同步不了,本地鏡像是個不完美副本,背景常駐久了兩邊會悄悄漂移,而「錯的同步比沒同步更糟」。

建議分三層,逐步推進:

| 層級 | 是什麼 | 評價 |
|---|---|---|
| ① 翻譯 + 移植兩個零件 | 讓 agent 能「改一張既有卡片」 | 真正的寶物,最小最安全 |
| ② 隨選 pull / push | 明確指令的本地工作區 | 合理的 v1 |
| ③ 全庫背景 daemon | 整個 vault 永遠自動同步 | 先別做,有漂移風險 |

## 7. v1 設計

**Vault 結構**

```
my-vault/
  .heptasync/sidecar/<cardId>.json   上次 pull 的 JSON(移植基準 / 衝突基準)
  notes/<slug>.md                    一張卡 = 一個檔
```

**Frontmatter schema**(隱藏標頭,記住身分)

```
---
heptabase:
  cardId: <uuid>
  type: note
  title: ...
  tags: [...]
  whiteboards: [...]
  contentMd5: <上次同步的 md5>
  syncedAt: <iso>
---
```

**同步模型** —— pull:讀卡 → 轉 markdown → 寫檔 + sidecar。push:解析 frontmatter → scratch 卡轉格式 → 移植 block ID → `save` 帶 contentMd5 → 更新 sidecar。衝突:偵測到 `Content conflict` 就備份本地、重新 pull、通知使用者。

## 8. 打包成 skill

做成 skill(隨選呼叫,對應「不做 daemon」)需要三塊:

- **已有**:`pm2md` / `transplant` / `htb` / `frontmatter`(POC 產出,已驗證)。
- **要補**:決策樹實作(超大卡拆檔、衝突)、防呆、production 品質。
- **外殼**:`SKILL.md`(模擬官方 `heptabase-cli` 寫法,但最上面標明非官方)、`scripts/`、`references/`、版本守門。

## 9. 現況與下一步

- POC:21 實驗完成,pull / push 兩個方向都驗證可行。
- v1:資料夾結構、frontmatter schema、`SKILL.md` 草稿、`hs push` / `hs pull` 最小實作 —— 完成。
- 下一步:把決策樹(超大卡拆檔、衝突)實作進 `hs`,補測試,收斂成 skill。

## 10. 專案檔案地圖

- `poc/` —— 21 個實驗 + 可重用零件(`pm2md` / `transplant` / `htb`)
- `poc/EXPERIMENTS.md` —— 完整實驗記錄
- `v1/DESIGN.md` —— 詳細設計文件
- `v1/frontmatter.py` —— frontmatter schema 實作
- `v1/hs.py` —— 最小 sync 進入點(`push` / `pull`)
- `v1/skill/SKILL.md` —— skill 草稿
- `vault/` —— 示範用 vault(這份文件就放在這裡)

---

*這張卡片由 `hs push` 從本地 `vault/notes/heptasync.md` 同步上來;本句經第二次 push 修改,用來示範 transplant 更新 —— 既有卡片改寫後,未變更的 block 編號全數保留。*
