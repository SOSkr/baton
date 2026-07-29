"""baton config loading. Looks for .baton/config.yaml walking up from cwd.

Minimal by design — everything not here is discovered by the adapter.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .base import BatonError


# Env var NAMES per credential role. Tokens themselves NEVER live in config.yaml.
# agent = write code, branches, items. admin = create/administer projects, merge.
# "github" is not a board backend — it is the code host, and still needs its own pair.
_DEFAULT_TOKENS = {
    "github": {"agent": "GH_TOKEN", "admin": "GH_ADMIN_TOKEN"},
    "plane": {"agent": "PLANE_API_KEY", "admin": "PLANE_ADMIN_API_KEY"},
}
BACKENDS = ("plane",)
ROLES = ("agent", "admin")

# The two branches baton's skills reach for. Names vary per project — trunk-based
# repos have no integration branch at all, and `main` is as common as `master` — so
# they are config, not constants baked into a skill.
_DEFAULT_GIT = {"integration": "develop", "production": "master"}


def github_token_env(role: str) -> str:
    """GitHub's var for `role`, regardless of which backend holds the board. With a
    Plane board, git is still GitHub and still needs its own credential."""
    return _DEFAULT_TOKENS["github"][role]


@dataclass
class Config:
    backend: str                              # "github" | "plane"
    target: dict = field(default_factory=dict)   # github: {repo, owner?, project?}
    labels: dict = field(default_factory=dict)   # {axes: [...]}
    stages: dict = field(default_factory=dict)   # verb->stage aliases: {approve: Approved, ...}
    tokens: dict = field(default_factory=dict)   # role->ENV VAR NAME: {agent: GH_TOKEN, admin: GH_ADMIN_TOKEN}
    repo: str | None = None                       # OWNER/REPO where the CODE lives, when the board is elsewhere
    git: dict = field(default_factory=lambda: dict(_DEFAULT_GIT))  # {integration, production}
    repos: dict = field(default_factory=dict)     # multi-repo project: {area-label-value: OWNER/REPO}
    migrate_from: dict = field(default_factory=dict)  # read-only source board: {repo, project}
    review_label: str | None = None               # label applied on UNEXPECTED (backward) transitions
    memory: str | None = None                     # this project's name in the session-memory store, if any
    projects: dict = field(default_factory=dict)  # sibling boards: {name: path to its .baton/config.yaml or its dir}
    path: Path | None = None                     # where it was loaded from

    def token_env(self, role: str) -> str:
        """The env var NAME holding the credential for `role`."""
        return self.tokens.get(role) or _DEFAULT_TOKENS[self.backend][role]

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
        for l in labels or []:
            if l.lower().startswith("area:"):
                hit = self.repos.get(l.split(":", 1)[1])
                if hit:
                    return hit
        return self.code_repo


def resolve_token(cfg: Config, role: str) -> str | None:
    """The credential for `role`, read from its env var.

    A missing `agent` credential is fine — the backend falls back to its own auth
    (`gh auth`, or its own error). A missing `admin` one is NOT: silently running an
    admin op with agent rights either fails confusingly or quietly does less than the
    caller thinks it did.
    """
    var = cfg.token_env(role)
    val = os.environ.get(var)
    if role == "admin" and not val:
        raise BatonError(
            f"--as admin needs ${var}, which is not set. Refusing to fall back to the "
            f"agent credential — set it, or run this op as the human who holds it."
        )
    return val


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
    backend = data.get("backend")
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
        target=data.get("target", {}) or {},
        labels=data.get("labels", {}) or {},
        stages=data.get("stages", {}) or {},
        tokens=data.get("tokens", {}) or {},
        repo=data.get("repo"),
        git={**_DEFAULT_GIT, **(data.get("git") or {})},
        repos=data.get("repos", {}) or {},
        migrate_from=data.get("migrate_from", {}) or {},
        review_label=data.get("review_label"),
        memory=data.get("memory"),
        projects=data.get("projects", {}) or {},
        path=p,
    )


def write_config(backend: str, target: dict, *, repo: str | None = None,
                 force: bool = False, root: Path | None = None) -> Path:
    """Write a minimal .baton/config.yaml under `root` (cwd). Everything else —
    project node id, status field id, stage option ids — stays discovered."""
    p = (root or Path.cwd()) / ".baton" / "config.yaml"
    if p.exists() and not force:
        raise BatonError(f"{p} already exists (use --force to overwrite)")
    if not (target.get("base_url") and target.get("workspace")):
        raise BatonError(f"{backend} needs --base-url and --workspace")
    data: dict = {"backend": backend, "target": target}
    if repo:
        data["repo"] = repo                  # the code host — the board knows no git
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False))
    return p


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
