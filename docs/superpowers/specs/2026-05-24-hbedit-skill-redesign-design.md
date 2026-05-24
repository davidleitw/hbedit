# hbedit SKILL.md Redesign — Design Spec

> **Status**: design phase, awaiting implementation plan
> **Date**: 2026-05-24
> **Supersedes**: portions of `2026-05-24-hbedit-redesign-design.md` that describe v2 SKILL.md structure (workflow SOPs, error code catalog placement). The v3 global-cache work in `2026-05-24-hbedit-global-cache-design.md` is unaffected.

## Background

hbedit v3 (global cache) is implemented (commits `b71eacb`…`9230e69`) and unit tests are green. During end-to-end manual testing (`docs/superpowers/testing/2026-05-24-hbedit-v3-manual-tests.md`), two of the four trigger-style test cases revealed that the current SKILL.md description and SOPs don't handle realistic ambiguous user prompts well:

- **TC-2** (in-vault, user said «把筆記存成卡片»): agent routed to base CLI `heptabase note create`. Card was created but orphaned (no `state.json` binding).
- **TC-4** (in-vault, user said «Heptabase 接得 OK 嗎»): agent used `heptabase --version` + journal read, never invoked `hb doctor`.

Investigation pulled three threads:

1. SKILL.md description trigger language is too narrow — focuses on maintenance/edit signals, doesn't catch ambiguous «push markdown» prompts.
2. SOPs encode routing decisions as branches (when to use hbedit vs. base CLI), which the Anthropic skill best-practices guide flags as an anti-pattern («Avoid offering too many options. Provide a default with escape hatch»).
3. SKILL.md is 323 lines — under Anthropic's 500-line cap, but routing/error-code/SOP detail drowns the core principles. Compression via progressive disclosure (references/ + sub-command `--help`) is appropriate.

## Problem statement

After loading the hbedit skill via `--plugin-dir`, a Claude Code agent should:

- Reach for `hb push` when the user wants to push markdown to Heptabase **in an hbedit vault**, even when the prompt lacks explicit «maintain» signals.
- Reach for `heptabase note create` (base CLI) when the user explicitly asks for one-shot card creation («隨手記一下», «不用追蹤», «丟上去就好»).
- Reach for `hb push`/`hb pull` flows on existing tracked content (mid-card edit, multi-machine continue) given clear signals (cardId mention, «剛 clone 進來», «接著編輯»).
- **Not** invoke `hb doctor` for generic «Is my Heptabase setup OK» queries — that's base CLI's territory. `hb doctor` runs only as preflight before another hb command.

The redesign solves these without using an ASK-the-user pattern (which Anthropic explicitly flags as anti-pattern: «too many choices»).

## Design principles (sourced from Anthropic skill best practices)

These are the principles the redesign must respect. All four come directly from `~/.claude/plugins/cache/claude-plugins-official/superpowers/5.1.0/skills/writing-skills/anthropic-best-practices.md`:

1. **Claude is already smart** — only put domain facts (capabilities, file layouts, command shapes) in SKILL.md, not reasoning the LLM can do itself.
2. **Context-dependent decisions use HIGH freedom** — describe principles, not switch statements. hbedit's «which tool to use» decision is many-paths-lead-to-success territory.
3. **Default + escape hatch, never ASK** — provide a sensible default and a clearly-described condition to override it. ASK pattern is anti-pattern.
4. **Progressive disclosure** — SKILL.md is the overview, `references/*.md` is on-demand detail, sub-command `--help` is per-command lazy detail. Reference files one level deep from SKILL.md only.

## Architecture

### Three-tier information layout

```
skills/hbedit/
├── SKILL.md                    # ≤ 100 lines, target ~70
│                               # principles + defaults + command list
├── references/
│   ├── workflows.md            # SOPs A-F + conflict resolution (with TOC)
│   └── errors.md               # 16 error code SOPs (no TOC, < 100 lines)
└── scripts/
    ├── hbedit.py               # argparse-refactored, every sub-command --help works
    ├── vault.py                # unchanged
    ├── local_state.py          # unchanged
    ├── htb.py                  # unchanged
    ├── pm2md.py                # unchanged
    ├── tagsync.py              # unchanged
    └── transplant.py           # unchanged
```

