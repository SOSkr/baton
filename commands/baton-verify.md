---
description: Validate a PR against the work-item it implements — criteria, verification, scope
---
Activate the baton-verify skill to validate a PR against its work-item: $ARGUMENTS

Follow the baton-verify workflow: read the item with `baton show <id> --comments`,
read the diff with `gh pr diff <n> --name-only` then `gh pr diff <n>`, run the item's
Verification verbatim, check acceptance criteria + out-of-scope + unrequested changes,
post the filled `templates/pr-review.md` as a PR comment and a one-liner on the item.
Review only — never approve the PR. Advance to Done only on PASS.
