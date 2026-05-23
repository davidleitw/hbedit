# hbedit v2 redesign — design spec

**Date:** 2026-05-24
**Status:** Draft for review
**Author:** brainstorm session(davidleitw + Claude)

## Background

hbedit v0.1.0 ships a 「pull → edit → push」workflow that lets an AI agent
edit existing Heptabase cards as local markdown files. The card↔file
binding lives in a YAML frontmatter block at the top of each `.md`.

Four rounds of testing(see `TESTING-NOTES.md`)plus deeper use-case
analysis surfaced architecture-level issues that v0.1's design can't fix
with documentation alone:

1. **Frontmatter pollutes `.md` content.** Every tracked file carries a
   9-line YAML header; reading the file in any editor shows
   `schemaVersion / cardId / contentMd5 / syncedAt / tags` noise above the
   actual content.

2. **`contentMd5` creates fake git noise across machines.** `contentMd5`
   is「last-pulled-from-this-machine」cache state, not a property of the
   card. Committing it to git via frontmatter means every push on machine
   A and pull on machine B generates a 1-line `contentMd5: ...` diff that
   has nothing to do with the user's content.

3. **The「push existing local doc as a new card」use case is unclear.**
   v1 technically supports it(frontmatter with no `cardId` field → push
   creates a new card), but the workflow is non-obvious and easy for the
   agent to get wrong(agents in testing reached for `heptabase note
   create` instead).

4. **Multi-machine sync is not designed for.** When the user clones the
   project repo on a second machine, they get the `.md` files but not the
   `.hbedit/sidecar/` block-ID cache. v1 has no story for re-establishing
   the local sync state.

Since the project is at v0.1.0 with no public users, a clean break
(no migration path)is acceptable.

## Goals

Primary use cases this redesign must serve(in priority order):

1. **Edit the middle of an existing card** — the original hbedit value
   proposition. Pull → edit `.md` → push.
2. **Push a local markdown doc to Heptabase as a new card and maintain it
   long-term** — the「write a doc on machine A, then continue maintaining
   it via hbedit」case.
3. **Multi-machine sync** — `git clone` on machine B, edit the same `.md`,
   push to the same card.
4. **Tag editing** — add / remove tags on existing cards without touching
   content.
5. **AI-friendly UX** — all CLI output is structured JSON with stable
   error codes; SKILL.md tells agents how to react to each code.

## Non-goals

The following are explicitly out of scope for v2:

- **Status / dashboard commands**(`hb status`, `hb diff`)— individual
  users don't need a tracking dashboard for personal notes.
- **Bind without pull**(`hb bind`)— edge case; manual `state.json` edit
  works.
- **`--force` flags** — the seven core commands stay flag-free for v2.
- **Batch operations**(`hb sync` all, `hb tag set` multi-name)— YAGNI.
- **Migration from v1 frontmatter** — no released users, no migration.
- **Card-type support beyond `note`** — journal, pdf, etc. remain
  out-of-scope. Same as v1.

## Architecture

### Three-layer data separation

| Layer | Path | Purpose | In git? |
| --- | --- | --- | --- |
| Content | `<anywhere>/*.md` | User-edited markdown content, no frontmatter | ✅ commit |
| Public state | `.hbedit/state.json` | `path → {cardId, tags}` registry | ✅ commit |
| Local cache | `.hbedit/local-state.json` | `path → {contentMd5, syncedAt}` per-machine | ❌ gitignore |
| Block cache | `.hbedit/sidecar/<cardId>.json` | ProseMirror JSON for block-ID transplant | ❌ gitignore |

`.gitignore` is auto-populated by `hb init` to include
`.hbedit/local-state.json` and `.hbedit/sidecar/`.

### `state.json` schema

```json
{
  "schemaVersion": 2,
  "files": {
    "docs/auth.md": {
      "cardId": "a1b2c3d4-...",
      "tags": ["architecture", "auth"]
    },
    "notes/leetcode/[98]-validate-bst.md": {
      "cardId": "6470a72f-...",
      "tags": ["leetcode"]
    }
  }
}
```

- `files` keys are paths **relative to the vault root**(the directory
  containing `.hbedit/`).
- `tags` reflects「公開意圖」— what tags the user wants on this card.
  3-way merge with remote at push time.
