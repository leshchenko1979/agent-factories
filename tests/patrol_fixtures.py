"""Shared fixtures for the patrol leg gates — split out of tests/test_patrol_host_state.py
by #602. Not a gate itself: twelve test_patrol_*.py files import from here.

Origin (issue #95). `tests/test_board_intake_recorded.py` ships the predicate for "an
OPEN issue with no intake row" and is wired into the audit — but its live test calls
`board_intake_problems([], rows, complete_board=False)`: an EMPTY board. The forward leg
therefore examines **0 open issues** and the reverse leg is skipped by design. A gate
that has never been asked a question reports the same green as one that passes.

`tools/patrol_host_state.py` is part (b) — the host-side runner that supplies the input.
This file is its gate, and it asserts the six properties that make the runner worth
having, each with a probe that would fail on the shape it forbids:

1. **The board is read WHOLE.** The reverse leg is sound only over the full board, so a
   filtered read must never be what the runner passes. Probed at the argv the runner
   builds, not at its prose.
2. **A non-empty board with a missing leg is REPORTED, non-vacuously.** The predicate is
   injected, so the probe drives a board that must fail and asserts the count is non-zero
   — the acceptance criterion #95 names.
3. **A board that could not be read is NOT a clean board.** rc=2 with the failure named,
   never rc=0 over zero issues. This is the failure mode that makes a patrol worse than
   useless: a broken read rendering as a passing one.
4. **A leg that is not run says so.** The cron-thinness leg (#54 part b) is WIRED now, so
   the deferred set is EMPTY and the runner asserts exactly that — an absent leg is a
   different fact from a passing leg, and the two must never render the same. The surface
   is kept because the CLASS is what it guards, not the one instance: a deferral still
   renders as NOT RUN with its reason, a tracker it names must not be CLOSED, and a claim
   it states must not be one the tree contradicts (#121).
5. **A close row's board declaration is checked against the board** (#117). The offline
   close-board gate asserts the token was RECORDED; nothing asserted the recorded state was
   TRUE, so a close row could declare a board close that never happened and read clean. The
   leg binds to that gate's own `BOARD_TOKEN` and `INVARIANT_KEY` rather than re-deriving
   them — a trailer-only read sees 40 of the 52 post-invariant rows, so a re-derived leg
   would judge 12 rows fewer and go false-green over them.

6. **A failed notify SURFACES** (#122), and the leg reads FOUR classes (#139). A cron's
   notify can fail while the run row reads green, and the failure lands on the job-local
   log. The leg is keyed on the receipt FORM the daemon wrote — not on the byte count the
   finding arrived in, so a new error string at a familiar length cannot satisfy it — and
   BOTH success forms are accepted, because only the deferred branch writes an id and a
   token-only predicate therefore refused every immediate DELIVERY as a failed duty
   (#139, ruling n=1087). Delivery and deferral keep their own kinds, a log with no output
   is reported as never ATTEMPTED, and only a log with output and no receipt form is the
   failed duty. A phrase without a uuid is not a receipt (n=405 clause 5), and its live
  population is legitimately empty on a quiet day, so non-vacuity rides the probe and
  never a loud-fail-on-zero (#112) — the opposite call from the cron-thinness leg.

7. **The shared tree's blocking paths are NAMED, with the instant, and move no verdict**
   (#241). The board legs read ONE tree, and a tree another lane is mid-write on makes
   their verdicts unattributable — measured 2026-09-29, when the fork produced FALSE
   verdicts and no single location gave a wholly correct read. The rider prints the dirty
   paths that `origin/main` also moved (the class that makes `git reset --keep origin/main`
   refuse), the instant it read them, and NOT RUN with its reason when the tree cannot be
   read. It carries no problem and cannot move the exit code: a STANDALONE detection leg
   was refused as #83's class, so it is admitted only as this rider on the board legs.

Run:  python3 tests/test_patrol_host_state.py
Exit: 0 all checks pass, 1 a check failed.
"""

# --- imports ---------------------------------------------------------------
from __future__ import annotations
import importlib.util
import io
import json
import os
import sqlite3
import shutil
import subprocess
import tempfile
import datetime as dt
from pathlib import Path
from unittest import mock
import pytest

# --- shared helpers and module-level state, in the monolith's own order -----
REPO = Path(__file__).resolve().parent.parent

RUNNER_PATH = REPO / "tools" / "patrol_host_state.py"

def load_runner():
    spec = importlib.util.spec_from_file_location("patrol_host_state", RUNNER_PATH)
    assert spec and spec.loader, f"cannot load {RUNNER_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

RUNNER = load_runner()

_EMPTY_LOG_DIR = Path(tempfile.mkdtemp(prefix="patrol-empty-log-"))

_EMPTY_SCORES_DIR = Path(tempfile.mkdtemp(prefix="patrol-empty-scores-"))

_IN_STEP_HOMES_REPO = Path(tempfile.mkdtemp(prefix="patrol-in-step-homes-"))

(_IN_STEP_HOMES_REPO / "tests").mkdir(parents=True, exist_ok=True)

(_IN_STEP_HOMES_REPO / "tests" / "test_kit_questions_homes.py").write_text(
    'print("template home : TEMPLATE/tools/questions (100 B)")\n'
    'print("executing home: /tmp/probe-exec-questions (120 B)")\n'
    'print("population    : 0 differing line(s) examined")\n'
    'print("OK: the difference is confined to the declared layer '
    '(0 parameter entries + 0 named local fix + 0 declared block(s))")\n'
    'raise SystemExit(0)\n',
    encoding="utf-8",
)

_NO_RULING_EXEMPTIONS = (
    Path(tempfile.mkdtemp(prefix="patrol-no-exempt-")) / "ruling-board-exemptions.json"
)

_NO_REF_ROLE_EXEMPTIONS = (
    Path(tempfile.mkdtemp(prefix="patrol-no-ref-roles-")) / "ledger-ref-roles-exemptions.json"
)

_NO_CRITERION_EXEMPTIONS = (
    Path(tempfile.mkdtemp(prefix="patrol-no-criterion-"))
    / "criterion-path-exemptions.json"
)

_EMPTY_GOAL_STORE = {
    "rows": [],
    "homes_read": ["probe-home"],
    "homes_without_store": [],
    "unreached": [],
}

_EMPTY_CRITERION_TREE: Path | None = None

def _empty_criterion_tree() -> Path:
    """The empty repository a probe that supplies no tree of its own reads (#450).

    Built on FIRST USE rather than at import, so a box without git fails the probes that
    need a repository rather than the whole file at collection time.
    """
    global _EMPTY_CRITERION_TREE
    if _EMPTY_CRITERION_TREE is None:
        _EMPTY_CRITERION_TREE = _criterion_tree()
    return _EMPTY_CRITERION_TREE

