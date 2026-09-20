# Best practices for organizing an agent factory

**Status: v0.2 — adopted 2026-09-11.** Every practice below is marked with the
factory that already proves it. Nothing here is theory; nothing here is yet
validated across all four.

**Scope.** These are laws for **factories as machines** — they must hold for
every factory of a given shape. The peculiarities of any individual project are
that project's own concern, handled by its own `HQ`; they do not belong here.

**Two layers.** A practice is either **core** (true on any substrate) or
**binding** (mechanics that hold for one surface or one harness, in an add-on
page). P21 is the rule that keeps the two apart, and the add-on pages are where
the mechanics live.

## What a factory is

A factory is a **pairing of three things**, not one:

1. a **versioned process law** (a skill / directive file that the agent reloads),
2. a **chat surface** whose named places carry state,
3. a **repo whose issues are the task list**.

Remove the law and the agent improvises; remove the chat and the human loses
sight of the work; remove the issue board and progress becomes unfalsifiable.

---

## P1 — The process law is a file, and the file is versioned

Put the procedure in a skill/directive file that is **git-tracked and
mirrored**, never in the agent's memory or in a chat message.

- *Proven:* opencrabs-dev (SKILL.md + 4 role files, mirrored to
  `opencrabs-skill`, version 0.4.137); inferhub-watch (`skills/inferhub/SKILL.md`);
  ai-antispam (`skills/outreach-reply-sweep/SKILL.md`).
- *Prevents:* post-compaction amnesia — the agent forgetting a gate that
  exists only in a previous session's context.
- *Corollary (opencrabs-dev):* after any compaction, the **first action** is to
  reload the skill, before any ruling, spawn or status claim. The always-loaded
  brain file carries a one-line recovery anchor pointing at the skill.

## P2 — One file per role; load only the role you are

Split a large procedure by **role**, and make each session load exactly one
role file. A shared "shared facts + router" file holds what every role needs.

- *Proven:* opencrabs-dev — EDITOR / SUPERVISOR / TRIAGE / TOOLSMITH, four
  files plus a router; the compiler role was retired with a documented
  re-enable trigger rather than deleted. (*SUPERVISOR* was renamed **HQ** on
  2026-09-11 — one role, one term. The old name stays here as the record.)
- *Prevents:* every lane loading 3 000 tokens of someone else's procedure, and
  the drift that comes from one giant file being edited by everyone.

## P3 — The issue board *is* the task list

Tasks live as issues on the factory's own tracker. Title prefixes encode
kind (`hq:` process, `probe:` product, `site:` surface, `ops:` infra). Issue
bodies state goal, owner and done-criteria; status changes are comments, never
silent body rewrites.

- *Proven:* inferhub-watch — issue law, hard, with re-triage of open issues
  every cycle.
- *Prevents:* shadow trackers, and "I thought we agreed" — the board is the
  single answer to "what is in flight".
- *Variant (opencrabs-dev):* issues on the fork + a numbered **workers-ledger**
  for claims/fanouts/attribution.

## P4 — Agents are briefed by direct message to their own session, never by a chat post

The chat surface exists for the **human** to observe, supervise and archive.
Instructions reach an agent only through a direct message carrying that
session's identifier. The binding names the mechanism; the requirement is that a
brief posted to the shared chat performs **zero work** for the worker.

- *Proven:* inferhub-watch (agent-communication law) and the ops profile's
  briefing law.
- *Prevents:* the silent-no-op failure — posting a briefing to a topic looks
  like dispatch but reaches no worker, so the lane idles blind.

## P5 — One named place per work unit, and the name carries its state

Each work unit gets its own named place at spawn time, in the spawn state, and
the name flips to the closed state on close. That place is the lane: brief,
receipts and result report all land there. The binding states what a named place
is on that surface and how the name changes.

- *Proven:* inferhub-watch (topic creation + rename on close);
  opencrabs-dev (role and workstream topics, e.g. `Triage`, `Skills`).
- *Prevents:* a single shared place where a worker's brief, its evidence and
  three unrelated conversations are interleaved.

## P6 — HQ works *on* the process, not *in* it

The HQ role dispatches; it implements nothing. Every work item — including work on
the factory's own repo — goes to a lane, so HQ stays idle for the incoming
managerial work that is its job: a new finding, ruling or owner order never waits
behind a diff HQ is in the middle of writing. A factory whose `ROLES` is `HQ`
alone has no implementer, and that is a **missing lane**, not a role HQ absorbs —
create the `Worker` lane before the first work item, not after. Sub-agents are
reserved for **review** tasks, where fresh context without session bias is the
whole point.

- *Proven:* inferhub-watch (delegation law, owner order); agent-factories (owner
  order 2026-09-18 — the HQ lane was implementing its own repo, and stood up a
  `Worker` lane to delegate to).
- *Prevents:* HQ becoming the bottleneck and the single point of failure, a work
  item queueing behind HQ's own diff, and review being done by the author of the
  thing under review.

## P7 — Cron is a thin pacemaker trigger, not the worker

A scheduled job should do one thing: wake up and notify the owning session (the **Pacemaker Law**).
The substantive work runs inside that persistent session, under the current law.

