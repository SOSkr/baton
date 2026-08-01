"""Plane adapter — direct REST calls (no CLI exists for Plane, unlike gh).

Discovery resolves the project UUID from its readable identifier, and caches
project states / labels (id<->name) so nothing is hardcoded.

Config (config.target):
  base_url:  "https://plane.example.com"   # instance URL, self-hosted or api.plane.so (required)
  workspace: "my-workspace"                # workspace slug (required)
  project:   "ENG"                         # project identifier, the "ENG" in ENG-123 (required)

Auth: PLANE_API_KEY env var — never in config.yaml.

Endpoint paths and field names verified against the official SDK source
(github.com/makeplane/plane-python-sdk, plane/api/*.py + plane/models/*.py) —
not scraped docs, which disagreed with each other on issues/ vs work-items/.
"""
from __future__ import annotations

import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from markdown_it import MarkdownIt

from ...base import BatonError, Comment, Group, Item
from .base import BoardBase

_TAG = re.compile(r"<[^>]+>")

# CommonMark plus tables — the verdict a triage posts IS a table. `linkify` is left off
# on purpose: it would drag in another dependency to autolink text nobody asked to link.
_MD = MarkdownIt("commonmark").enable("table")


def _strip_html(s: str) -> str:
    """Plane stores bodies and comments as HTML; baton's vocabulary is plain text.

    Used for BOTH, and for both it is the ONLY path here — not a fallback. The SDK
    models declare `description_stripped` and `comment_stripped`, but a live instance
    returns neither: not on the work-item list, not on its detail, not on comments. The
    `or` in `comments()` stays for backends that do send it; on this one it never fires.

    ponytail: regex, not a parser — what round-trips through here is text baton itself
    wrote and escaped on the way out, not arbitrary documents.
    """
    return html.unescape(_TAG.sub("", s.replace("</p>", "\n").replace("<br>", "\n")))


def _markdown_to_html(text: str) -> str:
    """A COMMENT on its way into Plane, rendered so the board reads like prose.

    Comments only. Bodies deliberately stay literal markdown, and the asymmetry is the
    point rather than an oversight:

    - a comment is append-only — nothing in baton ever rewrites one — so rendering it
      cannot compound;
    - a body is the CONTRACT. `baton-verify` grades it criterion by criterion and
      `baton body` rewrites it, so a lossy read would be baked back in on every edit:
      `## Acceptance criteria` returns as `Acceptance criteria`, `- [ ]` loses its
      bullet, and the next edit saves that.

    `html=False` (the default) is load-bearing: it escapes raw HTML while rendering, so
    `<id>` in a comment still travels as text. Converting with a library that passes
    HTML through would need escaping FIRST — and escaping turns `>` into `&gt;`, which
    would stop `> quoted` from being a quote. One pass, in the only order that works.
    """
    return _MD.render(text or "")


def _as_html(text: str) -> str:
    """A BODY on its way INTO Plane's HTML field. Escaped, never converted.

    Escaping is what stops the field eating content: `<id>` in a body reads as a tag
    and is dropped on save — silently, and it was, until an item documenting a CLI
    placeholder came back without it. Angle brackets are ordinary characters in the
    prose this tool carries (`<file>`, `List<T>`, `<mail@host>`), so they travel as
    text.

    What this does NOT do is turn markdown into HTML — headings and lists stay literal
    in Plane's web UI. That is deliberate and tracked separately: this change is about
    not losing what the author typed.
    """
    return html.escape(text or "")

# Plane's State.group values (plane/models/enums.py GroupEnum). "closed" for
# baton's open/closed Item.state means the board considers the work done or
# abandoned — completed and cancelled both qualify; triage/backlog/unstarted/
# started are all "open".
_CLOSED_GROUPS = {"completed", "cancelled"}


