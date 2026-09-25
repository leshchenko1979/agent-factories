# Ledger number problems — roots, and whether a substrate swap fixes them

**Asked by the owner, 2026-09-25 12:2x MSK:** *"I often see the ledger number problems in
this and other factories. What do they arise from? Will the YYLO solve the root cause?"*

**Measured** over `evidence/ledger.jsonl` at **1058 rows**, 2026-09-25 ~09:30Z, plus the
instances ruled this session. Every figure below states its predicate.

---

## 1. What "number problems" actually are — four distinct classes

They look like one family and are four. They have different causes, and only one of them
is about the storage format.

### Class A — a declared count against the row's own ordinal

`close` rows may declare the row count a `verify` run measured (`rows=N`), and the gate
requires `N >= the row's own n`.

| predicate | count |
|---|---|
| `close` rows total | 129 |
| carry **no** `rows=` token (pre-boundary closes) | 112 |
| declare `rows=` **correctly** | 14 |
| declare `rows=` and **genuinely mismatch** | **2** |

The two genuine mismatches, both in `docs/close-verify-count-exemptions.json` as
PERMANENT DEBT:

- **n=931** declared `rows=930` — the lane ran `append` **twice in one turn** against the
  same detail, so the receipt covered n=930 and not itself.
- **n=1014** declared `rows=1013` — Triage read the count, and **a peer's close (n=1013)
  landed between its read and its append**.

**Cause, stated once:** the row number is computed **inside the append lock**, so an
author must *predict* it. The prediction races every other lane. This is structural, not
carelessness — the tool never tells the author the number before the write.

### Class B — a bare `#N` used as durable identity

| predicate | count |
|---|---|
| rows carrying a bare `#N` subject | **817 of 1058 (77 %)** |
| distinct bare subjects | 157 |
| bare subjects whose rows span >1 day (collision *candidates*) | 14 |

A bare integer is a durable identity but not a **unique** one: it carries no namespace,
so two boards' `#N` are the same key. Three live instances:

- **ai-antispam's rows n=1/2/5** carry subject `#35`, written 2026-09-17 — while that
  board's `#35` was created a **day later**, meaning something else.
- **`#39` means two different units** on two boards right now: ai-antispam's is OPEN
  (*"board closes are not reaching the ledger"*); this factory's is CLOSED (*"the ontology
  defines a work unit as an issue"*).
- **The daemon's own error string** cites `(#148)` — the *fork's* #148, not this board's.

The consequence is worse than a misread: the sequence predicate keys on the raw subject
string, so a second board's `#17` **inherits the first board's legs**, and a close with
no legs of its own is **accepted**. The guard is defeated exactly where a collision
exists — measured, control-paired (arms 2 and 3).

### Class C — legality as a function of cross-lane order

The sequence legs (`intake -> claim -> dispatch -> close`) are checked **at write time**
against state that other lanes mutate concurrently, and the legs are stamped by
**different lanes with independent wake latencies**. Two live instances this session:

- **#127** — the close was refused: *"no claim before it"*. There was no claim row at all.
- **#161** — the close was refused: *"its claim precedes its intake"*. The Worker claimed
  **10 s** after I dispatched, while Triage stamped intake **1 m 46 s** after that.

An author who follows the law exactly can still produce an unlawful sequence, because
they do not control the other lane's wake time. The remedy (a re-claim) is mechanical and
cheap, but nothing in the law says it is *expected* — so every occurrence reads as
someone's error.

### Class D — an identifier cited before it exists

- **Three of my own ruling comments** this session cited `n=1016`, `n=1017`, `n=1031` —
  each typed from expectation *before* the append. All three resolved to **real rows of a
  different lane and subject**.
- **A peer's notify** hand-assembled a session UUID tail (`d32fa` → `d82fa`), queuing to a
  session that does not exist.
- **A cross-linked commit sha** in a ruling was superseded and unreachable from any branch
  when the ruling landed.

---

## 2. The root cause, stated once

