"""baton config loading. Looks for .baton/config.yaml walking up from cwd.

Minimal by design — everything not here is discovered by the adapter.
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
    memory: str | None = None                     # this project's name in the session-memory store, if any
    projects: dict = field(default_factory=dict)  # sibling boards: {name: path to its .baton/config.yaml or its dir}
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
            "Create one — see README.md § Config."
        )
    return load_file(p)


def load_file(p: Path) -> Config:
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
        memory=data.get("memory"),
        projects=data.get("projects", {}) or {},
        path=p,
    )


def load_project(name_or_path: str, base: Config) -> Config:
    """Load a SIBLING project's config, so one command can ask about another
    board without cd-ing into it.

    `name_or_path` is either a key of `base.projects` or a path — to a
    config file, or to any directory inside that project (the usual upward
    walk applies from there). Relative paths resolve from the PROJECT root,
    i.e. the directory holding `.baton/`, so siblings read as `../other-repo`.
    """
    raw = base.projects.get(name_or_path, name_or_path)
    root = base.path.parent.parent if base.path else Path.cwd()
    cand = Path(raw).expanduser()
    if not cand.is_absolute():
        cand = (root / cand).resolve()

    if cand.is_file():
        return load_file(cand)
    if cand.is_dir():
        return load(cand)
    known = ", ".join(sorted(base.projects)) or "(none declared in config.projects)"
    raise BatonError(f"project {name_or_path!r} not found: {cand} does not exist. Known: {known}")