- `schemaVersion: 2` distinguishes from v1's `{cards: {...}}` schema.
  Code rejects v1 schema with a clear error code.

### `local-state.json` schema

```json
{
  "schemaVersion": 1,
  "files": {
    "docs/auth.md": {
      "contentMd5": "90b422731ec8af8e9c2874ffc5ba384c",
      "localMd5": "f7c9a2b8...",
      "syncedAt": "2026-05-24T14:54:23Z"
    }
  }
}
```

- `contentMd5` is the remote ProseMirror md5 at last sync — used as the
  push lock to detect remote-side conflict.
- `localMd5` is the md5 of the local `.md` body at last sync — used to
  detect local-side uncommitted changes before pull overwrites them.
- Same path keys as `state.json`.
- Recreated lazily; missing on a fresh clone, populated by the first
  `hb pull <path>` on that machine.

### Vault discovery

A directory is an「hbedit vault」if it(or any ancestor)contains a
`.hbedit/` directory. CLI commands walk up from the given path to find the
vault root, like `git` walking up to find `.git/`.

### Card↔file identity

Bound exclusively via `state.json`. The `.md` file has no embedded
identity. Two consequences:

1. Renaming or moving an `.md` file breaks the binding(intentional — the
   user has to update `state.json` to reflect the new path).
2. Two paths can't reference the same `cardId`(state.json invariant
   enforced at write time).

### Multi-machine flow

**Machine A:**
```
edit docs/foo.md → hb push docs/foo.md
git add docs/foo.md .hbedit/state.json && git commit && git push
```

**Machine B(fresh clone):**
```
git clone <repo>
docs/foo.md  ← user content present
.hbedit/state.json  ← path↔cardId map present
.hbedit/local-state.json  ← MISSING(gitignored)
.hbedit/sidecar/        ← MISSING(gitignored)

# First operation on this machine must be:
hb pull docs/foo.md
# → reads state.json to find cardId
# → fetches remote, computes md5(remote-as-md)
# → compares against local file md5
# → if equal: writes local-state.json baseline, local file untouched
#             (action: "baseline-established")
# → if different: backs up local to .conflict.md, overwrites with remote,
#                 writes local-state.json (action: "conflict")
# → user / agent reconciles via the conflict SOP if needed

# After baseline established, edit / push works normally.
```

**Why smart compare matters.** Without it, a user who edits `docs/foo.md`
on machine B *before* their first `hb pull` would silently lose those
edits when the agent's SOP calls pull to "establish baseline". Smart
pull catches this case by routing through the conflict path instead of
clobbering local content.

## CLI surface

All commands output JSON to stdout. Exit code 0 on `status: "ok"`,
non-zero on `status: "error"`.

### Common output shape

```
{
  "command": "<name>",
  "status": "ok" | "error",
  ...command-specific fields...
}
```

Success:
```json
{"command":"push","status":"ok","action":"updated","cardId":"a1b2...","path":"docs/foo.md","detail":{"preserved":22,"edited":1,"inserted":2,"deleted":0,"reordered":0}}
```

Error:
```json
{"command":"push","status":"error","code":"no-baseline","path":"docs/foo.md","detail":"docs/foo.md is tracked but has no local sync state on this machine. Run `hb pull docs/foo.md` first."}
```

### Commands

#### `hb doctor`

Preflight environment check. Verifies `heptabase` CLI is installed,
version is in supported range(`0.3.x`), and the Heptabase desktop app
is running.

Output(ok): `{"command":"doctor","status":"ok","detail":"heptabase 0.3.0, desktop app reachable"}`

Error codes: `cli-missing`, `cli-version-unsupported`, `app-not-running`.

#### `hb init`

Initialize a vault in the current working directory. Creates
`.hbedit/state.json` with `{schemaVersion:2, files:{}}`, and a
`.gitignore` entry for `.hbedit/local-state.json` and `.hbedit/sidecar/`.

Behavior:
- cwd has its own `.hbedit/` → exits ok with detail `already initialized`
  (idempotent)
- cwd is *inside* another vault's tree(an ancestor has `.hbedit/`)
  → error `vault-nested`. User should `cd` to vault root, or remove the
  ancestor's `.hbedit/` if intentional.
