---
name: baton-approve
description: >
  Approve a triaged work-item: advance it to the board's approved stage. Use when
  the user says "approve X", "aprobar idea", or confirms approval after triage.
license: MIT
compatibility: requires Python 3.11+, baton CLI (pipx install baton-board)
credential: agent
---

# baton approve

Approve a reviewed item — moves it to the "approve" stage (config alias, default
`Approved`). No branches here (that's `baton-start`).

## Workflow

1. **Verify** the item is in the pre-approval stage:
   ```bash
   baton show <id>          # check its stage
   baton stages             # the board's stages, in order
   ```
2. **Confirm priority** with the user (drives implementation order); adjust the
   priority label if needed:
   ```bash
   baton priority <id> --to high     # urgent | high | medium | low | none
   ```
3. **Approve** (advance to the approved stage):
   ```bash
   baton approve <id>
   ```
   `approve` resolves the stage from `config.stages.approve` (default `Approved`).
   For a non-standard board, use `baton advance <id> --to "<Stage Name>"`.

## Notes
- **State = board stage, not labels.** The approved backlog = items in the approved
  stage, ordered by priority label (`baton list --stage Approved`).
- Implementation starts with `baton-start`.
