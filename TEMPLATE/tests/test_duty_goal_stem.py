"""Gate: a job's GOAL must name the duty stem its PROMPT declares (#618).

The defect this gate guards, measured 2026-11-05: `factory-hq-pacemaker` declares
`receipt_subject: hq-cycle` in its prompt and rendered a goal naming `#253`. A woken lane
reads TWO texts — the prompt and, when `set_goal` is truthy, the goal — and the GOAL is the
one it steers by. So the duty was declared on a surface the lane never read, the receipt
went out under an identifier no stem predicate can pair, and the round read MISSING for a
duty that had been done. Nothing in the tree asked the question.

WHAT THIS GATE CAN AND CANNOT SEE, stated because it is the difference between a real green
and a decorative one. The PROMPT half is TAUTOLOGICAL: `declared_receipt_stem` reads the
stem OUT OF the prompt, so for any row this leg judges, `stem in prompt` is true by
construction. The GOAL surface is the only half that can bite, and every arm below that
asserts a finding removes the stem from the GOAL and leaves the prompt untouched.

EVERY READER IS INJECTED (`disposition_fn`, `carries_fn`), so no verdict here is decided by
this box's live prompts or goal templates. The pair that matters is
`test_the_incident_goal_naming_a_ticket` against `test_control_the_same_job_naming_its_stem`:
they differ in ONE substring of ONE goal template.
"""

# --- imports ---------------------------------------------------------------
from __future__ import annotations
import pytest

from patrol_fixtures import RUNNER  # noqa: F401  (import side effect: loads the runner)

P = RUNNER

# --- fixture rows ----------------------------------------------------------
# The job as it is on the box: the declaration lives in the PROMPT, and `set_goal` renders a
# goal. `receipt_subject` as a row KEY would be read by nothing — that is the shape of #618.
_STEM = "hq-cycle"
_JOB_ID = "8e6522bb-1fa1-4eed-a2e5-de705f8ffa10"


def _row(*, goal: str, stem: str = _STEM, set_goal=1, name="factory-hq-pacemaker",
         prompt: str | None = None, home="ops") -> dict:
    """One enabled cron row, shaped exactly as `box_cron_rows` emits it."""
    return {
        "id": _JOB_ID,
        "name": name,
        "deliver_to": "",
        "prompt": prompt if prompt is not None else f"Run the weekly HQ cycle.\nreceipt_subject: {stem}\n",
        "last_run_at": "2026-11-02T09:50:35Z",
        "cron_expr": "0 9 * * 1",
        "next_run_at": "2026-11-09T06:00:00Z",
        "timezone": "Europe/Moscow",
        "set_goal": set_goal,
        "goal_template": goal,
        "home": home,
    }


def _leg(rows, **kw):
    return P.duty_goal_stem_leg(rows, read_at="2026-11-05T19:00:00Z", **kw)


# --- the incident and its control -----------------------------------------
def test_the_incident_goal_naming_a_ticket_instead_of_the_stem():
    """The measured shape: prompt declares `hq-cycle`, goal names `#253` -> FINDING."""
    leg = _leg([_row(goal="Complete the weekly cycle for #253 and report it.")])
    assert leg["status"] == "ASSERTED", leg
    assert len(leg["problems"]) == 1, leg["problems"]
    problem = leg["problems"][0]
    assert _STEM in problem, problem
    assert "factory-hq-pacemaker" in problem, problem
    assert "GOAL" in problem, problem
    assert leg["coverage"]["goal_judged"] == 1, leg["coverage"]
    assert leg["coverage"]["goal_passed"] == 0, leg["coverage"]


def test_control_the_same_job_naming_its_stem_in_the_goal():
    """ONE substring differs from the incident: `#253` -> `hq-cycle`. No finding."""
    leg = _leg([_row(goal="Complete the weekly hq-cycle round and report it.")])
    assert leg["status"] == "ASSERTED", leg
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["goal_judged"] == 1, leg["coverage"]
    assert leg["coverage"]["goal_passed"] == 1, leg["coverage"]


