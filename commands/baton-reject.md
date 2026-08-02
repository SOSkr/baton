---
description: Reject a work-item: close it with a reason comment
---
Activate the baton-reject skill for: $ARGUMENTS

Confirm reject vs defer. If reject, run `baton advance <id> --to @cancel` and then `baton close <id> --reason "..."`. Both, in that order: `close` does not move the item, on purpose.
