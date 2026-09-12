# The process register — a law needs the processes that uphold it

**Status: proposed, not law.** Nothing in this file is in force. It is written
from an owner question of 2026-09-12 and waits on the owner's ruling.

> *"A law needs to have processes that uphold it, and most probably also an
> auditor of those processes. It's the auditor who decides whether the factory
> is efficient or not. One other thing that the factory must keep track of is its
> own processes, and these have to be audited. How does it fit into our current
> structure?"*

---

## 1. What the question actually names

Three different things, and today the structure holds only two of them.

| Element | What it is | Example here |
|---|---|---|
| **Law** | The rules, versioned | `skills/meta-factory/SKILL.md` |
| **Process** | A recurring act that holds a rule up | the four gates, the daily measurement run, the ledger sequence check |
| **Audit** | Reading whether the processes ran | *does not exist* |

The rubric measures **properties** — is the law fresh, is state single-writer, is
throughput measured. A property is a *state*. What the question names is a
*process*: the act that keeps the state true. The two are not the same thing, and
only one of them is measured today.

---

## 2. What exists today

| Element | Exists | Where | Gap |
|---|---|---|---|
| Law | Yes | `SKILL.md`, `TEMPLATE/SKILL.md.tmpl` | — |
| Processes | Partly | four gates in `tests/`, `tools/ledger.py verify`, the daily job | They exist as **code**, not as a **named list** with an owner and a cadence |
| The factory tracking its own processes | **No** | — | Nothing records that a process ran |
| An audit of the processes | **No** | — | Nothing asks whether they still run |
| A verdict on efficiency | Partly | the score and its band | The band is assigned by the factory's own score |

---

## 3. The gap, with evidence

**`score` is a declared event type with zero rows.** The ledger's closed event set
is `genesis, intake, claim, dispatch, close, score, ruling`. In the live ledger of
2026-09-12 the counts are: genesis 1, intake 6, claim 5, dispatch 1, close 7,
ruling 3 — and **score 0**. The daily measurement run writes
`evidence/scores/<date>.md` and leaves no state transition behind. The one
process this factory runs on a schedule is invisible in the surface built to
record state.

**This is the third instance of one shape in this repo.** A check that reads only
what is *present* cannot see an *absence*:

| Instance | The check | What it could not see |
|---|---|---|
| **#10** | the ledger gate | a close with no intake — a **missing row** |
| **#12** | the rework gate | a table split by a blank line — a **missing contiguity** |
| *today* | the vocabulary gate | the per-term banned synonyms — a **missing enforcement** |

That third row is new and was found while writing this file. `ONTOLOGY.md`
declares banned synonyms in two places: the enforced `## Banned synonyms` table
(3 terms) and the "Not" column of the term table, which gives a synonym for
`Surveys`, one for `Delegate`, and 17 more. `tests/test_ontology.py` parses
**only the first**. The second is documentation nobody can violate, which is
exactly what the vocabulary criterion says an ontology must not be.

A process that has stopped running is the same shape once more: it produces no
output, and no output is indistinguishable from nothing wrong.

---

## 4. The proposal

Three parts. The first two make the third possible.

```mermaid
flowchart TD
    A["Law<br/>states the rules"] --> B["Process register<br/>names each process, its owner,<br/>its cadence, the criterion it upholds"]
    B --> C["Each process runs<br/>and appends a run row"]
    C --> D["Ledger<br/>dated state transitions"]
    D --> E["Surveys lane reads the register<br/>against the run rows"]
    E --> F{"Did every process<br/>run at its cadence?"}
    F -->|yes| G["Criterion stands"]
    F -->|no| H["Finding: a process has stopped"]
    H --> I["Triage files it as work"]
```

### 4.1 A process register — `docs/processes.md`

One row per recurring process: its **owner** (a lane), its **cadence**, the
**criterion it upholds**, and the **evidence a run leaves**. The register is what
makes "the factory keeps track of its own processes" a thing a reader can check
rather than a claim.

### 4.2 Run rows — every execution leaves a state transition

A process that runs appends a row. `score` already exists for the measurement run
and has never been used; the others need one more event type (`run`) in the
closed set. A missed cadence then becomes **visible as a gap in the sequence**,
which is what the ledger gate was built to read.

### 4.3 The verdict — self-score stays the engine, the band moves

Today the factory scores itself *and* the band follows its own score. The
question says the audit decides efficiency. Both can hold if the two jobs are
split:

| Job | Who | Cadence | Output |
|---|---|---|---|
| Self-score | the factory | continuous / daily | the improvement trigger — gaps become work |
| The band | the `Surveys` lane | periodic | the verdict on efficiency |

A score is a measurement and a factory may take its own. A **band** is a verdict,
and a verdict issued by the party being judged is not one. This keeps the owner's
2026-09-11 ruling — self-judgment is the engine of self-improvement — and adds
the audit on top rather than replacing it.

### 4.4 The audit is itself a process

The `Surveys` lane's own runs belong in the same register and leave the same run
rows. That is the whole point of putting the register in the repo: the audit of
the audit is not a special case, it is the same mechanism read one level up.

---

## 5. What it would change, and what could break

| Change | Risk |
|---|---|
| A new `run` event in the closed set | the schema is closed deliberately; a new type is a law change, not a convenience |
| A cadence per process | a cadence nobody checks is decoration — the audit is what gives it force |
| The band moving to `Surveys` | a member factory may read it as losing its own verdict; the split in 4.3 is what prevents that |
| Run rows for every process | a process that runs hourly writes 24 rows a day; the register must state which processes are row-writing and which are continuous |

---

## 6. Open questions for the owner

1. **The band** — does it become the `Surveys` lane's verdict, or does the
   factory keep assigning its own?
2. **Who audits this factory's own processes** — its own `Surveys` lane, or a
   peer factory's?
3. **Does the register ship in the template**, so every factory inherits it, or
   is it meta-factory-only?
4. **A missed cadence** — does it block the score, or is it reported alongside it?
5. **The unenforced second banned table** (§3) — enforce it, or delete it?
