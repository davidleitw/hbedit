# hbedit Error Code SOPs

Per-code agent guidance for `hb` command failures. Each entry: what
happened + numbered steps to take. Returned in the JSON output's `code`
field on a non-`ok` status.

## cli-missing

What happened: `heptabase` binary not on PATH.

The CLI ships with the Heptabase desktop app (≥ v1.91.0). It is **not**
distributed via npm, brew, or any package manager — enabling it is a
desktop-app setting.

Agent steps:
1. Inform the user the `heptabase` CLI is not on PATH.
2. Direct them to the desktop app: **Settings → AI Features → CLI**, then
   toggle it on. The desktop app must be v1.91.0 or newer; if older, ask
   them to update the desktop app first.
3. macOS: the binary lands on PATH automatically — nothing else to do.
   Windows: the app prints a one-time PATH-setup command; ask the user to
   run it, then open a fresh shell.
4. Reference: <https://support.heptabase.com/en/articles/14715462-how-to-use-heptabase-cli>
5. Pause; do not continue until `hb doctor` returns ok.

## cli-response-unexpected

What happened: an `hb` command got back stdout from `heptabase` that
isn't parseable as JSON (e.g. plain text, HTML, or an empty body where
JSON was expected). Most likely causes: Heptabase shipped a new CLI
that changed the response shape, or the desktop-app HTTP layer is in
a degraded state.

hbedit no longer pre-gates on CLI version, so this error is the signal
that drift may have happened.

Agent steps:
1. **Stop.** Do not retry the command. Do not edit `state.json`. Do not
   attempt a workaround.
2. Run `heptabase --version` and read the "Verified against" line at the
   top of `SKILL.md`.
3. **If the versions differ** (e.g. user has `0.4.0`, SKILL.md says
   `0.3.x`), tell the user:
   > Your `heptabase` CLI is `<actual>`, but this version of hbedit
   > was only verified against `<verified>`. The error may be due to
   > upstream API changes. Please either (a) check whether a newer
   > hbedit release supports `<actual>`, or (b) open an issue at
   > <https://github.com/davidleitw/hbedit/issues> with both versions
   > and the full error output.
4. **If the versions match**, the error is not version-drift. Surface
   the raw `detail` field to the user and ask them to open an issue
   at the same URL with the full error and what they were doing.
5. Reference: <https://support.heptabase.com/en/articles/14715462-how-to-use-heptabase-cli>
6. Pause until the user decides how to proceed.

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

## create-failed

What happened: `hb push` failed while creating a new card. Two sub-cases,
distinguished by the `detail` field:

**Sub-case A — card never created.** `detail` is a plain CLI error
(e.g. network failure, validation error). Nothing exists on Heptabase,
nothing changed in `state.json`.

Agent steps:
1. Surface the `detail` to the user.
2. Address the underlying cause (retry transient failure, fix body, etc.).
3. Re-run `hb push <path>`.

**Sub-case B — card created, substitution failed.** `detail` contains
`substitution failed` and `id=<cardId>` and `The card exists on Heptabase
with placeholders unresolved.` The card **is** on Heptabase, but no entry
was written to `state.json`. A naive retry of `hb push <path>` will create
a **second** card with the same content, leaving the first as an orphan.

Agent steps:
1. **Stop.** Do not retry `hb push <path>` blindly — that creates a
   duplicate orphan.
2. Extract `<cardId>` from the `detail` string and show it to the user
   along with what state the card is in (exists on Heptabase,
   `[[card:…]]` / `[[date:…]]` placeholders unresolved, not registered
   locally).
3. **Present** the two recovery options without executing them:
   - **Adopt the orphan**: `hb pull <cardId> <path>` to bind the existing
     card to the local file, then `hb push <path>` to retry the
     substitution via the update flow. Preserves the cardId and any inbound
     references already pointing at it.
   - **Discard the orphan**: run `heptabase card trash <cardId>` (or
     trash it from the desktop app — hbedit itself has no trash-by-id
     subcommand), then re-run `hb push <path>` for a clean create. Loses
     the cardId — use only if nothing references it yet.
4. **Wait for explicit user choice** before running either recovery. Do
   not pick on the user's behalf; the right call depends on whether they
   already shared the cardId out.

## state-schema-unsupported

What happened: `state.json` has `schemaVersion` other than 3.

Agent steps:
1. **Stop immediately.** Do not run any hb / shell command that mutates `.hbedit/` — no `rm`, no `hb init`, no rewriting `state.json`. v3 does not migrate v2 state files automatically.
2. Inform the user: show the affected path and the current `schemaVersion`.
3. **Present** the recovery options without executing them. List both, with their trade-offs:
   - Re-run `hb init` after removing `.hbedit/` — **destructive**, loses all tracked bindings; if `files` is non-empty those cards become orphans.
   - Manually upgrade `state.json` (set `schemaVersion: 3`, add a `vaultId` UUID) — preserves bindings if user understands the v2 → v3 diff.
4. **Wait for explicit user confirmation** before running any recovery command. Even if `files: {}` looks "safe to wipe", the decision is the user's — they may have audit / migration / archive reasons to keep the old `.hbedit/`. Reasoning your way past this rule is the failure mode this SOP is here to prevent.

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
