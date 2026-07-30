"""The CODE HOST contract: where the code, the PRs and the branch protections are.

Small on purpose. It exists — where a year of "one implementation, so no interface"
was the right call — because the contract is now something a second host has to
satisfy, not a guess: `repo/__init__.py` writes the role's rules against THIS list
and nothing else.

What is deliberately absent: anything that reads a local working tree. The host is
asked instead (`compare`, `branch_sha`, `create_branch` arrive with bootstrap) — so
a caller never has to be standing inside a clone.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class RepoBase(ABC):
    @abstractmethod
    def probe(self) -> str:
        """ONE cheap read-only call proving this credential reaches this repo, and
        saying WHAT it may do here. Raises BatonError if it does not."""

    @abstractmethod
    def branch_protection(self, branches: list[str]) -> dict[str, str]:
        """State of each branch: `protected`, `UNPROTECTED`, or `missing`.

        Three values, not a bool: a branch that is not there is a setup mistake, an
        open one is a security hole, and sending someone to fix the wrong one wastes
        the report. Reading whether protection exists must NOT need admin — the agent
        credential has to be able to surface a hole it cannot itself close.
        """
