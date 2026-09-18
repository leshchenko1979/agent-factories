#!/usr/bin/env python3
"""Gate: the hygiene audit tells IN-FLIGHT from STRANDED (issue #38).

This factory's working tree is shared. Several lanes edit it at once, so "this
path is dirty" and "this path was abandoned" are different facts — and the first
version of `tools/hygiene.py` treated them as identical, so its audit went RED
whenever a peer lane was mid-task. Observed live 2026-09-18 ~14:04Z: the gate
failed on four files that were the Worker's in-flight #33 gate, and passed 30
seconds later when that lane committed. The signal was a race, not a health
state, and the daily measurement pacemaker read it as DEGRADED on a healthy
factory.

`tools/hygiene.py` fixes it by classifying on **age** — the only discriminator
git offers — and this gate holds that classification still:

  * a dirty path younger than the grace window is an **advisory** (printed, rc=0);
  * the same path older than the window is a **violation** (rc=1);
  * litter (`.bak` `.tmp` `.log` `.orig`) is a violation at any age;
  * `--require-committed <path>` is a violation with no grace at all.

**The window is the only lever, and this gate proves it.** #38's done-criteria
ask for both "a lane mid-task does not fail the audit" and "a genuinely stranded
modified tracked file still fails". Those two cannot both hold at one window: a
file touched one second ago is exactly what the 14:04Z in-flight files were, and
no mechanical evidence separates them. So `test_the_window_is_the_only_lever`
runs the SAME fresh edit at the default window (rc=0, #38's criterion 1) and at
`--grace-minutes 0` (rc=1, #38's criterion 2 in its strict form). A single-lane
factory gets the strict form by declaring the window in its own process law; this
factory, which has lanes, declares a non-zero one.

Every case runs in a throwaway repo with this tool shipped into it, so the live
working tree is never touched and the exit codes under test are the real ones.

Run:  python3 -m pytest tests/test_hygiene_inflight.py -q
Exit: 0 clean, non-zero on a classification regression.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HYGIENE = REPO / "tools" / "hygiene.py"

# Mirrors tools/hygiene.py:DEFAULT_GRACE_MINUTES. Asserted, not assumed: if the
# tool's default moves and this gate still passes, the gate is testing nothing.
DEFAULT_GRACE_MINUTES = 60


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _make_repo(tmp: Path) -> Path:
    """A factory-shaped throwaway repo, with this tool shipped into it.

    `evidence/ledger.jsonl` is tracked so the ledger-append case #38 reproduced
    is exercised, not just a plain file edit.
    """
    _git(tmp, "init", "-q")
    _git(tmp, "config", "user.email", "gate@example.invalid")
    _git(tmp, "config", "user.name", "gate")
    (tmp / "evidence").mkdir()
    (tmp / "tools").mkdir()
    (tmp / "tests").mkdir()
    (tmp / "README.md").write_text("baseline\n")
    (tmp / "evidence" / "ledger.jsonl").write_text('{"n": 1, "event": "run"}\n')
    (tmp / "tests" / "test_baseline.py").write_text("def test_ok():\n    assert True\n")
    (tmp / "tools" / "hygiene.py").write_bytes(HYGIENE.read_bytes())
    _git(
        tmp,
        "add",
        "README.md",
        "evidence/ledger.jsonl",
        "tests/test_baseline.py",
        "tools/hygiene.py",
    )
    _git(tmp, "commit", "-q", "-m", "baseline")
    return tmp


def _audit(repo: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(repo / "tools" / "hygiene.py"), "--audit", *extra],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _age_minutes(path: Path, minutes: int) -> None:
    """Backdate a path's mtime, so 'stranded' is a fact of the fixture."""
    stamp = time.time() - minutes * 60
    os.utime(path, (stamp, stamp))


def test_default_window_matches_this_gate() -> None:
    """The window under test is the tool's real default, read from the source."""
    spec_text = HYGIENE.read_text()
    assert f"DEFAULT_GRACE_MINUTES = {DEFAULT_GRACE_MINUTES}" in spec_text, (
        f"tools/hygiene.py no longer defaults to {DEFAULT_GRACE_MINUTES} minutes — "
        f"this gate's fixtures are calibrated to a window the tool no longer uses"
    )


