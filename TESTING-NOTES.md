# hbedit skill — 本地測試筆記

> 這份文件記錄 2026-05-23 那次本地測 hbedit skill 的全部過程:做了什麼、為什麼這樣做、看到了什麼、下一步要怎麼改。
>
> 寫給未來的自己。等下次想動 SKILL.md 時,先看這份再動手。

## 我們在幹嘛?(背景)

hbedit 是這個專案做的 skill,作用是讓 AI agent 能編輯 Heptabase 卡片的中間段(官方 `heptabase` CLI 只能新建卡 / 在卡尾巴 append,動不了中間)。

skill 的「使用說明」放在 `skills/hbedit/SKILL.md` 的 frontmatter `description:` 欄位。當使用者跟 Claude Code 講話時,Claude Code 會掃所有 skill 的 description,判斷該不該觸發 hbedit。所以 description 寫得準不準,直接決定 agent 在「使用者描述模糊」的情境下會不會正確接手。

這次測試的目的:**驗證新版 description 能正確觸發 hbedit、agent 接手後的 workflow 行為合不合理。** 如果不合理,代表 SKILL.md 的 body(workflow 那段)該補東西。

## description 改了什麼

### 舊版

```
Edit and reorganize existing Heptabase note cards via a local-markdown
workflow — pull a card to a .md file, edit it as plain text, push it back.
Handles edits to the middle of a card, which the raw heptabase CLI cannot
do. Use when rewriting, restructuring, or cleaning up existing Heptabase
notes. UNOFFICIAL — not affiliated with Heptabase.
```

**問題:**

1. 觸發語料太窄 ── 只寫「rewriting / restructuring / cleaning up」,沒 cover「插段到中間」「拆卡」「跨卡批次」這些情境。
2. 沒講清楚跟官方 `heptabase` CLI 的分工(「Handles edits to the middle...」太隱晦)。
3. UNOFFICIAL 標記放在 description 末尾 ── 對 LLM 觸發判斷沒幫助、卻占字數。免責聲明該放 SKILL.md body。

### 新版(這次測試的版本)

```
Extends the `heptabase:heptabase-cli` skill with the ability to edit
existing card content — load `heptabase:heptabase-cli` first for the base
CLI, then use hbedit whenever a change touches what's already inside a
card: rewriting a section, inserting a paragraph mid-card, splitting one
long card into several, merging cards, cleaning up formatting, or making
the same edit across many cards. The base `heptabase` CLI only creates new
cards or appends to the end; reach for hbedit the moment you need to
mutate existing content.
```

改了三件事:

1. **開頭明寫「Extends heptabase:heptabase-cli skill」**── 讓 agent 知道這是建構在 base CLI skill 之上的。
2. **觸發語料展開成 6 個明確情境**── rewrite section / insert mid-card / split / merge / format cleanup / cross-card batch。
3. **跟官方 CLI 的分工寫死**── 「official CLI = create / append; hbedit = mutate existing」。

### 怎麼測新版

開新 Claude Code session 把這個 plugin load 進去:

```bash
cd /Users/leiweicheng/Desktop/HeptaSync
claude --plugin-dir .
```

`--plugin-dir .` 只對該 session 生效、不污染全域、退出即清。每次改完 SKILL.md 退掉 session 再開就是測新版,開發迴圈乾淨。

驗證 plugin 有 load 成功:看 session 開起來的 system reminder skill 列表,應該有 `hbedit:hbedit`。

---

## Prompt 1 ── 找錯字小修(故意設計成卡片不存在)

### Prompt

```
我那張 React Hooks 的卡片,第三段有個錯字 useEffec 應該是 useEffect,幫我改掉
```

### 為什麼這樣設計

P1 是故意拿**不存在的卡**去測:想看 agent 在「使用者口頭描述、不給 cardId」的情境下會不會亂猜、會不會搜、搜不到怎麼處理。

### 實際 trace 摘要

1. ✓ Load `hbedit:hbedit` skill
2. ✓ 跑 `hb doctor`(SKILL.md Step 0 mandatory)
3. ✓ 用 `heptabase card list -q` 搜了 4 次:`React Hooks` → `Hooks` → `useEffect` → `React`
4. ✓ 都沒命中 → 主動告訴使用者已搜過哪些關鍵字、請使用者提供 cardId 或更精確的標題

### 觀察

**整體非常好。** 沒亂猜 cardId、沒幻覺出一張卡。搜尋時自發 fallback 到多個關鍵字組合 ── 這沒寫在 SKILL.md 裡,是 LLM 自己的好行為。

