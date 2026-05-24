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

| TC | 標題 | 對應 / 目的 | Priority | Status |
|---|---|---|---|---|
| TC-1 | 第一次設定 vault | AC #1(回歸) | P0 | ✅ pass |
| TC-3 | 拉既有卡片到本地 | pull 流程(回歸) | P0 | ✅ pass |
| TC-7 | 在 vault 外 push 檔案 | AC #4 v3 bug fix(回歸) | P0 | 未跑 |
| TC-9 | 從深層子目錄發指令 | vault discovery(回歸) | P1 | 未跑 |
| TC-10 | 帶 v2 schema 的 vault | AC #5(回歸) | P1 | 未跑 |
| TC-trigger-A | 改既有卡中段 | edit-existing 正面觸發 | P0 | 未跑 |
| TC-trigger-B | 多機 clone 後接續編輯 | multi-machine 正面觸發 | P0 | 未跑 |
| TC-trigger-C | vault 內推 markdown 帶維護訊號 | new default+escape 設計驗證 | P0 | 未跑 |
| TC-trigger-D | 一次性建卡 + 明確 fire-and-forget | escape hatch 啟動 / 負面觸發 | P0 | 未跑 |

**Status 值**:`未跑` / `✅ pass` / `❌ fail (見備註)` / `⚠️ partial`

**已刪除**:TC-4 / TC-5(`hb doctor` 不該獨佔健康檢查 — 改框法,行為已用 shell 直接驗證)。
**已替換**:TC-2 → TC-trigger-C,TC-6 → TC-trigger-A,TC-8 → TC-trigger-B,TC-11 → TC-trigger-D。

> **重要順序提示**:TC-7 需要 `~/.hbedit/` 已經存在(才能觸發 v2 的 vault-walk-up bug)。請至少先跑過 TC-1
> 一次,讓 `~/.hbedit/cache/` 被建出來,再跑 TC-7。建議照 TC 編號順序跑(TC-1 / TC-3 / TC-7 / TC-9 / TC-10 / TC-trigger-A/B/C/D)。

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

## TC-trigger-A:改既有卡中段(強訊號正面觸發)

### 目的

驗證強訊號正面觸發:使用者明確要修改 vault 內已綁定的卡片內容,agent 該載入 hbedit、走 SOP A(pull → edit → push)。對應「edit-existing」主用例。

### 環境 setup

```bash
rm -rf /tmp/hb-tcA
mkdir -p /tmp/hb-tcA/notes
cd /tmp/hb-tcA
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py init

cat > notes/react-hooks.md <<'EOF'
# React Hooks 速記

## useState

useState 用來在 function component 裡管 local state。

## useEffec

useEffec 用來在 component lifecycle 的不同階段跑 side effect。

## useMemo

useMemo cache 昂貴計算結果。
EOF

# Push 一次讓它變 tracked,並抓出 cardId 給 prompt 用
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py push notes/react-hooks.md
python3 -c "import json; d=json.load(open('.hbedit/state.json')); print('cardId:', list(d['files'].values())[0]['cardId'])"
```

把印出來的 cardId 塞到下面 prompt 的 `<cardId>` 位置。

### Session 啟動

```bash
cd /tmp/hb-tcA
claude --plugin-dir /Users/leiweicheng/Desktop/HeptaSync
```

### Prompt(替換 `<cardId>`)

```
<cardId> 那張卡裡面第二個 H2 標題 useEffec 是 typo,改成 useEffect,內文也有錯一起改,然後同步回去
```

### 預期行為

- 載入 `hbedit:hbedit` skill
- 跑 `hb doctor`
- 讀 notes/react-hooks.md(或 `hb pull` — 兩者皆可)
- 用 Edit tool 改 typo(兩處)
- 跑 `hb push notes/react-hooks.md`
- 回報 `action:"updated"`、`detail.edited >= 1`

### 驗證指令

