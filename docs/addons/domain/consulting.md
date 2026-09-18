# Add-on: `consulting` — advising other factories

**Class:** domain · **Status:** proven (the meta-factory) · **Cost:** two lanes beyond the core set

Take it when the factory's output is **advice to other factories** — surveying their
process, diagnosing what has stopped, and recommending what to fix — rather than a
product of its own.

---

## What it adds

**Lanes.** A consulting factory needs two lanes the core set does not carry: one that
runs the surveys, and one that owns the conversation with each surveyed factory.

**The template ships no cards for them, and that is deliberate.** The core set is the
four cards in `roles/`, and `tools/ledger.py` is copied byte-identically into every
factory — so a lane only one factory has cannot live in a value that must match
everywhere. A factory taking this pack therefore does two things at bootstrap:

1. **Declares the lanes** in `tools/actors.txt`, one role per line, beside the tool.
   See `BOOTSTRAP.md`, *"Declare any lane the core set does not have."* A lane that is
   not declared cannot record its rows — the ledger refuses it, which is the difference
   between a lane and a name the ledger will not hear from.
2. **Writes its own cards** for them, in the same shape as the four shipped ones.

A factory that does neither has lanes its law names and its ledger refuses. Declare
them, or do not take this pack.

**League tables.** Cross-factory comparison — first-pass yield, lead time, queue dwell —
so that a member can see its own number against its peers rather than against a target
someone invented.

**A survey cadence.** A survey with no schedule is an anecdote. The pack is only worth
taking if the survey is on a pacemaker.

---

## Rules

- **Advise, never implement.** The factory converses with a member's HQ or that HQ's
  delegate. It does not edit a member's repo, file its issues, or run its tests. A
  consultant advises the leadership; they do not seize the tools.
- **Report the number with its predicate.** A rate without its denominator is not a
  measurement, and a bare `0.0` reads as "no failures" when the truth is "no linkage".
  Every measure travels with the definition that produced it.
- **A reading taken before the gates exist carries no signal.** Early numbers are a
  direction, not a verdict — say so in the same breath as the number.
- **The member owns its decisions.** A recommendation is not a ruling. When the member
  declines, that is the member's call and it is recorded, not relitigated.

---

## Costs

Two lanes, a survey cadence, and the discipline to keep the two apart. The recurring
trap is a consultant lane that starts *doing* the member's work because it can see how —
that duplicates the member's own lane, bypasses their process law, and leaves this
factory's own work undone.

The second cost is honesty about what travels. What crosses the boundary is the
*machine* — does the process hold, is the law fresh, is the state single-writer — never
the member's product decisions, backlog or code.

---

## What changes if the domain is swapped

Drop the pack and the following evaporate: both lanes, the survey cadence, the league
tables, the measurement procedure, and the two-way conversation with each member HQ.

What survives is the core: work units, the ledger, the gates, the role set. Nothing in
this pack is a requirement of a factory as such — a factory that builds a product needs
none of it. That is the test of whether this pack has leaked: if any rule above is still
true after you drop it, the rule belongs in the core law, not here.

---

## Artifacts — created by the factory, never shipped by the template

| Artifact | Who produces it | Why it cannot be template payload |
|---|---|---|
| `docs/measurement-procedure.md` | **the factory creates it** | It is the factory's own survey method. The template ships no method: the procedure is the pack's main work, not a file it carries |
| `evidence/scores/<date>.md` | **the factory creates it** | Measurement *output*. One file per run, dated, and meaningless in a tree that has not run |
| league tables | **the factory creates them** | They compare members against each other; a template has no members |

The template ships this page and nothing else. A pack that claimed to ship a factory's
scores would be describing a different factory's history as if it were payload.
