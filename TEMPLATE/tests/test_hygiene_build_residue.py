#!/usr/bin/env python3
"""Gate: hygiene's build-residue leg REPORTS its population and never removes anything.

pytest and ruff write a `.gitignore` containing `*` into the caches they create, so
`__pycache__/`, `.pytest_cache/`, `.ruff_cache/` and `.audit.lock` are SELF-IGNORING:
absent from `git status`, excluded from `registry/kit.json` as transient, and outside
`tools/hygiene.py`'s `/tmp`-only scratch glob. No leg of that tool could see them — the
failure mode this instrument exists to catch, a surface that reads clean because nothing
looked (G3 in the surface inventory).

The ruling (q15, 2026-09-30) is that the class is DECLARED OUT rather than reaped: a
worktree's cache is that worktree's and dies with the tree, and a reap races a test that
is running. What is owed instead is that the class be MEASURED, so "we chose not to reap
it" can never read as "there is none".

What this gate holds, and why each arm is needed:

  * the leg holds NO removal path — asserted by reading the leg's own SOURCE, because a
    promise in a docstring is not a mechanism (#220);
  * `removes` is False in the leg's coverage, so a reader of the REPORT is told the same
    thing the code says;
  * an UNREADABLE census is NOT RUN with its reason, never a clean zero: a leg that
    cannot see its population must not print one;
  * the depth bound is REAL — a cache deeper than it is genuinely outside the population,
    and the bound travels with the number rather than sitting in a comment;
  * NON-VACUITY: the same fixture with and without a planted cache, so the difference is
    attributable to the residue and not to the fixture;
  * the tool PRINTS the line on every run, driven through the real `main()` — the ruling's
    other half, since a leg that computes correctly and is never rendered is invisible.

Run:  python3 -m pytest tests/test_hygiene_build_residue.py -q
Exit: 0 clean, non-zero on any regression in the report leg.
"""

from __future__ import annotations

import importlib.util
import inspect
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HYGIENE = REPO / "tools" / "hygiene.py"


def _load_hygiene():
    spec = importlib.util.spec_from_file_location("hygiene_build_residue_under_test", HYGIENE)
    assert spec and spec.loader, f"cannot load {HYGIENE}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hygiene = _load_hygiene()


def test_the_leg_holds_no_removal_path() -> None:
    """The refusal, asserted STRUCTURALLY rather than promised in prose (#220).

    `tools/hygiene.py` DOES carry a reaper — that is the tool's job for scratch files — so
    the module cannot be scanned as a whole. The three functions that make up this leg are
    scanned instead, which is the narrower and the honest claim: whatever the reaper does
    elsewhere, THIS leg cannot remove anything.
    """
    for fn in (hygiene.build_residue_leg, hygiene.render_build_residue,
               hygiene._find_residue, hygiene.registered_worktrees):
        source = inspect.getsource(fn)
        for verb in ("rmtree", "os.remove", "unlink", "shutil.move", "os.rmdir"):
            assert verb not in source, f"{fn.__name__} carries a removal path: {verb}"


def test_the_leg_declares_removes_false() -> None:
    """A reader of the REPORT is told what the code does, in the report's own vocabulary."""
    leg = hygiene.build_residue_leg(
        worktrees_fn=lambda: (["/nonexistent-probe"], None), find_fn=lambda roots: []
    )
    assert leg["removes"] is False, leg
    assert leg["status"] == "ASSERTED", leg


def test_an_unreadable_census_is_NOT_RUN_and_never_a_clean_zero() -> None:
    """An unreadable census is not an empty one, and an empty one is not a clean one."""
    leg = hygiene.build_residue_leg(
        worktrees_fn=lambda: ([], "`git worktree list` could not run: boom"),
        find_fn=lambda roots: [],
    )
    assert leg["status"] == "NOT RUN", leg
    assert "could not run" in leg["reason"], leg
    line = hygiene.render_build_residue(leg)
    assert "NOT RUN" in line and "could not run" in line, line
    assert "item(s)" not in line, line


def test_the_census_refuses_a_directory_that_is_not_a_repository() -> None:
    """`git worktree list` outside a repository is an ERROR, never zero trees.

    Driven against a throwaway directory rather than the live tree, so the arm is
    deterministic in a member factory as well as here.
    """
    with tempfile.TemporaryDirectory() as tmp:
        paths, error = hygiene.registered_worktrees(Path(tmp))
    assert paths == [], paths
    assert error, "an unreadable census returned no error — it would render as a clean zero"


