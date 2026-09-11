# Add-on: `platform` — operating for other people

**Class:** domain · **Status:** proven (Miidas) · **Defining rule:** name the authoritative writer

Take it when the factory **runs a service for clients**, not just for itself.

---

## What it adds

**Topics.** One topic per surface the platform actually has (`Landing`, `CDP`,
`Agent runtime`, `Manager`).

Plus a hard boundary: **client-facing groups are not factory topics.** The
factory chat is for *building* the platform; the client's own group is the
*product*. Mixing them puts customer conversation into the team's work surface
and makes every report inherit a stranger's context.

**Artifacts.**

- `docs/adr/` — decisions recorded as ADRs, because a platform accumulates
  decisions that outlive the session that made them.
- `ONTOLOGY.md` — platform terms (slot, warm pool, claim, convert, deploy,
  decommission) with a banned-synonyms table, so the manager code, the ADRs and
  the reports do not drift apart.

**Lifecycle gates.** Provisioning and decommissioning are **procedures with
steps**, not ad-hoc sequences. A client must be able to be removed cleanly, and
that procedure must be written **before the second client exists**.

---

## The rule this pack exists for

> **Name the authoritative state writer.**

Multi-tenant platforms accumulate state in several places at once — a runtime
registry on disk, a client record in markdown, a provisioning log. Exactly one
of them is *authoritative* for "who is a client", and the law must say which.

Ambiguity here is the **single most expensive defect class in a platform
factory**, because every report inherits it. Two components each believing they
are authoritative produces a system that is wrong in a way no test catches —
both are internally consistent, and they disagree.

The same rule applies to the factory's own state: the platform enforces
one-writer-per-state on its objects, and the factory should keep its own ledger
of object statuses. A platform factory that governs tenancy strictly and its own
work loosely has the discipline backwards.

---

## Rules

- Client groups are not factory topics.
- Decommissioning is written down before the second client, not after the first
  surprise.
- ADRs are the decision record; a decision that lives only in a chat is not
  recorded.
- Every platform term is in the ontology, with its banned synonyms.

---

## Costs

- **ADR upkeep** is a real, recurring cost — and an unindexed ADR directory is
  worse than none, because it looks like a record.
- **The ontology is load-bearing** here in a way it is not in the other packs:
  drift between code, ADRs and reports is a correctness bug, not a style issue.
- **Client-facing surface** means the blast radius of a defect extends outside
  the team.

---

## What changes if the domain is swapped

Nothing structural. Dropping `platform` removes the per-surface topics, the ADR
directory, the ontology obligation and the lifecycle gates, and leaves the core
and the bindings untouched.
