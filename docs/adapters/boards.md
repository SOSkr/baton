# Board adapters

**A board is where work-item state lives.** It is the only family that writes, the
only one with a real contract, and the only one baton's lifecycle verbs talk to.

Contract: [`src/baton/adapters/board/base.py`](../../src/baton/adapters/board/base.py) → `BoardBase`.
Reference implementation: [`src/baton/adapters/board/plane.py`](../../src/baton/adapters/board/plane.py).

## The one idea to internalise first

> **State is the board stage. Never a label.**

Labels are *axes* — `type:`, `area:` — orthogonal facts about an item. The stage is
where the item is in its life. An adapter that stores state in a label has broken the
model, and every skill downstream will produce nonsense. If your backend has no status
concept at all, `list_stages()` returns `[]` and the lifecycle verbs will fail loudly;
that is the correct outcome, not a reason to improvise.

## The data you return

Three dataclasses, all in `base.py`. You construct them; nothing else does.

```python
Item(id, title, url="", stage=None, labels=[], state="open", body="", priority=None)
Group(name, id="", target_date=None, total=0, done=0)
Comment(body, author="", created_at="")
```

`Item.id` is **the id a human types** — an issue number, a `PROJ-42` sequence — not an
internal UUID. Everything the CLI accepts is that id; resolving it to whatever the API
needs is your job, every time.

`Item.state` is `"open"` or `"closed"` and must be derived from **the backend's own
notion of done**, not from a stage name. Plane does this via state *groups*:

```python
_CLOSED_GROUPS = {"completed", "cancelled"}
...
state="closed" if group in _CLOSED_GROUPS else "open"
```

Matching on the literal name `"Done"` would break the first time someone renames a
column or writes the board in Spanish. Find the machine-readable equivalent.

## Required methods

### `probe() -> str`

One cheap read-only call proving **this credential** reaches **this backend**. Returns
a one-line human summary; raises `BatonError` if it does not.

`baton doctor` calls it once per credential role. Make it prove something specific —
that the configured project is actually *visible to this key*, not merely that the host
answers:

```python
def probe(self) -> str:
    rows = self._request("GET", f"{self.workspace}/projects/").get("results", [])
    hit = next((p for p in rows if p["identifier"].lower() == self.ident.lower()), None)
    if hit is None:
        raise BatonError(f"reached workspace {self.workspace!r} ({len(rows)} projects "
                         f"visible) but {self.ident!r} is not among them")
    return f"{self.workspace}/{hit['identifier']} — {hit['name']}"
```

A key scoped to the wrong project now fails in `doctor` instead of three verbs later.

### `list_stages() -> list[str]`

The board's stages **in board order**. Order matters: `cli._flag_backward` compares
indices to detect an unexpected backwards move (`Approved → Review`) and label it. Sort
by whatever sequence field the backend gives you; do not rely on insertion order.

### `create(title, body, labels, priority=None) -> Item`

