# Model calls BETWEEN consecutive compactions — first reading (2026-09-20)

**Standing reading** added to `docs/measurement-procedure.md` step 7, beside the compaction-RATE
leg, by ruling **n=677** (board issue **#114**), which continues ruling n=643 (board #108).
It is **PRINTED, never a scored criterion** — a compaction rate is substantially a harness
property, and a scored criterion must be actionable by the scored party.

The leg exists because the ratio is blind to it: `compactions:turns` scores a lane that
compacts once per turn after **40 calls of work** identically to a spiral that compacts once
per turn after **2**.

## The reading

| field | value |
|---|---|
| **Instant of the read** | `2026-09-20T03:59:19Z` |
| **Scope** | ops daemon log, `opencrabs.2026-09-19` + `opencrabs.2026-09-20` (paths read = 2) |
| **Population** | **111 lanes read** · 1,250 compactions · 347 settled turns · **1,164 clean intervals examined** |
| **Model calls** | 42,528 attributed (44,072 streaming lines seen; 1,544 carried no `session_id`) |
| fleet calls per compaction | 34.02 |

| figure | value |
|---|---|
| **median clean interval** | **18.0 calls** |
| p25 / p75 | 4 / 43 |
| min / max interval | 0 / 357 |
| **share of intervals at or below 5 calls** | **35.0%** |
| lanes read / with ≥1 compaction / with a computable interval | 111 / 67 / 52 |
| **per-lane median spread** | **1.0 → 75.0** (median of per-lane medians 27.5) |
| lanes with ≥1 compaction and **ZERO** settled turns | 20 |

Interval distribution:

| interval | intervals | share |
|---|---|---|
| 0 calls | 8 | 0.7% |
| 1–2 calls | 211 | 18.1% |
| 3–5 calls | 189 | 16.2% |
| 6–20 calls | 221 | 19.0% |
| 21–100 calls | 468 | 40.2% |
| >100 calls | 67 | 5.8% |

## What this leg sees that the ratio cannot

Two lanes compacting at a similar rate, separated by what the companion measures — the interval
between compactions, not their count:

| lane | compactions | median calls between |
|---|---|---|
| Triage: Issue Portfolio & Harvest Analysis | 105 | **4.0** |
| Opencrabs Dev Factory / Compaction visibility | 91 | **3.0** |
| Opencrabs Dev Factory / #87 config | 63 | **2.0** |
| Fix #149: Cron Session Isolation | 59 | **4.5** |
| Opencrabs Dev Factory / #92 demote | 29 | **4.0** |
| Opencrabs Dev Factory / streaming- | 23 | **4.0** |
| Opencrabs Dev Factory / Graceful r… | 20 | **2.0** |
| Opencrabs Dev Factory / Rich resum… | 13 | **3.0** |
| Opencrabs Dev Factory / Subagents … | 13 | **3.0** |
| — for contrast — | | |
| Factories / Worker | 99 | 42.0 |
| Toolsmith Issue 255 and PR Dependency Laws | 53 | 42.0 |
| Opencrabs Dev Factory / JEV Classifier | 43 | 27.0 |

The first group reaches a compaction after a handful of calls; the second works for dozens of
calls per compaction. The rate leg names both "IN A LOOP" at or above 1:1, and it is right to —
but only this leg says which of them is working between compactions and which is turning over
its own context.

**A lane whose intervals cannot be computed prints its raw counts and the reason, never a
computed ratio.** 44 of the 111 lanes read carried **no** compaction in scope (cron and
short-lived sessions); 15 more carried one compaction and therefore no consecutive pair. Their
counts are printed; no interval is invented for them.

## The two traps, re-verified first-hand for this reading

Neither is transcribed from the ruling — both were measured on the ops daemon log this turn
(2026-09-20, ~03:59Z):

| log | `triggering LLM compaction` (CHECK line) | `Spawning background compaction at` (real) | inflation |
|---|---|---|---|
| 09-18 | 2,518 | 466 | 5.4× |
| 09-19 | 8,916 | 1,038 | **8.6×** |
| 09-20 | 1,799 | 211 | **8.5×** |

Counting the CHECK line over-counts by roughly **8.5×** and fails toward a *confident* wrong
number: on OpenCrabs Dev HQ's first pass it produced *"median 0 model calls between
compactions"*.

**Trap 2 — anchor on TEXT, never a line number.** The dispatch line drifts per build
(`custom_openai_compatible.rs` read `:3631` on 09-18, `:3667` and `:3673` on 09-19 with the
daemon swapped mid-day, `:3673` on 09-20). The call text `streaming request: model=` is present
**33,164 times** in the 09-18 log — the day a line-number anchor returned **zero** calls. A
total, silent loss of the population that reads exactly like a quiet box.

## Reproduce

```bash
cd /root/agent-factories
date -u +'INSTANT=%Y-%m-%dT%H:%M:%SZ' > /tmp/cpc.txt
python3 ~/.opencrabs/profiles/ops/opencrabs-dev/instruments/calls-per-compaction.py \
  /root/.opencrabs/profiles/ops/logs/opencrabs.2026-09-19 \
  /root/.opencrabs/profiles/ops/logs/opencrabs.2026-09-20 >> /tmp/cpc.txt 2>&1
```

The instrument streams the daemon log line by line with bounded RSS and reads no database, so
it is safe on this memory-constrained host. It prints the population itself (paths, lanes,
intervals examined); the instant is stamped beside the output by the run.

## Bounds, stated rather than hidden

1. The predicate counts **dispatch** lines, so a request that never reaches one contributes no
   call.
2. A call is attributed to a lane only when its line carries a `session_id` — over these two
   logs **1,544 of 44,072** streaming lines (**3.5%**) carried none; they enter no lane figure
   and no fleet ratio.
3. An interval is defined **within one session**, so a lane's first compaction opens none.
4. Scope difference from the rate leg, stated so it is not read as a contradiction: this reading
   covers two whole logs (~28 h) while the rate reading's window is the last 3 h, which is why
   the settled-turn totals differ (347 here against ~45–49 there).

## Instrument durability

`~/.opencrabs/profiles/ops/opencrabs-dev/instruments/calls-per-compaction.py` — 5,778 bytes,
md5 `f43b76f8b975a289d6252a105ab65db9`, matching the hash in ruling n=677. The ruling and the
intake row record it as **untracked**; a peer lane committed it at `2026-09-20T03:56:11Z` as
`c1f71d93` (blob md5 identical), so it is tracked now. **Durability, corrected against the live
remote rather than left as first read:** at `03:57Z` this lane read `origin/main` at `91cacb2b`
behind a 21-commit unpushed backlog (last push `01:01:36Z`); a peer lane's state sweep pushed at
~`04:00Z` and flushed it, so `c1f71d93` is now an ancestor of `origin/main` and the file is
present there — `git show origin/main:instruments/calls-per-compaction.py | md5sum` returns
`f43b76f8b975a289d6252a105ab65db9`, identical to the working copy. Acceptance criterion 5 is met
in full: committed **and** pushed.

One gap, offered rather than silently patched: the instrument prints its **population** but not
the **instant**, unlike `tools/compaction_rate.py`. The reading text therefore requires the
instant stamped beside the output. Adding it to the instrument would change a hash pinned in the
ruling, so it is left to OpenCrabs Dev HQ, which authored the file.
