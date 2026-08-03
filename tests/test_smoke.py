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
        self.STAGES = list(FakeAdapter.STAGES)       # per instance: tests create stages
        self._groups = {"Review": "unstarted", "Approved": "unstarted",
                        "In Progress": "started", "Done": "completed"}
        self._project: dict | None = {"id": "p1", "identifier": "FAKE", "name": "fake"}
        self._default = "Review"

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

    # ---- bootstrap surface, in memory ----
    def find_project(self): return self._project

    def create_project(self, name):
        self._project = {"id": "p1", "identifier": "FAKE", "name": name}
        return self._project

    def stage_groups(self): return {s: self._groups.get(s, "") for s in self.STAGES}

    def default_stage(self): return self._default

    def set_default_stage(self, name): self._default = name

    def create_stage(self, name, *, group, color):
        self.STAGES.append(name)
        self._groups[name] = group

    def set_stage_position(self, name, position):
        self.STAGES = [s for s in self.STAGES if s != name]
        self.STAGES.insert(position, name)

    def delete_stage(self, name):
        self.STAGES = [s for s in self.STAGES if s.lower() != name.lower()]
        self._groups.pop(name, None)


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


def _board_con_epica():
    """Un board donde la épica es una tarea más — como Kanboard, que es donde el
    problema existe: comparten espacio de ids y nada más los distingue."""
    from baton.base import Group

    a = FakeAdapter()
    item = a.create("trabajo de verdad", "", [])
    epica = a.create("Q3 auth", "", [])
    a.list_groups = lambda: [Group(name="Q3 auth", id=epica.id, total=1, done=0)]
    a.set_group = lambda item_id, name: None
    return a, item.id, epica.id


def test_item_verbs_refuse_an_epic():
    """El 2026-08-02 un id mal tipeado corrió el ciclo entero sobre una épica: la
    aprobó, la shipeó, la cerró y la metió dentro de la otra. Los SIETE comandos
    contestaron éxito."""
    from baton.config import Config
    from baton.core import Baton

    a, item, epica = _board_con_epica()
    b = Baton(Config(backend="plane"), board=a)

    for verbo, llamada in [
        ("show", lambda i: b.item(i)),
        ("comment", lambda i: b.comment(i, "hola")),
        ("close", lambda i: b.close(i)),
        ("labels", lambda i: b.set_labels(i, add=["x"])),
        ("body", lambda i: b.edit_body(i, "x")),
        ("advance", lambda i: b.advance(i, "Approved")),
        ("group", lambda i: b.set_group(i, "Q3 auth")),
    ]:
        llamada(item)                       # sobre un item, pasa
        try:
            llamada(epica)
        except BatonError as e:
            assert "is an epic" in str(e) and "Q3 auth" in str(e), f"{verbo}: {e}"
            assert "baton groups" in str(e), f"{verbo}: no dice qué usar en su lugar"
        else:
            raise AssertionError(f"`{verbo}` aceptó una épica sin decir nada")


def test_a_board_without_epics_is_not_slowed_down_by_the_guard():
    """`list_groups` levanta el error de capacidad ausente en un backend sin
    agrupación. Eso no puede volverse un fallo de cada verbo."""
    from baton.adapters.board import refuse_group

    a = FakeAdapter()
    it = a.create("x", "", [])
    refuse_group(a, it.id, "close")      # no explota: no hay con qué confundirlo


def test_cancelled_work_is_not_progress():
    """Descartar trabajo era la forma más rápida de mover la barra: cerrar por
    cancelación cerraba el item, y el backend contaba cerrados. Un roadmap que sube
    cuando se abandona algo dice lo contrario de lo que pasó."""
    from baton.adapters.board import groups
    from baton.base import Group, Item
    from baton.config import Config

    class Fake:
        def list_groups(self):
            # lo que el backend cree: tres cerrados de tres
            return [Group(name="Q3", id="1", target_date="2026-09-15", total=3, done=3)]

        def list(self, *, group=None, state="open", **_):
            return [Item(id="1", title="entregado", stage="Deployed", state="closed"),
                    Item(id="2", title="descartado", stage="Cancelled", state="closed"),
                    Item(id="3", title="abierto", stage="Review", state="open")]

    [g] = groups(Fake(), Config(backend="plane"))
    assert (g.done, g.total) == (1, 3), "lo cancelado no cuenta como hecho"
    assert g.target_date == "2026-09-15", "lo demás del grupo no se toca"


