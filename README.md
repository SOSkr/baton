# Baton

[![skills.sh](https://skills.sh/b/SOSkr/baton)](https://skills.sh/SOSkr/baton)

Work-item lifecycle from idea to shipped — **agent- and backend-agnostic**. Move
items through your board's stages (triage → approve → start → verify → ship) from
the CLI or from your agent's own skills, without hardcoding a single
project/field/option ID.

Three things swap independently: the **board** (Plane today), the **code host**
(GitHub today), and the **agent** (Claude Code and OpenCode today). Each is an
adapter or a symlink — never a rewrite.

## How it works

Two layers:
- **CLI `baton`** (this repo) — the mechanical ops: create/move/comment/close/list.
  A backend **adapter** (`plane`, ...) + **discovery** resolves IDs by name.
- **Skills** (`skills/`) — the judgment (triage scoring, priority, gates); they call `baton`.

The split is what makes both axes swappable. Skills hold no ids and no API calls, so a
new tracker is [a new adapter](docs/adapters/), not rewritten skills; the CLI holds no
prompts, so a new agent is a symlink into wherever that agent reads skills from.

## Architecture

```
baton/
├── src/baton/
│   ├── cli.py            # verbs: init/config/export/new/priority/verify/show/list/stages/groups/group/advance/approve/start/ship/comment/close/labels/body/doctor
│   ├── core.py            # class Baton — the one door: skills and cli.py talk to this
│   ├── base.py            # shared vocabulary: BatonError + Item/Group/Comment
│   ├── config.py          # .baton/config.yaml loader (walks up from cwd)
│   └── adapters/          # three roles — see docs/adapters/
│       ├── registry.py    # name -> class by file name; the only importer of a provider
│       ├── board/         # read-WRITE: where item state lives (plane.py)
│       ├── read/          # read-ONLY: old trackers, read once to migrate off (github_projects.py)
│       └── repo/          # the code host: permissions, branches, PRs (github.py)
├── docs/                  # adapters/ (how to write each family) · git-flow.md · design/
├── skills/                # the judgment layer, calls the CLI. Each skill's templates/ is a symlink into ↓
├── templates/             # item bodies (task/subtask/bug), epic description, triage verdict, PR review
├── commands/              # slash triggers for agents that use them (OpenCode)
├── hooks/                 # optional: post the PR link to the item without being asked
└── tests/
```

Templates live in one place (`templates/`) and each skill exposes the set it needs as
`skills/<skill>/templates` → a symlink. So they are findable as a group, and a skill
stays self-contained when it is symlinked into `~/.claude/skills/` — no build step,
nothing generated into git.

## Skills

The judgment layer — each wraps the CLI with a lifecycle verb. Install by
symlinking `skills/baton-*` (see [Setup for AI agents](#setup-for-ai-agents)).

| Skill | Description |
|---|---|
| [`baton-roadmap`](skills/baton-roadmap/SKILL.md) | Plan and read the roadmap **on the board** — epics with a target date, live progress. Never writes a document. |
| [`baton-new`](skills/baton-new/SKILL.md) | Discuss and register a new work-item on the board. |
| [`baton-triage`](skills/baton-triage/SKILL.md) | Review a work-item for viability/value/fit; scores it and posts the verdict. Doesn't change the stage. |
| [`baton-approve`](skills/baton-approve/SKILL.md) | Approve a triaged work-item: advance it to the board's approved stage. |
| [`baton-start`](skills/baton-start/SKILL.md) | Start implementation of an approved item: advance to In Progress, create the feature branch, drive it to Done/Shipped. |
| [`baton-verify`](skills/baton-verify/SKILL.md) | Validate a PR against its item: acceptance criteria met, Verification run, nothing touched that was out of scope. Reviews, never approves. |
| [`baton-ship`](skills/baton-ship/SKILL.md) | Take the integration branch to production and close the items that went out — PR, checks, merge, deploy verification. |
| [`baton-reject`](skills/baton-reject/SKILL.md) | Reject a work-item: close it with a reason comment. |
| [`baton-catch-up`](skills/baton-catch-up/SKILL.md) | Recover what already happened — on an item, or in another project you own — before asking anyone. |
| [`baton-bootstrap`](skills/baton-bootstrap/SKILL.md) | Step zero: create the repo, the board, protections and label axes, then wire baton to it. **Admin credential.** |
| [`baton-migrate`](skills/baton-migrate/SKILL.md) | Move an old GitHub Projects board onto the current one — items, stages, and the comment trail. |

## Config

Per-project `.baton/config.yaml` (walked up from cwd):

```yaml
backend: plane
target:
  base_url: https://plane.acme.com
  workspace: acme
  project: APP        # project identifier
stages:               # optional verb→stage aliases
  approve: Approved
  start: In Progress
  verify: Verify      # declaring this ALSO gates it — see below
  ship: Deployed
tokens:               # optional — env var NAMES per credential role (see below)
  agent: PLANE_API_KEY
  admin: PLANE_ADMIN_API_KEY
review_label: needs-review   # optional — see below

git:                  # optional — branch names; defaults shown. See docs/git-flow.md
  integration: develop
  production: master
repo: OWNER/REPO      # where the CODE lives — the board knows nothing about git
repos:                # multi-repo project: area-label value → repo
  engine: OWNER/app-engine
  web: OWNER/app-web
migrate_from:         # optional — the old board this project came from
  repo: OWNER/OLD
  project: 5
memory: app-a         # optional — this project's name in your session-memory store
projects:             # optional — sibling boards you can query with --project
  b: ../app-b         # relative to the PROJECT root (the dir holding .baton/)
```

Everything else (project node id, Status field id, stage option ids) is **discovered**.

Write it by hand, or let `baton init` do the mechanical part:

```bash
baton init --base-url https://plane.acme.com --workspace acme --board APP --repo OWNER/REPO
```

`init` records where an **existing** board is; creating the repo and the board is
[`baton-bootstrap`](skills/baton-bootstrap/SKILL.md). It refuses to overwrite a config
without `--force`.

## Credential roles

Two roles, because the thing that writes code should not be the thing that approves it —
the same separation Dependabot and Renovate rely on (GitHub does not let a PR author
approve their own PR).

| Role | Does | Board (plane) | Code host (github) |
|---|---|---|---|
| `agent` | items, comments, stages, branches, PRs — **everything in the normal lifecycle** | `PLANE_API_KEY` | `GH_TOKEN` |
| `admin` | create and administer projects, set protections, merge releases | `PLANE_ADMIN_API_KEY` | `GH_ADMIN_TOKEN` |

The board and the code host are two systems with two credentials each — `doctor` checks all four.

`agent` is the default; nothing needs `--as admin` except `baton-bootstrap` and the
merge step of a release. Tokens themselves **never** go in `config.yaml` — only the
env var names, so a project can point a role at a different variable.

```bash
baton doctor                  # one REAL read-only call per role, per system
baton --as admin <verb>       # opt in explicitly
```

`doctor` does not stop at "the variable is set" — a token that is merely present has
told you nothing. It runs one cheap read per credential against every system the
project uses (the board, and GitHub when the code lives elsewhere), reports each
independently, and keeps going after a failure so you see all of them at once.

On GitHub it reports the token's **permissions on the repo**, which is what makes the
split checkable: if the `agent` line comes back with `admin`, the separation is
decoration and doctor shows you so.

It also reports **branch protection per repo** — the one state that can be silently
wrong forever. In a multi-repo project it is easy to protect the repo you were standing
in and never notice the second one is open, and an open branch means an agent with push
rights skips the PR, the review and CI entirely. Reading it needs no admin, so the agent
credential can surface a hole it cannot fix.

Asking for `admin` when its variable is unset is an **error**, not a fallback: an admin
op silently running with agent rights either fails confusingly or quietly does less than
you think. The split only buys you anything if the admin credential is genuinely absent
from the agent's environment — if both sit in the same shell, it is decoration.

Declaring `stages.verify` turns it into a **gate**: baton refuses any move that jumps
over that stage, so an item cannot reach Done without passing through verification.
It gates the stage, not the work — two deliberate `advance` calls still get you
through — but skipping stops being an oversight nobody notices and becomes a move
recorded in the board's own history. Projects that do not declare it are never gated.

## Git flow

Work branches off the integration branch, reaches it by PR, and a release is a **direct
PR integration → production** — no release branches. Both branch names are config, so a
repo using `main`, or trunk-based with no integration branch at all, changes two lines
instead of editing globally-installed skills:

```yaml
git: {integration: develop, production: master}
```

`baton config git.integration` is what the skills and `ship-pr.sh` read. Branch names
follow `<prefix>/<id>-<slug>` and the **id is load-bearing** — the PR hook reads it to
link the PR back to the item. Full rules and where each one is enforced:
**[docs/git-flow.md](docs/git-flow.md)**.

`review_label` is applied only on **unexpected backward transitions** (e.g. `Approved → Review`), detected from the board's real stage order. Normal forward flow (new → review → approve → start → ship) is never flagged — that's the expected process. Backward moves get the label so a human can double-check what happened.

## Usage

```bash
baton init --base-url https://p --workspace w --board APP  # write .baton/config.yaml
baton doctor                        # validate config + credential roles + discovery
baton stages                        # the board's stages
baton new --title "Add dark mode" --label type:idea --stage Review
baton show 42
baton show 42 --comments             # + the comment trail (what others did)
baton --project b list --state all   # a sibling board, without cd-ing into it
baton list --stage Approved
baton groups                         # the roadmap: epics, progress, target dates
baton group 42 --to "Q3 auth"        # put an item in an existing epic
baton list --group "Q3 auth"         # what is still open in it = what is missing
baton advance 42 --to Approved
baton comment 42 --body "looks good"
baton close 42 --reason "superseded by #99"

baton priority 42 --to high          # the NATIVE field, not a priority: label
baton export --state all             # read the OLD board out (migrate_from in config)
```

## Example

```
$ baton doctor
baton 0.2.0
config: .baton/config.yaml
backend: plane   board: {'base_url': 'https://plane.acme.com', 'workspace': 'acme', 'project': 'APP'}
repos: engine=acme/app-engine, web=acme/app-web
token[agent] $PLANE_API_KEY:
  board (plane): OK — acme/APP — Acme App
  code acme/app-engine: OK — acme-bot on acme/app-engine — push, pull
  code acme/app-web: OK — acme-bot on acme/app-web — push, pull
token[admin] $PLANE_ADMIN_API_KEY:
  board (plane): OK — acme/APP — Acme App
  code acme/app-engine: OK — alice on acme/app-engine — admin, maintain, push, pull
  code acme/app-web: OK — alice on acme/app-web — admin, maintain, push, pull
branch protection:
  acme/app-engine: develop=protected · master=protected
  acme/app-web: develop=UNPROTECTED · master=protected
  ^ an unprotected branch means an agent with push rights skips the PR, the review and CI entirely.
    Fix: skills/baton-bootstrap/scripts/protect-branches.sh
stages: Review, Approved, In Progress, Deployed
epics (native groups): 2 on the board

$ baton show 42
#42 [Approved] Add dark mode
  https://github.com/OWNER/REPO/issues/42
  priority: medium
  labels: type:idea

$ baton show 42 --comments
#42 [Approved] Add dark mode
  https://github.com/OWNER/REPO/issues/42
  priority: medium
  labels: type:idea

  --- alice · 2026-07-27T10:04:11Z
  backend side landed in #51, toggle persists per user

  --- bob · 2026-07-27T14:22:03Z
  frontend still pending: the theme switcher flashes on first paint
```

`--comments` is what makes the item a shared channel: several people or agents
working the same item can read what the others already did instead of asking.

## Native first

Where the backend has a real field, baton writes the real field — not a label that
looks like one. A `priority:high` **label** is invisible to the board's own sorting,
filtering and grouping; the board's **priority field** is not.

```bash
baton new --title "..." --priority high     # native field
baton priority 42 --to urgent               # urgent | high | medium | low | none
```

Labels stay for the axes the backend has no field for — `type:`, `area:`. Which is
which is not a guess: `baton doctor` reports the native capabilities it can actually
reach, checked live, because editions and versions turn features off.

A backend without a given field keeps using a label. That fallback is the exception,
not the design.

### Optional capabilities

Everything in the `Adapter` contract is required except these. An adapter declares what
it has in `capabilities()`; `doctor` then **checks it live**, because an edition or a
version can turn a feature off after the code claimed it.

| Capability | Verbs it enables | Absent → |
|---|---|---|
| `groups` | `groups`, `group --to`, `list --group` | `baton-roadmap` says so and stops — it never simulates epics with labels and a hand-kept list |
| `priority` | `new --priority`, `priority --to` | falls back to a `priority:` label |

Writing a new adapter: implement the abstract methods, add the optional ones you can
back natively, and leave the rest — the base class already degrades with a clear error.
The names are deliberately backend-neutral, so `groups` maps to Plane *modules* or
GitHub *milestones* without either word reaching a skill. Full guides per family:
**[docs/adapters/](docs/adapters/)**.

## One board, several repos

A board project can cover more than one git repo, and the board knows nothing about
git. The `area:` label says which repo a piece of work belongs to, and `repos:` maps
it — so `baton-start` branches in the right place without asking.

An item whose work spans repos carries a **Checklist with one box per repo**. The box
is what says "this repo still owes something", and it is what stops the item closing
early. Several *items* under one outcome is a different thing — that is an epic.

## The roadmap is the board

There is no roadmap document, by design — a document has to be updated by hand, goes
stale immediately, and costs tokens to re-read. An **epic** is a native container with
a target date and a progress count the backend maintains itself: close an item and the
roadmap is already right.

```
$ baton groups
Q3 auth        [7/12 58%]  due 2026-09-30
Recorder v2    [0/4 0%]    due 2026-10-15
```

"Epic" is the word; on Plane it is stored as a **module**. `baton group <id> --to X`
refuses to create X — an epic is a deliberate act with a date, not a side effect of
filing a task. Items with no epic are out-of-roadmap by design, not an error.

Grouping is an **optional capability**: an adapter that has no native equivalent says
so instead of faking it with labels and a hand-kept list. `baton doctor` checks it live
rather than trusting a version number.

## Setup for AI agents

### Claude Code

Symlink skills into `~/.claude/skills/`:

```bash
ln -sf $PWD/skills/baton-* ~/.claude/skills/
```

Optionally install the [hooks](hooks/README.md) so the PR link reaches the item on
its own, instead of depending on the agent remembering.

### OpenCode

Symlink skills **and** commands:

```bash
# skills (procedural knowledge injected into system prompt)
ln -sf $PWD/skills/baton-* ~/.claude/skills/

# commands (/baton-new, /baton-start, /baton-ship, /baton-catch-up… — slash triggers in TUI)
ln -sf $PWD/commands/baton-* ~/.config/opencode/commands/
```

Plane MCP (optional — for direct Plane API access from the agent):

```json
// in ~/.config/opencode/opencode.json → "mcp"
"plane-mcp": {
  "type": "local",
  "command": ["npx", "-y", "@makeplane/plane-mcp-server"],
  "enabled": true,
  "environment": {
    "PLANE_API_KEY": "<your-plane-api-key>",
    "PLANE_API_HOST_URL": "<https://your-plane-instance>"
  }
}
```

### skills.sh (future)

```bash
npx skills add SOSkr/baton
```

Repo includes `skills.sh.json` for display grouping; `skills/` matches the expected layout.

## Requirements

- `gh` CLI, authenticated, with `project` scope (GitHub backend).
- Python ≥ 3.11: `pipx install baton-board` (or `uv run baton ...` from a clone).

The distribution is **`baton-board`** (`baton` was already taken on PyPI by an
unrelated iRODS wrapper); the command it installs is `baton`.

Releases publish themselves: `.github/workflows/publish.yml` fires when a GitHub
Release is **published** and uploads via **Trusted Publishing** (OIDC) — no API token
is stored anywhere. It refuses to build when the tag and `pyproject.toml`'s version
disagree, because a wrong version number on PyPI cannot be taken back.

## Roadmap

- **`baton search`** — embeddings-based retrieval, gated on scale (hundreds+ items
  cross-project). Not needed while `list --label/--stage` + backend full-text
  search covers it.
- **`baton prune`** — flag stale items (old + referencing closed/superseded
  issues) for review, cheaply, before a model looks at the flagged subset.
  Designed, not built: [docs/design/prune.md](docs/design/prune.md).

## Status

Plane board adapter and the GitHub code-host client done, both verified live.
Published: [`baton-board` on PyPI](https://pypi.org/project/baton-board/), and
`npx skills add SOSkr/baton` for the skills.

## License

MIT — see [LICENSE](LICENSE).
