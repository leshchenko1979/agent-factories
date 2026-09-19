#!/usr/bin/env python3
"""Tests for tools/registry_render.py — dedupe, freshness, and render determinism.

These are the rules the renderer owns, and each is probed with a SYNTHETIC context
rather than the live box: `build_context` reads every profile database and every
cron row, so a test that used it would assert whatever the box happened to be
doing. The functions under test here are pure over the context they are handed,
which is exactly why they can be probed at all.

The one live-ish path is `run_check`, and the only case reached here is an UNKNOWN
predicate name — which short-circuits before any connect, so the test stays
hermetic while still proving a bad `check:` name cannot take a render down.
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))
sys.path.insert(0, str(REPO_ROOT))

import registry_render as rr  # noqa: E402


def _fragment(slug: str, announcements=None, lanes=None, **over) -> dict:
    # The fixtures are SYNTHETIC on purpose — `alpha`/`beta`, and paths under a neutral
    # `/factories/` root rather than this box's `/root/`. The renderer never resolves a
    # fragment's `factory` against the manifest, so a fixture is free to name a factory
    # that does not exist; borrowing the fleet's own layout would only make the test look
    # like it were asserting something about this box's factories.
    fragment = {
        "factory": slug,
        "display_name": slug.title(),
        "profile": "ops",
        "repo": f"/factories/{slug}",
        "skill": f"/factories/{slug}/SKILL.md",
        "purpose": f"{slug} purpose",
        "zone": {"owns": ["x"], "does_not_own": ["y"]},
        "services": [],
        "substrates_owned": ["s"],
        "announcements": announcements or [],
        "lanes": lanes or [],
        "status": "attested",
        "attested_at": "2026-09-19T10:00:00Z",
    }
    fragment.update(over)
    return fragment


def _ctx(fragments: list[dict], jobs: list[dict] | None = None, at="2026-09-19T12:00:00Z") -> dict:
    entries = []
    for fragment in fragments:
        entries.append(
            {
                "fragment": fragment,
                "slug": fragment["factory"],
                "lanes": fragment.get("_resolved_lanes", []),
                "skill_version": "1.0.0",
                "attested_at": fragment.get("attested_at"),
                "status": fragment.get("status"),
            }
        )
    announcements, problems = rr.collect_announcements(fragments)
    return {
        "resolved_at": at,
        "factories": entries,
        "announcements": announcements,
        "jobs": jobs or [],
        "problems": problems,
    }


def _lane(topic="HQ", thread=21, session="2646d31a-71ee-49f0-be81-9c8dc32d32fa"):
    return {
        "topic": topic,
        "thread_id": thread,
        "role": "hq",
        "session_id": session,
        "status": "resolved",
        "channel": "telegram",
        "bound_at": "2026-09-18T12:20:00Z",
        "session_title": "Telegram: Factories / HQ",
        "declared_announcements": [],
    }


def _job(name, owner=None, basis="name prefix", **over):
    job = {
        "id": f"id-{name}",
        "name": name,
        "cron_expr": "0 3 * * *",
        "timezone": "Europe/Moscow",
        "enabled": 1,
        "set_goal": 1,
        "goal_template": "reach the gate",
        "next_run_at": "2026-09-20T00:00:00Z",
        "last_run_at": None,
        "deliver_to": "session:2646d31a-71ee-49f0-be81-9c8dc32d32fa",
        "trigger_cmd": None,
        "_profile": "ops",
        "_owner": owner,
        "_basis": basis,
    }
    job.update(over)
    return job


# --- dedupe ---------------------------------------------------------------

def test_announcement_dedup_by_id_merges_origins_and_affects():
    """One fact noticed by two lanes is ONE entry carrying both declarers."""
    one = _fragment(
        "alpha",
        announcements=[
            {
                "id": "sqlite3-cli-installed",
                "severity": "info",
                "text": "sqlite3 CLI is on the box",
                "since": "2026-09-19",
                "affects": ["profile"],
            }
        ],
    )
    two = _fragment(
        "beta",
        announcements=[
            {
                "id": "sqlite3-cli-installed",
                "severity": "info",
                "text": "sqlite3 CLI is on the box",
                "since": "2026-09-19",
                "affects": ["beta"],
            }
        ],
    )
    merged, problems = rr.collect_announcements([one, two])
    assert len(merged) == 1, f"expected one entry, got {len(merged)}"
    entry = merged[0]
    assert entry["origins"] == ["alpha", "beta"], entry["origins"]
    assert set(entry["affects"]) == {"profile", "beta"}, entry["affects"]
    assert not entry["conflict"], entry["conflict"]
    assert not problems, problems


def test_announcement_dedup_keeps_two_distinct_ids_apart():
    """The negative half: dedupe must not collapse different notices."""
    one = _fragment("alpha", announcements=[{"id": "a", "text": "A", "severity": "info"}])
    two = _fragment("beta", announcements=[{"id": "b", "text": "B", "severity": "info"}])
    merged, _ = rr.collect_announcements([one, two])
    assert [m["id"] for m in merged] == ["a", "b"]


def test_announcement_conflicting_text_under_one_id_is_flagged():
    """Two texts under one id is a contradiction, and it renders as one."""
    one = _fragment("alpha", announcements=[{"id": "x", "text": "first", "severity": "info"}])
    two = _fragment("beta", announcements=[{"id": "x", "text": "second", "severity": "info"}])
    merged, problems = rr.collect_announcements([one, two])
    assert len(merged) == 1
    assert merged[0]["text"] == "first", "the first declaration is kept verbatim"
    assert merged[0]["conflict"], "the conflicting text must be recorded"
    assert problems, "a conflict is a render warning, not a silent pick"


def test_lane_scoped_announcements_merge_into_the_same_entry():
    """A lane notice and a root notice sharing an id are one statement."""
    lane = {"topic": "Triage", "thread_id": 20, "announcements": [{"id": "s", "text": "S"}]}
    one = _fragment("alpha", announcements=[{"id": "s", "text": "S", "severity": "warning"}], lanes=[lane])
    merged, _ = rr.collect_announcements([one])
    assert len(merged) == 1
    assert merged[0]["lanes"] == ["alpha/Triage"], merged[0]["lanes"]


def test_announcements_sort_critical_first_then_newest():
    frag = _fragment(
        "alpha",
        announcements=[
            {"id": "old-info", "severity": "info", "text": "i", "since": "2026-01-01"},
            {"id": "new-info", "severity": "info", "text": "i", "since": "2026-09-01"},
            {"id": "crit", "severity": "critical", "text": "c", "since": "2026-02-01"},
        ],
    )
    merged, _ = rr.collect_announcements([frag])
    assert [m["id"] for m in merged] == ["crit", "new-info", "old-info"]


# --- freshness ------------------------------------------------------------

def test_attest_stale_hours_is_derived_from_the_cadence_not_guessed():
    """The window is cadence x multiple — a number with its predicate attached."""
    assert rr.ATTEST_STALE_HOURS == rr.ATTEST_CADENCE_HOURS * rr.ATTEST_STALE_MULTIPLE
    assert rr.ATTEST_CADENCE_HOURS == 24, "the re-attest pacemaker runs daily"


def test_freshness_badge_marks_a_stale_attestation():
    now = datetime.datetime(2026, 9, 19, 12, 0, tzinfo=datetime.timezone.utc)
    stale = rr._freshness_badge("attested", "2026-09-10T12:00:00Z", now)
    assert "STALE" in stale, stale
    fresh = rr._freshness_badge("attested", "2026-09-19T09:00:00Z", now)
    assert "STALE" not in fresh and "attested" in fresh, fresh
    missing = rr._freshness_badge("unattested", None, now)
    assert "INCOMPLETE" in missing, missing
    broken = rr._freshness_badge("attested", "not-a-date", now)
    assert "INCOMPLETE" in broken, broken


def test_age_hours_returns_none_for_unreadable_input():
    now = datetime.datetime(2026, 9, 19, 12, 0, tzinfo=datetime.timezone.utc)
    assert rr.age_hours(None, now) is None
    assert rr.age_hours("", now) is None
    assert rr.age_hours("garbage", now) is None
    assert abs(rr.age_hours("2026-09-19T10:00:00Z", now) - 2.0) < 1e-6


# --- review_by ------------------------------------------------------------

def test_review_by_in_the_past_renders_review_due():
    past = {"id": "p", "text": "T", "severity": "warning", "review_by": "2020-01-01"}
    lines = "\n".join(rr._announcement_line(past, {}))
    assert "REVIEW DUE" in lines, lines


def test_review_by_in_the_future_does_not_render_review_due():
    future = {"id": "f", "text": "T", "severity": "warning", "review_by": "2099-01-01"}
    lines = "\n".join(rr._announcement_line(future, {}))
    assert "REVIEW DUE" not in lines, lines
    assert "review by: 2099-01-01" in lines, lines


def test_unknown_check_name_renders_not_checked_instead_of_crashing():
    entry = {"id": "c", "text": "T", "severity": "warning", "check": "no_such_predicate"}
    lines = "\n".join(rr._announcement_line(entry, {}))
    assert "NOT CHECKED" in lines, lines


def test_known_check_is_run_once_per_render():
    """Six announcements citing one predicate must not run it six times."""
    calls = []

    def predicate():
        calls.append(1)
        return True, "ok"

    rr.CHECKS["_test_once"] = predicate
    try:
        cache: dict = {}
        for _ in range(3):
            rr.run_check("_test_once", cache)
        assert len(calls) == 1, f"predicate ran {len(calls)} times"
        holds, evidence = rr.run_check("_test_once", cache)
        assert holds is True and evidence == "ok"
    finally:
        del rr.CHECKS["_test_once"]


# --- rendering ------------------------------------------------------------

def test_render_index_has_one_entry_per_fragment_and_consistent_counts():
    frags = [_fragment("alpha"), _fragment("beta", announcements=[{"id": "a", "text": "A", "severity": "info"}])]
    index = rr.render_index(_ctx(frags))
    assert index["schema"] == rr.INDEX_SCHEMA
    assert index["resolved_at"] == "2026-09-19T12:00:00Z"
    assert [f["factory"] for f in index["factories"]] == ["alpha", "beta"]
    assert index["counts"]["factories"] == 2
    assert index["counts"]["announcements"] == 1
    assert index["counts"]["lanes"] == 0
    json.dumps(index)  # must be serializable as written


def test_index_never_carries_the_cron_prompt_body():
    """The index is a machine surface; prompt prose is the largest field and is dropped."""
    job = _job("alpha-thing")
    job["prompt"] = "x" * 5000
    index = rr.render_index(_ctx([_fragment("alpha")], jobs=[job]))
    assert "prompt" not in index["jobs"][0]
    assert "x" * 100 not in json.dumps(index)


def test_pacemaker_table_renders_set_goal_beside_goal_template():
    """set_goal alone reads healthy on the row that bites; the pair carries meaning."""
    with_template = _job("a-with", owner="alpha", goal_template="reach the gate")
    without = _job("a-without", owner="alpha", goal_template=None)
    markdown = rr.render_markdown(_ctx([_fragment("alpha")], jobs=[with_template, without]))
    assert "| set_goal | goal_template |" in markdown, markdown[:400]
    assert "present" in markdown and "**absent**" in markdown
    for name in ("a-with", "a-without"):
        assert f"`{name}`" in markdown, f"{name} missing from the pacemaker table"


def test_unattributed_jobs_are_rendered_not_dropped():
    orphan = _job("tmp-probe", owner=None, basis="unattributed")
    markdown = rr.render_markdown(_ctx([_fragment("alpha")], jobs=[orphan]))
    assert "## Unattributed jobs" in markdown
    assert "`tmp-probe`" in markdown
    assert "a finding, not an omission" in markdown


def test_no_unattributed_jobs_states_the_absence_plainly():
    markdown = rr.render_markdown(_ctx([_fragment("alpha")], jobs=[_job("a-x", owner="alpha")]))
    assert "Every cron row on the box is attributed" in markdown


def test_markdown_lists_every_fragment_as_its_own_section():
    markdown = rr.render_markdown(_ctx([_fragment("alpha"), _fragment("beta")]))
    assert markdown.count("\n### ") == 2, markdown.count("\n### ")
    assert "alpha — Alpha" in markdown and "beta — Beta" in markdown


def test_render_is_deterministic_for_a_fixed_context():
    """The drift gate compares bytes, so a re-render must be byte-identical."""
    frag = _fragment("alpha", announcements=[{"id": "a", "text": "A", "severity": "info"}])
    frag["_resolved_lanes"] = [_lane()]
    ctx = _ctx([frag], jobs=[_job("a-x", owner="alpha")])
    first_md = rr.render_markdown(ctx)
    first_index = json.dumps(rr.render_index(ctx), sort_keys=False)
    second_md = rr.render_markdown(ctx)
    second_index = json.dumps(rr.render_index(ctx), sort_keys=False)
    assert first_md == second_md
    assert first_index == second_index


def test_resolved_at_appears_in_both_artifacts():
    """A claim about live state without the instant it was read is not re-checkable."""
    ctx = _ctx([_fragment("alpha")])
    assert "2026-09-19T12:00:00Z" in rr.render_markdown(ctx)
    assert rr.render_index(ctx)["resolved_at"] == "2026-09-19T12:00:00Z"


def test_title_text_decodes_telegram_html_escaping():
    assert rr.title_text("MAX &amp; domain") == "MAX & domain"
    assert rr.title_text(None) == "—"
    assert rr.title_text("   ") == "—"


def test_cell_folds_newlines_and_escapes_pipes():
    assert rr.cell("a | b") == "a \\| b"
    assert rr.cell("a\nb") == "a b"
    assert rr.cell(None) == "—"

# --- end-to-end: the markers must reach the DOCUMENT, not just the helper ---
#
# The three probes below walk the whole `render_markdown` / `render_index` path.
# A helper that returns the right string and a template that forgets to call it
# look identical from the helper's own test, and the criteria name the rendered
# artifact — so each marker is asserted where a reader would find it.

def test_backdated_fragment_renders_stale_marker_in_the_document():
    """A fragment attested longer ago than cadence x multiple reads as STALE."""
    old = _fragment("alpha", attested_at="2026-09-10T00:00:00Z")
    markdown = rr.render_markdown(_ctx([old]))
    assert "| freshness | ⚠️ STALE — last attested 2026-09-10T00:00:00Z |" in markdown, markdown[:800]

def test_freshly_attested_fragment_does_not_read_as_stale():
    """The negative half: the marker must distinguish, not decorate every row."""
    fresh = _fragment("alpha", attested_at="2026-09-19T09:00:00Z")
    markdown = rr.render_markdown(_ctx([fresh]))
    assert "⚠️ STALE" not in markdown, markdown[:800]
    assert "| freshness | ✅ attested 2026-09-19T09:00:00Z |" in markdown, markdown[:800]

def test_past_review_by_renders_review_due_marker_in_the_document():
    notice = {
        "id": "sqlite3-cli-installed",
        "severity": "warning",
        "text": "sqlite3 CLI is on the box",
        "since": "2026-09-19",
        "affects": ["profile"],
        "review_by": "2020-01-01",
    }
    markdown = rr.render_markdown(_ctx([_fragment("alpha", announcements=[notice])]))
    assert "⚠️ REVIEW DUE" in markdown, markdown[:800]

def test_a_shared_id_renders_once_in_the_block_and_once_in_the_index():
    """Two fragments announcing one id = ONE entry carrying both declarers."""
    notice = {"id": "shared", "severity": "info", "text": "T", "since": "2026-09-19"}
    one = _fragment("alpha", announcements=[dict(notice, affects=["profile"])])
    two = _fragment("beta", announcements=[dict(notice, affects=["beta"])])
    ctx = _ctx([one, two])
    block = rr.render_markdown(ctx).split("## Announcements", 1)[1].split("## Reachability", 1)[0]
    assert block.count("`shared`") == 1, block
    assert "declared by: alpha, beta" in block, block
    index = rr.render_index(ctx)
    assert len(index["announcements"]) == 1, index["announcements"]
    assert index["announcements"][0]["origins"] == ["alpha", "beta"]
    assert index["counts"]["announcements"] == 1
