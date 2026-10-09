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
    """
    predicate = predicate or load_predicate()
    bound, bound_text, bound_refusal = scope if scope is not None else ruling_board_scope()
    exempt, exempt_problems = load_ruling_exemptions(exemptions_path)

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

    problems: list[str] = list(exempt_problems)
    examined = 0
    pre_boundary = 0
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
        if bound_refusal or number in ruled:
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
        comment_id = str(latest.get("id") or "")
        created = str(latest.get("createdAt") or "")
        entry = exempt.get(comment_id)
        if entry is not None:
            # The lawful exit, PRINTED on every run with its reason: a debt made visible,
            # never forgiveness.
            matched_exemptions.add(comment_id)
            exempted.append(comment_id)
            excused.append(
                f"#{number}: EXEMPTED — ruling comment {comment_id or '(no id)'} "
                f"({created or 'instant unstated'}) is declared in "
                f"{RULING_EXEMPTIONS_PATH.name}: {entry.get('reason')}"
            )
            continue
        if bound is None:
            # UNBOUNDED scope: the leg's pure shape, every instance judged.
            problems.append(
                f"#{number} carries a ruling comment on the board but the ledger holds no "
                f"`ruling` row for it (board read at {read_at}) — the ruling's content is on "
                f"the board, but every other row cites a ruling by `n`, and a ruling with no "
                f"row has no `n` for a reader to resolve"
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
            f"#{number} carries a ruling comment ({created}) on the board but the ledger "
            f"holds no `ruling` row for it, and the comment is at or after the declared "
            f"bound {bound_text} for `{RULING_BOUNDARY_KEY}` (board read at {read_at}) — the "
            f"pairing mechanism existed, so this is a lane that diverged from it"
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
            "rulings_read": len(ruled) + len(unbridgeable),
            "rulings_resolved": len(ruled),
            "rulings_unbridgeable": len(unbridgeable),
            "resolution_arms": arms,
            "unbridgeable_rows": unbridgeable,
            "bound": bound_text,
            "bound_refusal": bound_refusal,
            "bound_key": RULING_BOUNDARY_KEY,
            "pre_boundary_rulings": pre_boundary,
            "rulings_undatable": undatable,
            "exemptions_path": RULING_EXEMPTIONS_PATH.name,
            "exemptions_declared": len(exempt),
            "exemptions_matched": sorted(matched_exemptions),
            "rulings_exempted": exempted,
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

def dispatch_delivery_leg(
    rows: list[dict],
    *,
    read_at: str = "",
    bound: tuple | None = None,
    deliveries_fn=None,
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
    """
    window_before = dt.timedelta(seconds=DELIVERY_WINDOW_BEFORE_SECS)
    window_after = dt.timedelta(seconds=DELIVERY_WINDOW_AFTER_SECS)
    match_horizon = dt.timedelta(seconds=DELIVERY_MATCH_HORIZON_SECS)
    coverage = {
        "bound_key": DELIVERY_BOUNDARY_KEY,
        "bound": (bound[1] if bound else "") or "",
        "window_basis": DELIVERY_WINDOW_BASIS,
        "window_before_secs": DELIVERY_WINDOW_BEFORE_SECS,
        "window_after_secs": DELIVERY_WINDOW_AFTER_SECS,
        "match_horizon_secs": DELIVERY_MATCH_HORIZON_SECS,
        "dispatch_rows_read": sum(1 for r in rows if r.get("event") == "dispatch"),
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
        uses_declaration = declared is not None and declared < ts
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
            # TWO CONDITIONS, TWO VERDICTS (#432). The specimen that produced this clause is
            # row `n=2787` (`#428`): its window opened `12:23:04Z`, its notify landed
            # `12:11:28Z`, and the leg read "records no delivery" for a delivery that woke the
            # very lane that ruled the item -- sending a reader off to re-dispatch an item the
            # target already held. The reader is told WHICH instant the delivery carries and
            # which window judged it, so the mismatch is a fact they can act on rather than a
            # false absence they must disprove.
            outside = min(plausible, key=lambda d: d["epoch"])
            at = dt.datetime.fromtimestamp(outside["epoch"], dt.timezone.utc)
            problems.append(
                f"n={row.get('n')} ({subject}) dispatched at {row.get('ts')} to session "
                f"{session_ref} carries a delivery OUTSIDE the window this leg judged: a "
                f"notify carrying `{subject}` addressed to that target landed "
                f"{at.strftime('%Y-%m-%dT%H:%M:%SZ')} ({outside['state']}), and the window "
                f"[{lo.strftime('%Y-%m-%dT%H:%M:%SZ')}, {hi.strftime('%Y-%m-%dT%H:%M:%SZ')}] "
                f"({basis}) does not contain it — a DELIVERY EXISTS, so this is a WINDOW "
                f"MISMATCH, never an absence: do not re-dispatch on this line"
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
    })
    return {"name": "dispatch-delivery", "status": "ASSERTED", "reason": None,
            "problems": problems, "excused": [], "coverage": coverage}

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
    # all. Both are read off EVERY dispatch-bearing row rather than off the one `carriers`
    # holds, because the two questions differ: `carriers` keeps the EARLIEST row, which is
    # what the age is measured from (#308), while the addressee is where the work was LAST
    # sent. A later row that declares no target does NOT erase an earlier declaration --
    # silence is not a re-routing -- so the map keeps the newest row that actually declares.
    declared_refs: dict[str, tuple[str, dict]] = {}
    dispatch_counts: dict[str, int] = {}
    # THE NEWEST DISPATCH-BEARING ROW, per unit, kept for the PARK SUPERSESSION test alone
    # (#331 clause 1): a park is a state read off the rows, and the ledger keeps every row
    # forever, so a unit re-dispatched AFTER its park would stay silently held out of the
    # census for good. A dispatch newer than the declaring row puts the unit back in play.
    newest_dispatch: dict[str, dict] = {}

    def declare(unit: str, row: dict) -> None:
        """Record one dispatch-bearing row against the unit it dispatched."""
        dispatch_counts[unit] = dispatch_counts.get(unit, 0) + 1
        held_row = newest_dispatch.get(unit)
        if held_row is None or _ledger_row_order(row) >= _ledger_row_order(held_row):
            newest_dispatch[unit] = row
        session_ref = next(
            (str(value) for ref in (row.get("refs") or [])
             for kind, value in ref.items() if kind == "session"), ""
        )
        if not session_ref:
            return
        held = declared_refs.get(unit)
        if held is None or _ledger_row_order(row) >= _ledger_row_order(held[1]):
            declared_refs[unit] = (session_ref, row)

    observation = 0
    carried_units = 0
    pre_filing_rejected = 0
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
                declare(subject, row)
            continue
        blob = f"{row.get('detail') or ''} {row.get('refs') or ''}"
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
        for unit in units:
            carriers.setdefault(unit, row)
            declare(unit, row)

    problems: list[str] = list(park_problems)
    excused: list[str] = []
    owed: list[dict] = []
    parked: list[str] = []
    parked_units: set[str] = set()
    park_superseded: list[str] = []
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
    ] + park_superseded

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

    owed.sort(key=lambda entry: -entry["age_days"])
    addressees_resolved = 0
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
        problems.append(
            f"OWED {unit}: dispatched {entry['age_days']:.2f} d ago and NEVER CLAIMED, "
            f"and the board still carries it OPEN -- {addressee_note}.{assignee_note} "
            f"Re-dispatch it to the lane that owns it through `session_notify`, or close "
            f"it on the board: a dispatch no lane has taken is work nobody is doing"
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
            # THE ADDRESSEE COVERAGE (#331 clause 2): how many OWED lines could name the lane
            # the work was handed to. A line that names none says so in words; this pair is
            # the count, so a read where NOTHING resolved is not mistaken for one where the
            # question was never asked.
            "addressees_resolved": addressees_resolved,
            "addressees_unresolved": len(owed) - addressees_resolved,
            "threshold_days": threshold_days,
            "threshold_basis": STALL_CENSUS_THRESHOLD_BASIS,
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
    ruled: set[int] = set()
    arms = {"strict": 0, "declared": 0, "bridged": 0}
    unbridgeable: list[dict] = []
    for row in rows:
        if str(row.get("event") or "") != "ruling":
            continue
        ruling_rows += 1
        number, arm = resolve_ruling_issue(row, rows, predicate)
        if number is None:
            unbridgeable.append(
                {"n": row.get("n"), "subject": str(row.get("subject") or "")}
            )
        else:
            ruled.add(number)
            arms[arm] = arms.get(arm, 0) + 1

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
            "rulings_resolved": len(ruled),
            "rulings_unbridgeable": len(unbridgeable),
            "unbridgeable_rows": unbridgeable,
            "resolution_arms": arms,
            "population_unruled": len(population),
            "items_owed_ruling": len(owed),
            "owed": [entry["issue"] for entry in owed],
            "population": population,
            "threshold_hours": threshold_hours,
            "threshold_basis": BOARD_UNRULED_THRESHOLD_BASIS,
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

def criterion_path_leg(issues: list[dict], *, read_at: str,
                       repo: Path = REPO) -> dict:
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
    a leg that found everything clean. A path is judged against the tree at `read_at`, and a
    `TEMPLATE/`-prefixed name is resolved as the shipped twin, which is how the law writes
    it.
    """
    examined = 0
    problems: list[str] = []
    open_items = 0
    closed_items = 0
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
            for ref in sorted(set(CRITERION_PATH_REF.findall(text))):
                if not is_mechanism_path(ref):
                    continue
                examined += 1
                if (repo / ref).exists():
                    continue
                problems.append(
                    f"issue #{number} criterion ({where}) names `{ref}` — ABSENT at "
                    f"{read_at}; dispatch a work item naming `{ref}`"
                )
    return {
        "name": "criterion-paths",
        "status": "ASSERTED",
        "problems": problems,
        "excused": [],
        "coverage": {
            "refs_examined": examined,
            "issues_read": open_items,
            "closed_items_excluded": closed_items,
            "surfaces": ["body", "ruling comment"],
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
                f"{cov['units_off_board']} unit(s) dropped as not an OPEN issue of this "
                f"board)"
            )
            lines.append(
                f"  population: {cov['units_in_population']} dispatched unit(s) -- "
                f"{cov['units_owed']} never claimed past the declared threshold of "
                f"{cov['threshold_days']} d"
            )
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
            # ... and the ADDRESSEE coverage (#331 clause 2), so a run where NOTHING
            # resolved is not read as a run that never asked.
            lines.append(
                f"  addressee: {cov['addressees_resolved']} of {cov['units_owed']} OWED "
                f"unit(s) name the lane the work was handed to; "
                f"{cov['addressees_unresolved']} declare none"
            )
            lines.append(f"  threshold basis: {cov['threshold_basis']}")
            lines.append(f"  read at {cov['read_at']}")
        elif leg["name"] == "board-unruled":
            # The population is PRINTED BESIDE THE VERDICT (acceptance criterion 2), so an
            # empty sweep reads as "examined 0, 0 problems" rather than as silence -- which
            # is the failure #332 records: a skipped item reads clean.
            lines.append(
                f"  board: {cov['board_items_read']} item(s) read, "
                f"{cov['open_items_examined']} OPEN; intake rows read: "
                f"{cov['intake_rows_read']} ({cov['intake_rows_resolved']} naming an "
                f"issue); ruling rows read: {cov['ruling_rows_read']} "
                f"({cov['rulings_resolved']} resolved to an issue "
                f"[strict {cov['resolution_arms']['strict']}, declared "
                f"{cov['resolution_arms']['declared']}, bridged "
                f"{cov['resolution_arms']['bridged']}], "
                f"{cov['rulings_unbridgeable']} unbridgeable)"
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
            lines.append(
                f"  criterion paths (issue body and ruling comment): "
                f"{cov['refs_examined']} reference(s) examined over "
                f"{cov['issues_read']} issue(s), {len(leg['problems'])} unresolved — "
                f"{cov['closed_items_excluded']} closed item(s) outside the population — "
                f"board read at {cov['read_at']}"
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
    dirty_paths_fn=None,
    ruling_scope_fn=None,
    ruling_exemptions_path: Path | None = None,
    delivery_scope_fn=None,
    deliveries_fn=None,
    criterion_repo_fn=None,
    board_scope_fn=None,
    lane_names_fn=None,
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
            "dispatch-delivery, "
            "criterion-paths, "
            "kit-drift, "
            f"publish-freshness, worktree) — the run aborted at the board read at "
            f"{read_at}, so no leg was built"
        )
        return 2

    cron_rows, homes_read, unreached = cron_rows_fn()
    board_bound = board_scope_fn or declared_leg_boundary
    legs = [
        board_intake_leg(issues, rows, predicate=predicate, bound=board_bound),
        board_close_leg(issues, rows, read_at=read_at, bound=board_bound),
        board_closed_leg(issues, rows, read_at=read_at, predicate=predicate,
                         bound=board_bound),
        board_ruling_leg(
            issues, rows, read_at=read_at, predicate=predicate,
            scope=(ruling_scope_fn or ruling_board_scope)(),
            exemptions_path=ruling_exemptions_path,
        ),
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
        workspace_blocked_leg(rows, read_at=read_at, dirty_paths_fn=dirty_paths_fn),
        stall_census_leg(
            issues, rows, read_at=read_at,
            lane_names_fn=lane_names_fn or stall_lane_names,
        ),
        board_unruled_leg(issues, rows, read_at=read_at, predicate=predicate),
        criterion_path_leg(
            issues, read_at=read_at,
            repo=(criterion_repo_fn or (lambda: REPO))(),
        ),
        dispatch_delivery_leg(
            rows, read_at=read_at, bound=(delivery_scope_fn or dispatch_delivery_scope)(),
            deliveries_fn=deliveries_fn,
        ),
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