- *Thinness has TWO legs, and a route satisfies only the first.* A pacemaker row is thin
  only when (a) it carries a **wake** — `deliver_to` begins with `session:`, or its prompt
  invokes a session notify — **and** (b) its prompt carries **no work order**. A session
  target is the wake leg and nothing more: it does **not** make a row thin, and a row whose
  prompt carries a work order is a violation however it is routed. The reason is the
  dual-writer shape §11 forbids, applied to an actor rather than to the append path — a
  prompt carrying a work order executes the process in the cron's own session, and the wake
  makes the lane it notifies execute the same process again. The declared wake-only form
  opens with the marker `do NOT execute any project work yourself`; a non-empty prompt that
  does not declare itself wake-only is reported, never assumed thin. That leg is TEXTUAL —
  it cannot execute the prompt — so the live behavioural check is the measurement run, not
  this text.
- *Proven:* the marker form, verified live 2026-09-20 (the instant is stated because a cron
  row is mutable) — `factory-triage-patrol`, `oc-triage-owner-digest`,
  `ai-antispam-triage-sweep`, `ai-antispam-owner-digest` and the four other declared-thin
  rows then in the enabled table. The two names this line carried before
  (`inferhub-watch-hq-hourly`, `oc-triage-hourly`) match no live row today.
- *The Pacemaker Requirement:* Every agent role that owns a periodic process (surveys,
  triage sweeps, hygiene, health checks) **must** have a scheduled pacemaker job targeting
  its persistent session UUID. Without an automated heartbeat, language models default to
  one-shot conversational stopping, and declared cadences stall the instant the human steps away.
- *Prevents:*
  1. **Process stall / amnesia:** An agent sitting idle forever awaiting human turn input.
  2. **Substantive drift:** Cron prompts freezing old law in place — a prompt cannot be
     updated by a skill change, so anything substantive inside a cron payload goes stale silently.

## P8 — Codify the vocabulary, and enforce it with a test

An `ONTOLOGY.md` lists the terms, defines them, and carries a **banned-synonyms
table**. A unit test fails the build when the code drifts.

- *Proven:* inferhub-watch — `tests/test_ontology.py` enforces it in code;
  opencrabs-dev carries the same idea as canonical terms in the skill.
- *Prevents:* the same concept under three names, which makes reports
  unreadable and grep useless.

## P9 — Mechanical gates beat prose judgment

Where a check can be a command, it is a command with a documented return code.
Human judgment is reserved for the part a command cannot decide.

- *Proven:* opencrabs-dev — ~30 `oc-*` tools with an rc contract
  (`oc-ledger`, `oc-prchecks`, `oc-order-validate`, `oc-deploy`, `oc-attrib`).
- *Prevents:* a ritual being performed "approximately" — and the same ritual
  being performed differently by each lane.

## P10 — Verification is codified in the repo's own instruction file

Each repo states, in the file an agent reads first, the exact commands that
constitute "done" — and which component to deploy when.

- *Proven:* miidas (`cd manager && python3 -m pytest tests/ -v`, per-component
  deploy scripts, an explicit refuse-stub for the all-in-one); ai-antispam
  (`pytest`, `ruff`, `uvx ty check`); inferhub-watch (unittest discovery).
- *Prevents:* "tests pass" as an unverifiable claim, and a one-service change
  redeploying the whole platform.

## P11 — One writer per state surface

For each piece of state, exactly one process writes it. Everything else reads
or snapshots.

- *Proven:* ai-antispam-outreach — Postgres `outreach` schema is the single
  operational writer (`outreach/lib/db.py`); the repo holds nightly export
  snapshots, and the retired reverse ETL was removed precisely because it
  duplicated writes.
- *Prevents:* double-writer duplication, the classic way a campaign's numbers
  stop matching reality.

## P12 — Every task leaves a trace

A ledger line, a worklog row, an issue comment — one per executed task. The log
is the analysis substrate, not paperwork.

- *Proven:* inferhub-watch (`WORKLOG.md`, "no work without a log line");
  opencrabs-dev (`workers-ledger.json` with numbered rows).
- *Prevents:* attribution disputes and unrepeatable postmortems.

## P13 — Durable state lives off the working box

Mirror the state tier (ledger, journals, receipts) to a private remote so a
lost worktree is not a lost history.

- *Proven:* opencrabs-dev — `opencrabs-dev-state`, paired with the skill mirror.
- *Prevents:* the worktree cleanup that quietly deletes the only copy of a
  ledger.

## P14 — Approval gates for irreversible acts; self-approval only for the reversible

Anything touching spend, credentials, infra or the owner's own surfaces waits
for the human. Mechanical, reversible process edits may be self-approved — with
the approval stamped in a same-turn comment so the audit trail shows it was
self-, not owner-approved.

- *Proven:* inferhub-watch (self-approval law with three guardrails).
- *Prevents:* the agent either stalling on trivia or, at the other extreme,
  silently making a costly decision on the owner's behalf.

## P15 — Never satisfy a ruling by loosening the gate

When an owner ruling conflicts with a codified threshold, change **what the
gate measures** so it passes honestly — or surface the conflict. A value that
decides pass/fail belongs to the owner.

