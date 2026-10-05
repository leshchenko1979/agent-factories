# review-rotation — 2 routed finding(s)

Owner surface: `review-rotation`. Lane session: `d6cfd3f7-0cd7-4e26-b9ff-2b1474be981e`.

Source: `reviews/20260927-c1/state.json` → `codification_plan` (disposition=routed).

## 1. Lens I F6 (MEDIUM): review-rotation.md ships stale and self-contradictory numeric readings, including three counts of its own gate file
- home / change site: `the review-rotation instrument lane — docs/instruments/review-rotation.md`
- recorded_at: 2026-10-04T22:14:05Z

## 2. Lens P P-7 (LOW): The only prior lens-P report is an unverifiable false positive, and no gate can catch it
- home / change site: `the review-rotation lane — re-run lens P under the receipt discipline (durable fix is P-1)`
- recorded_at: 2026-10-04T22:14:23Z

---

**Added 2026-10-05 (re-route).** Two DOC halves, re-routed from the fleet-instruments batch whose
`home` named a tool surface. The code half of each is the Worker lane's (`worker.md`); this is the
`docs/review-lenses.md` alternative, and that file is authored `d6cfd3f7` (this lane).

## 3. Lens C Finding 4 (MEDIUM): No tool-invocation telemetry exists for this factory's own CLI surface (doc half)
- change site: `docs/review-lenses.md:77` (lens-C scope)
- code half: `tools/*.py` oc_log shim → Worker
- recorded_at: 2026-10-04T22:13:28Z

## 4. Lens F Finding 6 (MEDIUM): Exit-code collapse — no failure path exits a distinct non-zero code (doc half)
- change site: `docs/review-lenses.md:93` (exit-code convention)
- code half: define named exit constants per refusal class → Worker
- recorded_at: 2026-10-04T22:13:45Z