def _issue(number: int, state: str, assignees: "list[str] | None" = None) -> dict:
    issue = {"number": number, "state": state, "title": f"issue {number}",
             "closedAt": None if state == "OPEN" else "2026-09-19T00:00:00Z"}
    # `assignees` is present ONLY when a fixture supplies one, mirroring the live `gh`
    # read: an issue with no assignee carries `[]` there, and a fixture that omits the
    # key must keep every other verdict intact (#423).
    if assignees is not None:
        issue["assignees"] = [{"login": login} for login in assignees]
    return issue

def _rows(*pairs) -> list[dict]:
    """Ledger rows from (event, subject, n[, detail]) tuples.

    The optional fourth element is the row's `detail`. It exists because #511 made the
    board-ruling leg's pairing PER ACT: a `ruling` row clears a comment only when its detail
    carries `comment=<numeric id>`, so a probe that wants a PAIRED arm has to be able to say
    so. Rows built without it keep the `"probe"` detail every other leg ignores.
    """
    out = []
    for pair in pairs:
        event, subject, n = pair[0], pair[1], pair[2]
        detail = pair[3] if len(pair) > 3 else "probe"
        out.append({"n": n, "ts": _CLOSE_TS, "event": event, "actor": "triage",
                    "subject": subject, "detail": detail})
    return out

def _swept(*pairs) -> list[dict]:
    """`_rows(...)` for a board the round has SWEPT **and DISPATCHED**.

    Since #519 a `ruling` row whose unit carries no `dispatch` row naming it is a DEFECT:
    the ruling decided, and nothing handed the decision to an implementer. So a fixture that
    models a CLEAN board must carry both acts -- the ruling decides, the dispatch routes.
    A fixture that carried only the ruling was clean under the old law and is a TRUE
    POSITIVE now, which is exactly what the leg exists to say; it is the fixture that is
    stale, not the leg.

    Every `ruling` subject without a matching `dispatch` subject gets one, numbered from
    9000 so it cannot collide with the fixture's own rows. A probe that wants the OWED arm
    uses `_rows(...)` -- the un-dispatched shape is now a statement, not the default.
    """
    out = _rows(*pairs)
    next_n = 9000
    for row in list(out):
        if row["event"] != "ruling":
            continue
        subject = row["subject"]
        if any(r["event"] == "dispatch" and r["subject"] == subject for r in out):
            continue
        out.append({"n": next_n, "ts": _CLOSE_TS, "event": "dispatch",
                    "actor": "hq", "subject": subject, "detail": "probe"})
        # ...and a CLAIM, because a dispatch nobody took is its own defect (a
        # "never-claimed dispatch" standing past the declared threshold). The three
        # acts are one story: the ruling decides, the dispatch routes, the claim takes.
        out.append({"n": next_n + 1, "ts": _CLOSE_TS, "event": "claim",
                    "actor": "worker", "subject": subject, "detail": "probe"})
        next_n += 2
    return out

def _comment_url(number: int, index: int = 1) -> str:
    """A comment URL carrying the NUMERIC id the pairing surface compares (#511).

    The board read returns GraphQL node ids in `comments[].id` and the numeric id only in
    `comments[].url`, and the ledger's `comment=` trailer carries the numeric one — so a
    fixture that omits `url` cannot be paired at all, and a probe built on one would exercise
    the fail-closed arm while believing it exercised the paired one. That is the control this
    helper re-arms.
    """
    return f"https://github.com/o/r/issues/{number}#issuecomment-{_comment_numeric(number, index)}"

def _comment_numeric(number: int, index: int = 1) -> str:
    """The numeric id `_comment_url` embeds, so a probe can name it in a row's detail."""
    return f"{number}{index:03d}"

_PROBE_KIT: tuple[Path, Path] | None = None

def _probe_kit_pair() -> tuple[Path, Path]:
    """A throwaway manifest+fleet pair that is CLEAN, built once and reused.

    The kit-drift leg's population is LIVE state: the tree's own `registry/kit.json` and
    the member repos `registry/fleet.json` names. `_run` injects every other dependency for
    exactly one reason — a probe must never measure what the box happens to hold — and
    these two were the last pair it left un-injected. The cost of the gap is not theoretical:
    in a tree that carries no pin (the kit's own donor half, which by design ships only
    `kit.example.json`) EVERY probe driven through `_run` reads red for a reason none of
    them names, so thirteen probes about the board, the cron leg and the duty leg were
    statements about the kit leg instead.

    The leg's own probes pass a pair of their own, so this default never stands in for one.
    """
    global _PROBE_KIT
    if _PROBE_KIT is None:
        body = b"probe\n"
        _PROBE_KIT = _synthetic_kit(
            Path(tempfile.mkdtemp(prefix="probe-kit-")),
            files={"tools/probe.py": body},
            members={"probe-member": {"same": {"tools/probe.py": body}}},
        )
    return _PROBE_KIT

