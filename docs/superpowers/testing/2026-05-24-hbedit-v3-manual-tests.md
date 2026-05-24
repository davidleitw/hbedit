# hbedit v3 — 手動測試集

> 給 v3 (global cache) 用的 end-to-end 手動測試。每一個 TC 都從「真實使用者會怎麼說」出發,
> 而不是預先腳本化的「跑 hb doctor」這類技術指令。目的是同時驗證 (a) hbedit skill 在自然語句下會不會
> 正確被觸發、(b) 觸發後的底層行為符合 spec。
>
> 寫於 2026-05-24。對應 spec: `docs/superpowers/specs/2026-05-24-hbedit-global-cache-design.md`、
> plan: `docs/superpowers/plans/2026-05-24-hbedit-v3-global-cache.md`。

## 為什麼要手動測

`tests/` 底下的 unit / integration 已經覆蓋大部分內部邏輯,但有兩塊 unit test 觸不到:

1. **Skill 觸發** — 自然語句 → agent 判斷該不該用 hbedit。SKILL.md `description` 寫得好不好決定這件事,只能在真實 Claude session 試。
2. **End-to-end 流程含真實 `heptabase` CLI** — `doctor()`、`push()`、`pull()` 都會打 desktop app,unit test 沒辦法跑。

兩件事都得開新 session、丟自然 prompt、看 agent 反應。

## TC 跑法(每一個 TC 都這樣跑)

每個 TC 用**一個全新的 Claude Code session**跑,避免互相污染:

```bash
# 1. 跑該 TC 的「環境 setup」區塊裡的 shell 指令(在你終端機,不是 Claude session)

# 2. cd 到該 TC 指定的工作目錄

# 3. 開一個新 session,把 hbedit plugin load 進去:
claude --plugin-dir /Users/leiweicheng/Desktop/HeptaSync

# 4. 在 session 裡直接貼該 TC 的 prompt(不要加任何引導文字)

# 5. agent 跑完後,把完整輸出貼回給我

# 6. 我評估、更新本檔的「Status」欄,可能會建議修正

# 7. 跑該 TC 的「Reset」區塊清環境,進到下一個 TC
```

`--plugin-dir` 只對該 session 生效、退出即清。

## Test Matrix

| TC | 標題 | 對應 AC / 目的 | Priority | Status |
|---|---|---|---|---|
| TC-1 | 第一次設定 vault | AC #1 | P0 | ✅ pass |
| TC-2 | 把本地筆記推成新卡 | AC #2 | P0 | ⚠️ partial(揭露 skill 邊界 bug,見下方) |
| TC-3 | 拉既有卡片到本地 | pull 流程 | P0 | ✅ pass |
| TC-4 | vault 內健康檢查 | AC #6 (in-vault) | P0 | ⚠️ partial(技術 OK,skill trigger 失效 — Bug 2) |
| TC-5 | vault 外健康檢查 | AC #6 (out) + AC #4 | P0 | 未跑 |
| TC-6 | round-trip 編輯一張卡 | core flow | P0 | 未跑 |
| TC-7 | 在 vault 外 push 檔案 | AC #4(關鍵 v3 bug fix) | P0 | 未跑 |
| TC-8 | 多機同步(clone 模擬) | AC #3 | P0 | 未跑 |
| TC-9 | 從深層子目錄發指令 | vault discovery 回歸 | P1 | 未跑 |
| TC-10 | 帶 v2 schema 的 vault | AC #5 | P1 | 未跑 |
| TC-11 | 開新卡片走 base CLI | skill 邊界 | P1 | 未跑 |

**Status 值**:`未跑` / `✅ pass` / `❌ fail (見備註)` / `⚠️ partial`

> **重要順序提示**:TC-7 需要 `~/.hbedit/` 已經存在(才能觸發 v2 的 vault-walk-up bug)。請至少先跑過 TC-1
> 一次,讓 `~/.hbedit/cache/` 被建出來,再跑 TC-7。建議照 TC 編號順序跑。

---

## TC-1:第一次設定 vault

### 目的

驗證 AC #1:`hb init` 寫出 v3 schema 的 `state.json`、產生 `vaultId` (UUIDv4)、**不**寫 `.gitignore`,
且把 `~/.hbedit/cache/<vault-id>/sidecar/` 也建好。

### 環境 setup

```bash
rm -rf /tmp/hb-tc1
mkdir /tmp/hb-tc1
cd /tmp/hb-tc1
```

### Session 啟動

```bash
cd /tmp/hb-tc1
claude --plugin-dir /Users/leiweicheng/Desktop/HeptaSync
```

### Prompt

