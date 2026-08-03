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

from pathlib import Path

from . import __version__, version
from .adapters import board as _board
from .adapters import repo as _repo
from .base import PRIORITIES, BatonError, Item
from .config import (BACKENDS, DEFAULT_GIT, Config,
                     credential_sources, find_config, load, load_project,
                     write_config)
from .core import DEFAULT_STAGES, Baton


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


def cmd_new(a, b, cfg):
    # Before anything is written: an item that cannot say where its work goes is an
    # item someone will have to fix on the board, and by then it has an id people
    # already wrote down.
    _board.require_repo(cfg, a.label or [])
    it = b.board.create(a.title, a.body or "", a.label or [], priority=a.priority)
    stage = b.stage(a.stage)
    if stage:
        b.board.set_stage(it.id, stage)
        it.stage = stage
    _emit(it, a.json)


def cmd_show(a, b, cfg):
    it = b.item(a.id)
    if a.json:
        _emit({"item": it, "comments": b.board.comments(a.id)} if a.comments else it, True)
        return

    _emit(it, False)
    # The body IS the item: the user story, the acceptance criteria, the scope. Leaving
    # it out made `baton show` unable to answer the one question `baton-verify` opens
    # with — "what did this item say it would do" — and sent every reader to `--json`.
    # `list` stays one line per item on purpose; this is the single-item view.
    if it.body:
        print()
        for line in it.body.strip().splitlines():
            print(f"  {line}")
    if not a.comments:
        return
    cs = b.board.comments(a.id)
    if not cs:
        print("  (no comments)")
    for c in cs:
        head = " · ".join(p for p in (c.author, c.created_at) if p)
        print(f"\n  --- {head or 'comment'}")
        for line in c.body.splitlines():
            print(f"  {line}")


def cmd_list(a, b, cfg):
    _emit(b.board.list(stage=b.stage(a.stage), label=a.label, state=a.state, group=a.group), a.json)


def cmd_groups(a, b, cfg):
    """The roadmap: every epic, its target date, and how much of it is done. Read
    from the board every time, so there is nothing to keep up to date."""
    # NOT `b.board.list_groups()`: those counts are each backend's own idea of done,
    # and abandoned work is not progress. `b.groups()` applies that rule once, for
    # every provider — see `adapters/board/__init__.py`.
    gs = b.groups()
    if a.json:
        _emit(gs, True)
        return
    if not gs:
        print("(no epics yet — create one with the baton-roadmap skill)")
    for g in gs:
        pct = f"{round(100 * g.done / g.total)}%" if g.total else "—"
        print(f"{g.name}  [{g.done}/{g.total} {pct}]"
              + (f"  due {g.target_date}" if g.target_date else "  (no target date)"))


def cmd_group(a, b, cfg):
    b.set_group(a.id, a.to)
    _emit(f"#{a.id} → epic {a.to}", a.json)


def cmd_stages(a, b, cfg):
    st = b.board.list_stages()
    _emit(st if a.json else "\n".join(st) or "(no status field)", a.json)


def cmd_advance(a, b, cfg):
    _emit(f"#{a.id} → {b.advance(a.id, b.stage(a.to))}", a.json)


def _cmd_verb(verb: str):
    def fn(a, b, cfg):
        _emit(f"#{a.id} → {b.advance_verb(verb, a.id)}", a.json)
    return fn


def cmd_comment(a, b, cfg):
    body = a.body if a.body is not None else sys.stdin.read()
    b.comment(a.id, body)
    _emit(f"commented on #{a.id}", a.json)


def cmd_close(a, b, cfg):
    if a.reason:
        b.comment(a.id, a.reason)
    b.close(a.id, a.reason or "")
    _emit(f"closed #{a.id}", a.json)


def cmd_priority(a, b, cfg):
    b.set_priority(a.id, a.to)
    _emit(f"#{a.id} priority → {a.to}", a.json)


def cmd_labels(a, b, cfg):
    b.set_labels(a.id, add=a.add or [], remove=a.remove or [])
    _emit(f"updated labels on #{a.id}", a.json)


