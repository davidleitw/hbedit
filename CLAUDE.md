# hbedit project conventions

Instructions that apply to any Claude Code session opened in this repo.

## Release discipline

When tagging a new version (`vX.Y.Z`):

1. Add a `### vX.Y.Z — YYYY-MM-DD` block at the top of `## Changelog` in
   **both** `README.md` and `README.zh.md`. Bullet user-visible changes
   only — implementation refactors with no behavior change don't belong
   here. Keep voice consistent with prior entries.
2. Bump `version` in `.claude-plugin/plugin.json` to match the tag.
3. Commit those changes together as `chore(release): vX.Y.Z` and tag
   that commit.
4. Tag and branch get pushed together — never push a tag whose changelog
   entry isn't yet committed.

The two READMEs, the manifest version, and the git tag should all
describe the same state. If one is missing the others, the release is
not yet ready.

## CLI verification discipline

`skills/hbedit/SKILL.md` declares `Verified against Heptabase CLI: X.Y.x`
near the top. That line is the single source of truth for which upstream
CLI versions we've actually tested against. hbedit does **not** gate on
CLI version — the line is consulted by agents only when an error already
occurred, via the `cli-response-unexpected` SOP.

When Heptabase ships a new CLI minor (e.g. `0.4`):

1. Run the manual TCs (scratch card / transplant / tag round-trip) against
   the new CLI.
2. If green: update the "Verified against" line and the "last tested"
   date in `SKILL.md`, and ship as a patch release (`vX.Y.(Z+1)` — the
   release notes simply say "verified against 0.Y.x").
3. If something breaks: do **not** update the line. File an issue, fix
   hbedit, then update the line as part of the fix release.

The line moves only on green TCs. Do not bump it speculatively or as a
hopeful gesture — the whole error-time UX hinges on it being trustworthy.

## State schema discipline

`.hbedit/state.json` carries a `schemaVersion` field. Any change to its
structure or invariants — new fields, new constraints on existing fields,
new validation — requires:

1. Bumping `schemaVersion`.
2. Updating the `state-schema-unsupported` SOP in
   `skills/hbedit/references/errors.md` so older state files get a
   meaningful error path, not a corrupt-state surprise.

v3 (current) does not automatically migrate from v2; that policy stays
unless a future version explicitly takes on migration as a feature.

## Touching SKILL.md or references

`skills/hbedit/SKILL.md` and the files in `skills/hbedit/references/`
shape agent behavior in the field. Changes to either need to be
verified with the manual TCs (history of which is in git log under
`docs/superpowers/testing/` before the dev-docs cleanup commit
`1913a18` — restorable via `git checkout 1913a18~ -- docs/`).

In particular: do not soften the destructive-recovery wording in
`state-schema-unsupported` (introduced in `cf0434c`). It exists because
agents will otherwise reason their way into auto-running `rm -rf
.hbedit`. The wording is the guard.