```
我這個資料夾打算放一些 markdown 筆記,想跟 Heptabase 同步管理,幫我準備好環境
```

### 預期行為

- Agent 觸發 `hbedit` skill(載入後,description 應該命中「maintain a local markdown file alongside its Heptabase card」)
- 先跑 `hb doctor`(SKILL.md SOP B step 1 要求)
- 跑 `hb init`
- 回報 vaultId、`.hbedit/state.json` 路徑、cache 目錄位置

### 驗證指令(跑完後在終端機跑)

```bash
cat /tmp/hb-tc1/.hbedit/state.json
ls -la /tmp/hb-tc1/.gitignore 2>/dev/null && echo "❌ .gitignore 不該被建出來" || echo "✅ no .gitignore"
VAULTID=$(python3 -c "import json; print(json.load(open('/tmp/hb-tc1/.hbedit/state.json'))['vaultId'])")
echo "vaultId: $VAULTID"
ls -la ~/.hbedit/cache/$VAULTID/sidecar/
```

預期:
- `state.json` 有 `"schemaVersion": 3`、`"vaultId": "<uuid>"`、`"files": {}`
- 沒有 `.gitignore`
- `~/.hbedit/cache/<vaultId>/sidecar/` 存在

### Reset

```bash
VAULTID=$(python3 -c "import json; print(json.load(open('/tmp/hb-tc1/.hbedit/state.json'))['vaultId'])" 2>/dev/null)
rm -rf /tmp/hb-tc1
[ -n "$VAULTID" ] && rm -rf ~/.hbedit/cache/$VAULTID
# 注意:不要 rm -rf ~/.hbedit/ 整個 — TC-7 需要 ~/.hbedit/ 存在
```

### Status

✅ pass (2026-05-24)

- Skill 正確觸發(`Skill(hbedit:hbedit)`)
- 先跑 `hb doctor` 再 `hb init`,符合 SOP B
- `state.json` schemaVersion=3、vaultId=`4953dc4f-bfb1-4502-bf4e-2163d4763bc7`、files={}
- 無 `.gitignore`(AC #1 要求)
- `~/.hbedit/cache/4953dc4f-.../sidecar/` 已建出(空目錄,正常 — 還沒 push 過)
- Bonus:agent 主動提供下一步用法 + 詢問是否 `git init`,行為合理(non-destructive 提問)

---

## TC-2:把本地筆記推成新卡

### 目的

驗證 AC #2:`hb push <untracked-path>` → `action:"created"`,**只在** `.hbedit/` 寫 `state.json`(不寫
`local-state.json`、不建 `sidecar/`),per-machine cache 寫到 `~/.hbedit/cache/<vault-id>/`。

### 環境 setup

```bash
rm -rf /tmp/hb-tc2
mkdir -p /tmp/hb-tc2/notes
cd /tmp/hb-tc2

# 先建好 vault(我們要測 push,不是 init)
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py init

# 寫一個讓 prompt 有具體內容好指的檔
cat > notes/rust-ownership.md <<'EOF'
# Rust Ownership 筆記

今天讀完《The Rust Programming Language》第 4 章,把 ownership 三條核心規則整理一下。

## 三條規則

1. 每個值都有一個 owner
2. 同一時間只能有一個 owner
3. owner 離開 scope,值被 drop
EOF
```

### Session 啟動

```bash
cd /tmp/hb-tc2
claude --plugin-dir /Users/leiweicheng/Desktop/HeptaSync
```

### Prompt

```
我剛在 notes/rust-ownership.md 整理了今天讀 Rust ownership 的筆記,把它存成 Heptabase 卡片
```

### 預期行為

- 觸發 hbedit
- 跑 `hb doctor`
- 跑 `hb push notes/rust-ownership.md`
- 回報 `action:"created"` + cardId

### 驗證指令

```bash
# .hbedit/ 只該有 state.json
ls -la /tmp/hb-tc2/.hbedit/

# state.json 該有檔案綁定
cat /tmp/hb-tc2/.hbedit/state.json

VAULTID=$(python3 -c "import json; print(json.load(open('/tmp/hb-tc2/.hbedit/state.json'))['vaultId'])")
CARDID=$(python3 -c "import json; print(list(json.load(open('/tmp/hb-tc2/.hbedit/state.json'))['files'].values())[0]['cardId'])")
echo "vaultId: $VAULTID"
echo "cardId: $CARDID"

# 全域 cache 該有東西
ls -la ~/.hbedit/cache/$VAULTID/
cat ~/.hbedit/cache/$VAULTID/local-state.json
ls ~/.hbedit/cache/$VAULTID/sidecar/

# Heptabase 上確實有這張卡(會 echo 出 cardId 你可以對)
heptabase note read $CARDID 2>&1 | head -10
```