Information flows top-down:

- **SKILL.md** (always read once skill is loaded): description for triggering, defaults for routing, command list, critical limitations.
- **references/workflows.md** (read when agent is mid-workflow): step-by-step for edit / multi-machine continue / split / merge / batch / conflict resolution.
- **references/errors.md** (read when an error is encountered): per-code SOPs.
- **`hb <cmd> --help`** (executed when agent needs specific flag/output detail): output JSON shape, command-specific error codes, flag descriptions.

### New SKILL.md (skeleton — full text in implementation phase)

```yaml
---
name: hbedit
description: Edit Heptabase cards through local markdown files with `state.json`
  binding. Only path for: editing the middle of an existing card (block-ID
  transplant), pushing a local md as a tracked card, maintaining a card↔file
  binding across machines via git, or precise tag changes on existing cards.
  Use when the user wants to edit existing card content, continue editing after
  git clone, push a local markdown file to Heptabase, change tags on an
  existing card, or remove a card's local binding. Base `heptabase` CLI handles
  one-shot creates, appends, reads, searches — hbedit owns ongoing maintenance.
allowed-tools: Bash(hb *) Bash(heptabase *)
---

## What hbedit uniquely does

- Edit the middle of an existing card via block-ID transplant (base CLI cannot).
- Maintain a card↔file binding committed in `.hbedit/state.json` so the same
  card can be edited from multiple machines via git.
- Push a local markdown file as a tracked card with bidirectional sync.
- Add/remove tags on an existing card without disturbing other tags.

## Default behavior

| Situation | Default action | Escape hatch |
|---|---|---|
| User mentions markdown → Heptabase, **in a vault** | `hb push <path>` (tracked) | Explicit «一次性» / «不用追蹤» / «隨手» / «丟上去就好» → `heptabase note create` |
| User points at existing tracked file (cardId or path) | hbedit (`hb pull` if stale, edit, `hb push`) | None — hbedit is the only correct tool |
| User says «剛 clone 進來» / «另一台機器» | `hb pull <path>` smart-sync first | None |
| User wants pure read / search / list | base CLI | None — hbedit adds no value |
| User asks generic «Heptabase 設置 OK 嗎» | base CLI's `heptabase --version` | User specifically asks about vault/sync state → `hb doctor` |
| Not in a vault, user wants to push | base CLI's `heptabase note create` | User explicitly wants to start syncing → `hb init` first |

Mistake recovery: when default routes a file into tracking that the user
actually wanted fire-and-forget, run `hb unlink <path>` (removes binding,
leaves files alone).

## Preflight

`hb doctor` runs once before any other hb command. On error, consult
`references/errors.md`.

## Vault model

`.hbedit/state.json` (committed, git-tracked) binds `path → {cardId, tags}`
and stores `vaultId` (UUIDv4). Per-machine cache at
`~/.hbedit/cache/<vaultId>/` (local-state.json + sidecar/<cardId>.json). A
directory is an hbedit vault if it or any ancestor contains
`.hbedit/state.json` (the file, not just the directory).

## Commands

Run `hb <cmd> --help` for flags, JSON output shape, and error codes.

- `hb doctor` — preflight + cache state report
- `hb init` — initialize a vault in cwd
- `hb push <path>` — create new card or update existing (block-ID transplant)
- `hb pull <cardId> <path>` — first-time bind by cardId
- `hb pull <path>` — smart-sync tracked path (baseline / noop / updated / conflict)
- `hb tag add <path> <name>` / `hb tag remove <path> <name>` — round-trip safe
- `hb unlink <path>` — remove binding without deleting local md or remote card

## Limitations

- Card-to-card references can't be authored from markdown.
- ~100,000 char ProseMirror push cap; very large cards may fail.
- Note cards only — no journal/PDF/whiteboard.
- No `hb mv`: renaming a tracked .md needs manual `state.json` edit.

## Safety

Never read or write Heptabase's database, storage, cache, or internal
endpoints directly. Use only the `hb` and `heptabase` CLIs.

## Look up

- Workflow SOPs (edit / multi-machine / split / merge / batch / conflict):
  `references/workflows.md`
- Error code handling: `references/errors.md`
- Command-specific detail: `hb <cmd> --help`
```

