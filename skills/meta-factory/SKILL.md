---
name: meta-factory
description: Process law for the agent-factories meta-factory (/root/agent-factories). Load before ANY meta-factory task - surveying a member factory, deriving a template law, writing to TEMPLATE/ or docs/, scoring a factory, briefing the Delegate lane, or answering an owner question about the factory project. (/meta-factory, agent-factories, meta-factory, factory template, quality criteria)
version: 0.1.0
author: leshchenko1979
---

# meta-factory — process law

**Owns:** how the meta-factory runs — scope, boundaries, delegation, measurement, and the
owner surface. The template and the derived laws live in this repo; this file owns the
*process* of producing them.

**Repo:** `/root/agent-factories` · **Chat:** `Factories` (forum) · **Surface:** `surface/telegram-forums` · **Harness:** `harness/opencrabs`

---

## 0. Why this file exists

The ops-profile brain files (`AGENTS.md`, `MEMORY.md`, …) are **shared** — every session and
factory running on this OpenCrabs instance reads them. A rule written there binds everyone.

Therefore: **rules specific to this factory live in this file, not in the shared brain.**
The shared `AGENTS.md` carries a one-line pointer here and nothing more.

Corollary — the same applies to every factory bootstrapped from this template: *your* rules
go in *your* skill, in *your* repo. See `TEMPLATE/SKILL.md.tmpl` §17.

---

## 1. What this factory is

**Purpose.** Produce and maintain the factory template + rulebook, and survey the member
factories to derive laws that hold for every factory of a given shape.

**The three legs.**

| Leg | Where it lives |
|---|---|
| Process law | this file (mirrored in this repo, which is git-tracked) |
| Chat surface | `Factories` group — topics carry state in their names |
| Issue board | `leshchenko1979/agent-factories` issues |

---

## 2. Scope — the boundary law

**This factory tracks effectiveness and health, never project peculiarities.**

What travels up is the *machine*: does the factory's process hold, is its law fresh, is its
state single-writer, does it survive the founder leaving. The member's own product
decisions, backlog, clients and code are **that factory's HQ's concern**.

| In scope | Out of scope |
|---|---|
| How well a factory's process works | What the factory is building |
| Template laws that generalise | One project's architecture choices |
| Scores, drift, gaps in the machine | A member's backlog items |

When a question drifts into a member's domain, say so plainly and route it to that member's
HQ. Do not answer it here.

---

## 3. The hard boundary — never do a member's work

This factory **converses with a member factory's HQ, or with that HQ's delegate.** It does
not edit a member's repo, write its ontology, file its issues, or run its tests.

Doing a member's work duplicates a lane, bypasses the member's own process law, and leaves
this factory's own work undone.

**Delegation.** Member-factory conversation is delegated to a separate lane:

| Thing | Value |
|---|---|
| Delegate lane session | `f5a2d0fd-03e8-4366-a659-7a736b774f17` |
| Delegate topic | `thread_id` 68 in the Factories group |
| HQ topic | `thread_id` 21 |

- This lane (the HQ topic) is for **analysis and owner conversation only**.
- Member traffic goes to the **Delegate** lane, never into the HQ topic.
- A topic post is **owner visibility only** — agents do not read topics. Briefing the
  delegate means `session_notify` to its UUID; a topic post does zero work for it.

---

## 4. Briefing and dispatch

**An agent is briefed by a direct message to its own session UUID — never by a post in the
chat.** The chat exists for the operator to observe and archive.

Before dispatching work to any lane, check it is not already claimed.

Work goes **sender → owner of the resource**, directly. No relay hops.

---

## 5. Substrate routing — a defect goes to the repo that must change

When an instrument is inadequate, name **the repository that carries the code**, not the
tool that surfaced the defect, and dispatch in the same turn it is found.

| Substrate | Owner |
|---|---|
| OpenCrabs instruments (daemon, core tools, brain/skill loading) | **OpenCrabs Kanban Board HQ** — session `d72bd52d-42aa-4dbd-ac99-5b5300770019`; fork issues on `leshchenko1979/opencrabs` |
| `tg_*` tools (`tg_get_chat_info`, `tg_mtproto`) | `leshchenko1979/fast-mcp-telegram` |
| `telegram_send` | **OpenCrabs core** (`src/brain/tools/telegram_send.rs`) — not fast-mcp-telegram |
| The template / skill law text in this repo | this factory's HQ |

**A defect noted in a report is a defect unfiled.** Documenting a gap is not filing it.

**Peer agreement is not verification.** A claim two lanes share is still unverified if
neither read the surface. Find the substrate's repo, read its tool list, probe the tool.

---

## 6. Measurement

This factory is scored against `docs/quality-criteria.md` — 13 criteria, 4 families, 0–4 each.

| Requirement | Detail |
|---|---|
| A scored baseline exists | Recorded in this repo, with the date |
| Re-scoring is a scheduled job | `cron_manage`, daily to start, relaxed once variance is known |
| The procedure is a pointer, never a copy | `docs/measurement-procedure.md`; the job carries the pointer |
| The score is a diff, not an impression | Committed, so drift shows as a change |

The surveyed factories are measured on the same cadence. A factory's **own HQ owns its
domain detail**; what travels back is the score and the template law it implies.

---

## 7. Reporting language

Reports to the operator are **plain language**. Every criterion, rule and role has a plain
name; that name is what a report uses. Internal codes are handles for cross-referencing
inside the law, not a vocabulary to speak in.

Test: replace every code with its plain name. If a sentence stops making sense, it was
leaning on shared memory rather than on what it said.

---

## 8. Verdicts and claims

- **Verdict verbs need a receipt.** "Green", "passing", "verified", "shipped" only with the
  same-turn tool output that shows it.
- **Identifiers are never hand-assembled.** Copy the full value from live output.
- **No claim without a check.** Existence, absence and status all require a tool call in the
  same turn. "I have not verified" is acceptable; a confident guess is not.
- **Verification is scoped by load-bearing.** Verify what you will act on or report; accept
  receipted facts you will not. In a cross-lane pass, the value is the **contradiction** check.

---

## 9. After a context compaction

The law lives in message history, and compaction clears it.

> **First action after any compaction, before any ruling, dispatch or status claim:
> reload this skill.**

The shared brain file carries a one-line pointer here for exactly this reason.

---

## 10. Add-ons in force

| Class | Pack | Why |
|---|---|---|
| Binding | `surface/telegram-forums` | the chat surface |
| Binding | `harness/opencrabs` | the agent runtime |
| Domain | `domain/watch` | surveying the member factories |

**This law states requirements. A binding states the mechanics that satisfy them on one
product.** A product name in a sentence stating *mechanics* is a leak — move it to the binding.

---

## 11. Boundaries

| Neighbour | Mode | What crosses |
|---|---|---|
| The four member factories | facilitation | template laws and scores; they own their own results |
| The operator | service | analysis, decisions framed as options |
| OpenCrabs (the harness) | collaboration | harness defects and instrument requests |
