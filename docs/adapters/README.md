# Writing a baton adapter

baton has **three adapter families**. They are not variations on one idea — they
answer three different questions, so they have three different shapes and three
different lifespans.

| Family | Question | Access | Lifespan | Guide |
|---|---|---|---|---|
| **boards/** | Where does work-item *state* live? | read **and** write | permanent | [boards.md](boards.md) |
| **sources/** | What are we migrating *off*? | read **only** | temporary — delete it after the migration | [sources.md](sources.md) |
| **repos/** | Where does the *code* live? | read, and shell-outs | permanent, tiny | [repos.md](repos.md) |

```
src/baton/adapters/
├── _gh.py                        # shared `gh` shell-out (repos + sources)
├── __init__.py                   # the three factories
├── boards/plane.py
├── sources/github_projects.py
└── repos/github.py
```

## Picking the family

Ask what the thing is *for*, not what product it is. GitHub appears in two families at
once and that is correct: as a **source** it is an old board being read out one last
time; as a **repo** it is where the code lives. Same API, same credential, two
unrelated jobs.

The dividing line that matters is **write access**. A source is not a board with
methods missing — it is a thing that must never write. Keeping them in separate
directories makes that a structural fact instead of a runtime question, so nobody has
to ask "can this one write?" before calling it.

There are deliberately **no `Source` / `Repo` base classes**. With one implementation
each, an interface is a guess at a contract. The directory carries the rule until a
second implementation shows what they actually have in common. Only `boards/` has an
ABC (`baton.base.Adapter`), because it has a real contract that `cli.py` calls into.

## Rules that apply to all three

**1. Nothing is hardcoded.** No project id, no field id, no status option id, no label
id. Everything is addressed by **name**, and the adapter *discovers* the internal ids.
This is the single most important rule in the codebase — it is why a config file is
five lines instead of a pile of UUIDs, and why moving to another workspace does not
mean editing code. Cache discovery per-instance (see `PlaneAdapter._discover_states`),
never across runs.

**2. Credentials come from the environment, never from config.** `config.yaml` holds
the *name* of an env var, never a token. Two roles exist — `agent` and `admin` — and
which one you get is decided by the caller, not by the adapter. See
[credential roles](../../README.md#credential-roles).

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
ad = PlaneAdapter({...})
fake = FakePlane()
ad._request = lambda method, path, body=None, params=None: fake.request(
    method, path, body, params)
```

Copy the shape from [`tests/test_plane_adapter.py`](../../tests/test_plane_adapter.py).
Test the mapping decisions, not the HTTP: name→id resolution, stage ordering,
open/closed derivation, comment ordering, and every error path that is supposed to be
a `BatonError`.

Run everything with `python -m pytest -q` from the repo root.
