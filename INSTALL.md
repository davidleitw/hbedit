# 安裝 hbedit

> UNOFFICIAL — 非官方工具，不隸屬 Heptabase。

## 先決條件

- Python 3.9+（`hb` 是 stdlib-only，不需 pip）
- Heptabase 桌面 app **v1.91.0 或更新**（CLI 隨它一起裝、`hb` 也透過它運作）
- 官方 `heptabase` CLI 已啟用，版本 `0.3.x`

### 啟用 heptabase CLI

CLI **不是** 從 npm/brew 裝的，要在桌面 app 內啟用：

1. 打開 Heptabase 桌面 app → **Settings → AI Features → CLI**
2. 把 CLI 切換成啟用
3. **macOS**：`heptabase` 自動上 PATH，開個新 shell 就能用
4. **Windows**：app 會印一行 PATH 設定指令，照著跑、再開新 shell

詳細步驟參考官方說明：<https://support.heptabase.com/en/articles/14715462-how-to-use-heptabase-cli>

確認 CLI 通了：

```sh
heptabase --version
```

回 `0.3.x` 才繼續下面的 hbedit 安裝步驟。

---

## Claude Code（兩行）

在 Claude Code 裡輸入：

```
/plugin marketplace add davidleitw/hbedit
/plugin install hbedit@hbedit
```

裝完 `hb` 會自動上 PATH（Claude Code 的 plugin `bin/` 慣例）。重啟一個新 shell，或在當前 Claude session 跑 `/reload-plugins`，然後 `hb doctor` 應該回 `ok`。

## Codex CLI（一行）

```sh
curl -fsSL https://raw.githubusercontent.com/davidleitw/hbedit/main/install.sh | sh -s codex
```

會把 skill 裝到 `~/.agents/skills/hbedit/`，把 `hb` symlink 到 `~/.local/bin/hb`。確認 `~/.local/bin` 在你的 PATH 上。

## opencode（一行）

```sh
curl -fsSL https://raw.githubusercontent.com/davidleitw/hbedit/main/install.sh | sh -s opencode
```

skill 落在 `~/.config/opencode/skills/hbedit/`，其餘同上。

---

## 驗證

任一工具裝完，開一個新 shell：

```sh
hb doctor
```

回 `{"command": "doctor", "status": "ok", ...}` 即安裝成功。其他 status 照其 `detail` 修正（多半是裝 `heptabase` CLI、更新到 0.3.x、或開桌面 app）。

---

## 手動安裝（一鍵失敗時）

skill 沒有 build 步驟，直接複製檔案即可。

```sh
git clone https://github.com/davidleitw/hbedit.git ~/.local/share/hbedit

# Claude Code（不走 plugin 走 skill 路徑）:
ln -snf ~/.local/share/hbedit/skills/hbedit ~/.claude/skills/hbedit

# Codex CLI:
ln -snf ~/.local/share/hbedit/skills/hbedit ~/.agents/skills/hbedit

# opencode:
ln -snf ~/.local/share/hbedit/skills/hbedit ~/.config/opencode/skills/hbedit

# hb 上 PATH:
ln -snf ~/.local/share/hbedit/bin/hb ~/.local/bin/hb
```

---

## 不放心 `curl | sh`？

下載先檢查再執行：

```sh
curl -fsSL https://raw.githubusercontent.com/davidleitw/hbedit/main/install.sh -o /tmp/hbedit-install.sh
less /tmp/hbedit-install.sh
sh /tmp/hbedit-install.sh codex   # 或 opencode
```

整支 POSIX sh，純 stdlib Python；沒有 pip 依賴、沒有任何網路活動超出 `git clone` 範圍。
