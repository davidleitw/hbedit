# hbedit — 白話說明與批判檢視

> 給「知道做了很多實驗,但看不懂具體在幹嘛」的你。這張卡用白話講清楚:
> 我們想做什麼、它會怎麼運作、實驗證明了什麼、以及它到底值不值得做。
> (技術細節在另一張卡「HeptaSync POC — 實驗記錄」。)

## 一句話

讓 AI agent(或你自己)可以**像編輯一般文字檔一樣**整理 Heptabase 筆記 ——
改本地的 `.md` 檔,變更就同步回 Heptabase。

## 我們想解決什麼問題

Heptabase 有一個官方命令列工具(CLI),agent 可以透過它操作你的筆記。
但這個工具有一個很關鍵的缺口:

- ✅ 它能**新建**一張卡片
- ✅ 它能在一張卡片**最後面追加**內容
- ❌ 它**不能用純文字(markdown)修改一張既有卡片的中間內容**

為什麼?因為 Heptabase 內部不是用純文字存筆記,而是一種有結構的格式
(可以想成「一堆有編號的樂高積木」)。要改既有卡片,CLI 要你直接給它這種
積木格式 —— 手工拼很容易拼壞整張卡。

**結果:agent 目前只能幫你「加東西」,不能真的幫你「整理 / 改寫」既有筆記。**
這就是 hbedit 要補的洞。

## hbedit 想做的事 —— 你會怎麼用它

hbedit 在你電腦上開一個資料夾,把 Heptabase 的筆記**鏡像成一堆純文字
`.md` 檔**:

```
my-vault/
  notes/
    leetcode-1448.md
    english-log.md
    ...
```

- agent(或你)直接編輯這些 `.md` 純文字檔 —— 最自然、最好操作的形式。
- hbedit 把改動**推回** Heptabase,也把 Heptabase 上的改動**拉下來**。
- 每個 `.md` 檔最上面有一段隱藏標頭(frontmatter),記住「這個檔對應哪張
  Heptabase 卡片」。預覽 markdown 時這段標頭看不見。

對 agent 來說,從「要組一串 CLI 指令 + 拼積木格式」變成「就改一個文字檔」。

## 運作方式(白話)

整個系統就兩個動作:

**拉下來 (Pull):** Heptabase 卡片 → 讀出來 → 把積木格式翻譯成 markdown →
寫成本地 `.md` 檔。(已驗證,不會掉資料)

**推上去 (Push):** 這是最巧妙的地方。因為 CLI 不讓我們直接把 markdown 寫進
既有卡片,我們用一招「移植」:

1. 把編輯過的 markdown 丟給 Heptabase,讓它**自己**建一張暫時的卡 ——
   等於借 Heptabase 的手,把 markdown 翻譯成正確的積木格式。
2. 這張暫時卡的積木是全新編號的。我們把**原卡片的積木編號「移植」**到沒被
   改動的積木上 —— 這樣 Heptabase 才知道「這還是同一塊,只是內容改了」,
   不會弄丟卡片之間的關聯。
3. 把結果存回原卡片,刪掉暫時卡。

好處:我們**完全不用自己懂 Heptabase 的內部格式**,翻譯永遠交給 Heptabase。

若做成背景程式(daemon),它就是每隔幾秒跑一次這個循環:

```
偵測本地改了什麼 → 推上去
偵測遠端改了什麼 → 拉下來
```

## 實驗證明了什麼(不用看 21 個細節)

我對真實的 Heptabase 跑了 21 個測試。**白話結論:這套做法行得通。**

- 改一段、刪一段、加一段、調順序、加粗體 —— 推回去之後都正確。
- 改到一半、兩邊同時改 —— 有機制偵測得到衝突。
- 拉下來再推回去,完整一圈不掉資料。

## 三件做不到的事(誠實說)

1. **卡片之間的「引用連結」沒辦法從文字檔建立** —— 只能在 Heptabase app 裡建。
2. **太大的筆記推不回去** —— 有容量上限,超大卡片會被擋下。
3. **不是即時的** —— 靠每隔幾秒檢查一次,不是 Heptabase 一變就馬上知道。

