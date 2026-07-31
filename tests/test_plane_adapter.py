"""Runnable check for the Plane adapter's logic (discovery, id resolution,
label caching, stage/state mapping) — no network, no live Plane instance.

A FakePlane stands in for the REST API by matching on (method, path) the
same way the real server would route them, so PlaneBoard's own code (not
urllib) is what's under test. Run: `python tests/test_plane_adapter.py` or
`pytest`.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("PLANE_API_KEY", "fake-token")

from baton.adapters.board.plane import PlaneBoard  # noqa: E402
from baton.base import BatonError  # noqa: E402


class FakePlane:
    """In-memory stand-in for the Plane REST API, keyed the way
    PlaneBoard._request builds paths: '<workspace>/projects/...'."""

    def __init__(self):
        # Sequences spaced the way Plane spaces its own (15000, 25000, ...): the gaps
        # are what let a created stage land BETWEEN two existing ones.
        self.states = [
            {"id": "s-review", "name": "Review", "group": "backlog", "sequence": 15000},
            {"id": "s-approved", "name": "Approved", "group": "unstarted", "sequence": 25000},
            {"id": "s-done", "name": "Done", "group": "completed", "sequence": 45000},
            {"id": "s-cancelled", "name": "Cancelled", "group": "cancelled", "sequence": 55000},
        ]
        self.labels = []  # [{id, name}]
        self.items = {}   # uuid -> issue dict
        self.modules = []          # [{id, name, target_date, total_issues, completed_issues}]
        self.module_items = {}     # module id -> [item uuid]
        self._n = 0
        self.paths: list[str] = []

    def request(self, method, path, body=None, params=None):
        self.paths.append(path)
        parts = path.strip("/").split("/")
        ws, rest = parts[0], parts[1:]
        assert ws == "acme"

        if rest == ["projects"] and method == "GET":
            return {"results": [{"id": "proj-1", "identifier": "ENG"}]}

        assert rest[0] == "projects" and rest[1] == "proj-1"
        rest = rest[2:]

        if rest == ["states"] and method == "GET":
            return {"results": self.states}

        if rest == ["states"] and method == "POST":
            # Plane assigns its OWN sequence here and ignores whatever was sent —
            # appending after every state the project already had. The adapter is
            # expected to notice and fix it with a second call.
            self._n += 1
            row = {"id": f"s-new{self._n}", "name": body["name"], "group": body["group"],
                   "sequence": max(s["sequence"] for s in self.states) + 10}
            self.states.append(row)
            return row

        if rest[:1] == ["states"] and len(rest) == 2 and method == "PATCH":
            row = next(s for s in self.states if s["id"] == rest[1])
            row.update(body)
            self.states.sort(key=lambda s: s["sequence"])
            return row

        if rest[:1] == ["states"] and len(rest) == 2 and method == "DELETE":
            self.states = [s for s in self.states if s["id"] != rest[1]]
            return {}

        if rest == ["labels"]:
            if method == "GET":
                return {"results": self.labels}
            if method == "POST":
                lbl = {"id": f"l-{len(self.labels) + 1}", "name": body["name"]}
                self.labels.append(lbl)
                return lbl

        if rest[0] == "modules":
            if len(rest) == 1:
                if method == "GET":
                    return {"results": self.modules}
                if method == "POST":
                    m = {"id": f"m-{len(self.modules) + 1}", "name": body["name"],
                         "target_date": body.get("target_date"),
                         "total_issues": 0, "completed_issues": 0}
                    self.modules.append(m)
                    return m
            if rest[2:] == ["module-issues"]:
                mid = rest[1]
                if method == "POST":
                    self.module_items.setdefault(mid, []).extend(body["issues"])
                    return {}
                if method == "GET":
                    # link objects, the shape that carries the item uuid under "issue"
                    return {"results": [{"id": f"link-{i}", "issue": u}
                                        for i, u in enumerate(self.module_items.get(mid, []))]}

        if rest[0] == "work-items":
            if len(rest) == 1:
                if method == "GET":
                    return {"results": list(self.items.values())}
                if method == "POST":
                    self._n += 1
                    uid = f"w-{self._n}"
                    issue = {"id": uid, "sequence_id": self._n, "name": body["name"],
                             "description_html": body.get("description_html", ""),
                             "labels": body.get("labels", []), "state": self.states[0]["id"],
                             "priority": body.get("priority", "none")}
                    self.items[uid] = issue
                    return issue
            uid = rest[1]
            if len(rest) == 2:
                if method == "GET":
                    return self.items[uid]
                if method == "PATCH":
                    self.items[uid].update(body)
                    return self.items[uid]
            if rest[2:] == ["comments"]:
                if method == "POST":
                    self.items[uid].setdefault("comments", []).append(
                        {"id": f"c-{len(self.items[uid].get('comments', [])) + 1}",
                         "comment_html": body["comment_html"],
                         "actor": "u-1",
                         "created_at": f"2026-07-27T1{len(self.items[uid].get('comments', []))}:00:00Z"})
                    return self.items[uid]["comments"][-1]
                if method == "GET":
                    # Plane returns newest-first; the adapter must sort.
                    return {"results": list(reversed(self.items[uid].get("comments", [])))}

        raise AssertionError(f"unhandled fake request: {method} {path} body={body}")


def make_adapter():
    ad = PlaneBoard({"base_url": "http://plane.local", "workspace": "acme",
                       "project": "ENG"})
    fake = FakePlane()
    ad._request = lambda method, path, body=None, params=None: fake.request(
        method, path, body, params)
    return ad, fake


def test_discovery_and_lifecycle():
    ad, fake = make_adapter()
    assert ad.list_stages() == ["Review", "Approved", "Done", "Cancelled"]

    it = ad.create("Add dark mode", "<p>body</p>", ["type:idea"])
    assert it.id == "1" and it.stage == "Review" and it.labels == ["type:idea"]
    assert fake.labels and fake.labels[0]["name"] == "type:idea"

    ad.set_stage("1", "approved")  # case-insensitive
    assert ad.get("1").stage == "Approved"
    assert ad.get("1").state == "open"

    ad.comment("1", "looks good")
    assert [c["comment_html"] for c in fake.items["w-1"]["comments"]] == ["<p>looks good</p>"]

    ad.set_labels("1", add=["priority:high"], remove=["type:idea"])
    assert ad.get("1").labels == ["priority:high"]

    ad.close("1")
    got = ad.get("1")
    assert got.stage == "Done" and got.state == "closed"  # first completed/cancelled state in board order


def test_list_filters_by_stage_and_state():
    ad, fake = make_adapter()
    a = ad.create("a", "", [])
    b = ad.create("b", "", [])
    ad.set_stage(a.id, "Approved")
    ad.close(b.id)

    assert [i.id for i in ad.list(stage="Approved")] == [a.id]
    assert [i.id for i in ad.list(state="open")] == [a.id]
    assert [i.id for i in ad.list(state="closed")] == [b.id]
    assert {i.id for i in ad.list(state="all")} == {a.id, b.id}


def test_unknown_stage_errors():
    ad, fake = make_adapter()
    it = ad.create("x", "", [])
    try:
        ad.set_stage(it.id, "Nope")
        assert False, "expected BatonError"
    except BatonError:
        pass


def test_unknown_issue_errors():
    ad, fake = make_adapter()
    try:
        ad.get("999")
        assert False, "expected BatonError"
    except BatonError:
        pass


def test_comments_roundtrip_and_order():
    ad, fake = make_adapter()
    ad.create("Add dark mode", "<p>body</p>", [])
    assert ad.comments("1") == []

    ad.comment("1", "engine listo, PR #12")
    ad.comment("1", "platform pendiente")

    cs = ad.comments("1")
    # oldest first, even though the backend hands them back newest-first
    assert [c.body for c in cs] == ["engine listo, PR #12", "platform pendiente"]
    assert cs[0].author == "u-1" and cs[0].created_at < cs[1].created_at


def test_comment_html_is_stripped():
    ad, fake = make_adapter()
    ad.create("x", "", [])
    fake.items["w-1"]["comments"] = [
        {"comment_html": "<p>l&iacute;nea 1</p><p>l&iacute;nea 2</p>",
         "actor": "u-2", "created_at": "2026-07-27T10:00:00Z"}]
    body = ad.comments("1")[0].body
    assert "<p>" not in body and "&iacute;" not in body
    assert "línea 1" in body and "línea 2" in body


def test_priority_uses_the_native_field_not_a_label():
    """The whole point of native-first: a `priority:high` LABEL is invisible to the
    board's own sorting and filtering. This must land in the real field."""
    ad, fake = make_adapter()
    it = ad.create("urgent thing", "", [], priority="high")
    assert fake.items["w-1"]["priority"] == "high"   # native field, not a label
    assert it.priority == "high" and it.labels == []

    ad.set_priority("1", "low")
    assert fake.items["w-1"]["priority"] == "low"
    assert ad.get("1").priority == "low"

    # the list endpoint expands it to an object; both shapes must read the same
    fake.items["w-1"]["priority"] = {"id": "urgent", "label": "Urgent", "key": None}
    assert ad.get("1").priority == "urgent"

    # default when nobody sets it — and `capabilities()` must claim it
    ad.create("plain", "", [])
    assert ad.get("2").priority == "none"
    assert "priority" in ad.capabilities()


