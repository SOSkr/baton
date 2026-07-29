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

Most of what happens here is **your policy**, not mechanics: which protections, which
label axes, which stages. Confirm them; do not assume this repo's defaults are yours.

## Credential

Everything below needs admin rights (create repo, create project, set protections).
Nothing in the rest of baton's lifecycle does.

```bash
baton doctor           # shows which env var each role reads, and whether it is set
```

If `$GH_ADMIN_TOKEN` (or your configured admin var) is not set, **stop and say so.**
Do not proceed with the agent credential: repo creation will succeed and protections
will silently fail, leaving a project that looks configured and is not.

## 1. Confirm the parameters

Ask, do not guess: name · visibility (private/public) · the board's stages · the label
axes (`type`, `area`, `priority` — whatever this org uses) · the integration branch
name · who else needs access.

## 2. Create the repo

```bash
gh repo create <owner>/<name> --private --add-readme
gh repo clone <owner>/<name> && cd <name>
git checkout -b develop && git push -u origin develop     # the integration branch
# Name it whatever the project agreed in step 1, then record both in .baton/config.yaml:
#   git: {integration: develop, production: master}
# Trunk-based? Skip this branch and set integration to the production one.
```

## 3. Create the board

The board lives in **Plane**; GitHub is the code host only. Create the project in the
Plane UI or via its API, then note the **workspace slug** and the **project identifier**
(the short prefix, e.g. `APP` — that is what `config.target.project` takes).

Set up its states to match the stages you agreed in step 1. Epics are Plane **modules**
and are created later, deliberately, by `baton-roadmap` — not here.

## 4. Protections

The point of the credential split. The agent opens PRs; it must not be able to merge
its own work unreviewed.

**Protect both branches, not just production.** The agent touches the integration
branch on **every item** and production **once per release** — protecting only
production guards the branch they touch least. Leave integration open and an agent
with push rights skips the PR, the review and CI entirely, which is the whole thing
the credential split exists to prevent.

```bash
bash "{this skill's dir}/scripts/protect-branches.sh" --check "{your CI check}"
```

Branch protection is the same GitHub policy for every project — nothing about it is
language-specific — so it ships as a script instead of a snippet to retype. It reads
the branch names from `baton config`, applies the same policy to both, and **reads each
one back**: a PUT that returned 200 and a branch that is actually protected are two
different claims.

It **refuses to guess** about checks. Pass `--check <name>`, or `--no-checks` to say
you mean it — a protection with no required check lets a red PR merge, and one naming
a check that does not exist yet makes every PR hang. Neither should arrive by accident.
Rerun it later to add the check once CI exists; the call is a PUT, so it is idempotent.

Three decisions, each on purpose:

- **required reviews ≥ 1** — this is what stops an agent self-merging, because GitHub
  does not let a PR author approve their own PR.
- **`enforce_admins`** — leave it `false` and `baton-ship` can merge releases with
  `--admin`; set it `true` and every release needs a human approval. Pick one on
  purpose; the default here is not a recommendation.
- **which checks** — require **one aggregated name**, never the names a build matrix
  produces. A matrix reports `test (3.11)`, `test (3.12)`, … and no plain `test`;
  requiring those means that adding a version later blocks **every** PR until someone
  with admin edits the protection — and it does not fail, it hangs, waiting for a
  status that will never arrive. Have CI expose a single job that depends on the rest,
  and require that one name.

baton does not ship your CI — the workflow is your project's language and tooling. What
it asks is that the repo produce a check with a **stable** name, and the script wires
the protection to it. Run it with `--no-checks` first if CI does not exist yet, then
again with `--check` once it does.

The script needs **admin** and uses `$GH_ADMIN_TOKEN` when set. It checks first and
stops if the credential lacks it — half-applied protections that report success are
worse than none, because repo writes succeed while admin writes do not.

## 5. Label axes

Labels are **axes, not state** — state is the board stage. Create the axes the project
agreed on in step 1: typically `type:` (idea/bug/chore) and `area:` (one value per
repo, if the project spans several).

**Do not create a `priority:` axis.** Priority is a native field on this board —
`baton new --priority high`, `baton priority <id> --to high`. Same for anything else
`baton doctor` reports as native: a label that duplicates a real field is a field the
board cannot sort by.

Plane creates labels on demand, so there is usually nothing to pre-create — just agree
on the vocabulary and use it consistently from the first item.

## 6. Wire baton to it

```bash
baton init --base-url <plane-url> --workspace <slug> --board <identifier> \
           --repo <owner>/<name>
baton doctor
```

`--repo` is how the board learns where the code is — Plane has no concept of a git
repository. For a project spanning several repos, replace it afterwards with a `repos:`
map keyed by the `area:` label (see the README).

`doctor` must print `discovery OK` with the stages you created. If it does not, the
board is not what the config says it is — fix that now, not on the first item.

Then add by hand whatever the project needs: `stages` aliases if your columns are not
the defaults, `tokens` if the env vars differ, `memory`, `projects`.

## 7. Hand over

Say explicitly to the user: bootstrap is done, and everything from here (`baton-new`
onward) runs on the **agent** credential. The admin one should go back to wherever it
lives — not into the agent's environment, or the split you just built is decorative.

## Notes
- Idempotence: `gh repo create` on an existing repo fails loudly, which is correct.
  `baton init` refuses to overwrite a config without `--force`. Rerunning after a
  partial failure is safe; check what already exists before re-creating.
- The first work-item is `baton-new`, not this skill.
