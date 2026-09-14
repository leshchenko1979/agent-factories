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

### Stage 1: Autonomous Intake (Continuous Flow)

- **Throughput:** 5–50 tasks / week.
- **Operating Profile:** Scheduled jobs (crons) periodically scan the issue board, match open tasks, and invoke worker agents.
- **The Roadblock:** **The Concurrency Paradox & Queue Lag Illusion.**
  1. Multiple cron sweeps spawn duplicate workers on the same issue, leading to git merge collisions and clobbered work.
  2. While LLMs code in minutes, tasks spend 95% of their lifecycle idling in queue waiting for polling cycles (The 10.4-Hour Queue Trap).
- **Breakthrough Mechanism:** Atomic task claiming via exclusive file locks (`fcntl.flock`) and single-writer state surfaces.
- **Primary Metric:** `queue_dwell_time` (time from issue creation to first worker claim).

---

### Stage 2: Single-Writer & Concurrency Locking

- **Throughput:** 50–200 events / day.
- **Operating Profile:** Multi-lane operations. Persistent topic-bound workers. State transitions recorded in immutable, append-only ledgers (`evidence/ledger.jsonl`).
- **The Roadblock:** **The Inspector's Trap & Silent Rework.**
  The factory appears busy and commits are landing, but defects are repeatedly caught downstream. Without internal telemetry, the factory cannot distinguish real progress from repetitive churn and rework loops.
- **Breakthrough Mechanism:** The **Self-Audit Kit** (`tools/audit.py`). Transition from external inspection to internal self-auditing, calculating First-Pass Yield and Rework Rate mechanically.
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
| **0** | **1** | Operator spends >2 hrs/day babysitting agent turns | Issue board intake + automated scheduler |
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
