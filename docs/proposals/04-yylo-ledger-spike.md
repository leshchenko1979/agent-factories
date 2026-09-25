# YYLO Ledger spike — cross-clone reconciliation

- Source checkout: `/tmp/yylo-ledger-spike`, commit `e5cb8604d1b6c3a78c60fb5b632caf3aa49c410a`
  (= remote HEAD at time of run).
- Installed package: `yylo-ledger 0.4.0` in `/tmp/yylo-ledger-venv`.
- Fixture: `/tmp/yylo-race-20260925`; no factory repository touched.
- Run: 2026-09-25 ~06:03–06:08Z, inside a `systemd-run --user --scope` unit
  (`MemoryMax=900M`), because the ops cgroup sat at 99.78 % of `MemoryHigh`.

## Correction to the earlier fixture

The first pass used a **non-bare** origin and pulled clone-to-clone. That exercises
ordinary Git merge and cannot produce a push race. This run uses a **bare** origin and
two independent clones, which is the topology a factory would actually run.

## Result 1 — disjoint tasks: PASS

Two clones each created one task, committed, and pushed concurrently.

| Step | Outcome |
|---|---|
| Concurrent push | B accepted; A **rejected loudly** — `remote rejected`, `rc=1` |
| Loser pulls | Clean `ort` merge, no conflict |
| `doctor` (both clones) | `{"ok": true, "failures": []}` |
| `cache rebuild` | `{"rebuilt_tasks": 4}` |
| Canonical parity A vs B | **identical** — 4 tasks, same ids, same bodies |

No silent loss, no divergence.

## Result 2 — same task, conflicting update: LOUD CONFLICT

Both clones updated the **same** task (`task_llbcF9`) to different states, committed,
and raced the push.

| Step | Outcome |
|---|---|
| Push race | A accepted; B **rejected loudly** (`rc=1`) |
| Loser pulls | **`CONFLICT (content)`** in **both** `.juno_task/tasks/…md` and `.juno_task/ledger/…ndjson`; `rc=1`; 2 unmerged files |
| `doctor` while conflicted | **`rc=5`**, names the cause precisely: `invalid YAML front matter` + `ledger has no canonical current task` |
| `list` while conflicted | **`rc=1`** — refuses to answer rather than answering wrongly |

This is the behaviour the grite spike could not find: the failure is **loud and
detected**, not a silent overwrite reported as success.

### Why a union merge driver cannot rescue it

The ledger is a **hash chain**. In the conflict above, both clones appended an event
carrying the *same* `previous_event_sha256` (`c601262b…`):

```
…/task_llbcF9/000001.ndjson
  A branch event: previous_event_sha256 = c601262b…  → after_sha256 8ee58d22…
  B branch event: previous_event_sha256 = c601262b…  → after_sha256 44165464…
```

Both are valid successors of one parent, so the chain **forks**. A line-union merge
would concatenate them into a chain with two competing children — not a repair.
`--strategy {keep-newer,keep-both}` exists on `merge`, but `merge` operates on
`.juno_task` **directories**, not on a Git merge conflict; there is no shipped
`.gitattributes` and no merge driver.

## Result 3 — resolution converges, but discards the loser's event

Documented semantics: *"If ledger/cache work is interrupted, canonical current state
wins and the next mutation/reconcile converges."* Verified:

| Step | Outcome |
|---|---|
| Resolve to origin's side, commit | `rc=0` |
| `reconcile --check` | `rc=0`, `{"changed_task_ids": [], "check": true}` |
| `reconcile` | `rc=0`, **no changes** |
| `doctor` | `{"ok": true, "failures": []}` |
| Push + pull back | Fast-forward; both clones **identical** |
| `history task_llbcF9` | **2 events** — the loser's event is **absent** |

So convergence is real and clean, and it is **canonical-wins**: the losing branch's
event is discarded rather than recorded as a superseded sibling. That is a defensible
model, but it means a conflicted write is lost work, not a retained branch — and it is
recoverable only from Git's own history, not from the ledger.

## Result 4 — `--expected-revision` is LOCAL, not cross-clone

The optimistic control exists and works **within one store**:

