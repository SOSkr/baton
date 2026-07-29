# Code host (repo) adapters

**A repo adapter is where the code lives** — branches, PRs, protections, releases. It
is not a board and knows nothing about work-items.

Reference implementation:
[`src/baton/adapters/repos/github.py`](../../src/baton/adapters/repos/github.py).

## Why this family is tiny, and should stay tiny

The whole current implementation is one method:

```python
class GitHubRepo:
    def __init__(self, repo: str, token: str | None = None): ...
    def probe(self) -> str: ...
```

That is not an oversight. baton's git work happens **in the shell, inside the skills** —
`gh pr diff` in [`baton-verify`](../../skills/baton-verify/SKILL.md), `gh pr create`
and `gh pr merge` in [`ship-pr.sh`](../../skills/baton-ship/scripts/ship-pr.sh). Those
are already the right tool: they are readable, debuggable by hand, and a person can run
the exact same command to check what the agent did.

So Python needs exactly one thing from the code host today: **proving what a credential
can actually do**. Everything else would be an abstraction with one implementation,
built for a second code host that does not exist.

> Do not grow a portable PR abstraction here until there is a second host to contrast
> against. When there is one, the shape will be obvious from the two of them; guessed
> now, it will be wrong in a way that is expensive to undo.

## `probe()` — report capability, not success

This is the one method, and the subtlety is that "the token works" is the *uninteresting*
half of the answer. What matters is **what it is allowed to do here**:

```python
def probe(self) -> str:
    login = gh("api", "user", "--jq", ".login")
    perms = gh("api", f"repos/{self.repo}", "--jq", ".permissions", want_json=True) or {}
    can = ", ".join(k for k in ("admin", "maintain", "push", "pull") if perms.get(k)) or "none"
    return f"{login} on {self.repo} — {can}"
```

`baton doctor` runs this once per credential role, and the output is what makes the
[agent/admin split](../../README.md#credential-roles) *checkable*:

```
token[agent] $GH_TOKEN:
  code acme/app: OK — acme-bot on acme/app — push, pull
token[admin] $GH_ADMIN_TOKEN:
  code acme/app: OK — alice on acme/app — admin, maintain, push, pull
```

If the `agent` line comes back with `admin`, the separation is decoration and the
person reading can see it. A probe that returned "OK" would have hidden that.

Whatever host you implement, find its equivalent: the permission level, the scopes, the
role. Reporting only reachability wastes the one call you get.

## Multi-repo projects

A board project can span several git repos, and the board knows nothing about git. The
mapping lives in config, keyed by the `area:` label value:

```yaml
repo: soskr/canguro              # the default
repos:
  engine: soskr/canguro-engine   # matches label area:engine
  web: soskr/canguro-web
```

Resolution helpers live on `Config`
([`config.py`](../../src/baton/config.py)): `repo_for(area)`, `repo_for_labels(labels)`,
and `all_repos` — which is what `doctor` iterates, because **a credential can reach one
repo of a project and not the next**. Probe each one separately; a single green check
on the default repo proves nothing about the others.

## Credentials

The code host has **its own credential pair**, independent of the board's. `git` is a
second system: the board answering says nothing about whether the agent can push.

```python
from ..config import github_token_env
GitHubRepo(repo, os.environ.get(github_token_env(role)))
```

`github_token_env(role)` returns `GH_TOKEN` / `GH_ADMIN_TOKEN` regardless of which
backend holds the board. A new host needs its own equivalent in `_DEFAULT_TOKENS`.

## Wiring it up

1. Drop the module in `src/baton/adapters/repos/`.
2. Add a branch to `get_repo` in [`adapters/__init__.py`](../../src/baton/adapters/__init__.py).
3. Add a `repo_backend:` config key **only when a second host actually exists** — until
   then, inferring GitHub is correct and one fewer thing to configure.
4. If it shells out to a CLI, put the helper in
   [`adapters/_gh.py`](../../src/baton/adapters/_gh.py)'s sibling position, not inside
   the class — sources and repos share it.

## When it is right to grow this family

Move work from the shell into Python only when something needs a **decision** rather
than a command: retry logic, cross-host branching, parsing that a `--jq` cannot express.
`ship-pr.sh` is a good example of the boundary — it is 80 lines of shell doing waits,
retries and resumability, and it is more readable there than it would be as Python.

## Checklist

- [ ] `probe()` reports the credential's permission level, not just success
- [ ] Constructor takes `(repo, token)` and validates `repo`
- [ ] Every repo in `all_repos` is probed independently
- [ ] No PR/branch abstraction added speculatively
- [ ] Failures raise `BatonError` with the host's real error text quoted