def cmd_body(a, b, cfg):
    body = a.body if a.body is not None else sys.stdin.read()
    b.edit_body(a.id, body)
    _emit(f"updated body of #{a.id}", a.json)


def _bootstrap_config(a):
    """The config bootstrap will work from: this project's, with the flags on top.

    Reading the existing config first is what makes a bare re-run work — after a
    half-failed run every name is already on disk, so `baton bootstrap` with no flags
    is the resume command.
    """
    cur = load() if find_config() else None
    target = dict(cur.target if cur else {})
    for key, val in (("owner", a.owner), ("project", a.board),
                     ("base_url", a.base_url), ("workspace", a.workspace)):
        if val is not None:
            target[key] = val
    git = dict(cur.git if cur else DEFAULT_GIT)
    for key, val in (("integration", a.integration), ("production", a.production)):
        if val:
            git[key] = val
    return {
        "board": a.backend or (cur.backend if cur else BACKENDS[0]),
        "target": target,
        "repo": a.repo or (cur.code_repo if cur else None),
        "git": git,
        "visibility": a.visibility or (cur.visibility if cur else None) or "private",
        "board_stages": a.stage or (cur.board_stages if cur else None) or list(DEFAULT_STAGES),
    }


def _print_bootstrap(rep: dict) -> int:
    if rep.get("mode") == "repo":
        # Inside a repo baton read and compared; nothing was written to the host. What
        # is missing gets fixed from the projects root, and the report says which.
        v = rep.get("validated", {})
        print(f"repo: {v.get('repo')}")
        for b_, st in (v.get("branches") or {}).items():
            print(f"  {b_}: {st}")
        print(f"board: {v.get('board')}")
        bad = ("MISSING" in str(v.get("repo")) or "UNREACHABLE" in str(v.get("board"))
               or any("UNPROTECTED" in s_ for s_ in (v.get("branches") or {}).values()))
        if bad:
            print("\n  fix these from the projects root — inside a repo baton only reads.")
        return 1 if bad else 0

    """One line per step, and the step's own words for what happened. The failure mode
    this guards against is not "it failed" — it is "it failed and looked like it
    worked", which is why every write here is reported from a read-back."""
    bad = False
    r = rep.get("repo", {})
    print(f"repo {r.get('name')}: {r.get('state')} ({r.get('visibility', '?')})")
    br = rep.get("branch", {})
    print(f"branch {br.get('name')}: {br.get('state')}")
    bad |= "no " in str(br.get("state", ""))

    prot = rep.get("protections", {})
    if prot.get("state"):                                  # dry-run shape
        print(f"protections {', '.join(prot['repos'])} "
              f"[{', '.join(prot.get('branches', []))}]: {prot['state']}")
    for name, one in prot.items():
        if name in ("state", "repos", "branches"):
            continue
        if not one.get("admin", True):
            print(f"protections {name}: SKIPPED — this credential has no admin there")
            print("  (set $GH_ADMIN_TOKEN, or have whoever holds admin re-run this)")
            bad = True
            continue
        for br, state in one.get("branches", {}).items():
            print(f"protection {name} {br}: {state}")
            bad |= ("missing" in state) or ("did NOT land" in state)

    bd = rep.get("board", {})
    if bd.get("failed"):
        # Loud, and the exit code goes non-zero below: everything above it DID happen,
        # and the whole point of reporting instead of raising is that you can see both.
        print(f"board: FAILED — {bd['failed']}")
        print("  the repo side above is done. Create the board project by hand and "
              "re-run this — it adopts what exists.")
        return 1
    print(f"board {bd.get('identifier') or bd.get('project', {}).get('identifier')}: "
          f"{'created' if bd.get('created') else bd.get('state', 'existed')}")
    if bd.get("default"):
        print(f"  new items land in: {bd['default']}")
        bad |= "NOT set" in bd["default"]
    if bd.get("order"):
        print(f"  board order: {bd['order']}")
        bad |= str(bd["order"]).startswith("still ")
    for name, state in (bd.get("stages") or {}).items():
        print(f"  stage {name}: {state}")
        bad |= "config wants" in state
    for name in bd.get("extra") or []:
        print(f"  stage {name}: EXTRA — not in board_stages "
              f"({(bd.get('pruned') or {}).get(name, 'kept; --prune deletes it')})")

    if rep.get("created"):
        print("\ncreated by this run:")
        for line in rep["created"]:
            print(f"  {line}")
    return 1 if bad else 0


