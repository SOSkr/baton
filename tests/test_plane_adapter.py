"""Runnable check for the Plane adapter's logic (discovery, id resolution,
label caching, stage/state mapping) — no network, no live Plane instance.

A FakePlane stands in for the REST API by matching on (method, path) the
same way the real server would route them, so PlaneAdapter's own code (not
urllib) is what's under test. Run: `python tests/test_plane_adapter.py` or
`pytest`.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("PLANE_API_KEY", "fake-token")

from baton.adapters.plane import PlaneAdapter  # noqa: E402
from baton.base import BatonError  # noqa: E402


class FakePlane:
    """In-memory stand-in for the Plane REST API, keyed the way
    PlaneAdapter._request builds paths: '<workspace>/projects/...'."""

    def __init__(self):
        self.states = [
            {"id": "s-review", "name": "Review", "group": "backlog", "sequence": 1},
            {"id": "s-approved", "name": "Approved", "group": "unstarted", "sequence": 2},
            {"id": "s-done", "name": "Done", "group": "completed", "sequence": 3},
            {"id": "s-cancelled", "name": "Cancelled", "group": "cancelled", "sequence": 4},
        ]
        self.labels = []  # [{id, name}]
        self.items = {}   # uuid -> issue dict
        self._n = 0

    def request(self, method, path, body=None, params=None):
        parts = path.strip("/").split("/")
        ws, rest = parts[0], parts[1:]
        assert ws == "desarrollo"

        if rest == ["projects"] and method == "GET":
            return {"results": [{"id": "proj-1", "identifier": "PROJ"}]}

        assert rest[0] == "projects" and rest[1] == "proj-1"
        rest = rest[2:]

        if rest == ["states"] and method == "GET":
            return {"results": self.states}

        if rest == ["labels"]:
            if method == "GET":
                return {"results": self.labels}
            if method == "POST":
                lbl = {"id": f"l-{len(self.labels) + 1}", "name": body["name"]}
                self.labels.append(lbl)
                return lbl

        if rest[0] == "work-items":
            if len(rest) == 1:
                if method == "GET":
                    return {"results": list(self.items.values())}
                if method == "POST":
                    self._n += 1
                    uid = f"w-{self._n}"
                    issue = {"id": uid, "sequence_id": self._n, "name": body["name"],
                             "description_html": body.get("description_html", ""),
                             "labels": body.get("labels", []), "state": self.states[0]["id"]}
                    self.items[uid] = issue
                    return issue
            uid = rest[1]
            if len(rest) == 2:
                if method == "GET":
                    return self.items[uid]
                if method == "PATCH":
                    self.items[uid].update(body)
                    return self.items[uid]
            if rest[2:] == ["comments"] and method == "POST":
                self.items[uid].setdefault("comments", []).append(body["comment_html"])
                return {"id": "c-1", **body}

        raise AssertionError(f"unhandled fake request: {method} {path} body={body}")


def make_adapter():
    ad = PlaneAdapter({"base_url": "http://plane.local", "workspace": "desarrollo",
                       "project": "PROJ"})
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
    assert fake.items["w-1"]["comments"] == ["<p>looks good</p>"]

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


if __name__ == "__main__":
    test_discovery_and_lifecycle()
    test_list_filters_by_stage_and_state()
    test_unknown_stage_errors()
    test_unknown_issue_errors()
    print("ok")
