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

The HQ role dispatches; it does not implement work it has dispatched. Hands-on
work goes to a lane — unless `ROLES` is `HQ` alone, where there is no lane and
HQ is the factory's implementer. Sub-agents are reserved for **review** tasks,
where fresh context without session bias is the whole point.

- *Proven:* inferhub-watch (delegation law, owner order).
- *Prevents:* HQ becoming the bottleneck and the single point of
  failure, and review being done by the author of the thing under review.

## P7 — Cron is a thin pacemaker trigger, not the worker

A scheduled job should do one thing: wake up and notify the owning session (the **Pacemaker Law**).
The substantive work runs inside that persistent session, under the current law.

- *Proven:* inferhub-watch — `inferhub-watch-hq-hourly` runs exactly one thin trigger
  notifying the HQ session UUID and stops; opencrabs-dev — `oc-triage-hourly`.
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

- *Proven:* meta-factory (daily measurement pacemaker), inferhub-watch
  (HQ hourly pacemaker), miidas (HQ daily pacemaker).
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
  procedure in its payload.

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