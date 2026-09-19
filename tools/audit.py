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
import datetime
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

# The telemetry reader is the SHARED predicate, never a local re-parse (issue #90).
# `n=405` PART 5 rules the CLASS — "it is why the class, not the three call sites, is
# the ruling" — so a fourth site may not carry its own scan. The path insert is the
# sibling form: this file is run as a script (its own dir is already on the path) and
# imported by `tests/`, and both must resolve the same reader.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from field_predicate import declared_telemetry, mentioned_telemetry  # noqa: E402

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


def run_gate(cmd: list[str], cwd: Path) -> dict[str, Any]:
    """Run an individual verification gate and capture output and exit code."""
    try:
        t0 = datetime.datetime.now()
        res = subprocess.run(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
        t_el = (datetime.datetime.now() - t0).total_seconds()
        return {
            "cmd": " ".join(cmd),
            "exit_code": res.returncode,
            "passed": res.returncode == 0,
            "duration_sec": round(t_el, 2),
            "stdout": res.stdout.strip(),
            "stderr": res.stderr.strip(),
        }
    except Exception as e:
        return {
            "cmd": " ".join(cmd),
            "exit_code": 99,
            "passed": False,
            "duration_sec": 0.0,
            "stdout": "",
            "stderr": str(e),
        }


def execute_mechanical_gates(repo_root: Path) -> list[dict[str, Any]]:
    """Execute all discovered mechanical gates."""
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
        gates_to_run.append([sys.executable, "tests/test_board_intake_recorded.py"])

    # 26. Gate-fixture closure gate: a fixture that runs a tool inside a throwaway tree
    #     must stage the tool's import CLOSURE, not the file alone. Copying the file alone
    #     encodes an unstated assumption of self-containment, so it holds silently until
    #     the tool gains a lawful intra-repo import — and then the gate reds on a correct
    #     change and the red misreads as the tool's fault. The predicate resolves
    #     module-level path constants, because the fourth site stages its tool as
    #     `copy2(REPO_ROOT / TOOL_REL, ...)` and a literal-only match reports it clean
    #     (issue #60, P35, P29).
    if (repo_root / "tests/test_gate_fixtures_closure.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_gate_fixtures_closure.py"])

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
    #     state — session bindings and the known-factory set — which is why the file is
    #     classified in gate_registry.OPTIONAL_GATES until it is parameterized for the
    #     template (P29).
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
        gates_to_run.append([sys.executable, "tests/test_patrol_host_state.py"])

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

    results = []
    for cmd in gates_to_run:
        results.append(run_gate(cmd, repo_root))
    return results


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
        status = "PASS" if g["passed"] else "FAIL"
        note = g["stdout"].splitlines()[-1] if g["stdout"] else (g["stderr"].splitlines()[-1] if g["stderr"] else "")
        note = note.replace("|", "/")
        lines.append(f"| `{g['cmd']}` | `{status}` | `{g['duration_sec']}s` | {note[:60]} |")

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
    args = parser.parse_args()

    ledger_file = REPO_ROOT / "evidence/ledger.jsonl"
    rework_file = REPO_ROOT / "evidence/rework.md"

    ledger_stats, closed_subject_set = parse_ledger(ledger_file)
    rework_stats = parse_rework(rework_file, closed_subject_set)
    cadence_stats = check_cadence_integrity(ledger_file)
    gate_results = [] if args.no_gates else execute_mechanical_gates(REPO_ROOT)

    all_gates_pass = None if args.no_gates else all(g["passed"] for g in gate_results)
    cadence_ok = cadence_stats.get("cadence_held", True)
    gates_ran = not args.no_gates
    # A skipped gate suite reports no verdict at all. `all([])` is True, so leaving
    # `healthy` to be computed here would print a green over gates that never ran —
    # the same silent-green class of defect the hygiene gate carried (#28).
    healthy = (all_gates_pass and cadence_ok) if gates_ran else None

    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    if args.json:
        payload = {
            "date": today,
            "healthy": healthy,
            "all_gates_pass": all_gates_pass,
            "gates_skipped": not gates_ran,
            "cadence": cadence_stats,
            "delivery": ledger_stats,
            "rework": rework_stats,
            "gates": gate_results,
        }
        print(json.dumps(payload, indent=2))
        return 0 if (healthy is None or healthy) else 1

    # Text summary output
    print(f"=== Factory Operational Self-Audit ({today}) ===")
    print(f"Status: {'HEALTHY (PASS)' if healthy else ('GATES SKIPPED (metrics only)' if not gates_ran else 'DEGRADED (FAIL)')}")
    print(f"  - First-Pass Yield: {format_yield_text(ledger_stats)}")
    print(f"  - Cost / Successful Task: {format_cost_per_success_text(ledger_stats)}")
    print(f"  - Telemetry Outside the Trailer: {ledger_stats.get('out_of_trailer_count', 0)} row(s) — {format_out_of_trailer_note(ledger_stats)}")
    print(f"  - Undeclared Outcomes: {format_undeclared_text(ledger_stats)}")
    print(f"  - Closed Subjects: {ledger_stats.get('closed_tasks', 0)} (close rows: {ledger_stats.get('close_events', 0)}) | Intake Subjects: {ledger_stats.get('intake_tasks', 0)}")
    print(f"  - Rework Entries: {rework_stats.get('total_entries', 0)} (share: {round(rework_stats.get('rework_share', 0.0) * 100, 1)}% = {rework_stats.get('total_entries', 0)} ÷ ({rework_stats.get('closed_subjects', 0)} + {rework_stats.get('total_entries', 0)}) | per close: {round(rework_stats.get('rework_per_close', 0.0) * 100, 1)}% = {rework_stats.get('total_entries', 0)} ÷ {rework_stats.get('closed_subjects', 0)})")
    print(f"  - Change Fail Rate: {round(rework_stats.get('change_fail_rate', 0.0) * 100, 1)}% = {rework_stats.get('change_fail_rate_numerator', 0)} ÷ {rework_stats.get('change_fail_rate_denominator', 0)} closed work units (linkage coverage: {rework_stats.get('subject_coverage_numerator', 0)}/{rework_stats.get('subject_coverage_denominator', 0)} entries carry a determinate Subject — a bare rate is never read alone)")
    print(f"  - Cadence: {'HELD' if cadence_ok else 'MISSED'} (last run: {cadence_stats.get('hours_since_last_run')}h ago)")
    print(f"\nMechanical Gates ({len(gate_results)}):")
    for g in gate_results:
        mark = "PASS" if g["passed"] else "FAIL"
        print(f"  [{mark}] {g['cmd']} ({g['duration_sec']}s)")

    if args.report or args.output:
        report_md = format_report_markdown(today, ledger_stats, rework_stats, cadence_stats, gate_results)
        out_path = Path(args.output) if args.output else (REPO_ROOT / f"evidence/scores/{today}-self-audit.md")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report_md, encoding="utf-8")
        print(f"\nAudit report written to: {out_path}")

    if args.stamp or args.report:
        outcome = "accepted" if (healthy is None or healthy) else "failed"
        gate_summary = "skipped" if not gates_ran else ("all-pass" if all_gates_pass else "gate-failure")
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
