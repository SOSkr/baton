"""baton config loading. Looks for .baton/config.yaml walking up from cwd.

Minimal by design — everything not here is discovered by the adapter.
See P0-design.md §4.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .base import BatonError


@dataclass
class Config:
    backend: str                              # "github" | "plane"
    target: dict = field(default_factory=dict)   # github: {repo, owner?, project?}
    labels: dict = field(default_factory=dict)   # {axes: [...]}
    stages: dict = field(default_factory=dict)   # verb->stage aliases: {approve: Approved, ...}
    review_label: str | None = None               # label applied on UNEXPECTED (backward) transitions
    path: Path | None = None                     # where it was loaded from


def find_config(start: Path | None = None) -> Path | None:
    """Walk up from `start` (cwd) looking for .baton/config.yaml."""
    cur = (start or Path.cwd()).resolve()
    for d in [cur, *cur.parents]:
        cand = d / ".baton" / "config.yaml"
        if cand.is_file():
            return cand
    return None


def load(start: Path | None = None) -> Config:
    p = find_config(start)
    if p is None:
        raise BatonError(
            "no .baton/config.yaml found (walked up from cwd). "
            "Create one — see `baton doctor` / P0-design.md §4."
        )
    data = yaml.safe_load(p.read_text()) or {}
    backend = data.get("backend")
    if backend not in ("github", "plane"):
        raise BatonError(f"config.backend must be 'github' or 'plane' (got {backend!r}) in {p}")
    return Config(
        backend=backend,
        target=data.get("target", {}) or {},
        labels=data.get("labels", {}) or {},
        stages=data.get("stages", {}) or {},
        review_label=data.get("review_label"),
        path=p,
    )
