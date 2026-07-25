# baton

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

## Requirements

- `gh` CLI, authenticated, with `project` scope (GitHub backend).
- Python ≥ 3.11. Run with `uv run baton ...` or `pipx install .`.

## Status

P1: GitHub adapter + discovery + core CLI. Plane adapter (P3) and packaging/publish
(P4) pending. See `P0-design.md`.
