"""Where the version number comes from. One human-edited source: `pyproject.toml`.

The number used to be written twice — here and in the packaging metadata — and the two
drifted: PyPI served 0.3.0 while `baton doctor` printed 0.1.0 to whoever ran it, and
nothing failed. So there is exactly one place a person edits, and everything else
derives from it.

**Installed metadata wins.** Someone who installed baton is the one the number is for,
and inside a wheel `pyproject.toml` does not exist, so metadata is the only thing that
can answer. Reading the source tree is the fallback for running from a checkout.

The risk that leaves is an editable install whose metadata has gone stale — it reports
a version the code no longer is. That is not silenced, it is surfaced: `mismatch()` is
what `baton doctor` prints. Silence is how the original bug survived.
"""
from __future__ import annotations

import tomllib
from importlib.metadata import PackageNotFoundError, distributions
from importlib.metadata import version as _metadata_version
from pathlib import Path

# The distribution name on PyPI. NOT the import name: `baton` was taken, so the package
# ships as `baton-board` while the module stays `baton`.
DIST = "baton-board"

# What the project was called before that rename. A checkout installed back then still
# has it, reporting a version from before the split — which is exactly the number the
# original bug printed, so it is worth naming rather than ignoring.
_FORMER_DIST = "baton"


def installed() -> str | None:
    """The version of the installed distribution, or None if it is not installed.

    Deliberately does NOT fall back to the old distribution name: a stale `baton`
    install would answer with a version predating the rename, which is worse than
    admitting there is nothing installed.
    """
    try:
        return _metadata_version(DIST)
    except PackageNotFoundError:
        return None


def from_source(start: Path | None = None) -> str | None:
    """The version in `pyproject.toml`, walking up from this file. None when there is
    no source tree — inside a wheel, there is not."""
    here = (start or Path(__file__)).resolve()
    for parent in here.parents:
        cand = parent / "pyproject.toml"
        if cand.is_file():
            try:
                return tomllib.loads(cand.read_text())["project"]["version"]
            except (OSError, ValueError, KeyError):
                return None
    return None


def resolve() -> str:
    """The version to report. Metadata first, source tree second."""
    return installed() or from_source() or "0+unknown"


def stale_former_install() -> str | None:
    """The version of a leftover `baton` distribution, if one is installed.

    Its presence is why `baton doctor` once printed 0.1.0 from a checkout that said
    0.3.0, and it is invisible unless something looks for it by name.
    """
    for dist in distributions():
        if (dist.metadata["Name"] or "").lower() == _FORMER_DIST:
            return dist.version
    return None


def mismatch() -> str | None:
    """A one-line explanation when the version reported is not the version of the code
    around it, or None when everything agrees.

    Two ways that happens, and both are quiet by nature:
    an editable install whose metadata was written before the last bump, and a
    leftover distribution under the project's former name.
    """
    have, src = installed(), from_source()
    if have and src and have != src:
        return (f"installed {DIST} says {have}, but this source tree says {src} — "
                f"re-install it (`pip install -e .`) or you are reading a stale number")
    former = stale_former_install()
    if former:
        return (f"a leftover {_FORMER_DIST!r} distribution ({former}) is installed; the "
                f"project ships as {DIST!r} now. Harmless, but `pip uninstall "
                f"{_FORMER_DIST}` removes a confusing version from the environment")
    return None
