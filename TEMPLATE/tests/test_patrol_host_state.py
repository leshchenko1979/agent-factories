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
   leg binds to that gate's own `BOARD_TOKEN` and `INVARIANT_LANDED` rather than re-deriving
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


def _issue(number: int, state: str) -> dict:
    return {"number": number, "state": state, "title": f"issue {number}",
            "closedAt": None if state == "OPEN" else "2026-09-19T00:00:00Z"}


def _rows(*pairs) -> list[dict]:
    """Ledger rows from (event, subject, n) triples."""
    return [
        {"n": n, "ts": _CLOSE_TS, "event": event, "actor": "triage",
         "subject": subject, "detail": "probe"}
        for event, subject, n in pairs
    ]


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
         log_dir=None, kit_manifest=None, fleet_manifest=None):
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
        prefixes_fn=lambda: prefixes,
        log_dir=log_dir,
        kit_manifest=kit_manifest,
        fleet_manifest=fleet_manifest,
        out=lambda *a, **k: print(*a, file=out, **k),
        err=lambda *a, **k: print(*a, file=err, **k),
        publish_fn=_stub_publish_leg,
        worktree_fn=_stub_worktree_leg,
    )
    return rc, out.getvalue(), err.getvalue()


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
    rows = _rows(("intake", "#1", 1), ("intake", "#2", 2), ("intake", "#3", 3))
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

