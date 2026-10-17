#!/usr/bin/env python3
"""Gate: the binding-sync tool refuses before it moves, and moves only when lawful.

THE MECHANISM IT GUARDS. Board #503, ordered by the ruling on #502. The tree that serves a
profile's law binding is a SHARED WORKING TREE that nothing fetches into and nothing checks
out, so its currency was owned by nobody: measured 2026-10-17T00:58Z, HEAD `a0ba409b`
against `origin/main` `65d954fe`, the loaded `state.md` at `8d354b69d8ac` against
`a93fe1d4600f`, its own ledger at 2657 rows against 3469. Two crons resolve their REPO from
`__file__`, so both computed against a stale ledger. `tools/sync_binding.py` is the
mechanism; this file is the proof that it cannot do the one thing that would be worse than
staying stale -- destroy a lane's unpushed work.

WHY THE PREDICATE IS PURE AND THE LAST PROBE IS NOT. `assess()` takes a FACTS dict and
returns one of three outcomes, so a synthetic dict probes every branch without a repository.
That is the load-bearing half: the refusal is the point of the tool, and a refusal that has
never refused is a comment. But purity alone cannot prove the tool is WIRED -- a perfect
predicate whose `main()` returned 0 on every path would pass every pure probe -- so the
final leg drives a REAL repository through all three outcomes and reads the exit code and
the moved HEAD.

THE DISCRIMINATING PAIR. `test_local_only_is_the_discriminating_fact` feeds the SAME facts
as the refusal probe minus `local_only`, and asserts the outcome flips to `fast-forward`.
Without it, a predicate that refused everything would pass the refusal probe: the probe
would be measuring "refuse is reachable", never "this fact causes it" (rule 6: a candidate
cause must be shown to DIFFER between the two arms).

THE SCOPE BOUND, stated not hidden. This gate proves the TOOL. It does not prove the CRON
that invokes it: the job lives in the harness `cron_jobs` table, and a mechanical suite runs
offline against a tree, so a gate reading that table would RED in every bootstrapped factory
that has no such table (#68's class). The cron's own existence is a dispatch criterion
verified at landing time, not a tree property.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools/sync_binding.py"


def _module():
    """Load the tool by PATH -- it is a script, not an importable package member."""
    spec = importlib.util.spec_from_file_location("sync_binding", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _facts(**overrides) -> dict:
    """A LEVEL, clean tree, with any fact replaced by the caller."""
    facts = {
        "repo": "/tmp/tree",
        "remote": "origin",
        "branch": "main",
        "read_at": "2026-10-17T00:00:00Z",
        "fetch_rc": 0,
        "fetch_stderr": "",
        "head": "a" * 40,
        "remote_tip": "a" * 40,
        "current_branch": "main",
        "local_only": [],
        "dirty": [],
        "behind": 0,
    }
    facts.update(overrides)
    return facts


def test_the_tool_is_present() -> None:
    assert TOOL.is_file(), f"no tool at {TOOL}"


def test_level_changes_nothing() -> None:
    """HEAD == the remote tip: no action, and the reason list is empty."""
    decision = _module().assess(_facts())
    assert decision["action"] == "level", decision


def test_behind_and_clean_fast_forwards() -> None:
    """Behind, clean, no local commits: the ONLY move this tool may make."""
    decision = _module().assess(_facts(remote_tip="b" * 40, behind=2))
    assert decision["action"] == "fast-forward", decision
    assert decision["target"] == "b" * 40
    assert decision["behind"] == 2


def test_local_only_commit_refuses() -> None:
    """A commit not in origin/main is a lane's work: REFUSE, and name the sha."""
    sha = "c" * 40
    decision = _module().assess(
        _facts(remote_tip="b" * 40, behind=2, local_only=[[sha, "2026-10-17", "wip"]])
    )
    assert decision["action"] == "refuse", decision
    assert sha[:8] in " ".join(decision["reasons"]), decision


def test_dirty_path_refuses() -> None:
    """Any path differing from HEAD -- staged, unstaged or UNTRACKED -- is a refusal."""
    decision = _module().assess(
        _facts(remote_tip="b" * 40, behind=2, dirty=["?? tools/notes.py"])
    )
    assert decision["action"] == "refuse", decision
    assert "tools/notes.py" in " ".join(decision["reasons"]), decision


def test_local_only_is_the_discriminating_fact() -> None:
    """The control: the SAME facts minus `local_only` must flip to fast-forward.

    Without this, a predicate that refused everything would pass the probe above.
    """
    sha = "c" * 40
    module = _module()
    refused = module.assess(
        _facts(remote_tip="b" * 40, behind=2, local_only=[[sha, "2026-10-17", "wip"]])
    )
    control = module.assess(_facts(remote_tip="b" * 40, behind=2))
    assert refused["action"] == "refuse", refused
    assert control["action"] == "fast-forward", control


def test_detached_head_refuses() -> None:
    """A tree not on `main` is not a tree this tool can move lawfully."""
    decision = _module().assess(_facts(current_branch="HEAD", remote_tip="b" * 40, behind=2))
    assert decision["action"] == "refuse", decision


