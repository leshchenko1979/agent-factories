# Review Rotation — the donor `hq.md` transcription (for OC DEV HQ to land)

**Owns:** the exact replacement text and the clause inventory for the donor-side change
Task 9 owes, supplied as **transcription, not authorship**. The attached text, the target
lines and the inventory are this lane's; the LANDING is OC DEV HQ's.

**Why the split, cited rather than restated.** The donor's own `SKILL.md:390` reads
"ONLY HQ edits skill files: `SKILL.md` · `editor.md` · `harvest.md` · `hq.md` · `triage.md` ·
`toolsmith.md`". The per-instrument exception the owner granted on 2026-09-27
(`fleet-directives.md:97`) delegates authorship of **one file per instrument** —
`docs/instruments/<instrument>.md` and its twin — and says so explicitly: it "does NOT extend
to skill markdown generally". So the instrument's law is this lane's; **reducing the donor's
superseded copy to a pointer is HQ's**, and it is the same direction as the Open Questions
precedent (`fleet-directives.md:589`, landed 2026-09-27).

**Ordering constraint, from this lane's own plan:** do not land this until the promoted law's
reload link resolves and the instrument's own gate is green. Both hold — the reload link is
`skills/meta-factory/review-rotation.md`, and `tests/test_review.py` is green at the tip.

## 1. The three regions that carry the contract

Source: `/root/.opencrabs/profiles/ops/skills/opencrabs-dev/hq.md`, **333 lines**, read
2026-09-27. Predicate: section headings; scope: that file; the line numbers below are ITS OWN
and move as the file changes — re-derive them from the headings, never from a remembered offset.

| region | lines | what it carries |
|---|---|---|
| `## Duty 4 — Poll workers for skill input (Direct Persistence & Ledger Intake)` | 137–173 | the whole intake contract |
| `## Duty 6 — Periodic subagent skill review` | 184–291 | the whole review contract, incl. the frozen schema field table |
| `## Cadence boundary is stamped at review consolidation` | 324–327 | the boundary predicate and the close-stamp form |

## 2. Clause inventory — what moves and what stays

Every clause is classified before extraction. **A moved clause leaves the donor; a staying
clause is process law about THIS factory and belongs to no instrument; a routed clause goes to
another owner.** The classes are the frame's (§8, and the frame's own routed/dropped table);
they are cited here, not restated.

**MOVES — the instrument carries it, and the donor keeps only a pointer:**

| donor clause | where it lands |
|---|---|
| Duty 4 step 3, intake & closure determination (mechanical state check, quorum/window) | `review.py intake` + `review.py verify` |
| Duty 4 step 4, validate every proposal three ways | `review.py verify` |
| Duty 4 step 6, convergence beats volume | `docs/instruments/review-rotation.md` |
| Duty 4 PER-LENS CENSUS (step 7) + its completion formula | `review.py verify` (census) |
| Duty 6 step 0, step-0 recovery mandate | `review.py step0` |
| Duty 6 step 0, the FROZEN SCHEMA field names and their rules | `docs/review-cycle.schema.json` — **emitted by `review.py schema`, never hand-kept** |
| Duty 6 step 0, the two anchored matching rules (boundary pattern, `WITHHELD:`) | `review.py cadence` |
| Duty 6 steps 1–4 (read-only sub-agent reviewers, family split, persist-first, triple-check) | `docs/instruments/review-rotation.md` + `review.py brief/record` |
| Duty 6 step 7, reviewer-performance loop | `review.py verify` (lens census) |
| Duty 6 cadence line ("after every FIVE shipped version bumps") | `review.py cadence` (`trigger.kind=version_bumps, every=5`) |
| Cadence section's boundary predicate (`kind=note` row beginning `<version> ACCEPTED`, MAX `n`) | `review.py cadence` — **measured this turn**: predicate = rows whose text matches `^v… ACCEPTED`, scope = the donor's `workers-ledger.json` (**11 642** events), instant 2026-09-27 ~16:5xZ → **12** anchored rows (all `kind=note`), boundary `n=12391` at `2026-09-27T08:00:35Z`, **2** `skill-bump` rows after → `2/5 WAIT` |

