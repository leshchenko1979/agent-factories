#!/usr/bin/env python3
"""Patrol runner: feed LIVE host state into the pure board/ledger predicates.

Origin (issue #95). `tests/test_board_intake_recorded.py` ships the PREDICATE for
"an OPEN issue with no intake row" and is wired into the audit — but its live test
calls `board_intake_problems([], rows, complete_board=False)`, an EMPTY board, so
the forward leg examines **0 open issues** and the reverse leg is skipped by design.
Its own docstring says why: a repo gate cannot call `gh`, so part (b) — a host-side
runner that fetches the board — is "a later step and not this file's acceptance".
#56 closed with part (b) out of scope, and #54 part (b) is the same shape: one
mechanism, two call sites. This file is that mechanism.

**A green predicate with no live input is a gate that has never been asked a
question.** So this runner supplies the input, and it prints each leg's own coverage
count beside its verdict: "0 problems" over "0 examined" and "0 problems" over "29
examined" are different facts, and only the second is a finding.

Three things it does deliberately:

- **Reads the board WHOLE** (`--state all`, no filter). The reverse leg — an intake
  row naming a number the board never heard of — is sound only over the full board,
  so a partial list is never passed: `board_intake_problems` skips the leg instead
  of guessing, and a skipped leg is printed as SKIPPED, never as zero problems.
- **States the instant it read.** A claim about a live board describes it at an
  instant; without the instant the claim cannot be re-checked, and an uncheckable
  receipt is testimony, not evidence (skill section 11).
- **Names every leg it does NOT run, with the reason.** A leg that is silent for
  want of a predicate is a different fact from a leg that passed, and the two must
  never render the same.

The board slug is derived from the git remote, so nothing here hardcodes a factory.

Run:  python3 tools/patrol_host_state.py
Exit: 0 no problems, 1 problems found, 2 the board could not be read.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "evidence" / "ledger.jsonl"
PREDICATE = REPO / "tests" / "test_board_intake_recorded.py"

# The leg this runner does NOT yet run, and why. Printed every cycle so an absent
# leg can never be read as a passing one (the discipline the predicate's own three
# legs already apply to each other).
DEFERRED_LEG_REASON = (
    "#54 part (b) — the P7/P28 pacemaker-thinness assertion was never written, so "
    "there is no predicate for a host-side runner to feed: grep for deliver_to or "
    "set_goal over tests/ and tools/ returns only tools/registry_render.py, which "
    "RENDERS a cron row into a table and asserts nothing about it. One mechanism, "
    "two call sites — this runner is the mechanism, and a call site whose predicate "
    "does not exist is a predicate to write first, not a runner to wire."
)


class BoardReadError(RuntimeError):
    """The live board could not be read. Never silently treated as an empty board."""


def load_predicate(path: Path = PREDICATE):
    """The pure predicate module, loaded by path so no import path is assumed."""
    spec = importlib.util.spec_from_file_location("board_intake_predicate", path)
    if spec is None or spec.loader is None:
        raise BoardReadError(f"cannot load the predicate at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def repo_slug(remote: str) -> str:
    """`owner/repo` from a git remote URL, in both the ssh and https forms.

    Pure, so the parser is probeable without a repository: a slug that is wrong
    makes every leg read the wrong board, and a wrong board reads clean.
    """
    text = remote.strip()
    if text.endswith(".git"):
        text = text[: -len(".git")]
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+)$", text)
    if not match:
        raise BoardReadError(f"cannot derive owner/repo from remote {remote!r}")
    return f"{match.group(1)}/{match.group(2)}"


def remote_slug(repo: Path = REPO) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise BoardReadError(
            f"git remote get-url origin failed (rc={proc.returncode}): "
            f"{proc.stderr.strip()}"
        )
    return repo_slug(proc.stdout)


def fetch_board(slug: str) -> list[dict]:
    """The FULL board: every state, no filter, so the reverse leg is sound."""
    proc = subprocess.run(
        [
            "gh",
            "issue",
            "list",
            "-R",
            slug,
            "--state",
            "all",
            "--limit",
            "1000",
            "--json",
            "number,state,title,closedAt",
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise BoardReadError(
            f"gh issue list failed (rc={proc.returncode}): {proc.stderr.strip()[:300]}"
        )
    try:
        issues = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise BoardReadError(f"gh issue list returned unparseable JSON: {exc}") from exc
    if not isinstance(issues, list):
        raise BoardReadError("gh issue list returned something other than a list")
    return issues


def load_rows(path: Path = LEDGER) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def board_intake_leg(issues: list[dict], rows: list[dict], predicate=None) -> dict:
    """The live board-intake leg, with its own coverage beside its verdict."""
    predicate = predicate or load_predicate()
    problems, excused = predicate.board_intake_problems(
        issues, rows, complete_board=True
    )
    coverage = predicate.board_intake_coverage(issues, rows, complete_board=True)
    return {
        "name": "board-intake",
        "status": "ASSERTED",
        "problems": list(problems),
        "excused": list(excused),
        "coverage": dict(coverage),
    }


def deferred_legs() -> list[dict]:
    """Legs this runner does not run, each with the reason — never a silent zero."""
    return [
        {
            "name": "cron-thinness",
            "status": "NOT RUN",
            "reason": DEFERRED_LEG_REASON,
        }
    ]


def render(legs: list[dict], deferred: list[dict], *, slug: str, read_at: str,
           issues: list[dict]) -> str:
    """The report. Every count travels with the predicate that produced it."""
    open_count = sum(
        1 for i in issues if str(i.get("state", "")).strip().lower() == "open"
    )
    lines = [
        f"patrol host-state read: {slug} at {read_at}",
        f"board: {len(issues)} issue(s) read WHOLE (--state all), {open_count} open",
        "",
    ]
    for leg in legs:
        cov = leg["coverage"]
        lines.append(f"LEG {leg['name']} — {leg['status']}")
        lines.append(
            f"  forward  (open issue with no intake row): "
            f"{cov['forward_issues_examined']} examined, "
            f"{sum(1 for p in leg['problems'] if 'OPEN on the board' in p)} problem(s)"
        )
        lines.append(
            f"  reverse  (intake row naming no board issue): "
            f"{cov['reverse_intake_rows_examined']} examined — {cov['reverse_leg']}"
        )
        lines.append(f"  excused: {len(leg['excused'])}")
        lines.append(f"  problems: {len(leg['problems'])}")
        for problem in leg["problems"]:
            lines.append(f"    - {problem}")
        for excuse in leg["excused"]:
            lines.append(f"    excused: {excuse}")
        lines.append("")
    for leg in deferred:
        lines.append(f"LEG {leg['name']} — {leg['status']}")
        lines.append(f"  {leg['reason']}")
        lines.append("")
    total = sum(len(leg["problems"]) for leg in legs)
    examined = sum(
        int(leg["coverage"]["forward_issues_examined"]) for leg in legs
    )
    lines.append(
        f"verdict: {total} problem(s) over {examined} open issue(s) examined"
    )
    return "\n".join(lines)


def main(
    argv: list[str] | None = None,
    *,
    board_fn=fetch_board,
    slug_fn=remote_slug,
    rows_fn=load_rows,
    predicate=None,
    out=print,
    err=print,
) -> int:
    """Run the patrol read. Every dependency is injectable, so a probe drives it
    without a live board — and a probe that can only run against the live board is
    a probe that cannot be run at all when the board is what is broken."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", help="override the owner/repo derived from the remote")
    args = parser.parse_args(argv)

    read_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        slug = args.repo or slug_fn()
        issues = board_fn(slug)
        rows = rows_fn()
    except BoardReadError as exc:
        # A board that could not be read is NOT a board with nothing on it.
        err(f"patrol host-state read: FAILED at {read_at} — {exc}")
        return 2

    legs = [board_intake_leg(issues, rows, predicate=predicate)]
    out(render(legs, deferred_legs(), slug=slug, read_at=read_at, issues=issues))
    return 1 if any(leg["problems"] for leg in legs) else 0


if __name__ == "__main__":
    raise SystemExit(main())
