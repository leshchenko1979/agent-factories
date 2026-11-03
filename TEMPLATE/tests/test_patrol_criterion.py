"""Gate: the criterion path and its declarations — #48/#541/#506/#392

Split from tests/test_patrol_host_state.py by #602: one gate per leg, each
carrying its own measured budget, so one slow leg can no longer withhold a
verdict from the whole fleet.
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

from patrol_fixtures import (  # noqa: F401
    RUNNER,
    _BACKTICKED_DECL_PROMPT,
    _CLOSE_TS,
    _DUTY_FIRE,
    _NO_CRITERION_EXEMPTIONS,
    _OWES_NONE_PROMPT,
    _ROW_SET_CLEAN_CLAIMS,
    _UNDECLARED_PROMPT,
    _conversion_row,
    _criterion_tree,
    _duty_leg,
    _duty_row,
    _fires,
    _git,
    _git_init,
    _home_db,
    _issue,
    _issue_with_comments,
    _non_conversion_row,
    _plus,
    _rows,
    _run,
    _score_artifact,
    _scores_dir,
    _scores_tree,
    _stall_row,
    _swept,
    main,
    _SKIPS,
)


# --- this leg's own helpers -------------------------------------------------
def _issue_with_body(number: int, state: str, body: str) -> dict:
    """A board issue carrying a BODY, in the shape `gh issue list --json` returns."""
    issue = _issue(number, state)
    issue["body"] = body
    return issue

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

def _citation_store(payload) -> Path:
    """A store file for a probe, in its own directory, never the live one."""
    directory = Path(tempfile.mkdtemp(prefix="patrol-citation-store-"))
    path = directory / "criterion-path-exemptions.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path

def _pad(chars: int) -> str:
    """Prose filler with no unit token and no repository qualifier in it."""
    unit = "the lane read its own store and stated the measurement rather than the impression "
    return (unit * (chars // len(unit) + 1))[:chars]

def _cron_row(name: str, *, next_run_at: str, last_run_at: str = "", cron_expr: str = "0 9 * * *",
              timezone: str = "Europe/Moscow", home: str = "ops", row_id: str = "id-1") -> dict:
    """One enabled cron row in the shape `box_cron_rows` produces."""
    return {
        "id": row_id,
        "name": name,
        "deliver_to": "",
        "prompt": "",
        "last_run_at": last_run_at,
        "cron_expr": cron_expr,
        "next_run_at": next_run_at,
        "timezone": timezone,
        "home": home,
    }

def _run_record(name: str, started_at: str, *, job_id: str = "id-1", home: str = "ops") -> dict:
    """One `cron_job_runs` row in the shape `cron_run_fires` produces."""
    return {
        "job_id": job_id,
        "job_name": name,
        "started_at": started_at,
        "status": "success",
        "completed_at": started_at,
        "error": "",
        "content": "",
        "suppressed": False,
        "home": home,
    }

def _daily_runs(name: str, *, lateness: tuple, last: str = "2026-10-20T06:00:00+00:00",
                job_id: str = "id-1") -> list:
    """A job's own run history: one run per day, each `lateness` seconds after its boundary.

    Built by walking BACKWARD from `last` a day at a time, so the history lines up with the
    `0 9 * * *` Europe/Moscow schedule the fixtures use (09:00 MSK = 06:00Z).
    """
    base = RUNNER.reader_parse_ts(last)
    records = []
    for index, offset in enumerate(lateness):
        instant = base - dt.timedelta(days=index) + dt.timedelta(seconds=offset)
        records.append(_run_record(name, instant.isoformat(), job_id=job_id))
    return list(reversed(records))

def _instants(row: dict, records: list) -> list:
    """The run RECORDS for one row, as the PARSED INSTANTS the grace and verdict take.

    `cadence_grace_for` and `cadence_slot_verdict_for` do ARITHMETIC on what they are handed,
    so their `runs` argument is a list of instants -- the shape `cadence_job_runs` returns --
    and never the raw `cron_job_runs` rows. The leg performs exactly this conversion, so a
    direct call that goes through here exercises the documented contract rather than a
    private one.
    """
    return RUNNER.cadence_job_runs(row, records) or []

def _stall_fixture(*, silent_from: str, silent_to: str, before: int = 6,
                   after: int = 6) -> tuple[list, list]:
    """Three hourly jobs whose fires STOP for `silent_from` -> `silent_to`, then resume.

    Built so the aggregate stream has ONE long gap and many short ones: `before` fires an
    hour apart up to `silent_from`, then nothing until `after` fires resume from `silent_to`.
    Three jobs share the same schedule, so all three are due across the stall and all three
    are silent -- the shape the ruling defines, "many jobs sharing the same gap".

    The rows carry `0 * * * *` (hourly), so the derived floor is 3600 s and the stall gap is
    many times that, which is what makes the read's own floor reachable rather than moot.
    """
    rows, fires = [], []
    start = RUNNER.reader_parse_ts(silent_from) - dt.timedelta(hours=before)
    resume = RUNNER.reader_parse_ts(silent_to)
    for index in range(3):
        name = f"job-hourly-{index}"
        row_id = f"id-hourly-{index}"
        rows.append(_cron_row(name, next_run_at="2026-10-21T07:00:00+00:00",
                              last_run_at=silent_to, cron_expr="0 * * * *",
                              timezone="UTC", row_id=row_id))
        for step in range(before):
            fires.append(_run_record(name, (start + dt.timedelta(hours=step)).isoformat(),
                                     job_id=row_id))
        for step in range(after):
            fires.append(_run_record(name, (resume + dt.timedelta(hours=step)).isoformat(),
                                     job_id=row_id))
    return rows, fires

def _coverage_fixture(*, coverage: dict) -> tuple[list, list]:
    """Hourly jobs sharing ONE long silence, with each job's store OPENING chosen by the caller.

    The stream is arm 5's -- fires hourly, stops for ten hours, resumes in a burst -- and the
    ONLY thing `coverage` changes is where each job's own first record sits relative to that
    gap. Four words, one per job:

    * ``full``   -- first record six hours BEFORE the gap, so the job is observable across it;
    * ``inside`` -- first record INSIDE the gap, so it fires there and cannot read as silent;
    * ``after``  -- first record AFTER the gap has closed, so it has no fire in the gap at all;
    * ``never``  -- no run record anywhere, so it has no observable history.

    ``after`` is the May-2026 shape this unit files (#570): the job is DUE from its SCHEDULE,
    which is unbounded, while SILENT is the absence of a RECORD, which begins at the first
    fire -- so before the bound, a store that did not exist yet read exactly like a stall.
    ``inside`` is the milder half of the same defect: the job was observable for part of the
    window, so it dilutes the fraction without ever having had the chance to be silent.
    """
    rows, fires = [], []
    gap_from = RUNNER.reader_parse_ts("2026-10-20T11:00:00+00:00")
    gap_to = RUNNER.reader_parse_ts("2026-10-20T21:00:00+00:00")
    opens = {
        "full": RUNNER.reader_parse_ts("2026-10-20T06:00:00+00:00"),
        "inside": RUNNER.reader_parse_ts("2026-10-20T12:00:00+00:00"),
        "after": RUNNER.reader_parse_ts("2026-10-20T22:00:00+00:00"),
    }
    end = RUNNER.reader_parse_ts("2026-10-21T02:00:00+00:00")
    for name in sorted(coverage):
        when = coverage[name]
        assert when in (*opens, "never"), when
        row_id = f"id-{name}"
        rows.append(_cron_row(name, next_run_at="2026-10-21T07:00:00+00:00",
                              last_run_at=end.isoformat(), cron_expr="0 * * * *",
                              timezone="UTC", row_id=row_id))
        if when == "never":
            continue
        step, opening = opens[when], True
        while step <= end:
            # THE OPENING RECORD IS ALWAYS WRITTEN, and the gap interior is skipped after it:
            # a store that opens inside the gap HAS a fire there (that is what `inside`
            # means), while a store open across the gap records nothing in it (that is what
            # makes `full` silent).
            if opening or not (gap_from < step < gap_to):
                fires.append(_run_record(name, step.isoformat(), job_id=row_id))
            opening = False
            step += dt.timedelta(hours=1)
    return rows, fires

def _row_set_cov(**overrides):
    """A row-set coverage dict with the registrations keys at their UNREAD values.

    Every key is present, `None` included, exactly as `row_set_leg` emits them — the
    render is being probed, so a fixture that omitted a key would test a shape the leg
    never produces.
    """
    cov = {
        "name": "row-set",
        "status": "ASSERTED",
        "path": "evidence/ledger.jsonl",
        "base": "origin/main",
        "recovery": "ROUTE",
        "verdict": "none",
        "read_at": "2026-11-01T00:00:00Z",
        "tree_rows": 4593,
        "remote_rows": 4593,
        "rows_examined": 4593,
        "tree_only": [],
        "tree_only_count": 0,
        "remote_only": [],
        "remote_only_count": 0,
        "level": True,
        "registrations": None,
        "registrations_probed": None,
        "registrations_error": None,
        "rows_off_base": None,
        "rows_off_base_count": None,
        "ahead_of_base": None,
        "ahead_of_base_count": None,
        "stranded": None,
        "stranded_count": None,
        "loss_risk": None,
        "loss_risk_count": None,
        "registration_errors": None,
    }
    cov.update(overrides)
    return cov

def _row_set_claims(lines):
    """The clean claims the render ACTUALLY emitted, matched by line prefix."""
    found = []
    for line in lines:
        body = line.strip()
        for claim in _ROW_SET_CLEAN_CLAIMS:
            if body.startswith(claim):
                found.append(claim)
    return found

# --- this leg's tests -------------------------------------------------------
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
    rows = _swept(("intake", "#172", 1), ("ruling", "#172", 2))
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
    rows = _swept(("intake", "#11", 1), ("ruling", "#11", 2))
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
    rows = _swept(("intake", "#11", 1), ("ruling", "#11", 2))
    tree = _criterion_tree("tools/probe.py")
    rc, out, _ = _run(issues, rows, criterion_repo=tree)
    assert rc == 0, out
    assert "judged against the tree at" in out, out
    head, _why = RUNNER.committed_tree_rev(tree)
    assert head and head[:12] in out, (
        f"the render must name the commit it read ({head})\n{out}"
    )

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

def test_the_criterion_path_leg_reads_a_FENCED_quote_as_a_CITATION_and_prints_it() -> None:
    """Arm 1. A path quoted in a fenced block is the patrol's own output quoted as evidence,
    not an obligation — it reads CLEAN and prints `cited:` WITH its reason, because an excuse
    nobody can read is how a wrong excuse hides."""
    issues = [_issue_with_body(
        540, "OPEN",
        "The leg reports two dead exemptions:\n\n"
        "```\n"
        "  excused: `docs/hygiene-protected.json` — declared absent-by-law\n"
        "```\n",
    )]
    tree = _criterion_tree("tools/probe.py")
    leg = _criterion_leg(issues, repo=tree)
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["refs_examined"] == 1, leg["coverage"]
    assert leg["coverage"]["cited"] == 1, leg["coverage"]
    cited = " ".join(leg["cited"])
    assert "docs/hygiene-protected.json" in cited, cited
    assert "fenced block" in cited, cited
    # The token was EXAMINED, never dropped: the population's size is unchanged.
    assert leg["coverage"]["refs_examined"] == 1, leg["coverage"]

def test_the_criterion_path_leg_REDS_on_the_same_path_named_as_a_CRITERION() -> None:
    """Arm 2. The SAME path, named as a criterion in prose with no other subject in its
    sentence, is judged — and where a path is both quoted and named, the NAMED occurrence
    wins, because one obligation is enough."""
    issues = [_issue_with_body(
        540, "OPEN",
        "Quoted for context:\n\n"
        "```\n"
        "`docs/hygiene-protected.json`\n"
        "```\n\n"
        "Done when `docs/hygiene-protected.json` exists.\n",
    )]
    tree = _criterion_tree("tools/probe.py")
    leg = _criterion_leg(issues, repo=tree)
    assert leg["problems"], "a path NAMED as a criterion must be judged, quoted elsewhere or not"
    assert "`docs/hygiene-protected.json`" in leg["problems"][0], leg["problems"]
    assert "dispatch a work item" in leg["problems"][0], leg["problems"]
    assert leg["coverage"]["refs_examined"] == 1, leg["coverage"]
    assert leg["coverage"]["cited"] == 0, leg["coverage"]

def test_the_criterion_path_leg_does_NOT_let_a_QUOTED_dead_exemption_revive_itself() -> None:
    """Arm 3, the DISCRIMINATOR. This is the shape that made #540 self-silencing: a defect
    report QUOTES the dead exemption it reports, so the quoted path counted as a live absence
    and the entry stopped reading stale — a dead-debt verdict controlled by whichever report
    was open. Measured: `exemptions_declared 2, declared_exempt 2` and NO stale finding at
    00:40Z, against both being dead at 00:03:33Z.

    Arms 1 and 2 alone both pass on a leg that simply DROPPED every token, so this arm is the
    one that pins the fix: the entry must still report `matches no live absence`.
    """
    dead_path = "docs/dead-exemption-probe.json"
    store = _citation_store({"exempt": [{
        "path": dead_path,
        "authority": "skills/meta-factory/SKILL.md:414 + ruling n=2693",
        "reason": "probe: an entry whose work is done, reported as dead",
    }]})
    issues = [_issue_with_body(
        540, "OPEN",
        "The patrol now reports this entry as dead:\n\n"
        "```\n"
        f"`{dead_path}`: the exemption matches no live absence, so it excuses nothing\n"
        "```\n",
    )]
    tree = _criterion_tree("tools/probe.py")
    leg = _criterion_leg(issues, repo=tree, exemptions_path=store)
    cov = leg["coverage"]
    assert cov["exemptions_declared"] == 1, cov
    assert cov["declared_exempt"] == 0, cov
    joined = " ".join(leg["problems"])
    assert "matches no live absence" in joined, (
        f"quoting a dead exemption REVIVED it — the #540 shape is back: {leg['problems']}"
    )
    assert dead_path in joined, leg["problems"]
    # ...and the quoted token itself is still counted and printed, not silently dropped.
    assert cov["cited"] == 1, cov
    assert dead_path in " ".join(leg["cited"]), leg["cited"]

def test_the_criterion_path_leg_attributes_a_prose_path_to_the_OTHER_item_it_names() -> None:
    """The second citation shape, measured on the same body: a path in ordinary prose whose
    sentence names a DIFFERENT `#NNN` is that item's obligation, not this one's. A fence-skip
    alone catches 2 of the 4 phantom tokens; this shape is the other 2."""
    issues = [_issue_with_body(
        540, "OPEN",
        "Not in scope: `tests/test_commit_subject_issue_refs.py` is #529's, dispatched at "
        "n=3992, and `TEMPLATE/tests/test_audit_cadence.py` is parked on #324's design gate.",
    )]
    tree = _criterion_tree("tools/probe.py")
    leg = _criterion_leg(issues, repo=tree)
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["refs_examined"] == 2, leg["coverage"]
    assert leg["coverage"]["cited"] == 2, leg["coverage"]
    cited = " ".join(leg["cited"])
    assert "#529" in cited and "#324" in cited, cited
    assert "attributed to" in cited, cited

def test_the_criterion_path_leg_is_NOT_fooled_by_a_bare_number_in_the_same_sentence() -> None:
    """The attribution test must not excuse a criterion merely because the sentence carries a
    number: `#540` IS this item, so a sentence naming only its own number judges the path."""
    issues = [_issue_with_body(
        540, "OPEN",
        "Done when `tools/probe-criterion.py` exists for #540.",
    )]
    tree = _criterion_tree("tools/probe.py")
    leg = _criterion_leg(issues, repo=tree)
    assert leg["problems"], "a sentence naming only this item's own number excused its path"
    assert "`tools/probe-criterion.py`" in leg["problems"][0], leg["problems"]
    assert leg["coverage"]["cited"] == 0, leg["coverage"]

def test_the_criterion_path_leg_reads_a_TABLE_CELL_quote_as_a_CITATION() -> None:
    """Ruling n=4056 adds the THIRD shape: a table cell whose content is a bare path token
    cites it, because a report's own table row measures rather than obliges. The omission was
    the ruling's — #541's body named four quotation shapes and n=4050 ruled two — so this arm
    is the repair of that, not a widening the leg invented."""
    issues = [_issue_with_body(
        541, "OPEN",
        "Measured, two store states:\n\n"
        "| store | unresolved | of which |\n"
        "|---|---|---|\n"
        "| as committed | 5 | **2** — `TEMPLATE/tests/test_audit_cadence.py` |\n",
    )]
    tree = _criterion_tree("tools/probe.py")
    leg = _criterion_leg(issues, repo=tree)
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["cited"] == 1, leg["coverage"]
    cited = " ".join(leg["cited"])
    assert "TEMPLATE/tests/test_audit_cadence.py" in cited, cited
    assert "table cell" in cited, cited

def test_the_criterion_path_leg_REDS_on_a_TABLE_CELL_that_carries_a_CRITERION() -> None:
    """The cell branch asks what the CELL holds, not whether the line has a `|`. A cell that
    carries prose is judged even though it sits in a table — otherwise the branch is a
    catch-all keyed on punctuation, which is the class the ruling closed the shape set to
    prevent."""
    issues = [_issue_with_body(
        541, "OPEN",
        "| requirement | state |\n"
        "|---|---|\n"
        "| Done when `tools/probe-criterion.py` exists | owed |\n",
    )]
    tree = _criterion_tree("tools/probe.py")
    leg = _criterion_leg(issues, repo=tree)
    assert leg["problems"], "a criterion stated inside a table cell was excused"
    assert "`tools/probe-criterion.py`" in leg["problems"][0], leg["problems"]
    assert leg["coverage"]["cited"] == 0, leg["coverage"]

def test_the_criterion_path_leg_JUDGES_bare_prose_with_no_attribution() -> None:
    """THE DISCRIMINATOR (ruling n=4056). A token in bare prose with no attribution stays a
    PROBLEM, even where a human can tell it was meant as an example. "The author obviously
    meant an example" is the fifth specimen of the #99/#247/#278/#476 cycle, each time one
    specimen after the fix, each time by adding vocabulary for the shape that had just bitten
    — so the shape set is CLOSED at three plus attribution, and an unnamed shape surfaces as a
    problem in the same place real debt appears rather than being silently excused."""
    issues = [_issue_with_body(
        540, "OPEN",
        "Add `docs/some-new-law-forbidden.json` with valid authority and reason and you get "
        "`FAIL — 3 declared but 2 matched a live absence`.",
    )]
    tree = _criterion_tree("tools/probe.py")
    leg = _criterion_leg(issues, repo=tree)
    assert leg["problems"], "bare prose with no attribution was excused — the branch became a catch-all"
    assert "`docs/some-new-law-forbidden.json`" in leg["problems"][0], leg["problems"]
    assert leg["coverage"]["cited"] == 0, leg["coverage"]

def test_the_ROUTING_test_reads_GRAMMATICAL_ROLE_not_the_opening_line() -> None:
    """#550 acceptance (1)-(3): a one-line detail separates its ROUTED unit from its
    MENTIONS, a genuine batch keeps every unit, and a unit standing 2,000+ characters in
    after a preamble still routes -- so the fix cannot pass by demoting real dispatches.

    Arm 1 is `n=4048`'s shape: a typed `{"subject": "#961"}` ref, a SECOND unit 800+
    characters later that its own prose predicates (`#962 was built for`), a possessive
    (`#963's`) and a parenthetical (`#964 (n=4035)`). Before the fix all four read ROUTED
    and four units were dispatched by a row that dispatched one. Arm 2 is `n=219`'s batch:
    five units, every one the subject of its own finding, spread past offset 800 -- the
    population an offset cap destroys. Arm 3 is `n=330`'s single dispatch: the unit at
    offset 2,274, after a lane preamble and a verbatim receipt.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # ---- arm 1: the must-RED shape (n=4048) -----------------------------------------
    typed_detail = (
        "DISPATCH to the HQ lane, resolved LIVE this turn rather than from memory. "
        "#961 is a law-and-gate question and HQ owns the ruling, so HQ is the addressee; "
        "no worker dispatch is owed until HQ rules. WHAT IS OWED: a ruling on the shape. "
        + _pad(700)
        + " #962 was built for that case. NOT OWED TO A WORKER: the other findings are "
        "already routed -- #963's tests were dispatched elsewhere, and #964 (n=4035) is "
        "parked on the owner design gate."
    )
    arm1_rows = [
        _stall_row(1, "dispatch", "criterion-path-dead-exemption-probe", 5, now=now,
                   detail=typed_detail, refs=[{"subject": "#961"}]),
        _stall_row(2, "intake", "#962", 9, now=now),
        _stall_row(3, "intake", "#963", 9, now=now),
        _stall_row(4, "intake", "#964", 9, now=now),
    ]
    arm1_issues = [_issue(961, "OPEN"), _issue(962, "OPEN"), _issue(963, "OPEN"),
                   _issue(964, "OPEN")]
    arm1 = RUNNER.stall_census_leg(arm1_issues, arm1_rows, read_at=read_at)
    cov = arm1["coverage"]
    assert cov["units_in_population"] == 1, (
        f"the row DECLARES #961 in a typed subject ref and prose cannot add to it (#550 "
        f"clause 1) -- three units dispatched by a row that dispatched one is the defect\n"
        f"{cov}"
    )
    named = "\n".join(arm1["problems"])
    assert "OWED #961" in named, named
    for mention in ("#962", "#963", "#964"):
        assert f"OWED {mention}" not in named, (
            f"{mention} stands in apposition to its clause and must never become a "
            f"routing, let alone an OWED finding\n{named}"
        )
    assert cov["units_named_only_as_mentions"] == 3, cov

    # ---- arm 1b: the mentions count PRINTS ITS POPULATION (clause 5) ----------------
    # A bare "3 mentions" has no denominator, so a reader cannot tell a narrow read from a
    # small one. Driven through the REAL `main()` so the line under test is the one a lane
    # reads, not a string this probe assembled.
    rc1, out1, _ = _run(arm1_issues, arm1_rows)
    assert rc1 == 1, f"the owed unit must fail the run\n{out1}"
    assert "mentions: 3 of 4 carried token(s)" in out1, (
        f"the count must stand beside the population it was drawn from -- 3 refused out of "
        f"4 examined\n{[ln for ln in out1.splitlines() if 'mention' in ln]}"
    )
    assert "in APPOSITION" in out1, (
        f"the line must state the predicate it applied, not just a number\n{out1[-2000:]}"
    )

    # ---- arm 2: the must-GREEN batch (n=219) ----------------------------------------
    batch_detail = (
        "Hourly triage pacemaker sweep complete. FINDINGS: (1) #971 unclaimed 4h10m since "
        "intake -> dispatched to the Worker lane. " + _pad(300)
        + " (2) #972 had NO intake row -> intaken and dispatched in the same brief. "
        + _pad(300)
        + " (3) #973 claimed by HQ and parked while HQ lands the owner's item. "
        + _pad(300)
        + " (4) #974 closed in the ledger but OPEN on the board. "
        + _pad(300)
        + " (5) #975 closed on the board 34s after its ledger close."
    )
    batch_rows = [
        _stall_row(11, "dispatch", "sweep-probe", 5, now=now, detail=batch_detail),
    ] + [_stall_row(20 + i, "intake", f"#{n}", 9, now=now)
         for i, n in enumerate((971, 972, 973, 974, 975))]
    batch_issues = [_issue(n, "OPEN") for n in (971, 972, 973, 974, 975)]
    batch = RUNNER.stall_census_leg(batch_issues, batch_rows, read_at=read_at)
    assert batch["coverage"]["units_in_population"] == 5, (
        f"every unit in a genuine batch is the SUBJECT of its own finding, at offsets past "
        f"800 -- a fix that demotes them is the offset cap the ruling withdrew\n"
        f"{batch['coverage']}"
    )
    assert batch["coverage"]["units_named_only_as_mentions"] == 0, batch["coverage"]

    # ---- arm 3: the must-GREEN single dispatch at offset 2,274 (n=330) --------------
    preamble = ("hq -> Worker lane, delivery turn-end; receipt verbatim: 'Delivered to "
                "session ... It will process the message on its next turn.' ")
    single_detail = (
        preamble + _pad(2000)
        + " THE DECIDING MOVE #976 shipped tonight. PRIORITY STATED: before #977 (n=325) "
        "and before #978's two mechanical halves."
    )
    assert single_detail.index("#976") > 2000, single_detail.index("#976")
    single_rows = [
        _stall_row(31, "dispatch", "ledger-clause-gate-exit-probe", 5, now=now,
                   detail=single_detail),
        _stall_row(32, "intake", "#977", 9, now=now),
        _stall_row(33, "intake", "#978", 9, now=now),
        _stall_row(34, "intake", "#976", 9, now=now),
    ]
    single = RUNNER.stall_census_leg(
        [_issue(976, "OPEN"), _issue(977, "OPEN"), _issue(978, "OPEN")],
        single_rows, read_at=read_at)
    assert single["coverage"]["units_in_population"] == 1, single["coverage"]
    assert "OWED #976" in "\n".join(single["problems"]), (
        f"a unit at offset {single_detail.index('#976')} is a REAL dispatch and must route; "
        f"an offset cap tight enough to fix arm 1 demotes exactly this\n"
        f"{single['problems']}"
    )
    assert single["coverage"]["units_named_only_as_mentions"] == 2, single["coverage"]

    # ---- arm 4: the newline is NOT the discriminator --------------------------------
    # The filing's own criterion 2, sharpened: the SAME text with real newlines at the same
    # logical places must reach the SAME verdict, so the fix is provably not a narrowing of
    # the newline case in either direction.
    newlined = batch_detail.replace(" (", "\n(")
    assert newlined != batch_detail, "the control must actually change the bytes"
    newline_rows = [
        _stall_row(41, "dispatch", "sweep-probe", 5, now=now, detail=newlined),
    ] + [_stall_row(50 + i, "intake", f"#{n}", 9, now=now)
         for i, n in enumerate((971, 972, 973, 974, 975))]
    split = RUNNER.stall_census_leg(batch_issues, newline_rows, read_at=read_at)
    assert split["coverage"]["units_in_population"] == 5, split["coverage"]
    assert split["coverage"]["units_named_only_as_mentions"] == 0, split["coverage"]

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

def test_arm1_a_slot_inside_its_grace_is_NOT_JUDGED_and_never_MISSED() -> None:
    """ARM 1: the false positive this unit exists to remove.

    THE STATE THAT USED TO RED. A slot arrives at 06:00Z, the daemon wakes at 06:00:35Z, and
    the old predicate read MISSED for every second in between -- for the ordinary dispatch
    latency of a healthy box. Here the slot arrived 60 s ago with no run row yet, which is
    inside this job's derived grace, so the verdict is NOT JUDGED and the leg raises no
    problem.

    The arm is not vacuous: the SAME row at the SAME grace is driven past the window in
    arm 2 below, so the quiet here is attributable to the window and not to a leg that cannot
    fire.
    """
    runs = _daily_runs("job-slow-dispatch", lateness=(35, 41, 29, 38))
    row = _cron_row("job-slow-dispatch", next_run_at="2026-10-21T06:00:00+00:00",
                    last_run_at="2026-10-20T06:00:35Z")
    now = RUNNER.reader_parse_ts("2026-10-21T06:01:00Z")
    record = RUNNER.cadence_slot_verdict_for(row, now=now, runs=_instants(row, runs))
    assert record["verdict"] == RUNNER.CADENCE_SLOT_NOT_JUDGED, record
    assert "inside this job's derived grace" in record["reason"], record
    assert record["grace"]["grace_secs"] is not None, record

    leg = RUNNER.cadence_slot_leg([row], ["ops"], [], read_at="2026-10-21T06:01:00Z",
                                  fires=runs)
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["counts"][RUNNER.CADENCE_SLOT_MISSED] == 0, leg["coverage"]

def test_arm2_PAST_its_grace_with_NO_run_row_still_reads_MISSED() -> None:
    """ARM 2, THE DISCRIMINATOR: a widened window that never fires proves nothing.

    Same job, same history, same derived grace as arm 1 -- only the read instant moves past
    `slot + grace`. If a future change widens the tolerance without keeping a way to fire,
    this arm is the one that reds.
    """
    runs = _daily_runs("job-slow-dispatch", lateness=(35, 41, 29, 38))
    row = _cron_row("job-slow-dispatch", next_run_at="2026-10-21T06:00:00+00:00",
                    last_run_at="2026-10-20T06:00:35Z")
    # The grace this fixture derives is the floor (p95 of 29-41 s is under 120 s), so 300 s
    # past the slot is unambiguously outside it.
    now = RUNNER.reader_parse_ts("2026-10-21T06:05:00Z")
    record = RUNNER.cadence_slot_verdict_for(row, now=now, runs=_instants(row, runs))
    assert record["verdict"] == RUNNER.CADENCE_SLOT_MISSED, record
    assert "PAST this job's derived grace" in record["reason"], record
    assert "no dispatch" in record["reason"], record

    leg = RUNNER.cadence_slot_leg([row], ["ops"], [], read_at="2026-10-21T06:05:00Z",
                                  fires=runs)
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "job-slow-dispatch" in leg["problems"][0], leg["problems"]
    out = RUNNER.render([leg], [], slug="owner/repo", read_at="2026-10-21T06:05:00Z",
                        issues=[])
    assert "MISSED: `job-slow-dispatch`" in out, out
    # AND THE DERIVATION IS IN THE REPORT, so the reader can audit the tolerance that let it
    # fire rather than take the verdict on faith.
    assert "grace DERIVED per job" in out, out
    assert "grace 120s [floor]" in out, out

def test_arm3_a_job_whose_run_rows_STOP_entirely_still_bites() -> None:
    """ARM 3: the genuine-stop case, which is the reason this leg exists at all.

    The job's history is intact and its grace is derivable, but its newest run is days old,
    so the slot it should have served has no record at or after it and the read instant is
    far past the grace. A leg that stayed quiet here would have traded a false positive for a
    false negative, which is the worse trade.
    """
    runs = _daily_runs("job-stopped", lateness=(35, 41, 29, 38),
                       last="2026-10-17T06:00:00+00:00")
    row = _cron_row("job-stopped", next_run_at="2026-10-21T06:00:00+00:00",
                    last_run_at="2026-10-17T06:00:35Z")
    leg = RUNNER.cadence_slot_leg([row], ["ops"], [], read_at="2026-10-21T07:00:00Z",
                                  fires=runs)
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "job-stopped" in leg["problems"][0], leg["problems"]

def test_arm5_a_shared_SILENCE_is_a_STALL_the_slot_read_cannot_see() -> None:
    """ARM 5 (#565): the retrospective read catches what the pending-slot read structurally cannot.

    THE STATE THAT USED TO BE INVISIBLE. Every job's run rows stop for hours and then resume
    in a burst. By the time any reader looks, the burst has advanced `next_run_at` in the same
    statement that wrote the run, so there is no pending slot left to judge -- the slot read
    reports NOT JUDGED and the stall is GONE from the record. The gap survives, because the
    burst could only extend it, and that is the whole argument for this read.

    THE ARM IS NOT VACUOUS: the same fixture is driven quiet in arm 6 by removing the stall,
    so the finding here is attributable to the shared silence rather than to a read that
    always fires.
    """
    rows, fires = _stall_fixture(silent_from="2026-10-20T12:00:00+00:00",
                                 silent_to="2026-10-20T21:00:00+00:00")
    read = RUNNER.cadence_stall_gaps(rows, fires,
                                     now=RUNNER.reader_parse_ts("2026-10-21T07:00:00+00:00"))
    assert read["verdict"] == "READ", read
    assert read["floor_secs"] == 3600.0, read
    assert len(read["stalls"]) == 1, read
    stall = read["stalls"][0]
    # The gap is TEN hours, not the nine of the silent window: the last pre-stall fire lands
    # at 11:00 (one hour before `silent_from`) and the first post-stall fire at 21:00.
    assert stall["gap_secs"] == 10 * 3600, stall
    assert stall["due"] == 3, stall
    assert stall["silent"] == 3, stall
    assert stall["fraction"] == 1.0, stall
    assert sorted(stall["silent_names"]) == [
        "job-hourly-0", "job-hourly-1", "job-hourly-2"], stall

    # AND IT REACHES THE LEG AS A PROBLEM, not only as coverage data: a read whose finding
    # never becomes a problem is a report nobody is told about.
    leg = RUNNER.cadence_slot_leg(rows, ["ops"], [],
                                  read_at="2026-10-21T07:00:00Z", fires=fires)
    assert any("cadence STALL" in problem for problem in leg["problems"]), leg["problems"]
    named = [problem for problem in leg["problems"] if "cadence STALL" in problem]
    assert "3 of 3 due job(s)" in named[0], named[0]
    assert "job-hourly-0" in named[0], named[0]

    out = RUNNER.render([leg], [], slug="owner/repo", read_at="2026-10-21T07:00:00Z",
                        issues=[])
    assert "retrospective gap read (#565)" in out, out
    assert "minimum detectable stall: 3600s" in out, out
    assert "`job-hourly-0`" in out, out

def test_arm6_a_HEALTHY_stream_raises_NO_stall_and_still_PRINTS_its_floor() -> None:
    """ARM 6, THE DISCRIMINATOR: a read that always fires proves nothing.

    Identical rows, identical population, identical floor as arm 5 -- only the silence is
    removed, so every job fires through the window. The read must find NO stall, and it must
    still print the derived floor, because a `0 stalls` over an undeclared floor is exactly
    the reading #565 files: it looks like coverage and states nothing.
    """
    rows, fires = _stall_fixture(silent_from="2026-10-20T12:00:00+00:00",
                                 silent_to="2026-10-20T12:00:00+00:00",
                                 before=6, after=9)
    read = RUNNER.cadence_stall_gaps(rows, fires,
                                     now=RUNNER.reader_parse_ts("2026-10-21T07:00:00+00:00"))
    assert read["verdict"] == "READ", read
    assert read["stalls"] == [], read
    assert read["floor_secs"] == 3600.0, read
    # EVERY gap in a healthy stream is exactly one hour, which equals the floor rather than
    # exceeding it, and every job fires inside each one.
    assert read["longest_gap_secs"] == 3600.0, read
    assert read["longest_gap_silent"] == 0, read

    leg = RUNNER.cadence_slot_leg(rows, ["ops"], [],
                                  read_at="2026-10-21T07:00:00Z", fires=fires)
    assert not any("cadence STALL" in problem for problem in leg["problems"]), leg["problems"]
    out = RUNNER.render([leg], [], slug="owner/repo", read_at="2026-10-21T07:00:00Z",
                        issues=[])
    assert "0 stall(s)" in out, out
    assert "minimum detectable stall: 3600s" in out, out
    assert "DERIVED as the shortest enabled period" in out, out

def test_arm7_a_SINGLE_silent_job_is_NOT_a_stall_and_the_floor_DECLINES_without_periods() -> None:
    """ARM 7: the ruling's two refusals, each measured.

    FIRST REFUSAL -- "a single sparse job's long gap is not [the stall], and must never
    trigger it". ONE job stops for nine hours while the other two keep firing: the aggregate
    stream has no gap at all, so nothing can fire. Then the same lone job is the ONLY job
    silent across a gap that DOES exist, and the due population is 1, below
    `CADENCE_STALL_MIN_DUE_JOBS` -- so the fraction, which would be 1.0, is never consulted.
    A fraction over one job cannot discriminate, which is why the floor on the population
    exists rather than a cleverer ratio.

    SECOND REFUSAL -- an undeclared floor is DECLINED, not defaulted. With no derivable
    period the read returns DECLINED and says the floor is UNDECLARED; it must NOT fall back
    to a constant, because a constant here is precisely the defect #565 files.
    """
    # (a) one job stops, two keep firing: the aggregate stream never goes quiet.
    rows, fires = [], []
    start = RUNNER.reader_parse_ts("2026-10-20T06:00:00+00:00")
    for index in range(2):
        name, row_id = f"job-steady-{index}", f"id-steady-{index}"
        rows.append(_cron_row(name, next_run_at="2026-10-21T07:00:00+00:00",
                              last_run_at="2026-10-21T06:00:00Z",
                              cron_expr="0 * * * *", timezone="UTC", row_id=row_id))
        for step in range(24):
            fires.append(_run_record(name, (start + dt.timedelta(hours=step)).isoformat(),
                                     job_id=row_id))
    lone = _cron_row("job-lone", next_run_at="2026-10-21T07:00:00+00:00",
                     last_run_at="2026-10-20T06:00:00Z", cron_expr="0 * * * *",
                     timezone="UTC", row_id="id-lone")
    rows.append(lone)
    fires.append(_run_record("job-lone", start.isoformat(), job_id="id-lone"))
    read = RUNNER.cadence_stall_gaps(rows, fires,
                                     now=RUNNER.reader_parse_ts("2026-10-21T07:00:00+00:00"))
    assert read["verdict"] == "READ", read
    assert read["stalls"] == [], read
    assert read["longest_gap_secs"] == 3600.0, read

    # (b) no derivable period -> DECLINED, never a defaulted floor.
    dead = [_cron_row("job-unparseable", next_run_at="", cron_expr="not a schedule",
                      row_id="id-dead")]
    declined = RUNNER.cadence_stall_gaps(dead, fires,
                                         now=RUNNER.reader_parse_ts("2026-10-21T07:00:00+00:00"))
    assert declined["verdict"] == "DECLINED", declined
    assert declined["floor_secs"] is None, declined
    assert "UNDECLARED" in declined["reason"], declined

    # (c) the store was NOT read is a THIRD fact, distinct from an empty store.
    unread = RUNNER.cadence_stall_gaps(rows, None,
                                       now=RUNNER.reader_parse_ts("2026-10-21T07:00:00+00:00"))
    assert unread["verdict"] == "DECLINED", unread
    assert "NOT READ" in unread["reason"], unread

def test_arm15_a_store_that_OPENED_after_the_gap_is_NOT_counted_silent() -> None:
    """ARM 15 (#570, ruling n=4366 clause 1): the false stall the coverage bound removes.

    THE STATE THAT USED TO RED, and it is the filed instance in miniature. One job has full
    coverage across the ten-hour silence; two others were created afterwards, so their first
    record sits after the gap has already closed. Without the bound all three are DUE -- their
    periods come from the SCHEDULE and need no records at all -- and all three are SILENT,
    because none of them has a record inside the gap. The read therefore reported a 3-of-3
    stall across a window in which two of the jobs did not exist.

    THE CONTROL IS IN THE SAME ARM. The fixture is rebuilt with the same three jobs and the
    same silence, changing ONLY the two late stores' opening instant to before the gap -- and
    the stall appears. So the quiet above is attributable to the bound and not to a read that
    cannot fire.
    """
    rows, fires = _coverage_fixture(coverage={"job-a": "full", "job-b": "after",
                                              "job-c": "after"})
    bounded = RUNNER.cadence_stall_gaps(
        rows, fires, now=RUNNER.reader_parse_ts("2026-10-21T07:00:00+00:00"))
    assert bounded["verdict"] == "READ", bounded
    assert bounded["longest_gap_secs"] == 10 * 3600, bounded
    assert bounded["longest_gap_due"] == 1, bounded
    assert bounded["longest_gap_silent"] == 1, bounded
    assert bounded["stalls"] == [], bounded
    # The late stores are not HIDDEN by the bound: each one's instant is carried per job.
    late = [entry for entry in bounded["coverage_bounds"]
            if entry["name"] in ("job-b", "job-c")]
    assert [entry["first_record"] for entry in late] == [
        "2026-10-20T22:00:00+00:00", "2026-10-20T22:00:00+00:00"], late

    control_rows, control_fires = _coverage_fixture(
        coverage={"job-a": "full", "job-b": "full", "job-c": "full"})
    control = RUNNER.cadence_stall_gaps(
        control_rows, control_fires, now=RUNNER.reader_parse_ts("2026-10-21T07:00:00+00:00"))
    assert control["longest_gap_due"] == 3, control
    assert control["longest_gap_silent"] == 3, control
    assert [stall["gap_secs"] for stall in control["stalls"]] == [10 * 3600], control

def test_arm16_a_job_with_ZERO_records_is_a_FINDING_and_never_silent() -> None:
    """ARM 16 (#570, ruling n=4366 clause 2): the THIRD state gets its own field.

    A job that is enabled and scheduled but has NO run record anywhere is neither due nor
    silent: it has no observable history, so nothing can be concluded about its silence.
    Dropping it would recreate the defect one bound over, because "excluded from the
    population" and "healthy" would then print identically.

    So it is reported in `never_recorded`, its own field, and the genuine stall beside it
    still reports: two jobs with full coverage are silent across the gap while the third has
    never recorded at all, and the read must name the stall (2 of 2) AND the finding (1 job)
    without confusing the two.
    """
    rows, fires = _coverage_fixture(coverage={"job-a": "full", "job-b": "full",
                                              "job-c": "never"})
    read = RUNNER.cadence_stall_gaps(
        rows, fires, now=RUNNER.reader_parse_ts("2026-10-21T07:00:00+00:00"))
    assert read["verdict"] == "READ", read
    # It IS scheduled, so it has a derivable period: the finding is not "unreadable".
    assert read["jobs_with_period"] == 3, read
    assert read["never_recorded"] == ["job-c"], read
    assert read["never_recorded_count"] == 1, read
    assert read["longest_gap_due"] == 2, read
    stalls = read["stalls"]
    assert [stall["gap_secs"] for stall in stalls] == [10 * 3600], stalls
    assert stalls[0]["silent"] == 2, stalls[0]
    assert "job-c" not in stalls[0]["silent_names"], stalls[0]

    leg = RUNNER.cadence_slot_leg(rows, ["ops"], [],
                                  read_at="2026-10-21T07:00:00Z", fires=fires)
    out = RUNNER.render([leg], [], slug="owner/repo", read_at="2026-10-21T07:00:00Z",
                        issues=[])
    assert "never recorded: 1 job(s)" in out, out
    assert "`job-c`" in out, out

def test_arm17_the_coverage_bound_is_DECLARED_beside_the_floor_not_applied_silently() -> None:
    """ARM 17 (#570, ruling n=4366 clause 3): a bound a reader cannot see is not a bound.

    `n=4319` established that an undeclared FLOOR reads as coverage -- a `0 stalls` over a
    floor nobody printed looks like a quiet box. The coverage bound has the same failure one
    over, and it is worse: without it printed, "this job was quiet" and "this job was not
    recorded yet" render identically.

    So the bound is printed with its own population, the instant each store becomes observable
    is listed PER JOB, and the never-recorded count is printed even when it is ZERO -- a field
    that only appears when it fires is a field a reader cannot tell from an absent one.
    """
    rows, fires = _coverage_fixture(coverage={"job-a": "full", "job-b": "full",
                                              "job-c": "full"})
    read = RUNNER.cadence_stall_gaps(
        rows, fires, now=RUNNER.reader_parse_ts("2026-10-21T07:00:00+00:00"))
    leg = RUNNER.cadence_slot_leg(rows, ["ops"], [],
                                  read_at="2026-10-21T07:00:00Z", fires=fires)
    out = RUNNER.render([leg], [], slug="owner/repo", read_at="2026-10-21T07:00:00Z",
                        issues=[])
    lines = out.splitlines()
    floor_at = next(index for index, line in enumerate(lines)
                    if "minimum detectable stall:" in line)
    bound_at = next(index for index, line in enumerate(lines)
                    if "coverage bound:" in line)
    # BESIDE THE FLOOR, not somewhere later: the two bounds qualify the same verdict, and a
    # reader who meets the stalls first has already formed the wrong one.
    assert bound_at == floor_at + 1, out
    assert "3 of 3 job(s) carry one" in out, out
    assert "observable from: `job-a` 2026-10-20T06:00:00+00:00" in out, out
    assert "never recorded: 0 job(s)" in out, out
    # The arm is not vacuous: this fixture DOES stall, so the bound is printed on a read that
    # found something rather than on a declined one.
    assert [stall["gap_secs"] for stall in read["stalls"]] == [10 * 3600], read
    assert "STALL:" in out, out

def test_arm8_the_unit_citation_form_is_the_SUBJECT_in_PARENTHESES_not_the_whole_message() -> None:
    """ARM 8 (#555, ruling n=4182): the discriminator is TIGHTER than the filing proposed.

    TWO LAYERS, and the second was measured AFTER the ruling. Layer one is the FORM: the
    filing proposed `git log --grep="#531"`, which scans the WHOLE message, and the ruling
    measured that on its own instance to return FIVE commits of which three are ledger and
    patrol rows merely NAMING the unit. Scoped to a parenthesised `(#NNN)` occurrence in the
    SUBJECT, three of the five fall away.

    Layer two is the half the ruling did not have: THE PARENTHESISED FORM ALONE IS STILL NOT
    ENOUGH. `ledger(#555): intake ...` and `dispatch(#552): ...` are two of the five, they
    carry the form, and they are bookkeeping rows that cite the unit they are FILING. The
    five subjects below are the ruling's measured population, copied from the pushed history,
    so this probe fails if the predicate is ever loosened back to a message scan -- and the
    second half fails it if the citation is ever credited on form alone.
    """
    # LAYER 1 -- the FORM, judged on the subject alone.
    form = {
        "score-conversion(#531): a short parse is NOT RUN, never a clean round": True,
        "ledger: close #515 on the 10-18 conversion row, and file the zero-cell scorecard read as #531": False,
        "patrol(2026-10-23T18): 23 problems, 22 legs ASSERTED -- #531 re-handed and claimed": False,
        "ledger(#555): intake -- the OWED line cannot see a fixed-but-unclosed unit, measured on #531": True,
        "dispatch(#552): first dispatch, deferred one slot while the Worker lane was mid-turn on #531": True,
    }
    hits = {s: bool(RUNNER.UNIT_CITATION_RE.search(s)) for s in form}
    assert hits == form, (
        "the unit-citation FORM is the parenthesised subject form only -- a bare mention of "
        f"the unit in a subject is not the citation form: {hits}"
    )
    # The capture is the UNIT NUMBER, and the map key is built from it.
    assert RUNNER.UNIT_CITATION_RE.search("score-conversion(#531): x").group(1) == "531"

    # LAYER 2 -- the WORK, judged on the real commits the five subjects belong to. Three of
    # the five carry the form; only ONE of them changes a path outside `evidence/`.
    cites = RUNNER.stall_unit_citations()
    assert cites, "the citation map must build over this repo's own pushed history"
    assert [sha for sha, _ in cites.get("#531", [])] == ["9e00791a"], (
        "#531's citation must be the FIX and nothing else -- the ruling measured exactly one, "
        f"got {cites.get('#531')}"
    )
    # THE BOOKKEEPING FILTER, judged on the unit that carries BOTH rows. The earlier version
    # of this arm asserted `"#555" not in cites`, true while #555 had no work commit -- and
    # then the fix LANDED, citing the unit and changing `tools/`, so the arm red-ed on its
    # own subject's repair. The property was never "no entry": it is that the row which
    # FILED a unit can never discharge it. So the intake row is located in history and its
    # ABSENCE from the map is the assertion -- a filter loosened back to form-alone would
    # put `4810aaf4` straight back in.
    # SUBJECT-ONLY, and this probe learned it the hard way: `git log --grep` scans the WHOLE
    # message, so `--grep 'ledger(#555)'` returned the FIX commit as well -- its body
    # discusses the intake row it must exclude. That is #555's own defect reproduced inside
    # the probe built to test it, which is why the row is located by its subject prefix here
    # and never by a message scan.
    history = subprocess.run(
        ["git", "log", "origin/main", "--format=%h%x1f%s"],
        cwd=str(RUNNER.REPO), capture_output=True, text=True, timeout=120,
    ).stdout.splitlines()
    intake = next(
        (sha for sha, _, subject in (line.partition("\x1f") for line in history)
         if subject.startswith("ledger(#555)")), "",
    )[:8]
    assert intake, "the #555 intake row is in this repo's history -- the probe is aimed at it"
    assert intake not in [sha for sha, _ in cites.get("#555", [])], (
        "the #555 INTAKE row discharges the unit it filed -- the filter must exclude a "
        f"commit that touches nothing but {RUNNER.UNIT_CITATION_BOOKKEEPING_PREFIX}"
    )
    # ...and the fix, which changes `tools/`, MUST be credited: the filter excludes the row
    # and keeps the repair, and an arm that only tested exclusion would pass on a filter
    # that excluded everything.
    assert cites.get("#555"), "#555's repair cites the unit; an empty entry means the filter ate it"
    assert [sha for sha, _ in cites.get("#552", [])] == ["45394852"], (
        "#552's citation must be its WORK commit, not its dispatch row, got "
        f"{cites.get('#552')}"
    )

def test_arm9_a_cited_unit_reads_OWED_CLOSE_and_the_RE_HAND_is_WITHDRAWN() -> None:
    """ARM 9 (#555): the remedy is the finding. Two debts, two prescriptions.

    A fixed-but-unclosed unit is a BOOKKEEPING debt. The line must (a) be labelled
    OWED-CLOSE rather than OWED, (b) PRINT the citing sha and subject so a reader can tell a
    fix from a filing, (c) carry the close remedy, and (d) NOT carry the re-hand remedy --
    which is the whole defect, because a re-hand sent a lane to re-open finished work.

    The sibling unit with no citation must keep the re-hand, or the discriminator would
    swallow the work-owed class whole.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(901, "OPEN"), _issue(902, "OPEN")]
    rows = [
        _stall_row(1, "dispatch", "#901", 3, now=now),
        _stall_row(2, "dispatch", "#902", 3, now=now),
    ]
    cites = {"#901": [("9e00791a", "score-conversion(#901): the fix")]}

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at,
                                  unit_citations_fn=lambda: cites)
    named = "\n".join(leg["problems"])
    assert "OWED-CLOSE #901" in named, f"a cited unit must read OWED-CLOSE\n{named}"
    assert "9e00791a" in named and "score-conversion(#901)" in named, (
        f"the citing commit's sha AND subject must be PRINTED, never concluded from\n{named}"
    )
    assert "WITHDRAWN" in named, f"the re-hand prescription must be withdrawn\n{named}"
    assert "Re-hand it OLDEST FIRST" not in named, (
        f"a re-hand on a fixed-but-unclosed unit re-opens finished work\n{named}"
    )
    # (e) the discriminating arm: an uncited unit keeps the work remedy.
    assert "OWED #902" in named, f"an uncited unit is still work owed\n{named}"
    assert "Re-hand it OLDEST FIRST" in named or "Re-dispatch" in named, (
        f"the work-owed remedy must survive for an uncited unit\n{named}"
    )
    # (f) the two debts are counted separately and never summed.
    assert leg["coverage"]["owed_close_units"] == 1, leg["coverage"]
    assert leg["coverage"]["unit_citation_commits_examined"] == 1, leg["coverage"]

def test_arm10_a_commit_CITATION_is_not_a_claim_and_cannot_discharge_one() -> None:
    """ARM 10 (#555 caution 2): the check must not become a second claim leg.

    `tools/ledger.py verify` owns the claim sequence. A cited unit must still appear in the
    census -- the label changes the REMEDY, never the population -- and a unit whose only
    discharge is a commit must still be reported. If this ever returns an empty problem list
    the citation has silently become a completion, which is the failure `#529` proves is real.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(901, "OPEN")]
    rows = [_stall_row(1, "dispatch", "#901", 3, now=now)]
    cites = {"#901": [("deadbeef", "area(#901): a commit that says nothing about done")]}

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at,
                                  unit_citations_fn=lambda: cites)
    assert leg["coverage"]["units_owed"] == 1, (
        f"a citation must not remove the unit from the population: {leg['coverage']}"
    )
    assert any("#901" in p for p in leg["problems"]), (
        "a citation is not a completion -- the unit must still be REPORTED"
    )
    # An unreadable map is the CONSERVATIVE direction: plain OWED, remedy intact.
    blind = RUNNER.stall_census_leg(issues, rows, read_at=read_at,
                                    unit_citations_fn=lambda: {})
    assert "OWED #901" in "\n".join(blind["problems"]), (
        "with no citation map the unit must read plain OWED -- a read that could not be "
        "made must never withdraw a remedy on evidence nobody read"
    )
    assert blind["coverage"]["owed_close_units"] == 0, blind["coverage"]

