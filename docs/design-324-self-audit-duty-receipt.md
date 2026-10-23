# Design — #324: the self-audit run row, dated, carrying `duty=`

**Status:** DESIGN, awaiting owner approval. No implementation has been made.
**Lane:** HQ (analysis, rulings, design). Implementation is the Worker lane's, after approval.
**Issued against:** #324 `kit(owner gate): stamp the internal self-audit run row dated + duty=`.
**Measured at:** `origin/main` = `87ff9a38`, `2026-10-23T06:32:13Z`, from committed blobs only.

---

## 1. What the ruling asks for

The issue asks for four changes to the kit, adopted from the meta-factory under infra's register
answer q21 (Option B, 2026-10-04T20:42:58Z):

1. Stamp the run subject **dated**: `internal-self-audit-<YYYY-MM-DD>` (UTC), not the bare stem.
2. Add `duty=completed|failed|skipped` to the detail, derived from the existing `outcome`.
3. Move `check_cadence_integrity`'s subject filter from exact equality to the boundary-checked
   prefix match (`receipt_subject_matches` shape) — "otherwise dating the subject SILENTLY
   DISABLES the cadence metric that caught the 2026-10-03 miss".
4. Update `TEMPLATE/tests/test_audit_cadence.py`, whose leg5 "pins `SELF_AUDIT_SUBJECT =
   "internal-self-audit"` and asserts the string appears EXACTLY ONCE".

Directive 3 is the load-bearing one: it is the only one that protects a measurement. It is also
the one that does not describe this tree.

---

## 2. Measured facts

Every figure below is a read of a committed blob at `origin/main`, not a recollection.

### 2.1 The kit's two halves are the same bytes

```
TEMPLATE/tools/audit.py  md5 a29667f3ad5eb0475a6c953cb6db06cc
tools/audit.py           md5 a29667f3ad5eb0475a6c953cb6db06cc
```

So a change made in one half and not the other is a template-sync failure, and
`tests/test_template_sync.py` is the gate that says so.

### 2.2 `check_cadence_integrity` has NO subject filter — directive 3's premise is false

`tools/audit.py:3216`:

```python
def check_cadence_integrity(ledger_path: Path) -> dict[str, Any]:
    """Check whether recurring processes ran according to declared schedule."""
    ...
            if data.get("event") in ("run", "score"):
                last_ts = data.get("ts")
```

It takes **the ledger path and nothing else**. There is no `subject` parameter, no equality
comparison, and no stem. It scans every row in file order, keeps the `ts` of the last row whose
event is `run` or `score` **of any subject**, and returns `cadence_held = hours_diff <= 30.0`.
Its only call site, `tools/audit.py:3443`, passes `ledger_file` alone.

Two consequences, and they point opposite ways:

- **Dating the subject cannot disable this metric**, because the metric never reads the subject.
  Directive 3's stated hazard does not exist.
- **The metric therefore does not measure the self-audit at all.** It measures *ledger activity*.
  Any lane stamping any `run` row resets it. A missed self-audit is invisible to it by
  construction, and `cadence_held: True` beside a self-audit that has not run in weeks is a
  **zero from a non-working instrument** — exactly the class this factory's own law forbids
  quoting as health.

The self-audit's own history makes that concrete. `internal-self-audit` rows in the whole ledger:

| row | instant | detail |
|---|---|---|
| `n=29` | `2026-09-13T22:34:27Z` | `outcome=accepted gate=all-pass yield=100%` |
| `n=1980` | `2026-10-02T20:02:18Z` | `outcome=failed gate=gate-failure yield=100.0%` |
| `n=2027` | `2026-10-03T02:59:00Z` | `outcome=failed gate=gate-failure yield=96.2%` |

Three rows. The last is **20.15 days / 483.6 hours** old at the measurement instant. The cadence
check reads `cadence_held: True` today anyway, because the patrol and the cycle lanes stamp `run`
rows continuously. The 30-hour window is satisfied by work that has nothing to do with the audit.

### 2.3 The row renderer already carries `outcome`, and `duty` is a different field

`tools/audit.py:293` `format_run_row_detail(stats, outcome, gate_summary, elapsed_secs)`:

```python
f"duration={format_elapsed_seconds(elapsed_secs)} turns=0 outcome={outcome} "
f"gate={gate_summary} "
f"yield={format_yield_percent(stats.get('first_pass_yield'))}"
```

`outcome` at `:3622` is `"accepted" if (healthy is None or healthy) else "failed"`. `gate_summary`
is one of `skipped` / `all-pass` / `gate-unknown` / `gate-failure`.

`tools/field_predicate.py:813-819`:

```python
DUTY_KEY = "duty"
DUTY_DOMAIN: tuple[str, ...] = ("completed", "failed", "skipped")

