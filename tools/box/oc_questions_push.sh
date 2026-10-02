#!/bin/bash
# oc-questions-push — mirror the published pages and the register to vpn.
#
# DIRECTION: agents -> vpn (outbound). vpn needs NO inbound access to this host,
# so the public host holds no key that can reach the private one.
#
# Triggered by oc-questions-push.path when the store changes.
#
# WRITE ORDER (measured 2026-09-28, #207 -- this replaces a comment that had it
# backwards and so made the unsafe fix read as safe):
#     open.json            FIRST  (11:40:24.577)
#     pages/*/index.html   LAST   (11:40:28.916)  -- 4.339 s after the trigger
# The trigger file is written FIRST and the content it triggers for lands
# seconds later. The path unit is edge-triggered while this service is already
# active, so those later triggers are DROPPED -- which is why a single copy can
# leave the served page one revision stale with nothing left to correct it. The
# trigger is left alone deliberately: it is cheap and imperfect, and this
# script's self-check is what makes the copy correct.
#
# THE COPY IS CORRECT BY COMPARISON, NOT BY TIMING (#207 shape 3):
# after the copy, the SOURCE digest is compared against the SERVED digest for
# the page tree AND the register. Agreement -> ok. Disagreement -> re-copy,
# bounded to 2 further attempts; still divergent -> exit non-zero naming both
# digests. The comparison prints on EVERY run, clean or not, so "ok" carries the
# population it judged instead of being a bare word. An uncalibrated settle
# would bound a variable process with a constant, which is why the comparison
# replaces it.
#
# `-c` IS LOAD-BEARING FOR THE RETRY (measured 2026-09-28): rsync's default
# quick-check transfers on size+mtime alone, so a rewrite that preserves both is
# SKIPPED and the served copy stays content-stale. Measured here: same-length
# rewrite with the mtime restored -> rsync copied nothing, exited 0. Without
# `-c` the digest comparison would diverge every time and no retry could
# converge. Trees are small (pages ~29 files/100 KB, register ~50 KB).
#
# BOUND (until 2026-10-02): this made the COPY correct. It said nothing about the
# page's CONTENT -- "a render that never ran is a different leg". THE RENDER LEG
# BELOW NOW CLOSES THAT LEG: one canonical render per mutation, run before the
# mirror. See "THE RENDER LEG" further down for its resolver, its convergence
# guard, and the race it has to survive.
#
# Paths and transport are env-overridable so the comparison can be exercised
# against local scratch dirs (OC_QUESTIONS_PUSH_TARGET="" = local, no ssh).
set -uo pipefail

SRC_ROOT="${OC_QUESTIONS_SRC_ROOT:-/root/.opencrabs/profiles/ops/questions}"
PAGES_SRC="${OC_QUESTIONS_PAGES_SRC:-$SRC_ROOT/pages}"
REG_SRC="${OC_QUESTIONS_REG_SRC:-$SRC_ROOT/open.json}"
PAGES_DST="${OC_QUESTIONS_PAGES_DST:-/srv/questions}"
REG_DST="${OC_QUESTIONS_REG_DST:-/var/lib/questions/open.json}"
SETTLE="${OC_QUESTIONS_PUSH_SETTLE:-3}"
MAX_RETRY="${OC_QUESTIONS_PUSH_MAX_RETRY:-2}"
TARGET="${OC_QUESTIONS_PUSH_TARGET-vpn}"
SSH_OPTS="${OC_QUESTIONS_PUSH_SSH_OPTS:--o BatchMode=yes -o ConnectTimeout=10}"
SSH_CMD="${OC_QUESTIONS_PUSH_SSH:-ssh}"

sleep "$SETTLE"

# Guard: never let an empty or missing source --delete the served tree.
count=$(ls -1 "$PAGES_SRC" 2>/dev/null | wc -l)
if ! [[ "$count" =~ ^[0-9]+$ ]] || [ "$count" -lt 1 ]; then
    echo "push: refusing - source listing unavailable or empty (count='$count')" >&2
    exit 1
