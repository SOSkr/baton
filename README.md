# Baton

[![skills.sh](https://skills.sh/b/SOSkr/baton)](https://skills.sh/SOSkr/baton)

Work-item lifecycle from idea to shipped — **agent- and backend-agnostic**. Move
items through your board's stages (triage → approve → start → verify → ship) from
the CLI or from your agent's own skills, without hardcoding a single
project/field/option ID.

Three things swap independently: the **board** (Kanboard or Plane), the **code host**
(GitHub today), and the **agent** (Claude Code and OpenCode today). Each is an
adapter or a symlink — never a rewrite.

New here? **[Getting started](#getting-started)** goes from nothing to a green
`baton doctor`.

## Getting started

From nothing to a green `baton doctor`. This walks a **Kanboard** board and a GitHub
repo, which is the pair the project runs on; Plane differs only in `target` and the
credential name.

**1. Install**

```bash
pipx install baton-board          # the command it installs is `baton`
```

`gh` also has to be installed and authenticated — baton drives GitHub through it.

**2. Get the two credentials**

| | Where | Export as |
|---|---|---|
| Board | Kanboard → *Settings → API*, or your own profile → *API* | `BOARD_TOKEN` |
| Code | GitHub → a token with `repo` scope | `REPO_TOKEN` |

Tokens live in your environment, never in `config.yaml`. The file holds env var
**names** only, so a project can point a role at a different variable.

**3. Point baton at them**

```bash
cd your-repo
baton bootstrap --board "Your Board" --base-url https://board.example.com \
                --repo owner/repo --check ci
```

Three things to know about that command, because each one is a wall the first time:

- **`--check` is not optional** — pass the name of the CI check that must pass before a
  PR can merge, or `--no-checks` to say you deliberately want none. baton refuses to
  guess: a protection with no required check lets a red PR merge, and one naming a
  check that does not exist makes every PR **hang** waiting for a status that never
  arrives. Use ONE aggregated name, never a matrix job like `test (3.11)`.
- **It is idempotent, and it looks before it creates.** If the board and repo already
  exist — someone added you to a board, which is the common case — it finds them,
  writes the config, and reports `existed` instead of making a second one. Re-run it
  after a half-failure; that is the resume command.
- **It needs the admin credential** to set branch protections. Without one it does the
  rest and tells you what it skipped, rather than pretending.

**4. Check it, before trusting it**

```bash
baton doctor
```

This is the acceptance test for everything above. It does not stop at "the variable is
set" — it makes one real read per credential against every system, and keeps going
after a failure so you see all of them at once.

**5. Wire your agent**

```bash
git clone https://github.com/SOSkr/baton /tmp/baton
ln -sf /tmp/baton/skills/baton-* ~/.claude/skills/
```

See [Setup for AI agents](#setup-for-ai-agents) for OpenCode and the optional hooks.

Then: `baton new`, or ask your agent for the `baton-new` skill.

## How it works

Two layers:
- **CLI `baton`** (this repo) — the mechanical ops: create/move/comment/close/list.
  A backend **adapter** (`kanboard`, `plane`) + **discovery** resolves IDs by name.
- **Skills** (`skills/`) — the judgment (triage scoring, priority, gates); they call `baton`.

The split is what makes both axes swappable. Skills hold no ids and no API calls, so a
new tracker is [a new adapter](docs/adapters/), not rewritten skills; the CLI holds no
prompts, so a new agent is a symlink into wherever that agent reads skills from.

## Architecture

```
baton/
├── src/baton/
│   ├── cli.py            # verbs: bootstrap/init/config/export/new/priority/show/list/stages/groups/group/advance/approve/start/verify/ship/release/comment/close/labels/body/doctor
│   ├── core.py            # class Baton — the one door: skills and cli.py talk to this
│   ├── base.py            # shared vocabulary: BatonError + Item/Group/Comment
│   ├── config.py          # .baton/config.yaml loader (walks up from cwd)
│   └── adapters/          # three roles — see docs/adapters/
│       ├── registry.py    # name -> class by file name; the only importer of a provider
│       ├── board/         # read-WRITE: where item state lives (kanboard.py, plane.py)
│       ├── read/          # read-ONLY: old trackers, read once to migrate off (github_projects.py, plane.py)
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
| [`baton-reject`](skills/baton-reject/SKILL.md) | Reject a work-item: move it to the cancel stage and close it, with the reason recorded. |
| [`baton-catch-up`](skills/baton-catch-up/SKILL.md) | Recover what already happened — on an item, or in another project you own — before asking anyone. |
| [`baton-bootstrap`](skills/baton-bootstrap/SKILL.md) | Step zero: create the repo, the board, its stages, protections and label axes, then wire baton to it. **Admin credential.** |
| [`baton-migrate`](skills/baton-migrate/SKILL.md) | Move an old board onto the current one — items, stages, and the comment trail. The source is any provider under `adapters/read/`. |

## Config

Per-project `.baton/config.yaml` (walked up from cwd). The required half:

```yaml
adapters:                          # which provider serves each role
  board: kanboard                  # `backend:` is the older spelling of this key
target:                            # THE KEYS DEPEND ON THE BOARD — see below
  base_url: https://board.acme.com # kanboard: instance URL, no /jsonrpc.php
  project: APP                     # kanboard: the project's NAME
  user: admin                      # kanboard: who comments are attributed to
repo: acme/app                     # where the CODE lives; the board knows no git
```

`target` is the one block that is not the same for everyone, because a board's
coordinates are a board's business:

| Key | `kanboard` | `plane` |
|---|---|---|
| `base_url` | instance URL, without `/jsonrpc.php` | instance URL |
| `project` | the project's **name**, as the board shows it | the identifier — the `APP` in `APP-123` |
| `workspace` | — *(Kanboard has none)* | workspace slug |
| `api_user` | whose credential `$BOARD_TOKEN` is | — *(the API key is a user)* |
| `user` | who comments are attributed to | — |

**`api_user` decides how much access baton has.** Kanboard takes two kinds of
credential and the username is what tells them apart:

| `api_user` | `$BOARD_TOKEN` is | Reaches |
|---|---|---|
| `jsonrpc` *(default)* | the **application** token, *Settings → API* | every project on the instance, as admin |
| a person's username | **their** token, from their profile → API | what that person can see, nothing more |

Adding a second person to a board should use the second form. Sharing the application
token to give someone access hands them administration of everything, and it is a
shared secret: rotating it breaks for everyone at once.

`user` names who comments are attributed to, because the application token is not a
user and Kanboard cannot infer an author. Skip it when `api_user` is a person — that
person *is* the author. `baton doctor` reports which credential it authenticated with.

Everything else (project id, Status field id, stage option ids) is **discovered** — no
ids in this file, ever, which is why it is five lines instead of a pile of UUIDs.

**Every key, with values and comments: [`docs/config.example.yaml`](docs/config.example.yaml).**
That file is loaded by [`tests/test_docs.py`](tests/test_docs.py), which also checks it
against `Config` in both directions — so it cannot document a key that does not exist,
and a new key cannot arrive undocumented. Copy it:

```bash
mkdir -p .baton && cp docs/config.example.yaml .baton/config.yaml
```

Or let `baton bootstrap` write the required half for you — see
[`baton-bootstrap`](skills/baton-bootstrap/SKILL.md).

Notable ones: `stages` maps baton's lifecycle vocabulary to **what this board calls
each column** (and declaring `stages.verify` **gates** it) · `repos` maps an `area:`
label to a repo for multi-repo projects · `tokens` holds env var NAMES, never
credentials · `git` names your branches, explained in
[docs/git-flow.md](docs/git-flow.md), and declares **how your deployment is set
off** (`git.release`: `release` · `tag` · `none`). That last one is **required to
ship**: `baton release` refuses without it, because a Release created where the CI
waits for a tag sets off nothing and says so to nobody.

### Stage names live in one place

Every command takes a column name **or baton's own name for it**, so nothing hardcodes
a board's vocabulary:

```bash
baton list --stage @approve      # whatever THIS board calls the approved column
baton new --title "..." --stage @triage
baton advance 42 --to @verify
```

`@triage · @approve · @start · @verify · @ship · @cancel`. Rename a column in `stages:`
and every command and skill follows. `baton bootstrap` also makes `@triage` the board's
**default** stage, so an item created without one lands inside the lifecycle instead of
in whatever column the backend picked — and `baton doctor` says so if either drifts.

## Credentials

**One variable per adapter role.** Not per provider, and not per "role of credential":

| Role | Reads | Is |
|---|---|---|
| board | `BOARD_TOKEN` | where item state lives |
| repo | `REPO_TOKEN` | the code host |
| migration | `MIGRATION_TOKEN` | the old board, read once — only during a migration |

**By role, so the name stays put when the provider changes.** Moving this project's
board from Plane to Kanboard would otherwise have meant exporting a different
variable — the provider was written into the name, and a name that repeats what
`adapters:` already says is a name that goes out of sync.

`MIGRATION_TOKEN` is its own because a migration has **two boards at once**. Until it
existed that worked by accident — the source was Plane and the destination Kanboard,
so their names happened to differ; moving between two instances of the same provider
collided.

```yaml
tokens: BOARD_TOKEN                      # the default; write it only to change it
tokens: {board: KB_PROD, repo: GH_BOT}   # or name them per role
```

### There is no `agent` and no `admin`

baton does not model roles of credential. **What a credential may do is decided by
whoever issued it**, and a separation is only real when a third party enforces it:
GitHub does — it will not let a PR author approve their own PR. A board enforces the
permissions of the user behind the token, which are the same whichever variable it
came from. Pointing a second one at it separated nothing, and nothing ever checked
that the one called `admin` could do more — an unverified claim, which is what
`doctor` exists to kill.

So which credential you use where is **your** decision, folder by folder: a projects
root wants one that can create repos; a repo does not need one. `--as admin` is still
accepted so older scripts do not break, and it chooses nothing.

**If a credential cannot do something**, whoever issued it says so and `doctor`
reports it. A board project that cannot be created gets created by hand, and
`bootstrap` adopts it.

**Credential missing?** `doctor` looks for it in the MCP servers an agent runtime has
configured (`~/.claude.json`, `.mcp.json`) and prints where it is, plus the command to
export it. It never reads the value: a token picked up silently from another program's
config is a credential nobody chose, used with a role nobody declared.

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

## Roots and repos

**Where you stand decides what baton may do**, and each folder links itself.

A **projects root** is a folder that holds repos — `~/Git-projects/`, or
`~/Git-projects/aot/` with its seven. One board, one code host, the repos under it.
It says so:

```yaml
kind: root
repos:
  engine: {folder: ./app-engine, repo: acme/app-engine}
  web:    {folder: ./app-web,    repo: acme/app-web}
```

| | At a root | Inside a repo |
|---|---|---|
| `bootstrap` | creates the repo, clones it, protects branches, links it, registers it | **validates**: reads, compares, reports |
| writes to the code host | yes | **never** |
| `doctor` | every repo in the map, plus what the map does not know about | this repo |

Everything that writes to the host happens at a root, with the credential you chose
to put there. Inside a repo baton reads — before this, `bootstrap` standing in one
repo could create another one and nothing stopped it. Declared rather than deduced, so
`doctor` can say *"this is not a root"* instead of behaving differently without saying
why.

**Config is never inherited.** `baton` reads `./.baton/config.yaml` and nowhere else;
it does not walk up. A repo with no link of its own used to take the one from the
folder above **and its credential** — at a root, that is the credential that creates
repos. Each repo links to its project explicitly, and several repos sharing a project
each say so on their own.

baton runs at the root of the repository. Being policy rather than habit, it says so:

```
$ cd src && baton list
baton: no .baton/config.yaml here — this is src/, inside the repo at ~/Git-projects/baton.
       baton runs at the root of the repository — `cd ~/Git-projects/baton`.
```

On a multi-repo project an item says which repo its work is for, with a `repo:` label
resolved against the root's map. It is **mandatory** there and has no default: a
default is how work gets branched in the wrong place and nobody finds out until the
PR. An epic can carry several — a deliverable rarely respects repo boundaries.

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
baton bootstrap --base-url https://board.acme.com --board APP --repo O/R --check test
                                    # create/adopt repo+board, protect, write config
                                    # (plane also takes --workspace)
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

baton release                        # set the deployment off the way `git.release` says,
                                     # then verify it ran. Non-zero if it did not.
```

## Example

```
$ baton doctor
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
    Fix: baton bootstrap --check <your CI check>   (idempotent; protects every repo the config declares)
stages: Review, Approved, In Progress, Verify, Deployed, Cancelled
epics (native groups): 2 on the board

$ baton show 42
#42 [Approved] Add dark mode
  https://board.acme.com/task/42
  priority: medium
  labels: type:idea

$ baton show 42 --comments
#42 [Approved] Add dark mode
  https://board.acme.com/task/42
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
Kanboard *task links* without either word reaching a skill. Full guides per family:
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
a target date, and the progress is read off the board every time: close an item and the
roadmap is already right.

The count is baton's, not the backend's, and that is deliberate. **Abandoned work is
not progress** — a backend that counts "closed" counts cancelled items too, and then
dropping a task is the fastest way to move a bar. Done means closed *and* not
cancelled, decided once for every board rather than once per adapter, which is how two
backends came to answer the same question differently.

```
$ baton groups
Q3 auth        [7/12 58%]  due 2026-09-30
Recorder v2    [0/4 0%]    due 2026-10-15
```

"Epic" is the word; Plane stores it as a **module**, Kanboard as a task with links.
Neither word reaches a skill. `baton group <id> --to X`
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

- `gh` CLI, authenticated. GitHub is the code host — `repo` scope is enough; the
  `project` scope is not needed since GitHub Projects stopped being a board.
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
- **Review y spec sync automáticos** — un agente revisa el PR contra los criterios
  del item, y al mergear detecta lo que el código y la spec ya no dicen igual.
  Designed, not built:
  [docs/design/automated-review-spec-sync.md](docs/design/automated-review-spec-sync.md).

## Status

Kanboard and Plane board adapters and the GitHub code-host client, all verified
live — this project's own board runs on Kanboard.
Published: [`baton-board` on PyPI](https://pypi.org/project/baton-board/), and
`npx skills add SOSkr/baton` for the skills.

## License

MIT — see [LICENSE](LICENSE).
