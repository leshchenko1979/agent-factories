#!/usr/bin/env python3
"""Gate: a subject that appears to name an issue IS one, or the row is invisible.

Origin (issue #80, ruled at ledger `n=538`). The ledger's `subject` field carries a
de-facto convention — an issue reference is written `#N` — and until this gate nothing
stated it and nothing validated it. Every subject-keyed predicate in the repo resolves an
issue number through one regex (`tests/test_board_intake_recorded.py`: `^#(\\d+)$`), and
`issue_reference()` returns `None` for anything that does not match. The namespace rule
then treats that row as a DESCRIPTIVE subject — a legitimate category, since
`pickaxe-attribution-trap` is a law change and not a board issue. So a row that ATTEMPTS
to name an issue but fails the predicate is not reported as malformed: it is silently
reclassified as descriptive and leaves the population of every subject-keyed predicate
without ever being reported as wrong.

`tools/ledger.py` states the same fact from the other side: "Subjects are compared as
exact strings — `#6` and `6` are different subjects, and no normalisation is applied,
because guessing at intent is how a gate starts agreeing with its author." That is why a
bare integer is not a sloppy spelling of a reference — it is a different subject, and the
row's work unit is not reachable under any predicate that keys on the reference.

Three instances, each repaired by hand and none by a gate
---------------------------------------------------------
`n=403` (hq — a descriptive stem where a reference was owed, repaired at `n=417`), `n=516`
(hq — `77`, repaired at `n=518`), `n=529` (triage — `79`, repaired at `n=533`). Each repair
was an append-only correction row: the correct remedy for the RECORD, and the whole remedy
that was applied. It is not a PREVENTION, and the class recurred twice after the first
correction was written — the second time by a lane that had already read it. By the
factory's own rule a second instance of a shape is a process defect whose remedy is a
MECHANISM, and P29 makes a requirement enforceable or dead text: §11 declared the ledger
an authoritative surface and said nothing about the form of a subject.

What fires and what does not
----------------------------
The predicate reads the FORM, and fires only where the subject is recognisably an
issue-reference ATTEMPT the strict form cannot resolve:

* `^\\d+$` — a bare integer. Names an issue to a human reader and nothing to a machine.
  FIRES.
* `^#\\s*\\d` — a reference with the hash and the digits separated, or carrying trailing
  matter the strict form cannot (`# 79`, `#79a`, `#79 - x`, `#79/`). FIRES.
* `^#\\d+$` — the strict form. Clean.
* `^#\\d+-\\S` — a clause label extending a reference (`#31-close-receipt`, `#332-D5`).
  DESCRIPTIVE, not a reference: it names a clause of a work unit, which the strict
  predicate is not meant to resolve. Clean — and these four are the calibration set.
* anything else — a descriptive stem naming the work in words
  (`pickaxe-attribution-trap`, `survey-2026-09-19`). Clean.

The clause-label arm is load-bearing, and it is why the near-miss pattern cannot be
written as the obvious `^#\\d+\\D`. That form fires on all four calibration rows, i.e. it
breaks the very namespace rule it was meant to protect: a mechanism that cannot tell a
broken reference from a clause label either misses the defect or fires on the law. The
separator carries the distinction — a hyphen followed by a label EXTENDS the reference,
any other non-digit does not. `test_probe_the_calibration_set_does_not_fire` pins it.

The number is NOT bound to this factory's board
-----------------------------------------------
A gate that read a strict `#N` and asked "does this exist on the agent-factories board?"
would false-RED on a legitimate row: `n=433` and `n=436` both cite
`leshchenko1979/opencrabs` issue 366, stated in their own detail text. The FORM is what is
codified; the repo is not constrained. So this gate performs NO board lookup, calls no
`gh` and touches no network — the same constraint `tests/test_board_intake_recorded.py`
already states for itself.

The boundary is DECLARED, and this file SHIPS
---------------------------------------------
The boundary — the instant the form became a requirement HERE — is a factory parameter,
read from `docs/ledger-invariants.json` under the `subject_form` key through the shared
`tests/ledger_boundary.py` reader (issue #78's mechanism, ruled `n=538` amendment 1). This
file carries NO inline date: landing it with its own constant would re-instantiate the
exact defect #78 removed, and would put two mechanisms on one concern. Rows before the
boundary print as `excused:` and are never backfilled — `#52` clause 1 makes the two
bare-integer rows' identity immutable once pushed, and the correction rows already
applied at `n=518` and `n=533` are the only remedy they were owed. A tree that has not
declared the key SKIPS with its reason; a declaration it cannot read is a FAILURE.

Run:  python3 -m pytest tests/test_subject_form.py -q
Exit: 0 clean, fully excused, or skipped-with-reason; non-zero on any post-boundary row
      whose subject appears to name an issue and is not one, or on a declaration this
      tree cannot honour.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ledger_boundary import (  # noqa: E402
    GateError,
    SkipGate,
    boundary_and_rows,
    parse_ts,
    population_skip_reason,
    post_boundary_rows,
    synthetic_tree,
)

REPO = Path(__file__).resolve().parent.parent

# The key this gate's boundary is declared under, in the factory's own
# `docs/ledger-invariants.json`. The key is the gate's own name with the `test_` prefix
# and `.py` suffix dropped, matching `close_row_revision` and `score_gate_recorded`.
INVARIANT_KEY = "subject_form"

# The form the law codifies, and the two ways a reference attempt misses it. Ordered as
# the predicate applies them, because the clause-label arm must be consulted before the
# near-miss arm — `^#\d+\D` would otherwise fire on the calibration set.
_STRICT = re.compile(r"^#\d+\Z")
_CLAUSE_LABEL = re.compile(r"^#\d+-\S")
_BARE_INTEGER = re.compile(r"^\d+\s*\Z")
_REFERENCE_ATTEMPT = re.compile(r"^#\s*\d")

def subject_form_problem(subject: object) -> str | None:
    """Why this subject fails the codified form, or None when it is well-formed.

    A pure function of the subject: no ledger, no tree, no clock. `None` covers BOTH the
    strict reference and the descriptive stem, because the law does not require a subject
    to name an issue — it requires a subject that NAMES one to do it in the strict form.
    The two are distinguished in the message, not in the verdict, so a reader of a failure
    knows which arm fired.
    """
    text = str(subject)
    if _BARE_INTEGER.match(text):
        return (
            f"subject {text!r} is a bare integer — it names an issue to a human reader "
            f"and nothing to a machine; the strict form is `#{text}`"
        )
    if _STRICT.match(text) or _CLAUSE_LABEL.match(text):
        return None
    if _REFERENCE_ATTEMPT.match(text):
        return (
            f"subject {text!r} is a near-miss reference — the strict form is the hash, "
            f"the digits and nothing else"
        )
    return None

def subject_form_problems(
    rows: list[dict], boundary_text: str
) -> tuple[list[str], list[str]]:
    """Return (problems, excused) for the subjects of a ledger.

    `problems` names every post-boundary row whose subject fails the form; `excused` names
    every PRE-boundary row that would have, so the two are never conflated and "clean" is
    never the same output as "excused". `boundary_text` is the DECLARED boundary verbatim,
    so an excused line quotes the date the factory declared rather than one this file
    carries.

    Every event is governed, not one kind of row: the subject form is a property of a
    subject, and a bare integer is invisible in an intake row exactly as it is in a close.
    """
    boundary = parse_ts(boundary_text)
    problems: list[str] = []
    excused: list[str] = []

    for row in rows:
        n, ts = row.get("n"), row.get("ts", "")
        try:
            when = parse_ts(ts)
        except (ValueError, TypeError):
            problems.append(f"n={n}: unparseable ts {ts!r}")
            continue
        problem = subject_form_problem(row.get("subject"))
        if problem is None:
            continue
        if when < boundary:
            excused.append(f"n={n} ({ts}) predates the declared boundary ({boundary_text})")
            continue
        problems.append(f"n={n} ({ts}) {problem}")

    return problems, excused

def evaluate(repo: Path) -> tuple[str, str, list[str], list[str], int]:
    """`(status, reason, problems, excused, checked)` over `repo` — the probe-able core.

    `status` is `"pass"`, `"skip"` or `"fail"`. A real problem always outranks a skip: the
    population guard runs only on an otherwise-clean ledger, so a defect is never hidden
    behind "there was nothing to judge".
    """
    try:
        boundary, boundary_text, rows = boundary_and_rows(repo, INVARIANT_KEY)
    except SkipGate as exc:
        return "skip", str(exc), [], [], 0
    except GateError as exc:
        return "fail", "", list(exc.problems), [], 0

    problems, excused = subject_form_problems(rows, boundary_text)
    if problems:
        return "fail", "", problems, excused, 0

    # The population is EVERY row at or after the boundary — this invariant is unscoped,
    # so the reader is asked for all events rather than for one kind of row.
    population = post_boundary_rows(rows, boundary)
    reason = population_skip_reason(population, boundary_text)
    if reason:
        return "skip", reason, [], excused, 0
    return "pass", "", [], excused, len(population)

# --- the live ledger: the boundary THIS factory declared, applied to its own rows -----

def _live_rows() -> list[dict]:
    """The live ledger's rows, or a pytest SKIP when this tree has none.

    The TEMPLATE twin resolves `REPO` to `TEMPLATE/`, whose ledger is BOOTSTRAP-created and
    therefore absent. That is #78's class (P35) — a byte-paired gate asserting a live-tree
    fact its own tree cannot satisfy — so the live probes below STATE that reason instead
    of asserting a fact their tree cannot produce.
    """
    try:
        _, _, rows = boundary_and_rows(REPO, INVARIANT_KEY)
    except (SkipGate, GateError) as exc:
        pytest.skip(f"this tree carries no live ledger to judge: {exc}")
    return rows

def _live_verdict() -> tuple[str, str, list[str], list[str], int]:
    return evaluate(REPO)

def test_live_subjects_carry_the_codified_form() -> None:
    """The live ledger against the boundary this factory declared. A `fail` here is a real
    subject-form defect in a row written on or after the boundary — not a fixture."""
    status, reason, problems, _, checked = _live_verdict()
    assert status in ("pass", "skip"), (status, reason, problems)
    if status == "pass":
        assert checked > 0, "a pass over an empty population is a silent pass"

def test_live_the_two_bare_integer_rows_are_excused_and_never_hits() -> None:
    """n=516 and n=529 PREDATE the boundary (n=538's own note on the boundary value). They
    must print as `excused:` and never as hits, and they are never backfilled: a run that
    reports them as defects has mis-set the boundary."""
    status, reason, problems, excused, _ = _live_verdict()
    if status != "pass":
        pytest.skip(f"no live population in this tree: {reason}")
    assert problems == [], problems
    named = " | ".join(excused)
    assert "n=516" in named and "n=529" in named, excused
    assert "predates the declared boundary" in named, excused

def test_live_the_four_clause_labels_never_fire() -> None:
    """Criterion 5, read from the LIVE ledger rather than from literals: the calibration
    rows are located by number and their subjects must not fire at all — not as a hit, and
    not as an excused row either, since an excused row is still a fired predicate."""
    calibration = {
        186: "#332-D5",
        187: "#332-D6-D1correction",
        188: "#31-#32-claim-gap",
        194: "#31-close-receipt",
    }
    rows = {row.get("n"): row for row in _live_rows()}
    for n, expected in calibration.items():
        assert n in rows, f"n={n} is missing from the live ledger"
        assert rows[n].get("subject") == expected, (n, rows[n].get("subject"))
        assert subject_form_problem(expected) is None, expected

    _, _, problems, excused, _ = _live_verdict()
    for n in calibration:
        marker = f"n={n} "
        assert not any(marker in line for line in problems), problems
        assert not any(marker in line for line in excused), excused

# --- probes: the predicate must reject bad input, not only accept good ----------------

_PROBE_BOUNDARY = "2026-09-19T13:07:51Z"

def _row(n: int, ts: str, subject: object, event: str = "dispatch") -> dict:
    return {"n": n, "ts": ts, "event": event, "actor": "worker", "subject": subject, "detail": "x"}

def _probe_tree(root: Path, rows: list[dict]) -> Path:
    return synthetic_tree(root, rows=rows, invariants={INVARIANT_KEY: _PROBE_BOUNDARY})

def test_probe_a_bare_integer_subject_fires_naming_the_row(tmp_path: Path) -> None:
    """Criterion 2: the report NAMES the row number, so a reader can find the row."""
    tree = _probe_tree(tmp_path / "bare", [_row(900, "2026-09-19T14:00:00Z", 79)])
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert len(problems) == 1, problems
    assert "n=900" in problems[0] and "bare integer" in problems[0], problems

def test_probe_a_tree_with_no_skills_directory_is_judged_the_same(tmp_path: Path) -> None:
    """The tree SHAPE is irrelevant to this invariant, and that is asserted rather than
    assumed. The subject form is a property of the LEDGER, so a tree carrying a root-level
    law file and no `skills/` directory at all — the layout a factory bootstrapped from
    this template has — is judged exactly like any other. A gate that found nothing here
    would report a clean run over a tree it never read, which is the failure this probe
    pins: the RED must name the offending row in that layout too."""
    tree = _probe_tree(tmp_path / "root-level-law", [_row(913, "2026-09-19T14:00:00Z", 79)])
    (tree / "SKILL.md").write_text("# law\n", encoding="utf-8")
    assert not (tree / "skills").is_dir(), "the fixture must model the layout it claims"
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert "n=913" in problems[0], problems

def test_probe_a_bare_integer_fires_in_every_event(tmp_path: Path) -> None:
    """The invariant is UNSCOPED, and this is the probe that pins it: a bare integer is
    invisible in an intake row exactly as it is in a close, so the reader is asked for
    every event rather than for one kind of row."""
    for event in ("intake", "claim", "dispatch", "close", "run", "ruling", "score"):
        tree = _probe_tree(
            tmp_path / event, [_row(901, "2026-09-19T14:00:00Z", 7, event=event)]
        )
        status, _, problems, _, _ = evaluate(tree)
        assert status == "fail", (event, status)
        assert "bare integer" in problems[0], (event, problems)

def test_probe_near_miss_references_fire() -> None:
    for subject in ("# 79", "#79a", "#79 - x", "#79/", "#\t79", "#79\n"):
        assert subject_form_problem(subject) is not None, subject

def test_probe_the_strict_form_and_descriptive_stems_are_clean() -> None:
    for subject in ("#79", "#1", "pickaxe-attribution-trap", "survey-2026-09-19", ""):
        assert subject_form_problem(subject) is None, subject

def test_probe_the_calibration_set_does_not_fire() -> None:
    """Criterion 5, and the reason the near-miss arm cannot be written as the obvious
    `^#\\d+\\D`: that form fires on all four of these, i.e. it breaks the namespace rule it
    was meant to protect. The separator carries the distinction — a hyphen followed by a
    label EXTENDS the reference, any other non-digit does not."""
    labels = ("#332-D5", "#332-D6-D1correction", "#31-#32-claim-gap", "#31-close-receipt")
    for subject in labels:
        assert subject_form_problem(subject) is None, subject
    naive = re.compile(r"^#\d+\D")
    assert all(naive.match(subject) for subject in labels), "the calibration set is inert"

def test_probe_the_predicate_is_pure_and_offline() -> None:
    """Criterion 3: no `gh`, no network, no board list. Asserted on the IMPORTS rather than
    on prose, so a later 'improvement' that adds a board lookup fails here."""
    imports = set(re.findall(r"^\s*(?:import|from)\s+([a-zA-Z0-9_.]+)", Path(__file__).read_text(encoding="utf-8"), re.M))
    banned = {"subprocess", "socket", "urllib", "urllib.request", "http", "requests"}
    assert not (imports & banned), sorted(imports & banned)
    assert subject_form_problem("#79") == subject_form_problem("#79"), "not a pure function"

def test_probe_a_pre_boundary_row_is_excused_not_a_hit(tmp_path: Path) -> None:
    tree = _probe_tree(tmp_path / "pre", [_row(902, "2026-09-19T12:00:00Z", 79)])
    status, reason, problems, excused, checked = evaluate(tree)
    assert (status, problems, checked) == ("skip", [], 0), (status, reason, problems)
    assert len(excused) == 1, excused
    assert "predates the declared boundary" in excused[0], excused
    assert _PROBE_BOUNDARY in excused[0], excused

def test_probe_the_boundary_comes_from_the_declaration_not_this_file(tmp_path: Path) -> None:
    """The date is READ. The same row is post-boundary under one declaration and
    pre-boundary under another, and this file carries neither."""
    row = _row(903, "2026-09-19T14:00:00Z", 79)
    early = synthetic_tree(
        tmp_path / "early", rows=[row], invariants={INVARIANT_KEY: "2026-09-19T15:00:00Z"}
    )
    late = synthetic_tree(
        tmp_path / "late", rows=[row], invariants={INVARIANT_KEY: "2026-09-19T13:00:00Z"}
    )
    assert evaluate(early)[0] == "skip", "the declared boundary was not applied"
    assert evaluate(late)[0] == "fail", "the declared boundary was not applied"

def test_probe_a_tree_with_no_ledger_skips_with_a_stated_reason(tmp_path: Path) -> None:
    status, reason, _, _, _ = evaluate(synthetic_tree(tmp_path / "bare"))
    assert status == "skip" and "no evidence/ledger.jsonl" in reason, (status, reason)

def test_probe_a_tree_with_no_declaration_skips_with_a_stated_reason(tmp_path: Path) -> None:
    tree = synthetic_tree(tmp_path / "undeclared", rows=[_row(904, "2026-09-19T14:00:00Z", "#79")])
    status, reason, _, _, _ = evaluate(tree)
    assert status == "skip", (status, reason)
    assert "ledger-invariants.json" in reason, reason
    assert "DECLARED factory parameter" in reason, reason

def test_probe_a_declaration_missing_this_key_skips(tmp_path: Path) -> None:
    """One declaration file serves every ledger invariant; a key a factory has not
    declared skips for that gate alone."""
    tree = synthetic_tree(
        tmp_path / "other-key",
        rows=[_row(905, "2026-09-19T14:00:00Z", "#79")],
        invariants={"close_row_revision": "2026-09-19T05:05:49Z"},
    )
    status, reason, _, _, _ = evaluate(tree)
    assert status == "skip" and INVARIANT_KEY in reason, (status, reason)

def test_probe_an_empty_ledger_skips(tmp_path: Path) -> None:
    tree = synthetic_tree(tmp_path / "empty", rows=[], invariants={INVARIANT_KEY: _PROBE_BOUNDARY})
    status, reason, _, _, _ = evaluate(tree)
    assert status == "skip" and "carries no rows" in reason, (status, reason)

def test_probe_an_empty_population_skips_rather_than_passing(tmp_path: Path) -> None:
    """The population guard is PROPORTIONAL: a factory whose history predates the boundary
    skips with its reason instead of passing vacuously. The row carries a FIRING subject so
    the excused set is non-empty — an excused row is still a fired predicate, and that is
    what makes "clean" and "excused" different output rather than the same one."""
    tree = _probe_tree(tmp_path / "young", [_row(906, "2026-09-19T12:00:00Z", 79)])
    status, reason, problems, excused, checked = evaluate(tree)
    assert (status, problems, checked) == ("skip", [], 0), (status, reason, problems)
    assert "population is empty" in reason, reason
    assert len(excused) == 1, excused

def test_probe_the_cross_repo_fact_is_accepted_on_form_alone(tmp_path: Path) -> None:
    """Criterion 8, calibrated on n=433/n=436: both rows cite `leshchenko1979/opencrabs`
    issue 366, a number that is NOT on this factory's board. The strict form is accepted on
    FORM alone, so the gate must be clean on such a subject — a gate that asked 'does this
    exist here?' would false-RED on a legitimate row. The probe is a TREE, so the verdict is
    produced with no board reachable at all: if the predicate needed one it could not pass.
    """
    assert subject_form_problem("#366") is None
    tree = _probe_tree(tmp_path / "cross-repo", [_row(912, "2026-09-19T14:00:00Z", "#366")])
    status, reason, problems, _, checked = evaluate(tree)
    assert (status, problems, checked) == ("pass", [], 1), (status, reason, problems)

def test_live_the_cross_repo_rows_carry_the_strict_form() -> None:
    """The live calibration for criterion 8: n=433 and n=436 exist, carry the strict form,
    and are clean — so the form-only rule is exercised against the real rows that motivated
    it, not only against a fixture."""
    rows = {row.get("n"): row for row in _live_rows()}
    for n in (433, 436):
        assert n in rows, f"n={n} is missing from the live ledger"
        assert rows[n].get("subject") == "#366", (n, rows[n].get("subject"))
        assert subject_form_problem(rows[n].get("subject")) is None, n

def test_probe_a_defect_is_never_hidden_behind_a_skip(tmp_path: Path) -> None:
    """A row that cannot be DATED is a problem, and it must not be laundered into a stated
    skip: the population guard runs only on an otherwise-clean ledger."""
    tree = _probe_tree(
        tmp_path / "undated", [{"n": 907, "ts": "not-a-timestamp", "event": "dispatch", "subject": "#79"}]
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert "unparseable ts" in problems[0], problems

def test_probe_a_malformed_declaration_fails_rather_than_raising(tmp_path: Path) -> None:
    """A declared parameter that cannot be read is a DEFECT, not an absence: skipping it
    would hide a broken declaration behind the same output as no declaration at all."""
    tree = synthetic_tree(
        tmp_path / "malformed",
        rows=[_row(908, "2026-09-19T14:00:00Z", "#79")],
        declaration="{ this is not json",
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail" and problems, (status, problems)
    assert "not valid JSON" in problems[0], problems

def test_probe_an_unreadable_declared_boundary_fails(tmp_path: Path) -> None:
    tree = synthetic_tree(
        tmp_path / "bad-date",
        rows=[_row(909, "2026-09-19T14:00:00Z", "#79")],
        invariants={INVARIANT_KEY: "yesterday"},
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert "not a readable ISO-8601 timestamp" in problems[0], problems

def test_probe_a_corrupt_ledger_line_fails_rather_than_raising(tmp_path: Path) -> None:
    tree = synthetic_tree(tmp_path / "corrupt", invariants={INVARIANT_KEY: _PROBE_BOUNDARY})
    (tree / "evidence/ledger.jsonl").write_text('{"n": 1}\nnot a row\n', encoding="utf-8")
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert "is not a JSON row" in problems[0], problems

def test_probe_the_population_guard_is_proportional() -> None:
    assert population_skip_reason([], _PROBE_BOUNDARY) is not None
    assert population_skip_reason([{"n": 1}], _PROBE_BOUNDARY) is None
    reason = population_skip_reason([], _PROBE_BOUNDARY) or ""
    assert "`close`" not in reason, "the unscoped reason must not claim an event scope"

def test_probe_the_script_form_prints_its_population(tmp_path: Path, capsys) -> None:
    """Criterion 1: a clean run and a run that examined nothing are never the same output —
    the script states the rows EXAMINED, the HITS and the EXCUSED set separately."""
    tree = _probe_tree(
        tmp_path / "printed",
        [_row(910, "2026-09-19T12:00:00Z", 79), _row(911, "2026-09-19T14:00:00Z", "#79")],
    )
    assert main(tree) == 0
    out = capsys.readouterr().out
    assert "excused: n=910" in out, out
    assert "1 post-boundary row(s) examined" in out, out
    assert "0 hit(s)" in out, out

def main(repo: Path = REPO) -> int:
    """Script form: the same verdict, with the population and the excused set on STDOUT.

    Criterion 1 of issue #80: a clean run prints the rows EXAMINED, the HITS and the
    EXCUSED set separately, so a clean run and a run that examined nothing are never the
    same output. `repo` is a parameter so a probe can exercise the printed form against a
    synthetic tree — the TEMPLATE twin has no ledger of its own to print.
    """
    status, reason, problems, excused, checked = evaluate(repo)
    for line in excused:
        print(f"  excused: {line}")
    if status == "skip":
        print(f"subject-form gate: SKIP — {reason}")
        return 0
    if status == "fail":
        print("subject-form gate FAILED:", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        return 1
    print(
        f"subject-form gate: clean — {checked} post-boundary row(s) examined, "
        f"{len(problems)} hit(s), {len(excused)} excused (pre-boundary)"
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
