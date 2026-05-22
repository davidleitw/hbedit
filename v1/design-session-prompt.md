我在做一個叫 **HeptaSync** 的工具 —— 一個**非官方**的 Heptabase「本地 markdown ⇄ 卡片」同步層,打算最終包成一個 Claude Code skill。可行性 POC 已經做完(21 個實驗驗證 pull / push 都可行),最小的 `hs.py` 也能實際跑了。現在我想跟你**一起把「語意與使用者體驗設計」想清楚**,再進實作。

## 第一步:先讀懂現況

請先讀這些檔案(在 `/Users/leiweicheng/Desktop/HeptaSync/`),讀完跟我確認你掌握重點再開始:

- `v1/DESIGN.md` —— 架構與同步模型設計
- `vault/notes/heptasync.md` —— 專案總覽(本身也是一個實際同步過的範例檔)
- `v1/skill/SKILL.md` —— skill 草稿
- `v1/hs.py`、`v1/frontmatter.py` —— 目前可運作的程式

## 已經拍板、不要再推翻的

- push 用「transplant」策略(借 Heptabase 自己做 markdown→內部格式轉換,再把原卡的 block ID 移植回去)—— 已驗證可行。
- 範圍走「隨選 pull / push」,**不做背景 daemon**。
- 已知限制:卡片引用無法從 markdown 建立(只能唯讀);內容上限 100,000 字元(約 700 行混合內容就可能 push 不回去);無事件推送只能輪詢;CLI 不能刪 tag。
- 只透過官方 `heptabase` CLI;Python 全部 stdlib-only。

## 這個 session 要設計的

請當成**互動式 design 討論** —— 不要直接丟一份成品給我。一項一項跟我釐清、給選項、講清楚取捨,先探索我的真實使用情境再下結論。

### A. 同步語意

- 工作單位是「單卡隨選」還是「vault 資料夾」?
- 檔案生命週期:新檔 = create、有 cardId = update;本地把檔案刪掉,要不要連帶 trash 卡片?
- 改名語意:檔名 / 卡片標題,誰是真相?
- pull 下來的檔案放哪、怎麼命名?
- journal、whiteboard 算 v1 範圍嗎?

### B. 使用者互動

- push 會覆寫真實資料 —— 每次都先跟我確認嗎?還是給我一份 diff 摘要再決定?
- skill 該多話還是安靜?哪些動作要回報、哪些靜默做掉?
- 太大 / 衝突時,怎麼跟使用者講、給什麼選項?

### C. Tag(我特別想討論)

- 新建卡片時,要**主動問**「要掛哪些 tag」嗎?還是預設不掛?還是從內容 / 資料夾推測?
- 要不要先列出我現有的 tag 讓我挑?
- 在 frontmatter 裡改了 tag,push 時怎麼同步?(注意:從 frontmatter 移除 tag ≠ 刪掉 tag 資料庫)

### D. Frontmatter schema

- 我寫一個全新的純 `.md`(完全沒有 frontmatter)想同步上去 —— skill 要自動補 frontmatter?先問我?怎麼問?
- 哪些欄位是工具自己管(managed)、哪些我可以自己編(像 tags / whiteboards)?
- schema 要不要版本號,方便日後擴充?

## 產出

討論完,把結論整理成 `v1/DESIGN.md` 的一個新章節「語意與互動設計」(或更新既有章節)。
