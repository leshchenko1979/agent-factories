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

## 5. Task-State Memory Binding (`plan` vs `session_context`)

A durable task contract and ephemeral in-flight variables are **two different memory needs**, satisfied by two different substrates. Using one for the other is the defect.

| Memory Need | Substrate | Persistence | Correct Use |
|---|---|---|---|
| **Macroscopic task contract** | `plan` tool | Disk JSON (`.opencrabs_plan_<session-id>.json`) | Ordered steps, dependencies, and checkable acceptance criteria. Re-surfaced verbatim by `plan(operation="show_plan")`. |
| **Ephemeral in-flight variables** | `session_context` tool | Session store | Intermediate calculation state, resolved identifiers, decisions taken mid-task — values that must cross a compaction but do not deserve a durable artifact. |
| **Conversation history** | Message window | None (lossy) | **Never** a carrier for task state: it is summarized lossily at compaction. |

The `plan` card tracks **coarse task boundaries**; it does not carry fine-grained calculation state. A factory lane must pair both: the plan anchors *what remains to be done*, `session_context` anchors *what has already been computed*.

## 6. The Pre-Compaction Flush Protocol

The runtime emits an explicit **warning when context consumption approaches the compaction threshold**. This is a deterministic boundary signal, not an unpredictable crash, and it defines a mandatory state-flush step:

1. **On warning:** flush any un-persisted in-flight variable into `session_context`, and ensure every remaining step and acceptance criterion is written into the `plan` card.
2. **After compaction:** the first action is to reload the always-loaded recovery anchor (`SKILL.md`), then call `plan(operation="show_plan")` to re-anchor ground truth from disk before executing any further turn or asserting any status.
3. **Never** rely on pre-compaction *instructions* surviving compaction: in-context instructions are summarized away. Only what is written to an always-injected file or a durable substrate survives.

## 7. Working Directory Control

The session working directory is persistent state, not a per-command detail:

- `config_manager(operation="set_working_directory", path="...")` mutates it for the session across turns. A `cd` inside one `bash` call does **not** persist to the next call — chaining `cd <dir> && <cmd>` only scopes that single invocation.
- A lane must set its working directory explicitly at the start of a work unit rather than relying on an inherited default.
