# HeptaSync

> **非官方工具。** 不隸屬 Heptabase,也不是它做的。完全建構在官方
> `heptabase` CLI 之上 —— 絕不直接碰 Heptabase 的資料庫或內部檔案。

📖 *[← English README](./README.md)*

## 這是做什麼的?

問題是這樣的。官方的 `heptabase` CLI 可以**新建**一張卡、可以往卡片
**尾巴加東西** —— 但它沒辦法用純文字去改一張卡的**中間**。結果就是,
AI agent 只能幫你「往筆記裡加東西」,不能幫你「整理它」。

HeptaSync 補的就是這個洞。它讓你(或 AI agent)把一張 Heptabase 卡片
當成普通的 markdown 檔來對待:把它拉下來、用一般文字工具隨你怎麼改、
再推回去。同一張卡、身分不變 —— 只是內容被改寫了。

所以當你想「把那張亂掉的筆記整理一下」「把這幾段重新排序」「統一我
所有 LeetCode 卡片的格式」—— 這就是 HeptaSync 的用途。如果你只是想
開一張新卡、或加一行字,直接用官方 CLI 就好,更簡單。

## 怎麼用?

HeptaSync 以 **Agent Skill** 的形式發佈 —— 在 Claude Code、Codex CLI、
opencode 裡都能用。

裝好之後(見 **[`v1/INSTALL.md`](./v1/INSTALL.md)**),你不用特別下什麼
指令。直接用白話跟你的 agent 講就好:

> 「把我的『讀書清單』卡片拉下來,照主題重新整理。」

agent 會認出這是 HeptaSync 的活、接手處理。它背後其實就跑三個指令:

```
hs doctor                  # 確認環境沒問題
hs pull <cardId> <vault>   # 卡片  ->  本地一個 .md 檔
#   ... 編輯那個 .md ...
hs push <file>             # .md   ->  推回同一張卡
```

你也可以自己在終端機跑這幾個指令,如果你想手動操作的話。

## 它到底怎麼運作?

最麻煩的是 **push**。Heptabase 卡片是用它自己的內部格式存的
(ProseMirror JSON),不是 markdown —— 所以你不能直接把改好的文字
丟給它。

HeptaSync 的招數:讓 **Heptabase 自己**做轉換。

1. **Pull** —— 讀出卡片,把它的內部 JSON 轉成乾淨的 markdown,存成
   本地 `.md` 檔(檔案開頭有一小段隱藏標頭,記住它是哪張卡)。
2. **Push** —— 拿你改好的 markdown,請 Heptabase 用它建一張**暫時卡**。
   這樣 Heptabase 就幫你把 markdown→內部格式轉好了。HeptaSync 接著把
   原卡的 block 編號「移植」到對應的 block 上,存回真正的那張卡,再把
   暫時卡刪掉。

結果就是:HeptaSync 自己完全不用懂 Heptabase 的內部格式。而且因為
block 編號有保留下來,指向這張卡的連結和引用都不會斷。

兩個值得知道的安全機制:每次 push 會先檢查卡片是不是在你編輯期間被
改過 —— 如果有,HeptaSync 會把你的版本備份成一個 `.conflict.md` 檔,
而不是直接蓋掉。另外,它**只**透過官方 `heptabase` CLI 溝通 —— 絕不
直接碰 Heptabase 的資料庫或檔案。

## 現況

**v1** —— note 卡片的 pull / 編輯 / push,含衝突偵測與 tag 同步。
安裝步驟:[`v1/INSTALL.md`](./v1/INSTALL.md)。完整設計文件:
[`v1/DESIGN.md`](./v1/DESIGN.md)。