- *Proven:* inferhub-watch, owner ruling 2026-09-11 (issues #15 → #16).
- *Prevents:* laundering a ruling into a fake certification.

## P16 — Dispatch directly; no relay hops

Work notifications go sender → resource owner. A lane does not re-send or
forward work to a third lane.

- *Proven:* ops profile directive (fleet-directives, v0.4.131).
- *Prevents:* briefs arriving paraphrased, late, or not at all.

## P17 — Claims about state need a same-turn receipt

Never report a gate verdict, a delivery, or an identifier (PR number, run id,
sha) without a tool result from the *same turn* naming it. A plan to deliver is
not a delivery.

- *Proven:* ops profile hard rule, from a documented phantom-claim incident
  family.
- *Prevents:* the most damaging failure mode of an autonomous factory — a
  confident report that nothing happened to produce.

## P18 — A surface change does not move the delivery paths with it

When the surface's addressing model changes, every delivery path — scheduled
jobs, webhooks, bound sessions — keeps pointing at the **old address**. A chat
that was already a delivery sink becomes a surface whose named places are
decorative: the reports still pile into one undifferentiated stream, now with a
place list beside it that suggests otherwise. Re-point the deliveries in the same
pass, and verify by reading the delivery table back.

- *Proven:* ai-antispam, 2026-09-11 — eleven crons all still targeted the chat
  root after the conversion; all eleven were re-pointed to the per-topic target
  and the table was re-read to confirm zero rows remained on the unthreaded one.
- *Prevents:* declaring a migration complete because the surface looks right,
  while the behaviour is unchanged.
- *Corollary:* a topic's address is the id of the message that **created** it, and
  cannot be derived from its position in a list. Create named places serially if
  you want ordered addresses; read them back either way, never predict them.

## P19 — Boundaries are named, and the meta-factory advises rather than executes

Every factory states what it **owns**, what it **consumes**, and how it talks
to each neighbour. A factory whose output is other factories — a meta-factory, a
platform team, a template repo — **converses with a member factory's HQ or its
delegate, and never does that factory's work**.

- *Proven:* owner order 2026-09-11 on this repo — the factory that produces the
  template does not write the other factories' ontologies, file their issues or
  run their tests; it talks to their HQs.
- *Prevents:* the failure that looks like helpfulness. Doing a member's work
  duplicates a lane, bypasses the member's own process law, and leaves the
  meta-factory's own work undone. The member also learns nothing, because the
  work appeared without its process producing it.
- *Corollary:* an unnamed boundary defaults to the most expensive interaction
  mode. Say which relationship it is — service, collaboration, or facilitation.

## P20 — Measure the machine, not only the output

Track at least one number that describes the **factory itself** — law freshness,
first-pass yield, rework rate — not only the work it ships.

- *Proven:* the research base in [quality-criteria.md](quality-criteria.md) —
  DORA's 2025 finding is that AI adoption **raises throughput and lowers
  stability**, and MAST found 78.7% of multi-agent failures are specification
  and coordination, not model capability.
- *Prevents:* the lucky factory — strong output, no idea why, and no warning
  when the reason stops holding.
- *Note:* do not treat the top of the scale as the target. A criterion with no
  decisions hanging off it is a dashboard, not a control.

## P21 — Separate requirements from mechanics; bind the substrate as an add-on

The **core** law states *requirements*. A **binding** add-on states the
*mechanics* that satisfy them on one product. Every factory has exactly two
bindings — a chat **surface** and an agent **harness** — and they are named
explicitly rather than assumed.

- *Proven:* this project's own restructure, 2026-09-11 (owner order). The core
  law had `session_notify`, `send_input`, Telegram topics and `gh` written into
  it. Each is true only while the surface and harness stay put — and each would
  silently become a wrong rule the day either changed, in the one place nobody
  would think to look.
- *Prevents:* a law that is correct today and quietly false tomorrow. The
  failure is invisible because nothing errors — the rule simply stops matching
  reality, and lanes follow it anyway.
- *Mechanical check:* a grep for product names across the core files. A hit that
  states **mechanics** is a leak; move it to the binding. The check is a command,
  so it can be a gate.
- *Test of the split:* you can state, for each binding, **what changes if it is
  swapped**. If you cannot write that list, the mechanics have leaked inward.

## P22 — Measure the factory on a cadence, and keep domain detail out of the number

A scored baseline is recorded at bootstrap and **re-scored on a schedule** —
a recurring job, not an intention. Factory-specific measures are welcome, but
each must name the decision it informs.

- *Proven:* this project, 2026-09-11 (owner order: adopt the rubric, measure the
  surveyed factories daily for now, revisit the cadence later).
- *Prevents:* the score that exists once, in a document nobody re-reads. Drift
  is only visible as a **diff** between dated scores.
- *Scope rule:* the score covers **effectiveness and health**, never the
  peculiarities of the domain. A member factory's product detail belongs to its
  own `HQ`; what travels up is the number and the law it implies.
- *Restraint:* a measure with no decision attached is dropped. Dashboards are
  not controls, and the top of the scale is not a goal — each level costs more
  than the last.

---

## P23 — The operator reads plain language, never the factory's shorthand

Every criterion, rule and role has a **plain name**, and that name is what any
report to the operator uses. Internal codes — `O2`, `L2`, `P19` — are handles
for cross-referencing between documents. They are not a vocabulary to speak in.

- *Proven:* this project, 2026-09-11. A status report scored the factory
  "13/52, weakest on L2 and L3". The owner's reply: *"I don't understand L1, O2
  and such — use plain language."* The report was accurate and unusable at the
  same time.
- *Prevents:* a factory that can only be understood by the people who built it.
  Shorthand is cheap for the author and expensive for the reader — and the
  reader is the one who has to act on it. A code also hides an empty criterion:
  "L2: 0" reads like a number, "vocabulary conformance: nothing exists" reads
  like a gap.
- *Test:* replace every code in the report with its plain name. If a sentence
  stops making sense, the sentence was leaning on shared memory rather than on
  what it said.
- *Boundary:* this governs the operator-facing surface only. Inside the law
  files and the ledger, stable codes are useful — short, diffable, and immune to
  rewording. Keep the codes; stop speaking in them.

---

## P24 — A defect in the substrate goes to the substrate's owner

Every factory runs **on** something — a chat surface, an agent harness, a
database, a CI system. Each of those has an owner. When an instrument is
missing, broken, or simply inadequate for what the process law requires, the
finding goes to that owner **in the same turn it is found**, as a request for
the change.

- *Proven:* this project, 2026-09-11 (owner order). Three gaps in the Telegram
  tooling — a `get_chat_info` that fails for every caller, a `list_topics` that
  sees only topics the bot has posted in, and no action at all for creating or
  renaming a topic — had been **documented in a binding** and dispatched
  nowhere. A fourth, in the harness, had been diagnosed wrongly (a stale-mtime
  theory for a guard that ignores mtime) because nobody had taken it to the
  party who could answer.
- *Prevents:* the workaround that becomes permanent. A documented gap reads like
  a known limitation, and a known limitation is a decision — one nobody made.
  Every undocumented workaround is a permanent tax on every future factory that
  inherits this template.
- *Test:* for each binding, name the owner and the route. A binding with no
  named owner leaves every future defect homeless.
- *Boundary:* a defect dispatch is not a conversation about the neighbour's
  work, and it is not a request that someone else do it. It is a finding handed
  to the party who can act, which is the same discipline as P16 applied to the
  substrate rather than to the queue.

---

## P25 — A factory's rules live in its own skill, not in the shared brain

Every session on a harness shares an **always-loaded workspace brain file**.
Writing a factory's rule there does not scope it to that factory — it binds
every other session on the box, silently.

- *Proven:* this project, 2026-09-11 (owner order). The meta-factory had been
  writing its own process rules — its boundary law, its delegate lane, its
  measurement cadence — straight into the shared `AGENTS.md`, where every
  unrelated lane on the profile reads them. The rules were not wrong; their
  *home* was.
- *Practice:* a factory's rules go in its own skill, in its own repo. The shared
  brain file carries a **one-line pointer** to that skill and nothing more. Only
  a rule that must bind every session on the harness goes in the shared file.
- *Prevents:* rule pollution that is invisible to its author. The writer sees
  their own rule working and cannot see the other factories paying for it. It
  also makes the shared file the de-facto constitution of a box whose parts have
  nothing in common.
- *Test:* before writing a rule into the shared brain, ask **"does every other
  factory on this harness need to obey this?"** If not, it belongs in the skill.
- *Boundary:* this is about *where a rule lives*, not about whether it binds.
  A factory's own skill is still law for that factory — it is versioned, and it
  reloads after compaction like any other.
- *Note:* the scoping mechanism is a property of the **harness**, so the
  mechanics — discovery paths, what a skill's frontmatter actually honours —
  belong in the harness binding (see `harness/opencrabs`), never here.

---

## P26 — A factory counts the acts that still need its operator

The rubric's machine family asks one question: *will it still land next month, with the
founder out of the loop?* A factory answers it with an **enumeration, not a yes**. Every act
that still requires the operator's hand is listed and counted, and the number falling over
time is the evidence of transferability. A factory that cannot produce the list has not
measured its independence — it has asserted it.

- *Proven:* this project, 2026-09-11. The template stated lane creation as an operator act
  and rested transferability on a mechanism that needs the operator **per work unit** — so
  the claim and the mechanism contradicted each other in the same document, and nothing
  caught it until a member factory tried to answer the question for itself.
- *Why a count and not a verdict:* "the factory survives its founder" is unfalsifiable as a
  yes/no. Every founder-dependent act is invisible until the founder leaves — the one moment
  the answer arrives too late to use. A count is checkable today, it moves in a direction,
  and every act on it is a candidate for mechanization.
- *Prevents:* an assertion of transferability standing in for its measurement. The
  founder-leaving question is the easiest one to *claim* and the only one whose failure
  cannot be observed while it still matters.
- *Practice:* at bootstrap, enumerate the acts only the operator can perform. Re-run the
  count on the measurement cadence. An act that gets mechanized leaves the list, and the
  count is the trend.
- *Boundary:* an act on the list is not automatically a defect. A deliberate approval gate
  (P14) belongs to the operator **by design** and stays on the list. The defect is an act
  that needs the operator for *mechanical* reasons nobody chose — those are the ones that
  can be mechanized, and the ones that quietly make a factory un-transferable.

---

## P27 — Automated task assignment and execution monitoring

A factory does not rely on a human to assign work or follow up on stalled tasks.
When an issue is created on the board, the factory assigns it to a persistent worker
lane, establishes a claim record, and runs an automated watchdog to monitor execution.

- *Proven:* opencrabs-dev (Triage assignment, worker ledger claim records, `oc-waiter-sweep`
  monitoring active tasks, timeouts, and stale claims).
- *Mechanism — 3 Stages:*
  1. **Automated Dispatch:** Triage scans unassigned issues on the board, performs the claim
     check (unclaimed on board, unclaimed in ledger), selects the designated persistent worker lane,
     and delivers the brief via direct session message.
  2. **Claim Registration:** An immutable ledger/claim record stamps `task_id`, `lane_id`, `state=claimed`,
     and `timestamp`.
  3. **Execution Watchdog:** A periodic trigger (cron / background sweep) checks live task status:
     - Detects idle or dead workers (no progress for *N* cycles).
     - Detects finished tasks awaiting review/verification.
     - Escalates blocked or failed tasks to HQ or triggers a retry with fresh context.
- *Prevents:* "Fire-and-forget" dispatch where an issue is filed, assigned into an unmonitored lane,
  and quietly stalls forever with no completion receipt or failure report.
- *Boundary:* The watchdog detects staleness and notifies; it does not take over the worker's
  implementation. Remediation is routed through HQ or Triage re-dispatch.

---

## P28 — Every periodic process is driven by a thin nudging cron

Every declared periodic process in a factory's process register must be driven
by an active, scheduled pacemaker job waking its session UUID. Without an
automated heartbeat trigger, conversational bias halts periodic execution the
moment human attention leaves.

- *Proven:* meta-factory — `factory-triage-patrol` and `factory-measurement-daily`, both
  carrying the declared wake-only marker; verified live 2026-09-20. A cron row is MUTABLE, so
  a named proof carries the instant it was read: the two other factories this line named
  before now carry work-order rows.
- *Mechanism:*
  1. A scheduled job acts as a thin pacemaker, sending a direct message to
     the persistent session identifier of the process owner.
  2. The process runs in that persistent session, under the current law,
     preserving lane memory and single-writer locks.
  3. No throwaway heavy runners: a job does not duplicate execution out-of-band;
     it wakes the lane that owns the process.
- *Prevents:* "Dead text" schedules where a daily or hourly cadence is declared
  in documentation but silently stalls because no mechanical trigger wakes the session.
- *Boundary:* The cron trigger initiates the turn; it does not embed mutable
  procedure in its payload. Thinness is TWO legs and a route is only the first — P7 states
  that rule in full, so it is not restated here.

---

## P29 — Every law needs an active process or mechanical gate upholding it

A rule written in a skill or process law that has no automated mechanical gate,
no CI test, and no scheduled audit process is dead text. It will be forgotten
across context compactions and ignored in production.

- *Proven:* meta-factory (vocabulary gated by `tests/test_ontology.py`, rework
  gated by `tests/test_rework.py`, single-writer state gated by
  `tests/test_single_writer.py`, template sync gated by `tests/test_template_sync.py`).
- *Mechanism:*
  1. When a new law, invariant, or constraint is codified, its author must
     simultaneously ship the mechanical gate (test script / CLI validator) or
     register the recurring audit process that enforces it.
  2. The gate must return a deterministic exit code (`0` for pass, non-zero for
     violation) and be wired into the build/verification suite (`tools/audit.py`).
  3. Un-upheld rules are flagged during periodic governance audits and either
     mechanized or struck from the law.
- *Prevents:* "Law rot" — accumulation of aspirational prose, unenforced rules,
  and dead guidelines that agents ignore.
- *Boundary:* If a property cannot be checked mechanically by a deterministic
  script, it must be assigned to an explicit human or agent audit process with a
  declared cadence.

---

## P30 — Autonomous incident remediation & template self-healing

When an incident, regression, or defect report from any factory identifies an ambiguity,
missing instruction, or absent mechanical gate in the template or process law, the
meta-factory does not narrate the fix, wait for a prompt, or ask for operator permission.
It patches the canonical template, updates the mechanical gates, logs the rework RCA,
and stamps the ledger autonomously in the same turn.

- *Proven:* meta-factory (Infra Factory bootstrap symlink incident, 2026-09-16).
- *Mechanism:*
  1. **Immediate Template Patch:** Directly update `TEMPLATE/BOOTSTRAP.md`, `TEMPLATE/roles/`,
     or `TEMPLATE/SKILL.md.tmpl` to close the instructional gap.
  2. **Mechanical Gate Hardening:** Add or sharpen the verification gate in `TEMPLATE/tools/hygiene.py`,
     `TEMPLATE/tools/audit.py`, or `TEMPLATE/tests/`.
  3. **RCA Logging:** Record the defect, root cause, resolution, and `Prevented by` gate in
     `evidence/rework.md`.
  4. **Ledger Stamp & Commit:** Stamp `evidence/ledger.jsonl`, run `tools/ledger.py verify`,
     and commit/push to `origin/main`.
- *Prevents:* "Advisory idling" — where an agent diagnoses a clear systemic defect but pauses
  to ask the operator "should I fix this?", creating unnecessary human bottleneck and stalling
  self-improvement.
- *Boundary:* Governs template hygiene and mechanical defect remediation. Substantive product
  pivot decisions or external resource allocation remain owner-gated.

---

## P31 — Every process has exactly one named owner

Every declared process has exactly one named process owner role. Shared
ownership is zero ownership.

- *Proven:* meta-factory (`docs/processes.md` assigning HQ, Triage, and Surveys
  as exclusive owners of their respective value streams).
- *Mechanism:*
  1. The process register maps each process to exactly one role card.
  2. The process owner is solely accountable for the design, health, SLA, and
     quality criteria of the process.
  3. The process owner delegates execution steps to process implementers, but
     accountability cannot be delegated or split between roles.
- *Prevents:* Ambiguous accountability, finger-pointing during stalls, and
  orphaned workflows where multiple roles assume the other is monitoring the pipeline.
- *Boundary:* Multiple implementers may execute subprocesses, but only the
  single process owner answers to the process client for the end-to-end outcome.

---

## P32 — Periodic multi-lens review of factory law and operations

Laws, instructions, and tools drift over time: rules accumulate bloat, procedures become no-ops, tools duplicate interfaces, and dead references survive context compactions.

To prevent process decay, the factory executes a periodic multi-lens review (e.g. after every $N$ shipped increments or on a regular cadence) across distinct, non-overlapping quality dimensions:

1. **Docs & Language Lenses:**
   - **Redundancy & Ontology:** Strip duplicate rules across files; enforce single-concept-single-name glossary adherence; eliminate provenance sediment (dates, historical anecdotes belong in changelogs, not live rules).
   - **LLM Efficiency & Responsibility Creep:** Minimize token weight; enforce progressive disclosure; convert prose into tables; prune subsumed rituals when composite tools ship; remove no-op rules that models follow by default.
   - **Role File Structure:** Verify each step ends with a checkable completion criterion; maintain cohesive sections; verify load paths survive context compactions.
2. **Mechanical Enforcement Lens:**
   - **Law-to-Tool Migration:** Audit every rule asking: *Is this decision a pure function of state on disk?* If yes, the rule is an unwritten tool spec. Move deterministic decisions from prose instructions into deterministic CLI scripts and gates.
3. **Tools & Interface Lenses:**
   - **Automation Gaps:** Identify recurring multi-step manual rituals that should collapse into a single CLI tool command.
   - **Interface Topology:** Identify tools whose invocations are chained; merge duplicate flags, verbs, and redundant interfaces.
   - **Tool Code Quality:** Audit shell quoting, deterministic exit codes (`0` vs `1`), pre-step journaling, and flag contracts.
4. **State & Artifacts Lenses:**
   - **Artifact Lifecycle & Deletion Safety:** Enumerate stale, retired, or orphaned files, markers, and state directories. Verify zero references across the tree before deletion.
   - **Ledger Invariants & Monotonicity:** Audit lifecycle sequences (`intake` → `claim` → `close`), verify monotonic numbering, and detect unresolved claims or phantom citations.
5. **Meta-Review Lens:**
   - **Lens Brief Integrity:** Audit the review catalog itself for scope drift, overlapping coverage, and unquoted findings. Ensure every review finding carries a verifiable locator and verbatim quote.

- *Proven:* OpenCrabs Dev Factory Duty 4+6 review rotation; meta-factory lens catalog.
- *Mechanism:* Multi-lens reviews MUST execute through **isolated adversarial sub-agents** (one sub-agent per lens or lens family). A single primary session suffers from conversational self-confirmation bias and amnesia; an isolated sub-agent enters with a fresh, unpolluted context window and an explicitly adversarial audit prompt (`tools/review.py brief <LENS>`). Findings are recorded on disk (`tools/review.py record`) and compiled into an immutable review manifest. HQ validates and codifies accepted findings in a single versioned batch.
- *Prevents:* Silent law drift, conversational self-confirmation bias, prompt token bloat, zombie artifacts, unwritten tool specs lingering as prose, and author-blindness.
- *Boundary:* Reviewers inspect and recommend; they never edit process laws directly. Only HQ codifies accepted findings.

---

## P33 — Context manifest curation across context compactions

Language models suffer severe amnesia and token truncation when context compactions occur mid-loop. While durable files and the `plan` card anchor tasks, active skills and non-core lazy tools are frequently dropped by the compactor summarizer unless explicitly instructed otherwise.

Analysis across 778 real production compactions proves that compactor engines reliably honor explicit manifest guidance in Section 10 of compaction summaries (>93% retention when guided, with 0% contradictory retention). Standardizing Section 10 manifest curation eliminates the need for complex daemon hooks or binary modifications.

The factory codifies a strict two-sided compaction protocol:

1. **Pre-Compaction Flush:** On the pre-compaction warning signal, flush in-flight variables to durable state (`session_context`, ledger, and `plan` card).
2. **Context Manifest Curation (Section 10):** Every compaction summary must emit an explicit `context-manifest` block with three strictly curated lists:
   - `active_skills`: Retain the factory's root process skill (`SKILL.md`) plus the session's active role card (e.g. `roles/worker.md` or `roles/hq.md`).
   - `discard_skills`: Explicitly discard non-active role cards and auxiliary task skills that do not apply to the current lane's role.
   - `required_tools`: Explicitly pre-activate critical operational tools (`session_notify`, `session_search`, `bash`, `read_file`, `telegram_send`) to prevent tool schema amnesia and discovery delays post-compaction.
3. **Immediate Recovery Action:** First action post-compaction is to re-read the recovery anchor (`SKILL.md`) and call `plan(operation="show_plan")` before taking any further action.

- *Proven:* OpenCrabs Dev Factory empirical production dataset (778 compactions, v0.4.196).
- *Mechanism:* Standardized Section 10 context manifest template in `SKILL.md.tmpl`, role cards (`roles/*.md`), and harness methodology (`04-harness-binding.md`).
- *Prevents:* Post-compaction skill amnesia, loss of critical role directives, tool discovery latency/thrashing, and phantom execution attempts.

---

## P34 — The mirror test: diagnose the mechanism before prescribing the counter

An agent failure has four possible generative mechanisms — epistemic, context-capacity,
behavioral, operational — and each one takes a different remedy. Calling them all
"hallucination" produces the wrong prescription: prompt-bloat for what is actually a
capacity failure, more rules for what is actually a compaction failure, or a plea to
"be careful" for what is actually a training-induced bias. The wrong remedy does not
merely fail; it consumes the attention budget that the right remedy needed.

The mirror test is the diagnostic step that prevents this. Before designing a counter,
ask the same question of yourself: do you forget? Have you ever "remembered" something
that never happened? Have you lost the thread in a flood of information? Have you lost
focus under bombardment? Every answer lands in a family, because the mechanism is the
same one — a probabilistic memory that degrades under load.

The management analogy follows, and it is the design method rather than a metaphor: a
factory is a department. Sessions message each other, ask each other questions, hand
work over, contend for shared resources, and complain upward. So the counters are the
standard instruments of managing work, re-expressed in substrate — a written checklist,
external notes, standard work, a shift handover note, peer review, single accountability,
an escalation path, a defect log with root cause, stop-the-line authority. Two of those
collapse into one mechanism here: peer review and job rotation both put a *different*
reader on the work, which is why the multi-lens review law requires an isolated session
rather than a re-read by the author.

The analogy has limits, and they are load-bearing:

- **A similar symptom is not the same cause.** A person who forgets may be tired; an
  agent that forgets has had its history summarized. Choose the remedy from the
  mechanism, not from the resemblance.
- **Self-reported confidence carries no independent information.** An agent's statement
  that it is sure is produced by the same process that produced the error. This is why
  every counter is external and mechanical — receipts, gates and durable state — and
  none of them is introspection.

- *Proven:* the mirror test is the diagnostic that produced the four-family split; the
  analogy is what maps human remedies onto substrate counters.
- *Mechanism:* `docs/methodology/01-llm-weakness-counters.md` §4–§7 (reasoning), and the
  cognitive-traps table in `AGENTS.md` (the short form an agent acts on).
- *Prevents:* misdiagnosis, prompt-bloat remedies aimed at the wrong mechanism,
  anthropomorphic remedies that ask the agent to introspect, and counters that are
  designed from how a failure looks rather than from how it is generated.

---

## P35 — A gate fixture must model the tree its tool runs in, and name the cause it actually found

A gate that runs a tool inside a throwaway tree is a *model* of the real tree, and
the model is valid only if it stages everything the tool needs to start. The
tempting shortcut — copy the tool file alone — encodes an unstated assumption of
self-containment. Nothing states it and nothing checks it, so it holds silently
until the tool gains a lawful intra-repo import. Then the fixture breaks while the
tool is correct: the gate reds on the next lawful commit, and the red reads as the
tool's fault.

- *Proven:* meta-factory #60. `tests/test_synthesize_interface.py` staged the tool
  alone; #53 clause 8 gave that tool a deliberate `import audit as _audit` (the DRY
  mandate), and the gate red on a change that was correct. Three further sites —
  `tests/test_ledger.py:208`, `:262`, `tests/test_roadmap_transition.py:88` — were
  latent, stdlib-only at the time and one import away from the same break.
