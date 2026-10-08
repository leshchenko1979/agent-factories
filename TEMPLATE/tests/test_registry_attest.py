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

TWO MORE SURFACES, added for #259 (ruling n=1848):

  * **the brief names the route it expects the answer on.** The closing line used to read
    "Reply on this session." — which each lane read as ITS OWN, because the notify
    arrived in that lane's session. Four of six did exactly that on the 2026-10-01 round
    and delivered nothing to the collector. The arm below pins the route by a predicate
    over the RENDERED brief, and a MUTATION CONTROL proves the predicate bites: a brief
    with the route line removed must FAIL it, or the arm is re-reading text it wrote.
  * **the collection leg declares its population.** `classify_answers` is pure over
    (targets, observed, recovered), so it is driven here with synthetic rows; the split is
    asserted, and an unaccounted target must be reported rather than folded into silence.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import registry as reg  # noqa: E402
import registry_attest as ra  # noqa: E402

PROFILE = reg.FACTORY_PROFILE

# #267 — the marker that ends the brief's CONDENSED head block. Kept as a constant read by
# the cap arm, not as a literal inside it, so the boundary and the thing it bounds cannot
# drift apart.
HEAD_BLOCK_END = "--- FULL DETAIL BELOW ---"


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


def test_the_head_block_survives_the_classic_cap():
    """#267 — the classic-leg cap elides the MIDDLE, so Q3 must live in the HEAD.

    `truncate_chars_tail_preserving` (opencrabs `src/utils/string.rs:46`) keeps
    `head = inner*2/3` and `tail = inner-head_len` and elides what is BETWEEN them. The
    brief is over the classic budget, so on that leg the middle is what is lost — and
    before this change QUESTION 3 (2313 chars in) sat exactly there, while ANSWER BY
    survived in the tail. The target therefore receives Q1, Q2 and the answer instruction
    and cannot read what it is asked about its prefix and cron rows.

    The remedy is not a second variant: a CONDENSED block in the HEAD survives any cap
    that preserves head+tail. This arm asserts that on a FAITHFUL projection.

    The cap is DECLARED here with its provenance rather than derived from the harness,
    which this repo does not vendor: `ECHO_BODY_CAP_CHARS = 3200` (opencrabs
    `src/utils/echo_budget.rs`, quoted in #267). A literal that the harness moves is a
    reading, so the numbers travel with the issue that measured them.
    """
    text = _rendered_brief()
    cap = 3200
    marker = "\n\n[... middle elided ...]\n\n"  # the elision marker's own footprint
    inner = cap - len(marker)
    head_len = inner * 2 // 3
    tail_len = inner - head_len
    assert len(text) > cap, f"the brief is {len(text)} chars — it no longer over-caps, so this arm tests nothing"
    projected = text[:head_len] + marker + text[-tail_len:]

    for token in ("QUESTION 1", "QUESTION 2", "QUESTION 3", "ANSWER BY session_notify"):
        assert token in projected, (
            f"{token!r} does not survive the classic cap — a classic-leg target cannot "
            f"read it. Projection tail:\n{projected[-400:]}"
        )

    # The head block itself must END inside the preserved head, or a cap that trims the
    # block would still lose a question. Asserted as a boundary, not as a length, so the
    # arm survives the block being reworded.
    head_block_end = text.find(HEAD_BLOCK_END)
    assert head_block_end != -1, f"the head block terminator {HEAD_BLOCK_END!r} is gone"
    assert head_block_end <= head_len, (
        f"the condensed head block ends at {head_block_end}, past the {head_len} chars the "
        "classic cap preserves — Q3 would be elided again"
    )

