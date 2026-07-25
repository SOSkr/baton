---
name: baton-start
description: >
  Start implementation of an approved work-item: advance it to In Progress, create
  the feature branch, and drive it to Done/Shipped. Use when the user says
  "start X", "implement idea", "empezar/implementar", "work on <id>".
---

# baton start

Implement an approved item following the target repo's git flow. `baton` tracks the
stage; the code lives in the target repo (which may differ from where the item lives).

## Start
1. **Verify** approved: `baton show <id>` (check stage).
2. **Identify the target repo** (from the item's area/service label or the user).
   Implementation happens **there**.
3. **Feature branch** (in the target repo):
   ```bash
   git checkout develop && git pull && git checkout -b feature/<id>-<slug>
   ```
4. **Mark In Progress**: `baton start <id>` (config alias, default `In Progress`).
5. **Break down** the acceptance criteria and implement.

## During
- Commits reference the item id; PR body references the item (cross-repo items don't
  auto-close on merge).
- Update any linked doc alongside the code.

## Finish
- On merge to the integration branch: `baton advance <id> --to Done` (or your board's
  done stage).
- On release/deploy: `baton ship <id>` (config alias, default `Deployed`), then close
  if that's your terminal state.

## Multi-part items (checklist)
If the item has a "Checklist" (several areas/services), on finishing **your** part:
tick your box + link your PR in the item body:
```bash
baton body <id> --body "$(...updated body with your box ticked...)"
```
**Do not** mark Done or close while any box is unticked — the item stays In Progress
until the last part lands. Only the final part → Done, then Ship/close. A single
part's release must not close the item if siblings remain.

## Notes
- Keep the item's stage current as work progresses (`baton list --stage "In Progress"`).
- **State = board stage, not labels.**
