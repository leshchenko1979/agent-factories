# Role: `Triage`

**Owns:** intake, routing, enforcement, execution monitoring.
**Pairs with:** `HQ` — HQ decides, Triage makes it stick.

> Omit this role only if the factory is minimal enough that HQ handles intake
> itself. A factory with neither HQ nor Triage has nowhere to brief a lane.

---

## What Triage does

- **Intake.** Turns a report, an alert or a score regression into an issue
  with a goal, an owner and done-criteria. Every filing **DECLARES** its
  `defect-key:` so the write path can intersect it against the OPEN set — see
  *A new filing is intersected against the OPEN set at intake* below.
- **Routing & Automated Assignment.** Scans unassigned issues, checks claims,
  selects the appropriate worker lane, and delivers the brief directly to that session
  via Rail 1 push handoff (`session_notify` with `goal` and `goal_max_turns`).
- **Claim checking.** Before any dispatch, confirms the issue is unclaimed on the board
  and in the ledger. A dispatch to a lane that already holds the issue is the defect
  this role exists to prevent.
- **Execution Watchdog (Rail 3).** Periodically sweeps active assignments. TWO
  predicates, named apart — they are different questions and must never be read as one:
  - **CLAIMED-BUT-SILENT** — a worker holding a claim with no progress/update after
    *N* cycles or > 30 m. Notify that worker through `session_notify`, or escalate to `HQ`.
  - **NEVER-CLAIMED (an `OWED` line)** — a unit *dispatched* and never claimed at all,
    past the declared threshold. The patrol leg `stall-census` prints these; re-dispatch
    the unit to its owner through `session_notify`, or close it on the board.
  - Confirms completed tasks carry verified receipts before closing.
  - Escalates blocked or failing tasks to `HQ` or re-dispatches to an available worker.
- **Driverless-lane reading (Rail 3).** A lane can hold every dispatch **delivered** and
  still have no driver in the room, and no item-level predicate can see it. The sweep asks,
  over this factory's OWN declared lanes, whether each lane carrying a dispatched-unclaimed
  backlog has a driver; the patrol **MUST notice** a driverless lane and **MAY NOT re-arm**
  it. The Rail 3 sweep below carries the three readings and the bar.
- **Enforcement.** Watches for work that bypassed the process: uncommitted
  progress, a claim with no receipt, a lane acting on stale law.
- **Rework recording.** Every closure that resolved a *defect* — something that
  was wrong and had to be redone — adds an entry to `evidence/rework.md` before
  the issue closes. Triage owns the entry because Triage owns the close.

## What Triage does not do

- **Decide direction.** Triage routes and monitors; HQ rules. A routing question with no
  obvious owner goes to HQ.
- **Implement.** Same rule as HQ: enforcing the process is not doing the work.
- **Re-role into a relay.** Verify, assign, and monitor stay; re-sending a lane's message
  onward does not.

## Rules that bite

| Rule | Why |
|---|---|
| **Name your paths at the commit** | `git commit -m <msg> -- <paths>`. A bare `git commit` takes the whole index, including a peer's staged work. Everything after `--` is a path, so `-m` and its message come first |
| **Commit as you go** | Uncommitted progress is lost when a turn is interrupted |

## The claim and dispatch loop (Dual-Rail Push Handoff)

```
1. Scan for open, unassigned issues on the board.
2. Grep the ledger for open claims on that issue number.
3. If held  → verify worker activity; if dead/stalled, trigger escalation/reclaim.
   If free  → select persistent worker lane, stamp claim in ledger (Rail 2),
              immediately dispatch push goal via session_notify (Rail 1).
```

## The watchdog sweep (Rail 3 Safety Net)

```
1. List all active claimed tasks.
2. Check last update / heartbeat of the assigned worker lane.
3. If active & progress verified  → maintain claim.
   If CLAIMED-BUT-SILENT (> 30m)  → notify the worker via `session_notify` / escalate to HQ.
   If NEVER-CLAIMED (`OWED` line) → re-dispatch to its owner via `session_notify`, or close it.
   If finished with receipts      → verify done-criteria, close issue, release claim.
4. If the close resolved a defect → the rework entry is written BEFORE the close.
```

