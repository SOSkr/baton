# Baton

Work-item lifecycle over a board — **backend-agnostic**. Move items through your
board's stages (triage → advance → ship) from the CLI or via Claude Code skills,
against **GitHub Projects** today and **Plane** (or others) tomorrow, without
hardcoding a single project/field/option ID.

> Successor to the PROJ `idea-*` skills, generalized. See `P0-design.md`.

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
│       └── plane.py       # Plane — REST directo (no CLI oficial), discovery vía API
├── skills/                # baton-new/triage/approve/start/reject — el juicio, llaman al CLI
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
```

Everything else (project node id, Status field id, stage option ids) is **discovered**.

## Usage

```bash
baton doctor                        # validate config + backend discovery
baton stages                        # the board's stages
baton new --title "Add dark mode" --label type:idea --stage Review
baton show 42
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
```

## Requirements

- `gh` CLI, authenticated, with `project` scope (GitHub backend).
- Python ≥ 3.11. Run with `uv run baton ...` or `pipx install .`.

## Status

P1-P3 done: GitHub adapter, Plane adapter, discovery, core CLI — both verified live.
Packaging/publish (P4) pending. See `P0-design.md`.

## License

MIT — see [LICENSE](LICENSE).
