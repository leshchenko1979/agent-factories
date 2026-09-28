#!/usr/bin/env python3
"""Gate: the insights register's STATUS — where an entry stands in its workflow.

`class` says what KIND of claim an entry is (who it serves). `status` says what has been
DONE about it, which is a different axis and is read by a different question: not "who
wants this?" but "what is still owed, and for how long?". Six invariants, each one a way
the field can LIE rather than merely be absent:

1. **A new entry OPENS at `pending` and is stamped.** Class is a property of the claim,
   which the author knows; a destination is the owner's routing call, so the append
   asserts only the row's own state. The default exists so a fresh row is never a silent
   blank in a register whose whole job is to show what is owed.
2. **A blank status is refused at the append, and an UNKNOWN one too.** The second is the
   same defect wearing a value: it passes any "is it set?" check and reaches no consumer,
   while reading as a routing decision that was taken.
3. **`status_at` travels WITH the status.** A status with no instant cannot be aged out —
   "which items have been sitting in `hq` for a fortnight?" is the question the field
   exists to answer, and it is unanswerable without it.
4. **`verify` REJECTS a stored blank, an unknown value, or a status with no instant, and
   ACCEPTS a legacy row with no key at all.** The register is append-only, so rows
   predating the field keep their shape; a value that was WRITTEN is a different thing
   from a field that never existed, and the two must not collapse into one verdict.
5. **A transition rewrites the label and NOTHING else.** Every claim field is
   byte-identical afterwards — a status move that restated a claim would be a rewrite
   wearing a routing change's name. All-or-nothing too: one unknown id and the register
   is left untouched, because a half-applied move reads exactly like a complete one.
6. **The two axes are ORTHOGONAL.** Setting a status must not disturb the class, and
   re-routing a row must not disturb any other row.

**Fixture-driven by construction, and that is load-bearing.** Every probe redirects
`INSIGHTS_PATH` and `LOCK_PATH` into a temporary directory, because the live register is
production data: a probe that appended to `evidence/insights.jsonl` to test the append
would be writing the artifact it measures.

Run:  python3 -m pytest tests/test_insights_status.py -q
Exit: 0 the status is defaulted, constrained, stamped and verified; non-zero otherwise.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import insights  # noqa: E402

CLAIM_KEYS = ("n", "id", "ts", "author", "class", "topic", "stage",
              "naive_assumption", "empirical_reality", "mechanism")


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


def _rows(register):
    return [json.loads(l) for l in register.read_text(encoding="utf-8").splitlines() if l.strip()]


def _row(n, **over):
    row = {"n": n, "id": f"row-{n}", "ts": "2026-09-14T08:25:08Z", "topic": "t",
           "stage": "stage-1", "naive_assumption": "a", "empirical_reality": "b",
           "mechanism": "c", "author": "Surveys", "class": "general"}
    row.update(over)
    return row


def _legacy_register(register, rows):
    """Write rows as the register held them BEFORE status existed — no key at all."""
    register.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                        encoding="utf-8")
    return register.read_text(encoding="utf-8")


def _without(row, *keys):
    return {k: v for k, v in row.items() if k not in keys}


# --- the append ----------------------------------------------------------------------

def test_append_opens_at_pending_and_stamps_it(tmp_path, monkeypatch):
    """A fresh row is never a silent blank: it opens unrouted, and says when."""
    register = _redirect(tmp_path, monkeypatch)
    entry = _append(slug="probe-opening")
    assert entry["status"] == "pending"
    assert entry["status_at"], "a status with no instant cannot be aged out"

    stored = _rows(register)
    assert stored[0]["status"] == "pending", "the status must reach the PERSISTED row"
    assert stored[0]["status_at"] == entry["status_at"]


def test_append_accepts_each_allowed_status(tmp_path, monkeypatch):
    register = _redirect(tmp_path, monkeypatch)
    for value in insights.ALLOWED_STATUSES:
        entry = _append(slug=f"probe-{value}", status=value)
        assert entry["status"] == value
    assert [r["status"] for r in _rows(register)] == insights.ALLOWED_STATUSES


def test_append_refuses_a_blank_status(tmp_path, monkeypatch):
    register = _redirect(tmp_path, monkeypatch)
    for missing in ("", "   "):
        try:
            _append(status=missing)
        except ValueError as exc:
            assert "status" in str(exc)
        else:
            raise AssertionError(f"a blank status {missing!r} was accepted")
    assert not register.exists(), "a refused append must write nothing"


def test_append_refuses_an_unknown_status(tmp_path, monkeypatch):
    register = _redirect(tmp_path, monkeypatch)
    for unknown in ("Pending", "pub", "queued", "publish"):
        try:
            _append(status=unknown)
        except ValueError as exc:
            assert "status" in str(exc)
        else:
            raise AssertionError(f"an unknown status {unknown!r} was accepted")
    assert not register.exists(), "a refused append must write nothing"


def test_the_status_vocabulary_is_the_whole_set():
    """Two destinations and the terminals they reach — no second taxonomy hiding here."""
    assert insights.ALLOWED_STATUSES == [
        "pending", "publishing", "hq", "published", "landed", "dropped"]


# --- verify --------------------------------------------------------------------------

def test_verify_rejects_blank_unknown_and_unstamped_and_accepts_a_legacy_row(tmp_path, monkeypatch):
    register = _redirect(tmp_path, monkeypatch)

    # A row predating the field carries NO key: history is not rewritten, so this is clean.
    legacy = _row(1)
    register.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
    ok, errors = insights.verify_insights()
    assert ok, f"a legacy row must stay valid, got {errors}"

    # The SAME row with an EMPTY status is a defect: it was written and it says nothing.
    blank = _row(2, **{"status": "", "status_at": "2026-09-14T08:25:08Z"})
    register.write_text(json.dumps(legacy) + "\n" + json.dumps(blank) + "\n", encoding="utf-8")
    ok, errors = insights.verify_insights()
    assert not ok, "a stored blank status must be rejected"
    assert any("status" in e for e in errors), errors

    # An UNKNOWN value is the same defect wearing a value.
    unknown = _row(2, **{"status": "queued", "status_at": "2026-09-14T08:25:08Z"})
    register.write_text(json.dumps(legacy) + "\n" + json.dumps(unknown) + "\n", encoding="utf-8")
    ok, errors = insights.verify_insights()
    assert not ok, "an unknown stored status must be rejected"
    assert any("status" in e for e in errors), errors

    # And a KNOWN value with no instant is the shape unique to this field: unroutable.
    unstamped = _row(2, **{"status": "hq"})
    register.write_text(json.dumps(legacy) + "\n" + json.dumps(unstamped) + "\n", encoding="utf-8")
    ok, errors = insights.verify_insights()
    assert not ok, "a status with no status_at must be rejected"
    assert any("status_at" in e for e in errors), errors


# --- the transition ------------------------------------------------------------------

def test_status_moves_the_label_stamps_it_and_leaves_every_claim_identical(tmp_path, monkeypatch):
    """A transition rewrites the label. A restated claim would be a rewrite, not a move."""
    register = _redirect(tmp_path, monkeypatch)
    _legacy_register(register, [_row(1), _row(2)])
    before = _rows(register)

    changes = insights.set_statuses({"row-1": "publishing", "row-2": "hq"})

    assert [c[0] for c in changes] == ["row-1", "row-2"]
    assert [c[1] for c in changes] == [None, None], (
        "a legacy row's old status is ABSENT, never the empty string — they differ")
    after = _rows(register)
    assert [r["status"] for r in after] == ["publishing", "hq"]
    assert all(r["status_at"] for r in after), "every move is stamped"
    assert [_without(r, "status", "status_at") for r in after] == before, (
        "every CLAIM field must be byte-identical across a status move")
    assert insights.verify_insights()[0], "a moved register must verify clean"


def test_status_keeps_the_row_key_order_and_puts_the_pair_at_their_positions(tmp_path, monkeypatch):
    register = _redirect(tmp_path, monkeypatch)
    original = _row(1)
    _legacy_register(register, [original])

    insights.set_statuses({"row-1": "hq"})

    row = _rows(register)[0]
    added = [k for k in row if k not in original]
    assert added == ["status", "status_at"], f"exactly the two labels were added, got {added}"
    assert [k for k in row if k in CLAIM_KEYS] == [k for k in original if k in CLAIM_KEYS], (
        "every pre-existing key keeps the position it already had")
    assert row["status_at"] >= original["ts"], "a stamp cannot predate the row it labels"


def test_status_re_stamps_on_a_second_move_and_touches_nothing_else(tmp_path, monkeypatch):
    """Re-routing is a normal event: the label and its instant move, the claims do not."""
    register = _redirect(tmp_path, monkeypatch)
    _legacy_register(register, [_row(1)])
    insights.set_statuses({"row-1": "pending"})
    first = _rows(register)[0]

    insights.set_statuses({"row-1": "published"})
    second = _rows(register)[0]

    assert second["status"] == "published"
    assert second["status_at"] >= first["status_at"]
    assert _without(second, "status", "status_at") == _without(first, "status", "status_at")


def test_status_refuses_an_unknown_id_and_writes_nothing(tmp_path, monkeypatch):
    register = _redirect(tmp_path, monkeypatch)
    _legacy_register(register, [_row(1), _row(2)])
    before = register.read_text(encoding="utf-8")

    try:
        insights.set_statuses({"row-1": "hq", "row-nope": "hq"})
    except ValueError as exc:
        assert "row-nope" in str(exc)
    else:
        raise AssertionError("an unknown id was accepted")

    assert register.read_text(encoding="utf-8") == before, (
        "a refused move must leave the register byte-identical")


def test_status_refuses_an_unknown_value_and_writes_nothing(tmp_path, monkeypatch):
    register = _redirect(tmp_path, monkeypatch)
    _legacy_register(register, [_row(1)])
    before = register.read_text(encoding="utf-8")

    for unknown in ("Pending", "queued", "", "publish"):
        try:
            insights.set_statuses({"row-1": unknown})
        except ValueError as exc:
            assert "status" in str(exc), str(exc)
        else:
            raise AssertionError(f"an unknown status {unknown!r} was accepted")
    assert register.read_text(encoding="utf-8") == before


def test_status_leaves_rows_absent_from_the_mapping_untouched(tmp_path, monkeypatch):
    """Routing 31 rows must not rewrite the rows it was not asked about."""
    register = _redirect(tmp_path, monkeypatch)
    _legacy_register(register, [_row(1), _row(2), _row(3)])

    insights.set_statuses({"row-2": "publishing"})

    stored = _rows(register)
    assert "status" not in stored[0] and "status" not in stored[2], "an untouched row gained a key"
    assert stored[1]["status"] == "publishing"


def test_status_refuses_an_empty_mapping(tmp_path, monkeypatch):
    register = _redirect(tmp_path, monkeypatch)
    _legacy_register(register, [_row(1)])
    try:
        insights.set_statuses({})
    except ValueError as exc:
        assert "no statuses" in str(exc)
    else:
        raise AssertionError("an empty mapping was accepted")
    assert "status" not in register.read_text(encoding="utf-8")


# --- the two axes are orthogonal -----------------------------------------------------

def test_a_status_move_does_not_disturb_the_class(tmp_path, monkeypatch):
    """`class` and `status` answer different questions; moving one must not move the other."""
    register = _redirect(tmp_path, monkeypatch)
    _legacy_register(register, [_row(1), _row(2)])

    insights.classify_insights({"row-1": "general", "row-2": "implementation"})
    insights.set_statuses({"row-1": "publishing", "row-2": "hq"})
    stored = _rows(register)

    assert [r["class"] for r in stored] == ["general", "implementation"]
    assert [r["status"] for r in stored] == ["publishing", "hq"]

    # And a class move on top of a routed row leaves the routing alone.
    routed = stored[0]["status_at"]
    insights.classify_insights({"row-1": "implementation"})
    stored = _rows(register)
    assert stored[0]["class"] == "implementation"
    assert stored[0]["status"] == "publishing", "a class move must not re-route the row"
    assert stored[0]["status_at"] == routed, "a class move must not re-stamp the status"
    assert insights.verify_insights()[0], "both axes together must still verify clean"


def test_class_and_status_share_one_backfill_and_neither_accepts_the_others_field(tmp_path, monkeypatch):
    """The shared mechanism is deliberately narrow: each verb writes only its own field."""
    register = _redirect(tmp_path, monkeypatch)
    _legacy_register(register, [_row(1)])
    try:
        insights.set_statuses({"row-1": "general"})
    except ValueError as exc:
        assert "status" in str(exc), str(exc)
    else:
        raise AssertionError("a CLASS value was accepted as a status")
    assert "status" not in register.read_text(encoding="utf-8")
