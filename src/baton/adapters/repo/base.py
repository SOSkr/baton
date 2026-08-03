"""The CODE HOST contract: where the code, the PRs and the branch protections are.

Small on purpose. It exists — where "one implementation, so no interface" was the
right call for a long time — because the contract is now something a second host has
to satisfy, not a guess: `repo/__init__.py` writes the role's rules against THIS list
and nothing else.

What is deliberately absent: anything that reads a local working tree. The host is
asked instead, so `baton bootstrap` never has to be standing inside a clone.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ...base import BatonError


class RepoBase(ABC):
    # ---- discovery ----
    @abstractmethod
    def probe(self) -> str:
        """ONE cheap read-only call proving this credential reaches this repo, and
        saying WHAT it may do here. Raises BatonError if it does not."""

    @abstractmethod
    def permissions(self) -> set[str]:
        """What this credential may do here, as a set (`admin`, `push`, ...).

        Structured on purpose: the admin gate before any protection write reads this,
        and a gate that has to parse `probe()`'s human sentence is a gate one wording
        change away from silently passing.
        """

    @abstractmethod
    def find(self) -> dict | None:
        """The repo's facts (`{name, visibility, default_branch}`), or **None if it
        does not exist**.

        `None` means "not there", never "could not look". A host that cannot tell a
        404 from a 403 turns a permissions problem into a create — see `GhError.status`.
        """

    @abstractmethod
    def create(self, visibility: str) -> dict:
        """Create the repo, with an initial commit so it HAS a default branch — the
        integration branch is cut from it. Same shape as `find()`."""

    # ---- branches ----
    @abstractmethod
    def branch_sha(self, ref: str) -> str | None:
        """Head sha of `ref`, or None if there is no such branch."""

    @abstractmethod
    def create_branch(self, name: str, sha: str) -> bool:
        """Create `name` at `sha`. Returns False if it already existed — existing is
        the expected state on a re-run, not an error."""

    @abstractmethod
    def branch_protection(self, branches: list[str]) -> dict[str, str]:
        """State of each branch: `protected`, `UNPROTECTED`, or `missing`.

        Three values, not a bool: a branch that is not there is a setup mistake, an
        open one is a security hole, and sending someone to fix the wrong one wastes
        the report. Reading whether protection exists must NOT need admin — the agent
        credential has to be able to surface a hole it cannot itself close.
        """

    @abstractmethod
    def required_checks(self, branch: str) -> list[str]:
        """Which status checks the protection requires. Empty when there are none —
        which is itself a finding: a protection with no check lets a red PR merge."""

    @abstractmethod
    def protect_branch(self, branch: str, *, checks: list[str], reviews: int,
                       enforce_admins: bool) -> None:
        """Require `reviews` approvals and `checks` on `branch`. Idempotent (the host
        call is a PUT), which is what makes "re-run once CI exists" the upgrade path.

        `reviews >= 1` is what stops an agent merging its own work: a host that
        forbids self-approval turns the review requirement into a second pair of eyes.
        """

    # ---- releasing: OPTIONAL, like the board's grouping ----
    # NOT abstract on purpose. A code host without releases is a real thing, and the
    # `git.release: none` path never calls any of these — so forcing every
    # implementation to stub them would buy nothing. A host that lacks the concept
    # says so, the same way a board without epics does.
    #
    # What a release IS depends on the project, and the host is the only thing that
    # knows how to make one. WHICH of these to call is baton's rule (`git.release`),
    # decided once in `adapters/repo/__init__.py`.

    def release_triggers(self) -> set[str]:
        """What this repo's CI says fires a deployment: any of `release`, `tag`,
        `push`. Read from whatever the host declares it in — for GitHub, the `on:`
        of each workflow.

        Used to CHECK, never to decide. `doctor` compares it against `git.release`
        and says so when they disagree; guessing from it would be the same mistake
        as guessing a required check — right until the day it is quietly wrong."""
        return set()

    def create_release(self, tag: str, *, target: str, title: str, notes: str) -> str:
        """Publish a release at `tag` on `target`. Returns its URL.

        **Published, not drafted.** A draft fires nothing, and a release that fires
        nothing is exactly the failure this exists to prevent: it looks done."""
        raise BatonError(f"{type(self).__name__} cannot create releases")

    def release_exists(self, tag: str) -> bool:
        """Re-running a ship must not create a second release, and must not fail
        either — the first run may have died after creating it."""
        raise BatonError(f"{type(self).__name__} cannot create releases")

    def create_tag(self, tag: str, *, target: str) -> None:
        """Push a tag at `target`, for projects whose CI fires on tags."""
        raise BatonError(f"{type(self).__name__} cannot create tags")

    def deploy_runs(self, tag: str) -> dict[str, str]:
        """Workflow run name -> conclusion, for the runs that `tag` set off.

        This is what turns "the release was created" into "the release worked".
        Without it a ship reports success for having made a git object."""
        return {}

    @abstractmethod
    def set_delete_branch_on_merge(self, value: bool) -> None:
        """Repo-level setting, same class of policy as protections: agnostic of
        language, set once. It matters more with agents than with people — a day of
        work is twenty branches, and without this all twenty stay on the remote."""
