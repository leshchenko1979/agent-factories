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
- **FETCH, THEN FAST-FORWARD; DIVERGENCE REPORTED, NEVER RESOLVED.** Before its push
  the pusher SYNCS: it fetches, then fast-forwards its own checkout to the remote tip
  (`git merge --ff-only`). The no-fetch bound this bullet USED TO DECLARE is amended by
  the owner's own answer (q36 -> (a), ledger n=2746), and the amendment is the point:
  the cron pusher runs from a shared tree that lanes advance past, so a pusher that
  never fetched read a cache and reported the normal steady state forever. `--ff-only`
  is the load-bearing half AND the amendment's limit: a merely-behind tree advances
  silently, while a GENUINE divergence refuses loudly and the round publishes nothing.
  A fetch is not a rewrite and an ff-only merge is a fast-forward, so neither is one of
  the three verbs bound 2 forbids.
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

Run:  python3 tools/publish.py            report only, nothing is pushed or synced
      python3 tools/publish.py --apply    sync (fetch + fast-forward), then push when
                                          the grace window allows
Exit: 0 the round ran (published, held, in sync, behind, or reported a divergence)
      1 the round could not be completed (no remote, unreachable, unreadable, a refused
        fast-forward, or a failed push)
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
RECEIPT_NAME = "publish-receipt.json"

def git_common_dir(repo: Path) -> Path | None:
    """This checkout's GIT COMMON DIR, or None when it cannot be read (#445, #242).

    The RELATIVE FORM IS THE TRAP: from the MAIN checkout `git rev-parse --git-common-dir`
    prints the RELATIVE string ".git", so `Path(raw).resolve()` resolves against the
    CALLER's cwd -- from /tmp that yields "/tmp/.git", matching nothing while looking like
    a fix. The path is joined to the repo FIRST, which is correct from both a main checkout
    and a worktree (`--path-format=absolute` also works but needs git >= 2.33).
    """
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--git-common-dir"],
        capture_output=True, text=True,
    )
    raw = proc.stdout.strip()
    if proc.returncode != 0 or not raw:
        return None
    return (Path(repo) / raw).resolve()


def receipt_path(repo: Path) -> Path | None:
    """Where the pusher records its OWN last push: ONE record per repository.

    `None` when the common dir cannot be read. There is deliberately NO fallback to a
    checkout-local path: a fallback would reinstate, silently, the very defect this shape
    removes -- the caller reports the absence instead.
    """
    common = git_common_dir(repo)
    return None if common is None else common / RECEIPT_NAME


