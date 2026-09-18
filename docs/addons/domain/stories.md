# Add-on: `stories` — turning operations into published case studies

**Class:** domain · **Status:** proven (the meta-factory) · **Cost:** an insights ledger and an editorial pass

Take it when the factory's operational history is worth publishing — when what it learned
building the thing is the thing an outside audience wants.

---

## What it adds

**An insights ledger.** A single-writer append log of empirical findings: what was
believed, what happened, what the number actually was. Entries are dated and carry their
own evidence, so a claim in a published story can be traced back to the run that produced
it.

**A narrative generator.** A pass that compiles ledger entries into case studies —
battle-tested accounts of queue dwell time, lock contention, self-auditing loops — rather
than marketing prose.

**A public-facing document tree.** Where the finished pieces live, separate from the
process law, so an outside reader has something to read that is not the rulebook.

---

## Rules

- **Every published claim traces to a ledger entry.** A case study is an argument about
  what happened; if the number in it cannot be re-read from the ledger, it is an anecdote
  and it does not ship.
- **Write the finding when it is found.** An insight reconstructed at publication time is
  a memory of a memory, and the detail that made it interesting is the part that goes
  missing.
- **Publish the defect, not only the fix.** The failure is the transferable part. A story
  that reports only the working end state teaches nothing a reader can apply.
- **The ledger is single-writer.** One append path, lock held across the read-modify-write,
  exactly as the state ledger works. Two writers silently produce two row 41s.

---

## Costs

An append-only ledger that must actually be appended to — a ledger nobody writes is worse
than none, because it looks like evidence — plus an editorial pass on every piece. The
recurring failure is a narrative generator that runs on an empty ledger and produces
confident prose about nothing.

---

## What changes if the domain is swapped

Drop the pack and the ledger, the generator and the document tree go with it. Nothing in
the core depends on them: the factory's state ledger and its gates are unaffected, and a
factory that never publishes anything runs exactly as well.

What does not survive is the *traceability* habit — that a published claim is backed by a
recorded run. If the factory keeps that habit without the pack, it is keeping a core idea
and should say so in its own law.

---

## Artifacts — created by the factory, never shipped by the template

| Artifact | Who produces it | Why it cannot be template payload |
|---|---|---|
| `tools/insights.py` | **the factory creates it** | A single-writer append tool with a lock. It is factory tooling, not payload — the template ships the *state* ledger tool because every factory needs one; this one is specific to a factory that publishes |
| `evidence/insights.jsonl` | **the factory creates it** | Accumulated findings. A ledger of discoveries a factory never made is a file of another factory's history |
| `docs/stories/` | **the factory creates it** | The published pieces themselves, written by the factory that lived them |

The template ships this page. Everything the pack describes is work the taking factory
does — which is the honest shape of a domain pack: it tells you what structure to build,
not what content to inherit.
