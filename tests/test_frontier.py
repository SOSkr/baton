"""Runnable check for the layering rules — the ones a reviewer cannot see in a diff.

Three rules, agreed on purpose, each with a failure mode that is invisible until it is
expensive:

1. A role's rules (`adapters/<role>/__init__.py`) may NOT import a provider. The
   moment `board/__init__.py` says `from .plane import ...`, "these rules hold for
   every board" silently becomes "these rules hold for Plane".
2. Nothing under `adapters/` may import `core`. Dependencies point one way
   (cli → core → adapters); the other direction is an import cycle waiting for the
   second caller.
3. Adapters never print. An adapter that prints cannot be used by `--json`, by a
   skill, or by a test.

Run: `python tests/test_frontier.py` or `pytest`.
"""
import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from baton.adapters import registry  # noqa: E402
from baton.base import BatonError  # noqa: E402

ADAPTERS = SRC / "baton" / "adapters"


def _imported_names(path: Path) -> list[str]:
    """Every module path this file imports, dotted and relative-flattened."""
    tree = ast.parse(path.read_text())
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = "." * (node.level or 0) + (node.module or "")
            out += [base] + [f"{base}.{a.name}" for a in node.names]
    return out


def test_role_rules_never_import_a_provider():
    offenders = []
    for role in registry.ROLES:
        providers = set(registry.available(role))
        assert providers, f"no providers found for role {role!r} — did the layout change?"
        for imp in _imported_names(ADAPTERS / role / "__init__.py"):
            leaf = imp.rsplit(".", 1)[-1]
            if leaf in providers:
                offenders.append(f"{role}/__init__.py imports {imp}")
    assert not offenders, ("role rules must reach providers through registry.resolve:\n  "
                           + "\n  ".join(offenders))


def test_adapters_never_import_core():
    offenders = [f"{p.relative_to(SRC)} imports {imp}"
                 for p in ADAPTERS.rglob("*.py")
                 for imp in _imported_names(p)
                 if imp.rstrip(".").endswith("core")]
    assert not offenders, "adapters must not depend on core:\n  " + "\n  ".join(offenders)


def test_adapters_never_print():
    offenders = []
    for p in ADAPTERS.rglob("*.py"):
        for node in ast.walk(ast.parse(p.read_text())):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "print"):
                offenders.append(f"{p.relative_to(SRC)}:{node.lineno}")
    assert not offenders, ("adapters return or raise; cli.py owns output:\n  "
                           + "\n  ".join(offenders))


def test_registry_resolves_by_file_name():
    """The config value IS the file name — that is the whole dispatch mechanism."""
    assert registry.resolve("board", "plane").__name__ == "PlaneBoard"
    assert registry.resolve("repo", "github").__name__ == "GitHubRepo"
    assert registry.resolve("read", "github_projects").__name__ == "GitHubProjectsRead"


def test_unknown_provider_says_what_exists():
    """A typo'd backend is the likeliest way in here; an error without the list
    leaves the reader guessing."""
    try:
        registry.resolve("board", "plana")
        assert False, "expected BatonError"
    except BatonError as e:
        assert "plana" in str(e) and "plane" in str(e), e


def test_every_provider_exports_adapter():
    for role in registry.ROLES:
        for name in registry.available(role):
            cls = registry.resolve(role, name)      # raises if ADAPTER is missing
            assert isinstance(cls, type), f"{role}/{name}.py ADAPTER is not a class"


if __name__ == "__main__":
    test_role_rules_never_import_a_provider()
    test_adapters_never_import_core()
    test_adapters_never_print()
    test_registry_resolves_by_file_name()
    test_unknown_provider_says_what_exists()
    test_every_provider_exports_adapter()
    print("ok — frontiers hold")