預期:
- `.hbedit/` 只有 `state.json`,沒有 `local-state.json` / `sidecar/`
- `state.json` 的 `files["notes/rust-ownership.md"]` 有 cardId、tags=[]
- `~/.hbedit/cache/<vault-id>/local-state.json` 有對應 entry
- `~/.hbedit/cache/<vault-id>/sidecar/<cardId>.json` 存在
- Heptabase 上 cardId 對應的卡片實際存在,內容是 Rust ownership 筆記

### Reset

```bash
CARDID=$(python3 -c "import json; print(list(json.load(open('/tmp/hb-tc2/.hbedit/state.json'))['files'].values())[0]['cardId'])" 2>/dev/null)
VAULTID=$(python3 -c "import json; print(json.load(open('/tmp/hb-tc2/.hbedit/state.json'))['vaultId'])" 2>/dev/null)
[ -n "$CARDID" ] && heptabase card trash $CARDID
rm -rf /tmp/hb-tc2
[ -n "$VAULTID" ] && rm -rf ~/.hbedit/cache/$VAULTID
```

### Status

⚠️ partial (2026-05-24) — 揭露 SKILL.md skill-trigger 邊界 bug

**觀察到的行為**
- agent 載入 `heptabase:heptabase-cli`,**沒**載入 `hbedit:hbedit`
- 直接跑 `heptabase note create --content-file ...`,**沒**呼叫 `hb push`
- 卡片建出來了(cardId `1ad66646-771c-4e52-8014-0f684ff12d9e`),但是 orphan — 不在 `state.json` 裡

**為什麼會這樣(根因)**

SKILL.md `When to use` 表把「Create a brand-new card from scratch and never touch it again」分給 base CLI、把「Push a local markdown doc as a new card and **maintain it long-term**」分給 hbedit。TC-2 的 prompt(「整理了…把它存成 Heptabase 卡片」)沒給「之後還會改 / 維護 / 同步」這種持續性訊號,agent 判斷為一次性建卡 → 走 base CLI 完全符合 SKILL.md 設計。

但這暴露一個盲點:**cwd 已經在 vault 內**(`/tmp/hb-tc2/.hbedit/state.json` 存在),理論上任何 markdown→card 動作都該預設走 hbedit、寫進綁定。SKILL.md 沒寫這條 vault-aware disambiguation,agent 也沒 `ls -la` 檢查 cwd。

**修法**:強化 SKILL.md description / SOP B,加一條「If cwd has `.hbedit/state.json`, prefer hbedit for any markdown→card operation」。修完後用原 prompt 重跑 TC-2 驗證。詳見 Bugs found 段。

---

## TC-3:拉既有卡片到本地

### 目的

驗證 `hb pull <cardId> <path>` 流程:寫檔、寫 state.json、寫 local-state.json、寫 sidecar。

### 環境 setup

```bash
rm -rf /tmp/hb-tc3
mkdir -p /tmp/hb-tc3
cd /tmp/hb-tc3
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py init

# 先在 Heptabase 建一張卡(模擬「已經存在的卡」),記下 cardId
heptabase note create -t "v3 TC-3 測試卡" -c "這是一段測試用內容\n\n第二段\n\n第三段"
```

跑完上面那行 `heptabase note create` 會印出一個 JSON,包含新卡的 `id`。把那個 id 記下來,
**塞到下面 prompt 的 `<cardId>` 位置**。

### Session 啟動

```bash
cd /tmp/hb-tc3
claude --plugin-dir /Users/leiweicheng/Desktop/HeptaSync
```

### Prompt(把 `<cardId>` 換成上面記下的 id)

```
Heptabase 上有張卡 ID 是 <cardId>,我想抓下來本地改,放到 notes/ 底下
```

### 預期行為

- 觸發 hbedit
- 跑 `hb doctor`
- 跑 `hb pull <cardId> notes/<some-name>.md`(agent 可能會用卡片標題當檔名)
- 回報 path、檔案內容、tags

### 驗證指令

```bash
ls /tmp/hb-tc3/notes/
cat /tmp/hb-tc3/.hbedit/state.json
VAULTID=$(python3 -c "import json; print(json.load(open('/tmp/hb-tc3/.hbedit/state.json'))['vaultId'])")
cat ~/.hbedit/cache/$VAULTID/local-state.json
ls ~/.hbedit/cache/$VAULTID/sidecar/
```

預期:`notes/` 下有 `.md`、state.json 有對應 entry、local-state.json 有 contentMd5/localMd5、
sidecar 下有 `<cardId>.json`。

### Reset

