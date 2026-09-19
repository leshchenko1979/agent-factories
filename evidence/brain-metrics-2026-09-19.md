# Brain metrics — 2026-09-19

**Question (owner, Alexey, 2026-09-19):** can each factory measure its brain metrics —
(a) LOC of the always-inserted files, (b) LOC of `SKILL.md` in the main factory skill,
(c) the average post-compaction context size against the full provider context size?

**Answer:** (a) and (b) yes, from the filesystem. (c) yes, from the daemon logs — the
compaction path logs its exact input-token figure. **None of the three is codified today:**
`tools/` ships no brain-metrics instrument, so these are hand measurements, reproducible
with the script recorded in §Reproduce.

Measured by the HQ lane (`2646d31a-71ee-49f0-be81-9c8dc32d32fa`), ledger row n=557.

---

## (a) Always-inserted files — LOC

The files the runtime injects into every session on this profile.

| File | Lines | Bytes |
|---|---|---|
| `SOUL.md` | 12 | 1,237 |
| `USER.md` | 45 | 3,452 |
| `AGENTS.md` | 531 | 67,704 |
| **Total** | **588** | **72,393** |

`AGENTS.md` is **90.3%** of the always-injected line count and **93.5%** of its bytes — it is
the file that dominates this metric, and it is the one already flagged as over the 500-line
skill budget.

## (b) Main factory skill — LOC

`skills/meta-factory/SKILL.md`, resolved from the profile symlink to
`/root/agent-factories/skills/meta-factory/SKILL.md`:

| Metric | Value |
|---|---|
| Lines | 452 |
| Bytes | 32,247 |

Under the 500-line warning threshold, but 452 lines is close enough that the next few law
additions will cross it.

### Token equivalents (proxy, ratio stated)

Tokens are **not** logged for the static files, so these are proxies at **3.5 chars/token**
(the ratio measured for English markdown — see the unit law in `AGENTS.md`; Cyrillic runs
~1.7, so a mixed-language profile would differ).

| Corpus | Lines | Bytes | ~Tokens | % of 200k |
|---|---|---|---|---|
| Always-injected | 588 | 72,393 | 20,684 | 10.3% |
| `SKILL.md` | 452 | 32,247 | 9,213 | 4.6% |
| **Combined** | 1,040 | 104,640 | **29,897** | **14.9%** |

So the static brain — the floor every session pays before it reads a single message — is
about **15% of the provider window**.

## (c) Post-compaction context size

**Source:** the daemon's own log line (`src/brain/agent/service/context.rs:1007`), which
records the exact input-token count of each compaction:

```
Compaction: sending 67 / 67 messages to summarizer (79111 / 200000 input tokens, reserving 9000 for output)
```

**Population:** every occurrence across all profile logs, `opencrabs.2026-09-12.gz` through
`opencrabs.2026-09-19` — **n = 2,011** samples. Provider limit was 200,000 in every sample
(no other window appears).

| Statistic | Input tokens | % of 200,000 |
|---|---|---|
| Mean | 66,393 | **33.2%** |
| Median | 70,493 | 35.2% |
| p90 | 97,608 | 48.8% |
| min / max | 6,397 / 153,037 | 3.2% / 76.5% |

**Headline: mean 66,393 tokens = 33.2% of the provider window; median 35.2%.**

### Per-lane (meta-factory lanes only)

Lane attribution requires a `session_id` span prefix on the log line. Only **184 of 2,011
samples (9.1%)** carry one — the prefix appears only on recent days (09-17 onward), so this
subset is **biased toward recent, busier sessions** and is reported separately for that
reason, never merged into the population above.

| Lane | n | Mean tokens | % of 200k | Median |
|---|---|---|---|---|
| HQ (topic 21) | 10 | 102,853 | 51.4% | 51.4% |
| Worker (topic 1271) | 4 | 123,058 | 61.5% | 61.8% |
| Triage (topic 20) | 4 | 98,258 | 49.1% | 47.6% |
| Delegate (topic 68) | 0 | — | — | — |
| Surveys (topic 19) | 0 | — | — | — |
| **Combined** | **18** | **106,322** | **53.2%** | **51.4%** |

**The meta-factory lanes compact at roughly 1.6× the profile-wide average** (53.2% vs 33.2%).
That is the expected shape: these are long-lived, law-heavy lanes that accumulate context
and compact when full, while the profile-wide population is dominated by short-lived
sessions that compact at low occupancy. Delegate and Surveys have no attributable samples —
which is a coverage gap, not a zero.

### Caveat — the trigger percentage is NOT the window ratio

The trigger logs `Context at 66% (>65%) — triggering LLM compaction`, but the same compaction
measures ~33% of the 200k window. These are **different denominators**, from
`compaction.rs:269-270`:

```
usage_pct = context.effective_token_count() / effective_max * 100.0
```

`effective_max` is the **effective** budget (window minus reserves such as the 9,000 output
reserve), and `effective_token_count()` is the runtime's own estimate — neither is the raw
2,000-window input-token count. **Never read the trigger percentage as a fraction of the
provider window;** the ratio in the table above is the window fraction.

---

## Reproduce

`/tmp/brain_metrics.py` (measurement script; streams every log line-by-line — no whole-file
reads, per the memory-constrained-host rule). LOC:

```sh
for f in SOUL.md USER.md AGENTS.md; do wc -lc ~/.opencrabs/profiles/ops/$f; done
wc -lc ~/.opencrabs/profiles/ops/skills/meta-factory/SKILL.md
```

## Gap — this measurement is not codified

There is **no brain-metrics instrument in `tools/`** (`audit.py`, `hygiene.py`,
`insights.py`, `ledger.py`, `registry.py`, `review.py`, `roadmap.py`, `synthesize_insights.py`,
`telemetry.py` — none measures any of the three). Consequences:

1. A member factory cannot self-measure this from its own tooling; it would have to
   re-derive the log format, as this lane did.
2. The metric is not on the measurement cadence, so it cannot show drift as a diff —
   which is the whole point of `evidence/scores/<date>.md`.
3. The static-brain floor (~15%) is invisible to every existing gate.

**Candidate law:** brain metrics are a *harness* concern, not a factory concern — the log
line, the injection set and the window all belong to the runtime. If codified, it belongs
in the template as a measurement the factory *consumes*, with the runtime supplying the
figures.
