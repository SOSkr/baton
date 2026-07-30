"""Runnable check for config loading and sibling-project resolution.

Builds a throwaway two-project tree in a temp dir — the shape a developer with
several repos actually has — and checks that `--project` reaches the other
board's config. Run: `python tests/test_config.py` or `pytest`.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from baton.base import BatonError  # noqa: E402
from baton.config import (github_token_env, load, load_project,  # noqa: E402
                          resolve_token, write_config)  # noqa: E402


def _write(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


_PLANE = "backend: plane\ntarget: {base_url: https://p, workspace: w, project: %s}\n"


def _tree(root: Path):
    """workspace/
         app-a/.baton/config.yaml   <- declares app-b as a sibling
         app-b/.baton/config.yaml
    """
    _write(root / "app-a" / ".baton" / "config.yaml",
           _PLANE % "APPA"
           + "repo: acme/app-a\n"
           "memory: app-a\n"
           "projects:\n"
           "  b: ../app-b\n")   # relative to the PROJECT root (the dir holding .baton/)
    _write(root / "app-b" / ".baton" / "config.yaml",
           _PLANE % "APPB" + "repo: acme/app-b\nmemory: app-b\n")


def test_loads_new_fields():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _tree(root)
        cfg = load(root / "app-a")
        assert cfg.memory == "app-a"
        assert cfg.projects == {"b": "../app-b"}


def test_sibling_by_name_and_by_path():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _tree(root)
        a = load(root / "app-a")

        by_name = load_project("b", a)
        assert by_name.code_repo == "acme/app-b" and by_name.memory == "app-b"

        # same board, addressed by path instead of by declared name
        by_path = load_project(str(root / "app-b"), a)
        assert by_path.code_repo == "acme/app-b"


def test_unknown_project_lists_known_ones():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _tree(root)
        a = load(root / "app-a")
        try:
            load_project("nope", a)
            assert False, "expected BatonError"
        except BatonError as e:
            assert "nope" in str(e) and "b" in str(e)


def test_defaults_when_fields_absent():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _write(root / ".baton" / "config.yaml",
               "backend: plane\ntarget: {workspace: w, project: P}\n")
        cfg = load(root)
        assert cfg.memory is None and cfg.projects == {}


def test_token_roles_have_defaults_and_are_overridable():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _write(root / ".baton" / "config.yaml", _PLANE % "P")
        cfg = load(root)
        assert cfg.token_env("agent") == "PLANE_API_KEY"
        assert cfg.token_env("admin") == "PLANE_ADMIN_API_KEY"
        # git is a separate system with its own pair, whatever holds the board
        assert github_token_env("agent") == "GH_TOKEN"
        assert github_token_env("admin") == "GH_ADMIN_TOKEN"

        _write(root / "p" / ".baton" / "config.yaml",
               _PLANE % "P" + "tokens: {admin: MY_ADMIN_VAR}\n")
        p = load(root / "p")
        assert p.token_env("agent") == "PLANE_API_KEY"   # default kept
        assert p.token_env("admin") == "MY_ADMIN_VAR"    # override honoured


def test_github_projects_backend_is_refused_with_a_route_forward():
    """An old config must not half-work: it fails with the migration path in the
    message, not with a confusing discovery error three verbs later."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _write(root / ".baton" / "config.yaml", "backend: github\ntarget: {repo: a/b}\n")
        try:
            load(root)
            assert False, "expected BatonError"
        except BatonError as e:
            assert "no longer a board backend" in str(e) and "baton export" in str(e)


