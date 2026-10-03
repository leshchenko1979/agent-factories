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

3. **A post-invariant row with an EMPTY REPAIR SPACE is exempted in FACTORY DATA, and
   said so.** The boundary in part 2 is a TIMESTAMP, and a timestamp cannot excuse the
   rows the rule actually catches: the first post-invariant close that omits the token
   is PERMANENTLY RED, because the ledger is append-only, the row's identity is
   immutable once pushed, and a gate that walks `close` rows never revisits a repaired
   history. A gate whose only exits are barred is a stop with no andon cord, and the
   suite would stay red until every lane learned to ignore it — destroying every other
   gate's signal. So the exemption surface exists, and its terms are the skill's:
   admitted ONLY where the repair space is genuinely EMPTY (the row is pushed, and
   rewriting it is barred by the identity law); declared as FACTORY DATA in
   `docs/close-board-exemptions.json`, never inline in this file, because this file is
   paired byte-identically with `TEMPLATE/tests/test_close_board_recorded.py` and a
   factory's row number must not ship to every new factory; keyed by the row's own `n`,
   so a FUTURE close (a different `n`) can never be excused by it; and PRINTED as an
   `excused:` line with its reason and its proof on EVERY run, so clean and excused are
   never the same output. An entry that is malformed, or that matches NO violation, is a
   gate ERROR rather than a silent pass — an exemption list that quietly fails to load
   is indistinguishable from no exemptions. One exemption of this shape is a debt; a
   second is a PROCESS DEFECT, and the remedy is a mechanism, not a third row.

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
import tempfile
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

# The exemption surface (docstring part 3). FACTORY DATA, never source: this file is paired
# byte-identically with TEMPLATE/tests/test_close_board_recorded.py, so a factory's own row
# number must not live in a file that ships to every new factory.
EXEMPTIONS_PATH = REPO / "docs" / "close-board-exemptions.json"
BOARD_EXEMPT_DOMAIN = ("the board close happened but was not recorded in the row",)


def _parse_ts(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _has_board_token(detail: str) -> bool:
    """True when `detail` carries a `board=<state>` token, whatever the state.

    DELIBERATELY a scan of the whole `detail`, NOT of a canonical terminal run. MEASURED
    2026-10-03: 26 post-invariant close rows carry `board=closed` outside their terminal run
    — mid-prose, or with punctuation attached (`board=closed;`) — so a positional read would
    false-RED a quarter of the gate's population. The trailer convention binds the WRITER of
    a new row; this gate reads HISTORY, and a tightening that reds history is a false-red,
    not a finding. Commas and semicolons are stripped so `board=closed;` still reads as a
    `board=` token for the self-contradiction arm.
    """
    for token in detail.replace(",", " ").replace(";", " ").split():
        if token.startswith("board="):
            return True
    return False

def load_exemptions(path: Path | None = None) -> tuple[dict[int, dict], list[str]]:
    """Load the factory's close-board exemptions, keyed by row `n`.

    Absent or empty data means no exemptions — the shipped state of a new factory. Anything
    malformed is a problem, never a silent pass: an exemption list that quietly fails to
    load is indistinguishable from no exemptions, which is the vacuous-pass shape the whole
    gate exists to catch.
    """
    path = EXEMPTIONS_PATH if path is None else path
    if not path.is_file():
        return {}, []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"{path.name}: unreadable or malformed JSON: {exc!r}"]
    if not isinstance(data, dict):
        return {}, [f"{path.name}: expected a JSON object with an 'exemptions' list"]
    raw = data.get("exemptions", [])
    if not isinstance(raw, list):
        return {}, [f"{path.name}: 'exemptions' must be a list"]
    out: dict[int, dict] = {}
    problems: list[str] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            problems.append(f"{path.name}: exemption #{i} is not an object")
            continue
        row_n = entry.get("n")
        if not isinstance(row_n, int) or isinstance(row_n, bool):
            problems.append(f"{path.name}: exemption #{i} has no integer `n`")
            continue
        reason = str(entry.get("reason") or "").strip()
        proof = str(entry.get("proof") or "").strip()
        domain = str(entry.get("domain") or "").strip()
        if not reason or not proof:
            problems.append(
                f"{path.name}: exemption n={row_n} must state both `reason` and `proof`"
            )
            continue
        if domain not in BOARD_EXEMPT_DOMAIN:
            problems.append(
                f"{path.name}: exemption n={row_n} declares domain {domain!r}, outside the "
                f"declared domain {BOARD_EXEMPT_DOMAIN}"
            )
            continue
        if row_n in out:
            problems.append(f"{path.name}: exemption n={row_n} is declared twice")
            continue
        out[row_n] = entry
    return out, problems


