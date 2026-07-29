"""baton CLI — mechanical work-item ops over a board backend.

The generic primitives; skills (SKILL.md) compose them and add judgment.
Verbs: init · new · show · list · stages · advance · comment · close · labels · body · doctor.
Every verb runs as the `agent` credential unless `--as admin` says otherwise.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .adapters import get_adapter
from .adapters import get_repo, get_source
from .base import PRIORITIES, BatonError, Item
from .config import (BACKENDS, ROLES, find_config, github_token_env, load,
                     load_project, write_config)


def _emit(obj, as_json: bool):
    if as_json:
        print(json.dumps(obj, default=lambda o: o.__dict__, indent=2))
    else:
        if isinstance(obj, Item):
            print(f"#{obj.id} [{obj.stage or '-'}] {obj.title}\n  {obj.url}"
                  + (f"\n  priority: {obj.priority}" if obj.priority
                     and obj.priority != "none" else "")
                  + (f"\n  labels: {', '.join(obj.labels)}" if obj.labels else ""))
        elif isinstance(obj, list):
            for it in obj:
                print(f"#{it.id} [{it.stage or '-'}] {it.title}")
        else:
            print(obj)


def _flag_backward(ad, cfg, item_id, prev_stage, target_stage):
    """Flag an UNEXPECTED (backward) stage transition — e.g. Approved→Review — with
    `config.review_label`, so the user evaluates it. Normal forward moves (Review→
    Approved→In Progress→...) and creation are NOT flagged. Never fails the move."""
    if not cfg.review_label or not prev_stage:
        return
    try:
        order = [s.lower() for s in ad.list_stages()]
        p, t = prev_stage.lower(), target_stage.lower()
        if p in order and t in order and order.index(t) < order.index(p):
            ad.set_labels(item_id, add=[cfg.review_label])
    except BatonError:
        pass


def _require_verify(ad, cfg, item_id, prev_stage, target_stage):
    """Refuse a move that jumps OVER the verify stage.

    Opt-in: only when the project declares `stages.verify`. It gates the STAGE, not
    the work — nothing stops two `advance` calls in a row. What it buys is that
    skipping verification stops being an oversight nobody notices and becomes a
    deliberate move, recorded in the board's own history.
    """
    if "verify" not in cfg.stages or not prev_stage:
        return
    verify_stage = cfg.stages["verify"]
    try:
        order = [s.lower() for s in ad.list_stages()]
        v = order.index(verify_stage.lower())
        p, t = order.index(prev_stage.lower()), order.index(target_stage.lower())
    except (BatonError, ValueError):
        return          # unknown stage names — not our call to block on
    if p < v < t:
        raise BatonError(
            f"#{item_id}: {prev_stage} → {target_stage} skips {verify_stage!r}. "
            f"Run the baton-verify skill — it checks the diff against the acceptance "
            f"criteria and the scope boundary, and advances the item itself. To move "
            f"it without verifying, go through {verify_stage!r} explicitly.")


def cmd_new(a, ad, cfg):
    it = ad.create(a.title, a.body or "", a.label or [], priority=a.priority)
    if a.stage:
        ad.set_stage(it.id, a.stage)
        it.stage = a.stage
    _emit(it, a.json)


def cmd_show(a, ad, cfg):
    it = ad.get(a.id)
    if not a.comments:
        _emit(it, a.json)
        return
    cs = ad.comments(a.id)
    if a.json:
        _emit({"item": it, "comments": cs}, True)
        return
    _emit(it, False)
    if not cs:
        print("  (no comments)")
    for c in cs:
        head = " · ".join(p for p in (c.author, c.created_at) if p)
        print(f"\n  --- {head or 'comment'}")
        for line in c.body.splitlines():
            print(f"  {line}")


def cmd_list(a, ad, cfg):
    _emit(ad.list(stage=a.stage, label=a.label, state=a.state, group=a.group), a.json)


def cmd_groups(a, ad, cfg):
    """The roadmap: every epic, its target date, and how much of it is done. Read
    from the board every time, so there is nothing to keep up to date."""
    gs = ad.list_groups()
    if a.json:
        _emit(gs, True)
        return
    if not gs:
        print("(no epics yet — create one with the baton-roadmap skill)")
    for g in gs:
        pct = f"{round(100 * g.done / g.total)}%" if g.total else "—"
        print(f"{g.name}  [{g.done}/{g.total} {pct}]"
              + (f"  due {g.target_date}" if g.target_date else "  (no target date)"))


def cmd_group(a, ad, cfg):
    ad.set_group(a.id, a.to)
    _emit(f"#{a.id} → epic {a.to}", a.json)


def cmd_stages(a, ad, cfg):
    st = ad.list_stages()
    _emit(st if a.json else "\n".join(st) or "(no status field)", a.json)


def cmd_advance(a, ad, cfg):
    prev = ad.get(a.id).stage
    _require_verify(ad, cfg, a.id, prev, a.to)
    ad.set_stage(a.id, a.to)
    _flag_backward(ad, cfg, a.id, prev, a.to)
    _emit(f"#{a.id} → {a.to}", a.json)


_DEFAULT_STAGE = {"approve": "Approved", "start": "In Progress",
                  "verify": "Verify", "ship": "Deployed"}


def _verb_stage(cfg, verb: str) -> str:
    """Resolve a lifecycle verb to a board stage name (config alias or default)."""
    return cfg.stages.get(verb, _DEFAULT_STAGE[verb])


def _cmd_verb(verb: str):
    def fn(a, ad, cfg):
        st = _verb_stage(cfg, verb)
        prev = ad.get(a.id).stage
        _require_verify(ad, cfg, a.id, prev, st)
        ad.set_stage(a.id, st)
        _flag_backward(ad, cfg, a.id, prev, st)
        _emit(f"#{a.id} → {st}", a.json)
    return fn


def cmd_comment(a, ad, cfg):
    body = a.body if a.body is not None else sys.stdin.read()
    ad.comment(a.id, body)
    _emit(f"commented on #{a.id}", a.json)


def cmd_close(a, ad, cfg):
    if a.reason:
        ad.comment(a.id, a.reason)
    ad.close(a.id, a.reason or "")
    _emit(f"closed #{a.id}", a.json)


def cmd_priority(a, ad, cfg):
    ad.set_priority(a.id, a.to)
    _emit(f"#{a.id} priority → {a.to}", a.json)


def cmd_labels(a, ad, cfg):
    ad.set_labels(a.id, add=a.add or [], remove=a.remove or [])
    _emit(f"updated labels on #{a.id}", a.json)


def cmd_body(a, ad, cfg):
    body = a.body if a.body is not None else sys.stdin.read()
    ad.edit_body(a.id, body)
    _emit(f"updated body of #{a.id}", a.json)


def cmd_init(a, ad, cfg):
    """Write .baton/config.yaml for a board that ALREADY exists. Creating the repo
    and the board is `baton-bootstrap` (admin credential); this only records where
    they are, then proves discovery reaches them."""
    target = {k: v for k, v in (
        ("owner", a.owner), ("project", a.board),
        ("base_url", a.base_url), ("workspace", a.workspace),
    ) if v is not None}
    path = write_config(a.backend, target, repo=a.repo, force=a.force)
    print(f"wrote {path}")
    print("run `baton doctor` to verify discovery reaches the board.")
    return 0


def _probe(label: str, build) -> bool:
    """Run one real read-only call and report it. Never raises: doctor's job is to
    check EVERYTHING and then tell you what is broken — one that stops at the first
    failure hides the second one."""
    try:
        print(f"  {label}: OK — {build().probe()}")
        return True
    except BatonError as e:
        print(f"  {label}: FAILED — {e}")
        return False


def cmd_export(a, ad, cfg):
    """Read an old GitHub Projects board out to JSON, comments included, so the
    migration skill can move it onto the real board. Read-only.

    Which old board belongs to which project is PROJECT data, so it lives in that
    project's `.baton/config.yaml` under `migrate_from:` — the skills are installed
    globally and must not carry it. Flags override, for a one-off."""
    src_cfg = (cfg.migrate_from if cfg else {}) or {}
    repo = a.from_github or src_cfg.get("repo")
    project = a.project_number or src_cfg.get("project")
    if not repo:
        raise BatonError(
            "no source board. Either pass --from-github OWNER/REPO, or declare it in "
            "this project's .baton/config.yaml:\n"
            "  migrate_from: {repo: OWNER/REPO, project: 5}")
    src = get_source("github", repo=repo, project=project, owner=a.owner)
    items = src.list(state=a.state)
    out = {
        "source": {"repo": repo, "project": project},
        "stages": src.list_stages() if project else [],
        "items": [],
    }
    for it in items:
        d = dict(it.__dict__)
        # The trail is the point. An item without its comments is a title and a
        # guess — everything that explains WHY lives in the thread.
        d["comments"] = [c.__dict__ for c in src.comments(it.id)]
        out["items"].append(d)
    print(json.dumps(out, indent=2))
    n_comments = sum(len(i["comments"]) for i in out["items"])
    print(f"exported {len(items)} items and {n_comments} comments from {repo}",
          file=sys.stderr)
    return 0


def cmd_doctor(a, ad, cfg):
    print(f"baton {__version__}")
    print(f"config: {cfg.path}")
    print(f"backend: {cfg.backend}   board: {cfg.target}")
    if cfg.repos:
        print(f"repos: {', '.join(f'{k}={v}' for k, v in sorted(cfg.repos.items()))}")
    elif cfg.code_repo:
        print(f"code repo: {cfg.code_repo}")
    if cfg.migrate_from:
        print(f"migration source: {cfg.migrate_from}")

    ok = True
    saved = os.environ.get("GH_TOKEN")   # probing as admin must not leak into later ops
    try:
        for role in ROLES:
            var = cfg.token_env(role)
            if not os.environ.get(var):
                print(f"token[{role}] ${var}: NOT set — skipped")
                continue
            print(f"token[{role}] ${var}:")
            ok &= _probe(f"board ({cfg.backend})", lambda r=role: get_adapter(cfg, r))
            # git is a SECOND system on a SECOND credential — "the board answers"
            # says nothing about whether the agent can push. And a credential can
            # reach one repo of a multi-repo project and not the next, so check each.
            gh_var = github_token_env(role)
            for r in cfg.all_repos:
                if not os.environ.get(gh_var):
                    print(f"  code {r} ${gh_var}: NOT set — skipped")
                else:
                    ok &= _probe(f"code {r}", lambda x=r, ro=role: get_repo(x, ro))
    finally:
        if saved is None:
            os.environ.pop("GH_TOKEN", None)
        else:
            os.environ["GH_TOKEN"] = saved

    try:
        stages = ad.list_stages()
        print(f"stages: {', '.join(stages) or '(none)'}")
    except BatonError as e:
        print(f"stages FAILED: {e}")
        ok = False

    # Capabilities are CHECKED, not declared — a backend's edition or version can
    # turn a feature off, and finding that out here beats finding it out mid-verb.
    if "groups" in ad.capabilities():
        try:
            print(f"epics (native groups): {len(ad.list_groups())} on the board")
        except BatonError as e:
            print(f"epics (native groups): FAILED — {e}")
            ok = False
    if cfg.stages:
        print(f"verb aliases: {cfg.stages}")
    if cfg.memory:
        print(f"memory project: {cfg.memory}")
    if cfg.projects:
        print(f"sibling projects: {', '.join(sorted(cfg.projects))}")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="baton", description="Work-item lifecycle over a board.")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("-p", "--project", metavar="NAME|PATH",
                   help="operate on a sibling board instead of this one: a key of "
                        "`projects` in the config, or a path to its config/dir")
    p.add_argument("--as", dest="role", choices=list(ROLES), default="agent",
                   help="credential role: 'agent' (default — items, branches, PRs) or "
                        "'admin' (create/administer projects, merge). Each reads its own "
                        "env var; see `baton doctor`.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="write .baton/config.yaml for an existing board")
    s.add_argument("--backend", default=BACKENDS[0], choices=list(BACKENDS))
    s.add_argument("--repo", help="OWNER/REPO where the code lives")
    s.add_argument("--owner", help="reserved for backends that separate board owner")
    # `--board`, not `--project`: the global -p/--project already means "a sibling
    # board", and an argparse subparser would silently clobber it.
    s.add_argument("--board", help="github: ProjectV2 number · plane: project identifier")
    s.add_argument("--base-url", dest="base_url", help="plane: instance URL")
    s.add_argument("--workspace", help="plane: workspace slug")
    s.add_argument("--force", action="store_true", help="overwrite an existing config")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("new", help="create an item")
    s.add_argument("--title", required=True)
    s.add_argument("--body")
    s.add_argument("--label", action="append")
    s.add_argument("--priority", choices=list(PRIORITIES),
                   help="the board's NATIVE priority field — not a priority: label")
    s.add_argument("--stage", help="initial stage (else backend default)")
    s.set_defaults(fn=cmd_new)

    s = sub.add_parser("show", help="show an item")
    s.add_argument("id")
    s.add_argument("-c", "--comments", action="store_true",
                   help="include the comment trail (what other agents/people did)")
    s.set_defaults(fn=cmd_show)

    s = sub.add_parser("list", help="list items")
    s.add_argument("--stage")
    s.add_argument("--label")
    s.add_argument("--group", metavar="EPIC", help="only items in this epic")
    s.add_argument("--state", default="open", choices=["open", "closed", "all"])
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("stages", help="list the board's stages")
    s.set_defaults(fn=cmd_stages)

    s = sub.add_parser("groups", help="the roadmap: epics with target date and progress")
    s.set_defaults(fn=cmd_groups)

    s = sub.add_parser("group", help="put an item in an existing epic")
    s.add_argument("id")
    s.add_argument("--to", required=True, metavar="EPIC")
    s.set_defaults(fn=cmd_group)

    s = sub.add_parser("advance", help="move item to a stage (by name)")
    s.add_argument("id")
    s.add_argument("--to", required=True)
    s.set_defaults(fn=cmd_advance)

    for verb in ("approve", "start", "verify", "ship"):
        s = sub.add_parser(verb, help=f"advance item to the '{verb}' stage (config alias)")
        s.add_argument("id")
        s.set_defaults(fn=_cmd_verb(verb))

    s = sub.add_parser("comment", help="comment on an item (body or stdin)")
    s.add_argument("id")
    s.add_argument("--body")
    s.set_defaults(fn=cmd_comment)

    s = sub.add_parser("close", help="close an item (optional reason comment)")
    s.add_argument("id")
    s.add_argument("--reason")
    s.set_defaults(fn=cmd_close)

    s = sub.add_parser("priority", help="set the board's native priority field")
    s.add_argument("id")
    s.add_argument("--to", required=True, choices=list(PRIORITIES))
    s.set_defaults(fn=cmd_priority)

    s = sub.add_parser("labels", help="add/remove labels")
    s.add_argument("id")
    s.add_argument("--add", action="append")
    s.add_argument("--remove", action="append")
    s.set_defaults(fn=cmd_labels)

    s = sub.add_parser("body", help="replace item body (body or stdin)")
    s.add_argument("id")
    s.add_argument("--body")
    s.set_defaults(fn=cmd_body)

    s = sub.add_parser("export", help="read an old GitHub Projects board out to JSON "
                                      "(migration source — read-only)")
    s.add_argument("--from-github", dest="from_github", required=True, metavar="OWNER/REPO")
    s.add_argument("--project", dest="project_number", metavar="N",
                   help="ProjectV2 number — without it you get issues but no stages")
    s.add_argument("--owner", help="project owner login (default: repo owner)")
    s.add_argument("--state", default="all", choices=["open", "closed", "all"])
    s.set_defaults(fn=cmd_export)

    s = sub.add_parser("doctor", help="validate config + backend discovery")
    s.set_defaults(fn=cmd_doctor)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "init":               # runs WITHOUT a config — it writes one
            return args.fn(args, None, None) or 0
        if args.cmd == "export":             # config OPTIONAL: it holds `migrate_from`
            return args.fn(args, None, load() if find_config() else None) or 0
        cfg = load()
        if getattr(args, "project", None):
            cfg = load_project(args.project, cfg)
        ad = get_adapter(cfg, args.role)
        rc = args.fn(args, ad, cfg)
        return rc or 0
    except BatonError as e:
        print(f"baton: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
