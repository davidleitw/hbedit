# hbedit SKILL.md Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 323-line SOP-heavy SKILL.md with a ~70-line narrow-but-trigger-permissive version following Anthropic skill best practices (default + escape hatch, no ASK pattern, progressive disclosure via `references/*.md` + sub-command `--help`). Add `hb unlink <path>` for cheap recovery and refactor `hbedit.py` to argparse so every sub-command's `--help` works.

**Architecture:** Three-tier information layout — SKILL.md (overview + defaults), `references/{workflows,errors}.md` (lazy-load detail), `hb <cmd> --help` (per-command lazy detail). One new command (`hb unlink`). One CLI refactor (manual dispatch → argparse). One test doc rewrite (4 trigger TCs replace 4 old TCs, 2 doctor TCs removed, 5 regression TCs retained).

**Tech Stack:** Python 3 stdlib only (`argparse`, `json`, `os`). No new dependencies. Existing pytest harness.

**Spec:** `docs/superpowers/specs/2026-05-24-hbedit-skill-redesign-design.md`

**Branch:** continue on current branch (`master`)

---

## File map

| File | Action |
|---|---|
| `skills/hbedit/references/errors.md` | Create (~80 LoC, extracted from current SKILL.md) |
| `skills/hbedit/references/workflows.md` | Create (~150 LoC, extracted from current SKILL.md) |
| `skills/hbedit/scripts/hbedit.py` | Modify (~50 LoC change: new `unlink` function + argparse `main`) |
| `tests/test_unlink.py` | Create (~80 LoC, 5 unit tests) |
| `tests/test_cli_help.py` | Create (~60 LoC, 7 sub-command `--help` smoke tests) |
| `skills/hbedit/SKILL.md` | Rewrite from 323 lines to ~70 lines |
| `docs/superpowers/testing/2026-05-24-hbedit-v3-manual-tests.md` | Update (add TC-trigger-A/B/C/D, remove TC-2/4/5/6/8/11, keep TC-1/3/7/9/10) |

Files unchanged: `vault.py`, `local_state.py`, `htb.py`, `pm2md.py`, `tagsync.py`, `transplant.py`, `errors.py`, `bin/hb`.

---

## Task 1: Extract error code SOPs to `references/errors.md`

**Goal:** Pull the 16-row `## Error Code SOPs` table out of `SKILL.md` into a dedicated reference file. Pure file extraction — no behavior change. Original SKILL.md unchanged in this task (Task 5 rewrites it wholesale).

**Files:**
- Create: `skills/hbedit/references/errors.md`

- [ ] **Step 1: Create the references directory**

```bash
mkdir -p /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/references
```

- [ ] **Step 2: Write `references/errors.md`**

Source: rows of the `## Error Code SOPs` table in current `skills/hbedit/SKILL.md` (lines 289–309). Convert each row to a per-code subsection. The file should look like:

```markdown
# hbedit Error Code SOPs

Per-code agent guidance for `hb` command failures. Each entry: what
happened + numbered steps to take. Returned in the JSON output's `code`
field on a non-`ok` status.

## cli-missing

What happened: `heptabase` binary not on PATH.

Agent steps:
1. Inform user the Heptabase CLI is not installed.
2. Direct them to install it (heptabase.com or `npm i -g @heptabase/cli`).
3. Pause; do not continue until `hb doctor` returns ok.

## cli-version-unsupported

What happened: CLI version outside `0.3.x`.

Agent steps:
1. Tell user the installed CLI version is unsupported.
2. Ask them to update (`npm update -g @heptabase/cli` or reinstall).
3. Pause.

## app-not-running

What happened: Desktop app closed.

Agent steps:
1. Tell user the Heptabase desktop app is not running.
2. Ask them to launch it (or run `heptabase start`).
3. Pause.

## not-in-vault

What happened: No `.hbedit/state.json` ancestor found for the given path.

Agent steps:
1. Tell user there is no hbedit vault for this path.
2. Ask: "Want me to run `hb init` here?"
3. If yes, run `hb init` and retry the original command.

## file-not-found

What happened: `path` does not exist on disk.

Agent steps:
1. Inform user the path was not found.
2. Ask them to confirm the path or correct any typo.
3. Retry with the confirmed path.

## path-exists-untracked

What happened: First-time pull would overwrite an untracked file already at `path`.

Agent steps:
1. Tell user the path is already occupied by an untracked file.
2. Ask: choose an alternative path, or confirm removal of the existing file.
3. Proceed based on user choice.

## path-not-tracked

What happened: `state.json` has no entry for `path`.

Agent steps:
1. Tell user this file is not tracked.
2. Ask: "Create a new card for it?" (use `hb push`) or "Link it to an existing card?" (get cardId, use `hb pull <cardId> <path>`).

## no-baseline

What happened: Tracked path has no local sync state (fresh clone or partial cache deletion).

Agent steps:
1. Tell user the local cache for this card is missing.
2. Run `hb pull <path>` — smart pull will safely establish baseline or surface a conflict.
3. Follow the outcome (see `workflows.md` SOP C step 2).

## content-conflict

What happened: Remote changed since last pull.

Agent steps:
1. Tell user the remote was edited concurrently.
2. Follow the Conflict resolution SOP in `workflows.md`.

## tag-ambiguity

What happened: New tag name looks like a typo of an existing tag.

Agent steps:
1. Show the user the warning (which tag it resembles).
2. Ask: typo or intentional new tag?
3. If intentional, rerun `hb tag add` with the confirmed name.

## card-not-found

What happened: cardId in state.json doesn't exist on Heptabase (possibly trashed).

Agent steps:
1. Tell user the card may have been trashed remotely.
2. Ask whether to remove the `state.json` entry (with `hb unlink <path>`) and treat the file as untracked.
3. If yes, run `hb unlink <path>` and proceed.

## tag-not-on-card

What happened: `hb tag remove` for a tag the card doesn't have.

Agent steps:
1. Inform user the tag was not present on the card.
2. No further action needed.

## cardId-already-tracked

What happened: First-time pull for a cardId already mapped to a different path.

Agent steps:
1. Tell user the card is already linked to `<other-path>`.
2. Ask: edit there instead, or unlink first (`hb unlink <other-path>`)?

## state-schema-unsupported

What happened: `state.json` has `schemaVersion` other than 3.

Agent steps:
1. Inform user the state file is from an incompatible older version.
2. Advise running `hb init` in a fresh directory, or removing `.hbedit/` and starting over. v3 does not migrate v2 state files automatically.
3. Do not run any other hb command until resolved.

## state-corrupt

What happened: `state.json` is invalid JSON or violates schema invariants.

Agent steps:
1. Stop immediately. Do not run any other hb command.
2. Show user the corrupt content.
3. Ask them to fix it by hand or restore from git history.

## vault-nested

What happened: `hb init` called inside an existing vault's tree.

Agent steps:
1. Tell user there is already a vault at `<ancestor-path>`.
2. Ask: use that one, or remove the ancestor's `.hbedit/` if a separate vault is intentional?

## local-has-changes

What happened: `hb pull` would overwrite a file with uncommitted local edits.

Agent steps:
1. Tell user the local file diverges from the last sync.
2. Ask: push these changes first (`hb push <path>`), or discard them?
3. Proceed based on user choice; if discarding, revert the file manually before retrying pull.
```

