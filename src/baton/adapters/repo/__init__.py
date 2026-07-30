"""The REPO role: the code host — permissions, branches, PRs. Permanent, small.

Its credential is separate from the board's, and that is not an accident: git is a
second system, and "the board answers" says nothing about whether you can push.

Rules of the role go here (written against `RepoBase` only). Today that is the
construction; branch protection and find-before-create arrive with `baton bootstrap`.
"""
from __future__ import annotations

from ...config import Config, github_token_env
from .. import registry
from .base import RepoBase

# ponytail: the provider name is a constant until `adapters.repo` exists in the config
# (next PR). It has always been GitHub in practice — what changes then is that a
# project can SAY so, not that the default moves.
_PROVIDER = "github"


def get(cfg: Config | None = None, repo: str | None = None,
        role: str = "agent") -> RepoBase:
    """The code host for `repo` (default: the project's own), as `role`."""
    import os
    name = repo or (cfg.code_repo if cfg else None)
    return registry.resolve("repo", _PROVIDER)(name, os.environ.get(github_token_env(role)))
