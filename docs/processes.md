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

Every process in this register adheres to eight structural laws:

1. **The Client Principle (Ruling 4, 2026-09-13):** Every process runs for a
   **process client**. The client decides why the process runs, sets its trigger
   condition or cadence expectation, and consumes its value.
2. **Every process delivers a product with explicit client value:** A process
   delivers verifiable **product(s)** to its client(s). Every product must carry
   an explicit statement of the **client value** it provides (e.g. fewer repeat
   defects, zero operator toil, lower waste). A product without recorded client
   value is an unverified output.
3. **Many-to-many process-to-product relationship:** One process can deliver
   multiple distinct products (e.g. Process 3 delivers scores, advisories, and
   insight stories), and one product can be produced or hardened by multiple
   processes (e.g. the template product is built by Process 1, hardened by
   Process 2, and calibrated by Process 3).
4. **Failure to start is an execution failure:** When the client's trigger condition
   fires or the declared interval passes, failure to start is recorded as a
   failure (`outcome = failed`). It directly lowers **first-pass yield** and
   depresses **Stability (O2)**.
5. **Single Process Ownership (P30):** Every declared process has exactly one named
   **process owner** role. Shared ownership is zero ownership. Accountability cannot
   be split or delegated; execution alone is delegated to **process implementers**.
6. **Law-Upholding Law (P29):** Every codified law in this factory must be upheld by
   an active process registered here or a deterministic mechanical gate. A rule without
   an upholding mechanism is dead text.
7. **The Pacemaker Law (P28):** Every periodic process declared here must have an active
   scheduled thin pacemaker job waking the persistent session UUID of the process owner.
8. **Subprocesses recurse:** When an implementer's execution consists of distinct
   stages, each stage is a **subprocess** with its own `(Process Client, Process
   Owner, Delegated Implementers, Process Quality Criteria, Product & Client Value)`
   tuple.
9. **The Dual-Rail Architecture (Fast Path vs Durable Ledger):** Multi-agent
   handoffs must decouple Fast Path execution signaling (Rail 1: direct peer-to-peer
   `session_notify` goal push) from the Durable State of Record (Rail 2:
   `evidence/ledger.jsonl` under `fcntl.flock`) and the Safety Net (Rail 3:
   scheduled watchdog pacemakers for stalled tasks $>30\text{m}$). Polling-based
   handoffs are prohibited due to the $\frac{\Delta t}{2}$ queue dwell tax.

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

| Process | Process Owner | Process Client | Delegated Implementers | Product & Client Value | Declared cadence / trigger | Quality Criteria (Stakeholder Value) | Trace / Evidence | Applicable measures |
|---|---|---|---|---|---|---|---|---|
| **1. Work Delivery Pipeline** | HQ | Factory Owner / Requester | Triage (intake/assign), Worker (code), CI (gates), Carrier (ship) | **Verified release & Template artifacts** (Client Value: Zero regressions, new capabilities shipped, fast lead time) | on finding, gap, or task | Zero regressions, rapid cycle time, verified release without rollback | Board issue, ledger intake/claim/close rows, git commit | throughput · duration · first-pass yield · waste |
| **2. Rework Prevention & Learning Loop** | Triage | HQ (owner of Process 1) + Factory Owner | Triage lane, defect resolving lane | **Prevention gate** (Client Value: Defect family permanently eliminated, rework rate reduced, token waste averted) | on defect resolution | Root mechanism (not symptom) identified; actionable test or gate prevents recurrence | Entry in `evidence/rework.md`, passing `tests/test_rework.py` | throughput · first-pass yield · duration |
| **3. Operational Measurement & Consulting** | Surveys | Owner & Member Factory HQs | Surveys lane / cron (`factory-measurement-daily`) | **Score diff, Consulting advisory, & Insights entries** (Client Value: Objective bottleneck visibility, prioritized actionable fixes, predictable growth trajectory) | daily (09:00 MSK) | Objective, reproducible score diffs; actionable consulting guidance for member HQs | `evidence/scores/<date>.md`, `evidence/insights.jsonl`, ledger `score` row carrying the workspace-gate verdict (`workspace_gate=rc=0`) | cadence · duration · resources consumed · throughput |
| **4. Workspace Hygiene Sweep** | HQ | Host Environment / Operators | Automated runner / cron (`python3 tools/hygiene.py`) | **Clean tree** (Client Value: Zero runaway storage, zero stale scratch interference, reproducible builds) | daily | Zero resource exhaustion; stale scratch scripts reaped; clean git tree | Clean audit log from `tools/hygiene.py` | cadence · duration · first-pass yield |

---

## 3.1 Product-to-Process Synthesis

Every deliverable product of the meta-factory maps directly to its producing process(es):

