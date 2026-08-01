"""The BOARD contract: where work-item state lives, read and write.

This is the interface, and it is also the documentation — the method list and its
semantics live here, not in a `.md` that drifts. `docs/adapters/boards.md` carries
what a `.py` cannot: why the three families exist and how to test one.

Everything is by NAME. Discovery resolves internal ids — see `plane.py`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ...base import BatonError, Comment, Group, Item


class BoardBase(ABC):
    """Every board backend implements this. Stages are referenced by NAME."""

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

    # ---- creation (bootstrap) ----
    # A board is created ONCE, by `baton bootstrap`, with the admin credential. These
    # are separate from the item verbs above because everything above assumes the board
    # already exists — and because a backend where a human creates the project by hand
    # can still serve the whole lifecycle.

    @abstractmethod
    def find_project(self) -> dict | None:
        """The configured project's facts (`{id, identifier, name}`), or **None if it
        does not exist**. None means "not there", never "could not look" — bootstrap
        creates on None, so a credential error answered as None creates a duplicate."""

    @abstractmethod
    def create_project(self, name: str) -> dict:
        """Create the project the config points at. Same shape as `find_project()`."""

    @abstractmethod
    def stage_groups(self) -> dict[str, str]:
        """Stage name -> the backend's own lifecycle group for it (for Plane:
        `backlog` | `unstarted` | `started` | `completed` | `cancelled`).

        This is what makes a created stage *work*: baton derives an item's open/closed
        from its stage's group, so a "Deployed" column filed under `backlog` leaves
        every shipped item reading as open forever. A backend with no such concept
        returns empty strings.
        """

    @abstractmethod
    def create_stage(self, name: str, *, group: str, color: str) -> None:
        """Add a stage. `group` is the backend's lifecycle group (see `stage_groups`)."""

    @abstractmethod
    def set_stage_position(self, name: str, position: int) -> None:
        """Put `name` at 0-based `position` in the board order.

        Order is not cosmetic here: baton reads `list_stages()` ORDER to decide whether
        a move goes forward or backward and whether it skipped verification. Backends
        append new stages at the end, so without this the first column of the lifecycle
        can end up after the last one — and the rules quietly invert.

        Unlike a stage's group, position carries no meaning about the work sitting in
        it, which is why this is the one property `bootstrap` will rewrite on a stage it
        did not create.
        """

    @abstractmethod
    def default_stage(self) -> str | None:
        """The stage a new item lands in when none is given, by the backend's own
        reckoning. None if the backend has no such concept."""

    @abstractmethod
    def set_default_stage(self, name: str) -> None:
        """Make `name` that stage. Whether the previous default has to be cleared by
        hand is the backend's business, not the caller's — Plane, for one, will happily
        end up with two."""

    @abstractmethod
    def delete_stage(self, name: str) -> None:
        """Remove a stage. Destructive on a board with work in it — the caller is
        responsible for asking first (`bootstrap --prune`)."""

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
