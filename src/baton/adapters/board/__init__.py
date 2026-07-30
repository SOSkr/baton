"""The BOARD role: read-write, permanent. Where the work-item lifecycle lives.

This module holds the rules that are true of EVERY board and of no provider in
particular — stage ordering, the verify gate, the verb aliases. They are written
against `BoardBase` and the config, and against nothing else: importing a concrete
provider here is the one thing this layer may never do (`registry` is how a class is
reached, and `tests/test_frontier.py` fails the build if that slips).
"""
from __future__ import annotations

from ...base import BatonError
from ...config import Config, resolve_token
from .. import registry
from .base import BoardBase

# Lifecycle verb -> stage name, when the project declares no alias. The verbs are
# baton's; the column names are the project's, which is why `config.stages` can
# rename any of them.
_DEFAULT_STAGE = {"approve": "Approved", "start": "In Progress",
                  "verify": "Verify", "ship": "Deployed"}


def get(cfg: Config, role: str = "agent") -> BoardBase:
    """The board, authenticated as `role` (agent | admin)."""
    return registry.resolve("board", cfg.backend)(cfg.target, resolve_token(cfg, role))


def verb_stage(cfg: Config, verb: str) -> str:
    """Resolve a lifecycle verb to a board stage name (config alias or default)."""
    return cfg.stages.get(verb, _DEFAULT_STAGE[verb])


def require_verify(ad: BoardBase, cfg: Config, item_id: str,
                   prev_stage: str | None, target_stage: str) -> None:
    """Refuse a move that jumps OVER the verify stage.

    Opt-in: only when the project declares `stages.verify`. It gates the STAGE, not
    the work — nothing stops two `advance` calls in a row. What it buys is that
    skipping verification stops being an oversight nobody notices and becomes a
    deliberate move, recorded in the board's own history.
    """
    if "verify" not in cfg.stages or not prev_stage:
        return
    verify_stage = cfg.stages["verify"]
    try:
        order = [s.lower() for s in ad.list_stages()]
        v = order.index(verify_stage.lower())
        p, t = order.index(prev_stage.lower()), order.index(target_stage.lower())
    except (BatonError, ValueError):
        return          # unknown stage names — not our call to block on
    if p < v < t:
        raise BatonError(
            f"#{item_id}: {prev_stage} → {target_stage} skips {verify_stage!r}. "
            f"Run the baton-verify skill — it checks the diff against the acceptance "
            f"criteria and the scope boundary, and advances the item itself. To move "
            f"it without verifying, go through {verify_stage!r} explicitly.")


def flag_backward(ad: BoardBase, cfg: Config, item_id: str,
                  prev_stage: str | None, target_stage: str) -> None:
    """Flag an UNEXPECTED (backward) stage transition — e.g. Approved→Review — with
    `config.review_label`, so the user evaluates it. Normal forward moves (Review→
    Approved→In Progress→...) and creation are NOT flagged. Never fails the move."""
    if not cfg.review_label or not prev_stage:
        return
    try:
        order = [s.lower() for s in ad.list_stages()]
        p, t = prev_stage.lower(), target_stage.lower()
        if p in order and t in order and order.index(t) < order.index(p):
            ad.set_labels(item_id, add=[cfg.review_label])
    except BatonError:
        pass
