# methodology — 13 routed finding(s)

Owner surface: `methodology`. Lane session: `4515ea72 (this lane)`.

Source: `reviews/20260927-c1/state.json` → `codification_plan` (disposition=routed).

## 1. Lens F Finding 3 (HIGH): Atomic journaling: review.py writes its cycle state, report and receipt with no lock, no temp file and no fsync
- home / change site: `this lane's own surface (review instrument) — tools/review.py:901,1157,1169 — write via sibling temp + fsync + os.replace; fsync the index append`
- recorded_at: 2026-10-04T22:13:42Z

## 2. Lens I F1 (HIGH): The lens briefs are generated from a SECOND, drifted copy of the lens definitions; review-lenses.md and LENS_METADATA disagree
- home / change site: `this lane's own surface (review instrument) — tools/review.py:74-219 (LENS_METADATA) — align names/families/scopes/checks with docs/review-lenses.md`
- recorded_at: 2026-10-04T22:14:01Z

## 3. Lens I F2 (HIGH): The 'Quote-or-No-Finding' evidence rule is unenforced: record accepts any non-empty bytes and stamps COMPLETED
- home / change site: `this lane's own surface (review instrument) — tools/review.py:1147 — reject a report body with no path:line locator token`
- recorded_at: 2026-10-04T22:14:02Z

## 4. Lens I F3 (HIGH): The freeze is bypassable: record and waive carry no is_frozen check, so a closed cycle's state.json can be mutated after close
- home / change site: `this lane's own surface (review instrument) — tools/review.py:1127,1194 — add the is_frozen refusal to cmd_record and cmd_waive`
- recorded_at: 2026-10-04T22:14:03Z

## 5. Lens I F4 (MEDIUM-HIGH): The 'UNRECEIPTED (no index line)' state is unreachable: verify reads a self-stamped boolean, never the index log
- home / change site: `this lane's own surface (review instrument) — tools/review.py:1482 — verify parses review-index.log, not the self-stamped receipt field`
- recorded_at: 2026-10-04T22:14:04Z

## 6. Lens I F5 (MEDIUM): Every emitted brief scopes the reviewer onto paths that do not exist in this repo, while dropping the one path that does
- home / change site: `this lane's own surface (review instrument) — tools/review.py:78 — localise LENS_METADATA scopes to this repo's paths`
- recorded_at: 2026-10-04T22:14:04Z

## 7. Lens I F7 (MEDIUM): Overlapping lens coverage: C and D claim the same 'uninvoked/legacy tool' finding, and C's error-code clause overlaps F
- home / change site: `this lane's own surface (review instrument) — docs/review-lenses.md:80,93 — add an ownership boundary between lenses C/D and C/F`
- recorded_at: 2026-10-04T22:14:05Z

## 8. Lens I F8 (MEDIUM): The Adversarial Isolation Requirement is unenforceable: nothing records who produced a report or that it came from an isolated sub-agent
- home / change site: `this lane's own surface (review instrument) — tools/review.py — add brief-id + recorded_by; or downgrade the isolation claim in docs/review-lenses.md:13`
- recorded_at: 2026-10-04T22:14:06Z

## 9. Lens I F9 (LOW): review.py doc drift: the Usage block and enforcement list omit codify, and two --help strings disagree on the lens set
- home / change site: `this lane's own surface (review instrument) — tools/review.py:39 — add codify to the Usage block + enforcement list; align the two help strings`
- recorded_at: 2026-10-04T22:14:07Z

## 10. Lens M F5 (MAJOR): 'Batch Size Control (P11)' cites a clause that says the opposite, and the check is unmeasurable
- home / change site: `this lane's own surface (review instrument) — docs/review-lenses.md:127 + tools/review.py:186 — correct or remove the (P11) batch-size citation`
- recorded_at: 2026-10-04T22:14:16Z

## 11. Lens S S-5 (MEDIUM): The lens catalogue's own scope for Lens S names generic paths that do not exist in this repo (catalogue-to-corpus drift)
- home / change site: `this lane's own surface (review instrument) — docs/review-lenses.md:156 — localise the Lens S scope to the real profile brain files`
- recorded_at: 2026-10-04T22:14:26Z

## 12. Lens S S-15 (INFO): Lens S's own 'Core Checks' cites 'P25', but P25 is defined nowhere in the process register
- home / change site: `this lane's own surface (review instrument) — docs/review-lenses.md:158 — replace the undefined (P25) citation with the plain rule`
- recorded_at: 2026-10-04T22:14:31Z

## 13. Orchestrator observation (measured this run): the brief's REQUIRED FINDINGS FORMAT (tools/review.py:1102-1108) mandates locator, quote, analysis and remediation but NOT a severity, so 3 of 14 reports (A, D, G) carry none and 36 of 125 findings have no common ordering key for cross-lens triage
- home / change site: `tools/review.py:1102 — add a Severity line to the brief's REQUIRED FINDINGS FORMAT (one of CRITICAL/SEVERE/HIGH/MEDIUM/LOW/INFO), so every lens report is triageable on one key`
- recorded_at: 2026-10-04T22:16:30Z

