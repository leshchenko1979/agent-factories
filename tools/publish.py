#!/usr/bin/env python3
"""Publish this repository's own commits: fast-forward only, after a grace window.

Origin (issue #146, ruled at ledger n=1168). Nothing guaranteed that a commit
reached `origin`. Publication happened only when some lane happened to run a push
as its own last step, so a turn killed after committing but before pushing left
work that no surface could see and nothing would re-publish. Four instances were
measured in one day, one of them a commit a RULING cited while it was unreachable
from any branch — which is what makes this a defect rather than housekeeping.

Three bounds, each from the ruling, each load-bearing:

- **A GRACE WINDOW.** A pusher without one manufactures the published-then-amended
  divergence this factory already paid for once (commit fc8e33f9, corrected by
  append at fad3a720): a commit pushed mid-edit and then amended has rewritten
  PUBLISHED history. So a commit younger than the window stays LOCAL, and the
  window is tested on the NEWEST unpushed commit — a fast-forward push publishes
  everything up to the tip, so testing the oldest would publish a younger commit
  sitting above it.
- **FAST-FORWARD ONLY; DIVERGENCE REPORTED, NEVER RESOLVED.** When the remote tip
  is not an ancestor of ours this prints the divergence and stops. It does not
  fetch, merge, reconcile or rewrite.
- **NO FORCED PUSH AND NO HISTORY REWRITE.** The bound is written here because it
  belongs written down, and it appears in NO executable line: the gate strips the
  docstring and the comments and asserts both tokens are absent from what remains.
  A pusher that can rewrite history is a worse defect than the gap it closes.

READ THE REMOTE, NEVER THE LOCAL REF
------------------------------------
`origin/main` is a CACHE, updated only by a fetch, so a pusher reading it reports
what the last fetch saw — exactly the fact in doubt. The remote tip therefore comes
from `ls-remote`, and an unreachable remote is REPORTED as unreachable rather than
silently replaced by the local ref, which would turn "I could not ask" into "in sync".

REPORTING IS NOT A BOOLEAN
--------------------------
Every round prints its count and its shas. A count can be re-checked and a sha can
be dispatched, claimed or closed; a boolean can be none of those.

Run:  python3 tools/publish.py            report only, nothing is pushed
      python3 tools/publish.py --apply    push when the grace window allows
Exit: 0 the round ran (published, held, in sync, or reported a divergence)
      1 the round could not be completed (no remote, unreachable, unreadable)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_REMOTE = "origin"
DEFAULT_BRANCH = "main"
DEFAULT_GRACE_SECS = 900
LS_REMOTE_TIMEOUT = 30
GIT_TIMEOUT = 120

_FIELD = "\x1f"
_RECORD = "\x1e"
_LOG_FORMAT = (
    f"%H{_FIELD}%cI{_FIELD}%(trailers:key=Session-Id,valueonly){_FIELD}%s{_RECORD}"
)


def _git(repo: Path, *args: str, timeout: int = GIT_TIMEOUT):
    """`(rc, stdout, stderr)` — a failed invocation is REPORTED, never raised.

    A pusher runs from a clock, with no lane watching it. An exception would end
    the round with no record of what it had read, which is the same silence the
    item exists to remove.
    """
    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(repo), capture_output=True, text=True, timeout=timeout
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"git {' '.join(args)} timed out after {timeout}s"
    except OSError as exc:
        return 127, "", f"git could not be run: {exc}"


def parse_ts(value: str):
    """An ISO-8601 instant, or None when it does not parse."""
    try:
        when = dt.datetime.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    return when


def age_secs(value: str, now: dt.datetime):
    """Seconds since `value`, or None when it does not parse."""
    when = parse_ts(value)
    return None if when is None else (now - when).total_seconds()


def remote_tip(repo: Path, remote: str, branch: str, *, timeout: int = LS_REMOTE_TIMEOUT):
    """`(sha, reason)` — the tip read FROM THE REMOTE, never from the local ref."""
    rc, out, err = _git(
        repo, "ls-remote", "--heads", remote, f"refs/heads/{branch}", timeout=timeout
    )
    if rc != 0:
        return None, (err or out).strip() or f"git ls-remote exited {rc}"
    lines = [line for line in out.splitlines() if line.strip()]
    if not lines:
        return None, f"{remote} carries no refs/heads/{branch}"
    return lines[0].split()[0], ""


def unpushed_commits(repo: Path, remote_sha: str):
    """`(commits, reason)`, NEWEST FIRST. Each carries its lane trailer when it has one."""
    rc, out, err = _git(repo, "log", f"--format={_LOG_FORMAT}", f"{remote_sha}..HEAD")
    if rc != 0:
        return None, (err or out).strip() or f"git log exited {rc}"
    commits = []
    for record in out.split(_RECORD):
        record = record.strip()
        if not record:
            continue
        parts = record.split(_FIELD)
        if len(parts) < 4:
            continue
        commits.append(
            {
                "sha": parts[0].strip(),
                "committed_at": parts[1].strip(),
                "session_id": parts[2].strip(),
                "subject": parts[3].strip(),
            }
        )
    return commits, ""


def publishable(unpushed: list[dict], *, grace_secs: int, now: dt.datetime):
    """`(to_publish, held)` — the grace window, tested on the NEWEST commit.

    An unreadable timestamp is HELD, never published: an age that does not parse is
    not evidence of an old commit, and the failure that would follow is published
    history rather than a late push.
    """
    if not unpushed:
        return [], []
    age = age_secs(unpushed[0].get("committed_at") or "", now)
    if age is None or age < grace_secs:
        return [], list(unpushed)
    return list(unpushed), []


def publish(
    repo: Path = REPO,
    *,
    remote: str = DEFAULT_REMOTE,
    branch: str = DEFAULT_BRANCH,
    grace_secs: int = DEFAULT_GRACE_SECS,
    apply: bool = False,
    now: dt.datetime | None = None,
) -> dict:
    """One round. Returns a report dict; never raises, never forces, never rewrites."""
    repo = Path(repo)
    now = now or dt.datetime.now(dt.timezone.utc)
    report = {
        "repo": str(repo),
        "remote": remote,
        "branch": branch,
        "grace_secs": grace_secs,
        "read_at": now.isoformat().replace("+00:00", "Z"),
        "status": "",
        "reason": "",
        "count": 0,
        "shas": [],
        "held": [],
        "diverged": None,
    }

    rc, _, _ = _git(repo, "remote", "get-url", remote)
    if rc != 0:
        report["status"] = "no-remote"
        report["reason"] = f"{remote} is not configured in this repository"
        return report

    rc, out, _ = _git(repo, "symbolic-ref", "--short", "HEAD")
    current = out.strip() if rc == 0 else ""
    if current != branch:
        report["status"] = "not-on-branch"
        report["reason"] = (
            f"HEAD is on {current or 'a detached head'}, not {branch} — a pusher that "
            f"published another branch would publish work this branch never contained"
        )
        return report

    tip, why = remote_tip(repo, remote, branch)
    if tip is None:
        report["status"] = "unreachable"
        report["reason"] = why
        return report
    report["remote_tip"] = tip

    rc, _, _ = _git(repo, "merge-base", "--is-ancestor", tip, "HEAD")
    if rc != 0:
        rc2, ahead, _ = _git(repo, "rev-list", "--count", f"HEAD..{tip}")
        behind = ahead.strip() if rc2 == 0 else "an unreadable number of"
        report["status"] = "diverged"
        report["diverged"] = {"remote_tip": tip, "remote_ahead_by": behind}
        report["reason"] = (
            f"{remote}/{branch} is not an ancestor of HEAD — the branch has DIVERGED and "
            f"is {behind} commit(s) behind. Reported, not resolved: this pusher does not "
            f"fetch, merge, reconcile or rewrite."
        )
        return report

    commits, why = unpushed_commits(repo, tip)
    if commits is None:
        report["status"] = "unreadable"
        report["reason"] = why
        return report
    report["count"] = len(commits)
    report["shas"] = [c["sha"] for c in commits]
    if not commits:
        report["status"] = "in-sync"
        return report

    to_publish, held = publishable(commits, grace_secs=grace_secs, now=now)
    report["held"] = [
        {
            "sha": c["sha"],
            "age_secs": int(age_secs(c["committed_at"], now) or 0),
            "session_id": c["session_id"],
            "subject": c["subject"],
        }
        for c in held
    ]
    if not to_publish:
        report["status"] = "held"
        report["reason"] = (
            f"the newest unpushed commit is younger than the {grace_secs}s window "
            f"({int(age_secs(commits[0]['committed_at'], now) or 0)}s) — it stays LOCAL"
        )
        return report

    if not apply:
        report["status"] = "would-publish"
        return report

    rc, out, err = _git(repo, "push", remote, f"{branch}:{branch}")
    if rc != 0:
        report["status"] = "push-failed"
        report["reason"] = (err or out).strip()
        return report
    report["status"] = "published"
    return report


def render(report: dict) -> str:
    """The round's record. Count and shas, never a boolean."""
    lines = [
        f"publish: {report['status']} — {report['remote']}/{report['branch']} "
        f"read at {report['read_at']}"
    ]
    if report.get("remote_tip"):
        lines.append(f"  remote tip: {report['remote_tip']}")
    lines.append(
        f"  unpushed: {report['count']} commit(s)"
        + (f" {', '.join(report['shas'])}" if report["shas"] else "")
    )
    if report.get("diverged"):
        lines.append(f"  DIVERGED: {json.dumps(report['diverged'], sort_keys=True)}")
    for held in report.get("held", []):
        lines.append(
            f"  held (within the {report['grace_secs']}s window, age {held['age_secs']}s): "
            f"{held['sha']} {held['session_id'] or 'no lane trailer'} — {held['subject']}"
        )
    if report.get("reason"):
        lines.append(f"  {report['reason']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=str(REPO))
    parser.add_argument("--remote", default=DEFAULT_REMOTE)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--grace-secs", type=int, default=DEFAULT_GRACE_SECS)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="push when the grace window allows; without it the round only reports",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = publish(
        Path(args.repo),
        remote=args.remote,
        branch=args.branch,
        grace_secs=args.grace_secs,
        apply=args.apply,
    )
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else render(report))
    # A round that could not be completed exits non-zero. "Held" and "diverged" are
    # COMPLETED rounds: the first is the window working and the second is the report
    # the ruling asks for, so neither is a failure.
    return 1 if report["status"] in ("no-remote", "unreachable", "unreadable", "push-failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
