# PROPOSAL 03 — grite as a ledger substrate: export-fidelity spike

**Status:** finding, decision input (not law)
**Date:** 2026-09-24
**Subject:** can `grite` replace or host `evidence/ledger.jsonl`?
**Artifact under test:** grite **0.5.3**, x86_64-unknown-linux-gnu, released 2026-05-07,
`sha256 2627082f7687512c61f1bb7c3eee24642c5c63fca40c293ec39c83539ebb0773` (verified on download)
**Host:** ops box, git 2.43.0, glibc 2.39. No Rust toolchain (box law) — the prebuilt binary was
used; nothing was built. Every grite call ran with `--no-daemon`; heavy runs were wrapped in a
sibling `systemd-run --user --scope` so the ops cgroup (94 % of `MemoryHigh` at the time) was
never charged. Scratch tree: `/root/spike-grite-20260924/`.

---

## 1. The question

Prior review asked whether grite could give us two things we want and do not have: a **pristine
working tree** (our ledger is tracked, so it is perpetually dirty and lanes commit each other's
rows) and **conflict-free concurrent appends**. The spike's single question was:

> Is `grite export --format json` a **faithful render** of the store — lossless enough to serve as
> the read surface while the WAL stays the source of truth?

Answer: **the export is faithful in content; the substrate underneath it is not safe to build on.**

---

## 2. Export fidelity — verdict

Measured on two fixtures: 18 events covering all 10 documented kinds plus adversarial content,
and 300 events for scale/order.

### 2.1 Content: FAITHFUL (no defects found)

| Check | Result |
|---|---|
| Event count, WAL vs export | 18/18 and 300/300 — exact |
| `ts_unix_ms` mismatches (joined by `event_id`) | **0** |
| `actor` mismatches | **0** |
| `issue_id` mismatches | **0** |
| Kinds surviving | 10/10 documented, plus tag **11** (`DependencyAdded`) which the docs do not list |
| Unicode: Cyrillic, CJK, emoji, `✓` | byte-exact |
| Adversarial: backticks, `"quotes"`, `<angle>`, `\|pipe\|`, tabs, newlines | byte-exact |
| 20 000-char body | byte-exact |
| Determinism across runs | events identical **as sets and as lists**; only `meta.generated_ts` differs |

The export is a faithful content render. That part of the question is answered cleanly.

### 2.2 Losses and gaps

| # | Finding | Predicate |
|---|---|---|
| L1 | **`parent` and `sig` are dropped.** The WAL event is an 8-field CBOR array; the export carries 5 keys. | decoded WAL vs `export.json` keys |
| L2 | …but both are **always null** in practice, so today the loss is theoretical. Signing is opt-in and was off. | 0 non-null of 18, both fields |
| L3 | **The materialized `issues[]` has no `body`.** Body exists only inside `IssueCreated`. | issue keys: `assignees, comment_count, created_ts, issue_id, labels, state, title, updated_ts` |
| L4 | **Export order is not event order.** It is a stable but hash-like ordering — 0/300 positional agreement with the true chain; first six titles effectively random. | WAL parent chain vs export order |
| L5 | Order **is** recoverable — `sort by ts_unix_ms` reproduced the true chain exactly — but that holds **only while timestamps are unique**. | 300/300 distinct ts, min delta 45 ms |
| L6 | **No sequence number exists** on either surface. Our ledger's `n` has no counterpart. | field inspection |
| L7 | `export` writes `.grite/` **into the working tree**, untracked, **not gitignored**, and there is no `--out` flag. `git status` goes from clean to `?? .grite/`. | `git check-ignore .grite` → not ignored |
| L8 | The website advertises **CSV** export; the shipped CLI offers `json` and `md` only. | `grite export --help` |
| L9 | The export command's own output reports `wal_head: null`. | observed on every run |

**L7 matters most for our stated motive.** The reason to consider grite is that our ledger dirties
the tree — and `export`, the surface we would read it through, dirties the tree itself.

---

## 3. The finding that decides it: the CRDT merge does not work

The headline claim is *"CRDT-based merging — deterministic conflict resolution, no manual merge
needed … no edit is silently dropped."* Reproduced across **three** remote-refspec configurations,
two independent runs each, two clones, each writing two issues:

| Config | Pull behaviour | Push behaviour | Outcome |
|---|---|---|---|
| **A.** No WAL refspec (git default) | reports `"Already up to date"` — **false**, origin's WAL head is not local | `cannot push non-fastforwardable reference` | no merge, no loss, tool blind |
| **B.** Direct refspec — **what the docs prescribe** (`refs/grite/*:refs/grite/*`) | **force-overwrites the local WAL ref** | reports `Push successful` | **SILENT DATA LOSS, reported as success** |
| **C.** Tracking refspec (`+refs/grite/*:refs/remotes/origin/grite/*`) | does not touch the local WAL | `cannot push non-fastforwardable reference` | no merge, no loss, loud |

### Config B, verbatim

