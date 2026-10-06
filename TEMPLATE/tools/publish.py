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
Exit: 0 the round ran (published, held, in sync, behind, or reported a divergence)
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


# --- the push RECEIPT: a FILE, never a ledger row --------------------------------
#
# The pusher is not a lane. The ledger's actor set is the roles the law names, and a
# clock-driven tool is not one of them -- so the record of its own last push lives in a
# file beside the evidence it protects. It is LOCAL and never committed: a receipt that
# travelled in the pushed history would move the remote tip PAST the sha it records, so
# the record would contradict itself on the very round it was written.
RECEIPT_REL = Path("evidence") / "publish-receipt.json"


def receipt_path(repo: Path) -> Path:
    """Where the pusher records its OWN last push."""
    return Path(repo) / RECEIPT_REL


def write_receipt(repo: Path, *, sha: str, remote: str, branch: str, instant: str):
    """Record the push this round made. `(path, reason)`; a failure is REPORTED.

    Written through a sibling temp file and renamed, so a reader never sees a half-written
    receipt -- the same reason the ledger fsyncs before it releases its lock.
    """
    path = receipt_path(repo)
    body = {"sha": sha, "instant": instant, "remote": remote, "branch": branch}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        return None, f"the receipt could not be written to {RECEIPT_REL}: {exc}"
    return path, ""


def read_receipt(repo: Path):
    """`(receipt, reason)`. An ABSENT receipt is neither an error nor a mismatch.

    A factory that has never pushed has no receipt, and reporting that as a finding would
    red the reader on every fresh clone. The absence is stated; it is not a verdict.
    """
    path = receipt_path(repo)
    if not path.is_file():
        return None, f"no receipt recorded at {RECEIPT_REL}"
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"the receipt at {RECEIPT_REL} could not be read: {exc}"
    if not isinstance(body, dict) or not str(body.get("sha") or "").strip():
        return None, f"the receipt at {RECEIPT_REL} names no sha"
    return body, ""


def commit_info(repo: Path, sha: str):
    """`(info, reason)` for ONE commit -- its instant, its lane trailer and its subject.

    Read through the same log format the unpushed read uses, so a caller comparing a remote
    tip against the local history reads both halves the same way. A tip the local object
    store does not carry -- a push from another clone this one never fetched -- is REPORTED
    as unreadable rather than rendered as an absent commit.
    """
    if not str(sha or "").strip():
        return None, "no sha was given"
    rc, out, err = _git(repo, "log", "-1", f"--format={_LOG_FORMAT}", str(sha))
    if rc != 0:
        return None, (err or out).strip() or f"git log exited {rc}"
    record = out.strip().split(_RECORD)[0]
    parts = record.split(_FIELD)
    if len(parts) < 4:
        return None, f"git log returned an unreadable record for {sha}"
    return {
        "sha": parts[0].strip(),
        "committed_at": parts[1].strip(),
        "session_id": parts[2].strip(),
        "subject": parts[3].strip(),
    }, ""


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


def divergence(repo: Path, tip: str):
    """`{"state", "behind", "ahead"}` — the ONE reading that separates BEHIND from DIVERGED.

    `tip` not being an ancestor of HEAD is true for BOTH a stale checkout and a genuine
    divergence, so ancestry ALONE cannot separate them: the discriminating reading is
    `ahead`, the commits HEAD carries that `tip` does not. `ahead == "0"` means HEAD is a
    PURE ANCESTOR of `tip` -- a stale read copy with nothing of its own, fast-forwardable,
    NOT a conflict. An unreadable `ahead` is treated as DIVERGED: the conservative and loud
    direction, because we could not show HEAD is a pure ancestor and so must not claim it.

    `state` is one of "ahead-or-same" (tip is an ancestor of HEAD: the normal path),
    "behind" (pure ancestor: nothing to publish) or "diverged" (ahead > 0 AND behind > 0).
    The pusher (`publish`) and the patrol's freshness leg BOTH call this, so they cannot
    disagree about what BEHIND means -- the one-predicate rule (#418).
    """
    rc, _, _ = _git(repo, "merge-base", "--is-ancestor", tip, "HEAD")
    if rc == 0:
        return {"state": "ahead-or-same", "behind": "0", "ahead": None}
    rc, behind_out, _ = _git(repo, "rev-list", "--count", f"HEAD..{tip}")
    behind = behind_out.strip() if rc == 0 and behind_out.strip() else "an unreadable number of"
    rc, ahead_out, _ = _git(repo, "rev-list", "--count", f"{tip}..HEAD")
    ahead = ahead_out.strip() if rc == 0 and ahead_out.strip() else "an unreadable number of"
    return {
        "state": "behind" if ahead == "0" else "diverged",
        "behind": behind,
        "ahead": ahead,
    }


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


