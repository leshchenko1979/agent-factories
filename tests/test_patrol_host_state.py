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

6. **A failed notify SURFACES** (#122). A cron's notify can fail while the run row reads
   green, and the failure lands on the job-local log. The leg is keyed on the SUCCESS TOKEN
   and not on the byte count the finding arrived in, so a new error string at a familiar
   length cannot satisfy it — and a log that merely MENTIONS the token is not a receipt,
   because a field prose can satisfy is not a field (n=405 clause 5). Its live population
   is legitimately empty on a quiet day, so non-vacuity rides the probe and never a
   loud-fail-on-zero (#112) — the opposite call from the cron-thinness leg beside it.

Run:  python3 tests/test_patrol_host_state.py
Exit: 0 all checks pass, 1 a check failed.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

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
        {"n": n, "ts": "2026-09-19T10:00:00Z", "event": event, "actor": "triage",
         "subject": subject, "detail": "probe"}
        for event, subject, n in pairs
    ]


def _run(issues, rows, *, cron_rows=None, homes=None, unreached=None, prefixes=None,
         log_dir=None):
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
    """
    cron_rows = [] if cron_rows is None else cron_rows
    homes = ["probe-home"] if homes is None else homes
    unreached = [] if unreached is None else unreached
    prefixes = [] if prefixes is None else prefixes
    log_dir = _EMPTY_LOG_DIR if log_dir is None else log_dir
    out, err = io.StringIO(), io.StringIO()
    rc = RUNNER.main(
        [],
        board_fn=lambda slug: issues,
        slug_fn=lambda: "owner/repo",
        rows_fn=lambda: rows,
        cron_rows_fn=lambda: (cron_rows, homes, unreached),
        prefixes_fn=lambda: prefixes,
        log_dir=log_dir,
        out=lambda *a, **k: print(*a, file=out, **k),
        err=lambda *a, **k: print(*a, file=err, **k),
    )
    return rc, out.getvalue(), err.getvalue()


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

def _thin(name, **kw) -> dict:
    """A correctly-thin row: a session target whose prompt declares itself wake-only."""
    return _cron(name, deliver_to=f"session:{_SESSION_UUID}", prompt=_WAKE_PROMPT, **kw)

def _ledger_with(*subjects) -> Path:
    """A synthetic ledger in a temp dir — the guard is checked against DATA, not the live log."""
    path = Path(tempfile.mkdtemp()) / "ledger.jsonl"
    path.write_text(
        "".join(
            json.dumps({"n": i + 1, "ts": "2026-09-19T10:00:00Z", "event": "close",
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
    assert gate.INVARIANT_LANDED == "2026-09-18T18:04:24Z", gate.INVARIANT_LANDED


def test_a_false_board_declaration_is_reported_and_fails_the_run() -> None:
    """#117 acceptance: a close row declaring board=closed for an OPEN issue is a problem.

    This is the NON-VACUITY probe. The live board is clean as this lands, so a leg that
    only ever saw a clean board would have shown nothing — the probe supplies the false
    declaration and asserts the leg bites.
    """
    issues = [_issue(1, "OPEN"), _issue(2, "CLOSED")]
    rows = _rows(("intake", "#1", 1), ("intake", "#2", 2)) + [
        _close_row(3, "#1", "2026-09-19T10:00:00Z", "settled board=closed"),
        _close_row(4, "#2", "2026-09-19T10:05:00Z", "settled board=closed"),
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
        _close_row(2, "#1", "2026-09-19T10:00:00Z", "settled board=closed"),
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
        _close_row(2, "#1", "2026-09-19T10:00:00Z",
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
        _close_row(2, "#99", "2026-09-19T10:00:00Z", "settled board=closed"),
    ]
    rc, out, _ = _run(issues, rows)
    assert rc == 1, out
    assert "no issue #99 exists on the board" in out, out


def test_a_pre_invariant_close_row_is_outside_the_population() -> None:
    """The GATE's own boundary is honoured: a pre-invariant row is not judged here."""
    issues = [_issue(1, "OPEN")]
    rows = _rows(("intake", "#1", 1)) + [
        _close_row(2, "#1", "2026-09-01T10:00:00Z", "settled board=closed"),
    ]
    rc, out, _ = _run(issues, rows)
    assert rc == 0, out
    assert "0 close row(s) checked" in out, (
        f"a pre-invariant close row must not enter the population\n{out}"
    )


# --- #122: the notify-receipt leg — a failed notify SURFACES -----------------------

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
        assert not RUNNER.reads_notify_receipt(text), (
            f"{name} mentions the token without naming an id and must NOT read as a "
            f"receipt — prose about a missing field is the n=405 clause 5 damage"
        )
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-22T00:00:00Z")
    assert len(leg["problems"]) == 2, (
        f"both logs carry no receipt and both must be reported: {leg['problems']}"
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


def main() -> int:
    checks = [value for name, value in sorted(globals().items())
              if name.startswith("test_") and callable(value)]
    failures: list[str] = []
    for check in checks:
        try:
            check()
        except AssertionError as exc:
            failures.append(f"{check.__name__}: {exc}")
            print(f"  FAIL  {check.__name__} — {exc}")
        else:
            print(f"  PASS  {check.__name__}")
    print()
    if failures:
        print(f"patrol-runner gate FAILED: {len(failures)} check(s)")
        return 1
    print(f"patrol-runner gate passed: {len(checks)} check(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
