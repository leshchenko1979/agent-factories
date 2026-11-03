"""Gate: the runner's own preamble

Split from tests/test_patrol_host_state.py by #602: one gate per leg, each
carrying its own measured budget, so one slow leg can no longer withhold a
verdict from the whole fleet.
"""

# --- imports ---------------------------------------------------------------
from __future__ import annotations
import importlib.util
import io
import json
import os
import sqlite3
import shutil
import subprocess
import tempfile
import datetime as dt
from pathlib import Path
from unittest import mock
import pytest

from patrol_fixtures import (  # noqa: F401
    RUNNER,
    _EMPTY_GOAL_STORE,
    _NO_CRITERION_EXEMPTIONS,
    _NO_REF_ROLE_EXEMPTIONS,
    _issue,
    _rows,
    _run,
    _stub_publish_leg,
    _stub_shared_tree_rider,
    _swept,
    _SKIPS,
)


# --- this leg's tests -------------------------------------------------------
def test_repo_slug_reads_both_remote_forms() -> None:
    """The slug decides WHICH board is read; a wrong slug reads a wrong board clean."""
    assert RUNNER.repo_slug("git@github.com:leshchenko1979/agent-factories.git") == \
        "leshchenko1979/agent-factories"
    assert RUNNER.repo_slug("https://github.com/owner/repo.git") == "owner/repo"
    assert RUNNER.repo_slug("https://github.com/owner/repo") == "owner/repo"
    assert RUNNER.repo_slug("git@github.com:o/r\n") == "o/r", "trailing newline must not leak"

def test_repo_slug_refuses_a_remote_it_cannot_parse() -> None:
    """A non-github remote must FAIL, never degrade to a silently wrong slug."""
    for bad in ("", "https://gitlab.com/o/r.git", "not a url"):
        try:
            RUNNER.repo_slug(bad)
        except RUNNER.BoardReadError:
            continue
        raise AssertionError(f"repo_slug accepted {bad!r}")

def test_the_board_is_fetched_whole_never_filtered() -> None:
    """The reverse leg is sound only over the FULL board, so the argv must say so."""
    captured: dict = {}

    class _Proc:
        returncode = 0
        stdout = "[]"
        stderr = ""

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _Proc()

    with mock.patch.object(RUNNER.subprocess, "run", _fake_run):
        RUNNER.fetch_board("owner/repo")

    cmd = captured["cmd"]
    assert "--state" in cmd, cmd
    assert cmd[cmd.index("--state") + 1] == "all", (
        f"the board must be read in every state, not filtered: {cmd}"
    )
    assert "--limit" in cmd, cmd
    assert "--json" in cmd, cmd
    assert "state" in cmd[cmd.index("--json") + 1], cmd

def test_a_non_empty_board_with_a_missing_leg_is_reported() -> None:
    """#95's own acceptance: a non-zero forward count when the board is non-empty."""
    issues = [_issue(1, "OPEN"), _issue(2, "OPEN"), _issue(3, "CLOSED")]
    rows = _rows(("intake", "#1", 1), ("intake", "#3", 2))
    rc, out, _ = _run(issues, rows)
    assert rc == 1, f"a missing intake leg must fail the run, got rc={rc}\n{out}"
    assert "#2 is OPEN on the board with no intake row" in out, out
    assert "2 examined" in out, f"the forward coverage count must be printed\n{out}"
    assert "0 problem(s)" not in out.split("forward")[1].split("\n")[0], (
        "the forward leg examined a non-empty board and must not read zero problems"
    )

def test_a_clean_board_reads_clean_and_STATES_ITS_COVERAGE() -> None:
    """Non-vacuity: a green must be green over a NON-ZERO examined count."""
    issues = [_issue(1, "OPEN"), _issue(2, "OPEN"), _issue(3, "CLOSED")]
    # The `ruling` rows are not decoration: since #332 the patrol also asserts the ROUND's
    # own predicate (an OPEN item with an intake row and no ruling row is a miss), so a
    # fixture that models a clean board must be a board the round has SWEPT.
    rows = _swept(
        ("intake", "#1", 1), ("ruling", "#1", 5),
        ("intake", "#2", 2), ("ruling", "#2", 6),
        ("intake", "#3", 3), ("close", "#3", 4),
    )
    rc, out, _ = _run(issues, rows)
    assert rc == 0, f"a fully intaken board must pass, got rc={rc}\n{out}"
    assert "2 examined" in out, f"the clean verdict must name what it examined\n{out}"
    assert "asserted over the FULL board" in out, out
    assert "0 problem(s) over 2 open issue(s) examined" in out, out

def test_a_board_that_could_not_be_read_is_not_a_clean_board() -> None:
    """The failure mode that makes a patrol worse than useless: broken read, green verdict."""

    def _boom(slug):
        raise RUNNER.BoardReadError("gh issue list failed (rc=1): not authenticated")

    out, err = io.StringIO(), io.StringIO()
    rc = RUNNER.main(
        [],
        board_fn=_boom,
        slug_fn=lambda: "owner/repo",
        rows_fn=lambda: [],
        out=lambda *a, **k: print(*a, file=out, **k),
        err=lambda *a, **k: print(*a, file=err, **k),
        publish_fn=_stub_publish_leg,
        shared_tree_fn=_stub_shared_tree_rider,
        # #133: the driverless-lane leg's goal store and its turn-in-flight read are
        # injected here for the same reason every other live surface is -- and the
        # defaults WITHHOLD the driven claim (empty store, no turn open) rather than
        # granting one, so a probe that never asserts a driver cannot read one.
        driverless_goals_fn=lambda: _EMPTY_GOAL_STORE,
        driverless_turn_open_fn=lambda: {},
        # #330: the ref-role store is injected for the same reason the ruling table is.
        ref_role_exemptions_path=_NO_REF_ROLE_EXEMPTIONS,
        # #507: the criterion-path store, injected for the same reason.
        criterion_exemptions_fn=lambda: _NO_CRITERION_EXEMPTIONS,
    )
    assert rc == 2, f"an unreadable board must exit 2, got rc={rc}"
    assert "FAILED" in err.getvalue(), err.getvalue()
    assert "not authenticated" in err.getvalue(), err.getvalue()
    assert "verdict" not in out.getvalue(), (
        "an unreadable board must emit NO verdict at all — a verdict over zero issues "
        f"reads as a clean patrol\n{out.getvalue()}"
    )

def main() -> int:
    checks = [value for name, value in sorted(globals().items())
              if name.startswith("test_") and callable(value)]
    failures: list[str] = []
    for check in checks:
        try:
            check()
        except pytest.skip.Exception:
            continue
        except AssertionError as exc:
            failures.append(f"{check.__name__}: {exc}")
            print(f"  FAIL  {check.__name__} — {exc}")
        else:
            print(f"  PASS  {check.__name__}")
    print()
    if failures:
        print(f"patrol-runner gate FAILED: {len(failures)} check(s)")
        return 1
    ran = len(checks) - len(_SKIPS)
    skipped = f", {len(_SKIPS)} SKIPPED (nothing to judge)" if _SKIPS else ""
    print(f"patrol-runner gate passed: {ran} check(s){skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
