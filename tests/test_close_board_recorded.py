#!/usr/bin/env python3
"""Gate: a close records the BOARD close, not only the ledger row.

Origin (issue #44). Process 1 step 6, `Settlement & Release`, named the ledger
`close` row and treated the board close as optional — so it happened some of the
time. Measured over one day, five subjects were complete-by-ledger and open-on-board
at once: `#36` for 30m26s until closed by hand, `#33` for 79m06s and `#35` for 78m34s,
`#34` for 18m55s, `#38` for 6m20s. A step that does not require the board close gets it
remembered, not
performed; the ledger then says the work is done while the board's own hourly sweep
re-derives it as outstanding.

The rule, in two parts:

1. **Every `close` row written on or after the invariant landed carries
   `board=closed`** — the board state the settling lane recorded at close time. A
   close that skipped the board close leaves the token absent, so the absence is the
   signal. The value must be `closed`: a close row asserting `board=open` is a
   self-contradiction, not a weaker form of the same record.
2. **Rows written before the invariant are excused, and said so.** They are reported
   as `excused:` with their count, never folded into a bare "clean" — the convention
   `tools/ledger.py` and `tests/test_score_gate_recorded.py` both use, so that
   "clean" and "excused" are never the same output. Nothing is backfilled: a token
   written today for a close that predates the rule would be a falsified record, not
   a repair.

**Why the row records the state rather than the gate checking it.** A gate cannot
call `gh`: the mechanical suite must run offline and against a tree, not a live
board. So the settling lane records the board state it observed, and the gate asserts
it was recorded — the same shape `tests/test_score_gate_recorded.py` uses for the
closing `workspace_gate` verdict. The gate's job is to make the omission visible, and
an omission is visible from the row alone.

The invariant is factored into `close_board_problems()` so synthetic rows can probe
it: a rule that has only ever seen good input has not been shown to reject bad input.

Run:  python3 -m pytest tests/test_close_board_recorded.py -q
Exit: 0 clean or fully excused, non-zero on any post-invariant close without the token.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ledger_boundary import evidence_skip_reason, module_skip  # noqa: E402

REPO = Path(__file__).resolve().parent.parent

# BOTH INVOCATION MODES MUST REACH THE GUARD (#199). The audit invokes this gate in pytest
# mode and pytest never calls `main()`, so a guard there protects only the script-mode run —
# #195's split exactly. `pytestmark` COLLECTS the tests and skips them (exit 0); a module-level
# `pytest.skip` would exit 5, which the audit reads as a failure.
# STATED SKIP: evidence/ledger.jsonl (BOOTSTRAP-created, step 4b)
_SKIP_REASON = module_skip(REPO)
if _SKIP_REASON:
    import pytest as _pytest  # noqa: E402

    pytestmark = _pytest.mark.skipif(True, reason=_SKIP_REASON)

LEDGER = REPO / "evidence" / "ledger.jsonl"

# The commit that landed the step-6 board-close requirement in docs/processes.md.
# Rows written before this moment predate the rule and are excused; rows at or after
# it must carry the token. Nothing before it is backfilled.
INVARIANT_LANDED = "2026-09-18T18:04:24Z"  # commit d6c9d55
BOARD_TOKEN = "board=closed"


def _parse_ts(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _has_board_token(detail: str) -> bool:
    """True when `detail` carries a `board=<state>` token, whatever the state."""
    for token in detail.replace(",", " ").replace(";", " ").split():
        if token.startswith("board="):
            return True
    return False


def close_board_problems(
    rows: list[dict], exempt_before: str = INVARIANT_LANDED
) -> tuple[list[str], list[str]]:
    """Return (problems, excused) for the `close` rows of a ledger.

    `problems` names every post-invariant close row missing the token; `excused`
    names every pre-invariant row, so the two are never conflated.
    """
    boundary = _parse_ts(exempt_before)
    problems: list[str] = []
    excused: list[str] = []

    for row in rows:
        if row.get("event") != "close":
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
        if BOARD_TOKEN in detail:
            continue
        if _has_board_token(detail):
            problems.append(
                f"n={n} ({ts}) carries a board= token whose value is not `closed` — "
                f"a close row asserting the board is still open contradicts itself"
            )
        else:
            problems.append(
                f"n={n} ({ts}) missing {BOARD_TOKEN} — the board issue was not closed "
                f"with this close, so the ledger says done while the board says open"
            )

    return problems, excused


def _load_rows() -> list[dict]:
    rows: list[dict] = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


# --- live gate -------------------------------------------------------------------


def test_live_ledger_records_the_board_close() -> None:
    rows = _load_rows()
    problems, excused = close_board_problems(rows)
    for line in excused:
        print(f"  excused: {line}")
    if problems:
        raise AssertionError(
            "close rows written after the step-6 board-close requirement must carry "
            f"{BOARD_TOKEN}:\n  " + "\n  ".join(problems)
        )
    checked = sum(
        1
        for r in rows
        if r.get("event") == "close"
        and _parse_ts(r.get("ts", "")) >= _parse_ts(INVARIANT_LANDED)
    )
    print(
        f"board-close gate: {checked} post-invariant close row(s) verified, "
        f"{len(excused)} excused (pre-invariant)"
    )


# --- probes: the invariant must reject bad input, not only accept good ------------


def test_a_post_invariant_close_without_the_token_is_rejected() -> None:
    rows = [
        {"n": 1, "ts": "2026-09-18T19:00:00Z", "event": "close", "detail": "outcome=accepted"}
    ]
    problems, excused = close_board_problems(rows)
    assert problems and not excused, (problems, excused)
    assert BOARD_TOKEN in problems[0]


def test_a_pre_invariant_close_is_excused_not_failed() -> None:
    rows = [
        {"n": 2, "ts": "2026-09-18T17:00:00Z", "event": "close", "detail": "outcome=accepted"}
    ]
    problems, excused = close_board_problems(rows)
    assert not problems and excused, (problems, excused)


def test_a_token_that_does_not_say_closed_is_rejected() -> None:
    """`board=open` on a close row is a self-contradiction, not a weaker record."""
    rows = [
        {"n": 3, "ts": "2026-09-18T19:00:00Z", "event": "close", "detail": "board=open"}
    ]
    problems, _excused = close_board_problems(rows)
    assert problems, "a board=open close row was accepted"
    assert "contradicts itself" in problems[0]


def test_a_post_invariant_close_with_the_token_passes() -> None:
    rows = [
        {
            "n": 4,
            "ts": "2026-09-18T19:00:00Z",
            "event": "close",
            "detail": f"outcome=accepted {BOARD_TOKEN} gate=18-of-18-pass",
        }
    ]
    problems, excused = close_board_problems(rows)
    assert not problems and not excused, (problems, excused)


def test_non_close_rows_are_outside_the_population() -> None:
    """Only `close` rows promise a board close; a claim or run row does not."""
    rows = [
        {"n": 5, "ts": "2026-09-18T19:00:00Z", "event": "claim", "detail": "no token here"},
        {"n": 6, "ts": "2026-09-18T19:00:00Z", "event": "run", "detail": "no token here"},
    ]
    problems, excused = close_board_problems(rows)
    assert not problems and not excused, (problems, excused)


def test_an_unparseable_ts_is_a_problem_not_an_excuse() -> None:
    """A row whose timestamp cannot be read cannot be excused by it either."""
    rows = [{"n": 7, "ts": "not-a-time", "event": "close", "detail": "board=closed"}]
    problems, excused = close_board_problems(rows)
    assert problems and not excused, (problems, excused)


def test_gate_is_registered_in_the_audit() -> None:
    audit = (REPO / "tools" / "audit.py").read_text(encoding="utf-8")
    assert "test_close_board_recorded.py" in audit, (
        "gate not registered in tools/audit.py — an unregistered gate never runs (P29)"
    )


def main() -> int:
    # THE SHIPPED TREE IS NOT A FACTORY (#199). `evidence/` is BOOTSTRAP-created (BOOTSTRAP.md
    # steps 4b/4c), so the tree the kit ships carries none of it and this gate's whole subject
    # is absent. Without this arm the gate died with FileNotFoundError in the tree it ships
    # from -- a CRASH, not a verdict, which is neither a pass nor a stated skip. The reason is
    # printed and names the artifact, so a reader can tell "nothing to judge yet" from "clean".
    skip = evidence_skip_reason(REPO)
    if skip:
        print(f"close-board gate: SKIPPED — {skip}")
        return 0
    try:
        test_live_ledger_records_the_board_close()
    except AssertionError as exc:
        print(f"close-board gate failed:\n{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
