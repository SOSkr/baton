"""Runnable check for config loading and sibling-project resolution.

Builds a throwaway two-project tree in a temp dir — the shape a developer with
several repos actually has — and checks that `--project` reaches the other
board's config. Run: `python tests/test_config.py` or `pytest`.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from baton.base import BatonError  # noqa: E402
from baton.config import load, load_project  # noqa: E402


def _write(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _tree(root: Path):
    """workspace/
         app-a/.baton/config.yaml   <- declares app-b as a sibling
         app-b/.baton/config.yaml
    """
    _write(root / "app-a" / ".baton" / "config.yaml",
           "backend: github\n"
           "target: {repo: acme/app-a}\n"
           "memory: app-a\n"
           "projects:\n"
           "  b: ../app-b\n")   # relative to the PROJECT root (the dir holding .baton/)
    _write(root / "app-b" / ".baton" / "config.yaml",
           "backend: github\n"
           "target: {repo: acme/app-b}\n"
           "memory: app-b\n")


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
        assert by_name.target["repo"] == "acme/app-b" and by_name.memory == "app-b"

        # same board, addressed by path instead of by declared name
        by_path = load_project(str(root / "app-b"), a)
        assert by_path.target["repo"] == "acme/app-b"


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


if __name__ == "__main__":
    test_loads_new_fields()
    test_sibling_by_name_and_by_path()
    test_unknown_project_lists_known_ones()
    test_defaults_when_fields_absent()
    print("ok")
