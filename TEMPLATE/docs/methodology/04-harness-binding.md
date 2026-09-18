# Methodology Module 04: Harness Binding (OpenCrabs Runtime)

> **Core Law:** A factory law states requirements; a harness binding states the mechanics that satisfy them on a specific agent runtime.

---

## 1. Addressing & Inter-Lane Goal Dispatch

In OpenCrabs, agent sessions are identified by immutable **Session UUIDs**.

| Communication Path | Mechanism | Usage Rule |
|---|---|---|
| **Inter-Lane Task Briefing** | `session_notify` | **Mandatory.** Delivers structured task seeds directly into a worker's context window. |
| **Autonomous Goal Dispatch** | `session_notify` with `goal` & `goal_max_turns` | **Autonomy standard (v0.5.1).** Automatically activates GoalManager in target session for bounded inner-loop convergence without conversational prompting. |
| **Receipt / Ack Delivery** | `session_notify(delivery={"mode": "quiet"})` | Queues notification silently without interrupting an active turn. |
| **Urgent Escalation** | `session_notify(delivery={"mode": "now"})` | Triggers immediate attention on critical failures. |
| **Cross-Factory Goal Delegation** | A2A Notify (`a2a_send` / JSON-RPC) | Extracts and establishes active goals across agent-to-agent boundaries. |
| **Chat Topic Posts** | `telegram_send` | **Human visibility only.** Agents do NOT read chat topics; briefing via chat does zero work. |

---

## 2. The Dual-Rail Architecture: Fast-Path Push Handoff vs Durable Ledger

A multi-agent factory must decouple its **State of Record** from its **Execution Transport Plane** to prevent the queue dwell tax from dominating task cycle time.

```
+--------------------------------------------------------------------------------+
| DUAL-RAIL MULTI-AGENT EXECUTION ARCHITECTURE                                  |
|                                                                                |
|  [ Rail 1: Fast Path (Execution Transport Plane) ]                             |
|    Upstream Lane (Triage) === session_notify(push goal) ===> Downstream Lane  |
|    - Push-based event signaling (0s queue dwell)                              |
|    - Wakes target session UUID immediately with goal & turn budget             |
|                                                                                |
|  [ Rail 2: State of Record (Durable Ledger Plane) ]                            |
|    Upstream Lane (Triage) ---> fcntl.flock append (claim)                     |
|    Downstream Lane (Worker) -> fcntl.flock append (close)                      |
|    - Single-writer append-only sequence (evidence/ledger.jsonl)               |
|    - Guarantees recovery checkpoints, monotonicity, and audit integrity        |
|                                                                                |
|  [ Rail 3: Safety Net (Reconciliation / Watchdog Plane) ]                      |
|    Cron Pacemaker (e.g. factory-triage-hourly) -- sweeps ledger claims > 30m   |
|    - Catches dropped messages, crashed workers, or stalled turns               |
|    - Does NOT act as the primary conveyor belt                                 |
+--------------------------------------------------------------------------------+
```

### 2.1 The Queue Dwell Tax ($T_{\text{dwell}} = \frac{\Delta t}{2}$)
If downstream workers poll a shared ledger or issue board on an hourly cron ($\Delta t = 60\text{m}$), the average work unit sits idle in the queue for **30 minutes** before execution begins ($T_{\text{dwell}} = 30\text{m}$). If coding takes 2 minutes, **idle queue dwell constitutes 94% of the entire task lead time**.

Push-based handoffs eliminate polling dwell entirely ($T_{\text{dwell}} \approx 0\text{s}$), enabling true single-piece flow.

### 2.2 Subprocess Handoff Protocol
When an upstream lane (e.g. Triage in Subprocess 1.2) completes its stage and hands over to a downstream lane (e.g. Worker in Subprocess 1.3/1.4):
1. **Durable Lock (Rail 2):** Append the state transition to `evidence/ledger.jsonl` under `fcntl.flock` (e.g. `event: claim`).
2. **Immediate Push Dispatch (Rail 1):** Dispatch `session_notify` directly to the target worker session UUID with `goal`, `goal_max_turns`, and the calibrated task contract.
3. **Execution (Worker Inner Loop):** Target session wakes immediately on the next tool loop boundary, loads feedforward constraints, and runs the Ralph evaluation loop against mechanical test gates.
4. **Completion Settlement:** Worker passes all test gates, appends `event: close` under `fcntl.flock` (Rail 2), and pushes an acknowledgment receipt back to Triage/HQ (Rail 1).
5. **Watchdog Reconciliation (Rail 3):** If a worker crashes or exceeds the 30-minute lead time SLA, the scheduled cron pacemaker detects the stale claim and triggers recovery.

---

## 3. Standalone Zero-Token Pacemaker Crons (`trigger_cmd`)

To eliminate token waste on idle heartbeat turns, OpenCrabs crons support **headless 0-token trigger probes** where the `prompt` parameter is omitted:

```bash
# Example trigger_cmd in cron definition (cron_manage):
# 1. Checks if remote main has drifted or if unassigned issues exist
# 2. Evaluated via TriggerCondition (ExitZero or Regex)
git fetch origin main && [ $(git rev-parse HEAD) != $(git rev-parse origin/main) ]
```

### TriggerCondition Types
- **`ExitZero` (`exit_0`, `exitzero`, `zero`):** Triggers only when `trigger_cmd` exits with code 0.
- **`Regex(pattern)` (`regex:<pattern>`, `re:<pattern>`):** Evaluates regex match against command stdout/stderr.

### Execution Flow
1. **Cron fires on schedule:** Runs `trigger_cmd` in a local shell subshell.
2. **If TriggerCondition matches:** Dispatches wake-up payload (`session_notify` with active `goal`) to target session UUID.
3. **If TriggerCondition does not match:** Exits silently. **0 LLM tokens spent.**

