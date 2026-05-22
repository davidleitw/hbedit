# HeptaSync v1 — 設計文件

> 本文是 v1 的資料夾結構與 frontmatter schema 設計。所有設計決策都由
> 21 項實驗(E01–E21)佐證(見 `v1/EXPERIMENTS.md` 或 Heptabase 上的
> 「HeptaSync POC — 實驗記錄」卡片)。

## 1. 目標與範圍

讓 agent(以及人)只要編輯**本地的純 markdown 檔案**,變更就會同步到
Heptabase;反之 Heptabase 上的變更也會拉回本地。本地檔案是一棵可以
`ripgrep`、可以 git 版控、可以離線編輯的 `.md` 樹。

**v1 範圍**:note 卡片的雙向同步(含 tag 同步)、frontmatter schema、明確指令式 `sync`。
**v1 之後**:背景 daemon、journal 同步、whiteboard 寫入、3-way prose merge。

唯一資料通道是官方 `heptabase` CLI(0.3.x)。絕不直接碰 app 的 DB / 快取。

## 2. Vault 資料夾結構

```
my-vault/
  .heptasync/
    state.json            # 每張卡的同步狀態(見 §4)
    sidecar/
      <cardId>.json       # 上次 pull 到的 ProseMirror JSON
  notes/
    <slug>.md             # 一張 note 卡 = 一個檔案
  journals/               # v1 之後
    2026-05-22.md
```

- **`notes/<slug>.md`** — 檔名是人類可讀的 slug(由標題產生),使用者可自由
  改名。卡片的真正身分是 frontmatter 裡的 `cardId`,不是檔名。沒有
  `cardId` 的新檔案 = 要在 Heptabase 新建的卡。
- **`.heptasync/sidecar/<cardId>.json`** — 上次 pull 的 ProseMirror JSON。
  它有兩個用途:(a) push 時作為 block-ID 移植的基準(見 §4 push);
  (b) 衝突時作為三方合併的 base。
- **`.heptasync/state.json`** — 每張卡的同步狀態。除了判斷哪邊變了,還存
  上次同步的 tag 集合(§8.5 的 3-way tag 合併基準)與 managed 欄位基準
  (§8.6 防呆)。vault root = 最近的含 `.heptasync/` 的祖先目錄(如同 git
  找 `.git/`,見 §8.2)。

## 3. Frontmatter schema

每個 `.md` 檔開頭是一段 YAML frontmatter,所有受管理的欄位都收在單一
`heptabase:` mapping 底下,所以這個區塊明確、好辨識、push 前好剝除。
標準 markdown previewer 會隱藏 `---` 區塊,所以閱讀時 metadata 不可見。

```yaml
---
heptabase:
  schemaVersion: 1
  cardId: 7301c5b4-ee45-4b10-bb31-7cc50b92dc4f
  type: note
  tags:
    - HeptaSync
  contentMd5: 7d960abeac141347ff200a6f59991de9
  syncedAt: 2026-05-22T00:00:00Z
---
# Example note

Body markdown...
```

| 欄位 | 意義 | 寫入方 |
|---|---|---|
| `schemaVersion` | frontmatter schema 版本(目前 `1`);供日後遷移 | HeptaSync |
| `cardId` | Heptabase 卡片 UUID;卡片的唯一身分 | HeptaSync |
| `type` | `note`(v1 之後:`journal`) | HeptaSync |
| `tags` | 卡片的 tag 名稱清單 | 雙向(3-way 合併,見 §8.5) |
| `contentMd5` | 上次 pull 時 Heptabase 回傳的 md5;樂觀鎖用 | HeptaSync |
| `syncedAt` | 上次成功同步的時間 | HeptaSync |

卡片標題不收進 frontmatter —— 標題的真相是 body 第一個 `# H1`(見 §8.3)。

具體實作見 `v1/skill/scripts/frontmatter.py`,其 serialize ⇄ parse 無損往返由實驗 E19
驗證。範例檔見 `v1/sample-note.md`。

> v1 的 daemon 正式版應改用 `pyyaml`;`frontmatter.py` 為了讓 POC 零相依,
> 自行實作了 schema 所需的 YAML 子集。

## 4. 同步模型

### Pull(Heptabase → 本地)