```bash
grep -c 'useEffec\b' /tmp/hb-tcA/notes/react-hooks.md || echo "✅ 本地已改"
CARDID=$(python3 -c "import json; print(list(json.load(open('/tmp/hb-tcA/.hbedit/state.json'))['files'].values())[0]['cardId'])")
heptabase note read $CARDID 2>&1 | grep -c useEffect && echo "✅ remote 也更新"
```

### Reset

```bash
CARDID=$(python3 -c "import json; print(list(json.load(open('/tmp/hb-tcA/.hbedit/state.json'))['files'].values())[0]['cardId'])" 2>/dev/null)
VAULTID=$(python3 -c "import json; print(json.load(open('/tmp/hb-tcA/.hbedit/state.json'))['vaultId'])" 2>/dev/null)
[ -n "$CARDID" ] && heptabase card trash $CARDID
rm -rf /tmp/hb-tcA
[ -n "$VAULTID" ] && rm -rf ~/.hbedit/cache/$VAULTID
```

### Status

未跑

---

## TC-trigger-B:多機 clone 後接續編輯(強訊號正面觸發)

### 目的

驗證強訊號正面觸發:使用者描述 git clone 場景 + 想繼續編輯,agent 該載入 hbedit、走 SOP C(`hb pull <path>` smart-sync → baseline-established)。對應「multi-machine」主用例。

### 環境 setup

```bash
# Phase A:在 machine_a 設定 vault 並 push
rm -rf /tmp/machine_a /tmp/machine_b
mkdir -p /tmp/machine_a/docs
cd /tmp/machine_a
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py init

cat > docs/mm.md <<'EOF'
# 多機同步測試

machine A 寫的初始內容。

## 第一段

Lorem ipsum dolor sit amet.

## 第二段

下一段待 machine B 接手編輯。
EOF
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py push docs/mm.md

CARDID=$(python3 -c "import json; print(list(json.load(open('.hbedit/state.json'))['files'].values())[0]['cardId'])")
VAULTID=$(python3 -c "import json; print(json.load(open('.hbedit/state.json'))['vaultId'])")
echo "cardId: $CARDID"
echo "vaultId: $VAULTID"

# Phase B:模擬 git clone(只 cp 進 git 追蹤的東西)
cp -r /tmp/machine_a/.hbedit /tmp/machine_b/
cp -r /tmp/machine_a/docs /tmp/machine_b/

# Phase C:模擬 fresh machine — 把這台對 vaultId 的 cache 刪掉
rm -rf ~/.hbedit/cache/$VAULTID

# 確認 machine_b 沒 cache
ls ~/.hbedit/cache/ | grep $VAULTID && echo "❌ cache 沒清乾淨" || echo "✅ cache 已清"
```

### Session 啟動

```bash
cd /tmp/machine_b
claude --plugin-dir /Users/leiweicheng/Desktop/HeptaSync
```

### Prompt

```
我剛從 git clone 下來這個 repo,進來想接著編輯 docs/mm.md 加一段新內容
```

### 預期行為

- 載入 `hbedit:hbedit` skill(強訊號:「git clone」+「接著編輯」)
- 跑 `hb doctor`
- 跑 `hb pull docs/mm.md`(single-arg smart-sync 形式)
- 回報 `action:"baseline-established"`(**不是** `conflict`)
- 才開始編輯 + push

### 驗證指令

```bash
VAULTID=$(python3 -c "import json; print(json.load(open('/tmp/machine_b/.hbedit/state.json'))['vaultId'])")
cat ~/.hbedit/cache/$VAULTID/local-state.json
diff /tmp/machine_a/docs/mm.md /tmp/machine_b/docs/mm.md && echo "✅ 兩邊內容一致"
ls /tmp/machine_b/docs/ | grep conflict && echo "❌ 不該有 .conflict.md" || echo "✅ no conflict file"
```

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

## TC-trigger-C:vault 內推 markdown 帶維護訊號(default+escape 驗證)

### 目的

驗證新 default+escape 設計:使用者在 vault 內推 markdown、帶有「之後會繼續改」的維護訊號,agent 該載入 hbedit、走 `hb push`(tracked),**不**走 base CLI `heptabase note create`。

