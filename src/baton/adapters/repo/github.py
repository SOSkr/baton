"""GitHub as a CODE HOST — not a board.

The board lives elsewhere (Plane); this is where the code, the PRs and the branch
protections are. Everything here goes through the **host's API**, never a local
working tree: `baton bootstrap` creates a repo, cuts its integration branch and
protects both branches without cloning anything.

Every call is one `gh api` away from the raw endpoint on purpose — the mapping from
baton's vocabulary to GitHub's is the only thing this file is allowed to know.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ...base import BatonError
from .._gh import gh, status_of, use_token
from .base import RepoBase

_PERMS = ("admin", "maintain", "push", "pull")
_CREATED_URL = re.compile(r"https?://[^/\s]+/([^/\s]+/[^/\s]+?)(?:\.git)?/?$", re.M)


class GitHubRepo(RepoBase):
    def __init__(self, repo: str, token: str | None = None):
        use_token(token)
        if not repo:
            raise BatonError("GitHubRepo needs a repo, 'OWNER/REPO'")
        self.repo = repo

    # ---------- discovery ----------
    def permissions(self) -> set[str]:
        perms = gh("api", f"repos/{self.repo}", "--jq", ".permissions", want_json=True) or {}
        return {k for k in _PERMS if perms.get(k)}

    def probe(self) -> str:
        """`permissions` is the whole point: it proves not just that the token works
        but WHAT it can do here. An agent token reporting admin=True means the
        credential split is decoration — doctor says so out loud."""
        login = gh("api", "user", "--jq", ".login")
        can = ", ".join(k for k in _PERMS if k in self.permissions()) or "none"
        return f"{login} on {self.repo} — {can}"

    def find(self) -> dict | None:
        try:
            r = gh("api", f"repos/{self.repo}", want_json=True)
        except BatonError as e:
            if status_of(e) == 404:
                return None
            raise           # 403 is "you may not look", which is NOT "create it"
        return {"name": r.get("full_name") or self.repo,
                "visibility": "private" if r.get("private") else "public",
                "default_branch": r.get("default_branch") or ""}

    def create(self, visibility: str) -> dict:
        """`--add-readme` is not cosmetic: a repo with no commit has no default branch,
        and the integration branch is cut from that branch's sha."""
        if visibility not in ("private", "public"):
            raise BatonError(f"visibility must be private or public, got {visibility!r}")
        out = gh("repo", "create", self.repo, f"--{visibility}", "--add-readme")
        # WHERE it landed, which is not necessarily where it was asked for: `gh` takes
        # the owner prefix, DISCARDS it, creates under the account the token belongs to
        # and exits 0. The URL it prints is the only place that says so — and reading
        # `find()` alone would call that "created but unreadable", sending someone to
        # check a repo that was never going to be there.
        #
        # Not an edge case since roles-of-credential: a root holding an agent's token
        # is a token whose account differs from the owner you declared, by design.
        landed = _CREATED_URL.findall(out.strip())
        if landed and landed[-1].lower() != self.repo.lower():
            mine, theirs = self.repo.split("/")[0], landed[-1].split("/")[0]
            raise BatonError(
                f"asked for {self.repo}, got {landed[-1]} — `gh` ignores the owner and "
                f"creates under the token's account ({theirs}). Use a token of {mine}, "
                f"or declare `repo: {landed[-1]}`. {landed[-1]} now exists.")
        found = self.find()
        if not found:                      # created, then not there: do not paper over it
            raise BatonError(f"created {self.repo} but cannot read it back — "
                             f"check it by hand before re-running")
        return found

    # ---------- branches ----------
    def branch_sha(self, ref: str) -> str | None:
        try:
            return gh("api", f"repos/{self.repo}/git/ref/heads/{ref}",
                      "--jq", ".object.sha").strip() or None
        except BatonError as e:
            if status_of(e) == 404:
                return None
            raise

    def create_branch(self, name: str, sha: str) -> bool:
        try:
            gh("api", f"repos/{self.repo}/git/refs", "-f", f"ref=refs/heads/{name}",
               "-f", f"sha={sha}")
        except BatonError as e:
            # 422 is GitHub for "reference already exists" — the expected answer on a
            # re-run, and the reason `ensure` can be called twice.
            if status_of(e) == 422 and self.branch_sha(name):
                return False
            raise
        return True

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
            except BatonError as e:
                if status_of(e) not in (404, None):
                    raise                           # 403 is not "missing"
                out[br] = "missing"                 # a branch that is not there is a
                continue                            # different problem from an open one
            out[br] = "protected" if p.strip() == "true" else "UNPROTECTED"
        return out

    def required_checks(self, branch: str) -> list[str]:
        try:
            got = gh("api", f"repos/{self.repo}/branches/{branch}", "--jq",
                     ".protection.required_status_checks.contexts // []", want_json=True)
        except BatonError as e:
            if status_of(e) == 404:
                return []
            raise
        return list(got or [])

    def protect_branch(self, branch: str, *, checks: list[str], reviews: int,
                       enforce_admins: bool) -> None:
        """One PUT with the whole policy. `required_status_checks` must be **null**
        rather than an empty contexts list when there are no checks: a protection
        requiring a check named "" waits forever for a status nobody reports."""
        body = {
            "required_pull_request_reviews": {"required_approving_review_count": reviews},
            "required_status_checks": ({"strict": False, "contexts": list(checks)}
                                       if checks else None),
            "enforce_admins": enforce_admins,
            "restrictions": None,
        }
        gh("api", "-X", "PUT", f"repos/{self.repo}/branches/{branch}/protection",
           "--input", "-", stdin=json.dumps(body))

    # ---- releasing ----
    def release_triggers(self) -> set[str]:
        """Read off the workflows' `on:`, in the checkout — not from the API.

        A workflow file is what actually decides this, and it is right here. Parsed
        with a regex rather than YAML on purpose: this reads ONE key to warn a human,
        and a warning that needs a parser to be right is a warning that will be wrong
        the day the file gets clever.
        """
        found: set[str] = set()
        wf = Path(".github/workflows")
        if not wf.is_dir():
            return found
        for f in sorted(wf.glob("*.y*ml")):
            txt = f.read_text(errors="ignore")
            head = txt.split("jobs:", 1)[0]
            if re.search(r"^\s*release:", head, re.M):
                found.add("release")
            if re.search(r"^\s*tags:", head, re.M):
                found.add("tag")
            elif re.search(r"^\s*push:", head, re.M):
                found.add("push")
        return found

    def clone(self, into: Path) -> None:
        if into.exists() and any(into.iterdir()):
            return                          # already there: bootstrap is re-runnable
        gh("repo", "clone", self.repo, str(into))

    def create_release(self, tag: str, *, target: str, title: str, notes: str) -> str:
        return gh("release", "create", tag, "--repo", self.repo, "--target", target,
                  "--title", title, "--notes", notes)

    def release_exists(self, tag: str) -> bool:
        try:
            gh("release", "view", tag, "--repo", self.repo, "--json", "tagName")
            return True
        except BatonError as e:
            if status_of(e) in (404, None):
                return False
            raise

    def create_tag(self, tag: str, *, target: str) -> None:
        sha = self.branch_sha(target)
        if sha is None:
            raise BatonError(f"cannot tag {target!r}: no such ref on {self.repo}")
        gh("api", f"repos/{self.repo}/git/refs", "-X", "POST",
           "-f", f"ref=refs/tags/{tag}", "-f", f"sha={sha}")

    def deploy_runs(self, tag: str) -> dict[str, str]:
        """Runs whose head is this tag. `status` when it has not finished, so a caller
        can tell "still going" from "went wrong" — closing items on either is what
        this is here to stop."""
        rows = gh("run", "list", "--repo", self.repo, "--branch", tag, "--limit", "20",
                  "--json", "name,status,conclusion", want_json=True) or []
        return {r["name"]: (r.get("conclusion") or r.get("status") or "?") for r in rows}

    def set_delete_branch_on_merge(self, value: bool) -> None:
        gh("api", "-X", "PATCH", f"repos/{self.repo}",
           "-F", f"delete_branch_on_merge={'true' if value else 'false'}")


# What `registry.resolve('repo', 'github')` returns. The class name is free to
# change; this constant and the FILE NAME are the contract.
ADAPTER = GitHubRepo