def test_arm11_a_tree_only_row_AT_LEVEL_is_named_and_NEVER_becomes_a_problem() -> None:
    """ARM 11: the #559 contradiction, and the reason it may not be a problem line.

    A reset leaves the rows in the working tree and the commits unreachable, so
    `rev-list --left-right --count` reads `0 0` and the pusher's own `in-sync` -- that same
    count -- is satisfied while the rows exist nowhere on the base. The leg NAMES the rows.

    It carries NO problem, and that is the point: a lane's uncommitted append produces the
    identical read (measured live at `0 0`, tree 4360 vs base 4359, the extra row a claim
    stamped minutes earlier), so a problem here would be red on a healthy tree -- #83's
    class. Ruling n=4232: the leg reports the numbers, the reader decides.
    """
    leg = RUNNER.row_set_leg(
        read_at="2026-10-27T02:40:00Z",
        level_fn=lambda repo, base: (0, 0, None),
        tree_fn=lambda repo, path: ([4358, 4359, 4360], None),
        remote_fn=lambda repo, base, path: ([4358, 4359], None),
    )
    cov = leg["coverage"]
    assert leg["status"] == "ASSERTED", leg
    assert cov["level"] is True, cov
    assert cov["tree_only"] == [4360], cov
    assert cov["remote_only"] == [], cov
    assert cov["rows_examined"] == 3, cov
    # THE ARM THAT MATTERS: a named contradiction is still not a problem.
    assert leg["problems"] == [], leg
    assert leg["excused"] == [], leg
    assert "reader decides" in cov["verdict"], cov["verdict"]

    out = RUNNER.render([leg], [], slug="owner/repo", read_at="2026-10-27T02:40:00Z",
                        issues=[])
    assert "row-set leg" in out, out
    assert "n=4360" in out, out
    assert "0/0" in out, out
    assert "AT LEVEL" in out, out
    assert "recoverable:" in out, out   # the route is printed, not merely referenced
    assert "problems: 0" in out, out