- otherwise → create the vault.

#### `hb push <path>`

Sync local edits up to Heptabase. **Push touches content only — never
tags.** To change tags, use `hb tag add` / `hb tag remove` separately.

Behavior depends on whether `path` is registered in `state.json`:

- **Not registered** → create a new Heptabase card from the file's
  contents, write a new entry to `state.json`(with empty `tags`),
  write `contentMd5` + `localMd5` to `local-state.json`. Output
  `action: "created"`.
- **Registered** → require `local-state.json` baseline AND
  `.hbedit/sidecar/<cardId>.json` to exist(else `no-baseline`). Push
  as update using block-ID transplant from sidecar, locked on
  `contentMd5`. Refresh `contentMd5` + `localMd5` after success.
  Output `action: "updated"` with block counters from transplant
  report.

Note: `hb push` with no edits since last sync still does a full
round-trip(scratch card + transplant + save), but produces all-zero
change counters(only `preserved > 0`). It's not a fast-path noop.

Errors: `file-not-found`, `not-in-vault`, `no-baseline`,
`content-conflict`, `state-corrupt`, `card-not-found`(when remote
deleted the card between syncs).

#### `hb pull <cardId> <path>`(first-time pull)

Pull a card by ID to a path that's not yet tracked. Writes the `.md`
file, registers in `state.json`, writes `local-state.json`, writes
sidecar.