def test_the_cancel_stage_comes_from_the_config():
    """`Cancelled` es solo el default. Un board que llama a esa columna de otra forma
    lo declara en `stages`, y la regla tiene que leer de ahí — si no, cuenta como
    entregado el trabajo que ese proyecto descartó."""
    from baton.adapters.board import groups
    from baton.base import Group, Item
    from baton.config import Config

    class Fake:
        def list_groups(self):
            return [Group(name="Q3", id="1", total=2, done=2)]

        def list(self, *, group=None, state="open", **_):
            return [Item(id="1", title="entregado", stage="Desplegado", state="closed"),
                    Item(id="2", title="descartado", stage="Descartado", state="closed")]

    cfg = Config(backend="plane", stages={"cancel": "Descartado", "ship": "Desplegado"})
    [g] = groups(Fake(), cfg)
    assert (g.done, g.total) == (1, 2)


def test_shipped_but_not_closed_is_not_done_yet():
    """Un item en la etapa de ship sin cerrar no cuenta: salió cuando alguien dijo que
    salió, y eso es `close`. Si contara, la barra subiría al mover una tarjeta."""
    from baton.adapters.board import groups
    from baton.base import Group, Item
    from baton.config import Config

    class Fake:
        def list_groups(self):
            return [Group(name="Q3", id="1", total=1, done=1)]

        def list(self, *, group=None, state="open", **_):
            return [Item(id="1", title="en deployed, abierto", stage="Deployed",
                         state="open")]

    [g] = groups(Fake(), Config(backend="plane"))
    assert (g.done, g.total) == (0, 1)


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


def test_show_prints_the_body_and_list_does_not():
    """The body IS the item — the user story, the criteria, the scope. `baton-verify`
    opens by reading it, and for a long time `show` did not print it: the skill sent
    readers to a command that could not answer its own first question.

    `list` stays one line per item: there the body would be noise.
    """
    import argparse
    import io
    from contextlib import redirect_stdout

    from baton.cli import cmd_list, cmd_show
    from baton.config import Config

    a = FakeAdapter()
    it = a.create("Add dark mode", "## User story\nComo alguien, quiero algo.\n\n- [ ] un criterio", [])
    b = Baton(Config(backend="plane"), board=a)

    out = io.StringIO()
    with redirect_stdout(out):
        cmd_show(argparse.Namespace(id=it.id, comments=False, json=False), b, b.cfg)
    shown = out.getvalue()
    assert "## User story" in shown and "- [ ] un criterio" in shown
    assert "Add dark mode" in shown          # y sigue mostrando lo de antes

    out = io.StringIO()
    with redirect_stdout(out):
        cmd_list(argparse.Namespace(stage=None, label=None, state="open", group=None,
                                    json=False), b, b.cfg)
    assert "User story" not in out.getvalue(), "list debe seguir siendo una línea por item"


def test_show_with_comments_puts_the_body_first():
    """The thread reads as what happened AFTER the item said what it wanted."""
    import argparse
    import io
    from contextlib import redirect_stdout

    from baton.cli import cmd_show
    from baton.config import Config

    a = FakeAdapter()
    it = a.create("x", "el cuerpo del item", [])
    a.comment(it.id, "un comentario")
    b = Baton(Config(backend="plane"), board=a)

    out = io.StringIO()
    with redirect_stdout(out):
        cmd_show(argparse.Namespace(id=it.id, comments=True, json=False), b, b.cfg)
    shown = out.getvalue()
    assert shown.index("el cuerpo del item") < shown.index("un comentario")


def test_version_is_derived_not_written_twice():
    """The number used to live in two literals and they drifted: PyPI served 0.3.0
    while `baton doctor` printed 0.1.0. Now `pyproject.toml` is the only place a human
    edits it, so this checks the DERIVATION still lands on it — from a checkout, which
    is the path every local run and every CI run takes."""
    import tomllib

    import baton
    root = Path(__file__).resolve().parents[1]
    declared = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    assert baton.__version__ == declared, \
        f"baton reports {baton.__version__}, pyproject.toml says {declared}"

    src = (root / "src" / "baton" / "__init__.py").read_text()
    assert declared not in src, "the version is written in __init__.py again"


if __name__ == "__main__":
    test_lifecycle()
    test_verify_stage_cannot_be_skipped()
    test_unknown_stage_errors()
    test_labels_add_remove()
    test_verb_stage()
    test_backward_flag()
    test_show_prints_the_body_and_list_does_not()
    test_show_with_comments_puts_the_body_first()
    test_version_is_derived_not_written_twice()
    try:
        test_config_load()
    except ImportError:
        print("(skipping config test — pyyaml not installed)")
    print("OK — baton smoke tests passed")
