"""The REPO role: the code host — permissions, branches, protections. Permanent, small.

Its credential is separate from the board's, and that is not an accident: git is a
second system, and "the board answers" says nothing about whether you can push.

The rules here are written against `RepoBase` and the config only — never against a
provider (`tests/test_frontier.py` fails the build if that slips). Two of them:
find-before-create, and never trust a write you have not read back.
"""
from __future__ import annotations

from ...base import BatonError
from ...config import Config, github_token_env
from .. import registry
from .base import RepoBase


def get(cfg: Config | None = None, repo: str | None = None,
        role: str = "agent") -> RepoBase:
    """The code host for `repo` (default: the project's own), as `role`."""
    import os
    name = repo or (cfg.code_repo if cfg else None)
    provider = (cfg.adapters.get("repo") if cfg else None) or "github"
    return registry.resolve("repo", provider)(name, os.environ.get(github_token_env(role)))


def ensure(ad: RepoBase, visibility: str = "private") -> tuple[dict, bool]:
    """The repo, and whether THIS call created it. Looks first, always.

    Find-before-create is the rule that makes bootstrap safe to re-run: a half-failed
    run leaves the repo behind, and the second run has to reuse it rather than trip
    over it. It is also why `find()` must answer None only for "does not exist" — a
    403 read as "not there" would turn a permissions problem into a new repo.
    """
    found = ad.find()
    if found:
        return found, False
    return ad.create(visibility), True


def ensure_branch(ad: RepoBase, name: str, *, base: str) -> tuple[str, bool]:
    """`name`, cut from `base` if it is not there yet. Returns (state, created) where
    state is `existed` | `created` | `no base branch`."""
    if ad.branch_sha(name):
        return "existed", False
    sha = ad.branch_sha(base)
    if not sha:
        return f"no {base} to branch from", False
    return ("created", True) if ad.create_branch(name, sha) else ("existed", False)


def protect(ad: RepoBase, branches: list[str], *, checks: list[str] | None,
            reviews: int = 1, enforce_admins: bool = False) -> dict:
    """Protect each branch, then READ IT BACK. Returns a report, never raises for a
    credential that simply lacks admin.

    Skipping is not failing: protecting two repos of three and saying so out loud
    beats protecting none. What must never happen is reporting success for a write
    that did not land — a PUT that returned 200 and a branch that is actually
    protected are two different claims.

    `checks` is `None` for "I have not decided" and `[]` for "I mean none". They are
    not the same: a protection with no required check lets a red PR merge, and one
    naming a check that does not exist makes every PR HANG — waiting on a status that
    will never arrive. Neither should arrive by accident, so undecided is refused.
    """
    if checks is None:
        raise BatonError(
            "refusing to guess about required checks: pass the check name(s), or say "
            "explicitly that there are none.\n"
            "Require ONE aggregated name, never the names a build matrix produces — a "
            "matrix reports `test (3.11)`, `test (3.12)`, ... and no plain `test`, so "
            "adding a version later would block every PR until someone with admin "
            "edits the protection by hand.")

    report: dict = {"admin": True, "branches": {}}
    if "admin" not in ad.permissions():
        # Checked BEFORE writing, on purpose: half-applied protections that report
        # success are worse than none, because repo writes succeed while admin ones do
        # not. The agent credential legitimately gets here.
        report["admin"] = False
        return report

    ad.set_delete_branch_on_merge(True)
    report["delete_branch_on_merge"] = True

    wanted = list(dict.fromkeys(branches))          # trunk-based: one branch, one pass
    state = ad.branch_protection(wanted)
    for br in wanted:
        if state[br] == "missing":
            report["branches"][br] = "missing — skipped"
            continue
        ad.protect_branch(br, checks=checks, reviews=reviews,
                          enforce_admins=enforce_admins)
        after = ad.branch_protection([br])[br]
        got = ad.required_checks(br)
        report["branches"][br] = (f"{after} checks={','.join(got) or '(none)'}"
                                  if after == "protected"
                                  else f"{after} — the write did NOT land")
    return report
