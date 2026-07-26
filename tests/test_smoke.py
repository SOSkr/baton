"""Runnable check for baton's core: the adapter contract + lifecycle flow.

Uses an in-memory FakeAdapter (no network) to exercise create → advance →
get → list-by-stage → close. Run: `python tests/test_smoke.py` or `pytest`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from baton.base import Adapter, BatonError, Item  # noqa: E402


class FakeAdapter(Adapter):
    STAGES = ["Review", "Approved", "In Progress", "Done"]

    def __init__(self):
        self._items: dict[str, Item] = {}
        self._n = 0
        self.comments: list[tuple[str, str]] = []

    def list_stages(self): return list(self.STAGES)

    def create(self, title, body, labels):
        self._n += 1
        it = Item(id=str(self._n), title=title, url=f"fake://{self._n}",
                  labels=list(labels), body=body, stage=None)
        self._items[it.id] = it
        return it

    def get(self, item_id): return self._items[item_id]

    def list(self, *, stage=None, label=None, state="open"):
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

    def comment(self, item_id, text): self.comments.append((item_id, text))

    def set_stage(self, item_id, stage):
        if stage.lower() not in [s.lower() for s in self.STAGES]:
            raise BatonError(f"unknown stage {stage!r}")
        self._items[item_id].stage = stage

    def set_labels(self, item_id, add=None, remove=None):
        it = self._items[item_id]
        it.labels = [l for l in it.labels if l not in (remove or [])] + list(add or [])

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
    assert a.comments == [("1", "looks good")]

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
        {"backend": "github", "target": {"repo": "SOSkr/proj-spec", "project": 5}}))
    cfg = load(start=d)
    assert cfg.backend == "github" and cfg.target["project"] == 5


def test_verb_stage():
    from baton.cli import _verb_stage
    from baton.config import Config
    c = Config(backend="github", stages={"approve": "Aceptada"})
    assert _verb_stage(c, "approve") == "Aceptada"   # config alias wins
    assert _verb_stage(c, "start") == "In Progress"  # default
    assert _verb_stage(c, "ship") == "Deployed"


def test_stamp_label():
    import argparse
    from baton.cli import _stamp, cmd_new, cmd_advance
    from baton.config import Config
    a = FakeAdapter()
    cfg = Config(backend="github", stamp_label="agent-changed")

    # _stamp adds the governance label
    it = a.create("x", "", [])
    _stamp(a, cfg, it.id)
    assert "agent-changed" in a.get(it.id).labels

    # cmd_new stamps on creation
    ns = argparse.Namespace(title="y", body="", label=[], stage="Review", json=False)
    cmd_new(ns, a, cfg)
    created = [i for i in a.list() if i.title == "y"][0]
    assert "agent-changed" in created.labels and created.stage == "Review"

    # cmd_advance stamps on state change
    cmd_advance(argparse.Namespace(id=it.id, to="Approved", json=False), a, cfg)
    assert "agent-changed" in a.get(it.id).labels  # still there, no dup crash

    # no stamp_label configured → no label added
    a2 = FakeAdapter()
    it2 = a2.create("z", "", [])
    _stamp(a2, Config(backend="github"), it2.id)
    assert a2.get(it2.id).labels == []


if __name__ == "__main__":
    test_lifecycle()
    test_unknown_stage_errors()
    test_labels_add_remove()
    test_verb_stage()
    test_stamp_label()
    try:
        test_config_load()
    except ImportError:
        print("(skipping config test — pyyaml not installed)")
    print("OK — baton smoke tests passed")
