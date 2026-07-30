"""GitHub as a CODE HOST — not a board.

The board lives elsewhere (Plane); this is where the code, the PRs and the branch
protections are. Deliberately tiny: `baton-verify` and `baton-ship` do their git work
in the shell (`gh pr diff`, `ship-pr.sh`), so the only thing Python needs from GitHub
today is proving what a credential can actually do. Do not grow a portable PR
abstraction here until a second code host exists to contrast it with.
"""
from __future__ import annotations

from ...base import BatonError
from .base import RepoBase
from .._gh import gh, use_token


class GitHubRepo(RepoBase):
    def __init__(self, repo: str, token: str | None = None):
        use_token(token)
        if not repo:
            raise BatonError("GitHubRepo needs a repo, 'OWNER/REPO'")
        self.repo = repo

    def branch_protection(self, branches: list[str]) -> dict[str, str]:
        """State of each branch: `protected`, `UNPROTECTED`, or `missing`.

        Deliberately separate from `probe()`: protection is a property of the REPO,
        not of a credential, so reporting it once per token role would be noise.

        `.protected` comes back on the plain branch endpoint, which needs no admin —
        reading the protection *rules* does, but reading whether any exist does not.
        That matters: the agent credential can surface a hole it cannot fix.
        """
        out: dict[str, str] = {}
        for br in dict.fromkeys(branches):          # dedupe, keep order (trunk-based)
            try:
                p = gh("api", f"repos/{self.repo}/branches/{br}", "--jq", ".protected")
            except BatonError:
                out[br] = "missing"                 # a branch that is not there is a
                continue                            # different problem from an open one
            out[br] = "protected" if p.strip() == "true" else "UNPROTECTED"
        return out

    def probe(self) -> str:
        """`permissions` is the whole point: it proves not just that the token works
        but WHAT it can do here. An agent token reporting admin=True means the
        credential split is decoration — doctor says so out loud."""
        login = gh("api", "user", "--jq", ".login")
        perms = gh("api", f"repos/{self.repo}", "--jq", ".permissions", want_json=True) or {}
        can = ", ".join(k for k in ("admin", "maintain", "push", "pull") if perms.get(k)) or "none"
        return f"{login} on {self.repo} — {can}"


# What `registry.resolve('repo', 'github')` returns. The class name is free to
# change; this constant and the FILE NAME are the contract.
ADAPTER = GitHubRepo
