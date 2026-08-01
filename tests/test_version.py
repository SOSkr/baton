"""Runnable check for where the version number comes from.

The bug this exists to prevent already happened: the number lived in two literals, they
drifted, and PyPI served 0.3.0 while `baton doctor` printed 0.1.0 to whoever ran it —
with nothing failing. So the derivation is tested on BOTH paths, not just the happy one:
the fallback (running from a checkout) is what every local run and every CI run takes,
and it is the one a "works on my machine" test would never reach.

Run: `python tests/test_version.py` or `pytest`.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from baton import version  # noqa: E402


class _FakeDist:
    def __init__(self, name, ver):
        self.metadata, self.version = {"Name": name}, ver


def _patched(**attrs):
    """Swap module-level functions, the way the adapter tests swap `gh`."""
    saved = {k: getattr(version, k) for k in attrs}
    for k, v in attrs.items():
        setattr(version, k, v)
    return saved


def _restore(saved):
    for k, v in saved.items():
        setattr(version, k, v)


def test_installed_metadata_wins():
    """Whoever installed baton is who the number is for — and inside a wheel there is
    no pyproject.toml to read, so metadata has to be the first answer."""
    saved = _patched(installed=lambda: "9.9.9", from_source=lambda *a: "1.0.0")
    try:
        assert version.resolve() == "9.9.9"
    finally:
        _restore(saved)


def test_falls_back_to_the_source_tree():
    """The path every local run takes: a checkout with nothing installed."""
    saved = _patched(installed=lambda: None)
    try:
        assert version.resolve() == version.from_source()
        assert version.resolve() != "0+unknown"
    finally:
        _restore(saved)


def test_neither_available_says_so_instead_of_guessing():
    saved = _patched(installed=lambda: None, from_source=lambda *a: None)
    try:
        assert version.resolve() == "0+unknown"
    finally:
        _restore(saved)


def test_from_source_reads_the_real_pyproject_and_survives_its_absence():
    assert version.from_source() == _declared()
    with tempfile.TemporaryDirectory() as d:          # a tree with no pyproject above it
        assert version.from_source(Path(d) / "nothing.py") is None


def test_a_stale_editable_install_is_reported_not_hidden():
    """The residual risk of preferring metadata: an install whose number was written
    before the last bump keeps reporting it. Quiet is how the original bug survived."""
    saved = _patched(installed=lambda: "0.1.0", from_source=lambda *a: "0.4.0",
                     stale_former_install=lambda: None)
    try:
        note = version.mismatch()
        assert note and "0.1.0" in note and "0.4.0" in note
    finally:
        _restore(saved)


def test_a_leftover_distribution_under_the_old_name_is_named():
    """`baton` was renamed to `baton-board` for PyPI. A checkout installed before that
    still carries the old one, reporting a version from before the split — which is
    exactly the number the original bug printed."""
    saved = _patched(installed=lambda: None, from_source=lambda *a: "0.4.0",
                     distributions=lambda: [_FakeDist("baton", "0.1.0"),
                                            _FakeDist("pyyaml", "6.0")])
    try:
        note = version.mismatch()
        assert note and "baton" in note and "0.1.0" in note
        # and it is NOT used as the version: that would resurrect the bug
        assert version.resolve() == "0.4.0"
    finally:
        _restore(saved)


def test_agreement_is_silent():
    saved = _patched(installed=lambda: "1.2.3", from_source=lambda *a: "1.2.3",
                     stale_former_install=lambda: None)
    try:
        assert version.mismatch() is None
    finally:
        _restore(saved)


def _declared() -> str:
    import tomllib
    root = Path(__file__).resolve().parents[1]
    return tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ok — the version has one source")
