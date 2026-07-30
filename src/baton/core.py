"""`Baton` — the one door. Skills and `cli.py` talk to this and to nothing below it.

Why a class and not more free functions: the rules that matter are the ones spanning
two sides (a board AND a code host), and something has to hold the config, the
credential role and the instances while they run. What it deliberately is NOT is a
mirror of `BoardBase`: the dumb verbs go straight through `.board`, so adding a method
to the board contract does not mean adding a wrapper here that can drift from it.

Dependencies point one way: cli → core → adapters. Never back.
"""
from __future__ import annotations

from .adapters import board as _board
from .adapters import read as _read
from .adapters import repo as _repo
from .adapters.board.base import BoardBase
from .adapters.read.base import ReadBase
from .adapters.repo.base import RepoBase
from .config import Config


class Baton:
    """One project, one credential role.

    `board` is the raw adapter — `b.board.comment(id, text)` is the intended way to
    reach a plain board verb. Methods on Baton exist only where there is a RULE:
    a gate, a two-sided flow, or an alias to resolve.
    """

    def __init__(self, cfg: Config | None, role: str = "agent", *,
                 board: BoardBase | None = None):
        self.cfg = cfg
        self.role = role
        self._board = board          # injectable: tests pass a fake, no network

    # ---- the sides ----
    @property
    def board(self) -> BoardBase:
        """Cached: discovery caches ids per instance, so handing out a fresh adapter
        per call would re-discover the board on every verb."""
        if self._board is None:
            self._board = _board.get(self.cfg, self.role)
        return self._board

    def repo(self, name: str | None = None) -> RepoBase:
        """The code host for `name` (default: the project's own repo). Not cached:
        a multi-repo project asks about several, one at a time."""
        return _repo.get(self.cfg, name, self.role)

    def read(self, kind: str, **kw) -> ReadBase:
        """A read-only migration source."""
        return _read.get(kind, **kw)

    # ---- rules ----
    def stage_for(self, verb: str) -> str:
        return _board.verb_stage(self.cfg, verb)

    def advance(self, item_id: str, to: str) -> str:
        """Move an item, with both stage rules applied: the verify gate refuses a
        jump over verification, and a backward move gets flagged for review. Returns
        the stage moved to."""
        prev = self.board.get(item_id).stage
        _board.require_verify(self.board, self.cfg, item_id, prev, to)
        self.board.set_stage(item_id, to)
        _board.flag_backward(self.board, self.cfg, item_id, prev, to)
        return to

    def advance_verb(self, verb: str, item_id: str) -> str:
        """`approve` / `start` / `verify` / `ship` — the verb's stage for THIS
        project, then the same rules as `advance`."""
        return self.advance(item_id, self.stage_for(verb))
