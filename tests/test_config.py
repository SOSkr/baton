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
from baton.config import (load, load_project,  # noqa: E402
                          write_config)  # noqa: E402


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


def test_credential_sources_finds_the_server_without_reading_the_secret():
    """`doctor` says WHERE a missing credential lives. What it must never do is read
    it: a token picked up from another program's config is a credential nobody chose,
    used with a role nobody declared."""
    import json
    from baton.config import credential_sources
    with tempfile.TemporaryDirectory() as d:
        cfgfile = Path(d) / "agent.json"
        cfgfile.write_text(json.dumps({
            "mcpServers": {
                "plane-mcp": {"command": "npx", "env": {"PLANE_API_KEY": "s3cr3t",
                                                        "PLANE_WORKSPACE_SLUG": "acme"}},
                "other": {"command": "npx", "env": {"SOMETHING_ELSE": "x"}},
            },
            "projects": {"/w/app": {"mcpServers": {
                "scoped": {"env": {"PLANE_API_KEY": "another"}}}}},
        }))
        import baton.config as mod
        orig = mod._MCP_CONFIGS
        try:
            mod._MCP_CONFIGS = (str(cfgfile),)
            got = credential_sources("PLANE_API_KEY")
        finally:
            mod._MCP_CONFIGS = orig

    names = [n for n, _, _ in got]
    assert names == ["plane-mcp", "scoped"]          # global and project-scoped blocks
    assert not credential_sources_leaks(got), "a value escaped into the result"
    assert got[0][2] == ["mcpServers", "plane-mcp", "env", "PLANE_API_KEY"]
    assert got[1][2][:2] == ["projects", "/w/app"]


def credential_sources_leaks(rows) -> bool:
    return any("s3cr3t" in str(part) or "another" in str(part)
               for row in rows for part in row)


def test_a_var_no_server_declares_is_simply_absent():
    from baton.config import credential_sources
    assert credential_sources("NOPE_NOT_A_VAR_" + "X" * 8) == []


def test_doctor_reports_everything_even_with_no_credentials_at_all():
    """Its contract: check EVERYTHING, then say what is broken. One that dies halfway
    hides the failure after the one it died on."""
    from baton.cli import main
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _write(root / ".baton" / "config.yaml", _PLANE % "APP")
        cwd, saved = os.getcwd(), {k: os.environ.pop(k, None)
                                   for k in ("PLANE_API_KEY", "PLANE_ADMIN_API_KEY",
                                             "GH_TOKEN", "GH_ADMIN_TOKEN")}
        try:
            os.chdir(root)
            rc = main(["doctor"])          # must not raise
        finally:
            os.chdir(cwd)
            os.environ.update({k: v for k, v in saved.items() if v is not None})
    assert rc == 1                          # and it reports failure rather than dying


def test_a_board_has_one_credential_and_the_verb_does_not_change_it():
    """Un board no tiene dos credenciales: tiene una, y qué puede hacer lo decide el
    board según el usuario dueño. baton no tiene voto, así que no modela dos.

    Apuntar una segunda variable a un board no separaba nada — solo elegía, y nadie
    comprobaba nunca que la llamada `admin` pudiera más. En el code host esa
    comprobación existe y la hace cumplir GitHub; acá era una afirmación sin verificar.
    """
    from baton.config import Config

    for backend, var in [("kanboard", "KANBOARD_TOKEN"), ("plane", "PLANE_API_KEY")]:
        c = Config(backend=backend)
        assert c.token_env() == var
        assert c.token_env("agent") == c.token_env("admin") == var, \
            "el rol no puede cambiar de quién es la credencial del board"


def test_a_project_names_its_own_board_variable():
    from baton.config import Config

    assert Config(backend="kanboard",
                  tokens="KB_DEL_PROYECTO").token_env() == "KB_DEL_PROYECTO"


def test_a_config_written_before_this_still_loads():
    """`tokens: {agent: X, admin: Y}` existe en discos ajenos. Nunca fueron dos
    credenciales, así que cualquiera de los dos nombres resuelve a lo mismo."""
    from baton.config import Config

    c = Config(backend="kanboard", tokens={"agent": "VIEJO", "admin": "VIEJO"})
    assert c.token_env() == "VIEJO"


def test_asking_for_admin_does_not_change_the_board_credential():
    """`--as admin` sigue existiendo y sigue significando algo — en el REPO, donde
    GitHub hace cumplir la separación. Del lado del board no tiene nada que elegir."""
    import os

    from baton.config import Config, github_token_env, resolve_token

    c = Config(backend="kanboard")
    os.environ["KANBOARD_TOKEN"] = "t"
    try:
        assert resolve_token(c, "admin") == resolve_token(c, "agent") == "t"
    finally:
        del os.environ["KANBOARD_TOKEN"]
    assert github_token_env("agent") != github_token_env("admin"), \
        "en el code host la separación sí es real"


if __name__ == "__main__":
    # Enumerado por reflexión y no a mano: la lista escrita quedó nombrando tests que
    # ya no existen en cuanto uno se renombró, y ruff fue el único que lo notó.
    ns = dict(globals())
    fns = [(n, f) for n, f in ns.items() if n.startswith("test_") and callable(f)]
    for nombre, fn in fns:
        fn()
        print(f"ok  {nombre}")
    print(f"\n{len(fns)} checks passed")
