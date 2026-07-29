---
name: baton-roadmap
description: >
  Plan and read the roadmap on the board itself — create epics with a target date,
  put items in them, and answer "what is there and what is missing" from live data.
  Use when the user says "roadmap", "crear épica", "qué falta para X", "what's left
  on <epic>", "plan the next quarter".
license: MIT
compatibility: requires Python 3.11+, baton CLI (pipx install baton), a backend with native grouping (Plane modules)
credential: agent
---

# baton roadmap

**Never write a roadmap document.** That is the whole point of this skill. A document
has to be updated by hand, goes stale the day after it is written, and costs tokens to
re-read every time someone asks a question the board already knows the answer to.

The roadmap **is** the board. An epic is a native container with a target date and a
progress bar the backend maintains itself: close an item and the roadmap is already
correct, with nobody touching anything.

> **Epic = module.** "Epic" is the word we use; in Plane it is stored as a *module*.
> Same object. Expect to see "Modules" in the Plane UI.

## Reading it — free, always current

```bash
baton groups                              # every epic: progress + target date
baton list --group "Q3 auth" --state all  # what is inside one
baton list --group "Q3 auth"              # only what is still open = what is missing
```

For a plain "how is X going", `baton groups` is the whole answer. Do not paraphrase it
into prose the user then has to trust — show the numbers.

## Creating an epic

Deliberate act, never a side effect. Needs a **name** and a **target date** — an epic
without a date is invisible to the timeline, which is most of what you came for.

1. Confirm with the user: name, target date, and what is in and out of scope.
2. Write the description from `{this skill's dir}/templates/epic.md`.
3. Create it on the board with the target date set as the module's own field.

`baton group <id> --to "<epic>"` **fails** if the epic does not exist. That is
deliberate: filing a task must not quietly invent a deliverable nobody agreed to.

## Putting items in an epic

```bash
baton group 42 --to "Q3 auth"
```

Not every item belongs to one. Work that comes in and goes straight out does not need
a deliverable wrapped around it — that is bureaucracy, not planning. **An item with no
epic is out-of-roadmap by design, not an error.** Never nag about it.

## The read-out — only what the board cannot answer itself

The backend already gives you progress and the timeline. Do not re-derive them. What
it does *not* cross-check, and what this skill is actually for:

| Check | How |
|---|---|
| Epic past its target date with items still open | `baton groups` + `baton list --group X` |
| Item In Progress with no PR in its comments | `baton show <id> --comments` |
| Epic at 100% whose "Done when" condition is unmet | read the epic description |
| Out-of-roadmap work, as information | items with no epic — report the count, do not flag it |

Report the ones that are true. An empty read-out is a good answer, not a failed one.

## Notes
- **Progress is a count, not a stage.** An epic is not "In Progress" — it is 7/12.
  Never substitute one for the other.
- If `baton groups` errors with *no grouping concept*, the backend has no native
  grouping and there is nothing to fall back to. Say so; do not simulate epics with
  labels and a hand-kept list — that is the document this skill exists to avoid.
- Sprints/cycles are a different axis (a slice of time, not a deliverable). baton does
  not model them.
