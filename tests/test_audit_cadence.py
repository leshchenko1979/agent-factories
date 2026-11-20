#!/usr/bin/env python3
"""Gate: the internal self-audit's cadence is measured over ITS OWN rows (#324 Leg B).

THE DEFECT THIS GATE EXISTS FOR. `tools/audit.py::check_cadence_integrity` took the newest
`run`/`score` row of ANY kind. On 2026-11-18 that returned `hours_since_last_run 31.7` from a
patrol-park row (n=5170) while the last real self-audit was n=2027 at `2026-10-03T02:59:00Z`
— 46.23 days earlier. The verdict was RED, and the figure it printed described a different
process than the one it named. A number that travels with the wrong predicate is worse than no
number: it reads as a measurement of the duty while being a measurement of its neighbours.

WHAT IT PROVES, and nothing beyond it:

1. **The population is the self-audit's.** A synthetic ledger carrying a FRESH patrol row and
   a STALE self-audit row must report the stale one. This is the defect itself, so the probe
   fails on the exact code the defect shipped.
2. **Both lawful subject forms are accepted, and the boundary is CHECKED.** The legacy bare
   stem and the dated form are self-audit rows; `-notes`, month `13`, and a digit immediately
   after the date are not. The negatives are the control: a predicate that matched everything
   with the prefix would pass every positive and fail nothing.
3. **A zero-examined read is not a clean read.** A ledger with no self-audit row, and an
   absent ledger, each return `cadence_held: False` WITH their reason named — never the
   vacuous green the old code returned for an empty population.
4. **The duty token is three-valued and the row carries it.** `skipped` is neither a
   completion nor a failure, and the trailer reaches `format_run_row_detail`'s output.
5. **The stamp site emits the DATED subject**, read from the shipped source — a mechanism
   that renders a date nobody stamps is a declaration with no producer.

WHAT IT DOES NOT ASSERT. The live cadence figure. It is a property of an INSTANT (the ledger
is appended during its own run), so the gate drives SYNTHETIC ledgers under a temp directory
and reports the live reading without judging it — the same division gate 57 draws. That is
also why this file passes at the shipped depth: it reads no live board, no fleet manifest and
no box-local fixture.

WHY IT SHIPS AS A PAIR, against the dispatch's expectation of a TEMPLATE-only file. A gate
registered in `tools/audit.py` is counted by `gate_registry.invoked_gates`, which scans the
audit's SOURCE TEXT with no file-existence filter, so the registration is a declaration the
tree must honour at BOTH depths; and `template_parity_problems` refuses a TEMPLATE-shipped
declared gate that the shared `REQUIRED_GATES` manifest omits. A TEMPLATE-only registered gate
is therefore not representable, and a TEMPLATE-only UNregistered one is a check nobody runs
(P29). The pair is the only shape the mechanisms admit; the asymmetry the dispatch predicted
would have been a dead gate, not a deliberate one.

Run:  python3 tests/test_audit_cadence.py
Exit: 0 every probe held, 1 otherwise.
"""

from __future__ import annotations

import datetime
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import audit  # noqa: E402

STEM = "internal-self-audit"
AUDIT_SOURCE = REPO / "tools" / "audit.py"

FAILURES: list[str] = []
CHECKS = 0


def check(label: str, held: bool, detail: str = "") -> None:
    """Record one probe. A failure is NAMED, never counted into a bare total."""
    global CHECKS
    CHECKS += 1
    if not held:
        FAILURES.append(f"{label}{(' — ' + detail) if detail else ''}")


