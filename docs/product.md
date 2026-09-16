# Product: the four products of the meta-factory

**What this is.** Four complementary products produced and maintained by this meta-factory to build and operate **Autonomously Self-Improving Factories (ASIF)**:
1. **The Factory Template & Add-on Packs:** A working structure an operator (or an agent) copies
   and instantiates to create a new autonomously self-improving factory, plus the rules that make it work
   and the domain add-ons that adapt it to a particular kind of work.
2. **The Consulting Practice & Advisories:** An active process-consultancy to the surveyed
   member factories — diagnosing operational bottlenecks, surfacing stopped or
   low-yield processes, recommending hardened gates and practices, and helping their
   HQs measurably increase their efficiency and autonomy (throughput, cadence, yield, waste reduction, self-improvement).
3. **The Factory Growth & Maturity Map:** A blueprint mapping how an autonomously self-improving factory evolves across
   throughput stages (Stage 0 to Stage 4), predicting the exact roadblocks that emerge at each scale
   and specifying the transition mechanics to cross them.
4. **The Empirical Insights Story (Public Narrative):** A battle-tested engineering narrative
   drawn directly from live fleet telemetry (lead time reality, atomic concurrency locks, self-auditing quality loops, autonomous RSI)
   published for technical operators and communities.

**What it is not.** Not a framework, not a runtime, not a library. There is no
code to import. The template product is a set of files plus an ordered procedure,
and it is complete when a new factory can be stood up in an afternoon without the
operator re-deriving any of the decisions. The consulting practice advises and
diagnoses — it never seizes the tools or writes code in a member factory's repository.

---

## Product-to-Process Mapping

Every product is produced and maintained by recurring operational processes in this factory:

| Product | Primary Producing Process | Process Owner | Process Client | Client Value Delivered | Key Artifacts |
|---|---|---|---|---|---|
| **1. Factory Template & Add-ons** | Process 1: Work Delivery Pipeline *(hardened by P2 & P3)* | HQ | New Factory Operators & Fleet Developers | Bootstraps production-ready autonomous factory with built-in quality gates | `TEMPLATE/`, `docs/addons/` |
| **2. Consulting Practice & Advisories** | Process 3: Operational Measurement & Consulting | Surveys | Member Factory HQs | Objective bottleneck visibility, reduced lead time, higher operational yield | `evidence/scores/<date>.md`, advisories via Delegate |
| **3. Factory Growth & Maturity Map** | Process 1 (Work Delivery) *(calibrated by P3)* | HQ | Factory Owners & Technical Leadership | Predicts scale roadblocks (Stages 0–4) and provides transition mechanics | `docs/growth-stages.md` |
| **4. Empirical Insights Story** | Process 3 (Measurement) *(harvesting fleet telemetry)* | Surveys / HQ | Public Engineering Audience & Operators | Battle-tested engineering case studies for building in public | `evidence/insights.jsonl`, `docs/stories/` |

---

## What this project does and does not concern itself with

This is a meta-factory. Its subject is **the factory as a machine** — how
effective it is, how healthy it is, and which laws hold for every factory of a
given shape.

| In scope | Out of scope |
|---|---|
| Factory effectiveness and health, measured | The domain work a factory does |
| Process consulting to member HQs to raise efficiency | Doing member implementation or backlog work |
| Template laws that hold for **every** factory | One factory's product decisions |
| Add-on laws that hold for **every** factory of that kind | One factory's backlog, clients or code |
| The mechanics of a surface or harness, as a swappable binding | Any given factory's configuration of them |

The **peculiarities of an individual project are not this project's concern.**
They belong to that factory's own `HQ`, which has the context to decide them.
This project acts as a consultant to a member factory's HQ or that HQ's delegate —
it diagnoses, advises, and recommends improvements, but it never does a member's
work, and it never files a member's issues.

That boundary is not politeness. A meta-factory that absorbs domain detail stops
being a meta-factory: it becomes a second, worse `HQ` for every factory at once,
and its own output — the laws and objective consulting — goes unwritten.

---

## The problem it solves

Every factory here was built by hand, and each one re-derived the same
decisions: where the process law lives, how work units map to topics, how
agents get briefed, what happens after a context compaction. Four factories
meant four derivations and four sets of drift.

The template exists so the fifth factory starts from a decision that is already
made, and so the parts that genuinely differ by domain are isolated into
**add-ons** instead of smeared through the core.