def _run(issues, rows, *, cron_rows=None, homes=None, unreached=None, prefixes=None,
         log_dir=None, kit_manifest=None, fleet_manifest=None, presence_fn=None,
         dirty_paths_fn=None, ruling_scope=None, ruling_exemptions_path=None,
         delivery_scope=None, deliveries=None, criterion_repo=None,
         board_scope=None, lane_names_fn=None, cron_fires=None, scores_dir=None,
         shared_tree_fn=None, duty_scope=None, publish_fn=None, worktree_fn=None,
         duty_exemptions=None, ref_role_exemptions_path=None,
         criterion_exemptions_path=None, driverless_goals=None,
         driverless_turn_open=None, dispatch_batches=None, questions_homes=None,
         standing_items=None):
    """Drive main() with an injected board, ledger, cron table AND log surface; return
    (rc, out, err).

    The cron read is injected for the same reason the board is: a gate must never open
    the live database, and a probe that can only run against live state cannot run at all
    when that state is what is broken. An EMPTY declared prefix set leaves the cron leg
    inert, which is what the board-focused probes want — the probes that exercise the leg
    pass a prefix set and rows of their own.

    The log surface is injected for the third time and for the same reason (#122): with
    no declared prefix the notify-receipt leg judges nothing, and the default here is a
    fresh EMPTY directory rather than the live `/tmp`, so no probe depends on what the
    box happens to have left lying around. The probes that exercise the leg pass a
    directory of their own.

    The kit-drift leg's two manifests are injected for the fourth time and for the same
    reason, which the probes here had been quietly living without (see `_probe_kit_pair`).

    The board-ruling leg's bound and exemption table are injected for the fifth time and for
    the sharpest version of the same reason (issue #334): the leg is now BOUNDED by a
    declaration in this tree, so a probe that read the live declaration would be asserting
    this factory's own history rather than the leg's behaviour — and every probe written
    before the bound existed would silently change meaning, because an instance its fixture
    places before 2026-10-02 would stop being judged. So the default here is the leg's
    UNBOUNDED shape, which is exactly what those probes asserted when they were written, and
    the exemption table defaults to a path that does not exist — no probe's verdict may be
    decided by whatever exemptions the live factory happens to hold. A probe that asserts the
    bound passes `ruling_scope`; one that asserts the exemption surface passes
    `ruling_exemptions_path`.
    """
    cron_rows = [] if cron_rows is None else cron_rows
    homes = ["probe-home"] if homes is None else homes
    unreached = [] if unreached is None else unreached
    prefixes = [] if prefixes is None else prefixes
    log_dir = _EMPTY_LOG_DIR if log_dir is None else log_dir
    if kit_manifest is None or fleet_manifest is None:
        default_manifest, default_fleet = _probe_kit_pair()
        kit_manifest = default_manifest if kit_manifest is None else kit_manifest
        fleet_manifest = default_fleet if fleet_manifest is None else fleet_manifest
    out, err = io.StringIO(), io.StringIO()
    rc = RUNNER.main(
        [],
        board_fn=lambda slug: issues,
        slug_fn=lambda: "owner/repo",
        rows_fn=lambda: rows,
        cron_rows_fn=lambda: (cron_rows, homes, unreached),
        # The FIRE history (#449) is injected for the same reason the cron table is: the
        # duty-receipt leg's forward window is derived from it, so a probe must never have
        # its window decided by the live box's own runs table. The default is EMPTY, which
        # makes every job fall to the printed DEFAULT — the shape every pre-#449 probe was
        # written against — and a probe that asserts the derivation passes `cron_fires`.
        cron_fires_fn=lambda: ([] if cron_fires is None else cron_fires),
        prefixes_fn=lambda: prefixes,
        log_dir=log_dir,
        kit_manifest=kit_manifest,
        fleet_manifest=fleet_manifest,
        out=lambda *a, **k: print(*a, file=out, **k),
        err=lambda *a, **k: print(*a, file=err, **k),
        # #501: injectable so a probe can hand the runner a leg that RAISES. The default is
        # the stub, so every probe written before the containment guard keeps its meaning.
        publish_fn=publish_fn or _stub_publish_leg,
        worktree_fn=worktree_fn or _stub_worktree_leg,
        presence_fn=presence_fn or _stub_presence_leg,
        # The workspace-blocked leg's tree read is stubbed by default: a probe must not
        # cross-read against whatever THIS checkout happens to have dirty. A probe that
        # asserts the cross-read passes a `dirty_paths_fn` of its own.
        dirty_paths_fn=dirty_paths_fn or (lambda: set()),
        # The board-ruling leg's bound (issue #334): the leg's pure, UNBOUNDED shape is the
        # default, so every probe written before the bound existed keeps the meaning it was
        # written with. A probe that asserts the bound passes `ruling_scope`.
        ruling_scope_fn=(
            (lambda: ruling_scope) if ruling_scope is not None
            else (lambda: RUNNER.UNBOUNDED_SCOPE)
        ),
        # ... and a path that does not exist, so no probe's verdict is decided by the live
        # factory's own exemption table.
        ruling_exemptions_path=(
            _NO_RULING_EXEMPTIONS if ruling_exemptions_path is None
            else ruling_exemptions_path
        ),
        # The delivery leg (#49) is made INERT by default: an absent bound renders it
        # NOT RUN with its reason and no problem, so every probe written before the leg
        # existed keeps the meaning it was written with. A probe that asserts the leg
        # passes `delivery_scope` (the bound tuple) and `deliveries` (the store rows).
        delivery_scope_fn=(
            (lambda: delivery_scope) if delivery_scope is not None
            else (lambda: (None, "", "probe: the delivery leg is not exercised here"))
        ),
        deliveries_fn=lambda: (
            [] if deliveries is None else deliveries, ["probe-home"], []
        ),
        # The criterion-path leg (#48) resolves the paths a board criterion names against the
        # TREE AT THE READING REVISION (#450, template-instruments.md §7.5), so a probe must not have its verdict
        # decided by whether the LIVE repo holds `tools/x.py`. The default here is an empty
        # REPOSITORY — it exists, it resolves a commit, and its commit holds nothing — so a
        # probe that does not inject a tree of its own cannot accidentally pass by finding a
        # live file, and cannot read as NOT RUN either.
        criterion_repo_fn=(
            (lambda: criterion_repo) if criterion_repo is not None
            else _empty_criterion_tree
        ),
        # The score-conversion leg's surface (#67) is injected for the same reason and one
        # sharper one: the leg reads the NEWEST survey in the LIVE tree, so the default here
        # is an EMPTY directory -- a probe that does not pass one reads NOT RUN with its
        # reason, and no probe's verdict is decided by this factory's own latest scorecard.
        scores_dir_fn=(
            (lambda: scores_dir) if scores_dir is not None
            else (lambda: _EMPTY_SCORES_DIR)
        ),
        # The three BOARD legs' bounds (#428) are injected for the same reason the ruling
        # bound is: each judges a HISTORICAL population against a bound this tree declares,
        # and in the half of this byte-paired file that SHIPS no declaration exists. The
        # default reads whatever this tree declares and falls back to the kit's literal, so
        # every probe written before the conversion keeps its meaning; a probe that asserts
        # a pre-boundary, post-boundary, NOT RUN or REFUSED bound passes its own.
        board_scope_fn=(board_scope if board_scope is not None else _board_scope),
        # The duty-receipt leg's bound (#487) is injected for the same reason the three
        # board legs' are: it judges a HISTORICAL population of rounds against a bound THIS
        # tree declares, so a probe must be able to drive a pre-boundary round, a
        # post-boundary one or a REFUSED bound without the live declaration deciding its
        # verdict. The default reads this tree's declaration through the SAME `_duty_scope`
        # the probes derive their own instants from, so probe and leg resolve by one path.
        duty_scope_fn=(duty_scope if duty_scope is not None else _duty_scope),
        # The duty-receipt leg's declared-exemption store (#506) is injected for the same
        # reason: a probe must not have its verdict decided by whichever exemptions this
        # factory happens to hold, and the default here is an EMPTY store rather than the
        # live one, so an entry added later can never silently change a probe's meaning.
        duty_exemptions_fn=(
            duty_exemptions if duty_exemptions is not None else (lambda: ({}, None))
        ),
        # The ref-role leg's declared-exemption store (#330) is injected for the same reason,
        # and its default is a path that does NOT exist: the store ships absent in the kit's
        # donor half, so a probe must never have its verdict decided by the adjudications this
        # factory happens to hold. A probe that asserts the store passes its own path.
        ref_role_exemptions_path=(
            _NO_REF_ROLE_EXEMPTIONS if ref_role_exemptions_path is None
            else ref_role_exemptions_path
        ),
        # The criterion-path leg's declared-exemption store (#507) is injected for the same
        # reason, and the default is a path that does NOT exist: the store ships absent in the
        # kit's donor half, and an entry matching no live absence is a PROBLEM, so a probe
        # reading the LIVE store would red against its own synthetic board. A probe that
        # asserts the store passes a path of its own.
        criterion_exemptions_fn=(
            (lambda: _NO_CRITERION_EXEMPTIONS) if criterion_exemptions_path is None
            else (lambda: criterion_exemptions_path)
        ),
        # The stall-census leg's ONE read (#331 clause 2) is injected for the same reason as
        # every other declaration here: the default `lane_names_fn` resolves NO session id, so
        # an addressee can only resolve in a probe that supplied its own binding map — never
        # from whichever lanes this box happens to have bound. The park clause (clause 1)
        # needs no injection: it reads the unit's own rows, which the probe already supplies.
        lane_names_fn=lane_names_fn or (lambda: {}),
        # The driverless-lane leg's goal store (#133) is injected for the same reason as every
        # other live surface here, and the default is an EMPTY STORE that was READ: a probe
        # must never have its reading decided by whichever goal rows THIS box happens to hold,
        # and a lane judged against an unread store would read DRIVERLESS for want of a read
        # rather than for want of a driver. A probe that asserts a reading passes its own.
        driverless_goals_fn=lambda: (
            _EMPTY_GOAL_STORE if driverless_goals is None else driverless_goals
        ),
        # ... and "a turn is in flight" rides its own read (#133), injected for the same
        # reason and with the same safe default: NO session has a turn open. That default
        # WITHHOLDS the driven claim rather than granting it, so a probe that forgets to
        # inject cannot accidentally read a live turn as a driver it never asserted.
        driverless_turn_open_fn=lambda: dict(driverless_turn_open or {}),
        # The undispatched-ruling leg's batch declaration (#519) is injected for the same
        # reason every other declaration here is: the leg's verdict is "is this ruled item
        # corroborated by a dispatch row or a DECLARED batch act", and a probe that read the
        # live declaration would be asserting whichever batches THIS factory happens to have
        # recorded rather than the leg's behaviour. The default is the ABSENT declaration
        # with its own reason, which is the state a factory that has run no batch act is in
        # — so a probe written without a batch keeps its meaning, and a probe that asserts
        # the resolution passes its own map.
        dispatch_batches_fn=(
            (lambda: {"batches": {}, "batch_refusal": "ABSENT: probe: no batch declared"})
            if dispatch_batches is None
            else (lambda: {"batches": dispatch_batches, "batch_refusal": ""})
        ),

        # #586: the STANDING declaration is injected for the same reason and one sharper
        # one. A probe that read the live `docs/ledger-invariants.json` would be asserting
        # whichever permanent-state item THIS factory happens to have declared, so the
        # default is the ABSENT declaration with its own reason -- the state a factory that
        # has none is in. A probe that asserts the resolution passes its own map.
        standing_items_fn=(
            (lambda: {"standing": {}, "standing_refusal": "ABSENT: probe: none declared"})
            if standing_items is None
            else (lambda: {"standing": standing_items, "standing_refusal": ""})
        ),

        # #530: the questions-homes leg RUNS a gate against a tree, so a probe must
        # never have its verdict decided by this box's live executing home. The default
        # is a hermetic stub gate that reports a clean comparison over 0 lines, which
        # leaves every pre-#530 probe with the meaning it was written with.
        questions_homes_fn=lambda: (
            questions_homes if questions_homes is not None
            else {"repo": _IN_STEP_HOMES_REPO}
        ),
        # The shared-tree rider (#241) shells out three times against the tree the patrol
        # is running in, so it is stubbed by default for the same reason the publish and
        # worktree legs are: a probe must not pay for live state it never asserts. The
        # probes that DO assert the rider drive `render_shared_tree_rider` directly, or
        # pass a rider of their own here so the RENDER path is exercised, not assumed.
        shared_tree_fn=shared_tree_fn or _stub_shared_tree_rider,
    )
    return rc, out.getvalue(), err.getvalue()

