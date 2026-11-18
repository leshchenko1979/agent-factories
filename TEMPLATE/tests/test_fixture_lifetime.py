"""Gate: fixture LIFETIME (#640) — what importing `patrol_fixtures` creates, and for how long.

Before #640 the module built SEVEN fixtures with module-level `tempfile.mkdtemp()` calls, so
every import of it — and 19 gate files import it — leaked seven directories into `/tmp`,
permanently. Six of the seven declared a prefix; the seventh (`_DUTY_TREE`, the P35 duty
tree) used a BARE `mkdtemp()` with no prefix, which is why a prefix-keyed leak count read it
as clean while it smuggled a `docs/ledger-invariants.json` + `evidence/ledger.jsonl` pair
into every interpreter that ever imported the module.

The fix routes every creation through a `TemporaryDirectory` created only when a probe first
READS the name (PEP 562 `__getattr__`), with the reference held in `_LAZY_TEMPS` for the life
of the process. The lifetime contract is therefore TWO-sided, and this gate measures BOTH
halves separately, because a count taken after a child exits measures nothing: at interpreter
shutdown the held refs are collected and the finalizers remove the trees, so an after-death
count is 0 for a clean module and for a module that never created anything alike.

  ALIVE (measured by the child, printed on stdout): a bare import creates NOTHING; reading a
  lazy name creates exactly its own directory, once; the duty tree carries the P35 shape.
  DEAD (measured by this process, after the child exits): every directory the child created
  is GONE — and the mutant whose cleanup is a no-op still has all of its directories, which
  is what makes the dead-half assertion able to discriminate.

Children run under a private TMPDIR so the count is exact, and the child runner kills the
WHOLE process group on a hang — `subprocess.run(timeout=)` kills only the direct child
(#639's own rework entry), which is the same class this gate exists to police.
"""

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# --- child-timeout budget (#651) ---------------------------------------------------------
# A child timeout is only worth having if it can fire BEFORE this gate's declared wall. A
# hung child that reaches the wall is CENSORED — killed with no verdict at all — while one
# killed by its own timeout FAILS the arm it belongs to, which is a verdict. So the SUM of
# every timeout is what must sit below the wall, never each site on its own: a per-site
# "< wall" check is exactly what passed at 600.0 and 900.0 beside a 249.99 s wall.
#
# The sum is DERIVED from the call sites by `tests/child_budget.py`, never kept as a
# hand-written total, because the defect this bounds was two literals that no declaration
# mentioned. That module also expands WRAPPERS: `_alive_count` holds one `_child` call and
# runs five times, so a census of source sites understates the worst case by 4x — the same
# arithmetic error that produced the "~730 s" estimate this gate replaced (true pre-fix
# worst case: 2463 s over runs, against the 1980 s a site count gives).
#
# Sized from MEASURED cost, not from caution: the whole gate is 12.83 s over 10 child runs on
# a quiet box (2026-11-18, load 0.5), so a plain run costs ~1.3 s and gets >13x headroom.
CHILD_TIMEOUT = 18.0        # the default: 5 `_alive_count` runs + leakmut + reintro + duty
CONSUMER_TIMEOUT = 30.0     # one arm driving a single `_run`
BARE_MUT_TIMEOUT = 40.0     # one arm driving TWO `_run` calls back to back
HANG_PROBE_TIMEOUT = 3.0    # the deliberately-hung child that proves a timeout CAN fire

sys.path.insert(0, str(Path(__file__).resolve().parent))
import child_budget as _child_budget_mod  # noqa: E402  (path set above)

GATE_KEY = "tests/test_fixture_lifetime.py"

def _declared_wall(path: Path | None = None) -> float | None:
    """This gate's own `budget_sec`, read from the tree's manifest by gate key."""
    return _child_budget_mod.declared_wall(GATE_KEY, path)

def _child_budget(path: Path, wall: float | None):
    """(runs, total_sec, child_runs, problems) for `path` against `wall`."""
    return _child_budget_mod.child_budget(path, wall)