def test_arm12_an_ordinary_UNPUSHED_append_reads_its_LEVEL_and_is_not_the_defect() -> None:
    """ARM 12: the same row list ahead of the base is ordinary work in flight.

    The count alone cannot tell these two apart -- that is exactly the defect -- so the
    LEVEL must travel beside it and the render must say which reading applies. A leg that
    printed "1 row in the tree and not on origin/main" with no level would be
    indistinguishable from the incident it was built for.
    """
    leg = RUNNER.row_set_leg(
        read_at="2026-10-27T02:40:00Z",
        level_fn=lambda repo, base: (2, 0, None),
        tree_fn=lambda repo, path: ([4359, 4360, 4361], None),
        remote_fn=lambda repo, base, path: ([4359], None),
    )
    cov = leg["coverage"]
    assert leg["status"] == "ASSERTED", leg
    assert cov["level"] is False, cov
    assert cov["tree_only"] == [4360, 4361], cov
    assert leg["problems"] == [], leg

    out = RUNNER.render([leg], [], slug="owner/repo", read_at="2026-10-27T02:40:00Z",
                        issues=[])
    assert "2/0" in out, out
    assert "not level" in out, out
    assert "work in flight" in out, out
    # The AT LEVEL paragraph is the defect's own reading and must NOT appear here.
    assert "AT LEVEL" not in out, out