### 唯一一個觀察點:description 的「load heptabase:heptabase-cli first」沒被執行

trace 裡 agent 沒去 load `heptabase:heptabase-cli`,直接就跑 `heptabase card list -q ...`。

兩種解讀:

- **(A) agent 偷懶沒照 description 做** → description 那句話要寫得更強硬。
- **(B) agent 判斷「我已經知道 base CLI 怎麼用,不需要 load base skill」** → 這其實是合理的、節省 context 的判斷。

**傾向 (B)。** description 那句「load first」可能定得太硬。實務上 base CLI 用法簡單的 case(list / search),agent 自己就會;只有遇到複雜情境(tag / property / whiteboard)才該 load。

**待決:** description 要不要改成 lazy load 語氣(「reach for `heptabase:heptabase-cli` when you need anything beyond simple operations」)。

---

## Prompt 2 ── 段落重排(用已知存在的測試卡)

### 為什麼要先建測試卡

P1 卡在「找卡片」沒進到 pull → edit → push 主流程。為了確保 P2 能跑完整流程,先用 `heptabase note create` 建了一張測試卡:

- **cardId:** `330c7cd7-552c-49c4-8c07-df5c273b00b2`
- **標題:** 測試 hbedit:本地開啟新 session 的最小流程
- **內容:** 8 個 H2 段 (TL;DR / 為什麼是 `--plugin-dir` / 開發迴圈 / 驗證 skill 有被 load / 測試 prompt 範本 / 進階:乾淨環境模擬 / 相關)

### Prompt

```
幫我把 cardId 330c7cd7-552c-49c4-8c07-df5c273b00b2 那張卡的
## 開發迴圈 段移到 ## 驗證 skill 有被 load 上面
```

### 實際 trace 摘要

1. ✓ Load skill + `hb doctor`
2. ✓ `hb pull 330c... /Users/leiweicheng/Desktop/HeptaSync` ── pull 成功
3. ✓ 用 Edit tool 交換兩個 H2 段位置(沒動 frontmatter)
4. ✓ `hb push` 成功,output: `preserved=27 edited=0 reordered=2 inserted=0 deleted=0`

push output 的 `reordered=2 edited=0` 證明:純粹 2 個 block 換位置、其他 27 個 block 完全沒動、沒任何內容被改寫。完美執行。

### 觀察到三個 SKILL.md body 該補的問題

#### 問題 1:vault 路徑沒指引 → agent 把專案 root 當 vault

trace 裡 agent 跑的是:

```
hb pull 330c... /Users/leiweicheng/Desktop/HeptaSync
                ↑↑↑ 直接把 hbedit plugin 專案 root 當 vault!
```

結果 `.md` 被寫到 `HeptaSync/notes/測試-hbedit...md` ── **污染了 plugin 專案 repo**。

但專案 root 其實有 `.vault/` 目錄(我們之前留下的)。agent 沒注意到、也沒問、就用 cwd。

SKILL.md body 的 Workflow step 1 只寫:「`hb pull <cardId> <vault>` — pulls the card into `<vault>/notes/`」── `<vault>` 是什麼、預設應該選哪、什麼時候該問使用者,完全沒指引。

**該補:** SKILL.md body 加一段「Choosing a vault」。決策樹大概像:

> 先檢查 cwd 有沒有 `.vault/`?有就用它。沒有就問使用者:「要用哪個目錄當 vault?(沒有的話我可以建個 tmp 的)」── 千萬別預設用 cwd,可能會污染專案 repo。

#### 問題 2:push 前沒給 diff,直接 push

trace 是 `Edit → 立刻 hb push`,中間沒「我要把 A 段移到 B 段上面,這樣 OK 嗎?」也沒 dry-run。

對這次測試卡 OK(我們就是要改它),但對真實使用者的筆記是潛在風險 ── SKILL.md body 自己寫得很清楚「`hb push` overwrites real card content」,結果 LLM 預設就是「edit 完直接 push」,完全沒安全閥。

**該補:** SKILL.md body 加 `## Safety: review before push` 段。

決策樹大概像:

> 除非使用者明確說「直接 push」「不用問」「就改吧」,否則 push 前先把改動 summary 告訴使用者(例如「我要把 A 段移到 B 段上面,然後 push 回卡片 X」),等使用者確認再 push。改動越大(拆卡 / 跨卡批次)越要先給 diff;只改一個字的錯字可以直接 push 沒差。

順帶要查:`hb push` 有沒有 `--dry-run` 模式?有的話可以納入安全 flow。

