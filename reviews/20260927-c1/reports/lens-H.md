# Lens H — Ledger Invariants & Monotonicity

**Revision audited:** `git -C /root/agent-factories rev-parse HEAD` → `e679687c683ed56d4a4de9ecf43495366b0508ae`
**Corpus mapped to:** `evidence/ledger.jsonl` (2248 rows, 4 597 791 bytes) per `CORPUS.md` row *H*.
**Law read:** `docs/review-lenses.md` §Lens H (`:110-121`), `tools/review.py:170-179` (the brief generator),
`docs/instruments/ledger.md` (the instrument's own law), `docs/best-practices.md:620`,
`docs/measurement-procedure.md:167,195`, `tools/ledger.py` (`append`/`verify`/`repair`), `tests/test_ledger_schema.py`.
**Method:** `python3` parse of every row (`json.loads`), integer/timestamp scans, per-subject event indexing, the
union authorization matrix, and `python3 tools/ledger.py verify` (read-only, rc=0).

---

## Finding 1 — SEVERE: timestamp ordering is non-monotonic, and no mechanism detects it

### 1a. The ledger violates the mandated invariant

**File Locators / verbatim quotes** (`evidence/ledger.jsonl`; row `n` is at line `n`, verified with `sed -n '<n>p'`):

- `evidence/ledger.jsonl:1624`
  `{"n": 1624, "ts": "2026-09-29T07:08:05Z", "event": "run", "actor": "worker", "subject": "#219", …`
- `evidence/ledger.jsonl:1625`
  `{"n": 1625, "ts": "2026-09-29T06:50:46Z", "event": "intake", "actor": "triage", "subject": "#230", …`
- `evidence/ledger.jsonl:1851`
  `{"n": 1851, "ts": "2026-10-01T08:28:44Z", "event": "dispatch", "actor": "hq", "subject": "#162", …`
- `evidence/ledger.jsonl:1852`
  `{"n": 1852, "ts": "2026-10-01T07:30:35Z", "event": "claim", "actor": "ledger", "subject": "#258", …`
- `evidence/ledger.jsonl:2147`
  `{"n": 2147, "ts": "2026-10-03T23:10:00Z", "event": "claim", "actor": "insights", "subject": "#300", …`
- `evidence/ledger.jsonl:2148`
  `{"n": 2148, "ts": "2026-10-03T22:52:01Z", "event": "run", "actor": "ledger", "subject": "#298", …`

**Defect analysis.** The Lens H law requires this exact check:

> `docs/review-lenses.md:117` — `  2. **Sequence Monotonicity:** Confirm integer sequence numbers ($n=1, 2, \dots$) and monotonically advancing timestamps.`

and the brief generator repeats it verbatim: `tools/review.py:174` — `"1. Verify strict monotonic row numbering and timestamp ordering.\n"`.

Measured on the live file: **`n` is strictly monotonic and gap-free (`1..2248`, 2248 distinct values) but the
timestamps are not.** Three adjacent inversions (`ts[i] < ts[i-1]`) were read directly:

| inversion | row n | ts | successor n | ts |
|---|---|---|---|---|
| 1 | 1624 | `2026-09-29T07:08:05Z` | 1625 | `2026-09-29T06:50:46Z` |
| 2 | 1851 | `2026-10-01T08:28:44Z` | 1852 | `2026-10-01T07:30:35Z` |
| 3 | 2147 | `2026-10-03T23:10:00Z` | 2148 | `2026-10-03T22:52:01Z` |

Sorting the file by `ts` and comparing to row order, **13 rows sit out of timestamp order**
(clusters at `n=1623-1626`, `1846-1852`, `2147-2148`). So the file's row order and its time order are two
different orders, and the ledger does not say so anywhere.

### 1b. The inversions cannot come from the append path — they are residue of a second writer

**File Locators / verbatim quotes:**

- `tools/ledger.py:1604-1611` (the only row-build site):
  `        row = {`
  `            "n": (rows[-1]["n"] + 1) if rows else 1,`
  `            "ts": now_iso(),`
- `tools/ledger.py:561` — `    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`
- `tools/ledger.py:2518-2527` — the `append` argparse block, which defines only `--event`, `--subject`,
  `--detail`, `--subprocess`, `--ref`: **there is no `--ts` option.**

**Defect analysis.** `ts` is stamped by `now_iso()` *at the instant of append* and cannot be supplied by the
caller. Therefore a row whose `ts` is earlier than its predecessor's **cannot have been produced by `append`
in that position**. The three inversions are positive evidence that these rows entered the file by a path
*other than the append lock* — a rebase/re-mint that carried the row's original bytes (and original `ts`)
forward. This is exactly the "wrong remedy" the single-writer law claims is caught:

> `docs/instruments/ledger.md:779` — ``| `verify`'s monotonic-`n` loop | the residue a WRONG remedy leaves — two rows carrying one `n` — is caught on the committed file | `tools/ledger.py verify` |``

That layer is blind to this failure: `verify` checks `n`, not `ts` (see Finding 1c). The re-mint protocol at
`docs/instruments/ledger.md:692-798` ("The unpublished sibling re-appends at the next free `n`") is silent on
what happens to `ts`, and the three observed instances show what happens: it is preserved, and the ordering
inverts. Concretely, git archaeology confirms the mechanism — commit `8cb5ebb` (2026-10-01T07:57:07Z) first
introduced the `#258` claim as `n=1846`; the row now stands at `n=1852` carrying its original `ts`
`07:30:35Z`, behind rows stamped `07:32:54Z … 08:28:44Z` (`n=1846-1851`). The row was re-minted; its `ts` was not.

### 1c. `verify` prints an unqualified "monotonic" that a reader takes to cover timestamps

**File Locator / verbatim quote:** `tools/ledger.py:2230`

```
        print(f"ledger clean: {len(rows)} row(s), monotonic, all event types known, sequences complete")
```

**Defect analysis.** On the live file this prints `ledger clean: 2248 row(s), monotonic, all event types known,
sequences complete` (rc=0). The word **`monotonic` is unqualified and applies only to `n`.** A reader running
the mandated Lens H check — or the law's own quote of this line at `docs/instruments/ledger.md:602`
(`*"ledger clean: 590 row(s), monotonic, all event types known, sequences …"*`) — has no way to learn that the
timestamps are *not* monotonic, because nothing on the surface says which quantity the word describes. The
schema gate likewise validates only the timestamp **format**, never its order:
`tests/test_ledger_schema.py:169` checks `n_val != line_num`; `tests/test_ledger_schema.py:171` checks
`ISO_TIMESTAMP_RE.match(ts_val)` and nothing else. A grep for any timestamp-ordering assertion across
`tests/test_ledger*.py` returns none.

**Actionable remediation.**
1. Add a `ts`-ordering leg to `tools/ledger.py::cmd_verify` (and a paired arm in `tests/test_ledger.py`):
   for history, **report** every `ts[i] < ts[i-1]` as `line N: timestamp inversion (ts < predecessor)` beside the
   existing `multiple closes:` reports; for the write path, refuse an `append` whose computed `now_iso()` is
   `< rows[-1]["ts"]` (cheap, and turns a silent inversion into a refusal).
2. Reword `tools/ledger.py:2230` to `… row(s), n monotonic, …` (or `… monotonic n …`) so the claim matches what
   is checked. Update the quoted copy at `docs/instruments/ledger.md:602` in the same commit.
3. Record the three live inversions (`n=1625`, `n=1852`, `n=2148`) as named visible debt in
   `docs/instruments/ledger.md §9.1`, the way the malformed-dispatch population is already named — the rows are
   immutable, so the only lawful repair is disclosure plus a forward gate.

---

## Finding 2 — HIGH: duplicate close/claim rows leave the ledger unable to answer "closed once or twice?"

**File Locators / verbatim quotes** (`evidence/ledger.jsonl`):

- `:930` — `{"n": 930, "ts": "2026-09-22T12:24:13Z", "event": "close", "actor": "worker", "subject": "#140", …`
  and `:931` — `{"n": 931, "ts": "2026-09-22T12:25:10Z", "event": "close", "actor": "worker", "subject": "#140", …`
- `:1361` / `:1363` — two `close` rows for `#169`, both `actor":"worker"`.
- `:1502` / `:1504` — two `close` rows for `#202`, both `actor":"hq"`.
- `:1509` / `:1511` — two `close` rows for `#84`, both `actor":"hq"`.

**Defect analysis.** Lens H check 3 asks to "Detect conflicting event records or duplicate task identifiers"
(`docs/review-lenses.md:118`). Measured: **6 subjects carry two `close` rows** and **8 subjects carry two
`claim` rows**. Four of the close pairs (`#140`, `#169`, `#202`, `#84`) are same-actor pairs 1–3 minutes apart
whose `detail` differs *only* in the telemetry trailer (`#140`: `turns=45 duration=9424s` vs `turns=49
duration=9483s`), i.e. the exact shape the write path now refuses as a retry-duplicate. The tool sees them and
says so, but cannot resolve them:

```
  multiple closes: #140 carries 2 close rows (n=930, n=931), and 1 of them declare no `reclose=` reason — either a deliberate re-close that did not declare itself, or a DUPLICATE minted by retrying an append that had already completed (#213). A second close declaring no `reclose=` is now refused at the write path; this reading is of history, whose rows are immutable
```

The consequence is not cosmetic: `#140` has no single "close" event, so any consumer that counts `close` rows
for a subject (rather than distinct closed subjects) double-counts it, and the ledger itself cannot distinguish
"deliberate re-close" from "duplicate append" — the ambiguity is the finding. The same holds for the 4
same-actor duplicate claims (`#113`, `#161`, `#220`, `#26`).

**Actionable remediation.** These are immutable historical rows, so the repair is disclosure, not deletion:
1. Extend `docs/ledger-exemptions.json` (or a sibling `reclose`/`reclaim` reconciliation list) to carry one
   entry per unresolved pair naming which of the two rows is canonical — an explicit "this is a duplicate" or
   "this is a deliberate re-close", with a proof, so the population stops reading as an open question on every
   run.
2. Have `verify` print the *disposition* beside each pair (`resolved:` / `unresolved:`) so the reader can tell a
   reconciled pair from one nobody has looked at.

---

## Finding 3 — MEDIUM: the documented lock path is not the lock the write path takes

**File Locators / verbatim quotes:**

- `tools/ledger.py:324` — `LOCK = _git_common_dir() / "opencrabs-ledger.lock"` (with `_git_common_dir()` at
  `tools/ledger.py:285-313` returning the **common git dir**).
- `docs/instruments/hygiene.md:217` — ``**track** — `evidence/.ledger.lock`, `evidence/.insights.lock`, the derived `evidence/.ledger-index.sqlite` — and a``
- `tools/hygiene.py:786` — ``writes and gitignores (`evidence/.insights.lock`, `evidence/.ledger.lock`,``

**Defect analysis.** The live lock is `.git/opencrabs-ledger.lock` (confirmed present, 0 bytes, 2026-10-04T20:52Z);
the file `evidence/.ledger.lock` **exists in the working tree** (0 bytes, 2026-09-29T01:34Z) and is the path the
law and the hygiene instrument name as the lock surface — but the write path never touches it. It is only the
path a *fixture* uses (`tests/test_ledger_schema.py:822`: `ledger.LOCK = ledger_path.parent / ".ledger.lock"`).
So a reader auditing "single-writer locking compliance" (Lens H check 3) by looking for the lock where the law
says it is inspects a **decoy**: the mechanism that actually serialises writers is invisible to any working-tree
listing, and the stale `evidence/.ledger.lock` suggests a lock that no live write takes. Combined with
Findings 1a-1b — where rows demonstrably entered out of append order, i.e. through a git operation the lock
does not guard — the "single-writer is a mechanism" claim holds only for writers that reach the *same* tool on
the *same* file, and the docstring does not say the lock's location is different from the documented one.

**Actionable remediation.** Correct `docs/instruments/hygiene.md:217` and `tools/hygiene.py:786` to name
`.git/opencrabs-ledger.lock` (the common-dir lock) as the live single-writer surface, and state explicitly that
`evidence/.ledger.lock` is a fixture path. Delete the stale `evidence/.ledger.lock` from the working tree, or
document why it is retained.

---

## Finding 4 — MEDIUM: the timestamp invariant exists in one law file and was dropped from its summary, with no gate in either place (P29)

**File Locators / verbatim quotes:**

- `docs/review-lenses.md:117` (kept) — `  2. **Sequence Monotonicity:** Confirm integer sequence numbers ($n=1, 2, \dots$) and monotonically advancing timestamps.`
- `docs/best-practices.md:620` (dropped) — ``   - **Ledger Invariants & Monotonicity:** Audit lifecycle sequences (`intake` → `claim` → `close`), verify monotonic numbering, and detect unresolved claims or phantom citations.``

**Defect analysis.** The catalogue's Lens H names **two** ordering properties (`n` **and** timestamps); the
best-practices summary of the same lens keeps only `verify monotonic numbering`. The invariant is therefore
stated in one place, weakened in a second, and implemented in **neither** — no gate reads `ts` order (Finding
1c). A rule that lives only in prose and is contradicted by the prose next to it is precisely the class the
factory's own P29 ("an assertion with no mechanism") names; the drift is already visible in two files, and the
measured violations (Finding 1a) show the gap is not theoretical.

**Actionable remediation.** Make the two summaries agree on the *full* invariant, and back it with the gate
proposed in Finding 1c so the check is mechanical rather than restated. If timestamps are deliberately
*not* required to be monotonic (a defensible position, given re-mints preserve `ts`), then delete the clause
from `docs/review-lenses.md:117` and `tools/review.py:174` and say so — an unenforced invariant that the
ledger violates is worse than no invariant.

---

## Surfaces checked and found clean (with method)

To be explicit that this is not an empty pass — these were measured, not assumed:

- **Row numbering.** `n` is strictly increasing with no gaps and no repeats: 2248 parsed rows,
  `set(ns)` size 2248, `all(b>a for a,b in zip(ns,ns[1:]))` → `True`, first `n=1`, last `n=2248`. Every `ts` is
  canonical `YYYY-MM-DDTHH:MM:SSZ` (0 of 2248 malformed).
- **Lifecycle sequence.** Closes lacking a prior intake (positional): `{n=7}`; closes lacking a prior claim
  (positional): `{n=3, n=7}`; claims lacking an intake *anywhere*: **0**. Both violations are lawfully excused
  by `docs/ledger-exemptions.json` with proof (the `#6`/`#8` pre-gate closes, proofs naming ledger `n=14`/`n=15`),
  so `verify` reports them as `excused:`, never as problems. 5 claims carry an intake *after* them
  (`n=479,673,1053,1081,1159`) — lawful under the claim leg's "anywhere" rule (`tools/ledger.py:906-908`, `intakes = [j for j, ev in legs if ev == "intake"]`).
- **Actor attribution.** Every row's `(event, actor)` is inside the union of the core matrix
  (`tools/ledger_declaration.py:80-89`) and the declared `by_event` lanes (`docs/ledger-authorizations.json`):
  **0 of 2248 rows outside**. Each declared lane's first row postdates its declaration (`hygiene` first at
  `n=2018` vs the `#283` ruling at `n=2008`; `insights` first at `n=1538` vs the `#209` ruling at `n=1527`).
- **Refs.** `verify` (rc=0) examined every `refs` entry; no dangling `row:` ref and no undeclared kind.
- **`session` key.** Absent on 1830 rows and present on all 418 rows at/after `n=1831` — consistent with the
  key's introduction at `#256` (`n=1831-1833`) and the law's forward-only stance; the omission on earlier rows is
  pre-feature, not a defect.

---

## Summary

**4 findings** (1 severe, 1 high, 2 medium). The single most severe is **Finding 1**: the live ledger is *not*
timestamp-monotonic — three adjacent inversions (`n=1625`, `n=1852`, `n=2148`) and 13 rows out of `ts` order —
which violates the Lens H law at `docs/review-lenses.md:117` and the brief at `tools/review.py:174`, is invisible
to every gate, and is actively masked by the unqualified word `monotonic` in `verify`'s clean line
(`tools/ledger.py:2230`); because `append` stamps `ts` via `now_iso()` with no `--ts` flag
(`tools/ledger.py:1607`, parser at `:2518-2527`), those inversions also prove rows entered by a path the
single-writer lock does not guard. Measurements were produced by: `git -C /root/agent-factories rev-parse HEAD`;
a `python3 json.loads` pass over `evidence/ledger.jsonl` computing `n`-monotonicity, `ts`-inversion detection,
per-subject event indexing, duplicate-subject counts, the union `(event,actor)` matrix, and a `ts`-sort-vs-row-order
comparison; `python3 tools/ledger.py verify` (read-only, rc=0); `sed -n '<n>p' evidence/ledger.jsonl` for byte
receipts; `git show`/`git log -S` to trace the re-mint history of `n=1852`; and greps over `tools/`, `tests/`,
`docs/` confirming no gate reads `ts` order (`grep -rniE "monoton|ts.*(order|increas)"`).