| Product | Producing Process | Lifecycle & Maintenance |
|---|---|---|
| **1. The Factory Template & Add-on Packs** | **Process 1 (Work Delivery)** *(hardened by P2 & P3)* | Versioned in `TEMPLATE/`, verified by `test_template_sync.py` |
| **2. The Consulting Practice & Advisories** | **Process 3 (Measurement & Consulting)** | Generated daily during surveys, delivered via Delegate lane |
| **3. The Factory Growth & Maturity Map** | **Process 1 (Work Delivery)** *(calibrated by P3)* | Maintained in `docs/growth-stages.md`, updated upon fleet discoveries |
| **4. The Empirical Insights Story** | **Process 3 (Measurement & Surveys)** | Appended to `evidence/insights.jsonl`, compiled to `docs/stories/` |

---

---

## 4. Process Specifications, Atomic Subprocesses & Custom Acceptance Criteria

Every process decomposes into **atomic subprocesses** (`atomic_subprocess`) with strict input/output contracts, and must declare **custom acceptance criteria** (`custom_acceptance_criteria`) defining domain correctness.

---

### 4.1 Work Delivery Pipeline (Process 1: Value Stream)
- **Process Owner:** HQ
- **Process Client:** Factory Owner / Requester
- **Product:** Verified release — the merged change with all gates green the client consumes
- **Custom Acceptance Criteria:**
  1. Complete pipeline cycle delivers verified change with zero rollbacks and **every**
     mechanical gate passing (`python3 tools/audit.py` rc=0). The gate list, its count and
     its runtime are read live from that surface, never restated here: a hardcoded figure
     drifts the moment a gate is added, and nothing prints the stale one (this line read
     "all 8 mechanical gates passing in <10s" while the suite was 15 gates and ~25s).
  2. First-pass yield on closed tasks $\ge 90\%$.
  3. Average task execution lead time $\le 30$ minutes with queue dwell time $< 5\%$ of lead time achieved via Dual-Rail push handoffs.
  4. Byte-for-byte synchronization of all template pairs verified by `test_template_sync.py`.

- **Atomic Subprocesses (`atomic_subprocess`):**

| Subprocess | Implementer | Input Contract | Output Contract | Primary Failure Mode | Subprocess Metric |
|---|---|---|---|---|---|
| **1. Intake & Calibration** | Triage | Raw finding, issue, or request | Scored issue with verified custom acceptance criteria | Ambiguous goal / stalled queue | Queue dwell time ($t_{\text{claim}} - t_{\text{intake}}$) |
| **2. Lock & Claim** | Triage / Worker | Intake issue on board | `claim` row in ledger under `fcntl.flock` (Rail 2) + Rail 1 push goal via `session_notify` | Double-claim / race condition / dropped dispatch | Monotonicity, sequence validity & push dispatch latency ($\approx 0\text{s}$) |
| **3. Feedforward Context Assembly** | Worker | Push-dispatched task contract + `SKILL.md` + `rework.md` | Grounded context window with rules & criteria | Missing constraint / prompt amnesia | First-token prompt size & rule hit |
| **4. Implementation Loop (Ralph)** | Worker | Grounded context | Candidate code diff / artifact | Logic defect / hallucination | Turn count per task & token cost |
| **5. Multi-Criteria Gate Evaluation** | Automated Gates | Candidate artifact | Deterministic score vector & error trace | Silent pass / false positive | Gate execution duration & exit code |
| **6. Settlement & Release** | HQ / Carrier | All gates green | Fast-forward commit on main + `close` row (Rail 2) + Rail 1 ack + the board issue closed with its receipt | Stale sha / broken remote push / false open (`close` row written, board issue still open) | Commit sha identity & delivery trace · board/ledger close agreement |

**The settlement receipt is taken AFTER the row it certifies — and the TOOL takes it (procedure).** The `close` row is appended first, then the sequence check runs against a ledger that **includes** that row, and the receipt records the population it covered. Taken before the append, the receipt is structurally incapable of covering the artifact it certifies: `verify` reads a subject's rows as a sequence, so a run made while the `close` row does not yet exist has not seen the row it is cited for. This is an ORDER defect, never a claim about honesty — a citation taken early is not a false citation, and the rows that carry one stand as written.

**Its upholding mechanism is the WRITE PATH, not a declaration by the author (2026-09-25, superseding the `rows=` gate).** The order above and a receipt *inside* the close row cannot both hold in one append, so the rule previously asked the author to declare `rows=<count>` at least the row's own number — a value assigned inside the append lock, which the author cannot know. Satisfying it required **predicting** `current_count + 1`, right until a peer appended in between: measured across all five factory ledgers, 2 of 17 declaring closes were off by exactly one. `append --event close` therefore writes a **second row inside the same lock** — a `run` row carrying `verified_rows=N`, N being the count the check covered with the close row present — and the declaration, its reader, its gate, its exemption files and its boundary are retired. Rows that already carry `rows=` stand as written and are never backfilled (#96, ruling n=745; simplified under plan 2646d31a).

---