**STAYS — process law about this factory, and the instrument must NOT carry it:**

| donor clause | why it stays |
|---|---|
| Duty 4, Zero Session Notify Law for Worker Proposals (owner order 2026-09-11) | it is about HQ's context window and notify flooding — a routing rule for THIS factory, in no executable |
| Duty 4, the donor's own channels (`$REVIEW_DIR/proposals/<uuid>.md`, `oc-ledger stamp proposal`) | the instrument takes DECLARED channels; which channels are ours is our declaration |
| Duty 4 step 5 / Duty 6 step 5, "HQ lands every ACCEPTED finding in its entirety" (owner order 2026-09-25) | the donor's fix-approval gate exception; its scope is this factory's law surface |
| Duty 4 step 5 / Duty 6 step 5, the ROUTED disposition to other owners | routing is HQ's |
| Duty 6 step 0, the two `reviews/` roots and `--dir` discipline | `$OC_DEV_STATE` and the frozen skill-repo root are THIS factory's layout |
| Duty 6 step 6, the verdict posts to owner topic 30220 | a board identifier |
| Duty 6 step 8, the ledger cadence reset stamp (`oc-ledger stamp note "v<version> ACCEPTED"`) | the donor's own ledger and its boundary row form |
| The `oc-review-persist --dir` divergence note | a `tools/**` divergence already routed to Toolsmith |

**ROUTED — named in the file today, owned elsewhere:** the `oc-review-persist` `DEFAULT_DIR`
defect (Toolsmith) · the corpus pack at
`~/.opencrabs/profiles/ops/projects/jev-bloat-review/pilot/pack.py` (a separate trial
instrument, and its routing into `tools/` is its own decision, not a packaging detail) ·
`tools/docs/RC-CONTRACT.md` · `tools/docs/HEALTH-CHECKS.md` · `tools/docs/HEALTH-CLASSES.md`.

## 3. The replacement text

Heading text and position are **kept** so any `[LANE]` tag keeps resolving — the same shape the
Open Questions carve used. Body prose between the headings is replaced by the blocks below.

### For `## Duty 4 …` (replacing 137–173)

```
## Duty 4 — Poll workers for skill input (Direct Persistence & Ledger Intake)

**MOVED 2026-09-27.** The intake contract — the channels a proposal arrives on, the closure
determination, the validation triple-check, the per-lens census and the checkable completion
formula — now lives at `docs/instruments/review-rotation.md` **in the meta-factory repo
(`/root/agent-factories/`), NOT resolvable from this skill tree**. The executable is
`tools/review.py` (verb `intake`); its state schema is `docs/review-cycle.schema.json`.
Authored by the Review Rotation instrument lane (owner order 2026-09-27). Do not restate the
contract here — a second copy is the drift this carve removed.

What STAYS at this factory, because it is process law about US and not about the instrument:

- **Cadence: STANDING** — after every FIVE shipped version bumps (shared trigger with Duty 6),
  on owner request, or when incidents cluster without a rule.
- **Zero Session Notify Law for Worker Proposals (owner order 2026-09-11):** workers do NOT
  submit Duty 4 proposals via `session_notify` to HQ — inbound notify floods pollute HQ's
  context window, accelerate compactions and duplicate the freeze-ACK anti-pattern. Workers
  write proposals to `$REVIEW_DIR/proposals/<session-uuid>.md` or record them on the ledger via
  `oc-ledger stamp proposal "ADD|CHANGE <rule> in <file+section> BECAUSE <evidence>"`.
  Workers NEVER edit skill files themselves.
- **The channels are DECLARED, not inferred.** The cycle declares the proposal directory and the
  ledger kind it reads; the instrument REFUSES on an undeclared or absent channel rather than
  reading nothing and reporting clean.
- **HQ lands every ACCEPTED proposal itself — in its entirety, in the cycle's version batch**
  (owner order 2026-09-25), with NO design gate, NO plan card and NO owner approval; a fix whose
  owner is elsewhere is ROUTED to that owner and recorded as routed.
```

