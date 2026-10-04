# Lens P — Pacemaker & Autonomous Convergence

**Repo audited:** `/root/agent-factories` (READ-ONLY; no file created/modified/deleted under it)
**Revision pinned:** `git rev-parse HEAD` → `6bd9690d578c5bbc911537b95abe0ab0bc884c8c` (working tree clean at read time)
**Instant of audit:** 2026-10-04 ~21:10–21:20 UTC
**Lens scope (from `tools/review.py:119-127`, mirrored at `docs/review-lenses.md:65-70`):** Cron configuration, outer heartbeat loops, and autonomous task convergence — checks 1. 0-Token Quiescence (P28), 2. Goal State Convergence, 3. Dead Session Detection.

## Method / receipts

Commands actually run (all read-only): `git rev-parse HEAD`; `grep -rn` over `tools/ tests/ docs/`; `awk`/`sed`/`read_file` for every quoted locator; `sqlite3 "file:<home>/opencrabs.db?immutable=1"` over all four profile DBs (ops, family, oc348probe, code-spike); and the repo's own live runner driven in-process with `importlib` (no board/network legs) to obtain `cron_thinness_leg`'s real verdict. The instrument half of every quoted path was confirmed byte-identical to its `TEMPLATE/` twin (`cmp -s` → SAME for `docs/instruments/pacemaker.md`, `docs/review-lenses.md`, `docs/methodology/04-harness-binding.md`, `tools/patrol_host_state.py`, `tests/test_cron_thinness.py`, `tests/test_patrol_host_state.py`).

Live cron population measured from the ops profile home (`/root/.opencrabs/profiles/ops/opencrabs.db`), `enabled=1` rows only, exactly the predicate `docs/instruments/pacemaker.md:64-65` declares:

| metric | value (2026-10-04) | value the doc states (2026-09-27, `:71-76`) |
|---|---|---|
| enabled | **34** | 33 |
| with a cheap gate (`length(trigger_cmd)>0`) | **11** | 10 |
| waking a session (`deliver_to LIKE 'session:%'`) | **7** | 8 |
| gate **AND** session wake | **3** | 2 |
| with `set_goal` | **1** | 2 |
| gate **AND** session wake **AND** `set_goal` | **0** | 0 |

---

## P-1 — HIGH — The instrument's declared concept has four columns; its gates read two, so 0-token quiescence and goal convergence are ungated

**(a) LOCATOR:** `docs/instruments/pacemaker.md:37-42` (the concept table), `docs/instruments/pacemaker.md:211-214` (the §4 gate set), `tests/test_cron_thinness.py:277-293` (the predicate), `tools/patrol_host_state.py:1188-1191` (the live read).

**(b) VERBATIM QUOTE:**

`docs/instruments/pacemaker.md:39`
> `| `trigger_cmd` | the cheap pre-flight: a shell command run under `/bin/sh -c` (30 s timeout) **before** any agent turn. It watches; it never acts. |`

`docs/instruments/pacemaker.md:42`
> `| `set_goal` (+ `goal_template`) | the keeping-going. The fire sets an **active goal** in the target session, so the lane works the detected condition to completion rather than settling after one turn. Refused unless `deliver_to` targets a session. |`

`docs/instruments/pacemaker.md:213`
> `| `test_cron_thinness.py` | `gate_registry.py`, REQUIRED | required | the predicate is PURE over a list of rows and reads no live table, so it passes in a bootstrapped factory exactly as it does here — there is no `TEMPLATE` comparison or box-local fixture that would make it red |`

`tests/test_cron_thinness.py:291-293`
> `        name = _text(row.get("name")) or f"<row {index}>"`
> `        prompt = _text(row.get("prompt"))`
> `        deliver_to = _text(row.get("deliver_to")).strip()`

`tools/patrol_host_state.py:1189-1191`
> `                "select id, name, coalesce(deliver_to,''), coalesce(prompt,''), "`
> `                "coalesce(last_run_at,'') "`
> `                "from cron_jobs where enabled = 1"`

