"""GitHub Projects v2 adapter — shells to the authenticated `gh` CLI.

Discovery resolves the project node id, the Status single-select field id, and
its options (name->id) so nothing is hardcoded.

Config (config.target):
  repo:    "OWNER/REPO"        # where issues live (required)
  owner:   "OWNER"            # project owner login; defaults to repo owner
  project: 5                  # ProjectV2 number (required for stage ops)
  status_field: "Status"      # single-select field name (default "Status")
"""
from __future__ import annotations

import json
import subprocess

from ..base import Adapter, BatonError, Item


def _gh(*args: str, want_json: bool = False):
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise BatonError(f"gh {' '.join(args[:2])} failed: {r.stderr.strip() or r.stdout.strip()}")
    out = r.stdout.strip()
    return json.loads(out) if want_json and out else out


class GitHubAdapter(Adapter):
    def __init__(self, target: dict):
        self.repo = target.get("repo")
        if not self.repo:
            raise BatonError("github adapter needs config.target.repo = 'OWNER/REPO'")
        self.owner = target.get("owner") or self.repo.split("/")[0]
        self.project_number = target.get("project")
        self.status_field_name = target.get("status_field", "Status")
        self._disco: dict | None = None   # {project_id, field_id, options:{name_lower:id}, owner_type}

    # ---------- graphql helper ----------
    @staticmethod
    def _gql(query: str, *, s: dict | None = None, i: dict | None = None) -> dict:
        args = ["api", "graphql", "-f", f"query={query}"]
        for k, v in (s or {}).items():
            args += ["-f", f"{k}={v}"]
        for k, v in (i or {}).items():
            args += ["-F", f"{k}={v}"]
        return _gh(*args, want_json=True)["data"]

    # ---------- discovery ----------
    def _discover(self) -> dict:
        if self._disco is not None:
            return self._disco
        if not self.project_number:
            raise BatonError("config.target.project (ProjectV2 number) required for board ops")
        q = """
        query($owner:String!,$number:Int!){
          %(root)s(login:$owner){
            projectV2(number:$number){
              id
              field(name:"%(field)s"){
                ... on ProjectV2SingleSelectField { id name options { id name } }
              }
            }
          }
        }"""
        last_err = None
        for root in ("user", "organization"):
            try:
                data = self._gql(q % {"root": root, "field": self.status_field_name},
                                 s={"owner": self.owner}, i={"number": self.project_number})
                proj = data.get(root, {}).get("projectV2")
                if not proj:
                    continue
                field = proj.get("field") or {}
                opts = {o["name"].lower(): o["id"] for o in field.get("options", [])}
                self._disco = {
                    "project_id": proj["id"],
                    "field_id": field.get("id"),
                    "options": opts,
                    "option_names": [o["name"] for o in field.get("options", [])],
                    "owner_type": root,
                }
                return self._disco
            except BatonError as e:
                last_err = e
        raise BatonError(
            f"could not resolve project #{self.project_number} for owner {self.owner!r} "
            f"(tried user & organization). {last_err or ''}")

    def _item_node_id(self, number: str) -> str:
        """ProjectV2 item id for issue `number`."""
        d = self._discover()
        root = d["owner_type"]
        # ponytail: first:100 — paginate if a project ever exceeds it.
        q = """
        query($owner:String!,$number:Int!){
          %(root)s(login:$owner){ projectV2(number:$number){ items(first:100){
            nodes{ id content{ ... on Issue { number } } } } } } }""" % {"root": root}
        data = self._gql(q, s={"owner": self.owner}, i={"number": self.project_number})
        for n in data[root]["projectV2"]["items"]["nodes"]:
            c = n.get("content") or {}
            if c.get("number") == int(number):
                return n["id"]
        raise BatonError(f"issue #{number} is not on project #{self.project_number}")

    def _stage_map(self) -> dict[int, str]:
        d = self._discover()
        root = d["owner_type"]
        q = """
        query($owner:String!,$number:Int!){
          %(root)s(login:$owner){ projectV2(number:$number){ items(first:100){
            nodes{ content{ ... on Issue { number } }
                   fieldValueByName(name:"%(field)s"){
                     ... on ProjectV2ItemFieldSingleSelectValue { name } } } } } } }""" % {
            "root": root, "field": self.status_field_name}
        data = self._gql(q, s={"owner": self.owner}, i={"number": self.project_number})
        out = {}
        for n in data[root]["projectV2"]["items"]["nodes"]:
            c = n.get("content") or {}
            if c.get("number") is not None:
                fv = n.get("fieldValueByName") or {}
                out[c["number"]] = fv.get("name")
        return out

    # ---------- Adapter API ----------
    def list_stages(self) -> list[str]:
        return list(self._discover()["option_names"])

    def create(self, title: str, body: str, labels: list[str]) -> Item:
        args = ["issue", "create", "--repo", self.repo, "--title", title, "--body", body]
        if labels:
            args += ["--label", ",".join(labels)]
        url = _gh(*args).splitlines()[-1].strip()
        number = url.rstrip("/").split("/")[-1]
        return Item(id=number, title=title, url=url, labels=list(labels), body=body)

    def get(self, item_id: str) -> Item:
        j = _gh("issue", "view", item_id, "--repo", self.repo,
                "--json", "number,title,url,state,labels,body", want_json=True)
        stage = self._stage_map().get(int(item_id)) if self.project_number else None
        return Item(id=str(j["number"]), title=j["title"], url=j["url"],
                    stage=stage, state=j["state"].lower(),
                    labels=[l["name"] for l in j.get("labels", [])], body=j.get("body", ""))

    def list(self, *, stage=None, label=None, state="open") -> list[Item]:
        args = ["issue", "list", "--repo", self.repo, "--state", state, "--limit", "200",
                "--json", "number,title,url,state,labels"]
        if label:
            args += ["--label", label]
        rows = _gh(*args, want_json=True)
        smap = self._stage_map() if (self.project_number and (stage or True)) else {}
        items = []
        for j in rows:
            st = smap.get(j["number"])
            if stage and (st or "").lower() != stage.lower():
                continue
            items.append(Item(id=str(j["number"]), title=j["title"], url=j["url"],
                              stage=st, state=j["state"].lower(),
                              labels=[l["name"] for l in j.get("labels", [])]))
        return items

    def comment(self, item_id: str, text: str) -> None:
        _gh("issue", "comment", item_id, "--repo", self.repo, "--body", text)

    def set_stage(self, item_id: str, stage: str) -> None:
        d = self._discover()
        opt = d["options"].get(stage.lower())
        if opt is None:
            raise BatonError(
                f"stage {stage!r} not found. Board stages: {', '.join(d['option_names']) or '(none)'}")
        item_node = self._item_node_id(item_id)
        mut = """mutation($p:ID!,$i:ID!,$f:ID!,$o:String!){
          updateProjectV2ItemFieldValue(input:{projectId:$p,itemId:$i,fieldId:$f,
            value:{singleSelectOptionId:$o}}){ projectV2Item{ id } } }"""
        self._gql(mut, s={"p": d["project_id"], "i": item_node, "f": d["field_id"], "o": opt})

    def set_labels(self, item_id, add=None, remove=None) -> None:
        args = ["issue", "edit", item_id, "--repo", self.repo]
        for l in (add or []):
            args += ["--add-label", l]
        for l in (remove or []):
            args += ["--remove-label", l]
        if len(args) > 5:
            _gh(*args)

    def edit_body(self, item_id: str, body: str) -> None:
        _gh("issue", "edit", item_id, "--repo", self.repo, "--body", body)

    def close(self, item_id: str, reason: str = "") -> None:
        _gh("issue", "close", item_id, "--repo", self.repo, "--reason", "not planned")