def test_arm13_a_read_that_CANNOT_be_made_is_NOT_RUN_with_its_reason() -> None:
    """ARM 13: a zero standing in for "could not look" is what made the incident silent.

    Every dependency is injected, so each of the three failure points must produce NOT RUN
    WITH A REASON rather than an empty set that renders as a clean round.
    """
    for kwargs in (
        {"level_fn": lambda repo, base: (0, 0, "no such base ref: origin/main")},
        {"level_fn": lambda repo, base: (0, 0, None),
         "tree_fn": lambda repo, path: ([], "ledger unreadable")},
        {"level_fn": lambda repo, base: (0, 0, None),
         "tree_fn": lambda repo, path: ([1], None),
         "remote_fn": lambda repo, base, path: ([], "base ref unreadable")},
    ):
        leg = RUNNER.row_set_leg(read_at="2026-10-27T02:40:00Z", **kwargs)
        assert leg["status"] == "NOT RUN", leg
        assert leg["problems"] == [], leg
        reason = leg["coverage"]["reason"]
        assert reason, leg
        out = RUNNER.render([leg], [], slug="owner/repo", read_at="2026-10-27T02:40:00Z",
                            issues=[])
        assert "NOT RUN" in out, out
        assert reason in out, out
        # A NOT RUN round must never print a row population: there is none.
        assert "row(s) in the tree and NOT on" not in out, out

