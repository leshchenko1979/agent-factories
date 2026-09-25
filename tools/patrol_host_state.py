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

Six things it does deliberately:

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

- **Reads the notify logs a failed thin trigger leaves behind** (#122). A cron's notify can
  fail while the table records a successful run, and the table cannot express the outcome —
  `cron_jobs` carries no status, error or result column at all. WHERE the failure lands is
  the job-local log, and the predicate is the SUCCESS TOKEN (`notification id <uuid>`), never
  the byte count the finding was first stated in: a log carrying no receipt is a notify that
  produced no receipt, which IS the invariant. A failure report cannot ride the channel that
  failed, which is why this is a READER and not a second notify.

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
FIELD_PREDICATE = REPO / "tools" / "field_predicate.py"

# ---- the canonicality leg (law: SKILL.md section 8, the ladder T0-T4) --------------
#
# A check that reports a discrepancy names the TIER that resolved it (law section 8), and
# this leg is the PROCESS half of that rule: the tiers DECLARED in the ledger are
# enumerated, and every `T4` — the verdict meaning NEITHER side is canonical — that no
# later row has superseded is reported. Without this, an unresolved tier lives only in a
# lane's prose, which is where a resolution goes to be forgotten.
#
# Population and its limit, stated because a count without its predicate is unreadable:
# `rows_read` is every ledger row loaded, and `rows_declaring_tier` is the subset whose
# canonical trailer DECLARES `tier=`. The second figure is legitimately zero today — the
# field is new, so nothing has declared one yet — and zero THERE is not the vacuous-clean
# failure the population law bars, because the enumeration asserted non-empty is
# `rows_read`, never the tier count. What proves this leg BITES is the probe in
# `tests/test_patrol_host_state.py`, not a live hit (#112, ruling n=657 item 8).
CANONICALITY_KEY = "tier"
CANONICALITY_TIERS = ("T0", "T1", "T2", "T3", "T4")
CANONICALITY_UNRESOLVED = "T4"
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

# --- the notify-receipt leg (#122) ---------------------------------------------
#
# Origin (issue #122, ruled at ledger n=772..774). A thin-trigger cron's notify can FAIL
# while the cron table records a SUCCESSFUL run, and the table cannot express the outcome:
# `pragma table_info(cron_jobs)` carries no status, error or result column at all —
# `last_run_at` is stamped when the run is DISPATCHED, and nothing writes an outcome beside
# it. The failure therefore lands on the only surface that survives it: the job-local log
# the thin trigger's own redirect writes.
#
# **A FAILURE REPORT CANNOT RIDE THE CHANNEL THAT FAILED.** The obvious repair — have the
# prompt report its own non-zero exit — is dead on arrival: the notify failed because the
# gateway was unreachable, so a second notify travels the SAME transport and fails the same
# way. That is why the shape here is a READER, and not a workaround for one.
#
# **THE PREDICATE IS CONTENT, NOT SIZE** (ruling n=774). The finding was stated as a byte
# count (155 = failure, 197 = success), and a byte count is a count by PATTERN — this
# factory's own law bars a pattern count from standing in for a count of items, and a new
# error string arriving at a familiar length would satisfy it. The sharper predicate is the
# SUCCESS TOKEN: a log that produced a receipt carries `notification id <uuid>`; a log that
# carries none is a notify that produced no receipt, which IS the invariant. The uuid is
# REQUIRED rather than the bare phrase, so prose ABOUT a missing id cannot satisfy the read
# (the prose-as-data class, ruled at n=405 clause 5).
#
# **NON-VACUITY RIDES A PROBE, NEVER A LOUD-FAIL-ON-ZERO** (ruling n=774 done-criteria).
# The live population of failed notifies is legitimately EMPTY on a quiet day, so an empty
# read here is a normal read and is PRINTED as one — the opposite call from the cron-thinness
# leg above, which fails loudly because its population is the rows this factory declares. The
# probe that drives a log carrying no receipt is what shows the leg can bite (#112's shape).
LOG_DIR = Path("/tmp")
# `<job-name>-<YYYYmmddTHHMMSS>.log` — the thin trigger's own redirect, nothing else.
NOTIFY_LOG_RE = re.compile(r"^(?P<job>.+)-(?P<stamp>\d{8}T\d{6})\.log$")
NOTIFY_RECEIPT_TOKEN = "notification id"
# The token AND the id it names. Anchored on a UUID so a log that merely MENTIONS the token
# cannot read as a receipt, and the `\b` ends keep a longer identifier from matching.
NOTIFY_RECEIPT_RE = re.compile(
    r"\bnotification id\s+[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
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
                "select id, name, coalesce(deliver_to,''), coalesce(prompt,''), "
                "coalesce(last_run_at,'') "
                "from cron_jobs where enabled = 1"
            ))
        except sqlite3.Error as exc:
            unreached.append(f"{db.parent.name}: {exc}")
            continue
        finally:
            conn.close()
        for row_id, name, deliver_to, prompt, last_run_at in fetched:
            rows.append({
                # The id is read because a report must RESOLVE the row it names: two jobs
                # may share a name across homes, and a name alone is not an address. The
                # notify-receipt leg cites it; the cron-thinness predicate ignores it and
                # is handed the row whole rather than a projection (#126).
                "id": row_id,
                "name": name,
                "deliver_to": deliver_to,
                "prompt": prompt,
                # The fire instant, read for the duty-receipt leg (#147): the round a
                # trigger woke is the one dated the day the run was DISPATCHED, and
                # `last_run_at` is that instant. `enabled = 1` is in the WHERE clause
                # above, so every row here is enabled and carries no `enabled` key.
                "last_run_at": last_run_at,
                "home": db.parent.name,
            })
        homes_read.append(db.parent.name)
    return rows, homes_read, unreached