## 批判性檢視:這到底值不值得做?

重新檢視 Heptabase CLI 的能力後,誠實講幾點:

**❓ agent 真的需要「一整個本地資料夾」嗎?**
agent 本來就能直接呼叫 CLI。對 agent 而言「改檔案」不見得比「呼叫 CLI」更
自然 —— 它真正的痛點只有一個:**不能改既有卡片**。而這個痛點,光靠「翻譯 +
移植」這兩個零件就解決了,不一定需要整個資料夾鏡像。

**⚠️ 永遠在背景跑的 daemon 有「假同步」風險。**
因為引用連結、超大卡片同步不了,本地鏡像其實是個「不完美的副本」。如果
agent 把本地檔當成唯一真相在改,但有些東西其實沒同步上去,久了兩邊就會悄悄
對不上。**錯的同步比沒有同步更糟。**

**⚠️ Heptabase 本身已有自己的雲端同步。** 再疊一套 hbedit,等於有兩套同步
系統,要小心互相打架。

**⚠️ 維護成本。** CLI 介面會隨 Heptabase 更新改版,一個依賴 CLI 的常駐程式
等於要一直追著 Heptabase 跑。

### 我的建議:分三層,不要一次做到底

| 層級 | 是什麼 | 價值 / 風險 |
|---|---|---|
| **① 翻譯 + 移植兩個零件** | 讓 agent 能「改一張既有卡片」 | **真正的寶物**。最小、最安全、解決核心痛點。你現有的 LeetCode / journal skills 馬上受惠 —— 從「只能 append」升級成「能改寫」 |
| **② 隨選工作區** | `pull` 幾張要處理的卡 → 本地改 → `push` 回去 | 加上 grep / git / 離線。明確指令、無背景程式、不會偷偷漂移。**這就是 v1 該做的** |
| **③ 全庫背景 daemon** | 整個 vault 永遠自動雙向同步 | 加上「全庫隨時最新」,但帶來漂移 / 衝突 / 維護成本。**只有當你真的常常需要全庫 grep 才值得做** |

**結論:① 一定值得做,它本身就有用;② 是合理的 v1;③ 先別做 —— 等你用過
② 之後,再回頭問自己「我真的需要背景常駐嗎」。**

換句話說:你原本想的「本地資料夾 + 永遠自動同步」這個畫面,**核心價值是對的
(agent 終於能整理既有筆記了),但不需要一開始就做成永遠在背景跑的版本。**
先做「隨選 pull / push」,風險低很多,而且 90% 的好處都拿得到。

## 一句話總結

> hbedit 想做的事**有真實價值** —— 它讓 AI 終於能「改寫」你的 Heptabase
> 筆記,而不只是「往後面加」。但不要一開始就做成全自動背景同步;先把「翻譯 +
> 移植」做出來,再做「隨選 pull / push」,這樣風險最低、見效最快。

## 打包成 skill 需要什麼

把這件事做成一個 skill 是對的方向 —— skill 是「隨選」呼叫的,正好對應「不做
背景 daemon」的決定。需要的東西分三塊:

### 一、已經有了 —— POC 產出的可重用零件

POC 不只是做實驗,它順手把 skill 的「引擎」做出來、而且驗證過了:

| 零件 | 作用 |
|---|---|
| `pm2md.py` | Heptabase 內部格式 → Markdown(pull) |
| `transplant.py` | block ID 移植(push 的關鍵招式) |
| `htb.py` | Heptabase CLI 的封裝 |
| `frontmatter.py` | `.md` 檔的 metadata schema |

這些已驗證可用,但目前是「POC 品質」—— 能跑、邏輯對,但還沒把所有邊角情況收完。

### 二、還需要補的

1. **一個真正的進入點命令** —— 像 `hb pull <卡片>` / `hb push <檔案>`。目前只有
   測試用的 `poc.py`,不是日常工具。skill 會叫 agent 跑這些。
2. **狀態管理** —— sidecar(上次 pull 下來的原始 JSON,push 移植時要用)。
   skill 版可簡化:pull 時把 `.md` 和 sidecar 寫在一起。
