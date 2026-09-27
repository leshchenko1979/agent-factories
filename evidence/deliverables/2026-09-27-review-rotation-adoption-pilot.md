# Review Rotation — the adoption pilot (Task 10, criterion 2)

**Owns:** the pilot's ADOPTION RECEIPT — the delivery rehearsed end-to-end against a real
member's committed bytes, its self-probe, and the one condition it did **not** clear. The census
that selected the pilot is `evidence/instrument-census-review-rotation-2026-09-27.md`; the
instrument's law is `docs/instruments/review-rotation.md`. This file cites the frame and coins
no cross-instrument definition (frame §8).

## 1. The pilot, and why this member

**Predicate for candidacy:** a member carrying a DECLARED ledger surface (frame §9 O4 —
`tools/actors.txt`, the authorized-event matrix) **and** a vendored pin (`registry/kit.json`),
because §6's delivery leg cannot run without one.

| member | actors.txt | vendored pin | eligible |
|---|---|---|---|
| **inferhub-watch** | **yes** | **yes** | **PILOT** |
| infra-factory | yes | yes | excluded — `/root/vds-servers` is PULL-ONLY for this fleet |
| ai-antispam | no | yes | — |
| miidas | no | yes | — |
| opencrabs-dev | no | **no** | no pin, so no delivery path |

**`inferhub-watch` is the pilot.** Its O4 matrix is the one the frame itself measured, and it is
the only eligible member whose repo is not pull-only.

## 2. The rehearsal — real member bytes, and the live tree never touched

The member has **work in flight** (four untracked test files in its live tree), so writing into
it would have raced a peer's uncommitted work. The rehearsal therefore materialized the
member's **committed state** read-only:

```
git -C /root/inferhub-watch archive HEAD | tar -x -C /tmp/rr-pilot
```

`git archive` writes to the member in no way — no index, no HEAD, no working tree — which is the
property that makes this a rehearsal rather than a deployment. **Scope limit, stated:** the
rehearsal base is the member's COMMITTED state, so its untracked files are not in it. That is
the right base for judging a delivery (a delivery interacts with committed bytes) and it is
stated rather than left implicit.

## 3. The receipts

| leg | reading | predicate | instant |
|---|---|---|---|
| delivery plan, dry | 96 written · 15 local forks skipped · 17 declarations untouched · 0 refused | `kit_deliver.py --dry-run --to /tmp/rr-pilot` | 2026-09-27 ~17:0xZ |
| delivery, real | pin `db6aa904a8a1` → **`f99738fe256a`**, bytes and pin in ONE run | same tool, no `--dry-run` | same |
| idempotence | **0 written**, 5 forks skipped — a second run is a no-op | same tool, second run | same |
| **declared set held** | **5 / 5** | the five paths of the law doc §2, at the adopted tree | same |
| **the instrument's own gate** | **`ALL TESTS PASSED`, rc=0** | `python3 tests/test_review.py` in the adopted tree | same |
| the member's kit gate | **FAILED, 1 check** | `python3 tests/test_kit_pin.py` in the adopted tree | same |

**The instrument's adoption works end-to-end.** Five of five declared paths arrive, the
executable runs, and its own gate is green in the member's tree — which is the receipt
criterion 2 asks for.

## 4. The one condition it did NOT clear — and the control that attributes it

The delivered tree's kit-pin gate reds on **one** path:

```
FAIL — carried paths that diverge from YOUR OWN pin and are not declared exempt:
  tests/test_single_writer.py  class=standalone  pin=ba542c47b52f tree=a39c11e839b1
```

**That is the delivery leg behaving as designed**, not a defect: `kit_deliver` SKIPS a local
fork rather than overwriting the member's own work, and "skipping it leaves the pin claiming the
new state, so the member's own gate reds until they either take the update or declare the fork.
The gate says so; the transport does not decide for them."

**But a red in the member's tree after a delivery must never be assumed to be OURS, so it was
controlled.** The member's own pin gate was run against its live tree, read-only, where no
delivery of ours had landed:

```
kit pin FAILED: 1 check(s)
  judged 22 carried path(s); 2 factory-class path(s) excluded by class; 5 declared exempt
```

**The member's kit gate was ALREADY RED before anything of ours touched it** — and on a
DIFFERENT population (22 carried paths judged, versus 118 in the delivered tree). So the
delivery neither caused nor cleared it. It is a pre-existing member-side condition: the member
has not taken its pending updates nor declared its forks.

**This is the discrimination the tool's own docstring demands.** Without the control arm the red
would have been attributed to the delivery, which is the worst reading available — a state we
created that reds the member's gate — and it would have been wrong.

## 5. What this pilot does NOT establish

- **It does not adopt the instrument at the member.** The rehearsal is a COPY; the member's live
  tree is untouched. Adoption is the member's own act: §6.1's reload link is "**your** act, in
  **your** tree; it is never installed from the template", and the census's declared leg is
  `unestablished` for every member because the per-instrument disposition surface does not exist
  yet (an HQ schema question, recorded in the census).
- **It does not make the member's kit gate green.** That red predates this work and clears by
  one of two lawful acts the member owns — take the update, or declare the fork with a reason.
- **It does not licence porting to any other member.** Criterion 2 sequences the wave behind a
  green pilot receipt; the port to the rest has not run.
- **It does not touch the donor** (`opencrabs-dev` has no pin, so no delivery path exists for it
  — its leg is the `hq.md` carve, plus its own adoption act).
