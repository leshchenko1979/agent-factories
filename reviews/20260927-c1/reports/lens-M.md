# Lens M — Value Stream, Flow & WIP Stagnation — Adversarial Audit

**Cycle:** 20260927-c1 · **Lens:** M (Family 4 — State, Delivery & Flow)
**Repo audited (read-only):** `/root/agent-factories`
**Revision pinned:** `e679687c683ed56d4a4de9ecf43495366b0508ae` (`git -C /root/agent-factories rev-parse HEAD`)
**Ledger read instant:** 2026-10-04T21:35:59Z (2,248 rows, `n=1..2248` monotonic, 0 malformed JSON)
**Author isolation:** none — this auditor shares no context with the authoring lane.

**Method (all counts READ, not estimated):** parsed `evidence/ledger.jsonl` with Python; ran the
factory's own `python3 tools/audit.py --json --no-gates` at HEAD; `grep`/`sed` on law and tools;
`cron_manage list`; `wc`/`ls`. Numeric ledger line number == the row's `n` (verified: 2,248 rows,
`n` strictly `i+1`).

---

## F1 — The factory's own flow acceptance criterion is violated ~46× and is upheld by nothing (SEVERE)

**(1) Locator:** `docs/processes.md:136`
**(2) Verbatim quote:**
> `  3. Average task execution lead time $\le 30$ minutes with queue dwell time $< 5\%$ of lead time achieved via Dual-Rail push handoffs.`

**(3) Defect analysis.** This is a stated *custom acceptance criterion* of Process 1 (the Value
Stream), written as a checkable number. The factory's own tool computes the quantity and reports it
against it — and fails it by two orders of magnitude:

- `python3 tools/audit.py --json --no-gates` at HEAD returns
  `delivery.avg_lead_time_sec = 82423.9` over `len(lead_times_sec) = 279` sampled subjects
  → **22.9 hours**, i.e. **45.8× the ≤30-minute target** (`82423.9 / 1800`).
- Median lead time `8,461.0 s` (2.35 h); max `1,149,653 s` (319.3 h).
- `213 of 279` subjects exceed 1,800 s; `58 of 279` exceed 24 h.

The mechanism is `tools/audit.py:546` (`lead_times_sec.append(diff)`) with
`tools/audit.py:583` (`avg_lead_time = sum(...)/len(...)`); the report line is
`tools/audit.py:2600` (`| **Avg Task Lead Time** | \`{...}s\` | Mean intake→close duration over {N} sampled subjects |`).
So the number is measured every run — and **no gate, test, or process consumes it**:

- `grep -rn "dwell\|lead_time\|lead time\|avg_lead\|SLA" tests/*.py` → **exit 1, zero matches**
  across all **89** test files.
- `grep -rn "throughput" tests/*.py` → **zero matches**.
- The factory states this itself: `docs/projects/hygiene-surfaces.md:94` — *"WIP stagnation is a
  Lens M finding, not a gate."*