| Write | Result |
|---|---|
| Correct local revision | `rc=0`, accepted |
| Stale revision (bogus sha) | **`rc=1`** — `stale task revision … expected deadbeef…, current c90cfbe…` |
| **No revision** | `rc=0`, accepted — blind write |

But it compares against **local** state only. In clone B, whose local state was behind
origin:

| Write in B | Result |
|---|---|
| with **B's own** (stale vs origin) revision | **`rc=0` — accepted** |
| with **origin's** revision | `rc=1` — refused, because B's *local* state differs |

**It is a single-worktree lock, not a distributed one.** It prevents lost updates
between concurrent writers sharing one store (the 5 s `JUNO_KANBAN_LOCK_TIMEOUT_SECONDS`
lock), and does nothing about two clones racing a push. So it is **not** a mitigation
for the Result 2 conflict.

## Result 5 — resource cost

| Measure | Value |
|---|---|
| One CLI call | **28.9 MB max RSS**, 0.51 s wall |
| Canonical bytes per task | ~2.6 KB (ledger 7 842 B + task md 2 683 B for 4 tasks) |
| Bare origin | 620 KB; 63 loose objects, 252 KiB, `size-pack: 0` |
| Cache (disposable) | 164 KB of the 248 KB `.juno_task` |

Comparable to the current JSONL ledger (~2.0 KB/row) and **far** below grite
(~32 KiB/event). The 28.9 MB per-call RSS is the notable cost: every write is a
Python process, where the current ledger's writes are a shell append.

## Requirement comparison

| Requirement | Result | Predicate and scope |
|---|---|---|
| Append-only canonical history | PASS | Immutable per-task `.md` + hash-chained per-task `.ndjson`; Git commits are the authority |
| Deterministic replay / cache rebuild | PASS | `cache rebuild` reproduced identical `list -f json` in the fixture |
| Single-worktree concurrent writers | PASS | 4 concurrent `create` exited 0; `doctor` OK |
| **Independent clone synchronization** | **PASS** | Bare origin, 2 clones, disjoint tasks: loud rejection, clean merge, identical final state |
| **Cross-clone conflicting writes** | **PASS — loud conflict** | Same task, conflicting values: `CONFLICT` on both files, `doctor rc=5`, `list rc=1`; converges canonical-wins |
| **Distributed optimistic control** | **ABSENT** | `--expected-revision` compares LOCAL state only; accepted a write that was stale against origin |
| Merge driver / union semantics | **ABSENT** | No `.gitattributes`, no driver; hash-chain fork is not union-mergeable |
| Existing JSONL reader/gate compatibility | **FAIL / migration** | Different storage, vocabulary and identity model; 44 readers and 50 gates cannot consume it unchanged |
| Board identity / event vocabulary | **FAIL / migration** | YYLO task IDs + statuses ≠ factory event/actor/subject vocabulary; multi-board collision untested |
| Resource cost at factory scale | PARTIAL | Measured at 4 tasks; no 981-row equivalent benchmark |

## Recommendation

**Do not migrate the factory ledger.** YYLO is a genuine improvement on grite — its
failures are loud, its cache is disposable and provably rebuildable, and its per-record
cost is comparable to ours — but it does not remove the migration burden, and it lacks
the distributed concurrency control that a multi-lane, multi-clone ledger needs:

- conflicting cross-clone writes are a **Git conflict requiring manual resolution**;
- the ledger hash chain **forks** and cannot be union-merged;
- the optimistic guard is **local-only**;
- resolution is **canonical-wins**, discarding the losing event from the ledger.

Its documented seven-day acceptance explicitly requires `mutation_conflicts` and
`worktree_merges` evidence artifacts — i.e. upstream considers these properties
**unproven**, and does not ship the receipts.

Retain `evidence/ledger.jsonl`. The factory's ledger is written by many lanes into one
tracked file; that is an **ownership problem**, and YYLO solves a different one.

## Limitations

Not tested: scale beyond 4 tasks; the `merge`/`archive-pack`/`host` command families;
`compatibility` acceptance flow; multi-actor identity (single actor used throughout);
repeated races beyond two clones; behaviour under the 5 s lock timeout at factory
concurrency. Host note: no Rust toolchain (box law) — this is the Python package, run
`--no-daemon` equivalent throughout.
