---
name: baton-catch-up
description: Recover what already happened — on a work-item, or in another project you own — before asking anyone. Use when the user says "what did engine do", "catch me up on X", "ponete al día con", "what's the state of #42", or when the task touches a project/item someone else (or another session) has been working on.
license: MIT
compatibility: requires Python 3.11+, baton CLI (pipx install baton-board)
credential: agent
---

# baton-catch-up

Someone already did part of this. Find out **what**, before asking them — or
before redoing it.

Two layers. The board is always available; session memory only sometimes. Use
both when you can, and **say which ones you actually got** — a thin answer that
looks complete is worse than an honest gap.

| Layer | Answers | Scope |
|---|---|---|
| **Board** (always) | what *we* did — decisions, blockers, PRs, current stage | shared across people and machines |
| **Session memory** (if present) | what *I* did — the detail of how it got done | local to this machine |

## Mode A — a specific item

```bash
baton show <id> --comments
```

Item, stage, labels, and the comment trail: what each person or agent did, what
they hit, what they left open. Then follow the PRs referenced in the comments if
you need the code.

## Mode B — a project, no item id

Most "what did X do" questions have no item number. Start from the board:

```bash
baton --project <name> list --state all      # what moved there
baton --project <name> show <id> --comments  # then drill into what looks relevant
```

`--project` takes a key of `projects` in `.baton/config.yaml`, or a path. Run
`baton doctor` to see which siblings are declared. Without it you can only see
the board of the project you are standing in.

## Layer 2 — session memory (optional)

If a session-memory store is available (e.g. claude-mem exposing search tools),
query it for the same project and topic. It holds the working detail the board
never gets: what was tried and abandoned, why a path was rejected, which file
turned out to be the real problem.

Map board project → memory project with `memory:` in the config:

```yaml
memory: app-a        # this project's name in the memory store
```

`baton doctor` prints it. If there is no store, or no `memory:` key, skip this
layer — and **say so in the answer**.

## Rules

- **Search before asking.** Asking the user to paste context they already
  produced is the last resort, not the first.
- **Absence of results is not absence of work.** Comments get written after the
  fact, and memory lags an in-flight session by minutes. Say "nothing recorded
  yet" — never conclude "nothing was done".
- **Cross-check when it matters.** The board has the agreed state, memory has
  the detail, and `git log` / `gh pr list` in the target repo have the facts.
  Where they disagree, the repo wins.
- **Report the layers you used.** "Board only — no memory store for this
  project" tells the reader how much to trust the answer.

## Output

A short summary aimed at the task that triggered the lookup: what was done, what
is open, what to watch out for. Not a dump of comments.
