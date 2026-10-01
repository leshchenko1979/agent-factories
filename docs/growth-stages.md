# Factory Growth & Maturity Map

**Owns:** the evolutionary trajectory of agent factories across throughput bands, mapping the
inevitable roadblocks and the structural mechanisms required to transition between stages.

---

## 0. The Core Thesis: Roadblocks Shift With Throughput

A factory producing 5 commits a month has fundamentally different failure modes than a
factory handling 1,200 events a day.

Applying Stage 3 governance to a Stage 0 experiment kills momentum with bureaucracy.
Conversely, trying to scale a Stage 1 prompt setup into continuous production produces
uncontrolled token burn, race conditions, and silent task loss.

This document maps the **5 stages of agent factory maturity**, defining:
1. **The Operating Profile** (velocity, actors, state model)
2. **The Inevitable Roadblock** (the ceiling that halts growth at that stage)
3. **The Breakthrough Mechanism** (the architectural transition required to unlock the next band)
4. **Primary Health Metric** (what to measure to know if the stage is healthy)

---

## 1. The 5 Evolutionary Stages

```mermaid
flowchart TD
    S0["<b>Stage 0: Interactive Prototype</b><br/>Human-in-the-loop prompts<br/><i>Roadblock: Operator attention bottleneck</i>"]
    S1["<b>Stage 1: Autonomous Intake</b><br/>Cron scanner + worker dispatch<br/><i>Roadblock: Race conditions & duplicate work</i>"]
    S2["<b>Stage 2: Single-Writer & Concurrency Locking</b><br/>Atomic ledgers, persistent lanes<br/><i>Roadblock: Invisible queue lag & silent stalls</i>"]
    S3["<b>Stage 3: Self-Auditing Quality Loops</b><br/>Internal telemetry, lead time, automated RCA<br/><i>Roadblock: Substrate tool friction & token cost waste</i>"]
    S4["<b>Stage 4: Fleet Ecosystem & Value Optimization</b><br/>Supplier-client feedback, value-weighted routing<br/><i>Roadblock: Strategic alignment & external economics</i>"]

    S0 -->|Add autonomous cron dispatch| S1
    S1 -->|Add atomic file locking & ledgers| S2
    S2 -->|Add internal self-audit kit| S3
    S3 -->|Add supplier-client fleet loops| S4
```

---

### Stage 0: Interactive Prototype (Prompt-Driven)

- **Throughput:** 1–5 tasks / week.
- **Operating Profile:** Single interactive session. Human operator writes prompts, reviews code, runs tests, and guides every turn.
- **The Roadblock:** **Operator Attention Fatigue.** The factory's capacity is strictly limited by human availability. The operator spends hours babysitting turn completions.
- **Breakthrough Mechanism:** Decouple intake from human presence. Move to issue boards as the single intake surface and introduce an autonomous polling trigger.
- **Primary Metric:** `turns_per_task` (human intervention ratio).

---

### Stage 1: Autonomous Intake & The Pacemaker Law (Continuous Flow)

- **Throughput:** 5–50 tasks / week.
- **Operating Profile:** Scheduled jobs (crons) act as thin pacemakers, periodically notifying persistent lane sessions to scan the issue board, match open tasks, and invoke worker agents.
- **The Pacemaker Law:** Every agent role that owns a periodic process must have a dedicated thin cron pacemaker waking its session UUID. Without it, conversational bias halts the loop.
- **The Roadblock:** **The Concurrency Paradox & Queue Lag Illusion.**
  1. Multiple cron sweeps spawn duplicate workers on the same issue, leading to git merge collisions and clobbered work.
  2. While LLMs code in minutes, tasks spend 95% of their lifecycle idling in queue waiting for polling cycles (The 10.4-Hour Queue Trap).
- **Breakthrough Mechanism:** Atomic task claiming via exclusive file locks (`fcntl.flock`), single-writer state surfaces, and thin session-nudging pacemakers.
- **Primary Metric:** `queue_dwell_time` (time from issue creation to first worker claim).