def cmd_bootstrap(a, b, cfg):
    """Create the project — repo, integration branch, protections, board, stages — and
    write the config it all hangs off. Idempotent: everything is looked up before it is
    created, so this is also the command you re-run after a half-failure.

    `baton init` is the same command: recording where an existing repo and board are is
    what this does when the lookups find them.
    """
    want = _bootstrap_config(a)
    # Asked BEFORE anything is written. The role layer refuses the same thing, but by
    # then a repo may exist — an undecided flag should cost nothing but a re-run.
    checks = None if not (a.check or a.no_checks) else (a.check or [])
    if checks is None and not a.dry_run:
        raise BatonError(
            "refusing to guess about required checks: pass --check <name>, or --no-checks "
            "to say you mean it.\n"
            "A protection with no required check lets a red PR merge. One naming a check "
            "that does not exist yet makes every PR HANG — it does not fail, it waits for "
            "a status that never arrives.\n"
            "Require ONE aggregated name, never a build matrix's `test (3.11)`.")
    if a.dry_run:
        # No config written, nothing created: this is where a typo'd repo name shows up
        # as "would create" while it is still free.
        cfg = Config(backend=want["board"], target=want["target"], repo=want["repo"],
                     git=want["git"], visibility=want["visibility"],
                     board_stages=want["board_stages"])
        rep = Baton(cfg, a.role).plan()
        print("dry run — nothing was written or created\n")
        return _print_bootstrap(rep)

    path, changed, comments = write_config(
        want["board"], want["target"], repo=want["repo"], git=want["git"],
        visibility=want["visibility"], board_stages=want["board_stages"], force=a.force)
    print(f"config: {path}" + (" (updated)" if changed else ""))
    for key, (old, new) in changed.items():
        print(f"  {key}: {old!r} -> {new!r}")
    if comments:
        print("  note: comments in that file were lost — yaml round-trip cannot keep them")

    rep = Baton(load(path.parent.parent), a.role).bootstrap(
        project_name=a.name, checks=checks, reviews=a.reviews,
        enforce_admins=a.enforce_admins, prune=a.prune)
    print()
    rc = _print_bootstrap(rep)
    print("\nnext: `baton doctor`" + ("" if rc == 0 else " — and fix what is marked above"))
    return rc


def _missing_credential(var: str) -> None:
    """Say where the credential IS when the shell does not have it.

    Only the location and a command to export it — baton never reads the value itself.
    The point is that the credential entering the session stays a thing the user did on
    purpose, not something a CLI picked up from another program's config.
    """
    for name, path, keys in credential_sources(var):
        accessor = "".join(f"[{k!r}]" for k in keys)
        print(f"  ${var} is defined in the MCP server {name!r} ({path}). To reuse it:")
        print(f"    export {var}=$(python3 -c \"import json,os;"
              f"print(json.load(open(os.path.expanduser('{path}')))"
              f"{accessor})\")")


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