def test_the_head_block_arm_bites_when_the_block_is_removed():
    """MUTATION CONTROL — the arm above must FAIL on the brief that caused #267.

    Without this, the projection assertion could pass on any brief at all: a test that
    renders the string it just asserted on re-reads its own text. So the head block is
    STRUCK OUT and the same projection must lose QUESTION 3 — which is exactly the shape
    the issue measured (2313 chars in, elided), while ANSWER BY survives in the tail.
    """
    text = _rendered_brief()
    neutered = text[text.find(HEAD_BLOCK_END) + len(HEAD_BLOCK_END):]
    assert HEAD_BLOCK_END not in neutered, "the neutering did not remove the head block"
    assert "QUESTION 3" in neutered, (
        "the pre-fix shape still carries Q3 in the BODY — that is the text the cap elides, "
        "and removing it here would make this control test nothing"
    )

    cap = 3200
    marker = "\n\n[... middle elided ...]\n\n"
    inner = cap - len(marker)
    head_len = inner * 2 // 3
    tail_len = inner - head_len
    projected = neutered[:head_len] + marker + neutered[-tail_len:]
    # The measured defect, reproduced: Q1 and Q2 arrive, Q3 does NOT, and ANSWER BY
    # survives in the tail — which is exactly why the loss was invisible from the send side.
    assert "QUESTION 1" in projected, projected[:400]
    assert "QUESTION 2" in projected, projected[:400]
    assert "QUESTION 3" not in projected, (
        "the neutered brief still carries Q3 in the projection — the arm above cannot bite"
    )
    assert "ANSWER BY session_notify" in projected, (
        "ANSWER BY is expected to SURVIVE in the tail — the issue's own measurement — so "
        "losing it here means the projection model no longer matches the harness"
    )

def test_no_placeholder_survives_the_format():
    """A `{...}` left in the rendered brief is a template bug the sender cannot see, and
    every recipient reads it. The three-question test above formats the string; this one
    asserts nothing else in it stayed un-substituted."""
    import re

    text = ra.BRIEF.format(slug="alpha-factory", stamp="2026-09-25T00:00Z")
    leftover = re.findall(r"\{[a-z_]+\}", text)
    assert leftover == [], leftover

# --------------------------------------------------------------------------------------
# #259 (ruling n=1848), clause 1 — the brief NAMES the route it expects the answer on.
# --------------------------------------------------------------------------------------

UUID_LITERAL = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

def _rendered_brief() -> str:
    return ra.BRIEF.format(slug="alpha-factory", stamp="2026-09-25T00:00Z")

def _brief_names_the_route(text: str) -> bool:
    """Clause 1's predicate, over a RENDERED brief.

    All four conditions are required, and each one is a distinct way the defect could
    return:

      * the lane-to-lane route is NAMED (`session_notify`) — without it the brief gives no
        route at all, which is where "reply on this session" left the reader;
      * the SENDER ID's location is named (the `from` header) — the route without a
        destination is still unfollowable, and this is the clause that keeps a literal id
        out of the text, since the header already carries it and can never go stale;
      * the OLD wording is gone — "reply on this session" is not ambiguous, it is
        unfollowable: a lane cannot write into the collector's own session;
      * NO literal session uuid — a baked-in id is stale the moment a topic is rebound,
        which is the exact hazard the brief's own forbidden-fields list names.

    Kept in the GATE rather than the tool on purpose: it is an assertion about the shipped
    text, and the mutation arm below is what proves it discriminates.
    """
    lowered = text.lower()
    if "session_notify" not in lowered:
        return False
    if "`from`" not in lowered:
        return False
    if "reply on this session" in lowered:
        return False
    if UUID_LITERAL.search(lowered):
        return False
    return True

def test_the_brief_names_the_notify_route_and_points_at_the_header():
    """The product of #259: the closing line says HOW to answer and WHERE to send it."""
    text = _rendered_brief()
    assert _brief_names_the_route(text) is True, text[-700:]
    assert "Reply on this session." not in text, text[-700:]
    assert "session_notify" in text, text[-700:]

