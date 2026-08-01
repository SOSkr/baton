"""Runnable check for `baton bootstrap` — no network.

Two fakes (a code host, a board) stand in for the providers, so what is under test is
the RULES: look before creating, never trust a write you have not read back, and get a
stage's lifecycle group right. Every failure mode covered here is one that is silent
in production: a board whose "Deployed" column counts as open, a protection that
returned 200 without landing, a re-run that creates a second repo.

Run: `python tests/test_bootstrap.py` or `pytest`.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from baton.adapters import board as board_role  # noqa: E402
from baton.adapters import repo as repo_role  # noqa: E402
from baton.adapters.board.base import BoardBase  # noqa: E402
from baton.adapters.repo.base import RepoBase  # noqa: E402
from baton.base import BatonError  # noqa: E402
from baton.config import Config, load, write_config  # noqa: E402
from baton.core import Baton  # noqa: E402


class FakeRepo(RepoBase):
    """A code host in a dict. `exists=False` is a repo that has to be created."""

    def __init__(self, name="acme/app", *, exists=True, admin=True, branches=None,
                 visibility="private"):
        self.repo = name
        self.facts = ({"name": name, "visibility": visibility, "default_branch": "master"}
                      if exists else None)
        self._admin = admin
        self.branches = dict(branches or ({"master": "sha-master"} if exists else {}))
        self.protected: dict[str, dict] = {}
        self.calls: list[str] = []
        self.dbom = False
        self.land = True          # False: the PUT "succeeds" and nothing changes

    def probe(self): return f"fake on {self.repo}"

    def permissions(self): return {"admin", "push"} if self._admin else {"push"}

    def find(self):
        self.calls.append("find")
        return dict(self.facts) if self.facts else None

    def create(self, visibility):
        self.calls.append(f"create:{visibility}")
        self.facts = {"name": self.repo, "visibility": visibility,
                      "default_branch": "master"}
        self.branches["master"] = "sha-master"
        return dict(self.facts)

    def branch_sha(self, ref): return self.branches.get(ref)

    def create_branch(self, name, sha):
        if name in self.branches:
            return False
        self.branches[name] = sha
        self.calls.append(f"branch:{name}@{sha}")
        return True

    def branch_protection(self, branches):
        return {b: ("protected" if b in self.protected else "UNPROTECTED")
                if b in self.branches else "missing"
                for b in dict.fromkeys(branches)}

    def required_checks(self, branch): return list(self.protected.get(branch, {}).get("checks", []))

    def protect_branch(self, branch, *, checks, reviews, enforce_admins):
        self.calls.append(f"protect:{branch}")
        if self.land:
            self.protected[branch] = {"checks": list(checks), "reviews": reviews,
                                      "enforce_admins": enforce_admins}

    def set_delete_branch_on_merge(self, value): self.dbom = value


class FakeBoard(BoardBase):
    """A board in a dict, shipping Plane's default states when freshly created.

    States carry a `sequence` like the real backend, because ORDER is what several of
    baton's rules read — and because ordering by sequence is exactly what lets a created
    stage land BETWEEN two the backend already had.
    """

    # name -> (group, sequence). The numbers are Plane's own.
    PLANE_DEFAULTS = {"Backlog": ("backlog", 15000), "Todo": ("unstarted", 25000),
                      "In Progress": ("started", 35000), "Done": ("completed", 45000),
                      "Cancelled": ("cancelled", 55000)}

    def __init__(self, *, exists=True, states=None):
        self.project = {"id": "p1", "identifier": "APP", "name": "app"} if exists else None
        if states is None:
            self._states = dict(self.PLANE_DEFAULTS) if exists else {}
        else:   # a test naming groups only: keep the order it wrote them in
            self._states = {n: (g, (i + 1) * 10000) for i, (n, g) in enumerate(states.items())}
        self.created_states: list[tuple[str, str, str]] = []
        self.deleted: list[str] = []
        # The backend picks its own default, and it is NOT "the first one": Plane flags
        # Backlog and then refuses to delete whatever holds the flag.
        self._default = "Backlog" if (states is None and exists) else None

    @property
    def states(self) -> dict:
        """name -> group, in board order (by sequence), like `stage_groups()`."""
        return {n: g for n, (g, _) in sorted(self._states.items(), key=lambda kv: kv[1][1])}

    # bootstrap surface
    def find_project(self): return dict(self.project) if self.project else None

    def create_project(self, name):
        self.project = {"id": "p1", "identifier": "APP", "name": name}
        self._states = dict(self.PLANE_DEFAULTS)    # a fresh project is not empty
        self._default = "Backlog"
        return dict(self.project)

    def stage_groups(self): return dict(self.states)

    def default_stage(self): return self._default

    def set_default_stage(self, name):
        if name not in self._states:
            raise BatonError(f"stage {name!r} not found")
        self._default = name

    def create_stage(self, name, *, group, color):
        """Appends, like a real backend: ordering is a separate act."""
        self.created_states.append((name, group, color))
        seq = max((s for _, s in self._states.values()), default=0) + 10000
        self._states[name] = (group, seq)

    def set_stage_position(self, name, position):
        group, _ = self._states[name]
        self._states[name] = (group, (position + 1) * 10000)

    def delete_stage(self, name):
        if name not in self._states:
            raise BatonError(f"stage {name!r} not found")
        if name == self._default:               # Plane's own words, and its own refusal
            raise BatonError("Default state cannot be deleted")
        del self._states[name]
        self.deleted.append(name)

    # lifecycle surface — not what this file tests
    def probe(self): return "fake board"
    def list_stages(self): return list(self.states)      # board order
    def create(self, title, body, labels, priority=None): raise NotImplementedError
    def get(self, item_id): raise NotImplementedError
    def list(self, **kw): return []
    def comment(self, item_id, text): pass
    def comments(self, item_id): return []
    def set_stage(self, item_id, stage): pass
    def set_labels(self, item_id, add=None, remove=None): pass
    def edit_body(self, item_id, body): pass
    def close(self, item_id, reason=""): pass


# --------------------------------------------------------------- stage groups
def test_group_is_inferred_from_position_not_index():
    """`[..., Deployed, Cancelled]` is the common shape. Reading "done" as literally the
    last stage would file Deployed under `started` — and baton derives open/closed from
    the group, so every shipped item would read as open forever."""
    cfg = Config(backend="plane", board_stages=[
        "Review", "Approved", "In Progress", "Verify", "Deployed", "Cancelled"])
    assert board_role.wanted_stages(cfg) == [
        ("Review", "unstarted"), ("Approved", "unstarted"), ("In Progress", "started"),
        ("Verify", "started"), ("Deployed", "completed"), ("Cancelled", "cancelled")]


def test_unstarted_runs_up_to_the_stage_the_start_verb_points_at():
    """`Approved` means approved-and-not-begun. Grouping it with `In Progress` shows
    work as under way that nobody picked up — and which column means "begun" is
    something baton already knows, from `stages: {start: ...}`."""
    cfg = Config(backend="plane", stages={"start": "Haciendo"},
                 board_stages=["Idea", "Lista", "Haciendo", "Hecho"])
    assert board_role.wanted_stages(cfg) == [
        ("Idea", "unstarted"), ("Lista", "unstarted"),
        ("Haciendo", "started"), ("Hecho", "completed")]

    # A board that never names its start column keeps the old shape: only the first
    # stage is unstarted, because there is nothing better to go on.
    plain = Config(backend="plane", board_stages=["Uno", "Dos", "Tres"])
    assert [g for _, g in board_role.wanted_stages(plain)] == [
        "unstarted", "started", "completed"]


def test_explicit_mapping_wins_over_the_guess():
    """A board in another language, or with two closing columns, says so itself."""
    cfg = Config(backend="plane", board_stages={
        "Pendiente": "unstarted", "Haciendo": "started",
        "Desplegado": "completed", "Cancelado": "cancelled"})
    got = dict(board_role.wanted_stages(cfg))
    assert got["Desplegado"] == "completed" and got["Cancelado"] == "cancelled"
    # and order survives the mapping (YAML loads insertion-ordered)
    assert [n for n, _ in board_role.wanted_stages(cfg)][0] == "Pendiente"


def test_unknown_group_is_refused_with_the_list():
    cfg = Config(backend="plane", board_stages={"Review": "unstarted", "Done": "finished"})
    try:
        board_role.wanted_stages(cfg)
        assert False, "expected BatonError"
    except BatonError as e:
        assert "finished" in str(e) and "completed" in str(e)


# --------------------------------------------------------------- board side
def test_board_creates_only_the_missing_stages_and_reports_the_extras():
    bd = FakeBoard(exists=False)
    cfg = Config(backend="plane", board_stages=[
        "Review", "Approved", "In Progress", "Verify", "Deployed", "Cancelled"])
    rep = board_role.ensure(bd, "app", board_role.wanted_stages(cfg))

    assert rep["created"] is True
    # "In Progress" and "Cancelled" came with the fresh project — not created twice
    assert [n for n, _, _ in bd.created_states] == ["Review", "Approved", "Verify", "Deployed"]
    assert rep["stages"]["Deployed"] == "created (completed)"
    assert rep["stages"]["In Progress"] == "existed"
    # left in the DECLARED order, not appended after the backend's own defaults:
    # `require_verify` and `flag_backward` read stage ORDER as a rule
    assert [s for s in bd.list_stages() if s in dict(board_role.wanted_stages(cfg))] == [
        "Review", "Approved", "In Progress", "Verify", "Deployed", "Cancelled"]
    assert rep["order"] == "reordered to match board_stages"

    # Plane's own defaults that the project does not want are reported, never removed.
    # `Done` is in that list: this project ships to `Deployed`, so Plane's `Done` is a
    # column nothing will ever move to — exactly the kind of thing worth being told.
    assert sorted(rep["extra"]) == ["Backlog", "Done", "Todo"]
    assert bd.deleted == []


def test_new_items_land_where_the_config_says_and_the_old_default_becomes_prunable():
    """The backend picks its own default column (Plane calls it Backlog) and refuses to
    delete the one holding that flag. Moving it first is what makes the leftovers
    removable, and what stops `baton new` filing work outside the lifecycle."""
    bd = FakeBoard(exists=False)
    cfg = Config(backend="plane", board_stages=["Review", "In Progress", "Deployed"])
    rep = board_role.ensure(bd, "app", board_role.wanted_stages(cfg),
                            default=board_role.verb_stage(cfg, "triage"))
    assert rep["default"] == "set to Review"
    assert bd.default_stage() == "Review"

    board_role.prune_stages(bd, rep["extra"])       # now that Backlog is not the default
    assert list(bd.states) == ["Review", "In Progress", "Deployed"]

    # re-running says so instead of writing again
    again = board_role.ensure(bd, "app", board_role.wanted_stages(cfg),
                              default=board_role.verb_stage(cfg, "triage"))
    assert again["default"] == "already"


def test_an_existing_stage_in_the_wrong_place_is_moved():
    """Position is the one property bootstrap rewrites on a stage it did not create: it
    says nothing about the work in that column, and the gate reads order as a rule."""
    bd = FakeBoard(states={"Deployed": "completed", "Review": "unstarted"})
    rep = board_role.ensure(bd, "app", [("Review", "unstarted"), ("Deployed", "completed")])
    assert list(bd.states) == ["Review", "Deployed"]
    assert rep["order"] == "reordered to match board_stages"


def test_existing_stage_with_the_wrong_group_is_reported_not_silently_changed():
    """Changing a stage's group changes what every item already sitting in it counts
    as. That is a human's call, with the board open."""
    bd = FakeBoard(states={"Deployed": "started"})
    rep = board_role.ensure(bd, "app", [("Deployed", "completed")])
    assert "group is 'started'" in rep["stages"]["Deployed"]
    assert bd.states["Deployed"] == "started"       # untouched