- *Mechanism:*
  1. **Stage the closure, not the file.** A tool's local imports are computed
     transitively, never assumed — a shared, paired helper stages the tool and its
     closure into the tree.
  2. **Name the cause.** A fixture distinguishes "the tool could not start" (a
     non-zero exit carrying an import error) from "the tool ran and reported a
     problem", and its failure message states the cause its own evidence supports.
     A headline that blames the parser while the traceback shows an import sends the
     next reader into the wrong file.
  3. **Gate it** (P29). A deterministic check reds when a fixture stages a tool file
     into a throwaway tree without its closure, so the property is upheld rather
     than remembered.
- *Prevents:* a correct refactor read as a defect; a reader sent to repair the
  parser when the fixture was at fault; a latent site that passes until the day it
  matters and then misattributes.

---

## P36 — A surface that describes the box must be DECLARED, and the gate that guards it must be able to pass where it is copied

A self-description surface — who is on this box, how to reach them, what each one
owns — answers two different kinds of question, and mixing them is what makes it
unportable. *What exists* is readable: a live session binding, a repo on disk, a
skill file's version. *Which things the box is meant to carry* is not readable at
all — nothing on the filesystem says a factory was supposed to be there. That
second kind is a decision, and a decision that is not written down somewhere with
one writer gets written down implicitly, as a constant, in the middle of a tool.

