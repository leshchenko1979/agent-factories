#!/usr/bin/env python3
"""Gate: the rework number is reported in two named forms, each with its denominator.

Origin (issue #31). `tools/audit.py` emitted a single field called `rework_rate`
whose value was `rework entries ÷ closed subjects` — a per-close rate — while
`evidence/rework.md`'s Rates table used the same two words, "Rework rate", for the
*share* form, `entries ÷ (closed + entries)`. One name, two numbers, and the two
surfaces disagreed by 22 points (58.6% against 37.0%). A reader could not tell which
was meant, and neither could a diff.

The rule this gate enforces, in three parts:

1. **Two names, never one.** `rework_rate` is gone. The payload carries
   `rework_share` and `rework_per_close`, and each is computed from the denominator
   its own name states.
2. **The forms cannot collapse.** `share` and `per_close` are equal only when the
   arithmetic is wrong, so equality is a failure rather than a coincidence.
3. **The denominator is reconciled, not assumed.** `close_events` (close rows) travels
   beside `closed_subjects` (distinct work units), and `close_events` must equal the
   close-row count read independently from the ledger — the ledger can be perfectly
   numbered and still report a close nobody took.

The invariant is factored into `rate_form_problems()` so it can be probed with
synthetic payloads as well as the live one: a rule that only ever sees good input has
not been shown to reject bad input.

Run:  python3 -m pytest tests/test_audit_rates.py -q
Exit: 0 clean, non-zero on any rate-form regression.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AUDIT = REPO / "tools" / "audit.py"
LEDGER = REPO / "evidence" / "ledger.jsonl"
GATE_CMD = "tests/test_audit_rates.py"

FORBIDDEN = "rework_rate"
REQUIRED_FORMS = ("rework_share", "rework_per_close")


def load_audit() -> dict:
    """Read the live audit payload with the gate suite skipped.

    `--no-gates` is what makes this file safe to register as a gate: without it the
    audit would run this gate, which would run the audit, recursively. The flag
    reports `healthy: null` rather than a green, so a skipped suite is never read
    as a passing one.
    """
    res = subprocess.run(
        [sys.executable, str(AUDIT), "--json", "--no-gates"],
        cwd=REPO,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60,
    )
    assert res.returncode == 0, f"audit exited {res.returncode}: {res.stderr.strip()[:400]}"
    return json.loads(res.stdout)


def ledger_close_counts(path: Path = LEDGER) -> tuple[int, int]:
    """Return (close rows, distinct closed subjects), read straight from the ledger."""
    rows = 0
    subjects: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        ev = json.loads(line)
        if ev.get("event") == "close" and ev.get("subject"):
            rows += 1
            subjects.add(ev["subject"])
    return rows, len(subjects)


def rate_form_problems(payload: dict) -> list[str]:
    """Every way a payload can state the rework rate wrongly. Empty list means sound."""
    problems: list[str] = []
    rework = payload.get("rework") or {}
    delivery = payload.get("delivery") or {}

    if FORBIDDEN in rework or FORBIDDEN in payload:
        problems.append(f"a field named {FORBIDDEN!r} is back: one name cannot carry two numbers")

    for form in REQUIRED_FORMS:
        if form not in rework:
            problems.append(f"missing named form {form!r}")

    entries = rework.get("total_entries")
    closed = rework.get("closed_subjects")
    if not isinstance(entries, int) or not isinstance(closed, int):
        problems.append("total_entries and closed_subjects must both be integers")
        return problems
    if closed <= 0:
        problems.append("closed_subjects must be positive for a rate to be defined")
        return problems

    want_share = round(entries / (closed + entries), 4)
    want_per_close = round(entries / closed, 4)
    if rework.get("rework_share") != want_share:
        problems.append(
            f"rework_share {rework.get('rework_share')!r} != {want_share} "
            "(entries / (closed subjects + entries))"
        )
    if rework.get("rework_per_close") != want_per_close:
        problems.append(
            f"rework_per_close {rework.get('rework_per_close')!r} != {want_per_close} "
            "(entries / closed subjects)"
        )
    if entries > 0 and want_share == want_per_close:
        problems.append("the two forms collapsed onto one number: they are not the same measure")

    # The two surfaces must name the same work unit as the denominator.
    if rework.get("closed_subjects") != delivery.get("closed_subjects"):
        problems.append("rework and delivery name different closed-subject denominators")
    if delivery.get("closed_tasks") != delivery.get("closed_subjects"):
        problems.append("closed_tasks and closed_subjects disagree")
    if delivery.get("close_events", 0) < delivery.get("closed_subjects", 0):
        problems.append("close_events < closed_subjects: a subject cannot close fewer times than it exists")
    return problems


def test_live_payload_states_both_forms():
    problems = rate_form_problems(load_audit())
    assert not problems, "; ".join(problems)


def test_close_events_reconciles_with_the_ledger():
    payload = load_audit()
    rows, subjects = ledger_close_counts()
    assert payload["delivery"]["close_events"] == rows, (
        f"audit reports {payload['delivery']['close_events']} close rows, the ledger holds {rows}"
    )
    assert payload["delivery"]["closed_subjects"] == subjects, (
        f"audit reports {payload['delivery']['closed_subjects']} closed subjects, "
        f"the ledger holds {subjects}"
    )


def test_gate_is_registered_in_the_audit():
    src = AUDIT.read_text(encoding="utf-8")
    registered = [ln for ln in src.splitlines() if GATE_CMD in ln and "gates_to_run.append" in ln]
    assert registered, f"{GATE_CMD} is not registered in the audit gate list"


def test_synthetic_probes_reject_each_regression():
    """The invariant must reject bad input, not merely accept good input."""
    good = {
        "rework": {
            "total_entries": 17,
            "closed_subjects": 29,
            "rework_share": round(17 / 46, 4),
            "rework_per_close": round(17 / 29, 4),
        },
        "delivery": {"closed_subjects": 29, "closed_tasks": 29, "close_events": 31},
    }
    assert rate_form_problems(good) == [], "the synthetic sound payload must pass"

    # 1. The old single-name form reappears.
    single = json.loads(json.dumps(good))
    single["rework"][FORBIDDEN] = single["rework"].pop("rework_share")
    assert any(FORBIDDEN in p for p in rate_form_problems(single))

    # 2. The two forms collapse onto the per-close value.
    collapsed = json.loads(json.dumps(good))
    collapsed["rework"]["rework_share"] = collapsed["rework"]["rework_per_close"]
    assert rate_form_problems(collapsed)

    # 3. A form is renamed away entirely.
    missing = json.loads(json.dumps(good))
    del missing["rework"]["rework_per_close"]
    assert any("rework_per_close" in p for p in rate_form_problems(missing))

    # 4. The denominator disagrees between the two surfaces.
    split = json.loads(json.dumps(good))
    split["delivery"]["closed_subjects"] = 31
    assert any("denominator" in p for p in rate_form_problems(split))

    # 5. Fewer close rows than closed subjects.
    short = json.loads(json.dumps(good))
    short["delivery"]["close_events"] = 12
    assert any("close_events < closed_subjects" in p for p in rate_form_problems(short))


def main() -> int:
    problems = rate_form_problems(load_audit())
    if problems:
        print("rate-form gate FAILED:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    rows, subjects = ledger_close_counts()
    payload = load_audit()
    rw = payload["rework"]
    print(
        f"rate forms OK — share {rw['rework_share']} = {rw['total_entries']}/({rw['closed_subjects']}"
        f"+{rw['total_entries']}), per close {rw['rework_per_close']} = {rw['total_entries']}/{rw['closed_subjects']}"
    )
    print(f"denominators reconciled — {rows} close rows over {subjects} distinct closed subjects")
    return 0


if __name__ == "__main__":
    sys.exit(main())
