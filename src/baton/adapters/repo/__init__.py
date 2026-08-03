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


# What `git.release` may say. The project declares how its deployment is set off,
# because no single command can guess it without being wrong on the other two:
#
#   release  the CI fires on a published release  -> ship CREATES it
#   tag      the CI fires on a pushed tag         -> ship PUSHES it
#   none     the merge already deployed           -> ship creates nothing
#
# Not detected from the workflows, on purpose. `doctor` compares the two and warns —
# but deciding from a guess is how you end up believing you published and finding out
# from a user. The same reason `bootstrap` refuses to guess a required check.
RELEASE_MODES = ("release", "tag", "none")


def release_mode(cfg: Config) -> str:
    """How this project's deployment is set off. Refuses to guess."""
    mode = (cfg.git or {}).get("release")
    if mode in RELEASE_MODES:
        return mode
    raise BatonError(
        "config.git.release is not set, and shipping cannot guess it:\n"
        "  release   your CI fires on a published GitHub Release (a package)\n"
        "  tag       your CI fires on a pushed tag\n"
        "  none      merging to production already deployed\n"
        "Pick the one your CI actually declares — `baton doctor` shows what it does."
        + (f"\nGot {mode!r}." if mode else ""))


def release(ad: RepoBase, cfg: Config, tag: str, *, title: str, notes: str) -> dict:
    """Set the deployment off, whatever "off" means here. Returns what happened.

    Creating the release or the tag belongs to the host — GitLab will do it its own
    way — but WHICH of the three to do is the same everywhere, so it is decided here
    and not in an adapter.

    Idempotent where it can be: a release that already exists is reported, not
    duplicated and not an error. The first attempt may have died after creating it,
    and a ship that cannot be re-run is a ship nobody re-runs.
    """
    mode = release_mode(cfg)
    target = cfg.git["production"]
    if mode == "none":
        return {"mode": mode, "did": "nothing — merging already deployed"}
    if mode == "tag":
        ad.create_tag(tag, target=target)
        return {"mode": mode, "did": f"pushed tag {tag}"}
    if ad.release_exists(tag):
        return {"mode": mode, "did": f"release {tag} already existed"}
    url = ad.create_release(tag, target=target, title=title, notes=notes)
    return {"mode": mode, "did": f"published release {tag}", "url": url}


def deploy_verdict(ad: RepoBase, cfg: Config, tag: str) -> tuple[bool, dict[str, str]]:
    """Did the deployment this ship set off actually work?

    Returns (ok, runs). `ok` is False while anything is still running, too: "not
    finished" is not "finished well", and closing items on either is what made a
    release look done while PyPI still served the previous version.
    """
    if release_mode(cfg) == "none":
        return True, {}
    runs = ad.deploy_runs(tag)
    if not runs:
        return False, runs
    return all(v == "success" for v in runs.values()), runs


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
