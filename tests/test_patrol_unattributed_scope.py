"""Gate: a residual bucket states what was MEASURED, never a box-wide claim (#563).

THE DEFECT, measured 2026-11-08. Three print sites rendered the rows a single factory could
not attribute as "unattributed":

    cron-thinness    {cov['rows_unattributed']} unattributed
    duty-receipt     {cov['jobs_unattributed']} unattributed
    pacemaker-presence ({cov['unattributed_rows']} unattributed)

Every one traces to ONE function, `attribute_rows(rows, prefixes)`, called with THIS
factory's own `declared_prefixes()`. So each measured "matches no prefix THIS factory
declares" and printed it as though nobody declares them. On this box that bucket held 31
rows of which **23 carry a PEER's declared prefix** and 8 carry none — 74 % of the bucket
was attributed, so the sentence was a 3.9x overstatement, printed three times.

WHY A GATE AND NOT A REWORDING. The misnomer also lived in the FUNCTION's own docstring
("rows attributed to NOBODY"), which is the surface the next reader consults before the
prints, so a fix confined to the three sites would have left the wrong vocabulary teaching
the next author to reintroduce it. Both halves are asserted here.

THE CONTROL IS THE POINT. `test_the_old_global_sentence_fails_this_predicate` runs the
predicate over the sentence the tree used to print and requires it to be REJECTED. Without
it every arm below would pass just as well against a predicate that accepts any string.

NO VERDICT HERE IS DECIDED BY THIS BOX: the split is driven through the leg's own
injection points and the pure helper, never through the live cron table.
"""

# --- imports ---------------------------------------------------------------
from __future__ import annotations

import re
from pathlib import Path

from patrol_fixtures import REPO, RUNNER  # noqa: F401

# --- the leg's own helpers --------------------------------------------------
_READ_AT = "2026-11-08T13:00:00Z"

# The live shape measured on this box, in miniature: two rows carrying a peer's declared
# prefix, one carrying none. Names are REAL prefixes (see `registry/fleet.json`) so the
# discrimination is exercised through `job_owner`, not through a fixture-only convention.
_PEER_ROWS = [
    {"name": "inferhub-daily-report", "home": "ops"},
    {"name": "miidas-hq-daily-trigger", "home": "ops"},
]
_NO_PREFIX_ROWS = [{"name": "tamara_accounting_sync", "home": "family"}]
_RESIDUAL = _PEER_ROWS + _NO_PREFIX_ROWS

# What the tree printed before this fix, verbatim in shape.
_OLD_SENTENCE = f"{len(_RESIDUAL)} unattributed"

# The declared-prefix table, INJECTED. The real one is the live fleet manifest, which
# declares factories on this box and none in the shipped tree — so a fixture keyed on the
# real prefixes passes only where it was written. These are the same two buckets the box
# measured (23 peer-prefixed, 8 prefix-less), in miniature.
_PREFIXES = {"peer-factory": ("inferhub-", "miidas-")}


def _owner(job: dict, _uuid_owner: dict, _chat_owner: dict) -> tuple[str | None, str]:
    """The discrimination the split must perform, driven by the table above."""
    name = str(job.get("name") or "")
    for slug, prefixes in _PREFIXES.items():
        if any(name.startswith(p) for p in prefixes):
            return slug, "name prefix"
    return None, "unattributed"


def _problems(sentence: str, *, split, count: int) -> list[str]:
    """The predicate under test: what a residual sentence MUST and MUST NOT say.

    Kept as a plain function rather than inlined into the arms so the control can run the
    SAME predicate over the OLD sentence — a control that re-implemented the check would
    prove nothing about the check.
    """
    problems: list[str] = []
    if "not attributed to this factory" not in sentence:
        problems.append(
            "the sentence does not scope its claim to THIS factory, so a single-factory "
            "prefix test reads as a statement about the whole box (#563)"
        )
    if "unattributed" in sentence:
        problems.append(
            "the sentence still uses the bare word 'unattributed', which is the global "
            "claim this gate exists to forbid"
        )
    if split is None:
        if "NOT MEASURED" not in sentence:
            problems.append(
                "no split was measured and the sentence does not say so — a zeroed split "
                "would report a measurement nobody took"
            )
        return problems
    peer, none = len(split["peer_prefix"]), len(split["no_prefix"])
    if f"{peer} carry a peer's declared prefix" not in sentence:
        problems.append(f"the peer-prefix count ({peer}) is not stated")
    if f"{none} carry none" not in sentence:
        problems.append(f"the no-prefix count ({none}) is not stated")
    total = peer + none + len(split.get("self_resolved") or [])
    if total != count:
        problems.append(
            f"the split sums to {total} but the bucket holds {count} — the parts must sum "
            f"to the whole or one of them is wrong"
        )
    return problems


