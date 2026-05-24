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
