# hbedit

> **Unofficial.** Not made by or affiliated with Heptabase. Built entirely on
> top of the official `heptabase` CLI — it never touches Heptabase's database,
> storage, or internal files.

📖 *[繁體中文 README →](./README.zh.md)*

## What it is

hbedit lets you (or an AI agent) edit an existing Heptabase card as if it
were a plain markdown file — pull it down, edit it, push it back. Same card,
same ID, links into it stay intact.

The simplest case: you want to ask Claude to fix a typo or reorder the
sections of a card you already have. The official `heptabase` CLI can
**create** cards and **append** to them, but it can't rewrite the middle
of an existing one from plain text. That gap is the entire reason hbedit
exists.

If all you want is to **make a new card** or **add one line at the bottom**,
just use the official CLI directly — it's simpler.

## What hbedit actually does

Heptabase stores card content internally as ProseMirror JSON. The official
CLI exposes `create`, `append`, and `read` — but it doesn't take edited
markdown and apply it as a content rewrite to an existing card. hbedit
fills that gap. On push, it hands your edited markdown to Heptabase as a
new "scratch" card, lets Heptabase's own engine produce the matching
ProseMirror JSON, copies the original card's block IDs onto the
corresponding blocks in that JSON, saves the result back onto the real
card, and trashes the scratch card. The card keeps its ID, and any
reference pointing into its blocks stays valid.