**(c) DEFECT ANALYSIS:** The instrument's own framing (`:29-31`) is that the concept *is* four columns — `trigger_cmd`, `trigger_on`, `deliver_to`, `set_goal` — and that "the property it upholds is the four columns above" (`:60-61`). But the only shipped gate (`test_cron_thinness.py`, `pacemaker_problems`) reads exactly three row keys: `name`, `prompt`, `deliver_to`. The live runner's SQL projects the same three plus `id`/`last_run_at` — `trigger_cmd`, `trigger_on` and `set_goal` are never selected. Therefore **column 1 (the 0-token gate) and column 4 (`set_goal` convergence) have no mechanical upholder anywhere in the repo.** `trigger_cmd`/`trigger_on` are read only by `tools/registry.py:1042` `is_trigger_gated_poll` for a *different* law (the 6 h lane-wake cadence floor, #289), and `set_goal` only by `tools/registry_render.py` for *display* (`:571-572`); neither judges the pacemaker's quiescence or convergence. This is a direct P29 violation ("Every law needs an active process or mechanical gate upholding it", `docs/best-practices.md:531-533`) sitting inside the factory's own instrument. It also makes the lens-P checks 1 and 2 unenforceable: `docs/review-lenses.md:67-68` requires exactly what no gate measures.

**(d) REMEDIATION:** Add a gate leg. Extend `pacemaker_problems` (or add a sibling predicate) so that an enabled row whose `deliver_to` begins `session:` and whose prompt is not the #177 bounded-job class must carry a non-empty `trigger_cmd`; and a row that declares a convergence duty must carry `set_goal=1` **with** a non-empty `goal_template` (`tools/registry_render.py:286-290` already documents that `set_goal=1` without a template auto-pauses after three NO_EVIDENCE runs — so the pair is the real condition). Feed it the same rows the runner already reads, widening the SQL at `tools/patrol_host_state.py:1189-1191` to also select `trigger_cmd, trigger_on, set_goal, goal_template`. If instead the two columns are *not* law, delete the claim at `:60-61` and reduce §1's table to the two columns the gate actually enforces — either way, stop asserting a property nothing tests.

---

## P-2 — HIGH — Live state violates the instrument's own concept and the factory's own patrol is green over it (the population the predicate cannot see)

**(a) LOCATOR:** `docs/instruments/pacemaker.md:80-81`; live ops DB `/root/.opencrabs/profiles/ops/opencrabs.db` `cron_jobs`; live runner verdict from `tools/patrol_host_state.py` `cron_thinness_leg`.

**(b) VERBATIM QUOTE:**

`docs/instruments/pacemaker.md:80-81`
> `session-wakes have no gate at all and burn a turn on every fire. This table is a snapshot of ONE`

Live DB, `SELECT name FROM cron_jobs WHERE enabled=1 AND deliver_to LIKE 'session:%' AND length(coalesce(trigger_cmd,''))=0` returns exactly four rows:

> `inferhub-daily-report | NO-MARKER(work order)`
> `inferhub-hq-pacemaker | NO-MARKER(work order)`
> `inferhub-self-audit-daily | NO-MARKER(work order)`
> `miidas-hq-daily-trigger | marker`

Live runner output (`cron_thinness_leg`, driven in-process against the real DBs):

> `"status": "ASSERTED", "problems": [], ... "rows_read": 42, ... "rows_attributed": 8, "rows_unattributed": 34`

The prompts of the three `NO-MARKER` rows, verbatim from the DB:

> `inferhub-hq-pacemaker` prompt: `Execute the 6-hourly HQ cycle per skills/inferhub/SKILL.md.`
> `inferhub-daily-report` prompt: `Daily inferhub report for Alexey. Execute exactly, in order: 1. `git -C /root/inferhub-watch pull --ff-only` …`
> `inferhub-self-audit-daily` prompt: `Daily self-audit pacemaker … Thin trigger — run the runner … 1. `git -C /root/inferhub-watch pull --ff-only` 2. `cd /root/inferhub-watch && python3 tools/audit.py --report` 3. Commit ONLY the artifacts …`

**(c) DEFECT ANALYSIS:** Three defects compound here.

1. **Ungated wakes burn tokens.** Four enabled rows wake a session on *every* fire with no `trigger_cmd`, so the pre-flight short-circuit (the instrument's "economy is the point", `:44`) never runs and a full agent turn is billed each time. `inferhub-hq-pacemaker` fires every 6 h (`10 */6 * * *`), `inferhub-daily-report` and `inferhub-self-audit-daily` daily, `miidas-hq-daily-trigger` daily.
2. **Three of them are also P7 violations — "two writers on one actor".** Their prompts are full work orders (`git pull`, run a script, commit, push) delivered into a session *and* waking that session, which is exactly the shape `docs/best-practices.md:118-121` forbids. `pacemaker_problems` would flag them as "work order on a waking row" — **but it never sees them.**
3. **The factory's own patrol is structurally blind to them.** `registry/fleet.json` declares the meta-factory's `job_prefixes` as `["factory-"]`, so `attribute_rows` hands the predicate only the 8 `factory-*` rows; the other 34 enabled rows (including all three violations above) are "counted and named, never judged" by design (`tools/patrol_host_state.py:1255-1264`). The leg therefore prints `problems: []` and exits green while the box carries live rows of the exact class the predicate was written to catch. The instrument itself predicts this at `:60-62`: "a member that ports the files without gating its own crons has adopted the checker and not the concept" — and its own §9 census, which measures only **file presence**, reads `inferhub-watch` as **ADOPTED** (`docs/instruments/pacemaker.md:439`). So the census certifies a member whose live crons violate the concept, and no artifact in the repo records it.

**(d) REMEDIATION:** Two concrete moves. (i) Make the census/patrol record concept-compliance as a second axis beside file presence: run the new quiescence predicate (P-1) over each member's *attributed* rows and stamp the result in the fragment's `instruments.pacemaker` entry (e.g. `gate_compliant: false`), so `ADOPTED` cannot mean "holds the files" alone. (ii) For the four ungated rows: give `inferhub-hq-pacemaker`, `inferhub-daily-report` and `inferhub-self-audit-daily` a `trigger_cmd` gate and either strip their work orders to the wake-only marker or move the work into the woken lane (they are currently both the worker and the waker); `miidas-hq-daily-trigger` needs only a gate. Absent an owner decision, the meta-factory should at minimum *red* on the meta-factory-owned rows and *name the offenders* in the report rather than reporting a bare `problems: []`.

---

## P-3 — MEDIUM — Dead Session Detection (lens-P check 3) has no mechanism anywhere in the repo

**(a) LOCATOR:** `docs/review-lenses.md:69`; absence confirmed across `tools/` and `tests/`.

**(b) VERBATIM QUOTE:**

`docs/review-lenses.md:69`
> `  3. **Dead Session Detection:** Verify crons target live session UUIDs and do not push into dead subagent queues or unbound topics.`

**(c) DEFECT ANALYSIS:** A repo-wide search for any code that validates a cron row's `deliver_to` session UUID against the live `sessions` table returns nothing — `grep -rni "dead session\|live session\|session uuid\|archived_at\|unbound" tools/ tests/ docs/` matches only `tools/registry.py` (lane resolution for the *registry*, not for crons) and unrelated "unbounded" hits. Neither `pacemaker_problems` nor the runner's `cron_thinness_leg` touches the `sessions` table; `docs/instruments/pacemaker.md` never mentions the check. The instrument declares a `deliver_to = session:<uuid>` wake column (`:41`) but ships no upholder that the UUID is *live*. Measured now, the check would pass (all 7 enabled session targets exist and are unarchived — `SELECT count(*) FROM sessions WHERE id='<uuid>'` returns 1 for each, `archived_at` NULL), so there is no live failure today; but the lens-P check is unimplemented, and a rebind/archive would push a wake into a dead queue with nothing to notice.

**(d) REMEDIATION:** Add a leg to `tools/patrol_host_state.py` that, for each attributed enabled row whose `deliver_to` begins `session:`, resolves the UUID against the profile's `sessions` table and reports a PROBLEM when the row is absent or `archived_at IS NOT NULL` — mirroring `tools/registry.py:2287` (`resolve` each declared lane to a live session), which already proves the read is feasible. Add the probe pair to `tests/test_patrol_host_state.py` (bites on a synthetic dead UUID; stays clean on a live one).

---

## P-4 — MEDIUM — The instrument's own code citations have drifted (`:91`→`:93`, `:1188`→`:1760`)

**(a) LOCATOR:** `docs/instruments/pacemaker.md:105` and `docs/instruments/pacemaker.md:547-548`.

**(b) VERBATIM QUOTE:**

`docs/instruments/pacemaker.md:105`
> `| 10 | `tests/ledger_boundary.py` ↔ `TEMPLATE/tests/ledger_boundary.py` | `closure` | the boundary reader the runner loads by path (`patrol_host_state.py:91`) |`

`docs/instruments/pacemaker.md:547-548`
> `   local note: `patrol_host_state.py:91` sets `LEDGER_BOUNDARY = REPO / "tests" / "ledger_boundary.py"``
> `   and loads it by path at `:1188`, and `ledger_boundary.py:69` does `from ledger_declaration import …`.`

**(c) DEFECT ANALYSIS:** The real file contradicts both citations. `awk 'NR>=90&&NR<=93' tools/patrol_host_state.py` yields `90: KIT_PIN = …`, `91: # The boundary reader (#175). Reached by PATH through `load_module`, never imported:`, `92: # this runner is copied into every member factory…`, `93: LEDGER_BOUNDARY = REPO / "tests" / "ledger_boundary.py"` — so the assignment the doc names at `:91` is at **`:93`**; `:91` is a comment. And the path-load the doc names at `:1188` is not there: `awk 'NR==1188'` prints `fetched = list(conn.execute(` (the cron SQL, see P-1); `grep -n "LEDGER_BOUNDARY" tools/patrol_host_state.py` shows the only load is `1760: _BOUNDARY_READER = load_module("ledger_boundary", LEDGER_BOUNDARY)`. Both cited line numbers are wrong. This matters because §10 (`:605-606`) makes the *point* that a pointer "must name **the enforcing line**, not a prose line that a later edit can move without any gate noticing" — and the instrument's own enforcing-line citations have already moved with nothing noticing. `ledger_boundary.py:69` is still correct.

**(d) REMEDIATION:** Update `:91`→`:93` and `:1188`→`:1760` (or, better, cite the symbol — `LEDGER_BOUNDARY` / the `load_module("ledger_boundary", …)` call — and drop the brittle line number, which is the remedy §10 itself prescribes). Add a cheap gate that re-resolves the doc's `path:line` citations against the tree, since this class has now recurred (§9.1 item 7 is the same failure on a member's citation).

---

## P-5 — MEDIUM — The harness-binding methodology contradicts the cron contract and the pacemaker doc on the trigger probe

**(a) LOCATOR:** `docs/methodology/04-harness-binding.md:65` and `:71`.

**(b) VERBATIM QUOTE:**

`docs/methodology/04-harness-binding.md:65`
> `To eliminate token waste on idle heartbeat turns, OpenCrabs crons support **headless 0-token trigger probes** where the `prompt` parameter is omitted:`

`docs/methodology/04-harness-binding.md:71`
> `git fetch origin main && [ $(git rev-parse HEAD) != $(git rev-parse origin/main) ]`

**(c) DEFECT ANALYSIS:** Two contradictions with the repo's own law. (i) The methodology says the 0-token probe **omits the `prompt` parameter**; the `cron_manage` contract states `prompt` is "required for create", and the pacemaker doc describes the opposite mechanism — the prompt is *present* and simply never executes on a non-fire (`docs/instruments/pacemaker.md:44-45`: "the prompt never executes and nothing is delivered"). A reader who follows `04-harness-binding.md:65` will try to create a trigger-only cron and be refused, or will believe the wake carries no prompt when the whole P7 thinness rule is *about* the prompt's content. (ii) The doc's own example `trigger_cmd` runs `git fetch origin main`, which **writes** to `.git` (updates remote-tracking refs) — directly contradicting the pacemaker doc's defining property of the column, `docs/instruments/pacemaker.md:39`: "It watches; it never acts." A trigger that mutates the tree on a schedule it then gates on is the leaky form the "watches, never acts" line exists to forbid.

**(d) REMEDIATION:** Reconcile the two docs: state in `04-harness-binding.md` that the prompt is present but short-circuited (matching `pacemaker.md:44` and the `cron_manage` contract), and replace the `git fetch … && [ … ]` example with a read-only probe (e.g. `git ls-remote` or a `git rev-parse` against a ref already fetched, or a plain file/state check) so the example honours "It watches; it never acts." If the harness truly did once accept an omitted prompt, mark the paragraph as historical rather than present-tense.

---

## P-6 — LOW/MEDIUM — The instrument's "live state" snapshot is stale in every cell, and one §6 census claim no longer reproduces

**(a) LOCATOR:** `docs/instruments/pacemaker.md:64-83` (the snapshot table) and `docs/instruments/pacemaker.md:238`.

**(b) VERBATIM QUOTE:**

`docs/instruments/pacemaker.md:71-76`
> `| enabled | 33 |`
> `| with a cheap gate | 10 |`
> `| waking a session | 8 |`
> `| gate **AND** session wake | 2 |`
> `| with `set_goal` | 2 |`
> `| gate **AND** session wake **AND** `set_goal` | **0** |`

`docs/instruments/pacemaker.md:238`
> `| `registry/fleet.json` → `job_prefixes` | `registry/fleet.example.json` | **the factory** | it IS the ownership declaration: the runner attributes each cron row to a factory by this field, never by the home a row sits in (measured: all twelve ai-antispam rows live in the ops home) |`

**(c) DEFECT ANALYSIS:** The doc labels the table "a snapshot of ONE home at ONE instant" (`:81-82`), so drift is expected in principle — but this is the instrument's *only* live-state figure, it is the number a reader will cite, and every cell has moved within seven days: enabled 33→**34**, gated 10→**11**, waking a session 8→**7**, gate AND session 2→**3**, `set_goal` 2→**1**. Worse, the prose at `:78-80` names `ai-antispam-43-close-gate` and `ai-antispam-52-close-gate` as "the two gated session-wakes" — measured now both have `deliver_to = NULL`, i.e. they are gated rows with **no session wake at all**, so the sentence that interprets the table is now wrong, not merely old. The §6 claim "all twelve ai-antispam rows live in the ops home" is likewise stale: `SELECT count(*) FROM cron_jobs WHERE name LIKE 'ai-antispam%'` returns **19** (16 enabled). The doc's own §5 lesson ("a count taken by a pattern is not a count of items", `:225-226`) argues for re-stamping rather than trusting a frozen figure.

**(d) REMEDIATION:** Replace the hand-typed table with a derived one: the repo already renders the live rows (`tools/registry_render.py:561-562`, `_pacemaker_table`), so cite that artifact's stamp and let it move, or mark the §1 table explicitly "historical — measured 2026-09-27, superseded; see the rendered pacemaker table" and drop the interpretation sentence at `:78-80`. Update `:238`'s "twelve" to the live count or remove the number.

---

## P-7 — LOW — The only prior lens-P report is an unverifiable false positive, and no gate can catch it (a consequence of P-1)

**(a) LOCATOR:** `reviews/20260917-c1/reports/lens-P.md:1`.

**(b) VERBATIM QUOTE:**

> `Audited live cron pacemakers in /root/.opencrabs/profiles/ops/opencrabs.db. Confirmed 0-token trigger_cmd short-circuits (exit_zero / non_empty) and set_goal: 1 autonomous convergence on factory-triage-hourly, factory-insights-weekly, factory-template-weekly, oc-roster-detached-sweep, and infra-triage-hourly.`

**(c) DEFECT ANALYSIS:** The report asserts `set_goal: 1` convergence on five named jobs. Measured against the live DB: `factory-triage-hourly` and `infra-triage-hourly` **do not exist** (`SELECT … WHERE name='…'` returns nothing; the live names are `factory-triage-patrol` and `infra-triage-patrol`), and the three that do exist — `factory-insights-weekly`, `factory-template-weekly`, `oc-roster-detached-sweep` — all carry `set_goal = 0`. So on the names that resolve, the report's central claim is false; on two names it cannot resolve. The report carries no locator, no verbatim quote and no exit-code receipt, so it cannot be re-verified at all — and because the lens-P checks have no mechanical backing (P-1), nothing in the pipeline can contradict it. It is a praise-shaped artifact of exactly the kind the adversarial brief exists to catch. (Cron rows are mutable, so I cannot prove the claim was false *on 2026-09-17*; I can prove it is unverifiable and that it does not reproduce today.)

**(d) REMEDIATION:** Re-run lens P with the receipt discipline the corpus demands (locator + verbatim quote + a command that reproduces each figure), and record it. The durable fix is P-1: once the quiescence/convergence predicate exists, a lens-P verdict becomes a tool output rather than prose, and a report like this one fails to reproduce automatically.

---

## Coverage note — brief premise vs the repo

The brief and the corpus map lens P onto "the cron/pacemaker sections of `skills/meta-factory/SKILL.md`". **No such section exists.** `grep -n "cron\|pacemaker\|P7\|P28" skills/meta-factory/SKILL.md` returns only scattered mentions (lines 46, 280, 285, 481) inside other sections; there is no dedicated cron or pacemaker section in `SKILL.md`. The operative law for this lens lives in `docs/instruments/pacemaker.md`, `docs/best-practices.md` P7/P28 (`:111-140`, `:505-527`), `docs/methodology/04-harness-binding.md` §3 (`:63-81`), and `skills/meta-factory/state.md:18-52` (the duty-receipt / redirect-log clauses). I audited those instead. This is a scope/coverage finding, not a defect in the repo.

---

## Summary

**Findings: 7** (2 HIGH, 3 MEDIUM, 2 LOW/MEDIUM-LOW), plus one coverage note.

**Single most severe: P-1** — `docs/instruments/pacemaker.md` declares a four-column pacemaker concept (`trigger_cmd`, `trigger_on`, `deliver_to`, `set_goal`) and states at `:60-61` that "the property it upholds is the four columns above", but the only shipped gate (`tests/test_cron_thinness.py:277-293`) and the live runner (`tools/patrol_host_state.py:1188-1191`) read just `deliver_to` and `prompt`; `trigger_cmd`/`trigger_on` and `set_goal` are read by no pacemaker gate, so lens-P checks 1 (0-token quiescence) and 2 (goal convergence) have no mechanical upholder — a P29 "law without gate" violation inside the factory's own instrument, and the root cause that lets P-2 and P-7 exist.

**Measurements behind the summary:** `git rev-parse HEAD` = `6bd9690d578c5bbc911537b95abe0ab0bc884c8c`; ops-home `cron_jobs` counts (enabled 34 / gated 11 / session-wake 7 / gate+session 3 / `set_goal` 1 / full 0) via `sqlite3 "file:…/ops/opencrabs.db?immutable=1"`; the live `cron_thinness_leg` verdict (rows_read 42, attributed 8, unattributed 34, `problems: []`) via an in-process `importlib` drive of `tools/patrol_host_state.py` with the board/publish/worktree legs not invoked; the four ungated session-wakes and their prompts via the same DB; the dead-session check via `grep -rni` across `tools/ tests/ docs/` plus a `sessions`-table existence check for each of the 7 enabled targets (all present, `archived_at` NULL); the citation drift via `awk 'NR>=90&&NR<=93'` and `grep -n "LEDGER_BOUNDARY"`; and template parity via `cmp -s` (all six audited paths SAME).