def test_arm14_a_clean_claim_requires_a_census_that_LOOKED() -> None:
    """ARM 14 (#595): a clean claim may never follow an admitted INABILITY.

    The defect this arm exists for was live in the render: with 31 registrations seen
    and ZERO probed, the block printed "registrations: INCOMPLETE -- ... an INABILITY,
    not a clean result" and then, two lines below it, "no STRANDED commit: every
    registration ahead of the base is carried by a ref". A clean claim emitted after an
    admitted inability is the exact collapse the leg was built to end, wearing the
    report's own words.

    FIVE SHAPES, and the CLEAN one is the only shape allowed to claim anything. The
    others are the same four empty lists under different reasons for not having looked,
    which is why they are one arm: a zero and an unread value are the same number and
    different facts.
    """
    cases = (
        # (label, overrides, expect_clean_claims)
        ("UNREAD -- never attempted", {}, False),
        ("CLEAN -- 31 seen, 31 probed, nothing found", {
            "registrations": 31, "registrations_probed": 31,
            "rows_off_base": [], "rows_off_base_count": 0,
            "ahead_of_base": [], "ahead_of_base_count": 0,
            "stranded": [], "stranded_count": 0,
            "loss_risk": [], "loss_risk_count": 0,
            "registration_errors": [],
        }, True),
        ("ENUMERATION-FAILED -- git could not be read", {
            "registrations_error": "git worktree list --porcelain failed: exit 128",
        }, False),
        ("READ-BUT-UNPROBED -- 31 seen, 0 probed", {
            "registrations": 31, "registrations_probed": 0,
            "rows_off_base": [], "rows_off_base_count": 0,
            "ahead_of_base": [], "ahead_of_base_count": 0,
            "stranded": [], "stranded_count": 0,
            "loss_risk": [], "loss_risk_count": 0,
            "registration_errors": [],
        }, False),
        ("PARTIAL -- 31 seen, 30 probed, 1 error", {
            "registrations": 31, "registrations_probed": 30,
            "rows_off_base": [], "rows_off_base_count": 0,
            "ahead_of_base": [], "ahead_of_base_count": 0,
            "stranded": [], "stranded_count": 0,
            "loss_risk": [], "loss_risk_count": 0,
            "registration_errors": ["/tmp/x/tree: the registration carries no HEAD"],
        }, False),
    )
    for label, overrides, expect_clean in cases:
        out = RUNNER.render_row_set(
            {"name": "row-set", "status": "ASSERTED", "problems": [], "excused": [],
             "coverage": _row_set_cov(**overrides)}
        )
        claims = _row_set_claims(out)
        if expect_clean:
            assert claims == list(_ROW_SET_CLEAN_CLAIMS), (label, claims, out)
        else:
            assert claims == [], (
                f"{label}: a clean claim was printed by a census that did not look: "
                f"{claims}\n" + "\n".join(out)
            )
            # And the refusal must be STATED, not merely withheld: four unread values
            # render as four "unstated" lines, so the silence is legible.
            assert "\n".join(out).count("unstated (not read)") >= 4, (label, out)
    # The two shapes that ADMIT an inability say so in words the reader can act on.
    for overrides, fragment in (
        ({"registrations_error": "git worktree list --porcelain failed: exit 128"},
         "COULD NOT BE ENUMERATED"),
        ({"registrations": 31, "registrations_probed": 0,
          "rows_off_base": [], "ahead_of_base": [], "stranded": [], "loss_risk": []},
         "INCOMPLETE"),
    ):
        out = "\n".join(RUNNER.render_row_set(
            {"name": "row-set", "status": "ASSERTED", "problems": [], "excused": [],
             "coverage": _row_set_cov(**overrides)}
        ))
        assert fragment in out, (fragment, out)

