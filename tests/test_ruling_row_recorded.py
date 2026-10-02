#!/usr/bin/env python3
"""Gate: a `ruling` row names the BOARD COMMENT it was paired with.

Origin (issue #270), ruled at ledger n=1925, dispatched at n=1927.

**The pairing has two directions and this gate is one of them.** A ruling is two acts in
two surfaces — a board comment and a ledger `ruling` row — and until #270 nothing bound
them, so they diverged: 11 instances, then 13 while the detector watched. A reader does
not prevent.

| Direction | Asked by | Where |
|---|---|---|
| a ruling comment on the board has its `ruling` row | the **board-ruling leg** in `tools/patrol_host_state.py` | LIVE — it reads the board, so it cannot live in an offline suite |
| a `ruling` row names the comment it paired with | **this gate** | OFFLINE — it reads the ledger alone |

A gate cannot call `gh`: the mechanical suite must run offline and against a tree, not a
live board. That is why the two directions sit in two places rather than one, and why
this one asserts the ROW side — the row must carry `comment=<id>`, the id of the comment
it was paired with, so the pairing is recorded on the surface that travels with the tree.

**What the rule is, in two parts.**

1. **A `ruling` row written on or after the pairing requirement carries `comment=<id>`**
   inside its canonical terminal run — the maximal run of `=`-carrying tokens at the END
   of `detail`. The token must be inside that run because that is what every
   trailer-scoped reader reads; a token buried in prose is a mention, not a declaration.
   A row without it does not say which comment it ruled with, so the ruling is
   half-recorded and no reader can pair the surfaces.
2. **A token that IS declared must be well-formed, whatever its age.** This arm is
   boundary-free: a token naming something that is not a numeric comment id, or a row
   that names a comment while resolving to no board issue, is a defect whenever it was
   written. Nothing is backfilled — a token written today for a ruling that predates the
   rule would be a falsified record, not a repair.

**The boundary is DECLARED, and this file SHIPS (issue #248).** The requirement's start
instant is a fact about THIS factory's history, and this file is paired byte-identically
with its TEMPLATE copy, so it ships to every member. A date written inside it would be
read against the MEMBER's ledger — a red in a tree the constant does not describe, which
is the worse half of the #248 class (the other half is a false clean). So the boundary
lives in `docs/ledger-invariants.json`, the factory's own declaration, read through
`tests/ledger_boundary.py` — the ONE reader of that file, shared with
`test_close_row_revision.py` so the class has one implementation. A tree that has not
declared this key SKIPS with a stated reason; a tree with no ledger skips for the same
reason (`TEMPLATE/evidence/` does not exist, because the ledger is BOOTSTRAP-created); a
declaration that is present but unreadable FAILS, because a factory that declared a
boundary and cannot be read must not be hidden behind the output of one that declared
none.

**Why the forward-only arm's population is empty today, and why that is stated rather
than implied.** Every `ruling` row written before this gate landed predates it and is
EXCUSED with its count, never folded into a bare "clean". The live run prints the whole
population, the post-requirement population and the excused population side by side, so a
zero post-requirement count reads as a zero rather than as a sweep that found nothing.
**What proves the gate bites is therefore the PROBES, not the live run** — which is
exactly the split ledger n=657 item 8 rules: population visibility is the property of the
RUN, non-vacuity is the property of the PROBE, and the loud-fail-on-zero form is right for
a gate whose population is the whole history and wrong for a forward-only gate whose
population is legitimately empty until its next instance.

The invariant is factored into `ruling_pairing_problems()` so synthetic rows can probe
it: a rule that has only ever seen good input has not been shown to reject bad input.

Run:  python3 -m pytest tests/test_ruling_row_recorded.py -q
Exit: 0 clean, fully excused, or skipped-with-reason; non-zero on any post-requirement
      ruling row without the token, or on a declaration this tree cannot honour.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ledger_boundary import (  # noqa: E402
    GateError,
    SkipGate,
    boundary_and_rows,
    module_skip,
    parse_ts,
    population_skip_reason,
    post_boundary_rows,
    synthetic_tree,
)

REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "evidence" / "ledger.jsonl"
PATROL = REPO / "tools" / "patrol_host_state.py"
FIELD_PREDICATE = REPO / "tools" / "field_predicate.py"
RULE_TOOL = REPO / "tools" / "rule.py"

# BOTH INVOCATION MODES MUST REACH THE GUARD (#199). The audit invokes this gate in pytest
# mode and pytest never calls `main()`, so a guard there protects only the script-mode run.
# `pytestmark` COLLECTS the tests and skips them (exit 0); a module-level `pytest.skip`
# would exit 5, which the audit reads as a failure.
# STATED SKIP: evidence/ledger.jsonl (BOOTSTRAP-created, step 4b)
_SKIP_REASON = module_skip(REPO)
if _SKIP_REASON:
    pytestmark = pytest.mark.skipif(True, reason=_SKIP_REASON)

# The key this gate's boundary is declared under, in the factory's own
# `docs/ledger-invariants.json`. The key is the gate's own name, so the declaration says
# which invariant each date belongs to (#248, the shape `test_close_row_revision.py` uses).
INVARIANT_KEY = "ruling_row_recorded"

# The trailer key naming the paired board comment. Same key `tools/rule.py` writes.
PAIRING_KEY = "comment"


def _load(name: str, path: Path):
    """Load a sibling module BY PATH.

    By path rather than by import: this file is vendored into factories where the layout
    above it differs, which is the reason `tools/patrol_host_state.py` loads its own
    siblings this way (#171).
    """
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _resolver():
    """The live leg's OWN `resolve_ruling_issue`, wrapped as `(row, rows) -> (issue, arm)`.

    ONE PREDICATE, TWO CALL SITES. What a ruling row's subject MEANS is decided in
    `tools/patrol_host_state.py` and nowhere else; a private parse here would let a row
    pair in this gate and not in the leg — two answers to one question, which is the
    defect section 11 names rather than a style preference.
    """
    module = _load("_pairing_patrol", PATROL)
    predicate = module.load_predicate()
    return lambda row, rows: module.resolve_ruling_issue(row, rows, predicate)


def _declared_pairing(detail: str, fp) -> str | None:
    """The `comment=` value inside the detail's canonical terminal run, else None."""
    for token in fp.trailer_tokens(detail):
        value = fp.keyed_value(token, PAIRING_KEY)
        if value:
            return value
    return None


def ruling_pairing_problems(
    rows: list[dict],
    boundary_text: str,
    *,
    resolve=None,
    fp=None,
) -> tuple[list[str], list[str]]:
    """Return `(problems, excused)` for the `ruling` rows of a ledger.

    `problems` names every post-requirement row that does not pair, plus every row whose
    declared pairing is malformed or unresolvable whatever its age; `excused` names the
    rows that predate the requirement, so the two are never conflated.

    `boundary_text` is the DECLARED instant verbatim, so an excused line quotes the date
    the factory itself declared rather than one this file carries (#248).
    """
    fp = fp or _load("_pairing_field_predicate", FIELD_PREDICATE)
    boundary = parse_ts(boundary_text)
    problems: list[str] = []
    excused: list[str] = []

    for row in rows:
        if row.get("event") != "ruling":
            continue
        n, ts = row.get("n"), row.get("ts", "")
        try:
            when = parse_ts(ts)
        except (ValueError, TypeError):
            problems.append(
                f"n={n}: unparseable ts {ts!r} — a row that cannot be dated cannot be "
                f"excused by its date either"
            )
            continue

        declared = _declared_pairing(str(row.get("detail") or ""), fp)

        # ARM 2 — boundary-free. A pairing that IS declared must be well-formed.
        if declared is not None:
            if not declared.isdigit():
                problems.append(
                    f"n={n} ({ts}) declares {PAIRING_KEY}={declared!r}, which is not a "
                    f"numeric comment id — a pairing token that names nothing pairs nothing"
                )
                continue
            if resolve is not None:
                issue, arm = resolve(row, rows)
                if issue is None:
                    problems.append(
                        f"n={n} ({ts}) names comment {declared} but its subject resolves to "
                        f"no board issue (arm={arm!r}) — the row points at a comment on a "
                        f"board item it cannot name"
                    )
                    continue

        if when < boundary:
            excused.append(f"n={n} ({ts}) predates the pairing requirement ({boundary_text})")
            continue

        # ARM 1 — forward-only. At or after the requirement, the token is required.
        if declared is None:
            problems.append(
                f"n={n} ({ts}) carries no `{PAIRING_KEY}=<id>` in its canonical trailer — "
                f"the row does not name the board comment it ruled with, so the ruling is "
                f"half-recorded and no reader can pair the two surfaces. Stamp it with "
                f"`tools/rule.py`, which writes both in one invocation"
            )

    return problems, excused


def evaluate(repo: Path) -> tuple[str, str, list[str], list[str], int, int]:
    """`(status, reason, problems, excused, rulings, post)` over `repo` — the core.

    `status` is `"pass"`, `"skip"` or `"fail"`. A real problem always outranks a skip: the
    population guard runs only on an otherwise-clean ledger, so a defect is never hidden
    behind "there was nothing to judge". `rulings` and `post` are the whole population and
    the forward-only population, carried out so the live run can PRINT them.
    """
    try:
        boundary, boundary_text, rows = boundary_and_rows(repo, INVARIANT_KEY)
    except SkipGate as exc:
        return "skip", str(exc), [], [], 0, 0
    except GateError as exc:
        return "fail", "", list(exc.problems), [], 0, 0

    problems, excused = ruling_pairing_problems(rows, boundary_text, resolve=_resolver())
    rulings = [r for r in rows if r.get("event") == "ruling"]
    post = post_boundary_rows(rows, boundary, "ruling")

    if problems:
        return "fail", "", problems, excused, len(rulings), len(post)

    # A forward-only gate whose population is legitimately empty says so (#78 clause c):
    # the reason is PROPORTIONAL, never a floor, and it is a STATED skip rather than the
    # verdict of a run that examined the population and found it clean.
    reason = population_skip_reason(post, boundary_text, "ruling")
    if reason:
        return "skip", reason, [], excused, len(rulings), len(post)

    return "pass", "", [], excused, len(rulings), len(post)


def _population_line(rulings: int, post: int, excused: list[str]) -> str:
    """The one aggregate line stating the whole / forward-only / excused populations."""
    span = ""
    if excused:
        numbers = [line.split(" ")[0].removeprefix("n=") for line in excused]
        span = f" (n={numbers[0]}..n={numbers[-1]})"
    return (
        f"ruling-pairing gate: {rulings} ruling row(s) examined, {post} at or after the "
        f"pairing requirement, {len(excused)} excused (pre-requirement){span}. The "
        f"forward-only arm's population is stated rather than implied: at zero it reads as "
        f"a zero, never as a clean sweep — the probes below are what prove the predicate "
        f"bites."
    )


# --- live gate -------------------------------------------------------------------


def test_live_ledger_pairs_every_ruling_row() -> None:
    status, reason, problems, excused, rulings, post = evaluate(REPO)
    # The excused population is stated as ONE aggregate line with its count, its boundary
    # and its `n` range: one identical per-row line each would bury the signal the count is
    # there to carry. An exclusion that is not printed is indistinguishable from a miss; an
    # exclusion printed once per row is indistinguishable from noise. It is printed for
    # EVERY verdict, so a skip never reads as a run that examined nothing.
    print(_population_line(rulings, post, excused))
    if status == "fail":
        raise AssertionError(
            "ruling rows at or after the pairing requirement must carry "
            f"{PAIRING_KEY}=<id>, and a declared pairing must be well-formed:\n  "
            + "\n  ".join(problems)
        )
    if status == "skip":
        pytest.skip(reason)


# --- probes: the predicate must reject bad input, not only accept good ----------------

_BOUNDARY = "2026-10-02T16:00:00Z"  # the declared boundary the probes judge against
_POST = "2026-10-02T16:30:00Z"  # at/after the requirement
_PRE = "2026-10-02T15:00:00Z"  # before it


def _ruling(n: int, ts: str, detail: str, subject: str = "#1") -> dict:
    return {"n": n, "ts": ts, "event": "ruling", "subject": subject, "detail": detail}


def test_a_post_requirement_ruling_without_the_token_is_rejected() -> None:
    rows = [_ruling(1, _POST, "## RULED\n\nprose")]
    problems, excused = ruling_pairing_problems(
        rows, _BOUNDARY, resolve=lambda r, rs: (1, "strict")
    )
    assert problems and not excused, (problems, excused)
    assert PAIRING_KEY in problems[0]


def test_a_pre_requirement_ruling_without_the_token_is_excused_not_failed() -> None:
    rows = [_ruling(2, _PRE, "## RULED\n\nprose")]
    problems, excused = ruling_pairing_problems(
        rows, _BOUNDARY, resolve=lambda r, rs: (2, "strict")
    )
    assert not problems and excused, (problems, excused)


def test_a_token_that_is_not_a_numeric_comment_id_is_rejected() -> None:
    """A pairing token that names nothing pairs nothing — and it is rejected at any age."""
    rows = [_ruling(3, _POST, "## RULED\n\ncomment=soon")]
    problems, _excused = ruling_pairing_problems(
        rows, _BOUNDARY, resolve=lambda r, rs: (3, "strict")
    )
    assert problems, "a non-numeric pairing token was accepted"
    assert "not a numeric comment id" in problems[0]


def test_a_token_outside_the_canonical_run_does_not_count() -> None:
    """The trailer is the run of `=`-tokens at the END: prose after it terminates the run,
    so the token becomes a mention and the row reads as unpaired."""
    rows = [_ruling(4, _POST, "## RULED\n\ncomment=12345\n\nand some trailing prose")]
    problems, _excused = ruling_pairing_problems(
        rows, _BOUNDARY, resolve=lambda r, rs: (4, "strict")
    )
    assert problems, "a token terminated by trailing prose was read as a declaration"
    assert PAIRING_KEY in problems[0]


def test_a_paired_row_that_resolves_to_no_board_issue_is_rejected() -> None:
    rows = [_ruling(5, _POST, "## RULED\n\ncomment=999", subject="prose-subject")]
    problems, _excused = ruling_pairing_problems(
        rows, _BOUNDARY, resolve=lambda r, rs: (None, "unbridgeable")
    )
    assert problems, "a row naming a comment but resolving to no issue was accepted"
    assert "resolves to no board issue" in problems[0]


def test_a_well_formed_paired_row_passes() -> None:
    rows = [_ruling(6, _POST, "## RULED\n\ntext\n\ncomment=12345")]
    problems, excused = ruling_pairing_problems(
        rows, _BOUNDARY, resolve=lambda r, rs: (6, "strict")
    )
    assert not problems and not excused, (problems, excused)


def test_non_ruling_rows_are_outside_the_population() -> None:
    """Only `ruling` rows promise a pairing; a close or run row does not."""
    rows = [
        {"n": 7, "ts": _POST, "event": "close", "subject": "#7", "detail": "board=closed"},
        {"n": 8, "ts": _POST, "event": "run", "subject": "#7", "detail": "no token here"},
    ]
    problems, excused = ruling_pairing_problems(
        rows, _BOUNDARY, resolve=lambda r, rs: (7, "strict")
    )
    assert not problems and not excused, (problems, excused)


def test_an_unparseable_ts_is_a_problem_not_an_excuse() -> None:
    rows = [_ruling(9, "not-a-time", "comment=1")]
    problems, excused = ruling_pairing_problems(
        rows, _BOUNDARY, resolve=lambda r, rs: (9, "strict")
    )
    assert problems and not excused, (problems, excused)


# --- probes: the DECLARED boundary — the #248 class this gate must not carry ----------


def test_probe_a_tree_with_no_ledger_skips_with_a_stated_reason(tmp_path: Path) -> None:
    """`TEMPLATE/evidence/` does not exist — the ledger is BOOTSTRAP-created. A gate that
    RAISED here would be RED on the very tree it ships to (#78)."""
    status, reason, problems, _, _, _ = evaluate(synthetic_tree(tmp_path / "bare"))
    assert status == "skip", (status, reason, problems)
    assert "evidence/ledger.jsonl" in reason and "BOOTSTRAP" in reason, reason


def test_probe_a_tree_with_no_declared_boundary_skips_with_a_stated_reason(
    tmp_path: Path,
) -> None:
    """A factory that has not adopted the invariant has no boundary to judge against —
    a STATED skip, never a silent pass and never a foreign boundary (#248)."""
    tree = synthetic_tree(tmp_path / "undeclared", rows=[_ruling(1, _POST, "## RULED")])
    status, reason, _, _, _, _ = evaluate(tree)
    assert status == "skip", (status, reason)
    assert "ledger-invariants.json" in reason and "DECLARED factory parameter" in reason, reason


def test_probe_a_declaration_missing_this_key_skips(tmp_path: Path) -> None:
    """One declaration file serves every ledger invariant; a key a factory has not
    declared skips for that gate alone."""
    tree = synthetic_tree(
        tmp_path / "other-key",
        rows=[_ruling(1, _POST, "## RULED")],
        invariants={"score_gate_recorded": "2026-09-18T10:04:05Z"},
    )
    status, reason, _, _, _, _ = evaluate(tree)
    assert status == "skip", (status, reason)
    assert INVARIANT_KEY in reason, reason


def test_probe_a_synthetic_tree_fails_a_ruling_row_without_the_token(tmp_path: Path) -> None:
    """THE PROPERTY SURVIVES THE DECLARED FORM. Making the boundary a parameter must not
    cost the gate its teeth: a post-boundary ruling row with no token still FAILS."""
    tree = synthetic_tree(
        tmp_path / "offending",
        rows=[_ruling(1, _POST, "## RULED\n\nprose")],
        invariants={INVARIANT_KEY: _BOUNDARY},
    )
    status, _, problems, _, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert problems and PAIRING_KEY in problems[0], problems


def test_probe_a_compliant_synthetic_tree_is_not_condemned(tmp_path: Path) -> None:
    """THE POSITIVE CONTROL: the same instrument must pass a good row, or a gate that
    failed EVERYTHING would satisfy the probe above."""
    tree = synthetic_tree(
        tmp_path / "compliant",
        rows=[_ruling(1, _POST, "## RULED\n\nprose\n\ncomment=12345")],
        invariants={INVARIANT_KEY: _BOUNDARY},
    )
    status, reason, problems, _, _, _ = evaluate(tree)
    assert status == "pass", (status, reason, problems)


def test_probe_a_malformed_declaration_fails(tmp_path: Path) -> None:
    """A factory that declared a boundary the gate cannot read must not be hidden behind
    the same output as one that declared none (#248)."""
    tree = synthetic_tree(
        tmp_path / "malformed",
        rows=[_ruling(1, _POST, "## RULED\n\ncomment=12345")],
        declaration="{ this is not json",
    )
    status, _, problems, _, _, _ = evaluate(tree)
    assert status == "fail" and problems, (status, problems)
    assert "not valid JSON" in problems[0], problems


def test_probe_an_unreadable_declared_boundary_fails(tmp_path: Path) -> None:
    tree = synthetic_tree(
        tmp_path / "bad-date",
        rows=[_ruling(1, _POST, "## RULED\n\ncomment=12345")],
        invariants={INVARIANT_KEY: "yesterday"},
    )
    status, _, problems, _, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert "not a readable ISO-8601 timestamp" in problems[0], problems


def test_probe_the_population_guard_is_proportional(tmp_path: Path) -> None:
    """A forward-only gate whose post-boundary population is legitimately empty says so
    with a STATED skip, never a silent pass (#78 clause c)."""
    tree = synthetic_tree(
        tmp_path / "empty",
        rows=[_ruling(1, _PRE, "## RULED\n\nprose")],
        invariants={INVARIANT_KEY: _BOUNDARY},
    )
    status, reason, problems, excused, _, post = evaluate(tree)
    assert status == "skip", (status, reason, problems)
    assert post == 0 and excused, (post, excused)
    assert "population is empty" in reason, reason


# --- probes: the WRITER's half of the pairing ---------------------------------------


def _run_tool(body: str, tmp_path) -> subprocess.CompletedProcess:
    path = tmp_path / "body.md"
    path.write_text(body, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(RULE_TOOL), "--issue", "1", "--body-file", str(path), "--dry-run"],
        capture_output=True,
        text=True,
    )


