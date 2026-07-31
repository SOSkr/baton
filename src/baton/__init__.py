"""baton — work-item lifecycle from idea to shipped.

The version is NOT written here: it is derived, so that the number a user is shown and
the number the package was built with cannot disagree. See `baton/version.py`.
"""
from .version import resolve as _resolve

__version__ = _resolve()