Labels arrive as **names**. Resolve them to ids, creating any that do not exist yet if
the backend requires pre-registered labels. `priority` is one of `base.PRIORITIES`
(`urgent|high|medium|low|none`) — set the **native field** if you have one, and if you
do not, ignore it (see [optional capabilities](#optional-capabilities)).

### `get(item_id) -> Item` · `list(*, stage, label, state, group) -> list[Item]`

`list` filters are AND-ed. `state` is `open|closed|all`. `group` only means anything if
you report the `groups` capability — accept it and ignore it otherwise.

Filtering server-side is nicer but not required; filtering in Python after one page is
an acceptable shortcut **with a `ponytail:` comment naming the ceiling**.

### `comment(item_id, text)` · `comments(item_id) -> list[Comment]`

**Oldest first.** Many APIs return newest-first — sort. The comment trail is how the
next person or agent reconstructs what happened (`baton-catch-up` reads it), and a
reversed trail reads like a conversation played backwards.

If the backend stores HTML, strip it on the way out. A `Comment.body` full of `<p>` and
`&iacute;` is not readable by the thing that has to read it.

### `set_stage(item_id, stage)`

Match the stage **by name, case-insensitively**. Unknown name → `BatonError` listing
the real stages.

### `set_labels(item_id, add, remove)` · `edit_body(item_id, body)` · `close(item_id, reason)`

`close` should move the item to the backend's terminal state. The *reason* is posted as
a comment by `cli.cmd_close` before `close` is called — you do not need to write it,
but if your backend has a native "closed as not-planned" distinction, use it.

## Optional capabilities

Not abstract. The base class already raises a clear error, so **implement only what
your backend genuinely has natively**, and declare it:

```python
def capabilities(self) -> set[str]:
    return {"groups", "priority"}
```

| Capability | Implement | Skip it when |
|---|---|---|
| `groups` | `list_groups`, `create_group`, `set_group`, and honour `group=` in `list` | the backend has no deliverable/epic container with a date |
| `priority` | `set_priority`, accept `priority=` in `create`, read it in your item mapper | there is no native priority field — the `priority:` label stays |

**Do not fake a capability with labels.** A simulated group is a hand-kept list that
goes stale, which is the exact failure baton exists to remove. Declining is a supported
answer; `baton-roadmap` says so and stops.

`doctor` verifies claims by *calling* them, because an edition or licence tier can turn
a feature off after your code claimed it — that is how baton found out this Plane
instance has no issue types.

### Groups, concretely

`Group` is baton's neutral name for what skills call an **epic**: Plane *modules*,
GitHub *milestones*. `total`/`done` come from the backend so progress cannot drift.

`set_group` puts an item in an **existing** group and must **fail** if it does not
exist — creating one is a deliberate act with a target date, never a side effect of
filing a task. Error message should point at the roadmap skill.

## The creation half, and the one thing that silently breaks a board

`find_project` · `create_project` · `stage_groups` · `create_stage` · `delete_stage` are
what `baton bootstrap` calls. They are separate from everything above because everything
above assumes the board already exists — and a backend whose projects are created by a
human in a UI can still serve the whole lifecycle.

**`stage_groups()` is the one to get right.** baton derives an item's open/closed from
its stage's *lifecycle group*, not from the stage's name (`_CLOSED_GROUPS` in
[`plane.py`](../../src/baton/adapters/board/plane.py)). So a `Deployed` column created
under the group `backlog` leaves every shipped item reading as **open, forever** — and
nothing surfaces it, because the column looks right on the board.

Which is why creating a stage takes the group explicitly:

```python
ad.create_stage("Deployed", group="completed", color="#16a34a")
```

Where the group comes from is the role layer's business, not the provider's. A plain
`board_stages` list is inferred: everything before the stage `stages.start` points at is
`unstarted`, the last non-cancelled one is what done means, and a name like Cancelled is
a cancellation. That middle rule uses baton's own vocabulary rather than a new guess —
`Approved` means approved-and-not-begun, and filing it under `started` would show work as
under way that nobody has picked up. A mapping in the config overrides all of it. See
`wanted_stages` in [`board/__init__.py`](../../src/baton/adapters/board/__init__.py).

Two rules the role layer holds, so every backend inherits them:

- **Nothing existing is touched.** A stage whose group disagrees with the config is
  *reported*, never rewritten — changing a group changes what every item already sitting
  in that column counts as.
- **Extra stages are reported, not removed.** A fresh Plane project ships Backlog / Todo /
  Done. Deleting a stage on a board with work in it loses that work's history, so it takes
  `--prune` and a human.

## Wiring it up

1. Drop the module in `src/baton/adapters/board/`. **The file name is the config
   value** — `board/mytracker.py` is what `backend: mytracker` reaches.
2. Export the class: `ADAPTER = MyTrackerBoard` at the bottom of the module. That is
   the whole registration — there is no factory to edit and no list to keep in sync
   (see [`adapters/registry.py`](../../src/baton/adapters/registry.py)).
3. Add the name to `BACKENDS` in [`config.py`](../../src/baton/config.py), plus what
   its `target` needs before a config is worth writing:

```python
BACKENDS = ("plane", "kanboard", "mytracker")
_REQUIRED_TARGET = {..., "mytracker": ("base_url", "project")}
```

   **There is no credential var to add.** The name comes from the adapter ROLE —
   a board reads `$BOARD_TOKEN` whichever provider serves it — so a new backend
   inherits it. Writing `MYTRACKER_API_KEY` would put the provider back into the
   name, and then swapping boards means exporting a different variable for nothing.

4. Accept `(target: dict, token: str | None)` in `__init__`, validate `target` there,
   and raise `BatonError` naming the missing key.
5. Implement the creation half too, or `baton bootstrap` cannot set that backend up.
   `find_project()` returns `None` **only** for "not there" — an unauthorised lookup
   answered as `None` makes bootstrap create a duplicate project.

## Checklist before you call it done

- [ ] No id of any kind in `config.yaml` except human-typed names
- [ ] `probe()` proves the *configured project* is reachable, not just the host
- [ ] `list_stages()` is in board order
- [ ] `state` derives from the backend's done-concept, not a stage name
- [ ] `comments()` is oldest-first and plain text
- [ ] Every not-found raises `BatonError` listing what *does* exist
- [ ] `stage_groups()` reports the backend's real lifecycle group per stage
- [ ] `create_stage()` files the stage under the group it was given, not a default
- [ ] `find_project()` answers `None` for absent and raises for unauthorised
- [ ] `capabilities()` claims only what is really native
- [ ] A fake-server test covers the mapping and the error paths
- [ ] `baton doctor` is green against a real instance