Estimated final line count: 65-75 lines.

### `hb unlink <path>` command (new)

**Goal**: provide cheap recovery when `hb push` was mis-routed to a file the user wanted untracked.

**Behavior**:

1. Resolve `path` relative to vault root (standard vault discovery via `vault.find()`).
2. Look up `state.json["files"][path]`:
   - If absent → emit error `path-not-tracked`.
   - If present → capture `cardId`.
3. Atomic update:
   - Remove `state.json["files"][path]`.
   - Remove `~/.hbedit/cache/<vaultId>/local-state.json` entry for path (if present).
   - Delete `~/.hbedit/cache/<vaultId>/sidecar/<cardId>.json` (if present).
4. Local `.md` at `path` is **untouched** — user owns it.
5. Remote Heptabase card is **untouched** — user trashes separately if desired.

**Output shape**:

```json
{"command":"unlink","status":"ok","action":"unlinked","path":"notes/foo.md","cardId":"abc-123"}
```

**Error codes**:

- `path-not-tracked` — path absent from state.json (also returned on second invocation; idempotent-friendly signal).
- `not-in-vault` — standard when no `.hbedit/state.json` ancestor found.
- `state-corrupt` / `state-schema-unsupported` — same as other commands.

**Implementation footprint**:

- `skills/hbedit/scripts/hbedit.py`: ~30 LoC new function `_unlink()` + dispatch entry.
- `tests/test_hbedit.py` (new or extend): 3 unit tests covering tracked, untracked, and cache cleanup.

### Sub-command `--help` (phases 4a + 4b)

Current state: `hb push --help` errors because `--help` is treated as a path argument. Sub-command parsing is manual, not argparse-based.

**Phase 4a** (required for SKILL.md compression):

Refactor `hbedit.py` dispatch to use argparse sub-parsers. Each sub-command gets at minimum:

- One-line description matching the SKILL.md command list.
- Standard `--help` output (auto-generated by argparse).

This makes `hb <cmd> --help` work for all commands without error.

**Phase 4b** (incremental quality improvement, deferred):

Each sub-command's `--help` gets rich text including:

- Full JSON output shape with example.
- Command-specific error codes (subset of references/errors.md).
- Common usage patterns / recipes.

Phase 4b allows `references/errors.md` to be slimmed further (per-command error guidance migrates into help text). Not blocking for this redesign — `references/errors.md` can carry the full catalog initially.

### references/workflows.md (new)

Source content: current SKILL.md SOPs A-F + Conflict resolution section.

Structure:

```markdown
# hbedit Workflow SOPs

## Contents

- SOP A — Edit an existing card
- SOP B — Push a local doc as a new tracked card
- SOP C — Continue editing on another machine after git clone
- SOP D — Read-only access to a card
- SOP E — Edit tags on an existing card
- SOP F — Multi-step composites (split / merge / batch push)
- Conflict resolution (referenced by SOPs A and C)
```

Total estimated ~150 lines (per Anthropic, > 100 lines → TOC required, already included above).

### references/errors.md (new)

Source content: current SKILL.md `## Error Code SOPs` table (16 codes).

Structure: per-code subsection. No TOC needed (< 100 lines).

```markdown
# hbedit Error Code SOPs

For each code: what happened, agent steps to take.

## cli-missing
...

## cli-version-unsupported
...
```

(16 sections total.)

## Acceptance criteria

The redesign is complete when:

