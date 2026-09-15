# Methodology Module 04: Harness Binding (OpenCrabs Runtime)

> **Core Law:** A factory law states requirements; a harness binding states the mechanics that satisfy them on a specific agent runtime.

---

## 1. Addressing & Inter-Lane Dispatch

In OpenCrabs, agent sessions are identified by immutable **Session UUIDs**.

| Communication Path | Mechanism | Usage Rule |
|---|---|---|
| **Inter-Lane Task Briefing** | `session_notify` | **Mandatory.** Delivers structured task seeds and instructions directly into a worker's context window. |
| **Receipt / Ack Delivery** | `session_notify(delivery={"mode": "quiet"})` | Queues notification silently without interrupting an active turn. |
| **Urgent Escalation** | `session_notify(delivery={"mode": "now"})` | Triggers immediate attention on critical failures. |
| **Chat Topic Posts** | `telegram_send` | **Human visibility only.** Agents do NOT read chat topics; briefing via chat does zero work. |

---

## 2. The Zero-Token Pacemaker Probe (`trigger_cmd`)

To avoid burning tokens on idle heartbeat turns, OpenCrabs crons use shell pre-flight probes:

```bash
# Example trigger_cmd in cron definition:
# 1. Checks if remote main has drifted or if unassigned issues exist
# 2. Exits 0 only if action is needed; exits non-zero (or clean) to skip agent turn
git fetch origin main && [ $(git rev-parse HEAD) != $(git rev-parse origin/main) ]
```

- **If Probe returns 0:** Session is woken up to perform triage or rebase.
- **If Probe returns $\ne 0$:** Session remains asleep. Zero tokens spent.

---

## 3. Post-Compaction Recovery Anchors

Context compaction wipes conversation history. To prevent amnesia:
1. Every profile injects an always-loaded recovery anchor pointing to the factory's `SKILL.md`.
2. The agent's mandatory first action post-compaction is to reload `SKILL.md` before executing turns or asserting status claims.