---

### Stage 2: Single-Writer & Concurrency Locking

- **Throughput:** 50–200 events / day.
- **Operating Profile:** Multi-lane operations. Persistent topic-bound workers. State transitions recorded in immutable, append-only ledgers (`evidence/ledger.jsonl`).
- **The Roadblock:** **The Inspector's Trap & Silent Rework.**
  The factory appears busy and commits are landing, but defects are repeatedly caught downstream. Without internal telemetry, the factory cannot distinguish real progress from repetitive churn and rework loops.
- **Breakthrough Mechanism:** The **Self-Audit Kit** (`tools/audit.py`). Transition from external inspection to internal self-auditing, calculating First-Pass Yield, Rework Share, and Rework per Close mechanically.
- **Primary Metric:** `first_pass_yield` (percentage of tasks completed without requiring rework).

---

### Stage 3: Self-Auditing Quality Loops

- **Throughput:** 200–1,000 events / day.
- **Operating Profile:** Autonomous continuous integration. Defects automatically trigger root-cause analysis (RCA), writing prevention rules into tests (`tests/test_rework.py`). The factory audits its own lead times and yields daily.
- **The Roadblock:** **Substrate Friction & Economic Waste.**
  Internal processes are disciplined, but execution hits limits in the underlying agent runtime (e.g. inability to bind forum topics autonomously, model timeout loops, token cost inefficiencies).
