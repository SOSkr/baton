"""Board adapter contract for baton.

A board adapter maps baton's generic work-item lifecycle onto a concrete tracker
(Plane, ...). Everything is by NAME — discovery resolves internal IDs.

This contract is for BOARDS only. Migration sources and code hosts are different
jobs with different (much smaller) shapes — see docs/adapters/.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


# Priority is a CLOSED set, not free text — every tracker that has the concept ships
# roughly these five, and a board that sorts by priority cannot sort by prose.
PRIORITIES = ("urgent", "high", "medium", "low", "none")


@dataclass
class Item:
    """A work-item on a board, backend-agnostic."""
    id: str                      # backend id the user refers to (issue number for github)
    title: str
    url: str = ""
    stage: str | None = None     # current Status stage NAME (e.g. "Review"), or None
    labels: list[str] = field(default_factory=list)
    state: str = "open"          # open | closed
    body: str = ""
    priority: str | None = None  # one of PRIORITIES, when the backend has the field


@dataclass
class Group:
    """A deliverable that items are grouped into — a Plane **module**.

    baton's skills call these **epics**, because that is the word people think in;
    `group` is the backend-neutral name for the same thing. The roadmap IS this list:
    a name, a target date, and how much of it is done — all read from the backend, so
    it cannot go stale the way a roadmap document does.
    """
    name: str
    id: str = ""
    target_date: str | None = None
    total: int = 0
    done: int = 0


@dataclass
class Comment:
    """A comment on a work-item. The trail of how the item got where it is —
    what other agents/people did, decided or hit."""
    body: str
    author: str = ""             # login/id when the backend gives one, else ""
    created_at: str = ""         # ISO-8601 as the backend reports it


class Adapter(ABC):
    """Every backend implements this. Stages are referenced by NAME."""

    # ---- discovery ----
    @abstractmethod
    def probe(self) -> str:
        """ONE cheap read-only call proving this credential actually reaches this
        backend. Returns a one-line human summary (who am I, what can I do here).
        Raises BatonError if it does not. `baton doctor` calls this per credential
        role — a token that is merely *set* has told you nothing."""

    @abstractmethod
    def list_stages(self) -> list[str]:
        """The board's Status stages, in board order. Empty if the board has no
        status field."""

    # ---- items ----
    @abstractmethod
    def create(self, title: str, body: str, labels: list[str],
               priority: str | None = None) -> Item:
        ...

    @abstractmethod
    def get(self, item_id: str) -> Item:
        ...

    @abstractmethod
    def list(self, *, stage: str | None = None, label: str | None = None,
             state: str = "open", group: str | None = None) -> list[Item]:
        """Filters are AND-ed. `group` only means anything on a backend that reports
        the `groups` capability; elsewhere accept it and ignore it."""

    @abstractmethod
    def comment(self, item_id: str, text: str) -> None:
        ...

    @abstractmethod
    def comments(self, item_id: str) -> list[Comment]:
        """Existing comments, oldest first. Writing a comment nobody can read
        back is half a channel — this is the other half."""

    @abstractmethod
    def set_stage(self, item_id: str, stage: str) -> None:
        """Move item to the stage whose NAME matches `stage` (case-insensitive)."""

    @abstractmethod
    def set_labels(self, item_id: str, add: list[str] | None = None,
                   remove: list[str] | None = None) -> None:
        ...

    @abstractmethod
    def edit_body(self, item_id: str, body: str) -> None:
        ...

    @abstractmethod
    def close(self, item_id: str, reason: str = "") -> None:
        ...

    # ---- optional capabilities ----
    # NOT abstract on purpose. Native-first means using what a backend really has
    # rather than flattening every backend to the smallest common shape — so a
    # backend that lacks a concept says so, instead of every backend faking it.

    def capabilities(self) -> set[str]:
        """Which optional features below this backend supports natively."""
        return set()

    def list_groups(self) -> list[Group]:
        """Every deliverable/epic on the board, with target date and progress."""
        raise BatonError(f"{type(self).__name__} has no grouping concept")

    def create_group(self, name: str, *, target_date: str | None = None,
                     description: str = "") -> Group:
        raise BatonError(f"{type(self).__name__} has no grouping concept")

    def set_group(self, item_id: str, name: str) -> None:
        """Put an item in an EXISTING group. Never creates one: an epic is a
        deliberate act with a target date, not a side effect of filing a task."""
        raise BatonError(f"{type(self).__name__} has no grouping concept")

    def set_priority(self, item_id: str, value: str) -> None:
        """Set the NATIVE priority field. A backend without one should keep using a
        `priority:` label — a label the board cannot sort or filter by is exactly
        what this exists to stop."""
        raise BatonError(f"{type(self).__name__} has no native priority field")


class BatonError(Exception):
    """User-facing error (bad config, stage not found, backend failure)."""
