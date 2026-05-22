# HeptaSync

A local-markdown ⇄ Heptabase sync layer built **only** on the official
`heptabase` CLI. Edit plain `.md` files locally; changes sync to Heptabase and
back, so agents (and people) can work on a normal markdown tree.

## Status — POC complete, v1 designed

| Folder | Contents |
|---|---|
| `poc/` | 21 feasibility experiments + the reusable pieces they validated |
| `v1/`  | The v1 design: folder layout, frontmatter schema, `DESIGN.md` |

Run the experiments (Heptabase desktop app must be open):

```bash
python3 poc/poc.py
```

Results go to `poc/EXPERIMENTS.md` and to a single Heptabase card —
**"HeptaSync POC — 實驗記錄"** — which also carries the full v1 design.

## What the POC proved

Both sync directions work through the official CLI alone:

- **Pull** — ProseMirror JSON → Markdown, lossless across Heptabase's full
  node vocabulary (`poc/pm2md.py`).
- **Push** — edited Markdown → Heptabase via the **transplant strategy**:
  Heptabase itself converts the markdown (a scratch card), then we transplant
  the original card's block IDs onto the surviving blocks so unchanged content
  keeps its identity (`poc/transplant.py`).

21 experiments, 20 pass; the one warning (E03) is a real limitation — card-to-card
references cannot be authored from markdown.

See `v1/DESIGN.md` for the design and `poc/EXPERIMENTS.md` for full results.

## Reusable pieces (validated in the POC)

`poc/htb.py` (CLI wrapper) · `poc/pm2md.py` (pull) · `poc/transplant.py` (push)
· `v1/frontmatter.py` (frontmatter schema).