def test_the_writer_refuses_a_body_that_does_not_open_with_the_canonical_head(tmp_path) -> None:
    """The half #270 exists for: with a tool on the path, the head is ENFORCED rather
    than merely declared. Before this, the convention had no writer to hold it."""
    proc = _run_tool("## A note, not a ruling\n\nprose\n", tmp_path)
    assert proc.returncode != 0, f"a non-canonical head was accepted\n{proc.stdout}"
    assert "## RULED" in proc.stderr, proc.stderr


def test_the_writer_accepts_a_canonical_body(tmp_path) -> None:
    """THE POSITIVE CONTROL. The refusal above is only evidence of biting if the same
    instrument can pass a good body — otherwise a tool that refused EVERYTHING would
    satisfy the negative probe."""
    proc = _run_tool("## RULED — a real ruling\n\nprose\n", tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert "DRY RUN" in proc.stdout, proc.stdout


def test_the_writer_is_registered_as_the_pairing_writer() -> None:
    """The tool and this gate must name the SAME trailer key, or the writer writes a
    token the reader does not look for — a pairing that exists and is invisible."""
    source = RULE_TOOL.read_text(encoding="utf-8")
    assert f'PAIRING_KEY = "{PAIRING_KEY}"' in source, (
        "tools/rule.py no longer declares the pairing key this gate reads"
    )


def test_gate_is_registered_in_the_audit() -> None:
    audit = (REPO / "tools" / "audit.py").read_text(encoding="utf-8")
    assert "test_ruling_row_recorded.py" in audit, (
        "gate not registered in tools/audit.py — an unregistered gate never runs (P29)"
    )


def main() -> int:
    """Script form: the same verdict, with the skip reason on STDOUT rather than in a
    pytest short summary — so a reader of the run sees WHY nothing was judged."""
    status, reason, problems, excused, rulings, post = evaluate(REPO)
    if status == "skip":
        print(f"ruling-pairing gate: SKIP — {reason}")
        return 0
    if status == "fail":
        print("ruling-pairing gate FAILED:", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        return 1
    print(_population_line(rulings, post, excused))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