# --- the sentence and its split ---------------------------------------------
def test_the_sentence_states_the_split_it_measured() -> None:
    """The live shape: 3 residual rows, 2 carrying a peer's prefix, 1 carrying none."""
    split = RUNNER.unattributed_split(_RESIDUAL, factory_slug="meta-factory", owner_fn=_owner)
    assert len(split["peer_prefix"]) == 2, split
    assert len(split["no_prefix"]) == 1, split
    assert split["self_resolved"] == [], split
    sentence = RUNNER.unattributed_sentence(split)
    assert _problems(sentence, split=split, count=len(_RESIDUAL)) == [], sentence
    assert sentence.startswith("3 not attributed to this factory"), sentence


def test_the_old_global_sentence_fails_this_predicate() -> None:
    """THE CONTROL. The sentence the tree used to print must be REJECTED, on two grounds.

    Without this arm the predicate above could accept anything and every other arm in this
    file would still pass — the decoration this repo refuses.
    """
    problems = _problems(
        _OLD_SENTENCE,
        split=RUNNER.unattributed_split(_RESIDUAL, factory_slug="meta-factory", owner_fn=_owner),
        count=len(_RESIDUAL),
    )
    assert problems, "the old sentence PASSED — the predicate is not testing the claim"
    joined = " | ".join(problems)
    assert "does not scope its claim" in joined, joined
    assert "bare word 'unattributed'" in joined, joined


def test_a_missing_split_is_stated_never_zeroed() -> None:
    """A leg that returns a count but no split has measured nothing — say so (#242's class)."""
    sentence = RUNNER.unattributed_sentence(None, count=31)
    assert "NOT MEASURED" in sentence, sentence
    assert "0 carry a peer's declared prefix" not in sentence, sentence
    # And the predicate refuses it too, so a leg that regresses to a bare count is caught.
    assert _problems(sentence, split=None, count=31) == [], sentence
    zeroed = "31 not attributed to this factory (0 carry a peer's declared prefix, 0 carry none)"
    assert _problems(zeroed, split=None, count=31), "a zeroed split passed as measured"


def test_a_self_resolved_row_is_reported_as_a_reader_disagreement() -> None:
    """The third bucket is a DISAGREEMENT, not a population: two readers, two prefix sets.

    Measured 0 on this box, so it is the branch that would otherwise never be exercised —
    which is exactly why it needs an arm: an unexercised branch is an unverified one.
    """
    split = {"peer_prefix": ["peer-a"], "no_prefix": [], "self_resolved": ["factory-odd"]}
    sentence = RUNNER.unattributed_sentence(split)
    assert "2 not attributed to this factory" in sentence, sentence
    assert "1 resolve to THIS factory by prefix" in sentence, sentence
    assert "the two attribution readers disagree" in sentence, sentence
    assert _problems(sentence, split=split, count=2) == [], sentence


# --- the three legs carry the split -----------------------------------------
class _Predicate:
    """A stub predicate: no problems, so the arm measures the COVERAGE and not the verdict."""

    @staticmethod
    def pacemaker_problems(rows):
        return [], []

    @staticmethod
    def row_wake(row):
        return "session:probe"


def test_the_cron_thinness_leg_carries_the_split() -> None:
    """The coverage key the first print site reads must exist and be MEASURED."""
    leg = RUNNER.cron_thinness_leg(
        _RESIDUAL, ["probe-home"], [], ["factory-"], read_at=_READ_AT,
        predicate=_Predicate(),
    )
    cov = leg["coverage"]
    assert cov["rows_unattributed"] == 3, cov
    split = cov["rows_unattributed_split"]
    # The leg calls the split with the LIVE reader, which resolves nothing in the shipped
    # tree, so this arm asserts the SHAPE it must carry and the count it must sum to --
    # the discrimination itself is asserted against the injected table in the arms above.
    assert set(split) == {"peer_prefix", "no_prefix", "self_resolved"}, split
    assert sum(len(v) for v in split.values()) == 3, split
    # And the sentence the renderer builds from it is the corrected one.
    sentence = RUNNER.unattributed_sentence(split, count=cov["rows_unattributed"])
    assert _problems(sentence, split=split, count=3) == [], sentence