This is the exact class `P29` (`docs/best-practices.md:531`, *"Every law needs an active process or
mechanical gate upholding it … is dead text"*) exists to catch: a numeric acceptance criterion the
factory fails continuously, computed on every audit run, that nothing reads as pass/fail. The
criterion is not merely unmet — it is **unfalsifiable in practice**, because no surface turns it red.

**(4) Actionable remediation.** Pick one and make it mechanical, in this commit:
- *Keep the target:* wire `avg_lead_time_sec` (and a dwell ratio, see F2) into `tools/audit.py`'s
  gate set with a threshold the factory can actually hold, printing the population beside the
  verdict (the pattern `first_pass_yield_coverage` already uses); **or**
- *Strike it:* delete the `≤ 30 minutes / < 5%` clause from `docs/processes.md:136` and replace it
  with the measured reality plus a pointer to `tools/audit.py`, so the law stops asserting a number
  the ledger refutes on every run. Leaving it as written is the worst option: it trains readers to
  treat a 46× breach as normal.

---

## F2 — The queue-dwell law is unmeasured, and the one tool whose docstring claims to measure it does not (SEVERE)

**(1) Locator:** `tools/synthesize_insights.py:255` (function docstring) — and the law it claims to serve at `docs/methodology/02-quality-management.md:37`
**(2) Verbatim quotes:**
> `tools/synthesize_insights.py:255:` `    """Mines queue dwell time, turn count distributions, and yield drops from ledger.`
>
> `tools/synthesize_insights.py:7:` `  3. evidence/ledger.jsonl (high turn counts, lead time outliers, queue dwell)`
>
> `docs/methodology/02-quality-management.md:37:` `| **Queue Dwell Ratio** | Proportion of lead time spent idling in queues vs. active execution. | $\frac{t_{\text{claim}} - t_{\text{intake}}}{t_{\text{close}} - t_{\text{intake}}}$ | $< 20\%$ |`

**(3) Defect analysis.** The brief's rule holds exactly here: *a claim in a docstring is not a
mechanism.* The docstring at `synthesize_insights.py:255` promises queue-dwell mining, but reading
the body (`mine_ledger_telemetry()`, `tools/synthesize_insights.py:253–324`) shows it computes
**only** `high_turns` and a yield:

- `grep -n "dwell\|claim\|intake\|t_close\|t_claim" tools/synthesize_insights.py` → **only lines 7 and
  255**, both docstrings. There is **no intake/claim/close timestamp subtraction anywhere**.
- The only `category=` values the function emits are `"yield_drop"` (`:304`) and
  `"high_turn_convergence"` (`:318`). There is no `queue_dwell` pattern.
- `grep -rn "dwell" tools/*.py` across the whole tool surface → **three hits, all non-mechanisms**:
  `tools/review.py:182` (the lens-brief prose) and `tools/synthesize_insights.py:7,255` (docstrings).

So the Queue Dwell Ratio — a named factory metric with a `< 20%` target (`02-quality-management.md:37`)
and a stricter `< 5%` restatement (`processes.md:136`) — is computed by **nothing**. I computed it by
hand from the ledger: mean dwell ratio **0.696 (69.6%)**, with **240 of 267** subjects above 5% and
**218 of 267** above 20%. The law's target is missed by roughly **14–35×**, and the drift was
invisible because no surface reads it.

**(4) Actionable remediation.** Either implement the metric where the docstring already claims it —
`intake`, `claim`, `close` are all in the ledger; the ratio is `(t_claim − t_intake)/(t_close −
t_intake)` — and emit a `queue_dwell` pattern, or **delete the claim from both docstrings** (`:7`,
`:255`) and delete/relabel the two dwell targets. Do not leave a docstring asserting a mining
capability the code does not have; that is precisely the "leaky tool" the isolation rule guards against.

---

## F3 — WIP stagnation is a live livelock: 27 open items past 24 h, 20 re-dispatched ≥2×, oldest 16.2 days; the detector fires but the remedy never drains (SEVERE)

**(1) Locator:** `evidence/ledger.jsonl:237` (intake of #37) and `evidence/ledger.jsonl:2167` (the re-dispatch that reads its own age)
**(2) Verbatim quotes:**
> `evidence/ledger.jsonl:237:` `{"n": 237, "ts": "2026-09-18T15:21:57Z", "event": "intake", "actor": "triage", "subject": "#37", …}`
>
> `evidence/ledger.jsonl:2167:` `"detail": "RE-DISPATCH of #37 -- OWED 15.44 d at the stall-census read 2026-10-04T06:08:15Z (declared threshold 1.0 d), the board still carries it OPEN and no lane has ever claimed it. …"`

**(3) Defect analysis.** Measured against the ledger's last instant (`2026-10-04T20:52:47Z`):

- **34** numeric subjects carry an `intake` row and **no `close`**; **27** of them are older than
  24 h. Oldest: **#37 at 389.5 h (16.2 d)**, #48 385.4 h, #49 384.8 h, #67 374.3 h.
- These are not idle backlog — they are **re-dispatched repeatedly and never claimed**. The 34 open
  items carry **59 `dispatch` rows**; **20 never-claimed items have ≥2 dispatches**, one (**#48**)
  has **4**, and #118/#144/#162/#263 have 3 each.

The mechanism is not absent, which sharpens the defect. `tools/patrol_host_state.py:2161`
(`stall_census_leg`) *does* detect these — its own 2026-10-04T06:08:15Z run reported
*"23 never claimed past the declared threshold of 1.0 d"* (`evidence/ledger.jsonl:2188`, `problems: 23`).
But the leg's docstring states its limit: `tools/patrol_host_state.py:2170–2171` —
> `SHAPE (c), ruled at n=1857: this leg DETECTS AND PRINTS; the ACT stays a lane act. It NOTIFIES NOTHING.`

and `TEMPLATE/roles/triage.md:94` names the outcome explicitly — *"DISCHARGED is not CLEARED."* The
remedy (re-dispatch) is defined to leave the line standing at its original age. The result is a
**livelock**: Triage re-dispatches #48 a fourth time, the census re-reports it, and no `claim` ever
lands. `P27` (`docs/best-practices.md:480–500`) requires the watchdog to *"Escalate blocked or failed
tasks to HQ or trigger a retry"* — the retry fires indefinitely and the exit condition is never met.

Compounding it: the census threshold is **1.0 day** (`tools/patrol_host_state.py:184`,
`STALL_CENSUS_THRESHOLD_DAYS = 1.0`), a **48× relaxation** of the law's 30-minute SLA. A 30-minute
SLA breach is therefore *structurally invisible* to the only detector that exists — the census cannot
report an item until it is 47 hours past the threshold the law names.

**(4) Actionable remediation.** (a) Add a bounded re-dispatch rule: after *N* re-dispatches with no
`claim`, the item escalates to HQ/owner or is closed on the board with a recorded disposition — so the
livelock has an exit. (b) Reconcile the threshold: if the 30-minute SLA is real, the census must
report at that scale (or the law must name 1.0 d as its own); the two numbers must not sit 48× apart
in one system. (c) State, in the census output, the count of items *past SLA* separately from items
past the census threshold, so the red reads at the law's scale.

---

## F4 — The census explicitly excludes claimed units, and no leg covers "claimed-but-silent" — the Triage card's >30 m duty is unmechanized (MAJOR)

**(1) Locator:** `tools/patrol_host_state.py:2208` (the OWED predicate) vs `TEMPLATE/roles/triage.md:23`
**(2) Verbatim quotes:**
> `tools/patrol_host_state.py:2208:` `    A unit is therefore OWED when it is in the population, carries NO \`claim\` row and NO`
>
> `TEMPLATE/roles/triage.md:23:` `  - **CLAIMED-BUT-SILENT** — a worker holding a claim with no progress/update after`
> `TEMPLATE/roles/triage.md:24:` `    *N* cycles or > 30 m. Notify that worker through \`session_notify\`, or escalate to \`HQ\`.`

**(3) Defect analysis.** The Triage card declares a **>30 m** duty on a *claimed-but-silent* lane —
the tighter, earlier predicate. The stall census covers only the *other* half: by its own predicate
(`:2208`) a unit leaves the population the moment it carries a `claim`, so a claimed-then-quiet lane
is **never** in scope. I enumerated every patrol leg
(`grep -n '"name": "' tools/patrol_host_state.py`) —
`board-intake, board-close, board-closed, board-ruling, cron-thinness, notify-receipt, duty-receipt,
canonicality-tier, stall-census, kit-drift, worktree, publish-freshness` — and **none is a
claimed-silent leg** (`grep -ni "claimed.but.silent\|claimed_silent" tools/patrol_host_state.py` → only
the two docstring lines that *disclaim* it, `:179, :188`).

The gap is live, not theoretical. Three subjects hold a `claim` with no `close` and are idle far past
30 m: **#201 idle 142.7 h**, **#251 idle 93.6 h**, **#252 idle 93.6 h** (plus #296 at 23.8 h). Under
`P29` this is dead text: a stated duty with no process or gate upholding it, and a real hole in the
flow law that the census's own design leaves open.

**(4) Actionable remediation.** Add a `claimed-silent` patrol leg keyed on the unit's last `claim` ts
vs `read_at`, reporting at the 30-minute scale the card names; or fold it into `stall_census_leg` as a
second population (claimed-but-quiet) beside the existing never-claimed one. Print both populations
with their thresholds, as the leg already does for its coverage counts.

---

## F5 — "Batch Size Control (P11)" cites a clause that says the opposite, and the check is unmeasurable (MAJOR)

**(1) Locator:** `docs/review-lenses.md:127` and `tools/review.py:186` vs `docs/best-practices.md:177`
**(2) Verbatim quotes:**
> `docs/review-lenses.md:127:` `  3. **Batch Size Control (P11):** Enforce small task batching. Flag tasks touching >3 files or >200 lines without explicit architectural decomposition.`
>
> `tools/review.py:186:` `            "3. Enforce single-piece flow and batch size limits (P11)."`
>
> `docs/best-practices.md:177:` `## P11 — One writer per state surface`
>
> `tests/test_law_coverage.py:62:` `    "P11": ["tools/ledger.py", "tests/test_single_writer.py", "tests/test_ledger_no_shrink.py"],  # Single writer per surface (flock)`

**(3) Defect analysis.** `grep -rn "P11"` across the repo returns six sites: two bind **P11 =
single-writer** (`docs/best-practices.md:177`; `tests/test_law_coverage.py:62`), and two — the lens
catalogue and the brief generator that produced *this* brief — bind **P11 = batch-size control**. Both
disagreeing citations ship to every member factory (`TEMPLATE/docs/review-lenses.md:127`,
`TEMPLATE/tools/review.py:186`). A reader who follows "(P11)" from the lens lands on the single-writer
rule, which says nothing about batching.

Worse, the check it names is **unfalsifiable from the data the factory keeps**. The ledger row schema
is fixed at `{n, ts, event, actor, subject, detail, session, refs}` (measured over all 2,248 rows);
there is **no** files-touched or lines-changed field, and
`grep -rn "files_touched\|lines_changed\|batch_size\|files_changed" tools/*.py docs/*.md` → **zero
matches**. So "Flag tasks touching >3 files or >200 lines" cannot be evaluated by any reader, human or
script, from any surface this repo writes. There is likewise no law defining a batch limit — the
string ">3 files" / "200 lines" appears only in the two lens-catalogue sites.

**(4) Actionable remediation.** Choose one: (a) correct the citation in `docs/review-lenses.md:127`
and `tools/review.py:186` to name the clause actually intended (or add a real batch-size law as its
own `P##`), and give it teeth by recording `files`/`lines` (or a commit `--numstat` reference) in the
close row so the check has an input; or (b) delete the "Batch Size Control (P11)" check and the
"(P11)" from the brief generator, since neither a law nor a data field backs it. Apply the fix to the
`TEMPLATE/` twins in the same change (`test_template_sync.py` gates the pair).

---

## F6 — The restated "Avg lead time" figure has drifted 27% and nothing re-derives it (MINOR)

**(1) Locator:** `docs/growth-stages.md:223`
**(2) Verbatim quote:**
> `| Avg lead time | **64,817.3 s** | — |`

**(3) Defect analysis.** This derived figure is restated in a doc with **no denominator** (the third
column is `—`). The live value at HEAD is `avg_lead_time_sec = 82,423.9` — a **+27.2% drift** since the
figure was written. `SKILL.md` §11 states that a figure *derived* from a surface must be updated in
the same commit that invalidates it, and that ledger-owned rate figures are "not restated at all."
The figure does sit under a dated header (*"Live self-metrics (2026-10-01T06:15:32Z, HEAD 78fa86b)"*),
which mitigates it, but it is presented as a bare metric beside `Ledger events` and `Rework share` —
reading as current, not as a snapshot of a superseded HEAD.

**(4) Actionable remediation.** Either drop the number and point to `tools/audit.py --json` as the
source (consistent with the "pointer, never a copy" discipline used elsewhere), or annotate the cell
with its read instant and HEAD so a reader cannot mistake a 2026-10-01 snapshot for the live value.

---

## Surfaces checked and found clean (explicit, per rule 3/5)

- **Ledger sequence integrity.** All **2,248** rows parse as JSON; `n` is strictly `1..2248` with no
  gaps (`all(rows[i]['n'] == i+1)` → `True`). No malformed rows. This part is sound.
- **Close-row population.** 280 `close` rows over **274** distinct closed subjects — the docstring's
  claim at `tools/audit.py` (work unit = distinct subject, not row) matches the data; re-closes are
  the 6-row difference. Correctly counted.
- **`intake`→`claim` ordering.** The documented inversion (claim before intake, a wake-latency race,
  `docs/…`/SKILL §4) is real but small: min dwell `−2,609 s`, a handful of instances — consistent with
  the law's "6 instances across 3 factories" note. Not a defect.
- **Cron pacemakers.** `cron_manage list` confirms `factory-triage-patrol`
  (`3673ffec-…`, `0 */6 * * *`, enabled, last run 2026-10-04 18:00 UTC) and `factory-measurement-daily`
  are live — `P28` is upheld for these. (Note: `docs/process-audit.md:233` describes an *"Execution
  watchdog … periodic (hourly)"*, but that file's own header, `docs/process-audit.md:3`, reads
  *"Status: proposed, not law. Nothing in this file is in force."* — so this is a proposal, not a
  violated law; flagged here only so no reader mistakes it for the live cadence, which is 6-hourly.)

---

## Summary

**Six findings (3 severe, 2 major, 1 minor).** The single most severe is **F1**: the factory's own
Value-Stream acceptance criterion — *"Average task execution lead time ≤ 30 minutes with queue dwell
time < 5% of lead time"* (`docs/processes.md:136`) — is violated by **45.8×** (live
`avg_lead_time_sec = 82,423.9` = 22.9 h, `tools/audit.py` at HEAD `e679687`) and is upheld by nothing:
zero of 89 tests reference lead time, dwell, throughput, or SLA, and the factory itself concedes
*"WIP stagnation is a Lens M finding, not a gate"* (`docs/projects/hygiene-surfaces.md:94`) — a P29
dead-text violation, not merely an unmet target. It is inseparable from **F2** (the dwell metric is
claimed by a docstring at `tools/synthesize_insights.py:255` and computed nowhere) and **F3** (a live
stagnation livelock: 34 open items, 27 past 24 h, 20 re-dispatched ≥2×, oldest #37 at 389.5 h).
Measurements that produced this: `python3 tools/audit.py --json --no-gates` at HEAD `e679687`
(`avg_lead_time_sec=82423.9`, `lead_times_sec n=279`); a Python parse of `evidence/ledger.jsonl`
(2,248 rows; per-subject intake/claim/close pairing; dwell-ratio mean 0.696; 34 open, 27 >24 h, 59
dispatch rows on them); `grep -rn "dwell\|lead_time\|SLA" tests/*.py` (exit 1, 0 matches);
`grep -n '"name": "' tools/patrol_host_state.py` (12 legs, no claimed-silent leg);
`git -C /root/agent-factories rev-parse HEAD` → `e679687c683ed56d4a4de9ecf43495366b0508ae`.
