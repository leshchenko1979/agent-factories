#!/usr/bin/env python3
"""Gate: the insights register's CLASS — the audience every entry names.

The register feeds two consumers, and the field exists so neither has to guess: `general`
entries are publishable content (the channel, the site, X), `implementation` entries are
internal amendments for HQ. Four invariants, and each one is a way the field can LIE
rather than merely be absent:

1. **An entry with no class is refused at the append.** An unclassified row feeds neither
   consumer while reading as a classified one, and the two are read by different surfaces.
2. **An UNKNOWN class is refused.** A typo'd value is the same defect wearing a value: it
   passes any "is it set?" check and still reaches neither consumer.
3. **`verify` REJECTS a stored blank or an unknown value, and ACCEPTS a legacy row with no
   key at all.** The register is append-only, so rows predating the field keep their shape
   and are never rewritten to invent one; a value that was WRITTEN is a different thing
   from a field that never existed, and the two must not collapse into one verdict.
4. **A backfill sets the class on a row that PREDATES the field, and nothing else.** `classify`
   adds one routing label per row, so every claim field is byte-identical afterwards — a backfill
   that quietly restated a claim would be a rewrite wearing a migration's name. It is
   all-or-nothing too: one unknown id and the register is left untouched, because a
   half-applied classification reads exactly like a complete one.

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


# --- classify: the backfill, and the ways it must refuse ------------------------------

def _legacy_register(register, rows):
    """Write rows as the register held them BEFORE the field existed — no class key at all."""
    register.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                        encoding="utf-8")
    return register.read_text(encoding="utf-8")


def test_classify_sets_the_class_and_leaves_every_claim_byte_identical(tmp_path, monkeypatch):
    """The backfill adds ONE key. A restated claim would be a rewrite, not a migration."""
    register = _redirect(tmp_path, monkeypatch)
    before = _legacy_register(register, [_row(1), _row(2)])

    changes = insights.classify_insights({"row-1": "general", "row-2": "implementation"})

    assert [c[0] for c in changes] == ["row-1", "row-2"]
    assert [c[1] for c in changes] == [None, None], (
        "a legacy row's old class is ABSENT, never the empty string — the two are different things")
    stored = [json.loads(l) for l in register.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert [r["class"] for r in stored] == ["general", "implementation"]

    # Strip the added key and the file must be EXACTLY what it was. The invariant is
    # asserted rather than inspected, because reading it back would not fail on a drift.
    stripped = "".join(
        json.dumps({k: v for k, v in r.items() if k != "class"}, ensure_ascii=False) + "\n"
        for r in stored)
    assert stripped == before, "classify must not touch a claim field"


def test_classify_refuses_an_unknown_id_and_writes_nothing(tmp_path, monkeypatch):
    register = _redirect(tmp_path, monkeypatch)
    _legacy_register(register, [_row(1), _row(2)])
    before = register.read_text(encoding="utf-8")

    try:
        insights.classify_insights({"row-1": "general", "row-nope": "implementation"})
    except ValueError as exc:
        assert "row-nope" in str(exc)
    else:
        raise AssertionError("an unknown id was accepted")

    assert register.read_text(encoding="utf-8") == before, (
        "a refused classify must leave the register byte-identical")


def test_classify_refuses_an_unknown_class_and_writes_nothing(tmp_path, monkeypatch):
    register = _redirect(tmp_path, monkeypatch)
    _legacy_register(register, [_row(1)])
    before = register.read_text(encoding="utf-8")

    for unknown in ("General", "impl", "", "genera"):
        try:
            insights.classify_insights({"row-1": unknown})
        except ValueError as exc:
            assert "class" in str(exc)
        else:
            raise AssertionError(f"an unknown class {unknown!r} was accepted")
    assert register.read_text(encoding="utf-8") == before


def test_classify_leaves_rows_absent_from_the_mapping_untouched(tmp_path, monkeypatch):
    """Backfilling 31 rows must not rewrite the rows it was not asked about."""
    register = _redirect(tmp_path, monkeypatch)
    _legacy_register(register, [_row(1), _row(2), _row(3)])

    insights.classify_insights({"row-2": "implementation"})

    stored = [json.loads(l) for l in register.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert "class" not in stored[0] and "class" not in stored[2], "an untouched row gained a key"
    assert stored[1]["class"] == "implementation"


def test_classify_inserts_the_key_without_reordering_the_row(tmp_path, monkeypatch):
    """A backfill is ADDITIVE: the row keeps its own key order and gains one label."""
    register = _redirect(tmp_path, monkeypatch)
    original = _row(1)
    _legacy_register(register, [original])

    insights.classify_insights({"row-1": "general"})

    row = json.loads(register.read_text(encoding="utf-8").strip())
    assert [k for k in row if k != "class"] == list(original.keys()), (
        "every pre-existing key keeps the position it already had")
    assert list(row.keys()).index("class") == list(original.keys()).index("ts") + 1, (
        "class lands at its canonical position, right after ts")
    assert insights.verify_insights()[0], "a backfilled register must verify clean"


def test_classify_refuses_an_empty_mapping(tmp_path, monkeypatch):
    register = _redirect(tmp_path, monkeypatch)
    _legacy_register(register, [_row(1)])
    try:
        insights.classify_insights({})
    except ValueError as exc:
        assert "no classifications" in str(exc)
    else:
        raise AssertionError("an empty mapping was accepted")
    assert "class" not in register.read_text(encoding="utf-8")