def attribute_rows(rows: list[dict], prefixes: list[str]) -> tuple[list[dict], list[dict]]:
    """(rows attributed to this factory, rows attributed to NOBODY) — by declaration.

    The unattributed rows are RETURNED, not counted. A bare count is not a report: a
    reader who must act on one has to be able to name it and find the home it came from,
    and a number that resolves to no object cannot be resolved by anyone (#126). Nothing
    here JUDGES them — attribution only separates the two populations.
    """
    attributed: list[dict] = []
    unattributed: list[dict] = []
    for row in rows:
        name = str(row.get("name") or "")
        if prefixes and any(name.startswith(prefix) for prefix in prefixes):
            attributed.append(row)
        else:
            unattributed.append(row)
    return attributed, unattributed


def cron_thinness_leg(rows: list[dict], homes_read: list[str], unreached: list[str],
                      prefixes: list[str], *, predicate=None, read_at: str = "") -> dict:
    """The cron-thinness leg: THIS factory's rows, judged by the PURE predicate.

    A row the manifest cannot attribute is COUNTED, NAMED and REPORTED, never judged — the
    runner judges its own factory's rows, and an unattributable row belongs to nobody here.
    It is reported rather than gated: a box-wide RED over unattributable rows would fire on
    the household rows another home legitimately carries (#101, ruling n=610 PART 3b), so
    the reader gets the population instead of a verdict, and non-vacuity rides the probe
    rather than a loud-fail-on-zero the live population could never satisfy (#112).

    ZERO attributed rows over a declared, non-empty prefix set FAILS LOUDLY: a clean
    verdict over an examined-nothing read is not a verdict (skill section 8).

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
            "rows_unattributed": len(unattributed),
            "unattributed_rows": [
                {"name": str(r.get("name") or ""), "home": str(r.get("home") or "")}
                for r in unattributed
            ],
            "prefixes": prefixes,
            "read_at": read_at,
        },
    }


def reads_notify_receipt(text: str) -> bool:
    """True when `text` carries a notify RECEIPT — the token AND the id it names.

    The uuid is required on purpose. A log whose only line is "no notification id was
    recorded" carries the phrase and must NOT satisfy the read, because a field prose can
    SATISFY is the class ruled at n=405 clause 5.
    """
    return NOTIFY_RECEIPT_RE.search(text) is not None

def notify_failure_line(text: str) -> str:
    """The line that reports the failure: the transport error if present, else the first
    non-empty line. Quoted verbatim — a report a reader cannot trace back to bytes is
    testimony, not evidence."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        if "transport_error" in line:
            return line
    return lines[0] if lines else ""

