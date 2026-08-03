# Writing a baton adapter

baton has **three adapter families**. They are not variations on one idea — they
answer three different questions, so they have three different shapes and three
different lifespans.

| Family | Question | Access | Lifespan | Guide |
|---|---|---|---|---|
| **board/** | Where does work-item *state* live? | read **and** write | permanent | [boards.md](boards.md) |
| **read/** | What are we migrating *off*? | read **only** | temporary — delete it after the migration | [read.md](read.md) |
| **repo/** | Where does the *code* live? | read, via the host's API | permanent, small | [repos.md](repos.md) |

```
src/baton/adapters/
├── _gh.py                     # shared `gh` shell-out (repo + read)
├── registry.py                # name -> class; the ONLY module that imports a provider
├── board/
│   ├── base.py                # BoardBase — the contract
│   ├── __init__.py            # the role's rules: get(), verb_stage, require_verify, ...
│   └── plane.py               # a provider; `ADAPTER = PlaneBoard`
├── repo/  {base.py, __init__.py, github.py}
└── read/  {base.py, __init__.py, github_projects.py}
```

Every role package is the same shape: `base.py` is the contract, `__init__.py` is the
role's own rules plus its `get()`, and every other file is one provider **whose file
name is the value a config carries**. `core.Baton` is the only caller above them.

## Picking the family

Ask what the thing is *for*, not what product it is. GitHub appears in two families at
once and that is correct: as a **source** it is an old board being read out one last
time; as a **repo** it is where the code lives. Same API, same credential, two
unrelated jobs.

The dividing line that matters is **write access**. A source is not a board with
methods missing — it is a thing that must never write. Keeping them in separate
directories makes that a structural fact instead of a runtime question, so nobody has
to ask "can this one write?" before calling it.

Each family now has its own ABC (`board/base.py`, `repo/base.py`, `read/base.py`), and
that is a **reversal of an earlier rule here** worth explaining: for a long time only
boards had one, on the grounds that with a single implementation an interface is a guess
at a contract. What changed is that there is something to satisfy now — the role's rules
in `<role>/__init__.py` are written against the ABC and nothing else, so the interface
is what makes "this rule holds for every board" a checkable claim instead of a comment.
For `read/`, which has one implementation and a deliberately short life, the ABC exists
as documentation: it is the answer to "how do I write one of these".

Three layering rules are enforced by [`tests/test_frontier.py`](../../tests/test_frontier.py),
not by good intentions: a role's rules may not import a provider, nothing under
`adapters/` may import `core`, and no adapter prints.

Which backend the board should be is not a matter of taste either: it was measured, and
the method and the numbers are in
[docs/design/board-backends.md](../design/board-backends.md) — including the test no
vendor documentation answers, which is what a body looks like after a human merely
*opens* the item.

## Rules that apply to all three

**1. Nothing is hardcoded.** No project id, no field id, no status option id, no label
id. Everything is addressed by **name**, and the adapter *discovers* the internal ids.
This is the single most important rule in the codebase — it is why a config file is
five lines instead of a pile of UUIDs, and why moving to another workspace does not
mean editing code. Cache discovery per-instance (see `PlaneBoard._discover_states`),
never across runs.

**2. Credentials come from the environment, never from config.** `config.yaml` holds
the *name* of an env var, never a token. One variable per **adapter role** — `board`,
`repo`, `migration` — so the name stays put when the provider changes, and what that
credential may do is the host's answer, not baton's. See
[Credentials](../../README.md#credentials).

**3. Every failure is a `BatonError` with a message a human can act on.** Not a
traceback, not `KeyError`. Include what was being looked for and what does exist:

```python
raise BatonError(f"stage {name!r} not found. Board stages: {', '.join(names) or '(none)'}")
```

That second half — *what does exist* — is what turns a dead end into a fix.

**4. Nothing prints.** Adapters return data or raise; `cli.py` owns all output. An
adapter that prints cannot be used by `--json`, by a skill, or by a test.

**5. Leave a `ponytail:` comment on any deliberate shortcut**, naming the ceiling and
the upgrade path:

```python
# ponytail: linear scan over one page of issues; fine at board scale,
# revisit with a server-side filter if boards grow past a page.
```

## Testing

No adapter test may touch the network. The pattern is a **fake server keyed by
(method, path)** that routes the way the real API does, injected by replacing the
adapter's own request helper — so the adapter's logic is what is under test, not
`urllib`:

```python
ad = PlaneBoard({...})
fake = FakePlane()
ad._request = lambda method, path, body=None, params=None: fake.request(
    method, path, body, params)
```

Copy the shape from [`tests/test_plane_adapter.py`](../../tests/test_plane_adapter.py).
Test the mapping decisions, not the HTTP: name→id resolution, stage ordering,
open/closed derivation, comment ordering, and every error path that is supposed to be
a `BatonError`.

Run everything with `python -m pytest -q` from the repo root.
