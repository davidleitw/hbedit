# 安裝 hbedit

> UNOFFICIAL — 非官方工具,不隸屬 Heptabase。

## 先決

- Python 3.9+(`hb` 是 stdlib-only,無需 pip)。
- 官方 `heptabase` CLI,版本 `0.3.x`。
- Heptabase 桌面 app(`hb` 透過它運作)。

## 安裝

hbedit 的 skill 目錄就是 repo 裡的 `v1/skill/` —— 沒有 build 步驟,直接複製即可。安裝 = 把 `v1/skill/` 複製進工具的 skill 路徑,並把 `hb` 指令放上 PATH。

### Claude Code
    cp -r v1/skill ~/.claude/skills/hbedit
    ln -s ~/.claude/skills/hbedit/scripts/hb ~/.local/bin/hb

### Codex CLI
    cp -r v1/skill ~/.agents/skills/hbedit
    ln -s ~/.agents/skills/hbedit/scripts/hb ~/.local/bin/hb

### opencode
    cp -r v1/skill ~/.config/opencode/skills/hbedit
    ln -s ~/.config/opencode/skills/hbedit/scripts/hb ~/.local/bin/hb

(`~/.local/bin` 需在 PATH 上;也可改 symlink 到任何已在 PATH 的目錄。)

## 驗證

裝完,在任一工具的終端跑:

    hb doctor

回 `{"command": "doctor", "status": "ok", ...}` 即安裝成功。若回其他 status,照其 `detail` 修正(裝 CLI / 更新到 0.3.x / 開桌面 app)。

## 備註

- 三個工具都原生讀 Anthropic Agent Skill 格式(`SKILL.md`),所以同一個 `v1/skill/` 目錄三邊通用,毋須各自的 plugin 打包。
- Claude Code 的 plugin / marketplace 一鍵安裝是日後的便利選項;v1 以上面的手動複製為準。