def test_a_brief_with_the_route_line_removed_fails_the_same_predicate():
    """MUTATION CONTROL — the predicate must BITE, or the arm above proves nothing.

    A gate that formats the string it just asserted on re-reads its own text: it would
    pass just as happily against a brief that had lost the route. So the same predicate is
    run against a NEUTERED copy — the route line struck out — and must return False.
    """
    text = _rendered_brief()
    neutered = "\n".join(
        line for line in text.splitlines() if "session_notify" not in line
    )
    assert "session_notify" not in neutered, neutered[-400:]
    assert _brief_names_the_route(neutered) is False, neutered[-700:]

def test_the_predicate_rejects_the_pre_fix_wording():
    """The predicate is only worth having if it rejects the text that CAUSED #259.

    Re-introducing the old closing sentence into the shipped brief — leaving the route
    line in place, so the ONLY thing that changed is the old wording coming back — must
    fail it. This is the arm that would have caught the original defect.
    """
    text = _rendered_brief()
    regressed = text + "\nReply on this session.\n"
    assert _brief_names_the_route(regressed) is False, regressed[-700:]

def test_the_predicate_rejects_a_brief_carrying_a_literal_session_id():
    """Clause 2 — no id is baked in. A brief with one must fail the same predicate."""
    text = _rendered_brief()
    baked = text.replace("`from`", "`from` (collector 23549292-77ff-40d1-97e3-5aa0bdd19d74)")
    assert baked != text, "the substitution did not apply — this arm would test nothing"
    assert _brief_names_the_route(baked) is False, baked[-700:]

# --------------------------------------------------------------------------------------
# #439 — the brief names the READ SOURCE, not only the read action.
# --------------------------------------------------------------------------------------

# The prohibition is a PHRASE, not a vibe: the brief must say in words that a shared
# working tree is not the source. Matched with a regex so the wording can be reflowed
# ("never a shared working tree" / "never from a shared working tree") without disarming
# the arm — the thing being pinned is that the prohibition EXISTS, not its sentence.
READ_SOURCE_PROHIBITION = re.compile(r"never (?:from )?a shared working tree")

def _brief_names_the_read_source(text: str) -> bool:
    """#439 — Q1 must name WHERE to read the fragment, not only THAT to read it.

    The shipped brief said "Read it back before answering" and named no source, so the
    natural path a lane takes is the shared clone, whose working tree is FROZEN. Two
    fragments read from it in the 2026-10-08 round were three days stale, and a
    write-back patch built from that image would have REVERTED a correct line another
    lane had already landed — the stale read corrupts a write, not only an answer.

    Three tokens, because each is load-bearing and any one of them missing leaves the
    defect reachable: the REVISION (`origin/main`), the COMMAND that reads it
    (`git show origin/main:`), and the PROHIBITION that rules out the shared tree.
    """
    lowered = text.lower()
    if "origin/main" not in lowered:
        return False
    if "git show origin/main:" not in lowered:
        return False
    if not READ_SOURCE_PROHIBITION.search(lowered):
        return False
    return True

def test_the_brief_names_the_read_source_and_not_only_the_read_action():
    """The product of #439: Q1 says where to read, and rules out the stale surface."""
    text = _rendered_brief()
    assert _brief_names_the_read_source(text) is True, text[:900]

def test_a_brief_with_the_read_source_struck_out_fails_the_same_predicate():
    """MUTATION CONTROL — the predicate must BITE, or the arm above proves nothing.

    The same failure mode the route arm guards against: an arm that formats the string
    it just asserted on re-reads its own text. So the source is struck out of a copy of
    the shipped brief and the predicate must return False.
    """
    text = _rendered_brief()
    neutered = "\n".join(
        line for line in text.splitlines() if "origin/main" not in line
    )
    assert "origin/main" not in neutered, "the neutering did not remove the source"
    assert _brief_names_the_read_source(neutered) is False, neutered[:900]