3. **決策樹的實作** —— 超大卡片拆檔、append-only vs 改中間、衝突處理、引用
   唯讀。這些都設計好了(在 `DESIGN.md`),要寫成程式 + 寫進 skill 指令。
4. **防呆 / 錯誤處理** —— app 沒開、CLI 版本不符、timeout、半成品復原。
5. **converters 升級到 production 品質** —— 補更多 node 類型與 edge case 的保險。

### 三、skill 本身的外殼

| 要件 | 內容 |
|---|---|
| `SKILL.md` | 觸發條件、工作流程、決策樹、前置檢查 —— 給 agent 看的「說明書」 |
| `scripts/` | 上面那些 `.py` 引擎 |
| `references/` | frontmatter schema、ProseMirror schema 筆記、決策樹細節 |
| 版本守門 | 檢查 `heptabase --version` 在支援範圍,不符就停 |
| 定位 | 獨立 skill,與現有的 `heptabase-cli` skill 並存(共用同一個 CLI) |

### skill 補的是什麼洞

現有的 `heptabase-cli` skill 只能 **append / create**;hbedit skill 的賣點
是它能**改寫既有卡片**。觸發情境 = 「使用者想整理 / 重寫既有的 Heptabase
筆記」。做出來後,你其他的 skill(LeetCode、journal …)也能站在它上面 ——
從「只能往後加」升級成「能改」。

### 最小可行版本

不用一次做滿。最小的 skill = 零件 + 「編輯單一卡片」流程:pull 一張卡 →
agent 改 → push 回去。不需要 vault、不需要 daemon。先把這個做順,再決定要不要
加多檔案工作區。

### 小結

> 最難的部分 ——「這套做法到底行不行」—— POC 已經回答了。剩下的是工程:把零件
> 收尾、寫一個 `hb` 命令、寫 `SKILL.md`。**研究風險清掉了,剩下實作。**

## 如果做成 skill —— 運作方式與 SKILL.md 草稿

以下是我設想的 hbedit skill 完整運作方式。寫法刻意**模擬官方
`heptabase-cli` skill 的結構**(Prerequisites / Workflow / Known limitations /
Warnings),但最上面用**顯眼的橫幅標示「非官方」** —— 使用者問起來時,agent
就能明確回答:這是第三方社群工具,不是 Heptabase 官方做的,只透過官方 CLI
運作。

### agent 實際會怎麼跑一輪

1. **觸發** —— 使用者說「幫我重寫 / 整理 / 重排某張卡」時載入這個 skill。
   (純 append / 新建不會觸發,那用官方 CLI 就夠。)
2. **前置檢查** —— app 有開、`heptabase --version` 在支援範圍內。
3. **Pull** —— `hb pull <cardId>`:卡片變成本地 `.md`,旁邊存一份 sidecar
   JSON(push 移植時要用)。
4. **Edit** —— agent 用一般檔案工具改 `.md` 內文,不碰 frontmatter。
5. **Push 前決策** —— 估 JSON 大小、查衝突、判斷是 append-only 還是改中間。
6. **Push** —— 走 transplant 把改動寫回同一張卡;遇到太大 / 衝突就照決策樹
   處理,並把明確原因講給使用者。

### 為什麼要強調「非官方」

這個 skill 跟官方 `heptabase-cli` skill 長得很像(故意的,降低學習成本),
但它**不是 Heptabase 出的**。所以 SKILL.md 最上面放一個醒目橫幅,明寫:
非官方、社群工具、只透過官方 CLI 運作、不碰資料庫。使用者問「這是官方的嗎」,
agent 就照橫幅回答。

完整的 SKILL.md 草稿(模擬 `heptabase-cli` 寫法)放在 `v1/skill/SKILL.md`,
重點章節:`Prerequisites` / `Workflow`(pull → edit → push)/ `Decision
rules`(size pre-flight、conflict、oversized card 拆檔、references 唯讀)/
`Known limitations` / `Warnings`,最上面是 UNOFFICIAL 橫幅。
