#!/usr/bin/env python3
"""Gate: the insights register's CLASS — the audience every entry names.

The register feeds two consumers, and the field exists so neither has to guess: `general`
entries are publishable content (the channel, the site, X), `implementation` entries are
internal amendments for HQ. Three invariants, and each one is a way the field can LIE
rather than merely be absent:

1. **An entry with no class is refused at the append.** An unclassified row feeds neither
   consumer while reading as a classified one, and the two are read by different surfaces.
2. **An UNKNOWN class is refused.** A typo'd value is the same defect wearing a value: it
   passes any "is it set?" check and still reaches neither consumer.
3. **`verify` REJECTS a stored blank or an unknown value, and ACCEPTS a legacy row with no
   key at all.** The register is append-only, so rows predating the field keep their shape
   and are never rewritten to invent one; a value that was WRITTEN is a different thing
   from a field that never existed, and the two must not collapse into one verdict.

**Fixture-driven by construction, and that is load-bearing.** Every probe redirects
`INSIGHTS_PATH` and `LOCK_PATH` into a temporary directory, because the live register is
production data: a probe that appended to `evidence/insights.jsonl` to test the append
would be writing the artifact it measures.

Run:  python3 -m pytest tests/test_insights_class.py -q
Exit: 0 the class is required, constrained and verified; non-zero otherwise.
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import insights  # noqa: E402


def _redirect(tmp_path, monkeypatch):
    """Point the module at a throwaway register, never the live one."""
    register = tmp_path / "insights.jsonl"
    monkeypatch.setattr(insights, "INSIGHTS_PATH", register)
    monkeypatch.setattr(insights, "LOCK_PATH", tmp_path / ".insights.lock")
    return register


def _append(**over):
    kwargs = dict(
        slug="probe-insight",
        topic="A probe",
        stage="stage-1",
        naive_assumption="naive",
        empirical_reality="measured",
        mechanism="structural",
        author="Surveys",
        insight_class="general",
    )
    kwargs.update(over)
    return insights.append_insight(**kwargs)


def test_append_records_each_allowed_class(tmp_path, monkeypatch):
    register = _redirect(tmp_path, monkeypatch)
    for value in insights.ALLOWED_CLASSES:
        entry = _append(slug=f"probe-{value}", insight_class=value)
        assert entry["class"] == value
    stored = [json.loads(l) for l in register.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert [r["class"] for r in stored] == insights.ALLOWED_CLASSES, (
        "the class must reach the PERSISTED row, not only the returned dict")


def test_append_refuses_a_missing_class(tmp_path, monkeypatch):
    register = _redirect(tmp_path, monkeypatch)
    for missing in ("", "   "):
        try:
            _append(insight_class=missing)
        except ValueError as exc:
            assert "class" in str(exc)
        else:
            raise AssertionError(f"a missing class {missing!r} was accepted")
    assert not register.exists(), "a refused append must write nothing"


def test_append_refuses_an_unknown_class(tmp_path, monkeypatch):
    register = _redirect(tmp_path, monkeypatch)
    for unknown in ("General", "impl", "marketing", "genera"):
        try:
            _append(insight_class=unknown)
        except ValueError as exc:
            assert "class" in str(exc)
        else:
            raise AssertionError(f"an unknown class {unknown!r} was accepted")
    assert not register.exists(), "a refused append must write nothing"


def _row(n, **over):
    row = {"n": n, "id": f"row-{n}", "ts": "2026-09-14T08:25:08Z", "topic": "t",
           "stage": "stage-1", "naive_assumption": "a", "empirical_reality": "b",
           "mechanism": "c", "author": "Surveys"}
    row.update(over)
    return row


def test_verify_rejects_a_stored_blank_or_unknown_and_accepts_a_legacy_row(tmp_path, monkeypatch):
    register = _redirect(tmp_path, monkeypatch)

    # A row predating the field carries NO key: history is not rewritten, so this is clean.
    legacy = _row(1)
    register.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
    ok, errors = insights.verify_insights()
    assert ok, f"a legacy row must stay valid, got {errors}"

    # The SAME row with an EMPTY class is a defect: it was written and it says nothing.
    blank = _row(2, **{"class": ""})
    register.write_text(json.dumps(legacy) + "\n" + json.dumps(blank) + "\n", encoding="utf-8")
    ok, errors = insights.verify_insights()
    assert not ok, "a stored blank class must be rejected"
    assert any("class" in e for e in errors), errors

    # An UNKNOWN value is the same defect wearing a value.
    unknown = _row(2, **{"class": "marketing"})
    register.write_text(json.dumps(legacy) + "\n" + json.dumps(unknown) + "\n", encoding="utf-8")
    ok, errors = insights.verify_insights()
    assert not ok, "an unknown stored class must be rejected"
    assert any("class" in e for e in errors), errors


def test_the_two_classes_are_the_whole_vocabulary():
    """An AUDIENCE split, deliberately coarse — a finer value would be a second axis."""
    assert insights.ALLOWED_CLASSES == ["general", "implementation"]