def declared_duty(detail: str) -> list[str]:
    return _declared_values(detail, DUTY_KEY)
```

`declared_duty` reads the **canonical trailer**, positionally. Its docstring states the constraint
that decides this design:

> `duty` IS NOT `outcome`, and the two are not interchangeable. `outcome` is a WORK run's field: a
> run row declaring one ENTERS `first_pass_yield_population`, and a duty receipt is
> SELECTION-BIASED ... putting receipts under `outcome` would add near-certain successes to the
> yield's denominator and make the ratio structurally optimistic.

So directive 2's "derived from the existing `outcome` field" is correct **only** as a derivation of
the *value*, never as a reuse of the *field*. `outcome` stays exactly where it is, for the yield;
`duty` is a second, separate token whose position is the trailer.

### 2.4 The prefix matcher requires the date — which is what makes dating a fix

`tools/patrol_host_state.py:3488`:

```python
def receipt_subject_matches(subject: str, stem: str, round_date: str) -> bool:
    prefix = f"{stem}-{round_date}"
    if not str(subject).startswith(prefix):
        return False
    rest = str(subject)[len(prefix):]
    return not rest[:1].isdigit()
```

Feed it today's subject: `receipt_subject_matches("internal-self-audit", "internal-self-audit",
"2026-10-23")` → prefix is `internal-self-audit-2026-10-23`, the subject does not start with it →
**False**. An undated subject can never name a round.

Feed it the dated subject: `("internal-self-audit-2026-10-23", "internal-self-audit",
"2026-10-23")` → prefix matches exactly, `rest == ""` → **True**.

This inverts directive 1's risk. Dating the subject is not a formatting preference that endangers a
metric; it is **the change that makes the row a receipt at all**. Until it lands, any factory whose
duty declares `receipt_subject: internal-self-audit` reads MISSING on every round — and the duty
contract in the cron envelope states the required shape in terms: *"the woken lane writes a ledger
run row whose subject carries this stem **and the round date**"*.

### 2.5 The file directive 4 names does not exist, and neither does its constant

```
TEMPLATE/tests/test_audit_cadence.py   ABSENT
tests/test_audit_cadence.py            ABSENT
git log --all --oneline -- TEMPLATE/tests/test_audit_cadence.py   (no commits)
git grep SELF_AUDIT_SUBJECT origin/main -- tests TEMPLATE/tests tools TEMPLATE/tools   (no hits)
```

It has never existed in any commit on any branch, and the constant it is said to pin appears
nowhere in the tree. Directive 4 therefore has no subject to update: the gate must be **created**,
and the file the issue names is the right name for it.

### 2.6 Who actually owes this receipt

- **This factory** declares 9 `receipt_subject` values in `registry/state.json` — `growth-map`,
  `hq-cycle`, `insights`, `none` ×2, `patrol-verify`, `questions-redeliver`, `registry-attest`,
  `survey`, `template-weekly`. **None is `internal-self-audit`.** So this factory's own audit
  verdict is not currently gated on the self-audit being a receipt.
- **Infra** declares it, and drives the audit from a host crontab rather than an OpenCrabs cron
  job: `registry/factories/infra-factory.json:86` — *"root crontab on agents:
  `/usr/local/bin/infra-audit-stamp.sh` ... runs `tools/audit.py --report --stamp --actor
  surveys`"*. Infra runs **the kit's** `audit.py`, which is why this is a kit change and not
  infra's.

So the beneficiary of directives 1–2 is the member factory, and the beneficiary of a corrected
directive 3 is this factory's own audit verdict.

---

## 3. The design

Three legs. Leg A is the stamp; leg B is the metric the stamp must not blind; leg C is the gate that
makes both permanent.

### Leg A — date the subject, and make `duty` the terminal trailer

In `tools/audit.py` (and the byte-identical `TEMPLATE/tools/audit.py`):

1. **Subject** at `:3648` becomes `f"internal-self-audit-{today}"`, where `today` is the same UTC
   date string the report already uses (`today` is in scope at that call — the report path
   `evidence/scores/{today}-self-audit.md` is built from it two functions up, so the row and its
   artifact cannot disagree about the date).
2. **`duty`** is appended by `format_run_row_detail`, as the **last** token of the detail, because
   `declared_duty` reads the canonical trailer positionally. Rendering it mid-detail would put it
   in prose and it would declare nothing — the failure `mentions_duty` exists to name.
3. **The mapping** from the two existing fields, and it is total:

   | `gate_summary` | `outcome` | `duty=` |
   |---|---|---|
   | `skipped` | any | `skipped` |
   | `all-pass` / `gate-unknown` / `gate-failure` | `accepted` | `completed` |
   | `all-pass` / `gate-unknown` / `gate-failure` | `failed` | `failed` |

   `skipped` is tested first because a run that took no verdict is not a completed duty, whatever
   `outcome` says. `gate-unknown` maps to `completed` deliberately: the duty ran, and the *gates*
   being unknown is already carried by `gate=`, which is the field for it. Collapsing the two would
   be the `#143` class — one number answering two questions.

