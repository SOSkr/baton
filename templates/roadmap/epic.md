<!-- The description of an EPIC. In Plane this is stored as a MODULE — same thing,
     different word: "epic" is what we say, "module" is what the board calls it, and
     the target date + progress bar you get for free are the reason we use it.
     Keep this short. It is a container, not a spec — the specs are the items. -->

## Outcome
What is true when this epic is done, in one paragraph. Not a task list — the items
are the task list, and `baton list --group "<name>"` already prints them.

## Why now
The problem this closes, and what it unblocks.

## In scope
- <the deliverables this epic owns>

## Out of scope
- <what someone will reasonably assume is included and is not>

## Done when
Every item closed AND <the cross-cutting condition no single item covers — migration
finished, old path deleted, docs updated>. Without this line an epic hits 100% and
still is not done.

<!-- The target date is NOT written here — it is the module's own field, which is
     what the board reads to draw the timeline. `baton groups` shows it. -->