Errors: `not-in-vault`, `path-exists-untracked`(refuses to overwrite),
`card-not-found`(remote doesn't have the cardId).

#### `hb pull <path>`(subsequent pull / smart sync)

Refresh a tracked path from Heptabase. **Always uses smart compare** to
avoid clobbering local edits silently.

Behavior matrix(md5(local body) = LL, md5(remote-as-md) = RR,
local-state.json `localMd5` = LS):

| Case | local-state.json | LL vs LS | RR vs LS | Action |
| --- | --- | --- | --- | --- |
| Fresh clone, no divergence | missing | n/a | LL == RR | `baseline-established`(write local-state, no file change)|
| Fresh clone, divergence | missing | n/a | LL != RR | `conflict`(backup local, overwrite with remote, write local-state)|
| Both synced | present | LL == LS | RR == LS | `noop`(nothing to write, just refresh timestamp)|
| Remote changed, local clean | present | LL == LS | RR != LS | `updated`(overwrite local with remote, update local-state)|
| Local diverged from baseline | present | LL != LS | RR == LS | error `local-has-changes`(refuse;tell user to push or revert first)|
| Both diverged | present | LL != LS | RR != LS | `conflict`(backup local, overwrite, update local-state)|

Errors: `path-not-tracked`, `not-in-vault`, `card-not-found`,
`local-has-changes`.

#### `hb tag add <path> <name>`

Add a tag to the card bound to `path`. Semantics: fetch the card's
current tag set from remote, union with `{name}`, push the new tag list
to remote, refresh `state.json.files[path].tags` to match the final
remote state.

If `name` is suspiciously close to an existing tag(typo guard), aborts
with `tag-ambiguity` before any remote mutation.

Errors: `path-not-tracked`, `not-in-vault`, `tag-ambiguity`.

#### `hb tag remove <path> <name>`

Remove a tag from the card. Semantics: fetch remote tags, subtract
`{name}`, push, refresh `state.json`.

Errors: `path-not-tracked`, `not-in-vault`, `tag-not-on-card`.

## Error codes

| Code | When it happens | Agent's SOP(SKILL.md will spell this out) |
| --- | --- | --- |
| `cli-missing` | `heptabase` binary not on PATH | Tell user to install the Heptabase CLI(link to install docs) |
| `cli-version-unsupported` | CLI version outside `0.3.x` | Tell user to update the Heptabase CLI |
| `app-not-running` | Desktop app closed | Tell user to launch the Heptabase desktop app |
| `not-in-vault` | Operation requires a vault but cwd has no `.hbedit/` ancestor | Ask user「want me to run `hb init` here?」 |
| `file-not-found` | `path` doesn't exist on disk | Ask user to confirm the path / typo |
| `path-exists-untracked` | First-time pull would overwrite a non-tracked existing file | Tell user the path is occupied, ask for alternative path or removal |
| `path-not-tracked` | `state.json` has no entry for `path`(on pull / tag commands) | Ask user:「create new card?」(use push)or「link to existing card?」(get cardId, use `hb pull <cardId> <path>`) |
| `no-baseline` | Path is tracked, but the local cache is incomplete: either `local-state.json` lacks contentMd5 or `.hbedit/sidecar/<cardId>.json` is missing(fresh clone, or partial cache deletion) | Tell user「local cache for this card is missing, running smart pull to rebuild it」and run `hb pull <path>`(smart pull will safely establish baseline or surface conflict) |
| `content-conflict` | Remote changed since last pull | Tell user「remote was edited, local saved to `.conflict.md`」, present both versions, do a semantic merge with the user, then push the merged result |
| `tag-ambiguity` | New tag name looks like a typo of an existing tag | Show user the warning, ask「typo or intentional new tag?」 |
| `card-not-found` | The cardId in state.json doesn't exist on Heptabase(possibly trashed) | Tell user the card may have been trashed remotely; ask if they want to remove the state.json entry |
| `tag-not-on-card` | `tag remove` for a tag the card doesn't have | Inform user the tag wasn't on the card; no action needed |
| `cardId-already-tracked` | First-time pull for a cardId already mapped to a different path in state.json | Tell user the card is already linked to `<other-path>`; ask if they want to edit there instead, or unlink first |
| `state-schema-unsupported` | `state.json` has `schemaVersion` other than 2(e.g. v1 leftover from earlier installation) | Inform user the state file is from an older incompatible version; advise running `hb init` in a fresh directory or removing `.hbedit/` and starting over(no auto-migration in v2) |
| `state-corrupt` | `state.json` exists but is not valid JSON or violates schema invariants(e.g. duplicate cardId across paths) | STOP. Tell user the state file is corrupt; do not run any other hb command. Show them the corrupt content so they can fix by hand, or restore from git history if applicable |
| `vault-nested` | `hb init` called inside a directory tree where an ancestor already has `.hbedit/` | Tell user there's already a vault at `<ancestor-path>`; ask whether to use that one, or remove the ancestor's `.hbedit/` if intentional |
| `local-has-changes` | `hb pull` would overwrite a working file that has uncommitted local changes(local md5 doesn't match baseline localMd5) | Tell user the local file diverges from the last sync; ask whether to push these changes first, or discard them by running pull with an explicit confirmation(deferred — currently the only path is push or manually revert) |

## SKILL.md structure

The new `skills/hbedit/SKILL.md` follows this outline. Target length:
200-280 lines(within Anthropic's 500-line recommendation).

```
[1] Frontmatter
    name: hbedit
    description: (rewritten — extends heptabase-cli, no frontmatter
                  mention, surfaces new use cases)

[2] Header & unofficial disclaimer (~10 lines)

[3] When to use this skill vs heptabase-cli (~10 lines)
    Decision table.

[4] Preflight: hb doctor (~10 lines)
    Always-first step. JSON output shape.

[5] Concepts: how hbedit tracks files (~25 lines)
    Three-layer table (state.json / local-state / sidecar) +
    vault auto-discovery.

[6] Command reference (~80 lines)
    One subsection per command:
    - doctor, init, push, pull (×2 forms), tag add, tag remove.
    Each subsection: semantic + success JSON + error codes.

[7] Workflow SOPs (~100 lines)
    One subsection per use case. Each SOP is numbered steps. Use cases:
    a. Edit an existing card
    b. Push a local doc as a new card
    c. Continue editing on a second machine (post-git-clone)
       — explicitly handles smart pull outcomes:
         action="baseline-established" → safe, continue editing
         action="conflict" → reconcile via conflict SOP
         error "local-has-changes" → push current state first
    d. Read-only access to a card
    e. Edit tags
    f. Multi-step composites: split / merge / batch
       (built from primitives, not a single command)
    g. Plan-before-push (embedded as a step in each destructive SOP)
    h. Recover from state-corrupt (don't auto-fix, present file to user)

[8] Error code SOPs (~40 lines)
    Mirror of the error codes table above, but with the agent's
    response steps spelled out per row.

[9] Limitations (~10 lines)
    - No card-to-card references from markdown
    - ~100k char push limit
    - No remote event stream (changes seen only on pull)
    - Note cards only (no journal, pdf, etc.)
```

### `description` field rewrite

Target description(within Anthropic's 1024 char limit, 3rd person,
includes both「what」+「when to use」+ pushy):

```
Edit Heptabase cards as plain local markdown files — push existing
local docs as new cards, edit the middle of existing cards, sync
across machines via git, and manage tags. Each file is bound to a card
via .hbedit/state.json (the markdown stays clean, no frontmatter).
Reach for hbedit when the user wants to: (a) maintain a local
markdown file alongside its Heptabase card, (b) edit existing card
content from a CLI / agent, (c) sync the same card across multiple
machines, or (d) add/remove tags on existing cards. The base
`heptabase` CLI only creates new cards or appends — use hbedit
whenever the work involves an existing card, ongoing maintenance, or
multi-machine workflows.
```

## Code changes summary

### Files removed

- `skills/hbedit/scripts/frontmatter.py`(~168 lines)
- `tests/test_frontmatter.py`

### Files heavily modified

- `skills/hbedit/scripts/hbedit.py`
  - Remove all frontmatter parse/write logic
  - Add `init` command
  - Add `tag add` / `tag remove` subcommands
  - Split `pull` into 「first-time(`<cardId> <path>`)」 and
    「subsequent(`<path>`)」 dispatch
  - Update `push` to write state.json + local-state.json instead of
    frontmatter
  - Standardize all output to JSON
- `skills/hbedit/scripts/vault.py`
  - `state.json` schema v1 → v2
  - Remove `find_file_by_card_id`(replaced by `state.json` lookup)
  - Add `local_state` reader / writer module(may be split into a new
    file)

### Files added

- `skills/hbedit/scripts/local_state.py`(~50 lines)
  - Read / write `.hbedit/local-state.json`

### SKILL.md rewritten end-to-end

New structure outlined above.

### Net LoC change

Estimated **net negative**(removed code > added code), since
frontmatter parsing was the biggest module and state.json operations
are simpler.

## Test strategy

Per davidleitw's request: tests are **manual**, planned upfront, run
against a real Heptabase desktop after implementation. No automated
integration tests for the round-trip(unit tests for pure-function
modules are still appropriate).

### Unit test scope

Replace `test_frontmatter.py` with:

- `test_state.py` — state.json read/write/upgrade-reject
- `test_local_state.py` — local-state.json read/write

Keep existing pure-function tests where they still apply
(`test_pm2md.py`, `test_transplant.py`, etc.).

### Manual integration tests

| # | Test case | Verifies |
| --- | --- | --- |
| TC1 | `hb init` in empty dir → `.hbedit/state.json` with `schemaVersion:2` exists, `.gitignore` updated | init |
| TC1b | `hb init` again in same dir → `action:"already-initialized"`, no changes | init idempotent |
| TC1c | `hb init` in sub-dir of an existing vault → error `vault-nested` | nested-vault guard |
| TC2 | Create `docs/foo.md`, `hb push docs/foo.md` → JSON `action:"created"` with cardId, file unchanged on disk(no frontmatter), state.json entry written, local-state.json entry written | push-as-new |
| TC3 | `hb pull <cardId> docs/bar.md` → file written, state / local-state / sidecar all populated | first-time pull |
| TC3b | `hb pull <cardId>` where the cardId already maps to another path in state.json → error `cardId-already-tracked` | unique-mapping guard |
| TC4 | Edit `docs/foo.md`, `hb push docs/foo.md` → JSON `action:"updated"` with block counters(`inserted>0` or `deleted>0` or `edited>0`), local-state.json contentMd5 and localMd5 updated | round-trip edit |
| TC5 | `hb push docs/foo.md` without edits → ok, all change counters are 0(only `preserved>0`)── confirms push is a full round-trip, not a fast-path noop, but produces no net change | push with no edits |
| TC6 | Modify card in Heptabase desktop, `hb pull docs/foo.md`(state.json has entry, local body matches old baseline, remote diverged) → `action:"updated"`, local file overwritten, local-state refreshed | smart pull: remote-changed case |
| TC6b | `hb pull docs/foo.md` with no edits anywhere → `action:"noop"`, file untouched | smart pull: both-synced case |
| TC6c | Edit `docs/foo.md` locally(no push), then `hb pull docs/foo.md` → error `local-has-changes` | smart pull: refuse to clobber local |
| TC7 | `hb pull <cardId> existing-untracked-file.md` → error `path-exists-untracked` | overwrite guard |
| TC8 | Fresh clone simulation: delete `.hbedit/local-state.json` AND `.hbedit/sidecar/`, leave working file matching remote, `hb pull docs/foo.md` → `action:"baseline-established"`, working file untouched, local-state.json written | smart pull: fresh-clone OK |
| TC8b | Fresh clone simulation: also edit the working file before pull, `hb pull docs/foo.md` → `action:"conflict"`, `.conflict.md` created with local edits, working file overwritten with remote | smart pull: fresh-clone divergence(the data-loss-prevention case) |
| TC8c | Fresh clone, attempt `hb push docs/foo.md` without pull → error `no-baseline` | push-without-baseline guard |
| TC9 | Concurrent edit: edit local, also edit remote via Heptabase desktop, `hb push docs/foo.md` → error `content-conflict`, `.conflict.md` backup created, working file re-pulled | conflict during push |
| TC10 | `hb tag add docs/foo.md leetcode` → state.json tags updated, remote tags updated. Then `hb tag add docs/foo.md leetcod` → error `tag-ambiguity`(no remote mutation) | tag add + typo guard |
| TC10b | `hb tag remove docs/foo.md leetcode` → state.json and remote both lose the tag. Then `hb tag remove docs/foo.md nonexistent` → error `tag-not-on-card` | tag remove |
| TC11 | Various `hb doctor` scenarios: ok / cli-missing / app-not-running | preflight |
| TC12 | End-to-end multi-machine sim: machine A push, simulate clone(delete local-state/sidecar), `hb pull <path>`(baseline-established), edit, `hb push` works | multi-machine flow |
| TC13 | Corrupt `.hbedit/state.json`(write malformed JSON), any hb command → error `state-corrupt`, no recovery attempted | corruption guard |
| TC14 | Run `hb push docs/foo.md` from a sub-directory inside the vault tree(not from vault root)→ command works, vault discovered by walking up | vault discovery |
| TC15 | `hb push` outside any vault → error `not-in-vault` | vault-required guard |
| TC16 | Manually edit state.json to `schemaVersion: 1`, any hb command → error `state-schema-unsupported` | schema version guard |

Each TC includes:
- Setup commands(bash)
- Action(`hb <cmd>`)
- Expected JSON output(matched against a stored fixture or pattern)
- Expected file system state after

### Out-of-scope for testing

- Tag concurrent edits across machines(rare; user accepts manual merge)
- Conflict during `tag add`(rare; existing tag-ambiguity already
  guards similar)
- Network partition / partial failures(Heptabase CLI is local-only)

## Open questions / decisions deferred to implementation

- **Exact JSON output schema details** — field names, nesting depth.
  Will be locked in during implementation review.
- **CLI argv parsing** — `hb pull <cardId> <path>` vs `hb pull <path>`
  ambiguity: use argument count(2 args = first-time, 1 arg =
  subsequent). Confirmed during design.
- **`.gitignore` modification policy** — `hb init` appends to existing
  `.gitignore` if present, creates new one if absent. Idempotent
  (don't duplicate lines).
- **State file write atomicity** — write to temp file + rename, to
  avoid corrupting state.json on a crash mid-write.
- **Line ending normalization** — local `.md` files written by hb pull
  always use LF;`hb push` is robust to CRLF on read(normalizes
  internally before md5/transform)to avoid spurious diffs across OSes.
- **State.json invariant enforcement** — at every write, the CLI
  validates(a)`schemaVersion == 2`,(b)no two paths map to the same
  cardId. Violations emit `state-corrupt`.
- **Single-writer assumption** — hbedit assumes at most one hb command
  is mutating a given vault at a time. Concurrent agents on the same
  vault are not supported in v2(no locking). The user / agent must
  serialize.
- **Renaming a tracked `.md` file** — not a CLI operation in v2. The
  user / agent manually edits `state.json` to update the path key. If
  this proves common in practice, consider adding `hb mv` in v3.

## Implementation plan

To be created in a separate file via writing-plans skill after this
spec is approved.
