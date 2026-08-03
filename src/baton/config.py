"""baton config loading. Looks for .baton/config.yaml walking up from cwd.

Minimal by design — everything not here is discovered by the adapter.
"""
from __future__ import annotations

import json
import os
from dataclasses import InitVar, dataclass, field
from pathlib import Path

import yaml

from .base import BatonError


# Env var NAMES. Tokens themselves NEVER live in config.yaml.
#
# THE CODE HOST has two, and the split is real: agent writes code, admin approves and
# merges — GitHub itself refuses to let a PR author approve their own PR.
_DEFAULT_TOKENS = {
    "github": {"agent": "GH_TOKEN", "admin": "GH_ADMIN_TOKEN"},
}

# THE BOARD has ONE. Not a simplification — the honest shape.
#
# A board credential belongs to a user, and what it may do is the BOARD's answer, from
# that user's role. baton gets no vote, so it does not model two. Pointing a second
# variable at a board separates nothing: it only picks, and nothing ever checked that
# the one called `admin` could do more. On the code host that check exists and the host
# enforces it; here it was an unverified claim — which is what `doctor` exists to kill.
#
# The rule, once: A SEPARATION IS ONLY REAL WHEN A THIRD PARTY ENFORCES IT.
#
# If that credential cannot create a project, the project gets created by hand and
# `bootstrap` adopts it — which it already knows how to do. There is no privileged mode
# to ask for: the permission belongs to the user, not to baton.
_BOARD_TOKEN = {
    "plane": "PLANE_API_KEY",
    "kanboard": "KANBOARD_TOKEN",
}
BACKENDS = ("plane", "kanboard")

# What each board needs in `target` before its config is worth writing. Lives here
# next to the token names, for the same reason: it is per-provider knowledge that the
# CLI needs BEFORE any adapter exists to ask. Kanboard has no workspace — it has a
# project name — so this used to reject a perfectly good Kanboard config with Plane's
# error message.
_REQUIRED_TARGET = {
    "plane": ("base_url", "workspace", "project"),
    "kanboard": ("base_url", "project"),
}
ROLES = ("agent", "admin")

# Which provider serves each adapter role. The value is the FILE NAME under
# `adapters/<role>/` — see adapters/registry.py. Only the board has ever varied; the
# other two get a default so no existing config has to be touched to keep working.
_DEFAULT_ADAPTERS = {"repo": "github", "read": "github_projects"}

# The two branches baton's skills reach for. Names vary per project — trunk-based
# repos have no integration branch at all, and `main` is as common as `master` — so
# they are config, not constants baked into a skill.
DEFAULT_GIT = {"integration": "develop", "production": "master"}


# Where agent runtimes keep their MCP server definitions. baton reads these files for
# one thing only: the NAMES of servers whose env declares a variable this project needs
# and the shell does not have. The VALUE is never read — `doctor` prints where the
# credential lives and the command to export it, and the user runs that command. A CLI
# that quietly picked up a token from another program's config would be a credential
# nobody chose, used with a role nobody declared.
_MCP_CONFIGS = ("~/.claude.json", ".mcp.json")


def credential_sources(var: str) -> list[tuple[str, Path, list[str]]]:
    """MCP servers whose env declares `var`, as (server name, file, key path).

    The key path is what a caller needs to build a copy-pasteable command; it is where
    the value IS, not the value.
    """
    out: list[tuple[str, Path, list[str]]] = []
    for raw in _MCP_CONFIGS:
        path = Path(raw).expanduser()
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue                      # no config there, or not ours to parse
        for prefix, block in _mcp_blocks(data):
            for name, server in (block or {}).items():
                if var in ((server or {}).get("env") or {}):
                    out.append((name, path, [*prefix, name, "env", var]))
    return out


def _mcp_blocks(data: dict):
    """Every `mcpServers` map in an agent config, with the keys that lead to it.
    Claude Code keeps a global one and one per project directory."""
    if isinstance(data.get("mcpServers"), dict):
        yield ["mcpServers"], data["mcpServers"]
    for proj, cfg in (data.get("projects") or {}).items():
        if isinstance((cfg or {}).get("mcpServers"), dict):
            yield ["projects", proj, "mcpServers"], cfg["mcpServers"]


def github_token_env(role: str) -> str:
    """GitHub's var for `role`, regardless of which backend holds the board. With a
    Plane board, git is still GitHub and still needs its own credential."""
    return _DEFAULT_TOKENS["github"][role]


