#!/usr/bin/env python3
"""Gate: hygiene's stale-directory leg REPORTS what the reaper's glob cannot see (G6).

The reaper globs `/tmp/<namespace>-*`, and that glob is the whole of its vision: a
directory this factory created at a path that does not match it is invisible to every leg
of `tools/hygiene.py`. `git worktree add` is the declared creation convention that produces
exactly that class -- the path is the caller's choice, so `/tmp/af-223` and `/tmp/af-225/wt`
are both trees this factory made and NEITHER matches the pattern. Measured 2026-10-02: 75
registered trees, 75 of them outside the namespace.

What this gate holds, and why each arm is needed:

  * the leg holds NO removal path -- asserted by reading the leg's own SOURCE, because a
    promise in a docstring is not a mechanism (#220). `git worktree prune` is a write, and
    the tree may hold a peer lane's uncommitted work;
  * `removes` is False in the leg's own coverage AND in the rendered line, so a reader of
    the REPORT is told what the code does;
  * the census is GIT'S OWN (`git worktree list --porcelain`), never a `/tmp` glob: a
    scratch prefix would miss the main tree and every tree named outside the namespace;
  * an unreadable census is NOT RUN with its reason, never a clean zero -- and an
    unanswerable reachability check degrades to a stated NOT RUN rather than a silent 0;
  * the population MOVES when a tree is planted: a count that cannot move is not a
    measurement;
  * `landed` and `age` are COUNTS and never a verdict -- this very worktree sat on a landed
    commit while the leg was written, so a landed tree that is young is shown to be reported
    as landed and NOT as aged;
  * a prunable tree is ENUMERATED BY NAME with git's own reason, because it is a declaration
    by the tool that owns the data rather than an inference by this one;
  * the namespace test is the REAPER'S OWN pattern, read from `scratch_patterns_for`, so the
    two legs cannot drift apart about what "inside" means;
  * the report prints the `git worktree list` count on every run, driven through the real
    `main()`.

Fixtures are in-memory record sets plus throwaway directories, never the live tree: the
census and the reachability check are both INJECTED, so this gate plants a population
without touching git.

Run:  python3 -m pytest tests/test_hygiene_stale_dirs.py -q
Exit: 0 clean, non-zero on any regression in the report leg.
"""

from __future__ import annotations

import importlib.util
import inspect
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# BOTH INVOCATION MODES MUST REACH THE GUARD (#199). The audit invokes this gate in PYTEST
# mode, and this module has no `main()` at all, so the guard is a module-level `pytestmark`:
# it COLLECTS the tests and SKIPS them (exit 0). A module-level `pytest.skip` would exit 5
# ("no tests were collected"), which the audit reads as a failure.
# STATED SKIP: evidence/ (BOOTSTRAP-created, steps 4b/4c)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ledger_boundary import module_skip  # noqa: E402

_SKIP_REASON = module_skip(REPO)
if _SKIP_REASON:
    import pytest as _pytest  # noqa: E402

    pytestmark = _pytest.mark.skipif(True, reason=_SKIP_REASON)
HYGIENE = REPO / "tools" / "hygiene.py"


def _load_hygiene():
    spec = importlib.util.spec_from_file_location("hygiene_stale_dirs_under_test", HYGIENE)
    assert spec and spec.loader, f"cannot load {HYGIENE}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hygiene = _load_hygiene()

LEG_FUNCTIONS = (
    "stale_dirs_leg",
    "render_stale_dirs",
    "worktree_records",
    "registered_worktrees",
    "_primary_reachable",
)

REMOVAL_VERBS = (
    "rmtree",
    "os.remove",
    "unlink",
    "shutil.move",
    "os.rmdir",
    "write_text",
    "open(",
    "replace(",
)

SHA = "a" * 40


def _leg_source() -> str:
    return "\n".join(inspect.getsource(getattr(hygiene, name)) for name in LEG_FUNCTIONS)


def _record(path, head=SHA, branch=None, prunable=None) -> dict:
    return {
        "path": str(path),
        "head": head,
        "branch": branch,
        "detached": branch is None,
        "prunable": prunable,
    }


def _records_fn(records):
    return lambda root: (records, None)


