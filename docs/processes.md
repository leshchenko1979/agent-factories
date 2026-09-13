# Process Register — Meta-Factory

> **Owns:** the canonical register of every recurring process in this
> meta-factory, its process owner, process client, delegated implementers,
> quality criteria, declared cadence or trigger, and trace evidence.

---

## 1. Principles and Model

This register makes the rule verifiable: **the factory keeps track of its own
processes, and these processes are audited.** A process is a recurring act that
keeps a property true. A property is a state; a process is the act that holds the
state up, and only the act can silently stop.

Every process in this register adheres to five structural laws:

1. **The Client Principle (Ruling 4, 2026-09-13):** Every process runs for a
   **process client**. The client decides why the process runs, sets its trigger
   condition or cadence expectation, and consumes its value.
2. **Failure to start is an execution failure:** When the client's trigger condition
   fires or the declared interval passes, failure to start is recorded as a
   failure (`outcome = failed`). It directly lowers **first-pass yield** and
   depresses **Stability (O2)**.
3. **Accountability cannot be delegated:** The **process owner** is accountable
   for the design, health, specification, and SLA of the process. The process
   owner delegates execution to **process implementers** (lanes, tools, or
   automated runners). If a run fails or stalls, the process owner remains
   accountable to the client.
4. **Subprocesses recurse:** When an implementer's execution consists of distinct
   stages, each stage is a **subprocess** with its own `(Process Client, Process
   Owner, Delegated Implementers, Process Quality Criteria)` triad.
5. **Quality criteria reflect client and stakeholder value:** Each process defines
   explicit quality criteria framed around the value delivered to the client,
   not internal mechanical chores.

---

## 2. Telemetry: Recorded vs. Derived Measures

A process run is **measured, not merely checked**. We distinguish what is
recorded on each run from what is read off the record:

| Layer | Measure | Source |
|---|---|---|
| **Recorded** (per run) | `duration` | Elapsed wall time of the run |
| | `resources consumed` | Compute, tokens, turns, or cost spent |
| | `outcome` | `accepted` · `reworked` · `abandoned` · `failed` |
| **Derived** (over time) | `cadence` | Actual runs ÷ declared runs |
| | `throughput` | Accepted outputs ÷ elapsed period |
| | `first-pass yield` | Accepted runs ÷ total runs |
| | `waste` | `(1 − yield) × resources consumed` |
| | `cost per successful task` | Total resources consumed ÷ accepted outputs |

---

## 3. The Meta-Factory Process Register

| Process | Process Owner | Process Client | Delegated Implementers | Declared cadence / trigger | Quality Criteria (Stakeholder Value) | Trace / Evidence | Applicable measures |
|---|---|---|---|---|---|---|---|
| **The four gates** | HQ | Carrier / Author | automated runner / CLI | every change | Zero regressions, clean invariants, immediate feedback (<10s) | Command exit code and output | duration · resources consumed · first-pass yield · waste |
| **Intake** | Triage | Reporter / Finder | Triage lane | on finding / gap | Unambiguous scope, clear goal, and verifiable done-criteria | Work unit issue on the board | throughput · duration |
| **Assignment** | Triage | Worker / Task | Triage lane | on intake | Clean claim check, clear task brief, no orphan runs | Ledger claim row, session dispatch brief | throughput · duration · first-pass yield |
| **Execution watchdog** | Triage | HQ / Owner | Triage lane | periodic (hourly) | Early detection of stalled workers before SLA breach | Escalation report or clean sweep log | cadence · throughput · first-pass yield |
| **Rework entry** | Triage | Surveys / Quality loop | Triage lane | on defect resolution | Root cause and actionable prevention rule recorded | Row in `evidence/rework.md` | throughput · first-pass yield |
| **Ship chain** | Carrier | Consumers / Release | Carrier lane | every release | Atomic, verified artifact without release rollback | Release commit, artifact identity proof | duration · resources consumed · first-pass yield · waste |
| **Daily measurement** | Surveys | Owner / Factory HQs | Surveys lane / cron | daily (09:00 MSK) | Reproducible, objective score diffs delivered on schedule | `evidence/scores/<date>.md`, ledger `score` row | cadence · duration · resources consumed · throughput |
| **Process audit** | Surveys & meta-factory | Owner / Governance | Surveys lane | periodic (weekly) | Early detection of silently stopped processes across fleet | Audit report section in evidence | cadence · first-pass yield |

---

