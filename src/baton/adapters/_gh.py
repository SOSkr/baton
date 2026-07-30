"""Shared `gh` shell-out. Used by the GitHub repo client and the GitHub Projects
migration source — same binary, same credential, two different jobs."""
from __future__ import annotations

import json
import os
import re
import subprocess

from ..base import BatonError

_STATUS = re.compile(r"HTTP (\d{3})")


class GhError(BatonError):
    """A failed `gh` call, carrying the HTTP status when there was one.

    The status is the whole point: "does not exist" (404) and "you may not look"
    (403) are different answers, and code that cannot tell them apart will happily
    conclude a repo it cannot read is a repo it should create.
    """

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def use_token(token: str | None) -> None:
    """`gh` reads GH_TOKEN from the environment; setting it is how a credential ROLE
    reaches every shell-out. No token → whatever `gh auth` already holds."""
    if token:
        os.environ["GH_TOKEN"] = token


def gh(*args: str, want_json: bool = False, stdin: str | None = None):
    r = subprocess.run(["gh", *args], capture_output=True, text=True, input=stdin)
    if r.returncode != 0:
        err = r.stderr.strip() or r.stdout.strip()
        m = _STATUS.search(err)
        raise GhError(f"gh {' '.join(args[:2])} failed: {err}",
                      int(m.group(1)) if m else None)
    out = r.stdout.strip()
    return json.loads(out) if want_json and out else out


def status_of(e: BaseException) -> int | None:
    """The HTTP status behind a failure, when the failure knows it. Falls back to
    reading the message so a hand-built BatonError (a test fake, an older caller)
    still answers correctly."""
    st = getattr(e, "status", None)
    if st is not None:
        return st
    m = _STATUS.search(str(e))
    return int(m.group(1)) if m else None
