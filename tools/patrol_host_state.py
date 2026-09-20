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

**#117 added the second call site.** `tests/test_close_board_recorded.py` asserts a close
row RECORDED the board state it observed (`board=closed`); nothing verified the
observation was TRUE, so two close rows declared a board close that had never happened
and the gate read clean over both. The board-close leg below closes that gap: it reads
the close rows through the GATE's own predicate and constant and reports every
declaration the live board contradicts.

**A green predicate with no live input is a gate that has never been asked a
question.** So this runner supplies the input, and it prints each leg's own coverage
count beside its verdict: "0 problems" over "0 examined" and "0 problems" over "29
examined" are different facts, and only the second is a finding.

Four things it does deliberately:

- **Reads the board WHOLE** (`--state all`, no filter). The reverse leg — an intake
  row naming a number the board never heard of — is sound only over the full board,
  so a partial list is never passed: `board_intake_problems` skips the leg instead
  of guessing, and a skipped leg is printed as SKIPPED, never as zero problems.
- **States the instant it read.** A claim about a live board describes it at an
  instant; without the instant the claim cannot be re-checked, and an uncheckable
  receipt is testimony, not evidence (skill section 11).
- **Names every leg it does NOT run, with the reason.** A leg that is silent for
  want of a predicate is a different fact from a leg that passed, and the two must
  never render the same. (#121 wired the last such leg, so the list is empty — and
  the SURFACE stays, because a deferral's stated reason is exactly what rotted
  un-checked: an entry added here must declare the board issue tracking it and its
  factual claims about the tree in a closed vocabulary, and both are checked against
  HEAD on every run.)
