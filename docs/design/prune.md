# `baton prune` — design

**Status: designed, not implemented.** This document exists because the design was
worked out over several sessions, lived only in a roadmap file that was later deleted,
and was decaying into a two-line bullet in the README. Nothing here is built yet.

## The problem

Items sitting in an intake or review stage go stale in ways nobody notices:

- **superseded** — a later decision or item made this one wrong or redundant
- **already done** — it got implemented as part of something else
- **written against code that no longer exists** — a refactor moved the ground

Finding out which is which means reading and investigating each item, and that is
expensive precisely when there are enough items for it to matter. A board of 80 items
where 12 are stale costs 80 reads to find the 12.

**That cost is the whole reason prune exists.** The command does a cheap rule pass and
flags candidates; a model then reads **only the flagged subset**. It is not trying to
decide anything — it is trying to make the expensive reader look at 12 items instead
of 80.

## Why it is a verb *and* a skill

prune is the clearest illustration of baton's split:

| Layer | Does |
|---|---|
| **CLI `baton prune`** | the rule pass over metadata that already exists. Mechanical, cheap, no model. Outputs flagged ids with the reason each was flagged. |
| **Skill `baton-prune`** | reads the flagged subset and decides per item: still valid, needs revision, superseded → close. Judgment. |

Building only the skill means the model reads everything, which is the cost we are
avoiding. Building only the verb means flags nobody acts on.

## Tier 1 — rules over metadata that already exists

Recommended, and where to start. No pre-computation, no extra state, nothing to keep
in sync. Three signals, in descending order of strength as observed in practice:

**1. Dangling or superseded references — the strongest signal.** The item's body
references another item that is now **closed**, or a decision that a later one revised.
In practice this catches most real staleness, because a superseded item almost always
names the thing that superseded it.

**2. Age combined with a type/area label.** Old alone is weak — a good item can wait.
Old *plus* an axis that ages badly (an `area:` covering a subsystem that has since been
rewritten) is a real signal. This rule needs the project to say which axes age; it is
not derivable.

**3. `depends-on` pointing at a closed item.** ⚠️ **Not available today.** baton has no
dependency model — verified: there is no blocking concept in the CLI, the adapter
contract, or the item model, and Plane's v1 API exposes no relations endpoint (what it
documents as *Work Item Links* attaches external URLs). Implementing this rule requires
either that model or a `depends-on:<id>` label convention. Treat it as conditional, not
as part of the first cut.

The output is a list of ids plus **why each was flagged**. A flag without its reason
sends the reader back to reading everything, which defeats the point.

## Governance: prune always applies `review_label`

**This is the rule most likely to be lost, so it goes first in any implementation.**

> **prune applies `config.review_label` to every item it touches — forward, backward,
> close, or reclassification, without exception.**

The reason is not symmetry, it is auditability: prune runs **automatically and
unsupervised**. The user did not see any of those decisions and has to be able to review
all of them afterwards. An unlabelled automatic change is a change that disappears.

This is a **different trigger** from the auto-flag the CLI already has, and reusing the
existing path would be wrong:

| | Existing auto-flag (`cli.py:_flag_backward`) | prune |
|---|---|---|
| Fires on | **unexpected backward transitions only** (`Approved → Review`), detected against the board's real stage order | **every** change prune makes |
| Normal forward flow | never flagged — that is the expected process, the user is in the loop | still flagged — the user was not in the loop |
| How | derived from stage indices | applied explicitly |

Both write the same label. They must not share the code path: prune must not depend on
backward-detection, because most of what it does is *not* backward.

## Tier 2 — staleness fingerprint (gated)

Richer, and **only if Tier 1 proves insufficient.** At intake, store a fingerprint per
item:

```
{ key assumptions, components/decisions/files referenced, depends-on, one-line claim }
```

The fingerprint is **stable** — it describes the item. Reality **moves** — new decisions,
new code. Comparing one against the other detects staleness without re-reading the item.

The cost is generating it: once per item, at intake, by a model. That is a permanent tax
on every item to catch a problem that only some items have. Do not pay it until Tier 1
demonstrably misses things.

## Open decisions

- **What "old" means.** A config key, a flag, or derived from the board's own activity.
- **Whether prune ever closes anything on its own**, or only ever flags and leaves every
  state change to the skill. Leaning: flags only in the first cut — an unsupervised
  command that closes items is a much larger trust step.
- **Rule 3** stays blocked on the dependency question above.

## See also

- [`docs/adapters/`](../adapters/) — where a rule that needs backend data would live
- `README.md` § Roadmap — the one-line summary this document expands
