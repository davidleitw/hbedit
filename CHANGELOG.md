# Changelog

Versions follow [SemVer](https://semver.org). Newest first.

## v0.1.4 — 2026-05-26

- Date inline nodes (`date` nodes in ProseMirror) now round-trip
  through `hb pull` / `hb push` via the strict `[[date:YYYY-MM-DD]]`
  placeholder syntax. Pull emits the placeholder only when
  `attrs.date` matches `YYYY-MM-DD` AND
  `datetime.date.fromisoformat` accepts it; otherwise it falls
  back to the existing `<!-- UNCONVERTED inline date -->` comment so
  the markdown never claims a round-trip the tool cannot honor. Push
  reverses the placeholder with calendar validation. Same
  post-process mechanism as the v0.1.2 card embed work. See the
  README's **Current limitations** for the migration note and
  forward-compat caveat.
- **Breaking** for anyone who wrote `[[date:YYYY-MM-DD]]` as literal
  text and pushed: it now becomes a real date inline node. Wrap such
  literals in backticks (`` `[[date:2026-05-26]]` ``) to keep them
  as text.
- Already-pulled `.md` files containing the prior
  `<!-- UNCONVERTED inline date -->` comment do NOT auto-upgrade.
  Re-pull (`hb pull <path>`) to refresh; otherwise push behavior
  matches v0.1.3 (date is lost).
- **docs**: new `create-failed` SOP in
  `skills/hbedit/references/errors.md` documenting the
  "card created, substitution failed" sub-case introduced by v0.1.2
  and generalized here. Critical for agents: do NOT retry `hb push`
  blindly — it creates a duplicate orphan.

## v0.1.3 — 2026-05-26

- **fix**: the `curl | sh` one-liner in README / README.zh / INSTALL.md
  pointed at the non-existent `main` branch. This repo's default branch
  is `master`, so anyone who copy-pasted the documented one-liner got a
  404 and an empty install. `install.sh -h` help text fixed as well.
- **docs**: `install.sh`'s refresh-behavior comment was inaccurate — it
  claimed to "discard local edits", but `git reset --hard` only touches
  tracked files; untracked files survive. Comment now reflects real
  behavior. (No code change.)

## v0.1.2 — 2026-05-25

- Card embeds (`card` nodes in ProseMirror) now round-trip through
  `hb push`. The placeholder `[[card:<UUID>]]` in markdown is
  converted back to a real card embed before the card is saved.
  Mechanism: post-process the ProseMirror that Heptabase's parser
  returns from `note create`, then `note save` the modified version.
  See the README's **Architecture → Card references round-trip**.
- **Breaking** for anyone who relied on `[[card:<UUID>]]` being
  preserved as plain text on push: it now becomes a real card embed.
  Wrap such literal text in backticks (`` `[[card:<UUID>]]` ``) to
  keep it as text.
- No behavior change for cards without any `[[card:` substring in
  their markdown: the new code path is gated behind a string check
  and skipped entirely.

## v0.1.1 — 2026-05-25

- Removed the strict `cli-version-unsupported` gate. The Heptabase CLI
  ships with the desktop app and updates with it, so a hard pin meant
  every upstream minor bump broke hbedit until we shipped a patch.
- New `cli-response-unexpected` error code: surfaced when `heptabase`
  stdout isn't parseable JSON (plain text, HTML, or empty where JSON
  was expected). Its SOP asks the user to compare `heptabase --version`
  against the new "Verified against" line at the top of `SKILL.md`
  (currently `0.3.x`) and to open an issue at the repo — phrased
  differently depending on whether the versions match or differ.
- `hb doctor` no longer blocks on CLI version; it still reports the
  detected version in `detail`.

## v0.1.0 — 2026-05-24

Initial release.

- `hb` CLI: `doctor`, `init`, `push`, `pull` (first-bind and smart-sync
  forms), `tag add` / `tag remove`, `unlink`.
- Block-ID transplant via scratch card — rewrite the middle of an existing
  card while preserving block IDs and any references pointing at them.
- Vault model: git-tracked `.hbedit/state.json` holds `path → cardId`
  bindings, per-machine `~/.hbedit/cache/<vaultId>/` holds sync state.
- Multi-machine workflow via committed `state.json` + smart-sync
  `hb pull <path>` (baseline / noop / updated / conflict).
- Conflict guard: `hb push` aborts with `content-conflict` and saves your
  local copy to `<path>.conflict.md` if the remote changed underneath you.
- Heptabase Agent Skill for Claude Code, Codex CLI, and opencode —
  natural-language triggering plus an explicit escape hatch for
  fire-and-forget cards.
- Stdlib-only Python (3.9+); zero pip dependencies.