- **Feeds the cron-thinness predicate the live table** (#121). The rows are read from
  every OpenCrabs home on the BOX, in place through a `mode=ro` URI — never copied,
  because a copy of a WAL-mode database is stale state and a disk leak. Ownership is
  the fleet manifest's declared `job_prefixes`, not the home a row sits in, and a row
  nobody declares is COUNTED and REPORTED rather than judged.
- **Checks the close rows' board declarations against the board it already read**
  (#117). The offline gate asserts the token was RECORDED; this leg asserts the
  recorded state was TRUE, reading the rows through the gate's own `BOARD_TOKEN`
  and `INVARIANT_LANDED` so the two surfaces cannot drift into two definitions of
  one field. Freshness stays REPORTED — the read instant travels with the count and
  is never folded into the verdict, because a check that fails by construction
  carries no more information than one that cannot fail.

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
import sqlite3
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "evidence" / "ledger.jsonl"
PREDICATE = REPO / "tests" / "test_board_intake_recorded.py"

# The close-board gate (#44) OWNS the definition of a close row's board
# declaration — its whole-detail token scan (`BOARD_TOKEN`) and its invariant
# boundary (`INVARIANT_LANDED`). The board-close leg below BINDS to both rather
# than re-deriving them: a canonical-trailer read (`trailer_tokens` in
# tools/field_predicate.py) sees only 40 of the 52 post-invariant rows, because 12
# carry the token OUTSIDE the trailing `=`-run — so a leg that re-derived the read
# would judge 12 rows fewer than the gate and go green over them. One field, one
# predicate (the class ruled at n=405 clause 5, n=599).
CLOSE_BOARD_GATE = REPO / "tests" / "test_close_board_recorded.py"

# --- the cron-thinness leg (#121) ---------------------------------------------
#
# The P7/P28 predicate EXISTS (tests/test_cron_thinness.py, `pacemaker_problems` over a
# list of cron rows, byte-paired into TEMPLATE/), so this runner FEEDS it. The deferral
# that used to stand here is DELETED rather than corrected: a reason that no longer
# exists cannot go stale, and a corrected reason is still a hand-written claim about the
# tree that nothing re-checks — the class #121 was filed to kill.
REGISTRY = REPO / "tools" / "registry.py"
CRON_THINNESS_PREDICATE = REPO / "tests" / "test_cron_thinness.py"


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


def load_close_board_gate(path: Path = CLOSE_BOARD_GATE):
    """The close-board gate module, loaded by path so no import path is assumed.

    The board-close leg reads the rows through THIS module's predicate and constant,
    so the leg and the gate cannot drift into two definitions of one field. The
    loader is deliberately separate from `load_predicate` so each surface's identity
    is visible at the call site rather than inferred from an argument.
    """
    spec = importlib.util.spec_from_file_location("close_board_gate", path)
    if spec is None or spec.loader is None:
        raise BoardReadError(f"cannot load the close-board gate at {path}")
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


def board_close_leg(issues: list[dict], rows: list[dict], *, gate=None,
                    read_at: str, predicate=None) -> dict:
    """The live board-close leg: every close row's board declaration checked (#117).

    Population: post-invariant close rows carrying the GATE's own token whose subject
    names an issue, where that issue is not closed on the board read. A subject the
    board has never heard of is a MISSING ROW, not a silent pass — it is reported as
    a problem, because "absent" and "closed" are different facts and only one of them
    is what the row declares.

    The population count is returned as `close_rows_examined` and printed beside the
    verdict, so a green reads as "examined N, 0 problems" rather than being
    indistinguishable from "examined nothing". The read instant travels with it:
    freshness is a property of the INSTANT and is REPORTED, never folded into the
    correctness verdict.
    """
    gate = gate or load_close_board_gate()
    predicate = predicate or load_predicate()
    token, boundary = gate.BOARD_TOKEN, gate.INVARIANT_LANDED
    bound = gate._parse_ts(boundary)

    board_numbers = {
        i.get("number") for i in issues if isinstance(i.get("number"), int)
    }
    closed = {
        i.get("number")
        for i in issues
        if isinstance(i.get("number"), int)
        and str(i.get("state", "")).strip().lower() == "closed"
    }

    problems: list[str] = []
    examined = 0
    for row in rows:
        if row.get("event") != "close":
            continue
        detail = str(row.get("detail") or "")
        if token not in detail:
            # The GATE's own predicate (a whole-detail token scan), never a second
            # parser: a trailer-only read would drop every row carrying the token
            # outside the trailing `=`-run and go green over them.
            continue
        number = predicate.issue_reference(row.get("subject"))
        if number is None:
            continue
        try:
            when = gate._parse_ts(row.get("ts", ""))
        except (ValueError, TypeError):
            continue
        if when < bound:
            # The GATE's own boundary: pre-invariant rows predate the rule and are
            # outside this population, exactly as the offline gate excuses them.
            continue
        examined += 1
        if number in closed:
            continue
        if number in board_numbers:
            problems.append(
                f"n={row.get('n')} declares {token} for #{number}, but #{number} is "
                f"still OPEN on the board (read at {read_at}) — the close records a "
                f"settlement that was never performed"
            )
        else:
            problems.append(
                f"n={row.get('n')} declares {token} for #{number}, but no issue "
                f"#{number} exists on the board (read at {read_at}) — the subject "
                f"names a board item that is absent, not one that is closed"
            )

    return {
        "name": "board-close",
        "status": "ASSERTED",
        "problems": problems,
        "excused": [],
        "coverage": {
            "close_rows_examined": examined,
            "board_read_at": read_at,
            "declaration_token": token,
            "invariant_boundary": boundary,
        },
    }


def load_module(name: str, path: Path):
    """Load a module by path, so no import path is assumed."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise BoardReadError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def closed_subjects(path: Path = LEDGER) -> set[str]:
    """Every subject the ledger has CLOSED — the offline read of a tracker's state.

    The ledger is in the tree, so a deferral's tracker can be checked against HEAD
    without a board call. A tracker that has closed is the exact staleness #121 found:
    the reason pointed at #54, and #54 had closed under it.
    """
    subjects: set[str] = set()
    if not path.is_file():
        return subjects
    for row in load_rows(path):
        if row.get("event") == "close" and row.get("subject"):
            subjects.add(str(row["subject"]))
    return subjects


def deferred_entry_problems(entries: list[dict], *, repo_root: Path = REPO,
                            ledger: Path = LEDGER) -> list[str]:
    """Every defect in a DEFERRED entry, checked against the tree — never trusted as prose.

    Wiring the cron-thinness leg retires a STRING, not the CLASS: `deferred_legs()` survives
    and can carry a new unchecked reason tomorrow. So an entry must declare, in a CLOSED
    vocabulary, what can be CHECKED:

      - `tracker`: the board issue carrying the remaining question, as an int;
      - `claims`:  `[{"path": <repo-relative>, "present": <bool>}, ...]`.

    Both are evaluated against HEAD. A tracker already CLOSED in the ledger, or a claim the
    tree contradicts, is a defect — the vocabulary is closed on purpose, because free prose
    cannot be checked and a reason that cannot be checked IS the defect this guards.

    The caller prints the population it examined: this guard's live population is
    legitimately EMPTY until the next deferral, so an empty read is never a clean verdict —
    the PROBE that shows it bites is the evidence (skill section 8).
    """
    problems: list[str] = []
    if not entries:
        return problems
    closed = closed_subjects(ledger)
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            problems.append(
                f"<entry {index}>: not a mapping ({type(entry).__name__}) — a deferred "
                f"entry must be a mapping declaring a tracker and its claims"
            )
            continue
        name = str(entry.get("name") or f"<entry {index}>")
        tracker = entry.get("tracker")
        if not isinstance(tracker, int) or isinstance(tracker, bool):
            problems.append(
                f"{name}: declares no integer `tracker` — a deferral must name the board "
                f"issue that carries the remaining question, so a reader can follow it"
            )
        elif f"#{tracker}" in closed:
            problems.append(
                f"{name}: tracker #{tracker} is CLOSED in the ledger — a reader following "
                f"it lands on a settled item with nothing left to answer, which is exactly "
                f"how this class first appeared"
            )
        claims = entry.get("claims")
        if not isinstance(claims, list) or not claims:
            problems.append(
                f"{name}: declares no `claims` — a deferral must state its factual claims "
                f"about the tree in the closed vocabulary, or nothing can re-check them"
            )
            continue
        for claim in claims:
            if (
                not isinstance(claim, dict)
                or not isinstance(claim.get("path"), str)
                or not isinstance(claim.get("present"), bool)
            ):
                problems.append(
                    f"{name}: a claim is not {{'path': str, 'present': bool}} — {claim!r}"
                )
                continue
            actual = (repo_root / claim["path"]).exists()
            if actual != claim["present"]:
                problems.append(
                    f"{name}: claims {claim['path']!r} present={claim['present']}, but the "
                    f"tree says present={actual} — a stated reason must not outlive the "
                    f"tree it describes"
                )
    return problems


def declared_prefixes(repo: Path = REPO) -> list[str]:
    """This factory's declared `job_prefixes`, read from the fleet manifest.

    Ownership is by the manifest's DECLARATION, never by the home a row happens to sit
    in: all twelve ai-antispam rows sit in the OPS home, so a profile-scoped read answers
    a narrower question than the one it names (#102). An empty return is reported by the
    caller as an unattributable population, never read as a clean one.
    """
    registry = load_module("oc_registry", REGISTRY)
    manifest = registry.load_fleet_manifest()
    want = str(repo.resolve())
    for record in manifest.get("factories", []):
        declared = record.get("repo")
        if isinstance(declared, str) and str(Path(declared).resolve()) == want:
            return [str(p) for p in record.get("job_prefixes", [])]
    return []


def box_cron_rows(root: Path | None = None) -> tuple[list[dict], list[str], list[str]]:
    """(rows, homes_read, unreached) for every OpenCrabs home's ENABLED cron rows.

    Read IN PLACE through a `mode=ro` URI — copying a live WAL-mode database yields stale
    state and leaks disk, so no home is ever copied. `opencrabs_home_dbs()` RETURNS the
    unreached list rather than dropping it: a home that could not be read is not a home
    with nothing in it, and the two must never render the same.
    """
    registry = load_module("oc_registry", REGISTRY)
    dbs, unreached = registry.opencrabs_home_dbs(root)
    rows: list[dict] = []
    homes_read: list[str] = []
    for db in dbs:
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        except sqlite3.Error as exc:
            unreached.append(f"{db.parent.name}: {exc}")
            continue
        try:
            fetched = list(conn.execute(
                "select name, coalesce(deliver_to,''), coalesce(prompt,'') "
                "from cron_jobs where enabled = 1"
            ))
        except sqlite3.Error as exc:
            unreached.append(f"{db.parent.name}: {exc}")
            continue
        finally:
            conn.close()
        for name, deliver_to, prompt in fetched:
            rows.append({
                "name": name,
                "deliver_to": deliver_to,
                "prompt": prompt,
                "home": db.parent.name,
            })
        homes_read.append(db.parent.name)
    return rows, homes_read, unreached


def attribute_rows(rows: list[dict], prefixes: list[str]) -> tuple[list[dict], int]:
    """(rows attributed to this factory, count attributed to nobody) — by declaration."""
    attributed: list[dict] = []
    unattributed = 0
    for row in rows:
        name = str(row.get("name") or "")
        if prefixes and any(name.startswith(prefix) for prefix in prefixes):
            attributed.append(row)
        else:
            unattributed += 1
    return attributed, unattributed


def cron_thinness_leg(rows: list[dict], homes_read: list[str], unreached: list[str],
                      prefixes: list[str], *, predicate=None, read_at: str = "") -> dict:
    """The cron-thinness leg: THIS factory's rows, judged by the PURE predicate.

    A row the manifest cannot attribute is COUNTED and REPORTED, never judged — the runner
    judges its own factory's rows, and an unattributable row belongs to nobody here. ZERO
    attributed rows over a declared, non-empty prefix set FAILS LOUDLY: a clean verdict
    over an examined-nothing read is not a verdict (skill section 8).

    The rows are read live by the caller; the predicate stays pure and is handed a list.
    """
    predicate = predicate or load_module("cron_thinness_predicate",
                                         CRON_THINNESS_PREDICATE)
    attributed, unattributed = attribute_rows(rows, prefixes)
    problems: list[str] = []
    if prefixes and not attributed:
        problems.append(
            f"no enabled row attributed to this factory — {len(rows)} row(s) read across "
            f"{len(homes_read)} home(s) with declared prefixes {prefixes!r}, and the "
            f"population came back EMPTY, which is reported and never read as clean"
        )
    judged, excused = predicate.pacemaker_problems(attributed)
    problems.extend(judged)
    return {
        "name": "cron-thinness",
        "status": "ASSERTED",
        "problems": problems,
        "excused": excused,
        "coverage": {
            "rows_read": len(rows),
            "homes_read": len(homes_read),
            "homes_read_names": homes_read,
            "homes_unreached": unreached,
            "rows_attributed": len(attributed),
            "rows_unattributed": unattributed,
            "prefixes": prefixes,
            "read_at": read_at,
        },
    }


def deferred_legs() -> list[dict]:
    """Legs this runner does not run, each declaring its tracker and its checkable claims.

    EMPTY is the honest state now that the cron-thinness leg is wired: it runs, so there
    is no reason left to print. The function stays because the SURFACE is the class #121
    guards — `deferred_entry_problems` checks any entry added here, and the guard's own
    population is legitimately empty until the next deferral.
    """
    return []


def render(legs: list[dict], deferred: list[dict], *, slug: str, read_at: str,
           issues: list[dict], deferred_problems: list[str] | None = None) -> str:
    """The report. Every count travels with the predicate that produced it."""
    deferred_problems = list(deferred_problems or [])
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
        if leg["name"] == "board-close":
            lines.append(
                f"  close rows (declaring {cov['declaration_token']}, at or after "
                f"{cov['invariant_boundary']}): {cov['close_rows_examined']} examined, "
                f"{len(leg['problems'])} problem(s) — board read at {cov['board_read_at']}"
            )
        elif leg["name"] == "cron-thinness":
            lines.append(
                f"  rows: {cov['rows_read']} enabled read across {cov['homes_read']} "
                f"home(s), {cov['rows_attributed']} attributed to this factory "
                f"({', '.join(cov['prefixes']) or 'no declared prefix'}), "
                f"{cov['rows_unattributed']} attributed to nobody"
            )
            lines.append(
                f"  homes unreached: {len(cov['homes_unreached'])}"
                + (f" — {'; '.join(cov['homes_unreached'])}" if cov['homes_unreached'] else "")
                + f" — read at {cov['read_at']}"
            )
        else:
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
        if leg.get("reason"):
            lines.append(f"  {leg['reason']}")
        if "tracker" in leg:
            lines.append(f"  tracker: #{leg['tracker']}")
        for claim in leg.get("claims", []):
            lines.append(
                f"  claim: {claim['path']} present={claim['present']}"
            )
        lines.append("")
    lines.append(
        f"deferred entries examined: {len(deferred)} — checked against HEAD for a closed "
        f"tracker and a claim the tree contradicts"
    )
    for problem in deferred_problems:
        lines.append(f"    - {problem}")
    lines.append("")
    total = sum(len(leg["problems"]) for leg in legs) + len(deferred_problems)
    forward = sum(
        int(leg["coverage"].get("forward_issues_examined", 0)) for leg in legs
    )
    closes = sum(
        int(leg["coverage"].get("close_rows_examined", 0)) for leg in legs
    )
    cron = sum(
        int(leg["coverage"].get("rows_attributed", 0)) for leg in legs
    )
    lines.append(
        f"verdict: {total} problem(s) over {forward} open issue(s) examined, "
        f"{closes} close row(s) checked against the board, and {cron} cron row(s) "
        f"attributed to this factory and judged"
    )
    return "\n".join(lines)


def main(
    argv: list[str] | None = None,
    *,
    board_fn=fetch_board,
    slug_fn=remote_slug,
    rows_fn=load_rows,
    cron_rows_fn=box_cron_rows,
    prefixes_fn=declared_prefixes,
    predicate=None,
    out=print,
    err=print,
) -> int:
    """Run the patrol read. Every dependency is injectable, so a probe drives it
    without a live board — and a probe that can only run against the live board is
    a probe that cannot be run at all when the board is what is broken. The cron read
    and the prefix declaration are injected for the same reason: a probe drives the
    cron-thinness leg with NO live database."""
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

    cron_rows, homes_read, unreached = cron_rows_fn()
    legs = [
        board_intake_leg(issues, rows, predicate=predicate),
        board_close_leg(issues, rows, read_at=read_at),
        cron_thinness_leg(
            cron_rows, homes_read, unreached, prefixes_fn(), read_at=read_at
        ),
    ]
    deferred = deferred_legs()
    deferred_problems = deferred_entry_problems(deferred)
    out(render(legs, deferred, slug=slug, read_at=read_at, issues=issues,
               deferred_problems=deferred_problems))
    return 1 if any(leg["problems"] for leg in legs) or deferred_problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
