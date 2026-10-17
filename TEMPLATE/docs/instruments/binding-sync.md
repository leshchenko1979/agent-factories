# The binding sync

**Owns:** the sync's own law — its three outcomes, its exit codes, its receipt, and the one
move it may make. It owns **no** cross-instrument definition; those live in
`template-instruments.md`, the frame, which this file cites and never restates.
**Writer:** the Worker lane. **Authority:** **HQ retains cross-factory authority** — any clause
here that binds a member factory is HQ's, and so is the process law *about* instruments.

**Why a home was owed (issue #503, ordered by the ruling on #502).** The tree that serves a
profile's law binding is a SHARED WORKING TREE: nothing fetches into it and nothing checks it
out, so its currency was owned by nobody. Measured 2026-10-17T00:58Z on `/root/agent-factories`:
HEAD `a0ba409b` against `origin/main` `65d954fe`, the loaded `state.md` at `8d354b69d8ac`
against `a93fe1d4600f`, and its own `evidence/ledger.jsonl` at 2657 rows against 3469. Two
crons resolve their `REPO` from `__file__`, so both computed against a stale ledger — and
nothing measured it, because the freshness arm only compares what the patrol can see.

## 1. What the sync is

**Its job, in one sentence: bring the tree that serves a law binding to `origin/main`, and
REFUSE — changing nothing — when that tree carries work `origin/main` does not have.**

The refusal is not a limitation; it is the product. The hand reconciliation of 2026-10-17 was
safe because a human read the 192 displaced paths first. A cron that reset automatically would
have destroyed them silently, which is strictly worse than staying stale: a stale tree computes
old numbers, and a destroyed tree loses a lane's only copy of its work.

The executable is `tools/sync_binding.py`, shipped as a byte-gated pair with
`TEMPLATE/tools/sync_binding.py`. Its gate is `tests/test_binding_sync.py`, paired for the same
reason and REQUIRED in `gate_registry.REQUIRED_GATES`.

## 2. The three outcomes

A run always ends in exactly one of these. There is no fourth and no partial move.

| outcome | exit | what it means |
|---|---|---|
| `level` | 0 | HEAD equals the remote tip, read from the REMOTE this round. Nothing to do. |
| `fast-forward` | 0 | the tree is CLEAN and BEHIND: no local-only commit, no path differing from HEAD, and `origin/main` strictly ahead. `--apply` moves it with `git merge --ff-only`. |
| `refuse` | 3 | the tree carries work not in `origin/main`. **Nothing is changed**, and every reason found is named. |

`2` is the fourth exit and not an outcome: the tree could not be read at all (not a git
repository, or `HEAD`/the remote tip unresolvable). A broken read is never a clean one.

**`--ff-only` is the ONLY move this tool may make.** It is not a flag a caller can widen:
there is no `--reset`, no `--force`, and no `--hard` in the argument parser, so the destructive
sync cannot be requested, only implemented — and implementing it would fail this file's own
gate, whose third leg asserts that a refused run leaves HEAD exactly where it was.

## 3. What counts as work

Five conditions, each of which alone forces `refuse`:

- **a local-only commit** — anything in `origin/main..HEAD`. Named by sha, up to eight of them.
- **a path differing from HEAD** — `git status --porcelain`, which includes STAGED, UNSTAGED
  and UNTRACKED. Untracked counts on purpose: a lane's scratch file is that lane's work, and a
  fast-forward over a dirty tree either aborts halfway or silently carries the file forward.
- **HEAD not on `main`** — a detached HEAD is not a tree this tool can move lawfully.
- **a divergence** — HEAD differs from the remote tip but is neither behind nor ahead. Not a
  shape to guess at, so it is refused rather than classified.
- **stale loaded bytes** — a tracked file under a declared `repo_path` whose ON-DISK content
  does not hash to the blob the remote tip records. This is a condition of its own because
  `HEAD == origin/main` says the COMMIT is level, never that the working tree holds its
  content: a file restored from a backup, an `assume-unchanged` bit or a sparse checkout
  leaves a tree that every git command calls current while the bound law loads old text —
  which is precisely the state the issue measured (`state.md` at `8d354b69d8ac` under a tree
  whose git commands reported currency). The comparison is `git hash-object` of the file
  against `git ls-tree` of the tip, so no file content is read into the process, and a path
  the tip records but the tree no longer has counts as stale too. A SYMLINK is compared as
  a LINK — its blob at the tip is the target string, not the bytes it resolves to — because
  hashing through it would report every correct link as stale (measured on this tree: 8 of
  11 bound files, all symlinked instrument docs, on a level HEAD).

**The bound, stated not hidden.** The tool cannot tell a lane's abandoned work from a lane's
work in flight; both read as `refuse`. That is deliberate — the cron reports the paths and a
human or a lane decides. It also does not decide whether the declaration still names this
repository: it reports the binding rows it resolved and prints `NOT RUN` with its reason when
none resolves, so an unbound tree is VISIBLE rather than clean.

## 4. How it decides whether it is the tree that serves a binding

It reads `docs/harness-bindings.json` — the declaration `tests/test_harness_bindings.py` reads,
never a derivation over the repo's own `skills/` directory — and asks, per row, whether the
profile entry `~/.opencrabs/profiles/<profile>/skills/<skill>` is a symlink whose REALPATH lands
inside this tree. The schema is `profile` + `skill` + `repo_path`; there is no absolute path in
it, so a reader keyed on one would report `NOT RUN` on a correct declaration and its verdict
would be indistinguishable from a tree that declares nothing.

A row carrying `loaded: false` declares a law deliberately NOT bound. It is skipped: it is a
statement of intent, never a load path that could be stale.

## 5. The receipt

`<git-common-dir>/binding-sync-receipt.json` — `{read_at, repo, binding_rows, before, after,
remote_tip, behind, local_only, dirty, action, reasons, move, applied}`.

**Why a file and not a ledger row.** `pacemaker.md` names the duty receipt as a `run` row
written by the WOKEN LANE, and the ledger's actor set is closed and derived from a lane's own
session. This job does not wake a lane: it runs on a clock and needs no judgement, so there is
no lane to derive an actor from. The file shape is the one `publish.py` uses, for the same two
reasons: a receipt that rode the pushed history would move the remote tip PAST the sha it
records, and a receipt written INSIDE the tree would make the tree dirty — which is the one
condition this tool refuses on. It sits in the COMMON dir so every worktree of the repository
reads ONE record, and it records the checkout that wrote it.

## 6. The cron

`factory-binding-sync`, every six hours, trigger-gated on `exit_non_zero`:

```
python3 /root/agent-factories/tools/sync_binding.py --apply
```

A `level` or `fast-forward` run exits 0 and the job short-circuits at zero tokens. A `refuse`
exits 3 and the job fires a thin wake that reads the receipt and reports the named paths. The
prompt declares `receipt_subject: none`, because the receipt is the JSON file above and never a
ledger row.

**What upholds it.** `tests/test_binding_sync.py` proves the TOOL — every branch of the
predicate on a synthetic facts dict, then all three outcomes through `main()` on a real
repository under a temp directory, with the discriminating pair (the same facts minus
`local_only` must flip to `fast-forward`) so a predicate that refused everything cannot pass.
It does NOT prove the cron: the job lives in the harness `cron_jobs` table, and a suite that
read that table would RED in every bootstrapped factory that has no such table. The cron's
existence is a dispatch criterion verified at landing time, not a tree property.
