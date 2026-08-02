"""Runnable check that the documentation cannot lie.

Everything here guards one failure mode, and it is a failure mode this repo has already
had three times: documentation that is wrong and nothing fails. `epic.md` was cited by a
skill for six PRs after it moved; `__version__` said 0.1.0 while PyPI served 0.3.0; the
`doctor` example in the README lost a section the code had grown.

So: the config example is loaded, its keys are checked against `Config` **in both
directions**, every YAML block in the README is checked the same way, and every relative
link in the docs has to resolve.

Run: `python tests/test_docs.py` or `pytest`.
"""
import re
import sys
from dataclasses import fields
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from baton.config import Config, load_file  # noqa: E402

EXAMPLE = ROOT / "docs" / "config.example.yaml"

# Fields that are deliberately NOT in the example, each with its reason. `backend` is
# absent from this list on purpose: it is an InitVar, so it is not a field at all — the
# old spelling is translated on the way in and never stored, which is exactly why it
# needs no exception here.
_NOT_IN_YAML = {
    "path": "runtime: where the file was loaded from, not something you write",
}

# Every markdown file whose links must resolve.
_MARKDOWN = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md")),
             *sorted((ROOT / "skills").glob("*/SKILL.md"))]


def _config_keys() -> set[str]:
    return {f.name for f in fields(Config)}


def test_the_example_loads_as_a_real_config():
    """Not "is valid YAML" — is a config baton can actually run on."""
    cfg = load_file(EXAMPLE)
    assert cfg.adapters["board"] == "plane"
    assert cfg.code_repo == "acme/app"
    assert cfg.repo_for("engine") == "acme/app-engine"     # the multi-repo map works
    assert cfg.git["integration"] == "develop"


def test_the_example_invents_no_keys():
    """`load_file` ignores keys it does not know, so a typo (`board_stage:`) parses
    fine, does nothing, and tells nobody. This is what notices."""
    used = set(yaml.safe_load(EXAMPLE.read_text()))
    unknown = used - _config_keys() - {"backend"}
    assert not unknown, f"{EXAMPLE.name} uses keys that do not exist: {sorted(unknown)}"


def test_every_config_key_is_documented():
    """The other direction, and the one that catches the real habit: a key added to
    `Config` with nothing but a maintainer's memory documenting it. `adapters`,
    `board_stages` and `visibility` all arrived that way."""
    used = set(yaml.safe_load(EXAMPLE.read_text()))
    missing = _config_keys() - used - set(_NOT_IN_YAML)
    assert not missing, (f"config keys nobody documented: {sorted(missing)}. Add them to "
                         f"docs/config.example.yaml, or to _NOT_IN_YAML with a reason.")


def test_readme_yaml_blocks_use_real_keys():
    """The README's snippets are partial on purpose, so only this direction applies:
    whatever they DO show has to exist."""
    known = _config_keys() | {"backend"}
    bad = []
    for block in re.findall(r"```yaml\n(.*?)```", (ROOT / "README.md").read_text(), re.S):
        try:
            data = yaml.safe_load(block)
        except yaml.YAMLError as e:
            bad.append(f"unparseable block: {e}")
            continue
        if not isinstance(data, dict):
            continue                       # a fragment, e.g. a bare list
        bad += [f"unknown key {k!r}" for k in data if k not in known]
    assert not bad, "README yaml blocks:\n  " + "\n  ".join(bad)


def test_every_relative_link_resolves():
    """The `epic.md` class of rot, applied to links."""
    broken = []
    for md in _MARKDOWN:
        for m in re.finditer(r"\]\((?!https?:|mailto:|#)([^)\s]+)", md.read_text()):
            target = (md.parent / m.group(1).split("#")[0])
            if not target.exists():
                broken.append(f"{md.relative_to(ROOT)} -> {m.group(1)}")
    assert not broken, "links pointing at nothing:\n  " + "\n  ".join(broken)


def test_no_doc_is_orphaned():
    """A doc nobody links is a doc nobody reads. Whatever is worth keeping under
    docs/ is worth reaching from somewhere."""
    text = "\n".join(p.read_text() for p in _MARKDOWN)
    text += "\n".join(p.read_text() for p in [ROOT / "README.md"])
    orphans = []
    for doc in sorted((ROOT / "docs").rglob("*")):
        if doc.is_dir() or doc == ROOT / "docs" / "adapters" / "README.md":
            continue                       # a directory's own index is reached as `docs/x/`
        if doc.name not in text:
            orphans.append(str(doc.relative_to(ROOT)))
    assert not orphans, ("docs nothing links to:\n  " + "\n  ".join(orphans)
                         + "\nLink them, or delete them.")


def test_gitignore_patterns_carry_no_trailing_comment():
    """`#` starts a comment in .gitignore ONLY at the start of a line. `.baton/  # why`
    is a pattern that matches a directory with spaces and a hash in its name — that is,
    nothing. It shipped that way, and it was invisible here because a global gitignore
    happened to cover the same path; on CI the file would have been committable.
    """
    bad = [ln for ln in (ROOT / ".gitignore").read_text().splitlines()
           if ln.strip() and not ln.lstrip().startswith("#") and "#" in ln]
    assert not bad, ("patterns with an inline comment ignore nothing:\n  "
                     + "\n  ".join(bad) + "\nPut the comment on its own line.")


def test_the_dogfooding_config_is_ignored():
    """baton administers baton, and its own .baton/config.yaml carries the Plane URL of
    whoever runs it. This repo is public."""
    lines = {ln.strip() for ln in (ROOT / ".gitignore").read_text().splitlines()}
    assert ".baton/" in lines or ".baton/config.yaml" in lines


if __name__ == "__main__":
    test_the_example_loads_as_a_real_config()
    test_the_example_invents_no_keys()
    test_every_config_key_is_documented()
    test_readme_yaml_blocks_use_real_keys()
    test_every_relative_link_resolves()
    test_no_doc_is_orphaned()
    test_gitignore_patterns_carry_no_trailing_comment()
    test_the_dogfooding_config_is_ignored()
    print("ok — the docs match the code")


def test_reject_names_its_stage_before_closing():
    """`close` does not move an item, on purpose (see BoardBase.close). A reject that
    only closes leaves the item sitting in the intake column reading as open work —
    and an adapter that "helpfully" picked a stage once sent rejected items to
    Deployed. The skill and its command must both spell the two steps out."""
    skill = (ROOT / "skills" / "baton-reject" / "SKILL.md").read_text()
    assert "--to @cancel" in skill, "baton-reject must advance to the cancel stage"
    assert skill.index("--to @cancel") < skill.index("baton close"), \
        "the advance goes BEFORE the close"

    command = (ROOT / "commands" / "baton-reject.md").read_text()
    assert "--to @cancel" in command, "the slash command must say it too"


def test_the_close_contract_says_it_does_not_move_the_item():
    """The rule lives on the interface, where whoever writes the next adapter reads
    it — not only in the skill that happens to call it."""
    base = (ROOT / "src" / "baton" / "adapters" / "board" / "base.py").read_text()
    close_doc = base.split("def close(")[1].split("# ---- creation")[0]
    assert "do NOT move" in close_doc.lower() or "not move it" in close_doc.lower(), \
        "BoardBase.close must state that closing never picks a stage"
