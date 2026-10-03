#!/usr/bin/env python3
"""Gate: the insights register's AUDIENCE — the reader a claim has outside the factory.

The owner re-cut the routing axis on 2026-10-02: *"I was wrong when I told that an issue
can be either general or implementation-based. Instead, the axis should be — marketable or
not."* The replacement is `audience: public | internal`, and the rename is not cosmetic.
`class` asked *what the claim requires of its reader* and was READ as answering *whether
anyone would want to read it* — so an author asserted a routing the consumer then refused,
and 8 of the 14 `general` rows sent to the content funnel came back refused with the
funnel's own words: *"class is not an audience axis."*

`audience` is a PROPERTY of the claim — does it have a reader OUTSIDE this factory? — never
the funnel's verdict on it. That is what makes a refusal non-contradictory: a refused row
says *"public audience, not fit to publish"*, which is two facts, not a field lying.

Four invariants, and each one is a way the field can LIE rather than merely be absent:

1. **An entry with no audience is refused at the append.** A row that names no reader
   outside the factory is routed to no publishing surface while reading as a routed one.
2. **An UNKNOWN audience is refused.** A typo'd value is the same defect wearing a value:
   it passes any "is it set?" check and still routes the row nowhere.
3. **`verify` REJECTS a stored blank or an unknown value, and ACCEPTS a legacy row with no
   key at all.** The register is append-only, so rows predating the field keep their shape
   and are never rewritten to invent one; a value that was WRITTEN is a different thing
   from a field that never existed, and the two must not collapse into one verdict.
4. **`set_routing` backfills the GROUP on a row that PREDATES it, and nothing else.**
   `audience` and `process` are atomic — both are required at the append — so they land in
   ONE transaction, and every claim field is byte-identical afterwards: a backfill that
   quietly restated a claim would be a rewrite wearing a migration's name. It is
   all-or-nothing too: one unknown id and the register is left untouched, because a
   half-applied classification reads exactly like a complete one. The three single-field
   verbs (`audience`, `process`, `surface`) are CHANGE-only: they serve a row that already
   carries the group, and a row that predates it is refused with the door NAMED (#279).

**Fixture-driven by construction, and that is load-bearing.** Every probe redirects
`INSIGHTS_PATH` and `LOCK_PATH` into a temporary directory, because the live register is
production data: a probe that appended to `evidence/insights.jsonl` to test the append
would be writing the artifact it measures.

Run:  python3 -m pytest tests/test_insights_audience.py -q
Exit: 0 the audience is required, constrained and verified; non-zero otherwise.
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
        audience="public",
        process="no",
    )
    kwargs.update(over)
    return insights.append_insight(**kwargs)

def test_append_records_each_allowed_audience(tmp_path, monkeypatch):
    register = _redirect(tmp_path, monkeypatch)
    for value in insights.ALLOWED_AUDIENCE:
        entry = _append(slug=f"probe-{value}", audience=value)
        assert entry["audience"] == value
    stored = [json.loads(l) for l in register.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert [r["audience"] for r in stored] == insights.ALLOWED_AUDIENCE, (
        "the audience must reach the PERSISTED row, not only the returned dict")

def test_append_refuses_a_missing_audience(tmp_path, monkeypatch):
    register = _redirect(tmp_path, monkeypatch)
    for missing in ("", "   "):
        try:
            _append(audience=missing)
        except ValueError as exc:
            assert "audience" in str(exc)
        else:
            raise AssertionError(f"a missing audience {missing!r} was accepted")
    assert not register.exists(), "a refused append must write nothing"

def test_append_refuses_an_unknown_audience(tmp_path, monkeypatch):
    register = _redirect(tmp_path, monkeypatch)
    for unknown in ("Public", "marketable", "general", "publics", "internal-only"):
        try:
            _append(audience=unknown)
        except ValueError as exc:
            assert "audience" in str(exc)
        else:
            raise AssertionError(f"an unknown audience {unknown!r} was accepted")
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

    # The SAME row with an EMPTY audience is a defect: it was written and it says nothing.
    blank = _row(2, **{"audience": ""})
    register.write_text(json.dumps(legacy) + "\n" + json.dumps(blank) + "\n", encoding="utf-8")
    ok, errors = insights.verify_insights()
    assert not ok, "a stored blank audience must be rejected"
    assert any("audience" in e for e in errors), errors

    # An UNKNOWN value is the same defect wearing a value.
    unknown = _row(2, **{"audience": "marketable"})
    register.write_text(json.dumps(legacy) + "\n" + json.dumps(unknown) + "\n", encoding="utf-8")
    ok, errors = insights.verify_insights()
    assert not ok, "an unknown stored audience must be rejected"
    assert any("audience" in e for e in errors), errors

def test_the_two_audiences_are_the_whole_vocabulary():
    """A PROPERTY split, deliberately coarse — a finer value would be a second axis."""
    assert insights.ALLOWED_AUDIENCE == ["public", "internal"]

def test_the_retired_class_vocabulary_is_kept_but_not_live():
    """`class` is RETIRED, never deleted: the record of what the legacy rows were marked
    under stays readable, and no value is validated against it any more."""
    assert insights.RETIRED_CLASSES == ["general", "implementation"]
    assert not hasattr(insights, "ALLOWED_CLASSES"), (
        "the retired axis must not keep a LIVE vocabulary — a live one would be a second "
        "place for a value to be refused")

def test_verify_no_longer_validates_a_stored_class_value(tmp_path, monkeypatch):
    """A legacy `class` value outside the old vocabulary is history, not a defect:
    refusing it would make the retirement a rewrite."""
    register = _redirect(tmp_path, monkeypatch)
    register.write_text(json.dumps(_row(1, **{"class": "something-else"})) + "\n",
                        encoding="utf-8")
    ok, errors = insights.verify_insights()
    assert ok, f"a retired label's value must not be validated any more, got {errors}"

# --- set_routing: the named backfill for the group, and the ways it must refuse ---------

def _legacy_register(register, rows):
    """Write rows as the register held them BEFORE the field existed — no group key."""
    register.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                        encoding="utf-8")
    return register.read_text(encoding="utf-8")

def test_set_routing_backfills_the_group_and_leaves_every_claim_byte_identical(tmp_path, monkeypatch):
    """The backfill adds TWO keys in ONE transaction. A restated claim would be a rewrite."""
    register = _redirect(tmp_path, monkeypatch)
    before = _legacy_register(register, [_row(1), _row(2)])

    changes = insights.set_routing({
        "row-1": {"audience": "public", "process": "no"},
        "row-2": {"audience": "internal", "process": "yes"},
    })

    assert [c[0] for c in changes] == ["row-1", "row-2"]
    assert [c[1]["audience"] for c in changes] == [None, None], (
        "a legacy row's old audience is ABSENT, never the empty string — the two are "
        "different things")
    stored = [json.loads(l) for l in register.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert [r["audience"] for r in stored] == ["public", "internal"]
    assert [r["process"] for r in stored] == ["no", "yes"]

    # Strip the added keys and the file must be EXACTLY what it was. The invariant is
    # asserted rather than inspected, because reading it back would not fail on a drift.
    stripped = "".join(
        json.dumps({k: v for k, v in r.items() if k not in ("audience", "process")},
                   ensure_ascii=False) + "\n"
        for r in stored)
    assert stripped == before, "set_routing must not touch a claim field"
    assert insights.verify_insights()[0], "a backfilled register must verify clean"

def test_set_routing_refuses_an_unknown_id_and_writes_nothing(tmp_path, monkeypatch):
    register = _redirect(tmp_path, monkeypatch)
    _legacy_register(register, [_row(1), _row(2)])
    before = register.read_text(encoding="utf-8")

    try:
        insights.set_routing({"row-1": {"audience": "public", "process": "no"},
                              "row-nope": {"audience": "internal", "process": "yes"}})
    except ValueError as exc:
        assert "row-nope" in str(exc)
    else:
        raise AssertionError("an unknown id was accepted")

    assert register.read_text(encoding="utf-8") == before, (
        "a refused set_routing must leave the register byte-identical")

def test_set_routing_refuses_an_unknown_value_and_writes_nothing(tmp_path, monkeypatch):
    register = _redirect(tmp_path, monkeypatch)
    _legacy_register(register, [_row(1)])
    before = register.read_text(encoding="utf-8")

    for field, unknown in (("audience", "Public"), ("audience", "marketable"),
                           ("audience", ""), ("process", "maybe"), ("process", "")):
        group = {"audience": "public", "process": "no"}
        group[field] = unknown
        try:
            insights.set_routing({"row-1": group})
        except ValueError as exc:
            assert field in str(exc), str(exc)
        else:
            raise AssertionError(f"an unknown {field} {unknown!r} was accepted")
    assert register.read_text(encoding="utf-8") == before

def test_set_routing_refuses_a_PARTIAL_group(tmp_path, monkeypatch):
    """`audience` and `process` are both required at the append, so a one-field mapping is
    the PARTIAL group this verb exists to make impossible — not a smaller backfill."""
    register = _redirect(tmp_path, monkeypatch)
    _legacy_register(register, [_row(1)])
    before = register.read_text(encoding="utf-8")

    for partial in ({"audience": "public"}, {"process": "no"}):
        try:
            insights.set_routing({"row-1": partial})
        except ValueError as exc:
            assert "names no" in str(exc), str(exc)
        else:
            raise AssertionError(f"a partial group {partial!r} was accepted")
    assert register.read_text(encoding="utf-8") == before

def test_set_routing_refuses_a_field_it_cannot_set(tmp_path, monkeypatch):
    register = _redirect(tmp_path, monkeypatch)
    _legacy_register(register, [_row(1)])
    try:
        insights.set_routing({"row-1": {"audience": "public", "process": "no",
                                        "status": "published"}})
    except ValueError as exc:
        assert "status" in str(exc), str(exc)
    else:
        raise AssertionError("the backfill accepted a status")
    assert "audience" not in register.read_text(encoding="utf-8")

def test_set_routing_leaves_rows_absent_from_the_mapping_untouched(tmp_path, monkeypatch):
    """Backfilling 33 rows must not rewrite the rows it was not asked about."""
    register = _redirect(tmp_path, monkeypatch)
    _legacy_register(register, [_row(1), _row(2), _row(3)])

    insights.set_routing({"row-2": {"audience": "internal", "process": "yes"}})

    stored = [json.loads(l) for l in register.read_text(encoding="utf-8").splitlines() if l.strip()]
    for untouched in (stored[0], stored[2]):
        assert "audience" not in untouched and "process" not in untouched, (
            "an untouched row gained a key")
    assert (stored[1]["audience"], stored[1]["process"]) == ("internal", "yes")

def test_set_routing_inserts_the_keys_without_reordering_the_row(tmp_path, monkeypatch):
    """A backfill is ADDITIVE: the row keeps its own key order and gains its labels."""
    register = _redirect(tmp_path, monkeypatch)
    original = _row(1)
    _legacy_register(register, [original])

    insights.set_routing({"row-1": {"audience": "public", "process": "no"}})

    row = json.loads(register.read_text(encoding="utf-8").strip())
    keys = list(row.keys())
    assert [k for k in keys if k not in ("audience", "process")] == list(original.keys()), (
        "every pre-existing key keeps the position it already had")
    assert keys.index("audience") == keys.index("ts") + 1, (
        "audience lands at its CANONICAL position — after the identity keys, before the "
        "claim body — not appended to the tail")
    assert keys.index("process") == keys.index("audience") + 1, (
        "the group lands in its DECLARED order, not in mapping order")
    assert insights.verify_insights()[0], "a backfilled register must verify clean"

def test_set_routing_refuses_an_empty_mapping(tmp_path, monkeypatch):
    register = _redirect(tmp_path, monkeypatch)
    _legacy_register(register, [_row(1)])
    try:
        insights.set_routing({})
    except ValueError as exc:
        assert "no routing group" in str(exc)
    else:
        raise AssertionError("an empty mapping was accepted")
    assert "audience" not in register.read_text(encoding="utf-8")

# --- the single-field verbs are CHANGE-only, and their refusal NAMES the door (#279) ----

def test_the_single_field_verbs_refuse_a_row_that_predates_the_group_and_name_the_door(tmp_path, monkeypatch):
    """#279: each refusal was CORRECT and named a different missing sibling, so a lane
    following them burned turns on a cycle. The refusal must name the exit."""
    register = _redirect(tmp_path, monkeypatch)
    _legacy_register(register, [_row(1)])
    before = register.read_text(encoding="utf-8")

    for verb, mapping in ((insights.set_audience, {"row-1": "public"}),
                          (insights.set_process, {"row-1": "no"}),
                          (insights.set_surfaces, {"row-1": "x"})):
        try:
            verb(mapping)
        except ValueError as exc:
            message = str(exc)
            assert "predates the routing group" in message, message
            assert "routing" in message, f"the refusal names no door: {message}"
        else:
            raise AssertionError(f"{verb.__name__} served a row predating the group")
    assert register.read_text(encoding="utf-8") == before, (
        "a refused change must leave the register byte-identical")

def test_the_single_field_verbs_CHANGE_a_row_that_already_carries_the_group(tmp_path, monkeypatch):
    """The narrowed population: a row carrying the group takes a field CHANGE, and the
    other member of the group is untouched by it."""
    register = _redirect(tmp_path, monkeypatch)
    _legacy_register(register, [_row(1)])
    insights.set_routing({"row-1": {"audience": "public", "process": "no"}})

    assert insights.set_audience({"row-1": "internal"}) == [("row-1", "public", "internal")]
    assert insights.set_process({"row-1": "yes"}) == [("row-1", "no", "yes")]

    row = json.loads(register.read_text(encoding="utf-8").strip())
    assert (row["audience"], row["process"]) == ("internal", "yes")
    assert insights.verify_insights()[0], "a changed group must still verify clean"
