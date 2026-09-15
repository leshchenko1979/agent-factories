# Add-on: `outreach` — running a campaign

**Class:** domain · **Status:** proven (AI AntiSpam) · **Defining feature:** state in a database

Take it when the factory **contacts people outside the team** and must track
replies.

---

## What it adds

**Topics.** `Outreach` (the campaign lane), plus one topic per wave or channel
when they run in parallel.

Every other pack converges on **a topic per workstream**. Outreach converges on
**a topic per channel** — because the deliverability of one channel is
independent of another's, and mixing them in one topic makes a channel-specific
problem look like a campaign-wide one.

**State — this is the defining part.** Campaign state lives in a **database**,
not in files: targets, candidates, sends, replies, state. Exactly one writer
component touches it. The repo holds code, plans and **nightly snapshots** —
never live state.

Editing a repo JSON as if it were live state is the failure this pack exists to
prevent. It has already produced double-writer duplication once: two writers,
two directions, numbers that stopped matching reality.

**Crons.** The reply sweep, as a thin trigger. Reporting goes through the
scheduler's `deliver_to` — **no send-tool calls inside a cron prompt**.

---

## Rules

- **Owner-handled is absolute.** Never close a lead the owner has personally
  replied to. Re-read the thread before drafting any close-out or courtesy
  message.
- **Anything addressed to an administrator is a draft awaiting approval**, not
  a send.
- **A cron prompt cannot be updated by a skill change** — keep crons thin so
  they cannot freeze stale law in place.
- **Name the authoritative writer** for campaign state, and keep the repo in
  the snapshot role permanently.

---

## Costs

- A database is a second state surface to operate, back up and reconcile.
- Snapshot-vs-live confusion is a standing hazard: every reader must know which
  one it is holding.
- Outreach is **irreversible in the world** — a wrong send cannot be recalled.
  This pack carries the most human-approval gates of the four for that reason.

---

## What changes if the domain is swapped

Nothing structural. Dropping `outreach` removes the campaign topic, the state
database and the approval gates, and leaves the core and the bindings
untouched.
