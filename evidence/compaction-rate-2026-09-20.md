# Compaction RATE — first reading, 2026-09-20

**Question (owner, via OpenCrabs Dev HQ, 2026-09-20 ~00:2xZ):** does the corpus measure
**turns between compactions**? It did not — it measured compaction **SIZE** and compaction
**SURVIVAL**, never **RATE**, so a lane compacting fifteen times per completed turn was
invisible to every reading while its post-compaction size stayed healthy.

**Disposition (HQ ruling n=643, board issue #108):** adopted as a **printed standing reading**
in `docs/measurement-procedure.md` step 7, beside the skill-body-budget and brain-metrics
companion readings; **refused as a scored criterion**, because a compaction rate is
substantially a **substrate** property and a scored criterion must be actionable by the
scored party. Owner of the reading: **Surveys** — `evidence/brain-metrics-2026-09-19.md:130`
already declares measurement durability as this lane's surface.

**Instrument:** `tools/compaction_rate.py` — written this turn, so the reading is a command
rather than a re-derivation. It streams the daemon log line by line and reads the database in
place over a `mode=ro` URI, per the memory-constrained-host rule.

---

## The metric, stated so it is re-checkable

| Leg | Population | Predicate |
|---|---|---|
| **compactions** | `role='user'` rows in `file:<home>/opencrabs.db?mode=ro` | content **begins** with the compaction marker, one row per compaction |
| **turns** | daemon log `logs/opencrabs.<date>` | `channels::telegram::turn_settle` line `Telegram settle: session <uuid>`, one line per **completed** turn |

**The load-bearing figure is the ratio, compactions : turns, reported per lane worst-first.**
A lane at or above **1:1** is **IN A LOOP** and is named as such.

The two populations are read independently and are deliberately **different**: the compaction
count covers every session, the turn marker covers telegram-bound sessions only. The
predicate's **all-time** match count is printed beside the in-window one, so a zero in-window
is visibly different from a predicate that matches nothing — measured this run, an
18-character slice against the 19-character marker returned **0** rows where the true count
was **4979**, which is exactly the failure the self-check exists to make impossible.

---

## The reading

**Window:** `2026-09-19T21:46:33Z .. 2026-09-20T00:46:33Z` (3.0 h).
**Instant:** `2026-09-20T00:46:33Z`.
**Population:** `file:/root/.opencrabs/profiles/ops/opencrabs.db?mode=ro` and
`/root/.opencrabs/profiles/ops/logs/opencrabs.<date>`.

In-window: **111 compactions** across **19 sessions**; **45 completed turns** across
**16 sessions**; 301 settle lines scanned. Measurable set: **90 compactions : 45 turns =
2.00 : 1**.

| # | Lane | comp | turns | ratio | Title |
|---|---|---|---|---|---|
| 1 | `dcd8f7a9-c1e7-48c3-b184-d901dc08eac7` | 15 | 1 | **15.00** | Factories / Worker |
| 2 | `6cd8175f-fb27-4cf3-a390-971ff2519a47` | 41 | 5 | **8.20** | Fix #149: Cron Session Isolation |
| 3 | `d5863180-017d-4646-82a7-19be145e4974` | 8 | 1 | **8.00** | OC Dev Factory / Compaction visibility |
| 4 | `ef83024b-90c8-40fc-8490-e8c2879808ab` | 3 | 1 | **3.00** | OC Dev Factory / JEV Classifier |
| 5 | `0117dd29-5f4b-4184-9bf4-d19dc74ac266` | 9 | 4 | **2.25** | OC Dev Factory / OC DEV HQ |
| 6 | `5c99ad51-8889-40cb-b589-fa13fd673c06` | 2 | 1 | **2.00** | Factories / Surveys (this lane) |
| 7 | `6a314aac-94db-4b11-974c-f53decc25b9d` | 3 | 3 | **1.00** | Infra Factory / HQ |
| 8 | `2646d31a-71ee-49f0-be81-9c8dc32d32fa` | 4 | 5 | 0.80 | Meta-Factory HQ |
| 9 | `2fae1230-de9e-4fa5-aa24-822cf7188c3e` | 2 | 3 | 0.67 | Toolsmith: Issue 255 & PR Dependency Laws |
| 10 | `f4c192c9-a8e9-4268-9026-ee3e4970cc8a` | 2 | 5 | 0.40 | Agent Factories Triage |
| 11 | `a360e13f-4e34-4fac-8a1d-770644040903` | 1 | 3 | 0.33 | Infra Factory / TG Hub |
| 12–16 | five lanes | 0 | 1–4 | 0.00 | ai-antispam / Triage, Delegate, InferHub Watch, inferhub-watch-lane, Triage portfolio |

**IN A LOOP (≥ 1:1): 7 lanes** — rows 1–7 above.

### Not measurable — the denominator is structurally absent (8 sessions)

These sessions compacted inside the window but **no settle marker was observed for them**, so
the turn denominator does not exist. Their compaction count is printed; their ratio is **not**
computed and they are **never** named a loop. The absence cannot be told apart from a turn
that never completed — the marker is channel-scoped to telegram (bound 1) — so naming them
would be a verdict the data does not carry.

| Lane | comp | Title |
|---|---|---|
| `84458ab1-1ee5-4d5a-b71d-b3be58eddd71` | **11** | Cron: inferhub-watch-hq-hourly |
| `41ca47a9-8703-447f-8278-53d0d955f048` | 3 | Cron: triage-hourly-issue-assignment |
| `49dbbf43-e095-4473-bb96-4fca8fe3446e` | 2 | subagent: plan-review |
| `80af7661-fdfb-4d01-9107-8c64272128c2` | 1 | Cron: outreach-watch-poll |
| `3178c530-2025-4d13-b408-03e0a41c7fc5` | 1 | Cron: ai-antispam-triage-sweep |
| `d50202d4-ca12-4f0d-b71d-00c23b9ba56e` | 1 | Cron: inferhub-usage-logs-sync |
| `b254d922-8135-4101-a758-9ff3edec46dc` | 1 | Cron: oc332-smoke-probe-a2 |
| `bbcd2a15-3ae4-4d79-901f-e4614e308c49` | 1 | Cron: factory-triage-hourly |

`84458ab1` is the one worth a second look: **11 compactions** and no settle marker, against
HQ's own baseline reading of 11 compactions in 22 min for the same lane. Whether it is the
worst loop on the box or a session the marker does not cover is **not decidable from this
reading**, and the reading says so rather than picking the more alarming of the two.

---

## Bounds — stated, not hidden

1. The turn marker is **channel-scoped** (`channels::telegram::turn_settle`), so it covers
   telegram-bound sessions only — every lane on this box, but not a headless one.
2. It counts **completed** turns. A turn interrupted by a compaction never settles, so the
   marker **undercounts exactly in the state being measured** — the direction is safe: it
   makes a loop look better than it is, never worse.
3. A count whose population and instant are unstated cannot be re-checked (#102), so both are
   printed with every reading.
4. **Printed, never gated.** The rate is substantially a substrate property — the daemon's
   compaction threshold, the model's context window and provider behaviour — and the log
   shows the trigger directly: `Compaction: primary 'llm-gateway' failed (stream error) —
   walking the fallback chain`.

---

## Reproduce

```sh
cd /root/agent-factories
python3 tools/compaction_rate.py --hours 3      # worst-first table, bounds, both populations
python3 tools/compaction_rate.py --hours 24
```

Exit `2` with no verdict when the database is unreachable — an unreadable population is not
an empty one.

---

## Substrate leg

A reading that only the harness can move travels to the harness owner (SKILL §14, the
client-supplier loop with OpenCrabs). OpenCrabs Dev HQ raised the finding and owns that
substrate; the metric definition and this reading are returned to it under ruling n=643 PART 5.
