# hbedit

> **非官方工具。** 不是 Heptabase 出的、也不隸屬於它。完全建構在官方 `heptabase`
> CLI 之上 —— 絕不直接碰 Heptabase 的資料庫、儲存或內部檔案。

📖 *[← English README](./README.md)*

## 這是什麼

hbedit 讓你(或 AI agent)把 Heptabase 上的卡當成普通 markdown 檔來改 ——
拉下來、隨你怎麼改、推回去。同一張卡、ID 不變,指向這張卡的連結也不會斷掉。

最直接的例子:你想叫 Claude 幫你修一張既有卡片裡的 typo、或把段落重新排序。
官方 `heptabase` CLI 可以**新建**卡、可以往卡片**尾巴加東西**,但沒辦法用純
文字去改一張卡的**中間**。hbedit 補的就是這個洞。

如果你只是要**開一張新卡**或**加一行字**到既有卡片末尾,直接用官方 CLI 就好,
更簡單,也不用裝 hbedit。

實際怎麼改寫(scratch-card 招數、衝突保護、per-machine cache),下面的
[架構](#架構--怎麼運作的)那段有講。

## 怎麼裝

你會需要:

- Python 3.9+(純 stdlib、不用 pip)
- Heptabase 桌面 app,**v1.91.0 或更新**,而且要開著
- 官方 `heptabase` CLI 已**在桌面 app 內啟用**:**Settings → AI Features →
  CLI**(它跟桌面 app 一起裝、**不是** 從 npm 或 brew 來的)。macOS 會自動
  幫你上 PATH;Windows 會看到 app 印一條 PATH 設定指令,照著跑一次。完整
  步驟:<https://support.heptabase.com/en/articles/14715462-how-to-use-heptabase-cli>

然後挑你用的 agent:

**Claude Code**(在 Claude 裡輸入兩行):
```
/plugin marketplace add davidleitw/hbedit
/plugin install hbedit@hbedit
```

**Codex CLI**(一行):
```sh
curl -fsSL https://raw.githubusercontent.com/davidleitw/hbedit/master/install.sh | sh -s codex
```

**opencode**(一行):
```sh
curl -fsSL https://raw.githubusercontent.com/davidleitw/hbedit/master/install.sh | sh -s opencode
```

裝完開個新 shell:

```sh
hb doctor
```

回 `"status": "ok"` 就可以了。其他結果照它印的 `detail` 修(多半是還沒裝
`heptabase` CLI、版本不對、或桌面 app 沒開)。手動安裝步驟、不放心
`curl | sh` 想先檢查的對策,完整版在 [`INSTALL.md`](./INSTALL.md)。

## 怎麼用

你不用直接下 `hb` 任何指令 —— 用人話跟 agent 講就好,skill 會自己判斷
什麼時候該接手。下面是幾個會自動觸發 hbedit 的場景:

### 1. 改一張既有卡片

最常見的場景。卡片已經在 Heptabase 上,你想改裡面的內容。

> *「我那張 React Hooks 卡片裡的 `useEffec` 是 typo,改成 `useEffect`,
> 順便把段落順序調一下,useState 放前面。」*

agent 跑 `hb pull` 把卡片拉成本地 `.md` → 在 `.md` 上編輯 → `hb push`
推回去。原卡的 block ID 都保留下來,所以指向這張卡內部 block 的引用都不會斷。

### 2. 把本地 markdown 推進 Heptabase 開始追蹤

你在 vault 裡寫了一份新的 markdown,想讓它變成一張會持續維護的 Heptabase 卡。

> *「我這個 vault 多了 `notes/rust-ownership.md`,推到 Heptabase,
> 我之後還會繼續從本地改。」*

agent 跑 `hb push`,建立新卡 + 把 `path → cardId` 寫進
`.hbedit/state.json`。從此本地改完一聲「同步」就推回去。

### 3. 多機協作(git clone 後接續編輯)

你在電腦 A 把 vault 弄好、`git push`。`.hbedit/state.json` 跟著 commit
上去了,但 per-machine 的 sync cache 沒有(也不該有)。換到電腦 B clone
下來:

> *「剛從 git clone 下來這個 repo,想接著編輯 `docs/mm.md`。」*

agent 跑 `hb pull docs/mm.md`(single-arg smart-sync 形式)。如果本地檔
跟 Heptabase 上的內容一致,回 `baseline-established`、你就直接開編。
如果中間真的有歧異,會回 `conflict`、把遠端的內容寫進工作檔、把你本地的
版本另存成 `docs/mm.conflict.md` 讓你對照處理 —— 你的版本不會被悶聲蓋掉。

### 4. 改 tag,不動其他既有的 tag

> *「把這張 Two Sum 卡加上 `algorithm` 跟 `hashmap` 兩個 tag。」*

agent 跑 `hb tag add`,既有 tag 完全不會被動到。

### 5. 不用追蹤,隨手丟一張就好

Escape hatch —— 當你只想要一張一次性卡片、不想要 hbedit 介入。

> *「幫我隨手建一張卡記今天的會議結論,不用追蹤、丟上去就好。」*

skill 會自己讓開,agent 直接用官方 `heptabase note create`。不會寫
`state.json`、不會生 cache、之後也不會有殘留要清。

## 架構 / 怎麼運作的

### 它是個 Agent Skill

hbedit 包成 Claude Code plugin / Agent Skill。`SKILL.md` 告訴 agent
「什麼時候該用我、怎麼用」;後面接一支 Python CLI 叫 `hb`。沒有後端、
沒有 daemon —— 就是一支純 stdlib Python 腳本,呼叫官方 `heptabase` CLI
做事。

### Vault 模型

在某個目錄跑 `hb init`,那個目錄就是一個 *vault*。Vault 的狀態刻意切成
兩塊:

- **`.hbedit/state.json`** —— 放在 vault 裡、**會 git commit**。記每個檔
  綁哪張卡(`path → {cardId, tags}`)+ 一個 `vaultId` UUID。
- **`~/.hbedit/cache/<vaultId>/`** —— 放在你 home、**不**會 commit。
  per-machine 的 sync 狀態:`local-state.json`(每個檔的 MD5,用來偵測
  改動)、`sidecar/<cardId>.json`(原卡的 ProseMirror JSON,給 block ID
  對位用)。

這樣切的好處:clone 一份 vault 過去,綁定跟著一起走;cache 每台機器第一
次跑 `hb pull <path>` 時自己重建。多機協作就是靠這個架構工作的。

### Block-ID 移植招數

這是 hbedit 最關鍵的設計。Heptabase 卡片**內部**是 ProseMirror JSON,
不是 markdown,所以你不能直接把改好的純文字塞回去。hbedit 不想自己寫
一個 markdown ↔ ProseMirror 轉換器(維護成本太高、bug 太多),就走偏門
—— 讓 **Heptabase 自己**做轉換:

1. **Pull**:讀卡的 ProseMirror JSON → 轉成乾淨 markdown → 寫 `.md` 檔。
   綁定資訊(這個檔是哪張卡)只記在 `state.json`,**不**寫在檔案裡。
2. **Push**:拿你改好的 markdown → 請 Heptabase 用它建一張**用完即丟的
   scratch 卡**(`heptabase note create`)→ 從 scratch 卡撈出新版
   ProseMirror JSON(Heptabase 已經幫你轉好了)→ 把原卡的 block ID 移植
   到對應的 block 上 → 寫回原卡 → 把 scratch 卡 trash 掉。

因為原 block ID 在 round-trip 過程一直保留著,指向卡片內部 block 的引用
(block reference、embed)都不會斷。

### Card 引用 round-trip

Heptabase 的卡片可以內嵌其他卡片 — 底層 ProseMirror 是一個 `card`
node,UI 上呈現為 inline 或 block-level 的卡片引用。`pm2md` 把這種
embed 序列化成 markdown 裡的 `[[card:<UUID>]]` placeholder。push 時
hbedit 要把它轉回真正的 `card` node,但**沒辦法**只靠
`heptabase note create` 達成:它的 markdown parser 不認識
`[[card:<UUID>]]`,會把它留成純文字。

hbedit 用兩步驟解決:

1. 讓 `heptabase note create` 照常 parse markdown,placeholder 會
   被當成純文字落到 ProseMirror 裡。
2. 把這份 ProseMirror 讀回來,DFS 走一遍,把每個
   `[[card:<valid-uuid>]]` text node 替換成真正的 `card` node,
   再用 `heptabase note save` 把改過的 ProseMirror 存回去。

第 2 步只在 markdown 包含字串 `[[card:` 時才跑。沒有 embed 的卡片
走原本的單次呼叫路徑,沒有額外 round-trip。

兩個要知道的影響:

- **如果你要在卡片裡寫純文字的 `[[card:<UUID>]]`**(例如寫 hbedit
  本身的說明文件),請用 backtick 包起來 `` `[[card:<UUID>]]` ``,
  或寫進 fenced code block。沒包的話 hbedit 會在 push 時把它變成
  真的 card embed,UUID 不存在就會變成 dangling reference。
- **placeholder 大小寫不敏感**,但會 normalize 成小寫存。
  `[[card:ABC...]]` 也可以。

`date` inline node 透過同一個機制 round-trip,使用嚴格
`[[date:YYYY-MM-DD]]` placeholder 語法(兩端都會做行事曆驗證;非
嚴格格式例如帶時間的會 fall back 回 `<!-- UNCONVERTED inline date -->`,
markdown 不會假裝可以 round-trip 一個工具其實處理不了的形態)。
`mention` node 還是不能 round-trip,序列化成
`<!-- UNCONVERTED inline mention -->`,push 回去會掉。

**舊 pull 的遷移**:vault 裡仍含 `<!-- UNCONVERTED inline date -->`
的 `.md` 不會自動升級。請對那張卡片重新 `hb pull <path>`,markdown
才會更新成新 placeholder。沒重 pull 就 push 一樣會掉 date,行為跟舊版相同。

### 安全保證

兩個值得知道的設計:

1. **不碰內部**:hbedit **只**透過官方 `heptabase` CLI 跟 Heptabase 對話。
   不開它的 SQLite、不戳 IndexedDB、不碰任何內部檔案。Heptabase 那邊改
   儲存格式,hbedit 跟著官方 CLI 的相容性走就好。
2. **衝突保護**:每次 `hb push` 前先檢查遠端卡有沒有在你編輯期間被改過。
   有的話會把你的本地版本另存成 `<檔>.conflict.md`、印 `content-conflict`
   錯誤,**不會**直接蓋掉。

## 目前的限制

- **卡片內嵌 (card embed) round-trip 自 v0.1.2 起支援**,使用
  `[[card:<UUID>]]` placeholder 語法(見上方「Card 引用
  round-trip」)。針對特定 block 的 cross-card *block reference*
  仍然不能 round-trip — 只有整張卡片的 embed 可以。
- **Date inline node round-trip 支援**,使用 `[[date:YYYY-MM-DD]]`
  placeholder 語法(機制跟 card embed 相同;見上方「Card 引用
  round-trip」)。如果要在 markdown 裡寫純文字的
  `[[date:YYYY-MM-DD]]`,用 backtick 包起來
  (`` `[[date:2026-05-26]]` ``)。Heptabase 未來如果加 time-of-day
  或 timezone,在未支援前會 fall back 回
  `<!-- UNCONVERTED inline date -->` 註解。
- **單卡 push 大約 10 萬字會撞天花板**:ProseMirror serialization 的硬限制。
- **只支援 note 卡片**:journal、PDF、whiteboard 都不行。
- **沒有 `hb mv`**:想改名 tracked `.md`,要手動編 `state.json`。
- **Windows 未驗證**:我們完全沒有在 native Windows(PowerShell / cmd)
  上跑過 hbedit。`bin/hb` 是 POSIX shell script,WSL 應該可以、native
  Windows 八成需要改才能動。CI 也只跑 Linux 跟 macOS。如果你是 Windows
  使用者願意試,歡迎回報結果,或更歡迎直接送 PR。

## 還想知道更多

- [`INSTALL.md`](./INSTALL.md) —— 完整安裝、手動安裝、`curl | sh` 想先看再
  跑的對策
- [`skills/hbedit/SKILL.md`](./skills/hbedit/SKILL.md) —— agent 自己看的那
  份:default+escape 決策表 + 完整指令列表
- [`skills/hbedit/references/workflows.md`](./skills/hbedit/references/workflows.md)
  —— 編輯 / 多機 / 拆卡 / 合卡 / 衝突處理 SOP
- [`skills/hbedit/references/errors.md`](./skills/hbedit/references/errors.md)
  —— 每個 error code 對應的處理步驟

### 改 hbedit 本身

不用全域安裝,直接把這個目錄 load 進一個 Claude Code session:

```bash
claude --plugin-dir /path/to/hbedit
```

`--plugin-dir` **只對該 session** 生效 —— 改完 `SKILL.md`、重開 session
就在測新版,不留任何殘留。

## Changelog

詳見 [`CHANGELOG.md`](./CHANGELOG.md)。版本依 [SemVer](https://semver.org) 命名。

## License

MIT —— 詳見 [`LICENSE`](./LICENSE)。
