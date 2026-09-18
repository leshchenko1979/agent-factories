#!/usr/bin/env python3
"""Gate: a measurement run records its closing workspace-gate verdict.

Origin (issue #32). The measurement run could end with an uncommitted score file:
step 7 committed the report, later re-read corrections landed after that commit, and
no step re-checked the tree. The workspace gate already existed (`tools/hygiene.py
--audit`, repaired by #28) but the run never invoked it — a gate that exists and does
not run is dead text (P29). Step 7 now requires it, and this gate makes that
requirement *checkable* instead of asserted: the difference between a procedure that
says it and a rule that is upheld.

The rule, in two parts:

1. **Every `score` row written on or after the invariant landed carries the closing
   verdict** — `workspace_gate=rc=0` — and the HEAD sha the run committed at
   (`head=<sha>`). A run that skipped the gate leaves no verdict, so the absence is
   the signal; the sha makes the row checkable against the repository rather than a
   claim about a tree that has since moved.
2. **Rows written before the invariant are excused, and said so.** They are reported
   as `excused:` with their count, never folded into a bare "clean" — the convention
   `tools/ledger.py` already uses for its own legacy closes, so that "clean" and
   "excused" are never the same output. Nothing is backfilled: a verdict written today
   for a run that predates the rule would be a falsified record, not a repair.

The invariant is factored into `score_gate_problems()` so synthetic rows can probe it:
a rule that has only ever seen good input has not been shown to reject bad input.

Run:  python3 -m pytest tests/test_score_gate_recorded.py -q
Exit: 0 clean or fully excused, non-zero on any post-invariant row without a verdict.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "evidence" / "ledger.jsonl"

# The commit that landed the step-7 closing invariant in docs/measurement-procedure.md.
# Rows written before this moment predate the rule and are excused; rows at or after it
# must carry the verdict. Nothing before it is backfilled.
INVARIANT_LANDED = "2026-09-18T10:04:05Z"  # commit 9552947
VERDICT_KEY = "workspace_gate=rc=0"
_HEX = set("0123456789abcdef")


def _parse_ts(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _has_head_sha(detail: str) -> bool:
    """True when `detail` carries a `head=<sha>` token with a plausible sha."""
    for token in detail.replace(",", " ").replace(";", " ").split():
        if not token.startswith("head="):
            continue
        sha = token[len("head="):].strip(").")
        if len(sha) >= 7 and all(c in _HEX for c in sha):
            return True
    return False


def score_gate_problems(
    rows: list[dict], exempt_before: str = INVARIANT_LANDED
) -> tuple[list[str], list[str]]:
    """Return (problems, excused) for the `score` rows of a ledger.

    `problems` names every post-invariant score row missing part of the verdict;
    `excused` names every pre-invariant row, so the two are never conflated.
    """
    boundary = _parse_ts(exempt_before)
    problems: list[str] = []
    excused: list[str] = []

    for row in rows:
        if row.get("event") != "score":
            continue
        n, ts = row.get("n"), row.get("ts", "")
        try:
            when = _parse_ts(ts)
        except (ValueError, TypeError):
            problems.append(f"n={n}: unparseable ts {ts!r}")
            continue
        if when < boundary:
            excused.append(f"n={n} ({ts}) predates the invariant ({exempt_before})")
            continue
        detail = str(row.get("detail") or "")
        missing = []
        if VERDICT_KEY not in detail:
            missing.append(VERDICT_KEY)
        if not _has_head_sha(detail):
            missing.append("head=<sha>")
        if missing:
            problems.append(f"n={n} ({ts}) missing {' and '.join(missing)}")

    return problems, excused


def _load_rows() -> list[dict]:
    rows: list[dict] = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


# --- live gate -------------------------------------------------------------------


def test_live_ledger_records_the_closing_verdict() -> None:
    rows = _load_rows()
    problems, excused = score_gate_problems(rows)
    for line in excused:
        print(f"  excused: {line}")
    if problems:
        raise AssertionError(
            "score rows written after the step-7 closing invariant must carry the "
            "workspace-gate verdict and the committed HEAD sha:\n  "
            + "\n  ".join(problems)
        )
    checked = sum(
        1
        for r in rows
        if r.get("event") == "score"
        and _parse_ts(r.get("ts", "")) >= _parse_ts(INVARIANT_LANDED)
    )
    print(
        f"score-gate verdict gate: {checked} post-invariant score row(s) verified, "
        f"{len(excused)} excused (pre-invariant)"
    )


# --- probes: the invariant must reject bad input, not only accept good ------------

_OK = {
    "n": 900,
    "ts": "2026-09-19T06:00:00Z",
    "event": "score",
    "detail": "survey-2026-09-19 — workspace_gate=rc=0 head=9552947a985b0f1a6c8919c362a0a56ec7d0d42e",
}


def test_probe_accepts_a_compliant_row() -> None:
    problems, excused = score_gate_problems([_OK])
    assert problems == [] and excused == []


def test_probe_rejects_a_row_without_the_verdict() -> None:
    row = {**_OK, "detail": "survey-2026-09-19 — head=9552947a985b0f1a6c8919c362a0a56ec7d0d42e"}
    problems, _ = score_gate_problems([row])
    assert problems and VERDICT_KEY in problems[0], problems


def test_probe_rejects_a_failing_verdict() -> None:
    row = {**_OK, "detail": "survey-2026-09-19 — workspace_gate=rc=1 head=9552947a985b0"}
    problems, _ = score_gate_problems([row])
    assert problems, "a failing workspace gate must not read as a recorded pass"


def test_probe_rejects_a_row_without_the_head_sha() -> None:
    row = {**_OK, "detail": "survey-2026-09-19 — workspace_gate=rc=0"}
    problems, _ = score_gate_problems([row])
    assert problems and "head=<sha>" in problems[0], problems


def test_probe_excuses_pre_invariant_rows_without_calling_them_clean() -> None:
    legacy = {
        "n": 179,
        "ts": "2026-09-18T07:04:29Z",
        "event": "score",
        "detail": "survey-2026-09-18-third-read",
    }
    problems, excused = score_gate_problems([legacy])
    assert problems == [], problems
    assert len(excused) == 1 and "predates the invariant" in excused[0]


def test_probe_ignores_non_score_events() -> None:
    other = {"n": 901, "ts": "2026-09-19T06:00:00Z", "event": "dispatch", "detail": "x"}
    problems, excused = score_gate_problems([other])
    assert problems == [] and excused == []