1. `card list --sort lastUpdatedTime` 找出 `lastEditedTime` 比 state 新的卡。
2. 對每張:`note read` → ProseMirror JSON。
3. JSON 存進 `sidecar/<cardId>.json`。
4. JSON 經 `pm2md` 轉成 markdown body(E02 證明對完整 node 詞彙無損)。
5. 套上 frontmatter,寫入 `notes/<slug>.md`。
6. 更新 `state.json`。

### Push(本地 → Heptabase)

關鍵問題:`note save` 只吃 ProseMirror JSON,但本地真相是被編輯過的
markdown。**不自己手寫 markdown→ProseMirror 轉換器**(對 Heptabase 自訂
schema 太脆弱),改用 **transplant 策略**:

1. 找出 body hash ≠ `state.localHash` 的本地檔(被編輯過)。
2. 解析 frontmatter 取得 `cardId`。
3. 用編輯後的 body 建一張 scratch 卡 → 讓 **Heptabase 自己**做
   markdown→ProseMirror(對所有 node 類型都正確)。
4. `transplant.transplant_ids(sidecar_json, scratch_json)` —— 把原卡的
   block ID 移植到存活的 block(未變更的保留、編輯的保留、刪除的丟棄、
   新增的給新 ID)。E06/E07 證明 modify / delete / insert / reorder 都成立。
5. `note save` 帶**上次 pull 的 `contentMd5`**(取自 frontmatter / state,
   **非**重新 `note read` 的當下值)作樂觀鎖寫回原卡;trash scratch 卡。
6. 更新 sidecar、state。

完整一輪 pull→編輯→push 由 E18 端到端驗證。

### Daemon 迴圈(v1 之後)

每 N 秒輪詢:先 pull、後 push。寫操作序列化,實測 ~600 張卡/分鐘
(E20),對一般 vault 綽綽有餘。CLI 無事件推送,只能輪詢(E10)。

## 5. 衝突處理

`contentMd5` 是樂觀鎖:push 時若 `note save` 回 `Content conflict`,代表
遠端在我們上次 pull 之後也改過(E08 驗證)。v1 策略:

- 偵測到衝突 → **不自動合併 prose**。
- 把本地版本另存為 `<slug>.conflict.md`,然後 pull 遠端最新版覆蓋。
- 在 `sync` 報告中明確列出衝突檔,交由使用者手動處理。
- sidecar JSON 是未來要做 3-way merge 的 base(v1 之後)。

## 6. 已知約束(實驗佐證)

| 約束 | 影響 | 來源 |
|---|---|---|
| 卡片引用無法從 markdown 建立 | frontmatter 可列出引用供唯讀;不可從本地新建引用 | E03 |
| 100,000 字元上限:create 驗證 markdown、save 驗證 ProseMirror JSON | JSON 約為 markdown 數倍,故 `note save`(push)可推送的卡片遠小於 100K markdown;daemon 需對超長卡片分段或拒絕同步 | E21 |
| CLI 無刪除 tag 的指令 | 從 frontmatter 移除 tag 不會刪掉 tag 資料庫 | E09 |
| whiteboard 只能管成員、不能定位 | v1.1 做 whiteboard 時只能表達歸屬,不存座標 | E11 |
| journal 用日期當 key | 與 note(UUID)分開建模 | E16 |
| 需 desktop app 開著 | app 關閉時所有 `hs` 指令失敗;`hs doctor` 會先回 `app-not-running` 擋下 | §9.4 |

## 7. v1 實作計畫

1. **`vault.py`** — 掃描 vault、讀寫 `state.json` 與 sidecar。
2. **`sync.py`** — `pull()` / `push()`,組合既有的 `pm2md` + `transplant`
   + `frontmatter`。
3. **`hs` CLI** — `hs init` / `hs pull` / `hs push` / `hs sync` / `hs status`
   / `hs trash` / `hs tags`。
4. 先只支援 note;journal、whiteboard 寫入、背景 daemon 留待 v1 之後。
5. 詳細的逐步實作計畫見 `v1/PLAN.md`(Phase 1 引擎修正 + Phase 2 封裝)。

POC 已驗證的可重用零件 `pm2md`(pull)、`transplant`(push)、`frontmatter`
(schema)、`htb`(CLI 封裝)於 v1 落地時收編進 `v1/skill/scripts/`;`poc/`
實驗目錄隨之解散(見 §9.3)。

## 8. 語意與互動設計