def cmd_export(a, b, cfg):
    """Read an old board out to JSON, comments included, so the migration skill can
    move it onto the real board. Read-only.

    The source is whatever `adapters/read/` has a file for — `migrate_from.kind`
    picks it. It started GitHub-only, and `--from-github` still works because the
    skill and the README say so.

    Which old board belongs to which project is PROJECT data, so it lives in that
    project's `.baton/config.yaml` under `migrate_from:` — the skills are installed
    globally and must not carry it. Flags override, for a one-off."""
    src_cfg = dict((cfg.migrate_from if cfg else {}) or {})
    kind = a.from_kind or src_cfg.pop("kind", "github")
    if a.from_github:                       # the one-off flag names its own source
        kind, src_cfg = "github", {**src_cfg, "repo": a.from_github}
    if a.project_number:
        src_cfg["project"] = a.project_number
    if a.owner:
        src_cfg["owner"] = a.owner
    if not src_cfg:
        raise BatonError(
            "no source board. Either pass --from-github OWNER/REPO, or declare it in "
            "this project's .baton/config.yaml:\n"
            "  migrate_from: {repo: OWNER/REPO, project: 5}\n"
            "  migrate_from: {kind: plane, base_url: ..., workspace: ..., project: ENG}")
    src = b.read(kind, **src_cfg)
    items = src.list(state=a.state)
    # GitHub without a project number has issues but no board, so no stages to read.
    # Every other source knows its own columns.
    has_board = kind != "github" or bool(src_cfg.get("project"))
    out = {
        "source": {"kind": kind, **src_cfg},
        "stages": src.list_stages() if has_board else [],
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
    print(f"exported {len(items)} items and {n_comments} comments from "
          f"{kind}:{src_cfg.get('repo') or src_cfg.get('project')}", file=sys.stderr)
    return 0


def cmd_release(a, b, cfg):
    """Set the deployment off, and then say whether it worked.

    Separate from `baton ship`, which moves ONE item: a release is one act for the
    whole batch. The skill runs this once, then ships the items it covered — and only
    if this said the deployment succeeded.
    """
    tag = a.tag or _tag_from_project()
    mode = _repo.release_mode(cfg)
    ad = b.repo()

    if not a.check:
        notes = a.notes if a.notes is not None else (
            sys.stdin.read() if not sys.stdin.isatty() else "")
        rep = _repo.release(ad, cfg, tag, title=a.title or tag, notes=notes)
        print(f"{rep['mode']}: {rep['did']}" + (f"\n{rep['url']}" if rep.get("url") else ""))

    ok, runs = _repo.deploy_verdict(ad, cfg, tag)
    for name, verdict in sorted(runs.items()):
        print(f"  {name}: {verdict}")
    if ok:
        print(f"deploy verified for {tag}" if mode != "none"
              else "nothing to verify — merging already deployed")
        return 0
    # Loud, and non-zero: the failure this whole verb exists for is a release that
    # looked done. `baton-ship` must not close a single item past this line.
    print(f"\nDEPLOY NOT VERIFIED for {tag}."
          + ("  No run has started yet — re-run this to check again."
             if not runs else "  Do NOT close the items."), file=sys.stderr)
    return 1


def _tag_from_project() -> str:
    """`v` + the version in pyproject.toml.

    Only pyproject: baton is not going to grow a detector for every ecosystem's idea
    of where a version lives. Where it cannot know, it asks — the same rule this item
    applies one level up. A guessed tag on a package is worse than one typed by hand,
    which is why `publish.yml` aborts when the tag and the version disagree.
    """
    v = version.from_source(Path.cwd() / "x")
    if not v:
        raise BatonError(
            "no pyproject.toml here, so the tag cannot be derived — pass --tag vX.Y.Z.\n"
            "It is not guessed on purpose: a wrong tag on a published package cannot "
            "be taken back.")
    return f"v{v}"


def cmd_config(a, b, cfg):
    """Print one config value by dotted path — `baton config git.integration`.

    Exists so a skill or a shell script can ASK instead of hardcoding. A branch name
    baked into a SKILL.md is wrong for every project that names things differently,
    and the skills are installed globally.
    """
    cur = cfg
    for part in a.key.split("."):
        cur = cur.get(part) if isinstance(cur, dict) else getattr(cur, part, None)
        if cur is None:
            raise BatonError(f"config key {a.key!r} is not set in {cfg.path}")
    print(json.dumps(cur) if isinstance(cur, (dict, list)) else cur)
    return 0


def cmd_doctor(a, b, cfg):
    print(f"baton {__version__}")
    # A version that is merely printed proves nothing: an editable install whose
    # metadata went stale reports a number the code no longer is, silently. That is how
    # `doctor` once told people 0.1.0 while PyPI served 0.3.0.
    drift = version.mismatch()
    if drift:
        print(f"  note: {drift}")
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
        # The board: ONE credential, so one line. Which verb is running does not
        # change whose it is — see `_BOARD_TOKEN`.
        board_var = cfg.token_env()
        if not os.environ.get(board_var):
            print(f"board ${board_var}: NOT set — skipped")
            _missing_credential(board_var)
        else:
            print(f"board ${board_var}:")
            ok &= _probe(f"board ({cfg.backend})", lambda: Baton(cfg).board)

        # git is a SECOND system on a SECOND credential — "the board answers" says
        # nothing about whether you can push. And one credential can reach one repo of
        # a multi-repo project and not the next, so check each.
        if cfg.all_repos:
            repo_var = cfg.token_env("repo")
            if not os.environ.get(repo_var):
                print(f"code ${repo_var}: NOT set — falling back to `gh auth`")
            else:
                print(f"code ${repo_var}:")
            for r in cfg.all_repos:
                ok &= _probe(f"code {r}", lambda x=r: Baton(cfg).repo(x))
    finally:
        if saved is None:
            os.environ.pop("GH_TOKEN", None)
        else:
            os.environ["GH_TOKEN"] = saved

    # Protection is per REPO, not per credential, so it gets its own section instead
    # of being repeated under each token role. Reported and not failed: a solo
    # trunk-based project may legitimately have none. What must not happen is finding
    # out months later that one repo of a multi-repo project was never protected.
    if cfg.all_repos:
        print("branch protection:")
        wanted = [cfg.git["integration"], cfg.git["production"]]
        holes = False
        for r in cfg.all_repos:
            try:
                st = b.repo(r).branch_protection(wanted)
                print(f"  {r}: " + " · ".join(f"{b}={s}" for b, s in st.items()))
                holes |= "UNPROTECTED" in st.values()
            except BatonError as e:
                print(f"  {r}: could not read — {e}")
        if holes:
            print("  ^ an unprotected branch means an agent with push rights skips the"
                  " PR, the review and CI entirely.")
            print("    Fix: baton bootstrap --check <your CI check>   (idempotent; "
                  "protects every repo the config declares)")

    # A ROOT reports on every repo it holds. This is what the per-repo `repos:` map
    # used to buy: standing in one repo you could see that a SIBLING was unprotected —
    # the kind of hole nobody finds because nobody stands there. The root is where that
    # view belongs, and from here it can also see what the map does not know about.
    if cfg.is_root:
        print(f"projects root: {len(cfg.repos)} registered")
        registered = set()
        for key, entry in sorted(cfg.repos.items()):
            e = cfg.repo_entry(key) or {}
            folder = Path(e.get("folder") or key)
            here = (cfg.path.parent.parent / folder) if cfg.path else folder
            registered.add(here.resolve())
            state = []
            state.append("folder" if here.is_dir() else "FOLDER MISSING")
            state.append("linked" if (here / ".baton" / "config.yaml").is_file()
                         else "NOT LINKED")
            print(f"  {key}: {e.get('repo', '?')} — {' · '.join(state)}")
            ok &= "MISSING" not in " ".join(state) and "NOT" not in " ".join(state)
        # What the map does not know about: a folder that linked itself and never got
        # registered. Silent drift is the failure mode of every hand-kept list.
        base = cfg.path.parent.parent if cfg.path else Path.cwd()
        for d in sorted(p for p in base.iterdir() if p.is_dir()):
            if (d / ".baton" / "config.yaml").is_file() and d.resolve() not in registered:
                print(f"  {d.name}: linked but NOT in the map — add it or it is invisible here")
                ok = False

    # How this project releases, checked against what its CI actually declares. Not
    # used to decide anything — `git.release` decides — but a config that says `tag`
    # on a repo whose only workflow fires on `release` is a ship that will report
    # success and publish nothing.
    if cfg.all_repos:
        declared = (cfg.git or {}).get("release")
        print(f"release mode: {declared or 'NOT SET — `baton release` will refuse'}")
        if not declared:
            print("  set git.release to one of: release · tag · none")
            ok = False
        try:
            fires = b.repo().release_triggers()
            if fires and declared and declared not in fires:
                print(f"  ^ but this repo's CI fires on {', '.join(sorted(fires))}"
                      f" — a release created as {declared!r} would set off nothing")
                ok = False
        except BatonError:
            pass                  # unreachable host: already reported above

    try:
        stages = b.board.list_stages()
        print(f"stages: {', '.join(stages) or '(none)'}")
    except BatonError as e:
        print(f"stages FAILED: {e}")
        ok = False

    # Capabilities are CHECKED, not declared — a backend's edition or version can
    # turn a feature off, and finding that out here beats finding it out mid-verb.
    # Inside the try because reaching the board can fail HERE too (no credential at
    # all): doctor's whole job is to check everything and then say what is broken, so
    # it must not die halfway through its own report.
    try:
        if "groups" in b.board.capabilities():
            print(f"epics (native groups): {len(b.board.list_groups())} on the board")
    except BatonError as e:
        print(f"epics (native groups): FAILED — {e}")
        ok = False
    # The lifecycle vocabulary, checked against the board rather than trusted. An alias
    # naming a column that is not there does not fail loudly: `require_verify` swallows
    # the lookup and the gate simply stops gating — which is exactly how a project ends
    # up believing it verifies and never does.
    try:
        on_board = {st.lower() for st in b.board.list_stages()}
        for verb, name in b.stages_map().items():
            if name.lower() not in on_board:
                print(f"stage @{verb}: {name!r} is NOT on the board"
                      + ("  ← the verify gate is off while this is true"
                         if verb == "verify" else ""))
                ok = False
        landing = b.board.default_stage()
        if landing and landing.lower() != b.stage("@triage").lower():
            print(f"new items land in {landing!r}, but @triage is "
                  f"{b.stage('@triage')!r} — run `baton bootstrap` to fix it")
            ok = False
    except BatonError:
        pass                      # unreachable board: already reported above

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
    # `--as` no longer chooses anything: there is one credential per adapter role,
    # and what it may do is decided by whoever issued it. Kept so existing scripts and
    # skills do not break on an unknown flag; it is a no-op and says so.
    p.add_argument("--as", dest="role", choices=["agent", "admin"], default=None,
                   help=argparse.SUPPRESS)
    sub = p.add_subparsers(dest="cmd", required=True)

    # `init` is the same command: with an existing repo and board, "create the project"
    # is exactly "write down where it is". Kept as an alias because it is what 0.3.0
    # documented and what people's notes say.
    s = sub.add_parser("bootstrap", aliases=["init"],
                       help="create the project (repo + board + protections) and write "
                            ".baton/config.yaml. Idempotent: re-run to resume")
    # No default: con uno, `bootstrap` re-corrido sobre un proyecto ya configurado
    # pisaba su backend con el primero de la lista. Latente mientras hubo un solo
    # backend, y un reseteo silencioso el día que hubo dos.
    s.add_argument("--backend", choices=list(BACKENDS),
                   help="board provider; default: lo que diga el config, si no plane")
    s.add_argument("--repo", help="OWNER/REPO where the code lives")
    s.add_argument("--owner", help="reserved for backends that separate board owner")
    # `--board`, not `--project`: the global -p/--project already means "a sibling
    # board", and an argparse subparser would silently clobber it.
    s.add_argument("--board", help="plane: project identifier (the ENG in ENG-123)")
    s.add_argument("--base-url", dest="base_url", help="plane: instance URL")
    s.add_argument("--workspace", help="plane: workspace slug")
    s.add_argument("--name", help="the board project's display name (default: its identifier)")
    s.add_argument("--visibility", choices=["private", "public"],
                   help="new repos only; default private")
    s.add_argument("--stage", action="append", metavar="NAME",
                   help="a stage the board must have, in board order (repeatable). "
                        "Default: " + ", ".join(DEFAULT_STAGES) + ". For a board whose "
                        "columns need explicit lifecycle groups, write `board_stages` "
                        "as a mapping in the config instead")
    s.add_argument("--integration", help=f"integration branch (default {DEFAULT_GIT['integration']})")
    s.add_argument("--production", help=f"production branch (default {DEFAULT_GIT['production']})")
    s.add_argument("--check", action="append", metavar="NAME",
                   help="required status check on both branches (repeatable). Use ONE "
                        "aggregated name, never a build matrix's `test (3.11)`")
    s.add_argument("--no-checks", dest="no_checks", action="store_true",
                   help="protect with no required check — say it on purpose: a red PR "
                        "can then merge. Re-run with --check once CI exists")
    s.add_argument("--reviews", type=int, default=1, metavar="N",
                   help="required approvals (default 1 — what stops an agent merging "
                        "its own work, since a PR author cannot approve their own)")
    s.add_argument("--enforce-admins", dest="enforce_admins", action="store_true",
                   help="protections apply to admins too; then every release needs a "
                        "human approval")
    s.add_argument("--prune", action="store_true",
                   help="DELETE board stages that `board_stages` does not declare "
                        "(a fresh Plane project ships Backlog/Todo/Done). Destructive "
                        "on a board with work in it")
    s.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="print the plan and change nothing")
    s.add_argument("--force", action="store_true",
                   help="replace config values that already say something different")
    s.set_defaults(fn=cmd_bootstrap)

    s = sub.add_parser("new", help="create an item")
    s.add_argument("--title", required=True)
    s.add_argument("--body")
    s.add_argument("--label", action="append")
    s.add_argument("--priority", choices=list(PRIORITIES),
                   help="the board's NATIVE priority field — not a priority: label")
    s.add_argument("--stage", help="initial stage: a column name, or baton's own name "
                                   "for it (@triage, @approve, @start, @verify, @ship, "
                                   "@cancel) so the command works on any board")
    s.set_defaults(fn=cmd_new)

    s = sub.add_parser("show", help="show an item")
    s.add_argument("id")
    s.add_argument("-c", "--comments", action="store_true",
                   help="include the comment trail (what other agents/people did)")
    s.set_defaults(fn=cmd_show)

    s = sub.add_parser("list", help="list items")
    s.add_argument("--stage", help="column name, or @verb (e.g. --stage @approve)")
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

    s = sub.add_parser("advance", help="move item to a stage (by name, or @verb)")
    s.add_argument("id")
    s.add_argument("--to", required=True,
                   help="column name, or baton's name for it (@approve, @start, ...)")
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

    s = sub.add_parser("export", help="read an old board out to JSON "
                                      "(migration source — read-only)")
    s.add_argument("--from", dest="from_kind", metavar="KIND",
                   help="source provider (adapters/read/<KIND>.py); default: what "
                        "migrate_from.kind says, else github")
    s.add_argument("--from-github", dest="from_github", metavar="OWNER/REPO")
    s.add_argument("--project", dest="project_number", metavar="N",
                   help="ProjectV2 number — without it you get issues but no stages")
    s.add_argument("--owner", help="project owner login (default: repo owner)")
    s.add_argument("--state", default="all", choices=["open", "closed", "all"])
    s.set_defaults(fn=cmd_export)

    s = sub.add_parser("release", help="set the deployment off the way this project "
                                       "does it, then verify it ran")
    s.add_argument("--tag", help="default: v + the version in pyproject.toml")
    s.add_argument("--title", help="default: the tag")
    s.add_argument("--notes", help="release body; omit to read stdin")
    s.add_argument("--check", action="store_true",
                   help="do not create anything — just report the deploy verdict")
    s.set_defaults(fn=cmd_release)

    s = sub.add_parser("config", help="print one config value by dotted path")
    s.add_argument("key", metavar="KEY", help="e.g. git.integration, target.repo")
    s.set_defaults(fn=cmd_config)

    s = sub.add_parser("doctor", help="validate config + backend discovery")
    s.set_defaults(fn=cmd_doctor)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd in ("bootstrap", "init"):  # runs WITHOUT a config — it writes one
            return args.fn(args, None, None) or 0
        if args.cmd == "export":             # config OPTIONAL: it holds `migrate_from`
            cfg = load() if find_config() else None
            return args.fn(args, Baton(cfg), cfg) or 0
        cfg = load()
        if getattr(args, "project", None):
            cfg = load_project(args.project, cfg)
        if args.cmd == "config":             # reads the config, never the backend
            return args.fn(args, None, cfg) or 0
        rc = args.fn(args, Baton(cfg, args.role), cfg)
        return rc or 0
    except BatonError as e:
        print(f"baton: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