def test_prune_deletes_the_extras_but_not_the_one_holding_the_default():
    """The backend refuses to delete its default column, and says so. Reported, not
    raised: pruning three of four and telling you which one stayed beats failing."""
    bd = FakeBoard()
    rep = board_role.ensure(bd, "app", [("In Progress", "started")])
    out = board_role.prune_stages(bd, rep["extra"])
    assert sorted(bd.deleted) == ["Cancelled", "Done", "Todo"]
    assert "Default state cannot be deleted" in out["Backlog"]
    assert set(bd.states) == {"In Progress", "Backlog"}


# --------------------------------------------------------------- repo side
def test_repo_is_looked_up_before_it_is_created():
    """The rule that makes a re-run safe: a half-failed bootstrap left the repo
    behind, and the second run has to reuse it, not trip over it."""
    existing = FakeRepo()
    facts, made = repo_role.ensure(existing, "private")
    assert made is False and existing.calls == ["find"]

    fresh = FakeRepo(exists=False)
    facts, made = repo_role.ensure(fresh, "public")
    assert made is True and facts["visibility"] == "public"
    assert fresh.calls == ["find", "create:public"]


def test_integration_branch_is_cut_from_the_default_branch_and_only_once():
    ad = FakeRepo()
    assert repo_role.ensure_branch(ad, "develop", base="master") == ("created", True)
    assert repo_role.ensure_branch(ad, "develop", base="master") == ("existed", False)
    assert ad.branches["develop"] == "sha-master"


