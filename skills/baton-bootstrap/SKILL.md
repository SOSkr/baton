---
name: baton-bootstrap
description: >
  Create a new project from nothing: the repo, the board, branch protections, the
  label axes — then wire baton to it. Use when the user says "new project", "crear
  proyecto", "bootstrap X", "set up a repo and board for X".
license: MIT
compatibility: requires Python 3.11+, baton CLI (pipx install baton-board), gh (github) or a Plane API key
credential: admin
---

# baton bootstrap

Step zero of the lifecycle — everything `baton-new` assumes already exists. Runs
**once per project**, with the **admin credential**, and ends by handing the project
over to the agent credential for all normal work.

The mechanics are one command. **Your job here is the decisions it takes as flags** —
which protections, which stages, which label axes, public or private. Confirm them with
the user; do not assume this repo's defaults are theirs.

```bash
baton bootstrap --repo <owner>/<name> --base-url <plane-url> --workspace <slug> \
                --board <IDENT> --check "<your CI check>"
```

That one call: writes `.baton/config.yaml` · creates the repo (if absent) · cuts the
integration branch · protects integration **and** production on **every** repo the
config declares · creates the board project (if absent) · creates the stages that are
missing. Everything is looked up before it is created, so **re-running is how you
resume** after a half-failure, and running it against an existing repo and board is
how you adopt them (`baton init` is the same command, kept as an alias).

## 1. Confirm the parameters — this is the actual work

Ask, do not guess:

| Decision | Flag | Default if unsaid |
|---|---|---|
| repo | `--repo owner/name` | — (required) |
| public or private | `--visibility` | `private` |
| board coordinates | `--base-url`, `--workspace`, `--board IDENT` | — (required) |
| board display name | `--name` | the identifier |
| the stages | `--stage` (repeatable, in board order) | Review · Approved · In Progress · Verify · Deployed · Cancelled |
| branch names | `--integration`, `--production` | `develop`, `master` |
| required check | `--check NAME` (repeatable) or `--no-checks` | **refused** — see below |
| approvals | `--reviews N` | 1 |
| protections bind admins too | `--enforce-admins` | off |
| who else needs access | — | do it in the host's UI afterwards |

**Run it with `--dry-run` first and show the plan to the user.** That is where a typo
in the repo name is still free: it prints `would create` for something that does not
exist yet, instead of creating `acme/appp` and leaving you to explain it.

## 2. The credential

Everything that writes here needs admin. Nothing in the rest of baton's lifecycle does.

```bash
baton doctor           # shows which env var each role reads, and whether it is set
```

If the admin var is not set, **stop and say so**. Do not proceed with the agent
credential: the repo would be created and the protections silently skipped, leaving a
project that looks configured and is not. `bootstrap` reports that skip out loud and
exits non-zero — read its output, do not assume success.

## 3. Read the report, do not assume

Every write is reported **from a read-back**: a PUT that returned 200 and a branch that
is actually protected are two different claims. Exit code is non-zero if anything was
skipped or did not land.

What the lines mean when they are not `existed` / `created` / `protected`:

- `protections <repo>: SKIPPED — no admin` → the credential is wrong, not the config.
- `protection <repo> <branch>: missing — skipped` → that branch does not exist there.
  Normal in a multi-repo project where a sibling repo has no `develop` yet.
- `stage X: existed — group is 'started', config wants 'completed'` → **read this one.**
  baton derives open/closed from a stage's group, so a `Deployed` column filed under
  `started` leaves every shipped item reading as open. It is not fixed automatically:
  changing a group changes what every item already in that column counts as. Fix it in
  the board's UI, or declare the mapping in the config (see below).
- `stage X: EXTRA — not in board_stages` → a fresh Plane project ships Backlog/Todo/Done.
  Harmless clutter; `--prune` deletes them. **Do not pass `--prune` on a board that
  already has work in it** without asking — it deletes columns items may live in.

## 4. Three decisions worth arguing about

- **required reviews ≥ 1** — this is what stops an agent self-merging, because a host
  does not let a PR author approve their own PR.
- **`--enforce-admins`** — leave it off and `baton-ship` can merge releases with
  `--admin`; turn it on and every release needs a human approval. Pick on purpose; the
  default here is not a recommendation.
- **which checks** — require **one aggregated name**, never the names a build matrix
  produces. A matrix reports `test (3.11)`, `test (3.12)`, … and no plain `test`;
  requiring those means adding a version later blocks **every** PR until someone with
  admin edits the protection — and it does not fail, it hangs, waiting for a status
  that will never arrive. Have CI expose a single job that depends on the rest, and
  require that one name. `bootstrap` refuses to guess: pass `--check`, or `--no-checks`
  to say you mean it. Re-run with `--check` once CI exists; the call is idempotent.

baton does not ship your CI — the workflow is your project's language and tooling. What
it asks is that the repo produce a check with a **stable** name.

## 5. Stages whose meaning is not obvious

`--stage` takes names and infers each one's lifecycle group: everything before the
stage `stages.start` points at is unstarted, the last non-cancelled one is what "done"
means, and a name like Cancelled/Rechazado is a cancellation. When that guess would be
wrong — a board in another language, two closing columns — write the mapping in
`.baton/config.yaml` instead and re-run:

```yaml
board_stages: {Pendiente: unstarted, Haciendo: started,
               Desplegado: completed, Cancelado: cancelled}
```

## 6. Label axes

Labels are **axes, not state** — state is the board stage. Create the axes the project
agreed on: typically `type:` (idea/bug/chore) and `area:` (one value per repo, if the
project spans several). Plane creates labels on demand, so there is usually nothing to
pre-create — agree on the vocabulary and use it consistently from the first item.

**Do not create a `priority:` axis.** Priority is a native field on this board —
`baton new --priority high`, `baton priority <id> --to high`. Same for anything else
`baton doctor` reports as native: a label duplicating a real field is a field the board
cannot sort by.

## 7. Verify, then hand over

```bash
baton doctor
```

`doctor` must print the stages you asked for and reach both sides. If it does not, the
board is not what the config says it is — fix that now, not on the first item.

Then add by hand whatever the project needs: `stages` verb aliases if the columns are
not the defaults, `tokens` if the env vars differ, `memory`, `projects`, and a `repos:`
map for a multi-repo project (after which re-running `bootstrap` protects all of them).

Say explicitly to the user: bootstrap is done, and everything from here (`baton-new`
onward) runs on the **agent** credential. The admin one goes back to wherever it lives —
not into the agent's environment, or the split you just built is decorative.

## Notes
- **Nothing is rolled back.** On failure, the report ends with `created by this run:`
  and the exact undo command for each thing. That is deliberate: an automatic delete
  driven by a lookup that may simply have been unauthorised is how you lose a repo that
  was never yours to create.
- The first work-item is `baton-new`, not this skill.
