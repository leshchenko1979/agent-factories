#!/usr/bin/env python3
"""Gate: the attestation dispatcher resolves HQ targets, and one bad factory is silent
for no other.

`tools/registry_attest.py` is the clock behind the registry's DECLARED half — it wakes
every factory's HQ with the three attestation questions. It ships in the kit, is
installed by BOOTSTRAP step 4d, and until this file existed it carried **no gate of any
kind**: zero gates named for it, and zero gates importing it (measured, `n=1130`). That
is the exact hole this project was opened to close — an instrument that reads as adopted
because it is present, while nothing exercises what it promises.

WHAT IS UNDER TEST. Not the resolver: `registry.resolve_lane` has its own gate
(`test_registry.py`). Under test here is the dispatcher's logic sitting ON TOP of it,
which is the half that can be wrong while every component beneath is right:

  * a factory with **no** `role: hq` lane is reported and skipped, not dispatched to;
  * a factory with **two** such lanes is AMBIGUOUS and refused — picking one silently is
    how a registry sends an attestation brief to the wrong lane;
  * a lane that does not resolve is reported by name with the resolver's own status;
  * **fail-open**: one factory's missing lane must not silence the fleet's attestation.
    This is the property the tool's docstring claims and the one a reader would never
    think to test, because the tempting bug is a `raise` or an early `return` inside the
    loop — which would pass every happy-path read of this file and quietly stop the
    whole fleet's clock for one malformed fragment.

The bindings are SYNTHETIC and `reg.all_bindings` is monkeypatched, so this gate reads no
database: `hq_targets` is pure over (fragments, bindings), and the real resolver runs
unchanged beneath it. A test that used the live box would assert whatever the box
happened to be doing.

WHY THIS FILE DECLARES ITSELF A GATE, and why it says so HERE. It is pytest-style —
`def test_*` at module level, NO `__main__` block — so
`python3 tests/test_registry_attest.py` binds its test functions and EXECUTES NONE: it
exits 0 with empty output. It must therefore be registered as
`[sys.executable, "-m", "pytest", ...]` and never in the script form, because the script
form would add a gate that prints PASS while running nothing. `tests/gate_registry.py`
asserts that pairing (direction 4).

It is byte-paired into `TEMPLATE/`, so the manifest grain is what keeps a factory from
dropping the runner and keeping the file (issue #107, ruling n=639).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import registry as reg  # noqa: E402
import registry_attest as ra  # noqa: E402

PROFILE = reg.FACTORY_PROFILE


def _fragment(slug: str, lanes: list[dict]) -> dict:
    """A synthetic fragment. Only `factory`, `profile` and `lanes` are read by the
    dispatcher, and the slug is deliberately NOT a fleet slug: `FACTORY_CHATS` has no
    entry for it, so `chat_id` is None and the resolver narrows on thread alone. That
    keeps this gate's fixtures from colliding with a real factory's bindings."""
    return {
        "factory": slug,
        "profile": PROFILE,
        "lanes": lanes,
    }


def _lane(role: str, thread: int, topic: str = "Topic") -> dict:
    return {"role": role, "thread_id": thread, "topic": topic}


def _binding(session: str, thread: int, profile: str = PROFILE, updated: int = 1_790_000_000) -> dict:
    """`updated_at` is an INTEGER epoch, not a timestamp string — measured: the live
    `session_bindings.updated_at` column is `INTEGER` and all 112 rows read back
    `typeof() = 'integer'`. A string here is not a harmless rendering choice: the resolver
    feeds it to `datetime.fromtimestamp`, so a fixture with the wrong type raises
    `TypeError` and the gate reports a defect that does not exist. The sibling
    `tests/test_registry.py:610` uses the same int shape for the same reason."""
    return {
        "session_id": session,
        "thread_id": thread,
        "chat_id": "111111111",
        "updated_at": updated,
        "_profile": profile,
    }


def _run(fragments: list[dict], bindings: list[dict], errors: list[str] | None = None):
    """Drive `hq_targets` with the bindings it would read from live profile DBs."""
    real = reg.all_bindings
    reg.all_bindings = lambda: (bindings, list(errors or []))
    try:
        return ra.hq_targets([(Path("/synthetic"), f) for f in fragments])
    finally:
        reg.all_bindings = real


def test_a_resolved_hq_lane_becomes_one_target():
    """The happy path, stated so the failure arms mean something."""
    frags = [_fragment("alpha-factory", [_lane("hq", 1, "HQ")])]
    binds = [_binding("sess-alpha-hq", 1)]
    targets, problems = _run(frags, binds)
    assert problems == [], problems
    assert len(targets) == 1, targets
    t = targets[0]
    assert t["slug"] == "alpha-factory", t
    assert t["session_id"] == "sess-alpha-hq", t
    assert t["thread_id"] == 1, t
    assert t["status"] == "resolved", t


def test_a_factory_with_no_hq_lane_is_reported_and_skipped():
    """A fragment whose lanes carry no `hq` cannot be woken. Reported by name."""
    frags = [_fragment("beta-factory", [_lane("worker", 2, "Work")])]
    targets, problems = _run(frags, [_binding("sess-beta-worker", 2)])
    assert targets == [], targets
    assert len(problems) == 1, problems
    assert "beta-factory" in problems[0], problems
    assert "role `hq`" in problems[0], problems


def test_two_hq_lanes_are_ambiguous_and_refused():
    """The load-bearing arm for correctness of DISPATCH.

    Two lanes claiming `hq` means the registry cannot say which session owns the
    attestation. Selecting the first would send the brief to a lane that may not be the
    HQ, and nothing downstream would show it: the send succeeds, the answer arrives from
    the wrong place. So it is refused and both topics are named.
    """
    frags = [_fragment("gamma-factory", [_lane("hq", 3, "First"), _lane("hq", 4, "Second")])]
    targets, problems = _run(frags, [_binding("sess-gamma-3", 3), _binding("sess-gamma-4", 4)])
    assert targets == [], targets
    assert len(problems) == 1, problems
    assert "ambiguous" in problems[0].lower(), problems
    assert "gamma-factory" in problems[0], problems
    assert "First" in problems[0] and "Second" in problems[0], problems


def test_an_unresolved_hq_lane_is_reported_with_the_resolvers_status():
    """A declared lane with no binding row is named, with WHY — not swallowed."""
    frags = [_fragment("delta-factory", [_lane("hq", 9, "Missing")])]
    targets, problems = _run(frags, [_binding("sess-other", 1)])
    assert targets == [], targets
    assert len(problems) == 1, problems
    assert "delta-factory" in problems[0], problems
    assert "Missing" in problems[0], problems
    assert "unbound" in problems[0], problems


def test_one_bad_factory_does_not_silence_the_others():
    """FAIL-OPEN, and the reason this gate exists.

    Four fragments, arranged so a resolvable factory sits AFTER each problem branch:
    alpha (no HQ lane at all), bravo (resolves), charlie (two HQ lanes), delta (resolves).
    Both good factories must still receive their briefs.

    The ordering is the load-bearing part of this arm and it was got wrong first. An
    earlier version placed the no-HQ fragment LAST, so a `return` at that branch lost
    nothing downstream and the arm passed on the mutant — decorative, caught only by
    running the mutation control. With a good fragment after EACH problem branch, an
    early `return` at either site loses a target this test asserts.

    A loop that `raise`s or `return`s on the first problem passes every single-fixture
    test above and stops the whole fleet's clock, which is the failure this tool's own
    docstring names as unacceptable.
    """
    frags = [
        _fragment("alpha-factory", [_lane("worker", 6, "Work")]),
        _fragment("bravo-factory", [_lane("hq", 5, "HQ")]),
        _fragment("charlie-factory", [_lane("hq", 7, "One"), _lane("hq", 8, "Two")]),
        _fragment("delta-factory", [_lane("hq", 9, "HQ")]),
    ]
    binds = [
        _binding("sess-alpha-worker", 6),
        _binding("sess-bravo-hq", 5),
        _binding("sess-charlie-7", 7),
        _binding("sess-charlie-8", 8),
        _binding("sess-delta-hq", 9),
    ]
    targets, problems = _run(frags, binds)
    assert [t["slug"] for t in targets] == ["bravo-factory", "delta-factory"], targets
    assert [t["session_id"] for t in targets] == ["sess-bravo-hq", "sess-delta-hq"], targets
    assert len(problems) == 2, problems
    assert any("alpha-factory" in p for p in problems), problems
    assert any("charlie-factory" in p for p in problems), problems


def test_targets_are_ordered_by_slug_so_a_rerun_is_diffable():
    """Dispatch order is a property of the input set, not of filesystem walk order.

    The run's output is what a later reader diffs against an earlier run; two runs of the
    same fleet printing different orders would make a stable state look like movement.
    """
    frags = [
        _fragment("zulu-factory", [_lane("hq", 11, "HQ")]),
        _fragment("alpha-factory", [_lane("hq", 12, "HQ")]),
        _fragment("mike-factory", [_lane("hq", 13, "HQ")]),
    ]
    binds = [
        _binding("sess-z", 11),
        _binding("sess-a", 12),
        _binding("sess-m", 13),
    ]
    targets, problems = _run(frags, binds)
    assert problems == [], problems
    assert [t["slug"] for t in targets] == ["alpha-factory", "mike-factory", "zulu-factory"], targets


def test_a_binding_read_error_is_carried_into_the_problems():
    """`all_bindings` returns (rows, errors) and an undeclared profile_root is an ERROR
    rather than an empty result, precisely so "no profile was readable" cannot render as
    "no lane is bound". The dispatcher must not drop that half."""
    frags = [_fragment("novaya-factory", [_lane("hq", 21, "HQ")])]
    targets, problems = _run(frags, [], errors=["no profile root declared for ops"])
    assert targets == [], targets
    assert any("no profile root declared for ops" in p for p in problems), problems


def test_the_brief_carries_all_three_questions():
    """The brief is the product. Its three questions are the declared half's whole
    anti-rot surface — fragment, announcements, cron attribution — and a fourth edit that
    silently drops one is invisible from the send side, because the send still succeeds.

    Asserted on the shipped template string, keyed on the phrases the tool's own docstring
    uses to name each question.
    """
    text = ra.BRIEF.format(slug="alpha-factory", stamp="2026-09-25T00:00Z")
    assert "alpha-factory" in text and "2026-09-25T00:00Z" in text, text[:200]
    assert "QUESTION 1" in text, text
    assert "QUESTION 2" in text, text
    assert "QUESTION 3" in text, text
    for phrase in ("fragment", "announcement", "prefix"):
        assert phrase in text.lower(), (phrase, text)
    assert "{slug}" not in text and "{stamp}" not in text, text


def test_no_placeholder_survives_the_format():
    """A `{...}` left in the rendered brief is a template bug the sender cannot see, and
    every recipient reads it. The three-question test above formats the string; this one
    asserts nothing else in it stayed un-substituted."""
    import re

    text = ra.BRIEF.format(slug="alpha-factory", stamp="2026-09-25T00:00Z")
    leftover = re.findall(r"\{[a-z_]+\}", text)
    assert leftover == [], leftover
