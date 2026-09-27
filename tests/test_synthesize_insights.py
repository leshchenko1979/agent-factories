#!/usr/bin/env python3
"""Gate: the insights synthesizer's own behaviour — its classifier's word predicate and its
dedup guard's read of the PERSISTED file.

Two invariants, both born as defects in the tool this gate's subject is:

1. **The classifier matches WORDS, not substrings (#168).** It tests the union of the
   entry's Defect / Root cause / Prevented-by columns against an ordered key list, and the
   chain is `elif` — so a key that matches a word merely CONTAINING it does not merely add a
   false positive, it DIVERTS that entry from its true bucket, which is then never reached.
   The live table had `lock` matching `block` (18 rows) and `clock` (6), and `race` matching
   `trace`, `traceback`, `traceable` and `braces` (7 — the instance #168 was filed for). The
   predicate is a LEFT boundary: a both-sides boundary would break the `concurr` key
   outright, since the words it exists to catch are `concurrency` and `concurrent`.
2. **The dedup guard reads the persisted file (#166).** Its first version built its id set
   from the list it had just assembled IN THE SAME CALL, so it could never fire — an id
   absent from that list is by construction absent from a set built from it. `INSIGHTS_PATH`
   was defined in the module and read nowhere. The duplicate it let through was caught by
   hand at the append step (the weekly run's own record: `survey-requisite-variety` was
   already at `n=17`), and at the fix all THREE ids the tool emitted were already persisted.

**Both proofs are FIXTURE-driven, and that is load-bearing.** On the live tree every id is
already persisted and the classifier's live table carries no containment instance, so a
live-driven probe would return the same answer under the correct predicate and the defect —
the arms would be indistinguishable and the gate would pass VACUOUSLY. This factory has
shipped that failure twice (the hygiene guard, the #137 port), which is why the file
contents are what these probes vary.

Declared here rather than left to a by-hand `pytest` run: a probe the audit never executes
is dead text, and the two items above closed on non-vacuity that nothing would have run.

Run:  python3 -m pytest tests/test_synthesize_insights.py -q
Exit: 0 the classifier matches words and the guard reads the file; non-zero otherwise.
"""

import json
import shutil
import tempfile
import pytest
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

from synthesize_insights import (
    mine_rework_defects,
    mine_ledger_telemetry,
    synthesize_insights,
    FrictionPattern,
    SynthesizedInsight,
)


def test_mine_rework_defects():
    patterns = mine_rework_defects()
    assert isinstance(patterns, list)
    for p in patterns:
        assert isinstance(p, FrictionPattern)
        assert p.occurrences >= 1
        assert p.literature_grounding
        assert p.suggested_mechanism


def test_mine_ledger_telemetry():
    patterns = mine_ledger_telemetry()
    assert isinstance(patterns, list)
    for p in patterns:
        assert isinstance(p, FrictionPattern)
        assert p.literature_grounding


def test_synthesize_insights():
    """The synthesizer returns WELL-FORMED insights — and only ones not already persisted.

    The shape checks below hold for whatever it returns, including nothing. THE `>= 1` AND
    `"survey-requisite-variety" IN IDS` ASSERTIONS THIS TEST USED TO CARRY PINNED THE DEFECT
    (#166): they required the tool to re-emit an id that was already in the file, so the
    tautological dedup guard was the behaviour under test. On the live tree the correct
    answer is now EMPTY — every id the tool can synthesize is already persisted — so a
    non-empty expectation would fail a working tool. Both directions are pinned in the
    fixture-driven probes below instead, where the file's contents are known.
    """
    insights = synthesize_insights()
    for ins in insights:
        assert isinstance(ins, SynthesizedInsight)
        assert ins.topic
        assert ins.naive_assumption
        assert ins.empirical_reality
        assert ins.mechanism
        assert ins.literature
        assert 0.0 <= ins.confidence <= 1.0