## 4. Process Specifications and Subprocesses

### 4.1 The Four Gates
- **Process Owner:** HQ
- **Process Client:** Author (immediate code feedback), Carrier (release safety)
- **Subprocesses:**
  1. *Ontology gate* (`tests/test_ontology.py`): Rejects banned synonyms and uncanonical terminology.
  2. *Rework gate* (`tests/test_rework.py`): Verifies contiguous rework logging and prevents placeholder prevention fields.
  3. *Template sync gate* (`tests/test_template_sync.py`): Guarantees byte-identity between template gates and canonical tools.
  4. *Ledger sequence gate* (`tools/ledger.py verify`): Verifies monotonicity, intact state sequences (intake -> claim -> close), and single-writer locks.
- **Quality Criteria:** Complete verification suite exits 0 in <10 seconds with zero false positives.

### 4.2 Intake
- **Process Owner:** Triage
- **Process Client:** Reporter / Finder
- **Subprocesses:**
  1. *Classification & Deduplication:* Verify finding is not already tracked.
  2. *Work Unit Specification:* Ensure title prefix, goal, acceptance criteria, and owner are specified.
  3. *Ledger Intake:* Append immutable `intake` event row to state ledger.
- **Quality Criteria:** Work units have unambiguous done-criteria and clear scope; no untracked findings left in chat.

### 4.3 Assignment
- **Process Owner:** Triage
- **Process Client:** Worker / Assigned Lane
- **Subprocesses:**
  1. *Claim Check:* Verify target work unit is unclaimed in ledger.
  2. *Ledger Claim:* Append immutable `claim` event row to state ledger.
  3. *Direct Briefing:* Dispatch task brief to worker session without relay hops.
- **Quality Criteria:** Zero duplicate dispatches; clear and complete brief delivered directly to implementer.

### 4.4 Execution Watchdog
- **Process Owner:** Triage
- **Process Client:** HQ / Factory Owner
- **Subprocesses:**
  1. *Roster Sweep:* Check in-flight worker sessions against active claims.
  2. *Stall Detection:* Identify lanes exceeding SLA duration without heartbeat or receipt.
  3. *Escalation:* Notify HQ or Owner when worker is unresponsive.
- **Quality Criteria:** Stalled executions flagged before client SLA is breached; zero unmonitored orphan sessions.

### 4.5 Rework Entry
- **Process Owner:** Triage
- **Process Client:** Surveys / Quality Loop
- **Subprocesses:**
  1. *Defect Extraction:* Extract root mechanism (not symptom) on defect close.
  2. *Prevention Definition:* Formulate rule, test, or gate preventing recurrence (`nothing yet` if unaddressed).
  3. *Table Formatting:* Append contiguous row adhering to `tests/test_rework.py` invariants.
- **Quality Criteria:** Every defect resolved by rework has an audited entry with an actionable `Prevented by` field.

### 4.6 Ship Chain
- **Process Owner:** Carrier
- **Process Client:** Release Consumers / Downstream
- **Subprocesses:**
  1. *Gate Run:* Execute verification gates on release candidate.
  2. *Merge & Tag:* Fast-forward merge to production branch.
  3. *Artifact Verification:* Confirm deployed artifact identity matches built commit.
- **Quality Criteria:** Zero release rollbacks; 100% verified artifact identity.

### 4.7 Daily Measurement
- **Process Owner:** Surveys
- **Process Client:** Factory Owner / Member Factory HQs
- **Subprocesses:**
  1. *Live State Collection:* Inspect member repos, test suites, ledgers, and boards.
  2. *Rubric Scoring:* Score against 13 criteria (0-4) across 4 families.
  3. *Diff & Report Generation:* Commit `evidence/scores/<date>.md`.
  4. *Ledger Recording:* Append `score` event row to `evidence/ledger.jsonl`.
- **Quality Criteria:** Objective, reproducible diffs delivered daily at 09:00 MSK; zero subjective grading.

### 4.8 Process Audit
- **Process Owner:** Surveys & Meta-Factory HQ
- **Process Client:** Governance / Factory Owner
- **Subprocesses:**
  1. *Register Comparison:* Compare actual run rows in ledger against declared cadences in this register.
  2. *Yield & Waste Analysis:* Compute first-pass yield, waste, and duration trends per process.
  3. *Gap Identification:* Convert stopped or degrading processes into intake findings.
- **Quality Criteria:** 100% of declared processes audited; stopped processes caught within one audit cycle.