def test_a_clean_tree_is_clean() -> None:
    """Baseline: a healthy tree with nothing dirty passes, and says so."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        res = _audit(repo)
        assert res.returncode == 0, f"clean tree failed the audit:\n{res.stdout}{res.stderr}"
        assert "0 advisory" in res.stdout, f"clean tree reported advisories:\n{res.stdout}"


def test_fresh_dirty_paths_do_not_fail_a_healthy_factory() -> None:
    """#38 cases (a) (b) (c), all fresh: a lane mid-task must not fail the audit.

    (a) a ledger append, (b) a new file another lane just created, (c) an edit to
    a tracked file — the three cases #38 reproduced as false REDs.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))

        with (repo / "evidence" / "ledger.jsonl").open("a") as fh:
            fh.write('{"n": 2, "event": "run"}\n')  # (a)
        (repo / "tests" / "test_inflight_gate.py").write_text("x = 1\n")  # (b)
        with (repo / "README.md").open("a") as fh:
            fh.write("\n# touch\n")  # (c)

        res = _audit(repo)
        assert res.returncode == 0, (
            "a healthy factory with a lane mid-task failed the audit — the #38 "
            f"race is back:\n{res.stdout}{res.stderr}"
        )
        for path in (
            "evidence/ledger.jsonl",
            "tests/test_inflight_gate.py",
            "README.md",
        ):
            assert path in res.stderr, (
                f"{path} was dirty but the audit did not report it at all — "
                f"silence is not the fix; an advisory must still be printed:\n{res.stderr}"
            )
        assert "advisory" in res.stderr, f"no advisory section in:\n{res.stderr}"


def test_stranded_modified_tracked_file_still_fails() -> None:
    """#38 criterion 2 / issue #28: a genuinely stranded edit is still a violation.

    #28 fixed a false green here — the audit passed without examining modified
    tracked files at all. The age window must not re-open it.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        with (repo / "README.md").open("a") as fh:
            fh.write("\n# abandoned\n")
        _age_minutes(repo / "README.md", DEFAULT_GRACE_MINUTES + 120)

        res = _audit(repo)
        assert res.returncode == 1, (
            "a modified tracked file untouched for "
            f"{DEFAULT_GRACE_MINUTES + 120}m passed the audit — #28 is re-opened:\n"
            f"{res.stdout}{res.stderr}"
        )
        assert "README.md" in res.stderr, (
            f"the violation does not name the stranded path:\n{res.stderr}"
        )
        assert "untouched for" in res.stderr, (
            f"the violation does not state the age it was judged on:\n{res.stderr}"
        )


def test_untracked_litter_fails_at_any_age() -> None:
    """Litter is litter: `.bak` fails even when it is brand new."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        (repo / "notes.bak").write_text("left behind\n")

        res = _audit(repo)
        assert res.returncode == 1, (
            f"fresh untracked litter passed the audit:\n{res.stdout}{res.stderr}"
        )
        assert "notes.bak" in res.stderr, f"litter not named:\n{res.stderr}"


def test_require_committed_fails_with_no_grace() -> None:
    """The run-scoped invariant: a path this run owns must be committed, now.

    This is the sharp form of #28's catch — the measurement run knows which
    artifacts are its own, so it does not have to wait out a window for them.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        (repo / "evidence" / "scores").mkdir()
        artifact = repo / "evidence" / "scores" / "2026-09-18.md"
        artifact.write_text("# a fresh, stranded run artifact\n")

        res = _audit(repo, "--require-committed", "evidence/scores/2026-09-18.md")
        assert res.returncode == 1, (
            "a fresh uncommitted artifact this run declared as its own passed the "
            f"audit — the run-scoped invariant is not blocking:\n{res.stdout}{res.stderr}"
        )
        assert "required committed, but dirty" in res.stderr, (
            f"the run-scoped violation is not named as such:\n{res.stderr}"
        )


def test_the_window_is_the_only_lever() -> None:
    """Same fresh edit, two windows: rc=0 at the default, rc=1 at zero.

    This is #38's two done-criteria side by side, and the proof that no rule can
    satisfy both at one window: the 14:04Z live false RED was four freshly
    modified tracked files, which is byte-for-byte the fixture below. The strict
    form stays available for a single-lane factory by declaring `--grace-minutes 0`.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        with (repo / "README.md").open("a") as fh:
            fh.write("\n# fresh edit\n")

        default = _audit(repo)
        strict = _audit(repo, "--grace-minutes", "0")

        assert default.returncode == 0, (
            f"a fresh edit failed the default window:\n{default.stdout}{default.stderr}"
        )
        assert strict.returncode == 1, (
            "a fresh edit passed a zero-minute window — the window is not wired to "
            f"the classifier:\n{strict.stdout}{strict.stderr}"
        )
        assert "untouched for 0m or more" in strict.stderr, (
            f"the audit does not state the window it judged on:\n{strict.stderr}"
        )