> 本章是 v1 的語意與互動設計,由一場互動式 design 討論(2026-05-22)收斂
> 而成。§8.1–8.2 講定位與冷啟動,§8.3–8.6 是同步語意 / 互動 / tag /
> frontmatter 四塊決策,§8.7 列出對既有章節與程式的修正事項。

### 8.1 定位與使用情境

HeptaSync 的定位一句話講清楚:**它是官方 `heptabase` CLI 缺的那個「編輯
既有卡」動詞。**

官方 CLI 對既有卡片是 append-only —— 能 `note create`、`note append`,但
`note save` 要的是內部 ProseMirror JSON,無法從純文字改卡片中段。HeptaSync
補的就是這個洞,其餘動作仍走官方 CLI。

| 任務 | 用什麼 |
|---|---|
| 找 / 瀏覽 / 搜尋卡片 | 官方 `heptabase` CLI(`card list`、`tag cards`) |
| 建新卡 / 純尾端追加 | 官方 CLI(`note create` / `note append`) |
| **改寫 / 重構 / 批次編輯既有卡** | **HeptaSync** |

三種典型情境:

1. **單卡整理** —— 「把這張卡的標題層級與段落順序重排」。`hs pull` → 用一般
   檔案工具改 `.md` → `hs push`。
2. **跨卡批次** —— 「統一所有 LeetCode 卡的免責聲明格式」。批次 `hs pull` →
   `rg` + 編輯 → `hs sync` 整批推回。
3. **本地長期工作** —— pull 一批卡進 vault,數天內用 agent / 編輯器 / 手改,
   `hs sync` 對帳。vault 是 git repo,筆記從此有 diff 歷史。

對比直接用官方 CLI,優勢五點:

1. **能力缺口** —— 官方 CLI 改不了既有卡中段;這是 HeptaSync 存在的唯一理由。
2. **agent 在 markdown 檔裡最強** —— pull 成 `.md` 後用一般檔案工具編輯;
   手刻 ProseMirror JSON 易錯,串 `note append` 無法重構。
3. **vault 是工作區** —— 可 grep、跨卡、可 diff、可 git 版控、可離線編輯。
4. **block ID 保存(正確性)** —— transplant 保住未變更 block 的原 ID;若
   直接 read→改 JSON→save,所有 ID 重生,指進這些 block 的引用 / backlink
   全斷。
5. **身分追蹤** —— frontmatter 記住「哪個檔 = 哪張卡」,日後再改是一道指令。

**呼叫模型** —— HeptaSync 打包成 skill(`v1/skill/SKILL.md`)。使用者用自然
語言描述需求,Claude 比對 skill description 自動啟動。冷啟動的真實流程是
官方 CLI 與 HeptaSync 合作:先用官方 `card list -q` 把卡片名稱解析成
cardId,再 `hs pull` 進 vault 編輯。

### 8.2 vault 模型與冷啟動

- **每專案一個 vault** —— vault 不是全域單一,而是綁在專案 / 工作目錄。
- **vault 探測** —— skill 啟動時從 cwd 向上尋找含 `.heptasync/` 的目錄
  (如同 git 找 `.git/`),最近的那個即 vault root。找不到 → 提議在 cwd
  `hs init`。
- **同卡多 vault 的風險** —— 同一張卡可被 pull 進多個 vault 各自編輯。這
  不會靜默掉資料:第二次 push 會撞上 `contentMd5` 樂觀鎖,觸發 §8.4 的
  衝突處理(備份 + 重新 pull + 回報)。屬優雅降級,可接受。

### 8.3 同步語意

1. **工作單位** —— vault 工作區為主(`.heptasync/state.json` + sidecar),
   同時支援單卡快速操作。`hs pull <cardId>` / `hs push <file>` 為單卡;
   `hs sync` 對整個 vault 批次對帳。
2. **檔案生命週期** —— 無 `cardId` 的檔 = push 時 `note create` 新卡;有
   `cardId` = transplant 更新。**刪檔 = 只取消追蹤**:`hs sync` 偵測
   「state 中曾追蹤、本地檔案已消失」的卡 → 移除 state 條目 + 清 sidecar,
   **Heptabase 卡片不動**。要真正 trash 卡片得用明確指令
   `hs trash <cardId>`(軟刪除,可復原)。