```bash
CARDID=$(python3 -c "import json; print(list(json.load(open('/tmp/hb-tc3/.hbedit/state.json'))['files'].values())[0]['cardId'])" 2>/dev/null)
VAULTID=$(python3 -c "import json; print(json.load(open('/tmp/hb-tc3/.hbedit/state.json'))['vaultId'])" 2>/dev/null)
[ -n "$CARDID" ] && heptabase card trash $CARDID
rm -rf /tmp/hb-tc3
[ -n "$VAULTID" ] && rm -rf ~/.hbedit/cache/$VAULTID
```

### Status

✅ pass (2026-05-24)

- Skill 正確觸發
- agent 走完整 SOP A 前置:`hb doctor` → `ls -la` 確認 vault 存在 → `heptabase note read` 先看卡片(用標題當檔名)→ `hb pull <cardId> notes/v3-tc-3-測試卡.md`
- 檔案內容跟 seed 一致(3 個 H2 段、Lorem ipsum)
- `state.json` 綁定正確
- `~/.hbedit/cache/<vault>/local-state.json` 寫入 contentMd5/localMd5/syncedAt
- `~/.hbedit/cache/<vault>/sidecar/<cardId>.json` 寫入

**對比 TC-2 的旁證**:TC-3 prompt 含「抓下來**本地改**」維護訊號 → 命中 hbedit;TC-2 prompt「**存成**卡片」一次性語意 → 走 base CLI。確認 agent 是吃語意訊號而非環境訊號 → Bug 1 修補方向(加 vault-aware disambiguation)成立。

---

## TC-4:vault 內健康檢查

### 目的

驗證 AC #6 in-vault 路徑:cwd 在 vault 內時,`hb doctor` 的 `detail` 該含兩行 ——
heptabase 版本行 + `cache: <path> (exists: yes)` 行。

### 環境 setup

```bash
rm -rf /tmp/hb-tc4
mkdir /tmp/hb-tc4
cd /tmp/hb-tc4
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py init
```

### Session 啟動

```bash
cd /tmp/hb-tc4
claude --plugin-dir /Users/leiweicheng/Desktop/HeptaSync
```

### Prompt

```
我這台跟 Heptabase 接得 OK 嗎?跑個檢查
```

### 預期行為

- 觸發 hbedit(或直接執行 `hb doctor` — 邊界判斷)
- 跑 `hb doctor`
- 回報的 JSON `detail` 含兩行:
  - `heptabase 0.3.x, desktop app reachable`
  - `cache: /Users/leiweicheng/.hbedit/cache/<uuid>/ (exists: yes)`

### 驗證指令

agent 輸出本身就是驗證 —— 看 `detail` 有沒有 `cache:` 那行、`exists:` 是不是 `yes`。

### Reset

```bash
VAULTID=$(python3 -c "import json; print(json.load(open('/tmp/hb-tc4/.hbedit/state.json'))['vaultId'])" 2>/dev/null)
rm -rf /tmp/hb-tc4
[ -n "$VAULTID" ] && rm -rf ~/.hbedit/cache/$VAULTID
```

### Status

⚠️ partial (2026-05-24) — 技術行為正確,skill trigger 失效

**Agent 實際行為(不符預期)**
- **沒**載入 hbedit skill
- **沒**跑 `hb doctor`
- 跑了 `which heptabase` + `heptabase --version`(基本 CLI 檢查)
- 跑了 `heptabase journal read $(date +%Y-%m-%d)`(被使用者 CLAUDE.md 的「Heptabase-touching session lazy-fill」規則接走)
- 結論「接得 OK」,但根本沒檢查到 hbedit 該檢查的東西(vault 綁定狀態、cache 目錄、desktop app 可達性)

**AC #6 技術行為(直接跑 `hb doctor` 驗證,綁定正確)**
```json
{"command":"doctor","status":"ok","detail":"heptabase 0.3.0, desktop app reachable\ncache: /Users/leiweicheng/.hbedit/cache/9c8c0f62-19cc-45f0-b9fa-d0ca98dcb95d (exists: yes)"}
```
- `detail` 確實含兩行 ✅
- cache 路徑正確 ✅
- `exists: yes`(init 已 eager 建 sidecar/)✅

**結論**:v3 Task 8 的 `_doctor_cache_line` 實作完全 OK,但這個能力被 SKILL.md `description` 跟使用者 CLAUDE.md 兩層遮蔽,自然語句下 agent 不會抵達。詳見 Bug 2。

---

## TC-5:vault 外健康檢查

### 目的

