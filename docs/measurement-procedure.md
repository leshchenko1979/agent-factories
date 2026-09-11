# Daily factory measurement — procedure

The recurring measurement run. **The scheduled job's prompt points here; the
procedure lives in this file, not in the job.**

> Why: a job's definition cannot be updated by a change to the law. Procedure
> embedded in a job prompt silently goes stale the moment this file changes.
> The job carries a pointer; this file carries the procedure.

---

## Cadence and Roles

**Self-scoring:** each member factory maintains its own standing measurement loop (daily or on its
own sprint cadence) to trigger continuous self-correction.

**Surveyor audit:** periodic meta-factory review (less frequent than daily self-scoring; owner order 2026-09-11).
The surveyor's role is calibration and cross-factory pattern discovery, not micro-management.

---

## What one run does

For each surveyed factory:

1. **Review** the factory's self-score and audit against [quality-criteria.md](quality-criteria.md) — 13
   criteria, 0–4 each. Verify against **live state**: the factory's repo,
   its board, its law files, its scheduled jobs. Never from memory and never
   from the previous report.
2. **Diff** against previous records. Note where self-judgment and external audit diverge (the calibration gap).
3. **Record** the dated score in this repo — the diff is the signal, a single
   score is an opinion.
4. **Report** to the analysis topic: the scores, the movements, and any
   **template law** the movement implies.

---

## What one run must NOT do

| Don't | Why |
|---|---|
| Adjudicate a factory's product decisions | That is its own `HQ`'s call. This run measures the machine, not the work |
| File, edit or close anything in a member factory's repo | Doing a member's work duplicates a lane and bypasses its process law |
| Talk to a member factory's lanes directly | Converse with its **HQ**, or that HQ's delegate — never into its lanes |
| Report a score without the read that produced it | A score is a claim; claims need a same-turn receipt |
| Pull domain detail into the number | The score is effectiveness and health — how the machine works, not what it is working on |

**If a factory is unreadable** — no board, no law file, no reachable HQ — that
is a finding, not a blocker. Score what is absent as absent and say which read
failed. "Could not read" and "scored zero" are different results and must be
reported differently.

---

## Measures

The 13 criteria are the **floor**. Factory-specific measures are added as the
need appears, and each must name the **decision it informs**.

A measure with no decision attached is dropped. Dashboards are not controls.

---

## Trend, not snapshot

Keep every run's date and score. The value of the daily cadence is that a
**movement** becomes visible while it is still cheap to act on. A run that
reports only the current score has thrown away the reason it runs daily.

---

## Routing

- **Results** go to the analysis topic in the Factories group — the owner's
  lane.
- **Anything needing a member factory's action** goes to that factory's HQ via
  its own direct-address path, as a finding. Not as a work order: the HQ decides
  what its factory does about it.