fi
if [ ! -s "$REG_SRC" ]; then
    echo "push: refusing - register missing or empty at $REG_SRC" >&2
    exit 1
fi

# Transport: with TARGET set the mirror goes over ssh; with TARGET="" it is a
# local copy, which is how the comparison is tested.
if [ -n "$TARGET" ]; then
    pages_dest="$TARGET:$PAGES_DST/"
    reg_dest="$TARGET:$REG_DST"
    rsync_e=(-e "$SSH_CMD $SSH_OPTS")
    remote_mv() { $SSH_CMD $SSH_OPTS "$TARGET" "mv -f '$REG_DST.tmp' '$REG_DST'"; }
else
    pages_dest="$PAGES_DST/"
    reg_dest="$REG_DST"
    rsync_e=()
    remote_mv() { mv -f "$REG_DST.tmp" "$REG_DST"; }
fi

# Per-file digests over a tree, path-relative and sorted, folded to one line.
# Content only -- mtimes never enter, so both ends agree across transports.
tree_digest() { # $1 = directory, $2 = "" | remote-host
    local dir=$1 host=${2:-}
    if [ -n "$host" ]; then
        $SSH_CMD $SSH_OPTS "$host" \
            "cd '$dir' && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 -r md5sum" \
            2>/dev/null | md5sum | cut -d' ' -f1
    else
        ( cd "$dir" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 -r md5sum ) \
            2>/dev/null | md5sum | cut -d' ' -f1
    fi
}

file_digest() { # $1 = file, $2 = "" | remote-host
    local f=$1 host=${2:-}
    if [ -n "$host" ]; then
        $SSH_CMD $SSH_OPTS "$host" "md5sum '$f'" 2>/dev/null | cut -d' ' -f1
    else
        md5sum "$f" 2>/dev/null | cut -d' ' -f1
    fi
}

# Content fingerprint of the whole SOURCE side (pages + register). Used to tell
# whether the source MOVED across a copy -- a digest comparison can agree at an
# instant when the source has not yet finished changing, and a copy is only
# settled when the source held still across the whole attempt.
fingerprint() {
    {
        ( cd "$PAGES_SRC" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 -r md5sum )
        md5sum "$REG_SRC"
    } 2>/dev/null | md5sum | cut -d' ' -f1
}

# =============================================================================
# THE RENDER LEG -- render centralisation (owner order 2026-09-30, started 10-02)
#
# The mirror below makes the COPY correct; it never asked WHICH COPY RENDERED the
# page. The render resolves its asset BESIDE THE INVOKED BINARY (`RENDER_SRC`,
# oc-questions:2127), so before this leg a member lane's own copy rendered the page
# the owner reads -- and two copies could serve two different behaviours on one
# path, which is the shape test for a tier-1 centralised element
# (docs/instruments/template-instruments.md section 6.4).
#
# This leg closes it: ONE canonical render per mutation, performed by the copy the
# ANSWER BACKEND itself resolves, on the push leg, before the mirror.
#
# THE RESOLVER IS THE BACKEND'S OWN PREDICATE, never a second one (instrument law
# section 5.1): glob `<CLI_ROOT>/*/oc-questions` plus `<CLI_ROOT>/oc-questions`,
# EXACTLY ONE match -- zero or two-or-more is a LOUD REFUSAL, never a pick, because
# the backend exits 127 on any other count. Authority for the shape:
# /opt/questions/backend.py (CLI_ROOT default + the CLI_RESOLVE glob), mirrored in
# tools/kit_census.py:answering_path(). No clause here pins the path: it is
# resolved at call time, which is why the CLI could move tools/ -> tools/state/
# without breaking anything.
#
# CONVERGENCE -- why the swap is CONDITIONAL. This script is triggered BY the store
# it writes into. systemd re-checks a path unit's monitored paths when the triggered
# service terminates and restarts it instantly on a change (systemd.path(5)), so an
# UNCONDITIONAL page write would re-trigger this unit forever. The scratch render
# therefore replaces the live page tree ONLY where it differs: an unchanged register
# renders identical bytes, nothing is written, and the cycle cannot sustain itself.
#
# RACE -- why the render is re-done on EVERY attempt. The mutating lane keeps its own
# best-effort local page (the owner's words keep the MUTATION member-invoked), so a
# member render can land AFTER this one. `src_pages = stage_digest` in the settled
# test is what catches it: while the live page tree no longer matches what the
# canonical render produced, the attempt is not settled and the render runs again.
# =============================================================================
CLI_ROOT="${OC_QUESTIONS_CLI_ROOT:-/root/.opencrabs/profiles/ops/skills/opencrabs-dev/tools}"
RENDER_DIR="${OC_QUESTIONS_RENDER_DIR:-$SRC_ROOT/build}"
CANON_CLI=""
STAGE=""