驗證 AC #6 out-of-vault 路徑 + AC #4 vault-discovery 修補:cwd 在 `/tmp`(沒有 vault 祖先,但 `~/.hbedit/`
存在)時,`hb doctor` 該:
- 正常 ok
- `detail` **只有** heptabase 版本那行,**沒有** cache 行
- **不**因為 walk-up 撞到 `~/.hbedit/` 而吐 `state-corrupt` 錯誤(這是 v2 latent bug,v3 修)

### 環境 setup

```bash
# 確認 ~/.hbedit/ 存在(跑過 TC-1 之後就會在了)
ls ~/.hbedit/cache/ || echo "⚠️ ~/.hbedit/cache/ 不存在 — 先跑 TC-1"
```

### Session 啟動

```bash
cd /tmp
claude --plugin-dir /Users/leiweicheng/Desktop/HeptaSync
```

### Prompt(故意跟 TC-4 用同一句,只有環境不同)

```
我這台跟 Heptabase 接得 OK 嗎?跑個檢查
```

### 預期行為

- 跑 `hb doctor`
- 回報 ok,`detail` 只有 `heptabase 0.3.x, desktop app reachable` 單一行
- **不**有 cache 行
- **不**有 state-corrupt 之類錯誤(這個錯誤出現代表 v3 修補回歸)

### 驗證

看 agent 輸出的 JSON `detail`:應該是單行字串、status 是 ok。

### Reset

無 — 沒污染任何狀態。

### Status

未跑

---

## TC-6:round-trip 編輯一張卡

### 目的

驗證 hbedit 核心使用案例:讀現有檔 → 修內容 → push,正確走 block-ID transplant。

### 環境 setup

```bash
rm -rf /tmp/hb-tc6
mkdir -p /tmp/hb-tc6/notes
cd /tmp/hb-tc6
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py init

# 寫一個有故意 typo 的檔
cat > notes/react-hooks.md <<'EOF'
# React Hooks 速記

## useState

`useState` 是最常用的 hook,用來在 function component 裡管 local state。

## useEffec

`useEffec` 用來在 component lifecycle 的不同階段跑 side effect,例如打 API。

## useMemo

`useMemo` 拿來 cache 昂貴計算結果,deps 沒變就不重算。
EOF

# 先 push 上去,讓它變 tracked
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py push notes/react-hooks.md
```

### Session 啟動

```bash
cd /tmp/hb-tc6
claude --plugin-dir /Users/leiweicheng/Desktop/HeptaSync
```

### Prompt

```
notes/react-hooks.md 第二個 H2 標題的 useEffec 是 typo,正確是 useEffect,內文也一樣有錯,
都改掉然後同步回 Heptabase
```

### 預期行為

- 觸發 hbedit(命中「edit existing card content」)
- 跑 `hb doctor`
- 讀檔、Edit 改 typo(兩處)
- 跑 `hb push notes/react-hooks.md`
- 回報 `action:"updated"`,counters 該有 `edited >= 1`,其他 block `preserved`

### 驗證指令

```bash
# 改完應該沒有 useEffec 殘留
grep -c "useEffec\b" /tmp/hb-tc6/notes/react-hooks.md || echo "✅ 已全改"
# Heptabase 上也應該已經更新(用 cardId 從 state.json 抓)
CARDID=$(python3 -c "import json; print(list(json.load(open('/tmp/hb-tc6/.hbedit/state.json'))['files'].values())[0]['cardId'])")
heptabase note read $CARDID 2>&1 | grep -c "useEffect" && echo "✅ remote 也更新了"
```

預期:
- 本地檔沒有 `useEffec\b`(只 match 完整 typo)
- agent 輸出的 push JSON 有 `action:"updated"` + `edited >= 1`
- Heptabase 卡片內容已更新

### Reset

```bash
CARDID=$(python3 -c "import json; print(list(json.load(open('/tmp/hb-tc6/.hbedit/state.json'))['files'].values())[0]['cardId'])" 2>/dev/null)
VAULTID=$(python3 -c "import json; print(json.load(open('/tmp/hb-tc6/.hbedit/state.json'))['vaultId'])" 2>/dev/null)
[ -n "$CARDID" ] && heptabase card trash $CARDID
rm -rf /tmp/hb-tc6
[ -n "$VAULTID" ] && rm -rf ~/.hbedit/cache/$VAULTID
```

### Status

未跑

---

## TC-7:在 vault 外 push 檔案 ⚠️ 關鍵 v3 bug fix

### 目的

驗證 AC #4 — v2 latent bug 已修。背景:v2 `find_vault_root` 只看 `.hbedit/` 目錄存不存在;從 `/tmp/xxx`
walk-up 會撞到 `~/.hbedit/`(其實是 global cache),被誤認為 vault 根、嘗試讀 state.json 失敗、吐
`state-corrupt`。v3 改成要求 `.hbedit/state.json` 檔案存在才算 vault,該路徑現在該回 `not-in-vault`。

