# fleet-instruments — 19 routed finding(s)

Owner surface: `fleet-instruments`. Lane session: `37e71e03-0022-4d38-9279-1687fec7a823`.

Source: `reviews/20260927-c1/state.json` → `codification_plan` (disposition=routed).

## 1. Lens C Finding 2 (HIGH): A documented reproduce command that no longer reproduces, and the file contradicts itself
- home / change site: `the kit instrument lane — docs/instruments/kit.md section 9.2 / section 4.1`
- recorded_at: 2026-10-04T22:13:27Z

## 2. Lens C Finding 4 (MEDIUM): No tool-invocation telemetry exists for this factory's own CLI surface; the lens's error-distribution analysis is unimplementable
- home / change site: `the tool lanes owning tools/*.py (oc_log telemetry shim); or docs/review-lenses.md:77 lens-C scope`
- recorded_at: 2026-10-04T22:13:28Z

## 3. Lens C Finding 7 (LOW): Two tools in tools/ are invoked by nothing: no law, no gate, no cron, no kit
- home / change site: `the tool lanes — tools/render-trap-runbook.py, tools/sigpipe_threshold.sh`
- recorded_at: 2026-10-04T22:13:30Z

## 4. Lens D D-5 (UNSPECIFIED): tools/sigpipe_threshold.sh is an ungated, unshipped one-off whose header cites paths that do not exist in this repo
- home / change site: `the tool lane owning tools/sigpipe_threshold.sh`
- recorded_at: 2026-10-04T22:13:34Z

## 5. Lens E Finding 2 (HIGH): --stdout means 'also write' in one census and 'do not write' in two others
- home / change site: `the tool lanes owning the three census tools (state the contract in docs/instruments/kit.md)`
- recorded_at: 2026-10-04T22:13:37Z

## 6. Lens E Finding 4 (MEDIUM): roadmap.py --cadence is a silent alias of --audit (two help texts, one code path)
- home / change site: `the roadmap tool lane — tools/roadmap.py + the cron row docs/factory-registry.md:382`
- recorded_at: 2026-10-04T22:13:38Z

## 7. Lens E Finding 5 (MEDIUM): Cross-script flag-name collisions: --home and --stamp each mean two unrelated things
- home / change site: `the tool lanes owning brain_metrics/compaction_rate/audit; rename per the report`
- recorded_at: 2026-10-04T22:13:38Z

## 8. Lens F Finding 1 (HIGH): Shell hygiene: neither shell script sets -e; the lens law requires set -euo pipefail
- home / change site: `the tool lanes owning the two shell scripts`
- recorded_at: 2026-10-04T22:13:41Z

## 9. Lens F Finding 2 (HIGH): audit.py masks a failed ledger stamp with exit 0
- home / change site: `the audit tool lane — tools/audit.py:2922-2924`
- recorded_at: 2026-10-04T22:13:42Z

## 10. Lens F Finding 4 (MEDIUM): audit.py silently drops malformed ledger rows that ledger.py treats as fatal
- home / change site: `the audit tool lane — tools/audit.py:426,546`
- recorded_at: 2026-10-04T22:13:43Z

## 11. Lens F Finding 5 (MEDIUM): audit.py --json silently ignores --report / --stamp
- home / change site: `the audit tool lane — tools/audit.py:2770-2786`
- recorded_at: 2026-10-04T22:13:44Z

## 12. Lens F Finding 6 (MEDIUM): Exit-code collapse: no failure path in the tool surface exits a distinct non-zero code
- home / change site: `the tool lanes — define named exit constants per refusal class; or amend docs/review-lenses.md:93`
- recorded_at: 2026-10-04T22:13:45Z

## 13. Lens F Finding 8 (LOW): registry_render.py writes its three state surfaces non-atomically
- home / change site: `the registry tool lane — tools/registry_render.py:1161-1163`
- recorded_at: 2026-10-04T22:13:46Z

## 14. Lens T T-2 (HIGH): tokens_out is not output tokens; the schema exposes no output-token column
- home / change site: `the telemetry lane — tools/telemetry.py:181-191`
- recorded_at: 2026-10-04T22:14:33Z

## 15. Lens T T-3 (HIGH): Model right-sizing (lens check 2) has no instrument; 'model' is never read
- home / change site: `the telemetry lane — add a model-attribution leg to tools/telemetry.py`
- recorded_at: 2026-10-04T22:14:34Z

## 16. Lens T T-4 (HIGH): Prompt-cache efficiency (lens check 3) has no instrument; the substrate already records the columns
- home / change site: `the telemetry lane — add a cache-hit leg to tools/telemetry.py`
- recorded_at: 2026-10-04T22:14:35Z

## 17. Lens T T-5 (MEDIUM): The money metric double-counts duplicate close rows and run/close pairs
- home / change site: `the audit lane — dedupe total_cost_usd by (subject, event)`
- recorded_at: 2026-10-04T22:14:36Z

## 18. Lens T T-6 (MEDIUM): The measurement covers a minority of closes by construction (82 measured / 92 unavailable of 280)
- home / change site: `the telemetry lane — index messages(created_at); print coverage beside the cost figure`
- recorded_at: 2026-10-04T22:14:37Z

## 19. Lens T T-7 (LOW): brain-metrics leg A states two char/token ratios and implements one
- home / change site: `the brain_metrics lane — tools/brain_metrics.py:71-72`
- recorded_at: 2026-10-04T22:14:38Z

