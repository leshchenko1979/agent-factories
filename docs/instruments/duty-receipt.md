# The duty receipt

**Owns:** the writer's rule for a duty receipt — where the `duty` token goes, why its position
is the difference between a declaration and a discussion, and the reader that reports the rows
already written the wrong way. It owns **no** cross-instrument definition; those live in
`template-instruments.md`, the frame, which this file cites and never restates.

**Why a home was owed (issue #587, ruled at n=4483).** #498 closed on 2026-10-16 ordering a
writer-side trailer rule. It landed nowhere a receipt author reads: measured on this tree at
4486 ledger rows, the meta-factory law carried zero occurrences of `trailer` or `duty=completed`,
and `docs/instruments/` shipped no duty-receipt doc. The rule was therefore obeyed by whoever
already knew it and invisible to everyone else — and the population shows the cost: 26 `run`
rows carry the token in PROSE while their canonical trailer declares NOTHING, 18 of them
written AFTER the rule was ordered, the newest at `2026-10-29T18:06:45Z`.

## 1. The rule

**A duty receipt declares its completion in the CANONICAL TRAILER — a `duty=<value>` line at
the end of `detail` — and never in the prose above it.**

```text
… the round's body, in prose …
duty=completed
```

The trailer is the only position a reader treats as a declaration. A token inside a sentence is
a MENTION: it may be a citation of another row's token, a discussion of the field, or a
description of what the author intends. None of those is a declaration, and the reader that
counts declarations is right to ignore all three.

## 2. Why position is the whole rule

`tools/field_predicate.py` exposes the pair, and the split between them is load-bearing:

| reader | answers | used for |
|---|---|---|
| `declared_duty(detail)` | what the CANONICAL TRAILER declares, as a list | the VERDICT on any receipt |
| `mentions_duty(detail)` | did the `duty` KEY appear in the row's own voice, anywhere | naming WHY a verdict is empty — never the verdict |

The run is POSITIONAL, matching `declared_rework` and `declared_telemetry_provenance`. That is
deliberate and it is not a parser limitation: a receipt's detail discusses completion at length,
so a whole-detail scan would read the discussion as the declaration — the damage ruled at `n=405`
clause 5, "prose must not SATISFY a field". `mentions_duty` is therefore asked ONLY of a row
whose trailer already declared nothing, so the token it finds is by construction outside the run.

Two consequences for a writer:

- **A token mid-sentence does not declare, and will not be read as one.** The author is told the
  duty is undeclared while believing they declared it — the failure mode this doc exists to stop.
- **A trailer terminated early is a trailer with nothing in it.** A `Session: <uuid> (actor …)`
  line carrying no `=` ends the run before it starts; put `duty=` on a line of its own, after it.

## 3. What reads it

`tools/patrol_host_state.py` judges this class in two places, and the split is why a third reader
was owed:

| reader | population | sees a prose token when |
|---|---|---|
| `duty_round_finding` | one round's receipts, judged per fire | the round carries **no** declaring receipt |
| `duty_receipt_leg` | the CRON ROWS — does the prompt declare a stem at all | never: it judges declarations, not receipts |
| `duty-receipt-prose` | every `run` row on a DECLARED stem, census-wide | always |

Measured on this tree: of the 26 prose-token rows, **16 sit in rounds that DO carry a declaring
receipt**, so `duty_round_finding`'s malformed branch is structurally blind to them (it requires
`not receipts`), and the other 10 it already reports. The census is the reader that sees all of
them, and it is READ-SIDE on purpose: the ledger is append-only and **no backfill is ordered**,
so a writer fix alone would govern only the future and leave the population invisible.

## 4. The verdict splits at the rule's own instant

The census reports findings stamped on/after `2026-10-16` as PROBLEMS — the rule was in force
when they were written — and findings before it as EXCUSED visible debt. Without that split the
leg is un-greenable by construction: the pre-rule rows can never be repaired, so it would be red
forever, which is the "red that teaches lanes to ignore red" declined at ruling `n=1579`.

The leg also prints its population and its class boundary beside the verdict, so no reader has
to infer either: rows on stems this factory does not declare, and rows on non-`run` events, are
counted and named as OUTSIDE the population rather than folded into the finding count.

## 5. What a writer owes, in one line

**Write `duty=<value>` as the terminal line of `detail`.** If a receipt already reads
`declared_duty -> []` while its author believes it declared, the token is in the prose: move it
to the trailer. The reader cannot meet you halfway — the position IS the declaration.

## 6. The residual has an exclusion surface (#617)

The forward window a job is judged against is DERIVED from that job's own measured
fire-to-receipt latency, so every observation that enters it must be a fact about the LANE.
Two classes are not, and both are dropped before the maximum is taken:

| class | why it is not promptness data | how a row declares itself |
|---|---|---|
| a round the factory declared owed nothing | the duty never existed, so there was nothing to be prompt about | a ROUND-SCOPED entry in `docs/duty-receipt-exemptions.json` (an entry carrying a `round` key) |
| a RECOVERY receipt | it exists to make an already-completed round VISIBLE to the pairing, so its timestamp dates the repair, not the lane | the terminal trailer `observation=recovery`, or the clause `RECOVERY record, not a latency observation` |

The distinction the first row rests on is that **"was this round receipted?" and "how prompt is
this lane?" are two questions**, and only the second one is the residual's. A recovery row must
therefore REMAIN a valid pairing — the leg still sees its round as receipted — while never
entering the observations.

Measured cost of getting this wrong, on `factory-hq-pacemaker` (2026-11-05): one recovery row
(`n=4781`) entered as an 80.33 h observation, lifting the job's measured max from 18.97 h to
80.33 h and its derived residual from 75.87 h to 321.31 h — and because that window then
excused BOTH of the job's rounds as still inside it, the job had no round left to judge at all.
A wider window is SILENT; a narrower one costs one look. So both exclusions err narrow, and both
are COUNTED and PRINTED: a window resting on fewer observations than the job has rounds must
never be readable as a prompt lane.

No backfill is ordered and none is possible: the fix is read-side, and the ledger is
append-only.