3. **改名** —— 卡片標題的真相是 **body 第一個 `# H1`**。實測 Heptabase 的
   title 是從內文首個 heading 即時推導(DERIVED),所以改 H1 後 push 會
   連帶改卡片標題,天生雙向、不需特別處理。**檔名 `<slug>.md` 純裝飾** ——
   只在首次 pull / create 時由標題產 slug,之後永不自動改名(自動改名會
   打斷 agent 持有的路徑、編輯器 buffer、git 狀態)。slug 撞名時加 cardId
   短前綴(`foo.md` → `foo-7301c5b4.md`)。
4. **子資料夾** —— `notes/` 底下可自由開子資料夾整理,**純本地裝飾**;
   Heptabase 沒有資料夾概念(組織只有 Card Library / tag / whiteboard),
   子資料夾在 Heptabase 端無對應、也不影響同步,sync 只認 cardId。
5. **v1 範圍** —— 只做 note 卡片的內容同步。journal(日期 key,可重用
   同套 transplant)與 whiteboard 成員寫入都留 v1.1。

### 8.4 使用者互動

1. **push 確認分層** —— transplant 流程中只有最後 `note save` 不可逆,
   在那之前已能取得 transplant 報告與 diff。據此:
   - 明確的 `hs push <file>`(使用者剛指名此檔)→ 直接執行,事後回報
     transplant 摘要。
   - `hs sync` 批次 → 先列出每個 dirty 檔 + 變更摘要,**整批確認一次**
     再寫入。
2. **回報基調:安靜、結果導向** —— 不旁白內部步驟(建 scratch、移植…)。
   pull 成功一行帶過或靜默;push 成功**一定**回報 transplant 摘要
   (動到真實資料);任何 skip / 衝突 / 超大 / 需決策 → 一定明顯講出。
3. **超大卡片** —— push 前估算結果 ProseMirror JSON 大小。純尾端追加且
   超標 → 改用 `note append`。中段編輯導致超過 100K → **停下來**說明
   具體原因 + 建議在某標題邊界切卡,使用者同意才切(前半保留 cardId、
   後半成新卡、複製 tag);否則該檔留 dirty 不 push。**絕不靜默切卡。**
4. **衝突** —— `note save` 回 `Content conflict`(遠端在上次 pull 後也
   改過)→ **自動處理 + 大聲回報**:本地版本另存 `<slug>.conflict.md`、
   重新 pull 遠端最新版覆蓋工作檔、明確告知使用者本地編輯與遠端最新
   各在何處、如何接手。不打斷批次(安全預設不丟資料)。3-way prose
   merge 留 v1 之後。

### 8.5 Tag

CLI 事實:`tag add --card-id --tag-name` 用名稱掛 tag(**名稱不存在會自動
建新 tag**);`tag remove --card-id --tag-id` 用 tag UUID 移除,**只拔卡片
成員、不刪 tag 資料庫**(無 `tag delete` 指令);卡片現有 tag 由
`card properties <cardId>` 取得。

1. **新卡 tag** —— 單卡 `hs push` 不主動問,完全照 frontmatter `tags:`
   (空白就建無 tag 卡)。`hs sync` 批次:摘要列出無 tag 的新卡清單;
   sync 跑完後給**一次性 opt-in 提示**「N 張新卡無 tag,現在掛嗎?」,
   同意才逐卡簡短詢問,永不擋 sync。
2. **建新 tag 的防呆** —— push 要建一個現有 tag 清單裡沒有的 tag 時,先
   與現有 tag 做模糊比對:有相近者(疑似 typo,如 `Heptasync` vs
   `HeptaSync`)→ 停下來問,讓使用者選用既有或確認建新;完全無相近者
   (真新 tag)→ 直接建並回報。
3. **tag 同步:3-way 合併** —— `contentMd5` 樂觀鎖只管內文、不管 tag,
   故 tag 遠端變動不會觸發衝突。push 時以三方比對避免清掉遠端新增:
   base = `state.json` 存的「上次同步 tag 集合」、local = frontmatter
   `tags:`、remote = `card properties` 現有 tag。本地新增的 → `tag add`、
   本地移除的 → `tag remove`、遠端自行新增且本地未碰的 → 保留。tag 是
   集合可無衝突合併,故安全自動執行。
4. **`hs tags`** —— 提供列出現有 tag 的指令,方便撰寫 frontmatter 前
   對照、降低 typo 生垃圾 tag。