def _reachable_fn(rev="origin/main", reachable=None, error=None):
    return lambda root: (rev, reachable, error)


def _leg(records, reachable=None, error=None, namespace=None, **kw):
    return hygiene.stale_dirs_leg(
        root=REPO,
        namespace=namespace or hygiene.NAMESPACE,
        records_fn=_records_fn(records),
        reachable_fn=_reachable_fn(reachable=reachable, error=error),
        **kw,
    )


# --------------------------------------------------------------------------------------
# The leg is REPORT-ONLY, and says so in code as well as in prose.
# --------------------------------------------------------------------------------------


def test_the_leg_holds_no_removal_path():
    source = _leg_source()
    offenders = [verb for verb in REMOVAL_VERBS if verb in source]
    assert not offenders, (
        f"the stale-directory leg carries a removal/write path {offenders} -- it must "
        "REPORT a surviving tree, never prune it (#220)"
    )


def test_the_leg_declares_removes_false():
    leg = _leg([_record("/tmp/af-999")])
    assert leg["removes"] is False, "the leg's own coverage must declare removes: False"
    assert "(removes: no)" in hygiene.render_stale_dirs(leg), (
        "the rendered line must tell a reader of the REPORT the same thing the code says"
    )


# --------------------------------------------------------------------------------------
# An instrument that failed is NOT a clean zero.
# --------------------------------------------------------------------------------------


def test_an_unreadable_census_is_NOT_RUN_and_never_a_clean_zero():
    leg = hygiene.stale_dirs_leg(
        root=REPO, records_fn=lambda root: ([], "`git worktree list` exited 128: boom")
    )
    assert leg["status"] == "NOT RUN", "an unreadable census is a failure, not a state"
    assert "boom" in leg["reason"]
    rendered = hygiene.render_stale_dirs(leg)
    assert "NOT RUN" in rendered and "0 tree(s)" not in rendered, (
        "a failed census must never render as a clean population of zero"
    )


def test_the_census_refuses_a_directory_that_is_not_a_repository():
    with tempfile.TemporaryDirectory() as tmp:
        records, error = hygiene.worktree_records(Path(tmp))
    assert records == [], "a non-repository cannot report trees"
    assert error, "a non-repository must return an ERROR, never an empty census"


def test_the_census_is_gits_own_and_reads_the_live_tree():
    records, error = hygiene.worktree_records(REPO)
    assert error is None, f"the live tree must be readable: {error}"
    assert records, "`git worktree list` must report at least the main tree"
    paths = [record["path"] for record in records]
    assert str(REPO) in paths, (
        f"the MAIN tree {REPO} must be in git's own census, not only the linked ones"
    )
    assert all(record.get("head") for record in records), "every tree carries a HEAD"


def test_the_namespace_test_is_the_reapers_OWN_pattern():
    leg = _leg([_record("/tmp/af-999")])
    patterns = hygiene.scratch_patterns_for(leg["namespace"])
    assert leg["pattern"] in patterns, (
        f"the leg tests `{leg['pattern']}`, which is not among the reaper's own globs "
        f"{patterns} -- the two legs would then disagree about what 'inside' means"
    )


# --------------------------------------------------------------------------------------
# The population is real: it discriminates, and it MOVES.
# --------------------------------------------------------------------------------------


def test_a_tree_INSIDE_the_namespace_is_not_reported_as_outside():
    namespace = hygiene.NAMESPACE
    inside = f"/tmp/{namespace}-1"
    outside = "/tmp/af-999"
    leg = _leg([_record(inside), _record(outside)], reachable=set())
    assert leg["outside"] == [outside], (
        f"only the tree outside the reaper's glob belongs in the report; got {leg['outside']}"
    )
    assert leg["total"] == 2, "the total is the whole census, inside and outside alike"


def test_a_planted_outside_tree_MOVES_the_reported_number():
    base = [_record("/tmp/af-999")]
    before = _leg(base, reachable=set())
    after = _leg(base + [_record("/tmp/af-1000")], reachable=set())
    assert len(before["outside"]) == 1 and len(after["outside"]) == 2, (
        "a count that does not move when a tree is planted is not a measurement"
    )
    assert "2 outside the namespace" in hygiene.render_stale_dirs(after), (
        "the moved population must reach the rendered line"
    )