The registry shipped that way first: six factories hardcoded across two modules,
43 fleet-shaped lines. It produced two failures that are the same failure seen
from two sides. The coverage gate read the same hardcoded set it validated, so a
check whose population is its own subject could only ever report the answer it had
been given. And the tool could not be a template artifact: a factory that copied
it inherited one box's fleet, then validated itself against that fleet and red-ed
on coverage for factories it did not have.

- *Proven:* meta-factory, the fleet registry. The gate's own held-out entry stated
  the defect and its own fix in one sentence — *"hardcodes KNOWN_FACTORY_SLUGS and
  FACTORY_CHATS for this box's six factories, so a bootstrapped factory would RED
  on coverage before it had enrolled anything. Moves into REQUIRED_GATES in the
  same change that ports TEMPLATE/registry/ and parameterizes those two sets."* The
  same family, earlier and independently found: issue **#76**, a byte-paired gate
  asserting a live-tree fact its own tree could not satisfy.
- *Mechanism:*
  1. **Split the surface by kind, and say which is which.** Declared facts live in
     a manifest with one named writer; derived facts are computed from live state
     at read time. Then never restate a declared fact as a constant beside its own
     declaration — a second copy of a list is the defect, not the constant, and
     Python's last-definition-wins makes the copy that *loses* the silent one.
  2. **Parameterise the gates in the same change, not after.** A gate held out of
     the required set *"until it is parameterised"* is a law with no upholding
     mechanism (P29) — dead text that reads as a live check, and a template that
     ships a toolchain whose own gate it does not run.
  3. **Prove the equivalence before deleting the old source.** Compare every
     derived collection against the live module and report the diff per name. The
     one mismatch this found was ordering — and the ordering was a real precedence
     the manifest now owns rather than an accident.
  4. **An undeclared root is a REFUSAL, never an empty result.** `Path("").glob(…)`
     returns `[]`, and every predicate built on it reads that as *nothing to check*
     and passes: the exact shape of a check that cannot fail. The caller is told
     the reason, and the reason is carried out to the report.
  5. **A fixture that must genuinely differ from the tree it ships beside is not a
     pair.** It carries a `.tmpl` suffix and lives outside the shared path, which
     is what makes the difference visible instead of silent. A fixture whose own
     body names one box's factory cannot be copied byte-identically into a
     template: the template's own `validate` reds on the file it was told to copy.
