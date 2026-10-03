# `tools/box/` — the landed box configuration

**Owns:** the versioned home of the host artefacts that RUN on this box but sit in no
member's tree. This directory is the first of its kind in this repo, so its contract is
written here rather than assumed.

## Why this directory exists

`oc_questions_push.sh` ran on every Open Questions mutation for months while being
**tracked in no repository**. `evidence/rework.md` recorded the debt in its own words
(entry dated 2026-09-29, for #207): *"it is TRACKED IN NO REPOSITORY, so it has no
history, no gate, and nothing in any tree would fail if it were removed; it is
unversioned box configuration whose mechanism runs on every push."* Landing the file is
what closes that half of the entry: it gains a history, and a diff of it is reviewable
and revertible.

## The artefacts

| landed path | live path (what actually runs) | sha256 of the landed bytes |
|---|---|---|
| `tools/box/oc_questions_push.sh` | `/root/.opencrabs/profiles/ops/scripts/oc_questions_push.sh` | `fd786fde695c7d3d57d7630adfa069aa39d9b7fa76c35754046699c82fa7a5f2` |
| `tools/box/oc-questions-push.service` | `/root/.config/systemd/user/oc-questions-push.service` | `13850376bd57c1143a5903fcd51f2017d8f3a9205e098bc5c01f715ff1fe0b85` |
| `tools/box/oc-questions-push.path` | `/root/.config/systemd/user/oc-questions-push.path` | `7233b1c0b00758128d0f36791f3b11fdd80794789f365526d3eaa3d4e69cbc7f` |

The three landed files were byte-identical to their live counterparts at the instant of
landing (2026-10-02), by `md5sum` on both sides. That is a property of that instant, not
of this revision: see the bound below.

## Which copy is authoritative

**Edit here; install to the box.** The direction is one-way and it is stated so that
there is never a question of which copy a reader should believe:

- **The tree is the source of a change.** A change to the push script is authored and
  reviewed here, where a diff exists and a revert is possible.
- **The box copy is the installed artefact.** It is what `systemd` executes, and it is
  not a second authoring surface. An edit made directly on the box is *drift*, and the
  check below is what makes it visible.

Install:

```sh
install -m 0755 tools/box/oc_questions_push.sh \
    /root/.opencrabs/profiles/ops/scripts/oc_questions_push.sh
install -m 0644 tools/box/oc-questions-push.service \
    /root/.config/systemd/user/oc-questions-push.service
install -m 0644 tools/box/oc-questions-push.path \
    /root/.config/systemd/user/oc-questions-push.path
systemctl --user daemon-reload
```

## The drift check

```sh
diff tools/box/oc_questions_push.sh \
     /root/.opencrabs/profiles/ops/scripts/oc_questions_push.sh
```

A non-empty diff means the box and the tree disagree. **Resolve it toward the tree** —
bring the box forward with the install command above, or land the box's change here with
a commit that says why. Never leave the disagreement standing: the whole reason this
directory exists is that a box file with no tracked counterpart has no history to check
it against.

## The bound — stated, not implied

**No gate in this repo enforces the freshness of these copies, and that is a bound rather
than an omission.** A gate would have to read the live box path, which is not part of any
tree: the mechanical suite runs offline against a tree, so a check that read the host
would report a property of the machine it happened to run on rather than of the revision.
What upholds this directory is therefore a process — the drift check above, run by whoever
touches the push path — and a stale copy is reported, never silently tolerated.

## What the push script does

It mirrors the Open Questions page tree from the agents' store to the vpn host, and it
does so **by comparison rather than by timing**: the source digest and the served digest
are taken for the page tree and printed on every run; a disagreement re-copies, bounded
to two further attempts, and past the bound it exits non-zero naming both digests. The
register is **not** mirrored (2026-10-02, S2): the confirmation's lane and question title
ride in the token's own page meta, so the public host needs no copy of the register — and
a copy it never had cannot go stale. The register still drives the render leg below, from
this host. `-c` is load-bearing for the retry — `rsync`'s default
size-and-mtime quick-check skips a same-length rewrite whose mtime was restored, so the
retry could otherwise never converge.

The script also carries **the render leg** (added 2026-10-02, render centralisation): one
canonical render per mutation, run **before** the mirror, so the served page is rendered
by the canonical asset rather than by whichever copy a member lane happens to invoke. Its
resolver is the answer backend's own predicate — a glob under the skill's tools root that
demands **exactly one** match and refuses loudly on any other count, never picking one —
and its swap writes **only where the tree differs**, because the unit is a `systemd.path`
trigger whose own writes would otherwise re-trigger it (a busy loop). The convergence guard
is why the swap uses `rsync -a --no-times -c --delete`: measured 2026-10-02, `rsync -a -c`
over a byte-identical pair emitted `.f..t......` and **moved the destination mtime**, which
is the mtime of the watched `pages/latest.json` — the pointer the path unit fires on.
