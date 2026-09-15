# Add-on: `watch` — monitoring something

**Class:** domain · **Status:** proven (InferHub Watch) · **Cost:** almost nothing

Take it when the factory's job is **periodic probing and ranking**.

This is the pack you take to keep a factory small — and the shape the core
template is extracted from. If you are unsure which pack applies, start here.

---

## What it adds

**Almost nothing, on purpose.** That is the whole design: `watch` is the
demonstration that the core plus two bindings is already a working factory.

**Shape.** Exactly one standing topic (`HQ`). Every work unit gets its own
topic named `Worker — #N <title>`, renamed to `Done — #N <title>` on close and
**left in place** — the forum doubles as the archive.

One thin cron that does exactly one thing: notify the owning session.

---

## Rules

- **The issue board is the task list, hard.** Open issues are re-triaged every
  cycle; nothing lives outside the board.
- **The issue title prefix encodes kind** (`probe:`, `site:`, `ops:`, `hq:`).
- **Findings are ranked by a stated basis** — e.g. quality per unit cost — and
  the basis itself is a documented decision, not a number someone liked.
- **No work without a log line.** Every task leaves a trace; the log is the
  analysis substrate, not paperwork.

---

## Costs

Nothing structural. But note the limit: this pack **does not scale to a factory
where multiple lanes edit the same artifact**. There is no ledger, no claim
discipline and no merge gate here. Take `ship` for that.

---

## What changes if the domain is swapped

Nothing structural. This pack adds no roles, no gates and no extra state — so
dropping it leaves the core and the bindings entirely untouched, which is
exactly why it is the right starting point for a new factory.
