---
description: Move an old GitHub Projects board onto the current board, comment trail included
---
Activate the baton-migrate skill: $ARGUMENTS

Follow the baton-migrate workflow: `baton export --from-github OWNER/REPO --project N
--state all` to read the source, confirm the stage map with the user BEFORE writing,
then per item create → comments (oldest first) → stage → close. Keep and print the
source→destination id map. Verify counts and spot-check comment trails before
reporting success.
