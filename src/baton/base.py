"""Backend adapter contract for baton.

An adapter maps baton's generic work-item lifecycle onto a concrete board
backend (GitHub Projects, Plane, ...). Everything is by NAME — discovery
resolves internal IDs.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


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
    def list_stages(self) -> list[str]:
        """The board's Status stages, in board order. Empty if the board has no
        status field."""

    # ---- items ----
    @abstractmethod
    def create(self, title: str, body: str, labels: list[str]) -> Item:
        ...

    @abstractmethod
    def get(self, item_id: str) -> Item:
        ...

    @abstractmethod
    def list(self, *, stage: str | None = None, label: str | None = None,
             state: str = "open") -> list[Item]:
        ...

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


class BatonError(Exception):
    """User-facing error (bad config, stage not found, backend failure)."""
