#!/usr/bin/env python3
"""Operational Process Audit & Self-Audit Tool.

Upholds Process 3 (Internal Self-Audit / Operational Measurement).
Reads the evidence chain (ledger.jsonl, rework.md), computes operational
metrics (yield, rework rate, cadence, lead time), runs mechanical gates,
and records the run's own receipt: `--report` is ONE invocation that writes the
dated artifact AND its telemetry run row, while `--stamp` records a row alone and
writes no artifact, so it does not satisfy the report step.

Usage:
  python3 tools/audit.py              # Run check & print metrics/gates
  python3 tools/audit.py --json       # Output machine-readable JSON
  python3 tools/audit.py --report     # Write evidence/scores/<date>-self-audit.md AND its run row
  python3 tools/audit.py --stamp      # Record a run row only (no artifact)
"""

from __future__ import annotations

import argparse
import ctypes
import datetime
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parent.parent

# The telemetry reader is the SHARED predicate, never a local re-parse (issue #90).
# `n=405` PART 5 rules the CLASS — "it is why the class, not the three call sites, is
# the ruling" — so a fourth site may not carry its own scan. The path insert is the
# sibling form: this file is run as a script (its own dir is already on the path) and
# imported by `tests/`, and both must resolve the same reader.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from field_predicate import (  # noqa: E402
    declared_rework,
    declared_telemetry,
    mentioned_telemetry,
)

# The gate-budget reader, on the SAME path-insert convention and for the same
# reason: this file is run as a script (its own dir is already on the path) and
# imported by `tests/`, and both must resolve the same reader (issue #94).
from gate_budget import (  # noqa: E402
    GateBudgetManifestError,
    GateBudgets,
    TIMEOUT_EXIT_CODE,
    gate_key_for_cmd,
    load_gate_budgets,
)

# The `Subject` column's vocabulary, named once. `tests/test_rework.py` enforces the
# same three values on the document; they live here as well because the audit *reads*
# the column to derive a numerator, and a second hand-written pattern would let the
# gate and the reader disagree about what a determinate link looks like.
SUBJECT_NONE = "none"
SUBJECT_PRE_COLUMN = "not recorded (pre-column)"
SUBJECT_WORK_UNIT_RE = re.compile(r"#\d+")



# The `outcome` field's domain, named once (`docs/processes.md`: accepted · reworked ·
# abandoned · failed). Anything outside it is not an outcome, it is a typo.
OUTCOME_DOMAIN = ("accepted", "reworked", "abandoned", "failed")

def declared_outcome(detail: str) -> tuple[str, str | None]:
    """What the row DECLARES about its outcome: (bucket, problem).

    The bucket is one of the four domain values, or `"unstated"` when the row
    declares no outcome at all, or `"invalid:<value>"` when it declares one outside
    the domain. `problem` is a readable report for the two non-domain cases.

    Two rules, both from #53 (ruling n=333 clause 4):

    * **Read a FIELD, not the first `outcome=` substring in free prose.** The writer
      appends its trailer at the END of the detail, so the LAST `outcome=` token is
      the canonical one and an earlier mention is prose that happens to contain the
      word. The old reader took the FIRST substring and stripped nothing, so a close
      row whose prose ended `outcome=accepted.` yielded the value `accepted.` — the
      sentence's full stop travelling inside the value.
    * **Validate the value against the domain.** The old reader did not, so a typo
      read as a failure — it fabricated a non-success as readily as a success. The
      live instance was a close row whose prose read `outcome=accepted.`, with the
      sentence's full stop inside the value, which dropped a genuinely accepted
      work unit out of the success set.

    An unstated outcome is UNKNOWN. It is never `accepted`: that default is the
    defect this clause removes, and it is why the two headline rates could only
    report success.
    """
    value = None
    for part in str(detail).split():
        if part.startswith("outcome="):
            value = part.split("=", 1)[1]
    if value is None:
        return "unstated", None
    if value in OUTCOME_DOMAIN:
        return value, None
    return (
        f"invalid:{value}",
        f"outcome value {value!r} is outside the domain {OUTCOME_DOMAIN} — "
        f"reported, never bucketed as a verdict",
    )

def rework_bucket(value: str) -> str:
    """The FORM of a declared `rework` value — one bucket, never a verdict (#106).

    `work_unit` — a reference to the entry this close produced (`#N`), tested with the
    same `SUBJECT_WORK_UNIT_RE` the rework log's Subject column uses, so the count here
    and the gate that RESOLVES those references agree by construction. `none` — the close
    states it produced no entry. `unstated` — the row carries the absence token itself
    (#53 clause 2: an unrecorded disposition is UNKNOWN, never a value). `invalid:<value>`
    — anything else, reported by name rather than bucketed as a disposition.

    Classification lives here and not in `field_predicate.py` because it needs this
    module's vocabulary (`SUBJECT_WORK_UNIT_RE`, `SUBJECT_NONE`) and importing upward
    would invert the dependency; the POSITIONAL read stays there, where it is shared.
    `tests/test_rework_declared_landed.py` imports THIS function, so a value is never
    classified two ways.
    """
    if SUBJECT_WORK_UNIT_RE.fullmatch(value):
        return "work_unit"
    if value == SUBJECT_NONE:
        return "none"
    if value == "unstated":
        return "unstated"
    return f"invalid:{value}"

def format_rework_declaration_note(stats: dict[str, Any]) -> str:
    """The declaration count's buckets, so the share is never read alone (#106).

    Every bucket is printed. A row carrying `rework=unstated` is UNDECLARED, not a
    declaration — and a value outside the vocabulary is reported by name, because a
    malformed declaration silently counted as one is the defect the marker exists to
    make visible. The note states the PREDICATE with the number: the canonical trailer,
    read by position.
    """
    buckets = stats.get("rework_declarations_by_bucket", {}) or {}
    undeclared = stats.get("close_events", 0) - stats.get("close_rows_declaring_rework", 0)
    parts = [
        f"rework=#N {buckets.get('work_unit', 0)}",
        f"rework=none {buckets.get('none', 0)}",
        f"undeclared {undeclared}",
    ]
    if buckets.get("unstated", 0):
        parts.append(f"of which state rework=unstated {buckets.get('unstated', 0)}")
    invalid = stats.get("invalid_rework_reports", []) or []
    if invalid:
        parts.append(f"invalid {len(invalid)}")
    return (
        "canonical trailer read by position: " + "; ".join(parts)
        + " (printed, never gated — n=386 clause 5)"
    )


def format_yield_rate(stats: dict[str, Any]) -> str:
    """The yield as a percentage, or `n/a` when no run row states an outcome."""
    value = stats.get("first_pass_yield")
    return "n/a" if value is None else f"{round(value * 100, 1)}%"

def format_yield_note(stats: dict[str, Any]) -> str:
    """The yield's population and coverage, as the note column states it (clause 5)."""
    accepted = stats.get("runs_by_outcome", {}).get("accepted", 0)
    population = stats.get("first_pass_yield_population", 0)
    total = stats.get("run_events", 0)
    return (
        f"{accepted} accepted runs ÷ {population} runs stating an outcome "
        f"(coverage: {population} of {total} run rows)"
    )

def format_yield_text(stats: dict[str, Any]) -> str:
    """First-Pass Yield with its population and its coverage (clause 5).

    A rate is never printed alone. The undeclared rows are excluded from the ratio
    and COUNTED BESIDE IT, because counting them as accepted is the defect and
    counting them as failures would be a second fabrication in the other direction.
    The coverage is a printed disclosure, never a gate (clause 6): against
    append-only historical rows a threshold would be permanently RED with no lawful
    repair, which is the empty-repair-space defect ruled at n=328.
    """
    value = stats.get("first_pass_yield")
    population = stats.get("first_pass_yield_population", 0)
    total = stats.get("run_events", 0)
    accepted = stats.get("runs_by_outcome", {}).get("accepted", 0)
    rate = "n/a — no run row states an outcome" if value is None else f"{round(value * 100, 1)}%"
    return (
        f"{rate} ({accepted} accepted runs ÷ {population} runs stating an outcome "
        f"— coverage: {population} of {total} run rows)"
    )

def format_cost_per_success_text(stats: dict[str, Any]) -> str:
    """Cost / Successful Task with its population and its coverage (clause 5)."""
    return (
        f"${stats.get('cost_per_successful_task_usd', 0.0):.4f} "
        f"(${stats.get('total_cost_usd', 0.0):.4f} total cost ÷ "
        f"{stats.get('successful_closed_tasks', 0)} accepted closed subjects "
        f"— coverage: {stats.get('close_rows_stating_outcome', 0)} of "
        f"{stats.get('close_events', 0)} close rows state an outcome)"
    )

def format_cost_note(stats: dict[str, Any]) -> str:
    """Cost / Successful Task's population and coverage, for the note column."""
    return (
        f"${stats.get('total_cost_usd', 0.0):.4f} total cost ÷ "
        f"{stats.get('successful_closed_tasks', 0)} accepted closed subjects "
        f"(coverage: {stats.get('close_rows_stating_outcome', 0)} of "
        f"{stats.get('close_events', 0)} close rows state an outcome)"
    )

def format_out_of_trailer_note(stats: dict[str, Any]) -> str:
    """Which rows carry telemetry-shaped tokens the trailer scope EXCLUDED (issue #90).

    The count alone is a number without a referent: a reader cannot tell a census from
    a measurement without seeing the rows. So the note names them, and says why they
    are out — an exclusion that cannot be audited is indistinguishable from a loss.
    """
    rows = stats.get("out_of_trailer_rows", []) or []
    if not rows:
        return "none — every telemetry-shaped token in the ledger sits inside a canonical trailer"
    named = ", ".join(f"n={row.get('n')} ({row.get('event')})" for row in rows)
    return (
        "excluded from the totals above BY DESIGN: these rows carry a telemetry-shaped "
        f"token outside the canonical trailer — {named}. Read each as prose, not as spend"
    )

def format_undeclared_text(stats: dict[str, Any]) -> str:
    """What the ledger does NOT say, reported rather than absorbed (clause 4)."""
    reports = stats.get("invalid_outcome_reports", []) or []
    invalid = (
        f"; {len(reports)} invalid value(s) reported"
        if reports
        else "; no invalid value reported"
    )
    return (
        f"{stats.get('unstated_run_rows', 0)} run rows and "
        f"{stats.get('unstated_close_rows', 0)} close rows state none — UNKNOWN, "
        f"never accepted{invalid}"
    )