### 環境 setup

```bash
# ⚠️ 前置條件:~/.hbedit/cache/ 必須存在,才能觸發 v2 bug 條件
ls ~/.hbedit/cache/ || { echo "❌ ~/.hbedit/cache/ 不存在,請先跑 TC-1"; exit 1; }

rm -rf /tmp/random-notes
mkdir /tmp/random-notes
echo "# 隨手記" > /tmp/random-notes/foo.md
cd /tmp/random-notes
```

### Session 啟動

```bash
cd /tmp/random-notes
claude --plugin-dir /Users/leiweicheng/Desktop/HeptaSync
```

### Prompt

```
foo.md 推到 Heptabase 變一張卡
```

### 預期行為

- agent 跑 `hb push foo.md`
- 收到 error JSON:`status:"error"`、`code:"not-in-vault"`
- agent 該根據 SKILL.md 的 `not-in-vault` SOP 問使用者要不要 `hb init`
- **絕對不該**收到 `state-corrupt` 錯誤(若有 → v3 修補回歸)

### 驗證

agent 輸出本身就是驗證。確認 error code 是 `not-in-vault`、**不是** `state-corrupt`。

### Reset

```bash
rm -rf /tmp/random-notes
```

### Status

未跑

---

## TC-8:多機同步(clone 模擬)

### 目的

驗證 AC #3 — 兩台機器透過 git 同步 vault 設定,新機器 pull 時走 baseline-established 路徑(不誤判 conflict)。
v2 因為 cache 還在 `.hbedit/` 裡會跟 git 衝突;v3 把 cache 移到 `~/.hbedit/cache/`,
clone 過來的 repo 沒有 cache → smart-pull 該安全建立 baseline。

### 環境 setup

```bash
# Phase A:machine_a 設定 vault 並 push 一張卡
rm -rf /tmp/machine_a /tmp/machine_b
mkdir -p /tmp/machine_a/docs
cd /tmp/machine_a
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py init
cat > docs/mm.md <<'EOF'
# 多機同步測試

machine A 寫的內容。下一段該被 machine B 拉到。

## 第二段

Lorem ipsum dolor sit amet.
EOF
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py push docs/mm.md

# 記下 cardId 跟 vaultId(reset 跟 sanity check 都用得到)
CARDID=$(python3 -c "import json; print(list(json.load(open('.hbedit/state.json'))['files'].values())[0]['cardId'])")
VAULTID=$(python3 -c "import json; print(json.load(open('.hbedit/state.json'))['vaultId'])")
echo "cardId: $CARDID"
echo "vaultId: $VAULTID"

# Phase B:模擬 git clone — 只 cp .hbedit/ + docs/(代表 git 追蹤的東西)
cp -r /tmp/machine_a/.hbedit /tmp/machine_b/
cp -r /tmp/machine_a/docs /tmp/machine_b/

# Phase C:模擬 fresh machine — 把這台對 vaultId 的 cache 刪掉
rm -rf ~/.hbedit/cache/$VAULTID

# 確認 machine_b 沒有 cache(該空)
ls ~/.hbedit/cache/ | grep $VAULTID && echo "❌ cache 沒清乾淨" || echo "✅ cache 已清"
```

### Session 啟動

```bash
cd /tmp/machine_b
claude --plugin-dir /Users/leiweicheng/Desktop/HeptaSync
```

### Prompt

```
我剛從 git clone 下來這個 repo,進來想接著編輯 docs/mm.md,先確認 sync 狀態 OK 不 OK 再動手
```

### 預期行為

- agent 觸發 hbedit,認到這是 SKILL.md SOP C 的場景(continue editing after git clone)
- 跑 `hb doctor`
- 跑 `hb pull docs/mm.md`(single-arg form,smart-pull)
- 回報 `action:"baseline-established"`(**不是** `conflict`)
- 重點:machine_b 的 cache 從零建起,沒有把 machine_a 寫到 Heptabase 的內容當衝突

### 驗證指令

```bash
VAULTID=$(python3 -c "import json; print(json.load(open('/tmp/machine_b/.hbedit/state.json'))['vaultId'])")
# baseline 該被建出來
cat ~/.hbedit/cache/$VAULTID/local-state.json
# 本地檔該跟 machine_a 寫進去的一模一樣(沒被覆蓋、沒 .conflict.md)
diff /tmp/machine_a/docs/mm.md /tmp/machine_b/docs/mm.md && echo "✅ 兩邊內容一致"
ls /tmp/machine_b/docs/ | grep conflict && echo "❌ 不該有 .conflict.md"
```

