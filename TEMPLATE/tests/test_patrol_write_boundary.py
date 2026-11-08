"""Gate: the WRITE-BOUNDARY leg — a session that writes this repo must be a lane of it (#561).

The defect this gate guards, measured 2026-10-26T01:15-01:22Z: a member factory's lane
(session `359fe71b`, InferHub Watch HQ, chat -1004379632866 thread 2) issued `edit_file`
against THIS repo's `tools/patrol_host_state.py` and its test pair, for this factory's board
item #550 — which this factory had already dispatched to its own Worker lane. The only gate
that fired was a SKILL-LOADING check, which is satisfied by loading the skill and is blind to
`bash` (that session ran 177 bash calls). The missing artifact was OWNERSHIP.

Every arm drives the leg's own injection points, so no verdict here can be decided by this
box's files: the events, the bindings and the lane declaration are all supplied by the probe.
The pair that matters is `test_a_foreign_session_writing_this_repo_is_REPORTED` against
`test_the_same_write_from_a_lane_is_CLEAN`: they differ in ONE binding row, so the verdict is
a function of ownership rather than of the fixture.
"""

# --- imports ---------------------------------------------------------------
from __future__ import annotations
import datetime as dt
import tempfile
from pathlib import Path

from patrol_fixtures import REPO, RUNNER  # noqa: F401

# --- this leg's own constants ----------------------------------------------
_READ_AT = "2026-11-06T22:00:00Z"
_NOW = dt.datetime(2026, 11, 6, 22, 0, tzinfo=dt.timezone.utc)
# SYNTHETIC ids, deliberately: every arm below drives the leg's injections, so no verdict
# here may depend on this box's real chat, threads or sessions. The incident the docstring
# measures is cited by its own short session id; the fixtures are not it.
_CHAT = -1001111111111
_PEER_CHAT = -1002222222222
_PEER_SESSION = "aaaa1111-2222-4333-8444-555566660561"
_LANE_SESSION = "bbbb1111-2222-4333-8444-555566660561"
_LANE_THREADS = (21, 1271, 68, 20, 19)
_TOOL = "tools/patrol_host_state.py"


def _path(name: str = _TOOL) -> str:
    return str(REPO / name)


def _event(session: str, name: str = _TOOL, *, kind: str = "tracked",
           instant: str = "2026-11-06T21:40:00Z") -> dict:
    return {"session": session, "kind": kind, "path": _path(name),
            "instant": instant, "log": "opencrabs.2026-11-06"}


def _binding(session: str, chat, thread, *, title: str = "") -> dict:
    return {"session_id": session, "chat_id": chat, "thread_id": thread,
            "session_title": title}


def _bindings(*, lane: bool = True, peer: bool = True) -> list[dict]:
    rows = []
    if lane:
        rows.append(_binding(_LANE_SESSION, _CHAT, 1271, title="Worker"))
    if peer:
        rows.append(_binding(_PEER_SESSION, _PEER_CHAT, 2, title="InferHub Watch HQ"))
    return rows


def _fragment(*, lanes=None) -> dict:
    declared = _LANE_THREADS if lanes is None else lanes
    return {"slug": "meta-factory", "lanes": [{"thread_id": t} for t in declared]}


def _leg(events, *, bindings=None, fragment=None, chat=_CHAT, window_hours=24.0):
    """The leg, with all three reads injected — no file, no log, no live manifest."""
    return RUNNER.write_boundary_leg(
        read_at=_READ_AT,
        slug="meta-factory",
        repo=REPO,
        window_hours=window_hours,
        now=_NOW,
        events_fn=lambda: (list(events), {"files": 1, "lines": 10, "bytes": 100,
                                          "outside_repo": 0, "undated": 0,
                                          "unreadable": []}),
        bindings_fn=lambda: (_bindings() if bindings is None else list(bindings), []),
        fragment_fn=lambda: (_fragment() if fragment is None else fragment),
        factory_chat=chat,
    )


