"""Runnable check for baton's core: the adapter contract + lifecycle flow.

Uses an in-memory FakeAdapter (no network) to exercise create → advance →
get → list-by-stage → close. Run: `python tests/test_smoke.py` or `pytest`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from baton.adapters.board.base import BoardBase  # noqa: E402
from baton.base import BatonError, Comment, Item  # noqa: E402
from baton.core import Baton  # noqa: E402


class FakeAdapter(BoardBase):
    STAGES = ["Review", "Approved", "In Progress", "Done"]

    def __init__(self):
        self._items: dict[str, Item] = {}
        self._n = 0
        self._comments: list[tuple[str, str]] = []

    def probe(self): return "fake backend, always reachable"

    # deliberately does NOT implement the optional group capability — the base
    # class must degrade with a clear error, not an AttributeError

    def list_stages(self): return list(self.STAGES)

    def create(self, title, body, labels, priority=None):
        self._n += 1
        it = Item(id=str(self._n), title=title, url=f"fake://{self._n}",
                  labels=list(labels), body=body, stage=None, priority=priority)
        self._items[it.id] = it
        return it

    def get(self, item_id): return self._items[item_id]

    def list(self, *, stage=None, label=None, state="open", group=None):
        out = []
        for it in self._items.values():
            if state != "all" and it.state != state:
                continue
            if stage and (it.stage or "").lower() != stage.lower():
                continue
            if label and label not in it.labels:
                continue
            out.append(it)
        return out

    def comment(self, item_id, text): self._comments.append((item_id, text))

    def comments(self, item_id):
        return [Comment(body=t) for i, t in self._comments if i == item_id]

    def set_stage(self, item_id, stage):
        if stage.lower() not in [s.lower() for s in self.STAGES]:
            raise BatonError(f"unknown stage {stage!r}")
        self._items[item_id].stage = stage

    def set_labels(self, item_id, add=None, remove=None):
        it = self._items[item_id]
        it.labels = [lb for lb in it.labels if lb not in (remove or [])] + list(add or [])

    def edit_body(self, item_id, body): self._items[item_id].body = body

    def close(self, item_id, reason=""): self._items[item_id].state = "closed"


def test_lifecycle():
    a = FakeAdapter()
    it = a.create("Add dark mode", "body", ["type:idea", "priority:medium"])
    assert it.id == "1" and it.stage is None

    a.set_stage(it.id, "Review")
    assert a.get("1").stage == "Review"

    a.set_stage(it.id, "Approved")
    assert a.get("1").stage == "Approved"
    assert [i.id for i in a.list(stage="Approved")] == ["1"]
    assert a.list(stage="Review") == []

    a.comment("1", "looks good")
    assert a._comments == [("1", "looks good")]
    assert [c.body for c in a.comments("1")] == ["looks good"]
    assert a.comments("2") == []

    a.close("1", "superseded")
    assert a.get("1").state == "closed"
    assert a.list(state="open") == []
    assert len(a.list(state="all")) == 1


def test_unknown_stage_errors():
    a = FakeAdapter()
    it = a.create("x", "", [])
    try:
        a.set_stage(it.id, "Nope")
        assert False, "expected BatonError"
    except BatonError:
        pass


def test_labels_add_remove():
    a = FakeAdapter()
    it = a.create("x", "", ["a", "b"])
    a.set_labels(it.id, add=["c"], remove=["a"])
    assert set(a.get(it.id).labels) == {"b", "c"}


def test_config_load(tmp_path=None):
    import tempfile
    import yaml
    from baton.config import load
    d = Path(tempfile.mkdtemp())
    (d / ".baton").mkdir()
    (d / ".baton" / "config.yaml").write_text(yaml.safe_dump(
        {"backend": "plane", "target": {"base_url": "https://p", "workspace": "w", "project": "APP"}}))
    cfg = load(start=d)
    assert cfg.backend == "plane" and cfg.target["project"] == "APP"


def test_verb_stage():
    from baton.adapters.board import verb_stage
    from baton.config import Config
    c = Config(backend="plane", stages={"approve": "Aceptada"})
    assert verb_stage(c, "approve") == "Aceptada"   # config alias wins
    assert verb_stage(c, "start") == "In Progress"  # default
    assert verb_stage(c, "ship") == "Deployed"


def test_backward_flag():
    import argparse
    from baton.cli import cmd_advance
    from baton.config import Config
    # FakeAdapter.STAGES = ["Review","Approved","In Progress","Done"]
    a = FakeAdapter()
    cfg = Config(backend="plane", review_label="revisar-cambio")
    it = a.create("x", "", [])
    a.set_stage(it.id, "Approved")

    # FORWARD (Approved→In Progress): NOT flagged
    cmd_advance(argparse.Namespace(id=it.id, to="In Progress", json=False), Baton(cfg, board=a), cfg)
    assert "revisar-cambio" not in a.get(it.id).labels

    # BACKWARD (In Progress→Review): flagged
    cmd_advance(argparse.Namespace(id=it.id, to="Review", json=False), Baton(cfg, board=a), cfg)
    assert "revisar-cambio" in a.get(it.id).labels

    # creation is NOT flagged (no stage yet / forward only)
    assert "revisar-cambio" not in a.create("fresh", "", []).labels

    # no review_label configured → never flags, even backward
    a2 = FakeAdapter()
    it2 = a2.create("y", "", [])
    a2.set_stage(it2.id, "Approved")
    c2 = Config(backend="plane")
    cmd_advance(argparse.Namespace(id=it2.id, to="Review", json=False),
                Baton(c2, board=a2), c2)
    assert a2.get(it2.id).labels == []


def test_verify_stage_cannot_be_skipped():
    """Opt-in gate: with `stages.verify` declared, a jump OVER it is refused. It
    gates the stage, not the work — going through it explicitly is still allowed,
    which is the point: skipping becomes deliberate and visible, not an oversight."""
    import argparse
    from baton.cli import cmd_advance
    from baton.config import Config
    # FakeAdapter.STAGES = ["Review", "Approved", "In Progress", "Done"]
    a = FakeAdapter()
    cfg = Config(backend="plane", stages={"verify": "In Progress"})

    def advance(item, to, c=cfg, ad=None):
        cmd_advance(argparse.Namespace(id=item, to=to, json=False),
                    Baton(c, board=ad or a), c)

    it = a.create("x", "", [])
    a.set_stage(it.id, "Approved")

    # Approved → Done jumps over "In Progress" (the declared verify stage)
    try:
        advance(it.id, "Done")
        assert False, "expected BatonError"
    except BatonError as e:
        assert "skips" in str(e) and "In Progress" in str(e)
    assert a.get(it.id).stage == "Approved"      # the move did NOT happen

    # going through it explicitly is allowed — two deliberate steps
    advance(it.id, "In Progress")
    advance(it.id, "Done")
    assert a.get(it.id).stage == "Done"

    # forward moves that do not cross the verify stage are untouched
    b = FakeAdapter()
    it2 = b.create("y", "", [])
    b.set_stage(it2.id, "Review")
    advance(it2.id, "Approved", ad=b)
    assert b.get(it2.id).stage == "Approved"

    # and a project that never declares stages.verify is never gated
    c = FakeAdapter()
    it3 = c.create("z", "", [])
    c.set_stage(it3.id, "Approved")
    advance(it3.id, "Done", c=Config(backend="plane"), ad=c)
    assert c.get(it3.id).stage == "Done"


def test_version_matches_pyproject():
    """`__version__` and `pyproject.toml` drifted apart once already: PyPI served
    0.3.0 while `baton doctor` printed 0.1.0 to whoever ran it. Two literals, one
    number, nothing failing — so this is the thing that fails."""
    import tomllib

    import baton
    root = Path(__file__).resolve().parents[1]
    declared = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    assert baton.__version__ == declared, \
        f"__init__.py says {baton.__version__}, pyproject.toml says {declared}"


if __name__ == "__main__":
    test_lifecycle()
    test_verify_stage_cannot_be_skipped()
    test_unknown_stage_errors()
    test_labels_add_remove()
    test_verb_stage()
    test_backward_flag()
    test_version_matches_pyproject()
    try:
        test_config_load()
    except ImportError:
        print("(skipping config test — pyyaml not installed)")
    print("OK — baton smoke tests passed")