- *Prevents:* a coverage gate that can only report the answer it was handed; a
  template that ships one box's fleet to every factory that copies it; an optional
  gate that is never actually required, so the law it states has no mechanism; and
  a fixture that reds the tree it was ported into.

---

## P37 — A check that judges a commit reads the index; a check that judges live state says so

A check is only as sound as the surface it reads, and two surfaces are routinely
confused. When a commit lands, what it carries is the **index** — the staged tree —
and nothing else. The working tree beside it may hold anything at all: a fix that
was made but never staged, a half-finished edit, another lane's in-flight work. A
check that reads the working tree therefore answers a different question from the
one it was asked, and answers it GREEN.

The measured case is issue **#92**. `tests/test_template_sync.py` has always caught
a declared byte pair changed on one side only, but only *after* the commit, so the
defect landed on `main` and sat there until an audit noticed. The obvious repair —
run that same gate from a `pre-commit` hook — is **unsound**: it reads the working
tree, so a lane that staged one side and fixed the other side on disk without
staging it gets a PASS and the one-sided commit goes through. That is a green light
on the exact defect the hook exists to catch. The hook that shipped reads
`git diff --cached`, and its gate proves the difference with synthetic probes
rather than asserting it.

- *Mechanism:*
  1. **A check that judges a COMMIT reads the INDEX, or a recorded artifact.**
     Staged paths, never the working tree; a committed ledger row, never the file
     on disk. If the index cannot be read, the check says so and refuses — a check
     that silently falls back to the working tree is a false green, not a degraded
     one.
  2. **A check that judges LIVE state says so, and stays out of the correctness
     pass.** Live state — a running process, a cron table, a session binding, a
     remote board — cannot be read in a bootstrapped factory or in a detached
     worktree, so a reader of it is a *runner*, P29's process arm: it prints what
     it did and did not read, states the instant it read, and refuses a verdict
     when its source is unreachable. What belongs in the correctness pass is the
     offline gate over that runner's logic, which can pass anywhere. Enrolling the
     live read itself is the worse failure of the two, because it reds every tree
     that legitimately lacks that state.
  3. **A generator rendering a committed artifact must be runnable from the
     index.** A rendered artifact is a function of its source, and if the
     generator reads the working tree then a dirty tree cancels the drift — the
     render reports a difference that is not in the commit, or hides one that is.
     Reading the index makes the output a function of the commit and nothing else.