### 4.2 Rework Prevention & Learning Loop (Process 2: Feedback Loop)
- **Process Owner:** Triage
- **Process Client:** HQ (owner of Process 1) + Factory Owner
- **Product:** Prevention gate — a `rework.md` entry whose `Prevented by` mechanism the client consumes as fewer repeat defects and lower waste
- **Custom Acceptance Criteria:**
  1. Zero defect recurrences in tracked defect families.
  2. 100% of rework entries carry audited, non-placeholder `Prevented by` mechanisms validated by `test_rework.py`.
  3. Root mechanism (not human/lane narrative blame) isolated in $<1$ turn.

- **Atomic Subprocesses (`atomic_subprocess`):**

| Subprocess | Implementer | Input Contract | Output Contract | Primary Failure Mode | Subprocess Metric |
|---|---|---|---|---|---|
| **1. Defect Mechanism Extraction** | Triage | Observed failure or escaped defect | Isolated structural root cause | Blame narrative / symptom focus | Extraction lead time |
| **2. Mechanized Gate Construction** | Fixing Lane | Isolated root cause | New test in `tests/` or rule in `SKILL.md` | Non-biting gate / dead test | Probe test verification |
| **3. Entry Gate Audit** | Triage | Row appended by the lane that holds the defect | Audited row in `evidence/rework.md` | Fragmented table / blank line | `tests/test_rework.py` pass |

---

### 4.3 Operational Measurement & Consulting (Process 3: Governance Loop)
- **Process Owner:** Surveys
- **Process Client:** Factory Owner & Member Factory HQs
- **Product:** Score diff, consulting advisory, & documentation calibration report
- **Custom Acceptance Criteria:**
  1. Self-audit automated via `tools/audit.py`; meta-audit spot-checks prevent grade inflation.
  2. Documentation class (`documentation_class`) evaluated across all 4 dimensions ($\ge 2/4$ baseline).
  3. Surveys cite member custom acceptance criteria; surveys without custom criteria cap at score 1/4.
  4. Advisories measurably reduce member factory queue dwell time and increase first-pass yield.

- **Atomic Subprocesses (`atomic_subprocess`):**

| Subprocess | Implementer | Input Contract | Output Contract | Primary Failure Mode | Subprocess Metric |
|---|---|---|---|---|---|
| **1. Internal Self-Audit** | `python3 tools/audit.py --report` | Local ledger, rework log, and test suite | `evidence/scores/<date>-self-audit.md` — which must NAME its ledger read instant (`YYYY-MM-DDTHH:MM:SSZ`) and say it is a start-of-run snapshot; ledger run row | Stale scratch files / gate failure | Gate pass rate & duration |
| **2. Documentation Calibration** | Surveys / Delegate | Target factory repo | 0–4 Documentation score vector | Cold-start survey blindness | Documentation baseline score ($\ge 2/4$) |
| **3. Onboarding Interview Loop** | Delegate | Factory operator | Minimal `ONTOLOGY.md`, `SKILL.md`, `processes.md`, `docs/products.json` | Vague domain requirements | Interview turns to baseline |
| **4. Member Self-Audit Meta-Audit** | Surveys | Member factory `evidence/scores/` | Verified cadence & spot-checked receipts | Superficial checklist audit | Dwell ratio & yield delta |
| **5. Advisory Dispatch & Telemetry** | Delegate / Surveys | Synthesized fleet findings | Briefing to member HQ + `score` row | Unactionable advice / noise | Member adoption rate |

> **Defined exit from the RED roadmap gate.** The loop's output includes `docs/products.json` — this factory's own product declaration. Until that file declares this factory's products, `tools/roadmap.py` reports RED with the reason *"no product declaration at docs/products.json"*. A newly bootstrapped factory is therefore **specified to be red, not broken**: the red state is the honest reading of "this factory has not said what it produces yet", and the onboarding interview is the documented way out. Copy `docs/products.example.json` to `docs/products.json` and replace every placeholder.

---

### 4.4 Workspace Hygiene Sweep (Process 4: Hygiene Loop)
- **Process Owner:** HQ
- **Process Client:** Host Environment / Operators
- **Product:** Clean tree — zero runaway storage, zero stale scratch interference
- **Custom Acceptance Criteria:**
  1. Host storage remains unexhausted; zero orphaned scratch scripts $>24$h.
  2. Clean git status with zero untracked artifacts.

- **Atomic Subprocesses (`atomic_subprocess`):**

| Subprocess | Implementer | Input Contract | Output Contract | Primary Failure Mode | Subprocess Metric |
|---|---|---|---|---|---|
| **1. Scratch File Sweep** | `tools/hygiene.py` | `/tmp/oc-*` filesystem paths | List of aged scratch files ($>24$h) | Missed rogue scratch processes | Reaped item count |
| **2. Garbage Collection** | `tools/hygiene.py` | Aged file list | Clean filesystem & reaped files | Permission error / incomplete wipe | Reaped bytes & exit code |
| **3. Git Workspace Audit** | `tools/hygiene.py` | Working directory status | Clean tree verification receipt | Untracked clutter accumulation | Git status exit code |