def test_arm15_a_STRANDED_commit_is_named_by_path_and_sha() -> None:
    """ARM 15 (#595): a commit carried by NO ref is named, and is still not a problem.

    The live casualty this arm was written against (2026-11-01): one lane worktree one
    commit ahead of the base and carried by ZERO refs -- one `git worktree prune` from
    gone, and `fsck` cannot see it for 30 days. The leg must name the path, the sha, the
    subject and the ref count. The sha below is FABRICATED on purpose: this file is a
    TEMPLATE pair and ships to factories whose history does not contain ours, so citing a
    real commit would make the pair non-portable (a probe asserting on a sha the reader's
    repo has never seen).

    It carries NO problem: a registration ahead of base is the DESIGNED state for a lane
    worktree (SKILL.md §Briefing and dispatch), so STRANDED is a naming and the reader decides (#559 ruling
    n=4232). The finding is a fact about reachability, not a verdict about the lane.
    """
    stranded_entry = {
        "path": "/tmp/gate-select-wtk06ses/tree",
        "sha": "9f9e9d9c9b9a9989796959493929190897867564",
        "oldest_sha": "9f9e9d9c9b9a9989796959493929190897867564",
        "oldest_committed_at": "2026-11-01T19:29:03+00:00",
        "oldest_subject": "sync_binding: a clean tree inside the pusher grace window is HELD, not refused (#594)",
        "ahead": 1,
        "ref_count": 0,
        "directory_present": True,
        "pusher_checkout": False,
        "stranded": True,
        "loss_risk": False,
    }
    leg = RUNNER.row_set_leg(
        read_at="2026-11-01T20:00:00Z",
        level_fn=lambda repo, base: (0, 0, None),
        tree_fn=lambda repo, path: ([4593], None),
        remote_fn=lambda repo, base, path: ([4593], None),
        registrations_fn=lambda repo, base, base_rows, **kw: ({
            "registrations": 31, "registrations_probed": 31,
            "rows_off_base": [], "rows_off_base_count": 0,
            "ahead_of_base": [stranded_entry], "ahead_of_base_count": 1,
            "stranded": [stranded_entry], "stranded_count": 1,
            "loss_risk": [], "loss_risk_count": 0,
            "errors": [],
        }, None),
    )
    cov = leg["coverage"]
    assert leg["status"] == "ASSERTED", leg
    assert cov["stranded_count"] == 1, cov
    assert cov["ahead_of_base_count"] == 1, cov
    assert cov["loss_risk_count"] == 0, cov
    # THE ARM THAT MATTERS: a named casualty is still not a problem line.
    assert leg["problems"] == [], leg
    assert leg["excused"] == [], leg

    out = "\n".join(RUNNER.render_row_set(leg))
    assert "1 STRANDED commit(s)" in out, out
    assert "/tmp/gate-select-wtk06ses/tree" in out, out          # the PATH
    assert "9f9e9d9c9b9a" in out, out                            # the SHA
    assert "carried by 0 ref(s)" in out, out                     # the reachability
    assert "one 'git worktree prune' deletes them" in out, out    # the consequence
    assert "HELD, not refused" in out, out                       # the subject
    # The clean STRANDED claim must NOT be printed beside a real stranded commit.
    assert "no STRANDED commit" not in [ln.strip() for ln in out.splitlines()], out

def test_arm16_a_LOSS_RISK_registration_names_its_ABSENT_directory() -> None:
    """ARM 16 (#595): ahead of base AND the directory gone -- the only copy of the commit.

    This is the strictly worse sibling of STRANDED: the commit is carried by no ref AND
    the working tree that held it is gone, so the object is the last copy anywhere. The
    leg names the path and the sha with `directory ABSENT`, and still files no problem.
    """
    loss_entry = {
        "path": "/tmp/af-reaped-1029",
        "sha": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        "oldest_sha": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        "oldest_committed_at": "2026-10-29T08:00:00+00:00",
        "oldest_subject": "a commit whose tree is gone",
        "ahead": 2,
        "ref_count": 0,
        "directory_present": False,
        "pusher_checkout": False,
        "stranded": True,
        "loss_risk": True,
    }
    leg = RUNNER.row_set_leg(
        read_at="2026-11-01T20:00:00Z",
        level_fn=lambda repo, base: (0, 0, None),
        tree_fn=lambda repo, path: ([4593], None),
        remote_fn=lambda repo, base, path: ([4593], None),
        registrations_fn=lambda repo, base, base_rows, **kw: ({
            "registrations": 31, "registrations_probed": 31,
            "rows_off_base": [], "rows_off_base_count": 0,
            "ahead_of_base": [loss_entry], "ahead_of_base_count": 1,
            "stranded": [loss_entry], "stranded_count": 1,
            "loss_risk": [{"path": loss_entry["path"], "sha": loss_entry["sha"],
                           "ahead": 2}],
            "loss_risk_count": 1,
            "errors": [],
        }, None),
    )
    cov = leg["coverage"]
    assert cov["loss_risk_count"] == 1, cov
    assert leg["problems"] == [], leg

    out = "\n".join(RUNNER.render_row_set(leg))
    assert "1 LOSS RISK registration(s)" in out, out
    assert "/tmp/af-reaped-1029" in out, out
    assert "deadbeefdead" in out, out
    assert "directory ABSENT" in out, out
    assert "the directory is GONE" in out, out
    assert "no LOSS RISK registration" not in [ln.strip() for ln in out.splitlines()], out

def test_arm17_an_EMPTY_census_is_an_INSTRUMENT_FAILURE_not_a_repository() -> None:
    """ARM 17 (#595): a repository always has at least its main worktree.

    So `git worktree list --porcelain` returning no record is the INSTRUMENT failing, not
    a repository with nothing registered -- and the leg must say so rather than hand back
    an empty set that renders as a clean census. Same law as every other leg here: a zero
    standing in for "could not look" is what made the incident silent.

    The seam is `worktree_records`, not a kwarg: `row_set_registrations` calls it
    directly, so patching it is the only way to drive the census without a live repo.
    """
    with mock.patch.object(RUNNER, "worktree_records", lambda repo=None: ([], None)):
        findings, error = RUNNER.row_set_registrations(Path("."), "origin/main", set())
    assert findings is None, findings
    assert error, error
    assert "instrument failure" in error, error
    assert "at least its main worktree" in error, error

    # The census read ITSELF failing is the same class, with its own reason.
    with mock.patch.object(RUNNER, "worktree_records",
                           lambda repo=None: (None, "fatal: not a git repository")):
        findings, error = RUNNER.row_set_registrations(Path("."), "origin/main", set())
    assert findings is None, findings
    assert "could not be read" in error, error
    assert "fatal: not a git repository" in error, error

