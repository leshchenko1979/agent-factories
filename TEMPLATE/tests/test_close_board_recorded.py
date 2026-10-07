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
from ledger_boundary import (  # noqa: E402
    GateError,
    SkipGate,
    boundary_and_rows,
    evidence_skip_reason,
    module_skip,
    population_skip_reason,
    post_boundary_rows,
    synthetic_tree,
)

import pytest  # noqa: E402

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

# The boundary is FACTORY DATA (#428), declared in `docs/ledger-invariants.json` under this
# key and read through `tests/ledger_boundary.py`. It is NOT a literal here: this file is
# paired byte-identically with TEMPLATE/tests/test_close_board_recorded.py, so a date
# written inside it ships to every member and is read against the MEMBER's ledger, where
# this factory's commit history means nothing. An ABSENT declaration skips with its reason
# — the state every bootstrapped factory is in until it adopts the invariant; a MALFORMED
# one FAILS, because a broken declaration must not hide behind the same output as none.
INVARIANT_KEY = "close_board_recorded"
BOARD_TOKEN = "board=closed"

# The PROBES' own boundary — a fixture, never the factory's declaration. It sits between
# the probe rows' `17:00` and `19:00` timestamps so both arms are reachable, and it is
# deliberately NOT the commit instant: a probe asserts the PREDICATE, and a predicate
# pinned to this factory's history asserts nothing about a member's.
_PROBE_BOUNDARY = "2026-09-18T18:00:00Z"

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
    exempt_before: str,
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


def evaluate(repo: Path) -> tuple[str, str, list[str], list[str], int]:
    """`(status, reason, problems, excused, checked)` over `repo` — the probe-able core.

    `status` is `"pass"`, `"skip"` or `"fail"`. A real problem outranks a skip: the
    population guard runs only on an otherwise-clean ledger, so a defect is never hidden
    behind "there was nothing to judge".
    """
    try:
        boundary, boundary_text, rows = boundary_and_rows(repo, INVARIANT_KEY)
    except SkipGate as exc:
        return "skip", str(exc), [], [], 0
    except GateError as exc:
        return "fail", "", list(exc.problems), [], 0

    exempt, exempt_problems = load_exemptions(repo / "docs" / "close-board-exemptions.json")
    problems, excused = close_board_problems(rows, boundary_text, exempt)
    if exempt_problems or problems:
        return "fail", "", list(exempt_problems) + list(problems), excused, 0

    population = post_boundary_rows(rows, boundary, "close")
    reason = population_skip_reason(population, boundary_text, "close")
    if reason:
        return "skip", reason, [], excused, 0
    checked = sum(1 for r in population if BOARD_TOKEN in str(r.get("detail") or ""))
    return "pass", "", [], excused, checked


# --- live gate -------------------------------------------------------------------


def test_live_ledger_records_the_board_close() -> None:
    status, reason, problems, excused, checked = evaluate(REPO)
    for line in excused:
        print(f"  excused: {line}")
    if status == "skip":
        print(f"  SKIP: {reason}")
        pytest.skip(reason)
    if status == "fail":
        raise AssertionError(
            "close rows written after the declared boundary must carry "
            f"{BOARD_TOKEN}:\n  " + "\n  ".join(problems)
        )
    print(
        f"board-close gate: {checked} post-boundary close row(s) carry {BOARD_TOKEN}, "
        f"{len(excused)} excused in total (pre-boundary + exempted)"
    )


# --- probes: the invariant must reject bad input, not only accept good ------------


def test_a_post_invariant_close_without_the_token_is_rejected() -> None:
    rows = [
        {"n": 1, "ts": "2026-09-18T19:00:00Z", "event": "close", "detail": "outcome=accepted"}
    ]
    problems, excused = close_board_problems(rows, _PROBE_BOUNDARY)
    assert problems and not excused, (problems, excused)
    assert BOARD_TOKEN in problems[0]


def test_a_pre_invariant_close_is_excused_not_failed() -> None:
    rows = [
        {"n": 2, "ts": "2026-09-18T17:00:00Z", "event": "close", "detail": "outcome=accepted"}
    ]
    problems, excused = close_board_problems(rows, _PROBE_BOUNDARY)
    assert not problems and excused, (problems, excused)


def test_a_token_that_does_not_say_closed_is_rejected() -> None:
    """`board=open` on a close row is a self-contradiction, not a weaker record."""
    rows = [
        {"n": 3, "ts": "2026-09-18T19:00:00Z", "event": "close", "detail": "board=open"}
    ]
    problems, _excused = close_board_problems(rows, _PROBE_BOUNDARY)
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
    problems, excused = close_board_problems(rows, _PROBE_BOUNDARY)
    assert not problems and not excused, (problems, excused)


def test_non_close_rows_are_outside_the_population() -> None:
    """Only `close` rows promise a board close; a claim or run row does not."""
    rows = [
        {"n": 5, "ts": "2026-09-18T19:00:00Z", "event": "claim", "detail": "no token here"},
        {"n": 6, "ts": "2026-09-18T19:00:00Z", "event": "run", "detail": "no token here"},
    ]
    problems, excused = close_board_problems(rows, _PROBE_BOUNDARY)
    assert not problems and not excused, (problems, excused)


