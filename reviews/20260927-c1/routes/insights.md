# insights — 4 routed finding(s)

Owner surface: `insights`. Lane session: `95b14002-4541-45a5-b2a6-4294ee1104f8`.

Source: `reviews/20260927-c1/state.json` → `codification_plan` (disposition=routed).

## 1. Lens E Finding 7 (LOW): synthesize_insights.py --audit names a caller that never calls it
- home / change site: `the tool lane owning tools/synthesize_insights.py`
- recorded_at: 2026-10-04T22:13:40Z

## 2. Lens G F11 (UNSPECIFIED): Cross-reference off by one: insights.md cites test_instrument_census.py 'arm 6' for a check that is ARM 7
- home / change site: `the insights instrument lane — docs/instruments/insights.md:45`
- recorded_at: 2026-10-04T22:13:55Z

## 3. Lens M F2 (SEVERE): The queue-dwell law is unmeasured, and the one tool whose docstring claims to measure it does not
- home / change site: `the tool lane owning tools/synthesize_insights.py; or delete the docstring claim`
- recorded_at: 2026-10-04T22:14:13Z

## 4. Lens S S-13 (LOW): docs/instruments/insights.md exists with NO template half and its symlink points at the ROOT doc, breaking the doc-pair contract
- home / change site: `the insights instrument lane — docs/instruments/insights.md section 10`
- recorded_at: 2026-10-04T22:14:30Z

