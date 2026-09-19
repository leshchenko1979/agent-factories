---
name: meta-factory
description: Process law for the agent-factories meta-factory (/root/agent-factories). Load before ANY meta-factory task - surveying a member factory, deriving a template law, writing to TEMPLATE/ or docs/, scoring a factory, briefing the Delegate lane, or answering an owner question about the factory project. (/meta-factory, agent-factories, meta-factory, factory template, quality criteria)
version: 0.1.3
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
- **Verification is scoped by load-bearing.** Verify what you will act on or report; accept
  receipted facts you will not. In a cross-lane pass, the value is the **contradiction** check.
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
  itself and is safe either way. Measured precedent: n=303's two parenthetical `REPAIR NOTE`
  sentences displaced its own canonical `cost_usd=2.7719 tokens_out=9956523 turns=1 …`, which
  was canonical when the row was written. n=303 is **not** backfilled — the law above bars it
  — and stands as the measured precedent (#91, ruling n=572 PART 3).

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
| `evidence/rework.md` | the rework entries this factory has **recorded** — each defect, regression and law rollback it wrote down, with its root cause and what now prevents it | `Triage`, at the close that resolved it | read-only; `tests/test_rework.py` gates each entry's completeness, the `Subject` column's vocabulary, the table's contiguity, every rate claim's form, and that every determinate `Subject` resolves to a real closed work unit (each unresolvable one reported by name); the share of closes DECLARING a rework disposition is PRINTED, never gated — never the completeness of the set |
| `evidence/scores/<date>.md` | one measurement run, one file per run | the daily measurement job (`Surveys`) | read-only |
| `evidence/*.md` | survey receipts and dated evidence | the survey run | read-only |
| `ONTOLOGY.md` | the canonical vocabulary | `HQ` | read-only, gated by `tests/test_ontology.py` |
| `docs/processes.md` | the canonical process register | `HQ` | read-only |
| `skills/meta-factory/SKILL.md` | this law | `HQ` | read-only |

**A close and its board are coupled in three directions, and each one has its own mechanism.** (1) A close ROW must name the board state it observed — gated by `tests/test_close_board_recorded.py`. That gate cannot call `gh`: the mechanical suite runs offline and against a tree, not a live board, so the settling lane records the board state it saw and the gate asserts the record exists. (2) A close must be preceded by its own intake and claim — gated by `tools/ledger.py verify`, which reads a subject's rows as a sequence and names the subject and the missing leg. (3) A CLOSED board item must have a close row — **no offline gate can reach this direction**, and each mechanism says why in its own code: a gate cannot call `gh` (1 above), and `verify` builds its sequence check by iterating close rows, so a subject with no close row is never visited. Its upholding mechanism is therefore a PROCESS: a standing patrol cross-reads the board against the ledger. P29 admits a process as readily as a gate — a rule needs one or the other, not specifically a gate.

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

**A row is retired by naming it, never by deleting it.** The single-writer lock above binds the code, not the artifact: a writer that never calls `tools/ledger.py` takes no lock and leaves no trace, and once its removal is *committed* the append guard compares working against committed, goes self-consistent, and every gate reads green over a ledger that has lost committed history. So no row identity — the `(n, ts, event, actor, subject)` tuple a row is known by — is ever removed: a row that must not stand is retired by appending a row that names it, and the original stays. `tests/test_ledger_no_shrink.py` walks the committed history and reports every commit whose diff removes a row identity, which is why the check is a set difference over identities and not a text search — the one measured case removes a row whose surviving neighbours still contain every word it carried. Its exemptions are factory data in `docs/ledger-no-shrink-exemptions.json`, keyed by full sha and never inline in the gate, and every run prints them so "clean" and "excused" are never the same output; a gate that examines zero commits fails loudly rather than passing vacuously.

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

**A ledger subject names an issue or describes the work, and the form says which.** A subject that names a board issue is written `#N` — the hash, the digits, and nothing else. `#N` is the strict form every subject-keyed predicate resolves through, so a near-miss is not a malformed reference to those predicates: it is not a reference at all, and the row silently leaves their population without ever being reported as wrong. A subject that names no issue is a descriptive stem naming the work in words (`pickaxe-attribution-trap`), and a clause label extending a reference (`#31-close-receipt`) is descriptive, not a reference — a mechanism that cannot tell those two apart from a broken reference will either miss the defect or fire on the law. The number a subject names is not bound to this factory's own board: a row may cite another repository's issue, so the form is what is codified and no gate may read `#N` as naming this factory's board without saying so. The gate that upholds this is `tests/test_subject_form.py`, and the instant it governs from is declared in `docs/ledger-invariants.json` like every other ledger invariant.

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