### 8.6 Frontmatter schema

新 schema(移除 `title`、新增 `schemaVersion`):

```yaml
---
heptabase:
  schemaVersion: 1
  cardId: <uuid>
  type: note
  tags: [...]
  contentMd5: <上次 pull 的 md5>
  syncedAt: <iso>
---
```

1. **純 .md 無 frontmatter** —— push 一個完全沒有 frontmatter 的 `.md` →
   `note create` 建卡 → **自動**在檔案開頭插入 `heptabase:` block(含新
   cardId)→ 事後回報。補 frontmatter 是工具能追蹤的必要動作,非選配。
2. **managed / 可編** —— `cardId`、`type`、`contentMd5`、`syncedAt`、
   `schemaVersion` 由 HeptaSync 管理,使用者不應手改;`tags` 可編、雙向
   (3-way)。whiteboard 成員關係**不納入 v1 schema** —— Heptabase 沒有
   便宜的「卡片→所屬白板」查詢,且 v1 不寫白板;整個 whiteboard 支援
   (讀與寫)留待 v1.1,屆時再加回對應欄位(`schemaVersion` 即為此而設)。
3. **managed 欄位防呆** —— push 前以輕量驗證比對 frontmatter 的 managed
   欄位 vs `state.json`:`cardId` 與 state 不符 → **中止並警告**(幾乎
   必為誤改);`contentMd5` / `type` / `syncedAt` / `schemaVersion` 被改
   → 以 state 為準靜默覆寫(本就由工具重寫)。
4. **schemaVersion** —— 目前為 `1`。schema 一旦變更即遞增,供日後版本
   遷移判斷。

### 8.7 對既有章節 / 程式的修正事項

- **§2 / `v1/skill/scripts/hs.py`** —— `_vault_root` 從「往上找 `notes/` 父層」改為
  「往上找含 `.heptasync/` 的目錄」(§8.2)。
- **§3** —— frontmatter schema 表移除 `title`、新增 `schemaVersion`;
  `whiteboards` 不納入 v1 schema(整個 whiteboard 支援留 v1.1);卡片
  標題不再進 frontmatter,真相為 body H1(§8.3)。
- **§4 / `v1/skill/scripts/hs.py`** —— 現行 push 以重新 `note read` 的當下 md5 當
  樂觀鎖,等於鎖失效、永不偵測衝突。2026-05-22 dogfood 撞車實測證實:
  本地與遠端在同一同步點後各改一行,`hs push` 回報 `updated` 成功、
  **遠端那行被靜默覆寫消失**,完全未偵測衝突。修法:改用 frontmatter /
  state 中「上次 pull 的 `contentMd5`」當鎖 —— 底層 `note_save` 對 stale
  md5 會回 `Content conflict` 已實測確認,故修法可行。另:即使鎖修好,
  push 目前仍**無衝突發生後的處理碼**(§8.4 的備份 `.conflict.md` + 重新
  pull + 回報),該處理流程須一併實作。
- **`v1/skill/scripts/frontmatter.py`** —— `SCHEMA_FIELDS` 與 `build_note_meta` 須配合
  新 schema(去 `title`、加 `schemaVersion`);`build_note_meta` 目前由
  `card_record` 帶 `title`,改名語意改後應移除。
- **`v1/skill/scripts/pm2md.py`** —— 連續的 `numbered_list_item` 轉回 markdown 時每項
  都印 `1.` 而非遞增(2026-05-22 dogfood `hs push` 一張白話設計卡時發現)。
  卡片在 Heptabase 上顯示正常(Heptabase 數連續兄弟節點自動編號),但
  `hs pull` 下來的 `.md` 會是 `1. 1. 1.`,在 round-trip 製造假 diff、
  使 `hs sync` 的 hash-based dirty 判斷誤判。修法:轉換時對連續
  `numbered_list_item` 維護遞增計數器。連帶 §4 的「E02 無損」應釐清為
  「結構無損,但非 byte 無損」—— 而 `hs sync` 的 dirty 判斷正是靠 hash,
  故此類非 byte 無損的轉換差異都須在 pull 端消除。
