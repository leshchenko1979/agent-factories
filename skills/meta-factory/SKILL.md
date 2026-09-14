---
name: meta-factory
description: Process law for the agent-factories meta-factory (/root/agent-factories). Load before ANY meta-factory task - surveying a member factory, deriving a template law, writing to TEMPLATE/ or docs/, scoring a factory, briefing the Delegate lane, or answering an owner question about the factory project. (/meta-factory, agent-factories, meta-factory, factory template, quality criteria)
version: 0.1.0
author: leshchenko1979
globs:
  - "/root/agent-factories/**"
  - "~/.opencrabs/profiles/*/skills/meta-factory/**"
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

**Purpose.** Two complementary purposes:
1. **The product:** Produce and maintain the factory template + rulebook, deriving laws
   that hold for every factory of a given shape.
2. **The consulting practice:** Act as a process consultant to surveyed member factories,
   diagnosing bottlenecks, surfacing stopped processes, and actively helping their HQs
   increase their operational efficiency (throughput, cadence, yield, waste reduction).

**The three legs.**

| Leg | Where it lives |
|---|---|
| Process law | this file (mirrored in this repo, which is git-tracked) |
| Chat surface | `Factories` group — topics carry state in their names |
| Issue board | `leshchenko1979/agent-factories` issues |

**The board is the intake surface** (owner ruling 2026-09-11). A finding, gap or task that
arrives anywhere — this chat, a member factory's reply, a lane's own observation — is filed
as an issue on `leshchenko1979/agent-factories`. It is not tracked in chat. Chat carries the
conversation; the board carries the work. Triage owns intake, and a closed issue carries the
receipt that resolved it.

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

This factory **converses with a member factory's HQ, or with that HQ's delegate.** It
consults, diagnoses, and recommends — it does not edit a member's repo, write its ontology,
file its issues, or run its tests. A consultant advises the leadership; they do not seize
the tools.

Doing a member's work duplicates a lane, bypasses the member's own process law, and leaves
this factory's own work undone.

**Delegation.** Member-factory conversation is delegated to a separate lane.

**This factory's own lanes.** All four are topic-bound sessions in the Factories group; the
ids below were read back from `session_bindings` on 2026-09-11 14:2xZ. A lane is addressed by
its **session id**, and that id is re-read from live state before any send — never carried
over from an earlier turn.

| Topic | `thread_id` | Lane session | Carries |
|---|---|---|---|
| HQ | 21 | `2646d31a-71ee-49f0-be81-9c8dc32d32fa` | analysis, rulings, owner conversation, repo implementation (this factory has no worker lane; its own repo is the artifact) |
| Delegate | 68 | `23549292-77ff-40d1-97e3-5aa0bdd19d74` | member-factory comms |
| Triage | 20 | `f4c192c9-a8e9-4268-9026-ee3e4970cc8a` | intake and routing |
| Surveys | 19 | `5c99ad51-8889-40cb-b589-fa13fd673c06` | survey and measurement work |

**Two of these lanes are this factory's own, not the template's** (owner ruling
2026-09-12). `delegate` and `surveys` are not roles a bootstrapped factory has: the
template ships four cards — `hq`, `triage`, `worker`, `carrier` — and no delegate card.
A lane that cannot write a state row cannot do its job, so both are declared in
`tools/actors.txt`, the extension point for a role the core set does not have. The core
set in `tools/ledger.py` is exactly the template's four cards plus `owner`; the
declaration file is what lets a factory name its own lanes without editing a file that
is copied byte-identically into every factory.

**A lane exists only once a message has arrived in its topic.** A topic's session is created
by its first **inbound** message — an outbound post never claims one. So a topic is
addressable (deliveries target its `thread_id`) but unowned until someone writes into it, and
"the lane is up" is a claim that needs a `session_bindings` read, not an assumption.

**A subagent id is not a lane.** The delegate was first dispatched as a one-shot subagent
(`subagent: delegate`), and its id was recorded here as "the Delegate lane session". It
finished, and the three member HQs' replies — six messages, 11:33Z–11:50Z — parked in its
`notify_queue` with nothing left to read them. A dispatch returned a receipt; nothing consumed
it. A subagent session has no channel binding, so it cannot be a lane.

- This lane (the HQ topic) owns analysis, rulings and owner conversation **and** repo
  implementation for this factory's own repo. It still does not do a **member** factory's
  work — the hard boundary above is unchanged.
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