def test_probe_the_dedup_guard_reads_the_persisted_file_not_its_own_list():
    """#166, both directions, driven from a fixture.

    THE DEFECT. The guard built `existing_ids` from the list it had JUST assembled in the
    same call, so it was a tautology: an id absent from that list is by construction absent
    from a set built from it, and the guard could never fire. `INSIGHTS_PATH` was defined in
    the module and read nowhere. The duplicate it let through was caught by hand at the
    append step (the weekly run's record: `survey-requisite-variety` was already at `n=17`).

    A probe driven from the LIVE tree cannot show this: on the live tree every id is
    persisted, so a filter and a tautology both return nothing and the arms are
    indistinguishable. The file's contents are what the predicate reads, so they are what
    the probe varies.
    """
    import json as _json
    import synthesize_insights as S

    real_rework = S.REWORK_PATH
    real_insights = S.INSIGHTS_PATH
    try:
        with tempfile.TemporaryDirectory(prefix="dedup-probe-") as tmp:
            root = Path(tmp)
            evidence = root / "evidence"
            evidence.mkdir()
            # The rework table drives which patterns fire; reuse the live one so the
            # pattern-mapped insights are present to be filtered.
            shutil.copy(real_rework, evidence / "rework.md")
            insights_path = evidence / "insights.jsonl"
            S.REWORK_PATH = evidence / "rework.md"
            S.INSIGHTS_PATH = insights_path

            # ARM 1 — an EMPTY file: everything the tool synthesizes is new, so it emits.
            insights_path.write_text("", encoding="utf-8")
            fresh = {i.id for i in S.synthesize_insights()}
            assert fresh, "an empty insights file must not suppress every insight"
            assert "survey-requisite-variety" in fresh, fresh

            # ARM 2 — the SAME ids already persisted: none may be re-emitted.
            insights_path.write_text(
                "".join(_json.dumps({"n": i, "id": rid}) + "\n"
                        for i, rid in enumerate(sorted(fresh), start=1)),
                encoding="utf-8",
            )
            again = {i.id for i in S.synthesize_insights()}
            assert again == set(), (
                "the guard re-emitted ids already present in the file: "
                f"{sorted(again)}"
            )

            # ARM 3 — a PARTIALLY populated file: the missing ids still come through, so
            # arm 2 is a filter and not a tool that emits nothing once the file is touched.
            one = sorted(fresh)[0]
            insights_path.write_text(
                _json.dumps({"n": 1, "id": one}) + "\n", encoding="utf-8"
            )
            partial = {i.id for i in S.synthesize_insights()}
            assert one not in partial, partial
            assert partial == fresh - {one}, (partial, fresh)
    finally:
        S.REWORK_PATH = real_rework
        S.INSIGHTS_PATH = real_insights


def test_probe_the_classifier_matches_words_not_substrings():
    """#168, both directions: the key must match the WORD, never a word that contains it.

    THE DEFECT. The classifier tested the union of Defect/Root cause/Prevented-by with a
    raw `in`, so it counted WORDS rather than events: `lock` matched `block` and `clock`,
    and `race` matched `trace`, `traceback`, `traceable` and `braces`. The chain being
    `elif`, each such entry was DIVERTED from its true bucket and never reached it — 7
    entries fired on `race` alone in the live table, and the `lock` family was 24 more,
    measured when this predicate replaced the substring test (30 concurrency entries
    became 10).

    A BOTH-SIDES word boundary is not the fix either, and the probe pins that too: the
    `concurr` key exists to catch `concurrency` and `concurrent`, neither of which ends at
    `concurr`, so a trailing boundary drops them and the key silently stops matching.
    """
    import synthesize_insights as S

    # REAL forms: the key itself, and its inflections — these MUST fire.
    for text, expected in [
        ("a lock on the state file", "lock"),
        ("locking the ledger", "lock"),
        ("fcntl.flock on the file", "flock"),
        ("a race condition in the runner", "race"),
        ("races between writers", "race"),
        ("concurrency probe", "concurr"),
        ("concurrent writers", "concurr"),
        ("concurrently modified state", "concurr"),
    ]:
        assert S.key_fires(expected, text), f"{expected!r} must fire on {text!r}"

    # CONTAINMENT: a word that merely CONTAINS the key must NOT fire. This is the defect.
    for text, key in [
        ("a blocked writer", "lock"),
        ("the clock advanced", "lock"),
        ("blocker resolved", "lock"),
        ("a trace of the calls", "race"),
        ("a traceback in the log", "race"),
        ("traceable provenance", "race"),
        ("braces in the format string", "race"),
    ]:
        assert not S.key_fires(key, text), (
            f"{key!r} must NOT fire on {text!r} — that word merely contains it"
        )