def write_receipt(repo: Path, *, sha: str, remote: str, branch: str, instant: str):
    """Record the push this round made. `(path, reason)`; a failure is REPORTED.

    Written through a sibling temp file and renamed, so a reader never sees a half-written
    receipt -- the same reason the ledger fsyncs before it releases its lock.
    """
    path = receipt_path(repo)
    if path is None:
        return None, "the receipt could not be written: the repository's git common dir is unresolvable"
    # `checkout` is the ORIGIN half of the honesty requirement (#445): the record is keyed
    # on the REPOSITORY, so a reader in a sibling worktree must be able to say WHICH
    # checkout made the push it is reading.
    body = {
        "sha": sha, "instant": instant, "remote": remote, "branch": branch,
        "checkout": str(Path(repo).resolve()),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        return None, f"the receipt could not be written to {path}: {exc}"
    return path, ""


def read_receipt(repo: Path):
    """`(receipt, reason)`. An ABSENT receipt is neither an error nor a mismatch.

    A factory that has never pushed has no receipt, and reporting that as a finding would
    red the reader on every fresh clone. The absence is stated; it is not a verdict.
    """
    path = receipt_path(repo)
    if path is None:
        return None, "no receipt read: the repository's git common dir is unresolvable"
    if not path.is_file():
        return None, f"no receipt recorded at {path}"
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"the receipt at {path} could not be read: {exc}"
    if not isinstance(body, dict) or not str(body.get("sha") or "").strip():
        return None, f"the receipt at {path} names no sha"
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

# --- THE SYNC: fetch, then fast-forward (#418 PART 2, owner q36 -> (a), ledger n=2746) ---
#
# The cron pusher runs from a FIXED PATH -- the shared tree -- and lanes publish from their
# own worktrees, which advance `origin/main` past it. So the shared tree is routinely BEHIND,
# and a pusher that never fetched read a cache and reported that normal steady state forever.
# The owner's answer is shape (a): fetch, `merge --ff-only`, then push.
#
# The two halves do different work and are ONE act. The FETCH is what makes the local view
# current at all. The `--ff-only` MERGE is the load-bearing half: a merely-behind tree
# advances silently, while a GENUINE divergence refuses -- loudly, and the round publishes
# nothing. A fetch is not a rewrite and an ff-only merge is a fast-forward, so neither is one
# of the three verbs #146 bound 2 forbids; `--ff-only` is what keeps it that way.
#
# TWO REFUSALS, TWO REMEDIES, and the round must not confuse them. A GENUINE DIVERGENCE is a
# HISTORY fact: the remote tip is not an ancestor of HEAD, so nothing can be fast-forwarded.
# A BLOCKED fast-forward is a WORKING-TREE fact: history fast-forwards cleanly, but local
# modifications sit on paths the incoming commits touch, so git refuses to overwrite them.
# The first is `diverged`; the second must NAME its paths, because its remedy is a peer's
# in-flight edit, not a reconciliation.

def blocking_paths(repo: Path, tip: str):
    """The locally-modified paths an incoming fast-forward would overwrite, SORTED.

    COMPUTED, never scraped out of git's refusal message: that wording is not a contract,
    and a reader that parses it goes quiet the day it changes. Two reads define the answer
    and it is their intersection -- what the working tree has modified against HEAD
    (tracked) plus what it holds untracked, against what the incoming commits touch. An
    untracked file is included because git refuses to overwrite one just the same.
    """
    rc, tracked_out, _ = _git(repo, "diff", "--name-only", "HEAD")
    if rc != 0:
        return []
    rc, untracked_out, _ = _git(repo, "ls-files", "--others", "--exclude-standard")
    untracked = untracked_out if rc == 0 else ""
    rc, incoming_out, _ = _git(repo, "diff", "--name-only", "HEAD", tip)
    if rc != 0:
        return []
    local = {
        line.strip()
        for line in (tracked_out + "\n" + untracked).splitlines()
        if line.strip()
    }
    incoming = {line.strip() for line in incoming_out.splitlines() if line.strip()}
    return sorted(local & incoming)

def sync_remote(repo: Path, remote: str, branch: str):
    """`{"ok", "reason", "blocking", "before", "after"}` -- fetch, then fast-forward.

    One round of the owner's shape (a). `ok` is True only when the fetch ran AND the
    fast-forward was accepted -- an already-level or already-ahead checkout is accepted
    too, which git calls "Already up to date". On refusal the caller must read `blocking`:
    a NON-EMPTY list means the fast-forward was blocked by the working tree; an EMPTY one
    beside a still-behind tree means git refused for a reason this reading did not model,
    which the caller must treat as a divergence rather than as a clean sync.
    """
    result = {"ok": False, "stage": "", "reason": "", "blocking": [], "before": "", "after": ""}
    rc, out, _ = _git(repo, "rev-parse", "HEAD")
    if rc == 0:
        result["before"] = out.strip()
    rc, out, err = _git(repo, "fetch", remote, branch)
    if rc != 0:
        result["stage"] = "fetch"
        result["reason"] = (err or out).strip() or f"git fetch exited {rc}"
        return result
    rc, out, err = _git(repo, "merge", "--ff-only", f"{remote}/{branch}")
    result["stage"] = "merge"
    if rc == 0:
        rc, out, _ = _git(repo, "rev-parse", "HEAD")
        result["ok"] = True
        if rc == 0:
            result["after"] = out.strip()
        return result
    result["reason"] = (err or out).strip() or f"git merge --ff-only exited {rc}"
    rc, tip_out, _ = _git(repo, "rev-parse", f"{remote}/{branch}")
    if rc == 0 and tip_out.strip():
        tip = tip_out.strip()
        if divergence(repo, tip)["state"] == "behind":
            result["blocking"] = blocking_paths(repo, tip)
    return result


# --- IS THE ROW READABLE YET? (issue #441, ruled at ledger n=2907) -----------------
#
# A ledger row is a CITATION TARGET: a board ruling comment, a peer row, a report and a
# notify all name `n=<N>`. Until #441 nothing asked whether the row a citation names could
# be REACHED by the reader who followed it. The measured instance: ruling comments named
# `n=2900-2905` on the public board from 06:40:46Z while the commit carrying those rows was
# not authored until 06:48:39Z and not published until 07:09:08Z -- ~28 minutes in which
# the citation was public and its referent existed nowhere a reader could go.
#
# The cause is a DESIGNED bound, not neglect: the pusher holds a commit younger than its
# 900s grace window (#146/n=1168, scoped by #284/e133c87d), so a lane that commits, cites
# and pushes in one turn CANNOT publish same-turn. So the remedy is never "push faster" --
# that re-creates the direct-push anti-pattern #329 removed. It is to STATE the publication
# of whatever a durable surface names, and to gate the citing act on that state.
#
# THE PREDICATE IS THE REMOTE'S OWN LEDGER, NOT A COMMIT'S ANCESTRY. "Is commit X pushed?"
# answers a question about a COMMIT; a reader following `n=2905` needs the ROW, and a row is
# readable exactly when the remote's `evidence/ledger.jsonl` carries it. The two agree in
# the ordinary case and can disagree after a revert or a repair -- and it is readability
# that a citation claims.
LEDGER_REL = Path("evidence") / "ledger.jsonl"
# The LOCAL tracking ref, for callers that cannot reach the network (the offline gate). It
# is a CACHE, updated only by a fetch, so a reader that uses it MUST state that bound beside
# its verdict -- the same rule `remote_tip` refuses to violate silently one screen up.
DEFAULT_TRACKING_REF = "refs/remotes/origin/main"

def ledger_rows_at(repo: Path, ref: str):
    """`(rows, reason)` -- the row numbers the ledger blob at `ref` carries."""
    rc, out, err = _git(repo, "show", f"{ref}:{LEDGER_REL.as_posix()}")
    if rc != 0:
        return None, (err or out).strip() or f"git show {ref}:{LEDGER_REL} exited {rc}"
    rows: set[int] = set()
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            return None, f"the ledger blob at {ref} carries a line that is not JSON"
        if isinstance(row, dict) and isinstance(row.get("n"), int):
            rows.add(row["n"])
    return rows, ""

def unpublished_rows(repo: Path, rows, *, ref: str = DEFAULT_TRACKING_REF):
    """Which of `rows` a reader could NOT reach in the ledger at `ref`.

    Returns `{"ref", "checked", "unpublished", "reason"}`. An unreadable blob is reported
    as a REASON rather than folded into an empty `unpublished`: "I could not ask" and
    "everything is published" are different facts and must never render alike (the
    `remote_tip` rule, one function up). A caller that cannot read the blob must therefore
    treat `reason` as a finding, never as a clean result.
    """
    wanted = sorted({int(row) for row in rows})
    published, why = ledger_rows_at(repo, ref)
    if published is None:
        return {"ref": ref, "checked": len(wanted), "unpublished": wanted, "reason": why}
    return {
        "ref": ref,
        "checked": len(wanted),
        "unpublished": [row for row in wanted if row not in published],
        "reason": "",
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
        "sync": None,
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

    # --- THE SYNC (#418 PART 2, owner q36 -> (a), ledger n=2746) --------------------------
    # The cron pusher runs from a FIXED PATH -- the shared tree -- and lanes publish from
    # their own worktrees, which advance `origin/main` past it. So the shared tree is
    # routinely BEHIND, and the no-fetch bound this round used to honour left it reading a
    # cache and reporting that normal steady state forever. A PUBLISHING round therefore
    # syncs first: fetch, then fast-forward.
    #
    # UNDER `--apply` ONLY. A report-only round (`python3 tools/publish.py`, no flag) is a
    # READ -- the patrol's freshness leg reads this module's predicates on the same shared
    # tree -- and a read that fast-forwarded would mutate the surface it was inspecting. The
    # sync is part of PUBLISHING, so it rides the flag that publishes.
    #
    # ORDER IS LOAD-BEARING: the sync runs BEFORE the classification below, because after it
    # a merely-behind checkout is LEVEL with the tip and reads "ahead-or-same". That is the
    # whole point -- it advances silently and then publishes its own commits, instead of
    # reading BEHIND forever. A genuine divergence is untouched: `--ff-only` cannot
    # fast-forward it, so it still refuses and is still REPORTED rather than resolved.
    if apply:
        synced = sync_remote(repo, remote, branch)
        report["sync"] = {
            "ok": synced["ok"],
            "stage": synced["stage"],
            "before": synced["before"],
            "after": synced["after"],
            "blocking": synced["blocking"],
            "reason": synced["reason"],
        }
        if not synced["ok"]:
            if synced["stage"] == "fetch":
                report["status"] = "unreachable"
                report["reason"] = (
                    f"{remote}/{branch} could not be fetched, so this round could not sync "
                    f"before publishing: {synced['reason']}"
                )
                return report
            if synced["blocking"]:
                report["status"] = "ff-blocked"
                report["reason"] = (
                    f"{remote}/{branch} carries commits this checkout could fast-forward "
                    f"to, but the fast-forward is BLOCKED by local modifications on "
                    f"{len(synced['blocking'])} path(s) it would overwrite "
                    f"({', '.join(synced['blocking'])}). Reported at {report['read_at']}, "
                    f"not resolved: publishing from a tree whose own edits sit on those "
                    f"paths would clobber a peer's in-flight work. The next round publishes "
                    f"once those paths are clear."
                )
                return report
            # An EMPTY blocking list beside a refused merge is a HISTORY fact, not a
            # working-tree one -- a genuine divergence -- and the classification below names
            # it. That is the honest read, and it keeps the two refusals distinct.

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
            f"of its own to publish, so nothing is stranded. "
            + (
                "This round ran with --apply, so the sync above should have advanced HEAD to "
                "the tip; that it did not is what the sync payload explains."
                if apply else
                "A report-only round reads and does not sync, so run with --apply to advance "
                "this checkout to the tip."
            )
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
            f"({state['ahead']} commit(s) ahead, {state['behind']} behind). "
            + (
                "The sync's fast-forward refused it and this round publishes nothing — a "
                "genuine divergence is reported, never resolved, and this pusher never "
                "rewrites published history."
                if apply else
                "Reported, not resolved: this pusher never rewrites published history, and a "
                "report-only round does not sync either."
            )
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
        "path": None if path is None else str(path),
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
    syn = report.get("sync")
    if syn:
        if syn.get("ok"):
            before, after = syn.get("before", ""), syn.get("after", "")
            if before and after and before != after:
                lines.append(f"  SYNC: fast-forwarded HEAD {before[:12]} -> {after[:12]}")
            else:
                lines.append(f"  SYNC: already level at {(after or before)[:12]}")
        else:
            lines.append(f"  SYNC: {syn.get('stage', '?')} refused — {syn.get('reason', '')[:120]}")
            if syn.get("blocking"):
                lines.append(f"    blocking path(s): {', '.join(syn['blocking'])}")
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
    return 1 if report["status"] in (
        "no-remote", "unreachable", "unreadable", "push-failed", "ff-blocked",
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
