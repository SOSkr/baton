"""Shared `gh` shell-out. Used by the GitHub repo client and the GitHub Projects
migration source — same binary, same credential, two different jobs."""
from __future__ import annotations

import json
import os
import subprocess

from ..base import BatonError


def use_token(token: str | None) -> None:
    """`gh` reads GH_TOKEN from the environment; setting it is how a credential ROLE
    reaches every shell-out. No token → whatever `gh auth` already holds."""
    if token:
        os.environ["GH_TOKEN"] = token


def gh(*args: str, want_json: bool = False):
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise BatonError(f"gh {' '.join(args[:2])} failed: {r.stderr.strip() or r.stdout.strip()}")
    out = r.stdout.strip()
    return json.loads(out) if want_json and out else out
