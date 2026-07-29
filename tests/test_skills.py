"""Runnable check for the skills layer: that a skill can actually open every
template it offers.

This exists because it already broke. `epic.md` moved from `templates/new/` to
`templates/roadmap/`, and `baton-new` kept listing it in its template table for six
PRs — offering the reader a file it could not open, with nothing failing. Templates
are reached through a per-skill symlink, so a move on one side is invisible on the
other until someone tries to read it.

Run: `python tests/test_skills.py` or `pytest`.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = sorted(p for p in (ROOT / "skills").iterdir() if (p / "SKILL.md").is_file())

# `SKILL.md` is how skills cite each other; `README.md` is the repo's own.
_NOT_TEMPLATES = {"SKILL.md", "README.md"}


def test_every_skill_has_a_skill_md():
    assert SKILLS, "no skills found — did the layout change?"


def test_template_symlinks_resolve():
    """Each skill exposes its templates as a symlink into the shared templates/ dir.
    A dangling one means the target moved or was renamed."""
    for skill in SKILLS:
        link = skill / "templates"
        if not link.exists() and not link.is_symlink():
            continue                      # not every skill has templates
        assert link.is_symlink(), f"{link.relative_to(ROOT)} should be a symlink"
        assert link.resolve().is_dir(), \
            f"{link.relative_to(ROOT)} dangles → {link.readlink()}"


def test_every_template_a_skill_names_is_reachable_from_it():
    """The check that would have caught the epic.md regression: a skill may only
    name a template it can open through its own templates/ dir."""
    missing = []
    for skill in SKILLS:
        text = (skill / "SKILL.md").read_text()
        tdir = skill / "templates"
        named = set(re.findall(r"`([a-z0-9_-]+\.md)`", text))          # `task.md`
        named |= set(re.findall(r"templates/([a-z0-9_-]+\.md)", text))  # templates/x.md
        for name in sorted(named - _NOT_TEMPLATES):
            if not (tdir / name).is_file():
                missing.append(f"{skill.name} names {name}, cannot open it")
    assert not missing, "skills offering templates they cannot read:\n  " + "\n  ".join(missing)


if __name__ == "__main__":
    test_every_skill_has_a_skill_md()
    test_template_symlinks_resolve()
    test_every_template_a_skill_names_is_reachable_from_it()
    print(f"ok — {len(SKILLS)} skills")
    sys.exit(0)
