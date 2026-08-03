"""Plane as a migration SOURCE — read once, on the way off it.

Exists because baton is leaving Plane for Kanboard (BATON-17, and the measurements
in `docs/design/board-backends.md`). **Delete this file once the migration is done**;
that is what the whole `read/` family is for.

It does NOT reuse `adapters/board/plane.py`, and the duplication is the point. A
source that inherited from the board would inherit `create`, `close`, `set_stage` and
every other write with them, and "this one cannot write" would go back to being a
promise instead of a fact you can check by opening the file.

Config (`migrate_from` in .baton/config.yaml):
  migrate_from: {kind: plane, base_url: "https://plane.example.com",
                 workspace: my-workspace, project: BATON}

Auth: PLANE_API_KEY — the same credential the board adapter used, since this reads
the board that is being left behind.
"""
from __future__ import annotations

import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from ...base import BatonError, Comment, Item, user_agent
from .base import ReadBase

_TAG = re.compile(r"<[^>]+>")

# Plane's own closed groups. An item's open/closed is read off its state's group.
_CLOSED_GROUPS = {"completed", "cancelled"}


def _strip_html(s: str) -> str:
    """Plane keeps bodies and comments as HTML; everything downstream wants text.

    The same regex as the board adapter, on purpose and not by accident: this reads
    exactly what that one wrote, so stripping it any differently would mean the
    migration disagreed with the tool that produced the data.
    """
    return html.unescape(_TAG.sub("", s.replace("</p>", "\n").replace("<br>", "\n")))


class PlaneRead(ReadBase):
    def __init__(self, base_url: str | None = None, workspace: str | None = None,
                 project: str | None = None, token: str | None = None, **_ignored):
        self.base_url = (base_url or "").rstrip("/")
        self.workspace = workspace
        self.project_identifier = project
        if not (self.base_url and self.workspace and self.project_identifier):
            raise BatonError(
                "plane source needs base_url, workspace and project — declare them "
                "under migrate_from: in .baton/config.yaml")
        self.token = token or os.environ.get("MIGRATION_TOKEN")
        if not self.token:
            raise BatonError(
                "$MIGRATION_TOKEN required to read the old board. It is its own "
                "variable because a migration has TWO boards at once — the source and "
                "the destination — and moving between two instances of the same "
                "provider would otherwise need one name for both.")
        self._project_id: str | None = None
        self._states: list[dict] | None = None

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.base_url}/api/v1/workspaces/{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"X-Api-Key": self.token,
                                                   "User-Agent": user_agent()})
        try:
            with urllib.request.urlopen(req) as r:
                out = r.read()
                return json.loads(out) if out else {}
        except urllib.error.HTTPError as e:
            raise BatonError(f"plane GET {path} failed: {e.code} {e.read().decode()[:200]}")
        except urllib.error.URLError as e:
            raise BatonError(f"plane GET {path} unreachable: {e.reason}")

    def _proj(self) -> str:
        if self._project_id is None:
            rows = self._get(f"{self.workspace}/projects/").get("results", [])
            for p in rows:
                if (p.get("identifier") or "").lower() == self.project_identifier.lower():
                    self._project_id = p["id"]
                    break
            if self._project_id is None:
                raise BatonError(f"project {self.project_identifier!r} not found in "
                                 f"workspace {self.workspace!r}")
        return self._project_id

    def _state_rows(self) -> list[dict]:
        if self._states is None:
            rows = self._get(f"{self.workspace}/projects/{self._proj()}/states/")
            self._states = sorted(rows.get("results", []),
                                  key=lambda s: s.get("sequence", 0))
        return self._states

    def list_stages(self) -> list[str]:
        return [s["name"] for s in self._state_rows()]

    def _to_item(self, j: dict) -> Item:
        st = j.get("state")
        if isinstance(st, dict):
            name, group = st.get("name"), st.get("group")
        else:
            row = {s["id"]: s for s in self._state_rows()}.get(st) or {}
            name, group = row.get("name"), row.get("group")
        labels = []
        for lb in j.get("labels") or []:
            labels.append(lb.get("name", lb.get("id")) if isinstance(lb, dict) else lb)
        pri = j.get("priority")
        if isinstance(pri, dict):
            pri = pri.get("key") or pri.get("id")
        return Item(
            id=str(j["sequence_id"]),
            title=j.get("name", ""),
            url=f"{self.base_url}/{self.workspace}/browse/"
                f"{self.project_identifier}-{j['sequence_id']}/",
            stage=name,
            state="closed" if group in _CLOSED_GROUPS else "open",
            labels=labels,
            body=_strip_html(j.get("description_html") or ""),
            priority=pri or None,
        )

    def _rows(self) -> list[dict]:
        return self._get(f"{self.workspace}/projects/{self._proj()}/work-items/",
                         params={"expand": "labels,state", "per_page": 100}
                         ).get("results", [])

    def get(self, item_id: str) -> Item:
        for j in self._rows():
            if str(j.get("sequence_id")) == str(item_id):
                return self._to_item(j)
        raise BatonError(f"item {item_id!r} not found on the source board")

    def list(self, *, stage=None, label=None, state="open") -> list[Item]:
        items = [self._to_item(j) for j in self._rows()]
        if stage:
            items = [i for i in items if (i.stage or "").lower() == stage.lower()]
        if label:
            items = [i for i in items if label.lower() in (lb.lower() for lb in i.labels)]
        if state != "all":
            items = [i for i in items if i.state == state]
        # Oldest first, so a migration replays the board in the order it happened.
        items.sort(key=lambda i: int(i.id))
        return items

    def comments(self, item_id: str) -> list[Comment]:
        uuid = next((j["id"] for j in self._rows()
                     if str(j.get("sequence_id")) == str(item_id)), None)
        if uuid is None:
            raise BatonError(f"item {item_id!r} not found on the source board")
        j = self._get(
            f"{self.workspace}/projects/{self._proj()}/work-items/{uuid}/comments/",
            params={"per_page": 100})
        rows = j.get("results", []) if isinstance(j, dict) else (j or [])
        out = [Comment(body=(r.get("comment_stripped")
                             or _strip_html(r.get("comment_html") or "")).strip(),
                       author=str(r.get("actor") or ""),
                       created_at=r.get("created_at") or "")
               for r in rows]
        # Plane returns newest FIRST. Read straight through, a migration would replay
        # every thread backwards — and it did, once, in a verification script that
        # then reported the wrong answer.
        out.sort(key=lambda c: c.created_at)
        return out


ADAPTER = PlaneRead
