"""Backend adapter factory."""
from __future__ import annotations

from ..base import Adapter, BatonError
from ..config import Config


def get_adapter(cfg: Config) -> Adapter:
    if cfg.backend == "github":
        from .github import GitHubAdapter
        return GitHubAdapter(cfg.target)
    if cfg.backend == "plane":
        from .plane import PlaneAdapter
        return PlaneAdapter(cfg.target)
    raise BatonError(f"unknown backend {cfg.backend!r}")
