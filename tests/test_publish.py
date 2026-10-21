#!/usr/bin/env python3
"""Gate: the pusher publishes after a grace window, and never rewrites history.

Origin: issue #146, ruled at ledger n=1168. Nothing guaranteed a commit reached
`origin`, so a turn killed after committing but before pushing stranded work that
no surface could see. The remedy is a periodic pusher, and its three bounds are
each checkable — which is what this gate does, because a pusher is a tool that
runs from a clock with no lane watching it, and the failure it can cause (rewritten
PUBLISHED history) is worse than the gap it closes.

THREE ARMS, ONE PER BOUND
-------------------------
- **The grace window HOLDS a fresh commit.** Measured on a throwaway repository with
  a real bare remote: the pusher runs with `--apply` and the commit is still ahead of
  the remote afterwards. A pusher that published immediately would manufacture the
  published-then-amended divergence this factory already paid for once.
- **The grace window LETS AN OLD COMMIT THROUGH**, so the window is a window and not
  a permanent refusal — the control that makes the hold a finding rather than a broken
  tool. Without it, a pusher that never pushed would pass the first arm.
- **A DIVERGED BRANCH IS REPORTED, NOT RESOLVED**, in two clones against one remote:
  the report names the divergence, and the repository is UNCHANGED afterwards — same
  HEAD, same remote tip, no merge and no extra commit.

WHY THE SOURCE ARM IS TOKEN-BASED AND NOT A GREP
------------------------------------------------
"No force, no rebase" is a bound that has to be written down to be maintained, and
writing it down means the module docstring necessarily CONTAINS both words. So the
arm strips docstrings and comments and asserts the tokens are absent from what
remains — the executable text — and its own extractor is proved to still see a
token it must see, because an extractor that returned nothing would pass the arm
vacuously. That is the failure this factory has shipped twice.

Run:  python3 tests/test_publish.py
Exit: 0 every arm passed; 1 an arm failed.
"""

from __future__ import annotations

import ast
import contextlib
import datetime as dt
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import tokenize
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent


def _repo_root(here: Path) -> Path:
    """The repository root, whichever COPY of this file is running.

    This file ships in two places (tests/ and TEMPLATE/tests/), so the
    parent of its own directory is the copy root, not the repo root: in the
    TEMPLATE twin that is <repo>/TEMPLATE, and a path built as
    REPO/"TEMPLATE"/... would resolve to <repo>/TEMPLATE/TEMPLATE/... .
    The repo root is the ancestor that holds both tools/ and TEMPLATE/tools/.
    """
    for cand in (here.parent, here.parent.parent):
        if (cand / "tools").is_dir() and (cand / "TEMPLATE" / "tools").is_dir():
            return cand
    return here.parent


ROOT = _repo_root(HERE)
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "tools"))

import publish as pub  # noqa: E402

TOOL = REPO / "tools" / "publish.py"
FORBIDDEN = ("force", "rebase", "amend", "reset")
MUST_SEE = ("push", "merge-base", "ls-remote")
GRACE = 900

checks: list[tuple[bool, str, str]] = []


def check(ok: bool, name: str, detail: str = "") -> None:
    checks.append((bool(ok), name, detail))


def git(repo: Path, *args: str, env: dict | None = None, check_rc: bool = True):
    merged = dict(os.environ)
    merged.update(env or {})
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, env=merged, timeout=120,
    )
    if check_rc and proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def init_bare(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "--bare", "-q")
    git(path, "symbolic-ref", "HEAD", "refs/heads/main")
    return path


