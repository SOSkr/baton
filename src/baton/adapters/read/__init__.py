"""The MIGRATION role: an old tracker being migrated OFF. Read-only, temporary.

Its credential is `$MIGRATION_TOKEN`, its own and not the board's — because during a
migration there are TWO boards at once, and moving between two instances of the same
provider would otherwise need one name for both.

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


def get(kind: str, token: str | None = None, **kw) -> ReadBase:
    """A read-only migration source. `kw` is the source's own coordinates
    (repo, project, owner) — they come from flags or `config.migrate_from`.

    `token` comes from the caller, like every other role. It used to be read straight
    from the environment inside the provider, with the variable name written into the
    adapter — the one role that bypassed `tokens:` entirely.
    """
    return registry.resolve("read", _ALIASES.get(kind, kind))(token=token, **kw)
