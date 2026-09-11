# Quality criteria for an agent factory

**Status: v0.2 — ADOPTED 2026-09-11 (owner order).** The 13 criteria and the
0–4 scale are the standing measurement system; factory-specific measures will be
added on top. Each criterion is either derived from published research or
extracted from a factory that runs today. The scale is still young, the
thresholds are hypotheses, and the first factory scored against it is the one
that wrote it — see
[the self-audit](#worked-example-this-factory-scored-against-itself).

**Cadence:** the surveyed factories are scored **daily** for now, relaxing once
the numbers are stable. See [how this rubric is used](#how-this-rubric-is-used).

**Scope:** this measures **effectiveness and health** — the factory as a machine.
It does not measure, and must not adjudicate, any factory's own domain work.

---

## Two products, two sets of measures

A factory makes two things. They need separate measures, and most measurement
covers only the first:

| Product | Question it answers | Who feels it |
|---|---|---|
| **The output** | Did the work land, and does it stay landed? | The customer of the factory |
| **The machine** | Will it still land next month, with the founder out of the loop? | Whoever inherits it |

A factory with strong output and a broken machine is a **lucky** factory: it
works because one person is compensating somewhere, and it stops working when
they stop. Output metrics alone cannot see that, which is why the rubric below
scores both.

---

## What the research says

Nothing in this rubric is invented. Each family of criteria comes from a body
of work that already measured the same problem in a different setting.

| Source | What it contributes |
|---|---|
| **DORA** — *dora.dev*, 2025 State of AI-Assisted Software Development | Splits delivery into **throughput** (change lead time, deployment frequency, failed deployment recovery time) and **instability** (change fail rate, deployment rework rate). Its headline finding for AI: adoption **raises throughput and lowers stability** — acceleration exposes downstream weakness unless testing, version control and feedback loops are already mature. |
| **Google Cloud** — *The KPIs that actually matter for production AI agents* | Agent-specific measures: tool-selection accuracy, argument-hallucination rate, plan adherence, consistency. **Cost per successful task**, never cost per task — plain cost rewards an agent that gives up fast and wrong. Acceptance rate and *implicit rejection* (the revert, not the thumbs-down) as the real adoption signal. **Time-to-verify**: if human review takes longer than doing the task, the automation is net negative. |
| **MAP** — *Measuring Agents in Production*, arXiv 2512.04123 | Field data from 86 deployed systems: 68% execute ≤10 steps before human intervention, 74% rely on human-in-the-loop evaluation, and **reliability is the top development bottleneck — solved by system design, not by a better model**. Coding agents are the rare case with fast automatic verification (compiler + tests). |
| **MAST** — *Why Do Multi-Agent LLM Systems Fail?*, arXiv 2503.13657 | The failure taxonomy: **specification 41.8%, inter-agent misalignment 36.9%, verification 21.3%**. Verifiers that check only the surface pass broken work — the paper's example is a generated chess program that compiles and still accepts illegal moves. Multi-level verification is required. |
| **Anthropic** — *Building Effective Agents*, *Demystifying Evals*, *How we built our multi-agent research system* | Use the simplest pattern that works. The orchestrator must delegate with an **objective, an output format, tool guidance and clear boundaries** — vague briefs make subagents duplicate each other. Graders should be code-based where possible, calibrated against humans, and **resistant to being gamed**. Read the transcripts. |
| **CNCF** — *Platform Engineering Maturity Model* | The four-level progression used below (Provisional → Operational → Scalable → Optimizing), across five aspects. And an explicit warning: **the top level is not a goal in itself** — each level costs more than the last. |
| **Team Topologies** — cognitive load, *Thinnest Viable Platform* | Cognitive load is the design constraint, not an afterthought. A platform should be the **thinnest** one that works. Trade Me measured success as *time to first hello world* — three weeks down to one day. |
| **Flow metrics** — Little's Law, first-pass yield | `average cycle time ≈ WIP ÷ throughput`. Flow efficiency in software runs 15–25%: **the queue, not the work, is where the time goes**. First-pass yield is the share of items accepted without being kicked back. |

Two of these findings shape the whole rubric:

1. **AI raises throughput and lowers stability.** A factory that only measures
   speed will get faster and less trustworthy at the same time. O2 and M2 exist
   to catch that.
2. **The failures are organisational, not model-level.** 78.7% of MAST's
   failures are specification and coordination. Buying a better model does not
   fix a factory with vague briefs and no verifier.

---

## The scale

Each criterion is scored 0–4. Thirteen criteria, so the maximum is **52**.

| Score | Level | What it means |
|---|---|---|
| **0** | Absent | Nothing exists. It has never been done. |
| **1** | Ad-hoc | It happens — when someone remembers, and differently each time. |
| **2** | Defined | Written down, and followed by convention. Not measured. |
| **3** | Measured | A number exists, produced mechanically, without a human counting. |
| **4** | Self-correcting | The number has a threshold, and crossing it triggers action on its own. |

| Band | Score | Reading |
|---|---|---|
| **Provisional** | 0–25% | The factory runs on the founder's head. It works; it is not transferable. |
| **Operational** | 26–50% | Written down. A stranger could follow it. Nothing is measured. |
| **Scalable** | 51–75% | Measured. You can tell whether it is getting better. |
| **Optimizing** | 76–100% | Thresholds fire by themselves. The factory corrects without being asked. |

**Do not treat 4 as the target.** Most factories should stop at *Defined* on
criteria their volume does not justify measuring. A criterion with no decisions
hanging off it is a dashboard, not a control.

---

## F1 — Output: does the work land?

| # | Criterion | Measure | Prevents |
|---|---|---|---|
| **O1** | **Throughput** | Items reaching done per week; change lead time from task opened to landed | A factory that is busy but not shipping — activity read as progress |
| **O2** | **Stability** | Change fail rate (share of changes needing immediate intervention) **and** rework rate (share of work that is unplanned fixes) | "Fast and broken". DORA's 2025 finding: AI adoption lifts throughput and drops stability. Speed with no stability measure is a factory running up a debt it cannot see |
| **O3** | **Cost per successful task** | Total spend ÷ tasks that reached the intended outcome — never spend ÷ tasks attempted | Cheap failures looking efficient. An agent that gives up fast and wrong is cheap per task and expensive per outcome |

*Evidence:* DORA's five metrics are the standard here, with rework rate the 2024
addition that finally made "how much of our work is repair?" visible.
Cost-per-success is Google Cloud's KPI framework, which is blunt about the
trap: an agent costing $0.10 per run that fails half the time really costs
$0.20 per success.

---

## F2 — Machine: is the factory sound?

| # | Criterion | Measure | Prevents |
|---|---|---|---|
| **M1** | **Specification clarity** | Share of briefs that two independent domain experts would grade pass/fail **identically** | The single largest failure class. A task that two experts cannot grade the same way cannot be graded by a verifier either — and ambiguity in the spec becomes noise in every metric downstream |
| **M2** | **Verification depth — and its record** | Verification at more than one level (unit → integration → acceptance); grader resistant to being gamed; every task leaves a trace a third party can re-check without asking the author | Superficial verifiers that pass broken work. MAST's example: a chess program that compiles, passes review, and accepts illegal moves. Also the phantom report — a confident claim with nothing behind it |
| **M3** | **Coordination integrity** | Brief completeness (objective, output format, tool access, boundaries); share of handoffs delivered **directly** rather than relayed; count of tasks derailed by an unstated assumption | Duplicated and dropped work. MAST's second-largest class is agents proceeding on wrong assumptions instead of asking, and agents ignoring each other's input |
| **M4** | **Boundary clarity** | Written statement of what this factory **owns**, what it **consumes**, and the interaction mode for each neighbour | Two factories doing the same work; or a meta-layer quietly doing a member's work while its own goes undone. Also the reverse: a factory that will not act on anything outside its own repo |

*Evidence:* MAST (arXiv 2503.13657) found explicit verifiers reduce failures but
are no silver bullet — the verifiers were performing surface checks while the
output was broken. M1 comes from Anthropic's eval-design rule: a task is only
well-formed when two domain experts would reach the same verdict, and a task
that cannot be passed by an agent following the instructions is a broken task,
not an incapable agent. M4 is Team Topologies' interaction modes — a
relationship that is not named defaults to the most expensive one.

---

## F3 — Law: does the process stay true?

| # | Criterion | Measure | Prevents |
|---|---|---|---|
| **L1** | **Law freshness** | The process law is versioned; every session reloads it after a context compaction; a check flags a lane running under a stale version | Ruling from a stale memory of the law — worse than not ruling, because it looks authoritative. A factory whose law is older than its code is running yesterday's process with today's confidence |
| **L2** | **Vocabulary conformance** | An ontology with a banned-synonyms table, **and a test that fails the build when the code drifts from it** | The same concept under three names. Reports become unreadable, grep stops working, and every new lane re-derives the vocabulary |
| **L3** | **Single-writer state** | The authoritative writer is **named** for every state surface; every other path is read-only or a snapshot | Double-writer duplication — the classic way a factory's numbers stop matching reality, and the hardest defect to notice because both writers look correct in isolation |

*Evidence:* L1 is the opencrabs-dev post-compaction law plus its drift check —
the skill is gone from context after compaction, so the always-loaded file
carries a recovery anchor pointing at it. L2 is inferhub-watch's
`tests/test_ontology.py`, which turns the ontology from a document into a gate.
L3 is ai-antispam's outreach schema: one writer module, the repo holding only
nightly snapshots, and a retired reverse-ETL path removed precisely because it
was a second writer.

---

## F4 — Stewardship: is it sustainable?

| # | Criterion | Measure | Prevents |
|---|---|---|---|
| **S1** | **Human cognitive load** | How much of the factory the operator must hold in their head. Proxy measures: time to first useful output for a new task; the count of facts only the operator knows | The factory that works only while its founder watches. This is the failure mode the whole product exists to prevent — and the one that is invisible in every output metric |
| **S2** | **Recoverability** | Time from a bad change to restored service — and whether the operator is required in that path | A single bad merge that needs the owner to unpick it. A factory that cannot recover without its founder is not autonomous, it is supervised |
| **S3** | **Improvement loop** | Every failure becomes a rule, a test, or a gate — and the change is checked against the next occurrence | A factory that makes the same mistake quarterly, with the same surprise each time. Distinct from L1: the law can be fresh and still never learn anything |

*Evidence:* S1 is Team Topologies' thinnest-viable-platform principle, with
Trade Me's *time to first hello world* as the measured version (three weeks to
one day). S2 is DORA's failed deployment recovery time, promoted to the
throughput group precisely because fast recovery is what keeps delivery moving.
S3 is Anthropic's eval practice: failures become test cases, capability evals
start at a low pass rate to give a hill to climb, and regression evals protect
what already works.

---

## What this rubric deliberately does not measure

- **Individual lanes or agents.** Outcomes are read as properties of the system
  people and agents work inside, not as scores on a person. The moment a metric
  becomes a target it stops measuring what it was meant to (Goodhart), and
  velocity is the clearest casualty — it climbs while cycle time gets worse.
- **Agent count, message count, token count.** All three are activity. O1 and
  O3 already capture what they are proxies for.
- **The sophistication of the machinery.** A wiki page can be a platform. The
  thinnest structure that carries the work is the correct one; more machinery
  is a cost until a criterion says otherwise.
- **Anything the factory has no decisions hanging off.** A measure nobody acts
  on is decoration.

---

## Worked example: this factory scored against itself

The rule this repo states is that the principles apply to the factory that
wrote them. So: scored honestly, by the same rubric, on what is actually true
of **this** factory (this repo + this session + this chat surface), not of the
parent infrastructure it borrows from. Scoring inherited capability as one's
own is the most flattering way to make a rubric useless.

| # | Criterion | Score | Why |
|---|---|---|---|
| O1 | Throughput | 1 | Work lands, but nothing counts it. No rate, no lead-time record |
| O2 | Stability | 0 | No record of rework, no change-fail measure. Nothing exists |
| O3 | Cost per successful task | 0 | No cost tracking of any kind |
| M1 | Specification clarity | 1 | Briefs are prose. Detailed, but never tested against the two-experts rule |
| M2 | Verification depth + record | 2 | Strong inherited law (receipts, read-back-immune proofs) applied by hand; no mechanical gate in this repo |
| M3 | Coordination integrity | 2 | Direct dispatch is codified and briefs carry deliverables. The delivery path itself failed once and needed a second hop |
| M4 | Boundary clarity | 1 | Was **zero** until this turn. The owner had to state it: the meta-factory converses with member HQs, it does not do their work |
| L1 | Law freshness | 1 | The docs exist; they carry no version and no reload trigger for this factory itself |
| L2 | Vocabulary conformance | 0 | This repo ships an `ONTOLOGY.md` template and has never instantiated one for itself |
| L3 | Single-writer state | 0 | No ledger, no state surface. The factory has no memory outside the chat |
| S1 | Human cognitive load | 1 | The owner asked twice about one open question and had to correct the product framing |
| S2 | Recoverability | 2 | Versioned and pushed to a remote; no documented recovery path |
| S3 | Improvement loop | 2 | Failures do become rules — this document is the loop firing. Nothing checks whether a failure recurs |

**Total: 13 / 52 = 25% — Provisional.** By family:

| Family | Score | Reading |
|---|---|---|
| F1 Output | 1 / 12 (8%) | Nothing about output is measured |
| F2 Machine | 6 / 16 (38%) | The strongest family — inherited rules, applied by hand |
| F3 Law | 1 / 12 (8%) | The law is written but not versioned, not enforced, not recorded |
| F4 Stewardship | 5 / 12 (42%) | Version control and a habit of writing rules down |

**The finding:** the factory that writes the rulebook is the weakest factory in
the set, and it fails on exactly the criteria it prescribes to others. It
carries no ontology of its own (L2), keeps no state of its own (L3), measures
none of its own output (F1), and until this turn had no written boundary (M4).

That is the useful part of the exercise, and it is the argument for the rubric
existing: **a factory can be articulate about process and still be Provisional.**
Prose about practice is not practice. The four factories this repo surveys score
higher on F1 and F3 than the meta-layer that describes them.

---

## How this rubric is used

**Adopted 2026-09-11** (owner order). Three standing decisions:

| Decision | Detail |
|---|---|
| **The rubric is the measurement system** | Factories are scored against it, 0–4 per criterion |
| **The surveyed factories are measured on a cadence** | **Daily, for now** — deliberately conservative; the cadence is expected to relax once the numbers are stable and their variance is known |
| **Factory-specific measures will be added** | The 13 criteria are the floor, not the ceiling. A factory's own domain adds measures — each one naming the decision it informs |

**Where the cadence lives.** The recurring measurement is a **scheduled job** —
in the OpenCrabs harness binding, that is
[`cron_manage`](addons/harness/opencrabs.md#periodic-processes--cron_manage),
and it is the harness binding, not this document, that carries the mechanism.

**What the daily run produces.** A dated score per factory, recorded in the
repo. Consecutive scores diff into a **trend**; a single score is an opinion.

**What it must not produce.** Detail about a factory's own project. The score
covers **effectiveness and health** — how well the machine works, not what it is
working on. Domain specifics belong to that factory's `HQ`, which has the
context to act on them. A measurement process that starts adjudicating product
decisions has stopped measuring and started meddling.

---

## Open questions for discussion

1. **Should the meta-factory be held to this rubric at all, or is it a
   different kind of thing?** It has no product output to measure with O1–O3 in
   the same way. Candidate answer: its output is *factories bootstrapped*, and
   its O3 is the cost of each bootstrap — but that is a guess.
2. **Which criteria are mandatory at bootstrap, and which are earned by
   volume?** The minimal-factory list in `best-practices.md` implies L1, L2, L3
   and M1 are day-one; O2 and O3 are almost certainly not.
3. **Who scores the factory?** Self-scoring has an obvious bias. A peer HQ, or
   the operator, would produce a different number — and the gap between the two
   is itself worth measuring.
4. **Is 0–4 the right scale?** Four levels mirror the CNCF model, but a factory
   with nothing measured cannot distinguish "defined but unmeasured" from
   "ad-hoc" reliably.
5. **What is the failure threshold?** DORA-style, a factory below *Operational*
   on F3 should probably not be given work that others depend on. That is a
   policy, and policy belongs to the owner.

---

## Sources

- DORA, *Software delivery performance metrics* — https://dora.dev/guides/dora-metrics/
- DORA 2025, *State of AI-Assisted Software Development* — https://cloud.google.com/blog/products/ai-machine-learning/announcing-the-2025-dora-report
- Google Cloud, *The KPIs that actually matter for production AI agents* — https://cloud.google.com/transform/the-kpis-that-actually-matter-for-production-ai-agents
- Pan et al., *Measuring Agents in Production* — https://arxiv.org/abs/2512.04123
- Cemri et al., *Why Do Multi-Agent LLM Systems Fail?* (MAST) — https://arxiv.org/abs/2503.13657
- Anthropic, *Building Effective AI Agents* — https://www.anthropic.com/engineering/building-effective-agents
- Anthropic, *Demystifying evals for AI agents* — https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- Anthropic, *How we built our multi-agent research system* — https://www.anthropic.com/engineering/multi-agent-research-system
- CNCF TAG App Delivery, *Platform Engineering Maturity Model* — https://tag-app-delivery.cncf.io/whitepapers/platform-eng-maturity-model/
- Team Topologies, *Thinnest Viable Platform* — https://teamtopologies.com/key-concepts-content/what-is-a-thinnest-viable-platform-tvp

