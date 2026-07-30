"""Adapter roles — three packages, three different jobs.

    board/   read-write. Where the work-item state lives. This is the lifecycle.
    read/    READ-ONLY. Old trackers, read once to migrate off them.
    repo/    the code host: permissions, branches, PRs.

A source is not a degraded board — it is a different job. Separate packages make
"this one cannot write" a structural fact instead of a runtime question.

Each role package is the same shape: `base.py` is its interface, `__init__.py` its
rules and its `get()`, and every other file is one provider whose FILE NAME is the
value a config carries. `registry.py` is the only module that imports a provider.

Nothing here reaches for `core` — dependencies point one way: cli → core → adapters.
"""
