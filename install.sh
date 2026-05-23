#!/bin/sh
# hbedit installer for Codex CLI and opencode.
# Usage:  curl -fsSL https://raw.githubusercontent.com/davidleitw/hbedit/main/install.sh | sh -s <tool>
#         where <tool> is one of:  codex  |  opencode
#
# Claude Code users do NOT need this script — install via /plugin marketplace
# add davidleitw/hbedit; see INSTALL.md.
#
# What this does (idempotent, safe to re-run):
#   1. Clones (or refreshes) the hbedit repo at ~/.local/share/hbedit
#   2. Copies skills/hbedit/ into the tool's skill directory
#   3. Symlinks ~/.local/bin/hb -> repo's bin/hb so the `hb` CLI is on PATH
#
# No pip deps. Pure POSIX sh. Requires: git, python3 (>=3.9), and the official
# heptabase CLI (0.3.x) installed separately via the Heptabase desktop app.

set -eu

TOOL="${1:-}"
REPO_URL="https://github.com/davidleitw/hbedit.git"
INSTALL_ROOT="${HBEDIT_INSTALL_ROOT:-$HOME/.local/share/hbedit}"
BIN_DIR="$HOME/.local/bin"

case "$TOOL" in
  -h|--help)
    sed -n '2,15p' "$0"; exit 0 ;;
  codex)    SKILL_DIR="$HOME/.agents/skills/hbedit" ;;
  opencode) SKILL_DIR="$HOME/.config/opencode/skills/hbedit" ;;
  "")       echo "error: missing <tool>. usage: sh install.sh codex|opencode" >&2; exit 2 ;;
  *)        echo "error: unknown tool '$TOOL'. expected: codex | opencode" >&2; exit 2 ;;
esac

# prerequisite check (clearer failure than git/python's own errors)
for cmd in git python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "error: required command not found: $cmd" >&2
    echo "       install it and re-run." >&2
    exit 1
  fi
done

say() { printf '  %s\n' "$*"; }

echo "hbedit installer (tool: $TOOL)"

# 1. clone or refresh the repo
#    Note: refresh discards local edits inside $INSTALL_ROOT. That directory is
#    machine-managed — don't put anything you want to keep in there.
if [ -d "$INSTALL_ROOT/.git" ]; then
  say "refresh: $INSTALL_ROOT"
  git -C "$INSTALL_ROOT" fetch --quiet origin
  # Resolve the remote's default branch instead of trusting origin/HEAD,
  # which may be stale if the upstream renamed its default branch.
  DEFAULT_REF=$(git -C "$INSTALL_ROOT" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null || true)
  if [ -z "$DEFAULT_REF" ]; then
    git -C "$INSTALL_ROOT" remote set-head --auto origin >/dev/null 2>&1 || true
    DEFAULT_REF=$(git -C "$INSTALL_ROOT" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null || echo "origin/main")
  fi
  git -C "$INSTALL_ROOT" reset --quiet --hard "$DEFAULT_REF"
else
  say "clone:   $REPO_URL -> $INSTALL_ROOT"
  mkdir -p "$(dirname "$INSTALL_ROOT")"
  git clone --quiet "$REPO_URL" "$INSTALL_ROOT"
fi

# 2. copy skill bundle into tool's skill dir
say "copy:    skills/hbedit -> $SKILL_DIR"
mkdir -p "$(dirname "$SKILL_DIR")"
rm -rf "$SKILL_DIR"
cp -R "$INSTALL_ROOT/skills/hbedit" "$SKILL_DIR"

# 3. symlink hb onto PATH
say "symlink: $BIN_DIR/hb -> $INSTALL_ROOT/bin/hb"
mkdir -p "$BIN_DIR"
ln -snf "$INSTALL_ROOT/bin/hb" "$BIN_DIR/hb"
chmod +x "$INSTALL_ROOT/bin/hb"

# 4. PATH sanity check
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo
     echo "  ! warning: $BIN_DIR is not in your PATH."
     echo "    add this to your shell rc:  export PATH=\"\$HOME/.local/bin:\$PATH\""
     ;;
esac

echo
echo "done. verify with:  hb doctor"