def test_arm4_the_grace_is_DERIVED_per_job_and_PRINTED_with_its_derivation() -> None:
    """ARM 4: a hardcoded constant must be unable to produce these numbers.

    TWO JOBS, TWO HISTORIES, TWO GRACES, driven through the same leg at the same instant. A
    shared literal cannot satisfy both arms, so the pair is the control: one job's p95 sits
    above the floor (its own lateness decides), the other's sits below it (the floor binds).
    The render must carry BOTH values and the basis that produced each.
    """
    fast = _daily_runs("job-fast", lateness=(30, 33, 28, 31), job_id="id-fast")
    slow = _daily_runs("job-slower", lateness=(300, 330, 280, 310), job_id="id-slow")
    fast_row = _cron_row("job-fast", next_run_at="2026-10-21T06:00:00+00:00",
                         last_run_at="2026-10-20T06:00:30Z", row_id="id-fast")
    slow_row = _cron_row("job-slower", next_run_at="2026-10-21T06:00:00+00:00",
                         last_run_at="2026-10-20T06:05:30Z", row_id="id-slow")

    fast_grace = RUNNER.cadence_grace_for(fast_row, _instants(fast_row, fast))
    slow_grace = RUNNER.cadence_grace_for(slow_row, _instants(slow_row, slow))
    assert fast_grace["grace_secs"] == RUNNER.CADENCE_GRACE_FLOOR_SECS, fast_grace
    assert fast_grace["basis"] == "floor", fast_grace
    assert slow_grace["grace_secs"] > fast_grace["grace_secs"], (fast_grace, slow_grace)
    assert slow_grace["basis"] == "p95", slow_grace
    # NO SHARED LITERAL COULD PRODUCE BOTH: the two values differ, and the slower job's is
    # the one its own history produced rather than a constant that happens to sit near it.
    assert slow_grace["grace_secs"] != fast_grace["grace_secs"], (fast_grace, slow_grace)

    leg = RUNNER.cadence_slot_leg([fast_row, slow_row], ["ops"], [],
                                  read_at="2026-10-21T05:00:00Z", fires=fast + slow)
    graces = {entry["name"]: entry for entry in leg["coverage"]["graces"]}
    assert graces["job-fast"]["grace_secs"] == RUNNER.CADENCE_GRACE_FLOOR_SECS, graces
    assert graces["job-slower"]["grace_secs"] == slow_grace["grace_secs"], graces
    out = RUNNER.render([leg], [], slug="owner/repo", read_at="2026-10-21T05:00:00Z",
                        issues=[])
    assert "grace 120s [floor]" in out, out
    assert f"grace {slow_grace['grace_secs']:.0f}s [p95]" in out, out
    # The derivation itself travels: sample size and the p95 behind the number.
    assert "sample 4" in out, out

def test_arm4b_the_CAP_and_the_PERIOD_clamp_both_bind_and_both_are_named() -> None:
    """ARM 4's bounds, which the ruling required to be STATED rather than implied.

    A tail that would exceed the cap is clamped to it, and a job whose period is shorter than
    the clamped value is clamped again to a fraction of its own period -- with
    `basis="period"` and `period_bound_binds` travelling, because that is the arm where the
    verdict is a coin flip by construction and a reader has to be told so.
    """
    wild = _daily_runs("job-wild", lateness=(4000, 4200, 3900, 4100))
    row = _cron_row("job-wild", next_run_at="2026-10-21T06:00:00+00:00",
                    last_run_at="2026-10-20T07:08:00Z")
    grace = RUNNER.cadence_grace_for(row, _instants(row, wild))
    assert grace["grace_secs"] == RUNNER.CADENCE_GRACE_CAP_SECS, grace
    assert grace["basis"] == "cap", grace

    # A 30-minute job (`15,45 * * * *`) whose tail exceeds half its period: 1800 s period, so
    # the period clamp lands at 900 s -- under the cap, which makes `period` the binding one.
    every_half_hour = [
        _run_record("job-halflhour", f"2026-10-20T{h:02d}:{m:02d}:{s:02d}+00:00")
        for h, m, s in ((5, 45, 40), (6, 15, 50), (6, 45, 45), (7, 15, 35))
    ]
    half_row = _cron_row("job-halflhour", next_run_at="2026-10-20T07:45:00+00:00",
                         last_run_at="2026-10-20T07:15:35Z", cron_expr="15,45 * * * *")
    half_grace = RUNNER.cadence_grace_for(half_row, _instants(half_row, every_half_hour))
    assert half_grace["period_secs"] == 1800.0, half_grace
    assert half_grace["grace_secs"] <= half_grace["period_secs"] * \
        RUNNER.CADENCE_GRACE_PERIOD_FRACTION, half_grace

def test_arm5_HELD_cannot_reappear_and_its_RETIREMENT_is_printed() -> None:
    """ARM 5: a retired verdict must be GONE and SAID to be gone.

    Three separate readings, because each one alone can be satisfied while the defect
    survives: the bucket is absent from the verdict vocabulary, the module exposes no `HELD`
    constant for a future reader to reach for, and the report PRINTS the retirement -- an
    absent bucket and a bucket that cannot fire render identically, and the second is the
    defect.
    """
    assert "HELD" not in RUNNER.CADENCE_SLOT_VERDICTS, RUNNER.CADENCE_SLOT_VERDICTS
    assert not hasattr(RUNNER, "CADENCE_SLOT_HELD"), "the retired constant is still exported"
    retired = dict(RUNNER.CADENCE_SLOT_RETIRED)
    assert "HELD" in retired, retired
    assert "scheduler.rs" in retired["HELD"], retired

    # A FIXTURE THAT WOULD HAVE SATISFIED THE OLD PRECONDITION. `last_run_at` is AFTER
    # `next_run_at` here -- the shape `HELD` required and the writer cannot produce. It must
    # now read DISPATCHED (a run row decides it), and it must NOT resurrect a bucket.
    runs = _daily_runs("job-would-be-held", lateness=(35, 41, 29, 38))
    row = _cron_row("job-would-be-held", next_run_at="2026-10-20T06:00:00+00:00",
                    last_run_at="2026-10-20T06:00:35Z")
    record = RUNNER.cadence_slot_verdict_for(
        row, now=RUNNER.reader_parse_ts("2026-10-21T07:00:00Z"), runs=_instants(row, runs))
    assert record["verdict"] == RUNNER.CADENCE_SLOT_DISPATCHED, record

    leg = RUNNER.cadence_slot_leg([row], ["ops"], [],
                                  read_at="2026-10-21T07:00:00Z", fires=runs)
    counts = leg["coverage"]["counts"]
    assert "HELD" not in counts, counts
    assert counts[RUNNER.CADENCE_SLOT_DISPATCHED] == 1, counts
    out = RUNNER.render([leg], [], slug="owner/repo", read_at="2026-10-21T07:00:00Z",
                        issues=[])
    assert "RETIRED verdict `HELD`" in out, out
    # The totals line names the four live buckets and no retired one, so a reader scanning
    # the counts cannot mistake the absence for a zero.
    assert "HELD 0" not in out, out
    assert "DISPATCHED 1" in out, out

def test_the_verdict_does_NOT_depend_on_the_write_order_of_the_two_columns() -> None:
    """THE EVIDENCE SOURCE, which is the half of #543 that has nothing to do with timing.

    `last_run_at` here is BEFORE the slot -- the exact state the old predicate read as MISSED
    -- while `cron_job_runs` records a dispatch 35 s after it. The row is DISPATCHED, because
    a run RECORD answers the question and a column's value does not. This is the arm that
    would still pass if the grace were set to zero, which is why it is separate from arms 1-3.
    """
    runs = [_run_record("job-lagging-column", "2026-10-21T06:00:35+00:00")]
    row = _cron_row("job-lagging-column", next_run_at="2026-10-21T06:00:00+00:00",
                    last_run_at="2026-10-20T06:00:27Z")
    record = RUNNER.cadence_slot_verdict_for(
        row, now=RUNNER.reader_parse_ts("2026-10-21T06:01:00Z"), runs=_instants(row, runs))
    assert record["verdict"] == RUNNER.CADENCE_SLOT_DISPATCHED, record
    assert "recorded in cron_job_runs" in record["reason"], record

def test_an_UNDERTAKABLE_grace_is_NOT_JUDGED_rather_than_invented() -> None:
    """A tolerance invented for a job whose history could not be read is the defect, not the fix.

    Three shapes, each refused with its own reason: no dispatch history at all, a schedule
    this reader cannot parse, and a schedule whose parse cannot reproduce the scheduler's own
    stored slot (the independent-declaration guard). The last one is the important arm: it is
    what caught this box's non-POSIX day-of-week numbering, and it must keep refusing rather
    than fall back to a guess.
    """
    row = _cron_row("job-no-history", next_run_at="2026-10-21T06:00:00+00:00",
                    last_run_at="2026-10-20T06:00:27Z")
    grace = RUNNER.cadence_grace_for(row, [])
    assert grace["grace_secs"] is None, grace
    assert "no dispatch record" in grace["reason"], grace

    record = RUNNER.cadence_slot_verdict_for(
        row, now=RUNNER.reader_parse_ts("2026-10-21T07:00:00Z"), runs=[])
    assert record["verdict"] == RUNNER.CADENCE_SLOT_NOT_JUDGED, record
    assert record["grace_underivable"] is True, record
    assert "UNDERTAKABLE" in record["reason"], record

    # A schedule this reader cannot parse is refused, not approximated.
    unparseable = _cron_row("job-bad-expr", next_run_at="2026-10-21T06:00:00+00:00",
                            cron_expr="0 9 * * * *")
    runs = _daily_runs("job-bad-expr", lateness=(30, 40))
    assert RUNNER.cadence_grace_for(
        unparseable, _instants(unparseable, runs))["grace_secs"] is None

    # THE INDEPENDENT DECLARATION: `next_run_at` says the 21st, this row's expression says a
    # different day, so the parse is not trustworthy and no grace comes out of it.
    disagreeing = _cron_row("job-disagreeing", next_run_at="2026-10-21T06:00:00+00:00",
                            cron_expr="0 9 1 * *")
    disagreeing_runs = _daily_runs("job-disagreeing", lateness=(30, 40))
    grace = RUNNER.cadence_grace_for(disagreeing, _instants(disagreeing, disagreeing_runs))
    assert grace["grace_secs"] is None, grace
    assert "does not reproduce" in grace["reason"], grace