def test_probe_every_entry_reports_the_key_that_put_it_there():
    """#168's second half: the output says WHY, not only HOW MANY.

    A bucket count cannot distinguish a real match from a containment artefact; the firing
    token can, and it is what a reader needs to audit the classification. Every classified
    entry therefore carries its key, and the key must actually fire on that entry's text.
    """
    import synthesize_insights as S

    entries = S.classify_rework_entries()
    assert entries, "the live rework table must classify to something"
    for entry in entries:
        assert set(entry) == {"category", "key", "defect", "mined"}, entry
        if entry["category"] == "generic":
            assert entry["key"] is None, entry
        else:
            assert entry["key"], f"a classified entry must name its key: {entry}"

    # The key is validated against the RECORDED MINED TEXT, never the defect cell alone
    # (#194). Validating against the defect cell is a scope mismatch between two surfaces
    # of one predicate, and it fails toward a FALSE RED on correct prose: the classifier
    # mines the Defect, Root cause and Prevented-by cells, so an entry whose key fires in
    # its Root-cause cell classifies normally and red a probe reading the defect cell.
    for entry in entries:
        if entry["key"]:
            assert S.key_fires(entry["key"], entry["mined"]), entry


def test_the_key_is_validated_against_the_RECORDED_mined_text_never_the_defect_cell():
    """#194: the classifier MINES three cells and must RECORD what it mined.

    The defect is a scope mismatch between two surfaces of ONE predicate: the classifier
    builds its text from the Defect, Root cause and Prevented-by cells, while the probe
    validated the key against the Defect cell ALONE. An entry whose key fires only in its
    Root-cause cell therefore classified normally and red this gate — a FALSE RED ON
    CORRECT PROSE, measured live (#142: category concurrency_locking, key=race, mined from
    a Root-cause cell reading "race guard", with no "race" anywhere in the defect cell).

    Driven from a CONSTRUCTED row rather than from live prose, because the shipped probe
    could not fail on this shape until such a row existed — before #142 landed there was
    none, which is why the gate stayed green while the mismatch was already there.
    """
    import synthesize_insights as S

    defect = "the leg skipped a round it should have judged"
    cause = "the race guard fired before the round was stamped"
    prevented = "a left-boundary predicate now rejects the containment form"
    mined = f"{defect} {cause} {prevented}".lower()

    category, key = S.classify_defect(mined)
    assert key == "race", f"the fixture must classify through the Root-cause cell: {category}/{key}"

    # THE BITE, both halves: the key fires in the mined text (so the record is the right
    # thing to validate against) and NOT in the defect cell alone (so the old form reds on
    # this correct row, and the fixture is not vacuous).
    assert S.key_fires(key, mined), "the key must fire on the recorded mined text"
    assert not S.key_fires(key, defect.lower()), (
        "the fixture is vacuous unless the key fires ONLY outside the defect cell"
    )