def init_work(path: Path, remote: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q")
    git(path, "symbolic-ref", "HEAD", "refs/heads/main")
    git(path, "config", "user.email", "probe@probe.invalid")
    git(path, "config", "user.name", "probe")
    git(path, "remote", "add", "origin", str(remote))
    return path


def commit(repo: Path, name: str, when: dt.datetime | None = None) -> str:
    (repo / name).write_text(f"{name}\n", encoding="utf-8")
    git(repo, "add", "-A")
    env = {}
    if when is not None:
        stamp = when.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        env = {"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
    git(repo, "commit", "-q", "-m", name, env=env)
    return git(repo, "rev-parse", "HEAD")


def head_of(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD")


def ahead(repo: Path, remote_ref: str = "origin/main") -> int:
    return int(git(repo, "rev-list", "--count", f"{remote_ref}..HEAD"))

def sync_of(report: dict) -> dict:
    """The round's `sync` payload, or an EMPTY dict when the round carried none.

    A missing payload must FAIL a check, not raise: if the sync is ever removed the arms
    below have to report a clean FAIL, and `report["sync"]["ok"]` on a `None` would instead
    crash the whole gate at the first arm that reads it."""
    return report.get("sync") or {}

def write_commit(repo: Path, name: str, content: str) -> str:
    """Commit `name` with EXPLICIT content, so a second commit on the same path is a real
    change rather than an empty one -- `commit()` always writes `f"{name}\\n"`, which makes
    two commits of the same path a no-op and would quietly hollow out a fixture that needs
    the remote to genuinely advance."""
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", f"probe: {name}")
    return head_of(repo)

def configured_clone(root: Path, remote: Path, name: str) -> Path:
    """A clone of `remote` with a committer identity set, so the fixture can advance the
    remote from a SECOND checkout the way the live shared tree is advanced by lanes."""
    dest = root / name
    git(root, "clone", "-q", str(remote), str(dest))
    git(dest, "config", "user.email", "probe@probe.invalid")
    git(dest, "config", "user.name", "probe")
    return dest


def _placement(root: Path) -> dict:
    """The placement leg, read from the TOOL that owns it (#452).

    Never re-implemented here: a second copy of the predicate would let this gate pass
    while the shipped leg still read the orphan as clean, which is the defect the arm
    exists to catch."""
    spec = importlib.util.spec_from_file_location(
        "hygiene_placement_for_publish_gate", REPO / "tools" / "hygiene.py"
    )
    assert spec and spec.loader, "cannot load tools/hygiene.py"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.placement_leg(root)

# --- pure predicates -----------------------------------------------------------------


def pure_arms() -> None:
    now = dt.datetime(2026, 9, 26, 12, 0, 0, tzinfo=dt.timezone.utc)
    fresh = {"sha": "f" * 40, "committed_at": "2026-09-26T11:59:00Z", "session_id": "", "subject": "fresh"}
    old = {"sha": "o" * 40, "committed_at": "2026-09-26T10:00:00Z", "session_id": "", "subject": "old"}
    unreadable = {"sha": "u" * 40, "committed_at": "not-a-time", "session_id": "", "subject": "?"}

    to_pub, held = pub.publishable([fresh, old], grace_secs=GRACE, now=now)
    check(
        to_pub == [] and len(held) == 2,
        "the window is tested on the NEWEST commit, not the oldest",
        f"an old commit under a fresh one must not be published: to_publish={len(to_pub)} held={len(held)}",
    )

    to_pub, held = pub.publishable([old], grace_secs=GRACE, now=now)
    check(
        len(to_pub) == 1 and held == [],
        "an old commit is publishable",
        f"age={int(pub.age_secs(old['committed_at'], now))}s against a {GRACE}s window",
    )

    to_pub, held = pub.publishable([unreadable], grace_secs=GRACE, now=now)
    check(
        to_pub == [] and held == [unreadable],
        "an unreadable timestamp is HELD, never published",
        "an age that does not parse is not evidence of an old commit",
    )

    check(
        pub.publishable([], grace_secs=GRACE, now=now) == ([], []),
        "no commits is neither publishable nor held",
    )
    check(pub.parse_ts("2026-09-26T10:00:00Z") is not None, "parse_ts reads an ISO instant")
    check(pub.parse_ts("") is None and pub.age_secs("", now) is None, "parse_ts refuses empty text")


# --- source arm ----------------------------------------------------------------------


def executable_text(path: Path) -> str:
    """`path` with docstrings and comments removed — the executable half."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    doc_lines: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            for line in range(first.lineno, (first.end_lineno or first.lineno) + 1):
                doc_lines.add(line)
    kept = [line for i, line in enumerate(src.splitlines(), 1) if i not in doc_lines]
    lines = kept
    for tok in tokenize.generate_tokens(io.StringIO("\n".join(lines)).readline):
        if tok.type == tokenize.COMMENT:
            row, col = tok.start
            lines[row - 1] = lines[row - 1][:col]
    return "\n".join(lines)


def source_arms() -> None:
    text = executable_text(TOOL)
    lower = text.lower()
    present = [token for token in FORBIDDEN if token in lower]
    check(
        not present,
        "no force and no rebase in the pusher's executable path",
        f"docstrings and comments stripped; found {present}",
    )
    missing = [token for token in MUST_SEE if token not in lower]
    check(
        not missing,
        "the extractor still sees the tokens it must see (non-vacuity control)",
        f"an extractor returning nothing would pass the arm above; missing={missing}",
    )


# --- live arms, throwaway repositories ------------------------------------------------


def no_remote_arm() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "r"
        repo.mkdir(parents=True, exist_ok=True)
        git(repo, "init", "-q")
        git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
        report = pub.publish(repo, remote="origin", branch="main")
        check(
            report["status"] == "no-remote" and "not configured" in report["reason"],
            "a repository with no remote is REPORTED, not treated as in sync",
            f"status={report['status']}",
        )


def unreachable_arm() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = init_work(Path(tmp) / "r", Path(tmp) / "missing.git")
        commit(repo, "a.txt")
        report = pub.publish(repo, remote="origin", branch="main")
        check(
            report["status"] == "unreachable",
            "an unreachable remote is REPORTED, never silently replaced by the local ref",
            f"status={report['status']} reason={report['reason'][:80]}",
        )


def not_on_branch_arm() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        remote = init_bare(Path(tmp) / "remote.git")
        repo = init_work(Path(tmp) / "r", remote)
        commit(repo, "a.txt")
        git(repo, "push", "-q", "origin", "main:main")
        git(repo, "checkout", "-q", "-b", "side")
        report = pub.publish(repo, remote="origin", branch="main")
        check(
            report["status"] == "not-on-branch",
            "a pusher on another branch REFUSES rather than publishing that branch",
            f"status={report['status']}",
        )


def detached_head_publishes_arm() -> None:
    """Issue #329, ruled at ledger n=2407. The law requires every lane to work in a
    worktree checked out at `origin/main` (SKILL section 4), so a lane's HEAD is DETACHED
    by construction -- and the pusher refused exactly that state, which made it unusable by
    the lanes it exists to govern. The detached HEAD resolves to the configured branch from
    the remote-tracking ref, and the round publishes it like any other.
    """
    with tempfile.TemporaryDirectory() as tmp:
        remote = init_bare(Path(tmp) / "remote.git")
        repo = init_work(Path(tmp) / "r", remote)
        commit(repo, "a.txt")
        git(repo, "push", "-q", "origin", "main:main")
        old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=GRACE * 4)
        git(repo, "checkout", "-q", "--detach")
        sha = commit(repo, "b.txt", when=old)

        report = pub.publish(repo, remote="origin", branch="main", grace_secs=GRACE, apply=True)

        tip_after = git(remote, "rev-parse", "refs/heads/main")
        rec = report.get("receipt") or {}
        check(
            report["status"] == "published" and tip_after == sha,
            "a DETACHED head publishes to the configured branch (the law's own lane state)",
            f"status={report['status']} remote tip {'== HEAD' if tip_after == sha else '!= HEAD'}",
        )
        receipt_file = pub.receipt_path(repo)
        body = pub.read_receipt(repo)[0] if receipt_file and receipt_file.is_file() else None
        check(
            isinstance(body, dict)
            and body.get("sha") == sha
            and body.get("remote") == "origin"
            and body.get("branch") == "main"
            and body.get("instant"),
            "a detached round still records {sha, instant, remote, branch}",
            f"receipt={rec} body={body}",
        )

def detached_off_branch_refuses_arm() -> None:
    """The control that makes the arm above a RESOLUTION and not a removal of the guard.
    A detached HEAD that does NOT descend from `origin/main` -- here a feature branch that
    has diverged from it -- has no claim to `main`: it is refused, and nothing moves.
    """
    with tempfile.TemporaryDirectory() as tmp:
        remote = init_bare(Path(tmp) / "remote.git")
        repo = init_work(Path(tmp) / "r", remote)
        commit(repo, "a.txt")
        git(repo, "push", "-q", "origin", "main:main")
        git(repo, "checkout", "-q", "-b", "side")
        side_sha = commit(repo, "side.txt")
        git(repo, "push", "-q", "origin", "side:side")
        git(repo, "checkout", "-q", "main")
        commit(repo, "main2.txt")
        git(repo, "push", "-q", "origin", "main:main")
        tip_before = git(remote, "rev-parse", "refs/heads/main")
        git(repo, "checkout", "-q", "--detach", side_sha)

        report = pub.publish(repo, remote="origin", branch="main", grace_secs=0, apply=True)

        tip_after = git(remote, "rev-parse", "refs/heads/main")
        check(
            report["status"] == "not-on-branch" and tip_after == tip_before,
            "a detached head that does NOT descend from origin/main is REFUSED, and nothing moves",
            f"status={report['status']} reason={report['reason'][:90]}",
        )

def detached_behind_arm() -> None:
    """A detached HEAD BEHIND `origin/main` is a STALE CHECKOUT, not an off-line commit:
    it is still on main's line, so the pusher must NOT refuse it -- it must let the round
    reach the fast-forward check and report BEHIND, which names the gap. Refusing it here
    would swap a true status for a false reason, which is what the first cut of #329 did.

    (#418) BEHIND, not DIVERGED: this checkout is a PURE ANCESTOR of the remote tip -- it
    carries nothing of its own -- so it is fast-forwardable and must not be reported as a
    conflict. The old one-sided test called it DIVERGED and red the normal steady state.
    """
    with tempfile.TemporaryDirectory() as tmp:
        remote = init_bare(Path(tmp) / "remote.git")
        repo = init_work(Path(tmp) / "r", remote)
        stale = commit(repo, "a.txt")
        git(repo, "push", "-q", "origin", "main:main")
        commit(repo, "b.txt")
        git(repo, "push", "-q", "origin", "main:main")
        tip_before = git(remote, "rev-parse", "refs/heads/main")
        git(repo, "checkout", "-q", "--detach", stale)

        # REPORT-ONLY is a READ and does not sync (#418 PART 2): the patrol's freshness leg
        # reads this module's predicates on the same tree, and a read that fast-forwarded
        # would mutate the surface it was inspecting.
        report = pub.publish(repo, remote="origin", branch="main", grace_secs=0)
        check(
            report["status"] == "behind"
            and head_of(repo) == stale
            and git(remote, "rev-parse", "refs/heads/main") == tip_before,
            "a report-only round on a behind checkout reports BEHIND and moves nothing",
            f"status={report['status']} reason={report['reason'][:90]}",
        )
        check(
            report["diverged"] is None and report["behind"],
            "a pure-ancestor checkout carries NO diverged payload, only behind",
            f"behind={report['behind']} diverged={report['diverged']}",
        )

        # WITH --apply the same checkout SYNCS FIRST (#418 PART 2, owner q36 -> (a)): the
        # fast-forward advances HEAD to the tip, so the round no longer reads BEHIND at all.
        # The checkout has nothing of its own, so the round publishes nothing and the remote
        # tip is untouched -- advancing the LOCAL checkout is not publishing.
        report = pub.publish(repo, remote="origin", branch="main", grace_secs=0, apply=True)
        tip_after = git(remote, "rev-parse", "refs/heads/main")
        check(
            report["status"] == "in-sync"
            and sync_of(report).get("ok")
            and sync_of(report).get("before") == stale
            and sync_of(report).get("after") == tip_before,
            "with --apply a behind checkout fast-forwards to the tip, then reports in-sync",
            f"status={report['status']} sync={sync_of(report)}",
        )
        check(
            head_of(repo) == tip_before and tip_after == tip_before,
            "the fast-forward advances the CHECKOUT, never the remote tip",
            f"HEAD={'== tip' if head_of(repo) == tip_before else '!= tip'} remote={'moved' if tip_after != tip_before else 'unchanged'}",
        )

def in_sync_arm() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        remote = init_bare(Path(tmp) / "remote.git")
        repo = init_work(Path(tmp) / "r", remote)
        commit(repo, "a.txt")
        git(repo, "push", "-q", "origin", "main:main")
        report = pub.publish(repo, remote="origin", branch="main")
        check(
            report["status"] == "in-sync" and report["count"] == 0,
            "an in-sync repository reports in-sync with a zero count",
            f"status={report['status']} count={report['count']}",
        )


def grace_holds_arm() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        remote = init_bare(Path(tmp) / "remote.git")
        repo = init_work(Path(tmp) / "r", remote)
        commit(repo, "a.txt")
        git(repo, "push", "-q", "origin", "main:main")
        tip_before = git(remote, "rev-parse", "refs/heads/main")
        commit(repo, "b.txt")
        before = ahead(repo)

        report = pub.publish(repo, remote="origin", branch="main", grace_secs=GRACE, apply=True)

        after = ahead(repo)
        tip_after = git(remote, "rev-parse", "refs/heads/main")
        check(
            report["status"] == "held" and before == 1 and after == 1 and tip_after == tip_before,
            "a commit younger than the grace window stays LOCAL",
            f"status={report['status']} ahead {before}->{after} remote tip {'moved' if tip_after != tip_before else 'unchanged'}",
        )
        check(
            report["held"] and report["held"][0]["sha"] == head_of(repo),
            "the held commit is NAMED, with its age",
            f"held={report['held']}",
        )


def old_commit_publishes_arm() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        remote = init_bare(Path(tmp) / "remote.git")
        repo = init_work(Path(tmp) / "r", remote)
        commit(repo, "a.txt")
        git(repo, "push", "-q", "origin", "main:main")
        old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=GRACE * 4)
        sha = commit(repo, "b.txt", when=old)

        report = pub.publish(repo, remote="origin", branch="main", grace_secs=GRACE, apply=True)

        tip_after = git(remote, "rev-parse", "refs/heads/main")
        check(
            report["status"] == "published" and tip_after == sha and ahead(repo) == 0,
            "a commit older than the window IS published (the control)",
            f"status={report['status']} remote tip {'== HEAD' if tip_after == sha else '!= HEAD'} ahead={ahead(repo)}",
        )


def receipt_arm() -> None:
    """Issue #284, leg (c)(1). The pusher records the push it made, so the patrol can tell
    'the pusher ran late' from 'the pusher never ran' -- and can name a tip that left through
    some other path. The record is a FILE, never a ledger row: the pusher is not a lane, and
    the ledger's actor set is closed.
    """
    with tempfile.TemporaryDirectory() as tmp:
        remote = init_bare(Path(tmp) / "remote.git")
        repo = init_work(Path(tmp) / "r", remote)
        commit(repo, "a.txt")
        git(repo, "push", "-q", "origin", "main:main")
        old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=GRACE * 4)
        sha = commit(repo, "b.txt", when=old)

        report = pub.publish(repo, remote="origin", branch="main", grace_secs=GRACE, apply=True)
        rec = report.get("receipt") or {}
        path = pub.receipt_path(repo)

        check(
            report["status"] == "published" and rec.get("sha") == sha,
            "a published round records the sha it pushed",
            f"status={report['status']} receipt={rec}",
        )
        check(
            path is not None and path.is_file(),
            "the receipt is written to the repo's git common dir",
            f"receipt={rec} path={path}",
        )
        body = pub.read_receipt(repo)[0] if path and path.is_file() else None
        check(
            isinstance(body, dict) and body.get("sha") == sha and body.get("instant"),
            "the receipt carries the sha AND the instant of the push",
            f"body={body}",
        )
        check(
            rec.get("path") == str(path)
            and path is not None
            and path.parent.name == ".git"
            and not (repo / "evidence" / "ledger.jsonl").exists(),
            "the receipt is a FILE in the git common dir, never a ledger row",
            f"receipt={rec} path={path}",
        )

    # The control: a round that pushed NOTHING must leave no receipt behind, or the arm
    # above would pass on a file written unconditionally.
    with tempfile.TemporaryDirectory() as tmp:
        remote = init_bare(Path(tmp) / "remote.git")
        repo = init_work(Path(tmp) / "r", remote)
        commit(repo, "a.txt")
        git(repo, "push", "-q", "origin", "main:main")
        old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=GRACE * 4)
        commit(repo, "b.txt", when=old)

        report = pub.publish(repo, remote="origin", branch="main", grace_secs=GRACE, apply=False)
        control_path = pub.receipt_path(repo)
        check(
            report["status"] == "would-publish"
            and not (control_path is not None and control_path.is_file()),
            "a round that pushed nothing records NO receipt (the control)",
            f"status={report['status']} path={control_path}",
        )

        # An absent receipt is neither an error nor a mismatch: the leg reads it as
        # "no baseline", never as a clean one.
        absent, why = pub.read_receipt(repo)
        check(
            absent is None and bool(why),
            "an absent receipt is reported as absent, never as a clean read",
            f"receipt={absent} why={why!r}",
        )

def receipt_is_shared_across_worktrees_arm() -> None:
    """Issue #445: the receipt is keyed on the REPOSITORY, not on the checkout.

    Two checkouts of ONE repository -- a main clone and a linked worktree -- must resolve
    the SAME receipt file. Before this shape each resolved its own
    `evidence/publish-receipt.json` INSIDE ITS OWN TREE, so a push made from one was
    invisible to the other while the patrol's receipt arm compared a GLOBAL remote tip
    against whichever receipt the READING checkout happened to hold. Measured on one tip
    across three checkouts: 0 / 1 / 1 problems, and BOTH findings named the lane that had
    pushed correctly.
    """
    with tempfile.TemporaryDirectory() as tmp:
        remote = init_bare(Path(tmp) / "remote.git")
        repo = init_work(Path(tmp) / "r", remote)
        commit(repo, "a.txt")
        git(repo, "push", "-q", "origin", "main:main")

        # a LINKED worktree: a second checkout of the same repository, one object store
        wt = Path(tmp) / "wt"
        git(repo, "worktree", "add", "-q", str(wt), "-b", "side")

        main_path = pub.receipt_path(repo)
        wt_path = pub.receipt_path(wt)
        check(
            main_path is not None and wt_path is not None and main_path == wt_path,
            "both checkouts of one repository resolve the SAME receipt path",
            f"main={main_path} worktree={wt_path}",
        )
        check(
            main_path is not None and main_path.parent.name == ".git",
            "the receipt lives in the repository's git common dir, not inside a checkout",
            f"path={main_path}",
        )

        # the ACCEPTANCE: write it from the main checkout, read it from the worktree
        tip = head_of(repo)
        written, why = pub.write_receipt(
            repo, sha=tip, remote="origin", branch="main",
            instant=dt.datetime.now(dt.timezone.utc).isoformat(),
        )
        seen, seen_why = pub.read_receipt(wt)
        check(
            written is not None and isinstance(seen, dict) and seen.get("sha") == tip,
            "a receipt written in one checkout is READ by a sibling worktree",
            f"written={written} seen={seen} why={seen_why!r}",
        )

        # the ORIGIN half of the honesty requirement: the record names who wrote it
        check(
            isinstance(seen, dict) and seen.get("checkout") == str(repo.resolve()),
            "the receipt names the checkout that wrote it (the honesty half)",
            f"checkout={None if not isinstance(seen, dict) else seen.get('checkout')}",
        )

        # and the defect's own shape is gone: no checkout-local receipt is left behind
        check(
            not (repo / "evidence" / "publish-receipt.json").exists()
            and not (wt / "evidence" / "publish-receipt.json").exists(),
            "neither checkout leaves a checkout-local receipt behind",
            f"main_local={(repo / 'evidence' / 'publish-receipt.json').exists()} "
            f"wt_local={(wt / 'evidence' / 'publish-receipt.json').exists()}",
        )

def legacy_receipt_orphan_arm() -> None:
    """Issue #452: the next push REMOVES the pre-#445 checkout-local receipt.

    #445 moved the record into the repository's git common dir, but every checkout that had
    already pushed kept the OLD `evidence/publish-receipt.json` behind. Nothing creates it
    any more and nothing declares it, so the placement leg reads it as a TRUE mismatch --
    a JSON file in a directory that admits only markdown and jsonl.

    Two halves, and the second is the discriminating one: the arm is not allowed to pass by
    having planted something the leg would ignore anyway. The SAME planted orphan is shown
    to be READ as a mismatch before the push, and GONE after it -- so a leg that reported
    the orphan regardless, or a pusher that never removed it, fails here.
    """
    legacy_rel = pub.LEGACY_RECEIPT_REL
    with tempfile.TemporaryDirectory() as tmp:
        remote = init_bare(Path(tmp) / "remote.git")
        repo = init_work(Path(tmp) / "r", remote)
        commit(repo, "a.txt")
        git(repo, "push", "-q", "origin", "main:main")

        # exactly what the pre-#445 pusher left in a checkout that had already pushed
        orphan = repo / legacy_rel
        orphan.parent.mkdir(parents=True, exist_ok=True)
        orphan.write_text('{"sha": "deadbeef"}\n', encoding="utf-8")
        check(
            orphan.is_file(),
            "the fixture plants the legacy receipt where the pre-#445 pusher left it",
            f"path={orphan}",
        )

        # THE CONTROL: the leg READS the planted orphan as a mismatch. Without this the
        # arm below would also pass if the leg never looked at `evidence/` at all.
        before = _placement(repo)
        check(
            any(m["path"] == str(legacy_rel) for m in before["mismatches"]),
            "the planted legacy receipt IS read as a placement mismatch (the control)",
            f"mismatches={[m['path'] for m in before['mismatches']]}",
        )

        old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=GRACE * 4)
        sha = commit(repo, "b.txt", when=old)
        report = pub.publish(repo, remote="origin", branch="main", grace_secs=GRACE, apply=True)
        leg = report.get("legacy_receipt") or {}

        check(
            report["status"] == "published",
            "the round pushed, so the removal ran on a real publish path",
            f"status={report['status']} sha={sha}",
        )
        check(
            not orphan.exists(),
            "a successful push REMOVES the legacy checkout-local receipt",
            f"exists={orphan.exists()} reported={leg}",
        )
        check(
            leg.get("path") == str(orphan) and not leg.get("reason"),
            "the round REPORTS the removal by name",
            f"legacy_receipt={leg}",
        )

        # the #445 record is untouched: the removal is of the LEGACY path only
        receipt = pub.receipt_path(repo)
        check(
            receipt is not None and receipt.is_file() and receipt != orphan,
            "the common-dir receipt still stands after the legacy one is removed",
            f"receipt={receipt} legacy={orphan}",
        )

        # and the leg now reads clean on the same tree that was RED a moment ago
        after = _placement(repo)
        check(
            after["mismatches"] == [],
            "the placement leg reads clean once the push has swept the orphan",
            f"mismatches={[m['path'] for m in after['mismatches']]}",
        )

    # THE INERT HALF: a checkout with NO orphan pays nothing and reports nothing. The
    # removal is a single stat, so a member factory that never carried the path sees no
    # change -- and a report that named a removal here would be naming a file it never had.
    with tempfile.TemporaryDirectory() as tmp:
        remote = init_bare(Path(tmp) / "remote.git")
        repo = init_work(Path(tmp) / "r", remote)
        commit(repo, "a.txt")
        git(repo, "push", "-q", "origin", "main:main")
        old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=GRACE * 4)
        commit(repo, "b.txt", when=old)

        clean_report = pub.publish(
            repo, remote="origin", branch="main", grace_secs=GRACE, apply=True
        )
        clean_leg = clean_report.get("legacy_receipt") or {}
        check(
            clean_report["status"] == "published"
            and clean_leg.get("path") is None
            and not clean_leg.get("reason")
            and not (repo / legacy_rel).exists(),
            "a checkout with no legacy receipt reports NOTHING (the inert half)",
            f"status={clean_report['status']} legacy_receipt={clean_leg}",
        )

        # a removal that FAILED is REPORTED, never silently swallowed: an orphan that is a
        # directory is not a file, so the pusher leaves it standing and says why
        stubborn = repo / legacy_rel
        stubborn.mkdir(parents=True, exist_ok=True)
        stuck = pub.remove_legacy_receipt(repo)
        check(
            stuck[0] is None and stubborn.is_dir(),
            "a legacy path that cannot be removed is left standing, never forced",
            f"result={stuck} exists={stubborn.is_dir()}",
        )

def dry_run_arm() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        remote = init_bare(Path(tmp) / "remote.git")
        repo = init_work(Path(tmp) / "r", remote)
        commit(repo, "a.txt")
        git(repo, "push", "-q", "origin", "main:main")
        old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=GRACE * 4)
        commit(repo, "b.txt", when=old)

        report = pub.publish(repo, remote="origin", branch="main", grace_secs=GRACE, apply=False)

        check(
            report["status"] == "would-publish" and ahead(repo) == 1,
            "without --apply the round REPORTS and pushes nothing",
            f"status={report['status']} ahead={ahead(repo)}",
        )


def divergence_arm() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote = init_bare(root / "remote.git")
        seed = init_work(root / "seed", remote)
        commit(seed, "a.txt")
        git(seed, "push", "-q", "origin", "main:main")

        mine = root / "mine"
        git(root, "clone", "-q", str(remote), str(mine))
        git(mine, "config", "user.email", "probe@probe.invalid")
        git(mine, "config", "user.name", "probe")
        theirs = root / "theirs"
        git(root, "clone", "-q", str(remote), str(theirs))
        git(theirs, "config", "user.email", "probe@probe.invalid")
        git(theirs, "config", "user.name", "probe")

        commit(theirs, "theirs.txt")
        git(theirs, "push", "-q", "origin", "main:main")
        remote_tip = git(remote, "rev-parse", "refs/heads/main")

        commit(mine, "mine.txt")
        my_head = head_of(mine)

        report = pub.publish(mine, remote="origin", branch="main", grace_secs=0, apply=True)

        after_head = head_of(mine)
        after_tip = git(remote, "rev-parse", "refs/heads/main")
        check(
            report["status"] == "diverged",
            "a diverged branch is REPORTED",
            f"status={report['status']}",
        )
        check(
            report["diverged"] and report["diverged"]["remote_tip"] == remote_tip,
            "the divergence report NAMES the remote tip it read",
            f"{report['diverged']}",
        )
        check(
            after_head == my_head and after_tip == remote_tip,
            "the divergence is NOT RESOLVED: neither side moved",
            f"local HEAD {'moved' if after_head != my_head else 'unchanged'}, remote tip {'moved' if after_tip != remote_tip else 'unchanged'}",
        )
        check(
            not (mine / "theirs.txt").exists(),
            "no merge, fetch or reconcile brought the other side in",
        )


def behind_is_not_diverged_arm() -> None:
    """#418, the hermetic fixture PAIR. The live tree exhibits ONLY the behind state (the
    shared tree is a pure ancestor of `origin/main`), so the two statuses cannot be
    separated on it -- this arm builds BOTH shapes in throwaway repositories and asserts
    each gets its OWN name. Fixture B is the control that keeps fixture A from passing a
    pusher that simply stopped reporting divergence altogether.

    BEHIND: HEAD is a PURE ANCESTOR of the remote tip (ahead == 0) -- a stale read copy
    with nothing of its own, fast-forwardable. It must NOT read DIVERGED, which is the
    false RED that reds the normal steady state under the worktree law.
    DIVERGED: ahead > 0 AND behind > 0 -- the only shape #146's ruling is about, still
    reported and never resolved.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # --- fixture A: pure BEHIND (ahead == 0) ---
        remote_a = init_bare(root / "behind" / "remote.git")
        repo_a = init_work(root / "behind" / "r", remote_a)
        stale = commit(repo_a, "a.txt")
        git(repo_a, "push", "-q", "origin", "main:main")
        commit(repo_a, "b.txt")
        git(repo_a, "push", "-q", "origin", "main:main")
        tip_a = git(remote_a, "rev-parse", "refs/heads/main")
        git(repo_a, "checkout", "-q", "--detach", stale)

        # The CLASSIFICATION is read report-only: a read must not sync (#418 PART 2).
        report_a = pub.publish(repo_a, remote="origin", branch="main", grace_secs=0)
        check(
            report_a["status"] == "behind",
            "fixture A (pure ancestor, ahead==0) reports BEHIND, not DIVERGED",
            f"status={report_a['status']} reason={report_a['reason'][:100]}",
        )
        check(
            report_a["diverged"] is None
            and report_a["behind"]["remote_ahead_by"] == "1",
            "the BEHIND report carries behind.remote_ahead_by and NO diverged payload",
            f"behind={report_a['behind']} diverged={report_a['diverged']}",
        )
        check(
            git(remote_a, "rev-parse", "refs/heads/main") == tip_a,
            "the BEHIND round moved nothing (reported, not resolved)",
            "remote tip unchanged",
        )

        # THE PART-2 CONTROL (#418 PART 2): the SAME behind checkout, now publishing. The
        # sync fast-forwards it to the tip FIRST, so it no longer reads BEHIND -- the false
        # RED the leg suffered on the normal steady state is gone. This is the arm a
        # pusher that only reports (and never syncs) FAILS, which is what makes the pair
        # above a finding rather than a tautology.
        report_a2 = pub.publish(repo_a, remote="origin", branch="main", grace_secs=0, apply=True)
        check(
            report_a2["status"] == "in-sync"
            and sync_of(report_a2).get("ok")
            and head_of(repo_a) == tip_a,
            "the same behind checkout, with --apply, syncs to the tip and stops reading BEHIND",
            f"status={report_a2['status']} sync={report_a2['sync']} HEAD={'== tip' if head_of(repo_a) == tip_a else '!= tip'}",
        )
        check(
            git(remote_a, "rev-parse", "refs/heads/main") == tip_a,
            "syncing a behind checkout publishes nothing (it had nothing of its own)",
            "remote tip unchanged",
        )

        # --- fixture B: genuine DIVERGENCE (ahead > 0 AND behind > 0) ---
        base = root / "diverged"
        remote_b = init_bare(base / "remote.git")
        seed_b = init_work(base / "seed", remote_b)
        commit(seed_b, "a.txt")
        git(seed_b, "push", "-q", "origin", "main:main")

        mine = base / "mine"
        git(base, "clone", "-q", str(remote_b), str(mine))
        git(mine, "config", "user.email", "probe@probe.invalid")
        git(mine, "config", "user.name", "probe")
        commit(mine, "mine.txt")                      # local ahead by 1

        theirs = base / "theirs"
        git(base, "clone", "-q", str(remote_b), str(theirs))
        git(theirs, "config", "user.email", "probe@probe.invalid")
        git(theirs, "config", "user.name", "probe")
        commit(theirs, "theirs.txt")
        git(theirs, "push", "-q", "origin", "main:main")   # remote ahead by 1
        # FETCH, so the remote tip object is LOCAL and the two counts are READABLE. A tree
        # that has diverged normally has fetched -- the live #418 reading carried
        # `remote_ahead_by: 11`, i.e. a readable count -- and `rev-list --count` needs the
        # tip object present. Without this the counts read "unreadable", which is the
        # conservative fallback and would mask the ahead/behind reading under test.
        git(mine, "fetch", "-q", "origin")

        head_before = head_of(mine)
        tip_b = git(remote_b, "rev-parse", "refs/heads/main")
        report_b = pub.publish(mine, remote="origin", branch="main", grace_secs=0, apply=True)
        check(
            report_b["status"] == "diverged",
            "fixture B (ahead>0 AND behind>0) still reports DIVERGED",
            f"status={report_b['status']}",
        )
        check(
            report_b["diverged"]
            and report_b["diverged"]["local_ahead_by"] == "1"
            and report_b["diverged"]["remote_ahead_by"] == "1",
            "the DIVERGED report names BOTH sides (ahead and behind)",
            f"{report_b['diverged']}",
        )
        check(
            head_of(mine) == head_before
            and git(remote_b, "rev-parse", "refs/heads/main") == tip_b,
            "the DIVERGED round moved nothing (reported, not resolved)",
            "both sides unchanged",
        )

def sync_then_publish_arm() -> None:
    """#418 PART 2, the ACCEPTANCE fixture (i): a tree BEHIND the remote SYNCS (fetch +
    fast-forward) and, on top of the fresh tip, publishes its OWN commit.

    The shared tree the cron pusher runs from is a PURE ANCESTOR of `origin/main` most of the
    time (lanes publish from their own worktrees), so before this change it read a stale
    cache forever. Two legs, the change and its control:
      - WITH the sync: the behind tree fast-forwards to the tip, and a commit made on the
        fresh tip publishes normally.
      - WITHOUT it (a report-only round does not sync): the same tree stays behind, so the
        commit it then makes sits ahead AND behind -- a genuine divergence -- and the round
        publishes NOTHING. That contrast is what makes the first leg a finding rather than a
        tautology.
    """
    for label, sync_first in (("with the sync", True), ("committing while behind (no sync)", False)):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = init_bare(root / "remote.git")
            seed = init_work(root / "seed", remote)
            commit(seed, "a.txt")
            git(seed, "push", "-q", "origin", "main:main")
            base = head_of(seed)

            tree = configured_clone(root, remote, "tree")

            # A LANE advances `origin/main` past the shared tree, as the worktree law says it
            # does -- so the tree is now a PURE ANCESTOR (behind, nothing of its own).
            lane = configured_clone(root, remote, "lane")
            write_commit(lane, "b.txt", "b\n")
            git(lane, "push", "-q", "origin", "main:main")
            tip = git(remote, "rev-parse", "refs/heads/main")

            # The shared repository's checkouts SHARE one object store (the lane worktrees
            # are worktrees of it), so the remote tip object is present locally even while
            # HEAD sits behind it. A fetch supplies it in the fixture; it is not the sync --
            # the sync is the fast-forward, and it is what the two legs below differ on.
            git(tree, "fetch", "-q", "origin")

            if sync_first:
                first = pub.publish(tree, remote="origin", branch="main", grace_secs=0, apply=True)
                synced_to_tip = head_of(tree) == tip
                check(
                    first["status"] == "in-sync"
                    and sync_of(first).get("ok")
                    and sync_of(first).get("before") == base
                    and sync_of(first).get("after") == tip
                    and synced_to_tip,
                    f"[{label}] a BEHIND tree fast-forwards to the remote tip",
                    f"status={first['status']} sync={sync_of(first)}",
                )

            # The tree commits its OWN work -- the ledger rows a shared tree carries.
            mine = write_commit(tree, "c.txt", "c\n")

            second = pub.publish(tree, remote="origin", branch="main", grace_secs=0, apply=True)
            tip_after = git(remote, "rev-parse", "refs/heads/main")
            if sync_first:
                check(
                    second["status"] == "published" and tip_after == mine,
                    f"[{label}] the tree's own commit, on the fresh tip, PUBLISHES",
                    f"status={second['status']} remote tip {'== HEAD' if tip_after == mine else '!= HEAD'}",
                )
            else:
                check(
                    second["status"] == "diverged" and tip_after == tip,
                    f"[{label}] a tree that commits BEFORE syncing is ahead AND behind, so it publishes NOTHING",
                    f"status={second['status']} remote tip {'moved' if tip_after != tip else 'unchanged'}",
                )

def sync_blocked_by_a_dirty_tree_arm() -> None:
    """#418 PART 2, the n=2936 CONSTRAINT: the pusher runs from the SHARED tree, a READ
    surface that carries other lanes' uncommitted edits. `merge --ff-only` REFUSES when the
    incoming commits touch a locally-modified path, and the pusher must NOT clobber a peer's
    in-flight work: it REPORTS the blocking paths and the read instant, and publishes nothing.

    The control clears the local edit and re-runs: the SAME history then fast-forwards
    cleanly, so the block was the WORKING TREE, not the history -- which is exactly what
    separates a blocked fast-forward from a genuine divergence.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote = init_bare(root / "remote.git")
        seed = init_work(root / "seed", remote)
        write_commit(seed, "x.txt", "base\n")
        git(seed, "push", "-q", "origin", "main:main")

        tree = configured_clone(root, remote, "tree")
        lane = configured_clone(root, remote, "lane")
        write_commit(lane, "x.txt", "lane advance\n")
        git(lane, "push", "-q", "origin", "main:main")
        tip = git(remote, "rev-parse", "refs/heads/main")

        # A peer's in-flight edit, UNCOMMITTED, on a path the incoming commit touches.
        (tree / "x.txt").write_text("peer in-flight edit\n", encoding="utf-8")

        report = pub.publish(tree, remote="origin", branch="main", grace_secs=0, apply=True)
        tip_after = git(remote, "rev-parse", "refs/heads/main")
        kept = (tree / "x.txt").read_text(encoding="utf-8") == "peer in-flight edit\n"

        check(
            report["status"] == "ff-blocked",
            "a dirty tree that blocks the fast-forward reports ff-blocked, not diverged",
            f"status={report['status']} reason={report['reason'][:140]}",
        )
        check(
            sync_of(report).get("blocking") == ["x.txt"],
            "the round NAMES the blocking path(s)",
            f"blocking={sync_of(report).get('blocking')}",
        )
        check(
            bool(report["read_at"]) and report["read_at"] in report["reason"],
            "the round carries the READ INSTANT it observed the block at",
            f"read_at={report['read_at']}",
        )
        check(
            tip_after == tip and kept,
            "the block publishes nothing AND does not clobber the peer's edit",
            f"remote={'moved' if tip_after != tip else 'unchanged'} peer edit {'kept' if kept else 'OVERWRITTEN'}",
        )

        # THE CONTROL: clear the peer's edit; the SAME history now fast-forwards cleanly.
        git(tree, "checkout", "-q", "--", "x.txt")
        again = pub.publish(tree, remote="origin", branch="main", grace_secs=0, apply=True)
        check(
            again["status"] == "in-sync" and head_of(tree) == tip,
            "clearing the local edit lets the SAME history fast-forward -- the block was the tree, not the history",
            f"status={again['status']} HEAD={'== tip' if head_of(tree) == tip else '!= tip'}",
        )

def remote_tip_is_read_from_the_remote_arm() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote = init_bare(root / "remote.git")
        seed = init_work(root / "seed", remote)
        commit(seed, "a.txt")
        git(seed, "push", "-q", "origin", "main:main")

        mine = root / "mine"
        git(root, "clone", "-q", str(remote), str(mine))
        git(mine, "config", "user.email", "probe@probe.invalid")
        git(mine, "config", "user.name", "probe")
        stale = git(mine, "rev-parse", "origin/main")

        theirs = root / "theirs"
        git(root, "clone", "-q", str(remote), str(theirs))
        git(theirs, "config", "user.email", "probe@probe.invalid")
        git(theirs, "config", "user.name", "probe")
        commit(theirs, "peer.txt")
        git(theirs, "push", "-q", "origin", "main:main")
        moved = git(remote, "rev-parse", "refs/heads/main")

        report = pub.publish(mine, remote="origin", branch="main")

        check(
            moved != stale,
            "the local origin/main ref is genuinely stale at this instant (the arm's precondition)",
            f"local ref={stale[:8]} remote={moved[:8]}",
        )
        check(
            report.get("remote_tip") == moved,
            "the remote tip is read FROM THE REMOTE, not from the stale local ref",
            f"reported={str(report.get('remote_tip'))[:8]} remote={moved[:8]} local={stale[:8]}",
        )


def install_pre_push(repo: Path, body: str) -> None:
    """Put a `pre-push` hook on the WORK repo — the race window, reproduced for real.

    A ref race lives between the moment a round decides to push and the moment the server
    applies its update: the round's own fetch/ff-only cannot see it, because at sync time
    the remote is still where the round left it. `pre-push` runs exactly in that window, so
    a hook that lands a PEER's commit before our update is sent is not a mock of the race —
    it is the race, with real refs and a real server rejection.

    (A `pre-receive` hook cannot do this: git quarantines the incoming objects, so a ref
    update from inside that hook fails with "ref updates forbidden inside quarantine
    environment". Measured, not assumed.)
    """
    hooks = repo / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    path = hooks / "pre-push"
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(0o755)

def rejected_push_arm() -> None:
    """Issue #518, ruling n=3841. A rejection is not a verdict about whether work landed.

    Three arms, because the predicate has three outcomes and a control is only a control if
    it can differ:

      (A) the remote ends up carrying a commit that ADVANCED PAST ours -> `already-published`,
          exit 0, and NO receipt. CONTAINMENT, not equality: an equality test calls this a
          failure, which is the same fabricated verdict wearing the opposite sign.
      (B) the EQUALITY special case, at the predicate: a remote tip that IS our commit.
      (C) the remote genuinely does NOT carry our commit -> `push-failed`, non-zero, with
          the server's own message preserved. Without this arm, "always report success"
          would pass (A) and (B).
    """
    old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=GRACE * 4)

    # (A) CONTAINMENT: a peer advances the branch past our commit while our push is in flight.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote = init_bare(root / "remote.git")
        repo = init_work(root / "r", remote)
        commit(repo, "a.txt")
        git(repo, "push", "-q", "origin", "main:main")
        sha = commit(repo, "b.txt", when=old)

        peer = root / "peer"
        git(root, "clone", "-q", str(remote), str(peer))
        git(peer, "config", "user.email", "peer@probe.invalid")
        git(peer, "config", "user.name", "peer")
        git(peer, "fetch", "-q", str(repo), "main")
        git(peer, "reset", "-q", "--hard", "FETCH_HEAD")
        peer_commit = commit(peer, "peer.txt")  # a CHILD of our commit
        install_pre_push(repo, f'git -C "{peer}" push -q origin main:main\nexit 0\n')

        report = pub.publish(repo, remote="origin", branch="main", grace_secs=GRACE, apply=True)
        tip = git(remote, "rev-parse", "refs/heads/main")
        rc_ancestor = subprocess.run(
            ["git", "-C", str(remote), "merge-base", "--is-ancestor", sha, tip]
        ).returncode
        receipt = repo / ".git" / "publish-receipt.json"

        check(
            rc_ancestor == 0 and tip != sha and tip == peer_commit,
            "the arm's precondition: the remote ADVANCED PAST our commit during our push",
            f"tip={tip[:8]} ours={sha[:8]} peer={peer_commit[:8]} is-ancestor rc={rc_ancestor}",
        )
        check(
            report["status"] == "already-published",
            "a rejected push whose commit the remote CONTAINS reports `already-published` "
            "(containment, not equality)",
            f"status={report['status']} reason={report.get('reason','')[:240]}",
        )
        check(
            report["status"] not in pub.PLAIN_NONZERO
            and report["status"] in pub.TERMINAL_PUBLISHED,
            "`already-published` is terminal-SUCCESS: exit 0 and nothing left to wait for",
            f"in PLAIN_NONZERO={report['status'] in pub.PLAIN_NONZERO} "
            f"in TERMINAL_PUBLISHED={report['status'] in pub.TERMINAL_PUBLISHED}",
        )
        check(
            not receipt.exists(),
            "`already-published` writes NO receipt — this round pushed nothing",
            f"{receipt} exists; a receipt here forges provenance for a peer's push",
        )
        check(
            bool(str(report.get("reason", "")).strip()),
            "the server's rejection message is PRESERVED on the success status",
            "the reason must still say what the server said, so the race stays visible",
        )

    # (B) THE EQUALITY SPECIAL CASE, at the predicate: tip == sha.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote = init_bare(root / "remote.git")
        repo = init_work(root / "r", remote)
        commit(repo, "a.txt")
        git(repo, "push", "-q", "origin", "main:main")
        same = git(repo, "rev-parse", "HEAD")
        unpushed = commit(repo, "b.txt", when=old)

        carries, tip, why = pub.remote_carries(repo, "origin", "main", same)
        check(
            carries is True and tip == same and why == "",
            "the predicate reads a remote tip that IS our commit as CARRIED (the equality case)",
            f"carries={carries} tip={str(tip)[:8]} ours={same[:8]} why={why}",
        )
        carries, tip, why = pub.remote_carries(repo, "origin", "main", unpushed)
        check(
            carries is False and tip == same and why != "",
            "the predicate reads a commit the remote does NOT carry as NOT carried, and says why",
            f"carries={carries} tip={str(tip)[:8]} ours={unpushed[:8]} why={why}",
        )

    # (C) THE CONTROL: the remote genuinely does not carry our commit.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote = init_bare(root / "remote.git")
        repo = init_work(root / "r", remote)
        base = commit(repo, "a.txt")
        git(repo, "push", "-q", "origin", "main:main")
        sha = commit(repo, "b.txt", when=old)

        peer = root / "peer"
        git(root, "clone", "-q", str(remote), str(peer))
        git(peer, "config", "user.email", "peer@probe.invalid")
        git(peer, "config", "user.name", "peer")
        peer_commit = commit(peer, "divergent.txt")  # a SIBLING of our commit, off `base`
        install_pre_push(repo, f'git -C "{peer}" push -q origin main:main\nexit 0\n')

        report = pub.publish(repo, remote="origin", branch="main", grace_secs=GRACE, apply=True)
        tip = git(remote, "rev-parse", "refs/heads/main")
        rc_ancestor = subprocess.run(
            ["git", "-C", str(remote), "merge-base", "--is-ancestor", sha, tip]
        ).returncode

        check(
            tip != sha and rc_ancestor != 0 and tip == peer_commit,
            "the control's precondition: the remote does NOT carry our commit",
            f"tip={tip[:8]} ours={sha[:8]} is-ancestor rc={rc_ancestor}",
        )
        check(
            report["status"] == "push-failed",
            "a rejected push whose commit the remote does NOT carry still reports `push-failed`",
            f"status={report['status']} reason={report.get('reason','')[:240]}",
        )
        check(
            report["status"] in pub.PLAIN_NONZERO,
            "`push-failed` remains a failure the plain path exits non-zero on",
            f"status={report['status']}",
        )
        check(
            "non-fast-forward" in str(report.get("reason", "")).lower()
            or "rejected" in str(report.get("reason", "")).lower(),
            "the genuine failure quotes the server's own message",
            f"reason={report.get('reason','')[:240]}",
        )

class SteppingClock:
    """A clock that ADVANCES on every read, so a grace window costs no real seconds.

    `publish()` takes its instant through this and `wait_for_publish` reads it again for its
    own budget, so one call per poll walks a commit past any window. The same injection the
    round's own `now` parameter exists for, lifted to the waiting layer.
    """

    def __init__(self, start: dt.datetime | None = None, step_secs: float = 1.0):
        self.now = start or dt.datetime.now(dt.timezone.utc)
        self.step = dt.timedelta(seconds=step_secs)

    def __call__(self) -> dt.datetime:
        self.now = self.now + self.step
        return self.now

def wait_publishes_arm() -> None:
    """#482: `--wait` BLOCKS until the round can publish, and the poll lines show it.

    Driven by an injected clock: the window it waits through is 30 seconds of budget and
    ZERO seconds of wall clock, which is the only way a gate can assert on a 900-second
    window's behaviour.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote = init_bare(root / "remote.git")
        work = init_work(root / "work", remote)
        commit(work, "seed.txt")
        git(work, "push", "-q", "origin", "main:main")
        commit(work, "publish-me.txt")
        clock = SteppingClock()
        lines: list[str] = []
        report = pub.wait_for_publish(
            work, grace_secs=30, timeout=600, poll_secs=0,
            now_fn=clock, emit=lines.append, sleep_fn=lambda _s: None,
        )
        check(
            report["status"] == "published",
            "a --wait round publishes once the grace window passes",
            f"status={report['status']} polls={report.get('polls')}",
        )
        check(
            len(lines) >= 2 and lines[0].startswith("status=held")
            and lines[-1].startswith("status=published"),
            "the poll lines record the held -> published transition, one per poll",
            " | ".join(lines[:2] + lines[-1:]),
        )
        check(
            report["polls"] == len(lines),
            "every poll emitted exactly ONE machine-readable line",
            f"polls={report['polls']} lines={len(lines)}",
        )
        check(ahead(work) == 0, "the waited-for commit is ON the remote afterwards")

def wait_stops_on_a_terminal_status_arm() -> None:
    """#482: only `held` can become publishable by waiting.

    A terminal status must STOP the wait rather than poll to its own timeout, because
    polling to a timeout reports a window that expired instead of a state that was never
    going to change -- and the caller's budget is spent either way.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "r"
        repo.mkdir(parents=True, exist_ok=True)
        git(repo, "init", "-q")
        git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
        clock = SteppingClock()
        lines: list[str] = []
        report = pub.wait_for_publish(
            repo, timeout=600, poll_secs=0,
            now_fn=clock, emit=lines.append, sleep_fn=lambda _s: None,
        )
        check(
            report["status"] == "no-remote" and len(lines) == 1,
            "a terminal status stops the wait after ONE poll, not at the timeout",
            f"status={report['status']} polls={report.get('polls')} lines={len(lines)}",
        )

def wait_timeout_arm() -> None:
    """#482: a wait that cannot clear its own timeout REPORTS that, never a publish."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote = init_bare(root / "remote.git")
        work = init_work(root / "work", remote)
        commit(work, "seed.txt")
        git(work, "push", "-q", "origin", "main:main")
        commit(work, "always-held.txt")
        clock = SteppingClock()
        lines: list[str] = []
        report = pub.wait_for_publish(
            work, grace_secs=10 ** 6, timeout=5, poll_secs=0,
            now_fn=clock, emit=lines.append, sleep_fn=lambda _s: None,
        )
        check(
            report["status"] == "held" and report.get("wait_timed_out") is True,
            "a wait that hits its timeout reports the TIMEOUT, not a publish",
            f"status={report['status']} timed_out={report.get('wait_timed_out')}",
        )

def wait_line_fields_arm() -> None:
    """#482: the poll line is a RECORD a caller parses, not prose."""
    report = {
        "status": "held", "remote_tip": "b" * 40,
        "held": [{"sha": "a" * 40, "age_secs": 42, "session_id": "s", "subject": "x"}],
        "reason": "younger\nthan the window",
    }
    line = pub.wait_line(report)
    fields = dict(part.split("=", 1) for part in line.split(" ") if "=" in part)
    check(
        all(k in fields for k in ("status", "held", "age", "tip", "reason")),
        "the poll line carries status, held, age, tip and reason",
        line,
    )
    check(
        fields.get("age") == "42" and fields.get("held") == "1" and "\n" not in line,
        "the poll line carries the AGE and the HELD COUNT on ONE line",
        line,
    )
    empty = pub.wait_line({"status": "in-sync", "held": [], "reason": ""})
    check(
        "tip=-" in empty and "age=None" in empty,
        "an absent tip and age read as '-', never as an empty field",
        empty,
    )

def not_on_branch_exits_nonzero_arm() -> None:
    """#482 order 2: `not-on-branch` exited 0 while being a REFUSAL like the statuses beside
    it in the same tuple, so an rc-only caller could not tell it from a round that ran -- and
    a caller that WAITS loops forever on a state that cannot change.

    The CONTROL beside it is the other half: the fix must narrow the tuple, not the contract,
    so an in-sync round still exits 0.
    """
    with tempfile.TemporaryDirectory() as tmp:
        remote = init_bare(Path(tmp) / "remote.git")
        repo = init_work(Path(tmp) / "r", remote)
        commit(repo, "a.txt")
        git(repo, "push", "-q", "origin", "main:main")
        git(repo, "checkout", "-q", "-b", "side")
        report = pub.publish(repo, remote="origin", branch="main")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = pub.main(["--repo", str(repo)])
        check(
            report["status"] == "not-on-branch" and rc != 0,
            "the not-on-branch round exits NON-ZERO, so an rc-only caller cannot loop",
            f"status={report['status']} rc={rc}",
        )
        git(repo, "checkout", "-q", "main")
        buf2 = io.StringIO()
        with contextlib.redirect_stdout(buf2):
            rc_sync = pub.main(["--repo", str(repo)])
        check(
            rc_sync == 0,
            "CONTROL: an in-sync round still exits 0 -- the tuple narrowed, not the contract",
            f"rc={rc_sync}",
        )

def wait_cli_publishes_arm() -> None:
    """#482 (a): the CALLER's path. A cron shell runs `main()`, not `wait_for_publish()`, so
    the exit code and the poll record are asserted at the CLI boundary with `--grace-secs 0`,
    which publishes on the first poll and therefore needs no injected clock."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote = init_bare(root / "remote.git")
        work = init_work(root / "work", remote)
        commit(work, "seed.txt")
        git(work, "push", "-q", "origin", "main:main")
        commit(work, "publish-me.txt")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = pub.main(
                ["--repo", str(work), "--wait", "--grace-secs", "0", "--timeout", "30"]
            )
        out = buf.getvalue()
        check(
            rc == 0 and "status=published" in out,
            "--wait through the CLI exits 0 and prints a published poll line",
            f"rc={rc} first={out.splitlines()[0] if out else ''}",
        )
        check(ahead(work) == 0, "the CLI waited-for commit is ON the remote")

def wait_cli_refuses_arm() -> None:
    """#482 (b): the CLI against a state that cannot publish. Non-zero AND the status is
    PRINTED, because a caller that only learns "failed" cannot say what failed."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "r"
        repo.mkdir(parents=True, exist_ok=True)
        git(repo, "init", "-q")
        git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = pub.main(["--repo", str(repo), "--wait", "--timeout", "30"])
        out = buf.getvalue()
        check(
            rc != 0 and "status=no-remote" in out,
            "--wait through the CLI exits NON-ZERO and names the status it refused on",
            f"rc={rc} first={out.splitlines()[0] if out else ''}",
        )

def load_module(path: Path, name: str):
    """Import a tool by PATH -- never by name, so a temp COPY (or a mutated one) is loaded."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

def _isolated_copy(root: Path, mutate: bool = False) -> Path:
    """A copy of the pusher OUTSIDE any git work tree -- the shape a `/tmp` fetch has.

    `REPO` is derived from `__file__`, so a copy at `<root>/isolated/publish_copy.py` derives
    `<root>`: a real directory, and not a work tree. That is exactly the defect's shape, and it
    is built rather than described.

    `mutate=True` restores the PRE-#525 shape in the copy: the derived tree as the default and
    no startup guard. The control arm below asserts the refusal disappears there, so the arm
    above is proven to be reading the guard rather than the copy's mere existence.
    """
    src = TOOL.read_text(encoding="utf-8")
    if mutate:
        # THE ANCHOR CARRIES `"--repo",` ON ITS OWN LINE. A bare `default=None,` matches EVERY
        # flag in `main()` -- `--timeout`'s among them -- and argparse applies `type=int` to a
        # string default, so the mutant died in the PARSER (`invalid int value`) rather than in
        # the guard under test. A mutation that breaks a different flag is not a control.
        src = src.replace(
            '        "--repo",\n        default=None,\n',
            '        "--repo",\n        default=str(REPO),\n',
        )
        start = src.index("    if args.repo is None and not repo_is_work_tree(REPO):")
        end = src.index("    repo = Path(args.repo) if args.repo else REPO\n", start)
        src = src[:start] + src[end:]
        assert '        "--repo",\n        default=str(REPO),\n' in src, (
            "the mutation did not restore the old --repo default"
        )
        assert "if args.repo is None and not repo_is_work_tree(REPO)" not in src, (
            "the mutation did not remove the startup guard -- the control would test nothing"
        )
    path = root / "isolated" / "publish_copy.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(src, encoding="utf-8")
    return path

def unbound_repo_arm() -> None:
    """#525 item 1 (ruling n=3895): the tool REFUSES to guess its repository.

    The measured instance: a fetched copy at `/tmp/<name>.py` run with no `--repo` reported
    `status=no-remote`, `repo: "/"`, rc=1 -- a terminal verdict about a repository nobody chose,
    on a clean tree with one unpushed commit. The ruled shape stops AT STARTUP with a status that
    names the flag, and never emits `no-remote` about the assumption.

    The control inside the arm: the SAME copy, handed `--repo`, runs an ordinary round. Without
    it a refusal could be the copy being unusable rather than the flag being absent.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        copy = _isolated_copy(root)
        mod = load_module(copy, "_pub_unbound")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = mod.main(["--json"])
        out = buf.getvalue()
        data = json.loads(out)
        check(
            data["status"] == "unbound-repo",
            "no --repo outside a work tree STOPS at startup with the distinct status "
            "`unbound-repo`",
            f"status={data['status']!r} reason={data.get('reason','')[:160]}",
        )
        check(
            rc == 1,
            "and the refusal exits NON-ZERO -- a round that read nothing is not a round",
            f"rc={rc}",
        )
        check(
            "--repo" in data.get("reason", "") and "REQUIRED" in data.get("reason", ""),
            "and the reason NAMES the flag the caller must pass",
            data.get("reason", "")[:200],
        )
        check(
            data["status"] != "no-remote",
            "and it is NOT a `no-remote` verdict -- nothing was asked of any remote",
            data["status"],
        )

        remote = init_bare(root / "remote.git")
        work = init_work(root / "work", remote)
        commit(work, "seed.txt")
        # The remote must CARRY a `main` before a round can compare against it: an empty bare
        # repo answers `unreachable`, which would make this control read as a refusal for a
        # reason of its own. Seed, then leave ONE unpushed commit -- the report-only answer.
        git(work, "push", "-q", "origin", "main:main")
        commit(work, "mine.txt")
        buf = io.StringIO()
        # `--grace-secs 0` because a fresh commit is inside the window: without it the round
        # answers `held` -- the window working -- and the control would read a refusal where an
        # ordinary round ran.
        with contextlib.redirect_stdout(buf):
            rc = mod.main(["--repo", str(work), "--grace-secs", "0", "--json"])
        data = json.loads(buf.getvalue())
        check(
            rc == 0 and data["status"] == "would-publish",
            "CONTROL: the SAME copy handed `--repo` runs an ordinary round -- so the refusal "
            "above is the ABSENT FLAG, not a copy that cannot run at all",
            f"rc={rc} status={data['status']!r}",
        )

def unbound_repo_control_bites() -> None:
    """The mutation control for the arm above: restore the old default and it must FAIL.

    Pre-#525 the flag defaulted to `str(REPO)` and no startup guard existed, so the copy at
    `/tmp` went on to probe the derived tree for an `origin` and answered `no-remote`. If that
    shape still produced `unbound-repo`, the arm above would be reading something other than
    the guard.
    """
    with tempfile.TemporaryDirectory() as tmp:
        copy = _isolated_copy(Path(tmp), mutate=True)
        mod = load_module(copy, "_pub_unbound_mut")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            mod.main(["--json"])
        data = json.loads(buf.getvalue())
        check(
            data["status"] == "no-remote",
            "CONTROL: with the pre-#525 default restored the refusal DISAPPEARS and the round "
            "reports `no-remote` about the derived tree -- so the arm is testing the guard",
            f"status={data['status']!r} reason={data.get('reason','')[:160]}",
        )

def documented_statuses_arm() -> None:
    """#482 (order 4): the status table has a HOME, and that home is GATED.

    A doc stating a contract nothing checks drifts the moment a thirteenth status ships. This
    arm reads the DECLARATION (`ALL_STATUSES`) and the doc, and fails on either direction:
    a status in the code and absent from the doc, or a status the doc names that no round can
    return. It reads the doc through the byte-gated pair, so the two copies cannot disagree.
    """
    doc = (ROOT / "docs" / "instruments" / "publish.md").read_text(encoding="utf-8")
    undeclared = [s for s in pub.ALL_STATUSES if f"`{s}`" not in doc]
    check(
        not undeclared,
        "every status the pusher can return is DOCUMENTED in docs/instruments/publish.md",
        f"undocumented: {undeclared}",
    )
    extra = [
        s for s in re.findall(r"^\| `([a-z-]+)` \|", doc, re.M)
        if s not in pub.ALL_STATUSES
    ]
    check(
        not extra,
        "the documented table names NO status the pusher cannot return",
        f"extra: {extra}",
    )
    check(
        set(pub.PLAIN_NONZERO) <= set(pub.ALL_STATUSES)
        and set(pub.TERMINAL_PUBLISHED) <= set(pub.ALL_STATUSES)
        and set(pub.WAITABLE) <= set(pub.ALL_STATUSES),
        "the partitioned sets are SUBSETS of the declared status set",
        f"nonzero={len(pub.PLAIN_NONZERO)} published={len(pub.TERMINAL_PUBLISHED)} "
        f"waitable={len(pub.WAITABLE)} all={len(pub.ALL_STATUSES)}",
    )
    # FOURTEEN since #525 (ruling n=3895) added the STARTUP refusal `unbound-repo`. The count is
    # stated here rather than derived so that ADDING a status is a deliberate act with a doc row
    # and a law line, never a side effect of a branch somebody added.
    check(
        len(pub.ALL_STATUSES) == 14 and len(set(pub.ALL_STATUSES)) == 14,
        "the status set is FOURTEEN distinct statuses, as the law states",
        f"count={len(pub.ALL_STATUSES)} distinct={len(set(pub.ALL_STATUSES))}",
    )
    twinned = (ROOT / "TEMPLATE" / "docs" / "instruments" / "publish.md").read_bytes()
    check(
        twinned == doc.encode("utf-8"),
        "the doc's TEMPLATE twin is byte-identical, so the table cannot be true in one tree only",
    )

def report_arms() -> None:
    report = {
        "status": "held", "remote": "origin", "branch": "main",
        "read_at": "2026-09-26T12:00:00Z", "grace_secs": GRACE,
        "count": 1, "shas": ["a" * 40], "remote_tip": "b" * 40,
        "held": [{"sha": "a" * 40, "age_secs": 12, "session_id": "s", "subject": "x"}],
        "diverged": None, "reason": "younger than the window",
    }
    text = pub.render(report)
    check(
        "a" * 40 in text and "1 commit" in text,
        "the round prints its COUNT and its SHAS, never a boolean",
        text.splitlines()[0],
    )
    empty = dict(report, status="in-sync", count=0, shas=[], held=[], remote_tip=None)
    check("in-sync" in pub.render(empty), "an in-sync round renders as in-sync")


def repo_root_is_copy_independent_arm() -> None:
    """The gate must resolve the SAME repo root from either copy.

    A path built from the copy root works in one tree and doubles in the
    other: this arm ran green in tests/ and red in TEMPLATE/tests/ with
    <repo>/TEMPLATE/TEMPLATE/docs/..., which the slow shipped audit caught
    and this one catches locally.
    """
    root = _repo_root(HERE)
    check(
        (root / "tools" / "publish.py").is_file(),
        "the detected root holds the tool",
        f"root={root} tool={root / 'tools' / 'publish.py'}",
    )
    check(
        (root / "TEMPLATE" / "tools" / "publish.py").is_file(),
        "the detected root holds the TEMPLATE twin of the tool",
        f"root={root}",
    )
    for rel in ("docs/instruments/publish.md", "TEMPLATE/docs/instruments/publish.md"):
        p = root / rel
        check(
            p.is_file(),
            f"the doc path resolves from this copy: {rel}",
            f"missing {p}",
        )
    check(
        not (root / "TEMPLATE" / "TEMPLATE").exists(),
        "the root is not a copy root (no doubled TEMPLATE)",
        f"root={root}",
    )


def main() -> int:
    pure_arms()
    source_arms()
    no_remote_arm()
    unreachable_arm()
    not_on_branch_arm()
    detached_head_publishes_arm()
    detached_off_branch_refuses_arm()
    detached_behind_arm()
    in_sync_arm()
    grace_holds_arm()
    old_commit_publishes_arm()
    receipt_arm()
    receipt_is_shared_across_worktrees_arm()
    legacy_receipt_orphan_arm()
    dry_run_arm()
    divergence_arm()
    behind_is_not_diverged_arm()
    sync_then_publish_arm()
    sync_blocked_by_a_dirty_tree_arm()
    remote_tip_is_read_from_the_remote_arm()
    rejected_push_arm()
    wait_publishes_arm()
    wait_stops_on_a_terminal_status_arm()
    wait_timeout_arm()
    wait_line_fields_arm()
    wait_cli_publishes_arm()
    wait_cli_refuses_arm()
    not_on_branch_exits_nonzero_arm()
    repo_root_is_copy_independent_arm()
    unbound_repo_arm()
    unbound_repo_control_bites()
    documented_statuses_arm()
    report_arms()

    failures = [c for c in checks if not c[0]]
    print(f"publish gate: {len(checks)} check(s), {len(failures)} failed")
    for ok, name, detail in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        if detail and not ok:
            print(f"        {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
