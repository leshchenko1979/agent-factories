# Review Rotation — the donor replay, and the three frictions it found

**Owns:** the migration EVIDENCE for the Review Rotation instrument — a donor cycle carried
end-to-end through the promoted engine, what that run exposed, and the donor-side change this
leg does **not** make. The instrument's law is `docs/instruments/review-rotation.md`; the frame
is `docs/instruments/template-instruments.md`. This file cites both and **coins no
cross-instrument definition** (frame §8).

Read the frame before this file. Where a term is the frame's, the frame is the authority.

## 1. The input, stated before the result

A migration claim is a claim about a specific record, so the record is named with its own
predicate, scope and instant:

| what | value | predicate | scope | instant |
|---|---|---|---|---|
| the donor cycle replayed | `20260925-c24` | one cycle directory under the donor's **state-repo** root | `/root/.opencrabs/profiles/ops/opencrabs-dev/reviews/` | read 2026-09-27 ~16:47Z |
| its state file | md5 `9d46f57cbab8111cf4624efbb7c40d8a`, 3 842 B | that file | — | stated as read |
| its lens reports | 12 files | `ls reports/` | that cycle | same |
| the replay target | `reviews/rr-donor-replay/` in this repo | a COPY, never the donor's file | this repo | — |

**The donor's file is never written.** `migrate` writes a pre-image
(`state.json.pre-v1.bak`) and its output path is the copy, which is the only reason a
destructive schema change can be rehearsed against live data at all.

**Why this cycle:** of the donor's cycles it is the one that carries the most of what the
promoted schema has to absorb — `status: 'COMPLETE'` (a value outside the donor's own ruled
enum), `cadence` as **free text** rather than a structure, `proposals: []`, and 11 lens entries
against a 14-lens catalogue. A clean cycle would have proved nothing.

## 2. The replay, end to end

Transcript, one section per leg, each with the leg's own exit code (read directly — a pipe
reports its own rc, not the tool's):

### `migrate` → rc=0
```
Migrate 'rr-donor-replay': 10 keys read -> 17 written, schema v1
  cadence                  kept
  ...
  status                   kept
  status mapped: 'COMPLETE' -> 'COMPLETED'
pre-image written: .../state.json.pre-v1.bak
migrated: .../state.json
```

### `step0` → rc=0
```
status      : COMPLETED  frozen=yes
census      : 10 completed | 0 waived | 4 pending (of 14)
proposals   : 0 receipt(s)
next action : cycle is FROZEN (terminal): report the frozen snapshot. Do NOT re-read a live
              ledger or proposals dir — pass --live only to say you mean today's bytes.
```

### `intake` → **rc=2, REFUSED**
```
REFUSED: cycle 'rr-donor-replay' is FROZEN at 2026-09-25T19:00:00Z; intake would read live
mutable input the cycle did not close on. Re-run with --live to read today's bytes
deliberately, or read the frozen snapshot in state.json.
```
**This refusal is the promoted behaviour, not a failure of the replay.** A cycle that closed
on 2026-09-25 must not silently re-read today's ledger and report it as that cycle's intake.

### `compile` → rc=0
```
Compiled master verdict skeleton: reviews/rr-donor-replay/verdict.md
```

### `verify` → **rc=1, FAIL, three named classes**
```
Missing or incomplete lenses: P (PENDING), M (PENDING), T (PENDING), S (PENDING)
Checksum corrupted lenses: A, B, G, J, C, E, F, D, H, I (checksum mismatch)
UNRECEIPTED lenses (no index line): A, B, G, J, C, E, F, D, H, I
```

**A migrated legacy record CANNOT pass `verify`, and that is correct rather than a defect.**
The donor never recorded a digest or an index line, so the promoted verdict has nothing to
check against — and a gate that passed such a record would be claiming a verification nobody
performed. The three classes are named, so the reader sees exactly which rung is missing
instead of a bare red.

**Conclusion for AC1:** the cycle reads **end to end** — every leg produces a stated result,
and the two non-zero exits are named refusals rather than crashes. The durable report is
`reviews/rr-donor-replay/verdict.md` (+ its `state.json`), committed beside this file.

## 3. What the replay found — three frictions, all now fixed

Each was found by running donor data through the engine. None was found by reading the code,
which is the point of a replay over a review.

| # | symptom | evidence | fix |
|---|---|---|---|
| **F1** | `status` **crashed** on a migrated cycle — `TypeError: 'NoneType' object is not subscriptable` | a donor lens entry carries `report_path` with `sha256` **absent**; the render indexed it directly, so EVERY migrated cycle died on its first read | renders `unrecorded` — a digest nobody computed is a verification claim nobody made |
| **F2** | `migrate` left the donor's terminal SYNONYM unmapped | the donor's cycle `status` carries **six** values (COMPLETED 9, IN_PROGRESS 4, reports_persisted 1, intake_complete 1, VALIDATED 1, COMPLETE 1), its lens entries **four** (COMPLETED 66, COMPLETE 11, PENDING 7, PERSISTED 4) — predicate: each cycle dir's `state.json`; scope: the donor state root, 17 files | `COMPLETE` → `COMPLETED`, **and only that one**: `PERSISTED` says a report was written, not that a lens reached a verdict |
| **F3** | `migrate` absorbed everything unmapped in **silence** | a reader could not tell "mapped" from "carried in unvalidated" | prints `status mapped: …` and `UNMAPPED (carried in, not valid here): …` |

**A note on F2's own figure.** The counts above are the donor's, measured over its state files
at the instant shown. They are a reading of a live corpus, not a constant: a later reader who
re-derives them should get the same numbers **for the same 17 files**, and should expect them
to move when the donor runs another cycle.

## 4. What this file does NOT claim

- **It does not claim the donor's gates pass.** They are measured separately, and the reading
  belongs with the donor-side change.
- **It does not claim the donor-side migration has landed.** The donor's `hq.md` carries
  Duties 4/6 as an implementation contract, and skill law text is authored by OC DEV HQ
  (frame §8: authorship of a law doc is delegable; a clause binding a member factory is not).
  This lane supplies the replacement text; HQ lands it.
- **It does not install into the donor's tree.** Frame §6.1: the member leg is an ADOPTION
  STEP owned by the member — `kit_deliver.py` copies files and creates no symlinks, and a
  distribution that wrote into a member's skill tree would be touching the member's own files.
  The precedent is the Open Questions instrument (`fbe57c5`): the law pair plus the reload
  link, landed in THIS repo, and the donor's superseded copy reduced to a `[LANE]` pointer by
  HQ.