def notify_logs(log_dir: Path = LOG_DIR) -> tuple[list[tuple[str, Path]], str | None]:
    """(matched (job-name, path) pairs, not-run reason) for the thin-trigger log surface.

    The reason is `None` when the directory was READ and a stated reason when it was not:
    an absent directory is a NOT RUN, and a read that never happened must not render as a
    read that found nothing. The pairs sort by job then filename, so two runs over the same
    surface print the same order and a diff of two reports is readable.
    """
    if not log_dir.is_dir():
        return [], (
            f"the thin-trigger log directory {log_dir} does not exist — the only surface "
            f"a failed notify lands on was never read"
        )
    matched: list[tuple[str, Path]] = []
    for path in log_dir.iterdir():
        if not path.is_file():
            continue
        found = NOTIFY_LOG_RE.match(path.name)
        if found:
            matched.append((found.group("job"), path))
    matched.sort(key=lambda pair: (pair[0], pair[1].name))
    return matched, None

def notify_receipt_leg(rows: list[dict], homes_read: list[str], unreached: list[str],
                       prefixes: list[str], *, log_dir: Path = LOG_DIR,
                       read_at: str = "") -> dict:
    """The notify-receipt leg: did each thin trigger's notify produce a RECEIPT?

    POPULATION. The job-local logs whose job NAME is an ENABLED cron row this factory
    DECLARES — the same manifest declaration `cron_thinness_leg` attributes rows by, so one
    predicate governs both legs and this one judges its own surface only. Three buckets are
    COUNTED, NAMED and REPORTED rather than dropped, because a population that resolves to
    no object cannot be checked by the reader it is reported to (#126):

      - `logs_matched` — judged, because a live row this factory declares owns the name;
      - `retired_logs` — this factory's prefix with no live row: history, never judged;
      - `unattributed_logs` — nobody here declares it: another factory's law (#101, n=610).

    A log that EXISTS and cannot be read is a PROBLEM, never an absence — a declared surface
    that defeats the read is the #69 clause (e) shape. An absent log DIRECTORY is a NOT RUN
    carrying its reason and no problem: the surface is a constant of this tool rather than
    factory data, and a box with no thin triggers yet has nothing to judge.

    ZERO MATCHED LOGS IS NOT A FAILURE HERE (ruling n=774 done-criteria). This population is
    legitimately empty on a quiet day, so an empty read is PRINTED and never gated — the
    opposite call from the cron-thinness leg, whose population is the rows the factory
    declares and which therefore does fail loudly. Non-vacuity here is carried by the probe.
    """
    attributed, _ = attribute_rows(rows, prefixes)
    live = {str(row.get("name") or ""): row for row in attributed}
    matched, not_run = notify_logs(log_dir)
    problems: list[str] = []
    excused: list[str] = []
    judged: list[dict] = []
    retired: list[dict] = []
    foreign: list[dict] = []
    for name, path in matched:
        if not prefixes or not any(name.startswith(prefix) for prefix in prefixes):
            foreign.append({"job": name, "path": str(path)})
            continue
        row = live.get(name)
        if row is None:
            retired.append({"job": name, "path": str(path)})
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            problems.append(
                f"{name}: {path} exists and could not be read ({exc}) — a surface that "
                f"defeats the read is a defect, never an absence"
            )
            continue
        if reads_notify_receipt(text):
            excused.append(f"{name}: {path.name} carries a receipt — the notify delivered")
            continue
        line = notify_failure_line(text)
        judged.append({
            "job": name,
            "id": str(row.get("id") or ""),
            "path": str(path),
            "line": line,
        })
        problems.append(
            f"{name} (cron id {row.get('id') or 'unstated'}): the notify produced NO "
            f"receipt — {path} carries no '{NOTIFY_RECEIPT_TOKEN}' id; failure line: "
            f"{line!r}"
        )
    return {
        "name": "notify-receipt",
        "status": "NOT RUN" if not_run else "ASSERTED",
        "reason": not_run,
        "problems": problems,
        "excused": excused,
        "coverage": {
            "log_dir": str(log_dir),
            "jobs_read": len(attributed),
            "rows_read": len(rows),
            "homes_read": len(homes_read),
            "homes_read_names": homes_read,
            "homes_unreached": unreached,
            "logs_on_surface": len(matched),
            "logs_matched": len(matched) - len(retired) - len(foreign),
            "logs_without_receipt": len(judged),
            "logs_retired": len(retired),
            "logs_unattributed": len(foreign),
            "retired_logs": retired,
            "unattributed_logs": foreign,
            "prefixes": prefixes,
            "read_at": read_at,
        },
    }