#### 問題 3:push 完沒清理 pull 下來的 .md

push 成功後,`/Users/leiweicheng/Desktop/HeptaSync/notes/測試-hbedit本地開啟新-session-的最小流程.md` 還躺在 repo 裡。SKILL.md body 沒寫 push 完該不該刪這個檔。

累積下來會有兩個問題:
- repo 被一堆殘檔污染(更要命:這個 plugin 的 repo,別人會 clone 來看)
- 下次 pull 同一張卡會覆寫上去,使用者如果中間動過本地檔但忘了 push 就會丟資料(SKILL.md body 已經有這個警告,但沒寫 push 完該清檔)

**該補:** SKILL.md body 在 Workflow 加 step 4「Cleanup」── push 成功後刪掉本地 .md。或者明寫「保留本地 .md 直到使用者確認不需要」── 都行,重點是要寫死預設行為,別讓 LLM 自由發揮。

順帶該決定:`notes/` 要不要進 `.gitignore`?測試完才發現 repo 已經被污染,該補一下。

### 測完還原

把 P2 改的順序還原回去(用本地手動 swap + hb push),`reordered=2` ── 卡片恢復原狀。SKILL.md 沒動。

---

## Prompt 3 ── 拆卡(重新設計)

### 原本的版本為什麼廢掉

原本 P3 是:

```
我有張很長的 LeetCode 卡關於 Two Sum,裡面同時寫了 Brute Force 和 Hash Map
兩種解法,幫我拆成兩張獨立的卡
```

**問題:你的 vault 裡根本沒有題號 1 的 Two Sum 卡。** 我當初設計 prompt 時用「經典 LeetCode 題」的直覺,沒先 `heptabase card list` 確認。結果 agent 搜了 4 次都找不到,變成跟 P1 同一種測試(找不到卡 → 問使用者) ── 拆卡 workflow 完全沒測到。

教訓:**測 workflow 的 prompt 必須給已知存在的卡片**。P2 之所以能跑通,正是因為給了已知 cardId(330c7cd7...)。

### 新版 P3

用同一張測試卡(330c7cd7...),把它的某段獨立成新卡:

```
cardId 330c7cd7-552c-49c4-8c07-df5c273b00b2 那張卡太長了,
把 ## TL;DR 和 ## 為什麼是 `--plugin-dir` 兩段抽出來獨立成一張新卡,
標題叫「hbedit 本地測試 — 快速啟動」,
原卡只保留剩下的內容
```

### 想觀察什麼

| 觀察點 | 為什麼重要 |
|---|---|
| agent 知不知道 split 的正確 flow? | SKILL.md body **完全沒寫**拆卡 workflow,純看 LLM 自己想:pull 原卡 → 抽段落 → 用 `heptabase note create` 建新卡 → 從原卡刪掉那段 → `hb push` 原卡 |
| 新卡用什麼指令建? | hbedit 沒有「create」指令,正確做法是用官方 `heptabase note create -f <file>`。agent 會不會走錯路想用 `hb push`(會失敗,因為新檔沒 frontmatter)? |
| 兩張新卡的 cardId 怎麼回報? | `heptabase note create` 回傳 JSON 帶 id。agent 有沒有抓 id 回報給使用者 |
| 原卡的 push 有沒有正確刪掉 2 個 H2 block? | 看 push output 的 `deleted=2` |
| 整個流程有沒有先給使用者看 plan? | 拆卡是「大改動」── 按 P2 觀察 2 的安全閥邏輯,這種 case 應該先給 plan 再執行 |

### 預期看到的問題

SKILL.md body 完全沒寫拆卡 workflow,**所以 agent 100% 會自己想辦法**。不管它做出什麼,都是 signal:

- 做對了 → 證明 LLM 自己會推 → SKILL.md body 不一定要寫
- 做錯了 → 證明 SKILL.md body 必須補一段「Multi-card workflows: split / merge」

---

## Prompt 4 ── 跨卡批次(重新設計)

### 原本的版本為什麼廢掉

原本 P4 是「把所有 LeetCode 卡裡的 `O(n)` 改成 `O(n) time`」── 同樣的問題:我沒先確認你 vault 裡有多少 LC 卡、有多少卡寫了 `O(n)`。

### vault 實際狀況

剛剛掃過,你 vault 裡有 **20 張 `[數字] 標題` 格式的 LC 卡**:

