---
description: Ship what is on the integration branch to production and close the work-items that went out
---
Activate the baton-ship skill for: $ARGUMENTS

Check the board, verify the suite is green, run `scripts/ship-pr.sh` (PR head→base,
checks, merge, wait for the deploy-verification run), then `baton ship <id>` +
`baton close <id>` per item — only once the deploy is verified, never on merge alone.