# --- the duty-completion-receipt leg (#147) ------------------------------------
#
# Origin (issue #147, ruled at ledger n=974). #122's leg asks whether a thin trigger's
# notify produced a RECEIPT. This leg asks the question #122 cannot: did the DUTY that
# notify woke actually COMPLETE? They are opposite ends of one mechanism and neither
# implies the other — a notify can succeed while the duty fails (this leg), or the notify
# can fail (the leg above). Measured on the registry-attest pacemaker: six fragments sat
# at attested_at 2026-09-19 for four days against a job firing daily at 0 6, while
# `cron_job_runs` carried SUCCESS on 09-21 and 09-23. Nothing reported it, because a cron
# run row describes the TRIGGER and the trigger worked.
#
# **THE RECEIPT BELONGS TO THE DUTY, NEVER TO THE TRIGGER** (ruling n=974). A cron run row
# may truthfully report only that the trigger fired. The duty's completion receipt is an
# append-only ledger RUN row written by the woken lane, carrying the round outcome and the
# targets attested. `attested_at` is RESULTING STATE — a CONSEQUENCE of a completed round —
# and is never the receipt, which is why a stale attestation and a missing receipt are
# different findings and this leg reports the second.
#
# **THE ROW DECLARES ITS OWN RECEIPT.** This runner must not hardcode a job name: the
# repository's own doctrine is that a name comes from the declaration and never from a
# reader (`tools/registry.py` says so in place). So a row that owes a duty receipt SAYS SO
# in its own prompt, on one line:
#
#     receipt_subject: <stem>
#
# and the leg judges exactly those rows. A row declaring no stem is NOT JUDGED, and is
# COUNTED and NAMED in the coverage: a clean verdict over a population that declared
# nothing must never be the same output as one that examined the population and found it
# clean (P29).
#
# **THE ROUND COMES FROM THE ROW'S OWN RECORD, not from a cron parser.** `last_run_at` is
# stamped when the run is DISPATCHED, so it names the instant the trigger last fired and
# the round it woke is the one dated that day. Deriving the round by parsing `cron_expr`
# would re-implement a scheduler and would be wrong for every form this parser does not
# know; reading the row's own record cannot disagree with the row.
#
# **NON-VACUITY RIDES A PROBE, NEVER A LOUD-FAIL-ON-ZERO.** A box whose duty round
# completed cleanly has an empty problem list, so an empty read here is a normal read and
# is PRINTED as one. The probe that drives a fired round with no receipt is what shows the
# leg can bite (#112's shape).
RECEIPT_DECL_RE = re.compile(r"^receipt_subject:\s*(\S+)\s*$", re.MULTILINE)
FRAGMENT_STORE = REPO / "registry" / "factories"
# The outcome values that mean the duty did NOT complete. Read through the SHARED
# positional reader rather than a private scan: `outcome` is one field with one predicate
# (SKILL.md section 11), and a regex here would drift from the ledger's own reading.
DUTY_FAILED_OUTCOMES = ("failed", "abandoned")

def declared_receipt_stem(prompt: str) -> str | None:
    """The receipt stem this row declares, or None — the line `receipt_subject: <stem>`.

    Anchored to a whole line so a sentence that merely MENTIONS the declaration cannot
    satisfy it: prose about a field is not a declaration of one (the class ruled at
    n=405 clause 5).
    """
    found = RECEIPT_DECL_RE.search(prompt or "")
    return found.group(1) if found else None

def receipt_round(last_run_at: str) -> str | None:
    """The round date a fire instant belongs to — its UTC date, `YYYY-MM-DD`.

    `last_run_at` is RFC3339 TEXT on this table, so it takes NO `unixepoch` modifier:
    `messages.created_at` is INTEGER and needs one, `cron_jobs.last_run_at` is TEXT and
    returns NULL for every row if handed it. An absent or unshaped value returns None and
    the caller reports NOT JUDGED rather than naming a round it cannot read.
    """
    text = (last_run_at or "").strip()
    if len(text) < 10 or text[4] != "-" or text[7] != "-":
        return None
    return text[:10]

