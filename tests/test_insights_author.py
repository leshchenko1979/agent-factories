#!/usr/bin/env python3
"""Gate: the insights register's AUTHOR — recorded, derived, and never defaulted.

The field exists so the register can tell the owner's own insights from a lane's. Three
invariants, and each one is a way the field can LIE rather than merely be absent:

1. **A blank author is refused at the append.** `author` is required on every row written
   since the field landed, and an empty string is the failure mode that matters: it renders
   as provenance while carrying none, so a reader cannot tell it from an authored row.
2. **`verify` REJECTS a stored blank, and ACCEPTS a legacy row that has no key at all.** The
   register is append-only, so rows predating the field keep their shape and are never
   rewritten to invent an author; a blank that was WRITTEN is a different thing from a field
   that never existed, and the two must not be collapsed into one verdict.
3. **The derivation REFUSES rather than defaults.** This is the ledger's own defect class,
   one surface over: a default is how a row gets stamped with an author that no lane ever
   claimed, and a guessed author is worse than a missing one because it reads as a receipt.
   The fragment leg is checked to WIN over the title leg, so the ordering is asserted rather
   than assumed.

**Fixture-driven by construction, and that is load-bearing.** Every probe redirects
`INSIGHTS_PATH` and `LOCK_PATH` into a temporary directory and monkeypatches the registry's
own reader functions, because the live register is production data: a probe that appended to
`evidence/insights.jsonl` to test the append would be writing the artifact it measures. The
registry leg is driven through the module's functions rather than a live DB for the same
reason — the probe must not depend on which lanes happen to be bound at run time.

Run:  python3 -m pytest tests/test_insights_author.py -q
Exit: 0 the author is required, derived and verified; non-zero otherwise.
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


def test_append_records_the_author(tmp_path, monkeypatch):
    register = _redirect(tmp_path, monkeypatch)
    entry = _append()
    assert entry["author"] == "Surveys"
    stored = json.loads(register.read_text(encoding="utf-8").strip())
    assert stored["author"] == "Surveys", "the author must reach the PERSISTED row"


def test_append_refuses_a_blank_author(tmp_path, monkeypatch):
    register = _redirect(tmp_path, monkeypatch)
    for blank in ("", "   "):
        try:
            _append(author=blank)
        except ValueError as exc:
            assert "author" in str(exc)
        else:
            raise AssertionError(f"a blank author {blank!r} was accepted")
    assert not register.exists(), "a refused append must write nothing"


def test_verify_rejects_a_stored_blank_and_accepts_a_legacy_row(tmp_path, monkeypatch):
    register = _redirect(tmp_path, monkeypatch)

    # A row predating the field carries NO key: history is not rewritten, so this is clean.
    legacy = {"n": 1, "id": "legacy", "ts": "2026-09-14T08:25:08Z", "topic": "t",
              "stage": "stage-1", "naive_assumption": "a", "empirical_reality": "b",
              "mechanism": "c"}
    register.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
    ok, errors = insights.verify_insights()
    assert ok, f"a legacy row must stay valid, got {errors}"

    # The SAME row with an EMPTY author is a defect: it was written and it says nothing.
    blank = dict(legacy, n=2, id="blank", author="")
    register.write_text(json.dumps(legacy) + "\n" + json.dumps(blank) + "\n", encoding="utf-8")
    ok, errors = insights.verify_insights()
    assert not ok, "a stored blank author must be rejected"
    assert any("author" in e for e in errors), errors


def test_derivation_refuses_rather_than_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENCRABS_SESSION_ID", raising=False)
    lane, why = insights.resolve_author()
    assert lane is None, f"an unidentifiable session must yield NO author, got {lane!r}"
    assert why, "a refusal must name its reason"


def test_derivation_refuses_when_the_session_holds_no_binding(monkeypatch):
    monkeypatch.setenv("OPENCRABS_SESSION_ID", "11111111-2222-3333-4444-555555555555")
    import registry  # the module the resolver imports lazily

    monkeypatch.setattr(registry, "all_bindings",
                        lambda: ([{"session_id": "99999999-9999-9999-9999-999999999999",
                                   "session_title": "Telegram: Elsewhere / Other "
                                                    "[chat:-1:topic:1]"}], []))
    monkeypatch.setattr(registry, "live_fragment_paths", lambda _args: [])
    lane, why = insights.resolve_author()
    assert lane is None, f"a session with no binding must not be named, got {lane!r}"
    assert "binding" in why, why


def test_fragment_leg_wins_over_the_title_leg(monkeypatch):
    """The ordering is the contract: a DECLARED topic is canonical, a title is a fallback."""
    sid = "11111111-2222-3333-4444-555555555555"
    monkeypatch.setenv("OPENCRABS_SESSION_ID", sid)
    import registry

    monkeypatch.setattr(registry, "all_bindings", lambda: ([
        {"session_id": sid, "chat_id": "-1", "thread_id": 7,
         "session_title": "Telegram: Factories / Insights [chat:-1:topic:7]"},
    ], []))
    monkeypatch.setattr(registry, "live_fragment_paths", lambda _args: ["fragment.json"])
    monkeypatch.setattr(registry, "load_fragment",
                        lambda _p: ({"factory": "meta-factory",
                                     "lanes": [{"topic": "Factories / Ledger",
                                                "thread_id": 7, "role": "ledger"}]}, None))
    monkeypatch.setattr(registry, "FACTORY_CHATS", {"meta-factory": "-1"}, raising=False)
    monkeypatch.setattr(registry, "resolve_lane",
                        lambda lane, bindings, topic_names, chat_id=None: {
                            "session_id": sid, "role": lane.get("role")})
    lane, why = insights.resolve_author()
    assert lane == "Factories / Ledger", (
        f"the declared fragment topic must win over the title, got {lane!r} ({why})")


def test_title_leg_reads_the_channel_name():
    assert insights._lane_from_title(
        "Telegram: Factories / Insights [chat:-1004497192134:topic:6865]") == "Insights"
    assert insights._lane_from_title("Telegram: Factories / Ledger [chat:-1:topic:3981]") == "Ledger"
    assert insights._lane_from_title("") is None
    assert insights._lane_from_title(None) is None
    assert insights._lane_from_title("[chat:-1:topic:1]") is None


def test_owner_author_is_a_first_class_value(tmp_path, monkeypatch):
    """The owner is not a lane and no session resolves to him, so the literal must pass."""
    _redirect(tmp_path, monkeypatch)
    entry = _append(author=insights.OWNER_AUTHOR)
    assert entry["author"] == "Alexey"
    ok, errors = insights.verify_insights()
    assert ok, errors
