#!/usr/bin/env python3
"""Gate: hygiene REPORTS a branch checked out in more than one worktree (#504).

The worktree census (`worktree_records`) has always parsed each tree's `branch` and no leg
read it, so two trees on one branch was invisible to every leg of `tools/hygiene.py` —
while it silently corrupts the tree the whole factory reads.

Measured 2026-10-17: `/tmp/af-487` sat on branch `main`, the same branch
`/root/agent-factories` holds. When af-487 committed on `main` the branch ref moved, so the
SHARED tree's HEAD re-pointed while its index still held the old blob, and the new ledger
row rendered as a STAGED DELETION in a tree that had lost nothing. The owning lane restored
the "deleted" row twice and could not find the cause.

What this gate holds, and why each arm is needed:

  * the leg FIRES on a census with two trees on the primary branch — a leg that has never
    fired is a shell, so the finding is asserted rather than assumed;
  * the discriminating pair is asserted: the SAME census minus one tree must read clean, so
    a predicate that flags every census cannot pass;
  * an all-detached census reads zero branches and zero findings, so "no branch" is not
    folded into "contention";
  * a multiply-held NON-primary branch is a FINDING, never a VIOLATION — the violation class
    is the primary branch, because that is the tree every lane reads;
  * an unreadable census is NOT RUN with its reason, never a clean zero;
  * the population is PRINTED beside the verdict, so an unread census cannot render as a
    clean one;
  * the leg holds NO removal, detach or prune verb — asserted by reading its own SOURCE,
    because a promise in a docstring is not a mechanism (#220), and detaching another lane's
    worktree is the interference rule 22/23 forbids.

Run:  python3 -m pytest tests/test_hygiene_branch_occupancy.py -q
Exit: 0 clean, non-zero on any regression in the report leg.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# BOTH INVOCATION MODES MUST REACH THE GUARD (#199). The audit invokes this gate in PYTEST
# mode, so the guard is a module-level `pytestmark`: it COLLECTS the tests and SKIPS them
# (exit 0). A module-level `pytest.skip` would exit 5 ("no tests were collected"), which the
# audit reads as a failure.
# STATED SKIP: evidence/ (BOOTSTRAP-created, steps 4b/4c)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ledger_boundary import module_skip  # noqa: E402

_SKIP_REASON = module_skip(REPO)
if _SKIP_REASON:
    import pytest as _pytest  # noqa: E402

    pytestmark = _pytest.mark.skipif(True, reason=_SKIP_REASON)

HYGIENE = REPO / "tools" / "hygiene.py"

def _load_hygiene():
    spec = importlib.util.spec_from_file_location("hygiene_branch_occupancy_under_test", HYGIENE)
    assert spec and spec.loader, f"cannot load {HYGIENE}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

hygiene = _load_hygiene()

LEG_FUNCTIONS = ("branch_occupancy_leg", "render_branch_occupancy", "_short_branch")

# A leg that can move a tree is not this leg: the class is report-only by ruling, and
# detaching a worktree under a running lane is exactly what rules 22/23 forbid.
#
# The scan names WRITES and PROCESS SPAWNS, not the word "detached": the leg must READ
# `record["detached"]` to skip a tree that occupies no branch, and a scan that forbids the
# word would forbid the very field the census exists to expose. What makes a move possible
# is running a command or writing a file, so those are what this gate bars.
FORBIDDEN_VERBS = (
    "subprocess",
    "rmtree",
    "os.remove",
    "unlink",
    "shutil.move",
    "os.rmdir",
    "write_text",
    "write_bytes",
    "open(",
)

def _leg_source() -> str:
    return "\n".join(inspect.getsource(getattr(hygiene, name)) for name in LEG_FUNCTIONS)

def _record(path: str, branch: str | None, detached: bool = False) -> dict:
    return {
        "path": path,
        "head": (path.encode().hex() * 40)[:40],
        "branch": branch,
        "detached": detached,
        "prunable": None,
    }

def _census(records: list[dict]):
    """A records_fn for the leg: (records, error), the shape `worktree_records` returns."""
    return lambda root=None: (records, None)

# --- the finding fires, and it discriminates -----------------------------------------

def test_two_trees_on_the_primary_branch_is_a_violation():
    records = [
        _record("/shared", "refs/heads/main"),
        _record("/tmp/af-487", "refs/heads/main"),
        _record("/tmp/af-494", "refs/heads/own"),
    ]
    leg = hygiene.branch_occupancy_leg(records_fn=_census(records))
    assert leg["status"] == "ASSERTED"
    assert leg["primary_branch"] == "refs/heads/main"
    assert leg["primary_contended"] is True
    assert len(leg["multiply_held"]) == 1
    entry = leg["multiply_held"][0]
    assert entry["branch"] == "refs/heads/main"
    assert entry["paths"] == ["/shared", "/tmp/af-487"], "every path on the branch is named"
    rendered = hygiene.render_branch_occupancy(leg)
    assert "VIOLATION main" in rendered, rendered
    assert "/shared" in rendered and "/tmp/af-487" in rendered, rendered

def test_the_same_census_minus_one_tree_reads_clean():
    """The discriminating pair: without the second tree the leg must NOT fire.

    A predicate that flags every census passes the test above and is worthless. Removing
    the competing tree is the only difference, so a clean read here proves the leg reads
    CONTENTION rather than the mere presence of branches.
    """
    records = [
        _record("/shared", "refs/heads/main"),
        _record("/tmp/af-494", "refs/heads/own"),
    ]
    leg = hygiene.branch_occupancy_leg(records_fn=_census(records))
    assert leg["multiply_held"] == []
    assert leg["primary_contended"] is False
    rendered = hygiene.render_branch_occupancy(leg)
    assert "0 branch(es) multiply held" in rendered, rendered
    assert "VIOLATION" not in rendered and "FINDING" not in rendered, rendered

def test_a_non_primary_branch_is_a_finding_not_a_violation():
    """Contention on a side branch is reported, but it is not the corruption class."""
    records = [
        _record("/shared", "refs/heads/main"),
        _record("/tmp/x", "refs/heads/side"),
        _record("/tmp/y", "refs/heads/side"),
    ]
    leg = hygiene.branch_occupancy_leg(records_fn=_census(records))
    assert len(leg["multiply_held"]) == 1
    assert leg["primary_contended"] is False, "only the primary branch is the violation class"
    rendered = hygiene.render_branch_occupancy(leg)
    assert "FINDING side" in rendered, rendered
    assert "VIOLATION" not in rendered, rendered

def test_an_all_detached_census_reads_zero_branches():
    records = [_record("/t%d" % i, None, detached=True) for i in range(3)]
    leg = hygiene.branch_occupancy_leg(records_fn=_census(records))
    assert leg["branches"] == 0, "a detached tree occupies no branch"
    assert leg["multiply_held"] == []
    assert leg["primary_contended"] is False
    assert leg["total"] == 3, "the population is still counted"

# --- the instrument cannot lie about its own coverage --------------------------------

def test_an_unreadable_census_is_not_run_never_a_clean_zero():
    leg = hygiene.branch_occupancy_leg(records_fn=lambda root=None: ([], "census exploded"))
    assert leg["status"] == "NOT RUN"
    assert "census exploded" in leg["reason"]
    rendered = hygiene.render_branch_occupancy(leg)
    assert "NOT RUN" in rendered, rendered
    assert "0 branch(es) multiply held" not in rendered, (
        "an unread census must never render as a clean one"
    )

def test_the_population_is_printed_beside_the_verdict():
    """A reader must be able to tell 'examined 70, none contended' from 'examined nothing'."""
    records = [_record("/shared", "refs/heads/main")]
    rendered = hygiene.render_branch_occupancy(
        hygiene.branch_occupancy_leg(records_fn=_census(records))
    )
    assert "1 tree(s) on 1 branch(es)" in rendered, rendered

def test_the_leg_declares_removes_false():
    leg = hygiene.branch_occupancy_leg(records_fn=_census([_record("/shared", "refs/heads/main")]))
    assert leg["removes"] is False, "report-only by ruling: the leg never reclaims"

def test_the_leg_holds_no_removal_detach_or_prune_verb():
    source = _leg_source()
    for verb in FORBIDDEN_VERBS:
        assert verb not in source, (
            f"the leg's own source carries `{verb}`; this leg PRINTS and a human acts, "
            "because detaching another lane's worktree is the interference rule 22/23 forbids"
        )
    # A git verb can only be reached through a process, and this leg spawns none: so no
    # `prune`, `checkout --detach` or any other mutating command can appear behind a name.
    assert "git" not in source.lower() or "worktree list" in source.lower(), (
        "the leg must not invoke git itself; it reads the ONE shared census"
    )

def test_the_live_census_reads_a_population():
    """The leg runs against THIS repository: a population of zero trees is a broken census."""
    leg = hygiene.branch_occupancy_leg()
    assert leg["status"] == "ASSERTED", leg.get("reason")
    assert leg["total"] >= 1, "git reports at least the main tree"
    assert leg["primary_branch"] == "refs/heads/main", leg["primary_branch"]