Pull, conflict handling, and the per-machine cache are covered in
[Architecture](#architecture--how-it-works) below.

## Install

You need:

- Python 3.9+ (stdlib only — no pip deps)
- The Heptabase desktop app, **v1.91.0 or newer**, running
- The official `heptabase` CLI enabled inside the app at
  **Settings → AI Features → CLI** (it ships with the desktop app — not
  npm, not brew). macOS adds it to PATH automatically; Windows users get
  a one-time PATH-setup command from the app. Full steps:
  <https://support.heptabase.com/en/articles/14715462-how-to-use-heptabase-cli>

Then pick your agent:

**Claude Code** (two lines, inside Claude):
```
/plugin marketplace add davidleitw/hbedit
/plugin install hbedit@hbedit
```

**Codex CLI** (one line):
```sh
curl -fsSL https://raw.githubusercontent.com/davidleitw/hbedit/master/install.sh | sh -s codex
```

**opencode** (one line):
```sh
curl -fsSL https://raw.githubusercontent.com/davidleitw/hbedit/master/install.sh | sh -s opencode
```

Verify in a new shell:

```sh
hb doctor
```

`"status": "ok"` means you're set. Anything else, follow the `detail` field
(usually: install `heptabase` CLI, update it to 0.3.x, or launch the desktop
app). Manual install steps and `curl | sh` audit instructions are in
[`INSTALL.md`](./INSTALL.md).

## How to use it

You don't run hbedit commands directly — just talk to your agent in plain
language. The skill recognizes when it should kick in. Here are the
scenarios it handles:

### 1. Edit an existing card

The main case. You have a card and want to change something inside it.

> *"In my React Hooks card, `useEffec` is a typo — fix it to `useEffect`,
> and reorder the sections so useState comes first."*

The agent runs `hb pull` to fetch the card as markdown, edits the file
locally, then `hb push` to send it back. The original card's block IDs are
preserved, so anything linking to that card still points at the right place.

### 2. Start tracking a local markdown file

You wrote some markdown in your vault and want it to live as a Heptabase
card you'll keep editing.

> *"I just added `notes/rust-ownership.md` to this vault — push it to
> Heptabase, I'll keep editing it from here."*

The agent runs `hb push`, which creates a new card and records the
`path → cardId` binding in `.hbedit/state.json`. From then on you edit the
local `.md` and `hb push` to sync.

### 3. Pick up editing on another machine (after git clone)

You committed `.hbedit/state.json` to git on machine A. On machine B you
clone the repo — the bindings come with the clone, but the per-machine
sync cache doesn't.

> *"Just cloned this repo on my laptop, I want to keep editing
> `docs/mm.md`."*

The agent runs `hb pull docs/mm.md` (single-arg "smart sync" form). If the
local file matches what's on Heptabase, you get `baseline-established` and
can start editing. If it diverged, you get a `conflict` with the remote
version dropped to `docs/mm.conflict.md` for you to reconcile — your local
copy is never silently overwritten.

### 4. Change tags on a card without disturbing others

> *"Add `algorithm` and `hashmap` tags to my Two Sum card."*

The agent runs `hb tag add`. Existing tags on the card stay exactly where
they are.

### 5. Just dump a card, no tracking needed

The escape hatch — when you want a one-off card and don't want hbedit to
get involved.

> *"Just dump today's meeting notes into a new Heptabase card —
> don't track it, fire and forget."*

The skill steps aside and the agent uses the base `heptabase note create`
instead. No `state.json` entry, no per-machine cache, no cleanup needed.

## Architecture & how it works

### It's an Agent Skill

hbedit ships as a Claude Code plugin / Agent Skill. The skill manifest
(`SKILL.md`) tells your agent when to use it and how; behind that is a
Python CLI called `hb`. No daemon, no server — just a stdlib-only Python
script that shells out to the official `heptabase` CLI.

### The vault model

Run `hb init` in a directory and that directory becomes a *vault*. Vault
state is deliberately split into two pieces:

- **`.hbedit/state.json`** — lives inside the vault, **committed to git**.
  Holds the `path → {cardId, tags}` bindings plus a `vaultId` UUID.
- **`~/.hbedit/cache/<vaultId>/`** — lives in your home directory, **never
  committed**. Per-machine sync state: `local-state.json` (file MD5s for
  drift detection) and `sidecar/<cardId>.json` (the original ProseMirror
  document for block-ID lookup).

Splitting them this way is what makes multi-machine work: clone the repo,
the bindings travel with it; the cache rebuilds itself on each machine the
first time you `hb pull <path>`.

### The block-ID transplant trick

This is the central technique. Heptabase stores cards as ProseMirror JSON
internally, not markdown. hbedit deliberately doesn't write its own
markdown ↔ ProseMirror converter (too much surface area to maintain), so
it lets **Heptabase do the conversion for it**:

1. **Pull**: read the card's ProseMirror JSON, convert it to clean
   markdown, write the `.md` file. The binding (which card it came from)
   lives in `state.json`, not in the file itself.
2. **Push**: take your edited markdown, ask Heptabase to build a
   throwaway "scratch" card from it (`heptabase note create`). Now you
   have fresh ProseMirror JSON, courtesy of Heptabase's own converter.
   hbedit then transplants the original card's block IDs onto matching
   blocks in the new JSON, saves the result back onto the real card, and
   trashes the scratch card.

Because the original block IDs survive the round-trip, anything linking
into the card (block references, embeds) stays valid.

### Card references round-trip

Heptabase cards can embed other cards — a `card` node in the underlying
ProseMirror, rendered as an inline or block-level reference in the UI.
`pm2md` serializes such an embed as the placeholder string
`[[card:<UUID>]]` in markdown. On push, hbedit converts the placeholder
back into a real `card` node, but it can't do that through
`heptabase note create` alone: that CLI's markdown parser doesn't know
about `[[card:<UUID>]]` and would keep it as plain text.

Instead hbedit uses a two-step trick:

1. Let `heptabase note create` parse the markdown normally. The
   placeholder lands as plain text inside the resulting ProseMirror.
2. Read that ProseMirror back, walk it, replace each
   `[[card:<valid-uuid>]]` text occurrence with a real `card` node,
   and `heptabase note save` the modified ProseMirror.

Step 2 only runs when the source markdown contains the literal
substring `[[card:`. Cards without any embeds get the original
single-call path — no extra round-trips.

Two consequences worth knowing:

- **If you write `[[card:<UUID>]]` as literal text** (e.g. in
  documentation about hbedit itself), wrap it in backticks
  (`` `[[card:<UUID>]]` ``) or put it inside a fenced code block.
  Unwrapped, hbedit will convert it on push — and if the UUID isn't
  a real card, you'll end up with a dangling reference in Heptabase.
- **The placeholder syntax is case-insensitive** on the way in but
  lowercased before storage. `[[card:ABC...]]` works.

`date` inline nodes round-trip via the same mechanism, using the
strict `[[date:YYYY-MM-DD]]` placeholder syntax (calendar-validated on
both ends; non-strict shapes such as time-bearing dates fall back to
`<!-- UNCONVERTED inline date -->` so the markdown never claims a
round-trip the tool cannot honor). `mention` nodes still don't
round-trip — they serialize as `<!-- UNCONVERTED inline mention -->`
and pushing loses them.

**Migrating older pulls:** `.md` files in your vault that still
contain `<!-- UNCONVERTED inline date -->` from a prior version do NOT
auto-upgrade. Re-pull the affected card (`hb pull <path>`) to refresh
the markdown with the new placeholder. If you push without re-pulling,
the date is lost — the same behavior as the prior version.

### Safety guarantees

Two things worth knowing:

1. **No internal access.** hbedit only talks to the official `heptabase`
   CLI. It doesn't open Heptabase's SQLite, doesn't read IndexedDB,
   doesn't touch any internal files. If Heptabase changes their storage
   format, hbedit just follows the CLI's compatibility window.
2. **Conflict guard.** Before every `hb push`, hbedit checks whether the
   remote card has changed since your last sync. If it has, your local
   version is moved to `<file>.conflict.md` and the push aborts with
   `content-conflict`. Nothing gets silently overwritten.

## Current limitations

- **Card embed round-trip works since v0.1.2** via the `[[card:<UUID>]]`
  placeholder syntax (see "Card references round-trip" above). Block-level
  cross-card *block references* (pointing at a specific block inside
  another card) still don't round-trip — only whole-card embeds.
- **Date inline nodes round-trip** via the `[[date:YYYY-MM-DD]]`
  placeholder syntax (same mechanism as card embeds; see "Card
  references round-trip" above). If you want literal
  `[[date:YYYY-MM-DD]]` text in your markdown, wrap it in backticks
  (`` `[[date:2026-05-26]]` ``). Future Heptabase additions such as
  time-of-day or timezone fall back to the `<!-- UNCONVERTED inline
  date -->` comment until a future placeholder revision adds support.
- **~100,000 character push ceiling.** Very large cards may hit a
  ProseMirror serialization limit and fail.
- **Note cards only.** Journal entries, PDFs, and whiteboards are not
  supported.
- **No `hb mv`.** Renaming a tracked `.md` file requires editing
  `state.json` by hand.
- **Windows is untested.** We have never run hbedit on native Windows
  (PowerShell / cmd). The `bin/hb` shim is a POSIX shell script; WSL
  should work, native Windows almost certainly does not without
  adjustments. CI only covers Linux and macOS. If you're a Windows
  user willing to try it, a report — or a PR — would be very welcome.

## Where to learn more

- [`INSTALL.md`](./INSTALL.md) — full install reference, manual install,
  curl-audit instructions
- [`skills/hbedit/SKILL.md`](./skills/hbedit/SKILL.md) — what the agent
  reads; decision table and full command list
- [`skills/hbedit/references/workflows.md`](./skills/hbedit/references/workflows.md)
  — step-by-step SOPs for edit / multi-machine / split / merge / conflict
- [`skills/hbedit/references/errors.md`](./skills/hbedit/references/errors.md)
  — per-error-code handling steps

### Working on hbedit itself

To load the plugin from a working copy without installing globally:

```bash
claude --plugin-dir /path/to/hbedit
```

`--plugin-dir` only applies to that one session — edit `SKILL.md`,
restart the session, and you're testing the new version. Nothing to
clean up afterward.

## Changelog

Versions follow [SemVer](https://semver.org). Newest first.

### v0.1.4 — 2026-05-26

- Date inline nodes (`date` nodes in ProseMirror) now round-trip
  through `hb pull` / `hb push` via the strict `[[date:YYYY-MM-DD]]`
  placeholder syntax. Pull emits the placeholder only when
  `attrs.date` matches `YYYY-MM-DD` AND
  `datetime.date.fromisoformat` accepts it; otherwise it falls
  back to the existing `<!-- UNCONVERTED inline date -->` comment so
  the markdown never claims a round-trip the tool cannot honor. Push
  reverses the placeholder with calendar validation. Same
  post-process mechanism as the v0.1.2 card embed work. See
  **Known limitations** for the migration note and forward-compat
  caveat.
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

### v0.1.3 — 2026-05-26

- **fix**: the `curl | sh` one-liner in README / README.zh / INSTALL.md
  pointed at the non-existent `main` branch. This repo's default branch
  is `master`, so anyone who copy-pasted the documented one-liner got a
  404 and an empty install. `install.sh -h` help text fixed as well.
- **docs**: `install.sh`'s refresh-behavior comment was inaccurate — it
  claimed to "discard local edits", but `git reset --hard` only touches
  tracked files; untracked files survive. Comment now reflects real
  behavior. (No code change.)

### v0.1.2 — 2026-05-25

- Card embeds (`card` nodes in ProseMirror) now round-trip through
  `hb push`. The placeholder `[[card:<UUID>]]` in markdown is
  converted back to a real card embed before the card is saved.
  Mechanism: post-process the ProseMirror that Heptabase's parser
  returns from `note create`, then `note save` the modified version.
  See **Architecture → Card references round-trip**.
- **Breaking** for anyone who relied on `[[card:<UUID>]]` being
  preserved as plain text on push: it now becomes a real card embed.
  Wrap such literal text in backticks (`` `[[card:<UUID>]]` ``) to
  keep it as text.
- No behavior change for cards without any `[[card:` substring in
  their markdown: the new code path is gated behind a string check
  and skipped entirely.

### v0.1.1 — 2026-05-25

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

### v0.1.0 — 2026-05-24

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

## License

MIT — see [`LICENSE`](./LICENSE).
