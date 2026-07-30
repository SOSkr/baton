"""The MIGRATION SOURCE contract: an old tracker, read once, on the way out.

The interface exists to answer "how do I write one of these", not because the code
needs polymorphism — there is one implementation and it is meant to be deleted after
the migration it serves.

The whole point of this family is the ABSENCE of writes. There is no `create`, no
`set_stage`, no `comment`. A source is not a board with methods missing; it is a
thing that must never write, and the shortest way to guarantee that is to give it no
way to.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ...base import Comment, Item


class ReadBase(ABC):
    @abstractmethod
    def list_stages(self) -> list[str]:
        """The old board's stages, in its own order — what the new board's stages
        have to be mapped onto."""

    @abstractmethod
    def get(self, item_id: str) -> Item:
        ...

    @abstractmethod
    def list(self, *, stage: str | None = None, label: str | None = None,
             state: str = "open") -> list[Item]:
        ...

    @abstractmethod
    def comments(self, item_id: str) -> list[Comment]:
        """Oldest first. An item without its comments is a title and a guess —
        everything explaining WHY it exists is in the thread."""