def test_the_predicate_rejects_the_pre_fix_wording():
    """The predicate is only worth having if it rejects the text that CAUSED #439.

    That sentence — the read action with no source — is what shipped, and it is what a
    lane answered from the frozen clone against.
    """
    pre_fix = "QUESTION 1 — YOUR FRAGMENT. Read it back before answering."
    assert _brief_names_the_read_source(pre_fix) is False, pre_fix

# --------------------------------------------------------------------------------------
# #440(c) — Q3(b) reads the orphan set OFF THE RENDER instead of asking lanes to recall.
# --------------------------------------------------------------------------------------

def _brief_reads_the_orphan_set_off_the_render(text: str) -> bool:
    """#440(c) — the orphan question must point at the COMPUTED set.

    Q3(b) asked every lane to remember the cron rows it could not attribute. The
    remembered list was four rows long and wrong in both directions for weeks: it named
    `538-probe-boundary-delivery`, already attributed to `opencrabs-dev` by `deliver_to`,
    and it never once named `tamara_accounting_sync` — the one ENABLED unattributed job
    on the box. `registry/index.json` computes `counts.unattributed_jobs` on every
    render, so the brief points there.
    """
    lowered = text.lower()
    return "counts.unattributed_jobs" in lowered and "registry/index.json" in lowered

def test_the_brief_reads_the_orphan_set_off_the_render():
    """The product of #440(c): the set is COMPUTED, not remembered."""
    text = _rendered_brief()
    assert _brief_reads_the_orphan_set_off_the_render(text) is True, text[-1200:]

def test_the_orphan_set_arm_bites_when_the_pointer_is_struck_out():
    """MUTATION CONTROL for the arm above."""
    text = _rendered_brief()
    neutered = "\n".join(
        line for line in text.splitlines() if "counts.unattributed_jobs" not in line
    )
    assert "counts.unattributed_jobs" not in neutered, "the neutering did not apply"
    assert _brief_reads_the_orphan_set_off_the_render(neutered) is False, neutered[-1200:]


def _target(slug: str, session: str) -> dict:
    return {
        "slug": slug,
        "session_id": session,
        "thread_id": 1,
        "topic": "HQ",
        "status": "resolved",
    }

def _collect_args(**over: object) -> argparse.Namespace:
    base = {
        "collect": True,
        "since": "2026-10-01T05:00:00Z",
        "until": "2026-10-01T08:00:00Z",
        "collector": "collector-session",
        "recovered": None,
        "only": None,
    }
    base.update(over)
    return argparse.Namespace(**base)

ALPHA = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa"
BRAVO = "bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb"
CHARLIE = "cccccccc-3333-4333-8333-cccccccccccc"

def test_classify_answers_splits_by_notify_recovered_and_unaccounted():
    """Pure over its inputs, so the split is asserted without a store or a clock."""
    targets = [
        _target("alpha-factory", ALPHA),
        _target("bravo-factory", BRAVO),
        _target("charlie-factory", CHARLIE),
    ]
    by_notify, recovered, unaccounted = ra.classify_answers(targets, {ALPHA}, ["bravo-factory"])
    assert by_notify == ["alpha-factory"], by_notify
    assert recovered == ["bravo-factory"], recovered
    assert unaccounted == ["charlie-factory"], unaccounted

def test_classify_answers_matches_the_eight_char_short_form_the_store_also_carries():
    """The store carries BOTH header shapes; a reader that knows one reports the other as
    silence. The 2026-10-01 collector's own store held one of each."""
    targets = [_target("alpha-factory", ALPHA), _target("bravo-factory", BRAVO)]
    by_notify, recovered, unaccounted = ra.classify_answers(targets, {ALPHA[:8]}, [])
    assert by_notify == ["alpha-factory"], by_notify
    assert unaccounted == ["bravo-factory"], unaccounted

