---
name: baton-reject
description: >
  Reject a work-item: close it with a reason comment. Use when the user says
  "reject X", "rechazar idea", or decides an item won't move forward.
license: MIT
compatibility: requires Python 3.11+, baton CLI (pipx install baton)
---

# baton reject

Reject an item — close it as the terminal state, with the reason recorded. Rejection
is distinct from **defer** (defer = leave it open, lower its priority, or keep it in
an early stage).

## Workflow

1. **Confirm** with the user: reject (drop it) vs defer (keep for later). If defer,
   don't close — adjust priority or leave the stage, and stop here.
2. **Reject** — comment the reason + close:
   ```bash
   baton close <id> --reason "Rejected: <why — out of scope / superseded by #NN / not worth the cost>"
   ```
   `baton close` posts the reason as a comment, then closes the item.

## Notes
- Prefer a rejection comment that explains the blocker over silence — a future
  re-intake can reference this item.
- **Multi-part items**: rejecting closes the whole item regardless of checklist
  boxes — reject means the item itself is dropped, not that parts finished. (The
  completion gate in `baton-start` is for closing on *completion*, not rejection.)
