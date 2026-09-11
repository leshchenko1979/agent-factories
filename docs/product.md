# Product: the factory template

**What this is.** A template for creating a new agent factory — a working
structure an operator (or an agent) copies and instantiates, plus the rules
that make it work and the domain add-ons that adapt it to a particular kind of
work.

**What it is not.** Not a framework, not a runtime, not a library. There is no
code to import. The product is a set of files plus an ordered procedure, and it
is complete when a new factory can be stood up in an afternoon without the
operator re-deriving any of the decisions.

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
| `ROLES` | Which roles exist (HQ, Triage, workers, carrier) | `HQ` only for a minimal factory |
| `DOMAINS` | Domain topics in the middle of the spine | `Landing`, `Bot`, `Outreach` |
| `ADDONS` | Domain packs to apply | `watch` |
| `GATES` | Commands that decide, where a command can | `oc-*` tool set, or a repo test suite |

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