def test_protect_refuses_to_guess_about_checks():
    """A protection with no check lets a red PR merge; one naming a check that does not
    exist makes every PR hang. Undecided is not a default anyone should get."""
    try:
        repo_role.protect(FakeRepo(), ["develop"], checks=None)
        assert False, "expected BatonError"
    except BatonError as e:
        assert "refusing to guess" in str(e)
    # explicitly none is allowed
    rep = repo_role.protect(FakeRepo(branches={"master": "s", "develop": "s"}),
                            ["develop"], checks=[])
    assert rep["branches"]["develop"] == "protected checks=(none)"


def test_no_admin_is_skipped_and_nothing_is_written():
    ad = FakeRepo(admin=False)
    rep = repo_role.protect(ad, ["develop", "master"], checks=["test"])
    assert rep["admin"] is False and rep["branches"] == {}
    assert ad.calls == [] and ad.dbom is False      # checked BEFORE writing


def test_a_write_that_did_not_land_is_reported_as_such():
    """The whole reason protections are read back: a PUT that returned 200 and a branch
    that is actually protected are two different claims."""
    ad = FakeRepo(branches={"master": "sha-master", "develop": "sha-develop"})
    ad.land = False
    rep = repo_role.protect(ad, ["develop"], checks=["test"])
    assert "did NOT land" in rep["branches"]["develop"]