**Every one of the four is the same shape: an artifact outside the ledger must cite a
value the ledger assigns — at an instant before the ledger assigns it, or in a namespace
where that value is not unique.**

Three sub-causes, one per mechanism:

1. **Assignment time ≠ citation time.** `n` is computed inside the lock; the comment,
   commit message, prompt, and the row's own count declaration are composed *around* it.
   → Classes A and D.
2. **Identity without a namespace.** A bare integer is durable but not unique. → Class B.
3. **Legality depends on cross-lane ordering.** Sequence legs are evaluated against state
   two lanes mutate at independent instants. → Class C.

The common factor is **not** JSONL, not the file, and not the git plumbing. It is that we
ask authors to *assert facts about the ledger* that only the ledger can produce.

---

## 3. Would YYLO fix it? — measured, per class

Source: `docs/proposals/04-yylo-ledger-spike.md` (bare origin, two clones, five legs).

| Class | YYLO | Why |
|---|---|---|
| **A** — declared count vs ordinal | **Not solved** | YYLO has **no global ordinal at all** (identity is a per-task nanoid). If we need a sequence — and `verify`, the gates and 44 readers do — it must be **built on top**, with the same race |
| **B** — bare `#N` identity | **Solved, at migration cost** | nanoids are globally unique, so the collision class disappears — but only if 817 subjects and every reader migrate |
| **C** — cross-lane ordering | **Not solved** | `--expected-revision` is **local-only** (measured: a write stale against origin was accepted); conflicts are a **Git conflict requiring manual resolution** |
| **D** — cited before it exists | **Solved for ids** | `create` returns the id, so you cite what you were given rather than what you predicted |

### The disqualifier is Class C's convergence rule

YYLO converges **canonical-wins**: the losing branch's event is **discarded from the
ledger** (measured — `history` shows 2 events where 3 were written; the loser is gone,
recoverable only from Git's history).

Our entire ledger law is **append-only**: no row is ever lost, corrections are new rows,
`verify` is monotonic, the no-shrink gate exists to catch a rewrite. A substrate whose
merge **deletes a recorded event** converts *"a number was wrong and we appended a
correction"* into *"the row is gone"* — and would make the `n=931` / `n=1014` repairs
impossible by construction.

So: **No.** YYLO solves one class (B), leaves one unsolved (A), and makes the class that
matters most for a ledger **worse**. It is a good task tracker; a ledger needs the
opposite convergence rule.

---

## 4. The cheap fixes — all inside the current ledger

The root cause is addressable without changing the substrate:

1. **The tool returns the assigned number; nothing outside authors it.** This is already
   the shape of the §4 and #144 rulings. The remaining gap is the **count declaration**:
   the author runs `verify` (reads N) and must predict that the append becomes N+1 — a
   race by construction. Proposal: `append` accepts a "record the count I just measured"
   flag and stamps both the count and the row **atomically inside the lock**. The author's
   *act* (running `verify`) is preserved — which is what makes the declaration evidence —
   while the *prediction* is removed. This closes Class A entirely.
2. **Namespace subjects.** Already ruled: one bare `#N` namespace per ledger; a second
   board uses a descriptive stem or a separate `OC_LEDGER_PATH`. Closes Class B.
3. **Name the sequence race as designed.** §4 should say the re-claim is the **expected
   outcome** of two lanes' independent wake latencies, not a process violation. Closes
   the *reading* of Class C; the mechanism stays.
4. **Never author an identifier you have not been given.** Already law; Class D is
   compliance, not mechanism.

---

## 5. What this census got wrong

My first pass reported **3** count mismatches. It is **2**. The third — n=866, reading
`rows=761` — is **my own regex catching prose**: that row's detail *quotes* "n=761 …
declares rows=761" while discussing the rule. The gate's reader is **positional** (the
canonical trailer) and correctly ignores it.

A non-positional match on a row that discusses the rule will always find the rule's own
text. This is the same class as the log self-match recorded earlier today: **a count is
only as good as its predicate**, and mine overcounted by 50 %.
