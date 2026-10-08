---
name: meta-factory
description: Process law for the agent-factories meta-factory (/root/agent-factories). Load before ANY meta-factory task - surveying a member factory, deriving a template law, writing to TEMPLATE/ or docs/, scoring a factory, briefing the Delegate lane, or answering an owner question about the factory project. (/meta-factory, agent-factories, meta-factory, factory template, quality criteria)
version: 0.1.53
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

**Router:** two clause sets live in sibling files, loaded on demand — `verdicts-and-claims.md`
(this file's §8) and `state.md` (its §11 clause tail). Load one before a verdict or a state row.

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

**Purpose.** To build, measure, and evolve **Autonomously Self-Improving Factories (ASIF)** across two complementary pillars:
1. **The product:** Produce and maintain the factory template + rulebook, deriving laws and mechanical gates that enable any repository to run autonomous task eval loops and closed-loop self-improvement.
2. **The consulting practice:** Act as a process consultant to surveyed member factories,
   diagnosing bottlenecks, surfacing stopped processes, and actively helping their HQs
   increase their operational efficiency (throughput, cadence, yield, waste reduction, and autonomy).

**The Core Triad of an Autonomously Self-Improving Factory:**
- **Autonomous (The Momentum):** Outer cron pacemakers (P28) wake persistent session UUIDs without token waste; inner eval loops (Ralph) converge tasks against deterministic gates with zero human prompt dependence.
- **Self-Improving (The Compound Engine):** Runtime defects are codified into `evidence/rework.md` (`Prevented by`), and score regressions automatically trigger backlog issues (P1/P27) that upgrade prompt laws and mechanical test gates permanently.
- **Factory (The Industrial Discipline):** Strict single-writer concurrency (`fcntl.flock`), atomic subprocess contracts with measurable lead times, and verifiable product delivery.

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

**A ruling that orders a mechanism gets its OWN board item.** A mechanism ordered by a ruling
is filed as its own issue on the board — never as a numbered item riding inside another issue's
dispatch. The board is the surface a patrol reads; a queue position inside a dispatch is read by
nothing, so a mechanism that exists only as a queue entry is invisible to every sweep: it reads
as undispatched, and the patrol that should carry it cannot see it at all. Its upholding
mechanism is a PROCESS (P29): before a ruling is stamped, the lane that authors it files an
issue for every mechanism the ruling orders, so each one has a subject a patrol can find.

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

**This factory's own lanes.** All five are topic-bound sessions in the Factories group; the
ids below were read back from `session_bindings` on 2026-09-18 12:20Z. A lane is addressed by
its **session id**, and that id is re-read from live state before any send — never carried
over from an earlier turn.

| Topic | `thread_id` | Lane session | Carries |
|---|---|---|---|
| HQ | 21 | `2646d31a-71ee-49f0-be81-9c8dc32d32fa` | analysis, rulings, owner conversation. Implements nothing — kept idle for incoming managerial work |
| Worker | 1271 | `dcd8f7a9-c1e7-48c3-b184-d901dc08eac7` | repo implementation for this factory's own repo — the lane HQ delegates work items to |
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

- This lane (the HQ topic) owns analysis, rulings and owner conversation. It implements
  **nothing** — repo work for this factory's own repo goes to the **Worker** lane, so HQ
  stays idle for the incoming managerial work that is its job (owner order 2026-09-18).
  It still does not do a **member** factory's work — the hard boundary above is unchanged.
- The **Worker** lane is the implementation destination: `session_notify` its UUID with the
  issue number, the goal and the done-criteria. A work item with no lane to take it is a
  missing lane, not an item HQ picks up.
- Member traffic goes to the **Delegate** lane, never into the HQ topic.
- A topic post is **owner visibility only** — agents do not read topics. Briefing the
  delegate means `session_notify` to its UUID; a topic post does zero work for it.

---

## 4. Briefing and dispatch

**An agent is briefed by a direct message to its own session UUID — never by a post in the
chat.** The chat exists for the operator to observe and archive.

**A NOTIFICATION MUST CARRY A STATE CHANGE OR AN ASK — a bare acknowledgment is neither, and is
NOT SENT (owner order 2026-10-03: *"Which of the notifications you receive are useless? Issue a
law not to send them."*).** The class has been ordered against twice before and both orders were
SCOPED — the ledger-as-ACK-channel order of 2026-09-11 (freeze waves) and the zero-ACK dispatch
order of 2026-09-13 (task & harvest dispatches) — so the general form is stated here:

- a **STATE CHANGE** — a fact the recipient cannot read from a surface it already reads. The
  ledger, the board and the recipient's own session are surfaces it already reads, so *"I stamped
  `n=X`"*, *"the row is closed"*, *"the law has LANDED"* are **not** state changes: they are
  re-reads of a surface the recipient can open itself.
- an **ASK** — an action requested of the recipient, carrying what it needs to act.

**The sender's test, before pressing send:** name the state the recipient lacks, or the action
you are asking of it. If you can name neither, write the ledger row and stop. The receipt for a
dispatch, a wave, a freeze or a law-change is the **ledger row**, never a reply: the sender reads
acks in one `tools/ledger.py tail` call and counts them. A conversational receipt — *"received",
"ack", "starting now", "confirmed", "nothing owed"* — spends the sender's tokens, interrupts a
working lane, and puts a second surface beside a fact the first already holds. **No gate upholds
this and that is stated, not implied** — a notify body lives in no tree the offline suite reads
(§8) — so what upholds it is this text and the sender's own test. Nothing is backfilled: the law
governs what is sent from here, and it does not narrow the notifies that DO earn their interrupt,
because a dispatch, a return leg, a correction, a finding or an ask carries a state change or an
ask by construction.

**A dispatch notify names the unit it routes in its opening non-blank line.** The patrol reads
the delivery's header — `DELIVERY_HEADER_LINES = 1` in `tools/patrol_host_state.py` — to learn
which unit a notify is about, so a dispatch that names its subject only in the body is invisible
to the leg that checks it: the reader keys on the one line a delivery DECLARES itself on, and it
is deliberately NOT widened (#433). Writer-side twin of #433.

Before dispatching work to any lane, check it is not already claimed.

Work goes **sender → owner of the resource**, directly. No relay hops.

**The intake leg is dispatched at FILING time, never last.** Filing a board item is a sequence
with four legs — the board issue, the ledger intake row, the claim, and the dispatch to the lane
that implements it. Intake is **Triage's** leg, so filing a board item owes Triage a dispatch in
the **same turn** as the filing. **The row is stamped by the FILER, in the same turn as the filing, WHERE THE FILER IS AUTHORIZED for the `intake` event — the role-to-event matrix `AUTHORIZED_ACTORS_BY_EVENT` (`tools/ledger_declaration.py`); a filer the matrix does not authorize for `intake` cannot stamp it, because the write path derives the actor from `OPENCRABS_SESSION_ID` and refuses a mismatch, so it dispatches the intake role in the same turn and the intake role stamps the row at that boundary. Triage owns the leg's ORDERING and receives the dispatch.** Filed last, the intake row
lands after the claim, and
`tests/test_board_intake_recorded.py` **fails on a numeric subject carrying a `claim` or a
`close` with no intake row of its own**.

**A CLAIM THAT PRECEDES ITS INTAKE IS ACCEPTED, AND THE RE-CLAIM IS THE DESIGNED OUTCOME OF A
WAKE-LATENCY GAP (2026-09-25, superseding the refusal clause).** The ledger's order leg was
PRECEDENCE — it refused a close whose claim preceded its intake. That clause is RETIRED: the two
rows are written by **two lanes** whose wake latencies are independent, so the inversion is a
**derived** outcome of that race — neither lane controls the other's wake latency, so it is not
an error by either. Measured before retiring it: **6
instances across 3 factories**, and on #161 the claim still preceded the intake by **1m46s** even
though the filing lane dispatched Triage in the **same turn** as the filing — the implementer was
idle and woke in 10s while Triage was mid-turn. What the leg keeps is **PRESENCE**: a close must
have both legs somewhere before it, read positionally, which is the `#137` shape that sat silent
for 35 hours. Presence is checkable without asking a lane to control another lane's timing;
precedence is not. So when the inversion happens, the remedy is a **fresh re-claim** by the lane
that took the work — mechanical, and bought with a dispatch that cost nothing to send on time.
Precedent: n=191 filed and dispatched intake in one breath. Origin: #113, whose intake leg went
last (n=675, after the claim at n=673); #114 is the first item filed under this clause.

**The offline leg's population is narrower than "ledger activity", and by design.**
A subject whose only rows are a `ruling` or a `dispatch` is **outside** the offline leg's
population — not a defect it missed. Under the filing-time ordering above that window is
NORMAL: HQ stamps the ruling and the dispatches before the intake row exists, so a gate
widened to every event would fire RED on the designed sequence. The offline leg judges only
subjects carrying a `claim` or a `close`, and prints that population beside its verdict, so
its green reads as "examined N, 0 problems" rather than being indistinguishable from
"examined nothing" (#116). A **board item with no intake row** — the other half of the same
window — is the **board** leg's concern, owned by the host runner `tools/patrol_host_state.py`,
which reads the board whole and is the authority on that direction.

**Name your paths at the commit, not only at the stage.** This tree is shared, and a bare
`git commit` takes the **entire index**, including every peer's staged work — so a commit
written for two paths can land carrying a dozen, and one lane's commit becomes the transport for
another lane's unreviewed work. Use `git commit -m <msg> -- <paths>`, or stage and commit in a
single invocation. The staging rule alone is satisfiable in full while this fires: it governs the
*staging* step, and the hazard lives in the *commit* step. Origin: #47, recurred on this lane
2026-09-20 when a bare commit carried a peer's staged registry-gate fix into a law commit.

**The shared tree is a READ surface; work happens in a worktree.** The tree every lane can
see is for READING — `git log`, `grep`, `sed`, the ledger's own bytes. A change is made in a
worktree checked out at `origin/main`, and a lane that edits the shared tree in place races
every peer who does the same, so its result is not a revision anyone chose. Origin: #241,
ruled 2026-09-29 (n=1696) — the patrol's board legs read a shared tree another lane was
mid-write on, and the fork produced FALSE VERDICTS: no single location gave a wholly correct
read. NOT ruled: that the shared tree must be reconciled first — the remedy is the discipline
above, plus the patrol's cheap rider that prints the blocking paths and the read instant, and
prints NOT RUN with its reason when the tree cannot be read.

---

## 5. Substrate routing — a defect goes to the repo that must change

When an instrument is inadequate, name **the repository that carries the code**, not the
tool that surfaced the defect, and dispatch in the same turn it is found.

The harness that this meta-factory and all surveyed factories run on is produced and managed
by the **OpenCrabs factory** (Crabs Kanban Board topic `OC DEV HQ`), which works from the source
fork `leshchenko1979/opencrabs` and files on **two trackers**: a **BINARY** defect (runtime behaviour,
channels, providers, TUI, memory, tools) on `opencrabs/opencrabs`, and a **FACTORY** defect (tooling,
CI, release automation, process) on `leshchenko1979/opencrabs-dev-factory` — the portfolio
`leshchenko1979/opencrabs` is **READ-ONLY**, never an issue home (owner order 2026-10-03 21:17Z).
The OpenCrabs factory is simultaneously one of our surveyed member factories and the fleet's
runtime supplier. All factories act as clients to OpenCrabs: we experience runtime friction,
telemetry gaps, and scheduling bottlenecks directly, and advise OpenCrabs HQ with concrete
feature requests and instrument specifications.

| Substrate | Owner |
|---|---|
| OpenCrabs instruments (daemon, core tools, brain/skill loading) | **OpenCrabs Kanban Board HQ** — lane `opencrabs-dev` / `hq`, topic `OC DEV HQ` (thread 30220), resolved live at dispatch; **binary** issues on `opencrabs/opencrabs`, **factory** issues on `leshchenko1979/opencrabs-dev-factory`, and the portfolio `leshchenko1979/opencrabs` READ-ONLY |
| Token provisioning, model routing, inference pricing & endpoints | **InferHub Watch HQ** — lane `inferhub-watch` / `hq`, topic `InferHub Watch: Fallback Publisher Diversity & Predictors` (thread 2), resolved live at dispatch; issues on `leshchenko1979/inferhub-watch` |
| `tg_*` tools (`tg_get_chat_info`, `tg_mtproto`) | `leshchenko1979/fast-mcp-telegram` |
| `telegram_send` | **OpenCrabs core** (`src/brain/tools/telegram_send.rs`) — not fast-mcp-telegram |
| The template / skill law text in this repo | this factory's HQ |

**These rows name a LANE, never a session.** The session that owns a topic is the newest
binding within its own profile, so the session is resolved live at dispatch — `python3
tools/registry.py resolve` — and a raw uuid written here would be a value that rots the moment
the topic is re-opened, leaving a reader who follows it reaching nobody (#254, ledger n=1810).
`tests/test_law_no_raw_session_uuid.py` holds the shape: no raw uuid in a law file, except
where the debt is declared in `docs/law-uuid-exemptions.json` and printed on every run.

**A defect noted in a report is a defect unfiled.** Documenting a gap is not filing it.

**Peer agreement is not verification.** A claim two lanes share is still unverified if
neither read the surface. Find the substrate's repo, read its tool list, probe the tool.

---

## 6. Measurement and self-improvement loop

This factory is scored against `docs/quality-criteria.md` — 19 criteria across 6 families, 0–4 each.

| Requirement | Detail |
|---|---|
| A scored baseline exists | `evidence/scores/<date>.md` — one file per run, committed, so drift shows as a diff |
| Re-scoring is a scheduled job | `cron_manage`, daily to start, relaxed once variance is known |
| The procedure is a pointer, never a copy | `docs/measurement-procedure.md`; the job carries the pointer |
| The score is a diff, not an impression | Committed, so drift shows as a change |
| Automated self-improvement conversion | Score regressions (score < 3 or negative deltas) are automatically converted into board issues by Triage (P1, P27) |
| Autonomous assignment & monitoring | Triage scans open intake issues, checks claims, assigns persistent worker lanes, and runs periodic execution sweeps (P27) |
| **The Pacemaker Requirement** | Every periodic process owner (Surveys, Triage, HQ) must have an active thin cron pacemaker waking its session UUID |
| **The Subject Matter Consulting Gate** | Substantive consulting & diagnostic audits strictly require baseline Subject Matter Documentation (`docs/subject/` >= 2/4) |

**An attribution is dated by a CONTENT WALK, never by a pickaxe.** `git log -S <string>`
counts OCCURRENCES, not changes, so it cannot date a line-level change: a value swap
(`0.1.0 → 0.1.1`) leaves the count unchanged and is invisible to it, and a reflow that
re-adds an already-present line moves the count and reads as the introduction. Both produce
a confident, wrong attribution — and the attribution is the whole value of a rework entry,
because it names which change a reader must guard against. A rework entry's attribution is
therefore produced by a **content walk** over the commits touching the file — bisecting the
occurrence count, or testing the line's presence at each step — and **never** by
`git log -S` alone; a pickaxe result is a hypothesis about where a string appeared, not a
finding about where a change happened.

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

**This section's clauses live in `verdicts-and-claims.md`, beside this file** — load it before
any verdict, receipt, citation or canonicality claim. The heading stays here so the section
number and the clause title remain reachable from this file.

---

## 9. After a context compaction

The law lives in message history, and compaction clears it.

The runtime warns the session when context consumption approaches the compaction threshold. That warning is a **deterministic boundary signal**, and it defines a two-sided protocol:

> **On the pre-compaction warning:** flush in-flight state into durable substrates — un-persisted
> intermediate variables into `session_context`, every remaining step and acceptance criterion
> into the `plan` card. In-context instructions do not survive compaction; only what is written
> to an always-injected file or a durable substrate does.

> **Context-Manifest Curation (Section 10 Standard):** In the compaction prompt manifest, explicitly
> curate `active_skills` (retaining this skill), `discard_skills` (discarding inactive sibling roles),
> and `required_tools` (pre-activating `session_notify`, `session_search`, `bash`, `read_file`, `edit_file`, `write_file`)
> to guarantee >93% retention post-compaction.

> **First action after any compaction, before any ruling, dispatch or status claim:
> reload this skill, then re-anchor the task contract from disk with `plan(operation="show_plan")`.**

The shared brain file carries a one-line pointer here for exactly this reason. Mechanics: `docs/methodology/04-harness-binding.md` §5–9.

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
survives exactly as long as the context does. Every durable fact therefore lives on a
surface with **one named writer** — in the repo, or in the one surface this factory keeps
outside it, the issue board. Every other path to it is read-only.

**An instrument's own law lives in its own file, and this section keeps what is THIS factory's.** The contract for an instrument — its verbs, store path, gates and closure — ships as a doc pair (`docs/instruments/<instrument>.md` + `TEMPLATE/docs/instruments/<instrument>.md`) and reloads into this skill through a relative symlink (`skills/meta-factory/<instrument>.md`), so the law survives a compaction without a second copy in this file. What stays here is the surface table below and its one-writer rule. The process law that binds a lane writing to one of these surfaces lives in `state.md`, beside this file. Where a clause in `state.md` restates an instrument's own contract, the shipped doc is the **delivery** home and this file is the **authority** — a member reads the doc, never a citation into this file (the §8 split, exercised in §9).

**The workspace-hygiene instrument.** A factory audits and reaps its own workspace on a declared cadence, telling a lane's work IN FLIGHT from work STRANDED by age, so a busy factory never reads DEGRADED and genuine litter is still caught. Its law is `docs/instruments/hygiene.md` (shipped pair `TEMPLATE/docs/instruments/hygiene.md`), reloaded through the `skills/meta-factory/hygiene.md` symlink; it upholds **Process 4 — Workspace Hygiene Sweep** (`docs/processes.md`).

| Surface | Holds | Authoritative writer | Everyone else |
|---|---|---|---|
| the issue board (`leshchenko1979/agent-factories` issues) | the work itself — intake, state, and the receipt that resolved it | the lane that files or settles the item (`Triage` owns intake) | read-only, via `gh` |
| `evidence/ledger.jsonl` | every state transition — intake, claim, dispatch, close, score, ruling, run | `tools/ledger.py append` | `tail`, `verify` — read-only; law: `docs/instruments/ledger.md` |
| `evidence/subprocesses/*.jsonl` | granular domain-specific subprocess event streams | `tools/ledger.py append --subprocess` | `tail`, `verify` — read-only |
| `evidence/insights.jsonl` | empirical factory insights across growth stages | `tools/insights.py` — the ONE writer; every write verb it exposes is the SAME writer, never a second one | `list`, `verify`, `format` — read-only |
| `evidence/.ledger-index.sqlite` | the derived, disposable search index over the ledgers — a **cache, never a source of truth** | `tools/ledger-index.py build` | `find`, `subject`, `touching` — read-only; deletable at any instant, and STALE is not a defect |
| `evidence/publish-receipt.json` | the pusher's record of its OWN last push — `{sha, instant, remote, branch}` (issue #284); **LOCAL and gitignored, by design** | `tools/publish.py` — the pusher's own write, read through its `read_receipt` | read-only; never a ledger row — the pusher is not a lane and the ledger's actor set is closed |
| `evidence/rework.md` | the rework entries this factory has **recorded** — each defect, regression and law rollback it wrote down, with its root cause and what now prevents it | the lane that HOLDS the defect: the declaring lane where a close declared the entry, the discovering lane where a patrol or survey found it | read-only; `tests/test_rework.py` gates each entry's completeness, the `Subject` column's vocabulary, the table's contiguity, every rate claim's form, and that every determinate `Subject` resolves to a real closed work unit (each unresolvable one reported by name); the share of closes DECLARING a rework disposition is PRINTED, never gated — never the completeness of the set |
| `evidence/scores/<date>.md` | one measurement run, one file per run | the daily measurement job (`Surveys`) | read-only |
| `evidence/*.md` | survey receipts and dated evidence | the survey run | read-only |
| `ONTOLOGY.md` | the canonical vocabulary | `HQ` | read-only, gated by `tests/test_ontology.py` |
| `docs/processes.md` | the canonical process register | `HQ` | read-only |
| `skills/meta-factory/*.md` | this law and its two clause files (`verdicts-and-claims.md`, `state.md`) | `HQ` | read-only |
| the questions register (profile home, outside this repo) | the open questions lanes have DECLARED, one standing set per factory key | the `oc-questions` tool | read-only; the rendered page is served from `vpn` behind basic auth; law: `docs/instruments/open-questions.md` |
| `registry/fleet.json` and `registry/factories/<slug>.json` | what each factory IS in a form a peer can read — its chat, its lanes, the substrates it owns, the cron prefixes it claims | `HQ` (the fleet manifest) and the lane that enrolls (`tools/registry.py enroll`) | read-only, via `tools/registry.py resolve` |
| `docs/factory-registry.md` and `registry/index.json` | the generated half — the same facts rendered for a reader, plus the reachability route | `tools/registry.py render` | read-only; `tests/test_registry.py` fails a committed render that no longer reproduces over its state-bearing bytes |
| `registry/gates.json` | the per-gate time budgets and the **default's derivation** — every declared value is `budget_sec = margin_x x measured_sec`, and the default is `margin_x x the largest measured runtime among the UNDECLARED population` (the registered gates with no entry), re-derived whenever that population changes | the measurement duty (`Surveys`), on the same derivation rule the budget values follow — **except the DEFAULT's VALUE, which is a policy choice about what the suite does with a gate nobody has measured, and is `HQ`'s** (n=574 PART 5) | read-only; `tools/gate_budget.py` REFUSES a stated derivation its own numbers contradict, and `tests/test_gate_registration.py` asserts the live one holds and bites on a synthetic manifest that violates it |

**Authorship is not transcription.** The writer named above decides what a surface
*says*; applying a correction already decided is **transcription**, and transcription is
work — it goes to the implementation lane. So `ONTOLOGY.md`, `docs/processes.md` and this
file have one author of their *content* (`HQ`) and may be *edited* by the `Worker` lane
whenever the change is already decided. Without this split the table contradicts the
idle-HQ law above: a lane that owns a surface's content would also be its only permitted
typist, which is precisely the queue that law exists to keep `HQ` out of. The writer still
gates the result — the lane applies the correction, and the writer verifies it landed
before the item closes. Deciding content is never delegated; typing a decision is never
`HQ`'s.

**A figure DERIVED from the surface it sits on is not authored content either.** A figure
computed from that surface's own rows, with no input from any other surface, carries no
content decision to delegate — its value is a measurement and its definition lives in the
gate that computes it — so recomputing it is TRANSCRIPTION under the clause above, and the
commit that INVALIDATES it updates it IN THE SAME COMMIT, whichever lane makes that commit.
The writer still gates the result. This clause is scoped to DERIVED figures and nothing
else: it does not touch the RATE figures, which are ledger-owned and are not restated at
all, it does not move the duty to add an entry, and it does not make any lane the writer of
another lane's surface. The live instance is the coverage claim in `evidence/rework.md`'s
`## Rates` — a property of that file alone, measured by `tools/audit.py` and asserted by
`tests/test_rework.py`, which moves whenever any lane adds an entry, so the lane that
breaks it is NOT the lane that owns the surface (#51, ruling n=329).


**The rest of this section's clauses live in `state.md`, beside this file** — load it before
writing any state row or touching a surface's writer. The table and the authorship split
above stay here, beside the clauses they qualify.


---

## 12. Autonomous incident remediation & template self-healing (P30)

When an incident, regression, or defect report from any factory identifies an ambiguity,
missing instruction, or absent mechanical gate in the template or process law:

1. **Do NOT pause, narrate, wait for a prompt, or ask for operator approval.**
2. **In the same turn:**
   - Patch `TEMPLATE/` directly (e.g. `BOOTSTRAP.md`, `roles/`, `SKILL.md.tmpl`) to close the gap.
   - Add or sharpen the mechanical verification gate in `TEMPLATE/tools/` or `TEMPLATE/tests/`.
   - Record the defect, root cause, resolution, and `Prevented by` gate in `evidence/rework.md`.
   - Stamp `evidence/ledger.jsonl`, run `tools/ledger.py verify`, and commit/push to `origin/main`.
3. **Report the shipped remediation directly in the completion summary.**


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

## 13. The agent failure taxonomy — one pointer, no copy

Four orthogonal failure families, each with its own generative mechanism and its own substrate
counter. The canonical statement lives in `docs/methodology/01-llm-weakness-counters.md`; this
section is a pointer, never a second copy.

| Family | Generative mechanism | Substrate counter |
|---|---|---|
| **Epistemic** (true hallucination) | Probabilistic generation ungrounded in facts | Deterministic exit codes and same-turn receipts — no receipt, no verdict |
| **Context-capacity** (attention dispersion, compaction amnesia) | Attention dilution over large windows; lossy history summarization | Pre-compaction flush into `session_context` + `plan` card; `plan(show_plan)` after compaction |
| **Behavioral bias** (chat reflex, premature yield) | Conversational fine-tuning rewarding politeness over convergence | `GoalManager` (`set_goal`) and outer cron pacemakers driving the Ralph loop |
| **Operational friction** (scope creep, tool thrashing) | Unbounded search depth and cascading errors | Single-entry single-exit atomic subprocesses; Jidoka stop-on-defect |

The point of the split: each family takes a *different* remedy. Treating a capacity failure as
an epistemic one produces prompt-bloat that cannot work.

---

## 14. Boundaries

| Neighbour | Mode | What crosses |
|---|---|---|
| The four member factories | consulting | diagnostic findings, recommendations, template laws and scores; they own their own decisions and implementation |
| The operator | service | analysis, decisions framed as options |
| OpenCrabs (harness & dev factory) | client-supplier loop | runtime friction, telemetry requirements, and feature requests; daemon release builds |
| InferHub (inference & token provider / inferhub-watch) | client-supplier loop | token pricing, model availability, routing latency, prompt caching, and retry economics |
