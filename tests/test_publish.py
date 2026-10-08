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
        receipt_file = repo / "evidence" / "publish-receipt.json"
        body = pub.read_receipt(repo)[0] if receipt_file.is_file() else None
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
    detached_head_publishes_arm()
    detached_off_branch_refuses_arm()
    detached_behind_arm()
    in_sync_arm()
    grace_holds_arm()
    old_commit_publishes_arm()
    receipt_arm()
    dry_run_arm()
    divergence_arm()
    behind_is_not_diverged_arm()
    sync_then_publish_arm()
    sync_blocked_by_a_dirty_tree_arm()
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
