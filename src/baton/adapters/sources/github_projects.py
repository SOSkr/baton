"""GitHub Projects v2 — a migration SOURCE. Read-only, one way, one time.

Not a board backend: baton does not run a lifecycle here any more. Everything this
class can do is read an old board out — items, stages, and the comment trail — so
`baton export` can hand it to `baton-migrate`. There is deliberately no write path;
if you find yourself wanting one, the answer is that migration is one-way.

Discovery resolves the project node id and the Status field options by name, so no
project/field/option id is ever hardcoded.
"""
from __future__ import annotations

from ...base import BatonError, Comment, Item
from .._gh import gh, use_token


class GitHubProjectsSource:
    def __init__(self, repo: str, project: int | str | None = None,
                 token: str | None = None, owner: str | None = None,
                 status_field: str = "Status"):
        use_token(token)
        if not repo:
            raise BatonError("the GitHub Projects source needs a repo, 'OWNER/REPO'")
        self.repo = repo
        self.owner = owner or repo.split("/")[0]
        self.project_number = project
        self.status_field_name = status_field
        self._disco: dict | None = None

    # ---------- graphql helper ----------
    @staticmethod
    def _gql(query: str, *, s: dict | None = None, i: dict | None = None) -> dict:
        args = ["api", "graphql", "-f", f"query={query}"]
        for k, v in (s or {}).items():
            args += ["-f", f"{k}={v}"]
        for k, v in (i or {}).items():
            args += ["-F", f"{k}={v}"]
        return gh(*args, want_json=True)["data"]

    # ---------- discovery ----------
    def _discover(self) -> dict:
        if self._disco is not None:
            return self._disco
        if not self.project_number:
            raise BatonError("a ProjectV2 number is required to read board stages")
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
                self._disco = {
                    "project_id": proj["id"],
                    "option_names": [o["name"] for o in field.get("options", [])],
                    "owner_type": root,
                }
                return self._disco
            except BatonError as e:
                last_err = e
        raise BatonError(
            f"could not resolve project #{self.project_number} for owner {self.owner!r} "
            f"(tried user & organization). {last_err or ''}")

    def _stage_map(self) -> dict[int, str]:
        d = self._discover()
        root = d["owner_type"]
        # ponytail: first:100 — paginate if an old board ever exceeded it.
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
                out[c["number"]] = (n.get("fieldValueByName") or {}).get("name")
        return out

    # ---------- reads ----------
    def list_stages(self) -> list[str]:
        return list(self._discover()["option_names"])

    def get(self, item_id: str) -> Item:
        j = gh("issue", "view", item_id, "--repo", self.repo,
               "--json", "number,title,url,state,labels,body", want_json=True)
        stage = self._stage_map().get(int(item_id)) if self.project_number else None
        return Item(id=str(j["number"]), title=j["title"], url=j["url"],
                    stage=stage, state=j["state"].lower(),
                    labels=[l["name"] for l in j.get("labels", [])], body=j.get("body", ""))

    def list(self, *, stage=None, label=None, state="open") -> list[Item]:
        args = ["issue", "list", "--repo", self.repo, "--state", state, "--limit", "200",
                "--json", "number,title,url,state,labels,body"]
        if label:
            args += ["--label", label]
        rows = gh(*args, want_json=True)
        smap = self._stage_map() if self.project_number else {}
        items = []
        for j in rows:
            st = smap.get(j["number"])
            if stage and (st or "").lower() != stage.lower():
                continue
            items.append(Item(id=str(j["number"]), title=j["title"], url=j["url"],
                              stage=st, state=j["state"].lower(), body=j.get("body", ""),
                              labels=[l["name"] for l in j.get("labels", [])]))
        return items

    def comments(self, item_id: str) -> list[Comment]:
        j = gh("issue", "view", item_id, "--repo", self.repo,
               "--json", "comments", want_json=True) or {}
        return [Comment(body=(c.get("body") or "").strip(),
                        author=(c.get("author") or {}).get("login", ""),
                        created_at=c.get("createdAt") or "")
                for c in j.get("comments", [])]