def test_an_empty_goal_template_is_the_same_class_not_a_skip():
    """A goal rendered from an empty template carries no stem either -> FINDING."""
    leg = _leg([_row(goal="")])
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "EMPTY" in leg["problems"][0], leg["problems"][0]
    assert _STEM in leg["problems"][0], leg["problems"][0]


# --- the population boundary, printed rather than silent -------------------
def test_a_job_rendering_no_goal_is_not_judged():
    """`set_goal` falsy -> no goal text exists to carry the stem: NOT JUDGED, counted."""
    leg = _leg([_row(goal="", set_goal=0)])
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["goal_judged"] == 0, leg["coverage"]
    assert leg["coverage"]["goal_not_rendered"] == 1, leg["coverage"]
    # and with no goal surface at all the leg is NOT RUN, never a clean ASSERTED
    assert leg["status"] == "NOT RUN", leg
    assert "ZERO" in leg["coverage"]["reason"], leg["coverage"]["reason"]


def test_a_home_without_the_column_is_unknown_never_a_pass():
    """`set_goal` NULL (a home predating the column) is UNREAD, not absent -> EXCUSED."""
    leg = _leg([_row(goal="Complete the weekly cycle for #253.", set_goal=None)])
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["goal_surface_unknown"] == 1, leg["coverage"]
    assert leg["coverage"]["goal_judged"] == 0, leg["coverage"]
    assert len(leg["excused"]) == 1, leg["excused"]
    assert "UNREAD" in leg["excused"][0], leg["excused"][0]
    assert leg["status"] == "NOT RUN", leg


def test_owes_none_and_undeclared_are_outside_the_population():
    """`receipt_subject: none` and no declaration at all are counted, never judged."""
    leg = _leg([
        _row(goal="Complete #253.", stem="none"),
        _row(goal="Complete #253.", prompt="Run the weekly cycle.", name="no-decl"),
    ])
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["owes_none"] == 1, leg["coverage"]
    assert leg["coverage"]["undeclared"] == 1, leg["coverage"]
    assert leg["coverage"]["declares_stem"] == 0, leg["coverage"]


def test_a_malformed_declaration_is_excused_not_a_second_finding():
    """#506's class is `duty-receipt`'s finding; this leg must not double-report it."""
    leg = _leg([_row(goal="Complete #253.", prompt="Run it.\nreceipt_subject: `hq-cycle`\n")])
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["malformed_declarations"] == 1, leg["coverage"]
    assert leg["coverage"]["declares_stem"] == 0, leg["coverage"]
    assert len(leg["excused"]) == 1, leg["excused"]


def test_the_population_counts_always_print():
    """A leg that examined nothing must not render like one that examined everything (#126)."""
    leg = _leg([])
    cov = leg["coverage"]
    for key in ("cron_rows_read", "declares_stem", "goal_judged", "goal_passed",
                "goal_not_rendered", "goal_surface_unknown", "undeclared", "owes_none",
                "malformed_declarations", "prompt_surface_tautological", "stems_declared"):
        assert key in cov, (key, sorted(cov))
    assert cov["cron_rows_read"] == 0, cov
    assert leg["status"] == "NOT RUN", leg


def test_the_tautological_half_is_declared_as_such():
    """The prompt check cannot be evidence of diligence, and the coverage says so."""
    leg = _leg([_row(goal="Complete the weekly hq-cycle round.")])
    assert leg["coverage"]["prompt_surface_tautological"] is True, leg["coverage"]


# --- mutant: remove the thing under test ----------------------------------
def test_MUTANT_without_the_stem_predicate_the_incident_reads_CLEAN(monkeypatch):
    """A gate that cannot fail is decoration.

    This arm neuters `stem_carried` — the ONE predicate the verdict turns on — and asserts
    the incident's finding DISAPPEARS on the SAME fixture. So the green above is
    attributable to that predicate and to nothing else.
    """
    monkeypatch.setattr(P, "stem_carried", lambda stem, text: True)
    leg = _leg([_row(goal="Complete the weekly cycle for #253 and report it.")])
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["goal_passed"] == 1, leg["coverage"]


if __name__ == "__main__":
    # PYTEST form: these are module-level arms, so a bare run would exit 0 having asserted
    # NOTHING — a gate whose only exits are barred (entry-point equivalence, #612 review).
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