# --- the verdict -----------------------------------------------------------
def test_a_foreign_session_writing_this_repo_is_REPORTED() -> None:
    """The incident's own shape: a peer factory's lane writing THIS repo's tools.

    The sentence must name WHO (its chat, its thread, its title), WHAT (the paths) and the
    DECLARATION it was judged against — an unattributed red is one a reader cannot act on.
    """
    leg = _leg([_event(_PEER_SESSION)])
    assert leg["status"] == "ASSERTED", leg
    assert len(leg["problems"]) == 1, leg["problems"]
    problem = leg["problems"][0]
    assert _PEER_SESSION in problem
    assert str(_PEER_CHAT) in problem and "thread 2" in problem
    assert "InferHub Watch HQ" in problem
    assert _TOOL in problem
    assert "not a lane of this factory" in problem
    assert leg["coverage"]["sessions_foreign"] == 1, leg["coverage"]
    assert leg["coverage"]["sessions_lane"] == 0, leg["coverage"]


def test_the_same_write_from_a_lane_is_CLEAN() -> None:
    """ONE binding row differs from the arm above, and the verdict must flip with it.

    Without this pair the gate would pass on a leg that reds everything, which is the same
    as a leg that means nothing.
    """
    leg = _leg([_event(_LANE_SESSION)])
    assert leg["status"] == "ASSERTED", leg
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["sessions_lane"] == 1, leg["coverage"]
    assert leg["coverage"]["events_under_repo"] == 1, leg["coverage"]


def test_a_lane_of_a_DIFFERENT_thread_of_the_SAME_chat_is_foreign() -> None:
    """The chat alone is not ownership: a topic this factory never declared is not a lane.

    Measured while writing this gate: the two factories share the fleet's profile root, so a
    chat-only match would call every lane on the box a lane of every factory.
    """
    rows = [_binding(_PEER_SESSION, _CHAT, 999, title="undeclared topic")]
    leg = _leg([_event(_PEER_SESSION)], bindings=rows)
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "not a lane of this factory" in leg["problems"][0]
    assert leg["coverage"]["sessions_foreign"] == 1, leg["coverage"]


def test_a_session_with_NO_binding_at_all_is_reported_as_UNKNOWN() -> None:
    """No binding row means no chat/thread to match, so ownership is UNKNOWN — not clean.

    This is the arm that stops "absent from the binding table" from reading as "therefore
    fine": a session that wrote here and left no trace of WHO it is, is the worst case, not
    the best.
    """
    leg = _leg([_event(_PEER_SESSION)], bindings=[])
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "NO session_bindings row" in leg["problems"][0]
    assert "UNKNOWN" in leg["problems"][0]
    assert leg["coverage"]["sessions_unbound"] == 1, leg["coverage"]


def test_one_problem_per_SESSION_not_per_event() -> None:
    """A lane that pokes the repo forty times is ONE boundary fact, and its paths travel."""
    events = [_event(_PEER_SESSION, _TOOL), _event(_PEER_SESSION, "tests/test_x.py",
                                                   kind="blocked"),
              _event(_PEER_SESSION, "tools/audit.py")]
    leg = _leg(events)
    assert len(leg["problems"]) == 1, leg["problems"]
    problem = leg["problems"][0]
    assert "2 write(s) that LANDED" in problem and "1 attempt(s)" in problem
    assert "tools/audit.py" in problem
    assert leg["coverage"]["events_tracked"] == 2, leg["coverage"]
    assert leg["coverage"]["events_blocked"] == 1, leg["coverage"]


