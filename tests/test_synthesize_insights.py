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
