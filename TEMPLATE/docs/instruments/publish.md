# The pusher

**Owns:** the pusher's own law — its twelve statuses, its exit codes, its receipt, its grace
window, and the waiting primitive. It owns **no** cross-instrument definition; those live in
`template-instruments.md`, the frame, which this file cites and never restates.
**Writer:** the Worker lane. **Authority:** **HQ retains cross-factory authority** — any clause
here that binds a member factory is HQ's, and so is the process law *about* instruments.
**Does not own, by role:** the landing law itself. *"Landing work: the pusher, never a raw
push"* keeps its single home in `skills/meta-factory/SKILL.md` §4; this file **cites** it and
states only what is true of the executable.

**Why a home was owed (issue #482).** The pusher reports twelve statuses and exits with two
different contracts depending on how it was called, and neither was written down anywhere. A
caller that looped on the exit code therefore could not tell "the round ran" from "the round
refused" — and one status, `not-on-branch`, was actively dishonest about which it was. The law
lived in a docstring, which is to say it lived nowhere a caller reads.

## 1. What the pusher is

**Its job, in one sentence: publish this checkout's own commits to `origin`, after a grace
window, by fast-forward only — never forcing and never rewriting published history.**

It exists because nothing else guaranteed a commit reached `origin`. Publication happened only
when some lane happened to push as its own last step, so a turn killed after committing but
before pushing left work no surface could see and nothing would re-publish. Origin: issue #146,
ruled at ledger `n=1168`.

The executable is `tools/publish.py`, shipped as a byte-gated pair with
`TEMPLATE/tools/publish.py`.

## 2. The fourteen statuses

A round always ends in exactly one of these. `held` is the **only** status that can become
publishable by waiting — every other terminal status is a verdict the caller must act on.

| status | what it means | a caller may wait for it |
|---|---|---|
| `published` | the push landed; the receipt records the pushed sha | it is the goal |
| `in-sync` | HEAD is level with the remote tip; nothing of this checkout's is unpushed | it is the goal |
| `held` | the newest unpushed commit is younger than the grace window, so it stays LOCAL | **yes — the only one** |
| `behind` | HEAD is a PURE ANCESTOR of the tip: a stale checkout with nothing of its own | no |
| `diverged` | the branch is not an ancestor of HEAD; reported, never resolved | no |
| `ff-blocked` | the sync could fast-forward, but local edits sit on paths it would overwrite | no |
| `not-on-branch` | HEAD is detached and on **neither end** of the configured branch's line | no |
| `unbound-repo` | **STARTUP refusal** (#525): no `--repo` was passed and the tree this copy of the tool sits in is not a git work tree — the shape of a copy fetched to `/tmp`, whose derived root is `/`. The round stops before it asks the remote anything, so this is **not** a verdict about any repository | no |
| `no-remote` | the configured remote is not configured in this repository | no |
| `unreachable` | the remote could not be asked (fetch or `ls-remote` failed) | no |
| `unreadable` | the unpushed-commit log could not be read | no |
| `push-failed` | the push itself was refused | no |
| `would-publish` | a report-only round found work it *would* publish; it publishes nothing | no |
| `already-published` | the push was rejected because another pusher landed the same commit first — the remote **carries** it. No receipt is written: this round pushed nothing | it is the goal |

`behind` and `diverged` are **reports the round was asked to make**, not failures: a mere
ancestor is the normal steady state for a checkout that is not the one advancing `origin/main`,
and reddening it would red the steady state (#418). A genuine divergence refuses loudly and
publishes nothing.

**`would-publish` cannot occur under an applying round** — it is the report-only answer, and
`--wait` implies `--apply`.

**`already-published` is a SUCCESS, not a failure** (#518, ruling n=3841). Two pushers
sharing one remote is the declared design (#284: the grace window binds the pusher, nothing
else), so a `git push` rejected with *"cannot lock ref … is at X but expected Y"* is a **ref
race**: the loser is not wrong about the remote, it was wrong about what a rejection means.
The round therefore asks the only question that settles it — *does the remote tip **contain**
the commit I was publishing?* (`git merge-base --is-ancestor`) — rather than trusting the
rejection. **Containment, never equality**: a remote that advanced *past* our commit also
carries our work, and an equality test would call that a failure. The server's message is
preserved in `reason`, so the race stays visible; it just stops being a verdict.

## 3. The exit codes

Two contracts, because a report and a wait are different questions.

| invocation | exit 0 | exit 1 |
|---|---|---|
| `python3 tools/publish.py [--apply]` | the round RAN — `published`, `already-published`, `held`, `in-sync`, `behind`, `diverged`, `would-publish` | the round could not be completed — `unbound-repo`, `no-remote`, `not-on-branch`, `unreachable`, `unreadable`, `push-failed`, `ff-blocked` |
| `python3 tools/publish.py --wait` | **only** `published`, `in-sync` and `already-published` | **every** other status |

**`not-on-branch` was the defect (issue #482, order 2).** It exited 0 beside the refusals above
while being a refusal like them, so an rc-only caller could not distinguish it from a round that
ran — and a caller that waits loops forever on a state that will never change. It now exits 1.
`behind` and `diverged` deliberately **stay at 0** on the plain path, because they are reports;
a waiting caller refuses them through the waitable set instead.

**`unbound-repo` is the STARTUP refusal (#525, ruling n=3895 item 1), and it is not
`no-remote`.** The tool derives its repo root from its own `__file__`, which is correct for the
copy that lives in the tree and wrong for every copy that does not: a copy fetched to `/tmp`
derives `/`, and the old default sent it on to ask whether `origin` was configured *in `/`* and
answer `no-remote` — a verdict about a repository, emitted about a tree the invocation never
chose. So where `--repo` is absent **and** the derived tree is not a git work tree, the round
stops at startup with a status that names the flag it needs. `--repo` supplied is never
second-guessed: the caller chose a tree, so that tree's answer is a verdict about it.

## 4. The waiting primitive

`--wait` implies `--apply`: a caller that asked to block until publication cannot be asking for
a report-only round. It polls until the round publishes, or until a status that cannot.

- It loops on **`held` alone**, then returns. A terminal status stops the wait immediately
  rather than polling to the timeout, because polling to a timeout reports a window that expired
  instead of a state that was never going to change.
- `--timeout N` bounds the block. The default is **derived, not guessed**: the grace window plus
  a margin (`DEFAULT_GRACE_SECS` + `WAIT_TIMEOUT_MARGIN_SECS` = 1200 s), because the harness's own
  run-lifetime budget is not readable from this repository and the tool runs as a subprocess with
  no view of the agent's config.
- **Every poll prints one machine-readable line**, so a caller parses a record rather than prose:

```
status=<s> held=<n> age=<secs> tip=<sha> reason=<text>
```

With `--json` the poll lines go to **stderr**, so stdout stays one JSON document.

## 5. The receipt

The pusher records its own last push as `{sha, instant, remote, branch}` at
`<git-common-dir>/publish-receipt.json` — in a worktree, the **shared** git directory, so a push
from any worktree of the checkout is readable by every other. It is deliberately **local and
gitignored**: it is a record of this checkout's own act, not a fact about the remote.

The pre-#445 placement — `evidence/publish-receipt.json`, checkout-local — is **legacy** and is
removed by a publishing round that finds it (#452). Nothing creates it any more.

**A stale pusher copy is a real hazard, and it is why the landing route names a checkout at
`origin/main`.** A copy predating #445 writes the legacy path, so a *compliant* push made from a
real worktree by that copy leaves the receipt the patrol reads untouched — and the patrol then
names a compliant round a raw push. The route clause in a cron envelope must therefore name a
checkout sitting at `origin/main`, never a shared tree that lanes advance past (issue #480).

## 6. The grace window

A commit younger than `DEFAULT_GRACE_SECS` (900 s) stays LOCAL, and the window is tested on the
**newest** unpushed commit — a fast-forward push publishes everything up to the tip, so testing
the oldest would publish a younger commit sitting above it.

The window exists because a pusher without one manufactures the published-then-amended
divergence this factory already paid for once: a commit pushed mid-edit and then amended has
rewritten PUBLISHED history. `status:"held"` inside the window is therefore **the pusher
working**, not failing — a caller retries, and never falls back to a raw push.

## 7. What this file does not supply

This is the pusher's **status and contract law**. It is **not yet a declared instrument** under
the frame's nine parts: it supplies no version identifier, no data-surface split, no self-probe,
no adoption census and no update path. Those are owed if the pusher is to be adopted as one, and
the frame — not this file — defines what each would require.