- **Breakthrough Mechanism:** **Supplier-Client Fleet Loops.**
  Formalize relationships with fleet suppliers:
  - Runtime harness supplier (e.g. OpenCrabs core): report substrate defects, demand native tools (e.g. Issue #170 topic auto-binding).
  - Inference provider (e.g. InferHub): monitor cache hit rates, prompt token demand, and model value routing.
- **Primary Metric:** `cost_per_accepted_task` ($ / task) split by Demand vs Supply.

---

### Stage 4: Fleet Ecosystem & Value Optimization

- **Throughput:** 1,000+ events / day.
- **Operating Profile:** Network of specialized, autonomous factories (development, analytics, domain bots) interacting via structured protocols. Minimal operator intervention required except for strategic priority setting.
- **The Roadblock:** **Strategic Alignment & Value Drift.**
  The machine runs at blistering speed, but optimizes for easy tasks rather than highest client value.
- **Breakthrough Mechanism:** Value-weighted priority routing (e.g. Artificial Analysis IQ / ask-weighted value crowns) and automated portfolio governance.
- **Primary Metric:** `net_client_value_delivered` per unit of capital burned.

---

## 2. Stage Transition Matrix

| From | To | Trigger to Evolve | Mechanics to Deploy |
|---|---|---|---|
| **0** | **1** | Operator spends >2 hrs/day babysitting agent turns | Issue board intake + thin cron pacemaker nudges |
| **1** | **2** | Workers collide on git branches or duplicate claims | `tools/ledger.py` with `fcntl.flock`, closed actor sets |
| **2** | **3** | Rework share exceeds 30% or tasks stall silently | `tools/audit.py`, `evidence/rework.md`, RCA gates |
| **3** | **4** | Substrate friction or token costs dominate spend | Supplier-client loops, runtime feature requests, value routing |

---

## 3. Template Packaging Rule

Every factory bootstrapped from the template starts with the architectural foundations for **Stage 2 and 3** pre-installed:
- `tools/ledger.py` (atomic single-writer locking)
- `tools/audit.py` (internal self-audit)
- `tests/test_single_writer.py` (state surface verification)
- `tools/hygiene.py` (garbage collection)

A new factory operates in **Stage 0 or 1** mode initially, but inherits the guardrails so it does not suffer the concurrency crashes and rework blindness when throughput accelerates.

---

## 4. Bi-Weekly Fleet Calibration & Maturity Verification (2026-09-16)

> **Pacemaker Cadence:** Bi-Weekly (1st & 15th) · `factory-growth-map-biweekly`  
> **Evaluation Rubric:** Quality Criteria v0.4 (17 criteria across 5 families, max 68) — the rubric this dated run was scored against; superseded by v0.5 (19 criteria across 6 families, max 76)  
> **Telemetry Source:** Live state across 6 fleet factories (`evidence/scores/2026-09-16.md`, `evidence/ledger.jsonl`, git trees, and CI/audit receipts)

### Fleet Maturity Census

| Factory | Score (v0.4/68) | Maturity Band | Active Stage | Target Stage | Breakthrough Mechanism Deployed | Primary Health Metric Status |
|---|:---:|:---:|:---:|:---:|---|---|
| **Meta-factory** | **65** (96%) | **Optimizing** | **Stage 3** | Stage 4 | Tier-1 Self-Audit Kit (8 green gates), single-writer `fcntl.flock`, automated RCA (`rework.md`) | First-pass yield: 100%, rework rate: 77.8%, avg cost/task: $0.0138 |
| **OpenCrabs dev** | **56** (82%) | **Optimizing** | **Stage 3** | Stage 4 | 4-leg smoke rubric, atomic `workers-ledger.json` (`fcntl.flock`), fast-swap rollback journal | Smoke pass rate: 100% on 850+ runs; throughput: 480+ events/day |
| **InferHub Watch** | **53** (78%) | **Optimizing** | **Stage 3** | Stage 3 | Tier-1 Self-Audit Kit, 762 automated pytests, hourly cron pacemaker | 100% self-audit yield; True TPS & latency telemetry active |
| **Miidas** | **53** (78%) | **Optimizing** | **Stage 3** | Stage 3 | Tier-1 Self-Audit Kit (8 green gates), single-writer `fcntl.flock`, `rework.md` | 100% self-audit yield; 337 pytests passing clean |
| **Infra Factory** | **50** (74%) | **Scalable** | **Stage 2** | Stage 3 | Single-writer ledger (`fcntl.flock`), 5 mechanical audit gates, topic-based coordination | 100% yield on 5 gates; first closed end-to-end task lead time met |
| **AI AntiSpam** | **35** (51%) | **Scalable** | **Stage 1** | Stage 2 | 0-token preflight cron pacemakers (`trigger_cmd`), Postgres single-writer | 500+ tests pass; blocked on D3 until file-level ledger & audit kit adopted |

### Stage-by-Stage Verification Summary

1. **Stage 0 (Interactive Prototype): 100% Graduated (0/6 active).**
   - No fleet factory relies on prompt-by-prompt human operator guidance.
   - All 6 factories intake tasks from persistent surfaces (GitHub boards, topic backlogs, or structured sweep epochs).

2. **Stage 1 (Autonomous Intake & The Pacemaker Law): 100% Conformance.**
   - All factories operate scheduled cron pacemakers waking persistent session UUIDs.
   - OpenCrabs v0.5.1 thin cron spec with zero-token pre-flight checks (`trigger_cmd`) and `set_goal: true` successfully rolled out to AI AntiSpam (`cfb86dc5`), Infra Factory (`d6119dbc`), and Miidas (`a2936da9`).
   - 1 factory (AI AntiSpam) currently resides at Stage 1, actively working on Stage 2 concurrency mechanisms.

3. **Stage 2 (Single-Writer & Concurrency Locking): 83.3% Deployed (5/6 active).**
   - Meta-factory, OpenCrabs dev, InferHub Watch, Miidas, and Infra Factory enforce immutable, append-only ledgers guarded by `fcntl.flock` with closed actor sets.
   - Concurrency collisions eliminated across multi-lane sessions.
   - AI AntiSpam has Postgres transaction safety for outreach, but requires the repo-level single-writer ledger to complete Stage 2 transition.

4. **Stage 3 (Self-Auditing Quality Loops): 66.7% Active / Piloted (4/6 active).**
   - **Meta-factory & OpenCrabs dev:** Full Stage 3 maturity. Meta-factory runs 8 deterministic gates via `tools/audit.py`, measuring lead times, yields, and automated issue generation (P1/P27). OpenCrabs dev enforces a 4-leg smoke verification rubric before any harvest PR.
   - **Miidas & InferHub Watch:** Piloting Stage 3. Miidas runs 8 green audit gates and maintains `rework.md`; InferHub Watch runs 762 automated pytests and hourly self-audits.
   - **Infra Factory:** Initial Stage 3 loops deployed with 5 mechanical audit gates.

5. **Stage 4 (Fleet Ecosystem & Value Optimization): 33.3% In Progress (2/6 pioneering).**
   - Meta-factory and OpenCrabs dev have established active supplier-client fleet loops.
   - Meta-factory reports substrate friction directly to OpenCrabs (e.g. Issue #170 forum topic auto-binding) and inference telemetry to InferHub.
   - OpenCrabs dev operates as the upstream engine supplying the runtime binary.
   - Next milestone: value-weighted task routing and cross-factory token economics.

---

## 5. Bi-Weekly Fleet Calibration & Maturity Verification (2026-10-01)

> **Pacemaker Cadence:** Bi-Weekly (1st & 15th) · `factory-growth-map-biweekly` (cron `e51a80de-c58b-44f3-ac73-fa5472ab07ea`, `0 9 1,15 * *`)
> **Read instant:** 2026-10-01T06:15Z UTC · meta-factory HEAD `78fa86b`
> **Evaluation Rubric:** Quality Criteria **v0.5** (19 criteria across 6 families, max 76).
> **Not differenced against §4:** that census was scored under **v0.4** (17 criteria, max 68), superseded by v0.5 — the two rubrics are not comparable, so this run reports the v0.5 census and leaves §4 as its own dated reading.
> **Telemetry Source:** `evidence/scores/2026-09-28.md` (the newest run — see the gap note), live `evidence/ledger.jsonl` via `tools/audit.py --no-gates`, `registry/index.json`, and the ops cron table.

### The telemetry gap this run must disclose

`evidence/scores/` holds **no run for 2026-09-29, 2026-09-30 or 2026-10-01**; the newest is **2026-09-28** (its own read instant 2026-09-28T07:10Z). So this calibration reads a **three-day-old** fleet survey and says so, rather than presenting it as current. The gap coincides with the **2026-09-30 daemon outage** Triage's grid reported: the `factory-measurement-daily` round for 2026-09-30 was receipted `duty=skipped`, its trigger never having fired. A calibration that silently read a stale survey would be indistinguishable from one that read a fresh one.

### Fleet Maturity Census (rubric v0.5, read 2026-09-28)

| Factory | Score (v0.5/76) | Band | Active Stage | Health metric at that read |
|---|:---:|:---:|:---:|---|
| **Meta-factory** | **71** (93.4%) | Optimizing | Stage 3 | 1,455 ledger rows / 173 close; rework share 45.43%; 70 of 71 gates PASS |
| **OpenCrabs dev** | **62** (81.6%) | Optimizing | Stage 3 | 11,830 state-ledger events; 4-leg smoke rubric; 2 ahead / 0 behind |
| **Miidas** | **59** (77.6%) | Optimizing | Stage 3 | 8 green audit gates + `rework.md`; live re-run 24/24 PASS |
| **InferHub Watch** | **58** (76.3%) | Optimizing | Stage 3 | 642 rows / 81 close; rework rate 2.5%; first-pass yield 99.4% |
| **Infra Factory** | **55** (72.4%) | Scalable | Stage 2 | Cadence `MISSED` (32.1h); live re-run `DEGRADED`, 17 PASS / 3 FAIL |
| **AI AntiSpam** | **51** (67.1%) | Scalable | Stage 1 → 2 | `#156` exemption surface landed; audit `HEALTHY`, 15 gates, 0 FAIL |
| **Fleet** | **356 / 456 (78.1%)** | — | — | — |

**The stage distribution is UNCHANGED from §4** — four factories at Stage 3, one at Stage 2, one at Stage 1. No factory crossed a band in this interval. AI AntiSpam remains the only Stage-1 factory and is still porting the Stage-2 concurrency mechanisms (its ledger instrument reads `partial`, one revision behind).

### Stage-by-Stage Verification Summary

1. **Stage 0 (Interactive Prototype): 0 / 6 active.** No factory relies on prompt-by-prompt operator guidance; all six intake from persistent surfaces.

2. **Stage 1 (Autonomous Intake & the Pacemaker Law): 6 / 6 conformance.** All six factories are enrolled in the fleet registry (`registry/fleet.json`) with a declared `job_prefixes` entry, and every cron row on this box attributes to exactly one of them by prefix. Live census: the ops cron table holds **65 rows**, of which **12 carry an explicit `--mode`** (9 turn-end, 3 quiet) — and the three `--mode quiet` rows belong to **ai-antispam and opencrabs-dev, none to meta-factory**.

3. **Stage 2 (Single-Writer & Concurrency Locking): NOT fleet-wide, and the mechanical signal is narrower than §4's prose.** §4 read this as 5/6 "active" on a structural basis. The signal this run can read mechanically is the registry fragment's own `instruments.ledger.state`, and it is **1 of 6 `adopted`** (meta-factory). The rest are `partial` (ai-antispam `behind_by=1`, red; inferhub-watch `behind_by=4`, red), `deferred` (infra-factory `behind_by=13`; miidas `behind_by=6`), or `not-applicable` (opencrabs-dev). **Adoption is a different predicate from "has an append-only ledger"** — the two are named apart here so a reader does not read one as the other.

4. **Stage 3 (Self-Auditing Quality Loops): 4 / 6 active, 1 piloting, 1 initial.** Meta-factory runs the full loop live at this read: `tools/audit.py` cadence held (`last_run_ts 2026-10-01T02:43:52Z`), **1,833 ledger rows** (intake 258 / claim 238 / close 232 / dispatch 286 / ruling 225 / run 574), and a rework instrument with **190 entries**, 21 unprevented. InferHub Watch, Miidas and Infra Factory carry their own self-audits; Infra Factory's reads `FAILED` on 8 named gate failures.

5. **Stage 4 (Fleet Ecosystem & Value Optimization): 2 / 6 pioneering.** Meta-factory and OpenCrabs dev hold active supplier-client loops. Unchanged from §4; value-weighted routing remains the open milestone.

### Live self-metrics (2026-10-01T06:15:32Z, HEAD `78fa86b`)

Read from `tools/audit.py --json --no-gates`; the gate verdict fields read `null` because the gate suite was deliberately skipped, never as a green.

| Metric | Value | Denominator / bound |
|---|---|---|
| Ledger events | **1,833** | — |
| Closed subjects | **226** | 232 close rows |
| Rework share | **45.67%** | 190 entries ÷ 226 closed subjects |
| Rework per close | **84.07%** | — |
| Change-fail rate | **68.14%** | 154 ÷ 226 |
| Rework subject coverage | **90.0%** | 171 ÷ 190 |
| First-pass yield | **1.0** | over **25 of 574** run rows — 4.4% of the population, stated with its denominator |
| Avg lead time | **64,817.3 s** | — |
| Cost per successful task | **$165.09** | — |

### What to watch

- **The measurement gap is the finding of this round.** A daily measurement job whose round can vanish in an outage leaves the growth map reading a stale survey; the map's own §5 is now a dated reading with a named gap rather than a silent one.
- **Infra Factory's ledger `behind_by=13`** is the fleet's largest kit lag, and its cadence row reads `MISSED`.
- **Six cron rows carry no attributable prefix** in the registry render (67 jobs, 6 unattributed), and `tamara_accounting_sync` sits in a profile home outside this factory's — reported, not touched.