def write_ledger(directory: str, rows: list[dict]) -> Path:
    """Write a synthetic ledger. Synthetic by construction: no live surface is read."""
    path = Path(directory) / "ledger.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def probe_the_population_is_the_self_audits_not_the_newest_run_row() -> None:
    """Probe 1 — THE DEFECT. A fresh patrol row must not answer for a stale self-audit."""
    rows = [
        {"n": 1, "event": "run", "subject": "patrol-park-2026-11-17",
         "ts": "2026-11-18T07:00:00Z", "detail": "duration=1s"},
        {"n": 2, "event": "run", "subject": STEM, "ts": "2026-10-03T02:59:00Z",
         "detail": "duration=9s"},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        stats = audit.check_cadence_integrity(write_ledger(tmp, rows))
    check(
        "a fresh patrol row does not answer for a stale self-audit",
        stats.get("last_run_ts") == "2026-10-03T02:59:00Z",
        f"last_run_ts={stats.get('last_run_ts')!r}",
    )
    check(
        "the cadence figure is the self-audit's own age, not the newest run row's",
        float(stats.get("hours_since_last_run") or 0) > 24 * 40,
        f"hours_since_last_run={stats.get('hours_since_last_run')!r}",
    )
    check(
        "the population is counted, so a clean read is never a read that found nothing",
        stats.get("examined") == 1 and stats.get("population") == 2,
        f"examined={stats.get('examined')!r} population={stats.get('population')!r}",
    )
    check(
        "a stale self-audit is MISSED, never held",
        stats.get("cadence_held") is False,
        f"cadence_held={stats.get('cadence_held')!r}",
    )

    # The forward direction on the SAME predicate: a fresh self-audit under a stale patrol
    # row holds. Without this arm the probe above would pass on a selector that returned
    # nothing at all, which is the zero-examined shape wearing a verdict.
    #
    # THE FRESH INSTANT IS COMPUTED FROM THE CHECK'S OWN CLOCK, NEVER HARDCODED. This arm
    # first shipped with a literal `2026-11-18T07:30:00Z`, which was "now" when it was
    # written and expired exactly CADENCE_WINDOW_HOURS (30 h) later: on 2026-11-20 the same
    # fixture read 50.39 h old, `cadence_held` came back False, and the gate went RED on a
    # timer with no code change behind it -- measured at origin/main 4bf38d2a in a clean
    # worktree, so it was not any one lane's change. A probe asserting "fresh holds" must
    # take its freshness from the clock the predicate reads, or it tests the calendar
    # instead of the predicate.
    fresh_instant = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)
    rows = [
        {"n": 1, "event": "run", "subject": "patrol-park-2026-10-01",
         "ts": "2026-10-01T00:00:00Z", "detail": "duration=1s"},
        {"n": 2, "event": "run",
         "subject": f"{STEM}-{fresh_instant.date().isoformat()}",
         "ts": fresh_instant.strftime("%Y-%m-%dT%H:%M:%SZ"), "detail": "duration=9s"},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        stats = audit.check_cadence_integrity(write_ledger(tmp, rows))
    check(
        "a fresh DATED self-audit holds while a stale patrol row sits beside it",
        stats.get("cadence_held") is True and stats.get("examined") == 1,
        f"cadence_held={stats.get('cadence_held')!r} examined={stats.get('examined')!r}",
    )


def probe_the_subject_boundary_is_checked_not_merely_prefixed() -> None:
    """Probe 2 — the NEGATIVE control. A prefix-only match would pass every positive."""
    accepted = [STEM, f"{STEM}-2026-11-18"]
    rejected = [
        f"{STEM}-notes",       # tail is not a date
        f"{STEM}-2026-13-01",  # month 13
        f"{STEM}-2026-11-180", # a digit after the date makes it a longer number
        f"{STEM}-2026-11-1",   # a truncated date
        "patrol-park-2026-11-17",
        "#324",
        "",
        None,
    ]
    for subject in accepted:
        check(
            f"a self-audit row is accepted: {subject!r}",
            audit.self_audit_subject_matches(subject),
        )
    for subject in rejected:
        check(
            f"a subject merely sharing the prefix is REJECTED: {subject!r}",
            not audit.self_audit_subject_matches(subject),
        )


def probe_a_zero_examined_read_is_never_clean() -> None:
    """Probe 3 — the vacuous green. An empty population is the duty never stamped."""
    rows = [{"n": 1, "event": "run", "subject": "patrol-park-2026-11-17",
             "ts": "2026-11-18T07:00:00Z", "detail": "duration=1s"}]
    with tempfile.TemporaryDirectory() as tmp:
        stats = audit.check_cadence_integrity(write_ledger(tmp, rows))
    check(
        "a ledger with no self-audit row is NOT cadence held",
        stats.get("cadence_held") is False,
        f"cadence_held={stats.get('cadence_held')!r}",
    )
    check(
        "its zero-examined population names its reason instead of printing a bare 0 of N",
        stats.get("examined") == 0 and "self-audit" in str(stats.get("reason") or ""),
        f"examined={stats.get('examined')!r} reason={stats.get('reason')!r}",
    )
    check(
        "the zero-examined render states the reason, so it is distinguishable from clean",
        "no internal self-audit row" in audit.format_cadence_population(stats),
        audit.format_cadence_population(stats),
    )

    with tempfile.TemporaryDirectory() as tmp:
        absent = audit.check_cadence_integrity(Path(tmp) / "no-such-ledger.jsonl")
    check(
        "an ABSENT ledger is not cadence held either, and names that reason",
        absent.get("cadence_held") is False and "no ledger" in str(absent.get("reason") or ""),
        f"cadence_held={absent.get('cadence_held')!r} reason={absent.get('reason')!r}",
    )


def probe_the_duty_token_is_three_valued_and_reaches_the_row() -> None:
    """Probe 4 — `skipped` is neither a completion nor a failure."""
    check("an all-pass run's duty is completed",
          audit.self_audit_duty("accepted", "all-pass") == "completed")
    check("a failed run's duty is failed",
          audit.self_audit_duty("failed", "gate-failure") == "failed")
    check("a stamp-only run's duty is SKIPPED, not completed",
          audit.self_audit_duty("accepted", "skipped") == "skipped")
    # AN UNKNOWN VERDICT IS NOT A FAILED DUTY. The run executed and discharged the duty; what
    # is unknown is the VERDICT, and the row already carries that in `gate=gate-unknown`. Folding
    # it into `duty=failed` would record a failure nobody observed -- the collapse the three-token
    # vocabulary exists to prevent, in the other direction.
    check("an unknown-verdict run still DISCHARGED its duty; `gate=` carries the unknown",
          audit.self_audit_duty("accepted", "gate-unknown") == "completed")
    check("the three tokens are exactly the declared vocabulary",
          {audit.self_audit_duty(o, g) for o, g in
           [("accepted", "all-pass"), ("failed", "gate-failure"), ("accepted", "skipped")]}
          == {"completed", "failed", "skipped"})

    detail = audit.format_run_row_detail({}, "accepted", "all-pass", 3.0)
    check("the row's detail carries duty= as its TRAILER",
          detail.rstrip().endswith("duty=completed"), detail)
    check("the trailer did not displace the fields existing readers match",
          "gate=all-pass" in detail and "yield=" in detail, detail)
    check("a stamp-only run stamps duty=skipped",
          "duty=skipped" in audit.format_run_row_detail({}, "accepted", "skipped", 0.0))


def probe_the_stamp_site_emits_the_dated_subject() -> None:
    """Probe 5 — a mechanism that renders a date nobody stamps is a declaration with no producer.

    Read from the SHIPPED SOURCE, because the stamp site is inside `main()` and cannot be
    driven without running a whole audit. The needle is CONSTRUCTED rather than spelled, so
    this probe cannot satisfy itself with its own literal (the #645 arm-7 failure).
    """
    source = AUDIT_SOURCE.read_text(encoding="utf-8")
    needle = 'f"{SELF_AUDIT_SUBJECT_STEM}-{today}"'
    check(
        "the stamp site's subject is the DATED form, not the bare stem",
        needle in source,
        f"needle {needle!r} absent from {AUDIT_SOURCE.name}",
    )
    renderer = "format_cadence_population(cadence_stats)"
    check(
        "the population is printed by BOTH renderers, never the verdict alone",
        source.count(renderer) >= 2,
        f"{renderer!r} appears {source.count(renderer)} time(s), expected 2",
    )


def probe_the_live_reading_is_reported_never_judged() -> None:
    """Probe 6 — report the live population; assert only that the report is well formed.

    The live figure is a property of an INSTANT, so pinning it would fail a correct
    instrument. What IS asserted: the renderer states a population for whatever it read,
    including the zero case, so "clean" and "found nothing" never render alike.
    """
    ledger = REPO / "evidence" / "ledger.jsonl"
    if not ledger.is_file():
        print("  live reading: no ledger at this depth (reported, not judged)")
        return
    stats = audit.check_cadence_integrity(ledger)
    rendered = audit.format_cadence_population(stats)
    print(f"  live reading: {rendered} · last self-audit {stats.get('last_run_ts')!r} · "
          f"{stats.get('hours_since_last_run')}h ago · "
          f"{'HELD' if stats.get('cadence_held') else 'MISSED'}")
    check(
        "the live reading renders a population, never a bare verdict",
        "run/score row(s) scanned" in rendered,
        rendered,
    )


def main() -> int:
    print("audit-cadence gate: the self-audit's cadence is measured over its own rows")
    probe_the_population_is_the_self_audits_not_the_newest_run_row()
    probe_the_subject_boundary_is_checked_not_merely_prefixed()
    probe_a_zero_examined_read_is_never_clean()
    probe_the_duty_token_is_three_valued_and_reaches_the_row()
    probe_the_stamp_site_emits_the_dated_subject()
    probe_the_live_reading_is_reported_never_judged()

    if FAILURES:
        print(f"\nFAILED: {len(FAILURES)} of {CHECKS} check(s)")
        for failure in FAILURES:
            print(f"  FAIL {failure}")
        return 1
    print(f"\naudit-cadence gate passed: {CHECKS} check(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
