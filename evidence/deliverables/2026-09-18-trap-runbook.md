# The Trap Runbook — agent failures, and what to do about them

> Extracted from `docs/methodology/01-llm-weakness-counters.md` sections 4-7 —
> that file is the source of truth, this is a rendering of it. Regenerate with
> `python3 tools/render-trap-runbook.py`.

The extract opens by referring to "the taxonomy above", which is section 1 of the
source and is not repeated here. It splits agent failures by *generative
mechanism*, because each mechanism takes a different remedy:

| Family | Mechanism | Remedy that works |
|---|---|---|
| **Epistemic** | A fact that was never in context | Grounding — deterministic exit codes, same-turn receipts |
| **Context-capacity** | A fact that *was* in context and is gone | Flush to durable state before the summary |
| **Behavioral bias** | Training rewards politeness over convergence | An external driver — a goal, a pacemaker, a gate |
| **Operational friction** | Unbounded search, cascading errors | Stop on first defect, atomic work units, single accountability |

Getting the family wrong is what produces the useless counter: more rules for a
capacity failure, or a plea to "be careful" for a bias. Section 4 is the test
that tells them apart.

## 4. The Mirror Test: these are not AI failures, they are mind failures

The taxonomy above is not a list of machine defects. Every family in it describes a failure mode that humans already have a name for, a remedy for, and centuries of practice at mitigating — because a probabilistic memory that degrades under load is what a person's mind is, too.

Before designing a counter for an observed agent defect, run the mirror test: ask the same question of yourself.

| Mirror question | Human name for it | Family |
|---|---|---|
| Do you ever forget anything? | Forgetting, absent-mindedness | 2 — Context-capacity |
| Have you ever "remembered" something that never happened? | Confabulation, false memory | 1 — Epistemic |
| Have you ever lost the thread in a flood of information? | Overload, attention fatigue | 2 — Context-capacity |
| Have you ever lost focus while being bombarded from several directions? | Interruption cost, context switching | 2 + 4 |
| Have you ever said "yes, done" to end an awkward exchange? | Social lubrication, conflict avoidance | 3 — Behavioral bias |
| Have you ever kept going on the wrong thing because stopping meant admitting it? | Sunk cost | 3 + 4 |

The value of the mirror test is diagnostic, not decorative. It tells you where to look for the remedy: where humans solved this, the solution is usually a *practice* rather than a smarter brain — and a practice can be implemented as mechanical substrate, which is exactly what a factory is. It also predicts where the resemblance stops, and §7 states those limits.

---

## 5. The Management Analogy: a factory is a department

The second half of the same insight: if you have ever run a department, you already know how to run an agent factory. The correspondence is close enough to be a design method.

| A department has | A factory has |
|---|---|
| People who talk to each other | Sessions that message each other |
| People who ask each other questions | Peer lanes that query each other directly |
| People who hand work over | Push handoff to the owning session |
| People who contend for shared resources | Contention for one ledger, one repo, one claim |
| An escalation path upward | Triage → HQ → owner |
| A manager accountable for the process | Exactly one named process owner (P31) |
| People who complain about each other | Cross-lane defect reports routed to the owning lane |

Consequence: **org design is the design method.** The counters below are not novel inventions; they are the standard instruments of managing work, re-expressed in substrate.

| Human remedy | Why it works for people | Substrate implementation |
|---|---|---|
| Written checklist | Takes recall off the critical path | `plan` card on disk — survives compaction |
| External notes, notebook | Offloads working memory to a durable medium | `session_context`, ledger, `rework.md` |
| Standard work, SOP | Makes the right action the default action | `SKILL.md` + role cards, reloaded after compaction |
| Shift handover note | Carries state across a change of worker | Pre-compaction flush into the plan card |
| Two-person rule, peer review | An independent reader catches what the author cannot | Adversarial isolated review (P32), mechanical gates |
| Job rotation, fresh eyes | Breaks author-blindness | Review in an isolated session with a clean context |
| Single accountability | Shared ownership is zero ownership | P31 — one named process owner |
| Escalation path | Unblocks a worker who cannot decide alone | Triage → HQ → owner |
| Defect log with root cause | Stops the same defect recurring | `evidence/rework.md` with a `Prevented by` column |
| Stop-the-line authority | Prevents building on a known-bad unit | Jidoka — halt on first gate failure |

