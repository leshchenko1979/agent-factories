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

Every process in this register adheres to seven structural laws:

1. **The Client Principle (Ruling 4, 2026-09-13):** Every process runs for a
   **process client**. The client decides why the process runs, sets its trigger
   condition or cadence expectation, and consumes its value.
2. **Every process delivers a product:** One run of a process delivers one
   verifiable **product** — the result the process client consumes. A process with
   no product has no client value to score; the register names each process's product.
3. **Failure to start is an execution failure:** When the client's trigger condition
   fires or the declared interval passes, failure to start is recorded as a
   failure (`outcome = failed`). It directly lowers **first-pass yield** and
   depresses **Stability (O2)**.
3. **Single Process Ownership (P30):** Every declared process has exactly one named
   **process owner** role. Shared ownership is zero ownership. Accountability cannot
   be split or delegated; execution alone is delegated to **process implementers**.
4. **Law-Upholding Law (P29):** Every codified law in this factory must be upheld by
   an active process registered here or a deterministic mechanical gate. A rule without
   an upholding mechanism is dead text.
5. **The Pacemaker Law (P28):** Every periodic process declared here must have an active
   scheduled thin pacemaker job waking the persistent session UUID of the process owner.
6. **Subprocesses recurse:** When an implementer's execution consists of distinct
   stages, each stage is a **subprocess** with its own `(Process Client, Process
   Owner, Delegated Implementers, Process Quality Criteria)` triad.
7. **Quality criteria reflect client and stakeholder value:** Each process defines
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

### 2.1 Co-ownership of Process Cost: Demand vs. Supply

Process spend (`resources consumed`, and derived `cost per successful task` and
`waste`) is **co-owned across two boundaries**:
- **Demand side (Process Owner & Implementer):** Owns prompt structure, context
  budget, tool payload footprint, turn economy, and model tier selection (using
  a compact model where a frontier model is waste).
- **Supply side (InferHub / token provider):** Owns model routing, token unit
  pricing ($/M tokens), prompt caching discounts, inference latency (time to
  first token, tokens per second), and endpoint uptime.

When process costs spike or yield falls due to model timeouts, diagnosis investigates
both sides: did the process inflate its prompt, or did the provider suffer routing
latency, pricing drift, or dropouts?

---

## 3. The Meta-Factory Process Register

The meta-factory organizes its work into **three primary operational processes** (the core
value stream, the quality feedback loop, and the measurement/governance loop) plus an
automated **hygiene process** upholding workspace resource safety:

| Process | Process Owner | Process Client | Delegated Implementers | Product (what the client consumes) | Declared cadence / trigger | Quality Criteria (Stakeholder Value) | Trace / Evidence | Applicable measures |
|---|---|---|---|---|---|---|---|---|
| **1. Work Delivery Pipeline** | HQ | Factory Owner / Requester | Triage (intake/assign), Worker (code), CI (gates), Carrier (ship) | **Verified release** — merged change with all gates green | on finding, gap, or task | Zero regressions, rapid cycle time, verified release without rollback | Board issue, ledger intake/claim/close rows, git commit | throughput · duration · first-pass yield · waste |
| **2. Rework Prevention & Learning Loop** | Triage | HQ (owner of Process 1) + Factory Owner | Triage lane, defect resolving lane | **Prevention gate** — `rework.md` entry whose `Prevented by` mechanism stops the defect family recurring | on defect resolution | Root mechanism (not symptom) identified; actionable test or gate prevents recurrence | Entry in `evidence/rework.md`, passing `tests/test_rework.py` | throughput · first-pass yield · duration |
| **3. Operational Measurement & Consulting** | Surveys | Owner & Member Factory HQs | Surveys lane / cron (`factory-measurement-daily`) | **Score diff + advisory** — reproducible score and actionable guidance the member HQ consumes | daily (09:00 MSK) | Objective, reproducible score diffs; actionable consulting guidance for member HQs | `evidence/scores/<date>.md`, ledger `score` row | cadence · duration · resources consumed · throughput |
| **4. Workspace Hygiene Sweep** | HQ | Host Environment / Operators | Automated runner / cron (`python3 tools/hygiene.py`) | **Clean tree** — zero stale scratch, zero untracked clutter | daily | Zero resource exhaustion; stale scratch scripts reaped; clean git tree | Clean audit log from `tools/hygiene.py` | cadence · duration · first-pass yield |

