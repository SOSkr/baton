---
name: baton-start
description: >
  Start implementation of an approved work-item: advance it to In Progress, create
  the feature branch, and drive it to Done/Shipped. Use when the user says
  "start X", "implement idea", "empezar/implementar", "work on <id>".
license: MIT
compatibility: requires Python 3.11+, baton CLI (pipx install baton-board)
credential: agent
---

# baton start

Implement an approved item following the target repo's git flow. `baton` tracks the
stage; the code lives in the target repo (which may differ from where the item lives).

## Start
1. **Verify** approved: `baton show <id>` (check stage).
2. **Identify the target repo.** A single-repo project has one: its `repo:`. A
   multi-repo project keeps the map at its **projects root**, and the item says which
   entry with a `repo:` label:

   ```
   #42  type:bug  repo:app-engine
   ```

   Resolve the folder from the root's map — `baton doctor` at the root prints it — and
   `cd` there. **If the label names something the map does not have, stop and say so.**
   Do not fall back to the project's default repo: that is how work gets branched in
   the wrong place and nobody finds out until the PR.

   An item with no `repo:` on a multi-repo project should not exist — `baton new`
   refuses to create one — so finding one means the item predates the map. Ask which
   repo it is for; do not guess.

   Implementation happens in that repo, **not** where the board lives, and baton runs
   at the root of the repository.
3. **Feature branch** (in the target repo):
   ```bash
   git checkout "$(baton config git.integration)" && git pull
   git checkout -b "feat/<id>-<slug>"
   ```
   Prefix is one of `feat` · `fix` · `chore` · `hotfix` — the same words the commit
   types use. **The `<id>` is load-bearing**, not decoration: the optional PR hook
   reads it off the branch to post the PR link back to the item, and a branch without
   one silently never gets linked.
4. **Mark In Progress**: `baton start <id>` (config alias, default `In Progress`).
5. **Break down** the acceptance criteria and implement. If the body has an
   "Out of scope", stay out of it; if it has a "Verification", run it and report the
   result before advancing the stage.

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
- **Do not advance the item here.** A merged PR is not the same as an item that did
  what it said — `baton-verify` checks the diff against the acceptance criteria, the
  `Verification` and the scope boundary, and **it** is what moves the item on. Hand
  off to it; if the project declares `stages.verify`, baton refuses the jump anyway.
- On release/deploy: `baton ship <id>` (config alias, default `Deployed`), then close
  if that's your terminal state.

## Multi-part items (checklist)
If the item has a "Checklist" — one box per repo, or one box per phase of a wide
mechanical change — then on finishing **your** part: tick your box + link your PR
in the item body:
```bash
baton body <id> --body "$(...updated body with your box ticked...)"
```
**Do not** mark Done or close while any box is unticked — the item stays In Progress
until the last part lands. Only the final part → Done, then Ship/close. A single
part's release must not close the item if siblings remain.

**Phase boxes are ordered; repo boxes are not.** Never start a phase while an earlier
one is still open. In an expand–contract that is the entire point: run `contract`
before the migrate batches have landed and you delete something that still has
callers. The board does not enforce this — the order in the body and the test suite
do, so read the body before you pick a box.

## Notes
- Keep the item's stage current as work progresses (`baton list --stage @start`).
- **State = board stage, not labels.**
