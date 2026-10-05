# worker — 21 re-routed finding(s)

**Re-route, 2026-10-05.** These 19 findings were first sent to `fleet-instruments`, whose `home`
strings named a **tool surface** ("the audit tool lane", "the telemetry lane", "the tool lanes")
rather than a lane. The fleet-instruments lane does not own `tools/**` code — frame §8
(`docs/instruments/template-instruments.md:897`): *"Out of scope for an instrument owner, by role:
`tools/**` code ownership (Toolsmith)"*. In **this** factory the implementation destination for its
own repo is the **Worker** lane (SKILL §3; `skills/meta-factory/ledger.md:1254` — *"the lane that
owns that code in the tree concerned"*). Measured convention: every recent `tools/**` defect
(#263, #201, #319, #322, #332, #333, #334) was dispatched to Worker `dcd8f7a9`. Root defect: **#339**.

Lane session: `dcd8f7a9-c1e7-48c3-b184-d901dc08eac7` (Worker, thread 1271).

Source: `reviews/20260927-c1/state.json` → `codification_plan` (disposition=routed).
Two rows carry a DOC alternative on `docs/review-lenses.md` (authored `d6cfd3f7`, review-rotation) —
those halves are re-routed there and noted per row.

**Extended 2026-10-05 (insights lane pushback).** Entries **20–21** were re-routed here from the
**insights** lane (`95b14002`, thread 6865), which flagged on receipt that their `home` named a tool
surface ("the tool lane owning `tools/synthesize_insights.py`") — the same #339 class. Both change
`tools/synthesize_insights.py`; #357's law half (the dwell targets) stays with HQ per its issue body.

## 1. Lens C Finding 4 (MEDIUM): No tool-invocation telemetry exists for this factory's own CLI surface; the lens's error-distribution analysis is unimplementable
- change site: `tools/*.py` (oc_log telemetry shim)
- doc alt: `docs/review-lenses.md:77` (lens-C scope) → review-rotation
- recorded_at: 2026-10-04T22:13:28Z

## 2. Lens C Finding 7 (LOW): Two tools in tools/ are invoked by nothing: no law, no gate, no cron, no kit
- change site: `tools/render-trap-runbook.py`, `tools/sigpipe_threshold.sh`
- recorded_at: 2026-10-04T22:13:30Z

## 3. Lens D D-5 (UNSPECIFIED): tools/sigpipe_threshold.sh is an ungated, unshipped one-off whose header cites paths that do not exist in this repo
- change site: `tools/sigpipe_threshold.sh`
- recorded_at: 2026-10-04T22:13:34Z

## 4. Lens E Finding 2 (HIGH): --stdout means 'also write' in one census and 'do not write' in two others
- change site: `tools/{instrument_census,kit_census,kit_names}.py` (code half)
- doc half: `docs/instruments/kit.md` census `--stdout` contract → kit instrument (filed **#354**)
- recorded_at: 2026-10-04T22:13:37Z

## 5. Lens E Finding 4 (MEDIUM): roadmap.py --cadence is a silent alias of --audit (two help texts, one code path)
- change site: `tools/roadmap.py` + the cron row `docs/factory-registry.md:382`
- recorded_at: 2026-10-04T22:13:38Z

## 6. Lens E Finding 5 (MEDIUM): Cross-script flag-name collisions: --home and --stamp each mean two unrelated things
- change site: `tools/{brain_metrics,compaction_rate,audit}.py` (rename per the report)
- recorded_at: 2026-10-04T22:13:38Z

## 7. Lens F Finding 1 (HIGH): Shell hygiene: neither shell script sets -e; the lens law requires set -euo pipefail
- change site: the two shell scripts under `tools/*.sh`
- recorded_at: 2026-10-04T22:13:41Z

## 8. Lens F Finding 2 (HIGH): audit.py masks a failed ledger stamp with exit 0
- change site: `tools/audit.py:2922-2924`
- recorded_at: 2026-10-04T22:13:42Z

## 9. Lens F Finding 4 (MEDIUM): audit.py silently drops malformed ledger rows that ledger.py treats as fatal
- change site: `tools/audit.py:426,546`
- recorded_at: 2026-10-04T22:13:43Z

## 10. Lens F Finding 5 (MEDIUM): audit.py --json silently ignores --report / --stamp
- change site: `tools/audit.py:2770-2786`
- recorded_at: 2026-10-04T22:13:44Z

## 11. Lens F Finding 6 (MEDIUM): Exit-code collapse: no failure path in the tool surface exits a distinct non-zero code
- change site: the tool surface — define named exit constants per refusal class
- doc alt: `docs/review-lenses.md:93` → review-rotation
- recorded_at: 2026-10-04T22:13:45Z

## 12. Lens F Finding 8 (LOW): registry_render.py writes its three state surfaces non-atomically
- change site: `tools/registry_render.py:1161-1163`
- recorded_at: 2026-10-04T22:13:46Z

## 13. Lens T T-1 (CRITICAL): extract_task_telemetry session_id threading — telemetry attributed to the wrong session
- change site: `tools/ledger.py:1514` + `tools/telemetry.py:243` + `tools/audit.py:591`
- note: the ledger lane flagged this as NOT its own (change site is the telemetry extractor, not the ledger writer)
- recorded_at: 2026-10-04T22:13:47Z

## 14. Lens T T-2 (HIGH): tokens_out is not output tokens; the schema exposes no output-token column
- change site: `tools/telemetry.py:181-191`
- recorded_at: 2026-10-04T22:13:47Z

## 15. Lens T T-3 (HIGH): Model right-sizing (lens check 2) has no instrument; 'model' is never read
- change site: `tools/telemetry.py` — add a model-attribution leg
- recorded_at: 2026-10-04T22:13:48Z

## 16. Lens T T-4 (HIGH): Prompt-cache efficiency (lens check 3) has no instrument; the substrate already records the columns
- change site: `tools/telemetry.py` — add a cache-hit leg
- recorded_at: 2026-10-04T22:13:49Z

## 17. Lens T T-5 (MEDIUM): The money metric double-counts duplicate close rows and run/close pairs
- change site: `tools/audit.py` — dedupe `total_cost_usd` by (subject, event)
- recorded_at: 2026-10-04T22:13:50Z

## 18. Lens T T-6 (MEDIUM): The measurement covers a minority of closes by construction (82 measured / 92 unavailable of 280)
- change site: `tools/telemetry.py` — index messages(created_at); print coverage beside the cost figure
- recorded_at: 2026-10-04T22:13:51Z

## 19. Lens T T-7 (LOW): brain-metrics leg A states two char/token ratios and implements one
- change site: `tools/brain_metrics.py:71-72`
- recorded_at: 2026-10-04T22:13:52Z

## 20. Lens E Finding 7 (LOW): the `--audit` help names a caller that never calls it (CI/audit.py)
- change site: `tools/synthesize_insights.py:407` — the flag's real consumer is the weekly cron `factory-insights-weekly`, not `tools/audit.py` (which runs the test instead)
- filed **#355**; re-routed from the insights lane 2026-10-05 (same #339 class)
- recorded_at: 2026-10-04T22:13:39Z

## 21. Lens M Finding 2 (SEVERE): the queue-dwell law is unmeasured and the synthesize tool claims to mine it
- change site: `tools/synthesize_insights.py:255,7` — `mine_ledger_telemetry()` claims queue-dwell but does not measure it (law: `docs/methodology/02-quality-management.md:37`, `docs/processes.md:136`)
- filed **#357**; its law half (the dwell targets) is routed to **HQ** in the issue body
- re-routed from the insights lane 2026-10-05 (same #339 class)
- recorded_at: 2026-10-04T22:14:11Z

---

**Acceptance-criteria note (frame §8 split).** Where a subject tool is an instrument's own, the
instrument lane supplies the TEXT and the acceptance criteria; the code is landed by the
implementation destination (this lane). Relevant instrument homes: the three census tools →
**kit** (fleet-instruments); `tools/ledger.py` / `tools/telemetry.py` → **Ledger** (telemetry.py was
authored by `d0cba805`, 83a2776). No instrument law file exists for audit / registry / roadmap /
brain_metrics / the shell scripts.