這是取代原本 TC-2 的 case — 加上維護訊號讓 trigger 路徑更穩,同時驗證 default 行為對齊新 SKILL.md。

### 環境 setup

```bash
rm -rf /tmp/hb-tcC
mkdir -p /tmp/hb-tcC/notes
cd /tmp/hb-tcC
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py init

cat > notes/rust-ownership.md <<'EOF'
# Rust Ownership 筆記

今天讀完 The Rust Programming Language 第 4 章。

## 三條規則

1. 每個值都有一個 owner
2. 同一時間只能有一個 owner
3. owner 離開 scope,值被 drop
EOF
```

### Session 啟動

```bash
cd /tmp/hb-tcC
claude --plugin-dir /Users/leiweicheng/Desktop/HeptaSync
```

### Prompt

```
我這個 vault 多了一個 notes/rust-ownership.md,推到 Heptabase,之後我會繼續從本地改
```

### 預期行為

- 載入 `hbedit:hbedit` skill(中強訊號:「vault」+「之後會繼續改」)
- 跑 `hb doctor`
- 跑 `hb push notes/rust-ownership.md`
- 回報 `action:"created"` + cardId
- `state.json["files"]["notes/rust-ownership.md"]` 有新 entry(**不**是 orphan)

### 驗證指令

```bash
cat /tmp/hb-tcC/.hbedit/state.json
python3 -c "
import json
d = json.load(open('/tmp/hb-tcC/.hbedit/state.json'))
assert 'notes/rust-ownership.md' in d['files'], 'state.json 沒有 entry — agent 走錯路'
print('✅ tracked entry 存在:', d['files']['notes/rust-ownership.md'])
"
ls /tmp/hb-tcC/.hbedit/  # 應該只有 state.json
VAULTID=$(python3 -c "import json; print(json.load(open('/tmp/hb-tcC/.hbedit/state.json'))['vaultId'])")
ls ~/.hbedit/cache/$VAULTID/  # local-state.json + sidecar/
```

### Reset

```bash
CARDID=$(python3 -c "import json; print(list(json.load(open('/tmp/hb-tcC/.hbedit/state.json'))['files'].values())[0]['cardId'])" 2>/dev/null)
VAULTID=$(python3 -c "import json; print(json.load(open('/tmp/hb-tcC/.hbedit/state.json'))['vaultId'])" 2>/dev/null)
[ -n "$CARDID" ] && heptabase card trash $CARDID
rm -rf /tmp/hb-tcC
[ -n "$VAULTID" ] && rm -rf ~/.hbedit/cache/$VAULTID
```

### Status

未跑

---

## TC-trigger-D:一次性建卡 + 明確 fire-and-forget(escape hatch / 負面觸發)

### 目的

驗證 escape hatch 啟動:使用者明確說「不用追蹤 / 隨手 / 丟上去就好」,agent **不**該載入 hbedit,直接走 base CLI `heptabase note create`。這是負面測試,確認 SKILL.md 的 escape hatch 條件真的擋得住。

### 環境 setup

```bash
# 故意在 vault 內測 — 確認 escape hatch 比 cwd 環境訊號更強
rm -rf /tmp/hb-tcD
mkdir /tmp/hb-tcD
cd /tmp/hb-tcD
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py init
```

### Session 啟動

```bash
cd /tmp/hb-tcD
claude --plugin-dir /Users/leiweicheng/Desktop/HeptaSync
```

### Prompt

```
幫我在 Heptabase 隨手建一張卡記今天的會議結論,不用追蹤、丟上去就好
```

### 預期行為

- **不**載入 `hbedit:hbedit` skill(escape hatch 明確訊號:「隨手」+「不用追蹤」+「丟上去就好」)
- 載入 `heptabase:heptabase-cli`
- 跑 `heptabase note create`(直接 base CLI)
- 回報新 cardId
- `state.json["files"]` 維持空,**不**新增 entry

### 驗證指令

