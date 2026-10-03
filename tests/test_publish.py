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
import datetime as dt
import io
import os
import subprocess
import sys
import tempfile
import tokenize
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
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
        path = repo / "evidence" / "publish-receipt.json"

        check(
            report["status"] == "published" and rec.get("sha") == sha,
            "a published round records the sha it pushed",
            f"status={report['status']} receipt={rec}",
        )
        check(
            path.is_file(), "the receipt is written under evidence/",
            f"receipt={rec} exists={path.is_file()}",
        )
        body = pub.read_receipt(repo)[0] if path.is_file() else None
        check(
            isinstance(body, dict) and body.get("sha") == sha and body.get("instant"),
            "the receipt carries the sha AND the instant of the push",
            f"body={body}",
        )
        check(
            rec.get("path") == "evidence/publish-receipt.json"
            and not (repo / "evidence" / "ledger.jsonl").exists(),
            "the receipt is a FILE under evidence/, never a ledger row",
            f"receipt={rec}",
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
        check(
            report["status"] == "would-publish"
            and not (repo / "evidence" / "publish-receipt.json").exists(),
            "a round that pushed nothing records NO receipt (the control)",
            f"status={report['status']}",
        )

        # An absent receipt is neither an error nor a mismatch: the leg reads it as
        # "no baseline", never as a clean one.
        absent, why = pub.read_receipt(repo)
        check(
            absent is None and bool(why),
            "an absent receipt is reported as absent, never as a clean read",
            f"receipt={absent} why={why!r}",
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


def main() -> int:
    pure_arms()
    source_arms()
    no_remote_arm()
    unreachable_arm()
    not_on_branch_arm()
    in_sync_arm()
    grace_holds_arm()
    old_commit_publishes_arm()
    receipt_arm()
    dry_run_arm()
    divergence_arm()
    remote_tip_is_read_from_the_remote_arm()
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