def test_the_census_is_gits_own_and_reads_the_live_tree() -> None:
    """The population's PROVENANCE: git's census, never a `/tmp` glob.

    A scratch-prefix glob would miss the main tree and every tree named outside the
    namespace, and would sweep a directory belonging to nobody — the #174/#220 class. Only
    the two facts that hold in any git tree are asserted (an error-free, non-empty census);
    a tree's own path is not asserted, because `TEMPLATE/` resolves to the enclosing
    repository rather than to a registered worktree of its own.
    """
    paths, error = hygiene.registered_worktrees(REPO)
    assert error is None, error
    assert paths, "the census reported no tree, which a repository cannot do"


def test_a_planted_cache_MOVES_the_reported_number() -> None:
    """NON-VACUITY: one fixture, driven twice, so the difference is the residue itself.

    The real `find` runs here (only the census is injected), so this arm also proves the
    instrument can observe the class it is aimed at: without it, a leg that always printed
    a constant would satisfy every other assertion in this file.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        clean = hygiene.build_residue_leg(worktrees_fn=lambda: ([str(root)], None))
        (root / "pkg").mkdir()
        (root / "pkg" / "__pycache__").mkdir()
        (root / "pkg" / "__pycache__" / "m.cpython-314.pyc").write_bytes(b"x")
        (root / ".pytest_cache").mkdir()
        (root / ".audit.lock").write_text("", encoding="utf-8")
        dirty = hygiene.build_residue_leg(worktrees_fn=lambda: ([str(root)], None))
    assert clean["status"] == "ASSERTED" and dirty["status"] == "ASSERTED", (clean, dirty)
    assert clean["items"] == 0, clean
    assert dirty["items"] == 3, dirty
    assert dirty["counts"]["__pycache__"] == 1, dirty["counts"]
    assert dirty["counts"][".pytest_cache"] == 1, dirty["counts"]
    assert dirty["counts"][".audit.lock"] == 1, dirty["counts"]
    assert dirty["counts"][".ruff_cache"] == 0, dirty["counts"]


def test_the_depth_bound_is_REAL_not_a_claim() -> None:
    """The bound travels with the number, so a cache outside it is genuinely not counted.

    Measured over the live census when the leg landed: the population by depth was 1:42,
    2:132, 3:48, 4+:0 — so depth 3 carries the whole class. This arm pins the bound as a
    MECHANISM: a cache one level deeper is outside the population and is not reported, and
    the leg says which bound it judged on.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "a" / "b" / "c" / "__pycache__").mkdir(parents=True)
        leg = hygiene.build_residue_leg(worktrees_fn=lambda: ([str(root)], None))
    assert leg["maxdepth"] == hygiene.BUILD_RESIDUE_MAXDEPTH, leg
    assert hygiene.BUILD_RESIDUE_MAXDEPTH == 3, hygiene.BUILD_RESIDUE_MAXDEPTH
    assert leg["items"] == 0, f"a cache at depth 4 is outside the bound and was counted: {leg}"


def test_the_report_line_carries_its_population_and_the_removes_declaration() -> None:
    """The line a reader meets names the count, the class, and `removes: no`."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "__pycache__").mkdir()
        leg = hygiene.build_residue_leg(worktrees_fn=lambda: ([str(root)], None))
    line = hygiene.render_build_residue(leg)
    assert "removes: no" in line, line
    assert "1 item(s) over 1 worktree(s)" in line, line
    assert "__pycache__ 1" in line, line
    assert "declared out" in line, line


def test_the_tool_PRINTS_the_population_on_every_run() -> None:
    """The ruling's other half — 'print the population on every run'.

    Driven through the REAL `main()`, so a leg that computes correctly and is never
    rendered cannot pass. The exit code is deliberately NOT asserted: a peer lane holding
    a stranded file is a legitimate non-zero on this shared tree, and the arm under test is
    the printed population, not the audit's verdict.
    """
    proc = subprocess.run(
        [sys.executable, str(HYGIENE), "--audit"],
        cwd=str(REPO), capture_output=True, text=True,
    )
    out = proc.stdout + proc.stderr
    assert "hygiene build residue:" in out, out
    assert "removes: no" in out, out
    assert "worktree(s)" in out, out