---

## 4. Post-Compaction Recovery Anchors

Context compaction wipes conversation history. To prevent amnesia:
1. Every profile injects an always-loaded recovery anchor pointing to the factory's `SKILL.md`.
2. The agent's mandatory first action post-compaction is to reload `SKILL.md` before executing turns or asserting status claims.

---

## 5. The Five Memory Tiers of the Runtime

The runtime does not have "memory"; it has five distinct tiers, each with its own persistence
guarantee. A lane that conflates them either loses state or wastes context.

| Memory Tier | Substrate Mechanism | Location / Scope | Operational Role |
|---|---|---|---|
| **Tier 0: Structural Invariants** | Core brain files | `SOUL.md`, `USER.md`, `AGENTS.md` (injected last, nearest the generation point) | Unconditional behavioural constraints and security boundaries. |
| **Tier 1: Passive In-Flight Recall** | `memory_recall.rs` (length-normalised BM25) | Rides along in the user prompt envelope | Automatic, zero-effort contextual conditioning before turn 1. A model that never volunteers a search still receives the match. |
| **Tier 2: Active Multi-Corpus Retrieval** | `memory_search` (hybrid RRF: FTS5 BM25 + vector) | Scopes: `brain` (rules), `memory` (history), `external` (code graph) | Deliberate research and prior-precedent lookups. |
| **Tier 3: Substrate Task State** | `plan` tool and `session_context` | Disk JSON (`.opencrabs_plan_<session-id>.json`) and the session store | Durable task contracts and in-flight variables that survive compaction. |
| **Tier 4: Durable Factory History** | `evidence/ledger.jsonl` and `evidence/rework.md` | Single-writer disk files (`fcntl.flock`) | Monotonic state transitions and defect root-cause preventions. |

Tier 0 is unconditional, Tier 1 is automatic, Tier 2 is deliberate, Tier 3 is written by the
lane itself, Tier 4 is written by the factory. Anything a lane needs after a compaction must
already be in Tier 0 or Tier 3 — Tiers 1 and 2 are lookups the lane may or may not make, and
the message window is not a tier at all.

## 6. Task-State Memory Binding (`plan` vs `session_context`)

A durable task contract and ephemeral in-flight variables are **two different memory needs**, satisfied by two different substrates. Using one for the other is the defect.

| Memory Need | Substrate | Persistence | Correct Use |
|---|---|---|---|
| **Macroscopic task contract** | `plan` tool | Disk JSON (`.opencrabs_plan_<session-id>.json`) | Ordered steps, dependencies, and checkable acceptance criteria. Re-surfaced verbatim by `plan(operation="show_plan")`. |
| **Ephemeral in-flight variables** | `session_context` tool | Session store | Intermediate calculation state, resolved identifiers, decisions taken mid-task — values that must cross a compaction but do not deserve a durable artifact. |
| **Conversation history** | Message window | None (lossy) | **Never** a carrier for task state: it is summarized lossily at compaction. |

The `plan` card tracks **coarse task boundaries**; it does not carry fine-grained calculation state. A factory lane must pair both: the plan anchors *what remains to be done*, `session_context` anchors *what has already been computed*.

## 7. The Pre-Compaction Flush Protocol

The runtime emits an explicit **warning when context consumption approaches the compaction threshold**. This is a deterministic boundary signal, not an unpredictable crash, and it defines a mandatory state-flush step:

1. **On warning:** flush any un-persisted in-flight variable into `session_context`, and ensure every remaining step and acceptance criterion is written into the `plan` card.
2. **After compaction:** the first action is to reload the always-loaded recovery anchor (`SKILL.md`), then call `plan(operation="show_plan")` to re-anchor ground truth from disk before executing any further turn or asserting any status.
3. **Never** rely on pre-compaction *instructions* surviving compaction: in-context instructions are summarized away. Only what is written to an always-injected file or a durable substrate survives.

## 8. Working Directory Control

The session working directory is persistent state, not a per-command detail:

- `config_manager(operation="set_working_directory", path="...")` mutates it for the session across turns. A `cd` inside one `bash` call does **not** persist to the next call — chaining `cd <dir> && <cmd>` only scopes that single invocation.
- A lane must set its working directory explicitly at the start of a work unit rather than relying on an inherited default.

## 9. Context-Manifest Curation & Compaction Retention

Empirical findings from OpenCrabs Dev across 778 production compactions demonstrate that compaction retention is governed by prompt manifest guidance rather than binary daemon modifications.

### 9.1 Empirical Compaction Dataset (N = 778)
- **Manifest Retention Efficiency:** >93% retention of active skills when guided; 0.00% contradictory auxiliary retention when obsolete skills are explicitly listed in `discard_skills`.
- **Top Retained Tools Post-Compaction:**
  - `session_notify`: 61.3%
  - `session_search`: 43.8%
  - `bash`: 34.9%
  - `telegram_send`: 31.0%
  - `read_file`: 26.8%

### 9.2 Section 10 Manifest Standard
Every factory lane prompt envelope and role template standardizes a Section 10 context-manifest structure:

```yaml
context_manifest:
  active_skills:
    - <factory-root-skill>
    - <active-role-card>
  discard_skills:
    - <stale-role-card-1>
    - <stale-role-card-2>
  required_tools:
    - session_notify
    - session_search
    - bash
    - read_file
    - edit_file
    - write_file
```

By explicitly curating `active_skills`, discarding inactive sibling roles, and declaring `required_tools`, agent sessions maintain immediate operational readiness without tool search latency or skill amnesia post-compaction.