def test_the_SCHEDULER_day_of_week_dialect_is_1_is_SUNDAY_not_POSIX() -> None:
    """The dialect this box actually schedules in, pinned so a future reader cannot "fix" it.

    Measured 2026-10-22: `ai-antispam-wave0-unactivated-reprobe` carries `0 12 * * 2` and the
    scheduler stored `2026-10-26T09:00:00+00:00` -- a MONDAY. Under POSIX numbering `2` is
    Tuesday, so a POSIX reading would place that job's boundaries a day off and report every
    dispatch as ~24 h late. Named days cannot discriminate the two dialects, which is exactly
    why a numeric fixture is used here.
    """
    assert dt.date(2026, 10, 26).weekday() == 0, "the fixture date must be a Monday"
    parsed = RUNNER.parse_cron_expr("0 12 * * 2")
    monday = RUNNER.reader_parse_ts("2026-10-26T12:00:00+00:00")
    assert RUNNER.cron_boundary_matches(monday, parsed), "dow=2 must match a Monday"
    tuesday = RUNNER.reader_parse_ts("2026-10-27T12:00:00+00:00")
    assert not RUNNER.cron_boundary_matches(tuesday, parsed), "dow=2 must NOT match a Tuesday"
    # And a named day lands on the same weekday its name says, in the same dialect.
    assert RUNNER.cron_boundary_matches(
        RUNNER.reader_parse_ts("2026-10-26T09:00:00+00:00"),
        RUNNER.parse_cron_expr("0 9 * * Mon"))

def test_the_leg_CAN_fire_and_the_population_is_ALWAYS_printed() -> None:
    """The positive control, plus the empty-population arm it is paired with.

    The empty read is the second half: `examined 0` must render as NOT RUN with its reason,
    never as a clean round, because a predicate that examined nothing has not been shown to
    work (skill section 8).
    """
    runs = _daily_runs("job-overdue", lateness=(35, 41))
    missed = _cron_row("job-overdue", next_run_at="2026-10-21T06:00:00+00:00",
                       last_run_at="2026-10-20T06:00:27Z")
    leg = RUNNER.cadence_slot_leg([missed], ["ops"], [], read_at="2026-10-21T07:00:00Z",
                                  fires=runs)
    assert leg["status"] == "ASSERTED", leg
    assert leg["coverage"]["examined"] == 1, leg["coverage"]
    assert leg["coverage"]["counts"][RUNNER.CADENCE_SLOT_MISSED] == 1, leg["coverage"]

    empty = RUNNER.cadence_slot_leg([], [], ["ops: unable to open database file"],
                                    read_at="2026-10-21T07:00:00Z")
    assert empty["status"] == "NOT RUN", empty
    assert empty["problems"] == [], empty
    assert "NOT a clean round" in empty["coverage"]["reason"], empty["coverage"]
    out = RUNNER.render([empty], [], slug="owner/repo", read_at="2026-10-21T07:00:00Z",
                        issues=[])
    assert "examined: 0" in out, out
    assert "ops: unable to open database file" in out, out

def test_no_runs_store_supplied_is_UNREADABLE_never_MISSED() -> None:
    """The injection boundary, held to #271.

    A leg handed no `cron_job_runs` store has not been told whether anything was dispatched.
    Reporting that as MISSED would red every job in any probe that forgot the argument, and
    reporting it as DISPATCHED would be a false clean -- so it is UNREADABLE with its reason,
    which is the only reading that says "I could not answer".
    """
    row = _cron_row("job-no-store", next_run_at="2026-10-21T06:00:00+00:00")
    record = RUNNER.cadence_slot_verdict_for(
        row, now=RUNNER.reader_parse_ts("2026-10-21T07:00:00Z"), runs=None)
    assert record["verdict"] == RUNNER.CADENCE_SLOT_UNREADABLE, record
    assert "no cron_job_runs store was supplied" in record["reason"], record

    leg = RUNNER.cadence_slot_leg([row], ["ops"], [], read_at="2026-10-21T07:00:00Z")
    assert leg["coverage"]["counts"][RUNNER.CADENCE_SLOT_UNREADABLE] == 1, leg["coverage"]
    assert leg["problems"] == [], leg["problems"]
    out = RUNNER.render([leg], [], slug="owner/repo", read_at="2026-10-21T07:00:00Z",
                        issues=[])
    assert "UNREADABLE: `job-no-store`" in out, out

def test_a_slot_that_has_NOT_ARRIVED_is_NOT_JUDGED_and_carries_no_verdict_of_its_own() -> None:
    """The order of the tests, which is the law and not a preference.

    This is the exact case that produced the retracted Miidas section 8 remedy: a FUTURE slot
    read as a miss. The row carries a `last_run_at` BEFORE its next slot, the ordinary healthy
    state of every job on the box.
    """
    runs = _daily_runs("job-future", lateness=(35, 41))
    row = _cron_row("job-future", next_run_at="2026-10-21T06:00:00+00:00",
                    last_run_at="2026-10-20T06:00:27Z")
    # The grace is supplied the way the LEG supplies it, because it is a property of the job
    # and the leg derives it for every row before any verdict is reached.
    grace = RUNNER.cadence_grace_for(row, _instants(row, runs))
    record = RUNNER.cadence_slot_verdict_for(
        row, now=RUNNER.reader_parse_ts("2026-10-21T03:00:00Z"),
        runs=_instants(row, runs), grace=grace)
    assert record["verdict"] == RUNNER.CADENCE_SLOT_NOT_JUDGED, record
    assert "has not arrived" in record["reason"], record
    # AND THE GRACE STILL TRAVELS: it is a property of the JOB, so a healthy population --
    # where every slot is in the future -- still prints the derivation it was judged against.
    assert record["grace"]["grace_secs"] is not None, record

def test_an_all_NOT_JUDGED_population_is_ASSERTED_and_says_NOTHING_OVERDUE() -> None:
    """The healthy-box shape, which is the population this leg sees almost every day.

    `next_run_at` is the slot the scheduler is WAITING for and it ADVANCES on dispatch, so a
    healthy row is permanently `now < next_run_at`. Measured live 2026-10-22T12:52Z: 42
    enabled rows, 42 NOT JUDGED. If that read as NOT RUN the leg could never report a healthy
    box -- it would speak only once something had already gone wrong.
    """
    healthy = [
        _cron_row(f"job-pending-{i}", next_run_at="2026-10-22T06:00:00+00:00",
                  last_run_at="2026-10-21T06:00:31Z", row_id=f"id-{i}")
        for i in range(3)
    ]
    runs = _daily_runs("job-pending-0", lateness=(35, 41), job_id="id-0")
    leg = RUNNER.cadence_slot_leg(healthy, ["ops"], [], read_at="2026-10-21T07:00:00Z",
                                  fires=runs)
    assert leg["status"] == "ASSERTED", leg
    assert leg["problems"] == [], leg["problems"]
    counts = leg["coverage"]["counts"]
    assert counts[RUNNER.CADENCE_SLOT_NOT_JUDGED] == 3, counts
    assert leg["coverage"]["judged"] == 0, leg["coverage"]
    out = RUNNER.render([leg], [], slug="owner/repo", read_at="2026-10-21T07:00:00Z",
                        issues=[])
    assert "NOT JUDGED 3, UNREADABLE 0" in out, out
    assert "nothing overdue" in out, out

def test_a_population_of_ONLY_UNREADABLE_rows_is_NOT_RUN_never_clean() -> None:
    """PLACED, not judged, is what separates the two readings.

    A row whose `next_run_at` cannot be placed was not measured at all, so a population of
    nothing but those is NOT RUN -- the instrument looked and could place none of it.
    """
    unreadable = [
        _cron_row(f"job-unreadable-{i}", next_run_at=raw, row_id=f"id-{i}")
        for i, raw in enumerate(("", "not-a-slot"))
    ]
    leg = RUNNER.cadence_slot_leg(unreadable, ["ops"], [], read_at="2026-10-21T07:00:00Z")
    assert leg["status"] == "NOT RUN", leg
    assert leg["coverage"]["counts"][RUNNER.CADENCE_SLOT_UNREADABLE] == 2, leg["coverage"]
    assert "could be PLACED" in leg["coverage"]["reason"], leg["coverage"]
    out = RUNNER.render([leg], [], slug="owner/repo", read_at="2026-10-21T07:00:00Z",
                        issues=[])
    assert "UNREADABLE: `job-unreadable-0`" in out, out
    assert "UNREADABLE: `job-unreadable-1`" in out, out

    # DISCRIMINATING CONTROL: one readable row in the same population moves it off NOT RUN.
    readable = _cron_row("job-pending", next_run_at="2026-10-22T06:00:00+00:00", row_id="id-ok")
    mixed = RUNNER.cadence_slot_leg(unreadable + [readable], ["ops"], [],
                                    read_at="2026-10-21T07:00:00Z", fires=[])
    assert mixed["status"] == "ASSERTED", mixed
    assert mixed["coverage"]["counts"][RUNNER.CADENCE_SLOT_UNREADABLE] == 2, mixed["coverage"]

def test_a_ZONE_LESS_instant_is_UNREADABLE_never_assumed_UTC() -> None:
    """A naive instant would be shifted by the reader's own assumption.

    Every live row carries an offset (measured 2026-10-22: 34 of 34 enabled), so this costs
    nothing today -- and ASSUMING UTC would move a `0 9 * * *` Moscow row's 06:00Z slot to
    09:00Z, manufacture a three-hour disagreement with the scheduler, and red a job that fired
    on time.
    """
    now = RUNNER.reader_parse_ts("2026-10-21T07:00:00Z")
    record = RUNNER.cadence_slot_verdict_for(
        _cron_row("job-naive", next_run_at="2026-10-21 06:00:00"),
        now=now, runs=[])
    assert record["verdict"] == RUNNER.CADENCE_SLOT_UNREADABLE, record
    assert "no zone offset" in record["reason"], record

def test_the_READ_PATH_carries_the_rows_own_ZONE() -> None:
    """The predicate needs no zone because `next_run_at` carries it -- and the READ still
    carries the zone for the REPORT, which is where a reader needs it ("09:15 Moscow" is an
    address; 06:15Z alone is not).

    Driven through `box_cron_rows` over a THROWAWAY home, so the probe reads the real read
    path rather than a stub.
    """
    root = Path(tempfile.mkdtemp()) / "profiles"
    (root / "ops").mkdir(parents=True)
    _home_db(root.parent / "opencrabs.db",
             ("id-default", "factory-default-home", "", "", 1))
    db = root / "ops" / "opencrabs.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "create table cron_jobs (id text, name text, deliver_to text, prompt text, "
        "enabled integer, last_run_at text, cron_expr text, next_run_at text, timezone text)"
    )
    conn.execute(
        "insert into cron_jobs values (?,?,?,?,?,?,?,?,?)",
        ("id-msk", "factory-moscow-job", "", "", 1, "2026-10-21T06:15:04Z",
         "15 9 * * *", "2026-10-22T06:15:00+00:00", "Europe/Moscow"),
    )
    conn.commit()
    conn.close()
    rows, homes_read, unreached = RUNNER.box_cron_rows(root)
    assert unreached == [], unreached
    row = {r["name"]: r for r in rows}["factory-moscow-job"]
    assert row["timezone"] == "Europe/Moscow", row
    record = RUNNER.cadence_slot_verdict_for(
        row, now=RUNNER.reader_parse_ts("2026-10-21T07:00:00Z"), runs=[]
    )
    assert record["verdict"] == RUNNER.CADENCE_SLOT_NOT_JUDGED, record
    assert record["timezone"] == "Europe/Moscow", record
    assert record["next_run_at"] == "2026-10-22T06:15:00+00:00", record

def main() -> int:
    checks = [value for name, value in sorted(globals().items())
              if name.startswith("test_") and callable(value)]
    failures: list[str] = []
    for check in checks:
        try:
            check()
        except pytest.skip.Exception:
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
