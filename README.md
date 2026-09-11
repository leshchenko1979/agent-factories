# Agent Factories

**A template for creating a new agent factory** — plus the best practices it
encodes, and add-ons for the domains a factory works in.

An *agent factory* is the structure that turns a repository plus a chat group
into a self-driving delivery line: AI agents do the work, a human supervises
through the chat, and the process itself is a versioned file rather than
something living in someone's head.

This repo is the **product**: the thing you copy when you want to stand up a
new factory, and the rulebook that says why each piece is there.

## What you get

| Piece | Path | What it is |
|---|---|---|
| **Template** | [`TEMPLATE/`](TEMPLATE/) | The instantiable skeleton — bootstrap checklist, process-law skeleton, ontology, role cards |
| **Best practices** | [docs/best-practices.md](docs/best-practices.md) | The laws the template encodes, each with the factory that proves it |
| **Quality criteria** | [docs/quality-criteria.md](docs/quality-criteria.md) | The adopted measurement system: 13 criteria in 4 families, scored 0–4, re-scored on a cadence — with this factory scored against itself |
| **Add-ons** | [docs/addons.md](docs/addons.md) | Two mandatory **bindings** (chat surface, agent harness) plus optional **domain** packs |
| **Product spec** | [docs/product.md](docs/product.md) | What the product is, who it is for, what v1 covers, and what it deliberately does not |
| **Evidence** | [evidence/](evidence/) | The four real factories, surveyed — the receipts behind every practice |

## Scope — what this project is not about

This is the meta-layer. Its subject is **the factory as a machine**: how
effective it is, how healthy it is, and which laws hold for every factory of a
given shape.

It does **not** concern itself with the peculiarities of any individual project.
A factory's own product decisions, backlog, clients and code are that factory's
`HQ`'s business — not this project's. This project converses with a member
factory's HQ or that HQ's delegate, and never does a member's work.

That boundary is load-bearing. A meta-layer that absorbs domain detail becomes a
second, worse `HQ` for every factory at once — and stops producing the laws it
exists to produce.

## Start here

1. Read [docs/product.md](docs/product.md) — what you are building.
2. Follow [`TEMPLATE/BOOTSTRAP.md`](TEMPLATE/BOOTSTRAP.md) — the ordered checklist that takes an empty directory to a running factory.
3. Take the two **bindings**, then pick your **domain** add-ons from [docs/addons.md](docs/addons.md).
4. Keep [docs/best-practices.md](docs/best-practices.md) open — it is the normative rulebook.
5. Score the result against [docs/quality-criteria.md](docs/quality-criteria.md) — a factory with no numbers is Provisional by definition — and schedule the re-score.

## The thesis

A factory is **three things paired**, not one:

```
process law  ×  chat surface  ×  issue board
```

- the **law** is a versioned file the agent reloads after every compaction;
- the **chat** carries state in its topic names — one topic per work unit;
- the **board** is the task list — issues, not a shadow tracker.

Remove the law and the agent improvises. Remove the chat and the human loses
sight of the work. Remove the board and progress becomes unfalsifiable.

## Reference implementations

The template is extracted from four factories that run today. They are not
examples — they are the evidence, and each one proves a different part of the
pattern:

| Factory | What it proves |
|---|---|
| **OpenCrabs development** | Mechanical gates, role split, ledger, carrier/ship chain — the full-weight instance |
| **InferHub Watch** | The cleanest minimal instance: one `HQ` topic, everything else a work unit that closes by rename |
| **Miidas** | The multi-tenant platform case: ADRs as decisions, client state, a factory chat created from scratch |
| **AI AntiSpam** | The router skill and the outreach domain — cron re-pointing, campaign state in a database |

Per-factory detail: [evidence/factories.md](evidence/factories.md).

## This project's own surface

The meta-factory runs on the same pattern it prescribes, so its own surface is
recorded here. Group **Factories**, a Telegram forum:

| Topic | `thread_id` | Who speaks | What belongs |
|---|---|---|---|
| `HQ` | 21 | The HQ lane | Analysis, rulings, owner conversation |
| `Delegate` | 68 | The delegate lane | Member-factory comms — dispatches to member HQs, and their answers |
| `Triage` | 20 | — | Intake and routing |
| `Surveys` | 19 | — | Survey and measurement work |

`HQ` is the analysis surface and the owner's conversation. Member-factory
traffic does **not** belong there: that is what `Delegate` is for, and keeping
the two apart is a boundary rule rather than a preference. A meta-factory that
routes member traffic through its own analysis lane has re-created the exact
confusion the boundary exists to prevent.

Topic ids are read back from live state, never predicted. The ids above are a
record of one such read; any delivery targeting one re-confirms it first.

### Member-factory lanes

Who the delegate lane talks to. Resolved from live state on 2026-09-11 — a lane
is addressed by the **full session id read back in the same turn**, because a
remembered prefix is how a message lands in the wrong session.

| Member factory | HQ lane session | Their surface |
|---|---|---|
| OpenCrabs dev | `d72bd52d-42aa-4dbd-ac99-5b5300770019` | Crabs Kanban Board, topic `OC DEV HQ` |
| InferHub Watch | `359fe71b-c7a1-420b-b856-acfb49939a7b` | Inferhub watch, topic `Auditor` |
| AI AntiSpam | `acc3fa9b-cefa-4e35-bf87-422696e558f0` | ai-antispam, group root |
| Miidas | **none exists** | `Miidas Factory` has no session binding |

**Miidas is the open gap.** Its own skill states that no lane has been
dispatched from that factory yet and that its topic map is a scaffold. Standing
up its `HQ` lane is **that factory's own work**, not this one's — until it
exists the delegate cannot reach Miidas, and that is a finding rather than a
defect to fix from here.

The topic names above are the live titles, not the ones a factory's own law
would lead you to expect: InferHub Watch's HQ topic is named `Auditor` in
practice. Record the read, not the expectation.

## Status

**v0.1 — the template is written, no factory has been created from it yet.**
The first factory bootstrapped with it will be the validation. Until then the
practices are proven by their origin factories, not by the template.
