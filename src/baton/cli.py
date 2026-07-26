"""baton CLI — mechanical work-item ops over a board backend.

The generic primitives; skills (SKILL.md) compose them and add judgment.
Verbs: new · show · list · stages · advance · comment · close · labels · body · doctor.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .adapters import get_adapter
from .base import BatonError, Item
from .config import load


def _emit(obj, as_json: bool):
    if as_json:
        print(json.dumps(obj, default=lambda o: o.__dict__, indent=2))
    else:
        if isinstance(obj, Item):
            print(f"#{obj.id} [{obj.stage or '-'}] {obj.title}\n  {obj.url}"
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


def cmd_new(a, ad, cfg):
    it = ad.create(a.title, a.body or "", a.label or [])
    if a.stage:
        ad.set_stage(it.id, a.stage)
        it.stage = a.stage
    _emit(it, a.json)


def cmd_show(a, ad, cfg):
    _emit(ad.get(a.id), a.json)


def cmd_list(a, ad, cfg):
    _emit(ad.list(stage=a.stage, label=a.label, state=a.state), a.json)


def cmd_stages(a, ad, cfg):
    st = ad.list_stages()
    _emit(st if a.json else "\n".join(st) or "(no status field)", a.json)


def cmd_advance(a, ad, cfg):
    prev = ad.get(a.id).stage
    ad.set_stage(a.id, a.to)
    _flag_backward(ad, cfg, a.id, prev, a.to)
    _emit(f"#{a.id} → {a.to}", a.json)


_DEFAULT_STAGE = {"approve": "Approved", "start": "In Progress", "ship": "Deployed"}


def _verb_stage(cfg, verb: str) -> str:
    """Resolve a lifecycle verb to a board stage name (config alias or default)."""
    return cfg.stages.get(verb, _DEFAULT_STAGE[verb])


def _cmd_verb(verb: str):
    def fn(a, ad, cfg):
        st = _verb_stage(cfg, verb)
        prev = ad.get(a.id).stage
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


def cmd_labels(a, ad, cfg):
    ad.set_labels(a.id, add=a.add or [], remove=a.remove or [])
    _emit(f"updated labels on #{a.id}", a.json)


def cmd_body(a, ad, cfg):
    body = a.body if a.body is not None else sys.stdin.read()
    ad.edit_body(a.id, body)
    _emit(f"updated body of #{a.id}", a.json)


def cmd_doctor(a, ad, cfg):
    print(f"baton {__version__}")
    print(f"config: {cfg.path}")
    print(f"backend: {cfg.backend}")
    print(f"target: {cfg.target}")
    try:
        stages = ad.list_stages()
        print(f"discovery OK — stages: {', '.join(stages) or '(none)'}")
        if cfg.stages:
            print(f"verb aliases: {cfg.stages}")
    except BatonError as e:
        print(f"discovery FAILED: {e}")
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="baton", description="Work-item lifecycle over a board.")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("new", help="create an item")
    s.add_argument("--title", required=True)
    s.add_argument("--body")
    s.add_argument("--label", action="append")
    s.add_argument("--stage", help="initial stage (else backend default)")
    s.set_defaults(fn=cmd_new)

    s = sub.add_parser("show", help="show an item")
    s.add_argument("id")
    s.set_defaults(fn=cmd_show)

    s = sub.add_parser("list", help="list items")
    s.add_argument("--stage")
    s.add_argument("--label")
    s.add_argument("--state", default="open", choices=["open", "closed", "all"])
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("stages", help="list the board's stages")
    s.set_defaults(fn=cmd_stages)

    s = sub.add_parser("advance", help="move item to a stage (by name)")
    s.add_argument("id")
    s.add_argument("--to", required=True)
    s.set_defaults(fn=cmd_advance)

    for verb in ("approve", "start", "ship"):
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

    s = sub.add_parser("labels", help="add/remove labels")
    s.add_argument("id")
    s.add_argument("--add", action="append")
    s.add_argument("--remove", action="append")
    s.set_defaults(fn=cmd_labels)

    s = sub.add_parser("body", help="replace item body (body or stdin)")
    s.add_argument("id")
    s.add_argument("--body")
    s.set_defaults(fn=cmd_body)

    s = sub.add_parser("doctor", help="validate config + backend discovery")
    s.set_defaults(fn=cmd_doctor)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = load()
        ad = get_adapter(cfg)
        rc = args.fn(args, ad, cfg)
        return rc or 0
    except BatonError as e:
        print(f"baton: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