@dataclass
class Config:
    target: dict = field(default_factory=dict)   # github: {repo, owner?, project?}
    labels: dict = field(default_factory=dict)   # {axes: [...]}
    stages: dict = field(default_factory=dict)   # verb->stage aliases: {approve: Approved, ...}
    tokens: dict = field(default_factory=dict)   # role->ENV VAR NAME: {agent: GH_TOKEN, admin: GH_ADMIN_TOKEN}
    repo: str | None = None                       # OWNER/REPO where the CODE lives, when the board is elsewhere
    git: dict = field(default_factory=lambda: dict(DEFAULT_GIT))  # {integration, production}
    repos: dict = field(default_factory=dict)     # multi-repo project: {area-label-value: OWNER/REPO}
    migrate_from: dict = field(default_factory=dict)  # read-only source board: {repo, project}
    review_label: str | None = None               # label applied on UNEXPECTED (backward) transitions
    memory: str | None = None                     # this project's name in the session-memory store, if any
    projects: dict = field(default_factory=dict)  # sibling boards: {name: path to its .baton/config.yaml or its dir}
    adapters: dict = field(default_factory=dict)  # role -> provider file name: {board: plane, repo: github}
    # `backend: plane` is the older spelling of `adapters.board`. It is accepted here
    # forever — it is on people's disks — but it is NOT stored: it is translated on the
    # way in, and `cfg.backend` below reads back out of `adapters`. One fact, one home,
    # so the two spellings cannot drift apart.
    backend: InitVar[str | None] = None
    board_stages: list = field(default_factory=list)  # stages the board MUST have (bootstrap creates them)
    visibility: str | None = None                 # new repos: private | public (bootstrap only)
    path: Path | None = None                     # where it was loaded from

    def __post_init__(self, backend):
        self.adapters = {**_DEFAULT_ADAPTERS, **(self.adapters or {})}
        if backend and not self.adapters.get("board"):
            self.adapters["board"] = backend

    def token_env(self, role: str | None = None) -> str:
        """The env var NAME holding THE board credential. `role` is accepted and
        ignored: a board has one credential, and which verb is running does not change
        whose it is.

        A `tokens:` written before this had a key per role. It is still read — those
        were never two credentials, so either name resolves to the same thing.
        """
        t = self.tokens
        if isinstance(t, str) and t:
            return t
        if isinstance(t, dict) and t:
            return t.get("agent") or t.get("admin") or _BOARD_TOKEN[self.backend]
        return _BOARD_TOKEN[self.backend]

    @property
    def code_repo(self) -> str | None:
        """The project's default repo. Single-repo projects have only this."""
        return self.repo or self.target.get("repo")

    @property
    def all_repos(self) -> list[str]:
        """Every repo this project touches — what `doctor` has to check, since a
        credential can reach one repo and not another."""
        seen = [r for r in [self.code_repo, *self.repos.values()] if r]
        return list(dict.fromkeys(seen))

    def repo_for(self, area: str | None) -> str | None:
        """Which repo an `area:<x>` label points at. Singular on purpose: an item
        that spans repos carries a Checklist with ONE BOX PER REPO, and each box
        names its own area — so per box it is always one repo."""
        if area and area in self.repos:
            return self.repos[area]
        return self.code_repo

    def repo_for_labels(self, labels: list[str]) -> str | None:
        """The repo implied by an item's labels (the first `area:<x>` that maps)."""
        for lb in labels or []:
            if lb.lower().startswith("area:"):
                hit = self.repos.get(lb.split(":", 1)[1])
                if hit:
                    return hit
        return self.code_repo


# Defined after the decorator on purpose: a property assigned inside a dataclass body
# would be read as the field's default value.
Config.backend = property(lambda self: self.adapters.get("board"))


def resolve_token(cfg: Config, role: str | None = None) -> str | None:
    """The board credential. One, whatever verb is asking.

    Missing is fine and `doctor` reports it: the backend may have its own auth to fall
    back on, and dying at the door of every verb would be worse than saying it once.
    `role` is accepted so existing callers keep working; it changes nothing, because
    there is nothing for it to choose between.
    """
    return os.environ.get(cfg.token_env())


def find_config(start: Path | None = None) -> Path | None:
    """Walk up from `start` (cwd) looking for .baton/config.yaml."""
    cur = (start or Path.cwd()).resolve()
    for d in [cur, *cur.parents]:
        cand = d / ".baton" / "config.yaml"
        if cand.is_file():
            return cand
    return None


def load(start: Path | None = None) -> Config:
    p = find_config(start)
    if p is None:
        raise BatonError(
            "no .baton/config.yaml found (walked up from cwd). "
            "Create one — see README.md § Config."
        )
    return load_file(p)


