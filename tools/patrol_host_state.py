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

Seven things it does deliberately:

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
  and its DECLARED bound (`INVARIANT_KEY`, resolved through the one boundary reader)
  so the two surfaces cannot drift into two definitions of one field. Freshness stays REPORTED — the read instant travels with the count and
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

- **Names the shared tree's blocking paths, with the instant** (#241). The board legs read
  ONE tree, and a tree another lane is mid-write on makes their verdicts unattributable —
  measured 2026-09-29, when the fork produced FALSE verdicts and no single location gave a
  wholly correct read. The rider prints the dirty paths `origin/main` also moved (the class
  that makes `git reset --keep origin/main` refuse), the instant it read them, and NOT RUN
  with its reason when the tree cannot be read. It carries no problem and cannot move the
  exit code: a STANDALONE detection leg was refused as #83's class, so it rides the board
  legs rather than standing beside them.

The board slug is derived from the git remote, so nothing here hardcodes a factory.

Run:  python3 tools/patrol_host_state.py
Exit: 0 no problems, 1 problems found, 2 the board could not be read.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import statistics
import subprocess
import sys
import zoneinfo
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

# THE RECEIPT'S RESIDUAL (#445), stated because a per-repository record carries a
# per-repository hazard. The receipt is ONE file per REPOSITORY, in the git common dir, so
# every worktree of this repository reads the SAME record -- which is the fix: before #445 it
# sat under `evidence/`, was gitignored, and was therefore CHECKOUT-LOCAL, so this leg
# compared a GLOBAL remote tip against whichever checkout happened to be reading and the same
# tip produced a finding in one worktree and silence in another. The residual of the new
# shape is that the record is LAST-WRITER-WINS: it names the MOST RECENT push from ANY
# worktree, never this checkout's own push. That is by design -- one record, one repository --
# and it is STATED here rather than asserted away. `checkout` in the receipt body says which
# worktree wrote the record being read.
PUBLISH_RECEIPT_RESIDUAL = (
    "the receipt is ONE record per repository (git common dir) and is LAST-WRITER-WINS: it "
    "names the most recent push from ANY worktree of this repository, never this checkout's "
    "own push -- `checkout` in the receipt says which worktree wrote the record being read"
)

# THE DUTY RESIDUAL (#449), DERIVED per job rather than declared once for the fleet.
#
# A round's receipt lands when the lane the trigger woke FINISHES ITS TURN, and the leg
# cannot read a lane's turn -- so a round young enough that its lane is plausibly still
# working must not be judged. That window is a property of the JOB, not of the leg, and the
# fleet constant this replaced (`DUTY_RESIDUAL_SECS = 1800`, #200) was derived from the
# population of rounds that cleared FAST -- so it excluded by construction the very rounds
# the window exists to protect. Measured 2026-09-28 (n=1518): of 29 fire->receipt latencies,
# 22 (75.9%) sat ABOVE it, max 6.90 h. #449 recorded the harm live: the 06:00Z
# `factory-measurement-daily` duty runs 44.6-178 min while `factory-hq-pacemaker` reads it at
# 06:50Z, so EVERY 06:50Z round read a working duty MISSING.
#
# THE FORM is the gate-budget law's (`tools/gate_budget.py`), because that law already states
# how a measured runtime becomes a cap -- `budget_sec = margin_for(measured_sec) x measured_sec`,
# with `margin_for(m) = MARGIN_ASYMPTOTIC + MARGIN_FIXED_SEC/m`. The measurement is the job's
# OWN measured max fire->receipt latency, read at THIS instant from the daemon's own fire
# records (`cron_job_runs.started_at`) paired with the ledger's own receipt rows -- the
# predicate n=1518 used. `margin_for` is BOUND to that module, never re-derived: one field,
# one predicate (SKILL.md section 11).
#
# THE RESIDUAL IS NOT CLAMPED TO THE CADENCE, and an over-cadence value is PRINTED rather
# than refused. For a duty whose own measured max exceeds its cadence the two requirements
# are mutually unsatisfiable (n=1518 FINDING 3): a residual covering the observed max
# outlives the next fire, and one short enough to stay under the cadence reads the duty's own
# real rounds as MISSING. Clamping would hide that; the honest output is the number AND the
# statement that this window cannot discriminate for that duty. The residual and the job's
# own observed cadence are both printed, so the reader makes the call.
DUTY_RESIDUAL_DEFAULT_SECS = 1800
DUTY_RESIDUAL_DEFAULT_BASIS = (
    "1800 s -- the pre-#449 fleet constant, retained as the DEFAULT for a job with no "
    "measurable round. A job that has never receipted has no measured max to derive from, "
    "and the two error directions are not equal: a short window judges a round the leg "
    "cannot yet clear (a false MISSING, which costs one look), while a long one is SILENT "
    "(#160). The default errs SHORT."
)
DUTY_RESIDUAL_ZERO_BASIS = (
    "1800 s -- the same default, applied because the max measured latency is NON-POSITIVE "
    "rather than absent (#500). `margin_for` is shared law in `tools/gate_budget.py` and "
    "divides by its argument (`4.0 + 0.75/x`), so a measured max of 0.0 raises "
    "ZeroDivisionError -- and because this runner builds its legs in ONE list with no "
    "try/except, that exception takes the WHOLE round down and every leg after it never "
    "runs. The guard therefore lives HERE, at the caller, and never in `margin_for`: that "
    "predicate is pinned by its own probes, so `margin_for(0.0)` must still raise at the "
    "bytes. `measured_rounds` stays in the record, so the reading is STATED, not silent."
)
DUTY_RESIDUAL_FORM = (
    "budget_sec = margin_for(measured_max) x measured_max, in the gate-budget law's form "
    "(`tools/gate_budget.py`) -- the job's OWN measured max fire->receipt latency, from the "
    "daemon's fire records paired with the ledger's receipt rows"
)
# The gate-budget module, reached by PATH through `load_module` like every sibling above: this
# runner is copied into every member factory, where a module-level import would break the load.
GATE_BUDGET = REPO / "tools" / "gate_budget.py"

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

# --- the dispatch-delivery leg (#49, ruled at ledger n=1893) -------------------------
#
# A `dispatch` ROW IS A CLAIM THAT A LANE WAS TOLD, and nothing tied the row to the
# `session_notify` that carries the brief. Measured 2026-09-18 in BOTH directions: `#41`/
# `#42` delivered with no row, `#48` a row (n=276) with NO delivery — the row appended and
# committed by a turn a restart killed between the append and the notify, so the ledger
# reported a routing that had not happened. This leg is shape (3) of that item, the
# EVIDENCE half; `tools/ledger.py`'s write-path refusal is shape (1), the SEAM half.
#
# THE WINDOW IS ANCHORED ON THE ROW UNDER TEST, and the ruling says why in terms: the
# first census anchored on each subject's NEWEST dispatch row, so `#77`'s window opened
# AFTER the delivery it was testing for and reported a confident miss. The bound is taken
# from the row under test, always.
#
# ... AND THE ROW'S `ts` IS AN UPPER BOUND ON ITS DISPATCH, NOT THE INSTANT ITSELF (#432).
# A row's `ts` is a WRITE instant (`tools/ledger.py::now_iso()` at append), so a lane that
# stamps its dispatch row LATER than it dispatched -- a batched ledger write -- postdates the
# dispatch, and the window's backward bound then lands AFTER a genuine delivery. Measured
# 2026-10-07: row `n=2787` (`#428`) carries `ts 12:26:04Z` while its own detail declares
# `resolved_at 2026-10-07T12:11:46Z`, and the notify landed at `12:11:28Z` -- 11m36s before
# the window the leg chose, reported as "records no delivery" for a delivery that woke the
# very lane that ruled the item. Where the row's own detail DECLARES its dispatch instant the
# anchor is the EARLIER of the two, which widens the search backward and can only turn a
# false RED into a clean one.
#
# THE TOKEN MUST BE NO NARROWER THAN THE ARTIFACT. A delivered notify may carry the bare
# subject number (`77`), the hash-prefixed form (`#77`), or a descriptive stem. The first
# census searched `#77` where the artifact carried `77`, and returned a zero that read as
# good news — worse than no leg. So the match accepts every form the artifact may take.
#
# AND THE LEG CARRIES TWO VERDICTS, NOT ONE (#432). "No delivery exists" and "a delivery
# exists but outside the window the leg chose" are different facts, and reporting both as
# "records no delivery" is a FALSE ABSENCE -- the condition that recurs and sends a reader
# off to re-dispatch an item the target already holds. So a match found ANYWHERE in the store
# is reported as a WINDOW MISMATCH, naming the delivery's own instant; only a store carrying
# no match at all reads as the absence.
DELIVERY_BOUNDARY_KEY = "dispatch_delivery_declared"
DELIVERY_WINDOW_BEFORE_SECS = 180
DELIVERY_WINDOW_AFTER_SECS = 5400
DELIVERY_WINDOW_BASIS = (
    "anchored on each dispatch row's OWN instant: [anchor - 180 s, anchor + 5400 s] -- three "
    "minutes of clock skew behind the stamp, ninety minutes of delivery lag ahead. The anchor "
    "is the row's `ts` (a WRITE instant) or the earlier instant its own detail DECLARES, "
    "whichever is earlier (#432). Anchoring on a subject's NEWEST row opened the window after "
    "the delivery it tested for (#77, ledger n=1893), so the bound is always the row under "
    "test's own instant."
)
# THE ROW'S OWN DECLARED DISPATCH INSTANT (#432), held as a DECLARED TUPLE of (form, regex)
# pairs so a further declaration form is a one-line addition -- the same shape
# `NOTIFY_DELIVERY_HEADERS` uses for the header forms (#426). The forms are NOT a licence to
# parse free prose loosely: each names the token AND its value, so a row whose detail merely
# MENTIONS an instant (a quoted window, another row's stamp) declares nothing.
DISPATCH_DECLARED_INSTANT_FORMS = (
    ("resolved_at", re.compile(r"\bresolved_at\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)")),
)
# THE OUTER BOUND ON "A DELIVERY EXISTS SOMEWHERE" (#432). The window itself is the 90-minute
# band a delivery is EXPECTED in; this is the band in which a match counts as a delivery AT
# ALL. It is needed because a match is a SUBJECT MENTION, not a proof of routing: measured on
# this box at the 2026-10-07T18:05Z read, the `#432` dispatch row's own target held FORTY-NINE
# deliveries carrying `#432` -- the oldest 19 days before the dispatch, almost all of them
# compaction summaries quoting the lane's task list -- so an unbounded "exists elsewhere" search
# reports a delivery for a brief that had not been sent. A brief is not delivered a day away
# from its dispatch: the measured late-stamp slip is minutes (the specimen: 14m36s), so a day
# either side is generous by orders of magnitude and still leaves FIVE of those forty-nine
# inside the band.
DELIVERY_MATCH_HORIZON_SECS = 86400
# THE BOUND ON A ROW'S OWN DECLARED INSTANT (#476). The declared-instant form is a PHRASE
# MATCH, so a detail that QUOTES the token as evidence about a DIFFERENT artifact declares it
# as its own dispatch instant -- the hole #432 left open. Measured on this ledger 2026-10-13:
# row `n=3215` (#474's dispatch) quotes the stale `registry/state.json` snapshot's
# `resolved_at 2026-10-05T13:01:19Z` AS A MEASUREMENT, and the anchor rule built the judged
# window 8 days early, printing "records no delivery" for a dispatch that had landed one
# second before the row's own write stamp. `n=3226` is the second instance, found within the
# hour by the lane that wrote it.
# The bound separates the DESIGNED population from a quote, with margin on both sides: the
# largest lag among the 45 designed declarations is 1675 s (51.6x headroom under the bound),
# while the two quoted instances are 672779 s and 672598 s (7.8x past it). A quote INSIDE the
# horizon is NOT separated by this rule; that residual is stated in the #476 ruling rather
# than papered over, and a third instance carrying a RECENT quote is the signal for the
# schema-side field, not a third application of this bound.
DECLARED_INSTANT_MAX_LAG_SECS = 86400
# THE SCOPE OF A DELIVERY'S HEADER (#433), in LINES, so "the header" is a DECLARED quantity
# rather than a number hidden in a function. A dispatched notify NAMES ITS SUBJECT in its
# opening line -- `TRIAGE DISPATCH — #428 (law: ...)`, `[factory dispatch] #432 — WORK ITEM`,
# `DISPATCH #423 -> the Worker lane` -- while a message that merely TALKS about the subject
# carries it in the body, hundreds of characters and many lines further down. Measured
# 2026-10-07 on the `#428` specimen: the genuine delivery at offset 78 (line 3, the sender's
# opening line after a blank line) and the mention that also cleared the row at offset 868
# (line 10, a queue list). The count is the number of NON-BLANK lines
# after the envelope that count as the header, and it is ONE because that is what every
# measured dispatch form uses; a factory whose notices open with a two-line banner raises it
# here rather than being read as undelivered.
DELIVERY_HEADER_LINES = 1
NOTIFY_DELIVERY_HEADER = "[session-notify from="

# THE TWO HEADER FORMS THE HARNESS WRITES, held as a DECLARED TUPLE so a third form is a
# one-line addition (#426). Both are REAL, measured 2026-10-07 in a live store: one session
# held `[session-notify from=cli:Gatus]` and another `📨 notify from cbdfde4a:`. The leg read
# only the first, so a notify that LANDED in the emoji form read as a phantom dispatch --
# four RED rows (n=2749-2752) that were a predicate artefact, not undelivered dispatches.
#
# A bare substring (`notify from`) is NOT the fix: a message QUOTING a header would then read
# as landed (the reader-echo class, AGENTS.md rule 7), so each form carries its own boundary.
NOTIFY_DELIVERY_HEADERS = (
    NOTIFY_DELIVERY_HEADER,
    "📨 notify from ",
)

# --- the board-unruled leg (#332) ----------------------------------------------------
#
# THE ROUND'S OWN PREDICATE, ASSERTED BY NOTHING. The meta-factory HQ round's whole job is
# to sweep the board's population of OPEN items that carry an `intake` row and NO `ruling`
# row, and no leg watched that class. The two neighbouring legs are blind to it BY
# CONSTRUCTION rather than by accident: `board_intake_leg` asserts the INTAKE direction
# (an open item must have an intake row), so an item that HAS one is never a candidate; and
# `board_ruling_leg`'s population is "every board issue carrying a ruling COMMENT", so an
# item with no ruling row has no ruling comment either and is outside its population too.
# Measured 2026-10-05 (#332): #327 carried intake n=2380 at 12:07:20Z, was OPEN, and had no
# `ruling` row when that lane's own 12:50Z round swept -- it was ruled only after the
# predicate was re-run following a context compaction (n=2410, 13:12:34Z). The miss was
# found by a re-run, not by an instrument, which is the #118 class (a class with no machine
# watcher) landing on the sweep's own duty.
#
# WHY THE THRESHOLD IS 6.0 h, TAKEN FROM THE ROUND'S OWN CADENCE. A fresh intaken item is
# NOT a defect: the round that owes it a ruling has not yet been due, and a leg that fired
# on arrival would red every filing for the minutes before its ruling. The round's own
# receipts date its cadence -- the `hq-cycle-*` receipt rows on this ledger sit at 00, 06
# and 12 on 2026-10-05, gaps p50 5.06 h / max 6.24 h (5 rows: a thin sample, and it is the
# round's OWN record, which is the only declaration of the cadence that exists) -- so one
# full cadence is the shortest interval in which a healthy round has demonstrably swept the
# item and left it unruled. Below it the item is in flight; at or above it the round has
# passed over it. The threshold is PRINTED with this basis on every run, never carried in a
# reader's memory.
BOARD_UNRULED_THRESHOLD_HOURS = 6.0
BOARD_UNRULED_THRESHOLD_BASIS = (
    "6.0 h -- one full HQ round cadence. The round's own receipts date it: this ledger's "
    "5 `hq-cycle-*` receipt rows (2026-10-05) sit at 00/06/12 with gaps p50 5.06 h and "
    "max 6.24 h. A fresh intaken item is in flight below this; at or above it the round "
    "that owes the ruling has demonstrably passed over it."
)

# The subject form `#<n>` is the ledger tool's, BOUND rather than re-derived: one field,
# one predicate (SKILL.md section 11).
LEDGER_TOOL = REPO / "tools" / "ledger.py"

# The DECLARED extension surface's one reader (#519). `docs/ledger-invariants.json` carries
# `dispatch_batches` beside the ledger's own invariants, and BOTH the ledger tool and this
# runner read it through `ledger_declaration` — never a second parse, because two readers of
# one declaration are two answers to one question, and the silent one is invisible.
LEDGER_DECLARATION = REPO / "tools" / "ledger_declaration.py"

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

# THE MUST-ADOPT CLASS (#514, ruled at ledger n=3792). A manifest class value, READ from
# the pin's own `classes` map and never derived here: a second classification would be a
# second copy of the declaration, which is the drift class this leg exists to report.
SHARED_SURFACE_CLASS = "shared-surface"

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
# declaration — its whole-detail token scan (`BOARD_TOKEN`) and the KEY its invariant
# boundary is declared under (`INVARIANT_KEY`). The board-close leg below BINDS to both
# rather than re-deriving them: a canonical-trailer read (`trailer_tokens` in
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

# --- an instant in a CITATION is REPORTED, never judged (#478) -------------------
#
# The class above reserves the citation role for BARE DATES and says so in its own words:
# "A bare date is most often a CITATION of when something was decided — the past, not
# state — so it is REPORTED and never judged." The measurement that chose the instant
# predicate assumed instants are always state, and that assumption is falsified by a
# prompt that CITES a ruling whose timestamp happens to be instant-form: `(issue #469,
# ruling 2026-10-11T12:59:43Z)` was returned as the row's own embedded boundary and
# printed as "the prompt is a COPY that drifts", which is a false RED on a ratified row
# (#478, the q44 decision at ledger n=3354 — "admit a bounded chained pipeline AND stop
# judging a citation").
#
# THE CARVE-OUT IS NARROWER THAN THE CLASS, deliberately, and the asymmetry is the point:
# the instant is judged UNLESS its clause names a SOURCE RECORD and asserts no state. Any
# boundary/window/epoch/deadline word in the same clause keeps it judged, so a clause that
# cites a ruling AND sets a window still fires. An exemption that swallows a near-miss
# converts a false RED into a false clean, and the false clean is the expensive direction.
#
# The reported population is PRINTED like the bare-date population beside it: an instant
# dropped silently would be the same defect one layer down.
_CITATION_CLAUSE_BREAKS = ".;:\n—("

CITATION_SOURCE_RE = re.compile(
    r"\b(?:rulings?|ruled|issue|issues|ledger|cited|citation|decided|filed)\b"
    r"|#\d+|\bn=\d+",
    re.IGNORECASE,
)

STATE_ASSERTION_RE = re.compile(
    r"\b(?:boundar(?:y|ies)|windows?|epochs?|deadlines?|cut-?offs?|expir(?:y|es|ing)|"
    r"opens?|closes?|starts?|ends?|since|until)\b",
    re.IGNORECASE,
)

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
# The RUN's own verdict about its delivery (#306, ruling n=2191). `cron_job_runs.status`
# separates the two cases a 0-byte log renders identically, and before #306 nothing in this
# tool read it: a run that REACHED its notify is a FAILED DUTY when its log is empty, while
# a run that never reached its notify is the #139 case and is correctly not judged.
#
# `delivery_failed` sits on the PROBLEM side, never the excuse side. It is the daemon's own
# value for "the notify was attempted and its delivery FAILED" — the ruling names it as the
# value a run whose notify never delivered must carry — and it is measured on this box: all
# 24 rows carrying it also carry `completed_at` and an error naming the failed delivery
# ("Unbaked target URL … reached delivery"). Excusing it would file a failed duty as one that
# never happened, which is the exact inversion #306 exists to end. The vocabulary is the
# DAEMON's and is closed here on purpose — a status this leg does not know is REPORTED rather
# than excused, because excusing an unknown value is how a green signal stops being able to
# observe the failure it is named for (the n=903 class).
RUN_DELIVERED_STATUSES = ("success",)
RUN_UNDELIVERED_STATUSES = ("delivery_failed",)
RUN_COMPLETED_STATUSES = RUN_DELIVERED_STATUSES + RUN_UNDELIVERED_STATUSES
RUN_NOT_COMPLETED_STATUSES = ("interrupted", "error")
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

    `assignees` travels with it for the same reason (#423): the stall-census OWED line
    must not render an assigned-but-unclaimed unit identically to one nobody has touched.
    An assignee is NOT a claim — a claim is a session-derived ledger row — so this is a
    VISIBILITY field only; the OWED verdict is unchanged. Additive, and the legs that do
    not read it ignore it, so the read stays ONE call.

    `body` travels with it for the third and the same reason (#48): the criterion-path leg's
    population is the path a criterion NAMES, and an item's own statement of what it wants
    lives in its BODY — the `comments` field carries every reply but not the item itself, so
    a read without this field left the leg blind to surface 1 of its own ruling (`#172`'s
    acceptance criterion was in the body). Additive, and the legs that do not read it ignore
    it, so the read stays ONE call.
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
            "number,state,title,createdAt,closedAt,body,comments,assignees",
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


def board_intake_leg(issues: list[dict], rows: list[dict], predicate=None,
                     bound=None) -> dict:
    """The live board-intake leg, with its own coverage beside its verdict.

    The BOUND is read through the ONE reader (`tests/ledger_boundary.py`), never carried
    as a literal — see `declared_leg_boundary` for why a boundary is factory data.

    ONLY THE OFFLINE ARM IS BOUND-DEPENDENT. The forward arm compares the board's OPEN
    items to the intake rows and the reverse arm compares the intake rows to the board;
    neither asks when a rule landed. The third arm — a subject carrying a `claim` or a
    `close` with no intake row — excuses anything that predates the gate, so it is the one
    that needs the bound. An undeclared bound therefore leaves the two answerable arms
    JUDGED and reports the third as NOT JUDGED with its reason, rather than sinking a leg
    whose majority needs no bound at all. A declared-but-unreadable bound is a DEFECT and
    refuses the leg outright.

    `bound` is injectable for the reason every other dependency is: a probe must be able
    to drive a pre-boundary instance, a post-boundary one, and a refused bound without the
    live tree's declaration deciding its verdict.
    """
    predicate = predicate or load_predicate()
    key = predicate.INVARIANT_KEY
    text, refusal, skip_reason = (bound or declared_leg_boundary)(REPO, key)
    if refusal:
        # The two bound-independent arms are still measured: what was not judged must not
        # read as what was not there (#242).
        coverage = predicate.board_intake_coverage(
            issues, rows, "", complete_board=True
        )
        coverage.update({"bound_key": key, "bound_refusal": refusal, "bound_reason": ""})
        return {
            "name": "board-intake",
            "status": "REFUSED",
            "problems": [refusal],
            "excused": [],
            "coverage": dict(coverage),
        }
    problems, excused = predicate.board_intake_problems(
        issues, rows, text or None, complete_board=True
    )
    coverage = predicate.board_intake_coverage(
        issues, rows, text, complete_board=True
    )
    coverage.update({"bound_key": key, "bound_refusal": "", "bound_reason": skip_reason})
    if skip_reason:
        excused = list(excused) + [skip_reason]
    return {
        "name": "board-intake",
        "status": "ASSERTED",
        "problems": list(problems),
        "excused": list(excused),
        "coverage": dict(coverage),
    }


def board_close_leg(issues: list[dict], rows: list[dict], *, gate=None,
                    read_at: str, predicate=None, bound=None) -> dict:
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

    The BOUND is read through the ONE reader, from the declaration the GATE itself reads
    (`gate.INVARIANT_KEY`) — never a second copy of the instant, which would go stale
    silently (n=405 clause 5, n=599). A declared-but-unreadable bound REFUSES the leg; an
    UNDECLARED one is a NOT RUN with its reason, because this leg's whole population is
    bound-dependent and judging it unbounded is exactly what the bound exists to stop.
    `bound` is injectable so a probe can drive either arm.
    """
    gate = gate or load_close_board_gate()
    predicate = predicate or load_predicate()
    token, key = gate.BOARD_TOKEN, gate.INVARIANT_KEY
    boundary, refusal, skip_reason = (bound or declared_leg_boundary)(REPO, key)
    if refusal or skip_reason:
        return {
            "name": "board-close",
            "status": "REFUSED" if refusal else "NOT RUN",
            "problems": [refusal] if refusal else [],
            "excused": [],
            "coverage": {
                "close_rows_examined": 0,
                "board_read_at": read_at,
                "declaration_token": token,
                "invariant_boundary": boundary,
                "bound_key": key,
                "bound_refusal": refusal,
                "reason": refusal or skip_reason,
            },
        }
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
            "bound_key": key,
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
# THE BOUNDARY IS READ, NEVER RE-TYPED. It is the instant declared under the close-board
# gate's own `INVARIANT_KEY`, resolved through the one boundary reader (`#428`) — a second
# copy of an instant is a copy that goes stale silently, and a guard that re-types the
# value it guards has already stopped guarding.
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
                     read_at: str, predicate=None, bound=None) -> dict:
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
    token, key = gate.BOARD_TOKEN, gate.INVARIANT_KEY
    boundary, refusal, skip_reason = (bound or declared_leg_boundary)(REPO, key)
    if refusal or skip_reason:
        return {
            "name": "board-closed",
            "status": "REFUSED" if refusal else "NOT RUN",
            "problems": [refusal] if refusal else [],
            "excused": [],
            "coverage": {
                "closed_items_examined": 0,
                "pre_boundary_closed_items": 0,
                "board_read_at": read_at,
                "declaration_token": token,
                "invariant_boundary": boundary,
                "bound_key": key,
                "bound_refusal": refusal,
                "reason": refusal or skip_reason,
                "items_without_close_row": [],
            },
        }
    try:
        bound_ts = gate._parse_ts(boundary)
    except (ValueError, TypeError):
        bound_ts = None

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
        if closed_at is None or bound_ts is None or closed_at < bound_ts:
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
            "bound_key": key,
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

# THE PAIRING READER IS THE SHARED PREDICATE, never a leg-local copy (#511, ruled at
# `n=3845`). `tools/rule.py` posts the board comment and stamps the `ruling` row in ONE
# invocation, and the row's detail ends `comment=<id>` — the pairing that makes the two
# surfaces one act. BOTH halves of that predicate live in `tools/field_predicate.py`:
# `PAIRING_KEY` (the writer's key) and `declared_comment_id` (the reader). This leg asks
# THAT predicate by path — `field_predicate_readers()` below — and never by import, because
# the runner is copied into every member factory where the layout above it is not the same.
#
# A LEG-LOCAL COPY OF THE READ IS THE DEFECT, and that is measured rather than argued
# (ruling `n=3845`). This block used to carry its own `re.search(r"comment=(\d+)", detail)`
# and defend it on the #243 shape-1 ground that the leg owns its ruling-vocabulary readers.
# That ground is about the KEY and the SUBJECT forms; the POSITIONAL question — is this
# token the row's DECLARATION or a QUOTATION — was never asked, and a first-match scan
# answers it wrongly on rows that already exist:
#   n=3029 (#455) quotes a #454 act's `comment=6091047134` in prose and DECLARES
#                 `comment=6091268072` in its canonical run — first-match pairs the citation.
#   n=2135 (#297) carries the prose placeholder `comment=123456` and DECLARES
#                 `comment=5973889388` — first-match pairs the placeholder.
# `declared_comment_id` reads the CANONICAL TRAILER RUN only (`trailer_tokens`: the maximal
# run of `=`-carrying tokens at the END of the detail) and digit-filters it, so a quotation
# cannot shadow a declaration and `comment=none` reads as ABSENT. That is the SAME predicate
# the write path refuses on (`tools/ledger.py append --event ruling`), so the writer and the
# reader cannot disagree about what a row declares (SKILL.md section 11, one field one
# predicate; #297 clause 2).

# THE ID SPACE IS NUMERIC, and that is a measured trap rather than a preference. The board
# read returns GraphQL node ids (`IC_kwDOUWc1QM8AAAAB...`) in `comments[].id`, while the
# write path parses the post's own URL and stamps `#issuecomment-<digits>`. Comparing the
# two id spaces matches nothing, and a predicate that did so would report EVERY ruling as
# unpaired — a false red of the whole population, indistinguishable in shape from the false
# clean #511 removes. So the leg parses the same URL fragment the writer parses
# (`comment_numeric_id` below) and keeps the node id for the exemption surface only.
_COMMENT_URL_FRAGMENT = re.compile(r"#issuecomment-(\d+)")


def comment_numeric_id(comment: dict) -> str:
    """The numeric id from a comment's own URL, or "" when the read carried none.

    EMPTY IS A FAIL-CLOSED SIGNAL, never a pass: a comment whose id this leg cannot read
    cannot be shown to be paired, and reporting it as paired would be the false clean the
    leg exists to prevent. The caller reports it as a problem.
    """
    match = _COMMENT_URL_FRAGMENT.search(str(comment.get("url") or ""))
    return match.group(1) if match else ""


def ruling_paired_comment_ids(rows: list[dict], predicate=None) -> dict[str, list]:
    """`comment=<numeric id>` -> the `n`s of the RULING rows that DECLARE it (#511).

    RULING ROWS ONLY, and the narrowing is the point. The leg's claim is "the ledger holds
    no `ruling` row NAMING it"; the write path stamps exactly one event with the pairing
    trailer. A `dispatch` or `run` row that cites the same id is a CITATION of the ruling
    act — #455 carries such a row — never its record, so scanning every row's `comment=`
    field would let a citation excuse an unrecorded ruling: the same false clean, one layer
    down. The `n`s travel so a problem can name the row it found.

    THE VALUE IS READ THROUGH THE SHARED PREDICATE (`field_predicate.declared_comment_id`),
    never a local scan, and the POSITION is why (ruling `n=3845`). A first-match regex over
    the whole detail reads a row that QUOTES another act's `comment=` in prose as declaring
    that act: `n=3029` pairs a #454 citation instead of its own `comment=6091268072`, and
    `n=2135` pairs the placeholder `123456` instead of `comment=5973889388`. The predicate
    reads the CANONICAL TRAILER RUN only, which is the row's declaration by definition, and
    digit-filters it, so `comment=none` reads as ABSENT rather than as a pairing.
    """
    predicate = predicate or field_predicate_readers()
    paired: dict[str, list] = {}
    for row in rows:
        if row.get("event") != "ruling":
            continue
        declared = predicate.declared_comment_id(str(row.get("detail") or ""))
        if declared:
            paired.setdefault(declared, []).append(row.get("n"))
    return paired


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


def resolve_ruling_issue(
    ruling: dict, rows: list[dict], predicate
) -> tuple[int | None, str, dict | None]:
    """`(issue, arm, bridge)` for a ruling row — the arm NAMED and its SOURCE row named too.

    `arm` is `"strict"`, `"declared"` (`governs=`), `"bridged"` or `"unbridgeable"`. The
    tier is reported rather than implied, the same discipline the canonicality ladder uses:
    a resolution that does not say how it was reached cannot be re-litigated when the
    vocabulary moves.

    `bridge` is the row that SUPPLIED a `"bridged"` resolution — `{"n": ..., "event": ...}`
    — and `None` for every other arm (#551, ruling n=4157). The third element exists
    because the arm alone says HOW a resolution was reached and nothing about WHAT reached
    it: the bridge is any OTHER row whose `detail` merely MENTIONS `n=<this row>`, so to
    this predicate ownership and evidence are the same substring. Measured before the fix:
    16 of 28 bridged rulings attribute to an issue their own detail never names (`n=826`
    bridges to `#453` while naming `#129`). Naming the source row turns an implied
    attribution into one a reader can re-litigate row by row; it deliberately does NOT
    change WHICH rows bridge — that narrowing is remedy 2, and changing both at once would
    leave no reader able to tell which move altered the population.
    """
    own = issue_from_row(ruling, predicate)
    if own is not None:
        return own, "strict", None

    declared = re.search(rf"{re.escape(RULING_GOVERNS_KEY)}(\d+)", str(ruling.get("detail") or ""))
    if declared:
        return int(declared.group(1)), "declared", None

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
                return bridged, "bridged", {
                    "n": other.get("n"),
                    "event": str(other.get("event") or ""),
                }

    return None, "unbridgeable", None

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

def ruling_comments(issue: dict) -> list[dict]:
    """EVERY ruling comment the issue carries, in board order (oldest first).

    `ruling_comment` answers "does this issue carry a ruling at all" and returns the first;
    this answers "which ruling ACTS does it carry", which is what dating an instance needs.
    An amendment posted after a ruling is a SECOND ruling act, and the leg's bound must be
    read against the LATEST one: an issue whose first ruling predates the pairing mechanism
    and whose amendment follows it is exactly the case where reading the first would excuse
    a post-mechanism divergence — a false clean, the worse half of the #248 class.
    """
    out: list[dict] = []
    for comment in issue.get("comments") or []:
        if not isinstance(comment, dict):
            continue
        head = comment_heading(comment)
        if head is not None and _accepted_heading(head):
            out.append(comment)
    return out

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

# --- the board-ruling leg's boundary and its exemption surface (issue #334) -----------
#
# The leg below asserts that a ruling comment on the board has its ledger `ruling` row.
# Until #334 it had NO boundary and NO exemption surface, so it reported a PERMANENT red:
# 12 of its 13 live instances were ruling comments posted before the write path that pairs
# the two acts existed, and its one post-mechanism instance had no lawful exit.
#
# THE BOUNDARY IS THE MECHANISM'S LANDING INSTANT, and the choice is stated because it IS
# a choice. Two instants are candidates and they answer DIFFERENT questions:
#
#   * `ruling_row_recorded` (docs/ledger-invariants.json) is the instant the #270 RULING was
#     issued, 2026-10-02T14:26:52Z, and it bounds the OFFLINE direction
#     (`tests/test_ruling_row_recorded.py`): does a row that EXISTS name the comment it
#     paired with? That direction judges ROW CONTENT, and a lane can satisfy it BY HAND —
#     rows n=1949/1950/1951 carry `comment=` and were stamped 15:37Z, INSIDE the window
#     between 14:26:52Z and the mechanism's landing.
#   * THIS leg asks whether the row exists AT ALL, and the mechanism that makes the two acts
#     ONE act is `tools/rule.py`, landed by commit `366353a`. Before it a ruling was a board
#     comment with nothing on the path to stamp the row: #275's divergence is an instance of
#     the PRE-FIX defect #270 exists to fix. Reading that as a lane's neglect is a FALSE RED;
#     excusing it is what this bound is for.
#
# So the two instants are different FACTS about this factory, not two half-rules for one
# requirement: the offline gate's bound is when the row-content rule landed, this one's is
# when the write path could pair the acts. Both are FACTORY DATA read through the ONE reader
# (`tests/ledger_boundary.py`), and neither instant is typed into this file — which ships,
# byte-paired, to every member factory (#248).
#
# THE POPULATION IS INSENSITIVE TO AUTHOR-vs-COMMITTER: both instants sit between #275's
# comment and #282's, so the 12/1 split is the same either way. The declaration names the
# AUTHOR instant, the one #334 measured.
RULING_BOUNDARY_KEY = "ruling_writer_landed"

# The exemption surface — the leg's ONE lawful exit, the shape #317/#320 established.
# FACTORY DATA in its own file, keyed by the RULING COMMENT ID this leg reads, NEVER by
# issue number: a FUTURE ruling comment on an exempted issue is a NEW instance and cannot
# inherit the exemption. A malformed entry, or one that matches no in-scope unruled comment,
# is a PROBLEM — a stale exemption is visible debt, never a silent pass.
RULING_EXEMPTIONS_PATH = REPO / "docs" / "ruling-board-exemptions.json"
RULING_EXEMPT_DOMAIN = (
    "a ruling comment with no paired `ruling` row whose repair NO BACKFILL bars",
)

# The UNBOUNDED scope: no bound, no refusal, every instance judged. This is the leg's PURE
# shape, and it is what its probes pass; `main()` always passes the LIVE scope, so the bound
# cannot be forgotten at the one call site that reads the board.
UNBOUNDED_SCOPE = (None, "", "")

def ruling_board_scope(repo: Path = REPO) -> tuple[dt.datetime | None, str, str]:
    """The bound this leg judges against, as `(instant, text, refusal)`.

    Read through the ONE boundary reader (`tests/ledger_boundary.py`), so this leg and the
    boundary-reading gates cannot disagree about what this factory declared — one field, one
    predicate (SKILL.md section 11).

    The reader's own policy is absent SKIPS / malformed FAILS; this leg maps BOTH onto a
    REFUSAL, and that is the duty leg's policy deliberately. For a gate an absent
    declaration is a legitimate state (the invariant has not been adopted). For a leg that
    would otherwise judge EVERY instance it is not: judging them all against no bound is
    exactly the permanent red #334 removes, so a tree that declares nothing is TOLD so
    rather than shown a clean run or an unbounded one. The distinction survives in the
    WORDING, which is what a reader needs in order to act on it.
    """
    try:
        reader = boundary_reader()
    except Exception as exc:  # noqa: BLE001 — any load failure is the same refusal
        return None, "", (
            f"the boundary reader cannot be loaded from {LEDGER_BOUNDARY} ({exc}) — "
            f"REFUSED: without it `{RULING_BOUNDARY_KEY}` cannot be read, and a leg that "
            f"judges every ruling against a bound it could not read is the permanent-red "
            f"behaviour #334 exists to stop"
        )
    try:
        instant, text = reader.declared_boundary(repo, RULING_BOUNDARY_KEY)
    except reader.SkipGate as exc:
        return None, "", (
            f"`{RULING_BOUNDARY_KEY}` is UNDECLARED in this tree ({exc}) — REFUSED: a "
            f"ruling comment posted before the pairing mechanism could not have carried a "
            f"row, and this tree has not declared when that mechanism landed, so no "
            f"instance is judged rather than every instance being judged unbounded"
        )
    except reader.GateError as exc:
        return None, "", (
            f"`{RULING_BOUNDARY_KEY}` is declared in this tree but cannot be read: "
            f"{'; '.join(str(p) for p in exc.problems)} — REFUSED: a malformed bound is a "
            f"DEFECT, never a licence to judge unbounded"
        )
    return instant, text, ""

def load_ruling_exemptions(path: Path | None = None) -> tuple[dict[str, dict], list[str]]:
    """Load the factory's ruling-board exemptions, keyed by the ruling COMMENT id.

    Absent or empty data means no exemptions — the shipped state of a new factory, and the
    state this file returns to the moment the write path makes a third entry unnecessary.
    Anything malformed is a problem, never a silent pass: an exemption list that quietly
    fails to load is indistinguishable from no exemptions, which is the vacuous-pass shape
    the whole leg exists to catch.
    """
    path = RULING_EXEMPTIONS_PATH if path is None else path
    if not path.is_file():
        return {}, []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"{path.name}: unreadable or malformed JSON: {exc!r}"]
    if not isinstance(data, dict):
        return {}, [f"{path.name}: expected a JSON object with an 'exemptions' list"]
    raw = data.get("exemptions", [])
    if not isinstance(raw, list):
        return {}, [f"{path.name}: 'exemptions' must be a list"]
    out: dict[str, dict] = {}
    problems: list[str] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            problems.append(f"{path.name}: exemption #{i} is not an object")
            continue
        comment = str(entry.get("comment") or "").strip()
        if not comment:
            problems.append(
                f"{path.name}: exemption #{i} has no `comment` id — the key this leg reads"
            )
            continue
        reason = str(entry.get("reason") or "").strip()
        proof = str(entry.get("proof") or "").strip()
        domain = str(entry.get("domain") or "").strip()
        issue = entry.get("issue")
        granted = str(entry.get("granted") or "").strip()
        if not isinstance(issue, int) or not granted:
            problems.append(
                f"{path.name}: exemption {comment} must name the `issue` (an int) it was "
                f"granted over and the `granted` date it was admitted"
            )
            continue
        if not reason or not proof:
            problems.append(
                f"{path.name}: exemption {comment} must state both `reason` and `proof`"
            )
            continue
        if domain not in RULING_EXEMPT_DOMAIN:
            problems.append(
                f"{path.name}: exemption {comment} declares domain {domain!r}, outside the "
                f"declared domain {RULING_EXEMPT_DOMAIN}"
            )
            continue
        if comment in out:
            problems.append(f"{path.name}: exemption {comment} is declared twice")
            continue
        out[comment] = entry
    return out, problems

def board_ruling_leg(issues: list[dict], rows: list[dict], *, read_at: str,
                     predicate=None, scope=None, exemptions_path=None) -> dict:
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
    not one it repairs. That answers the REPAIR question; #334 added the POPULATION question
    the leg had left open — a ruling comment posted before the pairing mechanism existed is
    not a lane ignoring a tool, because the law cannot require a row for an obligation that
    did not yet exist. So the population is now BOUNDED (a pre-boundary instance is COUNTED
    and PRINTED as excused, never dropped and never a problem) and the post-boundary instance
    whose repair NO BACKFILL bars has a lawful exit through a declared exemption surface. The
    leg's red therefore means "a lane diverged since the mechanism", never "history exists".

    `scope` is `(bound_instant, bound_text, refusal)`. It defaults to the LIVE scope read
    through the one boundary reader; a probe passes `UNBOUNDED_SCOPE` (the leg's pure shape,
    every instance judged) or a synthetic bound of its own. `exemptions_path` is injectable
    for the same reason every other dependency is: a probe must not read the live file.

    THE PAIRING IS PER ACT, NOT PER ISSUE (#511). Until it, the leg short-circuited on
    `number in ruled` — a set of ISSUE numbers — so an issue carrying a `ruling` row for ANY
    act had NO comment examined at all, and a post-boundary amendment on an already-ruled
    issue was never judged. That is the false clean `ruling_comments` names as the worse half
    of the #248 class, and the write path makes it a defect rather than a population choice:
    `tools/rule.py` pairs ONE comment with ONE row per invocation, and `tools/ledger.py`
    refuses `event=ruling` without `comment=<digits>`, so the obligation the mechanism
    implements is per act. `ruled` KEEPS its membership role — `rulings_resolved` is read
    off it, and narrowing it to fix the short-circuit would silently shrink the printed
    population (ruling n=3768, constraint on the remedy). `rulings_read` is NOT read off it:
    it is a genuine per-row counter, because a field with that name must be the rows read
    (#545, ruling n=4096).
    """
    predicate = predicate or load_predicate()
    bound, bound_text, bound_refusal = scope if scope is not None else ruling_board_scope()
    exempt, exempt_problems = load_ruling_exemptions(exemptions_path)

    ruled: set[int] = set()
    arms = {"strict": 0, "declared": 0, "bridged": 0}
    unbridgeable: list[dict] = []
    # THE BRIDGES ARE NAMED, NOT COUNTED (#551, ruling n=4157): the `bridged` arm says HOW a
    # resolution was reached and, until this list existed, nothing about WHAT reached it, so
    # a resolution could not be re-litigated row by row. Every bridge carries the resolving
    # ruling's `n`, the row that supplied the mention, and that row's `event`.
    bridges: list[dict] = []
    # TWO COUNTERS, because `len(ruled)` answers neither question (#545, ruling n=4096).
    # `ruling_rows` is the ROWS READ — a field named `rulings_read` must be the rows the
    # ledger handed this leg, never a sum derived from the sets it built. `resolved_rows`
    # counts successful ROW-RESOLVES; the ledger is append-only and a later ruling
    # supersedes an earlier one, so one issue number can be resolved many times (#50 six
    # times, #453 and #47 four each). Both are printed beside the distinct count so the
    # partition closes on its own face: rows == resolved_rows + unbridgeable, and
    # resolved_rows == distinct + repeated. The repeated resolves are NOT de-duplicated:
    # dropping them would falsify the history to tidy an arithmetic line.
    ruling_rows = 0
    resolved_rows = 0
    for row in rows:
        if row.get("event") != "ruling":
            continue
        ruling_rows += 1
        number, arm, bridge = resolve_ruling_issue(row, rows, predicate)
        if number is not None:
            ruled.add(number)
            resolved_rows += 1
            arms[arm] = arms.get(arm, 0) + 1
            if bridge is not None:
                bridges.append(
                    {
                        "issue": number,
                        "ruling_n": row.get("n"),
                        "via_n": bridge.get("n"),
                        "via_event": bridge.get("event"),
                    }
                )
        else:
            # PRINTED, never dropped: a resolver that cannot place a row must say so, or
            # the leg reports a smaller population than it examined (#243 clause 2).
            unbridgeable.append({"n": row.get("n"), "subject": str(row.get("subject") or "")})

    problems: list[str] = list(exempt_problems)
    examined = 0
    pre_boundary = 0
    paired_latest = 0
    paired = ruling_paired_comment_ids(rows)
    exempted: list[str] = []
    matched_exemptions: set[str] = set()
    undatable: list[int] = []
    excused: list[str] = []
    unmatched: list[dict] = []
    if bound_refusal:
        # A REFUSAL is neither a skip nor a pass: NO instance is judged while the bound is
        # unreadable, or the unbounded pre-#334 behaviour returns silently. The exemption
        # surface is not evaluated either — a stale check run over a population that was
        # never judged would report every entry as stale.
        problems.append(bound_refusal)
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
        comments = ruling_comments(issue)
        if not comments:
            continue
        # The POPULATION is counted even under a refusal: what was not judged must not read
        # as what was not there (#242).
        examined += 1
        if bound_refusal:
            continue
        # The INSTANCE is the LATEST accepted ruling comment on the issue: an amendment is a
        # new ruling act, so reading the first would let a pre-mechanism head excuse a
        # post-mechanism amendment. An instant this leg cannot date fails CLOSED below.
        latest: dict | None = None
        latest_instant: dt.datetime | None = None
        for candidate in comments:
            try:
                instant = reader_parse_ts(str(candidate.get("createdAt") or ""))
            except (ValueError, TypeError):
                latest, latest_instant = candidate, None
                break
            if latest_instant is None or instant > latest_instant:
                latest, latest_instant = candidate, instant
        assert latest is not None
        # TWO ID SPACES, kept apart on purpose. `comment_node` is the board's GraphQL node id
        # and is the key the exemption surface uses (docs/ruling-board-exemptions.example.json:
        # "Key every entry by the RULING COMMENT ID the leg reads"). `comment_id` is the
        # NUMERIC id from the comment's own URL — the id `tools/rule.py` stamps into the row.
        # Comparing a node id to a `comment=` trailer can never match; see
        # `ruling_paired_comment_ids`.
        comment_node = str(latest.get("id") or "")
        comment_id = comment_numeric_id(latest)
        created = str(latest.get("createdAt") or "")
        # THE PAIRING TEST (#511). The instance is this COMMENT, and it is clean only when a
        # `ruling` row NAMES it. The issue-level `number in ruled` short-circuit that stood
        # here asked a different question — "does this issue carry any ruling row" — so an
        # amendment on an already-ruled issue was never judged at all, which is the false
        # clean `ruling_comments` names as the worse half of the #248 class.
        paired_rows = paired.get(comment_id) if comment_id else None
        if paired_rows:
            paired_latest += 1
            continue
        entry = exempt.get(comment_node)
        if entry is not None:
            # The lawful exit, PRINTED on every run with its reason: a debt made visible,
            # never forgiveness.
            matched_exemptions.add(comment_node)
            exempted.append(comment_node)
            excused.append(
                f"#{number}: EXEMPTED — ruling comment {comment_node or '(no id)'} "
                f"({created or 'instant unstated'}) is declared in "
                f"{RULING_EXEMPTIONS_PATH.name}: {entry.get('reason')}"
            )
            continue
        if not comment_id:
            # FAIL CLOSED on an unreadable id, and say WHICH read was empty: an id this leg
            # cannot parse cannot be shown to be paired, and calling it paired is the false
            # clean. The node id is printed so the exemption surface can still be keyed.
            problems.append(
                f"#{number} carries a ruling comment ({created or 'instant unstated'}, "
                f"node id {comment_node or '(none)'}) whose own URL carries no "
                f"`#issuecomment-<id>` fragment, so this leg cannot tell whether a `ruling` "
                f"row pairs it (board read at {read_at}) — NOT JUDGED as paired, and never "
                f"excused as if it were"
            )
            continue
        if bound is None:
            # UNBOUNDED scope: the leg's pure shape, every instance judged.
            problems.append(
                f"#{number} carries a ruling comment on the board (comment {comment_id}) but "
                f"the ledger holds no `ruling` row naming it (board read at {read_at}) — the "
                f"ruling's content is on the board, but every other row cites a ruling by "
                f"`n`, and a ruling with no row has no `n` for a reader to resolve"
            )
            continue
        if latest_instant is None:
            # FAIL CLOSED: an instant this leg cannot date cannot be placed against the bound
            # either, and excusing it would trade a false red for a false clean.
            undatable.append(number)
            problems.append(
                f"#{number} carries a ruling comment whose `createdAt` this leg cannot date "
                f"({created!r}), so it cannot be placed against the declared bound "
                f"{bound_text!r} either — NOT JUDGED, and never excused as pre-boundary"
            )
            continue
        if latest_instant < bound:
            pre_boundary += 1
            excused.append(
                f"#{number}: the ruling comment ({created}) PREDATES the declared bound "
                f"{bound_text} for `{RULING_BOUNDARY_KEY}`, so no row could be paired with "
                f"it — NOT JUDGED, and NEVER backfilled"
            )
            continue
        problems.append(
            f"#{number} carries a ruling comment ({created}, comment {comment_id}) on the "
            f"board but the ledger holds no `ruling` row NAMING it, and the comment is at or "
            f"after the declared bound {bound_text} for `{RULING_BOUNDARY_KEY}` (board read "
            f"at {read_at}) — the pairing mechanism existed, so this is a lane that diverged "
            f"from it"
        )
    if not bound_refusal:
        for comment_id, entry in exempt.items():
            if comment_id in matched_exemptions:
                continue
            problems.append(
                f"{RULING_EXEMPTIONS_PATH.name}: exemption {comment_id} "
                f"(issue #{entry.get('issue', '?')}) matches NO in-scope unruled ruling "
                f"comment — a stale exemption inflates visible debt while excusing nothing"
            )

    return {
        "name": "board-ruling",
        "status": "ASSERTED",
        "problems": problems,
        "excused": excused,
        "coverage": {
            "rulings_issued": examined,
            "issues_read": len(issues),
            "board_read_at": read_at,
            "headings": list(RULING_HEADINGS),
            "canonical_heading": RULING_CANONICAL_HEADING,
            "unmatched_heads_examined": len(unmatched),
            "unmatched_heads": unmatched,
            "rulings_read": ruling_rows,
            "rulings_resolved_rows": resolved_rows,
            "rulings_repeated": resolved_rows - len(ruled),
            "rulings_resolved": len(ruled),
            "rulings_unbridgeable": len(unbridgeable),
            "resolution_arms": arms,
            "unbridgeable_rows": unbridgeable,
            # WHICH ROW SUPPLIED EACH BRIDGE (#551, ruling n=4157). Printed, never implied:
            # the arm alone says HOW, and a reader who cannot see WHAT reached the verdict
            # cannot re-litigate it row by row.
            "bridged_via": bridges,
            "bound": bound_text,
            "bound_refusal": bound_refusal,
            "bound_key": RULING_BOUNDARY_KEY,
            "pre_boundary_rulings": pre_boundary,
            "rulings_undatable": undatable,
            "rulings_paired": paired_latest,
            "rulings_pairing_rows": len(paired),
            "exemptions_path": RULING_EXEMPTIONS_PATH.name,
            "exemptions_declared": len(exempt),
            "exemptions_matched": sorted(matched_exemptions),
            "rulings_exempted": exempted,
        },
    }


def load_module(name: str, path: Path):
    """Load a module by path, so no import path is assumed.

    The module is REGISTERED in `sys.modules` before `exec_module`, because a loaded
    module that is not registered re-executes itself when its own code reaches an
    `import` of its own name -- `gate_budget` does exactly that at its `__main__`
    guard, and the second execution builds a SECOND copy of every constant the
    first one exported. Registering is the fix; a module loaded twice is two
    predicates for one field.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise BoardReadError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
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
            # THE ROW'S OWN SCHEDULING RECORD (#281) IS PROBED, NEVER ASSUMED. A home whose
            # `cron_jobs` predates `cron_expr`/`next_run_at` reads NULL for them and is still
            # READ, because those two are CARRIED for the report and no instant is derived
            # from them — the prior round comes from the job's own run history. This is the
            # idiom `tools/registry.py` uses for `trigger_cmd`, for the same reason: a column
            # a home does not have must not make that home unreadable. A home with no
            # `cron_jobs` table at all still fails the select below and lands in `unreached`,
            # which is the distinction that must not be lost.
            columns = {r[1] for r in conn.execute("PRAGMA table_info(cron_jobs)")}
            sched = [
                col if col in columns else f"NULL as {col}"
                for col in ("cron_expr", "next_run_at", "timezone")
            ]
            fetched = list(conn.execute(
                "select id, name, coalesce(deliver_to,''), coalesce(prompt,''), "
                "coalesce(last_run_at,''), " + ", ".join(sched) + " "
                "from cron_jobs where enabled = 1"
            ))
        except sqlite3.Error as exc:
            unreached.append(f"{db.parent.name}: {exc}")
            continue
        finally:
            conn.close()
        for (row_id, name, deliver_to, prompt, last_run_at, cron_expr, next_run_at,
             timezone) in fetched:
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
                # The row's OWN SCHEDULING RECORD (#281, ruling n=2003), read for the same
                # reason `last_run_at` is: the duty-receipt leg must NAME the schedule the
                # round it judges belongs to. It is CARRIED, never parsed into an instant --
                # the prior round is READ from the job's own fire history
                # (`cron_run_fires`), because a round composed from `last_run_at` and
                # `next_run_at` would be an instant no record dates.
                "cron_expr": cron_expr,
                "next_run_at": next_run_at,
                # THE ROW'S OWN ZONE (#392), carried and PRINTED, never applied: `next_run_at`
                # is stored already resolved against it, so the cadence-slot host needs the
                # zone only to make a verdict READABLE ("09:15 Moscow" is an address; 06:15Z
                # alone is not) and must never apply it a second time.
                "timezone": timezone,
                "home": db.parent.name,
            })
        homes_read.append(db.parent.name)
    return rows, homes_read, unreached

# THE GOAL STATE THAT MEANS A DRIVER IS RUNNING (#133). `goal_state.state` is the daemon's own
# word for what a session's autonomous convergence loop is doing, and the three values it
# emits mean three different things to a lane carrying an unclaimed backlog:
#   * `active`        -- the loop is RUNNING and will take the next turn: DRIVEN.
#   * `completed`     -- the loop RAN and stopped; nothing will wake it again until a lane
#                        arms it. ARMED-INERT: the mechanism exists, no turn is coming.
#   * `paused`        -- the loop was armed and STOPPED mid-flight; same consequence.
# Read as a declared vocabulary, not a guess: the value is PRINTED on every line, so a state
# this reader has never seen renders as its own name rather than being folded into a verdict.
GOAL_DRIVEN_STATE = "active"

def box_goal_rows(root: Path | None = None) -> dict:
    """{rows, homes_read, homes_without_store, unreached} for every home's `goal_state`.

    The driverless-lane leg (#133) asks whether a lane that is carrying an unclaimed backlog
    has a DRIVER at all, and `goal_state` is the only surface that answers it: it is the
    daemon's own record of each session's convergence loop, keyed by `session_id`.

    FOUR OUTCOMES, FOUR NAMES, because three of them are absences that would otherwise render
    identically. A home whose DB opened and carried the table is READ; a home that opened and
    carries no `goal_state` at all is `homes_without_store` (a member factory's harness may
    not ship the table, and calling that "unreached" would red a leg for a shape the kit
    never promised); a home whose DB could not be opened is `unreached`; and the rows
    themselves are the reading. Read IN PLACE through the same `mode=ro` URI as
    `box_cron_rows`, for the same reason: a copy of a live WAL-mode database is stale state
    and a disk leak.

    The COLUMNS are probed, never assumed -- the same idiom `box_cron_rows` uses for
    `cron_expr`: a home whose `goal_state` predates a column reads NULL for it and is still
    READ, because `turns_used` and the instants are CARRIED for the report and no verdict is
    derived from their presence.
    """
    registry = load_module("oc_registry", REGISTRY)
    dbs, unreached = registry.opencrabs_home_dbs(root)
    rows: list[dict] = []
    homes_read: list[str] = []
    homes_without_store: list[str] = []
    for db in dbs:
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        except sqlite3.Error as exc:
            unreached.append(f"{db.parent.name}: {exc}")
            continue
        try:
            present = conn.execute(
                "select 1 from sqlite_master where type='table' and name='goal_state'"
            ).fetchone()
            if not present:
                homes_without_store.append(db.parent.name)
                continue
            columns = {r[1] for r in conn.execute("PRAGMA table_info(goal_state)")}
            wanted = ("state", "turns_used", "max_turns", "created_at", "updated_at")
            select = ", ".join(
                col if col in columns else f"NULL as {col}" for col in wanted
            )
            fetched = list(conn.execute(f"select session_id, {select} from goal_state"))
        except sqlite3.Error as exc:
            unreached.append(f"{db.parent.name}: {exc}")
            continue
        finally:
            conn.close()
        for session_id, state, turns_used, max_turns, created_at, updated_at in fetched:
            rows.append({
                "session_id": str(session_id or ""),
                "state": state,
                "turns_used": turns_used,
                "max_turns": max_turns,
                "created_at": created_at,
                "updated_at": updated_at,
                "home": db.parent.name,
            })
        homes_read.append(db.parent.name)
    return {
        "rows": rows,
        "homes_read": homes_read,
        "homes_without_store": homes_without_store,
        "unreached": unreached,
    }


# THE ACTIVITY FACT (#532, ruling n=3952). The driverless-lane leg read exactly TWO facts --
# the newest `goal_state` row's `state` and `session_bindings.turn_open_at` -- and from them
# claimed what would happen NEXT ("nothing will evaluate this session's goal"). The ledger
# falsified the claim: 33 `close` rows by actor `worker` landed AFTER the goal row the leg was
# judging had stopped (32 distinct units, to 2026-10-21T02:26:08Z), and the Surveys lane
# carries no goal row in any home while recording 10,336 tool executions. A lane can be driven
# by a notify, a cron, a peer push or a plan completion, and every one of those writes the
# same `tool_executions` row -- so that table is the fact the predicate was missing.
#
# IT IS DELIBERATELY NOT NAMED FOR A MECHANISM. The filing proposed `NOTIFY-DRIVEN`; this
# reader cannot see WHY a lane woke, and a mechanism name would assert a cause from a proxy,
# which is the very defect being repaired, one layer down.
LANE_ACTIVITY_READ = "read"              # source read; this session carries measured work
LANE_ACTIVITY_NONE = "none"              # source read; this session carries NO work at all
LANE_ACTIVITY_UNREADABLE = "unreadable"  # source could not be read -- never a zero (#271)

def activity_epoch(value) -> tuple[int | None, str]:
    """One `tool_executions.created_at` as a UTC epoch second, or `(None, why)`.

    INTEGER epoch seconds in the daemon's own schema, but this reader is handed OTHER homes'
    databases too, so the TEXT forms are read rather than assumed away. A value this reader
    cannot place is RETURNED AS A REASON, never coerced to zero: a zero here would be the
    "could not look" reading wearing the shape of "nothing happened" (#271).
    """
    if value is None:
        return None, "the row carries no created_at"
    if isinstance(value, (int, float)):
        return int(value), ""
    text = str(value).strip()
    if not text:
        return None, "created_at is empty"
    try:
        return int(float(text)), ""
    except ValueError:
        pass
    try:
        parsed = reader_parse_ts(text)
    except (ValueError, TypeError) as exc:
        return None, f"created_at {text!r} does not parse ({exc})"
    if parsed.tzinfo is None:
        return None, f"created_at {text!r} carries no zone offset"
    return int(parsed.timestamp()), ""

def box_lane_activity(root: Path | None = None) -> dict:
    """{newest, epochs, homes_read, homes_without_store, unreached, unparsed, readable,
    reason} for every home's `tool_executions`, newest instant PER SESSION (#532).

    THE FOURTH READING'S SOURCE. `box_goal_rows` answers "is a goal loop armed"; this answers
    "was this session MEASURED DOING anything", which is the fact the driverless-lane leg
    never read and therefore could not distinguish a stopped loop from a lane draining work
    through some other trigger.

    FOUR OUTCOMES, FOUR NAMES, mirroring `box_goal_rows` for the same reason: a home that
    opened and carries `tool_executions` is READ; a home that opened without the table is
    `homes_without_store` (a member factory's harness may not ship it, and calling that
    "unreached" would red a leg for a shape the kit never promised); a home whose DB could not
    be opened is `unreached`; and the per-session instants are the reading.

    `readable` IS THE HONEST ZERO GUARD. It is True only when at least one home was actually
    read -- otherwise every session would read "no work", which is a statement about this
    reader and not about the lane. `reason` says which of the three absences produced it.

    Read IN PLACE through the same `mode=ro` URI as `box_goal_rows`, and the COLUMNS are
    probed, never assumed: `created_at` is the only instant this table carries, and a home
    that predates it lands in `homes_without_store` rather than being dropped in silence.

    AN UNRESOLVABLE ROOT IS UNREADABLE, NOT A CRASH. `opencrabs_home_dbs` raises
    `FleetManifestError` when the manifest declares no `profile_root`, and the SHIPPED tree
    reaches this reader with exactly that shape -- `registry/fleet.example.json` is the only
    manifest the kit carries, and `tests/test_shipped_audit_runs.py` runs this file from
    `TEMPLATE/`. Letting the exception escape took the whole patrol down at the shipped depth
    (measured: 35 red arms in `test_template_gate_pairing.py`, every one a traceback out of
    `main()`), which is the same class `declared_slug` already guards -- and the ruling's
    clause 4 says an unreadable source yields UNREADABLE WITH ITS REASON. A guard that let the
    error through would satisfy the letter of "never a zero" and fail its point.
    """
    registry = load_module("oc_registry", REGISTRY)
    try:
        dbs, unreached = registry.opencrabs_home_dbs(root)
    except Exception as exc:
        return {
            "newest": {},
            "epochs": {},
            "homes_read": [],
            "homes_without_store": [],
            "unreached": [f"no OpenCrabs home could be located: {exc}"],
            "unparsed": [],
            "readable": False,
            "reason": f"the activity source could not be located ({exc})",
        }
    newest: dict[str, str] = {}
    epochs: dict[str, int] = {}
    homes_read: list[str] = []
    homes_without_store: list[str] = []
    unparsed: list[str] = []
    for db in dbs:
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        except sqlite3.Error as exc:
            unreached.append(f"{db.parent.name}: {exc}")
            continue
        try:
            present = conn.execute(
                "select 1 from sqlite_master where type='table' and name='tool_executions'"
            ).fetchone()
            if not present:
                homes_without_store.append(db.parent.name)
                continue
            columns = {r[1] for r in conn.execute("PRAGMA table_info(tool_executions)")}
            if "session_id" not in columns or "created_at" not in columns:
                homes_without_store.append(db.parent.name)
                continue
            fetched = list(conn.execute(
                "select session_id, max(created_at) from tool_executions "
                "where session_id is not null and session_id != '' group by session_id"
            ))
        except sqlite3.Error as exc:
            unreached.append(f"{db.parent.name}: {exc}")
            continue
        finally:
            conn.close()
        for session_id, created_at in fetched:
            epoch, why = activity_epoch(created_at)
            if epoch is None:
                unparsed.append(f"{db.parent.name}:{session_id}: {why}")
                continue
            prior = epochs.get(str(session_id))
            if prior is None or epoch > prior:
                epochs[str(session_id)] = epoch
                newest[str(session_id)] = dt.datetime.fromtimestamp(
                    epoch, dt.timezone.utc
                ).isoformat()
        homes_read.append(db.parent.name)
    readable = bool(homes_read)
    if readable:
        reason = ""
    elif unreached:
        reason = "no home's tool_executions could be read: " + "; ".join(unreached)
    elif homes_without_store:
        reason = (
            "no home carries a tool_executions table: " + ", ".join(homes_without_store)
        )
    else:
        reason = "no OpenCrabs home database was found to read"
    return {
        "newest": newest,
        "epochs": epochs,
        "homes_read": homes_read,
        "homes_without_store": homes_without_store,
        "unreached": unreached,
        "unparsed": unparsed,
        "readable": readable,
        "reason": reason,
    }


# THE DAEMON'S OWN WORDING for a round its trigger gate skipped (#477). Read from the run
# record's `content` prose, which is the ONLY field that separates a suppressed fire from a
# round that ran and produced nothing -- both are stored `status=success`.
CRON_SUPPRESSION_MARKER = "Execution skipped"

def fire_is_suppressed(content: str) -> bool:
    """Whether a run record's OWN `content` prose says its trigger gate SKIPPED the round.

    #477. A suppressed fire is stored with `status=success`, so the run's own verdict cannot
    distinguish it from a round that ran and produced nothing -- the only field that does is
    this prose, and before #477 the reader did not carry it. Anchored to the DAEMON's own
    emitted wording rather than to a pattern of our own invention, so a change in that
    wording surfaces as a predicate to revisit instead of as silent drift: the marker is a
    named constant and the probe asserts against the constant, not against a literal.
    """
    return CRON_SUPPRESSION_MARKER in str(content or "")

def cron_run_fires(root: Path | None = None) -> list[dict]:
    """Every cron FIRE this box recorded: {job_id, job_name, started_at, status,
    completed_at, error, content, suppressed, home}.

    `box_cron_rows` reads only the CURRENT row (`last_run_at`), so it can name each job's
    LAST fire and nothing older. The per-job residual (#449) is derived from that job's OWN
    measured MAX fire->receipt latency, which needs the job's HISTORY — so this reader takes
    `cron_job_runs`, the daemon's own per-fire record, and the caller pairs each fire with
    the ledger's own receipt row for the round it opened.

    The run's OWN VERDICT rides along (#306, ruling n=2191): `status`, `completed_at` and
    `error` are carried because the notify-receipt leg must ask whether the run that opened a
    0-byte log COMPLETED — a completed run whose notify died is a failed duty, while a run
    that never reached its notify is the #139 case. One table, one read, two legs: the duty
    leg takes the instants and the notify leg takes the verdict.

    Read IN PLACE through the same `mode=ro` URI as `box_cron_rows`, for the same reason: a
    copy of a live WAL-mode database is stale state and a disk leak. A home that cannot be
    read contributes NOTHING and is not reported here — the residual this feeds is a
    MEASUREMENT, and a measurement taken over a partial population prints its own
    `measured_rounds` count beside its value so a thin sample is visible as thin.
    """
    registry = load_module("oc_registry", REGISTRY)
    dbs, _unreached = registry.opencrabs_home_dbs(root)
    fires: list[dict] = []
    for db in dbs:
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        except sqlite3.Error:
            continue
        try:
            fetched = list(conn.execute(
                "select coalesce(job_id,''), coalesce(job_name,''), "
                "coalesce(started_at,''), coalesce(status,''), "
                "coalesce(completed_at,''), coalesce(error,''), "
                "coalesce(content,'') from cron_job_runs"
            ))
        except sqlite3.Error:
            continue
        finally:
            conn.close()
        for job_id, job_name, started_at, status, completed_at, error, content in fetched:
            fires.append({
                "job_id": str(job_id),
                "job_name": str(job_name),
                "started_at": str(started_at),
                # The run's OWN verdict (#306, ruling n=2191). Carried because the
                # notify-receipt leg must tell a COMPLETED run whose notify was launched and
                # then died from a run that never reached its notify — and the two leave the
                # same 0-byte log. `cron_job_runs` is the only surface that separates them,
                # and before #306 nothing in this tool read it.
                "status": str(status),
                "completed_at": str(completed_at),
                "error": str(error),
                # #477: the run's OWN suppression prose, and the flag derived from it by the
                # ONE reader that owns that predicate. Carried because a trigger-gated duty
                # fires on time, succeeds, and produces no receipt -- the exact shape this
                # leg exists to red -- and this field is the only thing that tells them apart.
                "content": str(content),
                "suppressed": fire_is_suppressed(content),
                "home": db.parent.name,
            })
    return fires

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


def _citation_clause(text: str, start: int) -> str:
    """The clause the instant at `start` sits in — text back to the nearest break.

    The clause, not the sentence, because a citation is commonly parenthesised: cutting at
    `(` makes `(issue #469, ruling 2026-10-11T12:59:43Z)` its own clause instead of
    dragging the preceding sentence's words into the verdict.
    """
    head = text[:start]
    cut = max((head.rfind(ch) for ch in _CITATION_CLAUSE_BREAKS), default=-1)
    return head[cut + 1:]

def is_citation_instant(text: str, start: int) -> bool:
    """Does the instant at `start` CITE a source record rather than assert state?

    True only when its clause names a source record (a ruling, an issue, a ledger row, a
    `#N`, an `n=N`) AND carries no boundary/window/epoch/deadline word. Everything else —
    including a clause that says nothing recognisable — is False, so the instant stays
    judged: the carve-out can only ever remove a false positive, never create a false clean.
    """
    clause = _citation_clause(text, start)
    if not CITATION_SOURCE_RE.search(clause):
        return False
    return not STATE_ASSERTION_RE.search(clause)

def embedded_law_content(prompt: str) -> tuple[str, str, str]:
    """(judged instant, bare date, cited instant) — at most one is non-empty.

    The three are RETURNED APART rather than folded into one verdict, because they are
    different findings: an instant is drift-prone STATE and is judged, a bare date is a
    citation of the past and is only REPORTED, and an instant sitting in a CITATION is the
    same citation wearing a time component — reported for the same reason (#478). Collapsing
    them would make the citation indistinguishable from the state, which is the false
    positive this class measured on the box's own best-shaped row (whose bare date sits in a
    rationale explaining why its prompt is THIN) and then repeated on a prompt that cited a
    ruling by its timestamp.
    """
    text = prompt or ""
    for match in EMBEDDED_INSTANT_RE.finditer(text):
        if not is_citation_instant(text, match.start()):
            return match.group(0), "", ""
    cited = EMBEDDED_INSTANT_RE.search(text)
    if cited:
        return "", "", cited.group(0)
    date = BARE_DATE_RE.search(text)
    return "", (date.group(0) if date else ""), ""

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
    cited_only: list[dict] = []
    for row in rows:
        row_name = str(row.get("name") or "")
        instant, bare, cited = embedded_law_content(str(row.get("prompt") or ""))
        if instant:
            law_content.append({"name": row_name, "home": str(row.get("home") or ""),
                                "instant": instant, "owner": _declares(row_name)})
        elif cited:
            cited_only.append({"name": row_name, "home": str(row.get("home") or ""),
                               "instant": cited, "owner": _declares(row_name)})
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
            # An instant that CITES a source record is the same citation the bare-date arm
            # above reports, wearing a time component. Printed for the same reason: a
            # carve-out that drops the population is a false clean one layer down (#478).
            "cited_instant_rows": cited_only,
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

def run_key(row: dict) -> tuple[str, str]:
    """The identity a cron row and a run row SHARE: `(job_id, job_name)`.

    The two surfaces spell the pair DIFFERENTLY — `cron_jobs` carries `id`/`name` while
    `cron_job_runs` carries `job_id`/`job_name` — so this one predicate reads both shapes,
    and a reader that compared only one spelling would match nothing on one of the two
    surfaces and report every log as unattributable.

    Neither column alone is enough: a job that was deleted and re-created keeps its name but
    changes its id, so keying on the name alone would attach a fresh run to a retired row,
    and keying on the id alone would drop a run whose row was renamed. The pair is what the
    daemon writes on both surfaces.
    """
    return (str(row.get("job_id") or row.get("id") or ""),
            str(row.get("job_name") or row.get("name") or ""))


def log_stamp(text: str):
    """The instant a thin trigger's log NAME carries, as a UTC datetime — or None.

    The name's stamp is the trigger's own record of when it fired
    (`<job>-YYYYMMDDTHHMMSS.log`), and it is the only thing tying a log to the run that
    opened it. It is written in UTC, which is checked rather than assumed: the log's own
    mtime tracks the stamp within seconds on this box, and the stamp falls inside the
    window of the run row for the same job. An unparsable stamp returns None, so the
    caller reports the log as unattributable instead of comparing it against nothing.
    """
    try:
        return dt.datetime.strptime(text, "%Y%m%dT%H%M%S").replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def ts_or_none(parse, text: str):
    """`parse(text)` where an absent or malformed stamp is None, never an exception.

    The daemon leaves `completed_at` EMPTY for a run that never reached its own end — the
    #139 orphan, and any run still in flight — so a reader that raised on the empty string
    would turn the very case this leg exists to see into a crash that takes the whole patrol
    down with it (#306). A malformed stamp is treated the same way: the caller reports the
    log as unattributable rather than dying on it.
    """
    if not str(text or "").strip():
        return None
    try:
        return parse(text)
    except (TypeError, ValueError):
        return None


def run_containing(fires: list[dict], row: dict, parse, stamp: dt.datetime) -> dict | None:
    """The run of THIS job whose window contains `stamp` — the run that opened the log.

    A log's name carries the instant the thin trigger FIRED, and a run row carries the
    window that fire opened (`[started_at, completed_at]`). Containment is the whole
    predicate: the log cannot be attributed to a run by name alone, because a job fires
    many times and every fire writes the same log name with a different stamp.

    `completed_at` is EMPTY for a run that never reached its own end (the #139 orphan, and
    any run still in flight), so the window is then open-ended and the run still counts as
    containing the stamp: a run that died mid-flight is exactly the case this leg must be
    able to see, and refusing to match it would leave the 0-byte log unattributed — which
    reads as "no run to judge" rather than "a run that did not finish".

    Where several runs contain the stamp (an overlapping retry), the LATEST `started_at`
    governs: it is the fire the log belongs to, and the earlier one is a run the daemon
    recorded as superseded. Returns None where no run of this job contains the stamp —
    the caller reports that as unattributable rather than assuming either verdict.
    """
    wanted = run_key(row)
    containing = []
    for run in fires:
        if run_key(run) != wanted:
            continue
        started = ts_or_none(parse, run.get("started_at") or "")
        if started is None or started > stamp:
            continue
        finished = ts_or_none(parse, run.get("completed_at") or "")
        if finished is not None and finished < stamp:
            continue
        containing.append((started, run))
    if not containing:
        return None
    return max(containing, key=lambda pair: pair[0])[1]


def notify_receipt_leg(rows: list[dict], homes_read: list[str], unreached: list[str],
                       prefixes: list[str], *, log_dir: Path = LOG_DIR,
                       read_at: str = "", fires: list[dict] | None = None) -> dict:
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

    A 0-BYTE LOG IS TWO FACTS, NOT ONE (#306, ruling n=2191). Until #306 both were excused
    as "never attempted", so a run that COMPLETED and whose notify was launched and then
    died was filed as a run that never got there — a failed duty wearing an excuse. The
    run's own verdict is what separates them, and `cron_job_runs` is the only surface that
    carries it: a 0-byte log whose containing run REACHED ITS DELIVERY (`success` or
    `delivery_failed`) is a PROBLEM, and a 0-byte log whose run never reached it
    (`interrupted`/`error`, or no run matched at all) is the #139 case and is excused WITH
    THE STATUS NAMED. `delivery_failed` is a PROBLEM and never an excuse: the daemon writes
    it when the notify WAS attempted and its delivery FAILED, which is the failed duty
    itself rather than a duty that never happened. The status vocabulary is closed here, so
    a value this leg does not recognise is REPORTED rather than excused — a leg that excuses
    what it cannot read is a green signal that has stopped observing its own failure class.

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
    # The 0-byte logs no run row could be matched to (#306). Counted and NAMED rather than
    # folded into the excuse, because "the run did not complete" and "no run could be
    # matched to this log" are different facts and only the first is a finding about the
    # box; the second is a statement about the read, and it must be visible as one.
    unattributed: list[dict] = []
    # #537 (ruling n=4009): a candidate log whose own stamp NO run of its job contains is
    # EXCUSED and PRINTED with the stamp and the job the filename nominates — never judged,
    # and never silently dropped. The live pair that produced this ruling were two 954/948 B
    # files written by another lane's background task into the shared /tmp namespace: they
    # carried a cron stem, no run of that job covered their instants, and the filename proxy
    # alone called them failed dispatches. The excuse is loud by construction because an
    # excuse-heavy round must be visible as one.
    uncorroborated: list[dict] = []
    # A job with NO run rows at all is a DECLARED DEGRADATION, not an excuse: the
    # corroboration cannot be performed for it, so the filename proxy stands and the leg
    # SAYS SO with its reason (#524's rule, applied here one surface over). This arm is
    # what stops `cron_run_fires`' silent per-home skip — it contributes NOTHING for a home
    # it cannot read — from turning an unread run table into a blanket excuse that reads as
    # a clean round (#271: a zero must never stand in for "could not look").
    degraded: list[dict] = []
    fires = list(fires or [])
    # The jobs this run table can corroborate AT ALL. Membership is per JOB, never global:
    # a table holding one job's runs must not be read as corroborating another's.
    corroborable = {run_key(fire) for fire in fires}
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
        # ---- #537 (ruling n=4009): corroborate EVERY candidate BEFORE judging it --------
        # The leg's own asymmetry WAS the defect: a 0-byte log was reconciled against the
        # scheduler's run record while a non-empty log was judged on the filename proxy
        # alone, so any file carrying a cron stem — written by any lane, for any reason —
        # was scored as a failed dispatch. One predicate now, both sizes: a log is
        # attributed to a job only when that job has a run row whose window CONTAINS the
        # log's own stamp. The filename nominates a CANDIDATE and never settles one.
        found = NOTIFY_LOG_RE.match(path.name)
        stamp = log_stamp(found.group("stamp")) if found else None
        run = None
        if run_key(row) not in corroborable:
            # DECLARED DEGRADATION: this job has no run rows, so corroboration cannot be
            # performed. The filename proxy stands, and the leg prints that it did and why.
            degraded.append({
                "job": name,
                "id": str(row.get("id") or ""),
                "path": str(path),
                "stamp": stamp.isoformat() if stamp else "",
            })
        else:
            run = run_containing(fires, row, reader_parse_ts, stamp) if stamp else None
            if run is None:
                # UNATTRIBUTED: the filename nominates this job, no run of it covers the
                # stamp, so nothing in the record says this file came from that job at all.
                # EXCUSED and PRINTED with both facts — never a problem, never silence.
                uncorroborated.append({
                    "job": name,
                    "id": str(row.get("id") or ""),
                    "path": str(path),
                    "stamp": stamp.isoformat() if stamp else "",
                    "runs_of_job": sum(1 for fire in fires
                                       if run_key(fire) == run_key(row)),
                })
                continue
        if not text.strip():
            # A 0-byte log is a notify that produced NOTHING — which is what a run that
            # never reached its notify leaves AND what a completed run whose notify died
            # leaves. Only the run's own verdict separates them (#306, ruling n=2191).
            status = str(run.get("status") or "") if run else ""
            entry = {
                "job": name,
                "id": str(row.get("id") or ""),
                "path": str(path),
                "run_status": status,
                "run_started": str(run.get("started_at") or "") if run else "",
                "run_completed": str(run.get("completed_at") or "") if run else "",
            }
            if status in RUN_COMPLETED_STATUSES:
                judged.append({
                    "job": name,
                    "id": str(row.get("id") or ""),
                    "path": str(path),
                    "line": "",
                    "run_status": status,
                })
                # The two completed statuses are DIFFERENT failures and the verdict says
                # which: `success` is the n=903 lie (a delivery recorded as OK with no
                # receipt), while `delivery_failed` is the daemon's own honest record that
                # the notify was attempted and its delivery failed.
                if status in RUN_UNDELIVERED_STATUSES:
                    why = (
                        "the run REACHED ITS DELIVERY and its own record says that delivery "
                        "FAILED"
                    )
                else:
                    why = (
                        "the run recorded its delivery as DELIVERED"
                    )
                problems.append(
                    f"{name} (cron id {row.get('id') or 'unstated'}): the run that opened "
                    f"{path.name} COMPLETED (status {status}, "
                    f"{entry['run_started'] or 'no start stamp'} -> "
                    f"{entry['run_completed'] or 'no completion stamp'}) and the log is "
                    f"0 bytes — {why}, so the duty FAILED. A completed run's empty log is "
                    f"never 'not attempted' (#306)."
                )
                continue
            if status and status not in RUN_NOT_COMPLETED_STATUSES:
                # A status this leg does not know is REPORTED, never excused: excusing it
                # would let the daemon move its own vocabulary and silently widen the
                # excuse until the leg could no longer see the class it exists for.
                judged.append({
                    "job": name,
                    "id": str(row.get("id") or ""),
                    "path": str(path),
                    "line": "",
                    "run_status": status,
                })
                problems.append(
                    f"{name} (cron id {row.get('id') or 'unstated'}): the run that opened "
                    f"{path.name} carries the status {status!r}, which this leg does not "
                    f"know ({', '.join(RUN_COMPLETED_STATUSES + RUN_NOT_COMPLETED_STATUSES)}) "
                    f"— an unrecognised verdict cannot be an excuse, so it is reported and "
                    f"the vocabulary is corrected where it is owned (#306)."
                )
                continue
            if run is None:
                unattributed.append(entry)
            not_attempted.append(entry)
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
            # #306: the excuse is only earned by a run that did NOT complete, so the count
            # of 0-byte logs no run could be matched to is printed SEPARATELY — a box whose
            # runs table could not be read must not render as a box with no failed notify.
            "logs_not_attempted_unattributed": len(unattributed),
            "unattributed_not_attempted_logs": unattributed,
            "logs_completed_with_empty_log": len(
                [j for j in judged if j.get("run_status") in RUN_COMPLETED_STATUSES]
            ),
            # The bucket's own PREDICATE, printed beside its population (#163 half 2 (b)):
            # a 0-byte log is excused only by the run's own verdict, and a clean bucket and
            # one that cannot see a member must never render the same.
            "not_attempted_predicate": (
                "the 0-byte log's OWN stamp falls inside the window of a run row for the "
                "same (job_id, job_name) whose status is one of "
                f"{', '.join(RUN_NOT_COMPLETED_STATUSES)}; a run reading "
                f"{', '.join(RUN_COMPLETED_STATUSES)} makes the same 0-byte log a PROBLEM, "
                "and a status outside the closed vocabulary is reported, never excused"
            ),
            "logs_retired": len(retired),
            # #537 (ruling n=4009): the corroboration surface, its population and its
            # predicate, all printed beside each other. A round that excuses many logs
            # because nothing covers their stamps must be VISIBLE as one, and a round where
            # the run table could not corroborate a job at all must say so rather than
            # render as a clean read (#271, #163 half 2 (b)).
            "logs_uncorroborated": len(uncorroborated),
            "uncorroborated_logs": uncorroborated,
            "logs_corroboration_degraded": len(degraded),
            "corroboration_degraded_logs": degraded,
            "jobs_corroborable": len(corroborable),
            "run_rows_read": len(fires),
            "corroboration_predicate": (
                "a log is attributed to a job only when a run row for the same "
                "(job_id, job_name) has a window CONTAINING the log's own stamp; the "
                "filename nominates a candidate and never settles one. A candidate no run "
                "covers is EXCUSED and printed with its stamp; a job carrying NO run rows "
                "at all falls back to the filename proxy AS A DECLARED DEGRADATION, and a "
                "corroborated log with no receipt stays a PROBLEM"
            ),
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
# **AND THE NEWEST ROUND IS NOT THE ONLY ROUND (#281, ruling n=2003).** Reading
# `last_run_at` alone made this leg judge exactly ONE round per job, and the round it read
# was usually the one still IN FLIGHT -- so the `continue` below ended the job's turn and
# the round the PREVIOUS fire woke was never visited. For a job whose derived residual
# reaches its own cadence that is EVERY round: measured live at 2026-10-12T18:40Z,
# `factory-triage-patrol` (`0 */6`, derived residual 3.77 d against a 6 h cadence) had no
# round judged at all, and a leg that examines nothing must never render as one that
# examined and found clean (#160). The prior round is therefore READ -- from the job's own
# run record (`cron_job_runs`, through `duty_fire_instants`), which dates every fire the
# daemon took -- and it is judged when the newest one is in flight.
#
# IT IS NEVER COMPOSED. `last_run_at - (next_run_at - last_run_at)` would name an instant
# no record carries, and the round this leg names must be one the daemon's own table
# dates: an instant that was never read is the #175 class wearing arithmetic (SKILL.md
# hard rule 4). So the row's own scheduling record is CARRIED beside the read -- the cron
# SELECT reads `cron_expr` and `next_run_at` for the reason `last_run_at` is read, to NAME
# the schedule the round belongs to -- and where no earlier fire can be read the leg
# prints NOT JUDGED with its reason rather than falling back to an inferred round.
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
# **AND A RECEIPT THE READER CANNOT REACH IS NAMED, never read as a round that declared
# nothing (#281, ruling n=2003).** The declaration is POSITIONAL — the token must sit inside
# the row's canonical terminal run — and a row that writes it in the prose HEAD and closes
# with a token carrying no `=` reads as declaring NOTHING. That state is neither clean nor a
# missing duty, and both readings blame the wrong party: the author wrote the declaration and
# the reader cannot see it. So a judged round whose matched rows declare no duty is asked one
# further question — does a matched row carry the `duty=` token in its OWN VOICE outside its
# canonical run? — and a yes is reported as a MALFORMED RECEIPT, NAMING the row and the
# repair (make the token terminal). Measured on the live ledger when this landed: n=1875,
# n=1880 and n=1966 each read `declared_duty -> []` while carrying `duty=completed` in prose.
#
# THE DISCRIMINATOR IS THE SHARED OWN-VOICE READER (`field_predicate.mentions_duty`), never a
# private scan and never a second predicate (n=405 PART 5 / n=599): a token inside a
# parenthetical aside is a CITATION of another row's token. A WRITE-PATH REFUSAL was ruled
# out and the precedent is measured (#247 / `b4b1aa8`): a lexical branch that refused prose
# quoting the token produced false positives on legitimate quotations and had to be demoted
# to a NOTE. Reader-side detection with the own-voice scope is what is safe where a lexical
# refusal is not. The finding is a POINTER, true of the row whether it declared or merely
# discussed — the leg never rules on what the round DID from a malformed row.
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
# THE TOKEN THAT DECLARES A DUTY OWES NO RECEIPT (#424 items 1+2+3-clause-3, ordered at
# n=2723 and re-sequenced at n=3228). It rides the SAME line and the SAME regex as a stem,
# because it is the same declaration -- what differs is what it says the duty owes. Read as
# a STEM it forges a false MISSING: the leg hunts `none-<round>*`, finds nothing and reds,
# every round, on a job that owes nothing at all. `factory-publish` is the live instance.
RECEIPT_OWES_NONE_TOKEN = "none"
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

# A DECLARATION THE CANONICAL READER CANNOT PARSE IS A PROBLEM, NOT SILENCE (#506). The
# canonical line is anchored at BOTH ends, so a backtick, an indent, a list marker or a
# trailing clause un-declares a duty silently: the leg printed NOT JUDGED beside
# `problems: 0`, which is indistinguishable from a clean round. This regex is deliberately
# NOT a wider declaration reader -- it reads only whether a LINE BEGINS with the token, which
# is what separates an ATTEMPTED declaration from prose that merely mentions the field (the
# n=405 clause 5 class: "the old text said receipt_subject: ..." begins with neither, so it is
# correctly neither a declaration nor a defect). The canonical reader above is untouched, so
# what COUNTS as a declaration is exactly as narrow as it was -- only the silence is closed.
def declared_receipt_stem(prompt: str) -> str | None:
    """The receipt stem this row declares, or None — the line `receipt_subject: <stem>`.

    Anchored to a whole line so a sentence that merely MENTIONS the declaration cannot
    satisfy it: prose about a field is not a declaration of one (the class ruled at
    n=405 clause 5).
    """
    found = RECEIPT_DECL_RE.search(prompt or "")
    if not found:
        return None
    stem = found.group(1)
    # A BACKTICKED VALUE IS NOT A STEM (#506). The canonical line matches ``receipt_subject:
    # `survey` `` because a backtick is \S, and the resulting stem can never equal any ledger
    # subject -- so the duty would be hunted forever against a name that cannot exist and read
    # MISSING on every round. Rejected here, named as a shape by the attempt reader.
    if "`" in stem:
        return None
    return stem

def declared_receipt_disposition(prompt: str) -> tuple[str, str | None]:
    """Which of the THREE buckets this row's `receipt_subject:` line puts it in.

    Returns `("declares", stem)` when the row names a receipt to hunt, `("owes_none", None)`
    when it declares it owes none, and `("undeclared", None)` when it carries no declaration
    at all. ONE reader for ONE field (SKILL.md section 11): the line and the regex are
    shared, and only the TOKEN differs -- so a member factory declaring `none` is read by
    the same declaration the rest of the population uses rather than by a second vocabulary.

    The third bucket is the one the leg has always had and never NAMED: a row that declares
    nothing is NOT JUDGED, and the emitter already printed that phrase for it while the code
    had no way to tell it from a row that had declared it owes none.
    """
    stem = declared_receipt_stem(prompt)
    if stem is not None:
        if stem == RECEIPT_OWES_NONE_TOKEN:
            return ("owes_none", None)
        return ("declares", stem)
    # THE FOURTH BUCKET (#506). A row that ATTEMPTED a declaration the reader cannot parse is
    # neither a declaration nor a silence: it is evidence the author meant to declare
    # something, and reporting it as a clean NOT JUDGED is the false negative this closes.
    # The detail is the SHAPE, so the leg can name what to fix.
    malformed = malformed_receipt_declaration(prompt)
    if malformed is not None:
        return ("malformed", malformed[2])
    return ("undeclared", None)

def malformed_receipt_declaration(prompt: str) -> tuple[int, str, str] | None:
    """(1-based line, the line, the SHAPE it was found in) for an ATTEMPTED declaration the
    canonical reader cannot parse -- or None where the prompt carries no attempt at all.

    THE SHAPE IS NAMED, because the author has to be able to see which edit un-declared the
    duty: "it is malformed" is not a repair, and the backticked form that produced #506 was
    invisible to every reader for a whole round.

    THE WALK IS PER LINE, and it finds the token ANYWHERE on one (ruling n=3527 criterion 4).
    An earlier form anchored its pattern at the line start and therefore reported a token
    sitting inside a sentence as NOTHING AT ALL -- the same false negative one indentation
    over, because prose that says `The old text said receipt_subject: x` is evidence an
    author had the token in hand, and the leg cannot tell a removed declaration from a
    mangled one. Reporting it is the ruling's order; reading it as a declaration is the
    non-goal. So the shape names `prose before the token`, and `declared_receipt_stem` --
    which stays anchored to a whole line -- still refuses to call it one.

    A line that carries BOTH a canonical declaration and prose elsewhere cannot reach here:
    `declared_receipt_stem` answers first, so the row is judged on its declaration and this
    reader is never consulted. That ordering is what keeps a correct prompt from reding.
    """
    text = prompt or ""
    for index, raw in enumerate(text.splitlines(), start=1):
        at = raw.find("receipt_subject")
        if at < 0:
            continue
        canonical = RECEIPT_DECL_RE.fullmatch(raw.rstrip())
        # A canonical line is a declaration -- unless its VALUE is backticked, in which case
        # `declared_receipt_stem` refuses it and this reader has to say why (see above).
        if canonical and "`" not in canonical.group(1):
            continue
        shapes: list[str] = []
        prefix = raw[:at]
        if prefix != prefix.lstrip():
            shapes.append("indented")
        stripped = prefix.lstrip()
        marker = re.match(r"(?:[-*+]|\d+\.)[ \t]+", stripped)
        if marker:
            shapes.append("a list marker before it")
            stripped = stripped[marker.end():]
        if stripped:
            shapes.append("prose before the token")
        ticks = re.search(r"`+$", prefix)
        if ticks:
            shapes.append(f"wrapped in {len(ticks.group(0))} backtick(s)")
        rest = raw[at + len("receipt_subject"):]
        if not rest.startswith(":"):
            shapes.append("no `:` after the token")
        else:
            value = rest[1:].strip()
            if not value:
                shapes.append("an empty value")
            elif re.search(r"\s", value):
                shapes.append("prose after the value")
            elif "`" in value:
                shapes.append("a backtick in the value")
        shape = ", ".join(shapes) or "a shape the canonical reader cannot parse"
        return index, raw.strip(), shape
    return None

# The jobs this factory DECLARES are legitimately NOT JUDGED (#506 half 2). An exemption is
# factory data, never a manifest path: absence IS the empty state, the convention
# `docs/kit-exemptions.json` already sets, so a factory that has never needed one carries no
# file and reads clean rather than red.
DUTY_RECEIPT_EXEMPTIONS = REPO / "docs" / "duty-receipt-exemptions.json"

def receipt_declaration_exemptions(
    path: Path | None = None,
) -> tuple[dict[str, str], str | None]:
    """(job name -> its declared reason, a PROBLEM where the store cannot be honoured).

    A store that EXISTS but cannot be parsed is a problem rather than a silent empty set: an
    unreadable exemption list would red every excused duty, and a typo'd one would hide a
    real finding behind a name that matches nothing.
    """
    target = path or DUTY_RECEIPT_EXEMPTIONS
    if not target.is_file():
        return {}, None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, (
            f"{target.name} could not be read ({type(exc).__name__}), so no declared "
            f"exemption can be honoured and every NOT JUDGED duty is a finding"
        )
    rows = data.get("exempt") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return {}, f"{target.name} declares no `exempt` list, so no exemption can be honoured"
    out: dict[str, str] = {}
    for entry in rows:
        if not isinstance(entry, dict) or not isinstance(entry.get("job"), str) or not entry["job"]:
            return {}, f"{target.name} carries an entry naming no `job`, so no exemption can be honoured"
        out[entry["job"]] = str(entry.get("reason") or "")
    return out, None

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

def round_fire_instants(job: dict, fires: list[dict], round_date: str,
                        parse) -> list[dt.datetime]:
    """This job's fires that fall on `round_date`, oldest first — the round's OWN population.

    THE ROUND IS A DAY and a sub-daily job fires SEVERAL times inside it, so the round's
    receipt question is per FIRE: a day carrying four fires and three receipts has one round
    unaccounted, and `last_run_at` alone can never show it (#499, ruling n=3446). The fires
    come from `cron_job_runs` through `duty_fire_instants`, so a fire this reader cannot date
    contributes no round rather than a composed one.
    """
    return [inst for inst in duty_fire_instants(job, fires, parse)
            if inst.strftime("%Y-%m-%d") == round_date]

def fire_receipt_token(stem: str, round_date: str, fire_iso: str) -> str:
    """The subject token a receipt for THIS fire carries — `<stem>-<date>T<HH>`.

    The hour is the FIRE's own hour, which is the key the box's pacemakers actually write
    (`hq-cycle-2026-10-16T06`). A lane that keys its COMPLETION hour instead writes a token
    that answers no fire — measured at 10-06, where the 06:50 fire left a `T09` row and the
    round read clean — and that is exactly the miss this predicate exists to name.
    """
    text = str(fire_iso or "")
    return f"{stem}-{round_date}T{text[11:13]}" if len(text) >= 13 else ""

def receipt_hour_token(subject: str, stem: str, round_date: str) -> str | None:
    """The `T<HH>` hour a round receipt carries, or None when it is ROUND-LEVEL.

    THE HOUR IS THE WRITER'S TO CHOOSE, exactly as the date decoration is (#159): the box
    runs TWO conventions and both are lawful. `hq-cycle-2026-10-16T06` is HOUR-KEYED — a
    sub-daily pacemaker writing one receipt per fire — while `insights-2026-10-16` is
    ROUND-LEVEL, a daily job writing one receipt for its single round. A reader that
    demanded an hour from every receipt would charge the round-level jobs a receipt per
    fire they never promised, which is the false-RED class the ruling warns about (#146);
    measured live at 2026-10-16T21:0xZ, that mistake turned `factory-insights-weekly`,
    `factory-template-weekly` and `factory-growth-map-biweekly` RED on rounds that had
    receipted correctly.
    """
    prefix = f"{stem}-{round_date}"
    text = str(subject or "")
    if not text.startswith(prefix):
        return None
    rest = text[len(prefix):]
    if rest[:1] != "T" or not rest[1:3].isdigit() or rest[3:4].isdigit():
        return None
    return rest[:3]

def receipt_is_hour_keyed(subject: str, stem: str, round_date: str) -> bool:
    """Does this receipt's subject KEY AN HOUR — valid or not?

    The distinction that keeps the round-level exemption honest. A subject carrying `T` plus
    digits declares the HOUR-KEYED convention whether or not its hour answers a fire, so
    `registry-attest-2026-09-25T070` is a malformed hour token and NOT a round-level
    receipt: reading it as round-level would let one mistyped row exempt every fire in the
    round, turning the 10-06 miss CLEAN again. Only a subject that stops at the date is
    round-level.
    """
    prefix = f"{stem}-{round_date}"
    text = str(subject or "")
    if not text.startswith(prefix):
        return False
    rest = text[len(prefix):]
    return rest[:1] == "T" and rest[1:].isdigit()

def unanswered_fires(round_fires: list[str], stem: str, round_date: str,
                     receipts: list[dict], *, residual_secs: float | None = None,
                     read_instant: dt.datetime | None = None, parse=None) -> list[str]:
    """The round's fires that NO receipt answers — each named by its OWN instant.

    THE ROUND'S OWN CONVENTION DECIDES, and that is what keeps this from being a false RED.
    The hour tokens present among the round's receipts are read first:

    - **No hour key at all** — the round is ROUND-LEVEL and its receipt answers the round.
      Every fire is answered, so nothing is charged. This is the honest reading: a
      date-only subject declares one round, and how many receipts such a round "should"
      carry is not something the subject says.
    - **An hour key present** — the round IS hour-keyed, so each fire owns one, and a fire
      whose hour no receipt carries is UNANSWERED. `hq-cycle-2026-10-16T06` answers the
      06:50 fire and nothing else. A MALFORMED hour key (`T070`) still declares the
      convention, so it exempts nothing — one mistyped row must not silence the round.
    - **No receipts at all** — nothing declares anything, so every fire past its residual is
      unanswered. The caller reaches here only when the round HAS receipts, so this arm is
      the helper's own contract rather than a live path.

    Boundary-checked so `T06` is not satisfied by `T060`. A fire still inside the job's own
    residual is NOT counted: the trigger fired and its lane has not finished, which is the
    same in-flight window the round-level judgement honours (#200/#449) — charging a
    receipt for a round still running would trade this leg's false CLEAN for a false RED.
    """
    subjects = [str(r.get("subject") or "") for r in receipts]
    hours = {tok for tok in (receipt_hour_token(s, stem, round_date) for s in subjects)
             if tok is not None}
    if receipts and not any(receipt_is_hour_keyed(s, stem, round_date) for s in subjects):
        return []
    out: list[str] = []
    for fire in round_fires:
        if residual_secs is not None and read_instant is not None and parse is not None:
            try:
                age = (read_instant - parse(fire)).total_seconds()
            except (ValueError, TypeError):
                age = None
            if age is not None and 0 <= age < residual_secs:
                continue
        token = fire_receipt_token(stem, round_date, fire)
        if not token:
            continue
        if token[-3:] in hours:
            continue
        out.append(fire)
    return out

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


def declared_leg_boundary(repo: Path, key: str) -> tuple[str, str, str]:
    """A board leg's forward bound, read through the ONE boundary reader (#428).

    Returns `(text, refusal, skip_reason)`. Exactly one of the three is populated: the
    DECLARED text, a REFUSAL (a bound is declared but cannot be read — a DEFECT), or a
    skip reason (this tree has declared nothing).

    WHY THIS IS READ AND NOT CARRIED. The three board legs judge a HISTORICAL population,
    and the bound is what keeps them off the history that predates the rule. That bound is
    FACTORY DATA — one member's history is not another's — while this file ships
    byte-identical into every member tree, so a literal here asserts one member's instant
    against another's (#78 clause b).

    The reader's own policy is absent SKIPS / malformed FAILS; this maps it onto
    "not judged, and TOLD so" versus "REFUSED", and never onto "judge everything" — the
    unbounded read the bound exists to stop. The two are kept apart in the WORDING,
    because that is what a reader acts on.
    """
    try:
        reader = boundary_reader()
    except Exception as exc:  # noqa: BLE001 — any load failure is the same refusal
        return "", (
            f"the boundary reader cannot be loaded from {LEDGER_BOUNDARY} ({exc}) — "
            f"REFUSED: without it `{key}` cannot be read, and a leg that judges a "
            f"historical population against a bound it could not read is the unbounded "
            f"behaviour the bound exists to stop"
        ), ""
    try:
        _instant, text = reader.declared_boundary(repo, key)
    except reader.SkipGate as exc:
        return "", "", (
            f"`{key}` is UNDECLARED in this tree ({exc}) — NOT JUDGED: the bound is "
            f"factory data, and judging a whole history against a bound that was never "
            f"declared is the unbounded read the bound exists to stop"
        )
    except reader.GateError as exc:
        return "", (
            f"`{key}` is declared in this tree but cannot be read: "
            f"{'; '.join(str(p) for p in exc.problems)} — REFUSED: a malformed bound is a "
            f"DEFECT, never a licence to judge unbounded"
        ), ""
    return text, "", ""


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

_GATE_BUDGET = None

def gate_budget_module():
    """The gate-budget law, loaded ONCE and cached (#449).

    Cached for the reason `boundary_reader` is: `load_module` re-executes the module on
    every call, and this accessor is reached once per declared job. The margin law is
    BOUND to that module rather than re-derived here — one field, one predicate
    (SKILL.md section 11): a second copy of `4.0 + 0.75/m` in this file would be a second
    statement of the same law, and the two would drift.
    """
    global _GATE_BUDGET
    if _GATE_BUDGET is None:
        _GATE_BUDGET = load_module("gate_budget", GATE_BUDGET)
    return _GATE_BUDGET

def duty_fire_instants(job: dict, fires: list[dict], parse) -> list[dt.datetime]:
    """This job's OWN fire instants, oldest first — the measurement's population.

    Matched by `job_id` where both sides carry one, because a NAME is not an address: two
    jobs may share a name across homes (#126). A fire carrying no id falls back to the
    name, and the fallback is decided PER FIRE rather than per job, so a table written by
    an older daemon still yields the fires it does carry. An unparseable instant is
    dropped rather than defaulted: a fire this reader cannot date contributes no latency,
    and inventing one would put a fabricated measurement under a derived cap.
    """
    job_id = str(job.get("id") or "")
    name = str(job.get("name") or "")
    instants: list[dt.datetime] = []
    for fire in fires:
        fire_id = str(fire.get("job_id") or "")
        fire_name = str(fire.get("job_name") or "")
        if job_id and fire_id:
            if fire_id != job_id:
                continue
        elif name and fire_name:
            if fire_name != name:
                continue
        else:
            continue
        try:
            instants.append(parse(str(fire.get("started_at") or "")))
        except (ValueError, TypeError):
            continue
    return sorted(instants)

def prior_fire_instant(job: dict, fires: list[dict], newest: dt.datetime,
                       parse) -> dt.datetime | None:
    """The fire BEFORE `newest` in this job's OWN run record, or None when none is readable.

    The prior round of #281 (ruling n=2003), and it is READ rather than COMPOSED: the
    instants come from `cron_job_runs` through `duty_fire_instants`, which matches fires to
    this job by id (falling back to the name per fire). `last_run_at - (next_run_at -
    last_run_at)` would name an instant no record carries, and a round this leg names must
    be one the daemon's own table dates (SKILL.md hard rule 4) -- so where no earlier fire
    can be read the caller prints NOT JUDGED with its reason.

    STRICTLY OLDER than `newest`, and that is what makes it robust: the newest instant is
    normally the `last_run_at` fire, so this is the second-newest -- but a row whose
    dispatch stamp is newer than any recorded run row still resolves, because the filter is
    the INSTANT and not the list position.
    """
    earlier = [i for i in duty_fire_instants(job, fires, parse) if i < newest]
    return max(earlier) if earlier else None

# HOW FAR a run record's `started_at` may sit from its row's `last_run_at` and still be read
# as the SAME round (#477). The two stamps are written by DIFFERENT acts -- the row stamps
# the dispatch instant and the run row stamps when the run began -- so they are never equal
# strings, and a string match would find nothing at all. MEASURED over this box's 33 enabled
# rows carrying a readable `last_run_at` (read 2026-10-13T15Z): the gap is ALWAYS positive,
# a run never beginning before its own dispatch stamp, and its maximum is 146.0017 s
# (`factory-growth-map-biweekly`), against a shortest cadence of 6 h (21600 s) in that same
# population. This bound is 1800 s -- 12.33x the measured maximum and 12x below the shortest
# cadence -- so a fire a whole cadence away is never read as this round's.
ROUND_FIRE_MATCH_TOLERANCE_SECS = 1800.0

def round_fire_record(job: dict, fires: list[dict], instant: dt.datetime,
                      parse) -> dict | None:
    """The fire record this round's instant NAMES, or None when no record can be matched.

    `last_run_at` and `cron_job_runs.started_at` are written by different acts, so the round
    is matched by INSTANT: the record whose `started_at` lies nearest `instant` within
    `ROUND_FIRE_MATCH_TOLERANCE_SECS`. Matching is per FIRE and by id-first, exactly as
    `duty_fire_instants` does it, so a table written by an older daemon still yields what it
    carries.

    None is the honest answer when nothing matches, and the caller must then judge the round
    exactly as it did before this reader existed: a suppression that cannot be ATTRIBUTED to
    a round is a suppression this leg must not act on, or an unreadable run table would
    silently excuse every duty on the box.
    """
    job_id = str(job.get("id") or "")
    name = str(job.get("name") or "")
    best: dict | None = None
    best_gap: float | None = None
    for fire in fires:
        fire_id = str(fire.get("job_id") or "")
        fire_name = str(fire.get("job_name") or "")
        if job_id and fire_id:
            if fire_id != job_id:
                continue
        elif name and fire_name:
            if fire_name != name:
                continue
        else:
            continue
        try:
            started = parse(str(fire.get("started_at") or ""))
        except (ValueError, TypeError):
            continue
        gap = abs((started - instant).total_seconds())
        if gap > ROUND_FIRE_MATCH_TOLERANCE_SECS:
            continue
        if best_gap is None or gap < best_gap:
            best, best_gap = fire, gap
    return best

def job_schedule_text(row: dict) -> str:
    """The row's OWN scheduling record as a reader needs it, or a stated absence.

    Carried for #281 so a round judged by FALLBACK names the schedule it belongs to: a
    prior round is only readable against the cadence that produced it. It is printed and
    never parsed into an instant -- `cron_expr` is the row's declaration of WHEN it fires,
    while every instant this leg names is one `cron_job_runs` dates.
    """
    expr = str(row.get("cron_expr") or "").strip()
    nxt = str(row.get("next_run_at") or "").strip()
    if not expr and not nxt:
        return "the row records no schedule (cron_expr and next_run_at are both empty)"
    return f"`{expr or 'no cron_expr'}` (next_run_at {nxt or 'unstated'})"

# ---- the cadence predicate host (#392 ruled n=3949, re-based at #543 ruled n=4087) ---
#
# `docs/measurement-procedure.md` section 4.1 states the own-elapsed-slot predicate as LAW:
# cadence freshness is judged against each job's OWN last elapsed slot, read WITH its
# timezone. No code hosted it, and the two neighbours are DIFFERENT predicates -- neither
# is widened here, and naming them is the point:
#
#   * `tools/audit.py::check_cadence_integrity` judges ONE GLOBAL `<= 30.0` hour window
#     against the newest `run`/`score` row. It reads no job, no schedule, no timezone.
#   * `duty_residual_for`'s `cadence_secs` (below) is the median gap between the job's own
#     FIRES -- an OBSERVED cadence. It measures how often a job has been firing; it cannot
#     say a slot ARRIVED and went unexecuted, because a job that never fired has no gap.
#
# WHAT #543 CHANGED, AND WHY THE OLD PREDICATE WAS WRONG AT THE BYTES. The first host of
# this predicate read the TWO SCHEDULER COLUMNS and compared them: `last_run_at < slot`
# meant MISSED. That is false for the whole of the scheduler's normal dispatch latency --
# the slot arrives at T, the daemon wakes at T+35s (p50 measured over 1,068 paired rows),
# and in between the row reads MISSED for a job that is about to run. The old host also
# carried a `HELD` bucket whose precondition (`last_run_at >= next_run_at`) the writer
# cannot produce: `src/cron/scheduler.rs:213-217` writes both columns in ONE statement, so
# after any dispatch `last_run_at` is that instant and `next_run_at` is strictly later.
# Measured 2026-10-22: 0 of 69 `cron_jobs` rows (34 enabled) satisfy it, so `HELD 0` was a
# structurally guaranteed zero wearing the shape of a measurement (#271). HELD is RETIRED
# here, and the retirement is PRINTED rather than left as an empty bucket -- see
# `CADENCE_SLOT_RETIRED`.
#
# THE EVIDENCE IS NOW THE RUN STORE, NOT THE COLUMNS' WRITE ORDER. "Was this slot
# dispatched?" is answered by a row in `cron_job_runs` at or after the slot, which is a
# dispatch RECORD rather than an inference from which of two columns was written last.
# `cron_job_runs` records ATTEMPTS, not only successes (measured 2026-10-22: 6,406 rows --
# success 5,967, error 271, interrupted 120, delivery_failed 24), so a dispatch that failed
# still counts as dispatched, which is what this predicate asks.
#
# AND THE BOUND IS PER JOB, DERIVED, AND PRINTED. Ruling n=4087 REFUSED the filing's own
# "a grace of a few minutes" on measurement: over the 1,200 most recent run rows paired to
# their cron boundary, lateness ran p50 35s / p95 94s / p99 423s / max 1,478s, with 10.4%
# over 60s and 1.8% over 300s. One global constant cannot serve that population -- a grace
# covering the tail (>= 1,478s) exceeds the period of every hourly job on this box, so it
# would blind the leg to genuine stops, while a grace fitting an hourly job leaves 1.8% of
# real dispatches misreported. So `cadence_grace_for` derives a grace PER JOB from that
# job's own lateness history, and every judged row prints its grace, its basis and the
# sample it rests on. A tolerance a reader cannot see is a tolerance they cannot audit.
#
# THE READING OF THE PENDING SLOT IS STILL THE SCHEDULER'S OWN. `cron_jobs.next_run_at` is
# stored ALREADY RESOLVED against the row's own `timezone` (column `timezone TEXT NOT NULL
# DEFAULT 'UTC'`), so the predicate needs no cron parser for the SLOT. Measured live
# 2026-10-21: `ai-antispam-bot-service-health` Europe/Moscow `15 9 * * *` stores
# `2026-10-21T06:15:00+00:00`; `factory-growth-map-biweekly` Europe/Moscow `0 9 1,15 * *`
# stores `2026-11-01T06:00:00+00:00`. The Moscow rows are the proof: 09:15 local as 06:15Z.
#
# HISTORICAL boundaries are the one thing the scheduler does NOT store, and the grace needs
# them: lateness is (run instant - the boundary that run served). `cron_boundaries_before`
# supplies them from `cron_expr` + `timezone`, in stdlib `zoneinfo`, and it is NOT trusted
# on its own -- it is VALIDATED against the scheduler's own resolved `next_run_at` before
# any number it produces is used (rule 7: a check whose expected state is read from the
# thing it checks proves nothing; here the independent declaration is the scheduler's own
# instant, which this reader never computes). A job whose parse cannot reproduce the
# scheduler's instant has its grace DECLARED UNDERTAKABLE and is printed as such, rather
# than judged against a tolerance derived from a parse that already disagrees.
CADENCE_SLOT_DISPATCHED = "DISPATCHED"
CADENCE_SLOT_MISSED = "MISSED"
CADENCE_SLOT_NOT_JUDGED = "NOT JUDGED"
CADENCE_SLOT_UNREADABLE = "UNREADABLE"

# THE RETIREMENT, AS A DECLARATION. `HELD` is named here so the render can say it is GONE
# rather than leave a reader to notice an absent bucket, and so a control can assert the
# token appears in no verdict. Its reason is the writer's own shape, not a preference.
CADENCE_SLOT_RETIRED = (
    ("HELD",
     "RETIRED at #543: its precondition `last_run_at >= next_run_at` cannot occur, because "
     "src/cron/scheduler.rs:213-217 writes both columns in ONE statement, so after any "
     "dispatch last_run_at is that instant and next_run_at is strictly later (measured "
     "2026-10-22: 0 of 69 cron_jobs rows, 34 enabled, satisfy it). The bucket counted a "
     "structurally impossible state and read as health; the replacement bucket is "
     f"{CADENCE_SLOT_DISPATCHED}, which is decided by a run ROW."),
)

CADENCE_SLOT_VERDICTS = (
    CADENCE_SLOT_DISPATCHED,
    CADENCE_SLOT_MISSED,
    CADENCE_SLOT_NOT_JUDGED,
    CADENCE_SLOT_UNREADABLE,
)

# THE GRACE'S THREE CONSTANTS, and each one is a BOUND rather than a tolerance (#543).
#   * FLOOR: below this, scheduler jitter alone would read as a miss. Measured p50 over
#     1,068 paired rows is 35s, so a floor under a couple of minutes buys nothing.
#   * CAP: at or above a job's own period the grace outlives the next fire and the leg
#     cannot discriminate (n=1518 FINDING 3, the same failure `duty_residual_for` names).
#     900s sits under every period on this box except `ai-antispam-loss-watch` (1,800s).
#   * PERIOD FRACTION: the cap that binds first for a fast job. A job whose PERIOD is
#     shorter than its own latency tail cannot be judged by timing at all, and this is the
#     clamp that says so out loud instead of emitting a coin flip.
CADENCE_GRACE_FLOOR_SECS = 120.0
CADENCE_GRACE_CAP_SECS = 900.0
CADENCE_GRACE_PERCENTILE = 0.95
CADENCE_GRACE_WINDOW = 50
CADENCE_GRACE_PERIOD_FRACTION = 0.5
# A scan bound, so a schedule this reader mis-parses cannot walk the calendar forever. It is
# also the point at which the derivation gives up and DECLARES rather than guesses.
CADENCE_BOUNDARY_SCAN_DAYS = 800

# THE DAY-OF-WEEK DIALECT IS THE SCHEDULER'S, AND IT IS NOT POSIX. Measured 2026-10-22 on
# this box: `ai-antispam-wave0-unactivated-reprobe` carries `0 12 * * 2` and the scheduler
# stored `2026-10-26T09:00:00+00:00` (12:00 MSK) -- a MONDAY. Under POSIX numbering `2` is
# Tuesday; under the Rust `cron` crate's it is Monday, because that crate numbers 1=Sunday
# through 7=Saturday. Named days cannot discriminate the two (each dialect maps a NAME to its
# own number, so `Mon` lands on Monday either way); a single numeric day field settles it, and
# this box has exactly one. Reading POSIX here would have placed that job's boundaries a day
# off and reported every one of its dispatches as ~24 h late.
#
# 0 is accepted as a second spelling of Sunday, which costs nothing and keeps a POSIX-written
# row from being refused outright. The validation in `cadence_grace_for` remains the net: a
# row whose parse cannot reproduce the scheduler's own `next_run_at` derives no grace.
CRON_FIELD_BOUNDS = (
    (0, 59),   # minute
    (0, 23),   # hour
    (1, 31),   # day of month
    (1, 12),   # month
    (0, 7),    # day of week, SCHEDULER dialect: 1=Sunday .. 7=Saturday, 0 also Sunday
)

# The same dialect as the numeric field above: 1=Sunday .. 7=Saturday.
CRON_DOW_NAMES = {
    "sun": 1, "mon": 2, "tue": 3, "wed": 4, "thu": 5, "fri": 6, "sat": 7,
}
CRON_MONTH_NAMES = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

def _cron_token_value(token: str, names: dict | None) -> int:
    """One field token as an integer, accepting the three-letter names cron allows.

    THE LIVE BOX SCHEDULES WITH NAMES, not only digits: measured 2026-10-22, four enabled
    rows carry `Mon`, `Fri` or `Mon,Wed,Fri` in their day-of-week field. A parser that
    accepted only digits would call those rows' grace UNDERTAKABLE and then never judge
    their slots at all -- a silent coverage hole dressed as a principled refusal.
    """
    token = token.strip()
    if token.isdigit():
        return int(token)
    if names and token[:3].lower() in names:
        return names[token[:3].lower()]
    raise ValueError(f"unsupported token {token!r}")

def _cron_field_values(spec: str, low: int, high: int, names: dict | None = None) -> frozenset:
    """One cron field expanded to the values it matches. Raises ValueError on any doubt.

    A SUBSET OF THE LANGUAGE, deliberately: the five-field syntax this box actually
    schedules with -- `*`, `*/n`, `a`, `a-b`, `a-b/n` and comma lists of those. Anything
    else raises, and the raise is the point: an unrecognised token must make the DERIVATION
    undertakable (and say so) rather than silently match nothing, which would read as "this
    job has no boundaries" and then as a clean slot.
    """
    values: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            raise ValueError(f"empty list item in field {spec!r}")
        step = 1
        if "/" in part:
            part, _, raw_step = part.partition("/")
            if not raw_step.isdigit() or int(raw_step) == 0:
                raise ValueError(f"bad step {raw_step!r} in field {spec!r}")
            step = int(raw_step)
        if part == "*":
            start, end = low, high
        elif "-" in part:
            raw_start, _, raw_end = part.partition("-")
            start = _cron_token_value(raw_start, names)
            end = _cron_token_value(raw_end, names)
        else:
            start = _cron_token_value(part, names)
            end = high if step != 1 else start
        if start < low or end > high or start > end:
            raise ValueError(
                f"range {start}-{end} outside {low}-{high} in field {spec!r}")
        values.update(range(start, end + 1, step))
    if not values:
        raise ValueError(f"field {spec!r} matches nothing")
    return frozenset(values)

def parse_cron_expr(expr: str) -> dict:
    """A five-field cron expression as the five value sets it matches. Raises on doubt."""
    fields = str(expr or "").split()
    if len(fields) != 5:
        raise ValueError(
            f"{expr!r} is not a five-field cron expression (got {len(fields)} field(s))")
    return {
        "minute": _cron_field_values(fields[0], *CRON_FIELD_BOUNDS[0]),
        "hour": _cron_field_values(fields[1], *CRON_FIELD_BOUNDS[1]),
        "dom": _cron_field_values(fields[2], *CRON_FIELD_BOUNDS[2]),
        "month": _cron_field_values(fields[3], *CRON_FIELD_BOUNDS[3],
                                     names=CRON_MONTH_NAMES),
        "dow": _cron_field_values(fields[4], *CRON_FIELD_BOUNDS[4], names=CRON_DOW_NAMES),
        # The day fields are the one place standard cron is not a plain AND: when BOTH are
        # restricted a boundary matches if EITHER does, and when one is `*` the other alone
        # decides. Recorded at parse time so the matcher cannot get it wrong twice.
        "dom_star": fields[2].strip() == "*",
        "dow_star": fields[4].strip() == "*",
    }

def cron_day_matches(day, parsed: dict) -> bool:
    """Whether a calendar DAY can carry a boundary of the parsed schedule.

    Standard cron's one non-AND rule lives here, once: when BOTH day fields are restricted a
    day matches if EITHER does, and when one is `*` the other alone decides. Recorded at
    parse time (`dom_star`/`dow_star`) so the matcher cannot get it wrong twice.
    """
    if day.month not in parsed["month"]:
        return False
    dom_hit = day.day in parsed["dom"]
    # Python's weekday() is Monday=0; the scheduler's day-of-week is 1=Sunday..7=Saturday.
    scheduler_dow = ((day.weekday() + 1) % 7) + 1
    dow_hit = scheduler_dow in parsed["dow"] or (
        scheduler_dow == 1 and 0 in parsed["dow"])
    if parsed["dom_star"] and parsed["dow_star"]:
        return True
    if parsed["dom_star"]:
        return dow_hit
    if parsed["dow_star"]:
        return dom_hit
    return dom_hit or dow_hit

def cron_boundary_matches(instant, parsed: dict) -> bool:
    """Whether a zone-aware instant IS a boundary of the parsed schedule.

    Second and microsecond must be ZERO: a boundary is a minute-resolution event, while a
    run's own `started_at` carries nanoseconds and is never itself a boundary.
    """
    if instant.second != 0 or instant.microsecond != 0:
        return False
    if instant.minute not in parsed["minute"] or instant.hour not in parsed["hour"]:
        return False
    return cron_day_matches(instant.date(), parsed)

def cron_boundaries_before(expr: str, timezone: str, instant, *, limit: int,
                           scan_days: int = CADENCE_BOUNDARY_SCAN_DAYS) -> list:
    """The `limit` most recent boundaries at or before `instant`, newest first.

    Walks BACKWARD BY DAY and expands only the hours and minutes the schedule names, so a
    daily job costs one day-scan per boundary instead of 1,440 minute-scans. `zoneinfo` is
    stdlib, and the local wall time is what the schedule names -- the same reading the
    scheduler applies when it stores `next_run_at` already resolved.

    Raises ValueError when the expression, the zone or the scan bound defeats it. The caller
    treats every raise as UNDERTAKABLE and prints the reason: a boundary this reader cannot
    place must never become a lateness of zero.
    """
    parsed = parse_cron_expr(expr)
    raw_zone = str(timezone or "UTC").strip()
    try:
        zone = dt.timezone.utc if raw_zone.upper() in ("", "UTC") \
            else zoneinfo.ZoneInfo(raw_zone)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"timezone {timezone!r} cannot be resolved ({exc})") from exc
    if instant.tzinfo is None:
        raise ValueError("the instant to walk back from carries no zone offset")
    local = instant.astimezone(zone)
    hours = sorted(parsed["hour"], reverse=True)
    minutes = sorted(parsed["minute"], reverse=True)
    found: list = []
    day = local.date()
    for _ in range(scan_days):
        if cron_day_matches(day, parsed):
            for hour in hours:
                for minute in minutes:
                    candidate = dt.datetime(day.year, day.month, day.day, hour, minute,
                                            tzinfo=zone)
                    if candidate > local:
                        continue
                    if not cron_boundary_matches(candidate, parsed):
                        continue
                    found.append(candidate)
                    if len(found) >= limit:
                        return found
        day = day - dt.timedelta(days=1)
    raise ValueError(
        f"no {limit} boundary(ies) of {expr!r} in {raw_zone} found within "
        f"{scan_days} day(s) before {local.isoformat()}")

def cron_zone(timezone: str):
    """The zone a row's schedule is written in. Raises ValueError when it cannot resolve."""
    raw = str(timezone or "UTC").strip()
    try:
        return dt.timezone.utc if raw.upper() in ("", "UTC") else zoneinfo.ZoneInfo(raw)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"timezone {raw!r} cannot be resolved ({exc})") from exc

def cadence_job_runs(row: dict, fires: list[dict] | None, *, parse=None) -> list | None:
    """The dispatch RECORDS belonging to ONE cron row, newest last.

    MATCHED BY ID FIRST, THEN BY NAME (#543). `cron_job_runs` carries both, and a name alone
    is not an address -- two jobs may share a name across homes -- so an id match wins. A
    home that records no `job_id` at all still matches by name, which is why the fallback
    exists rather than being refused: refusing would make every run in such a home invisible
    and then read as "never dispatched", the exact false positive this unit removes.

    `None` (not `[]`) when no store was supplied: "the store was not read" and "the store
    holds no run for this job" are different facts and must never render the same.
    """
    if fires is None:
        return None
    parse = parse or reader_parse_ts
    job_id = str(row.get("id") or "").strip()
    name = str(row.get("name") or "").strip()
    home = str(row.get("home") or "").strip()
    instants: list = []
    for fire in fires:
        if home and str(fire.get("home") or "").strip() not in ("", home):
            continue
        matched = bool(job_id) and str(fire.get("job_id") or "").strip() == job_id
        if not matched and name:
            matched = str(fire.get("job_name") or "").strip() == name
        if not matched:
            continue
        try:
            instant = parse(str(fire.get("started_at") or ""))
        except (ValueError, TypeError):
            continue
        if instant is not None and instant.tzinfo is not None:
            instants.append(instant)
    instants.sort()
    return instants

def _percentile(values: list[float], fraction: float) -> float:
    """Nearest-rank percentile over an ASCENDING list, so the value is one that was MEASURED.

    Interpolated percentiles invent a latency no run exhibited, and this figure is printed
    as a tolerance a reader may check against the runs themselves.
    """
    if not values:
        raise ValueError("no values to take a percentile of")
    index = min(len(values) - 1, max(0, int(round(fraction * (len(values) - 1)))))
    return values[index]

def cadence_grace_for(row: dict, runs: list, *, parse=None) -> dict:
    """The grace window for ONE job, DERIVED from that job's own lateness, with its basis.

    THE QUANTITY. For every recent run of this job, lateness is (the run's `started_at` - the
    boundary that run served). The boundaries come from `cron_boundaries_before`, and the
    parse that produces them is VALIDATED first against the scheduler's own resolved
    `next_run_at`: if this reader's reading of `cron_expr` + `timezone` cannot reproduce the
    instant the scheduler itself stored, the derivation is refused outright. That is the
    independent declaration rule 7 asks for -- the expected state is not read from the
    instrument being checked.

    THE VALUE. `p95` of that job's lateness over its last `CADENCE_GRACE_WINDOW` runs,
    clamped to `[CADENCE_GRACE_FLOOR_SECS, CADENCE_GRACE_CAP_SECS]` and then to
    `CADENCE_GRACE_PERIOD_FRACTION` of its own period. The clamp that binds is NAMED in
    `basis`, and every figure the arithmetic used travels in the returned record, so the
    number is checkable rather than asserted.

    THE REFUSAL. A job with no run history, no parseable schedule, or a schedule this reader
    cannot reproduce the scheduler's slot for returns `grace_secs=None` with
    `basis="underivable"` and the reason. The CALLER must then decline to judge the slot: a
    tolerance invented for a job whose history could not be read is the #507
    permanent-false-positive class this unit exists to remove.
    """
    parse = parse or reader_parse_ts
    record = {
        "grace_secs": None,
        "basis": "underivable",
        "percentile": CADENCE_GRACE_PERCENTILE,
        "sample": 0,
        "p50": None,
        "p95": None,
        "max": None,
        "period_secs": None,
        "unpaired": 0,
        "period_bound_binds": False,
        "reason": "",
    }
    expr = str(row.get("cron_expr") or "").strip()
    timezone = str(row.get("timezone") or "UTC")
    raw_next = str(row.get("next_run_at") or "").strip()

    def _refuse(reason: str) -> dict:
        return {**record, "reason": reason}

    if not expr:
        return _refuse(
            "the row records no cron_expr, so its boundaries cannot be placed and no "
            "lateness can be measured -- the grace is UNDERTAKABLE rather than defaulted")
    if not raw_next:
        return _refuse("the row records no next_run_at to validate a schedule parse against")
    try:
        slot = parse(raw_next)
    except (ValueError, TypeError) as exc:
        return _refuse(f"next_run_at {raw_next!r} does not parse ({exc})")
    if slot.tzinfo is None:
        return _refuse(f"next_run_at {raw_next!r} carries no zone offset")
    try:
        zone = cron_zone(timezone)
        parsed = parse_cron_expr(expr)
    except ValueError as exc:
        return _refuse(f"the row's schedule cannot be parsed ({exc})")
    # THE INDEPENDENT DECLARATION. The scheduler stored this instant already resolved against
    # the row's zone; this reader's parse must agree that the instant IS a boundary of the
    # schedule, or the parse is wrong and nothing derived from it is usable.
    if not cron_boundary_matches(slot.astimezone(zone), parsed):
        return _refuse(
            f"this reader's parse of {expr!r} in {timezone} does not reproduce the "
            f"scheduler's own next_run_at {raw_next} as a boundary of that schedule, so the "
            f"parse is not trustworthy and no grace is derived from it")

    window = [instant for instant in runs or []][-CADENCE_GRACE_WINDOW:]
    if not window:
        return _refuse(
            "no dispatch record for this job in cron_job_runs, so there is no lateness "
            "history to derive a grace from")
    try:
        boundaries = cron_boundaries_before(
            expr, timezone, window[-1], limit=len(window) + 1)
    except ValueError as exc:
        return _refuse(f"this job's boundaries cannot be placed ({exc})")

    # THE PERIOD COMES FROM THE BOUNDARIES THEMSELVES, ASCENDING -- `cron_boundaries_before`
    # returns newest-first, and subtracting in that order yields a NEGATIVE period, which
    # then inverts every clamp downstream. Measured before the fix: 42 of 42 jobs printed a
    # negative period and a negative grace.
    ascending = sorted(boundaries)
    gaps = [(later - earlier).total_seconds()
            for earlier, later in zip(ascending, ascending[1:])]
    period = statistics.median(gaps) if gaps else None

    # EACH RUN IS PAIRED TO ITS NEAREST BOUNDARY, and a run that cannot have served one is
    # EXCLUDED rather than folded in. Pairing to "the newest boundary at or before the run"
    # is wrong for a job whose SCHEDULE WAS EDITED: `inferhub-self-audit-daily` moved from a
    # ~06:02Z fire to a 06:40Z one, and its older runs then pair to the PREVIOUS day's
    # boundary and report a 23.4-hour lateness that no dispatch ever had (measured
    # 2026-10-22: p50 84,359s against a real tail of 35-540s). A run more than half a period
    # from any boundary is indistinguishable from an early fire, so it is counted and
    # printed as `unpaired` -- and the bound is safe in the direction that matters, because
    # the observed tail on this box (max 1,478s over 1,068 paired rows) is far inside half
    # of every period here.
    ceiling = (period * CADENCE_GRACE_PERIOD_FRACTION) if period else None
    lateness: list[float] = []
    unpaired = 0
    for instant in window:
        boundary = min(boundaries,
                       key=lambda candidate: abs((instant - candidate).total_seconds()))
        delta = (instant - boundary).total_seconds()
        if delta < 0 or (ceiling is not None and delta > ceiling):
            unpaired += 1
            continue
        lateness.append(delta)
    if not lateness:
        return _refuse(
            f"none of the {len(window)} run(s) of this job could be paired to a boundary "
            f"of {expr!r} ({unpaired} unpaired), so no lateness was measured")
    lateness.sort()
    p50 = _percentile(lateness, 0.50)
    p95 = _percentile(lateness, CADENCE_GRACE_PERCENTILE)
    grace = min(max(p95, CADENCE_GRACE_FLOOR_SECS), CADENCE_GRACE_CAP_SECS)
    basis = "p95" if grace == p95 else ("floor" if grace == CADENCE_GRACE_FLOOR_SECS else "cap")
    period_bound = False
    if period:
        ceiling = period * CADENCE_GRACE_PERIOD_FRACTION
        if grace > ceiling:
            grace = ceiling
            basis = "period"
            period_bound = True
    return {
        **record,
        "grace_secs": float(grace),
        "basis": basis,
        "sample": len(lateness),
        "p50": float(p50),
        "p95": float(p95),
        "max": float(lateness[-1]),
        "period_secs": float(period) if period else None,
        "unpaired": unpaired,
        "period_bound_binds": period_bound,
        "reason": (
            f"{basis}: p{CADENCE_GRACE_PERCENTILE * 100:.0f} of {len(lateness)} paired "
            f"run(s) = {p95:.0f}s (p50 {p50:.0f}s, max {lateness[-1]:.0f}s"
            + (f", {unpaired} unpaired" if unpaired else "") + f"), clamped to "
            f"[{CADENCE_GRACE_FLOOR_SECS:.0f}s floor, {CADENCE_GRACE_CAP_SECS:.0f}s cap"
            + (f", {CADENCE_GRACE_PERIOD_FRACTION:.0%} of a {period:.0f}s period"
               if period else "")
            + f"] -> {grace:.0f}s"
        ),
    }

def cadence_slot_verdict_for(row: dict, *, now, parse=None, runs=None,
                             grace: dict | None = None) -> dict:
    """ONE enabled cron row against its OWN pending slot, as a record naming why.

    `(instant, reason)` pairs throughout, never a bare `None`: a row this host cannot read
    must say WHY, because "could not be placed" and "placed and clean" are the two readings
    a zero silently merges (#271).

    A NAIVE INSTANT IS UNREADABLE, never assumed UTC. `reader_parse_ts` returns exactly what
    the text says, so `2026-10-21 06:15:00` parses to a zone-less datetime; comparing that
    to an aware `now` would raise, and ASSUMING UTC would shift a Moscow row by three hours
    and manufacture a false MISSED -- the permanent-false-positive class #507 names. Every
    live row carries an offset (measured 2026-10-22: 34 of 34 enabled), so the strict
    reading costs nothing today and refuses to invent one tomorrow.

    THE ORDER OF THE TESTS IS THE LAW (#543):

      1. a slot that has not ARRIVED is NOT JUDGED -- nothing can have been missed yet;
      2. a slot that has arrived and has a RUN ROW at or after it is DISPATCHED, whatever
         the scheduler columns say;
      3. a slot that has arrived with no run row is inside its GRACE while `now < slot +
         grace`, and MISSED only past it;
      4. a slot whose grace is UNDERTAKABLE is NOT JUDGED and says so -- a tolerance
         invented for a job whose history could not be read is the defect, not the fix.

    Test 2 is what makes the false positive go away, and test 3 is what keeps it honest: a
    change that only widens a window and never fires proves nothing.
    """
    parse = parse or reader_parse_ts
    name = str(row.get("name") or "(unnamed row)")
    record = {
        "name": name,
        "id": str(row.get("id") or "unstated"),
        "home": str(row.get("home") or "unstated"),
        "schedule": job_schedule_text(row),
        # PRINTED, never used to derive an instant: `next_run_at` already carries the zone,
        # and a second application of the same zone is how two readers of one field drift.
        "timezone": str(row.get("timezone") or "unstated"),
        "next_run_at": str(row.get("next_run_at") or ""),
        "last_run_at": str(row.get("last_run_at") or ""),
        "runs_read": 0 if runs is None else len(runs),
        # THE GRACE TRAVELS EVEN WHEN NO SLOT HAS ARRIVED. It is a property of the JOB, not
        # of the verdict: on a healthy box every slot is in the future, so a derivation
        # attached only to a judged row would never be printed at all -- and then the whole
        # of #543 would be invisible in the normal case.
        "grace": grace,
    }

    def _unreadable(reason: str) -> dict:
        return {**record, "verdict": CADENCE_SLOT_UNREADABLE, "reason": reason}

    raw_next = record["next_run_at"].strip()
    if not raw_next:
        return _unreadable(
            "the row records no next_run_at, so the host has no slot to judge and does NOT "
            "count it as served"
        )
    try:
        slot = parse(raw_next)
    except (ValueError, TypeError) as exc:
        return _unreadable(f"next_run_at {raw_next!r} does not parse ({exc})")
    if slot.tzinfo is None:
        return _unreadable(
            f"next_run_at {raw_next!r} carries no zone offset, so it cannot be placed "
            f"against the read instant without assuming a zone"
        )

    if now < slot:
        return {
            **record,
            "verdict": CADENCE_SLOT_NOT_JUDGED,
            "reason": f"slot {raw_next} has not arrived (read at {now.isoformat()})",
        }

    if runs is None:
        # NOT the same as "no run for this slot": the store was never read, so this row's
        # dispatch state is UNKNOWN and must not be reported as a miss.
        return _unreadable(
            f"slot {raw_next} has arrived, but no cron_job_runs store was supplied to this "
            f"host, so whether it was dispatched cannot be answered"
        )

    if grace is None:
        grace = cadence_grace_for(row, runs, parse=parse)
    served = [instant for instant in runs if instant >= slot]
    if served:
        lateness = (served[0] - slot).total_seconds()
        return {
            **record,
            "verdict": CADENCE_SLOT_DISPATCHED,
            "grace": grace,
            "reason": (
                f"slot {raw_next} was dispatched at {served[0].isoformat()} "
                f"({lateness:.0f}s after it), recorded in cron_job_runs"
            ),
        }
    if grace["grace_secs"] is None:
        return {
            **record,
            "verdict": CADENCE_SLOT_NOT_JUDGED,
            "grace": grace,
            "grace_underivable": True,
            "reason": (
                f"slot {raw_next} has arrived with no dispatch record, and the grace it "
                f"would be judged against is UNDERTAKABLE: {grace['reason']}"
            ),
        }
    unserved = (now - slot).total_seconds()
    if unserved < grace["grace_secs"]:
        return {
            **record,
            "verdict": CADENCE_SLOT_NOT_JUDGED,
            "grace": grace,
            "reason": (
                f"slot {raw_next} has arrived {unserved:.0f}s ago with no dispatch record "
                f"yet, inside this job's derived grace of {grace['grace_secs']:.0f}s "
                f"({grace['reason']})"
            ),
        }
    return {
        **record,
        "verdict": CADENCE_SLOT_MISSED,
        "grace": grace,
        "reason": (
            f"slot {raw_next} arrived {unserved:.0f}s ago, PAST this job's derived grace of "
            f"{grace['grace_secs']:.0f}s ({grace['reason']}), and cron_job_runs records no "
            f"dispatch at or after it"
        ),
    }

def cadence_slot_leg(
    cron_rows: list[dict],
    homes_read: list[str],
    unreached: list[str],
    *,
    read_at: str = "",
    now=None,
    parse=None,
    fires: list[dict] | None = None,
) -> dict:
    """The cadence-slot leg: did each enabled job's OWN elapsed slot get DISPATCHED?

    ONE READING, ONE LEG. The rows are the same `box_cron_rows` fetch the cron-thinness,
    notify-receipt and duty-receipt legs are handed, so this leg opens no database of its
    own and cannot disagree with them about what the box holds. The dispatch records are the
    same `cron_run_fires` read the two receipt legs take, injected for the reason those legs
    take it injected: a probe must never have its verdict decided by the live box's own runs
    table, and a leg whose input is not injectable cannot be tested at all.

    WHAT THIS LEG MEASURES, stated because its counts must not read as health (#543): the
    lateness of this box's dispatches and the slots that have gone UNSERVED past their own
    derived grace. It is not a scheduler-health figure. `DISPATCHED` is near-zero in normal
    operation for a reason that is structural rather than reassuring -- the scheduler
    advances `next_run_at` in the same statement that records the run, so by the time this
    reader looks, the slot it would have judged has already moved into the future and the
    row reads NOT JUDGED. That is why the derivation, not the bucket, is what this leg
    prints.

    BOUNDS, declared on the leg itself so a green line cannot be read as more than it is:

      * DETECTOR, NOT PREVENTION. It catches a slot the scheduler let pass unserved; it
        cannot catch a scheduler that advanced `next_run_at` without a run, because the
        advanced instant is the only record of the slot.
      * AN OVERLAP-SKIPPED SLOT IS INDISTINGUISHABLE FROM A MISS. If a run of the same job
        is still in flight when its next slot arrives and the daemon suppresses the
        overlap, no run row is written and this leg cannot tell that from a dispatch that
        never happened. There is no overlap guard in `cron_jobs` this reader can consult, so
        the bound is stated rather than worked around; such a slot is reported MISSED.
      * A JOB WHOSE PERIOD IS SHORTER THAN ITS OWN LATENCY TAIL CANNOT BE JUDGED BY TIMING
        ALONE. For such a job the grace is clamped to half its period and the clamp is
        PRINTED (`basis="period"`), because a tolerance that reaches the next fire cannot
        discriminate. The verdict it then emits is a coin flip by construction, and the
        printed basis is what tells a reader so.
      * #528's CLASS IS NOT COVERED. A slot that dispatched and DIED is dispatched: the run
        row exists, so this leg reads DISPATCHED. #528 was re-scoped at n=3923 to a lane that
        wakes and emits no tool call, which is a different defect, and it is named here so
        the citation does not silently imply coverage this leg does not have.
    """
    parse = parse or reader_parse_ts
    if now is None:
        now = None
        if read_at:
            try:
                now = parse(read_at)
            except (ValueError, TypeError):
                now = None
        if now is None:
            now = dt.datetime.now(dt.timezone.utc)

    examined = len(cron_rows)
    counts = {verdict: 0 for verdict in CADENCE_SLOT_VERDICTS}
    findings: list[dict] = []
    for row in cron_rows:
        runs = cadence_job_runs(row, fires, parse=parse)
        # DERIVED FOR EVERY ROW, not only for the ones that reach a verdict (#543). The
        # grace is what this leg has to SHOW; a run that prints no derivation because no
        # slot had arrived would hide the fix in exactly the state the box is normally in.
        grace = cadence_grace_for(row, runs, parse=parse) if runs else None
        record = cadence_slot_verdict_for(row, now=now, parse=parse, runs=runs, grace=grace)
        counts[record["verdict"]] = counts.get(record["verdict"], 0) + 1
        findings.append(record)

    # ONLY A MISSED SLOT IS A PROBLEM, and the severity split is a reading of the read path
    # rather than a convenience. `box_cron_rows` STATES that a home whose `cron_jobs`
    # predates `next_run_at` "reads NULL for them and is still READ, because those two are
    # CARRIED for the report and no instant is derived from them" -- so an absent
    # `next_run_at` is a LEGITIMATE row shape, not a defect of the row. Reding it would put
    # a permanent red on every member factory whose schema predates the column, which is the
    # permanent-false-positive class #507 names.
    #
    # What #271 forbids is counting such a row as ZERO -- as served, or as clean. That is
    # honoured by the COUNT, not by the exit code: it lands in `UNREADABLE` (never
    # `DISPATCHED`), its own reason is printed, and the totals line carries the count.
    problems: list[str] = []
    for record in findings:
        if record["verdict"] == CADENCE_SLOT_MISSED:
            problems.append(
                f"cadence slot MISSED for `{record['name']}` ({record['home']}): "
                f"{record['reason']}")

    underivable = [record for record in findings if record.get("grace_underivable")]
    coverage = {
        # THE POPULATION IS ALWAYS PRINTED. `examined 0, 0 problems` and `examined 34, 0
        # problems` are different readings, and only the count tells them apart (skill
        # section 8: a verdict over an examined-nothing read is not a verdict).
        "examined": examined,
        "unit": "enabled cron row(s)",
        "counts": counts,
        "homes_read": list(homes_read),
        "unreached": list(unreached),
        "read_at": read_at,
        "read_instant": now.isoformat(),
        "findings": findings,
        # THE DERIVATION, PER JOB, because the ruling refuses a tolerance a reader cannot
        # audit. One entry per row that reached a grace at all; a row that never arrived at
        # a slot has no grace to print and is not listed here.
        "graces": [
            {
                "name": record["name"],
                "grace_secs": (record.get("grace") or {}).get("grace_secs"),
                "basis": (record.get("grace") or {}).get("basis"),
                "sample": (record.get("grace") or {}).get("sample"),
                "p95": (record.get("grace") or {}).get("p95"),
                "period_secs": (record.get("grace") or {}).get("period_secs"),
                "period_bound_binds": (record.get("grace") or {}).get("period_bound_binds"),
                "reason": (record.get("grace") or {}).get("reason"),
            }
            for record in findings if record.get("grace")
        ],
        # A COUNT THAT IS NOT A HEALTH FIGURE: rows whose slot arrived unserved and whose
        # grace could not be derived. Printed so a population of them cannot hide inside
        # NOT JUDGED, which is where a healthy row lives.
        "grace_underivable": len(underivable),
        # AND THE WHOLE POPULATION, so a row whose grace could not be derived is visible
        # even when its slot has not arrived yet. The count above is the JUDGED subset --
        # rows whose slot arrived unserved and which this leg therefore declined to judge --
        # and reporting only that one would hide an undertakable job on a healthy box, which
        # is the normal state.
        "grace_underivable_rows": sum(
            1 for record in findings
            if (record.get("grace") or {}).get("grace_secs") is None),
        "dispatches_read": sum(record.get("runs_read") or 0 for record in findings),
        "retired": [{"verdict": verdict, "reason": reason}
                    for verdict, reason in CADENCE_SLOT_RETIRED],
        "bound": (
            "detector, not prevention: it catches a slot the scheduler let pass unserved; "
            "it does NOT catch a slot that dispatched and died (#528, re-scoped at n=3923), "
            "it cannot catch a scheduler that advanced next_run_at without a run, an "
            "overlap-skipped slot is indistinguishable from a miss (no overlap guard is "
            "readable from cron_jobs), and a job whose period is shorter than its own "
            "latency tail is judged against a period-clamped grace whose verdict is a coin "
            "flip by construction"
        ),
    }

    if examined == 0:
        return {
            "name": "cadence-slot",
            "status": "NOT RUN",
            "problems": [],
            "excused": [],
            "coverage": {
                **coverage,
                "reason": (
                    "no enabled cron row was read, so no slot was judged -- an empty "
                    "population is NOT a clean round"
                    + (f"; unreached: {'; '.join(unreached)}" if unreached else "")
                ),
            },
        }

    judged = counts.get(CADENCE_SLOT_DISPATCHED, 0) + counts.get(CADENCE_SLOT_MISSED, 0)
    # NOT JUDGED IS NOT A READING LIMIT, AND CONFLATING THE TWO SILENCES THE LEG.
    # `next_run_at` is the slot the scheduler is WAITING for, and it ADVANCES on every
    # dispatch -- so a healthy row is permanently `now < next_run_at`, i.e. permanently
    # NOT JUDGED. Measured on this box 2026-10-22T12:52Z: 34 enabled rows, 34 NOT JUDGED.
    # So an all-NOT-JUDGED population is the NORMAL state of a healthy box, and reporting it
    # as NOT RUN would mean the leg can never say "I read 34 jobs and none is stuck" -- it
    # would speak only once something had already gone wrong, and a detector that is silent
    # exactly when healthy is a detector nobody reads. The line that separates the two is
    # PLACED, not judged: a row whose instant was READ and placed (in the future, or at a
    # slot that was dispatched) was measured; a row whose instant could not be placed was not.
    placed = examined - counts.get(CADENCE_SLOT_UNREADABLE, 0)
    if placed == 0:
        # NOTHING WAS PLACED. Every row was UNREADABLE, so the leg examined a population and
        # could place none of it -- a verdict over that is not a verdict (skill section 8).
        return {
            "name": "cadence-slot",
            "status": "NOT RUN",
            "problems": [],
            "excused": [],
            "coverage": {
                **coverage,
                "judged": judged,
                "reason": (
                    f"none of the {examined} enabled row(s) could be PLACED: "
                    f"{counts.get(CADENCE_SLOT_UNREADABLE, 0)} carried no readable "
                    f"next_run_at -- nothing was served and nothing was missed, which is NOT "
                    f"the same as clean"
                ),
            },
        }

    return {
        "name": "cadence-slot",
        "status": "ASSERTED",
        "problems": problems,
        "excused": [],
        # `judged` may be 0 here, and that zero is a MEASUREMENT rather than a silence: it
        # says no enabled row was past its own scheduled slot at `read_instant`. The counts
        # travel beside it so a reader can see the population was read and where it landed.
        "coverage": {**coverage, "judged": judged},
    }

def render_cadence_slot(coverage: dict) -> list[str]:
    """The leg's own lines: the population, the DERIVATION per job, then each finding.

    THE DERIVATION IS PRINTED, PER JOB (#543, ruling n=4087): the grace this leg used, the
    basis that produced it, the sample it rests on and the p95 behind it. A tolerance a
    reader cannot see is a tolerance they cannot audit, and before this unit the leg printed
    neither the grace nor anything it was derived from -- the verdict simply appeared.

    THE RETIREMENT IS PRINTED TOO. `HELD` is named as GONE with its reason, rather than left
    as a bucket that is absent, because an absent bucket and a bucket that cannot fire read
    identically and the second one is the defect.

    ONLY THE ACTING VERDICTS ARE NAMED PER ROW -- MISSED and UNREADABLE -- while the grace
    table above names every job that reached a slot. On the live box 2026-10-22, 34 of 34
    enabled rows were NOT JUDGED (their next slot has not arrived), so naming those one by
    one would bury the one row that missed under thirty-four lines of healthy state.
    """
    counts = coverage.get("counts") or {}
    lines = [
        f"  examined {coverage.get('examined', 0)} {coverage.get('unit', 'row(s)')} "
        f"(read at {coverage.get('read_instant') or 'unstated'}): "
        + ", ".join(f"{verdict} {counts.get(verdict, 0)}" for verdict in CADENCE_SLOT_VERDICTS)
    ]
    judged = coverage.get("judged")
    if judged is not None:
        lines.append(f"  judged (slot arrived and decided): {judged}")
    if not judged and coverage.get("examined"):
        lines.append(
            "  nothing overdue: no enabled row is past its own scheduled slot at this "
            "instant, so no slot has ARRIVED to be judged"
        )
    graces = coverage.get("graces") or []
    if graces:
        lines.append(
            f"  grace DERIVED per job from its own cron_job_runs lateness "
            f"(p{int(CADENCE_GRACE_PERCENTILE * 100)} over the last "
            f"{CADENCE_GRACE_WINDOW} runs, clamped to {CADENCE_GRACE_FLOOR_SECS:.0f}s floor "
            f"/ {CADENCE_GRACE_CAP_SECS:.0f}s cap / "
            f"{CADENCE_GRACE_PERIOD_FRACTION:.0%} of period): {len(graces)} job(s)"
        )
        for entry in sorted(graces, key=lambda item: str(item.get("name"))):
            grace = entry.get("grace_secs")
            shown = "UNDERTAKABLE" if grace is None else f"{grace:.0f}s"
            period = entry.get("period_secs")
            lines.append(
                f"    `{entry.get('name')}` grace {shown} "
                f"[{entry.get('basis')}] sample {entry.get('sample')} "
                f"p95 {entry.get('p95') if entry.get('p95') is not None else 'n/a'} "
                f"period {f'{period:.0f}s' if period else 'n/a'}"
                + (" PERIOD-CLAMPED" if entry.get("period_bound_binds") else "")
                + f" -- {entry.get('reason')}"
            )
    if coverage.get("grace_underivable_rows"):
        lines.append(
            f"  grace UNDERTAKABLE for {coverage['grace_underivable_rows']} of "
            f"{coverage.get('examined', 0)} row(s) (named in the table above): their slots "
            f"are NOT JUDGED rather than judged against an invented tolerance"
        )
    if coverage.get("grace_underivable"):
        lines.append(
            f"  grace UNDERTAKABLE for {coverage['grace_underivable']} row(s) whose slot "
            f"arrived unserved: those rows are NOT JUDGED and are named below -- a slot "
            f"judged against an invented tolerance is the defect this leg removes"
        )
    for record in coverage.get("findings") or []:
        if record.get("verdict") not in (CADENCE_SLOT_MISSED, CADENCE_SLOT_UNREADABLE) \
                and not record.get("grace_underivable"):
            continue
        lines.append(
            f"  {record['verdict']}: `{record['name']}` [{record['id']}] ({record['home']}, "
            f"zone {record['timezone']}) {record['schedule']} -- {record['reason']}"
        )
    for entry in coverage.get("retired") or []:
        lines.append(f"  RETIRED verdict `{entry['verdict']}`: {entry['reason']}")
    unreached = coverage.get("unreached") or []
    if unreached:
        lines.append(f"  homes NOT read: {'; '.join(unreached)}")
    lines.append(f"  bound: {coverage.get('bound', 'unstated')}")
    return lines

def duty_residual_for(job: dict, stem: str, *, fires: list[dict], ledger_rows: list[dict],
                      predicate=None, margin_for=None, parse=None) -> dict:
    """The forward window for ONE job, DERIVED from that job's own measured max (#449).

    THE MEASUREMENT. Each of the job's own fires opens a round (`receipt_round`), and the
    latency is the gap from the fire to the NEWEST ledger row for that round which
    DECLARES a duty (`receipt_subject_matches` + the shared field predicate). That pairing
    is the predicate n=1518 used, and it is stated here because a rate without its
    population is unreadable: `measured_rounds` travels in the returned record, so a
    residual resting on one observation is visible as one.

    THE FORM. `residual = margin_for(measured_max) * measured_max`, with `margin_for` READ
    from `tools/gate_budget.py` — the same law the gate-budget manifest derives its
    per-gate budgets with, so this instrument and that one cannot drift into two margins.
    The returned record carries `margin_x` and `measured_max_secs` beside the product, so
    the arithmetic is checkable rather than asserted.

    THE DEFAULT. A job with no measurable round (never fired, never receipted, or a runs
    table this reader cannot date) has NO measured max to derive from, and gets
    `DUTY_RESIDUAL_DEFAULT_SECS` with `basis="default"` and the stated reason. The two
    error directions are not equal — a short window judges a round the leg cannot yet
    clear (a false MISSING, which costs one look), while a long one is SILENT (#160) — so
    the default errs SHORT, and it is PRINTED, never applied invisibly. A max measured as
    NON-POSITIVE takes this same path (#500): `margin_for` divides by it, and this runner
    builds its legs in one list with no try/except, so raising here would take the whole
    round down. The guard is at this CALLER, never in `margin_for`.

    THE CADENCE IS REPORTED, NEVER ENFORCED. `cadence_secs` is the median gap between this
    job's own fires, and `over_cadence` is true when the derived residual reaches it. Such
    a residual cannot discriminate (n=1518 FINDING 3) — it outlives the next fire — and
    the honest output is the number AND that statement, never a clamp that hides it.
    """
    if predicate is None:
        predicate = field_predicate_readers()
    if parse is None:
        parse = reader_parse_ts
    if margin_for is None:
        margin_for = gate_budget_module().margin_for

    instants = duty_fire_instants(job, fires, parse)
    latencies: list[float] = []
    for instant in instants:
        round_date = receipt_round(instant.isoformat())
        if round_date is None:
            continue
        candidates = [
            r for r in ledger_rows
            if receipt_subject_matches(str(r.get("subject") or ""), stem, round_date)
            and predicate.declared_duty(str(r.get("detail") or ""))
        ]
        if not candidates:
            continue
        newest = max(candidates, key=lambda r: str(r.get("ts") or ""))
        try:
            receipt_instant = parse(str(newest.get("ts") or ""))
        except (ValueError, TypeError):
            continue
        latency = (receipt_instant - instant).total_seconds()
        # A NEGATIVE latency is a clock artefact, not a fast duty: the receipt cannot
        # precede the fire that opened its round. Dropped rather than clamped to zero,
        # because a zero would enter the max as a real observation.
        if latency < 0:
            continue
        latencies.append(latency)

    measured_max = max(latencies) if latencies else None
    # A NON-POSITIVE max is not a measurable round (#500), and it takes the SAME default
    # path as an absent one rather than reaching `margin_for`, which DIVIDES by its
    # argument. Guarded at the CALLER, never in `margin_for`: that predicate is shared law
    # with its own probes pinning the division.
    if measured_max is None or measured_max <= 0:
        residual = float(DUTY_RESIDUAL_DEFAULT_SECS)
        margin = None
        basis = "default"
        basis_text = (
            DUTY_RESIDUAL_DEFAULT_BASIS if measured_max is None else DUTY_RESIDUAL_ZERO_BASIS
        )
    else:
        margin = margin_for(measured_max)
        residual = margin * measured_max
        basis = "derived"
        basis_text = DUTY_RESIDUAL_FORM

    cadence: float | None = None
    if len(instants) >= 2:
        gaps = [(b - a).total_seconds() for a, b in zip(instants, instants[1:])]
        gaps = [g for g in gaps if g > 0]
        if gaps:
            cadence = statistics.median(gaps)

    return {
        "name": str(job.get("name") or "(unnamed row)"),
        "id": str(job.get("id") or "unstated"),
        "stem": stem,
        "basis": basis,
        "basis_text": basis_text,
        "residual_secs": residual,
        "margin_x": margin,
        "measured_max_secs": measured_max,
        "measured_rounds": len(latencies),
        "fires_read": len(instants),
        "cadence_secs": cadence,
        "over_cadence": cadence is not None and residual >= cadence,
    }

def dispatch_delivery_scope(repo: Path = REPO) -> tuple[dt.datetime | None, str, str]:
    """The bound this leg judges against, as `(instant, text, refusal)`.

    Read through the ONE boundary reader (`tests/ledger_boundary.py`), so this leg and the
    boundary-reading gates cannot disagree about what this factory declared — one field,
    one predicate (SKILL.md section 11).

    THE BOUND EXISTS BECAUSE THE HISTORICAL POPULATION IS LEGITIMATELY LARGE. Measured on
    this ledger at the mechanism's landing: 430 dispatch rows, and the delivery verdict is
    a NEW field no historical row could carry. Judging all of them against a rule that did
    not exist when they were written is exactly the permanent-red behaviour #334 exists to
    stop, and the ruling forbids backfilling them. So rows BEFORE the declared boundary are
    COUNTED and PRINTED, never judged; rows at or after it are judged.

    The reader's own policy is absent SKIPS / malformed FAILS; this leg maps BOTH onto a
    REFUSAL, for the reason the duty-receipt leg states: for a gate an absent declaration
    is a legitimate state, but for a leg that would otherwise judge EVERY instance it is
    not, so a tree that declares nothing is TOLD so rather than shown a clean run or an
    unbounded one.
    """
    try:
        reader = boundary_reader()
    except Exception as exc:  # noqa: BLE001 — any load failure is the same refusal
        return None, "", (
            f"the boundary reader cannot be loaded from {LEDGER_BOUNDARY} ({exc}) — "
            f"REFUSED: without it `{DELIVERY_BOUNDARY_KEY}` cannot be read, and a leg that "
            f"judges every dispatch against a bound it could not read is the permanent-red "
            f"behaviour #334 exists to stop"
        )
    try:
        instant, text = reader.declared_boundary(repo, DELIVERY_BOUNDARY_KEY)
    except reader.SkipGate as exc:
        return None, "", (
            f"`{DELIVERY_BOUNDARY_KEY}` is UNDECLARED in this tree ({exc}) — REFUSED: a "
            f"dispatch row written before the delivery-verdict mechanism could not have "
            f"carried a verdict, and this tree has not declared when that mechanism landed, "
            f"so no row is judged rather than every row being judged unbounded"
        )
    except reader.GateError as exc:
        return None, "", (
            f"`{DELIVERY_BOUNDARY_KEY}` is declared in this tree but cannot be read: "
            f"{'; '.join(str(p) for p in exc.problems)} — REFUSED: a malformed bound is a "
            f"DEFECT, never a licence to judge unbounded"
        )
    return instant, text, ""

def subject_token_re(subject: str) -> "re.Pattern[str] | None":
    """The compiled token predicate for `subject`, or None when the subject is empty.

    ONE home for the boundary discipline (#49, #425): the match, the locator a verdict prints
    and the header/body split all read the SAME pattern, so no caller can build a wider token
    than the one that produced the verdict.
    """
    s = str(subject or "").strip()
    if not s:
        return None
    if len(s) > 1 and s[0] == "#" and s[1:].isdigit():
        return re.compile(rf"(?<![0-9A-Za-z])#?{re.escape(s[1:])}(?![0-9A-Za-z])")
    return re.compile(re.escape(s))

def delivery_subject_matches(text: str, subject: str) -> bool:
    """True when `text` carries `subject` in a form NO NARROWER than the artifact (#49).

    A delivered notify is free prose that names the routed unit however its sender wrote
    it: the bare number (`77`), the hash-prefixed form (`#77`), or a descriptive stem
    (`wave-2026-10-05`). The ruling's constraint is stated in terms because the first
    census got it wrong and the error was SILENT: it searched `#77` where the artifact
    carried `77`, and the confident zero that returned read as good news — worse than no
    leg at all. So the match accepts every form.

    For a work unit the digits are matched with a NON-ALPHANUMERIC boundary on both
    sides, so `77` never matches inside `177`, `770`, a commit sha (`423f233`) or any
    other longer identifier (`x423y`) — a digit-only guard let the last two through and
    matched a `#423` subject against prose that named a different artifact (#425). A
    substring test would make the token WIDER than the artifact, which is the opposite
    error and just as silent. For a descriptive stem the whole stem is required.

    WHAT THIS ANSWERS, AND WHAT IT DOES NOT (#433). It answers "does this text carry the
    token"; it says NOTHING about WHERE. A delivery NAMES its subject in its header, and a
    message that merely discusses the subject carries it in the body — so this predicate is
    applied to the delivery's HEADER to decide corroboration and to the WHOLE text only to
    count a MENTION. Callers that need the distinction call `delivery_header` first.
    """
    pattern = subject_token_re(subject)
    if pattern is None or not text:
        return False
    return pattern.search(str(text)) is not None

def subject_offset(text: str, subject: str) -> tuple[int, int]:
    """(character offset, 1-based line) of the FIRST token occurrence, else (-1, -1).

    The locator a MENTION verdict prints, built from the SAME token as the match that found it
    (#433): a locator computed from a wider token would point the reader at an occurrence other
    than the one that was judged, which is the #425 error wearing a diagnostic's clothes.
    """
    pattern = subject_token_re(subject)
    if pattern is None:
        return (-1, -1)
    body = str(text or "")
    found = pattern.search(body)
    if found is None:
        return (-1, -1)
    return (found.start(), body.count("\n", 0, found.start()) + 1)

def delivery_header(text: str, *, lines: int = DELIVERY_HEADER_LINES) -> str:
    """The delivery's HEADER: its opening `lines` NON-BLANK line(s), envelope prefixes skipped.

    A delivered notify DECLARES its subject here — `TRIAGE DISPATCH — #428`, `[factory dispatch]
    #432 — WORK ITEM` — and the harness's own envelope (`[session-notify from=<uuid>]`,
    `📨 notify from <short-id>:`) is not part of what the sender wrote, so the DECLARED envelope
    prefixes above are skipped rather than counted as a header line. The scope is ONE line by
    declaration (`DELIVERY_HEADER_LINES`), measured from the #433 specimen's discriminator: the
    genuine delivery carried its subject at offset 78 and the mention that also cleared the row
    at offset 868, inside a queue list.

    WHY THE SCOPE IS NOT THE WHOLE TEXT (#433). A dispatch row is cleared when its target holds
    a delivery CARRYING THE SUBJECT — but a lane's store is full of messages that MENTION the
    subject: compaction summaries quoting the task list, rulings quoting the row under
    discussion, return legs listing what is queued. Measured 2026-10-07T18:05Z on the `#432`
    dispatch row's own target: 49 deliveries carried `#432`, of which 2 named it in a header and
    the other 47 only in a body. A whole-body match therefore clears a row whose brief was never
    routed — the false-CLEAN twin of the false absence #432 fixed.
    """
    kept: list[str] = []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if any(line.startswith(prefix) for prefix in NOTIFY_DELIVERY_HEADERS):
            continue
        kept.append(line)
        if len(kept) >= max(1, int(lines)):
            break
    return "\n".join(kept)

def box_deliveries(root: Path | None = None) -> tuple[list[dict], list[str], list[str]]:
    """(deliveries, homes_read, unreached) for every delivered notify on the box.

    TWO SURFACES, because a delivery exists in one of two states and both are receipts: a
    notify that LANDED is a `messages` row the harness stamped with ONE OF the header forms
    declared in `NOTIFY_DELIVERY_HEADERS` (`[session-notify from=<uuid>]` or
    `📨 notify from <short-id>:`), and a notify still ACCEPTED-but-undrained is a
    `notify_queue` row. Reading only the first would report a legitimate deferral as a
    phantom dispatch — the opposite error to the one this leg exists to catch.

    Read IN PLACE through a `mode=ro` URI, for the reason `box_cron_rows` states: copying a
    live WAL-mode database yields stale state and leaks disk. A home that could not be read
    is RETURNED in `unreached`, never dropped — a home that could not be read is not a home
    with nothing in it, and the two must never render the same.
    """
    registry = load_module("oc_registry", REGISTRY)
    dbs, unreached = registry.opencrabs_home_dbs(root)
    deliveries: list[dict] = []
    homes_read: list[str] = []
    for db in dbs:
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        except sqlite3.Error as exc:
            unreached.append(f"{db.parent.name}: {exc}")
            continue
        try:
            # AN OR OVER THE DECLARED TUPLE, never a single form (#426): the harness writes
            # both, and matching one read a drained notify as a phantom dispatch.
            landed = list(conn.execute(
                "select session_id, coalesce(content,''), created_at from messages "
                "where role = 'user' and ("
                + " or ".join("content like ?" for _ in NOTIFY_DELIVERY_HEADERS)
                + ")",
                tuple(f"%{header}%" for header in NOTIFY_DELIVERY_HEADERS),
            ))
            queued = list(conn.execute(
                "select session_id, coalesce(display_text,'') || ' ' || "
                "coalesce(context_text,''), created_at from notify_queue"
            ))
        except sqlite3.Error as exc:
            unreached.append(f"{db.parent.name}: {exc}")
            continue
        finally:
            conn.close()
        for session, text, created in landed:
            deliveries.append({
                "home": db.parent.name, "session": str(session or ""),
                "epoch": int(created or 0), "state": "landed", "text": str(text or ""),
            })
        for session, text, created in queued:
            deliveries.append({
                "home": db.parent.name, "session": str(session or ""),
                "epoch": int(created or 0), "state": "queued", "text": str(text or ""),
            })
        homes_read.append(db.parent.name)
    return deliveries, homes_read, unreached

def declared_dispatch_instant(row: dict) -> tuple[dt.datetime | None, str]:
    """The instant a dispatch row's OWN detail declares, as `(instant, form)`, else `(None, "")`.

    The row's `ts` is a WRITE instant (`tools/ledger.py::now_iso()` at append), so a batched
    ledger write stamps the row AFTER the dispatch it records and the window's backward bound
    then lands after a genuine delivery (#432, measured: row `n=2787`, `ts 12:26:04Z`, notify
    landed `12:11:28Z`, detail declares `resolved_at 2026-10-07T12:11:46Z`). A declared instant
    is the row's own statement of WHEN it dispatched, so it beats the write stamp.

    ONLY A NAMED FORM COUNTS. The detail is free prose, and 146 of this ledger's 458 dispatch
    rows carry SOME ISO instant in it -- a window, a neighbour's stamp, a read instant. Matching
    a bare ISO string would anchor windows on whatever instant a row happened to quote, so each
    form pairs a TOKEN with its value. An unparseable value declares nothing and raises nothing:
    a malformed declaration is not a licence to judge unbounded, it is simply no declaration.

    EARLIER WINS AT THE CALL SITE. The caller takes `min(ts, declared)`, so a detail naming an
    instant AFTER the write stamp cannot pull the window forward over a delivery that landed.
    """
    detail = str(row.get("detail") or "")
    if not detail:
        return None, ""
    for form, pattern in DISPATCH_DECLARED_INSTANT_FORMS:
        match = pattern.search(detail)
        if not match:
            continue
        try:
            return reader_parse_ts(match.group(1)), form
        except (ValueError, TypeError):
            return None, ""
    return None, ""

def subject_issue_number(subject: str) -> int | None:
    """The board number a dispatch row's subject NAMES, or None (#538).

    A NUMERIC SUBJECT IS THE WHOLE POPULATION THIS CAN RESOLVE, and the narrowness is
    deliberate: `#538` is a board item, `wave0-reply-sweep` is a campaign slug, and reading
    a slug as if it were an item would scope rows on a guess. A subject this cannot resolve
    is JUDGED exactly as before, so the narrowing can only ever move rows OUT of the
    problem population on an explicit board read -- never on an inference about the name.
    """
    match = re.fullmatch(r"#(\d+)", str(subject or "").strip())
    return int(match.group(1)) if match else None

def closed_board_numbers(issues: list[dict] | None) -> set[int]:
    """The board items a dispatch row for which is HISTORY, not a debt (#538)."""
    numbers: set[int] = set()
    for issue in issues or []:
        if str(issue.get("state", "")).strip().lower() != "closed":
            continue
        try:
            numbers.add(int(issue.get("number")))
        except (TypeError, ValueError):
            continue
    return numbers

def dispatch_delivery_leg(
    rows: list[dict],
    *,
    read_at: str = "",
    bound: tuple | None = None,
    deliveries_fn=None,
    issues: list[dict] | None = None,
) -> dict:
    """The dispatch-delivery leg: did each dispatch row's routing actually go OUT?

    SHAPE (3), ruled at ledger `n=1893`: a PRINTED LEG of the standing patrol, not a lane's
    ad-hoc census. It DETECTS; it does not prevent — `tools/ledger.py`'s write-path refusal
    is the preventing half, and the ruling is explicit that the field's PRESENCE proves a
    verdict was RECORDED, never that it was TRUE. A reader that takes the token as proof of
    delivery has re-derived the very error this item is about, so this leg reads the TARGET's
    own message history instead.

    FAIL OPEN, in the ruling's own words: an unreadable session store exits with NO VERDICT
    rather than reporting clean. Three surfaces can fail that way and each is distinguished:
    a refused bound (the tree declared nothing, or declared something unreadable), a store
    that could not be reached at all, and a store reached only in part. The third JUDGES
    what it read and PRINTS the homes it could not, so a partial read is never a silent one.

    A ZERO MUST BE DISTINGUISHABLE FROM A BLIND LEG (acceptance criterion 3), so the
    examined dispatch-row count is always printed: `examined 33, 0 problems` is never the
    same output as `examined 0`.

    TWO VERDICTS, NOT ONE (#432). "No delivery exists" and "a delivery exists but outside the
    window this leg chose" are different facts, and the leg carried ONE verdict for both --
    reporting the second as "records no delivery", which is a FALSE ABSENCE that sends a
    reader off to re-dispatch an item the target already holds. So a match is taken WITHOUT
    the window first: a target holding the brief somewhere is a WINDOW MISMATCH naming the
    delivery's own instant, and only a store holding no match at all reads as the absence.

    AND NEITHER OF THOSE IS A PROBLEM (#538, ruled at ledger n=4029). Two of this leg's own
    verdicts contradicted its own reading in the same line: a WINDOW MISMATCH is a delivery
    that EXISTS -- the line says "do not re-dispatch" -- and a dispatch row whose subject is
    a CLOSED board item is a record of history, not a debt anyone owes. Both were counted
    under `problems`, and they were 74 of the leg's 96 on the 2026-10-21 read, so the count
    could only rise as the factory closed more work: a verdict whose number grows with the
    factory's own success is not measuring debt. The window mismatch now reads as an EXCUSAL
    carrying its instant and its window, and closed-subject rows are scoped OUT of the
    population into `judged_closed_subject`, printed once as a figure. The campaign-slug
    rows stay reported -- those are #443's, not this one's -- and the absence verdict is
    untouched. This is a DETECTOR's repair: no write-path change, no new gate.
    """
    window_before = dt.timedelta(seconds=DELIVERY_WINDOW_BEFORE_SECS)
    window_after = dt.timedelta(seconds=DELIVERY_WINDOW_AFTER_SECS)
    match_horizon = dt.timedelta(seconds=DELIVERY_MATCH_HORIZON_SECS)
    # THE BOARD READ IS WHAT MAKES THE SCOPING POSSIBLE, AND ITS ABSENCE IS STATED (#538).
    # A probe that injects no board gets no scoping, so its rows are judged exactly as
    # before: the narrowing can only come from a board that actually said CLOSED, and a
    # leg that scoped on a guess would be inventing the very debt it is meant to measure.
    closed_numbers = closed_board_numbers(issues)
    coverage = {
        "bound_key": DELIVERY_BOUNDARY_KEY,
        "bound": (bound[1] if bound else "") or "",
        "window_basis": DELIVERY_WINDOW_BASIS,
        "window_before_secs": DELIVERY_WINDOW_BEFORE_SECS,
        "window_after_secs": DELIVERY_WINDOW_AFTER_SECS,
        "match_horizon_secs": DELIVERY_MATCH_HORIZON_SECS,
        "dispatch_rows_read": sum(1 for r in rows if r.get("event") == "dispatch"),
        "board_read": issues is not None,
        "board_items_read": len(issues or []),
        "board_closed_items": len(closed_numbers),
        "read_at": read_at,
    }
    if bound is None or bound[0] is None:
        reason = (bound[2] if bound else "") or "no bound was supplied to this leg"
        coverage.update({
            "dispatch_rows_examined": 0, "dispatch_rows_pre_boundary": 0,
            "dispatch_rows_undated": 0, "dispatch_rows_not_judged": 0,
            "dispatch_rows_declared_anchor": 0,
            "subject_matches_anywhere": 0, "subject_matches_within_horizon": 0,
            "dispatch_rows_corroborated": 0,
            "subject_mentions_body_only": 0, "subject_mentions_body_only_within_horizon": 0,
            "deliveries_read": None, "homes_read": None, "homes_unreached": [],
            "store_read": False,
            "store_not_read_reason": reason,
        })
        return {"name": "dispatch-delivery", "status": "NOT RUN", "reason": reason,
                "problems": [], "excused": [], "coverage": coverage}
    boundary: dt.datetime = bound[0]
    # THE POPULATION IS RESOLVED BEFORE THE STORE IS TOUCHED, and the order is load-bearing
    # in BOTH directions (measured 2026-10-06 while landing this leg). The read is O(the
    # whole box's message history) -- expensive enough that a leg scanning it BEFORE knowing
    # whether it had anything to corroborate pays that cost to judge zero rows -- so every
    # probe that drove `main()` paid it again: the
    # runner's own gate went from well inside its budget to a TIMEOUT the moment this leg's
    # boundary was declared. Resolving first is also the more honest shape: `deliveries_read`
    # then describes a read the leg actually NEEDED, never a number collected in case it was.
    problems: list[str] = []
    examined = 0
    pre_boundary = 0
    undated = 0
    not_judged = 0
    declared_anchor = 0
    matches_anywhere = 0
    matches_near = 0
    mentions_anywhere = 0
    mentions_near = 0
    corroborated = 0
    closed_subjects: list[str] = []
    outside_window: list[str] = []
    to_judge: list[tuple[dict, dt.datetime, dt.datetime, dt.datetime, str, str]] = []
    for row in rows:
        if row.get("event") != "dispatch":
            continue
        try:
            ts = reader_parse_ts(str(row.get("ts") or ""))
        except (ValueError, TypeError):
            # An instant this leg cannot read is REPORTED as undated, never silently
            # dropped: a row that cannot be placed against the bound is one the leg did
            # not judge, and a population that quietly shrinks by it would read as clean.
            undated += 1
            continue
        if ts < boundary:
            pre_boundary += 1
            continue
        # THE ROW'S ROUTED TARGET IS ITS TYPED `session` REF (#425 clause 1). The leg
        # corroborates a dispatch against the TARGET's own message history, so a row that
        # names no target names no history to read: it is NOT JUDGED -- counted and printed
        # beside the verdict, never CLEAN and never RED, and nothing is backfilled onto it.
        # `tools/ledger.py` refuses such a row at the write path from now on; this bucket is
        # for the HISTORY written before that refusal, which is immutable once pushed.
        session_ref = next(
            (str(value) for ref in (row.get("refs") or [])
             for kind, value in ref.items() if kind == "session"), ""
        )
        if not session_ref:
            not_judged += 1
            continue
        # THE ANCHOR IS THE EARLIER OF THE ROW'S WRITE STAMP AND THE INSTANT IT DECLARES
        # (#432). `ts` is when the ROW was written, which is an upper bound on when the
        # dispatch happened -- a batched write stamps it late, and a window built from it then
        # opens AFTER a genuine delivery. A declared instant is the row's own statement of the
        # dispatch, so the earlier of the two is the honest backward bound; it can only widen
        # the search, never narrow it, so it cannot manufacture a clean verdict.
        declared, declared_form = declared_dispatch_instant(row)
        # EARLIER WINS, and a declaration LATER than the write stamp is not used at all: it
        # would pull the backward bound forward, which is the false-absence direction. The
        # count is of rows whose anchor actually CAME from the declaration, never of rows that
        # merely carry one -- a number that counted presence would print an anchor claim for a
        # window it did not build.
        # AND THE LAG IS BOUNDED (#476): a declaration far behind the write stamp is not this
        # row's dispatch instant but a token the row QUOTES as evidence about another artifact,
        # so it falls back to `ts` exactly as an unparsed form does. Both arms are in
        # `DECLARED_INSTANT_MAX_LAG_SECS` above.
        uses_declaration = (
            declared is not None
            and declared < ts
            and (ts - declared).total_seconds() <= DECLARED_INSTANT_MAX_LAG_SECS
        )
        anchor = declared if uses_declaration else ts
        if uses_declaration:
            declared_anchor += 1
        basis = (
            f"anchored on the row's declared `{declared_form}` "
            f"{declared.strftime('%Y-%m-%dT%H:%M:%SZ')} (earlier than its write stamp "
            f"{ts.strftime('%Y-%m-%dT%H:%M:%SZ')}, #432)"
            if uses_declaration else
            f"anchored on the row's write stamp {ts.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        )
        # A DISPATCH ROW FOR A FINISHED UNIT IS HISTORY, NOT A DEBT (#538, ruling n=4029).
        # The subject is resolved against the BOARD, never inferred from its shape: only a
        # numeric subject naming an item the board reports CLOSED is scoped out, and the
        # count is printed as a figure rather than as N excused lines -- 57 of the leg's 96
        # on the 2026-10-21 read, which is exactly the volume that made the verdict
        # unreadable. Rows whose subject is a campaign slug resolve to no item and are
        # JUDGED as before, so #443's population stays visible here.
        subject_text = str(row.get("subject") or "").strip()
        if closed_numbers and subject_issue_number(subject_text) in closed_numbers:
            closed_subjects.append(subject_text)
            continue
        examined += 1
        to_judge.append(
            (row, anchor, anchor - window_before, anchor + window_after, session_ref, basis)
        )
    coverage.update({
        "dispatch_rows_examined": examined,
        "dispatch_rows_pre_boundary": pre_boundary,
        "dispatch_rows_undated": undated,
        "dispatch_rows_not_judged": not_judged,
        "dispatch_rows_declared_anchor": declared_anchor,
        "dispatch_rows_closed_subject": len(closed_subjects),
        "judged_closed_subject": list(closed_subjects),
    })
    if not to_judge:
        # THE STORE IS NOT READ, AND THAT IS SAID. There is no post-boundary dispatch row to
        # corroborate, so no delivery is sought -- and the render must not let `deliveries
        # read: 0` stand for BOTH "the store held none" and "the store was never opened".
        # Those are different facts and a reader who cannot tell them apart is reading the
        # confident zero this leg exists to refuse.
        #
        # TWO WAYS TO HAVE NOTHING TO JUDGE, and they are not the same fact (#425 clause 1):
        # no post-boundary row at all, or post-boundary rows that name no target. The second
        # is a POPULATION the leg declined to judge -- `examined: 0` over it would read as a
        # clean sweep of rows it never looked at -- so the reason says which one it is.
        if not_judged:
            reason = (
                f"{not_judged} dispatch row(s) at or after the bound "
                f"`{DELIVERY_BOUNDARY_KEY}` ({coverage['bound']}) carry no typed "
                f"`session` ref, so none names a routed target to corroborate against "
                f"(#425) -- NOT JUDGED, never a clean zero"
            )
        elif closed_subjects:
            # THE SCOPING IS NOT SILENT (#538). A population emptied by the board read is a
            # MEASURED zero -- every row it held was history -- and it must not read as the
            # "nothing to corroborate" shape, which is what an unread board produces.
            reason = (
                f"{len(closed_subjects)} dispatch row(s) at or after the bound "
                f"`{DELIVERY_BOUNDARY_KEY}` ({coverage['bound']}) name board items the "
                f"board reports CLOSED, so all of them are history and none is a debt "
                f"(#538) -- NOTHING OWED, never a clean sweep of rows this leg never read"
            )
        else:
            reason = (
                f"no dispatch row at or after the bound `{DELIVERY_BOUNDARY_KEY}` "
                f"({coverage['bound']}) to corroborate, so no delivery was sought"
            )
        coverage.update({
            "deliveries_read": None, "homes_read": None, "homes_unreached": [],
            "store_read": False,
            "store_not_read_reason": reason,
        })
        return {"name": "dispatch-delivery", "status": "ASSERTED", "reason": None,
                "problems": [], "excused": [], "coverage": coverage}
    deliveries, homes_read, unreached = (deliveries_fn or box_deliveries)()
    coverage.update({
        "store_read": True,
        "deliveries_read": len(deliveries),
        "homes_read": len(homes_read),
        "homes_read_names": homes_read,
        "homes_unreached": unreached,
        "deliveries_by_state": {
            state: sum(1 for d in deliveries if d["state"] == state)
            for state in ("landed", "queued")
        },
    })
    if not homes_read:
        # NOT ONE HOME COULD BE REACHED — the store is blind, so a clean verdict here would
        # be the "confident zero" the ruling names as worse than no leg.
        reason = (
            "no OpenCrabs home could be read, so no delivery could be sought — "
            + ("; ".join(unreached) if unreached else "no home database was found")
        )
        return {"name": "dispatch-delivery", "status": "NOT RUN", "reason": reason,
                "problems": [], "excused": [], "coverage": coverage}
    for row, anchor, lo, hi, session_ref, basis in to_judge:
        subject = str(row.get("subject") or "").strip()
        # A MATCH MUST BE TO THE ROW'S OWN TARGET (#425 clause 1). A notify carrying the
        # subject but addressed to a DIFFERENT lane is not corroboration of THIS dispatch --
        # the same subject is broadcast to several lanes, so a subject-only match would clear
        # a row whose actual target was never told. The row named its target; the delivery
        # must name the same one.
        #
        # THE MATCH IS TAKEN WITHOUT THE WINDOW FIRST (#432), because the leg must never
        # report ABSENCE from a window it chose itself. `matched` answers "does this target
        # hold this brief AT ALL"; only then is the window applied, and a match that falls
        # outside it is a WINDOW MISMATCH -- a delivery that exists -- never an absence.
        carrying = [
            d for d in deliveries
            if d.get("session") == session_ref
            and delivery_subject_matches(d["text"], subject)
        ]
        # AND THE MATCH MUST BE IN THE DELIVERY'S HEADER (#433). A delivery NAMES the unit it
        # routes -- `TRIAGE DISPATCH — #428`, `[factory dispatch] #432 — WORK ITEM` -- so the
        # token belongs in its opening line; a message that merely DISCUSSES the subject
        # carries it in the BODY, and a lane's store is full of those: compaction summaries
        # quoting the task list, rulings quoting the row under discussion, return legs listing
        # what is queued. Measured 2026-10-07T18:05Z on the `#432` dispatch row's own target:
        # 49 deliveries carried `#432` while only 2 named it in a header. A whole-text match clears a
        # row whose brief was never routed -- the false-CLEAN twin of the false absence #432
        # fixed, and the reason a body-only match is reported as a MENTION and never counted
        # as corroboration.
        matched = [d for d in carrying if delivery_subject_matches(delivery_header(d["text"]), subject)]
        mentions = [d for d in carrying if d not in matched]
        # A MATCH COUNTS AS A DELIVERY ONLY INSIDE THE HORIZON (#432). Beyond it a match is a
        # subject MENTION -- this box's `#432` target held 47 of them at the 2026-10-07T18:05Z
        # read, the oldest `2026-09-19T08:29:00Z`, 19 days back -- and reporting one as "a
        # delivery exists" would be the false-CLEAN twin of the false absence this item is
        # about. The unbounded count is kept and printed, so the horizon's effect is visible
        # rather than silent.
        plausible = [
            d for d in matched
            if anchor - match_horizon
            <= dt.datetime.fromtimestamp(d["epoch"], dt.timezone.utc)
            <= anchor + match_horizon
        ]
        # A BODY-ONLY MENTION IS HORIZON-BOUNDED FOR THE SAME REASON (#433): an 18-day-old
        # summary quoting the unit is not evidence that a briefing reached the target, and the
        # MENTION verdict must not be a second way to read one as a delivery.
        near_mentions = [
            d for d in mentions
            if anchor - match_horizon
            <= dt.datetime.fromtimestamp(d["epoch"], dt.timezone.utc)
            <= anchor + match_horizon
        ]
        matches_anywhere += len(carrying)
        matches_near += len(plausible)
        mentions_anywhere += len(mentions)
        mentions_near += len(near_mentions)
        if matched:
            corroborated += 1
        hits = [
            d for d in plausible
            if lo <= dt.datetime.fromtimestamp(d["epoch"], dt.timezone.utc) <= hi
        ]
        if hits:
            continue
        if plausible:
            # TWO CONDITIONS, TWO VERDICTS (#432), AND ONLY ONE OF THEM IS A PROBLEM (#538).
            # The specimen that produced this clause is row `n=2787` (`#428`): its window
            # opened `12:23:04Z`, its notify landed `12:11:28Z`, and the leg read "records no
            # delivery" for a delivery that woke the very lane that ruled the item -- sending
            # a reader off to re-dispatch an item the target already held. The reader is told
            # WHICH instant the delivery carries and which window judged it, so the mismatch
            # is a fact they can act on rather than a false absence they must disprove.
            #
            # BUT A DELIVERY THAT EXISTS IS NOT A DEBT, and this leg said both in one line:
            # the text ended "a DELIVERY EXISTS, so this is a WINDOW MISMATCH, never an
            # absence: do not re-dispatch on this line" while being counted under `problems`.
            # 57 of the leg's 96 on the 2026-10-21 read were this shape, and every one of
            # them is a unit that was delivered and then finished -- so the count grew with
            # the factory's own success. It is an EXCUSAL carrying the same instant and the
            # same window; the reader loses no fact and the verdict stops contradicting
            # itself.
            outside = min(plausible, key=lambda d: d["epoch"])
            at = dt.datetime.fromtimestamp(outside["epoch"], dt.timezone.utc)
            outside_window.append(
                f"n={row.get('n')} ({subject}) dispatched at {row.get('ts')} to session "
                f"{session_ref} carries a delivery OUTSIDE the window this leg judged: a "
                f"notify carrying `{subject}` addressed to that target landed "
                f"{at.strftime('%Y-%m-%dT%H:%M:%SZ')} ({outside['state']}), and the window "
                f"[{lo.strftime('%Y-%m-%dT%H:%M:%SZ')}, {hi.strftime('%Y-%m-%dT%H:%M:%SZ')}] "
                f"({basis}) does not contain it — a DELIVERY EXISTS, so this is a WINDOW "
                f"MISMATCH, never an absence: do not re-dispatch on this line — and not a "
                f"problem either (#538)"
            )
            continue
        if near_mentions:
            # A BODY-ONLY MATCH IS A MENTION, NOT A DELIVERY (#433). Reporting it as
            # corroboration would clear a row whose brief was never routed; reporting it as an
            # ABSENCE would be a lie in the other direction, because the text IS there and the
            # reader can see it. So the third verdict says exactly what was found and where --
            # the token in the BODY, never in the header a delivery declares its subject in --
            # and leaves the row's truth to a lane that can read the store itself.
            first = min(near_mentions, key=lambda d: d["epoch"])
            at = dt.datetime.fromtimestamp(first["epoch"], dt.timezone.utc)
            off, line = subject_offset(first["text"], subject)
            problems.append(
                f"n={row.get('n')} ({subject}) dispatched at {row.get('ts')} to session "
                f"{session_ref} is corroborated by NO delivery: {len(near_mentions)} message(s) "
                f"on that target MENTION `{subject}` inside their body within the "
                f"{int(match_horizon.total_seconds())} s horizon (earliest "
                f"{at.strftime('%Y-%m-%dT%H:%M:%SZ')}, {first['state']}, at offset {off} on "
                f"line {line} — never in a delivery header), and {mentions_anywhere} mention it "
                f"anywhere in the stores. A body mention is a MENTION, not a delivery: no "
                f"notify NAMING `{subject}` in its header reached that target inside the window "
                f"[{lo.strftime('%Y-%m-%dT%H:%M:%SZ')}, {hi.strftime('%Y-%m-%dT%H:%M:%SZ')}] "
                f"({basis}), so this row reads NEITHER corroborated NOR absent — a lane "
                f"discussing the unit is not a lane that was briefed"
            )
            continue
        problems.append(
            f"n={row.get('n')} ({subject}) dispatched at {row.get('ts')} to session "
            f"{session_ref} records no delivery: no inbound notify carrying `{subject}` "
            f"addressed to that target appears in ANY of the "
            f"{coverage.get('deliveries_read')} delivery(ies) read from the box's stores — "
            f"the window judged was "
            f"[{lo.strftime('%Y-%m-%dT%H:%M:%SZ')}, {hi.strftime('%Y-%m-%dT%H:%M:%SZ')}] "
            f"({basis}) — the row claims this lane was TOLD and nothing corroborates it"
        )
    # THE MATCH COUNTS ARE STORED AFTER THE LOOP, never before it: they are accumulated
    # inside it, and a coverage snapshot taken ahead of the loop would print `0 anywhere`
    # for a store that held forty-six -- a blind zero wearing the shape of a clean one.
    coverage.update({
        "subject_matches_anywhere": matches_anywhere,
        "subject_matches_within_horizon": matches_near,
        "dispatch_rows_corroborated": corroborated,
        "subject_mentions_body_only": mentions_anywhere,
        "subject_mentions_body_only_within_horizon": mentions_near,
        "delivered_outside_window": len(outside_window),
    })
    return {"name": "dispatch-delivery", "status": "ASSERTED", "reason": None,
            "problems": problems, "excused": outside_window, "coverage": coverage}

def duty_fallback_note(problems: list[str], fallback_from: str | None,
                       schedule_text: str = "") -> list[str]:
    """Append the PRIOR-round note to every problem of a fallback finding (#281).

    One exit path is not enough: `duty_round_finding` returns EARLY for a round with no
    receipt, which is exactly the finding a fallback produces most often, so the note is
    applied through this one function at BOTH returns. Measured while writing the probe:
    the first version appended it only at the end of the function, and the prior round's
    RED arrived with no statement of which round it was about — the finding read as a
    stale verdict on a round the reader could not place.

    `schedule_text` is the row's OWN scheduling record, carried because WHY a round was
    skipped is a property of the job's cadence against its derived residual (#449): a
    reader meeting "the prior round is the one judged" needs the schedule that produced
    it, and a row that records none says so rather than printing an empty clause.
    """
    if not fallback_from:
        return problems
    tail = f" (that job's declared schedule: {schedule_text})" if schedule_text else ""
    return [
        p + (
            f" [This is the PRIOR round: the newest round {fallback_from} is still in "
            f"flight and is NOT JUDGED, and a round this leg cannot judge must not hide "
            f"the one before it (#281){tail}]"
        )
        for p in problems
    ]

def duty_round_finding(*, name: str, job_id: str, stem: str, round_date: str, fired: str,
                       ledger_rows: list[dict], predicate,
                       fallback_from: str | None = None, schedule_text: str = "",
                       round_fires: list[str] | None = None,
                       residual_secs: float | None = None,
                       read_instant: dt.datetime | None = None) -> dict:
    """Judge ONE round of one job — the rows matching its subject, and what they DECLARE.

    Split out of the leg's loop for #281 (ruling n=2003) so a round can be judged from a
    WALK rather than from a single instant: the leg judges the newest round, and when that
    round is IN FLIGHT it judges the one the PREVIOUS fire woke through THIS function, so
    the prior round is judged by exactly the predicate the newest one is — never by a
    second, weaker path.

    `fallback_from` names the round this one is judged INSTEAD of, and it is CARRIED into
    the finding rather than implied: a reader meeting a finding about an older round must
    be told why the leg is not looking at the newest one, or the finding reads as a stale
    verdict.
    """
    matched = [r for r in ledger_rows
               if receipt_subject_matches(str(r.get("subject") or ""), stem, round_date)]
    # A row that declares NOTHING is not a receipt (#160). This is the false-clean fix: the
    # leg's first version accepted any subject match, so a DISPATCH record written before
    # the round completed certified it. The declaration is what makes a row a receipt, so
    # the filter is the predicate and not a formatting preference.
    receipts = [r for r in matched
                if predicate.declared_duty(str(r.get("detail") or ""))]
    finding = {
        "judged": {
            "name": name, "id": job_id, "stem": stem, "round": round_date,
            "fired": fired, "rows_matched": len(matched), "receipts": len(receipts),
        },
        "problems": [], "excused": [], "superseded": 0, "malformed": 0,
    }
    if fallback_from:
        finding["judged"]["fallback_from"] = fallback_from
    if not receipts:
        # A MATCHED ROW THAT CARRIES THE TOKEN WHERE THE READER CANNOT REACH IT (#281).
        # The row DECLARES nothing to the positional predicate while carrying the token in
        # its own voice, and that is a distinct state from a round that never declared: the
        # author wrote the declaration and the reader cannot reach it. Reporting it as a
        # bare "declares no `duty=`" hides the fix; reporting it as a missing duty blames a
        # lane that may well have completed. So it is NAMED, with the repair.
        #
        # THE PREDICATE IS THE SHARED OWN-VOICE READER, never a second discriminator
        # (`n=405` PART 5, `n=599`): a token inside a parenthetical aside is a CITATION of
        # another row's token, and only `field_predicate.own_voice_text` decides that. A row
        # that DISCUSSES a duty in its own voice is reported too, and the finding is a
        # POINTER ("make the token terminal") — true of the row whether it declared or
        # merely discussed, and never a verdict on what the round did.
        malformed = [r for r in matched
                     if predicate.mentions_duty(str(r.get("detail") or ""))]
        if malformed:
            named = "; ".join(f"n={r.get('n')} ({r.get('subject')})" for r in malformed)
            finding["malformed"] = len(malformed)
            finding["problems"].append(
                f"{name} (cron id {job_id}): the round {round_date} has NO duty receipt "
                f"this leg can READ — {len(matched)} row(s) match the round's subject and "
                f"{len(malformed)} of them carry `{predicate.DUTY_KEY}=` in the row's OWN "
                f"VOICE while DECLARING nothing: {named}. The declaration is REAL and the "
                f"reader cannot reach it, so this is a MALFORMED RECEIPT and never a missing "
                f"duty: the token sits outside the row's canonical terminal run. Make it "
                f"TERMINAL — the detail's last line must carry the "
                f"`{predicate.DUTY_KEY}=` trailer"
            )
        else:
            unmatched_note = (
                f" {len(matched)} row(s) match the round's subject and declare no "
                f"`{predicate.DUTY_KEY}=`, so none of them is a receipt."
                if matched else ""
            )
            finding["problems"].append(
                f"{name} (cron id {job_id}): the round {round_date} has NO duty receipt — "
                f"no ledger run row for {stem}-{round_date}* DECLARES a completion "
                f"(`{predicate.DUTY_KEY}=`).{unmatched_note} A cron run row records only that "
                f"the TRIGGER fired, so a green run here is a MISSING duty and not a clean one"
            )
        return {**finding, "problems": duty_fallback_note(
            finding["problems"], fallback_from, schedule_text)}
    # THE ROUND'S FIRES, EACH OWING A RECEIPT (#499, ruling n=3446). The round is a DAY and
    # a sub-daily job fires SEVERAL times inside it, so the `if not receipts` test above —
    # AT LEAST ONE — let a day carrying four fires and three receipts read exactly like a
    # day carrying one and one. `last_run_at` cannot show the difference either: it records
    # the NEWEST fire, so the earlier ones leave no trace in any field the leg read.
    #
    # The day prefix STAYS for DECLARATION (#159 is not reverted): a lane still writes one
    # receipt per round and the round-level predicates below are untouched. What is added is
    # JUDGEMENT, keyed on the FIRE: the receipts are bucketed by the token each fire owns
    # and the fires no receipt answers are NAMED with their own instants.
    #
    # THE FALSE-RED GUARD IS THE RESIDUAL (#146, #200/#449). A fire younger than the job's
    # own residual has a lane still working on it — the trigger fired and the work is IN
    # FLIGHT, which is the same window the round-level judgement already honours. Charging a
    # receipt for it would trade this leg's false CLEAN for a false RED, and the ruling
    # names that class explicitly. So `unanswered_fires` skips them.
    if round_fires:
        finding["judged"]["fires"] = len(round_fires)
        missing = unanswered_fires(
            round_fires, stem, round_date, receipts,
            residual_secs=residual_secs, read_instant=read_instant, parse=reader_parse_ts,
        )
        finding["judged"]["fires_unanswered"] = len(missing)
        if missing:
            named = "; ".join(missing)
            finding["problems"].append(
                f"{name} (cron id {job_id}): the round {round_date} FIRED "
                f"{len(round_fires)} time(s) and {len(missing)} of those fires left NO "
                f"receipt — {named}. {len(receipts)} receipt(s) match the round and none "
                f"carries the token for those fires, so the day is UNDER-RECEIPTED: the "
                f"job ran, its lane did not report, and a round judged on the newest fire "
                f"alone reads clean while the earlier one did nothing"
            )
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
                finding["problems"].append(
                    f"{name} (cron id {job_id}): the round {round_date} — receipt row "
                    f"n={n} declares {predicate.DUTY_KEY}={value}, outside the domain "
                    f"{'/'.join(predicate.DUTY_DOMAIN)}. An unrecognised value is an "
                    f"ERROR, never a silent pass"
                )
            elif receipt is not newest and value in DUTY_INCOMPLETE_VALUES:
                finding["superseded"] += 1
                finding["excused"].append(
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
            finding["problems"].append(
                f"{name} (cron id {job_id}): the round {round_date} did NOT complete — "
                f"its NEWEST receipt row n={newest.get('n')} declares "
                f"{predicate.DUTY_KEY}={value} at {newest.get('ts')}"
            )
    if fallback_from:
        # The reader must be told WHICH round this verdict is about and WHY it is not the
        # newest one. A finding about an older round with no such note reads as a stale
        # verdict, and a reader who cannot tell the two apart cannot act on either.
        finding["problems"] = duty_fallback_note(
            finding["problems"], fallback_from, schedule_text)
    return finding

def duty_receipt_leg(rows: list[dict], homes_read: list[str], unreached: list[str],
                     prefixes: list[str], ledger_rows: list[dict], *,
                     read_at: str = "", store: Path = FRAGMENT_STORE,
                     predicate=None, repo: Path = REPO, now=None,
                     fires: list[dict] | None = None, margin_for=None,
                     scope_fn=None, exemptions_fn=None) -> dict:
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
    # THE THREE BUCKETS (#424 items 1+2+3-clause-3, ordered at n=2723). A row declaring a
    # STEM is judged; a row declaring it OWES NONE is a declaration the leg READS and never
    # hunts; a row declaring NOTHING is NOT JUDGED. The third was always this leg's
    # behaviour and had no name; the second had no expression at all, so a
    # `receipt_subject: none` row was read as a STEM, hunted as `none-<round>*`, and reddened
    # every round -- the false MISSING measured at n=3228.
    declared: list[tuple[dict, str]] = []
    owes_none: list[dict] = []
    malformed: list[tuple[dict, str]] = []
    undeclared: list[dict] = []
    undeclared_exempt: list[tuple[dict, str]] = []
    # INJECTED like every other reader this leg takes (#487's shape): a probe drives its own
    # store rather than reading this factory's, so the pair of halves stays honest in a
    # member tree that has declared exemptions of its own.
    exemptions, exemption_problem = (exemptions_fn or receipt_declaration_exemptions)()
    for row in attributed:
        disposition, detail = declared_receipt_disposition(str(row.get("prompt") or ""))
        if disposition == "declares":
            declared.append((row, detail or ""))
        elif disposition == "owes_none":
            owes_none.append(row)
        elif disposition == "malformed":
            malformed.append((row, detail or ""))
        elif str(row.get("name") or "") in exemptions:
            undeclared_exempt.append((row, exemptions[str(row.get("name") or "")]))
        else:
            undeclared.append(row)

    problems: list[str] = []
    excused: list[str] = []
    if exemption_problem:
        problems.append(exemption_problem)
    # #506 HALF 1 -- A DECLARATION THE READER CANNOT PARSE IS A PROBLEM. The alternative is
    # what the box did for a whole round: a duty printed NOT JUDGED beside `problems: 0`,
    # which is indistinguishable from a clean round. The shape is NAMED so the author can
    # see which edit un-declared it.
    for row, shape in malformed:
        problems.append(
            f"{str(row.get('name') or '(unnamed row)')}: the prompt carries a "
            f"`receipt_subject` the canonical reader cannot parse ({shape}), so the duty is "
            f"NOT JUDGED -- a declaration that cannot be read is a PROBLEM, not silence (#506)"
        )
    # #506 HALF 2 -- NOT JUDGED IS A FINDING unless the factory DECLARED the job exempt. A
    # third state that reads as silence is how a duty sat unjudged with a clean problem
    # count; an exemption is visible debt, printed on every run like every other `excused:`.
    for row in undeclared:
        problems.append(
            f"{str(row.get('name') or '(unnamed row)')}: NOT JUDGED -- the prompt declares no "
            f"`receipt_subject:` line and the job is named in no declared exemption "
            f"(docs/duty-receipt-exemptions.json), so this leg cannot tell whether it owes a "
            f"receipt (#506)"
        )
    # #506 HALF 3 -- AN EXEMPTION THAT EXCUSES NOTHING IS VISIBLE DEBT (ruling n=3527
    # criterion 3). The store is the one lawful exit, and an exit naming a job that is not an
    # undeclared duty on this box has stopped describing reality: the job got a declaration,
    # or was renamed, or was retired -- and the row sits there looking like an active
    # exemption. A silent stale entry is how a store rots into a rubber stamp, so it is a
    # problem with the job NAMED rather than a pass nobody reads.
    # The population an exemption may lawfully name is BOTH halves: the rows the exemption
    # left unjudged AND the rows it excused. Taking only `undeclared` here would have called
    # every WORKING exemption stale -- the exempted rows are removed from `undeclared` above
    # by construction, so a store doing its job would have redded on every round. Measured
    # while writing this arm's own probe; the discriminating control is what caught it.
    excusable_names = {str(row.get("name") or "") for row in undeclared}
    excusable_names |= {str(row.get("name") or "") for row, _ in undeclared_exempt}
    stale_exemptions = sorted(job for job in exemptions if job not in excusable_names)
    for job in stale_exemptions:
        problems.append(
            f"declared exemption names {job!r}, which is NOT an undeclared duty on this box "
            f"(docs/duty-receipt-exemptions.json) -- an exemption that excuses nothing is "
            f"stale debt: remove the row, or it will keep reading as an active exit (#506)"
        )
    for row, why in undeclared_exempt:
        excused.append(
            f"{str(row.get('name') or '(unnamed row)')}: NOT JUDGED by DECLARED EXEMPTION "
            f"(docs/duty-receipt-exemptions.json) -- {why or 'no reason stated'}"
        )
    judged: list[dict] = []
    residuals: list[dict] = []
    rounds_superseded = 0
    rounds_excused_by_bound = 0
    rounds_excused_by_residual = 0
    rounds_over_cadence = 0
    # #281's two counters. `rounds_judged_by_fallback` counts the rounds judged as the
    # PRIOR fire's round because the newest was in flight, and `rounds_prior_unreadable`
    # counts the jobs left with NO round judged for want of a readable earlier fire — the
    # second is printed rather than folded into the first, because "judged an older round"
    # and "judged nothing at all" are different facts about the box.
    rounds_judged_by_fallback = 0
    rounds_prior_unreadable = 0
    # #499's two counters, and they are SEPARATE because they answer different questions: a
    # round carrying four fires and three receipts is ONE round under-receipted, and the
    # reader who must act on it needs both the count of rounds and the count of fires left
    # unanswered -- a single number would report either the rounds as fires or the fires as
    # rounds. Both print on a clean round as an explicit `0`, never as a missing key.
    rounds_under_receipted = 0
    fires_unanswered = 0
    # #477's counter. A round whose OWN trigger gate suppressed it owes no receipt at all,
    # and the excuse must be VISIBLE rather than a silent skip: a leg that quietly drops the
    # round trades a false RED for a false CLEAN, which is the #160 class this leg's other
    # excuses are all careful to avoid. The round is NAMED through `excused` like every other
    # excuse this leg writes, so no new rendering path is introduced for it.
    rounds_excused_by_suppression = 0
    # A MALFORMED RECEIPT is its own class (#281): the declaration exists and the reader
    # cannot reach it, which is neither a clean receipt nor an absent duty.
    receipts_malformed = 0
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
        # #487: the bound is read through the INJECTED reader where a probe supplied one,
        # exactly as the three board legs read theirs. Read from the ambient `REPO`, this
        # leg judges a history the probe never declared -- and the two halves of this
        # byte-paired file then disagree about what the factory declared, which is the
        # #459 class: the shipped half declares nothing and reads an adopting tree's bound.
        bound_instant, bound_text, bound_refusal = (scope_fn or duty_receipt_bound)(repo)
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
        # THE JOB'S OWN WINDOW (#449), derived BEFORE any branch so the coverage carries a
        # residual for every declared job -- including one excused by the bound, whose
        # window a reader still needs in order to see what it WOULD have been judged against.
        residual = duty_residual_for(
            row, stem, fires=fires or [], ledger_rows=ledger_rows,
            predicate=predicate, margin_for=margin_for, parse=reader_parse_ts,
        )
        residuals.append(residual)
        if residual["over_cadence"]:
            rounds_over_cadence += 1
        residual_secs = residual["residual_secs"]
        round_date = receipt_round(fired)
        if round_date is None:
            excused.append(
                f"{name} (cron id {job_id}): declares a receipt but records no fire "
                f"instant (last_run_at={fired!r}), so no round can be named — NOT JUDGED"
            )
            continue
        if bound_refusal:
            continue
        # THE ROUND'S OWN FIRES (#499), read from the daemon's table through the SAME reader
        # the residual above uses -- one population, one reader, so the comparison this feeds
        # cannot disagree with the window it is judged against. A day is a round and a
        # sub-daily job fires several times inside it; these are the fires that owe receipts.
        round_fires = [
            inst.strftime("%Y-%m-%dT%H:%M:%SZ")
            for inst in round_fire_instants(row, fires or [], round_date, reader_parse_ts)
        ]
        try:
            fired_instant = reader_parse_ts(fired)
        except (ValueError, TypeError):
            excused.append(
                f"{name} (cron id {job_id}): the round {round_date} records a fire "
                f"instant this leg cannot date ({fired!r}), so it cannot be placed "
                f"against the declared bound either — NOT JUDGED"
            )
            continue
        # #477: THE ROUND'S OWN SUPPRESSION, read from the fire record the round names. A
        # trigger-gated duty fires on time, is stored `status=success`, and produces no
        # receipt — indistinguishable, without this read, from a lane that did nothing. The
        # excuse is PER ROUND and from the FIRE RECORD, never from a declaration: a
        # declaration-based excuse would also cover a conditional duty that genuinely ran and
        # produced nothing, which is a false CLEAN and the exact failure this leg exists to
        # catch (ruling n=3232).
        fire = round_fire_record(row, fires or [], fired_instant, reader_parse_ts)
        if fire is not None and fire.get("suppressed"):
            rounds_excused_by_suppression += 1
            excused.append(
                f"{name} (cron id {job_id}): the round {round_date} (fired {fired}) was "
                f"SUPPRESSED by its own trigger gate — the daemon's own run record reads "
                f"`{CRON_SUPPRESSION_MARKER}` — so this round owed NO receipt and is NOT "
                f"JUDGED, and NEVER backfilled"
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
        # THE FORWARD WINDOW (#200), DERIVED per job since #449. A round younger than its
        # OWN job's residual is IN FLIGHT: the trigger fired and the lane it woke has not
        # finished, which the leg cannot read and must not call a missing duty. The window
        # AND the age are PRINTED -- a bare skip would trade a false RED for a false clean,
        # which is the #160 class -- and the window is now the JOB's, so a duty whose real
        # rounds run 178 min is no longer judged against a fleet constant derived from the
        # rounds that cleared FAST.
        age = (residual_now - fired_instant).total_seconds()
        if 0 <= age < residual_secs:
            rounds_excused_by_residual += 1
            excused.append(
                f"{name} (cron id {job_id}): the round {round_date} (fired {fired}) is "
                f"IN FLIGHT — {duty_age_text(age)} old at the {read_at or 'unstated'} read, "
                f"against its OWN residual {duty_age_text(residual_secs)} "
                f"[{duty_residual_basis_text(residual)}]. A round younger than its residual "
                f"is NOT JUDGED: the trigger fired and its lane has not finished, and this "
                f"leg cannot tell that from a duty never done"
            )
            # THE ROUND THE PREVIOUS FIRE WOKE (#281, ruling n=2003). Reading `last_run_at`
            # alone made this leg judge exactly ONE round per job, and for a job whose
            # derived residual reaches its own cadence that round was ALWAYS the one still
            # in flight — so the `continue` above ended the job's turn and NO round was ever
            # judged. Measured live at 2026-10-12T18:40Z: `factory-triage-patrol` (`0 */6`,
            # derived residual 3.77 d against a 6 h cadence) had no round judged at all.
            #
            # The prior round is READ from the job's own run record and NEVER composed: an
            # instant no record dates is the #175 class wearing arithmetic, and a leg that
            # judges one round per job owes a NAMED round or an honest silence.
            prior = prior_fire_instant(row, fires or [], fired_instant, reader_parse_ts)
            if prior is None:
                rounds_prior_unreadable += 1
                excused.append(
                    f"{name} (cron id {job_id}): the round {round_date} (fired {fired}) is "
                    f"still inside its residual, and this job's OWN run record dates NO fire "
                    f"before it ({len(fires or [])} fire(s) read in all), so no prior round "
                    f"can be NAMED — NOT JUDGED: this leg judges one round per job, and it "
                    f"will not infer an instant that no record carries"
                )
                continue
            prior_fired = prior.strftime("%Y-%m-%dT%H:%M:%SZ")
            prior_date = receipt_round(prior_fired)
            if prior_date is None or prior_date == round_date:
                rounds_prior_unreadable += 1
                excused.append(
                    f"{name} (cron id {job_id}): the fire before the newest round "
                    f"({prior_fired}) does not name a DIFFERENT round from {round_date}, so "
                    f"no prior round can be NAMED — NOT JUDGED"
                )
                continue
            # #477, the same excuse on the round this leg actually JUDGES. A job whose gate
            # suppresses every fire is judged on its prior round (#281), so the suppression
            # read must follow the leg onto whichever round it lands on — `factory-questions-
            # redeliver` is the live instance and it has never had a round that was not
            # suppressed.
            prior_fire = round_fire_record(row, fires or [], prior, reader_parse_ts)
            if prior_fire is not None and prior_fire.get("suppressed"):
                rounds_excused_by_suppression += 1
                excused.append(
                    f"{name} (cron id {job_id}): the PRIOR round {prior_date} (fired "
                    f"{prior_fired}) was SUPPRESSED by its own trigger gate — the daemon's "
                    f"own run record reads `{CRON_SUPPRESSION_MARKER}` — so this round owed "
                    f"NO receipt and is NOT JUDGED, and NEVER backfilled"
                )
                continue
            if bound_instant is not None and prior < bound_instant:
                rounds_excused_by_bound += 1
                excused.append(
                    f"{name} (cron id {job_id}): the PRIOR round {prior_date} (fired "
                    f"{prior_fired}) is BEFORE the declared bound {bound_text} for "
                    f"`{DUTY_RECEIPT_BOUNDARY_KEY}`, so no receipt was possible for it — "
                    f"NOT JUDGED, and NEVER backfilled"
                )
                continue
            prior_age = (residual_now - prior).total_seconds()
            if 0 <= prior_age < residual_secs:
                rounds_excused_by_residual += 1
                excused.append(
                    f"{name} (cron id {job_id}): the PRIOR round {prior_date} (fired "
                    f"{prior_fired}) is {duty_age_text(prior_age)} old at the "
                    f"{read_at or 'unstated'} read, inside its OWN residual "
                    f"{duty_age_text(residual_secs)} — NOT JUDGED: two consecutive rounds "
                    f"both inside one window leave this job with no round to judge"
                )
                continue
            prior_round_fires = [
                inst.strftime("%Y-%m-%dT%H:%M:%SZ")
                for inst in round_fire_instants(row, fires or [], prior_date, reader_parse_ts)
            ]
            rounds_judged_by_fallback += 1
            finding = duty_round_finding(
                name=name, job_id=job_id, stem=stem, round_date=prior_date,
                fired=prior_fired, ledger_rows=ledger_rows, predicate=predicate,
                fallback_from=round_date, schedule_text=job_schedule_text(row),
                round_fires=prior_round_fires, residual_secs=residual_secs,
                read_instant=residual_now,
            )
            judged.append(finding["judged"])
            problems.extend(finding["problems"])
            excused.extend(finding["excused"])
            rounds_superseded += finding["superseded"]
            receipts_malformed += finding["malformed"]
            _missing = finding["judged"].get("fires_unanswered", 0)
            fires_unanswered += _missing
            if _missing:
                rounds_under_receipted += 1
            continue
        finding = duty_round_finding(
            name=name, job_id=job_id, stem=stem, round_date=round_date, fired=fired,
            ledger_rows=ledger_rows, predicate=predicate,
            round_fires=round_fires, residual_secs=residual_secs,
            read_instant=residual_now,
        )
        judged.append(finding["judged"])
        problems.extend(finding["problems"])
        excused.extend(finding["excused"])
        rounds_superseded += finding["superseded"]
        receipts_malformed += finding["malformed"]
        _missing = finding["judged"].get("fires_unanswered", 0)
        fires_unanswered += _missing
        if _missing:
            rounds_under_receipted += 1

    state, state_reason = attestation_state(store)
    return {
        "name": "duty-receipt",
        # A leg that FOUND problems has read the population, even where no row declared a
        # stem: reporting NOT RUN beside a non-empty problem list would say the leg could not
        # look in the same breath as it reports what it saw (#506).
        "status": "ASSERTED" if (declared or problems) else "NOT RUN",
        # The reason NAMES ITS POPULATION and refuses the conclusion (#242 clause 5). The
        # old text ended "so no duty owes a receipt on this box" — a POSITIVE CLAIM ABOUT
        # THE BOX drawn from an enumeration that can be empty, which is how a lane
        # patrolling from a linked worktree was told the box was clean while the main
        # checkout reported two real problems in the same minute. An empty population
        # supports no conclusion about duties; it supports a statement about the read.
        "reason": (None if declared else (
            f"of the {len(attributed)} enabled row(s) this factory declares, NONE names a "
            f"receipt STEM to judge — {len(owes_none)} declares it OWES NONE and "
            f"{len(undeclared)} carries no `receipt_subject:` line at all — so NO DUTY WAS "
            f"JUDGED: that is a statement about the DECLARED population ({len(rows)} row(s) "
            f"read in all), never a finding that no duty owes a receipt on this box"
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
            # THE SECOND BUCKET (#424 item 2). Named beside the first rather than folded into
            # it: a row that declares it owes none is a DECLARATION the leg read and honoured,
            # and a row that declares nothing is a SILENCE the leg could not act on. Printing
            # one number for both would report the second as the first.
            "jobs_owing_none": len(owes_none),
            "owes_none_jobs": [str(r.get("name") or "") for r in owes_none],
            "jobs_undeclared": len(undeclared),
            "undeclared_jobs": [str(r.get("name") or "") for r in undeclared],
            # THE FOURTH BUCKET (#506), named beside its siblings rather than folded into
            # the silence it used to be counted as: a malformed declaration is evidence the
            # author MEANT to declare, which is a different fact from declaring nothing.
            "jobs_malformed": len(malformed),
            "malformed_jobs": [str(r.get("name") or "") for r, _ in malformed],
            "malformed_shapes": [shape for _, shape in malformed],
            # And the declared exemptions, printed as debt rather than subtracted silently:
            # a reader must be able to see WHICH duty was excused and on what authority.
            "jobs_undeclared_exempt": len(undeclared_exempt),
            "undeclared_exempt_jobs": [str(r.get("name") or "") for r, _ in undeclared_exempt],
            "jobs_stale_exempt": len(stale_exemptions),
            "stale_exempt_jobs": stale_exemptions,
            "jobs_unattributed": len(foreign),
            "duties_judged": judged,
            "bound": bound_text,
            "bound_refusal": bound_refusal,
            "rounds_superseded": rounds_superseded,
            "rounds_excused_by_bound": rounds_excused_by_bound,
            # THE WINDOW IS PER JOB (#449): there is no single fleet residual to print, so
            # the coverage carries the DEFAULT and the FORM beside the per-job derivations.
            # A scalar here would be a number no round was judged against.
            "residuals": residuals,
            "residual_default_secs": DUTY_RESIDUAL_DEFAULT_SECS,
            "residual_default_basis": DUTY_RESIDUAL_DEFAULT_BASIS,
            "residual_form": DUTY_RESIDUAL_FORM,
            "rounds_over_cadence": rounds_over_cadence,
            "rounds_excused_by_residual": rounds_excused_by_residual,
            # #281: the walk's two outcomes, PRINTED rather than folded together. A leg
            # that judged an older round and a leg that judged NOTHING both leave the newest
            # round unjudged, and a reader who cannot tell them apart cannot act on either.
            "rounds_judged_by_fallback": rounds_judged_by_fallback,
            "rounds_prior_unreadable": rounds_prior_unreadable,
            # #499: the fires that owed a receipt and found none. The round itself is NAMED
            # through `problems`, each fire with its own instant -- a count without the
            # instance is a problem the operator cannot act on.
            "rounds_under_receipted": rounds_under_receipted,
            "fires_unanswered": fires_unanswered,
            # #477: the rounds a trigger gate suppressed. The count rides here and the round
            # itself is NAMED through `excused`, like every other excuse this leg writes --
            # a count without the instance is a problem the operator cannot act on.
            "rounds_excused_by_suppression": rounds_excused_by_suppression,
            # The malformed class counts separately from `duties_missing` even though both
            # RED the round: a receipt whose token the reader cannot reach is not a duty
            # nobody did, and the finding says so in its own words.
            "receipts_malformed": receipts_malformed,
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

def duty_residual_basis_text(residual: dict) -> str:
    """HOW one job's residual was obtained — the derivation, or the default and why.

    A cap without its basis is unreadable: `4.12 h` says nothing a reader can check, while
    `margin 4.01 x its own measured max 59.0 min over 13 round(s)` can be recomputed from
    the ledger. The default's own reason travels too, because "no measurable round" and
    "measured, and the number is this" are different facts that must never render alike.
    """
    if residual.get("basis") == "derived":
        return (
            f"derived: margin {residual['margin_x']:.3f} x its own measured max "
            f"{duty_age_text(residual['measured_max_secs'])} over "
            f"{residual['measured_rounds']} round(s)"
        )
    max_secs = residual.get("measured_max_secs")
    if max_secs is not None and max_secs <= 0:
        return (
            f"DEFAULT — {residual.get('measured_rounds', 0)} measurable round(s) for this "
            f"job, whose max measured latency is NON-POSITIVE ({max_secs} s); `margin_for` "
            f"divides by it, so the default is applied at this caller rather than raising"
        )
    return (
        f"DEFAULT — {residual.get('measured_rounds', 0)} measurable round(s) for this job, "
        f"so there is no measured max to derive from"
    )


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

# ---- the ledger ref-role leg (#330, ruled at n=3362) ----------------------------------
#
# A receipt's PROSE asserts a ROLE for a named row -- "intake row n=2374", "dispatch row
# n=2376", "close row n=Z" -- and `tools/ledger.py` validates a `row:` pointer for
# EXISTENCE only: the token must be numeric and at most the current max `n`. A number
# composed from a stale read therefore passes the write path while naming a DIFFERENT row,
# and a reader following it lands on another lane's event and reads a green. That is #330's
# own instance: the Triage 2026-10-05T12 patrol receipt carried eight refs six low, every
# one of them resolving to the Worker lane's close rows.
#
# THE PREDICATE IS THE ROLE MATCH, and it was chosen by measurement over two alternatives
# (ruling n=3362 section 2). "The ref's subject is claimed in the receipt's detail" passes
# all eight of that receipt's refs -- a round receipt's detail is long and names many items
# -- and would red 68 of 657 row-refs; "the noun the detail asserts for a ref is that row's
# EVENT" bites the instance and its siblings. Existence is the WRITE path's leg and stays
# there; identity is this one's.
#
# SCOPE, and it PRINTS on every run: the three roles the ruling names -- intake, dispatch,
# close. The same class exists on `run` / `ruling` / `claim` assertions (measured
# 2026-10-17: n=1688, n=3032, n=3033), and those are NOT judged here. Two further measured
# instances (n=2724, n=3099) are citations of UNPUBLISHED or OWN-NUMBERING rows -- a
# false-positive class the ruling never adjudicated -- and a predicate that reds on correct
# prose is the permanent-false-positive class #507 names, where a leg with no exit teaches
# the next reader to ignore a red patrol. Widening is a later question with its own
# measurement, never an accident of this one.
REF_ROLE_EXEMPTIONS = REPO / "docs" / "ledger-ref-roles-exemptions.json"

# A COMPOUND label -- "ruling/dispatch rows n=2277" -- asserts NEITHER role, and the
# lookbehind is what keeps it out of the population: measured on this corpus, the naive
# pattern counted two such labels as mismatches, and a false positive here is a red that
# teaches the reader to ignore the leg.
REF_ROLE_ASSERTION = re.compile(
    r"(?<![/\w-])(intake|dispatch|close)\s+rows?\s+`?n=(\d+)", re.IGNORECASE
)
REF_ROLES_JUDGED = ("intake", "dispatch", "close")

def load_ref_role_exemptions(path: Path | None = None) -> tuple[list[dict], list[str]]:
    """`(entries, problems)` for the declared ref-role exemption surface.

    AN ABSENT FILE IS THE SHIPPED STATE of a new factory -- the convention
    `docs/kit-exemptions.json` sets -- so absence is no problem and no exemption. A store
    that EXISTS but cannot be honoured IS a problem: an unreadable exemption list would red
    every adjudicated residual, and a typo'd entry would excuse nothing while reading as an
    excuse. An entry must carry the three fields the match needs plus a REASON, because an
    exemption nobody explained belongs to nobody (the same strictness gate 94 applies to the
    duty-receipt store).
    """
    target = path or REF_ROLE_EXEMPTIONS
    if not target.is_file():
        return [], []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], [
            f"{target.name} could not be read ({type(exc).__name__}), so no declared "
            f"exemption can be honoured and every residual is a finding"
        ]
    rows = data.get("exempt") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return [], [
            f"{target.name} declares no `exempt` list, so no exemption can be honoured"
        ]
    out: list[dict] = []
    problems: list[str] = []
    for index, entry in enumerate(rows):
        if not isinstance(entry, dict):
            problems.append(
                f"{target.name} entry {index} is not an object, so it can excuse nothing"
            )
            continue
        row_n = entry.get("row")
        asserted = str(entry.get("asserted") or "").strip().lower()
        asserted_row = entry.get("asserted_row")
        reason = str(entry.get("reason") or "").strip()
        if not isinstance(row_n, int) or isinstance(row_n, bool):
            problems.append(
                f"{target.name} entry {index} names no integer `row`, so it can excuse nothing"
            )
            continue
        if asserted not in REF_ROLES_JUDGED:
            problems.append(
                f"{target.name} entry {index} asserts {asserted or 'nothing'!r}, which is not "
                f"one of the roles this leg judges ({'/'.join(REF_ROLES_JUDGED)})"
            )
            continue
        if not isinstance(asserted_row, int) or isinstance(asserted_row, bool):
            problems.append(
                f"{target.name} entry {index} names no integer `asserted_row`, so it can "
                f"excuse nothing"
            )
            continue
        if not reason:
            problems.append(
                f"{target.name} entry {index} (n={row_n}) carries no `reason` -- an exemption "
                f"nobody explained belongs to nobody"
            )
            continue
        out.append({"row": row_n, "asserted": asserted,
                    "asserted_row": asserted_row, "reason": reason})
    return out, problems

def ledger_ref_roles_leg(rows: list[dict], *, read_at: str,
                         exemptions_path: Path | None = None) -> dict:
    """Does every role a receipt ASSERTS for a row name a row carrying that role?

    The population is PRINTED on every run, an explicit zero included: "examined 0" and
    "examined N and found nothing wrong" are the same verdict otherwise, and the first is
    exactly what a broken reader produces (#242).
    """
    by_n = {row.get("n"): row for row in rows if isinstance(row.get("n"), int)}
    assertions: list[tuple[int, str, int]] = []
    for row in rows:
        row_n = row.get("n")
        if not isinstance(row_n, int):
            continue
        for match in REF_ROLE_ASSERTION.finditer(str(row.get("detail") or "")):
            assertions.append((row_n, match.group(1).lower(), int(match.group(2))))
    residuals: list[dict] = []
    for row_n, asserted, asserted_row in assertions:
        target = by_n.get(asserted_row)
        actual = str((target or {}).get("event") or "") or None
        if actual == asserted:
            continue
        residuals.append({
            "row": row_n,
            "asserted": asserted,
            "asserted_row": asserted_row,
            "actual_event": actual,
            "declared": False,
        })
    entries, store_problems = load_ref_role_exemptions(exemptions_path)
    problems: list[str] = list(store_problems)
    excused: list[str] = []
    live = {(r["row"], r["asserted"], r["asserted_row"]) for r in residuals}
    used: set[tuple[int, str, int]] = set()
    for entry in entries:
        key = (entry["row"], entry["asserted"], entry["asserted_row"])
        if key not in live:
            # An exemption that matches no live mismatch is debt that has stopped describing
            # the ledger: PRINTED and counted, never subtracted, so a store that has rotted
            # into a rubber stamp is visible on the round it rots.
            problems.append(
                f"{REF_ROLE_EXEMPTIONS.name}: the exemption for n={entry['row']} asserting "
                f"`{entry['asserted']}` of n={entry['asserted_row']} matches no live "
                f"mismatch, so it excuses nothing"
            )
            continue
        used.add(key)
        excused.append(
            f"n={entry['row']} asserting `{entry['asserted']}` of n={entry['asserted_row']}: "
            f"DECLARED -- {entry['reason']}"
        )
    for residual in residuals:
        key = (residual["row"], residual["asserted"], residual["asserted_row"])
        residual["declared"] = key in used
        if residual["declared"]:
            continue
        target_text = (
            f"is a `{residual['actual_event']}`" if residual["actual_event"]
            else "names no row in this ledger"
        )
        problems.append(
            f"n={residual['row']} asserts `{residual['asserted']} row "
            f"n={residual['asserted_row']}` and n={residual['asserted_row']} {target_text} "
            f"-- the pointer resolves to a DIFFERENT role, so a reader following it lands on "
            f"another row and reads a green"
        )
    return {
        "name": "ledger-ref-roles",
        "status": "ASSERTED",
        "problems": problems,
        "excused": excused,
        "coverage": {
            "rows_read": len(rows),
            "roles_judged": list(REF_ROLES_JUDGED),
            "assertions_examined": len(assertions),
            "residuals": residuals,
            "exemptions_declared": len(entries),
            "exempted": len(used),
            "unresolved": sum(1 for r in residuals if not r["declared"]),
            "read_at": read_at,
        },
    }

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

# ---- the workspace-blocked leg (issue #201, ruled at ledger n=2286) -------------------
#
# The closing invariant on a governed run was `require rc=0`. Ruling n=2286 admits a SECOND
# lawful verdict -- `workspace_gate=blocked-by-unowned`, lawful ONLY when the row NAMES the
# blocking paths -- because on a shared tree a run's own artifacts can be clean while an
# unrelated lane's stranded paths keep `hygiene.py --audit` at rc=1. A token without its
# paths is an unexaminable excuse, and that is the failure mode the ruling refuses.
#
# A lawful exception must remain a VISIBLE DEBT, and the offline score gate cannot see it:
# that gate asserts the token was RECORDED, never that the block was real. So this leg is the
# live cross-reader the ruling's AC4 owes (#201, re-dispatched at ledger n=1886). It:
#   1. PRINTS the population of blocked declarations with its count, and is LOUD on a zero
#      population -- an instrument that never sees the token cannot be told from a broken one;
#   2. REDs on a declaration that names NO paths (the unexaminable excuse); and
#   3. RE-READS the named paths against the live tree, reporting every path that is no longer
#      dirty -- a declared block the live tree no longer corroborates.
#
# The read is the field predicate's POSITIONAL trailer, never a substring scan: rows that
# merely MENTION the token in prose (a dispatch, a ruling, the ledger repair that appended it)
# carry it mid-detail and are not declarations, and counting them would be this reader's own
# echo mistaken for evidence (AGENTS.md rule 7).
WORKSPACE_GATE_KEY = "workspace_gate"
WORKSPACE_BLOCKED_TOKEN = "blocked-by-unowned"
BLOCKED_PATHS_KEY = "blocked_paths"
# The row classes that carry a governed run's closing invariant: `score` is the daily
# survey's, `run` is the insights run's -- the two surfaces the law's closing-invariant
# clauses address. A `dispatch` or `ruling` row that merely cites the token is not a run.
WORKSPACE_GATE_EVENTS = ("score", "run")

def live_dirty_paths(root: Path = REPO) -> set[str]:
    """The repo-relative paths `git status --porcelain` reports as dirty, right now.

    `GIT_OPTIONAL_LOCKS=0` for the reason the worktree leg states: a read-only census must
    never refresh the index of a tree a peer lane may be mid-task on. A non-zero exit is an
    INSTRUMENT failure, raised rather than swallowed -- a cross-reader that cannot read the
    tree has corroborated nothing, and an empty set would read as "every path cleared", the
    exact false-clean this leg exists to prevent.
    """
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    proc = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        capture_output=True, text=True, env=env, timeout=120,
    )
    if proc.returncode != 0:
        raise BoardReadError(
            f"git status in {root} exited {proc.returncode}: "
            f"{(proc.stderr or '').strip()[:120]}"
        )
    dirty: set[str] = set()
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        entry = line[3:]
        if " -> " in entry:  # a rename: the destination is the path that is dirty
            entry = entry.split(" -> ", 1)[1]
        dirty.add(entry.strip())
    return dirty

def workspace_blocked_leg(rows: list[dict], *, read_at: str,
                          dirty_paths_fn=None) -> dict:
    """Every governed run that took the `blocked-by-unowned` escape hatch, cross-read live.

    Loud on a zero population (#201, #242): a run's closing invariant may lawfully be met by
    `workspace_gate=blocked-by-unowned`, so an instrument that reports NONE cannot be told
    from one that has stopped working -- the status is NOT RUN and the reason names the
    counts, never a clean HOLD over an empty read.

    The cross-read is REPORTED, never judged into a red: a declaration that named paths
    stranded at ITS instant is true history even after those paths are committed, and a leg
    that reds for ever on a settled block is the permanent-false-positive class #139 names.
    What this leg REDS on is the UNEXAMINABLE declaration -- the token with no paths, which
    no reader can tell from a forged clean.
    """
    fp = field_predicate_readers()
    problems: list[str] = []
    declarations: list[dict] = []
    runs_declaring_gate = 0

    for row in rows:
        if str(row.get("event") or "") not in WORKSPACE_GATE_EVENTS:
            continue
        detail = str(row.get("detail") or "")
        if WORKSPACE_GATE_KEY not in fp.declared_keys(detail):
            continue
        runs_declaring_gate += 1
        gate = ""
        paths_raw = ""
        for token in fp.trailer_tokens(detail):
            found = fp.keyed_value(token, WORKSPACE_GATE_KEY)
            if found is not None:
                gate = found
            found = fp.keyed_value(token, BLOCKED_PATHS_KEY)
            if found is not None:
                paths_raw = found
        if gate != WORKSPACE_BLOCKED_TOKEN:
            continue
        n = row.get("n")
        subject = str(row.get("subject") or "")
        paths = [p for p in paths_raw.split(",") if p]
        if not paths:
            problems.append(
                f"n={n} ({subject}): workspace_gate={gate} names NO blocking paths -- an "
                f"unexaminable excuse, and the token is lawful ONLY with {BLOCKED_PATHS_KEY}=. "
                f"A reader cannot tell a real block from a forged clean without them (#201)"
            )
        declarations.append({"n": n, "subject": subject, "paths": paths})

    if not declarations:
        return {
            "name": "workspace-blocked",
            "status": "NOT RUN",
            "problems": [],
            "excused": [],
            "coverage": {
                "reason": (
                    f"no governed run in {len(rows)} ledger row(s) declares "
                    f"workspace_gate={WORKSPACE_BLOCKED_TOKEN}. The escape hatch is lawful, "
                    f"so an instrument that never sees it cannot be told from one that has "
                    f"stopped working -- a zero is LOUD, never a clean factory (#201, #242)"
                ),
                "rows_read": len(rows),
                "runs_declaring_gate": runs_declaring_gate,
                "blocked_declarations": 0,
                "blocked_rows": [],
                "read_at": read_at,
            },
        }

    # The live tree is read ONCE, and only because a declaration exists to cross-read: a leg
    # with no declaration pays no `git status`. A tree that cannot be read makes the leg
    # NOT RUN rather than reporting every path as cleared -- the instrument failed, and a
    # failure is not a corroboration.
    try:
        dirty = set((dirty_paths_fn or live_dirty_paths)())
    except (BoardReadError, OSError, subprocess.SubprocessError) as exc:
        return {
            "name": "workspace-blocked",
            "status": "NOT RUN",
            "problems": problems,
            "excused": [],
            "coverage": {
                "reason": (
                    f"{len(declarations)} blocked declaration(s) could not be cross-read: "
                    f"the live tree was unreadable ({exc}) -- a cross-reader that cannot "
                    f"read the tree has corroborated nothing"
                ),
                "rows_read": len(rows),
                "runs_declaring_gate": runs_declaring_gate,
                "blocked_declarations": len(declarations),
                "blocked_rows": declarations,
                "read_at": read_at,
            },
        }

    for entry in declarations:
        entry["still_dirty"] = [p for p in entry["paths"] if p in dirty]
        entry["no_longer_dirty"] = [p for p in entry["paths"] if p not in dirty]

    return {
        "name": "workspace-blocked",
        "status": "ASSERTED",
        "problems": problems,
        "excused": [],
        "coverage": {
            "rows_read": len(rows),
            "runs_declaring_gate": runs_declaring_gate,
            "blocked_declarations": len(declarations),
            "blocked_rows": declarations,
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

# ---- the foreign-reference scope (#333) --------------------------------------------
#
# THE BOARD DECLARES THIS FACTORY'S NAMESPACE, and nothing else. A `#N` in free prose
# names whichever repository the writer had in mind, and the ledger holds rows for
# foreign numbers too (`#366` above). The board read cannot separate the two on its own,
# because a foreign number can COLLIDE with a real issue of this board: measured
# 2026-10-05, row n=186 (subject `#332-D5`, a comment on the FORK's issue) names
# *"fork issue #332"* in its detail, and the intake row n=2421 (`subject "#332"`) made
# that same number resident -- so the harvest carried `#332` out of the fork mention and
# the patrol printed `OWED #332: dispatched 17.22 d ago` against a board item filed the
# same day.
#
# The harvest stays: a wave's detail is where a subject-keyed census cannot look, and
# that is the leg's whole reason for reading prose. What was MISSING is the SCOPE of an
# OCCURRENCE, so the guard qualifies each occurrence rather than the token. A `#N` is a
# unit of THIS board only when it is written as one:
#
#   * UNQUALIFIED -- the character before `#` is not a word character, so `opencrabs#504`
#     and `leshchenko1979/miidas#99` are repository-qualified forms, not board units;
#   * not preceded by a FOREIGN SCOPE WORD -- `fork`, `upstream`, `foreign` -- among the
#     two words before it, which is the shape of *"fork issue #332"*;
#   * not preceded by a REPOSITORY PATH -- a token carrying `/`, no `#` and no `.`, the
#     shape of *"leshchenko1979/opencrabs #366"*. A token carrying `#` is a UNIT LIST
#     (`#200/#344` and `#33/#35` list this board's own units), never a path, and a token
#     carrying `.` is a FILE path; both are left alone.
#
# The word list is deliberately small and declared: it names the qualifiers this ledger
# actually writes, and every shape the 2026-10-05 measurement found is one of the three.
FOREIGN_SCOPE_WORDS = frozenset({"fork", "upstream", "foreign"})

def is_board_unit_occurrence(blob: str, start: int) -> bool:
    """Whether the `#N` starting at `blob[start]` is WRITTEN as a unit of this board.

    The scope half of the carried-unit harvest (#333). `start` indexes the `#`, so the
    character before it is the ATTACH test and the two words before it are the QUALIFIER
    test. True for an unqualified occurrence -- the form a lane writes when it means one
    of this board's units -- and False for a repository-qualified mention, which names
    whichever repository the writer had in mind.
    """
    if start > 0 and blob[start - 1].isalnum():
        # ATTACHED to a preceding word character (`opencrabs#504`, `repo#332`): a board
        # unit is preceded by a boundary, never by a repository's name.
        return False
    for token in blob[:start].rstrip().split()[-2:]:
        stripped = token.strip("*_`([<\"'|,;:.").lower()
        if stripped in FOREIGN_SCOPE_WORDS:
            return False
        if "/" in stripped and "#" not in stripped and "." not in stripped:
            return False
    return True

# THE PARK TOKEN (#331 clause 1): `park:owner:<question>`, declared in a work unit's OWN
# ledger row. HQ's C1 scope ruling (n=2884) fixes the shape at ONE -- the register is the
# only sanctioned blocked-on-you channel (docs/instruments/open-questions.md section 3), so
# the token names a REGISTER QUESTION and nothing else. A unit waiting on a board memo has
# no truthful token; `park:owner:memo:<issue>#<comment>` is REFUSED, and #301/#312/#313 wait
# on q39 once it is minted.
#
# IT IS READ FROM THE ROWS, NOT FROM A TABLE, and the deciding evidence is the live ledger:
# Triage's own park rows for #317/#320 (n=2881/n=2882) carry the token as the LAST LINE of
# their `detail`, and each says in as many words that "this row is the declared park HQ's C1
# defines". A table this tree edits would never see them, so the declaration the census has
# to honour is the one already written.
#
# THE TOKEN MUST STAND ALONE ON A LINE OF ITS OWN. The correction row beside those two
# (n=2883) QUOTES the token shape in prose while carrying no token itself -- it names
# `park:owner:q30` and `park:owner:q39` mid-sentence and closes "THIS ROW CARRIES NO PARK
# TOKEN". A reader that matched the substring would park #301 on the very mis-citation that
# row exists to withdraw, so a declaration is a line of its own and a mention is not.
PARK_TOKEN_RE = re.compile(r"^park:owner:(q\d+)$")
PARK_TOKEN_PREFIX = "park:owner:"


def declared_parks(
    rows: list[dict], is_unit, precedes_filing=None
) -> tuple[dict[str, tuple[str, dict]], list[str]]:
    """Read every `park:owner:<question>` declaration off the units' own ledger rows.

    Returns `{unit: (question_id, row)}` holding the NEWEST declaration per unit, plus
    problem strings. The declaring ROW travels with the question because the census must be
    able to print which row declared the park -- a park no reader can trace to a row is a
    claim, not a declaration.

    A LINE THAT TRIES TO DECLARE AND CANNOT BE READ IS A PROBLEM, never a silent pass: the
    factory believes it parked something the census cannot see, and the census would then go
    on reporting that unit OWED -- a defect in the declaration wearing the shape of a finding
    about the unit. The ONE shape is `park:owner:qN`, the id being a register question (HQ
    n=2884); the refused `memo:` form, a bare `<question>` placeholder and an empty id all
    land here. A member factory whose register mints a different id shape gets a visible
    problem rather than a silent non-park -- that is the honest direction, and it is a law
    question to settle, not one for this reader to guess at.

    A unit whose rows name two DIFFERENT questions is not adjudicated: the newest declaration
    wins and the PARKED line names the question and row it read, so a re-park (one question
    answered, another standing) is a traceable act rather than a silent overwrite.
    """
    declarations: dict[str, list[tuple[str, dict]]] = {}
    problems: list[str] = []
    for row in rows:
        subject = str(row.get("subject") or "").strip()
        if not is_unit(subject):
            continue
        if precedes_filing is not None and precedes_filing(row.get("ts"), subject):
            continue
        for line in str(row.get("detail") or "").splitlines():
            stripped = line.strip()
            if not stripped.startswith(PARK_TOKEN_PREFIX):
                continue
            match = PARK_TOKEN_RE.match(stripped)
            if not match:
                problems.append(
                    f"row n={row.get('n')} ({subject}) declares a park in a shape this leg "
                    f"cannot read: {stripped!r} -- the ONE shape is `park:owner:<question>` "
                    f"with a register question id (qN). The refused `memo:` form, a "
                    f"`<placeholder>` standing in for an id, or a prose line that merely "
                    f"STARTS with the prefix all land here: reword it, or make the "
                    f"declaration a line of its own (#331, HQ n=2884)"
                )
                continue
            declarations.setdefault(subject, []).append((match.group(1), row))
    parks: dict[str, tuple[str, dict]] = {}
    for unit, items in declarations.items():
        items.sort(key=lambda item: _ledger_row_order(item[1]))
        parks[unit] = items[-1]
    return parks, problems

# THE DECLARED DISPOSITION (#473). A ruling can DISPOSE of a unit -- rule it
# UNSUBSTANTIATED, void, not-a-defect -- without the board item being closed, and until this
# leg existed the census could not see that at all: it read the board, saw OPEN, saw a
# dispatch with no claim, and printed OWED.
#
# THE MEASURED FAILURE (#453). Intake n=3032, dispatch n=3033, and at n=3041 HQ ruled the
# unit "UNSUBSTANTIATED -- not-a-defect ... dispatch at n=3033 is void". The board item
# stayed OPEN, the census kept printing `OWED #453`, and a Worker lane claimed it at n=3202
# and spent a whole repair cycle building a 266-probe arm for a defect that had been ruled
# non-existent 26 hours earlier, then withdrew it (commit 8dc9a206) and closed the unit
# `outcome=abandoned` at n=3203. The cost was not the ruling -- the ruling was correct and
# loud -- it was that nothing downstream could READ it.
#
# THE MECHANISM IS THE PARK TOKEN'S, deliberately (#473's decided shape). `disposition:void`
# stands alone on a line of the unit's OWN row. That adds no event type and no vocabulary
# token to `tools/ledger_declaration.py`'s role-to-event matrix, so the blast radius is this
# reader and the fixture beside it. A new record type was considered and refused for exactly
# that widening; a prose parser was refused in ruling n=3206 and refused again here -- a
# finding invented from an unparsed file is worse than no finding.
#
# THE TOKEN MUST STAND ALONE ON A LINE OF ITS OWN, for the reason the park token must: a row
# that QUOTES the shape in prose carries no declaration (n=2883 withdrew a park on those
# terms), so a reader matching the substring would dispose of a unit on a row that only
# discussed disposing of it.
DISPOSITION_TOKEN_RE = re.compile(r"^disposition:void$")
DISPOSITION_TOKEN_PREFIX = "disposition:"

def declared_dispositions(
    rows: list[dict], is_unit, precedes_filing=None
) -> tuple[dict[str, tuple[str, dict]], list[str]]:
    """Read every `disposition:void` declaration off the units' own ledger rows.

    Returns `{unit: (kind, row)}` holding the NEWEST declaration per unit, plus problem
    strings. The declaring ROW travels with the kind because the census must be able to
    print which row disposed of the unit -- a disposition no reader can trace to a row is a
    claim, not a declaration, and the row is the only thing that makes "this was ruled, not
    forgotten" checkable.

    A LINE THAT TRIES TO DECLARE AND CANNOT BE READ IS A PROBLEM, never a silent pass: the
    factory believes a ruling disposed of a unit the census cannot see, and the census goes
    on serving that unit to a lane as live work -- the #453 failure with the declaration
    present and unread. `disposition:void` is the ONE shape today; a bare `disposition:`, a
    `disposition:<anything-else>` and a prose line that merely STARTS with the prefix all
    land here. Refusing the unknown rather than guessing is the honest direction: a
    disposition this reader does not implement is a law question, not a reading to invent.

    A unit whose rows declare two DIFFERENT dispositions is not adjudicated: the newest wins
    and the line names the row it read, so a re-disposition is a traceable act rather than a
    silent overwrite.
    """
    declarations: dict[str, list[tuple[str, dict]]] = {}
    problems: list[str] = []
    for row in rows:
        subject = str(row.get("subject") or "").strip()
        if not is_unit(subject):
            continue
        if precedes_filing is not None and precedes_filing(row.get("ts"), subject):
            continue
        for line in str(row.get("detail") or "").splitlines():
            stripped = line.strip()
            if not stripped.startswith(DISPOSITION_TOKEN_PREFIX):
                continue
            match = DISPOSITION_TOKEN_RE.match(stripped)
            if not match:
                problems.append(
                    f"row n={row.get('n')} ({subject}) declares a disposition in a shape "
                    f"this leg cannot read: {stripped!r} -- the ONE shape is "
                    f"`disposition:void`, standing alone on a line of its own. A bare "
                    f"`disposition:`, an unimplemented kind, or a prose line that merely "
                    f"STARTS with the prefix all land here: reword it, or make the "
                    f"declaration a line of its own (#473)"
                )
                continue
            declarations.setdefault(subject, []).append(("void", row))
    dispositions: dict[str, tuple[str, dict]] = {}
    for unit, items in declarations.items():
        items.sort(key=lambda item: _ledger_row_order(item[1]))
        dispositions[unit] = items[-1]
    return dispositions, problems

def _ledger_row_order(row: dict) -> tuple:
    """A dispatch row's append order: its `n` where the read declares one, else its stamp.

    `n` first because it IS the append order and a stamp can be backdated; the stamp is the
    fallback for a read that carries no `n`, which is every synthetic fixture and any member
    factory whose ledger reader does not number its rows. Comparing the pair is what keeps
    the ordering TOTAL rather than partial, so "the newest declaration" is a defined answer
    for any pair of rows rather than only for rows that happen to carry both fields.
    """
    n = row.get("n")
    return (n if isinstance(n, int) else -1, str(row.get("ts") or ""))

def stall_lane_names() -> dict[str, str]:
    """Live session id -> lane name, from the box's own session bindings (#331 clause 2).

    The OWED line must name the LANE a dispatch was ADDRESSED to, and a dispatch row
    declares that lane as a session id. Turning an id into a name is the registry's job, so
    this reads the SAME binding rows the registry leg reads -- `all_bindings()` -- and derives
    each name from the bound session's own title, the one read that needs no declaration to be
    present in a member factory that adopted this kit without one.

    A read that fails returns an EMPTY map rather than raising. The stall-census verdict is
    about stalled UNITS, and a binding store this read could not open must not decide it: an
    empty map makes every addressee UNRESOLVED, which the OWED line states in words -- the
    honest direction, and never the author printed in the addressee's slot.
    """
    try:
        registry = load_module("oc_registry", REGISTRY)
        bindings, _errors = registry.all_bindings()
    except Exception:
        return {}
    names: dict[str, str] = {}
    for row in bindings:
        session_id = str(row.get("session_id") or "")
        if not session_id or session_id in names:
            continue
        name, _canonical = registry.lane_name_from_title(row.get("session_title"))
        if name:
            names[session_id] = name
    return names

def _lane_claim_latency(
    units: list[str],
    dispatch_instants: dict[str, "dt.datetime"],
    claims_by_unit: dict[str, list[dict]],
    parse,
) -> dict:
    """A lane's OWN dispatch->claim intervals, over the units it was dispatched (#546).

    THE QUANTITY. For every unit this lane was handed AND that carries a `claim` row, the
    interval is (the unit's FIRST claim instant - its FIRST dispatch instant). Both halves
    are deliberately the FIRST of their kind. The first dispatch is the instant the unit
    entered the lane's queue, and it is the figure the ruling measured: `#543` was dispatched
    2026-10-22T08:07:31Z (n=4088) and claimed 14:15:17Z (n=4110) -- 6.13 h -- while pairing on
    a RE-hand would reset the clock every time the remedy was applied, flattering the lane
    exactly when it was stalled. The first claim is the TAKE; a later claim row on the same
    unit is a second state transition, not a second wait.

    THE POPULATION IS RETURNED (`n`), because a percentile over three intervals and one over
    a hundred render identically once printed. `p50`/`p75` are NEAREST-RANK over the sorted
    intervals, so both are durations a real take exhibited rather than an interpolation.

    A unit whose dispatch or claim instant this read cannot date is DROPPED and counted in
    `unpaired`, never imputed -- the same refusal the leg applies to an undatable dispatch,
    one level down. A NEGATIVE interval is dropped too: a claim that precedes its dispatch is
    not a wait, it is two rows about different hand-offs (a re-dispatch after a close, a
    cross-namespace collision), and letting it through would put a negative duration into the
    distribution. `n == 0` is therefore a real answer, and the caller prints it as NO
    distribution rather than inventing a tolerance (#546 bound).
    """
    intervals: list[float] = []
    unpaired = 0
    for unit in units:
        fired = dispatch_instants.get(unit)
        if fired is None:
            unpaired += 1
            continue
        claim_rows = claims_by_unit.get(unit) or []
        if not claim_rows:
            unpaired += 1
            continue
        claimed_at = None
        for claim_row in claim_rows:
            try:
                claimed_at = parse(str(claim_row.get("ts") or ""))
            except (ValueError, TypeError):
                continue
            break
        if claimed_at is None:
            unpaired += 1
            continue
        interval = (claimed_at - fired).total_seconds()
        if interval < 0:
            unpaired += 1
            continue
        intervals.append(interval)
    intervals.sort()
    record: dict = {
        "n": len(intervals),
        "unpaired": unpaired,
        "intervals_secs": intervals,
        "p50_secs": None,
        "p75_secs": None,
        "max_secs": None,
    }
    if intervals:
        record["p50_secs"] = _percentile(intervals, 0.50)
        record["p75_secs"] = _percentile(intervals, 0.75)
        record["max_secs"] = intervals[-1]
    return record

def stall_census_leg(
    issues: list[dict],
    rows: list[dict],
    *,
    read_at: str,
    threshold_days: float = STALL_CENSUS_THRESHOLD_DAYS,
    lane_names_fn=None,
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
      dispatch). The OCCURRENCE must ALSO be written as a unit of this board:
      `is_board_unit_occurrence` refuses a repository-qualified mention, so a fork's
      `#332` is not read as this board's `#332` however many rows the local issue
      carries (#333);
      BEARING IS NOT ROUTING (#467): such a row is read as the unit's ADDRESSEE
      only where the token stands in the row's OPENING LINE -- the SAME declared
      header the dispatch-delivery leg matches a delivery's subject against (#433),
      read through the same helper, because it is the same question one surface
      over. A row that dispatches a batch declares its units up front
      (`DISPATCH #318 -> the HQ lane`); a row that merely TALKS about them -- an
      escalation asking for a ruling, a return leg, a defect carried -- lists them
      hundreds of characters later, and dispatches none of them. The harvest count
      is unaffected: every token such a row names is still CARRIED, because that
      count is the harvest's coverage. What a MENTION may not take is every ROUTING
      slot (#470): population admission, the dispatch AGE the census measures from,
      and the PARK SUPERSESSION test -- a row that handed the unit to nobody cannot
      start its clock, and cannot put a declared park back in play. Measured on
      `n=3098`, a Triage escalation whose BODY names `#460` and `#313`: read
      permissively, both were admitted, dated off its own write stamp and printed
      as parks SUPERSEDED, so two units nobody had ever dispatched read OWED;
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

    A PARKED UNIT IS NOT A FINDING (#331 clause 1). This factory can DECLARE a work unit
    parked on something outside its own reach -- an owner question above all -- and the
    declaration is a `park:owner:<question>` token standing alone on a line of that unit's
    OWN ledger row. The unit then reads PARKED instead of OWED, leaves the `units_owed`
    total, and its exclusion is PRINTED beside the verdict. It is read from the rows rather
    than from a table this tree edits because the rows are where the declaration already
    lives: Triage's park rows for #317/#320 (n=2881/n=2882) carry the token as their last
    line, and a table would never have seen them.

    A PARK IS SUPERSEDED BY A LATER DISPATCH, and that guard is the whole reason the
    declaration can be trusted as a state rather than a permanent gag. An append-only ledger
    keeps every park row forever, so a unit re-dispatched after its park would otherwise stay
    silently held out of the census for good; a dispatch-bearing row NEWER than the declaring
    row puts the unit back in play, and the supersession is PRINTED so the stale declaration
    is visible rather than merely obeyed. A row that tries to declare and cannot be read (the
    refused `memo:` shape, a `<placeholder>` for an id, a prose line that merely starts with
    the prefix) is a PROBLEM, never a silent pass: a declaration the census cannot see is
    indistinguishable from no declaration, and it re-arms the very line the park was written
    to stop -- a defect in the declaration wearing the shape of a finding about the unit.

    THE OWED LINE NAMES THE ADDRESSEE, NEVER THE AUTHOR (#331 clause 2). It used to print
    `actor={actor}` -- the author of the dispatch-bearing row, which for a re-dispatch is
    whoever ran the census, usually Triage, never the lane the work belongs to -- beside the
    advice to "re-dispatch it to the lane that owns it". An author printed in that slot reads
    as an assignment, which is worse than an empty one. The addressee is the unit's MOST
    RECENT DECLARED ROUTING: a typed `session` ref, the same declaration the dispatch-delivery
    leg corroborates against, resolved to a lane name through the box's own session bindings.
    A later row that declares none does not erase an earlier declaration -- silence is not a
    re-routing -- so the search runs newest-first and stops at the first declaration. Where no
    row declares a target, or the declaration resolves to no lane name this read knows, the
    line SAYS SO in words; it never falls back to the author.

    THE REMEDY KEYS ON THE CLAIM, NEVER ON THE DRAIN (#546, ruling n=4117). #465 (ruling
    n=3097) had installed the clause one way round: wherever the addressee lane looked
    DRAINING, the OWED line said "do not re-dispatch, the lane already holds it". Its warrant
    is a DUPLICATE, and the OWED class is by definition NEVER CLAIMED -- so for 100% of the
    rows that clause governed, the warrant was false. Measured on the Worker lane: `#543`'s
    first dispatch (n=4088) was ACKNOWLEDGED by the lane in its own words at 08:45
    ("Ordering is clear: #543 first"), the session was then compacted 117 times in one day,
    111 of them in hours 08-09, and the unit produced no work for 4 h 53 m. DELIVERY, READING
    and RETENTION are three different things.

    So the branch is on the CLAIM:
    * a CLAIMED unit -> a re-hand IS a duplicate, and the line says so. Unreachable in the
      OWED class by construction (`owed` skips every claimed unit), which is the point: the
      CLAIMED class keeps its remedy explicitly rather than losing it, and
      `owed_units_carrying_a_claim` in the coverage asserts it stays unreachable.
    * a NEVER-CLAIMED unit whose lane is ALIVE -> the drain evidence still PRINTS (it tells
      the reader the lane is worth handing to) but it never FORBIDS the re-hand. The line
      says the lane is ALIVE but does NOT hold this unit, that a delivery it never re-read is
      SPENT, and that the act is a re-hand OLDEST FIRST, ONE AT A TIME.
    * a NEVER-CLAIMED unit whose lane claimed nothing inside the window -> the original
      sentence, VERBATIM. There the stall is real and the re-dispatch advice is the only exit
      there is (#465 criterion 3).

    THE AGE IS PLACED AGAINST THE LANE'S OWN DISTRIBUTION, not against a constant. Every OWED
    line prints the unit's own age, the addressee lane's paired dispatch->claim p50/p75 and
    `n`, and which side of that p75 the unit sits on. The pairing is FIRST dispatch to FIRST
    claim (see `_lane_claim_latency`), so a re-hand does not reset the clock. The declared
    threshold stops being the PERMISSION gate and stays only the OBSERVATION window: the
    ruling's measured basis for the Worker lane is n=108, p50 2.94 h, p75 17.63 h, and a fixed
    1.0 d threshold flags the normal case 21.3% of the time while saying nothing about the tail
    it exists to name.

    A LANE'S CLAIMS CAN BE OUT OF DISPATCH ORDER, AND THAT IS A FINDING (#546 change 3). A
    lane that claimed a YOUNGER unit while an OLDER one stayed unclaimed is not draining a
    queue: it takes what is HANDED to it when it is free, so a dispatch arriving while it is
    busy is SPENT, not queued. Such a lane prints `NOT-A-QUEUE` instead of `DRAINING`, with
    the pair that proves it, because that is exactly the shape in which the #465 warrant is
    void -- and before this test it passed as DRAINING.

    THE DRAIN EVIDENCE IS PRINTED BESIDE THE OWED TOTAL, never left to be inferred from a
    total that is smaller than the reader expected. The standing set is the LANE'S OWN
    DISPATCHED POPULATION, grouped on the SAME declared routing the addressee is read from,
    so the evidence and the line it corrects cannot disagree about whose lane it is. The
    window is this leg's own declared threshold, and the claims' own instants and row
    numbers travel with it, so the reading is re-derivable rather than asserted.
    """
    is_unit = ledger_predicate().is_work_unit

    def precedes_filing(ts: object, created: "dt.datetime | None") -> bool:
        """A dispatch instant that PREDATES the board item it would be read as
        dispatching (#415) -- the door #333's scope guard left open, where a number is
        named in prose (or carried by a foreign row) BEFORE this board minted it.

        False whenever either instant is absent or undatable. That is deliberate and is
        not a fail-open: a synthetic read that omits `createdAt` must keep every OTHER
        verdict intact, and an instant this leg cannot read is already refused elsewhere
        -- excusing it here would trade a false red for a false clean.
        """
        if created is None:
            return False
        try:
            return reader_parse_ts(str(ts or "")) < created
        except (ValueError, TypeError):
            return False

    # THE DECLARED PARKS (#331 clause 1), read ONCE, off the units' OWN rows. Read HERE,
    # after `precedes_filing`, because a park row that predates the board item's own filing
    # is a cross-namespace subject collision (#415) and not a declaration about this unit.
    parks, park_problems = declared_parks(rows, is_unit, precedes_filing)
    # THE DECLARED DISPOSITIONS (#473), read on the SAME terms and in the same place: a
    # ruling that disposed of a unit predating the board item's own filing is a
    # cross-namespace subject collision (#415), not a declaration about this unit.
    dispositions, disposition_problems = declared_dispositions(
        rows, is_unit, precedes_filing
    )

    claimed: set[str] = set()
    closed: set[str] = set()
    resident: set[str] = set()
    # THE CLAIM ROWS ARE KEPT, not merely counted (#465): the drain evidence is a claim's
    # INSTANT on a sibling unit, so the row itself has to survive the scan. The `claimed`
    # set stays for the OWED predicate -- it is read by the same loop and must keep its
    # exact meaning -- and this map is a SECOND reading of the same rows, keyed by the
    # unit each claim took.
    claims_by_unit: dict[str, list[dict]] = {}
    for row in rows:
        subject = str(row.get("subject") or "").strip()
        resident.add(subject)
        event = str(row.get("event") or "")
        if event == "claim":
            claimed.add(subject)
            claims_by_unit.setdefault(subject, []).append(row)
        elif event == "close":
            closed.add(subject)

    open_on_board: set[str] = set()
    for issue in issues:
        number = issue.get("number")
        if number is None:
            continue
        if str(issue.get("state", "")).strip().lower() == "open":
            open_on_board.add(f"#{number}")

    # THE FILING INSTANT (#415): each board item's own `createdAt`, where the read
    # declared it. A `#N` in free prose can name a DIFFERENT repository's issue of the
    # same number (#366), and a carrier may name a number months before THIS board
    # minted it (#344) -- so a dispatch row that PREDATES the item it is read as
    # dispatching cannot be a dispatch of it. A missing instant is simply absent from
    # this map, which is what keeps every synthetic fixture's verdict unchanged.
    board_created: dict[str, dt.datetime] = {}
    for issue in issues:
        number = issue.get("number")
        if number is None:
            continue
        try:
            board_created[f"#{number}"] = reader_parse_ts(
                str(issue.get("createdAt") or "")
            )
        except (ValueError, TypeError):
            continue

    # THE TRACKER ASSIGNEE (#423), read from the SAME board read and keyed the same way.
    # An assignee is NOT a claim -- a claim is a session-derived ledger row -- so this map
    # never touches the OWED predicate. It exists so the OWED line can render an
    # assigned-but-unclaimed unit differently from one nobody has touched: without it the
    # two read identically, which is the visibility gap the item names. A fixture that
    # omits `assignees` is simply absent from this map, keeping every other verdict intact.
    board_assignees: dict[str, list[str]] = {}
    for issue in issues:
        number = issue.get("number")
        if number is None:
            continue
        logins = [
            str(entry.get("login"))
            for entry in (issue.get("assignees") or [])
            if isinstance(entry, dict) and entry.get("login")
        ]
        if logins:
            board_assignees[f"#{number}"] = logins

    dispatch_rows = [row for row in rows if str(row.get("event") or "") == "dispatch"]
    carriers: dict[str, dict] = {}
    # THE DECLARED ROUTING (#331 clause 2), per unit: the NEWEST dispatch-bearing row that
    # declares a typed `session` target, and how many dispatch-bearing rows the unit has at
    # all. Both are read off every ROUTED row rather than off the one `carriers` holds,
    # because the two questions differ: `carriers` keeps the EARLIEST routed row, which is
    # what the age is measured from (#308), while the addressee is where the work was LAST
    # sent. A later row that declares no target does NOT erase an earlier declaration --
    # silence is not a re-routing -- so the map keeps the newest row that actually declares.
    declared_refs: dict[str, tuple[str, dict]] = {}
    dispatch_counts: dict[str, int] = {}
    # THE NEWEST DISPATCH-BEARING ROW, per unit, kept for the PARK SUPERSESSION test alone
    # (#331 clause 1): a park is a state read off the rows, and the ledger keeps every row
    # forever, so a unit re-dispatched AFTER its park would stay silently held out of the
    # census for good. A dispatch newer than the declaring row puts the unit back in play.
    # It is read off ROUTED rows alone (#470): a row that only NAMES the unit in its prose
    # dispatched nothing, so it cannot put a declared park back in play.
    newest_dispatch: dict[str, dict] = {}
    # THE MENTION POPULATION (#470), per unit: named by a carrier row that did NOT route
    # it. Kept as its own set so the leg prints the two populations side by side -- a
    # narrowed read that hides what it dropped is the failure this leg exists to catch.
    mention_units: set[str] = set()

    def declare(unit: str, row: dict, *, routed: bool) -> None:
        """Record one dispatch-bearing row against the unit it dispatched.

        `routed` (#467) is whether the row DISPATCHED the unit or merely NAMED it, and
        it gates every ROUTING question this harvest feeds: `declared_refs` (where the
        work was LAST SENT), `newest_dispatch` (the park-supersession test, #331 clause
        1) and the caller's `carriers` (population admission and the age). A row that
        merely NAMES a unit in its prose -- an escalation, a return leg, a defect
        carried -- is a MENTION, and a mention answers none of them: it did not hand the
        unit to anyone, it did not put a declared park back in play, and it did not
        start the clock on the unit's age. Measured on `n=3098`, a Triage escalation
        whose BODY names `#460` and `#313`: read permissively they were admitted, dated
        off its own write stamp and printed as parks SUPERSEDED, so two units nobody had
        ever dispatched read OWED (#470).

        What stays PERMISSIVE is the harvest COUNT (`dispatch_counts`), which measures
        how many rows name the unit at all: that is coverage, not routing, and it is
        what keeps #467's criterion 3 legible.

        A carrier row is routed for a unit when the token stands in its opening line;
        a direct row is routed by construction, since the unit IS its subject.
        """
        dispatch_counts[unit] = dispatch_counts.get(unit, 0) + 1
        if routed:
            held_row = newest_dispatch.get(unit)
            if held_row is None or _ledger_row_order(row) >= _ledger_row_order(held_row):
                newest_dispatch[unit] = row
        session_ref = next(
            (str(value) for ref in (row.get("refs") or [])
             for kind, value in ref.items() if kind == "session"), ""
        )
        if not session_ref:
            return
        if not routed:
            # A MENTION, not a routing: the row names the unit without sending it
            # anywhere, so it declares no addressee however new it is (#467).
            return
        held = declared_refs.get(unit)
        if held is None or _ledger_row_order(row) >= _ledger_row_order(held[1]):
            declared_refs[unit] = (session_ref, row)

    observation = 0
    carried_units = 0
    pre_filing_rejected = 0
    # THE ROUTING TEST'S OWN COUNT (#467): tokens carried by a carrier row but named
    # only in its BODY, so read as a mention and refused the routing slot. Printed
    # beside the harvest count, so a leg that rejected nothing is distinguishable from
    # one that never applied the test.
    mentions_rejected = 0
    for row in dispatch_rows:
        subject = str(row.get("subject") or "").strip()
        if is_unit(subject):
            # THE FILING INSTANT (#415), the DIRECT door: a subject-keyed dispatch whose
            # row PREDATES the board item's own `createdAt` is a cross-namespace subject
            # collision -- the row carries another repository's issue of that number, not
            # this board's (`#366`'s rows n=433/n=436 are the fork's).
            if precedes_filing(row.get("ts"), board_created.get(subject)):
                pre_filing_rejected += 1
            else:
                carriers.setdefault(subject, row)
                # ROUTED BY CONSTRUCTION: the unit IS the row's subject, so the row
                # names it in its header wherever in the detail it goes on to explain
                # itself (#467).
                declare(subject, row, routed=True)
            continue
        blob = f"{row.get('detail') or ''} {row.get('refs') or ''}"
        # THE ROUTING TEST (#467). A carrier is read for the units it NAMES; whether it
        # ROUTED them is a second question, and the ledger's own answer is WHERE the
        # token stands. A batch dispatch declares its units in its OPENING LINE
        # (`DISPATCH #318 -> the HQ lane`, `CENSUS RE-DISPATCH #67 -> Worker`), while a
        # row that merely TALKS about them -- an escalation, a return leg, a defect
        # carried -- lists them hundreds of characters and many lines further down.
        # The scope is the SAME declared header the dispatch-delivery leg measures a
        # delivery's subject against (#433), read through the SAME helper, because it
        # is the same question one surface over: a body mention is a MENTION, not a
        # routing. Raising the scope is a one-line change here, the same lever the
        # delivery leg declares for a factory whose notices open with a banner.
        header = delivery_header(row.get("detail") or "")
        header_units = {
            match.group(0)
            for match in re.finditer(r"#\d+", header)
            if is_unit(match.group(0))
            and is_board_unit_occurrence(header, match.start())
        }
        units = {
            match.group(0)
            for match in re.finditer(r"#\d+", blob)
            if is_unit(match.group(0))
            and match.group(0) in resident
            # THE SCOPE (#333): the token must be WRITTEN as a unit of this board, not
            # merely named in prose that belongs to another repository's namespace.
            and is_board_unit_occurrence(blob, match.start())
        }
        if not units:
            observation += 1
            continue
        # THE FILING INSTANT (#415), the CARRIER door: a carrier's prose may name a
        # number that only LATER became this board's (`#344`'s carrier n=321, dated
        # 2026-09-18, while the board minted `#344` on 2026-10-05). A carrier cannot have
        # dispatched an item that did not yet exist.
        before_filing = len(units)
        units = {
            unit for unit in units
            if not precedes_filing(row.get("ts"), board_created.get(unit))
        }
        pre_filing_rejected += before_filing - len(units)
        if not units:
            continue
        carried_units += len(units)
        mentions_rejected += sum(1 for unit in units if unit not in header_units)
        for unit in units:
            if unit in header_units:
                carriers.setdefault(unit, row)
            else:
                # A MENTION, not a routing: counted in `mention_units` and NOT admitted to
                # the population, so it neither dates the unit nor lets the unit's declared
                # park read SUPERSEDED (#470). #467's harvest count is unaffected.
                mention_units.add(unit)
            declare(unit, row, routed=unit in header_units)

    problems: list[str] = list(park_problems) + list(disposition_problems)
    excused: list[str] = []
    owed: list[dict] = []
    parked: list[str] = []
    parked_units: set[str] = set()
    park_superseded: list[str] = []
    # THE VOIDED UNITS (#473), the disposition's own three buckets, kept SEPARATE from the
    # park's so neither declaration can be printed under the other's heading: `voided_units`
    # are OWED units a ruling EXCLUDED from the owed total, `disposition_superseded` maps a
    # unit whose void was lifted by a LATER dispatch to that dispatch, and the never-routed
    # and matched-no-OWED-line notes are assembled after the loop.
    voided: list[str] = []
    voided_units: set[str] = set()
    disposition_superseded: dict[str, tuple[str, dict, dict]] = {}
    # THE SUPERSEDED UNITS (#470), by name: those units are listed in `park_superseded`, and
    # they must NOT also be listed among the declarations that "matched NO OWED line" -- one
    # park printed with two contradictory dispositions is the defect #471 reports.
    superseded_units: set[str] = set()
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
        # THE DECLARED DISPOSITION (#473), checked BEFORE the park and after the age test,
        # for the same reason the park is: a declaration can only ever REMOVE a line the
        # census would otherwise report. Before the park because the two are not peers -- a
        # park says the unit waits on the owner, a disposition says the unit is not a defect
        # at all, so a unit carrying both must read VOID and must never also print "the park
        # is SUPERSEDED, so the unit stays OWED", which would be false the moment the void
        # was honoured.
        disposition = dispositions.get(unit)
        if disposition is not None:
            kind, disposition_row = disposition
            superseding = newest_dispatch.get(unit)
            if (
                superseding is not None
                and _ledger_row_order(superseding) > _ledger_row_order(disposition_row)
            ):
                # SUPERSEDED, and printed rather than obeyed: the ledger keeps every ruling
                # forever, so a unit re-dispatched AFTER it was ruled void would otherwise
                # stay excluded for good and the stale ruling would read as live. The line
                # stays OWED; the note says why the disposition no longer holds.
                disposition_superseded[unit] = (kind, disposition_row, superseding)
            else:
                voided_units.add(unit)
                voided.append(
                    f"VOID {unit}: dispatched {age_days:.2f} d ago and NEVER CLAIMED, but a "
                    f"ruling DECLARED it `disposition:{kind}` at row "
                    f"n={disposition_row.get('n')} -- not a finding, and EXCLUDED from the "
                    f"owed total (#473)."
                )
                continue
        # THE PARK STATE (#331 clause 1). The unit reaches the OWED predicate and a declared
        # park holds it: it reads PARKED, it is NOT a finding, and it leaves the owed total.
        # The park is checked HERE, after the age test, so the declaration can only ever
        # REMOVE a line the census would otherwise report -- never add one, and never change
        # the age of a line it does not hold.
        park = parks.get(unit)
        if park is not None:
            question, park_row = park
            superseding = newest_dispatch.get(unit)
            if (
                superseding is not None
                and _ledger_row_order(superseding) > _ledger_row_order(park_row)
            ):
                # SUPERSEDED, and printed rather than obeyed: the ledger keeps every park row
                # forever, so a unit put back in play by a LATER dispatch would otherwise stay
                # held out of the census for good, and the stale declaration would read as a
                # live park. The line stays OWED; the note says why the declaration no longer
                # holds.
                superseded_units.add(unit)
                park_superseded.append(
                    f"{unit} declares park:owner:{question} at row n={park_row.get('n')}, but "
                    f"a LATER dispatch-bearing row n={superseding.get('n')} puts it back in "
                    f"play -- the park is SUPERSEDED, so the unit stays OWED (#331)"
                )
            else:
                parked_units.add(unit)
                parked.append(
                    f"PARKED {unit}: dispatched {age_days:.2f} d ago and NEVER CLAIMED, but "
                    f"this factory DECLARED it parked on {question} at row "
                    f"n={park_row.get('n')} -- not a finding, and EXCLUDED from the owed "
                    f"total (#331)."
                )
                continue
        declared = declared_refs.get(unit)
        owed.append({
            "unit": unit,
            "age_days": age_days,
            "assignees": board_assignees.get(unit, []),
            "session_ref": declared[0] if declared else "",
            "ref_row_n": declared[1].get("n") if declared else None,
            "dispatch_rows": dispatch_counts.get(unit, 1),
        })

    # A PARK WHOSE UNIT IS NOT IN THE POPULATION AT ALL (#470). The declaration STANDS and the
    # unit is EXCLUDED from the owed total, but no dispatch ROUTED it, so it never entered the
    # census population and no OWED line is owed for it. `#460` and `#313` reach this branch
    # through `n=3098`, a Triage escalation that names them in its BODY. They read PARKED
    # rather than "matched NO OWED line", because that note's reasons -- claimed, closed, off
    # this board, no longer stalled -- all describe a unit that WAS routed, and it closes by
    # inviting the reader to suspect the declaration names the wrong subject. Here the
    # declaration is right and the routing is simply absent.
    park_never_routed = [
        (unit, question, row)
        for unit, (question, row) in parks.items()
        if unit not in parked_units
        and unit not in superseded_units
        and unit not in carriers
    ]
    # NOT counted in `units_parked`, which means OWED units a park HELD OUT: these units were
    # never in the population, so the census never owed them a line and the park held nothing
    # out. The set exists so the "matched NO OWED line" note below does not print a second,
    # contradictory disposition for the same park (#471).
    never_routed_units = {unit for unit, _, _ in park_never_routed}
    park_never_routed_notes = [
        f"PARKED {unit}: declares park:owner:{question} at row n={row.get('n')} -- the "
        f"declaration STANDS and the unit is EXCLUDED from the owed total; no dispatch "
        f"ROUTED it (its token stands in a row's BODY, never in the opening line, or it is "
        f"not a unit of this board), so it is not in the census population and no OWED line "
        f"is owed (#470)"
        for unit, question, row in park_never_routed
    ]

    # A PARK DECLARED FOR A UNIT THAT IS NOT OWED IS PRINTED, never silently ignored: a
    # declaration that matches no OWED line is indistinguishable from a typo'd subject, and a
    # declaration that quietly does nothing is the same failure an unreadable one is. The
    # legitimate reasons are named so the note reads as an observation rather than a defect:
    # the unit may be claimed, closed, off this board, or no longer past the threshold.
    park_notes = [
        f"{unit} declares park:owner:{question} at row n={row.get('n')}, but matched NO OWED "
        f"line this read -- the unit is claimed, closed, off this board, or no longer stalled; "
        f"if none of those hold, the declaration names the wrong subject (#331)"
        for unit, (question, row) in parks.items()
        if unit not in parked_units
        and unit not in superseded_units
        and unit not in never_routed_units
        # A unit a ruling DISPOSED OF, or whose void a later dispatch lifted, must not also
        # print a park note: one unit carrying two contradictory dispositions is the defect
        # #471 reports, and the void line above is the one that decided the census (#473).
        and unit not in voided_units
        and unit not in disposition_superseded
    ] + park_superseded + park_never_routed_notes

    # A DISPOSITION WHOSE UNIT IS NOT IN THE POPULATION AT ALL (#473), on the park's terms:
    # the declaration STANDS and the unit is EXCLUDED from the owed total, but no dispatch
    # ROUTED it, so it never entered the census population and no OWED line is owed for it.
    disposition_never_routed = [
        (unit, kind, row)
        for unit, (kind, row) in dispositions.items()
        if unit not in voided_units
        and unit not in disposition_superseded
        and unit not in carriers
    ]
    disposition_never_routed_units = {unit for unit, _, _ in disposition_never_routed}
    disposition_never_routed_notes = [
        f"VOID {unit}: declares `disposition:{kind}` at row n={row.get('n')} -- the "
        f"declaration STANDS and the unit is EXCLUDED from the owed total; no dispatch "
        f"ROUTED it (its token stands in a row's BODY, never in the opening line, or it is "
        f"not a unit of this board), so it is not in the census population and no OWED line "
        f"is owed (#473)"
        for unit, kind, row in disposition_never_routed
    ]
    # A DISPOSITION DECLARED FOR A UNIT THAT IS NOT OWED IS PRINTED, never silently ignored,
    # and never under the park heading: a declaration that matches no OWED line is
    # indistinguishable from a typo'd subject, and one that quietly does nothing is the same
    # failure an unreadable one is. A unit held PARKED is excluded here because the park
    # already printed it -- the two declarations are exclusive in the printed census (#471).
    disposition_superseded_notes = [
        f"{unit} declares `disposition:{kind}` at row n={row.get('n')}, but a LATER "
        f"dispatch-bearing row n={superseding.get('n')} puts it back in play -- the "
        f"disposition is SUPERSEDED, so the unit stays OWED (#473)"
        for unit, (kind, row, superseding) in disposition_superseded.items()
        if unit not in parked_units
    ]
    disposition_notes = [
        f"{unit} declares `disposition:{kind}` at row n={row.get('n')}, but matched NO OWED "
        f"line this read -- the unit is claimed, closed, off this board, or no longer "
        f"stalled; if none of those hold, the declaration names the wrong subject (#473)"
        for unit, (kind, row) in dispositions.items()
        if unit not in voided_units
        and unit not in disposition_superseded
        and unit not in parked_units
        and unit not in disposition_never_routed_units
    ] + disposition_superseded_notes + disposition_never_routed_notes

    # THE ADDRESSEE'S NAMES ARE RESOLVED ONCE, and only when there is a line to put them on:
    # the live read walks every profile's session bindings, so a census with nothing owed
    # pays nothing for it. A resolver that raises leaves the map EMPTY, which makes every
    # addressee UNRESOLVED -- stated in words on the line -- rather than deciding the verdict.
    lane_names: dict[str, str] = {}
    if owed and lane_names_fn is not None:
        try:
            lane_names = dict(lane_names_fn() or {})
        except Exception:
            lane_names = {}

    # THE LANE'S OWN DRAIN (#465), read off the rows and printed BESIDE the OWED total.
    #
    # THE DEFECT THIS ANSWERS. The OWED line used to close with a remedy that, for a unit
    # whose addressee lane is demonstrably draining, names an exit that does not exist:
    # "re-dispatch it" is a duplicate (the sibling `dispatch-delivery` leg proves a delivery
    # EXISTS on the unit and says in its own words "do not re-dispatch on this line"), and
    # "close it on the board" would be a falsification, because these units are live, OPEN,
    # wanted defects of this factory's own product. A finding with no working exit is the
    # class this factory refuses (#295, #139).
    #
    # THE MEASURED SHAPE. The addressee lane is SERIAL -- one unit at a time, implement ->
    # audit -> publish -> close -- so a multi-item queue outlives the 1.0 d threshold and
    # the tail re-flags every round while the lane works exactly as designed. Measured
    # 2026-10-11T06 on the live ledger: the 2026-10-10T18:19Z batch (dispatch rows
    # n=3066-n=3075, ten units) was still carrying nine OWED, and the Worker lane
    # (`dcd8f7a9`) had claimed and closed two of that same batch inside the window --
    # `#162` claim n=3080 at 2026-10-10T19:51:24Z, `#67` claim n=3083 at 22:25:43Z, 3.4553 h
    # apart. A bare "9 OWED" is therefore a LANE reading, not nine independent findings.
    #
    # THE STANDING SET IS THE LANE'S OWN DISPATCHED POPULATION, and a SIBLING is any unit
    # in it. The set is grouped on the SAME declared routing the addressee is read from, so
    # the evidence and the line it corrects cannot disagree about whose lane it is; a unit
    # whose routing does not resolve to a lane NAME is in no group, which is why a read with
    # no binding store prints no drain evidence rather than attributing one to a bare uuid.
    # A lane with no claim inside the window is left ALONE: its OWED line keeps the original
    # remedy verbatim, because there the stall is real and the re-dispatch advice is the
    # only exit there is (#465 criterion 3).
    owed_lanes: set[str] = set()
    for entry in owed:
        ref = declared_refs.get(entry["unit"])
        if ref and lane_names.get(ref[0]):
            owed_lanes.add(lane_names[ref[0]])

    # THE LANE'S DISPATCHED POPULATION, grouped on the SAME declared routing the addressee is
    # read from, built ONCE and shared by the drain evidence and the latency profile (#546).
    # `carriers` keeps the EARLIEST routed dispatch row for a unit (`setdefault`), so its `ts`
    # is the instant the unit entered its lane's queue -- the base of the pairing below.
    lane_units: dict[str, list[str]] = {}
    dispatch_instants: dict[str, "dt.datetime"] = {}
    for unit, carrier_row in carriers.items():
        try:
            dispatch_instants[unit] = reader_parse_ts(str(carrier_row.get("ts") or ""))
        except (ValueError, TypeError):
            pass
        ref = declared_refs.get(unit)
        if not ref:
            continue
        name = lane_names.get(ref[0])
        if name:
            lane_units.setdefault(name, []).append(unit)

    # THE LANE'S OWN LATENCY DISTRIBUTION (#546 change 2), derived for EVERY lane carrying an
    # OWED unit -- never only for a lane with an in-window claim. The figure is what a reader
    # places each unit's AGE against, so it is a property of the LANE and not of the verdict,
    # and withholding it on a lane whose claims fell outside the observation window would hide
    # the distribution exactly where the stall is longest.
    lane_profiles: dict[str, dict] = {
        lane: _lane_claim_latency(
            lane_units.get(lane, []), dispatch_instants, claims_by_unit, reader_parse_ts
        )
        for lane in sorted(owed_lanes)
    }

    lane_drain: list[str] = []
    draining_lanes: set[str] = set()
    not_a_queue_lanes: set[str] = set()
    lane_drain_verdicts: list[dict] = []
    if owed_lanes:
        try:
            now = reader_parse_ts(read_at)
        except (ValueError, TypeError):
            now = None
        if now is not None:
            window_start = now - dt.timedelta(days=threshold_days)
            for lane in sorted(owed_lanes):
                drained: list[tuple[str, dict]] = []
                for unit in lane_units.get(lane, []):
                    for claim_row in claims_by_unit.get(unit, []):
                        try:
                            claimed_at = reader_parse_ts(str(claim_row.get("ts") or ""))
                        except (ValueError, TypeError):
                            continue
                        if window_start <= claimed_at <= now:
                            drained.append((unit, claim_row))
                if not drained:
                    continue
                drained.sort(key=lambda item: str(item[1].get("ts") or ""))
                draining_lanes.add(lane)
                # THE ORDER TEST (#546 change 3, ruling n=4117). A lane whose claims are out
                # of DISPATCH order is not draining a queue. The measured mechanism: the
                # Worker lane claimed and closed `#545`, dispatched 75.3 min YOUNGER than
                # `#543`, then produced zero claim rows for 4 h 10 m 30 s with `#543` still
                # unclaimed. A lane draining a queue in dispatch order would have taken the
                # OLDER unit next. It did not: it takes what is HANDED to it when it is free,
                # so a dispatch arriving while it is busy is SPENT, not queued -- which is
                # exactly why the #465 warrant ("a re-hand is a duplicate") is VOID here.
                # Before this test the same fixture passed as DRAINING, so the one lane shape
                # that makes the warrant false was the shape the evidence called healthy.
                out_of_order: list[tuple[str, str]] = []
                for claimed_unit, _claim_row in drained:
                    claimed_fired = dispatch_instants.get(claimed_unit)
                    if claimed_fired is None:
                        continue
                    for other in lane_units.get(lane, []):
                        if other in claimed or other in closed:
                            continue
                        other_fired = dispatch_instants.get(other)
                        if other_fired is None:
                            continue
                        if other_fired < claimed_fired:
                            out_of_order.append((other, claimed_unit))
                evidence = (
                    f"claimed {len(drained)} sibling(s) of the same standing set inside the "
                    f"last {threshold_days} d -- "
                    + ", ".join(
                        f"{unit} at row n={claim_row.get('n')} "
                        f"({claim_row.get('ts')})"
                        for unit, claim_row in drained
                    )
                )
                if out_of_order:
                    oldest_unclaimed, younger_claimed = out_of_order[0]
                    not_a_queue_lanes.add(lane)
                    lane_drain_verdicts.append({
                        "lane": lane,
                        "verdict": "NOT-A-QUEUE",
                        "claims_in_window": len(drained),
                        "out_of_order_pairs": len(out_of_order),
                    })
                    lane_drain.append(
                        f"NOT-A-QUEUE {lane}: {evidence}, BUT OUT OF DISPATCH ORDER -- "
                        f"{younger_claimed} (dispatched "
                        f"{dispatch_instants.get(younger_claimed)}) was claimed while "
                        f"{oldest_unclaimed} (dispatched "
                        f"{dispatch_instants.get(oldest_unclaimed)}, OLDER) is still "
                        f"unclaimed. This lane does NOT drain a queue: it takes what is "
                        f"handed to it when it is free, so a dispatch arriving while it is "
                        f"busy is SPENT, not queued -- the #465 warrant ('a re-hand is a "
                        f"duplicate') is VOID for this lane, and re-handing the OLDEST "
                        f"unclaimed unit ONE AT A TIME is the lawful act (#546)"
                    )
                    continue
                lane_drain_verdicts.append({
                    "lane": lane,
                    "verdict": "DRAINING",
                    "claims_in_window": len(drained),
                    "out_of_order_pairs": 0,
                })
                lane_drain.append(
                    f"DRAINING {lane}: {evidence}. A multi-item backlog on a queue-draining "
                    f"lane is a LANE reading, not N owed items: the remedy is ONE "
                    f"consolidated backlog-first brief that names the ORDER, OLDEST FIRST, "
                    f"one unit at a time (#465, #546)"
                )

    owed.sort(key=lambda entry: -entry["age_days"])
    addressees_resolved = 0
    units_owed_on_draining_lanes = 0
    # THE BACKLOG GROUPED ON THE SAME DECLARED ROUTING THE ADDRESSEE IS READ FROM (#133).
    # The driverless-lane leg asks whether a lane carrying an unclaimed backlog has a DRIVER,
    # and it must ask that about the SAME addressees this leg already resolved -- re-deriving
    # the routing one leg over would be a second reader of the same declaration, and the two
    # would drift apart on the first re-routing either of them missed. So the grouping is
    # built HERE, from the entries this leg has just resolved, and travels in the coverage.
    # The population of that leg is therefore exactly `owed_by_lane`, printed beside it.
    owed_by_lane: dict[str, dict] = {}
    for entry in owed:
        key = entry["session_ref"] or ""
        slot = owed_by_lane.setdefault(
            key,
            {"session_ref": key, "lane": None, "units": [], "oldest_age_days": 0.0},
        )
        slot["units"].append(entry["unit"])
        slot["oldest_age_days"] = max(slot["oldest_age_days"], entry["age_days"])
    for entry in owed:
        unit = entry["unit"]
        # THE ASSIGNEE IS RENDERED, NEVER PREDICATED ON (#423). An assigned-but-unclaimed
        # unit and one nobody has touched are different states, and before this the OWED
        # line rendered them identically -- an assigned unit read as untouched. The
        # sentence says the assignee is not a claim, because the two must not be confused:
        # OWED stays OWED until a `claim` row exists.
        assignee_note = ""
        if entry["assignees"]:
            assignee_note = (
                f" The tracker shows it ASSIGNED to {', '.join(entry['assignees'])}, but "
                f"an assignee is not a ledger claim, so it stays OWED."
            )
        # THE ADDRESSEE, NOT THE ACTOR (#331 clause 2). The slot names the LANE the dispatch
        # was handed to; where nothing resolves it says so. The row's AUTHOR is deliberately
        # NOT printed here -- an author in this slot reads as an assignment, which is worse
        # than an empty one, and for a census re-dispatch the author is only whoever ran the
        # census.
        session_ref = entry["session_ref"]
        name = lane_names.get(session_ref) if session_ref else None
        if session_ref and name:
            addressees_resolved += 1
            slot = owed_by_lane.get(session_ref)
            if slot is not None:
                slot["lane"] = name
            addressee_note = (
                f"the routing standing at read time (row n={entry['ref_row_n']}) was "
                f"ADDRESSED to {name}"
            )
        elif session_ref:
            addressee_note = (
                f"NO ADDRESSEE RESOLVES: its most recent declared routing (row "
                f"n={entry['ref_row_n']}) names a typed `session` target this read cannot "
                f"turn into a lane name (#331)"
            )
        else:
            addressee_note = (
                f"NO ADDRESSEE RESOLVES: none of its {entry['dispatch_rows']} "
                f"dispatch-bearing row(s) declares a typed `session` target, so the lane "
                f"the work was handed to is UNSTATED (#331)"
            )
        # THE UNIT'S AGE AGAINST ITS OWN LANE'S DISTRIBUTION (#546 change 2, ruling n=4117).
        # The age prints BESIDE the lane's own paired dispatch->claim p50/p75 and n, so a
        # reader places it instead of weighing a bare "5.00 d" against a constant. The
        # ruling's measured basis for the Worker lane: n=108, p50 2.94 h, p75 17.63 h -- and
        # the fixed 1.0 d threshold sits on the WRONG side of that data, flagging the normal
        # case 21.3% of the time and saying nothing about the tail it exists to name. The
        # threshold stays the OBSERVATION window; the LANE's own p75 is the READING, and it
        # orders the re-hand rather than forbidding it.
        age_hours = entry["age_days"] * 24.0
        profile = lane_profiles.get(name) if name else None
        if profile and profile.get("n"):
            p50_h = profile["p50_secs"] / 3600.0
            p75_h = profile["p75_secs"] / 3600.0
            max_h = profile["max_secs"] / 3600.0
            side = "ABOVE" if age_hours > p75_h else "AT OR BELOW"
            age_note = (
                f" Its age {age_hours:.2f} h is {side} its addressee lane's own p75 of "
                f"{p75_h:.2f} h (n={profile['n']} paired dispatch->claim interval(s): "
                f"p50 {p50_h:.2f} h, p75 {p75_h:.2f} h, max {max_h:.2f} h, derived from the "
                f"lane's own rows; {profile['unpaired']} unit(s) UNPAIRED and excluded, never "
                f"imputed)."
            )
        else:
            age_note = (
                f" Its age {age_hours:.2f} h is placed against NO measured distribution: the "
                f"addressee lane's own dispatch->claim history yields n=0 paired interval(s) "
                f"this read can derive, so its p75 is UNKNOWN and the age is not evidence "
                f"about it (#546)"
            )
        # THE REMEDY KEYS ON THE CLAIM, NEVER ON THE DRAIN (#546 change 1, ruling n=4117).
        # #465 installed this clause in the OWED branch and keyed it on the addressee lane's
        # DRAIN. Its warrant is a DUPLICATE -- "a delivery EXISTS, so a re-dispatch carries no
        # state change" -- and the OWED class is by definition NEVER CLAIMED, so for 100% of
        # the rows it governs the warrant is false. Measured on the Worker lane: #543's first
        # dispatch (n=4088) was ACKNOWLEDGED by the lane in its own words at 08:45 ("Ordering
        # is clear: #543 first"), and the session was then compacted 117 times in one day, 111
        # of them in hours 08-09, dying mid-task. Delivery, reading and RETENTION are three
        # different things: the delivery existed and the working state did not.
        unit_claimed = unit in claimed
        if unit_claimed:
            # UNREACHABLE IN THE OWED CLASS (#546), and that is the point: `owed` is built by
            # skipping every unit in `claimed`, so this branch keeps the CLAIMED class's remedy
            # explicit rather than deleting it. `owed_units_carrying_a_claim` in the coverage
            # is the standing assertion that it stays unreachable.
            remedy_note = (
                f"Do NOT re-dispatch this item: its addressee lane ({name}) has CLAIMED it, "
                f"so a second hand-off would duplicate work already in hand (#546)"
            )
        elif name in draining_lanes:
            units_owed_on_draining_lanes += 1
            if name in not_a_queue_lanes:
                held = (
                    f"ALIVE, and its claims are OUT OF DISPATCH ORDER, so it does not drain a "
                    f"queue either -- it takes what is HANDED to it when it is free"
                )
            else:
                held = (
                    f"ALIVE -- it claimed a sibling of the same standing set inside the last "
                    f"{threshold_days} d -- but it does NOT hold this unit"
                )
            remedy_note = (
                f"Re-hand it OLDEST FIRST, ONE AT A TIME: its addressee lane ({name}) is "
                f"{held}. A delivery the lane never re-read is SPENT, so a re-hand is NOT a "
                f"duplicate and is the lawful act (#546)"
            )
        else:
            remedy_note = (
                f"Re-dispatch it to the lane that owns it through `session_notify`, or "
                f"close it on the board: a dispatch no lane has taken is work nobody is "
                f"doing"
            )
        problems.append(
            f"OWED {unit}: dispatched {entry['age_days']:.2f} d ago and NEVER CLAIMED, "
            f"and the board still carries it OPEN -- {addressee_note}.{assignee_note}"
            f"{age_note} {remedy_note}"
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
            # THE ROUTING TEST'S OWN COUNT (#467), beside the harvest it filters.
            # `carried_units_resolved` measures the HARVEST -- every board-unit token
            # a carrier row names -- and stays deliberately permissive, because that
            # is what makes the leg's coverage legible. The ADDRESSEE is the stricter
            # question, and this is how many of those tokens were named only in the
            # BODY: read as a mention, never as a routing.
            "mentions_rejected": mentions_rejected,
            # THE TWO POPULATIONS (#470), printed side by side so a narrowed read cannot
            # hide what it dropped: `units_in_population` is what a dispatch ROUTED, and
            # `units_named_only_as_mentions` is what the harvest saw and refused the
            # population slot -- units a row named in its BODY and never handed to anyone.
            "units_named_only_as_mentions": len(mention_units - set(carriers)),
            "units_rejected_pre_filing": pre_filing_rejected,
            "units_in_population": len(carriers),
            "units_off_board": off_board,
            "units_owed": len(owed),
            "units_owed_assigned": sum(1 for entry in owed if entry["assignees"]),
            # THE PARK EXCLUSION TRAVELS WITH THE VERDICT (#331 clause 1): a reader who sees
            # `units_owed: 15` and a census of 17 dispatched units must be able to read WHY,
            # and `units_parked` beside `parks_declared` is that answer. A park that was
            # declared and then SUPERSEDED is counted in neither -- it is named in `parks`,
            # where a reader meets the declaration and the dispatch that lifted it.
            "parks_declared": len(parks),
            "units_parked": len(parked_units),
            "units_park_superseded": len(park_superseded),
            "parks": parked + park_notes,
            # THE DISPOSITION EXCLUSION TRAVELS WITH THE VERDICT (#473), on the park's terms:
            # a reader who sees an owed total smaller than the dispatched population must be
            # able to read WHY, and `units_voided` beside `dispositions_declared` is that
            # answer. A void lifted by a later dispatch is counted in neither -- it is named
            # in `dispositions`, where the declaration and the dispatch that lifted it meet.
            "dispositions_declared": len(dispositions),
            "units_voided": len(voided_units),
            "units_disposition_superseded": len(disposition_superseded_notes),
            "dispositions": voided + disposition_notes,
            # THE ADDRESSEE COVERAGE (#331 clause 2): how many OWED lines could name the lane
            # the work was handed to. A line that names none says so in words; this pair is
            # the count, so a read where NOTHING resolved is not mistaken for one where the
            # question was never asked.
            "addressees_resolved": addressees_resolved,
            "addressees_unresolved": len(owed) - addressees_resolved,
            # THE BACKLOG BY ADDRESSEE (#133). The driverless-lane leg's population, printed
            # here so the two legs cannot disagree about which lane a unit sits on. A lane
            # whose routing does not resolve to a name appears with `lane: null` and its
            # units, which is the UNRESOLVED line this leg already reds -- carried, never
            # silently dropped from the grouping.
            "owed_by_lane": sorted(
                owed_by_lane.values(),
                key=lambda slot: (-slot["oldest_age_days"], slot["session_ref"]),
            ),
            "lanes_with_backlog": len(owed_by_lane),
            # THE DRAIN EVIDENCE TRAVELS WITH THE VERDICT (#465 criterion 1). A reader who
            # sees `units_owed: 9` must be able to read WHY that is a LANE reading and not
            # nine independent findings, and the count of OWED units sitting on a lane with
            # in-window claims is that answer. It prints even at zero, so a leg that found no
            # drain is distinguishable from one that never looked.
            #
            # THE VERDICT SPLIT IS NEW (#546 change 3, ruling n=4117): a lane with in-window
            # claims is ALIVE, and whether it is DRAINING A QUEUE is a SECOND question --
            # `lanes_not_a_queue` counts the lanes whose claims are OUT OF DISPATCH ORDER, so
            # the shape that makes the #465 warrant false is named rather than averaged into
            # the healthy count. Before this split that shape read as DRAINING.
            "lanes_draining": len(draining_lanes),
            "lanes_draining_a_queue": len(draining_lanes - not_a_queue_lanes),
            "lanes_not_a_queue": len(not_a_queue_lanes),
            "units_owed_on_draining_lanes": units_owed_on_draining_lanes,
            "lane_drain": lane_drain,
            "lane_drain_verdicts": lane_drain_verdicts,
            # THE STANDING ASSERTION OF CHANGE 1 (#546): the claim-keyed remedy's CLAIMED
            # branch is unreachable in this class BY CONSTRUCTION, because `owed` is built by
            # skipping every claimed unit. Printing the count is what turns "unreachable" from
            # a comment into a measured fact -- a non-zero here means the owed predicate and
            # the remedy have drifted apart.
            "owed_units_carrying_a_claim": sum(1 for entry in owed if entry["unit"] in claimed),
            # THE LANE'S OWN LATENCY DISTRIBUTION (#546 change 2), per lane, with its
            # population and its EXCLUDED count. A percentile without its `n` is not a
            # measurement, and `unpaired` is what the derivation refused rather than imputed.
            "lane_latency_profiles": {
                lane: {
                    "n": record["n"],
                    "unpaired": record["unpaired"],
                    "p50_secs": record["p50_secs"],
                    "p75_secs": record["p75_secs"],
                    "max_secs": record["max_secs"],
                }
                for lane, record in lane_profiles.items()
            },
            "threshold_days": threshold_days,
            "threshold_basis": STALL_CENSUS_THRESHOLD_BASIS,
            "read_at": read_at,
        },
    }

# THE FOURTH READING AND THE HONEST FIFTH (#532, ruling n=3952). `UNARMED-ACTIVE` is a lane
# with NO active goal row that was nonetheless MEASURED WORKING inside the declared window --
# the reading the leg could not produce while it read goal rows alone, and the one that made a
# draining lane read DRIVERLESS. `UNREADABLE` is not a reading of a lane but of the SOURCE: it
# exists so an unread activity store can never render as "no work" (#271).
DRIVERLESS_READINGS = (
    "DRIVEN",
    "ARMED-INERT",
    "DRIVERLESS",
    "UNARMED-ACTIVE",
    "UNREADABLE",
)

def _newest_goal_row(goal_rows: list[dict]) -> dict | None:
    """The row that decides a session's current state, or None for no rows.

    Ordered by `updated_at` then `created_at` then row order, because a session may carry
    several rows over its life and the last one is its current state. A row whose instants are
    NULL still sorts (as the empty string), which keeps the ordering TOTAL rather than partial:
    "the newest row" must be a defined answer for every input.
    """
    if not goal_rows:
        return None
    return max(
        goal_rows,
        key=lambda row: (str(row.get("updated_at") or ""), str(row.get("created_at") or "")),
    )

def _goal_turns_used(row: dict) -> int:
    """`turns_used` as an int, with an unreadable value counting as ZERO.

    The card's DRIVEN predicate needs `turns_used > 0`, so an unparseable value must not read
    as motion: zero is the conservative direction -- it withholds the "driven" claim rather
    than inventing one.
    """
    try:
        return int(row.get("turns_used") or 0)
    except (TypeError, ValueError):
        return 0

def _goal_advanced(row: dict) -> bool:
    """Whether the row was touched AFTER it was created -- the card's motion half.

    Both instants must be present and comparable; a missing one is NOT evidence of motion.
    """
    created = str(row.get("created_at") or "")
    updated = str(row.get("updated_at") or "")
    return bool(created) and bool(updated) and updated > created

def driver_reading(
    goal_rows: list[dict],
    *,
    turn_open: bool = False,
    activity: dict,
) -> tuple[str, dict | None]:
    """(reading, newest goal row) for ONE session's goal rows -- the CARD's predicates.

    THE PREDICATES ARE THE CARD'S, not this reader's invention: `TEMPLATE/roles/triage.md`
    carries the four-reading table, and #460's second criterion requires the runner and the
    card to AGREE, so a change here owes the card a change in the same commit.

    * DRIVEN        -- the evaluation is ADVANCING: `turns_used > 0` and `updated_at >
                       created_at`, or a turn is in flight. MOTION, never declared state -- a
                       goal is evaluated only at a turn's END, so an armed goal cannot summon a
                       turn, and `state='active'` is a declaration that a driver exists rather
                       than a measurement that one is in the room.
    * ARMED-INERT   -- an active row that is not advancing: `turns_used = 0` and `updated_at =
                       created_at` is the card's named case, and it covers every other
                       active-but-motionless row too. The loop exists and steers a turn that is
                       not coming.
    * UNARMED-ACTIVE-- no active row, and MEASURED WORK inside the declared window: the lane is
                       draining through something other than a goal loop. Re-arm is REFUSED --
                       a working lane does not need a driver installed (#532).
    * DRIVERLESS    -- no active row and no measured work inside that window: no goal-loop
                       driver and no measured work since the instant the reading prints.
    * UNREADABLE    -- the ACTIVITY source could not be read, so the lane's driving state is
                       not known. Never a zero (#271).

    NO BRANCH ASSERTS THE FUTURE (#532). The pre-#532 text said DRIVERLESS meant "nothing will
    evaluate this session's goal"; two facts cannot support a claim about what happens next,
    and the ledger falsified it -- 33 `close` rows by actor `worker` landed after the goal row
    this leg was judging had stopped, and the Surveys lane carries no goal row in any home
    while recording 10,336 tool executions. Every reading now states what was MEASURED, and
    the activity instant is carried on the record so "no work since T" can never be confused
    with "not read".

    `activity` IS REQUIRED and has no default: a caller that does not state the fact would get
    the pre-#532 reading back silently, which is exactly the defect. Its `state` is one of
    LANE_ACTIVITY_READ / LANE_ACTIVITY_NONE / LANE_ACTIVITY_UNREADABLE, and only the READ arm
    carries `in_window` and `instant`.

    THE MOTION CLAUSE IS SCOPED TO A LIVE ROW, and that scoping is the ONE place the card's
    rows did not already agree. Read literally, a `paused` row that advanced before it stopped
    satisfies DRIVEN (`turns_used > 0`, `updated_at > created_at`) AND DRIVERLESS (no active
    row, no turn in flight) at the same time, so the two rows overlapped and the table never
    said which won. The card states the scope and this reader matches it, because the
    alternative is a reading that calls a stopped loop "driven" and therefore REFUSES the one
    act that would restart it: a paused lane holding a fortnight-old backlog would print DRIVEN
    and go unmentioned for ever, which is the exact failure #133 was filed to end.

    A turn in flight is tested FIRST and decides on its own: the card states that a lane whose
    turn is in flight is driven by that turn EVEN WHEN ITS ARM IS INERT.
    """
    if turn_open:
        return "DRIVEN", _newest_goal_row(goal_rows)
    newest = _newest_goal_row(goal_rows)
    state = str((newest or {}).get("state") or "").strip().lower()
    if newest is not None and state == GOAL_DRIVEN_STATE:
        if _goal_turns_used(newest) > 0 and _goal_advanced(newest):
            return "DRIVEN", newest
        return "ARMED-INERT", newest
    # NO ACTIVE ROW from here on, so the ACTIVITY fact decides -- and it decides in THIS order.
    # An unreadable source is UNREADABLE before it can be a zero (#271): the leg must never
    # report "no work" when what it means is "could not look".
    kind = str((activity or {}).get("state") or "")
    if kind == LANE_ACTIVITY_UNREADABLE:
        return "UNREADABLE", newest
    if kind == LANE_ACTIVITY_READ and bool((activity or {}).get("in_window")):
        return "UNARMED-ACTIVE", newest
    return "DRIVERLESS", newest

def stall_lane_turn_open() -> dict[str, bool]:
    """Live session id -> whether a turn is IN FLIGHT, from the box's own bindings (#133).

    The card's DRIVEN row admits a lane "whose turn is in flight" even when its arm is inert,
    so the reading needs a fact `goal_state` does not carry. It comes from the SAME
    `all_bindings()` read the lane names come from -- `session_bindings.turn_open_at` -- so the
    leg costs one binding read and the two facts cannot disagree about which sessions exist.

    A read that fails returns an EMPTY map rather than raising. That makes every session read
    as "no turn in flight", which WITHHOLDS the driven claim and lets the goal-row test decide:
    the honest direction, because a binding store this read could not open must not be able to
    declare a lane driven.
    """
    try:
        registry = load_module("oc_registry", REGISTRY)
        bindings, _errors = registry.all_bindings()
    except Exception:
        return {}
    open_turns: dict[str, bool] = {}
    for row in bindings:
        session_id = str(row.get("session_id") or "")
        if not session_id or session_id in open_turns:
            continue
        open_turns[session_id] = bool(row.get("turn_open_at"))
    return open_turns

def driverless_leg(
    census: dict,
    *,
    goals: dict,
    read_at: str,
    lane_names_fn=None,
    lane_turn_open_fn=None,
    lane_activity_fn,
    threshold_days: float = STALL_CENSUS_THRESHOLD_DAYS,
    now: dt.datetime | None = None,
) -> dict:
    """Does a lane carrying an UNCLAIMED BACKLOG have a driver at all? (#133)

    The stall census names units; this leg names the LANE STATE behind them. A lane with
    eleven dispatched-and-never-claimed units and no convergence loop running is not eleven
    problems, it is one: nobody is driving that lane, and every re-dispatch aimed at it lands
    in the same queue. That distinction is the whole reason this leg exists, and it is
    invisible to every other leg -- the census reds the units, the pacemaker leg asks whether
    a cron wakes the session, and NEITHER asks whether the woken session has a goal to
    converge on.

    THE POPULATION IS THE CENSUS'S OWN GROUPING, never a second read of the routing. It comes
    from `census["coverage"]["owed_by_lane"]`, which the census built from the same declared
    routing its OWED lines name, so the two legs cannot disagree about which lane a unit sits
    on. A census that did not run (or ran NOT RUN) yields an EMPTY population and this leg
    says so in words -- it never reads that as a clean bill.

    DETECT ONLY. This leg NOTIFIES NOTHING and RE-ARMS NOTHING (#133): arming another lane's
    goal is that lane's act or its owner's, and a patrol that armed lanes would be inventing
    work rather than reporting it. The remedy sentence says exactly that, so a reader is never
    left thinking this leg did something about what it found. The FOURTH reading refuses the
    re-arm for a second reason (#532): a lane measured working inside the window is draining,
    and installing a driver on a running lane is this leg's own false positive.

    THE ACTIVITY FACT IS INJECTED, never a module global (#532): `lane_activity_fn` defaults to
    `box_lane_activity` for the live run and is patched in every probe, so a reading here can
    never be decided by this box's own `tool_executions`. The WINDOW is
    `STALL_CENSUS_THRESHOLD_DAYS` and not a constant of this leg's own: that one already means
    "the shortest interval in which a lane that intends to take a dispatched item would have
    claimed it", which is exactly the question the fourth reading asks, and it is PRINTED with
    its basis on every run.
    """
    coverage = census.get("coverage") or {}
    grouped = coverage.get("owed_by_lane")
    lanes: list[dict] = []
    problems: list[str] = []
    names = lane_names_fn() if lane_names_fn else {}
    # "a turn is in flight" is a BINDING fact, not a goal fact (the card's DRIVEN row admits
    # it even when the arm is inert), so it rides its own injected read. A read that fails
    # returns {} -- see `stall_lane_turn_open`, and note the direction it fails in.
    open_turns = (lane_turn_open_fn or stall_lane_turn_open)()
    # "was this session MEASURED doing anything" is the fact the leg was missing (#532), and
    # it rides the same injection discipline: a source that could not be read yields
    # UNREADABLE for every lane, never a zero.
    activity_store = lane_activity_fn()
    activity_readable = bool(activity_store.get("readable"))
    activity_epochs = activity_store.get("epochs") or {}
    activity_newest = activity_store.get("newest") or {}
    window_secs = float(threshold_days) * 86400.0
    now_epoch = (now or dt.datetime.now(dt.timezone.utc)).timestamp()

    def activity_for(session_ref: str) -> dict:
        """ONE session's activity fact, in the shape `driver_reading` decides on."""
        if not activity_readable:
            return {
                "state": LANE_ACTIVITY_UNREADABLE,
                "reason": str(activity_store.get("reason") or "the source gave no reason"),
            }
        epoch = activity_epochs.get(session_ref)
        if epoch is None:
            return {"state": LANE_ACTIVITY_NONE}
        age_secs = now_epoch - float(epoch)
        return {
            "state": LANE_ACTIVITY_READ,
            "instant": activity_newest.get(session_ref),
            "age_days": age_secs / 86400.0,
            "in_window": age_secs <= window_secs,
        }
    rows = goals.get("rows") or []
    by_session: dict[str, list[dict]] = {}
    for row in rows:
        by_session.setdefault(str(row.get("session_id") or ""), []).append(row)
    counts = {reading: 0 for reading in DRIVERLESS_READINGS}
    unresolved_lanes = 0
    backlog_units = 0
    if grouped is None:
        # NOT the same as "no lane has a backlog": the census never produced a grouping, so
        # this leg judged NOTHING and says so rather than reading green over an empty list.
        return {
            "name": "driverless-lane",
            "status": "NOT RUN",
            "problems": [],
            "excused": [],
            "coverage": {
                "reason": (
                    "the stall census produced no `owed_by_lane` grouping this round, so the "
                    "population this leg asks about does not exist -- an unasked question, "
                    "never a clean lane (board #133)"
                ),
                "census_status": census.get("status"),
                "read_at": read_at,
            },
        }
    for slot in grouped:
        session_ref = str(slot.get("session_ref") or "")
        units = list(slot.get("units") or [])
        backlog_units += len(units)
        if not session_ref:
            # The census already reds this unit's routing as UNRESOLVED; counting it here is
            # the honest population arithmetic, and re-redding it would be the same fact
            # reported twice under two names.
            unresolved_lanes += 1
            continue
        lane = slot.get("lane") or names.get(session_ref) or session_ref
        activity = activity_for(session_ref)
        reading, newest = driver_reading(
            by_session.get(session_ref, []),
            turn_open=bool(open_turns.get(session_ref)),
            activity=activity,
        )
        counts[reading] += 1
        state = str((newest or {}).get("state") or "")
        turns_used = (newest or {}).get("turns_used")
        lanes.append({
            "lane": lane,
            "session_ref": session_ref,
            "reading": reading,
            "turn_open": bool(open_turns.get(session_ref)),
            "state": state,
            "turns_used": turns_used,
            "updated_at": (newest or {}).get("updated_at"),
            # THE INSTANT THE FOURTH READING RESTS ON (#532), carried on the record so a
            # reader can tell "no work since T" from "not read" -- and PRINTED on every
            # UNARMED-ACTIVE and every DRIVERLESS line.
            "activity_state": activity.get("state"),
            "activity_instant": activity.get("instant"),
            "activity_age_days": activity.get("age_days"),
            "units": units,
            "oldest_age_days": slot.get("oldest_age_days"),
        })
        if reading == "DRIVEN":
            continue
        held = ", ".join(units[:6]) + (", ..." if len(units) > 6 else "")
        # THE ACTIVITY FACT IN WORDS, on every line that is not DRIVEN (#532): "no work since
        # T" and "not read" are different findings, and a line that omits the instant merges
        # them into one sentence a reader cannot act on.
        if activity.get("state") == LANE_ACTIVITY_READ:
            measured = (
                f"its newest measured tool execution is {activity.get('instant')} "
                f"({float(activity.get('age_days') or 0.0):.2f} d before this read)"
            )
        elif activity.get("state") == LANE_ACTIVITY_UNREADABLE:
            measured = "its activity could not be read at all"
        else:
            measured = "no tool execution for that session in any home this read reached"
        if reading == "UNREADABLE":
            detail = (
                f"the ACTIVITY source could not be read ({activity.get('reason')}), so this "
                f"line reports an UNREAD source and NOT an absent driver"
            )
        elif reading == "UNARMED-ACTIVE":
            detail = (
                f"it has NO active goal row, but it was MEASURED WORKING at "
                f"{activity.get('instant')} ({float(activity.get('age_days') or 0.0):.2f} d "
                f"before this read, inside the {float(threshold_days):.2f} d window), so it is "
                f"draining through a trigger this leg cannot see -- and a driver is not what "
                f"it lacks"
            )
        elif newest is None:
            detail = (
                "NO goal row for that session in any home this read reached, and "
                f"{measured}, so nothing was armed to drive it AND nothing was measured "
                "running"
            )
        elif reading == "ARMED-INERT":
            detail = (
                f"its goal row is `{state}` (turns used {turns_used}, last touched "
                f"{newest.get('updated_at')}), so the convergence loop EXISTS and has never "
                f"been evaluated -- an arm that has never run steers a turn that is not coming"
            )
        else:
            # A row EXISTS here and it is not active, so this branch must never claim "no goal
            # row": the row's own state is the finding, and printing an absence beside a row
            # that is sitting right there is the misreport this split exists to prevent.
            detail = (
                f"its newest goal row is `{state}` (turns used {turns_used}, last touched "
                f"{newest.get('updated_at')}), no turn is in flight, and {measured}, so it has "
                f"no goal-loop driver and no measured work since that instant -- a stopped "
                f"loop is not a driver, whatever it did before it stopped"
            )
        # THE REMEDY IS PER-READING (#532): the fourth reading refuses the re-arm for a reason
        # of its own, and printing #133's sentence on it would invite exactly the act the
        # ruling forbids.
        remedy = (
            "The ACT is NOT a re-arm: a lane measured working inside the window is draining, "
            "and installing a driver on a running lane is this leg's own false positive "
            "(board #532)"
            if reading == "UNARMED-ACTIVE"
            else (
                "The ACT is the lane's own or the sweep owner's: this leg detects and prints, "
                "and MUST NOT re-arm another lane's goal (board #133)"
            )
        )
        problems.append(
            f"{reading} LANE {lane}: {len(units)} unit(s) dispatched and NEVER CLAIMED "
            f"({held}; oldest {float(slot.get('oldest_age_days') or 0.0):.2f} d) while "
            f"{detail}. {remedy}"
        )
    return {
        "name": "driverless-lane",
        "status": "ASSERTED",
        "problems": problems,
        "excused": [],
        "coverage": {
            # THE POPULATION IS PRINTED WITH ITS ZEROS (#133): a round where no lane carries
            # a backlog and a round where the grouping was never read must not render alike.
            "lanes_with_backlog": len(grouped),
            "lanes_judged": len(lanes),
            "lanes_routing_unresolved": unresolved_lanes,
            "backlog_units": backlog_units,
            "driven": counts["DRIVEN"],
            "armed_inert": counts["ARMED-INERT"],
            "driverless": counts["DRIVERLESS"],
            "unarmed_active": counts["UNARMED-ACTIVE"],
            "unreadable": counts["UNREADABLE"],
            "readings": DRIVERLESS_READINGS,
            "lanes": lanes,
            "lanes_with_a_turn_in_flight": sum(
                1 for lane in lanes if lane["turn_open"]
            ),
            # THE WINDOW AND ITS BASIS PRINT ON EVERY RUN (#532, criterion 3): a reading that
            # says "inside the window" without naming the window is a claim a reader cannot
            # check, and this one is not this leg's own constant -- it is the census's.
            "activity_window_days": float(threshold_days),
            "activity_window_basis": STALL_CENSUS_THRESHOLD_BASIS,
            "activity_readable": activity_readable,
            "activity_reason": str(activity_store.get("reason") or ""),
            "activity_homes_read": list(activity_store.get("homes_read") or []),
            "activity_homes_without_store": list(
                activity_store.get("homes_without_store") or []
            ),
            "activity_homes_unreached": list(activity_store.get("unreached") or []),
            "activity_instants_unparsed": list(activity_store.get("unparsed") or []),
            "goal_rows_read": len(rows),
            "goal_homes_read": list(goals.get("homes_read") or []),
            "goal_homes_without_store": list(goals.get("homes_without_store") or []),
            "goal_homes_unreached": list(goals.get("unreached") or []),
            "read_at": read_at,
        },
    }

def board_unruled_leg(
    issues: list[dict],
    rows: list[dict],
    *,
    read_at: str,
    threshold_hours: float = BOARD_UNRULED_THRESHOLD_HOURS,
    predicate=None,
) -> dict:
    """Open board items carrying an `intake` row and NO `ruling` row, past the threshold.

    THE POPULATION IS THE ROUND'S OWN PREDICATE (#332, ruled at ledger n=2425). Population
    = board items the board calls OPEN, carrying an `intake` row, and carrying no `ruling`
    row that resolves to them. Nothing else in the patrol watches it: the intake leg's
    forward arm asserts the ROW side (an open item must have an intake row), and the ruling
    leg's population is "every board issue carrying a ruling COMMENT", so an item with no
    ruling row at all is outside both populations by construction.

    ITS OWN RESOLVER (#243). Two namespaces have to be resolved to answer this leg's own
    question, and each is BOUND to the leg that OWNS it rather than re-derived here:

      * the INTAKE namespace is the intake predicate's own `intaken_numbers` -- the same
        function `board_intake_leg` reads -- so the two legs cannot disagree about which
        item carries an intake row (the discipline `board_closed_leg` follows for
        `issue_reference`);
      * the RULING namespace is `resolve_ruling_issue`, whose three arms (strict,
        `governs=`, bridged) are the ruling leg's own vocabulary. A second copy here would
        drift from it and let one leg call an item ruled while the other calls it unruled
        -- a FALSE RED no reader could re-litigate.

    What is leg-local is the POPULATION and the VERDICT: this function composes the two
    namespaces into its own question, and it is the only place that question is answered.

    IT DETECTS AND PRINTS; IT ACTS ON NOTHING. The remedy for an item in the population is
    a ruling by the lane that owns the round, and this runner holds no session tool with
    which to reach it. The red is an andon cord with a working exit, not the no-exit class.

    AN EMPTY POPULATION IS PRINTED AS EMPTY, never as silence (acceptance criterion 2). The
    population count, the OPEN-item count and the board read instant all travel in
    `coverage` and are rendered on the leg's own line, so "examined 0, 0 problems" is
    distinguishable from a leg that examined nothing -- which is the whole reason #332 was
    filed: a skipped item reads clean.

    A ROW THAT RESOLVES TO NO ISSUE IS PRINTED, never silently dropped (#243 clause 2). An
    intake row with a descriptive subject names no issue and is not evidence about intake
    in either direction, so it is COUNTED as unresolved rather than folded into the
    population; a ruling row whose three arms all fail is LISTED, because dropping it would
    report a smaller ruled set than was read and fire on an item that is in fact ruled.
    """
    predicate = predicate or load_predicate()

    intaken = predicate.intaken_numbers(rows)
    open_numbers = predicate.open_issue_numbers(issues)
    by_n = {row.get("n"): row for row in rows if row.get("n") is not None}

    ruling_rows = 0
    resolved_rows = 0
    ruled: set[int] = set()
    arms = {"strict": 0, "declared": 0, "bridged": 0}
    unbridgeable: list[dict] = []
    # Named, never merely counted — the same attribution the board-ruling leg carries, so
    # the two legs cannot disagree about how a bridge was sourced (#551, ruling n=4157).
    bridges: list[dict] = []
    for row in rows:
        if str(row.get("event") or "") != "ruling":
            continue
        ruling_rows += 1
        number, arm, bridge = resolve_ruling_issue(row, rows, predicate)
        if number is None:
            unbridgeable.append(
                {"n": row.get("n"), "subject": str(row.get("subject") or "")}
            )
        else:
            ruled.add(number)
            # A ROW-RESOLVE, counted per row and never folded into `len(ruled)` (#545,
            # ruling n=4096): a re-ruling is the append-only ledger working, so one issue
            # number can be resolved many times. `rulings_resolved` stays DISTINCT because
            # it feeds the population predicate below; `rulings_resolved_rows` and
            # `rulings_repeated` name the bucket that the two numbers alone hide.
            resolved_rows += 1
            arms[arm] = arms.get(arm, 0) + 1
            if bridge is not None:
                bridges.append(
                    {
                        "issue": number,
                        "ruling_n": row.get("n"),
                        "via_n": bridge.get("n"),
                        "via_event": bridge.get("event"),
                    }
                )

    intake_rows_read = sum(
        1 for row in rows if str(row.get("event") or "") == "intake"
    )

    excused: list[str] = []
    population: list[dict] = []
    owed: list[dict] = []
    for number in sorted(open_numbers):
        if number not in intaken or number in ruled:
            continue
        intake_n = intaken[number]
        stamp = str((by_n.get(intake_n) or {}).get("ts") or "")
        try:
            entered = reader_parse_ts(stamp)
            now = reader_parse_ts(read_at)
        except (ValueError, TypeError):
            excused.append(
                f"#{number}: the intake row n={intake_n} records an instant this leg "
                f"cannot date ({stamp!r}), so its age cannot be measured -- NOT JUDGED"
            )
            continue
        age_hours = (now - entered).total_seconds() / 3600.0
        entry = {
            "issue": number,
            "intake_n": intake_n,
            "intake_ts": stamp,
            "age_hours": age_hours,
            "owed": age_hours >= threshold_hours,
        }
        population.append(entry)
        if entry["owed"]:
            owed.append(entry)

    population.sort(key=lambda entry: -entry["age_hours"])
    owed.sort(key=lambda entry: -entry["age_hours"])

    problems: list[str] = []
    for entry in owed:
        problems.append(
            f"#{entry['issue']} is OPEN on the board and carries intake "
            f"n={entry['intake_n']} at {entry['intake_ts']}, but the ledger holds NO "
            f"`ruling` row resolving to it -- unruled for {entry['age_hours']:.2f} h, past "
            f"the declared threshold of {threshold_hours:.1f} h (board read at {read_at}). "
            f"The HQ round's own predicate selects this item, so the round has passed over "
            f"it: rule it, or take it off the round's population on the board"
        )

    return {
        "name": "board-unruled",
        "status": "ASSERTED",
        "problems": problems,
        "excused": excused,
        "coverage": {
            "board_items_read": len(issues),
            "open_items_examined": len(open_numbers),
            "intake_rows_read": intake_rows_read,
            "intake_rows_resolved": len(intaken),
            "ruling_rows_read": ruling_rows,
            "rulings_resolved_rows": resolved_rows,
            "rulings_repeated": resolved_rows - len(ruled),
            "rulings_resolved": len(ruled),
            "rulings_unbridgeable": len(unbridgeable),
            "unbridgeable_rows": unbridgeable,
            "resolution_arms": arms,
            "bridged_via": bridges,
            "population_unruled": len(population),
            "items_owed_ruling": len(owed),
            "owed": [entry["issue"] for entry in owed],
            "population": population,
            "threshold_hours": threshold_hours,
            "threshold_basis": BOARD_UNRULED_THRESHOLD_BASIS,
            "board_read_at": read_at,
        },
    }

# --- the undispatched-ruling leg (#519) ---------------------------------------
#
# WHY THE CENSUS IS BLIND HERE, and it is the reason this leg exists at all.
# `stall_census_leg`'s admission ticket is a DISPATCH row: a unit enters that population
# only once a row of event `dispatch` names it. So a unit whose routing happened as a BATCH
# ACT — one `run` receipt, a partition of per-lane route files, and a hundred-odd findings
# fanned out by notify — is invisible to the leg that exists to find stalled work, and it
# stays invisible however long it sits. A leg whose admission ticket is the very artifact
# it is looking for can only ever report the units that already have one (#519, ruling
# n=3864). This leg therefore takes its population from the OTHER end: ruled, open, and
# unclaimed, whatever the dispatch rows say.
#
# THE BATCH RESOLUTION IS DECLARED, NEVER INFERRED. A batch act's finding->issue linkage is
# prose-only (the cycle's `codification_plan` carries no issue field; its route files name
# findings by lens and F-number), so a leg that resolved units by matching a finding string
# against an issue title would be guessing with a join's clothes on — and a wrong resolution
# here silently excuses a real debt. The units are read from
# `docs/ledger-invariants.json`'s `dispatch_batches`, through the one shared reader, and a
# tree that has declared nothing gets the honest answer: nothing in it says these units were
# dispatched, so the red is TRUE.
#
# IT REPORTS AND IT REPAIRS NOTHING (clause 3). A leg that resolved its own population
# cannot report it. The disposition of an owed unit — re-dispatch, close as superseded, or
# park — belongs to the lane that owns the round, and this runner holds no tool with which
# to reach it.
#
# EVERY BUCKET PRINTS ITS OWN PREDICATE, so "no owed units" and "a bucket that cannot see
# one" never render the same (#163 half 2 (b)). A MENTION IS NOT A DISPATCH (#467): a unit
# named only inside a dispatch row's body is COUNTED AND PRINTED in its own bucket, never
# folded into the dispatched population and never re-filed as debt — the ruling separates
# that class from the owed one, and a leg that reds on a mention re-reds on the same units
# forever.

_DECLARATION_READER = None

def declaration_reader():
    """`tools/ledger_declaration.py`, loaded ONCE and cached.

    Loaded by PATH through the same accessor every other cross-tool read here uses, so
    there is exactly one way to reach it. Cached because `load_module` RE-EXECUTES on
    every call and this runner reaches it once per patrol.
    """
    global _DECLARATION_READER
    if _DECLARATION_READER is None:
        _DECLARATION_READER = load_module("ledger_declaration", LEDGER_DECLARATION)
    return _DECLARATION_READER

def undispatched_batches_fn(repo: Path | None = None) -> dict:
    """`{"batches": ..., "batch_refusal": ...}` — the declared batch record, or its refusal.

    The leg takes these as KEYWORD ARGUMENTS rather than reading the declaration itself, so
    a probe never has its verdict decided by whichever batches the live factory happens to
    have declared. This function is the LIVE default for that injection.

    The two failure modes are mapped apart, and the split is the point. ABSENT is a
    legitimate state — a factory that has never run a batch act has declared none — so it
    resolves NOTHING and says so in `batch_refusal`, which the leg prints. MALFORMED is a
    DEFECT in a declaration that exists, and it also resolves nothing, but it must never
    read as "no batches exist": an empty map is the absent declaration wearing a key, and
    excusing a population on it is the act the declaration's own reader refuses.

    A zero must never stand in for "could not look" (#271): both arms return an empty
    `batches` map WITH the reason attached, never a bare `{}`.
    """
    reader = declaration_reader()
    try:
        batches = reader.load_dispatch_batches(repo if repo is not None else REPO)
    except reader.DeclarationUnavailable as exc:
        return {"batches": {}, "batch_refusal": f"ABSENT: {exc}"}
    except reader.DeclarationUnreadable as exc:
        return {"batches": {}, "batch_refusal": f"UNREADABLE: {exc}"}
    return {"batches": batches, "batch_refusal": ""}

def undispatched_ruling_leg(issues: list[dict], rows: list[dict], *, read_at: str,
                            predicate=None, batches: dict | None = None,
                            batch_refusal: str = "") -> dict:
    """OPEN board items carrying a `ruling` row and NO `dispatch` row naming them (#519).

    Population: every item the board calls OPEN, that carries a `ruling` row resolving to
    it, and that carries no `claim` and no `close` row — the work is ruled, not started, and
    not done. That is the state a dispatch is owed in. Each member is then placed in exactly
    one bucket, and the three predicates are disjoint by construction:

      * `named_in_subject` — a dispatch row's SUBJECT resolves to it: dispatched, and
        outside the reported population entirely.
      * `named_in_body_only` — a dispatch row's BODY carries the token while no subject
        does. Printed as the #467 mention class with its own predicate; a mention is not a
        dispatch, and it is not this leg's debt either.
      * `resolved_by_batch` — a declared batch record names it: EXCUSED, with the batch row
        and the declaration instant printed, because a batch act is a dispatch that happened.
      * `owed_dispatch` — named by nothing and declared by no batch: the PROBLEM.

    `batches` is injected so a probe never reads the live declaration, and `batch_refusal`
    carries an unreadable-or-absent declaration's own reason so a population resolved on no
    declaration is VISIBLE as such rather than silently treated as "no batches exist".
    """
    predicate = predicate or load_predicate()
    open_numbers = predicate.open_issue_numbers(issues)

    ruled: set[int] = set()
    ruling_rows_read = 0
    resolved_rows = 0
    unbridgeable_rows = 0
    for row in rows:
        if str(row.get("event") or "") != "ruling":
            continue
        ruling_rows_read += 1
        number, _arm, _bridge = resolve_ruling_issue(row, rows, predicate)
        if number is not None:
            ruled.add(number)
            resolved_rows += 1
        else:
            unbridgeable_rows += 1

    # The two rows that take a unit OUT of the owed state: work started, or work done.
    started: set[int] = set()
    done: set[int] = set()
    for row in rows:
        event = str(row.get("event") or "")
        if event not in ("claim", "close"):
            continue
        number = issue_from_row(row, predicate)
        if number is None:
            continue
        (started if event == "claim" else done).add(number)

    # The dispatch rows, split by WHERE the token sits: a header NAMES its subject (#433),
    # a body merely discusses it.
    in_subject: set[int] = set()
    in_body_only: dict[int, dict] = {}
    dispatch_rows_read = 0
    for row in rows:
        if str(row.get("event") or "") != "dispatch":
            continue
        dispatch_rows_read += 1
        own = issue_from_row(row, predicate)
        if own is not None:
            in_subject.add(own)
        detail = str(row.get("detail") or "")
        for number in sorted(open_numbers):
            if number in in_subject:
                continue
            if delivery_subject_matches(detail, f"#{number}"):
                in_body_only.setdefault(number, {
                    "issue": number,
                    "dispatch_n": row.get("n"),
                    "dispatch_subject": str(row.get("subject") or ""),
                })

    declared: dict[int, dict] = {}
    for slug, entry in (batches or {}).items():
        for number in entry.get("units") or []:
            declared.setdefault(int(number), {
                "issue": int(number),
                "batch": slug,
                "batch_row": entry.get("row"),
                "declared_at": str(entry.get("recorded_at") or ""),
            })

    population: list[int] = sorted(
        n for n in open_numbers
        if n in ruled and n not in started and n not in done and n not in in_subject
    )
    owed: list[dict] = []
    excused_batch: list[dict] = []
    mentioned: list[dict] = []
    for number in population:
        if number in declared:
            excused_batch.append(declared[number])
        elif number in in_body_only:
            mentioned.append(in_body_only[number])
        else:
            owed.append({"issue": number})

    problems: list[str] = []
    for entry in owed:
        problems.append(
            f"#{entry['issue']} is OPEN on the board and carries a `ruling` row, and no "
            f"`dispatch` row names it in its subject, and no declared batch resolves it "
            f"(board read at {read_at}) — the ruling asserts a routing that no row "
            f"corroborates. Dispatch it, or close it as superseded WITH the evidence"
        )

    excused: list[str] = []
    for entry in excused_batch:
        excused.append(
            f"#{entry['issue']}: resolved by declared batch `{entry['batch']}` "
            f"(ledger n={entry['batch_row']}, declared {entry['declared_at'] or 'undated'}) "
            f"— a batch act is a dispatch that happened, and NO BACKFILL bars the per-item "
            f"row"
        )
    for entry in mentioned:
        excused.append(
            f"#{entry['issue']}: named only inside dispatch n={entry['dispatch_n']}'s BODY "
            f"({entry['dispatch_subject']!r}) — a MENTION is not a dispatch (#467), and it "
            f"is not this leg's debt either"
        )

    return {
        "name": "undispatched-ruling",
        "status": "ASSERTED",
        "problems": problems,
        "excused": excused,
        "coverage": {
            "board_items_read": len(issues),
            "open_items_examined": len(open_numbers),
            "ruling_rows_read": ruling_rows_read,
            "rulings_resolved_rows": resolved_rows,
            "rulings_repeated": resolved_rows - len(ruled),
            "rulings_unbridgeable": unbridgeable_rows,
            "rulings_resolved": len(ruled),
            "dispatch_rows_read": dispatch_rows_read,
            "claims_read": len(started),
            "closes_read": len(done),
            "population_undispatched": len(population),
            "items_owed_dispatch": len(owed),
            "owed": [entry["issue"] for entry in owed],
            "items_named_in_body_only": len(mentioned),
            "named_in_body_only": mentioned,
            "items_resolved_by_batch": len(excused_batch),
            "resolved_by_batch": excused_batch,
            "batch_refusal": batch_refusal,
            "population_predicate": (
                "OPEN on the board, carries a `ruling` row resolving to it, carries no "
                "`claim` and no `close` row, and no `dispatch` row resolves to it by subject"
            ),
            "mention_predicate": (
                "the unit's token appears in a dispatch row's DETAIL while no dispatch row's "
                "SUBJECT resolves to it — printed, never counted as a dispatch (#467)"
            ),
            "batch_predicate": (
                "the unit is named in `dispatch_batches` in docs/ledger-invariants.json, the "
                "declared record of a batch act whose per-item rows NO BACKFILL bars"
            ),
            "board_read_at": read_at,
        },
    }

# A PATH a criterion NAMES, in backticks: the shape `docs/measurement-procedure.md`,
# `tests/test_x.py`, `tools/y.py`, `tools/questions`. A criterion names its artefact this
# way, and the class (#48) is a name that resolves to nothing.
CRITERION_PATH_REF = re.compile(
    r"`((?:TEMPLATE/)?(?:tests|tools|docs|skills|evidence|registry)/[A-Za-z0-9_./-]+)`"
)

# ... but a backticked token is not a PATH merely because a mechanism directory roots it.
# Four shapes look like one and are not, each measured on this board (2026-10-06):
#
#   `docs/...`                                  an ellipsis standing for "the docs"
#   `registry/topics/`                          a DIRECTORY, and a directory is not a file
#   `tools/field_predicate.split_canonical_run` a dotted ATTRIBUTE, not a file
#   `evidence/.ledger.lock`                     a transient lock file, never committed
#
# Judging those four would have put four false findings on the board for every true one, so
# the basename must be FILE-SHAPED: a KNOWN extension, or a bare name carrying no dot at all
# (the `tools/questions` shape — the executable the kit ships without an extension, and the
# ruling's own measured instance, so a bare name is judged rather than dropped).
MECHANISM_SUFFIXES = frozenset({
    ".py", ".md", ".json", ".jsonl", ".mjs", ".js", ".sh", ".tmpl", ".txt",
    ".toml", ".yaml", ".yml", ".cfg", ".sql", ".html", ".css", ".rs", ".example",
})

def is_mechanism_path(ref: str) -> bool:
    """Is this backticked token a FILE an obligation can be checked against?

    The predicate is stated separately from the regex because the regex answers a different
    question — "is this token ROOTED at a mechanism directory" — and the two were conflated
    in the first draft, which reported a placeholder (`docs/...`), a directory
    (`registry/topics/`) and an attribute chain (`tools/x.y`) as absent mechanisms. A gate
    whose findings are mostly artefacts of its own predicate is a gate nothing can act on.
    """
    if ref.endswith("/"):
        return False
    base = ref.rsplit("/", 1)[-1]
    if not base:
        return False
    if "." not in base:
        return True
    return base[base.rindex("."):] in MECHANISM_SUFFIXES

# A backticked mechanism path is not a CRITERION merely because it appears on a criterion
# surface (#541). Two shapes QUOTE a path without obliging anything, both measured on #540's
# own body at 2026-10-22T00:40:00Z:
#
#   a FENCED BLOCK or BLOCKQUOTE     the patrol's own output, quoted as evidence
#   a TABLE CELL that is a bare path  a report's own table row, measuring rather than obliging
#   a sentence naming ANOTHER #NNN   "`TEMPLATE/tests/test_audit_cadence.py` is parked on the
#                                    owner design gate" — #324's obligation, not this item's
#
# THE SHAPE SET IS CLOSED AT THREE plus attribution (ruling n=4056), and the closure IS the
# recurrence guard: an unnamed shape must surface as a PROBLEM, loudly, in the same place real
# debt appears, rather than being silently excused. So a token in BARE PROSE stays judged even
# when a human can tell it was meant as an example — "the author obviously meant an example" is
# the fifth specimen of the #99/#247/#278/#476 cycle, each time one specimen after the fix, each
# time by adding vocabulary for the shape that had just bitten. The remedy for such a specimen
# belongs at the SOURCE: mark it as a quote, and the law already recognises the marking.
#
# Judging those put two already-routed units' paths on a third unit's account, and worse:
# filing a report that QUOTED a dead exemption REVIVED it, because a quoted path counted as a
# live absence — a dead-debt verdict controlled by whichever report happens to be open. So the
# predicate is stated here, once, rather than patched at the finding.
CRITERION_PATH_FENCE = re.compile(r"^\s{0,3}(?:```|~~~)")
CRITERION_PATH_QUOTE = re.compile(r"^\s{0,3}>")
# A TABLE ROW is a cell boundary, not a quotation: the branch below asks whether a cell's
# content is a bare path token, so `| as committed | 5 | **2** — ... |` cites its paths and
# `Done when `x` exists |` does not.
CRITERION_PATH_TABLE = re.compile(r"^\s{0,3}\|")
ISSUE_NUMBER_REF = re.compile(r"#(\d+)")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

def criterion_path_citations(text: str, number: int) -> dict[str, str | None]:
    """`{ref: citation reason or None}` for ONE criterion surface of issue `number` (#541).

    `None` means the token is a CRITERION and must be judged. A string means every occurrence
    of that token on this surface is a CITATION, and the string is the reason to PRINT — an
    excuse nobody can read is how a wrong excuse hides, which is the rule the exemption store
    already learned and this leg inherits.

    THE NAMED OCCURRENCE WINS. A path quoted in a fence and ALSO named as a criterion on the
    same surface is judged, because one obligation is enough; so the map is keyed per token
    and its value is `None` when ANY occurrence is a criterion.

    THE POPULATION'S SIZE DOES NOT SHRINK. The caller counts a cited token exactly as it
    counts a judged one and prints it as `cited:`, so a leg that simply dropped every token
    would read as a smaller population rather than as a cleaner one — and #519 clause 3
    forbids repairing the population instead of the predicate.

    The two shapes are the ruling's (n=4050), not a heuristic: a fence or blockquote is quoted
    instrument output, and a sentence naming a DIFFERENT `#NNN` attributes its paths to that
    item. A lexical blacklist was refused because two of the four measured phantom tokens sit
    in ordinary prose, and this class has already failed that way four times
    (#99, #247, #278, #476).
    """
    occurrences: dict[str, list[str | None]] = {}
    in_fence = False
    for line in text.splitlines():
        if CRITERION_PATH_FENCE.match(line):
            in_fence = not in_fence
            continue
        refs = CRITERION_PATH_REF.findall(line)
        if not refs:
            continue
        if in_fence:
            for ref in refs:
                occurrences.setdefault(ref, []).append("quoted inside a fenced block")
            continue
        if CRITERION_PATH_QUOTE.match(line):
            for ref in refs:
                occurrences.setdefault(ref, []).append("quoted inside a blockquote")
            continue
        if CRITERION_PATH_TABLE.match(line):
            # A table row cites the paths in cells that hold LITTLE ELSE, and judges the ones
            # in a cell that carries prose — so the discriminator is the CELL's own content,
            # not the presence of a `|` on the line. A branch that cited every line holding a
            # pipe would pass this arm and fail the bare-prose one, which is the control.
            for cell in line.split("|"):
                content = cell.strip()
                for ref in CRITERION_PATH_REF.findall(content):
                    rest = CRITERION_PATH_REF.sub("", content)
                    rest = re.sub(r"[\s`*_—–\-:,.()\[\]\d]+", "", rest)
                    occurrences.setdefault(ref, []).append(
                        "quoted inside a table cell" if not rest else None
                    )
            continue
        for sentence in SENTENCE_SPLIT.split(line):
            sentence_refs = CRITERION_PATH_REF.findall(sentence)
            if not sentence_refs:
                continue
            others = sorted({
                found for found in ISSUE_NUMBER_REF.findall(sentence) if int(found) != number
            })
            if others:
                reason = f"attributed to #{', #'.join(others)}"
                for ref in sentence_refs:
                    occurrences.setdefault(ref, []).append(reason)
            else:
                for ref in sentence_refs:
                    occurrences.setdefault(ref, []).append(None)
    return {
        ref: (reasons[0] if all(reason is not None for reason in reasons) else None)
        for ref, reasons in occurrences.items()
    }

def committed_tree_rev(repo: Path, rev: str = "HEAD") -> tuple[str | None, str]:
    """Resolve `rev` to a COMMIT in `repo`, or the reason it cannot be read (#450, template-instruments.md §7.5).

    Returns `(sha, why)`: `why` is empty only when `sha` is a commit. A tree that cannot be
    read and a tree that holds nothing are different facts, and a leg that conflated them
    would report a broken checkout as a board full of missing files — the confident zero,
    inverted. `--verify --quiet` keeps a non-repo and a missing revision on the same
    non-zero path so the caller gets a reason rather than a traceback.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"git rev-parse {rev} could not run in {repo}: {exc}"
    sha = (proc.stdout or "").strip()
    if proc.returncode != 0 or not sha:
        detail = (proc.stderr or "").strip().splitlines()
        return None, (f"`{repo}` resolves no commit at {rev}"
                      + (f" ({detail[-1]})" if detail else ""))
    return sha, ""

def committed_path_present(ref: str, *, repo: Path, rev: str) -> tuple[bool, str]:
    """Whether the COMMITTED tree at `rev` holds `ref`, and WHY NOT when the probe failed.

    The read is `git cat-file -e <rev>:<ref>` — the tree the commit records, never the
    working tree a checkout happens to hold (`template-instruments.md:776` §7.5). `cat-file
    -e` answers for TREES as well as blobs, so a name that resolves to a directory reads
    present exactly as `Path.exists()` read it, and this change moves the SURFACE without
    moving the population.

    `why` is non-empty only when the probe could not run at all. That is a different fact
    from a path absent from the commit, and the caller must not read one as the other: the
    first is an instrument failure, the second is the finding this leg exists to report.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "cat-file", "-e", f"{rev}:{ref}"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"git cat-file -e {rev}:{ref} could not run: {exc}"
    return proc.returncode == 0, ""

CRITERION_PATH_EXEMPTIONS = REPO / "docs" / "criterion-path-exemptions.json"

def load_criterion_path_exemptions(
    path: Path | None = None,
) -> tuple[list[dict], list[str]]:
    """`(entries, problems)` for the declared criterion-path exemption surface (#507).

    THE SURFACE EXISTS BECAUSE A PATH CAN BE ABSENT BY LAW. `docs/hygiene-protected.json`
    never ships (`skills/meta-factory/SKILL.md:414`), so a criterion naming it is correct
    and the leg was wrong to red it — ruling n=2693 had already returned that half of #422
    as NOT UPHELD, which settles the declaration. The exemption is taken from the TREE's own
    declaration rather than from a list inside this script, because a list inside the script
    is a second copy of the law that goes stale silently.

    THE ADMISSION RULE IS AN AUTHORITY OBLIGATION. An entry carries `path` (the exact
    backticked token a criterion names), optional `issue` narrowing it to one board item,
    and REQUIRED `authority` (a ruling row `n=` or a law file:line) plus `reason`: an
    exemption nobody can check is forgiveness. Malformed and DUPLICATE entries are problems,
    and an absent file is the shipped state of a new factory (`docs/kit-exemptions.json`
    convention), never a failure.
    """
    target = path or CRITERION_PATH_EXEMPTIONS
    if not target.is_file():
        return [], []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], [
            f"{target.name} could not be read ({type(exc).__name__}), so no declared "
            f"exemption can be honoured and every absent path is a finding"
        ]
    rows = data.get("exempt") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return [], [
            f"{target.name} declares no `exempt` list, so no exemption can be honoured"
        ]
    out: list[dict] = []
    problems: list[str] = []
    seen: set[tuple[str, int | None]] = set()
    for index, entry in enumerate(rows):
        if not isinstance(entry, dict):
            problems.append(
                f"{target.name} entry {index} is not an object, so it can excuse nothing"
            )
            continue
        ref = str(entry.get("path") or "").strip()
        issue = entry.get("issue")
        authority = str(entry.get("authority") or "").strip()
        reason = str(entry.get("reason") or "").strip()
        if not ref:
            problems.append(
                f"{target.name} entry {index} names no `path`, so it can excuse nothing"
            )
            continue
        if issue is not None and (not isinstance(issue, int) or isinstance(issue, bool)):
            problems.append(
                f"{target.name} entry {index} (`{ref}`) carries a non-integer `issue`, so "
                f"its narrowing is unreadable"
            )
            continue
        if not authority:
            problems.append(
                f"{target.name} entry {index} (`{ref}`) carries no `authority` -- an "
                f"exemption nobody can check is forgiveness"
            )
            continue
        if not reason:
            problems.append(
                f"{target.name} entry {index} (`{ref}`) carries no `reason` -- an exemption "
                f"nobody explained belongs to nobody"
            )
            continue
        key = (ref, issue if isinstance(issue, int) else None)
        if key in seen:
            problems.append(
                f"{target.name} entry {index} duplicates (`{ref}`, issue {key[1]}) -- a "
                f"second copy of one exemption reads as two"
            )
            continue
        seen.add(key)
        out.append({"path": ref, "issue": key[1],
                    "authority": authority, "reason": reason})
    return out, problems

def criterion_path_leg(issues: list[dict], *, read_at: str,
                       repo: Path = REPO, rev: str = "HEAD",
                       exemptions_path: Path | None = None) -> dict:
    """Resolve the paths a board item's CRITERIA name (#48, ruling criterion 3/4).

    Candidate 1 closes the law-surface half and cannot reach two surfaces, because neither
    is in a commit: a BOARD ISSUE BODY and a SESSION PLAN. Measured instance: `#172`'s
    acceptance criterion named `tools/questions`, which resolves nowhere (the instrument
    ships only at `TEMPLATE/tools/questions`); `#96`'s plan criterion named a test file that
    existed under no revision. The patrol already reads the board, so this leg resolves the
    paths a criterion names and reports EACH as a finding naming the path and the criterion
    that named it — never as a bare count, so Triage can dispatch it as a work item (the
    `#148` discipline: a finding that cannot be dispatched is not a finding).

    WHICH SURFACES ARE READ, and why exactly these two. A criterion is a statement of what
    must be true for the item to be done, and on this board it lives in two places: the
    issue BODY (the item's own statement) and the RULING COMMENT (HQ's acceptance contract,
    which is where the numbered criteria sit — this item's own five are one). A close
    comment, a discussion comment and a correction block are HISTORY: they narrate what
    happened rather than obliging anything, and judging them measured 1696 refs and 67
    findings against 227 and 18 here — the extra 49 being chatter, not obligations. So the
    ruling surface is read through the SHARED `ruling_comments` predicate, never a private
    copy of it, exactly as the `board-ruling` leg binds to it.

    WHICH ITEMS, and why the harm bounds it. Only an OPEN item can still send a lane at a
    missing file, and that is the whole harm this class names: `#172`'s criterion was caught
    because Triage read it BEFORE dispatching. A closed item's obligation is discharged or
    abandoned and can send nobody anywhere, so the closed population is EXCLUDED and its
    count is PRINTED rather than silently dropped.

    The population is PRINTED (`refs_examined`), so a leg that read nothing does not read as
    a leg that found everything clean. A path is judged against the COMMITTED TREE at the
    reading revision, never the working tree (#450, template-instruments.md §7.5): a criterion naming a path that
    exists only on someone's disk — a gitignored receipt, an untracked scratch file — is
    unresolvable for EVERY reader, and that is what makes the verdict reproducible. The
    consequence is stated rather than hidden: since #445 moved the publish receipt to the
    git common dir, the refs naming `evidence/publish-receipt.json` read unresolved in every
    checkout, and that is TRUE — the path is not in the repository. A `TEMPLATE/`-prefixed
    name is resolved as the shipped twin, which is how the law writes it.

    A tree that cannot be read is NOT RUN with its reason, never a clean sweep: an
    instrument that failed has judged nothing, and reading every path ABSENT because git
    could not run would put a board's worth of false findings on the record.
    """
    commit, why = committed_tree_rev(repo, rev)
    if commit is None:
        return {
            "name": "criterion-paths",
            "status": "NOT RUN",
            "problems": [],
            "excused": [],
            "cited": [],
            "coverage": {
                "reason": (
                    f"the reading revision could not be resolved, so no criterion path was "
                    f"judged: {why} — a path is judged against the COMMITTED tree (#450, "
                    f"template-instruments.md §7.5), and a tree that cannot be read has judged nothing"
                ),
                "repo": str(repo),
                "rev": rev,
                "read_at": read_at,
            },
        }
    examined = 0
    unreadable: list[str] = []
    open_items = 0
    closed_items = 0
    absences: list[dict] = []
    cited: list[dict] = []
    for issue in issues:
        number = issue.get("number")
        if number is None:
            continue
        if issue.get("state") != "OPEN":
            closed_items += 1
            continue
        open_items += 1
        surfaces = [("body", issue.get("body") or "")]
        for comment in ruling_comments(issue):
            surfaces.append(("ruling comment", comment.get("body") or ""))
        for where, text in surfaces:
            # The ATTRIBUTION test (#541): a token quoted in a fence or a blockquote, or named
            # in a sentence that attributes it to ANOTHER item, is a CITATION — examined and
            # printed, never judged and never dropped.
            for ref, citation in sorted(criterion_path_citations(text, number).items()):
                if not is_mechanism_path(ref):
                    continue
                examined += 1
                if citation is not None:
                    cited.append({"issue": number, "where": where, "ref": ref, "why": citation})
                    continue
                present, why = committed_path_present(ref, repo=repo, rev=commit)
                if why:
                    unreadable.append(f"`{ref}`: {why}")
                    continue
                if present:
                    continue
                absences.append({"issue": number, "where": where, "ref": ref})
    if unreadable:
        # A PARTIAL READ IS NOT A MEASUREMENT (template-instruments.md §7.5): if any path could not be probed, the
        # leg's count is a figure no reader can reproduce, so the whole verdict is NOT RUN
        # over the reason rather than a short population wearing a clean one's name.
        return {
            "name": "criterion-paths",
            "status": "NOT RUN",
            "problems": [],
            "excused": [],
            "cited": [],
            "coverage": {
                "reason": (
                    f"{len(unreadable)} of {examined} reference(s) could not be probed "
                    f"against the reading commit {commit[:12]}: "
                    f"{'; '.join(unreadable[:3])}"
                ),
                "repo": str(repo),
                "rev": rev,
                "read_rev": commit,
                "refs_examined": examined,
                "read_at": read_at,
            },
        }
    # THE DECLARED EXEMPTION SURFACE (#507). A path can be ABSENT BY LAW rather than absent
    # by neglect — `docs/hygiene-protected.json` never ships (skills/meta-factory/SKILL.md:414),
    # and ruling n=2693 had already returned that half of #422 as NOT UPHELD, settling the
    # declaration and leaving this leg as the defect. The exemption is read from the TREE's own
    # declaration, never from a list inside this script: a list here would be a second copy of
    # the law that goes stale silently. Every matched entry PRINTS as an `excused:` line and is
    # counted in the population, so a green reads as examined-minus-exempt rather than as
    # examined-nothing; an entry matching NO live absence is itself a problem, because retired
    # debt must not sit here looking live.
    entries, store_problems = load_criterion_path_exemptions(exemptions_path)
    problems: list[str] = list(store_problems)
    excused: list[str] = []
    used: set[tuple[str, int | None]] = set()
    for absence in absences:
        number, ref = absence["issue"], absence["ref"]
        match = next(
            (e for e in entries
             if e["path"] == ref and (e["issue"] is None or e["issue"] == number)),
            None,
        )
        if match is None:
            problems.append(
                f"issue #{number} criterion ({absence['where']}) names `{ref}` — ABSENT at "
                f"{read_at}; dispatch a work item naming `{ref}`"
            )
            continue
        used.add((match["path"], match["issue"]))
        excused.append(
            f"issue #{number} criterion ({absence['where']}) names `{ref}`: DECLARED "
            f"ABSENT-BY-LAW -- {match['reason']} (authority: {match['authority']})"
        )
    for entry in entries:
        key = (entry["path"], entry["issue"])
        if key in used:
            continue
        narrowed = f" (issue #{entry['issue']})" if entry["issue"] is not None else ""
        problems.append(
            # The file NAMED is the one actually read, not the module default: a probe
            # injects its own store, and a finding that names the wrong file sends the
            # reader to edit a surface the run never opened.
            f"{(exemptions_path or CRITERION_PATH_EXEMPTIONS).name}: the exemption for "
            f"`{entry['path']}`{narrowed} matches no live absence, so it excuses nothing"
        )
    return {
        "name": "criterion-paths",
        "status": "ASSERTED",
        "problems": problems,
        "excused": excused,
        "cited": [
            f"issue #{item['issue']} criterion ({item['where']}) names `{item['ref']}` — CITED, "
            f"not a criterion: {item['why']}"
            for item in cited
        ],
        "coverage": {
            "refs_examined": examined,
            "issues_read": open_items,
            "closed_items_excluded": closed_items,
            "surfaces": ["body", "ruling comment"],
            "read_at": read_at,
            "absences": len(absences),
            "cited": len(cited),
            "declared_exempt": len(used),
            "unresolved": len(problems) - len(store_problems),
            "exemptions_declared": len(entries),
            # The revision the verdict is reproducible from (template-instruments.md §7.5): a reader re-derives the
            # same set from this commit alone, whatever their own checkout holds on disk.
            "read_rev": commit,
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

def member_root_probe(root: Path) -> tuple[bool, str]:
    """Whether a member's root is a readable directory, and WHY NOT when it is not.

    `Path.is_dir()` answers False for a root that is ABSENT, but it RE-RAISES when a
    PARENT of the root denies traversal, because EACCES is not among the errors pathlib
    ignores (#429). A member repo under a mode-700 home — a CI runner's `/root` — therefore
    raised straight out of `kit_drift_leg`, on the very leg whose job is to record that the
    member could not be read, and took the whole sweep with it. Measured in
    inferhub-watch run 37587867752 (Python 3.12.14, `pathlib.py:840`).

    A missing root and an unreadable one are BOTH unreachable, and both are recorded. The
    reason is what tells them apart, and they have different remedies: a stale `repo` in
    the fleet manifest versus a permissions problem on the member's box.

    The read is a PROBE, so the caller never sees the exception — an instrument that
    crashes on the input it exists to describe reports nothing about it.
    """
    try:
        if root.is_dir():
            return True, ""
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"
    return False, ""

def kit_drift_leg(
    *,
    manifest_path: Path | None = None,
    fleet_path: Path = FLEET_MANIFEST,
    bootstrap_named: tuple[str, ...] = BOOTSTRAP_NAMED,
    read_at: str = "",
) -> dict:
    """Per-member drift against `registry/kit.json`: same / DIFF / ABSENT, with names.

    A REPORT, not a verdict on the members, with ONE DECLARED EXCEPTION. `problems` carries
    this factory's own defects — a manifest or fleet file it cannot read, a manifest that
    describes no files, or no reachable member at all — because those are the
    examined-nothing cases. A member being stale is ORDINARILY a fact about THAT member,
    reported in `coverage` and acted on by the notify step; reddening this factory's patrol
    for it would make our verdict a function of another lane's backlog, which is the
    coupling the design exists to avoid.

    THE EXCEPTION IS THE `shared-surface` CLASS (#514, ruled at ledger n=3792). A file whose
    STORE is a box-wide surface is not a per-factory adoption choice: a superseded copy keeps
    WRITING that surface with old semantics, so the blast radius is every factory rather than
    that member. A DIFF cell for such a file is therefore a problem here, naming the member
    and the file. An ABSENT cell is NOT: a factory that does not carry the writer never
    writes the surface, which is the safe state, and it is printed as such rather than folded
    into a coverage count. The class comes from the manifest's own `classes` map — never from
    a heuristic over file content, which would be a second copy of the declaration.

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
    shared_totals = {"same": 0, "DIFF": 0, "ABSENT": 0}

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
    classes: dict[str, str] = manifest.get("classes") or {}
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
        is_reachable, why = member_root_probe(root)
        if not is_reachable:
            members.append({"slug": slug, "root": str(root), "reachable": False,
                            "reason": why,
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
        # MUST-ADOPT, NOT PER-FACTORY (#514). `diff_files` are MEMBER-relative paths, so the
        # manifest key is recovered through the pin's own `member_path` rather than by
        # re-deriving the prefix here -- one mapping, shared with the predicate that produced
        # the names.
        shared_map = {
            kit_pin.member_path(rel): rel
            for rel, cls in classes.items() if cls == SHARED_SURFACE_CLASS
        }
        shared_diff = sorted(p for p in diff_files if p in shared_map)
        shared_absent = sorted(p for p in absent_files if p in shared_map)
        shared_totals["DIFF"] += len(shared_diff)
        shared_totals["ABSENT"] += len(shared_absent)
        shared_totals["same"] += len(shared_map) - len(shared_diff) - len(shared_absent)
        for shared_path in shared_diff:
            problems.append(
                f"member `{slug}` carries a STALE SHARED-SURFACE writer: {shared_path} "
                f"({shared_map[shared_path]}) differs from the kit, and that file writes a "
                f"store every factory reads and writes — a superseded copy mutates state "
                f"another factory's law governs, so it is a problem here rather than a "
                f"coverage statistic (#514)"
            )
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
            # The class's own cells, so a reader can see the must-adopt population apart from
            # the per-factory one -- and can see an ABSENT shared-surface file as the SAFE
            # state it is rather than inferring it from a total.
            "shared_surface": {
                "same": len(shared_map) - len(shared_diff) - len(shared_absent),
                "diff": shared_diff,
                "absent": shared_absent,
            },
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
            # THE MUST-ADOPT POPULATION, reported apart from the per-factory one (#514). Its
            # DIFF cells are the leg's problems; its ABSENT cells are the safe state and are
            # counted so a reader can tell "no member carries it" from "no member was read".
            "shared_surface": {
                "class": SHARED_SURFACE_CLASS,
                "files": sorted(rel for rel, cls in classes.items()
                                if cls == SHARED_SURFACE_CLASS),
                "cells": dict(shared_totals),
            },
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


# ---------------------------------------------------------------------------
# #241 — THE SHARED TREE RIDER.
#
# The board legs read the shared tree, and a read taken while a peer lane was mid-write
# produced FALSE VERDICTS: measured at the filing, no single location gave a wholly
# correct read (ruling n=1696). What was ruled is a RULE — the shared tree is a READ
# surface, work happens in a worktree at origin/main — plus THIS cheap rider: the board
# legs print the blocking paths and the instant they were read, and print NOT RUN with
# its reason when the tree cannot be read.
#
# A RIDER, never a leg with a verdict of its own. A standalone detection leg was REFUSED
# as #83's class — a permanent report of a state nobody will fix — so this carries NO
# problem and NEVER moves the patrol's exit code. Its whole job is ATTRIBUTION: a reader
# who sees a board verdict can see the tree state it was taken against.
#
# "BLOCKING" is the ruling's own measured class rather than a new one: a path that is
# BOTH dirty in the shared tree AND moved by the base since that tree's HEAD — exactly
# the set that makes `git reset --keep <base>` refuse with `Entry <path> not uptodate`.
# It is REPORTED and never reconciled, because the ruling is explicit that the shared
# tree must NOT be reconciled first: a lane whose append is refused has its own remedy,
# a worktree.
# ---------------------------------------------------------------------------

SHARED_TREE_BASE = WORKTREE_BASE_REF
"""The ref a dirty path is judged against — the same base the ruling's deadlock used."""


def _git_read(repo: Path, args: list[str], *, timeout: int = 120) -> tuple[str | None, str | None]:
    """One read-only git call: `(stdout, None)` or `(None, reason)`.

    `GIT_OPTIONAL_LOCKS=0` for the reason `worktree_state` states: `git status` otherwise
    REFRESHES the index and takes `index.lock` in a tree a peer lane may be mid-task in,
    so a read-only census would be a writer on someone else's work. The reason is RETURNED
    rather than raised, so the caller renders a STATED INABILITY instead of a traceback.
    """
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, env=env, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"`git {' '.join(args)}` could not run: {exc}"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        return None, (
            f"`git {' '.join(args)}` exited {proc.returncode}"
            + (f" — {detail[0][:160]}" if detail else "")
        )
    return proc.stdout, None


def _status_z_paths(blob: str) -> list[str]:
    """Paths out of `git status --porcelain -z`, INCLUDING both sides of a rename.

    `-z` rather than the plain form because the plain form QUOTES a path carrying a
    special character, and a quoted path never intersects a plain one — so a blocking
    path would drop out of the report SILENTLY, which is the one failure mode this rider
    exists to prevent. Both sides of a rename are returned because either can block.
    """
    tokens = blob.split("\0")
    paths: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if len(token) < 4:
            continue
        status, path = token[:2], token[3:]
        if not path:
            continue
        paths.append(path)
        if "R" in status or "C" in status:
            if index < len(tokens) and tokens[index]:
                paths.append(tokens[index])
                index += 1
    return paths


def shared_tree_read(repo: Path = REPO, *, base: str = SHARED_TREE_BASE) -> dict:
    """The shared tree's dirty paths and the BLOCKING subset, read without writing.

    A failed read is REPORTED, never rendered as an empty one — and a ZERO blocking set is
    a verdict only from a WORKING comparison, so an unresolvable `base` (or a failed diff)
    is reported as UNKNOWN rather than folded into a silent zero.
    """
    out, error = _git_read(repo, ["status", "--porcelain", "-z"])
    if error:
        return {"status": "NOT RUN", "reason": error}
    dirty = _status_z_paths(out)

    rev, error = _git_read(
        repo, ["rev-parse", "--verify", f"{base}^{{commit}}"], timeout=60
    )
    if error:
        return {
            "status": "ASSERTED", "dirty": dirty, "blocking": None,
            "base": base, "base_sha": None,
            "reason": (
                f"the BLOCKING subset is UNKNOWN — {error}, so a dirty path cannot be "
                f"judged against the base that moved it"
            ),
        }
    base_sha = rev.strip()

    moved_out, error = _git_read(repo, ["diff", "--name-only", "-z", "HEAD", base_sha])
    if error:
        return {
            "status": "ASSERTED", "dirty": dirty, "blocking": None,
            "base": base, "base_sha": base_sha,
            "reason": f"the BLOCKING subset is UNKNOWN — {error}",
        }
    moved = {path for path in moved_out.split("\0") if path}
    return {
        "status": "ASSERTED",
        "dirty": dirty,
        "blocking": sorted({path for path in dirty if path in moved}),
        "base": base,
        "base_sha": base_sha,
        "reason": None,
    }


def shared_tree_rider(read_at: str, repo: Path = REPO, read_fn=None) -> dict:
    """The rider the board legs carry and the report prints once (#241).

    `read_fn` is injected for the reason every other leg here has one: a probe must drive
    all three renderings — blocking paths, an UNKNOWN comparison, NOT RUN — without the
    live box, and a rider that can only be driven against the live box cannot be probed at
    all when the live box is what is wrong.
    """
    state = (read_fn or shared_tree_read)(repo)
    if state.get("status") == "NOT RUN":
        return {
            "status": "NOT RUN",
            "reason": state.get("reason"),
            "read_at": read_at,
            "reconciles": False,
        }
    blocking = state.get("blocking")
    return {
        "status": "ASSERTED",
        "read_at": read_at,
        "base": state.get("base") or SHARED_TREE_BASE,
        "base_sha": state.get("base_sha"),
        "dirty": list(state.get("dirty") or []),
        "blocking": None if blocking is None else list(blocking),
        "reason": state.get("reason"),
        "reconciles": False,
    }


def render_shared_tree_rider(rider: dict) -> list[str]:
    """The rider's report lines: the blocking paths and the instant, or NOT RUN (#241).

    Every branch prints the instant, because a claim about a live tree is a claim about
    the INSTANT it was read — and an unreadable comparison prints UNKNOWN with its reason
    rather than an empty list, so a silent zero is not available to it.
    """
    head = "shared tree rider (qualifies the board legs below)"
    instant = rider.get("read_at") or "unstated"
    if rider.get("status") == "NOT RUN":
        return [
            f"{head} — NOT RUN: {rider.get('reason') or 'reason not stated'} "
            f"(read attempted at {instant})"
        ]
    lines = [f"{head} — read at {instant}"]
    dirty = rider.get("dirty") or []
    blocking = rider.get("blocking")
    if blocking is None:
        lines.append(
            f"  {len(dirty)} dirty path(s); BLOCKING: UNKNOWN — "
            f"{rider.get('reason') or 'reason not stated'}"
        )
    else:
        base = rider.get("base") or SHARED_TREE_BASE
        sha_text = f" {rider['base_sha']}" if rider.get("base_sha") else ""
        lines.append(
            f"  {len(dirty)} dirty path(s); {len(blocking)} BLOCKING (dirty AND moved by "
            f"{base}{sha_text}) — `git reset --keep {base}` refuses while these stand"
        )
        for path in blocking:
            lines.append(f"    ~ {path}")
    lines.append(
        "  REPORTED, never reconciled (reconciles: "
        f"{'yes' if rider.get('reconciles') else 'no'}) — a lane removes its OWN "
        "worktree's residue, and the shared tree is a READ surface (#241)"
    )
    return lines


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


# ---- the binding-freshness arm (issue #468, ruled at ledger n=3137) ------------------
#
# #79's gate owns RESOLUTION, offline: `test -L && test -d`, plus the forward leg that the
# declared source exists. The LIVE half -- that the profile entry still points at the
# declared source -- was explicitly DELEGATED to this patrol, because no offline gate can
# reach a surface outside the tree (`docs/harness-bindings.json` states that in its `_note`).
#
# RESOLUTION IS NOT FRESHNESS, and that is the defect this arm closes. A binding resolves
# perfectly and still serves STALE LAW. Measured first-hand 2026-10-16: the tree the ops
# profile loads stood 487 commits behind its own `origin/main` while `test -L && test -d`
# read GREEN -- and the #443 dispatch-composition clause was in force on `origin/main` and
# ABSENT from every lane's loaded text, which is why 5 of the 23 dispatches stamped since it
# landed named their unit only in the body, 4 of them the HQ lane's own. That recurrence is
# this class's SYMPTOM, not a discipline slip.
#
# THE PREDICATE IS A CONTENT HASH, NEVER A TIMESTAMP. A timestamp is disarmed by a rewrite of
# identical bytes -- an instrument error this factory has already logged -- so the comparison
# is sha256 over the bytes the profile LOADS (the resolved working tree) against the bytes at
# the reference. The REFERENCE travels with its own residual, printed rather than taken
# silently: the remote tip when its object is present in this store, else this checkout's
# `refs/remotes/origin/main`, which is a CACHE updated only by a fetch.
#
# NO NEW INSTRUMENT (#3137): this rides the leg that already asks the same question -- is
# what we serve the same as what we published -- and it is SKIPPED with a STATED reason when
# the repo declares no binding, so a factory that never adopted the manifest is never
# measured against one.

HARNESS_BINDINGS_REL = "docs/harness-bindings.json"
HARNESS_PROFILE_ROOT_ENV = "OC_HARNESS_PROFILE_ROOT"
HARNESS_LAW_BASENAME = "SKILL.md"
HARNESS_BINDING_FORMS = ("dir", "file")
BINDING_FRESHNESS_SCOPE = (
    "CONTENT only, per law file: the bytes the profile LOADS (the resolved tree) against "
    "the bytes at the reference. Never a timestamp and never a commit age -- a rewrite of "
    "identical bytes moves an mtime and changes no law."
)
BINDING_REFERENCE_RESIDUAL = (
    "the reference is the remote tip read from the REMOTE when its object is present in "
    "this store; otherwise this checkout's own `refs/remotes/origin/main`, which is a CACHE "
    "updated only by a fetch -- a lagging cache makes a stale loaded tree read level, which "
    "is why the reference used is PRINTED with every verdict"
)

def _git_bytes(repo: Path, args: list[str], *, timeout: int = 120) -> tuple[bytes | None, str | None]:
    """One read-only git call returning BYTES: `(stdout, None)` or `(None, reason)`.

    Bytes, not text, because the predicate is a CONTENT hash and a decode would make two
    different blobs hash alike (or raise) on any byte that is not valid UTF-8. Same
    `GIT_OPTIONAL_LOCKS=0` as `_git_read` and the same reason: a read must never take
    `index.lock` in a tree a peer lane is mid-task in.
    """
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, env=env, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"`git {' '.join(args)}` could not run: {exc}"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).decode("utf-8", "replace").strip().splitlines()
        return None, (
            f"`git {' '.join(args)}` exited {proc.returncode}"
            + (f" — {detail[0][:160]}" if detail else "")
        )
    return proc.stdout, None

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _git_toplevel(path: Path) -> tuple[Path | None, str | None]:
    out, err = _git_read(Path(path), ["rev-parse", "--show-toplevel"], timeout=60)
    if err:
        return None, err
    return Path(out.strip()), None

def _git_common_dir(path: Path) -> tuple[Path | None, str | None]:
    """The COMMON git dir, which is what makes two paths the same repository.

    Not `--show-toplevel`: under the worktree law a lane works in a worktree while the
    profile loads the SHARED tree, so two DIFFERENT paths are routinely the same repository
    -- comparing paths would red every worktree run for the one shape the law prescribes.
    """
    out, err = _git_read(Path(path), ["rev-parse", "--git-common-dir"], timeout=60)
    if err:
        return None, err
    raw = Path(out.strip())
    if not raw.is_absolute():
        raw = Path(path) / raw
    try:
        return raw.resolve(), None
    except OSError as exc:
        return None, f"{raw} could not be resolved: {exc}"

def _binding_profile_root(declaration: dict, explicit: Path | None) -> tuple[Path | None, str]:
    """`(profile_root, source)` -- explicit, then the env var, then the declared profile."""
    if explicit is not None:
        return Path(explicit), "explicit"
    env = os.environ.get(HARNESS_PROFILE_ROOT_ENV, "").strip()
    if env:
        return Path(env), f"{HARNESS_PROFILE_ROOT_ENV}"
    profile = str(declaration.get("profile") or "").strip()
    if not profile:
        return None, ""
    return Path.home() / ".opencrabs" / "profiles" / profile, "the declaration's `profile`"

def _binding_reference(repo: Path, tip: str | None) -> tuple[str | None, str, str]:
    """`(ref, source, reason)` for the bytes the loaded law is compared AGAINST.

    The remote tip first: it was read from the REMOTE this round, so it is the published
    fact rather than a local cache. It can only be used when its object is present in this
    store -- a checkout that never fetched does not hold it -- and then the fallback is the
    local ref, whose residual is printed rather than hidden.
    """
    if tip:
        _, err = _git_read(repo, ["cat-file", "-e", f"{tip}^{{commit}}"], timeout=60)
        if err is None:
            return tip, "the remote tip, read from the REMOTE this round", ""
    out, err = _git_read(
        repo, ["rev-parse", "--verify", f"{PUBLISH_REMOTE}/{PUBLISH_BRANCH}^{{commit}}"], timeout=60
    )
    if err:
        return None, "", (
            f"neither the remote tip nor {PUBLISH_REMOTE}/{PUBLISH_BRANCH} could be "
            f"resolved in this store: {err}"
        )
    return (
        out.strip(),
        f"this checkout's {PUBLISH_REMOTE}/{PUBLISH_BRANCH} (a CACHE, updated only by a fetch)",
        "",
    )

def binding_freshness_arm(
    *,
    repo: Path,
    profile_root: Path | None,
    declaration_path: Path,
    reference_ref: str | None,
    reference_source: str,
    reference_reason: str = "",
    read_at: str,
) -> tuple[list[str], dict]:
    """The law a profile LOADS, hashed against the law at the reference. `(problems, coverage)`.

    Two predicates, and they are NOT the same question (#468's own intake ruling): the entry
    must RESOLVE to the declared source of THIS repository, and the bytes it serves must
    MATCH the bytes at the reference. A binding can pass either and fail the other, so both
    are checked and each finding names which one broke.

    The population is per LAW FILE, not per binding: a binding serving eleven files where one
    is stale is one stale file, NAMED, and a count without the name cannot be dispatched.
    """
    coverage = {
        "declaration": str(declaration_path),
        "profile_root": None,
        "profile_root_source": "",
        "reference_ref": reference_ref,
        "reference_source": reference_source,
        "reference_residual": BINDING_REFERENCE_RESIDUAL,
        "scope": BINDING_FRESHNESS_SCOPE,
        "rows": [],
        "stale": [],
        "missing_local": [],
        "binding_reason": "",
    }
    problems: list[str] = []

    if not declaration_path.is_file():
        coverage["binding_reason"] = (
            f"{declaration_path} is absent, so this repo declares no binding to check -- a "
            f"factory carries the manifest only if it adopted it"
        )
        return problems, coverage

    try:
        declaration = json.loads(declaration_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"the binding declaration could not be read: {exc}")
        return problems, coverage

    root, source = _binding_profile_root(declaration, profile_root)
    if root is None:
        coverage["binding_reason"] = (
            f"no profile root: neither an explicit root, {HARNESS_PROFILE_ROOT_ENV}, nor a "
            f"`profile` in the declaration -- the live leg is NOT RUN rather than passed"
        )
        return problems, coverage
    coverage["profile_root"] = str(root)
    coverage["profile_root_source"] = source

    if not reference_ref:
        coverage["binding_reason"] = (
            f"no reference to compare against -- {reference_reason or 'unstated'}; an "
            f"unreadable reference is never a clean result"
        )
        problems.append(
            f"the binding-freshness arm has no `origin/main` to compare the loaded law "
            f"against: {reference_reason or 'the reference could not be resolved'}"
        )
        return problems, coverage

    rows = declaration.get("bindings")
    if not isinstance(rows, list):
        problems.append(f"{declaration_path} carries no `bindings` list")
        return problems, coverage

    skills_dir = root / "skills"
    for row in rows:
        if not isinstance(row, dict):
            problems.append(f"{declaration_path}: a binding row is not an object")
            continue
        skill = str(row.get("skill") or "").strip()
        repo_path = str(row.get("repo_path") or "").strip()
        form = row.get("form")
        entry: dict = {
            "skill": skill, "form": form, "repo_path": repo_path,
            "entry": "", "resolves_to": None, "resolution": "", "files": [], "stale": 0,
        }
        coverage["rows"].append(entry)

        if row.get("loaded") is False:
            entry["resolution"] = f"not bound (declared `loaded: false`: {row.get('reason') or 'no reason'})"
            continue
        if not skill or form not in HARNESS_BINDING_FORMS or not repo_path:
            entry["resolution"] = "unusable row"
            problems.append(
                f"{declaration_path}: a binding row is missing `skill`, `repo_path` or a "
                f"`form` in {HARNESS_BINDING_FORMS}"
            )
            continue

        # WHAT THE PROFILE LOADS: form `dir` -> `skills/<skill>`; form `file` ->
        # `skills/<skill>/SKILL.md`. The same shape gate P29's forward leg checks, so the
        # two never disagree about which entry is owed as the symlink.
        loaded = skills_dir / skill / HARNESS_LAW_BASENAME if form == "file" else skills_dir / skill
        entry["entry"] = str(loaded)

        if not loaded.is_symlink():
            entry["resolution"] = "NOT A SYMLINK"
            problems.append(
                f"{loaded} is not a symlink -- the profile must LOAD the law this repo "
                f"authors ({repo_path}), never carry a COPY of it (the copy-not-link class)"
            )
            continue
        try:
            resolved = loaded.resolve(strict=True)
        except OSError as exc:
            entry["resolution"] = "UNRESOLVABLE"
            problems.append(f"{loaded} is a symlink that does not resolve: {exc}")
            continue
        entry["resolves_to"] = str(resolved)

        top, err = _git_toplevel(resolved if resolved.is_dir() else resolved.parent)
        if err:
            # A path INSIDE this repository always reports a toplevel, so git's own "not a
            # git repository" is PROOF that the resolved target sits in no repository at all
            # -- and a target in no repository cannot be the declared source of THIS one.
            # That is the RESOLVES ELSEWHERE class, and it is decidable from the failure, so
            # it is not reported as an unreadable verdict. Every OTHER failure (git could not
            # run, a timeout, a refusal) stays UNREADABLE: a stated inability is never a
            # clean result, and it is never promoted to a class it cannot prove. Reaching
            # this loop at all means git works -- the reference was resolved through it
            # above, and a broken git returns before any row is read.
            if "not a git repository" in err:
                entry["resolution"] = "RESOLVES ELSEWHERE"
                problems.append(
                    f"{loaded} resolves to {resolved}, which is inside NO git repository "
                    f"({err}) -- so it is not `{repo_path}` of this one: the profile loads "
                    f"law this repo does not author"
                )
            else:
                entry["resolution"] = "UNREADABLE"
                problems.append(
                    f"{loaded} resolves to {resolved}, whose repository could not be read: "
                    f"{err}"
                )
            continue
        try:
            rel_resolved = resolved.relative_to(top).as_posix()
        except ValueError:
            rel_resolved = None
        repo_common, _ = _git_common_dir(repo)
        res_common, _ = _git_common_dir(top)
        same_repo = None not in (repo_common, res_common) and repo_common == res_common
        if rel_resolved != Path(repo_path).as_posix() or not same_repo:
            entry["resolution"] = "RESOLVES ELSEWHERE"
            problems.append(
                f"{loaded} resolves to {resolved} -- {rel_resolved!r} of {top}"
                + ("" if same_repo else ", which is a DIFFERENT repository")
                + f", not `{repo_path}` of this one: the profile loads law this repo does "
                f"not author"
            )
            continue
        entry["resolution"] = "resolved"

        # --- the FRESHNESS predicate: sha256 per law file, loaded vs the reference --------
        if form == "file":
            local_files = [resolved]
            base = resolved.parent
        else:
            base = resolved
            local_files = []
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames[:] = sorted(d for d in dirnames if d != ".git")
                for name in sorted(filenames):
                    if name.endswith(".md"):
                        local_files.append(Path(dirpath) / name)
            local_files.sort()

        for path in local_files:
            try:
                real = path.resolve(strict=True)
            except OSError as exc:
                entry["files"].append({"path": str(path), "status": "UNREADABLE", "detail": str(exc)})
                entry["stale"] += 1
                coverage["stale"].append(str(path))
                problems.append(f"{path} could not be read: {exc}")
                continue
            try:
                rel = real.relative_to(top).as_posix()
            except ValueError:
                entry["files"].append(
                    {"path": str(path), "status": "OUTSIDE-SOURCE", "detail": str(real)}
                )
                entry["stale"] += 1
                coverage["stale"].append(str(path))
                problems.append(
                    f"{path} loads {real}, which is OUTSIDE {top} -- the law is served from "
                    f"outside the tree this repo authors"
                )
                continue
            try:
                loaded_bytes = real.read_bytes()
            except OSError as exc:
                entry["files"].append({"path": rel, "status": "UNREADABLE", "detail": str(exc)})
                entry["stale"] += 1
                coverage["stale"].append(rel)
                problems.append(f"{real} could not be read: {exc}")
                continue

            ref_bytes, why = _git_bytes(repo, ["show", f"{reference_ref}:{rel}"])
            record = {
                "path": rel,
                "loaded": _sha256(loaded_bytes)[:12],
                "at_reference": None,
                "status": "equal",
            }
            if ref_bytes is None:
                record["status"] = "ABSENT AT THE REFERENCE"
                record["detail"] = why
                entry["stale"] += 1
                coverage["stale"].append(rel)
                problems.append(
                    f"{rel} is LOADED by `{skill}` but does not exist at {reference_ref} "
                    f"({why}) -- a law file the profile serves and the repository does not "
                    f"publish is either local-only or moved upstream"
                )
            elif ref_bytes != loaded_bytes:
                record["status"] = "STALE"
                record["at_reference"] = _sha256(ref_bytes)[:12]
                entry["stale"] += 1
                coverage["stale"].append(rel)
                problems.append(
                    f"{rel} is STALE: the profile loads {record['loaded']} from {top} but "
                    f"{record['at_reference']} stands at {reference_ref} "
                    f"({reference_source}) -- a lane loading `{skill}` reads law this "
                    f"repository has already replaced"
                )
            else:
                record["at_reference"] = record["loaded"]
            entry["files"].append(record)

        # THE OTHER DIRECTION: a law file the reference publishes and the loaded tree lacks.
        # The #443 clause landed inside an existing file, but a NEW clause file upstream is
        # the same staleness wearing a different shape -- and a hash over local files alone
        # can never see it.
        if form == "dir":
            out, why = _git_read(
                repo, ["ls-tree", "-r", "--name-only", reference_ref, "--", repo_path], timeout=60
            )
            if why:
                problems.append(
                    f"the law files at {reference_ref} under {repo_path} could not be listed: {why}"
                )
            else:
                prefix = f"{Path(repo_path).as_posix().rstrip('/')}/"
                at_ref = {
                    name.strip()[len(prefix):]
                    for name in (out or "").splitlines()
                    if name.strip().startswith(prefix) and name.strip().endswith(".md")
                }
                loaded_names = {p.relative_to(base).as_posix() for p in local_files}
                for name in sorted(at_ref - loaded_names):
                    coverage["missing_local"].append(name)
                    problems.append(
                        f"{prefix}{name} is published at {reference_ref} and ABSENT from the "
                        f"loaded tree {base} -- the profile serves a law the repository has "
                        f"already extended"
                    )

    return problems, coverage

def publish_freshness_leg(
    *,
    repo: Path = REPO,
    remote: str = PUBLISH_REMOTE,
    branch: str = PUBLISH_BRANCH,
    read_at: str,
    now=None,
    pusher: Path = PUBLISH_PUSHER,
    profile_root: Path | None = None,
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
    push in ONE file per REPOSITORY, in the git common dir (#445), and a remote tip that is
    not that sha left through some other path. That arm names the tip, its age and the lane
    trailer of its commit.

    THE RECEIPT IS PER-REPOSITORY, NOT PER-CHECKOUT (#445). The record lives in the git
    COMMON dir, so every worktree of this repository reads the SAME receipt -- before this,
    a receipt under `evidence/` was gitignored and therefore checkout-local, and this leg
    compared a GLOBAL remote tip against whichever checkout happened to be reading, so the
    same tip produced a finding in one worktree and silence in another. The coverage
    therefore PRINTS the reading checkout AND the receipt's own recorded origin, and STATES
    the residual: the record is LAST-WRITER-WINS across worktrees, so a push made by a
    sibling checkout is named as that checkout's push and never misattributed to this one.

    THE BINDING ARM (issue #468, ruled at n=3137). This leg also answers the same freshness
    question one surface over: the LAW a profile LOADS, against the law at `origin/main`.
    A profile skill binding is verified offline for RESOLUTION only (`test -L && test -d`),
    so a binding that resolves can still serve a tree hundreds of commits behind -- measured
    first-hand 2026-10-16, 487 commits behind, with the #443 dispatch-composition clause in
    force on `origin/main` and ABSENT from every lane's loaded text. The predicate is a
    CONTENT hash per law file and never a timestamp, and a repo that declares no binding
    leaves the arm NOT RUN with its stated reason rather than silently clean.
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
        # THE DIVERGENCE PARTITION (#418). `behind` is a pure-ancestor stale checkout
        # (nothing of its own, not a problem); `diverged` is ahead>0 AND behind>0, the only
        # shape #146's ruling is about. Both are initialized so the population print is
        # stable and a clean round renders "behind: False, diverged: False" rather than an
        # absent key a reader must interpret.
        "behind": False,
        "diverged": False,
        # THE CADENCE SIDE (issue #284). `receipt` is the pusher's own record of its last
        # push; a remote tip that is not that sha left through some OTHER path, and the
        # tip-age arm is the opportunistic half -- it only sees a tip SAMPLED while young.
        "receipt": None,
        "receipt_reason": "",
        "receipt_mismatch": None,
        # WHERE THIS LEG IS READING FROM, and WHERE THE RECEIPT IT READS WAS WRITTEN (#445).
        # The receipt is ONE record per repository (git common dir), so "which checkout is
        # reading" and "which checkout wrote the record" are DIFFERENT questions and both are
        # printed. `receipt_path` is the resolved file the record was read from, or None when
        # the common dir is unresolvable -- the absence is REPORTED, never silently fallen
        # back to a checkout-local path.
        "reading_checkout": str(Path(repo).resolve()),
        "receipt_path": None,
        "receipt_residual": PUBLISH_RECEIPT_RESIDUAL,
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

    # BEHIND IS NOT DIVERGED, and this leg calls the PUSHER's own `divergence()` rather than
    # restating a one-sided predicate (#418): the same helper `publish()` reads, so the leg
    # and the mechanism cannot disagree about what BEHIND means. A pure-ancestor checkout
    # (ahead == 0) is a stale read copy with nothing of its own -- reporting it would red
    # this leg on the normal steady state, since under the worktree law the shared tree is
    # behind `origin/main` most of the time, the very false RED #146's ruling warns of.
    state = pub.divergence(Path(repo), tip)
    if state["state"] == "behind":
        coverage["behind"] = True
    elif state["state"] == "diverged":
        problems.append(
            f"{remote}/{branch} ({tip}) is not an ancestor of HEAD -- the branch has "
            f"DIVERGED ({state['ahead']} commit(s) ahead, {state['behind']} behind), and the "
            f"pusher reports rather than resolves by design"
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
    receipt_file = pub.receipt_path(Path(repo))
    coverage["receipt_path"] = None if receipt_file is None else str(receipt_file)
    if receipt is None:
        coverage["receipt_reason"] = receipt_why
    else:
        rec_age = pub.age_secs(receipt.get("instant") or "", now)
        coverage["receipt"] = {
            "sha": str(receipt.get("sha") or ""),
            "instant": str(receipt.get("instant") or ""),
            "age_secs": None if rec_age is None else int(rec_age),
            # THE ORIGIN HALF (#445): WHICH checkout wrote the record being read. A receipt
            # written before #445 landed carries no `checkout`, and that absence is reported
            # as None -- never assumed to be this checkout, which is the very misattribution
            # the fix exists to remove.
            "origin_checkout": str(receipt.get("checkout") or "") or None,
        }
        if coverage["receipt"]["sha"] != tip:
            lane = (tip_info or {}).get("session_id") or ""
            subject = (tip_info or {}).get("subject") or ""
            trailer = lane if tip_info is not None else f"unreadable ({tip_why})"
            origin = coverage["receipt"]["origin_checkout"]
            coverage["receipt_mismatch"] = {
                "remote_tip": tip,
                "receipt_sha": coverage["receipt"]["sha"],
                "receipt_instant": coverage["receipt"]["instant"],
                "receipt_origin_checkout": origin,
                "lane": lane,
                "subject": subject,
            }
            problems.append(
                f"the remote tip {tip} is NOT the sha the pusher last recorded "
                f"({coverage['receipt']['sha']} at {coverage['receipt']['instant']}) -- a "
                f"push that did not go through the pusher; lane "
                f"{trailer or 'no lane trailer'}"
                + (f" -- {subject[:60]}" if subject else "")
                + (
                    f" [receipt written by {origin}]"
                    if origin
                    else " [receipt names no origin checkout]"
                )
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

    # --- the binding arm (issue #468, ruled at n=3137) --------------------------------
    #
    # It rides THIS leg because the leg already asks the question the arm answers -- is what
    # we serve the same as what we published -- and it reads the same checkout the pusher
    # reads, so no second instrument is created (#3137). The reference is the tip THIS round
    # read from the remote when its object is present, so the arm is anchored on the
    # published fact rather than on a local cache whenever that is possible.
    ref, ref_source, ref_reason = _binding_reference(Path(repo), tip)
    arm_problems, arm_coverage = binding_freshness_arm(
        repo=Path(repo),
        profile_root=None if profile_root is None else Path(profile_root),
        declaration_path=Path(repo) / HARNESS_BINDINGS_REL,
        reference_ref=ref,
        reference_source=ref_source,
        reference_reason=ref_reason,
        read_at=read_at,
    )
    problems.extend(arm_problems)
    # NAMESPACED, never merged flat (#468): the arm's own key vocabulary is close to this
    # leg's -- both carry a `stale` list and both count law/commits -- and a flat update
    # silently overwrote the leg's commit `stale` list with the arm's law-file list, which
    # read as a clean round on the very probe that exists to catch an unpushed commit. One
    # nested key cannot collide with any key the leg already carries.
    coverage["binding"] = arm_coverage

    return {
        "name": "publish-freshness",
        "status": "ASSERTED",
        "problems": problems,
        "excused": [],
        "coverage": coverage,
    }


# ------------------------------------------------------------------ score conversion

SCORES_DIR_REL = "evidence/scores"

_SCORE_ARTIFACT_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})\.md$")
_SCORECARD_HEADING_RE = re.compile(
    r"^###\s+\d+\.\s+(?P<name>.+?)\s+—\s+(?P<total>\d+)\s*/\s*(?P<den>\d+)\s*$"
)
_SCORECARD_CRITERIA_RE = re.compile(r"^\|\s*D1\s*\|")
# BOLD IS PRESENTATION, `(UNM)` IS DATA (#531). A cell written `**3**` is a three; the
# earlier form admitted up to two LEADING asterisks and NONE trailing, so `**3**` read as
# no value at all and the block silently lost a cell -- measured: 2026-10-09's Miidas card
# parsed 18 of 19, and that arm prints nothing anomalous, which is why it was never filed.
# The trailing pair is accepted for the same reason the leading pair was: emphasis wrapped
# around a number must not change what the number is. Measured across every artifact in the
# series (35 artifacts, 66 blocks, 1139 cells): exactly ONE cell changes reading.
_SCORECARD_CELL_RE = re.compile(
    r"^\*{0,2}\s*(?P<value>\d+)\s*(?P<unm>\(UNM\))?\s*\*{0,2}$"
)

# THE FLOOR IS THE RULING'S OWN, not this leg's choice (#67): "any criterion score < 3".
SCORE_FLOOR = 3


def score_artifacts(scores_dir: Path) -> list[tuple[str, Path]]:
    """Every dated survey artifact in `scores_dir`, OLDEST first.

    The date is read from the FILENAME, never from the artifact's own heading: the name is
    the identity the `converted_from` token joins against, so a leg that took the date from
    the body would be joining on a different key than the one the write path accepts.
    """
    out: list[tuple[str, Path]] = []
    try:
        entries = list(Path(scores_dir).iterdir())
    except OSError:
        return []
    for path in entries:
        match = _SCORE_ARTIFACT_RE.match(path.name)
        if match and path.is_file():
            out.append((match.group("date"), path))
    return sorted(out)


def scorecard_blocks(text: str) -> list[dict]:
    """Each factory scorecard's own total and criterion cells, in the artifact's own order.

    A cell is `(criterion, value, unmeasurable)`. The UNM marker is carried rather than
    dropped because `0 (UNM)` reads as `0 < 3` under the floor predicate while being an
    EXCLUDED cell by ruling `n=2747` -- a leg that scored it would report every round as a
    regression, which is the failure mode that makes a predicate ignored rather than fixed.
    """
    lines = text.splitlines()
    blocks: list[dict] = []
    current: dict | None = None
    for idx, line in enumerate(lines):
        heading = _SCORECARD_HEADING_RE.match(line)
        if heading:
            current = {
                "name": heading.group("name").strip(),
                "total": int(heading.group("total")),
                "den": int(heading.group("den")),
                "cells": [],
                # THE BLOCK'S OWN POPULATION DECLARATION (#531). `declared` is how many
                # criterion columns the block's header row names; `parsed` is how many of
                # those cells actually read as a value. Both travel on the block so a
                # caller can see incompleteness WITHOUT re-deriving it -- the filed symptom
                # was a consumer that read `cells: []` and reported a clean round.
                "declared": 0,
                "parsed": 0,
            }
            blocks.append(current)
            continue
        if current is None:
            continue
        if line.startswith("## ") or line.startswith("### "):
            current = None
            continue
        if current["cells"] or not _SCORECARD_CRITERIA_RE.match(line):
            continue
        header = [c.strip() for c in line.strip().strip("|").split("|")]
        # The header IS the declaration: whatever columns it names, that many cells the
        # block owes. Recorded before the values are read, so a row whose width disagrees
        # with its own header reads as SHORT rather than as absent.
        current["declared"] = len(header)
        values = None
        for nxt in lines[idx + 1: idx + 4]:
            if set(nxt.strip()) <= set("|-: "):
                continue
            values = [c.strip() for c in nxt.strip().strip("|").split("|")]
            break
        if not values or len(values) != len(header):
            continue
        for criterion, cell in zip(header, values):
            match = _SCORECARD_CELL_RE.match(cell)
            if not match:
                continue
            current["cells"].append((
                criterion, int(match.group("value")), bool(match.group("unm")),
            ))
    for block in blocks:
        block["parsed"] = len(block["cells"])
    return blocks

def scorecard_shortfalls(blocks: list[dict]) -> list[dict]:
    """Every block whose cell population is SHORT of what its own header declares (#531).

    A block is COMPLETE only when it declared at least one criterion column AND every
    declared column read as a value. `declared == 0` is NOT "0 of 0, therefore fine" -- it
    is the shape a card takes when its cells are grouped per family instead of laid out as
    a flat criterion row, so the leg parsed the heading and nothing else. Measured
    2026-10-17: all six cards, 0 cells each, and the leg printed `0 cell(s) examined ... 0
    regression(s): none, no conversion owed` -- a clean verdict over a population it never
    read, which is indistinguishable from a round that read 114 cells and found them clean.

    The comparison is against the block's OWN header, never a hard-coded 19: the leg reads
    whatever rubric the artifact declares, and a fixture that declares two columns and
    delivers two is complete. Returns `{factory, parsed, declared}` per short block, so the
    caller names both counts rather than re-deriving either.
    """
    short: list[dict] = []
    for block in blocks:
        parsed = int(block.get("parsed", 0))
        declared = int(block.get("declared", 0))
        if declared < 1 or parsed < declared:
            short.append({
                "factory": block["name"], "parsed": parsed, "declared": declared,
            })
    return short

def shortfall_phrase(entry: dict) -> str:
    """One short block, NAMED with both counts (#531): block, parsed, declared."""
    if entry["declared"] < 1:
        return (
            f"{entry['factory']} (0 cell(s) parsed, 0 declared -- the card carries no "
            f"`| D1 | ... |` criterion header row this leg reads)"
        )
    return (
        f"{entry['factory']} ({entry['parsed']} of {entry['declared']} declared cell(s) "
        f"parsed, {entry['declared'] - entry['parsed']} unread)"
    )


def lapsed_unread_entry(artifact_rel: str, reason: str) -> dict:
    """A lapsed round the leg could NOT measure (#531).

    `owed` is deliberately NOT False here, and that distinction is the whole clause: `owed`
    answers "does this round carry a regression nothing answers", and a round whose cells
    never read cannot answer it in EITHER direction. False is the verdict "measured, clean,
    owes nothing" -- precisely the reading that let 2026-10-17 print as a clean round. The
    `unread` marker makes the render print the reason IN PLACE OF counts the leg does not
    have, so no `0 regression(s): none, no conversion owed` line can be assembled from an
    artifact that was never read.
    """
    return {
        "artifact": artifact_rel,
        "regressions": [],
        "owed": True,
        "unread": True,
        "reason": reason,
    }

def score_regressions(blocks: list[dict], previous: dict[str, int]) -> tuple[list[dict], int, int]:
    """Every regression a round carries, by the ONE predicate (#517).

    A regression is a measurable criterion cell under the floor (3) OR a factory whose net
    total fell against the round before it. `(UNM)` cells are EXCLUDED, never scored: `0
    (UNM)` under the floor would make every round read as a regression (ruling n=2747).

    ONE HOME because the leg now applies it to TWO populations -- the newest artifact (with
    its own predecessor) and every LAPSED round (each with the artifact before it). Two
    copies of this predicate would be two verdicts about one fact, and the lapsed read
    exists precisely because the newest-only read could not answer an older round.

    Returns `(regressions, cells_examined, unmeasurable_cells)`.
    """
    regressions: list[dict] = []
    cells = 0
    unmeasurable = 0
    for block in blocks:
        below: list[str] = []
        for criterion, value, unm in block["cells"]:
            cells += 1
            if unm:
                unmeasurable += 1
                continue
            if value < SCORE_FLOOR:
                below.append(f"{criterion} {value}")
        reasons: list[str] = []
        if below:
            reasons.append(
                f"criterion cell(s) below the floor: {', '.join(below)}"
            )
        was = previous.get(block["name"])
        if was is not None and block["total"] < was:
            reasons.append(f"net total fell {was} -> {block['total']}")
        if reasons:
            regressions.append({
                "factory": block["name"],
                "total": block["total"],
                "reasons": reasons,
            })
    return regressions, cells, unmeasurable


def score_conversion_leg(
    rows: list[dict],
    *,
    read_at: str,
    repo: Path = REPO,
    predicate=None,
    scores_dir: Path | None = None,
) -> dict:
    """Every regression in the NEWEST survey artifact, and whether a row ANSWERS it.

    AND EVERY LAPSED ROUND SINCE (#517). The newest-only population healed a lapse by
    accident: a round whose `conversion` row never landed dropped out of the population the
    moment a newer artifact arrived, so its regressions could never be answered and nothing
    said so. This docstring declared exactly that scope -- *"every regression in the NEWEST
    survey artifact"* -- and the declared behaviour's consequence was never measured, which
    is why the repair is a widened COVERAGE read rather than a wider regression read: the
    floor verdict and the delta still need the newest round and its predecessor.

    The statute (`skills/meta-factory/SKILL.md` §6) carried the word "automatically" over a
    conversion no trigger performed. The ruling's repair is not a promise in prose but a
    JOIN: a regression is a criterion cell under the floor or a factory whose net total
    fell, and it is ANSWERED only by a ledger row declaring
    `converted_from=evidence/scores/<date>.md` for THAT artifact. A row naming a different
    round answers a different regression, so the join is on the exact path.

    THE POPULATION IS PRINTED, and a zero-regression read states its own size
    (#112, `skills/meta-factory/SKILL.md` §8):
    "no regression" and "no artifact parsed" are the same verdict otherwise, and the second
    is the state a broken parse produces.

    IT FAILS OPEN. An absent artifact, an unreadable one, or one carrying no scorecard
    section is NOT RUN with its reason -- the leg has no predicate to read with, and a
    finding invented from an unparsed file is worse than no finding at all. The JOIN side
    carries the same guard one level down (#472): an EMPTY row population is NOT RUN too,
    because the leg cannot tell "no row answers this regression" from "I was handed no
    rows" and would otherwise report the former from a ledger it never read -- before the
    guard existed both states returned the SAME `ASSERTED` status, so a lane verifying its
    own just-written `conversion` row had no mechanical way to tell "my row is missing"
    from "I passed no rows". A regression WITH no answering row is a FINDING, and it names
    the factory: a count cannot be dispatched, claimed or closed (#148).
    """
    # THE FIELD PREDICATE, not the board-intake one: `converted_from` is a detail-field
    # token read through the SHARED predicate (one field, one predicate, SKILL.md section
    # 11), and the board-intake module carries no reader for it -- binding the leg to that
    # loader would make its default arm raise on the first row rather than read it.
    predicate = predicate or field_predicate_readers()
    directory = Path(scores_dir) if scores_dir is not None else Path(repo) / SCORES_DIR_REL
    coverage = {
        "read_at": read_at,
        "scores_dir": str(directory),
        "artifact": None,
        "previous": None,
        "factories": 0,
        "criteria_cells": 0,
        "unmeasurable_cells": 0,
        "regressions": [],
        "answered": [],
        "unanswered": [],
        "conversion_rows": 0,
        "floor": SCORE_FLOOR,
    }
    artifacts = score_artifacts(directory)
    if not artifacts:
        return {
            "name": "score-conversion",
            "status": "NOT RUN",
            "problems": [],
            "excused": [],
            "coverage": {**coverage, "reason": (
                f"no `{SCORES_DIR_REL}/<date>.md` artifact is in this tree, so the "
                f"predicate has nothing to read -- a bootstrapped factory carries the "
                f"survey's artifacts only once it has run a round"
            )},
        }
    date, path = artifacts[-1]
    coverage["artifact"] = f"{SCORES_DIR_REL}/{path.name}"
    if len(artifacts) >= 2:
        coverage["previous"] = f"{SCORES_DIR_REL}/{artifacts[-2][1].name}"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {
            "name": "score-conversion",
            "status": "NOT RUN",
            "problems": [],
            "excused": [],
            "coverage": {**coverage, "reason": f"{path} could not be read: {exc}"},
        }

    blocks = scorecard_blocks(text)
    if not blocks:
        return {
            "name": "score-conversion",
            "status": "NOT RUN",
            "problems": [],
            "excused": [],
            "coverage": {**coverage, "reason": (
                f"{path.name} carries no `## Detailed Factory Scorecards` section this leg "
                f"can parse, so no regression can be read from it -- the artifact predates "
                f"the section, or its shape has moved"
            )},
        }

    # AN INCOMPLETE BLOCK IS NOT A CLEAN BLOCK (#531). This leg's whole job is to read cells
    # and weigh them against the floor, so a block that LOST cells can only under-report
    # regressions: a verdict taken off it is a clean round invented from a population the
    # leg did not read. Measured 2026-10-17 -- six cards, zero cells each, printed as
    # `0 cell(s) examined, 0 regression(s): none, no conversion owed`. The refusal names the
    # block and BOTH counts, because "the parse was short" without the numbers is the same
    # unverifiable claim in a different voice.
    short = scorecard_shortfalls(blocks)
    if short:
        return {
            "name": "score-conversion",
            "status": "NOT RUN",
            "problems": [],
            "excused": [],
            "coverage": {
                **coverage,
                "factories": len(blocks),
                "criteria_cells": sum(int(b.get("parsed", 0)) for b in blocks),
                "incomplete_blocks": short,
                "reason": (
                    f"{path.name} parses into {len(blocks)} factory scorecard(s) and "
                    f"{len(short)} of them are INCOMPLETE against their own header, so no "
                    f"regression can be read from the round: "
                    + "; ".join(shortfall_phrase(entry) for entry in short)
                    + " -- a verdict off an unread block would report a clean round over a "
                    f"population this leg never read (#531)"
                ),
            },
        }

    previous: dict[str, int] = {}
    if len(artifacts) >= 2:
        try:
            previous = {
                block["name"]: block["total"]
                for block in scorecard_blocks(artifacts[-2][1].read_text(encoding="utf-8"))
            }
        except OSError:
            previous = {}

    regressions, cells, unmeasurable = score_regressions(blocks, previous)

    artifact_rel = f"{SCORES_DIR_REL}/{path.name}"

    # AN EMPTY ROW POPULATION IS AN INSTRUMENT FAILURE, NEVER A FINDING (#472). The join
    # below is handed the ledger to read WITH, and a caller that hands it none -- a probe
    # checking its own declaration, a leg wired before the ledger is loaded -- would
    # otherwise walk ZERO rows, find nothing answering the round, and report the SAME
    # `ASSERTED` status a real read reports: a confident finding about a ledger the leg
    # never read. The verdict is NOT RUN, and the artifact-side counters still travel with
    # it, because a NOT RUN arm that zeroed them would misreport what it DID manage to read
    # (SKILL.md section 8: the population is printed; #112: "no regression" and "no
    # artifact parsed" are the same verdict otherwise; #242: a leg that examined NOTHING
    # must never render as one that examined the population and found it clean).
    #
    # THE ARM IS THE JOIN INPUT ALONE, and deliberately NOT "a populated ledger carrying no
    # `conversion` event at all". A ledger that WAS read and carries no conversion row is a
    # legitimate FINDING -- it is precisely the state this leg exists to report (#67, #148:
    # a regression no row answers reads as converted and is not, the 2026-09-19 decline).
    # Widening the arm to that state would silence the leg exactly when it has something to
    # say, and would report "nothing read" over a ledger whose thousands of rows were in
    # fact read -- the conflation section 8 forbids, in the INVERSE direction. `len(rows)`
    # settles the one question the guard exists to settle, and the population stays visible
    # either way: `conversion_rows` travels in the coverage of both arms.
    if not rows:
        return {
            "name": "score-conversion",
            "status": "NOT RUN",
            "problems": [],
            "excused": [],
            "coverage": {
                **coverage,
                "factories": len(blocks),
                "criteria_cells": cells,
                "unmeasurable_cells": unmeasurable,
                "regressions": [r["factory"] for r in regressions],
                "reason": (
                    f"the leg was handed an EMPTY row population, so the join had no "
                    f"ledger to read an answering `converted_from={artifact_rel}` row "
                    f"from: {artifact_rel} parsed into {len(blocks)} factory scorecard(s) "
                    f"carrying {len(regressions)} regression(s), but ZERO row(s) were read "
                    f"against them -- the instrument failed, the round did not convert "
                    f"(#472)"
                ),
            },
        }

    answered: list[str] = []
    named_sources: set[str] = set()
    for row in rows:
        if str(row.get("event") or "") != "conversion":
            continue
        source = predicate.declared_conversion_source(str(row.get("detail") or ""))
        if source is None:
            continue
        coverage["conversion_rows"] += 1
        named_sources.add(source)
        if source == artifact_rel:
            answered.append(str(row.get("subject") or ""))

    # THE JOIN IS PER-ARTIFACT, not per-factory (#67): the row the write path accepts names
    # the artifact it converted (`converted_from=evidence/scores/<date>.md`), never a
    # factory, so ONE answering row clears the round and the coverage field must say what
    # the problems list says -- a field listing every regression as `unanswered` beside an
    # empty `problems` is two surfaces disagreeing about one fact.
    unanswered = [] if answered else [r["factory"] for r in regressions]
    problems: list[str] = []
    if regressions and not answered:
        problems.append(
            f"{artifact_rel} carries {len(regressions)} regression(s) and no ledger row "
            f"declares `converted_from={artifact_rel}`: "
            + "; ".join(f"{r['factory']} ({'; '.join(r['reasons'])})" for r in regressions)
            + " -- a regression no row answers reads as converted and is not (#67)"
        )

    # THE LAPSED READ (#517). The newest-only population had a blind spot the next round
    # healed by ACCIDENT: a round whose `conversion` row never landed left the population
    # the moment a newer artifact arrived, so its regressions could never be answered and
    # nothing said so. A lapse was survivable by exactly one round -- the failure mode the
    # per-artifact join exists to catch.
    #
    # THE POPULATION IS THE MECHANISM'S EPOCH FORWARD (ruling n=3820, 2026-10-19), never
    # "all artifacts" and never "the newest artifact a row names". The epoch is the
    # artifact named by the EARLIEST `conversion` row in the ledger: a factory's rounds
    # before the conversion existed carry no obligation, so widening to them would report
    # a lapse for every pre-mechanism round. Anchoring at the NEWEST named artifact instead
    # is blind to a mid-history gap -- rows for artifacts A and C with none for B reports
    # ZERO lapses there, which is the same blind spot wearing a different name. With no
    # named artifact at all there is no epoch, so the read is NOT RUN with its reason
    # rather than reporting the whole tree (#112: "no lapse" and "no epoch" must not
    # render the same).
    #
    # A LAPSE IS AN UNANSWERED ARTIFACT IN THAT POPULATION -- one whose exact path no
    # `converted_from=` row names -- and it is a PROBLEM only when it owes a conversion,
    # that is, when it carries a regression (docs/measurement-procedure.md section 5.4: "A
    # run whose artifact shows a regression declares the conversion on a row of its own").
    # A regression-free round owes nothing, so calling it a violation would teach the next
    # reader to ignore the leg. The NEWEST artifact is excluded from the problem arm: its
    # unanswered regressions are already reported above, and one fact must not be counted
    # twice.
    named_dates = {
        match.group("date")
        for match in (
            _SCORE_ARTIFACT_RE.match(Path(source).name) for source in named_sources
        )
        if match
    }
    lapsed: list[dict] = []
    if not named_dates:
        coverage["lapsed_reason"] = (
            f"no `conversion` row in the {len(rows)} row(s) read names any "
            f"`{SCORES_DIR_REL}/<date>.md` artifact, so the leg has no baseline to measure "
            f"a lapse against -- a factory whose rounds all predate the conversion "
            f"mechanism owes none, and reporting every artifact as lapsed would be a "
            f"finding invented from a missing declaration"
        )
    else:
        epoch_date = min(named_dates)
        coverage["lapsed_epoch"] = f"{SCORES_DIR_REL}/{epoch_date}.md"
        # The POPULATION prints beside the lapse count (#112, #242): "0 lapsed" and "no
        # artifact parsed at or after the epoch" must never render the same line.
        coverage["lapsed_population"] = sum(
            1 for date, _path in artifacts if date >= epoch_date
        )
        totals_by_date: dict[str, dict[str, int]] = {}
        for index, (date, artifact_path) in enumerate(artifacts):
            if date < epoch_date:
                continue
            # ANSWERED BY ITS OWN ROW: the join is per-artifact on the EXACT path, so a row
            # naming this artifact clears it and it is not a lapse (docs/measurement-
            # procedure.md section 5.4.2 -- a 10-18 row cannot answer 10-17).
            if f"{SCORES_DIR_REL}/{artifact_path.name}" in named_sources:
                continue
            try:
                artifact_text = artifact_path.read_text(encoding="utf-8")
            except OSError as exc:
                lapsed.append(lapsed_unread_entry(
                    f"{SCORES_DIR_REL}/{artifact_path.name}",
                    f"could not be read: {exc}",
                ))
                continue
            lapsed_blocks = scorecard_blocks(artifact_text)
            if not lapsed_blocks:
                lapsed.append(lapsed_unread_entry(
                    f"{SCORES_DIR_REL}/{artifact_path.name}",
                    "carries no `## Detailed Factory Scorecards` section this leg can "
                    "parse, so no regression can be read from it",
                ))
                continue
            # A LAPSED ROUND WITH A SHORT PARSE IS THE FILED SYMPTOM (#531): 2026-10-17's six
            # cards parsed to zero cells each, and the lapsed line read
            # `2026-10-17.md (0 regression(s): none, no conversion owed)` -- an unread round
            # clearing itself of an obligation nobody had checked.
            lapsed_short = scorecard_shortfalls(lapsed_blocks)
            if lapsed_short:
                lapsed.append(lapsed_unread_entry(
                    f"{SCORES_DIR_REL}/{artifact_path.name}",
                    f"{len(lapsed_short)} of {len(lapsed_blocks)} scorecard(s) INCOMPLETE "
                    f"against their own header: "
                    + "; ".join(shortfall_phrase(entry) for entry in lapsed_short),
                ))
                continue
            if index > 0:
                prev_date, prev_path = artifacts[index - 1]
                if prev_date not in totals_by_date:
                    try:
                        totals_by_date[prev_date] = {
                            block["name"]: block["total"]
                            for block in scorecard_blocks(
                                prev_path.read_text(encoding="utf-8")
                            )
                        }
                    except OSError:
                        totals_by_date[prev_date] = {}
                previous_totals = totals_by_date[prev_date]
            else:
                previous_totals = {}
            lapsed_regressions, _cells, _unm = score_regressions(
                lapsed_blocks, previous_totals
            )
            lapsed_rel = f"{SCORES_DIR_REL}/{artifact_path.name}"
            lapsed.append({
                "artifact": lapsed_rel,
                "regressions": [r["factory"] for r in lapsed_regressions],
                "owed": bool(lapsed_regressions),
            })
            if lapsed_regressions and lapsed_rel != artifact_rel:
                problems.append(
                    f"{lapsed_rel} is a LAPSED round -- no ledger row declares "
                    f"`converted_from={lapsed_rel}` -- and it carries "
                    f"{len(lapsed_regressions)} regression(s): "
                    + "; ".join(
                        f"{r['factory']} ({'; '.join(r['reasons'])})"
                        for r in lapsed_regressions
                    )
                    + " -- a round outside the newest-only population can never be "
                    "answered, which is the blind spot #517 names"
                )
    coverage["lapsed"] = lapsed
    coverage["lapsed_examined"] = len(lapsed)

    coverage.update({
        "factories": len(blocks),
        "criteria_cells": cells,
        "unmeasurable_cells": unmeasurable,
        "regressions": [r["factory"] for r in regressions],
        "answered": answered,
        "unanswered": unanswered,
    })
    return {
        "name": "score-conversion",
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


def render_lapsed_entry(entry: dict) -> str:
    """One lapsed round: its COUNTS when it was read, its REASON when it was not (#531).

    A single home for the entry's rendered shape, because the two arms must never share a
    phrasing: `0 regression(s): none, no conversion owed` is a measurement, and printing it
    over an artifact whose cells never parsed is how a clean round gets invented. An unread
    round says so and names what the parse saw.
    """
    if entry.get("unread"):
        return (
            f"{entry['artifact']} (UNREAD -- nothing measured, nothing cleared: "
            f"{entry.get('reason') or 'reason not stated'})"
        )
    return (
        f"{entry['artifact']} ({len(entry['regressions'])} regression(s): "
        f"{', '.join(entry['regressions']) or 'none'}"
        f"{'' if entry.get('owed') else ', no conversion owed'}"
        f"{'; ' + entry['reason'] if entry.get('reason') else ''})"
    )

def render(legs: list[dict], deferred: list[dict], *, slug: str, read_at: str,
           issues: list[dict], deferred_problems: list[str] | None = None,
           board_rider: dict | None = None) -> str:
    """The report. Every count travels with the predicate that produced it."""
    deferred_problems = list(deferred_problems or [])
    open_count = sum(
        1 for i in issues if str(i.get("state", "")).strip().lower() == "open"
    )
    lines = [
        f"patrol host-state read: {slug} at {read_at}",
        f"board: {len(issues)} issue(s) read WHOLE (--state all), {open_count} open",
    ]
    if board_rider is not None:
        # #241's rider, printed ONCE and at the head of the board-leg region: the four
        # board legs share ONE read of ONE tree, so repeating it per leg would be noise,
        # and printing it here is what makes their verdicts attributable to the tree state
        # they were taken against. It carries no problem and cannot move the verdict.
        lines.extend(render_shared_tree_rider(board_rider))
    lines.append("")
    for leg in legs:
        cov = leg["coverage"]
        lines.append(f"LEG {leg['name']} — {leg['status']}")
        if leg["status"] == "FAILED":
            # #501: a leg whose CONSTRUCTION raised. It is NAMED, its reason is printed
            # and its problem is counted, so the round still prints a verdict and the exit
            # code still reflects the failure. The name dispatch BELOW is deliberately
            # skipped: a leg that never built has none of the coverage keys its own branch
            # reads, so falling into that chain would raise a KeyError in the REPORT and
            # take the round down by the back door -- the very class this contains.
            lines.append(f"  FAILED: {cov.get('reason') or 'reason not stated'}")
            lines.append(f"  exception: {cov.get('exception') or 'unstated'}")
            lines.append(f"  excused: {len(leg['excused'])}")
            lines.append(f"  problems: {len(leg['problems'])}")
            for problem in leg["problems"]:
                lines.append(f"    - {problem}")
            lines.append(f"  read at {cov.get('read_at') or 'unstated'}")
            lines.append("")
            continue
        if leg["status"] == "NOT RUN" and leg["name"] == "cadence-slot":
            # #392 + #271: this arm fires EXACTLY when rows could not be judged, so a raw
            # counter dump here would print `UNREADABLE: 1` and never the reason -- the
            # zero-that-stands-for-could-not-look shape one coat over. render_cadence_slot
            # is this leg's ONE render home and it names every UNREADABLE row with its
            # reason, so both arms read the same way and neither can drift from the other.
            lines.extend(render_cadence_slot(cov))
            lines.append(f"  read at {cov.get('read_at') or 'unstated'}")
            lines.append(f"  excused: {len(leg['excused'])}")
            lines.append(f"  problems: {len(leg['problems'])}")
            lines.append("")
            continue
        if leg["status"] == "NOT RUN" and leg["name"] in (
            "cron-thinness", "pacemaker-presence", "notify-receipt", "duty-receipt",
            "score-conversion",
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
        if leg["name"] == "cadence-slot":
            # #392: the population line and every non-HELD verdict. A HELD row is COUNTED
            # and not printed one by one, so a box of 42 healthy jobs cannot bury the one
            # that missed -- while the count still shows the healthy half was READ rather
            # than skipped, which is the distinction an absent line cannot make.
            lines.extend(render_cadence_slot(cov))
        elif leg["name"] == "board-close":
            if leg["status"] != "ASSERTED":
                # A NOT RUN / REFUSED bound is neither a pass nor a silence: the leg says
                # which it is and why, so a reader can act on it. The population line is
                # not printed because there is no population — the bound that defines it
                # could not be read.
                lines.append(
                    f"  {leg['status']}: {cov.get('reason') or 'reason not stated'}"
                )
            else:
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
            if leg["status"] != "ASSERTED":
                lines.append(
                    f"  {leg['status']}: {cov.get('reason') or 'reason not stated'}"
                )
            else:
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
                f"owns, {len(cov['dated_not_boundary_rows'])} carry a bare date and "
                f"{len(cov.get('cited_instant_rows', []))} an instant in a CITATION (both "
                f"citations of the past, reported and never judged)"
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
            for row in cov.get("cited_instant_rows", []):
                owner = row["owner"] or row["home"] or "unknown"
                lines.append(
                    f"    instant in a citation: {row['name']} (owner {owner}) cites "
                    f"{row['instant']} — a reference to when something was decided, not a "
                    f"boundary the prompt asserts"
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
            # #537 (ruling n=4009): the corroboration line. It prints on the leg's OWN
            # surface, beside the population it qualifies, so an excuse-heavy round is
            # visible as one and a round whose run table could not corroborate is never
            # mistaken for a round that found nothing (#271).
            lines.append(
                f"  corroboration: {cov.get('run_rows_read', 0)} run row(s) covering "
                f"{cov.get('jobs_corroborable', 0)} job(s) — "
                f"{cov.get('logs_uncorroborated', 0)} log(s) EXCUSED as uncorroborated, "
                f"{cov.get('logs_corroboration_degraded', 0)} judged on the FILENAME PROXY "
                f"alone (declared degradation)"
            )
            for row in cov.get("uncorroborated_logs", []):
                lines.append(
                    f"    uncorroborated: {row['job']} (cron id {row['id'] or 'unstated'}) "
                    f"— {row['path']} carries the stamp "
                    f"{row.get('stamp') or 'no parseable stamp'}, and none of this job's "
                    f"{row.get('runs_of_job', 0)} run(s) covers it; the filename nominates "
                    f"the job, the record does not attribute the file — EXCUSED, never a "
                    f"failed dispatch"
                )
            for row in cov.get("corroboration_degraded_logs", []):
                lines.append(
                    f"    degradation: {row['job']} (cron id {row['id'] or 'unstated'}) "
                    f"— {row['path']} (stamp {row.get('stamp') or 'unparseable'}) is judged "
                    f"on the FILENAME PROXY because this job carries NO run rows to "
                    f"corroborate it against; the excuse this leg grants is a statement "
                    f"about the READ, and it is printed here so it can never be read as a "
                    f"clean box"
                )
            lines.append(
                f"  corroboration predicate: {cov.get('corroboration_predicate', 'predicate unstated')}"
            )
            for row in cov.get("not_attempted_logs", []):
                verdict = (
                    f"its run did NOT complete (status {row.get('run_status')}"
                    + (
                        f", {row.get('run_started')} -> {row.get('run_completed') or 'no completion stamp'}"
                        if row.get("run_started") else ""
                    )
                    + ")"
                    if row.get("run_status") else
                    "NO run row could be matched to its own stamp, so the excuse rests on "
                    "an unread surface rather than on a run that did not finish"
                )
                lines.append(
                    f"    no attempt: {row['job']} (cron id {row['id'] or 'unstated'}) — "
                    f"{row['path']} carries no output; {verdict}; reported, never a failed duty"
                )
            lines.append(
                f"  no-attempt predicate: {cov.get('not_attempted_predicate', 'predicate unstated')}"
            )
            lines.append(
                f"  no-attempt logs matched to NO run: "
                f"{cov.get('logs_not_attempted_unattributed', 0)} of "
                f"{cov.get('logs_not_attempted', 0)} — a 0-byte log with no run to judge is "
                f"a statement about the READ, and it is printed here so it can never be "
                f"read as a box with no failed notify (#306)"
            )
            for row in cov.get("unattributed_not_attempted_logs", []):
                lines.append(
                    f"    unmatched 0-byte log: {row['job']} ({row['path']}) — no run row of "
                    f"this job contains its stamp {row.get('path', '').rsplit('-', 1)[-1]}"
                )
            if cov.get("logs_completed_with_empty_log"):
                lines.append(
                    f"  COMPLETED runs with a 0-byte log: "
                    f"{cov['logs_completed_with_empty_log']} — the notify was launched and "
                    f"produced no output, so these are FAILED DUTIES (#306)"
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
                f"{cov['jobs_owing_none']} declare they OWE NONE, "
                f"{cov['jobs_undeclared']} declare NOTHING and are NOT JUDGED, "
                f"{cov['jobs_unattributed']} attributed to nobody"
            )
            for name in cov.get("owes_none_jobs", []):
                lines.append(
                    f"    OWES NONE — declares `receipt_subject: none`, so this duty owes no "
                    f"receipt and is NOT JUDGED: {name or '(unnamed row)'}"
                )
            for name in cov.get("undeclared_jobs", []):
                lines.append(
                    f"    NOT JUDGED — declares no `receipt_subject:` and is named in no "
                    f"declared exemption, so this leg cannot tell whether it owes one "
                    f"(a PROBLEM since #506): {name or '(unnamed row)'}"
                )
            # #506. Both new buckets print on EVERY run, an explicit 0 included: a count
            # that appears only when non-zero is indistinguishable from one the reader never
            # computed, which is the class that hid this defect for a round.
            malformed = cov.get("malformed_jobs", [])
            shapes = cov.get("malformed_shapes", [])
            lines.append(
                f"    malformed declarations: {len(malformed)} "
                f"(a `receipt_subject` the canonical line cannot parse — a PROBLEM)"
            )
            for name, shape in zip(malformed, shapes):
                lines.append(
                    f"    MALFORMED — the declaration is not canonical ({shape}), so the "
                    f"duty is NOT JUDGED: {name or '(unnamed row)'}"
                )
            exempt = cov.get("undeclared_exempt_jobs", [])
            lines.append(
                f"    declared exemptions: {len(exempt)} "
                f"(NOT JUDGED on this factory's own declaration, printed as debt)"
            )
            for name in exempt:
                lines.append(
                    f"    NOT JUDGED by DECLARED EXEMPTION "
                    f"(docs/duty-receipt-exemptions.json): {name or '(unnamed row)'}"
                )
            # #506 ruling n=3527 criterion 3. An exemption naming no undeclared duty is debt
            # that has stopped describing the box: printed, never subtracted, so a store that
            # has rotted into a rubber stamp is visible on every round.
            stale = cov.get("stale_exempt_jobs", [])
            lines.append(
                f"    stale exemptions: {len(stale)} "
                f"(an exemption naming no undeclared duty — a PROBLEM since #506)"
            )
            for name in stale:
                lines.append(
                    f"    STALE EXEMPTION — names no undeclared duty on this box, so it "
                    f"excuses nothing (docs/duty-receipt-exemptions.json): {name or '(unnamed)'}"
                )
            for duty in cov.get("duties_judged", []):
                lines.append(
                    f"    {duty['name']} (cron id {duty['id']}): round {duty['round']} "
                    f"(fired {duty['fired'] or 'unstated'}) — "
                    f"{duty['rows_matched']} row(s) match the round's subject, "
                    f"{duty['receipts']} DECLARE a completion"
                    + (
                        f" [the PRIOR round: the newest round {duty['fallback_from']} is "
                        f"still in flight and is NOT JUDGED (#281)]"
                        if duty.get("fallback_from") else ""
                    )
                )
            lines.append(
                f"  backward bound `{DUTY_RECEIPT_BOUNDARY_KEY}`: "
                f"{cov.get('bound') or 'UNDECLARED'}"
            )
            residuals = cov.get("residuals") or []
            if residuals:
                lines.append(
                    f"  forward residual: PER JOB, DERIVED (#449) — {len(residuals)} "
                    f"declared job(s); a round younger than ITS OWN job's residual is IN "
                    f"FLIGHT and NOT JUDGED"
                )
                for res in residuals:
                    lines.append(
                        f"    {res['name']} (cron id {res['id']}): "
                        f"{duty_age_text(res['residual_secs'])} "
                        f"({res['residual_secs']:.0f} s) — "
                        f"{duty_residual_basis_text(res)}"
                    )
                    if res.get("over_cadence"):
                        cadence = res.get("cadence_secs")
                        lines.append(
                            f"      OVER CADENCE: this residual reaches the job's own "
                            f"observed cadence "
                            f"{duty_age_text(cadence) if cadence else 'UNDECLARED'} — it "
                            f"cannot discriminate for this duty (a residual covering the "
                            f"observed max outlives the next fire). PRINTED, never refused, "
                            f"and never clamped to the cadence: clamping would hide the "
                            f"mutually-unsatisfiable pair rather than report it"
                        )
                lines.append(
                    f"    DEFAULT for a job with no measurable round: "
                    f"{duty_age_text(cov.get('residual_default_secs'))} "
                    f"({cov.get('residual_default_secs')} s) — {cov.get('residual_form')}"
                )
            else:
                lines.append(
                    "  forward residual: NONE APPLIED — this leg judged no round, so no "
                    "window was derived (a leg that judges nothing owes no bound)"
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
            if cov.get("rounds_judged_by_fallback"):
                lines.append(
                    f"    {cov['rounds_judged_by_fallback']} round(s) were judged as the "
                    f"PRIOR fire's round, because the newest round of that job was still in "
                    f"flight — NAMED above, and the round judged is the one the PREVIOUS "
                    f"fire woke"
                )
            # #499: the fires/receipts comparison, PRINTED on a clean round as an explicit
            # zero -- a round that fired once and was receipted once reads `1 of 1`, and a
            # reader who sees no line at all cannot tell that from a leg that never counted.
            if cov.get("rounds_under_receipted"):
                lines.append(
                    f"    {cov['rounds_under_receipted']} round(s) are UNDER-RECEIPTED: "
                    f"{cov['fires_unanswered']} fire(s) owed a receipt and found none, each "
                    f"NAMED with its own instant above — the job RAN and its lane did not "
                    f"report"
                )
            else:
                lines.append(
                    f"    fires vs receipts: 0 fire(s) left unanswered across every judged "
                    f"round — each fire on a judged round carried a receipt token"
                )
            if cov.get("rounds_prior_unreadable"):
                lines.append(
                    f"    {cov['rounds_prior_unreadable']} job(s) had NO round judged: the "
                    f"newest round is in flight and this job's OWN run record dates no "
                    f"earlier fire, so no prior round can be NAMED — NOT JUDGED with its "
                    f"reason, never a composed instant and never a clean verdict"
                )
            if cov.get("rounds_excused_by_suppression"):
                lines.append(
                    f"    {cov['rounds_excused_by_suppression']} round(s) were SUPPRESSED by "
                    f"their OWN trigger gate and are excused by that, NAMED above — the "
                    f"daemon's own run record reads `{CRON_SUPPRESSION_MARKER}`, so no duty "
                    f"was ever owed and there is nothing to backfill (#477)"
                )
            if cov.get("receipts_malformed"):
                lines.append(
                    f"    {cov['receipts_malformed']} row(s) carry a `duty=` token in their "
                    f"OWN VOICE that this reader cannot reach — MALFORMED RECEIPT, NAMED "
                    f"above: the declaration is real, the token is outside the row's "
                    f"canonical terminal run, and the repair is to make it terminal"
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
                if cov.get("behind"):
                    lines.append(
                        "  BEHIND: HEAD is a pure ancestor of the remote tip — a stale "
                        "checkout with nothing of its own to publish (not a divergence)"
                    )
                lines.append(
                    f"  residual window: {cov.get('residual_secs', 0)}s "
                    f"({cov.get('cadence_secs', 0)}s cadence + {cov.get('grace_secs', 0)}s "
                    f"grace); {len(cov.get('stale') or [])} commit(s) past it"
                )
                bounds_label = cov.get('bounds_label', 'the pusher\u2019s own')
                lines.append(f"  those bounds are {bounds_label}")
                lines.append(f"  SCOPE: {cov.get('leg_scope', '')}")
                # THE BINDING ARM (#468). Guarded on the arm's own key, so a leg injected
                # for a probe -- which carries no binding block -- renders without inventing
                # one, and an arm that could not run says so instead of reading clean.
                binding = cov.get("binding")
                if binding is not None:
                    if binding.get("binding_reason"):
                        lines.append(
                            f"  binding freshness: NOT RUN — {binding['binding_reason']}"
                        )
                    else:
                        lines.append(
                            f"  binding freshness: {len(binding.get('rows') or [])} "
                            f"binding(s) against {binding.get('reference_ref')} "
                            f"({binding.get('reference_source')}), "
                            f"{len(binding.get('stale') or [])} stale law file(s)"
                        )
                        for row in binding.get("rows") or []:
                            lines.append(
                                f"    {row.get('skill')} [{row.get('form')}]: "
                                f"{row.get('resolution')} -> "
                                f"{row.get('resolves_to') or 'nothing resolved'}"
                            )
                            for item in row.get("files") or []:
                                if item.get("status") != "equal":
                                    lines.append(
                                        f"      {item.get('status')}: {item.get('path')} — "
                                        f"loaded {item.get('loaded')} vs "
                                        f"{item.get('at_reference') or 'absent'} at the "
                                        f"reference"
                                    )
                        for name in binding.get("missing_local") or []:
                            lines.append(f"    MISSING FROM THE LOADED TREE: {name}")
                        lines.append(f"    scope: {binding.get('scope', '')}")
                        lines.append(
                            f"    reference residual: {binding.get('reference_residual', '')}"
                        )
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
                # WHERE THE RECORD LIVES, WHICH CHECKOUT IS READING IT, AND WHO WROTE IT
                # (#445). The receipt is ONE record per repository, so the reading checkout
                # and the receipt's origin are different questions; both are printed, and the
                # last-writer-wins residual is STATED rather than left for a reader to infer.
                lines.append(
                    f"  receipt file: {cov.get('receipt_path') or 'unresolvable (git common dir unreadable)'}"
                )
                lines.append(f"  reading checkout: {cov.get('reading_checkout', 'unknown')}")
                if rec and rec.get("origin_checkout"):
                    lines.append(f"  receipt origin checkout: {rec['origin_checkout']}")
                elif rec:
                    lines.append(
                        "  receipt origin checkout: not recorded (written before #445)"
                    )
                lines.append(f"  receipt residual: {cov.get('receipt_residual', '')}")
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
                        # The reason is printed because a missing root and an unreadable one
                        # are the same class and DIFFERENT remedies (#429): a stale fleet
                        # entry versus a permissions problem on the member's box. A bare
                        # UNREACHABLE tells the reader which, but not why.
                        why = member.get("reason") or "absent from this box"
                        lines.append(
                            f"    {member['slug']}: UNREACHABLE ({member['root']}) — {why}"
                        )
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
            if cov.get("bound_refusal"):
                lines.append(
                    f"  rulings issued on the board (openings {', '.join(cov['headings'])}): "
                    f"{cov['rulings_issued']} examined over {cov['issues_read']} "
                    f"issue(s) read — NOT JUDGED, the bound is refused — board read at "
                    f"{cov['board_read_at']}"
                )
            else:
                lines.append(
                    f"  rulings issued on the board (openings {', '.join(cov['headings'])}): "
                    f"{cov['rulings_issued']} examined over {cov['issues_read']} "
                    f"issue(s) read, {len(leg['problems'])} problem(s) — board read at "
                    f"{cov['board_read_at']}"
                )
                # The bound and the exemptions are PRINTED with their basis (#243): an
                # exclusion that is not printed cannot be told from a miss, and the reader
                # must see WHICH instant this run judged against, and what it excused,
                # without opening the source.
                lines.append(
                    f"  bound: {cov['bound']} for `{cov['bound_key']}` — "
                    f"{cov['pre_boundary_rulings']} ruling comment(s) earlier than it are "
                    f"NOT JUDGED (no row could be paired before the pairing mechanism "
                    f"existed, and NO BACKFILL bars writing one now)"
                )
                lines.append(
                    f"  exemptions ({cov['exemptions_path']}): "
                    f"{cov['exemptions_declared']} declared, "
                    f"{len(cov['exemptions_matched'])} matched this population"
                )
            # THE LEDGER SIDE, PRINTED WITH ITS PARTITION (#545, ruling n=4096). The rows
            # read are a row counter, never a sum of the sets built from them: `#50` alone
            # carries six `ruling` rows, so the distinct count alone cannot be reconciled
            # against the ledger by a reader. Both closures are visible here, on the run.
            lines.append(
                f"  ledger side: {cov['rulings_read']} ruling row(s) read — "
                f"{cov['rulings_resolved_rows']} resolved to an issue, over "
                f"{cov['rulings_resolved']} DISTINCT issue(s); {cov['rulings_repeated']} "
                f"are REPEATED re-rulings the append-only ledger keeps (a later ruling "
                f"supersedes an earlier one — NOT de-duplicated, and never a defect); "
                f"{cov['rulings_unbridgeable']} unbridgeable"
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
            # A problem counted and never itemised is a problem the operator cannot act on:
            # the verdict line carries the count, these lines carry the instance.
            lines.append(f"  excused: {len(leg['excused'])}")
            lines.append(f"  problems: {len(leg['problems'])}")
            for problem in leg["problems"]:
                lines.append(f"    - {problem}")
            for excuse in leg["excused"]:
                lines.append(f"    excused: {excuse}")
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
                f"{cov['mentions_rejected']} of their token(s) named only in the BODY "
                f"and read as a MENTION, never as a routing (#467); "
                f"{cov['units_off_board']} unit(s) dropped as not an OPEN issue of this "
                f"board)"
            )
            lines.append(
                f"  population: {cov['units_in_population']} dispatched unit(s) -- "
                f"{cov['units_owed']} never claimed past the declared threshold of "
                f"{cov['threshold_days']} d"
            )
            # THE MENTION POPULATION IS PRINTED BESIDE THE ROUTED ONE (#470): the population
            # admits ROUTED units alone, so a reader must be able to see how many units the
            # harvest saw and refused the population slot -- a narrowed read that hides what
            # it dropped is the failure this leg exists to catch.
            lines.append(
                f"  mentions: {cov['units_named_only_as_mentions']} unit(s) named by a "
                f"dispatch row that never ROUTED them (their tokens stand in the BODY, not "
                f"in the row's opening line) -- admitted to no population, dated by no row, "
                f"and holding no park back (#470)"
            )
            # THE DRAIN EVIDENCE IS PRINTED BESIDE THE OWED TOTAL (#465 criterion 1): a bare
            # "9 OWED" reads as nine independent findings, and where the addressee lane is
            # ALIVE that reading is wrong. The line prints even at zero, so a leg that found
            # no drain is distinguishable from one that never looked.
            #
            # THE SPLIT IS PRINTED, NOT AVERAGED (#546 change 3): a lane with in-window claims
            # is ALIVE, and whether it DRAINS A QUEUE is a second question -- a lane whose
            # claims are out of dispatch order is named `NOT-A-QUEUE` on its own line, because
            # that is the shape that makes the #465 warrant false and it used to read healthy.
            lines.append(
                f"  drain evidence (the addressee lane's own claims on a SIBLING of the "
                f"same standing set, inside the last {cov['threshold_days']} d): "
                + (
                    f"{cov['lanes_draining']} lane(s) ALIVE with claims inside the window -- "
                    f"{cov['lanes_draining_a_queue']} draining a QUEUE, "
                    f"{cov['lanes_not_a_queue']} NOT-A-QUEUE (claims out of dispatch order) "
                    f"-- {cov['units_owed_on_draining_lanes']} of {cov['units_owed']} OWED "
                    f"unit(s) sit on one. The remedy keys on the CLAIM, never on the drain "
                    f"(#546)"
                    if cov["lanes_draining"]
                    else "no lane carrying an OWED unit claimed a sibling inside the window"
                )
            )
            for note in cov.get("lane_drain", []):
                lines.append(f"    {note}")
            # THE PARK EXCLUSION IS PRINTED BESIDE THE VERDICT (#331 clause 1), never left
            # to be inferred from a total that is smaller than the population: a reader who
            # cannot see WHY a dispatched unit left the owed count cannot tell a declared
            # park from a dropped unit. The line prints even at zero, so a leg that read no
            # declarations is distinguishable from one whose declarations it could not see.
            lines.append(
                f"  parks (park:owner:<question> on the unit's own rows): "
                f"{cov['parks_declared']} declared, {cov['units_parked']} OWED unit(s) held "
                f"PARKED and EXCLUDED from the owed total"
                + (
                    f", {cov['units_park_superseded']} SUPERSEDED by a later dispatch"
                    if cov["units_park_superseded"]
                    else ""
                )
            )
            for note in cov.get("parks", []):
                lines.append(f"    {note}")
            # THE DISPOSITION EXCLUSION IS PRINTED BESIDE THE VERDICT (#473), for the same
            # reason: a unit ruled void is not a finding, and a reader who cannot see WHY it
            # left the owed count cannot tell a ruled-away unit from a dropped one. The line
            # prints even at zero, so a leg that read no rulings is distinguishable from one
            # whose rulings it could not see.
            lines.append(
                f"  dispositions (disposition:void on the unit's own rows): "
                f"{cov['dispositions_declared']} declared, {cov['units_voided']} OWED "
                f"unit(s) ruled VOID and EXCLUDED from the owed total"
                + (
                    f", {cov['units_disposition_superseded']} SUPERSEDED by a later dispatch"
                    if cov["units_disposition_superseded"]
                    else ""
                )
            )
            for note in cov.get("dispositions", []):
                lines.append(f"    {note}")
            # ... and the ADDRESSEE coverage (#331 clause 2), so a run where NOTHING
            # resolved is not read as a run that never asked.
            lines.append(
                f"  addressee: {cov['addressees_resolved']} of {cov['units_owed']} OWED "
                f"unit(s) name the lane the work was handed to; "
                f"{cov['addressees_unresolved']} declare none"
            )
            # THE BACKLOG GROUPED BY ADDRESSEE IS PRINTED HERE (#133): it is the population
            # the driverless-lane leg asks about, so a reader can see the grouping without
            # opening that leg's block, and the two legs cannot disagree about whose lane a
            # unit sits on.
            lines.append(
                f"  backlog by addressee: {cov['lanes_with_backlog']} lane(s) carry the "
                f"{cov['units_owed']} OWED unit(s)"
            )
            for slot in cov.get("owed_by_lane") or []:
                label = slot.get("lane") or "ROUTING UNRESOLVED"
                lines.append(
                    f"    {label}: {len(slot.get('units') or [])} unit(s), oldest "
                    f"{float(slot.get('oldest_age_days') or 0.0):.2f} d — "
                    f"{', '.join(slot.get('units') or [])}"
                )
            lines.append(f"  threshold basis: {cov['threshold_basis']}")
            lines.append(f"  read at {cov['read_at']}")
        elif leg["name"] == "driverless-lane":
            # A leg that did NOT RUN says WHY, and never renders as a clean population
            # (#133): an unasked question and a lane with nothing on it must not read alike.
            if cov.get("reason"):
                lines.append(f"  NOT RUN: {cov['reason']}")
                if cov.get("census_status"):
                    lines.append(f"  census status this round: {cov['census_status']}")
            else:
                lines.append(
                    f"  population: {cov['lanes_with_backlog']} lane(s) carrying an "
                    f"unclaimed backlog ({cov['backlog_units']} unit(s)); "
                    f"{cov['lanes_judged']} judged by their own goal row, "
                    f"{cov['lanes_routing_unresolved']} skipped because the census could "
                    f"not resolve a routing to a lane"
                )
                # THE FOUR READINGS PRINT WITH THEIR ZEROS, so a round that found no
                # driverless lane is distinguishable from one that never looked.
                # EACH LABEL NAMES ITS OWN PREDICATE, and DRIVERLESS deliberately does not
                # claim "no goal row": the card reads a lane with a STOPPED loop as
                # DRIVERLESS too (a paused row is not a driver), so a label asserting an
                # absent row would sit beside a row the very next line prints. The reading
                # is about whether anything will EVALUATE the lane, not whether a row exists.
                # (#532) NO LABEL ASSERTS THE FUTURE: DRIVERLESS says "no measured work
                # since T", never "nothing will evaluate it again" -- the ledger carried 33
                # `close` rows from a lane whose goal row had stopped five days earlier.
                lines.append(
                    f"  readings: {cov['driven']} DRIVEN (advancing, or a turn in flight), "
                    f"{cov['armed_inert']} ARMED-INERT (active arm never evaluated), "
                    f"{cov['driverless']} DRIVERLESS (no active row, no turn in flight, and "
                    f"no measured work inside the window), "
                    f"{cov['unarmed_active']} UNARMED-ACTIVE (no active row, but measured "
                    f"work inside the window), "
                    f"{cov['unreadable']} UNREADABLE (the activity source could not be read)"
                )
                # THE WINDOW AND ITS BASIS, printed on every run: the reading that says
                # "inside the window" is worthless if the window is unnamed, and this one is
                # the census's constant, not this leg's own (#532, criterion 3).
                lines.append(
                    f"  activity window: {cov['activity_window_days']:g} day(s) — "
                    f"{cov['activity_window_basis']}"
                )
                lines.append(
                    f"  turns in flight: {cov.get('lanes_with_a_turn_in_flight', 0)} of "
                    f"{cov['lanes_judged']} judged lane(s)"
                )
                for entry in cov.get("lanes") or []:
                    state = entry.get("state") or "no goal row"
                    # (#532) THE ACTIVITY INSTANT IS ON EVERY LINE, not only on the new
                    # reading: "no work since T" is the claim DRIVERLESS now makes, and a
                    # line that omits T leaves a reader unable to tell it from "not read".
                    lines.append(
                        f"    {entry['reading']}: {entry['lane']} — state `{state}`, "
                        f"turns used {entry.get('turns_used')}, last touched "
                        f"{entry.get('updated_at')}, turn in flight "
                        f"{'yes' if entry.get('turn_open') else 'no'}, "
                        f"work measured at {entry.get('activity_instant')} "
                        f"({entry.get('activity_state')}), "
                        f"{len(entry.get('units') or [])} "
                        f"unclaimed unit(s) ({', '.join(entry.get('units') or [])})"
                    )
                # THE STORE POPULATION IS PRINTED, because a driverless reading is only as
                # good as the read behind it: a home whose `goal_state` could not be opened
                # would otherwise make every lane look driverless.
                lines.append(
                    f"  goal store: {cov['goal_rows_read']} row(s) read from "
                    f"{len(cov.get('goal_homes_read') or [])} home(s)"
                    + (
                        f"; {len(cov['goal_homes_without_store'])} home(s) carry no "
                        f"goal_state table ({', '.join(cov['goal_homes_without_store'])})"
                        if cov.get("goal_homes_without_store")
                        else ""
                    )
                    + (
                        f"; {len(cov['goal_homes_unreached'])} UNREACHED "
                        f"({', '.join(cov['goal_homes_unreached'])}) — a lane on an "
                        f"unreached home reads DRIVERLESS for want of a read, not for want "
                        f"of a driver"
                        if cov.get("goal_homes_unreached")
                        else ""
                    )
                )
                # THE ACTIVITY STORE IS PRINTED for the same reason the goal store is: an
                # unreadable activity source must read as "could not look", never as zero
                # work (#271) -- otherwise every lane on an unopened home reads DRIVERLESS.
                lines.append(
                    f"  activity store: {'READ' if cov.get('activity_readable') else 'UNREADABLE'}"
                    f" — {len(cov.get('activity_homes_read') or [])} home(s) read"
                    + (
                        f"; {len(cov['activity_homes_without_store'])} home(s) carry no "
                        f"tool_executions table "
                        f"({', '.join(cov['activity_homes_without_store'])})"
                        if cov.get("activity_homes_without_store")
                        else ""
                    )
                    + (
                        f"; {len(cov['activity_homes_unreached'])} UNREACHED "
                        f"({', '.join(cov['activity_homes_unreached'])})"
                        if cov.get("activity_homes_unreached")
                        else ""
                    )
                    + (
                        f"; {len(cov['activity_instants_unparsed'])} instant(s) unparsed"
                        if cov.get("activity_instants_unparsed")
                        else ""
                    )
                    + (
                        f" — REASON: {cov['activity_reason']}"
                        if cov.get("activity_reason")
                        else ""
                    )
                )
                lines.append(
                    "  remedy: the ACT is the lane's own or the sweep owner's — this leg "
                    "DETECTS and prints, and MUST NOT re-arm another lane's goal (#133). "
                    "A re-arm is REFUSED for UNARMED-ACTIVE: a lane with measured work "
                    "inside the window does not need a driver installed (#532)"
                )
            lines.append(f"  read at {cov.get('read_at')}")
        elif leg["name"] == "board-unruled":
            # The population is PRINTED BESIDE THE VERDICT (acceptance criterion 2), so an
            # empty sweep reads as "examined 0, 0 problems" rather than as silence -- which
            # is the failure #332 records: a skipped item reads clean.
            lines.append(
                f"  board: {cov['board_items_read']} item(s) read, "
                f"{cov['open_items_examined']} OPEN; intake rows read: "
                f"{cov['intake_rows_read']} ({cov['intake_rows_resolved']} naming an "
                f"issue); ruling rows read: {cov['ruling_rows_read']} "
                f"({cov['rulings_resolved_rows']} resolved to an issue, over "
                f"{cov['rulings_resolved']} DISTINCT issue(s) "
                f"[strict {cov['resolution_arms']['strict']}, declared "
                f"{cov['resolution_arms']['declared']}, bridged "
                f"{cov['resolution_arms']['bridged']}]; {cov['rulings_repeated']} are "
                f"REPEATED re-rulings of an issue already ruled, which the append-only "
                f"ledger keeps and this leg does NOT de-duplicate; "
                f"{cov['rulings_unbridgeable']} unbridgeable)"
            )
            for entry in cov.get("bridged_via", []):
                lines.append(
                    f"    BRIDGED #{entry['issue']} via ruling n={entry['ruling_n']} "
                    f"-- supplied by row n={entry['via_n']} ({entry['via_event']})"
                )
            lines.append(
                f"  population (OPEN, intake row, NO ruling row): "
                f"{cov['population_unruled']} item(s) -- {cov['items_owed_ruling']} past "
                f"the declared threshold of {cov['threshold_hours']} h"
            )
            for entry in cov.get("population", []):
                lines.append(
                    f"    #{entry['issue']} (intake n={entry['intake_n']} at "
                    f"{entry['intake_ts']}): {entry['age_hours']:.2f} h unruled -- "
                    f"{'OWED' if entry['owed'] else 'in flight'}"
                )
            lines.append(f"  threshold basis: {cov['threshold_basis']}")
            lines.append(f"  board read at {cov['board_read_at']}")
        elif leg["name"] == "undispatched-ruling":
            # EVERY BUCKET PRINTS ITS OWN PREDICATE (#163 half 2 (b)): `0 owed` and "a bucket
            # that cannot see one" must never render the same line, so the population is
            # printed beside the verdict and each exclusion carries the predicate that made it.
            lines.append(
                f"  board: {cov['board_items_read']} item(s) read, "
                f"{cov['open_items_examined']} OPEN; ruling rows read: "
                f"{cov['ruling_rows_read']} ({cov['rulings_resolved_rows']} resolved to an "
                f"issue, over {cov['rulings_resolved']} DISTINCT issue(s) — "
                f"{cov['rulings_repeated']} REPEATED re-rulings, kept by the append-only "
                f"ledger and never de-duplicated; {cov['rulings_unbridgeable']} unbridgeable)"
            )
            lines.append(
                f"  population ({cov['population_predicate']}): "
                f"{cov['population_undispatched']} item(s) -- "
                f"{cov['items_owed_dispatch']} owed a dispatch"
            )
            for entry in cov.get("owed", []):
                lines.append(f"    OWED #{entry}")
            lines.append(
                f"  named only in a dispatch row's BODY (#467): "
                f"{cov['items_named_in_body_only']} item(s) -- a mention is not a dispatch, "
                f"and not this leg's debt either"
            )
            lines.append(
                f"  resolved by a DECLARED batch act: "
                f"{cov['items_resolved_by_batch']} item(s) -- {cov['batch_predicate']}"
            )
            # THE DECLARATION'S OWN STATE IS PRINTED, because an absent record and an
            # unreadable one both resolve nothing and are NOT the same fact: absent is a
            # factory that has declared no batch, unreadable is a defect in one that exists.
            lines.append(
                f"  batch declaration: {cov['batch_refusal'] or 'READ'}"
            )
            lines.append(f"  board read at {cov['board_read_at']}")
        elif leg["name"] == "dispatch-delivery":
            # THE EXAMINED POPULATION IS PRINTED BESIDE THE VERDICT (acceptance criterion 3),
            # so `examined 33, 0 problems` is never the same output as `examined 0` -- the
            # confident zero the ruling names as worse than no leg at all.
            lines.append(
                f"  dispatch rows read: {cov['dispatch_rows_read']} "
                f"({cov['dispatch_rows_pre_boundary']} before the bound "
                f"`{cov['bound_key']}` = {cov['bound']}, not judged; "
                f"{cov['dispatch_rows_undated']} undated; "
                f"{cov['dispatch_rows_not_judged']} carry no target, NOT JUDGED); "
                f"examined: {cov['dispatch_rows_examined']}"
            )
            # THE ANCHOR IS PRINTED (#432): a window built from a row's WRITE stamp and one
            # built from an instant the row DECLARES are different judgements, and a reader
            # who cannot tell which was used cannot tell a clean sweep from a narrow window.
            lines.append(
                f"  window anchors: {cov.get('dispatch_rows_declared_anchor', 0)} of "
                f"{cov['dispatch_rows_examined']} examined row(s) anchored on an instant the "
                f"row itself DECLARES, the rest on the row's write stamp (#432)"
            )
            # THE SCOPING IS PRINTED ONCE AS A FIGURE, never as N lines (#538): on the
            # 2026-10-21 read 57 of the 96 problem rows were dispatches for items the board
            # had already closed, so naming each one buried the six that were still live.
            # The board read that produced the figure travels with it, because a zero here
            # means "nothing closed" only when a board was actually read.
            lines.append(
                f"  scoped OUT as history: {cov.get('dispatch_rows_closed_subject', 0)} "
                f"dispatch row(s) name board items the board reports CLOSED "
                f"(judged_closed_subject), against a board read of "
                f"{cov.get('board_items_read', 0)} item(s) carrying "
                f"{cov.get('board_closed_items', 0)} closed"
                + ("" if cov.get("board_read") else " -- NO BOARD WAS INJECTED, so nothing "
                   "was scoped out and every row was judged (#538)")
            )
            if cov.get("delivered_outside_window"):
                # A DELIVERY THAT EXISTS IS NOT A DEBT (#538). The count is printed beside
                # the verdict and each instance prints as an EXCUSAL carrying its own
                # instant and window, so a reader can still see exactly what landed when --
                # and the branch must print them itself: the generic `excused` dump below
                # belongs to the legs with no branch of their own, and this leg has one.
                lines.append(
                    f"  delivered OUTSIDE the window (excused, never a problem): "
                    f"{cov['delivered_outside_window']} row(s) — a delivery EXISTS for each, "
                    f"so none is an absence (#538)"
                )
                for excuse in leg["excused"]:
                    lines.append(f"    excused: {excuse}")
            # THE MATCH COUNTS ARE PRINTED TOO, because the horizon SILENTLY decides whether a
            # subject mention is a delivery: `3 of 47` tells a reader that 44 messages carried
            # the subject and were not counted, which is the difference between a narrow
            # predicate and a blind one (#116).
            if cov.get("store_read"):
                lines.append(
                    f"  subject matches: {cov.get('subject_matches_within_horizon', 0)} within "
                    f"the {cov.get('match_horizon_secs')} s horizon of "
                    f"{cov.get('subject_matches_anywhere', 0)} anywhere in the store(s) "
                    f"(#432)"
                )
                # A MATCH IS SPLIT BY WHERE THE TOKEN SITS (#433): only a HEADER match
                # corroborates a dispatch row, so the count a reader needs is not "how many
                # messages carried the subject" but "how many NAMED it as the unit they route".
                # Printed beside the body-only count, because the difference IS the verdict.
                lines.append(
                    f"  subject matches in a delivery HEADER: "
                    f"{cov.get('dispatch_rows_corroborated', 0)} of "
                    f"{cov['dispatch_rows_examined']} examined row(s) corroborated by a header "
                    f"match; {cov.get('subject_mentions_body_only_within_horizon', 0)} "
                    f"body-only mention(s) within the horizon of "
                    f"{cov.get('subject_mentions_body_only', 0)} anywhere — a mention never "
                    f"corroborates (#433)"
                )
            if cov.get("store_read"):
                lines.append(
                    f"  deliveries read: {cov['deliveries_read']} "
                    f"({cov.get('deliveries_by_state', {}).get('landed', 0)} landed, "
                    f"{cov.get('deliveries_by_state', {}).get('queued', 0)} queued) across "
                    f"{cov['homes_read']} home(s) read"
                )
                if cov.get("homes_unreached"):
                    lines.append(
                        f"  homes UNREACHED ({len(cov['homes_unreached'])}) — judged only over "
                        f"what was read: {', '.join(cov['homes_unreached'])}"
                    )
            else:
                # A STORE THAT WAS NEVER OPENED MUST NOT RENDER AS ONE THAT HELD NOTHING:
                # `deliveries read: 0` would stand for both, and that is exactly the
                # confident zero this leg refuses. The not-read state gets its own line and
                # its own reason.
                lines.append(
                    f"  deliveries: NOT READ — "
                    f"{cov.get('store_not_read_reason') or 'the leg judged no row'}"
                )
            lines.append(f"  window: {cov['window_basis']}")
            lines.append(f"  read at {cov['read_at']}")
        elif leg["name"] == "workspace-blocked":
            # A lawful exception is a VISIBLE DEBT: the governed-run population and the
            # escape-hatch count are printed BESIDE the verdict, and a NOT RUN carries its
            # reason rather than reading as a clean zero (#201, #242).
            lines.append(
                f"  governed runs declaring a workspace gate: "
                f"{cov['runs_declaring_gate']} of {cov['rows_read']} ledger row(s) read; "
                f"{cov['blocked_declarations']} took the "
                f"{WORKSPACE_BLOCKED_TOKEN} escape hatch"
            )
            if leg["status"] == "NOT RUN":
                lines.append(f"  NOT RUN: {cov.get('reason') or 'reason not stated'}")
            for entry in cov.get("blocked_rows", []):
                if not entry["paths"]:
                    lines.append(
                        f"    n={entry['n']} ({entry['subject']}): NO paths named -- an "
                        f"unexaminable declaration"
                    )
                    continue
                lines.append(
                    f"    n={entry['n']} ({entry['subject']}): "
                    f"{len(entry['still_dirty'])} still dirty, "
                    f"{len(entry['no_longer_dirty'])} no longer dirty"
                )
                for path in entry["no_longer_dirty"]:
                    lines.append(
                        f"      no longer dirty (the live tree no longer corroborates this "
                        f"block): {path}"
                    )
        elif leg["name"] == "criterion-paths":
            # The population is PRINTED (#48 criterion 3): "examined N, M unresolved" is
            # never the same output as "examined 0", so a leg that read nothing does not
            # read as one that found everything clean. The EXCLUSION is printed beside it
            # for the same reason: a closed item's criteria are outside this leg by design,
            # and a reader must be able to see that they were dropped rather than missed.
            # A NOT RUN carries its reason: an unreadable tree is not a clean board (#450).
            if leg["status"] == "NOT RUN":
                lines.append(f"  NOT RUN: {cov.get('reason') or 'reason not stated'}")
                lines.append(f"  read at {cov.get('read_at') or 'unstated'}")
                lines.append(f"  excused: {len(leg['excused'])}")
                lines.append(f"  problems: {len(leg['problems'])}")
                lines.append("")
                continue
            lines.append(
                f"  criterion paths (issue body and ruling comment): "
                f"{cov['refs_examined']} reference(s) examined over "
                f"{cov['issues_read']} issue(s), {cov.get('unresolved', len(leg['problems']))} "
                f"unresolved, {cov.get('declared_exempt', 0)} declared-exempt, "
                f"{cov.get('cited', 0)} cited — "
                f"{cov['closed_items_excluded']} closed item(s) outside the population — "
                f"board read at {cov['read_at']}, judged against the tree at "
                f"{cov.get('read_rev') or 'an unrecorded revision'}"
            )
            # EVERY MATCHED EXEMPTION PRINTS, with its authority (#507): an exemption that
            # is counted but never shown is indistinguishable from a leg that skipped the
            # path, and the whole point of the store is that a reader can check it.
            for line in leg["excused"]:
                lines.append(f"  excused: {line}")
            # EVERY CITATION PRINTS, with its reason (#541, ruling n=4050): same discipline
            # one line up. A token the leg examined and did not judge is invisible unless it
            # is shown, and "clean" and "cited" must be different output rather than the same
            # one — otherwise a leg that dropped the token reads exactly like this one.
            for line in leg.get("cited") or []:
                lines.append(f"  cited: {line}")
        elif leg["name"] == "score-conversion":
            # THE POPULATION IS PRINTED (#112, section 8, #67): "no regression" and "no
            # artifact parsed" are the same verdict otherwise, and the second is the state
            # a broken parse produces. An ASSERTED read names the artifact it read, the
            # round it compared against, the cells it examined, which cells it EXCLUDED as
            # (UNM) -- and which regressions a ledger row answers, because a regression no
            # row answers reads as converted and is not.
            if leg["status"] != "ASSERTED":
                lines.append(
                    f"  {leg['status']}: {cov.get('reason') or 'reason not stated'}"
                )
            else:
                lines.append(
                    f"  artifact: {cov['artifact']} (compared against "
                    f"{cov.get('previous') or 'no earlier round'}) — "
                    f"{cov['factories']} factory scorecard(s), {cov['criteria_cells']} "
                    f"cell(s) examined, {cov['unmeasurable_cells']} excluded as (UNM), "
                    f"floor {cov['floor']} — {len(cov['regressions'])} regression(s): "
                    f"{', '.join(cov['regressions']) or 'none'}"
                )
                lines.append(
                    f"  conversion rows read: {cov['conversion_rows']} — answered: "
                    f"{', '.join(cov['answered']) or 'none'}; unanswered: "
                    f"{', '.join(cov['unanswered']) or 'none'}"
                )
                # #517: the lapsed population prints with its baseline, so "no lapse",
                # "no baseline" and "no artifact parsed" are three different lines rather
                # than one clean verdict.
                if cov.get("lapsed_reason"):
                    lines.append(f"  lapsed rounds: NOT RUN — {cov['lapsed_reason']}")
                else:
                    lapsed_entries = cov.get("lapsed") or []
                    lines.append(
                        f"  lapsed rounds since epoch {cov.get('lapsed_epoch')}: "
                        f"{cov.get('lapsed_population')} examined, "
                        f"{len(lapsed_entries)} lapsed — "
                        + (
                            "; ".join(
                                render_lapsed_entry(entry) for entry in lapsed_entries
                            )
                            or "none"
                        )
                    )
            lines.append(f"  read at {cov.get('read_at') or 'unstated'}")
        elif leg["name"] == "ledger-ref-roles":
            # THE POPULATION PRINTS, zeros included (#242): a leg that examined nothing and
            # one that examined the corpus and found it clean must never render the same.
            lines.append(
                f"  role assertions (a receipt naming the role of a row): "
                f"{cov['assertions_examined']} examined over {cov['rows_read']} ledger "
                f"row(s); roles judged: {'/'.join(cov['roles_judged'])}; "
                f"{len(cov['residuals'])} mismatch(es), {cov['exempted']} declared-exempt, "
                f"{cov['unresolved']} unresolved"
            )
            for residual in cov["residuals"]:
                lines.append(
                    f"    n={residual['row']} asserts `{residual['asserted']}` of "
                    f"n={residual['asserted_row']}, which is a "
                    f"`{residual['actual_event'] or 'MISSING'}` — "
                    + ("DECLARED-EXEMPT" if residual["declared"] else "UNRESOLVED")
                )
            lines.append(
                f"  declared exemptions: {cov['exemptions_declared']} "
                f"({REF_ROLE_EXEMPTIONS.name}; an entry matching no live mismatch is a "
                f"PROBLEM)"
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
    unruled = sum(
        int(leg["coverage"].get("items_owed_ruling", 0)) for leg in legs
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
        f"threshold, and {unruled} OPEN item(s) standing unruled (intaken, no `ruling` row)"
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

def leg_guard(name: str, build, read_at: str) -> dict:
    """Build ONE leg, and CONTAIN a raise so it cannot take the round down (#501).

    `main()` builds its legs EAGERLY, inside a single list literal, with no try/except
    between that literal and the exit-code line -- so an exception raised while building ANY
    leg aborts before the list is even complete, and every leg AFTER it never runs. Those
    legs leave no trace of their own: no NOT RUN line, no problem, no coverage count. That is
    the silent-failure class, and it is worse than a red leg because it is invisible.

    CONTAINMENT, not repair: the leg still FAILS, its problem still moves the exit code, and
    its verdict is UNKNOWN -- never clean. What changes is that its NEIGHBOURS still run and
    the round still prints a verdict.

    The NAME is passed in rather than derived: a leg that raised never returned the name it
    would have carried, so the caller states it -- and a probe asserts every name in the
    caller's table against a CLEAN round's own names, which is what keeps the table from
    drifting away from the legs it names.
    """
    try:
        return build()
    except Exception as exc:  # noqa: BLE001 -- containment is the whole point of this guard
        return {
            "name": name,
            "status": "FAILED",
            "problems": [
                f"the {name} leg RAISED while being built: {type(exc).__name__}: {exc} -- "
                f"it was contained so the round could finish, which means this leg's verdict "
                f"is UNKNOWN and NOT clean (board #501)"
            ],
            "excused": [],
            "coverage": {
                "reason": f"raised {type(exc).__name__}: {exc}",
                "exception": type(exc).__name__,
                "read_at": read_at,
            },
        }


def main(
    argv: list[str] | None = None,
    *,
    board_fn=fetch_board,
    slug_fn=remote_slug,
    rows_fn=load_rows,
    cron_rows_fn=box_cron_rows,
    cron_fires_fn=cron_run_fires,
    prefixes_fn=declared_prefixes,
    log_dir: Path = LOG_DIR,
    kit_manifest: Path | None = None,
    fleet_manifest: Path = FLEET_MANIFEST,
    predicate=None,
    publish_fn=None,
    worktree_fn=None,
    presence_fn=None,
    dirty_paths_fn=None,
    ruling_scope_fn=None,
    ruling_exemptions_path: Path | None = None,
    delivery_scope_fn=None,
    deliveries_fn=None,
    criterion_repo_fn=None,
    # #507: the criterion-path exemption store, injected for the same reason every other
    # declaration here is -- a probe must never have its verdict decided by whichever
    # exemptions the live factory happens to hold, and a probe that CANNOT drive an
    # exemption cannot prove the store is reconciled at all.
    criterion_exemptions_fn=None,
    scores_dir_fn=None,
    # #519: the batch-dispatch declaration, injected for the same reason every other
    # declaration here is -- a probe must never have its verdict decided by whichever
    # batches the live factory happens to have declared, and a probe that CANNOT drive a
    # declaration cannot prove the leg resolves anything at all.
    dispatch_batches_fn=None,
    board_scope_fn=None,
    duty_scope_fn=None,
    # #506: the declared-exemption store is injected for the sixth time and the same reason
    # every other declaration here is -- a probe must never have its verdict decided by
    # whichever exemptions the live factory happens to hold, and a probe that CANNOT drive
    # an exemption cannot prove the store is reconciled at all.
    duty_exemptions_fn=None,
    # #330: the ref-role exemption store, injected for the seventh time and the same
    # reason -- a probe must never have its verdict decided by whichever exemptions the
    # live factory happens to hold, and a probe that CANNOT drive an exemption cannot
    # prove the store is reconciled at all.
    ref_role_exemptions_path: Path | None = None,
    # #133: the box's goal store, injected for the eighth time and the same reason -- a probe
    # must never have its verdict decided by whichever goal rows this box happens to hold,
    # and a probe that CANNOT place a lane's goal row cannot prove a reading at all.
    driverless_goals_fn=None,
    # #133: "a turn is in flight" is a BINDING fact, so it is injected separately from the goal
    # store -- a probe must be able to put a turn in flight without inventing a goal row, since
    # the card's DRIVEN row admits that case precisely when the arm is inert.
    driverless_turn_open_fn=None,
    # #532: "was this session MEASURED doing anything" -- the fact the driverless reading was
    # missing. Injected for the ninth time and the same reason, and REQUIRED at the leg, so a
    # probe cannot silently read this box's live `tool_executions` and have its verdict decided
    # by whichever lanes happened to be busy.
    driverless_activity_fn=None,
    lane_names_fn=None,
    shared_tree_fn=None,
    out=print,
    err=print,
) -> int:
    """Run the patrol read. Every dependency is injectable, so a probe drives it
    without a live board — and a probe that can only run against the live board is
    a probe that cannot be run at all when the board is what is broken. The cron read
    and the prefix declaration are injected for the same reason: a probe drives the
    cron-thinness leg with NO live database. The cron FIRE history is injected for the
    same reason and one more (#449): the duty-receipt leg's forward window is now DERIVED
    per job from that job's own fire->receipt latencies, so a probe that read the live
    runs table would be asserting this box's own timings rather than the leg's arithmetic.
    The two drift manifests are injected for the
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
    cron legs receive.

    The workspace-blocked leg's tree read is injected for the eighth and the same reason: it
    shells out to `git status` in the live tree, so a probe that did not stub it would be
    measuring whatever paths this checkout happens to have dirty rather than the leg's
    behaviour. `dirty_paths_fn` returns the dirty path SET; the leg cross-reads the named
    paths against it.

    The board-ruling leg's BOUND is injected for the ninth and a reason of its own: the leg
    is bounded by a declaration in this tree (issue #334), and a probe that could only read
    the live declaration could not exercise a pre-boundary instance, a post-boundary one, or
    a REFUSED bound at all -- the three behaviours the bound exists to have. `ruling_scope_fn`
    returns the scope tuple; the live default reads this tree's declaration through the one
    boundary reader. `ruling_exemptions_path` is injected for the same reason: a probe must
    not have its verdict decided by whatever exemptions the live factory happens to hold.

    The delivery leg's TWO reads are injected for the tenth and the same practical reason as
    the ruling bound: `delivery_scope_fn` returns the bound tuple, so a probe can exercise a
    pre-boundary row, a post-boundary one, and a REFUSED bound without the live tree's
    declaration deciding its verdict; and `deliveries_fn` reads every OpenCrabs home's
    `messages` and `notify_queue` tables, so a probe that did not stub it would be measuring
    whatever this box happens to have delivered rather than the leg's behaviour.

    The criterion-path leg's TREE is injected for the eleventh and the same reason as the
    workspace-blocked leg's `dirty_paths_fn`: the leg resolves the paths a board criterion
    names against the tree at `read_at`, so a probe that did not inject it would be asserting
    whether the LIVE repo happens to hold `tools/x.py` rather than the leg's behaviour.
    `criterion_repo_fn` returns the tree root to resolve against; the live default is this
    repository.

    The three BOARD legs' bounds are injected for the twelfth and the last of the same
    reason: each judges a HISTORICAL population against a bound this tree declares, so a
    probe that could only read the live declaration could not exercise a pre-boundary
    instance, a post-boundary one, or a NOT RUN / REFUSED bound at all — and in the
    half of this byte-paired file that ships, no declaration exists, so a probe reading
    the live tree would assert an ADOPTING member's history rather than the leg's
    behaviour. `board_scope_fn(repo, key)` returns `(text, refusal, skip_reason)`; the live
    default reads this tree's declaration through the one boundary reader.

    The stall-census leg's SECOND read is injected for the thirteenth and the same reason
    again (#331): a park is declared on the unit's OWN rows, so it needs no separate
    injection -- the probe's own rows ARE the declaration -- while `lane_names_fn` resolves a
    dispatch row's typed `session` target to a lane name, reading every profile's live
    session bindings, so a probe that did not inject it would be asserting whichever lanes
    THIS box happens to have bound.

    The shared-tree rider is injected for the fourteenth and for the same reason (#241): it
    shells out three times against the tree the patrol is running in, and its three
    renderings -- blocking paths, an UNKNOWN comparison, NOT RUN -- are exactly what a
    probe must be able to drive without the live box. It is deliberately NOT a leg: it
    carries no problem, so it can never move the patrol's exit code.

    The duty-receipt leg's bound is injected for the fifteenth and for the same reason as
    the three board legs' (#487): it judges a HISTORICAL population of rounds against a
    bound this tree declares, so a probe that could only read the live declaration could
    not exercise a pre-boundary round, a post-boundary one, or a REFUSED bound at all --
    and in the half of this byte-paired file that ships, no declaration exists, so a probe
    reading the live tree would assert an ADOPTING member's history rather than the leg's
    behaviour. `duty_scope_fn(repo)` returns `(instant, text, refusal)` -- the INSTANT
    first, because this reader parses where the board legs' returns only text; the live
    default reads this tree's declaration through the one boundary reader.
    """
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
            "canonicality-tier, workspace-blocked, stall-census, "
            "board-unruled, "
            "undispatched-ruling, "
            "dispatch-delivery, "
            "criterion-paths, "
            "score-conversion, "
            "kit-drift, "
            f"publish-freshness, worktree) — the run aborted at the board read at "
            f"{read_at}, so no leg was built"
        )
        return 2

    cron_rows, homes_read, unreached = cron_rows_fn()
    board_bound = board_scope_fn or declared_leg_boundary
    # #487: the duty leg's bound is read the same way and for the same reason. It was the
    # one bounded leg still resolving the ambient `REPO` INSIDE the leg, so a probe that
    # injected a board bound still had its duty bound decided by the tree the patrol ran
    # in -- and in the half of this byte-paired file that ships, no declaration exists.
    duty_scope = duty_scope_fn or duty_receipt_bound
    # #241: the shared-tree rider is read ONCE and handed to the report, which prints it
    # at the head of the board-leg region. It is deliberately NOT a leg: it carries no
    # problem, so it can never move the patrol's exit code (a standalone detection leg was
    # refused as #83's class), and its only job is to make the board legs' read of the
    # shared tree attributable.
    # #501: the rider is read EAGERLY, before any leg is built, so a raise here would
    # abort the round exactly as a leg's would -- and for the same reason it is contained.
    # It carries no problem by design (it can never move the exit code), so the containment
    # yields None, a value the report already handles: it is STATED on stderr, never silent.
    try:
        board_rider = (shared_tree_fn or shared_tree_rider)(read_at=read_at)
    except Exception as exc:  # noqa: BLE001 -- same class as a leg's raise (#501)
        board_rider = None
        err(
            f"shared tree rider: NOT RUN -- it raised {type(exc).__name__}: {exc} at "
            f"{read_at}; the round continues and the board legs' read is UNATTRIBUTED"
        )
    # THE STALL CENSUS IS BUILT ONCE AND SHARED (#133). The driverless-lane leg's population
    # IS the census's own `owed_by_lane` grouping, so the two legs must read the SAME census:
    # a second call would re-read the board and could group a different round, and the two
    # blocks would then disagree about which lane a unit sits on. Lazy rather than eager, so
    # `leg_guard` still contains a census that raises -- the census leg reports its own FAILED
    # verdict, and the driverless leg's guard reports the raise it inherited.
    census_cache: dict[str, dict] = {}

    def _census() -> dict:
        if "v" not in census_cache:
            census_cache["v"] = stall_census_leg(
                issues, rows, read_at=read_at,
                lane_names_fn=lane_names_fn or stall_lane_names,
            )
        return census_cache["v"]

    legs = [
        leg_guard("board-intake", lambda: board_intake_leg(issues, rows, predicate=predicate, bound=board_bound), read_at),
        leg_guard("board-close", lambda: board_close_leg(issues, rows, read_at=read_at, bound=board_bound), read_at),
        leg_guard("board-closed", lambda: board_closed_leg(issues, rows, read_at=read_at, predicate=predicate,
                         bound=board_bound), read_at),
        leg_guard("board-ruling", lambda: board_ruling_leg(
            issues, rows, read_at=read_at, predicate=predicate,
            scope=(ruling_scope_fn or ruling_board_scope)(),
            exemptions_path=ruling_exemptions_path,
        ), read_at),
        leg_guard("cron-thinness", lambda: cron_thinness_leg(
            cron_rows, homes_read, unreached, prefixes_fn(), read_at=read_at
        ), read_at),
        # #392: the section 4.1 own-elapsed-slot predicate, hosted. It is handed the SAME
        # cron rows the three legs around it are, so it opens no database of its own.
        leg_guard("cadence-slot", lambda: cadence_slot_leg(
            cron_rows, homes_read, unreached, read_at=read_at,
            # #543: the verdict is decided against a dispatch RECORD, so the leg is handed
            # the same `cron_run_fires` read the two receipt legs take -- injected for the
            # same reason those are, so a probe's verdict is never decided by the live box's
            # own runs table.
            fires=cron_fires_fn(),
        ), read_at),
        leg_guard("notify-receipt", lambda: notify_receipt_leg(
            cron_rows, homes_read, unreached, prefixes_fn(), log_dir=log_dir,
            read_at=read_at,
            # #306: the run's own verdict, from the daemon's per-fire record. Injected for
            # the same reason the cron table and the duty leg's fires are: a probe must
            # never have its excuse decided by the live box's own runs table.
            fires=cron_fires_fn(),
        ), read_at),
        leg_guard("duty-receipt", lambda: duty_receipt_leg(
            cron_rows, homes_read, unreached, prefixes_fn(), rows, read_at=read_at,
            # The per-job residual (#449) is derived from each job's OWN fire history, so
            # the leg is handed the daemon's fire records. Injected for the same reason the
            # cron table is: a probe must not have its window decided by the live box.
            fires=cron_fires_fn(),
            # #487: the bound is injected, never read from the ambient tree the patrol runs
            # in -- the same reason the three board legs' bounds are.
            scope_fn=duty_scope,
            # #506: and the exemption store with it, for the same reason one layer down.
            exemptions_fn=duty_exemptions_fn,
        ), read_at),
        leg_guard("canonicality-tier", lambda: canonicality_leg(rows, read_at=read_at), read_at),
        leg_guard("ledger-ref-roles", lambda: ledger_ref_roles_leg(
            rows, read_at=read_at,
            # #330: injected so no probe's verdict is decided by this factory's own
            # declared exemptions.
            exemptions_path=ref_role_exemptions_path,
        ), read_at),
        leg_guard("workspace-blocked", lambda: workspace_blocked_leg(rows, read_at=read_at, dirty_paths_fn=dirty_paths_fn), read_at),
        leg_guard("stall-census", _census, read_at),
        # #133: the LANE STATE behind the census's units. Its population is the census's own
        # grouping, and the goal store is injected so no probe's verdict is decided by this
        # box's live `goal_state` rows.
        leg_guard("driverless-lane", lambda: driverless_leg(
            _census(),
            goals=(driverless_goals_fn or box_goal_rows)(),
            read_at=read_at,
            lane_names_fn=lane_names_fn or stall_lane_names,
            lane_turn_open_fn=driverless_turn_open_fn,
            lane_activity_fn=driverless_activity_fn or box_lane_activity,
        ), read_at),
        leg_guard("board-unruled", lambda: board_unruled_leg(issues, rows, read_at=read_at, predicate=predicate), read_at),
        leg_guard("undispatched-ruling", lambda: undispatched_ruling_leg(
            issues, rows, read_at=read_at, predicate=predicate,
            **(dispatch_batches_fn or undispatched_batches_fn)(),
        ), read_at),
        leg_guard("criterion-paths", lambda: criterion_path_leg(
            issues, read_at=read_at,
            repo=(criterion_repo_fn or (lambda: REPO))(),
            exemptions_path=(criterion_exemptions_fn or (lambda: CRITERION_PATH_EXEMPTIONS))(),
        ), read_at),
        leg_guard("score-conversion", lambda: score_conversion_leg(
            rows, read_at=read_at, predicate=predicate,
            # The scores surface (#67) is injected for the same reason the criterion tree
            # is: the leg reads the NEWEST `evidence/scores/<date>.md` in the LIVE tree, so
            # a probe that did not inject a directory would have its verdict decided by
            # this factory's own latest survey -- and every probe driven through `_run`
            # would start reading red for a reason none of them names. The default is the
            # live surface, which is what production wants; `_run` injects an EMPTY
            # directory, so a probe that does not pass one reads NOT RUN with its reason.
            scores_dir=scores_dir_fn() if scores_dir_fn else None,
        ), read_at),
        leg_guard("dispatch-delivery", lambda: dispatch_delivery_leg(
            rows, read_at=read_at, bound=(delivery_scope_fn or dispatch_delivery_scope)(),
            deliveries_fn=deliveries_fn,
            # THE BOARD IS INJECTED FOR THE SCOPING (#538): a dispatch row naming a CLOSED
            # item is history, and only a real board read can say which items are closed.
            # `main` has already exited 2 on an unreadable board, so this is the SAME read
            # the other board legs use -- one call, no second fetch.
            issues=issues,
        ), read_at),
        leg_guard("kit-drift", lambda: kit_drift_leg(manifest_path=kit_manifest, fleet_path=fleet_manifest,
                      read_at=read_at), read_at),
        leg_guard("publish-freshness", lambda: (publish_fn or publish_freshness_leg)(read_at=read_at), read_at),
        leg_guard("worktree", lambda: (worktree_fn or worktree_leg)(read_at=read_at), read_at),
        leg_guard("pacemaker-presence", lambda: (presence_fn or live_pacemaker_presence_leg)(
            cron_rows, homes_read, unreached, prefixes=prefixes_fn(),
            read_at=read_at,
        ), read_at),
    ]
    deferred = deferred_legs()
    deferred_problems = deferred_entry_problems(deferred)
    out(render(legs, deferred, slug=slug, read_at=read_at, issues=issues,
               deferred_problems=deferred_problems, board_rider=board_rider))
    return 1 if any(leg["problems"] for leg in legs) or deferred_problems else 0


if __name__ == "__main__":
    raise SystemExit(main())