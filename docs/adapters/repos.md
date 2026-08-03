# Code host (repo) adapters

**A repo adapter is where the code lives** — branches, PRs, protections, releases. It
is not a board and knows nothing about work-items.

Contract: [`src/baton/adapters/repo/base.py`](../../src/baton/adapters/repo/base.py) → `RepoBase`.
Reference implementation: [`src/baton/adapters/repo/github.py`](../../src/baton/adapters/repo/github.py).

## Ask the host, never a working tree

Every method here goes through the host's API. Nothing shells out to `git`, and nothing
assumes there is a clone to stand in: `baton bootstrap` creates a repo, cuts its
integration branch off the default branch's sha and protects both branches from an empty
directory.

That is a rule, not an accident. A local `git log` depends on how old your `fetch` is,
and a step that needs a checkout cannot run where there is no checkout — a fresh machine,
a CI job, an agent that was handed a name and nothing else. Where the host can answer,
the host answers.

The family is still small, and the reason it is no longer *one method* is that the
creation half now has a caller: `bootstrap` needs to find-or-create a repo, cut a branch
and apply protections, so those went into the contract. Nothing was added speculatively —
`compare()`, PR creation and release tagging are still absent, because the thing that
would use them ([`ship-pr.sh`](../../skills/baton-ship/scripts/ship-pr.sh)) has not been
ported yet.

> Do not grow a portable PR abstraction here until the caller exists. `ship-pr.sh` is
> that caller, and porting it is its own change.

## `probe()` and `permissions()` — report capability, not success

"The token works" is the *uninteresting* half of the answer. What matters is **what it is
allowed to do here**:

```python
def probe(self) -> str:
    login = gh("api", "user", "--jq", ".login")
    perms = gh("api", f"repos/{self.repo}", "--jq", ".permissions", want_json=True) or {}
    can = ", ".join(k for k in ("admin", "maintain", "push", "pull") if perms.get(k)) or "none"
    return f"{login} on {self.repo} — {can}"
```

`permissions()` is the same fact as a **set**, and that split matters: the admin gate
that runs before any protection write reads the set, never the sentence. A gate that has
to parse `probe()`'s prose is one wording change away from silently passing.

`baton doctor` runs the sentence once, and the output is what makes the credential
[checkable](../../README.md#credentials) instead of assumed:

```
code $REPO_TOKEN:
  code acme/app: OK — alice on acme/app — admin, maintain, push, pull
```

There is no second variable to compare against. What this credential may do is
GitHub's answer, printed verbatim — so a token that comes back `push, pull` when the
run needs `admin` says so here, before `bootstrap` fails on it. A probe that returned
just "OK" would have hidden that.

Whatever host you implement, find its equivalent: the permission level, the scopes, the
role. Reporting only reachability wastes the one call you get.

## Multi-repo projects

A board project can span several git repos, and the board knows nothing about git. The
mapping lives in config, keyed by the `area:` label value:

```yaml
repo: acme/app              # the default
repos:
  engine: acme/app-engine   # matches label area:engine
  web: acme/app-web
```

Resolution helpers live on `Config`
([`config.py`](../../src/baton/config.py)): `repo_for(area)`, `repo_for_labels(labels)`,
and `all_repos` — which is what `doctor` iterates, because **a credential can reach one
repo of a project and not the next**. Probe each one separately; a single green check
on the default repo proves nothing about the others.

`bootstrap` protects every repo in `all_repos` for the same reason, with no flag to
enable it: a project that protects one repo of three has protected nothing that matters,
and the config already knows the list.

## Credentials

The code host has **its own credential**, independent of the board's. `git` is a
second system: the board answering says nothing about whether you can push.

```python
GitHubRepo(repo, os.environ.get(cfg.token_env("repo")))
```

`token_env("repo")` returns `REPO_TOKEN` regardless of which backend holds the board —
the name is the adapter ROLE, so it stays put when the provider changes. A project
that wants to name it otherwise writes `tokens: {repo: MI_VAR}`.

## Wiring it up

1. Drop the module in `src/baton/adapters/repo/`, named for the config value, and
   export `ADAPTER = MyHostRepo`. Nothing else registers it.
2. Implement `RepoBase`. Ask the HOST, never a local working tree — a caller must
   not have to be standing inside a clone.
3. Say which host a project uses in the config (`adapters.repo`); GitHub stays the
   default so existing projects keep working untouched.
4. If it shells out to a CLI, put the helper next to
   [`adapters/_gh.py`](../../src/baton/adapters/_gh.py), not inside the class —
   `read/` and `repo/` share it.

## Two rules the role layer enforces, not the provider

Both live in [`repo/__init__.py`](../../src/baton/adapters/repo/__init__.py), written
against `RepoBase` alone, so a second host inherits them for free:

**Look before you create.** `find()` must answer `None` for "does not exist" and *raise*
for anything else. A host that cannot tell a 404 from a 403 turns a permissions problem
into a second repo standing next to the one it could not read.

**Never trust a write you have not read back.** Protections are applied and then
re-read, and the report says which. A PUT that returned 200 and a branch that is actually
protected are two different claims, and the gap between them is exactly where "it looked
configured" comes from.

## When it is right to grow this family

Move work into Python when something needs a **decision** rather than a command: looking
before creating, an admin gate before a write, a read-back after one. Live terminal
streams are the counter-example — `gh pr checks --watch` is a better tool than a poll
loop reimplemented here, which is why the release path is still a script for now.

## Checklist

- [ ] `probe()` reports the credential's permission level, not just success
- [ ] `permissions()` returns a set — the admin gate reads it, not the prose
- [ ] `find()` returns `None` **only** for "does not exist"; 403 raises
- [ ] Constructor takes `(repo, token)` and validates `repo`
- [ ] Every repo in `all_repos` is probed and protected independently
- [ ] Nothing reads a local working tree; the host is asked
- [ ] No PR/branch abstraction added speculatively
- [ ] Failures raise `BatonError` with the host's real error text quoted
