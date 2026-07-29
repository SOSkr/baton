"""Runnable check for the GitHub code-host client — no network.

`gh` is replaced by a recorder, so what is under test is the client's own mapping of
API answers to states, not the subprocess. Run: `python tests/test_repo_host.py` or
`pytest`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from baton.adapters.repos import github as gh_mod  # noqa: E402
from baton.base import BatonError  # noqa: E402


def _fake_gh(answers):
    """Replace the `gh` shell-out. `answers` maps branch name -> value, where an
    Exception instance is raised instead of returned (a 404 from the real CLI)."""
    calls = []

    def fake(*args, want_json=False):
        calls.append(" ".join(args))
        br = args[1].rsplit("/", 1)[-1] if len(args) > 1 else ""
        v = answers.get(br, "false")
        if isinstance(v, Exception):
            raise v
        return v

    return fake, calls


def test_protection_states_are_distinguished():
    """`missing` and `UNPROTECTED` are different problems: a branch that is not there
    is a setup mistake, an open one is a security hole. Collapsing them would send
    someone to fix the wrong thing."""
    orig = gh_mod.gh
    try:
        gh_mod.gh, calls = _fake_gh({
            "master": "true",
            "develop": "false",
            "nope": BatonError("gh: Not Found (HTTP 404)"),
        })
        repo = gh_mod.GitHubRepo("acme/app")
        assert repo.branch_protection(["master", "develop", "nope"]) == {
            "master": "protected",
            "develop": "UNPROTECTED",
            "nope": "missing",
        }
        assert len(calls) == 3
    finally:
        gh_mod.gh = orig


def test_trunk_based_asks_once():
    """A project whose integration and production branch are the same must not be
    reported twice, nor cost two API calls."""
    orig = gh_mod.gh
    try:
        gh_mod.gh, calls = _fake_gh({"main": "true"})
        got = gh_mod.GitHubRepo("acme/app").branch_protection(["main", "main"])
        assert got == {"main": "protected"}
        assert len(calls) == 1
    finally:
        gh_mod.gh = orig


def test_needs_a_repo():
    try:
        gh_mod.GitHubRepo("")
        assert False, "expected BatonError"
    except BatonError as e:
        assert "OWNER/REPO" in str(e)


if __name__ == "__main__":
    test_protection_states_are_distinguished()
    test_trunk_based_asks_once()
    test_needs_a_repo()
    print("ok")