def _thin(name, *, prompt=None, **kw) -> dict:
    """A correctly-thin row: a session target whose prompt declares itself wake-only.

    `prompt` EXTENDS the wake-only prompt rather than replacing it, so a probe can add the
    content it is testing while the row stays correctly thin on the wake and marker legs —
    otherwise the content probe would trip the unrelated work-order leg and prove nothing
    about the class it names.
    """
    body = _WAKE_PROMPT if prompt is None else f"{_WAKE_PROMPT} {prompt}"
    return _cron(name, deliver_to=f"session:{_SESSION_UUID}", prompt=body, **kw)

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
        _thin("oc-triage-hourly-patrol", home="other-home"),
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
    rows = [_thin("oc-triage-hourly-patrol")]
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
        _cron("oc-some-other-factory-job", deliver_to=f"session:{_SESSION_UUID}",
              prompt="Execute the hourly cycle and write the report.", home="other-home"),
    ]
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home", "other-home"],
                      prefixes=["factory-"])
    assert rc == 0, f"an unattributable row must not fail this factory's run\n{out}"
    assert "1 attributed to nobody" in out, out
    assert "    unattributed: oc-some-other-factory-job (home other-home)" in out, (
        f"the population read must NAME every row it could not attribute, with the home "
        f"it was read from — a count alone resolves to no object and cannot be checked "
        f"by the reader it is reported to (#126)\n{out}"
    )
    judged = [line for line in out.splitlines() if line.startswith("    - ")]
    assert not any("oc-some-other-factory-job" in line for line in judged), (
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
        _thin("oc-other-factory-window",
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
    assert "law content: oc-other-factory-window" in out, (
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
    """One field, one predicate: the leg reads the GATE's token and boundary.

    A private copy would be self-consistent on both sides and the drift would be
    invisible — the class this factory has already ruled (n=405 clause 5, n=599).
    """
    assert RUNNER.CLOSE_BOARD_GATE == REPO / "tests" / "test_close_board_recorded.py", (
        f"the leg must bind to the close-board gate, not {RUNNER.CLOSE_BOARD_GATE}"
    )
    gate = RUNNER.load_close_board_gate()
    assert gate.BOARD_TOKEN == "board=closed", gate.BOARD_TOKEN
    # The ANCHOR is this tree's own instant: the gate ships `standalone` precisely so a
    # factory can carry its own, so a member that does is not a defect. The probe asserts
    # the leg reaches the gate's constant and that the constant is a well-formed instant.
    anchor = gate.INVARIANT_LANDED
    assert anchor and anchor.endswith("Z") and len(anchor) == 20, anchor


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
    rows = _rows(("intake", "#1", 1)) + [
        _close_row(2, "#1", _PRE_CLOSE_TS, "settled board=closed"),
    ]
    rc, out, _ = _run(issues, rows)
    assert rc == 0, out
    assert "0 close row(s) checked" in out, (
        f"a pre-invariant close row must not enter the population\n{out}"
    )


# --- #223: the board-ruling leg --------------------------------------------------

def _issue_with_comments(number: int, state: str, *bodies: str) -> dict:
    """A board issue carrying comments, in the shape `gh issue list --json` returns."""
    issue = _issue(number, state)
    issue["comments"] = [
        {"body": body, "author": {"login": "hq"}, "createdAt": _CLOSE_TS}
        for body in bodies
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
    assert "#11 carries a ruling comment on the board but the ledger holds no" in out, out
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
    """The complement: the leg is discriminating, not a blanket red."""
    issues = [_issue_with_comments(41, "OPEN", "## RULED — stamped in the same turn.\n")]
    rows = _rows(("intake", "#41", 1), ("ruling", "#41", 2))
    rc, out, _ = _run(issues, rows)
    section = out.split("LEG board-ruling")[1].split("LEG ")[0]
    assert "#41" not in section, f"a stamped ruling must not be reported: {section!r}"
    assert "1 examined" in section and "0 problem(s)" in section, (
        f"it must be EXAMINED and found clean, never skipped: {section!r}"
    )

def test_the_leg_states_its_population_and_the_board_read_instant() -> None:
    """A clean read over an examined population, never a clean read over nothing.

    The clause is two-part: the gate PRINTS the population it examined. A leg that examined
    zero must not render identically to one that examined the board and found it clean.
    """
    issues = [
        _issue_with_comments(51, "OPEN", "## RULED — one.\n"),
        _issue_with_comments(52, "OPEN", "## RULING — two.\n"),
    ]
    rows = _rows(("intake", "#51", 1), ("ruling", "#51", 2),
                 ("intake", "#52", 3), ("ruling", "#52", 4))
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
    """
    assert isinstance(RUNNER.RULING_HEADINGS, tuple) and RUNNER.RULING_HEADINGS, (
        "the headings must be a declared module tuple"
    )
    assert "## RULED" in RUNNER.RULING_HEADINGS and "## RULING" in RUNNER.RULING_HEADINGS, (
        f"both headings the board carries must be declared: {RUNNER.RULING_HEADINGS}"
    )
    source = (REPO / "tools" / "patrol_host_state.py").read_text(encoding="utf-8")
    assert '"number,state,title,closedAt,comments"' in source, (
        "the board read must ask for comments, or the leg examines nothing"
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
            "prompt": _WAKE_PROMPT}

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
              prompt=f"{_WAKE_PROMPT} then run session notify for the lane"),
        _cron("factory-session-target", deliver_to=f"session:{_SESSION_UUID}",
              prompt=_WAKE_PROMPT),
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
              prompt=f"{_WAKE_PROMPT} then run session notify for the lane"),
        _cron("other-factory-job",
              prompt=f"{_WAKE_PROMPT} then run session notify for the lane"),
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
    log_dir = _log_dir(**{"oc-some-other-job-20260922T000045.log": _FAILURE})
    rows = [_notify_row("factory-measurement-daily")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-22T00:00:00Z")
    assert leg["problems"] == [], (
        f"an unattributable log belongs in the population read, never in the problems: "
        f"{leg['problems']}"
    )
    assert leg["coverage"]["logs_unattributed"] == 1, leg["coverage"]
    assert leg["coverage"]["unattributed_logs"][0]["job"] == "oc-some-other-job", leg["coverage"]

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
        dict(_notify_row("oc-not-mine"), home="other-home"),
    ]
    mine, nobody = RUNNER.attribute_rows(rows, ["factory-"])
    assert [r["name"] for r in mine] == ["factory-mine"], mine
    assert [r["name"] for r in nobody] == ["oc-not-mine"], nobody


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
    """The close-board gate's own anchor, as this tree carries it."""
    try:
        return RUNNER.load_close_board_gate().INVARIANT_LANDED
    except Exception:  # noqa: BLE001 — the leg reports a gate it cannot load; the fixture
        return "2026-09-18T18:04:24Z"  # only needs a well-formed instant to order against.


_DUTY_BOUND = _tree_bound(RUNNER.DUTY_RECEIPT_BOUNDARY_KEY, "2026-09-25T07:01:07Z")
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
              read_at=None) -> dict:
    return RUNNER.duty_receipt_leg(
        cron_rows, ["probe-home"], [], ["factory-"], ledger_rows,
        read_at=read_at if read_at is not None else _DUTY_READ_AT,
        store=store if store is not None else Path(tempfile.mkdtemp()),
        repo=repo if repo is not None else _DUTY_TREE,
    )

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

def test_a_row_declaring_no_receipt_is_NOT_JUDGED_and_is_COUNTED_by_name() -> None:
    """P29: a clean verdict over a population that declared nothing must never be the same
    output as one that examined the population — so the undeclared rows are NAMED."""
    leg = _duty_leg(
        [_duty_row(), _duty_row(name="factory-measurement-daily", prompt="no declaration here")],
        [],
    )
    assert leg["coverage"]["jobs_declaring_receipt"] == 1, leg["coverage"]
    assert leg["coverage"]["jobs_undeclared"] == 1, leg["coverage"]
    assert leg["coverage"]["undeclared_jobs"] == ["factory-measurement-daily"], leg["coverage"]
    assert len(leg["problems"]) == 1, "the undeclared row is not judged and adds no problem"

def test_the_duty_leg_reports_NOT_RUN_when_no_row_declares_a_receipt() -> None:
    leg = _duty_leg([_duty_row(prompt="no declaration here")], [])
    assert leg["status"] == "NOT RUN", leg
    assert "receipt_subject:" in (leg["reason"] or ""), leg["reason"]
    assert leg["problems"] == [], leg["problems"]

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
    # WHICH verdict reaches the report depends on whether THIS tree declares the bound the
    # leg judges against (#78 clause b): a tree that has declared none is REFUSED rather
    # than shown a clean run, which is the leg's own fail-closed law (#175) and not a
    # weaker outcome. Both states must carry the verdict and both must fail the run — a leg
    # silenced in either one is the failure this probe exists to catch — so the branch
    # asserts each tree's own honest verdict rather than one tree's wording.
    _, _, refusal = RUNNER.duty_receipt_bound(RUNNER.REPO)
    if refusal:
        assert "UNDECLARED" in out or "REFUSED" in out, (
            f"a tree that declares no bound must be TOLD so in the report\n{out}"
        )
    else:
        assert "NO duty receipt" in out, "a missing duty receipt must reach the report"
    assert rc == 1, "the leg's verdict must fail the run"


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
    hidden one -- the same discipline PUBLISH_RESIDUAL_SECS follows for the pusher."""
    leg = _duty_leg([_duty_row()], [_receipt_row()])
    assert leg["coverage"]["residual_secs"] == RUNNER.DUTY_RESIDUAL_SECS, leg["coverage"]
    rc, out, err = _run([], [], cron_rows=[_duty_row()], prefixes=["factory-"])
    assert "forward residual:" in out, out[-3000:]
    assert f"{RUNNER.DUTY_RESIDUAL_SECS} s" in out, out[-3000:]

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

# ------------------------------------------------------------------- kit-drift leg

def _synthetic_kit(tmp: Path, *, files: dict[str, bytes], members: dict[str, dict]) -> tuple[Path, Path]:
    """A throwaway manifest + fleet pair over synthetic member trees.

    Returns (manifest_path, fleet_path). The member trees are built by the caller under
    `tmp`, so nothing here reads a live repository: the leg's population is five OTHER
    repos, and a probe that read them would be measuring whatever they happen to hold.
    """
    import hashlib
    manifest = {"kit_version": "probe", "files": {}}
    for rel, body in files.items():
        path = tmp / "TEMPLATE" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        manifest["files"][f"TEMPLATE/{rel}"] = hashlib.sha256(body).hexdigest()
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
            prefixes_fn=lambda: [], log_dir=_EMPTY_LOG_DIR,
            kit_manifest=mpath, fleet_manifest=fpath,
            out=lambda *a, **k: print(*a, file=out, **k),
            err=lambda *a, **k: None,
            publish_fn=_stub_publish_leg,
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
            prefixes_fn=lambda: [], log_dir=_EMPTY_LOG_DIR,
            kit_manifest=mpath, fleet_manifest=fpath,
            out=lambda *a, **k: print(*a, file=out, **k),
            err=lambda *a, **k: None,
            publish_fn=_stub_publish_leg,
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
    """A bare remote carrying one commit, and a clone of it. Returns (remote, work)."""
    remote = _bare(root / "remote.git")
    seed = _work(root / "seed", remote)
    _commit(seed, "a.txt")
    _git(seed, "push", "-q", "origin", "main:main")
    work = root / "work"
    _git(root, "clone", "-q", str(remote), str(work))
    _git(work, "config", "user.email", "probe@probe.invalid")
    _git(work, "config", "user.name", "probe")
    return remote, work


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


# --- the duty-receipt leg's FORWARD BOUND (#175) --------------------------------
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
            prefixes_fn=lambda: [],
            log_dir=Path(tmp) / "logs",
            kit_manifest=_synthetic_kit(Path(tmp), files={"tools/a.py": b"a"},
                                        members={})[0],
            fleet_manifest=_synthetic_kit(Path(tmp), files={"tools/a.py": b"a"},
                                          members={})[1],
            out=lambda *a, **k: print(*a, file=out, **k),
            err=lambda *a, **k: None,
            publish_fn=_stub_publish_leg,
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
    assert leg["status"] == "NOT RUN", leg["status"]
    reason = leg["reason"]
    assert "NONE carries" in reason, reason
    assert "NO DUTY WAS JUDGED" in reason, reason
    assert "never a finding" in reason, reason
    assert "so no duty owes a receipt on this box" not in reason, reason
    assert "1 enabled row(s) this factory declares" in reason, (
        f"the reason must name the population it enumerated: {reason}"
    )

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
    leg = RUNNER.board_ruling_leg(issues, rows, read_at="probe", predicate=pred)
    cov = leg["coverage"]
    assert cov["rulings_unbridgeable"] == 1, cov
    assert cov["unbridgeable_rows"] == [{"n": 901, "subject": "no-issue-anywhere"}], cov
    assert cov["rulings_read"] == cov["rulings_resolved"] + cov["rulings_unbridgeable"], cov

def test_probe_the_BRIDGE_is_the_thing_that_moves_the_population() -> None:
    """The NON-VACUITY control for clause 3.

    Neutering the bridge returns a bridged issue to the problem list. The probe drives the
    REAL leg twice over one fixture: once with the dispatch present, once without — so the
    difference is attributable to the bridge and not to the fixture.
    """
    pred = RUNNER.load_predicate()
    issues = [_issue_with_comments(85, "OPEN", "## RULED — settled on the board.\n")]
    ruling = {"n": 545, "event": "ruling", "subject": "foreign-instrument-coupling",
              "detail": "the clause"}
    dispatch = {"n": 546, "event": "dispatch", "subject": "#85", "detail": "Ruling n=545"}

    with_bridge = RUNNER.board_ruling_leg(issues, [ruling, dispatch], read_at="probe",
                                          predicate=pred)
    assert with_bridge["problems"] == [], with_bridge["problems"]

    # Remove ONLY the bridge row: the same fixture must now report the false-unruled item.
    without = RUNNER.board_ruling_leg(issues, [ruling], read_at="probe", predicate=pred)
    assert len(without["problems"]) == 1, without["problems"]
    assert "#85 carries a ruling comment" in without["problems"][0], without["problems"]

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
    rows = _rows(("intake", "#7", 1), ("intake", "#8", 2), ("ruling", "#8", 3))
    leg = RUNNER.board_ruling_leg(issues, rows, read_at="probe",
                                  predicate=RUNNER.load_predicate())
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

    widened = RUNNER.board_ruling_leg(issues, rows, read_at="probe", predicate=pred)
    assert widened["coverage"]["ruling_comments_examined"] == 1, widened["coverage"]
    assert len(widened["problems"]) == 1, widened["problems"]
    assert "#133 carries a ruling comment" in widened["problems"][0], widened["problems"]

    saved = RUNNER.RULING_HEADINGS
    RUNNER.RULING_HEADINGS = ("## RULED", "## RULING")
    try:
        narrowed = RUNNER.board_ruling_leg(issues, rows, read_at="probe", predicate=pred)
    finally:
        RUNNER.RULING_HEADINGS = saved
    assert narrowed["coverage"]["ruling_comments_examined"] == 0, narrowed["coverage"]
    assert narrowed["problems"] == [], narrowed["problems"]

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
    rows = _rows(("intake", "#1", 1))
    out, err = io.StringIO(), io.StringIO()
    rc = RUNNER.main(
        [], board_fn=lambda slug: issues, slug_fn=lambda: "owner/repo",
        rows_fn=lambda: rows, cron_rows_fn=lambda: ([], ["probe-home"], []),
        prefixes_fn=lambda: [], log_dir=_EMPTY_LOG_DIR,
        kit_manifest=_probe_kit_pair()[0], fleet_manifest=_probe_kit_pair()[1],
        out=lambda *a, **k: print(*a, file=out, **k),
        err=lambda *a, **k: print(*a, file=err, **k),
        publish_fn=_stub_publish_leg, worktree_fn=_stub,
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
    rows = _rows(("intake", "#1", 1))
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
