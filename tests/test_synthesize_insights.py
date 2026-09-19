#!/usr/bin/env python3
"""Tests for tools/synthesize_insights.py."""

import json
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
    insights = synthesize_insights()
    assert len(insights) >= 1
    ids = {i.id for i in insights}
    assert "survey-requisite-variety" in ids
    for ins in insights:
        assert isinstance(ins, SynthesizedInsight)
        assert ins.topic
        assert ins.naive_assumption
        assert ins.empirical_reality
        assert ins.mechanism
        assert ins.literature
        assert 0.0 <= ins.confidence <= 1.0


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

