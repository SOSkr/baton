---
name: baton-new
description: >
  Discuss and register a new work-item on the board via `baton new`. Use when the
  user says "new item/idea/ticket", "nueva idea", "file X", "register X", or wants
  to formalize a concept into a tracked issue.
license: MIT
compatibility: requires Python 3.11+, baton CLI (pipx install baton)
---

# baton new

Register a work-item as a tracked issue on the configured board. `baton` handles
the backend (GitHub Projects / Plane / ...) and discovery — you do the **judgment**.
Config: `.baton/config.yaml` (backend, target, label axes, stage aliases).

## Workflow

1. **Clarify** if ambiguous: scope, the label axes your project uses
   (`config.labels.axes` — e.g. type/area/priority), and the initial stage.
2. **Write the body** (user story · context · proposal · acceptance criteria).
   Follow the project's language convention if it has one.
   *(Optional, multi-part items)*: if the item spans several areas/services, add a
   "Checklist" — one box per part with its owner + PR — so closure can gate on all
   parts. See `baton-start` for the gate.
3. **Create it**:
   ```bash
   baton new --title "..." --label type:idea --label priority:medium \
     --body "$(cat <<'EOF'
   ...body...
   EOF
   )" --stage "$(baton stages | head -1)"
   ```
   `--stage` sets the initial column (default first stage / your board's intake stage).
   The returned id is the item's identity.
4. **Confirm** the item URL to the user.

## Notes
- The board's canonical source is the issue; keep IDs stable.
- Labels are **axes** (type/area/priority), not state — **state = the board stage**,
  set via `baton advance` / `approve` / `start` / `ship`.
- Rich docs (spec-grade): if your project versions design docs, link one from the
  body — that's a project convention, not required by baton.