def test_missing_branch_is_skipped_not_invented():
    ad = FakeRepo()                                  # only master exists
    rep = repo_role.protect(ad, ["develop", "master"], checks=["test"])
    assert rep["branches"]["develop"] == "missing — skipped"
    assert rep["branches"]["master"] == "protected checks=test"
    assert ad.dbom is True


def test_trunk_based_repo_is_protected_once():
    ad = FakeRepo()
    rep = repo_role.protect(ad, ["master", "master"], checks=["test"])
    assert list(rep["branches"]) == ["master"]
    assert ad.calls.count("protect:master") == 1


# --------------------------------------------------------------- both sides
def _baton(monkey_repo, monkey_board, cfg):
    """A Baton whose two sides are the fakes. `board=` is injected; the repo side is
    reached through one seam, `repo.get`."""
    b = Baton(cfg, "admin", board=monkey_board)
    repo_role.get = lambda *a, **kw: monkey_repo      # noqa: E731 — restored by caller
    return b


def test_bootstrap_does_both_sides_in_one_call_and_says_what_it_created():
    cfg = Config(backend="plane", repo="acme/app", target={"project": "APP"},
                 board_stages=["Review", "In Progress", "Deployed", "Cancelled"])
    rp, bd = FakeRepo(exists=False), FakeBoard(exists=False)
    real_get, real_board_get = repo_role.get, board_role.get
    try:
        repo_role.get = lambda *a, **kw: rp
        board_role.get = lambda *a, **kw: bd
        rep = Baton(cfg, "admin").bootstrap(checks=["test"])
    finally:
        repo_role.get, board_role.get = real_get, real_board_get

    assert rep["repo"]["state"] == "created"
    assert rep["branch"] == {"name": "develop", "state": "created"}
    assert rep["protections"]["acme/app"]["branches"]["develop"].startswith("protected")
    assert rep["board"]["created"] is True
    assert rep["board"]["stages"]["Deployed"] == "created (completed)"
    # what to undo, since nothing is rolled back automatically
    assert any("gh repo delete acme/app" in line for line in rep["created"])
    assert any("board project APP" in line for line in rep["created"])


