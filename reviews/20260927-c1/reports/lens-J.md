# LENS J — Law-to-Tool Migration (The Pure Function Test)

**Repo under review:** `/root/agent-factories` @ HEAD `ee518861e1f20d4b2ebed42313a7508c237072ad` (2026-10-04 20:42:54 +0000)
**Lens letter:** J · **Cycle:** `20260927-c1` · **Mode:** isolated adversarial, read-only
**Scope (mapped by `CORPUS.md`):** every written-law surface — `skills/meta-factory/SKILL.md`,
`state.md`, `verdicts-and-claims.md`; `docs/*.md`; `docs/methodology/*`; `docs/instruments/*.md`;
`ONTOLOGY.md`; `README.md`; `TEMPLATE/*.md` — measured **against `tools/*.py`**, asking which
rules tell an agent to derive, remember or manually check state that a script could compute.

**The Three-Part Test (from `briefs/lens-J.md`).** A rule is an *unwritten tool specification* when
all three hold: **T1** the decision depends purely on git-tree / filesystem / environment / ledger
state (no human judgment); **T2** a CLI script or mechanical test already exists or is the natural
host; **T3** the rule currently instructs an agent to remember, derive, or manually check that state.
Excluded by the brief: irreversible human gates (P14), approval checkpoints, client-subjective calls.

**Method (what I read and ran — all read-only; nothing under the repo was modified).**
- Read in full: `skills/meta-factory/SKILL.md` (496 lines), `state.md` (188), `verdicts-and-claims.md`
  (246), `docs/review-lenses.md` (181), `docs/processes.md` (213), `docs/quality-criteria.md` (410),
  `docs/best-practices.md` (851), `docs/measurement-procedure.md` (661), `ONTOLOGY.md` (539),
  `TEMPLATE/BOOTSTRAP.md`, `tests/test_law_coverage.py`, `tests/gate_registry.py`,
  `tests/test_commit_pair_hook.py`, `tools/audit.py`, `tools/gate_budget_rederive.py`,
  `tools/patrol_host_state.py`, `tools/instrument_census.py`, `tools/kit_census.py`,
  `evidence/rework.md` (line 338), `evidence/scores/2026-10-04.md`.
- Counted with `grep -c`, `grep -rn`, `wc -l`, `ls`, `git`, and an `ast.literal_eval` parse of
  `PRACTICE_GATES` — never estimated.
- Law corpus measured at **10,899 lines** across 21 law files.

**Findings: 7** (1 CRITICAL, 3 HIGH, 2 MEDIUM, 1 INFO). Ordered most severe first. A "checked and
found clean" section follows the findings, per the brief's rule that a praise-free pass is a failed audit.

---

## F1 — CRITICAL — The gate that upholds P29 ("every law needs a mechanical gate") is satisfied by a `.md` file. Nine of 37 practices map only to prose.

**File Locator:** `tests/test_law_coverage.py:146` (the assert), with the map at `:40` and the
self-indicting comment at `:57`.

**Verbatim Quote:**
```
tests/test_law_coverage.py:40
PRACTICE_GATES: dict[str, list[str]] = {

tests/test_law_coverage.py:57
    # EXISTS. A file that exists and implements nothing satisfied it completely (#69, #54).

tests/test_law_coverage.py:143-148
        for target in gates:
            target_path = REPO_ROOT / target
            if not target_path.exists():
                unverified_targets.append(f"{p_id} -> {target} does not exist on disk")

    assert not missing_gates, f"Best practices missing mechanical gate mapping: {missing_gates}"
    assert not unverified_targets, f"Mapped gate targets do not exist on disk: {unverified_targets}"
```

**Defect Analysis.**
P29 (`docs/best-practices.md:531`) states: *"Every law needs an active process or mechanical gate
upholding it. A rule without an upholding mechanism is dead text."* The gate that is supposed to
uphold P29 is `tests/test_law_coverage.py`. Its entire verification of a mapped target is
`target_path.exists()`. A markdown file — a docstring-like prose surface, exactly the class P29 calls
"dead text" — satisfies it completely. The file's own comment at `:57` names this defect verbatim
(*"A file that exists and implements nothing satisfied it completely (#69, #54)"*) and then reproduces
it one level up: the check that *a practice is mechanically upheld* is itself upheld only by existence.

