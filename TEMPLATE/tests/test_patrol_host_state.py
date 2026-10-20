#!/usr/bin/env python3
"""Gate: the patrol runner feeds LIVE state to the pure predicate, and says what it examined.

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

REPO = Path(__file__).resolve().parent.parent
RUNNER_PATH = REPO / "tools" / "patrol_host_state.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("patrol_host_state", RUNNER_PATH)
    assert spec and spec.loader, f"cannot load {RUNNER_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner()

# One EMPTY log surface per process, not one per probe. The notify-receipt leg's default
# surface is the live `/tmp` — which is exactly the directory a per-call temp dir would
# leak into, and this leg SCANS that directory. A probe that emptied 15 directories into
# the surface under test would be feeding its own fixtures to the next run.
_EMPTY_LOG_DIR = Path(tempfile.mkdtemp(prefix="patrol-empty-log-"))

# One EMPTY scores surface per process, for the same reason and one sharper one (#67): the
# score-conversion leg reads the NEWEST `evidence/scores/<date>.md` in the LIVE tree, so a
# probe that did not inject a directory would have its verdict decided by this factory's own
# latest survey -- and, once the leg was wired in, EVERY probe driven through `_run` would
# read red for a reason none of them names. An empty directory reads NOT RUN with its stated
# reason, which leaves every pre-#67 probe with the meaning it was written with.
_EMPTY_SCORES_DIR = Path(tempfile.mkdtemp(prefix="patrol-empty-scores-"))

# A path under a fresh temp dir that is deliberately NEVER created: the board-ruling leg's
# exemption table defaults to it, so a probe that does not pass a table of its own cannot
# have its verdict decided by the exemptions the LIVE factory happens to hold (issue #334).
_NO_RULING_EXEMPTIONS = (
    Path(tempfile.mkdtemp(prefix="patrol-no-exempt-")) / "ruling-board-exemptions.json"
)

# The ref-role leg's exemption store (#330) defaults to a path that is NEVER created, for
# the reason `_NO_RULING_EXEMPTIONS` sets and one of its own: the store ships ABSENT in the
# kit's donor half, so a probe that read the live factory's store would be asserting this
# box's own adjudications rather than the leg's behaviour -- and a probe whose synthetic
# rows happened to match a live triple would be silently excused by an entry it never wrote.
_NO_REF_ROLE_EXEMPTIONS = (
    Path(tempfile.mkdtemp(prefix="patrol-no-ref-roles-")) / "ledger-ref-roles-exemptions.json"
)

# The criterion-path leg's exemption store (#507) defaults to a path that is NEVER created,
# for the reason `_NO_REF_ROLE_EXEMPTIONS` sets and one sharper one: the leg now reports an
# entry that matches NO live absence as a PROBLEM, so a probe driven through `_run` against
# the LIVE store would red on every probe's synthetic board — the store's real entries name
# paths no probe's fixture mentions. Defaulting to an absent path keeps every pre-#507 probe
# at the meaning it was written with, and a probe that asserts the store passes its own.
_NO_CRITERION_EXEMPTIONS = (
    Path(tempfile.mkdtemp(prefix="patrol-no-criterion-"))
    / "criterion-path-exemptions.json"
)

# The driverless-lane leg's goal store (#133) defaults to an EMPTY STORE THAT WAS READ, not to
# the live one and not to an unreachable one. Both halves matter: reading the live `goal_state`
# would decide a probe's verdict with whichever convergence loops THIS box happens to be
# running, and defaulting to an UNREACHED store would be worse still — it would make every lane
# read DRIVERLESS for want of a read, so a probe asserting a clean round would red for a reason
# it never named. `homes_read` is populated precisely so the default is distinguishable in the
# output from a store nobody could open.
_EMPTY_GOAL_STORE = {
    "rows": [],
    "homes_read": ["probe-home"],
    "homes_without_store": [],
    "unreached": [],
}

# The stall-census leg's park clause (#331) needs NO injection point, and that is the point:
# a park is declared by a `park:owner:<question>` line on the unit's OWN ledger row, so the
# rows a probe already passes ARE the declaration. A probe that declares no park therefore
# reads none, and every probe written before the clause existed keeps its meaning without
# being touched — there is no live table a probe could accidentally read.

# The criterion-path leg (#48) resolves a board criterion's named paths against the TREE AT
# THE READING REVISION (#450, template-instruments.md §7.5) — never a working tree, which moves under the reader and
# puts a peer's in-flight file into the verdict. The default for a probe is therefore an
# EMPTY REPOSITORY: a probe that supplies no tree of its own reads every named path as
# ABSENT, so it cannot pass by accidentally finding a live file — and it cannot read as NOT
# RUN either, which a plain directory would now be, since a directory has no commit to read.
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
         driverless_turn_open=None):
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


def test_repo_slug_reads_both_remote_forms() -> None:
    """The slug decides WHICH board is read; a wrong slug reads a wrong board clean."""
    assert RUNNER.repo_slug("git@github.com:leshchenko1979/agent-factories.git") == \
        "leshchenko1979/agent-factories"
    assert RUNNER.repo_slug("https://github.com/owner/repo.git") == "owner/repo"
    assert RUNNER.repo_slug("https://github.com/owner/repo") == "owner/repo"
    assert RUNNER.repo_slug("git@github.com:o/r\n") == "o/r", "trailing newline must not leak"


def test_repo_slug_refuses_a_remote_it_cannot_parse() -> None:
    """A non-github remote must FAIL, never degrade to a silently wrong slug."""
    for bad in ("", "https://gitlab.com/o/r.git", "not a url"):
        try:
            RUNNER.repo_slug(bad)
        except RUNNER.BoardReadError:
            continue
        raise AssertionError(f"repo_slug accepted {bad!r}")


def test_the_board_is_fetched_whole_never_filtered() -> None:
    """The reverse leg is sound only over the FULL board, so the argv must say so."""
    captured: dict = {}

    class _Proc:
        returncode = 0
        stdout = "[]"
        stderr = ""

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _Proc()

    with mock.patch.object(RUNNER.subprocess, "run", _fake_run):
        RUNNER.fetch_board("owner/repo")

    cmd = captured["cmd"]
    assert "--state" in cmd, cmd
    assert cmd[cmd.index("--state") + 1] == "all", (
        f"the board must be read in every state, not filtered: {cmd}"
    )
    assert "--limit" in cmd, cmd
    assert "--json" in cmd, cmd
    assert "state" in cmd[cmd.index("--json") + 1], cmd


def test_a_non_empty_board_with_a_missing_leg_is_reported() -> None:
    """#95's own acceptance: a non-zero forward count when the board is non-empty."""
    issues = [_issue(1, "OPEN"), _issue(2, "OPEN"), _issue(3, "CLOSED")]
    rows = _rows(("intake", "#1", 1), ("intake", "#3", 2))
    rc, out, _ = _run(issues, rows)
    assert rc == 1, f"a missing intake leg must fail the run, got rc={rc}\n{out}"
    assert "#2 is OPEN on the board with no intake row" in out, out
    assert "2 examined" in out, f"the forward coverage count must be printed\n{out}"
    assert "0 problem(s)" not in out.split("forward")[1].split("\n")[0], (
        "the forward leg examined a non-empty board and must not read zero problems"
    )


def test_a_clean_board_reads_clean_and_STATES_ITS_COVERAGE() -> None:
    """Non-vacuity: a green must be green over a NON-ZERO examined count."""
    issues = [_issue(1, "OPEN"), _issue(2, "OPEN"), _issue(3, "CLOSED")]
    # The `ruling` rows are not decoration: since #332 the patrol also asserts the ROUND's
    # own predicate (an OPEN item with an intake row and no ruling row is a miss), so a
    # fixture that models a clean board must be a board the round has SWEPT.
    rows = _rows(
        ("intake", "#1", 1), ("ruling", "#1", 5),
        ("intake", "#2", 2), ("ruling", "#2", 6),
        ("intake", "#3", 3), ("close", "#3", 4),
    )
    rc, out, _ = _run(issues, rows)
    assert rc == 0, f"a fully intaken board must pass, got rc={rc}\n{out}"
    assert "2 examined" in out, f"the clean verdict must name what it examined\n{out}"
    assert "asserted over the FULL board" in out, out
    assert "0 problem(s) over 2 open issue(s) examined" in out, out


def test_a_board_that_could_not_be_read_is_not_a_clean_board() -> None:
    """The failure mode that makes a patrol worse than useless: broken read, green verdict."""

    def _boom(slug):
        raise RUNNER.BoardReadError("gh issue list failed (rc=1): not authenticated")

    out, err = io.StringIO(), io.StringIO()
    rc = RUNNER.main(
        [],
        board_fn=_boom,
        slug_fn=lambda: "owner/repo",
        rows_fn=lambda: [],
        out=lambda *a, **k: print(*a, file=out, **k),
        err=lambda *a, **k: print(*a, file=err, **k),
        publish_fn=_stub_publish_leg,
        shared_tree_fn=_stub_shared_tree_rider,
        # #133: the driverless-lane leg's goal store and its turn-in-flight read are
        # injected here for the same reason every other live surface is -- and the
        # defaults WITHHOLD the driven claim (empty store, no turn open) rather than
        # granting one, so a probe that never asserts a driver cannot read one.
        driverless_goals_fn=lambda: _EMPTY_GOAL_STORE,
        driverless_turn_open_fn=lambda: {},
        # #330: the ref-role store is injected for the same reason the ruling table is.
        ref_role_exemptions_path=_NO_REF_ROLE_EXEMPTIONS,
        # #507: the criterion-path store, injected for the same reason.
        criterion_exemptions_fn=lambda: _NO_CRITERION_EXEMPTIONS,
    )
    assert rc == 2, f"an unreadable board must exit 2, got rc={rc}"
    assert "FAILED" in err.getvalue(), err.getvalue()
    assert "not authenticated" in err.getvalue(), err.getvalue()
    assert "verdict" not in out.getvalue(), (
        "an unreadable board must emit NO verdict at all — a verdict over zero issues "
        f"reads as a clean patrol\n{out.getvalue()}"
    )


# --- #121: the cron-thinness leg, WIRED -----------------------------------------

def _cron(name, *, deliver_to="", prompt="", home="probe-home") -> dict:
    return {"name": name, "deliver_to": deliver_to, "prompt": prompt, "home": home}

_SESSION_UUID = "359fe71b-c7a1-420b-b856-acfb49939a7b"
_WAKE_PROMPT = (
    "Thin trigger only. Run the command below, then report and exit. "
    "do NOT execute any project work yourself"
)

# The receipt disposition a wake-only row declares (#506). Every `_thin`/`_notify_row`
# fixture carries it for the reason their own docstrings give: a probe must not red an
# unrelated leg, or its exit code stops being attributable to the defect under test.
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

def _ledger_with(*subjects) -> Path:
    """A synthetic ledger in a temp dir — the guard is checked against DATA, not the live log."""
    path = Path(tempfile.mkdtemp()) / "ledger.jsonl"
    path.write_text(
        "".join(
            json.dumps({"n": i + 1, "ts": _CLOSE_TS, "event": "close",
                        "actor": "worker", "subject": s, "detail": "probe"}) + "\n"
            for i, s in enumerate(subjects)
        ),
        encoding="utf-8",
    )
    return path

def test_the_cron_leg_RUNS_and_states_the_population_it_examined() -> None:
    """#121: the leg is wired, and every count it reports travels with its scope.

    Ownership is the manifest's DECLARATION, never the home a row sits in — all twelve
    ai-antispam rows sit in the OPS home, so a home-scoped read answers a narrower
    question than the one it names (#102).
    """
    rows = [
        _thin("factory-triage-patrol"),
        _thin("factory-measurement-daily", home="other-home"),
        _thin("sibling-triage-hourly-patrol", home="other-home"),
    ]
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home", "other-home"],
                      unreached=["gone-home: no opencrabs.db"], prefixes=["factory-"])
    assert rc == 0, out
    assert "LEG cron-thinness — ASSERTED" in out, (
        f"the leg is WIRED: it must render ASSERTED, never a deferred NOT RUN\n{out}"
    )
    assert "3 enabled read across 2 home(s)" in out, out
    assert "2 attributed to this factory (factory-)" in out, out
    assert "1 attributed to nobody" in out, (
        f"a row nobody declares is COUNTED, and the count must be printed\n{out}"
    )
    assert "homes unreached: 1" in out, out
    assert "gone-home" in out, (
        f"an unreached home is REPORTED, never dropped — an unreachable home is not an "
        f"empty one\n{out}"
    )
    assert "read at " in out, f"the read instant must travel with the count\n{out}"

def test_the_cron_leg_fails_LOUDLY_when_nothing_is_attributed() -> None:
    """A clean verdict over an examined-nothing read is not a verdict (skill section 8).

    The declared prefix set is non-empty and NOTHING matches it, so the population the
    leg claims to judge came back empty — reported, never read as clean.
    """
    rows = [_thin("sibling-triage-hourly-patrol")]
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home"], prefixes=["factory-"])
    assert rc == 1, f"an empty attributed population must FAIL LOUDLY, got rc={rc}\n{out}"
    assert "population came back EMPTY" in out, out
    assert "0 cron row(s) attributed to this factory" in out, out

def test_an_unattributable_row_is_COUNTED_NAMED_and_never_judged() -> None:
    """A row this factory cannot attribute is COUNTED, NAMED, never judged.

    The second row carries a WORK ORDER on a waking session target — a real defect under
    the shared predicate — but nobody here declares it, so judging it would be this
    factory enforcing another factory's law.

    NAMED is the half that used to be forbidden here. A bare count is not a report: the
    name and the home it was read from are what let a reader resolve it, so the population
    read carries them (#126). The property this probe tests is the one it always claimed —
    the row is never JUDGED — and it still bites, because a row that reached the problems
    list would fail the second assertion.
    """
    rows = [
        _thin("factory-triage-patrol"),
        _cron("sibling-some-other-factory-job", deliver_to=f"session:{_SESSION_UUID}",
              prompt="Execute the hourly cycle and write the report.", home="other-home"),
    ]
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home", "other-home"],
                      prefixes=["factory-"])
    assert rc == 0, f"an unattributable row must not fail this factory's run\n{out}"
    assert "1 attributed to nobody" in out, out
    assert "    unattributed: sibling-some-other-factory-job (home other-home)" in out, (
        f"the population read must NAME every row it could not attribute, with the home "
        f"it was read from — a count alone resolves to no object and cannot be checked "
        f"by the reader it is reported to (#126)\n{out}"
    )
    judged = [line for line in out.splitlines() if line.startswith("    - ")]
    assert not any("sibling-some-other-factory-job" in line for line in judged), (
        f"the leg judges its OWN rows only — an unattributable row belongs in the "
        f"population read, never in this factory's problems\n{judged}\n{out}"
    )

def test_the_cron_leg_BITES_on_a_defect_in_a_row_this_factory_declares() -> None:
    """Non-vacuity: the wired leg must report a defect, not merely render a green line."""
    rows = [
        _thin("factory-triage-patrol"),
        _cron("factory-broken-pacemaker", deliver_to=f"session:{_SESSION_UUID}",
              prompt="Execute the 6-hourly cycle and write the report."),
    ]
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home"], prefixes=["factory-"])
    assert rc == 1, f"a work order on a waking row must fail the run, got rc={rc}\n{out}"
    assert "factory-broken-pacemaker" in out, out
    assert "work order" in out, out
    assert "2 cron row(s) attributed to this factory and judged" in out, (
        f"the verdict must state the judged population\n{out}"
    )

def test_the_law_content_class_NAMES_every_row_and_states_its_population() -> None:
    """#178: the class NAMES each row, never a bare count, and prints the population read.

    A count cannot be dispatched, claimed or closed; a named row can be all three (#148).
    The row below belongs to ANOTHER factory, and the leg still names it — because a
    per-factory scan would see none of the class's live instances and would report a clean
    verdict over the class it exists to catch (the #170/#177 family).
    """
    rows = [
        _thin("factory-triage-patrol"),
        _thin("sibling-other-factory-window",
              prompt=_WAKE_PROMPT + " The window from the deploy (2026-09-24T11:33:19Z) "
                                   "has passed.", home="other-home"),
    ]
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home", "other-home"],
                      prefixes=["factory-"])
    assert rc == 0, (
        f"another factory's row must not fail THIS factory's run — the class is reported "
        f"for rows this factory does not declare (#101)\n{out}"
    )
    assert "law-content scan: 2 row(s) examined" in out, (
        f"the population examined must be printed, so a clean verdict is distinguishable "
        f"from one that examined nothing\n{out}"
    )
    assert "law content: sibling-other-factory-window" in out, (
        f"the row must be NAMED, with the instant it embeds\n{out}"
    )
    assert "2026-09-24T11:33" in out, out

def test_the_law_content_class_BITES_on_a_row_this_factory_declares() -> None:
    """Non-vacuity: the class must FAIL the run when the row carrying it is ours."""
    rows = [
        _thin("factory-triage-patrol"),
        _thin("factory-boundary-holder",
              prompt=_WAKE_PROMPT + " Pool-swap boundary: 2026-09-25T16:17:46Z. The pool is "
                                   "now model-a:free + model-b:free."),
    ]
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home"], prefixes=["factory-"])
    assert rc == 1, f"an embedded boundary on our own row must fail the run, got rc={rc}\n{out}"
    assert "factory-boundary-holder" in out, out
    assert "2026-09-25T16:17" in out, out
    assert "P7/P28" in out, (
        f"the finding must name the rule that would have prevented it, per #148 — the "
        f"repairer is named, not counted\n{out}"
    )

def test_a_bare_date_is_REPORTED_and_never_judged_so_the_exclusion_is_visible() -> None:
    """A bare date is a CITATION of the past, not state — printed, never judged.

    This is the half that keeps the exclusion checkable: a reader can see WHICH rows were
    set aside and why, instead of trusting a silent predicate.
    """
    rows = [
        _thin("factory-triage-patrol"),
        _thin("factory-thin-exemplar",
              prompt=_WAKE_PROMPT + " This prompt is thin: it was 5,289 chars of pasted law "
                                   "on 2026-09-26, every word of which already lived in "
                                   "triage.md."),
    ]
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home"], prefixes=["factory-"])
    assert rc == 0, (
        f"a historical rationale carrying a bare date is not embedded state\n{out}"
    )
    assert "dated, not a boundary: factory-thin-exemplar" in out, (
        f"the row must be REPORTED with its date — an exclusion that prints nothing is "
        f"indistinguishable from a predicate that never looked\n{out}"
    )
    judged = [line for line in out.splitlines() if line.startswith("    - ")]
    assert not any("factory-thin-exemplar" in line for line in judged), (
        f"a bare date must never reach the problems list\n{judged}\n{out}"
    )

def test_the_negative_control_BITES_a_date_only_predicate_would_fire_on_the_exemplar() -> None:
    """The control is not vacuous, and this is the measurement that chose the predicate.

    Widening the class to a BARE DATE makes the box's best-shaped row a defect: the
    exemplar explains its own thinness using a date. A predicate that fires on the exemplar
    is one a reader learns to ignore, so the instant (date WITH a time) is the predicate and
    this probe is the evidence for it — it fails if the control cannot fire at all.
    """
    rows = [
        _thin("factory-triage-patrol"),
        _thin("factory-thin-exemplar",
              prompt=_WAKE_PROMPT + " It was 5,289 chars of pasted law on 2026-09-26, every "
                                   "word of which already lived in triage.md."),
    ]
    saved = RUNNER.EMBEDDED_INSTANT_RE
    try:
        RUNNER.EMBEDDED_INSTANT_RE = RUNNER.BARE_DATE_RE
        rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home"], prefixes=["factory-"])
        assert rc == 1, (
            f"the control must BITE: a date-only predicate fires on the exemplar, which is "
            f"exactly why the shipped predicate is an INSTANT\n{out}"
        )
    finally:
        RUNNER.EMBEDDED_INSTANT_RE = saved
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home"], prefixes=["factory-"])
    assert rc == 0, f"the shipped predicate must not fire on the exemplar\n{out}"

def test_the_leg_binds_to_the_SHARED_predicate_and_the_shared_registry() -> None:
    """One predicate, one home — imported, never re-derived.

    A private copy would be self-consistent on both sides and the drift invisible: the
    class this factory has already ruled (n=405 clause 5, n=599).
    """
    assert RUNNER.CRON_THINNESS_PREDICATE == REPO / "tests" / "test_cron_thinness.py", (
        f"the leg must bind to the shared predicate, not {RUNNER.CRON_THINNESS_PREDICATE}"
    )
    predicate = RUNNER.load_module("cron_thinness_predicate", RUNNER.CRON_THINNESS_PREDICATE)
    assert callable(predicate.pacemaker_problems), "the shared entry point must exist"
    assert RUNNER.REGISTRY == REPO / "tools" / "registry.py", (
        f"the box read must use the registry the 6h-floor law already uses, "
        f"not {RUNNER.REGISTRY}"
    )
    assert hasattr(RUNNER, "DEFERRED_LEG_REASON") is False, (
        "the cron-thinness reason must be DELETED, not corrected — a corrected reason is "
        "still a hand-written claim about the tree that nothing re-checks"
    )

# --- #121: the CLASS GUARD — a deferral's claims are checked, never trusted ---------

def test_nothing_is_deferred_now_that_the_cron_leg_is_wired() -> None:
    """Wiring the leg retires the REASON, and an empty list is the honest state."""
    assert RUNNER.deferred_legs() == [], (
        f"the cron-thinness leg is WIRED, so nothing may still be deferred: "
        f"{RUNNER.deferred_legs()}"
    )

def test_a_deferred_entry_with_a_CLOSED_tracker_is_reported() -> None:
    """THE BITE. A reader following a closed tracker lands on a settled item.

    This is the exact shape #121 found: the reason pointed at #54, and #54 had closed
    under it while every gate stayed green. The guard's live population is legitimately
    EMPTY, so THIS probe is the evidence that it bites (skill section 8).
    """
    entries = [{"name": "some-future-leg", "tracker": 54,
                "claims": [{"path": "tools/registry.py", "present": True}]}]
    problems = RUNNER.deferred_entry_problems(entries, ledger=_ledger_with("#54"))
    assert problems, "a CLOSED tracker must be reported"
    assert any("CLOSED" in p for p in problems), problems
    assert any("#54" in p for p in problems), problems

def test_a_deferred_entry_with_a_FALSE_claim_is_reported() -> None:
    """THE BITE, second arm: a stated reason must not outlive the tree it describes."""
    entries = [{"name": "some-future-leg", "tracker": 121,
                "claims": [{"path": "tools/registry.py", "present": True},
                           {"path": "tools/does-not-exist.py", "present": True}]}]
    problems = RUNNER.deferred_entry_problems(entries, ledger=_ledger_with())
    assert problems, "a claim the tree contradicts must be reported"
    assert any("tools/does-not-exist.py" in p for p in problems), problems

def test_a_truthful_deferral_reads_clean() -> None:
    """The complement: the guard is not a wall — a truthful entry is not a problem."""
    entries = [{"name": "some-future-leg", "tracker": 121,
                "claims": [{"path": "tools/registry.py", "present": True},
                           {"path": "tools/nope.py", "present": False}]}]
    assert RUNNER.deferred_entry_problems(entries, ledger=_ledger_with()) == [], (
        "a truthful deferral must read clean"
    )

def test_a_deferral_declaring_nothing_checkable_is_reported() -> None:
    """The CLOSED vocabulary is the point: free prose cannot be re-checked."""
    problems = RUNNER.deferred_entry_problems([{"name": "vague-leg", "reason": "later"}],
                                             ledger=_ledger_with())
    assert len(problems) >= 2, problems
    assert any("tracker" in p for p in problems), problems
    assert any("claims" in p for p in problems), problems

def test_the_guard_PRINTS_the_population_it_examined() -> None:
    """A guard that examined nothing must never print the verdict of one that did."""
    rc, out, _ = _run([], [])
    assert rc == 0, out
    assert "deferred entries examined: 0" in out, (
        f"the empty population must be PRINTED, so a clean read is never mistaken for a "
        f"checked one\n{out}"
    )



def test_the_runner_reads_the_repo_own_ledger_by_default() -> None:
    """The default path is this repo's own ledger, and every row it reads carries its `n`.

    A bootstrapped factory begins with an empty ledger, so the row assertions are made
    over whatever is there and the coverage is PRINTED — "0 rows read" and "584 rows
    read" must never render the same, and an absent ledger is stated rather than
    silently passing as a clean one.
    """
    ledger = RUNNER.LEDGER
    assert ledger == REPO / "evidence" / "ledger.jsonl", (
        f"the runner must default to this repo's ledger, not {ledger}"
    )
    if not ledger.is_file():
        print(f"  note: no ledger at {ledger} — this tree carries none to read")
        return
    rows = RUNNER.load_rows()
    assert all(isinstance(r.get("n"), int) for r in rows), "every row carries its n"
    print(f"  ledger read: {len(rows)} row(s) from {ledger}")


# --- #117: the board-close leg --------------------------------------------------

def _close_row(n: int, subject: str, ts: str, detail: str) -> dict:
    return {"n": n, "ts": ts, "event": "close", "actor": "worker",
            "subject": subject, "detail": detail}


def test_the_leg_binds_to_the_gate_own_constant_not_a_private_copy() -> None:
    """One field, one predicate: the leg reads the GATE's token and its DECLARED bound key.

    A private copy would be self-consistent on both sides and the drift would be
    invisible — the class this factory has already ruled (n=405 clause 5, n=599). The
    instant itself is FACTORY DATA (#428), so what the leg binds to is the gate's
    `INVARIANT_KEY`; the value is read from this tree's declaration through the one
    reader, and a tree that declares none is a NOT RUN rather than a red.
    """
    assert RUNNER.CLOSE_BOARD_GATE == REPO / "tests" / "test_close_board_recorded.py", (
        f"the leg must bind to the close-board gate, not {RUNNER.CLOSE_BOARD_GATE}"
    )
    gate = RUNNER.load_close_board_gate()
    assert gate.BOARD_TOKEN == "board=closed", gate.BOARD_TOKEN
    assert gate.INVARIANT_KEY == "close_board_recorded", gate.INVARIANT_KEY
    # The leg reaches the DECLARATION through the reader, and the reader's answer is
    # either a well-formed instant or a stated absence — never a third, silent state.
    text, refusal, skip_reason = RUNNER.declared_leg_boundary(REPO, gate.INVARIANT_KEY)
    if refusal:
        raise AssertionError(f"the bound is declared but unreadable: {refusal}")
    if not skip_reason:
        assert text.endswith("Z") and len(text) == 20, text


def test_a_tree_with_NO_declared_bound_does_not_judge_the_bound_dependent_legs() -> None:
    """#428 acceptance, the SKIP arm: absent factory data is a stated NOT RUN, never a red.

    A boundary is factory data, and the shipped half of this byte-identical pair declares
    none — the state every bootstrapped factory is in until it adopts the invariant. So an
    absent bound must not redden the run, and it must not silently pass either: both legs
    say which they are and why, and the intake leg still judges the two arms that ask no
    question about when a rule landed.
    """
    # The `ruling` row is not decoration: since #332 the patrol also asserts the ROUND's
    # own predicate, so a fixture that models a clean board must be a board it has SWEPT.
    # The `claim` for #7 is the OFFLINE arm's population — a subject acted on with no
    # intake row of its own — so the arm that needs the bound is actually exercised.
    issues = [_issue(1, "OPEN")]
    rows = _rows(("intake", "#1", 1), ("ruling", "#1", 2), ("claim", "#7", 3))

    def _undeclared(_repo, key):
        return "", "", f"`{key}` is UNDECLARED in this tree — NOT JUDGED: probe"

    rc, out, _ = _run(issues, rows, board_scope=_undeclared)
    assert rc == 0, f"an absent bound is factory data, not a defect, got rc={rc}\n{out}"
    assert "LEG board-close — NOT RUN" in out, out
    assert "LEG board-closed — NOT RUN" in out, out
    assert "`close_board_recorded` is UNDECLARED in this tree" in out, out
    # The intake leg's bound-independent arms are STILL judged: what was not judged must
    # never read as what was not there (#242).
    assert "LEG board-intake — ASSERTED" in out, out
    assert "1 examined" in out, out
    # ... and the bound-dependent arm says it was not judged, rather than reporting zero.
    assert "declares no boundary for the gate" in out, out

def test_a_MALFORMED_declared_bound_REFUSES_the_board_legs() -> None:
    """#428 acceptance, the FAIL arm: a declared-but-unreadable bound is a DEFECT.

    The reader's policy is absent SKIPS / malformed FAILS, and the leg maps that onto
    NOT RUN versus REFUSED. A malformed declaration hiding behind the same output as none
    at all is the failure this arm exists to catch, so the run must be RED and must name
    the key it could not read.
    """
    issues = [_issue(1, "OPEN")]
    rows = _rows(("intake", "#1", 1), ("ruling", "#1", 2))

    def _malformed(_repo, key):
        return "", f"`{key}` is declared but cannot be read: not an instant — REFUSED: probe", ""

    rc, out, _ = _run(issues, rows, board_scope=_malformed)
    assert rc == 1, f"a malformed bound is a defect, got rc={rc}\n{out}"
    assert "LEG board-close — REFUSED" in out, out
    assert "LEG board-closed — REFUSED" in out, out
    assert "LEG board-intake — REFUSED" in out, out
    assert "`close_board_recorded` is declared but cannot be read" in out, out

def test_declared_leg_boundary_MAPS_the_readers_three_outcomes() -> None:
    """#428 acceptance: the leg's own reader is DRIVEN, not assumed.

    The two probes above hand the leg a `board_scope`, so they exercise the leg's handling
    of a scope's ANSWER and never `declared_leg_boundary`'s own mapping. Measured while
    writing this: a mutant that re-typed the instant in the SKIP arm, and a mutant that
    downgraded a malformed declaration to a skip, both left those two probes GREEN — the
    mapping between the reader's two exceptions and the leg's NOT RUN / REFUSED was the
    one path in the change with no probe behind it. This drives the reader itself against
    the three trees `ledger_boundary.synthetic_tree` builds, so each outcome has a probe
    that fails on the shape it forbids.
    """
    reader = RUNNER.load_module("ledger_boundary", RUNNER.LEDGER_BOUNDARY)
    key = "close_board_recorded"

    # (1) Nothing declared: the state every bootstrapped factory is in. NOT a defect.
    undeclared = reader.synthetic_tree(_scratch(), rows=[])
    text, refusal, skip_reason = RUNNER.declared_leg_boundary(undeclared, key)
    assert (text, refusal) == ("", ""), (text, refusal)
    assert "UNDECLARED" in skip_reason and key in skip_reason, skip_reason
    assert "NOT JUDGED" in skip_reason, skip_reason

    # (2) Declared and unreadable: a DEFECT, and it must never render as (1).
    malformed = reader.synthetic_tree(_scratch(), rows=[],
                                      invariants={key: "not an instant"})
    text, refusal, skip_reason = RUNNER.declared_leg_boundary(malformed, key)
    assert (text, skip_reason) == ("", ""), (text, skip_reason)
    assert "REFUSED" in refusal and key in refusal, refusal
    assert "cannot be read" in refusal, refusal

    # (3) Declared and readable: the text is the FACTORY's, not one this file carries.
    declared = reader.synthetic_tree(_scratch(), rows=[],
                                     invariants={key: "2026-01-02T03:04:05Z"})
    text, refusal, skip_reason = RUNNER.declared_leg_boundary(declared, key)
    assert (refusal, skip_reason) == ("", ""), (refusal, skip_reason)
    assert text == "2026-01-02T03:04:05Z", text

def test_a_false_board_declaration_is_reported_and_fails_the_run() -> None:
    """#117 acceptance: a close row declaring board=closed for an OPEN issue is a problem.

    This is the NON-VACUITY probe. The live board is clean as this lands, so a leg that
    only ever saw a clean board would have shown nothing — the probe supplies the false
    declaration and asserts the leg bites.
    """
    issues = [_issue(1, "OPEN"), _issue(2, "CLOSED")]
    rows = _rows(("intake", "#1", 1), ("intake", "#2", 2)) + [
        _close_row(3, "#1", _CLOSE_TS, "settled board=closed"),
        _close_row(4, "#2", _CLOSE_TS2, "settled board=closed"),
    ]
    rc, out, _ = _run(issues, rows)
    assert rc == 1, f"a false board declaration must fail the run, got rc={rc}\n{out}"
    assert "declares board=closed for #1" in out, out
    assert "still OPEN on the board" in out, out
    assert "2 close row(s) checked" in out, (
        f"the leg must PRINT the population it examined\n{out}"
    )
    assert "close rows (declaring board=closed" in out, (
        f"the leg's own line must state the token it read\n{out}"
    )
    leg_line = out.split("LEG board-close")[1].split("\n")[1]
    assert "2 examined" in leg_line, (
        f"the leg's OWN line must carry the count, not only the verdict's: {leg_line!r}"
    )
    assert "board read at" in out, (
        f"freshness is a property of the INSTANT and must be reported\n{out}"
    )
    assert "#2" not in out.split("LEG board-close")[1].split("LEG ")[0], (
        f"a TRUE declaration must not be reported as a problem\n{out}"
    )


def test_a_true_board_declaration_reads_clean_and_states_its_population() -> None:
    """The complement: a green must be green over a NON-ZERO examined count."""
    issues = [_issue(1, "CLOSED")]
    rows = _rows(("intake", "#1", 1)) + [
        _close_row(2, "#1", _CLOSE_TS, "settled board=closed"),
    ]
    rc, out, _ = _run(issues, rows)
    assert rc == 0, out
    assert "1 close row(s) checked" in out, out
    assert "0 problem(s) — board read at" in out, out


def test_a_mid_detail_token_is_judged_not_only_a_canonical_trailer() -> None:
    """THE BINDING PROBE. A row carrying the token outside the trailing `=`-run counts.

    Measured on the live ledger: 12 of the 52 post-invariant close rows carry
    `board=closed` outside the canonical trailer (`n=303`, `315`, `327`, `341`, `368`,
    `370`, `372`, `374`, `554`, `565`, `584`, `589`). A leg that re-derived the read via
    `trailer_tokens` would judge 40 and go FALSE-GREEN over those 12.
    """
    issues = [_issue(1, "OPEN")]
    rows = _rows(("intake", "#1", 1)) + [
        _close_row(2, "#1", _CLOSE_TS,
                   "settled board=closed and then prose trails after it"),
    ]
    rc, out, _ = _run(issues, rows)
    assert rc == 1, f"a mid-detail token must still be judged, got rc={rc}\n{out}"
    assert "1 close row(s) checked" in out, out
    assert "declares board=closed for #1" in out, out


def test_a_subject_absent_from_the_board_is_a_problem_not_a_silent_pass() -> None:
    """`absent` and `closed` are different facts; only one is what the row declares."""
    issues = [_issue(1, "CLOSED")]
    rows = _rows(("intake", "#1", 1)) + [
        _close_row(2, "#99", _CLOSE_TS, "settled board=closed"),
    ]
    rc, out, _ = _run(issues, rows)
    assert rc == 1, out
    assert "no issue #99 exists on the board" in out, out


def test_a_pre_invariant_close_row_is_outside_the_population() -> None:
    """The GATE's own boundary is honoured: a pre-invariant row is not judged here."""
    issues = [_issue(1, "OPEN")]
    # The `ruling` row keeps the fixture inside the round's own population (#332): an OPEN
    # intaken item with no ruling row is a miss, and this probe is about the close board.
    rows = _rows(("intake", "#1", 1), ("ruling", "#1", 5)) + [
        _close_row(2, "#1", _PRE_CLOSE_TS, "settled board=closed"),
    ]
    rc, out, _ = _run(issues, rows)
    assert rc == 0, out
    assert "0 close row(s) checked" in out, (
        f"a pre-invariant close row must not enter the population\n{out}"
    )


def test_the_bound_is_DECLARED_DATA_and_moves_the_population() -> None:
    """#428 acceptance: the same fixture, two bounds, two populations.

    This is the arm that catches a hardcoded boundary. A row at `_CLOSE_TS` is judged
    against the declared bound and excluded against a later one — so if the leg ever went
    back to carrying its own literal, ONE of these two runs would disagree with the bound
    it was handed, and the probe would say so.
    """
    issues = [_issue(1, "OPEN")]
    rows = _rows(("intake", "#1", 1), ("ruling", "#1", 5)) + [
        _close_row(2, "#1", _CLOSE_TS, "settled board=closed"),
    ]
    declared = _close_anchor()

    def _later(_repo, key):
        return _plus(declared, 24.0), "", ""

    rc_early, out_early, _ = _run(issues, rows)
    assert rc_early == 1, out_early
    assert "1 close row(s) checked" in out_early, out_early
    assert "declares board=closed for #1" in out_early, out_early

    # The SAME row, one day past a later bound: outside the population, so not judged.
    rc_late, out_late, _ = _run(issues, rows, board_scope=_later)
    assert rc_late == 0, out_late
    assert "0 close row(s) checked" in out_late, (
        f"the bound the leg was HANDED must decide the population\n{out_late}"
    )

# --- #223: the board-ruling leg --------------------------------------------------

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

def test_the_ruling_leg_BITES_on_a_ruling_comment_with_no_row() -> None:
    """#223 acceptance, the NON-VACUITY probe: the live board is the only clean one.

    The leg's whole population is rulings that were never stamped, so a probe that only
    read a clean board would prove nothing. This supplies the defect and asserts the leg
    names it AND fails the run.
    """
    issues = [_issue_with_comments(11, "OPEN", "## RULED — shape (2), the patrol leg.\n")]
    rows = _rows(("intake", "#11", 1))
    rc, out, _ = _run(issues, rows)
    assert rc == 1, f"a ruling comment with no row must fail the run, got rc={rc}\n{out}"
    assert f"#11 carries a ruling comment on the board (comment {_comment_numeric(11)})" in out, out
    assert "but the ledger holds no `ruling` row naming it" in out, out
    assert "LEG board-ruling" in out, f"the leg must be reported at all\n{out}"

def test_a_MENTION_inside_a_comment_is_not_an_instance() -> None:
    """The discrimination that makes the leg mechanical, and the reason for the heading test.

    The loose form (`--search "RULED in:comments"`) returned 118 issues against a true
    population of 9, because every filing that says the item is NOT ruled yet scored as an
    instance. So the test is on the OPENING of the body, and this probe pins that: a mention
    mid-body and a sentence about not having ruled are both refused.
    """
    issues = [
        _issue_with_comments(21, "OPEN", "We have not ruled on this yet."),
        _issue_with_comments(22, "OPEN", "See the ## RULED section further down."),
        _issue_with_comments(23, "OPEN", "  \n## RULING — leading whitespace is tolerated."),
    ]
    rows = _rows(("intake", "#21", 1), ("intake", "#22", 2), ("intake", "#23", 3))
    rc, out, _ = _run(issues, rows)
    section = out.split("LEG board-ruling")[1].split("LEG ")[0]
    assert "examined over" in section, f"the leg must state its population\n{out}"
    assert "1 examined" in section, (
        f"EXACTLY ONE of the three must be examined — the heading one and only it: {section!r}"
    )
    assert "#21" not in section and "#22" not in section, (
        f"a mere mention must never be reported as a missing row: {section!r}"
    )

def test_a_CLOSED_item_is_still_in_the_population() -> None:
    """The class is NOT state-scoped, and the read must be the board WHOLE.

    `--state open --search` returned a DIFFERENT set from the whole-board read, because four
    of the eight originally filed had since closed. So a closed item carrying a ruling
    comment with no row is still a finding — an open-filtered read would drop it silently.
    """
    issues = [_issue_with_comments(31, "CLOSED", "## RULED — settled after the fact.\n")]
    rows = _rows(("intake", "#31", 1), ("close", "#31", 2))
    rc, out, _ = _run(issues, rows)
    assert rc == 1, f"a CLOSED item with a ruling comment and no row is still a finding: {out}"
    assert "#31 carries a ruling comment" in out, out

def test_a_ruling_row_for_the_subject_clears_it() -> None:
    """The complement: the leg is discriminating, not a blanket red.

    #511 RE-ARMED this probe. It used to clear on `number in ruled` — ANY ruling row for the
    subject — which is precisely the short-circuit the ruling removed. A row now clears the
    comment only when it NAMES it, so the fixture's row carries the pairing trailer and the
    assertion is that the pair reads clean; the `#511` test below supplies the same row
    WITHOUT the trailer and asserts the opposite verdict on the same board.
    """
    issues = [_issue_with_comments(41, "OPEN", "## RULED — stamped in the same turn.\n")]
    rows = _rows(("intake", "#41", 1),
                 ("ruling", "#41", 2, f"probe comment={_comment_numeric(41)}"))
    rc, out, _ = _run(issues, rows)
    section = out.split("LEG board-ruling")[1].split("LEG ")[0]
    assert "#41" not in section, f"a stamped ruling must not be reported: {section!r}"
    assert "1 examined" in section and "0 problem(s)" in section, (
        f"it must be EXAMINED and found clean, never skipped: {section!r}"
    )

def test_the_pairing_is_PER_ACT_not_PER_ISSUE() -> None:
    """#511, the two-arm control: ONE board, ONE issue, two ledgers, opposite verdicts.

    The defect this pins is the issue-level short-circuit — `number in ruled`, "does this
    issue carry ANY `ruling` row". Under it both arms below read CLEAN, because both carry a
    `ruling` row for #42; the only difference between them is whether that row NAMES the
    comment. A ruling is an ACT on a comment, so the trailer is the whole predicate, and the
    arm WITHOUT it is the one that must bite.

    Same fixture both sides, so the verdict is attributable to the trailer alone — the shape
    #243's bridge control used. The board is LIVE state: the false-clean direction is the
    dangerous one, so the bare arm is the arm that has to be red.
    """
    issues = [_issue_with_comments(42, "OPEN", "## RULED — a ruling.\n")]
    numeric = _comment_numeric(42)

    paired_rows = _rows(("intake", "#42", 1), ("ruling", "#42", 2, f"probe comment={numeric}"))
    rc, out, _ = _run(issues, paired_rows)
    section = out.split("LEG board-ruling")[1].split("LEG ")[0]
    assert rc == 0, f"a row NAMING the comment must clear it: {out[-3000:]}"
    assert "#42" not in section, f"a paired ruling must not be reported: {section!r}"
    assert "1 examined" in section and "0 problem(s)" in section, section

    # The SAME row, the SAME issue, the SAME comment — only the trailer is gone. This is the
    # arm the short-circuit made unreachable: the row exists, so `number in ruled` was true.
    bare_rows = _rows(("intake", "#42", 1), ("ruling", "#42", 2))
    rc, out, _ = _run(issues, bare_rows)
    section = out.split("LEG board-ruling")[1].split("LEG ")[0]
    assert rc == 1, f"a ruling row that does not NAME the comment must NOT clear it: {out[-3000:]}"
    assert "#42" in section, section
    assert "1 problem(s)" in section, section
    assert f"comment {numeric}" in section, f"the comment judged must be NAMED: {section!r}"
    assert "holds no `ruling` row naming it" in section, section

def test_the_leg_states_its_population_and_the_board_read_instant() -> None:
    """A clean read over an examined population, never a clean read over nothing.

    The clause is two-part: the gate PRINTS the population it examined. A leg that examined
    zero must not render identically to one that examined the board and found it clean.
    """
    issues = [
        _issue_with_comments(51, "OPEN", "## RULED — one.\n"),
        _issue_with_comments(52, "OPEN", "## RULING — two.\n"),
    ]
    # Both rows NAME their comment: since #511 a `ruling` row clears a comment only when its
    # detail carries `comment=<numeric id>`, so a bare row would make this a probe about the
    # pairing instead of about the printed population.
    rows = _rows(("intake", "#51", 1), ("ruling", "#51", 2, f"probe comment={_comment_numeric(51)}"),
                 ("intake", "#52", 3), ("ruling", "#52", 4, f"probe comment={_comment_numeric(52)}"))
    rc, out, _ = _run(issues, rows)
    assert rc == 0, f"both rulings are stamped, so the run is clean: {out}"
    section = out.split("LEG board-ruling")[1].split("LEG ")[0]
    assert "2 examined" in section, f"the POPULATION must be printed: {section!r}"
    assert "board read at" in section, (
        f"the board is LIVE state — the read instant is owed: {section!r}"
    )
    assert "2 issue(s) read" in section, f"the read size must travel: {section!r}"

def test_the_readings_are_DECLARED_and_the_read_carries_comments() -> None:
    """Both halves of the mechanism are pinned, because either silently kills the leg.

    A read without `comments` makes the leg examine NOTHING and print a clean verdict over
    it — the exact false-clean the population clause exists to stop. And a heading list
    inlined at the comparison cannot be probed or changed by a factory whose board differs.

    The read's field list is pinned WHOLE, so a field dropped from it is caught here rather
    than discovered as a silent no-op on live state: `createdAt` dates the stall-census
    filing guard (#415), `assignees` is what lets the OWED line tell an
    assigned-but-unclaimed unit from an untouched one (#423), and `body` carries the item's
    own statement of what it wants, which is surface 1 of the criterion-path leg's own ruling
    — without it that leg reads only replies and is blind to the criterion (#48).
    """
    assert isinstance(RUNNER.RULING_HEADINGS, tuple) and RUNNER.RULING_HEADINGS, (
        "the headings must be a declared module tuple"
    )
    assert "## RULED" in RUNNER.RULING_HEADINGS and "## RULING" in RUNNER.RULING_HEADINGS, (
        f"both headings the board carries must be declared: {RUNNER.RULING_HEADINGS}"
    )
    source = (REPO / "tools" / "patrol_host_state.py").read_text(encoding="utf-8")
    assert '"number,state,title,createdAt,closedAt,body,comments,assignees"' in source, (
        "the board read must ask for comments, or the leg examines nothing — and for "
        "`createdAt`, without which the stall-census filing guard (#415) cannot date an "
        "item and the guard is a silent no-op on live state — and for `assignees`, "
        "without which the OWED line renders an assigned-but-unclaimed unit identically "
        "to one nobody has touched (#423) — and for `body`, without which the "
        "criterion-path leg is blind to the item's own statement of what it wants (#48)"
    )


def _log_dir(**files: str) -> Path:
    """A synthetic log surface. The live population is legitimately empty on a quiet day,
    so a probe that needs a fixture gets one rather than the box's leftovers."""
    root = Path(tempfile.mkdtemp())
    for name, text in files.items():
        (root / name.replace("__", "-")).write_text(text, encoding="utf-8")
    return root

# The two shapes the finding was measured on, verbatim from the live surface: a 155-byte
# transport failure and a 197-byte delivered notify. THE LEG IS KEYED ON THE SECOND'S
# SUCCESS TOKEN, never on either size — a byte count is a count by pattern.
_FAILURE = (
    "❌ transport_error: cannot reach the A2A gateway at http://127.0.0.1:18791/a2a/v1: "
    "error sending request for url (http://127.0.0.1:18791/a2a/v1) (exit 4)\n"
)
_RECEIPT = (
    "⚠️ deferred: deferred for session 6ca0d547-4a72-4c29-ac10-967daa98af0a: delivers once "
    "the session has been quiet for 20s (hard cap 30s) — notification id "
    "f50759ea-b25f-475b-9c48-319dfa73dd8c\n"
)
# The OTHER success form, verbatim from /tmp (73 B), and the one the token-only predicate
# refused: the daemon writes no `notification id` on the immediate-delivery path.
_DELIVERED = "✅ delivered: delivered to session fb67ca75-8735-4c39-80be-06b59bd4365f\n"

def _notify_row(name, *, row_id="row-1", home="probe-home") -> dict:
    """An ENABLED cron row this factory declares — the rows the leg attributes by.

    The prompt is `_WAKE_PROMPT`, so the row is correctly thin and the CRON leg beside it
    stays clean: a probe for the notify leg must not red on the other leg, or the run's
    exit code would not be attributable to the defect under test.
    """
    return {"id": row_id, "name": name, "home": home, "deliver_to": "session:probe",
            "prompt": f"{_WAKE_PROMPT}\n\n{_NONE_DECL}"}

def _run_row(name, *, started, completed, status, row_id="row-1") -> dict:
    """A `cron_job_runs` row — the daemon's per-fire record, carrying the run's OWN VERDICT.

    The columns are the ones the daemon writes on that table, and the `job_id` here is
    deliberately the SAME value as the cron row's `id` in `_notify_row`: the leg keys a run
    to its row by the `(job_id, job_name)` pair, and the two surfaces spell that pair
    differently (`id`/`name` against `job_id`/`job_name`), so a probe that got the spelling
    wrong would exercise a leg that can match nothing (#306).
    """
    return {"job_id": row_id, "job_name": name, "started_at": started,
            "completed_at": completed, "status": status, "error": "", "home": "probe-home"}

def test_the_notify_leg_BITES_on_a_log_carrying_no_receipt() -> None:
    """THE BITE, and the acceptance criterion's probe: a log with no notification id.

    Non-vacuity here rides THIS fixture, never a loud-fail-on-zero: the live population of
    failed notifies is legitimately empty on a quiet day, so an empty read is a normal read
    (#112's shape — the opposite call from the cron-thinness leg, whose population is the
    rows the factory declares and which therefore does fail loudly).
    """
    log_dir = _log_dir(**{"factory-measurement-daily-20260921T060126.log": _FAILURE})
    rows = [_notify_row("factory-measurement-daily", row_id="55b363eb-probe")]
    rc, out, _ = _run([], [], cron_rows=rows, prefixes=["factory-"], log_dir=log_dir)
    assert rc == 1, f"a notify that produced no receipt must fail the run, got rc={rc}\n{out}"
    assert "the notify produced NO receipt" in out, out
    assert "55b363eb-probe" in out, (
        f"the report must name the cron id, so the defective JOB is resolvable\n{out}"
    )
    assert "factory-measurement-daily-20260921T060126.log" in out, (
        f"the report must name the LOG PATH the failure was read from\n{out}"
    )
    assert "transport_error" in out, (
        f"the report must quote the failure LINE, so a reader can trace it to bytes\n{out}"
    )

def test_the_notify_leg_prints_the_population_it_examined() -> None:
    """P29: a clean verdict over a population that was never named is indistinguishable
    from one that examined nothing."""
    log_dir = _log_dir(**{"factory-measurement-daily-20260921T060126.log": _RECEIPT})
    rows = [_notify_row("factory-measurement-daily")]
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home", "other-home"],
                      unreached=["gone-home: no opencrabs.db"], prefixes=["factory-"],
                      log_dir=log_dir)
    assert rc == 0, out
    assert "LEG notify-receipt — ASSERTED" in out, out
    assert "1 enabled row(s) attributed to this factory of 1 read across 2 home(s)" in out, (
        f"the jobs read, the homes read and the family they belong to must all be named\n{out}"
    )
    assert "homes unreached: 1" in out, out
    assert "gone-home" in out, (
        f"an unreached home is REPORTED — an unreachable home is not an empty one\n{out}"
    )
    assert "logs matched: 1 of 1 log(s)" in out, out
    assert "0 produced no receipt" in out, out
    assert "read at " in out, f"the read instant must travel with the count\n{out}"

def test_a_receipt_bearing_log_is_EXCUSED_and_never_judged() -> None:
    """A notify that DELIVERED is not a finding — and the excuse says which token proved it."""
    log_dir = _log_dir(**{"factory-measurement-daily-20260919T060154.log": _RECEIPT})
    rows = [_notify_row("factory-measurement-daily")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-22T00:00:00Z")
    assert leg["problems"] == [], leg["problems"]
    assert len(leg["excused"]) == 1 and "carries a receipt" in leg["excused"][0], leg["excused"]

def test_prose_ABOUT_a_missing_receipt_does_not_satisfy_the_read() -> None:
    """The prose-as-data law (n=405 clause 5): a field prose can SATISFY is not a field.

    A log that merely MENTIONS the token must not read as a receipt, or the leg would go
    quiet exactly when it is being told the id is absent.
    """
    log_dir = _log_dir(**{
        "factory-measurement-daily-20000101T000000.log":
            "❌ the notify returned no notification id: transport_error (exit 4)\n",
        "factory-measurement-daily-20000101T000001.log":
            _FAILURE.replace("transport_error", "notification id absent; transport_error"),
    })
    rows = [_notify_row("factory-measurement-daily")]
    for name in sorted(p.name for p in log_dir.iterdir()):
        text = (log_dir / name).read_text(encoding="utf-8")
        assert RUNNER.read_notify_receipt(text) is None, (
            f"{name} mentions the token without naming an id and must NOT read as a "
            f"receipt — prose about a missing field is the n=405 clause 5 damage"
        )
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-22T00:00:00Z")
    assert len(leg["problems"]) == 2, (
        f"both logs carry no receipt and both must be reported: {leg['problems']}"
    )

def test_the_DELIVERED_form_reads_as_a_receipt_of_kind_delivered() -> None:
    """#139 criterion (b): the form the token-only predicate REFUSED now reads as a receipt.

    This is the whole defect. Measured on the live surface: the immediate-delivery branch
    writes `delivered to session <uuid>` and NO id, so a predicate requiring the id reported
    every successful delivery as a failed duty — permanently, and growing by one each time.
    """
    assert RUNNER.read_notify_receipt(_DELIVERED) == "delivered", (
        "the delivered form must read as kind 'delivered' — it is the STRONGER receipt, "
        "and refusing it was the defect"
    )
    log_dir = _log_dir(**{"factory-measurement-daily-20260924T060116.log": _DELIVERED})
    rows = [_notify_row("factory-measurement-daily")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-25T13:44:00Z")
    assert leg["problems"] == [], (
        f"a delivered notify is NOT a failed duty: {leg['problems']}"
    )
    assert len(leg["excused"]) == 1 and "(delivered)" in leg["excused"][0], (
        f"the verdict must NAME the kind — delivery and acceptance are different facts: "
        f"{leg['excused']}"
    )

def test_the_DEFERRED_form_reads_as_a_receipt_of_kind_deferred_with_its_id() -> None:
    """#139 criterion (c): the weaker form keeps its own kind, and its id is quoted."""
    assert RUNNER.read_notify_receipt(_RECEIPT) == "deferred", (
        "the deferred form proves ACCEPTANCE, not delivery — a different fact"
    )
    log_dir = _log_dir(**{"factory-measurement-daily-20260919T060154.log": _RECEIPT})
    rows = [_notify_row("factory-measurement-daily")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-25T13:44:00Z")
    assert leg["problems"] == [], leg["problems"]
    assert "(deferred, id f50759ea-b25f-475b-9c48-319dfa73dd8c)" in leg["excused"][0], (
        f"the kind AND the acceptance id must be named: {leg['excused']}"
    )

def test_BOTH_forms_without_a_uuid_are_NOT_receipts() -> None:
    """#139 criterion (d), the non-vacuity control, on BOTH forms.

    A phrase alone is prose. If the phrases matched without a uuid, a log that merely
    MENTIONS the wording — a finding ABOUT the forms, e.g. this file's own text — would read
    as a receipt, which is the n=405 clause 5 damage on two forms instead of one.
    """
    for phrase in ("delivered to session ", "deferred for session "):
        assert RUNNER.read_notify_receipt(f"❌ the notify {phrase}could not be written\n") is None, (
            f"{phrase!r} without a uuid must NOT read as a receipt"
        )
    for form in ("✅ delivered: delivered to session not-a-uuid\n",
                 "⚠️ deferred: deferred for session 6ca0d547-short: x\n"):
        assert RUNNER.read_notify_receipt(form) is None, (
            f"a malformed uuid must not satisfy the read: {form!r}"
        )
    # The POSITIVE arm beside the negative one, so the control cannot pass by the predicate
    # having stopped matching anything at all.
    assert RUNNER.read_notify_receipt(_DELIVERED) == "delivered", "positive arm"
    assert RUNNER.read_notify_receipt(_RECEIPT) == "deferred", "positive arm"

def test_a_log_with_NO_OUTPUT_is_reported_as_no_attempt_never_a_failed_duty() -> None:
    """#139 criterion (e): a 0-byte log is a notify that was never ATTEMPTED.

    Measured origin: a run row reading `interrupted: cleared by doctor --fix (orphaned: no
    live process owns this run)` left a 0-byte log, so no receipt could ever be written and
    every future patrol re-reported it — a detector that could never go green. It is
    REPORTED and NAMED, because an unreported absence is indistinguishable from a clean read.
    """
    log_dir = _log_dir(**{"factory-measurement-daily-20260922T085519.log": ""})
    rows = [_notify_row("factory-measurement-daily", row_id="orphaned-probe")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-25T13:44:00Z")
    assert leg["problems"] == [], (
        f"a notify never attempted is not a failed one: {leg['problems']}"
    )
    assert leg["coverage"]["logs_not_attempted"] == 1, leg["coverage"]
    assert leg["coverage"]["not_attempted_logs"][0]["job"] == "factory-measurement-daily", (
        leg["coverage"]
    )
    assert leg["coverage"]["logs_without_receipt"] == 0, (
        f"no-attempt must NOT be counted as a missing receipt\n{leg['coverage']}"
    )

def test_a_COMPLETED_runs_0_byte_log_is_a_FAILED_DUTY_never_an_excuse() -> None:
    """#306, acceptance leg 1: the run COMPLETED and its log is 0 bytes — that is a problem.

    Measured defect: the leg excused EVERY 0-byte log as "never attempted", so a run that
    completed, launched its notify, and then died leaving no output was filed as a run that
    never got there. The two facts leave an identical log, and only the run's own verdict
    separates them — which is why the fixture is a PAIR: this half flips the run row to
    `success` and the SAME log must go from excused to RED.
    """
    log_dir = _log_dir(**{"factory-measurement-daily-20260922T085519.log": ""})
    rows = [_notify_row("factory-measurement-daily", row_id="55b363eb-probe")]
    fires = [_run_row("factory-measurement-daily", row_id="55b363eb-probe",
                      started="2026-09-22T08:55:15Z", completed="2026-09-22T08:56:20Z",
                      status="success")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-25T13:44:00Z",
                                    fires=fires)
    assert len(leg["problems"]) == 1, (
        f"a COMPLETED run's 0-byte log is a failed duty, never 'not attempted': "
        f"{leg['problems']}"
    )
    assert "COMPLETED" in leg["problems"][0] and "status success" in leg["problems"][0], (
        leg["problems"][0]
    )
    assert leg["coverage"]["logs_not_attempted"] == 0, (
        f"the excuse must NOT be earned by a completed run\n{leg['coverage']}"
    )
    assert leg["coverage"]["logs_without_receipt"] == 1, leg["coverage"]
    assert leg["coverage"]["logs_completed_with_empty_log"] == 1, leg["coverage"]

def test_a_DELIVERY_FAILED_run_is_a_PROBLEM_and_never_an_excuse() -> None:
    """#306: `delivery_failed` is the daemon's own record that the notify WAS attempted.

    The ruling names `delivery_failed` as the value a run whose notify never delivered must
    carry, and 24 rows on this box carry it beside a `completed_at` and an error naming the
    failed delivery. So it is the failed duty itself, and excusing it would file a duty that
    was attempted and failed as one that never happened — the exact inversion #306 ends.
    """
    log_dir = _log_dir(**{"factory-measurement-daily-20260922T085519.log": ""})
    rows = [_notify_row("factory-measurement-daily", row_id="55b363eb-probe")]
    fires = [_run_row("factory-measurement-daily", row_id="55b363eb-probe",
                      started="2026-09-22T08:55:15Z", completed="2026-09-22T08:56:20Z",
                      status="delivery_failed")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-25T13:44:00Z",
                                    fires=fires)
    assert len(leg["problems"]) == 1, (
        f"an attempted-and-FAILED delivery is a failed duty, never an excuse: "
        f"{leg['problems']}"
    )
    assert "status delivery_failed" in leg["problems"][0], leg["problems"][0]
    assert "REACHED ITS DELIVERY" in leg["problems"][0], (
        f"the verdict must say WHICH completed status this is\n{leg['problems'][0]}"
    )
    assert leg["coverage"]["logs_not_attempted"] == 0, (
        f"the excuse must NOT be earned by a run that reached its delivery\n{leg['coverage']}"
    )
    assert leg["coverage"]["logs_completed_with_empty_log"] == 1, leg["coverage"]


def test_an_INTERRUPTED_runs_0_byte_log_is_excused_WITH_ITS_STATUS_NAMED() -> None:
    """#306, acceptance leg 2 — the other half of the pair: the run did NOT complete.

    This is the #139 case and it stays excused, because judging it made a permanent false
    positive out of a run orphaned before it ever reached its notify. What changes is that
    the excuse now CARRIES THE EVIDENCE: the status is named in the entry, so a reader can
    tell an excused log from one that was excused because nothing was read.
    """
    log_dir = _log_dir(**{"factory-measurement-daily-20260922T085519.log": ""})
    rows = [_notify_row("factory-measurement-daily", row_id="55b363eb-probe")]
    fires = [_run_row("factory-measurement-daily", row_id="55b363eb-probe",
                      started="2026-09-22T08:55:15Z", completed="",
                      status="interrupted")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-25T13:44:00Z",
                                    fires=fires)
    assert leg["problems"] == [], (
        f"a run that never reached its notify is not a failed duty: {leg['problems']}"
    )
    assert leg["coverage"]["logs_not_attempted"] == 1, leg["coverage"]
    entry = leg["coverage"]["not_attempted_logs"][0]
    assert entry["run_status"] == "interrupted", (
        f"the excuse must NAME the status it rests on\n{entry}"
    )
    assert leg["coverage"]["logs_not_attempted_unattributed"] == 0, (
        f"the run WAS matched, so this is not an unread surface\n{leg['coverage']}"
    )

def test_a_0_byte_log_matched_to_NO_run_is_PRINTED_as_a_read_not_an_excuse() -> None:
    """#306: an unmatched 0-byte log is a statement about the READ, and it is printed.

    With no run row carrying the log's stamp there is no verdict to excuse it, so the leg
    must not fold it into the bucket silently: the count of unmatched logs is printed beside
    the bucket's own predicate, because "the run did not complete" and "no run could be
    matched" are different facts and only the first is a finding about the box.
    """
    log_dir = _log_dir(**{"factory-measurement-daily-20260922T085519.log": ""})
    rows = [_notify_row("factory-measurement-daily", row_id="55b363eb-probe")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-25T13:44:00Z",
                                    fires=[])
    assert leg["problems"] == [], (
        f"an unmatched log is not itself a failed duty: {leg['problems']}"
    )
    assert leg["coverage"]["logs_not_attempted_unattributed"] == 1, leg["coverage"]
    assert leg["coverage"]["logs_not_attempted"] == 1, leg["coverage"]
    assert leg["coverage"]["not_attempted_logs"][0]["run_status"] == "", (
        f"no run was matched, so no status may be claimed\n{leg['coverage']}"
    )

def test_an_UNKNOWN_run_status_is_REPORTED_never_excused() -> None:
    """#306: the status vocabulary is closed, so a value outside it cannot be an excuse.

    A leg that excuses what it cannot read stops observing the class it is named for the
    moment the substrate moves: the daemon adds a status, every 0-byte log under it is
    excused, and the leg goes greener as its blind spot grows. The unknown value is
    reported with the vocabulary it was checked against.
    """
    log_dir = _log_dir(**{"factory-measurement-daily-20260922T085519.log": ""})
    rows = [_notify_row("factory-measurement-daily", row_id="55b363eb-probe")]
    fires = [_run_row("factory-measurement-daily", row_id="55b363eb-probe",
                      started="2026-09-22T08:55:15Z", completed="2026-09-22T08:56:20Z",
                      status="delivered_late")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-25T13:44:00Z",
                                    fires=fires)
    assert len(leg["problems"]) == 1, (
        f"an unrecognised run status must be reported: {leg['problems']}"
    )
    assert "delivered_late" in leg["problems"][0], leg["problems"][0]
    assert leg["coverage"]["logs_not_attempted"] == 0, leg["coverage"]

def test_the_runner_PRINTS_the_no_attempt_verdict_and_its_predicate() -> None:
    """#306's render leg: the report names the run's verdict, and prints the predicate.

    A bucket and its predicate must appear together (#163 half 2 (b)): a reader who sees
    "1 no-attempt log" without the predicate cannot tell whether the leg checked a run at
    all, and the count of logs matched to NO run is printed so an unread surface is never
    indistinguishable from a box with no failed notify.
    """
    log_dir = _log_dir(**{"factory-measurement-daily-20260922T085519.log": ""})
    rows = [_notify_row("factory-measurement-daily", row_id="55b363eb-probe")]
    fires = [_run_row("factory-measurement-daily", row_id="55b363eb-probe",
                      started="2026-09-22T08:55:15Z", completed="",
                      status="interrupted")]
    rc, out, _ = _run([], [], cron_rows=rows, prefixes=["factory-"], log_dir=log_dir,
                      cron_fires=fires)
    assert "no-attempt predicate:" in out, out
    assert "its run did NOT complete (status interrupted" in out, out
    assert "no-attempt logs matched to NO run: 0 of 1" in out, out

def test_a_log_with_no_live_ROW_is_reported_as_history_and_never_judged() -> None:
    """A name this factory declares but that no enabled row carries is HISTORY.

    Judging it would red on a retired pacemaker's log forever, and a leg that cannot go
    green is a leg nobody reads. It is COUNTED and NAMED instead — the state resolved, not
    dropped (#126). The second half is the sharp edge: a row that WAS live and has been
    DISABLED is likewise history, because the population is enabled rows.
    """
    log_dir = _log_dir(**{"factory-triage-6h-20260922T000045.log": _FAILURE})
    rows = [_notify_row("factory-measurement-daily")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-22T00:00:00Z")
    assert leg["problems"] == [], (
        f"a retired job's log carries no live row to judge and must not be a problem: "
        f"{leg['problems']}"
    )
    assert leg["coverage"]["logs_retired"] == 1, leg["coverage"]
    assert leg["coverage"]["retired_logs"][0]["job"] == "factory-triage-6h", leg["coverage"]
    assert leg["coverage"]["logs_matched"] == 0, (
        f"a retired log is outside the judged population\n{leg['coverage']}"
    )


def test_a_log_whose_stem_is_a_LIVE_rows_DECLARED_redirect_is_JUDGED_not_retired() -> None:
    """#163 half 2 (a): a hand-typed label on a LIVE trigger must not hide its log in history.

    The leg's first key was the log's FILENAME stem looked up among the enabled rows' NAMES,
    and that parse cannot see a label that does not equal its job name. Measured origin: the
    job `factory-triage-patrol` wrote `/tmp/factory-triage-6h-<ts>.log` for 16 rounds, the
    stem matched no row, and every one of those logs landed in `retired_logs` as history —
    while the 2026-09-25T12:00:32Z fire's own redirect log carried no receipt and no
    directive reached the woken lane. The leg built to catch that reported the log clean.

    A live surface is never history: the stem its OWN prompt declares puts the log in the
    judged population, and the mismatch is NAMED.
    """
    log_dir = _log_dir(**{"factory-triage-6h-20260922T000045.log": _FAILURE})
    rows = [_thin("factory-triage-patrol",
                  prompt="/tmp/factory-triage-6h-$(date -u +%Y%m%dT%H%M%S).log")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-22T00:00:00Z")
    assert leg["coverage"]["logs_retired"] == 0, (
        f"a stem a LIVE row declares in its own prompt is not history\n{leg['coverage']}"
    )
    assert leg["coverage"]["logs_attributed_by_redirect"] == 1, leg["coverage"]
    assert leg["coverage"]["attributed_by_redirect"][0]["row"] == "factory-triage-patrol", (
        f"the log must name the LIVE row that declares it\n{leg['coverage']}"
    )
    assert leg["coverage"]["logs_without_receipt"] == 1, (
        f"judged, so its missing receipt is reported rather than filed as history\n"
        f"{leg['coverage']}"
    )
    assert len(leg["problems"]) == 1 and "factory-triage-6h" in leg["problems"][0], (
        f"the live mis-labelled log must be a NAMED problem: {leg['problems']}"
    )


def test_a_stem_NO_live_row_declares_stays_HISTORY() -> None:
    """NEGATIVE CONTROL for the arm above: the bucket is keyed on the DECLARED stem.

    A fix that moved every unmatched stem into the judged population would be worse than
    the defect — it would red forever on genuinely retired pacemakers' logs, and a leg that
    cannot go green is a leg nobody reads. So a row declaring a DIFFERENT redirect does not
    adopt this log.
    """
    log_dir = _log_dir(**{"factory-triage-6h-20260922T000045.log": _FAILURE})
    rows = [_thin("factory-measurement-daily",
                  prompt="/tmp/factory-measurement-daily-$(date -u +%Y%m%dT%H%M%S).log")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-22T00:00:00Z")
    assert leg["coverage"]["logs_retired"] == 1, (
        f"a stem no live row declares is genuinely history\n{leg['coverage']}"
    )
    assert leg["coverage"]["logs_attributed_by_redirect"] == 0, leg["coverage"]
    assert leg["problems"] == [], (
        f"history is never a problem\n{leg['problems']}"
    )


def test_a_CLASS_1_row_is_NAMED_with_its_class_never_counted() -> None:
    """#148 acceptance 1: a class-gate that prints only a COUNT fails.

    `#119` created the class and the detection worked; nothing acted on the finding, so the
    row stayed broken while every mechanical surface read clean (criterion 4 of #148, ruling
    n=1169: "a count is a fact about a population and a repairer needs an OBJECT"). The leg
    must therefore NAME the row and its class, not merely report that a class exists.
    """
    rows = [_cron("factory-broken-pacemaker", deliver_to=f"oc://session/{_SESSION_UUID}",
                  prompt=_WAKE_PROMPT)]
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home"], unreached=[],
                      prefixes=["factory-"])
    assert rc != 0, f"a class-1 row is a problem, so the run reds\n{out}"
    assert "factory-broken-pacemaker" in out, (
        f"the class-1 row must be NAMED, never folded into a count\n{out}"
    )
    assert "unbaked" in out, f"the finding must name the CLASS it belongs to\n{out}"
    assert "route: factory-broken-pacemaker — unbaked-target" in out, (
        f"and its CURRENT route must be printed per row WITH ITS CLASS, not merely the "
        f"predicate's finding — so a row that regresses into class 1 is named as class 1\n"
        f"{out}"
    )


def test_the_leg_prints_the_CURRENT_delivery_path_of_every_attributed_row() -> None:
    """#148 acceptance 2: the scheduled check asserts the state READ, not a forecast.

    The patrol runs on a cron cadence, so the current delivery path of each attributed row
    is what makes the row's health assertable by a RUN rather than predicted by a plan.
    """
    rows = [
        _cron("factory-prompt-notify",
              prompt=f"{_WAKE_PROMPT} then run session notify for the lane\n\n{_NONE_DECL}"),
        _cron("factory-session-target", deliver_to=f"session:{_SESSION_UUID}",
              prompt=f"{_WAKE_PROMPT}\n\n{_NONE_DECL}"),
    ]
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home"], unreached=[],
                      prefixes=["factory-"])
    assert rc == 0, f"both rows are thin and must be clean\n{out}"
    assert "delivery paths:" in out, f"the routes block must be printed\n{out}"
    assert "route: factory-prompt-notify — prompt-notify (no deliver_to)" in out, (
        f"each attributed row's CURRENT route must be named with the field it came from\n{out}"
    )
    assert "route: factory-session-target — session-target" in out, out
    assert "2 attributed row(s)" in out, f"the population must be printed\n{out}"


def test_a_row_this_factory_does_NOT_own_is_not_in_the_routes_block() -> None:
    """NEGATIVE CONTROL: the block's population is the ATTRIBUTED set, not every row read.

    A block that named rows this factory has no authority over would turn a per-factory
    report into a box-wide one (#101, ruling n=610 part 3b).
    """
    rows = [
        _cron("factory-mine",
              prompt=f"{_WAKE_PROMPT} then run session notify for the lane\n\n{_NONE_DECL}"),
        _cron("other-factory-job",
              prompt=f"{_WAKE_PROMPT} then run session notify for the lane\n\n{_NONE_DECL}"),
    ]
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home"], unreached=[],
                      prefixes=["factory-"])
    assert rc == 0, out
    routes_block = out.split("delivery paths:", 1)[1]
    assert "route: factory-mine" in routes_block, routes_block
    assert "other-factory-job" not in routes_block.split("homes unreached", 1)[0], (
        f"an unattributed row is REPORTED in its own bucket, never judged here\n{routes_block}"
    )


def test_the_retired_bucket_prints_its_POPULATION_and_its_PREDICATE() -> None:
    """#163 half 2 (b): "no retired logs" and "a bucket that cannot see one" must differ.

    The bucket is the leg's silent-exclusion surface, so an empty read has to PRINT the
    population it examined and the predicate that emptied it. A bare zero is
    indistinguishable from a bucket whose key can never match.
    """
    # arm 1 — nothing retired: the zero must still carry its predicate.
    rows = [_notify_row("factory-measurement-daily")]
    log_dir = _log_dir(**{"factory-measurement-daily-20260921T060126.log": _RECEIPT})
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home"], unreached=[],
                      prefixes=["factory-"], log_dir=log_dir)
    assert rc == 0, out
    assert "retired: 0 log(s)" in out, (
        f"an empty bucket must print its population rather than vanish\n{out}"
    )
    assert "names no enabled row this factory declares" in out, (
        f"the bucket's PREDICATE must be printed beside its population\n{out}"
    )

    # arm 2 — a live label mismatch: NAMED as judged, never filed as history.
    rows2 = [_thin("factory-triage-patrol",
                   prompt="/tmp/factory-triage-6h-$(date -u +%Y%m%dT%H%M%S).log")]
    log_dir2 = _log_dir(**{"factory-triage-6h-20260922T000045.log": _FAILURE})
    _, out2, _ = _run([], [], cron_rows=rows2, homes=["probe-home"], unreached=[],
                      prefixes=["factory-"], log_dir=log_dir2)
    assert "attributed by DECLARED REDIRECT" in out2, (
        f"a live label mismatch must be VISIBLE in the report\n{out2}"
    )
    assert "live label mismatch" in out2 and "factory-triage-patrol" in out2, (
        f"the mismatch must NAME the live row that owns the log\n{out2}"
    )

def test_a_log_nobody_here_declares_is_reported_and_never_judged() -> None:
    """Another factory's law is not this factory's to enforce (#101, ruling n=610 part 3b)."""
    log_dir = _log_dir(**{"sibling-some-other-job-20260922T000045.log": _FAILURE})
    rows = [_notify_row("factory-measurement-daily")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-22T00:00:00Z")
    assert leg["problems"] == [], (
        f"an unattributable log belongs in the population read, never in the problems: "
        f"{leg['problems']}"
    )
    assert leg["coverage"]["logs_unattributed"] == 1, leg["coverage"]
    assert leg["coverage"]["unattributed_logs"][0]["job"] == "sibling-some-other-job", leg["coverage"]

def test_a_log_that_exists_and_cannot_be_READ_is_a_problem_not_an_absence() -> None:
    """The #69 clause (e) shape: a declared surface that defeats the read is a defect.

    An unreadable log rendering as an absent one is the failure mode that makes a reader
    worse than useless — the notify may have failed and the leg would say nothing.

    The read failure is DRIVEN rather than simulated with a permission bit: this gate runs
    as root on this box, and root reads a `chmod 000` file happily, so a permission-bit
    probe would pass for the wrong reason here and fail in a factory that runs as a user.
    """
    log_dir = _log_dir(**{"factory-measurement-daily-20260921T060126.log": _FAILURE})
    target = log_dir / "factory-measurement-daily-20260921T060126.log"
    rows = [_notify_row("factory-measurement-daily")]
    real_read_text = Path.read_text

    def denying_read_text(self, *args, **kwargs):
        if self == target:
            raise OSError("probe: simulated read failure")
        return real_read_text(self, *args, **kwargs)

    with mock.patch.object(Path, "read_text", denying_read_text):
        leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                        log_dir=log_dir, read_at="2026-09-22T00:00:00Z")
    assert leg["problems"], "an unreadable log must be a problem, never an absence"
    assert "could not be read" in leg["problems"][0], leg["problems"]
    assert "never an absence" in leg["problems"][0], leg["problems"]
    assert leg["coverage"]["logs_without_receipt"] == 0, (
        f"the row was never JUDGED — it failed at the read, which is a different fact: "
        f"{leg['coverage']}"
    )

def test_an_absent_log_directory_is_a_NOT_RUN_with_its_reason() -> None:
    """A read that never happened must never render as a read that found nothing.

    Stated in the leg's own contract, so this is asserted against the leg rather than
    through main() — main() takes the constant path that exists.
    """
    rows = [_notify_row("factory-measurement-daily")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=Path("/tmp/does-not-exist-probe-122"),
                                    read_at="2026-09-22T00:00:00Z")
    assert leg["status"] == "NOT RUN", leg["status"]
    assert leg["reason"] and "does not exist" in leg["reason"], leg["reason"]
    assert leg["problems"] == [], (
        f"an unread surface is NOT RUN, never a problem and never a silent pass: {leg}"
    )

def test_the_leg_finds_the_LIVE_surface_and_never_copies_it() -> None:
    """The leg reads `/tmp` IN PLACE by constant, and the constant is this tool's own.

    A copy of a live surface is stale the moment it is written, and the failure log is a
    file that the next run overwrites; there is nothing to copy and no reason to.
    """
    assert RUNNER.LOG_DIR == Path("/tmp"), f"the surface is /tmp, not {RUNNER.LOG_DIR}"
    matched, reason = RUNNER.notify_logs(RUNNER.LOG_DIR)
    assert reason is None, f"the live surface must be readable here: {reason}"
    assert all(
        RUNNER.NOTIFY_LOG_RE.match(path.name) for _, path in matched
    ), "every matched path must carry a `<job>-<stamp>.log` name"
    print(f"  live log surface: {len(matched)} matched log(s) under {RUNNER.LOG_DIR}")

def test_the_leg_shares_the_manifest_declaration_with_the_CRON_leg() -> None:
    """ONE attribution predicate, TWO legs — imported, never re-derived.

    Ownership is the manifest's declared `job_prefixes`, so a leg that re-derived it would
    judge a different population than the leg beside it and the two reports could never be
    reconciled.
    """
    rows = [
        _notify_row("factory-mine"),
        dict(_notify_row("sibling-not-mine"), home="other-home"),
    ]
    mine, nobody = RUNNER.attribute_rows(rows, ["factory-"])
    assert [r["name"] for r in mine] == ["factory-mine"], mine
    assert [r["name"] for r in nobody] == ["sibling-not-mine"], nobody


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

def test_the_box_read_SUPPLIES_the_id_that_resolves_each_row() -> None:
    """THE DEFECT THIS PROBE EXISTS FOR, measured live before it was written.

    The leg's first live run reported every finding as `(cron id unstated)`, because the
    box read projected only name/deliver_to/prompt and the id never reached the report.
    The probes above could not see it: they HAND the leg a row that already carries an id,
    so they fed it the very field whose absence was the bug. A criterion naming "the job
    id" is satisfied by a row that HAS one, and the read path is where it is lost.
    """
    root = Path(tempfile.mkdtemp()) / "profiles"
    (root / "ops").mkdir(parents=True)
    _home_db(root.parent / "opencrabs.db",
             ("id-in-default-home", "factory-default-home", "", "", 1))
    _home_db(root / "ops" / "opencrabs.db",
             ("id-in-ops-home", "factory-ops-home", "session:probe", _WAKE_PROMPT, 1),
             ("id-disabled", "factory-disabled", "", "", 0))
    rows, homes_read, unreached = RUNNER.box_cron_rows(root)
    assert unreached == [], unreached
    assert len(homes_read) == 2, f"both homes must be read: {homes_read}"
    by_name = {row["name"]: row for row in rows}
    assert set(by_name) == {"factory-default-home", "factory-ops-home"}, (
        f"the read is of ENABLED rows only: {sorted(by_name)}"
    )
    for name in ("factory-default-home", "factory-ops-home"):
        assert by_name[name].get("id"), (
            f"{name} was read without an id — a report cannot resolve a row it names by "
            f"a name two homes may share (#126)"
        )
    assert by_name["factory-ops-home"]["id"] == "id-in-ops-home", by_name

def test_a_finding_reports_the_id_read_from_the_box_not_a_placeholder() -> None:
    """End to end over the same throwaway shape: the id in the REPORT is the id on the ROW.

    The report is what a reader acts on. A placeholder there — `unstated`, `row 3` — is a
    finding that cannot be resolved to a cron job, which is the whole job of the line.
    """
    root = Path(tempfile.mkdtemp()) / "profiles"
    (root / "ops").mkdir(parents=True)
    _home_db(root.parent / "opencrabs.db")
    _home_db(root / "ops" / "opencrabs.db",
             ("55b363eb-live", "factory-measurement-daily", "session:probe", _WAKE_PROMPT, 1))
    rows, homes_read, unreached = RUNNER.box_cron_rows(root)
    log_dir = _log_dir(**{"factory-measurement-daily-20260921T060126.log": _FAILURE})
    leg = RUNNER.notify_receipt_leg(rows, homes_read, unreached, ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-22T00:00:00Z")
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "55b363eb-live" in leg["problems"][0], leg["problems"]
    assert "unstated" not in leg["problems"][0], (
        f"the id was read from the row and must be reported, never hedged\n"
        f"{leg['problems'][0]}"
    )


def _tier_row(n: int, subject: str, detail: str, event: str = "ruling") -> dict:
    """A ledger row carrying whatever `detail` says — trailer discipline is the caller's."""
    return {"n": n, "ts": _CLOSE_TS, "event": event, "actor": "hq",
            "subject": subject, "detail": detail}


def test_the_canonicality_leg_primes_ON_the_ledger_it_was_given() -> None:
    """A leg is only as good as the population it enumerates, so the population is stated.

    `rows_declaring_tier` is legitimately zero today — the field is new — and zero THERE
    is not a vacuous clean, because the enumeration asserted non-empty is `rows_read`.
    """
    rows = _rows(("intake", "#1", 1), ("close", "#1", 2))
    leg = RUNNER.canonicality_leg(rows, read_at="2026-09-23T11:00Z")
    assert leg["name"] == "canonicality-tier", leg["name"]
    assert leg["status"] == "ASSERTED", leg
    cov = leg["coverage"]
    assert cov["rows_read"] == 2, cov
    assert cov["rows_declaring_tier"] == 0, cov
    assert leg["problems"] == [], leg["problems"]


def test_a_STANDING_T4_is_reported_and_names_the_tier() -> None:
    """The probe that proves this leg BITES: force a T4, and it must not read clean.

    The declaration sits in the canonical trailer — the run of `key=value` tokens at the
    END of the detail (SKILL.md section 11). Prose after it terminates the run, which is
    the next test's subject.
    """
    rows = [_tier_row(1, "#900", "open question: which twin is canonical run=7 tier=T4")]
    leg = RUNNER.canonicality_leg(rows, read_at="2026-09-23T11:00Z")
    assert leg["problems"], "a standing T4 produced no problem — the leg is vacuous"
    joined = " ".join(leg["problems"])
    assert "tier=T4" in joined, joined
    assert "NEITHER side is canonical" in joined, joined
    assert leg["coverage"]["t4_standing"] == 1, leg["coverage"]


def test_a_T4_superseded_by_a_LATER_row_stops_reding_for_ever() -> None:
    """A leg with no exit teaches the next reader to ignore a red patrol (#139).

    The read is a SEQUENCE: once a later row for the same subject declares a resolved
    tier, the T4 is history, not a standing finding.
    """
    rows = [
        _tier_row(1, "#900", "unresolved run=7 tier=T4"),
        _tier_row(2, "#900", "resolved run=8 tier=T1"),
    ]
    leg = RUNNER.canonicality_leg(rows, read_at="2026-09-23T11:00Z")
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["t4_superseded"] == 1, leg["coverage"]
    assert leg["coverage"]["t4_standing"] == 0, leg["coverage"]


def test_a_T4_for_a_DIFFERENT_subject_is_not_superseded_by_the_wrong_row() -> None:
    """Supersession is keyed on the SUBJECT, never on mere recency.

    An earlier draft compared indices alone, which would let any later row anywhere in
    the ledger resolve any earlier T4 — the adjacency error, in a new place.
    """
    rows = [
        _tier_row(1, "#900", "unresolved run=7 tier=T4"),
        _tier_row(2, "#901", "an unrelated subject run=8 tier=T1"),
    ]
    leg = RUNNER.canonicality_leg(rows, read_at="2026-09-23T11:00Z")
    assert leg["coverage"]["t4_standing"] == 1, leg["coverage"]
    assert leg["coverage"]["unresolved_subjects"] == ["#900"], leg["coverage"]


def test_an_EMPTY_tier_population_is_NOT_a_vacuous_clean() -> None:
    """The loud-fail form is WRONG for a forward-only population, and this pins why.

    `rows_declaring_tier` is legitimately zero until the first tier lands, so failing on
    zero would red the patrol for a state that is not a defect — the permanent
    false-positive class #139 names. Section 8's own clause (#112, ruling n=657 item 8)
    makes NON-VACUITY a property of the PROBE for exactly this shape, and
    `test_a_STANDING_T4_is_reported_and_names_the_tier` above is that probe. What the
    RUN must carry is POPULATION VISIBILITY, not a synthetic finding.
    """
    leg = RUNNER.canonicality_leg([], read_at="2026-09-23T11:00Z")
    assert leg["problems"] == [], (
        "an empty tier population must not manufacture a finding — non-vacuity is the "
        f"probe's job here, and this leg is forward-only: {leg['problems']}"
    )
    assert leg["coverage"]["rows_read"] == 0, leg["coverage"]
    assert "rows_declaring_tier" in leg["coverage"], leg["coverage"]


def test_the_leg_PRINTS_the_population_it_examined() -> None:
    """Population visibility is the RUN's property: a count travelling with its predicate."""
    rows = [_tier_row(1, "#900", "settled run=7 tier=T1")]
    rc, out, _ = _run([], rows)
    assert "1 of 1 declare a tier" in out, out


def test_an_unrecognised_tier_is_a_defect_not_a_resolution() -> None:
    """`tier=T9` cannot have resolved a discrepancy, and reading it as one is the bug."""
    rows = [_tier_row(1, "#902", "nonsense run=7 tier=T9")]
    leg = RUNNER.canonicality_leg(rows, read_at="2026-09-23T11:00Z")
    assert leg["problems"], "an unrecognised tier passed"
    assert "not one of" in " ".join(leg["problems"]), leg["problems"]


def test_a_tier_OUTSIDE_the_canonical_trailer_is_a_mention_not_a_declaration() -> None:
    """The read is trailer-scoped by design, and this pins that it is not a bug.

    A detail whose trailer is terminated by prose declares nothing: the same rule that
    makes a quoted trailer mid-sentence not a declaration (#91, ruled at n=572 PART 3).
    """
    rows = [_tier_row(1, "#903", "a mention only tier=T4 and then prose follows")]
    leg = RUNNER.canonicality_leg(rows, read_at="2026-09-23T11:00Z")
    assert leg["coverage"]["rows_declaring_tier"] == 0, leg["coverage"]
    assert leg["problems"] == [], leg["problems"]


def test_the_leg_reaches_the_RENDERED_report_and_reds_the_run() -> None:
    """End to end: a standing T4 must appear in the report AND set the exit code."""
    rows = [_tier_row(1, "#900", "unresolved run=7 tier=T4")]
    rc, out, _ = _run([], rows)
    assert "LEG canonicality-tier" in out, out
    assert "tier=T4" in out, out
    assert rc == 1, f"a standing T4 must red the run, got rc={rc}\n{out}"


def test_a_clean_ledger_reads_clean_in_the_RENDERED_report() -> None:
    """The negative half: with nothing unresolved the leg must not manufacture a finding."""
    rows = [_tier_row(1, "#900", "settled run=7 tier=T1")]
    rc, out, _ = _run([], rows)
    assert "LEG canonicality-tier" in out, out
    assert "1 standing tier=T4" not in out, out
    assert "0 standing tier=T4" in out, out


def test_the_leg_reads_through_the_SHARED_predicate_never_a_private_split() -> None:
    """One field, one predicate (section 11) — a private parse is the defect it names."""
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "field_predicate" in source, "the leg does not bind to the shared predicate"
    start = source.index("def canonicality_leg")
    end = source.index("def deferred_legs")
    body = source[start:end]
    assert "trailer_tokens(" in body, "the trailer read must come from the module"
    assert "keyed_value(" in body, "the value read must come from the module"
    assert '.split("=")' not in body, "a private split is exactly what the law bars"

# ---- the ledger ref-role leg (#330, ruled at n=3362) --------------------------------

def test_the_ref_role_leg_reaches_the_RENDER_and_reds_the_run() -> None:
    """End to end: a receipt asserting the WRONG role for a row must red the round.

    The instance is #330's own, shrunk to two rows: a receipt says `intake row n=2` and
    n=2 is a close. Existence is satisfied — n=2 IS a row — which is exactly why the write
    path passed it; the ROLE is what the reader needs and what the leg judges.
    """
    rows = [
        _tier_row(1, "#900", "settled run=7 tier=T1", event="intake"),
        _tier_row(2, "#900", "CLOSE #900. Intake row n=2.", event="close"),
    ]
    rc, out, _ = _run([], rows)
    assert "LEG ledger-ref-roles" in out, out
    assert "UNRESOLVED" in out, out
    assert rc == 1, f"a wrong role assertion must red the run, got rc={rc}\n{out}"

def test_the_ref_role_leg_PRINTS_its_population_even_when_clean() -> None:
    """A leg that examined nothing and one that examined the corpus must never render alike.

    The negative half: a correct assertion reads clean, and the render still carries the
    counts — assertions examined, roles judged, mismatches, declared-exempt, unresolved.
    """
    rows = [
        _tier_row(1, "#900", "settled run=7 tier=T1", event="intake"),
        _tier_row(2, "#900", "CLOSE #900. Intake row n=1.", event="close"),
    ]
    rc, out, _ = _run([], rows)
    assert "LEG ledger-ref-roles" in out, out
    assert "1 examined over 2 ledger row(s)" in out, out
    assert "0 mismatch(es), 0 declared-exempt, 0 unresolved" in out, out
    # The rc is NOT asserted here: this fixture's board is empty while its rows name #900,
    # so the board-intake leg reds for a reason this probe is not about. What this probe
    # owns is that the ref-role leg contributes NO unresolved line of its own.
    assert "UNRESOLVED" not in out, out


# --- the duty-completion-receipt leg (#147) ------------------------------------
#
# #122's leg asks whether a thin trigger's notify produced a RECEIPT. These probe the
# question it cannot: did the DUTY the notify woke actually COMPLETE? The live population
# of a cleanly-completed round is an EMPTY problem list, so a test driven from the live box
# passes vacuously — every probe below drives the leg from a FIXTURE.

_RECEIPT_PROMPT = (
    "Thin trigger only — do NOT execute any project work yourself. Call the "
    "session_notify tool exactly ONCE, then stop.\n\nreceipt_subject: registry-attest\n"
)

# --- the TREE's own instants, never the kit's literals ---------------------------
# Every instant in the duty and board fixtures below is derived from the boundary and the
# gate anchor THIS tree declares, read through the same readers the legs themselves use.
# This file ships as a byte-identical pair, and in the half that ships "this factory" is
# the ADOPTING MEMBER, whose instants are its own (#78 clause b). A fixture pinned to the
# kit's literal therefore exercises the leg against a date no member need share — the same
# failure the file guards against for the leg, applied to its own probes. Measured in the
# adoption pilot: 8 of 102 probes failed in a member tree that had done nothing wrong.
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
        return fallback  # here the literal only keeps the probes runnable before adoption.


def _close_anchor() -> str:
    """The close-board gate's own anchor, as this tree declares it.

    Read through the same reader the leg uses (#428): the gate no longer carries the
    instant as a constant, because a boundary is factory data and this file ships into
    every member tree. The literal is only the fallback that keeps the probes runnable
    before adoption, and it is the same value the kit ships in the example declaration.
    """
    return _tree_bound("close_board_recorded", "2026-09-18T18:04:24Z")

# The three board legs' bounds (#428). Same rule as the duty bound above: the instant is
# read from THIS tree's declaration through the reader the legs themselves use, with the
# kit's literal only as the pre-adoption fallback. A probe pinned to the kit's literal
# would exercise the leg against a date no member need share.
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


# The duty leg's bound (#487). Same rule as the three board legs' bounds above: the instant
# is read from THIS tree's declaration through the reader the leg itself uses, with the kit's
# literal only as the pre-adoption fallback. `_duty_scope` returns `(instant, text, refusal)`
# -- the INSTANT first, unlike `_board_scope`, because this leg consumes a parsed instant where
# the board legs re-parse a text -- and it is the SAME function `_run` hands the leg as its
# default reader, so the probe's own instants and the leg's bound resolve by ONE path.
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

def _receipt_row(subject=None,
                 detail="the round completed. duty=completed", n=1) -> dict:
    subject = f"registry-attest-{_DUTY_ROUND}" if subject is None else subject
    """A receipt row. The `duty=` token is what MAKES it a receipt (#160).

    The default carries it, because a row that declares nothing is not a receipt at all —
    the leg's first version accepted any subject match, which is how a dispatch record
    written before the round completed certified the round.
    """
    return {"n": n, "ts": _RECEIPT_TS, "event": "run", "actor": "delegate",
            "subject": subject, "detail": detail}

def _fire_receipt(fire_hours: float, latency_secs: float, n: int) -> dict:
    """A receipt row for the round opened `fire_hours` after the bound, `latency_secs` later.

    Built rather than pinned, because the per-job residual (#449) is a function of the GAP
    between a fire and its round's receipt: a fixture with a fixed receipt instant can only
    express one latency, and a measurement over one observation is not a max.
    """
    fire = _plus(_DUTY_BOUND, fire_hours)
    fired = dt.datetime.strptime(fire, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    receipt = (fired + dt.timedelta(seconds=latency_secs)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"n": n, "ts": receipt, "event": "run", "actor": "delegate",
            "subject": f"registry-attest-{fire[:10]}",
            "detail": "the round completed. duty=completed"}

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

# THE FORWARD BOUND the duty probes are driven against (#175). Declared HERE rather than
# read from the live tree, because this file is a SHIPPED PAIR: a member factory that has
# not adopted the convention declares no key, and criterion 4 makes that a REFUSAL — so a
# probe that inherited the live declaration would fail in the very tree it ships to.
# The instant is the one this factory declares in docs/ledger-invariants.json, so the
# probes exercise the same boundary the live leg does without depending on it.
# `_DUTY_BOUND` is derived ABOVE, from the tree's own declaration.


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

def _stub_predicate(**overrides):
    """The SHARED field predicate with ONE reader replaced — the neuter-the-code control.

    Criterion 1 of the #281 ruling (n=2003) requires the MALFORMED-RECEIPT finding to be
    proven to BITE, and a finding that survives its own discriminator being neutered is
    not a finding: it is prose that happens to be true. So the probes replace exactly one
    attribute and assert the finding MOVES, which is what makes the surviving assertion
    attributable to that attribute rather than to the fixture.

    Everything else delegates to the real module, so a probe neuters ONE reader and the
    rest of the leg keeps the behaviour the live run has.
    """
    real = RUNNER.field_predicate_readers()
    class _Stub:
        def __init__(self):
            object.__setattr__(self, "_real", real)
            for key, value in overrides.items():
                object.__setattr__(self, key, value)
        def __getattr__(self, name):
            return getattr(object.__getattribute__(self, "_real"), name)
    return _Stub()

def _lexical_duty_scan(detail: str) -> bool:
    """`mentions_duty` with the own-voice scope REMOVED — the pre-#278 lexical reading.

    Built on the real module's own `keyed_value`, so the neutered reader differs from the
    live one in ONE respect only: whether a token inside a parenthetical aside counts. That
    is the exact question the ruling says the shared discriminator answers, so this is the
    control that shows it is answering it.
    """
    real = RUNNER.field_predicate_readers()
    return any(real.keyed_value(token, real.DUTY_KEY) is not None
               for token in str(detail).split())


def test_the_duty_leg_BITES_when_a_fired_round_left_no_receipt() -> None:
    """THE probe this leg exists for: a green cron run with no duty row is a FINDING.

    The measured instance: six fragments sat at attested_at 2026-09-19 for four days while
    `cron_job_runs` carried success — the trigger worked and the duty did not, and nothing
    reported it.
    """
    leg = _duty_leg([_duty_row()], [])
    assert leg["status"] == "ASSERTED", leg
    assert leg["coverage"]["duties_judged"][0]["round"] == _DUTY_ROUND, leg["coverage"]
    assert len(leg["problems"]) == 1, leg["problems"]
    problem = leg["problems"][0]
    assert "NO duty receipt" in problem, problem
    assert f"registry-attest-{_DUTY_ROUND}" in problem, problem
    assert "9ec28cec" in problem, "the finding must RESOLVE the row it names, by id"
    assert "TRIGGER fired" in problem, "the finding must say what a green run does mean"

def test_the_duty_leg_passes_when_the_round_left_its_receipt() -> None:
    leg = _duty_leg([_duty_row()], [_receipt_row()])
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["duties_judged"][0]["receipts"] == 1

def test_the_duty_leg_reports_a_FAILED_receipt_not_only_a_missing_one() -> None:
    """A receipt that declares a non-success is a FAILED duty, never a clean one."""
    leg = _duty_leg(
        [_duty_row()],
        [_receipt_row(detail="the round did not complete. duty=failed")],
    )
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "did NOT complete" in leg["problems"][0], leg["problems"][0]
    assert "duty=failed" in leg["problems"][0], leg["problems"][0]

def test_a_SKIPPED_receipt_is_a_finding_too() -> None:
    """`skipped` is in the domain and is NOT a completion — it must not pass silently.

    The domain is completed|failed|skipped, so the leg owes an answer for each member. A
    receipt declaring `skipped` says the duty did not run, which is exactly what this leg
    exists to surface.
    """
    leg = _duty_leg([_duty_row()], [_receipt_row(detail="nothing ran today. duty=skipped")])
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "duty=skipped" in leg["problems"][0], leg["problems"][0]

def test_a_duty_value_OUTSIDE_the_domain_is_an_ERROR_never_a_silent_pass() -> None:
    """The `declared_outcome` precedent: an unrecognised value is REPORTED, never bucketed.

    A reader that silently accepted `duty=done` would let a typo read as a completion, which
    is the fabrication direction #53 clause 4 removed from the outcome reader.
    """
    leg = _duty_leg([_duty_row()], [_receipt_row(detail="the round finished. duty=done")])
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "outside the domain" in leg["problems"][0], leg["problems"][0]
    assert "duty=done" in leg["problems"][0], leg["problems"][0]

def test_the_NEWEST_receipt_GOVERNS_a_round_that_failed_then_completed() -> None:
    """#217: a round can fail at T and complete at T+n, and that is not a standing problem.

    The measured instance: round 2026-09-28 on `registry-attest` carried a `duty=failed` row
    written at 5-of-6, then a `duty=completed` row when the sixth fragment answered. Every
    row is honest and neither corrects the other, so before this the round red for the rest
    of its key and a lane had NO lawful way to record the recovery.

    BOTH halves are asserted, because either alone is passable by a wrong implementation:
    the verdict must go CLEAN, and the SUPERSEDED row must still be printed. A leg that
    simply dropped the incomplete rows would pass the first half and hide the failure.
    """
    failed = _receipt_row(subject=f"registry-attest-{_DUTY_ROUND}",
                          detail="5 of 6 fragments written back. duty=failed", n=1499)
    failed["ts"] = _plus(_DUTY_BOUND, 0.9)
    completed = _receipt_row(subject=f"registry-attest-{_DUTY_ROUND}",
                             detail="6 of 6 fragments written back. duty=completed", n=1529)
    completed["ts"] = _plus(_DUTY_BOUND, 1.5)
    leg = _duty_leg([_duty_row()], [failed, completed])

    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["rounds_superseded"] == 1, leg["coverage"]
    superseded = [e for e in leg["excused"] if "SUPERSEDED" in e]
    assert len(superseded) == 1, leg["excused"]
    note = superseded[0]
    assert "n=1499" in note, note                      # the superseded row, NAMED
    assert "duty=failed" in note, note                 # with the value it declared
    assert "n=1529" in note, note                      # and its successor
    assert "not backfilled" in note, note              # the row is not rewritten

def test_a_round_whose_NEWEST_receipt_failed_still_REDs() -> None:
    """The discriminator must not weaken the finding it was added alongside.

    Same round, the OPPOSITE order: it completed, then a later row says it failed. The
    newest declaration governs, so the round is a problem — which is what stops the fix
    from becoming "any completed row anywhere clears the round".
    """
    completed = _receipt_row(subject=f"registry-attest-{_DUTY_ROUND}",
                             detail="6 of 6 fragments written back. duty=completed", n=1529)
    completed["ts"] = _plus(_DUTY_BOUND, 0.9)
    failed = _receipt_row(subject=f"registry-attest-{_DUTY_ROUND}",
                          detail="a fragment regressed on re-read. duty=failed", n=1540)
    failed["ts"] = _plus(_DUTY_BOUND, 1.5)
    leg = _duty_leg([_duty_row()], [completed, failed])

    assert len(leg["problems"]) == 1, leg["problems"]
    assert "did NOT complete" in leg["problems"][0], leg["problems"][0]
    assert "n=1540" in leg["problems"][0], "the finding must name the GOVERNING row"
    assert "NEWEST" in leg["problems"][0], leg["problems"][0]

def test_a_SINGLE_incomplete_receipt_still_REDs() -> None:
    """The single-row case is the one the leg was always right about — unchanged by #217."""
    leg = _duty_leg([_duty_row()], [_receipt_row(
        subject=f"registry-attest-{_DUTY_ROUND}",
        detail="nothing ran today. duty=skipped", n=7)])
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "did NOT complete" in leg["problems"][0], leg["problems"][0]
    assert leg["coverage"]["rounds_superseded"] == 0, leg["coverage"]

def test_the_DOMAIN_leg_is_NOT_superseded_by_a_later_row() -> None:
    """A vocabulary fault is not a state a later row settles — the carve-out, pinned.

    An unrecognised token is the WRITER's error, so it is reported even when a later row
    declares a clean completion. Folding it into the supersession would let a typo be
    buried by a subsequent correct row, which is the fabrication direction the domain leg
    exists to refuse.
    """
    bad = _receipt_row(subject=f"registry-attest-{_DUTY_ROUND}",
                       detail="the round finished. duty=done", n=1500)
    bad["ts"] = _plus(_DUTY_BOUND, 0.9)
    good = _receipt_row(subject=f"registry-attest-{_DUTY_ROUND}",
                        detail="6 of 6 fragments written back. duty=completed", n=1529)
    good["ts"] = _plus(_DUTY_BOUND, 1.5)
    leg = _duty_leg([_duty_row()], [bad, good])

    assert len(leg["problems"]) == 1, leg["problems"]
    assert "outside the domain" in leg["problems"][0], leg["problems"][0]
    assert "n=1500" in leg["problems"][0], leg["problems"][0]

def test_a_row_that_DECLARES_NOTHING_is_NOT_a_receipt() -> None:
    """THE false-clean fix (#160), and the probe the first version would have passed.

    Measured instance: the leg accepted n=1003 — subject `registry-attest-2026-09-25`,
    appended 06:08:53Z — as the round's receipt, while n=1003 is the DISPATCH record and the
    completion landed later (n=1007, 06:14:25Z) under a different subject. A subject match
    was enough, so the round reported 0 problems while it was incomplete.

    The omission is the failure the mechanism cannot see: a row that declares nothing is not
    a duty that owed nothing.
    """
    leg = _duty_leg(
        [_duty_row()],
        [_receipt_row(detail="Registry attestation — the round. NO REPLY OWED on this row.")],
    )
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "NO duty receipt" in leg["problems"][0], leg["problems"][0]
    assert "declare no `duty=`" in leg["problems"][0], (
        "the finding must say that a row matched and declared nothing, so the reader can "
        f"tell this from an absent row: {leg['problems'][0]}"
    )
    assert leg["coverage"]["duties_judged"][0]["rows_matched"] == 1, leg["coverage"]
    assert leg["coverage"]["duties_judged"][0]["receipts"] == 0, leg["coverage"]

def test_a_PROSE_mention_of_the_duty_is_not_a_declaration() -> None:
    """Positional read: a sentence that merely SAYS the round completed is not the field.

    This is the n=405 clause 5 damage on a new field — the rows carrying a receipt discuss
    completion at length in prose, so a whole-detail scan would read the discussion as the
    declaration.
    """
    leg = _duty_leg(
        [_duty_row()],
        [_receipt_row(detail="the round completed and all six were answered. head=abc123")],
    )
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "NO duty receipt" in leg["problems"][0], leg["problems"][0]

def test_an_HOUR_BEARING_subject_names_the_round() -> None:
    """#159: the round is a DATE, so an hour-keyed receipt must still resolve.

    `factory-triage-patrol` writes `patrol-verify-2026-09-25T06` — exact equality could never
    match it, so a duty that DID complete reported MISSING.
    """
    leg = _duty_leg(
        [_duty_row(name="factory-triage-patrol", prompt=_RECEIPT_PROMPT.replace(
            "registry-attest", "patrol-verify"))],
        [_receipt_row(subject=f"patrol-verify-{_DUTY_ROUND}T06",
                      detail="the patrol ran. duty=completed")],
    )
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["duties_judged"][0]["receipts"] == 1, leg["coverage"]

def test_a_DECORATED_AFTER_the_date_subject_names_the_round() -> None:
    """#159: a decoration that FOLLOWS the date is reached by the ruled prefix."""
    leg = _duty_leg(
        [_duty_row()],
        [_receipt_row(subject=f"registry-attest-{_DUTY_ROUND}-writeback",
                      detail="the write-back round. duty=completed")],
    )
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["duties_judged"][0]["receipts"] == 1, leg["coverage"]

def test_an_INFIX_decorated_subject_is_NOT_reached_by_the_ruled_prefix() -> None:
    """THE BOUND, stated so the widening is not oversold (#159).

    The ruled key is `subject.startswith(f"{stem}-{round_date}")`, so a decoration AFTER the
    date is reached (`...-2026-09-25T06`, `...-2026-09-25-writeback`) while one BEFORE it is
    not: `registry-attest-writeback-2026-09-25` does not start with
    `registry-attest-2026-09-25`. Measured, all four shapes, at the ruled key:

        registry-attest-2026-09-25            -> reached  (exact)
        registry-attest-2026-09-25T06         -> reached  (hour, the #159 defect)
        registry-attest-2026-09-25-writeback  -> reached  (word suffix)
        registry-attest-writeback-2026-09-25  -> NOT      (infix decoration)

    The last is the live subject of n=1007 — the instance the coupling rationale cites — so
    the ruled widening does not reach it. This probe PINS that bound rather than widening
    past the ruling on this lane's own reading: the key is a ruled shape, and the
    measurement was reported to HQ instead. It is here so a future reader cannot mistake the
    prefix for a general "the subject mentions the round" rule.
    """
    leg = _duty_leg(
        [_duty_row()],
        [_receipt_row(subject="registry-attest-writeback-2026-09-25",
                      detail="the write-back round. duty=completed")],
    )
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "NO duty receipt" in leg["problems"][0], leg["problems"][0]

def test_the_PREFIX_IS_BOUNDARY_CHECKED_so_a_longer_date_cannot_match() -> None:
    """#159's guard: `...-2026-09-25` must NOT match `...-2026-09-250`.

    A bare `startswith` would read a DIFFERENT date's subject as this round's — the widening
    would trade a false MISSING for a false CLEAN, which is the defect it is fixing.
    """
    leg = _duty_leg(
        [_duty_row()],
        [_receipt_row(subject=f"registry-attest-{_DUTY_ROUND}0",
                      detail="some other round. duty=completed")],
    )
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "NO duty receipt" in leg["problems"][0], leg["problems"][0]

def test_the_EXACT_match_case_still_resolves() -> None:
    """The widening is strictly more permissive — the original shape must not regress."""
    leg = _duty_leg([_duty_row()], [_receipt_row()])
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["duties_judged"][0]["receipts"] == 1, leg["coverage"]

def test_a_row_declaring_no_receipt_is_NOT_JUDGED_COUNTED_and_since_506_a_PROBLEM() -> None:
    """P29, and #506 half 2 which SUPERSEDES this probe's original expectation.

    The original assertion was `len(problems) == 1` with the comment "the undeclared row is
    not judged and adds no problem" — the row added no problem, so `problems: 0` was
    indistinguishable from a clean round for a duty the leg could not look at. That is the
    exact false negative #506 closed: an unjudged duty is now a FINDING with the job named.
    The P29 half is unchanged and still bites — the population is COUNTED by name, never a
    bare zero.
    """
    leg = _duty_leg(
        [_duty_row(), _duty_row(name="factory-measurement-daily", prompt="no declaration here")],
        [],
    )
    assert leg["coverage"]["jobs_declaring_receipt"] == 1, leg["coverage"]
    assert leg["coverage"]["jobs_undeclared"] == 1, leg["coverage"]
    assert leg["coverage"]["undeclared_jobs"] == ["factory-measurement-daily"], leg["coverage"]
    # the declared row is judged and MISSING (it owes a receipt nobody wrote), and the
    # undeclared one REDS under #506 -- two problems, and the #506 one NAMES the job
    assert len(leg["problems"]) == 2, leg["problems"]
    findings = [p for p in leg["problems"] if "#506" in p]
    assert len(findings) == 1, leg["problems"]
    assert "factory-measurement-daily" in findings[0], findings[0]
    assert any("NO duty receipt" in p for p in leg["problems"]), leg["problems"]

def test_a_census_where_NO_row_declares_a_receipt_is_a_FINDING_not_a_silent_NOT_RUN() -> None:
    """#506 half 2. This probe used to assert `status == "NOT RUN"` and `problems == []` —
    the silence itself. A census in which NOT ONE attributed duty declares a receipt is now
    the loudest possible finding: the leg judged nothing because nothing was declarable, and
    it says so by NAMING the jobs rather than by rendering a status that reads as deferred.
    """
    leg = _duty_leg([_duty_row(prompt="no declaration here")], [])
    assert leg["status"] == "ASSERTED", leg
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "factory-registry-attest" in leg["problems"][0], leg["problems"][0]
    # the reason still names the POPULATION it enumerated, so the reader can tell a census
    # that declared nothing from one that declared something and found it missing
    assert "receipt_subject:" in (leg["reason"] or ""), leg["reason"]
    assert "NO DUTY WAS JUDGED" in (leg["reason"] or ""), leg["reason"]

def test_the_round_comes_from_the_rows_own_fire_instant_never_a_parsed_schedule() -> None:
    """`last_run_at` is stamped at DISPATCH, so it names the round the trigger woke.

    The tree is pinned to an EARLIER declared bound rather than moving the fixture instant,
    because the assertion's whole power is that the round date (09-24) differs from the read
    instant (09-25) — a schedule parse would name 09-25. Moving the instant forward to clear
    the #175 bound would have made the probe unable to tell the two derivations apart.

    The second arm is the same row under this factory's real bound: 09-24 predates it, so
    the round is EXCUSED and never judged. One row, two bounds, two outcomes — which is the
    property #175 exists to establish.
    """
    early = _duty_tree(invariants={"duty_receipt_declared": "2026-09-20T00:00:00Z"})
    leg = _duty_leg([_duty_row(last_run_at="2026-09-24T06:00:11Z")], [], repo=early)
    assert leg["coverage"]["duties_judged"][0]["round"] == "2026-09-24", leg["coverage"]
    assert "registry-attest-2026-09-24" in leg["problems"][0], leg["problems"][0]

    bounded = _duty_leg([_duty_row(last_run_at="2026-09-24T06:00:11Z")], [])
    assert bounded["coverage"]["duties_judged"] == [], bounded["coverage"]
    assert bounded["coverage"]["rounds_excused_by_bound"] == 1, bounded["coverage"]

def test_a_row_with_no_fire_instant_is_EXCUSED_and_never_guessed() -> None:
    """A round that cannot be READ is never NAMED: the row is excused with its reason."""
    leg = _duty_leg([_duty_row(last_run_at="")], [])
    assert leg["problems"] == [], leg["problems"]
    assert len(leg["excused"]) == 1, leg["excused"]
    assert "no fire instant" in leg["excused"][0], leg["excused"][0]

def test_a_MENTION_of_the_declaration_is_not_a_DECLARATION() -> None:
    """Prose about a field must not satisfy it — the declaration is a whole LINE (n=405)."""
    prompt = (
        "Thin trigger only — do NOT execute any project work yourself.\n"
        "The old text said receipt_subject: registry-attest and it was removed.\n"
    )
    assert RUNNER.declared_receipt_stem(prompt) is None, "a mid-sentence mention declared one"
    assert RUNNER.declared_receipt_stem(_RECEIPT_PROMPT) == "registry-attest"

def test_the_duty_leg_names_attested_at_as_RESULTING_STATE_never_the_receipt() -> None:
    """Criterion 4: a stale attestation is RESULTING STATE, and a stale one must not stand
    in for the missing receipt — the receipt is the ledger run row, and it is still absent."""
    store = Path(tempfile.mkdtemp())
    (store / "probe.json").write_text(
        json.dumps({"factory": "probe", "attested_at": "2026-09-19T00:00:00Z"}),
        encoding="utf-8",
    )
    leg = _duty_leg([_duty_row()], [], store=store)
    assert leg["coverage"]["attested_at_state"] == {"probe": "2026-09-19T00:00:00Z"}, leg["coverage"]
    assert len(leg["problems"]) == 1, "a stale attestation must not excuse the missing receipt"

def test_the_duty_leg_is_WIRED_into_the_runner_and_prints_its_population() -> None:
    """A leg that is not wired is not a leg: the runner's own output must carry it."""
    rc, out, err = _run([], [], cron_rows=[_duty_row()], prefixes=["factory-"])
    assert "LEG duty-receipt" in out, out
    assert "1 row(s) declare a receipt" in out, out
    assert "RESULTING STATE, never the receipt" in out, out
    # #487: the bound is read through the SAME reader the runner was handed, never the LIVE
    # one. A probe that resolved this field by a second path would be the very defect #487
    # fixed — and it would assert the shipped half REFUSES while the runner, handed the
    # reader whose fallback keeps the probes runnable, JUDGES. The REFUSAL path is exercised
    # through `main()` by the probe below, which drives a refusing reader.
    assert _duty_scope(RUNNER.REPO)[2] == "", "the default reader must not refuse here"
    assert "NO duty receipt" in out, "a missing duty receipt must reach the report"
    assert rc == 1, "the leg's verdict must fail the run"


def test_a_REFUSED_duty_bound_is_HONOURED_through_the_runner() -> None:
    """#487 acceptance, the FAIL arm: a reader that REFUSES must reach the verdict.

    The bound is injected, so a probe can drive a state the live tree cannot be in — a
    declaration that is present but unreadable — without the live tree deciding the verdict.
    A REFUSAL is neither a skip nor a pass: no round may be judged while the bound is
    unreadable, and the run must be RED naming the key it could not read. Without this arm
    the injection could be wired to nothing and every other probe would still pass.
    """
    def _refusing(_repo):
        return None, "", (
            "`duty_receipt_declared` is declared in this tree but cannot be read: "
            "not an instant — REFUSED: probe"
        )

    rc, out, _ = _run([], [], cron_rows=[_duty_row()], prefixes=["factory-"],
                      duty_scope=_refusing)
    assert rc == 1, f"a refused bound is a defect, got rc={rc}\n{out}"
    assert "LEG duty-receipt" in out, out
    assert "cannot be read" in out, out[-3000:]
    assert "REFUSED" in out, out[-3000:]


def test_a_round_YOUNGER_than_the_residual_is_NOT_JUDGED_with_its_AGE_printed() -> None:
    """#200's whole defect: a round IN FLIGHT read as a missing duty.

    The filed specimen judged three live lanes MISSING at age 1136 s. A round younger than
    the declared residual has a trigger that fired and a lane that has not finished, which
    this leg cannot tell from a duty never done -- so it must not judge it. The age AND the
    window are both asserted: a bare skip would trade a false RED for a false clean (#160).
    """
    young_read = _plus(_DUTY_FIRE, 0.3)          # 18 min after the fire, well inside 30 min
    leg = _duty_leg([_duty_row()], [], read_at=young_read)
    assert leg["problems"] == [], (
        f"a round still inside its residual must not be judged MISSING: {leg['problems']}")
    assert leg["coverage"]["rounds_excused_by_residual"] == 1, leg["coverage"]
    line = [e for e in leg["excused"] if "IN FLIGHT" in e]
    assert len(line) == 1, leg["excused"]
    assert "18.0 min old" in line[0], line[0]      # the AGE
    assert "30.0 min" in line[0], line[0]          # the WINDOW, beside it
    assert "factory-registry-attest" in line[0], "the round is NAMED, never a bare count"

def test_the_residual_is_PRINTED_in_the_coverage_beside_its_sibling() -> None:
    """Criterion 3: the window travels in the coverage, so an ACCEPTED window is never a
    hidden one -- the same discipline PUBLISH_RESIDUAL_SECS follows for the pusher.

    Since #449 there is no single fleet residual: the coverage carries the DEFAULT and the
    FORM beside the PER-JOB derivations, and a scalar here would be a number no round was
    judged against.
    """
    leg = _duty_leg([_duty_row()], [_receipt_row()])
    assert "residual_secs" not in leg["coverage"], (
        "there is no single fleet residual any more -- a scalar would be a number no round "
        f"was judged against: {leg['coverage'].get('residual_secs')}"
    )
    assert leg["coverage"]["residual_default_secs"] == RUNNER.DUTY_RESIDUAL_DEFAULT_SECS, (
        leg["coverage"]
    )
    # No fires were injected, so this job has no measurable round and falls to the DEFAULT.
    residuals = leg["coverage"]["residuals"]
    assert len(residuals) == 1, residuals
    assert residuals[0]["basis"] == "default", residuals[0]
    assert residuals[0]["residual_secs"] == RUNNER.DUTY_RESIDUAL_DEFAULT_SECS, residuals[0]
    rc, out, err = _run([], [], cron_rows=[_duty_row()], prefixes=["factory-"])
    assert "forward residual:" in out, out[-3000:]
    assert "PER JOB, DERIVED" in out, out[-3000:]
    assert f"{RUNNER.DUTY_RESIDUAL_DEFAULT_SECS} s" in out, out[-3000:]

def test_the_residual_does_NOT_excuse_a_round_OLDER_than_it() -> None:
    """The counter-control, and the half that keeps the fix honest: a window that excused
    everything would make the leg permanently clean, which is the pre-fix defect inverted.

    The same round with the same absence, read PAST the residual, must still read MISSING.
    """
    old_read = _plus(_DUTY_FIRE, 5.0)               # 5 h after the fire, far past 30 min
    leg = _duty_leg([_duty_row()], [], read_at=old_read)
    assert leg["coverage"]["rounds_excused_by_residual"] == 0, leg["coverage"]
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "NO duty receipt" in leg["problems"][0], leg["problems"][0]

def test_the_residual_is_DERIVED_from_the_jobs_OWN_measured_max() -> None:
    """#449 criterion 1: the window is the JOB's, never a fleet constant.

    Three fires, three receipts, the longest 6000 s behind its fire. The assertion is made
    against the MARGIN LAW `tools/gate_budget.py` states -- `margin_for(measured_max) *
    measured_max`, read through the runner's own accessor -- rather than against a number
    copied into this probe, because a copied number would be a second statement of the law
    and would keep passing after the law moved.
    """
    fires = _fires((0.5, 26.0, 50.0))
    ledger = [
        _fire_receipt(0.5, 6000.0, 11),
        _fire_receipt(26.0, 3000.0, 12),
        _fire_receipt(50.0, 1200.0, 13),
    ]
    leg = _duty_leg([_duty_row()], ledger, fires=fires)
    residual = leg["coverage"]["residuals"][0]
    assert residual["basis"] == "derived", residual
    assert residual["measured_rounds"] == 3, residual
    assert residual["measured_max_secs"] == 6000.0, residual
    margin = RUNNER.gate_budget_module().margin_for(6000.0)
    assert abs(residual["margin_x"] - margin) < 1e-9, residual
    assert abs(residual["residual_secs"] - margin * 6000.0) < 1e-6, residual
    assert residual["residual_secs"] > RUNNER.DUTY_RESIDUAL_DEFAULT_SECS, (
        "the job's own measured max exceeds the pre-#449 fleet constant, so the derived "
        f"window must be the WIDER one -- the derivation must not collapse back to it: {residual}"
    )
    # THE OBSERVABLE EFFECT, and it is the #449 harm exactly: this round's age (5400 s at
    # the read) is ABOVE the old fleet constant and BELOW this job's own derived residual,
    # so the round the pre-fix leg called a missing duty is now correctly IN FLIGHT.
    assert 5400.0 > RUNNER.DUTY_RESIDUAL_DEFAULT_SECS, "the fixture must straddle the old value"
    assert leg["coverage"]["rounds_excused_by_residual"] == 1, leg["coverage"]
    assert leg["problems"] == [], leg["problems"]

def test_an_OVER_CADENCE_residual_is_PRINTED_never_refused() -> None:
    """#449 criterion 2: a mutually-unsatisfiable window is REPORTED, not hidden.

    Four fires a day apart with a 7 h measured max give a derived residual of ~28 h -- past
    the job's own 24 h cadence. The two requirements cannot both hold (n=1518 FINDING 3),
    and the honest output is the number AND the statement. So the leg must still judge --
    never refuse, never turn the job's own timing into a problem -- and the rendered report
    must carry the OVER CADENCE line beside the value.
    """
    fires = _fires((0.5, 24.5, 48.5))
    ledger = [
        _fire_receipt(0.5, 25200.0, 21),
        _fire_receipt(24.5, 25200.0, 22),
        _fire_receipt(48.5, 25200.0, 23),
    ]
    leg = _duty_leg([_duty_row()], ledger, fires=fires)
    residual = leg["coverage"]["residuals"][0]
    assert residual["cadence_secs"] == 86400.0, residual
    assert residual["over_cadence"] is True, residual
    assert residual["residual_secs"] >= residual["cadence_secs"], residual
    assert leg["coverage"]["rounds_over_cadence"] == 1, leg["coverage"]
    # NEVER REFUSED, and never a problem in its own right: the leg still returns a verdict
    # over the round, and the duty's timing is reported rather than judged.
    assert leg["status"] == "ASSERTED", leg
    assert leg["problems"] == [], leg["problems"]
    rc, out, err = _run([], ledger, cron_rows=[_duty_row()], prefixes=["factory-"],
                        cron_fires=fires)
    assert "OVER CADENCE" in out, out[-3000:]
    assert "never clamped to the cadence" in out, out[-3000:]

def test_a_MALFORMED_receipt_is_REPORTED_and_proven_to_BITE() -> None:
    """#281 (A), acceptance 1 of ruling n=2003 — and the BITE is the probe.

    THE MEASURED INSTANCE, and it is a real row: n=1966 writes its receipt as
    *"DUTY RECEIPT, duty=completed."* in the prose HEAD and closes with
    *"Session: f4c192c9-… (actor triage)."* — so the canonical terminal run is empty,
    `declared_duty` reads NOTHING, and a lane that declared its completion reads as a lane
    that declared nothing. The author is told to declare the token they believe they
    declared; the reader cannot reach it. Neither "clean" nor "missing duty" describes that
    state, so the leg names it and names the repair.

    PROVEN TO BITE: the second half neuters `mentions_duty` to a constant False and asserts
    the finding MOVES back to the generic no-declaration text. Without that half the
    assertion would pass on any fixture, including one where the finding came from
    something else entirely.
    """
    prose = (
        "TRIAGE CYCLE — patrol-verify-2026-09-25. DUTY RECEIPT, duty=completed.\n"
        "Session: f4c192c9-a8e9-4268-9026-ee3e4970cc8a (actor triage)."
    )
    row = _receipt_row(subject=f"registry-attest-{_DUTY_ROUND}", detail=prose, n=1875)
    leg = _duty_leg([_duty_row()], [row])
    assert leg["coverage"]["receipts_malformed"] == 1, leg["coverage"]
    assert leg["coverage"]["duties_judged"][0]["receipts"] == 0, leg["coverage"]
    assert len(leg["problems"]) == 1, leg["problems"]
    problem = leg["problems"][0]
    assert "MALFORMED RECEIPT" in problem, problem
    assert "OWN VOICE" in problem, problem
    assert "Make it TERMINAL" in problem, problem
    assert "n=1875" in problem, "the finding must NAME the row it is about, by number"
    assert "registry-attest-2026-09-25" in problem, problem
    assert "never a missing duty" in problem, (
        "the finding must refuse the missing-duty reading, because a lane that declared is "
        f"not a lane that did nothing: {problem}"
    )
    # THE BITE: neuter the discriminator and the finding must vanish, leaving the generic
    # no-declaration text behind. A finding that survives this is not this finding.
    neutered = _duty_leg([_duty_row()], [row],
                         predicate=_stub_predicate(mentions_duty=lambda detail: False))
    assert neutered["coverage"]["receipts_malformed"] == 0, (
        f"the malformed class must be produced BY `mentions_duty`: {neutered['coverage']}"
    )
    assert "MALFORMED RECEIPT" not in neutered["problems"][0], (
        f"with the discriminator neutered the generic text must return: {neutered['problems']}"
    )
    assert "declare no `duty=`" in neutered["problems"][0], neutered["problems"][0]

def test_the_OWN_VOICE_discriminator_keeps_a_QUOTED_aside_out() -> None:
    """The discriminator is the #278 helper, and THIS is what proves it is load-bearing.

    A token inside a PARENTHETICAL ASIDE is a CITATION of another row's trailer, and the
    ruling names exactly this as what keeps the detector off a row that quotes a token. The
    probe neuters the own-voice scope — the same scan with the aside-stripping REMOVED — and
    asserts the finding appears, so the clean verdict on the real reader is attributable to
    that scope and not to the fixture happening to be quiet.

    A SECOND discriminator was refused (n=405 PART 5 / n=599), so this probe asserts the
    SHARED reader is the one doing the separating rather than a private walk here.
    """
    aside = (
        "the round was cleared by the repair recorded in n=1999 (whose trailer carries "
        "duty=completed), and nothing further is owed."
    )
    row = _receipt_row(subject=f"registry-attest-{_DUTY_ROUND}", detail=aside, n=2000)
    real = RUNNER.field_predicate_readers()
    assert real.mentions_duty(aside) is False, "the shared reader must drop the aside"
    assert _lexical_duty_scan(aside) is True, "the lexical control must keep it, or it proves nothing"
    leg = _duty_leg([_duty_row()], [row])
    assert leg["coverage"]["receipts_malformed"] == 0, leg["coverage"]
    assert "MALFORMED RECEIPT" not in leg["problems"][0], leg["problems"][0]
    neutered = _duty_leg([_duty_row()], [row],
                         predicate=_stub_predicate(mentions_duty=_lexical_duty_scan))
    assert neutered["coverage"]["receipts_malformed"] == 1, (
        "without the own-voice scope the aside must be read as a mention — that is the "
        f"over-inclusion the scope exists to narrow: {neutered['coverage']}"
    )

def test_a_repair_rows_round_is_READ_through_its_DECLARING_row() -> None:
    """The n=2000 population control, stated as a probe because the ruling states it.

    n=2000 is a repair record that QUOTES the token and then MENTIONS it unquoted in its own
    prose ("the receipt row declares duty=completed in its TEXT"). No lexical reader can tell
    that mention from a declaration, so the ruling keeps the detector off n=2000 by its
    POPULATION rather than by a cleverer predicate: the round it keys (2026-10-03) also
    carries n=1999, which DECLARES. So the round is judged clean and the repair record is
    never asked the question — which is what this probe pins, so a future change that made
    n=2000 the only row of its round would show up here as the behaviour change it is.
    """
    repair = _receipt_row(
        subject=f"registry-attest-{_DUTY_ROUND}",
        detail=("the repair of n=1999: the receipt row declares duty=completed in its "
                "TEXT. Session: 8f0c (actor triage)."),
        n=2000,
    )
    declaring = _receipt_row(subject=f"registry-attest-{_DUTY_ROUND}", n=1999)
    leg = _duty_leg([_duty_row()], [declaring, repair])
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["receipts_malformed"] == 0, leg["coverage"]
    assert leg["coverage"]["duties_judged"][0]["receipts"] == 1, leg["coverage"]

def test_the_PRIOR_round_is_JUDGED_when_the_newest_is_IN_FLIGHT() -> None:
    """#281 (B), acceptance 2 — the permanent gap this fixes, and it is a REAL one.

    `factory-triage-patrol` fires every 6 h and its own derived residual reaches 3.77 d, so
    the round the leg judged was ALWAYS the one still in flight: the `continue` ended the
    job's turn and no round was ever examined. Measured live at 2026-10-12T18:40Z, the job
    had no round judged at all.

    Here the newest fire is 18 min old (inside the 30 min default residual) and the fire
    before it is a day older, with NO receipt: the leg must judge the PRIOR round and NAME
    it, and the excuse must still name the round it declined to judge.
    """
    newest = _plus(_DUTY_BOUND, 74.0)
    prior = _plus(_DUTY_BOUND, 50.0)
    read_at = _plus(newest, 0.3)                      # 18 min after the newest fire
    row = _duty_row(last_run_at=newest)
    # The row's OWN scheduling record, carried since #281 (ruling n=2003): the reason a
    # round was skipped is the cadence against the residual, so the finding must name the
    # schedule it belongs to rather than leaving the reader to guess it.
    row["cron_expr"] = "0 */6 * * *"
    row["next_run_at"] = _plus(newest, 6.0)
    fires = [
        {"job_id": row["id"], "job_name": row["name"], "started_at": prior},
        {"job_id": row["id"], "job_name": row["name"], "started_at": newest},
    ]
    leg = _duty_leg([row], [], read_at=read_at, fires=fires)
    assert leg["coverage"]["rounds_judged_by_fallback"] == 1, leg["coverage"]
    assert leg["coverage"]["rounds_prior_unreadable"] == 0, leg["coverage"]
    judged = leg["coverage"]["duties_judged"]
    assert len(judged) == 1, judged
    assert judged[0]["round"] == prior[:10], (
        f"the PRIOR round must be the one judged, and it must be NAMED: {judged[0]}"
    )
    assert judged[0]["fallback_from"] == newest[:10], judged[0]
    assert judged[0]["fired"] == prior, judged[0]
    assert len(leg["problems"]) == 1, leg["problems"]
    problem = leg["problems"][0]
    assert "PRIOR round" in problem, problem
    assert "is NOT JUDGED" in problem, problem
    assert newest[:10] in problem, "the round being declined must be named too"
    assert "0 */6 * * *" in problem, (
        f"the PRIOR-round note must carry the row's own schedule: {problem}"
    )
    in_flight = [e for e in leg["excused"] if "IN FLIGHT" in e]
    assert len(in_flight) == 1, leg["excused"]
    assert newest[:10] in in_flight[0], in_flight[0]

def test_a_prior_round_that_cannot_be_DERIVED_is_NOT_JUDGED_with_its_reason() -> None:
    """#281 (B)'s bound — acceptance 3, and it is the #112/#160 law, not a nicety.

    The ruling is explicit: where the prior round cannot be derived the leg prints NOT JUDGED
    with its reason, NEVER a silent fallback to the old behaviour. A fallback that cannot
    judge must say so, because silence here is exactly the false clean the leg exists to
    catch — and the old behaviour was a silent one.

    The instant is READ from the job's own run record and never composed (`next_run_at -
    last_run_at` is the #175 class wearing arithmetic), so a job whose record holds only the
    in-flight fire has no prior round to name.
    """
    newest = _plus(_DUTY_BOUND, 74.0)
    read_at = _plus(newest, 0.3)
    row = _duty_row(last_run_at=newest)
    fires = [{"job_id": row["id"], "job_name": row["name"], "started_at": newest}]
    leg = _duty_leg([row], [], read_at=read_at, fires=fires)
    assert leg["coverage"]["rounds_prior_unreadable"] == 1, leg["coverage"]
    assert leg["coverage"]["rounds_judged_by_fallback"] == 0, leg["coverage"]
    assert leg["coverage"]["duties_judged"] == [], (
        f"no round may be judged from a fire the record does not date: {leg['coverage']}"
    )
    assert leg["problems"] == [], (
        f"an unexamined round is not a RED — it is a stated absence: {leg['problems']}"
    )
    stated = [e for e in leg["excused"] if "NO fire before it" in e]
    assert len(stated) == 1, leg["excused"]
    assert "NOT JUDGED" in stated[0], stated[0]
    assert "no prior round can be NAMED" in stated[0], stated[0]

def test_the_runner_PRINTS_the_prior_round_and_the_malformed_class() -> None:
    """Acceptance 4, the printing half: the leg's population and its two new verdicts.

    A verdict that never reaches the report is a verdict no reader can act on, and the
    population line is what keeps an empty or one-row population from reading as a clean
    box (#160). Both new classes are asserted at the RENDERED output, not at the coverage
    dict, because the coverage dict is what the leg computes and the report is what the
    operator reads.
    """
    now = dt.datetime.now(dt.timezone.utc)
    iso = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")
    newest = iso(now - dt.timedelta(minutes=10))
    prior = iso(now - dt.timedelta(hours=24, minutes=10))
    prior_date = prior[:10]
    row = _duty_row(last_run_at=newest)
    fires = [
        {"job_id": row["id"], "job_name": row["name"], "started_at": prior},
        {"job_id": row["id"], "job_name": row["name"], "started_at": newest},
    ]
    malformed = {
        "n": 1875, "ts": prior, "event": "run", "actor": "triage",
        "subject": f"registry-attest-{prior_date}",
        "detail": (f"TRIAGE CYCLE — patrol-verify-{prior_date}. DUTY RECEIPT, "
                   f"duty=completed.\nSession: 8f0c (actor triage)."),
    }
    rc, out, err = _run([], [malformed], cron_rows=[row], prefixes=["factory-"],
                        cron_fires=fires)
    assert "LEG duty-receipt" in out, out
    assert "jobs: 1 enabled row(s) attributed to this factory of 1 read across" in out, out
    assert "duties: 1 row(s) declare a receipt" in out, out
    assert "were judged as the PRIOR fire's round" in out, out[-4000:]
    assert "MALFORMED RECEIPT" in out, out[-4000:]
    assert "make it terminal" in out, out[-4000:]
    assert f"round {prior_date}" in out, "the judged round must be NAMED in the report"
    assert rc == 1, "both new classes are findings, so the run must fail"


# ------------------------------------------------------------------- kit-drift leg

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

def test_the_drift_leg_counts_same_diff_and_absent_apart() -> None:
    """Three DIFFERENT facts. Folding them would hide which one a member has."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mpath, fpath = _synthetic_kit(
            root,
            files={"tools/a.py": b"a", "tools/b.py": b"b", "tools/c.py": b"c"},
            members={"alpha": {"same": {"tools/a.py": b"a"}, "diff": {"tools/b.py": b"WRONG"}}},
        )
        leg = RUNNER.kit_drift_leg(manifest_path=mpath, fleet_path=fpath, read_at="probe")
        cov = leg["coverage"]
        assert leg["problems"] == [], leg["problems"]
        assert cov["manifest_cells"] == {"same": 1, "DIFF": 1, "ABSENT": 1}, cov["manifest_cells"]
        member = cov["members"][0]
        assert member["slug"] == "alpha" and member["reachable"]
        assert member["absent_files"] == ["tools/c.py"], member["absent_files"]
        assert member["diff_files"] == ["tools/b.py"], member["diff_files"]

def test_a_member_is_never_a_PROBLEM_even_when_fully_stale() -> None:
    """Drift belongs to the MEMBER. Reddening this factory's patrol for another lane's
    backlog would make our verdict a function of that lane's queue -- the coupling the
    leg's whole design avoids -- and a leg that reds forever teaches readers to ignore a
    red patrol (#139's permanent-false-positive class)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mpath, fpath = _synthetic_kit(
            root, files={"tools/a.py": b"a"},
            members={"alpha": {"diff": {"tools/a.py": b"DIFFERENT"}}},
        )
        leg = RUNNER.kit_drift_leg(manifest_path=mpath, fleet_path=fpath, read_at="probe")
        assert leg["problems"] == [], f"drift must not red the patrol: {leg['problems']}"
        assert leg["coverage"]["manifest_cells"]["DIFF"] == 1

def test_a_STALE_SHARED_SURFACE_writer_is_a_PROBLEM_and_an_absent_one_is_not() -> None:
    """#514, ruled at ledger n=3792. THE TWO ARMS ARE THE WHOLE POINT.

    A `shared-surface` file writes a box-wide store, so a member's stale copy mutates state
    every factory reads -- that is not that member's backlog, it is this factory's hazard,
    and it must red here. Its ABSENCE is the SAFE state: a factory that does not carry the
    writer never writes the surface, so flagging absence would punish the members that did
    nothing wrong.

    The third arm is the CONTROL the first would pass without: the SAME diverging tree with
    the classification removed reads clean. That is what makes the problem a function of the
    declaration rather than of the bytes -- and it is why the class is read from the
    manifest's own map instead of being inferred from what the file looks like.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # ARM 1 -- declared shared-surface, member's copy DIFFERS -> exactly one problem,
        # naming BOTH the member and the file.
        mpath, fpath = _synthetic_kit(
            root, files={"tools/questions": b"current"},
            members={"stale": {"diff": {"tools/questions": b"superseded"}}},
            classes={"tools/questions": "shared-surface"},
        )
        leg = RUNNER.kit_drift_leg(manifest_path=mpath, fleet_path=fpath, read_at="probe")
        assert len(leg["problems"]) == 1, leg["problems"]
        assert "`stale`" in leg["problems"][0], leg["problems"][0]
        assert "tools/questions" in leg["problems"][0], leg["problems"][0]
        cells = leg["coverage"]["shared_surface"]["cells"]
        assert cells == {"same": 0, "DIFF": 1, "ABSENT": 0}, cells

        # ARM 2 -- same fixture, the member does NOT carry the file -> no problem, and the
        # safe state is RECORDED rather than inferred from a total.
        mpath2, fpath2 = _synthetic_kit(
            root / "absent", files={"tools/questions": b"current"},
            members={"silent": {"same": {"tools/other.py": b"x"}}},
            classes={"tools/questions": "shared-surface"},
        )
        leg2 = RUNNER.kit_drift_leg(manifest_path=mpath2, fleet_path=fpath2, read_at="probe")
        assert leg2["problems"] == [], leg2["problems"]
        assert leg2["coverage"]["shared_surface"]["cells"]["ABSENT"] == 1, \
            leg2["coverage"]["shared_surface"]["cells"]

        # ARM 3 -- CONTROL: the identical DIFF with NO classification reads clean, so arm 1
        # is measuring the declaration and not the divergence.
        mpath3, fpath3 = _synthetic_kit(
            root / "unclassified", files={"tools/questions": b"current"},
            members={"stale": {"diff": {"tools/questions": b"superseded"}}},
        )
        leg3 = RUNNER.kit_drift_leg(manifest_path=mpath3, fleet_path=fpath3, read_at="probe")
        assert leg3["problems"] == [], f"the class must be load-bearing: {leg3['problems']}"
        assert leg3["coverage"]["shared_surface"]["files"] == [], \
            leg3["coverage"]["shared_surface"]

def test_an_unreachable_member_is_reported_never_silently_skipped() -> None:
    """A member whose repo is absent is NAMED. A sweep that silently dropped it would
    report a smaller population as if it were the whole one."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mpath, fpath = _synthetic_kit(root, files={"tools/a.py": b"a"}, members={})
        fleet = json.loads(fpath.read_text())
        fleet["factories"].append({"slug": "ghost", "repo": str(root / "does-not-exist")})
        fpath.write_text(json.dumps(fleet), encoding="utf-8")
        leg = RUNNER.kit_drift_leg(manifest_path=mpath, fleet_path=fpath, read_at="probe")
        cov = leg["coverage"]
        assert cov["members_unreachable"] == ["ghost"], cov["members_unreachable"]
        assert cov["members_reachable"] == 0
        assert any("no member repository was reachable" in p for p in leg["problems"]), \
            leg["problems"]

def test_an_UNREADABLE_member_root_is_recorded_unreachable_never_raised() -> None:
    """#429: a member root the box cannot READ is UNREACHABLE, not a traceback.

    `Path.is_dir()` answers False for a root that is ABSENT, but it RE-RAISES when a
    PARENT of the root denies traversal, because EACCES is not among the errors pathlib
    ignores. So a member repo under a mode-700 home -- a CI runner's `/root` -- raised
    straight out of `kit_drift_leg`, on the very leg whose job is to record that the member
    could not be read, and took the whole sweep with it.

    Measured in inferhub-watch run 37587867752, head 569088a, job `validate`, Python
    3.12.14: `PermissionError: [Errno 13] Permission denied: '/root/inferhub-watch'` at
    `pathlib.py:840`, raised from the member's own `kit_drift_leg` line 1556 -- the
    byte-identical `if not root.is_dir():` this probe now guards.

    The failure is DRIVEN, never simulated with a permission bit, for the reason the
    notify-receipt leg states at its own read-failure probe: this gate runs as root on this
    box, so a `chmod 000` parent is traversed happily and the probe would pass for the
    wrong reason. A second, independent reason applies here: this box's Python is 3.14,
    where `is_dir` delegates to `os.path.isdir` and swallows the error -- so only a DRIVEN
    raise exercises the code path the member's Python takes.

    A missing root and an unreadable one are the same class with DIFFERENT remedies (a
    stale fleet entry versus a permissions problem on the member's box), so the reason is
    asserted to reach the RENDER, which is a second surface.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mpath, fpath = _synthetic_kit(root, files={"tools/a.py": b"a"}, members={})
        fleet = json.loads(fpath.read_text())
        guarded = root / "unreadable"
        fleet["factories"].append({"slug": "locked", "repo": str(guarded)})
        fpath.write_text(json.dumps(fleet), encoding="utf-8")

        real_is_dir = Path.is_dir

        def denying_is_dir(self, *args, **kwargs):
            if self == guarded:
                raise PermissionError(13, "Permission denied", str(self))
            return real_is_dir(self, *args, **kwargs)

        with mock.patch.object(Path, "is_dir", denying_is_dir):
            leg = RUNNER.kit_drift_leg(manifest_path=mpath, fleet_path=fpath, read_at="probe")
            text = RUNNER.render([leg], [], slug="owner/repo", read_at="probe", issues=[])

        cov = leg["coverage"]
        assert cov["members_unreachable"] == ["locked"], cov["members_unreachable"]
        assert cov["members_reachable"] == 0, cov["members_reachable"]
        member = cov["members"][0]
        assert member["reachable"] is False, member
        assert "PermissionError" in member["reason"], (
            f"the reason must NAME the failure class -- an unreadable root and an absent "
            f"one share the UNREACHABLE verdict but not the remedy: {member}"
        )
        assert "UNREACHABLE" in text and "PermissionError" in text, (
            f"the reason must reach the RENDER, which is a second surface:\n{text}"
        )
        assert any("no member repository was reachable" in p for p in leg["problems"]), \
            leg["problems"]

def test_the_meta_factory_is_excluded_from_its_own_drift_sweep() -> None:
    """This factory IS the template source: comparing it against its own manifest would
    report every file identical and inflate the totals with a tautology."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mpath, fpath = _synthetic_kit(root, files={"tools/a.py": b"a"}, members={})
        fleet = json.loads(fpath.read_text())
        fleet["factories"].append({"slug": "meta-factory", "repo": str(root)})
        fpath.write_text(json.dumps(fleet), encoding="utf-8")
        leg = RUNNER.kit_drift_leg(manifest_path=mpath, fleet_path=fpath, read_at="probe")
        assert leg["coverage"]["members_declared"] == 0, leg["coverage"]["members_declared"]
        assert leg["coverage"]["manifest_cells_total"] == 0

def test_an_absent_manifest_EXAMINES_NOTHING_and_says_so() -> None:
    """The examined-nothing case is this leg's ONLY problem: with no reference there is
    nothing to measure, and a clean sweep over no population is not a verdict."""
    with tempfile.TemporaryDirectory() as tmp:
        leg = RUNNER.kit_drift_leg(
            manifest_path=Path(tmp) / "absent.json", fleet_path=Path(tmp) / "fleet.json",
            read_at="probe",
        )
        assert leg["status"] == "NOT RUN", leg["status"]
        assert any("examined NOTHING" in p for p in leg["problems"]), leg["problems"]

def test_an_absent_manifest_RENDERS_as_NOT_RUN_never_a_traceback() -> None:
    """The render path is a SECOND surface, and a leg that reports correctly but
    crashes while printing has reported nothing.

    Measured 2026-09-25: the kit-drift branch read `coverage["manifest_cells"]`
    unconditionally, so the absent-manifest path -- the one that exists to REPORT the
    absence -- raised KeyError instead. It was reachable in the TEMPLATE copy, whose
    REPO resolves to TEMPLATE/ where `registry/kit.json` is factory data and never
    ships. Every other kit-drift probe injects a manifest, so none of them could see it.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mpath, fpath = _synthetic_kit(root, files={"tools/a.py": b"a"}, members={})
        mpath.unlink()  # the manifest is ABSENT: the NOT RUN path
        out = io.StringIO()
        RUNNER.main(
            [], board_fn=lambda slug: [], slug_fn=lambda: "owner/repo",
            rows_fn=lambda: [], cron_rows_fn=lambda: ([], ["probe-home"], []),
            cron_fires_fn=lambda: [],
            prefixes_fn=lambda: [], log_dir=_EMPTY_LOG_DIR,
            scores_dir_fn=lambda: _EMPTY_SCORES_DIR,
            kit_manifest=mpath, fleet_manifest=fpath,
            out=lambda *a, **k: print(*a, file=out, **k),
            err=lambda *a, **k: None,
            publish_fn=_stub_publish_leg,
            shared_tree_fn=_stub_shared_tree_rider,
            # #133: the driverless-lane leg's goal store and its turn-in-flight read are
            # injected here for the same reason every other live surface is -- and the
            # defaults WITHHOLD the driven claim (empty store, no turn open) rather than
            # granting one, so a probe that never asserts a driver cannot read one.
            driverless_goals_fn=lambda: _EMPTY_GOAL_STORE,
            driverless_turn_open_fn=lambda: {},
            # #330: the ref-role store is injected for the same reason the ruling table is.
            ref_role_exemptions_path=_NO_REF_ROLE_EXEMPTIONS,
        # #507: the criterion-path store, injected for the same reason.
        criterion_exemptions_fn=lambda: _NO_CRITERION_EXEMPTIONS,
        )
        text = out.getvalue()
        assert "LEG kit-drift" in text, text
        assert "NOT RUN" in text, text
        assert "examined NOTHING" in text, text
        assert "manifest_cells" not in text, text

def test_an_empty_manifest_is_a_FAILURE_not_a_universal_agreement() -> None:
    """A manifest declaring no files would agree with every tree in existence."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "kit.json").write_text(json.dumps({"files": {}}), encoding="utf-8")
        (root / "fleet.json").write_text(json.dumps({"factories": []}), encoding="utf-8")
        leg = RUNNER.kit_drift_leg(manifest_path=root / "kit.json",
                                   fleet_path=root / "fleet.json", read_at="probe")
        assert any("declares NO files" in p for p in leg["problems"]), leg["problems"]

def test_the_MUTATION_control_flips_same_to_DIFF_without_touching_a_member_tree() -> None:
    """The probe that makes the leg's green mean something.

    A leg reporting `same` for every cell is exactly what a vacuous implementation would
    print, so the leg is driven twice over ONE synthetic pair: once clean, and once with a
    single byte moved in a file that previously matched. The moved byte is written to a
    COPY of the member tree, so no real repository is touched -- and the live member trees
    are compared before and after, so that claim is measured rather than asserted.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mpath, fpath = _synthetic_kit(
            root, files={"tools/a.py": b"a", "tools/b.py": b"b"},
            members={"alpha": {"same": {"tools/a.py": b"a", "tools/b.py": b"b"}}},
        )
        before = RUNNER.kit_drift_leg(manifest_path=mpath, fleet_path=fpath, read_at="p1")
        assert before["coverage"]["manifest_cells"] == {"same": 2, "DIFF": 0, "ABSENT": 0}, \
            before["coverage"]["manifest_cells"]

        # The mutation lands in a COPY of the member tree, never the tree itself.
        member_root = root / "alpha"
        copied = root / "alpha-copy"
        shutil.copytree(member_root, copied)
        (copied / "tools/a.py").write_bytes(b"a-MUTATED")
        fleet = json.loads(fpath.read_text())
        fleet["factories"][0]["repo"] = str(copied)
        fpath.write_text(json.dumps(fleet), encoding="utf-8")

        after = RUNNER.kit_drift_leg(manifest_path=mpath, fleet_path=fpath, read_at="p2")
        assert after["coverage"]["manifest_cells"] == {"same": 1, "DIFF": 1, "ABSENT": 0}, \
            after["coverage"]["manifest_cells"]
        assert after["coverage"]["members"][0]["diff_files"] == ["tools/a.py"]

        # The ORIGINAL member tree is byte-identical: the mutation was on a copy.
        assert (member_root / "tools/a.py").read_bytes() == b"a"
        assert (member_root / "tools/b.py").read_bytes() == b"b"

def test_the_leg_reaches_the_RENDERED_report() -> None:
    """A leg whose output never renders is a leg nobody reads."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mpath, fpath = _synthetic_kit(
            root, files={"tools/a.py": b"a"},
            members={"alpha": {"same": {"tools/a.py": b"a"}}},
        )
        out = io.StringIO()
        RUNNER.main(
            [], board_fn=lambda slug: [], slug_fn=lambda: "owner/repo",
            rows_fn=lambda: [], cron_rows_fn=lambda: ([], ["probe-home"], []),
            cron_fires_fn=lambda: [],
            prefixes_fn=lambda: [], log_dir=_EMPTY_LOG_DIR,
            scores_dir_fn=lambda: _EMPTY_SCORES_DIR,
            kit_manifest=mpath, fleet_manifest=fpath,
            out=lambda *a, **k: print(*a, file=out, **k),
            err=lambda *a, **k: None,
            publish_fn=_stub_publish_leg,
            shared_tree_fn=_stub_shared_tree_rider,
            # #133: the driverless-lane leg's goal store and its turn-in-flight read are
            # injected here for the same reason every other live surface is -- and the
            # defaults WITHHOLD the driven claim (empty store, no turn open) rather than
            # granting one, so a probe that never asserts a driver cannot read one.
            driverless_goals_fn=lambda: _EMPTY_GOAL_STORE,
            driverless_turn_open_fn=lambda: {},
            # #330: the ref-role store is injected for the same reason the ruling table is.
            ref_role_exemptions_path=_NO_REF_ROLE_EXEMPTIONS,
        # #507: the criterion-path store, injected for the same reason.
        criterion_exemptions_fn=lambda: _NO_CRITERION_EXEMPTIONS,
        )
        text = out.getvalue()
        assert "LEG kit-drift" in text, text
        assert "drift over the WHOLE manifest (1 cells)" in text, text
        assert "alpha: same=1 DIFF=0 ABSENT=0" in text, text

def test_the_live_baseline_reproduces_the_measured_figure() -> None:
    """The criterion's own figure, re-derived from the leg rather than quoted.

    The 1/20/29 baseline was measured over the BOOTSTRAP-NAMED set across the member
    factories -- a narrower predicate than the whole manifest -- so both populations are
    read here and the bootstrap one is asserted against its own recorded figure. If a
    member ports a file, this figure MOVES, and the assertion is meant to be updated
    rather than to fail for ever: it pins the predicate, not a permanent state.
    """
    leg = RUNNER.kit_drift_leg(read_at="probe")
    cov = leg["coverage"]
    # A tree carrying no manifest — a bootstrapped factory, or the TEMPLATE copy, whose
    # REPO resolves to TEMPLATE/ — has nothing to reproduce, and the leg says so with a
    # stated reason rather than a clean sweep. Both states are legitimate; what is NOT
    # legitimate is reading either as a verdict about a member.
    if leg["status"] == "NOT RUN" or cov.get("members_reachable", 0) == 0:
        print(f"  (no live member repos to reproduce against: {cov.get('reason', 'none reachable')})")
        return
    boot = cov["bootstrap_cells"]
    assert len(cov["bootstrap_named"]) == 10, len(cov["bootstrap_named"])
    assert cov["bootstrap_cells_total"] == 10 * cov["members_reachable"], cov
    print(f"  (live bootstrap drift: {boot['same']} same / {boot['DIFF']} DIFF / "
          f"{boot['ABSENT']} ABSENT over {cov['bootstrap_cells_total']} cells)")

def test_the_reference_is_read_from_HEAD_not_from_the_working_tree() -> None:
    """Issue #185: a member's pin is COMMITTED, so the reference it is judged against has
    to be re-derivable by a reader who was not here.

    The manifest is GENERATED FROM THE WORKING TREE, so a disk read returns whatever the
    last generation happened to see — and a lane mid-write changes it under the reader.
    Measured at the filing (2026-09-26): five distinct kit_version values in about 23
    minutes, TWO of which appeared in no commit at all, the file changed between two reads
    14 seconds apart, and the manifest included two files untracked at that instant.

    THE PROBE IS HERMETIC AND THE BITE IS REAL, which is why it is built this way. On the
    live tree HEAD and the working copy AGREE, so a live assertion would pass under the
    PRE-FIX code too and would prove nothing about the dispatch. So the leg is pointed at a
    throwaway repository built here whose HEAD and working copy deliberately DISAGREE — the
    window the filing measured, reproduced deterministically — and driven twice over that
    ONE tree: once with no manifest_path (the live call, which must read HEAD) and once with
    an explicit path (the probe call, which must still read disk). The two answers must
    DIFFER, and in that direction. Under the pre-fix code both arms read the file, both
    return the dirty version, and the first assertion below fails.
    """
    import hashlib

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        (repo / "registry").mkdir(parents=True)

        member = root / "member"
        (member / "tools").mkdir(parents=True)
        (member / "tools" / "a.py").write_bytes(b"a")
        files = {"TEMPLATE/tools/a.py": hashlib.sha256(b"a").hexdigest()}

        (repo / "registry" / "kit.json").write_text(
            json.dumps({"kit_version": "COMMITTED", "files": files}), encoding="utf-8")
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.email=probe@probe.invalid", "-c", "user.name=probe",
                      "commit", "-qm", "probe"]):
            done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
            assert done.returncode == 0, done.stderr

        # THE WINDOW: the working copy now names a version that appears in NO commit.
        (repo / "registry" / "kit.json").write_text(
            json.dumps({"kit_version": "DIRTY-UNCOMMITTED", "files": files}), encoding="utf-8")

        fleet = root / "fleet.json"
        fleet.write_text(json.dumps({"factories": [{"slug": "alpha", "repo": str(member)}]}),
                         encoding="utf-8")

        with mock.patch.object(RUNNER, "REPO", repo), \
                mock.patch.object(RUNNER, "KIT_MANIFEST_REL", "registry/kit.json"):
            head_arm = RUNNER.kit_drift_leg(fleet_path=fleet, read_at="head")
            disk_arm = RUNNER.kit_drift_leg(manifest_path=repo / "registry" / "kit.json",
                                            fleet_path=fleet, read_at="disk")

        assert head_arm["coverage"]["kit_version"] == "COMMITTED", head_arm["coverage"]
        assert disk_arm["coverage"]["kit_version"] == "DIRTY-UNCOMMITTED", disk_arm["coverage"]
        assert head_arm["coverage"]["manifest_source"] == "HEAD:registry/kit.json"
        assert disk_arm["coverage"]["manifest_source"].endswith("registry/kit.json")
        # Both arms saw the SAME member tree, so the only thing that moved the reference was
        # where it was read from — not a different fixture.
        assert (head_arm["coverage"]["manifest_files"]
                == disk_arm["coverage"]["manifest_files"])

def test_the_LIVE_reference_is_the_committed_manifest() -> None:
    """The live half of the #185 remedy, and the provenance that makes it checkable.

    The probe above proves the DISPATCH hermetically; this one pins the LIVE call to the
    committed bytes, so a later change that quietly restored a disk default is caught
    against the real repository rather than only against a fixture. It derives the expected
    version the SAME way the leg does — `git show HEAD:registry/kit.json` — so it cannot
    drift from the leg's own definition of "the committed manifest", and it asserts the
    provenance field, because a HEAD read and a disk read print identically otherwise and
    the whole change is which one happened.
    """
    leg = RUNNER.kit_drift_leg(read_at="probe")
    cov = leg["coverage"]
    if leg["status"] == "NOT RUN":
        # A tree carrying no manifest at HEAD — a bootstrapped factory, or this file's
        # TEMPLATE twin, whose REPO resolves to TEMPLATE/ where `registry/kit.json` is
        # factory data that never ships. STATED, never silently passed.
        print(f"  (no committed manifest to pin: {cov.get('reason')})")
        return
    done = subprocess.run(["git", "-C", str(RUNNER.REPO), "show", "HEAD:registry/kit.json"],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    at_head = json.loads(done.stdout)
    assert cov["manifest_source"] == "HEAD:registry/kit.json", cov["manifest_source"]
    assert cov["kit_version"] == at_head["kit_version"], (cov["kit_version"], at_head["kit_version"])
    assert cov["manifest_files"] == len(at_head["files"]), cov["manifest_files"]

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


# --- the publish-freshness leg (issue #146) ------------------------------------------
#
# The leg's live population is "unpushed commits older than the residual window", and on a
# healthy box that is ZERO -- so a probe that only read the live tree would pass by
# examining nothing. Non-vacuity therefore rides these probes, driven from synthetic
# repositories, exactly as the notify-receipt leg's does (#112's opposite call is the
# cron-thinness leg, whose empty population IS a finding).


def _git(repo: Path, *args: str, env: dict | None = None) -> str:
    merged = dict(os.environ)
    merged.update(env or {})
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, env=merged, timeout=120
    )
    assert proc.returncode == 0, f"git {' '.join(args)}: {proc.stderr.strip()}"
    return proc.stdout.strip()


def _bare(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "--bare", "-q")
    _git(path, "symbolic-ref", "HEAD", "refs/heads/main")
    return path


def _work(path: Path, remote: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "symbolic-ref", "HEAD", "refs/heads/main")
    _git(path, "config", "user.email", "probe@probe.invalid")
    _git(path, "config", "user.name", "probe")
    _git(path, "remote", "add", "origin", str(remote))
    return path


def _commit(repo: Path, name: str, *, when: dt.datetime | None = None,
            trailer: str | None = None) -> str:
    (repo / name).write_text(f"{name}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    env = {}
    if when is not None:
        stamp = when.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        env = {"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
    message = name if trailer is None else f"{name}\n\nSession-Id: {trailer}\n"
    _git(repo, "commit", "-q", "-m", message, env=env)
    return _git(repo, "rev-parse", "HEAD")


def _seeded(root: Path):
    """A bare remote carrying one commit, and a clone of it. Returns (remote, work).

    The seed commit is BACKDATED. A repo with history has an old tip, and the publish leg's
    tip-age arm (issue #284) reads a tip younger than the pusher's grace window as one no
    governed push explains -- which a just-created seed would be. Backdating keeps the
    fixture representative, so a control that asserts a clean leg is asserting it about a
    healthy repo rather than about an artifact of the fixture's own clock.
    """
    remote = _bare(root / "remote.git")
    seed = _work(root / "seed", remote)
    _commit(seed, "a.txt", when=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=6))
    _git(seed, "push", "-q", "origin", "main:main")
    work = root / "work"
    _git(root, "clone", "-q", str(remote), str(work))
    _git(work, "config", "user.email", "probe@probe.invalid")
    _git(work, "config", "user.name", "probe")
    return remote, work

def _sibling(work: Path, root: Path, name: str = "sibling") -> Path:
    """A SECOND checkout of the SAME repository, sharing its git common dir (#445).

    A `git worktree` is the only shape that gives one repository two working directories:
    the sibling's `.git` is a FILE pointing into the main checkout's `.git/worktrees/`, so
    `rev-parse --git-common-dir` resolves BOTH checkouts to the same directory. That is what
    makes a receipt written here visible to a reader in `work` -- and what makes a
    checkout-local fallback in `receipt_path` FAIL these arms rather than pass them.
    """
    sib = root / name
    _git(work, "worktree", "add", "-q", "--detach", str(sib))
    return sib


def test_the_publish_leg_BITES_when_a_commit_has_been_unpushed_past_the_window() -> None:
    """The leg's whole purpose: a commit no healthy pusher can explain, NAMED."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote, work = _seeded(root)
        now = dt.datetime.now(dt.timezone.utc)
        stale = now - dt.timedelta(seconds=RUNNER.PUBLISH_RESIDUAL_SECS * 2)
        sha = _commit(work, "b.txt", when=stale, trailer="deadbeef-lane")

        leg = RUNNER.publish_freshness_leg(
            repo=work, remote="origin", branch="main", read_at="probe", now=now
        )
        assert leg["problems"], "an unpushed commit past the window must be a problem"
        assert any(sha in problem for problem in leg["problems"]), leg["problems"]
        assert any("deadbeef-lane" in problem for problem in leg["problems"]), (
            f"a finding must NAME the lane that authored it: {leg['problems']}"
        )
        assert leg["coverage"]["unpushed"] == 1 and leg["coverage"]["shas"] == [sha]
        assert len(leg["coverage"]["stale"]) == 1


def test_the_publish_leg_HOLDS_a_commit_inside_the_residual_window_and_still_names_it() -> None:
    """The control. Without it, a leg that flagged EVERY unpushed commit would pass the
    arm above -- and would red the patrol on every round between two healthy pushes."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote, work = _seeded(root)
        now = dt.datetime.now(dt.timezone.utc)
        fresh = now - dt.timedelta(seconds=60)
        sha = _commit(work, "b.txt", when=fresh)

        leg = RUNNER.publish_freshness_leg(
            repo=work, remote="origin", branch="main", read_at="probe", now=now
        )
        assert leg["problems"] == [], leg["problems"]
        assert leg["coverage"]["unpushed"] == 1, leg["coverage"]
        assert leg["coverage"]["shas"] == [sha]
        assert leg["coverage"]["stale"] == []
        assert leg["coverage"]["residual_secs"] == RUNNER.PUBLISH_RESIDUAL_SECS


def test_the_publish_leg_reports_an_UNREACHABLE_remote_as_a_finding() -> None:
    """'I could not ask' and 'there is nothing to publish' are different facts. A leg
    that read an unreachable remote as in-sync would report a clean result over a
    question it never got an answer to."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        work = _work(root / "work", root / "does-not-exist.git")
        _commit(work, "a.txt")
        leg = RUNNER.publish_freshness_leg(
            repo=work, remote="origin", branch="main", read_at="probe"
        )
        assert leg["problems"], "an unreadable remote must be a finding"
        assert any("could not be read" in p for p in leg["problems"]), leg["problems"]
        assert leg["coverage"]["remote_tip"] is None


def test_the_publish_leg_reads_the_REMOTE_not_the_local_ref() -> None:
    """`origin/main` is a cache updated only by a fetch. A leg reading it would report the
    fact in doubt -- the same substitution the pusher itself refuses."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote, work = _seeded(root)
        stale_ref = _git(work, "rev-parse", "origin/main")

        peer = root / "peer"
        _git(root, "clone", "-q", str(remote), str(peer))
        _git(peer, "config", "user.email", "probe@probe.invalid")
        _git(peer, "config", "user.name", "probe")
        _commit(peer, "peer.txt")
        _git(peer, "push", "-q", "origin", "main:main")
        moved = _git(remote, "rev-parse", "refs/heads/main")

        assert moved != stale_ref, "the arm's own precondition: the local ref is stale"

        leg = RUNNER.publish_freshness_leg(
            repo=work, remote="origin", branch="main", read_at="probe"
        )
        assert leg["coverage"]["remote_tip"] == moved, (
            f"reported {leg['coverage']['remote_tip']} but the remote tip is {moved}"
        )


def test_the_publish_leg_shares_the_PUSHER_own_predicate() -> None:
    """One predicate, two call sites. A private `git` call here would let the leg and the
    mechanism disagree about what 'unpushed' means -- the drift the kit-drift leg avoids
    by reading through `tools/kit_pin.py`."""
    source = RUNNER_PATH.read_text(encoding="utf-8")
    start = source.index("def publish_freshness_leg")
    end = source.index("def deferred_legs")
    body = source[start:end]
    assert 'load_module("publish"' in body, "the leg must load the pusher's own module"
    assert 'pub.remote_tip(' in body and 'pub.unpushed_commits(' in body, body[:400]
    assert '"ls-remote"' not in body, "the leg must not restate the remote read"
    assert '"rev-list"' not in body, "the leg must not restate the unpushed read"


def test_the_publish_leg_is_WIRED_into_the_runner_and_prints_its_population() -> None:
    """A leg that is not wired is a leg nobody runs; a leg whose population never renders
    is a leg nobody reads. A count without its predicate is unreadable."""
    source = RUNNER_PATH.read_text(encoding="utf-8")
    # The property is WIRED **and** INJECTABLE, not a literal: the leg reads the remote, so
    # the seam that lets a probe stub it is part of what must be true (see the 40s-to-4s
    # measurement in the stub's own docstring).
    assert "(publish_fn or publish_freshness_leg)(read_at=read_at)," in source, (
        "not wired into main(), or wired without the injection seam"
    )
    assert "publish_fn=None," in source, "main() must accept a publish_fn"

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote, work = _seeded(root)
        now = dt.datetime.now(dt.timezone.utc)
        stale = now - dt.timedelta(seconds=RUNNER.PUBLISH_RESIDUAL_SECS * 2)
        sha = _commit(work, "b.txt", when=stale, trailer="cafebabe-lane")

        leg = RUNNER.publish_freshness_leg(
            repo=work, remote="origin", branch="main", read_at="probe", now=now
        )
        text = RUNNER.render(
            [leg], [], slug="owner/repo", read_at="2026-09-26T00:00:00Z", issues=[]
        )
        assert "LEG publish-freshness" in text, text
        assert "residual window" in text, text
        assert sha in text and "cafebabe-lane" in text, text
        assert "STALE" in text, text

def test_the_publish_leg_does_not_RED_a_pure_ancestor_tree_but_still_REDs_a_DIVERGENCE() -> None:
    """#418, the hermetic fixture PAIR for the leg. The live tree exhibits ONLY the BEHIND
    state (the shared tree is a pure ancestor of `origin/main`), so the leg cannot be shown
    on it to tell the two shapes apart. Fixture A (pure ancestor, ahead==0) must produce NO
    problem and print BEHIND; fixture B (ahead>0 AND behind>0) must still RED with DIVERGED.

    Both halves are load-bearing: without fixture B a leg that stopped reddening EVERYTHING
    would pass, and without fixture A the leg's old one-sided test (which red the normal
    steady state) would pass. The leg's own population print must survive in both.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        now = dt.datetime.now(dt.timezone.utc)
        old = now - dt.timedelta(hours=6)

        # --- fixture A: pure BEHIND. The peer's commit is BACKDATED past the grace window
        # so the tip-age arm (which fires on a tip SAMPLED while young) stays out of it.
        remote_a, work_a = _seeded(root / "a")
        peer = root / "a" / "peer"
        _git(root / "a", "clone", "-q", str(remote_a), str(peer))
        _git(peer, "config", "user.email", "probe@probe.invalid")
        _git(peer, "config", "user.name", "probe")
        _commit(peer, "peer.txt", when=old, trailer="peer-lane")
        _git(peer, "push", "-q", "origin", "main:main")
        # FETCH, so the remote tip object is LOCAL: `rev-list --count` needs it, and a
        # behind tree normally has it (the live #418 reading was a readable `11`). Without
        # the fetch the count reads "unreadable", which would mask the reading under test.
        # After the fetch `work_a`'s HEAD is STILL a pure ancestor of the remote tip.
        _git(work_a, "fetch", "-q", "origin")
        leg_a = RUNNER.publish_freshness_leg(
            repo=work_a, remote="origin", branch="main", read_at="probe", now=now
        )
        assert leg_a["problems"] == [], (
            f"a pure-ancestor (BEHIND) tree must NOT be a problem: {leg_a['problems']}"
        )
        assert leg_a["coverage"]["behind"] is True, leg_a["coverage"]
        assert leg_a["coverage"]["diverged"] is False, leg_a["coverage"]

        text_a = RUNNER.render(
            [leg_a], [], slug="owner/repo", read_at="2026-10-06T00:00:00Z", issues=[]
        )
        assert "BEHIND" in text_a, text_a
        assert "remote tip" in text_a and "unpushed commit(s)" in text_a, (
            f"the population print must survive: {text_a}"
        )

        # --- fixture B: genuine DIVERGENCE (ahead>0 AND behind>0). The local commit is
        # FRESH so only the divergence arm speaks (the stale arm stays out of it).
        remote_b, work_b = _seeded(root / "b")
        _commit(work_b, "mine.txt", when=now - dt.timedelta(seconds=60), trailer="mine-lane")
        peer_b = root / "b" / "peer"
        _git(root / "b", "clone", "-q", str(remote_b), str(peer_b))
        _git(peer_b, "config", "user.email", "probe@probe.invalid")
        _git(peer_b, "config", "user.name", "probe")
        _commit(peer_b, "peer.txt", when=old, trailer="peer-b-lane")
        _git(peer_b, "push", "-q", "origin", "main:main")
        # FETCH, so both counts are READABLE (see fixture A's note): after it `work_b` has
        # one commit the remote lacks (ahead 1) and one it lacks (behind 1) -- a genuine
        # divergence, not an unreadable-count fallback.
        _git(work_b, "fetch", "-q", "origin")

        leg_b = RUNNER.publish_freshness_leg(
            repo=work_b, remote="origin", branch="main", read_at="probe", now=now
        )
        assert any("DIVERGED" in p for p in leg_b["problems"]), (
            f"a genuine divergence must still RED: {leg_b['problems']}"
        )
        assert leg_b["coverage"]["diverged"] is True, leg_b["coverage"]
        assert leg_b["coverage"]["behind"] is False, leg_b["coverage"]

        text_b = RUNNER.render(
            [leg_b], [], slug="owner/repo", read_at="2026-10-06T00:00:00Z", issues=[]
        )
        assert "DIVERGED" in text_b, text_b


# --- the publish leg's CADENCE SIDE (issue #284) -------------------------------------
#
# The leg above measures LAG, and a late pusher and an absent one leave the same unpushed
# commit behind -- so the leg could not tell them apart. Leg (c) gives it a second side: the
# pusher records its own last push in a file under `evidence/`, and a remote tip that is not
# that sha left through some OTHER path. These probes drive both arms, and the control that
# keeps them from passing on a leg that reds on every healthy round.

def _pusher():
    return RUNNER.load_module("publish", RUNNER.PUBLISH_PUSHER)

def test_the_publish_leg_REPORTS_an_ungoverned_push_BY_NAME() -> None:
    """Leg (c)(2). The receipt names the sha the pusher pushed; a tip that is not that sha
    left through some other path, and the finding must NAME the tip, the lane trailer of its
    commit and the receipt it contradicts. A count alone cannot be dispatched or closed.

    THE RECEIPT IS WRITTEN BY A SIBLING CHECKOUT (#445): the record is per-REPOSITORY, so a
    reader in `work` must still see it and report the mismatch -- a checkout-local fallback
    would read no receipt at all and this arm would silently weaken to the tip-age case.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote, work = _seeded(root)
        pub = _pusher()
        now = dt.datetime.now(dt.timezone.utc)
        old = now - dt.timedelta(hours=6)

        governed = _commit(work, "b.txt", when=old, trailer="gov-lane")
        _git(work, "push", "-q", "origin", "main:main")
        writer = _sibling(work, root, "writer")
        path, why = pub.write_receipt(
            writer, sha=governed, remote="origin", branch="main",
            instant=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        assert path is not None and not why, why

        # The ungoverned push: committed 6h ago (so the tip-age arm stays out of it) and
        # pushed straight to the remote, bypassing the pusher entirely.
        rogue = _commit(work, "rogue.txt", when=old, trailer="rogue-lane")
        _git(work, "push", "-q", "origin", "main:main")

        leg = RUNNER.publish_freshness_leg(
            repo=work, remote="origin", branch="main", read_at="probe", now=now
        )
        joined = " ".join(leg["problems"])
        assert leg["problems"], "a tip the receipt does not account for must be a finding"
        assert rogue in joined, f"the finding must NAME the ungoverned sha: {leg['problems']}"
        assert "rogue-lane" in joined, f"the finding must NAME its lane: {leg['problems']}"
        assert governed in joined, (
            f"the finding must NAME the receipt it contradicts: {leg['problems']}"
        )
        assert leg["coverage"]["receipt_mismatch"]["remote_tip"] == rogue
        # The record was written by the SIBLING and the finding says so, rather than
        # attributing it to the checkout that happens to be reading (#445).
        assert leg["coverage"]["receipt_mismatch"]["receipt_origin_checkout"] == str(
            writer.resolve()
        ), leg["coverage"]["receipt_mismatch"]

        text = RUNNER.render(
            [leg], [], slug="owner/repo", read_at="2026-10-03T00:00:00Z", issues=[]
        )
        assert "UNGOVERNED PUSH" in text and rogue in text, text

def test_the_publish_leg_is_QUIET_when_the_receipt_ACCOUNTS_for_the_tip() -> None:
    """The control. Without it, a leg that red on ANY receipt would pass the arm above --
    and would red the patrol on every healthy round, since a governed push leaves the tip
    exactly equal to the sha the pusher recorded.

    THE RECEIPT IS WRITTEN IN A SIBLING CHECKOUT (#445). The record is per-REPOSITORY (git
    common dir), so this control writes it from a `git worktree` sibling and reads it from
    `work`. A checkout-local fallback would find no receipt in `work` and the leg would
    report `no receipt recorded` -- the exact false negative this shape removes -- so the
    control FAILS against the old shape rather than passing it.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote, work = _seeded(root)
        pub = _pusher()
        now = dt.datetime.now(dt.timezone.utc)
        old = now - dt.timedelta(hours=6)

        governed = _commit(work, "b.txt", when=old, trailer="gov-lane")
        _git(work, "push", "-q", "origin", "main:main")
        writer = _sibling(work, root, "writer")
        path, why = pub.write_receipt(
            writer, sha=governed, remote="origin", branch="main",
            instant=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        assert path is not None and not why, why

        leg = RUNNER.publish_freshness_leg(
            repo=work, remote="origin", branch="main", read_at="probe", now=now
        )
        assert leg["problems"] == [], leg["problems"]
        assert leg["coverage"]["receipt_mismatch"] is None
        assert leg["coverage"]["receipt"]["sha"] == governed
        assert leg["coverage"]["tip_younger_than_grace"] is False
        # The record was written by the SIBLING, and the coverage says so rather than
        # attributing it to the checkout that happens to be reading (#445).
        assert leg["coverage"]["receipt"]["origin_checkout"] == str(writer.resolve()), (
            leg["coverage"]["receipt"]
        )
        assert leg["coverage"]["reading_checkout"] == str(work.resolve())
        assert leg["coverage"]["receipt_path"] == str(pub.receipt_path(work))

def test_the_receipt_is_SHARED_across_worktrees_of_one_repository() -> None:
    """#445 acceptance: the SAME remote tip, read from TWO checkouts of ONE repository,
    returns the SAME verdict -- the fixture pair.

    This is the defect itself, as a discriminating arm. Before #445 the receipt sat under
    `evidence/`, gitignored and therefore checkout-local, so one tip read 0 problems in the
    checkout that had pushed and 1 in a sibling that had not: a GLOBAL remote tip judged
    against a LOCAL record, with the finding naming a lane that had pushed correctly. Both
    checkouts now read the ONE record in the git common dir, so the arm asserts EQUALITY of
    the two verdicts AND that both resolve the SAME receipt file -- merely asserting each is
    quiet would pass a leg that read no receipt at all.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote, work = _seeded(root)
        pub = _pusher()
        now = dt.datetime.now(dt.timezone.utc)
        old = now - dt.timedelta(hours=6)

        governed = _commit(work, "b.txt", when=old, trailer="gov-lane")
        _git(work, "push", "-q", "origin", "main:main")
        sibling = _sibling(work, root, "sibling")

        # The pusher pushed FROM `work` and recorded its receipt there.
        path, why = pub.write_receipt(
            work, sha=governed, remote="origin", branch="main",
            instant=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        assert path is not None and not why, why

        leg_a = RUNNER.publish_freshness_leg(
            repo=work, remote="origin", branch="main", read_at="probe", now=now
        )
        leg_b = RUNNER.publish_freshness_leg(
            repo=sibling, remote="origin", branch="main", read_at="probe", now=now
        )
        assert leg_a["problems"] == [] and leg_b["problems"] == [], (
            f"one repository, one receipt: the two checkouts must agree, got "
            f"{leg_a['problems']} vs {leg_b['problems']}"
        )
        assert (
            leg_a["coverage"]["receipt_path"] == leg_b["coverage"]["receipt_path"]
        ), "both checkouts must read the SAME receipt file (git common dir)"
        # The reading checkout differs; the receipt's origin does not.
        assert leg_a["coverage"]["reading_checkout"] == str(work.resolve())
        assert leg_b["coverage"]["reading_checkout"] == str(sibling.resolve())
        assert leg_a["coverage"]["receipt"]["origin_checkout"] == str(work.resolve())
        assert leg_b["coverage"]["receipt"]["origin_checkout"] == str(work.resolve())

def test_a_PUSHER_made_push_reads_GOVERNED_from_a_SIBLING_worktree() -> None:
    """#445 acceptance, driven by a REAL pusher push rather than a hand-written receipt.

    The arm above writes the record through `write_receipt` directly; this one runs the
    PUSHER -- `publish(..., apply=True)` -- so the receipt read is the one the tool itself
    writes on a round it published, and then reads the leg from a SIBLING worktree that
    holds no record of its own. Before #445 that sibling read `no receipt recorded` (the
    measured false negative) or a stale checkout-local receipt (the measured false positive
    that named the lane which had pushed correctly); now it reads the one per-repository
    record and reports the tip as GOVERNED.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote, work = _seeded(root)
        pub = _pusher()
        now = dt.datetime.now(dt.timezone.utc)
        old = now - dt.timedelta(seconds=RUNNER.PUBLISH_GRACE_SECS * 4)

        sha = _commit(work, "b.txt", when=old, trailer="gov-lane")
        report = pub.publish(
            work, remote="origin", branch="main",
            grace_secs=RUNNER.PUBLISH_GRACE_SECS, apply=True,
        )
        assert report["status"] == "published" and report["receipt"]["sha"] == sha, report

        sibling = _sibling(work, root, "sibling")
        leg = RUNNER.publish_freshness_leg(
            repo=sibling, remote="origin", branch="main", read_at="probe", now=now
        )
        assert leg["problems"] == [], (
            f"a push the pusher ITSELF made must read governed from a sibling worktree: "
            f"{leg['problems']}"
        )
        # The DISCRIMINATING assertion. Against the old checkout-local shape the sibling
        # reads no receipt at all, so `problems` is ALSO empty -- the false negative is
        # silent -- and only a read of the record itself separates the two shapes.
        assert leg["coverage"]["receipt"] is not None, (
            "the sibling must READ the record the pusher wrote in the OTHER checkout, not "
            f"report it absent (receipt_reason={leg['coverage']['receipt_reason']!r})"
        )
        assert leg["coverage"]["receipt"]["sha"] == sha
        assert leg["coverage"]["receipt_mismatch"] is None
        assert leg["coverage"]["receipt"]["origin_checkout"] == str(work.resolve()), (
            leg["coverage"]["receipt"]
        )

def test_a_STALE_checkout_local_receipt_does_not_mislead_the_leg() -> None:
    """#445 acceptance, the STALE half of the fixture pair.

    The sibling arm covers the checkout that holds NO record. This one plants the OLD
    shape's leftover -- a checkout-local `evidence/publish-receipt.json` naming a sha the
    remote tip does NOT match -- in the READING checkout, and asserts the leg still reads
    the ONE per-repository record and reports the tip GOVERNED. It is the false positive
    itself: before #445 the leg read that stale file and named the lane that had pushed
    correctly.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote, work = _seeded(root)
        pub = _pusher()
        now = dt.datetime.now(dt.timezone.utc)
        old = now - dt.timedelta(seconds=RUNNER.PUBLISH_GRACE_SECS * 4)

        sha = _commit(work, "b.txt", when=old, trailer="gov-lane")
        report = pub.publish(
            work, remote="origin", branch="main",
            grace_secs=RUNNER.PUBLISH_GRACE_SECS, apply=True,
        )
        assert report["status"] == "published" and report["receipt"]["sha"] == sha, report

        sibling = _sibling(work, root, "sibling")
        # The leftover: a stale record in the OLD, checkout-local location.
        stale_dir = sibling / "evidence"
        stale_dir.mkdir(parents=True, exist_ok=True)
        (stale_dir / "publish-receipt.json").write_text(
            json.dumps({
                "sha": "0" * 40,
                "instant": "2026-01-01T00:00:00Z",
                "remote": "origin",
                "branch": "main",
            }) + "\n",
            encoding="utf-8",
        )

        leg = RUNNER.publish_freshness_leg(
            repo=sibling, remote="origin", branch="main", read_at="probe", now=now
        )
        assert leg["problems"] == [], (
            f"a stale checkout-local receipt must not make a governed push read "
            f"UNGOVERNED: {leg['problems']}"
        )
        assert leg["coverage"]["receipt"] is not None, leg["coverage"]["receipt_reason"]
        assert leg["coverage"]["receipt"]["sha"] == sha, (
            "the leg must read the per-repository record, not the stale local file"
        )
        assert leg["coverage"]["receipt_mismatch"] is None
        assert leg["coverage"]["receipt_path"] == str(pub.receipt_path(work)), (
            leg["coverage"]["receipt_path"]
        )

def test_the_publish_leg_flags_a_YOUNG_tip_no_receipt_can_explain() -> None:
    """Leg (c)(3), the cheap arm. The pusher HOLDS a commit younger than its grace window,
    so a tip that young cannot have left through it -- and this arm speaks when there is no
    receipt at all, which is the case the receipt arm is blind to. Its bound is printed
    beside it: it sees only a tip SAMPLED while still young."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote, work = _seeded(root)
        now = dt.datetime.now(dt.timezone.utc)

        fresh = _commit(
            work, "direct.txt", when=now - dt.timedelta(seconds=30), trailer="direct-lane"
        )
        _git(work, "push", "-q", "origin", "main:main")

        leg = RUNNER.publish_freshness_leg(
            repo=work, remote="origin", branch="main", read_at="probe", now=now
        )
        assert leg["coverage"]["receipt"] is None, "the arm's own precondition: no receipt"
        assert leg["coverage"]["tip_younger_than_grace"] is True
        joined = " ".join(leg["problems"])
        assert fresh in joined, f"the young tip must be NAMED: {leg['problems']}"
        assert "grace window" in joined, leg["problems"]

        text = RUNNER.render(
            [leg], [], slug="owner/repo", read_at="2026-10-03T00:00:00Z", issues=[]
        )
        assert "tip-age arm bound" in text, text

def test_the_publish_leg_prints_the_PUSHERS_bounds_and_its_OWN_scope() -> None:
    """Leg (b)(2). The three figures travel as the PUSHER's declared bounds, and the leg's
    own scope is printed beside them -- a coverage line that reads as a fleet-wide property
    is the defect #284 closes. Presence is not behaviour, so this reads the rendered text."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote, work = _seeded(root)
        leg = RUNNER.publish_freshness_leg(
            repo=work, remote="origin", branch="main", read_at="probe"
        )
        text = RUNNER.render(
            [leg], [], slug="owner/repo", read_at="2026-10-03T00:00:00Z", issues=[]
        )
        assert "the PUSHER's declared bounds" in text, text
        assert "SCOPE: LAG only" in text, text
        assert "not a property of the fleet" in text.lower(), text
        assert "pusher receipt:" in text, text

# --- the binding-freshness arm (#468, ruled at n=3137) --------------------------------
#
# RESOLUTION IS NOT FRESHNESS. Gate P29 verifies that the profile entry resolves to the
# declared source; nothing verified that the bytes it serves are the bytes this repository
# publishes. Measured live 2026-10-16: the ops profile's tree stood 487 commits behind its
# own `origin/main` -- 6 of the binding's 11 law files differing, 5 equal -- while
# `test -L && test -d` read GREEN, and the #443 dispatch-composition clause was in force
# upstream and absent from every lane's loaded text.
#
# The live population is therefore NOT empty, but a probe must not depend on the box's own
# staleness (a factory that caught up would turn every probe below vacuous). These probes
# drive the arm directly against synthetic repositories, and the discriminating pair is the
# BITE and its CONTROL -- a control is what proves the arm is reading, not merely red.

def _binding_fixture(root: Path, *, behind: bool = False, publish_extra: str | None = None):
    """`(repo, profile_root, declaration_path, reference_sha)` for a synthetic factory.

    The profile root carries `skills/demo` as a SYMLINK to the repo's own `skills/demo`, so
    the fixture is the live shape and not an approximation of it. With `behind=True` the
    loaded tree is reset one commit back AFTER the reference was pushed -- the loaded tree
    stands BEHIND `origin/main`, which is exactly the state the live box is in and the one a
    timestamp cannot distinguish from a healthy tree.
    """
    remote = _bare(root / "remote.git")
    work = _work(root / "work", remote)
    law = work / "skills" / "demo"
    law.mkdir(parents=True)
    (law / "SKILL.md").write_text("v1\n", encoding="utf-8")
    (work / "docs").mkdir()
    (work / "docs" / "harness-bindings.json").write_text(
        json.dumps({
            "profile": "probe",
            "bindings": [{"skill": "demo", "repo_path": "skills/demo", "form": "dir"}],
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    _commit(work, "seed-law")
    _git(work, "push", "-q", "origin", "main:main")

    (law / "SKILL.md").write_text("v2 -- the published law\n", encoding="utf-8")
    if publish_extra:
        (law / publish_extra).write_text(f"{publish_extra}\n", encoding="utf-8")
    _commit(work, "publish-law")
    _git(work, "push", "-q", "origin", "main:main")
    reference = _git(work, "rev-parse", "HEAD")
    if behind:
        _git(work, "reset", "--hard", "HEAD~1")

    profile = root / "profile"
    (profile / "skills").mkdir(parents=True)
    (profile / "skills" / "demo").symlink_to(law)
    return work, profile, work / "docs" / "harness-bindings.json", reference

def _run_arm(repo: Path, profile: Path, declaration: Path, reference: str | None):
    return RUNNER.binding_freshness_arm(
        repo=repo, profile_root=profile, declaration_path=declaration,
        reference_ref=reference, reference_source="probe", read_at="probe",
    )

def test_the_binding_arm_BITES_when_the_loaded_law_stands_BEHIND_the_reference() -> None:
    """The arm's whole purpose, on the live shape: the tree the profile LOADS is behind the
    tree this repository publishes. The finding must NAME the file and BOTH content hashes --
    a count cannot be dispatched, a named file can."""
    with tempfile.TemporaryDirectory() as tmp:
        repo, profile, declaration, reference = _binding_fixture(Path(tmp), behind=True)
        problems, cov = _run_arm(repo, profile, declaration, reference)
        assert problems, "a loaded tree behind the reference must be a finding"
        assert cov["stale"] == ["skills/demo/SKILL.md"], cov
        joined = " ".join(problems)
        assert "skills/demo/SKILL.md" in joined, joined
        assert "STALE" in joined, joined
        assert cov["rows"][0]["resolution"] == "resolved", (
            f"the binding RESOLVES and is still stale -- that split is the defect: {cov['rows']}"
        )
        assert cov["rows"][0]["stale"] == 1, cov["rows"]
        item = [f for f in cov["rows"][0]["files"] if f["path"] == "skills/demo/SKILL.md"][0]
        assert item["status"] == "STALE", item
        assert item["loaded"] != item["at_reference"], (
            f"both hashes must travel, and they must DIFFER: {item}"
        )

def test_the_binding_arm_is_QUIET_when_the_loaded_law_MATCHES_the_reference() -> None:
    """The control. Without it an arm that reds on every round would pass the probe above --
    and would teach the next reader to ignore it, which is the false RED #146's ruling warns
    of. It also proves the fixture is a real comparison: the same files, the same reference."""
    with tempfile.TemporaryDirectory() as tmp:
        repo, profile, declaration, reference = _binding_fixture(Path(tmp))
        problems, cov = _run_arm(repo, profile, declaration, reference)
        assert problems == [], problems
        assert cov["stale"] == [] and cov["missing_local"] == [], cov
        assert len(cov["rows"][0]["files"]) == 1, cov["rows"][0]["files"]
        assert cov["rows"][0]["files"][0]["status"] == "equal", cov["rows"][0]["files"]
        assert cov["reference_ref"] == reference, cov["reference_ref"]

def test_the_binding_arm_reads_CONTENT_and_is_not_disarmed_by_an_IDENTICAL_rewrite() -> None:
    """The ruling's own clause (n=3137): the predicate is a CONTENT hash, NEVER a timestamp.

    A rewrite of identical bytes moves the mtime and changes no law -- this factory has
    already logged that as an instrument error, and a timestamp predicate here would red a
    healthy binding every time a lane touched the file. The probe asserts the mtime really
    moved, so it cannot pass by the rewrite having been a no-op.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo, profile, declaration, reference = _binding_fixture(Path(tmp))
        path = repo / "skills" / "demo" / "SKILL.md"
        before = path.stat().st_mtime_ns
        body = path.read_text(encoding="utf-8")
        path.write_text(body, encoding="utf-8")
        os.utime(path, ns=(before + 10_000_000_000, before + 10_000_000_000))
        assert path.stat().st_mtime_ns != before, "the probe must actually move the mtime"

        problems, cov = _run_arm(repo, profile, declaration, reference)
        assert problems == [], (
            f"an identical rewrite changes no law and must not be a finding: {problems}"
        )
        assert cov["stale"] == [], cov

def test_the_binding_arm_REDs_a_COPY_where_the_profile_owes_a_SYMLINK() -> None:
    """The resolution half, which #79 owns and this arm must not go blind to: a profile that
    carries a COPY of the law serves whatever it copied, forever, and no hash can see it."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo, profile, declaration, reference = _binding_fixture(root)
        entry = profile / "skills" / "demo"
        entry.unlink()
        shutil.copytree(repo / "skills" / "demo", entry)
        problems, cov = _run_arm(repo, profile, declaration, reference)
        assert any("not a symlink" in p for p in problems), problems
        assert cov["rows"][0]["resolution"] == "NOT A SYMLINK", cov["rows"]

def test_the_binding_arm_REDs_a_symlink_that_RESOLVES_ELSEWHERE() -> None:
    """A symlink is not enough: it must resolve to the source THIS repo declares. A link into
    a sibling checkout -- or into another repository entirely -- serves law this repo does not
    author, and it resolves perfectly while doing so."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo, profile, declaration, reference = _binding_fixture(root)
        other = root / "other" / "skills" / "demo"
        other.mkdir(parents=True)
        (other / "SKILL.md").write_text("someone else's law\n", encoding="utf-8")
        entry = profile / "skills" / "demo"
        entry.unlink()
        entry.symlink_to(other)
        problems, cov = _run_arm(repo, profile, declaration, reference)
        assert any("RESOLVES ELSEWHERE" in p or "not `skills/demo`" in p for p in problems), problems
        assert cov["rows"][0]["resolution"] == "RESOLVES ELSEWHERE", cov["rows"]

def test_the_binding_arm_does_NOT_RED_a_SIBLING_worktree_of_the_SAME_repo() -> None:
    """The false-RED the arm must NOT raise, and the reason it compares COMMON DIRS.

    Under the worktree law a lane works in a worktree while the profile may load the SHARED
    tree, so two DIFFERENT paths are routinely ONE repository. A path comparison would red
    the very shape the law prescribes -- and a guard that fires on the prescribed shape is
    the one its readers learn to ignore. The common dir is what tells the two apart, so the
    probe holds that split: the sibling serves the same law file at the same relative path,
    the bytes match the reference, and there is NO finding.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo, profile, declaration, reference = _binding_fixture(root)
        sib = _sibling(repo, root)
        entry = profile / "skills" / "demo"
        entry.unlink()
        entry.symlink_to(sib / "skills" / "demo")
        problems, cov = _run_arm(repo, profile, declaration, reference)
        assert cov["rows"][0]["resolution"] == "resolved", (
            f"a sibling worktree of the SAME repo serves this repo's own law at the "
            f"declared path: {cov['rows']}"
        )
        assert not problems, (
            f"the worktree shape the law prescribes must not be a finding: {problems}"
        )

def test_the_binding_arm_REDs_a_law_file_the_reference_does_NOT_publish() -> None:
    """A law file the profile serves and the repository never published is either local-only
    or moved upstream; both are staleness, and a hash over local files alone would read the
    first as clean."""
    with tempfile.TemporaryDirectory() as tmp:
        repo, profile, declaration, reference = _binding_fixture(Path(tmp))
        (repo / "skills" / "demo" / "local-only.md").write_text("local\n", encoding="utf-8")
        problems, cov = _run_arm(repo, profile, declaration, reference)
        assert any("does not exist at" in p for p in problems), problems
        assert cov["stale"] == ["skills/demo/local-only.md"], cov

def test_the_binding_arm_REDs_a_law_file_the_reference_PUBLISHES_and_the_tree_LACKS() -> None:
    """The OTHER direction, and the reason the arm lists the reference's own tree: the #443
    clause landed inside an existing file, but a NEW clause file upstream is the same
    staleness in a shape a local-only hash can never see."""
    with tempfile.TemporaryDirectory() as tmp:
        repo, profile, declaration, reference = _binding_fixture(
            Path(tmp), behind=True, publish_extra="newer.md"
        )
        problems, cov = _run_arm(repo, profile, declaration, reference)
        assert cov["missing_local"] == ["newer.md"], cov
        assert any("ABSENT from the loaded tree" in p for p in problems), problems

def test_the_binding_arm_is_NOT_RUN_when_the_repo_declares_no_binding() -> None:
    """A factory that never adopted the manifest is not measured against one, and the reason
    is STATED -- an arm that silently read clean over zero declarations would be the exact
    found-nothing-is-not-clean defect this file's doctrine forbids."""
    with tempfile.TemporaryDirectory() as tmp:
        repo, profile, declaration, reference = _binding_fixture(Path(tmp))
        declaration.unlink()
        problems, cov = _run_arm(repo, profile, declaration, reference)
        assert problems == [], problems
        assert "declares no binding" in cov["binding_reason"], cov
        assert cov["rows"] == [], cov

def test_the_binding_arm_REDs_an_UNREADABLE_reference_rather_than_reading_clean() -> None:
    """'I could not ask' and 'the law is level' are different facts. With no reference to
    compare against, the arm has no verdict to give -- and must say so, never pass."""
    with tempfile.TemporaryDirectory() as tmp:
        repo, profile, declaration, _ = _binding_fixture(Path(tmp))
        problems, cov = _run_arm(repo, profile, declaration, None)
        assert any("no `origin/main` to compare" in p for p in problems), problems
        assert "unreadable reference is never a clean result" in cov["binding_reason"], cov

def test_the_binding_arm_rides_the_LEG_and_its_keys_do_not_COLLIDE_with_the_legs_own() -> None:
    """#3137: the detector RIDES the existing leg -- no new instrument. It must therefore
    reach the report through the leg, and its coverage must be NAMESPACED: the arm and the
    leg both carry a `stale` list, and a flat merge silently overwrote the leg's commit list
    with the arm's law-file list -- which read as a clean round on the leg's own probe."""
    with tempfile.TemporaryDirectory() as tmp:
        repo, profile, declaration, reference = _binding_fixture(Path(tmp), behind=True)
        now = dt.datetime.now(dt.timezone.utc)
        leg = RUNNER.publish_freshness_leg(
            repo=repo, remote="origin", branch="main", read_at="probe", now=now,
            profile_root=profile,
        )
        assert leg["name"] == "publish-freshness", leg["name"]
        assert any("skills/demo/SKILL.md is STALE" in p for p in leg["problems"]), leg["problems"]
        assert leg["coverage"]["binding"]["stale"] == ["skills/demo/SKILL.md"], (
            leg["coverage"]["binding"]
        )
        assert all(not str(s).endswith(".md") for s in leg["coverage"]["stale"]), (
            f"the leg's own commit `stale` list must survive beside the arm's: "
            f"{leg['coverage']['stale']}"
        )
        text = RUNNER.render(
            [leg], [], slug="owner/repo", read_at="2026-10-16T00:00:00Z", issues=[]
        )
        assert "binding freshness:" in text, text
        assert "skills/demo/SKILL.md" in text, text
        assert "CONTENT only" in text, text


#
# The law is forward-looking: SKILL.md section 11 says a duty whose lane writes an
# undated, ad-hoc subject predating the convention "owes the convention going forward".
# So a round that fired BEFORE this factory adopted the convention could not have carried
# a receipt, and judging it is a FALSE MISSING. These probes pin the bound, and — the half
# that matters more — pin that the bound NARROWS the population without silencing the leg.

def test_a_round_that_fired_BEFORE_the_declared_bound_is_EXCUSED_and_named() -> None:
    """Acceptance 1: a pre-bound round is excused, and the excuse NAMES it.

    The measured instances are `factory-template-weekly` (round 2026-09-21, four days
    before the convention) and `factory-growth-map-biweekly` (round 2026-09-16, nine days
    before). Both fired when no receipt was possible, and both were reported MISSING.
    """
    leg = _duty_leg([_duty_row(last_run_at="2026-09-21T06:00:27Z")], [])
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["duties_judged"] == [], "a pre-bound round is NOT judged"
    assert leg["coverage"]["rounds_excused_by_bound"] == 1, leg["coverage"]
    excuse = [e for e in leg["excused"] if "BEFORE the declared" in e]
    assert len(excuse) == 1, leg["excused"]
    text = excuse[0]
    assert "factory-registry-attest" in text, text
    assert "9ec28cec" in text, "the excuse must name the cron row it excused, by id"
    assert _DUTY_BOUND in text, f"the excuse must print the bound it applied: {text}"
    assert "NEVER backfilled" in text, text


def test_the_bound_NARROWS_the_population_and_the_leg_STILL_REDs_after_it() -> None:
    """Acceptance 2, the negative control — the bound must not silence the leg.

    A bound that excused everything would pass acceptance 1 and read as a clean run, so
    the two rounds are driven TOGETHER: the pre-bound one excused, the post-bound one
    still RED. This is the arm that proves the bound narrows rather than hides.
    """
    leg = _duty_leg(
        [_duty_row(name="factory-old", last_run_at=_plus(_DUTY_BOUND, -48),
                   row_id="aaaa1111-0000-0000-0000-000000000001"),
                  _duty_row(name="factory-new", last_run_at=_DUTY_FIRE,
                   row_id="bbbb2222-0000-0000-0000-000000000002")],
        [],
    )
    assert leg["coverage"]["rounds_excused_by_bound"] == 1, leg["coverage"]
    problems = [p for p in leg["problems"] if "NO duty receipt" in p]
    assert len(problems) == 1, problems
    assert "factory-new" in problems[0], problems
    assert "factory-old" not in problems[0], "the excused round must not also be a problem"


def test_an_UNDECLARED_bound_REFUSES_instead_of_judging_every_round() -> None:
    """Acceptance 4: no declaration is a REFUSAL, never the pre-fix behaviour arriving
    as a clean run. Judging the whole population unbounded is exactly what #175 exists
    to stop, so a tree that declares nothing must be told so rather than shown green.
    """
    leg = _duty_leg([_duty_row()], [], repo=_duty_tree(invariants={}))
    assert len(leg["problems"]) == 1, leg["problems"]
    refusal = leg["problems"][0]
    assert "duty_receipt_declared" in refusal, refusal
    assert "REFUSED" in refusal, refusal
    assert leg["coverage"]["duties_judged"] == [], (
        "no round may be judged while the bound is unreadable — that is the unbounded "
        "pre-fix behaviour arriving silently")
    assert leg["coverage"]["bound"] == "", leg["coverage"]
    assert leg["coverage"]["bound_refusal"], leg["coverage"]


def test_a_MALFORMED_bound_REFUSES_with_the_reader_s_own_problems() -> None:
    """A declared-but-unreadable bound is a DEFECT, never a skip and never a pass.

    The reader's own policy (absent SKIPS, malformed FAILS) is mapped here onto
    refuse-vs-refuse, because for this leg an absent declaration is also not a licence to
    judge unbounded. The distinction survives in the WORDING, which is what a reader of
    the report needs in order to act on it.
    """
    leg = _duty_leg([_duty_row()], [], repo=_duty_tree(declaration="not json {{{"))
    assert len(leg["problems"]) == 1, leg["problems"]
    refusal = leg["problems"][0]
    assert "cannot be read" in refusal, refusal
    assert leg["coverage"]["duties_judged"] == [], leg["coverage"]


def test_the_bound_is_FACTORY_DATA_read_through_the_ONE_reader() -> None:
    """Acceptance 3: the instant is declared factory data, never a second constant.

    A bootstrapped factory's history is its own, so a leg that hardcoded this factory's
    date would judge a tree it does not describe — the same reason the boundary-reading
    gates declare theirs. The grep is the whole probe: no instant of the bound may appear
    in the runner, and the key must resolve through `tests/ledger_boundary.py`.
    """
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "2026-09-25T07:01:07" not in source, (
        "the bound instant is hardcoded in the leg; it belongs in docs/ledger-invariants.json")
    assert RUNNER.DUTY_RECEIPT_BOUNDARY_KEY == "duty_receipt_declared", source
    reader = RUNNER.load_module("ledger_boundary", RUNNER.LEDGER_BOUNDARY)
    try:
        bound, text = reader.declared_boundary(REPO, RUNNER.DUTY_RECEIPT_BOUNDARY_KEY)
    except reader.SkipGate as exc:
        # The bound is FACTORY DATA (#78 clause b) and this tree declares none, so there
        # is no live declaration for the probes to agree with. `ledger_boundary.py`
        # states the outcome: SKIP, with the reason. The two probes above still ran —
        # only the agreement is set aside — so the skip is narrow, not a blanket pass.
        _declared_skip("the bound is factory data", str(exc))
        return
    except reader.GateError as exc:
        raise AssertionError(
            f"the boundary declaration is unreadable: {exc}"
        ) from exc
    assert text == _DUTY_BOUND, f"the probes and the live declaration disagree: {text}"


def test_the_leg_prints_the_bound_beside_the_population_it_judged() -> None:
    """Acceptance 1's second half: the bound is PRINTED, so a clean verdict can never be
    mistaken for an unbounded one that happened to find nothing.

    Driven through main() rather than the leg alone, because a bound that exists only in
    the data and never reaches the report is a bound nobody can audit. The assertion is
    portable on purpose: a bootstrapped factory declares no key and prints UNDECLARED,
    which satisfies the same property — the reader is always told WHICH bound applied.
    """
    rc, out, err = _run([], [], cron_rows=[_duty_row()], prefixes=["factory-"])
    assert rc == 1, (rc, out[-2000:], err[-2000:])  # the fixture round carries no receipt
    assert "LEG duty-receipt" in out, out
    assert "backward bound `duty_receipt_declared`" in out, out[-3000:]
    assert "forward residual:" in out, out[-3000:]
    assert (_DUTY_BOUND in out) or ("UNDECLARED" in out), (
        "the run must print either the instant it bounded against or say plainly that "
        f"no bound is declared: {out[-3000:]}")



_SKIPS: list[str] = []

# --- #499: the round's FIRES against its RECEIPTS (ruling n=3446) ------------------
# The round is a DAY and a sub-daily job fires several times inside it, so a leg that
# asked only "is there at least ONE receipt for this date?" certified a day that fired
# four times and reported three. `factory-hq-pacemaker` is the live instance: it fired
# four times on 2026-10-06/10-14/10-16 and the leg printed "problems: 0" each day, because
# one of the four receipts satisfied the whole round.
#
# THE FIRES ARE ON THE SAME DATE, hours apart, and `last_run_at` names the NEWEST one —
# the shape the live table has. The receipts are keyed by the FIRE's hour, which is the
# token the box's pacemakers write; a lane that keys its COMPLETION hour writes a row
# that answers no fire, and that is the 10-06 miss reproduced exactly.
_499_FIRE_HOURS = (0.5, 4.5, 8.5, 12.5)  # 07:31 / 11:31 / 15:31 / 19:31 on the round date
_499_ROUND = _plus(_DUTY_BOUND, 0.5)[:10]
# THE READ INSTANT IS FAR PAST THE WINDOW, and it has to be: #449 pairs EVERY fire of the
# round to that round's NEWEST receipt, so a job firing four times a day derives a residual
# of `margin x (last receipt - first fire)` -- here ~33 h, longer than its own 4 h cadence
# (`over_cadence`, reported and never clamped). A probe reading minutes after the fires
# would sit inside that window and be excused by it, which is the leg working correctly and
# the fixture testing nothing. Reading a week out puts every fire past the residual, so what
# the arm does with an ANSWERED and an UNANSWERED fire is what the probes actually measure.
_499_READ_AT = _plus(_DUTY_BOUND, 200.0)

def _499_row(**kw) -> dict:
    """The duty row whose newest fire is the LAST of the four — the round is their date."""
    kw.setdefault("last_run_at", _plus(_DUTY_BOUND, _499_FIRE_HOURS[-1]))
    return _duty_row(**kw)

def _499_receipt(hour: float, n: int, *, token_hour: str | None = None) -> dict:
    """A receipt for the fire at `hour`, or — when `token_hour` is given — one that keys a
    DIFFERENT hour, which is a row that declares a duty and answers no fire."""
    fire = _plus(_DUTY_BOUND, hour)
    token = token_hour if token_hour is not None else fire[11:13]
    return {"n": n, "ts": _plus(_DUTY_BOUND, hour + 0.25), "event": "run",
            "actor": "delegate", "subject": f"registry-attest-{_499_ROUND}T{token}",
            "detail": "the round completed. duty=completed"}

def _499_leg(receipt_hours, *, fires=None, read_at=_499_READ_AT, **kw) -> dict:
    return _duty_leg(
        [_499_row()], list(receipt_hours),
        fires=_fires(fires if fires is not None else _499_FIRE_HOURS),
        read_at=read_at, **kw)

def test_the_fires_arm_REDs_a_round_that_fired_more_often_than_it_reported() -> None:
    """Acceptance 1: four fires, three receipts — the day is UNDER-RECEIPTED and the fire
    that answered nothing is NAMED by its own instant.

    This is the exact state that read CLEAN before the arm existed: one receipt satisfied
    `if not receipts`, and `last_run_at` records only the newest fire, so the three earlier
    ones left no trace in any field the leg read.
    """
    leg = _499_leg([_499_receipt(h, i + 1) for i, h in enumerate(_499_FIRE_HOURS[:3])])
    assert leg["status"] == "ASSERTED", leg["reason"]
    cov = leg["coverage"]
    assert cov["fires_unanswered"] == 1, cov
    assert cov["rounds_under_receipted"] == 1, cov
    named = "\n".join(leg["problems"])
    assert "UNDER-RECEIPTED" in named, named
    assert _plus(_DUTY_BOUND, _499_FIRE_HOURS[-1]) in named, (
        f"the finding must NAME the fire that found no receipt: {named}")
    assert cov["duties_judged"][0]["fires"] == 4, cov["duties_judged"]
    assert cov["duties_judged"][0]["fires_unanswered"] == 1, cov["duties_judged"]

def test_the_fires_arm_is_CLEAN_when_every_fire_answered() -> None:
    """The CONTROL for the probe above: the SAME fixture with the fourth receipt present.

    Without it the RED above is attributable to the fixture rather than to the missing
    receipt — a finding that survives its own input being fixed is not a finding.
    """
    leg = _499_leg([_499_receipt(h, i + 1) for i, h in enumerate(_499_FIRE_HOURS)])
    cov = leg["coverage"]
    assert cov["fires_unanswered"] == 0, (cov, leg["problems"])
    assert cov["rounds_under_receipted"] == 0, cov
    assert not leg["problems"], leg["problems"]

def test_the_fires_arm_REDs_a_receipt_that_keys_its_COMPLETION_hour() -> None:
    """The 10-06 miss, reproduced: the fire is at 06:50 and the lane wrote a `T09` row.

    ONE fire, ONE receipt, and the round matched — so every predicate this leg had before
    the arm read CLEAN. The token answers no fire, so the day is unreported and the arm
    says so. This is the clause that makes the predicate a CONTENT comparison rather than
    a count: a row existing is not a row answering.
    """
    leg = _499_leg([_499_receipt(0.5, 1, token_hour="09")], fires=(0.5,))
    cov = leg["coverage"]
    assert cov["fires_unanswered"] == 1, (cov, leg["problems"])
    assert "UNDER-RECEIPTED" in "\n".join(leg["problems"]), leg["problems"]
    assert cov["duties_missing"] == 0, (
        "the round DID declare a duty — this is the under-receipted class, not a missing "
        f"duty, and folding them together would misreport the repair: {cov}")

def test_the_fires_arm_does_not_charge_a_ROUND_LEVEL_receipt() -> None:
    """The LIVE false RED of 2026-10-16, reproduced: a DATE-ONLY receipt on a 4-fire day.

    `factory-insights-weekly` fired four times and wrote `insights-2026-10-16` — no `T<HH>`
    anywhere, because a round-level job writes ONE receipt for its round. An earlier form of
    this predicate demanded an hour token from every receipt and charged all four fires, so
    three correctly-receipted jobs on the live box read UNDER-RECEIPTED (#146's false-RED
    class, found only by driving the real ledger). The hour is the WRITER's convention to
    choose (#159): where a round's receipts carry no hour at all, the round IS the unit and
    its receipt answers every fire in it.
    """
    date_only = {"n": 1, "ts": _plus(_DUTY_BOUND, 0.75), "event": "run", "actor": "delegate",
                 "subject": f"registry-attest-{_499_ROUND}",
                 "detail": "the round completed. duty=completed"}
    leg = _499_leg([date_only])
    cov = leg["coverage"]
    assert cov["fires_unanswered"] == 0, (cov, leg["problems"])
    assert cov["rounds_under_receipted"] == 0, cov
    assert not leg["problems"], (
        "a round-level receipt declares the round; charging it per-fire is the false RED: "
        f"{leg['problems']}")

def test_the_fires_arm_still_REDs_when_an_HOUR_keyed_round_skips_one() -> None:
    """The CONTROL for the probe above — and the guard against over-correcting into a false
    CLEAN.

    The exemption must key on the ROUND's convention, not on a receipt merely lacking an
    hour: here the round writes hours for 3 of its 4 fires, so the convention IS hour-keyed
    and the fourth fire is genuinely unanswered. A predicate that accepted any date-only
    token would read this CLEAN — and would then also read the 10-06 `T09` miss clean the
    moment one receipt dropped its hour.
    """
    receipts = [_499_receipt(h, i + 1) for i, h in enumerate(_499_FIRE_HOURS[:3])]
    receipts.append({"n": 9, "ts": _plus(_DUTY_BOUND, 1.0), "event": "run",
                     "actor": "delegate", "subject": f"registry-attest-{_499_ROUND}",
                     "detail": "the round completed. duty=completed"})
    leg = _499_leg(receipts)
    cov = leg["coverage"]
    assert cov["fires_unanswered"] == 1, (
        "an hour-keyed round that also carries a bare date token still owes its fourth "
        f"fire a receipt: {cov}")
    assert _plus(_DUTY_BOUND, _499_FIRE_HOURS[-1]) in "\n".join(leg["problems"])

def test_the_fires_arm_counts_only_the_round_it_judges() -> None:
    """A fire on ANOTHER date contributes no round to this one.

    `round_fire_instants` filters by the round's own date, so a job that fired yesterday
    and today is judged per day. Without the filter the older fires would be charged to
    today's receipts and every round would read under-receipted.
    """
    fires = (_499_FIRE_HOURS[0], _499_FIRE_HOURS[0] - 24.0)  # one today, one yesterday
    leg = _499_leg([_499_receipt(_499_FIRE_HOURS[0], 1)], fires=fires)
    cov = leg["coverage"]
    assert cov["duties_judged"][0]["fires"] == 1, (
        f"only the round's OWN date may be counted: {cov['duties_judged']}")
    assert cov["fires_unanswered"] == 0, (cov, leg["problems"])

def test_the_fires_arm_does_not_charge_a_fire_still_inside_its_residual() -> None:
    """The false-RED guard (#146, #200/#449): a fire younger than the job's residual has a
    lane still working on it, and charging it a receipt would trade a false CLEAN for a
    false RED.

    Driven at the helper, where the window is stated rather than derived, so the guard is
    tested as a predicate and not as a side effect of the fixture's timing.
    """
    fire = _plus(_DUTY_BOUND, 0.5)
    read = RUNNER.reader_parse_ts(_plus(_DUTY_BOUND, 0.6))  # 6 minutes after the fire
    assert RUNNER.unanswered_fires(
        [fire], "registry-attest", _499_ROUND, [], residual_secs=3600.0,
        read_instant=read, parse=RUNNER.reader_parse_ts) == [], (
        "a fire inside its residual is IN FLIGHT and owes no receipt yet")
    assert RUNNER.unanswered_fires(
        [fire], "registry-attest", _499_ROUND, [], residual_secs=60.0,
        read_instant=read, parse=RUNNER.reader_parse_ts) == [fire], (
        "past the residual the same fire IS owed a receipt")

def test_the_fires_arm_token_is_BOUNDARY_checked() -> None:
    """`T06` is not satisfied by `T060` — the same boundary guard the round prefix keeps.

    A bare `startswith` would let a receipt for a DIFFERENT hour certify this fire, which
    is a false CLEAN wearing a match.
    """
    fire = _plus(_DUTY_BOUND, 0.5)  # 07:31, token T07
    exact = {"subject": f"registry-attest-{_499_ROUND}T07"}
    wider = {"subject": f"registry-attest-{_499_ROUND}T070"}
    assert RUNNER.unanswered_fires([fire], "registry-attest", _499_ROUND, [exact]) == []
    assert RUNNER.unanswered_fires([fire], "registry-attest", _499_ROUND, [wider]) == [fire], (
        "a token that merely extends the hour's digits answers a DIFFERENT fire")

def test_the_fires_arm_prints_its_population_on_a_CLEAN_round() -> None:
    """#242: a clean round states what it counted. A reader who sees no line cannot tell
    `0 fires unanswered` from `the leg never counted fires` — and a leg that silently
    examines nothing renders exactly like one that examined everything and found nothing.
    """
    rc, out, err = _run(
        [], [_499_receipt(0.5, 1)], cron_rows=[_duty_row()], prefixes=["factory-"],
        cron_fires=_fires((0.5,)))
    assert "LEG duty-receipt" in out, out[-3000:]
    assert "fires vs receipts:" in out, out[-4000:]
    assert "0 fire(s) left unanswered" in out, out[-4000:]
    assert "UNDER-RECEIPTED" not in out, out[-4000:]

def test_the_fires_arm_renders_the_UNDER_RECEIPTED_round_it_found() -> None:
    """The other render branch, driven through `main()`: the fires/receipts line must reach
    the report rather than being computed and dropped (#242's swallow).
    """
    rc, out, err = _run(
        [], [_499_receipt(h, i + 1) for i, h in enumerate(_499_FIRE_HOURS[:3])],
        cron_rows=[_499_row()], prefixes=["factory-"],
        cron_fires=_fires(_499_FIRE_HOURS))
    assert "fires vs receipts:" in out or "UNDER-RECEIPTED" in out, out[-4000:]



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


# --- #500: a NON-POSITIVE measured max is not a measurement ------------------------
# `margin_for` (tools/gate_budget.py) is `4.0 + 0.75/x`, so it DIVIDES by its argument: a
# measured max of 0.0 raises ZeroDivisionError. That is reachable through the residual
# derivation -- a round that fires more than once whose single receipt is ts-EQUAL to the
# round's FIRST fire leaves latencies == [0.0], because the first fire's gap is exactly
# zero and every later fire's gap is NEGATIVE and dropped as a clock artefact.
#
# WHY IT MATTERED: the runner builds its legs in ONE list in main() with no try/except, so
# the exception does not lose one leg -- it takes the WHOLE round down and every leg after
# it never runs. The guard therefore belongs at the CALLER, and these probes pin BOTH
# halves: the caller returns the default, AND `margin_for(0.0)` still raises at the bytes,
# because that predicate is shared law with its own probes on the division.
_500_FIRE_HOURS = (0.5, 4.5, 8.5, 12.5)
_500_READ_AT = _plus(_DUTY_BOUND, 200.0)

def _500_rows() -> list[dict]:
    """ONE receipt, ts-EQUAL to the FIRST of the four fires.

    It answers the first fire exactly and every later fire with a negative gap, so the
    measured max is 0.0 -- NOT None, which is the whole defect: the `is None` guard passed
    it straight through to the division.
    """
    first = _plus(_DUTY_BOUND, _500_FIRE_HOURS[0])
    return [{"n": 1, "ts": first, "event": "run", "actor": "delegate",
             "subject": f"registry-attest-{first[:10]}",
             "detail": "the round completed. duty=completed"}]

def _500_row(**kw) -> dict:
    kw.setdefault("last_run_at", _plus(_DUTY_BOUND, _500_FIRE_HOURS[-1]))
    return _duty_row(**kw)

def _500_residual(rows) -> dict:
    return RUNNER.duty_residual_for(
        _500_row(), "registry-attest", fires=_fires(_500_FIRE_HOURS), ledger_rows=rows)

def test_the_zero_max_guard_keeps_margin_for_RAISING() -> None:
    """Acceptance 1: the guard is at the CALLER, so the SHARED law is unchanged.

    A fix that caught the zero INSIDE `margin_for` would silence the predicate for every
    caller in the fleet, including the gate-budget manifest's own derivation. This asserts
    the raise still happens, at the bytes.
    """
    margin_for = RUNNER.gate_budget_module().margin_for
    try:
        margin_for(0.0)
    except ZeroDivisionError:
        return
    raise AssertionError(
        "margin_for(0.0) no longer raises — the #500 guard leaked into shared law "
        "(tools/gate_budget.py), whose own probes pin the division")

def test_the_zero_max_guard_returns_the_DEFAULT_instead_of_raising() -> None:
    """Acceptance 2: the exact fixture that crashed the derivation returns the default.

    `measured_rounds` is asserted beside the basis, because the requirement is that the
    reading is STATED rather than silent: a default that also hid the one round it measured
    would render identically to a job that never fired at all.
    """
    residual = _500_residual(_500_rows())
    assert residual["basis"] == "default", residual
    assert residual["measured_max_secs"] == 0.0, residual
    assert residual["measured_rounds"] == 1, residual
    assert residual["margin_x"] is None, residual
    assert residual["residual_secs"] == float(RUNNER.DUTY_RESIDUAL_DEFAULT_SECS), residual

def test_the_zero_max_guard_CONTROL_derives_a_POSITIVE_max_normally() -> None:
    """The CONTROL for the probe above: a positive max still DERIVES.

    Without it the default could be the guard firing on EVERY fixture rather than on the
    zero — a change that replaced the whole derivation with the constant would pass the
    probe above and destroy the measurement (#449).
    """
    rows = [{**_500_rows()[0], "ts": _plus(_500_rows()[0]["ts"], 1.0)}]
    residual = _500_residual(rows)
    assert residual["basis"] == "derived", residual
    assert residual["measured_max_secs"] == 3600.0, residual
    assert residual["margin_x"] is not None, residual

def test_the_zero_max_guard_reaches_the_LEG_and_it_keeps_its_shape() -> None:
    """Acceptance 3: the fixture driven through `duty_receipt_leg`, the path a round runs.

    A guard that only satisfied the helper would leave the crash on the real path, and the
    leg is what the patrol actually calls. The assertion is that the leg RETURNS and that
    the record is the leg's normal shape — before the guard the exception propagated out of
    the derivation and, with no try/except around the leg list, took the round down.
    """
    leg = _duty_leg([_500_row()], _500_rows(), fires=_fires(_500_FIRE_HOURS),
                    read_at=_500_READ_AT)
    assert set(leg) >= {"name", "status", "problems", "excused", "coverage"}, sorted(leg)
    assert leg["status"] in ("ASSERTED", "NOT RUN"), leg["status"]
    assert leg["name"] == "duty-receipt", leg["name"]

def test_the_zero_max_guard_STATES_the_reading_in_the_render() -> None:
    """The render distinguishes a measured ZERO from an absent measurement.

    "no measurable round" and "measured, and the number is zero" are different facts, and a
    render printing one sentence for both would report a silent job and a clock-artefact job
    identically. The second half is the control: the absent case must not borrow the
    non-positive wording.
    """
    zero_text = RUNNER.duty_residual_basis_text(
        {"basis": "default", "measured_max_secs": 0.0, "measured_rounds": 1})
    absent_text = RUNNER.duty_residual_basis_text(
        {"basis": "default", "measured_max_secs": None, "measured_rounds": 0})
    assert "NON-POSITIVE" in zero_text, zero_text
    assert "NON-POSITIVE" not in absent_text, absent_text

# --- #501: a RAISING leg is CONTAINED, NAMED, and cannot take the round down ----------
# `main()` builds its legs EAGERLY in one list literal with no try/except before the
# exit-code line, so a raise in ANY leg aborted the round mid-build: every leg AFTER it
# never ran, and left NO trace of its own -- no NOT RUN line, no problem, no coverage
# count. That is the silent-failure class, and it is worse than a red leg because a red leg
# is visible and a vanished one is not.
#
# The remedy is CONTAINMENT at the RUNNER (#501): the leg FAILS by name with its reason,
# its problem still moves the exit code, and its neighbours still run. `margin_for` is NOT
# widened -- the #500 probes above pin that, and the guard belongs at this call site.

def _501_clean():
    """A board the round can sweep clean, so the ONLY variable is the raising leg."""
    issues = [_issue(1, "OPEN")]
    rows = _rows(("intake", "#1", 1), ("ruling", "#1", 5))
    return issues, rows

def _raising_publish_leg(*, read_at: str) -> dict:
    """A MIDDLE leg that raises, so legs on BOTH sides of it are asserted to survive.

    `publish-freshness` is leg 16 of 18: `kit-drift` precedes it and `worktree` and
    `pacemaker-presence` follow it. Under the old shape those last two were exactly the
    legs that vanished.
    """
    raise RuntimeError("probe: the publish leg could not read the remote")

def _leg_names(text: str) -> list[str]:
    return [line.split()[1] for line in text.splitlines() if line.startswith("LEG ")]

def _leg_status(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        if line.startswith("LEG ") and " \u2014 " in line:
            name, status = line[4:].split(" \u2014 ", 1)
            out[name] = status
    return out

def test_a_contained_round_still_carries_EVERY_leg_the_clean_round_carries() -> None:
    """The crux: a raise used to DELETE every leg after it, with no trace of its own.

    This is asserted as SET AND ORDER equality against a clean round's own leg list, so the
    probe fails both when a leg vanishes AND when the containment guard's name table drifts
    away from the legs it names -- a contained leg is only useful if the name is right.
    """
    issues, rows = _501_clean()
    _, clean_out, _ = _run(issues, rows)
    _, out, _ = _run(issues, rows, publish_fn=_raising_publish_leg)

    clean, got = _leg_names(clean_out), _leg_names(out)
    assert got == clean, (
        "a contained round must carry the SAME legs as a clean one, in the same order -- a "
        f"missing leg IS the silent failure #501 is about\nclean: {clean}\ngot:   {got}"
    )
    # EXACTLY ONE status may differ from the clean round's: the raiser's. Comparing against
    # the clean run's OWN statuses rather than against "ASSERTED" is the point -- several
    # legs are legitimately NOT RUN under `_run`'s inert defaults, and a probe that demanded
    # ASSERTED of them would be asserting the fixture, not the containment.
    clean_statuses = _leg_status(clean_out)
    statuses = _leg_status(out)
    assert statuses == {**clean_statuses, "publish-freshness": "FAILED"}, (
        "containment must change EXACTLY the raising leg's status and nothing else\n"
        f"clean: {clean_statuses}\ngot:   {statuses}"
    )

def test_a_raising_leg_is_NAMED_with_its_reason_and_moves_the_exit_code() -> None:
    """Criterion (a)+(d): a FAILED leg named for ITSELF, with the reason, and rc reflects it.

    A containment that swallowed the problem would be worse than the abort: the round would
    read CLEAN over a leg that never ran. So the problem is asserted to be COUNTED and the
    exit code asserted to move.
    """
    issues, rows = _501_clean()
    rc, out, _ = _run(issues, rows, publish_fn=_raising_publish_leg)

    assert rc == 1, f"a contained leg's problem must still move the exit code\n{out}"
    block = out.split("LEG publish-freshness")[1].split("LEG ")[0]
    assert "FAILED" in block.split("\n")[0], block
    assert "RuntimeError" in block, block
    assert "could not read the remote" in block, block
    assert "problems: 1" in block, block
    assert "UNKNOWN" in block, (
        f"the containment must state that the leg's verdict is UNKNOWN, not clean: {block}"
    )
    assert "verdict:" in out, f"the round must STILL print a verdict\n{out}"

def test_the_containment_guard_changes_NOTHING_on_a_clean_round() -> None:
    """CONTROL: with no leg raising, the guard is invisible -- rc, verdict and legs alike.

    A guard that perturbed the clean path would move every other probe in this file, and
    the honest way to say it does not is to assert the clean round is unchanged.
    """
    issues, rows = _501_clean()
    rc, out, _ = _run(issues, rows)

    assert rc == 0, f"a clean round must stay clean\n{out}"
    assert "FAILED" not in out, out
    assert "0 problem(s)" in out, out
    assert len(_leg_names(out)) == len(set(_leg_names(out))), "no leg may be named twice"

def test_the_board_read_abort_path_is_UNCHANGED_by_the_containment_guard() -> None:
    """Criterion (c): the abort BEFORE the legs is by design, and it is the leg-free case.

    The board read happens before any leg exists, so containment cannot apply there: the run
    must still abort with rc=2, name every leg NOT RUN, and print NO verdict. A guard that
    caught this too would replace a loud abort with a quiet round over zero issues.
    """
    def _boom(slug):
        raise RUNNER.BoardReadError("probe: the board could not be read")

    out, err = io.StringIO(), io.StringIO()
    rc = RUNNER.main(
        [], board_fn=_boom, slug_fn=lambda: "owner/repo", rows_fn=lambda: [],
        out=lambda *a, **k: print(*a, file=out, **k),
        err=lambda *a, **k: print(*a, file=err, **k),
        publish_fn=_stub_publish_leg, shared_tree_fn=_stub_shared_tree_rider,
        # #133: the driverless-lane leg's goal store and its turn-in-flight read are
        # injected here for the same reason every other live surface is -- and the
        # defaults WITHHOLD the driven claim (empty store, no turn open) rather than
        # granting one, so a probe that never asserts a driver cannot read one.
        driverless_goals_fn=lambda: _EMPTY_GOAL_STORE,
        driverless_turn_open_fn=lambda: {},
    )
    assert rc == 2, f"the board-read abort must be unchanged, got rc={rc}"
    assert "NOT RUN: every leg" in err.getvalue(), err.getvalue()
    assert "verdict" not in out.getvalue(), out.getvalue()

def test_a_raise_in_the_FIRST_leg_still_prints_a_verdict() -> None:
    """Criterion (b), on the leg whose OWN render branch reads coverage keys it lacks.

    The probes above raise in `publish-freshness`, which is leg 16 of 18 AND whose render
    branch is status-guarded -- so they prove the BUILD half (the leg is named, its problem
    counts, its neighbours survive) but they cannot exercise the REPORT half, because that
    leg's branch tolerates a leg that never built. `board-intake` is leg 1 of 18 and its
    branch reads `forward_issues_examined` and `reverse_intake_rows_examined` with NO status
    guard, and a leg that never built has neither key.

    So without the FAILED branch the round raises `KeyError` while printing its own report:
    the same silent-failure class one layer down, and the reason the branch is load-bearing
    rather than decorative. Disable it and this probe errors with the KeyError; that is its
    bite, and it is the only probe here that bites on the report half at all.
    """
    real = RUNNER.board_intake_leg

    def _boom(*a, **k):
        raise RuntimeError("probe: board-intake could not read the board")

    issues, rows = _501_clean()
    _, clean_out, _ = _run(issues, rows)

    RUNNER.board_intake_leg = _boom
    try:
        rc, out, err = _run(issues, rows)
    finally:
        RUNNER.board_intake_leg = real

    assert "verdict:" in out, f"the round must STILL print a verdict\n{out}\n{err}"
    assert rc == 1, f"a contained leg's problem must still move the exit code\n{out}"
    block = out.split("LEG board-intake")[1].split("LEG ")[0]
    assert "FAILED" in block.split("\n")[0], block
    assert "RuntimeError" in block, block
    # Leg 1 raising must not delete the other seventeen: the report is built from the SAME
    # leg list the clean round produced, in the same order.
    assert _leg_names(out) == _leg_names(clean_out), (
        "a raise in the FIRST leg must not vanish the ones after it\n"
        f"clean: {_leg_names(clean_out)}\ngot:   {_leg_names(out)}"
    )

# --- #242: attribution by GIT COMMON DIR, and an empty prefix set is NOT RUN ---------

def _git_repo_with_worktree(root: Path) -> tuple[Path, Path]:
    """`(main_checkout, linked_worktree)` — a real worktree, not a path that looks like one.

    Both are derived from the fixture, so the probe resolves in any factory. A linked
    worktree is the move this factory PRESCRIBES for a diverged tree, which is why the
    attribution defect hid behind the remedy rather than behind an exotic state.
    """
    main = root / "main"
    main.mkdir(parents=True)
    for args in (["init", "-q", "-b", "main"],
                 ["config", "user.email", "probe@example.invalid"],
                 ["config", "user.name", "probe"]):
        subprocess.run(["git", "-C", str(main), *args], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (main / "a.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(main), "add", "-A"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "-C", str(main), "commit", "-q", "-m", "one"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    linked = root / "linked"
    subprocess.run(["git", "-C", str(main), "worktree", "add", "-q", str(linked)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return main, linked

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


def test_probe_the_common_dir_is_shared_by_a_linked_worktree() -> None:
    """The mechanism: a worktree and its main checkout resolve to ONE repository identity.

    Keyed on the CHECKOUT they are two paths and neither matches the manifest's declared
    repo from the other — which is how a lane patrolling from a worktree silently judged
    nobody.
    """
    tmp_path = _scratch()
    main, linked = _git_repo_with_worktree(tmp_path)
    a, b = RUNNER.git_common_dir(main), RUNNER.git_common_dir(linked)
    assert a is not None and b is not None, (a, b)
    assert a == b, f"the common dir must be shared: main={a} linked={b}"
    assert a != linked.resolve(), "a worktree's own path is NOT its repository identity"

def test_probe_the_RELATIVE_OUTPUT_TRAP_is_pinned() -> None:
    """THE TRAP, pinned so a naive edit REDs instead of silently returning [].

    From the MAIN checkout `git rev-parse --git-common-dir` prints the RELATIVE string
    ".git". So `Path(raw).resolve()` resolves against the CALLER's cwd and yields a path
    that matches nothing — the SAME empty result the defect produces, wearing the shape of
    a fix. The repo-relative join is what makes it correct from both ends.
    """
    tmp_path = _scratch()
    main, linked = _git_repo_with_worktree(tmp_path)
    raw = subprocess.run(["git", "-C", str(main), "rev-parse", "--git-common-dir"],
                         capture_output=True, text=True, check=True).stdout.strip()
    assert raw == ".git", (
        f"the premise of this probe is that the main checkout prints a RELATIVE path; it "
        f"printed {raw!r} — re-derive the trap before trusting the fix"
    )
    # The naive form, resolved from a cwd that is NOT the repo — the exact edit a future
    # reader would make.
    naive = (tmp_path / raw).resolve()
    assert naive != RUNNER.git_common_dir(main), (
        "the naive `Path(raw).resolve()` must NOT accidentally be correct"
    )
    # And the repo-relative join IS correct, from both ends.
    assert (main / raw).resolve() == RUNNER.git_common_dir(main)
    assert RUNNER.git_common_dir(main) == RUNNER.git_common_dir(linked)

def test_probe_an_empty_prefix_set_makes_the_three_cron_legs_NOT_RUN() -> None:
    """#242 clause 4: prefixes == [] is an UNATTRIBUTABLE population, never a clean box.

    The legs already carry the discriminating counter and `declared_prefixes`' own
    docstring already obliged the caller; ONE caller with THREE call sites complied with
    neither. So a lane from a worktree read `ASSERTED ... 0 problems` from a leg that
    judged nothing — and, in the duty-receipt case, a positive FALSE CONCLUSION.
    """
    rows = [{"name": "factory-x-job", "home": "probe-home", "enabled": True,
             "prompt": "do a thing", "deliver_to": "", "last_run_at": _DUTY_FIRE}]
    with tempfile.TemporaryDirectory() as tmp:
        out = io.StringIO()
        RUNNER.main(
            [], board_fn=lambda slug: [], slug_fn=lambda: "owner/repo",
            rows_fn=lambda: [], cron_rows_fn=lambda: (rows, ["probe-home"], []),
            cron_fires_fn=lambda: [],
            prefixes_fn=lambda: [],
            log_dir=Path(tmp) / "logs",
            scores_dir_fn=lambda: _EMPTY_SCORES_DIR,
            kit_manifest=_synthetic_kit(Path(tmp), files={"tools/a.py": b"a"},
                                        members={})[0],
            fleet_manifest=_synthetic_kit(Path(tmp), files={"tools/a.py": b"a"},
                                          members={})[1],
            out=lambda *a, **k: print(*a, file=out, **k),
            err=lambda *a, **k: None,
            publish_fn=_stub_publish_leg,
            shared_tree_fn=_stub_shared_tree_rider,
            # #133: the driverless-lane leg's goal store and its turn-in-flight read are
            # injected here for the same reason every other live surface is -- and the
            # defaults WITHHOLD the driven claim (empty store, no turn open) rather than
            # granting one, so a probe that never asserts a driver cannot read one.
            driverless_goals_fn=lambda: _EMPTY_GOAL_STORE,
            driverless_turn_open_fn=lambda: {},
            # #330: the ref-role store is injected for the same reason the ruling table is.
            ref_role_exemptions_path=_NO_REF_ROLE_EXEMPTIONS,
        # #507: the criterion-path store, injected for the same reason.
        criterion_exemptions_fn=lambda: _NO_CRITERION_EXEMPTIONS,
        )
        text = out.getvalue()

    for name in ("cron-thinness", "notify-receipt", "duty-receipt"):
        block = text.split(f"LEG {name}")[1].split("LEG ")[0]
        assert "NOT RUN" in block.split("\n")[0], f"{name} must be NOT RUN: {block!r}"
        assert "UNATTRIBUTED" in block, f"{name} must name its unattributed population: {block!r}"
        assert "resolves to no factory" in block, (
            f"{name} must name the manifest reason: {block!r}"
        )
    assert "so no duty owes a receipt on this box" not in text, (
        "the reason must not assert a fact about the box over an empty population"
    )

_OWES_NONE_PROMPT = (
    "Thin trigger only — do NOT execute any project work yourself. Run the pusher, then "
    "stop.\n\nreceipt_subject: none\n"
)

def test_an_OWES_NONE_declaration_reads_OWES_NONE_and_hunts_no_receipt() -> None:
    """#424 items 1+2+3-clause-3 — ordered at n=2723, re-sequenced at n=3228.

    `factory-publish` runs the pusher in the cron's OWN session, and the ledger's actor set is
    closed — SKILL.md section 11 names the pusher a TOOL, not a lane — so its duty owes no
    receipt at all. Before the bucket the leg read `none` as a STEM, hunted `none-<round>*`,
    found nothing, and RED every round: the false MISSING the amendment ruling reproduced by
    running this very reader hermetically.
    """
    row = _duty_row(prompt=_OWES_NONE_PROMPT)
    leg = _duty_leg([row], [], read_at=_plus(_DUTY_FIRE, 5.0))
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["jobs_owing_none"] == 1, leg["coverage"]
    assert leg["coverage"]["owes_none_jobs"] == ["factory-registry-attest"], leg["coverage"]
    # THE TWO SILENCES ARE COUNTED APART: a row that DECLARED it owes none is not a row that
    # declared nothing, and folding them into one number reports the second as the first.
    assert leg["coverage"]["jobs_declaring_receipt"] == 0, leg["coverage"]
    assert leg["coverage"]["jobs_undeclared"] == 0, leg["coverage"]
    # AND THE BUCKET REACHES THE REPORT. Driven from a MIXED population on purpose: a leg
    # whose judged population is empty renders through the generic NOT-RUN block, so an
    # owes-none row ALONE could never prove the bucket is PRINTED — only that it is counted.
    # `factory-publish` owes none beside a duty that does, which is the live shape.
    owes_none = _duty_row(name="factory-publish", prompt=_OWES_NONE_PROMPT,
                          row_id="e30bfc83-3fee-400a-945d-e74b962c142e")
    rc, out, err = _run([], [], cron_rows=[owes_none, _duty_row()], prefixes=["factory-"],
                        cron_fires=_fires((0.5,)))
    assert "OWES NONE" in out, out[-2500:]
    assert "factory-publish" in out, out[-2500:]
    assert "declare NOTHING and are NOT JUDGED" in out, out[-2500:]

def test_the_OWES_NONE_bucket_is_what_stops_the_false_MISSING() -> None:
    """The neuter probe, and without it the arm above proves nothing.

    The neutered reader differs from the live one in ONE respect — whether the token `none` is
    a declaration that nothing is owed or a stem to hunt — so a verdict that MOVES under it is
    attributable to the bucket rather than to the fixture.
    """
    row = _duty_row(prompt=_OWES_NONE_PROMPT)
    assert _duty_leg([row], [], read_at=_plus(_DUTY_FIRE, 5.0))["problems"] == []

    real = RUNNER.declared_receipt_disposition

    def _pre_bucket(prompt):
        disposition, stem = real(prompt)
        return ("declares", stem or RUNNER.RECEIPT_OWES_NONE_TOKEN) if (
            disposition == "owes_none") else (disposition, stem)

    RUNNER.declared_receipt_disposition = _pre_bucket
    try:
        neutered = _duty_leg([row], [], read_at=_plus(_DUTY_FIRE, 5.0))
    finally:
        RUNNER.declared_receipt_disposition = real
    assert neutered["problems"], (
        "reading `none` as a STEM must RED the round again — the bucket is the only thing "
        f"standing between this row and a false MISSING every round: {neutered['coverage']}"
    )
    assert "NO duty receipt" in neutered["problems"][0], neutered["problems"][0]

def test_the_SUPPRESSION_predicate_is_anchored_to_the_DAEMONS_own_wording() -> None:
    """#477. The anchor is the daemon's EMITTED text, read here from the CONSTANT rather than
    from a copied literal — so a change in that wording moves this probe instead of silently
    un-excusing every gated round on the box."""
    assert RUNNER.fire_is_suppressed(
        f"Trigger condition not met (exit_code=0, output_bytes=0). "
        f"{RUNNER.CRON_SUPPRESSION_MARKER}."
    ), "the daemon's own suppression wording must read as suppressed"
    assert RUNNER.fire_is_suppressed(
        f"Trigger condition not met (exit_code=1, output_bytes=19070). "
        f"{RUNNER.CRON_SUPPRESSION_MARKER}."
    ), "the marker is the wording, not the exit code — both codes are emitted"
    assert not RUNNER.fire_is_suppressed(""), "an empty run record is not a suppression"
    assert not RUNNER.fire_is_suppressed("the round completed. duty=completed"), (
        "a round that RAN and declared its duty must never read as suppressed"
    )

def test_a_SUPPRESSED_round_is_EXCUSED_and_never_a_missing_duty() -> None:
    """#477 on the round the leg judges directly.

    The round fired on time, the run is stored `status=success`, and no receipt exists — the
    exact shape this leg exists to red, and legitimate all the same, because the job's own
    trigger gate never let the lane wake.
    """
    fires = _fires((0.5,), suppressed=True)
    leg = _duty_leg([_duty_row()], [], fires=fires, read_at=_plus(_DUTY_FIRE, 5.0))
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["rounds_excused_by_suppression"] == 1, leg["coverage"]
    assert any(RUNNER.CRON_SUPPRESSION_MARKER in e for e in leg["excused"]), leg["excused"]

def test_the_SUPPRESSION_excuse_is_what_stops_the_red_round() -> None:
    """The neuter probe for #477: blind the leg to the fire's flag and the round REDS again.

    Built by REMOVING the field the live source carries, not by editing a constant, because
    that is the defect exactly — before #477 the reader did not carry it at all.
    """
    fires = _fires((0.5,), suppressed=True)
    blind = [{k: v for k, v in f.items() if k != "suppressed"} for f in fires]
    assert _duty_leg([_duty_row()], [], fires=fires,
                     read_at=_plus(_DUTY_FIRE, 5.0))["problems"] == []
    neutered = _duty_leg([_duty_row()], [], fires=blind, read_at=_plus(_DUTY_FIRE, 5.0))
    assert neutered["coverage"]["rounds_excused_by_suppression"] == 0, neutered["coverage"]
    assert len(neutered["problems"]) == 1, neutered["problems"]
    assert "NO duty receipt" in neutered["problems"][0], neutered["problems"][0]

def test_a_SUPPRESSED_PRIOR_round_is_excused_on_the_round_the_leg_JUDGES() -> None:
    """#477 on the #281 path, which is the LIVE case rather than a corner.

    `factory-questions-redeliver` carries a 1800 s default residual against a 6 h cadence, so
    its newest round is ALWAYS in flight and the round this leg actually judges is the prior
    one. An excuse wired only to the newest round would leave the live defect standing.
    """
    row = _duty_row(last_run_at=_plus(_DUTY_BOUND, 24.5))
    newest = _fires((24.5,))[0]                       # the round that RAN
    prior = _fires((0.25,), suppressed=True)[0]       # the PRIOR round, suppressed
    fires = [prior, newest]
    leg = _duty_leg([row], [], fires=fires, read_at=_plus(_DUTY_BOUND, 24.5 + 0.1))
    assert leg["coverage"]["rounds_judged_by_fallback"] == 0, (
        f"this fixture must be excused on the PRIOR round, not judged: {leg['coverage']}"
    )
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["rounds_excused_by_suppression"] == 1, leg["coverage"]
    assert any("PRIOR round" in e for e in leg["excused"]), leg["excused"]

def test_a_NON_suppressed_round_still_REDS_so_the_excuse_is_no_false_CLEAN() -> None:
    """The alternative #477's ruling REFUSED, kept as a probe.

    A declaration-based excuse ("this duty is conditional") would also cover a conditional duty
    that genuinely ran and produced nothing. This is that case: the fire record is present,
    carries no suppression wording, and the round must still RED.
    """
    leg = _duty_leg([_duty_row()], [], fires=_fires((0.5,)),
                    read_at=_plus(_DUTY_FIRE, 5.0))
    assert leg["coverage"]["rounds_excused_by_suppression"] == 0, leg["coverage"]
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "NO duty receipt" in leg["problems"][0], leg["problems"][0]

def test_a_round_no_fire_record_MATCHES_is_JUDGED_and_never_excused() -> None:
    """An unreadable or mismatched fire table must not silently excuse every duty on the box.

    The round's instant is matched to a record by INSTANT, so a record belonging to another
    job can never stand in for it — and a suppression that cannot be ATTRIBUTED to this round
    is one this leg must not act on.
    """
    foreign = {"job_id": "some-other-job", "job_name": "some-other-job",
               "started_at": _DUTY_FIRE, "content": f"{RUNNER.CRON_SUPPRESSION_MARKER}.",
               "suppressed": True}
    leg = _duty_leg([_duty_row()], [], fires=[foreign], read_at=_plus(_DUTY_FIRE, 5.0))
    assert leg["coverage"]["rounds_excused_by_suppression"] == 0, leg["coverage"]
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "NO duty receipt" in leg["problems"][0], leg["problems"][0]

def test_probe_the_duty_reason_NAMES_its_population_and_refuses_the_conclusion() -> None:
    """#242 clause 5. The old text ended "so no duty owes a receipt on this box" — a
    POSITIVE claim about the box drawn from an enumeration that can be empty. An empty
    population supports a statement about the READ, never a conclusion about duties.
    """
    rows = [{"name": "factory-x-job", "home": "probe-home", "enabled": True,
             "prompt": "no receipt declaration here", "deliver_to": "",
             "last_run_at": _DUTY_FIRE}]
    leg = RUNNER.duty_receipt_leg(rows, ["probe-home"], [], ["factory-"], [],
                                  read_at="probe")
    # the STATUS moved with #506 (a census that declares nothing now carries a finding, so
    # the leg is ASSERTED); the clause-5 property below is about the REASON and is unchanged
    assert leg["status"] == "ASSERTED", leg["status"]
    reason = leg["reason"]
    assert "NONE names a receipt STEM to judge" in reason, reason
    assert "NO DUTY WAS JUDGED" in reason, reason
    assert "never a finding" in reason, reason
    assert "so no duty owes a receipt on this box" not in reason, reason
    assert "1 enabled row(s) this factory declares" in reason, (
        f"the reason must name the population it enumerated: {reason}"
    )
    # #424 item 2 / #477: the reason must separate the TWO ways a row can be silent about a
    # receipt -- declaring it OWES NONE (a declaration, read and honoured) and carrying no
    # `receipt_subject:` line at all (a silence the leg cannot act on). A reason that prints
    # one number for both reports the second as the first.
    assert "declares it OWES NONE" in reason, reason
    assert "carries no `receipt_subject:` line at all" in reason, reason

def test_probe_every_probe_is_callable_by_the_SCRIPT_runner() -> None:
    """This file has TWO runners, and a probe must satisfy both (#242, measured).

    `main()` calls every `test_*` with NO arguments, so a probe that takes `tmp_path`
    passes under pytest and raises TypeError under the audit's own invocation — a probe
    that is green in one runner and absent in the other. Measured while landing #242: two
    of the four new probes took `tmp_path` and the script form died on the first of them
    while pytest reported 119 passed.
    """
    import inspect

    offenders = []
    for name, value in sorted(globals().items()):
        if not (name.startswith("test_") and callable(value)):
            continue
        required = [
            p for p in inspect.signature(value).parameters.values()
            if p.default is inspect.Parameter.empty
            and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        if required:
            offenders.append(f"{name} requires {[p.name for p in required]}")
    assert offenders == [], (
        "every probe must be callable with no arguments, because main() runs them that "
        "way: " + "; ".join(offenders)
    )

# --- #243: the ruling leg resolves through a leg-local resolver ----------------------

def test_probe_the_strict_arm_still_resolves() -> None:
    """Arm 1, and the reason the shared predicate is NOT widened: `issue_reference` is
    strictly numeric by design and its own gate depends on that."""
    pred = RUNNER.load_predicate()
    ruling = {"n": 1, "event": "ruling", "subject": "#42", "detail": "ruled"}
    issue, arm = RUNNER.resolve_ruling_issue(ruling, [ruling], pred)
    assert (issue, arm) == (42, "strict"), (issue, arm)

def test_probe_the_BRIDGE_resolves_a_slug_subject() -> None:
    """Arm 2 — the shape the ledger really carries, and the one #243 was filed for.

    The ruling is stamped under a SLUG (`foreign-instrument-coupling`) while the issue is
    filed a row later under `#85`, so the strict form returns None and the row is invisible
    to `ruled`. The bridge is a row that REFERENCES this ruling's `n` and itself names an
    issue — which is exactly the real n=545 / n=546 pair.
    """
    pred = RUNNER.load_predicate()
    ruling = {"n": 545, "event": "ruling", "subject": "foreign-instrument-coupling",
              "detail": "OWNER ORDER: do not use the instruments ..."}
    dispatch = {"n": 546, "event": "dispatch", "subject": "#85",
                "detail": "DISPATCH #85 ... Ruling n=545; issue filed at https://x/issues/85"}
    issue, arm = RUNNER.resolve_ruling_issue(ruling, [ruling, dispatch], pred)
    assert (issue, arm) == (85, "bridged"), (issue, arm)

    # A bare-number subject is ALSO a real form (n=516 carries subject `77`, which its own
    # correction row n=518 complains about) — so the bridge must read it too.
    bare = {"n": 517, "event": "dispatch", "subject": "77", "detail": "see Ruling n=545"}
    issue, arm = RUNNER.resolve_ruling_issue(ruling, [ruling, bare], pred)
    assert (issue, arm) == (77, "bridged"), (issue, arm)

def test_probe_the_DECLARED_arm_is_constructible_because_it_has_NO_live_instance() -> None:
    """Arm 3, driven off a FIXTURE because the token has zero live rows.

    Measured by Triage: `governs=` occurs exactly twice in the whole ledger — inside the
    ruling that PRESCRIBES it and its dispatch. So the arm is prospective, and a probe that
    could not construct it would leave the arm unexercised while reading as covered.
    """
    pred = RUNNER.load_predicate()
    ruling = {"n": 900, "event": "ruling", "subject": "some-concern",
              "detail": "a ruling that governs a concern rather than an item. governs=1234"}
    issue, arm = RUNNER.resolve_ruling_issue(ruling, [ruling], pred)
    assert (issue, arm) == (1234, "declared"), (issue, arm)

def test_probe_the_leg_PRINTS_an_unbridgeable_row_instead_of_dropping_it() -> None:
    """Clause 2: a resolver that cannot place a row must SAY SO.

    Silence here reports a smaller population than the leg examined — the leg would read
    as though every ruling resolved, which is the false-clean shape the population clause
    forbids. The count travels beside the verdict.
    """
    pred = RUNNER.load_predicate()
    ruling = {"n": 901, "event": "ruling", "subject": "no-issue-anywhere",
              "detail": "governs nothing identifiable"}
    issue, arm = RUNNER.resolve_ruling_issue(ruling, [ruling], pred)
    assert (issue, arm) == (None, "unbridgeable"), (issue, arm)

    # ...and the leg's coverage carries them, so the print is not the only reader.
    issues = [_issue_with_comments(1, "OPEN", "## RULED — a ruling.\n")]
    rows = [ruling, {"n": 902, "event": "intake", "subject": "#1", "detail": "intake"}]
    leg = RUNNER.board_ruling_leg(issues, rows, read_at="probe", predicate=pred,
                                  scope=RUNNER.UNBOUNDED_SCOPE,
                                  exemptions_path=_NO_RULING_EXEMPTIONS)
    cov = leg["coverage"]
    assert cov["rulings_unbridgeable"] == 1, cov
    assert cov["unbridgeable_rows"] == [{"n": 901, "subject": "no-issue-anywhere"}], cov
    assert cov["rulings_read"] == cov["rulings_resolved"] + cov["rulings_unbridgeable"], cov

def test_probe_the_BRIDGE_is_the_thing_that_moves_the_population() -> None:
    """The NON-VACUITY control for clause 3 — re-armed by #511, on the surface it still owns.

    Neutering the bridge moves the bridged row out of the RESOLVED population. The probe
    drives the REAL leg twice over one fixture: once with the dispatch present, once without
    — so the difference is attributable to the bridge and not to the fixture.

    WHAT #511 CHANGED HERE, and why the old assertion was wrong rather than merely failing.
    This probe used to assert that dropping the bridge produced a PROBLEM, because the
    issue-level short-circuit judged a comment only when its issue resolved to a `ruling`
    row. Under per-act pairing the verdict belongs to the COMMENT ID: the row names
    `comment=<id>`, the id is globally unique, and so the act IS recorded whether or not the
    row's SUBJECT can be attributed to an issue. Keeping the old assertion would have
    restored the short-circuit it was written against — a problem invented from an
    unresolvable subject, which is the same false red one layer over. The bridge's remaining
    job is the POPULATION question, and that is what is asserted: the row is resolved, or it
    is PRINTED as unbridgeable, never silently dropped (#243 clause 2).
    """
    pred = RUNNER.load_predicate()
    issues = [_issue_with_comments(85, "OPEN", "## RULED — settled on the board.\n")]
    ruling = {"n": 545, "event": "ruling", "subject": "foreign-instrument-coupling",
              "detail": f"the clause comment={_comment_numeric(85)}"}
    dispatch = {"n": 546, "event": "dispatch", "subject": "#85", "detail": "Ruling n=545"}

    with_bridge = RUNNER.board_ruling_leg(issues, [ruling, dispatch], read_at="probe",
                                          predicate=pred,
                                          scope=RUNNER.UNBOUNDED_SCOPE,
                                          exemptions_path=_NO_RULING_EXEMPTIONS)
    assert with_bridge["problems"] == [], with_bridge["problems"]
    assert with_bridge["coverage"]["rulings_resolved"] == 1, with_bridge["coverage"]
    assert with_bridge["coverage"]["rulings_unbridgeable"] == 0, with_bridge["coverage"]
    assert with_bridge["coverage"]["rulings_paired"] == 1, with_bridge["coverage"]

    # Remove ONLY the bridge row: the row leaves the resolved population and is PRINTED.
    without = RUNNER.board_ruling_leg(issues, [ruling], read_at="probe", predicate=pred,
                                      scope=RUNNER.UNBOUNDED_SCOPE,
                                      exemptions_path=_NO_RULING_EXEMPTIONS)
    assert without["coverage"]["rulings_resolved"] == 0, without["coverage"]
    assert without["coverage"]["rulings_unbridgeable"] == 1, without["coverage"]
    assert without["coverage"]["unbridgeable_rows"] == [
        {"n": 545, "subject": "foreign-instrument-coupling"}
    ], without["coverage"]["unbridgeable_rows"]
    # The ACT is still recorded, so the comment is still paired: two questions, two surfaces.
    assert without["coverage"]["rulings_paired"] == 1, without["coverage"]
    assert without["problems"] == [], without["problems"]

# --- #245: the ruling predicate's head alternation, and the clause that keeps it honest ---

def test_the_widened_head_ADMITS_the_spellings_the_board_actually_uses() -> None:
    """#245 done-when 1, the widening arm: `## Amendment` IS a ruling head.

    `#133` is the measured case — its two `## Amendment` comments ARE its ruling, while the
    strict predicate returned None for them, so the issue read as unruled from the BOARD as
    well as from the ledger. `#148` is the same spelling with a `ruling` row already stamped.
    Both arms are driven here: the new spelling is admitted, and the two original forms are
    NOT displaced by the widening.
    """
    for body in ("## RULED — shape (2), settled.\n",
                 "## RULING — the clause reads as follows.\n",
                 "## Amendment — done-when 3 resolved, and it is not conditional.\n"):
        issue = _issue_with_comments(133, "OPEN", body)
        assert RUNNER.ruling_comment(issue) is not None, f"not admitted: {body!r}"
        assert RUNNER.unmatched_heading_comments(issue) == [], body

def test_the_ruling_predicate_is_BOUNDARY_checked() -> None:
    """A prefix match admits an EXTENSION unless the boundary is checked.

    `## RULINGS — the ledger` starts with `## RULING`, so a bare `str.startswith` would read
    a DIFFERENT heading as this one — the digit-extension class this factory has filed
    repeatedly. Measured over the live board before the check was written: 0 headings extend
    an accepted form, so this arm exists so the population cannot move tomorrow, not because
    it moves today. Both sides are asserted, so the check cannot be satisfied by a predicate
    that refuses everything.
    """
    for head in ("## RULINGS — the ledger", "## RULEDLY", "## Amendment2"):
        assert not RUNNER._accepted_heading(head), head
    for head in ("## RULED", "## RULED — shape (2)", "## RULING", "## Amendment",
                 "## Amendment — x", "## RULED: a colon is a boundary"):
        assert RUNNER._accepted_heading(head), head

def test_the_leg_PRINTS_a_head_it_did_NOT_match() -> None:
    """#245 done-when 2: the clause that keeps the widening from reproducing the defect.

    A NOVEL head — one no one has written before — must surface as a printed line with its
    issue number on the run that first meets it. Without this clause the next spelling is
    simply not examined, which is indistinguishable from absent. Both halves are driven: the
    line, and the count beside the verdict.
    """
    issues = [
        _issue_with_comments(7, "OPEN", "## DISPOSITION — a spelling nobody has used yet.\n"),
        _issue_with_comments(8, "OPEN", "## RULED — an ordinary ruling.\n"),
    ]
    # `ruling` #7 is added for #332: #7 carries no ACCEPTED head, so it is the probe's own
    # point that it reads unruled — but the ROUND's population is read from the LEDGER, and
    # a row exists for it, so the patrol's board-unruled leg stays quiet here.
    rows = _rows(("intake", "#7", 1), ("ruling", "#7", 4), ("intake", "#8", 2),
                 ("ruling", "#8", 3, f"probe comment={_comment_numeric(8)}"))
    leg = RUNNER.board_ruling_leg(issues, rows, read_at="probe",
                                  predicate=RUNNER.load_predicate(),
                                  scope=RUNNER.UNBOUNDED_SCOPE,
                                  exemptions_path=_NO_RULING_EXEMPTIONS)
    cov = leg["coverage"]
    assert cov["unmatched_heads"] == [{"issue": 7, "head": "## DISPOSITION — a spelling nobody has used yet."}], cov["unmatched_heads"]
    assert cov["unmatched_heads_examined"] == 1, cov
    assert cov["canonical_heading"] == "## RULED", cov

    rc, out, _ = _run(issues, rows)
    assert "## DISPOSITION — a spelling nobody has used yet." in out, out
    assert "#7" in out, out
    assert "heading comments the ruling predicate did NOT match: 1 over 1 issue(s)" in out, out
    assert "the convention names '## RULED'" in out, out
    assert rc == 0, out

def test_the_counter_counts_ISSUES_not_COMMENTS() -> None:
    """#274: the counter's NAME and its PREDICATE are one fact, so they are gated together.

    The defect this pins was measured on the live board: three `## RULED` comments posted in
    ONE turn (#75/#227/#263) moved the counter from 79 to 81, because the leg increments once
    per ISSUE carrying an accepted heading and #75 already carried one. A reader comparing two
    runs expected +3 and went hunting for an unplaced comment that does not exist.

    The name moved to match the predicate (`ruling_comments_examined` -> `rulings_issued`) and
    the predicate STAYED per-issue. This probe is what keeps it that way: two ruling comments
    on ONE issue, and a second issue with none, must read as ONE. If the increment ever moves
    to per-comment the count reads 2 and this reds — which is the only thing that stops a
    renamed counter from drifting back under a name that no longer describes it.
    """
    issues = [
        # ONE issue, TWO ruling comments — the measured shape.
        _issue_with_comments(75, "OPEN", "## RULED — the ruling.\n", "## RULED — amended.\n"),
        _issue_with_comments(76, "OPEN", "no ruling here, only prose.\n"),
    ]
    # `ruling` #76 is added for #332: #76 carries no ruling COMMENT (which is this probe's
    # point), but the round's population is read from the LEDGER, so a row keeps the
    # board-unruled leg quiet over a fixture that is about the ruling leg.
    # #75 carries TWO ruling comments and the leg judges the LATEST act (#511), so the row
    # must name the SECOND one; #76 carries no accepted head at all, so no pairing is owed.
    rows = _rows(("intake", "#75", 1),
                 ("ruling", "#75", 2, f"probe comment={_comment_numeric(75, 2)}"),
                 ("intake", "#76", 3), ("ruling", "#76", 4))
    leg = RUNNER.board_ruling_leg(issues, rows, read_at="probe", predicate=RUNNER.load_predicate(),
                                  scope=RUNNER.UNBOUNDED_SCOPE,
                                  exemptions_path=_NO_RULING_EXEMPTIONS)
    assert leg["coverage"]["rulings_issued"] == 1, (
        f"two ruling comments on ONE issue are ONE ruling: {leg['coverage']!r}"
    )
    assert leg["problems"] == [], leg["problems"]

    rc, out, _ = _run(issues, rows)
    section = out.split("LEG board-ruling")[1].split("LEG ")[0]
    assert "1 examined over 2 issue(s) read" in section, (
        f"the printed count and the read size must both travel: {section!r}"
    )
    assert rc == 0, out

def test_the_widening_MOVES_an_amendment_only_issue_INTO_the_population() -> None:
    """The NON-VACUITY control for the widening, driven through the REAL leg.

    An issue whose ONLY head is `## Amendment` and which has no `ruling` row was invisible
    before the widening: it was not counted as examined and not reported. The same fixture
    is driven through the accepted set as it stands and against the NARROWED tuple, so the
    difference is attributable to the widening and not to the fixture — the shape #243's
    bridge control used.
    """
    pred = RUNNER.load_predicate()
    issues = [_issue_with_comments(133, "OPEN", "## Amendment — the item is ruled here.\n")]
    rows = _rows(("intake", "#133", 846), ("dispatch", "#133", 847))

    widened = RUNNER.board_ruling_leg(issues, rows, read_at="probe", predicate=pred,
                                      scope=RUNNER.UNBOUNDED_SCOPE,
                                      exemptions_path=_NO_RULING_EXEMPTIONS)
    assert widened["coverage"]["rulings_issued"] == 1, widened["coverage"]
    assert len(widened["problems"]) == 1, widened["problems"]
    assert "#133 carries a ruling comment" in widened["problems"][0], widened["problems"]

    saved = RUNNER.RULING_HEADINGS
    RUNNER.RULING_HEADINGS = ("## RULED", "## RULING")
    try:
        narrowed = RUNNER.board_ruling_leg(issues, rows, read_at="probe", predicate=pred,
                                       scope=RUNNER.UNBOUNDED_SCOPE,
                                       exemptions_path=_NO_RULING_EXEMPTIONS)
    finally:
        RUNNER.RULING_HEADINGS = saved
    assert narrowed["coverage"]["rulings_issued"] == 0, narrowed["coverage"]
    assert narrowed["problems"] == [], narrowed["problems"]

# --- #334: the board-ruling leg's BOUND and its exemption surface ------------------
#
# The leg asserts that a ruling comment has its paired ledger `ruling` row. Until #334 it
# had no bound, so 12 pre-mechanism comments were PERMANENT problems, and no exemption
# surface, so its one post-mechanism instance had no lawful exit. Every instant below is
# derived from THIS tree's declaration through the same reader the leg uses — never the
# kit's literal — because this file ships byte-identical to its TEMPLATE twin and in that
# half "this factory" is the ADOPTING MEMBER (#78 clause b).

_RULING_BOUND = _tree_bound(RUNNER.RULING_BOUNDARY_KEY, "2026-10-02T18:07:38Z")
_RULING_PRE = _plus(_RULING_BOUND, -2.0)
_RULING_POST = _plus(_RULING_BOUND, 2.0)

def _scope_at(text: str) -> tuple:
    """A synthetic bound at `text`, in the tuple shape the leg consumes."""
    instant = dt.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    return (instant, text, "")

def _ruling_issue(number: int, created: str, *, body: str = "## RULED — a ruling.\n",
                  comment_id: str | None = None, state: str = "OPEN") -> dict:
    """A board issue carrying ONE ruling comment posted at `created`.

    `state` is a parameter because two different fixtures are needed. A leg-only probe uses
    OPEN; a probe driven through `main()` uses CLOSED, because an OPEN item carrying an
    `intake` row and no `ruling` row is the #332 board-unruled leg's own population, and a
    run that is red for THAT reason would make this file's assertions statements about
    another leg.
    """
    issue = _issue(number, state)
    issue["comments"] = [{
        "id": comment_id or f"IC_probe_{number}",
        "body": body,
        "author": {"login": "leshchenko1979"},
        "createdAt": created,
        "url": _comment_url(number),
    }]
    return issue

def _exemptions_file(tmp: str, *entries: dict) -> Path:
    """A throwaway exemption table, so no probe reads the live factory's own."""
    path = Path(tmp) / "ruling-board-exemptions.json"
    path.write_text(json.dumps({"_note": "probe", "exemptions": list(entries)}),
                    encoding="utf-8")
    return path

def _exemption(comment: str, issue: int, **over) -> dict:
    entry = {
        "comment": comment, "issue": issue, "created": _RULING_POST,
        "granted": "2026-10-05",
        "domain": RUNNER.RULING_EXEMPT_DOMAIN[0],
        "reason": "probe: NO BACKFILL bars the only repair",
        "proof": "probe: the comment exists and no `ruling` row names the issue",
    }
    entry.update(over)
    return entry

def test_the_ruling_bound_EXCUSES_a_pre_boundary_comment_and_JUDGES_a_post_boundary_one() -> None:
    """Acceptance (d), as a NON-VACUITY pair: one fixture, two instants, two verdicts.

    The leg's red must mean "a lane diverged since the mechanism", never "history exists".
    The same issue and the same ledger are driven twice with the ONLY difference the ruling
    comment's own `createdAt` — so the verdict is attributable to the bound and not to the
    fixture, which is the shape #243's bridge control used.
    """
    rows = _rows(("intake", "#1", 1))
    scope = _scope_at(_RULING_BOUND)

    pre = RUNNER.board_ruling_leg([_ruling_issue(1, _RULING_PRE)], rows, read_at="probe",
                                  scope=scope, exemptions_path=_NO_RULING_EXEMPTIONS)
    assert pre["problems"] == [], pre["problems"]
    # COUNTED, never dropped: a pre-boundary instance that vanished from the population
    # would be indistinguishable from one that was never on the board (#242).
    assert pre["coverage"]["rulings_issued"] == 1, pre["coverage"]
    assert pre["coverage"]["pre_boundary_rulings"] == 1, pre["coverage"]
    assert pre["coverage"]["bound"] == _RULING_BOUND, pre["coverage"]
    assert len(pre["excused"]) == 1, pre["excused"]
    assert "PREDATES the declared bound" in pre["excused"][0], pre["excused"]
    assert "NEVER backfilled" in pre["excused"][0], pre["excused"]

    post = RUNNER.board_ruling_leg([_ruling_issue(1, _RULING_POST)], rows, read_at="probe",
                                   scope=scope, exemptions_path=_NO_RULING_EXEMPTIONS)
    assert len(post["problems"]) == 1, post["problems"]
    assert "#1 carries a ruling comment" in post["problems"][0], post["problems"]
    assert "a lane that diverged from it" in post["problems"][0], post["problems"]
    assert post["coverage"]["pre_boundary_rulings"] == 0, post["coverage"]

def test_the_ruling_bound_reads_the_LATEST_accepted_comment_not_the_first() -> None:
    """The false-clean control for the instance's instant.

    An issue ruled BEFORE the mechanism and amended AFTER it carries two ruling acts. Dating
    the instance by the FIRST comment would excuse the post-mechanism amendment — a false
    clean, which is the worse half of the #248 class. The fixture is exactly that issue, and
    the assertion is that it is JUDGED.
    """
    issue = _issue(7, "OPEN")
    # `url` is NOT decoration: the pairing surface compares the NUMERIC id that only the URL
    # carries (#511). A fixture without it drives the fail-closed arm while reading as if it
    # drove the paired one, so this control is re-armed with the helper that supplies it.
    issue["comments"] = [
        {"id": "IC_pre", "body": "## RULED — the original.\n",
         "author": {"login": "leshchenko1979"}, "createdAt": _RULING_PRE,
         "url": _comment_url(7, 1)},
        {"id": "IC_post", "body": "## RULED — amended.\n",
         "author": {"login": "leshchenko1979"}, "createdAt": _RULING_POST,
         "url": _comment_url(7, 2)},
    ]
    leg = RUNNER.board_ruling_leg([issue], _rows(("intake", "#7", 1)), read_at="probe",
                                  scope=_scope_at(_RULING_BOUND),
                                  exemptions_path=_NO_RULING_EXEMPTIONS)
    assert len(leg["problems"]) == 1, leg["problems"]
    # The INSTANT is the amendment's and the COMMENT named is the amendment's. Reading the
    # first comment would print the pre-boundary instant, excuse the instance, and report a
    # clean leg — so the negative assertion on `_RULING_PRE` is the control, not decoration.
    assert _RULING_POST in leg["problems"][0], leg["problems"]
    assert f"comment {_comment_numeric(7, 2)}" in leg["problems"][0], leg["problems"]
    assert _RULING_PRE not in leg["problems"][0], leg["problems"]
    assert leg["excused"] == [], leg["excused"]
    assert leg["coverage"]["pre_boundary_rulings"] == 0, leg["coverage"]

def test_the_ruling_leg_REFUSES_rather_than_judging_UNBOUNDED() -> None:
    """An unreadable bound is neither a skip nor a pass — and it is not the old behaviour.

    A REFUSAL must judge NOTHING: judging every instance against no bound is exactly the
    permanent red #334 removes, and silently returning to it is the failure mode this arm
    pins. The population is still counted, so a refused run cannot read as an empty board.
    """
    refusal = "`ruling_writer_landed` is UNDECLARED — REFUSED: probe"
    leg = RUNNER.board_ruling_leg([_ruling_issue(1, _RULING_POST)], _rows(("intake", "#1", 1)),
                                  read_at="probe", scope=(None, "", refusal),
                                  exemptions_path=_NO_RULING_EXEMPTIONS)
    assert leg["problems"] == [refusal], leg["problems"]
    assert leg["coverage"]["rulings_issued"] == 1, leg["coverage"]
    assert leg["coverage"]["bound_refusal"] == refusal, leg["coverage"]
    assert leg["excused"] == [], leg["excused"]

    rc, out, _ = _run([_ruling_issue(1, _RULING_POST, state="CLOSED")],
                      _rows(("intake", "#1", 1), ("close", "#1", 2)),
                      ruling_scope=(None, "", refusal))
    assert rc == 1, (rc, out[-2000:])
    assert "NOT JUDGED, the bound is refused" in out, out[-3000:]

def test_the_ruling_bound_is_FACTORY_DATA_read_through_the_ONE_reader() -> None:
    """The instant is declared factory data, never a second constant in a shipped file.

    The runner is paired byte-identically with its TEMPLATE copy, so a date written inside it
    would judge a member tree against this factory's history — the same reason the
    boundary-reading gates declare theirs. The grep is the whole probe: no instant of the
    bound may appear in the runner, and the key must resolve through `tests/ledger_boundary.py`.
    """
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "2026-10-02T18:07:38" not in source, (
        "the bound instant is hardcoded in the leg; it belongs in docs/ledger-invariants.json")
    assert RUNNER.RULING_BOUNDARY_KEY == "ruling_writer_landed", source
    reader = RUNNER.load_module("ledger_boundary", RUNNER.LEDGER_BOUNDARY)
    try:
        _instant, text = reader.declared_boundary(REPO, RUNNER.RULING_BOUNDARY_KEY)
    except reader.SkipGate as exc:
        _declared_skip("the bound is factory data", str(exc))
        return
    except reader.GateError as exc:
        raise AssertionError(f"the boundary declaration is unreadable: {exc}") from exc
    assert text == _RULING_BOUND, f"the probes and the live declaration disagree: {text}"

def test_the_leg_PRINTS_the_bound_and_the_pre_boundary_count() -> None:
    """A bound that never reaches the report is a bound nobody can audit.

    Driven through `main()`, because the print is the property — an exclusion that is not
    printed cannot be told from a miss.
    """
    issues = [_ruling_issue(1, _RULING_PRE, state="CLOSED")]
    rows = _rows(("intake", "#1", 1), ("close", "#1", 2))
    rc, out, err = _run(issues, rows, ruling_scope=_scope_at(_RULING_BOUND))
    section = out.split("LEG board-ruling")[1].split("LEG ")[0]
    assert rc == 0, (rc, section, err)
    assert f"bound: {_RULING_BOUND} for `ruling_writer_landed`" in section, section
    assert "1 ruling comment(s) earlier than it are NOT JUDGED" in section, section
    assert "excused: 1" in section, section
    assert "PREDATES the declared bound" in section, section

def test_an_exemption_EXCUSES_a_post_boundary_instance_and_is_PRINTED() -> None:
    """The one lawful exit, and it is a VISIBLE debt rather than forgiveness.

    The instance is post-boundary, so the bound cannot excuse it; the exemption table can,
    and the run must say so on the same line it would otherwise carry the problem.
    """
    with tempfile.TemporaryDirectory() as tmp:
        issues = [_ruling_issue(282, _RULING_POST, comment_id="IC_probe_282",
                                state="CLOSED")]
        rows = _rows(("intake", "#282", 1), ("close", "#282", 2))
        path = _exemptions_file(tmp, _exemption("IC_probe_282", 282))

        leg = RUNNER.board_ruling_leg(issues, rows, read_at="probe",
                                      scope=_scope_at(_RULING_BOUND), exemptions_path=path)
        assert leg["problems"] == [], leg["problems"]
        assert leg["coverage"]["exemptions_declared"] == 1, leg["coverage"]
        assert leg["coverage"]["exemptions_matched"] == ["IC_probe_282"], leg["coverage"]
        assert len(leg["excused"]) == 1 and "EXEMPTED" in leg["excused"][0], leg["excused"]
        assert "NO BACKFILL bars the only repair" in leg["excused"][0], leg["excused"]

        rc, out, _ = _run(issues, rows, ruling_scope=_scope_at(_RULING_BOUND),
                          ruling_exemptions_path=path)
        section = out.split("LEG board-ruling")[1].split("LEG ")[0]
        assert rc == 0, (rc, section)
        assert "exemptions (ruling-board-exemptions.json): 1 declared, 1 matched" in section, section
        assert "EXEMPTED" in section, section

def test_an_exemption_is_KEYED_on_the_comment_so_a_new_ruling_cannot_inherit_it() -> None:
    """The key's whole point, as a NON-VACUITY control.

    A ruling is a COMMENT. Exempting by issue number would let a FUTURE ruling on the same
    issue inherit a grant made for a different act — the exact defect class this repo keeps
    filing. Here the table names the comment, and the board carries a DIFFERENT one on the
    same issue: the instance is judged, and the unmatched entry is reported as stale debt.
    """
    with tempfile.TemporaryDirectory() as tmp:
        issues = [_ruling_issue(282, _RULING_POST, comment_id="IC_probe_NEW")]
        rows = _rows(("intake", "#282", 1))
        path = _exemptions_file(tmp, _exemption("IC_probe_OLD", 282))

        leg = RUNNER.board_ruling_leg(issues, rows, read_at="probe",
                                      scope=_scope_at(_RULING_BOUND), exemptions_path=path)
        assert len(leg["problems"]) == 2, leg["problems"]
        assert any("#282 carries a ruling comment" in p for p in leg["problems"]), leg["problems"]
        assert any("matches NO in-scope unruled ruling comment" in p for p in leg["problems"]), (
            leg["problems"])
        assert leg["excused"] == [], leg["excused"]

def test_a_MALFORMED_exemption_is_a_PROBLEM_never_a_silent_pass() -> None:
    """Every malformed shape is reported: an entry that quietly fails to load is
    indistinguishable from no exemptions, which is the vacuous-pass shape this leg exists
    to catch."""
    cases = {
        "no comment key": {"issue": 1, "granted": "2026-10-05",
                           "domain": RUNNER.RULING_EXEMPT_DOMAIN[0], "reason": "r", "proof": "p"},
        "no reason": {"comment": "IC_x", "issue": 1, "granted": "2026-10-05",
                      "domain": RUNNER.RULING_EXEMPT_DOMAIN[0], "proof": "p"},
        "no proof": {"comment": "IC_x", "issue": 1, "granted": "2026-10-05",
                     "domain": RUNNER.RULING_EXEMPT_DOMAIN[0], "reason": "r"},
        "no issue": {"comment": "IC_x", "granted": "2026-10-05",
                     "domain": RUNNER.RULING_EXEMPT_DOMAIN[0], "reason": "r", "proof": "p"},
        "foreign domain": {"comment": "IC_x", "issue": 1, "granted": "2026-10-05",
                           "domain": "something else", "reason": "r", "proof": "p"},
    }
    for label, entry in cases.items():
        with tempfile.TemporaryDirectory() as tmp:
            path = _exemptions_file(tmp, entry)
            leg = RUNNER.board_ruling_leg([_ruling_issue(1, _RULING_POST)],
                                          _rows(("intake", "#1", 1)), read_at="probe",
                                          scope=_scope_at(_RULING_BOUND), exemptions_path=path)
            assert leg["coverage"]["exemptions_declared"] == 0, (label, leg["coverage"])
            assert leg["problems"], f"{label}: a malformed entry must be a problem"
            assert any("ruling-board-exemptions.json" in p for p in leg["problems"]), (
                label, leg["problems"])
            assert leg["excused"] == [], (label, leg["excused"])

    with tempfile.TemporaryDirectory() as tmp:
        broken = Path(tmp) / "ruling-board-exemptions.json"
        broken.write_text("not json {{{", encoding="utf-8")
        leg = RUNNER.board_ruling_leg([_ruling_issue(1, _RULING_POST)],
                                      _rows(("intake", "#1", 1)), read_at="probe",
                                      scope=_scope_at(_RULING_BOUND), exemptions_path=broken)
        assert any("unreadable or malformed JSON" in p for p in leg["problems"]), leg["problems"]

def test_an_absent_exemption_table_means_NO_exemptions_and_is_not_a_problem() -> None:
    """A new factory ships no table at all, and that is a legitimate state, not a defect.

    The counterpart to the malformed arm: absent means empty, and the leg still judges the
    population. Without this arm a leg that reported a missing file would red every factory
    that has never needed one.
    """
    leg = RUNNER.board_ruling_leg([_ruling_issue(1, _RULING_POST)], _rows(("intake", "#1", 1)),
                                  read_at="probe", scope=_scope_at(_RULING_BOUND),
                                  exemptions_path=_NO_RULING_EXEMPTIONS)
    assert leg["coverage"]["exemptions_declared"] == 0, leg["coverage"]
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "#1 carries a ruling comment" in leg["problems"][0], leg["problems"]

# --- #220: the worktree leg — the object class the cleanliness instrument excludes ---

def _wt_records(*paths: str) -> list[dict]:
    return [{"path": p} for p in paths]

def _wt_dirs(count: int) -> tuple[tempfile.TemporaryDirectory, list[str]]:
    """Real directories for the census fixture.

    The leg classifies a record whose directory is GONE as a missing registration — that
    is `git worktree prune`'s class and the reason the missing-directory list exists — so a
    fixture built from invented paths would be measuring that branch instead of the hazard
    branches under test. Directories are created rather than mocked for that reason.
    """
    tmp = tempfile.TemporaryDirectory()
    paths = []
    for index in range(count):
        path = Path(tmp.name) / f"wt{index}"
        path.mkdir()
        paths.append(str(path))
    return tmp, paths

def test_the_worktree_leg_NAMES_both_hazard_classes_with_their_paths() -> None:
    """#220 clause 3: the two hazard classes, WITH THE PATHS.

    A count without the paths sends the reader to `git worktree list` to find what the leg
    already knew, which is the shape that makes a report decorative. Both classes are
    driven here, and the population is asserted too — `scratch` is the complement of the
    FIRST record, because the first record is the tree the command was run from.
    """
    tmp2, dirs = _wt_dirs(4)
    main, a, b, c = dirs
    with tmp2:
        records = _wt_records(main, a, b, c)
        states = {
            main: {"dirty": [], "ahead": 0, "problems": []},
            a: {"dirty": [" M x"], "ahead": 0, "problems": []},
            b: {"dirty": [], "ahead": 3, "problems": []},
            c: {"dirty": [], "ahead": 0, "problems": []},
        }
        leg = RUNNER.worktree_leg(
            read_at="probe",
            records_fn=lambda repo=None: (records, None),
            state_fn=lambda path, **kw: states[path],
        )
        cov = leg["coverage"]
        assert leg["status"] == "ASSERTED", leg
        assert cov["worktrees_total"] == 4, cov
        assert cov["worktrees_scratch"] == 3, cov
        assert cov["missing_directory"] == [], cov
        assert cov["unreachable_commits"] == [{"path": b, "ahead": 3}], cov
        assert cov["uncommitted_work"] == [{"path": a, "paths": 1}], cov
    assert cov["hazard_classes"] == ["unreachable-commit", "uncommitted-work"], cov
    assert cov["base_ref"] == "origin/main", cov
    assert cov["instrument"] == "git worktree list --porcelain / git worktree prune", cov

def test_the_worktree_leg_REPORTS_and_never_removes() -> None:
    """The refusal, asserted STRUCTURALLY rather than promised in prose.

    The ruling refused widening the cleanliness instrument's glob because hygiene's remedy
    is REMOVAL, and removal on a worktree holding uncommitted work destroys it. So this leg
    must hold no mutating path at all — and a promise in a docstring is not a mechanism.
    The module's own source is scanned for every form that would remove or mutate a
    worktree, and the leg declares `removes: False` so a reader of the REPORT is told the
    same thing the code says.
    """
    source = (RUNNER.REPO / "tools" / "patrol_host_state.py").read_text(encoding="utf-8")
    forbidden = ("worktree", "prune"), ("worktree", "remove"), ("shutil.rmtree",),
    for needle in ("prune", "remove"):
        assert f'"worktree", "{needle}"' not in source, f"a worktree {needle} call is present"
    assert "shutil.rmtree" not in source, "an rmtree is present in the runner"
    del forbidden

    tmp, (main, scratch) = _wt_dirs(2)
    with tmp:
        leg = RUNNER.worktree_leg(
            read_at="probe",
            records_fn=lambda repo=None: (_wt_records(main, scratch), None),
            state_fn=lambda path, **kw: {"dirty": [], "ahead": 0, "problems": []},
        )
    assert leg["coverage"]["removes"] is False, leg["coverage"]

def test_the_worktree_leg_is_NOT_RUN_when_the_census_cannot_be_read() -> None:
    """An unreadable census is not an empty one, and an empty one is not a clean one.

    Both arms: the instrument failing (an error from `git worktree list`), and the
    instrument returning NO records — which a repository can never legitimately do, since
    it always carries at least its main worktree. Each must state its reason rather than
    render as a clean verdict.
    """
    failed = RUNNER.worktree_leg(
        read_at="probe",
        records_fn=lambda repo=None: ([], "`git worktree list` could not run: boom"),
        state_fn=lambda path, **kw: {"dirty": [], "ahead": 0, "problems": []},
    )
    assert failed["status"] == "NOT RUN", failed
    assert "could not be read" in failed["coverage"]["reason"], failed["coverage"]

    empty = RUNNER.worktree_leg(
        read_at="probe",
        records_fn=lambda repo=None: ([], None),
        state_fn=lambda path, **kw: {"dirty": [], "ahead": 0, "problems": []},
    )
    assert empty["status"] == "NOT RUN", empty
    assert "at least its main worktree" in empty["coverage"]["reason"], empty["coverage"]

def test_a_NOT_RUN_worktree_leg_RENDERS_its_reason_never_a_clean_verdict() -> None:
    """The render branch, driven separately: NOT RUN must carry its reason.

    Without this arm a NOT RUN leg could render as an empty block, and an unreadable
    census would then be indistinguishable from a clean one in the only surface a reader
    actually meets -- the report.
    """
    def _stub(*, read_at: str, **_kw) -> dict:
        return {
            "name": "worktree", "status": "NOT RUN", "problems": [], "excused": [],
            "coverage": {"reason": "the worktree census could not be read — probe",
                         "read_at": read_at},
        }

    issues = [_issue(1, "OPEN")]
    # The `ruling` row keeps this fixture inside the round's own population (#332), so the
    # only NOT RUN under test is the worktree leg's.
    rows = _rows(("intake", "#1", 1), ("ruling", "#1", 2))
    out, err = io.StringIO(), io.StringIO()
    rc = RUNNER.main(
        [], board_fn=lambda slug: issues, slug_fn=lambda: "owner/repo",
        rows_fn=lambda: rows, cron_rows_fn=lambda: ([], ["probe-home"], []),
        cron_fires_fn=lambda: [],
        prefixes_fn=lambda: [], log_dir=_EMPTY_LOG_DIR,
        scores_dir_fn=lambda: _EMPTY_SCORES_DIR,
        kit_manifest=_probe_kit_pair()[0], fleet_manifest=_probe_kit_pair()[1],
        out=lambda *a, **k: print(*a, file=out, **k),
        err=lambda *a, **k: print(*a, file=err, **k),
        publish_fn=_stub_publish_leg, worktree_fn=_stub,
        shared_tree_fn=_stub_shared_tree_rider,
        # #133: the driverless-lane leg's goal store and its turn-in-flight read are
        # injected here for the same reason every other live surface is -- and the
        # defaults WITHHOLD the driven claim (empty store, no turn open) rather than
        # granting one, so a probe that never asserts a driver cannot read one.
        driverless_goals_fn=lambda: _EMPTY_GOAL_STORE,
        driverless_turn_open_fn=lambda: {},
        # #330: the ref-role store is injected for the same reason the ruling table is.
        ref_role_exemptions_path=_NO_REF_ROLE_EXEMPTIONS,
        # #507: the criterion-path store, injected for the same reason.
        criterion_exemptions_fn=lambda: _NO_CRITERION_EXEMPTIONS,
        ruling_scope_fn=lambda: RUNNER.UNBOUNDED_SCOPE,
        ruling_exemptions_path=_NO_RULING_EXEMPTIONS,
    )
    text = out.getvalue()
    assert rc == 0, text
    assert "LEG worktree — NOT RUN" in text, text
    assert "NOT RUN: the worktree census could not be read — probe" in text, text
    assert "worktrees: " not in text, text

def test_the_worktree_leg_is_the_thing_that_moves_the_report() -> None:
    """The NON-VACUITY control: the same fixture with and without a hazard.

    One fixture, driven twice — once with a tree ahead of the base and once with none — so
    the difference is attributable to the hazard and not to the fixture. Without this arm
    a leg that always printed empty lists would satisfy every assertion above.
    """
    tmp, (main, scratch) = _wt_dirs(2)
    hazard = {"dirty": [" M x"], "ahead": 2, "problems": []}
    clean = {"dirty": [], "ahead": 0, "problems": []}
    with tmp:
        records = _wt_records(main, scratch)
        with_hazard = RUNNER.worktree_leg(
            read_at="probe", records_fn=lambda repo=None: (records, None),
            state_fn=lambda path, **kw: hazard if path == scratch else clean,
        )
        without = RUNNER.worktree_leg(
            read_at="probe", records_fn=lambda repo=None: (records, None),
            state_fn=lambda path, **kw: clean,
        )
    assert len(with_hazard["coverage"]["unreachable_commits"]) == 1, with_hazard["coverage"]
    assert len(with_hazard["coverage"]["uncommitted_work"]) == 1, with_hazard["coverage"]
    assert without["coverage"]["unreachable_commits"] == [], without["coverage"]
    assert without["coverage"]["uncommitted_work"] == [], without["coverage"]

def test_the_whole_run_PRINTS_the_worktree_population_and_never_a_bare_zero() -> None:
    """The clause that keeps a clean run from being read as "no residue".

    Driven through the REAL `main()`, so the render path is exercised rather than the leg
    alone — the leg returning a correct dict and the report dropping it is exactly the
    half-fix this probes for. The figures are asserted WITH their predicate: the population,
    both hazard classes, the `removes: no` declaration, and the read instant.
    """
    issues = [_issue(1, "OPEN")]
    # `ruling` #1 keeps this fixture inside the round's own population (#332); without it
    # the board-unruled leg REDs and this probe would pass while measuring a red run.
    rows = _rows(("intake", "#1", 1), ("ruling", "#1", 2))
    rc, out, _ = _run(issues, rows)
    assert "LEG worktree — ASSERTED" in out, out
    assert "worktrees: 2 total, 1 scratch" in out, out
    assert "the cleanliness instrument's glob cannot reach" in out, out
    assert "removes: no" in out, out
    assert "unreachable-commit (commits not reachable from origin/main): 1 tree(s)" in out, out
    assert "~ /probe/scratch — 1 commit(s) ahead" in out, out
    assert "uncommitted-work (paths differing from HEAD): 1 tree(s)" in out, out
    assert "~ /probe/scratch — 2 path(s)" in out, out
    assert "read at " in out, out

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

def test_the_stall_census_leg_BITES_and_discriminates_on_every_neighbour() -> None:
    """#260 acceptance (1), the NON-VACUITY probe: the leg must NAME a never-claimed
    dispatch past its threshold, and must NOT name the four neighbours that look like one.

    The discriminating pairs are the whole point, because the naive predicate the ruling
    was written from -- "the latest dispatch row with no later claim row" -- reports every
    one of them. Measured on this ledger 2026-10-03, that literal form reports 36 units
    where the true population is 20: the extras are claimed-then-RE-DISPATCHED
    (`#132` intake n=836, claim n=837, dispatch n=838, close n=840; `#235` claim n=1674,
    close n=1675, dispatch n=1681) and closed-without-claim. So each of these four is a
    live false positive the leg must keep out, and a probe that supplied only the true
    positive would pass a leg that reported all five.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [
        _issue(901, "OPEN"),    # dispatched 3 d ago, NEVER claimed -> OWED
        _issue(902, "OPEN"),    # dispatched seconds ago -> in flight, below threshold
        _issue(903, "OPEN"),    # dispatched, then CLAIMED -> not owed
        _issue(904, "OPEN"),    # dispatched, then CLOSED by a ledger close row
        _issue(905, "CLOSED"),  # never claimed, but the BOARD carries it closed
    ]
    rows = [
        _stall_row(1, "intake", "#901", 4, now=now),
        _stall_row(2, "dispatch", "#901", 3, now=now),
        _stall_row(3, "dispatch", "#902", 0.01, now=now),
        _stall_row(4, "dispatch", "#903", 5, now=now),
        _stall_row(5, "claim", "#903", 4.9, now=now),
        _stall_row(6, "dispatch", "#904", 6, now=now),
        _stall_row(7, "close", "#904", 5.9, now=now),
        _stall_row(8, "dispatch", "#905", 7, now=now),
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    assert "OWED #901" in named, f"the never-claimed dispatch must be NAMED\n{named}"
    for quiet in ("#902", "#903", "#904", "#905"):
        assert quiet not in named, (
            f"{quiet} must NOT be reported owed: a below-threshold dispatch is in flight, "
            f"a claimed one has a taker, a closed one is finished, and a board-closed item "
            f"owes no claim\n{named}"
        )
    assert leg["coverage"]["units_owed"] == 1, leg["coverage"]

    # ... and the same fixture through the REAL `main()`: the report must carry the OWED
    # line AND the population it was read from. A leg returning a correct dict while the
    # render drops it is the half-fix this half exists to catch.
    rc, out, _ = _run(issues, rows)
    assert rc == 1, f"an OWED line must fail the run, got rc={rc}\n{out}"
    assert "LEG stall-census — ASSERTED" in out, out
    assert "OWED #901" in out, out
    assert "population: 5 dispatched unit(s) -- 1 never claimed" in out, out
    assert "read at " in out, out

def test_the_stall_census_leg_PRINTS_the_tracker_assignee_and_still_reads_OWED() -> None:
    """#423: an assigned-but-unclaimed unit is VISIBLE as assigned, and is STILL OWED.

    TWO FACTS, and the second is what keeps the fix honest.

    (a) An OWED unit whose board issue carries an assignee must NAME that assignee on the
    OWED line. Before this the line rendered an assigned-but-unclaimed unit identically to
    one nobody had touched -- the visibility gap the item names.

    (b) The assignee must NOT clear the OWED verdict. An assignee is a tracker field, not a
    session-derived `claim` row, and reading it as a taker would let an assignment silence
    the andon cord. So the SAME fixture still reports the unit OWED, and the line says so
    in words.

    The discriminating pair is the point: the unassigned unit must NOT carry the assignee
    sentence, or a leg that printed a constant would satisfy (a) alone.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [
        _issue(921, "OPEN", ["leshchenko1979"]),  # assigned, still never claimed -> OWED
        _issue(922, "OPEN"),                       # untouched -> OWED, no assignee text
    ]
    rows = [
        _stall_row(1, "dispatch", "#921", 3, now=now),
        _stall_row(2, "dispatch", "#922", 3, now=now),
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    assert "OWED #921" in named, f"an assigned-but-unclaimed unit stays OWED\n{named}"
    assert "ASSIGNED to leshchenko1979" in named, (
        f"the tracker assignee must be PRINTED on the OWED line\n{named}"
    )
    assert "an assignee is not a ledger claim" in named, named
    assert leg["coverage"]["units_owed"] == 2, leg["coverage"]
    assert leg["coverage"]["units_owed_assigned"] == 1, leg["coverage"]

    # ... and the UNASSIGNED unit carries no assignee sentence: a leg that printed the
    # sentence unconditionally would pass every assertion above just as well.
    line_922 = [ln for ln in leg["problems"] if "#922" in ln]
    assert line_922 and "ASSIGNED to" not in line_922[0], (
        f"an unassigned unit must not read as assigned\n{line_922}"
    )

    # ... and the same fixture through the REAL `main()`: the assignee reaches the report.
    rc, out, _ = _run(issues, rows)
    assert rc == 1, f"an OWED line must fail the run, got rc={rc}\n{out}"
    assert "ASSIGNED to leshchenko1979" in out, out

def _park_row(n, unit, days_ago, token=None, *, now, mention=None):
    """A ledger row that DECLARES a park on `unit` (#331 clause 1).

    The token stands ALONE on the last line, which is the shape the live declarations use --
    Triage's rows n=2881/n=2882 carry `park:owner:q30` exactly so -- and the shape the reader
    requires. `mention` writes a sentence that QUOTES a token without declaring one, and
    `token` is left free-form so a probe can write the REFUSED forms as well as the accepted
    one: the live row that withdrew #301's park (n=2883) quotes two tokens mid-sentence and
    closes "THIS ROW CARRIES NO PARK TOKEN".
    """
    body = f"CENSUS DISPOSITION -- {unit} is PARKED AT THE OWNER DESIGN GATE.\n\n"
    if mention:
        body += f"{mention}\n\n"
    if token:
        body += token
    return _stall_row(n, "run", unit, days_ago, now=now, detail=body.rstrip())

def test_the_stall_census_leg_holds_a_DECLARED_PARK_out_of_the_owed_total() -> None:
    """#331 clause 1, two-sided: a unit whose OWN row declares `park:owner:<question>` reads
    PARKED, is not a finding, and leaves the owed total -- and the SAME rows with the
    declaration line removed still read OWED, so the park is measured as the thing that
    cleared it.

    The declaration is read off the ROWS rather than off a table this tree edits, and the live
    ledger is the reason: Triage's park rows for #317/#320 (n=2881/n=2882) carry the token as
    their last line and each says in as many words that "this row is the declared park HQ's C1
    defines". A table would never have seen them, so the live need would have gone unmet.

    The live need is #317/#320 -- and #301/#312/#313 on q39 -- units dispatched to a lane that
    lawfully cannot take them, parked on an owner question, re-reported as findings every day
    that question stays open.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(931, "OPEN"), _issue(932, "OPEN")]
    rows = [
        _stall_row(1, "dispatch", "#931", 5, now=now),
        _park_row(2, "#931", 4, "park:owner:q32", now=now),   # declared -> PARKED
        _stall_row(3, "dispatch", "#932", 5, now=now),        # undeclared -> stays OWED
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    assert "OWED #931" not in named, (
        f"a DECLARED park holds the line out of the OWED findings -- a parked line is not a "
        f"finding\n{named}"
    )
    parked = "\n".join(leg["coverage"]["parks"])
    assert "PARKED #931" in parked, leg["coverage"]["parks"]
    # The QUESTION and the DECLARING ROW both travel with the verdict: a park a reader cannot
    # trace to the row that declared it is a claim, not a declaration.
    assert "parked on q32" in parked and "row n=2" in parked, leg["coverage"]["parks"]
    assert "OWED #932" in named, (
        f"the undeclared neighbour must STILL be owed, or a leg that cleared the whole "
        f"population would satisfy the assertions above\n{named}"
    )
    cov = leg["coverage"]
    assert cov["units_owed"] == 1, cov
    assert cov["parks_declared"] == 1, cov
    assert cov["units_parked"] == 1, cov
    assert cov["units_park_superseded"] == 0, cov

    # THE TWO-SIDED HALF: the SAME fixture WITHOUT the declaring row reads #931 OWED, so the
    # park -- and nothing else -- is what moved it. A probe that asserted only the parked read
    # would pass a leg that reported nothing owed at all.
    bare_rows = [row for row in rows if row["n"] != 2]
    bare = RUNNER.stall_census_leg(issues, bare_rows, read_at=read_at)
    assert "OWED #931" in "\n".join(bare["problems"]), bare["problems"]
    assert bare["coverage"]["units_owed"] == 2, bare["coverage"]
    assert bare["coverage"]["units_parked"] == 0, bare["coverage"]
    assert bare["coverage"]["parks_declared"] == 0, bare["coverage"]

    # ... and the render half: the exclusion is PRINTED BESIDE THE VERDICT, so a reader who
    # sees an owed total smaller than the population can tell a declared park from a dropped
    # unit.
    rc, out, _ = _run(issues, rows)
    assert rc == 1, f"the undeclared neighbour is still OWED, got rc={rc}\n{out}"
    assert "1 declared, 1 OWED unit(s) held PARKED and EXCLUDED from the owed total" in out, out
    assert "PARKED #931" in out, out
    assert "not a finding" in out, out

def test_the_stall_census_leg_reads_a_park_ONLY_from_a_standalone_token() -> None:
    """#331 clause 1, the READ discipline, two-sided: a declaration is a LINE OF ITS OWN, and
    a token quoted inside a sentence is a MENTION.

    This is not a hypothetical. The row that WITHDREW #301's park (n=2883) quotes
    `park:owner:q30` and `park:owner:q39` mid-sentence while carrying no token of its own, and
    closes "THIS ROW CARRIES NO PARK TOKEN". A reader that matched the substring would park
    #301 on the very mis-citation that row exists to withdraw -- the false positive would be
    the exact defect the correction was written to repair.

    The four units below are discriminated by SHAPE ALONE, and the last one is the control
    that keeps this from being a blanket refusal: the mention and the two refused forms stay
    OWED with a PROBLEM naming them, the standalone `park:owner:qN` is the only one that
    holds. HQ's C1 scope ruling (n=2884) fixes the shape at ONE -- the register is the only
    sanctioned blocked-on-you channel -- so the `memo:` form and a `<placeholder>` standing in
    for an id are refused loudly rather than silently parking nothing.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(n, "OPEN") for n in (951, 952, 953, 954)]
    rows = [
        _stall_row(1, "dispatch", "#951", 5, now=now),
        _park_row(2, "#951", 4, now=now,
                  mention="n=2878 declared park:owner:q30 for it; this row WITHDRAWS that as "
                          "a MIS-CITATION and CARRIES NO PARK TOKEN of its own"),
        _stall_row(3, "dispatch", "#952", 5, now=now),
        _park_row(4, "#952", 4, "park:owner:memo:#301", now=now),
        _stall_row(5, "dispatch", "#953", 5, now=now),
        _park_row(6, "#953", 4, "park:owner:<question>", now=now),
        _stall_row(7, "dispatch", "#954", 5, now=now),
        _park_row(8, "#954", 4, "park:owner:q39", now=now),
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    for quiet in ("#951", "#952", "#953"):
        assert f"OWED {quiet}" in named, (
            f"{quiet} must stay OWED: a mention is not a declaration, and a declaration in a "
            f"refused shape cannot be read as one\n{named}"
        )
    assert "OWED #954" not in named, (
        f"the standalone declaration is the CONTROL -- if it did not hold, the probe above "
        f"would pass a reader that parks nothing at all\n{named}"
    )
    # ... and the two refused shapes are PROBLEMS, each naming the row and the ONE lawful
    # shape: a declaration the census cannot see re-arms the very line it was written to hold.
    assert "cannot read" in named and "memo:#301" in named, named
    assert "park:owner:<question>" in named, named
    assert "row n=4" in named and "row n=6" in named, named

    cov = leg["coverage"]
    assert cov["units_owed"] == 3, cov
    assert cov["parks_declared"] == 1, cov
    assert cov["units_parked"] == 1, cov
    assert "PARKED #954" in "\n".join(cov["parks"]), cov["parks"]

    # A park declared for a unit the census does NOT report owed is PRINTED as a note, never
    # dropped: a declaration that matches no OWED line is indistinguishable from a declaration
    # aimed at the wrong subject, and it is the same silence the refusals above exist to stop.
    # The two arms below are the two REASONS a park matches no OWED line, and they read
    # differently because the reasons are different (#470).
    extra = rows + [
        # #955 has no dispatch row at all: no ROUTING ever handed it to a lane, so it was
        # never in the population and its declaration held nothing out. It reads PARKED --
        # not "matched NO OWED line", whose reasons all describe a unit that WAS routed.
        _park_row(9, "#955", 4, "park:owner:q39", now=now),
        # #956 WAS routed (a direct dispatch row) and the board carries it CLOSED, so it is
        # dropped from the census by the off-board filter: this is the "matched NO OWED line"
        # disposition, and it must keep a fixture of its own.
        _stall_row(10, "dispatch", "#956", 5, now=now),
        _park_row(11, "#956", 4, "park:owner:q40", now=now),
    ]
    leg2 = RUNNER.stall_census_leg(issues + [_issue(956, "CLOSED")], extra, read_at=read_at)
    notes = "\n".join(leg2["coverage"]["parks"])
    assert "#955" in notes and "PARKED #955" in notes, leg2["coverage"]["parks"]
    assert "#956" in notes and "matched NO OWED line" in notes, leg2["coverage"]["parks"]
    assert leg2["coverage"]["units_parked"] == 1, leg2["coverage"]

def test_the_stall_census_leg_SUPERSEDES_a_park_a_LATER_dispatch_lifted() -> None:
    """#331 clause 1, the STATE half: a park holds until a LATER dispatch puts the unit back
    in play, and the supersession is PRINTED rather than obeyed.

    Without this guard the clause would be a permanent gag rather than a state. The ledger
    keeps every park row forever, so a unit parked once and re-dispatched a week later would
    stay silently held out of the census for good -- and nothing in the report would say why.
    The two units below carry the SAME two rows in OPPOSITE order, which is the property under
    test: order alone decides whether the declaration still holds.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(961, "OPEN"), _issue(962, "OPEN")]
    rows = [
        # #961: parked FIRST, then re-dispatched -- the park is stale and the unit is OWED.
        _park_row(1, "#961", 5, "park:owner:q33", now=now),
        _stall_row(2, "dispatch", "#961", 4, now=now),
        # #962: dispatched FIRST, parked after -- the declaration is the newest act.
        _stall_row(3, "dispatch", "#962", 5, now=now),
        _park_row(4, "#962", 4, "park:owner:q33", now=now),
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    assert "OWED #961" in named, (
        f"a dispatch NEWER than the park puts the unit back in play\n{named}"
    )
    assert "OWED #962" not in named, named
    notes = "\n".join(leg["coverage"]["parks"])
    assert "PARKED #962" in notes, leg["coverage"]["parks"]
    assert "#961" in notes and "SUPERSEDED" in notes, (
        f"the stale declaration is PRINTED, not merely obeyed: a reader must be able to see "
        f"that a park was declared and then lifted\n{notes}"
    )
    assert "row n=2" in notes and "row n=1" in notes, notes
    cov = leg["coverage"]
    assert cov["units_owed"] == 1, cov
    assert cov["units_parked"] == 1, cov
    assert cov["parks_declared"] == 2, cov
    assert cov["units_park_superseded"] == 1, cov

def test_a_BODY_MENTION_neither_ADMITS_a_unit_nor_SUPERSEDES_its_park() -> None:
    """#470, the routing split measured on ONE population, three arms.

    THE DEFECT. Ledger `n=3098` is a Triage escalation whose subject is a descriptive stem
    and whose BODY names `#460` and `#313`. Read permissively, those two tokens were admitted
    to the census population, DATED off the escalation's own write stamp, and -- because that
    same row then counted as their newest "dispatch" -- printed as parks SUPERSEDED. Two units
    nobody had ever dispatched therefore read OWED, and the census totalled 11 where it owed 9.

    THE SPLIT (#470). A row that names a unit only in its prose is a MENTION: it still counts
    in the harvest's coverage (#467 criterion 3, asserted below), but it may take no ROUTING
    slot -- not population admission, not the age, not park supersession.

    THE DISCRIMINATOR IS THE TOKEN'S POSITION, not the row's identity, and the arms below
    differ in that ALONE. `#971` is named only in a carrier's body, and its park HOLDS.
    `#972` is named in the SAME carrier's opening line, so it was ROUTED and its park is
    SUPERSEDED. `#973` is routed by a direct dispatch row and is superseded too. An
    implementation that refused every carrier row fails on `#972`; one that obeyed every
    carrier row fails on `#971` -- and the carrier is the NEWEST row in both cases, so the
    mention arm is a live supersession that must not happen rather than a row too old to act.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(n, "OPEN") for n in (971, 972, 973)]
    rows = [
        # #971: parked, then named only in a carrier's BODY -- the park must HOLD.
        _stall_row(1, "intake", "#971", 6, now=now),
        _park_row(2, "#971", 5, "park:owner:q40", now=now),
        # #972: parked, then named in the carrier's OPENING LINE -- ROUTED, so SUPERSEDED.
        _stall_row(3, "intake", "#972", 6, now=now),
        _park_row(4, "#972", 5, "park:owner:q41", now=now),
        # #973: parked, then re-dispatched by a direct row -- SUPERSEDED, the #331 control.
        _stall_row(5, "intake", "#973", 6, now=now),
        _park_row(6, "#973", 5, "park:owner:q42", now=now),
        _stall_row(7, "dispatch", "#973", 2, now=now),
        # THE CARRIER, and the newest row in the population: a descriptive stem that ROUTES
        # #972 in its opening line and only TALKS about #971 further down (the `n=3098` shape).
        _stall_row(8, "dispatch", "stall-census-escalation-probe", 3, now=now,
                   detail="TRIAGE ESCALATION -> the HQ lane: this row ROUTES #972.\n\n"
                          "Its body then talks about #971, and hands it to nobody."),
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    assert "OWED #971" not in named, (
        f"a token named only in a carrier's BODY is a MENTION, so it neither enters the "
        f"population nor starts the clock on the unit's age\n{named}"
    )
    assert "OWED #972" in named, (
        f"the POSITIVE arm: a token in the carrier's OPENING LINE was ROUTED, so the park it "
        f"supersedes is lifted\n{named}"
    )
    assert "OWED #973" in named, named

    parks = "\n".join(leg["coverage"]["parks"])
    assert "PARKED #971" in parks, (
        f"#971's declaration is RIGHT and the routing is simply absent, so it reads PARKED "
        f"rather than being accused of naming the wrong subject\n{parks}"
    )
    assert "SUPERSEDED" in parks and "#972" in parks and "#973" in parks, parks

    cov = leg["coverage"]
    assert cov["units_owed"] == 2, cov
    assert cov["units_park_superseded"] == 2, cov
    assert cov["parks_declared"] == 3, cov
    # NOT counted among the OWED units a park held out: #971 was never in the population, so
    # the census never owed it a line and the declaration held nothing out.
    assert cov["units_parked"] == 0, cov
    # COVERAGE IS UNCHANGED (#467 criterion 3): the mention is still CARRIED by the harvest
    # and still counted as a mention. The split narrows the ROUTING slot, never the coverage.
    assert cov["carried_units_resolved"] == 2, cov
    assert cov["mentions_rejected"] == 1, cov
    # AND THE TWO POPULATIONS ARE PRINTED SIDE BY SIDE (#470): what a dispatch ROUTED, and
    # what the harvest saw and refused the population slot -- a narrowed read that hides what
    # it dropped is the failure this leg exists to catch.
    assert cov["units_in_population"] == 2, cov
    assert cov["units_named_only_as_mentions"] == 1, cov

def _disposition_row(n, unit, days_ago, token=None, *, now, mention=None):
    """A ledger row that DECLARES a disposition on `unit` (#473).

    The token stands ALONE on the last line, which is the shape a ruling uses and the shape
    the reader requires. `mention` writes a sentence that QUOTES a token without declaring
    one -- the `n=2883` lesson, which withdrew a park on exactly those terms -- and `token`
    is left free-form so a probe can write the REFUSED forms as well as the accepted one.
    """
    body = f"RULING -- {unit} is DISPOSED OF.\n\n"
    if mention:
        body += f"{mention}\n\n"
    if token:
        body += token
    return _stall_row(n, "ruling", unit, days_ago, now=now, detail=body.rstrip())


def test_the_stall_census_leg_holds_a_RULED_VOID_unit_out_of_the_owed_total() -> None:
    """#473 acceptance, the whole point: a unit a RULING disposed of stops reading OWED even
    though its board item is still OPEN, and the declaring row travels with the verdict.

    THE MEASURED FAILURE THIS ANSWERS. `#453`: intake n=3032, dispatch n=3033, ruled
    "UNSUBSTANTIATED -- not-a-defect ... dispatch at n=3033 is void" at n=3041. The board item
    stayed OPEN, so the census kept printing `OWED #453`, and a Worker lane claimed it at
    n=3202, built a 266-probe arm for a defect ruled non-existent, withdrew it (8dc9a206) and
    closed the unit `outcome=abandoned` at n=3203. The ruling was loud; nothing could read it.

    TWO-SIDED, because a one-sided probe would pass a leg that voids everything: `#981`
    carries the declaration and leaves the owed total, `#982` carries none and stays OWED.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(981, "OPEN"), _issue(982, "OPEN")]
    rows = [
        _stall_row(1, "dispatch", "#981", 5, now=now),
        _disposition_row(2, "#981", 4, "disposition:void", now=now),
        _stall_row(3, "dispatch", "#982", 5, now=now),
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    assert "OWED #981" not in named, (
        f"a unit a RULING disposed of is not a finding, and its board item being OPEN is "
        f"exactly the state #473 exists to read\n{named}"
    )
    assert "OWED #982" in named, (
        f"the CONTROL: an undeclared unit must stay OWED, or the probe above would pass a "
        f"census that voids everything\n{named}"
    )
    voided = "\n".join(leg["coverage"]["dispositions"])
    assert "VOID #981" in voided, leg["coverage"]["dispositions"]
    # THE DECLARING ROW TRAVELS WITH THE VERDICT: a disposition no reader can trace to a row
    # is a claim, not a declaration -- and the row is what lets a reader go and read the
    # ruling that decided it.
    assert "row n=2" in voided and "disposition:void" in voided, voided

    cov = leg["coverage"]
    assert cov["units_owed"] == 1, cov
    assert cov["dispositions_declared"] == 1, cov
    assert cov["units_voided"] == 1, cov
    assert cov["units_disposition_superseded"] == 0, cov

    # ... and the exclusion reaches the REPORT, not only the dict: a reader who sees an owed
    # total smaller than the dispatched population must be able to read WHY.
    rc, out, _ = _run(issues, rows)
    assert rc == 1, f"the control unit is OWED, so the run must fail, got rc={rc}\n{out}"
    assert "ruled VOID and EXCLUDED from the owed total" in out, out
    assert "dispositions (disposition:void on the unit's own rows): 1 declared, 1 OWED" in out, out


def test_the_stall_census_leg_reads_a_disposition_ONLY_from_a_standalone_token() -> None:
    """#473, the READ discipline, two-sided: a declaration is a LINE OF ITS OWN, a token
    quoted inside a sentence is a MENTION, and an unimplemented kind is a PROBLEM.

    The mention arm is not hypothetical -- it is the `n=2883` shape, the row that withdrew a
    park while quoting two park tokens mid-sentence. A reader matching the substring would
    dispose of a unit on a row that merely DISCUSSED disposing of it, which is a worse
    failure than the one #473 repairs: it would silently drop live work.

    The refused forms are PROBLEMS rather than silent passes: a factory that believes it
    disposed of a unit the census cannot see is back in the #453 state with the ruling
    present and unread.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(n, "OPEN") for n in (991, 992, 993, 994)]
    rows = [
        _stall_row(1, "dispatch", "#991", 5, now=now),
        _disposition_row(2, "#991", 4, now=now,
                         mention="n=3041 declared `disposition:void` for it; this row "
                                 "WITHDRAWS that and CARRIES NO DISPOSITION TOKEN"),
        _stall_row(3, "dispatch", "#992", 5, now=now),
        _disposition_row(4, "#992", 4, "disposition:", now=now),
        _stall_row(5, "dispatch", "#993", 5, now=now),
        _disposition_row(6, "#993", 4, "disposition:reopened", now=now),
        _stall_row(7, "dispatch", "#994", 5, now=now),
        _disposition_row(8, "#994", 4, "disposition:void", now=now),
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    for quiet in ("#991", "#992", "#993"):
        assert f"OWED {quiet}" in named, (
            f"{quiet} must stay OWED: a mention is not a declaration, and an unreadable "
            f"declaration cannot be obeyed\n{named}"
        )
    assert "OWED #994" not in named, (
        f"the standalone declaration is the CONTROL -- if it did not hold, the probe above "
        f"would pass a reader that voids nothing\n{named}"
    )
    assert "cannot read" in named, named
    assert "row n=4" in named and "row n=6" in named, named
    assert "disposition:reopened" in named, named

    cov = leg["coverage"]
    assert cov["units_owed"] == 3, cov
    assert cov["dispositions_declared"] == 1, cov
    assert cov["units_voided"] == 1, cov


def test_the_stall_census_leg_SUPERSEDES_a_void_a_LATER_dispatch_lifted() -> None:
    """#473 clause 3: a void holds until a LATER dispatch puts the unit back in play, and the
    supersession is PRINTED rather than obeyed.

    Without this the clause would be a permanent gag: the ledger keeps every ruling forever,
    so a unit ruled void and then RE-DISPATCHED would stay silently excluded for good and
    nothing in the report would say why. The two units carry the same two acts in OPPOSITE
    order, which is the property under test.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(995, "OPEN"), _issue(996, "OPEN")]
    rows = [
        # #995: ruled void FIRST, then re-dispatched -- the ruling is stale, the unit is OWED.
        _stall_row(1, "dispatch", "#995", 6, now=now),
        _disposition_row(2, "#995", 5, "disposition:void", now=now),
        _stall_row(3, "dispatch", "#995", 4, now=now),
        # #996: dispatched, then ruled void -- the ruling is the newest act.
        _stall_row(4, "dispatch", "#996", 6, now=now),
        _disposition_row(5, "#996", 4, "disposition:void", now=now),
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    assert "OWED #995" in named, (
        f"a dispatch NEWER than the ruling puts the unit back in play\n{named}"
    )
    assert "OWED #996" not in named, named
    notes = "\n".join(leg["coverage"]["dispositions"])
    assert "VOID #996" in notes, leg["coverage"]["dispositions"]
    assert "#995" in notes and "SUPERSEDED" in notes, (
        f"the stale ruling is PRINTED, not merely obeyed\n{notes}"
    )
    assert "row n=2" in notes and "row n=3" in notes, notes
    cov = leg["coverage"]
    assert cov["units_owed"] == 1, cov
    assert cov["units_voided"] == 1, cov
    assert cov["units_disposition_superseded"] == 1, cov


def test_a_DISPOSITION_that_matches_no_OWED_line_is_PRINTED_once() -> None:
    """#473 clause 4 + the #471 rule: a disposition the census cannot act on is PRINTED, and
    a unit carrying BOTH a park and a void is printed under ONE heading.

    Two arms. `#997` was never ROUTED (its token stands in a row's body), so it was never in
    the population -- the declaration STANDS and the note says the routing is absent rather
    than accusing the declaration of naming the wrong subject. `#998` WAS routed and the board
    carries it CLOSED, so it is dropped by the off-board filter: the "matched NO OWED line"
    arm. `#999` carries a park token AND a void token, and must read VOID alone -- one unit
    printed with two contradictory dispositions is the defect #471 reports.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(998, "CLOSED"), _issue(999, "OPEN")]
    rows = [
        _disposition_row(1, "#997", 4, "disposition:void", now=now),
        _stall_row(2, "dispatch", "#998", 5, now=now),
        _disposition_row(3, "#998", 4, "disposition:void", now=now),
        _stall_row(4, "dispatch", "#999", 5, now=now),
        _park_row(5, "#999", 4, "park:owner:q43", now=now),
        _disposition_row(6, "#999", 3, "disposition:void", now=now),
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    notes = "\n".join(leg["coverage"]["dispositions"])
    assert "VOID #997" in notes and "no dispatch ROUTED it" in notes, notes
    assert "#998" in notes and "matched NO OWED line" in notes, notes
    assert "VOID #999" in notes, notes
    parks = "\n".join(leg["coverage"]["parks"])
    assert "#999" not in parks, (
        f"a unit a ruling DISPOSED OF must not also print a park note -- the void decided "
        f"the census, and two dispositions on one unit is the #471 defect\n{parks}"
    )
    cov = leg["coverage"]
    assert cov["units_owed"] == 0, cov
    assert cov["units_voided"] == 1, cov
    assert cov["parks_declared"] == 1, cov
    assert cov["units_parked"] == 0, cov


def test_the_stall_census_leg_names_the_ADDRESSEE_and_never_the_AUTHOR() -> None:
    """#331 clause 2, two-sided: the OWED line names the LANE the dispatch was handed to, and
    a unit whose dispatch declares no target SAYS SO rather than printing the row's author.

    The defect this replaces: the line printed `actor={actor}` -- the author of the
    dispatch-bearing row, which for a census re-dispatch is whoever RAN the census, usually
    Triage, and never the lane the work belongs to -- directly beside the advice to
    "re-dispatch it to the lane that owns it". An author in that slot reads as an assignment,
    which is worse than an empty one.

    Three arms, each of which a wrong implementation fails. #941 is AUTHORED by `hq` and
    ADDRESSED to the Ledger lane by a typed `session` ref the resolver maps to `Ledger`, so a
    leg that printed the author fails. #942 declares a session the resolver does NOT know, and
    #943 declares no target at all -- so a leg that silently fell back to the author, or
    silently printed nothing, fails on those too.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    ledger_session = "11111111-2222-3333-4444-555555555555"
    issues = [_issue(941, "OPEN"), _issue(942, "OPEN"), _issue(943, "OPEN")]
    rows = [
        _stall_row(1, "dispatch", "#941", 5, now=now, actor="hq",
                   refs=[{"session": ledger_session}]),
        _stall_row(2, "dispatch", "#942", 5, now=now, actor="hq",
                   refs=[{"session": "99999999-0000-0000-0000-000000000000"}]),
        _stall_row(3, "dispatch", "#943", 5, now=now, actor="hq"),
    ]
    names = {ledger_session: "Ledger"}

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at,
                                  lane_names_fn=lambda: names)
    line_941 = [ln for ln in leg["problems"] if "#941" in ln][0]
    assert "ADDRESSED to Ledger" in line_941, line_941
    assert "actor=hq" not in line_941, (
        f"the AUTHOR must never stand in the addressee's slot -- it reads as an "
        f"assignment\n{line_941}"
    )
    for unit in ("#942", "#943"):
        line = [ln for ln in leg["problems"] if unit in ln][0]
        assert "NO ADDRESSEE RESOLVES" in line, (
            f"{unit} declares no resolvable target and the line must SAY SO, never fall back "
            f"to the author\n{line}"
        )
        assert "actor=hq" not in line, line
    cov = leg["coverage"]
    assert cov["units_owed"] == 3, cov
    assert cov["addressees_resolved"] == 1, cov
    assert cov["addressees_unresolved"] == 2, cov

    # THE TWO-SIDED HALF: with a resolver that knows NOTHING, the same row cannot name a lane,
    # so "ADDRESSED to Ledger" is a statement about the RESOLUTION and not a constant the leg
    # prints. This is also the shape a member factory without a binding store sees.
    blind = RUNNER.stall_census_leg(issues, rows, read_at=read_at, lane_names_fn=lambda: {})
    assert "ADDRESSED to Ledger" not in "\n".join(blind["problems"]), blind["problems"]
    assert blind["coverage"]["addressees_resolved"] == 0, blind["coverage"]

    # ... and the render half: the addressee and its coverage reach the report, and `actor=`
    # is nowhere on it.
    rc, out, _ = _run(issues, rows, lane_names_fn=lambda: names)
    assert rc == 1, f"an OWED line must fail the run, got rc={rc}\n{out}"
    assert "ADDRESSED to Ledger" in out, out
    assert "addressee: 1 of 3 OWED unit(s) name the lane the work was handed to; " \
           "2 declare none" in out, out
    assert "actor=hq" not in out, out

def test_the_stall_census_leg_DISCHARGES_on_an_act_but_CLEARS_only_on_a_claim_or_close() -> None:
    """#308 acceptance (3): a re-dispatch DISCHARGES the lane's duty but does NOT clear the
    census READING, and does NOT reset the age clock.

    The distinction the Triage card's old sentence collapsed -- *"Clearing an `OWED` line is
    an ACT -- a re-dispatch through `session_notify`, or a board close"* -- into a single
    verb. `stall_census_leg` keys each unit's EARLIEST dispatch-bearing row
    (`carriers.setdefault`) and clears a unit only on a `claim` or a `close`, deliberately,
    so that "a re-dispatch would otherwise reset the clock and hide a stall that has stood
    for a fortnight" (its own docstring).

    So a unit dispatched, then RE-dispatched hours ago, is still OWED at its ORIGINAL age --
    and the age is read off the RENDER, because a leg naming the right unit at the wrong age
    would be a different statement: that the re-dispatch reset the clock.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(911, "OPEN"), _issue(912, "OPEN")]
    rows = [
        _stall_row(1, "intake", "#911", 4, now=now),
        _stall_row(2, "dispatch", "#911", 3, now=now),     # dispatched 3 d ago
        _stall_row(3, "dispatch", "#911", 0.1, now=now),   # RE-dispatched 0.1 d ago
        _stall_row(4, "intake", "#912", 4, now=now),
        _stall_row(5, "dispatch", "#912", 3, now=now),     # dispatched 3 d ago
        _stall_row(6, "claim", "#912", 0.1, now=now),      # then CLAIMED
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    assert "OWED #911" in named, (
        f"a re-dispatch is neither a `claim` nor a `close` -- the line must STAND, or the "
        f"census clears on an act it is not supposed to clear on\n{named}"
    )
    assert "dispatched 3.00 d ago" in named, (
        f"the age must run from the EARLIEST dispatch-bearing row: a re-dispatch must not "
        f"reset the clock and hide a stall that has stood for a fortnight\n{named}"
    )
    assert "#912" not in named, (
        f"a `claim` row clears the line -- that unit has a taker\n{named}"
    )
    assert leg["coverage"]["units_owed"] == 1, leg["coverage"]

    # The render half: a leg returning the right dict while the report drops it is the
    # half-fix this catches.
    rc, out, _ = _run(issues, rows)
    assert rc == 1, f"an OWED line must fail the run, got rc={rc}\n{out}"
    assert "OWED #911" in out, out
    assert "dispatched 3.00 d ago" in out, out

    # THE CONTROL, asserted rather than described: the naive "LATEST dispatch row" reading
    # dates #911 at 0.10 d -- below the 1.0 d threshold -- and would report NOTHING owed. A
    # leg that keyed the latest row fails on the assertions above; this measures that the
    # fixture can TELL the two apart, so the probe is never vacuous.
    latest = max(
        (r for r in rows if r["event"] == "dispatch" and r["subject"] == "#911"),
        key=lambda r: r["n"],
    )
    naive_age = (
        now - dt.datetime.strptime(latest["ts"], "%Y-%m-%dT%H:%M:%SZ")
        .replace(tzinfo=dt.timezone.utc)
    ).total_seconds() / 86400.0
    assert naive_age < RUNNER.STALL_CENSUS_THRESHOLD_DAYS, (
        f"the control must BITE: the latest-dispatch reading is {naive_age:.2f} d and must "
        f"fall BELOW the {RUNNER.STALL_CENSUS_THRESHOLD_DAYS} d threshold, or the fixture "
        f"cannot tell earliest from latest and the probe proves nothing"
    )

def test_the_stall_census_leg_reads_CARRIED_units_and_only_from_a_CARRIER() -> None:
    """#260 acceptance (1), the population half: a unit dispatched by a WAVE row is a
    dispatched unit, and each of the three shapes that merely LOOK like one is refused.

    This is the measured class the whole leg exists for. Board #181 carries intake n=1221,
    run n=1226 and ruling n=1233 and NO dispatch row of its own -- its dispatch leg is the
    wave row n=1214 (`subject=kit-adoption-wave-2026-09-26`, `refs=None`), whose detail
    reads "...carrying BOTH instruments (board #181 ledger bundle, board #182
    questions)...". A subject-keyed census cannot see it (#2092, ruling n=2100).

    The other half is the false positive the naive `#\\d+` scan generates, and the fixture
    carries each shape the discriminator must refuse:

    * `#908` is named inside a WORK-UNIT dispatch's own detail -- a cross-reference, not a
      carrier's payload, so the row is never scanned as a carrier at all;
    * `#909` is named by a real carrier but has NO ledger rows of its own, which is what a
      prose mention of another repository's number looks like;
    * `#910` HAS rows of its own and is named by a real carrier, yet is not an issue this
      board declares -- the `#366` shape, which carries ledger rows n=433 and n=436 and is
      not on this board at all (the fork's `#366`).

    Measured 2026-10-03, a scan that admitted the prose shapes reported 160 units against a
    true population of 206 examined / 20 owed, and corrupted ages -- a mention moved `#49`
    from 15.05 d to 4.96 d.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(906, "OPEN"), _issue(907, "OPEN"), _issue(908, "OPEN")]
    rows = [
        _stall_row(1, "intake", "#906", 4, now=now),
        _stall_row(2, "dispatch", "kit-adoption-wave-probe", 3, now=now,
                   actor="delegate",
                   detail="dispatched to five member HQs (board #906 ledger bundle)"),
        _stall_row(3, "intake", "#907", 5, now=now),
        _stall_row(4, "dispatch", "#907", 4, now=now,
                   detail="WHY NOT COVERED BY #908"),
        _stall_row(5, "dispatch", "sweep-probe-2026-10-03", 3, now=now,
                   detail="sweep of the board (board #909 backlog)"),
        _stall_row(6, "intake", "#910", 6, now=now),
        _stall_row(7, "dispatch", "relay-probe-2026-10-03", 5, now=now,
                   detail="relayed onward (board #910 follow-up)"),
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    assert "OWED #906" in named, (
        f"a unit carried by a wave row IS a dispatched unit and must be named\n{named}"
    )
    assert "OWED #907" in named, f"a work-unit dispatch is dispatched too\n{named}"
    assert "#908" not in named, (
        f"a unit named inside another unit's dispatch is a cross-reference, not a "
        f"carrier's payload\n{named}"
    )
    assert "#909" not in named, (
        f"a unit with no ledger rows of its own is a prose mention\n{named}"
    )
    assert "#910" not in named, (
        f"a unit the board does not declare is not a unit of this board's namespace, "
        f"however many ledger rows it carries\n{named}"
    )
    cov = leg["coverage"]
    assert cov["carried_units_resolved"] == 2, cov
    assert cov["units_off_board"] == 1, cov
    assert cov["observation_dispatches"] == 1, cov
    assert cov["units_in_population"] == 3, cov
    assert cov["units_owed"] == 2, cov

def test_the_stall_census_leg_counts_an_OBSERVATION_dispatch_and_never_judges_it() -> None:
    """A descriptive-stem dispatch naming NO work unit is EXPLICITLY LEGAL (ruling n=524),
    and the leg must COUNT it rather than read it as an empty population.

    The pair is deliberate: a leg that judged these would red the run for the ordinary
    relay traffic this factory runs on, and a leg that silently dropped them would report
    the same numbers whether it examined them or never looked.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(901, "OPEN")]
    rows = [
        _stall_row(1, "intake", "#901", 4, now=now),
        _stall_row(2, "dispatch", "#901", 3, now=now),
        _stall_row(3, "dispatch", "board-hygiene-observation", 2, now=now,
                   detail="nothing in particular was handed over"),
    ]
    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    cov = leg["coverage"]
    assert cov["dispatch_rows_examined"] == 2, cov
    assert cov["observation_dispatches"] == 1, cov
    assert cov["units_in_population"] == 1, cov
    assert cov["units_owed"] == 1, cov
    assert len(leg["problems"]) == 1, leg["problems"]

def test_the_stall_census_leg_PRINTS_its_threshold_with_its_basis() -> None:
    """#260 acceptance (3): the threshold and the basis it rests on are PRINTED on every
    run, never carried in a reader's memory -- and the basis must NAME the distinction the
    ruling drew, or the two thresholds read as one number in two places (n=1861).

    Asserted on the RENDER, not on the constant: a basis declared in a module constant and
    dropped from the report is the same failure as one never written.
    """
    rc, out, _ = _run([_issue(901, "OPEN")], [])
    assert "LEG stall-census — ASSERTED" in out, out
    assert "never claimed past the declared threshold of 1.0 d" in out, out
    assert "threshold basis: 1.0 d" in out, out
    assert "CLAIMED-but-silent" in out, (
        f"the basis must name the Triage card's own predicate it is NOT\n{out}"
    )

def test_the_stall_census_leg_does_not_harvest_a_REPOSITORY_QUALIFIED_mention() -> None:
    """#333 acceptance: a `#N` the prose QUALIFIES as another repository's is not a unit
    of this board, and the harvest itself survives the guard.

    The live collision this arm reproduces, measured 2026-10-05: ledger row n=186
    (`subject "#332-D5"`, a comment on the FORK's issue) names *"fork issue #332"* in its
    detail, while the unrelated intake row n=2421 (`subject "#332"`) makes that same
    number RESIDENT -- so the pre-fix harvest carried `#332` out of the fork mention and
    the patrol printed `OWED #332: dispatched 17.22 d ago` against a board item filed the
    same day.

    FOUR foreign shapes the guard must refuse are covered by the direct unit arm at the
    bottom; this fixture covers the collision end to end AND keeps a legitimate carrier,
    so the probe is never vacuous: a guard that dropped the whole harvest would pass the
    `#901` half and fail the `#902` half.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [
        _issue(901, "OPEN"),   # the colliding board item: open, never claimed
        _issue(902, "OPEN"),   # carried by THIS board's own dispatch prose -> still OWED
    ]
    rows = [
        # The colliding intake row: it makes `#901` RESIDENT without dispatching it.
        _stall_row(1, "intake", "#901", 20, now=now, actor="triage"),
        # The CARRIER: a fork-issue comment whose prose names "fork issue #901".
        _stall_row(2, "dispatch", "#901-D5", 17.22, now=now, actor="triage",
                   detail="dispatched to OpenCrabs Kanban Board HQ as comment on "
                          "fork issue #901 (issuecomment-5727369776)"),
        # A legitimate unit of this board, made resident by its own intake row.
        _stall_row(3, "intake", "#902", 5, now=now, actor="triage"),
        # A wave whose prose carries THIS board's unit -- the harvest must keep working.
        _stall_row(4, "dispatch", "wave-2026-10-05", 3, now=now,
                   detail="routed #902 to the Worker lane"),
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    assert "OWED #901" not in named, (
        "a `#N` the detail QUALIFIES as another repository's (`fork issue #901`) is not a "
        f"unit of this board, however many rows the local issue carries\n{named}"
    )
    assert "OWED #902" in named, (
        "the harvest itself must SURVIVE the scope guard: a wave naming this board's own "
        f"unit still dispatched it\n{named}"
    )
    assert leg["coverage"]["units_owed"] == 1, leg["coverage"]

    # THE CONTROL, asserted rather than described: on THIS fixture the pre-fix predicate
    # (`is_work_unit(token) and token in resident`, no occurrence scope) DOES admit
    # `#901` -- the token is a strict unit and a resident subject -- so the two predicates
    # are distinguishable here and the probe is not vacuous.
    detail = rows[1]["detail"]
    assert "#901" in {str(r["subject"]).strip() for r in rows}, (
        "the collision needs a RESIDENT subject of the same number, or the fixture tests "
        "the residency guard instead of the scope guard"
    )
    assert RUNNER.is_board_unit_occurrence(detail, detail.index("#901")) is False, (
        f"the occurrence guard must refuse the fork mention in {detail!r}"
    )

    # ... and through the REAL `main()`: the render must carry the same verdict, because a
    # leg returning a correct dict while the report drops it is the half-fix this catches.
    rc, out, _ = _run(issues, rows)
    assert "OWED #902" in out, out
    assert "OWED #901" not in out, out

def test_the_scope_guard_refuses_every_measured_foreign_shape() -> None:
    """#333 acceptance, the direct arm: the four shapes the 2026-10-05 measurement found
    on the live ledger, and the two shapes that must stay ADMITTED.

    Named one by one because a guard tuned to the single reported case would pass a
    one-shape probe: the collision is *"fork issue #332"*, but the same defect was live in
    `inferhub-watch#115`, `alexeyleshchenko/ai-antispam#76` and
    `leshchenko1979/opencrabs #366` -- three different spellings of "another repository".
    The two admitted shapes are the ones a scope guard is most likely to over-reach on: a
    UNIT LIST (`#200/#344/#12`, whose slash is a separator, not a path) and a plain
    mention preceded by an ordinary word.
    """
    refused = [
        ("dispatched as comment on fork issue #332 (issuecomment-5727369776)", "#332"),
        ("ai-antispam 13, inferhub 4 (tracked at inferhub-watch#115, NOT routed)", "#115"),
        ("ai-antispam -- alexeyleshchenko/ai-antispam#76, OPEN. Its board...", "#76"),
        ("FILED: leshchenko1979/opencrabs #366 - \"restart recovery\"", "#366"),
    ]
    admitted = [
        ("no claim rows exist for #31 or #32 on the ledger", "#31"),
        ("WHY NOT COVERED BY #200/#344/#12: those cover a different failure", "#12"),
        ("Priority unchanged: #33/#35, then #34 (n=222)", "#34"),
        ("FINDINGS: (1) #33 unclaimed 4h10m", "#33"),
    ]
    for blob, token in refused:
        assert RUNNER.is_board_unit_occurrence(blob, blob.index(token)) is False, (
            f"{token} in {blob!r} names another repository's namespace and must be REFUSED"
        )
    for blob, token in admitted:
        assert RUNNER.is_board_unit_occurrence(blob, blob.index(token)) is True, (
            f"{token} in {blob!r} is written as a unit of THIS board and must be ADMITTED"
        )

def test_the_stall_census_leg_refuses_a_dispatch_that_PREDATES_the_item_it_names() -> None:
    """#415 acceptance: the harvest must not pair a FOREIGN or OLDER mention with a
    today-filed issue.

    Two doors #333's scope guard left open, both measured live 2026-10-06:

    * the CARRIER bare-prose mention -- carrier `n=321` (2026-09-18) writes
      `WHY NOT COVERED BY #200/#344/#12`, while this board minted `#344` on
      2026-10-05, so the carrier PREDATES the item it was read as dispatching;
    * the CROSS-NAMESPACE subject collision -- `#366`'s rows `n=433`/`n=436` are the
      FORK's, while this board minted its own `#366` on 2026-10-05.

    Both read `OWED ... 17 d ago`. The guard: a dispatch row that PREDATES the item's own
    `createdAt` cannot be a dispatch of it. Two controls are deliberate -- `#903` is a
    genuine stall dispatched AFTER its filing (must STAY OWED, so the guard is not an
    over-reaching blanket), and `#904` carries NO `createdAt` (must STAY OWED, so a read
    that omits the field keeps every other verdict intact).
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    minted = (now - dt.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    minted_older = (now - dt.timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [
        {"number": 901, "state": "OPEN", "title": "issue 901", "closedAt": None,
         "createdAt": minted},   # a carrier names it 17 d BEFORE the board minted it
        {"number": 902, "state": "OPEN", "title": "issue 902", "closedAt": None,
         "createdAt": minted},   # a foreign row carries the subject before minting
        {"number": 903, "state": "OPEN", "title": "issue 903", "closedAt": None,
         "createdAt": minted_older},   # a genuine stall: filed 5 d ago, dispatched 3 d ago
        {"number": 904, "state": "OPEN", "title": "issue 904", "closedAt": None},
    ]                            # `#904` declares NO `createdAt` -- the guard is a no-op
    rows = [
        _stall_row(1, "intake", "#901", 20, now=now, actor="triage"),
        _stall_row(2, "dispatch", "wave-2026-09-18", 17, now=now, actor="delegate",
                   detail="WHY NOT COVERED BY #200/#901/#12: those cover a different failure"),
        _stall_row(3, "intake", "#902", 20, now=now, actor="triage"),
        _stall_row(4, "dispatch", "#902", 17, now=now, actor="triage",
                   detail="the fork's row, filed under the same number"),
        _stall_row(5, "intake", "#903", 20, now=now, actor="triage"),
        _stall_row(6, "dispatch", "#903", 3, now=now, actor="hq"),   # AFTER minting
        _stall_row(7, "intake", "#904", 20, now=now, actor="triage"),
        _stall_row(8, "dispatch", "#904", 5, now=now, actor="hq"),   # no createdAt -> judged
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    assert "OWED #901" not in named, (
        f"a carrier that PREDATES the board item it names cannot have dispatched it\n{named}"
    )
    assert "OWED #902" not in named, (
        f"a subject-keyed dispatch older than the item is a foreign row, not this "
        f"board's\n{named}"
    )
    assert "OWED #903" in named, (
        f"a genuine stall dispatched AFTER its filing must STAY OWED -- the guard must not "
        f"be an over-reaching blanket\n{named}"
    )
    assert "OWED #904" in named, (
        f"a read that omits `createdAt` must keep the verdict -- the guard is a no-op, "
        f"never a fail-closed\n{named}"
    )
    cov = leg["coverage"]
    assert cov["units_rejected_pre_filing"] == 2, cov
    assert cov["units_owed"] == 2, cov
    assert cov["units_in_population"] == 2, cov

    # THE CONTROL, asserted rather than described: the #333 SCOPE guard ADMITS the carrier
    # mention (a unit list, `#200/#901/#12`), so what refuses it is the FILING guard and
    # not the scope guard -- the probe is never vacuous.
    detail = rows[1]["detail"]
    assert RUNNER.is_board_unit_occurrence(detail, detail.index("#901")) is True, (
        f"the scope guard ADMITS this bare carrier mention; only the filing guard refuses "
        f"it\n{detail!r}"
    )

    # ... and through the REAL `main()`: a leg returning the right dict while the render
    # drops it is the half-fix this catches.
    rc, out, _ = _run(issues, rows)
    assert "OWED #903" in out, out
    assert "OWED #904" in out, out
    assert "OWED #901" not in out, out
    assert "OWED #902" not in out, out

# --- the pacemaker-presence leg (#315) -----------------------------------------------

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

def _presence_leg(rows, *, register=_PRESENCE_REGISTER, fragment=_PRESENCE_FRAGMENT,
                  bindings=_PRESENCE_BINDINGS, prefixes=("factory-",)):
    return RUNNER.pacemaker_presence_leg(
        rows, bindings, register, fragment, read_at="2026-10-05T00:00:00Z",
        slug="meta-factory", prefixes=list(prefixes), homes_read=["probe-home"],
        registry=_StubRegistry(),
    )

def test_the_pacemaker_presence_leg_NAMES_an_owner_with_no_wake() -> None:
    """THE BITING PROBE. A register-declared owner with no inbound wake is NAMED.

    The row population is NON-EMPTY and carries a wake for a DIFFERENT session, so a clean
    verdict cannot come from an empty read — the failure is found in a populated table,
    which is exactly the #253 shape (a deleted row leaves the rest intact).
    """
    rows = [{"name": "factory-other", "prompt": "", "deliver_to": "session:SOMEONE-ELSE"}]
    leg = _presence_leg(rows)
    assert leg["status"] == "ASSERTED", leg
    assert len(leg["problems"]) == 3, leg["problems"]
    hq = [p for p in leg["problems"] if p.startswith("HQ")]
    assert len(hq) == 1, leg["problems"]
    assert "U-HQ" in hq[0] and "NO inbound wake" in hq[0], hq
    assert "HQ (U-HQ): NO WAKE" in leg["coverage"]["owners"], leg["coverage"]["owners"]
    assert leg["coverage"]["owners_declared"] == 3, leg["coverage"]

def test_the_pacemaker_presence_leg_is_QUIET_when_a_woken_sibling_is_present() -> None:
    """THE CONTROL. The same read that names an unwoken owner must clear a woken one.

    Both wake SHAPES are exercised — HQ by `deliver_to = session:<uuid>`, Triage by a
    prompt-carried notify — so the control proves the leg is not a constant RED and that
    the wake vocabulary is the thinness gate's own, not a `deliver_to`-only test.
    """
    rows = [
        {"name": "factory-hq-pacemaker", "prompt": "", "deliver_to": "session:U-HQ"},
        {"name": "factory-triage-patrol", "prompt": "", "deliver_to": "session:U-TRIAGE"},
    ]
    leg = _presence_leg(rows)
    problems = [p for p in leg["problems"] if p.startswith(("HQ", "Triage"))]
    assert problems == [], problems
    owners = leg["coverage"]["owners"]
    assert any(o.startswith("HQ (U-HQ): woken by factory-hq-pacemaker") for o in owners), owners
    assert any(o.startswith("Triage (U-TRIAGE): woken") for o in owners), owners

def test_a_presence_problem_FAILS_the_run() -> None:
    """A problem the leg reports must reach the run's verdict, never sit in a block only."""
    rows = [{"name": "factory-other", "prompt": "", "deliver_to": "session:SOMEONE-ELSE"}]
    leg = _presence_leg(rows)
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home"], prefixes=["factory-"],
                      presence_fn=lambda *a, **k: leg)
    assert rc == 1, f"a presence problem must FAIL the run, got rc={rc}\n{out}"
    assert "declared periodic process owner with NO inbound wake" in out, out

def test_the_pacemaker_presence_leg_PRINTS_its_examined_population() -> None:
    """A clean read over zero owners must not be indistinguishable from a verified one.

    The render names the register, the owner count, the rows judged and EVERY owner with
    its resolved session and the wake that satisfies it — the population travels with the
    verdict (#242).
    """
    _thin_decl = f"{_WAKE_PROMPT}\n\n{_NONE_DECL}"
    rows = [{"name": "factory-hq-pacemaker", "prompt": _thin_decl,
             "deliver_to": "session:U-HQ"},
            {"name": "factory-triage-patrol", "prompt": _thin_decl,
             "deliver_to": "session:U-TRIAGE"},
            {"name": "factory-measurement-daily", "prompt": _thin_decl,
             "deliver_to": "session:U-SURVEYS"}]
    leg = _presence_leg(rows)
    assert leg["problems"] == [], leg["problems"]
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home"], prefixes=["factory-"],
                      presence_fn=lambda *a, **k: leg)
    assert rc == 0, out
    assert "LEG pacemaker-presence — ASSERTED" in out, out
    assert "3 owner(s) declared" in out, out
    assert "population (owner — resolved session — the wake that satisfies it):" in out, out
    assert "HQ (U-HQ): woken by factory-hq-pacemaker" in out, out
    assert "Surveys (U-SURVEYS): woken by factory-measurement-daily" in out, out
    assert "3 declared periodic owner(s) checked for an inbound wake" in out, out

def test_the_pacemaker_presence_leg_fails_OPEN_when_the_register_is_absent() -> None:
    """An unreadable DECLARATION is NOT RUN with its reason — never a clean read.

    The expected set comes from the register; if the register cannot be read, the leg has
    verified nothing, and a silent clean verdict here is the very failure #315 exists to
    close (the check passing while testing nothing).
    """
    missing = Path(tempfile.mkdtemp(prefix="probe-no-register-")) / "processes.md"
    leg = RUNNER.pacemaker_presence_leg(
        [{"name": "factory-x", "prompt": "", "deliver_to": ""}], [],
        None, None, read_at="2026-10-05T00:00:00Z", prefixes=["factory-"],
        register_path=missing,
    )
    assert leg["status"] == "NOT RUN", leg
    assert leg["problems"] == [], leg
    assert "could not be read" in leg["coverage"]["reason"], leg["coverage"]
    assert str(missing) in leg["coverage"]["reason"], leg["coverage"]
    rc, out, _ = _run([], [], cron_rows=[], homes=["probe-home"], prefixes=["factory-"],
                      presence_fn=lambda *a, **k: leg)
    assert "LEG pacemaker-presence — NOT RUN" in out, out
    assert "NOT RUN: the process register" in out, out

def test_an_owner_with_no_resolvable_session_is_reported_never_excused() -> None:
    """A role the fragment does not map, or a lane with no live session, is a PROBLEM.

    Dropping the owner here would be the leg committing the very failure it exists to
    catch — an owner silently excused. The CAUSE travels in the coverage notes, the
    PROBLEM comes from the pure predicate (one source for the verdict, never two).
    """
    fragment = {"lanes": [{"role": "hq", "thread_id": 21}]}  # Triage/Surveys unmapped
    leg = _presence_leg(
        [{"name": "factory-hq-pacemaker", "prompt": "", "deliver_to": "session:U-HQ"}],
        fragment=fragment,
    )
    assert len(leg["problems"]) == 2, leg["problems"]
    assert all("could not be resolved" in p for p in leg["problems"]), leg["problems"]
    assert any("no lane with role 'triage'" in n for n in leg["coverage"]["resolution_notes"]), \
        leg["coverage"]["resolution_notes"]

def test_the_presence_leg_is_INJECTABLE_and_wired_by_default() -> None:
    """`presence_fn` is a real parameter, and the default is the live wiring."""
    import inspect
    params = inspect.signature(RUNNER.main).parameters
    assert "presence_fn" in params, sorted(params)
    assert hasattr(RUNNER, "live_pacemaker_presence_leg"), "the live wiring must exist"
    assert hasattr(RUNNER, "declared_slug"), "the slug resolver must exist"


# ---- the workspace-blocked leg (issue #201, ruled at ledger n=2286) --------------------
#
# The closing invariant gained a SECOND lawful verdict, `workspace_gate=blocked-by-unowned`,
# lawful ONLY when the row NAMES the blocking paths. A lawful exception must remain a VISIBLE
# DEBT, so the standing patrol prints the population and cross-reads the named paths live.
# These probes drive the leg directly (and one drives `main()`) so each property is asserted
# rather than assumed: it BITES on the unexaminable declaration, REPORTS a cleared path, is
# LOUD on a zero population, and never counts a mere MENTION as a declaration.

def _gate_row(n, subject, paths, *, event="score", gate="blocked-by-unowned"):
    """One governed-run row whose canonical trailer declares a workspace gate.

    `paths=None` omits `blocked_paths=` entirely; `paths=[]` writes it EMPTY. Both are the
    unexaminable shape the ruling refuses, and both must bite.
    """
    detail = "a governed run closed its workspace gate"
    detail += f" workspace_gate={gate}"
    if paths is not None:
        detail += f" blocked_paths={','.join(paths)}"
    return {"n": n, "event": event, "subject": subject, "detail": detail}

def test_the_workspace_blocked_leg_BITES_on_a_declaration_that_names_no_paths() -> None:
    """The unexaminable excuse is a PROBLEM, not a silent pass (the ruling's refusal)."""
    leg = RUNNER.workspace_blocked_leg(
        [_gate_row(1, "survey-x", None)], read_at="2026-10-05T00:00:00Z",
        dirty_paths_fn=lambda: set(),
    )
    assert leg["status"] == "ASSERTED", leg
    assert leg["coverage"]["blocked_declarations"] == 1, leg["coverage"]
    assert any("names NO blocking paths" in p for p in leg["problems"]), leg["problems"]

def test_the_workspace_blocked_leg_BITES_on_an_EMPTY_paths_value() -> None:
    """`blocked_paths=` with no value is a MENTION, not a declaration — it must bite too."""
    leg = RUNNER.workspace_blocked_leg(
        [_gate_row(2, "survey-y", [])], read_at="2026-10-05T00:00:00Z",
        dirty_paths_fn=lambda: set(),
    )
    assert any("names NO blocking paths" in p for p in leg["problems"]), leg["problems"]

def test_the_workspace_blocked_leg_REPORTS_a_path_no_longer_dirty() -> None:
    """The cross-read separates the still-stranded from the settled, and never reds on the
    settled half — a declaration true at its instant is history, not a permanent defect."""
    leg = RUNNER.workspace_blocked_leg(
        [_gate_row(3, "survey-z", ["evidence/a.md", "evidence/b.md"])],
        read_at="2026-10-05T00:00:00Z",
        dirty_paths_fn=lambda: {"evidence/a.md"},
    )
    assert leg["problems"] == [], leg["problems"]
    entry = leg["coverage"]["blocked_rows"][0]
    assert entry["still_dirty"] == ["evidence/a.md"], entry
    assert entry["no_longer_dirty"] == ["evidence/b.md"], entry

def test_the_workspace_blocked_leg_is_LOUD_on_a_zero_population() -> None:
    """Zero blocked declarations is NOT RUN with its reason, never a clean HOLD (#242)."""
    leg = RUNNER.workspace_blocked_leg(
        [_gate_row(4, "survey-clean", None, gate="rc=0")],
        read_at="2026-10-05T00:00:00Z", dirty_paths_fn=lambda: set(),
    )
    assert leg["status"] == "NOT RUN", leg
    assert "zero is LOUD" in leg["coverage"]["reason"], leg["coverage"]
    assert leg["problems"] == [], leg["problems"]

def test_the_workspace_blocked_leg_goes_NOT_RUN_when_the_tree_is_UNREADABLE() -> None:
    """A cross-reader that cannot read the tree has corroborated nothing — never "all cleared"."""
    def boom():
        raise RUNNER.BoardReadError("git status exited 128: not a git repository")
    leg = RUNNER.workspace_blocked_leg(
        [_gate_row(5, "survey-w", ["evidence/a.md"])],
        read_at="2026-10-05T00:00:00Z", dirty_paths_fn=boom,
    )
    assert leg["status"] == "NOT RUN", leg
    assert "unreadable" in leg["coverage"]["reason"], leg["coverage"]

def test_a_MENTION_of_the_blocked_token_is_not_a_declaration() -> None:
    """The read is the POSITIONAL trailer, never a substring: a row that cites the token in
    prose — a dispatch, a ruling, the ledger repair that appended it — is not a run, and
    counting it would be this reader's own echo mistaken for evidence (AGENTS.md rule 7)."""
    rows = [
        {"n": 6, "event": "dispatch", "subject": "#201",
         "detail": "GOAL: the verdict workspace_gate=blocked-by-unowned is lawful"},
        {"n": 7, "event": "score", "subject": "survey-v",
         "detail": "this run cites workspace_gate=blocked-by-unowned in prose, not as a "
                   "trailer, so it declares nothing"},
    ]
    leg = RUNNER.workspace_blocked_leg(
        rows, read_at="2026-10-05T00:00:00Z", dirty_paths_fn=lambda: set(),
    )
    assert leg["coverage"]["blocked_declarations"] == 0, leg["coverage"]
    assert leg["status"] == "NOT RUN", leg

def test_the_workspace_blocked_leg_is_WIRED_and_bites_through_main() -> None:
    """End to end: a no-paths declaration in the ledger REDs the run and the leg is printed."""
    rc, out, _ = _run(
        [], [_gate_row(8, "survey-u", None)],
        dirty_paths_fn=lambda: set(),
    )
    assert rc == 1, f"an unexaminable declaration must fail the run\n{out}"
    assert "LEG workspace-blocked" in out, out
    assert "NO paths named" in out, out

def test_the_workspace_blocked_leg_is_INJECTABLE_and_wired_by_default() -> None:
    """`dirty_paths_fn` is a real parameter, and the live tree read is the default."""
    import inspect
    params = inspect.signature(RUNNER.main).parameters
    assert "dirty_paths_fn" in params, sorted(params)
    assert hasattr(RUNNER, "live_dirty_paths"), "the live tree read must exist"

def test_the_board_unruled_leg_BITES_and_discriminates_on_every_neighbour() -> None:
    """#332 acceptance (a): the round's own predicate -- an OPEN item carrying an `intake`
    row and NO `ruling` row -- is DETECTED past the threshold, and the five neighbours that
    look like it stay quiet.

    The neighbours are the whole point, because each is a live false positive a naive
    reading ("any open item without a ruling row") would report: a fresh item is IN FLIGHT,
    a ruled item is out of the population, a CLOSED item owes the round nothing, an item
    with no intake row belongs to `board_intake_leg`, and a ruling stamped under a
    DESCRIPTIVE subject governs its item through the resolver's `declared` arm. A probe
    that supplied only the true positive would pass a leg that reported all six.

    The defect this reproduces, measured 2026-10-05 (#332): #327 carried intake n=2380 at
    12:07:20Z, was OPEN, and had no `ruling` row when the round swept at 12:50Z -- and
    nothing went red, because no leg had this population.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [
        _issue(921, "OPEN"),    # intaken 2 d ago, NO ruling row -> OWED
        _issue(922, "OPEN"),    # intaken 1 h ago, no ruling row -> in flight
        _issue(923, "OPEN"),    # intaken, and RULED (strict `#923`)
        _issue(924, "CLOSED"),  # intaken and unruled, but the board closed it
        _issue(925, "OPEN"),    # unruled and open, but carries NO intake row
        _issue(926, "OPEN"),    # ruled under a DESCRIPTIVE subject, via `governs=`
    ]
    rows = [
        _stall_row(21, "intake", "#921", 2, now=now),
        _stall_row(22, "intake", "#922", 1 / 24, now=now),
        _stall_row(23, "intake", "#923", 3, now=now),
        _stall_row(24, "ruling", "#923", 2.9, now=now),
        _stall_row(25, "intake", "#924", 3, now=now),
        _stall_row(26, "close", "#924", 2.5, now=now),
        _stall_row(27, "intake", "#926", 3, now=now),
        _stall_row(28, "ruling", "concern-probe", 2.9, now=now,
                   detail="governs=926"),
    ]

    leg = RUNNER.board_unruled_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    assert "#921" in named, f"the unruled intaken item must be NAMED\n{named}"
    for quiet in ("#922", "#923", "#924", "#925", "#926"):
        assert quiet not in named, (
            f"{quiet} must NOT be reported: a fresh item is in flight, a ruled one is out "
            f"of the population, a closed one owes the round nothing, an item with no "
            f"intake row belongs to the intake leg, and a `governs=` ruling IS a ruling"
            f"\n{named}"
        )
    assert leg["coverage"]["items_owed_ruling"] == 1, leg["coverage"]
    assert leg["coverage"]["population_unruled"] == 2, leg["coverage"]

    # ... and the same fixture through the REAL `main()`: the report must carry the leg,
    # the OWED line AND the population it was read from. A leg returning a correct dict
    # while the render drops it is the half-fix this half exists to catch. (#925 also REDs
    # `board-intake` here, deliberately: it is the boundary between the two legs -- an open
    # item with NO intake row is that leg's population, not this one's.)
    rc, out, _ = _run(issues, rows)
    assert rc == 1, f"an OWED line must fail the run, got rc={rc}\n{out}"
    assert "LEG board-unruled — ASSERTED" in out, out
    assert "#921 is OPEN on the board" in out, out
    assert "population (OPEN, intake row, NO ruling row): 2 item(s) -- 1 past" in out, out
    assert "board read at " in out, out

def test_the_board_unruled_leg_PRINTS_an_EMPTY_population_rather_than_silence() -> None:
    """#332 acceptance (b): a clean sweep over an EMPTY population is distinguishable from
    a leg that examined nothing -- the population count and the board read instant are
    PRINTED, and the run is GREEN.

    This is the criterion the defect itself turns on: #327 was skipped by the round and
    NOTHING went red, so a leg that stayed silent on an empty population would reproduce
    the very failure it exists to detect. The discriminating control is the fixture with
    the `ruling` row REMOVED, which fires -- driven in the arm above -- so this one proves
    the leg's own empty read is PRINTED, not merely that it is quiet.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(931, "OPEN")]
    rows = [
        _stall_row(31, "intake", "#931", 5, now=now),
        _stall_row(32, "ruling", "#931", 4.9, now=now),
    ]

    leg = RUNNER.board_unruled_leg(issues, rows, read_at=read_at)
    assert leg["problems"] == [], leg
    assert leg["coverage"]["population_unruled"] == 0, leg["coverage"]
    assert leg["coverage"]["board_read_at"] == read_at, leg["coverage"]
    assert leg["coverage"]["open_items_examined"] == 1, leg["coverage"]

    rc, out, _ = _run(issues, rows)
    assert rc == 0, f"a ruled item is not a defect, got rc={rc}\n{out}"
    assert "LEG board-unruled — ASSERTED" in out, out
    assert "population (OPEN, intake row, NO ruling row): 0 item(s) -- 0 past" in out, out
    assert f"board read at {read_at}" in out, out

def test_the_board_unruled_leg_PRINTS_its_threshold_with_its_basis() -> None:
    """#332: the threshold and the basis it rests on are PRINTED on every run, never
    carried in a reader's memory -- and the basis must NAME the round's own cadence it is
    derived from, or the value reads as a chosen number.

    Asserted on the RENDER, not on the constant: a basis declared in a module constant and
    dropped from the report is the same failure as one never written.
    """
    rc, out, _ = _run([_issue(931, "OPEN")], [])
    assert "LEG board-unruled — ASSERTED" in out, out
    assert "past the declared threshold of 6.0 h" in out, out
    assert "threshold basis: 6.0 h" in out, out
    assert "HQ round cadence" in out, (
        f"the basis must name the round's own cadence it is taken from\n{out}"
    )

def test_the_board_unruled_leg_resolves_the_RULING_namespace_and_PRINTS_an_unplaced_row() -> None:
    """#332 + #243 clause 2: the RULING namespace is resolved through the ruling leg's own
    three arms -- so a ruling written under a SLUG and bridged by a later row that
    references its `n` still clears its item -- and a ruling row that resolves to NO issue
    is LISTED, never silently dropped.

    Dropping an unplaced row would report a smaller ruled set than was read, and the leg
    would then fire on an item that is in fact ruled -- a false red no reader could
    re-litigate. So the row is printed, and the item it fails to clear stays OWED.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(941, "OPEN"), _issue(942, "OPEN")]
    rows = [
        _stall_row(41, "intake", "#941", 3, now=now),
        _stall_row(42, "ruling", "slug-probe", 2.9, now=now),
        # the DISPATCH BRIDGE: a later row references the ruling's `n` and names the issue
        _stall_row(43, "dispatch", "#941", 2.8, now=now, detail="Ruling n=42"),
        _stall_row(44, "intake", "#942", 3, now=now),
        _stall_row(45, "ruling", "another-slug-probe", 2.9, now=now),
    ]

    leg = RUNNER.board_unruled_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    assert "#941" not in named, (
        f"a bridged ruling IS a ruling, and its item must not be reported\n{named}"
    )
    assert "#942" in named, f"an unplaced ruling clears nothing\n{named}"
    assert leg["coverage"]["resolution_arms"]["bridged"] == 1, leg["coverage"]
    assert leg["coverage"]["rulings_unbridgeable"] == 1, leg["coverage"]
    assert leg["coverage"]["unbridgeable_rows"][0]["n"] == 45, leg["coverage"]

    rc, out, _ = _run(issues, rows)
    assert "unbridgeable" in out, out
    assert "bridged 1" in out, out

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

# The typed target a dispatch fixture routes to. ONE name, so a probe that intends a
# DIFFERENT target has to say so, and a fixture cannot accidentally pass by matching on
# subject alone.
_PROBE_TARGET = "probe-session"

def test_the_dispatch_delivery_leg_BITES_and_clears_on_a_delivery() -> None:
    """#49 acceptance (1) and (2): the leg NAMES a dispatch row with no delivery inside its
    window, and the SAME fixture with a delivery produces no problem.

    Both halves are asserted, because a leg that reported every row would pass the first
    alone and a leg that reported none would pass the second.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    dispatched = now - dt.timedelta(hours=1)
    row = _stall_row(51, "dispatch", "#77", 0, now=dispatched, actor="triage",
                     refs=[{"session": _PROBE_TARGET}])

    leg = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: ([], ["probe-home"], []),
    )
    named = "\n".join(leg["problems"])
    assert leg["status"] == "ASSERTED", leg
    assert "n=51" in named and "#77" in named, f"the phantom must be NAMED\n{named}"
    assert leg["coverage"]["dispatch_rows_examined"] == 1, leg["coverage"]

    delivered = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(dispatched + dt.timedelta(seconds=60),
                       "[session-notify from=abc]\nDISPATCH #77 to the Worker")],
            ["probe-home"], [],
        ),
    )
    assert delivered["problems"] == [], delivered["problems"]

def test_the_dispatch_delivery_leg_anchors_on_the_ROWS_OWN_ts_not_the_newest_row() -> None:
    """#49 acceptance (3): the `#77` shape, asserted directly.

    A LATER row exists on the same subject, so a leg that anchored on the subject's NEWEST
    row would open its window after the delivery it is testing for and report a confident
    miss -- the exact error the first census made (ledger n=1893). The delivery here lands
    60 s after the DISPATCH row and two hours BEFORE the later row, so only a
    row-own-`ts` anchor can see it.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    dispatched = now - dt.timedelta(hours=3)
    dispatch = _stall_row(61, "dispatch", "#77", 0, now=dispatched, actor="triage",
                          refs=[{"session": _PROBE_TARGET}])
    later = _stall_row(62, "claim", "#77", 0, now=dispatched + dt.timedelta(hours=2))
    delivered_at = dispatched + dt.timedelta(seconds=60)

    leg = RUNNER.dispatch_delivery_leg(
        [dispatch, later], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(delivered_at, "[session-notify from=abc]\nDISPATCH #77")],
            ["probe-home"], [],
        ),
    )
    assert leg["problems"] == [], (
        f"a newest-row anchor would miss a delivery that is inside the ROW's own window\n"
        f"{leg['problems']}"
    )

def test_the_dispatch_delivery_token_is_no_narrower_than_the_artifact() -> None:
    """#49 acceptance (4): a delivery carrying the BARE subject number clears a dispatch
    written `#77`, and a WIDER token (a longer number containing 77) does not count.

    The first census searched `#77` where the artifact carried `77` and returned a zero
    that read as good news. The mirror error -- a substring test that lets `77` match
    inside `177` -- is just as silent, so both directions are asserted.
    """
    assert RUNNER.delivery_subject_matches("DISPATCH 77 to the Worker", "#77")
    assert RUNNER.delivery_subject_matches("DISPATCH #77", "#77")
    assert RUNNER.delivery_subject_matches("wave-2026-10-05 begins", "wave-2026-10-05")
    assert not RUNNER.delivery_subject_matches("row 177 of the table", "#77")
    assert not RUNNER.delivery_subject_matches("row 770 of the table", "#77")
    assert not RUNNER.delivery_subject_matches("#177 was closed", "#77")

    # #425: a hex continuation is the SAME class of silent over-match. The digits of a
    # commit sha (`423f233`) or of an identifier that continues in hex letters (`x423y`)
    # are not a `#423` subject, and a digit-only boundary matched BOTH -- so a delivery
    # naming an unrelated artifact cleared the leg. A longer NUMBER (`41423f5`) and a
    # longer ALPHANUMERIC token (`B4239.log`) already failed on the digit boundary and must
    # keep failing; a legitimate mention (`FILED as #423`) must keep passing.
    assert not RUNNER.delivery_subject_matches("version 0.1.25 (commit 423f233)", "#423")
    assert not RUNNER.delivery_subject_matches("the sha x423y here", "#423")
    assert not RUNNER.delivery_subject_matches("release 41423f5 shipped", "#423")
    assert not RUNNER.delivery_subject_matches("see B4239.log for detail", "#423")
    assert RUNNER.delivery_subject_matches("FILED as #423", "#423")

def test_the_dispatch_delivery_leg_COUNTS_pre_boundary_rows_and_never_judges_them() -> None:
    """#49: the historical population is legitimately large -- 430 live dispatch rows
    carry no verdict, and the ruling forbids backfilling them. A leg that judged them all
    is the permanent red #334 exists to stop, so a pre-boundary row is COUNTED and
    PRINTED, and the examined count is printed beside the verdict so a clean read over
    zero rows is never mistaken for a verified one.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    old = _stall_row(71, "dispatch", "#70", 5, now=now, actor="triage")

    leg = RUNNER.dispatch_delivery_leg(
        [old], read_at=read_at, bound=bound,
        deliveries_fn=lambda: ([], ["probe-home"], []),
    )
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["dispatch_rows_pre_boundary"] == 1, leg["coverage"]
    assert leg["coverage"]["dispatch_rows_examined"] == 0, leg["coverage"]

def test_the_dispatch_delivery_leg_FAILS_OPEN_on_a_refused_bound_and_a_blind_store() -> None:
    """#49 acceptance (1): the leg fails open -- an absent bound and an unreachable store
    each render NOT RUN with the reason, never a clean zero.

    A clean verdict over a store the leg could not read is the "confident zero that reads
    as good news" the ruling names as worse than no leg at all.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    row = _stall_row(81, "dispatch", "#80", 0, now=now, actor="triage",
                     refs=[{"session": _PROBE_TARGET}])

    refused = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=(None, "", "probe refusal"),
        deliveries_fn=lambda: ([], ["probe-home"], []),
    )
    assert refused["status"] == "NOT RUN", refused
    assert refused["problems"] == [], refused["problems"]
    assert "probe refusal" in (refused["reason"] or ""), refused

    blind = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=(now - dt.timedelta(days=1), "b", ""),
        deliveries_fn=lambda: ([], [], ["probe-home: could not be read"]),
    )
    assert blind["status"] == "NOT RUN", blind
    assert blind["problems"] == [], blind["problems"]
    assert "could not be read" in (blind["reason"] or ""), blind

def test_the_dispatch_delivery_leg_PRINTS_its_examined_population() -> None:
    """#49 acceptance (3): `examined 1, 1 problem` must never render the same as
    `examined 0`. Asserted on the RENDER, because a count computed and dropped from the
    report is the same failure as one never computed.
    """
    now = dt.datetime.now(dt.timezone.utc)
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    row = _stall_row(91, "dispatch", "#90", 0, now=now - dt.timedelta(minutes=5),
                     actor="triage", refs=[{"session": _PROBE_TARGET}])
    rc, out, _ = _run(
        [], [row], delivery_scope=bound,
        deliveries=[],
    )
    assert "LEG dispatch-delivery — ASSERTED" in out, out
    assert "examined: 1" in out, out
    assert "read at " in out, out
    assert rc == 1, f"a phantom dispatch is a problem, got rc={rc}\n{out}"

def test_the_dispatch_delivery_leg_DEFERS_the_store_read_until_there_is_a_row_to_judge() -> None:
    """#49: the store read is DEFERRED, and the not-read state is DISTINGUISHABLE from an
    empty one.

    TWO FACTS, and the second is the one that matters.

    (a) A leg with no post-boundary dispatch row must not touch the store AT ALL. The read
    is O(the whole box's message history) -- expensive enough that a leg scanning it before
    knowing whether it had anything to corroborate pays that cost to judge zero rows -- so
    every probe driving `main()` paid it again. That is
    what turned this file's own gate from well inside its budget into a TIMEOUT the moment
    the leg's boundary was declared. `deliveries_fn` here RAISES, so a leg that read the
    store anyway fails by exception rather than by a number nobody thought to assert.

    (b) `deliveries_read` is then None and NOT 0, because `0` would stand for both "the
    store held no delivery" and "the store was never opened" -- the confident zero this leg
    exists to refuse.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    old = _stall_row(72, "dispatch", "#70", 5, now=now, actor="triage")

    def _explode():
        raise AssertionError("the store must not be read when there is nothing to judge")

    deferred = RUNNER.dispatch_delivery_leg(
        [old], read_at=read_at, bound=bound, deliveries_fn=_explode,
    )
    assert deferred["status"] == "ASSERTED", deferred
    assert deferred["problems"] == [], deferred["problems"]
    assert deferred["coverage"]["store_read"] is False, deferred["coverage"]
    assert deferred["coverage"]["deliveries_read"] is None, deferred["coverage"]

    # ... and the SAME leg WITH a row to judge DOES read it, so the deferral is a deferral
    # and not a leg that has stopped reading at all. Without this arm, a leg that never read
    # the store would satisfy the first half just as well.
    fresh = _stall_row(73, "dispatch", "#71", 0, now=now - dt.timedelta(minutes=5),
                       actor="triage", refs=[{"session": _PROBE_TARGET}])
    read = RUNNER.dispatch_delivery_leg(
        [fresh], read_at=read_at, bound=bound,
        deliveries_fn=lambda: ([], ["probe-home"], []),
    )
    assert read["coverage"]["store_read"] is True, read["coverage"]
    assert read["coverage"]["deliveries_read"] == 0, read["coverage"]

def test_the_leg_RENDERS_a_store_it_never_opened_distinctly_from_one_that_held_nothing() -> None:
    """#49 acceptance (3): `deliveries read: 0` must not be the render of BOTH "the store
    held no delivery" and "the store was never opened".

    Asserted on the RENDER for the same reason the examined-population probe is: a state the
    leg records but never prints is a state no reader can act on.
    """
    now = dt.datetime.now(dt.timezone.utc)
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    old = _stall_row(74, "dispatch", "#72", 5, now=now, actor="triage")
    rc, out, _ = _run([], [old], delivery_scope=bound, deliveries=[])
    assert "LEG dispatch-delivery — ASSERTED" in out, out
    assert "deliveries: NOT READ" in out, out
    assert "deliveries read:" not in out, out
    assert "examined: 0" in out, out

def test_the_dispatch_delivery_leg_corroborates_ONLY_the_rows_OWN_target() -> None:
    """#425 clause 1: a delivery carrying the subject but addressed to a DIFFERENT lane is
    NOT corroboration of this dispatch row.

    The same subject is broadcast to several lanes, so a subject-only match clears a row
    whose actual target was never told -- the false-clean class. Both arms are asserted,
    because a leg that reported every row would pass the first alone and a leg that reported
    none would pass the second.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    dispatched = now - dt.timedelta(hours=1)
    row = _stall_row(52, "dispatch", "#78", 0, now=dispatched, actor="triage",
                     refs=[{"session": _PROBE_TARGET}])
    delivered_at = dispatched + dt.timedelta(seconds=60)
    notify = "[session-notify from=abc]\nDISPATCH #78 to the lane"

    # arm 1 — the notify names the SUBJECT but is addressed to a DIFFERENT target: the row
    # is a phantom, and the problem must NAME the target it actually routed to.
    other = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(delivered_at, notify, session="a-different-lane")],
            ["probe-home"], [],
        ),
    )
    named = "\n".join(other["problems"])
    assert other["status"] == "ASSERTED", other
    assert "n=52" in named and _PROBE_TARGET in named, (
        f"a subject match to the WRONG target must stay RED and name the real target\n{named}"
    )

    # arm 2 — the SAME delivery addressed to the ROW'S OWN target clears it. Without this
    # arm the first would pass a leg that matched nothing at all.
    same = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(delivered_at, notify, session=_PROBE_TARGET)],
            ["probe-home"], [],
        ),
    )
    assert same["problems"] == [], same["problems"]

def test_the_dispatch_delivery_leg_counts_a_ref_less_row_as_NOT_JUDGED() -> None:
    """#425 clause 1: a post-boundary dispatch row carrying no typed `session` ref is NOT
    JUDGED -- counted and printed, never CLEAN and never RED, nothing backfilled.

    The 19 rows that carry a target are the shape the write path now enforces; every row
    written before that refusal is immutable history, so judging it would be the permanent
    red #334 exists to stop. The bucket is asserted on BOTH the leg's coverage AND the
    render, because a count computed and dropped from the report is the same failure as one
    never computed -- and the zero it would otherwise show is the confident one.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    ref_less = _stall_row(101, "dispatch", "#100", 0, now=now - dt.timedelta(minutes=5),
                          actor="triage")

    leg = RUNNER.dispatch_delivery_leg(
        [ref_less], read_at=read_at, bound=bound,
        deliveries_fn=lambda: ([], ["probe-home"], []),
    )
    assert leg["status"] == "ASSERTED", leg
    assert leg["problems"] == [], (
        f"a ref-less row is NOT JUDGED, never RED\n{leg['problems']}"
    )
    assert leg["coverage"]["dispatch_rows_not_judged"] == 1, leg["coverage"]
    assert leg["coverage"]["dispatch_rows_examined"] == 0, leg["coverage"]
    # the store is not read, and the reason names the BUCKET rather than an empty window.
    assert leg["coverage"]["store_read"] is False, leg["coverage"]
    assert "NOT JUDGED" in (leg["coverage"]["store_not_read_reason"] or ""), leg["coverage"]

    rc, out, _ = _run([], [ref_less], delivery_scope=bound, deliveries=[])
    assert "LEG dispatch-delivery — ASSERTED" in out, out
    assert "1 carry no target, NOT JUDGED" in out, out
    assert "examined: 0" in out, out
    assert rc == 0, f"a ref-less row is not a problem, got rc={rc}\n{out}"

def _late_stamp_row(n: int, *, now: dt.datetime, subject: str = "#77",
                    declared: dt.datetime | None = None, days_ago: float = 1 / 24.0) -> dict:
    """A dispatch row whose `ts` is a WRITE instant LATER than the instant it declares (#432).

    The live specimen this shape is taken from: row `n=2787` (`#428`) carries
    `ts 2026-10-07T12:26:04Z` -- a batched ledger write -- while its own detail declares
    `resolved_at 2026-10-07T12:11:46Z`, and the notify it records landed at `12:11:28Z`. One
    fixture, because a window built from `ts` alone misses that delivery by 11m36s while a
    window built from the declaration contains it.
    """
    detail = "DISPATCH to the probe lane, resolved LIVE this turn"
    if declared is not None:
        detail += f" (resolved_at {declared.strftime('%Y-%m-%dT%H:%M:%SZ')})"
    return _stall_row(n, "dispatch", subject, days_ago, now=now, actor="triage",
                      detail=detail, refs=[{"session": _PROBE_TARGET}])

def test_the_dispatch_delivery_leg_reads_a_LATE_STAMP_by_the_instant_the_row_DECLARES() -> None:
    """#432, the specimen. A row's `ts` is a WRITE instant, so a batched ledger write stamps it
    AFTER the dispatch it records and a window built from it opens after a genuine delivery.

    BOTH ARMS, because either alone proves nothing: the row WITH its declared instant clears
    the delivery, and the SAME row with the declaration stripped reports a window mismatch --
    so the declaration is measured to be the thing that clears it, not a leg that stopped
    judging. The declared instant is 1 h before the write stamp and the notify lands on it.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    declared = now - dt.timedelta(hours=2)
    # `ts` = now - 1 h; the delivery sits on the DECLARED instant, 1 h before the write stamp
    # and 57 min before the window a `ts`-only anchor would open.
    declared_row = _late_stamp_row(111, now=now, declared=declared)
    deliveries = lambda: (
        [_delivery(declared, "[session-notify from=abc]\nDISPATCH #77 to the lane",
                   session=_PROBE_TARGET)],
        ["probe-home"], [],
    )

    cleared = RUNNER.dispatch_delivery_leg(
        [declared_row], read_at=read_at, bound=bound, deliveries_fn=deliveries,
    )
    assert cleared["problems"] == [], (
        f"the row's own declared instant must anchor the window (#432)\n{cleared['problems']}"
    )
    assert cleared["coverage"]["dispatch_rows_declared_anchor"] == 1, cleared["coverage"]
    assert cleared["coverage"]["dispatch_rows_examined"] == 1, cleared["coverage"]

    # ... AND THE DECLARATION IS WHAT CLEARS IT. The same fixture with the declaration removed
    # keeps the same `ts`, the same delivery and the same target, so a leg that cleared the
    # first arm by matching nothing at all would fail here.
    stripped = _late_stamp_row(112, now=now, declared=None)
    mismatch = RUNNER.dispatch_delivery_leg(
        [stripped], read_at=read_at, bound=bound, deliveries_fn=deliveries,
    )
    assert mismatch["coverage"]["dispatch_rows_declared_anchor"] == 0, mismatch["coverage"]
    assert mismatch["problems"], "without the declaration the delivery falls outside the window"
    assert "WINDOW MISMATCH" in mismatch["problems"][0], mismatch["problems"]

def _row_with_lag(n: int, *, ts: dt.datetime, lag_secs: float, subject: str = "#90") -> dict:
    """A dispatch row whose detail QUOTES `resolved_at` an exact LAG behind its write stamp.

    `ts` is written to the second and `days_ago=0`, so the lag is exact and the boundary pair
    below is a statement about the bound rather than about rounding.
    """
    declared = ts - dt.timedelta(seconds=lag_secs)
    return _stall_row(
        n, "dispatch", subject, 0, now=ts, actor="triage",
        detail="DISPATCH to the probe lane, resolved LIVE this turn "
               f"(resolved_at {declared.strftime('%Y-%m-%dT%H:%M:%SZ')})",
        refs=[{"session": _PROBE_TARGET}],
    )

def test_the_declared_instant_is_BOUNDED_so_a_QUOTED_token_declares_NOTHING() -> None:
    """#476: the declared-instant form is a PHRASE MATCH, so a row that QUOTES the token as
    evidence about a DIFFERENT artifact declares it as its own dispatch instant.

    The live specimen is row `n=3215` (#474's dispatch): its detail quotes the stale
    `registry/state.json` snapshot's `resolved_at 2026-10-05T13:01:19Z` as a MEASUREMENT, 8
    days before the row's own write stamp, and the #432 anchor rule built the judged window
    from that quote -- printing "records no delivery" for a dispatch that had landed one
    second BEFORE the row's stamp. `n=3226` repeated it within the hour, on the ruling lane's
    own next dispatch.

    BOTH ARMS, because either alone proves nothing: a mid-line declaration INSIDE the bound is
    still used as the anchor, and the SAME shape with a quoted instant BEYOND the bound falls
    back to `ts` -- where the delivery IS found. A bound that rejected every declaration would
    pass the second arm while silently disabling the #432 repair the first arm pins.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    ts = now - dt.timedelta(hours=1)

    # ARM 1 -- a DESIGNED declaration: 7200 s of lag, well inside the bound. It anchors the
    # window on the declared instant and clears a delivery that sits there.
    designed_at = ts - dt.timedelta(seconds=7200)
    used = RUNNER.dispatch_delivery_leg(
        [_row_with_lag(161, ts=ts, lag_secs=7200)], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(designed_at, "[session-notify from=abc]\nDISPATCH #90 to the lane",
                       session=_PROBE_TARGET)],
            ["probe-home"], [],
        ),
    )
    assert used["coverage"]["dispatch_rows_declared_anchor"] == 1, used["coverage"]
    assert used["problems"] == [], (
        f"a declaration inside the bound must still anchor the window (#432)\n{used['problems']}"
    )

    # ARM 2 -- the `n=3215` shape: the same row carrying a quoted instant 8 days back. It must
    # NOT become the anchor, and a delivery inside the `ts` window must be found.
    fell_back = RUNNER.dispatch_delivery_leg(
        [_row_with_lag(162, ts=ts, lag_secs=8 * 86400)], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(ts - dt.timedelta(seconds=60),
                       "[session-notify from=abc]\nDISPATCH #90 to the lane",
                       session=_PROBE_TARGET)],
            ["probe-home"], [],
        ),
    )
    assert fell_back["coverage"]["dispatch_rows_declared_anchor"] == 0, (
        f"a quote beyond the bound must fall back to the write stamp\n{fell_back['coverage']}"
    )
    assert fell_back["problems"] == [], (
        f"anchored on `ts`, the delivery lands inside the window\n{fell_back['problems']}"
    )

    # ... AND THE BOUND IS EXACT, not merely present: a lag 1 s inside it anchors on the
    # declaration, 1 s outside it falls back to `ts`. The arms above would pass under ANY
    # bound; this pair pins WHICH one.
    limit = RUNNER.DECLARED_INSTANT_MAX_LAG_SECS
    for n, lag, expected in ((163, limit - 1, 1), (164, limit + 1, 0)):
        leg = RUNNER.dispatch_delivery_leg(
            [_row_with_lag(n, ts=ts, lag_secs=lag)], read_at=read_at, bound=bound,
            deliveries_fn=lambda: ([], ["probe-home"], []),
        )
        assert leg["coverage"]["dispatch_rows_declared_anchor"] == expected, (
            f"a {lag} s lag must anchor={expected} against a {limit} s bound\n"
            f"{leg['coverage']}"
        )

def test_the_dispatch_delivery_leg_reports_a_WINDOW_MISMATCH_never_an_ABSENCE() -> None:
    """#432, the class. The leg carried ONE verdict for TWO conditions, so a delivery that
    exists but falls outside the window the leg chose read as "records no delivery" -- a FALSE
    ABSENCE that sends a reader off to re-dispatch an item the target already holds.

    A match is taken WITHOUT the window first, so the two conditions are distinguishable. The
    mismatch verdict must NAME the delivery's own instant and the window that judged it, and
    must NOT carry the absence's words -- a reader who greps for the absence text must not find
    it on a row whose delivery is sitting in the store.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    dispatched = now - dt.timedelta(hours=1)
    row = _stall_row(121, "dispatch", "#79", 0, now=dispatched, actor="triage",
                     refs=[{"session": _PROBE_TARGET}])
    # 2 h after the write stamp: past the 5400 s forward bound, so the window cannot hold it.
    landed_at = dispatched + dt.timedelta(hours=2)

    leg = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(landed_at, "[session-notify from=abc]\nDISPATCH #79 to the lane",
                       session=_PROBE_TARGET)],
            ["probe-home"], [],
        ),
    )
    assert leg["status"] == "ASSERTED", leg
    assert leg["problems"], "a delivery outside the window is still a finding"
    problem = leg["problems"][0]
    assert "WINDOW MISMATCH" in problem, problem
    assert "records no delivery" not in problem, (
        f"a delivery that EXISTS must never read as an absence\n{problem}"
    )
    assert landed_at.strftime("%Y-%m-%dT%H:%M:%SZ") in problem, (
        f"the mismatch must name the delivery's own instant\n{problem}"
    )
    assert "do not re-dispatch" in problem, problem

    # ... AND A TRUE ABSENCE STILL READS AS ONE, or the fix would have bought the mismatch
    # verdict by never reporting the absence it exists to catch.
    absent = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: ([], ["probe-home"], []),
    )
    assert absent["problems"], absent
    assert "records no delivery" in absent["problems"][0], absent["problems"]
    assert "WINDOW MISMATCH" not in absent["problems"][0], absent["problems"]

    # ... AND A DELIVERY ADDRESSED TO ANOTHER LANE IS STILL AN ABSENCE, not a mismatch: the
    # match is on the ROW'S OWN target (#425 clause 1), so a broadcast that never reached this
    # row's target must not be read as "it exists, just elsewhere".
    elsewhere = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(landed_at, "[session-notify from=abc]\nDISPATCH #79 to the lane",
                       session="a-different-lane")],
            ["probe-home"], [],
        ),
    )
    assert "records no delivery" in elsewhere["problems"][0], elsewhere["problems"]
    assert "WINDOW MISMATCH" not in elsewhere["problems"][0], elsewhere["problems"]

def test_declared_dispatch_instant_reads_only_a_NAMED_form() -> None:
    """#432: the row's `detail` is FREE PROSE, so a bare ISO instant is not a declaration.

    Measured on this ledger: 146 of 458 dispatch rows carry SOME ISO instant in their detail --
    a window, a neighbour's row stamp, a read instant. A reader that took any ISO string would
    anchor windows on whatever instant a row happened to quote, which is the `#425` class of
    predicate-wider-than-the-artifact. So each form pairs a TOKEN with its value, a value that
    does not parse declares nothing (and raises nothing: a malformed declaration is no
    declaration, never a licence to judge unbounded), and the EARLIER of the two wins.
    """
    now = dt.datetime.now(dt.timezone.utc)
    declared = (now - dt.timedelta(hours=2)).replace(microsecond=0)
    iso = declared.strftime("%Y-%m-%dT%H:%M:%SZ")

    # A named form declares ...
    instant, form = RUNNER.declared_dispatch_instant(
        {"detail": f"routed LIVE this turn (resolved_at {iso})."}
    )
    assert instant == declared and form == "resolved_at", (instant, form)

    # ... a bare ISO instant does NOT ...
    assert RUNNER.declared_dispatch_instant(
        {"detail": f"the window was [{iso}, later]"}
    ) == (None, "")
    # ... nor does a mention of the token with no value, nor a value that cannot be parsed ...
    assert RUNNER.declared_dispatch_instant(
        {"detail": "resolved_at was not recorded"}
    ) == (None, "")
    assert RUNNER.declared_dispatch_instant(
        {"detail": "resolved_at 2026-13-45T99:99:99Z"}
    ) == (None, "")
    # ... nor an empty or absent detail.
    assert RUNNER.declared_dispatch_instant({"detail": ""}) == (None, "")
    assert RUNNER.declared_dispatch_instant({}) == (None, "")

    # EARLIER WINS: a declaration AFTER the write stamp cannot pull the window forward, so the
    # leg keeps the write stamp as the anchor and the later instant is simply not used.
    now2 = dt.datetime.now(dt.timezone.utc)
    read_at = now2.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now2 - dt.timedelta(days=1), "probe-bound", "")
    forward = _stall_row(
        131, "dispatch", "#81", 1 / 24.0, now=now2, actor="triage",
        detail=f"resolved_at {(now2 + dt.timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        refs=[{"session": _PROBE_TARGET}],
    )
    leg = RUNNER.dispatch_delivery_leg(
        [forward], read_at=read_at, bound=bound,
        deliveries_fn=lambda: ([], ["probe-home"], []),
    )
    assert leg["coverage"]["dispatch_rows_declared_anchor"] == 0, (
        f"a declaration AFTER the write stamp must not become the anchor\n{leg['coverage']}"
    )

def test_the_render_PRINTS_the_anchor_each_window_was_built_from() -> None:
    """#432: a window built from a row's WRITE stamp and one built from an instant the row
    DECLARES are different judgements. A reader who cannot tell which was used cannot tell a
    clean sweep from a narrow window, so the anchor counts are printed beside the verdict --
    the same discipline as the examined population (acceptance criterion 3, #116).
    """
    now = dt.datetime.now(dt.timezone.utc)
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    declared = now - dt.timedelta(hours=2)
    row = _late_stamp_row(141, now=now, declared=declared)
    rc, out, _ = _run([], [row], delivery_scope=bound, deliveries=[])
    assert "LEG dispatch-delivery — ASSERTED" in out, out
    assert "window anchors: 1 of 1 examined row(s) anchored on an instant the row itself DECLARES" in out, out
    # ... and the window line states which anchor was used, not just the count.
    assert "anchored on the row's declared `resolved_at`" in out, out

def test_the_match_HORIZON_keeps_an_OLD_mention_from_reading_as_a_DELIVERY() -> None:
    """#432: the horizon separates a DELIVERY from a subject MENTION, and both arms are needed.

    Measured on this ledger at the 2026-10-07T15:36Z read: the `#432` target held **47**
    messages carrying the subject, the oldest `2026-09-19T08:29:00Z` -- 18 days before the
    read -- and only **3** within 24 h. Without a horizon, the first of those 47 reads as "a
    delivery EXISTS, just outside the window", which is the false-CLEAN twin of the false
    absence this item is about: a leg that answered "it was delivered, only not then" for
    every stale mention would clear a row whose notify was never sent. So a match outside the
    horizon is NOT a delivery, and a true absence is still reported as one.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    dispatched = now - dt.timedelta(hours=1)
    row = _stall_row(151, "dispatch", "#83", 0, now=dispatched, actor="triage",
                     refs=[{"session": _PROBE_TARGET}])

    # ARM 1 -- an 18-day-old mention to the SAME target carrying the SAME subject is not a
    # delivery: it is a stale broadcast, and the row still records no delivery of THIS brief.
    stale_at = dispatched - dt.timedelta(days=18)
    stale = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(stale_at, "[session-notify from=abc]\nDISPATCH #83 to the lane",
                       session=_PROBE_TARGET)],
            ["probe-home"], [],
        ),
    )
    assert stale["coverage"]["subject_matches_anywhere"] == 1, stale["coverage"]
    assert stale["coverage"]["subject_matches_within_horizon"] == 0, stale["coverage"]
    assert stale["problems"], "a mention outside the horizon is not a delivery"
    assert "records no delivery" in stale["problems"][0], stale["problems"]
    assert "WINDOW MISMATCH" not in stale["problems"][0], (
        f"an 18-day-old mention must never read as a delivery\n{stale['problems']}"
    )

    # ARM 2 -- the SAME row with the mention 2 h after the write stamp is INSIDE the horizon
    # and outside the 5400 s window, so it is a WINDOW MISMATCH. Same subject, same target,
    # same fixture: only the age moved, so the horizon is measured to be the discriminator.
    near_at = dispatched + dt.timedelta(hours=2)
    near = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(near_at, "[session-notify from=abc]\nDISPATCH #83 to the lane",
                       session=_PROBE_TARGET)],
            ["probe-home"], [],
        ),
    )
    assert near["coverage"]["subject_matches_anywhere"] == 1, near["coverage"]
    assert near["coverage"]["subject_matches_within_horizon"] == 1, near["coverage"]
    assert "WINDOW MISMATCH" in near["problems"][0], near["problems"]

    # ... AND THE HORIZON IS BOUNDED, not merely present: a mention 1 s inside it is a
    # delivery and one 1 s outside it is not, so a leg that ignored the bound entirely would
    # fail the pair above while a leg that used ANY bound would still have to pass this one.
    horizon = RUNNER.DELIVERY_MATCH_HORIZON_SECS
    just_in = dispatched + dt.timedelta(seconds=horizon - 1)
    just_out = dispatched + dt.timedelta(seconds=horizon + 1)
    inside = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(just_in, "[session-notify from=abc]\nDISPATCH #83 to the lane",
                       session=_PROBE_TARGET)],
            ["probe-home"], [],
        ),
    )
    outside = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(just_out, "[session-notify from=abc]\nDISPATCH #83 to the lane",
                       session=_PROBE_TARGET)],
            ["probe-home"], [],
        ),
    )
    assert inside["coverage"]["subject_matches_within_horizon"] == 1, inside["coverage"]
    assert "WINDOW MISMATCH" in inside["problems"][0], inside["problems"]
    assert outside["coverage"]["subject_matches_within_horizon"] == 0, outside["coverage"]
    assert "records no delivery" in outside["problems"][0], outside["problems"]

def test_the_render_PRINTS_the_match_counts_the_horizon_judged() -> None:
    """#432: the horizon decides silently whether a mention is a delivery, so its effect is
    PRINTED -- `N within the horizon of M anywhere` -- and the reader can see how many
    mentions were set aside. A count that appears only when the horizon clears everything is a
    number a reader cannot distinguish from a store that held nothing (#116, criterion 3).
    """
    now = dt.datetime.now(dt.timezone.utc)
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    dispatched = now - dt.timedelta(hours=1)
    row = _stall_row(161, "dispatch", "#85", 0, now=dispatched, actor="triage",
                     refs=[{"session": _PROBE_TARGET}])
    stale = _delivery(dispatched - dt.timedelta(days=18),
                      "[session-notify from=abc]\nDISPATCH #85 to the lane",
                      session=_PROBE_TARGET)
    near = _delivery(dispatched + dt.timedelta(hours=2),
                     "[session-notify from=abc]\nDISPATCH #85 to the lane",
                     session=_PROBE_TARGET)
    rc, out, _ = _run([], [row], delivery_scope=bound, deliveries=[stale, near])
    assert "LEG dispatch-delivery — ASSERTED" in out, out
    assert (
        f"subject matches: 1 within the {RUNNER.DELIVERY_MATCH_HORIZON_SECS} s horizon of 2 "
        f"anywhere in the store(s)"
    ) in out, out

def test_a_BODY_only_mention_is_a_MENTION_and_NEVER_corroboration() -> None:
    """#433: a message that DISCUSSES the subject does not clear a dispatch row.

    The false-CLEAN twin of #432's false absence. A lane's store is full of messages carrying
    the unit's token -- compaction summaries quoting the task list, rulings quoting the row
    under discussion -- and a whole-text match lets any one of them clear a row whose brief was
    never routed. The token belongs in the delivery's HEADER, because that is where a delivery
    NAMES what it routes.

    THREE assertions, because a fix that overshot would pass two of them: the row is NAMED, it
    reads as a MENTION, and it does NOT read as an absence -- the text IS there, and calling it
    "records no delivery" would be a lie in the opposite direction.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    dispatched = now - dt.timedelta(hours=1)
    row = _stall_row(181, "dispatch", "#91", 0, now=dispatched, actor="triage",
                     refs=[{"session": _PROBE_TARGET}])
    leg = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(dispatched + dt.timedelta(seconds=60),
                       "[session-notify from=abc]\nTriage cycle report\n\n"
                       "queued for this lane: #91, #92",
                       session=_PROBE_TARGET)],
            ["probe-home"], [],
        ),
    )
    named = "\n".join(leg["problems"])
    assert leg["coverage"]["dispatch_rows_corroborated"] == 0, leg["coverage"]
    assert leg["coverage"]["subject_matches_anywhere"] == 1, leg["coverage"]
    assert leg["coverage"]["subject_matches_within_horizon"] == 0, leg["coverage"]
    assert leg["coverage"]["subject_mentions_body_only"] == 1, leg["coverage"]
    assert "n=181" in named and "#91" in named, f"the row must be NAMED\n{named}"
    assert "MENTION" in named, f"a body-only match reads as a MENTION\n{named}"
    assert "corroborated by NO delivery" in named, named
    assert "records no delivery" not in named, (
        f"a body mention is not an absence -- the text IS there\n{named}"
    )

def test_a_HEADER_match_still_clears_the_row_when_the_body_mentions_it_too() -> None:
    """#433, the specimen's own shape: `#428`'s dispatch row carried its subject at offset 78
    (the header) and again at offset 868 (a queue list in the body).

    A fix that scoped the match to "the first occurrence" or to "not the body" would redden
    this row -- the one whose delivery genuinely woke the lane. The discriminator is WHERE the
    token sits, never WHICH occurrence is found first.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    dispatched = now - dt.timedelta(hours=1)
    row = _stall_row(182, "dispatch", "#93", 0, now=dispatched, actor="triage",
                     refs=[{"session": _PROBE_TARGET}])
    leg = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(dispatched + dt.timedelta(seconds=60),
                       "[session-notify from=abc]\nTRIAGE DISPATCH — #93\n\n"
                       "queued for this lane: #93, #94",
                       session=_PROBE_TARGET)],
            ["probe-home"], [],
        ),
    )
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["dispatch_rows_corroborated"] == 1, leg["coverage"]
    assert leg["coverage"]["subject_mentions_body_only"] == 0, leg["coverage"]

def test_a_body_mention_addressed_to_a_DIFFERENT_target_is_still_an_ABSENCE() -> None:
    """#425 clause 1, re-asserted under the #433 split: a mention on ANOTHER lane is neither
    corroboration nor a mention OF THIS DISPATCH.

    The subject is broadcast to several lanes, so a body match on a different target must stay
    an absence -- otherwise the header fix would have widened the predicate it was meant to
    narrow.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    dispatched = now - dt.timedelta(hours=1)
    row = _stall_row(183, "dispatch", "#95", 0, now=dispatched, actor="triage",
                     refs=[{"session": _PROBE_TARGET}])
    leg = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(dispatched + dt.timedelta(seconds=60),
                       "[session-notify from=abc]\nTriage cycle report\n\nqueued: #95",
                       session="another-lane")],
            ["probe-home"], [],
        ),
    )
    named = "\n".join(leg["problems"])
    assert "records no delivery" in named, named
    assert "MENTION" not in named, f"another lane's mention is not this dispatch's\n{named}"
    assert leg["coverage"]["subject_mentions_body_only"] == 0, leg["coverage"]

def test_a_body_mention_beyond_the_horizon_is_counted_but_not_a_MENTION() -> None:
    """#433 horizon arm: the MENTION verdict is bounded exactly as a delivery match is.

    An 18-day-old compaction summary quoting the unit is not evidence that a briefing reached
    the target, so it must not become a second route to a confident near-verdict. It is still
    COUNTED (`..._anywhere`), because a count that vanished would be indistinguishable from a
    store that held nothing (#116).
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    dispatched = now - dt.timedelta(hours=1)
    row = _stall_row(184, "dispatch", "#96", 0, now=dispatched, actor="triage",
                     refs=[{"session": _PROBE_TARGET}])
    leg = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(dispatched - dt.timedelta(days=18),
                       "[session-notify from=abc]\nTriage cycle report\n\nqueued: #96",
                       session=_PROBE_TARGET)],
            ["probe-home"], [],
        ),
    )
    named = "\n".join(leg["problems"])
    assert leg["coverage"]["subject_mentions_body_only"] == 1, leg["coverage"]
    assert leg["coverage"]["subject_mentions_body_only_within_horizon"] == 0, leg["coverage"]
    assert "records no delivery" in named, named
    assert "MENTION" not in named, f"an 18-day-old mention is not a near-mention\n{named}"

def test_delivery_header_skips_the_envelope_and_reads_the_line_the_SENDER_wrote() -> None:
    """#433: the header is the sender's first NON-BLANK line, with the harness's envelope
    skipped.

    The envelope (`[session-notify from=<uuid>]`, `📨 notify from <short-id>:`) is added by the
    transport, not written by the lane that routed the brief, so counting it as the header line
    would scope the match to a line no sender controls. Both declared forms are exercised, and
    the blank line between envelope and body is what the skip exists for.
    """
    assert RUNNER.delivery_header(
        "[session-notify from=abc]\n\nTRIAGE DISPATCH — #94\nqueued: #94"
    ) == "TRIAGE DISPATCH — #94"
    assert RUNNER.delivery_header(
        "📨 notify from abc123:\nDISPATCH #94 to the Worker\nbody: #94"
    ) == "DISPATCH #94 to the Worker"

def test_the_render_PRINTS_the_header_and_body_split() -> None:
    """#433: the split is PRINTED, because it IS the verdict.

    "subject matches: 1 within the horizon of 1 anywhere" was true of the #433 specimen and
    said nothing about whether the match corroborated -- the reader needs "of the rows
    examined, how many a HEADER match cleared" beside "how many body-only mentions were set
    aside", or a green line cannot be told from a row cleared by a mention.
    """
    now = dt.datetime.now(dt.timezone.utc)
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    dispatched = now - dt.timedelta(hours=1)
    row = _stall_row(185, "dispatch", "#97", 0, now=dispatched, actor="triage",
                     refs=[{"session": _PROBE_TARGET}])
    mention = _delivery(dispatched + dt.timedelta(seconds=60),
                        "[session-notify from=abc]\nTriage cycle report\n\nqueued: #97",
                        session=_PROBE_TARGET)
    rc, out, _ = _run([], [row], delivery_scope=bound, deliveries=[mention])
    assert "LEG dispatch-delivery — ASSERTED" in out, out
    assert "subject matches in a delivery HEADER:" in out, out
    assert "body-only mention(s)" in out, out


def _messages_db(path: Path, *messages: tuple[str, str]) -> None:
    """A throwaway OpenCrabs home holding real `messages` rows — the landed-notify read path.

    `box_deliveries` consumes the header form in its SQL `like` clause, so a probe that
    injected delivery DICTS would pass whichever header it was handed and prove nothing about
    the predicate. This builds the SHAPE the live box has and reads it through the runner's
    own function (#426).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "create table messages "
        "(session_id text, role text, content text, created_at integer)"
    )
    conn.execute(
        "create table notify_queue "
        "(session_id text, display_text text, context_text text, created_at integer)"
    )
    stamp = int(dt.datetime.now(dt.timezone.utc).timestamp())
    conn.executemany(
        "insert into messages (session_id, role, content, created_at) values (?,?,?,?)",
        [(session, "user", text, stamp) for session, text in messages],
    )
    conn.commit()
    conn.close()

def test_box_deliveries_reads_BOTH_harness_header_forms() -> None:
    """#426: the harness writes TWO landed-notify header forms, and the leg matched only one.

    Measured live before the fix: four dispatch rows (n=2749-2752) read RED because their
    notifies landed in the emoji form and the read saw none. Both forms are asserted here, so
    the probe fails if the predicate narrows back to a single header — and a QUOTED header is
    asserted NOT to count, so the fix cannot be a bare `notify from` substring (rule 7).
    """
    root = Path(tempfile.mkdtemp()) / "profiles"
    # The live box's SHAPE: a default home beside a profile root, both read.
    _messages_db(root.parent / "opencrabs.db")
    _messages_db(
        root / "ops" / "opencrabs.db",
        ("probe-session", "📨 notify from abc12345:\nDISPATCH #77 to the Worker"),
        ("probe-session", "[session-notify from=abc]\nDISPATCH #78 to the Worker"),
        ("probe-session", "a report QUOTING `notify from abc` must not read as landed"),
    )
    deliveries, _homes_read, unreached = RUNNER.box_deliveries(root)
    assert unreached == [], unreached
    texts = [d["text"] for d in deliveries if d["state"] == "landed"]
    assert any(t.startswith("📨 notify from ") for t in texts), (
        f"the EMOJI form must read as landed\n{texts}"
    )
    assert any(t.startswith("[session-notify from=") for t in texts), (
        f"the BRACKETED form must still read as landed\n{texts}"
    )
    assert not any("QUOTING" in t for t in texts), (
        f"a QUOTED header is not a delivery (reader-echo class, rule 7)\n{texts}"
    )

# --- the criterion-path leg (#48) --------------------------------------------------------
#
# Candidate 1 of the #48 ruling closes the LAW-surface half — a law sentence naming a
# mechanism that does not exist — but it cannot reach two surfaces, because neither is in a
# commit: a BOARD ISSUE BODY and a SESSION PLAN. Measured instances: `#172`'s acceptance
# criterion named `tools/questions` (which resolves nowhere — the instrument ships only at
# `TEMPLATE/tools/questions`); `#96`'s plan criterion named a test file that existed under no
# revision. The patrol already reads the board, so this leg resolves the paths a criterion
# names. Its whole population is a name that resolves to NOTHING, so a probe that only read a
# clean board would prove nothing — the probes below supply the defect and assert the leg
# names it.

def _issue_with_body(number: int, state: str, body: str) -> dict:
    """A board issue carrying a BODY, in the shape `gh issue list --json` returns."""
    issue = _issue(number, state)
    issue["body"] = body
    return issue

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


def _criterion_tree_pair(*paths: str) -> tuple[Path, Path]:
    """TWO checkouts of ONE repository, both holding the named paths in their COMMITTED tree.

    The pair is what makes reader-independence provable (#450 acceptance): the checkouts
    share a commit, so any difference in their verdicts can only come from something
    OUTSIDE that commit — which is exactly the working-tree leak the defect reports.
    """
    root = Path(tempfile.mkdtemp(prefix="criterion-pair-"))
    main = _git_init(root / "main")
    for rel in paths:
        target = main / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("probe\n", encoding="utf-8")
    _git(main, "add", "-A")
    _git(main, "commit", "-q", "--allow-empty", "-m", "probe tree")
    linked = root / "linked"
    _git(main, "worktree", "add", "-q", str(linked))
    return main, linked

def _criterion_leg(issues, *, repo, rev="HEAD", read_at=_CLOSE_TS, exemptions_path=None):
    """Drive the criterion-path leg with an exemption store that is NEVER the live one (#507).

    The leg now reads a DECLARED store, and an entry matching no live absence is a PROBLEM —
    so a probe that let the leg fall to its default would red on this factory's own entries
    (which name paths no fixture mentions) and would be asserting this box's adjudications
    rather than the leg's behaviour. Every probe here therefore passes the never-created
    sentinel unless it is the probe that asserts the store itself.
    """
    return RUNNER.criterion_path_leg(
        issues, read_at=read_at, repo=repo, rev=rev,
        exemptions_path=(
            _NO_CRITERION_EXEMPTIONS if exemptions_path is None else exemptions_path
        ),
    )

def test_the_criterion_path_leg_RESOLVES_a_named_path_and_states_its_population() -> None:
    """The clean arm, WITH its population — `examined 0` must not render as `examined 1`."""
    issues = [_issue_with_body(11, "OPEN", "Done when `tools/probe.py` exists.")]
    tree = _criterion_tree("tools/probe.py")
    leg = _criterion_leg(issues, read_at=_CLOSE_TS, repo=tree)
    assert leg["problems"] == [], leg["problems"]
    assert leg["name"] == "criterion-paths", leg["name"]
    assert leg["coverage"]["refs_examined"] == 1, leg["coverage"]
    assert leg["coverage"]["issues_read"] == 1, leg["coverage"]
    assert leg["coverage"]["read_at"] == _CLOSE_TS, leg["coverage"]

def test_the_criterion_path_leg_BITES_on_a_path_that_resolves_to_nothing() -> None:
    """#48 acceptance (3), the NON-VACUITY probe: the defect is a criterion naming a path the
    tree does not hold, and the finding must NAME the path, the issue AND the surface — the
    `#148` discipline: a finding that cannot be dispatched is not a finding."""
    issues = [_issue_with_body(96, "OPEN", "Acceptance: `tests/test_ghost.py` passes.")]
    tree = _criterion_tree("tools/probe.py")
    leg = _criterion_leg(issues, read_at=_CLOSE_TS, repo=tree)
    assert leg["problems"], "a criterion naming an absent path must be reported"
    problem = leg["problems"][0]
    assert "#96" in problem, problem
    assert "body" in problem, problem
    assert "`tests/test_ghost.py`" in problem, problem
    assert _CLOSE_TS in problem, problem
    assert "dispatch a work item" in problem, problem

def test_the_criterion_path_leg_reads_the_RULING_comment_through_the_SHARED_predicate() -> None:
    """An HQ ruling carries the numbered acceptance criteria, and it is the item's contract.
    The read binds to the SHARED `ruling_comments` predicate, never a private copy of it —
    the same binding the `board-ruling` leg asserts, for the same reason."""
    issues = [_issue_with_comments(
        172, "OPEN", "## RULED — acceptance: `tools/questions` exists.\n"
    )]
    tree = _criterion_tree("tools/probe.py")
    leg = _criterion_leg(issues, read_at=_CLOSE_TS, repo=tree)
    assert leg["problems"], "a criterion named in a ruling must be judged"
    assert "ruling comment" in leg["problems"][0], leg["problems"][0]
    assert "`tools/questions`" in leg["problems"][0], leg["problems"][0]

def test_the_criterion_path_leg_does_NOT_judge_a_CLOSE_or_discussion_comment() -> None:
    """A close comment narrates what happened; it obliges nothing. Measured on the live board
    (2026-10-06): judging every comment read 1696 refs and 67 findings against 227 and 18 for
    the two obligation surfaces — the extra 49 were chatter, not criteria."""
    issue = _issue_with_body(55, "OPEN", "See `docs/real.md`.")
    issue["comments"] = [
        {"body": "## CLOSED — delivered; `tests/test_gone.py` was renamed.",
         "author": {"login": "hq"}, "createdAt": _CLOSE_TS},
    ]
    tree = _criterion_tree("docs/real.md")
    leg = _criterion_leg([issue], read_at=_CLOSE_TS, repo=tree)
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["refs_examined"] == 1, leg["coverage"]

def test_the_criterion_path_leg_resolves_a_TEMPLATE_prefixed_name_as_the_shipped_twin() -> None:
    """The law writes a shipped path with its `TEMPLATE/` prefix, and that is the path that
    must resolve — a reader that stripped the prefix would resolve a name the law never
    writes."""
    issues = [_issue_with_body(
        37, "OPEN", "Ship `TEMPLATE/docs/quality-criteria.md` beside the donor's copy."
    )]
    present = _criterion_tree("TEMPLATE/docs/quality-criteria.md")
    assert _criterion_leg(
        issues, read_at=_CLOSE_TS, repo=present
    )["problems"] == []
    absent = _criterion_tree("docs/quality-criteria.md")
    leg = _criterion_leg(issues, read_at=_CLOSE_TS, repo=absent)
    assert leg["problems"], "the `TEMPLATE/`-prefixed name must be judged as written"
    assert "`TEMPLATE/docs/quality-criteria.md`" in leg["problems"][0], leg["problems"][0]

def test_the_criterion_path_leg_does_NOT_judge_a_token_that_is_not_a_FILE() -> None:
    """The predicate that separates a name from a lookalike, each shape measured on this
    board: an ellipsis standing for "the docs", a DIRECTORY, a dotted ATTRIBUTE chain, a
    transient lock file. All four read as absent mechanisms and none of them is one, and a
    gate whose findings are mostly artefacts of its own predicate is a gate nothing can act
    on."""
    issues = [_issue_with_body(
        21, "OPEN",
        "See `docs/...`, `registry/topics/`, `tools/field_predicate.split_canonical_run` "
        "and `evidence/.ledger.lock`; the real name is `docs/real.md`.",
    )]
    tree = _criterion_tree("docs/real.md")
    leg = _criterion_leg(issues, read_at=_CLOSE_TS, repo=tree)
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["refs_examined"] == 1, (
        f"only the file-shaped name is in the population: {leg['coverage']}"
    )

def test_the_criterion_path_leg_JUDGES_a_bare_mechanism_name_with_no_extension() -> None:
    """`tools/questions` is the ruling's OWN measured instance, and it carries no extension —
    an executable the kit ships as a bare name. A predicate keyed only on known extensions
    would drop exactly the instance the class was filed for."""
    assert RUNNER.is_mechanism_path("tools/questions") is True
    assert RUNNER.is_mechanism_path("TEMPLATE/tools/questions") is True
    assert RUNNER.is_mechanism_path("tests/test_x.py") is True
    assert RUNNER.is_mechanism_path("docs/...") is False
    assert RUNNER.is_mechanism_path("registry/topics/") is False
    assert RUNNER.is_mechanism_path("tools/a.b_c") is False
    assert RUNNER.is_mechanism_path("evidence/.ledger.lock") is False

def test_the_criterion_path_leg_EXCLUDES_a_CLOSED_item_and_PRINTS_the_exclusion() -> None:
    """Only an OPEN item can still send a lane at a missing file — that is the whole harm
    this class names. A closed item's obligation is discharged or abandoned, so its refs are
    outside the population; the count is PRINTED rather than silently dropped."""
    issues = [
        _issue_with_body(31, "CLOSED", "Acceptance: `tests/test_ghost.py` passes."),
        _issue_with_body(32, "OPEN", "Acceptance: `tools/probe.py` exists."),
    ]
    tree = _criterion_tree("tools/probe.py")
    leg = _criterion_leg(issues, read_at=_CLOSE_TS, repo=tree)
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["issues_read"] == 1, leg["coverage"]
    assert leg["coverage"]["closed_items_excluded"] == 1, leg["coverage"]
    assert leg["coverage"]["refs_examined"] == 1, leg["coverage"]

def test_the_criterion_path_leg_is_WIRED_into_the_run_and_PRINTS_its_population() -> None:
    """Wiring and render, asserted through `main()`: a leg built but never listed is a leg
    that never runs, and a leg that runs but never prints its population reads as one that
    examined everything and found it clean."""
    issues = [_issue_with_body(172, "OPEN", "Acceptance: `tools/questions` exists.")]
    # The `ruling` row is not decoration: an OPEN item with an intake row and no ruling row is
    # a `board-unruled` miss, so a fixture that isolates THIS leg's verdict must be a board the
    # round has otherwise swept clean.
    rows = _rows(("intake", "#172", 1), ("ruling", "#172", 2))
    rc, out, _ = _run(
        issues, rows, criterion_repo=_criterion_tree("tools/probe.py")
    )
    assert "LEG criterion-paths — ASSERTED" in out, out
    assert "1 reference(s) examined over 1 issue(s), 1 unresolved" in out, out
    assert rc == 1, f"an unresolved criterion path must fail the run\n{out}"
    assert "verdict: 1 problem(s)" in out, (
        f"the criterion path must be the ONLY problem this board carries\n{out}"
    )

def test_the_criterion_path_leg_reads_a_CLEAN_board_clean_and_says_what_it_read() -> None:
    """The complement: the leg is discriminating, not a blanket red — and its clean render
    still carries the population it examined."""
    issues = [_issue_with_body(11, "OPEN", "Done when `tools/probe.py` exists.")]
    rows = _rows(("intake", "#11", 1), ("ruling", "#11", 2))
    rc, out, _ = _run(
        issues, rows, criterion_repo=_criterion_tree("tools/probe.py")
    )
    assert rc == 0, f"a resolvable criterion must not fail the run\n{out}"
    assert "1 reference(s) examined over 1 issue(s), 0 unresolved" in out, out


def test_the_criterion_path_leg_reads_the_COMMIT_never_the_WORKING_TREE() -> None:
    """#450 acceptance: two checkouts of ONE repository, the same board, the same commit —
    and one of them carries an UNTRACKED `evidence/publish-receipt.json` on disk.

    The verdicts must be IDENTICAL. Reproduced on the live board at `ea882c48`: 18
    unresolved with the receipt present against 21 without, and the 3-ref delta was exactly
    the publish-receipt refs — the reader's own working tree deciding the verdict. The
    consequence is EXPECTED, not suppressed: since #445 moved the receipt to the git common
    dir, the path is in no commit, so BOTH checkouts name it.
    """
    issues = [_issue_with_body(
        11, "OPEN", "Acceptance: `evidence/publish-receipt.json` is written by the pusher."
    )]
    reader, sibling = _criterion_tree_pair("docs/real.md")
    receipt = reader / "evidence" / "publish-receipt.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text('{"sha": "probe"}\n', encoding="utf-8")
    with_receipt = _criterion_leg(issues, read_at=_CLOSE_TS, repo=reader)
    without = _criterion_leg(issues, read_at=_CLOSE_TS, repo=sibling)
    assert with_receipt["problems"] == without["problems"], (
        "a working-tree file must not move the verdict\n"
        f"with: {with_receipt['problems']}\nwithout: {without['problems']}"
    )
    assert with_receipt["problems"], (
        "the path is in NO commit, so both checkouts must name it — a clean verdict here "
        "would mean the leg read the disk"
    )
    assert with_receipt["coverage"]["read_rev"] == without["coverage"]["read_rev"], (
        "the two checkouts share a commit, so they must read the SAME revision"
    )


def test_the_criterion_path_leg_is_NOT_RUN_when_the_revision_cannot_be_RESOLVED() -> None:
    """A reader that cannot resolve the reading revision says so — never a clean sweep.

    `examined 0` and "every named path resolves" are the same render when the instrument
    never ran, and telling them apart is what template-instruments.md §7.5 exists for. A plain directory has no
    commit to read, so it is NOT RUN over its reason rather than a board's worth of paths
    read ABSENT because git could not run.
    """
    issues = [_issue_with_body(11, "OPEN", "Done when `tools/probe.py` exists.")]
    plain = Path(tempfile.mkdtemp(prefix="criterion-notrepo-"))
    leg = _criterion_leg(issues, read_at=_CLOSE_TS, repo=plain)
    assert leg["status"] == "NOT RUN", leg["status"]
    assert leg["problems"] == [], leg["problems"]
    assert "could not be resolved" in leg["coverage"]["reason"], leg["coverage"]
    # And it must RENDER as NOT RUN, not as a clean leg: the status is printed, not inferred.
    rows = _rows(("intake", "#11", 1), ("ruling", "#11", 2))
    rc, out, _ = _run(issues, rows, criterion_repo=plain)
    assert "NOT RUN:" in out, out


def test_the_criterion_path_leg_PRINTS_the_revision_it_read() -> None:
    """The revision is part of the verdict: "0 unresolved" is a claim about a COMMIT, and a
    reader who cannot see WHICH commit cannot reproduce it (#450's honesty half, template-instruments.md §7.5)."""
    issues = [_issue_with_body(11, "OPEN", "Done when `tools/probe.py` exists.")]
    rows = _rows(("intake", "#11", 1), ("ruling", "#11", 2))
    tree = _criterion_tree("tools/probe.py")
    rc, out, _ = _run(issues, rows, criterion_repo=tree)
    assert rc == 0, out
    assert "judged against the tree at" in out, out
    head, _why = RUNNER.committed_tree_rev(tree)
    assert head and head[:12] in out, (
        f"the render must name the commit it read ({head})\n{out}"
    )

# ---------------------------------------------------------------------------------------
# score-conversion (#67). The statute asserted the conversion happened "automatically";
# no trigger carried it, so a regression could sit unanswered in the newest survey and
# nothing would say so. The repair is a JOIN -- the RUN declares, the leg READS -- and
# these probes pin the join's four edges: a regression with no answering row is a FINDING
# that names the factory (#148); a row naming THAT artifact answers it; a row naming a
# DIFFERENT round does not, because the token names an artifact and not a factory; and an
# (UNM) cell is EXCLUDED rather than scored, because `0 (UNM)` under a floor of 3 would
# make every round read as a regression (ruling n=2747) and teach the next reader to
# ignore the leg.
# ---------------------------------------------------------------------------------------

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

def test_the_score_conversion_leg_NAMES_each_regression_and_PRINTS_its_population() -> None:
    directory = _scores_dir(_score_artifact(total=70, cells=["2", "4"]))
    leg = RUNNER.score_conversion_leg(
        [_non_conversion_row()], read_at="probe", scores_dir=directory
    )
    assert leg["status"] == "ASSERTED", leg
    cov = leg["coverage"]
    assert cov["artifact"] == "evidence/scores/2026-10-10.md", cov
    assert cov["factories"] == 1, cov
    assert cov["criteria_cells"] == 2, cov
    assert cov["regressions"] == ["Probe factory"], cov
    assert cov["conversion_rows"] == 0, cov
    assert cov["unanswered"] == ["Probe factory"], cov
    assert len(leg["problems"]) == 1, leg["problems"]
    # The finding NAMES the factory and the cell: a count cannot be dispatched (#148).
    assert "Probe factory" in leg["problems"][0], leg["problems"]
    assert "D1 2" in leg["problems"][0], leg["problems"]

def test_the_score_conversion_leg_is_ANSWERED_by_a_row_naming_THAT_artifact() -> None:
    directory = _scores_dir(_score_artifact(total=70, cells=["2", "4"]))
    rows = [_conversion_row("evidence/scores/2026-10-10.md")]
    leg = RUNNER.score_conversion_leg(rows, read_at="probe", scores_dir=directory)
    assert leg["status"] == "ASSERTED", leg
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["answered"] == ["#67"], leg["coverage"]
    # ... and the coverage field must say what `problems` says. A row list still naming
    # every regression `unanswered` beside an empty problems list is two surfaces
    # disagreeing about one fact.
    assert leg["coverage"]["unanswered"] == [], leg["coverage"]
    assert leg["coverage"]["conversion_rows"] == 1, leg["coverage"]

def test_a_row_naming_a_DIFFERENT_round_does_not_answer_this_one() -> None:
    # The join is on the exact artifact path: `converted_from` names a ROUND, never a
    # factory, so a row converting the previous round leaves this round unanswered.
    directory = _scores_dir(_score_artifact(total=70, cells=["2", "4"]))
    rows = [_conversion_row("evidence/scores/2026-10-09.md")]
    leg = RUNNER.score_conversion_leg(rows, read_at="probe", scores_dir=directory)
    assert leg["status"] == "ASSERTED", leg
    assert len(leg["problems"]) == 1, leg["problems"]
    assert leg["coverage"]["answered"] == [], leg["coverage"]
    assert leg["coverage"]["conversion_rows"] == 1, leg["coverage"]

def test_the_score_conversion_leg_NEVER_scores_an_unmeasurable_cell() -> None:
    # `0 (UNM)` is an EXCLUDED cell (ruling n=2747), not a zero. Scored, every round
    # would read as a regression and the leg would be ignored rather than fixed.
    directory = _scores_dir(_score_artifact(total=70, cells=["0 (UNM)", "4"]))
    leg = RUNNER.score_conversion_leg(
        [_non_conversion_row()], read_at="probe", scores_dir=directory
    )
    assert leg["status"] == "ASSERTED", leg
    assert leg["coverage"]["unmeasurable_cells"] == 1, leg["coverage"]
    assert leg["coverage"]["regressions"] == [], leg["coverage"]
    assert leg["problems"] == [], leg["problems"]

def test_the_score_conversion_leg_reads_a_FALLEN_net_total_as_a_regression() -> None:
    # A factory can hold every criterion at or above the floor and still REGRESS: the
    # second arm is its net total against the previous round's, which is how the
    # 2026-09-19 decline would have been caught.
    directory = _scores_dir(
        _score_artifact(total=70, cells=["3", "3"]),
        _score_artifact(total=74, cells=["4", "4"]),
    )
    leg = RUNNER.score_conversion_leg(
        [_non_conversion_row()], read_at="probe", scores_dir=directory
    )
    assert leg["coverage"]["previous"] == "evidence/scores/2026-10-09.md", leg["coverage"]
    assert leg["coverage"]["regressions"] == ["Probe factory"], leg["coverage"]
    assert "net total fell 74 -> 70" in leg["problems"][0], leg["problems"]

def test_the_score_conversion_leg_fails_OPEN_with_NO_artifact() -> None:
    empty = Path(tempfile.mkdtemp(prefix="probe-no-scores-"))
    leg = RUNNER.score_conversion_leg([], read_at="probe", scores_dir=empty)
    assert leg["status"] == "NOT RUN", leg
    assert leg["problems"] == [], leg
    assert "no `evidence/scores/<date>.md`" in leg["coverage"]["reason"], leg["coverage"]

def test_the_score_conversion_leg_fails_OPEN_when_the_artifact_carries_no_scorecards() -> None:
    # The pre-2026-10-08 artifacts carry no `## Detailed Factory Scorecards` section. The
    # leg must state that, never invent a finding from a file it could not parse.
    directory = _scores_dir("# Survey\n\nNo scorecards in this one.\n")
    leg = RUNNER.score_conversion_leg([], read_at="probe", scores_dir=directory)
    assert leg["status"] == "NOT RUN", leg
    assert leg["problems"] == [], leg
    assert "no `## Detailed Factory Scorecards`" in leg["coverage"]["reason"], leg["coverage"]

def test_the_score_conversion_leg_is_WIRED_into_the_run_and_PRINTS_its_population() -> None:
    # Wired AND rendered: a leg the run builds but the render cannot describe is a leg
    # whose verdict no reader ever sees -- and this one falls outside the board-intake
    # arm's coverage keys, so an unhandled name is a KeyError rather than a blank line.
    directory = _scores_dir(_score_artifact(total=70, cells=["2", "4"]))
    rc, out, _ = _run([], [_non_conversion_row()], scores_dir=directory)
    assert rc == 1, out
    assert "LEG score-conversion — ASSERTED" in out, out
    assert "evidence/scores/2026-10-10.md" in out, out
    assert "1 regression(s): Probe factory" in out, out
    assert "read at " in out, out

def test_the_score_conversion_leg_renders_its_REASON_when_it_cannot_run() -> None:
    # An empty scores surface reads NOT RUN with its counters, never as a clean patrol:
    # "no regression" and "no artifact parsed" are otherwise the same verdict (#242).
    rc, out, _ = _run([], [])
    assert rc == 0, out
    assert "LEG score-conversion — NOT RUN" in out, out
    assert "no `evidence/scores/<date>.md`" in out, out

def test_the_score_conversion_leg_reads_an_EMPTY_row_population_as_NOT_RUN() -> None:
    """#472 criteria 1-3: the verdict travels with the population it examined.

    The artifact side is guarded three times (no artifact, unreadable, no scorecards); the
    JOIN side had no equivalent, so `rows=[]` walked ZERO rows, found nothing answering the
    round, and returned the SAME `ASSERTED` status a real read returns -- a confident
    finding about a ledger the leg never read. That is the state that made a lane believe
    its own just-written `conversion` row had not landed and drove a second round of
    diagnosis while the row was present and correct. #242: a leg that examined NOTHING must
    never render as one that examined the population and found it clean.

    HERMETIC: every arm is built from rows this fixture supplies, never from a live ledger
    row, because a control keyed on a mutable artifact stops discriminating the moment that
    artifact changes (#467 criterion 2).
    """
    directory = _scores_dir(_score_artifact(total=70, cells=["2", "4"]))

    # ARM 1 -- an EMPTY population is NOT RUN with NO problem list, and the artifact-side
    # counters still travel with it so the read is visible rather than absent.
    empty = RUNNER.score_conversion_leg([], read_at="probe", scores_dir=directory)
    assert empty["status"] == "NOT RUN", empty
    assert empty["problems"] == [], empty["problems"]
    reason = empty["coverage"]["reason"]
    assert "EMPTY row population" in reason, reason
    assert "evidence/scores/2026-10-10.md" in reason, reason
    # ... it still states WHAT it parsed before it ran out of ledger: a NOT RUN arm that
    # zeroed these would misreport the artifact side it did read.
    assert empty["coverage"]["factories"] == 1, empty["coverage"]
    assert empty["coverage"]["regressions"] == ["Probe factory"], empty["coverage"]
    assert empty["coverage"]["conversion_rows"] == 0, empty["coverage"]
    assert empty["coverage"]["answered"] == [], empty["coverage"]

    # ARM 2 -- the real arm is UNCHANGED. A populated population whose row names THIS
    # artifact answers the round ...
    answered = RUNNER.score_conversion_leg(
        [_conversion_row("evidence/scores/2026-10-10.md")], read_at="probe",
        scores_dir=directory,
    )
    assert answered["status"] == "ASSERTED", answered
    assert answered["problems"] == [], answered["problems"]
    assert answered["coverage"]["answered"] == ["#67"], answered["coverage"]
    assert answered["coverage"]["unanswered"] == [], answered["coverage"]

    # ... and a POPULATED population carrying no conversion event stays a FINDING, never a
    # NOT RUN. The ledger WAS read and nothing in it answers the round; this is the arm that
    # keeps the guard narrow (#67, #148: a regression no row answers reads as converted and
    # is not). Widening the guard to this state would silence the leg exactly when it has
    # something to say.
    unanswered = RUNNER.score_conversion_leg(
        [_non_conversion_row()], read_at="probe", scores_dir=directory,
    )
    assert unanswered["status"] == "ASSERTED", unanswered
    assert len(unanswered["problems"]) == 1, unanswered["problems"]
    assert "Probe factory" in unanswered["problems"][0], unanswered["problems"]
    assert unanswered["coverage"]["conversion_rows"] == 0, unanswered["coverage"]

    # ARM 3 -- the RUN's own verdict, not just the function's: an empty population reads
    # NOT RUN, contributes NO problem, and the patrol exits 0 rather than reporting a
    # finding it cannot support.
    rc, out, _ = _run([], [], scores_dir=directory)
    assert rc == 0, out
    assert "LEG score-conversion — NOT RUN" in out, out
    assert "EMPTY row population" in out, out

def _scores_tree(artifacts: dict[str, str]) -> Path:
    """A throwaway scores surface carrying EXACTLY the dated artifacts named.

    `_scores_dir` writes a fixed pair; the lapsed arms need a third round to prove that a
    round which is neither the newest nor its predecessor is still read.
    """
    root = Path(tempfile.mkdtemp(prefix="probe-scores-"))
    for date, text in artifacts.items():
        (root / f"{date}.md").write_text(text, encoding="utf-8")
    return root

def test_the_score_conversion_leg_reports_a_LAPSED_round_by_NAME() -> None:
    """#517 criteria 1-2, ARM 1: two artifacts and ONE conversion row -> exactly one lapse.

    The defect: the population was `artifacts[-1]`, so a round whose `conversion` row never
    landed dropped out of it the moment a newer artifact arrived and could never be
    answered. Here the newest round is ALSO the lapsed one, which is the state the live
    tree was in on 2026-10-18 -- and the newest-arm problem must not be counted twice.
    """
    directory = _scores_tree({
        "2026-10-09": _score_artifact(total=70, cells=["4", "4"]),
        "2026-10-10": _score_artifact(total=70, cells=["2", "4"]),
    })
    rows = [_conversion_row("evidence/scores/2026-10-09.md")]
    leg = RUNNER.score_conversion_leg(rows, read_at="probe", scores_dir=directory)
    assert leg["status"] == "ASSERTED", leg
    cov = leg["coverage"]
    # The EPOCH is the artifact the EARLIEST row NAMES, and the population is every
    # artifact at or after it (ruling n=3820) -- never the newest artifact present, and
    # never only the newest artifact a row happens to name.
    assert cov["lapsed_epoch"] == "evidence/scores/2026-10-09.md", cov
    assert cov["lapsed_population"] == 2, cov
    assert cov["lapsed_examined"] == 1, cov
    assert [e["artifact"] for e in cov["lapsed"]] == ["evidence/scores/2026-10-10.md"], cov
    assert cov["lapsed"][0]["owed"] is True, cov["lapsed"]
    # ONE problem: the newest-arm finding. The lapsed arm must not duplicate it.
    assert len(leg["problems"]) == 1, leg["problems"]

    # ... and the population PRINTS, so "no lapse" and "no artifact parsed" differ.
    rc, out, _ = _run([], rows, scores_dir=directory)
    assert rc == 1, out  # the newest round carries an unanswered regression
    assert (
        "lapsed rounds since epoch evidence/scores/2026-10-09.md: 2 examined, 1 lapsed"
        in out
    ), out
    assert "evidence/scores/2026-10-10.md (1 regression(s)" in out, out

def test_the_score_conversion_leg_reports_ZERO_lapsed_rounds_once_rows_land_for_BOTH() -> None:
    """#517 criteria 2, ARM 2: the same two artifacts with TWO rows -> zero lapses.

    A leg that reported zero in ARM 1 too would be the current blind spot wearing a new
    name, so the two arms must disagree on the SAME fixture.
    """
    directory = _scores_tree({
        "2026-10-09": _score_artifact(total=70, cells=["4", "4"]),
        "2026-10-10": _score_artifact(total=70, cells=["2", "4"]),
    })
    rows = [
        _conversion_row("evidence/scores/2026-10-09.md"),
        _conversion_row("evidence/scores/2026-10-10.md", subject="#68"),
    ]
    leg = RUNNER.score_conversion_leg(rows, read_at="probe", scores_dir=directory)
    assert leg["status"] == "ASSERTED", leg
    cov = leg["coverage"]
    # The epoch is the EARLIEST named artifact, not the newest: rows naming 10-09 and
    # 10-10 leave the population at BOTH rounds, and neither is a lapse.
    assert cov["lapsed_epoch"] == "evidence/scores/2026-10-09.md", cov
    assert cov["lapsed_population"] == 2, cov
    assert cov["lapsed"] == [], cov
    assert cov["lapsed_examined"] == 0, cov
    assert leg["problems"] == [], leg["problems"]

def test_the_epoch_anchor_reports_a_MID_HISTORY_gap_the_newest_anchor_cannot_see() -> None:
    """#517 ruling n=3820 section 4: the discriminator between the two candidate anchors.

    Rows name A (2026-10-08) and C (2026-10-10) with NONE for B (2026-10-09). The
    newest-converted anchor sets the population to C alone -- one round, answered by its own
    row -- and reports ZERO lapses. The epoch anchor sets it to A, B, C and names B, which is
    the round a mid-history gap strands. In the ruling's words: a leg that reports zero here
    has not been widened, it has been renamed.
    """
    directory = _scores_tree({
        "2026-10-08": _score_artifact(total=70, cells=["4", "4"]),
        "2026-10-09": _score_artifact(total=70, cells=["2", "4"]),
        "2026-10-10": _score_artifact(total=70, cells=["2", "4"]),
    })
    rows = [
        _conversion_row("evidence/scores/2026-10-08.md"),
        _conversion_row("evidence/scores/2026-10-10.md", subject="#68"),
    ]
    leg = RUNNER.score_conversion_leg(rows, read_at="probe", scores_dir=directory)
    assert leg["status"] == "ASSERTED", leg
    cov = leg["coverage"]
    # The epoch is the EARLIEST named artifact; the newest-named anchor would read 10-10.
    assert cov["lapsed_epoch"] == "evidence/scores/2026-10-08.md", cov
    assert cov["lapsed_population"] == 3, cov
    # EXACTLY B: A and C each carry their own answering row, so neither is a lapse.
    assert [e["artifact"] for e in cov["lapsed"]] == ["evidence/scores/2026-10-09.md"], cov
    assert cov["lapsed"][0]["owed"] is True, cov["lapsed"]
    # The newest round is clean against B, so the ONE problem can only be the lapsed arm --
    # a leg that read the newest anchor would find nothing to report at all.
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "evidence/scores/2026-10-09.md" in leg["problems"][0], leg["problems"]

def test_an_OLDER_lapsed_round_that_OWES_a_conversion_is_a_PROBLEM() -> None:
    """#517 criterion 1: the round that is neither newest nor predecessor is still read.

    This is the arm the defect was named for. 2026-10-09 sits BELOW the newest artifact and
    ABOVE the epoch, so a leg that read only `artifacts[-1]` could never see it. It owes
    a conversion because it carries a regression (docs/measurement-procedure.md section
    5.4); the newest round is clean, so the problem can only come from the lapsed arm.
    """
    directory = _scores_tree({
        "2026-10-08": _score_artifact(total=70, cells=["4", "4"]),
        "2026-10-09": _score_artifact(total=70, cells=["2", "4"]),
        "2026-10-10": _score_artifact(total=70, cells=["4", "4"]),
    })
    rows = [_conversion_row("evidence/scores/2026-10-08.md")]
    leg = RUNNER.score_conversion_leg(rows, read_at="probe", scores_dir=directory)
    assert leg["status"] == "ASSERTED", leg
    cov = leg["coverage"]
    assert cov["lapsed_population"] == 3, cov
    assert cov["lapsed_examined"] == 2, cov
    owed = {e["artifact"]: e["owed"] for e in cov["lapsed"]}
    assert owed == {
        "evidence/scores/2026-10-09.md": True,
        "evidence/scores/2026-10-10.md": False,
    }, cov["lapsed"]
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "evidence/scores/2026-10-09.md" in leg["problems"][0], leg["problems"]
    assert "LAPSED" in leg["problems"][0], leg["problems"]
    # A regression-free lapsed round owes nothing, so it is reported but never a problem.
    assert "2026-10-10.md" not in leg["problems"][0], leg["problems"]

def test_the_score_conversion_leg_reports_NO_BASELINE_rather_than_EVERY_artifact() -> None:
    """#517: the pre-mechanism population carries no obligation, so a missing declaration
    must read as NOT RUN and never as "every round lapsed".

    Triage measured the boundary: of 37 score artifacts, 30 predate the conversion
    mechanism. A lapsed read with no epoch that reported them all would invent 30
    findings out of a declaration that does not exist (#112, #242).
    """
    directory = _scores_tree({
        "2026-10-09": _score_artifact(total=70, cells=["4", "4"]),
        "2026-10-10": _score_artifact(total=70, cells=["4", "4"]),
    })
    leg = RUNNER.score_conversion_leg(
        [_non_conversion_row()], read_at="probe", scores_dir=directory
    )
    assert leg["status"] == "ASSERTED", leg
    cov = leg["coverage"]
    assert cov["lapsed"] == [], cov
    assert cov["lapsed_examined"] == 0, cov
    assert "no baseline to measure a lapse against" in cov["lapsed_reason"], cov
    assert "lapsed_epoch" not in cov, cov
    assert "lapsed_population" not in cov, cov
    assert leg["problems"] == [], leg["problems"]

def test_the_stall_census_leg_PRINTS_the_lane_drain_beside_the_OWED_total() -> None:
    """#465 criterion 1: the OWED total travels with the addressee LANE's own drain
    evidence -- its claims on a SIBLING of the same standing set inside the window.

    The defect this answers: a bare "9 OWED" reads as nine independent findings, and for
    an addressee lane that is demonstrably working through the same batch that reading is
    wrong. The evidence is the lane's OWN claims on units it was dispatched, which is why
    it is grouped on the SAME declared routing the addressee is read from -- so the
    evidence and the line it corrects cannot disagree about whose lane it is.

    The sibling here is `#1002`, dispatched in the same standing set and claimed 0.5 d
    ago. `#1004` is claimed too, but 3 d ago -- OUTSIDE the 1.0 d window -- so a leg that
    read "any claim ever" instead of "a claim inside the window" fails this arm.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    worker, pacemakers = "aaaaaaaa-0000-0000-0000-000000000001", \
        "bbbbbbbb-0000-0000-0000-000000000002"
    issues = [_issue(1001, "OPEN"), _issue(1002, "OPEN"),
              _issue(1003, "OPEN"), _issue(1004, "OPEN")]
    rows = [
        _stall_row(1, "dispatch", "#1001", 5, now=now, refs=[{"session": worker}]),
        _stall_row(2, "dispatch", "#1002", 5, now=now, refs=[{"session": worker}]),
        _stall_row(3, "claim", "#1002", 0.5, now=now),
        _stall_row(4, "dispatch", "#1003", 5, now=now, refs=[{"session": pacemakers}]),
        _stall_row(5, "dispatch", "#1004", 5, now=now, refs=[{"session": pacemakers}]),
        _stall_row(6, "claim", "#1004", 3, now=now),
    ]
    names = {worker: "Worker", pacemakers: "Pacemakers / Crons"}

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at,
                                  lane_names_fn=lambda: names)
    cov = leg["coverage"]
    assert cov["units_owed"] == 2, cov
    assert cov["lanes_draining"] == 1, cov
    assert cov["units_owed_on_draining_lanes"] == 1, cov
    assert len(cov["lane_drain"]) == 1, cov["lane_drain"]
    drain = cov["lane_drain"][0]
    assert "DRAINING Worker" in drain, drain
    assert "#1002" in drain and "n=3" in drain, (
        f"the evidence must name the SIBLING and the row it was claimed at\n{drain}"
    )
    assert "#1004" not in drain, (
        f"a claim 3 d ago is OUTSIDE the 1.0 d window and is not drain evidence\n{drain}"
    )

    # ... and through the REAL `main()`: the drain evidence must reach the REPORT, beside
    # the OWED population it corrects. A leg returning a correct dict while the render
    # drops it is the half-fix this half exists to catch.
    rc, out, _ = _run(issues, rows, lane_names_fn=lambda: names)
    assert rc == 1, f"OWED lines must fail the run, got rc={rc}\n{out}"
    assert "population: 4 dispatched unit(s) -- 2 never claimed" in out, out
    assert "drain evidence" in out, out
    assert "1 lane(s) DRAINING, 1 of 2 OWED unit(s) sit on a draining lane" in out, out
    assert "DRAINING Worker" in out, out


def test_the_stall_census_leg_STOPS_prescribing_a_PER_ITEM_re_dispatch_on_a_DRAINING_lane() -> None:
    """#465 criterion 2: where the addressee lane is DRAINING, the OWED line stops naming
    a remedy that does not exist.

    "Re-dispatch it" is a duplicate (the lane already holds the batch), and "close it on
    the board" would be a falsification (these units are live, OPEN, wanted defects). A
    finding with no working exit is the class this factory refuses (#295, #139), so the
    remedy becomes the LANE's: ONE consolidated backlog-first brief.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    worker = "aaaaaaaa-0000-0000-0000-000000000001"
    issues = [_issue(1001, "OPEN"), _issue(1002, "OPEN")]
    rows = [
        _stall_row(1, "dispatch", "#1001", 5, now=now, refs=[{"session": worker}]),
        _stall_row(2, "dispatch", "#1002", 5, now=now, refs=[{"session": worker}]),
        _stall_row(3, "claim", "#1002", 0.5, now=now),
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at,
                                  lane_names_fn=lambda: {worker: "Worker"})
    line = [ln for ln in leg["problems"] if "#1001" in ln][0]
    assert "Do NOT re-dispatch this item: its addressee lane (Worker) is DRAINING" in line, line
    assert "ONE consolidated backlog-first brief" in line, line
    assert "Re-dispatch it to the lane that owns it through `session_notify`" not in line, (
        f"a draining lane must never be told to re-dispatch the item it already holds\n{line}"
    )

    # ... and the render half.
    rc, out, _ = _run(issues, rows, lane_names_fn=lambda: {worker: "Worker"})
    assert rc == 1, out
    assert "Do NOT re-dispatch this item: its addressee lane (Worker) is DRAINING" in out, out


def test_a_lane_with_NO_in_window_claim_keeps_its_OWED_line_VERBATIM() -> None:
    """#465 criterion 3, the TWO-SIDED control: the softened remedy is a statement about
    the drain, never a constant.

    `#1003`'s lane (`Pacemakers / Crons`) claimed nothing inside the window, so its stall
    is real and the re-dispatch advice is the only exit there is. A census that softened
    the sentence everywhere would stop naming the class it exists to name.

    The control has two halves, because a text assertion alone would pass a leg that
    printed the original sentence by accident of the fixture: (a) with a resolver that
    knows NOTHING there is no drain evidence at all -- the drain line says so in words
    rather than going silent -- and (b) the drain line prints even at zero, so "found no
    drain" is distinguishable from "never looked".
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    worker, pacemakers = "aaaaaaaa-0000-0000-0000-000000000001", \
        "bbbbbbbb-0000-0000-0000-000000000002"
    issues = [_issue(1001, "OPEN"), _issue(1002, "OPEN"),
              _issue(1003, "OPEN"), _issue(1004, "OPEN")]
    rows = [
        _stall_row(1, "dispatch", "#1001", 5, now=now, refs=[{"session": worker}]),
        _stall_row(2, "dispatch", "#1002", 5, now=now, refs=[{"session": worker}]),
        _stall_row(3, "claim", "#1002", 0.5, now=now),
        _stall_row(4, "dispatch", "#1003", 5, now=now, refs=[{"session": pacemakers}]),
        _stall_row(5, "dispatch", "#1004", 5, now=now, refs=[{"session": pacemakers}]),
        _stall_row(6, "claim", "#1004", 3, now=now),
    ]
    names = {worker: "Worker", pacemakers: "Pacemakers / Crons"}
    original = ("Re-dispatch it to the lane that owns it through `session_notify`, or "
                "close it on the board: a dispatch no lane has taken is work nobody is "
                "doing")

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at,
                                  lane_names_fn=lambda: names)
    line = [ln for ln in leg["problems"] if "#1003" in ln][0]
    assert original in line, (
        f"a lane with NO in-window claim keeps the ORIGINAL remedy VERBATIM\n{line}"
    )
    assert "Do NOT re-dispatch this item" not in line, line

    # (a) THE RESOLVER CONTROL: with a blind resolver no lane name exists, so no unit can
    # sit on a draining lane and NO line is softened -- the drain evidence is a statement
    # about the resolution, not a constant the leg prints.
    blind = RUNNER.stall_census_leg(issues, rows, read_at=read_at,
                                    lane_names_fn=lambda: {})
    assert blind["coverage"]["lanes_draining"] == 0, blind["coverage"]
    assert blind["coverage"]["units_owed_on_draining_lanes"] == 0, blind["coverage"]
    assert blind["coverage"]["lane_drain"] == [], blind["coverage"]["lane_drain"]
    assert all(original in ln for ln in blind["problems"]), blind["problems"]

    # (b) THE ZERO-DRAIN RENDER: the line prints at zero and SAYS what it read, so a leg
    # that never looked is distinguishable from one that looked and found nothing.
    rc, out, _ = _run(issues, rows, lane_names_fn=lambda: {})
    assert "drain evidence" in out, out
    assert "no lane carrying an OWED unit claimed a sibling inside the window" in out, out

def test_the_stall_census_leg_reads_a_CARRIER_mention_as_a_MENTION_never_a_ROUTING() -> None:
    """#467, TWO-SIDED and HERMETIC: whether a carrier ROUTED a unit is read from WHERE
    the token STANDS in the row, never from the fact that the row names it at all.

    The defect: the addressee map kept the NEWEST dispatch-bearing row declaring a typed
    `session` ref. An ESCALATION row -- non-unit subject, actor `hq`, its detail listing
    the stalled units in the BODY -- declares HQ's own session, so it overwrote the
    genuine routing for every unit it merely mentioned. On the live ledger that is row
    `n=3098` (`stall-census-escalation-2026-10-11T06`), which took the slot from the real
    routing row `n=3067` (`#79`, actor triage, addressed to the Worker lane) and read
    twelve units as addressed to the lane that COMPLAINED about them rather than the lane
    they were sent to. One surface over from #433: a body mention is a MENTION.

    BOTH arms are built from rows THIS fixture supplies. The control is deliberately not
    read from the live row `n=3098`: a control keyed on a mutable live artifact stops
    discriminating the moment that artifact changes, and would keep passing while testing
    nothing.

    NEGATIVE arm: the escalation-shaped row names `#1101` and `#1102` in its body and
    declares HQ -- the addressee must stay the row that actually dispatched them.
    POSITIVE arm: a batch-dispatch-shaped row whose OPENING LINE names `#1103` DID route
    it, and being newer it must win the slot from the older direct dispatch.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    worker, hq = "aaaaaaaa-0000-0000-0000-000000000001", \
        "bbbbbbbb-0000-0000-0000-000000000002"
    issues = [_issue(1101, "OPEN"), _issue(1102, "OPEN"), _issue(1103, "OPEN")]
    rows = [
        # THE GENUINE ROUTINGS, addressed to the Worker lane.
        _stall_row(1, "dispatch", "#1101", 5, now=now, actor="triage",
                   refs=[{"session": worker}]),
        _stall_row(2, "dispatch", "#1102", 5, now=now, actor="triage",
                   refs=[{"session": worker}]),
        # THE NEGATIVE ARM: an escalation that only MENTIONS them, deep in its body.
        _stall_row(3, "dispatch", "stall-census-escalation-probe", 1, now=now, actor="hq",
                   refs=[{"session": hq}],
                   detail="escalation for HQ's attention:\n"
                          "the following units have never been claimed -- #1101, #1102 --\n"
                          "and the census re-flags them every cycle"),
        # #1103's genuine routing, older than the carrier below.
        _stall_row(4, "dispatch", "#1103", 5, now=now, actor="triage",
                   refs=[{"session": worker}]),
        # THE POSITIVE ARM: a carrier that ROUTES #1103 in its opening line, and is newer.
        _stall_row(5, "dispatch", "batch-dispatch-probe", 1, now=now, actor="hq",
                   refs=[{"session": hq}],
                   detail="DISPATCH #1103 -> the HQ lane\ncarrying the backlog brief"),
    ]
    names = {worker: "Worker", hq: "HQ"}

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at,
                                  lane_names_fn=lambda: names)
    by_unit = {ln.split("OWED ")[1].split(":")[0]: ln
               for ln in leg["problems"] if "OWED #" in ln}

    # NEGATIVE: a body mention never takes the routing slot.
    for unit in ("#1101", "#1102"):
        line = by_unit[unit]
        assert "ADDRESSED to Worker" in line, (
            f"a row that only MENTIONS {unit} in its body is a MENTION, not a routing: "
            f"the addressee must stay the row that dispatched it\n{line}"
        )
        assert "ADDRESSED to HQ" not in line, (
            f"the escalation's session must not stand in {unit}'s addressee slot\n{line}"
        )

    # POSITIVE: an opening-line carrier DID route its unit, and wins on being newer.
    assert "ADDRESSED to HQ" in by_unit["#1103"], (
        f"a carrier whose OPENING LINE names the unit DID route it, and being newer it "
        f"takes the slot\n{by_unit['#1103']}"
    )

    cov = leg["coverage"]
    assert cov["units_owed"] == 3, cov
    assert cov["addressees_resolved"] == 3, cov
    assert cov["mentions_rejected"] == 2, (
        f"the two body-only tokens must be COUNTED as rejected, or a leg that never "
        f"applied the test is indistinguishable from one that rejected nothing\n{cov}"
    )

    # THE RENDER HALF: the rejected count reaches the report.
    rc, out, _ = _run(issues, rows, lane_names_fn=lambda: names)
    assert rc == 1, f"OWED lines must fail the run, got rc={rc}\n{out}"
    assert "named only in the BODY and read as a MENTION, never as a routing (#467)" in out, out
    assert "2 of their token(s) named only in the BODY" in out, out

# --- #241: the shared-tree rider ------------------------------------------------


def _rider(**over) -> dict:
    base = {
        "status": "ASSERTED",
        "read_at": "2026-10-03T02:00:00Z",
        "base": "origin/main",
        "base_sha": "abc1234",
        "dirty": [],
        "blocking": [],
        "reason": None,
        "reconciles": False,
    }
    base.update(over)
    return base


def test_the_rider_prints_the_blocking_paths_AND_the_instant() -> None:
    """The rider's whole job: name the paths that block `reset --keep`, and say WHEN read.

    A claim about a live tree is a claim about the instant it was read, so the instant is
    asserted here beside the paths — without it the rider is testimony, not evidence.
    """
    rider = _rider(
        dirty=[" M a.py", "?? b.py", " M TEMPLATE/registry/kit.example.json"],
        blocking=["TEMPLATE/registry/kit.example.json"],
    )
    text = "\n".join(RUNNER.render_shared_tree_rider(rider))
    assert "read at 2026-10-03T02:00:00Z" in text, text
    assert "3 dirty path(s)" in text, text
    assert "1 BLOCKING" in text, text
    assert "~ TEMPLATE/registry/kit.example.json" in text, text
    assert "origin/main abc1234" in text, text
    assert "REPORTED, never reconciled (reconciles: no)" in text, text


def test_the_rider_reports_an_UNKNOWN_comparison_rather_than_a_zero() -> None:
    """A zero blocking set is a verdict only from a WORKING comparison (#242).

    When the base cannot be resolved the blocking subset is UNKNOWN, and the rider must
    print that — an empty list there would read exactly like a clean tree.
    """
    rider = _rider(
        dirty=[" M a.py"], blocking=None, base_sha=None,
        reason="git rev-parse --verify origin/main^{commit} failed",
    )
    text = "\n".join(RUNNER.render_shared_tree_rider(rider))
    assert "BLOCKING: UNKNOWN" in text, text
    assert "git rev-parse --verify origin/main^{commit} failed" in text, text
    assert "0 BLOCKING" not in text, f"an unknown comparison must not read as zero\n{text}"
    assert "read at 2026-10-03T02:00:00Z" in text, text


def test_the_rider_prints_NOT_RUN_with_its_reason() -> None:
    """A tree that could not be read is NOT RUN with its reason — never an empty rider."""
    rider = _rider(status="NOT RUN", reason="git status --porcelain -z failed: not a repo")
    text = "\n".join(RUNNER.render_shared_tree_rider(rider))
    assert "NOT RUN" in text, text
    assert "git status --porcelain -z failed: not a repo" in text, text
    assert "read attempted at 2026-10-03T02:00:00Z" in text, text
    assert "dirty path(s)" not in text, f"a NOT RUN rider has no population to report\n{text}"


def test_the_rider_is_NON_VACUOUS() -> None:
    """The control: the SAME fixture with and without a blocking path.

    One fixture, rendered twice — once with a path that is dirty AND moved, once with a
    clean tree — so the difference is attributable to the hazard and not to the fixture.
    Without this arm a renderer that always printed an empty list would satisfy the
    assertions above.
    """
    moved = "TEMPLATE/registry/kit.example.json"
    with_hazard = "\n".join(RUNNER.render_shared_tree_rider(
        _rider(dirty=[f" M {moved}"], blocking=[moved])))
    without = "\n".join(RUNNER.render_shared_tree_rider(
        _rider(dirty=[f" M {moved}"], blocking=[])))
    assert "1 BLOCKING" in with_hazard, with_hazard
    assert "0 BLOCKING" in without, without
    assert f"~ {moved}" in with_hazard, with_hazard
    assert f"~ {moved}" not in without, without


def test_an_unreadable_tree_yields_a_NOT_RUN_rider_through_the_real_reader() -> None:
    """The NOT RUN path through `shared_tree_read` itself, not a hand-made dict.

    A repo path that is not a repository makes `git status` fail; the reader must RETURN
    that reason rather than raise, so the rider degrades to NOT RUN instead of taking the
    patrol down.
    """
    state = RUNNER.shared_tree_read(Path("/nonexistent-probe-repo-241"))
    assert state.get("status") == "NOT RUN", state
    assert state.get("reason"), state
    rider = RUNNER.shared_tree_rider("2026-10-03T02:00:00Z",
                                     read_fn=lambda repo: state)
    assert rider["status"] == "NOT RUN", rider
    assert rider["read_at"] == "2026-10-03T02:00:00Z", rider
    assert rider["reconciles"] is False, rider


def test_the_whole_run_PRINTS_the_rider_and_it_moves_NO_verdict() -> None:
    """Driven through the REAL `main()`: the rider is rendered AND cannot gate.

    The rider is printed once, at the head of the board-leg region, and carries no
    problem — so a run whose ONLY unusual fact is a dirty shared tree still exits 0. A
    standalone detection leg was refused as #83's class precisely because a report of a
    state nobody will fix must never move the verdict; this asserts the rider kept that
    property.
    """
    issues = [_issue(1, "OPEN")]
    # The `ruling` row is here so the fixture is CLEAN apart from the dirty tree: the
    # board-unruled leg (added after this probe's fixture was first written) REDs on an
    # intaken OPEN item with no ruling row, and a probe whose exit code is moved by an
    # unrelated leg would be asserting that leg rather than the rider's non-gating.
    rows = _rows(("intake", "#1", 1), ("ruling", "#1", 2))

    def _dirty_rider(*, read_at: str, **_kw) -> dict:
        return _rider(
            read_at=read_at,
            dirty=[" M TEMPLATE/registry/kit.example.json"],
            blocking=["TEMPLATE/registry/kit.example.json"],
        )

    rc, out, _ = _run(issues, rows, shared_tree_fn=_dirty_rider)
    assert rc == 0, f"the rider must not move the exit code\n{out}"
    assert out.count("shared tree rider") == 1, f"the rider prints ONCE\n{out}"
    assert "~ TEMPLATE/registry/kit.example.json" in out, out
    head = out.split("LEG ")[0]
    assert "shared tree rider" in head, (
        f"the rider must precede the board legs it qualifies\n{out}"
    )
    assert "read at " in head, out


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


if __name__ == "__main__":
    raise SystemExit(main())


# --- #506: a duty's declaration is PROSE, so its SHAPE is load-bearing ---------------
# The live instance: `factory-binding-sync` declared `receipt_subject: none` wrapped in
# backticks with prose after it, the canonical line-anchored reader matched nothing, and the
# patrol printed NOT JUDGED beside `problems: 0` for a whole round. The two arms below are
# the issue's own two halves, and each carries its discriminating pair so a predicate that
# reds EVERYTHING cannot pass them.
_BACKTICKED_DECL_PROMPT = (
    "Thin trigger only — do NOT execute any project work yourself. Run the pusher, then "
    "stop.\n\n`receipt_subject: none` — the cron stamps no ledger row; the receipt is the "
    "file.\n"
)
_UNDECLARED_PROMPT = (
    "Thin trigger only — do NOT execute any project work yourself. Wake the lane, then "
    "stop.\n"
)

def test_a_BACKTICKED_declaration_is_a_PROBLEM_named_with_its_SHAPE() -> None:
    """#506 half 1. The declaration EXISTS and the reader cannot reach it — that is a finding,
    not a third state that renders beside a clean problem count."""
    row = _duty_row(name="factory-binding-sync", prompt=_BACKTICKED_DECL_PROMPT)
    leg = _duty_leg([row], [], read_at=_plus(_DUTY_FIRE, 5.0))
    assert any("factory-binding-sync" in p and "backtick" in p for p in leg["problems"]), \
        leg["problems"]
    assert leg["coverage"]["jobs_malformed"] == 1, leg["coverage"]
    assert leg["coverage"]["malformed_jobs"] == ["factory-binding-sync"], leg["coverage"]
    # THE DISCRIMINATING PAIR: the SAME declaration on a canonical line is CLEAN. The two
    # fixtures differ in nothing but the shape of that one line, so a verdict that does not
    # move is attributable to the shape rather than to the population.
    fixed = _duty_row(name="factory-binding-sync", prompt=_OWES_NONE_PROMPT)
    assert _duty_leg([fixed], [], read_at=_plus(_DUTY_FIRE, 5.0))["problems"] == []

def test_a_MENTION_is_a_PROBLEM_naming_prose_before_the_token_and_still_no_declaration() -> None:
    """Ruling n=3527 criterion 4, which REVERSED the half this probe was written with.

    The earlier form asserted a mid-sentence token was NOTHING AT ALL -- and that is the same
    false negative as the backtick, one shape over: an author with the token in hand and no
    canonical line is indistinguishable from a duty that never meant to declare one, so the
    leg could not name the edit that un-declared it.

    The NON-GOAL is asserted in the same breath, because the fix must not become the defect it
    replaced: prose is never READ as a declaration, only reported as a defect to repair.
    """
    mention = ("Thin trigger only.\nThe old text said receipt_subject: registry-attest and "
               "it was removed.\n")
    found = RUNNER.malformed_receipt_declaration(mention)
    assert found is not None, "a mid-sentence mention is still read as nothing at all"
    line, text, shape = found
    assert line == 2, (line, text)
    assert "prose before the token" in shape, shape
    # THE NON-GOAL: the row is a problem, never a declaration -- `declared_receipt_stem`
    # stays anchored to a whole line, so nothing hunts a ledger subject read out of prose.
    assert RUNNER.declared_receipt_stem(mention) is None
    assert RUNNER.declared_receipt_disposition(mention) == ("malformed", shape)

    # DISCRIMINATING CONTROL: the same sentence with the token at line start is canonical, so
    # the arm tests the SHAPE and not the mere presence of the word.
    assert RUNNER.declared_receipt_disposition(
        "work order\nreceipt_subject: registry-attest\n") == ("declares", "registry-attest")
    # and a prompt carrying BOTH is judged on its declaration: `declared_receipt_stem`
    # answers first, so a correct prompt cannot be reded by a prose mention elsewhere.
    mixed = ("The old text said receipt_subject: other and it was removed.\n"
             "receipt_subject: registry-attest\n")
    assert RUNNER.declared_receipt_disposition(mixed) == ("declares", "registry-attest")

    # the backticked arm keeps its own shape assertions
    found = RUNNER.malformed_receipt_declaration(_BACKTICKED_DECL_PROMPT)
    assert found is not None, "the backticked line was not read as an attempt at all"
    line, text, shape = found
    assert line == 3, (line, text)
    assert "backtick" in shape and "prose after the value" in shape, shape

def test_an_UNDECLARED_duty_is_a_PROBLEM_unless_the_factory_DECLARED_it_EXEMPT() -> None:
    """#506 half 2. NOT JUDGED is a finding; a declared exemption turns it into VISIBLE DEBT,
    which is a different thing from a clean round."""
    row = _duty_row(name="factory-silent", prompt=_UNDECLARED_PROMPT)
    red = _duty_leg([row], [], read_at=_plus(_DUTY_FIRE, 5.0))
    assert any("factory-silent" in p and "NOT JUDGED" in p for p in red["problems"]), \
        red["problems"]
    assert red["coverage"]["jobs_undeclared"] == 1, red["coverage"]
    assert red["coverage"]["jobs_undeclared_exempt"] == 0, red["coverage"]
    assert red["excused"] == [], red["excused"]
    # the SAME census, with the job declared exempt: no problem, and the debt is NAMED
    ok = _duty_leg([row], [], read_at=_plus(_DUTY_FIRE, 5.0),
                   exemptions_fn=lambda: ({"factory-silent": "the probe's own reason"}, None))
    assert ok["problems"] == [], ok["problems"]
    assert ok["coverage"]["jobs_undeclared_exempt"] == 1, ok["coverage"]
    assert ok["coverage"]["undeclared_exempt_jobs"] == ["factory-silent"], ok["coverage"]
    assert any("factory-silent" in e and "DECLARED EXEMPTION" in e for e in ok["excused"]), \
        ok["excused"]

def test_an_UNREADABLE_exemption_store_is_a_PROBLEM_not_a_silent_empty_set() -> None:
    """A store that exists and cannot be parsed must not read as `nothing is excused, and
    nothing is wrong` — that is the same false CLEAN one layer down."""
    row = _duty_row(name="factory-silent", prompt=_UNDECLARED_PROMPT)
    leg = _duty_leg([row], [], read_at=_plus(_DUTY_FIRE, 5.0),
                    exemptions_fn=lambda: ({}, "the store could not be read (JSONDecodeError)"))
    assert any("could not be read" in p for p in leg["problems"]), leg["problems"]

def test_the_MALFORMED_and_EXEMPT_buckets_REACH_the_report() -> None:
    """A bucket that is counted but never PRINTED is invisible to the reader it exists for —
    the class that hid #506 for a round. Driven from a MIXED population, because a leg whose
    judged population is empty renders through the generic NOT-RUN block."""
    malformed = _duty_row(name="factory-binding-sync", prompt=_BACKTICKED_DECL_PROMPT,
                          row_id="a1b2c3d4-0000-4000-8000-000000000001")
    silent = _duty_row(name="factory-silent", prompt=_UNDECLARED_PROMPT,
                       row_id="a1b2c3d4-0000-4000-8000-000000000002")
    rc, out, err = _run([], [], cron_rows=[malformed, silent, _duty_row()],
                        prefixes=["factory-"], cron_fires=_fires((0.5,)))
    assert "malformed declarations: 1" in out, out[-2500:]
    assert "MALFORMED" in out and "backtick" in out, out[-2500:]
    assert "declared exemptions: 0" in out, out[-2500:]
    assert "factory-binding-sync" in out and "factory-silent" in out, out[-2500:]

def test_a_BACKTICKED_VALUE_is_a_shape_not_a_stem() -> None:
    """The canonical line matches a backticked VALUE, because a backtick is `\\S` — and the
    stem it yields can never equal any ledger subject, so the duty is hunted forever against
    a name that cannot exist and reads MISSING on every round. Measured while writing the
    #506 probes: the shape list named "a backtick in the value" and this arm never reached
    it, so the defect the reader was supposed to name was the one it silently accepted.

    The discriminating pair is the SAME line without the ticks: a canonical declaration must
    stay a declaration, or the fix has traded a false MISSING for a false finding.
    """
    ticked = "work order\nreceipt_subject: `survey`\n"
    plain = "work order\nreceipt_subject: survey\n"

    assert RUNNER.declared_receipt_stem(ticked) is None
    assert RUNNER.declared_receipt_disposition(ticked) == (
        "malformed", "a backtick in the value"), RUNNER.declared_receipt_disposition(ticked)

    # the control: identical bytes minus the ticks is a declaration with a usable stem
    assert RUNNER.declared_receipt_stem(plain) == "survey"
    assert RUNNER.declared_receipt_disposition(plain) == ("declares", "survey")

def test_a_STALE_exemption_is_a_PROBLEM_naming_the_job() -> None:
    """Ruling n=3527 criterion 3. The store is the one lawful exit, and an exit naming a job
    that is not an undeclared duty on this box has stopped describing reality: the job got a
    declaration, or was renamed, or was retired. Left silent it rots into a rubber stamp --
    the exemption would read as an active exit forever and nobody would see it excuse nothing.
    """
    silent = _duty_row(name="factory-silent", prompt=_UNDECLARED_PROMPT)
    leg = _duty_leg([silent], [], read_at=_plus(_DUTY_FIRE, 5.0),
                    exemptions_fn=lambda: ({"factory-retired": "the job was retired"}, None))
    stale = [p for p in leg["problems"] if "stale debt" in p]
    assert len(stale) == 1, leg["problems"]
    assert "factory-retired" in stale[0], stale[0]
    assert leg["coverage"]["jobs_stale_exempt"] == 1, leg["coverage"]
    assert leg["coverage"]["stale_exempt_jobs"] == ["factory-retired"], leg["coverage"]

    # DISCRIMINATING CONTROL: the same store naming the job that IS undeclared excuses it
    # and is NOT stale -- so the arm flags rot, not the mere existence of an entry.
    live = _duty_leg([silent], [], read_at=_plus(_DUTY_FIRE, 5.0),
                     exemptions_fn=lambda: ({"factory-silent": "declared exempt"}, None))
    assert not [p for p in live["problems"] if "stale debt" in p], live["problems"]
    assert live["coverage"]["jobs_stale_exempt"] == 0, live["coverage"]
    assert any("factory-silent" in e for e in live["excused"]), live["excused"]

def test_the_STALE_exemption_line_prints_on_every_round_zero_included() -> None:
    """A count that appears only when non-zero is indistinguishable from one the reader never
    computed -- the class that hid #506 for a whole round, so the zero is printed too."""
    rc, out, err = _run([], [], cron_rows=[_duty_row()], prefixes=["factory-"],
                        cron_fires=_fires((0.5,)), duty_exemptions=lambda: ({}, None))
    assert "stale exemptions: 0" in out, out[-2500:]

# --- #133: the driverless-lane leg -------------------------------------------------------
#
# The leg's whole value is the SPLIT it makes: a lane carrying an unclaimed backlog is stuck
# either because its loop is running (DRIVEN), because a goal row exists and nothing will wake
# it (ARMED-INERT), or because nothing was ever armed (DRIVERLESS). A leg that only asked
# "does a goal row exist" would call the middle reading healthy, and the middle reading is the
# one this box actually carries.

def _census_with(*lanes, status="ASSERTED"):
    """A census leg carrying ONLY the grouping the driverless leg reads.

    Deliberately minimal: this leg's population is the census's `owed_by_lane`, so a fixture
    that rebuilt the census's own routing would be asserting a second implementation of it.
    """
    return {
        "name": "stall-census",
        "status": status,
        "problems": [],
        "excused": [],
        "coverage": {
            "owed_by_lane": list(lanes),
            "lanes_with_backlog": len(lanes),
            "read_at": "2026-10-18T00:00:00Z",
        },
    }

def _lane_slot(session_ref, units, *, lane=None, age=2.0):
    return {"session_ref": session_ref, "lane": lane, "units": list(units),
            "oldest_age_days": age}

_GOAL_CREATED = "2026-10-01T00:00:00+00:00"

def _goal_row(session_id, state, *, turns=1, updated=_GOAL_CREATED):
    """One `goal_state` row. `updated` defaults to `created`, i.e. an arm never evaluated.

    The default is deliberate: the card's ARMED-INERT row is defined by `updated_at =
    created_at`, so the motionless shape is the one a fixture should get by NOT asking for
    motion. A fixture that had to remember to suppress the timestamp would be encoding the
    predicate a second time.
    """
    return {"session_id": session_id, "state": state, "turns_used": turns,
            "max_turns": 20, "created_at": _GOAL_CREATED,
            "updated_at": updated}

def _goal_store(*rows, unreached=(), without_store=()):
    return {"rows": list(rows), "homes_read": ["probe-home"],
            "homes_without_store": list(without_store), "unreached": list(unreached)}

def test_the_three_readings_are_DISTINCT_and_counted_separately() -> None:
    """#133's acceptance: DRIVEN, ARMED-INERT and DRIVERLESS are three different findings.

    Non-vacuity rides THIS fixture rather than a loud-fail-on-zero: the live population of
    driverless lanes is legitimately empty on a healthy day, so an empty reading is a normal
    reading. What must never be empty is the leg's ability to tell the three apart, which is
    exactly what a fixture carrying one of each proves -- a leg that collapsed ARMED-INERT into
    DRIVEN would report two DRIVEN and one DRIVERLESS here and pass a count-only assertion.

    THE FOURTH LANE IS THE CARD'S OWN COLLISION (#460 criterion 2). Read literally, the card's
    DRIVEN row (motion) and DRIVERLESS row (no active row, no turn in flight) both matched a
    `paused` row that advanced before it stopped, so a reader could report either. It reads
    DRIVERLESS, because a stopped loop is not a driver and calling it one refuses the only act
    that restarts it -- and that is asserted here so the two halves cannot drift apart again.
    """
    census = _census_with(
        _lane_slot("sess-driven", ["#1", "#2"], lane="Driven Lane"),
        _lane_slot("sess-inert", ["#3"], lane="Inert Lane"),
        _lane_slot("sess-none", ["#4", "#5", "#6"], lane="Driverless Lane"),
        _lane_slot("sess-stopped", ["#7"], lane="Stopped Lane"),
    )
    goals = _goal_store(
        # ADVANCING: active, evaluated, touched after creation.
        _goal_row("sess-driven", "active", turns=4, updated="2026-10-17T00:00:00+00:00"),
        # ARMED AND NEVER EVALUATED: active, zero turns, updated == created.
        _goal_row("sess-inert", "active", turns=0),
        # STOPPED AFTER RUNNING: motion in its history, but nothing will evaluate it again.
        _goal_row("sess-stopped", "paused", turns=20, updated="2026-10-17T00:00:00+00:00"),
    )
    leg = RUNNER.driverless_leg(census, goals=goals, read_at="2026-10-18T00:00:00Z",
                                lane_names_fn=lambda: {})

    assert leg["status"] == "ASSERTED", leg
    cov = leg["coverage"]
    assert (cov["driven"], cov["armed_inert"], cov["driverless"]) == (1, 1, 2), cov
    assert cov["lanes_judged"] == 4, cov
    assert cov["backlog_units"] == 7, cov
    assert cov["lanes_with_a_turn_in_flight"] == 0, cov

    readings = {entry["lane"]: entry["reading"] for entry in cov["lanes"]}
    assert readings == {
        "Driven Lane": "DRIVEN",
        "Inert Lane": "ARMED-INERT",
        "Driverless Lane": "DRIVERLESS",
        "Stopped Lane": "DRIVERLESS",
    }, readings

    # THE BITE: only the three non-DRIVEN lanes are problems, and each names its OWN cause --
    # a never-evaluated arm, a stopped loop and an absent one are three remedies, so one
    # sentence for all of them would be the collapse this probe exists to forbid.
    assert len(leg["problems"]) == 3, leg["problems"]
    by_lane = {p.split("LANE ", 1)[1].split(":", 1)[0]: p for p in leg["problems"]}
    assert set(by_lane) == {"Inert Lane", "Driverless Lane", "Stopped Lane"}, by_lane
    assert "`active`" in by_lane["Inert Lane"], by_lane["Inert Lane"]
    assert "never" in by_lane["Inert Lane"] and "evaluated" in by_lane["Inert Lane"], by_lane["Inert Lane"]
    assert "NO goal row" in by_lane["Driverless Lane"], by_lane["Driverless Lane"]
    assert "`paused`" in by_lane["Stopped Lane"], by_lane["Stopped Lane"]
    # ... and the stopped lane must NOT be described as never armed: it carries a row, and
    # printing an absence beside a row that exists is the misreport this split prevents.
    assert "NO goal row" not in by_lane["Stopped Lane"], by_lane["Stopped Lane"]
    assert "`active`" not in by_lane["Stopped Lane"], by_lane["Stopped Lane"]
    # ... and ALL of them say the leg will not act, so no reader thinks a re-arm happened.
    for problem in leg["problems"]:
        assert "MUST NOT re-arm another lane's goal" in problem, problem

def test_a_TURN_IN_FLIGHT_drives_a_lane_whose_arm_is_INERT() -> None:
    """The card's DRIVEN row admits a turn in flight EVEN WHEN THE ARM IS INERT.

    This is the reading the goal store alone cannot produce: an armed-but-never-evaluated lane
    is ARMED-INERT by its rows, and yet it is being driven right now by the turn that is
    running. A reader that consulted only `goal_state` would call it inert and refuse a re-arm
    that the card permits only because nothing is in the room -- so the binding fact decides.
    """
    census = _census_with(_lane_slot("sess-busy", ["#1"], lane="Busy Lane"))
    goals = _goal_store(_goal_row("sess-busy", "active", turns=0))
    leg = RUNNER.driverless_leg(
        census, goals=goals, read_at="2026-10-18T00:00:00Z",
        lane_names_fn=lambda: {},
        lane_turn_open_fn=lambda: {"sess-busy": True},
    )

    cov = leg["coverage"]
    assert cov["driven"] == 1 and cov["armed_inert"] == 0, cov
    assert cov["lanes_with_a_turn_in_flight"] == 1, cov
    assert cov["lanes"][0]["reading"] == "DRIVEN", cov["lanes"]
    assert leg["problems"] == [], leg["problems"]

    # THE CONTROL, same fixture, turn closed: without the binding fact the very same rows read
    # ARMED-INERT and the lane IS a problem. Both halves in one probe, so the assertion cannot
    # pass by the binding fact being ignored in both directions.
    idle = RUNNER.driverless_leg(
        census, goals=goals, read_at="2026-10-18T00:00:00Z",
        lane_names_fn=lambda: {},
        lane_turn_open_fn=lambda: {"sess-busy": False},
    )
    assert idle["coverage"]["armed_inert"] == 1, idle["coverage"]
    assert len(idle["problems"]) == 1, idle["problems"]

def test_a_census_with_NO_grouping_renders_NOT_RUN_never_a_clean_lane() -> None:
    """An unasked question must not render like a lane with nothing on it (#133).

    The failure this forbids is the one every zero-shaped leg is one refactor away from: the
    census ran NOT RUN, its grouping is absent, and a leg that iterated `coverage.get(...) or
    []` would print `0 DRIVERLESS` — a clean bill of health for a question nobody asked.
    """
    leg = RUNNER.driverless_leg({"name": "stall-census", "status": "NOT RUN",
                                 "problems": [], "excused": [],
                                 "coverage": {"reason": "the ledger could not be read"}},
                                goals=_goal_store(), read_at="2026-10-18T00:00:00Z")
    assert leg["status"] == "NOT RUN", leg
    assert leg["problems"] == [], leg
    assert "owed_by_lane" in leg["coverage"]["reason"], leg["coverage"]
    assert leg["coverage"]["census_status"] == "NOT RUN", leg["coverage"]

    out = RUNNER.render([leg], [], slug="owner/repo", read_at="2026-10-18T00:00:00Z",
                        issues=[])
    assert "LEG driverless-lane — NOT RUN" in out, out
    assert "NOT RUN: " in out, out
    assert "census status this round: NOT RUN" in out, out
    # THE DISCRIMINATING HALF: no reading counts at all, so nothing can be read as clean.
    assert "DRIVEN" not in out, out
    assert "DRIVERLESS" not in out, out
    assert "readings:" not in out, out

def test_an_UNREACHED_goal_store_prints_as_UNREACHED_not_as_a_driverless_lane() -> None:
    """A lane on an unopened home reads DRIVERLESS for want of a READ (#133).

    That is a true statement about this reader and a false one about the lane, so the render
    must name the unreached home beside the reading — otherwise the leg manufactures exactly
    the finding it is meant to report, and a reader has no way to tell the two apart.
    """
    census = _census_with(_lane_slot("sess-x", ["#9"], lane="Unread Lane"))
    leg = RUNNER.driverless_leg(
        census,
        goals=_goal_store(unreached=["ops: unable to open database file"]),
        read_at="2026-10-18T00:00:00Z",
        lane_names_fn=lambda: {},
    )
    # The reading itself is honest: no row was found, so nothing was armed AS FAR AS THIS READ.
    assert leg["coverage"]["driverless"] == 1, leg["coverage"]
    assert leg["coverage"]["goal_homes_unreached"] == ["ops: unable to open database file"]

    out = RUNNER.render([leg], [], slug="owner/repo", read_at="2026-10-18T00:00:00Z",
                        issues=[])
    assert "1 UNREACHED" in out, out
    assert "ops: unable to open database file" in out, out
    assert "for want of a read, not for want of a driver" in out, out
    # DISCRIMINATING CONTROL: the same leg with a store that WAS read carries no UNREACHED
    # line, so the sentence is attributable to the unread home and not to the leg's shape.
    clean = RUNNER.driverless_leg(census, goals=_goal_store(_goal_row("sess-x", "active")),
                                  read_at="2026-10-18T00:00:00Z", lane_names_fn=lambda: {})
    assert clean["coverage"]["driverless"] == 0, clean["coverage"]
    clean_out = RUNNER.render([clean], [], slug="owner/repo",
                              read_at="2026-10-18T00:00:00Z", issues=[])
    assert "UNREACHED" not in clean_out, clean_out