### For `## Duty 6 …` (replacing 184–291)

```
## Duty 6 — Periodic subagent skill review

Cadence: after every FIVE shipped version bumps, on owner request, or when an incident suggests
drift. The cadence is COMPUTED from the ledger, never narrated — see
`docs/instruments/review-rotation.md` and the section below.

**MOVED 2026-09-27.** The review contract — step-0 recovery, the frozen state schema and its
field rules, the anchored boundary matching, the read-only sub-agent reviewers, the family
split, persist-first write-through, the validation triple-check, the reviewer-performance loop
and the lens census — now lives at `docs/instruments/review-rotation.md` **in the meta-factory
repo (`/root/agent-factories/`), NOT resolvable from this skill tree**. The executable is
`tools/review.py` (`step0` · `brief` · `record` · `waive` · `verify` · `compile` · `cadence` ·
`close` · `migrate`); the state schema is `docs/review-cycle.schema.json`, EMITTED by
`review.py schema` and never hand-kept. Authored by the Review Rotation instrument lane
(owner order 2026-09-27). Do not restate the contract here — a second copy is the drift this
carve removed.

What STAYS at this factory:

- **HQ lands EVERY accepted finding in its entirety — mechanical AND semantic — as ONE version
  batch**, with NO design gate, NO plan card and NO owner approval (owner order 2026-09-25:
  findings "not wasted but fixed in their entirety"). Nothing is deferred to the owner as a
  "proposal". A finding whose fix belongs to another owner is ROUTED and recorded as routed.
  Scope stays this factory's law surface; the owner-gated actions in `AGENTS.md` remain gated.
- **The verdict table posts to owner topic 30220**; registry notes updated.
- **The ledger cadence reset stamp is ours and is mandatory** — see the section below. Without
  it the counter never resets and continuously reports overdue cycles.
- **Two `reviews/` roots exist and only one is live.** The STATE-repo root
  (`~/.opencrabs/profiles/ops/opencrabs-dev/reviews/`) is canonical and is what `$OC_DEV_STATE`
  resolves to; the skill-repo root is FROZEN EVIDENCE — keep it, never sweep it, never write a
  new cycle into it, and always pass `--dir` explicitly.
- **The corpus pack is a TRIAL, not this instrument** — it runs by absolute path from its own
  project dir, and its routing into `tools/` is a separate decision.
```

### For `## Cadence boundary is stamped at review consolidation` (replacing 324–329)

```
## Cadence boundary is stamped at review consolidation

`oc-ledger cadence` = count of `skill-bump` events since the last BOUNDARY event. **The boundary
predicate is a `kind=note` row whose text BEGINS `<version> ACCEPTED`** — the tool's regex is
`^v[0-9]+\.[0-9]+\.[0-9]+ ACCEPTED`, taken as the MAX `n`.

**The close form is `oc-ledger stamp note "v<version> ACCEPTED"`, NOT
`oc-ledger stamp review-battery`.** This section prescribed the `review-battery` form until
v0.4.243, and following it literally silently FAILED to reset the counter while the stamp itself
returned success — a green receipt on a boundary that never moved (found by Duty 4 cycle
`20260922-c22`: the prose was stale, the tool was right). Rule: every consolidated review verdict
ends with the boundary stamp BEFORE reporting the cadence state; never narrate a cadence reading
without confirming the boundary row exists.

**The predicate's mechanics are the instrument's** — `review.py cadence`, and
`docs/instruments/review-rotation.md` for the two anchored matching rules. What stays here is the
STAMP, the ledger it lands on and the close ordering above.
```

## 4. What this transcription does not do

- **It does not edit `hq.md`.** That file is HQ's (`SKILL.md:390`), and the landing is HQ's act.
- **It does not create the donor's reload link.** Frame §6.1: that is the member's own act, in
  the member's tree — the shape is each member's own decision, and it is never installed from
  here.
- **It does not restate the instrument's contract**, which is the defect this whole carve
  exists to remove.
