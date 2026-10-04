# Lens T — Token Economics & Cost-Per-Success
## Adversarial audit, cycle 20260927-c1

**Revision audited:** `git -C /root/agent-factories rev-parse HEAD` → `e679687c683ed56d4a4de9ecf43495366b0508ae`

**Surfaces read (mapped by CORPUS.md):** `tools/telemetry.py` (376 lines, full), `tools/brain_metrics.py`
(483 lines, full), `tools/compaction_rate.py` (214 lines, full), `tools/insights.py` (cost/token paths),
`tools/audit.py` (cost-per-success paths, lines 120–660, 2590–2800), `tools/field_predicate.py` (trailer
readers), `tools/ledger.py` (the close guard, lines 1071–1697), `evidence/ledger.jsonl` (2248 rows),
the live OpenCrabs SQLite schema, `docs/review-lenses.md`, `docs/processes.md`,
`docs/measurement-procedure.md`, `docs/quality-criteria.md`.

### METHOD NOTE — a display hazard that produced a false Critical, and how I neutralised it

The harness's text rendering of tool output in this session intermittently substituted a three-byte
window: the ASCII bytes `end_epoch=` were rendered as `end_epond_epoch=`, and `end_epond_epoch` in my
own probe input rendered identically. Both are *impossible* in Python (a keyword argument cannot contain
`=`). I resolved every quote that mattered at the byte level. The file's line 360 byte list is
`[...,101,110,100,95,101,112,111,99,104,61,101,110,100,95,101,112,111,99,104,44]` = `end_epoch,`
(sha256 of the line `48c62131772140ea1652fa50b9fd9bb6f346fcbd49d9a675201a9f7189ea3a90`), i.e. the
**correct** keyword argument `end_epoch=end_epoch,`; `grep -c "end_epond_epoch"` = 1 and
`grep -c "end_epond"` = 0; `ast.parse(tools/telemetry.py)` is clean and the tool runs. **There is no such
defect.** I flag it because a lens that trusted the rendered text would file a spurious Critical. Every
quote below was confirmed by byte list, sha256, or a boolean membership probe, not by eyeball.

---

## FINDING T-1 — CRITICAL: task telemetry is not session-scoped; the "unit cost per task" is whole-factory spend over an unbounded claim window

**(1) File Locator**
- `tools/ledger.py:1514`
- `tools/telemetry.py:243` (`extract_task_telemetry`) → `tools/telemetry.py:286` (`extract_window_telemetry(session_id=session_id, …)`)
- `tools/audit.py:591`

**(2) Verbatim Quote**
`tools/ledger.py:1514` (inside `cmd_append`, which spans 1071–1697):
```
            telem = (extract_task_telemetry(args.subject, ledger_path=target_ledger)
```
`tools/telemetry.py:286`:
```
    result = extract_window_telemetry(
        db_path=db_path,
        session_id=session_id,
        start_epoch=start_epoch,
    )
```
`tools/telemetry.py:184` (the window predicate):
```
                WHERE {' AND '.join(where_clauses)} AND role = 'assistant'
```

**(3) Defect Analysis.** The writer never passes a session. `session_id` defaults to `None`, so
`extract_window_telemetry` builds only `created_at >= ?` / `created_at <= ?` — it sums **every assistant
message in the database across every session** for the window `[last claim row for the subject, now]`.
The very same function computes the writer's own session three hundred lines earlier —
`tools/ledger.py:1122`: `    session_id = None if fixture else writing_session_id()` — and simply does
not thread it into the measurement. The capability exists and is even tested (`tests/test_telemetry.py:91`
exercises `session_id=` filtering), and the CLI can pass `--session` (`tools/telemetry.py:355`), but the
**production append path cannot**. Consequence: `cost_usd`, `tokens_in`, `tokens_out`, `turns` and
`duration` on a close row are factory-wide aggregates stamped `telemetry=measured`, and
`tools/audit.py:591` divides that number by accepted subjects:
```
    cost_per_successful_task = (total_cost_usd / successful_closed_tasks) if successful_closed_tasks > 0 else 0.0
```
The law this violates is the factory's own definition — `docs/processes.md:70`:
`| | \`cost per successful task\` | Total resources consumed ÷ accepted outputs |`. "Total resources
consumed" by *this* task is what is being named; the instrument measures the whole box.