def test_epics_are_native_modules_and_are_never_auto_created():
    ad, fake = make_adapter()
    assert ad.list_groups() == []

    g = ad.create_group("Q3 auth", target_date="2026-09-30")
    assert g.name == "Q3 auth" and g.target_date == "2026-09-30"

    # filing into an epic that does not exist must FAIL, not invent one
    ad.create("in the epic", "", [])
    try:
        ad.set_group("1", "Nope")
        assert False, "expected BatonError"
    except BatonError as e:
        assert "not found" in str(e) and "Q3 auth" in str(e)
    assert len(fake.modules) == 1        # nothing was created behind our back

    ad.set_group("1", "q3 AUTH")         # by name, case-insensitive
    assert fake.module_items["m-1"] == ["w-1"]

    ad.create("outside the epic", "", [])
    assert [i.id for i in ad.list(group="Q3 auth")] == ["1"]
    assert len(ad.list()) == 2

    fake.modules[0].update(total_issues=12, completed_issues=7)
    got = ad.list_groups()[0]
    assert (got.total, got.done) == (12, 7)   # progress comes from the board, not us


def test_a_created_stage_is_put_where_the_board_wants_it():
    """Plane ignores `sequence` on create — it appends. Order is not decoration here:
    `require_verify` and `flag_backward` read the board's stage order to tell a step
    forward from a step back, so a stage that lands at the end inverts them."""
    ad, fake = make_adapter()
    ad.create_stage("Verify", group="started", color="#3b82f6", position=2)
    assert [s["name"] for s in fake.states] == [
        "Review", "Approved", "Verify", "Done", "Cancelled"]
    assert next(s for s in fake.states if s["name"] == "Verify")["sequence"] == 30000

    # created without a position: appended, which is the backend's own behaviour
    ad.create_stage("Later", group="started", color="#3b82f6")
    assert [s["name"] for s in fake.states][-1] == "Later"


def test_delete_stage_resolves_the_name_and_keeps_the_trailing_slash():
    """The slash is load-bearing: without it Plane answers 301 and urllib does not
    follow a redirect on DELETE, so `--prune` reported failure while every stage stayed
    exactly where it was. Found by running it against a real board."""
    ad, fake = make_adapter()
    ad.delete_stage("done")                       # case-insensitive, like every lookup
    assert [s["name"] for s in fake.states] == ["Review", "Approved", "Cancelled"]
    assert fake.paths[-1].endswith("/"), fake.paths[-1]


if __name__ == "__main__":
    test_discovery_and_lifecycle()
    test_priority_uses_the_native_field_not_a_label()
    test_epics_are_native_modules_and_are_never_auto_created()
    test_list_filters_by_stage_and_state()
    test_unknown_stage_errors()
    test_unknown_issue_errors()
    test_comments_roundtrip_and_order()
    test_comment_html_is_stripped()
    print("ok")
