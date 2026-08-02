---
name: baton-reject
description: >
  Reject a work-item: close it with a reason comment. Use when the user says
  "reject X", "rechazar idea", or decides an item won't move forward.
license: MIT
compatibility: requires Python 3.11+, baton CLI (pipx install baton-board)
credential: agent
---

# baton reject

Reject an item — close it as the terminal state, with the reason recorded. Rejection
is distinct from **defer** (defer = leave it open, lower its priority, or keep it in
an early stage).

## Workflow

1. **Confirm** with the user: reject (drop it) vs defer (keep for later). If defer,
   don't close — adjust priority or leave the stage, and stop here.
2. **Reject** — name the stage, then close:
   ```bash
   baton advance <id> --to @cancel
   baton close <id> --reason "Rejected: <why — out of scope / superseded by #NN / not worth the cost>"
   ```
   `baton close` posts the reason as a comment, then closes the item.

   **Both commands, in that order, and the first is not optional.** `close` marks the
   item closed; it does NOT move it, because a verb that picks a stage on its own is
   how a *rejected* item once ended up in **Deployed** — the closing state a backend
   happened to list first. So the caller says where it goes, always.

   That is the same shape `baton-ship` uses (`baton ship` then `baton close`), and the
   asymmetry between the two was the bug: ship named its stage and reject did not.
   Without the `advance`, a rejected item reads `closed` while still sitting in the
   intake column, and every board view shows it as work someone might pick up.

## Notes
- Prefer a rejection comment that explains the blocker over silence — a future
  re-intake can reference this item.
- **Multi-part items**: rejecting closes the whole item regardless of checklist
  boxes — reject means the item itself is dropped, not that parts finished. (The
  completion gate in `baton-start` is for closing on *completion*, not rejection.)