- [ ] **Step 3: Sanity check file**

```bash
wc -l /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/references/errors.md
```

Expected: ~85-100 lines.

- [ ] **Step 4: Commit**

```bash
git add skills/hbedit/references/errors.md
git commit -m "docs(hbedit): extract error code SOPs to references/errors.md

Pure file extraction prep for SKILL.md compression. Each of the 16
error codes gets a per-code subsection so the main SKILL.md can shed
the inline error table and just point here. Behavior unchanged."
```

---

## Task 2: Extract workflow SOPs to `references/workflows.md`

**Goal:** Pull the 6 workflow SOPs (A-F) + the Conflict resolution SOP out of `SKILL.md` into a single reference file with a Table of Contents (per Anthropic rule: any reference > 100 lines needs TOC). Pure file extraction.

**Files:**
- Create: `skills/hbedit/references/workflows.md`

- [ ] **Step 1: Write `references/workflows.md`**

Source: `## Workflow SOPs` section of current `skills/hbedit/SKILL.md` (lines 179–287). Add a TOC at the top. Final file:

```markdown
# hbedit Workflow SOPs

Step-by-step recipes for hbedit operations. Each SOP covers a complete
end-to-end scenario including preflight, user confirmation, and commit.

## Contents

- SOP A — Edit an existing card
- SOP B — Push a local doc as a new tracked card
- SOP C — Continue editing on another machine after git clone
- SOP D — Read-only access to a card
- SOP E — Edit tags on an existing card
- SOP F — Multi-step composites (split / merge / batch push)
- Conflict resolution (referenced by SOPs A and C)

---

## SOP A — Edit an existing card

1. `hb doctor` — on error, follow the matching code in `errors.md`.
2. Check `state.json` for the card's path. If not tracked, run
   `hb pull <cardId> <path>` (find cardId via
   `heptabase card list -q "<title>"`).
3. Read the `.md` file. Plan the change — identify what is preserved vs.
   inserted/edited/deleted. Show the plan to the user and confirm before
   writing, especially for destructive edits.
4. Edit the `.md` file.
5. `hb push <path>`:
   - `action: "updated"` → success; report block counters.
   - `code: "content-conflict"` → follow Conflict resolution below.
   - `code: "no-baseline"` → follow `no-baseline` in `errors.md`, retry.
6. Commit `state.json` + the `.md`.

---

## SOP B — Push a local doc as a new tracked card

1. `hb doctor`.
2. Confirm a vault exists (`.hbedit/state.json` in the tree). If absent,
   run `hb init` in the project root.
3. Read the `.md` and confirm intent with the user if there is any ambiguity.
4. `hb push <path>` — on `action: "created"`, report the new `cardId`.
5. Commit the `.md` and `state.json` together so other machines inherit
   the binding.

If the user later realizes they wanted a fire-and-forget card (no
tracking), `hb unlink <path>` removes the binding cleanly (local md and
remote card untouched).

---

## SOP C — Continue editing on a second machine after git clone

After `git clone`, the per-machine cache (`~/.hbedit/cache/<vault-id>/`)
is absent on the new machine — only `.hbedit/state.json` is committed.
The first operation on each tracked file must be `hb pull <path>`.

1. `hb doctor`.
2. `hb pull <path>` (one-argument form). Inspect the outcome:
   - `action: "baseline-established"` — file matches remote; continue to step 3.
   - `action: "conflict"` — local file diverged from remote; a `.conflict.md`
     backup was created, working file now holds remote. Reconcile via the
     Conflict resolution SOP before continuing.
   - `code: "local-has-changes"` — file was edited before pull; run
     `hb push <path>` first, then retry the pull.
3. Plan changes, confirm destructive edits with the user.
4. Edit `.md` and `hb push <path>`.
5. Commit `state.json` + `.md`.

---

## SOP D — Read-only access to a card

1. `hb doctor`.
2. If already tracked, read the `.md` directly.
3. If not tracked, `hb pull <cardId> <path>`, then read the resulting `.md`.

For pure reads with no intent to maintain, prefer `heptabase note read
<cardId>` (base CLI) instead of hbedit — no state.json binding gets
created.

---

## SOP E — Edit tags on an existing card

1. `hb doctor`.
2. Verify path is in `state.json`. If not, pull first (SOP A steps 1–2).
3. To add: `hb tag add <path> <name>`. On `tag-ambiguity`, show the warning
   and ask the user to confirm before retrying.
4. To remove: `hb tag remove <path> <name>`. On `tag-not-on-card`, no action
   needed.
5. Commit `state.json`.

---

## SOP F — Multi-step composites (split / merge / batch)

These operations are built from primitives, not single commands.

**Split one card into two:**

1. Pull the source card (SOP A steps 1–3).
2. Plan the split — show the user which content goes where and confirm.
3. Edit source `.md` to its portion; write a new `.md` for the second part.
4. `hb push <source-path>` (updated) then `hb push <new-path>` (created).
5. Commit both `.md` files and `state.json`.

**Merge two cards into one:**

1. Pull both cards. Plan + confirm the merge layout with the user.
2. Append second card's content into the first `.md`.
3. `hb push <primary-path>`.
4. Inform the user the second card still exists in Heptabase; ask if they
   want to trash it manually and `hb unlink <second-path>` to drop its
   binding.
5. Commit.

**Batch push (multiple files):**

1. List all candidate files; show the user the batch and confirm before
   starting.
2. Push files one at a time, collecting results. On any error, stop and
   report — do not continue past a `state-corrupt` error.

---

## Conflict resolution (referenced by SOPs A and C)

When `hb push` returns `code: "content-conflict"` or `hb pull` returns
`action: "conflict"`, a `.conflict.md` backup of local edits has been
created and the working `.md` now holds the remote version.

1. Present both files to the user.
2. Produce a merged version (semantic merge) and confirm with the user.
3. Write the merged content to the working `.md`.
4. `hb push <path>`.
```