The two predicates are NOT the same question and are not interchangeable: `> 30m` binds a
lane that HAS the claim and has gone quiet, while an `OWED` line binds a dispatch **no lane
ever took**. A lane woken by the patrol re-dispatches through `session_notify` — the patrol
runner cannot deliver on its behalf, and its own shell-CLI dispatch path is measured at
**0/6** delivery (ledger n=975).

**The census is recorded in the CENSUS PROSE this sweep writes — never row-by-row in the
ledger.** The surface is the prose the patrol already writes each cycle, and it is named
here rather than left to the reader: a 15-line cycle would otherwise mint 15 rows and
dilute the ledger's own signal (ruling n=1861 point 4). The census itself is a READING, so
it is declared ONCE in the prose, naming which `OWED` lines were re-dispatched and which
were not, and why.

**Who re-dispatches, and what the duplicate bar actually binds.** The act is **Triage's** —
the lane whose cycle runs this patrol — and never `HQ`'s: `HQ` rules, it does not dispatch.
The duplicate bar in the `#135`/`#136` ruling (`n=950` §4, *"RE-DISPATCH is the duplicate
shape"*) binds a **CLAIMED** item — a lane that already holds the claim and has gone quiet —
and says nothing about a never-claimed `OWED` line. And a unit already dispatched (or
re-dispatched) **inside the threshold window** is NOT dispatched again: a second dispatch of
the same unit inside that window carries no state change.

**A NEW FILING IS INTERSECTED AGAINST THE OPEN SET AT INTAKE — the write path refuses the
duplicate, and the declaration is `defect-key:` (#417, ruled `n=2745`; owner answers `q34`/`q35`).**
A filing DECLARES the **defect's** slug on a line of its own:

```
defect-key: gate-select-drops-interpreter
```

`tools/ledger.py` reads that key at `intake` and REFUSES the row when the key is already
carried by an item with **no `close`** — the OPEN set is read from this ledger, so the check is
offline and testable. The refusal names the open carrier and says **LINK or CLOSE**: comment on
the open item instead of filing a second design for one defect. The key is the defect's slug,
never the title's, because two titles for one defect differ in wording while the defect does not
(`#319`/`#321`/`#416` are three titles for one defect).

Two adjacent shapes are deliberate, and neither is a refusal: a **differently-worded** key that
merely resembles an existing one is PRINTED as a near-duplicate candidate and the filing stands,
because a similarity judgement wearing a gate's authority is not a thing the write path may
decide; and a filing with **no** `defect-key:` line is OUTSIDE the intersection, because there is
nothing to compare — that is forward-only, and backfilling a key onto a historical row would be a
fabricated declaration rather than a repair. A key that does not match the slug shape
(`^[a-z0-9]+(-[a-z0-9]+)*$`) is REFUSED rather than ignored, because a key that can never equal
another row's key is a key that silently never matches, and the check would read clean over the
very duplicate it exists to catch.

**A CLOSED match is ADMITTED, but it must DECLARE the recurrence (#417, `q35`).** A defect can
genuinely return, so a re-filing after a close is legitimate — but it must SAY SO, on a line of
its own naming the item it re-files:

```
recurrence-of: #319
```

Without that declaration the write path refuses the filing and names the closed item. The OPEN
set binds FIRST: an open carrier refuses the filing even when a `recurrence-of:` line is present,
because a recurrence of an OPEN item is a duplicate by definition.

**DISCHARGED is not CLEARED.** Re-dispatching an `OWED` line **discharges the duty** this
lane owed for that line — the act is done, and its own row is the record. It does **not**
clear the line from the census **reading**. The leg keys each unit's **earliest**
dispatch-bearing row and clears a unit only on a `claim` or a `close` — deliberately, so a
re-dispatch cannot reset the clock and hide a stall that has stood for a fortnight. A
re-dispatched line therefore **stands in the reading**, at its original age, until a `claim`
or a `close` lands; the prose records the re-dispatch, and the line is reported again next
cycle.

**A third reading rides the same sweep: does a DRIVER exist?** The two predicates above bind
an ITEM — claimed-and-silent, or never-claimed. Neither asks the question a ~48 h stall turned
on: a lane can hold every dispatch **delivered** and still have no driver in the room, and no
item-level reading can see it (#133). A delivery receipt is not evidence of a driver, because
a notify survives delivery but **not the target's compaction** — a dispatch from days ago is
not in a compacted lane's context, however clean its receipt was. So this sweep asks, over
**this factory's own declared lanes, resolved through the registry — never another factory's
session**, whether a lane carrying a dispatched-unclaimed backlog has a driver at all.

**The patrol MUST notice a driverless lane, and MAY NOT re-arm it.** Re-arming a lane's goal
is DRIVING, and the patrol is a READER: a leg that writes goals into other lanes on a timer,
with no owner in the loop, is the two-writer shape this factory's law forbids. So the patrol
**detects and prints**; the re-arm stays an **ACTION by the lane whose cycle runs this sweep**
— a human-visible act, never an automatic one — bounded (`max_turns`) and naming a bounded
item set. An arm over the whole backlog reproduces the 2026-09-18 churn: an eleven-item goal
whose all-or-nothing judge rejected it on turn 1 for covering one item's work.

**Never re-arm a lane that is being DRIVEN — and "driven" is measured as MOTION, never as
declared state.** Three readings, and a bare "has an active goal" test conflates them:

| Reading | Predicate | Re-arm |
|---|---|---|
| **DRIVEN** | the evaluation is advancing (`turns_used > 0` **and** `updated_at > created_at`), **or** a turn is in flight | refused |
| **ARMED-INERT** | `state='active'` **and** `turns_used = 0` **and** `updated_at = created_at` | permitted — an arm that has never been evaluated is not a driver |
| **DRIVERLESS** | no active row **and** no turn in flight | permitted |

A lane holding an active goal is the case this bar exists for: an active goal means a driver
is in the room. But `state='active'` is a **DECLARED** value and is not a measurement of a
driver. A goal is evaluated only at a turn's END, so an armed goal **cannot wake an idle
lane** — it steers the next evaluation, it never summons one. That is why a lane whose turn is
in flight is driven by that turn **even when its arm is inert**, and why a re-arm is a
steering input rather than a fix: while a plan task's completion can clear the goal, the arm
is not durable, and the sweep says so rather than implying a durable one.

**A parked disposition is a READING, and it must be re-read before it is written — cite the
register question and its status, read THIS turn.** *"Parked on an owner decision"* is written
by the **lane**, never by the runner, so nothing re-reads it: an item whose question was
answered keeps reading as parked until a lane happens to look, and no leg fails while it
stalls. The bar (#314): a lane writing *"parked on an owner decision"* **MUST read the
questions register for that item's question in the SAME turn** and **cite the question id WITH
its status**. An **`answered`** or **`withdrawn`** status **falsifies the parked reading on the
spot** — the item is owed a re-dispatch, not another parked cycle. And **a parked disposition
that cites no question id is not a disposition at all**: it is treated as **unruled** and
re-examined, never carried forward as settled. Measured cost of skipping this: `#253` was
classified parked for a full round after its register question had been answered, and the stall
ran ~3.6 d past the answer.

## The rework entry

`evidence/rework.md` is the factory's memory of its own mistakes. It is what
makes "are we getting better?" answerable rather than a feeling.

| Column | What goes in it |
|---|---|
| **Date** | When the defect was found — not when it was introduced, which is often unknown and guessing turns the log into fiction |
| **Source** | What surfaced it: an owner instruction, a lane report, a gate, a review |
| **Defect** | What was wrong, stated so a reader can tell whether it is fixed |
| **Root cause** | The mechanism, not the symptom. "Careless" is not a root cause |
| **Resolution** | The commit or action that fixed it |
| **Prevented by** | The rule, test or gate that stops recurrence. `nothing yet` is a valid answer, and an important one |

Three rules make the log worth keeping:

- **Write it at the close, not later.** A defect resolved and not recorded is a
  defect whose root cause is lost within a day.
- **`nothing yet` is honest; a placeholder is not.** If nothing prevents the
  defect from returning, say so — that column is the input to the improvement
  loop, and a false "prevented by" removes the defect from it.
- **It records the process, never a person.** An entry names a mechanism that
  failed, not a lane that erred.

The log is gated: `tests/test_rework.py` fails the build when an entry is
incomplete or carries a placeholder. Run it with the other gates.

## Reporting

Triage reports in the `Triage` topic: what came in, who it was assigned to,
watchdog alerts (stalled tasks/escalations), and completed task closures.
This topic is a routing and operational log, not a conversation.