---

## 4. Process Specifications and Subprocesses

### 4.1 Work Delivery Pipeline (Value Stream)
- **Process Owner:** HQ
- **Process Client:** Factory Owner / Requester
- **Product:** Verified release — the merged change with all gates green the client consumes
- **Subprocesses:**
  1. *Intake & Specification (Implementer: Triage)*: Converts findings into board issues with clear scope and verifiable acceptance criteria. Emits ledger `intake` event.
  2. *Assignment & Briefing (Implementer: Triage)*: Checks claims, acquires lock, and emits ledger `claim` event with direct session briefing.
  3. *Implementation & Self-Verification (Implementer: Worker)*: Writes code and runs the verification suite.
  4. *The Verification Gates (Implementer: Automated test suite)*:
     - `test_ontology.py` (vocabulary conformance)
     - `test_rework.py` (contiguous rework logging)
     - `test_template_sync.py` (template sync pair identity)
     - `test_single_writer.py` (single-writer state surface audit & lock verification)
     - `tools/ledger.py verify` (ledger sequence & monotonicity)
  5. *Ship & Release (Implementer: Carrier)*: Fast-forward merges to main, verifies artifact identity, and emits ledger `close` event.
- **Quality Criteria:** Complete pipeline cycle delivers verified change with zero rollbacks and all gates green in <10s.

### 4.2 Rework Prevention & Learning Loop (Feedback Loop)
- **Process Owner:** Triage
- **Process Client:** HQ (owner of Process 1) + Factory Owner
- **Product:** Prevention gate — a `rework.md` entry whose `Prevented by` mechanism the client consumes as fewer repeat defects and lower waste
- **Subprocesses:**
  1. *Defect Mechanism Extraction (Implementer: Triage)*: Isolates the structural flaw rather than narrative blame.
  2. *Mechanized Prevention (Implementer: Fixing Lane)*: Adds an automated test, gate, or codified rule preventing the defect.
  3. *Audit & Entry Gate (Implementer: Triage)*: Appends contiguous entry to `evidence/rework.md` passing `tests/test_rework.py` invariants.
- **Quality Criteria:** Zero defect recurrences; 100% of rework entries carry audited, non-placeholder `Prevented by` mechanisms.

### 4.3 Operational Measurement & Consulting (Governance Loop)
- **Process Owner:** Surveys
- **Process Client:** Factory Owner & Member Factory HQs
- **Product:** Score diff + advisory — the reproducible score and actionable guidance the member HQ consumes
- **Subprocesses:**
  1. *Internal Self-Audit (Implementer: tools/audit.py)*: Executes automated verification of meta-factory ledger sequence, rework rates, lead times, and the 6 mechanical gates.
  2. *Meta-Audit of Member Factories (Implementer: Surveys)*: Audits the integrity of member self-audits:
     - *Cadence Verification*: Checks whether member self-audits fired on declared schedule (Client Principle).
     - *Structural Invariants*: Audits member ledger monotonicity and single-writer locking.
     - *Calibration Spot-Check*: Samples one recently closed task and verifies unbroken intake -> claim -> close sequence.
  3. *Consulting Diagnostics & Advisory (Implementer: Surveys & Delegate)*: Synthesizes fleet patterns, identifies stopped processes or harness friction, and dispatches actionable advisories to member HQs.
  4. *Ledger Telemetry (Implementer: Surveys)*: Appends ledger `score` or `run` rows and commits score diffs.
- **Quality Criteria:** Self-audit automated via `tools/audit.py`; meta-audit spot-checks prevent grade inflation; advisories measurably increase member factory yield.

### 4.4 Workspace Hygiene Sweep (Hygiene Loop)
- **Process Owner:** HQ
- **Process Client:** Host Environment / Operators
- **Product:** Clean tree — zero stale scratch, zero untracked clutter the operators consume
- **Subprocesses:**
  1. *Scratch Script Audit (Implementer: tools/hygiene.py)*: Detects `/tmp/oc-*` scripts older than 24 hours.
  2. *Garbage Collection (Implementer: tools/hygiene.py)*: Safely reaps orphaned scratch files to prevent inode/space exhaustion.
  3. *Git Status Verification (Implementer: tools/hygiene.py)*: Asserts working tree is free of untracked clutter.
- **Quality Criteria:** Host storage remains unexhausted; zero orphaned scratch scripts >24h.