def _stub_presence_leg(rows, homes_read, unreached, *, prefixes, read_at: str, **_kw) -> dict:
    """A canned pacemaker-presence leg for every probe that drives `main()`.

    The real leg reads the process register, the factory fragment and every profile's live
    session bindings — none of which a board or cron probe asserts — so without this stub
    each of those probes would judge the LIVE owners against its own synthetic rows and RED
    for a reason it never names. The leg's own probes drive `pacemaker_presence_leg`
    directly with injected readers, or pass a `presence_fn` of their own through `_run`.
    """
    return {
        "name": "pacemaker-presence",
        "status": "ASSERTED",
        "problems": [],
        "excused": [],
        "coverage": {
            "register": "(stub)",
            "owners_declared": 3,
            "rows_judged": len(rows),
            "unattributed_rows": 0,
            "homes_read": len(homes_read),
            "unreached_homes": list(unreached),
            "owners": ["HQ (stub-uuid): woken by factory-probe"],
            "resolution_notes": [],
            "read_at": read_at,
        },
    }

def _stub_worktree_leg(*, read_at: str, **_kw) -> dict:
    """A canned worktree leg for every probe that drives `main()`.

    The real leg shells out twice per registered worktree, so stubbing it is the same
    discipline the publish leg's stub exists for: a probe must not pay for live state it
    never asserts. The probes that DO assert the leg's behaviour drive `worktree_leg`
    directly with injected readers, and one drives `main()` with THIS stub replaced by a
    populated one so the render path is exercised rather than assumed.
    """
    return {
        "name": "worktree",
        "status": "ASSERTED",
        "problems": [],
        "excused": [],
        "coverage": {
            "read_at": read_at,
            "base_ref": "origin/main",
            "hazard_classes": ["unreachable-commit", "uncommitted-work"],
            "removes": False,
            "worktrees_total": 2,
            "worktrees_scratch": 1,
            "missing_directory": [],
            "unreachable_commits": [{"path": "/probe/scratch", "ahead": 1}],
            "uncommitted_work": [{"path": "/probe/scratch", "paths": 2}],
            "instrument": "git worktree list --porcelain / git worktree prune",
            "population_predicate": "git worktree list --porcelain, main = first record",
        },
    }

def _stub_shared_tree_rider(*, read_at: str, **_kw) -> dict:
    """A canned shared-tree rider for every probe that drives `main()` (#241).

    The real rider shells out three times against the tree the patrol runs in, so stubbing
    it is the same discipline the publish and worktree stubs exist for: a probe must not
    pay for live state it never asserts. The probes that DO assert the rider drive
    `render_shared_tree_rider` directly, or drive `main()` with this stub replaced so the
    render path is exercised rather than assumed.

    The default is an ASSERTED rider over an EMPTY tree — no blocking paths — so a probe
    that does not care about the rider still gets a well-formed one, and the probes that do
    pass their own.
    """
    return {
        "status": "ASSERTED",
        "read_at": read_at,
        "base": "origin/main",
        "base_sha": None,
        "dirty": [],
        "blocking": [],
        "reason": None,
        "reconciles": False,
    }

