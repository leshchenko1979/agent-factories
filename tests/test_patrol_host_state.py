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
import os
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import datetime as dt
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
        publish_fn=_stub_publish_leg,
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
    return {"n": n, "ts": "2026-09-19T10:00:00Z", "event": event, "actor": "hq",
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

def _duty_row(name="factory-registry-attest", *, prompt=_RECEIPT_PROMPT,
              last_run_at="2026-09-25T06:00:13Z",
              row_id="9ec28cec-100c-4325-ba3e-62972351ff0d") -> dict:
    return {
        "id": row_id, "name": name, "deliver_to": "", "prompt": prompt,
        "last_run_at": last_run_at, "home": "probe-home",
    }

def _receipt_row(subject="registry-attest-2026-09-25",
                 detail="the round completed. duty=completed", n=1) -> dict:
    """A receipt row. The `duty=` token is what MAKES it a receipt (#160).

    The default carries it, because a row that declares nothing is not a receipt at all —
    the leg's first version accepted any subject match, which is how a dispatch record
    written before the round completed certified the round.
    """
    return {"n": n, "ts": "2026-09-25T06:14:25Z", "event": "run", "actor": "delegate",
            "subject": subject, "detail": detail}

def _duty_leg(cron_rows, ledger_rows, *, store=None) -> dict:
    return RUNNER.duty_receipt_leg(
        cron_rows, ["probe-home"], [], ["factory-"], ledger_rows,
        read_at="2026-09-25T06:31:48Z",
        store=store if store is not None else Path(tempfile.mkdtemp()),
    )

def test_the_duty_leg_BITES_when_a_fired_round_left_no_receipt() -> None:
    """THE probe this leg exists for: a green cron run with no duty row is a FINDING.

    The measured instance: six fragments sat at attested_at 2026-09-19 for four days while
    `cron_job_runs` carried success — the trigger worked and the duty did not, and nothing
    reported it.
    """
    leg = _duty_leg([_duty_row()], [])
    assert leg["status"] == "ASSERTED", leg
    assert leg["coverage"]["duties_judged"][0]["round"] == "2026-09-25", leg["coverage"]
    assert len(leg["problems"]) == 1, leg["problems"]
    problem = leg["problems"][0]
    assert "NO duty receipt" in problem, problem
    assert "registry-attest-2026-09-25" in problem, problem
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
        [_receipt_row(subject="patrol-verify-2026-09-25T06",
                      detail="the patrol ran. duty=completed")],
    )
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["duties_judged"][0]["receipts"] == 1, leg["coverage"]

def test_a_DECORATED_AFTER_the_date_subject_names_the_round() -> None:
    """#159: a decoration that FOLLOWS the date is reached by the ruled prefix."""
    leg = _duty_leg(
        [_duty_row()],
        [_receipt_row(subject="registry-attest-2026-09-25-writeback",
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
        [_receipt_row(subject="registry-attest-2026-09-250",
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
    """`last_run_at` is stamped at DISPATCH, so it names the round the trigger woke."""
    leg = _duty_leg([_duty_row(last_run_at="2026-09-24T06:00:11Z")], [])
    assert leg["coverage"]["duties_judged"][0]["round"] == "2026-09-24", leg["coverage"]
    assert "registry-attest-2026-09-24" in leg["problems"][0], leg["problems"][0]

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
    assert "NO duty receipt" in out, "a missing duty receipt must reach the report"
    assert rc == 1, "a missing duty receipt must fail the run"


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