def test_every_entry_records_the_mined_text_and_the_record_is_faithful():
    """#194's second half: the RECORD is what makes the class auditable.

    The recorded text must be the text the classifier actually read, built from the row's
    own cells in order — a record that merely resembles it would put the same gap back one
    layer down. This is also why no entry's category can move when the record is added: the
    mined expression is untouched, and every recorded text begins with the defect cell it
    was built from, so the population only ever WIDENED relative to the defect cell alone.
    """
    import synthesize_insights as S

    entries = S.classify_rework_entries()
    assert entries, "the live rework table must classify to something"
    for entry in entries:
        assert entry["mined"].startswith(entry["defect"].lower()), entry

def test_cli_execution():
    import subprocess
    cmd = [sys.executable, str(REPO / "tools" / "synthesize_insights.py"), "--json"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(res.stdout)
    assert data["healthy"] is True
    assert "friction_patterns" in data
    assert "synthesized_insights" in data

# The measured shape of ledger `n=586`: a `run` row whose detail QUOTES `n=303`'s
# canonical trailer as evidence. Its detail ends in prose, so its own canonical trailer
# is EMPTY — nothing in it is a measurement this row took. Live, the quotation carries
# `turns=1`, below the alarm's `>3` threshold, so today it changes a READ and not a
# COUNT. The probe sets the quoted value ABOVE the threshold: that is the future row
# the #99 ruling names, and it is the half a read-only disagreement cannot show.
_QUOTED_TRAILER = (
    "REWORK ENTRY LANDED for #91 in evidence/rework.md - entry 44, appended directly "
    "after #87's row so the Entries table stays one contiguous table under one header. "
    "The row's canonical trailer reads cost_usd=2.7719 tokens_out=9956523 turns=16 and "
    "that quotation is evidence, not a measurement this row took."
)

def _run_row(n: int, detail: str) -> dict:
    return {
        "n": n,
        "ts": "2026-09-19T00:00:00Z",
        "event": "run",
        "actor": "worker",
        "subject": "probe",
        "detail": detail,
    }

def test_probe_the_telemetry_reader_is_the_shared_predicate():
    """#99 leg (a): this tool reads telemetry through the ONE shared predicate.

    The private scan it replaced was `re.search(r"turns=(\\d+)", detail)` over the WHOLE
    detail, so it took a QUOTATION for a measurement. A lookalike re-implementation
    would satisfy the behavioural probe below and still leave the class open, so the
    binding is asserted by IDENTITY — and the private scanner's import is asserted
    ABSENT, because the defect is the scan, not merely its output.
    """
    import field_predicate
    import synthesize_insights

    assert (
        synthesize_insights._fields.declared_telemetry is field_predicate.declared_telemetry
    ), "the tool must call the shared predicate, not a local re-implementation"
    assert not hasattr(synthesize_insights, "re"), (
        "the private `re` scan must be gone: a whole-detail regex reads prose as data"
    )

def test_probe_a_quoted_trailer_does_not_count_as_a_run(tmp_path, monkeypatch):
    """Two rows DECLARE `turns=5`; a third only QUOTES it mid-prose. The alarm counts 2.

    The quoted row is the measured `n=586` shape, and the assertion is the count of 2 —
    a count of 3 is the private scan's reading, and it is the defect this leg closes.
    """
    import synthesize_insights

    ledger = tmp_path / "ledger.jsonl"
    rows = [
        _run_row(1, "Ran the gate. duration=1845s; turns=5"),
        _run_row(2, "Ran the gate. turns=5"),
        _run_row(3, _QUOTED_TRAILER),
    ]
    ledger.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    monkeypatch.setattr(synthesize_insights, "LEDGER_PATH", ledger)
    patterns = synthesize_insights.mine_ledger_telemetry()

    high = [p for p in patterns if p.category == "high_turn_convergence"]
    assert high, "two declaring rows must trip the alarm"
    assert high[0].occurrences == 2, (
        f"a QUOTED turns= must not count as a run: expected 2, got {high[0].occurrences}"
    )