- [ ] **Step 2: Verify TOC matches sections**

```bash
grep -E '^## ' /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/references/workflows.md
```

Expected: 8 lines — `## Contents`, `## SOP A`, `## SOP B`, `## SOP C`, `## SOP D`, `## SOP E`, `## SOP F`, `## Conflict resolution`. TOC has 7 entries (excluding `## Contents` itself).

- [ ] **Step 3: Commit**

```bash
git add skills/hbedit/references/workflows.md
git commit -m "docs(hbedit): extract workflow SOPs to references/workflows.md

SOPs A-F + Conflict resolution lifted from SKILL.md into a single
reference file with a TOC (per Anthropic's >100-line rule). Adds
mentions of hb unlink as the recovery path in SOP B and SOP F merge.
Behavior unchanged."
```

---

## Task 3: Implement `hb unlink <path>` (TDD)

**Goal:** New command that removes a path's binding from `state.json` + cache without touching the local md file or remote card. Used for cheap recovery when `hb push` was mis-routed to a file the user wanted untracked.

**Files:**
- Create: `tests/test_unlink.py`
- Modify: `skills/hbedit/scripts/hbedit.py` (add `unlink()` function — dispatch wiring lands in Task 4's argparse refactor)

- [ ] **Step 1: Write failing tests**

Create `tests/test_unlink.py`:

```python
"""Unit tests for `hb unlink <path>` — removes a path's binding from
state.json + per-machine cache without touching local md or remote card."""
import json
import os
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "skills", "hbedit", "scripts"))
import hbedit
import vault as vaultlib
import local_state


def _make_vault_with_tracked_file(root, rel_path="notes/foo.md",
                                  card_id="card-abc-123"):
    """Set up a vault with one tracked file. Returns (vault_info, abs_path)."""
    vaultlib.init_vault(root)
    info = vaultlib.find(root)
    abs_path = os.path.join(root, rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write("# Foo\n\nBody.\n")
    # Register in state.json
    vaultlib.set_file_entry(info.root, rel_path, card_id, [])
    # Populate local-state and sidecar
    local_state.set_local_entry(
        info.cache_dir, rel_path,
        content_md5="dummy-content-md5",
        local_md5="dummy-local-md5",
        synced_at="2026-05-24T00:00:00Z")
    sidecar = hbedit._sidecar_path(info.cache_dir, card_id)
    with open(sidecar, "w", encoding="utf-8") as f:
        f.write('{"type":"doc","content":[]}')
    return info, abs_path


class TestUnlinkBasic(unittest.TestCase):
    def test_unlink_removes_state_entry(self):
        with tempfile.TemporaryDirectory() as root:
            info, _ = _make_vault_with_tracked_file(root)
            out, rc = hbedit.unlink(os.path.join(root, "notes/foo.md"))
            self.assertEqual(rc, 0)
            payload = json.loads(out)
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["action"], "unlinked")
            self.assertEqual(payload["path"], "notes/foo.md")
            self.assertEqual(payload["cardId"], "card-abc-123")
            # state.json should no longer have the entry
            state = vaultlib.load_state(info.root)
            self.assertNotIn("notes/foo.md", state["files"])

    def test_unlink_removes_local_state_entry(self):
        with tempfile.TemporaryDirectory() as root:
            info, _ = _make_vault_with_tracked_file(root)
            hbedit.unlink(os.path.join(root, "notes/foo.md"))
            entry = local_state.get_local_entry(info.cache_dir, "notes/foo.md")
            self.assertIsNone(entry)

    def test_unlink_removes_sidecar(self):
        with tempfile.TemporaryDirectory() as root:
            info, _ = _make_vault_with_tracked_file(root, card_id="card-xyz")
            sidecar = hbedit._sidecar_path(info.cache_dir, "card-xyz")
            self.assertTrue(os.path.exists(sidecar))
            hbedit.unlink(os.path.join(root, "notes/foo.md"))
            self.assertFalse(os.path.exists(sidecar))

    def test_unlink_leaves_local_md_alone(self):
        with tempfile.TemporaryDirectory() as root:
            info, abs_path = _make_vault_with_tracked_file(root)
            original_body = open(abs_path).read()
            hbedit.unlink(abs_path)
            self.assertTrue(os.path.exists(abs_path))
            self.assertEqual(open(abs_path).read(), original_body)


class TestUnlinkErrors(unittest.TestCase):
    def test_unlink_path_not_tracked(self):
        with tempfile.TemporaryDirectory() as root:
            vaultlib.init_vault(root)
            os.makedirs(os.path.join(root, "notes"))
            untracked = os.path.join(root, "notes/never-pushed.md")
            with open(untracked, "w") as f:
                f.write("# Foo\n")
            out, rc = hbedit.unlink(untracked)
            self.assertEqual(rc, 2)
            payload = json.loads(out)
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["code"], "path-not-tracked")

    def test_unlink_idempotent_second_call_errors(self):
        # Second unlink on a path that's already gone returns the same
        # path-not-tracked error — agent / user can infer it's already done.
        with tempfile.TemporaryDirectory() as root:
            _make_vault_with_tracked_file(root)
            abs_path = os.path.join(root, "notes/foo.md")
            out1, rc1 = hbedit.unlink(abs_path)
            self.assertEqual(rc1, 0)
            out2, rc2 = hbedit.unlink(abs_path)
            self.assertEqual(rc2, 2)
            self.assertEqual(json.loads(out2)["code"], "path-not-tracked")

    def test_unlink_not_in_vault(self):
        with tempfile.TemporaryDirectory() as root:
            # No vault init
            os.makedirs(os.path.join(root, "notes"))
            target = os.path.join(root, "notes/orphan.md")
            with open(target, "w") as f:
                f.write("# Foo\n")
            out, rc = hbedit.unlink(target)
            self.assertEqual(rc, 2)
            self.assertEqual(json.loads(out)["code"], "not-in-vault")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/leiweicheng/Desktop/HeptaSync
python3 -m pytest tests/test_unlink.py -v
```

Expected: FAIL with `AttributeError: module 'hbedit' has no attribute 'unlink'`.

- [ ] **Step 3: Implement `unlink()` in `hbedit.py`**

In `skills/hbedit/scripts/hbedit.py`, add this function after `tag_remove` (around line 462, right before the `_backup_local` helper):

```python
def unlink(path):
    """Implement `hb unlink <path>` — remove binding without touching
    the local .md file or the remote Heptabase card. Cleans state.json,
    local-state.json, and sidecar/<cardId>.json."""
    try:
        info = vaultlib.find(path) or vaultlib.find(os.getcwd())
    except vaultlib.StateSchemaError as exc:
        return errors.emit_error("unlink", errors.STATE_SCHEMA_UNSUPPORTED,
                                 detail=str(exc)), 2
    except vaultlib.StateCorruptError as exc:
        return errors.emit_error("unlink", errors.STATE_CORRUPT,
                                 detail=str(exc)), 2
    if info is None:
        return errors.emit_error(
            "unlink", errors.NOT_IN_VAULT, path=path,
            detail="no .hbedit/ found at or above %s" % path), 2
    vault, state, cd = info.root, info.state, info.cache_dir
    rel = _resolve_vault_relative(vault, path)

    entry = state["files"].get(rel)
    if entry is None:
        return errors.emit_error(
            "unlink", errors.PATH_NOT_TRACKED, path=rel,
            detail="%s is not tracked; nothing to unlink." % rel), 2
    card_id = entry["cardId"]

    # Remove the three persistent bits. Local md and remote card untouched.
    vaultlib.remove_file_entry(vault, rel)
    local_state.remove_local_entry(cd, rel)
    sidecar = _sidecar_path(cd, card_id)
    if os.path.exists(sidecar):
        os.unlink(sidecar)

    return errors.emit_ok("unlink", action="unlinked",
                          cardId=card_id, path=rel), 0
```

(Dispatch wiring — adding `unlink` to `main()` — is part of Task 4's argparse refactor.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_unlink.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 5: Run full test suite to confirm no regressions**

```bash
python3 -m pytest tests/ -v
```

Expected: All tests PASS (including pre-existing test_vault, test_doctor, etc.).

- [ ] **Step 6: Commit**

```bash
git add skills/hbedit/scripts/hbedit.py tests/test_unlink.py
git commit -m "feat(hbedit): add hb unlink <path> to remove binding cleanly

Removes the path's entry from state.json, local-state.json, and
sidecar/<cardId>.json. Leaves the local .md file and the remote
Heptabase card alone (user owns the md; user trashes the card
separately if desired). Idempotent-friendly: second unlink on the
same path returns path-not-tracked.

Provides cheap recovery when the SKILL.md's default 'in vault →
hb push' routes a file the user actually wanted fire-and-forget."
```

---

## Task 4: Refactor `hbedit.py` `main()` to use argparse (Phase 4a)

**Goal:** Replace the manual `if len(argv) == X` dispatch with argparse sub-parsers so every sub-command's `--help` works without error. Wire up `unlink` from Task 3 at the same time.

**Files:**
- Modify: `skills/hbedit/scripts/hbedit.py:591-624` (the `main()` function)
- Create: `tests/test_cli_help.py`

- [ ] **Step 1: Write failing tests for `--help`**

Create `tests/test_cli_help.py`:

```python
"""Smoke tests for `hb <cmd> --help` — every sub-command must accept
--help without erroring out, so SKILL.md can reliably point agents at
'run hb <cmd> --help for details'."""
import os
import subprocess
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HB = os.path.join(_ROOT, "skills", "hbedit", "scripts", "hbedit.py")


def _run(args):
    """Run hb with the given args; return (stdout, stderr, rc)."""
    proc = subprocess.run(
        [sys.executable, _HB] + args,
        capture_output=True, text=True)
    return proc.stdout, proc.stderr, proc.returncode


class TestSubcommandHelp(unittest.TestCase):
    """Each sub-command's --help must exit 0 and print usage to stdout."""

    def test_doctor_help(self):
        out, err, rc = _run(["doctor", "--help"])
        self.assertEqual(rc, 0, "stderr=%s" % err)
        self.assertIn("doctor", out.lower())

    def test_init_help(self):
        out, err, rc = _run(["init", "--help"])
        self.assertEqual(rc, 0, "stderr=%s" % err)
        self.assertIn("init", out.lower())

    def test_push_help(self):
        out, err, rc = _run(["push", "--help"])
        self.assertEqual(rc, 0, "stderr=%s" % err)
        self.assertIn("push", out.lower())
        self.assertIn("path", out.lower())

    def test_pull_help(self):
        out, err, rc = _run(["pull", "--help"])
        self.assertEqual(rc, 0, "stderr=%s" % err)
        self.assertIn("pull", out.lower())

    def test_tag_help(self):
        out, err, rc = _run(["tag", "--help"])
        self.assertEqual(rc, 0, "stderr=%s" % err)
        self.assertIn("tag", out.lower())

    def test_tag_add_help(self):
        out, err, rc = _run(["tag", "add", "--help"])
        self.assertEqual(rc, 0, "stderr=%s" % err)
        self.assertIn("add", out.lower())

    def test_tag_remove_help(self):
        out, err, rc = _run(["tag", "remove", "--help"])
        self.assertEqual(rc, 0, "stderr=%s" % err)
        self.assertIn("remove", out.lower())

    def test_unlink_help(self):
        out, err, rc = _run(["unlink", "--help"])
        self.assertEqual(rc, 0, "stderr=%s" % err)
        self.assertIn("unlink", out.lower())


class TestTopLevelHelp(unittest.TestCase):
    def test_top_level_help(self):
        out, err, rc = _run(["--help"])
        self.assertEqual(rc, 0, "stderr=%s" % err)
        # Top-level help should mention each sub-command.
        for cmd in ("doctor", "init", "push", "pull", "tag", "unlink"):
            self.assertIn(cmd, out, "missing %s in top-level help" % cmd)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/leiweicheng/Desktop/HeptaSync
python3 -m pytest tests/test_cli_help.py -v
```

Expected: FAIL — most cases will error because the current `main()` treats `--help` as an unknown arg and prints `__doc__` with rc=1. Tests expect rc=0.

- [ ] **Step 3: Refactor `main()` in `hbedit.py`**

In `skills/hbedit/scripts/hbedit.py`, add `import argparse` to the top of the file (alongside the other stdlib imports near line 16-32). Then replace the entire `main()` function (lines 591-624) with:

```python
def _build_parser():
    """Construct the argparse parser for `hb`. Each sub-command's `help`
    string is what shows up in `hb --help`; their own `--help` is
    auto-generated from add_argument calls."""
    parser = argparse.ArgumentParser(
        prog="hb",
        description="hbedit — edit Heptabase cards through local markdown "
                    "files. UNOFFICIAL — talks only to the official "
                    "`heptabase` CLI.")
    sub = parser.add_subparsers(dest="command", required=True,
                                metavar="<command>")

    sub.add_parser("doctor",
                   help="preflight: verify CLI + desktop app + report cache")
    sub.add_parser("init",
                   help="initialize an hbedit vault in the current directory")

    p_push = sub.add_parser(
        "push", help="sync a tracked or new local .md up to Heptabase")
    p_push.add_argument("path", help="markdown file to push")

    p_pull = sub.add_parser(
        "pull",
        help="pull from Heptabase — `hb pull <path>` smart-syncs a tracked "
             "file; `hb pull <cardId> <path>` first-time binds a new path")
    p_pull.add_argument("first", metavar="path-or-cardId")
    p_pull.add_argument("second", nargs="?", default=None,
                        metavar="path",
                        help="provide only when first arg is a cardId")

    p_tag = sub.add_parser("tag", help="add or remove a tag on a tracked card")
    tag_sub = p_tag.add_subparsers(dest="tag_action", required=True,
                                   metavar="<add|remove>")
    p_tag_add = tag_sub.add_parser("add", help="add a tag to the bound card")
    p_tag_add.add_argument("path")
    p_tag_add.add_argument("name")
    p_tag_remove = tag_sub.add_parser("remove",
                                      help="remove a tag from the bound card")
    p_tag_remove.add_argument("path")
    p_tag_remove.add_argument("name")

    p_unlink = sub.add_parser(
        "unlink",
        help="remove the path's binding (state + cache); leave the local "
             ".md and the remote Heptabase card untouched")
    p_unlink.add_argument("path")

    return parser


def main(argv):
    parser = _build_parser()
    args = parser.parse_args(argv[1:])

    if args.command == "doctor":
        out, rc = doctor()
    elif args.command == "init":
        out, rc = init(os.getcwd())
    elif args.command == "push":
        out, rc = push(args.path)
    elif args.command == "pull":
        if args.second is None:
            out, rc = pull_smart(args.first)
        else:
            out, rc = pull_first_time(args.first, args.second)
    elif args.command == "tag":
        if args.tag_action == "add":
            out, rc = tag_add(args.path, args.name)
        else:
            out, rc = tag_remove(args.path, args.name)
    elif args.command == "unlink":
        out, rc = unlink(args.path)
    else:
        # argparse with required=True should make this unreachable,
        # but keep a defensive fallback.
        parser.print_help()
        return 1
    print(out)
    return rc
```

The module docstring at the top of `hbedit.py` (lines 1-13) was the old usage summary. Update it to reflect the new layout — replace the existing lines 1-13 with:

```python
"""hbedit v3 — Heptabase card editing through local markdown files.

Run `hb --help` or `hb <cmd> --help` for full usage. Top-level commands:
  hb doctor, init, push, pull, tag add|remove, unlink.

UNOFFICIAL — talks only to the official `heptabase` CLI.
"""
```

- [ ] **Step 4: Run `test_cli_help` to verify it passes**

```bash
python3 -m pytest tests/test_cli_help.py -v
```

Expected: All 9 tests PASS.

- [ ] **Step 5: Run full test suite — argparse refactor must not break anything**

```bash
python3 -m pytest tests/ -v
```

Expected: All tests PASS. Sanity-check that `test_vault.py`, `test_doctor.py`, `test_local_state.py`, `test_unlink.py` (from Task 3), `test_errors.py`, `test_htb_args.py`, `test_pm2md.py`, `test_tagsync.py` all stay green.

- [ ] **Step 6: Smoke-test the CLI by hand**

```bash
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py --help
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py doctor --help
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py push --help
python3 /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/scripts/hbedit.py unlink --help
```

Expected: each prints argparse-formatted help to stdout, exits 0.

- [ ] **Step 7: Commit**

```bash
git add skills/hbedit/scripts/hbedit.py tests/test_cli_help.py
git commit -m "refactor(hbedit): argparse-based dispatch + per-command --help

Replaces the manual 'if len(argv) == X' dispatch with argparse
sub-parsers. Every sub-command now accepts --help and exits 0 with
auto-generated usage. Wires up hb unlink (added in prior commit).

Phase 4a of the SKILL.md compression plan — lets SKILL.md point
at 'run hb <cmd> --help' instead of inlining flag/output details
for each command. Phase 4b (rich --help text per command) is left
as an incremental follow-up."
```

---

## Task 5: Rewrite `SKILL.md` to the new ~70-line version

**Goal:** Replace the current 323-line SKILL.md with the narrow-but-trigger-permissive design from the spec. Default + escape hatch routing in body, references for detail.

**Files:**
- Rewrite: `skills/hbedit/SKILL.md`

- [ ] **Step 1: Replace `SKILL.md` with the new version**

Overwrite the entire `skills/hbedit/SKILL.md` with:

```markdown
---
name: hbedit
description: Edit Heptabase cards through local markdown files with `state.json`
  binding. Only path for editing the middle of an existing card (block-ID
  transplant), pushing a local md as a tracked card, maintaining a card↔file
  binding across machines via git, or precise tag changes on existing cards.
  Use when the user wants to edit existing card content, continue editing
  after git clone, push a local markdown file to Heptabase, change tags on
  an existing card, or remove a card's local binding. Base `heptabase` CLI
  handles one-shot creates, appends, reads, searches — hbedit owns ongoing
  maintenance.
allowed-tools: Bash(hb *) Bash(heptabase *)
---

# hbedit (unofficial)

> Non-official. Built only on the official `heptabase` CLI; never reads
> or writes Heptabase's database, storage, or internal files. If asked
> whether this is official: it is not.

## What hbedit uniquely does

- Edit the middle of an existing card via block-ID transplant (base CLI cannot).
- Maintain a card↔file binding committed in `.hbedit/state.json` so the same
  card can be edited from multiple machines via git.
- Push a local markdown file as a tracked card with bidirectional sync.
- Add/remove tags on an existing card without disturbing other tags.

## Default behavior

| Situation | Default | Escape hatch |
|---|---|---|
| User asks markdown→card, in a vault | `hb push <path>` (tracked) | Explicit «一次性» / «不用追蹤» / «隨手» / «丟上去就好» → `heptabase note create` |
| User points at existing tracked file (by cardId or path) | hbedit (`hb pull` if stale, edit, `hb push`) | None — hbedit is the only correct tool |
| User says «剛 clone 進來» / «另一台機器» | `hb pull <path>` smart-sync first | None |
| Pure read / search / list | base CLI | None — hbedit adds no value |
| Generic «Heptabase 設置 OK 嗎» | base CLI's `heptabase --version` | User specifically asks about vault/sync state → `hb doctor` |
| Not in a vault, user wants to push | base CLI's `heptabase note create` | User explicitly wants to start syncing → `hb init` first |

Mistake recovery: if `hb push` ran when the user actually wanted
fire-and-forget, run `hb unlink <path>` to drop the binding cleanly
(local md and remote card both untouched).

## Preflight

`hb doctor` runs once before any other hb command. On error, look up the
`code` field in `references/errors.md`.

## Vault model

`.hbedit/state.json` (committed, git-tracked) binds `path → {cardId, tags}`
plus `vaultId` (UUIDv4, set at `hb init`). Per-machine cache at
`~/.hbedit/cache/<vaultId>/` (`local-state.json` + `sidecar/<cardId>.json`).
A directory is an hbedit vault if it or any ancestor contains
`.hbedit/state.json` (the *file* — an empty `.hbedit/` does not count).

## Commands

Run `hb <cmd> --help` for flags, output JSON shape, and command-specific
error codes.

- `hb doctor` — preflight + per-vault cache state report
- `hb init` — initialize a vault in the current directory
- `hb push <path>` — create new card or update existing (block-ID transplant)
- `hb pull <cardId> <path>` — first-time bind by cardId
- `hb pull <path>` — smart-sync a tracked path (baseline / noop / updated / conflict)
- `hb tag add|remove <path> <name>` — round-trip safe tag edits
- `hb unlink <path>` — remove binding without deleting local md or remote card

## Limitations

- Card-to-card references can't be authored from markdown.
- ~100,000 char ProseMirror push cap; very large cards may fail.
- Note cards only — no journal, PDF, or whiteboard.
- No `hb mv`: renaming a tracked .md requires manual `state.json` edit.

## Look up

- Workflow SOPs (edit / multi-machine / split / merge / batch / conflict
  resolution): `references/workflows.md`
- Error code handling per `code`: `references/errors.md`
- Per-command detail: `hb <cmd> --help`
```

- [ ] **Step 2: Verify line count**

```bash
wc -l /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/SKILL.md
```

Expected: 65-85 lines (well under the spec's 100-line cap and Anthropic's 500-line cap).

- [ ] **Step 3: Verify description length**

The YAML frontmatter description field has a 1024-char cap per Anthropic spec.

```bash
python3 -c "
import re
with open('/Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/SKILL.md') as f:
    text = f.read()
m = re.search(r'description:(.*?)allowed-tools:', text, re.DOTALL)
desc = m.group(1).strip()
print('description chars:', len(desc))
print('cap: 1024')
"
```

Expected: well under 1024 chars (target ~600).

- [ ] **Step 4: Verify references referenced exist**

```bash
ls /Users/leiweicheng/Desktop/HeptaSync/skills/hbedit/references/
```

Expected: `errors.md`, `workflows.md` (both created in Tasks 1 + 2).

- [ ] **Step 5: Commit**

```bash
git add skills/hbedit/SKILL.md
git commit -m "docs(hbedit)!: rewrite SKILL.md as narrow trigger + default/escape

Replaces 323-line SOP-heavy SKILL.md with a 70-ish-line version
following Anthropic skill best practices:

- Narrow but trigger-permissive description (matches 'push markdown
  to Heptabase' without requiring explicit 'tracked' qualifier, so
  hbedit loads alongside base CLI for ambiguous prompts and the
  body's default-in-vault routes correctly)
- Default + escape hatch routing table (no ASK pattern, which the
  Anthropic guide flags as 'too many choices' anti-pattern)
- Workflow SOPs moved to references/workflows.md
- Error code SOPs moved to references/errors.md
- Per-command detail deferred to 'hb <cmd> --help' (Phase 4a now
  works after argparse refactor)

Behavior of the underlying CLI is unchanged. Agent routing on
ambiguous in-vault prompts shifts more aggressively toward hbedit
(tracked binding); orphan-card recovery via 'hb unlink <path>'.

Spec: docs/superpowers/specs/2026-05-24-hbedit-skill-redesign-design.md"
```

---

## Task 6: Update manual test doc with 4 trigger TCs

**Goal:** Replace the obsolete trigger-style TCs (TC-2, TC-4, TC-5, TC-6, TC-8, TC-11) with 4 new trigger TCs (A/B/C/D) that match the new SKILL.md design. Keep regression TCs (TC-1, TC-3, TC-7, TC-9, TC-10) as-is. Update the Test Matrix to reflect the final 9-TC layout.

**Files:**
- Modify: `docs/superpowers/testing/2026-05-24-hbedit-v3-manual-tests.md`

- [ ] **Step 1: Update the Test Matrix table**

Replace the existing Test Matrix table (look for the line starting `| TC | 標題 | 對應 AC / 目的 | Priority | Status |`) with:

```markdown
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

**已刪除**:TC-4 / TC-5(`hb doctor` 不該獨佔健康檢查 — 改框法,行為已用 shell 直接驗證)。
**已替換**:TC-2 → TC-trigger-C,TC-6 → TC-trigger-A,TC-8 → TC-trigger-B,TC-11 → TC-trigger-D。
```

- [ ] **Step 2: Remove obsolete TC sections**

In the same file, delete these whole sections (each is the `## TC-X: ...` heading down to but not including the next `## TC-...` heading):

- `## TC-2: 把本地筆記推成新卡`
- `## TC-4: vault 內健康檢查`
- `## TC-5: vault 外健康檢查`
- `## TC-6: round-trip 編輯一張卡`
- `## TC-8: 多機同步(clone 模擬)`
- `## TC-11: 開新卡片走 base CLI(skill 邊界)`

Use the Edit tool repeatedly on each section's complete text. The intent: file ends up with only TC-1, TC-3, TC-7, TC-9, TC-10 as the originally-numbered sections.

- [ ] **Step 3: Add the 4 new trigger TC sections**

Append these sections to the test doc, after the existing TC sections but before `## 全部跑完之後` (or wherever the footer / closing sections start). Each section follows the existing TC format (環境 setup → Session 啟動 → Prompt → 預期 → 驗證指令 → Reset → Status):

```markdown
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
```

- [ ] **Step 4: Verify doc structure**

```bash
grep -E '^## TC-' /Users/leiweicheng/Desktop/HeptaSync/docs/superpowers/testing/2026-05-24-hbedit-v3-manual-tests.md
```

Expected output (9 lines):

```
## TC-1:第一次設定 vault
## TC-3:拉既有卡片到本地
## TC-7:在 vault 外 push 檔案 ⚠️ 關鍵 v3 bug fix
## TC-9:從深層子目錄發指令
## TC-10:帶 v2 schema 的 vault
## TC-trigger-A:改既有卡中段(強訊號正面觸發)
## TC-trigger-B:多機 clone 後接續編輯(強訊號正面觸發)
## TC-trigger-C:vault 內推 markdown 帶維護訊號(default+escape 驗證)
## TC-trigger-D:一次性建卡 + 明確 fire-and-forget(escape hatch / 負面觸發)
```

If TC-2, TC-4, TC-5, TC-6, TC-8, or TC-11 still appear → repeat Step 2 deletions for the missed ones.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/testing/2026-05-24-hbedit-v3-manual-tests.md
git commit -m "test(hbedit): redesign trigger TCs for new SKILL.md (4 trigger + 5 regression)

Removes obsolete trigger-style TCs:
- TC-4 / TC-5: hb doctor as health-check trigger (wrong premise —
  doctor is preflight, not user-facing trigger)
- TC-2 / TC-6 / TC-8 / TC-11: replaced by sharper trigger TCs that
  match the new SKILL.md design

Adds 4 trigger TCs aligned with the redesigned SKILL.md:
- TC-trigger-A: edit existing card (strong positive)
- TC-trigger-B: multi-machine clone continue (strong positive)
- TC-trigger-C: in-vault push with maintain signal (default+escape)
- TC-trigger-D: explicit fire-and-forget create (negative trigger /
  escape hatch verification)

Retains regression TCs: TC-1 (init), TC-3 (pull), TC-7 (v3 vault
discovery bug fix), TC-9 (deep subdir), TC-10 (v2 schema reject).
Each TC carries pre-setup commands, prompt, expected behavior,
verification commands, and reset block."
```

---

## Plan summary

6 tasks, each a separate commit:

1. **Extract `references/errors.md`** — pure file extraction from current SKILL.md error table.
2. **Extract `references/workflows.md`** — pure file extraction with TOC.
3. **Add `hb unlink <path>`** — TDD: 7 unit tests + new `unlink()` function.
4. **Refactor `hbedit.py` `main()` to argparse** — TDD: 9 `--help` smoke tests + argparse-based dispatch + wires up `unlink`.
5. **Rewrite `SKILL.md`** — replace 323 lines with ~70-line narrow+permissive version pointing at references/ and `hb <cmd> --help`.
6. **Update test doc** — 4 new trigger TCs replace 4 obsolete ones; 2 doctor TCs removed; 5 regression TCs retained.

After Task 6 commits, the manual test loop begins (user opens fresh session per TC, pastes prompt, returns output; we verify, log status, reset env, move to next). The test doc as written already documents this flow.

---

## Self-review checklist (run before handoff)

**Spec coverage:**
- Spec § «Architecture / Three-tier information layout» → Task 1 (errors), Task 2 (workflows), Task 4 (--help), Task 5 (new SKILL.md). ✓
- Spec § «`hb unlink` command» → Task 3 + Task 4 (dispatch). ✓
- Spec § «Sub-command `--help` (Phase 4a)» → Task 4. ✓
- Spec § «references/workflows.md» / «references/errors.md» → Tasks 1, 2. TOC requirement met in Task 2. ✓
- Spec § «Acceptance criteria» line 1 (SKILL.md ≤ 100 lines) → Task 5 Step 2 verification. ✓
- Spec § «Acceptance criteria» lines 2-4 → Tasks 1, 2, 3 each include the verification step. ✓
- Spec § «Acceptance criteria» line 5 (`hb <cmd> --help` works) → Task 4 verification. ✓
- Spec § «Acceptance criteria» line 6 (9-TC matrix) → Task 6 Test Matrix update + new TC sections. ✓
- Spec § «Acceptance criteria» line 7 (no regressions) → Task 4 Step 5 runs full suite. ✓

**Placeholder scan:**
- No `TBD` / `TODO` / `implement later` in tasks. ✓
- Every test has actual test code, not "write tests for the above". ✓
- All file paths absolute or relative-from-repo-root, no «exact path here». ✓

**Type / signature consistency:**
- `unlink(path)` signature consistent across Task 3 implementation, Task 4 dispatch wiring, and Task 6 verification commands. ✓
- `_doctor_cache_line` / `_sidecar_path` / `_resolve_vault_relative` all reference existing functions in `hbedit.py`, not invented. ✓
- argparse attribute names (`args.command`, `args.path`, `args.first`, `args.second`, `args.tag_action`, `args.name`) consistent between `_build_parser` and `main` dispatch. ✓

No issues found. Plan ready for handoff.
