# ledger — 6 routed finding(s)

Owner surface: `ledger`. Lane session: `d0cba805-92c9-4377-8808-a1cf715bce9e`.

Source: `reviews/20260927-c1/state.json` → `codification_plan` (disposition=routed).

## 1. Lens E Finding 8 (LOW): ledger-index.py is the odd dispatch style out, and its docstring omits a verb it implements (path)
- home / change site: `the ledger tool lane — tools/ledger-index.py`
- recorded_at: 2026-10-04T22:13:40Z

## 2. Lens H Finding 1 (SEVERE): Timestamp ordering is non-monotonic, and no mechanism detects it (13 rows out of order; verify prints unqualified 'monotonic')
- home / change site: `the ledger instrument lane — tools/ledger.py verify + docs/instruments/ledger.md section 9.1`
- recorded_at: 2026-10-04T22:13:58Z

## 3. Lens H Finding 2 (HIGH): Duplicate close/claim rows leave the ledger unable to answer 'closed once or twice?'
- home / change site: `the ledger instrument lane — docs/ledger-exemptions.json + a ledger verify disposition`
- recorded_at: 2026-10-04T22:13:59Z

## 4. Lens H Finding 3 (MEDIUM): The documented lock path is not the lock the write path takes
- home / change site: `the ledger instrument lane — docs/instruments/hygiene.md:217 + tools/hygiene.py:786`
- recorded_at: 2026-10-04T22:14:00Z

## 5. Lens H Finding 4 (MEDIUM): The timestamp invariant exists in one law file and was dropped from its summary, with no gate in either place (P29)
- home / change site: `the ledger instrument lane — back the ts invariant with a gate (tools/ledger.py)`
- recorded_at: 2026-10-04T22:14:01Z

## 6. Lens T T-1 (CRITICAL): Task telemetry is not session-scoped; the 'unit cost per task' is whole-factory spend over an unbounded claim window
- home / change site: `the ledger/telemetry lane — thread session_id through extract_task_telemetry`
- recorded_at: 2026-10-04T22:14:32Z