def test_an_unparseable_ts_is_a_problem_not_an_excuse() -> None:
    """A row whose timestamp cannot be read cannot be excused by it either."""
    rows = [{"n": 7, "ts": "not-a-time", "event": "close", "detail": "board=closed"}]
    problems, excused = close_board_problems(rows, _PROBE_BOUNDARY)
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
    problems, excused = close_board_problems(rows, _PROBE_BOUNDARY, exempt=exempt)
    assert not problems, problems
    assert len(excused) == 1 and "EXEMPTED" in excused[0], excused
    assert "gh issue view 197" in excused[0], excused

def test_an_exemption_that_matches_nothing_is_an_error() -> None:
    """A stale exemption excuses nothing while inflating the visible debt."""
    rows = [{"n": 2101, "ts": "2026-10-03T19:32:46Z", "event": "close", "detail": "board=closed"}]
    exempt = {999: {"n": 999, "reason": "stale", "proof": "none"}}
    problems, excused = close_board_problems(rows, _PROBE_BOUNDARY, exempt=exempt)
    assert problems and "matches NO" in problems[0], problems
    assert not excused, excused

def test_an_exemption_cannot_excuse_a_future_close() -> None:
    """The key is the row's own `n`, so a DIFFERENT close is never excused by it."""
    rows = [
        {"n": 2200, "ts": "2026-10-04T00:00:00Z", "event": "close", "detail": "outcome=accepted"}
    ]
    exempt = {2101: {"n": 2101, "reason": "the rows of 2026-10-03", "proof": "p"}}
    problems, _excused = close_board_problems(rows, _PROBE_BOUNDARY, exempt=exempt)
    assert any("missing board=closed" in p for p in problems), problems
    assert any("matches NO" in p for p in problems), problems

def test_an_exempted_row_that_gained_the_token_is_stale() -> None:
    """An exemption whose row now carries the token excuses nothing and must be removed."""
    rows = [{"n": 2101, "ts": "2026-10-03T19:32:46Z", "event": "close", "detail": "board=closed"}]
    exempt = {2101: {"n": 2101, "reason": "no longer needed", "proof": "p"}}
    problems, _excused = close_board_problems(rows, _PROBE_BOUNDARY, exempt=exempt)
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

# --- probes: the DECLARATION the boundary is read from (#428) ----------------------

def test_probe_a_tree_with_no_declared_boundary_skips_with_a_stated_reason(
    tmp_path: Path,
) -> None:
    """The declaration is FACTORY DATA and does not ship, so its absence is the state every
    bootstrapped factory is in — a STATED skip, never a red and never a silent pass. This
    is the arm that keeps the shipped `TEMPLATE/` tree green (#78, #76's class)."""
    tree = synthetic_tree(
        tmp_path / "no-declaration",
        rows=[
            {"n": 1, "ts": "2026-09-18T19:00:00Z", "event": "close", "detail": "board=closed"}
        ],
    )
    status, reason, problems, _, _ = evaluate(tree)
    assert status == "skip", (status, reason, problems)
    assert "ledger-invariants" in reason, reason

def test_probe_a_declaration_without_this_key_skips_and_names_it(tmp_path: Path) -> None:
    """A factory that has adopted SOME invariant but not this one is the same state: the
    skip names the KEY, so a reader can tell which invariant is unadopted."""
    tree = synthetic_tree(
        tmp_path / "other-key",
        rows=[
            {"n": 1, "ts": "2026-09-18T19:00:00Z", "event": "close", "detail": "board=closed"}
        ],
        invariants={"some_other_gate": "2026-09-18T18:00:00Z"},
    )
    status, reason, problems, _, _ = evaluate(tree)
    assert status == "skip", (status, reason, problems)
    assert INVARIANT_KEY in reason, reason

def test_probe_a_declared_boundary_with_a_bad_row_still_fails(tmp_path: Path) -> None:
    """The declaration MOVES the boundary; it never excuses the population. A row at or
    after the declared instant that omits the token is still RED — the guard is the
    predicate, not the fixture."""
    tree = synthetic_tree(
        tmp_path / "bad-row",
        rows=[
            {"n": 1, "ts": "2026-09-18T19:00:00Z", "event": "close", "detail": "outcome=accepted"}
        ],
        invariants={INVARIANT_KEY: "2026-09-18T18:00:00Z"},
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert any(BOARD_TOKEN in p for p in problems), problems

def test_probe_an_unreadable_declared_boundary_fails(tmp_path: Path) -> None:
    """A factory that DECLARED a boundary and cannot read it is a FAILURE, not a skip:
    skipping would hide a broken declaration behind the same output as none at all."""
    tree = synthetic_tree(
        tmp_path / "bad-declaration",
        rows=[
            {"n": 1, "ts": "2026-09-18T19:00:00Z", "event": "close", "detail": "board=closed"}
        ],
        invariants={INVARIANT_KEY: "yesterday"},
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert problems, status

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
    status, reason, problems, excused, checked = evaluate(REPO)
    for line in excused:
        print(f"  excused: {line}")
    if status == "skip":
        print(f"close-board gate: SKIPPED — {reason}")
        return 0
    if status == "fail":
        print("close-board gate failed:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    print(f"board-close gate: {checked} post-boundary close row(s) carry {BOARD_TOKEN}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
