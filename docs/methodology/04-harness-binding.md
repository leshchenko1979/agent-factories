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

## 2. Standalone Zero-Token Pacemaker Crons (`trigger_cmd`)

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

## 3. Post-Compaction Recovery Anchors

Context compaction wipes conversation history. To prevent amnesia:
1. Every profile injects an always-loaded recovery anchor pointing to the factory's `SKILL.md`.
2. The agent's mandatory first action post-compaction is to reload `SKILL.md` before executing turns or asserting status claims.