resolve_canonical() {
    local found=() p
    shopt -s nullglob
    for p in "$CLI_ROOT"/*/oc-questions "$CLI_ROOT"/oc-questions; do
        [ -f "$p" ] && found+=("$p")
    done
    shopt -u nullglob
    if [ "${#found[@]}" -ne 1 ]; then
        echo "push: render - REFUSED: the canonical CLI is not unique under $CLI_ROOT" >&2
        echo "push: render - found ${#found[@]} candidate(s); the answer backend wants exactly 1 and exits 127 on any other count" >&2
        for p in "${found[@]}"; do echo "push: render -   candidate: $p" >&2; done
        return 1
    fi
    CANON_CLI="${found[0]}"
    return 0
}

render_canonical() {
    # Render the register into a SCRATCH store with the canonical tool and leave the
    # scratch tree in $STAGE. This function never writes the live page tree: the
    # caller swaps only what differs, which is what keeps the unit convergent.
    local stage rc
    [ -n "$STAGE" ] && rm -rf "$STAGE"
    STAGE=""
    stage=$(mktemp -d "${TMPDIR:-/tmp}/oc-questions-render.XXXXXX") || {
        echo "push: render - REFUSED: cannot create a scratch store" >&2; return 1; }
    if ! cp -p "$REG_SRC" "$stage/open.json" 2>/dev/null; then
        echo "push: render - REFUSED: cannot stage the register" >&2
        rm -rf "$stage"; return 1
    fi
    OC_QUESTIONS_DIR="$stage" OC_QUESTIONS_RENDER_DIR="$RENDER_DIR" \
        "$CANON_CLI" publish --json >/dev/null 2>"$stage/render.err"
    rc=$?
    if [ "$rc" -ne 0 ]; then
        echo "push: render - REFUSED: the canonical render failed (rc=$rc)" >&2
        sed 's/^/push: render -   /' "$stage/render.err" >&2
        rm -rf "$stage"; return 1
    fi
    if [ ! -s "$stage/pages/latest.json" ]; then
        echo "push: render - REFUSED: the canonical render produced no page pointer" >&2
        rm -rf "$stage"; return 1
    fi
    STAGE="$stage"
    return 0
}

cleanup_stage() { [ -n "${STAGE:-}" ] && rm -rf "$STAGE"; return 0; }
trap cleanup_stage EXIT

attempt=0
while :; do
    attempt=$((attempt + 1))

    # ONE canonical render per attempt, before anything is mirrored.
    resolve_canonical || exit 5
    render_canonical || exit 5

    # Swap the canonical page tree into the live store, and ONLY where it differs.
    #
    # `--no-times -c` IS THE CONVERGENCE MECHANISM, and BOTH flags are load-bearing.
    # This path unit watches `pages/latest.json` with PathModified=, so any write to
    # that file -- content OR mtime -- re-triggers the service that just ran
    # (systemd.path(5): monitored paths are re-checked the moment the service exits),
    # and an unconditional writer would busy-loop.
    #
    #   * `-c` alone is NOT enough. The staging tree is freshly rendered, so every
    #     mtime in it is "now"; `-a` carries `-t`, and rsync syncs the mtime of a
    #     file whose CONTENT already matches. Measured 2026-10-02 on rsync 3.2.7:
    #     `rsync -a -c -i` over a byte-identical pair emitted `.f..t......` and moved
    #     the destination mtime -- no data transferred, file touched anyway.
    #   * `--no-times` removes that write. Measured on the same pair:
    #     `rsync -a --no-times -c -i` printed nothing and left the mtime untouched,
    #     while a REAL change still transferred (`>fcsT......`) and `--delete` still
    #     pruned. `-c` stays required beside it: without a checksum the mtime is the
    #     quick-check, and never syncing mtimes would make every run re-copy all 29
    #     files -- the busy-loop again, by a different door.
    #
    # THE RENDER IS NOT BYTE-DETERMINISTIC: `index.html` carries a wall-clock age
    # ("asked 27.9h ago"), so it re-renders differently once a 0.1 h tick has passed
    # (measured 2026-10-02: the only delta between the live page tree and a fresh
    # canonical render of the SAME register was those age strings -- that drift, not
    # a divergent renderer, is why the first run swapped). index.html lives in a
    # subdirectory and is not itself watched, so copying it cannot re-trigger the
    # unit; the watched pointer is left byte- AND mtime-identical, and writes
    # nothing at all. Convergence is structural, not a matter of timing.
    if ! diff -rq "$STAGE/pages" "$PAGES_SRC" >/dev/null 2>&1; then
        rsync -a --no-times -c --delete "$STAGE/pages/" "$PAGES_SRC/" || exit 5
        echo "push: render - canonical page tree swapped in (attempt $attempt)"
    fi
    stage_digest=$(tree_digest "$STAGE/pages")

    before=$(fingerprint)

    # Pages: --delete, so a rotated or expired token stops being served.
    rsync -a -c --delete --timeout=60 "${rsync_e[@]}" "$PAGES_SRC/" "$pages_dest" || exit 2

    # Register: to a temp path then rename, so a reader never sees a partial file.
    rsync -a -c --timeout=60 "${rsync_e[@]}" "$REG_SRC" "$reg_dest.tmp" || exit 3
    remote_mv || exit 4

    # The comparison: source vs SERVED, both legs. Printed unconditionally.
    src_pages=$(tree_digest "$PAGES_SRC")
    dst_pages=$(tree_digest "$PAGES_DST" "$TARGET")
    src_reg=$(file_digest "$REG_SRC")
    dst_reg=$(file_digest "$REG_DST" "$TARGET")
    echo "push: compare - pages src=$src_pages served=$dst_pages | register src=$src_reg served=$dst_reg"

    # Settled = the served copy matches the source AND the source held still
    # across the attempt. Either half alone is insufficient: agreement can be
    # momentary (the source is still being written), and stillness alone says
    # nothing about what was actually mirrored.
    after=$(fingerprint)
    if [ "$src_pages" = "$dst_pages" ] && [ "$src_reg" = "$dst_reg" ] \
       && [ "$before" = "$after" ] && [ "$src_pages" = "$stage_digest" ]; then
        break
    fi

    if [ "$attempt" -gt "$MAX_RETRY" ]; then
        echo "push: DIVERGENT after $attempt attempt(s) - pages src=$src_pages served=$dst_pages | register src=$src_reg served=$dst_reg | canonical=$stage_digest" >&2
        exit 6
    fi
    if [ "$src_pages" != "$stage_digest" ]; then
        echo "push: re-rendering - the live page tree no longer matches the canonical render (attempt $attempt of $((MAX_RETRY + 1)))"
    elif [ "$src_pages" = "$dst_pages" ] && [ "$src_reg" = "$dst_reg" ]; then
        echo "push: re-copying - the copy matched but the source was still moving (attempt $attempt of $((MAX_RETRY + 1)))"
    else
        echo "push: re-copying - the served copy does not match the source (attempt $attempt of $((MAX_RETRY + 1)))"
    fi
done

echo "push: ok - $count page entries, register refreshed (attempts=$attempt, pages=$src_pages, register=$src_reg, canonical=$stage_digest)"
