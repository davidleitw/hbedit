# hbedit Redesign — Test Phase Handoff

> **For a new Claude session picking up where we left off.**
> Read this top-to-bottom once, then jump straight to «Next action» at the bottom.

## TL;DR

- hbedit SKILL.md redesign **implementation is done** (7 commits, 63/63 unit tests pass).
- **Still 待跑**: 7 manual test cases (5 regression + 4 trigger TCs).
- The work lives on `master`, **not pushed yet** — we want trigger TCs green first.
- User runs each TC in a **fresh Claude session** (`claude --plugin-dir /Users/leiweicheng/Desktop/HeptaSync`) and pastes results back to you (the controlling session).
- Your job: set up env, give user the prompt to paste, evaluate the result, log status, reset, repeat.

## Status snapshot

| TC | 目的 | Status |
|---|---|---|
| TC-1 | 第一次設定 vault | ✅ pass |
| TC-3 | 拉既有卡片到本地 | ✅ pass |
| TC-7 | vault 外 push(v3 bug fix 回歸) | **NEXT** |
| TC-9 | 深層子目錄 push(vault discovery 回歸) | 未跑 |
| TC-10 | v2 schema reject(error path 回歸) | 未跑 |
| TC-trigger-A | 改既有卡中段(強訊號正面觸發) | 未跑 |
| TC-trigger-B | 多機 clone 後接續(強訊號正面觸發) | 未跑 |
| TC-trigger-C | vault 內推帶維護訊號(**default+escape 驗證,最關鍵**) | 未跑 |
| TC-trigger-D | 一次性建卡 + escape hatch(**負面觸發,最關鍵**) | 未跑 |

## Critical context you MUST respect

These were hard-won decisions across the previous session. Do **not** re-litigate without strong evidence.

1. **ASK pattern is forbidden.** When prompt is ambiguous, agent should default + announce, never «(a) or (b)?» prompts. Per Anthropic skill best practices («Avoid offering too many options»).
2. **`hb doctor` is preflight, not user-facing trigger.** If a user asks generic «Is Heptabase OK?», `heptabase --version` is the right answer, not `hb doctor`. Don't try to make hbedit trigger on health checks.
3. **TC-trigger-C is the load-bearing test.** It verifies the new SKILL.md's «in vault → `hb push`» default actually fires. If it fails (agent goes base CLI like old TC-2 did), the redesign hasn't solved the original problem — escalate, don't paper over.
4. **TC-trigger-D is equally load-bearing.** It verifies the escape hatch («一次性 / 不用追蹤 / 隨手 / 丟上去就好») actually overrides the in-vault default. If it fails (agent still goes hbedit), description is too aggressive.
5. **`hb unlink` is the recovery mechanism**, not a regular workflow command. If a TC creates an orphan card, use it for cleanup.
6. **Never push to `origin/master` automatically.** Master is 44 commits ahead. User decides when to push. Per session memory: user pushes manually.

## Reference documents (read on demand)

| Doc | When to read |
|---|---|
| `docs/superpowers/specs/2026-05-24-hbedit-skill-redesign-design.md` | When user questions a design decision |
| `docs/superpowers/plans/2026-05-24-hbedit-skill-redesign.md` | When user asks what was implemented |
| `docs/superpowers/testing/2026-05-24-hbedit-v3-manual-tests.md` | **For each TC's full setup / prompt / expected / verify / reset blocks** |
| `skills/hbedit/SKILL.md` | When debating skill trigger behavior |
| `skills/hbedit/references/{workflows,errors}.md` | When debugging error code SOPs or workflow expectations |
| Heptabase card `9a8d7b1d-0380-407a-a3f1-28da8bbadf77` | When user wants full session history / why-we-decided-X |
| `~/.claude/plugins/cache/claude-plugins-official/superpowers/5.1.0/skills/writing-skills/anthropic-best-practices.md` | When debating skill design principles |

## How the manual TC loop works

Per TC, the flow is **6 steps**, executed in **2 sessions** (you control session, user opens fresh session per TC):

1. **You (this session)** run the TC's «環境 setup» shell commands. Show user a brief confirmation of state.
2. **You** give user the «Session 啟動» command + the **prompt to paste**. Wait.
3. **User** opens a fresh terminal:
   - Runs `claude --plugin-dir /Users/leiweicheng/Desktop/HeptaSync` from the TC's cwd
   - Pastes the prompt
   - Waits for agent's response
   - Pastes the **full agent output** back to you
4. **You** evaluate against the TC's «預期行為» section. Run the «驗證指令» shell commands to check file state.
5. **You** update the TC's `### Status` field in `docs/superpowers/testing/2026-05-24-hbedit-v3-manual-tests.md` (use ✅ pass / ❌ fail / ⚠️ partial with notes).
6. **You** run the TC's «Reset» commands to clean up env (trash test cards, rm dirs, rm cache).

