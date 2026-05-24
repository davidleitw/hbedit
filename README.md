# hbedit

> **Unofficial.** Not made by or affiliated with Heptabase. Built entirely on
> top of the official `heptabase` CLI — it never touches Heptabase's database
> or internal files.

📖 *[繁體中文 README →](./README.zh.md)*

## What's this for?

Here's the gap. The official `heptabase` CLI can **create** a card, and it can
**tack stuff onto the end** of one — but it can't actually rewrite the
**middle** of an existing card from plain text. So an AI agent can help you
*add* to your notes, but not *clean them up*.

hbedit fixes that. It lets you (or an agent) treat a Heptabase card like an
ordinary markdown file: pull it down, edit it however you like with normal
text tools, push it back. Same card, same identity — just rewritten.

So when you want to "tidy up that messy note", "reorder these sections", or
"fix the formatting across all my LeetCode cards" — that's what hbedit is
for. If you just want a brand-new card or to append a line, use the official
CLI directly; it's simpler.

## How do you use it?

hbedit ships as an **Agent Skill** — it works inside Claude Code, Codex
CLI, and opencode.

Once it's installed (see **[`INSTALL.md`](./INSTALL.md)**), you don't
run anything special. Just talk to your agent in plain language:

> "Pull my 'Reading list' card and reorganize it by topic."

The agent recognizes this as an hbedit job and takes over. Under the hood
it runs three commands:

```
hb doctor                  # check the environment is OK
hb pull <cardId> <vault>   # card  ->  a local .md file
#   ... edit the .md ...
hb push <file>             # .md   ->  back into the same card
```

You can also run those yourself in a terminal if you'd rather drive it by hand.

## How does it actually work?

The tricky part is **push**. Heptabase stores cards in its own internal format
(ProseMirror JSON), not markdown — so you can't just hand it your edited text.

hbedit's trick: it lets **Heptabase itself** do the conversion.

1. **Pull** — read the card, convert its internal JSON into clean markdown,
   and save it as a local `.md` file (with a tiny hidden header that remembers
   which card it belongs to).
2. **Push** — take your edited markdown and ask Heptabase to build a
   *throwaway* card from it. Now Heptabase has done the markdown→internal
   conversion for you. hbedit then "transplants" the original card's block
   IDs onto the matching blocks, saves that into the real card, and deletes
   the throwaway.

The upshot: hbedit never has to understand Heptabase's internal format
itself. And because the block IDs are preserved, links and references that
point into the card don't break.

Two safety nets worth knowing: every push first checks whether the card
changed underneath you — if it did, hbedit backs up your version to a
`.conflict.md` file instead of clobbering it. And it talks **only** to the
official `heptabase` CLI — never to Heptabase's database or files directly.

## Status

**v1** — pull / edit / push for note cards, with conflict detection and tag
sync. Install steps: [`INSTALL.md`](./INSTALL.md).

## Local development

Working on the skill itself? Load it into a Claude Code session without
installing globally:

```bash
claude --plugin-dir /path/to/hbedit
```

`--plugin-dir` loads the plugin **for that session only** — edit
`skills/hbedit/SKILL.md`, restart the session, you're testing the new
version. Nothing to clean up.
