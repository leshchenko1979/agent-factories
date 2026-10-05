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
  the job-local log, and the predicate is the RECEIPT FORM the daemon wrote — `delivered to
  session <uuid>` or `deferred for session <uuid>` — never the byte count the finding was
  first stated in. Both are success forms and only one carries an id, so a token-only
  predicate refused the STRONGER half of its own evidence (#139, ruling n=1087). A log
  carrying no receipt form is a notify that produced no receipt, which IS the invariant. A
  failure report cannot ride the channel that failed, which is why this is a READER and not
  a second notify.

The board slug is derived from the git remote, so nothing here hardcodes a factory.

Run:  python3 tools/patrol_host_state.py
Exit: 0 no problems, 1 problems found, 2 the board could not be read.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "evidence" / "ledger.jsonl"
FIELD_PREDICATE = REPO / "tools" / "field_predicate.py"
# The kit pin reader, loaded by path beside it rather than imported: this runner is copied
# into every member factory where the layout above it differs, and a module-level sibling
# import here is what broke this file's own gate (#171) the day one was added.
KIT_PIN = REPO / "tools" / "kit_pin.py"
# The boundary reader (#175). Reached by PATH through `load_module`, never imported:
# this runner is copied into every member factory, where the layout above it differs.
LEDGER_BOUNDARY = REPO / "tests" / "ledger_boundary.py"

# ---- the publish-freshness leg (issue #146, ruled at ledger n=1168) ----------------
#
# The pusher (`tools/publish.py`) is the MECHANISM that gets a commit to origin; this leg
# is the FRESHNESS SURFACE that notices when it has not. Both are needed and neither
# substitutes for the other: the pusher runs from a clock with no lane watching it, so a
# pusher that stopped working is invisible except here.
#
# THE RESIDUAL WINDOW, stated because a threshold without its derivation is unreadable.
# The pusher runs at the 6h cadence floor and holds any commit younger than its grace
# window, so an unpushed commit younger than CADENCE + GRACE is EXPECTED — flagging it
# would red this leg on every round between two healthy pushes and teach the next reader
# to ignore it. Older than that, and no healthy pusher can explain it. The window is
# ACCEPTED and STATED, never hidden: `residual_secs` travels in the coverage.
PUBLISH_REMOTE = "origin"
PUBLISH_BRANCH = "main"
PUBLISH_PUSHER = REPO / "tools" / "publish.py"
PUBLISH_CADENCE_SECS = 6 * 3600
PUBLISH_GRACE_SECS = 900
PUBLISH_RESIDUAL_SECS = PUBLISH_CADENCE_SECS + PUBLISH_GRACE_SECS

# WHOSE BOUNDS THESE ARE, and what this leg does NOT measure. The three figures above are
# the PUSHER's declared bounds (`tools/publish.py`): they say how often it runs and how long
# it holds a young commit, and they bind that tool ALONE. They are not a property of the
# fleet and not a property of this leg. What this leg measures is LAG -- commits committed
# but not yet on the remote -- and it does NOT measure cadence compliance: a pusher that ran
# late and a pusher that never ran both leave the same unpushed commit behind, and only the
# commit is this leg's subject.
PUBLISH_LEG_SCOPE = (
    "LAG only: commits committed but not yet on the remote. This leg does NOT measure "
    "whether the pusher ran on its cadence, and the pusher's window binds the pusher "
    "alone -- neither is a property of the fleet."
)
PUBLISH_BOUNDS_LABEL = (
    "the PUSHER's declared bounds (tools/publish.py), which bind it alone -- grace_secs / "
    "cadence_secs / residual_secs are NOT a property of the fleet"
)

# THE DUTY RESIDUAL, stated because a threshold without its derivation is unreadable.
# A round's receipt lands when the lane the trigger woke FINISHES ITS TURN, and the leg
# cannot read a lane's turn -- so a round young enough that its lane is plausibly still
# working must not be judged. DECLARED rather than derived: deriving it from the round's
# own `cron_expr` would mean widening the cron SELECT to reach a column this file
# deliberately never parses (see the note at `box_cron_rows`), and it would be wrong for
# every form that parser does not know -- six declaring jobs carry six distinct forms.
# The value is MEASURED, not chosen. The filed specimen (#200, n=1455) judged three live
# lanes MISSING at age 1136 s (fired 06:00:46Z, read 06:19:42Z), and every fire->receipt
# latency on this factory's own ledger for a round that DID clear sits at or under 765 s.
# The next datum up is 2388 s, and the fastest cadence among the declaring jobs is 6 h --
# a window reaching either would let a round go UNJUDGED until the next fire superseded it.
# 1800 s clears the specimen with 1.58x margin, stays under the 2388 s datum, and is 8.3%
# of the fastest cadence. Printed in the coverage: an ACCEPTED window, never a hidden one.
DUTY_RESIDUAL_SECS = 1800

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

# --- the stall-census leg (#260) -------------------------------------------------
#
# Triage's census keys on the SUBJECT field, so a unit dispatched by a WAVE row reads as
# undispatched. Measured 2026-10-03 on this ledger: board #181 carries intake n=1221, run
# n=1226 and ruling n=1233, and NO dispatch row of its own -- its dispatch leg is the wave
# row n=1214 (`subject=kit-adoption-wave-2026-09-26`, `refs=None`), whose detail reads
# "...carrying BOTH instruments (board #181 ledger bundle, board #182 questions)...". A
# subject-keyed census cannot see it (#2092).
#
# WHY THE THRESHOLD IS 1.0 d AND NOT THE CARD'S 30 m. The two predicates are different
# questions and the ruling names them apart (n=1861): the Triage card's `>30 m` binds a
# CLAIMED-but-silent lane, and this leg binds a NEVER-claimed dispatch. Measured on this
# ledger 2026-10-03: the active queue's own in-flight dispatches sit at 0.02-0.05 d and
# fall below a day, so a threshold of one day reports a stall rather than the ordinary lag
# between a dispatch and its claim. The threshold is PRINTED with this basis on every run
# (acceptance criterion 3), never carried in a reader's memory.
STALL_CENSUS_THRESHOLD_DAYS = 1.0
STALL_CENSUS_THRESHOLD_BASIS = (
    "1.0 d -- the shortest interval in which a lane that intends to take a dispatched "
    "item would have claimed it. Distinct from the Triage card's >30 m, which binds a "
    "CLAIMED-but-silent lane; this binds a NEVER-claimed dispatch. Measured on this "
    "ledger 2026-10-03: the active queue's own in-flight dispatches sit at 0.02-0.05 d "
    "and fall below it."
)
# The subject form `#<n>` is the ledger tool's, BOUND rather than re-derived: one field,
# one predicate (SKILL.md section 11).
LEDGER_TOOL = REPO / "tools" / "ledger.py"

# ---- the kit-drift leg (plan 2646d31a step 10) --------------------------------------
#
# A member factory's drift was previously unmeasurable: the only thing that could say
# whether a factory's copy of `tools/ledger.py` matched the template's was a person
# reading both trees. Measured 2026-09-25 over the bootstrap's own named set across five
# member factories: 50 cells, 1 identical, 20 drifted, 29 absent -- and three of the
# absent ones were the write-path guards (`tools/gate_budget.py` and both
# `tools/hooks/` refusal points), which had therefore never bound a single member.
#
# WHY THIS IS A PATROL LEG AND NOT A GATE, stated because the coupling is the whole
# design. A gate reading five external repos would turn THIS factory's audit red whenever
# a MEMBER is stale -- our verdict would become a function of another lane's backlog, and
# the failure would be reported in the wrong factory. A patrol leg reports LIVE HOST
# STATE, which is exactly what drift is.
#
# WHY DRIFT IS COVERAGE AND NOT A PROBLEM, for the same reason. The patrol's exit code is
# the TRIAGE lane's signal, and a leg that reds on every patrol until five other
# factories finish their ports is the permanent-false-positive class #139 names: a leg
# with no exit teaches the next reader to ignore a red patrol. So the measurement is
# reported in full and the PROBLEMS are reserved for the one thing that is this factory's
# own defect -- a read that could not be taken, which is the examined-nothing case.
#
# THE TWO POPULATIONS ARE BOTH REPORTED, because the earlier figure was measured over a
# NARROWER predicate and a number must travel with its own. `manifest_cells` is every
# (member, manifest file) pair; `bootstrap_cells` is the subset restricted to the files
# `TEMPLATE/BOOTSTRAP.md` step 4c names, which is what the 1/20/29 baseline was taken
# over. Reporting only one of them would make the other unreproducible.
KIT_MANIFEST_REL = "registry/kit.json"
FLEET_MANIFEST = REPO / "registry" / "fleet.json"

# The files `TEMPLATE/BOOTSTRAP.md` step 4c instructs a factory to copy, by their
# repo-relative path in a member tree. Read as a CONSTANT because the bootstrap states
# them in prose across several paragraphs; a parser over that prose would be a second
# derivation of a fact the document already carries, and this list is asserted against
# the bootstrap by the leg's probe rather than trusted.
BOOTSTRAP_NAMED = (
    "tools/ledger.py",
    "tools/audit.py",
    "tools/field_predicate.py",
    "tools/gate_budget.py",
    "tools/hooks/commit-msg",
    "tools/hooks/pre-commit",
    "tests/test_ledger.py",
    "tests/test_ontology.py",
    "tests/test_rework.py",
    "tests/rework_table.py",
)

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

# --- the embedded-law-content class (#178) --------------------------------------
#
# A cron prompt must be a THIN POINTER to the law. When it carries the law's CONTENT
# inline, the law moves and the prompt does not: the prompt is a copy, the copy drifts,
# and nothing re-reads it (#178, ruling n=1230). The class is DRIFT-PRONE EMBEDDED STATE
# — a boundary, window, epoch or deadline the law owns — never a section reference, which
# the ruling measured at ZERO across the whole box and is therefore the WRONG zero to
# brief against.
#
# THE PREDICATE IS AN ISO-8601 INSTANT (a date WITH a time component), and that is a
# MEASURED choice rather than a convenience. A BARE DATE fires on the best-shaped row on
# the box: the box's own best-shaped row says "it was 5,289 chars of pasted law on
# 2026-09-26, every word of which already lived in triage.md" — a historical rationale
# EXPLAINING why its prompt is thin, and a date-only predicate reports it as a defect.
# Measured over 40 enabled rows across 3 homes at 2026-09-27T03:4xZ: a date-only
# predicate fires on 10 rows, an instant-only predicate on 5, and the 5 are exactly the
# rows asserting a boundary/window/epoch/deadline. A bare date is most often a CITATION
# of when something was decided — the past, not state — so it is REPORTED and never
# judged, which keeps the excluded population visible instead of silent.
#
# THE INSTANT IS NOT THE WHOLE CLASS, and the gap is stated rather than hidden: a prompt
# restating campaign law normatively ("only 0-star inboxes are usable") carries content
# the instant predicate cannot see. No phrasing predicate replaces it, because the
# wake-only marker ("do NOT execute any project work yourself") is itself normative and
# appears on nearly every row — a normative scan would fire on the whole population and
# be read as noise. The instant is the objective half, and the REPORTED bare-date
# population is what keeps the rest checkable by a reader.
EMBEDDED_INSTANT_RE = re.compile(r"\b20\d{2}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
BARE_DATE_RE = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")

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
# error string arriving at a familiar length would satisfy it. The predicate is therefore
# the receipt FORM the log carries. The uuid is REQUIRED rather than the bare phrase, so
# prose ABOUT a missing id cannot satisfy the read (the prose-as-data class, n=405 cl 5).
#
# **TWO ACCEPTED FORMS, ONE PREDICATE** (ruling n=1087, #139). The thin trigger's log
# carries ONE OF TWO success forms, and only the deferred branch writes the `notification
# id` token — so a token-only predicate could never accept an immediate delivery, and it
# reported every one of them as a FAILED duty: permanent, and growing with each delivery.
# Reshaping the world was REJECTED (both forms are emitted by the DAEMON and the trigger
# only redirects its stdout, so it is not a kit change) — the predicate describes the world.
# The delivered form is the STRONGER receipt (it proves delivery; the deferred form proves
# acceptance only, delivery pending), so the leg was refusing the better half of its
# evidence. Order is strongest-first: a log carrying both forms reports the stronger fact.
#
# **NON-VACUITY RIDES A PROBE, NEVER A LOUD-FAIL-ON-ZERO** (ruling n=774 done-criteria).
# The live population of failed notifies is legitimately EMPTY on a quiet day, so an empty
# read here is a normal read and is PRINTED as one — the opposite call from the cron-thinness
# leg above, which fails loudly because its population is the rows this factory declares. The
# probe that drives a log carrying no receipt is what shows the leg can bite (#112's shape).
LOG_DIR = Path("/tmp")
# `<job-name>-<YYYYmmddTHHMMSS>.log` — the thin trigger's own redirect, nothing else.
NOTIFY_LOG_RE = re.compile(r"^(?P<job>.+)-(?P<stamp>\d{8}T\d{6})\.log$")
# The redirect a prompt DECLARES, by its stem (#163 half 2). Every pacemaker on this
# box writes `/tmp/<stem>-$(date ...).log` (one job escapes the `$` as `\$(date`), so
# the stem is the token between `/tmp/` and the timestamp EXPRESSION. Read from the
# prompt that OWNS the redirect rather than inferred from a filename, so a hand-typed
# label cannot hide a live surface in `retired`.
DECLARED_REDIRECT_RE = re.compile(r"/tmp/(?P<stem>[A-Za-z0-9._-]+?)-(?:\\?\$\(date)")
# The phrase a reader should look for when NO form matched (the deferred branch's token).
NOTIFY_RECEIPT_TOKEN = "notification id"
_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
# Each form is anchored on its PHRASE PLUS A UUID, so a log that merely MENTIONS a phrase is
# not a receipt. Strongest first: delivery proves the fact the leg exists to assert, while
# deferral proves only that the notify was accepted.
NOTIFY_RECEIPT_FORMS = (
    ("delivered", re.compile(r"\bdelivered to session\s+" + _UUID + r"\b")),
    ("deferred", re.compile(r"\bdeferred for session\s+" + _UUID + r"\b")),
)
# The deferred form's own id, quoted in the verdict so the excuse names the acceptance
# token rather than merely its kind.
NOTIFY_ID_RE = re.compile(r"\bnotification id\s+(" + _UUID + r")\b")


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
    """The FULL board: every state, no filter, so the reverse leg is sound.

    `comments` travels with it because one leg's population IS the comments (#223): a
    ruling posted as a board comment is the transition the ledger's `ruling` event
    declares, and a read that omitted comments could not see one at all — the leg would
    examine nothing and print the verdict of a leg that examined the population. The
    field is additive and the other legs ignore it, so the read stays ONE call.
    """
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
            "number,state,title,closedAt,comments",
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

# ---- the board-closed leg (issue #75, ruled at ledger n=496) -------------------------
#
# DIRECTION (3) OF THE STATE LAW: a CLOSED board item carrying NO close row is drift.
# NEITHER existing board leg can see it, and both are blind BY CONSTRUCTION rather than
# by accident: the intake leg's forward arm reads `open_issue_numbers` (state == "open"
# ONLY), so a closed item is never a candidate; the close leg iterates ROWS whose event is
# `close`, so a subject carrying no close row is never a candidate. The population must
# therefore come from the BOARD — a ledger walk cannot enumerate an item the ledger never
# mentions, and that asymmetry is the whole defect. Measured at ledger n=1876: 233 closed
# board items, 3 post-boundary and carrying no close row (#143, #172, #227).
#
# THE BOUNDARY IS READ, NEVER RE-TYPED. It is the close-board gate's own INVARIANT_LANDED,
# loaded from that gate — a second copy of an instant is a copy that goes stale silently,
# and a guard that re-types the value it guards has already stopped guarding.
#
# WHAT THIS LEG DOES NOT DO. It does not decide whether the missing row is a DEFECT or a
# QUESTION, because for direction (3) that question does not arise: ruling n=496 clause
# (5) settles it — "a board close with no close row IS the drift the law names, whoever
# closed it, and the REPAIR IS A CLOSE ROW -- not an exemption." The complete/incomplete
# split of clause (2) governs the OTHER direction (a landed subject the board still reads
# OPEN), which is not this dispatch's goal and is not silently claimed here.
#
# NOT RUN, NOT SILENT: an unreadable board never reaches this leg — `main` exits 2 before
# any leg is built — so the leg cannot report a clean sweep over a board it never read.
def board_closed_leg(issues: list[dict], rows: list[dict], *, gate=None,
                     read_at: str, predicate=None) -> dict:
    """The live board-closed leg: a post-boundary CLOSED item with NO close row (#75).

    Population: board items whose state is `closed` AND whose `closedAt` is at or after
    the close-board gate's own boundary (read from that gate, never re-typed) AND whose
    number no `close` row names. That is direction (3).

    The count travels as `closed_items_examined` and is printed on the leg's OWN line, so
    a green reads as "examined N, 0 problems" rather than being indistinguishable from
    "examined nothing" — and the items excluded as PRE-BOUNDARY are counted and printed
    too, because an exclusion that is not printed is indistinguishable from a miss. The
    read instant and the boundary the population was taken against travel with it: a count
    is meaningless without the predicate and the instant that produced it.
    """
    gate = gate or load_close_board_gate()
    predicate = predicate or load_predicate()
    token, boundary = gate.BOARD_TOKEN, gate.INVARIANT_LANDED
    try:
        bound = gate._parse_ts(boundary)
    except (ValueError, TypeError):
        bound = None

    # The close-row namespace, resolved the way `board_close_leg` resolves it -- the same
    # strict `#N` reference, so the two legs cannot disagree about which subject a row
    # names. A close row whose subject is not an issue reference is not a close row FOR an
    # issue, and this leg asserts only over issue references.
    closed_subjects: set[int] = set()
    for row in rows:
        if row.get("event") != "close":
            continue
        number = predicate.issue_reference(row.get("subject"))
        if number is not None:
            closed_subjects.add(number)

    problems: list[str] = []
    examined = 0
    pre_boundary = 0
    missing: list[int] = []
    for item in issues:
        if str(item.get("state", "")).strip().lower() != "closed":
            continue
        number = item.get("number")
        if not isinstance(number, int):
            continue
        try:
            closed_at = gate._parse_ts(item.get("closedAt"))
        except (ValueError, TypeError):
            closed_at = None
        if closed_at is None or bound is None or closed_at < bound:
            # A close that PREDATES the invariant is outside this population: the law
            # cannot require a row for an obligation that did not yet exist, and the
            # offline gate excuses those rows the same way. Counted, never dropped.
            pre_boundary += 1
            continue
        examined += 1
        if number in closed_subjects:
            continue
        missing.append(number)
        problems.append(
            f"#{number} is CLOSED on the board (closed {item.get('closedAt')}) with NO "
            f"close row naming it — a board close with no close row IS the drift the law "
            f"names, whoever closed it, and the repair is a close row (board read at "
            f"{read_at}, boundary {boundary})"
        )

    return {
        "name": "board-closed",
        "status": "ASSERTED",
        "problems": problems,
        "excused": [],
        "coverage": {
            "closed_items_examined": examined,
            "pre_boundary_closed_items": pre_boundary,
            "board_read_at": read_at,
            "declaration_token": token,
            "invariant_boundary": boundary,
            "items_without_close_row": missing,
        },
    }

# ---- the board-ruling leg (issue #223, ruled at ledger n=1596) -----------------------
#
# A ruling posted as a board comment leaves no `ruling` row, and NOTHING asked for one:
# `grep` for a reader of `event == "ruling"` across `tools/*.py` returned ZERO hits — the
# token occurred only at the event tuple and the authorization matrix. So the transition
# was authorized, written by convention, and skipped indefinitely with no surface noticing,
# which is the field-with-no-reader shape arriving on the WRITE side. Eight of one lane's
# rulings in a single session had no row; Triage's re-measurement put the class at NINE and
# corrected the filing's figure, because the population MOVES as lanes start stamping.
#
# THE HEADINGS ARE DECLARED HERE BECAUSE THE PREDICATE IS THE WHOLE MECHANISM, and it was
# MEASURED before it was written rather than chosen (Triage, ledger n=1597 — the numbers
# below are that measurement, not a guess):
#
#   * a comment that IS a ruling OPENS with one of these headings. A comment that merely
#     MENTIONS the word is not a ruling — and that distinction is the entire leg: the loose
#     form `--search "RULED in:comments"` returned **118** issues, an order of magnitude
#     over, because a filing saying "not ruled yet" scores as an instance.
#   * the class is NOT state-scoped: `--state open --search` returned a DIFFERENT set,
#     because four of the eight had since closed. So the read is the board WHOLE and the
#     heading test is the ONLY predicate that finds the population.
#
# The tokens are DECLARED, never inline at the comparison, so a factory whose board carries
# a different ruling heading changes ONE tuple and the leg follows — and so the value can be
# probed without executing the leg against a live board. Both forms are declared rather than
# normalised to one: the board carries both, and a normalisation would be a second predicate
# standing beside this one, which is the drift the tuple exists to prevent.
# ---- #243: WHICH ISSUE DOES A RULING GOVERN -----------------------------------------
#
# The leg built its `ruled` set with the SHARED predicate's `issue_reference`, whose
# pattern is the strictly numeric `^#(\d+)$`. That predicate answers "does this subject
# NAME AN ISSUE", and for its own gate a descriptive subject genuinely names none — so
# widening it would move that gate's population in a direction nobody asked for. This leg
# asks a DIFFERENT question ("which issue does this ruling GOVERN") and answers it with a
# resolver of its own over the ledger's real subject vocabulary.
#
# MEASURED at origin e249022 from the leg's own resolver: 214 ruling rows, 174 reachable,
# **40 unreachable (18.8%)** — the resolver could not EXPRESS the case, so `ruled` could
# hold at most 130 distinct issue numbers. Realized harm on one day's board: a cross-read
# called eight open issues unruled, FIVE of them (#77 #85 #133 #185 #188) carrying a ruling
# row the strict form returns None for — every one a re-dispatch of an item that already
# had its ruling, which is the "duplicate brief to a lane already holding the item" class.
#
# THE THREE ARMS, in the ruled order:
#   1. STRICT — the ruling's own subject is `#<n>`.
#   2. THE DISPATCH BRIDGE — a ruling is often stamped under a SLUG (`foreign-instrument-
#      coupling`) while the issue is filed a row later, so the bridge is: another row that
#      REFERENCES this ruling's `n` and itself names an issue. #85 is reachable ONLY this
#      way (ruling n=545 <- dispatch n=546, subject `#85`, detail "Ruling n=545"), and #77
#      through a BARE-number subject (n=516, subject `77`), which the strict form also
#      misses and which its own correction row n=518 complains about.
#   3. `governs=<n>` — an explicit token for a ruling that governs a concern rather than an
#      item, so a lane can declare the attribution instead of relying on a bridge.
#
# A ROW THAT RESOLVES TO NO ISSUE IS PRINTED, never silently dropped: a resolver that
# cannot place a row must say so, or the leg reports a smaller population than it examined.
RULING_GOVERNS_KEY = "governs="
_RULING_ISSUE_URL = re.compile(r"/issues/(\d+)\b")
_RULING_BARE_NUMBER = re.compile(r"^(\d+)$")


def issue_from_row(row: dict, predicate) -> int | None:
    """The issue a row names, leg-locally: `#N` subject, bare `N` subject, or an issue URL.

    DELIBERATELY NOT the shared predicate (#243, shape 1): `issue_reference` is strictly
    numeric by design and its own gate depends on that. This is the patrol's question, so
    it is answered here — and a bare number is accepted because the dispatch rows really do
    carry one (`n=516`, subject `77`), which is the form n=518 was written to correct.
    """
    subject = str(row.get("subject") or "").strip()
    number = predicate.issue_reference(subject)
    if number is not None:
        return number
    bare = _RULING_BARE_NUMBER.match(subject)
    if bare:
        return int(bare.group(1))
    url = _RULING_ISSUE_URL.search(str(row.get("detail") or ""))
    if url:
        return int(url.group(1))
    return None


def resolve_ruling_issue(ruling: dict, rows: list[dict], predicate) -> tuple[int | None, str]:
    """`(issue, arm)` for a ruling row — the arm NAMED so a resolution is auditable.

    `arm` is `"strict"`, `"declared"` (`governs=`), `"bridged"` or `"unbridgeable"`. The
    tier is reported rather than implied, the same discipline the canonicality ladder uses:
    a resolution that does not say how it was reached cannot be re-litigated when the
    vocabulary moves.
    """
    own = issue_from_row(ruling, predicate)
    if own is not None:
        return own, "strict"

    declared = re.search(rf"{re.escape(RULING_GOVERNS_KEY)}(\d+)", str(ruling.get("detail") or ""))
    if declared:
        return int(declared.group(1)), "declared"

    n = ruling.get("n")
    if n is not None:
        for other in rows:
            if other.get("n") == n:
                continue
            detail = str(other.get("detail") or "")
            if not re.search(rf"\bn={n}\b", detail):
                continue
            bridged = issue_from_row(other, predicate)
            if bridged is not None:
                return bridged, "bridged"

    return None, "unbridgeable"

RULING_HEADINGS = ("## RULED", "## RULING", "## Amendment")
"""The heads a ruling comment OPENS with — widened to the spellings the board uses (#245).

The tuple was `("## RULED", "## RULING")` and that predicate silently dropped three
ruling-style comments on two issues: `#133` (x2) and `#148` (x1), every one of them headed
`## Amendment`. `#133` was the sharp case — it read as unruled from the LEDGER
(`event="ruling"` returns nothing under any subject) AND from the BOARD (0 strict-headed
comments), while its two `## Amendment` comments ARE its ruling.

`## Amendment` is a live spelling used deliberately by this factory's own HQ, so the
widening is to the OBSERVED forms and nothing is backfilled — the three comments are not
rewritten to the canonical head.

THE BOUND IS A FLOOR, NOT A CEILING, and that is what the clause below answers. The
candidate set came from a text search for `## Amendment`, so a ruling headed with a
DIFFERENT word (`## DISPOSITION`, `## DECISION`) was never in it; widening to today's
spellings carries the same blindness forward one spelling. So the leg also PRINTS every
heading comment it did NOT match — a fourth spelling surfaces as a finding on the run that
first meets it, instead of being indistinguishable from absent.
"""

RULING_CANONICAL_HEADING = "## RULED"
"""The head the convention NAMES, so a lane writing a ruling converges rather than infers.

ENFORCED at the write path since #270. `tools/rule.py` posts the board comment and stamps
the `ruling` row in ONE invocation, and it REFUSES a body that does not open with this head
-- boundary-checked exactly as `_accepted_heading` below is, so the writer and the reader
cannot disagree about the accepted set. The tool IMPORTS this constant rather than
restating it: a second copy of the accepted openings is the drift class this factory files
repeatedly, so a widening here moves the writer with the reader in one edit.

THIS REVERSES THE PREMISE THIS DOCSTRING WAS WRITTEN UNDER, which held that the writer was
an agent typing `gh issue comment` with nothing on the path to hold it, so a "use this
head" rule would be unenforceable exactly where it matters -- the dead-text shape P29
removes. That premise is measured FALSE as of #270: `tools/rule.py` sits on that path, so
the head is a mechanism rather than dead text. The retired reading is named here rather
than silently deleted, because a docstring that simply changed its mind leaves the old
claim unaccounted for.

The leg's own unmatched-heading clause is NOT made redundant by the tool, which is why it
stays: a comment posted BY HAND still has no writer to refuse it. So the run still PRINTS
every heading comment it did not match -- a spelling that bypassed the tool surfaces as a
finding on the run that first meets it, instead of being indistinguishable from absent.
"""

_RULING_HEADING_LINE = re.compile(r"^(#{1,6})\s+(\S.*)$")

def _accepted_heading(head: str) -> bool:
    """Whether a heading line is one of the accepted forms, BOUNDARY-CHECKED.

    `str.startswith` on a tuple admits an EXTENSION: `## RULINGS — the ledger` starts with
    `## RULING`, so a different heading would be read as this one — the digit-extension
    class this factory has filed repeatedly. The character after the form must therefore
    not be alphanumeric. Measured over the live board: 0 headings extend an accepted form,
    so the check moves NO population today and exists so it cannot move one tomorrow.
    """
    for form in RULING_HEADINGS:
        if head.startswith(form):
            rest = head[len(form):]
            if not rest or not rest[0].isalnum():
                return True
    return False

def comment_heading(comment: dict) -> str | None:
    """The comment's FIRST LINE when that line is a markdown heading, else None.

    The first line only, after leading whitespace: the heading is the comment's opening,
    which is the same discriminator the ruling predicate uses. A heading further down is a
    section inside a comment, not the comment's own declaration.
    """
    body = str(comment.get("body") or "").lstrip()
    if not body:
        return None
    first = body.splitlines()[0].strip()
    return first if _RULING_HEADING_LINE.match(first) else None

def ruling_comment(issue: dict) -> dict | None:
    """The issue's ruling comment, or None when it carries none.

    The test is on the OPENING of the body, after leading whitespace, and it is the reason
    the leg can be mechanical: 118 issues mention the word, and a subset of those are
    filings that say the item is NOT ruled. Opening-only admits the ruling and refuses the
    mention, with no second source of truth.
    """
    for comment in issue.get("comments") or []:
        if not isinstance(comment, dict):
            continue
        head = comment_heading(comment)
        if head is not None and _accepted_heading(head):
            return comment
    return None

def unmatched_heading_comments(issue: dict) -> list[str]:
    """Every heading the ruling predicate did NOT match — the clause that keeps it honest.

    Widening the alternation alone reproduces the defect one spelling later: a new head
    arrives, matches nothing, and is NOT EXAMINED, which is indistinguishable from absent.
    So the leg names what it could not place, per issue, and the count travels beside the
    verdict. A ruling that used a spelling nobody has seen yet shows up here on the run
    that first meets it rather than being silently dropped.

    This is the same obligation #223's direction-1 remedy carries and #231's stale basis
    lacked: a predicate that cannot place an item must SAY SO, never report a smaller
    population than it examined.
    """
    out: list[str] = []
    for comment in issue.get("comments") or []:
        if not isinstance(comment, dict):
            continue
        head = comment_heading(comment)
        if head is None or _accepted_heading(head):
            continue
        out.append(head)
    return out

def board_ruling_leg(issues: list[dict], rows: list[dict], *, read_at: str,
                     predicate=None) -> dict:
    """The live board-ruling leg: a ruling comment with no `ruling` row is reported (#223).

    Population: every board issue carrying a ruling comment — derived AT RUN TIME from the
    board the read returned, never a literal, so the count moves with the board and cannot
    go stale in the code. Returned as `rulings_issued` and printed beside the
    verdict, so a clean run reads as "examined N, 0 problems" rather than being
    indistinguishable from "examined nothing" — the leg that examined nothing has reported
    nothing, never a clean HOLD.

    The read instant travels with it: the board is LIVE state, so this is a property of the
    INSTANT and is REPORTED, never folded into the correctness verdict.

    NO BACKFILL, by law rather than by omission: a `ruling` row written after the fact is a
    falsified record, so a ruling that was never stamped is a FINDING the leg keeps printing,
    not one it repairs. The population it examines is stated so tonight's instances are
    visible as instances rather than silently passed over.
    """
    predicate = predicate or load_predicate()

    ruled: set[int] = set()
    arms = {"strict": 0, "declared": 0, "bridged": 0}
    unbridgeable: list[dict] = []
    for row in rows:
        if row.get("event") != "ruling":
            continue
        number, arm = resolve_ruling_issue(row, rows, predicate)
        if number is not None:
            ruled.add(number)
            arms[arm] = arms.get(arm, 0) + 1
        else:
            # PRINTED, never dropped: a resolver that cannot place a row must say so, or
            # the leg reports a smaller population than it examined (#243 clause 2).
            unbridgeable.append({"n": row.get("n"), "subject": str(row.get("subject") or "")})

    problems: list[str] = []
    examined = 0
    unmatched: list[dict] = []
    for issue in issues:
        number = issue.get("number")
        if not isinstance(number, int):
            continue
        # The clause that keeps the alternation honest (#245): every heading comment the
        # predicate did NOT accept is NAMED, per issue. It is collected over the WHOLE
        # board, not only over the issues that carried an accepted head — a novel spelling
        # is precisely the case where no accepted head exists, so scoping the collection to
        # the ruled population would exclude the only population it is for.
        for head in unmatched_heading_comments(issue):
            unmatched.append({"issue": number, "head": head})
        if ruling_comment(issue) is None:
            continue
        examined += 1
        if number in ruled:
            continue
        problems.append(
            f"#{number} carries a ruling comment on the board but the ledger holds no "
            f"`ruling` row for it (board read at {read_at}) — the ruling's content is on "
            f"the board, but every other row cites a ruling by `n`, and a ruling with no "
            f"row has no `n` for a reader to resolve"
        )

    return {
        "name": "board-ruling",
        "status": "ASSERTED",
        "problems": problems,
        "excused": [],
        "coverage": {
            "rulings_issued": examined,
            "issues_read": len(issues),
            "board_read_at": read_at,
            "headings": list(RULING_HEADINGS),
            "canonical_heading": RULING_CANONICAL_HEADING,
            "unmatched_heads_examined": len(unmatched),
            "unmatched_heads": unmatched,
            "rulings_read": len(ruled) + len(unbridgeable),
            "rulings_resolved": len(ruled),
            "rulings_unbridgeable": len(unbridgeable),
            "resolution_arms": arms,
            "unbridgeable_rows": unbridgeable,
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


def git_common_dir(repo: Path = REPO) -> Path | None:
    """This checkout's GIT COMMON DIR, or None when it cannot be read (#242).

    THE PATH IS THE WRONG IDENTITY, and the remedy this factory prescribes for a diverged
    tree — "run from a clean worktree at origin/main" — is exactly the move that exposes
    it. A LINKED WORKTREE resolves to its own path, so an attribution keyed on the checkout
    matches no record and the patrol silently judges nobody: measured in a worktree at
    origin e41d934, one call over a real 42-row cron population, `cron-thinness` read
    "0 attributed of 42, 42 unattributed, 0 problems" and `duty-receipt` concluded "no
    enabled row this factory declares carries a receipt_subject:" — a FALSE CONCLUSION over
    an empty population, while the main checkout reported 2 real problems in the same
    minute. The common dir is the repository's identity and every worktree shares it.

    THE RELATIVE FORM IS THE TRAP, and it is why this is a named function with a probe.
    From the MAIN checkout, `git rev-parse --git-common-dir` prints the RELATIVE string
    ".git", so `Path(raw).resolve()` resolves against the CALLER's cwd — measured: from
    /tmp it yields "/tmp/.git", matching nothing, which is the same empty result the defect
    produces while looking like a fix. The path must be joined to the repo FIRST:
    `(repo / raw).resolve()` is correct from both a main checkout and a worktree.
    (`--path-format=absolute` also works, but needs git >= 2.33; the join is version-safe
    and costs nothing.)
    """
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--git-common-dir"],
        capture_output=True, text=True,
    )
    raw = proc.stdout.strip()
    if proc.returncode != 0 or not raw:
        return None
    return (Path(repo) / raw).resolve()


def declared_prefixes(repo: Path = REPO) -> list[str]:
    """This factory's declared `job_prefixes`, read from the fleet manifest.

    Ownership is by the manifest's DECLARATION, never by the home a row happens to sit
    in: all twelve ai-antispam rows sit in the OPS home, so a profile-scoped read answers
    a narrower question than the one it names (#102). An empty return is reported by the
    caller as an unattributable population, never read as a clean one.

    THE MATCH IS ON THE REPOSITORY, NOT THE CHECKOUT (#242): the declared repo and this
    tree are both resolved to their GIT COMMON DIR, so a linked worktree — the very move
    this factory prescribes for a diverged tree — is this factory rather than nobody.
    """
    registry = load_module("oc_registry", REGISTRY)
    manifest = registry.load_fleet_manifest()
    want = git_common_dir(repo)
    for record in manifest.get("factories", []):
        declared = record.get("repo")
        if not isinstance(declared, str):
            continue
        if want is not None and git_common_dir(Path(declared)) == want:
            return [str(p) for p in record.get("job_prefixes", [])]
        # The common dir is the authority; the plain path is kept as a SECOND chance for a
        # declared repo that is not a git tree at all (a member not yet cloned, say), where
        # git_common_dir returns None on both sides and would otherwise match nothing.
        if want is None and str(Path(declared).resolve()) == str(repo.resolve()):
            return [str(p) for p in record.get("job_prefixes", [])]
    return []


def declared_slug(repo: Path = REPO) -> str:
    """This factory's `slug`, read from the fleet manifest — or '' when undeclared.

    The match is on the REPOSITORY, resolved to its git common dir, exactly as
    `declared_prefixes` matches — so a linked worktree is this factory rather than nobody.
    The slug is what the fragment file is named for, and the fragment is where a role is
    mapped to a topic; a slug guessed from the git remote would be `owner/repo`, which names
    no fragment at all.
    """
    registry = load_module("oc_registry", REGISTRY)
    try:
        manifest = registry.load_fleet_manifest()
    except registry.FleetManifestError:
        # AN ABSENT OR UNREADABLE MANIFEST IS A STATE, NOT A CRASH (#199's class, one surface
        # over). The tree the kit ships carries `registry/fleet.example.json` and no manifest
        # at all, so this resolver IS reached from the shipped tree -- and the report path it
        # feeds must render the empty answer as NOT RUN with its reason, never raise out of
        # `main()`. `tests/test_patrol_host_state.py`'s
        # `test_an_absent_manifest_RENDERS_as_NOT_RUN_never_a_traceback` is the arm that
        # caught the traceback this guard removes.
        return ""
    want = git_common_dir(repo)
    for record in manifest.get("factories", []):
        declared = record.get("repo")
        if not isinstance(declared, str):
            continue
        if want is not None and git_common_dir(Path(declared)) == want:
            return str(record.get("slug") or "")
        if want is None and str(Path(declared).resolve()) == str(repo.resolve()):
            return str(record.get("slug") or "")
    return ""

def no_prefixes_leg(name: str, *, population: int, unit: str, read_at: str,
                    read_count: int) -> dict:
    """A cron-consuming leg this factory cannot attribute ANY row for — NOT RUN (#242).

    This is the second half of the #242 repair and it is not an alternative to the first.
    The legs already carry the discriminating counter (`rows_unattributed=42`,
    `logs_unattributed=104`, `jobs_unattributed=42`), and `declared_prefixes`' own
    docstring already obliges its caller: "An empty return is reported by the caller as an
    unattributable population, never read as a clean one." One caller, three call sites,
    zero compliance — so an empty prefix set produced a leg that JUDGED NOTHING and
    printed `ASSERTED ... 0 problems`, and in the duty-receipt case a positive FALSE
    CONCLUSION about the box.

    A leg that examined nothing has reported nothing, never a clean HOLD: the status is
    NOT RUN, the reason names the manifest and the count, and the population travels in
    the coverage so the unattributed rows are visible rather than absent.
    """
    return {
        "name": name,
        "status": "NOT RUN",
        "problems": [],
        "excused": [],
        "coverage": {
            "reason": (
                f"this checkout resolves to no factory the fleet manifest declares, so no "
                f"job can be attributed to it — {population} of {read_count} {unit} read "
                f"are UNATTRIBUTED and NONE were judged. A clean box is NOT what this "
                f"means: it means the attribution could not be made (board #242)"
            ),
            unit.replace(" ", "_"): read_count,
            f"unattributed_{unit.split()[0]}": population,
            "read_at": read_at,
            "prefixes": [],
        },
    }


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


def embedded_law_content(prompt: str) -> tuple[str, str]:
    """(embedded instant, bare date) for one prompt — at most one of them is non-empty.

    The two are RETURNED APART rather than folded into one verdict, because they are
    different findings: an instant is drift-prone STATE and is judged, while a bare date is
    a citation of the past and is only REPORTED. Collapsing them would make the citation
    indistinguishable from the state, which is the false positive this class measured on
    the box's own best-shaped row (whose bare date sits in a
    rationale explaining why its prompt is THIN).
    """
    text = prompt or ""
    instant = EMBEDDED_INSTANT_RE.search(text)
    if instant:
        return instant.group(0), ""
    date = BARE_DATE_RE.search(text)
    return "", (date.group(0) if date else "")

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
    if not prefixes:
        return no_prefixes_leg("cron-thinness", population=len(rows), unit="row(s)",
                               read_at=read_at, read_count=len(rows))
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

    # EACH ATTRIBUTED ROW'S CURRENT DELIVERY PATH, named (#148, ruling n=1169 criteria 3/4).
    # A class-gate over a list can report that a class EXISTS and repairs nothing, and a
    # COUNT is a fact about a population while a repairer needs an OBJECT. So the route every
    # attributed row carries TODAY is read and NAMED here, on every scheduled run: a class-1
    # row (`unbaked-target`) is named with its class rather than folded into a number, and a
    # row that regresses into that class is visible at the next fire. This asserts the state
    # READ — never a predicted future failure, because a row's own history is not a forecast.
    attributed_routes = [
        {
            "name": str(row.get("name") or ""),
            "route": predicate.row_wake(row),
            "deliver_to": str(row.get("deliver_to") or ""),
            "home": str(row.get("home") or ""),
        }
        for row in attributed
    ]

    # THE EMBEDDED-LAW-CONTENT CLASS IS SCANNED OVER EVERY ROW READ, not only the
    # attributed ones, and that scope is the point: the class is a property of the PROMPT,
    # and the box's live instances sit on OTHER factories' rows (measured 2026-09-27T03:4xZ:
    # all five in the ops home, under prefixes this factory does not declare). A per-factory
    # scan would see none of them and would report a clean verdict over the class it was
    # built to catch — the #170/#177 family, a predicate that cannot see its own population.
    # Rows this factory OWNS are JUDGED; rows it does not are NAMED and reported, the same
    # split the unattributed population already uses, because a box-wide RED over another
    # factory's rows would fire on rows this factory has no authority over (#101).
    #
    # The declaring factory is read from the manifest, never guessed from the name: a name
    # is not an address, and the manifest is what DECLARES ownership. A manifest that cannot
    # be read yields {} and each finding then names the HOME it was read from instead of
    # inventing an owner.
    try:
        declaring = dict(load_module("oc_registry", REGISTRY).NAME_PREFIXES)
    except Exception:
        declaring = {}

    def _declares(name: str) -> str:
        for slug, pref in declaring.items():
            if any(name.startswith(p) for p in pref):
                return slug
        return ""

    law_content: list[dict] = []
    dated_only: list[dict] = []
    for row in rows:
        row_name = str(row.get("name") or "")
        instant, bare = embedded_law_content(str(row.get("prompt") or ""))
        if instant:
            law_content.append({"name": row_name, "home": str(row.get("home") or ""),
                                "instant": instant, "owner": _declares(row_name)})
        elif bare:
            dated_only.append({"name": row_name, "home": str(row.get("home") or ""),
                               "date": bare, "owner": _declares(row_name)})

    owned = {str(r.get("name") or "") for r in attributed}
    for entry in law_content:
        if entry["name"] not in owned:
            continue
        problems.append(
            f"{entry['name']}: its prompt embeds drift-prone law content — the instant "
            f"{entry['instant']} is a boundary/window/epoch the law owns, so the prompt is "
            f"a COPY that drifts the moment the law moves. P7/P28: a cron prompt is a thin "
            f"POINTER to the law, never the law itself (#178, ruling n=1230). Repairer: "
            f"this factory. Move the state into the law and have the prompt read it, or "
            f"drop it where the pre-flight command already derives it"
        )

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
            # The embedded-law-content class, NAMED — never a bare count, because a count
            # cannot be dispatched, claimed or closed while a named row can be all three
            # (#148's ruling, applied here). `rows_scanned` is printed beside it so a clean
            # verdict is distinguishable from one that examined nothing.
            "rows_scanned": len(rows),
            "law_content_rows": law_content,
            "dated_not_boundary_rows": dated_only,
            # #148's scheduled check: the CURRENT delivery path of every attributed row,
            # named per row. Printed every run, so the state is asserted by the run rather
            # than predicted by a plan (ruling n=1169 criterion 3).
            "attributed_routes": attributed_routes,
        },
    }


# --- the pacemaker-presence leg (#315) -----------------------------------------
#
# SKILL.md section 6 names every periodic process owner (Surveys, Triage, HQ) as owing an
# active thin cron pacemaker waking its session UUID. The thinness leg above judges the
# SHAPE of the rows that EXIST; it cannot see a row that does not exist, which is exactly
# why deleting `factory-hq-pacemaker` restored board #253 silently — a predicate over a
# list of rows has no way to miss one that was removed.
#
# The declaration is INDEPENDENT of the table this leg judges: WHO owes a pacemaker is read
# from the canonical process register (`docs/processes.md`, section 3), a versioned file,
# while the live `cron_jobs` table is asked only whether a wake exists. A leg whose expected
# state came from the live table would be self-consistent and would prove nothing (rule 7).
PRESENCE_REGISTER = REPO / "docs" / "processes.md"
FACTORY_FRAGMENT_DIR = REPO / "registry" / "factories"

def owner_sessions(register_text: str, fragment: dict | None, bindings: list[dict],
                   slug: str, *, registry=None, predicate=None
                   ) -> tuple[list[tuple[str, str]], list[str]]:
    """([(role, session_uuid)], notes) for the register's declared owners.

    The declaration is the REGISTER's (who owes a pacemaker); the factory fragment's `lanes`
    map a role to a topic, and the live bindings resolve that topic to a session. `notes`
    carries the CAUSE of an unresolved owner — a role the fragment does not declare, or a
    lane the bindings cannot place — so the coverage can say WHY, while the PROBLEM is left
    to the pure predicate (a single source for the verdict, never two).

    An owner that cannot be resolved travels as uuid "" rather than being dropped: an owner
    dropped here would be an owner silently excused, which is the failure this leg exists to
    catch, committed by the leg itself.
    """
    registry = registry or load_module("oc_registry", REGISTRY)
    predicate = predicate or load_module("cron_thinness_predicate",
                                         CRON_THINNESS_PREDICATE)
    declared = predicate.declared_periodic_owners(register_text)
    by_role: dict[str, dict] = {}
    for lane in ((fragment or {}).get("lanes") or []):
        role = str(lane.get("role") or "").strip().lower()
        if role and role not in by_role:
            by_role[role] = lane
    chat_id = registry.FACTORY_CHATS.get(slug) if slug else None
    owners: list[tuple[str, str]] = []
    notes: list[str] = []
    for name in declared:
        key = name.strip().lower()
        lane = by_role.get(key)
        if lane is None:
            owners.append((name, ""))
            notes.append(
                f"{name}: no lane with role {key!r} in this factory's fragment "
                f"({slug or 'unknown slug'})"
            )
            continue
        resolved = registry.resolve_lane(lane, bindings, {}, chat_id=chat_id)
        session = str(resolved.get("session_id") or "")
        owners.append((name, session))
        if not session:
            notes.append(
                f"{name}: declared lane (thread {lane.get('thread_id')}) resolves to no "
                f"live session — status {resolved.get('status')!r}"
            )
    return owners, notes

def pacemaker_presence_leg(rows: list[dict], bindings: list[dict],
                           register_text: str | None, fragment: dict | None, *,
                           read_at: str, slug: str = "", prefixes: list[str] | None = None,
                           homes_read: list[str] | None = None,
                           unreached: list[str] | None = None,
                           registry=None, predicate=None,
                           register_path: Path | None = None,
                           not_run_reason: str = "") -> dict:
    """The pacemaker-presence leg: every declared periodic owner must have an inbound wake.

    FAIL-OPEN, and the reason is PRINTED. An unreadable register, an unreadable cron table or
    an unreadable binding set is NOT RUN with the reason — never a clean read, because a
    check that could not read its input has verified nothing (#242). A leg that examined zero
    owners prints that count beside its verdict for the same reason.

    The rows judged are THIS factory's own (attributed by the manifest's declared prefixes),
    the same population the thinness leg judges — an owner of this factory is woken by this
    factory's pacemakers, and another factory's rows are its own concern (#101).
    """
    leg_name = "pacemaker-presence"
    register_path = register_path or PRESENCE_REGISTER
    if not_run_reason:
        return {
            "name": leg_name,
            "status": "NOT RUN",
            "problems": [],
            "excused": [],
            "coverage": {
                "reason": not_run_reason,
                "register": str(register_path),
                "owners_declared": 0,
                "read_at": read_at,
            },
        }
    if register_text is None:
        try:
            register_text = register_path.read_text(encoding="utf-8")
        except OSError as exc:
            return {
                "name": leg_name,
                "status": "NOT RUN",
                "problems": [],
                "excused": [],
                "coverage": {
                    "reason": (
                        f"the process register {register_path} could not be read ({exc}), so "
                        f"the DECLARATION of who owes a pacemaker is unavailable — a check "
                        f"that cannot read its independent declaration verifies nothing"
                    ),
                    "register": str(register_path),
                    "owners_declared": 0,
                    "read_at": read_at,
                },
            }
    predicate = predicate or load_module("cron_thinness_predicate",
                                         CRON_THINNESS_PREDICATE)
    owners, notes = owner_sessions(register_text, fragment, bindings, slug,
                                   registry=registry, predicate=predicate)

    if prefixes:
        judged, unattributed = attribute_rows(rows, prefixes)
    else:
        judged, unattributed = list(rows), []
    if not judged:
        return {
            "name": leg_name,
            "status": "NOT RUN",
            "problems": [],
            "excused": [],
            "coverage": {
                "reason": (
                    f"no enabled cron row attributed to this factory — {len(rows)} row(s) "
                    f"read across {len(homes_read or [])} home(s) with declared prefixes "
                    f"{prefixes!r}, so the population came back EMPTY and presence was never "
                    f"judged; a clean verdict over an examined-nothing read is not a verdict "
                    f"(#242)"
                    + (f"; homes UNREACHED: {list(unreached or [])}" if unreached else "")
                ),
                "register": str(register_path),
                "owners_declared": len(owners),
                "owners": [],
                "unattributed_rows": len(unattributed),
                "unreached_homes": list(unreached or []),
                "read_at": read_at,
            },
        }

    problems, population = predicate.pacemaker_presence_problems(owners, judged)
    return {
        "name": leg_name,
        "status": "ASSERTED",
        "problems": problems,
        "excused": [],
        "coverage": {
            "register": str(register_path),
            "owners_declared": len(owners),
            "rows_judged": len(judged),
            "unattributed_rows": len(unattributed),
            "homes_read": len(homes_read or []),
            "unreached_homes": list(unreached or []),
            "owners": population,
            "resolution_notes": notes,
            "read_at": read_at,
        },
    }

def read_notify_receipt(text: str) -> str | None:
    """The KIND of receipt `text` carries, or None — one predicate, two accepted forms.

    `"delivered"` proves the notify DELIVERED; `"deferred"` proves only that it was
    ACCEPTED, delivery pending. A bool could not say which fact was found and the verdict
    must say, because they mean different things to a reader (#139, ruling n=1087).

    The uuid is required on purpose. A log whose only line is "no notification id was
    recorded" carries the phrase and must NOT satisfy the read, because a field prose can
    SATISFY is the class ruled at n=405 clause 5.
    """
    for kind, pattern in NOTIFY_RECEIPT_FORMS:
        if pattern.search(text):
            return kind
    return None

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

      - `logs_matched` — judged, because a live row this factory declares owns the name
        OR declares, in its own prompt, the redirect stem the log carries (#163 half 2);
      - `retired_logs` — this factory's prefix with no enabled row owning the name AND no
        enabled row's prompt declaring that redirect stem: history, never judged. The
        PREDICATE is printed beside the bucket, so "no retired logs" and "a bucket that
        cannot see one" are never the same output;
      - `unattributed_logs` — nobody here declares it: another factory's law (#101, n=610).

    A log that EXISTS and cannot be read is a PROBLEM, never an absence — a declared surface
    that defeats the read is the #69 clause (e) shape. An absent log DIRECTORY is a NOT RUN
    carrying its reason and no problem: the surface is a constant of this tool rather than
    factory data, and a box with no thin triggers yet has nothing to judge.

    FOUR CLASSES, and only ONE is a failed duty (#139, ruling n=1087): `delivered` and
    `deferred` are both receipts and are EXCUSED with the kind named (they are different
    facts — one proves delivery, the other proves acceptance); a log with NO OUTPUT was
    never attempted and is REPORTED, never judged; and a log with output but no receipt
    form is the single class this leg exists to surface.

    ZERO MATCHED LOGS IS NOT A FAILURE HERE (ruling n=774 done-criteria). This population is
    legitimately empty on a quiet day, so an empty read is PRINTED and never gated — the
    opposite call from the cron-thinness leg, whose population is the rows the factory
    declares and which therefore does fail loudly. Non-vacuity here is carried by the probe.
    """
    if not prefixes:
        logs = sorted(p for p in log_dir.glob("*.log")) if log_dir.is_dir() else []
        return no_prefixes_leg("notify-receipt", population=len(logs), unit="log(s)",
                               read_at=read_at, read_count=len(logs))
    attributed, _ = attribute_rows(rows, prefixes)
    live = {str(row.get("name") or ""): row for row in attributed}
    # The redirect each ENABLED row's own prompt declares, keyed by the stem its log would
    # carry (#163 half 2). Built here so the bucket below can ask the question the filename
    # parse cannot: is this stem declared by a LIVE row even though it is not its NAME?
    declared_stem: dict[str, dict] = {}
    for row in attributed:
        for stem in declared_log_stems(str(row.get("prompt") or "")):
            declared_stem.setdefault(stem, row)
    matched, not_run = notify_logs(log_dir)
    problems: list[str] = []
    excused: list[str] = []
    judged: list[dict] = []
    retired: list[dict] = []
    foreign: list[dict] = []
    redeclared: list[dict] = []
    # The FOURTH class's sibling (#139): a log with no output at all is a notify that was
    # never ATTEMPTED, and judging it as a failed duty made a permanent false positive out
    # of a run that was orphaned before it ever reached its notify. Reported, never a problem.
    not_attempted: list[dict] = []
    for name, path in matched:
        if not prefixes or not any(name.startswith(prefix) for prefix in prefixes):
            foreign.append({"job": name, "path": str(path)})
            continue
        row = live.get(name)
        if row is None:
            # Not the row's NAME — but a live row may DECLARE this stem in its own prompt.
            # Filing it as history there is the defect: the log never enters the judged
            # population, so the one leg built to catch a failed notify reports it clean.
            row = declared_stem.get(name)
            if row is None:
                retired.append({"job": name, "path": str(path)})
                continue
            redeclared.append({
                "job": name,
                "path": str(path),
                "row": str(row.get("name") or ""),
            })
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            problems.append(
                f"{name}: {path} exists and could not be read ({exc}) — a surface that "
                f"defeats the read is a defect, never an absence"
            )
            continue
        kind = read_notify_receipt(text)
        if kind:
            id_match = NOTIFY_ID_RE.search(text)
            detail = f", id {id_match.group(1)}" if kind == "deferred" and id_match else ""
            meaning = ("the notify was DELIVERED" if kind == "delivered"
                       else "the notify was ACCEPTED; delivery is pending")
            excused.append(f"{name}: {path.name} carries a receipt ({kind}{detail}) — {meaning}")
            continue
        if not text.strip():
            not_attempted.append({
                "job": name,
                "id": str(row.get("id") or ""),
                "path": str(path),
            })
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
            f"receipt — {path} carries neither success form ('delivered to session <uuid>' "
            f"/ 'deferred for session <uuid>') nor any output at all; failure line: "
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
            "logs_not_attempted": len(not_attempted),
            "not_attempted_logs": not_attempted,
            "logs_retired": len(retired),
            "logs_attributed_by_redirect": len(redeclared),
            "logs_unattributed": len(foreign),
            "retired_logs": retired,
            "attributed_by_redirect": redeclared,
            # The bucket's own PREDICATE, printed beside its population: a clean bucket and
            # one that cannot see a member must never render the same (#163 half 2 (b)).
            "retired_predicate": (
                "log stem names no enabled row this factory declares, AND no such row's "
                "own prompt declares that redirect stem"
            ),
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
# **THE RECEIPT MUST DECLARE ITS COMPLETION — a subject match is not a receipt.** The row
# the duty's lane appends carries `duty=completed|failed|skipped` in its canonical trailer,
# read through the SHARED positional predicate (`field_predicate.declared_duty`), never a
# private scan. This is the leg's second correction and it closes a measured false clean:
# the first version accepted ANY ledger row whose subject matched the round, so
# `registry-attest-2026-09-25` was certified by n=1003 — the DISPATCH record, appended
# 06:08:53Z, before the round completed at ~06:14Z — while the real completion row (n=1007)
# sits under a different subject. Requiring the declaration rejects a pre-completion row
# AND makes silence unable to certify, which is the same property section 11 states for the
# declaration itself: the omission is the failure the mechanism cannot see.
#
# **THE KEY IS `duty`, NOT `outcome`, and the distinction is a property of the metric.** A
# run row declaring `outcome=` ENTERS `first_pass_yield_population` (`tools/audit.py`), and
# a duty receipt is SELECTION-BIASED — it is written by a lane that completed a duty — so
# receipts under `outcome` would add near-certain successes to the yield's denominator and
# make the ratio structurally optimistic. One number would then answer two questions, which
# is the #143 class. The yield and its published population are untouched by this leg.
#
# **NON-VACUITY RIDES A PROBE, NEVER A LOUD-FAIL-ON-ZERO.** A box whose duty round
# completed cleanly has an empty problem list, so an empty read here is a normal read and
# is PRINTED as one. The probe that drives a fired round with no receipt is what shows the
# leg can bite (#112's shape).
RECEIPT_DECL_RE = re.compile(r"^receipt_subject:\s*(\S+)\s*$", re.MULTILINE)
FRAGMENT_STORE = REPO / "registry" / "factories"
# The `duty` values that mean the round did NOT complete. The domain itself is DECLARED
# beside the shared reader (`tools/field_predicate.py::DUTY_DOMAIN`) and read from there,
# never retyped: one field, one predicate (SKILL.md section 11). This tuple is the SUBSET
# that is a finding rather than a completion, and it is the leg's question, not the
# writer's vocabulary -- which is why it lives here and the domain lives there.
DUTY_INCOMPLETE_VALUES = ("failed", "skipped")
# The invariant whose declared instant is this leg's forward bound (#175). The KEY is
# a constant here; the INSTANT is factory data in docs/ledger-invariants.json and is
# never written into this file, because a bootstrapped factory's history is its own:
# a leg that hardcoded this factory's date would judge a tree it does not describe.
DUTY_RECEIPT_BOUNDARY_KEY = "duty_receipt_declared"

def declared_receipt_stem(prompt: str) -> str | None:
    """The receipt stem this row declares, or None — the line `receipt_subject: <stem>`.

    Anchored to a whole line so a sentence that merely MENTIONS the declaration cannot
    satisfy it: prose about a field is not a declaration of one (the class ruled at
    n=405 clause 5).
    """
    found = RECEIPT_DECL_RE.search(prompt or "")
    return found.group(1) if found else None

def declared_log_stems(prompt: str) -> tuple[str, ...]:
    """The redirect STEMS a prompt declares — `/tmp/<stem>-$(date ...)`, in order, deduped.

    This is the attribution half of #163 half 2. The leg's first key was the log's FILENAME
    stem looked up among the enabled rows' NAMES, and that parse cannot see a hand-typed
    label: the job `factory-triage-patrol` wrote `/tmp/factory-triage-6h-<ts>.log`, the stem
    `factory-triage-6h` matched no row, and every one of those logs landed in `retired_logs`
    as history — a SILENT exclusion of exactly the surface the leg exists to judge. Reading
    the stem the prompt itself declares makes a live surface visible even when its label
    does not equal its job name.
    """
    seen: list[str] = []
    for found in DECLARED_REDIRECT_RE.finditer(prompt or ""):
        stem = found.group("stem")
        if stem not in seen:
            seen.append(stem)
    return tuple(seen)


def receipt_subject_matches(subject: str, stem: str, round_date: str) -> bool:
    """True when `subject` names this round — a BOUNDARY-CHECKED PREFIX, not equality.

    Equality was the leg's first key, and it could not express the shapes it governs: the
    round is a UTC DATE (`receipt_round`), while a duty may write an hour-bearing subject
    (`patrol-verify-2026-09-25T06`) or a decorated one
    (`registry-attest-2026-09-25-writeback`), so four of six pacemakers could not declare
    at all — and declaring where the key cannot match is worse than silence, because it
    produces a false MISSING on every round (#159).

    WHAT IT DOES NOT REACH, and the law states it in terms (SKILL.md v0.1.22): a subject
    that puts words BETWEEN the stem and the round does not name the round and is NOT a
    receipt, so the leg reads MISSING — loud, and true. A false MISSING costs one look; a
    false CLEAN is silent, which is the failure this leg exists to catch.

    THE BOUNDARY GUARD is what keeps the widening safe. A bare `startswith` would let
    `...-2026-09-25` match `...-2026-09-250`, a DIFFERENT date whose subject merely extends
    the digits of this one — so the character after the prefix must not be a digit. Any
    other continuation is a decoration of this round (`T06`, `-writeback`, or nothing at
    all), which is exactly what the prefix is for.
    """
    prefix = f"{stem}-{round_date}"
    if not str(subject).startswith(prefix):
        return False
    rest = str(subject)[len(prefix):]
    return not rest[:1].isdigit()

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

_BOUNDARY_READER = None


def boundary_reader():
    """The boundary reader, loaded ONCE and cached (#175).

    `load_module` RE-EXECUTES the module on every call, and this leg reaches the reader
    once per declared round, so an uncached accessor would re-import the closure for
    every row on a box carrying several factories. Loaded by PATH through the same
    accessor the leg uses, so there is still exactly one way to reach it.
    """
    global _BOUNDARY_READER
    if _BOUNDARY_READER is None:
        _BOUNDARY_READER = load_module("ledger_boundary", LEDGER_BOUNDARY)
    return _BOUNDARY_READER


def duty_receipt_bound(repo: Path) -> tuple[dt.datetime | None, str, str]:
    """The forward bound this leg judges against, as `(instant, text, refusal)`.

    Read through the ONE boundary reader (`tests/ledger_boundary.py`), so the leg and
    the boundary-reading gates cannot disagree about what this factory declared — one
    field, one predicate (SKILL.md section 11).

    The reader's own policy is absent SKIPS / malformed FAILS; this leg maps BOTH onto
    a REFUSAL, and that is deliberate. For a gate, an absent declaration is a legitimate
    state (the invariant has not been adopted). For this leg it is not: judging every
    fired round against no bound is precisely the unbounded read #175 exists to stop, so
    a tree that declares nothing is TOLD so rather than shown a clean run. The
    distinction survives in the WORDING, which is what a reader needs in order to act.
    """
    try:
        reader = boundary_reader()
    except Exception as exc:  # noqa: BLE001 — any load failure is the same refusal
        return None, "", (
            f"the boundary reader cannot be loaded from {LEDGER_BOUNDARY} ({exc}) — "
            f"REFUSED: without it `{DUTY_RECEIPT_BOUNDARY_KEY}` cannot be read, and a "
            f"leg that judges every round against a bound it could not read is the "
            f"unbounded behaviour #175 exists to stop"
        )
    try:
        instant, text = reader.declared_boundary(repo, DUTY_RECEIPT_BOUNDARY_KEY)
    except reader.SkipGate as exc:
        return None, "", (
            f"`{DUTY_RECEIPT_BOUNDARY_KEY}` is UNDECLARED in this tree ({exc}) — "
            f"REFUSED: a round fired before a convention could not have carried its "
            f"receipt, and this tree has not declared when that convention began, so "
            f"no round is judged rather than every round being judged unbounded"
        )
    except reader.GateError as exc:
        return None, "", (
            f"`{DUTY_RECEIPT_BOUNDARY_KEY}` is declared in this tree but cannot be "
            f"read: {'; '.join(str(p) for p in exc.problems)} — REFUSED: a malformed "
            f"bound is a DEFECT, never a licence to judge unbounded"
        )
    return instant, text, ""

def duty_receipt_leg(rows: list[dict], homes_read: list[str], unreached: list[str],
                     prefixes: list[str], ledger_rows: list[dict], *,
                     read_at: str = "", store: Path = FRAGMENT_STORE,
                     predicate=None, repo: Path = REPO, now=None) -> dict:
    """The duty-completion leg: did the round each thin trigger woke LEAVE A RECEIPT?

    POPULATION. The ENABLED cron rows this factory DECLARES that carry a receipt
    declaration in their own prompt. Three buckets are COUNTED, NAMED and PRINTED rather
    than dropped, because a population that resolves to no object cannot be checked by the
    reader it is reported to (#126): the rows JUDGED, the declared rows owing no receipt,
    and the rows attributed to nobody.
    """
    if not prefixes:
        return no_prefixes_leg("duty-receipt", population=len(rows), unit="row(s)",
                               read_at=read_at, read_count=len(rows))
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
    rounds_superseded = 0
    rounds_excused_by_bound = 0
    rounds_excused_by_residual = 0
    # The residual's reference instant is the READ's own instant, so every age this leg
    # prints is a property of ONE instant rather than of when each row happened to be
    # visited. `now` is injectable for probes; the live path uses `read_at`.
    residual_now = now
    if residual_now is None and read_at:
        try:
            residual_now = reader_parse_ts(read_at)
        except (ValueError, TypeError):
            residual_now = None
    if residual_now is None:
        residual_now = dt.datetime.now(dt.timezone.utc)
    # A leg that judges NOTHING owes no bound: computing one anyway would hand a member
    # factory with zero declared receipts a REFUSED line for a duty it never owed.
    if declared:
        bound_instant, bound_text, bound_refusal = duty_receipt_bound(repo)
    else:
        bound_instant, bound_text, bound_refusal = None, "", ""
    if bound_refusal:
        # A REFUSAL is not a skip and not a pass: no round may be judged while the
        # bound is unreadable, or the unbounded pre-fix behaviour returns silently.
        problems.append(bound_refusal)
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
        if bound_refusal:
            continue
        try:
            fired_instant = reader_parse_ts(fired)
        except (ValueError, TypeError):
            excused.append(
                f"{name} (cron id {job_id}): the round {round_date} records a fire "
                f"instant this leg cannot date ({fired!r}), so it cannot be placed "
                f"against the declared bound either — NOT JUDGED"
            )
            continue
        if bound_instant is not None and fired_instant < bound_instant:
            rounds_excused_by_bound += 1
            excused.append(
                f"{name} (cron id {job_id}): the round {round_date} (fired {fired}) "
                f"is BEFORE the declared bound {bound_text} for "
                f"`{DUTY_RECEIPT_BOUNDARY_KEY}`, so no receipt was possible for it — "
                f"NOT JUDGED, and NEVER backfilled"
            )
            continue
        # THE FORWARD WINDOW (#200). A round younger than the residual is IN FLIGHT: the
        # trigger fired and the lane it woke has not finished, which the leg cannot read
        # and must not call a missing duty. The window AND the age are PRINTED -- a bare
        # skip would trade a false RED for a false clean, which is the #160 class.
        age = (residual_now - fired_instant).total_seconds()
        if 0 <= age < DUTY_RESIDUAL_SECS:
            rounds_excused_by_residual += 1
            excused.append(
                f"{name} (cron id {job_id}): the round {round_date} (fired {fired}) is "
                f"IN FLIGHT — {duty_age_text(age)} old at the {read_at or 'unstated'} read, "
                f"against the declared residual {duty_age_text(DUTY_RESIDUAL_SECS)}. A round "
                f"younger than its residual is NOT JUDGED: the trigger fired and its lane "
                f"has not finished, and this leg cannot tell that from a duty never done"
            )
            continue
        matched = [r for r in ledger_rows
                   if receipt_subject_matches(str(r.get("subject") or ""), stem, round_date)]
        # A row that declares NOTHING is not a receipt (#160). This is the false-clean fix:
        # the leg's first version accepted any subject match, so a DISPATCH record written
        # before the round completed certified it. The declaration is what makes a row a
        # receipt, so the filter is the predicate and not a formatting preference.
        receipts = [r for r in matched
                    if predicate.declared_duty(str(r.get("detail") or ""))]
        judged.append({
            "name": name, "id": job_id, "stem": stem, "round": round_date,
            "fired": fired, "rows_matched": len(matched), "receipts": len(receipts),
        })
        if not receipts:
            unmatched_note = (
                f" {len(matched)} row(s) match the round's subject and declare no "
                f"`{predicate.DUTY_KEY}=`, so none of them is a receipt."
                if matched else ""
            )
            problems.append(
                f"{name} (cron id {job_id}): the round {round_date} has NO duty receipt — "
                f"no ledger run row for {stem}-{round_date}* DECLARES a completion "
                f"(`{predicate.DUTY_KEY}=`).{unmatched_note} A cron run row records only that "
                f"the TRIGGER fired, so a green run here is a MISSING duty and not a clean one"
            )
            continue
        # THE ROUND'S NEWEST DECLARATION GOVERNS (#217). A round can fail at T and complete
        # at T+n — the reporting lane measured exactly that on round 2026-09-28, where a
        # `duty=failed` row at 5-of-6 was cleared by a later `duty=completed` row and the
        # verdict did not move. A lane had no lawful way to record "failed, then completed"
        # without leaving a standing finding, so the verdict is taken from the NEWEST row.
        #
        # WHAT SUPERSESSION MUST NOT DO, and it is why this prints rather than filters: it
        # must not silently swallow a `failed` token. The superseded rows go to `excused`
        # WITH their instant and value, so a reader meets "failed, superseded by completed"
        # rather than only the happy ending. A supersession that hides the failure is a
        # false clean, which is worse than the standing problem this replaces.
        #
        # THE DOMAIN LEG IS NOT SUPERSEDED, and deliberately: an unrecognised token is a
        # fault in the WRITER'S VOCABULARY, not a state a later row settles. So it runs over
        # every receipt below, while only the newest decides the verdict.
        newest = max(receipts, key=lambda r: str(r.get("ts") or ""))
        for receipt in receipts:
            detail = str(receipt.get("detail") or "")
            n = receipt.get("n")
            for value in predicate.declared_duty(detail):
                if value not in predicate.DUTY_DOMAIN:
                    problems.append(
                        f"{name} (cron id {job_id}): the round {round_date} — receipt row "
                        f"n={n} declares {predicate.DUTY_KEY}={value}, outside the domain "
                        f"{'/'.join(predicate.DUTY_DOMAIN)}. An unrecognised value is an "
                        f"ERROR, never a silent pass"
                    )
                elif receipt is not newest and value in DUTY_INCOMPLETE_VALUES:
                    rounds_superseded += 1
                    excused.append(
                        f"{name}: the round {round_date} — SUPERSEDED receipt row n={n} "
                        f"declares {predicate.DUTY_KEY}={value} at {receipt.get('ts')}, "
                        f"superseded by n={newest.get('n')} "
                        f"({predicate.DUTY_KEY}="
                        f"{'/'.join(predicate.declared_duty(str(newest.get('detail') or ''))) or 'none'} "
                        f"at {newest.get('ts')}) — the round failed before it succeeded, and "
                        f"the earlier row is not backfilled"
                    )
        for value in predicate.declared_duty(str(newest.get("detail") or "")):
            if value in DUTY_INCOMPLETE_VALUES:
                problems.append(
                    f"{name} (cron id {job_id}): the round {round_date} did NOT complete — "
                    f"its NEWEST receipt row n={newest.get('n')} declares "
                    f"{predicate.DUTY_KEY}={value} at {newest.get('ts')}"
                )

    state, state_reason = attestation_state(store)
    return {
        "name": "duty-receipt",
        "status": "ASSERTED" if declared else "NOT RUN",
        # The reason NAMES ITS POPULATION and refuses the conclusion (#242 clause 5). The
        # old text ended "so no duty owes a receipt on this box" — a POSITIVE CLAIM ABOUT
        # THE BOX drawn from an enumeration that can be empty, which is how a lane
        # patrolling from a linked worktree was told the box was clean while the main
        # checkout reported two real problems in the same minute. An empty population
        # supports no conclusion about duties; it supports a statement about the read.
        "reason": (None if declared else (
            f"of the {len(attributed)} enabled row(s) this factory declares, NONE carries "
            f"a `receipt_subject:` declaration, so NO DUTY WAS JUDGED — that is a statement "
            f"about the DECLARED population ({len(rows)} row(s) read in all), never a "
            f"finding that no duty owes a receipt on this box"
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
            "bound": bound_text,
            "bound_refusal": bound_refusal,
            "rounds_superseded": rounds_superseded,
            "rounds_excused_by_bound": rounds_excused_by_bound,
            "residual_secs": DUTY_RESIDUAL_SECS,
            "rounds_excused_by_residual": rounds_excused_by_residual,
            "duties_missing": len([p for p in problems if "NO duty receipt" in p]),
            "attested_at_state": state,
            "attested_at_not_read": state_reason,
            "read_at": read_at,
        },
    }

def duty_age_text(secs: float) -> str:
    """A duration a reader can compare against a window, never a bare second count."""
    if secs < 90:
        return f"{secs:.0f} s"
    if secs < 5400:
        return f"{secs / 60:.1f} min"
    return f"{secs / 3600:.2f} h"


def reader_parse_ts(text: str):
    """Parse an RFC3339 instant through the reader's own predicate (#175).

    The reader is shared with the boundary gates, so this is the SAME parse that places
    a row against a boundary — a second parse here would be a second predicate for one
    field (SKILL.md section 11).
    """
    return boundary_reader().parse_ts(text)

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

_LEDGER_PREDICATE = None

def ledger_predicate():
    """`tools/ledger.py`, loaded by path for its `is_work_unit` SUBJECT predicate.

    One field, one predicate (SKILL.md section 11): the subject form `#<n>` is defined
    once, in the ledger's own tool, and this leg BINDS to it rather than re-deriving it.
    `is_work_unit` is deliberately regex-free -- its own docstring says why -- so the
    private re-derivation this refuses is not hypothetical, and the class is the one ruled
    at n=405 clause 5 and n=599.

    Loaded by PATH, with the tool's own directory placed on `sys.path` for the exec and
    removed after: `tools/ledger.py` imports its siblings (`ledger_declaration`,
    `field_predicate`, `reconstruction`), which resolve when it runs as a SCRIPT --
    `sys.path[0]` is then `tools/` -- and not when it is loaded by path from a test.
    Measured 2026-10-03: a bare `spec_from_file_location` load of `tools/ledger.py`
    raises `ModuleNotFoundError: No module named 'ledger_declaration'`.

    Cached, because the module runs a `git` call at import (`_git_common_dir()`).
    """
    global _LEDGER_PREDICATE
    if _LEDGER_PREDICATE is None:
        tools_dir = str(LEDGER_TOOL.parent)
        added = tools_dir not in sys.path
        if added:
            sys.path.insert(0, tools_dir)
        try:
            _LEDGER_PREDICATE = load_module("ledger_tool", LEDGER_TOOL)
        finally:
            if added:
                try:
                    sys.path.remove(tools_dir)
                except ValueError:
                    pass
    return _LEDGER_PREDICATE

def stall_census_leg(
    issues: list[dict],
    rows: list[dict],
    *,
    read_at: str,
    threshold_days: float = STALL_CENSUS_THRESHOLD_DAYS,
) -> dict:
    """Every unit dispatched and NEVER claimed, past the declared threshold.

    SHAPE (c), ruled at n=1857: this leg DETECTS AND PRINTS; the ACT stays a lane act. It
    NOTIFIES NOTHING. The runner's shell-CLI dispatch path is measured at 0/6 delivery
    (ledger n=975), so a delivery sent from here would be a message that never lands, and
    a lane that cannot be told cannot act. The woken lane re-dispatches through
    `session_notify`, which is a session tool this runner does not hold.

    THE POPULATION has two halves (ruling n=2100):

    * a dispatch row whose SUBJECT is a strict work unit (`#<n>`) dispatches THAT unit;
    * a dispatch row whose subject is a DESCRIPTIVE STEM -- a wave, a relay, a sweep -- is
      a CARRIER, and the units it names in its own detail/refs are the units it
      dispatched. A carried unit is admitted only where the ledger carries rows of its
      OWN, which is what separates a real board item carried by a wave (`#181`) from a
      cross-reference into ANOTHER repository's namespace or a prose mention. Measured
      2026-10-03: of the 14 units named only in dispatch prose, 11 have zero rows of their
      own, and of the three that do, one is CLOSED (`#6`) and one is named by a row that
      is itself a work-unit dispatch (`#262`, a cross-reference inside the `#75`
      dispatch);
    * a descriptive-stem dispatch naming no such unit is an OBSERVATION dispatch,
      EXPLICITLY LEGAL (ruling n=524). It is COUNTED and printed, never judged.

    THE BOARD IS THE DECLARATION OF THE NAMESPACE, and it is read for that reason. A `#N`
    in free prose names whichever repository the writer had in mind, and the ledger holds
    rows for foreign numbers too: measured 2026-10-03, `#366` carries ledger rows n=433
    and n=436 and is NOT an issue on this board at all (the fork's `#366`), while
    `openCrabs #435`, `opencrabs#504` and `#999` appear in dispatch prose and belong to
    the OpenCrabs fork. So a unit enters the population only as an issue THIS board
    declares, in state OPEN -- which is also the only reading under which "owes a claim"
    is true, since a closed board item owes none.

    THE PREDICATE IS "NEVER CLAIMED", and the ruling's own literal form was falsified by
    measurement. Read literally -- "the latest dispatch row with no later claim row" -- it
    reports 36 units on this ledger, and the extra ones are false positives of one shape:
    a unit CLAIMED and then RE-DISPATCHED. `#132` is intake n=836, claim n=837, dispatch
    n=838, close n=840; `#235` is claim n=1674, close n=1675, dispatch n=1681 (a delivery
    receipt written after the close). Both are finished, and both read OWED under the
    literal form. A `close` row is likewise disqualifying.

    A unit is therefore OWED when it is in the population, carries NO `claim` row and NO
    `close` row, and its age reaches the threshold. The age runs from the unit's EARLIEST
    dispatch-bearing row -- its own dispatch where it has one, else the earliest CARRIER
    that names it -- and never from a later MENTION, which is the second way a prose scan
    corrupts the reading: on the live ledger a mention moved `#49` from 15.05 d to 4.96 d.
    Earliest rather than latest is deliberate: a re-dispatch would otherwise reset the
    clock and hide a stall that has stood for a fortnight.

    THE OWED LINES ARE PROBLEMS, and that is stated rather than assumed, because this file
    contains the opposite ruling for the kit-drift leg. That leg reports drift as COVERAGE
    because its subject is FIVE OTHER FACTORIES' backlogs, which this factory cannot
    clear. These lines are this factory's own, and the lane the patrol wakes -- Triage --
    can clear every one of them by re-dispatching the unit or closing it on the board. The
    red is an andon cord with a working exit, not the no-exit class #139 names.
    """
    is_unit = ledger_predicate().is_work_unit

    claimed: set[str] = set()
    closed: set[str] = set()
    resident: set[str] = set()
    for row in rows:
        subject = str(row.get("subject") or "").strip()
        resident.add(subject)
        event = str(row.get("event") or "")
        if event == "claim":
            claimed.add(subject)
        elif event == "close":
            closed.add(subject)

    open_on_board: set[str] = set()
    for issue in issues:
        number = issue.get("number")
        if number is None:
            continue
        if str(issue.get("state", "")).strip().lower() == "open":
            open_on_board.add(f"#{number}")

    dispatch_rows = [row for row in rows if str(row.get("event") or "") == "dispatch"]
    carriers: dict[str, dict] = {}
    observation = 0
    carried_units = 0
    for row in dispatch_rows:
        subject = str(row.get("subject") or "").strip()
        if is_unit(subject):
            carriers.setdefault(subject, row)
            continue
        blob = f"{row.get('detail') or ''} {row.get('refs') or ''}"
        units = {
            token
            for token in re.findall(r"#\d+", blob)
            if is_unit(token) and token in resident
        }
        if not units:
            observation += 1
            continue
        carried_units += len(units)
        for unit in units:
            carriers.setdefault(unit, row)

    problems: list[str] = []
    excused: list[str] = []
    owed: list[tuple[str, float, str]] = []
    off_board = 0
    for unit, row in carriers.items():
        if unit not in open_on_board:
            off_board += 1
            continue
        if unit in claimed or unit in closed:
            continue
        try:
            fired = reader_parse_ts(str(row.get("ts") or ""))
            now = reader_parse_ts(read_at)
        except (ValueError, TypeError):
            excused.append(
                f"{unit}: the dispatch-bearing row n={row.get('n')} records an instant "
                f"this leg cannot date ({row.get('ts')!r}), so its age cannot be measured "
                f"-- NOT JUDGED"
            )
            continue
        age_days = (now - fired).total_seconds() / 86400.0
        if age_days < threshold_days:
            continue
        actor = str(row.get("actor") or "unstated")
        owed.append((unit, age_days, actor))

    owed.sort(key=lambda item: -item[1])
    for unit, age_days, actor in owed:
        problems.append(
            f"OWED {unit}: dispatched {age_days:.2f} d ago and NEVER CLAIMED, and the "
            f"board still carries it OPEN -- the dispatch-bearing row names "
            f"actor={actor}. Re-dispatch it to the lane that owns it through "
            f"`session_notify`, or close it on the board: a dispatch no lane has taken is "
            f"work nobody is doing"
        )

    return {
        "name": "stall-census",
        "status": "ASSERTED",
        "problems": problems,
        "excused": excused,
        "coverage": {
            "dispatch_rows_examined": len(dispatch_rows),
            "observation_dispatches": observation,
            "carried_units_resolved": carried_units,
            "units_in_population": len(carriers),
            "units_off_board": off_board,
            "units_owed": len(owed),
            "threshold_days": threshold_days,
            "threshold_basis": STALL_CENSUS_THRESHOLD_BASIS,
            "read_at": read_at,
        },
    }

def head_manifest(rel: str | None = None, *, repo: Path | None = None) -> tuple[str | None, str]:
    """Read the kit manifest from HEAD rather than from the working tree (issue #185).

    WHY HEAD AND NOT DISK. `registry/kit.json` is GENERATED FROM THE WORKING TREE, so a
    reference read off disk is whatever the last generation happened to see, and a lane
    mid-write changes it under the reader. Measured at the filing (2026-09-26): five
    distinct `kit_version` values in about 23 minutes, TWO of which appeared in NO commit
    at all, `registry/kit.json` changed between two reads 14 seconds apart, and the
    manifest included two files untracked at that instant. A member's pin is COMMITTED, so
    comparing it against an uncommitted reference makes the verdict unreproducible by any
    reader who was not here. HEAD is the one revision every reader can re-derive from the
    repository alone, and it is what the pin is actually a statement about.

    `HEAD:./<rel>` is CWD-RELATIVE, and that is deliberate rather than incidental. This
    file is byte-identical to its TEMPLATE twin, whose REPO resolves to TEMPLATE/ where
    `registry/kit.json` is factory data that never ships — so the twin reports the path
    absent, exactly as it did before this change, instead of silently reading the PARENT
    tree's manifest and comparing a factory's own files against the template source.

    Returns (text, why). `text` is None when HEAD cannot be read, and `why` names the
    reason so the leg reports NOT RUN with it rather than a clean sweep over nothing.

    Both coordinates default to the module globals and are resolved AT CALL TIME rather
    than frozen as default arguments, so a probe can point them at a throwaway repository
    and prove the HEAD read against a tree whose HEAD and working copy DISAGREE — which is
    the only way to show this leg reads HEAD, since on a clean live tree the two agree and
    the pre-fix code would pass the same assertion.
    """
    repo = REPO if repo is None else repo
    rel = KIT_MANIFEST_REL if rel is None else rel
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "show", f"HEAD:./{rel}"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"git show HEAD:./{rel} could not run: {exc}"
    if proc.returncode != 0:
        lines = (proc.stderr or "").strip().splitlines()
        return None, lines[-1] if lines else f"git show HEAD:./{rel} failed"
    return proc.stdout, ""

def kit_drift_leg(
    *,
    manifest_path: Path | None = None,
    fleet_path: Path = FLEET_MANIFEST,
    bootstrap_named: tuple[str, ...] = BOOTSTRAP_NAMED,
    read_at: str = "",
) -> dict:
    """Per-member drift against `registry/kit.json`: same / DIFF / ABSENT, with names.

    A REPORT, not a verdict on the members. `problems` carries only this factory's own
    defects — a manifest or fleet file it cannot read, a manifest that describes no files,
    or no reachable member at all — because those are the examined-nothing cases. A member
    being stale is a fact about THAT member, reported in `coverage` and acted on by the
    notify step; reddening this factory's patrol for it would make our verdict a function
    of another lane's backlog, which is the coupling the design exists to avoid.

    Each member's repo is read from `registry/fleet.json`'s own `repo` field, so a member
    that moves is followed by the manifest rather than by a second list. A manifest path is
    compared at `<member>/<path minus the TEMPLATE/ prefix>`, which is the path the file
    occupies in a member tree — the prefix is an artefact of how the template is stored
    here, never part of what a factory carries.
    """
    problems: list[str] = []
    members: list[dict] = []
    totals = {"same": 0, "DIFF": 0, "ABSENT": 0}
    boot_totals = {"same": 0, "DIFF": 0, "ABSENT": 0}

    if manifest_path is None:
        # THE #185 REMEDY: the live reference is the COMMITTED manifest, never the file on
        # disk. See `head_manifest` for the measurement that forced it. A probe passes an
        # explicit path and keeps the disk read it has always had, which is what lets one
        # leg serve both the live patrol and a hermetic fixture.
        source = f"HEAD:{KIT_MANIFEST_REL}"
        raw, why = head_manifest()
        if raw is None:
            problems.append(
                f"the kit manifest {source} could not be read from HEAD ({why}) — there is "
                f"no reference to measure drift against, so this leg examined NOTHING and "
                f"says so rather than reporting a clean sweep over no population"
            )
            return {"name": "kit-drift", "status": "NOT RUN", "problems": problems,
                    "excused": [], "coverage": {"reason": f"{source} — {why}",
                                                "read_at": read_at}}
    else:
        source = str(manifest_path)
        if not manifest_path.is_file():
            problems.append(
                f"the kit manifest {manifest_path} is absent — there is no reference to "
                f"measure drift against, so this leg examined NOTHING and says so rather "
                f"than reporting a clean sweep over no population"
            )
            return {"name": "kit-drift", "status": "NOT RUN", "problems": problems,
                    "excused": [], "coverage": {"reason": str(manifest_path),
                                                "read_at": read_at}}
        try:
            raw = manifest_path.read_text(encoding="utf-8")
        except OSError as exc:
            problems.append(f"the kit manifest {manifest_path} could not be read: {exc}")
            return {"name": "kit-drift", "status": "NOT RUN", "problems": problems,
                    "excused": [], "coverage": {"reason": str(exc), "read_at": read_at}}

    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as exc:
        problems.append(f"the kit manifest {source} could not be read: {exc}")
        return {"name": "kit-drift", "status": "NOT RUN", "problems": problems,
                "excused": [], "coverage": {"reason": str(exc), "read_at": read_at}}

    files: dict[str, str] = manifest.get("files") or {}
    if not files:
        problems.append(
            f"the kit manifest {manifest_path} declares NO files — a reference over an empty "
            f"set would agree with every tree, which is the vacuous-pass shape"
        )
        return {"name": "kit-drift", "status": "ASSERTED", "problems": problems,
                "excused": [], "coverage": {"manifest_files": 0, "read_at": read_at}}

    # The shared pin reader, loaded by path (see KIT_PIN). If it cannot be loaded the leg
    # does NOT fall back to a private loop: falling back would give this leg a second
    # implementation of the comparison it exists to share, which is the defect the sharing
    # prevents. It reports NOT RUN over the reason instead.
    try:
        kit_pin = load_module("kit_pin", KIT_PIN)
    except BoardReadError as exc:
        problems.append(f"{exc} — the kit-drift leg has no comparison predicate and refuses "
                        f"to invent a private one")
        return {"name": "kit-drift", "status": "NOT RUN", "problems": problems,
                "excused": [], "coverage": {"reason": str(KIT_PIN), "read_at": read_at}}

    if not fleet_path.is_file():
        problems.append(f"the fleet manifest {fleet_path} is absent — no member repo to read")
        return {"name": "kit-drift", "status": "NOT RUN", "problems": problems,
                "excused": [], "coverage": {"reason": str(fleet_path), "read_at": read_at}}

    try:
        fleet = json.loads(fleet_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"the fleet manifest {fleet_path} could not be read: {exc}")
        return {"name": "kit-drift", "status": "NOT RUN", "problems": problems,
                "excused": [], "coverage": {"reason": str(exc), "read_at": read_at}}

    for entry in fleet.get("factories") or []:
        slug = str(entry.get("slug") or "")
        root = Path(str(entry.get("repo") or ""))
        if slug == "meta-factory":
            # This factory IS the template source: comparing it against its own manifest
            # would report 106 identical cells and inflate every total with a tautology.
            continue
        if not root.is_dir():
            members.append({"slug": slug, "root": str(root), "reachable": False,
                            "same": 0, "DIFF": 0, "ABSENT": 0, "diff_files": [], "absent_files": []})
            continue
        same = diff = absent = 0
        diff_files: list[str] = []
        absent_files: list[str] = []
        # The comparison is the SHARED pin predicate, not a private loop: our patrol leg and
        # a factory's own pin gate compare the same way against different references, and two
        # implementations would make our report and theirs disagree about the same bytes
        # (SKILL.md section 11: one field, one predicate).
        res = kit_pin.compare(manifest, root)
        problems.extend(res["problems"])
        same = res["counts"]["same"]
        diff = res["counts"]["DIFF"]
        absent = res["counts"]["ABSENT"]
        diff_files = res["diff_files"]
        absent_files = res["absent_files"]
        totals["same"] += same
        totals["DIFF"] += diff
        totals["ABSENT"] += absent
        for name in bootstrap_named:
            if name in absent_files:
                boot_totals["ABSENT"] += 1
            elif name in diff_files:
                boot_totals["DIFF"] += 1
            elif (root / name).is_file():
                boot_totals["same"] += 1
        members.append({
            "slug": slug, "root": str(root), "reachable": True,
            "same": same, "DIFF": diff, "ABSENT": absent,
            "diff_files": sorted(diff_files), "absent_files": sorted(absent_files),
        })

    reachable = [m for m in members if m["reachable"]]
    if not reachable:
        problems.append(
            f"no member repository was reachable — {len(members)} declared in {fleet_path}, "
            f"none present on this box, so the sweep examined NOTHING and reports that "
            f"rather than a clean result"
        )

    return {
        "name": "kit-drift",
        "status": "ASSERTED",
        "problems": problems,
        "excused": [],
        "coverage": {
            "manifest_files": len(files),
            "kit_version": manifest.get("kit_version"),
            # WHICH REFERENCE WAS READ, and the revision IT was generated from (issue #185).
            # Without the first, a reader cannot tell a HEAD read from a disk read -- the two
            # are the whole point of the change and they print identically otherwise. The
            # second is the manifest's own `source_head`: the pin is windowed only when both
            # halves travel, since a HEAD read of a manifest that names no revision still
            # leaves the reader unable to say which commit the content came from.
            "manifest_source": source,
            "manifest_head": manifest.get("source_head"),
            "members_declared": len(members),
            "members_reachable": len(reachable),
            "members_unreachable": [m["slug"] for m in members if not m["reachable"]],
            "manifest_cells": dict(totals),
            "manifest_cells_total": totals["same"] + totals["DIFF"] + totals["ABSENT"],
            "bootstrap_cells": dict(boot_totals),
            "bootstrap_cells_total": sum(boot_totals.values()),
            "bootstrap_named": list(bootstrap_named),
            "members": members,
            "read_at": read_at,
        },
    }

# ---- the worktree leg (issue #220, ruled at ledger n=1567) ---------------------------
#
# THE EXCLUDED OBJECT CLASS. `tools/hygiene.py` derives its scratch population from the
# repository's own directory name (`scratch_patterns_for("agent-factories")` ->
# `/tmp/agent-factories-*`), while a lane names its worktree whatever it likes
# (`/tmp/<lane>-*`, `/tmp/rr-*`, `/tmp/kit*`). So NO worktree path can ever match that glob and
# the residue is outside the cleanliness instrument's population BY CONSTRUCTION rather than
# by a cleanliness result — measured at the filing: 38 registered worktrees, 0 matching.
#
# THE REMEDY IS NAMED, NOT WIDENED, and the refusal is the load-bearing half. Widening that
# glob was refused for two measured reasons that are together decisive: hygiene judges
# staleness by MTIME while 13 of the 37 held live uncommitted work at the filing instant
# (the widened population would report peers' ACTIVE work as residue), and hygiene's remedy
# is REMOVAL, which on a worktree holding uncommitted work DESTROYS it. A population
# containing live work paired with a destructive remedy is the combination this factory's
# law forbids — so the answer to an excluded class is a leg that NAMES it, never a widened
# glob over live work.
#
# THE INSTRUMENT ALREADY EXISTS: `git worktree list --porcelain` (population and state) and
# `git worktree prune` (registrations whose directory is gone — measured 0 of the 38 at the
# filing, so it clears none of this). Nothing is owed here that does not ship (#102/#120);
# what was missing is that NO factory surface READ them.
#
# THIS LEG NEVER REMOVES, and that is a property of its design rather than of its restraint:
# it holds no unlink, no prune and no git subcommand that mutates a worktree. A lane may
# remove its OWN tree; this leg's whole output is a report.
#
# WHY A LEG AND NOT A PARAGRAPH (P29): `git worktree list` exists and no factory surface
# read it, so a sentence saying "beware worktrees" would be dead text while a printed leg
# is not.
#
# THE HARM CLAUSE OF THE FILING IS FALSIFIED and the class claim stands: the specimen
# (a peer worktree's ad2ac70) is a DEAD DUPLICATE — patch-identical to 83a2776, which is on
# origin, 14 seconds later — so this is an OBSERVABILITY gap, never a data-loss incident.
# The leg's figures therefore REPORT residue and are deliberately NOT problems: a tree
# holding a peer's unlanded work is the CORRECT state for that tree, and a permanently red
# leg destroys every other leg's signal. The counts are printed so a `problems: 0` beside
# them cannot be read as "no residue".

WORKTREE_HAZARD_CLASSES = (
    "unreachable-commit",   # holds commits not reachable from the base ref
    "uncommitted-work",     # holds paths that differ from HEAD
)
"""The two hazard classes, DECLARED rather than inline at the comparison (#220 clause 3)."""

WORKTREE_BASE_REF = "origin/main"
"""The base a tree's own commits are judged against — the same ref the ruling used."""

_WORKTREE_FIELD = re.compile(r"^([a-z-]+)(?: (.*))?$")

def worktree_records(repo: Path = REPO) -> tuple[list[dict], str | None]:
    """`git worktree list --porcelain` parsed into records — or (records, error).

    The population AND its state come from git's own instrument, never from a glob over
    `/tmp`: a glob cannot tell a registered worktree from an abandoned directory, and this
    leg's whole subject is the class a glob cannot see. Returns the error rather than
    raising, so the caller can render a STATED INABILITY instead of a traceback.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "worktree", "list", "--porcelain"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return [], f"`git worktree list` could not run: {exc}"
    if proc.returncode != 0:
        return [], (proc.stderr or proc.stdout).strip()[:200] or "non-zero exit"

    records: list[dict] = []
    current: dict = {}
    for line in proc.stdout.splitlines():
        if not line.strip():
            if current:
                records.append(current)
                current = {}
            continue
        match = _WORKTREE_FIELD.match(line)
        if not match:
            continue
        key, value = match.group(1), match.group(2)
        if key == "worktree":
            if current:
                records.append(current)
            current = {"path": value}
        elif key in ("HEAD", "branch"):
            current[key.lower()] = value
        else:
            current[key] = value if value is not None else True
    if current:
        records.append(current)
    return records, None

def worktree_state(path: str, *, base: str = WORKTREE_BASE_REF) -> dict:
    """One tree's state: its uncommitted paths and its commits ahead of `base`.

    `GIT_OPTIONAL_LOCKS=0` is set deliberately: `git status` otherwise REFRESHES the
    index and takes `index.lock` in a tree that may belong to a peer lane mid-task, so a
    read-only census would be a writer on someone else's work. The predicate is exactly the
    ruling's own — `status --porcelain` and `rev-list --count <base>..HEAD` — so the leg's
    figures are comparable with the census that filed the issue.
    """
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    out = {"dirty": [], "ahead": 0, "problems": []}
    try:
        status = subprocess.run(
            ["git", "-C", path, "status", "--porcelain"],
            capture_output=True, text=True, env=env, timeout=120,
        )
        if status.returncode == 0:
            out["dirty"] = [line for line in status.stdout.splitlines() if line.strip()]
        else:
            out["problems"].append(
                f"{path}: `git status` exited {status.returncode} — "
                f"{(status.stderr or '').strip()[:120]}"
            )
        ahead = subprocess.run(
            ["git", "-C", path, "rev-list", "--count", f"{base}..HEAD"],
            capture_output=True, text=True, env=env, timeout=120,
        )
        if ahead.returncode == 0:
            out["ahead"] = int(ahead.stdout.strip() or "0")
        else:
            out["problems"].append(
                f"{path}: `git rev-list --count {base}..HEAD` exited {ahead.returncode} — "
                f"{(ahead.stderr or '').strip()[:120]}"
            )
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        out["problems"].append(f"{path}: {exc}")
    return out

def worktree_leg(*, read_at: str, repo: Path = REPO,
                 records_fn=None, state_fn=None) -> dict:
    """The worktree residue report — population, and the two hazard classes BY PATH.

    Injected dependencies for the reason every other leg here has them: a probe must drive
    the classification without a live worktree set, and a leg that can only run against the
    live box cannot be probed at all when the live box is what is wrong.

    A tree holding a peer's unlanded work is the CORRECT state for that tree, so nothing
    here is a `problem`; the counts and the paths are the report. NOT RUN with its reason
    when the instrument cannot answer: an unreadable worktree list is not an empty one, and
    an empty one is not a clean one.
    """
    records_fn = records_fn or worktree_records
    state_fn = state_fn or worktree_state

    records, error = records_fn(repo)
    if error:
        return {
            "name": "worktree",
            "status": "NOT RUN",
            "problems": [],
            "excused": [],
            "coverage": {
                "reason": f"the worktree census could not be read — {error}",
                "read_at": read_at,
            },
        }
    if not records:
        # A repository ALWAYS has at least its main worktree, so an empty list is an
        # instrument failure and never a clean box — the population clause's own rule.
        return {
            "name": "worktree",
            "status": "NOT RUN",
            "problems": [],
            "excused": [],
            "coverage": {
                "reason": "`git worktree list --porcelain` returned no record(s); a "
                          "repository always carries at least its main worktree, so this "
                          "is an instrument failure and NOT a clean box",
                "read_at": read_at,
            },
        }

    states: list[dict] = []
    missing_dir: list[str] = []
    for record in records:
        path = str(record.get("path") or "")
        entry = {"path": path, "main": False}
        if not path or not Path(path).is_dir():
            # `git worktree prune` clears exactly this class and nothing else; measured 0
            # of 38 at the filing, so it clears none of the residue this leg reports.
            entry["main"] = bool(record.get("bare")) or not path
            missing_dir.append(path or "<no path in the record>")
            states.append(entry)
            continue
        state = state_fn(path)
        entry.update(state)
        states.append(entry)

    # The FIRST record is the tree the command was run from — the main worktree for a run
    # from the repository itself. `scratch` is its complement, which is the population the
    # cleanliness instrument cannot reach: a lane names its own worktree, so no name can
    # match that tool's glob.
    for index, entry in enumerate(states):
        entry["main"] = index == 0
    scratch = [e for e in states if not e["main"]]

    unreachable = [e for e in scratch if e.get("ahead", 0) > 0]
    dirty = [e for e in scratch if e.get("dirty")]
    problems = [
        p for entry in states for p in entry.get("problems", [])
    ]

    return {
        "name": "worktree",
        "status": "ASSERTED",
        "problems": problems,
        "excused": [],
        "coverage": {
            "read_at": read_at,
            "base_ref": WORKTREE_BASE_REF,
            "hazard_classes": list(WORKTREE_HAZARD_CLASSES),
            "removes": False,
            "worktrees_total": len(states),
            "worktrees_scratch": len(scratch),
            "missing_directory": missing_dir,
            "unreachable_commits": [
                {"path": e["path"], "ahead": e.get("ahead", 0)} for e in unreachable
            ],
            "uncommitted_work": [
                {"path": e["path"], "paths": len(e.get("dirty") or [])} for e in dirty
            ],
            "instrument": "git worktree list --porcelain / git worktree prune",
            "population_predicate": "git worktree list --porcelain, main = first record",
        },
    }


def publish_freshness_leg(
    *,
    repo: Path = REPO,
    remote: str = PUBLISH_REMOTE,
    branch: str = PUBLISH_BRANCH,
    read_at: str,
    now=None,
    pusher: Path = PUBLISH_PUSHER,
) -> dict:
    """Every commit that has not reached `origin`, NAMED, with the instant read.

    The predicate is the pusher's own (`tools/publish.py::remote_tip` and
    `::unpushed_commits`), loaded by path rather than restated, so this leg and the
    mechanism cannot disagree about what "unpushed" means -- the same one-predicate rule
    the kit-drift leg follows against `tools/kit_pin.py`. The remote tip is read FROM THE
    REMOTE: `origin/main` is a cache updated only by a fetch, so a leg reading it would
    report the fact in doubt rather than the fact.

    A finding NAMES each offending sha with its age and its lane trailer. A count alone
    cannot be dispatched, claimed or closed; a named commit can be all three (#148).

    SCOPE (issue #284). This leg measures LAG -- commits committed but not yet on the
    remote -- and NOT cadence compliance. The pusher's grace window and cadence are the
    PUSHER's declared bounds and bind `tools/publish.py` alone, so a late pusher and an
    absent one leave the same unpushed commit behind and this leg cannot tell them apart.
    The cadence side it does carry is a RECEIPT comparison: the pusher records its own last
    push in a file under `evidence/`, and a remote tip that is not that sha left through
    some other path. That arm names the tip, its age and the lane trailer of its commit.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    coverage = {
        "remote": remote,
        "branch": branch,
        "read_at": read_at,
        # THE PUSHER'S BOUNDS, labelled as such. They travel here because a reader needs
        # them to interpret `stale`; they are NOT this leg's bounds and NOT the fleet's.
        "residual_secs": PUBLISH_RESIDUAL_SECS,
        "grace_secs": PUBLISH_GRACE_SECS,
        "cadence_secs": PUBLISH_CADENCE_SECS,
        "bounds_label": PUBLISH_BOUNDS_LABEL,
        "leg_scope": PUBLISH_LEG_SCOPE,
        "unpushed": 0,
        "shas": [],
        "stale": [],
        "remote_tip": None,
        # THE CADENCE SIDE (issue #284). `receipt` is the pusher's own record of its last
        # push; a remote tip that is not that sha left through some OTHER path, and the
        # tip-age arm is the opportunistic half -- it only sees a tip SAMPLED while young.
        "receipt": None,
        "receipt_reason": "",
        "receipt_mismatch": None,
        "remote_tip_age_secs": None,
        "remote_tip_age_reason": "",
        "tip_younger_than_grace": False,
    }
    problems: list[str] = []

    if not Path(pusher).is_file():
        return {
            "name": "publish-freshness",
            "status": "NOT RUN",
            "problems": [],
            "excused": [],
            "coverage": {**coverage, "reason": (
                f"{pusher} is absent, so this leg has no predicate to read with -- a "
                f"bootstrapped factory carries the pusher only if it adopted it"
            )},
        }

    try:
        pub = load_module("publish", Path(pusher))
    except BoardReadError as exc:
        problems.append(f"the pusher's own predicate could not be loaded: {exc}")
        return {
            "name": "publish-freshness", "status": "ASSERTED",
            "problems": problems, "excused": [], "coverage": coverage,
        }

    tip, why = pub.remote_tip(Path(repo), remote, branch)
    if tip is None:
        # An unreachable remote is a FINDING, not an absence: "I could not ask" and
        # "there is nothing to publish" are different facts and must never render alike.
        problems.append(
            f"{remote}/{branch} could not be read: {why} -- an unreadable remote is a "
            f"finding, never a clean result"
        )
        return {
            "name": "publish-freshness", "status": "ASSERTED",
            "problems": problems, "excused": [], "coverage": {**coverage, "reason": why},
        }
    coverage["remote_tip"] = tip

    rc, _, _ = pub._git(Path(repo), "merge-base", "--is-ancestor", tip, "HEAD")
    if rc != 0:
        problems.append(
            f"{remote}/{branch} ({tip}) is not an ancestor of HEAD -- the branch has "
            f"DIVERGED, and the pusher reports rather than resolves by design"
        )
        coverage["diverged"] = True

    commits, why = pub.unpushed_commits(Path(repo), tip)
    if commits is None:
        problems.append(f"the unpushed set could not be read: {why}")
        return {
            "name": "publish-freshness", "status": "ASSERTED",
            "problems": problems, "excused": [], "coverage": coverage,
        }

    coverage["unpushed"] = len(commits)
    coverage["shas"] = [c["sha"] for c in commits]
    for commit in commits:
        age = pub.age_secs(commit.get("committed_at") or "", now)
        entry = {
            "sha": commit["sha"],
            "age_secs": None if age is None else int(age),
            "session_id": commit.get("session_id") or "",
            "subject": commit.get("subject") or "",
        }
        coverage.setdefault("commits", []).append(entry)
        if age is None or age > PUBLISH_RESIDUAL_SECS:
            coverage["stale"].append(entry)
            problems.append(
                f"{commit['sha']} has been unpushed for "
                f"{'an unreadable age' if age is None else f'{int(age)}s'}, past the "
                f"{PUBLISH_RESIDUAL_SECS}s residual window (6h cadence + "
                f"{PUBLISH_GRACE_SECS}s grace) -- no healthy pusher explains this; "
                f"lane {entry['session_id'] if entry['session_id'] else 'no lane trailer'} -- {entry['subject'][:60]}"
            )

    # --- the cadence side (issue #284) ------------------------------------------------
    #
    # Two arms, and they are NOT equal. The RECEIPT arm is decisive: the pusher records the
    # sha it pushed, so a remote tip that is not that sha did not leave through the pusher.
    # The TIP-AGE arm is opportunistic -- it can only see a tip that happens to be sampled
    # while still younger than the grace window -- and its bound is printed beside it, so a
    # quiet round is never read as a clean one.
    tip_info, tip_why = pub.commit_info(Path(repo), tip)

    receipt, receipt_why = pub.read_receipt(Path(repo))
    if receipt is None:
        coverage["receipt_reason"] = receipt_why
    else:
        rec_age = pub.age_secs(receipt.get("instant") or "", now)
        coverage["receipt"] = {
            "sha": str(receipt.get("sha") or ""),
            "instant": str(receipt.get("instant") or ""),
            "age_secs": None if rec_age is None else int(rec_age),
        }
        if coverage["receipt"]["sha"] != tip:
            lane = (tip_info or {}).get("session_id") or ""
            subject = (tip_info or {}).get("subject") or ""
            trailer = lane if tip_info is not None else f"unreadable ({tip_why})"
            coverage["receipt_mismatch"] = {
                "remote_tip": tip,
                "receipt_sha": coverage["receipt"]["sha"],
                "receipt_instant": coverage["receipt"]["instant"],
                "lane": lane,
                "subject": subject,
            }
            problems.append(
                f"the remote tip {tip} is NOT the sha the pusher last recorded "
                f"({coverage['receipt']['sha']} at {coverage['receipt']['instant']}) -- a "
                f"push that did not go through the pusher; lane "
                f"{trailer or 'no lane trailer'}"
                + (f" -- {subject[:60]}" if subject else "")
            )

    if tip_info is None:
        coverage["remote_tip_age_reason"] = tip_why
    else:
        tip_age = pub.age_secs(tip_info.get("committed_at") or "", now)
        if tip_age is None:
            coverage["remote_tip_age_reason"] = (
                f"the tip's own instant did not parse ({tip_info.get('committed_at')!r})"
            )
        else:
            coverage["remote_tip_age_secs"] = int(tip_age)
            if tip_age < PUBLISH_GRACE_SECS:
                coverage["tip_younger_than_grace"] = True
                # The pusher HOLDS a commit this young, so no governed push explains this
                # tip -- but only say so when no receipt has the stronger word. A receipt
                # that names this tip explains it; a receipt that names ANOTHER sha is
                # already reported above, and one tip is named once.
                if coverage.get("receipt") is None:
                    problems.append(
                        f"the remote tip {tip} is {int(tip_age)}s old, YOUNGER than the "
                        f"pusher's {PUBLISH_GRACE_SECS}s grace window, and no receipt "
                        f"records any push -- the pusher holds a commit this young, so this "
                        f"tip left through some other path (arm bound: it sees only a tip "
                        f"SAMPLED while still young -- roughly 1 round in "
                        f"{PUBLISH_CADENCE_SECS // PUBLISH_GRACE_SECS} at this cadence)"
                    )

    return {
        "name": "publish-freshness",
        "status": "ASSERTED",
        "problems": problems,
        "excused": [],
        "coverage": coverage,
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
        if leg["status"] == "NOT RUN" and leg["name"] in (
            "cron-thinness", "pacemaker-presence", "notify-receipt", "duty-receipt"
        ):
            # A leg that examined NOTHING must never render as one that examined the
            # population and found it clean (#242). Its reason is printed, and its
            # counters travel with it so the unattributed population is visible rather
            # than absent — the same discipline the kit-drift and publish legs follow.
            lines.append(f"  NOT RUN: {cov.get('reason') or 'reason not stated'}")
            for key in ("prefixes",):
                if key in cov:
                    lines.append(f"  {key}: {cov[key] or 'none declared'}")
            for key, value in cov.items():
                if key in ("reason", "read_at", "prefixes"):
                    continue
                lines.append(f"  {key}: {value}")
            lines.append(f"  read at {cov.get('read_at') or 'unstated'}")
            lines.append(f"  excused: {len(leg['excused'])}")
            lines.append(f"  problems: {len(leg['problems'])}")
            lines.append("")
            continue
        if leg["name"] == "board-close":
            lines.append(
                f"  close rows (declaring {cov['declaration_token']}, at or after "
                f"{cov['invariant_boundary']}): {cov['close_rows_examined']} examined, "
                f"{len(leg['problems'])} problem(s) — board read at {cov['board_read_at']}"
            )
        elif leg["name"] == "board-closed":
            # Direction (3). The population is the BOARD's, so the line names the board
            # read instant and the boundary it was taken against; the PRE-BOUNDARY count
            # is printed too, because an exclusion that is not printed cannot be told
            # from a miss. A closed item with no close row is DRIFT by ruling n=496
            # clause (5) — this leg asks no completeness question of its population.
            lines.append(
                f"  closed items (at or after {cov['invariant_boundary']}, "
                f"{cov['pre_boundary_closed_items']} earlier close(s) excluded as "
                f"pre-invariant): {cov['closed_items_examined']} examined, "
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
                f"  law-content scan: {cov['rows_scanned']} row(s) examined, "
                f"{len(cov['law_content_rows'])} embed a boundary/window/epoch the law "
                f"owns, {len(cov['dated_not_boundary_rows'])} carry a bare date (a "
                f"citation of the past, reported and never judged)"
            )
            for row in cov["law_content_rows"]:
                owner = row["owner"] or row["home"] or "unknown"
                lines.append(
                    f"    law content: {row['name']} (owner {owner}) embeds "
                    f"{row['instant']} — a thin POINTER to the law must not carry its state"
                )
            for row in cov["dated_not_boundary_rows"]:
                owner = row["owner"] or row["home"] or "unknown"
                lines.append(
                    f"    dated, not a boundary: {row['name']} (owner {owner}) carries "
                    f"{row['date']}"
                )
            routes = cov.get("attributed_routes", [])
            lines.append(
                f"  delivery paths: the CURRENT route of each of {len(routes)} attributed "
                f"row(s), NAMED per row — a class-1 row is named with its class, never "
                f"counted, and a regression into that class shows at the next fire"
            )
            for row in routes:
                detail = (
                    f"deliver_to {row['deliver_to']!r}" if row["deliver_to"]
                    else "no deliver_to"
                )
                lines.append(f"    route: {row['name']} — {row['route']} ({detail})")
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
                f"on {cov['log_dir']} naming OR DECLARING a live row this factory "
                f"declares — {cov['logs_without_receipt']} produced no receipt"
            )
            for row in cov.get("not_attempted_logs", []):
                lines.append(
                    f"    no attempt: {row['job']} (cron id {row['id'] or 'unstated'}) — "
                    f"{row['path']} carries no output, so no notify was attempted; "
                    f"reported, never a failed duty"
                )
            lines.append(
                f"  retired: {cov.get('logs_retired', 0)} log(s) — "
                f"{cov.get('retired_predicate', 'predicate unstated')}; history, never "
                f"judged (a bucket that saw none prints 0 here, never silence)"
            )
            for row in cov.get("retired_logs", []):
                lines.append(
                    f"    retired: {row['job']} ({row['path']}) — history, not judged"
                )
            if cov.get("logs_attributed_by_redirect"):
                lines.append(
                    f"  attributed by DECLARED REDIRECT (the label does not equal the job "
                    f"name): {cov['logs_attributed_by_redirect']} log(s) — JUDGED, not "
                    f"filed as history, because a LIVE row's own prompt declares them"
                )
            for row in cov.get("attributed_by_redirect", []):
                lines.append(
                    f"    live label mismatch: {row['job']} ({row['path']}) is declared "
                    f"by the live row {row['row']}"
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
                lines.append(
                    f"    NOT JUDGED — declares no `receipt_subject:`, so this leg cannot "
                    f"tell whether it owes one: {name or '(unnamed row)'}"
                )
            for duty in cov.get("duties_judged", []):
                lines.append(
                    f"    {duty['name']} (cron id {duty['id']}): round {duty['round']} "
                    f"(fired {duty['fired'] or 'unstated'}) — "
                    f"{duty['rows_matched']} row(s) match the round's subject, "
                    f"{duty['receipts']} DECLARE a completion"
                )
            lines.append(
                f"  backward bound `{DUTY_RECEIPT_BOUNDARY_KEY}`: "
                f"{cov.get('bound') or 'UNDECLARED'}"
            )
            residual = cov.get("residual_secs")
            lines.append(
                f"  forward residual: "
                f"{duty_age_text(residual) if residual is not None else 'UNDECLARED'} "
                f"({residual if residual is not None else '?'} s) — a round younger than "
                f"this is IN FLIGHT and NOT JUDGED"
            )
            if cov.get("rounds_excused_by_residual"):
                lines.append(
                    f"    {cov['rounds_excused_by_residual']} round(s) are younger than "
                    f"that residual and are excused by it, NAMED above — never a missing duty"
                )
            if cov.get("rounds_excused_by_bound"):
                lines.append(
                    f"    {cov['rounds_excused_by_bound']} round(s) fired BEFORE that "
                    f"bound and are excused by it, NAMED above — never backfilled"
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
        elif leg["name"] == "publish-freshness":
            # `.get` throughout, for the reason the kit-drift branch below states: a leg
            # whose coverage is PARTIAL -- a NOT RUN, or a leg injected for a probe -- must
            # render as NOT RUN rather than crash the renderer on the very path that exists
            # to REPORT the absence. An absence is a NOT RUN, never a traceback.
            if "reason" in cov and cov.get("unpushed", 0) == 0 and not cov.get("remote_tip"):
                lines.append(f"  NOT RUN: {cov['reason']}")
            elif cov.get("stubbed"):
                lines.append(
                    f"  injected for this run: {cov.get('unpushed', 0)} unpushed commit(s) "
                    f"-- the live leg reads the remote, which no probe may do"
                )
            else:
                lines.append(
                    f"  {cov.get('remote', 'origin')}/{cov.get('branch', 'main')}: remote "
                    f"tip {cov.get('remote_tip') or 'unread'}, "
                    f"{cov.get('unpushed', 0)} unpushed commit(s)"
                    + (f" {', '.join(cov.get('shas') or [])}" if cov.get("shas") else "")
                )
                lines.append(
                    f"  residual window: {cov.get('residual_secs', 0)}s "
                    f"({cov.get('cadence_secs', 0)}s cadence + {cov.get('grace_secs', 0)}s "
                    f"grace); {len(cov.get('stale') or [])} commit(s) past it"
                )
                lines.append(f"  those bounds are {cov.get('bounds_label', 'the pusher\u2019s own')}")
                lines.append(f"  SCOPE: {cov.get('leg_scope', '')}")
                rec = cov.get("receipt")
                if rec:
                    lines.append(
                        f"  pusher receipt: {rec.get('sha')} pushed at {rec.get('instant')}"
                        + (
                            f" ({rec.get('age_secs')}s ago)"
                            if rec.get("age_secs") is not None
                            else " (age unreadable)"
                        )
                    )
                else:
                    lines.append(
                        f"  pusher receipt: NONE — {cov.get('receipt_reason', 'unstated')}"
                    )
                if cov.get("receipt_mismatch"):
                    mm = cov["receipt_mismatch"]
                    lines.append(
                        f"  UNGOVERNED PUSH: remote tip {mm.get('remote_tip')} is not the "
                        f"pusher's last receipt ({mm.get('receipt_sha')}) — lane "
                        f"{mm.get('lane') or 'no lane trailer'}"
                    )
                if cov.get("remote_tip_age_secs") is not None:
                    lines.append(
                        f"  remote tip age at read time: {cov['remote_tip_age_secs']}s"
                        + (
                            " — YOUNGER than the pusher's grace window"
                            if cov.get("tip_younger_than_grace")
                            else ""
                        )
                    )
                elif cov.get("remote_tip_age_reason"):
                    lines.append(
                        f"  remote tip age: UNREADABLE — {cov['remote_tip_age_reason']}"
                    )
                lines.append(
                    f"  tip-age arm bound: it sees only a tip SAMPLED while younger than the "
                    f"{cov.get('grace_secs', 0)}s grace window — roughly 1 round in "
                    f"{(cov.get('cadence_secs') or 0) // max(1, cov.get('grace_secs') or 1)} "
                    f"at this cadence; the receipt comparison is the arm that catches the rest"
                )
                for entry in cov.get("commits", []):
                    lines.append(
                        f"    {'STALE' if entry in (cov.get('stale') or []) else 'within window'}: "
                        f"{entry['sha']} age "
                        f"{entry['age_secs'] if entry['age_secs'] is not None else 'unreadable'}s"
                        f" -- {entry['session_id'] or 'no lane trailer'}: "
                        f"{entry['subject'][:60]}"
                    )
                if leg.get("reason"):
                    lines.append(f"  {leg['reason']}")
            lines.append(f"  read at {cov.get('read_at')}")

        elif leg["name"] == "kit-drift":
            # A leg that did NOT RUN carries a coverage of {reason, read_at} and no
            # totals or members. Reading those unconditionally crashes the renderer on
            # the very path that exists to REPORT the absence -- measured 2026-09-25 in
            # the TEMPLATE copy, where registry/kit.json is factory data and therefore
            # never ships. An absence is a NOT RUN, never a traceback.
            if "manifest_cells" not in cov:
                lines.append(f"  NOT RUN: {cov.get('reason', 'no reason recorded')}")
                if cov.get("manifest_files") is not None:
                    lines.append(f"  manifest: {cov['manifest_files']} file(s) declared")
            else:
                m, b = cov["manifest_cells"], cov["bootstrap_cells"]
                lines.append(
                    f"  manifest: {cov['manifest_files']} file(s), kit_version "
                    f"{cov['kit_version']} — {cov['members_reachable']} of "
                    f"{cov['members_declared']} member repo(s) reachable"
                )
                lines.append(
                    f"  drift over the WHOLE manifest ({cov['manifest_cells_total']} cells): "
                    f"{m['same']} same, {m['DIFF']} DIFF, {m['ABSENT']} ABSENT"
                )
                lines.append(
                    f"  drift over the BOOTSTRAP-NAMED set ({cov['bootstrap_cells_total']} cells): "
                    f"{b['same']} same, {b['DIFF']} DIFF, {b['ABSENT']} ABSENT — the predicate the "
                    f"1/20/29 baseline was measured over"
                )
                for member in cov.get("members", []):
                    if not member["reachable"]:
                        lines.append(f"    {member['slug']}: UNREACHABLE ({member['root']})")
                        continue
                    lines.append(
                        f"    {member['slug']}: same={member['same']} DIFF={member['DIFF']} "
                        f"ABSENT={member['ABSENT']}"
                    )
                    for name in member["absent_files"][:6]:
                        lines.append(f"      absent: {name}")
                    if len(member["absent_files"]) > 6:
                        lines.append(f"      ... and {len(member['absent_files']) - 6} more absent")
            lines.append(f"  read at {cov['read_at'] or 'unstated'}")
        elif leg["name"] == "board-ruling":
            lines.append(
                f"  rulings issued on the board (openings {', '.join(cov['headings'])}): "
                f"{cov['rulings_issued']} examined over {cov['issues_read']} "
                f"issue(s) read, {len(leg['problems'])} problem(s) — board read at "
                f"{cov['board_read_at']}"
            )
            # The clause that keeps the alternation honest (#245). The count is printed
            # BESIDE the verdict and the lines follow, so a spelling the predicate could not
            # place is visible on the run that first meets it. The canonical head is named
            # in the same breath: a reader who meets a novel head here is told what the
            # convention expects, rather than left to infer it from the tuple above.
            lines.append(
                f"  heading comments the ruling predicate did NOT match: "
                f"{cov['unmatched_heads_examined']} over "
                f"{len({u['issue'] for u in cov['unmatched_heads']})} issue(s) — "
                f"the convention names {cov['canonical_heading']!r}; a novel spelling is "
                f"printed here rather than being indistinguishable from absent"
            )
            for entry in cov["unmatched_heads"]:
                lines.append(f"    ~ #{entry['issue']}: {entry['head']}")
        elif leg["name"] == "worktree":
            # NOT RUN carries its reason here like the other legs; ASSERTED prints the
            # population, the two hazard classes WITH THEIR PATHS, and an explicit
            # "removes: no" so a reader cannot mistake the report for a reaper (#220).
            if leg["status"] == "NOT RUN":
                lines.append(f"  NOT RUN: {cov.get('reason') or 'reason not stated'}")
                lines.append(f"  read at {cov.get('read_at') or 'unstated'}")
                lines.append(f"  excused: {len(leg['excused'])}")
                lines.append(f"  problems: {len(leg['problems'])}")
                lines.append("")
                continue
            lines.append(
                f"  worktrees: {cov['worktrees_total']} total, "
                f"{cov['worktrees_scratch']} scratch (the class the cleanliness "
                f"instrument's glob cannot reach) — {cov['instrument']}"
            )
            lines.append(
                f"  residue is REPORTED, never removed (removes: "
                f"{'yes' if cov['removes'] else 'no'}); a lane removes its OWN tree"
            )
            lines.append(
                f"  {cov['hazard_classes'][0]} (commits not reachable from "
                f"{cov['base_ref']}): {len(cov['unreachable_commits'])} tree(s)"
            )
            for entry in cov["unreachable_commits"]:
                lines.append(f"    ~ {entry['path']} — {entry['ahead']} commit(s) ahead")
            lines.append(
                f"  {cov['hazard_classes'][1]} (paths differing from HEAD): "
                f"{len(cov['uncommitted_work'])} tree(s)"
            )
            for entry in cov["uncommitted_work"]:
                lines.append(f"    ~ {entry['path']} — {entry['paths']} path(s)")
            if cov["missing_directory"]:
                lines.append(
                    f"  registrations whose directory is GONE (what `git worktree prune` "
                    f"clears): {len(cov['missing_directory'])}"
                )
                for path in cov["missing_directory"]:
                    lines.append(f"    ~ {path}")
            lines.append(f"  read at {cov['read_at']}")
        elif leg["name"] == "pacemaker-presence":
            # The EXAMINED POPULATION travels with the verdict, so a clean read over zero
            # owners is never indistinguishable from a verified one (#242). Every owner is
            # named with its resolved session and the row that wakes it, or NONE.
            lines.append(
                f"  register: {cov['register']} — {cov['owners_declared']} owner(s) "
                f"declared"
            )
            lines.append(
                f"  rows judged: {cov['rows_judged']} of this factory's enabled row(s) "
                f"({cov['unattributed_rows']} attributed to nobody), across "
                f"{cov['homes_read']} home(s) read"
            )
            lines.append("  population (owner — resolved session — the wake that satisfies it):")
            for entry in cov.get("owners", []):
                lines.append(f"    {entry}")
            for note in cov.get("resolution_notes", []):
                lines.append(f"    note: {note}")
            lines.append(f"  read at {cov['read_at']}")
        elif leg["name"] == "stall-census":
            lines.append(
                f"  dispatch rows examined: {cov['dispatch_rows_examined']} "
                f"({cov['observation_dispatches']} observation dispatch(es), explicitly "
                f"legal; {cov['carried_units_resolved']} carried unit(s) resolved, "
                f"{cov['units_off_board']} unit(s) dropped as not an OPEN issue of this "
                f"board)"
            )
            lines.append(
                f"  population: {cov['units_in_population']} dispatched unit(s) -- "
                f"{cov['units_owed']} never claimed past the declared threshold of "
                f"{cov['threshold_days']} d"
            )
            lines.append(f"  threshold basis: {cov['threshold_basis']}")
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
    closed_items = sum(
        int(leg["coverage"].get("closed_items_examined", 0)) for leg in legs
    )
    cron = sum(
        int(leg["coverage"].get("rows_attributed", 0)) for leg in legs
    )
    notify = sum(
        int(leg["coverage"].get("logs_matched", 0)) for leg in legs
    )
    owed = sum(
        int(leg["coverage"].get("units_owed", 0)) for leg in legs
    )
    owners_declared = sum(
        int(leg["coverage"].get("owners_declared", 0)) for leg in legs
    )
    lines.append(
        f"verdict: {total} problem(s) over {forward} open issue(s) examined, "
        f"{closes} close row(s) checked against the board, "
        f"{closed_items} closed item(s) checked for a close row, and {cron} cron row(s) "
        f"attributed to this factory and judged, {owners_declared} declared periodic "
        f"owner(s) checked for an inbound wake, {notify} notify log(s) judged for a "
        f"receipt, and {owed} never-claimed dispatch(es) standing past the declared "
        f"threshold"
    )
    return "\n".join(lines)


def live_pacemaker_presence_leg(rows: list[dict], homes_read: list[str],
                                unreached: list[str], *,
                                prefixes: list[str], read_at: str) -> dict:
    """The live wiring for the presence leg: read the register, the fragment and the bindings.

    EVERY read is guarded, and a read that FAILED becomes a NOT RUN with its reason rather
    than an empty input — an unreadable declaration is not a declaration that names nobody,
    and the two must never render the same. The fragment is read from this repo's own
    `registry/factories/<slug>.json`, so the role→session resolution uses the same declared
    lanes the registry itself publishes rather than a second list kept here.

    The factory's slug is resolved from the fleet manifest by REPOSITORY, never from the git
    remote: the remote reads `owner/repo`, which names no fragment.
    """
    slug = declared_slug()
    if not slug:
        return pacemaker_presence_leg(
            rows, [], None, None, read_at=read_at, prefixes=prefixes,
            homes_read=homes_read, unreached=unreached,
            not_run_reason=(
                f"this checkout resolves to no factory the fleet manifest declares, so its "
                f"fragment — and therefore every role→lane mapping — is unknown; presence "
                f"cannot be checked for an undeclared factory (board #242)"
            ),
        )
    try:
        register_text = PRESENCE_REGISTER.read_text(encoding="utf-8")
    except OSError as exc:
        return pacemaker_presence_leg(
            rows, [], None, None, read_at=read_at, slug=slug, prefixes=prefixes,
            homes_read=homes_read, unreached=unreached,
            not_run_reason=(
                f"the process register {PRESENCE_REGISTER} could not be read ({exc}) — the "
                f"independent declaration of who owes a pacemaker is unavailable, so no "
                f"owner could be checked and this is NOT a clean read"
            ),
        )
    registry = load_module("oc_registry", REGISTRY)
    fragment: dict | None = None
    if slug:
        fragment, ferr = registry.load_fragment(FACTORY_FRAGMENT_DIR / f"{slug}.json")
        if ferr or not isinstance(fragment, dict):
            return pacemaker_presence_leg(
                rows, [], register_text, None, read_at=read_at, slug=slug, prefixes=prefixes,
                homes_read=homes_read, unreached=unreached,
                not_run_reason=(
                    f"this factory's fragment "
                    f"({FACTORY_FRAGMENT_DIR / f'{slug}.json'}) could not be read "
                    f"({ferr or 'not a mapping'}) — the role→lane declaration is unavailable, "
                    f"so no owner's session could be resolved"
                ),
            )
    try:
        bindings, berrors = registry.all_bindings()
    except Exception as exc:  # noqa: BLE001 — any failure here is a NOT RUN, never empty
        bindings, berrors = [], [str(exc)]
    if berrors and not bindings:
        return pacemaker_presence_leg(
            rows, [], register_text, fragment, read_at=read_at, slug=slug, prefixes=prefixes,
            homes_read=homes_read, unreached=unreached,
            not_run_reason=(
                f"no live session binding could be read ({'; '.join(berrors[:3])}) — every "
                f"owner's session would be unresolved, which is a read failure and not a "
                f"finding about the pacemakers"
            ),
        )
    return pacemaker_presence_leg(
        rows, bindings, register_text, fragment, read_at=read_at, slug=slug,
        prefixes=prefixes, homes_read=homes_read, unreached=unreached,
    )

def main(
    argv: list[str] | None = None,
    *,
    board_fn=fetch_board,
    slug_fn=remote_slug,
    rows_fn=load_rows,
    cron_rows_fn=box_cron_rows,
    prefixes_fn=declared_prefixes,
    log_dir: Path = LOG_DIR,
    kit_manifest: Path | None = None,
    fleet_manifest: Path = FLEET_MANIFEST,
    predicate=None,
    publish_fn=None,
    worktree_fn=None,
    presence_fn=None,
    out=print,
    err=print,
) -> int:
    """Run the patrol read. Every dependency is injectable, so a probe drives it
    without a live board — and a probe that can only run against the live board is
    a probe that cannot be run at all when the board is what is broken. The cron read
    and the prefix declaration are injected for the same reason: a probe drives the
    cron-thinness leg with NO live database. The two drift manifests are injected for the
    fourth: the kit-drift leg's population is five OTHER repositories, so a probe that
    could only run against the live box would be measuring whatever those trees happen to
    hold rather than the leg's behaviour. `kit_manifest` defaults to None, which is the
    LIVE reference: the leg then reads the manifest from HEAD rather than from disk (issue
    #185). A probe passes a path and keeps the disk read, so no probe's fixture changed
    meaning when the live default did. The publish leg is injected for the fifth and
    the most practical reason of all: it reads the remote, so a probe that did not stub it
    would make a NETWORK call on every run of every probe that drives this function --
    measured at ~2s each, which is how a 3s gate becomes a 40s one.

    The worktree leg reads the live box for the sixth time and for the sharpest version of
    the same reason: it shells out TWICE PER REGISTERED WORKTREE, so a probe that did not
    stub it would pay that cost on every run of every probe that drives this function --
    measured at ~10s on a box with 34 worktrees, which is a gate budget spent on state the
    probe never asserts.

    The presence leg is injected for the seventh and the same practical reason: it reads the
    process register, the factory fragment and every profile's session bindings, so a probe
    that did not stub it would need a live box with those files in place to assert a NOT RUN
    reason at all. `presence_fn` is handed the same cron rows, homes and prefixes the other
    cron legs receive."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", help="override the owner/repo derived from the remote")
    args = parser.parse_args(argv)

    read_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        slug = args.repo or slug_fn()
        issues = board_fn(slug)
        rows = rows_fn()
    except BoardReadError as exc:
        # A board that could not be read is NOT a board with nothing on it. The run
        # aborts BEFORE any leg is built, so every leg is declared NOT RUN by NAME with
        # the reason — a leg that could not read its input must never render as one that
        # examined nothing and passed (#242), and NO verdict is printed at all, because a
        # verdict over zero issues reads as a clean patrol.
        err(f"patrol host-state read: FAILED at {read_at} — {exc}")
        err(
            "NOT RUN: every leg (board-intake, board-close, board-closed, board-ruling, "
            "cron-thinness, pacemaker-presence, notify-receipt, duty-receipt, "
            "canonicality-tier, stall-census, "
            "kit-drift, "
            f"publish-freshness, worktree) — the run aborted at the board read at "
            f"{read_at}, so no leg was built"
        )
        return 2

    cron_rows, homes_read, unreached = cron_rows_fn()
    legs = [
        board_intake_leg(issues, rows, predicate=predicate),
        board_close_leg(issues, rows, read_at=read_at),
        board_closed_leg(issues, rows, read_at=read_at, predicate=predicate),
        board_ruling_leg(issues, rows, read_at=read_at, predicate=predicate),
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
        stall_census_leg(issues, rows, read_at=read_at),
        kit_drift_leg(manifest_path=kit_manifest, fleet_path=fleet_manifest,
                      read_at=read_at),
        (publish_fn or publish_freshness_leg)(read_at=read_at),
        (worktree_fn or worktree_leg)(read_at=read_at),
        (presence_fn or live_pacemaker_presence_leg)(
            cron_rows, homes_read, unreached, prefixes=prefixes_fn(),
            read_at=read_at,
        ),
    ]
    deferred = deferred_legs()
    deferred_problems = deferred_entry_problems(deferred)
    out(render(legs, deferred, slug=slug, read_at=read_at, issues=issues,
               deferred_problems=deferred_problems))
    return 1 if any(leg["problems"] for leg in legs) or deferred_problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
