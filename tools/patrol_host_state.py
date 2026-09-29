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
import re
import sqlite3
import subprocess
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
KIT_MANIFEST = REPO / "registry" / "kit.json"
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
# the box: `oc-triage-factory-patrol` says "it was 5,289 chars of pasted law on
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

# ---- the board-ruling leg (issue #223, ruled at ledger n=1596) -----------------------
#
# A ruling posted as a board comment leaves no `ruling` row, and NOTHING asked for one:
# `grep` for a reader of `event == "ruling"` across `tools/*.py` returned ZERO hits — the
# token occurred only at the event tuple and the authorization matrix. So the transition
# was authorized, written by convention, and skipped indefinitely with no surface noticing,
# which is §8's field-with-no-reader shape arriving on the WRITE side. Eight of one lane's
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
RULING_HEADINGS = ("## RULED", "## RULING")

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
        if str(comment.get("body") or "").lstrip().startswith(RULING_HEADINGS):
            return comment
    return None

def board_ruling_leg(issues: list[dict], rows: list[dict], *, read_at: str,
                     predicate=None) -> dict:
    """The live board-ruling leg: a ruling comment with no `ruling` row is reported (#223).

    Population: every board issue carrying a ruling comment — derived AT RUN TIME from the
    board the read returned, never a literal, so the count moves with the board and cannot
    go stale in the code. Returned as `ruling_comments_examined` and printed beside the
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
    for row in rows:
        if row.get("event") != "ruling":
            continue
        number = predicate.issue_reference(row.get("subject"))
        if number is not None:
            ruled.add(number)

    problems: list[str] = []
    examined = 0
    for issue in issues:
        number = issue.get("number")
        if not isinstance(number, int):
            continue
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
            "ruling_comments_examined": examined,
            "issues_read": len(issues),
            "board_read_at": read_at,
            "headings": list(RULING_HEADINGS),
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


def embedded_law_content(prompt: str) -> tuple[str, str]:
    """(embedded instant, bare date) for one prompt — at most one of them is non-empty.

    The two are RETURNED APART rather than folded into one verdict, because they are
    different findings: an instant is drift-prone STATE and is judged, while a bare date is
    a citation of the past and is only REPORTED. Collapsing them would make the citation
    indistinguishable from the state, which is the false positive this class measured on
    the box's own best-shaped row (`oc-triage-factory-patrol`, whose bare date sits in a
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

def kit_drift_leg(
    *,
    manifest_path: Path = KIT_MANIFEST,
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

    if not manifest_path.is_file():
        problems.append(
            f"the kit manifest {manifest_path} is absent — there is no reference to measure "
            f"drift against, so this leg examined NOTHING and says so rather than reporting "
            f"a clean sweep over no population"
        )
        return {"name": "kit-drift", "status": "NOT RUN", "problems": problems,
                "excused": [], "coverage": {"reason": str(manifest_path), "read_at": read_at}}

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"the kit manifest {manifest_path} could not be read: {exc}")
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
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    coverage = {
        "remote": remote,
        "branch": branch,
        "read_at": read_at,
        "residual_secs": PUBLISH_RESIDUAL_SECS,
        "grace_secs": PUBLISH_GRACE_SECS,
        "cadence_secs": PUBLISH_CADENCE_SECS,
        "unpushed": 0,
        "shas": [],
        "stale": [],
        "remote_tip": None,
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
                f"  ruling comments on the board (openings {', '.join(cov['headings'])}): "
                f"{cov['ruling_comments_examined']} examined over {cov['issues_read']} "
                f"issue(s) read, {len(leg['problems'])} problem(s) — board read at "
                f"{cov['board_read_at']}"
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
    kit_manifest: Path = KIT_MANIFEST,
    fleet_manifest: Path = FLEET_MANIFEST,
    predicate=None,
    publish_fn=None,
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
    hold rather than the leg's behaviour. The publish leg is injected for the fifth and
    the most practical reason of all: it reads the remote, so a probe that did not stub it
    would make a NETWORK call on every run of every probe that drives this function --
    measured at ~2s each, which is how a 3s gate becomes a 40s one."""
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
        kit_drift_leg(manifest_path=kit_manifest, fleet_path=fleet_manifest,
                      read_at=read_at),
        (publish_fn or publish_freshness_leg)(read_at=read_at),
    ]
    deferred = deferred_legs()
    deferred_problems = deferred_entry_problems(deferred)
    out(render(legs, deferred, slug=slug, read_at=read_at, issues=issues,
               deferred_problems=deferred_problems))
    return 1 if any(leg["problems"] for leg in legs) or deferred_problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
