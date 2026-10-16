#!/usr/bin/env python3
"""Gate: the register's INTAKE clause exists in the instrument's law, and its metric leg can SEE.

Issue #271, ruled by HQ 2026-10-02T18:21:56Z. The defect was a LAW gap with a measured cost:
nothing separated an OWNER decision from an INTERNAL one before it reached the register, so
four of the five answers in the burst of 2026-10-02T13:50:15Z-14:05:46Z (q21, q23, q24, q26)
had to decline the question as internal — and every one of them inflated the human-gate
metric, which `skills/meta-factory/state.md` defines as the count of open questions.

The ruling's leg 3: *"A gate asserts the clause's presence in the instrument's law and the
pointer in the law's State section."* This gate is that, plus the metric's own probes — because a printed number
nobody can drive is a number nobody can trust.

  A. THE CLAUSE, in the instrument's own law. `docs/instruments/open-questions.md` §3 carries
     the four admissible inputs and the decisive negative (a lane that cannot name one decides
     it itself and does NOT register it), and the doc is byte-identical to its TEMPLATE twin.
  B. THE POINTER, in SKILL.md §State — every surface has one writer. The surface table names the instrument's law AND the intake
     filter — that section keeps a pointer, never a second copy of the clause (the law's own split).
  C. THE METRIC CAN SEE, on a fixture. Driven with the measured burst: M counts the OWNER's
     answers, N the declines among them, and the LANE's own recording (q25, `answered_via:
     cli`) is NOT counted — a bare text scan reads that decision record as a fifth decline,
     which is the trap `answered_via` closes. The window filter is proven by an answer outside
     it, and an absent store prints NOT RUN with its reason rather than a zero.
  D. THE WIRING. The measurement round imports the ONE reader (two implementations drift, and
     the drift is silent) and prints the line.

SHAPE, never a hash (open-questions.md §5.5): the clauses are matched by their stable tokens, and the missing
one is named. `skills/meta-factory/SKILL.md` is a ROOT-only law file -- a bootstrapped factory
tree has no `skills/` directory -- so leg B SKIPS by name there rather than reddening a tree
that legitimately has no such file (#68: a leg that reds correct data teaches lanes to ignore
red). The instrument doc, the reader and the audit are all shipped, so their legs run everywhere.

Run:  python3 tests/test_question_intake.py      (or: python3 -m pytest tests/test_question_intake.py)
Exit: 0 the gate holds, 1 otherwise.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INSTRUMENT = "docs/instruments/open-questions.md"
TEMPLATE_INSTRUMENT = "TEMPLATE/docs/instruments/open-questions.md"
SKILL = "skills/meta-factory/SKILL.md"
READER = "tools/intake_metric.py"
TEMPLATE_READER = "TEMPLATE/tools/intake_metric.py"
AUDIT = "tools/audit.py"

# The pair legs are a property of the ORIGIN tree alone. A tree with no nested `TEMPLATE/` is
# either the shipped template itself — the copy runs with cwd=TEMPLATE, so REPO IS that
# directory — or a bootstrapped factory, which receives the template's CONTENTS and keeps no
# second copy of them. Comparing a tree against itself is not a check, so those legs SKIP BY
# NAME there rather than red a tree that legitimately has no twin. #68's class: a gate that
# reds correct data teaches lanes to ignore red.
# STATED SKIP: TEMPLATE/
PAIR_SKIP_NOTE = (
    "pair: SKIPPED — this tree carries no nested TEMPLATE/ (it IS the shipped template, or a "
    "bootstrapped factory), so there is no twin to compare against"
)

def origin_tree(repo: Path) -> bool:
    """True where `repo` is the origin tree — the one that carries the shipped pairs."""
    return (repo / "TEMPLATE").is_dir()

# The clause's SHAPE: the four admissible owner-only inputs, each a stable phrase, plus the
# decisive negative. Matched case-insensitively on the instrument's own text; a missing token
# is named in the failure so the reader knows which half of the clause went.
INTAKE_TOKENS = (
    "a value he alone holds",
    "a priority between goals he owns",
    "a cost he bears",
    "a policy only he may set",
    "does **not** register it",
)

# The metric leg's own marker, and the pointer's.
METRIC_MARKER = "declined-as-internal"
INTAKE_POINTER_TOKENS = ("intake", "docs/instruments/open-questions.md")

# The measured burst, reproduced as a fixture. `page` = the OWNER answered; `cli` = a LANE
# recorded its own decision. q25 is the trap: its text QUOTES the owner's declines.
FIXTURE_ANSWERS = (
    ("q19", "page", "2026-10-02T13:59:21+00:00", ["Uphold all 8 refusals - nothing is published"]),
    ("q21", "page", "2026-10-02T14:00:25+00:00", "you should decide this by yourself"),
    ("q23", "page", "2026-10-02T14:05:46+00:00", "this seems like some internal shit you shouldn't ask me about"),
    ("q24", "page", "2026-10-02T13:50:15+00:00", "it's you internal question, don't ask me questions like this, decide by yourself"),
    ("q26", "page", "2026-10-02T14:01:08+00:00", "you should decide this by yourself"),
    ("q25", "cli", "2026-10-02T14:30:32+00:00", 'DECIDED BY HQ (q23/q24/q26 all answered "decide by yourself"): OPTION 0'),
    ("qOLD", "page", "2026-08-01T00:00:00+00:00", "you should decide this by yourself"),
)
FIXTURE_NOW = "2026-10-02T14:10:00+00:00"


def _load_reader():
    """Import the ONE reader from `tools/`. Returns (module, problems)."""
    sys.path.insert(0, str(REPO / "tools"))
    try:
        import intake_metric  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - only where the reader is missing
        return None, [f"{READER} is not importable: {exc}"]
    return intake_metric, []


def _fixture_store() -> dict:
    return {
        "version": 1,
        "sets": [
            {
                "id": "meta-factory",
                "factory": "meta-factory",
                "lane": "HQ",
                "status": "open",
                "questions": [
                    {
                        "qid": qid,
                        "status": "answered",
                        "answer": answer,
                        "answered_via": via,
                        "answered_at": at,
                    }
                    for qid, via, at, answer in FIXTURE_ANSWERS
                ],
            }
        ],
    }


def leg_a_clause(repo: Path) -> tuple[list[str], list[str]]:
    """The clause in the instrument's law, and the doc's byte-identical twin."""
    problems: list[str] = []
    prints: list[str] = []
    doc = repo / INSTRUMENT
    if not doc.is_file():
        return [f"{INSTRUMENT} is absent"], prints
    text = doc.read_text(encoding="utf-8")
    missing = [tok for tok in INTAKE_TOKENS if tok.lower() not in text.lower()]
    if missing:
        problems.append(
            f"{INSTRUMENT} does not carry the intake clause's shape — missing: "
            + "; ".join(repr(t) for t in missing)
        )
    if METRIC_MARKER not in text:
        problems.append(f"{INSTRUMENT} never names the metric leg's marker {METRIC_MARKER!r}")
    prints.append(f"clause: {len(INTAKE_TOKENS) - len(missing)}/{len(INTAKE_TOKENS)} token(s) present in {INSTRUMENT}")

    if not origin_tree(repo):
        prints.append(PAIR_SKIP_NOTE)
    else:
        twin = repo / TEMPLATE_INSTRUMENT
        if not twin.is_file():
            problems.append(f"{TEMPLATE_INSTRUMENT} is absent (the doc is a shipped pair)")
        elif twin.read_bytes() != doc.read_bytes():
            problems.append(f"{TEMPLATE_INSTRUMENT} is NOT byte-identical to {INSTRUMENT}")
        else:
            prints.append(f"pair: {INSTRUMENT} == {TEMPLATE_INSTRUMENT}")
    return problems, prints


def leg_b_pointer(repo: Path) -> tuple[list[str], list[str], str]:
    """The SKILL.md §State — every surface has one writer pointer. SKIPS where the root-only law file is absent."""
    skill = repo / SKILL
    if not skill.is_file():
        return [], [], f"{SKILL} is not present in this tree (root-only law file)"
    text = skill.read_text(encoding="utf-8")
    problems: list[str] = []
    # The row is selected by its OWN first cell, never by a token this leg then asserts:
    # selecting on an asserted token would make the leg self-consistent by construction --
    # any row carrying that token would be found and pass. `questions register` is unique in
    # the file (verified) and is not one of INTAKE_POINTER_TOKENS. It is also not a toolchain
    # name: the register's authoritative writer is a profile-home CLI that resolves on no
    # host, so naming it here would be the foreign-toolchain defect `test_template_sync`
    # exists to catch -- this file ships to member factories that have no such binary.
    rows = [ln for ln in text.splitlines() if "questions register" in ln]
    if not rows:
        problems.append(f"SKILL.md §State — every surface has one writer: no row for the register in {SKILL}")
    else:
        row = rows[0]
        missing = [tok for tok in INTAKE_POINTER_TOKENS if tok.lower() not in row.lower()]
        if missing:
            problems.append(
                "SKILL.md §State — every surface has one writer: the register row does not carry the pointer's shape — missing: "
                + "; ".join(repr(t) for t in missing)
            )
    return problems, [f"pointer: SKILL.md §State — every surface has one writer names the register and its law ({len(rows)} row(s))"], ""


def leg_c_metric(repo: Path) -> tuple[list[str], list[str]]:
    """The metric can SEE: the burst, the discriminator, the window, and the honest absence."""
    problems: list[str] = []
    prints: list[str] = []
    module, load_problems = _load_reader()
    if module is None:
        return load_problems, prints

    import datetime as _dt  # noqa: PLC0415

    now = _dt.datetime.fromisoformat(FIXTURE_NOW)
    stats = module.intake_stats(_fixture_store(), days=30, now=now)
    if stats["answered"] != 5:
        problems.append(
            f"the fixture's OWNER answers (answered_via=page, in window) count {stats['answered']}, expected 5"
        )
    if stats["declined"] != 4:
        problems.append(
            f"the fixture's declines count {stats['declined']}, expected 4 — the measured burst "
            "declined 4 of 5 (q21, q23, q24, q26)"
        )
    counted = {row["qid"] for row in stats["matched"]}
    if "q25" in counted:
        problems.append(
            "q25 was counted as a decline — it is the LANE's own recording (`answered_via: cli`) "
            "whose text QUOTES the owner; a bare text scan reads it as a fifth decline, and the "
            "`answered_via` discriminator is what stops that"
        )
    if "qOLD" in counted:
        problems.append("qOLD was counted — it is outside the window and the window filter is not applied")
    prints.append(
        f"metric: {stats['declined']} of {stats['answered']} (window {stats['window_days']:g}d) "
        f"on the measured burst, matched {sorted(counted)}"
    )

    # A predicate with no positive is an instrument that cannot observe its own class.
    if module.declines_as_internal("Uphold all 8 refusals") is not None:
        problems.append("a substantive answer was classified as a decline — the predicate is too wide")
    else:
        prints.append("predicate: a substantive answer is NOT a decline")

    # A CASE PER PATTERN for the declines the owner's 2026-10-15 burst carried and the set
    # above MISSED (#489): the leg read 6 of 143 answered on that 30d window where the honest
    # reading is 9 of 143. Gated rather than asserted, so narrowing either regex reds HERE
    # instead of silently returning to the under-report. One case per ALTERNATION branch too:
    # a two-branch regex whose second branch is never exercised is half an instrument, and the
    # `be involved` / `dint` spellings are MEASURED from q31, not guessed.
    for text, expected in (
        ("This is outside of my human scope", "scope-boundary"),
        ("this is outside my remit", "scope-boundary"),
        ("I do not want to get involved in this", "get-involved"),
        ("I dint want to be involved in this", "get-involved"),
        ("that is not mine to solve", "get-involved"),
    ):
        got = module.declines_as_internal(text)
        if got != expected:
            problems.append(
                f"the measured decline {text!r} matched {got!r}, expected {expected!r} — the "
                "pattern set cannot see this class, which is the under-report #489 was filed on"
            )
        else:
            prints.append(f"predicate: {text!r} is seen as {expected}")

    # The absent store is NOT RUN with a reason, never a zero (#68's shape).
    line = module.format_line({"answered": 0, "declined": 0, "window_days": 30, "matched": []}, "no store here")
    if "NOT RUN" not in line or "no store here" not in line:
        problems.append(f"the absent-store line does not read as NOT RUN with its reason: {line!r}")
    else:
        prints.append(f"absence: {line}")
    return problems, prints


def leg_d_wiring(repo: Path) -> tuple[list[str], list[str]]:
    """The measurement round imports the ONE reader and prints the line."""
    problems: list[str] = []
    prints: list[str] = []
    reader = repo / READER
    if not reader.is_file():
        return [f"{READER} is absent — the metric has no reader"], prints
    if not origin_tree(repo):
        prints.append(PAIR_SKIP_NOTE)
    else:
        twin = repo / TEMPLATE_READER
        if not twin.is_file():
            problems.append(f"{TEMPLATE_READER} is absent (the reader is a shipped pair)")
        elif twin.read_bytes() != reader.read_bytes():
            problems.append(f"{TEMPLATE_READER} is NOT byte-identical to {READER}")
        else:
            prints.append(f"pair: {READER} == {TEMPLATE_READER}")

    audit = repo / AUDIT
    if not audit.is_file():
        return problems + [f"{AUDIT} is absent"], prints
    text = audit.read_text(encoding="utf-8")
    if "intake_metric" not in text:
        problems.append(f"{AUDIT} does not import the reader — the metric is computed by nobody")
    if "parse_intake_metric" not in text:
        problems.append(f"{AUDIT} never computes the intake metric — the reader is imported and unused")
    if METRIC_MARKER not in text:
        problems.append(f"{AUDIT} never prints {METRIC_MARKER!r} — the population has no reader")
    prints.append(f"wiring: {AUDIT} imports the reader and prints {METRIC_MARKER!r}")
    return problems, prints


def evaluate(repo: Path = REPO) -> tuple[str, str, list[str], list[str]]:
    """Return (status, skip_reason, problems, prints)."""
    problems: list[str] = []
    prints: list[str] = []
    for leg in (leg_a_clause, leg_c_metric, leg_d_wiring):
        p, pr = leg(repo)
        problems += p
        prints += pr
    p, pr, skip = leg_b_pointer(repo)
    problems += p
    prints += pr
    if problems:
        return "fail", "", problems, prints
    return "ok", skip, problems, prints


def main() -> int:
    status, skip, problems, prints = evaluate(REPO)
    if status == "fail":
        print("question-intake gate FAILED:", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        return 1
    for line in prints:
        print(f"  {line}")
    if skip:
        print(f"question-intake gate: clean — 1 leg SKIPPED: {skip}")
    else:
        print("question-intake gate: clean — the intake clause is in the instrument's law, SKILL.md §State — every surface has one writer points at it, and the metric can see")
    return 0


# --- pytest form ---------------------------------------------------------------------------
# The gate is registered under `-m pytest` (it carries module-level tests). The `main()` above
# is the script form, kept because a reader of the run wants the reason on STDOUT.


def test_intake_clause_is_in_the_instrument_law():
    problems, _ = leg_a_clause(REPO)
    assert not problems, "\n".join(problems)


def test_section_11_points_at_the_instrument():
    problems, _, skip = leg_b_pointer(REPO)
    assert not problems, "\n".join(problems) or skip


def test_metric_counts_the_measured_burst():
    problems, _ = leg_c_metric(REPO)
    assert not problems, "\n".join(problems)


def test_measurement_round_prints_the_metric():
    problems, _ = leg_d_wiring(REPO)
    assert not problems, "\n".join(problems)


if __name__ == "__main__":
    raise SystemExit(main())