def test_bootstrap_on_an_existing_project_creates_nothing():
    """Adopting an existing repo+board is the same command: the lookups find them."""
    cfg = Config(backend="plane", repo="acme/app", target={"project": "APP"},
                 board_stages=["In Progress"])
    rp = FakeRepo(branches={"master": "s", "develop": "s"})
    bd = FakeBoard(states={"In Progress": "started"})
    real_get, real_board_get = repo_role.get, board_role.get
    try:
        repo_role.get = lambda *a, **kw: rp
        board_role.get = lambda *a, **kw: bd
        rep = Baton(cfg, "admin").bootstrap(checks=["test"])
    finally:
        repo_role.get, board_role.get = real_get, real_board_get

    assert rep["repo"]["state"] == "existed"
    assert rep["branch"]["state"] == "existed"
    assert rep["board"]["created"] is False
    assert rep["created"] == []
    assert bd.created_states == []
    # this project declares no triage column, so there is nothing to point new items at
    assert "not in board_stages" in rep["board"]["default"]


# --------------------------------------------------------------- the config it writes
def test_config_merge_keeps_the_keys_a_human_added():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / ".baton").mkdir()
        (root / ".baton" / "config.yaml").write_text(
            "backend: plane\n"
            "target: {base_url: 'https://p', workspace: w, project: APP}\n"
            "memory: mine\nprojects: {other: ../other}\n"
            "tokens: {agent: MY_KEY}\n")
        write_config("plane", {"base_url": "https://p", "workspace": "w", "project": "APP"},
                     repo="acme/app", board_stages=["Review"], root=root)
        cfg = load(root)
        assert cfg.memory == "mine" and cfg.projects == {"other": "../other"}
        assert cfg.tokens == {"agent": "MY_KEY"}         # not clobbered
        assert cfg.repo == "acme/app" and cfg.board_stages == ["Review"]
        assert cfg.adapters["board"] == "plane" and cfg.adapters["repo"] == "github"


def test_writing_less_than_the_file_already_says_is_not_a_conflict():
    """`adapters: {board: plane}` over `{board: plane, repo: github}` sets nothing new —
    it just says less, because defaults are not repeated. Treating that as a change
    would block the re-run that bootstrap documents as the way to resume."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / ".baton").mkdir()
        (root / ".baton" / "config.yaml").write_text(
            "adapters: {board: plane, repo: github}\n"
            "target: {base_url: 'https://p', workspace: w, project: APP, owner: acme}\n")
        target = {"base_url": "https://p", "workspace": "w", "project": "APP"}
        _, changed, _ = write_config("plane", target, root=root)   # must not raise
        assert changed == {}
        cfg = load(root)
        assert cfg.adapters["repo"] == "github"      # kept
        assert cfg.target["owner"] == "acme"         # kept


def test_config_refuses_to_change_a_value_without_force():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        target = {"base_url": "https://p", "workspace": "w", "project": "APP"}
        write_config("plane", target, repo="acme/app", root=root)
        try:
            write_config("plane", target, repo="acme/other", root=root)
            assert False, "expected BatonError"
        except BatonError as e:
            assert "acme/other" in str(e) and "--force" in str(e)
        # the same values again change nothing — which is what makes a re-run resume
        write_config("plane", target, repo="acme/app", root=root)
        write_config("plane", target, repo="acme/other", root=root, force=True)
        assert load(root).repo == "acme/other"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ok — bootstrap rules hold")