```bash
cat /tmp/hb-tcD/.hbedit/state.json
python3 -c "
import json
d = json.load(open('/tmp/hb-tcD/.hbedit/state.json'))
assert d['files'] == {}, 'escape hatch 沒擋住 — state.json 多了 entry: %r' % d['files']
print('✅ state.json files 維持空 — escape hatch 啟動正確')
"
```

agent 輸出該含 `heptabase note create` 的 JSON,不含 `hb push`。

### Reset

```bash
# Agent 輸出的 cardId 手動 trash
# 範例:heptabase card trash <agent-輸出的-cardId>
VAULTID=$(python3 -c "import json; print(json.load(open('/tmp/hb-tcD/.hbedit/state.json'))['vaultId'])" 2>/dev/null)
rm -rf /tmp/hb-tcD
[ -n "$VAULTID" ] && rm -rf ~/.hbedit/cache/$VAULTID
```

### Status

未跑

---

## 全部跑完之後

把這份檔的 Test Matrix 跟每個 TC 的 Status 欄填好。如果有任何 fail / partial,寫一段 root cause + 修補 commit 在
最下面的「Bugs found」段(目前還沒,留空)。

## Bugs found

### Bug 1:SKILL.md 缺 vault-aware disambiguation,在 vault 內仍可能誤走 base CLI

- **發現於**:舊 TC-2(2026-05-24;已替換為 TC-trigger-C)
- **症狀**:cwd 在已 init 的 vault 內,使用者說「把 notes/xxx.md 存成 Heptabase 卡片」,agent 走 `heptabase note create`(base CLI)而不是 `hb push`(hbedit)。結果卡建出來但 orphan,不在 `state.json` 綁定裡 — 下次 pull / edit / sync 都接不上。
- **根因**:SKILL.md `When to use` 表把 hbedit 的觸發條件綁在「maintain long-term」的訊號上,但使用者自然語句通常不會明說維護意圖。當 cwd 已經是 vault,agent 該以環境訊號(vault 存在)而非語意訊號(「之後還會改」)作判斷,但 SKILL.md 目前沒寫這條規則,agent 也沒主動 `ls -la` 檢查。
- **影響**:任何使用者「新增筆記到 vault」的自然 prompt 都可能走錯路;orphan 卡片散落 Heptabase,使用者後續想透過 hbedit 維護時要手動 `hb pull <cardId> <path>` 重綁。
- **修補方向**:在 SKILL.md description / SOP B 加一條「cwd 含 `.hbedit/state.json` → 任何 markdown→card 操作預設走 hbedit;base CLI 只在沒 vault 或使用者明確要求一次性建立時用」。TC-trigger-C 加了明確維護訊號驗證修補後的新行為。
- **修補 commit**:`02cf678` docs(hbedit)!: rewrite SKILL.md as narrow trigger + default/escape — 新 SKILL.md「Default behavior」表第一列就是「In vault → `hb push`(tracked)」,搭配 escape hatch + `hb unlink` 救回機制。配套 commit:`9314be0` `hb unlink` + `6592509` argparse refactor 讓 `hb <cmd> --help` 全可用。
- **重測狀態**:待 TC-trigger-C 跑過確認新 SKILL.md 修補成功

## 設計筆記

### Prompt 設計原則(這次學到的)

- **別用技術術語**:不講 `hbedit`、`hb push`、`vault`、`state.json`。改用使用者語言:「同步」「推到 Heptabase」
  「綁好環境」。
- **別腳本化**:不寫「先(1)…再(2)…」這種步驟,讓 agent 自己決定流程。
- **別替 reviewer 做事**:不講「我要比較兩次差異」「把 vaultId 印給我」等元指示,測完反而從輸出讀。
- **環境訊號 vs 語意訊號**:同一句話在 vault 外 vs 在 vault 內跑出不同結果是 feature 不是 bug — 這正好測 agent 跟底層命令對環境的反應一致(已從 TC-4/TC-5 移除,改由 TC-trigger-C/D 以更清晰的方式驗證)。
- **負面測試很重要**:TC-trigger-D 測「escape hatch 明確訊號下不該觸發 hbedit」也是 skill 完整度的一部分,不只測「該觸發時有沒有觸發」。