def test_the_window_is_applied_by_the_READER_so_an_old_write_never_reaches_the_leg() -> None:
    """End to end through the real log reader: a write outside the window is not population.

    Driven through `profile_root` rather than the injected events, because the window is the
    READER's job — a probe that injected its own events would be asserting the fixture's
    filtering rather than the reader's.
    """
    home = Path(tempfile.mkdtemp())
    logs = home / "ops" / "logs"
    logs.mkdir(parents=True)
    (logs / "opencrabs.2026-11-06").write_text("\n".join([
        _log_line(f'Tracked new file: "{_path()}" in session {_PEER_SESSION}',
                  stamp="2026-11-01T00:00:00Z"),
        _log_line(f'Tracked new file: "{_path()}" in session {_PEER_SESSION}',
                  stamp="2026-11-06T21:40:00Z"),
    ]) + "\n", encoding="utf-8")
    leg = RUNNER.write_boundary_leg(
        read_at=_READ_AT, slug="meta-factory", repo=REPO, now=_NOW,
        bindings_fn=lambda: (_bindings(), []), fragment_fn=lambda: _fragment(),
        factory_chat=_CHAT, profile_root=home,
    )
    assert leg["status"] == "ASSERTED", leg
    assert leg["coverage"]["events_under_repo"] == 1, leg["coverage"]
    assert leg["coverage"]["log_files"] == 1, leg["coverage"]
    assert len(leg["problems"]) == 1, leg["problems"]


# --- NOT RUN, never clean (#242) -------------------------------------------
def test_an_empty_lane_declaration_is_NOT_RUN() -> None:
    """Zero declared lanes would make every session foreign, so it is a NOT RUN."""
    leg = _leg([_event(_PEER_SESSION)], fragment=_fragment(lanes=[]))
    assert leg["status"] == "NOT RUN", leg
    assert "declares NO lanes" in leg["coverage"]["reason"]


def test_an_unreadable_declaration_is_NOT_RUN() -> None:
    """The declaration is the independent fact; without it nothing can be judged."""
    leg = RUNNER.write_boundary_leg(
        read_at=_READ_AT, slug="meta-factory", repo=REPO, now=_NOW,
        events_fn=lambda: ([], {}),
        bindings_fn=lambda: (_bindings(), []),
        fragment_fn=lambda: (None),
        factory_chat=_CHAT,
    )
    assert leg["status"] == "NOT RUN", leg
    assert "could not be read" in leg["coverage"]["reason"]


def test_a_binding_read_that_raised_is_NOT_RUN() -> None:
    """An exception on the identity read is NOT a clean identity set."""
    def boom():
        raise RuntimeError("db locked")
    leg = RUNNER.write_boundary_leg(
        read_at=_READ_AT, slug="meta-factory", repo=REPO, now=_NOW,
        events_fn=lambda: ([], {}), bindings_fn=boom, fragment_fn=lambda: _fragment(),
        factory_chat=_CHAT,
    )
    assert leg["status"] == "NOT RUN", leg
    assert "db locked" in leg["coverage"]["reason"]


def test_no_factory_chat_declared_is_NOT_RUN() -> None:
    """No chat means no binding can be matched, so no session can be placed."""
    leg = RUNNER.write_boundary_leg(
        read_at=_READ_AT, slug="meta-factory", repo=REPO, now=_NOW,
        events_fn=lambda: ([], {}), bindings_fn=lambda: (_bindings(), []),
        fragment_fn=lambda: _fragment(), factory_chat=None, registry=_StubRegistry(),
    )
    assert leg["status"] == "NOT RUN", leg
    assert "declares no chat" in leg["coverage"]["reason"]


class _StubRegistry:
    """A registry declaring no chat — the NOT RUN arm's only dependency."""
    FACTORY_CHATS: dict = {}
    PROFILE_ROOT = None


def test_no_daemon_log_found_is_NOT_RUN() -> None:
    """A profile root with no logs directory is NOT a box where nobody wrote."""
    empty = Path(tempfile.mkdtemp())
    leg = RUNNER.write_boundary_leg(
        read_at=_READ_AT, slug="meta-factory", repo=REPO, now=_NOW,
        bindings_fn=lambda: (_bindings(), []), fragment_fn=lambda: _fragment(),
        factory_chat=_CHAT, profile_root=empty,
    )
    assert leg["status"] == "NOT RUN", leg
    assert "no daemon log was found" in leg["coverage"]["reason"]


