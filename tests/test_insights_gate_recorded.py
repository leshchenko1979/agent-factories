#!/usr/bin/env python3
"""Gate: a weekly insights synthesis run records its closing workspace-gate verdict.

Origin (issue #46). Process 3 (`docs/processes.md`) declares TWO artifacts as its output
contract: `evidence/scores/<date>.md` AND `evidence/insights.jsonl`. #32 gave the score
file a closing invariant; the insights half had none, and no procedure at all — so on
2026-09-18 the synthesis run appended insight #22, wrote its own `run` row carrying
`audit=DEGRADED-hygiene-modified-tracked-files`, and ended with the artifact uncommitted
for over two hours. The run RECORDED the dirty tree and reported anyway, which is the exact
shape #32 closed for the score file, one artifact over.

The rule is the score gate's rule applied to the other artifact, so the VOCABULARY is the
same two tokens — one vocabulary, two populations, nothing new to read:

1. **Every governed run row carries the closing verdict** — `workspace_gate=rc=0` — and the
   HEAD sha the run committed at (`head=<sha>`). A run that skipped the gate leaves no
   verdict, so the absence is the signal; the sha makes the row checkable against the
   repository rather than a claim about a tree that has since moved.
2. **Rows written before the invariant are excused, and said so**, with their count, never
   folded into a bare "clean". Nothing is backfilled: a verdict written today for a run that
   predates the rule would be a falsified record, not a repair.

THE POPULATION IS AN ACT, and it is scoped twice because one scope is not enough:
`event == "run"` (the ledger's own vocabulary) AND a subject naming this pacemaker's duty
(`subject_in_scope`, below). The subject is `<stem>-<round>` — the DATED duty-receipt form
the pacemaker writes today — where `<stem>` is the job's own declared `receipt_subject`
(SKILL.md section 11, the clause landed at n=1052) and `<round>` is its UTC date. That
declaration lives in the pacemaker's own cron prompt, a surface this gate does not read, so
the stem is RESTATED here as a LANE-LOCAL constant, not a schema name like `score` — the
same shape as the bare job name this file carried before, and the same shape as this
factory's entry in `tests/test_telemetry_reader_registry.py`'s `WRITER_MODULES` — and a
factory that names its pacemaker differently edits this one constant in its OWN copy. THE
BOUND, stated rather than left to be discovered: in such a factory this gate finds no
governed row and SKIPS with its reason, so it is useful exactly where the subject matches
and honestly silent where it does not — never a silent pass, because a skip prints why it
examined nothing.

THE KEY IS A BOUNDARY-CHECKED PREFIX, not equality. Equality was this gate's first key, and
it could not match what the writer writes: the pacemaker moved to dated duty receipts
(#159's convention, one surface over), so an exact key on the old name left the population
empty BY CONSTRUCTION and the gate SKIPPED the round it exists to judge. The guard keeps the
widening honest in two parts: the stem alone would admit `insights-and-growth-map` — a real
subject in this ledger (n=36), a different thing entirely — so the form is `<stem>-<date>`;
and the character after the date must not be a digit, because a date that merely extends
this one's digits (`...-2026-09-250`) is a DIFFERENT date. A round-key variant of the SAME
round (`T06`, `-writeback`, or nothing) is admitted, which is what the prefix is for. The
pre-convention name stays in scope so the pre-boundary history keeps printing as excused.

The boundary is DECLARED, and this file SHIPS
---------------------------------------------
The boundary is a DECLARED factory parameter, read from the factory's own
`docs/ledger-invariants.json` through `tests/ledger_boundary.py` — the ONE reader, shared
with `test_close_row_revision.py` and `test_score_gate_recorded.py` so the class has ONE
implementation (#78, ruled `n=515` clause 4). A hardcoded date here would be this factory's
history baked into a file that ships to every new factory: RED, or vacuously green, on the
very tree it ships to (P35). A tree that has not declared a boundary SKIPS with a stated
reason; a declaration it cannot read FAILS, because a declared parameter that cannot be read
is a defect, not an absence.

Three outcomes, and the difference between them is the point:

* **skip** — this tree legitimately has nothing to judge: no ledger, an empty ledger, no
  declaration, no declared boundary, or no governed run row at or after it. Printed as
  `SKIP: <reason>`, exit 0, the reason stated. The population here is FORWARD-ONLY and is
  legitimately empty until the next synthesis run, so the non-vacuity proof is the PROBES
  below rather than a live count — the guard #112 (`n=657` item 8) states for exactly this
  shape, and the reason the loud-fail-on-zero form of `tests/test_ledger_no_shrink.py` is
  NOT copied here.
* **fail** — a governed run row missing part of the verdict, or a declaration this tree
  cannot honour (malformed JSON, an unreadable date, a corrupt ledger line).
* **pass** — a non-empty population, every row carrying both halves of the verdict.

The tokens are read through the SHARED predicate `tools/field_predicate.py::keyed_value`,
not a substring test, so a row that merely NAMES a field cannot satisfy it: `workspace_gate=`
is a mention carrying no value, and prose about the rule is not a record of it. The scan
continues past an unreadable `head=` token rather than stopping at the first one, the shape
`tools/field_predicate.py::declared_revision` and `test_score_gate_recorded.py::_has_head_sha`
both use — a row that DESCRIBES the field before naming its revision does declare one.
(`test_close_row_revision.py` carried its own copy of that reader until #190 removed it,
because one field judged by two predicates was the defect #190 exists to close.)

The invariant is factored into `run_verdict_problems()` so synthetic rows can probe it: a
rule that has only ever seen good input has not been shown to reject bad input.

Run:  python3 -m pytest tests/test_insights_gate_recorded.py -q
Exit: 0 clean, fully excused, or skipped-with-reason; non-zero on any governed row written
      at or after the declared boundary without a verdict.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import re
import sys

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

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from field_predicate import keyed_value  # noqa: E402

REPO = Path(__file__).resolve().parent.parent

# The key this gate's boundary is declared under, in the factory's own
# `docs/ledger-invariants.json`: the key IS the gate's name, so the declaration says which
# invariant each date belongs to.
INVARIANT_KEY = "insights_gate_recorded"

# The ACT this gate governs: a `run` row written by the insights synthesis pacemaker.
RUN_EVENT = "run"

# The subject the pacemaker WRITES today: `<stem>-<round>`, where `<stem>` is the job's own
# declared `receipt_subject` (SKILL.md section 11, the clause landed at n=1052) and
# `<round>` is its UTC date. That declaration lives in the pacemaker's own cron prompt — a
# surface this gate does not read — so the stem is RESTATED here as a lane-local constant,
# the same shape as the bare job name this file carried before.
SUBJECT_STEM = "insights"

# The subject it wrote BEFORE that convention moved: its bare job name. Kept in scope so
# the pre-boundary history still prints as `excused:` rather than vanishing from the output
# when the scope is re-keyed — the boundary reader's contract is that rows before the
# boundary PRINT as excused on every run, and re-keying the scope must not quietly delete
# the history it was printing.
LEGACY_SUBJECT = "weekly-insight-synthesis-pacemaker"

# The round is a UTC DATE, so the stem alone is not a key: this ledger carries
# `insights-and-growth-map` (n=36, HQ's initialization row), which shares the stem's
# characters without naming a round. Requiring a date is what separates them.
_ROUND_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def subject_in_scope(subject: str) -> bool:
    """True when `subject` names this pacemaker's duty — its dated form, or its old name.

    THE KEY IS A BOUNDARY-CHECKED PREFIX, not equality (#159's shape, one surface over).
    Equality was this gate's first key and it could not match what the writer writes: the
    pacemaker moved to dated duty receipts, so an exact key on the old name left the
    population empty BY CONSTRUCTION and the gate SKIPPED the round it exists to judge.

    THE GUARD is what keeps the widening honest, in two parts. A bare
    `startswith(f"{SUBJECT_STEM}-")` would admit `insights-and-growth-map`, a real subject
    in this ledger and a different thing entirely — so the form is `<stem>-<date>`. And the
    character after the date must not be a digit, because a date that merely EXTENDS this
    one's digits (`...-2026-09-250`) is a DIFFERENT date, not this round. Any other
    continuation is a round-key variant of the same round (`T06`, `-writeback`, or
    nothing), which is exactly what the prefix is for.
    """
    s = str(subject or "")
    if s == LEGACY_SUBJECT:
        return True
    prefix = f"{SUBJECT_STEM}-"
    if not s.startswith(prefix):
        return False
    rest = s[len(prefix):]
    match = _ROUND_RE.match(rest)
    if match is None:
        return False
    return not rest[match.end():match.end() + 1].isdigit()

# The closing verdict, in the score gate's own vocabulary — one vocabulary, two gates.
VERDICT_FIELD = "workspace_gate"
VERDICT_KEY = f"{VERDICT_FIELD}=rc=0"
HEAD_FIELD = "head"
_MIN_SHA = 7
_HEX = set("0123456789abcdef")

def _tokens(detail: str) -> list[str]:
    return str(detail).replace(",", " ").replace(";", " ").split()

def declared_verdict(detail: str) -> str | None:
    """The `workspace_gate=<value>` value, or None when no token DECLARES the field.

    `keyed_value` is the declaration test: the key, then `=`, then a NON-EMPTY value. A
    token that merely names the field (`workspace_gate=` in a sentence about the rule) is a
    mention and yields nothing — which is the difference between a row that RECORDS the
    verdict and one that talks about recording it.
    """
    for token in _tokens(detail):
        value = keyed_value(token, VERDICT_FIELD)
        if value is not None:
            return value
    return None

def declared_head(detail: str) -> str | None:
    """The `head=<sha>` value, or None when no readable field is present.

    The value must be hex of at least `_MIN_SHA` chars: a row that says `head=<sha>` — the
    literal placeholder — has declared a field whose value is not a revision. The scan
    CONTINUES past an unreadable token rather than stopping at it, so a row that names the
    field in prose before carrying the real revision is not falsely refused.
    """
    for token in _tokens(detail):
        value = keyed_value(token, HEAD_FIELD)
        if value is None:
            continue
        sha = value.strip(").`")
        if len(sha) >= _MIN_SHA and all(c in _HEX for c in sha):
            return sha
    return None

def run_verdict_problems(
    rows: list[dict], boundary_text: str
) -> tuple[list[str], list[str]]:
    """Return (problems, excused) for the governed `run` rows of a ledger.

    `problems` names every post-boundary run row missing part of the verdict; `excused`
    names every pre-boundary one, so the two are never conflated. `boundary_text` is the
    DECLARED boundary verbatim, so an excused line quotes the date the factory declared
    rather than one this file carries.
    """
    boundary = parse_ts(boundary_text)
    problems: list[str] = []
    excused: list[str] = []

    for row in rows:
        if row.get("event") != RUN_EVENT or not subject_in_scope(row.get("subject")):
            continue
        n, ts = row.get("n"), row.get("ts", "")
        try:
            when = parse_ts(ts)
        except (ValueError, TypeError):
            problems.append(f"n={n}: unparseable ts {ts!r}")
            continue
        if when < boundary:
            excused.append(f"n={n} ({ts}) predates the declared boundary ({boundary_text})")
            continue
        detail = str(row.get("detail") or "")
        missing: list[str] = []
        verdict = declared_verdict(detail)
        if verdict is None:
            missing.append(VERDICT_KEY)
        elif verdict != "rc=0":
            missing.append(f"{VERDICT_FIELD}={verdict} (the run recorded a FAILING gate)")
        if declared_head(detail) is None:
            missing.append("head=<sha>")
        if missing:
            problems.append(f"n={n} ({ts}) {' and '.join(missing)}")

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

    problems, excused = run_verdict_problems(rows, boundary_text)
    if problems:
        return "fail", "", problems, excused, 0

    population = [
        row
        for row in post_boundary_rows(rows, boundary, RUN_EVENT)
        if subject_in_scope(row.get("subject"))
    ]
    reason = population_skip_reason(population, boundary_text, RUN_EVENT)
    if reason:
        # The shared guard's sentence names the event scope; the subject scope is this
        # gate's own, and an unstated scope reads as a narrower population than the one
        # that was measured.
        scope = f"{SUBJECT_STEM!r}-<round> or the legacy {LEGACY_SUBJECT!r}"
        return "skip", f"{reason} (scoped to subject {scope})", [], excused, 0
    return "pass", "", [], excused, len(population)

# --- live gate -------------------------------------------------------------------

def test_live_ledger_records_the_closing_verdict() -> None:
    status, reason, problems, excused, checked = evaluate(REPO)
    for line in excused:
        print(f"  excused: {line}")
    if status == "skip":
        print(f"  SKIP: {reason}")
        pytest.skip(reason)
    if status == "fail":
        raise AssertionError(
            "insight synthesis run rows written after the declared boundary must carry "
            "the workspace-gate verdict and the committed HEAD sha:\n  "
            + "\n  ".join(problems)
        )
    print(
        f"insights-gate verdict gate: {checked} post-boundary insights run row(s) "
        f"verified, {len(excused)} excused (pre-boundary)"
    )

# --- probes: the tree the gate runs in, then the predicate it applies --------------

def _run(n: int, ts: str, detail: str, subject: str = f"{SUBJECT_STEM}-2026-09-22") -> dict:
    return {
        "n": n,
        "ts": ts,
        "event": RUN_EVENT,
        "actor": "surveys",
        "subject": subject,
        "detail": detail,
    }

_OK = {
    "n": 900,
    "ts": "2026-09-22T18:00:00Z",
    "event": RUN_EVENT,
    "actor": "surveys",
    "subject": f"{SUBJECT_STEM}-2026-09-22",
    "detail": "insight_appended=23-some-insight — workspace_gate=rc=0 "
    "head=deadbeef985b0f1a6c8919c362a0a56ec7d0d42e",
}

_PROBE_BOUNDARY = "2026-09-21T00:00:00Z"

def test_probe_a_tree_with_no_ledger_skips_with_a_stated_reason(tmp_path: Path) -> None:
    """`TEMPLATE/evidence/` does not exist — the ledger is BOOTSTRAP-created. A gate that
    RAISED here was RED on the very tree it ships to (#78, #76's class)."""
    status, reason, problems, _, _ = evaluate(synthetic_tree(tmp_path / "bare"))
    assert status == "skip", (status, reason, problems)
    assert "evidence/ledger.jsonl" in reason and "BOOTSTRAP" in reason, reason

def test_probe_a_tree_with_no_declared_boundary_skips_with_a_stated_reason(
    tmp_path: Path,
) -> None:
    """A factory that has not adopted the invariant has no boundary to judge against —
    and that is a STATED skip, never a silent pass and never a foreign boundary."""
    tree = synthetic_tree(
        tmp_path / "undeclared", rows=[_run(1, "2026-09-22T18:00:00Z", "insight_appended=1")]
    )
    status, reason, _, _, _ = evaluate(tree)
    assert status == "skip", (status, reason)
    assert "ledger-invariants.json" in reason and "DECLARED factory parameter" in reason, reason

def test_probe_a_synthetic_tree_fails_a_row_without_the_verdict(tmp_path: Path) -> None:
    """THE PROPERTY SURVIVES THE DECLARED FORM. Making the boundary a parameter must not
    cost the gate its teeth: a governed post-boundary row with no verdict still FAILS."""
    tree = synthetic_tree(
        tmp_path / "offending",
        rows=[_run(1, "2026-09-22T18:00:00Z", "insight_appended=23 — head=deadbeef985b")],
        invariants={INVARIANT_KEY: _PROBE_BOUNDARY},
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert problems and VERDICT_KEY in problems[0], problems

def test_probe_a_compliant_synthetic_tree_passes(tmp_path: Path) -> None:
    tree = synthetic_tree(
        tmp_path / "compliant",
        rows=[_OK],
        invariants={INVARIANT_KEY: _PROBE_BOUNDARY},
    )
    status, reason, problems, _, checked = evaluate(tree)
    assert (status, problems) == ("pass", []), (status, reason, problems)
    assert checked == 1, checked

def test_probe_the_boundary_comes_from_the_declaration_not_this_file(
    tmp_path: Path,
) -> None:
    """The date is READ. The same row is post-boundary under one declaration and
    pre-boundary under another, and this file carries neither."""
    row = _run(1, "2026-09-22T18:00:00Z", "insight_appended=23")
    early = synthetic_tree(
        tmp_path / "early", rows=[row], invariants={INVARIANT_KEY: _PROBE_BOUNDARY}
    )
    late = synthetic_tree(
        tmp_path / "late", rows=[row], invariants={INVARIANT_KEY: "2026-09-23T00:00:00Z"}
    )
    assert evaluate(early)[0] == "fail", "the declared boundary was not applied"
    status, _, problems, excused, _ = evaluate(late)
    assert (status, problems) == ("skip", []), (status, problems)
    assert excused and "2026-09-23T00:00:00Z" in excused[0], excused

def test_probe_an_empty_population_skips_rather_than_passing(tmp_path: Path) -> None:
    """PROPORTIONAL: a young factory whose history predates the boundary — or which has
    never run the synthesis — skips with its reason instead of passing vacuously."""
    tree = synthetic_tree(
        tmp_path / "young",
        rows=[_run(1, "2026-09-20T18:00:00Z", "insight_appended=20")],
        invariants={INVARIANT_KEY: _PROBE_BOUNDARY},
    )
    status, reason, problems, excused, checked = evaluate(tree)
    assert (status, problems, checked) == ("skip", [], 0), (status, reason, problems)
    assert "population is empty" in reason, reason
    assert SUBJECT_STEM in reason and LEGACY_SUBJECT in reason, reason
    assert len(excused) == 1, excused

def test_probe_an_empty_ledger_skips(tmp_path: Path) -> None:
    tree = synthetic_tree(
        tmp_path / "empty-ledger", rows=[], invariants={INVARIANT_KEY: _PROBE_BOUNDARY}
    )
    status, reason, _, _, _ = evaluate(tree)
    assert status == "skip" and "carries no rows" in reason, (status, reason)

def test_probe_a_malformed_declaration_fails_rather_than_raising(tmp_path: Path) -> None:
    """A declared parameter that cannot be read is a DEFECT, not an absence: skipping it
    would hide a broken declaration behind the same output as no declaration."""
    tree = synthetic_tree(
        tmp_path / "malformed",
        rows=[_OK],
        declaration="{ this is not json",
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail" and problems, (status, problems)
    assert "not valid JSON" in problems[0], problems

def test_probe_an_unreadable_declared_boundary_fails(tmp_path: Path) -> None:
    tree = synthetic_tree(
        tmp_path / "bad-date",
        rows=[_OK],
        invariants={INVARIANT_KEY: "yesterday"},
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert "not a readable ISO-8601 timestamp" in problems[0], problems

def test_probe_a_corrupt_ledger_line_fails_rather_than_raising(tmp_path: Path) -> None:
    tree = synthetic_tree(
        tmp_path / "corrupt", invariants={INVARIANT_KEY: _PROBE_BOUNDARY}
    )
    (tree / "evidence/ledger.jsonl").write_text('{"n": 1}\nnot a row\n', encoding="utf-8")
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert "is not a JSON row" in problems[0], problems

# --- probes: the invariant must reject bad input, not only accept good ------------

def test_probe_accepts_a_compliant_row() -> None:
    problems, excused = run_verdict_problems([_OK], _PROBE_BOUNDARY)
    assert problems == [] and excused == []

def test_probe_rejects_a_row_without_the_verdict() -> None:
    row = {**_OK, "detail": "insight_appended=23 — head=deadbeef985b0f1a6c8919c362a0a56ec7d0d42e"}
    problems, _ = run_verdict_problems([row], _PROBE_BOUNDARY)
    assert problems and VERDICT_KEY in problems[0], problems

def test_probe_rejects_a_failing_verdict() -> None:
    row = {**_OK, "detail": "insight_appended=23 — workspace_gate=rc=1 head=deadbeef985b"}
    problems, _ = run_verdict_problems([row], _PROBE_BOUNDARY)
    assert problems, "a failing workspace gate must not read as a recorded pass"
    assert "rc=1" in problems[0], problems

def test_probe_rejects_a_prose_mention_of_the_field() -> None:
    """A mention is not a declaration: `workspace_gate=` carries no value, and the
    shared `keyed_value` predicate is what says so. A substring test would pass this row
    — the prose-as-data class the predicate exists to close."""
    row = {
        **_OK,
        "detail": "the run must declare workspace_gate= before it reports "
        "head=deadbeef985b0f1a6c8919c362a0a56ec7d0d42e",
    }
    problems, _ = run_verdict_problems([row], _PROBE_BOUNDARY)
    assert problems and VERDICT_KEY in problems[0], problems

def test_probe_rejects_a_row_without_the_head_sha() -> None:
    row = {**_OK, "detail": "insight_appended=23 — workspace_gate=rc=0"}
    problems, _ = run_verdict_problems([row], _PROBE_BOUNDARY)
    assert problems and "head=<sha>" in problems[0], problems

def test_probe_rejects_an_unreadable_head_but_accepts_a_later_readable_one() -> None:
    """The literal placeholder `head=<sha>` is not a revision; the scan must reject that
    row AND still find a real revision named after such a mention."""
    placeholder = {**_OK, "detail": "workspace_gate=rc=0 head=<sha>"}
    problems, _ = run_verdict_problems([placeholder], _PROBE_BOUNDARY)
    assert problems and "head=<sha>" in problems[0], problems

    described = {
        **_OK,
        "detail": "the head= field is carried by few rows; workspace_gate=rc=0 "
        "head=deadbeef985b0f1a6c8919c362a0a56ec7d0d42e",
    }
    problems, _ = run_verdict_problems([described], _PROBE_BOUNDARY)
    assert problems == [], problems

def test_probe_ignores_other_subjects_and_other_events() -> None:
    """The population is the ACT: a `run` row about something else — the class issue #46
    sits beside, e.g. HQ's `insights-and-growth-map` — is not governed by this rule, and
    neither is a non-`run` event."""
    other_subject = {**_OK, "subject": "insights-and-growth-map", "detail": "initialized"}
    other_event = {**_OK, "event": "close", "detail": "closed with no verdict"}
    problems, excused = run_verdict_problems([other_subject, other_event], _PROBE_BOUNDARY)
    assert problems == [] and excused == [], (problems, excused)

def test_probe_governs_the_dated_subject_the_pacemaker_writes_today() -> None:
    """THE NON-VACUITY PROOF, and the regression this gate was filed for (#167).

    The pacemaker writes `<stem>-<round>`; the gate's first key was exact equality on the
    bare job name it stopped writing, so the population was empty BY CONSTRUCTION and the
    gate SKIPPED the very round it exists to judge. A probe driven from the live ledger
    would have passed VACUOUSLY here — the whole point is that the live population was the
    empty one — so the proof rides this synthetic row.
    """
    dated = {**_OK, "subject": f"{SUBJECT_STEM}-2026-09-22",
             "detail": "insight_appended=23 — head=deadbeef985b"}
    problems, _ = run_verdict_problems([dated], _PROBE_BOUNDARY)
    assert problems and VERDICT_KEY in problems[0], problems

    governed = {**_OK, "subject": f"{SUBJECT_STEM}-2026-09-22"}
    problems, _ = run_verdict_problems([governed], _PROBE_BOUNDARY)
    assert problems == [], problems


def test_probe_a_round_key_variant_names_the_same_round() -> None:
    """#159's tolerance, one surface over: an hour-bearing or word-decorated subject names
    the SAME round, so it must stay in scope rather than read as absent."""
    for variant in (f"{SUBJECT_STEM}-2026-09-22T06", f"{SUBJECT_STEM}-2026-09-22-writeback"):
        row = {**_OK, "subject": variant}
        problems, _ = run_verdict_problems([row], _PROBE_BOUNDARY)
        assert problems == [], (variant, problems)


def test_probe_a_digit_extended_date_is_a_different_round() -> None:
    """The boundary guard. A bare `startswith(f"{SUBJECT_STEM}-")` would admit a subject
    whose date merely EXTENDS this one's digits — a different date, not this round."""
    row = {**_OK, "subject": f"{SUBJECT_STEM}-2026-09-220"}
    problems, excused = run_verdict_problems([row], _PROBE_BOUNDARY)
    assert problems == [] and excused == [], (problems, excused)


def test_probe_the_stem_alone_does_not_admit_a_stem_sharing_subject() -> None:
    """`insights-and-growth-map` (n=36) shares the stem's characters without naming a
    round, so the key is `<stem>-<date>` and not `<stem>-`. Without this arm the widening
    would swallow a neighbouring subject — the #159 class, in the other direction."""
    row = {**_OK, "subject": f"{SUBJECT_STEM}-and-growth-map", "detail": "initialized"}
    problems, excused = run_verdict_problems([row], _PROBE_BOUNDARY)
    assert problems == [] and excused == [], (problems, excused)

    assert subject_in_scope(f"{SUBJECT_STEM}-and-growth-map") is False
    assert subject_in_scope(f"{SUBJECT_STEM}-") is False
    assert subject_in_scope("") is False


def test_probe_the_matcher_is_a_predicate_and_not_a_position() -> None:
    """Every arm of the key in one place, so a future edit to `subject_in_scope` that
    widens or narrows it cannot pass unnoticed."""
    assert subject_in_scope(f"{SUBJECT_STEM}-2026-09-22") is True
    assert subject_in_scope(f"{SUBJECT_STEM}-2026-09-22T06") is True
    assert subject_in_scope(f"{SUBJECT_STEM}-2026-09-22-writeback") is True
    assert subject_in_scope(LEGACY_SUBJECT) is True
    assert subject_in_scope(f"{SUBJECT_STEM}-2026-09-220") is False
    assert subject_in_scope(f"{SUBJECT_STEM}-and-growth-map") is False
    assert subject_in_scope("patrol-verify-2026-09-22") is False


def test_probe_excuses_pre_boundary_rows_without_calling_them_clean() -> None:
    legacy = {
        "n": 241,
        "ts": "2026-09-18T15:32:02Z",
        "event": RUN_EVENT,
        "actor": "surveys",
        "subject": LEGACY_SUBJECT,
        "detail": "insight_appended=22-metric-population-mismatch-false-alarm",
    }
    problems, excused = run_verdict_problems([legacy], _PROBE_BOUNDARY)
    assert problems == [], problems
    assert len(excused) == 1 and "predates the declared boundary" in excused[0], excused

def test_probe_reports_a_row_whose_timestamp_cannot_be_read() -> None:
    """An undatable row cannot be excused by its date either, so it is a PROBLEM rather
    than silently absent from both lists."""
    problems, excused = run_verdict_problems([{**_OK, "ts": "whenever"}], _PROBE_BOUNDARY)
    assert problems and "unparseable ts" in problems[0], problems
    assert excused == [], excused