Then move to next TC.

## What «correctness» means per TC type

- **Regression TCs (TC-7, TC-9, TC-10)**: agent reaches for the right command, output matches expected JSON shape, file system state matches «驗證指令» expectations. These verify the v3 implementation still works after the SKILL.md rewrite.
- **Positive trigger TCs (TC-trigger-A, B, C)**: agent **loads the `hbedit:hbedit` skill** (visible in trace as `Skill(hbedit:hbedit)` invocation) and then performs the hbedit-side workflow correctly.
- **Negative trigger TC (TC-trigger-D)**: agent **does NOT load hbedit**, goes straight to base CLI `heptabase note create`, and `state.json["files"]` stays empty.

## When a TC reveals a real problem

If TC-trigger-C or TC-trigger-D fails (the load-bearing ones), this means the SKILL.md design didn't solve the problem. **Don't band-aid the test**. Instead:

1. Log status as `❌ fail` with the actual observation.
2. Discuss the failure with the user — they may want to:
   - Revisit SKILL.md description wording (less / more aggressive)
   - Change escape hatch keywords
   - Defer to Phase 4b (per-command rich `--help`)
   - Accept the gap and document it
3. Do not push to origin until decided.

Failure of regression TCs (TC-7/9/10) means an implementation bug — fix in code, re-test.

## Hard constraints on the controller agent (you)

- Don't auto-run `git push`. User pushes manually.
- Don't auto-trash Heptabase cards unless they're test artifacts from this session and the «Reset» block says to.
- Don't re-dispatch subagents for the test phase — testing is direct user collaboration, not subagent work.
- Don't modify SKILL.md / references/ during testing — those are under test. If they need changes, surface to user first.
- Don't skip the «驗證指令» step. Always verify the file system state matches expected, even if agent's output looks right.

## Next action: kick off TC-7

TC-7 verifies the v3 vault-discovery bug fix: agent in `/tmp/random-notes` (no vault, but `~/.hbedit/` exists) should get `not-in-vault` error, NOT `state-corrupt`.

**Step 1 — you run these setup commands in the controller session:**

```bash
ls ~/.hbedit/cache/ | head -3   # sanity check: dir exists from prior work
rm -rf /tmp/random-notes
mkdir /tmp/random-notes
echo "# 隨手記" > /tmp/random-notes/foo.md
ls -la /tmp/random-notes/
```

If `~/.hbedit/cache/` is empty, abort and run TC-1 first to populate it (TC-7's bug only triggers when `~/.hbedit/` actually exists in user's home).

**Step 2 — give user this verbatim:**

> 開新終端機:
> ```
> cd /tmp/random-notes
> claude --plugin-dir /Users/leiweicheng/Desktop/HeptaSync
> ```
>
> Session 開起來後,直接貼這句(不要加任何引導文字):
>
> ```
> foo.md 推到 Heptabase 變一張卡
> ```
>
> Agent 跑完之後,把完整輸出貼回給我。

**Step 3 — when user pastes the output, verify:**

- Agent ran `hb push foo.md` (or equivalent).
- Got JSON with `"status":"error"`, `"code":"not-in-vault"`.
- **Critical**: code is `not-in-vault`, NOT `state-corrupt`. If `state-corrupt`, the v3 fix has regressed — escalate immediately.
- Agent then per SKILL.md SOP for `not-in-vault` should ask user whether to run `hb init` here.

**Step 4 — update Status in test doc:**

Edit `docs/superpowers/testing/2026-05-24-hbedit-v3-manual-tests.md` Test Matrix:
- Change `TC-7` row Status from `未跑` to `✅ pass` (or `❌ fail (notes)`).
- Add a `### Status` block under the `## TC-7` section with timestamp + observations.

**Step 5 — reset:**

```bash
rm -rf /tmp/random-notes
# Don't touch ~/.hbedit/cache/ — TC-9 and beyond need it.
```

**Step 6 — proceed to TC-9** (read its setup block from the test doc).

## After all 9 TCs pass

If everything green:

1. Suggest user push to origin: `git push origin master` (44 commits including this redesign).
2. Suggest closing the «hbedit SKILL.md 重設計 — 思考卡» (cardId `9a8d7b1d-0380-407a-a3f1-28da8bbadf77`) with a final «結案」 append summarizing the actual test results.
3. Done.

If some red:

1. Don't push.
2. Discuss with user what to fix in SKILL.md / unlink semantics / etc.
3. Run a small follow-up plan, re-test affected TCs only.

## Done.