- *Proven:* issue **#92** — the unsound naive hook, and the index-reading one that
  shipped in its place; the same class earlier in **#80** and `c3b60d5`, where the
  pair guard fired only after the bytes had landed. The live-state arm is
  `tools/patrol_host_state.py`: a runner that exits 2 with no verdict on an
  unreadable board and is invoked on a cadence, while the correctness pass carries
  only `tests/test_patrol_host_state.py`, the offline gate over its logic.
- *Prevents:* a gate that passes a one-sided commit because the working tree
  happened to agree; a live-state check enrolled in the offline suite, red-ing
  every bootstrapped factory; a render whose output depends on uncommitted bytes.

---

## The minimum viable factory

If you are standing up factory number five, this is the smallest set that
already works:

1. One repo. Issues enabled. `AGENTS.md` stating the verification commands.
2. One chat surface, bound explicitly, with an `HQ` topic and one topic per work unit.
3. One agent harness, bound explicitly.
4. One skill file: mission, issue law, delegation law, agent-communication law.
5. One `ONTOLOGY.md` with a banned-synonyms table.
6. One recurring job: a thin trigger that notifies the `HQ` session.
7. One ledger: a file that gets a row per task.
8. One baseline score, re-scored on a cadence.

Items 2 and 3 are the bindings — they are not optional, only *swappable*.
Everything else — role splits, CLI tooling, self-approval — is earned by
volume, not adopted on day one.