# --- the log reader --------------------------------------------------------
def _log_line(text: str, session: str = _PEER_SESSION,
              stamp: str = "2026-11-06T21:40:00Z") -> str:
    """One daemon log line in the REAL shape: the session rides in `run_tool_loop{…}`.

    Measured off the live log while writing this gate — the tracked-file event repeats the
    session id inside its own text, but the skill-gate refusal does not, so the outer
    `run_tool_loop{session_id=…}` span is the only place BOTH shapes carry it.
    """
    return (f"{stamp}  INFO ThreadId(03) run_tool_loop{{session_id={session}}}: "
            f"opencrabs::brain::tools::registry: {text}")


def _log_file(lines: list[str]) -> Path:
    handle = Path(tempfile.mkdtemp()) / "opencrabs.2026-11-06"
    handle.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return handle


def test_the_reader_parses_both_event_shapes_and_drops_what_it_cannot_place() -> None:
    """The parser is the population's only source, so its exclusions are COUNTED.

    A line naming a path outside the repo, a line with no readable instant, and a line with
    no session are each excluded into their own bucket — never silently dropped, because an
    exclusion a reader cannot see is indistinguishable from a write that never happened.
    """
    log = _log_file([
        _log_line(f'Tracked new file: "{_path()}" in session {_PEER_SESSION}'),
        _log_line(f"skill_gate: blocked 'edit_file' — path '{_path('tools/audit.py')}'"),
        _log_line('Tracked new file: "/root/other-repo/x.py" in session '
                  f"{_PEER_SESSION}"),
        # An event with a session span but NO leading instant.
        f"no stamp here run_tool_loop{{session_id={_PEER_SESSION}}}: "
        f'Tracked new file: "{_path()}" in session {_PEER_SESSION}',
        # An event with an instant but NO session span.
        f'2026-11-06T21:44:00Z INFO Tracked new file: "{_path()}" in session '
        f"{_PEER_SESSION}",
        "2026-11-06T21:43:00Z INFO unrelated line mentioning agent-factories but no session",
    ])
    events, scanned = RUNNER.daemon_write_events(
        [log], repo=REPO, since=dt.datetime(2026, 11, 6, 0, 0, tzinfo=dt.timezone.utc))
    kinds = sorted(e["kind"] for e in events)
    assert kinds == ["blocked", "tracked"], events
    assert scanned["outside_repo"] == 1, scanned
    assert scanned["undated"] == 1, scanned
    assert scanned["no_session"] == 1, scanned
    assert scanned["lines"] == 6, scanned
    assert scanned["files"] == 1, scanned


def test_the_reader_honours_the_window() -> None:
    """`since` is applied at the reader, so a leg's window is not a post-filter."""
    log = _log_file([
        _log_line(f'Tracked new file: "{_path()}" in session {_PEER_SESSION}',
                  stamp="2026-11-01T00:00:00Z"),
        _log_line(f'Tracked new file: "{_path()}" in session {_PEER_SESSION}',
                  stamp="2026-11-06T21:40:00Z"),
    ])
    events, _ = RUNNER.daemon_write_events(
        [log], repo=REPO, since=dt.datetime(2026, 11, 6, 0, 0, tzinfo=dt.timezone.utc))
    assert len(events) == 1, events
    assert events[0]["instant"].startswith("2026-11-06"), events


# --- the render ------------------------------------------------------------
def test_the_report_prints_the_population_the_declaration_and_the_blind_spot() -> None:
    """`examined 0` must never render as `found 0`, so the counters print on every run."""
    leg = _leg([_event(_PEER_SESSION)])
    text = RUNNER.render([leg], [], slug="meta-factory", read_at=_READ_AT, issues=[])
    assert "LEG write-boundary — ASSERTED" in text
    assert "sessions writing under the repo in the last 24h: 1" in text
    assert "0 lane(s) of this factory, 1 foreign, 0 unbound" in text
    assert f"declared lane(s) of chat {_CHAT}" in text
    assert "BLIND SPOT:" in text
    assert "not a lane of this factory" in text


