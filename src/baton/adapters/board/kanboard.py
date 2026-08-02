"""Kanboard adapter — JSON-RPC, and markdown that comes back as markdown.

Chosen over Plane by measurement, not preference: `docs/design/board-backends.md`
has the experiment. The short version is that Kanboard stores the body you sent and
renders it when it shows it, instead of rewriting it into editor HTML the moment a
human opens the item.

Config (config.target):
  base_url: "https://kanboard.example.com"   # instance URL (required)
  project:  "baton"                          # project NAME — Kanboard has no identifier
  user:     "admin"                          # who comments are attributed to (optional)

Auth: KANBOARD_TOKEN env var — never in config.yaml. It goes as HTTP Basic with the
literal username `jsonrpc`, which is Kanboard's convention for the application token.

Every shape in here was read off a live instance, not off the docs: which calls
return `false` instead of raising, that `setTaskTags` REPLACES, that `createComment`
demands a `user_id`, and that a task created without a column lands in the first one.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request

from ...base import BatonError, Comment, Group, Item, user_agent
from .base import BoardBase

# baton's closed set <-> Kanboard's integer. Kanboard does not have priorities, it has
# a NUMBER with a per-project range, so this mapping is the adapter's invention and not
# a translation between two vocabularies.
#
# A fresh project ships `priority_end: 0..3` — four slots for five words — so
# `create_project` widens it to 4. The API itself never clamps (verified: a task
# accepted priority=4 on a 0..3 project); the range is what the web UI's slider reads,
# so leaving it at 3 would mean `urgent` was settable by baton and invisible to a human.
_PRIORITY = {"none": 0, "low": 1, "medium": 2, "high": 3, "urgent": 4}
_PRIORITY_NAME = {v: k for k, v in _PRIORITY.items()}

# An epic is a TASK — Kanboard has no epic object — so it needs something to tell it
# apart from the work, or every epic would show up in `baton list` as an item.
#
# A category, because it is a first-class field, allows exactly one per task, and does
# not collide with `set_labels`, which uses tags. Rejected: a swimlane (mixes layout
# with meaning — dragging a card between rows would change what the thing IS), and
# inferring it from having children (an epic created this morning, still empty, would
# not exist).
_EPIC_CATEGORY = "epic"

# Kanboard seeds eleven link types; these two are the pair for "this item belongs to
# that deliverable". The id is looked up by label rather than hardcoded to 8, because
# 8 is a row id in a seeded table and nothing promises it.
#
# The labels read backwards and that is Kanboard's doing, not a mistake here: an item
# is linked with `targets milestone`, and from the EPIC's side the same link comes back
# labelled `is a milestone of`. Verified against an instance; `getAllTaskLinks` returns
# no link id, so matching the label is the only handle there is.
_LINK_TO_EPIC = "targets milestone"
_LINK_FROM_EPIC = "is a milestone of"


class KanboardBoard(BoardBase):
    def __init__(self, target: dict, token: str | None = None):
        base_url = (target.get("base_url") or "").rstrip("/")
        self.project_name = target.get("project")
        if not (base_url and self.project_name):
            raise BatonError("kanboard adapter needs config.target.base_url and .project")
        self.url = f"{base_url}/jsonrpc.php"
        self.web = base_url
        self.user_name = target.get("user")
        self.token = token or os.environ.get("KANBOARD_TOKEN")
        if not self.token:
            raise BatonError("KANBOARD_TOKEN env var required (never put it in config.yaml)")
        self._project: dict | None = None
        self._columns: list[dict] | None = None
        self._user_id: int | None = None

    # ---------- JSON-RPC ----------
    def _rpc(self, method: str, **params):
        """One call. Raises on a JSON-RPC error; returns `result` as-is otherwise.

        `result` is frequently the bare `false` that Kanboard uses for "did not work"
        on write methods — that is NOT an error here, because for some calls it means
        "nothing to do". Callers that care check it; `_ok` is the shorthand.
        """
        payload = json.dumps({"jsonrpc": "2.0", "id": 1,
                              "method": method, "params": params}).encode()
        auth = base64.b64encode(f"jsonrpc:{self.token}".encode()).decode()
        req = urllib.request.Request(self.url, data=payload, method="POST", headers={
            "Content-Type": "application/json", "Authorization": f"Basic {auth}",
            "User-Agent": user_agent()})
        try:
            with urllib.request.urlopen(req) as r:
                body = json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            raise BatonError(f"kanboard {method} failed: {e.code} {e.read().decode()[:200]}")
        except urllib.error.URLError as e:
            raise BatonError(f"kanboard {method} unreachable: {e.reason}")
        if isinstance(body, dict) and body.get("error"):
            err = body["error"]
            raise BatonError(f"kanboard {method} failed: "
                             f"{err.get('message')} {err.get('data', '')}".strip())
        return body.get("result") if isinstance(body, dict) else None

    def _ok(self, method: str, **params) -> None:
        """A write that has to have happened. Kanboard answers `false` instead of
        raising, so without this a failed move reports success and the item silently
        stays where it was.

        `0` counts too, and that is not hypothetical: `createTask` against a project
        that does not exist answers `0`, not `false`. An `is False` check walks right
        past it — found while migrating, on a call that had already passed review.
        """
        if self._rpc(method, **params) in (False, 0):
            raise BatonError(f"kanboard {method} returned false (params: "
                             f"{', '.join(sorted(params))})")

    def probe(self) -> str:
        """Resolving the configured project proves URL, token and that THIS project is
        reachable, in one call — a token that is merely set has told you nothing."""
        p = self._rpc("getProjectByName", name=self.project_name)
        if not p:
            raise BatonError(f"reached {self.url} but project {self.project_name!r} "
                             f"is not there")
        return f"{p.get('name')} — project {p.get('id')}, kanboard {self._rpc('getVersion')}"

    # ---------- discovery ----------
    def _proj(self) -> int:
        if self._project is None:
            p = self._rpc("getProjectByName", name=self.project_name)
            if not p:
                raise BatonError(f"project {self.project_name!r} not found on {self.web}")
            self._project = p
        return int(self._project["id"])

    def _cols(self) -> list[dict]:
        if self._columns is None:
            rows = self._rpc("getColumns", project_id=self._proj()) or []
            self._columns = sorted(rows, key=lambda c: int(c.get("position", 0)))
        return self._columns

    def _col_by_name(self, name: str) -> dict:
        for c in self._cols():
            if c["title"].lower() == name.lower():
                return c
        names = ", ".join(c["title"] for c in self._cols())
        raise BatonError(f"stage {name!r} not found. Board stages: {names or '(none)'}")

    def _uid(self) -> int:
        """Who a comment is attributed to.

        The application token is not a user, so Kanboard cannot infer this and
        `createComment` refuses without it. One admin on the board is the common case
        and needs no config; more than one is ambiguous, and guessing an author is
        worse than asking.
        """
        if self._user_id is None:
            if self.user_name:
                u = self._rpc("getUserByName", username=self.user_name)
                if not u:
                    raise BatonError(f"config.target.user {self.user_name!r} is not a "
                                     f"user on this Kanboard")
                self._user_id = int(u["id"])
            else:
                admins = [u for u in (self._rpc("getAllUsers") or [])
                          if u.get("role") == "app-admin"]
                if len(admins) != 1:
                    raise BatonError(
                        f"{len(admins)} admin users on this Kanboard — set "
                        f"config.target.user to say who comments are attributed to")
                self._user_id = int(admins[0]["id"])
        return self._user_id

    # ---------- item mapping ----------
    def _tags(self, task_id) -> list[str]:
        # getTaskTags answers {tag_id: name}; baton only ever wants the names.
        #
        # ponytail: one call per task, so `list()` is N+1. Kanboard exposes no bulk
        # tag read — `getAllTasks` returns everything about a task EXCEPT its tags —
        # and at board scale (tens of items) that is a handful of local calls. If a
        # board ever gets big enough to feel it, the fix is a tag cache filled from
        # `getTaskTags` per column, not a different shape here.
        return sorted((self._rpc("getTaskTags", task_id=int(task_id)) or {}).values())

    def _to_item(self, t: dict) -> Item:
        titles = {int(c["id"]): c["title"] for c in self._cols()}
        return Item(
            id=str(t["id"]),
            title=t.get("title", ""),
            # Built from config, NOT from the task's own `url`: Kanboard renders that
            # from its `application_url` setting, which is empty on a fresh install and
            # answers `http://localhost/task/3` from a public instance.
            url=f"{self.web}/task/{t['id']}",
            stage=titles.get(int(t.get("column_id") or 0)),
            # No lifecycle groups here (see `stage_groups`), so open/closed comes from
            # the task's own flag instead of being inferred from which column it sits in.
            state="open" if int(t.get("is_active", 1)) else "closed",
            labels=self._tags(t["id"]),
            body=t.get("description") or "",
            priority=_PRIORITY_NAME.get(int(t.get("priority") or 0)),
        )

    # ---------- capabilities ----------
    def capabilities(self) -> set[str]:
        """Asked of the backend, never a constant.

        Returning a fixed set is how `doctor` came to report "epics: 0" on a Plane
        board whose modules were merely switched off — a diagnostic that lies is worse
        than none. Here `groups` is real only once the epic category exists, which is
        `create_project`'s job and a human's to undo.
        """
        caps = {"priority"}                      # native integer field, always present
        try:
            if self._epic_category() is not None:
                caps.add("groups")
        except BatonError:
            pass                                 # project unreachable: report less, not wrong
        return caps

    def _epic_category(self) -> int | None:
        for c in self._rpc("getAllCategories", project_id=self._proj()) or []:
            if (c.get("name") or "").lower() == _EPIC_CATEGORY:
                return int(c["id"])
        return None

    def _require_epic_category(self) -> int:
        cid = self._epic_category()
        if cid is None:
            raise BatonError(
                f"this project has no {_EPIC_CATEGORY!r} category, so epics cannot be "
                f"told apart from items. `baton bootstrap` creates it.")
        return cid

    # ---------- groups (epics: a task, plus links) ----------
    def _link_id(self, label: str) -> int:
        for link in self._rpc("getAllLinks") or []:
            if link.get("label") == label:
                return int(link["id"])
        raise BatonError(f"this Kanboard has no {label!r} link type")

    def _tasks(self, *, state: str = "open") -> list[dict]:
        """Kanboard splits open and closed into two calls; `all` costs both."""
        want = {"open": [1], "closed": [0]}.get(state, [1, 0])
        out: list[dict] = []
        for status in want:
            out += self._rpc("getAllTasks", project_id=self._proj(), status_id=status) or []
        return out

    def _epic(self, name: str) -> dict:
        cid = self._require_epic_category()
        for t in self._tasks(state="all"):
            if int(t.get("category_id") or 0) == cid and t.get("title", "").lower() == name.lower():
                return t
        names = ", ".join(t["title"] for t in self._tasks(state="all")
                          if int(t.get("category_id") or 0) == cid)
        raise BatonError(f"epic {name!r} not found. Existing: {names or '(none)'}. "
                         f"Epics are created deliberately — see the baton-roadmap skill.")

    def _members(self, epic_id) -> list[dict]:
        """The epic's items. ONE call: the link payload already carries each member's
        `is_active` and `column_title`, so progress needs no follow-up per item."""
        rows = self._rpc("getAllTaskLinks", task_id=int(epic_id)) or []
        return [r for r in rows if r.get("label") == _LINK_FROM_EPIC]

    def list_groups(self) -> list[Group]:
        cid = self._require_epic_category()
        out = []
        for t in self._tasks(state="all"):
            if int(t.get("category_id") or 0) != cid:
                continue
            members = self._members(t["id"])
            out.append(Group(
                name=t.get("title", ""), id=str(t["id"]),
                # Kanboard keeps dates as unix seconds; 0 means unset.
                target_date=_date(t.get("date_due")),
                total=len(members),
                done=sum(1 for m in members if not int(m.get("is_active", 1)))))
        return out

    def create_group(self, name, *, target_date=None, description="") -> Group:
        params = {"project_id": self._proj(), "title": name,
                  "category_id": self._require_epic_category(),
                  "description": description}
        if target_date:
            params["date_due"] = target_date
        tid = self._rpc("createTask", **params)
        if not tid:
            raise BatonError(f"kanboard refused to create the epic {name!r}")
        return Group(name=name, id=str(tid), target_date=target_date)

    def set_group(self, item_id: str, name: str) -> None:
        self._ok("createTaskLink", task_id=int(item_id),
                 opposite_task_id=int(self._epic(name)["id"]),
                 link_id=self._link_id(_LINK_TO_EPIC))

    # ---------- creation (bootstrap) ----------
    def find_project(self) -> dict | None:
        """None means "not there", never "could not look" — bootstrap creates on None,
        so an error answered as None would make a second project."""
        p = self._rpc("getProjectByName", name=self.project_name)
        if not p:
            return None
        self._project = p
        return {"id": str(p["id"]), "identifier": p.get("identifier") or "",
                "name": p.get("name", "")}

    def create_project(self, name: str) -> dict:
        """The project, and the two things that make it usable as a baton board.

        A fresh Kanboard project already ships `Backlog · Ready · Work in progress ·
        Done`, which `bootstrap` then reconciles against `board_stages` — nothing to
        seed. What it does NOT ship is the room for five priorities or somewhere to
        keep epics, and both are cheaper to do here than to explain later.
        """
        pid = self._rpc("createProject", name=name)
        if not pid:
            raise BatonError(f"kanboard refused to create project {name!r}")
        self._project, self._columns = None, None
        self._rpc("updateProject", project_id=int(pid), name=name,
                  priority_start=0, priority_end=max(_PRIORITY.values()))
        self._rpc("createCategory", project_id=int(pid), name=_EPIC_CATEGORY)
        return {"id": str(pid), "identifier": "", "name": name}

    def stage_groups(self) -> dict[str, str]:
        """Kanboard columns carry no lifecycle meaning — a column is a column — so
        every stage reports an empty group, which `BoardBase` defines as "no such
        concept". Nothing is lost by it: open/closed comes off the task's own
        `is_active`, not off which column it happens to sit in.
        """
        return {c["title"]: "" for c in self._cols()}

    def create_stage(self, name: str, *, group: str, color: str) -> None:
        """`group` and `color` are accepted and dropped. Kanboard columns have neither,
        and the alternative — refusing — would make every board rule that passes them
        provider-aware for no gain."""
        self._ok("addColumn", project_id=self._proj(), title=name)
        self._columns = None

    def set_stage_position(self, name: str, position: int) -> None:
        """Kanboard counts columns from 1; baton passes 0-based."""
        self._ok("changeColumnPosition", project_id=self._proj(),
                 column_id=int(self._col_by_name(name)["id"]), position=position + 1)
        self._columns = None

    def default_stage(self) -> str | None:
        """The FIRST column, because that is where a task with no column given lands —
        verified against an instance. Kanboard has no flag for this, so the concept
        exists but is positional."""
        cols = self._cols()
        return cols[0]["title"] if cols else None

    def set_default_stage(self, name: str) -> None:
        """Which is why making a stage the default means moving it to the front. It
        agrees with the declared order rather than fighting it: the stage `bootstrap`
        wants new items to land in is the first one in `board_stages` anyway."""
        self.set_stage_position(name, 0)

    def delete_stage(self, name: str) -> None:
        self._ok("removeColumn", column_id=int(self._col_by_name(name)["id"]))
        self._columns = None

    # ---------- items ----------
    def list_stages(self) -> list[str]:
        return [c["title"] for c in self._cols()]

    def create(self, title: str, body: str, labels: list[str],
               priority: str | None = None) -> Item:
        params = {"project_id": self._proj(), "title": title, "description": body or ""}
        if labels:
            params["tags"] = labels
        if priority:
            params["priority"] = _PRIORITY.get(priority, 0)
        tid = self._rpc("createTask", **params)
        if not tid:
            raise BatonError(f"kanboard refused to create the item {title!r}")
        return self.get(str(tid))

    def get(self, item_id: str) -> Item:
        t = self._rpc("getTask", task_id=int(item_id))
        if not t:
            raise BatonError(f"item #{item_id} not found on {self.project_name}")
        return self._to_item(t)

    def list(self, *, stage=None, label=None, state="open", group=None) -> list[Item]:
        rows = self._tasks(state=state)
        epic_cat = self._epic_category()
        if epic_cat is not None:
            # An epic is a task; without this every deliverable shows up as work.
            rows = [t for t in rows if int(t.get("category_id") or 0) != epic_cat]
        if group:
            keep = {str(m["task_id"]) for m in self._members(self._epic(group)["id"])}
            rows = [t for t in rows if str(t["id"]) in keep]
        items = [self._to_item(t) for t in rows]
        if stage:
            items = [i for i in items if (i.stage or "").lower() == stage.lower()]
        if label:
            items = [i for i in items if label.lower() in (lb.lower() for lb in i.labels)]
        return items

    def comment(self, item_id: str, text: str) -> None:
        self._ok("createComment", task_id=int(item_id), user_id=self._uid(), content=text)

    def comments(self, item_id: str) -> list[Comment]:
        rows = self._rpc("getAllComments", task_id=int(item_id)) or []
        out = [Comment(body=r.get("comment") or "",
                       author=r.get("username") or str(r.get("user_id") or ""),
                       created_at=_stamp(r.get("date_creation")))
               for r in rows]
        out.sort(key=lambda c: c.created_at)
        return out

    def set_stage(self, item_id: str, stage: str) -> None:
        col = int(self._col_by_name(stage)["id"])
        t = self._rpc("getTask", task_id=int(item_id))
        if not t:
            raise BatonError(f"item #{item_id} not found on {self.project_name}")
        # Moving a task to the column it is already in answers `false` — Kanboard
        # reports "nothing to do" the same way it reports failure. Without this,
        # `baton advance <id> --to <su propia etapa>` es un error, y una migración que
        # recorre todos los items se muere en el primero que ya estaba en su lugar.
        if int(t.get("column_id") or 0) == col:
            return
        # swimlane_id=0 is "the project's default swimlane"; position 1 is the top of
        # the column. Kanboard needs both — a move is a coordinate, not a column.
        self._ok("moveTaskPosition", project_id=self._proj(), task_id=int(item_id),
                 column_id=col, position=1, swimlane_id=0)

    def set_labels(self, item_id: str, add=None, remove=None) -> None:
        """Read, merge, write — because `setTaskTags` REPLACES the whole set.

        Measured, not assumed: writing `["type:bug"]` over `["type:bug", "area:cli"]`
        leaves only the first. Sending just the additions here would delete every label
        it was not told about, which is the kind of loss nobody notices until a filter
        stops matching.
        """
        tags = set(self._tags(item_id))
        tags |= set(add or [])
        tags -= set(remove or [])
        self._ok("setTaskTags", project_id=self._proj(), task_id=int(item_id),
                 tags=sorted(tags))

    def edit_body(self, item_id: str, body: str) -> None:
        self._ok("updateTask", id=int(item_id), description=body)

    def close(self, item_id: str, reason: str = "") -> None:
        """Kanboard closes a task natively, so nothing here has to pick a column.

        That is the whole fix for the bug this inherited: the Plane adapter chose "the
        first state in a closed group" and sent cancelled items to *Deployed*. A stage
        is never guessed by position — when a caller wants the item in a particular
        column too, that is an `advance` to a stage it named.
        """
        self._ok("closeTask", task_id=int(item_id))

    def set_priority(self, item_id: str, value: str) -> None:
        if value not in _PRIORITY:
            raise BatonError(f"unknown priority {value!r}; known: "
                             f"{', '.join(_PRIORITY)}")
        self._ok("updateTask", id=int(item_id), priority=_PRIORITY[value])


def _stamp(unix) -> str:
    """Kanboard timestamps are unix seconds; baton's vocabulary is ISO-8601."""
    from datetime import datetime, timezone
    if not unix:
        return ""
    return datetime.fromtimestamp(int(unix), timezone.utc).isoformat()


def _date(unix) -> str | None:
    """A due date, as YYYY-MM-DD. 0 is Kanboard's "unset", not 1970."""
    return _stamp(unix)[:10] or None


# What `registry.resolve('board', 'kanboard')` returns. The class name is free to
# change; this constant and the FILE NAME are the contract.
ADAPTER = KanboardBoard
