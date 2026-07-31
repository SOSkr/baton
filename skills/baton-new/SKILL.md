---
name: baton-new
description: >
  Discuss and register a new work-item on the board via `baton new`. Use when the
  user says "new item/idea/ticket", "nueva idea", "file X", "register X", or wants
  to formalize a concept into a tracked issue.
license: MIT
compatibility: requires Python 3.11+, baton CLI (pipx install baton-board)
credential: agent
---

# baton new

Register a work-item as a tracked issue on the configured board. `baton` handles
the backend (GitHub Projects / Plane / ...) and discovery — you do the **judgment**.
Config: `.baton/config.yaml` (backend, target, label axes, stage aliases).

## Workflow

1. **Clarify** if ambiguous: scope, the label axes your project uses
   (`config.labels.axes` — e.g. type/area/priority), and the initial stage.
2. **Pick the template** for what this actually is — read it from
   `{this skill's dir}/templates/`:

   | Template | When |
   |---|---|
   | `task.md` | the default — one deliverable. Has the optional Checklist, per repo or per phase. |
   | `subtask.md` | one part of a bigger item; inherits the parent's user story |
   | `bug.md` | something is broken — the repro is the verification |

   Ambiguous? Ask — a bug filed as a task loses the repro.

   **An epic is not one of these.** It is a native container on the board carrying its
   own target date and live progress, not an item body, so `baton new` cannot create
   one. Several items under one outcome go into an epic via `baton-roadmap`; each of
   those items is still filed here.

   **Size it against both tests.** One `Verification` that proves the *whole* thing
   done — two unrelated checks are two items. And one fresh context window for
   whoever implements it — one thing too wide to hold at once is still too big, and
   an agent that compacts halfway through ends up contradicting its own start.
   The exception is a wide mechanical change that no slice can make green on its
   own: that is **one** item with a Checklist box per phase, not several items.
3. **Write the body** from that template. Fill a section or delete it — placeholder
   text left in is worse than no section. Follow the project's language convention
   if it has one. `Verification` and `Out of scope` are optional for human-executed
   items and expected for agent-executed ones: `baton-verify` reads them, and
   without them a reviewer re-derives the whole diff to find out if it worked.
4. **Create it**:
   ```bash
   baton new --title "..." --label type:idea --priority medium \
     --body "$(cat <<'EOF'
   ...body...
   EOF
   )" --stage @triage
   ```
   **`--priority`, never a `priority:` label.** It writes the board's own field, the
   one the board sorts and filters by; a label the board cannot sort by is a note to
   yourself. `baton doctor` lists which fields are native here.
   `--stage` sets the initial column (default first stage / your board's intake stage).
   The returned id is the item's identity.
5. **Confirm** the item URL to the user.

## Notes
- The board's canonical source is the issue; keep IDs stable.
- Labels are **axes** (type/area/priority), not state — **state = the board stage**,
  set via `baton advance` / `approve` / `start` / `ship`.
- Rich docs (spec-grade): if your project versions design docs, link one from the
  body — that's a project convention, not required by baton.
