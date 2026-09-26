---
name: meta-factory
description: Process law for the agent-factories meta-factory (/root/agent-factories). Load before ANY meta-factory task - surveying a member factory, deriving a template law, writing to TEMPLATE/ or docs/, scoring a factory, briefing the Delegate lane, or answering an owner question about the factory project. (/meta-factory, agent-factories, meta-factory, factory template, quality criteria)
version: 0.1.27
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

Before dispatching work to any lane, check it is not already claimed.

Work goes **sender → owner of the resource**, directly. No relay hops.

**The intake leg is dispatched at FILING time, never last.** Filing a board item is a sequence
with four legs — the board issue, the ledger intake row, the claim, and the dispatch to the lane
that implements it. Intake is **Triage's** row, so filing a board item owes Triage a dispatch in
the **same turn** as the filing. Filed last, the intake row lands after the claim, and
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

- **Verdict verbs need a receipt — and the receipt must name the revision it measured.**
  "Green", "passing", "verified", "shipped" only with the same-turn tool output that shows
  it, and a receipt about a TREE must name the revision it describes: a gate count or a row
  count is true of the tree that produced it and unverifiable without the sha (issue #63).
- **Identifiers are never hand-assembled.** Copy the full value from live output.
- **No claim without a check.** Existence, absence and status all require a tool call in the
  same turn. "I have not verified" is acceptable; a confident guess is not.
- **A blocker a lane reports is CLAIMED STATE, and a plan's state is read from the plan — never
  from the lane's memory of it.** "Blocked on your approval", "awaiting `/execute`", "the card is
  pending" are status claims about a live session plan, so they carry the obligation the clause
  above puts on every other existence and status claim: a same-turn read of LIVE plan state, not
  a recollection that a plan was opened. A completed plan is ARCHIVED — its card reads completed
  and there is nothing left to approve — so a stale blocker sends the reader to a card that no
  longer exists, and whoever acts on it pays the cost. Measured 2026-09-23: a lane reported two
  workstreams as queued "behind your `/execute` on the plan card" eight hours after that plan had
  completed and been archived, and the owner went looking for a card that was gone. **The failure
  was DETECTED and not acted on** — the message carried the daemon's own phantom-blocked marker
  and nobody read it — which is the second half of the rule: a self-heal marker is a receipt, and
  a receipt nobody reads is not a check. **Approval routing is PER-SESSION:** `/execute` typed in
  one topic approves that topic's session plan and no other, so a lane asking for approval names
  WHERE the card lives, not merely that it exists.
- **A criterion is a claim too, and it is AUTHORED long before it is judged.** A plan
  acceptance criterion that names a path, a gate or a file asserts that the artefact RESOLVES,
  so the check the clause above requires is due **when the criterion is written** — not at
  completion, and not by whoever executes it days later. Resolve every name as you write it;
  where the artefact does not exist, name the MECHANISM by the behaviour you will observe
  rather than a filename that merely reads plausible. A name assembled from its neighbours is
  the same fabrication as a guessed sha, and it survives longer because **nothing runs a
  plan**: measured 2026-09-21, a Worker plan task carried as its third acceptance criterion a
  command naming a test file that exists under **no revision**. The name was assembled from
  the two real artefacts beside it — the ledger-invariants JSON and the ledger-boundary
  helper — which is exactly what made it read plausible rather than wrong. It stood for
  three days, and a patrol's report caught it, not a mechanical check. **No gate can uphold
  this and that is stated, not implied** — a session plan lives outside every tree the
  offline suite reads — so what upholds it is the process: the authoring lane resolves each
  name, and the lane that meets a criterion naming an absent artefact reports it and never
  silently re-words it (a judged acceptance is a record, and rewriting one is a backfill).
- **A citation is resolvable by a reader who holds ONLY this document.** A reference to
  tracked work carries its NUMBER, taken in full from the read that returned it; a reference
  to another document NAMES that document; a bare section number resolves only inside the file
  that holds it — which is precisely the reader an agent usually is: after a compaction, in
  another session, or in another factory. The mechanism is structural, not stylistic, so this is
  the citation half of the two bullets above: a numberless "see above" is unreadable to anyone
  who reached the law without the surrounding conversation, and it reads as knowledge while
  carrying none. Filed by the owner as `#135` half 2 on his own stated basis — a correlation
  observed in one factory, which he labelled a stated correlation rather than a measured chain —
  and MEASURED before it was written, in the direction that matters: this file's four section
  references are ALL compliant (three name their document, one is a same-file reference), so the
  clause is PREVENTIVE here rather than corrective, and it is stated that way rather than
  claiming a defect this tree does not carry.
- **Verification is scoped by load-bearing.** Verify what you will act on or report; accept
  receipted facts you will not. In a cross-lane pass, the value is the **contradiction** check.
- **An attribution names an ABSOLUTE sha, never a relative revision.** The receipt rule above
  governs RECEIPTS; this governs INVESTIGATION, which a probe that writes no receipt never
  reaches. `HEAD~1` means *the parent of whatever HEAD is when the probe runs*, so in a shared
  worktree where other lanes commit concurrently the revision it resolves is not the revision
  the author meant, and the verdict describes a commit nobody chose. Measured 2026-09-19: a
  stash-then-checkout probe read a `docs/` drift as PRE-EXISTING because a peer lane's commit
  landed between the stash and the checkout, so `HEAD~1` was this lane's OWN commit rather than
  its parent; the drift was attributed correctly only by reading both blobs at the NAMED
  commits. A claim about which commit introduced a change is established by reading that
  commit's own blob (`git show <sha>:<path>`), never by a relative revision, and a probe that
  must compare before and after resolves both sides to named commits. The same binds the
  RECORD: an `evidence/rework.md` entry that cites a relative-revision form must name the
  resolved absolute sha, upheld by `tests/test_rework_relative_revision.py` (#86, ruling n=558).
- **A message addressed to one factory cites only facts measured on THAT factory.** A
  per-factory report is a claim about a NAMED tree, so a figure, a file identity or a property
  measured on factory A and written into factory B's message is FALSE ABOUT B however true it
  was about A — and it is the half a reader cannot catch, because the sentence reads exactly
  like the true ones beside it. Measured 2026-09-25, TWICE inside one hour in the kit-drift
  round: miidas's byte-identical file was named to inferhub-watch, and infra-factory's
  stdlib-only `ledger.py` was asserted OF inferhub's, whose `ledger.py` imports the
  three-module closure at `:72`/`:82`/`:94`. Both were hand-composed from a pool of five
  replies, while the DISPATCH bodies — generated from each factory's own measured data —
  carried neither error, which is the whole finding. The form that prevents it: a per-factory
  body is BUILT FROM that factory's own reply, and every factual claim in it is traceable to
  that reply — a fact belonging to another factory NAMES that factory or is not written. No
  gate can uphold this and that is stated, not implied: a notify body lives in no tree the
  offline suite reads, so what upholds it is the build form and the reader.
- **A close row's trailer is DECLARED, never supplied.** The canonical close trailer is the
  run of `key=value` tokens at the end of a `close` row's `detail`. `tools/ledger.py` supplies
  only measurements it genuinely took (`cost_usd=`, `tokens_in=`, `tokens_out=`, `turns=`,
  `duration=`) — taking a number is not a judgement. Every VERDICT in the trailer is the
  author's, and the tool must never write one: it once appended `outcome=accepted` and
  `gate=all-pass` for silence, so both headline rates could only ever report success (#53,
  ruling n=333 clause 1). `rework=` joins that trailer on the same law — `rework=#N` names the
  rework entry the close produced, `rework=none` states it produced none, and either is
  legitimate only when the AUTHOR states it. ABSENCE stays `unstated`, never read as `none`:
  an unrecorded verdict is UNKNOWN, never a value (#53 clause 2). The marker is AVAILABLE, not
  REQUIRED — most closes resolve no defect, and a required field degrades to boilerplate — and
  nothing is backfilled, because a disposition reconstructed after the fact is a falsified
  record, not a repair (n=386 clauses 3/5/6; #53 clause 7).
- **A repair must not terminate the canonical run.** The trailer is POSITIONAL, so text
  appended AFTER it ends the run and every trailer-scoped reader stops seeing the row's
  declared telemetry — the repair silently REMOVES a measurement from the fleet total.
  `tools/ledger.py repair` therefore inserts its appended text BEFORE the run, so a prose
  note lands in the head and the run stays terminal; a `key=value` append EXTENDS the run
  itself and is safe either way — **when its key is NEW**. An append that introduces a key
  the run ALREADY declares is **REFUSED**, non-zero, before any write, so the ledger is
  left byte-identical: one field carrying two values has no canonical reading, and a
  consumer that takes the last occurrence reads the appended one while the row's own
  declaration still stands beside it. Refusing costs nothing lawful, because repair's
  lawful case is a row **INCOMPLETE** against a declared invariant — and an incomplete row
  is MISSING the key, never carrying it twice. Both sides of the comparison are read
  through the shared predicate (`field_predicate.declared_keys`) and each is scoped to its
  own canonical run, so prose in the head is not a declaration of the field and a prose
  append that merely NAMES a field is not refused (#104, ruled at ledger n=620 PART 4).
  Measured precedent: n=303's two parenthetical `REPAIR NOTE`
  sentences displaced its own canonical `cost_usd=2.7719 tokens_out=9956523 turns=1 …`, which
  was canonical when the row was written. n=303 is **not** backfilled — the law above bars it
  — and stands as the measured precedent (#91, ruling n=572 PART 3).
- **A predicate's SCOPE is its reader's population, and the two are stated together.** A
  predicate that claims the box and reads one profile root answers about the profile root,
  and its evidence must name the population it read — the count and the homes — so a
  narrower read is visible as a narrower read rather than as a clean box. An enumeration
  that cannot name its own population is not allowed to report HOLDS, and a home it could
  not reach is reported as unreached, never omitted (#102).
- **A measurement whose EITHER SIDE reads live state is a property of the INSTANT, not of the
  revision — and naming the sha does not make it one.** It must name the instant it read, and it
  must not be generalized into a revision property: #63 governs the case where both sides are tree
  bytes, this governs the case where they are not. The two properties are then kept APART.
  REPRODUCIBILITY — a committed artifact against a replay from its OWN RECORDED INPUTS — is
  deterministic, offline, and belongs in the correctness pass. FRESHNESS — an artifact against live
  state — is true only near the instant of the render, and it is REPORTED, never folded into the
  correctness verdict, because a check that fails by construction carries no more information than
  one that cannot fail. The POPULATION half is the predicate clause above: a predicate's scope is
  its reader's population, and the two are stated together (#102, #103).
- **A gate's time budget is a DECLARED MULTIPLE of a MEASURED runtime, never a round number.**
  A cap picked by feel is uncalibrated in both directions: too low, it kills a healthy gate and
  reports a timeout as a verdict; too high, it hides a hung one. So each gate's cap is derived —
  `budget_sec = margin_x × measured_sec` — with the margin, the measured runtime and the
  ABSOLUTE sha the measurement was taken at declared together in the gate-budget manifest, so
  the number carries its own basis and a reader can recompute it. The budget VALUES are the
  process owner's, never the implementing lane's (n=574 PART 5). A gate with no entry uses the
  declared default and the audit PRINTS which gates used it — a declared default with a printed
  population is not an exempt-by-silence surface, an unprinted fallback would be. A budget
  exhausted is UNKNOWN: never green, never a plain failure, and its recorded duration is the
  MEASURED elapsed time, never a hardcoded zero — a timeout is a fact about a gate and must be
  readable as one (#94, ruling n=744).
- **A predicate that examined nothing has reported nothing, not HOLDS.** Naming a population and examining one are two properties, and the first does not carry the second: a predicate can name its population exactly and still read zero items inside it, and its clean verdict over that empty read is indistinguishable in the output from a verified one. So every predicate that reports a clean verdict over an enumerated population asserts that the enumeration was NON-EMPTY, prints the count it examined, and FAILS LOUDLY on a zero count, naming which population came back empty. A gate that examined zero items must never print the verdict of one that examined the population and found it clean. This generalises a property already stated for one gate (`tests/test_ledger_no_shrink.py`) and already practised across the suite; it is codified because a predicate that cannot name its own population is already barred from reporting HOLDS, and a predicate that names its population perfectly and examines nothing is the same failure one step further in.
  The clause is **two-part**, and the second part is what keeps it from being satisfied by an exit code: a gate PRINTS the population it examined, and it is proven to BITE by a probe that makes it fail. **NON-VACUITY IS A PROPERTY OF THE PROBE, and POPULATION VISIBILITY is the property of the run.** A gate whose only evidence of working is an exit 0 over a population it does not print has not been shown to work. The loud-fail-on-zero form is right for a gate whose population is the whole history — `tests/test_ledger_no_shrink.py`'s is — and **wrong for a forward-only gate whose population is legitimately empty until its next instance**, where the probe is the only thing that can show the gate bites (#112, ruling n=657 item 8).
- **A cited line is evidence of a FACT, never of a CAUSE.** A log line, a count or a config read can establish that something happened; it cannot establish what produced it, and a causal sentence built on top of a real observation is a separate assertion that needs its own support. A cause is established by varying it — the effect follows — or by its absence coinciding with the effect's absence, and the ruling or entry that asserts one names the disproof it rests on. The sharpest available test, and the one this factory lost a ruling to: **a cause that VANISHES while the effect persists at FULL RATE is not the cause.** No gate can read causation, so the upholding mechanism is a PROCESS (P29), not a gate — and the clause is the second half of the record law above: the RECORD of a defect states its cause, so the cause must be as checkable as the fact.
- **A claim about the FUTURE is a third assertion class, supported by neither a fact nor a cause.** A status residue — `delivery_failed`, a failure timestamp, a non-zero count — is a fact about the PAST; promoting it into a prediction (*"it will fail again on 10-01"*) requires reading the field's **current** value AND the **guard** that gates the path the prediction names, and stating both. A prediction resting on the residue alone cannot be falsified before its date and reads as a live defect to every reader until then. Measured 2026-09-24: an advisory asserted a job would fail again on its next scheduled fire on an unbaked target URL, while `deliver_to` had read `NULL` since an unrelated edit — the guard is unreachable from `NULL`, so the predicted failure could not occur, and the repair had landed by accident rather than by a repair. Its sibling claim failed identically in the same artifact (*"has been failing silently since …"*, derived from a create-time test fire 7.565 s after creation), so the two shapes travel together: a recurrence assertion is a claim about the future, and the artifact that asserts one usually asserts the other. Origin: raised by the lane that produced it, whose own rework entry named the missing clause rather than leaving the gap unwritten.
- **Canonicality: which of two contradicting states stands (the ladder, T0–T4).** A check that
  reports a discrepancy has found a *disagreement*, not a *direction* — and a lane that guesses
  the direction repairs the canonical side to match the stale one, which is worse than the
  discrepancy standing. So every such report carries the TIER that resolved it, cheapest rung
  first:
  - **T0 — identity.** Read the objects' own fields before arbitrating anything: the question is
    often malformed rather than the state (a quote attributed from row adjacency; a paired file
    where byte-identity *is* the property). One read, and the question dissolves.
  - **T1 — precedence.** Where one side is UPSTREAM of the other, upstream wins and no goal
    knowledge is needed: source over render, authored over generated, live over snapshot, and
    §11's one named writer over every other path to that surface. **T1 POINTS AT §11's table and
    never restates it** — a second copy would drift from the gate that reads the first, which is
    the defect this clause exists to prevent. Precedence is never RECENCY: the newer side does
    not win.
  - **T2 — metric.** Only where both sides are genuinely independent does the factory's own goal
    decide, and the resolution NAMES the metric. An unstated metric cannot decide, so a T2 claim
    that cannot name one is a T3 or a T4 by construction.
  - **T3 — strategy.** Where the goal is too abstract to decide, a declared strategy does. The
    strategy layer is **already machine-readable, and the ladder does not duplicate it**:
    `tests/test_law_coverage.py`'s `PRACTICE_GATES` maps every practice law to the artefacts that
    uphold it, and the gate prints its own mapped count on every run — so a lane holding a check
    **inverts that map** to read its strategies off the existing relation rather than adding a
    second one beside it. No count is written here: the figure belongs to the gate that measures
    it, and a number copied into this file would be stale the moment a law is typed. A per-check
    copy of that field is the drift this clause's T1 rule forbids, in the strategy layer.
  - **T4 — neither.** Neither side is canonical on the evidence available: one is superseded, or
    both, or the identity needed to decide was never recorded. **T4 is a VERDICT, not a failure.**
    Its two answers are *re-measure* and *UNRESOLVED with the open question named*. Forcing a pick
    is how a durable record acquires a false fact — where no surface records the actor, the honest
    outcome is a recorded `UNRESOLVED`, never a named culprit.
  **The verdict NAMES its tier, and a T4 is loud.** A resolution that does not say which rung
  decided it is unauditable and can never be re-litigated when the metric or strategy moves. A
  check that found a discrepancy and reached no tier prints that outcome the way the patrol prints
  its `RAN` / `NOT RUN` legs, so "no tier resolved it" is never readable as a clean result. Its
  upholding mechanism is a PROCESS (P29), not a gate: no gate can decide a metric comparison, and
  one that pretended to would fail in a way that reads as a finding — so the standing patrol
  reports each tier that went unresolved.
  **Canonicality is not ownership, and the two are read apart.** `ONTOLOGY.md` carries the pair:
  ownership (§11) is *authority over a surface*; canonicality is *truth about a pair*. Ownership
  supplies ONE of T1's four precedence forms — it decides only when one side derives from the
  other. Two readings of the SAME surface share an owner, so ownership cannot choose between them;
  and a disagreement whose owner is undecidable is a T4, not a licence to name one.
  **What this does NOT do:** it never pre-writes canonical state per surface. That is the one
  approach that goes stale silently, which is the disease rather than the cure; the ladder is
  walked lazily, at the site, only where a disagreement actually exists.

**FOUR SHAPES OF THE SAME FAILURE — a surface that reports SUCCESS while the work did not
happen (derived 2026-09-25 from the question register's own defects, agent-factories#165).**
They are one family and each is a distinct mechanism, so the family is stated once and the
shapes are named. The common thread with *a green receipt over an unverifiable check* is
that the surface is not merely wrong: it is **confidently wrong in the direction that stops
anyone looking**. And the measured weight of the family: **three of the four were found by
the human, not by a gate**, while the register's own selftests were green throughout.

- **(a) A state transition must carry the content that justifies it, or be refused.** A
  transition to `awaiting_clarification` with an empty payload is a *drop wearing a status
  field*: the machine changed state, the reader was told nothing, and the lane that owns the
  question received a request with nothing to act on. The test is mechanical — **name the
  payload the transition carries, and refuse the transition if it is empty.**
- **(b) Every state a machine can enter must be distinguishable in the surface the human
  reads.** If the renderer does not read the status field, the status does not exist for its
  only reader: a clarifying question rendered IDENTICALLY to an open one, so the human could
  not tell whether his own earlier tap had registered. **The renderer is the reader; a state
  with no reader is a state the human cannot act on, and the defect is invisible from the
  machine's side because the machine's own tests assert the value it wrote.**
- **(c) An error path must be rendered by the surface that triggers it.** Where a transport
  swaps only success responses, a refusal produces NO visible change — and **an invisible
  refusal reads as a no-op, so the user repeats the action**, which is worse than an error
  message because it also destroys his model of what the control does. The rule binds the
  transport, not the handler: a handler that returns a correct refusal has not rendered it.
- **(d) A field written but never read is a record that can only lie.** Before adding a
  state field, **name its reader**; if it has none, the field is a liability rather than a
  record, because it will be read by whoever finds it next and believed. Two instances of
  this shape in one day, on two different surfaces: `answer_kind` left stale by `amend`,
  asserting a state the question was not in, and the duty receipt's `outcome=` measured as
  dead code on real receipts (so a row declaring nothing certified the duty). **The check is
  cheap and it is the one nobody runs: grep for a reader before you write the field, and
  again when you change what writes it.**

**Why these belong in this section rather than in a testing section.** Each is a *claim* the
system makes about itself — the status says awaiting, the page says open, the transport says
nothing, the field says completed — and a claim with no reader is the failure mode this
whole section governs. A gate can hold (d) once the reader is named, and can hold (a) once
the payload is declared; **(b) and (c) are not gate-able at all**, because their subject is
what a HUMAN sees, and no offline suite reads the human's screen. That is why three of the
four were found by the human, and it is the reason the four are stated as design obligations
rather than as gates: the remedy is to name the reader while the surface is being built.

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

| Surface | Holds | Authoritative writer | Everyone else |
|---|---|---|---|
| the issue board (`leshchenko1979/agent-factories` issues) | the work itself — intake, state, and the receipt that resolved it | the lane that files or settles the item (`Triage` owns intake) | read-only, via `gh` |
| `evidence/ledger.jsonl` | every state transition — intake, claim, dispatch, close, score, ruling, run | `tools/ledger.py append` | `tail`, `verify` — read-only |
| `evidence/subprocesses/*.jsonl` | granular domain-specific subprocess event streams | `tools/ledger.py append --subprocess` | `tail`, `verify` — read-only |
| `evidence/insights.jsonl` | empirical factory insights across growth stages | `tools/insights.py append` | `list`, `verify`, `format` — read-only |
| `evidence/rework.md` | the rework entries this factory has **recorded** — each defect, regression and law rollback it wrote down, with its root cause and what now prevents it | the lane that HOLDS the defect: the declaring lane where a close declared the entry, the discovering lane where a patrol or survey found it | read-only; `tests/test_rework.py` gates each entry's completeness, the `Subject` column's vocabulary, the table's contiguity, every rate claim's form, and that every determinate `Subject` resolves to a real closed work unit (each unresolvable one reported by name); the share of closes DECLARING a rework disposition is PRINTED, never gated — never the completeness of the set |
| `evidence/scores/<date>.md` | one measurement run, one file per run | the daily measurement job (`Surveys`) | read-only |
| `evidence/*.md` | survey receipts and dated evidence | the survey run | read-only |
| `ONTOLOGY.md` | the canonical vocabulary | `HQ` | read-only, gated by `tests/test_ontology.py` |
| `docs/processes.md` | the canonical process register | `HQ` | read-only |
| `skills/meta-factory/SKILL.md` | this law | `HQ` | read-only |
| the questions register (profile home, outside this repo) | the open questions lanes have DECLARED, one standing set per factory key | the `oc-questions` tool | read-only; the rendered page is served from `vpn` behind basic auth |

**The ledger carries a SECOND object, and its author is not the append path.** `evidence/ledger.jsonl` has one *writer* — `tools/ledger.py append` — and two *objects*. The first is a state transition, authored by the lane that makes it. The second is a **duty receipt**: a `run` row written by the **woken lane** when a thin trigger's duty actually completes, on behalf of the duty rather than of the trigger. The distinction is load-bearing because the two are separated by a silent gap: a pacemaker's own run row records that the **trigger fired**, never that the **duty ran**, so a job can read `success` on every fire while the work it exists to produce fails every day (#147). Nothing in the trigger's own record can close that gap — only the duty's lane can, by declaring the receipt, and the receipt is what the patrol consumes. A lane that wakes, does the work and writes no receipt row leaves the duty **unproven**, not discharged.

**A duty receipt is DECLARED, and the declaration is one whole line.** The row states `receipt_subject: <stem>` on a line of its own — anchored, so a mid-sentence mention cannot satisfy it — and the reader keys on that declaration rather than on a job name, so no job name is hardcoded and a row that declares nothing is *counted and named* as NOT JUDGED. **The declaration is the whole mechanism, so its omission is the failure it cannot see:** a row that simply omits the line is not a duty that owed nothing, and a reader that cannot tell those apart has a leg that passes by silence. A pacemaker whose duty owes a receipt therefore STATES the declaration in its own prompt, and the round is read from the row's own `last_run_at` — never from a parsed schedule, which is a second derivation of a fact the row already carries.

**`attested_at` is RESULTING STATE, never the receipt.** It is a *consequence* of a completed round, and a consequence is not evidence that the round happened: four fragments carried an `attested_at` four days stale against a job firing daily at `0 6`, which is exactly what an unreceipted duty looks like from the registry side. So `attested_at` prints under the label RESULTING STATE, is never consumed as the receipt, and never stands in for one. When it cannot be read, the reader says *why* rather than printing a date — an unread field is not a clean one.

**The receipt's SUBJECT is canonical, and the reader's key is deliberately NOT widened to meet a deviation.** A receipt's subject is `<stem>-<round>`: `<stem>` is the job's own declared `receipt_subject`, and `<round>` is its own `last_run_at` UTC date. The key is a **boundary-checked prefix** — the subject must start with `<stem>-<round>`, and the character after it must not be a digit, so a different date whose subject merely extends this one's digits (`...-2026-09-250`) cannot match. That tolerance exists for **round-key variants**: an hour-bearing subject (`patrol-verify-2026-09-25T06`) names the same round, and so does a trailing word. It is never licence to decorate: a subject that puts words BETWEEN the stem and the round (`registry-attest-writeback-2026-09-25`) does not name the round at all and is **not a receipt**, and the leg reads MISSING — loud, and true. **Do not widen the key to a fuzzy token match.** A false MISSING costs one look; a false CLEAN is silent, and this leg exists precisely because silence is the failure it cannot see (#160). The writer is upstream of the reader: fix the convention, never the key.

**A subject match is not a receipt — the row must DECLARE its completion.** A receipt carries `duty=completed`, `failed` or `skipped`, read through the shared positional reader (`tools/field_predicate.py::declared_duty`) against the domain declared beside it (`DUTY_DOMAIN`). A row whose subject matches the round and declares nothing is **not** a receipt: the leg's first version accepted any subject match, so a DISPATCH record written before the round completed certified it, and a round with no receipt at all read clean. Absent is not a value, an out-of-domain value is an ERROR, and `failed`/`skipped` are both findings. **The key is a distinct field, never `outcome=`:** a duty receipt is selection-biased — written by a lane that completed a duty — so folding it into the first-pass yield's population makes that metric structurally optimistic, one real lane failure diluting it roughly twofold. One number answering two questions is the #143 class.

**A pacemaker's redirect log is named after ITS OWN JOB, and the leg's precondition is
stated rather than assumed (2026-09-25, #163).** The notify-receipt leg attributes a
trigger's log by taking the filename's stem as a **cron job name** and looking it up among
the rows this factory declares (`patrol_host_state.py`, `NOTIFY_LOG_RE`). That makes
*the redirect label equals the job name* a load-bearing contract between every pacemaker
prompt and the leg — and it was written nowhere, which is how one job carried a
hand-typed label for **16 rounds** and every one of its logs landed in `retired_logs` as
*history, never judged*. The leg examined **nothing** and printed the same shape as a leg
that examined everything and found it clean.

**A mechanism whose precondition is undocumented is a permanent silent exclusion**, and it
is the mirror of the receipt clauses above: there, a declaration without its instruction
is a permanent false RED; here, a mechanism without its stated precondition is a
permanent false CLEAN. Both are the same failure — a contract that lives only in one
side's implementation.

So a pacemaker whose prompt writes a `/tmp` log **names the redirect after the job**, never
after a description of its cadence (`/tmp/factory-triage-patrol-<ts>.log`, never
`/tmp/factory-triage-6h-<ts>.log`), and a label that names no row is a finding rather than
history. When a redirect is renamed, **the prose that justified the old label is rewritten
in the same edit** — a prompt arguing for a label it no longer carries is the half-fix
shape this section rules against twice.

**THE WRITE PATH OWNS THE ACTOR, AND THE ACTOR IS DERIVED — identity is mechanical, never declared.** A row's `actor` is a **derived** value, read from `OPENCRABS_SESSION_ID`, which the daemon exports into every tool subprocess, resolved through the registry's own lane resolver (`registry.resolve_lane`, the same code that renders `registry/state.json`). The kit never asked for it, so identity was whatever a lane typed into `--actor`: checked for **membership** in the known-actor list, never for **authorization** against the per-event matrix, which meant an unauthorized row was written **silently** and surfaced a day later when the schema gate ran. Measured: three `intake` rows in one member factory carried `actor=worker`, and `intake` is Triage's — the write path accepted every one. The tool now enforces the matrix at append, so the row is refused **when it is written** rather than reported later, and a `--actor` is accepted only when it **AGREES** with the derivation. A lane it cannot resolve is refused **by name**, never defaulted: `repair` used to default to `worker`, so omitting the flag stamped the repair as the Worker regardless of who ran it. **A FIXTURE is the one exception, and the seam is what makes it safe:** a redirected `OC_LEDGER_PATH` or a `--subprocess` sub-ledger names its own actors, because a throwaway ledger has no live lane to bind to — and reaching the **live** ledger requires both overrides to be absent, so a fixture cannot smuggle a role into it.

**THE SETTLEMENT RECEIPT IS THE TOOL'S, NOT THE AUTHOR'S — and this retires the self-referential count (2026-09-25, superseding the `rows=` clause in part).** Settlement is *append the close row, then verify*, so the receipt must cover the row it certifies — and it had to live **in** that row. Both cannot hold in one append, so the law asked the author to declare `rows=<count>` where the count must be at least the row's own number. **The author cannot know that number:** it is assigned inside the append lock. The only way to satisfy the predicate was to **predict** `current_count + 1`, which is right until a peer appends in between — measured across all five factory ledgers, **2 of 17 declaring closes were off by exactly one** for exactly that reason, both now permanent debt because an append-only ledger has no repair space for a wrong number. The declaration is **retired**, and `append --event close` now writes a **second row inside the same lock**: a `run` row carrying `verified_rows=N`, where N is the count the sequence check covered with the close row present. No prediction and no self-reference — a row *about* a row, written after it. It carries **no `outcome=`**, for the duty receipt's own reason: a settlement receipt is selection-biased, so admitting it to `first_pass_yield_population` would make the published yield optimistic. **The commit-msg hook already refused a subject citing a row number for this same reason** (*"the number is assigned inside the append lock, so it cannot be known before the append"*, ruled n=405) — the close-receipt was the one surface still demanding the forbidden prediction.

**Which pacemakers owe a receipt.** Every pacemaker whose duty is performed by a **woken lane** — because its own run row records that the trigger fired and nothing about the work. A `trigger_cmd` gate does not exempt a job: a gate is a **pre-condition** that decides whether the trigger fires, and it says nothing about whether the lane then woken did the duty. The test is not whether the duty's work is recorded *somewhere* — a woken lane's own run row usually exists — but whether the leg can **BIND** that row to *this* job's round. Without the declaration it cannot, which is exactly why the declaration is an attribution key rather than a claim that nothing else records the work. A job that declares no stem is NOT JUDGED, and is counted and named so its silence is visible. A duty whose lane writes an undated, ad-hoc subject predating this convention owes the convention going forward: the receipt carries the round.

**A close and its board are coupled in four directions, and each one has its own mechanism.** (1) A close ROW must name the board state it observed — gated by `tests/test_close_board_recorded.py`. That gate cannot call `gh`: the mechanical suite runs offline and against a tree, not a live board, so the settling lane records the board state it saw and the gate asserts the record exists. (2) A close must be preceded by its own intake and claim — gated by `tools/ledger.py verify`, which reads a subject's rows as a sequence and names the subject and the missing leg. (3) A CLOSED board item must have a close row — **no offline gate can reach this direction**, and each mechanism says why in its own code: a gate cannot call `gh` (1 above), and `verify` builds its sequence check by iterating close rows, so a subject with no close row is never visited. Its upholding mechanism is therefore a PROCESS: a standing patrol cross-reads the board against the ledger. P29 admits a process as readily as a gate — a rule needs one or the other, not specifically a gate. The patrol is a runner, and its legs print whether they ran. Directions (3) and (4)'s standing patrol is `tools/patrol_host_state.py`, invoked on the factory-triage-patrol cadence (0 */6 * * * UTC). It reads the board WHOLE — gh issue list --state all — because the reverse leg, an intake row naming no board issue, is sound only over the full board, and feeds it to board_intake_problems(..., complete_board=True). Each leg prints RAN or NOT RUN with its reason AND the population it examined, so a leg whose predicate was never written is never read as a clean one and a leg that examined nothing is never read as one that examined the population and found it clean; the runner states the instant it read the board so every claim it makes is re-checkable. A board that cannot be read exits 2 with NO verdict: an unreadable board is not an empty one, and an empty board is not a clean one.

**(4) A close row's `board=closed` declaration must be TRUE — the direction the offline gate cannot reach either, because that gate reads the ROW and never the board.** Recording a state is not verifying it: direction (1) makes the omission visible, and nothing made a FALSE declaration visible, so two close rows declared a board close that had never happened and the gate read clean over both (#117). Its upholding mechanism is the same standing patrol, which gained a `board-close` leg: it reads every post-invariant close row through the GATE's own `BOARD_TOKEN` and `INVARIANT_LANDED` — never a re-derived parser, because a canonical-trailer read sees only 40 of the 52 such rows and a re-derived leg would judge 12 rows fewer and go false-green over them — and reports each declaration the live board contradicts, printing the population it examined and the instant it read the board beside its verdict. A subject the board has never heard of is reported too: `absent` and `closed` are different facts, and only one of them is what the row declares.

**A patrol claim about the board names the time it read it.** A claim like "no closed item lacks a close row" describes a live board at an instant; without the instant it cannot be re-checked, and by §8's own rule an uncheckable receipt is testimony, not evidence. So the patrol states its read time beside its finding.

**A committed board snapshot was considered for direction (3) and rejected.** It would make the comparison offline and gate-able, but a snapshot carries a freshness dimension the gate cannot attribute: a stale snapshot REDs for a subject whose close row landed after it was taken, and passes for one closed since — the gate would name a board/ledger mismatch when the real cause is a stale file. A detector that cannot name its cause is worse than a process that can, because it fails in a way that reads as a finding.

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

**A commit message names the concern; it does not cite row numbers.** A ledger row's
number is assigned *inside* the append lock, so it cannot be known before the append —
and by the time the commit runs, another lane may have appended further rows. Three
instances in one day carried the same shape: `d763277` named `n=211` and added
`211/212/213`; `d75b19a` named `212/213` and added `214/215`; `b12047e` named `n=259`
and added `n=261`. That is structural, not carelessness. Where a row must be cited,
cite it in the ledger's own `detail` text — written after the append, where the real
number can be read — or read it back before committing. This follows from the ruling
that the commit is **transport, not identity**: the row's identity is its `n`, so a
message asserting row numbers is a claim that can be wrong, and obeying this clause
removes the claim rather than policing it. It is upheld forward-only by
`tests/test_ledger_commit_cites_no_rows.py` — a history-wide form would be permanently
red, since 55 of 146 historical ledger commits cite row numbers in their subject.

**A law file's `version:` field is a CONTRACT with the body beside it, and the two move in the SAME commit.** Every law file in this repo — `skills/*/SKILL.md` and `TEMPLATE/SKILL.md.tmpl` — declares its own `version:`, and each carries its OWN, because the two are not byte-paired: they are independent documents that happen to share a structure, so a version field shared between them would name two different bodies at once and could not be a contract. The contract has two arms and both are needed. **Arm 1:** a commit that changes a law file's BODY must move THAT file's version in the same commit. **Arm 2:** a commit that moves a version must change that file's body. Arm 1 alone catches an unbumped law change; arm 2 catches a bump that names no new bytes, which mints a version range with no content — the same ambiguity the contract exists to remove, seen from the other side. Together the arms force the version and the body to move together, which is what a field naming the bytes means. The predicate is a BYTE change and never a judgement about whether a change was substantive: deleting a duplicated paragraph IS a body change and DOES require a bump, because a lane holding the old copy genuinely has different bytes.

What the contract buys is a lane's own staleness check. After a compaction a lane has lost the law text it was working to, and the only durable thing it can hold is a version. The field therefore has to mean the bytes: a lane that reloaded after a compaction holds the version it last read, compares that against the file in front of it, and a mismatch says the law moved under it. A version that drifts from its body makes that comparison silently useless — it reports "no drift" for a law that changed, which is the exact failure the check exists to prevent.

Upheld forward-only by `tests/test_skill_version_contract.py`, whose boundary is declared in `docs/ledger-invariants.json` under `skill_version_contract` and which reads from its landing commit forward. The historical decouplings are excused and printed as excused, never repaired — a bump written after the fact would be a falsified record rather than a repair. Nothing is backfilled.

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

**One field, one predicate — the read-side mirror of the rule above.** A telemetry field
read out of a row's `detail` has exactly ONE predicate, and it lives in
`tools/field_predicate.py` (`keyed_value`, `declared_field`, `trailer_tokens`,
`split_canonical_run`, `declared_telemetry`, `mentioned_telemetry`,
`telemetry_value_problem`, `telemetry_problems`). A module that reads such a field IMPORTS
that predicate; a private parse of the same field is the defect this law names, not a style
preference. The evidence is this factory's own record rather than a principle: the helper
was built at `n=405` PART 5 as "ONE field predicate, shared by all three call sites", and
the class recurred anyway — the aggregator, ruled a fourth site at `n=572` PART 2 and fixed
under #90, and `tools/synthesize_insights.py`, the fifth, under #99. Both were found by
SYMPTOM, a measured over-report, and neither by a rule, because until this sentence no rule
was readable. The predicate is scoped to the canonical trailer because `detail` is free
prose that QUOTES trailers as evidence, and a private scan takes a quotation for a
measurement: `n=586` aggregates `n=303`'s quoted trailer and over-reported cost 16x.

The gate that enforces it is `tests/test_telemetry_reader_registry.py`, and it must
distinguish a READER from a WRITER, must name the modules it permits in a stated
allow-list, and must PRINT that allow-list on every run — an unprinted allow-list is an
exempt-by-silence surface, the class ruled at `n=571`. Both halves are load-bearing
together: a blunt scan for telemetry-shaped strings reports three modules under `tools/`
that carry no predicate and only ONE is a genuine call site (`telemetry.py` is the WRITER,
and constructing a token is the opposite of reading one; `patrol_host_state.py`'s only hit
is the word `turns` inside a prose message), so a gate without the distinction would need
an exemption for a non-defect — and an exemption granted to something that is not a defect
is a permanent weakening.

**What that buys is the SYMBOL, not the semantics.** The law binds every reader to one
function; it does not promise that function reads correctly, and no probe over a shared
binding can show more than the binding. `tests/test_close_row_revision.py` states the bound
of its own probe — "a lookalike defined here would satisfy every behavioural probe above
and still leave the class unfixed" — and the same holds here: a lookalike that
re-implements the predicate and is imported under its name satisfies an identity probe of
the imported name and leaves the class open. Stated so the rule is not oversold: identity
of the function is what is codified, correctness of the reading is
`tools/field_predicate.py`'s own gate (#99, ruling n=599).

**A gate whose only exits are barred is a stop with no andon cord.** A gate that reads commit *subjects* across a range can be violated by a commit already PUSHED, and then no repair is available: the commit is immutable, a revert does not remove the offending subject from the range, and re-anchoring the marker past the violation would make the marker's own stated definition false and silently convert a live violation into an excused one — the exact silent-excuse failure the exemption design forbids. Left that way the suite stays permanently RED and the next lane learns to ignore a red gate, which destroys every other gate's signal; so the defect is the EMPTY REPAIR SPACE, not the violation. Every gate of that shape therefore carries a sanctioned, VISIBLE exit: an exemption table holding the entries as FACTORY DATA in its own file and never inline in the gate, because the gate is paired byte-identically with its template copy and a factory sha must not ship to every new factory, and each entry is keyed by the FULL 40-character sha copied from live git output. An exemption is a visible debt, not forgiveness: every entry that MATCHES is printed as an `excused:` line on EVERY run, and the closing line distinguishes clean from excused, so the two are never the same output. An entry that is malformed, or that matches NO violation in the range, is a gate ERROR rather than a silent pass — an exemption list that quietly fails to load is indistinguishable from no exemptions, and a stale entry inflates the visible debt while excusing nothing. Admission is by PROOF, as everywhere in this section: an exemption is granted only where the repair space is genuinely empty, and the entry STATES that proof; an exemption nobody would defend in that output is one that gets fixed instead. And a SECOND exemption of the same shape is a PROCESS DEFECT, not an exemption — one is a debt, two mean the mechanism (running `tools/audit.py` before a commit that touches the surface) is not biting, and the remedy is a mechanism, never a third row. Instances: `docs/ledger-commit-exemptions.json` for `tests/test_ledger_commit_cites_no_rows.py`, and `docs/ledger-no-shrink-exemptions.json` for `tests/test_ledger_no_shrink.py` (#47 clause 4, ruling n=328).

**A row is retired by naming it, never by deleting it.** The single-writer lock above binds the code, not the artifact: a writer that never calls `tools/ledger.py` takes no lock and leaves no trace, and once its removal is *committed* the append guard compares working against committed, goes self-consistent, and every gate reads green over a ledger that has lost committed history. So no row identity — the `(n, ts, event, actor, subject)` tuple a row is known by — is ever removed: a row that must not stand is retired by appending a row that names it, and the original stays. `tests/test_ledger_no_shrink.py` walks the committed history and reports every commit whose diff removes a row identity, which is why the check is a set difference over identities and not a text search — the one measured case removes a row whose surviving neighbours still contain every word it carried. Its exemptions are factory data in `docs/ledger-no-shrink-exemptions.json`, keyed by full sha and never inline in the gate, and every run prints them so "clean" and "excused" are never the same output; a gate that examines zero commits fails loudly rather than passing vacuously.

**"Retired" names two different objects, and the difference between them carries the teeth: a row's IDENTITY, and a FIELD VALUE the ledger cannot remove.** The clause above governs the first — the `(n, ts, event, actor, subject)` tuple a row is known by — and its hazard is a writer that bypasses the append lock, so its evidence is a set difference over committed history. This clause governs the second, and a reader who takes the first as covering both will miss the difference. A close row declares the revision its receipts describe (`head=<sha>`), and the ledger is append-only, so a token that resolves to nothing **cannot be removed**: the row stands exactly as written and the false value stands inside it. The exit is a DECLARATION in its own file — `docs/ledger-retirements.json` — which NAMES the value rather than excusing the row. **ADMISSION IS A PROOF OBLIGATION, NOT A LOOKUP:** an entry is admitted only when the ledger CARRIES its naming row AND that row's detail carries the false value VERBATIM. The naming row is what makes a retirement auditable — it is the row that says *this value was wrong, and here is the right one* — so a declaration whose naming row is absent, whose naming row does not carry the value it claims, or whose target row's canonical run does not declare that value at all, is a gate ERROR and never a silent pass; and an entry matching no unresolvable token is an error too, because it would inflate the visible debt while excusing nothing. The surface lives in the tree the gate judges and never inline in the gate, because the gate is paired byte-identically into `TEMPLATE/` and a factory's own row numbers must not ship to every new factory; the skeleton is `TEMPLATE/docs/ledger-retirements.example.json`.

**The existence leg asks whether the declared object EXISTS in this repository, and its bound is the part a reader will overread: EXISTENCE is neither ANCESTRY nor TRUTH.** A declared revision that resolves is not thereby the revision the row MEASURED, and the leg cannot say that it is. Ancestry is refused as the predicate for a MEASURED reason rather than a taste: a history rewrite leaves an honest revision unreachable while its object survives, so an ancestry test would condemn exactly the rows a rewrite did not touch. The distinction is not hypothetical — the leg exists because a close row declared a token that resolves nowhere while its TRUE revision resolves, so the leg reports the difference and the retirement names it. And **a leg that cannot judge SAYS SO**: on a tree with no object database the leg reports a STATED inability and the run prints `NOT RUN` with its reason, never the verdict of a leg that examined the population and found it clean.

**A retired declaration is NEITHER edited NOR excused.** It is not edited, because a ledger row is append-only and the one-append-path rule stands — a correction is a DECLARED DEVIATION, never a precedent. And it is not excused, because excusing is what the exemption surfaces do for a violation whose repair space is empty, while a retirement does something different: it names the false value, keeps the true one beside it, and stays visible. So the gate prints every admitted entry as a `retired:` line, beside its `excused:` lines and the count it examined, and the three — `clean`, `excused`, `retired` — are never the same output.

**A row count is not an integrity check.** The ledger is read as a *sequence*: a subject
that reaches `close` must have been filed (`intake`) before it and taken (`claim`) after
that intake, and `verify` fails naming the subject and the missing leg. A ledger can be
perfectly numbered and still say that work was closed without ever saying who took it. Each
missing leg is reported independently, so one pass says everything that is absent, and the
order leg is evaluated only when both legs are present — bounded by the latest intake before
the close, so a re-opened subject must be re-claimed. Exemptions are listed explicitly by
subject, leg, date and PROOF in `EXEMPTIONS` inside `tools/ledger.py`, and printed as
`excused:` whenever one is used, so "clean" and "excused" are never the same output. An
exemption nobody would defend in that output is one that gets fixed instead. Two kinds are
admittable, and the boundary between them is the PROOF: a leg missing on a close written
BEFORE the gate existed is excused by the boundary itself, while a leg missing on a close
written AFTER it is admitted only by an external receipt — never by a restatement of the
omission it excuses. An entry carrying no proof therefore excuses nothing: the omission
stays a problem and the refusal names the entry that failed to excuse it (#52 clause 3,
ruling n=318). Nothing is ever backfilled: an intake row written today for work filed before
the gate is a falsified record, not a repair.

**"A close row is refused at the write path when its subject has no preceding intake and claim."** `tools/ledger.py append --event close` runs the same sequence predicate `verify` runs — one predicate, two call sites — and exits non-zero, naming the subject and the missing leg, without writing anything. The refusal carries no exemption surface and needs none: a close appended now can never predate the gate. EXEMPTIONS governs `verify`'s reading of history only, and stays printed there. This does not replace `verify`: the order leg (a claim after its close) and any row written around the append path remain `verify`'s. §11's guarantee is one append path, not tamper-proof (#98, ruling n=596).

**A claim is an ACCEPTANCE, and it is stamped by the lane that takes the work — when it takes it, and before its first edit.** The three legs answer three questions: intake is Triage's filing, claim is WHO took the work, close is its completion. HQ's dispatch names the lane, and the lane's claim answers it; HQ never stamps the claim of the lane that took the work, because a claim records a taking and two actors on one transition is the shape this section forbids, applied to an actor rather than to the append path. The write-path refusal above is the BACKSTOP, not the step: it makes an omission impossible to reach a close SILENTLY, which is how the shape first appeared twice. A claim stamped after the work is a RECONSTRUCTED record: it must declare itself in terms, carry the token `claim=reconstructed`, and name the basis it rests on with the canonical marker `BASIS:` — and `verify` prints those rows beside its `excused:` lines together with the interval it recomputes from the row's own `ts` and its close row's `ts`, so clean, excused and reconstructed are never the same output. Forward-only: a reconstruction written before this sentence existed is not retrofitted (#98, ruling n=602; the interval moved from DECLARED to RECOMPUTED-AND-PRINTED under #115, ruling n=687).

**A reconstructed claim DECLARES itself and its basis; it never asserts an interval it cannot control.** The token above replaced a requirement that the reconstruction "take the close row's own ts, because both rows are written in the one instant", withdrawn by #112's ruling (n=657): the claim's `ts` is its own write instant, one of the five `ROW_IDENTITY` fields, while the close row's `ts` belongs to whoever appends the close — so the second boundary is not the author's to control, and a hand-supplied `ts` would invite back-dating on the honour system. Measured over the five historical reconstructions the gaps were 0s, 2s, 0s, 347s and 65s — THREE OF FIVE miss that equality, so a gate over it would have fired on honest rows. **A gate must test a property its author controls.** That fact withdraws the interval's VALUE for the same reason it withdrew the equality: the author controls the ACT of declaring, never the interval, which exists only once the close row is appended under the append lock. So the declaration is the two facts the author does control — the self-declaration token and the basis, named under the canonical marker `BASIS:` — and the interval moves from DECLARED to RECOMPUTED-AND-PRINTED: the reader recomputes it from the two rows' own `ts` values and prints it beside the row, tool-sourced on BOTH sides, with no typed expectation, read through the canonical trailer predicate, because one field has one predicate. The gate PRINTS the population it examined and is proven to BITE by a synthetic probe; its live population is legitimately EMPTY until the next reconstruction, so the loud-fail-on-zero form is the WRONG guard here. Its boundary is declared in `docs/ledger-invariants.json`, and the five historical reconstructions are OUTSIDE its population: NOTHING IS BACKFILLED. `n=602` PART 3(2) is SUPERSEDED by this ruling and stands as a ledger row — it is never edited. The `claim_gap` token is WITHDRAWN as a requirement (#115, ruling n=687) and no hand-edit of a ledger row is ever lawful — the one-append-path rule stands, and a correction is a DECLARED DEVIATION, never precedent.

**A ledger subject names an issue or describes the work, and the form says which.** A subject that names a board issue is written `#N` — the hash, the digits, and nothing else. `#N` is the strict form every subject-keyed predicate resolves through, so a near-miss is not a malformed reference to those predicates: it is not a reference at all, and the row silently leaves their population without ever being reported as wrong. A subject that names no issue is a descriptive stem naming the work in words (`pickaxe-attribution-trap`), and a clause label extending a reference (`#31-close-receipt`) is descriptive, not a reference — a mechanism that cannot tell those two apart from a broken reference will either miss the defect or fire on the law. The number a subject names is not bound to this factory's own board: a row may cite another repository's issue, so the form is what is codified and no gate may read `#N` as naming this factory's board without saying so. The gate that upholds this is `tests/test_subject_form.py`, and the instant it governs from is declared in `docs/ledger-invariants.json` like every other ledger invariant. **A ledger's `#N` namespace is ONE board's, and keeping it unique is the factory's obligation — the kit cannot check it.** The sequence predicate keys on the exact subject string, so two boards sharing a numbering make one bare `#N` name two work units, and the collision does not RED: a close on the second board's unit is accepted on the FIRST board's intake and claim, a defeated guard reported as clean (reproduced on a throwaway ledger against `TEMPLATE/tools/ledger.py` — `verify` rc=0, colliding close ACCEPTED rc=0, non-colliding control refused rc=1). A qualified reference is no discriminator either: `_STRICT` is `^#\d+\Z` while `_CLAUSE_LABEL` (`^#\d+-\S`) is descriptive, so `#17-campaign` would silently leave the reference population rather than name a second board. Nor can a board lookup close it — a row records a NUMBER and not WHICH board it meant, so the ambiguity lives in the row and not in the checker. A factory carrying more than one board therefore picks ONE disposition and states which: **scope lifecycle rows to the board the ledger records**, naming a second board's units with a distinct descriptive stem (which then needs its own intake and claim, like any subject), or **keep a second ledger** via `OC_LEDGER_PATH`. A bare `#N` is never reused across two boards.

**A lane's bindings are a SUPERSESSION CHAIN, and the live session is the newest binding within its own profile: a topic re-opened several times carries one binding per generation, and the newest is the lane. Only a match across two PROFILES is ambiguous, because there the registry cannot tell which daemon's session owns the topic; a single-profile chain is resolved by recency and the resolution is reported, never suppressed. The exit code carries the verdict: unbound and no-thread-id mean a declared lane is unreachable and exit non-zero, while a superseded chain is a live lane and does not (#100).**

The `chat_id` narrowing is what makes the PROFILE the partition: `resolve_lane` filters by
the factory's own chat before it counts matches, so every survivor already shares one chat
and a set spanning two profiles is the only case left in which the registry cannot tell
which daemon owns the topic. So `superseded` counts as RESOLVED in the exit predicate
(`unresolved_total` in `tools/registry.py`) and carries its own counter on `resolve`'s
summary line — visible without being a verdict — while `unbound`, `ambiguous` and
`no-thread-id` keep rc=1. The fix does not delete the detector it was built around:
`tests/test_registry.py` drives both halves over synthetic bindings, one profile to a
chain and two to `ambiguous`, because a chain-only probe would pass a fix that had removed
the ambiguity branch entirely.

**The cron table is the one surface this factory shares with every other, and sharing is
why only half of this law can be gated.** A factory's own jobs are named
`<declared-prefix><what-it-does>`, and `<declared-prefix>` is that factory's entry in the
fleet manifest's `job_prefixes` — **the prefix, never the slug**, because the prefix is the
only token a reader can resolve: a job name is judged against `job_prefixes` and against
nothing else, so a row named after its slug leaves its own factory's census silently
(#126). The two tokens coincide for most factories, which is why the distinction stayed
invisible until one of them did not. Those prefixes are the only reason a job on a shared
box can be attributed to its
owner at all, so no two factories may claim the same prefix — and `load_fleet_manifest`
now refuses a manifest where two overlap, **including one prefix nesting inside another**,
which `str.startswith` cannot tell apart and which would make the OWNER a property of
manifest ORDER rather than of ownership (`tests/test_registry.py`, probes over synthetic
manifests). Never disable, delete, edit or repace a job that is attributed to another
factory — a job you cannot attribute is not yours to touch, and it is reported instead. The
naming half is checkable per factory, because a factory can read its own jobs; the edit ban
is not, because it governs a cron table no single factory owns, and its upholding mechanism
is the process rather than a gate (#101): before touching a cron row, resolve the job's
owner through the registry attribution, and report a job you cannot attribute. That process
rides the existing ≥6 h attest pacemaker's question set rather than a new job.

**An ad-hoc probe never appends to live state, and the seam that isolates it is a MECHANISM, not a copy.** A scratch script, throwaway harness or one-off probe that appends to a durable surface is a SECOND writer on a surface this section gives one, and the rows it leaves behind are indistinguishable from real state transitions — the factory has paid for this twice, once with twenty rows and once with one, and in both cases the author did not know the seam existed. **Copying the data file isolates nothing:** the append path is bound to the TOOL's location, not to the data it reads, so a copy of the ledger with the tool still resolving its own repository root writes to the live file. So the requirement is a three-part SHAPE — the tool exposes a redirect for every path an append can land in; the harness binding documents those names and the incantation that uses them, because a name is a mechanic of one product and naming it in this law is a leak; and a gate proves the tool HONOURS each name the binding publishes, since a binding that names a redirect the tool no longer reads is a law naming a mechanism that does not exist. **The seam carries a stated COST:** a path outside the repository has no committed lineage to compare against, so the guard that makes a rewrite of live history loud FAILS OPEN and warns — that warning is EXPECTED on this path and is not an error. The gate that upholds this is `tests/test_binding_mechanism_exists.py`.

**A blocked decision goes in the register, and a prose line in the topic is NOT a registration.** A lane whose next action needs an owner decision registers it with `oc-questions ask --factory <key>` **in the same turn it stops** — because nothing aggregates a sentence in a topic, and the owner cannot see which lane is waiting on him. The factory key is this factory's **standing set**, reused and never re-minted; the tool resolves the *lane* from the lane's own session binding, so there is no `--lane` to mislabel and an unbound session is refused by name. Decisions are collected on the **rendered page**, never from card buttons: a tap is dropped while the target is mid-turn, and the register's own `asked_at` age is what re-surfaces a question, so a repeated topic ping is noise rather than pressure. **The URL is a CONSTANT RECORDED SLUG — read it from the register's own pointer, never assemble it from the factory slug**, because only one page directory exists and it carries every set, so a `<factory-slug>` path is a dead link for the owner. A `clarify` is a request and the lane owes the `amend`; left unamended it dead-ends the loop. **The count of open questions across all sets is the human-gate metric** — declared rather than inferred, which is why no heuristic over message traffic can substitute for it.

Canonical clause (full contract, verbs, store path): `skills/opencrabs-dev/fleet-directives.md` §Open Questions Register.

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
