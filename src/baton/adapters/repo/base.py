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

    @abstractmethod
    def set_delete_branch_on_merge(self, value: bool) -> None:
        """Repo-level setting, same class of policy as protections: agnostic of
        language, set once. It matters more with agents than with people — a day of
        work is twenty branches, and without this all twenty stay on the remote."""
