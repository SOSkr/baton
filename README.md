# Baton

Work-item lifecycle over a board — **backend-agnostic**. Move items through your
board's stages (triage → advance → ship) from the CLI or via Claude Code skills,
against **GitHub Projects** today and **Plane** (or others) tomorrow, without
hardcoding a single project/field/option ID.

## How it works

Two layers:
- **CLI `baton`** (this repo) — the mechanical ops: create/move/comment/close/list.
  A backend **adapter** (`github`, `plane`, ...) + **discovery** resolves IDs by name.
- **Skills** (`skills/`) — the judgment (triage scoring, priority, gates); they call `baton`.

Swapping trackers = a new adapter, not rewritten skills.

## Architecture

```
baton/
├── src/baton/
│   ├── cli.py            # verbs: new/show/list/stages/advance/approve/start/ship/comment/close/labels/body/doctor
│   ├── base.py            # Adapter contract + Item dataclass — every backend implements this
│   ├── config.py          # .baton/config.yaml loader (walks up from cwd)
│   └── adapters/
│       ├── github.py      # GitHub Projects v2 — shells to `gh`, GraphQL discovery
│       └── plane.py       # Plane — direct REST (no official CLI), discovery via API
├── skills/                # baton-new/triage/approve/start/reject — the judgment layer, calls the CLI
└── tests/
```

## Skills

The judgment layer — each wraps the CLI with a lifecycle verb. Install by
symlinking `skills/baton-*` into your project's `.claude/skills/`.

| Skill | Description |
|---|---|
| [`baton-new`](skills/baton-new/SKILL.md) | Discuss and register a new work-item on the board. |
| [`baton-triage`](skills/baton-triage/SKILL.md) | Review a work-item for viability/value/fit; scores it and posts the verdict. Doesn't change the stage. |
| [`baton-approve`](skills/baton-approve/SKILL.md) | Approve a triaged work-item: advance it to the board's approved stage. |
| [`baton-start`](skills/baton-start/SKILL.md) | Start implementation of an approved item: advance to In Progress, create the feature branch, drive it to Done/Shipped. |
| [`baton-reject`](skills/baton-reject/SKILL.md) | Reject a work-item: close it with a reason comment. |

## Config

Per-project `.baton/config.yaml` (walked up from cwd):

```yaml
backend: github
target:
  repo: OWNER/REPO
  owner: OWNER        # project owner login (default: repo owner)
  project: 5          # ProjectV2 number
stages:               # optional verb→stage aliases
  approve: Approved
  start: In Progress
  ship: Deployed
review_label: needs-review   # optional — see below
```

Everything else (project node id, Status field id, stage option ids) is **discovered**.

`review_label` is applied only on **unexpected backward transitions** (e.g. `Approved → Review`), detected from the board's real stage order. Normal forward flow (new → review → approve → start → ship) is never flagged — that's the expected process. Backward moves get the label so a human can double-check what happened.

## Usage

```bash
baton doctor                        # validate config + backend discovery
baton stages                        # the board's stages
baton new --title "Add dark mode" --label type:idea --stage Review
baton show 42
baton show 42 --comments             # + the comment trail (what others did)
baton list --stage Approved
baton advance 42 --to Approved
baton comment 42 --body "looks good"
baton close 42 --reason "superseded by #99"
```

## Example

```
$ baton doctor
baton 0.1.0
config: .baton/config.yaml
backend: github
target: {'repo': 'OWNER/REPO', 'project': 5}
discovery OK — stages: Review, Approved, In Progress, Deployed

$ baton show 42
#42 [Approved] Add dark mode
  https://github.com/OWNER/REPO/issues/42
  labels: type:idea, priority:medium

$ baton show 42 --comments
#42 [Approved] Add dark mode
  https://github.com/OWNER/REPO/issues/42
  labels: type:idea, priority:medium

  --- alice · 2026-07-27T10:04:11Z
  backend side landed in #51, toggle persists per user

  --- bob · 2026-07-27T14:22:03Z
  frontend still pending: the theme switcher flashes on first paint
```

`--comments` is what makes the item a shared channel: several people or agents
working the same item can read what the others already did instead of asking.

## Requirements

- `gh` CLI, authenticated, with `project` scope (GitHub backend).
- Python ≥ 3.11. Run with `uv run baton ...` or `pipx install .`.

## Roadmap

- **`baton search`** — embeddings-based retrieval, gated on scale (hundreds+ items
  cross-project). Not needed while `list --label/--stage` + backend full-text
  search covers it.
- **`baton prune`** — flag stale items (old + referencing closed/superseded
  issues) for review, cheaply, before a model looks at the flagged subset.

## Status

GitHub and Plane adapters done, both verified live. Packaging/publish
(PyPI/skills registry) pending.

## License

MIT — see [LICENSE](LICENSE).