1. **`skills/hbedit/SKILL.md`** is ≤ 100 lines (target ~70), uses default + escape hatch routing (no ASK pattern, no full SOP body).
2. **`skills/hbedit/references/workflows.md`** exists with TOC, contains SOPs A-F and Conflict resolution.
3. **`skills/hbedit/references/errors.md`** exists, contains all 16 error code SOPs.
4. **`hb unlink <path>`** implemented; 3 new unit tests pass (`tests/test_hbedit.py` or extend existing).
5. **`hb <cmd> --help`** works without error for: `doctor`, `init`, `push`, `pull`, `tag add`, `tag remove`, `unlink` (Phase 4a complete).
6. **Manual test matrix** (`docs/superpowers/testing/2026-05-24-hbedit-v3-manual-tests.md`):
   - Retained as regression: TC-1 (init), TC-3 (pull), TC-7 (vault-outside push, v3 bug fix), TC-9 (deep subdir), TC-10 (v2 schema reject) — all already ✅ or to-be-run.
   - New trigger TCs (4):
     - **TC-trigger-A** — Mid-card edit on existing tracked file. Strong positive trigger.
     - **TC-trigger-B** — Multi-machine continue after simulated clone. Strong positive trigger.
     - **TC-trigger-C** — In-vault push markdown with maintain signal. Confirms new default + escape design.
     - **TC-trigger-D** — Explicit fire-and-forget create. Negative trigger; agent should use base CLI only.
   - Removed: TC-4, TC-5 (doctor trigger tests — wrong test design, behavior now covered by direct shell verification in spec).
   - Replaced: TC-2 → TC-trigger-C, TC-6 → TC-trigger-A, TC-8 → TC-trigger-B, TC-11 → TC-trigger-D.
7. **All existing unit / integration tests** continue to pass after Phase 4a argparse refactor.

## Resolved design decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | Description includes «push a local markdown file to Heptabase» without «ongoing-tracked» qualifier (trigger-permissive) | Prevents hbedit from being missed when in-vault user prompt lacks maintenance signal; body's default-in-vault routes correctly once loaded. |
| 2 | Ambiguity handled by default + escape hatch, not ASK | Anthropic best practice; cross-session consistent. |
| 3 | Residual ambiguity (in-vault create without explicit escape) accepted; `hb unlink` provides cheap recovery | Lower friction than ASK every time; matches best practice. |
| 4 | `hb unlink` removes state + cache + sidecar; never touches local md or remote card | Reversibility without destruction. |
| 5 | Sub-command `--help` split into Phase 4a (argparse + basic help) and Phase 4b (rich text per command) | 4a unblocks SKILL.md compression; 4b is incremental. |
| 6 | Trigger test suite is 4 TCs (positive A/B/C, negative D); no separate unlink trigger TC | unit tests cover unlink correctness; description matches «unlink» / «移除追蹤» natural phrasings. |

## Out of scope

- `hb mv` (rename tracked file) — current spec leaves manual state.json edit as the workflow.
- `hb status` (show vault tracking state) — possibly Phase 5 follow-up.
- `hb push --dry-run` — possibly Phase 5 follow-up.
- v2 → v3 schema migration tool — v3 keeps refusing v2; user re-inits.

## Deployment notes

- `--plugin-dir` users (local dev): next session picks up the new SKILL.md, references/, and `hb` binary changes automatically. No action required.
- `/plugin install hbedit@hbedit` users: must run `/plugin update hbedit` after the redesign ships to a new tag. Mention in release notes.
- No data migration: `state.json` schema is unchanged (still v3). User vaults from before this redesign continue to work; only agent behavior changes (more aggressive default-to-hbedit in vault).

## Open follow-ups (not blocking this redesign)

- **Phase 4b**: complete rich `--help` per sub-command (output JSON shapes, examples). Allows further slimming of `references/errors.md`.
- **`hb status`** command: list tracked files in current vault, with sync state per file.
- **`hb push --dry-run`** flag: preview block transplant counters without remote write.
- **Batch `hb push *.md`**: native multi-file support (currently must loop in shell).

---

## Spec self-review (inline checks)

Per brainstorming skill protocol, reviewed for: placeholders, internal consistency, scope, ambiguity.

- **Placeholders**: none. No TBD/TODO/«fill later». All sections concrete.
- **Internal consistency**: SKILL.md skeleton uses default + escape table matching Section «Problem statement» expectations. Test matrix matches acceptance criteria. references/ structure matches information layout diagram.
- **Scope**: focused on SKILL.md restructure + 1 new command (`hb unlink`) + 1 CLI refactor (`--help`). Does not bundle unrelated features. Out-of-scope items are explicitly listed.
- **Ambiguity**: «trigger-permissive description» (decision 1) could be interpreted as «broad trigger» — clarified by inline language («without ongoing-tracked qualifier», not «broad»). `hb unlink` semantics explicit about what is and isn't removed (file, remote card both untouched).

No fixes needed. Spec ready for user review.
