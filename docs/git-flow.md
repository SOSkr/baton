# Git flow

baton assumes a flow. This is it, and how to change it — every branch name here is
config, not a constant baked into a skill.

## The shape

```
feat/42-slug ──PR──▶ integration ──PR──▶ production
                     (develop)          (master)
```

Work happens on a short-lived branch off the **integration** branch. It reaches
integration by PR. Releases are a **direct PR integration → production** that carries
whatever accumulated — [`baton-ship`](../skills/baton-ship/SKILL.md) does it, and
there are **no release branches**.

Both names are yours:

```yaml
# .baton/config.yaml
git:
  integration: develop
  production: master
```

Defaults are `develop` / `master`. Trunk-based? Point both at the same branch and the
release step becomes a no-op. `baton config git.integration` is what the skills and
`ship-pr.sh` read, so nothing needs editing when you change it.

## Branch names are load-bearing

```
<prefix>/<id>-<slug>        feat/42-dark-mode
                            feat/CANGURO-42-dark-mode
```

**The `<id>` is not decoration.** The optional [PR hook](../hooks/README.md) reads it
off the branch name to post the PR link back to the work-item — the one fact the board
cannot derive on its own, since the board and the repo are different systems. A branch
without an id gets no link, and nothing tells you: it fails silently, which is why CI
warns about it.

The id is the number `baton show` takes, bare or with the board's prefix. Both forms
resolve to the same item.

**Prefix** is one of:

| | For |
|---|---|
| `feat` | new capability |
| `fix` | a defect |
| `chore` | infra, CI, deps, docs |
| `hotfix` | urgent fix, branched from production |

The same four words the commit types use — one vocabulary, not two. The longer forms
`feature/` and `bugfix/` still work in the hook on purpose: a hook that silently
ignores a near-miss is worse than a permissive one. CI warns on them because they are
not canonical.

There is no `release/` prefix, deliberately: a release is a PR, not a branch.

## Enforced where

Three places, and none of them is prose alone:

| What | Where | Hard or soft |
|---|---|---|
| Branch prefix, and that the branch carries an id | `.github/workflows/branch-check.yml` | warning — legitimate work exists with no item |
| PR has a description | same workflow | **error** |
| An item cannot reach the done stage without passing through verification | `stages.verify` in config → the CLI refuses the jump | **error**, opt-in |
| The agent cannot merge its own work unreviewed | branch protection: 1 approving review, and GitHub blocks self-approval | **error** |

That last one is the real gate, and it is why the [credential split](../README.md#credential-roles)
exists: the token that writes code should not be the one that approves it.

## Why the release is a PR and not a branch

A release branch is a place for changes to accumulate that were not good enough to be
on integration. If integration is always releasable — which is what the verification
gate is for — the branch has nothing to hold. `ship-pr.sh` opens the PR, waits for
checks, merges, and then waits for the deploy-verification workflow run matching the
merged SHA. It is resumable: rerun it and it picks up the open PR instead of creating
a second one.