Measured with an `ast.literal_eval` parse of `PRACTICE_GATES`:
- **37** practice entries, **70** mapped targets, **25** targets end in `.md` (prose), **45** are non-`.md`.
- **9 practices map ONLY to `.md` files** — the practice has no mechanical target at all:

```
P2  ['TEMPLATE/roles/hq.md', 'TEMPLATE/roles/triage.md', 'TEMPLATE/roles/worker.md']
P14 ['TEMPLATE/roles/hq.md']
P16 ['skills/meta-factory/SKILL.md']
P18 ['skills/meta-factory/SKILL.md']
P19 ['skills/meta-factory/SKILL.md']
P21 ['TEMPLATE/README.md']
P24 ['skills/meta-factory/SKILL.md']
P25 ['skills/meta-factory/SKILL.md']
P31 ['docs/processes.md', 'TEMPLATE/roles/hq.md']
```

(Of these, P14 is the brief's own excluded class — an irreversible human gate — so 8 are genuine
migration candidates.) This is T1 (pure disk state), T2 (the natural host is the very gate file that
already exists), T3 (the mapping is a hand-maintained dict an author edits by hand). The map is an
**unwritten tool specification**: the rule "this practice is mechanically upheld" is asserted, never
computed.

**Actionable Remediation.**
1. Strengthen the predicate in `tests/test_law_coverage.py`: for each practice, assert **≥1 mapped
   target is a non-`.md` file that is itself registered** in `tests/gate_registry.py` /
   `tools/audit.py`. A mapping whose only targets are prose REDs naming the practice.
2. Migrate the 8 live prose-only practices to real gates: **P2/P14/P31** → a role-card schema /
   register-owner uniqueness gate over `TEMPLATE/roles/*`; **P16/P18/P24/P25** → a dispatch/boundary
   predicate over the skill's §11 surface table; **P21** → an add-on leak test.
3. Keep the prose target in the list only as a *citation*, never as the upholding mechanism.

---

## F2 — HIGH — P26's operator-act count is law with no tool, and the gate it maps to does not implement it.

**File Locator:** `docs/best-practices.md:416` (heading) and `:453` (Practice clause); mapping at
`tests/test_law_coverage.py:112`.

**Verbatim Quote:**
```
docs/best-practices.md:416
## P26 — A factory counts the acts that still need its operator

docs/best-practices.md:453-454
- *Practice:* at bootstrap, enumerate the acts only the operator can perform. Re-run the
  count on the measurement cadence. An act that gets mechanized leaves the list, and the
  count is the trend.

tests/test_law_coverage.py:112
    "P26": ["tools/audit.py"],  # Count acts that still need operator
```

**Defect Analysis.**
The law tells an **agent** to "enumerate the acts only the operator can perform" and "re-run the
count on the measurement cadence." That is T3: a rule instructing a lane to derive a count by hand.
The count is a pure function of disk/ledger state — the set of acts declared as operator-only (T1) —
and the map itself claims the host is `tools/audit.py` (T2). But the mapped tool does not count
operator acts:

```
$ grep -c -i "operator" tools/audit.py
1
```

That single hit is a comment at `tools/audit.py:2725`, not a count — no code in `audit.py` enumerates
or counts operator-required acts. The map asserts an upholding mechanism that does not exist, and
F1's `exists()`-only predicate lets it pass because the *file* exists.

Note the asymmetry the corpus already half-solved: the companion **rate** has a SQL predicate
recorded in `evidence/p26-rate-derivation-2026-09-29.md` (numerator = operator-prefix-anchored
`messages` rows; denominator = ledger `close` rows; value 2,849/207 = 13.76). The **count** — P26's
*primary* measure ("A factory answers it with an enumeration, not a yes") — has neither tool nor query.