- **`v1/skill/scripts/hs.py` `pull`(檔案身分)** —— `pull` 一律以 `_slug(title)` 推導
  目標路徑,不查該 cardId 是否已有對應檔(2026-05-22 dogfood re-pull 時
  發現)。對一張本地名為 `semantics-design.md` 的卡 re-pull,結果新建了
  `heptasync-v1-…白話版.md`,同一 cardId 出現兩個本地檔。`pull` 須先以
  cardId 查 `state.json` / 既有檔並**就地更新既有檔**,只有首次 pull 才
  產 slug 檔名(呼應 §8.3「檔名首次產生後永不自動改」)。
- **`v1/skill/scripts/hs.py` tag 同步(雙向皆未實作)** —— `pull` 呼叫 `build_note_meta`
  時未帶 tags,frontmatter 一律寫成 `tags: []`,把卡片真實的 tag 清空;
  `push` 也完全不呼叫 `tag add` / `tag remove`,frontmatter 的 `tags:`
  推上去毫無作用(2026-05-22 dogfood 時須另外手動 `heptabase tag add`
  補掛)。兩方向都須照 §8.5 實作:`pull` 以 `card properties` 讀回現有
  tag 填入;`push` 以 3-way 合併算出差異後 `tag add` / `tag remove`。
- **`v1/skill/scripts/htb.py` `tag_remove`** —— 函式簽名為 `tag_remove(card_id, tag_name)`、
  傳 `--tag-name`,但 CLI 的 `tag remove` 只吃 `--tag-id`(UUID),此函式
  一呼叫即失敗(2026-05-22 撰寫實作計畫時發現)。修法:改成
  `tag_remove(card_id, tag_id)` 傳 `--tag-id`,呼叫端先用 `tag list` 把
  名稱解析成 id。

## 9. 工具架構與多平台

> 本章定義 `hs` / 決策合約 / agent 的三層分工,以及如何同時支援
> Claude Code、Codex、opencode 等多套 agent 工具。它回答的是「§8 的
> 行為由誰執行」,不改變 §8 的行為本身。

### 9.1 三層分工

- **`hs`(程式)= 偵測 + 回報。** 只做機械性操作;遇到任何需要判斷的
  情況(衝突、超大、tag 疑似 typo),**不自行決策**,而是以結構化方式
  回報。
- **決策合約 = 決策層。** 窮舉規範「`hs` 回報 X → agent 做 Y」。
  tool-agnostic、單一來源(見 §9.3)。
- **agent(Claude Code / Codex / opencode)= 執行者。** 讀 `hs` 回報,
  依合約執行,包括把使用者選定的 resolution 再交回 `hs`。

§8 的行為(衝突→備份+重 pull、超大→建議切卡、批次→先確認)在此架構
下不變,只是明確:`hs` 偵測並回報、agent 依合約執行。「自動」對使用者
而言不變,差別在動作由 agent 跑、而非 `hs` 內部跑。

### 9.2 `hs` 輸出作為 contract

agent 既然依 `hs` 輸出做決策,該輸出即 API contract,要求:

- **JSON 輸出**,非散文。
- **列舉式 `status`** —— 每種情況一個明確代號。v1 至少涵蓋:`ok`、
  `conflict`(遠端在上次 pull 後也改過)、`oversized`(超過 100K,附
  建議切點)、`tag-ambiguous`(欲建之 tag 與既有 tag 模糊相近)、
  `no-frontmatter`(純 .md,已自動補)、`cardid-mismatch`(managed 欄位
  防呆觸發)。完整列舉於實作時定案。
- **一致的 exit code** —— 0 = ok,非 0 = 需 agent 介入。
- 偵測在 `hs`、決策在合約、**執行再回到 `hs`**:每條 resolution 都要有
  對應指令(例如 `oversized` 的切卡 → `hs split`)。

### 9.3 多平台:單一 Agent Skill 目錄

Claude Code、Codex CLI、opencode 三者的指令載入機制不同,但**都原生支援
Anthropic 的 Agent Skill 格式**(`SKILL.md` + `name` / `description`
frontmatter)。因此跨平台的通用產物**不是**「一份 contract 檔 + 三個
adapter」,而是**單一個 Agent Skill 目錄** —— 它直接以「可出貨形狀」存在
於 repo,**沒有 build 步驟**(全是靜態 `.py` 與 `.md`,無可編譯之物):