def _cron(name, *, deliver_to="", prompt="", home="probe-home") -> dict:
    return {"name": name, "deliver_to": deliver_to, "prompt": prompt, "home": home}

_SESSION_UUID = "359fe71b-c7a1-420b-b856-acfb49939a7b"

_WAKE_PROMPT = (
    "Thin trigger only. Run the command below, then report and exit. "
    "do NOT execute any project work yourself"
)

_NONE_DECL = "receipt_subject: none"

def _thin(name, *, prompt=None, **kw) -> dict:
    """A correctly-thin row: a session target whose prompt declares itself wake-only.

    `prompt` EXTENDS the wake-only prompt rather than replacing it, so a probe can add the
    content it is testing while the row stays correctly thin on the wake and marker legs —
    otherwise the content probe would trip the unrelated work-order leg and prove nothing
    about the class it names.
    """
    body = _WAKE_PROMPT if prompt is None else f"{_WAKE_PROMPT} {prompt}"
    return _cron(name, deliver_to=f"session:{_SESSION_UUID}",
                 prompt=f"{body}\n\n{_NONE_DECL}", **kw)

def _issue_with_comments(number: int, state: str, *bodies: str) -> dict:
    """A board issue carrying comments, in the shape `gh issue list --json` returns.

    The instants are STAGGERED by index, and that is a re-arm rather than tidiness: since
    #511 the leg judges the LATEST accepted comment, so two comments sharing one `createdAt`
    made the tie-break decide which act was judged — the first one, by the loop's own `<`
    comparison — and a fixture written to name the second read as unpaired. Real comments
    cannot share an instant; this one now cannot either.
    """
    issue = _issue(number, state)
    issue["comments"] = [
        {"body": body, "author": {"login": "hq"},
         "createdAt": _plus(_CLOSE_TS, (i - 1) * 0.1),
         "url": _comment_url(number, i)}
        for i, body in enumerate(bodies, start=1)
    ]
    return issue

_FAILURE = (
    "❌ transport_error: cannot reach the A2A gateway at http://127.0.0.1:18791/a2a/v1: "
    "error sending request for url (http://127.0.0.1:18791/a2a/v1) (exit 4)\n"
)

_RECEIPT = (
    "⚠️ deferred: deferred for session 6ca0d547-4a72-4c29-ac10-967daa98af0a: delivers once "
    "the session has been quiet for 20s (hard cap 30s) — notification id "
    "f50759ea-b25f-475b-9c48-319dfa73dd8c\n"
)

_DELIVERED = "✅ delivered: delivered to session fb67ca75-8735-4c39-80be-06b59bd4365f\n"

def _home_db(path: Path, *jobs) -> None:
    """A throwaway OpenCrabs home holding real cron rows — the read path, not a stub.

    The registry itself drives its floor law over a throwaway root for exactly this
    reason: a reader that has only ever run against the live box has not been shown to
    read what it claims. This probe builds the SHAPE the live box has (a default home
    beside a profile root) and reads it through the runner's own function.
    """
    conn = sqlite3.connect(path)
    conn.execute(
        "create table cron_jobs "
        "(id text, name text, deliver_to text, prompt text, enabled integer, "
        "last_run_at text)"
    )
    conn.executemany(
        "insert into cron_jobs (id, name, deliver_to, prompt, enabled) values (?,?,?,?,?)",
        jobs,
    )
    conn.commit()
    conn.close()

def _tier_row(n: int, subject: str, detail: str, event: str = "ruling") -> dict:
    """A ledger row carrying whatever `detail` says — trailer discipline is the caller's."""
    return {"n": n, "ts": _CLOSE_TS, "event": event, "actor": "hq",
            "subject": subject, "detail": detail}

_RECEIPT_PROMPT = (
    "Thin trigger only — do NOT execute any project work yourself. Call the "
    "session_notify tool exactly ONCE, then stop.\n\nreceipt_subject: registry-attest\n"
)

