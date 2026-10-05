# Add-on: `ship` — delivering code

**Class:** domain · **Status:** proven (OpenCrabs development) · **Cost:** the heaviest pack

Take it when the factory's output is **code that gets merged and released**.

---

## What it adds

**Topics.** `Skills` (where the process law itself is edited), `Harvest`
(upstream intake), plus per-workstream topics as they appear.

**Roles.**

| Role | Owns |
|---|---|
| `Triage` | Intake, routing, enforcement — the load-bearing partner to `HQ` |
| `Editor` | A lane that owns one workstream and edits code |
| `Toolsmith` | The tooling surface (this factory's own instruments) |
| `Carrier` | The merge and ship chain |

**Gates.** Where prose would say "make sure it is correct", a command with a
return code says it instead: a validator that refuses a malformed trailer, a
checker that refuses a feature-loss diff, a gate that refuses an unverified sha.

Aim for **a tool per ritual**, so any lane can run it and get the same answer.
This is the pack's defining idea: correctness on work that is expensive to get
wrong is bought with mechanics, not with care.

**State.** A numbered **workers-ledger**: claims, fan-outs, attribution. The
issue board says *what* is in flight; the ledger says *who claimed it and under
what authority*. Two questions, two stores — merging them loses the second.

---

## Rules

- The upstream repository is never pinged; PR feedback stays on the PR.
- **A gate verdict requires a same-turn receipt.** A job name proves run
  identity, never outcome.
- **Identifiers are never hand-assembled** — issue numbers, run ids, shas. Copy
  the full value from live output.
- After any compaction, reload the law before any ruling or status claim.
- Smoke verification has **four legs**: lineage, identity, CI gate, and a live
  behavioural probe (or a stated structural N/A).
- **Never satisfy a ruling by loosening the gate.** Change what the gate
  measures so it passes honestly, or surface the conflict.

---

## Costs

This pack buys correctness and pays in ceremony: four roles, a ledger, a set of
validators, and a merge chain with human gates. It is **overkill for a factory
whose output is a report** — take `watch` instead.

---

## What changes if the domain is swapped

Nothing structural. A domain pack is additive: dropping `ship` removes the
roles, gates and ledger above, and leaves the core and the bindings untouched.