---

## Who uses it

| User | How they use it |
|---|---|
| **The operator** (human, owns the factory) | Reads `BOOTSTRAP.md`, answers the fill-in questions, approves each step. Supervises through the chat surface afterwards. |
| **The bootstrap agent** (an AI session) | Executes `BOOTSTRAP.md` step by step: creates the repo, the forum, the topics, writes the law files from the skeletons, spawns the first lane. |
| **Lane agents** (workers inside the new factory) | Never read this repo. They load the generated skill of their own factory, exactly as they would in any of the four. |

---

## The three legs

```
   process law            chat surface             issue board
   ───────────            ────────────             ───────────
   versioned file,        one topic per            repo issues are
   reloaded after         work unit, renamed       the task list —
   compaction             on close                 not a shadow tracker
```

The template produces all three. A factory missing any leg is not a factory;
it is a repo some agent edits sometimes.

---

## What the template produces

Instantiating it yields, in the new factory:

| Artifact | Where | Purpose |
|---|---|---|
| Process law | skill file (mirrored to a repo) | The procedure lanes reload |
| Role cards | one file per role | Each session loads only its own role |
| Ontology | `ONTOLOGY.md` | Canonical terms + banned synonyms |
| Repo law | `AGENTS.md` in the factory repo | Engineering and execution rules |
| Chat surface | forum group with topics | HQ, Triage, domain topics, work-unit topics |
| Issue board | factory repo, issues enabled | The task list |
| Cron triggers | thin jobs | Each does one thing: notify the owner session |
| First lane | a spawned session in its own topic | Proves the surface carries a brief |

---

## Fill-in variables

The template is parameterised. Bootstrapping a factory means answering these,
once, and substituting them through the skeletons:

| Variable | Meaning | Example |
|---|---|---|
| `FACTORY` | Short name, used in topic titles and repo names | `inferhub-watch` |
| `PURPOSE` | One sentence: what this factory delivers | Daily probes + value ranking of InferHub routes |
| `REPO` | The factory's own repo, owner/name | `leshchenko1979/inferhub-watch` |
| `CHAT` | Forum group title + chat id | `Inferhub watch`, `-1004379632866` |
| `SURFACE` / `SURFACE_SLUG` | The chat surface binding | `Telegram forums` / `telegram-forums` |
| `HARNESS` / `HARNESS_SLUG` | The agent runtime binding | `OpenCrabs` / `opencrabs` |
| `ROLES` | Which roles exist (HQ, Triage, workers, carrier) | `HQ` only for a minimal factory |
| `DOMAINS` | Domain topics in the middle of the spine | `Landing`, `Bot`, `Outreach` |
| `ADDONS` | **Domain** packs to apply (bindings are separate and mandatory) | `watch` |
| `GATES` | Commands that decide, where a command can | `oc-*` tool set, or a repo test suite |

`SURFACE` and `HARNESS` are not optional. A factory always runs on some surface
and some harness; naming them is what keeps their mechanics in the add-on layer
instead of welded through the core law.

---

## Scope

**v1 covers**

- The core skeleton: bootstrap checklist, process-law skeleton, ontology, repo
  law, topic spec, role cards.
- The minimal viable factory — the InferHub Watch shape: one `HQ` topic, work
  units that close by rename, a thin cron, an issue board.
- Add-on selection: what to add for code-shipping, outreach, monitoring, and
  multi-tenant platform work.

**v1 does not cover**

- An executable installer. `BOOTSTRAP.md` is executed by an agent today; a
  `factory-new` command that automates it is a later tier, not this one.
- Factory migration. Converting an existing, unstructured project into a
  factory is a different (and messier) procedure — see
  [evidence/gaps.md](../evidence/gaps.md) for what that looked like here.
- Domain content. An add-on says *which topics, roles, gates and crons* a
  domain needs — never what the domain's work actually is.

---

## Success test

The template works when a new factory, bootstrapped from it by an agent that
has never read this repo before, can:

1. state its own purpose and canonical vocabulary from its own files;
2. receive a task as a GitHub issue and be briefed on it through a topic;
3. close that task by renaming the topic, with the evidence in the topic;
4. do all of the above after a context compaction, without the operator
   re-explaining the process.

Point 4 is the real test. Points 1–3 can be faked by a good session; point 4
is what the process law is for.
