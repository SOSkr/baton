"""The BOARD role: read-write, permanent. Where the work-item lifecycle lives.

This module holds the rules that are true of EVERY board and of no provider in
particular — stage ordering, the verify gate, the verb aliases. They are written
against `BoardBase` and the config, and against nothing else: importing a concrete
provider here is the one thing this layer may never do (`registry` is how a class is
reached, and `tests/test_frontier.py` fails the build if that slips).
"""
from __future__ import annotations

from ...base import BatonError
from ...config import Config, resolve_token
from .. import registry
from .base import BoardBase

# baton's lifecycle vocabulary -> the column that means it here, when the project
# declares no alias. THE WHOLE MAP IS OPTIONAL: a config that says nothing gets these.
#
# This is the only place a column name is written down. Everything else — the CLI, the
# skills — refers to the stage by its baton name (`@approve`), so a project that renames
# a column changes one line of config and nothing else.
_DEFAULT_STAGE = {
    "triage": "Review",         # where a new item lands: the board's default stage
    "approve": "Approved",
    "start": "In Progress",
    "verify": "Verify",
    "ship": "Deployed",
    "cancel": "Cancelled",      # where dropped work goes
}

# The stage set `bootstrap` creates when a project declares none: the four verb
# defaults above, plus where an item starts and where it goes when dropped. Order is
# the board order, and the board order is what the verify gate reads.
DEFAULT_STAGES = ("Review", "Approved", "In Progress", "Verify", "Deployed",
                  "Cancelled")


def get(cfg: Config, role: str = "agent") -> BoardBase:
    """The board, authenticated as `role` (agent | admin)."""
    return registry.resolve("board", cfg.backend)(cfg.target, resolve_token(cfg, role))


def verb_stage(cfg: Config, verb: str) -> str:
    """Resolve a lifecycle verb to a board stage name (config alias or default)."""
    return cfg.stages.get(verb, _DEFAULT_STAGE[verb])


def resolve_stage(cfg: Config, value: str) -> str:
    """`@approve` -> whatever this project calls that stage. Anything else is taken
    literally, so `--stage "In Progress"` still works.

    The `@` form is what lets a skill say `baton list --stage @approve` instead of
    hardcoding a column name that is only correct on the board it was written against.
    """
    if not value.startswith("@"):
        return value
    verb = value[1:].strip().lower()
    if verb not in _DEFAULT_STAGE:
        raise BatonError(f"unknown lifecycle stage {value!r}. Known: "
                         + ", ".join("@" + k for k in _DEFAULT_STAGE))
    return verb_stage(cfg, verb)


def stage_map(cfg: Config) -> dict[str, str]:
    """The whole vocabulary as baton-name -> board column, defaults filled in."""
    return {verb: verb_stage(cfg, verb) for verb in _DEFAULT_STAGE}


def require_verify(ad: BoardBase, cfg: Config, item_id: str,
                   prev_stage: str | None, target_stage: str) -> None:
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


def flag_backward(ad: BoardBase, cfg: Config, item_id: str,
                  prev_stage: str | None, target_stage: str) -> None:
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


# ---------------------------------------------------------------- bootstrap rules
# Plane's own vocabulary for what a column MEANS in the lifecycle. baton reads
# open/closed off it (see `_CLOSED_GROUPS` in board/plane.py), which is why a created
# stage without the right group is not a cosmetic mistake: a "Deployed" column filed
# under `backlog` leaves every shipped item reading as open, forever, silently.
GROUPS = ("backlog", "unstarted", "started", "completed", "cancelled")

# One colour per group, because the API requires a colour and nobody should have to
# pick six. Change them here; they mean nothing to baton.
_COLOR = {"backlog": "#a3a3a3", "unstarted": "#8b8b8b", "started": "#3b82f6",
          "completed": "#16a34a", "cancelled": "#dc2626"}

# Names that mean "this work was dropped". Inference only — a project whose column is
# called something else says so explicitly in `board_stages`.
_CANCELLED = {"cancelled", "canceled", "cancelado", "cancelada", "rejected",
              "rechazado", "rechazada", "descartado", "descartada", "won't do", "wontfix"}


def _infer_groups(names: list[str], start_stage: str | None = None) -> list[str]:
    """Guess each stage's lifecycle group from its position, its name, and the stage
    the `start` verb points at.

    Three rules, in order:

    - a name that means dropped (Cancelled, Rechazado, ...) is `cancelled`;
    - the LAST stage that is not a cancellation is what "done" means — `[..., Deployed,
      Cancelled]` is the common shape, and reading "last" as literally-last would file
      Deployed under `started` and leave Cancelled as the only closed stage;
    - everything BEFORE the stage that `start` moves to is `unstarted`; from there on it
      is `started`. This is baton's own vocabulary, not a new guess: `Approved` means
      approved-and-not-begun, and grouping it with `In Progress` would show work as
      under way that nobody has picked up. A project whose start column is named
      something else says so in `stages: {start: <name>}`.
    """
    lowered = [n.strip().lower() for n in names]
    cancelled = {i for i, n in enumerate(lowered) if n in _CANCELLED}
    rest = [i for i in range(len(names)) if i not in cancelled]
    done = rest[-1] if rest else None
    try:
        started_from = lowered.index((start_stage or "").strip().lower())
    except ValueError:
        started_from = rest[1] if len(rest) > 1 else len(names)   # no start stage named:
                                                                  # only the first is unstarted
    out = []
    for i in range(len(names)):
        if i in cancelled:
            out.append("cancelled")
        elif i == done:
            out.append("completed")
        elif i < started_from:
            out.append("unstarted")
        else:
            out.append("started")
    return out