def load_file(p: Path) -> Config:
    data = yaml.safe_load(p.read_text()) or {}
    adapters = data.get("adapters", {}) or {}
    # `backend:` is the older spelling of `adapters.board`. Both are read, forever:
    # every config written before this key existed is on someone's disk.
    backend = data.get("backend") or adapters.get("board")
    if backend == "github":
        raise BatonError(
            f"backend 'github' (GitHub Projects) is no longer a board backend, in {p}. "
            f"GitHub is now the code host only. To move an old board across, see the "
            f"baton-migrate skill: `baton export --from-github OWNER/REPO --project N`.")
    if backend not in BACKENDS:
        raise BatonError(f"config.backend must be one of {', '.join(BACKENDS)} "
                         f"(got {backend!r}) in {p}")
    return Config(
        backend=backend,
        adapters=adapters,
        board_stages=data.get("board_stages", []) or [],
        visibility=data.get("visibility"),
        target=data.get("target", {}) or {},
        labels=data.get("labels", {}) or {},
        stages=data.get("stages", {}) or {},
        tokens=data.get("tokens", {}) or {},
        repo=data.get("repo"),
        git={**DEFAULT_GIT, **(data.get("git") or {})},
        repos=data.get("repos", {}) or {},
        migrate_from=data.get("migrate_from", {}) or {},
        review_label=data.get("review_label"),
        memory=data.get("memory"),
        projects=data.get("projects", {}) or {},
        path=p,
    )


# The keys `baton bootstrap` OWNS. Everything else in the file — `tokens`, `memory`,
# `projects`, the `stages` verb aliases, the multi-repo `repos` map — is the human's,
# and is merged through untouched. Writing the whole file instead would silently drop
# work nobody can recover.
_OWNED = ("adapters", "target", "repo", "git", "visibility", "board_stages")


def write_config(board: str, target: dict, *, repo: str | None = None,
                 git: dict | None = None, visibility: str | None = None,
                 board_stages: list | None = None, force: bool = False,
                 root: Path | None = None) -> tuple[Path, dict, bool]:
    """Write/merge .baton/config.yaml under `root` (cwd).

    Returns `(path, changed, comments_lost)`. Nothing is printed here — the caller owns
    output — but the caller needs both facts: WHICH values it replaced, and whether the
    file it rewrote had comments (`yaml.safe_dump` cannot keep them).

    A value that would CHANGE an existing one needs `--force`. A rerun passing the same
    values changes nothing and so never asks — which is what makes bootstrap resumable
    after a half-failure.
    """
    p = (root or Path.cwd()) / ".baton" / "config.yaml"
    missing = [k for k in _REQUIRED_TARGET.get(board, ()) if not target.get(k)]
    if missing:
        flags = ", ".join("--" + ("board" if k == "project" else k.replace("_", "-"))
                          for k in missing)
        raise BatonError(f"{board} needs {flags}")

    raw = p.read_text() if p.is_file() else ""
    existing = (yaml.safe_load(raw) or {}) if raw else {}
    # Only the board is named: `repo` and `read` have defaults, and a config that does
    # not repeat a default is a config with less to contradict.
    new = {"adapters": {"board": board}, "target": target}
    for key, val in (("repo", repo), ("git", git), ("visibility", visibility),
                     ("board_stages", board_stages)):
        if val:
            new[key] = val

    # A dict-valued key is MERGED, not replaced, before deciding anything changed:
    # writing `{board: plane}` over `{board: plane, repo: github}` sets no new value, it
    # just says less. Comparing raw dicts would call that a conflict and stop a re-run
    # that was meant to resume — and re-running is the documented way to recover from a
    # half-failed bootstrap.
    for key, val in list(new.items()):
        if isinstance(val, dict) and isinstance(existing.get(key), dict):
            new[key] = {**existing[key], **val}
    changed = {k: (existing[k], v) for k, v in new.items()
               if k in existing and existing[k] != v}
    if changed and not force:
        lines = "\n".join(f"  {k}: {old!r} -> {want!r}" for k, (old, want) in changed.items())
        raise BatonError(
            f"{p} already says something different:\n{lines}\n"
            f"Re-run with --force to replace those values, or drop the flags to keep them.")

    merged = {**existing, **new}
    # Owned keys first, in a stable order, so a human diff of this file reads.
    ordered = {k: merged[k] for k in _OWNED if k in merged}
    ordered.update({k: v for k, v in merged.items() if k not in ordered})
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(ordered, sort_keys=False, default_flow_style=False))
    return p, changed, "#" in raw


def load_project(name_or_path: str, base: Config) -> Config:
    """Load a SIBLING project's config, so one command can ask about another
    board without cd-ing into it.

    `name_or_path` is either a key of `base.projects` or a path — to a
    config file, or to any directory inside that project (the usual upward
    walk applies from there). Relative paths resolve from the PROJECT root,
    i.e. the directory holding `.baton/`, so siblings read as `../other-repo`.
    """
    raw = base.projects.get(name_or_path, name_or_path)
    root = base.path.parent.parent if base.path else Path.cwd()
    cand = Path(raw).expanduser()
    if not cand.is_absolute():
        cand = (root / cand).resolve()

    if cand.is_file():
        return load_file(cand)
    if cand.is_dir():
        return load(cand)
    known = ", ".join(sorted(base.projects)) or "(none declared in config.projects)"
    raise BatonError(f"project {name_or_path!r} not found: {cand} does not exist. Known: {known}")
