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

### Leave a trail on the item

Whoever picks this up next — another person, another agent, you in two weeks — can
read the board but not your session. **Comment at these three points, and only
these**: commits are too frequent to be worth reporting, and git already has them.

| When | What to write |
|---|---|
| PR opened | what it does, the PR link, what is still open |
| Blocked | what blocks it and who/what it waits on — the most valuable comment there is |
| Your part done (multi-part item) | what landed, what the next part needs to know |

```bash
baton comment <id> --body "Engine listo: endpoints del recorder + drift-check en CI.
PR https://github.com/acme/app/pull/77 · falta el consumidor en la app web."
```

Three lines beat thirty. Write what someone would otherwise have to **ask you** —
decisions taken, paths rejected and why, the surprise you hit. Not a changelog:
`baton-catch-up` cross-checks against `git log` for the facts.

Before writing, `baton show <id> --comments` — if it is already said, don't repeat it.

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