The harness that this meta-factory and all surveyed factories run on is produced and managed
by the **OpenCrabs factory** (`leshchenko1979/opencrabs`, Crabs Kanban Board topic `OC DEV HQ`).
The OpenCrabs factory is simultaneously one of our surveyed member factories and the fleet's
runtime supplier. All factories act as clients to OpenCrabs: we experience runtime friction,
telemetry gaps, and scheduling bottlenecks directly, and advise OpenCrabs HQ with concrete
feature requests and instrument specifications.

| Substrate | Owner |
|---|---|
| OpenCrabs instruments (daemon, core tools, brain/skill loading) | **OpenCrabs Kanban Board HQ** — session `d72bd52d-42aa-4dbd-ac99-5b5300770019`; fork issues on `leshchenko1979/opencrabs` |
| Token provisioning, model routing, inference pricing & endpoints | **InferHub Watch HQ** — session `359fe71b-c7a1-420b-b856-acfb49939a7b`; issues on `leshchenko1979/inferhub-watch` |
| `tg_*` tools (`tg_get_chat_info`, `tg_mtproto`) | `leshchenko1979/fast-mcp-telegram` |
| `telegram_send` | **OpenCrabs core** (`src/brain/tools/telegram_send.rs`) — not fast-mcp-telegram |
| The template / skill law text in this repo | this factory's HQ |

**A defect noted in a report is a defect unfiled.** Documenting a gap is not filing it.

**Peer agreement is not verification.** A claim two lanes share is still unverified if
neither read the surface. Find the substrate's repo, read its tool list, probe the tool.

---

## 6. Measurement and self-improvement loop

This factory is scored against `docs/quality-criteria.md` — 13 criteria, 4 families, 0–4 each.

| Requirement | Detail |
|---|---|
| A scored baseline exists | `evidence/scores/<date>.md` — one file per run, committed, so drift shows as a diff |
| Re-scoring is a scheduled job | `cron_manage`, daily to start, relaxed once variance is known |
| The procedure is a pointer, never a copy | `docs/measurement-procedure.md`; the job carries the pointer |
| The score is a diff, not an impression | Committed, so drift shows as a change |
| Automated self-improvement conversion | Score regressions (score < 3 or negative deltas) are automatically converted into board issues by Triage (P1, P27) |
| Autonomous assignment & monitoring | Triage scans open intake issues, checks claims, assigns persistent worker lanes, and runs periodic execution sweeps (P27) |
| **The Pacemaker Requirement** | Every periodic process owner (Surveys, Triage, HQ) must have an active thin cron pacemaker waking its session UUID |

The surveyed factories are measured on the same cadence. A factory's **own HQ owns its
domain detail**; what travels back is the score and the template law it implies.

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
product.** A product name in a sentence stating *mechanics* is a leak — run the leak test
(`TEMPLATE/README.md`) before shipping any core law file.

Bindings are **mandatory and singular**: a factory must have a chat surface and a runtime,
and exactly one of each. Domain packs are **optional and compose**: a factory may carry
several, or none.

---

## 11. State — every surface has one writer

State that lives only in chat is not state. It is a memory of a conversation, and it
survives exactly as long as the context does. Every durable fact therefore lives in the
repo, on a surface with **one named writer**. Every other path to it is read-only.

| Surface | Holds | Authoritative writer | Everyone else |
|---|---|---|---|
| `evidence/ledger.jsonl` | every state transition — intake, claim, dispatch, close, score, ruling, run | `tools/ledger.py append` | `tail`, `verify` — read-only |
| `evidence/insights.jsonl` | empirical factory insights across growth stages | `tools/insights.py append` | `list`, `verify`, `format` — read-only |
| `evidence/rework.md` | every defect this factory produced, with its root cause and what now prevents it | `Triage`, at the close that resolved it | read-only, gated by `tests/test_rework.py` |
| `evidence/scores/<date>.md` | one measurement run, one file per run | the daily measurement job (`Surveys`) | read-only |
| `evidence/*.md` | survey receipts and dated evidence | the survey run | read-only |
| `ONTOLOGY.md` | the canonical vocabulary | `HQ` | read-only, gated by `tests/test_ontology.py` |
| `docs/processes.md` | the canonical process register | `HQ` | read-only |
| `skills/meta-factory/SKILL.md` | this law | `HQ` | read-only |

**The Law-Upholding Principle (P29):** Every codified law must be upheld by an active operational process or a deterministic mechanical gate (`tools/audit.py`). A rule without an upholding mechanism is dead text and will be removed.

**The Single Ownership Principle (P30):** Every declared process has exactly one named process owner role. Shared ownership is zero ownership.

