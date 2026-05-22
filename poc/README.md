# HeptaSync POC

Feasibility probe for a local-markdown ⇄ Heptabase sync layer built **only** on
the official `heptabase` CLI.

## Run

Heptabase desktop app must be open (Local CLI Server enabled).

```bash
python3 poc/poc.py
```

Stdlib only, no dependencies. Runs 21 experiments, writes
[`EXPERIMENTS.md`](./EXPERIMENTS.md) (a what / how / result log generated from
exactly what ran), and publishes that log + the v1 design to one Heptabase card
("HeptaSync POC — 實驗記錄"). Every *test* card created during the run is
trashed at the end.

## Files

| File | Role |
|---|---|
| `htb.py` | Subprocess wrapper over the `heptabase` CLI |
| `pm2md.py` | ProseMirror JSON → Markdown converter (the **pull** direction) |
| `transplant.py` | Block-ID transplant patcher (the **push** direction) |
| `harness.py` | Experiment framework; emits `EXPERIMENTS.md` |
| `experiments.py` | The 21 experiments (`E01`–`E21`) |
| `poc.py` | Runner — runs the suite and publishes the result card |
| `EXPERIMENTS.md` | **Generated** what / how / result log |
| `fixtures/` | Captured artifacts (discovered schema, round-tripped markdown) |

## Results — 21 experiments, CLI 0.3.0

20 pass, 1 warning. Full per-experiment detail is in `EXPERIMENTS.md`. Highlights:

- **Schema (E01)** — 15 ProseMirror node types; every block has a stable
  `attrs.id`; lists are flat; code lang in `attrs.params`, todo state in
  `attrs.checked`.
- **Pull (E02)** — `pm2md` round-trips the full vocabulary (tables, math,
  nested lists) losslessly.
- **Push (E06, E07, E13–E15, E18)** — the transplant strategy handles modify /
  delete / insert / reorder / marks-only / heading-level / rich-content edits;
  unchanged blocks keep their IDs; the end-to-end pull→edit→push cycle works.
- **`save` / `append` (E04, E05)** — block add/delete/reorder are reliable;
  untouched IDs never drift.
- **Optimistic locking (E08)** — `--content-md5` rejects stale writes;
  re-read-and-retry recovers.
- **Tags, whiteboards, journals (E09, E11, E16)** — readable/writable via the
  CLI, with documented caveats (no tag-delete; whiteboard position not
  controllable; journals are date-keyed).
- **Limits (E20, E21)** — ~600 writes/min (serialized); the **100,000-char**
  cap applies to `create` markdown *and* to `save` JSON — and JSON is several
  times larger than the markdown, so large cards become un-pushable.

### The one real limitation (E03)

Card-to-card references cannot be created from markdown — no `[[…]]` or link
syntax produces an inline `card` node. References must be authored in-app; a
sync daemon treats them as read-only.

## The two directions

- **Pull** (`pm2md.py`) — `note read` returns Heptabase's custom ProseMirror
  JSON; convert to Markdown.
- **Push** (`transplant.py`) — `note save` needs ProseMirror JSON, so let
  Heptabase convert the edited markdown (a scratch card), then transplant the
  original card's block IDs onto the surviving blocks. No hand-written
  Markdown→ProseMirror converter needed.

See `../v1/DESIGN.md` for how these feed the v1 sync model.