def test_an_unaccounted_target_is_never_folded_into_silence(monkeypatch, capsys):
    """The failure mode #259 exists to close: a lane that ignored the instruction must be
    VISIBLE, not lost. It is named on stderr and the run fails."""
    targets = [_target("alpha-factory", ALPHA), _target("bravo-factory", BRAVO)]
    monkeypatch.setattr(ra, "notified_senders", lambda sid, since, until: ({ALPHA}, 7, []))
    rc = ra.cmd_collect(targets, [], _collect_args())
    captured = capsys.readouterr()
    assert rc == 1, captured.out
    assert "UNACCOUNTED" in captured.err, captured.err
    assert "bravo-factory" in captured.err, captured.err

def test_collect_declares_the_population_it_measured_and_names_every_recovery(monkeypatch, capsys):
    """The round reports how many of N answered, split by route, and names each recovery."""
    targets = [
        _target("alpha-factory", ALPHA),
        _target("bravo-factory", BRAVO),
        _target("charlie-factory", CHARLIE),
    ]
    monkeypatch.setattr(
        ra, "notified_senders", lambda sid, since, until: ({ALPHA, BRAVO}, 42, [])
    )
    rc = ra.cmd_collect(targets, [], _collect_args(recovered="charlie-factory"))
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "2 by notify" in out, out
    assert "1 recovered by session read" in out, out
    assert "charlie-factory" in out, out
    assert "examined   42 session row(s)" in out, out

def test_collect_prints_the_window_it_actually_used(monkeypatch, capsys):
    """A window that is not stated is not a scope. The effective bounds are printed."""
    monkeypatch.setattr(ra, "notified_senders", lambda sid, since, until: ({ALPHA}, 3, []))
    ra.cmd_collect([_target("alpha-factory", ALPHA)], [], _collect_args())
    out = capsys.readouterr().out
    assert "2026-10-01T05:00:00Z..2026-10-01T08:00:00Z" in out, out

def test_collect_refuses_a_population_of_zero(monkeypatch, capsys):
    """NON-VACUITY: a predicate that examined nothing has reported nothing — a run over
    zero targets is a broken instrument, not a clean round, and must fail loudly."""
    monkeypatch.setattr(ra, "notified_senders", lambda sid, since, until: (set(), 0, []))
    rc = ra.cmd_collect([], [], _collect_args())
    captured = capsys.readouterr()
    assert rc == 1, captured.out
    assert "population of zero" in captured.err, captured.err

def test_collect_refuses_a_recovered_slug_that_resolves_to_no_target(monkeypatch, capsys):
    """A typo in `--recovered` must not silently shrink the recovered set."""
    monkeypatch.setattr(ra, "notified_senders", lambda sid, since, until: ({ALPHA}, 5, []))
    rc = ra.cmd_collect([_target("alpha-factory", ALPHA)], [], _collect_args(recovered="nope-factory"))
    captured = capsys.readouterr()
    assert rc == 1, captured.out
    assert "nope-factory" in captured.err, captured.err

def test_collect_refuses_without_a_collector_identity(monkeypatch, capsys):
    """The collector id is DERIVED from the environment, never declared — so an absent
    one is a refusal, not a default."""
    monkeypatch.delenv("OPENCRABS_SESSION_ID", raising=False)
    monkeypatch.setattr(ra, "notified_senders", lambda sid, since, until: ({ALPHA}, 5, []))
    rc = ra.cmd_collect([_target("alpha-factory", ALPHA)], [], _collect_args(collector=None))
    captured = capsys.readouterr()
    assert rc == 1, captured.out
    assert "OPENCRABS_SESSION_ID" in captured.err, captured.err

def test_a_reader_that_scanned_nothing_says_so_rather_than_reporting_silence(monkeypatch, capsys):
    """A reader that examined no rows has reported NOTHING — not "nobody answered". The
    count is printed so the difference is visible in the run's own output."""
    monkeypatch.setattr(ra, "notified_senders", lambda sid, since, until: (set(), 0, []))
    rc = ra.cmd_collect([_target("alpha-factory", ALPHA)], [], _collect_args(recovered="alpha-factory"))
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "examined   0 session row(s)" in out, out
    assert "0 by notify" in out, out
