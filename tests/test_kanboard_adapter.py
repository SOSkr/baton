"""Runnable check for the Kanboard adapter — no network, no live instance.

A FakeKanboard stands in for the JSON-RPC server, dispatching on the method name
and params the same way Kanboard routes them, so KanboardBoard's own logic is what
is under test rather than urllib.

The fake copies the behaviours that were MEASURED against a real instance, because
those are the ones the adapter exists to handle and the ones a naive fake would
paper over:

  - `setTaskTags` REPLACES the whole tag set
  - writes answer `false` instead of raising
  - `getAllTasks` needs a status_id, so open and closed are two calls
  - a task created with no column lands in the first one
  - `getAllTaskLinks` carries each member's `is_active`, so progress is one call

Run: `python tests/test_kanboard_adapter.py` or `pytest`.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("KANBOARD_TOKEN", "fake-token")

from baton.adapters.board.kanboard import KanboardBoard  # noqa: E402
from baton.base import BatonError  # noqa: E402

TARGET = {"base_url": "https://board.acme.test", "project": "acme", "user": "admin"}


class FakeKanboard:
    def __init__(self):
        self.columns = [
            {"id": 1, "title": "Review", "position": 1, "project_id": 1},
            {"id": 2, "title": "Approved", "position": 2, "project_id": 1},
            {"id": 3, "title": "In Progress", "position": 3, "project_id": 1},
            {"id": 4, "title": "Deployed", "position": 4, "project_id": 1},
        ]
        self.categories = [{"id": 7, "name": "epic", "project_id": 1}]
        self.tasks = {}          # id -> task dict
        self.tags = {}           # task id -> [names]
        self.comments = []
        self.links = []          # {task_id, opposite_task_id, link_id}
        self.project = {"id": 1, "name": "acme", "identifier": "",
                        "priority_start": 0, "priority_end": 3}
        self.calls = []
        self._n = 0
        self.add_task("uno", column_id=1, priority=3, tags=["type:bug", "area:cli"])

    # -- helpers the tests use directly ------------------------------------
    def add_task(self, title, **kw):
        self._n += 1
        t = {"id": self._n, "title": title, "description": kw.get("description", ""),
             "column_id": kw.get("column_id", self.columns[0]["id"]),
             "is_active": kw.get("is_active", 1), "project_id": 1,
             "category_id": kw.get("category_id", 0), "priority": kw.get("priority", 0),
             "date_due": kw.get("date_due", 0)}
        self.tasks[t["id"]] = t
        self.tags[t["id"]] = list(kw.get("tags", []))
        return t["id"]

    # -- the wire ----------------------------------------------------------
    def rpc(self, method, **p):
        self.calls.append((method, p))
        fn = getattr(self, "m_" + method, None)
        if fn is None:
            raise AssertionError(f"the adapter called an unstubbed method: {method}")
        return fn(**p)

    # -- discovery ---------------------------------------------------------
    def m_getVersion(self):
        return "v1.2.53"

    def m_getProjectByName(self, name):
        return dict(self.project) if name == self.project["name"] else False

    def m_getProjectById(self, project_id):
        return dict(self.project)

    def m_getColumns(self, project_id):
        return [dict(c) for c in sorted(self.columns, key=lambda c: c["position"])]

    def m_getAllCategories(self, project_id):
        return [dict(c) for c in self.categories]

    def m_getAllUsers(self):
        return [{"id": 1, "username": "admin", "role": "app-admin"}]

    def m_getUserByName(self, username):
        return next((u for u in self.m_getAllUsers() if u["username"] == username), False)

    def m_getAllLinks(self):
        return [{"id": 8, "label": "targets milestone"},
                {"id": 9, "label": "is a milestone of"}]

    # -- items -------------------------------------------------------------
    def m_getAllTasks(self, project_id, status_id):
        return [dict(t) for t in self.tasks.values() if t["is_active"] == status_id]

    def m_getTask(self, task_id):
        t = self.tasks.get(task_id)
        # A real instance answers with its own application_url, which is empty on a
        # fresh install — the adapter must not trust it.
        return {**t, "url": f"http://localhost/task/{task_id}"} if t else False

    def m_createTask(self, project_id, title, **kw):
        tags = kw.pop("tags", [])
        return self.add_task(title, tags=tags, **kw)

    def m_updateTask(self, id, **kw):
        if id not in self.tasks:
            return False
        self.tasks[id].update(kw)
        return True

    def m_closeTask(self, task_id):
        if task_id not in self.tasks:
            return False
        self.tasks[task_id]["is_active"] = 0
        return True

    def m_moveTaskPosition(self, project_id, task_id, column_id, position, swimlane_id):
        if task_id not in self.tasks:
            return False
        self.tasks[task_id]["column_id"] = column_id
        return True

    def m_getTaskTags(self, task_id):
        return {str(i): name for i, name in enumerate(self.tags.get(task_id, []), 1)}

    def m_setTaskTags(self, project_id, task_id, tags):
        # THE behaviour this adapter exists to work around: a full replace.
        self.tags[task_id] = list(tags)
        return True

    def m_createComment(self, task_id, user_id, content):
        self.comments.append({"id": len(self.comments) + 1, "task_id": task_id,
                              "user_id": user_id, "username": "admin",
                              "comment": content,
                              "date_creation": 1785600000 + len(self.comments)})
        return True

    def m_getAllComments(self, task_id):
        return [dict(c) for c in self.comments if c["task_id"] == task_id]

    # -- links -------------------------------------------------------------
    def m_createTaskLink(self, task_id, opposite_task_id, link_id):
        self.links.append({"task_id": task_id, "opposite_task_id": opposite_task_id,
                           "link_id": link_id})
        return True

    def m_getAllTaskLinks(self, task_id):
        # From the epic's side Kanboard reports the OPPOSITE label, and carries the
        # member's own state in the same payload.
        out = []
        for lk in self.links:
            if lk["opposite_task_id"] == task_id:
                t = self.tasks[lk["task_id"]]
                out.append({"id": len(out) + 1, "task_id": t["id"], "title": t["title"],
                            "label": "is a milestone of", "is_active": t["is_active"],
                            "column_title": "Review"})
        return out

    # -- bootstrap ---------------------------------------------------------
    def m_createProject(self, name):
        self.project = {"id": 2, "name": name, "identifier": "",
                        "priority_start": 0, "priority_end": 3}
        return 2

    def m_updateProject(self, project_id, name, **kw):
        self.project.update(kw)
        return True

    def m_createCategory(self, project_id, name):
        self.categories.append({"id": 99, "name": name, "project_id": project_id})
        return 99

    def m_addColumn(self, project_id, title):
        self.columns.append({"id": max(c["id"] for c in self.columns) + 1, "title": title,
                             "position": max(c["position"] for c in self.columns) + 1,
                             "project_id": project_id})
        return True

    def m_changeColumnPosition(self, project_id, column_id, position):
        col = next(c for c in self.columns if c["id"] == column_id)
        rest = [c for c in self.columns if c["id"] != column_id]
        rest.sort(key=lambda c: c["position"])
        rest.insert(position - 1, col)
        for i, c in enumerate(rest, 1):
            c["position"] = i
        return True

    def m_removeColumn(self, column_id):
        before = len(self.columns)
        self.columns = [c for c in self.columns if c["id"] != column_id]
        return len(self.columns) < before


def board(fake=None):
    fake = fake or FakeKanboard()
    b = KanboardBoard(TARGET, token="fake-token")
    b._rpc = fake.rpc
    return b, fake


# --------------------------------------------------------------------- tests
def test_probe_names_the_project():
    b, _ = board()
    assert "acme" in b.probe()


def test_probe_fails_when_the_project_is_not_there():
    b, fake = board()
    fake.project = {"id": 1, "name": "otro", "priority_start": 0, "priority_end": 3}
    try:
        b.probe()
    except BatonError as e:
        assert "not there" in str(e)
    else:
        raise AssertionError("a missing project has to be an error, not an empty answer")


def test_item_mapping():
    b, fake = board()
    item = b.get("1")
    assert item.id == "1"
    assert item.stage == "Review"
    assert item.state == "open"
    assert item.priority == "high"                    # 3 -> high
    assert item.labels == ["area:cli", "type:bug"]
    # NOT the task's own url: Kanboard renders that from a setting that is empty on a
    # fresh install and says localhost from a public instance.
    assert item.url == "https://board.acme.test/task/1"


def test_state_comes_from_is_active_not_from_the_column():
    b, fake = board()
    tid = fake.add_task("cerrada", column_id=1, is_active=0)   # closed, still in Review
    assert b.get(str(tid)).state == "closed"
    assert b.get(str(tid)).stage == "Review"


def test_close_never_moves_the_item():
    """The BATON-18 regression: the Plane adapter picked "the first closed-group state"
    and sent cancelled items to Deployed. Closing must not touch the column at all."""
    b, fake = board()
    b.close("1", "porque sí")
    assert fake.tasks[1]["is_active"] == 0
    assert fake.tasks[1]["column_id"] == 1
    assert not [c for c, _ in fake.calls if c == "moveTaskPosition"]


def test_set_labels_keeps_the_tags_it_was_not_told_about():
    """`setTaskTags` replaces the whole set, so a naive add would silently drop the
    rest. Measured on a live instance before it was written this way."""
    b, fake = board()
    b.set_labels("1", add=["needs-review"])
    assert fake.tags[1] == ["area:cli", "needs-review", "type:bug"]
    b.set_labels("1", remove=["type:bug"])
    assert fake.tags[1] == ["area:cli", "needs-review"]


def test_create_carries_tags_and_priority():
    b, fake = board()
    item = b.create("nueva", "cuerpo", ["type:idea"], priority="urgent")
    assert fake.tasks[int(item.id)]["priority"] == 4
    assert fake.tags[int(item.id)] == ["type:idea"]
    assert item.body == "cuerpo"


def test_body_is_stored_verbatim():
    """The whole reason this backend was chosen: what goes in comes back."""
    b, fake = board()
    md = "## Criterios\n- [ ] uno con `<id>` y `List<T>`\n\n| a | b |\n|---|---|\n"
    item = b.create("md", md, [])
    assert b.get(item.id).body == md


def test_list_hides_epics():
    b, fake = board()
    fake.add_task("Q3 auth", category_id=7)
    assert [i.title for i in b.list()] == ["uno"]


def test_list_filters():
    b, fake = board()
    fake.add_task("dos", column_id=2, tags=["area:web"])
    fake.add_task("tres", column_id=2, is_active=0)
    assert [i.title for i in b.list(stage="Approved")] == ["dos"]
    assert [i.title for i in b.list(label="area:web")] == ["dos"]
    assert [i.title for i in b.list(state="closed")] == ["tres"]
    assert len(b.list(state="all")) == 3


def test_groups_progress_comes_from_one_call():
    b, fake = board()
    fake.add_task("Q3 auth", category_id=7, date_due=1790799387)
    done = fake.add_task("hecha", is_active=0)
    fake.add_task("abierta")
    b.set_group(str(done), "Q3 auth")
    b.set_group("1", "Q3 auth")
    fake.calls.clear()
    g = b.list_groups()[0]
    assert (g.name, g.total, g.done) == ("Q3 auth", 2, 1)
    assert g.target_date == "2026-09-30"
    # One getAllTaskLinks for the epic, and NOT one getTask per member.
    assert [c for c, _ in fake.calls].count("getAllTaskLinks") == 1
    assert "getTask" not in [c for c, _ in fake.calls]


def test_list_by_group():
    b, fake = board()
    fake.add_task("Q3 auth", category_id=7)
    fake.add_task("fuera")
    b.set_group("1", "Q3 auth")
    assert [i.title for i in b.list(group="Q3 auth")] == ["uno"]


def test_set_group_uses_the_link_type_by_label_not_by_id():
    b, fake = board()
    fake.add_task("Q3 auth", category_id=7)
    b.set_group("1", "Q3 auth")
    assert fake.links[0]["link_id"] == 8          # resolved from getAllLinks
    assert ("getAllLinks", {}) in fake.calls


def test_epic_that_does_not_exist_is_an_error_not_a_creation():
    b, fake = board()
    try:
        b.set_group("1", "no existe")
    except BatonError as e:
        assert "not found" in str(e)
    else:
        raise AssertionError("filing an item must never invent a deliverable")


def test_capabilities_are_asked_of_the_backend():
    """The BATON-21 lesson: a constant is how `doctor` came to report epics on a board
    that had them switched off."""
    b, fake = board()
    assert b.capabilities() == {"priority", "groups"}
    fake.categories = []                       # no epic category -> no way to mark one
    assert b.capabilities() == {"priority"}


def test_groups_without_the_category_say_so():
    b, fake = board()
    fake.categories = []
    try:
        b.list_groups()
    except BatonError as e:
        assert "epic" in str(e)
    else:
        raise AssertionError("a missing concept has to be reported, never faked")


def test_stage_groups_are_empty_because_columns_carry_no_lifecycle():
    b, _ = board()
    assert set(b.stage_groups().values()) == {""}


def test_stage_positions_are_translated_to_kanboard_counting():
    b, fake = board()
    b.set_stage_position("Deployed", 0)         # baton 0-based -> kanboard 1-based
    assert b.list_stages() == ["Deployed", "Review", "Approved", "In Progress"]


def test_default_stage_is_the_first_column():
    b, fake = board()
    assert b.default_stage() == "Review"
    b.set_default_stage("In Progress")
    assert b.default_stage() == "In Progress"


def test_create_stage_ignores_group_and_colour():
    b, fake = board()
    b.create_stage("Verify", group="started", color="#3b82f6")
    assert "Verify" in b.list_stages()


def test_create_project_makes_room_for_five_priorities_and_for_epics():
    b, fake = board()
    b.create_project("nuevo")
    assert fake.project["priority_end"] == 4     # urgent would be unreachable at 3
    assert [c["name"] for c in fake.categories][-1] == "epic"


def test_find_project_answers_none_not_an_error():
    b, fake = board()
    fake.project = {"id": 1, "name": "otro", "priority_start": 0, "priority_end": 3}
    assert b.find_project() is None              # bootstrap creates on None


def test_moving_to_the_stage_it_is_already_in_is_a_no_op():
    """Kanboard responde `false` a un movimiento que no mueve nada, igual que a uno
    que falla. Sin esto, `advance` a la etapa actual es un error."""
    b, fake = board()
    fake.m_moveTaskPosition = lambda **kw: (_ for _ in ()).throw(
        AssertionError("no debería llamarse: la tarea ya está en Review"))
    b.set_stage("1", "Review")
    assert fake.tasks[1]["column_id"] == 1


def test_a_write_that_answers_false_is_an_error():
    """Kanboard reports failure by returning `false`. Taken at face value, a move that
    never happened reports success and the item silently stays put."""
    b, fake = board()
    try:
        b.edit_body("999", "cuerpo nuevo")       # no such task -> updateTask: false
    except BatonError as e:
        assert "updateTask" in str(e)
    else:
        raise AssertionError("`false` from a write has to surface")


def test_moving_a_task_that_does_not_exist_says_so():
    b, _ = board()
    try:
        b.set_stage("999", "Approved")
    except BatonError as e:
        assert "999" in str(e) and "not found" in str(e)
    else:
        raise AssertionError("un id inexistente tiene que decirse, no moverse")


def test_a_write_that_answers_zero_is_an_error_too():
    """Kanboard is not consistent about how it says no: `createTask` on a project that
    does not exist answers `0`, not `false`. An `is False` check walks past it."""
    b, fake = board()
    fake.m_addColumn = lambda project_id, title: 0
    try:
        b.create_stage("Verify", group="started", color="#000")
    except BatonError as e:
        assert "addColumn" in str(e)
    else:
        raise AssertionError("`0` from a write has to surface, same as `false`")


def test_comments_round_trip_with_author_and_date():
    b, fake = board()
    b.comment("1", "primero")
    b.comment("1", "segundo")
    got = b.comments("1")
    assert [c.body for c in got] == ["primero", "segundo"]
    assert got[0].author == "admin"
    assert got[0].created_at.startswith("2026-")   # unix seconds -> ISO-8601


def test_unknown_stage_lists_the_ones_that_exist():
    b, _ = board()
    try:
        b.set_stage("1", "Ninguna")
    except BatonError as e:
        assert "Review" in str(e)
    else:
        raise AssertionError("a bad stage name should say what the board has")


if __name__ == "__main__":
    ns = dict(globals())
    fns = [(n, f) for n, f in ns.items() if n.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"ok  {name}")
    print(f"\n{len(fns)} checks passed")