**Actionable Remediation.**
Add `tools/p26_acts.py` (or an `audit.py` leg) that reads a declared act list, prints the population
and the read instant, and exits 0/non-zero; register it in `tools/audit.py`. Make P26's rate SQL the
tool's second leg. Re-point `PRACTICE_GATES["P26"]` at the new tool (non-`.md`), satisfying F1's
strengthened predicate.

---

## F3 — HIGH — §5.2's gate-budget re-derivation names no tool, though the tool exists and the cron already calls it.

**File Locator:** `docs/measurement-procedure.md:186-188` (§5.2 standing duty) and `:545` (the writer rule).

**Verbatim Quote:**
```
docs/measurement-procedure.md:186-188
   - **The gate-budget re-derivation leg (§5.2) — a standing duty of THIS round.** When the
     audit reports a gate whose declared basis no longer describes it (leg A bytes / leg B
     runner), or one that exhausted its budget, the run re-derives that basis from its own
     fresh measurement and writes `registry/gates.json`.

docs/measurement-procedure.md:545-546
duty (`Surveys`)** — §11 of the skill names it. The derivation RULE is not the lane's: the budget
values are the process owner's, never the implementing lane's (n=574 PART 5), so a re-derivation
APPLIES the manifest's stated law to a fresh measurement
```