def attestation_state(store: Path = FRAGMENT_STORE) -> tuple[dict, str | None]:
    """(fragment -> attested_at, not-read reason) — RESULTING STATE, never a receipt.

    Read because criterion 4 requires `attested_at` to be NAMED as resulting state rather
    than offered as the receipt, and naming it without reading it would be testimony. It
    never makes this leg green: a completed round and a stale one differ HERE only after
    the receipt has already been found. A store that cannot be read returns a stated
    reason, so an unread store never renders as a fresh one.
    """
    if not store.is_dir():
        return {}, f"the fragment store {store} does not exist"
    read: dict = {}
    for path in sorted(store.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            read[path.name] = f"unreadable: {type(exc).__name__}"
            continue
        if isinstance(data, dict):
            read[str(data.get("factory") or path.stem)] = data.get("attested_at")
    return read, None

def duty_receipt_leg(rows: list[dict], homes_read: list[str], unreached: list[str],
                     prefixes: list[str], ledger_rows: list[dict], *,
                     read_at: str = "", store: Path = FRAGMENT_STORE,
                     predicate=None) -> dict:
    """The duty-completion leg: did the round each thin trigger woke LEAVE A RECEIPT?

    POPULATION. The ENABLED cron rows this factory DECLARES that carry a receipt
    declaration in their own prompt. Three buckets are COUNTED, NAMED and PRINTED rather
    than dropped, because a population that resolves to no object cannot be checked by the
    reader it is reported to (#126): the rows JUDGED, the declared rows owing no receipt,
    and the rows attributed to nobody.
    """
    if predicate is None:
        predicate = field_predicate_readers()

    attributed, foreign = attribute_rows(rows, prefixes)
    declared: list[tuple[dict, str]] = []
    undeclared: list[dict] = []
    for row in attributed:
        stem = declared_receipt_stem(str(row.get("prompt") or ""))
        if stem:
            declared.append((row, stem))
        else:
            undeclared.append(row)

    problems: list[str] = []
    excused: list[str] = []
    judged: list[dict] = []
    for row, stem in declared:
        name = str(row.get("name") or "(unnamed row)")
        job_id = str(row.get("id") or "unstated")
        fired = str(row.get("last_run_at") or "")
        round_date = receipt_round(fired)
        if round_date is None:
            excused.append(
                f"{name} (cron id {job_id}): declares a receipt but records no fire "
                f"instant (last_run_at={fired!r}), so no round can be named — NOT JUDGED"
            )
            continue
        subject = f"{stem}-{round_date}"
        receipts = [r for r in ledger_rows if str(r.get("subject") or "") == subject]
        judged.append({
            "name": name, "id": job_id, "stem": stem, "round": round_date,
            "fired": fired, "receipts": len(receipts),
        })
        if not receipts:
            problems.append(
                f"{name} (cron id {job_id}): the round {round_date} has NO duty receipt — "
                f"no ledger run row carries the subject {subject!r}. A cron run row records "
                f"only that the TRIGGER fired, so a green run here is a MISSING duty and "
                f"not a clean one"
            )
            continue
        for receipt in receipts:
            detail = str(receipt.get("detail") or "")
            for value in DUTY_FAILED_OUTCOMES:
                if predicate.declares_token(detail, "outcome", value):
                    problems.append(
                        f"{name} (cron id {job_id}): the round {round_date} FAILED — "
                        f"receipt row n={receipt.get('n')} declares outcome={value}"
                    )

    state, state_reason = attestation_state(store)
    return {
        "name": "duty-receipt",
        "status": "ASSERTED" if declared else "NOT RUN",
        "reason": (None if declared else (
            "no enabled row this factory declares carries a `receipt_subject:` "
            "declaration, so no duty owes a receipt on this box"
        )),
        "problems": problems,
        "excused": excused,
        "coverage": {
            "jobs_read": len(attributed),
            "rows_read": len(rows),
            "homes_read": len(homes_read),
            "homes_read_names": homes_read,
            "homes_unreached": unreached,
            "prefixes": prefixes,
            "jobs_declaring_receipt": len(declared),
            "jobs_undeclared": len(undeclared),
            "undeclared_jobs": [str(r.get("name") or "") for r in undeclared],
            "jobs_unattributed": len(foreign),
            "duties_judged": judged,
            "duties_missing": len([p for p in problems if "NO duty receipt" in p]),
            "attested_at_state": state,
            "attested_at_not_read": state_reason,
            "read_at": read_at,
        },
    }

def field_predicate_readers():
    """The shared detail-field predicate, loaded by path so no import path is assumed.

    Loaded rather than imported because this runner is copied into every member factory,
    where the layout above it is not the same — the same reason `load_predicate` exists
    for the board predicate. The READ goes through the shared predicate and never a
    private `split("=")`: one field, one predicate (SKILL.md section 11).
    """
    spec = importlib.util.spec_from_file_location("field_predicate", FIELD_PREDICATE)
    if spec is None or spec.loader is None:
        raise BoardReadError(f"cannot load the field predicate at {FIELD_PREDICATE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def canonicality_leg(rows: list[dict], *, read_at: str) -> dict:
    """Every tier the ledger DECLARES, and every `T4` still standing.

    The read is a SEQUENCE, not a single scan: a `T4` is superseded by a LATER row for the
    same subject declaring a resolved tier (T0-T3). Without that, a tier that was routed
    and answered would red this leg for ever — the permanent-false-positive class #139
    names, where a leg with no exit teaches the next reader to ignore a red patrol.
    """
    fp = field_predicate_readers()
    problems: list[str] = []
    declared: list[tuple[int, str, str]] = []

    for index, row in enumerate(rows):
        detail = str(row.get("detail") or "")
        if CANONICALITY_KEY not in fp.declared_keys(detail):
            continue
        value = ""
        for token in fp.trailer_tokens(detail):
            found = fp.keyed_value(token, CANONICALITY_KEY)
            if found is not None:
                value = found
                break
        tier = value.upper()
        if tier not in CANONICALITY_TIERS:
            problems.append(
                f"n={row.get('n')} ({row.get('subject')}): tier={value!r} is not one of "
                f"{'/'.join(CANONICALITY_TIERS)} — an unrecognised tier cannot have "
                f"resolved a discrepancy, and reading it as one is the defect this leg "
                f"exists to catch"
            )
            continue
        declared.append((index, str(row.get("subject") or ""), tier))

    unresolved: list[tuple[int, str]] = []
    superseded = 0
    for index, subject, tier in declared:
        if tier != CANONICALITY_UNRESOLVED:
            continue
        answered = any(
            later_index > index
            and later_subject == subject
            and later_tier != CANONICALITY_UNRESOLVED
            for later_index, later_subject, later_tier in declared
        )
        if answered:
            superseded += 1
            continue
        unresolved.append((index, subject))

    for index, subject in unresolved:
        row = rows[index]
        problems.append(
            f"n={row.get('n')} ({subject}): tier={CANONICALITY_UNRESOLVED} — NEITHER side "
            f"is canonical and no later row for this subject resolves it. Re-measure, or "
            f"route the open question; an unresolved tier is a finding, never a clean result"
        )

    return {
        "name": "canonicality-tier",
        "status": "ASSERTED",
        "problems": problems,
        "excused": [],
        "coverage": {
            "rows_read": len(rows),
            "rows_declaring_tier": len(declared),
            "tiers_declared": sorted({tier for _, _, tier in declared}),
            "t4_superseded": superseded,
            "t4_standing": len(unresolved),
            "unresolved_subjects": [subject for _, subject in unresolved],
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
            for row in cov.get("unattributed_rows", []):
                lines.append(
                    f"    unattributed: {row['name'] or '(unnamed row)'} "
                    f"(home {row['home'] or 'unknown'})"
                )
            lines.append(
                f"  homes unreached: {len(cov['homes_unreached'])}"
                + (f" — {'; '.join(cov['homes_unreached'])}" if cov['homes_unreached'] else "")
                + f" — read at {cov['read_at']}"
            )
        elif leg["name"] == "notify-receipt":
            declared = ", ".join(cov["prefixes"]) or "no declared prefix"
            lines.append(
                f"  jobs: {cov['jobs_read']} enabled row(s) attributed to this factory "
                f"of {cov['rows_read']} read across {cov['homes_read']} home(s) "
                f"({declared})"
            )
            lines.append(
                f"  homes unreached: {len(cov['homes_unreached'])}"
                + (f" — {'; '.join(cov['homes_unreached'])}" if cov['homes_unreached'] else "")
            )
            lines.append(
                f"  logs matched: {cov['logs_matched']} of {cov['logs_on_surface']} log(s) "
                f"on {cov['log_dir']} naming a live row this factory declares — "
                f"{cov['logs_without_receipt']} produced no receipt"
            )
            for row in cov.get("retired_logs", []):
                lines.append(
                    f"    no live row: {row['job']} ({row['path']}) — history, not judged"
                )
            for row in cov.get("unattributed_logs", []):
                lines.append(
                    f"    unattributed: {row['job']} ({row['path']}) — nobody here declares it"
                )
            if leg.get("reason"):
                lines.append(f"  {leg['reason']}")
            lines.append(f"  read at {cov['read_at'] or 'unstated'}")
        elif leg["name"] == "duty-receipt":
            declared = ", ".join(cov["prefixes"]) or "no declared prefix"
            lines.append(
                f"  jobs: {cov['jobs_read']} enabled row(s) attributed to this factory "
                f"of {cov['rows_read']} read across {cov['homes_read']} home(s) "
                f"({declared})"
            )
            lines.append(
                f"  duties: {cov['jobs_declaring_receipt']} row(s) declare a receipt, "
                f"{cov['jobs_undeclared']} declare none and are NOT JUDGED, "
                f"{cov['jobs_unattributed']} attributed to nobody"
            )
            for name in cov.get("undeclared_jobs", []):
                lines.append(f"    owes no receipt: {name or '(unnamed row)'}")
            for duty in cov.get("duties_judged", []):
                lines.append(
                    f"    {duty['name']} (cron id {duty['id']}): round {duty['round']} "
                    f"(fired {duty['fired'] or 'unstated'}) — "
                    f"{duty['receipts']} receipt row(s)"
                )
            lines.append(
                "  attested_at (RESULTING STATE, never the receipt): "
                + (
                    f"{len(cov['attested_at_state'])} fragment(s) read"
                    if not cov.get("attested_at_not_read")
                    else str(cov["attested_at_not_read"])
                )
            )
            for factory, when in sorted(cov.get("attested_at_state", {}).items()):
                lines.append(f"    {factory}: {when}")
            if leg.get("reason"):
                lines.append(f"  {leg['reason']}")
            lines.append(f"  read at {cov['read_at'] or 'unstated'}")
        elif leg["name"] == "canonicality-tier":
            tiers = ", ".join(cov["tiers_declared"]) or "none declared"
            lines.append(
                f"  rows: {cov['rows_declaring_tier']} of {cov['rows_read']} declare a "
                f"tier ({tiers}); {cov['t4_standing']} standing tier="
                f"{CANONICALITY_UNRESOLVED}, {cov['t4_superseded']} superseded"
            )
            if cov["unresolved_subjects"]:
                lines.append(
                    f"  UNRESOLVED: {', '.join(cov['unresolved_subjects'])} — no tier "
                    f"resolved these, and that is a finding, not a clean result"
                )
            lines.append(f"  read at {cov['read_at']}")
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
    notify = sum(
        int(leg["coverage"].get("logs_matched", 0)) for leg in legs
    )
    lines.append(
        f"verdict: {total} problem(s) over {forward} open issue(s) examined, "
        f"{closes} close row(s) checked against the board, and {cron} cron row(s) "
        f"attributed to this factory and judged, and {notify} notify log(s) judged "
        f"for a receipt"
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
    log_dir: Path = LOG_DIR,
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
        notify_receipt_leg(
            cron_rows, homes_read, unreached, prefixes_fn(), log_dir=log_dir,
            read_at=read_at,
        ),
        duty_receipt_leg(
            cron_rows, homes_read, unreached, prefixes_fn(), rows, read_at=read_at
        ),
        canonicality_leg(rows, read_at=read_at),
    ]
    deferred = deferred_legs()
    deferred_problems = deferred_entry_problems(deferred)
    out(render(legs, deferred, slug=slug, read_at=read_at, issues=issues,
               deferred_problems=deferred_problems))
    return 1 if any(leg["problems"] for leg in legs) or deferred_problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
