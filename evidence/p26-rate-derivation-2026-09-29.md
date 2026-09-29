# P26's companion rate — OPERATOR PROMPTS PER GOAL ACHIEVED

**Owns:** the derivation HQ's ruling `#234` (ledger `n=1663`) requires before the rate may enter
`docs/best-practices.md` **P26** as anything but a stated companion measure.

**Asked for:** *"the derivation stated as a predicate with its population (how many sessions, over
what window, at what instant), and a first reading with its variance."*

| | |
|---|---|
| **Read at** | `2026-09-29T12:23:30Z` |
| **Session store** | profile `ops` — `~/.opencrabs/profiles/ops/opencrabs.db`, opened `mode=ro` |
| **Ledger revision** | `origin/main` — 1690 rows, **207 `close` rows** |
| **Window** | `2026-09-12T11:00:15Z` → `2026-09-29T11:57:09Z` (the ledger's own first→last close) |

---

## 1. The load-bearing finding: `role='user'` is MOSTLY MACHINE

The obvious predicate — `messages WHERE role='user'` — is **not** the operator. In this harness a
cron dispatch, a `session_notify` from another lane, a `[SYSTEM: …]` marker and a
`[queued while you were working …]` note all land in the store as `role='user'`.

Measured, whole store:

| Predicate | Rows |
|---|---:|
| `role='user'` (the obvious one) | **45,501** |
| `role='user'` **anchored on the operator's author prefix** | **8,843** |

**The obvious predicate overstates the operator by 5.15x.** In the last 7 days the ratio is worse:
2,049 `[session-notify from=` rows against 979 operator rows — **machine wakes outnumber the
operator 2.09:1**. A rate computed on `role='user'` would have read **34.02 per close** where the
true figure is **11.00** — a 3.1x inflation, on a metric whose entire purpose is to fall.

This is the clause `#234` was right to demand. A metric written into law before its derivation is
named is a claim nothing computes; **a derivation written before its discriminator is settled is a
claim that computes the wrong thing, and it computes it confidently.**

---

## 2. THE PREDICATE

```sql
-- NUMERATOR — the operator's own hand.
-- Anchored at the operator's Telegram author prefix. The anchor is the discriminator:
-- an unanchored LIKE '%…%' also matches a machine message QUOTING the operator.
SELECT COUNT(*) FROM messages
 WHERE role = 'user'
   AND content LIKE 'Алексей Лещенко | Редевест (@leshchenko1979):%'
   AND created_at >= strftime('%s','2026-09-12T11:00:15Z');

-- DENOMINATOR — goals achieved, in the ledger's own vocabulary.
-- Read from the COMMITTED ledger at a named revision, never a working copy.
SELECT COUNT(*) FROM ledger WHERE event = 'close';
```

**Both operands are fleet-level, and the join key is the WINDOW, not the session.**
That is the derivation's central design choice, and §3 is the measurement that forces it.

**A second denominator is lawful and is reported as a COMPANION** (`#234` sanctions *"that session's
goal or its `close` row"*):

```sql
-- COMPANION DENOMINATOR — rung-4 goals
SELECT COUNT(*) FROM goal_state WHERE state = 'completed';
```

---

## 3. THE POPULATION — HQ's question, answered by measurement

HQ asked: *"which sessions are in the population — every session, or only sessions that produced a
goal or a close? A rate over sessions that never had a goal is a denominator that dilutes rather
than measures."*

**Measured: the population choice swings the answer 5.35x.**

| Population | Numerator | Denominator | Rate |
|---|---:|---:|---:|
| Every session | 8,843 | 13 goals | **680.23** |
| Goal-bearing sessions only | 1,653 | 13 goals | **127.15** |

So the concern is real — **but it is a property of the GOAL denominator, not of the population.**
A goal exists in only **22 sessions**, while the ledger closed **207 work units** across the fleet.
Pairing a fleet-wide numerator with a 22-session denominator is the mismatch.

**Resolution: use the `close` denominator. The dilution question then dissolves**, because both
operands are fleet-level and no session join is needed — the equality of scope is carried by the
window. The session join remains the right instrument only for the companion goal-denominator,
where it is also the *smallest* population, and it is reported as a companion for exactly that
reason.

**Session classes in the store** (1,645 sessions), stated so the scope is legible:

| Class | Sessions |
|---|---:|
| Telegram lanes | 491 |
| Cron sessions | 80 |
| Bot lanes | 1 |
| Other (A2A, subagent, team, CLI) | 1,073 |

---

## 4. FIRST READING

**`operator prompts per closed work unit = 2,849 / 207 = 13.76`**

at `2026-09-29T12:23:30Z`, over the window `2026-09-12T11:00:15Z → 2026-09-29T11:57:09Z`,
numerator from the `ops` session store, denominator from `evidence/ledger.jsonl` at `origin/main`.

**Companion (rung-4 goals): `2,849 / 8 = 356.12`** over the same window.

**Closes by actor, so the denominator is legible rather than a bare number:** worker 138, hq 48,
ledger 6, triage 5, surveys 5, insights 2, fleet-instruments 2, delegate 1 = 207.

---

## 5. VARIANCE — and the direction is NOT the one P26 wants

| Window | Operator prompts | Closes | Rate |
|---|---:|---:|---:|
| Prior 7 days | 1,143 | 109 | **10.49** |
| Last 7 days | 979 | 89 | **11.00** |

**Change: +4.9%. The rate is FLAT, not falling.** P26's own text says the falling number *"is the
evidence of transferability"* — so on this first reading the fleet has **no evidence of
transferability yet**. The operator's weekly volume did fall (1,143 → 979), but the fleet's output
fell with it, so the *rate* did not move.

That is a first reading at one interval, not a trend. It is stated because a first reading whose
direction is unfavourable is exactly the reading a derivation is tempted to bury.

---

## 6. BOUNDS — what this derivation does NOT claim

1. **A predicate, not a cause.** The rate counts the operator's hand. It does not say a lane would
   have succeeded without it — a prompt that redirects a wrong lane is not waste.
2. **The anchor's contamination is measured, not assumed absent:** 3 of 8,843 anchored rows also
   carry a machine marker (0.03%) — a machine message quoting the operator's own text.
3. **One store, one profile.** The `ops` profile. The `family` profile carries its own 46 MB store
   and is outside this reading's scope; stating the scope is the clause, not an oversight.
4. **The window is forced.** The ledger's first close is `2026-09-12T11:00:15Z` and the operator's
   prompts begin in July. A rate over all time would divide July prompts by September closes —
   the predicate/scope mismatch §8 names. The window is the earliest instant where **both**
   operands exist.
5. **Not a scored criterion.** Per `#234` and `n=574 PART 5`, P26's count remains the primary
   measure; the rate is a companion until it has a variance history.
6. **The instant is read, never composed.** Every figure above is a property of
   `2026-09-29T12:23:30Z`; both stores grow continuously and the count is stale the moment it is
   taken.

---

## 7. REPRODUCE

```bash
# denominator — the COMMITTED ledger, at a named revision
git -C /root/agent-factories show origin/main:evidence/ledger.jsonl \
  | python3 -c "import json,sys; print(sum(1 for l in sys.stdin if json.loads(l).get('event')=='close'))"

# numerator — the session store, read-only
sqlite3 "file:/root/.opencrabs/profiles/ops/opencrabs.db?mode=ro" \
  "SELECT COUNT(*) FROM messages WHERE role='user'
    AND content LIKE 'Алексей Лещенко | Редевест (@leshchenko1979):%'
    AND created_at >= strftime('%s','2026-09-12T11:00:15Z');"
```

Stamp `date -u` beside the output: neither store prints its own instant, and a count without one
cannot be re-checked.