def _child(code: str, tmp: str, timeout: float = CHILD_TIMEOUT) -> tuple[int, str, str]:
    """Run `code` in a fresh interpreter under a private TMPDIR; kill the whole TREE on hang."""
    env = dict(os.environ, TMPDIR=tmp, PYTHONPATH=str(REPO / "tests"))
    proc = subprocess.Popen(
        [sys.executable, "-c", code], cwd=str(REPO), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        start_new_session=True,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
        return proc.returncode, out, err
    except subprocess.TimeoutExpired:
        # The bound must bound: a bare kill of proc.pid would orphan any grandchild the
        # child spawned, and the orphan would keep holding this private directory.
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        out, err = proc.communicate()
        return proc.returncode, out, err


def _alive_count(code: str, tmp: str) -> tuple[str, str]:
    """Run a child whose LAST line is the alive count; return (last_line, stderr_tail)."""
    rc, out, err = _child(code, tmp)
    assert rc == 0, (rc, err[-2000:])
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    assert lines, f"child printed no alive count: rc={rc} out={out!r} err={err[-800:]}"
    return lines[-1], err[-800:]


def test_an_import_creates_nothing_and_the_counter_can_see_a_leak() -> None:
    # CONTROL, alive AND dead: a child that mkdtemps holds one entry while it lives and
    # STILL holds it after death (a raw mkdtemp has no finalizer) -- if either half of this
    # count could not see a real leak, the live assertions below would be green on any
    # module whatsoever.
    with tempfile.TemporaryDirectory(prefix="lifetime-control-") as tmp:
        last, err = _alive_count(
            "import os, tempfile\n"
            "tempfile.mkdtemp(prefix='leak-')\n"
            "print(len(os.listdir(os.environ['TMPDIR'])))\n",
            tmp,
        )
        assert last == "1", (last, err)
        assert len(os.listdir(tmp)) == 1, os.listdir(tmp)
    # LIVE: the property #640 was filed for. A bare import of the fixture module -- the act
    # 19 gate files perform -- must create NOTHING, alive or dead.
    with tempfile.TemporaryDirectory(prefix="lifetime-import-") as tmp:
        last, err = _alive_count(
            "import os, patrol_fixtures\n"
            "print(len(os.listdir(os.environ['TMPDIR'])))\n",
            tmp,
        )
        assert last == "0", (last, err)
        assert os.listdir(tmp) == [], os.listdir(tmp)


def test_a_lazy_name_creates_exactly_its_directory_once() -> None:
    # ALIVE: two names read -> exactly two directories, both under the module's declared
    # prefixes, and a re-read of the first returns the same path.
    with tempfile.TemporaryDirectory(prefix="lifetime-lazy-") as tmp:
        last, err = _alive_count(
            "import os\n"
            "import patrol_fixtures as pf\n"
            "a = pf._EMPTY_LOG_DIR\n"
            "b = pf._EMPTY_SCORES_DIR\n"
            "assert pf._EMPTY_LOG_DIR == a, 'not create-once'\n"
            "names = os.listdir(os.environ['TMPDIR'])\n"
            "assert all(n.startswith('patrol-') for n in names), names\n"
            "print(len(names))\n",
            tmp,
        )
        assert last == "2", (last, err)
    # MUTANT: the create-once cache neutered. One name must then cost TWO directories --
    # if the alive count cannot tell one read from two creations, it tests nothing.
    # Touching `_LAZY_DIRS` directly is the point: if the internals move, this arm fails
    # loudly and asks to be re-pointed rather than passing vacuously.
    with tempfile.TemporaryDirectory(prefix="lifetime-mutant-") as tmp:
        last, err = _alive_count(
            "import os\n"
            "import patrol_fixtures as pf\n"
            "a = pf._EMPTY_LOG_DIR\n"
            "pf._LAZY_DIRS.pop('_EMPTY_LOG_DIR')\n"
            "b = pf._EMPTY_LOG_DIR\n"
            "assert a != b, 'cache-neutered reads must not alias'\n"
            "print(len(os.listdir(os.environ['TMPDIR'])))\n",
            tmp,
        )
        assert last == "2", (last, err)


def test_everything_the_module_creates_dies_with_the_process() -> None:
    # ALIVE: three reads -- a bare dir, a SEEDED repo stub, and the P35 tree -- hold exactly
    # three directories while the child lives.
    with tempfile.TemporaryDirectory(prefix="lifetime-exit-") as tmp:
        last, err = _alive_count(
            "import os\n"
            "import patrol_fixtures as pf\n"
            "for name in ('_EMPTY_LOG_DIR', '_IN_STEP_HOMES_REPO', '_DUTY_TREE'):\n"
            "    assert getattr(pf, name), name\n"
            "print(len(os.listdir(os.environ['TMPDIR'])))\n",
            tmp,
        )
        assert last == "3", (last, err)
        # DEAD: the same private directory, after the child has exited. Shutdown collected
        # the held refs, so every one of the three is gone.
        assert os.listdir(tmp) == [], os.listdir(tmp)
    # MUTANT: the ownership promise itself neutered. `TemporaryDirectory` is replaced,
    # BEFORE the module is imported, by a wrapper whose cleanup does NOTHING -- the exact
    # shape of the pre-#640 leak. The same three reads must then leave all three directories
    # behind after death, which is what makes the dead-half assertion above able to
    # discriminate owned from raw.
    with tempfile.TemporaryDirectory(prefix="lifetime-leakmut-") as tmp:
        rc, out, err = _child(
            "import os, tempfile\n"
            "class _LeakTemp:\n"
            "    def __init__(self, prefix=None):\n"
            "        self.name = tempfile.mkdtemp(prefix=prefix)\n"
            "    def cleanup(self):\n"
            "        pass  # the neuter: the finalizer that would remove the tree is a no-op\n"
            "tempfile.TemporaryDirectory = _LeakTemp\n"
            "import patrol_fixtures as pf\n"
            "for name in ('_EMPTY_LOG_DIR', '_IN_STEP_HOMES_REPO', '_DUTY_TREE'):\n"
            "    assert getattr(pf, name), name\n"
            "print(len(os.listdir(os.environ['TMPDIR'])))\n",
            tmp,
        )
        assert rc == 0, (rc, err[-2000:])
        assert out.strip().endswith("3"), out
        # DEAD, mutant: with cleanup neutered the three SURVIVE the child's exit.
        assert len(os.listdir(tmp)) >= 3, os.listdir(tmp)


def test_a_reintroduced_module_level_mkdtemp_is_caught() -> None:
    # The ruling's literal shape (n=5017, close criterion 4): a MODULE-LEVEL
    # tempfile.mkdtemp() is reintroduced into a copy of the real source, and the same
    # ALIVE/DEAD measurement that proves the fixed module clean must SEE the copy leak.
    # A copy, not the live module: the live module is fixed, and this arm's job is to
    # prove the measurement discriminates the pre-#640 shape, not to damage the tree
    # under test. The appended line is exactly what the seven original call sites were.
    src_literal = repr(str(REPO / "tests" / "patrol_fixtures.py"))
    repo_literal = repr(str(REPO))
    with tempfile.TemporaryDirectory(prefix="lifetime-reintro-") as tmp:
        rc, out, err = _child(
            "import os, sys\n"
            "from pathlib import Path\n"
            f"repo = Path({repo_literal})\n"
            # The copy must sit at the REAL module's tree depth: the module derives its
            # own REPO from __file__.parent.parent, so a flat copy in TMPDIR breaks every
            # REPO-relative import before the reintroduced line even runs. A pseudo-repo
            # with the sibling trees symlinked keeps the copy's imports honest.
            "pseudo = Path(os.environ['TMPDIR'])\n"
            "tests = pseudo / 'tests'\n"
            "tests.mkdir()\n"
            f"src = Path({src_literal}).read_text(encoding='utf-8')\n"
            "copy = tests / 'patrol_fixtures_reintro.py'\n"
            "copy.write_text(src + '\\n"
            "_REINTRODUCED_LEAK = tempfile.mkdtemp(prefix=\"lifetime-reintro-\")\\n', encoding='utf-8')\n"
            "for name in ('tools', 'TEMPLATE', 'docs', 'evidence'):\n"
            "    target = pseudo / name\n"
            "    if not target.exists():\n"
            "        target.symlink_to(repo / name)\n"
            "sys.path.insert(0, str(tests))\n"
            "import patrol_fixtures_reintro  # module-level mkdtemp: the pre-#640 shape, verbatim\n"
            "print(len([d for d in os.listdir(os.environ['TMPDIR']) if d.startswith('lifetime-reintro-')]))\n",
            tmp,
        )
        # ALIVE: the reintroduced line is the ONLY directory the import creates — the
        # fixed body around it still creates nothing until a name is read.
        assert rc == 0, (rc, err[-2000:])
        assert out.strip() == "1", (out, err[-500:])
        # DEAD: the reintroduced module-level directory OUTLIVES the process, and nothing
        # patrol-owned does (no lazy name was read here, so no owned tree was created).
        # That asymmetry is what the dead-half assertion polices, firing on the leak shape.
        leftover = [d for d in os.listdir(tmp) if d.startswith("lifetime-")]
        assert len(leftover) == 1 and leftover[0].startswith("lifetime-reintro-"), leftover
        assert not any(d.startswith("patrol-") for d in os.listdir(tmp)), os.listdir(tmp)


def test_a_consumer_call_reaches_the_internal_reads_and_completes() -> None:
    # n=5024 criterion 4b: the module's OWN functions read the lazy names as bare
    # globals, and PEP 562 __getattr__ never fires for a module-internal read -- the
    # exact class the #640 fix broke and 8ea84c5f shipped red. This arm drives a REAL
    # consumer: `_run([], [], log_dir=...)` reaches past the first lazy read at :375
    # (log_dir supplied) into the :418/:448/:476/:485/:538/:569 reads, and `_duty_leg`
    # covers the :874 read. The assertion is NOT rc==0 -- a leg may fail on empty
    # populations by design -- what must not happen is an interpreter-level NameError,
    # because that is the shape a bare internal read produces and no leg verdict can.
    repo_literal = repr(str(REPO))
    with tempfile.TemporaryDirectory(prefix="lifetime-consumer-") as tmp:
        rc, out, err = _child(
            "import os\n"
            "from pathlib import Path\n"
            f"repo = Path({repo_literal})\n"
            "import patrol_fixtures as pf\n"
            "run_rc, _, run_err = pf._run([], [], log_dir=os.environ['TMPDIR'])\n"
            "assert 'NameError' not in run_err, run_err[-2000:]\n"
            "assert run_rc in (0, 1), (run_rc, run_err[-500:])\n"
            "leg = pf._duty_leg([], [], store=repo / 'registry' / 'factories')\n"
            "assert isinstance(leg, dict), type(leg)\n"
            "print('consumers-clean')\n",
            tmp,
            # Sized from the SAME measured IO thrash the old 600.0 was aimed at, but
            # bounded by the #651 budget instead of by caution: this arm drives ONE `_run`,
            # which costs ~1.7 s quiet, and the whole six-arm gate is 12.83 s. The old
            # literal was 2.4x the gate's OWN 249.99 s wall, so the timeout could never
            # fire — the hang it was written to catch was censored at the wall instead.
            timeout=CONSUMER_TIMEOUT,
        )
        assert rc == 0, (rc, err[-2000:])
        assert out.strip().endswith("consumers-clean"), (out, err[-500:])


def test_a_restored_bare_internal_read_is_caught_by_the_consumer_call() -> None:
    # n=5024 criterion 4a: the consumer-call arm must BITE on the pre-#640 shape. A copy
    # of the real source carries ONE restored bare internal read (the :418 site, exactly
    # as committed at 8ea84c5f^), the SAME consumer call is driven against BOTH copies,
    # and the mutated one must die with NameError while the unmutated control completes
    # clean. That control is what makes arm 4b able to catch this class rather than pass
    # on any module: same call, same machinery, one mutation, opposite outcomes.
    src_literal = repr(str(REPO / "tests" / "patrol_fixtures.py"))
    repo_literal = repr(str(REPO))
    with tempfile.TemporaryDirectory(prefix="lifetime-baremut-") as tmp:
        rc, out, err = _child(
            "import os, sys\n"
            "from pathlib import Path\n"
            f"repo = Path({repo_literal})\n"
            "pseudo = Path(os.environ['TMPDIR'])\n"
            "tests = pseudo / 'tests'\n"
            "tests.mkdir()\n"
            f"src = Path({src_literal}).read_text(encoding='utf-8')\n"
            "old = '_lazy_dir(\"_NO_RULING_EXEMPTIONS\")'\n"
            "assert src.count(old) == 1, src.count(old)\n"
            "mutated = src.replace(old, '_NO_RULING_EXEMPTIONS', 1)\n"
            "(tests / 'patrol_fixtures_baremut.py').write_text(mutated, encoding='utf-8')\n"
            "(tests / 'patrol_fixtures_ctrl.py').write_text(src, encoding='utf-8')\n"
            "for name in ('tools', 'TEMPLATE', 'docs', 'evidence'):\n"
            "    target = pseudo / name\n"
            "    if not target.exists():\n"
            "        target.symlink_to(repo / name)\n"
            "sys.path.insert(0, str(tests))\n"
            "import patrol_fixtures_ctrl as ctrl\n"
            "rc_c, _, err_c = ctrl._run([], [], log_dir=os.environ['TMPDIR'])\n"
            "assert 'NameError' not in err_c, err_c[-800:]\n"
            # The bite must be accepted in BOTH carriers, and this is NOT a softening:
            # `_run` does not catch an interpreter-level NameError, so a restored bare
            # read surfaces as a RAISED exception, never as a returned error string --
            # measured 2026-11-14, first run of this arm: the mutant died at
            # `NameError: name '_NO_RULING_EXEMPTIONS' is not defined` propagating out of
            # `mut._run(...)`, and the `err_m` assertion never got to run. Whichever
            # carrier it arrives in the NAME is pinned, so a mutant that raised some
            # unrelated NameError still fails -- and the control half above proves the
            # same call is clean on the unmutated source.
            "import patrol_fixtures_baremut as mut\n"
            "try:\n"
            "    rc_m, _, err_m = mut._run([], [], log_dir=os.environ['TMPDIR'])\n"
            "except NameError as exc:\n"
            "    assert '_NO_RULING_EXEMPTIONS' in str(exc), exc\n"
            "else:\n"
            "    assert 'NameError' in err_m, (rc_m, err_m[-800:])\n"
            "    assert '_NO_RULING_EXEMPTIONS' in err_m, err_m[-800:]\n"
            "print('mutant-bites')\n",
            tmp,
            # Same measured-IO basis, doubled: this ONE child drives TWO full
            # `_run` calls (control then mutant) back to back, so it gets the largest
            # share of the budget — and the pre-#651 literal (900.0) was 3.6x the gate's
            # own wall, i.e. dead code that guaranteed censoring rather than a verdict.
            timeout=BARE_MUT_TIMEOUT,
        )
        assert rc == 0, (rc, err[-2000:])
        assert out.strip().endswith("mutant-bites"), (out, err[-500:])


def test_the_duty_tree_is_lazy_and_carries_the_p35_shape() -> None:
    # The seventh leak had no prefix, so it is pinned by NAME here, not by a count that
    # could be fooled by an unrelated prefixed entry: import first (nothing alive), then
    # read `_DUTY_TREE` (exactly ONE directory alive), and that directory carries the P35
    # shape -- docs/ledger-invariants.json + evidence/ledger.jsonl -- whose unowned presence
    # was the leak this gate exists to name. Dead half: the tree is gone after exit too.
    with tempfile.TemporaryDirectory(prefix="lifetime-duty-") as tmp:
        rc, out, err = _child(
            "import os\n"
            "import patrol_fixtures as pf\n"
            "before = os.listdir(os.environ['TMPDIR'])\n"
            "assert before == [], before\n"
            "tree = pf._DUTY_TREE\n"
            "assert pf._DUTY_TREE == tree, 'not create-once'\n"
            "shape = sorted(p.name for p in tree.iterdir())\n"
            "assert shape == ['docs', 'evidence'], shape\n"
            "assert (tree / 'docs' / 'ledger-invariants.json').is_file(), 'no declaration'\n"
            "assert (tree / 'evidence' / 'ledger.jsonl').is_file(), 'no ledger'\n"
            "print(len(os.listdir(os.environ['TMPDIR'])))\n",
            tmp,
        )
        assert rc == 0, (rc, err[-2000:])
        assert out.strip().endswith("1"), out
        assert os.listdir(tmp) == [], os.listdir(tmp)


def test_the_child_timeouts_sum_below_the_declared_wall() -> None:
    # #651 criterion 2: the bound is the SUM, never each site on its own. That distinction is
    # the whole defect — 600.0 and 900.0 each look unremarkable beside a 249.99 s wall, and
    # together they are 6x it, so neither timeout could ever fire and a hung child was
    # CENSORED at the wall with no verdict at all.
    #
    # The sum is re-derived from THIS file's call sites, wrappers expanded, so the number
    # printed is the worst case and not a restatement of the constants above.
    wall = _declared_wall()
    runs, total, count, problems = _child_budget(Path(__file__), wall)
    print(f"\nchild-timeout budget: {count} run(s), sum {total:.1f}s, wall "
          f"{'absent (SKIP)' if wall is None else f'{wall:.2f}s'}")
    for arm, line, tmo, mult in runs:
        print(f"  {arm}:{line} timeout={tmo:.1f}s x{mult}")
    assert not problems, problems
    # Non-vacuous: an empty run list would satisfy the bound trivially, which is the same
    # class of self-grading this gate's sibling arms have already been caught doing.
    assert count >= 10, f"only {count} child run(s) found — the derivation lost sites"


def test_a_widened_child_timeout_breaks_the_sum_bound() -> None:
    # #651 criterion 4, second half: the bound must go RED when a timeout is widened back
    # above the wall, not merely hold today. The needle is CONSTRUCTED from the constant, so
    # this arm cannot match its own source text and grade its own homework.
    wall = _declared_wall()
    if wall is None:
        # A member factory that has not declared this gate inherits the population default,
        # which is not a tree-specific number to bound against. Documented SKIP, never a
        # silent pass: the arm prints why it did nothing.
        print("\nSKIP the widened-timeout arm: no declared wall for this gate in the tree")
        return
    needle = f"CONSUMER_TIMEOUT = {CONSUMER_TIMEOUT:.1f}"
    with tempfile.TemporaryDirectory(prefix="lifetime-budgetmut-") as tmp:
        src = Path(__file__).read_text(encoding="utf-8")
        assert src.count(needle) == 1, f"needle occurs {src.count(needle)}x: {needle!r}"
        mutant = Path(tmp) / "mutant_budget.py"
        mutant.write_text(src.replace(needle, f"CONSUMER_TIMEOUT = {wall * 2:.2f}"),
                          encoding="utf-8")
        _, total, _, problems = _child_budget(mutant, wall)
    assert total > wall, f"the mutant summed to {total:.1f}s, still under the {wall:.1f}s wall"
    assert problems, (
        f"a {total:.1f}s sum against a {wall:.1f}s wall produced NO problem: the bound does "
        "not bite, so it would pass a timeout widened above the wall")


def test_a_hung_child_is_killed_by_its_own_timeout_inside_the_wall() -> None:
    # #651 criterion 4, first half: the timeouts must be able to FIRE. A child that hangs is
    # killed by its OWN timeout, not by the gate's wall, so the arm that owns it fails WITH a
    # verdict instead of being censored — and it dies long before the wall could take it.
    with tempfile.TemporaryDirectory(prefix="lifetime-hang-") as tmp:
        started = time.time()
        rc, out, err = _child("import time\ntime.sleep(120)\n", tmp,
                              timeout=HANG_PROBE_TIMEOUT)
        elapsed = time.time() - started
    assert rc != 0, (rc, out[-400:], err[-400:])
    assert elapsed < HANG_PROBE_TIMEOUT + 5.0, (
        f"the hung child took {elapsed:.1f}s: its {HANG_PROBE_TIMEOUT}s timeout did not fire")


if __name__ == "__main__":
    # PYTEST form: these are module-level arms, so a bare run would exit 0 having asserted
    # NOTHING — a gate whose only exits are barred.
    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
