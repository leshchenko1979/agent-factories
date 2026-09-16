# Methodology Module 03: Documentation Standards & The Documentation Object Class

> **Core Law:** Documentation is a first-class operational object class that must be scored against an objective 0–4 rubric. A factory cannot be surveyed until its documentation achieves baseline calibration ($\ge 2/4$).

---

## 1. The Dual Documentation Requirement & The Consulting Gate

Every autonomous factory requires two distinct documentation pillars:

1. **Subject Matter Documentation (`docs/subject/`):** Explains *what* the factory builds (domain model, business rules, API schemas, client deliverables).
2. **Factory Methodology Documentation (`docs/methodology/`):** Explains *how* the factory operates (LLM weakness counters, quality loops, harness bindings, surface bindings).

### The Subject Matter Consulting Gate (Hard Law)
> **A factory is strictly barred from receiving substantive consulting, diagnostic audits, or bottleneck recommendations until baseline Subject Matter Documentation (`docs/subject/`) exists.**

Consulting on process without knowing what the process builds produces ungrounded bureaucracy. An auditor cannot diagnose whether a defect was caused by an ambiguous prompt, a broken model, or a domain misunderstanding if the domain requirements and schemas are not codified.

---

## 2. The Documentation Scoring Rubric (5 Dimensions, 0–4)

| Dimension | Minimal Baseline (Score 2) | Exemplary Standard (Score 4) |
|---|---|---|
| **1. Subject Matter (`docs/subject/`)** | `domain-model.md` and `client-requirements.md` present with core business entities, schemas, and deliverable specs. | Full domain model with verified API schemas, external credential specifications, client SLAs, and data fixture mocks. |
| **2. Ontology (`ONTOLOGY.md`)** | $\ge 10$ core domain terms defined unambiguously with canonical definitions. | Full ontology with canonical terms, banned synonyms, entity lifecycles, and test gate (`tests/test_ontology.py`). |
| **3. Process Register (`docs/processes.md`)** | All core processes declared with named single owner role and custom acceptance criteria. | All processes decomposed into atomic subprocesses with explicit input/output contracts and lead time targets. |
| **4. Process Law (`SKILL.md`)** | Execution rules, forbidden actions, and role boundaries declared. | Full feedforward constraints, rework memory integration, and post-compaction recovery anchors. |
| **5. Substrate & Harness Bindings** | Chat surface and agent runtime paths explicitly documented. | Full telemetry hooks, single-writer locking, and zero-token trigger probes wired. |

---

## 3. The Onboarding / Gap-Closing Interview Loop

When bootstrapping a new factory or onboarding a legacy codebase:

```mermaid
flowchart TD
    NewRepo["Un-onboarded Factory<br/>(Documentation Score < 2/4)"] --> Interview["Onboarding Interview Session<br/>(Structured Dialogue with Operator)"]
    Interview --> DraftDocs["Generates: docs/subject/, ONTOLOGY.md, SKILL.md, docs/processes.md"]
    DraftDocs --> AuditDocs["Documentation Score Gate<br/>(Requires docs/subject/ >= 2/4)"]
    
    AuditDocs -->|Score < 2/4| Interview
    AuditDocs -->|Score >= 2/4| Certified["Survey-Ready Certified<br/>(Enters Consulting & Daily Measurement Schedule)"]
```

- **Objective:** Bridge the documentation gap rapidly through structured dialogue.
- **Stop Condition:** Terminates when all 5 documentation dimensions score $\ge 2/4$.
- **Hard Prerequisite:** Baseline Subject Matter Documentation (`docs/subject/`) must be verified before the factory is admitted to substantive consulting or diagnostic audits.
- **Outcome:** The factory is baseline calibrated, enabling meaningful consulting, precise root-cause analysis, and automated audits.
