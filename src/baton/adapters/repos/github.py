"""GitHub as a CODE HOST — not a board.

The board lives elsewhere (Plane); this is where the code, the PRs and the branch
protections are. Deliberately tiny: `baton-verify` and `baton-ship` do their git work
in the shell (`gh pr diff`, `ship-pr.sh`), so the only thing Python needs from GitHub
today is proving what a credential can actually do. Do not grow a portable PR
abstraction here until a second code host exists to contrast it with.
"""
from __future__ import annotations

from ...base import BatonError
from .._gh import gh, use_token


class GitHubRepo:
    def __init__(self, repo: str, token: str | None = None):
        use_token(token)
        if not repo:
            raise BatonError("GitHubRepo needs a repo, 'OWNER/REPO'")
        self.repo = repo

    def probe(self) -> str:
        """`permissions` is the whole point: it proves not just that the token works
        but WHAT it can do here. An agent token reporting admin=True means the
        credential split is decoration — doctor says so out loud."""
        login = gh("api", "user", "--jq", ".login")
        perms = gh("api", f"repos/{self.repo}", "--jq", ".permissions", want_json=True) or {}
        can = ", ".join(k for k in ("admin", "maintain", "push", "pull") if perms.get(k)) or "none"
        return f"{login} on {self.repo} — {can}"