def test_admin_role_refuses_to_fall_back_to_the_agent_credential():
    """The whole point of the split: an admin op must NOT silently run with agent
    rights. A missing agent credential is fine (the backend has its own auth)."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _write(root / ".baton" / "config.yaml", _PLANE % "P")
        cfg = load(root)
        old = os.environ.pop("PLANE_ADMIN_API_KEY", None)
        try:
            assert resolve_token(cfg, "agent") == os.environ.get("PLANE_API_KEY")
            try:
                resolve_token(cfg, "admin")
                assert False, "expected BatonError"
            except BatonError as e:
                assert "PLANE_ADMIN_API_KEY" in str(e)
            os.environ["PLANE_ADMIN_API_KEY"] = "sekret"
            assert resolve_token(cfg, "admin") == "sekret"
        finally:
            os.environ.pop("PLANE_ADMIN_API_KEY", None)
            if old is not None:
                os.environ["PLANE_ADMIN_API_KEY"] = old


def test_write_config_roundtrips_and_refuses_to_clobber():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        target = {"base_url": "https://p", "workspace": "w", "project": "APP"}
        write_config("plane", dict(target), root=root)
        cfg = load(root)
        assert cfg.backend == "plane" and cfg.target["project"] == "APP"
        try:
            write_config("plane", dict(target, project="OTHER"), root=root)
            assert False, "expected BatonError"
        except BatonError as e:
            assert "already says something different" in str(e) and "OTHER" in str(e)
        write_config("plane", dict(target, project="OTHER"), root=root, force=True)
        assert load(root).target["project"] == "OTHER"


def test_code_repo_carries_the_git_host_the_board_knows_nothing_about():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        write_config("plane", {"base_url": "https://p", "workspace": "w", "project": "APP"},
                     repo="acme/app", root=root)
        cfg = load(root)
        assert cfg.repo == "acme/app" and "repo" not in cfg.target
        assert cfg.code_repo == "acme/app"


def test_multirepo_project_resolves_the_repo_from_the_area_label():
    """A Plane project can cover several git repos; Plane knows nothing about git.
    The `area:` label on each checklist box is what says which repo a box belongs to."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _write(root / ".baton" / "config.yaml",
               _PLANE % "CANGURO"
               + "repo: acme/app\n"
               "repos:\n"
               "  engine: acme/app-engine\n"
               "  web: acme/app-web\n")
        cfg = load(root)
        assert cfg.repo_for("engine") == "acme/app-engine"
        assert cfg.repo_for("web") == "acme/app-web"
        assert cfg.repo_for("unknown") == "acme/app"   # falls back to the default
        assert cfg.repo_for(None) == "acme/app"

        assert cfg.repo_for_labels(["type:bug", "area:web"]) == "acme/app-web"
        assert cfg.repo_for_labels(["type:bug"]) == "acme/app"

        # doctor has to check every repo — a credential can reach one and not the next
        assert set(cfg.all_repos) == {"acme/app", "acme/app-engine",
                                      "acme/app-web"}


def test_migration_source_is_project_data_not_skill_data():
    """Skills are installed globally; which old board a project came from is not
    something a globally-installed skill can know. It lives in the project config."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _write(root / ".baton" / "config.yaml",
               _PLANE % "AOTBOT" + "migrate_from: {repo: acme/legacy, project: 3}\n")
        cfg = load(root)
        assert cfg.migrate_from == {"repo": "acme/legacy", "project": 3}

        # a project that never migrated simply has none
        _write(root / "other" / ".baton" / "config.yaml", _PLANE % "X")
        assert load(root / "other").migrate_from == {}


def test_git_branch_names_are_config_with_defaults():
    """Branch names baked into a SKILL.md are wrong for every project that names
    things differently — and the skills are installed globally, so they cannot be
    edited per project. Defaults exist so a project that agrees with them says
    nothing; a trunk-based repo points both at the same branch."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _write(root / ".baton" / "config.yaml", _PLANE % "P")
        cfg = load(root)
        assert cfg.git == {"integration": "develop", "production": "master"}

        _write(root / "t" / ".baton" / "config.yaml",
               _PLANE % "P" + "git: {integration: main, production: main}\n")
        trunk = load(root / "t")
        assert trunk.git["integration"] == trunk.git["production"] == "main"

        # a partial override keeps the other default instead of blanking it
        _write(root / "p" / ".baton" / "config.yaml",
               _PLANE % "P" + "git: {production: main}\n")
        part = load(root / "p")
        assert part.git == {"integration": "develop", "production": "main"}


def test_write_config_rejects_incomplete_targets():
    with tempfile.TemporaryDirectory() as d:
        for n, target in enumerate(({}, {"workspace": "w"}, {"base_url": "https://p"})):
            try:
                write_config("plane", target, root=Path(d) / str(n))
                assert False, f"expected BatonError for {target}"
            except BatonError:
                pass


if __name__ == "__main__":
    test_loads_new_fields()
    test_sibling_by_name_and_by_path()
    test_unknown_project_lists_known_ones()
    test_defaults_when_fields_absent()
    test_token_roles_have_defaults_and_are_overridable()
    test_github_projects_backend_is_refused_with_a_route_forward()
    test_admin_role_refuses_to_fall_back_to_the_agent_credential()
    test_write_config_roundtrips_and_refuses_to_clobber()
    test_code_repo_carries_the_git_host_the_board_knows_nothing_about()
    test_multirepo_project_resolves_the_repo_from_the_area_label()
    test_migration_source_is_project_data_not_skill_data()
    test_git_branch_names_are_config_with_defaults()
    test_write_config_rejects_incomplete_targets()
    print("ok")