**The actor set is the roles the law names, and it is closed.** A role that is not listed
cannot write a row, so adding one is a law change rather than a convenience. The core set
is the template's four role cards plus `owner`, who directs without being a lane; a factory
whose law names a lane beyond them declares it in `tools/actors.txt`, one role per line. It
is declared there and not in the constant because `tools/ledger.py` is copied
byte-identically into the template — a lane only one factory has cannot live in a value that
must match everywhere. This set was **wrong until 2026-09-12**: it named `delegate` and
`surveys`, which the template does not ship, and refused `worker` and `carrier`, which it
does — a gate rejecting the very roles its own template hands out. Both directions are now
probed in `tests/test_ledger.py`.

**Single-writer is a mechanism, not a habit.** The ledger has exactly one append path
because concurrent writers would each read the same last row and each write `n+1` — the
file silently gains two row 41s, and every count taken from it is wrong from then on in a
way that looks fine. `tools/ledger.py` takes an exclusive lock, computes the next row
number *inside* it, and fsyncs before releasing. `tests/test_ledger.py` runs twenty
concurrent appends and asserts the row numbers are still `1..N`: the property is tested,
not asserted.

**A row count is not an integrity check.** The ledger is read as a *sequence*: a subject
that reaches `close` must have been filed (`intake`) before it and taken (`claim`) after
that intake, and `verify` fails naming the subject and the missing leg. A ledger can be
perfectly numbered and still say that work was closed without ever saying who took it. Each
missing leg is reported independently, so one pass says everything that is absent, and the
order leg is evaluated only when both legs are present — bounded by the latest intake before
the close, so a re-opened subject must be re-claimed. The only exemptions are closes written
before the gate existed, listed explicitly by subject, leg and date in `EXEMPTIONS` inside
`tools/ledger.py`, and printed as `excused:` whenever one is used, so "clean" and "excused"
are never the same output. An exemption nobody would defend in that output is one that gets
fixed instead. Nothing is ever backfilled: an intake row written today for work filed before
the gate is a falsified record, not a repair.

**What this does not give you.** The ledger is append-only by construction — the tool has
no rewrite command — but it is still a file, and a file can be edited. That is what
version control is for: a rewrite shows up as a diff, and the history is the audit. The
guarantee is *one append path*, not *tamper-proof*.

**An append-only surface with no reader is a write-only memory.** `tools/ledger.py tail`
is the read path. When a lane's state is in question, the ledger is what it is checked
against.

**The rework log is the other half of the ledger, and it is what makes "are we getting
better?" answerable.** The ledger records that work closed; `evidence/rework.md` records
what had to be redone and why. The rubric's Stability criterion asks for two rates —
change fail rate and rework rate — and neither is computable from memory. The log is the
numerator, the ledger's `close` rows are the denominator, and both are **recomputed on
each measurement run**, never recalled: a remembered rate is an impression with a decimal
point.

Three properties make the log worth keeping, and all three are easy to lose:

- **`Prevented by` is the load-bearing column.** It is the only one that changes future
  behaviour — it is where a failure becomes a rule, a test or a gate. `nothing yet` is a
  legitimate and useful entry: it marks the defect as still live. A log whose every entry
  reads "be more careful next time" has quietly stopped working.
- **It records the process, never a person.** An entry names a mechanism that failed, not
  a lane that erred. Blame entries stop being written, and an incomplete log is worse than
  none.
- **The entries are one contiguous table.** The log is read as a table, so a blank line
  inside it splits the log into fragments and every row after the break renders with no
  header above it — a broken artifact that still parses, which is why the first version of
  the gate passed it. The gate asserts that the rows it parsed are the rows sitting under
  one header, so a re-inserted blank line fails the build.

`tests/test_rework.py` gates it: an incomplete row, a placeholder, or a fragmented table
fails the build.

**The first readings are uninformative, and that is expected.** This factory
opened with four closes against eleven rework entries — a rework share of 73%,
which is what any factory
looks like before its gates exist. The number is not alarming; it carries no signal until
the gates have had time to bite. Report it as a direction, not a verdict.

---

## 12. Boundaries

| Neighbour | Mode | What crosses |
|---|---|---|
| The four member factories | consulting | diagnostic findings, recommendations, template laws and scores; they own their own decisions and implementation |
| The operator | service | analysis, decisions framed as options |
| OpenCrabs (harness & dev factory) | client-supplier loop | runtime friction, telemetry requirements, and feature requests; daemon release builds |
| InferHub (inference & token provider / inferhub-watch) | client-supplier loop | token pricing, model availability, routing latency, prompt caching, and retry economics |
