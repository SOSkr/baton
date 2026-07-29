"""Adapter factories — three families, three different jobs.

    boards/    read-write. Where the work-item state lives. This is the lifecycle.
    sources/   READ-ONLY. Old trackers, read once to migrate off them.
    repos/     the code host: permissions, and whatever git work Python needs.

A source is not a degraded board — it is a different job. Keeping them in separate
families makes "this one cannot write" a structural fact instead of a runtime question.

There are deliberately no `Source` / `Repo` base classes yet: with one implementation
each, an interface is a guess at a contract. The directory carries the rule until a
second implementation shows what they actually have in common.
"""
from __future__ import annotations

from ..base import Adapter, BatonError
from ..config import Config, github_token_env, resolve_token


def get_adapter(cfg: Config, role: str = "agent") -> Adapter:
    """The BOARD, authenticated as `role` (agent | admin)."""
    token = resolve_token(cfg, role)
    if cfg.backend == "plane":
        from .boards.plane import PlaneAdapter
        return PlaneAdapter(cfg.target, token)
    raise BatonError(f"unknown backend {cfg.backend!r}")


def get_repo(repo: str, role: str = "agent"):
    """The CODE HOST for `repo`. Its credential is separate from the board's — git is
    a second system, and "the board answers" says nothing about whether you can push."""
    import os
    from .repos.github import GitHubRepo
    return GitHubRepo(repo, os.environ.get(github_token_env(role)))


def get_source(kind: str, **kw):
    """A read-only migration SOURCE."""
    if kind in ("github", "github_projects"):
        from .sources.github_projects import GitHubProjectsSource
        return GitHubProjectsSource(**kw)
    raise BatonError(f"unknown migration source {kind!r}")
