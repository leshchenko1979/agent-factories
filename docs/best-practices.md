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
2. a **chat surface** whose topics carry state in their names,
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
  re-enable trigger rather than deleted.
- *Prevents:* every lane loading 3 000 tokens of someone else's procedure, and
  the drift that comes from one giant file being edited by everyone.

## P3 — The issue board *is* the task list

Tasks live as GitHub issues on the factory's own repo. Title prefixes encode
kind (`hq:` process, `probe:` product, `site:` surface, `ops:` infra). Issue
bodies state goal, owner and done-criteria; status changes are comments, never
silent body rewrites.

- *Proven:* inferhub-watch — issue law, hard, with re-triage of open issues
  every cycle.
- *Prevents:* shadow trackers, and "I thought we agreed" — the board is the
  single answer to "what is in flight".
- *Variant (opencrabs-dev):* issues on the fork + a numbered **workers-ledger**
  for claims/fanouts/attribution.

## P4 — Agents are briefed with `session_notify`, never with a chat post

Telegram topics exist for the **human** to observe, supervise and archive.
Instructions reach an agent only through a direct session notification carrying
the target session UUID.

- *Proven:* inferhub-watch (agent-communication law) and the ops profile's
  briefing law.
- *Prevents:* the silent-no-op failure — posting a briefing to a topic looks
  like dispatch but reaches no worker, so the lane idles blind.

## P5 — One topic per work unit, named with its state

Each worker gets its own forum topic at spawn time, named
`Worker — #N <title>`, flipped to `Done — #N <title>` on close. The topic is
the lane: brief, receipts and result report all land there.

- *Proven:* inferhub-watch (topic creation + rename on close);
  opencrabs-dev (role and workstream topics, e.g. `Triage`, `Skills`).
- *Prevents:* a single General topic where a worker's brief, its evidence and
  three unrelated conversations are interleaved.

## P6 — HQ works *on* the process, not *in* it

A supervisor role dispatches; it does not implement. Hands-on work goes to a
lane. Sub-agents are reserved for **review** tasks, where fresh context without
session bias is the whole point.

- *Proven:* inferhub-watch (delegation law, owner order).
- *Prevents:* the supervisor becoming the bottleneck and the single point of
  failure, and review being done by the author of the thing under review.

## P7 — Cron is a thin trigger, not the worker

A scheduled job should do one thing: notify the owning session. The work runs
in that session, under the current law.

- *Proven:* inferhub-watch — `inferhub-watch-hq-hourly` runs exactly one
  `session notify` command and stops.
- *Prevents:* cron prompts freezing old law in place — a prompt cannot be
  updated by a skill change, so anything substantive inside it goes stale
  silently.

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

## P18 — Converting a group to a forum does not move anything

`channels.ToggleForum` gives the chat topics and parks every existing message in
`General`. Every delivery path — crons, webhooks, bound sessions — keeps
pointing at the **chat root**, so a group that was already a delivery sink
becomes a forum whose topics are decorative: the reports still pile into one
undifferentiated stream, now with a topic list beside it that suggests
otherwise. Re-point the deliveries in the same pass, and verify by reading the
delivery table back.

- *Proven:* ai-antispam, 2026-09-11 — eleven crons all still targeted
  `telegram:-1003993000918` after the conversion; all eleven were re-pointed to
  `telegram:-1003993000918:<thread_id>` and the table was re-read to confirm
  zero rows remained on the unthreaded target.
- *Prevents:* declaring a migration complete because the surface looks right,
  while the behaviour is unchanged.
- *Corollary:* a topic id is the id of the topic's **create-service message**
  and cannot be derived from the topic's position in a list. Create topics
  serially if you want ordered ids; read them back either way, never predict
  them.

## P19 — Boundaries are named, and the meta-layer advises rather than executes

Every factory states what it **owns**, what it **consumes**, and how it talks
to each neighbour. A factory whose output is other factories — a meta-layer, a
platform team, a template repo — **converses with a member factory's HQ or its
delegate, and never does that factory's work**.

- *Proven:* owner order 2026-09-11 on this repo — the factory that produces the
  template does not write the other factories' ontologies, file their issues or
  run their tests; it talks to their HQs.
- *Prevents:* the failure that looks like helpfulness. Doing a member's work
  duplicates a lane, bypasses the member's own process law, and leaves the
  meta-layer's own work undone. The member also learns nothing, because the
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