Measured receipts in `evidence/ledger.jsonl` (read via the factory's own `declared_telemetry` parser):
- `n=1319` (close, subject `#123`): `cost_usd=3663.7563 tokens_in=480194717 tokens_out=13443640902 turns=4877 duration=577792s telemetry=measured` — a **6.69-day** window (claim `n=781` at `2026-09-20T17:17:29Z`, close at `2026-09-27T09:48:19Z`).
- `n=1490` (close, subject `#141`): `cost_usd=3944.7534 … duration=525894s telemetry=measured` (6.09 days).
- `n=901` (close, subject `#122`): `… cost_usd=538.7551 … telemetry=measured duration=8s …` — the row itself carries a window of **8 seconds**, yet the same trailer's `tokens_out=1940137518` and the claim→close span (`n=778` `2026-09-20T16:59:50Z` → `2026-09-22T00:51:19Z`) is 1.31 days. The `duration` and the token/cost figures describe different things and neither is this task.

The implemented figure is `cost_per_successful_task_usd = 143.4715` (total `12051.6041` ÷ 84 accepted
subjects). Because the numerator is a sum of overlapping factory-wide windows, this is not a unit cost
and cannot be compared across workflows — which is exactly lens check 1 (`docs/review-lenses.md:137`).

**(4) Actionable Remediation.** Thread the writer's session into the extractor at the single production
call site — `session_id` is already in scope:
```
telem = (extract_task_telemetry(args.subject, session_id=session_id, ledger_path=target_ledger)
         if extract_task_telemetry else None)
```
and make `extract_task_telemetry` refuse an empty `session_id` (or accept `session_id` as a required
keyword) so the factory-wide default cannot be reached silently. Add a gate that every
`telemetry=measured` close row's window is a subset of one session's `messages` rows.

---

## FINDING T-2 — HIGH: `tokens_out` is not output tokens; the schema exposes no output-token column

**(1) File Locator**
- `tools/telemetry.py:181` (the SELECT list) and `tools/telemetry.py:191` (the assignment)

**(2) Verbatim Quote**
`tools/telemetry.py:180-191`:
```
                    COALESCE(SUM(input_tokens), 0),
                    COALESCE(SUM(token_count), 0),
                    COUNT(*)
                FROM messages 
                WHERE {' AND '.join(where_clauses)} AND role = 'assistant'
            """
            cur.execute(msg_query, params)
            row = cur.fetchone()
            if row:
                cost = float(row[0] or 0.0)
                tokens_in = int(row[1] or 0)
                tokens_out = int(row[2] or 0)
```
The live schema (read via `sqlite3` `sqlite_master`, read-only):
```
CREATE TABLE "messages" (
    … token_count INTEGER,  -- Simplified from separate input/output tokens
    cost REAL, input_tokens INTEGER, thinking TEXT, cache_creation_tokens INTEGER,
    cache_read_tokens INTEGER, duration_secs INTEGER, …)
```

**(3) Defect Analysis.** `input_tokens` is a real column, so `tokens_in` is a real input count.
`token_count` is **not** an output count: the schema comment says it was "Simplified from separate
input/output tokens", there is **no `output_tokens` column at all**, and the values are impossible as
outputs. Measured from the live DB (read-only, rowid-bounded to avoid the unindexed scan):
- one assistant row: `token_count=10944120`, `input_tokens=115136` (ratio **95×**);
- one assistant row: `token_count=1037388`, `input_tokens=86032`;
- a 10-row sample ratios: 2.96, 48.99, 39.12, 95.05, 29.53, 19.87, 6.18, 46.40, 51.19, 3.93.

No model emits 10.9 M output tokens in one message. `token_count` is a total/context quantity (input +
cache + output + thinking), and mapping it to `tokens_out` means every `tokens_out=` in the ledger —
e.g. `n=901 tokens_out=1940137518`, `n=1319 tokens_out=13443640902` — is a mislabelled total. The lens's
own evidence format asks for a "token breakdown (input/output/cache)" (`docs/review-lenses.md:141`);
the instrument cannot produce an output figure from this substrate.

**(4) Actionable Remediation.** Either (a) rename the emitted key to what it is (`context_tokens=` or
`token_count=`) and drop the pretence of an output split, or (b) derive output as
`token_count - input_tokens - cache_read_tokens - cache_creation_tokens` if that identity is verified
against a row whose true output is known, and label the derivation. Do not ship `SUM(token_count)` as
`tokens_out`.

---

## FINDING T-3 — HIGH: model right-sizing (lens check 2) has no instrument; `model` is never read

**(1) File Locator**
- `docs/review-lenses.md:138` (the requirement) — no corresponding mechanism in `tools/telemetry.py`

**(2) Verbatim Quote**
`docs/review-lenses.md:138`:
```
  2. **Model Tier Right-Sizing:** Verify that heavy reasoning models (high cost) are not assigned to mechanical triage or deterministic formatting tasks where lightweight models suffice.
```
The duty is stated in law too — `docs/processes.md:77`:
```
  budget, tool payload footprint, turn economy, and model tier selection (using
```

**(3) Defect Analysis.** A model-attribution join is *possible* — the schema carries `sessions.model`
(`model TEXT`) and `usage_ledger.model` (`model TEXT NOT NULL DEFAULT ''`). But no factory tool reads
either: `grep -rn "select model\|SELECT model\|model from\|model FROM\|\.model" tools/telemetry.py
tools/insights.py tools/brain_metrics.py tools/compaction_rate.py` returns **nothing**, and
`tools/telemetry.py`'s SELECTs list only `cost`, `input_tokens`, `token_count`. So "expensive reasoning
models are not used for mechanical tasks" is unverifiable by any instrument in this factory. The lens
check is un-executable; a reviewer can only assert compliance from faith. `docs/quality-criteria.md:289`
even concedes the neighbouring point — "Throughput and cost-per-successful-task already capture what they
are proxies for" — but nothing captures *which model* incurred the cost.

**(4) Actionable Remediation.** Add a model-attribution leg to `tools/telemetry.py`:
`SELECT s.model, COUNT(*), SUM(m.cost) FROM messages m JOIN sessions s ON s.id=m.session_id WHERE … GROUP BY s.model`,
printed per window; then the mechanical-vs-reasoning question becomes a reading, not a claim.

---

## FINDING T-4 — HIGH: prompt-cache efficiency (lens check 3) has no instrument; the substrate already records the columns

**(1) File Locator**
- `docs/review-lenses.md:139` (the requirement)
- `tools/telemetry.py:176-192` (the messages SELECT — reads neither cache column)
- live schema: `messages(… cache_creation_tokens INTEGER, cache_read_tokens INTEGER …)`

**(2) Verbatim Quote**
`docs/review-lenses.md:139`:
```
  3. **Prompt Cache Efficiency:** Audit static instruction prefixes to ensure high prompt cache hit rates (>80%) and eliminate cache-busting dynamic timestamps in primary system prompts.
```
`grep -rln "cache_read_tokens\|cache_creation_tokens" tools/` → **no output** (no reader exists).

**(3) Defect Analysis.** The OpenCrabs substrate already persists per-assistant-message cache accounting
(`cache_creation_tokens`, `cache_read_tokens` — confirmed in the live schema). Not one factory tool reads
either column, so no cache-hit rate is computable from any instrument here, and there is no check for
cache-busting dynamic timestamps. The lens asks for a >80% hit rate; the factory cannot state its own
rate at all. The SKILL law claims prompt caching is in scope (`skills/meta-factory/SKILL.md:496`), so the
gap is between declared scope and mechanism (P29: a declared reading with no instrument is dead text).

**(4) Actionable Remediation.** Add a cache leg:
`SUM(cache_read_tokens) / NULLIF(SUM(cache_read_tokens)+SUM(cache_creation_tokens),0)` per window, printed
beside the cost reading, plus a static check that the always-injected brain prefix carries no per-turn
timestamp (a cache-buster).

---

## FINDING T-5 — MEDIUM: the money metric double-counts duplicate close rows and run/close pairs

**(1) File Locator**
- `tools/audit.py:471-483` (the accumulation) and `tools/audit.py:591` (the division)

**(2) Verbatim Quote**
`tools/audit.py:475-483`:
```
        # `cost_usd=26` is a census — "26 close rows carry cost_usd" — and it became
        # the second-largest single cost in the ledger. Scope spans EVERY event, not
        # `close` only: 22 `run` rows carry canonical trailer telemetry, so an
        # event-scoped predicate would drop them.
        declared = declared_telemetry(detail)
        for key, value in declared:
            try:
                if key in ("cost_usd", "cost"):
                    total_cost_usd += float(value.rstrip("$"))
```

**(3) Defect Analysis.** The sum spans *every* event and never dedupes by subject, so one task's spend
is counted once per row that carries it. Measured in `evidence/ledger.jsonl`:
- **run/close pairs with identical cost on both rows:** subjects `#13`–`#19` (e.g. `n=54` run
  `cost_usd=0.0150` and `n=55` close `cost_usd=0.0150`), plus `#40`. Redundant total **0.0990**.
- **duplicate close rows for one subject:** `#140` (`n=930` and `n=931`, both `cost_usd=35.4988`),
  `#84` (`n=1509`/`n=1511`, both `0.3420`), `#169` (`n=1361`=`8.9754`, `n=1363`=`0.6076` — **same head
  `1b931dd`, two minutes apart, 15× apart in cost**), `#202` (`n=1502`=`0.2517`, `n=1504`=`1.4981`).
  Exact-duplicate inflation **35.8408**.
- Total duplicate inflation **35.9398 USD** of `total_cost_usd = 12051.6041` (0.30%).

The denominator is distinct subjects (`tools/audit.py:589-591`), so the numerator is inflated relative to
the denominator — a money figure that only ever reads high. The `#169`/`#202` pairs are the sharper
defect: the same subject closes twice with *different* costs (two windows), and both are summed. The
tool's own docstring admits the class is unguarded — `tools/telemetry.py:40`:
```
# retried -- writing a duplicate pair each time (measured: n=1502/1504 and
```

**(4) Actionable Remediation.** Dedupe the money sum by `(subject, event)`, taking the last close row per
subject (the ledger already treats the work unit as a distinct closed subject); or restrict
`total_cost_usd` to close rows and reconcile the 22 run rows in a separate printed count.

---

## FINDING T-6 — MEDIUM: the measurement covers a minority of closes by construction

**(1) File Locator**
- `tools/telemetry.py:44-45` (the budget rationale)
- `evidence/ledger.jsonl` (per-row canonical `telemetry=` provenance)

**(2) Verbatim Quote**
`tools/telemetry.py:44-47`:
```
# The value is a DECLARED MULTIPLE of the measured worst case: 30 s is 0.28x of the
# 106.1 s measurement, so on the measured population the query is cut off and the row
# ships the STATED ABSENCE `telemetry=unavailable` (#130) rather than a row of zeros
```

**(3) Defect Analysis.** The instrument deliberately runs a budget *below* the measured worst case, so it
truncates and ships no measurement. Read per-row (last `telemetry=` token in the canonical trailer) over
280 close rows: **82 `measured` (29.3%), 92 `unavailable` (32.9%), 105 with no telemetry token at all
(pre-guard historical rows)**. So the headline cost-per-success figure rests on under 30% of closes, and
the majority of closes contribute nothing. The docstring states the budget as a deliberate trade, but the
net effect is that the economics reading is a sample, not a census — and no surface says so beside the
`$143.4715` figure.

**(4) Actionable Remediation.** The scan is the cost, not the window (the docstring says so), and the
schema has no index on `messages.created_at` (`indexes: sqlite_autoindex_messages_1, idx_messages_session_id`).
The durable fix is an index on `messages(created_at)` (file upstream with the OpenCrabs dev factory via
the client-supplier loop), which makes the window cheap and removes the truncation; until then, print the
measured/unavailable coverage beside the cost figure so a reader knows the denominator.

---

## FINDING T-7 — LOW: brain-metrics leg A states two char/token ratios and implements one

**(1) File Locator**
- `tools/brain_metrics.py:71-72` vs `tools/brain_metrics.py:139`, `:162`, `:274`

**(2) Verbatim Quote**
```
CHARS_PER_TOKEN = 3.5
CHARS_PER_TOKEN_NOTE = "3.5 chars/token English markdown, 1.7 Cyrillic"
```
The note is printed as the unit law (`tools/brain_metrics.py:228`), but every computation divides by the
single constant: `out["tokens"] += round(size / CHARS_PER_TOKEN)` (lines 139 and 162) and
`second = round((a["bytes"] + b["bytes"]) / CHARS_PER_TOKEN)` (line 274).

**(3) Defect Analysis.** The instrument's stated unit law names a Cyrillic ratio (1.7) it never applies.
A Cyrillic-bearing always-injected file would have its token proxy understated by ~2×, and leg A's token
figure is the numerator of the headline "share of the window" (`100.0 * a['tokens'] / w`). Live files are
near-English today (`USER.md`: 11 Cyrillic characters of 4,341; `SOUL.md`/`AGENTS.md`: 0), so the current
figure is safe — but the docstring's promise and the code's behaviour diverge, which is the exact
"unit confusion" the docstring cites as its own reason to exist.

**(4) Actionable Remediation.** Either implement the per-script ratio (measure each file's Cyrillic
fraction and interpolate between 3.5 and 1.7), or delete the "1.7 Cyrillic" clause so the note states one
ratio and matches the code.

---

## FINDING T-8 — LOW: the context-inflation guard (lens check 4) is disclaimed by both instruments

**(1) File Locator**
- `docs/review-lenses.md:140` (the requirement)
- `tools/compaction_rate.py` (BOUNDS point 4) and `tools/brain_metrics.py` ("PRINTED, NEVER GATED")

**(2) Verbatim Quote**
`docs/review-lenses.md:140`:
```
  4. **Context Inflation Guard:** Audit turn context growth; trigger compaction or subagent delegation before context sizes exceed cost-effective thresholds.
```
`tools/compaction_rate.py` (BOUNDS): `(4) PRINTED, NEVER GATED.`
`tools/brain_metrics.py` (docstring): `PRINTED, NEVER GATED. No threshold in this file fails a run — the owner judges.`

**(3) Defect Analysis.** The lens asks for a **trigger** — an action when context exceeds a cost-effective
threshold. Both factory instruments that measure the relevant quantities (`compaction_rate.py`:
compactions/turns; `brain_metrics.py` leg C: post-compaction input tokens) explicitly refuse to gate, on
the owner's ruling that a threshold is the owner's to set. So lens check 4 is unsatisfiable by any current
instrument, and the lens catalogue and the instruments disagree about whether a trigger is owed. This is a
catalogue-vs-mechanism drift rather than a code bug.

**(4) Actionable Remediation.** Reconcile the two: either amend `docs/review-lenses.md:140` to say the
check is a *printed reading with a named flag at threshold* (no gate), or state in the instruments that a
threshold trigger is deliberately out of scope and name the owner as its only gate.

---

## SURFACES CHECKED AND FOUND CLEAN (with method)

- **`tools/compaction_rate.py` (214 lines, full read).** The `SETTLE` regex and the compaction predicate
  are coherent, and both match live data: the daemon log carries
  `… +00:00  INFO … opencrabs::channels::telegram::turn_settle: …: Telegram settle: session 530c29ec-596e-43a4-9c7e-1b6dfc3cd870 — outcome ✅ Finished — block -1`,
  which `SETTLE` (`^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.\d+)?\+00:00.*Telegram settle: session (?P<sid>[0-9a-f-]{36})`)
  matches. Sessions that compact but never settle are correctly reported as NOT MEASURABLE rather than as
  an infinite ratio; the reading is memory-conserving (streams the log, reads the DB over a `mode=ro` URI).
  No defect found.
- **`tools/brain_metrics.py` leg C.** The `COMPACTION` regex is a real mechanism against live logs —
  `grep -m3 "Compaction: sending"` returned e.g.
  `… context.rs:1015: Compaction: sending 83 / 83 messages to summarizer (93322 / 200000 input tokens, reserving 9000 for output)`,
  which the regex parses.
- **`tools/brain_metrics.py` ORACLE provenance.** Every constant matches the cited snapshot file
  `evidence/brain-metrics-2026-09-19.md` exactly: `588`/`72,393` (file line 25), `452`/`32,247` (lines
  38–39), `29,897` (line 54), `66,393`/`70,493`/`97,608` and `n=2,011` (lines 69–76). The "snapshot is
  cited, not re-asserted" claim holds.
- **`tools/telemetry.py` budget/absence mechanism (apart from T-6's coverage effect).** The
  `_budget_secs` fallback, the progress-handler abort, and the `budget_exceeded → None →
  telemetry=unavailable` chain are internally consistent; `_budget_exceeded` is defined before the `try`
  so the handler cannot raise `NameError`.
- **`tools/field_predicate.py` trailer readers.** `declared_telemetry` correctly reads only the canonical
  trailing run (`trailer_tokens`), so the `cost_usd=26`-as-census class (issue #90) is genuinely closed at
  that layer. My `total_cost_usd` reproduction using `declared_telemetry` = `12051.6041` matches
  `audit.py`'s own scope.

---

## SUMMARY

**8 findings: 1 Critical, 3 High, 2 Medium, 2 Low.** The single most severe is **T-1**: the close-row
telemetry window is not session-scoped — `tools/ledger.py:1514` calls `extract_task_telemetry(args.subject, ledger_path=target_ledger)`
without the `session_id` that `cmd_append` already holds at `tools/ledger.py:1122`, so
`extract_window_telemetry` sums **every session's** assistant rows over `[last claim, now]` and stamps the
result `telemetry=measured` on the task's close row; `tools/audit.py:591` then divides that factory-wide
total by accepted subjects to publish `cost_per_successful_task_usd = 143.4715`, which is not a unit cost.
Receipted by ledger `n=1319` (`cost_usd=3663.7563 … duration=577792s`), `n=1490` (3944.7534 / 525894s) and
`n=901` (538.7551 with `duration=8s` against a 1.31-day claim→close span). The measurements behind this
report came from: `git -C /root/agent-factories rev-parse HEAD`; full reads of the four mapped tools;
`grep -rn` for `cost_usd`, `tokens_in/out`, `cache_read_tokens`, `model`, and every caller of
`extract_task_telemetry`; a read-only `sqlite3` dump of `sqlite_master` plus rowid-bounded
`SELECT token_count, input_tokens` samples; a Python reproduction of `audit.py`'s cost scope using
`tools/field_predicate.py::declared_telemetry` (total `12051.6041`, dup inflation `35.9398`, denominators
84/274); per-row canonical `telemetry=` provenance counts over 280 close rows (82 measured / 92
unavailable / 105 none); and live-log `grep` confirming the `compaction_rate` and `brain_metrics` leg-C
predicates match real daemon lines. No files under `/root/agent-factories` were modified.
