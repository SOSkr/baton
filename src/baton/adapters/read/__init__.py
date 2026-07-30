"""The READ role: an old tracker being migrated OFF. Read-only, temporary.

It lives in its own package so "this one cannot write" is a structural fact rather
than a runtime question — nobody has to ask before calling. Delete the provider once
the migration it served is done.
"""
from __future__ import annotations

from .. import registry
from .base import ReadBase

# `--from-github` reads a GitHub *Projects* board. The short name stays accepted
# because that is what the flag and the config's `migrate_from` have always said.
_ALIASES = {"github": "github_projects"}


def get(kind: str, **kw) -> ReadBase:
    """A read-only migration source. `kw` is the source's own coordinates
    (repo, project, owner) — they come from flags or `config.migrate_from`."""
    return registry.resolve("read", _ALIASES.get(kind, kind))(**kw)
