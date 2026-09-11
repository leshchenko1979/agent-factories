# Add-ons

The core template is deliberately minimal — the InferHub Watch shape: one
`HQ` topic, a thin cron, an issue board. That is enough for a factory that
watches something and reports.

Most factories do more than that. An **add-on** is a domain pack: the extra
topics, roles, gates, crons and rules a factory needs when it ships code, runs
an outreach campaign, or operates a platform for other people.

An add-on says *what structure the domain needs*. It never says what the
domain's work actually is.

---

## The four known add-ons

Each is extracted from a factory that runs it today, not invented.

| Add-on | Take it when | Proven by |
|---|---|---|
| [`ship`](#ship--delivering-code) | The factory's output is code that gets merged and released | OpenCrabs development |
| [`outreach`](#outreach--running-a-campaign) | The factory contacts people outside the team and must track replies | AI AntiSpam |
| [`watch`](#watch--monitoring-something) | The factory's job is periodic probing and ranking | InferHub Watch |
| [`platform`](#platform--operating-for-other-people) | The factory runs a service for clients, not just for itself | Miidas |

They compose. A platform factory that also ships code takes `platform` +
`ship`. A factory that watches its own product takes `watch` + `ship`.

---

## `ship` — delivering code

**Adds topics.** `Skills` (where the process law itself is edited), `Harvest`
(upstream intake), plus per-workstream topics as they appear.

**Adds roles.** `Triage` (intake, routing, enforcement — the load-bearing
partner to `HQ`), `Editor` (a lane that owns one workstream and edits code),
`Toolsmith` (owns the `oc-*` tooling surface), `Carrier` (owns the merge and
ship chain).

**Adds gates.** Where prose would say "make sure it is correct", a command
with a return code says it instead: a validator that refuses a malformed
trailer, a checker that refuses a feature-loss diff, a PR gate that refuses an
unverified sha. Aim for a tool per ritual, and a ritual that can be run by any
lane and produce the same answer.

**Adds state.** A numbered **workers-ledger**: claims, fan-outs, attribution.
The issue board says *what* is in flight; the ledger says *who claimed it and
under what authority*.

**Adds rules.**

- The upstream repo is never pinged; PR feedback stays on GitHub.
- A gate verdict requires a same-turn receipt — no verdict from memory.
- After any compaction, reload the skill before any ruling or status claim.
- Smoke verification has four legs: lineage, identity, CI gate, live probe.

**Costs.** This is the heaviest add-on. It buys correctness on work that is
expensive to get wrong, and it is overkill for a factory whose output is a
report.

---

## `outreach` — running a campaign

**Adds topics.** `Outreach` (the campaign lane), plus one topic per wave or
channel when they run in parallel.

**Adds state — this is the defining part.** Campaign state lives in a
**database**, not in files: targets, candidates, sends, replies, state. Exactly
one writer component touches it. The repo holds code, plans and nightly
snapshots — never live state. Editing a repo JSON as if it were live state is
the failure this add-on exists to prevent; it produced double-writer
duplication once already.

**Adds crons.** The reply sweep, as a thin trigger. Reporting goes through the
scheduler's `deliver_to` — no send-tool calls inside a cron prompt.

**Adds rules.**

- **Owner-handled is absolute.** Never close a lead the owner has personally
  replied to. Re-read the thread before drafting any close-out.
- Anything addressed to an administrator is a **draft awaiting approval**, not
  a send.
- A cron prompt cannot be updated by a skill change — keep crons thin so they
  cannot freeze stale law in place.

**Costs.** Every factory in this list converges on a chat topic per workstream;
outreach converges on a topic per *channel*, because the deliverability of one
channel is independent of another's.

---

## `watch` — monitoring something

**Adds almost nothing, on purpose.** This is the add-on you take to keep a
factory small.

**Shape.** Exactly one standing topic (`HQ`). Every work unit gets its own
topic named `Worker — #N <title>`, renamed to `Done — #N <title>` on close and
**left in place** — the forum doubles as the archive. One thin hourly cron that
does exactly one thing: notify the owning session.

**Adds rules.**

- The issue board is the task list, hard: open issues are re-triaged every
  cycle, and the issue title prefix encodes kind (`probe:`, `site:`, `ops:`,
  `hq:`).
- Findings are ranked by a stated basis (e.g. quality per unit cost), and the
  basis itself is a documented decision, not a number someone liked.

**Costs.** Nothing structural — but it does not scale to a factory where
multiple lanes edit the same artifact. Take `ship` for that.

---

## `platform` — operating for other people

**Adds topics.** One topic per surface the platform actually has (`Landing`,
`CDP`, `Agent runtime`, `Manager`), plus a hard boundary: **client-facing
groups are not factory topics.** The factory chat is for building the platform;
the client's own group is the product.

**Adds artifacts.** `docs/adr/` — decisions recorded as ADRs, because a
platform accumulates decisions that outlive the session that made them. An
`ONTOLOGY.md` carrying platform terms (slot, warm pool, claim, convert,
deploy, decommission) with a banned-synonyms table, so the manager code, the
ADRs and the reports do not drift apart.

**Adds the one rule this add-on exists for:** **name the authoritative state
writer.** Multi-tenant platforms accumulate state in several places at once —
a runtime registry on disk, a client record in markdown, a provisioning log.
Exactly one of them is *authoritative* for "who is a client", and the skill
must say which. Ambiguity here is the single most expensive defect class in a
platform factory, because every report inherits it.

**Adds lifecycle gates.** Provisioning and decommissioning are procedures with
steps, not ad-hoc sequences — a client must be able to be removed cleanly, and
that procedure must be written before the second client exists.

---

## Writing a new add-on

An add-on is a page with six headings: **take it when · adds topics · adds
roles · adds state · adds gates · adds rules · costs**. Derive it from a
factory that already runs it; if no factory runs it, mark it
`status: unproven` and say what would prove it.

The test of a good add-on: a factory that takes it can point at each thing it
added and say which failure it prevents. If it cannot, the add-on is
decoration.
