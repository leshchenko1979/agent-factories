# Methodology Module 05: Surface Binding (Telegram Forums)

> **Core Law:** The chat surface exists for human operator supervision, decision points, and archiving. It must reflect factory state clearly using structured forum topics and rich cards.

---

## 1. Forum Topic Architecture

Each functional lane of an autonomous factory binds to a designated Telegram Forum Topic:

| Topic Name | Typical Role | Purpose & Carried State |
|---|---|---|
| **HQ** | `hq` | Architecture, strategic rulings, human operator dialogues, and repo delivery. |
| **Triage** | `triage` | Intake processing, defect triage, queue monitoring, and worker assignment. |
| **Workers / Editors** | `worker` | Active multi-turn code generation, test iteration, and task execution. |
| **Surveys / Quality** | `surveys` | Daily pacemaker audits, league tables, and consulting diagnostics. |

---

## 2. Topic Creation & Session Seeding

- A topic is created via Bot API / fast-mcp-telegram.
- **Session Seeding:** A topic's session is initialized upon the first *inbound* message. Outbound posts alone do not claim a session.
- Once bound, addressing between lanes switches exclusively to **Session UUIDs** via `session_notify`.

---

## 3. Human Visibility & Delivery Discipline

1. **Rich Markdown & Visual Flowcharts:** Use GFM tables and native vertical `mermaid` diagrams (`flowchart TD`) for reports and architecture.
2. **Prototype Rule:** Send concrete prototypes (via `telegram_send` with rich HTML or images) rather than abstract textual descriptions when discussing UX.
3. **What Now / Next Orientation:** Every operator-facing report must conclude with a concise summary: *In flight*, *Next step + Owner*, and *Blocked on Operator*.