def close_board_problems(
    rows: list[dict],
    exempt_before: str = INVARIANT_LANDED,
    exempt: dict[int, dict] | None = None,
) -> tuple[list[str], list[str]]:
    """Return (problems, excused) for the `close` rows of a ledger.

    `problems` names every post-invariant close row missing the token, AND every exemption
    that matched no such row (a stale exemption inflates visible debt while excusing
    nothing — the same vacuous-pass shape as an exemption list that fails to load).
    `excused` names every pre-invariant row and every EXEMPTED post-invariant row, so the
    three states — clean, excused-by-boundary, excused-by-exemption — are never conflated.
    """
    boundary = _parse_ts(exempt_before)
    declared = dict(exempt or {})
    problems: list[str] = []
    excused: list[str] = []
    matched: set[int] = set()

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
        lacks_token = BOARD_TOKEN not in detail
        # The exemption arm sits AFTER the deficiency is established, never before it: an
        # exemption may only excuse a row that is genuinely missing the token. Applied
        # first, it would excuse a row that HAS the token — and the stale-exemption check
        # below could never see it, because the row was consumed before it could be judged
        # (caught by this file's own `..._gained_the_token_is_stale` probe, 2026-10-03).
        if lacks_token and isinstance(n, int) and not isinstance(n, bool) and n in declared:
            entry = declared[n]
            matched.add(n)
            excused.append(
                f"n={n} ({ts}) EXEMPTED (empty repair space) — {entry.get('reason')} "
                f"[proof: {entry.get('proof')}]"
            )
            continue
        if not lacks_token:
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

    for n, entry in sorted(declared.items()):
        if n not in matched:
            problems.append(
                f"exemption n={n} matches NO post-invariant close row lacking {BOARD_TOKEN} — "
                f"a stale exemption excuses nothing while inflating the visible debt "
                f"({entry.get('reason')})"
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
    exempt, exempt_problems = load_exemptions()
    problems, excused = close_board_problems(rows, exempt=exempt)
    for line in excused:
        print(f"  excused: {line}")
    if exempt_problems:
        raise AssertionError(
            f"{EXEMPTIONS_PATH.name} could not be read as factory data:\n  "
            + "\n  ".join(exempt_problems)
        )
    if problems:
        raise AssertionError(
            "close rows written after the step-6 board-close requirement must carry "
            f"{BOARD_TOKEN}:\n  " + "\n  ".join(problems)
        )
    post_invariant = [
        r
        for r in rows
        if r.get("event") == "close"
        and _parse_ts(r.get("ts", "")) >= _parse_ts(INVARIANT_LANDED)
    ]
    checked = sum(
        1 for r in post_invariant if BOARD_TOKEN in str(r.get("detail") or "")
    )
    print(
        f"board-close gate: {checked} post-invariant close row(s) carry {BOARD_TOKEN}, "
        f"{len(exempt)} exempted as factory data, "
        f"{len(excused)} excused in total (pre-invariant + exempted)"
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


def test_an_exempted_row_is_excused_and_printed() -> None:
    """An exemption excuses LOUDLY: the row leaves `problems` and PRINTS with its proof."""
    rows = [
        {"n": 2101, "ts": "2026-10-03T19:32:46Z", "event": "close", "detail": "outcome=accepted"}
    ]
    exempt = {
        2101: {
            "n": 2101,
            "reason": "the board close happened but was not recorded in the row",
            "proof": "gh issue view 197 reads CLOSED at 2026-10-03T19:35:54Z",
        }
    }
    problems, excused = close_board_problems(rows, exempt=exempt)
    assert not problems, problems
    assert len(excused) == 1 and "EXEMPTED" in excused[0], excused
    assert "gh issue view 197" in excused[0], excused

def test_an_exemption_that_matches_nothing_is_an_error() -> None:
    """A stale exemption excuses nothing while inflating the visible debt."""
    rows = [{"n": 2101, "ts": "2026-10-03T19:32:46Z", "event": "close", "detail": "board=closed"}]
    exempt = {999: {"n": 999, "reason": "stale", "proof": "none"}}
    problems, excused = close_board_problems(rows, exempt=exempt)
    assert problems and "matches NO" in problems[0], problems
    assert not excused, excused

def test_an_exemption_cannot_excuse_a_future_close() -> None:
    """The key is the row's own `n`, so a DIFFERENT close is never excused by it."""
    rows = [
        {"n": 2200, "ts": "2026-10-04T00:00:00Z", "event": "close", "detail": "outcome=accepted"}
    ]
    exempt = {2101: {"n": 2101, "reason": "the rows of 2026-10-03", "proof": "p"}}
    problems, _excused = close_board_problems(rows, exempt=exempt)
    assert any("missing board=closed" in p for p in problems), problems
    assert any("matches NO" in p for p in problems), problems

def test_an_exempted_row_that_gained_the_token_is_stale() -> None:
    """An exemption whose row now carries the token excuses nothing and must be removed."""
    rows = [{"n": 2101, "ts": "2026-10-03T19:32:46Z", "event": "close", "detail": "board=closed"}]
    exempt = {2101: {"n": 2101, "reason": "no longer needed", "proof": "p"}}
    problems, _excused = close_board_problems(rows, exempt=exempt)
    assert any("matches NO" in p for p in problems), problems

def test_load_exemptions_absent_means_none() -> None:
    """The shipped state of a new factory: no file, no exemptions, no problem."""
    with tempfile.TemporaryDirectory() as d:
        got, problems = load_exemptions(Path(d) / "close-board-exemptions.json")
    assert got == {} and problems == [], (got, problems)

def test_load_exemptions_rejects_a_malformed_entry() -> None:
    """An exemption list that quietly fails to load is indistinguishable from none."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "close-board-exemptions.json"
        p.write_text('{"exemptions": [{"n": 2101}]}', encoding="utf-8")
        got, problems = load_exemptions(p)
    assert problems and not got, (got, problems)

def test_load_exemptions_enforces_the_declared_domain() -> None:
    """A domain outside the declared set is an ERROR, never a silent pass."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "close-board-exemptions.json"
        p.write_text(
            '{"exemptions": [{"n": 1, "reason": "r", "proof": "p", "domain": "not it"}]}',
            encoding="utf-8",
        )
        got, problems = load_exemptions(p)
    assert problems and "domain" in problems[0], (got, problems)

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