Resulting detail:

```
duration=<n>s turns=0 outcome=<accepted|failed> gate=<...> yield=<pct> duty=<completed|failed|skipped>
```

`outcome` is untouched in place, so `first_pass_yield_population` sees exactly what it saw before.

### Leg B — give the cadence check a subject, because it has none

`check_cadence_integrity(ledger_path)` becomes `check_cadence_integrity(ledger_path, stem, round_date)`
and keeps only rows whose subject matches the stem, using the **imported**
`receipt_subject_matches` — imported, never re-implemented, per the one-field-one-predicate rule
(`n=405` PART 5). Call site `:3443` passes `("internal-self-audit", today)`.

Its return shape gains one field that must not be optional: `rows_in_window` (how many rows named
this stem and this round). Without it, `cadence_held: True` is again indistinguishable from
"examined nothing" — the zero-from-a-broken-instrument class — and the whole point of leg B is that
the check must be able to fail.

**This is a strengthening the issue did not ask for, and it is the honest reading of directive 3.**
Directive 3 asks to protect the metric from dating. The metric is already immune to dating, and is
not measuring the audit. Installing the subject filter is what makes the metric measure the thing it
is named after. The issue's own remedy — it names `receipt_subject_matches` as a key — is that
installation, described from the wrong premise.

### Leg C — the gate, created rather than updated

New file `tests/test_audit_cadence.py` + its `TEMPLATE/tests/` twin, with five legs:

1. **Subject is dated and parses.** Render the subject for a fixed date and assert it equals
   `internal-self-audit-<date>` and that `datetime.date.fromisoformat` accepts the suffix.
2. **The row is matchable.** `receipt_subject_matches(subject, "internal-self-audit", date)` is
   `True` for the rendered subject and **`False`** for the bare stem — the second half is the
   control that proves the assertion can fail.
3. **`duty` is in the canonical trailer.** `declared_duty(detail)` returns exactly one value and it
   is in `DUTY_DOMAIN`, over the full `gate_summary` × `outcome` cross product, including
   `skipped`.
4. **`duty` does not enter the yield.** Build a stats dict, render the detail, feed it to whatever
   computes `first_pass_yield_population`, and assert the population is unchanged from the same
   detail rendered without `duty=`. This is the arm that would catch a future author "simplifying"
   `duty` into `outcome`.
5. **The cadence check bites.** Two fixtures: a ledger whose only stem-matching row is 40 h old
   (must read `cadence_held: False`), and one where the stem-matching row is fresh while a
   *different* subject's `run` row is also fresh (must read `cadence_held: True` **and**
   `rows_in_window == 1`). The second is the arm that proves the filter is a filter: before leg B
   the foreign row would satisfy the check.

The `TEMPLATE/tests/` twin is required: `tests/test_template_sync.py` compares the halves, and a
gate that exists in only one half is the drift that gate exists to catch.

---

## 4. Blast radius