def test_unreadable_facts_refuse() -> None:
    """A broken read is never a clean one."""
    module = _module()
    for broken in ({"head": None}, {"remote_tip": None}):
        decision = module.assess(_facts(**broken))
        assert decision["action"] == "refuse", (broken, decision)


def test_diverged_refuses() -> None:
    """HEAD differs from the tip but is neither behind nor ahead: not a shape to guess at."""
    decision = _module().assess(_facts(head="d" * 40, remote_tip="b" * 40, behind=0))
    assert decision["action"] == "refuse", decision


def test_receipt_lives_outside_the_worktree(tmp_path) -> None:
    """The receipt must not dirty the tree -- that is the one condition it refuses on."""
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    path = _module().receipt_path(tmp_path)
    assert path is not None, "the receipt path could not be resolved in a real repository"
    assert path.parent != tmp_path, f"the receipt sits IN the worktree: {path}"
    assert path.parent.name == ".git", path


def test_the_binding_reader_uses_the_declared_schema(tmp_path, monkeypatch) -> None:
    """The declaration names `profile` + `skill`, NOT an absolute path.

    A reader keyed on an `entry` field would report NOT RUN on a CORRECT declaration --
    the instrument unable to observe the very surface it exists for -- and its verdict
    would be indistinguishable from a tree that declares nothing.
    """
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    (repo / "skills/meta-factory").mkdir(parents=True)
    (repo / "docs").mkdir()
    entry = home / ".opencrabs/profiles/ops/skills/meta-factory"
    entry.parent.mkdir(parents=True)
    entry.symlink_to(repo / "skills/meta-factory")
    (repo / "docs/harness-bindings.json").write_text(
        '{"profile": "ops", "bindings": ['
        '{"skill": "meta-factory", "repo_path": "skills/meta-factory", "form": "dir"}]}'
    )
    monkeypatch.setenv("HOME", str(home))

    rows, reason = _module().read_binding(repo)
    assert rows, f"a correct declaration did not resolve: {reason}"
    assert rows[0]["skill"] == "meta-factory", rows

    # The control: the same declaration with the profile entry pointing OUTSIDE this tree
    # must report NOT RUN with its reason, so a reader that resolved anything cannot pass.
    entry.unlink()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    entry.symlink_to(outside)
    rows, reason = _module().read_binding(repo)
    assert rows == [], rows
    assert reason, "an unbound tree reported no reason, so it reads as a clean verdict"


def test_exit_codes_and_the_actual_move(tmp_path) -> None:
    """All three outcomes through `main()` on a REAL repository: rc 0 / 0 / 3, and a move."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", "-b", "main", str(origin)], check=True)
    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", "-q", str(origin), str(seed)], check=True,
                   capture_output=True)

    def _commit(repo: Path, name: str, text: str) -> None:
        (repo / name).write_text(text)
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "-c", "user.email=t@t.t", "-c", "user.name=T",
             "commit", "-q", "-m", text],
            check=True,
        )

    _commit(seed, "state.md", "v1")
    subprocess.run(["git", "-C", str(seed), "push", "-q", "origin", "main"], check=True)

    tree = tmp_path / "tree"
    subprocess.run(["git", "clone", "-q", str(origin), str(tree)], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(tree), "config", "user.email", "t@t.t"], check=True)
    subprocess.run(["git", "-C", str(tree), "config", "user.name", "T"], check=True)
    module = _module()

    # leg 1: LEVEL
    assert module.main(["--repo", str(tree), "--apply"]) == 0
    level = subprocess.run(["git", "-C", str(tree), "rev-parse", "HEAD"],
                           capture_output=True, text=True).stdout.strip()

    # leg 2: BEHIND and CLEAN -> the move actually happens
    _commit(seed, "state.md", "v2")
    subprocess.run(["git", "-C", str(seed), "push", "-q", "origin", "main"], check=True)
    assert module.main(["--repo", str(tree), "--apply"]) == 0
    moved = subprocess.run(["git", "-C", str(tree), "rev-parse", "HEAD"],
                           capture_output=True, text=True).stdout.strip()
    tip = subprocess.run(["git", "-C", str(origin), "rev-parse", "main"],
                         capture_output=True, text=True).stdout.strip()
    assert moved == tip, f"tree at {moved[:8]}, origin/main at {tip[:8]}"
    assert (tree / "state.md").read_text() == "v2"

    # leg 3: a LOCAL-ONLY commit -> rc 3, and nothing moves
    _commit(tree, "local.md", "wip")
    before = subprocess.run(["git", "-C", str(tree), "rev-parse", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    assert module.main(["--repo", str(tree), "--apply"]) == 3
    after = subprocess.run(["git", "-C", str(tree), "rev-parse", "HEAD"],
                           capture_output=True, text=True).stdout.strip()
    assert after == before, "the refused run moved HEAD"
    assert level != moved, "leg 2 did not move the tree, so leg 3 proves nothing"