def test_the_split_is_measured_by_the_SAME_reader_the_render_uses() -> None:
    """MUTATION: neuter `registry_render.job_owner` and the DEFAULT path follows it.

    A split derived from anything else (a second prefix table, a name heuristic) would
    ignore the mutation, and the two readers could then disagree while both read clean.
    The patch intercepts regardless of what the manifest declares, so this arm holds in
    the shipped tree as well as here.
    """
    import registry_render

    original = registry_render.job_owner
    calls: list[str] = []

    def _recorder(job, uuid_owner, chat_owner):
        calls.append(str(job.get("name") or ""))
        return None, "mutated"

    try:
        registry_render.job_owner = _recorder
        split = RUNNER.unattributed_split(_RESIDUAL, factory_slug="meta-factory")
        assert split["peer_prefix"] == [], split
        assert len(split["no_prefix"]) == 3, split
    finally:
        registry_render.job_owner = original
    assert calls == [r["name"] for r in _RESIDUAL], (
        "the default path did not call registry_render.job_owner for every row -- the split "
        f"is not measured by the reader the render uses: {calls}"
    )


# --- the vocabulary, not only the prints ------------------------------------
def test_the_function_that_produces_the_bucket_does_not_call_it_nobody() -> None:
    """The misnomer lived in `attribute_rows`' own docstring, the surface read FIRST.

    A fix confined to the three print sites leaves the next author reading "attributed to
    NOBODY" above the function and reintroducing it at the fourth site.
    """
    source = (REPO / "tools" / "patrol_host_state.py").read_text(encoding="utf-8")
    assert "rows attributed to NOBODY" not in source, (
        "attribute_rows' docstring still calls the residual 'attributed to NOBODY' — the "
        "function's own vocabulary is the surface the next reader consults first (#563)"
    )
    assert "rows NOT attributed to it" in source, "the corrected docstring is missing"


_BARE_WORD = re.compile(r"\}\s*\(?\s*unattributed\b")


def _bare_word_sites(source: str) -> list[str]:
    """Print lines that render a COUNT followed by the bare word, in any of its shapes.

    The shapes matter: the three live sites rendered `{cov[...]} unattributed`,
    `{cov[...]} unattributed` and `({cov[...]} unattributed), across`, so a pattern keyed
    on a trailing quote catches two of three. Measured against HEAD, this one catches 3 of
    3 and 0 after the fix — the sweep is a predicate with a control, not a decoration.
    """
    return [
        line.strip()
        for line in source.splitlines()
        if 'f"' in line and _BARE_WORD.search(line) and "unattributed_sentence" not in line
    ]


def test_no_print_site_renders_the_bare_word() -> None:
    """The three sites, swept at the SOURCE — a fourth site is caught by the same arm."""
    source = (REPO / "tools" / "patrol_host_state.py").read_text(encoding="utf-8")
    offenders = _bare_word_sites(source)
    assert offenders == [], (
        "a print site still renders a bare 'unattributed' count instead of the measured "
        f"split: {offenders}"
    )


def test_the_source_sweep_catches_the_three_old_sites() -> None:
    """THE CONTROL FOR THE SWEEP. All THREE shapes the tree used to print must be caught.

    Two of the three end the f-string after the word and one continues with `), across`, so
    a sweep keyed on a trailing quote silently missed a third of its own population — which
    is the same class of defect this file exists for, one layer out.
    """
    old = (
        '            f"{cov[\'rows_unattributed\']} unattributed"\n'
        '            f"{cov[\'jobs_unattributed\']} unattributed"\n'
        '            f"({cov[\'unattributed_rows\']} unattributed), across "\n'
    )
    assert len(_bare_word_sites(old)) == 3, _bare_word_sites(old)

if __name__ == "__main__":
    # PYTEST form: these are module-level arms, so a bare run would exit 0 having asserted
    # NOTHING — a gate whose only exits are barred (#542).
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