```
v1/skill/                 ← 這個目錄就是產品:直接 commit、直接開發、直接安裝
  SKILL.md                ← name/description frontmatter + 決策合約本體(§9.1/§9.2)
  scripts/                ← Anthropic skill 慣例的程式目錄(非 lib/)
    hs                    ← 可執行 shim(chmod +x):realpath 自我定位後 import hs
    hs.py  frontmatter.py  vault.py  tagsync.py  pm2md.py  transplant.py  htb.py
```

決策合約(§9.1/§9.2 的 status→action 規範)**直接寫在 `SKILL.md` 內文**;
三個工具都原生讀它,不需要中介 adapter。

**安裝 = 把 `v1/skill/` 整個複製(或 symlink)進各工具的 skill 路徑,並讓
`hs` 上 PATH:**

| 工具 | skill 安裝路徑 | 一鍵安裝 |
|---|---|---|
| Claude Code | `~/.claude/skills/`,或包成 plugin | plugin marketplace(`/plugin install`) |
| Codex CLI | `~/.agents/skills/` 或專案 `.agents/skills/` | 放檔即生效 |
| opencode | `~/.claude/skills/`、`~/.config/opencode/skills/`、`~/.agents/skills/` 皆讀 | 放檔即生效 |

`.agents/skills/` 同時被 Codex 與 opencode 讀,`.claude/skills/` 同時被
Claude Code 與 opencode 讀 —— 兩個位置即覆蓋三者。

**結構與封裝要求:**

- **無 build、無重複檔** —— `v1/skill/` 在 repo 裡就是出貨形狀,開發直接
  改 `scripts/` 裡的檔。`hs.py` 的 import 只需 `sys.path.insert(0, _HERE)`
  (所有模組同目錄,符合 Anthropic skill 慣例)。沒有 `dist/`、沒有組裝腳本。
- **POC 目錄解散** —— `poc/` 的任務是驗證,v1 落地即解散。converters
  (`pm2md` / `transplant` / `htb`)收編為 `scripts/` 的產品程式(唯一一份,
  非「凍結副本」);實驗腳本由 git 歷史封存;`EXPERIMENTS.md` 移為
  `v1/EXPERIMENTS.md`(設計主張的佐證軌跡)。
- **`hs` 上 PATH** —— `SKILL.md` 全程只寫 `hs ...`,不用工具特定路徑變數
  (`${CLAUDE_SKILL_DIR}` 僅 Claude Code 有)。安裝步驟把 `scripts/hs`
  symlink 到 PATH;`scripts/hs` 以 `os.path.realpath(__file__)` 自我定位,
  被 symlink 也找得到同目錄的模組。
- **零依賴即免安裝** —— stdlib-only 表示沒有 pip 步驟,`.py` 檔本身就是
  成品。**不發佈 PyPI、不 `pip install`**,直接隨 skill 目錄出貨。

**plugin / marketplace 不可跨工具。** 三者的 plugin 系統互不相容
(Claude Code 一種、Codex `.codex-plugin/`、opencode 是 JS npm)。故
native plugin 只作為**單一平台的一鍵安裝糖衣**(Claude Code 上架
marketplace),不作為跨平台手段;跨平台真正的產物永遠是 `v1/skill/` 目錄。

### 9.4 環境 preflight

同步前必須確認 Heptabase CLI 可用。此檢查**做進 `hs` 自己**(指令
`hs doctor`),不靠 `SKILL.md` 散文自覺、也不靠 Claude Code 專屬的 `!`
注入 —— 才能三平台一致可攜,並貼合 §9.1「`hs` 偵測、agent 依合約決策」。

`hs doctor` 三項檢查,輸出 §9.2 的結構化 status:

| 檢查 | 方法 | 失敗 status |
|---|---|---|
| CLI 是否安裝 | `shutil.which("heptabase")` | `cli-missing` |
| CLI 版本相容 | 解析 `heptabase --version`,須落在 `0.3.x` | `cli-version-unsupported` |
| 桌面 app 是否運行 | 探測性讀取(`card list --limit 1`),連線失敗即 app 未開 | `app-not-running` |

全部通過 → `ok`。

`SKILL.md`(三平台共用)規範一句:**動任何同步前先跑 `hs doctor`;非
`ok` 就停下、照其 `detail` 訊息告知使用者**。`hs pull` / `hs push`
內部亦先跑同一檢查,環境不良即吐結構化錯誤、不嘗試同步。