def test_a_NOT_RUN_leg_renders_its_reason_and_no_population() -> None:
    """A NOT RUN that printed counters would read as a sweep that examined nothing."""
    leg = _leg([], fragment=_fragment(lanes=[]))
    text = RUNNER.render([leg], [], slug="meta-factory", read_at=_READ_AT, issues=[])
    assert "LEG write-boundary — NOT RUN" in text
    assert "NOT RUN: " in text
    assert "declares NO lanes" in text
    assert "BLIND SPOT:" not in text


# --- mutation --------------------------------------------------------------
def test_the_fragment_slug_is_RESOLVED_by_DECLARATION_never_by_the_caller() -> None:
    """The WIRING defect this arm exists for, measured 2026-11-08 on the live box.

    `main()` carries ONE `slug`, and it is the BOARD slug — `remote_slug()` reads
    `owner/repo`. The fragment is named for the FACTORY slug (`meta-factory`), which is a
    different resolution: `declared_slug()` matches the git common dir against the fleet
    manifest. The wiring passed the board slug, so the leg looked for
    `registry/factories/leshchenko1979/agent-factories.json`, found nothing, and rendered
    `NOT RUN — no independent declaration` on a tree whose declaration was sitting right
    there at `registry/factories/meta-factory.json`. A leg that is NOT RUN verifies nothing,
    so the whole instrument was dark while every arm below stayed green — because every arm
    below passes `slug=` explicitly, and the wiring path was therefore never driven.

    So this arm drives the leg with NO slug and NO fragment_path, and asserts the path it
    builds is the DECLARED one. It is the only arm that reads the wiring rather than the
    verdict.
    """
    namespace = RUNNER.__dict__
    saved = namespace.get("declared_slug")
    namespace["declared_slug"] = lambda repo=None: "meta-factory"
    try:
        leg = RUNNER.write_boundary_leg(
            read_at=_READ_AT,
            repo=REPO,
            now=_NOW,
            events_fn=lambda: ([], {"files": 0, "lines": 0, "bytes": 0,
                                    "outside_repo": 0, "undated": 0, "unreadable": []}),
            bindings_fn=lambda: (_bindings(), []),
            fragment_fn=lambda: _fragment(),
            factory_chat=_CHAT,
        )
    finally:
        if saved is None:
            namespace.pop("declared_slug", None)
        else:
            namespace["declared_slug"] = saved
    fragment = leg["coverage"]["fragment"]
    assert fragment.endswith("registry/factories/meta-factory.json"), (
        f"the leg built {fragment!r} — the fragment is named for the FACTORY slug, so a "
        f"caller-supplied board slug ('owner/repo') must never reach it"
    )


def test_MUTANT_with_the_lane_check_neutered_the_peer_arm_reads_CLEAN() -> None:
    """Neuter the ownership comparison and the incident's own shape must stop being a finding.

    A gate that cannot fail is decoration: this proves the lane check — rather than the
    fixture happening to red for another reason — is what carries the peer arm's verdict.
    """
    source = (REPO / "tools" / "patrol_host_state.py").read_text(encoding="utf-8")
    needle = (
        "            if thread in thread_ids:\n"
        "                return True\n"
        "        return False\n"
    )
    assert needle in source, "the lane check moved; re-point this mutant"
    mutant_source = source.replace(needle, needle.replace("return False", "return True"))
    assert mutant_source != source, "the mutant did not apply"
    namespace = RUNNER.__dict__
    saved = {key: namespace[key] for key in ("write_boundary_leg", "is_lane") if key in namespace}
    try:
        exec(compile(mutant_source, "mutant", "exec"), namespace)  # noqa: S102
        leg = _leg([_event(_PEER_SESSION)])
        assert leg["coverage"]["sessions_foreign"] == 0, leg["coverage"]
        assert leg["problems"] == [], (
            "the mutant still reds, so the ownership comparison is not what carries the verdict"
        )
    finally:
        for key, value in saved.items():
            namespace[key] = value


if __name__ == "__main__":
    # PYTEST form: these are module-level arms, so a bare run would exit 0 having asserted
    # NOTHING — a gate whose only exits are barred.
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