```
A writes 2 issues -> A WAL = 3 commits      B writes 2 issues -> B WAL = 3 commits
A sync:  ok=true  pulled=true pushed=true  pull_events=1  push_rebased=false  push_events_rebased=0
B sync:  ok=true  pulled=true pushed=true  pull_events=1  push_rebased=false  push_events_rebased=0
A sync:  ok=true  "Already up to date / Push successful"

FINAL: origin=1 commit   A=1 commit   B=1 commit      <- all four events gone
origin WAL titles: ['base']
A's own WAL commits: unreachable (dangling)
local store: still shows A-1, A-2 / B-1, B-2   <- store and WAL now disagree
```

Every step returned `ok: true`. The rebase that the docs' conflict-resolution algorithm describes
(*"create a new commit whose parent is the fetched head"*) never ran: `push_rebased: false` and
`push_events_rebased: 0` on all three calls. The pull had already discarded the local commits
before the push could reconcile them.

Reproduced with a **non-forced** refspec as well, so this is not an artifact of a `+` we added.

### What survives, precisely

- **Lost:** the events in the local WAL ref and on the remote. A fresh clone pulling afterwards
  receives only `base`.
- **Kept:** the local materialised store retains its own copy — which is why the loss is invisible
  locally and why the local view and the WAL disagree afterwards.
- `grite rebuild` reported `ok: true` and did **not** reconcile the two.

### The tooling does not see it

- `grite doctor --json` → `ok: true`, every check `ok`, on a clone that is permanently divergent.
- `grite doctor --fix` → `ok: true`, repairs nothing, push still refused.
- `grite sync --pull` → `"Already up to date"` on a clone missing the remote's WAL head.

There is **no merge/reconcile command**: `init, actor, issue, db, export, rebuild, sync, snapshot,
daemon, lock, doctor, context, install-skill`.

---

## 4. Concurrency — the second claimed win

| Parallel appends | Survived | Failures |
|---|---|---|
| 10 | **3 (30 %)** | 7 × `db_busy: Database locked by another process` |
| 3 | **1 (33 %)** | 2 × `db_busy` |

Failures are **loud**, not silent — the good half. But the local materialised-view lock serialises
writers hard, and there is no retry/backoff: two thirds of a burst is refused. `--lock` is offered
on `comment`/`close`/`label`/`assignee` but **not on `issue create`**, so the primary write path has
no locking option.

---

## 5. Operational notes

| Item | Measured |
|---|---|
| Cost per event | ~78 ms per `issue create` (300 sequential: 23.4 s) — one process + one git commit each |
| WAL size | **9.38 MiB for 300 events** (32 785 B/event = **32.0 KiB**, all loose objects, `size-pack: 0`). Our ledger: 2 045 900 B for 981 rows (2 086 B/row = **2.0 KiB**). Ratio **15.7×** larger per record |
| Export cost | 0.12 s, **14.4 MB max RSS** for 300 events — light, fits the cgroup budget |
| Export size | 194 KB json / 26 KB md for 300 events |
| `git clone` | does **not** carry `refs/grite/*`; needs an explicit refspec |
| `sync` to a non-bare local remote | fails: `local push doesn't (yet) support pushing to non-bare repos` |
| Working tree | pristine after normal operations; dirtied **only by `export`** |

---

## 6. Recommendation

**Do not adopt grite as the ledger substrate.** Not on export fidelity — that passed. On the
substrate: the merge path either loses data silently or cannot merge at all, and the configuration
that loses data silently is the one the project's own documentation prescribes.

Keep `evidence/ledger.jsonl` and the invariant layer (`verify`, the sequence predicates, the schema
and subject-form gates, 44 readers). The export question is now settled and does not need revisiting:
if grite were ever reconsidered, the export would be an acceptable read surface, with three caveats
— sort by `ts` yourself, treat order as unrecoverable once timestamps collide, and keep the local
store in sync manually.

**If the pristine-tree motive is what matters**, it is reachable without grite: our ledger is one
tracked JSONL file, and the pain is that every lane writes it. That is an ownership problem, not a
storage-format problem.

---

## 7. Not tested — stated so it is not assumed

- No Ed25519 signing was exercised, so L1/L2 could not be distinguished (field dropped vs null
  omitted). Signing fidelity is **unknown**.
- Only the `x86_64-unknown-linux-gnu` build of 0.5.3. The docs site may describe a newer version —
  0.5.3 is the newest release published (2026-05-07).
- The `grite-daemon` was never run; all results are `--no-daemon`. The daemon may change
  concurrency behaviour.
- Snapshots (`refs/grite/snapshots/*`) were not exercised.
- No large-repo scale test beyond 300 events.

## 8. Upstream

This is a third-party defect in a public repo (`neul-labs/grite`, MIT, 18★, last push 2026-07-02).
Nothing has been filed upstream — that is an owner decision, not a lane's. The reproduction is
self-contained and would take a maintainer minutes to run.