```
[98] Validate Binary Search Tree
[98] Validate Binary Search Tree — In-order Traversal
[105] Construct Binary Tree from Preorder and Inorder Traversal
[154] Find Minimum in Rotated Sorted Array II
[208] Implement Trie (Prefix Tree)
[211] Design Add and Search Words Data Structure
[212] Word Search II
[230] Kth Smallest Element in a BST
[230] Kth Smallest Element in a BST — Iterative (Stack)
[297] Serialize and Deserialize Binary Tree
[297] Serialize and Deserialize Binary Tree — Stream-based (sstream)
[355] Design Twitter
[621] Task Scheduler
[703] Kth Largest Element in a Stream
[973] K Closest Points to Origin
[1046] Last Stone Weight
[1448] Count Good Nodes in Binary Tree
[1448] Count Good Nodes in Binary Tree — Iterative (Stack)
[2657] Find the Prefix Common Array of Two Arrays
[3927] Minimize Array Sum Using Divisible Replacements
```

### 新版 P4

```
我所有 LeetCode 卡的標題都是 [編號] 標題 格式。
幫我在每一張的最前面(標題下面)加一行 link 回到 LeetCode 官網,
格式像:🔗 https://leetcode.com/problems/<slug>/
slug 自己從標題猜(例如 [98] Validate Binary Search Tree → validate-binary-search-tree)。
```

### 想觀察什麼

| 觀察點 | 為什麼重要 |
|---|---|
| agent 怎麼定義「所有 LeetCode 卡」? | description 提到 cross-card batch,但 SKILL.md body 沒寫怎麼 enumerate ── agent 用 tag?用標題前綴?如何處理 [98] 和 [98] — In-order Traversal 這種變體? |
| 有沒有先列候選清單給使用者確認? | 20 張一次改是大手術,應該先列出來給使用者確認,而不是直接 loop 全跑 |
| batch flow 怎麼組織 vault? | 20 張 pull 下來會在 `notes/` 一次塞 20 個檔,vault 會不會爆 |
| 中間出錯怎麼處理? | 例如第 10 張 push 失敗(conflict 或 tag typo),agent 會不會繼續跑剩下 10 張?還是停下來問? |
| 全部 push 完有沒有 summary? | 「20 張全部成功」vs「18 成功 2 失敗」── agent 該明確報告 |
| 有沒有清理 `notes/` 下 20 個檔? | 同 P2 觀察 3,只是放大 20 倍 |

### 為什麼選「加 link」這個 task 而不是「改 `O(n)`」

兩個理由:

1. **加 link 一定會動到所有卡片**(每張卡都需要插入新行) ── 確保每張卡都被實際編輯,測試結果不會因為「有 5 張卡剛好不含 O(n)」而被稀釋。
2. **每張卡的修改內容不同**(slug 從標題推) ── 不只是 find-replace,需要 agent 對每張卡個別判斷,更接近真實 batch 場景。

如果想保守一點測,可以改成更安全的 P4 變體:

```
幫我看一下這 5 張卡的標題,只 pull 不 push:
[98] [105] [208] [211] [230]
我想知道它們現在的內容大概長怎樣。
```

純讀 batch、不寫,風險更低。但這也測不到 push 流程。看你要冒多大風險。

---

## 全部測完之後要決定什麼

P3 / P4 跑完,結合 P1 / P2,會累積到以下要動 SKILL.md 的清單:

### description(frontmatter)

- [ ] 「load `heptabase:heptabase-cli` first」這句要不要改成 lazy load 語氣?
- [ ] 是否要加 negative trigger(「Do not use for creating new cards or pure appends — call the `heptabase` CLI directly」)?

### body 要新增的段

- [ ] `## Choosing a vault` ── 別預設用 cwd / 該檢查 `.vault/` / 該問使用者
- [ ] `## Safety: review before push` ── 大改動先給 plan、push 前看 diff
- [ ] `## Cleanup after push` ── push 完是否刪 `notes/<file>.md` 的預設行為
- [ ] `## Multi-card workflows: split / merge / batch` ── 拆卡 / 併卡 / 跨卡批次的 flow(P3 / P4 跑完才知道要寫多細)

### body 要強化的段

- [ ] Workflow step 1「Identify the card」── 把「找不到卡時的 fallback 搜尋策略」明寫(P1 的好行為要保固定)

### 其他

- [ ] `notes/` 進 `.gitignore`?(repo 已被污染需要清)
- [ ] `hb push --dry-run` 是否存在?若有,納入 safety flow

---

## 文件狀態

寫於 2026-05-23,P1 + P2 測完、P3 + P4 還沒跑的時間點。

P3 / P4 跑完後,把結果直接 append 到這份文件下面,不要另開新檔。