def _plus(literal: str, hours: float) -> str:
    """`literal` shifted by `hours`, in the ISO-8601 UTC form this tree stores."""
    t = dt.datetime.strptime(literal, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    return (t + dt.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")

def _tree_bound(key: str, fallback: str) -> str:
    """The instant THIS tree declares for `key`, or the kit's literal when it declares none."""
    try:
        reader = RUNNER.load_module("ledger_boundary", RUNNER.LEDGER_BOUNDARY)
        _instant, text = reader.declared_boundary(REPO, key)
        return text or fallback
    except Exception:  # noqa: BLE001 — an undeclared bound is the LEG's refusal to raise;
        return fallback

def _close_anchor() -> str:
    """The close-board gate's own anchor, as this tree declares it.

    Read through the same reader the leg uses (#428): the gate no longer carries the
    instant as a constant, because a boundary is factory data and this file ships into
    every member tree. The literal is only the fallback that keeps the probes runnable
    before adoption, and it is the same value the kit ships in the example declaration.
    """
    return _tree_bound("close_board_recorded", "2026-09-18T18:04:24Z")

_BOARD_BOUNDS = {
    "board_intake_recorded": "2026-09-19T00:00:00Z",
    "close_board_recorded": "2026-09-18T18:04:24Z",
}

def _board_scope(repo, key: str) -> tuple[str, str, str]:
    """The bound THIS tree declares for `key`, or the kit's literal when it declares none.

    The default for every probe that drives `main()`: it keeps the meaning those probes
    were written with in BOTH halves of this byte-identical pair — the adopting tree
    reads its own declaration, the shipped half falls back to the kit's literal — while a
    probe that asserts a pre-boundary, post-boundary, NOT RUN or REFUSED bound passes a
    `board_scope` of its own.
    """
    return _tree_bound(key, _BOARD_BOUNDS.get(key, "")), "", ""

def _duty_scope(repo) -> tuple:
    """The duty leg's bound, read from THIS tree (#487), as `(instant, text, refusal)`.

    The default for every probe that drives `main()`, and the reader `_DUTY_BOUND` below is
    derived from, so the probe's instants and the leg's bound can never resolve by two
    different paths -- the discipline `_board_scope` keeps for the three board legs. The kit's
    literal is only the fallback that keeps the probes runnable before adoption.
    """
    text = _tree_bound(RUNNER.DUTY_RECEIPT_BOUNDARY_KEY, "2026-09-25T07:01:07Z")
    return RUNNER.reader_parse_ts(text), text, ""

_DUTY_BOUND = _duty_scope(REPO)[1]

_DUTY_FIRE = _plus(_DUTY_BOUND, 0.5)

_DUTY_ROUND = _DUTY_FIRE[:10]

_RECEIPT_TS = _plus(_DUTY_BOUND, 1.0)

_DUTY_READ_AT = _plus(_DUTY_BOUND, 2.0)

_CLOSE_ANCHOR = _close_anchor()

_CLOSE_TS = _plus(_CLOSE_ANCHOR, 1.0)

_CLOSE_TS2 = _plus(_CLOSE_ANCHOR, 1.1)

_PRE_CLOSE_TS = _plus(_CLOSE_ANCHOR, -1.0)

def _duty_row(name="factory-registry-attest", *, prompt=_RECEIPT_PROMPT,
              last_run_at=_DUTY_FIRE,  # AFTER this tree's own #175 bound, see _DUTY_BOUND
              row_id="9ec28cec-100c-4325-ba3e-62972351ff0d") -> dict:
    return {
        "id": row_id, "name": name, "deliver_to": "", "prompt": prompt,
        "last_run_at": last_run_at, "home": "probe-home",
    }

def _fires(hours: tuple[float, ...], *, name: str = "factory-registry-attest",
           suppressed: bool = False) -> list[dict]:
    """Fire records for one job, on the instants named — the residual's population.

    `suppressed` writes the DAEMON's own wording into the record's `content` and derives the
    flag from it through the module's own reader, so a probe exercising #477 carries the same
    two fields the live source builds rather than a hand-set flag with no prose behind it.
    """
    content = (
        f"Trigger condition not met (exit_code=0, output_bytes=0). "
        f"{RUNNER.CRON_SUPPRESSION_MARKER}." if suppressed else ""
    )
    return [
        {"job_id": _duty_row()["id"], "job_name": name,
         "started_at": _plus(_DUTY_BOUND, h),
         "content": content,
         "suppressed": RUNNER.fire_is_suppressed(content)}
        for h in hours
    ]

def _duty_tree(*, invariants=None, declaration=None) -> Path:
    """A factory tree carrying exactly the bound the caller names — the P35 fixture.

    Reached through the RUNNER's own loader, so the probe and the leg resolve the boundary
    reader by ONE path: a second loader here would be a second predicate for one field.
    """
    reader = RUNNER.load_module("ledger_boundary", RUNNER.LEDGER_BOUNDARY)
    if declaration is None and invariants is None:
        invariants = {"duty_receipt_declared": _DUTY_BOUND}
    return reader.synthetic_tree(Path(tempfile.mkdtemp()), rows=[],
                                 invariants=invariants, declaration=declaration)

_DUTY_TREE = _duty_tree()

def _duty_leg(cron_rows, ledger_rows, *, store=None, repo=None,
              read_at=None, fires=None, margin_for=None, predicate=None,
              exemptions_fn=None) -> dict:
    return RUNNER.duty_receipt_leg(
        cron_rows, ["probe-home"], [], ["factory-"], ledger_rows,
        read_at=read_at if read_at is not None else _DUTY_READ_AT,
        store=store if store is not None else Path(tempfile.mkdtemp()),
        repo=repo if repo is not None else _DUTY_TREE,
        fires=fires, margin_for=margin_for, predicate=predicate,
        exemptions_fn=exemptions_fn,
    )

def _synthetic_kit(
    tmp: Path, *, files: dict[str, bytes], members: dict[str, dict],
    classes: dict[str, str] | None = None,
) -> tuple[Path, Path]:
    """A throwaway manifest + fleet pair over synthetic member trees.

    Returns (manifest_path, fleet_path). The member trees are built by the caller under
    `tmp`, so nothing here reads a live repository: the leg's population is five OTHER
    repos, and a probe that read them would be measuring whatever they happen to hold.

    `classes` is keyed by the SAME repo-relative spelling as `files` (no `TEMPLATE/`
    prefix) so a caller states the class once, beside the bytes it describes; the manifest
    gets the prefixed key the leg actually reads. Omitting it leaves the manifest carrying
    no `classes` map at all, which is the pre-#514 shape and the control arm's fixture.
    """
    import hashlib
    manifest = {"kit_version": "probe", "files": {}}
    for rel, body in files.items():
        path = tmp / "TEMPLATE" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        manifest["files"][f"TEMPLATE/{rel}"] = hashlib.sha256(body).hexdigest()
    if classes:
        manifest["classes"] = {f"TEMPLATE/{rel}": cls for rel, cls in classes.items()}
    mpath = tmp / "kit.json"
    mpath.write_text(json.dumps(manifest), encoding="utf-8")

    entries = []
    for slug, spec in members.items():
        root = tmp / slug
        root.mkdir(parents=True, exist_ok=True)
        for rel, body in (spec.get("same") or {}).items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        for rel, body in (spec.get("diff") or {}).items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        entries.append({"slug": slug, "repo": str(root)})
    fpath = tmp / "fleet.json"
    fpath.write_text(json.dumps({"factories": entries}), encoding="utf-8")
    return mpath, fpath

def _stub_publish_leg(*, read_at: str) -> dict:
    """A publish leg that reads NOTHING, for probes that drive `main()`.

    The real leg reads the remote (`git ls-remote`), so leaving it live would make every
    probe that drives `main()` perform a network call -- measured at ~2s each, which took
    this gate from 3s to 40s against a 17s budget. The file's own doctrine is that every
    dependency is injectable for exactly this reason: a probe must not measure the box.

    The leg's OWN behaviour is proved by the six probes below, which drive it directly
    against synthetic repositories.
    """
    return {
        "name": "publish-freshness",
        "status": "ASSERTED",
        "problems": [],
        "excused": [],
        "coverage": {"read_at": read_at, "stubbed": True, "unpushed": 0, "shas": [],
                     "stale": [], "remote": "origin", "branch": "main",
                     "remote_tip": None, "residual_secs": 22500},
    }

def _git(repo: Path, *args: str, env: dict | None = None) -> str:
    merged = dict(os.environ)
    merged.update(env or {})
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, env=merged, timeout=120
    )
    assert proc.returncode == 0, f"git {' '.join(args)}: {proc.stderr.strip()}"
    return proc.stdout.strip()

_499_FIRE_HOURS = (0.5, 4.5, 8.5, 12.5)

_499_ROUND = _plus(_DUTY_BOUND, 0.5)[:10]

_499_READ_AT = _plus(_DUTY_BOUND, 200.0)

# The skips THIS module's `_declared_skip` records. It lives here because the helper
# that appends to it does: a leg that defined its own list would leave every
# `_declared_skip` call raising NameError, which is exactly what the shipped-depth
# audit caught on the first run after the split (#602). The legs IMPORT this list
# rather than defining a second one, so `main()`'s skip count is the real count.
_SKIPS: list[str] = []

def _declared_skip(what: str, reason: str) -> None:
    """`ledger_boundary.py`'s third outcome: nothing to judge, stated, exit 0.

    Honoured in BOTH forms of this gate — pytest (a skip, not an error) and script (the
    reason printed, the run non-fatal). A `SkipGate` escaping as a traceback makes "this
    tree has nothing to judge" render exactly like "a check failed", which is the
    confusion this instrument exists to remove; a gate that cannot state its own skip is
    the gate failing at its own job.
    """
    line = f"{what}: {reason}"
    _SKIPS.append(line)
    print(f"  SKIP  {line}")
    pytest.skip(reason)

_500_FIRE_HOURS = (0.5, 4.5, 8.5, 12.5)

_500_READ_AT = _plus(_DUTY_BOUND, 200.0)

_SCRATCH_DIRS: list[Path] = []

def _scratch() -> Path:
    """A fresh scratch directory for a probe (#242).

    The SCRIPT runner in this file calls every `test_*` with NO arguments, so a probe must
    never take `tmp_path` — pytest supplies it and the script form does not, which is how a
    probe that passes under pytest raises TypeError under the audit's own invocation. The
    house style here is to create the directory inside the probe.
    """
    d = Path(tempfile.mkdtemp(prefix="patrol-probe-"))
    _SCRATCH_DIRS.append(d)
    return d

_OWES_NONE_PROMPT = (
    "Thin trigger only — do NOT execute any project work yourself. Run the pusher, then "
    "stop.\n\nreceipt_subject: none\n"
)

_RULING_BOUND = _tree_bound(RUNNER.RULING_BOUNDARY_KEY, "2026-10-02T18:07:38Z")

_RULING_PRE = _plus(_RULING_BOUND, -2.0)

_RULING_POST = _plus(_RULING_BOUND, 2.0)

def _stall_row(n, event, subject, days_ago, *, actor="hq", detail="probe", refs=None,
               now=None):
    """A ledger row dated RELATIVE to the read clock.

    The leg ages a row against `read_at`, so a hardcoded instant would make every probe
    below a statement about the day it was written. Relative instants keep the fixture a
    statement about the THRESHOLD, which is the property under test.
    """
    stamp = (now - dt.timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"n": n, "ts": stamp, "event": event, "actor": actor, "subject": subject,
            "detail": detail, "refs": refs}

_PRESENCE_REGISTER = (
    "| Process | Process Owner | Process Client |\n"
    "|---|---|---|\n"
    "| **1. Work Delivery Pipeline** | HQ | Owner |\n"
    "| **2. Rework Prevention** | Triage | HQ |\n"
    "| **3. Operational Measurement** | Surveys | Owner |\n"
)

_PRESENCE_FRAGMENT = {
    "lanes": [
        {"role": "hq", "thread_id": 21},
        {"role": "triage", "thread_id": 20},
        {"role": "surveys", "thread_id": 19},
    ]
}

_PRESENCE_BINDINGS = [
    {"thread_id": 21, "session_id": "U-HQ", "chat_id": "-100", "_profile": "ops",
     "updated_at": 3},
    {"thread_id": 20, "session_id": "U-TRIAGE", "chat_id": "-100", "_profile": "ops",
     "updated_at": 3},
    {"thread_id": 19, "session_id": "U-SURVEYS", "chat_id": "-100", "_profile": "ops",
     "updated_at": 3},
]

class _StubRegistry:
    """The two members `owner_sessions` uses: the factory's chat, and lane resolution."""
    FACTORY_CHATS = {"meta-factory": -100}

    def resolve_lane(self, lane, bindings, topic_names, chat_id=None):
        for b in bindings:
            if b.get("thread_id") == lane.get("thread_id"):
                return {"session_id": b.get("session_id"), "status": "resolved"}
        return {"session_id": None, "status": "unbound"}

def _delivery(instant: dt.datetime, text: str, *, state: str = "landed",
              session: str = "probe-session") -> dict:
    """A delivered-notify row as `box_deliveries` emits it.

    `session` is the TARGET the notify was addressed to, and it is load-bearing since #425
    clause 1: the leg corroborates a dispatch row only against a delivery whose target IS the
    row's own typed `session` ref, so a fixture that omitted the target would assert a leg
    that matches on subject alone -- the exact subject-only match the clause forbids.
    """
    return {"home": "probe-home", "session": session,
            "epoch": int(instant.timestamp()), "state": state, "text": text}

_PROBE_TARGET = "probe-session"

def _git_init(root: Path) -> Path:
    """`root` as a real repository with its OWN identity, never the box's (#450)."""
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "probe@example.invalid")
    _git(root, "config", "user.name", "probe")
    return root

