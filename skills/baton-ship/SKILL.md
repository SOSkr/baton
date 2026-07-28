---
name: baton-ship
description: Ship what is on the integration branch to production and close the loop on every work-item that went out. Use when the user says "release", "ship it", "deploy to production", "crear release", "llevar develop a producción".
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

Defaults are `--base master --head develop --workflow verify-deploy`; override per
repo:

```bash
bash .../ship-pr.sh "summary" --base main --head dev --workflow deploy
bash .../ship-pr.sh "summary" --no-merge          # stop after checks
```

If the repo has no such workflow the script says so and exits cleanly — there is
just no deploy verification and no tag.

## 4. Close the loop

Only once the deploy is verified — never on merge alone:

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