| Surface | Effect | Reversible? |
|---|---|---|
| `first_pass_yield` / its population | **none** — `outcome` is untouched and `duty` is a separate field, by §2.3's stated constraint | n/a |
| This factory's audit verdict | **can flip to FAILED** once leg B lands: `verdict` is `PASSED` only when `cadence_held`, and the last `internal-self-audit` row is 20.15 days old (§2.2). Until a fresh self-audit lands, this factory's own audit reports FAILED. | yes — by stamping a self-audit row, which is the correct remedy |
| Infra's duty leg | **MISSING → ASSERTED** for its `internal-self-audit` declaration, on its next stamp | n/a (repair) |
| Other member factories | a subject whose stem is `internal-self-audit` and which is undated stops being matchable — but it was never matchable (§2.4), so no factory loses a working receipt | n/a |
| `duty=` on run rows | `declared_duty` will now return a value for these rows. Any leg that treats "a row declaring a duty" as a receipt will see three historical rows, all dated before 2026-10-04 | n/a |
| `docs/shipped-mechanism-law.json` | lists `receipt_subject_matches` as a shipped token with its clause; a new consumer does not change the token's meaning, but the entry's `why` should name the second consumer | yes |

The verdict flip is the item the owner is being asked to accept. It is not damage: the audit has
been reading `cadence_held: True` for 20 days while the thing it names has not run. The flip is the
metric starting to work.

---

## 5. Verification arms (for the implementing lane, after approval)

| # | Command | Expected |
|---|---|---|
| 1 | `python3 -m pytest tests/test_audit_cadence.py -q` | all legs pass, 0 failed |
| 2 | `python3 -m pytest tests/test_template_sync.py -q` | pass — the two halves are byte-identical |
| 3 | render a detail for each `gate_summary` × `outcome` pair; assert `declared_duty` returns one value in `DUTY_DOMAIN` | 8 combinations, 0 outside the domain |
| 4 | negative control: revert the subject to the bare stem in a scratch copy and run leg 2 of the new gate | **must FAIL** — a gate that cannot fail proves nothing |
| 5 | `python3 tools/audit.py --report --stamp` on a scratch tree, then read the appended row | subject ends in today's UTC date; detail's last token is `duty=completed` |

Arm 4 is the one that matters: without it the new gate is a control that cannot pass/fail, which is
precisely the defect the last two cycles filed against other gates.

---

## 6. Triage's two questions

### Q1 — `TEMPLATE/tests/test_audit_cadence.py` is missing. What is the design response?

**It has never existed**, in either half or any branch, and neither has `SELF_AUDIT_SUBJECT` (§2.5).
So this is not a lost file to be restored: directive 4 describes a tree state that this tree has
never been in. The response is to **create** the gate at the name the issue gives it — which is
fortunate, because the name is exactly right for the gate that would have caught this class. Leg C
above is that gate.

The residual risk is worth stating: the issue's author was describing the *kit as they remembered
it*, not as it is. Any other directive resting on a remembered file should be re-measured before it
is implemented, and that is a process finding for the ruling, not a defect in #324.

### Q2 — can a ruling hold this unit while `park` is undeclared (#535)?

**Yes, and `park` is not needed — nor lawful to invent.** The mechanism that holds a unit is a
**`claim` row**, measured: the patrol's `stall_census_leg` reports
`owed_units_carrying_a_claim: 0`, which means a claim removes a unit from OWED by itself. That is
the whole hold.

`disposition: void` is the wrong instrument: it voids an ACCEPTED unit, and #324 is accepted and
parked on the owner design gate. Inventing a `park` event to express "waiting for the owner" would
create an undeclared ledger event — the exact defect #535 files. So the ruling states the gate in
its body and stamps a `claim`; the design gate is then visible in the ruling and the hold is
visible in the ledger, with no new vocabulary.

---

## 7. What approval authorises

Approving #324 authorises, and only authorises:

1. Leg A — dated subject + `duty=` terminal trailer, in **both** halves of `tools/audit.py`.
2. Leg B — the subject filter in `check_cadence_integrity` + `rows_in_window` in its return shape.
3. Leg C — `tests/test_audit_cadence.py` + `TEMPLATE/tests/test_audit_cadence.py`.
4. The `docs/shipped-mechanism-law.json` note for the second consumer of `receipt_subject_matches`.

It does **not** authorise: any change to `outcome` or the yield; any new ledger event; any edit to
`src/` or the daemon; any change to another factory's registry; or backfilling the three historical
`internal-self-audit` rows (rows are immutable, `#317`).

Approval should say explicitly whether the **verdict flip** in §4 is accepted. If it is not, leg B
must be dropped, and then the issue's directive 3 should be closed as based on a false premise
rather than implemented — because without leg B the dating is invisible to every instrument.
