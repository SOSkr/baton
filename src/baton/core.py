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
from .adapters.board import DEFAULT_STAGES  # noqa: F401 — re-exported for cli
from .adapters import read as _read
from .adapters import repo as _repo
from .adapters.board.base import BoardBase
from .adapters.read.base import ReadBase
from .adapters.repo.base import RepoBase
from .base import BatonError
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

    # ---- bootstrap: the one flow that spans both sides ----
    def plan(self) -> dict:
        """What bootstrap WOULD do, read with the current credential. No writes, so no
        admin needed — this is what `--dry-run` prints, and the answer to the typo
        problem: a repo name with a letter too many shows up here as "would create"
        before anything exists."""
        repo_name = self.cfg.code_repo
        integration, production = self.cfg.git["integration"], self.cfg.git["production"]
        out: dict = {"dry_run": True, "repo": {"name": repo_name}, "board": {}}

        found = self.repo().find() if repo_name else None
        out["repo"]["state"] = "exists" if found else "would create"
        if found:
            out["repo"]["visibility"] = found["visibility"]
            out["branch"] = {"name": integration,
                             "state": "exists" if self.repo().branch_sha(integration)
                                      else f"would create from {found['default_branch']}"}
        else:
            out["branch"] = {"name": integration, "state": "would create"}
        out["protections"] = {"repos": self.cfg.all_repos,
                              "branches": list(dict.fromkeys([integration, production])),
                              "state": "would apply"}

        wanted = _board.wanted_stages(self.cfg)
        project = self.board.find_project()
        out["board"] = {"identifier": self.cfg.target.get("project"),
                        "state": "exists" if project else "would create",
                        "stages": {}, "extra": []}
        have = self.board.stage_groups() if project else {}
        lower = {k.lower(): v for k, v in have.items()}
        for name, group in wanted:
            got = lower.get(name.lower())
            out["board"]["stages"][name] = (
                f"would create ({group})" if got is None
                else "exists" if not got or got == group
                else f"exists — group is {got!r}, config wants {group!r}")
        out["board"]["extra"] = [n for n in have
                                 if n.lower() not in {w.lower() for w, _ in wanted}]
        return out

    def bootstrap(self, *, project_name: str | None = None, checks: list[str] | None = None,
                  reviews: int = 1, enforce_admins: bool = False,
                  prune: bool = False) -> dict:
        """Create the project: the repo, its integration branch, the protections, the
        board and its stages. ONE call, four steps, each idempotent.

        Order is deliberate: repo, then protections, then board. If the protections
        cannot be applied that is worth knowing BEFORE a board exists — the credential
        split is the thing this whole step is for.

        Nothing is rolled back. `created` lists exactly what this run brought into
        existence, so a caller that has to undo something is told what, instead of a
        delete being attempted automatically on a `find` that may simply have been
        unauthorised.
        """
        cfg = self.cfg
        integration, production = cfg.git["integration"], cfg.git["production"]
        report: dict = {"dry_run": False, "created": []}

        # --- repo side. Writes go on the ADMIN credential; a missing GH_ADMIN_TOKEN
        # falls through to whatever `gh auth` holds and is reported by the admin gate
        # below, rather than failing before anything is inspected.
        if not cfg.code_repo:
            raise BatonError("bootstrap needs to know the repo (config `repo:`, or --repo)")
        rp = _repo.get(cfg, None, "admin")
        facts, made = _repo.ensure(rp, cfg.visibility or "private")
        report["repo"] = {"name": facts["name"], "visibility": facts["visibility"],
                          "state": "created" if made else "existed"}
        if made:
            report["created"].append(f"repo {facts['name']} (undo: gh repo delete {facts['name']})")

        state, cut = _repo.ensure_branch(rp, integration, base=facts["default_branch"])
        report["branch"] = {"name": integration, "state": state}
        if cut:
            report["created"].append(f"branch {integration} on {facts['name']}")

        # EVERY repo the project declares, not just the one being created. A multi-repo
        # project that protects one of three has protected nothing that matters, and the
        # config already knows the list — so there is no flag to forget.
        report["protections"] = {}
        for name in cfg.all_repos:
            ad = rp if name == facts["name"] else _repo.get(cfg, name, "admin")
            report["protections"][name] = _repo.protect(
                ad, [integration, production], checks=checks, reviews=reviews,
                enforce_admins=enforce_admins)

        # --- board side. Creation is an admin act on this side too, and here a missing
        # admin credential is a hard stop (config.resolve_token), which is correct: a
        # board created by the agent token is a board the agent can reconfigure.
        bd = _board.get(cfg, "admin")
        board_report = _board.ensure(bd, project_name or cfg.target.get("project") or "",
                                     _board.wanted_stages(cfg))
        if board_report["created"]:
            ident = board_report["project"].get("identifier")
            report["created"].append(f"board project {ident}")
        if prune and board_report["extra"]:
            board_report["pruned"] = _board.prune_stages(bd, board_report["extra"])
        report["board"] = board_report
        return report