# --- WHICH BRANCH IS HEAD ON, when HEAD carries no symbolic ref -------------------
#
# The law requires every lane to work in a worktree checked out at `origin/main`
# (SKILL section 4: the shared tree is a READ surface; a change is made in a worktree), so
# a lane's HEAD is DETACHED by construction. A detached HEAD has no `symbolic-ref`, and the
# refusal that read one and gave up refused the ONE state the law puts every lane in, so the
# sanctioned pusher was unusable by the lanes it exists to govern and they pushed directly
# (issue #329, ruled at ledger n=2407). The branch is a FACT to RESOLVE, not a fact the
# pusher may assume:
#
#   * HEAD on a branch -- the symbolic ref names it, and anything but `branch` is refused,
#     as before: a lane standing on `side` publishes `side`, never `main`.
#   * HEAD detached -- it is on `branch`'s line iff `refs/remotes/<remote>/<branch>` and HEAD
#     lie on the SAME line, one containing the other. AHEAD is a lane that committed on top
#     of the base; BEHIND is a stale checkout, and the round's own fast-forward check reports
#     that as BEHIND -- refusing it here would pre-empt that report with a worse reason. A
#     detached HEAD on NEITHER end -- a diverged feature branch, an unrelated commit -- has
#     no claim to `branch` and is refused.
#
# WHAT THIS DOES NOT SEPARATE, stated because a guard with an unstated limit reads as a
# guard without one: a detached HEAD standing on a DIFFERENT branch that is itself a
# descendant of `refs/remotes/<remote>/<branch>` resolves to `branch` too. Ancestry alone
# cannot tell the two apart, and it must not be pressed to: a lane that has already pushed
# its own branch (`git push -u origin worker/<n>-<slug>`) and then publishes to main has
# exactly that shape, so refusing it would rebuild #329. What the push publishes is what the
# lane has CHECKED OUT (`HEAD:<branch>`), never a local ref that may sit elsewhere.
def head_branch(repo: Path, remote: str, branch: str):
    """`(name, reason)` -- the branch HEAD is on, RESOLVED rather than assumed."""
    rc, out, _ = _git(repo, "symbolic-ref", "--short", "HEAD")
    if rc == 0:
        current = out.strip()
        if current == branch:
            return branch, ""
        return current, (
            f"HEAD is on {current}, not {branch} — a pusher that published another "
            f"branch would publish work this branch never contained"
        )

    tracking = f"refs/remotes/{remote}/{branch}"
    rc, out, _ = _git(repo, "rev-parse", "--verify", "--quiet", tracking)
    if rc != 0 or not out.strip():
        return "", (
            f"HEAD is detached and {remote}/{branch} is not a ref this repository carries, "
            f"so the detached HEAD cannot be shown to be on {branch} — fetch {remote} first"
        )
    # SAME LINE, not necessarily AHEAD. HEAD descending from `<remote>/<branch>` and HEAD
    # sitting BEHIND it are both "on `branch`'s line": the second is a stale checkout, and
    # the round's own fast-forward check reports it as BEHIND, which is the status the
    # ruling asks for -- refusing it here would pre-empt that report with a worse reason.
    # What is refused HERE is a detached HEAD on NEITHER end of the line: a feature branch
    # that has diverged from `branch`, or an unrelated commit.
    ahead = _git(repo, "merge-base", "--is-ancestor", tracking, "HEAD")[0] == 0
    behind = _git(repo, "merge-base", "--is-ancestor", "HEAD", tracking)[0] == 0
    if not (ahead or behind):
        return "", (
            f"HEAD is detached and {remote}/{branch} is on neither end of its history — "
            f"the checked-out commit is not on {branch}'s line, so publishing it to "
            f"{branch} would put work on {branch} that {branch} never contained"
        )
    return branch, ""

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
        "behind": None,
    }

    rc, _, _ = _git(repo, "remote", "get-url", remote)
    if rc != 0:
        report["status"] = "no-remote"
        report["reason"] = f"{remote} is not configured in this repository"
        return report

    current, why = head_branch(repo, remote, branch)
    if current != branch:
        report["status"] = "not-on-branch"
        report["reason"] = why
        return report

    tip, why = remote_tip(repo, remote, branch)
    if tip is None:
        report["status"] = "unreachable"
        report["reason"] = why
        return report
    report["remote_tip"] = tip

    # BEHIND IS NOT DIVERGED (#418). `divergence()` reads the ONE predicate that separates a
    # stale checkout from a genuine conflict -- ancestry alone cannot -- and is SHARED with
    # the patrol's freshness leg, so the pusher and the leg cannot disagree about what BEHIND
    # means. Reporting a pure-ancestor checkout DIVERGED reds the normal steady state (under
    # the worktree law the shared tree is behind `origin/main` most of the time), which is the
    # very harm #146's own ruling warns of.
    state = divergence(repo, tip)
    if state["state"] == "behind":
        report["status"] = "behind"
        report["behind"] = {"remote_tip": tip, "remote_ahead_by": state["behind"]}
        report["reason"] = (
            f"{remote}/{branch} is ahead of HEAD, which is a PURE ANCESTOR of it "
            f"({state['behind']} commit(s) behind, 0 ahead) — a stale checkout with nothing "
            f"of its own to publish. Reported, not resolved: this pusher does not fetch, "
            f"merge, reconcile or rewrite."
        )
        return report
    if state["state"] == "diverged":
        report["status"] = "diverged"
        report["diverged"] = {
            "remote_tip": tip,
            "remote_ahead_by": state["behind"],
            "local_ahead_by": state["ahead"],
        }
        report["reason"] = (
            f"{remote}/{branch} is not an ancestor of HEAD — the branch has DIVERGED "
            f"({state['ahead']} commit(s) ahead, {state['behind']} behind). Reported, not "
            f"resolved: this pusher does not fetch, merge, reconcile or rewrite."
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

    # WHAT IS PUBLISHED IS WHAT IS CHECKED OUT. `HEAD:{branch}` is the lane's own commit
    # whether HEAD stands on `branch` or is detached in a worktree; `{branch}:{branch}`
    # would push a LOCAL ref that a detached worktree never moves, so the pusher would
    # publish something other than the work it was asked to publish.
    rc, out, err = _git(repo, "push", remote, f"HEAD:{branch}")
    if rc != 0:
        report["status"] = "push-failed"
        report["reason"] = (err or out).strip()
        return report
    report["status"] = "published"

    # THE RECEIPT. The pushed sha is read AFTER the push, so the record names what the
    # remote actually received rather than what this round intended to send. A commit
    # landing between the two reads is the one residual race, and the reader's own
    # comparison -- remote tip against this receipt -- is what surfaces it.
    rc2, out2, _ = _git(repo, "rev-parse", "HEAD")
    pushed = out2.strip()
    if rc2 != 0 or not pushed:
        pushed = report["shas"][0] if report["shas"] else ""
    path, problem = write_receipt(
        repo, sha=pushed, remote=remote, branch=branch, instant=report["read_at"]
    )
    report["receipt"] = {
        "sha": pushed,
        "path": None if path is None else str(RECEIPT_REL),
        "reason": problem,
    }
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
    if report.get("behind"):
        lines.append(f"  BEHIND: {json.dumps(report['behind'], sort_keys=True)}")
    for held in report.get("held", []):
        lines.append(
            f"  held (within the {report['grace_secs']}s window, age {held['age_secs']}s): "
            f"{held['sha']} {held['session_id'] or 'no lane trailer'} — {held['subject']}"
        )
    if report.get("receipt"):
        rec = report["receipt"]
        if rec.get("reason"):
            lines.append(f"  receipt: NOT WRITTEN — {rec['reason']}")
        else:
            lines.append(f"  receipt: {rec['path']} records {rec['sha']}")
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
    # A round that could not be completed exits non-zero. "Held", "behind" and "diverged"
    # are COMPLETED rounds: the first is the window working, the second is a stale checkout
    # with nothing of its own, and the third is the report the ruling asks for — none is a
    # failure.
    return 1 if report["status"] in ("no-remote", "unreachable", "unreadable", "push-failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