預期:
- agent 輸出 `action:"baseline-established"`
- `~/.hbedit/cache/<vaultId>/local-state.json` 重新被建出
- `machine_b/docs/mm.md` 跟 `machine_a/docs/mm.md` 一致
- 沒有 `.conflict.md` 殘檔

### Reset

```bash
CARDID=$(python3 -c "import json; print(list(json.load(open('/tmp/machine_a/.hbedit/state.json'))['files'].values())[0]['cardId'])" 2>/dev/null)
VAULTID=$(python3 -c "import json; print(json.load(open('/tmp/machine_a/.hbedit/state.json'))['vaultId'])" 2>/dev/null)
[ -n "$CARDID" ] && heptabase card trash $CARDID
rm -rf /tmp/machine_a /tmp/machine_b
[ -n "$VAULTID" ] && rm -rf ~/.hbedit/cache/$VAULTID
```

### Status

未跑

---

## TC-9:從深層子目錄發指令

### 目的

回歸測試:`find_vault_root` 該從子目錄正確 walk up 找到 vault 根。v2 / v3 都該過,但 v3 改了 vault discovery
條件(需要 state.json 檔),要確認子目錄場景沒壞。

### 環境 setup

```bash
rm -rf /tmp/hb-tc9
mkdir -p /tmp/hb-tc9/src/components/deep
cd /tmp/hb-tc9
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py init

# 在深層目錄丟一個檔
cat > src/components/deep/note.md <<'EOF'
# 深層子目錄筆記

放在 src/components/deep/ 底下的內容。
EOF

# session cwd 設在最深處
```

### Session 啟動

```bash
cd /tmp/hb-tc9/src/components/deep
claude --plugin-dir /Users/leiweicheng/Desktop/HeptaSync
```

### Prompt

```
這個目錄下的 note.md 推到 Heptabase
```

### 預期行為

- agent 跑 `hb push note.md`(或 `hb push <abs-path>`)
- hbedit 從 cwd walk up 找到 `/tmp/hb-tc9/.hbedit/state.json`,當作 vault root
- push 成功,state.json 用 vault-relative path 紀錄(`src/components/deep/note.md`)

### 驗證指令

```bash
cat /tmp/hb-tc9/.hbedit/state.json
# 該有 "src/components/deep/note.md" 這個 key
python3 -c "import json; d = json.load(open('/tmp/hb-tc9/.hbedit/state.json')); print(list(d['files'].keys()))"
```

預期:
- push 成功 (`action:"created"`)
- state.json 的 `files` 含 `src/components/deep/note.md`(相對 vault root 的路徑,不是絕對路徑也不是 cwd-relative)

### Reset

```bash
CARDID=$(python3 -c "import json; print(list(json.load(open('/tmp/hb-tc9/.hbedit/state.json'))['files'].values())[0]['cardId'])" 2>/dev/null)
VAULTID=$(python3 -c "import json; print(json.load(open('/tmp/hb-tc9/.hbedit/state.json'))['vaultId'])" 2>/dev/null)
[ -n "$CARDID" ] && heptabase card trash $CARDID
rm -rf /tmp/hb-tc9
[ -n "$VAULTID" ] && rm -rf ~/.hbedit/cache/$VAULTID
```

### Status

未跑

---

## TC-10:帶 v2 schema 的 vault

### 目的

驗證 AC #5:碰到 `schemaVersion: 2` 的 state.json,任何 hb 指令該明確拒絕(`state-schema-unsupported`),
不做自動 migration,清楚告訴使用者怎麼處理。

### 環境 setup

```bash
rm -rf /tmp/hb-tc10
mkdir -p /tmp/hb-tc10
cd /tmp/hb-tc10
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py init

# 手動把 schemaVersion 降到 2
python3 -c "
import json
p = '.hbedit/state.json'
d = json.load(open(p))
d['schemaVersion'] = 2
json.dump(d, open(p, 'w'), indent=2)
print('降版完成')
"
cat .hbedit/state.json

# 寫一個檔讓 agent 有東西可推
echo "# 測試" > foo.md
```

### Session 啟動

```bash
cd /tmp/hb-tc10
claude --plugin-dir /Users/leiweicheng/Desktop/HeptaSync
```

### Prompt

```
foo.md 同步到 Heptabase
```

### 預期行為

- agent 跑 `hb push foo.md`
- 收到 error JSON:`status:"error"`、`code:"state-schema-unsupported"`,detail 該提到「schemaVersion is 2, expected 3」
- agent 該照 SKILL.md SOP 告知使用者:這是舊版 state、不會自動 migrate,建議重 `hb init` 或刪 `.hbedit/` 重來
- **不**自動嘗試修復

