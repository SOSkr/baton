"""The vocabulary every layer shares: the error, and the shapes adapters return.

Deliberately holds NO contract for any one adapter family — each role owns its own
interface, next to its implementations (`adapters/board/base.py`, `repo/base.py`,
`read/base.py`). What stays here is what more than one layer needs: `BatonError` is
raised by `config.py` too, and `Item`/`Comment` come back from a **read** source as
much as from a board.
"""
from __future__ import annotations

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


class BatonError(Exception):
    """User-facing error (bad config, stage not found, backend failure)."""