Two entries are structurally the same remedy: peer review and job rotation both work by putting a *different* reader on the work. In a factory both reduce to one mechanism — an isolated review session with a clean context window. That is why P32 requires isolation, rather than merely asking the author to re-read their own work.

---

## 6. The Trap Runbook

The taxonomy says what goes wrong. This says what to do about it, stated as the moment it happens, because that is when it is cheap to catch.

### Trap 1 — You are about to say "done"
**Symptom:** you are writing a completion sentence and the last tool result in your context is not the one that proves it.
**Counter:** name the receipt. If the proving command has not run, run it; if it ran, quote it. No receipt, no verdict — and "I have not verified this" is a complete and acceptable answer.

### Trap 2 — You are about to state a number, a sha, a path or an id
**Symptom:** the value came from memory or from mental arithmetic rather than from a tool result in this turn.
**Counter:** copy the full value out of live output, and compute with a tool, never in your head. A number must travel with its predicate: say what it counts and how it was counted, or state no number.

### Trap 3 — The context is getting long
**Symptom:** the harness warns that compaction is approaching; earlier instructions feel faint; you are re-reading things you already read.
**Counter:** flush *before* the summary — remaining steps and acceptance criteria into the plan card, in-flight variables into `session_context` — then carry on. After compaction, reload the skill and read the plan back from disk before any ruling, dispatch or status claim.

### Trap 4 — You are about to ask the operator something you could answer yourself
**Symptom:** the answer is in a file, a log, or a tool you have not called.
**Counter:** call the tool. Ask the operator only for a decision, a preference or a credential — never for a fact the substrate can supply. Ask once, with the options framed, then stop.

### Trap 5 — You have run the same failing command twice
**Symptom:** the second result resembles the first.
**Counter:** stop. Jidoka — halt, isolate the root cause, form a hypothesis, then act on the hypothesis. Repetition is not progress; a changed input is.

### Trap 6 — The task has grown beyond the work unit
**Symptom:** you are fixing something nobody asked about, "while you are in there".
**Counter:** write it down as its own item and finish the one you claimed. Scope is a decision that belongs to whoever owns the queue, not to whoever is mid-task.

### Trap 7 — You are about to accept a green you did not run
**Symptom:** the gate is reported passing by another lane, by an earlier turn, or by a summary.
**Counter:** run it yourself, in this turn, and read the exit code. A gate's green is only worth the same-turn receipt for it.

### Trap 8 — You are about to widen a gate so that it passes
**Symptom:** the honest reading of the law and the gate's verdict disagree, and the cheaper fix is the gate.
**Counter:** never. Change what the gate *measures* so it passes honestly, or surface the conflict upward. A gate edited to accommodate a violation has been deleted while appearing to remain (P15).

### Trap 9 — You are about to hand off by writing it down and moving on
**Symptom:** the next owner will not see the work unless they happen to poll.
**Counter:** push it. Write the durable record, then dispatch directly to the owning session. The ledger records what happened; it is not the conveyor belt that makes it happen.

### Trap 10 — You are about to close a work unit whose gate you have not re-run since the last edit
**Symptom:** the last edit came after the last green.
**Counter:** re-run the gate. Every edit invalidates the previous green, and a close row is a durable claim that will be read by someone who was not there.

---

## 7. What the mirror test does not license

The analogy is a design heuristic, not a claim about what an agent is. Two limits keep it honest:

1. **A similar symptom is not the same cause.** A person who forgets may be tired or distracted; an agent that forgets has had its history summarized. The remedy is chosen from the *mechanism*, which is exactly why §1 separates the families by generative mechanism rather than by how the failure looks from outside.
2. **The analogy predicts where it fails, too.** A person can notice they are confused and say so. An agent's report of its own confidence is produced by the same process that produced the error, so it carries no independent information. This is the reason every counter in §5 and §6 is external and mechanical — receipts, gates and durable state — and none of them is introspection.