def _criterion_tree(*paths: str) -> Path:
    """A throwaway REPOSITORY holding exactly the named paths IN ITS COMMITTED TREE.

    It must be a repository, not a directory holding files (#450): the leg reads the tree at
    the reading REVISION, so a fixture that merely wrote files would prove nothing about the
    verdict a reader reproduces — and a plain directory would now read NOT RUN, turning
    every probe in this block into an instrument failure. The paths are COMMITTED, so the
    commit is the one thing that decides.
    """
    root = _git_init(Path(tempfile.mkdtemp(prefix="criterion-tree-")))
    for rel in paths:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("probe\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "--allow-empty", "-m", "probe tree")
    return root

def _score_artifact(*, total: int, cells: list[str], name: str = "Probe factory") -> str:
    """One survey artifact in the shape `scorecard_blocks` parses.

    The criteria row must OPEN with `| D1 |` -- that is the anchor `_SCORECARD_CRITERIA_RE`
    matches, and it is the shape the live artifacts carry. A fixture that merely mentioned
    the criteria would parse as ZERO blocks, and every probe below would then assert a NOT
    RUN verdict while appearing to assert a regression one.
    """
    header = " | ".join(f"D{i + 1}" for i in range(len(cells)))
    body = " | ".join(cells)
    return (
        "## Detailed Factory Scorecards\n\n"
        f"### 1. {name} — {total} / 76\n\n"
        f"| {header} |\n"
        "|" + "---:|" * len(cells) + "\n"
        f"| {body} |\n"
    )

def _scores_dir(newest: str, previous: str | None = None) -> Path:
    """A throwaway scores surface: the leg reads the NEWEST artifact and the one before it."""
    root = Path(tempfile.mkdtemp(prefix="probe-scores-"))
    if previous is not None:
        (root / "2026-10-09.md").write_text(previous, encoding="utf-8")
    (root / "2026-10-10.md").write_text(newest, encoding="utf-8")
    return root

def _conversion_row(source: str, *, subject: str = "#67") -> dict:
    """The row shape the ledger's own write path accepts for a `conversion` event."""
    return {
        "n": 9001, "ts": _CLOSE_TS, "event": "conversion", "actor": "worker",
        "subject": subject, "detail": f"converted_from={source}",
    }

def _non_conversion_row() -> dict:
    """A row that is IN the population without being a `conversion` event.

    The artifact-side probes below used to pass `[]` as a stand-in population. Since #472
    an empty row list is NOT RUN, so the stand-in must be a POPULATED list carrying no
    `conversion` event: the join still finds nothing answering the round -- which is the
    state those probes assert -- and the empty-population path keeps its own probe.
    """
    return {
        "n": 9002, "ts": _CLOSE_TS, "event": "run", "actor": "worker",
        "subject": "probe", "detail": "no conversion declared here",
    }

def _scores_tree(artifacts: dict[str, str]) -> Path:
    """A throwaway scores surface carrying EXACTLY the dated artifacts named.

    `_scores_dir` writes a fixed pair; the lapsed arms need a third round to prove that a
    round which is neither the newest nor its predecessor is still read.
    """
    root = Path(tempfile.mkdtemp(prefix="probe-scores-"))
    for date, text in artifacts.items():
        (root / f"{date}.md").write_text(text, encoding="utf-8")
    return root

def main() -> int:
    checks = [value for name, value in sorted(globals().items())
              if name.startswith("test_") and callable(value)]
    failures: list[str] = []
    for check in checks:
        try:
            check()
        except pytest.skip.Exception:
            # `_declared_skip` already printed the reason and recorded it: a declared
            # skip is not a failure and must never abort the run around it.
            continue
        except AssertionError as exc:
            failures.append(f"{check.__name__}: {exc}")
            print(f"  FAIL  {check.__name__} — {exc}")
        else:
            print(f"  PASS  {check.__name__}")
    print()
    if failures:
        print(f"patrol-runner gate FAILED: {len(failures)} check(s)")
        return 1
    ran = len(checks) - len(_SKIPS)
    skipped = f", {len(_SKIPS)} SKIPPED (nothing to judge)" if _SKIPS else ""
    print(f"patrol-runner gate passed: {ran} check(s){skipped}")
    return 0

_BACKTICKED_DECL_PROMPT = (
    "Thin trigger only — do NOT execute any project work yourself. Run the pusher, then "
    "stop.\n\n`receipt_subject: none` — the cron stamps no ledger row; the receipt is the "
    "file.\n"
)

_UNDECLARED_PROMPT = (
    "Thin trigger only — do NOT execute any project work yourself. Wake the lane, then "
    "stop.\n"
)

_GOAL_CREATED = "2026-10-01T00:00:00+00:00"

def _goal_store(*rows, unreached=(), without_store=()):
    return {"rows": list(rows), "homes_read": ["probe-home"],
            "homes_without_store": list(without_store), "unreached": list(unreached)}

def _activity_store(*, work=None, readable=True, reason="", unreached=(),
                    without_store=()):
    """One injected `box_lane_activity` payload (#532).

    `work` maps a session id to the ISO instant of its newest measured tool execution. The
    DEFAULT IS A READ SOURCE WITH NO WORK, which is the pre-#532 reading: a probe that does not
    care about activity gets exactly the behaviour the leg had before the fourth reading, and
    one that does care must say so. A probe that could get a live-box answer by omission would
    be decided by whichever lane this box happened to be running.
    """
    work = dict(work or {})
    epochs = {}
    for session_ref, instant in work.items():
        epochs[session_ref] = int(
            dt.datetime.fromisoformat(instant.replace("Z", "+00:00")).timestamp()
        )
    return {
        "readable": readable,
        "reason": reason,
        "newest": work,
        "epochs": epochs,
        "homes_read": ["probe-home"] if readable else [],
        "homes_without_store": list(without_store),
        "unreached": list(unreached),
        "unparsed": [],
    }

def _completion_store(*, finished=None, readable=True, reason="", unattributed=0,
                      unparsed=(), without_store=()):
    """One injected `box_lane_completions` payload (#624).

    `finished` maps a session id to the ISO instant of its newest `close` row. THE DEFAULT IS A
    READ LEDGER WITH NO CLOSES, which is the honest reading for a probe that does not care about
    completion: a lane with measured activity then reads UNARMED-BUSY rather than the
    UNARMED-ACTIVE it used to get for free, because "executed a tool" was never evidence of
    "finished a unit". A probe that wants the draining reading must SAY a unit closed -- the same
    discipline as `_activity_store`, one fact over, so a verdict can never be decided by this
    box's own close history.
    """
    finished = dict(finished or {})
    epochs = {}
    for session_ref, instant in finished.items():
        epochs[session_ref] = int(
            dt.datetime.fromisoformat(instant.replace("Z", "+00:00")).timestamp()
        )
    return {
        "readable": readable,
        "reason": reason,
        "newest": finished,
        "epochs": epochs,
        "rows_read": len(finished),
        "close_rows": len(finished),
        "unattributed": unattributed,
        "unparsed": list(unparsed),
        "homes_read": ["probe-home"] if readable else [],
        "homes_without_store": list(without_store),
        "unreached": [],
    }

_NOW = dt.datetime(2026, 10, 21, 12, 0, 0, tzinfo=dt.timezone.utc)

_ROW_SET_CLEAN_CLAIMS = (
    "no registration carries a row the base does not",
    "no registration is ahead of",
    "no STRANDED commit",
    "no LOSS RISK registration",
)

_LIVE_MENTION_COINCIDENCES = {
    # unit -> (dispatch subject, dispatch detail). The SHAPES are verbatim from the live rows
    # the #556 ruling measured (read_at 2026-10-24T06:52-06:59Z, 4,207 rows, 556 board
    # items). These FOUR carry an ISSUE reference -- the `#NNN` form, or a bare digit that no
    # prefix claims -- so they stay in the mention class and the leg still prints what they
    # matched and where.
    549: ("#529", "the four lanes named #549 as the unit to route next"),
    550: ("#324", "row #550 carries the same shape as #324"),
    # `max 553.73 h` is the ONE coincidence #534 does NOT refuse: its boundary is a DECIMAL
    # point, not a row or file prefix, and the token's boundary discipline is a separate
    # question (#49/#425). It stays a mention, and it stays visible.
    553: ("#527", "the window measured max 553.73 h across the fleet"),
    555: ("#336", "the Owns: header round (#555) closed at 06:25Z"),
}

_LIVE_REFUSED_COINCIDENCES = {
    548: ("kit-defect-cluster-2026-10-20T15",
          "the cluster is recorded at docs/instruments/kit.md:548 in the tree"),
    554: ("#87", "ruling n=554 set the pace for the round"),
    556: ("#189", "the flag reads _LOG_ENABLED = False at :556"),
}

_ALL_LIVE_COINCIDENCES = {**_LIVE_MENTION_COINCIDENCES, **_LIVE_REFUSED_COINCIDENCES}

_ROUTING_TS = "2026-10-29T00:00:00Z"