def wanted_stages(cfg: Config) -> list[tuple[str, str]]:
    """`config.board_stages` as [(name, group)], in board order.

    Two accepted shapes, because the simple case should stay simple:

        board_stages: [Review, Approved, In Progress, Verify, Deployed, Cancelled]
        board_stages: {Review: unstarted, ..., Deployed: completed, Cancelled: cancelled}

    A plain list is inferred; a mapping is taken at its word (and keeps its order —
    YAML mappings load in insertion order). Declare it when the guess would be wrong:
    a board in another language, or two closing columns.
    """
    raw = cfg.board_stages or []
    if isinstance(raw, dict):
        pairs = [(str(n), (g or "").strip().lower() or None) for n, g in raw.items()]
    else:
        pairs = [(str(n), None) for n in raw]
    for name, group in pairs:
        if group and group not in GROUPS:
            raise BatonError(f"board_stages: {name!r} has group {group!r}; "
                             f"must be one of {', '.join(GROUPS)}")
    guessed = _infer_groups([n for n, _ in pairs], verb_stage(cfg, "start"))
    return [(n, g or guessed[i]) for i, (n, g) in enumerate(pairs)]


def ensure_default_stage(ad: BoardBase, name: str) -> str:
    """Make `name` where new items land. Returns what happened, for the report.

    Worth doing even though most boards ship a default: the backend's own default is
    a column IT chose (Plane calls it Backlog), so an item created without an explicit
    stage lands outside the lifecycle this project declared — and stays there, because
    nothing in the flow ever looks at a column nobody named.
    """
    if ad.default_stage() == name:
        return "already"
    ad.set_default_stage(name)
    return f"set to {name}"


def ensure(ad: BoardBase, project_name: str, stages: list[tuple[str, str]],
           default: str | None = None) -> dict:
    """The board, then its stages. Looks before creating, at both levels.

    Never touches what already exists — not the project, not a stage whose group
    disagrees with the config, not the extra stages a fresh Plane project ships with
    (Backlog, Todo, Done...). Those are REPORTED: deleting a stage on a board that
    already has work in it loses that work's history, so it takes `--prune` and a human.
    """
    found = ad.find_project()
    created = not found
    if created:
        found = ad.create_project(project_name)

    have = ad.stage_groups()                                  # name -> group, board order
    by_lower = {name.lower(): (name, group) for name, group in have.items()}
    report: dict = {"project": found, "created": created, "stages": {}, "extra": []}

    for name, group in stages:
        hit = by_lower.get(name.lower())
        if hit is None:
            ad.create_stage(name, group=group, color=_COLOR[group])
            report["stages"][name] = f"created ({group})"
        elif hit[1] and hit[1] != group:
            # Not fixed here: changing a stage's group changes what every item already
            # sitting in it counts as. That is a call for a human, with the board open.
            report["stages"][name] = f"existed — group is {hit[1]!r}, config wants {group!r}"
        else:
            report["stages"][name] = "existed"

    # Where new items land, before anything is pruned: the backend refuses to delete
    # the stage holding that flag, so moving it is what makes its own leftovers
    # removable at all.
    if default:
        if default.lower() in {n.lower() for n, _ in stages}:
            report["default"] = ensure_default_stage(ad, default)
        else:
            # `stages.triage` names a column this project never declared. Not fatal —
            # the board still works — but new items will land wherever the backend
            # decides, which is the thing this exists to stop.
            report["default"] = f"NOT set — {default!r} is not in board_stages"

    wanted = {n.lower() for n, _ in stages}
    report["extra"] = [n for n in have if n.lower() not in wanted]

    # ORDER is a rule, not decoration: `require_verify` and `flag_backward` read the
    # board's own stage order to tell a step forward from a step back. Backends append,
    # and a stage that already existed sits wherever the backend once put it — so the
    # declared order is applied to ALL of them, created or not. Position says nothing
    # about the work in a column, which is why this is the one thing here that rewrites
    # a stage nobody asked to create.
    declared = [n for n, _ in stages]
    if [s for s in ad.list_stages() if s.lower() in wanted] != declared:
        for position, name in enumerate(declared):
            ad.set_stage_position(name, position)
        report["order"] = "reordered to match board_stages"
    final = [s for s in ad.list_stages() if s.lower() in wanted]
    if final != declared:                     # the backend did not take it: say so
        report["order"] = f"still {' · '.join(final)}"
    return report


def prune_stages(ad: BoardBase, names: list[str]) -> dict:
    """Delete stages the config does not declare. Destructive and opt-in (`--prune`):
    on a fresh board these are Plane's defaults, but the SAME call on a board with work
    in it removes columns that items live in."""
    out = {}
    for n in names:
        try:
            ad.delete_stage(n)
            out[n] = "deleted"
        except BatonError as e:
            out[n] = f"kept — {e}"
    return out
