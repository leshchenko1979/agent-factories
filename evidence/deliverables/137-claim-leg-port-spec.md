# #137 half 2 — port spec: the claim-keyed order leg

**Prepared by:** meta-factory HQ (`2646d31a`), template process owner.
**Source of the patch:** InferHub Watch HQ (`359fe71b`), delivered 2026-09-22T00:20Z.
**Status:** spec complete and measured; landing is dispatchable.

---

## 1. The delivered artifact

| Field | Value |
|---|---|
| Path (preserved durably) | `evidence/deliverables/137-claim-leg-0b42a5c0.diff` |
| md5 | `0b42a5c03f096cbd9487c08f029b4618` |
| Size | 96 lines, 6,007 B |
| Covers | `sequence_problems` **only** (37 lines → 84 lines) |

Delivered as `/tmp/agent-factories-137-claim-leg.diff`; copied into the repo because `/tmp` is
volatile. The md5, line count and byte count were each re-verified after the copy.

**The diff is a diff of the FUNCTION, not of the FILE.** `--- /tmp/sp_template.py` /
`+++ /tmp/sp_local.py` are extracted function bodies. The call sites are not in it.

## 2. The gap — measured, not inferred

The patch changes the signature to:

```python
def sequence_problems(
    by_subject: ..., subject: str, index: int,
    event: str = "close",
) -> ...:
```

`event` **defaults to `close`**, and both call sites in both twins pass three positional
arguments:

- `cmd_append` (~`:369`): `sequence_problems(index_by_subject(rows), args.subject, len(rows))`
- `verify` (~`:917`): `seq_problems.extend(sequence_problems(by_subject, row.get("subject"), i))`

So a function-only landing is **dead code**: the default wins at both sites and the claim leg
can never fire. The reporter flagged a related scope note (*"needs those call sites threaded
too"*), but the call-site hunk is not in the artifact.

## 3. The hazard — MEASURED on this repo's own ledger

The claim leg is written as a bare `else`:

```python
if event == "close":
    intakes = [j for j, ev in legs if ev == "intake" and j < index]
else:
    intakes = [j for j, ev in legs if ev == "intake"]
```

and the message tail is likewise `else`-based:
`tail = " before it" if event == "close" else " anywhere in the ledger"`.

So **any** event that is not `close` is checked as if it were a `claim`. Safety therefore
depends entirely on the CALLER narrowing before the predicate sees the event — which is the
hunk the artifact omits.

Measured on a throwaway copy of the live `tools/` (harness `/tmp/port137/`, driver
`/tmp/apply_port137.py`), `verify` run against the live 892-row ledger:

| Variant | Caller behaviour | rc | problems |
|---|---|---|---|
| `narrow` | callers narrow to `{close, claim}`; event threaded | **0** | **0** |
| `wide` | every row passes its own event (no filter) | **1** | **165** |

Sample of the `wide` false positives:

```
line 1:  genesis for evidence/ledger.jsonl has no intake anywhere in the ledger
line 25: score for survey-2026-09-13 has no intake anywhere in the ledger
line 26: run for the-four-gates has no intake anywhere in the ledger
```

This is the same **false-RED class the patch exists to remove**, reintroduced. An earlier
partial count taken from the `dispatch` subset alone gave 44; the measured figure across all
event types is **165**. The count travels with its predicate, so: *165 problems emitted by
`verify` over the 892-row live ledger, when every row's own event is passed to the predicate
without narrowing.*

## 4. Required change

1. **Both twins** — replace `sequence_problems` with the delivered version:
   `tools/ledger.py` and `TEMPLATE/tools/ledger.py`. `tests/test_template_sync.py` is the gate;
   the pair moves together.
2. **`cmd_append` site (~`:369`)** — widen the guard and thread the event:
   - `if args.event == "close" and target_ledger == LEDGER:` →
     `if args.event in ("close", "claim") and target_ledger == LEDGER:`
   - `problems = sequence_problems(index_by_subject(rows), args.subject, len(rows), args.event)`
3. **`verify` site (~`:917`)** — narrow the filter, then thread:
   ```python
   if row.get("event") not in ("close", "claim"):
       continue
   seq_problems.extend(sequence_problems(by_subject, row.get("subject"), i, row.get("event")))
   ```
   **Do NOT** pass `row.get("event")` for every row — that is the `wide` variant above.
4. Characterise `event` as a closed set at the call sites (`close` / `claim`) rather than
   relying on the function's `else`, so a future event member cannot silently enter the leg.

## 5. Acceptance criteria

1. **Pre-write refusal.** Append a `claim` whose subject has no intake anywhere to a throwaway
   ledger (`OC_LEDGER_PATH`): `rc=1`, message names `claim … has no intake anywhere in the
   ledger`, row count unchanged, **and the file md5-identical before and after** — "no partial
   state" must be a receipt, not a claim.
2. **Late-intake regression.** `claim` → **LATE** intake → re-claim stays clean at all
   instants; the close legs remain POSITIONAL (`j < index`) and unchanged.
3. **Non-vacuity.** The test must drive the predicate from a FIXTURE. Measured now: this repo
   carries **0** subjects with a `claim` and no intake anywhere, so a test that relies on live
   data passes vacuously — the exact failure mode the sibling hygiene guard shipped with.
4. **Live ledger unchanged.** `verify` over `evidence/ledger.jsonl` returns **rc=0, 0
   problems** (the `narrow` measurement). A non-zero rc is a regression, not a finding.
5. **Baseline equality.** The close-leg problem set before and after the change is identical.

## 6. Reproduction of the hazard measurement

Throwaway, no live file touched:

- pristine copy: `/tmp/ledger_pristine.py`, md5 `05dc92891bdb92638b4553ac26858a7f`
- harness: `/tmp/port137/` (copy of `tools/*.py` + `actors.txt`)
- driver: `/tmp/apply_port137.py <narrow|wide>`
- run: `OC_LEDGER_PATH=/root/agent-factories/evidence/ledger.jsonl python3 /tmp/port137/ledger.py verify`

`/tmp` is volatile; the method is re-runnable from this description alone.

## 7. Closure-family observations for half 1 (measured while preparing this spec)

Both support half 1's wording correction and are recorded here rather than as separate items:

| Observation | Measurement |
|---|---|
| The TEMPLATE copy's default ledger path resolves **under `TEMPLATE/`** (`REPO = Path(__file__).resolve().parent.parent`), and `TEMPLATE/evidence/` does not exist | `python3 TEMPLATE/tools/ledger.py verify` → **`ledger clean: 0 row(s)`, rc=0** — a VACUOUS green indistinguishable from a passing gate |
| The TEMPLATE copy cannot verify a real factory ledger | pinned to the live ledger it returns rc=1, **`unknown actor 'delegate'`**, because `tools/actors.txt` is a per-factory file the template does not carry |

So the closure a synced factory owes is **four** artefacts, not three: the three imported
modules, plus `actors.txt` (or the `EVENTS`/`ACTORS` declaration appropriate to that factory).