def test_a_prunable_tree_is_ENUMERATED_by_name_with_gits_own_reason():
    reason = "gitdir file points to non-existent location"
    leg = _leg([_record("/tmp/foreign-wt-r2", prunable=reason)], reachable=set())
    assert leg["prunable"] == ["/tmp/foreign-wt-r2"], "git's own prunable flag must be read"
    rendered = hygiene.render_stale_dirs(leg)
    assert "/tmp/foreign-wt-r2" in rendered and reason in rendered, (
        "a prunable tree is ENUMERATED BY NAME with git's reason, not merely counted -- "
        "it is the one class git itself declares rather than this leg inferring"
    )


# --------------------------------------------------------------------------------------
# landed and age are COUNTS, never a verdict.
# --------------------------------------------------------------------------------------


def test_LANDED_is_a_count_and_never_a_verdict_on_its_own():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        landed_young = root / "landed-young"
        landed_young.mkdir()
        landed_old = root / "landed-old"
        landed_old.mkdir()
        os.utime(landed_old, (time.time() - 100 * 3600, time.time() - 100 * 3600))
        leg = _leg(
            [_record(landed_young), _record(landed_old)],
            reachable={SHA},
        )
    assert len(leg["landed"]) == 2, "both trees sit on a landed commit"
    assert [t["path"] for t in leg["trees"] if t["landed"] and not t["age_hours"] > 24] , (
        "a landed tree can be young"
    )
    assert [p for p in leg["aged"]] == [str(landed_old)], (
        "AGE is the discriminator for stranded, and it must select the old tree only -- "
        "'landed' means the work shipped, NOT that the tree is abandoned"
    )
    rendered = hygiene.render_stale_dirs(leg)
    assert "2 landed" in rendered and "1 older than 24h" in rendered, (
        "both facts must reach the reader BESIDE each other; the leg draws no conclusion"
    )


def test_an_unanswerable_reachability_check_is_NOT_RUN_and_never_a_clean_zero():
    leg = _leg(
        [_record("/tmp/af-999")],
        error="neither `origin/main` nor `main` resolves here",
    )
    assert leg["status"] == "ASSERTED", "the census still answered, so the leg still runs"
    assert leg["reach_error"], "the failed reachability check must be recorded"
    rendered = hygiene.render_stale_dirs(leg)
    assert "landed NOT RUN" in rendered, (
        "an unanswerable reachability check must render as NOT RUN, never as `0 landed`"
    )
    assert "0 landed" not in rendered


# --------------------------------------------------------------------------------------
# The acceptance criterion: the printed population includes the worktree-list count.
# --------------------------------------------------------------------------------------


def test_the_leg_reports_the_git_worktree_list_count():
    records, error = hygiene.worktree_records(REPO)
    assert error is None and records
    leg = hygiene.stale_dirs_leg(root=REPO)
    assert leg["status"] == "ASSERTED"
    assert leg["total"] == len(records) > 0, (
        f"the leg reports {leg['total']} trees against git's own {len(records)}"
    )
    assert f"{leg['total']} tree(s)" in hygiene.render_stale_dirs(leg), (
        "the `git worktree list` count must reach the printed line"
    )


def test_the_report_line_carries_its_population_and_the_removes_declaration():
    leg = _leg([_record("/tmp/af-999")], reachable=set())
    rendered = hygiene.render_stale_dirs(leg)
    head = rendered.splitlines()[0]
    for fragment in ("tree(s)", "outside the namespace", "landed", "older than", "removes: no"):
        assert fragment in head, f"the summary line must carry {fragment!r}: {head}"


def test_the_tool_PRINTS_the_stale_directory_population_on_every_run():
    result = subprocess.run(
        [sys.executable, str(HYGIENE)], cwd=str(REPO), capture_output=True, text=True
    )
    combined = result.stdout + result.stderr
    assert "hygiene stale directories:" in combined, (
        "the tool must PRINT the stale-directory population on every run, not only under a flag"
    )
    assert "removes: no" in combined
    # The exit code is deliberately NOT asserted: this factory's tree is shared, so a peer
    # lane's stranded path legitimately makes the audit non-zero, and that is not this
    # gate's subject.
