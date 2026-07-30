"""Name -> class, by convention. The ONE place that imports an implementation.

`adapters: {board: plane}` in the config means `adapters/board/plane.py`, which
exports `ADAPTER`. So adding a backend is adding a file: nothing to register, no list
to keep in sync with the directory it describes.

That makes the FILE NAME public API. Keep them snake_case and equal to the value a
config would carry (`plane`, `github`, `github_projects`).
"""
from __future__ import annotations

import importlib
from pathlib import Path

from ..base import BatonError

ROLES = ("board", "repo", "read")


def available(role: str) -> list[str]:
    """Which providers exist for `role` — read off the directory, so it cannot
    disagree with what is actually importable."""
    d = Path(__file__).with_name(role)
    return sorted(p.stem for p in d.glob("*.py")
                  if not p.stem.startswith("_") and p.stem != "base")


def resolve(role: str, name: str) -> type:
    """The adapter class for `name` in `role`.

    Errors say what DOES exist — a typo'd backend is the most likely way to get here,
    and "unknown backend 'plana'" without the list leaves the reader guessing.
    """
    if role not in ROLES:
        raise BatonError(f"unknown adapter role {role!r} (have: {', '.join(ROLES)})")
    if not name:
        raise BatonError(f"no {role} adapter configured. Set `adapters.{role}` in "
                         f".baton/config.yaml (have: {', '.join(available(role))})")
    try:
        mod = importlib.import_module(f"{__package__}.{role}.{name}")
    except ImportError as e:
        # A provider whose own imports are broken must not read as "does not exist".
        if name in available(role):
            raise BatonError(f"{role} adapter {name!r} failed to import: {e}") from e
        raise BatonError(f"unknown {role} adapter {name!r} "
                         f"(have: {', '.join(available(role)) or '(none)'})") from e
    try:
        return mod.ADAPTER
    except AttributeError as e:
        raise BatonError(f"{role}/{name}.py has no ADAPTER — every adapter module "
                         f"exports its class as `ADAPTER = <TheClass>`") from e