def parse_ledger(ledger_path: Path) -> tuple[dict[str, Any], set[str]]:
    """Parse ledger.jsonl and calculate operational delivery metrics, including token/cost economics.

    Returns the metrics payload *and* the set of distinct closed work units. The set
    travels beside the numbers rather than being re-derived per consumer, because it
    IS the denominator every per-task rate names: handing each rate its own copy of
    the count is how two rates come to state different populations (#34).
    """
    if not ledger_path.is_file():
        return {
            "exists": False,
            "total_events": 0,
            "event_counts": {},
            "closed_tasks": 0,
            "closed_subjects": 0,
            "close_events": 0,
            "intake_tasks": 0,
            "run_events": 0,
            "runs_by_outcome": {},
            "close_rows_by_outcome": {},
            "run_rows_stating_outcome": 0,
            "close_rows_stating_outcome": 0,
            "unstated_run_rows": 0,
            "unstated_close_rows": 0,
            "invalid_outcome_reports": [],
            "rework_declarations_by_bucket": {},
            "close_rows_declaring_rework": 0,
            "rework_declaration_rate": 0.0,
            "invalid_rework_reports": [],
            "first_pass_yield": 1.0,
            "first_pass_yield_population": 0,
            "first_pass_yield_coverage": [0, 0],
            "lead_times_sec": [],
            "avg_lead_time_sec": 0.0,
            "total_cost_usd": 0.0,
            "avg_cost_per_closed_task_usd": 0.0,
            "total_tokens_in": 0,
            "total_tokens_out": 0,
            "total_turns": 0,
            "out_of_trailer_rows": [],
            "out_of_trailer_count": 0,
            "latest_closed_subject": None,
            "spot_check": None,
        }, set()

    events: list[dict[str, Any]] = []
    with open(ledger_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except Exception:
                    pass

    event_counts: dict[str, int] = {}
    subjects_intake: dict[str, str] = {}
    subjects_claim: dict[str, str] = {}
    subjects_close: dict[str, str] = {}
    lead_times_sec: list[float] = []

    runs_by_outcome: dict[str, int] = {
        "accepted": 0,
        "failed": 0,
        "reworked": 0,
        "abandoned": 0,
    }
    close_rows_by_outcome: dict[str, int] = {}
    run_rows_stating_outcome = 0
    close_rows_stating_outcome = 0
    invalid_outcome_reports: list[str] = []
    # The close trailer's `rework` marker — the disposition a close DECLARES (#106,
    # ruling `n=386` clause 5). Read through the ONE predicate, `declared_rework`.
    rework_declarations_by_bucket: dict[str, int] = {}
    close_rows_declaring_rework = 0
    invalid_rework_reports: list[str] = []
    total_runs = 0
    total_cost_usd = 0.0
    total_tokens_in = 0
    total_tokens_out = 0
    total_turns = 0
    # Rows carrying a telemetry-shaped token OUTSIDE the canonical trailer (issue #90).
    # Recorded, never aggregated: they are the rows the trailer scope deliberately set
    # aside, and the count is what makes that exclusion auditable.
    out_of_trailer_rows: list[dict[str, Any]] = []

    successful_closed_subjects: set[str] = set()
    close_events = 0

    for ev in events:
        ev_type = ev.get("event", "unknown")
        event_counts[ev_type] = event_counts.get(ev_type, 0) + 1
        subj = ev.get("subject", "")
        ts = ev.get("ts", "")
        detail = ev.get("detail", "")

        # Telemetry is read from the canonical TRAILER, by POSITION and never by event
        # (issue #90 — this is `n=405` PART 5's class at its FOURTH call site). The old
        # form split the whole detail and took every `key=value` token, so a row that
        # REPORTED numbers was read as TAKING them: `n=382` is an intake row whose
        # `cost_usd=26` is a census — "26 close rows carry cost_usd" — and it became
        # the second-largest single cost in the ledger. Scope spans EVERY event, not
        # `close` only: 22 `run` rows carry canonical trailer telemetry, so an
        # event-scoped predicate would drop them.
        declared = declared_telemetry(detail)
        for key, value in declared:
            try:
                if key in ("cost_usd", "cost"):
                    total_cost_usd += float(value.rstrip("$"))
                elif key in ("tokens_in", "in_tokens"):
                    total_tokens_in += int(value)
                elif key in ("tokens_out", "out_tokens"):
                    total_tokens_out += int(value)
                elif key == "turns":
                    total_turns += int(value)
            except ValueError:
                pass

        # The rows whose telemetry-shaped tokens sit OUTSIDE the trailer, so the scope
        # above is auditable rather than silent. Visibility ONLY: these tokens are NOT
        # aggregated — that is the whole point — but a reader must be able to see what
        # the trailer scope set aside, and where. A multiset difference, so a token
        # both declared and merely mentioned still reports the mention.
        leftover = Counter(f"{k}={v}" for k, v in mentioned_telemetry(detail)) - Counter(
            f"{k}={v}" for k, v in declared
        )
        if leftover:
            out_of_trailer_rows.append(
                {"n": ev.get("n"), "event": ev_type, "tokens": sorted(leftover)}
            )

        if ev_type == "intake" and subj and subj not in subjects_intake:
            subjects_intake[subj] = ts
        elif ev_type == "claim" and subj and subj not in subjects_claim:
            subjects_claim[subj] = ts
        elif ev_type == "close" and subj:
            subjects_close[subj] = ts
            close_events += 1
            close_outcome, close_problem = declared_outcome(detail)
            close_rows_by_outcome[close_outcome] = close_rows_by_outcome.get(close_outcome, 0) + 1
            if close_problem:
                invalid_outcome_reports.append(f"n={ev.get('n')} close {subj}: {close_problem}")
            if close_outcome in OUTCOME_DOMAIN:
                close_rows_stating_outcome += 1
            if close_outcome == "accepted":
                successful_closed_subjects.add(subj)
            # One ROW declares one disposition, so the row count is taken once per
            # row however many tokens the run carries (the law gives a row one; the
            # list is what lets the resolving gate see every token it must resolve).
            row_declares = False
            for rework_value in declared_rework(detail):
                bucket = rework_bucket(rework_value)
                rework_declarations_by_bucket[bucket] = (
                    rework_declarations_by_bucket.get(bucket, 0) + 1
                )
                if bucket in ("work_unit", "none"):
                    row_declares = True
                elif bucket.startswith("invalid:"):
                    invalid_rework_reports.append(
                        f"n={ev.get('n')} close {subj}: rework value {rework_value!r} "
                        f"is not a work-unit reference (#N) or 'none'"
                    )
            if row_declares:
                close_rows_declaring_rework += 1

            if subj in subjects_intake:
                try:
                    t_in = datetime.datetime.fromisoformat(subjects_intake[subj].replace("Z", "+00:00"))
                    t_cl = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    diff = (t_cl - t_in).total_seconds()
                    if diff >= 0:
                        lead_times_sec.append(diff)
                except Exception:
                    pass

        elif ev_type == "run":
            total_runs += 1
            outcome, outcome_problem = declared_outcome(detail)
            runs_by_outcome[outcome] = runs_by_outcome.get(outcome, 0) + 1
            if outcome_problem:
                invalid_outcome_reports.append(f"n={ev.get('n')} run {subj}: {outcome_problem}")
            if outcome in OUTCOME_DOMAIN:
                run_rows_stating_outcome += 1

    # First-pass yield: accepted runs ÷ the run rows that STATE an outcome.
    #
    # Not ÷ every run row. A row declaring no outcome is UNKNOWN, not a success
    # (#53, ruling n=333 clause 2): counting it as accepted is the defect, and
    # counting it as a failure would be a second fabrication in the other
    # direction. So it is excluded from the ratio and COUNTED BESIDE IT — the
    # printed coverage is what tells a reader how much of the ledger the number
    # speaks for (clause 5). No gate rides on the coverage (clause 6): against
    # append-only historical rows a threshold would be permanently RED with no
    # lawful repair, the empty-repair-space defect ruled at n=328.
    #
    # With runs present and not one stating an outcome the ratio is UNDEFINED, and
    # 1.0 would be exactly the favourable fabrication this clause removes.
    unstated_run_rows = runs_by_outcome.get("unstated", 0)
    unstated_close_rows = close_rows_by_outcome.get("unstated", 0)
    if run_rows_stating_outcome > 0:
        yield_val: float | None = (
            runs_by_outcome.get("accepted", 0) / run_rows_stating_outcome
        )
    elif total_runs > 0:
        yield_val = None
    else:
        yield_val = 1.0

    avg_lead_time = (sum(lead_times_sec) / len(lead_times_sec)) if lead_times_sec else 0.0
    # The work unit is a distinct closed SUBJECT, never a close ROW: a subject that is
    # re-opened and closed again carries two close rows, and counting rows would inflate
    # every per-task denominator. `close_events` travels beside it so the two are
    # reconcilable rather than silently disagreeing.
    closed_count = len(subjects_close)
    successful_closed_tasks = len(successful_closed_subjects)
    avg_cost_per_closed_task = (total_cost_usd / closed_count) if closed_count > 0 else 0.0
    cost_per_successful_task = (total_cost_usd / successful_closed_tasks) if successful_closed_tasks > 0 else 0.0

    # Spot check the latest closed subject
    latest_closed = None
    spot_check = None
    for ev in reversed(events):
        if ev.get("event") == "close":
            latest_closed = ev.get("subject")
            break

    if latest_closed:
        has_in = latest_closed in subjects_intake
        has_clm = latest_closed in subjects_claim
        spot_check = {
            "subject": latest_closed,
            "intake_verified": has_in,
            "claim_verified": has_clm,
            "close_verified": True,
            "sequence_intact": has_in and has_clm,
        }

    return {
        "exists": True,
        "total_events": len(events),
        "event_counts": event_counts,
        "closed_tasks": closed_count,
        "closed_subjects": closed_count,
        "close_events": close_events,
        "intake_tasks": len(subjects_intake),
        "run_events": total_runs,
        "runs_by_outcome": runs_by_outcome,
        "close_rows_by_outcome": close_rows_by_outcome,
        "run_rows_stating_outcome": run_rows_stating_outcome,
        "close_rows_stating_outcome": close_rows_stating_outcome,
        "unstated_run_rows": unstated_run_rows,
        "unstated_close_rows": unstated_close_rows,
        "invalid_outcome_reports": invalid_outcome_reports,
        "rework_declarations_by_bucket": rework_declarations_by_bucket,
        "close_rows_declaring_rework": close_rows_declaring_rework,
        "rework_declaration_rate": round(
            close_rows_declaring_rework / close_events if close_events > 0 else 0.0, 4
        ),
        "invalid_rework_reports": invalid_rework_reports,
        "first_pass_yield": round(yield_val, 4) if yield_val is not None else None,
        "first_pass_yield_population": run_rows_stating_outcome,
        "first_pass_yield_coverage": [run_rows_stating_outcome, total_runs],
        "lead_times_sec": lead_times_sec,
        "avg_lead_time_sec": round(avg_lead_time, 1),
        "total_cost_usd": round(total_cost_usd, 4),
        "avg_cost_per_closed_task_usd": round(avg_cost_per_closed_task, 4),
        "cost_per_successful_task_usd": round(cost_per_successful_task, 4),
        "successful_closed_tasks": successful_closed_tasks,
        "total_tokens_in": total_tokens_in,
        "total_tokens_out": total_tokens_out,
        "total_turns": total_turns,
        "out_of_trailer_rows": out_of_trailer_rows,
        "out_of_trailer_count": len(out_of_trailer_rows),
        "latest_closed_subject": latest_closed,
        "spot_check": spot_check,
    }, set(subjects_close)


def parse_rework(rework_path: Path, closed_subject_set: set[str]) -> dict[str, Any]:
    """Parse rework.md for defects, unprevented items, and both rework rates.

    Two forms are returned, each named with its own denominator, because two
    different numbers travel under the name "rework rate" and the wrong one gets
    quoted:

      * rework_share     — entries ÷ (closed subjects + entries): how much of the
                           work done was repair. The form comparable across factories.
      * rework_per_close — entries ÷ closed subjects: repair paid per unit of
                           planned work.

    The denominator is distinct closed SUBJECTS, never close rows: a subject
    re-closed after a re-open must not inflate it. It arrives as the ledger's own
    closed-subject SET rather than as a count, so the population cannot drift between
    this function and its caller.

    A third metric is returned: **change fail rate** (O2 Stability) — closes that
    produced a rework entry ÷ closed work units — with its linkage coverage. The
    numerator is DERIVED from the `Subject` column, never stated: an entry counts only
    when its Subject names a work unit that actually closed, so a `#N` pointing at
    something that never landed is not a failed change. Coverage is mandatory and
    travels in the same payload, because an under-linked numerator of 0 reads as
    "nothing ever failed" when the truth is "nothing is linked".
    """
    closed_subjects = len(closed_subject_set)
    if not rework_path.is_file():
        return {
            "exists": False,
            "total_entries": 0,
            "unprevented_entries": 0,
            "closed_subjects": closed_subjects,
            "rework_share": 0.0,
            "rework_per_close": 0.0,
            "change_fail_rate": 0.0,
            "change_fail_rate_numerator": 0,
            "change_fail_rate_denominator": closed_subjects,
            "subject_coverage": 0.0,
            "subject_coverage_numerator": 0,
            "subject_coverage_denominator": 0,
        }

    entries = 0
    unprevented = 0
    determinate = 0
    change_failures = 0
    with open(rework_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("|") and not line.startswith("| Column") and not line.startswith("|---"):
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 7 and parts[1] and not parts[1].startswith("Date") and not parts[1].startswith("*"):
                    entries += 1
                    prevented_col = parts[6].lower()
                    if "nothing yet" in prevented_col or not prevented_col:
                        unprevented += 1
                    subject_col = parts[7] if len(parts) > 7 else ""
                    if SUBJECT_WORK_UNIT_RE.fullmatch(subject_col):
                        determinate += 1
                        if subject_col in closed_subject_set:
                            change_failures += 1
                    elif subject_col == SUBJECT_NONE:
                        # Caught before any change landed: determinate, not a failure.
                        determinate += 1

    rework_share = (entries / (closed_subjects + entries)) if (closed_subjects + entries) > 0 else 0.0
    rework_per_close = (entries / closed_subjects) if closed_subjects > 0 else 0.0
    change_fail_rate = (change_failures / closed_subjects) if closed_subjects > 0 else 0.0
    subject_coverage = (determinate / entries) if entries > 0 else 0.0

    return {
        "exists": True,
        "total_entries": entries,
        "unprevented_entries": unprevented,
        "closed_subjects": closed_subjects,
        "rework_share": round(rework_share, 4),
        "rework_per_close": round(rework_per_close, 4),
        "change_fail_rate": round(change_fail_rate, 4),
        "change_fail_rate_numerator": change_failures,
        "change_fail_rate_denominator": closed_subjects,
        "subject_coverage": round(subject_coverage, 4),
        "subject_coverage_numerator": determinate,
        "subject_coverage_denominator": entries,
    }


def run_gate(cmd: list[str], cwd: Path, budget_sec: float) -> dict[str, Any]:
    """Run an individual verification gate under its DECLARED time budget.

    `budget_sec` is a PARAMETER, never a constant, and that is the point of #94: the
    cap is a declared multiple of a measured runtime read from `registry/gates.json`
    (ruling n=744), so this function cannot know it and must not invent one.

    A gate that exhausts its budget is UNKNOWN -- it neither passed nor failed, and
    reporting it as either would be a verdict nobody measured. It carries the
    `unknown` flag and a DISTINCT exit code, so a killed gate is never read as a
    failed one; its recorded duration is the MEASURED elapsed time, because a
    timeout is a fact about the gate and must be readable as one.

    ONE BOUNDED RETRY, and ONLY for a timeout (#93 ruling n=574 PART 4). A
    load-dependent timeout is transient by nature, so a single retry distinguishes a
    flake from a gate that is genuinely too slow; a SECOND timeout is UNKNOWN. The
    retry is bounded to exactly one and its occurrence is RECORDED (`attempts`,
    `retried`, `first_attempt_sec`), because an unrecorded retry becomes a way to hide
    a gate that is genuinely too slow. It does NOT reopen the never-re-send family:
    that family governs duplicated SIDE EFFECTS, and a gate is a READ -- re-running it
    changes no state, so the reason for the ban is absent. A genuine FAIL (a non-zero
    exit) is a VERDICT and is never retried; only a timeout, which is no verdict at
    all, is.
    """
    attempts = 0
    first_attempt_sec: float | None = None
    while True:
        attempts += 1
        t0 = datetime.datetime.now()
        try:
            res = subprocess.run(
                cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=budget_sec,
                # The orphan half of #145: a gate must not outlive the run that started
                # it. `preexec_fn` leaves `cmd` untouched, so the budget key still
                # describes the command that ran.
                preexec_fn=_orphan_guard(),
            )
            t_el = (datetime.datetime.now() - t0).total_seconds()
            return {
                "cmd": " ".join(cmd),
                "exit_code": res.returncode,
                "passed": res.returncode == 0,
                "unknown": False,
                "duration_sec": round(t_el, 2),
                "attempts": attempts,
                "retried": attempts > 1,
                "stdout": res.stdout.strip(),
                "stderr": res.stderr.strip(),
            }
        except subprocess.TimeoutExpired:
            t_el = (datetime.datetime.now() - t0).total_seconds()
            if attempts == 1:
                first_attempt_sec = round(t_el, 2)
                continue
            return {
                "cmd": " ".join(cmd),
                "exit_code": TIMEOUT_EXIT_CODE,
                "passed": False,
                "unknown": True,
                "duration_sec": round(t_el, 2),
                "attempts": attempts,
                "retried": True,
                "first_attempt_sec": first_attempt_sec,
                "stdout": "",
                "stderr": (
                    f"budget exhausted: the gate was killed at {budget_sec:.2f}s after "
                    f"running {t_el:.2f}s, and killed AGAIN on the one bounded retry "
                    f"(first attempt {first_attempt_sec}s) -- UNKNOWN, no verdict taken"
                ),
            }
        except Exception as e:
            t_el = (datetime.datetime.now() - t0).total_seconds()
            return {
                "cmd": " ".join(cmd),
                "exit_code": 99,
                "passed": False,
                "unknown": False,
                "duration_sec": round(t_el, 2),
                "attempts": attempts,
                "retried": attempts > 1,
                "stdout": "",
                "stderr": str(e),
            }


def last_reported_line(text: str, limit: int = 200) -> str:
    """The last non-blank line of a gate's output, whitespace-collapsed and BOUNDED.

    The LAST line, because a failing gate states its reason at the end of what it
    prints -- pytest writes its failure list there, and a killed gate writes its
    reason there too. BOUNDED, because this lands on one line of the headline report
    whose job is to let the reader decide whether to RE-RUN, not to reproduce the log.

    One helper, two call sites (the stdout report and the markdown report), so the two
    surfaces cannot disagree about which line states the cause.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ""
    return " ".join(lines[-1].split())[:limit]


GATE_CAUSE_LIMIT = 140
"""One bound for a failing gate's recorded cause, shared by every surface that prints it.

Raised from the 60 the markdown cell used, because a SCRIPT-shaped failure states a COUNT
and a SPECIMEN and 60 characters cannot hold both (issue #158). The bound is KEPT: this
lands on one line of a table whose job is to let the reader decide whether to RE-RUN, not
to reproduce the log.
"""

_COUNT_FIRST_RE = re.compile(r"\b\d+\s+(?:problem|violation)\(s\)", re.IGNORECASE)

def reported_cause(text: str, limit: int = GATE_CAUSE_LIMIT) -> str:
    """A failing gate's cause: its COUNT when the output carries one, AND its last line.

    The kit ships TWO output shapes and they put the summary in DIFFERENT places. A
    PYTEST-shaped gate writes its failure list LAST and carries no count line, so the last
    line IS the reason. A SCRIPT-shaped gate prints `N problem(s) in <path>` FIRST and then
    N violations, so the last line is one ARBITRARY specimen and the total is lost --
    measured on tests/test_ledger_schema.py, where SIX problems were recorded as a single
    truncated tail violation (issue #158).

    So the count line is recorded FIRST when one exists, and the last line is appended as
    the specimen. Both share ONE bound, and the join keeps the HEAD, so the count cannot be
    crowded out by a specimen longer than the remaining budget.
    """
    lines = [" ".join(ln.split()) for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ""
    last = lines[-1]
    counted = next((ln for ln in lines if _COUNT_FIRST_RE.search(ln)), None)
    if counted is None or counted == last:
        return last[:limit]
    return f"{counted} \u2014 {last}"[:limit]

def attach_gate_causes(gate_results: list[dict]) -> None:
    """Set `note` on every gate that did not pass, from the ONE predicate above.

    Computed once and read by all three surfaces (the JSON payload, the markdown report
    and the stdout headline), so they cannot disagree about what the gate said. A PASSING
    gate carries no note; an UNKNOWN gate is not a pass and does carry one.
    """
    for g in gate_results:
        if g.get("passed"):
            g.pop("note", None)
            continue
        g["note"] = reported_cause(g.get("stdout") or "") or reported_cause(g.get("stderr") or "")

@dataclass
class GateVerdict:
    """The THREE-state verdict over a gate run (#93 ruling n=574 PART 2).

    GREEN / DEGRADED / UNKNOWN, and `None` when the suite was SKIPPED -- a skipped
    suite reports no verdict at all, because `all([])` is True and leaving `healthy`
    to be computed over it would print a green over gates that never ran (#28).

    UNKNOWN is a state of its own and NEVER a pass. A gate that exhausted its budget
    did not run to a verdict, so counting it in the pass total would be the vacuous
    pass in a new coat -- and reporting it as a failure would assert a verdict nobody
    measured. It is therefore in NEITHER the pass total nor the failure list, and it is
    as LOUD as FAIL: `status` is UNKNOWN, `healthy` is False, and the caller prints it.
    The three populations are carried apart so a report can state all three counts
    instead of collapsing them into one.

    `healthy` keeps the bool/None shape its existing consumers expect
    (`tools/roadmap.py` reads it, and the telemetry outcome below derives from it):
    True ONLY for GREEN, False for DEGRADED and for UNKNOWN, None when skipped.
    """

    status: str | None
    healthy: bool | None
    all_known_pass: bool | None
    passed: list[dict[str, Any]]
    failed: list[dict[str, Any]]
    unknown: list[dict[str, Any]]

    @property
    def examined(self) -> int:
        """Gates that RAN TO A VERDICT -- the population the pass total is taken over."""
        return len(self.passed) + len(self.failed)

    @property
    def total(self) -> int:
        """Every gate the runner attempted, UNKNOWN included."""
        return self.examined + len(self.unknown)


def judge_gates(
    gate_results: list[dict[str, Any]], cadence_ok: bool = True, gates_ran: bool = True
) -> GateVerdict:
    """Reduce gate results to the three-state verdict, keeping the populations apart.

    PURE over its inputs and free of I/O, so a probe can drive it with synthetic
    results -- including a timed-out gate -- without running the suite it judges. The
    headline's state is therefore testable without the 45-gate wall around it.

    A FAIL is a MEASURED statement and outranks an UNKNOWN, which is the absence of
    one: when a gate genuinely failed, DEGRADED is the verdict, and the UNKNOWN gates
    are still counted and named on the headline beside it rather than swallowed.
    """
    if not gates_ran:
        return GateVerdict(None, None, None, [], [], [])
    unknown = [g for g in gate_results if g.get("unknown")]
    failed = [g for g in gate_results if not g.get("unknown") and not g["passed"]]
    passed = [g for g in gate_results if not g.get("unknown") and g["passed"]]
    # The pass total is taken over the gates that ran to a verdict. An UNKNOWN is in
    # neither column: not a pass (that is the vacuous green) and not a failure (that is
    # a verdict nobody measured). `all([])` is True, which is right -- no gate ran to a
    # verdict and no gate failed -- and the status is UNKNOWN, so it is not a green.
    all_known_pass = all(g["passed"] for g in passed + failed)
    if failed or not cadence_ok:
        status = "DEGRADED"
    elif unknown:
        status = "UNKNOWN"
    else:
        status = "GREEN"
    return GateVerdict(status, status == "GREEN", all_known_pass, passed, failed, unknown)


def render_status_line(verdict: GateVerdict) -> str:
    """The headline. THREE states, and UNKNOWN is never rendered as a green (#93 PART 2).

    `HEALTHY` stays in the green line because this factory's law, docs and close-row
    prose all name that state by it, while `GREEN` is the canonical three-state term the
    ruling uses -- so the line carries BOTH and no reader has to know which vocabulary
    the other surface was written in.

    UNKNOWN is printed with the population that produced it (`N of M`), because a
    third state that renders without its count is indistinguishable from one that never
    fired -- the same population-visibility rule the default-budget print already obeys.
    """
    if verdict.status is None:
        return "Status: GATES SKIPPED (metrics only)"
    if verdict.status == "GREEN":
        return (
            f"Status: HEALTHY (GREEN) — all {verdict.examined} gate(s) that ran to a "
            f"verdict passed"
        )
    if verdict.status == "UNKNOWN":
        return (
            f"Status: UNKNOWN — {len(verdict.unknown)} of {verdict.total} gate(s) "
            f"exhausted their budget and returned NO verdict; they are counted in no "
            f"pass total, and this is NOT a green"
        )
    line = f"Status: DEGRADED (FAIL) — {len(verdict.failed)} gate(s) failed"
    if verdict.unknown:
        line += (
            f", and {len(verdict.unknown)} more exhausted their budget "
            f"(UNKNOWN, no verdict taken)"
        )
    return line


# PR_SET_PDEATHSIG's opcode (linux/prctl.h). Named rather than inlined so the one
# call below reads as what it is.
PR_SET_PDEATHSIG = 1

# The whole-run in-flight guard's lock, and its refusal exit code (issue #145, ruling
# n=940 Q2). The lock sits at the repo root and is covered by `.gitignore`'s `.*.lock`
# rule, the same idiom `.ledger.lock` and `.insights.lock` already use.
AUDIT_LOCK = REPO_ROOT / ".audit.lock"
LOCK_HELD_EXIT_CODE = 3

def _orphan_guard() -> Callable[[], None]:
    """Build the child-side `preexec_fn` that binds a child's life to THIS process.

    THE PROPERTY (issue #145, ruling n=940): no process in a run's tree outlives the
    run. The lock does NOT close this — a dead holder releases the lock, so the lock
    never sees an orphan, and the orphan is exactly the load the guard exists to bound:
    a gate left running after its audit was killed keeps burning the cgroup the next
    run is about to contend for.

    WHY `preexec_fn` AND NOT A WRAPPER: the gate's command line IS its budget key
    (`gate_key_for_cmd`), so prefixing a supervisor onto `cmd` would silently re-key
    every entry in the manifest. `preexec_fn` runs in the forked child before `exec`,
    so the command line the budget describes is the command line that runs.

    WHY IT IS SAFE HERE: `preexec_fn` is documented as unsafe in a threaded program,
    and this runner is single-threaded — the gate loop is sequential and nothing in
    this file starts a thread.

    FAIL-OPEN, deliberately: on a platform without `prctl` the call is skipped and the
    run proceeds unguarded. The property is a load bound, never a correctness
    condition, so losing it must not stop an audit from running.

    THE RACE, and why the `getppid` check is not decoration: `PR_SET_PDEATHSIG` arms
    only for deaths AFTER it is set, so a parent that died between `fork` and this
    call leaves a child that would never be signalled. Re-parenting is detectable
    precisely because the parent pid changes, so a child that finds a different
    `getppid` exits itself rather than outliving the run that spawned it.
    """
    parent_pid = os.getpid()

    def _bind() -> None:
        try:
            libc = ctypes.CDLL("libc.so.6", use_errno=True)
            libc.prctl(PR_SET_PDEATHSIG, signal.SIGKILL, 0, 0, 0)
        except Exception:
            return
        if os.getppid() != parent_pid:
            os._exit(0)

    return _bind

def acquire_run_lock(*, wait: bool = False, lock_path: Path | None = None) -> Any | None:
    """Take the whole-run lock, or refuse. Returns the held handle, or None on refusal.

    SCOPE (ruling n=940 Q1): the contended unit is the RUN, not the gate. The gate loop
    is sequential — `for cmd in gates_to_run` — so one run can never overlap itself, and
    a per-gate guard would bound nothing while adding a lock acquisition per gate.

    WHY REFUSE AND NOT WAIT (Q2): `flock` self-heals, so the safety argument for
    refusing is gone; the argument that remains is that WAITING IS WHAT CREATES THE
    ORPHAN — a lane's turn that blocks on the lock can die before it ever holds it, and
    the run it was waiting to start then belongs to nobody. So the default is a
    non-blocking refuse and `--wait` is the caller's opt-in.

    The handle is returned rather than kept in a global so the lock's lifetime is the
    caller's `with` block, and the refusal is a NAMED stderr line so a consumer can tell
    did-not-run from ran-and-failed. Nothing is written on the refusal path — no run
    row: `OUTCOME_DOMAIN` is a closed four-token set and a refused run did no work, so
    its row would either red a gate or let it grade the yield it never measured.
    """
    path = AUDIT_LOCK if lock_path is None else lock_path
    try:
        handle = open(path, "w")
    except OSError as exc:
        # An unopenable lock is a DEFECT, never a silent fallback to unguarded running:
        # falling through would make the guard's absence indistinguishable from a free
        # lock, which is the exempt-by-silence shape this factory forbids.
        print(
            f"audit in-flight guard: cannot open the run lock at {path} — {exc}",
            file=sys.stderr,
        )
        return None
    flags = fcntl.LOCK_EX if wait else (fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        fcntl.flock(handle, flags)
    except OSError:
        handle.close()
        print(
            f"audit in-flight guard: another audit run holds {path} — this run did NOT "
            f"start, no gate ran and no run row was written (re-run when it finishes, "
            f"or pass --wait to block on it)",
            file=sys.stderr,
        )
        return None
    return handle

def execute_mechanical_gates(repo_root: Path) -> tuple[list[dict[str, Any]], GateBudgets]:
    """Execute all discovered mechanical gates, and return the budgets they resolved against.

    The budgets come back WITH the results because the manifest's declared revisions are
    swept as they are read (#125, ruling n=786), and that sweep's account has to reach a
    printer. Returning it here costs one tuple and keeps the read at ONE call site: a
    second `load_gate_budgets()` in `main()` would re-read a file that may have changed
    under it, so the caps and the sweep could describe two different manifests.
    """
    gates_to_run: list[list[str]] = []

    # 1. Ledger verify
    if (repo_root / "tools/ledger.py").is_file():
        gates_to_run.append([sys.executable, "tools/ledger.py", "verify"])

    # 2. Ontology gate
    if (repo_root / "tests/test_ontology.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_ontology.py"])

    # 3. Rework gate
    if (repo_root / "tests/test_rework.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_rework.py"])

    # 4. Single-writer gate
    if (repo_root / "tests/test_single_writer.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_single_writer.py"])

    # 5. Ledger schema & domain invariant gate
    if (repo_root / "tests/test_ledger_schema.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_ledger_schema.py"])

    # 6. Template sync gate
    if (repo_root / "tests/test_template_sync.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_template_sync.py"])

    # 7. Workspace hygiene audit
    if (repo_root / "tools/hygiene.py").is_file():
        gates_to_run.append([sys.executable, "tools/hygiene.py", "--audit"])

    # 8. Visual roadmap and process-to-product matrix audit
    if (repo_root / "tools/roadmap.py").is_file():
        gates_to_run.append([sys.executable, "tools/roadmap.py", "--audit"])

    # 9. Best practice law-to-gate coverage audit (P29)
    if (repo_root / "tests/test_law_coverage.py").is_file():
        gates_to_run.append([sys.executable, "-m", "pytest", "tests/test_law_coverage.py"])

    # 10. Session binding and UUID integrity audit
    if (repo_root / "tests/test_session_bindings.py").is_file():
        gates_to_run.append([sys.executable, "-m", "pytest", "tests/test_session_bindings.py"])
    # 11. Law structure audit: numbered sections contiguous in every law file
    if (repo_root / "tests/test_law_structure.py").is_file():
        gates_to_run.append([sys.executable, "-m", "pytest", "tests/test_law_structure.py"])

    # 12. Documentation sync gate: a doc shipped in both trees must not drift
    if (repo_root / "tests/test_docs_sync.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_docs_sync.py"])

    # 13. Hygiene namespace gate: the scratch audit globs only owned prefixes
    if (repo_root / "tests/test_hygiene_namespace.py").is_file():
        gates_to_run.append([sys.executable, "-m", "pytest", "tests/test_hygiene_namespace.py"])
    # 14. Rate gate: the rework number is reported in two named forms and the change
    #     fail rate with its linkage coverage — each carrying its own denominator, and
    #     the numerator derived from the log rather than stated (issues #31 and #34).
    if (repo_root / "tests/test_audit_rates.py").is_file():
        gates_to_run.append([sys.executable, "-m", "pytest", "tests/test_audit_rates.py"])
    # 15. Score-gate verdict gate: a measurement run records its closing workspace-gate
    #     verdict and the HEAD sha it committed at (issue #32).
    if (repo_root / "tests/test_score_gate_recorded.py").is_file():
        gates_to_run.append([sys.executable, "-m", "pytest", "tests/test_score_gate_recorded.py"])
    # 16. HQ delegation gate: HQ implements nothing, and every law that declares lanes
    #     declares one for HQ to delegate to (owner order 2026-09-18 — retires the
    #     "HQ alone is a valid answer" doctrine).
    if (repo_root / "tests/test_hq_delegation.py").is_file():
        gates_to_run.append([sys.executable, "-m", "pytest", "tests/test_hq_delegation.py"])
    # 17. Template integrity gate: every file the template ships is accounted for by a
    #     pair, a class or a declared entry, and every add-on pack is registered
    #     (issues #33 and #35). Run under pytest so the in-flight-window probes
    #     travel with it (issue #38 — an uncommitted-yet file is not unshipped).
    if (repo_root / "tests/test_template_integrity.py").is_file():
        gates_to_run.append([sys.executable, "-m", "pytest", "tests/test_template_integrity.py"])
    # 18. Hygiene in-flight gate: the working-tree audit separates a lane's live
    #     work (advisory) from an abandoned path (violation), and the run-scoped
    #     invariant still blocks with no grace (issue #38; #28 stays fixed).
    if (repo_root / "tests/test_hygiene_inflight.py").is_file():
        gates_to_run.append([sys.executable, "-m", "pytest", "tests/test_hygiene_inflight.py"])
    # 19. Board-close gate: every close row records that the board issue was closed
    #     with it, so a subject cannot be complete-by-ledger while still open on the
    #     board (issue #44).
    if (repo_root / "tests/test_close_board_recorded.py").is_file():
        gates_to_run.append([sys.executable, "-m", "pytest", "tests/test_close_board_recorded.py"])

    # 20. Ledger clause gate: a commit carrying the ledger names the concern and cites no
    #     row numbers — forward-only, bounded by a marker commit, because a history-wide
    #     form would be permanently red (issue #47, clause 4).
    if (repo_root / "tests/test_ledger_commit_cites_no_rows.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_ledger_commit_cites_no_rows.py"])

    # 21. Commit pathspec law gate: the shared-tree rule is stated on the repo law and on
    #     every card that commits, and it names the invocation rather than only the flags
    #     it forbids — the shape the defect slipped past (issue #47, clause 1, P29).
    if (repo_root / "tests/test_commit_pathspec_law.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_commit_pathspec_law.py"])

    # 22. Criteria-count gate: every stated quality-criteria/family count on a scanned law
    #     or doc surface matches the live rubric, with a labelled historical reference
    #     excused — the number was stated in twelve places and checked in none, so it
    #     drifted silently (issue #43, P29).
    if (repo_root / "tests/test_criteria_count.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_criteria_count.py"])

    # 23. Synthesizer interface gate: the tool's usage block advertises exactly the
    #     flags argparse defines, and its rework parser is width-safe and reads the
    #     Defect column rather than the Source column beside it (issue #42).
    if (repo_root / "tests/test_synthesize_interface.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_synthesize_interface.py"])

    # 24. Roadmap-transition gate: the product declaration is factory data, not template
    #     law, so an un-onboarded factory is RED by design — and the gate asserts the
    #     correspondence (green iff declared artifacts exist), not a state. It was born
    #     permanently red because the product list shipped inside the paired tool and one
    #     entry was an artifact no other factory can have (issue #40, P29).
    if (repo_root / "tests/test_roadmap_transition.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_roadmap_transition.py"])

    # 25. Board-intake gate: a board issue and its ledger `intake` row are two records
    #     of one act, so the predicate reads both and reports each direction under its
    #     own soundness condition — forward over the open set, reverse only over the
    #     FULL board, with a pre-gate subject excused rather than backfilled. Nothing
    #     read the board against the ledger, so an owner-filed issue could sit open with
    #     no intake row while each surface stayed internally consistent (issue #56, P29).
    if (repo_root / "tests/test_board_intake_recorded.py").is_file():
        gates_to_run.append([sys.executable, "-m", "pytest", "tests/test_board_intake_recorded.py"])

    # 26. Gate-fixture closure gate: a fixture that runs a tool inside a throwaway tree
    #     must stage the tool's import CLOSURE, not the file alone. Copying the file alone
    #     encodes an unstated assumption of self-containment, so it holds silently until
    #     the tool gains a lawful intra-repo import — and then the gate reds on a correct
    #     change and the red misreads as the tool's fault. The predicate resolves
    #     module-level path constants, because the fourth site stages its tool as
    #     `copy2(REPO_ROOT / TOOL_REL, ...)` and a literal-only match reports it clean
    #     (issue #60, P35, P29).
    if (repo_root / "tests/test_gate_fixtures_closure.py").is_file():
        gates_to_run.append([sys.executable, "-m", "pytest", "tests/test_gate_fixtures_closure.py"])

    # 27. Ledger gate: the single-writer claim, tested rather than asserted — twenty
    #     concurrent appends keep the row numbers 1..N, the append-time guard refuses a
    #     reverted working file, and the refusal names the first divergent row. The law
    #     cites this file as the PROOF of the property, yet nothing registered it, so the
    #     probes ran nowhere while the audit printed HEALTHY over them. Its absence is
    #     itself probed from inside the file (issue #59, P29).
    if (repo_root / "tests/test_ledger.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_ledger.py"])


    # 28. Gate-registry gate: every file that declares itself a gate must be REGISTERED
    #     in this file, and declare itself CANONICALLY. A gate that never runs is
    #     indistinguishable from a gate that passes — that was #59, and the proof it is a
    #     CLASS and not one file is that tests/test_gate_fixtures_closure.py was born
    #     unregistered during #59's own fix window. A self-check closes the carrier only,
    #     so the scan extracts LOOSELY (any tests/test_*.py whose opening docstring line
    #     contains "gate") and asserts STRICTLY on top, so a departure from the canonical
    #     opener is loud rather than invisible (issue #59, P29).
    if (repo_root / "tests/test_gate_registration.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_gate_registration.py"])

    # 29. Close-row revision gate: a close row's receipts describe a TREE, so the row must
    #     name the revision it measured. Without it the receipt is not false, it is
    #     UNCHECKABLE — a reader cannot tell whether "27 gates, 0 FAIL" describes the tree
    #     that shipped or one that has since moved four commits. The value is validated as
    #     a FIELD (`head=<sha>`), never as prose: measured at landing, a loose hex-shaped
    #     pattern matches 30 of 54 close rows but only 4 carry the field, and a hex-shaped
    #     token is not even necessarily a revision — 2 of the 30 match only inside the
    #     append tool's own telemetry trailer (`tokens_out=`, rows n=349 and n=353) and 7
    #     more cite a 10-digit GitHub comment id that `git cat-file -t` does not resolve
    #     (n=10, 303, 341, 368, 370, 372, 374). Carries a boundary —
    #     pre-invariant rows are excused and reported by count, and nothing is backfilled
    #     (issue #63, P29).
    if (repo_root / "tests/test_close_row_revision.py").is_file():
        gates_to_run.append([sys.executable, "-m", "pytest", "tests/test_close_row_revision.py"])

    # 30. Score-artifact section gate: the day's score artifact carries every section step 7
    #     requires. The run's own output was the one surface no gate covered, so a
    #     restructure dropped the per-family criterion scorecards while every gate still
    #     read rc=0. Forward-only from 2026-09-20, with the landing day's artifact excused
    #     and never backfilled. The same gate is P7's upholding mechanism: the pacemaker
    #     thinness the run verifies is a required section of that artifact, because cron
    #     state lives in the harness database rather than in the tree, so a gate reading it
    #     would red in every bootstrapped factory (issue #69, P29).
    if (repo_root / "tests/test_score_artifact_sections.py").is_file():
        gates_to_run.append(
            [sys.executable, "-m", "pytest", "tests/test_score_artifact_sections.py"]
        )

    # 31. Duplicate-prose gate: a law file must not state the same prose claim twice.
    #     Two live instances were found in shipped law and no gate read prose structure
    #     at all — the structure gate reads heading numbers, and the profile and template
    #     copies are not paired because they differ by design — so the audit sat rc=0
    #     HEALTHY with the duplication in place. Two arms, because the class took two
    #     shapes and neither arm covers the other: consecutive identical lines are one
    #     block repeating inside itself, which the block arm cannot see, and a repeated
    #     paragraph block is invisible to a line-granular scan (issue #73, P29).
    if (repo_root / "tests/test_duplicate_prose.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_duplicate_prose.py"])

    # 32. Ledger no-shrink gate: a row present in the pushed lineage is never removed by a
    #     lawful path — a retired identity is restored by APPENDING a row naming it, never
    #     by deleting it from the file. Detection, not prevention: a writer that never
    #     calls tools/ledger.py takes no lock and leaves no reflog trace, and once its
    #     shrink is COMMITTED the append guard compares working against committed, goes
    #     self-consistent, and verify reads clean too. So the ARTIFACT is read instead of
    #     the code, and the predicate is a set difference over the #52 identity tuple
    #     (n, ts, event, actor, subject) — a keyword search finds nothing (issue #58,
    #     ruling n=354 clause 4, P11).
    if (repo_root / "tests/test_ledger_no_shrink.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_ledger_no_shrink.py"])

    # 33. Ledger subject-form gate: a subject that APPEARS to name an issue must BE one.
    #     Every subject-keyed predicate in the repo resolves an issue through `^#(\d+)$`,
    #     and `issue_reference()` returns None for anything else — so a near-miss is not
    #     reported as malformed: it is silently reclassified as a DESCRIPTIVE subject and
    #     leaves the population of every one of those predicates without ever being
    #     reported as wrong. Measured at landing over the live ledger: 2 bare-integer rows
    #     (n=516, n=529), both defects, zero false positives on that predicate, and 4
    #     `#`-prefixed clause labels as the false-positive guard the mechanism must leave
    #     alone. Pure and offline — no `gh`, no network, no board lookup, because the
    #     ledger's subject namespace is not bound to this factory's board (n=433 and n=436
    #     cite another repository's issue). Carries a DECLARED boundary read through
    #     tests/ledger_boundary.py: pre-invariant rows print as `excused:` and nothing is
    #     backfilled (issue #80, ruling n=538, P29).
    if (repo_root / "tests/test_subject_form.py").is_file():
        gates_to_run.append([sys.executable, "-m", "pytest", "tests/test_subject_form.py"])

    # 34. Factory-registry drift gate: the registry's declared half is valid, bound and
    #     covered, and its generated half is byte-reproducible. The registry is the fleet's
    #     self-description surface — a peer reads it to learn which topic reaches which
    #     factory — so it rots in two directions and each has its own failure mode: a
    #     fragment that stops validating, a lane whose declared thread_id no longer
    #     resolves to a live binding, a factory group the fleet knows that nobody enrolled,
    #     and a committed render that no longer equals a fresh one over its state-bearing
    #     bytes. The render comparison renders the fresh side at the COMMITTED artifact's
    #     own instant and substitutes that literal stamp for RESOLVED_SENTINEL on both
    #     sides, so a moved binding or a hand-edit fails while a fresh timestamp does not;
    #     the sentinel is declared in the renderer precisely so the two cannot disagree
    #     about it. `resolved_at` is gated separately on its own terms (present, parseable,
    #     not in the future, agreed by both artifacts) so the normalization can never
    #     smuggle an absent timestamp past the comparison. Checks 2, 3 and 5 read live
    #     state — session bindings and the DECLARED factory set — which is why the file was
    #     once classified in gate_registry.OPTIONAL_GATES: it hardcoded this box's six
    #     factories, so a bootstrapped factory would have RED-ed on coverage before it had
    #     enrolled anything. That is fixed, not deferred: the fleet is declared in
    #     `registry/fleet.json`, the probe pair is taken from the manifest in order, and the
    #     gate now runs REQUIRED in a bootstrapped factory against that factory's own fleet
    #     (P29 — the rule is upheld by a gate that can pass where it is copied).
    if (repo_root / "tests/test_registry.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_registry.py"])

    # 35. Patrol host-state gate: the board-intake predicate is fed LIVE host state, so its
    #     forward leg examines a real open set instead of zero. The predicate itself
    #     (tests/test_board_intake_recorded.py) is pure and offline by necessity — a repo
    #     gate cannot call `gh` — so its live test passes an EMPTY board, and a forward leg
    #     that examines 0 open issues reports the same green as one that passes.
    #     tools/patrol_host_state.py is part (b), the host-side runner the predicate's own
    #     docstring defers: it reads the board WHOLE (the reverse leg is sound only over the
    #     full board), feeds it to board_intake_problems(complete_board=True), and prints
    #     each leg's own coverage count so "clean" and "not examined" are never the same
    #     output. A board that could not be read exits 2 and emits NO verdict — a broken
    #     read rendering as a clean patrol is the one failure mode a patrol cannot survive.
    #     This gate is OFFLINE: every probe injects a synthetic board, so the audit itself
    #     never calls `gh` (issue #95, ruling n=580 PART 2).
    if (repo_root / "tests/test_patrol_host_state.py").is_file():
        gates_to_run.append([sys.executable, "-m", "pytest", "tests/test_patrol_host_state.py"])

    # 36. Rework relative-revision gate: an attribution names an ABSOLUTE sha, never a
    #     moving-HEAD-relative form. The receipt rule above (gate 29) governs RECEIPTS,
    #     which is a claim a lane writes down; this governs INVESTIGATION, which a probe
    #     that writes no receipt never reaches. `HEAD~1` means *the parent of whatever HEAD
    #     is when the probe runs*, so in a shared worktree where other lanes commit
    #     concurrently the revision it resolves is not the revision the author meant — and
    #     the verdict is wrong in the direction that EXONERATES the change under
    #     investigation. Measured at landing (2026-09-19, issue #86, ruling n=558): a
    #     stash-then-checkout probe ran a gate at `HEAD~1` and read a docs/ drift as
    #     PRE-EXISTING because a peer lane's commit landed between the stash and the
    #     checkout. The durable trace of an investigation is evidence/rework.md, so the
    #     predicate reads THAT log: the probe is transient, its record is not. It is a
    #     REVISION-CITATION predicate, never a bare tilde match — the live log carries 4
    #     tildes and 7 carets and only 6 sit in a citation, the rest being a
    #     home-directory path and four regex anchors, so a character match would red the
    #     audit on its first run while reporting nothing true. Exemptions are factory data
    #     in docs/rework-relative-revision-exemptions.json, and the gate prints its
    #     population on every run so a clean run and an unexamined one are never the same
    #     output (issue #86, ruling n=558, P29).
    if (repo_root / "tests/test_rework_relative_revision.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_rework_relative_revision.py"])

    # 37. Close-leg pre-flight gate: `append --event close` refuses a close whose subject
    #     has no preceding intake and claim, so the sequence defect is named at the WRITE
    #     PATH instead of being discovered in history after the board is already closed.
    #     ONE predicate, TWO call sites: `verify` asks it about every close row it reads,
    #     `append` asks it about the row it is about to write, with `index = len(rows)`,
    #     the line that row will occupy. Measured twice before it existed — `#50` at n=304
    #     and `#86` at n=589, the second time with the invalid row sitting uncommitted in
    #     the SHARED tree, where the next lane to stage the ledger would have carried it
    #     into history with no act of its own. The refusal carries NO exemption surface
    #     and needs none: a close appended now can never predate the gate. §11's guarantee
    #     is one append path, not tamper-proof, so the order leg and any row written
    #     AROUND the path stay `verify`'s — both are probed here (issue #98, ruling n=596,
    #     P29).
    if (repo_root / "tests/test_ledger_close_preflight.py").is_file():
        gates_to_run.append([sys.executable, "-m", "pytest", "tests/test_ledger_close_preflight.py"])

    # 38. Telemetry-reader registry gate: a telemetry field read out of a row's `detail`
    #     must go through the shared predicate in `tools/field_predicate.py`, because a
    #     free-prose `detail` QUOTES trailers as evidence and a private scan takes a
    #     quotation for a measurement — `n=586` over-reported cost 16x by aggregating
    #     `n=303`'s quoted trailer. Four call sites were repaired one at a time before the
    #     CLASS was seen (#88, n=405 clause 5), and the class moves to the next module
    #     after each repair, so the mechanism is a registry rather than a fifth repair.
    #     The predicate is AST-shaped, never a substring scan: `telemetry.py` CONSTRUCTS
    #     the tokens (a declared writer, allow-listed and printed every run) and
    #     `patrol_host_state.py` carries the word `turns` inside "re-turns" — a blunt scan
    #     reported both and would have needed a permanent exemption for a non-defect.
    #     Measured: 14 modules in the live tree, 0 private readers (issue #99, ruling
    #     n=599, P29).
    if (repo_root / "tests/test_telemetry_reader_registry.py").is_file():
        gates_to_run.append([sys.executable, "-m", "pytest", "tests/test_telemetry_reader_registry.py"])

    # 39. Commit-pair hook gate: the refusal point for a one-sided byte pair (#92, ruled
    #     at n=630). `tests/test_template_sync.py` has always caught the class, but only
    #     AFTER the commit lands — it recurred (#80, then c3b60d5) with a red on `main`
    #     until the next audit. `tools/hooks/pre-commit` refuses it at the only moment it
    #     is refusable, and it reads the INDEX rather than the working tree: a hook that
    #     read the working tree would PASS a commit that staged one side and fixed the
    #     other side on disk without staging it, i.e. a green light on the exact defect
    #     it exists to catch, which is worse than no hook at all.
    #     This gate is the offline half, because an uninstalled hook is SILENT and so
    #     absence must be RED rather than an advisory. Its installation predicate is
    #     SHARED with gate 20's hook through `tests/hook_installation.py` — one
    #     predicate, two call sites, since two implementations of one predicate drift.
    #     The hook's pair table IS `PAIRS` in `tests/test_template_sync.py`, loaded
    #     rather than copied and asserted BEHAVIOURALLY, because a lookalike table under
    #     the same name would satisfy a textual probe (P29).
    if (repo_root / "tests/test_commit_pair_hook.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_commit_pair_hook.py"])

    # 40. Registry-render gate: the renderer's own rules — dedupe, freshness and render
    #     determinism — asserted over SYNTHETIC contexts, so the suite is hermetic and
    #     offline. It was written as `#102`'s prevention and `evidence/rework.md` names it
    #     in that entry's Prevented-by cell, yet NO RUNNER RAN IT until issue #107 (ruling
    #     n=639): its only executions in this factory's history were manual, inside the
    #     closing-turn prose of two close rows. A gate that never runs is
    #     indistinguishable from a gate that passes, and because the file is byte-paired
    #     into TEMPLATE the false prevention shipped to every factory.
    #     THE FORM IS PYTEST, AND THAT IS NOT A STYLE CHOICE. The file defines `def test_*`
    #     at module level and has NO `__main__` block, so `python3 tests/test_registry_render.py`
    #     binds 29 test functions and EXECUTES NONE — it exits 0 with empty output. The
    #     script form would therefore register a gate that prints PASS while running
    #     nothing, which is the exact class this registration exists to close. Measured
    #     both ways at landing: script form rc=0 with no output, pytest form 29 passed.
    #     `tests/gate_registry.py` direction 4 now asserts this pairing mechanically, so
    #     the form cannot silently regress.
    if (repo_root / "tests/test_registry_render.py").is_file():
        gates_to_run.append([sys.executable, "-m", "pytest", "tests/test_registry_render.py"])

    # 41. Rework declared-to-landed gate: a close row's canonical trailer declares the
    #     rework entry it PRODUCED, and a declaration naming an entry that never landed is
    #     a claim nothing checked — the row then reads as evidence of a lesson recorded
    #     while the log carries no such entry. BOTH sides go through the shared predicates,
    #     never a private parse: the declaration through `tools/field_predicate.py`
    #     (`trailer_tokens` over the canonical run, then `keyed_value(token, "rework")` per
    #     token — `rework` is not a TELEMETRY_KEY, and `keyed_value` takes ONE token, so the
    #     list is iterated), the landed entries through `tests/rework_table.py`
    #     (`column_cells(text, "Entries", "Subject")` — read by NAME, because a positional
    #     read is silently wrong the moment a column moves, which is the live defect
    #     `tools/audit.py::parse_rework` still carries).
    #     THE BOUND, stated so the gate is not oversold: the property is EXISTENCE of the
    #     named entry, never TRUTH of the production claim. n=633 declares `rework=#102` and
    #     that token is FALSE — the close RESOLVED entry #102 and produced none, retired by
    #     name at n=642 — but #102 EXISTS, so the gate passes n=633 CORRECTLY on its own
    #     narrow property. No retirement surface is owed and none is built: `rework=#N` is
    #     not a sha, so it never enters `docs/ledger-retirements.json`'s population of
    #     shape-valid `head=` tokens, and an entry for it would match nothing (n=642).
    #     LOUD-FAIL-ON-ZERO, and this gate is that kind: its population is the WHOLE
    #     history, so an empty read means the parse broke, never that the factory is young.
    #     The forward-only sibling (#112) is the opposite case and must not copy this guard.
    #     No exemption surface: a declaration written now can never predate the gate, and
    #     history was measured clean at landing — 7 declarations in scope, all resolved
    #     (issue #110, ruling n=642, P29).
    if (repo_root / "tests/test_rework_declared_landed.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_rework_declared_landed.py"])

    # 42. Reconstructed-claim gate: a `claim` row stamped AFTER the work it accepts must
    #     DECLARE itself (the token `claim=reconstructed`) and name the BASIS it rests on
    #     under the canonical marker `BASIS:`. That is the whole predicate, and it is
    #     deliberately narrow: it is the author-controlled half, which is the only half a
    #     gate may judge.
    #     WHAT IT REPLACED, AND WHY (#115, ruling n=687): it used to require the row to
    #     declare the interval between its own `ts` and its close row's `ts` as the token
    #     `claim_gap`, and it compared that declaration against a recomputation. That
    #     requirement is WITHDRAWN for the reason the law already carried one paragraph
    #     down — a gate must test a property its author controls. The author controls the
    #     ACT of declaring, never the interval: the claim's `ts` is one of the five
    #     `ROW_IDENTITY` fields, while the close row's `ts` is assigned by
    #     `tools/ledger.py` under the append lock after `extract_task_telemetry` has run
    #     (~17-19s measured on this host), so the declared value was never the author's to
    #     compute. A gate over it would have compared the tool's own arithmetic against the
    #     rows that arithmetic was computed from — a check that cannot fail. Two
    #     alternatives were ruled out with it: having the TOOL write the token on the close
    #     row (same cannot-fail shape), and an atomic claim+close append (structurally zero
    #     interval, at the cost of a second append path).
    #     THE INTERVAL MOVES FROM DECLARED TO RECOMPUTED-AND-PRINTED. This gate recomputes
    #     it from the two rows' own `ts` values — tool-sourced on BOTH sides, no typed
    #     expectation — and PRINTS it beside each row it examines. It is REPORTED, never
    #     judged. `tools/ledger.py verify` prints it too, because the amended law asserts
    #     that it is printed and a law with no mechanism reading it is the dead-text class
    #     P29 forbids. The close row is resolved by SUBJECT with the row number as the
    #     tie-break — never by adjacency, because a claim's neighbour is a property of the
    #     file's order rather than of the work unit — and a work unit with no close row yet
    #     prints `no close row yet` rather than failing, because a lane reconstructing its
    #     claim mid-work has not closed yet and the gate must not fail a state the work has
    #     not reached.
    #     THE POPULATION IS DOUBLY SCOPED: `event == "claim"` AND the row declares
    #     `claim=reconstructed`. Both halves are load-bearing — the lexical scan finds rows
    #     that merely QUOTE the token (a ruling that states the token it defines, a run that
    #     quotes it, a close that quotes the claim it closes) and the event scope is what
    #     keeps them out (`n=602`). The BASIS marker is read over the WHOLE detail rather
    #     than positionally, and the head/trailer question cannot arise for it:
    #     `trailer_tokens` collects only tokens carrying `=`, so a colon-bearing marker can
    #     never be part of the canonical run. Two scoping questions, two predicates.
    #     THE MARKER IS MANDATED FORWARD ONLY. Measured before the gate was written: `n=647`
    #     is an honest reconstruction that names its basis in prose WITHOUT the marker, while
    #     five of the six historical reconstructions carry it — so a retroactive marker gate
    #     would have fired on an honest row, the defect class rework entry 157 records.
    #     ⚠️ FORWARD-ONLY — AND THIS GATE MUST NOT COPY BLOCK 41'S LOUD-FAIL-ON-ZERO GUARD,
    #     which is the contrast block 41 already names in its own comment. Its live
    #     population is legitimately EMPTY until the next reconstruction, so an empty read is
    #     the EXPECTED state rather than a broken parse; it takes the PROPORTIONAL guard
    #     instead (`tests/ledger_boundary.py::population_skip_reason`), which SKIPS with a
    #     stated reason and never passes silently. The boundary is a DECLARED FACTORY
    #     PARAMETER (`docs/ledger-invariants.json`, key `reconstructed_claim_declared`): all
    #     six historical reconstructions are OUTSIDE the population and print as `excused:`
    #     on every run, because NOTHING IS BACKFILLED. Its population is printed on every
    #     run, so a clean run and a run that examined nothing are never the same output
    #     (issue #112 ruling n=657, amended under issue #115 ruling n=687, P29).
    if (repo_root / "tests/test_reconstructed_claim_declared.py").is_file():
        gates_to_run.append([sys.executable, "-m", "pytest", "tests/test_reconstructed_claim_declared.py"])

    # 43. The skill-version contract (issue #71, ruling n=455 clause 3, P29). A commit that
    #     moves a LAW FILE's body must move the skill's `version:` line in the SAME commit,
    #     because `oc-drift-check` reads that line and a version-keyed staleness check reading
    #     a field that does not move reports "no drift" for a law that changed. Measured at
    #     n=455: of the 36 commits touching the law file, 32 changed the law body without
    #     moving the version — the decoupling is the norm, not an edge case.
    #
    #     Its population is COMMITS, not rows, so it reads a git history rather than the
    #     ledger, and it DISCOVERS the law file (`git ls-files` matched against the skill
    #     globs) instead of hardcoding the slug — that discovery leg is what lets it ship in
    #     the template and judge a bootstrapped factory's own skill.
    #
    #     Forward-only by construction: the boundary is a DECLARED FACTORY PARAMETER
    #     (`docs/ledger-invariants.json`, key `skill_version_contract`), commits before it are
    #     OUTSIDE the population, and NOTHING IS BACKFILLED — a commit cannot be repaired
    #     after the fact, so grandfathering is the only honest option and it is stated rather
    #     than implied. An absent key SKIPS with a stated reason; a key that is present but
    #     unreadable FAILS, because an unreadable declaration is not an absent one.
    #
    #     The loud-fail-on-zero form would be the WRONG guard here: this gate's population is
    #     legitimately EMPTY until the next law commit, so an empty window is a STATED SKIP
    #     and never a silent pass. The gate PRINTS the population it examined on every run —
    #     the boundary, the law files it discovered, and the commit count — so a clean run and
    #     a run that examined nothing are never the same output. Its non-vacuity is shown by a
    #     PROBE instead: the test file builds synthetic git histories (the repo's first) and
    #     proves the gate BITES on a body-only change and passes when the version moves.
    if (repo_root / "tests/test_skill_version_contract.py").is_file():
        gates_to_run.append([sys.executable, "-m", "pytest", "tests/test_skill_version_contract.py"])

    # 44. Cron-thinness gate (issue #54, P7 + P28). A pacemaker cron exists to WAKE the
    #     session that owns a periodic process; the substantive work runs there, under the
    #     current law. P7 and P28 both state that, and until #54 neither had a mechanism:
    #     P7 was mapped to `tools/hygiene.py`, which declares its own scope as P20 and
    #     never reads a cron row, and P28's mapped targets carried no cron reference
    #     either. `tests/test_law_coverage.py` asserts only that a mapped target EXISTS,
    #     so a file that exists and implements nothing passed both — the hole #50 lived
    #     in, where a live and unbounded P7 violation was found by a lane reading a cron
    #     row by hand because no gate could see it.
    #
    #     The predicate is PURE over a LIST of cron rows, and it must stay so: the rows
    #     live in the harness `cron_jobs` table while the mechanical suite runs offline
    #     against a tree, so a gate that read that table would RED in every bootstrapped
    #     factory that has no such table (the failure #68 measured). It reads BOTH
    #     `deliver_to` and the prompt, because the meta-factory's own correctly-thin
    #     pacemaker carries its wake IN THE PROMPT with `deliver_to` NULL — a
    #     `deliver_to`-only predicate flags a healthy factory — and "thin" is not a byte
    #     count either: a 1326-byte prompt running one notify command is thin, while a
    #     shorter prompt carrying a work order is not. A row it cannot classify is
    #     EXCUSED and PRINTED, never silently clean.
    #
    #     Its population is the CALLER's, and the host-side runner that feeds it live
    #     rows is WIRED (#121, ruling n=739): tools/patrol_host_state.py reads every
    #     OpenCrabs home in place through a mode=ro URI and hands its own factory's
    #     rows to pacemaker_problems. This gate's own evidence nevertheless remains
    #     its synthetic probes, because the predicate is PURE over a list and cannot
    #     read live state — not because no caller exists. Those probes pin all three
    #     live shapes and both directions of the byte-count trap.
    if (repo_root / "tests/test_cron_thinness.py").is_file():
        gates_to_run.append([sys.executable, "-m", "pytest", "tests/test_cron_thinness.py"])

    # 45. Close-telemetry provenance gate (issue #130). A close row's five measurement
    #     keys (`cost_usd`, `tokens_in`, `tokens_out`, `turns`, `duration`) have TWO
    #     possible writers: `tools/ledger.py`'s close guard fills them from a window it
    #     MEASURED, and the author may have declared them by hand. Nothing structural
    #     distinguishes the two -- HQ measured all three candidate predicates (POSITION,
    #     COMPLETENESS, VALUE EQUALITY) and each FAILED -- so the row must CARRY its
    #     provenance: exactly one `telemetry=` token in its canonical trailer, one of
    #     `measured` / `typed` / `unavailable`. The guard states it on all three of its
    #     branches, so the predicate is the WRITER'S OWN GUARANTEE and needs no key list.
    #
    #     The population is EVERY post-boundary close row, not only those declaring a
    #     measurement: the narrower predicate is strictly WEAKER, because a row whose
    #     guard never ran at all declares no measurement to hang provenance on. The gate
    #     PRINTS the population it examined (P29) and reports a stated SKIP -- never a
    #     silent pass -- when that population is empty or the boundary is undeclared.
    #
    #     The boundary is a DECLARED FACTORY PARAMETER read from
    #     `docs/ledger-invariants.json`, never a date hardcoded here: this gate file is
    #     paired byte-identically into `TEMPLATE/tests/`, and a baked-in date would RED
    #     in the tree it ships to (#76's class, P35). It is FORWARD-ONLY: the rows
    #     written before the guard landed -- including #130's own hand-typed class,
    #     `n=368`/`n=372`/`n=374` -- print as `excused:` on every run and are never
    #     backfilled, because a value reconstructed after the fact is a falsified record
    #     rather than a repair.
    if (repo_root / "tests/test_close_telemetry_provenance.py").is_file():
        gates_to_run.append([sys.executable, "-m", "pytest", "tests/test_close_telemetry_provenance.py"])

    # 46. Insights-gate verdict gate (issue #46). Process 3 declares TWO artifacts as its
    #     output contract -- `evidence/scores/<date>.md` AND `evidence/insights.jsonl` --
    #     and the score file got its closing invariant under #32 while the insights half
    #     got none. So on 2026-09-18 the synthesis run appended insight #22, wrote its own
    #     `run` row carrying `audit=DEGRADED-hygiene-modified-tracked-files`, reported
    #     anyway, and ended with the artifact uncommitted for over two hours: it RECORDED
    #     the dirty tree instead of clearing it. This gate is #32's rule one artifact over,
    #     and it reads the same two tokens rather than minting a vocabulary of its own --
    #     `workspace_gate=rc=0`, the closing workspace verdict, and `head=<sha>`, the HEAD
    #     the run committed at. Tokens are read through the SHARED
    #     `tools/field_predicate.py::keyed_value`, never a substring test, because a row
    #     that merely NAMES a field is not a row that declares it.
    #
    #     The population is an ACT scoped TWICE -- `event == "run"` AND
    #     `subject == "weekly-insight-synthesis-pacemaker"` -- because the ledger carries
    #     other `run` rows under other subjects, and a predicate on `event` alone would
    #     govern them. The subject is a LANE-LOCAL string, not a schema name, so a factory
    #     that names its pacemaker differently edits that one constant in its own copy.
    #     The gate PRINTS the population it examined (P29) and reports a stated SKIP --
    #     never a silent pass -- when that population is empty or the boundary is
    #     undeclared.
    #
    #     The boundary is a DECLARED FACTORY PARAMETER read from
    #     `docs/ledger-invariants.json`, never a date hardcoded here: this gate file is
    #     paired byte-identically into `TEMPLATE/tests/`, and a baked-in date would RED in
    #     the tree it ships to, or pass it vacuously (#76's class, P35). It is FORWARD-ONLY:
    #     rows written before the boundary -- including the run row that motivated it --
    #     print as `excused:` on every run and are never backfilled, because a verdict
    #     written today for a run that predates the rule would be a falsified record rather
    #     than a repair.
    if (repo_root / "tests/test_insights_gate_recorded.py").is_file():
        gates_to_run.append([sys.executable, "-m", "pytest", "tests/test_insights_gate_recorded.py"])

    # 47. Binding-mechanism-existence gate (issue #74, ruling n=485). §11 of the law gives the
    #     durable ledger exactly one writer, `tools/ledger.py append`, and a law clause now
    #     states that an ad-hoc probe, scratch script or throwaway harness must never append to
    #     live state. The REQUIREMENT is product-neutral and lives in the core law; the
    #     product-specific MECHANIC — which variables redirect which append path, and the
    #     incantation that uses them — lives in `docs/methodology/04-harness-binding.md` §10.
    #     A binding that names a redirect the tool no longer reads is a law naming a mechanism
    #     that does not exist, and nothing checked that: the defect was found by a lane that had
    #     been told the seam existed and watched it not work (#48's class), so this gate reads
    #     the variable names OUT OF THE BINDING DOCUMENT and probes the tool for each one.
    #
    #     The predicate is BEHAVIOUR, never a string match, and the population is derived from
    #     the document rather than from a second list kept beside it — a list would be free to
    #     drift from the doc the law points readers at. Each named variable is pinned at a
    #     throwaway path, an append is run, and the gate asserts the row landed THERE and that
    #     the tool's own default path was NOT created; `OC_ACTORS_PATH` is probed in both
    #     directions (a declared lane ACCEPTED, an absent file REFUSED), because acceptance
    #     alone would not distinguish the override from the repo's live vocabulary still being
    #     read. The third probe asserts the gate's own hermeticity: no marker row reached the
    #     live ledger. A ledger that moved WITHOUT the marker is printed as consistent with a
    #     concurrent lawful append, never as a leak — a peer lane's honest write must not turn
    #     this gate RED.
    #
    #     Forward-only by construction: the gate reads the two artifacts as they stand, so there
    #     is no boundary to declare and nothing to grandfather. Its non-vacuity is shown by
    #     construction rather than by a probe over history — it asserts the binding named at
    #     least one variable, so a table it could not parse FAILS loudly instead of passing over
    #     an empty population (P29). It is byte-paired with a TEMPLATE twin, so the manifest
    #     grain is what keeps a factory from dropping the runner and keeping the file.
    if (repo_root / "tests/test_binding_mechanism_exists.py").is_file():
        gates_to_run.append([sys.executable, "-m", "pytest", "tests/test_binding_mechanism_exists.py"])

    # 48. Brain-metrics gate: the standing-reading instrument measures what it says.
    #     Registered because a gate that never runs is indistinguishable from a gate that
    #     passes (#59's class, P29): `docs/measurement-procedure.md` §5 declares the
    #     brain-metrics COMPANION readings as a standing obligation every factory owes, and
    #     this is the file that proves the mechanism behind them exists and behaves. Its run
    #     is FIXTURE-DRIVEN and offline by construction -- the live figures are properties of
    #     an INSTANT, never of a revision (leg A's files are in no repository, so a revision
    #     stamp pins nothing about them: measured 09-19 -> 09-21, leg A moved +82 lines and
    #     419 B inside a single turn's window), so this gate asserts the ARITHMETIC against
    #     fixtures and the instrument REPORTS freshness. A criterion pinned to a live figure
    #     would fail a correct instrument. (The number above is 48, not 47: the two entries
    #     preceding this one both read `# 47.` -- noted rather than renumbered, because
    #     renumbering a peer's entry inside a commit about this gate would bury the fix.)
    if (repo_root / "tests/test_brain_metrics.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_brain_metrics.py"])

    # 49. In-flight guard gate: two audit runs contending for one cgroup is real load —
    #     17 cron jobs fired inside a 19-second window on 2026-09-22 after the scheduler
    #     starvation filed as opencrabs#504, and the pile included audits from MORE THAN
    #     ONE repository. The contended unit is the RUN, not the gate: the loop below is
    #     sequential, so a run can never overlap itself. A second run now refuses on its
    #     own exit code (3, distinct from the gate-failure 1 and the budget-manifest 2),
    #     prints a named stderr line, and writes NO run row — `OUTCOME_DOMAIN` is a closed
    #     four-token set, so a refused row would either red a gate or let a run that did no
    #     work grade the yield it never measured.
    #     THE EXEMPTION UNDER `--no-gates` IS LOAD-BEARING, and this registration is why:
    #     `tests/test_audit_rates.py` is itself a registered gate that runs
    #     `audit.py --json --no-gates` and asserts rc==0, so a NAIVE whole-run guard makes
    #     the outer run hold the lock while its own gate's nested run refuses, and that gate
    #     reds. The gate below drives BOTH directions — a guard that is absent fails the
    #     refusal probe, and a guard that is too wide fails the recursion probe.
    #     The second half is the ORPHAN PROPERTY: no process in a run's tree outlives the
    #     run. The lock cannot close it (a dead holder releases the lock, so the lock never
    #     sees an orphan), so `PR_SET_PDEATHSIG` is set in the gate child before exec and
    #     the gate proves it against a CONTROL arm.
    #     THE BOUND, stated so the guard is not oversold: a per-repo lock cannot bound the
    #     ops cgroup, which is shared ACROSS repositories — at least three other repos run
    #     this same template audit inside it, each with its own lock. (issue #145, ruling
    #     n=940, P29).
    if (repo_root / "tests/test_audit_inflight_guard.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_audit_inflight_guard.py"])

    # 50. Commit-session-trailer gate (issue #138, ruled at ledger n=928; plan 2646d31a
    #     step 6). The commit-msg hook now APPENDS a `Session-Id:` trailer carrying
    #     `OPENCRABS_SESSION_ID`, because a commit in this repo could previously not be
    #     attributed to a lane at all: measured, 0 of the last 200 commits carried the
    #     trailer and every one carried a shared author identity, so on 2026-09-21 two
    #     lanes chased the wrong culprit over a commit that named nobody.
    #     The trailer is a TOOL-written field, not a rewrite of the author's text --
    #     the same act as the ledger's own `ts` and `n`, which no author supplies --
    #     and it is written only AFTER the subject passes the citation clause, so a
    #     REFUSED commit is never stamped.
    #     THE LIMIT THIS GATE CANNOT CROSS, stated because it is the whole reason the
    #     probe is built the way it is: it can prove the MECHANISM (driven directly,
    #     with a synthetic message and session, both directions plus the refusal), and
    #     it cannot prove a historical commit carries a trailer, because the hook was
    #     installed late and history is not rewritten. A live-state population belongs
    #     to a patrol leg, never to a gate over history.
    #     It drives the hook DIRECTLY rather than making a real commit: the hook
    #     resolves its predicate through `git rev-parse --show-toplevel`, so a
    #     throwaway repository would have to carry this repo's whole gate file -- a
    #     fixture testing a fixture. Direct invocation tests the code git runs.
    if (repo_root / "tests/test_commit_session_trailer.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_commit_session_trailer.py"])

    # 51. Ledger-identity gate (issue #138, ruled at ledger n=928; plan 2646d31a step 8).
    #     The ledger's `actor` is DERIVED from `OPENCRABS_SESSION_ID` and the per-event
    #     authorization matrix is enforced at the write path, because identity was
    #     previously whatever a lane typed into `--actor` and was checked for membership
    #     only -- measured: three `intake` rows in one member factory carried
    #     `actor=worker`, and `intake` is Triage's, so the write path accepted every one
    #     and the schema gate reported them a day later.
    #     EVERY ARM RUNS IN A STAGED TREE, and the reason is structural: the strict branch
    #     (derivation, agreement, matrix) is reachable ONLY when `OC_LEDGER_PATH` is
    #     absent, and with it absent the tool's target is its own `REPO/evidence/ledger.jsonl`.
    #     So the strict path cannot be exercised against a redirected ledger by
    #     construction -- either the redirect is set and the fixture branch runs, or it is
    #     absent and the write goes to the live ledger. `gate_fixtures.stage_tool` builds
    #     the only tree where the live path is a temp file. This was found by writing the
    #     arms the wrong way first: the contradiction arm through `OC_LEDGER_PATH` returned
    #     rc=0, and the cause was the PROBE, not the tool.
    #     It SKIPS WITH A STATED REASON when the lane resolver cannot be read, which is
    #     what a bootstrapped factory with no fleet manifest looks like.
    if (repo_root / "tests/test_ledger_identity.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_ledger_identity.py"])

    # 52. Kit-manifest gate (plan 2646d31a step 9). `registry/kit.json` is the reference the
    #     cross-factory drift leg measures against, and it is GENERATED from `TEMPLATE/` rather
    #     than hand-kept -- because a hand-kept list of shipped files is a second copy of the
    #     tree that goes stale silently, which is the class this factory has ruled against
    #     repeatedly. The gate proves the manifest AGREES with the tree AND, by mutation on a
    #     copy, that the check REJECTS a drifted, a deleted and an unlisted file, each named:
    #     `--check` returning 0 is exactly what a vacuous implementation would print, so the
    #     mutation arms are what make the agreement arm mean anything.
    #     Its population is `TEMPLATE/`, so a bootstrapped factory has no such tree and the
    #     gate SKIPS WITH ITS REASON rather than passing silently.
    if (repo_root / "tests/test_kit_manifest.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_kit_manifest.py"])

    # 53. Synthesizer unit gate: the tool's own behaviour, including the two non-vacuity
    #     proofs its #166 and #168 closes owe. The classifier's key must match the WORD and
    #     never a word that CONTAINS it -- `lock` matched `block` and `clock`, `race` matched
    #     `trace`/`traceback`/`brace`, and because the chain is `elif` each such entry was
    #     DIVERTED from its true bucket and never reached it. The dedup guard must read the
    #     PERSISTED file, not the list it just built in the same call, which was a tautology
    #     that could never fire. Both probes are FIXTURE-driven, because on the live tree
    #     every id is already persisted and both predicates return the same empty answer --
    #     the arms would be indistinguishable and the gate would pass vacuously.
    #     It is DECLARED HERE rather than left to a by-hand `pytest` run because a probe the
    #     audit never runs is dead text: the two items above closed on non-vacuity that
    #     nothing would have executed. Registered as OPTIONAL, not REQUIRED -- its subject
    #     tool `tools/synthesize_insights.py` is meta-factory-only and does not ship, which
    #     is the same reason `tests/test_synthesize_interface.py` sits in OPTIONAL_GATES.
    if (repo_root / "tests/test_synthesize_insights.py").is_file():
        gates_to_run.append([sys.executable, "-m", "pytest", "tests/test_synthesize_insights.py"])

    # 54. Attestation-dispatch gate: the registry clock's OWN logic, which shipped to every
    #     factory with no gate of any kind. `tools/registry_attest.py` is installed by
    #     BOOTSTRAP step 4d, wakes every factory HQ with the three attestation questions, and
    #     until issue #162's parent work measured it carried ZERO gates -- no gate named for
    #     it, and no gate importing it (n=1130). That is the exact hole this project was
    #     opened to close: an instrument that reads as ADOPTED because the file is present,
    #     while nothing exercises what it promises. The brief it sends is the declared half's
    #     whole anti-rot surface, so a silent drop of one question is invisible from the send
    #     side -- the send still succeeds.
    #     WHAT IT PROBES that the resolver's own gate cannot: `test_registry.py` covers
    #     `resolve_lane`. Under test here is the dispatcher layered ON TOP -- fail-open (one
    #     malformed fragment must not silence the fleet's clock), ambiguity refusal (two lanes
    #     claiming `hq` must never silently pick one), and the brief's three questions
    #     surviving `format`. The fail-open arm is ordering-robust ON PURPOSE: a resolvable
    #     fragment sits AFTER each problem branch, because the first version placed it last
    #     and so passed on an early `return` that lost nothing downstream -- decorative, caught
    #     only by running the mutation control. All five mutants are caught by their intended
    #     arm.
    #     THE FORM IS PYTEST, AND THAT IS NOT A STYLE CHOICE. The file defines `def test_*` at
    #     module level with NO `__main__` block, so `python3 tests/test_registry_attest.py`
    #     binds its 9 test functions and EXECUTES NONE -- it exits 0 with empty output, which
    #     is the class this registration exists to close. `tests/gate_registry.py` direction 4
    #     asserts the pairing mechanically.
    #     REQUIRED, not OPTIONAL: the file is byte-paired into TEMPLATE and shipped by step 4d,
    #     so a manifest that omitted it would let a factory drop the runner and keep the file
    #     (issue #107, ruling n=639).
    if (repo_root / "tests/test_registry_attest.py").is_file():
        gates_to_run.append([sys.executable, "-m", "pytest", "tests/test_registry_attest.py"])

    # 55. Kit-delivery gate (plan 2646d31a step 7). The kit could TELL a factory it had drifted
    #     and had no mechanism to hand it the update: the law corpus carried `vendor` 0,
    #     `re-sync` 0, `propagat` 0-1, and `registry/kit.json` is a manifest, not a channel.
    #     `tools/kit_deliver.py` is that transport, and this gate is its evidence -- a
    #     transport that ships without a gate is a mechanism whose only proof is its author's
    #     word.
    #     WHAT IT PROVES: a factory at an older kit state RECEIVES the update; its OWN gate is
    #     green after, with a NEGATIVE CONTROL showing that same gate reds on the state a
    #     non-atomic update would leave (bytes moved, pin not) -- so "green after" is measured
    #     rather than a property the gate could never fail; its `factory`-class declarations
    #     and its own data are BYTE-UNCHANGED by digest; a local fork is SKIPPED, not
    #     overwritten; and `--dry-run` writes nothing.
    #     IT IS NOT A KIT FILE, and that is why it is OPTIONAL rather than REQUIRED: a member
    #     delivers to nobody, so the transport must not ship. Same grain as gate 52.
    if (repo_root / "tests/test_kit_deliver.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_kit_deliver.py"])

    # 56. Member-side pin gate (plan 2646d31a step 8). The SELF-JUDGEMENT half of drift:
    #     gate 52 measures what every member has ported (ours), while this one lets a factory
    #     judge ITSELF against the pin IT vendored — so a member's verdict moves only when its
    #     own tree diverges from its own declaration, never when we move. A gate against OUR
    #     live manifest would make a member's audit a function of our working tree and our
    #     backlog, which is the coupling the vendored pin exists to remove.
    #     IT JUDGES THREE POPULATIONS AND PRINTS ALL THREE, because each is an exclusion a
    #     reader must be able to see: ABSENT paths are the population filter (a factory ports
    #     a SUBSET, so reddening on those would punish the behaviour the port rule asks for);
    #     `factory`-class paths are excluded BY CLASS, since those are seeds the factory owns
    #     and its copy legitimately differs; the rest are judged byte-for-byte.
    #     BUILDING IT EXPOSED A DEFECT IN THE PREDICATE IT CALLS. `undeclared_divergence`
    #     compared `factory`-class paths byte-for-byte while the class doc says such a file
    #     "is never compared byte-for-byte, because the factory's copy legitimately differs" —
    #     and `TEMPLATE/README.md` maps to `README.md`, so EVERY factory would have been
    #     reported as diverging on its own README. Both were fixed in this change, and the
    #     arm that keeps it from regressing asserts the fixture's differing README is green
    #     BECAUSE it was excluded, not merely that a count is printed.
    #     REQUIRED, not OPTIONAL: the file is byte-paired into TEMPLATE, so a manifest that
    #     omitted it would let a factory drop the runner and keep the file (issue #107).
    if (repo_root / "tests/test_kit_pin.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_kit_pin.py"])

    # The budgets are read ONCE for the whole suite and resolved PER GATE. A gate
    # with no manifest entry is NOT an error -- it runs on the declared default, and
    # `budget_source` is what lets the audit PRINT which gates used it: a declared
    # default with a printed population is not an exempt-by-silence surface, while
    # an unprinted fallback is (#94, ruling n=744). A manifest that EXISTS and
    # cannot be read does NOT fall back -- it raises, because defaulting over an
    # unreadable budget set would silently re-cap every gate in the tree.
    budgets = load_gate_budgets()

    results = []
    for cmd in gates_to_run:
        key = gate_key_for_cmd(cmd, repo_root)
        budget_sec, source = budgets.resolve(key)
        result = run_gate(cmd, repo_root, budget_sec)
        result["gate_key"] = key
        result["budget_sec"] = budget_sec
        result["budget_source"] = source
        results.append(result)
    return results, budgets


def check_cadence_integrity(ledger_path: Path) -> dict[str, Any]:
    """Check whether recurring processes ran according to declared schedule."""
    if not ledger_path.is_file():
        return {"cadence_held": False, "hours_since_last_run": None}

    now = datetime.datetime.now(datetime.timezone.utc)
    last_ts = None
    with open(ledger_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    data = json.loads(line)
                    if data.get("event") in ("run", "score"):
                        last_ts = data.get("ts")
                except Exception:
                    pass

    if not last_ts:
        return {"cadence_held": True, "hours_since_last_run": None}

    try:
        t_last = datetime.datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
        hours_diff = (now - t_last).total_seconds() / 3600.0
        # Expected daily cadence: interval <= 30 hours
        cadence_held = hours_diff <= 30.0
        return {
            "cadence_held": cadence_held,
            "hours_since_last_run": round(hours_diff, 1),
            "last_run_ts": last_ts,
        }
    except Exception:
        return {"cadence_held": False, "hours_since_last_run": None}


def format_report_markdown(
    date_str: str,
    ledger_stats: dict[str, Any],
    rework_stats: dict[str, Any],
    cadence_stats: dict[str, Any],
    gate_results: list[dict[str, Any]],
) -> str:
    """Format the full audit into markdown document."""
    all_passed = all(g["passed"] for g in gate_results)
    verdict = "PASSED" if all_passed and cadence_stats.get("cadence_held", True) else "FAILED"

    lines = [
        f"# Operational Process Self-Audit — {date_str}",
        "",
        f"> **Verdict:** `{verdict}` · Process 3 (Internal Self-Audit)",
        "",
        "---",
        "",
        "## 1. Process Health & Delivery Telemetry",
        "",
        "| Metric | Value | Reference / Derivation |",
        "|---|---|---|",
        f"| **Total Ledger Events** | `{ledger_stats.get('total_events', 0)}` | Continuous ledger sequence |",
        f"| **Closed Tasks** | `{ledger_stats.get('closed_tasks', 0)}` | Distinct closed subjects; `{ledger_stats.get('close_events', 0)}` close rows ({ledger_stats.get('close_events', 0) - ledger_stats.get('closed_tasks', 0)} re-close of a re-opened subject) |",
        f"| **First-Pass Yield** | `{format_yield_rate(ledger_stats)}` | {format_yield_note(ledger_stats)} |",
        f"| **Rework Entries** | `{rework_stats.get('total_entries', 0)}` | Defect count recorded in rework.md |",
        f"| **Rework Declarations** | `{ledger_stats.get('close_rows_declaring_rework', 0)}/{ledger_stats.get('close_events', 0)}` ({round(ledger_stats.get('rework_declaration_rate', 0.0) * 100, 1)}%) | Close rows declaring a `rework=#N` or `rework=none` disposition — {format_rework_declaration_note(ledger_stats)} |",
        f"| **Rework Share** | `{round(rework_stats.get('rework_share', 0.0) * 100, 1)}%` | {rework_stats.get('total_entries', 0)} rework entries ÷ ({rework_stats.get('closed_subjects', 0)} closed subjects + {rework_stats.get('total_entries', 0)} rework entries) |",
        f"| **Rework per Close** | `{round(rework_stats.get('rework_per_close', 0.0) * 100, 1)}%` | {rework_stats.get('total_entries', 0)} rework entries ÷ {rework_stats.get('closed_subjects', 0)} closed subjects |",
        f"| **Change Fail Rate** | `{round(rework_stats.get('change_fail_rate', 0.0) * 100, 1)}%` | {rework_stats.get('change_fail_rate_numerator', 0)} closes that produced a rework entry ÷ {rework_stats.get('change_fail_rate_denominator', 0)} closed work units — **linkage coverage `{rework_stats.get('subject_coverage_numerator', 0)}/{rework_stats.get('subject_coverage_denominator', 0)}`** entries carry a determinate Subject ({round(rework_stats.get('subject_coverage', 0.0) * 100, 1)}%); read the rate only against this coverage |",
        f"| **Avg Task Lead Time** | `{ledger_stats.get('avg_lead_time_sec', 0.0)}s` | Mean intake→close duration over {len(ledger_stats.get('lead_times_sec', []))} sampled subjects |",
        f"| **Total Inference Cost** | `${ledger_stats.get('total_cost_usd', 0.0):.4f}` | Tracked cost across ledger task telemetry — summed from each row's canonical TRAILER only, by position and across every event (issue #90) |",
        f"| **Telemetry Outside the Trailer** | `{ledger_stats.get('out_of_trailer_count', 0)}` row(s) | {format_out_of_trailer_note(ledger_stats)} |",
        f"| **Avg Cost / Closed Task** | `${ledger_stats.get('avg_cost_per_closed_task_usd', 0.0):.4f}` | ${ledger_stats.get('total_cost_usd', 0.0):.4f} total cost ÷ {ledger_stats.get('closed_subjects', 0)} distinct closed subjects |",
        f"| **Cost / Successful Task** | `${ledger_stats.get('cost_per_successful_task_usd', 0.0):.4f}` | {format_cost_note(ledger_stats)} |",
        f"| **Total Tokens (In/Out)** | `{ledger_stats.get('total_tokens_in', 0)} / {ledger_stats.get('total_tokens_out', 0)}` | Cumulative prompt and completion tokens |",
        f"| **Cadence Status** | `{'HELD' if cadence_stats.get('cadence_held') else 'MISSED'}` | Last run: {cadence_stats.get('hours_since_last_run')}h ago |",
        "",
        "---",
        "",
        "## 2. Mechanical Gate Verification",
        "",
        "| Gate / Command | Outcome | Duration | Notes |",
        "|---|---|---|---|",
    ]

    for g in gate_results:
        # The same three states as the stdout print, and for a sharper reason: this
        # report is COMMITTED to `evidence/`, so a `FAIL` written here for a gate
        # that merely ran out of budget would be a durable false verdict (#94).
        status = "UNKNOWN" if g.get("unknown") else ("PASS" if g["passed"] else "FAIL")
        # The cause is read through the SAME helper as the stdout report, so the two
        # surfaces cannot disagree about which line states it (one field, one predicate).
        note = (g.get("note") or "").replace("|", "/")
        lines.append(f"| `{g['cmd']}` | `{status}` | `{g['duration_sec']}s` | {note} |")

    lines.extend([
        "",
        "---",
        "",
        "## 3. Calibration Spot-Check (Sampled Task)",
        "",
    ])

    sc = ledger_stats.get("spot_check")
    if sc:
        seq_ok = sc.get("sequence_intact")
        lines.extend([
            f"- **Sampled Subject:** `{sc.get('subject')}`",
            f"- **Intake Recorded:** `{'YES' if sc.get('intake_verified') else 'NO'}`",
            f"- **Claim Lock Recorded:** `{'YES' if sc.get('claim_verified') else 'NO'}`",
            f"- **Close Verified:** `{'YES' if sc.get('close_verified') else 'NO'}`",
            f"- **Sequence Integrity:** `{'VERIFIED' if seq_ok else 'BROKEN'}`",
        ])
    else:
        lines.append("*No closed tasks available to spot-check.*")

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Operational process audit runner.")
    parser.add_argument("--json", action="store_true", help="Output JSON results to stdout")
    parser.add_argument("--report", action="store_true", help="Write the dated report in evidence/scores/ AND record its telemetry run row")
    parser.add_argument("--output", type=str, default="", help="Custom report output path; diagnostic only: records no run row and does not satisfy the report step")
    parser.add_argument("--stamp", action="store_true", help="Record a run row only (no artifact; does not satisfy the report step)")
    parser.add_argument("--actor", type=str, default="hq", help="Actor role for ledger stamp (default: hq)")
    parser.add_argument(
        "--no-gates",
        action="store_true",
        help="Emit metrics only, skipping the mechanical gate suite (used by tests/test_audit_rates.py to avoid gate recursion). The verdict fields report null, never a green.",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Block on the run lock instead of refusing. The default is a non-blocking refuse (exit 3), because a blocked caller is what leaves an orphan when its turn dies.",
    )
    args = parser.parse_args()

    # THE WHOLE-RUN IN-FLIGHT GUARD (issue #145, ruling n=940). Two runs contending for
    # one cgroup is the load this bounds: 17 cron jobs fired inside a 19-second window
    # after the 2026-09-22 scheduler starvation, and the runs piled up. The guard is
    # taken BEFORE any work — a refusal must cost nothing and write nothing.
    #
    # EXEMPT UNDER --no-gates, and the exemption is principled rather than a carve-out:
    # `--no-gates` spawns no gates and so contributes none of the load the guard bounds.
    # It is also what keeps the suite green — `tests/test_audit_rates.py` is a registered
    # gate that runs `audit.py --json --no-gates` and asserts rc==0, so a guard applied
    # there would make the outer run hold the lock while its own gate's nested run
    # refused, and the gate would red.
    #
    # The handle is held in a local for the rest of `main()`: it is released when this
    # function returns and the file object is collected, which is exactly whole-run
    # scope, and it is deliberately NOT a global that could outlive the run.
    run_lock = None
    if not args.no_gates:
        run_lock = acquire_run_lock(wait=args.wait)
        if run_lock is None:
            # Exit 3 is DISTINCT from the 1 a gate failure returns, in the same namespace
            # as the budget-manifest refusal's 2: "the audit did not run" is not "the
            # audit ran and a gate failed", and a consumer reading a bare 1 would record
            # a verdict nobody took.
            return LOCK_HELD_EXIT_CODE

    ledger_file = REPO_ROOT / "evidence/ledger.jsonl"
    rework_file = REPO_ROOT / "evidence/rework.md"

    ledger_stats, closed_subject_set = parse_ledger(ledger_file)
    rework_stats = parse_rework(rework_file, closed_subject_set)
    cadence_stats = check_cadence_integrity(ledger_file)
    # A manifest that EXISTS and cannot be read is a DEFECT, never a fallback: defaulting
    # over an unreadable budget set would silently re-cap every gate in the tree (#94).
    # Caught HERE, at the one call site, so the operator gets one named line instead of a
    # traceback whose only readable line is its last. Exit 2 is DISTINCT from the 1 a gate
    # failure returns, because "the audit could not read its budgets" is not "the audit ran
    # and a gate failed" -- a consumer reading a bare 1 would record a verdict nobody took.
    try:
        if args.no_gates:
            gate_results, gate_budgets = [], None
        else:
            gate_results, gate_budgets = execute_mechanical_gates(REPO_ROOT)
    except GateBudgetManifestError as exc:
        print(f"gate budgets: {exc}", file=sys.stderr)
        return 2

    cadence_ok = cadence_stats.get("cadence_held", True)
    gates_ran = not args.no_gates
    # THREE states, decided by a PURE function so the headline is testable without the
    # whole gate wall around it (#93 ruling n=574 PART 2). The skipped-suite case (#28)
    # is decided inside `judge_gates`, not here.
    verdict = judge_gates(gate_results, cadence_ok=cadence_ok, gates_ran=gates_ran)
    # `healthy` keeps its bool/None shape for its existing consumers: True ONLY for
    # GREEN, False for DEGRADED and for UNKNOWN -- a state that returned no verdict is
    # not a healthy one -- and None when the suite was skipped. `all_gates_pass` keeps
    # its name for the JSON consumers and is taken over the gates that RAN TO A
    # VERDICT, so an UNKNOWN is in no pass total.
    healthy = verdict.healthy
    all_gates_pass = verdict.all_known_pass

    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    # THE CAUSE IS COMPUTED ONCE, for every surface (#158). It is attached here, before
    # the JSON emit and before both text renders, so the three cannot disagree about what
    # a failing gate said -- and so the JSON carries the COUNT a script-shaped gate prints
    # FIRST rather than leaving it to be dug out of the full stdout.
    attach_gate_causes(gate_results)

    if args.json:
        payload = {
            "date": today,
            "healthy": healthy,
            "status": verdict.status,
            "all_gates_pass": all_gates_pass,
            "gates_skipped": not gates_ran,
            "unknown_gates": len(verdict.unknown),
            "cadence": cadence_stats,
            "delivery": ledger_stats,
            "rework": rework_stats,
            "gates": gate_results,
        }
        print(json.dumps(payload, indent=2))
        return 0 if (healthy is None or healthy) else 1

    # Text summary output
    print(f"=== Factory Operational Self-Audit ({today}) ===")
    print(render_status_line(verdict))
    print(f"  - First-Pass Yield: {format_yield_text(ledger_stats)}")
    print(f"  - Cost / Successful Task: {format_cost_per_success_text(ledger_stats)}")
    print(f"  - Telemetry Outside the Trailer: {ledger_stats.get('out_of_trailer_count', 0)} row(s) — {format_out_of_trailer_note(ledger_stats)}")
    print(f"  - Undeclared Outcomes: {format_undeclared_text(ledger_stats)}")
    print(f"  - Closed Subjects: {ledger_stats.get('closed_tasks', 0)} (close rows: {ledger_stats.get('close_events', 0)}) | Intake Subjects: {ledger_stats.get('intake_tasks', 0)}")
    print(f"  - Rework Entries: {rework_stats.get('total_entries', 0)} (share: {round(rework_stats.get('rework_share', 0.0) * 100, 1)}% = {rework_stats.get('total_entries', 0)} ÷ ({rework_stats.get('closed_subjects', 0)} + {rework_stats.get('total_entries', 0)}) | per close: {round(rework_stats.get('rework_per_close', 0.0) * 100, 1)}% = {rework_stats.get('total_entries', 0)} ÷ {rework_stats.get('closed_subjects', 0)})")
    print(f"  - Rework Declarations: {ledger_stats.get('close_rows_declaring_rework', 0)}/{ledger_stats.get('close_events', 0)} close rows declare a disposition ({round(ledger_stats.get('rework_declaration_rate', 0.0) * 100, 1)}%) — {format_rework_declaration_note(ledger_stats)}")
    print(f"  - Change Fail Rate: {round(rework_stats.get('change_fail_rate', 0.0) * 100, 1)}% = {rework_stats.get('change_fail_rate_numerator', 0)} ÷ {rework_stats.get('change_fail_rate_denominator', 0)} closed work units (linkage coverage: {rework_stats.get('subject_coverage_numerator', 0)}/{rework_stats.get('subject_coverage_denominator', 0)} entries carry a determinate Subject — a bare rate is never read alone)")
    print(f"  - Cadence: {'HELD' if cadence_ok else 'MISSED'} (last run: {cadence_stats.get('hours_since_last_run')}h ago)")
    print(f"\nMechanical Gates ({len(gate_results)}):")
    for g in gate_results:
        # THREE marks, not two (#94 consequence 3): a gate that exhausted its budget
        # is UNKNOWN -- it neither passed nor failed, and printing FAIL would assert
        # a verdict nobody measured. The headline's three-state form is #93's; here
        # the state is at least never silently green.
        mark = "UNKNOWN" if g.get("unknown") else ("PASS" if g["passed"] else "FAIL")
        line = f"  [{mark}] {g['cmd']} ({g['duration_sec']}s of {g.get('budget_sec', 0.0):.2f}s)"
        if mark != "PASS":
            # THE CAUSE, ON THE LINE (#93 ruling n=574 PART 1(c)). A cause visible only
            # via `--json` is a cause the reader does not have, and the reader of this
            # line is the lane that must decide whether to RE-RUN. stdout first -- a
            # failing pytest gate writes its failure summary there -- then stderr, which
            # is where a KILLED or crashed gate states its reason.
            cause = g.get("note") or ""
            if cause:
                line += f" — {cause}"
        if g.get("retried"):
            line += f" [retried once — {g.get('attempts', 2)} attempt(s)]"
        print(line)

    # THE DEFAULT POPULATION, PRINTED (#94 consequence 1). A gate with no manifest
    # entry is legitimate -- a factory that has not measured it yet runs on the
    # declared default -- but an UNPRINTED fallback is an exempt-by-silence surface,
    # so the count examined is stated and every fallthrough gate is NAMED. The count
    # is stated even when it is zero, so an empty population is visibly empty rather
    # than indistinguishable from a print that never ran.
    default_gates = [g for g in gate_results if g.get("budget_source") == "default"]
    print(
        f"\nGate budgets: {len(gate_results)} gate(s) run — "
        f"{len(gate_results) - len(default_gates)} declared, "
        f"{len(default_gates)} fell through to default.budget_sec"
    )
    for g in default_gates:
        print(f"  [DEFAULT] {g.get('gate_key') or '(no file argument resolved)'} — {g['cmd']}")

    # THE DECLARED REVISIONS, SWEPT AND PRINTED (#125, ruling n=786). A basis that no
    # longer describes the command it was taken on is INVISIBLE in the caps themselves --
    # `budget_sec`, `measured_sec` and `margin_x` still satisfy the margin law, so every
    # existing check reads the entry as sound while the wall it describes has moved. The
    # sweep therefore prints its own account and names every entry it found, on the same
    # reasoning as the default population above: a check whose population is unprinted is
    # an exempt-by-silence surface, and the count is stated even at zero so an empty
    # population is visibly empty rather than indistinguishable from a print that never ran.
    #
    # IT REPORTS AND NEVER GATES. The values are the process owner's and never the
    # implementing lane's (n=574 PART 5), so a stale basis whose gate still runs inside its
    # cap is a fact about the manifest, not a failing gate -- and `test_template_sync.py`
    # is the live proof, having moved its bytes and got FASTER. Both legs are stated per
    # entry because they mean different things: moved BYTES say the basis describes a
    # different TEST, moved RUNNER FORM says it describes a different COMMAND.
    if gate_budgets is not None:
        print(f"\nGate budget staleness: {gate_budgets.stale_note}")
        for stale in gate_budgets.stale:
            print(f"  [STALE:{'+'.join(stale.legs)}] {stale.key} — {stale.detail}")

    if args.report or args.output:
        report_md = format_report_markdown(today, ledger_stats, rework_stats, cadence_stats, gate_results)
        out_path = Path(args.output) if args.output else (REPO_ROOT / f"evidence/scores/{today}-self-audit.md")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report_md, encoding="utf-8")
        print(f"\nAudit report written to: {out_path}")

    if args.stamp or args.report:
        outcome = "accepted" if (healthy is None or healthy) else "failed"
        # THREE tokens, matching the three states: an UNKNOWN run is neither `all-pass`
        # (no verdict was taken) nor `gate-failure` (no gate failed), and recording it as
        # either is exactly the collapse PART 2 forbids. Additive: no consumer enumerates
        # this vocabulary -- `gate=` appears in fixtures as a literal and in nothing that
        # validates its domain.
        gate_summary = (
            "skipped"
            if not gates_ran
            else (
                "all-pass"
                if verdict.status == "GREEN"
                else ("gate-unknown" if verdict.status == "UNKNOWN" else "gate-failure")
            )
        )
        _yield = ledger_stats.get("first_pass_yield")
        yield_pct = "n/a" if _yield is None else f"{int(_yield * 100)}%"
        detail = f"duration=4s turns=0 outcome={outcome} gate={gate_summary} yield={yield_pct}"
        stamp_cmd = [
            sys.executable,
            "tools/ledger.py",
            "append",
            "--event",
            "run",
            "--actor",
            args.actor,
            "--subject",
            "internal-self-audit",
            "--detail",
            detail,
        ]
        res = subprocess.run(stamp_cmd, cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0:
            print(f"Ledger telemetry stamped: {detail}")
        else:
            print(f"Failed to stamp ledger: {res.stderr.strip()}", file=sys.stderr)

    return 0 if (healthy is None or healthy) else 1


if __name__ == "__main__":
    sys.exit(main())
