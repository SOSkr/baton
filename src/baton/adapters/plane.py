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

from ..base import Adapter, BatonError, Comment, Item

_TAG = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    """Plane stores comments as HTML. Only used as a fallback when the API
    doesn't return `comment_stripped`. ponytail: regex, not a parser — these
    are agent-written comments, not arbitrary documents."""
    return html.unescape(_TAG.sub("", s.replace("</p>", "\n").replace("<br>", "\n")))

# Plane's State.group values (plane/models/enums.py GroupEnum). "closed" for
# baton's open/closed Item.state means the board considers the work done or
# abandoned — completed and cancelled both qualify; triage/backlog/unstarted/
# started are all "open".
_CLOSED_GROUPS = {"completed", "cancelled"}


class PlaneAdapter(Adapter):
    def __init__(self, target: dict):
        self.base_url = (target.get("base_url") or "").rstrip("/")
        self.workspace = target.get("workspace")
        self.project_identifier = target.get("project")
        if not (self.base_url and self.workspace and self.project_identifier):
            raise BatonError(
                "plane adapter needs config.target.base_url, .workspace and .project")
        self.token = os.environ.get("PLANE_API_KEY")
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
            self._labels = {l["name"].lower(): l["id"] for l in rows.get("results", [])}
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
        # (matches github.py's _item_node_id precedent), revisit with a
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

    def _to_item(self, j: dict) -> Item:
        stage, group = self._state_info(j.get("state"))
        return Item(
            id=str(j["sequence_id"]),
            title=j.get("name", ""),
            url=f"{self.base_url}/{self.workspace}/browse/{self.project_identifier}-{j['sequence_id']}/",
            stage=stage,
            state="closed" if group in _CLOSED_GROUPS else "open",
            labels=[self._label_name(l) for l in (j.get("labels") or [])],
            body=j.get("description_html", ""),
        )

    # ---------- Adapter API ----------
    def list_stages(self) -> list[str]:
        return [s["name"] for s in self._discover_states()]

    def create(self, title: str, body: str, labels: list[str]) -> Item:
        label_ids = [self._label_id(l) for l in labels]
        j = self._request("POST", f"{self.workspace}/projects/{self._proj()}/work-items/",
                           {"name": title, "description_html": body or "<p></p>",
                            "labels": label_ids})
        j.setdefault("labels", label_ids)
        return self._to_item(j)

    def get(self, item_id: str) -> Item:
        uuid = self._issue_uuid(item_id)
        j = self._request("GET", f"{self.workspace}/projects/{self._proj()}/work-items/{uuid}/",
                           params={"expand": "labels,state"})
        return self._to_item(j)

    def list(self, *, stage=None, label=None, state="open") -> list[Item]:
        rows = self._request("GET", f"{self.workspace}/projects/{self._proj()}/work-items/",
                              params={"expand": "labels,state", "per_page": 100})
        items = [self._to_item(j) for j in rows.get("results", [])]
        if stage:
            items = [i for i in items if (i.stage or "").lower() == stage.lower()]
        if label:
            items = [i for i in items if label.lower() in (l.lower() for l in i.labels)]
        if state != "all":
            items = [i for i in items if i.state == state]
        return items

    def comment(self, item_id: str, text: str) -> None:
        uuid = self._issue_uuid(item_id)
        self._request("POST",
                       f"{self.workspace}/projects/{self._proj()}/work-items/{uuid}/comments/",
                       {"comment_html": f"<p>{text}</p>"})

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
        current |= {self._label_id(l) for l in (add or [])}
        current -= {self._label_id(l) for l in (remove or [])}
        self._request("PATCH", f"{self.workspace}/projects/{self._proj()}/work-items/{uuid}/",
                       {"labels": list(current)})

    def edit_body(self, item_id: str, body: str) -> None:
        uuid = self._issue_uuid(item_id)
        self._request("PATCH", f"{self.workspace}/projects/{self._proj()}/work-items/{uuid}/",
                       {"description_html": body})

    def close(self, item_id: str, reason: str = "") -> None:
        cancelled = next((s for s in self._discover_states() if s.get("group") in _CLOSED_GROUPS),
                         None)
        if cancelled is None:
            raise BatonError("no completed/cancelled state found on this project's board")
        self.set_stage(item_id, cancelled["name"])