### 驗證

agent 輸出 JSON 確認 error code 是 `state-schema-unsupported`、回給使用者的訊息夠清楚(不要瞎修)。

### Reset

```bash
rm -rf /tmp/hb-tc10
# 沒進 ~/.hbedit/cache/(push 在驗 schema 階段就停了)
```

### Status

未跑

---

## TC-11:開新卡片走 base CLI(skill 邊界)

### 目的

Negative test:測試 hbedit 的 SKILL description 是否正確把「開新卡片」這條路擋在外面。SKILL.md
寫得很清楚:

| Task | Tool |
| --- | --- |
| Create a brand-new card from scratch and never touch it again | `heptabase note create` |

所以「請幫我開一張新卡」這種 prompt,agent **不該**用 hbedit,該直接呼叫 `heptabase note create`。

### 環境 setup

```bash
# 隨便一個目錄都行,有沒有 vault 都不影響
rm -rf /tmp/hb-tc11
mkdir /tmp/hb-tc11
cd /tmp/hb-tc11
```

### Session 啟動

```bash
cd /tmp/hb-tc11
claude --plugin-dir /Users/leiweicheng/Desktop/HeptaSync
```

### Prompt

```
幫我在 Heptabase 開一張新卡,標題叫「2026 Q2 OKR 草稿」,內容先放兩個 placeholder section 就好
```

### 預期行為

- agent **不**觸發 hbedit
- 直接用 `heptabase note create`(base CLI)建卡
- 回報新 cardId
- **不**呼叫 `hb push`(若有,代表 SKILL description 沒擋住、邊界破功)

### 驗證

看 agent 用了什麼指令:應該是 `heptabase note create -t ... -c ...`,**不該**出現 `hb push`。

### Reset

```bash
# 把建出來的卡片 trash 掉(cardId 從 agent 輸出抓)
# heptabase card trash <cardId-from-agent-output>
rm -rf /tmp/hb-tc11
```

### Status

未跑

---

## 全部跑完之後

把這份檔的 Test Matrix 跟每個 TC 的 Status 欄填好。如果有任何 fail / partial,寫一段 root cause + 修補 commit 在
最下面的「Bugs found」段(目前還沒,留空)。

## Bugs found

### Bug 1:SKILL.md 缺 vault-aware disambiguation,在 vault 內仍可能誤走 base CLI

- **發現於**:TC-2(2026-05-24)
- **症狀**:cwd 在已 init 的 vault 內,使用者說「把 notes/xxx.md 存成 Heptabase 卡片」,agent 走 `heptabase note create`(base CLI)而不是 `hb push`(hbedit)。結果卡建出來但 orphan,不在 `state.json` 綁定裡 — 下次 pull / edit / sync 都接不上。
- **根因**:SKILL.md `When to use` 表把 hbedit 的觸發條件綁在「maintain long-term」的訊號上,但使用者自然語句通常不會明說維護意圖。當 cwd 已經是 vault,agent 該以環境訊號(vault 存在)而非語意訊號(「之後還會改」)作判斷,但 SKILL.md 目前沒寫這條規則,agent 也沒主動 `ls -la` 檢查。
- **影響**:任何使用者「新增筆記到 vault」的自然 prompt 都可能走錯路;orphan 卡片散落 Heptabase,使用者後續想透過 hbedit 維護時要手動 `hb pull <cardId> <path>` 重綁。
- **修補方向**:在 SKILL.md description / SOP B 加一條「cwd 含 `.hbedit/state.json` → 任何 markdown→card 操作預設走 hbedit;base CLI 只在沒 vault 或使用者明確要求一次性建立時用」。修完後用 TC-2 原 prompt 重跑驗證。
- **修補 commit**:(尚未,規劃中)
- **重測狀態**:TC-2 待修補後重跑

## 設計筆記

### Prompt 設計原則(這次學到的)

- **別用技術術語**:不講 `hbedit`、`hb push`、`vault`、`state.json`。改用使用者語言:「同步」「推到 Heptabase」
  「綁好環境」。
- **別腳本化**:不寫「先(1)…再(2)…」這種步驟,讓 agent 自己決定流程。
- **別替 reviewer 做事**:不講「我要比較兩次差異」「把 vaultId 印給我」等元指示,測完反而從輸出讀。
- **同一 prompt 在不同環境跑出不同結果是 feature 不是 bug**:TC-4 / TC-5 共用同一句,差別是 cwd
  在不在 vault — 這正好測 agent 跟底層命令對環境的反應一致。
- **負面測試很重要**:TC-11 測「不該觸發」也是 skill 完整度的一部分,不只測「該觸發時有沒有觸發」。