class PlaneBoard(BoardBase):
    def __init__(self, target: dict, token: str | None = None):
        self.base_url = (target.get("base_url") or "").rstrip("/")
        self.workspace = target.get("workspace")
        self.project_identifier = target.get("project")
        if not (self.base_url and self.workspace and self.project_identifier):
            raise BatonError(
                "plane adapter needs config.target.base_url, .workspace and .project")
        self.token = token or os.environ.get("PLANE_API_KEY")
        if not self.token:
            raise BatonError("PLANE_API_KEY env var required (never put it in config.yaml)")
        self._project_id: str | None = None
        self._states: list[dict] | None = None      # [{id, name, group}], board order
        self._labels: dict[str, str] | None = None  # name_lower -> id

    # ---------- HTTP helper ----------
    def _request(self, method: str, path: str, body: dict | None = None,
                  params: dict | None = None) -> dict:
        url = f"{self.base_url}/api/v1/workspaces/{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "X-Api-Key": self.token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                out = r.read()
                return json.loads(out) if out else {}
        except urllib.error.HTTPError as e:
            raise BatonError(f"plane {method} {path} failed: {e.code} {e.read().decode()[:300]}")
        except urllib.error.URLError as e:
            raise BatonError(f"plane {method} {path} unreachable: {e.reason}")

    def probe(self) -> str:
        """Listing the workspace's projects proves URL + API key + membership in one
        call, and tells us whether THIS key can see the configured project — a key
        scoped to another project fails here instead of three verbs later."""
        rows = self._request("GET", f"{self.workspace}/projects/").get("results", [])
        hit = next((p for p in rows
                    if (p.get("identifier") or "").lower() == self.project_identifier.lower()), None)
        if hit is None:
            raise BatonError(
                f"reached workspace {self.workspace!r} ({len(rows)} projects visible) "
                f"but {self.project_identifier!r} is not among them")
        return f"{self.workspace}/{hit.get('identifier')} — {hit.get('name', '?')}"

    # ---------- discovery ----------
    def _proj(self) -> str:
        if self._project_id is None:
            rows = self._request("GET", f"{self.workspace}/projects/").get("results", [])
            for p in rows:
                if (p.get("identifier") or "").lower() == self.project_identifier.lower():
                    self._project_id = p["id"]
                    break
            if self._project_id is None:
                raise BatonError(
                    f"project {self.project_identifier!r} not found in workspace {self.workspace!r}")
        return self._project_id

    def _discover_states(self) -> list[dict]:
        if self._states is None:
            rows = self._request("GET", f"{self.workspace}/projects/{self._proj()}/states/")
            self._states = sorted(rows.get("results", []), key=lambda s: s.get("sequence", 0))
        return self._states

    def _state_by_name(self, name: str) -> dict:
        for s in self._discover_states():
            if s["name"].lower() == name.lower():
                return s
        names = ", ".join(s["name"] for s in self._discover_states())
        raise BatonError(f"stage {name!r} not found. Board stages: {names or '(none)'}")

    def _discover_labels(self) -> dict:
        if self._labels is None:
            rows = self._request("GET", f"{self.workspace}/projects/{self._proj()}/labels/")
            self._labels = {lb["name"].lower(): lb["id"] for lb in rows.get("results", [])}
        return self._labels

    def _label_id(self, name: str) -> str:
        labels = self._discover_labels()
        lid = labels.get(name.lower())
        if lid is None:
            row = self._request("POST", f"{self.workspace}/projects/{self._proj()}/labels/",
                                 {"name": name})
            lid = row["id"]
            labels[name.lower()] = lid
        return lid

    def _issue_uuid(self, sequence_id: str) -> str:
        # ponytail: linear scan over one page of issues; fine at board scale
        # (same shape as the GitHub source's node lookup), revisit with a
        # `filters={"sequence_id": ...}` server-side lookup if boards grow
        # past a page.
        rows = self._request("GET", f"{self.workspace}/projects/{self._proj()}/work-items/",
                              params={"per_page": 100})
        for j in rows.get("results", []):
            if str(j.get("sequence_id")) == str(sequence_id):
                return j["id"]
        raise BatonError(f"issue {sequence_id!r} not found in project {self.project_identifier!r}")

    def _state_info(self, v) -> tuple[str | None, str | None]:
        # `state` is a bare UUID normally, but an expanded {id, name, group,
        # ...} object when the request used `expand=state` (get/list do).
        if isinstance(v, dict):
            return v.get("name"), v.get("group")
        s = {s["id"]: s for s in self._discover_states()}.get(v)
        return (s["name"], s.get("group")) if s else (None, None)

    def _label_name(self, v) -> str:
        # same dict-vs-bare-id split as _state_info, for `expand=labels`.
        if isinstance(v, dict):
            return v.get("name", v.get("id"))
        return {lid: name for name, lid in self._discover_labels().items()}.get(v, v)

    @staticmethod
    def _priority(v) -> str | None:
        # bare string on a plain GET, {"id": "none", ...} when the list endpoint
        # expands it — same dict-vs-scalar split as state and labels.
        if isinstance(v, dict):
            v = v.get("key") or v.get("id")
        return v or None

    def _to_item(self, j: dict) -> Item:
        stage, group = self._state_info(j.get("state"))
        return Item(
            priority=self._priority(j.get("priority")),
            id=str(j["sequence_id"]),
            title=j.get("name", ""),
            url=f"{self.base_url}/{self.workspace}/browse/{self.project_identifier}-{j['sequence_id']}/",
            stage=stage,
            state="closed" if group in _CLOSED_GROUPS else "open",
            labels=[self._label_name(lb) for lb in (j.get("labels") or [])],
            body=_strip_html(j.get("description_html") or ""),
        )

    # ---------- groups (Plane modules — "epics" in baton's skills) ----------
    def capabilities(self) -> set[str]:
        return {"groups", "priority"}

    def _modules(self) -> list[dict]:
        rows = self._request("GET", f"{self.workspace}/projects/{self._proj()}/modules/")
        return rows.get("results", []) if isinstance(rows, dict) else rows

    def _module_by_name(self, name: str) -> dict:
        mods = self._modules()
        for m in mods:
            if (m.get("name") or "").lower() == name.lower():
                return m
        names = ", ".join(m.get("name", "?") for m in mods)
        raise BatonError(
            f"epic {name!r} not found. Existing: {names or '(none)'}. "
            f"Epics are created deliberately — see the baton-roadmap skill.")

    def _group_item_uuids(self, name: str) -> set[str]:
        # ponytail: the module-issues payload is either link objects ({id, issue})
        # or the work items themselves — take whichever key carries the item uuid.
        mid = self._module_by_name(name)["id"]
        rows = self._request(
            "GET", f"{self.workspace}/projects/{self._proj()}/modules/{mid}/module-issues/")
        results = rows.get("results", []) if isinstance(rows, dict) else rows
        return {r.get("issue") or r.get("id") for r in results}

    def list_groups(self) -> list[Group]:
        return [Group(name=m.get("name", ""), id=m.get("id", ""),
                      target_date=m.get("target_date"),
                      total=m.get("total_issues") or 0,
                      done=m.get("completed_issues") or 0)
                for m in self._modules()]

    def create_group(self, name, *, target_date=None, description="") -> Group:
        body = {"name": name}
        if target_date:
            body["target_date"] = target_date
        if description:
            body["description"] = description
        m = self._request("POST", f"{self.workspace}/projects/{self._proj()}/modules/", body)
        return Group(name=m.get("name", name), id=m.get("id", ""),
                     target_date=m.get("target_date"))

    def set_group(self, item_id: str, name: str) -> None:
        mid = self._module_by_name(name)["id"]
        self._request(
            "POST", f"{self.workspace}/projects/{self._proj()}/modules/{mid}/module-issues/",
            {"issues": [self._issue_uuid(item_id)]})

    # ---------- Adapter API ----------
    # ---------- creation (bootstrap) ----------
    def find_project(self) -> dict | None:
        """Same lookup as `_proj()` but answering None instead of raising: bootstrap
        asks in order to decide, not in order to fail."""
        rows = self._request("GET", f"{self.workspace}/projects/").get("results", [])
        for p in rows:
            if (p.get("identifier") or "").lower() == self.project_identifier.lower():
                self._project_id = p["id"]
                return {"id": p["id"], "identifier": p.get("identifier"),
                        "name": p.get("name", "")}
        return None

    def create_project(self, name: str) -> dict:
        """`identifier` is not optional for Plane and not ours to invent: it is the
        prefix in ENG-123, it comes from `config.target.project`, and it is what every
        later lookup resolves by."""
        row = self._request("POST", f"{self.workspace}/projects/",
                            {"name": name, "identifier": self.project_identifier})
        self._project_id = row.get("id")
        self._states = None                  # a fresh project ships its own states
        return {"id": row.get("id"), "identifier": row.get("identifier"),
                "name": row.get("name", name)}

    def stage_groups(self) -> dict[str, str]:
        return {s["name"]: (s.get("group") or "") for s in self._discover_states()}

    def create_stage(self, name: str, *, group: str, color: str) -> None:
        """Plane assigns its own `sequence` here and ignores one sent with the create —
        verified against a live instance, where the field is writable in the SDK model
        either way. Ordering is therefore a separate call; see `set_stage_position`."""
        self._request("POST", f"{self.workspace}/projects/{self._proj()}/states/",
                      {"name": name, "color": color, "group": group})
        self._states = None                  # order and ids changed

    def set_stage_position(self, name: str, position: int) -> None:
        """Plane orders states by `sequence`, and its own sit at 15000, 25000, ... The
        step matches so that a column this project does not manage keeps a sane place
        between the ones it does."""
        self._patch_state(self._state_by_name(name)["id"],
                          {"sequence": (position + 1) * 10000})
        self._states = None

    def default_stage(self) -> str | None:
        return next((s["name"] for s in self._discover_states() if s.get("default")), None)

    def set_default_stage(self, name: str) -> None:
        """Two calls, because Plane does NOT clear the old default when a new one is
        set — it just ends up with two, and then picks. Verified against a live
        instance; and the order matters: clearing first would leave the project with
        none if the second call failed.

        Clearing it is also what makes the old default deletable: Plane refuses to
        remove a state while it holds the flag ("Default state cannot be deleted"),
        which is why `--prune` could not touch Backlog before this existed.
        """
        want = self._state_by_name(name)
        for state in list(self._discover_states()):
            if state["id"] == want["id"]:
                continue
            if state.get("default"):
                self._patch_state(state["id"], {"default": False})
        self._patch_state(want["id"], {"default": True})
        self._states = None

    def _patch_state(self, state_id: str, body: dict) -> dict:
        return self._request(
            "PATCH", f"{self.workspace}/projects/{self._proj()}/states/{state_id}/", body)

    def delete_stage(self, name: str) -> None:
        """The trailing slash is not style: without it Plane answers 301, and urllib
        does not follow a redirect on DELETE — so the call reports failure while the
        stage is still there. Every path in this file ends in one for that reason."""
        sid = self._state_by_name(name)["id"]
        self._request("DELETE", f"{self.workspace}/projects/{self._proj()}/states/{sid}/")
        self._states = None

    def list_stages(self) -> list[str]:
        return [s["name"] for s in self._discover_states()]

    def create(self, title: str, body: str, labels: list[str],
               priority: str | None = None) -> Item:
        label_ids = [self._label_id(lb) for lb in labels]
        payload = {"name": title, "description_html": _as_html(body) or "<p></p>",
                   "labels": label_ids}
        if priority:
            payload["priority"] = priority
        j = self._request("POST", f"{self.workspace}/projects/{self._proj()}/work-items/",
                           payload)
        j.setdefault("labels", label_ids)
        return self._to_item(j)

    def set_priority(self, item_id: str, value: str) -> None:
        uuid = self._issue_uuid(item_id)
        self._request("PATCH",
                       f"{self.workspace}/projects/{self._proj()}/work-items/{uuid}/",
                       {"priority": value})

    def get(self, item_id: str) -> Item:
        uuid = self._issue_uuid(item_id)
        j = self._request("GET", f"{self.workspace}/projects/{self._proj()}/work-items/{uuid}/",
                           params={"expand": "labels,state"})
        return self._to_item(j)

    def list(self, *, stage=None, label=None, state="open", group=None) -> list[Item]:
        rows = self._request("GET", f"{self.workspace}/projects/{self._proj()}/work-items/",
                              params={"expand": "labels,state", "per_page": 100})
        raw = rows.get("results", [])
        if group:
            keep = self._group_item_uuids(group)
            raw = [j for j in raw if j.get("id") in keep]
        items = [self._to_item(j) for j in raw]
        if stage:
            items = [i for i in items if (i.stage or "").lower() == stage.lower()]
        if label:
            items = [i for i in items if label.lower() in (lb.lower() for lb in i.labels)]
        if state != "all":
            items = [i for i in items if i.state == state]
        return items

    def comment(self, item_id: str, text: str) -> None:
        uuid = self._issue_uuid(item_id)
        # Escaped for the same reason a body is: `comment_html` is an HTML field, so
        # anything shaped like a tag is read as one and dropped on save. The comment
        # thread is what `baton-catch-up` and the next agent read — and agents write
        # `<id>`, `<file>`, `List<T>` constantly, so this was corrupting the project's
        # own trail one comment at a time.
        self._request("POST",
                       f"{self.workspace}/projects/{self._proj()}/work-items/{uuid}/comments/",
                       {"comment_html": _markdown_to_html(text)})

    def comments(self, item_id: str) -> list[Comment]:
        uuid = self._issue_uuid(item_id)
        j = self._request("GET",
                           f"{self.workspace}/projects/{self._proj()}/work-items/{uuid}/comments/",
                           params={"per_page": 100})
        rows = j.get("results", []) if isinstance(j, dict) else (j or [])
        out = [Comment(body=(r.get("comment_stripped")
                             or _strip_html(r.get("comment_html") or "")).strip(),
                       author=str(r.get("actor") or ""),
                       created_at=r.get("created_at") or "")
               for r in rows]
        out.sort(key=lambda c: c.created_at)
        return out

    def set_stage(self, item_id: str, stage: str) -> None:
        st = self._state_by_name(stage)
        uuid = self._issue_uuid(item_id)
        self._request("PATCH", f"{self.workspace}/projects/{self._proj()}/work-items/{uuid}/",
                       {"state": st["id"]})

    def set_labels(self, item_id: str, add: list[str] | None = None,
                   remove: list[str] | None = None) -> None:
        uuid = self._issue_uuid(item_id)
        j = self._request("GET", f"{self.workspace}/projects/{self._proj()}/work-items/{uuid}/")
        current = set(j.get("labels") or [])
        current |= {self._label_id(lb) for lb in (add or [])}
        current -= {self._label_id(lb) for lb in (remove or [])}
        self._request("PATCH", f"{self.workspace}/projects/{self._proj()}/work-items/{uuid}/",
                       {"labels": list(current)})

    def edit_body(self, item_id: str, body: str) -> None:
        uuid = self._issue_uuid(item_id)
        self._request("PATCH", f"{self.workspace}/projects/{self._proj()}/work-items/{uuid}/",
                       {"description_html": _as_html(body)})

    def close(self, item_id: str, reason: str = "") -> None:
        cancelled = next((s for s in self._discover_states() if s.get("group") in _CLOSED_GROUPS),
                         None)
        if cancelled is None:
            raise BatonError("no completed/cancelled state found on this project's board")
        self.set_stage(item_id, cancelled["name"])


# What `registry.resolve('board', 'plane')` returns. The class name is free to
# change; this constant and the FILE NAME are the contract.
ADAPTER = PlaneBoard
