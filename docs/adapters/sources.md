# Migration source adapters

**A source is an exit ramp.** Read-only, one direction, one time: it reads an old
tracker out so [`baton-migrate`](../../skills/baton-migrate/SKILL.md) can move that
work onto the real board. Then it is finished.

Reference implementation:
[`src/baton/adapters/sources/github_projects.py`](../../src/baton/adapters/sources/github_projects.py).

## Temporary by design

> A source has a **shorter life than the code around it**. Once the migration has run
> and been verified, delete the file. It is not a permanent second view of that system.

This is the part people get wrong. A source that survives its migration turns into
code nobody runs, drifting against an API nobody watches, until someone assumes it
still works. Write it, run it, verify the result, delete it. That is the whole arc.

If the same product later comes back as a *board*, that is a `boards/` adapter with a
full read-write contract — not this file grown up.

## There is no base class

One implementation, so an ABC would be guessing at a contract. What a source must
provide is defined by **what `baton-migrate` actually needs**, which is exactly four
reads:

```python
list_stages()                -> list[str]     # to build the stage map
list(*, state="all")         -> list[Item]    # the items
get(item_id)                 -> Item          # spot-checks
comments(item_id)            -> list[Comment] # the trail — the whole point
```

Return the same `Item` / `Comment` dataclasses from `base.py` as a board would. The
migration skill reads both sides in one vocabulary; that is the only reason this is
shaped like a board at all.

**There is no write path, and there must not be.** No `create`, no `set_stage`, no
`close`. If you find yourself wanting one, the answer is that migration is one-way: the
old board is being abandoned, not synced.

## The comments are the point

Titles and bodies survive anywhere — a CSV export has those. What does not survive,
and what is worth writing an adapter for, is **the thread**: the decisions, the
rejected approaches, the blocker somebody hit in March.

So:

- `comments()` is not optional. A source that cannot read comments is a source that
  loses the only thing that was hard to reproduce.
- Export **closed items too** (`--state all` is the default in `baton export`). Closed
  items carry the decisions that explain why the open ones look the way they do.
- Preserve `author` and `created_at`. The migration skill writes them into the comment
  body, because the destination will attribute every recreated comment to whoever ran
  the migration.

## Pagination and scale

An old board is a fixed, known size — you can look it up before you run. That makes a
hard cap acceptable *if it is visible*:

```python
# ponytail: first:100 — paginate if an old board ever exceeded it.
```

What is **not** acceptable is a silent truncation. A migration that quietly moved the
first 100 of 340 items looks successful and is a disaster. If you cap, either the
number is provably above the real count, or you log what was dropped.

Reading comments is one API call per item. That is slow and completely fine — it runs
once. Do not optimise it into a batch endpoint you then have to debug.

## Faithful export, no interpretation

A source **exports what is there**. It does not map, rename, normalise, or improve.

The mapping decisions — which old stage becomes which new state, which `priority:`
label becomes the native priority field, what happens to labels with no destination —
belong to `baton-migrate`, which shows them to a human for confirmation *before*
writing anything. An adapter that silently renames a stage has taken a decision the
user never saw.

## Wiring it up

1. Drop the module in `src/baton/adapters/sources/`.
2. Add a branch to `get_source` in [`adapters/__init__.py`](../../src/baton/adapters/__init__.py):

```python
def get_source(kind: str, **kw):
    if kind in ("github", "github_projects"):
        from .sources.github_projects import GitHubProjectsSource
        return GitHubProjectsSource(**kw)
    raise BatonError(f"unknown migration source {kind!r}")
```

3. Teach `cmd_export` in `cli.py` how to address it, and extend `migrate_from:` in
   config if it needs different coordinates.

## Where the coordinates live

**Which old board belongs to which project is project data**, so it lives in that
project's `.baton/config.yaml` — never in the skill, which is installed globally and
shared across every project:

```yaml
migrate_from:
  repo: OWNER/OLD
  project: 5
```

```bash
cd <the project>          # config is found by walking up from cwd
baton export --state all > /tmp/source.json
```

Flags override for a one-off. Credentials stay in the environment, as everywhere else.

## Checklist

- [ ] No write method exists, at all
- [ ] `comments()` implemented, oldest-first, with author and timestamp
- [ ] Closed items are exportable
- [ ] Any cap is documented and provably above the real count
- [ ] No renaming or normalising — that is the skill's job, with a human in the loop
- [ ] A deletion is scheduled: this file goes away when the migration is verified
