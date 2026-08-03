---
name: baton-ship
description: Ship what is on the integration branch to production and close the loop on every work-item that went out. Use when the user says "release", "ship it", "deploy to production", "crear release", "llevar develop a producción".
license: MIT
compatibility: requires Python 3.11+, baton CLI (pipx install baton-board)
credential: agent
---

# baton-ship

Last stage of the lifecycle: everything accumulated on the integration branch goes
to production, and each work-item that went out advances to the ship stage and
closes. Follows on from [baton-start](../baton-start/SKILL.md), which leaves items
merged into the integration branch.

**A release is a direct PR `head` → `base`.** No release branches. Tagging and
deployment belong to the repo's own pipeline — this skill never deploys by hand.

## 1. Check the board

```bash
baton list --json          # what is ready to go out
baton show <id>            # a specific item
```

Anything still in progress either waits or is excluded from this release. State
lives on the board, not in labels.

## 2. Verify the branch is releasable

Run the target repo's test suite — whatever it uses (`pytest`, `phpunit`, `npm
test`, `dotnet test`). Red suite, no release.

## 3. Open the PR, merge it, watch the deploy

```bash
bash "{this skill's dir}/scripts/ship-pr.sh" "{one-line summary}"
```

The script is **resumable** — rerun it and it picks up the open PR instead of
creating a second one. It creates (or reuses) the PR with the commit list in the
body, waits for checks, merges with `--admin` (branch protection asks for a review
you cannot give yourself), then waits for the deploy-verification workflow run
matching the merged SHA and fails if that run fails.

Base and head default to `baton config git.production` and `git.integration`, so a
repo that calls its branches something else needs no flag. `--workflow` defaults to
`verify-deploy`. Override any of them:

```bash
bash .../ship-pr.sh "summary" --base main --head dev --workflow deploy
bash .../ship-pr.sh "summary" --no-merge          # stop after checks
```

If the repo has no such workflow the script says so and exits cleanly — there is
just no deploy verification and no tag.

## 4. Set the deployment off — and find out whether it worked

```bash
baton release                       # tag from the project version, notes on stdin
baton release --check               # verdict only, creates nothing
```

**What this does depends on `git.release`, and the project declares it.** Three
shapes exist and no command can guess between them without being wrong on two:

| `git.release` | The CI fires on | `baton release` |
|---|---|---|
| `release` | a published Release — a package | **creates** it |
| `tag` | a pushed tag | **pushes** it |
| `none` | the merge itself | creates nothing |

Get it wrong and nothing objects: a Release created where the CI waits for a tag
sets off nothing, and you find out from a user. That is why `baton release` refuses
to run without the key, and `baton doctor` prints the mode next to what the repo's
workflows actually declare.

**It exits non-zero unless the deployment finished green** — including while a run
is still going, because "not finished" is not "finished well". Re-running is safe:
a release that already exists is reported, not duplicated, so a first attempt that
died after creating it can be picked up.

The tag comes from `pyproject.toml`; anywhere else, pass `--tag`. It is not guessed
from the ecosystem on purpose — a wrong tag on a published package cannot be taken
back, which is why a publish workflow should also refuse to build when the tag and
the version disagree.

## 5. Close the loop

**Only once `baton release` exited zero.** Never on merge alone, and never on a
release that was created but whose workflow you did not watch:

```bash
baton ship <id>
baton close <id> --reason "Shipped in <tag>"
```

Repeat per item. `--reason` posts as a comment, so name the tag or build — that is
what someone reads months later when asking *when did this actually go out*.

Names of stages come from `.baton/config.yaml` (`stages.ship`); check with
`baton stages` if unsure. Never hardcode board or field ids here — that is exactly
what the CLI exists to absorb.

## Multi-part items

An item with a checklist spanning several repos does **not** ship until every box
is ticked. Shipping one part advances nothing: tick your box, and leave the item
in progress until the last part lands.

## When it fails

- **Merge conflicts on the PR** → do not close it; it tracks the head branch and
  re-evaluates on every push. Bring `base` into `head`, push, and rerun.
- **The workflow run never appears** → the merge may not have triggered it. Check
  `gh run list` before assuming success.
- **A tag with no release, or no tag at all** → the deploy never completed
  healthy. Treat it as an incident, not a formality, and do not run `baton ship`.
- **`baton release` says DEPLOY NOT VERIFIED** → close nothing. On 2026-08-02 a
  release was believed published, did not exist, and PyPI kept serving the previous
  version while seven items waited to close. Nothing objected, because moving a
  stage always succeeds. That silence is what this step exists to break.