**Defect Analysis.**
The law says "**the run re-derives** that basis from its own fresh measurement" — an agent act (T3).
The mechanism is disk state (a gate's declared basis vs. its measured bytes/runner — T1) and a tool
already exists (T2): `tools/gate_budget_rederive.py`, whose own docstring reads
`gate_budget.budget_staleness()`, three triggers, `EXIT_VACUOUS=2`, `EXIT_REFUSED=3`. Yet no law
surface names it:

```
$ grep -rln "gate_budget_rederive" docs/ skills/ TEMPLATE/ ONTOLOGY.md README.md
TEMPLATE/tests/test_gate_registration.py
```

The only naming surface is a *test*, not the law. Meanwhile the factory's own cron prompt **already
names the tool** — `registry/state.json:3455` (`factory-measurement-daily`) invokes
`python3 tools/gate_budget_rederive.py`. So the operational path names the tool and the written law
does not: the law is a hand-derivation instruction that the runtime has already outgrown. §5.2's
own first live application is recorded in `evidence/scores/2026-10-04.md:263-265` ("**7 of 54 declared
bases** no longer described what runs"), confirming the leg runs — the law just never says how.

**Actionable Remediation.**
State the exact invocation in §5.2, e.g. `python3 tools/gate_budget_rederive.py --audit-report
<payload> --apply`. The law keeps the trigger, the writer (`Surveys`) and the rule (the values are
the process owner's); the tool keeps the act. This is the same migration F2 and F4 propose, applied to
a leg whose tool is already shipped.

---

## F4 — HIGH — §4.1's "own-elapsed-slot" cadence predicate is a pure function of cron state, stated as a surveyor computation with no host.

**File Locator:** `docs/measurement-procedure.md:99` (§4.1 heading) and `:91` (the Tier-1 procedure).

**Verbatim Quote:**
```
docs/measurement-procedure.md:99
### 4.1 Cadence freshness: the own-elapsed-slot predicate

docs/measurement-procedure.md:91-92
1. **Verify live execution against declared cadence:** Inspect the factory's scheduler,
   run logs, and ledger timestamps.

docs/measurement-procedure.md:103-106
> *"Cadence freshness is judged against each job's OWN last elapsed slot, read WITH its
> timezone — never against wall-clock "today" in UTC across a mixed-timezone cron table.
> A slot that has not yet arrived cannot have been missed."*
```

**Defect Analysis.**
"Has this job missed its own last elapsed slot?" is a pure function of `cron_jobs.last_run_at`, the
job's timezone and its declared cadence — disk/DB state (T1) with a mechanical host already present
(T2). Yet the law instructs the surveyor to "inspect the scheduler, run logs, and ledger timestamps"
and apply the predicate by hand (T3). The predicate is precise enough to be a function — the law even
pins the exact instant and the future-slot arithmetic (`06:20:59Z` vs Miidas's `09:00Z` slot "2h39m01s
in the FUTURE") — which is the signature of a computation waiting for a script.

Measured: no tool computes this predicate. `tools/audit.py` carries a cadence leg, but it is a
different quantity — `check_cadence_integrity` (`tools/audit.py:2527`) measures the **ledger's own**
run cadence (`hours_diff <= 30.0` against the last audit row), not per-job own-slot freshness.
`tools/patrol_host_state.py`'s "freshness" legs are the **publish**-freshness surface
(`publish_freshness_leg`, issue #146) — a receipt comparison, not the cron cadence predicate. Greps
for an elapsed-slot host return nothing:

```
$ grep -rln "cadence_freshness\|own_elapsed\|elapsed_slot" tests/ tools/
(no matches)

$ grep -rn -i "freshness\|own.*slot\|missed.*slot" tools/*.py
tools/patrol_host_state.py:95  # ---- the publish-freshness leg (issue #146, ruled at ledger n=1168)
...   (all hits are the PUBLISH leg, not the cadence predicate)
```

The law itself names the failure mode ("the surveyor's predicate being wrong — measuring generation
and calling it execution") and fixes it in *prose*; the fixed predicate is never mechanized.

**Actionable Remediation.**
Add a pure predicate — `tests/test_cron_cadence.py`, or a cadence leg in
`tools/patrol_host_state.py` that already reads `cron_jobs.last_run_at` — that, per job, prints the
declared cadence, the job's timezone, the last elapsed slot, and MISSED/NOT-MISSED. The law then
points at the tool instead of instructing the surveyor to recompute it. (Verify the absence at HEAD
with the greps above before landing; if a host appears, this finding is discharged.)

---

## F5 — MEDIUM — `ONTOLOGY.md` claims its own gate "is run by hand" while `tools/audit.py` registers it in the daily suite.

**File Locator:** `ONTOLOGY.md:504-505`.

**Verbatim Quote:**
```
ONTOLOGY.md:504-505
**Status:** enforced by `tests/test_ontology.py`; no CI runner is configured
yet, so the gate is run by hand and its result is a receipt. Wiring it to CI is
what would make it a build failure in the strict sense.
```

**Defect Analysis.**
The claim "the gate is run by hand" is stale against the code. `tools/audit.py` registers
`tests/test_ontology.py` in the mechanical sweep:

```
$ grep -n "test_ontology.py" tools/audit.py
1242:    if (repo_root / "tests/test_ontology.py").is_file():
1243:        gates_to_run.append([sys.executable, "tests/test_ontology.py"])
```

So the gate is *not* run by hand — it runs on every `audit.py` sweep (which the cron drives:
`registry/state.json` `factory-measurement-daily`). Only the second half of the sentence ("no CI
runner is configured") is true. This is the flattering-reverse defect: a gate that **is** mechanized
is documented as ungated, so a reader resolving the enforcement table sees a gap where none exists
and the *status* is un-migrated from prose to the tool's own registration (T1 + T2 + T3). It is
medium, not high, because the direction is safe (it under-claims coverage rather than over-claims it).

**Actionable Remediation.**
Correct the status to: "enforced by `tests/test_ontology.py`, registered in the `tools/audit.py`
sweep (line 1242-1243); no CI runner is configured yet, so the result is a receipt, not a build
failure." Keep only the CI caveat.

---

## F6 — MEDIUM — The rubric and register admit measures are "applied by hand / nothing produces them mechanically," though `tools/audit.py` computes them.

**File Locators:** `docs/quality-criteria.md:313`, `docs/quality-criteria.md:328`,
`docs/process-audit.md:207`, `ONTOLOGY.md:441`.

**Verbatim Quote:**
```
docs/quality-criteria.md:313
| Verification depth + record | 2 | Strong inherited law (receipts, read-back-immune proofs) applied by hand; no mechanical gate in this repo |

docs/quality-criteria.md:328
| Machine | 6 / 16 (38%) | The strongest family — inherited rules, applied by hand |

docs/process-audit.md:207
reading live state by hand; nothing produces them mechanically.

ONTOLOGY.md:441
from rather than something Surveys has to read by hand.
```

**Defect Analysis.**
`tools/audit.py` computes the machine-family measures the rubric calls "applied by hand" /
"nothing produces them mechanically":

```
$ grep -n "first_pass_yield\|rework_share\|avg_lead_time_sec" tools/audit.py
283:        f"yield={format_yield_percent(stats.get('first_pass_yield'))}"
404:            "first_pass_yield": 1.0,
408:            "avg_lead_time_sec": 0.0,
637:        "first_pass_yield": yield_val,
```

i.e. yield, rework share and lead time are printed by the tool and written into a run row. The
"nothing produces them mechanically" clause is therefore stale for those measures. This is a
weaker instance of F5's class — the law's own account of its mechanism lags the tool — and it is
medium because it is a documentation drift, not a missing gate. (Two readings are possible and the
report does not hide it: either the law is outdated, or the tool is unnamed *by the law* — the T3
residue of an already-shipped mechanism. Either way the sentence as written is false.)

**Actionable Remediation.**
Point these clauses at `tools/audit.py`'s printed measures and its run row; delete the "nothing
produces them mechanically" sentence or narrow it to the measures still genuinely manual. Where a
measure truly is manual, name the surveyor's read and its instant (the corpus's own "population and
instant" rule).

---

## F7 — INFO (resolved) — §5.2 declared a third trigger that was unreachable until `007d959`; a law stating a mechanism that could not fire.

**File Locator:** `docs/measurement-procedure.md` §5.2 (the exhausted-budget trigger, heading at
`:506`) vs `tools/gate_budget_rederive.py`.

**Verbatim Quote (the law's third trigger, per the audit's own account of it):**
```
evidence/scores/2026-10-04.md:264
`_audit_samples()` skips every gate whose `unknown` flag is set, then
`containment_population()` computes `exhausted` **only over those same samples**
(`samples.get(key) >= budget`). A budget-exhausted gate is *always* `unknown`, so it can
**never** enter `exhausted`.
```

**Defect Analysis.**
For Lens J this is a textbook instance of the class the lens hunts: a written law declared a
mechanism ("a measured sample EXHAUSTED the declared budget" fires a re-derivation) whose
implementation **could not fire** — the trigger's population was computed from a set that structurally
excluded its own members ("the population was empty for every input, forever"). The measured case:
`tests/test_hygiene_placement.py` ran 18.50 s against a declared `budget_sec 18.43` (`rc=124`) and the
leg printed `exhausted: []`. A law that names a trigger with no reachable mechanism is exactly the
"law rot" P29 forbids — and here the *mechanism existed* but its predicate was inverted.

**Status, resolved — verified against git.** The ambiguity in the corpus (score artifact says
"reported and NOT fixed, filed as #307"; `evidence/rework.md:338` says fixed at `007d959`) resolves
to **fixed**:

```
$ git log --oneline -1 007d959
007d959 fix(#307): the exhausted-budget trigger reads the audit's UNKNOWN population

$ grep -n "unknown\|_audit_samples" tools/gate_budget_rederive.py
100:def _audit_samples(report_path: Path) -> tuple[dict, tuple, str]:
129:        if gate.get("unknown"):
191:        # budget -- the `unknown` flag -- never a comparison against the cap. It is read from
192:        # the UNKNOWN population, not from the completed samples
```

The tool now returns the two populations separately and reads the trigger from the `unknown` set, so
the trigger is reachable. **This finding is therefore INFO, not a live defect** — recorded because the
score artifact of 2026-10-04 still reads "NOT fixed" and a later reader would otherwise treat the
law's third trigger as dead.

**Actionable Remediation.**
None outstanding in code. The law (`docs/measurement-procedure.md` §5.2) should still **name the
tool** (see F3) so the trigger's reachability is anchored to a named mechanism rather than to prose.

---

## Checked and found CLEAN (named so this is not a praise-free pass)

- **`docs/processes.md:189`** — Process 3 subprocess 1 is a *mechanical* invocation
  (`python3 tools/audit.py --report`), already migrated; not a hand-derivation.
- **The commit-pair hooks are real and reachable.** `git config --get core.hooksPath` → `tools/hooks`;
  `git ls-files tools/hooks/` → `tools/hooks/commit-msg`, `tools/hooks/pre-commit` (tracked);
  `tests/test_commit_pair_hook.py` asserts installation and states the anti-vacuity reason ("an
  uninstalled hook is SILENT — the vacuous-pass shape this repo forbids"). No pre-push hook exists,
  consistent with the #286 ruling that none is owed for the forward-reference class.
- **`tests/test_law_coverage.py`'s reverse direction** (every `PRACTICE_GATES` key must be a declared
  practice, `:125-127`) is a genuine anti-vacuity guard — the forward mapping's `exists()` weakness
  (F1) is the *only* defect in this file, and it is real; the reverse check is not similarly weak.
- **`tests/gate_registry.py`** runs five directions (declared→registered, registered→declared,
  required→present, law→registered, registered→CAN RUN) — a bidirectional anti-vacuity design, not a
  single-sided existence check.
- **`tools/instrument_census.py`** and **`tools/kit_census.py`** state their own boundaries and
  refuse over empty populations (a zero over a failed parse is a REFUSAL, not a clean census) — the
  opposite of the `exists()` fail-open shape. No Lens-J defect found in either.

---

## Appendix — exact commands/reads that produced the measurements

```
# F1 — the P29 upholding map
python3 -c "import ast; ...ast.literal_eval(PRACTICE_GATES)..."
  -> entries: 37  total targets: 70  md targets: 25  non-md: 45
  -> prose-only practices: 9  ['P2','P14','P16','P18','P19','P21','P24','P25','P31']
grep -n "target_path.exists\|PRACTICE_GATES\|implements nothing satisfied" tests/test_law_coverage.py
  -> :40 map, :57 self-indicting comment, :146 the assert
grep -n "^## P29" docs/best-practices.md            -> :531

# F2 — P26
grep -c -i "operator" tools/audit.py                 -> 1  (a comment at :2725)
grep -n "P26" tests/test_law_coverage.py             -> :112  ["P26": ["tools/audit.py"]]
sed -n '412,456p' docs/best-practices.md             -> P26 heading :416, Practice :453

# F3 — §5.2 names no tool
grep -rln "gate_budget_rederive" docs/ skills/ TEMPLATE/ ONTOLOGY.md README.md
  -> TEMPLATE/tests/test_gate_registration.py  (ONLY; no law doc names it)
sed -n '186,188p;543,547p' docs/measurement-procedure.md

# F4 — §4.1 predicate has no host
grep -rln "cadence_freshness\|own_elapsed\|elapsed_slot" tests/ tools/   -> (none)
grep -n "check_cadence_integrity" tools/audit.py     -> :2527 (ledger cadence, not own-slot)
grep -rn -i "freshness\|own.*slot" tools/patrol_host_state.py -> publish-freshness leg only

# F5 — ONTOLOGY status vs audit registration
sed -n '504,505p' ONTOLOGY.md
grep -n "test_ontology.py" tools/audit.py            -> :1242-1243 (registered)

# F6 — rubric claims "by hand" vs audit.py computes
sed -n '313p;328p' docs/quality-criteria.md ; sed -n '207p' docs/process-audit.md ; sed -n '441p' ONTOLOGY.md
grep -n "first_pass_yield\|rework_share\|avg_lead_time_sec" tools/audit.py  -> :283,:404,:408,:637

# F7 — dead-trigger, resolved
sed -n '338p' evidence/rework.md ; sed -n '263,265p;436,442p' evidence/scores/2026-10-04.md
git log --oneline -1 007d959   -> fix(#307): the exhausted-budget trigger reads the audit's UNKNOWN population
grep -n "unknown\|_audit_samples" tools/gate_budget_rederive.py  -> :100,:129,:191

# clean checks
git config --get core.hooksPath                      -> tools/hooks
git ls-files tools/hooks/                            -> commit-msg, pre-commit
sed -n '189p' docs/processes.md
```

**Isolation note.** No file under `/root/agent-factories` was modified, created or deleted. The only
write performed was this report file. No `review.py record` call was made, because that tool writes
under `reviews/<cycle_id>/` inside the factory, which the read-only constraint forbids.
