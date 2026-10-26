#!/usr/bin/env python3
"""Gate: the ledger never shrinks — no commit removes a row identity.

Origin (issue #58, ruled at n=354). `tools/ledger.py`'s append-time guard (shipped as
#57's clause 1) compares the working ledger against the COMMITTED lineage and refuses
when the working file is shorter or a shared row differs. That closes the revert shape.
It does not close the **write side of the file itself**, and it leaves no **trace**: a
writer that never calls the tool bypasses the lock, the guard and the reflog together.
And once such a shrink is itself COMMITTED, the guard compares working against committed,
goes self-consistent, and `verify` reads clean too — `n` stays monotonic, every sequence
stays complete, and both gates are green over a ledger that has lost committed history.

**Detection, never prevention (clause 1).** A writer that never calls the tool cannot be
prevented by anything inside the tool: the lock and the guard are code, and single-writer
is a property of the CODE PATH, not of the file. Prevention is impossible by construction.
P29 asks that the invariant be upheld by an active process or a deterministic gate, and
detection is available: read the ARTIFACT — the committed diffs — not the code.

**No-shrink, scoped to the pushed lineage (clause 2).** A row present in `origin/main`'s
lineage of `evidence/ledger.jsonl` is never removed by a lawful path; a row is retired by
APPENDING a row naming the retired identity, the sanctioning ruling and the proof — never
by deleting it from the file. A LOCAL, UNPUSHED row may be amended away, because nothing
published it. This is the load-bearing clause because it makes the detector DECIDABLE: if
no lawful path removes a pushed row, every commit whose diff removes a row identity is a
violation with no accounting leg to adjudicate, and the false-positive surface disappears
with the question.

**The identity tuple.** A row's identity is `(n, ts, event, actor, subject)` — #52 clause 1's
tuple. A commit that changes a row's `detail` while preserving those five fields is a
CONTENT change, not an identity removal, and is out of this gate's scope. That distinction
is why the predicate compares identity SETS between consecutive revisions rather than
searching for a removal keyword: a keyword search finds nothing, and the live history
proves it — measured over 260 ledger commits, 8 carry deletions and only ONE removes an
identity.

**The 'own commit' mitigation is rejected (clause 3).** Requiring a ledger rewrite to be
committed as its own commit is unenforceable on this tree: a commit is transport, not
identity, and this tree's commits routinely transport peer rows, so no mechanical check
can separate a commit that transports a peer's row from a commit that IS the rewrite.
Under clause 2 the lawful path never deletes, so a deletion needs no annotation to be
evidence — it is a violation on its face.

**A deterministic offline gate, not a host-side reader (clause 4).** The issue proposed a
host-side reader, reasoning a writer bypassing the tool cannot be reached from inside it.
The premise is right; the conclusion does not follow — a repo TEST is not inside the tool.
This walks the committed history of the ledger, degrading to `HEAD` where `origin/main` is
unreadable. Residual stated rather than hidden: a repo gate is a repo file, so the same
bypassing writer could delete it — and that is a SECOND visible repo change that
`tests/test_law_coverage.py` turns red under P11. That layered posture is the factory's
standard; a host-side reader is not required by the issue's premise.

**The predicate is measured, not proposed.** Over the committed history of
`evidence/ledger.jsonl`, exactly ONE commit removes a row identity: `8643edd4`, rows
302 -> 304, removing `n=302` / `#50` — the #52 renumbering incident, already on the record
and corrected by append at n=317/318. That is this detector's ENTIRE historical exemption
list: one entry, dated, with the #52 ruling as its proof. Decidable, bounded, not noisy.

**The exemption list is factory data read by the gate, never source inside it.** This file
is copied byte-identically into `TEMPLATE/` (guarded by `tests/test_template_sync.py`), so
an inline table naming one factory's sha would ship a foreign sha to every new factory. The
data lives at `docs/ledger-no-shrink-exemptions.json`, whose skeleton is
`TEMPLATE/docs/ledger-no-shrink-exemptions.example.json`. An exemption is a visible debt,
not forgiveness: every matching entry is printed as an `excused:` line on EVERY run, and
the closing line distinguishes clean from excused so the two are never the same output. A
malformed entry, or one that matches no removal, is a gate ERROR rather than a silent pass.

**A removal is accounted for in one of two ways, and the two are never conflated.** An
EXEMPTION (the sha-keyed table above) is the case where the repair space is genuinely
EMPTY: the commit is pushed, rewriting it is barred by the identity law, and nothing on the
record already accounts for the removal. A DECLARED RECONCILIATION is the case #298 decided
— a fork where BOTH sides were PUBLISHED, so two lanes each published rows around the same
`n` and a merge re-minted one side, removing a published identity by a path the re-mint
protocol does not cover (`docs/instruments/ledger.md` section 9.1). There the lawful repair
is an explicit reconciliation ROW naming the removed identities and the disposition, and the
gate reads it from the ledger itself rather than from a second factory-data file: a line
ANCHORED at `reconciles:` at the start of a line in any row's `detail`, carrying
`{"removed": [<identity>, ...], ...}`. A declared identity is matched VERBATIM against an
identity the walk actually observed removed — a declaration naming a row that was not
removed, or naming it with the wrong `ts`, excuses nothing and is a gate ERROR, so a false
declaration cannot buy silence. The mechanism is deliberately NOT a second exemption: #47
clause 4 rules that a second entry of the same shape is a PROCESS DEFECT, and the remedy for
a process defect is a mechanism, never another row.

**Zero commits examined is a FAILURE, never a pass.** A gate that silently examines nothing
is indistinguishable from a gate that examines nothing and passes. If the walk finds no
commit touching the ledger, this gate FAILS naming what it could not read.

Run:  python3 tests/test_ledger_no_shrink.py
Exit: 0 clean or fully accounted, 1 on any unaccounted row removal.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEDGER_PATH = "evidence/ledger.jsonl"
EXEMPTIONS_PATH = "docs/ledger-no-shrink-exemptions.json"
PRIMARY_REF = "origin/main"
FALLBACK_REF = "HEAD"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")

# The #52 clause 1 identity tuple. A row is identified by these five fields; a commit that
# alters any of them removes the old identity and adds a new one.
IDENTITY_KEYS = ("n", "ts", "event", "actor", "subject")

# The reconciliation declaration, as it appears in a ledger row's `detail`. ANCHORED at the
# start of a line so a mid-sentence mention of the word cannot satisfy it — a declaration is
# a record, and a record that any prose can impersonate is not one. `load_reconciliations`
# reads it; the ledger itself is the store, so a reconciliation needs no second data file.
RECONCILES_PREFIX = "reconciles:"


def _git(*args: str, cwd: Path | None = None) -> tuple[int, str, str]:
    """Run git, returning `(rc, stdout, stderr)` — never raising on a missing ref."""
    proc = subprocess.run(
        ["git", *args], cwd=str(cwd or REPO), capture_output=True, text=True
    )
    return proc.returncode, proc.stdout, proc.stderr


def repo_toplevel() -> Path | None:
    """The git top level containing this gate, so a copy in a subdirectory still works.

    The ledger is repo data tracked from the top level, so it is resolved there rather than
    against this file's parent. That also keeps the walk NON-VACUOUS for the `TEMPLATE/`
    copy, which sits inside the meta-factory repo: resolving against `TEMPLATE/` instead
    would find no ledger history at all and pass over an empty population — the vacuous
    pass the zero-commits rule exists to forbid.
    """
    rc, out, _ = _git("rev-parse", "--show-toplevel")
    return Path(out.strip()) if rc == 0 and out.strip() else None


def identity_of(row: dict) -> tuple:
    """A row's identity — the #52 tuple, as a hashable key."""
    return tuple(row.get(k) for k in IDENTITY_KEYS)


def removed_identities(before_rows: list[dict], after_rows: list[dict]) -> list[tuple]:
    """Identities present before a revision and absent after it, sorted by `n`.

    Set difference, never a keyword search: the measured history shows why. Of 260 commits
    touching the ledger, 8 carry deletions and 7 of those only modify a row's `detail` —
    the same five identity fields survive. Only `8643edd4` actually removes one.
    """
    before = {identity_of(r) for r in before_rows}
    after = {identity_of(r) for r in after_rows}
    removed = before - after
    return sorted(removed, key=lambda key: (key[0] is None, key[0]))


def _remint_successor(row: dict, after_rows: list[dict]) -> int | None:
    """The `n` that re-mints `row` in `after_rows`, or None when nothing does.

    A re-mint is the SAME ACT carried under the SAME OR A HIGHER number: `event`, `actor`
    and `subject` are the row's identity of act, and a re-mint keeps all three. `ts` and
    `detail` are deliberately NOT compared: a re-mint is stamped at a new instant and its
    prose often names the number it replaced, so requiring those to match would fail on
    exactly the rows the law permits.

    SAME `n` IS A RE-MINT, and demanding strictly-up was the #569 defect. §9.1's freedom is
    about PUBLICATION, not about arithmetic: a row that exists only in a working tree may be
    re-stamped before it is pushed, and the ordinary way a lane does that is to edit the row
    in place -- same `n`, fresh `ts` -- rather than to skip numbers it never published.
    Measured on `e446fa9d` (2026-10-26): 4307 rows either side, all four removed identities
    re-present at the SAME `n` with the same `(event, actor, subject)` and only `ts` moved,
    which `r["n"] > n` could not see; the gate called that commit a shrink while no `n` was
    removed anywhere in it.

    LOWER `n` is still NOT a re-mint, and that half of the bound stands unchanged: a
    successor at a lower number is a different row wearing a number the removal did not
    publish, which is precisely what the identity law forbids.
    """
    n = row.get("n")
    if not isinstance(n, int):
        return None
    want = (row.get("event"), row.get("actor"), row.get("subject"))
    candidates = [
        r.get("n")
        for r in after_rows
        if (r.get("event"), r.get("actor"), r.get("subject")) == want
        and isinstance(r.get("n"), int)
        and r["n"] >= n
    ]
    return min(candidates) if candidates else None


def no_shrink_problems(
    transitions: Iterable[dict],
    exemptions: dict[str, dict],
    declared: set[tuple] | frozenset = frozenset(),
) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    """Return `(problems, excused, stale, reconciled, stale_declarations)`.

    Each transition is `{"sha", "subject", "before", "after", "merged_in"}` -- the row lists
    at the commit, at its FIRST parent, and at every OTHER parent. Pure, so a synthetic
    history can drive it: a rule that has only ever seen good input has not been shown to
    reject bad input.

    `transitions` is CONSUMED ONCE and may be a lazy stream (#510): every comparison is
    within a single transition, so nothing here needs the population at once. Callers pass
    `iter_transitions`' stream on live history and a list in the probes.

    A removal is accounted for by an EXEMPTION (keyed by the commit's sha) or by a DECLARED
    RECONCILIATION (keyed by the removed identity itself). The two are returned separately
    and printed separately, so `clean`, `excused` and `reconciled` are never the same output.
    `declared` holds the identity tuples a reconciliation row named, and each is matched
    VERBATIM against an identity the walk observed removed.

    A RE-MINT IS NOT A SHRINK (#301, and the re-mint bound in
    `docs/instruments/ledger.md` §9.1). Three shapes are distinguished,
    because conflating them is the trap the #301 ruling names -- a guard that fires on a
    legal re-mint is worse than none, since the lane learns to ignore it:

      1. REMOVED AND PRESENT ON A MERGED-IN LINE -- the identity was published, and the
         merge resolution dropped it. This is a PROBLEM: the one class the pre-#301 walker
         could not see, and the reason the gate exists.
      2. REMOVED AND ABSENT FROM EVERY MERGED-IN LINE -- the identity never reached the
         published line, so the re-mint bound (`docs/instruments/ledger.md` §9.1) makes the
         re-mint free. EXCUSED, and printed, because "clean"
         and "a re-mint happened here" must not read the same.
      3. REMOVED WITH NO MERGED-IN LINE TO COMPARE AGAINST -- absence proves nothing, so the
         row must carry the re-mint SIGNATURE (the same event/actor/subject at the same or a
         higher `n` in `after`), or be exempted, or be named by a reconciliation. A bare
         authored deletion of a published row stays a PROBLEM, which is what keeps shape 2
         from becoming a blanket excuse.

    SHAPES 2 AND 3 ARE PROPERTIES OF THE ROW, AND #569 IS WHAT FORCED THAT APART. Each shape
    asks one question of the IDENTITY: was it PUBLISHED (present in a population a peer could
    see), and does the SAME ACT stand in `after`. Shape 2's free pass is therefore not "the
    commit is a merge" -- it is "the row is absent from the published population, and this
    transition HAS a published population to be absent from"; a merge with no merged-in rows
    read has none, and the signature decides instead. Before #569 the branch read
    `if is_merge`, a property of the COMMIT, so shape 2 could never fire on the ordinary way a
    lane re-mints before publishing -- a single-parent commit -- and a lawful re-stamp read as
    a deletion.

    The obvious-looking alternative -- free the re-mint when the row's `n` sits above the
    highest `n` on the merged-in line -- is REJECTED, and the rejection is the reason shape 2
    is phrased as absence rather than as arithmetic. A row that exists only on the LOCAL
    first-parent line can sit BELOW the remote's high-water mark (a peer published further
    while this lane held an unpublished row at a lower `n`), and it was still never
    published; an `n`-vs-watermark test would red exactly that lawful case. Publication is a
    property of the population, never of the number.

    The INVERSE case is its own leg: an identity present on a merged-in line and absent from
    the merge, that was never on the first-parent line, was dropped ON THE WAY IN. A
    first-parent diff reports nothing for it, so `removed_identities` cannot see it, and it
    is a problem by the same predicate -- a published row is gone.

    `stale` names exemptions that matched nothing, and `stale_declarations` names declared
    identities that no transition removed. Both are gate ERRORS rather than silent passes:
    an accounting entry that excuses nothing inflates the visible debt while weakening the
    gate, and a declaration for a removal that did not happen is a false record.
    """
    problems: list[str] = []
    excused: list[str] = []
    reconciled: list[str] = []
    matched_exemptions: set[str] = set()
    matched_declarations: set[tuple] = set()

    for transition in transitions:
        sha = transition["sha"]
        merged_in_rows = transition.get("merged_in") or []
        merged_in_ids = {identity_of(r) for r in merged_in_rows}
        after_rows = transition["after"]
        after_ids = {identity_of(r) for r in after_rows}
        before_ids = {identity_of(r) for r in transition["before"]}
        removed = removed_identities(transition["before"], after_rows)

        # The inverse leg: published rows the resolution dropped on the way in. A row that
        # is ALSO absent from the first parent is invisible to `removed_identities`, and a
        # row present on both parents is already covered above, so only the difference is
        # taken here to keep one removal from being reported twice.
        dropped_on_the_way_in = sorted(
            merged_in_ids - after_ids - before_ids,
            key=lambda key: (key[0] is None, key[0]),
        )

        if not removed and not dropped_on_the_way_in:
            continue

        entry = exemptions.get(sha)
        if entry is not None:
            matched_exemptions.add(sha)
            excused.append(f"{sha} — {entry.get('reason', '')}")

        # Declarations are read for EVERY transition, exempted or not: an exemption and a
        # reconciliation can both be on the record for one removal, and a declaration that
        # is true must not read as stale merely because an exemption also covers it.
        named = [key for key in removed if key in declared]
        matched_declarations.update(named)
        if named:
            reconciled.append(
                f"{sha[:12]} — {len(named)} identity(ies) named by a reconciliation row: "
                + ", ".join(f"n={key[0]} ({key[2]} {key[3]} {key[4]})" for key in named)
            )

        before_by_id = {identity_of(r): r for r in transition["before"]}
        shrunk: list[tuple] = []
        reminted: list[tuple] = []
        for key in removed:
            if key in declared or entry is not None:
                continue
            # THE DECISION IS ABOUT THE ROW, NEVER ABOUT THE COMMIT (#569). Each test below
            # asks a question of the IDENTITY, and the two properties that decide it are
            # both row-level: whether the row was PUBLISHED (present on a line a peer could
            # see) and whether the SAME ACT stands in `after`. `is_merge` is not consulted
            # at all -- it is a property of the commit, and a predicate keyed on it cannot
            # tell a lane's ordinary pre-publication re-stamp from a deletion, which is what
            # made `e446fa9d` (single parent, four unpublished rows re-stamped in place) read
            # as a shrink.
            if key in merged_in_ids:
                shrunk.append(key)          # shape 1: it was PUBLISHED, and the merge dropped it
                continue
            row = before_by_id.get(key, {})
            successor = _remint_successor(row, after_rows)
            if successor is not None:
                # shape 3: the re-mint SIGNATURE is present -- the same act at the same or a
                # higher `n`. Checked before the merge free-pass on purpose: where a
                # signature exists the printed reason names the evidence rather than the
                # absence of a merged-in line, and where the row WAS published, shape 1 has
                # already fired above, so a same-`n` re-stamp of a published row still fails.
                reminted.append(key)
            elif merged_in_rows:
                # shape 2: absent from every merged-in line, so the identity never reached
                # the published line and §9.1 makes the re-mint free. A signature is not
                # required here because the merged-in line IS the publication evidence.
                reminted.append(key)
            else:
                shrunk.append(key)          # no signature and no merged-in line: a deletion

        if reminted:
            excused.append(
                f"re-mint {sha[:12]} — {len(reminted)} identity(ies) re-minted: the same act "
                "stands at the same or a higher `n` and no merged-in line carries the "
                "identity: "
                + ", ".join(f"n={key[0]} ({key[2]} {key[3]} {key[4]})" for key in reminted)
            )
        if shrunk:
            described = ", ".join(
                f"n={key[0]} ({key[2]} {key[3]} {key[4]})" for key in shrunk
            )
            why = (
                "published on a merged-in line, dropped by the resolution"
                if any(key in merged_in_ids for key in shrunk)
                else "no re-mint signature and no sanctioning row"
            )
            problems.append(
                f"{sha[:12]} removes {len(shrunk)} row identity(ies) from "
                f"{LEDGER_PATH} without a sanctioning row: {described} "
                f"— {why} — subject: {transition['subject'][:70]}"
            )
        if dropped_on_the_way_in:
            described = ", ".join(
                f"n={key[0]} ({key[2]} {key[3]} {key[4]})" for key in dropped_on_the_way_in
            )
            problems.append(
                f"{sha[:12]} drops {len(dropped_on_the_way_in)} PUBLISHED row identity(ies) "
                f"that existed only on the merged-in line: {described} "
                f"— subject: {transition['subject'][:70]}"
            )

    stale = sorted(set(exemptions) - matched_exemptions)
    stale_declarations = sorted(
        declared - matched_declarations, key=lambda key: (key[0] is None, key[0])
    )
    return problems, excused, stale, reconciled, stale_declarations


def load_exemptions(path: Path) -> tuple[dict[str, dict], list[str]]:
    """`({full_sha: entry}, problems)` read from the factory data file.

    Absent or empty data means no exemptions — the shipped state of a new factory. Anything
    malformed is a problem, never a silent pass: an exemption list that quietly fails to
    load is indistinguishable from no exemptions, which is the same vacuous-pass shape the
    zero-commits rule exists to forbid.
    """
    problems: list[str] = []
    if not path.is_file():
        return {}, problems
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, [f"{path.name} is not JSON: {exc}"]
    if not isinstance(data, dict):
        return {}, [f"{path.name}: expected a JSON object with an 'exemptions' list"]
    raw = data.get("exemptions", [])
    if not isinstance(raw, list):
        return {}, [f"{path.name}: 'exemptions' must be a list"]

    entries: dict[str, dict] = {}
    for i, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            problems.append(f"{path.name}: entry {i} is not an object")
            continue
        sha = item.get("sha")
        if not isinstance(sha, str) or not FULL_SHA.match(sha):
            problems.append(
                f"{path.name}: entry {i} names a sha that is not a full 40-character "
                f"lowercase hex sha: {sha!r}"
            )
            continue
        if not item.get("reason"):
            problems.append(f"{path.name}: entry {i} ({sha[:12]}) carries no reason")
            continue
        if sha in entries:
            problems.append(f"{path.name}: entry {i} repeats {sha}")
            continue
        entries[sha] = item
    return entries, problems


def load_reconciliations(
    rows: list[dict],
) -> tuple[set[tuple], set[tuple], list[str]]:
    """`({removed identity}, {surviving identity}, problems)` read from the ledger's rows.

    A reconciliation is a LEDGER ROW, not a second data file: the row that names a removed
    identity IS the record, and the ledger is already the surface every lane can read. The
    declaration is a line ANCHORED at `reconciles:` — at the start of a line, so prose that
    merely mentions the word cannot satisfy it — followed by a JSON object carrying
    `"removed": [<identity>, ...]`. The `sha` and `disposition` keys are provenance and are
    ignored by the match. `"surviving": [<identity>, ...]` is NOT ignored: it is the
    declaration's claim about what stands at the tip, and `surviving_problems` reads it
    against the tip rows — a field written and never read can only lie.

    Anything malformed is a problem, never a silent pass: a declaration that quietly fails
    to parse is indistinguishable from no declaration at all, which is the same vacuous-pass
    shape the exemption loader and the zero-commits rule exist to forbid.
    """
    problems: list[str] = []
    declared: set[tuple] = set()
    surviving: set[tuple] = set()
    for row in rows:
        detail = row.get("detail")
        if not isinstance(detail, str):
            continue
        for line in detail.splitlines():
            if not line.startswith(RECONCILES_PREFIX):
                continue
            raw = line[len(RECONCILES_PREFIX):].strip()
            # The parse is ATOMIC per declaration: both halves are collected into locals and
            # committed only when the whole record is sound. A record that any prose can
            # impersonate is not a record, and neither is one that is half garbage — honouring
            # a well-formed `removed` half beside a malformed `surviving` half would let a
            # broken declaration sanction a real removal while its own defect read as an
            # unrelated problem.
            local_declared: set[tuple] = set()
            local_surviving: set[tuple] = set()
            local_problems: list[str] = []
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                problems.append(
                    f"row n={row.get('n')} carries a '{RECONCILES_PREFIX}' line that is "
                    f"not JSON: {exc}"
                )
                continue
            if not isinstance(payload, dict) or not isinstance(payload.get("removed"), list):
                problems.append(
                    f"row n={row.get('n')} carries a '{RECONCILES_PREFIX}' declaration "
                    f"with no 'removed' list"
                )
                continue
            if not payload["removed"]:
                problems.append(
                    f"row n={row.get('n')} declares a reconciliation naming no identity — "
                    f"a declaration that names nothing accounts for nothing"
                )
                continue
            if "surviving" in payload and not isinstance(payload["surviving"], list):
                problems.append(
                    f"row n={row.get('n')} carries a 'surviving' value that is not a list: "
                    f"{payload['surviving']!r}"
                )
                continue
            for item in payload["removed"]:
                if not isinstance(item, dict):
                    local_problems.append(
                        f"row n={row.get('n')} declares a removed identity that is not an "
                        f"object: {item!r}"
                    )
                    continue
                identity = identity_of(item)
                if any(part is None for part in identity):
                    local_problems.append(
                        f"row n={row.get('n')} declares a removed identity missing one of "
                        f"{IDENTITY_KEYS}: {item!r}"
                    )
                    continue
                local_declared.add(identity)
            for item in payload.get("surviving", []):
                if not isinstance(item, dict):
                    local_problems.append(
                        f"row n={row.get('n')} declares a surviving identity that is not "
                        f"an object: {item!r}"
                    )
                    continue
                identity = identity_of(item)
                if any(part is None for part in identity):
                    local_problems.append(
                        f"row n={row.get('n')} declares a surviving identity missing one of "
                        f"{IDENTITY_KEYS}: {item!r}"
                    )
                    continue
                local_surviving.add(identity)
            # Commit the record only when it is WHOLE: a malformed half makes the whole
            # declaration account for nothing, so a well-formed `removed` list beside a
            # malformed `surviving` list cannot sanction a removal on its own. That is
            # "malformed is a problem, never a silent pass" at the granularity of ONE record.
            if local_problems:
                problems.extend(local_problems)
                continue
            declared |= local_declared
            surviving |= local_surviving
    return declared, surviving, problems

def surviving_problems(surviving: set[tuple], tip_rows: list[dict]) -> list[str]:
    """Problems for `surviving` identities a reconciliation row names but the tip lacks.

    A `surviving` list is a CLAIM about what stands at the tip after a re-mint, and a claim
    with no reader is a record that can only lie (the four-shapes family, shape (d)). So it
    is read: every identity the declaration says survived must be a row at the tip, or the
    declaration describes a state the ledger is not in. This is deliberately kept OUT of
    `no_shrink_problems`: that function judges a REMOVAL against a declaration, while this
    judges the declaration's own factual claim about the present.
    """
    present = {identity_of(row) for row in tip_rows}
    return [
        f"a reconciliation row declares n={key[0]} ({key[2]} {key[3]} {key[4]}) survived, "
        f"but no such row stands at the tip — a declaration describing a state the ledger "
        f"is not in accounts for nothing"
        for key in sorted(surviving - present, key=lambda k: (k[0] is None, k[0]))
    ]

def resolvable(ref: str, cwd: Path) -> bool:
    """True when a ref resolves — the `origin/main` -> `HEAD` degradation (clause 4)."""
    rc, out, _ = _git("rev-parse", "--verify", "--quiet", ref, cwd=cwd)
    return rc == 0 and bool(out.strip())


# METADATA ONLY, and deliberately so (#510). This cache holds `history_entries` -- one small
# dict per commit touching the ledger (sha, subject, added, deleted). It must NEVER hold
# TRANSITIONS, which is what it held until #510: a transition carries the FULL row list on
# both sides, so caching 67 deletion commits retained 67 x 2 x 3,761 parsed dicts at once and
# the gate peaked at 1.17 GiB (VmHWM 1202884 kB), OOM-killing the shared `opencrabs-ops`
# daemon four times in one day. The population moves ONE WAY -- 15 deletion commits when this
# cache was introduced, 67 at #510 -- so the retention was O(deletion_commits x rows) and got
# worse every week. `iter_transitions` streams instead; the rows walk has no cache at all.
_WALK_CACHE: dict[tuple, tuple] = {}


def history_entries(
    ref: str, rel_path: str, cwd: Path
) -> tuple[list[dict] | None, str]:
    """`([{sha, subject, added, deleted}], error)` for commits touching `rel_path`.

    The deletion counts are a stated OPTIMISATION, not the predicate: a row occupies at
    least one line and any change to that line counts as a deletion, so a commit with zero
    deleted lines cannot remove a row identity and needs no set comparison. The live
    history bears it out — at 2026-09-28, 831 commits touch the ledger and only 15 carry
    deletions, so the full comparison runs over those 15 rather than all 831. THE FIGURES
    MOVE: this was 260/8 when the sentence was written, and the walk's cost is
    O(history x filesize) — measured 55.7 s for one walk at 831 commits over a 3.4 MB
    file. That is why the result is CACHED: the gate walks the live ledger twice, and a
    second identical walk of immutable history buys nothing and cost the run its budget
    (rc=124 against a 200 s cap, 2026-09-28).

    `--diff-merges=first-parent` IS LOAD-BEARING (#301). A plain `git log --numstat`
    prints NO diffstat at all for a merge commit, so a merge whose resolution drops a
    row contributed `deleted=0` and the optimisation above silently skipped it -- the
    walker was blind to exactly the commit class where a conflict resolution can delete
    an identity without any authored commit deleting one. Measured on a three-line
    scratch history (/tmp/mtest): plain `--numstat` printed `5e8d48d merge resolution
    drops row 2` with NO numbers, while `--diff-merges=first-parent` printed
    `0 1 led.jsonl` for it and the same three other commits unchanged.

    The flag is `--diff-merges=first-parent`, NOT `-m` and NOT `-m --first-parent`:
    `-m` emits a merge ONCE PER PARENT (the same sha twice, here `0 1` then `1 2`), which
    double-counts the commit in the transition list; and `-m --first-parent` drops
    side-branch commits from the population entirely (the fixture's `8755a06 side adds
    row 4` vanished), which would hide real deletions. `first-parent` also pairs exactly
    with `build_transitions`' `before = rows_at(f"{sha}^")` -- `^` IS the first parent,
    so the diffstat and the before-side now describe the same comparison.
    """
    _key = ("history", ref, rel_path, str(cwd))
    if _key in _WALK_CACHE:
        return _WALK_CACHE[_key]

    rc, out, err = _git(
        "log",
        "--diff-merges=first-parent",
        "--numstat",
        "--format=%x01%H%x01%s",
        ref,
        "--",
        rel_path,
        cwd=cwd,
    )
    if rc != 0:
        return None, (err.strip() or f"git log failed for {ref}")
    entries: list[dict] = []
    sha: str | None = None
    subject = ""
    added = deleted = 0
    for line in out.splitlines():
        if line.startswith("\x01"):
            if sha is not None:
                entries.append(
                    {"sha": sha, "subject": subject, "added": added, "deleted": deleted}
                )
            parts = line.split("\x01")
            sha = parts[1] if len(parts) > 1 else ""
            subject = parts[2] if len(parts) > 2 else ""
            added = deleted = 0
        elif sha is not None and line.strip():
            cols = line.split("\t")
            if len(cols) == 3:
                if cols[0].isdigit():
                    added += int(cols[0])
                if cols[1].isdigit():
                    deleted += int(cols[1])
    if sha is not None:
        entries.append({"sha": sha, "subject": subject, "added": added, "deleted": deleted})
    return entries, ""


# A BOUNDED rows cache, sized to the WALK's access pattern rather than to history (#510).
#
# The walk visits commits newest-first and reads TWO revisions per commit: the commit's own
# rows and its first parent's. Consecutive commits SHARE a revision -- commit i's first
# parent IS commit i+1 -- so `after(commit i+1)` is the very list `before(commit i)` just
# parsed. Holding the last few parses turns that into a hit: measured 235 `git show` calls
# and 235 parses become 168, and the walk's 108.7 s drops with them.
#
# The bound is the point. This is NOT the cache #510 removed: that one retained EVERY
# deletion commit's two sides for the process lifetime (1.17 GiB). Two entries hold at most
# ~56 MiB and are evicted by the walk itself as it advances.
_ROWS_CACHE: dict[str, list[dict] | None] = {}
_ROWS_CACHE_MAX = 2

def _cache_rows(key: str, rows: list[dict] | None) -> list[dict] | None:
    """Store one revision's parse, evicting the oldest insertion past the bound."""
    _ROWS_CACHE[key] = rows
    while len(_ROWS_CACHE) > _ROWS_CACHE_MAX:
        _ROWS_CACHE.pop(next(iter(_ROWS_CACHE)))
    return rows

def rows_at(rev: str, rel_path: str, cwd: Path) -> list[dict] | None:
    """The ledger's rows at a revision, or None when the revision/path does not resolve.

    None is meaningful and never an error: for the FIRST commit touching the file, and for
    a commit that introduces it, the parent has no ledger and nothing can have been removed.
    An unparseable line is skipped rather than raised — it cannot carry an identity, so its
    disappearance is reported as the removal it is.

    Memoised through `_ROWS_CACHE` (#510): see that cache's own comment for why the bound is
    two and why it is not the retention #510 removed. A `None` is cached too — "this parent
    has no ledger" is a fact the walk asks about repeatedly at the shallow end of history.
    """
    key = f"{cwd}\x00{rev}\x00{rel_path}"
    if key in _ROWS_CACHE:
        return _ROWS_CACHE[key]
    rc, out, _ = _git("show", f"{rev}:{rel_path}", cwd=cwd)
    if rc != 0:
        return _cache_rows(key, None)
    rows: list[dict] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return _cache_rows(key, rows)


def commit_parents(sha: str, cwd: Path) -> list[str]:
    """The commit's parent shas in git's own order, first parent first.

    An empty list is not an error: a root commit has none, and an unreadable sha is already
    a problem the caller's own read reports. `rev-list --parents` resolves the same way
    `rows_at` does, by revision, so the two reads cannot disagree about which commit they
    describe.
    """
    rc, out, _ = _git("rev-list", "--parents", "-n", "1", sha, cwd=cwd)
    if rc != 0:
        return []
    parts = out.split()
    return parts[1:] if parts else []


def iter_transitions(
    ref: str, rel_path: str, cwd: Path
) -> tuple[Iterator[dict] | None, list[dict] | None, str]:
    """`(transition_stream, entries, error)` — one transition per commit that deleted a line.

    STREAMED, never materialised (#510). The predicate compares identity sets WITHIN one
    transition and never across two, so the walk needs the row lists on both sides of ONE
    commit at a time. Retaining them all buys nothing and costs O(deletion_commits x rows):
    measured on this tree at 2026-10-18, 67 deletion commits x 2 sides x 3,761 rows =
    484,410 live dicts, a 1.17 GiB peak (VmHWM 1202884 kB) that OOM-killed the shared
    `opencrabs-ops` daemon four times in one day -- and `gate_select --paths
    evidence/ledger.jsonl` SELECTS this gate, so every lane's ledger commit ran it.

    The multiplier moves ONE WAY. `history_entries` records 15 deletion commits at
    2026-09-28 and there are 67 now, while the row count only grows; a cost of
    O(deletion_commits x rows) is a cost that gets worse every week, on a 2 GiB cgroup
    shared by every lane in the daemon.

    `entries` is still returned and still CACHED: it is metadata -- four short fields per
    commit -- and the `git log --numstat` walk behind it is the expensive read (measured
    55.7 s at 831 commits), so a second identical walk would cost the run its budget
    (rc=124 against a 200 s cap, 2026-09-28). The ROWS walk is deliberately NOT cached:
    that cache WAS the memory, and there is exactly one consumer pass over the stream.
    """
    entries, err = history_entries(ref, rel_path, cwd)
    if entries is None:
        return None, None, err
    # THE CACHE LIVES FOR EXACTLY ONE WALK. Inside a walk every key is an immutable sha
    # (`entry["sha"]` or its `^`), so the entries cannot go stale; but a caller that passes a
    # MOVABLE ref ("HEAD", "origin/main") would otherwise be served a parse from before a
    # commit it just made -- the synthetic probes commit into a throwaway repo between
    # assertions. Clearing here keeps the within-walk hits (the whole point) and makes a
    # stale read impossible across walks.
    _ROWS_CACHE.clear()
    return _transition_stream(entries, rel_path, cwd), entries, ""

def _transition_stream(
    entries: list[dict], rel_path: str, cwd: Path
) -> Iterator[dict]:
    """Yield one `{sha, subject, before, after, merged_in}` at a time, then forget it.

    Module-level rather than a closure so the loop keeps the indentation it had as
    `build_transitions`' body: a reader comparing this against the pre-#510 version sees the
    SAME comparison with only the RETENTION removed. No predicate moved -- the three shapes,
    the re-mint signature and the merged-in read are byte-for-byte what they were.
    """
    for entry in entries:
        if entry["deleted"] <= 0:
            continue
        after = rows_at(entry["sha"], rel_path, cwd)
        if after is None:
            continue
        before = rows_at(f"{entry['sha']}^", rel_path, cwd)
        # A MERGE's remaining parents are the line that came IN, and
        # `--diff-merges=first-parent` diffs only against the first. Reading them is what
        # lets the predicate tell a RE-MINT from a SHRINK: an identity absent from every
        # merged-in parent was never on the published line, so the re-mint bound
        # (`docs/instruments/ledger.md` §9.1) makes re-minting it
        # free; an identity PRESENT on one of them was published, and a merge that drops it
        # is the removal this gate exists to catch. It is also the only read that sees the
        # inverse case -- a row that lived ONLY on the merged-in line and vanished in the
        # resolution appears in neither `before` nor `after`, so a first-parent diff reports
        # nothing at all (#301). Cost: one `show` per extra parent, and only for commits
        # already carrying a deletion.
        merged_in: list[dict] = []
        for parent in commit_parents(entry["sha"], cwd)[1:]:
            merged_in.extend(rows_at(parent, rel_path, cwd) or [])
        yield {
            "sha": entry["sha"],
            "subject": entry["subject"],
            "before": before or [],
            "after": after,
            "merged_in": merged_in,
        }

def build_transitions(
    ref: str, rel_path: str, cwd: Path
) -> tuple[list[dict] | None, list[dict] | None, str]:
    """`(transitions, entries, error)` — `iter_transitions` MATERIALISED.

    Kept for the PROBES, which drive throwaway synthetic repos of a handful of rows: there
    the whole history is smaller than one live transition, so materialising is free and the
    arms read naturally (`transitions[0]`, a filter by sha). The LIVE path in `main` uses
    `iter_transitions` and must never call this -- materialising the live history is exactly
    the 1.17 GiB peak #510 removed.
    """
    stream, entries, err = iter_transitions(ref, rel_path, cwd)
    if stream is None:
        return None, entries, err
    return list(stream), entries, ""


def _transition(
    sha: str,
    before: list[dict],
    after: list[dict],
    subject: str = "s",
    merged_in: list[dict] | None = None,
) -> dict:
    """A synthetic transition.

    `merged_in` defaults to empty, which is the SINGLE-PARENT shape: an authored commit has
    no merged-in line, so every removal it makes must carry the re-mint signature or be
    sanctioned. That default is deliberate -- a fixture that quietly supplied an empty
    merged-in list for a merge would make every merge removal look like a free re-mint.
    """
    return {
        "sha": sha,
        "subject": subject,
        "before": before,
        "after": after,
        "merged_in": merged_in or [],
    }


def _row(n: int, event: str = "close", actor: str = "hq", subject: str = "#1") -> dict:
    return {
        "n": n,
        "ts": f"2026-09-19T0{n % 10}:00:00Z",
        "event": event,
        "actor": actor,
        "subject": subject,
        "detail": "d",
    }


SHA_A = "a" * 40
SHA_B = "b" * 40


def probe_removal_without_exemption_is_a_problem() -> list[str]:
    """A synthetic history that removes a row identity must turn the gate RED."""
    fails: list[str] = []
    transitions = [_transition(SHA_A, [_row(1), _row(2)], [_row(1)])]
    problems, excused, stale, reconciled, stale_declarations = no_shrink_problems(transitions, {})
    if not problems:
        fails.append("a removed identity raised no problem")
    elif "n=2" not in problems[0]:
        fails.append(f"the problem does not name the removed identity: {problems[0]}")
    if excused or stale or reconciled or stale_declarations:
        fails.append(
            f"unexpected excused/stale/reconciled: {excused} {stale} {reconciled} "
            f"{stale_declarations}"
        )
    return fails


def probe_a_content_change_is_not_a_removal() -> list[str]:
    """The #52 tuple is the predicate: a `detail` edit preserves the identity."""
    fails: list[str] = []
    before = [_row(1), _row(2)]
    after = [_row(1), _row(2)]
    after[1]["detail"] = "corrected by a later row"
    problems, excused, stale, reconciled, stale_declarations = no_shrink_problems(
        [_transition(SHA_A, before, after)], {}
    )
    if problems or excused or stale or reconciled or stale_declarations:
        fails.append(
            f"a detail-only change was reported: {problems} {excused} {stale} {reconciled} "
            f"{stale_declarations}"
        )
    return fails


def probe_an_exempted_removal_is_excused_not_clean() -> list[str]:
    """An exemption excuses loudly — `clean` and `excused` must never be the same output."""
    fails: list[str] = []
    transitions = [_transition(SHA_A, [_row(1), _row(2)], [_row(1)])]
    problems, excused, stale, reconciled, stale_declarations = no_shrink_problems(
        transitions, {SHA_A: {"sha": SHA_A, "reason": "sanctioned by n=318"}}
    )
    if problems:
        fails.append(f"an exempted removal was still a problem: {problems}")
    if len(excused) != 1 or "n=318" not in excused[0]:
        fails.append(f"the exemption was not printed with its proof: {excused}")
    if stale or reconciled or stale_declarations:
        fails.append(
            f"unexpected stale/reconciled: {stale} {reconciled} {stale_declarations}"
        )
    return fails


def probe_a_stale_exemption_is_an_error() -> list[str]:
    """An exemption matching nothing inflates visible debt while excusing nothing."""
    fails: list[str] = []
    problems, _, stale, _, stale_declarations = no_shrink_problems(
        [_transition(SHA_A, [_row(1)], [_row(1)])],
        {SHA_B: {"sha": SHA_B, "reason": "matches nothing"}},
    )
    if problems:
        fails.append(f"an unrelated exemption raised a problem: {problems}")
    if stale != [SHA_B]:
        fails.append(f"the stale exemption was not reported: {stale}")
    if stale_declarations:
        fails.append(
            f"a declaration was reported with no declaration present: {stale_declarations}"
        )
    return fails

def probe_a_declared_reconciliation_is_reconciled_not_clean() -> list[str]:
    """#298's leg: a declared identity accounts for a removal, LOUDLY and separately.

    The declaration names the identity the walk observed removed, so the removal is
    accounted for — and it must be printed as `reconciled`, never folded into `clean`
    (a silent pass) or into `excused` (a different accounting path, #47 clause 4).
    """
    fails: list[str] = []
    before = [_row(1), _row(2)]
    after = [_row(1)]
    declared = {identity_of(_row(2))}
    problems, excused, stale, reconciled, stale_declarations = no_shrink_problems(
        [_transition(SHA_A, before, after)], {}, declared
    )
    if problems:
        fails.append(f"a declared reconciliation was still a problem: {problems}")
    if excused:
        fails.append(f"a reconciliation was reported as an exemption: {excused}")
    if len(reconciled) != 1 or "n=2" not in reconciled[0]:
        fails.append(
            f"the reconciliation did not name the identity it accounted for: {reconciled}"
        )
    if stale or stale_declarations:
        fails.append(f"a matched declaration read as stale: {stale} {stale_declarations}")
    return fails

def probe_a_reconciliation_for_a_MERGE_removal_is_not_stale() -> list[str]:
    """#301's second harm, and the one that made the blindness loud in the wrong direction.

    The issue states it exactly: "a reconciliation row naming an identity removed by a merge
    would be matched against a walk that never saw the removal, so the row reads as a STALE
    declaration and the gate REDS ON A TRUE STATEMENT". Before the merge read, the walker's
    population excluded the commit, `matched_declarations` never received the identity, and
    the reconciliation came back as stale debt. The honest row was punished for the
    instrument's blindness, which is the failure mode a bound stated in prose cannot fix.

    So this arm drives a MERGE transition whose removal is on the merged-in line, with the
    identity declared. It must read RECONCILED, and `stale_declarations` must stay empty.
    """
    fails: list[str] = []
    before = [_row(1), _row(2)]
    merged_in = [_row(1), _row(2), _row(3)]
    after = [_row(1), _row(3)]
    declared = {identity_of(_row(2))}
    problems, excused, stale, reconciled, stale_declarations = no_shrink_problems(
        [_transition(SHA_A, before, after, merged_in=merged_in)], {}, declared
    )
    if problems:
        fails.append(f"a declared merge removal was still a problem: {problems}")
    if stale_declarations:
        fails.append(
            "a reconciliation naming a TRUE merge removal read as STALE, which is the "
            f"exact harm #301 filed: {stale_declarations}"
        )
    if len(reconciled) != 1 or "n=2" not in reconciled[0]:
        fails.append(f"the reconciliation did not name the merge removal: {reconciled}")
    if stale:
        fails.append(f"a matched exemption read as stale: {stale}")
    if excused:
        fails.append(f"a declared removal was reported as an exemption: {excused}")
    return fails


def probe_an_undeclared_removal_beside_a_declared_one_is_still_a_problem() -> list[str]:
    """A declaration excuses ONLY the identities it names — never the commit it rides on.

    This is the arm that keeps the leg from becoming a blanket: if one declared identity
    silenced a commit that removed three, the mechanism would be a second exemption wearing
    a different name.
    """
    fails: list[str] = []
    before = [_row(1), _row(2), _row(3)]
    after = [_row(1)]
    declared = {identity_of(_row(2))}
    problems, _, _, reconciled, stale_declarations = no_shrink_problems(
        [_transition(SHA_A, before, after)], {}, declared
    )
    if len(problems) != 1:
        fails.append(f"the undeclared remainder was not reported: {problems}")
    elif "n=3" not in problems[0]:
        fails.append(f"the problem does not name the UNDECLARED identity: {problems[0]}")
    elif "n=2" in problems[0]:
        fails.append(f"the declared identity was reported as undeclared: {problems[0]}")
    if len(reconciled) != 1:
        fails.append(f"the declared identity was not printed as reconciled: {reconciled}")
    if stale_declarations:
        fails.append(f"a matched declaration read as stale: {stale_declarations}")
    return fails

def probe_a_declaration_for_a_removal_that_did_not_happen_is_an_error() -> list[str]:
    """A declaration naming an identity no transition removed is a FALSE RECORD, not silence.

    A stale exemption inflates visible debt; a stale declaration claims a reconciliation
    that never happened, which is worse — it reads as an accounted removal on a surface
    where nothing was accounted for.
    """
    fails: list[str] = []
    declared = {identity_of(_row(9))}
    problems, _, _, reconciled, stale_declarations = no_shrink_problems(
        [_transition(SHA_A, [_row(1)], [_row(1)])], {}, declared
    )
    if problems:
        fails.append(f"an unrelated declaration raised a problem: {problems}")
    if reconciled:
        fails.append(f"a declaration matching nothing was printed as reconciled: {reconciled}")
    if len(stale_declarations) != 1 or stale_declarations[0][0] != 9:
        fails.append(f"the stale declaration was not reported: {stale_declarations}")
    return fails

def probe_the_reader_anchors_and_rejects_malformed_declarations() -> list[str]:
    """`load_reconciliations`: an anchored line parses; a mid-sentence mention does not.

    The anchor is the whole mechanism — a record that any prose mentioning the word can
    impersonate is not a record — and a malformed declaration must be a PROBLEM, never a
    quiet read of zero declarations.
    """
    fails: list[str] = []
    good = _row(5)
    good["detail"] = (
        "RECONCILIATION #1 — prose above the line.\n"
        'reconciles: {"removed": [{"n": 7, "ts": "2026-01-01T00:00:00Z", "event": "run", '
        '"actor": "hq", "subject": "#1"}]}\n'
    )
    declared, surviving, problems = load_reconciliations([good])
    if problems:
        fails.append(f"a well-formed declaration was reported: {problems}")
    if len(declared) != 1 or (7, "2026-01-01T00:00:00Z", "run", "hq", "#1") not in declared:
        fails.append(f"the anchored declaration was not read: {declared}")

    # A mention INSIDE a sentence must not satisfy the anchor.
    mention = _row(6)
    mention["detail"] = (
        'the row says reconciles: {"removed": [{"n": 7, "ts": "2026-01-01T00:00:00Z", '
        '"event": "run", "actor": "hq", "subject": "#1"}]} and then continues.'
    )
    declared, surviving, problems = load_reconciliations([mention])
    if declared or problems:
        fails.append(f"a mid-sentence mention was read as a declaration: {declared} {problems}")

    # Malformed JSON, an absent `removed` list, an empty list, an identity missing four of
    # its five fields, a `surviving` that is not a list, a `surviving` entry that is not an
    # object, and a `surviving` identity missing four of its five fields are all problems.
    for detail, label in (
        ('reconciles: {"removed": [}', "unparseable JSON"),
        ('reconciles: {"disposition": "no removed key"}', "no 'removed' list"),
        ('reconciles: {"removed": []}', "an empty 'removed' list"),
        ('reconciles: {"removed": [{"n": 7}]}', "an identity missing four of its five fields"),
        ('reconciles: {"removed": [{"n": 7, "ts": "t", "event": "run", "actor": "hq", '
         '"subject": "#1"}], "surviving": 5}',
         "a 'surviving' value that is not a list"),
        ('reconciles: {"removed": [{"n": 7, "ts": "t", "event": "run", "actor": "hq", '
         '"subject": "#1"}], "surviving": ["n=8"]}',
         "a surviving entry that is not an object"),
        ('reconciles: {"removed": [{"n": 7, "ts": "t", "event": "run", "actor": "hq", '
         '"subject": "#1"}], "surviving": [{"n": 8}]}',
         "a surviving identity missing four of its five fields"),
    ):
        bad = _row(8)
        bad["detail"] = detail
        declared, surviving, problems = load_reconciliations([bad])
        if declared or surviving:
            fails.append(f"{label} was read as a declaration: {declared} {surviving}")
        if not problems:
            fails.append(f"{label} was not reported as a problem")
    return fails

def probe_a_reconciliation_whose_surviving_identity_does_not_exist_is_an_error() -> list[str]:
    """`surviving_problems`: the declaration's claim about the tip must be TRUE.

    A `surviving` list with no reader is a field that can only lie — the four-shapes
    family's shape (d). Here the declaration says three rows survived; the tip carries
    only two, so the third is a claim about a state the ledger is not in and MUST be a
    problem rather than a quietly-accepted decoration.
    """
    fails: list[str] = []
    tip = [_row(1), _row(2)]
    present = {identity_of(_row(2))}
    absent = {identity_of(_row(9))}
    problems = surviving_problems(present, tip)
    if problems:
        fails.append(f"a surviving identity that IS at the tip raised a problem: {problems}")
    problems = surviving_problems(absent, tip)
    if not problems:
        fails.append("a surviving identity absent from the tip was not reported")
    if not any("n=9" in line for line in problems):
        fails.append(f"the problem does not name the absent identity: {problems}")
    # The control: an empty declaration raises nothing, so the arm is not blanket-RED.
    if surviving_problems(set(), tip):
        fails.append("an empty surviving set raised a problem — the arm is blanket")
    return fails

def probe_a_stale_reconciliation_is_an_error() -> list[str]:
    """A declaration naming a removal that never happened is a FALSE RECORD (#112, P29).

    The same property as the older `..._a_declaration_for_a_removal_that_did_not_happen_...`
    probe, asserted here under the reconciliation vocabulary the law uses: `stale_declarations`
    must carry the identity, `problems` must stay empty for the unrelated declaration, and
    `reconciled` must not print it — a false record is never a reconciled one.
    """
    fails: list[str] = []
    declared = {identity_of(_row(9))}
    problems, _, _, reconciled, stale_declarations = no_shrink_problems(
        [_transition(SHA_A, [_row(1)], [_row(1)])], {}, declared
    )
    if problems:
        fails.append(f"an unrelated declaration raised a problem: {problems}")
    if reconciled:
        fails.append(f"a stale declaration was printed as reconciled: {reconciled}")
    if len(stale_declarations) != 1 or stale_declarations[0][0] != 9:
        fails.append(f"the stale declaration was not reported: {stale_declarations}")
    return fails


def _synthetic_repo_with_a_deletion(root: Path) -> tuple[Path, str, str]:
    """A throwaway repo whose history contains exactly one ledger deletion.

    `(cwd, ref, rel_path)`. The walker takes its repo as a PARAMETER -- `cwd` is the
    seam -- so proving it needs no refactor of the walker, only an input it can be
    pointed at (#169, ruling n=1128).
    """
    import subprocess

    rel = LEDGER_PATH
    ledger = root / rel
    ledger.parent.mkdir(parents=True, exist_ok=True)

    def git(*args: str) -> None:
        proc = subprocess.run(
            ["git", "-c", "user.email=probe@example.invalid", "-c", "user.name=probe",
             "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *args],
            cwd=root, capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")

    git("init", "-q")
    ledger.write_text(
        '{"n": 1, "event": "genesis", "ts": "2026-01-01T00:00:00Z"}\n'
        '{"n": 2, "event": "claim", "ts": "2026-01-01T00:01:00Z"}\n',
        encoding="utf-8",
    )
    git("add", "-A")
    git("commit", "-q", "-m", "add two ledger rows")
    # The DELETION: row 2 leaves the file, which is the transition the walker exists
    # to report and the row identity the no-shrink invariant protects.
    ledger.write_text('{"n": 1, "event": "genesis", "ts": "2026-01-01T00:00:00Z"}\n',
                      encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "remove ledger row 2")
    return root, "HEAD", rel


def probe_the_walker_DETECTS_a_deletion_when_one_is_present() -> list[str]:
    """The walker's OWN property, proven at ANY live-history depth (#169, ruling n=1128).

    THE ASSERTION MOVED, it did not disappear. It used to read "the live history
    contains a deletion", which is a fact about THIS repo: a bootstrapped factory has
    one ledger commit and no deletions, so the gate shipped to every factory RED from
    birth -- a gate that cannot pass where it is copied teaches lanes to ignore RED
    (the #139 class). Direction 1 (SKIP when the history carries no deletion) was
    REFUSED, because a probe that skips on a shallow history converts a false RED into
    a false CLEAN: a predicate that examined nothing has reported nothing, not HOLDS
    (SKILL.md section 8, the #170 class one surface over).

    So the subject is now the WALKER rather than the history: seed a deletion in a
    throwaway repo and assert the walker reports the transition. That holds at any
    live-history depth, including one commit, and it is strictly stronger than the old
    form -- the old one could pass on a history whose deletion the walker MISSED.
    """
    fails: list[str] = []
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        try:
            cwd, ref, rel = _synthetic_repo_with_a_deletion(Path(tmp))
        except RuntimeError as exc:
            fails.append(f"the synthetic repo could not be built: {exc}")
            return fails
        transitions, entries, err = build_transitions(ref, rel, cwd)
        if transitions is None:
            fails.append(f"the synthetic walk failed: {err}")
            return fails
        if not entries:
            fails.append("the synthetic walk found zero commits touching the ledger")
            return fails
        if not transitions:
            fails.append(
                "the walker MISSED a seeded deletion -- it reported no transition in a "
                "history that contains exactly one"
            )
            return fails
        first = transitions[0]
        if len(first["after"]) >= len(first["before"]):
            fails.append(
                f"the transition does not show a row leaving: before={len(first['before'])} "
                f"after={len(first['after'])}"
            )
    return fails

def _synthetic_repo_with_a_MERGE_deletion(root: Path) -> tuple[Path, str, str]:
    """A throwaway repo whose ledger deletion happens in a MERGE RESOLUTION (#301).

    The plain-deletion fixture above cannot reach this class: its removal is an authored
    commit, and `git log --numstat` reports those. A MERGE commit gets no diffstat at all
    from the plain form, so a row dropped by a conflict resolution left `deleted` at 0 and
    `build_transitions` skipped the commit before any before/after comparison -- the
    walker was blind to the one commit class where a resolution can delete an identity
    that no authored commit deleted.
    """
    import subprocess

    rel = LEDGER_PATH
    ledger = root / rel
    ledger.parent.mkdir(parents=True, exist_ok=True)

    def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
        proc = subprocess.run(
            ["git", "-c", "user.email=probe@example.invalid", "-c", "user.name=probe",
             "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *args],
            cwd=root, capture_output=True, text=True,
        )
        if check and proc.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
        return proc

    def rows(*ns: int) -> str:
        return "".join(
            f'{{"n": {n}, "event": "close", "ts": "2026-01-01T00:0{n}:00Z"}}\n' for n in ns
        )

    git("init", "-q")
    ledger.write_text(rows(1, 2, 3), encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "base three rows")

    git("checkout", "-q", "-b", "side")
    ledger.write_text(rows(1, 2, 3, 4), encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "side adds row 4")

    git("checkout", "-q", "main")
    ledger.write_text(rows(1, 2, 3, 5), encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "main adds row 5")

    # Both sides append at the same tail, so the merge conflicts. The RESOLUTION drops
    # row 2 -- that is the only place row 2 leaves the file, and it lives in no authored
    # commit's diff.
    git("merge", "--no-ff", "side", "-m", "merge side", check=False)
    ledger.write_text(rows(1, 3, 4, 5), encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "merge resolution drops row 2")
    return root, "HEAD", rel

def probe_a_MERGE_resolution_that_removes_a_row_is_DETECTED() -> list[str]:
    """#301: a removal performed by a MERGE RESOLUTION must be seen by the walker.

    Bites BOTH ways by construction. Leg 1 is the optimisation's own gate: the merge
    commit must appear in `entries` carrying `deleted > 0`. With the pre-#301 plain
    `git log --numstat` it carried 0 and `build_transitions` skipped it, so this leg
    fails on the old code with no help from any other arm. Leg 2 is the predicate: a
    transition for that merge whose `before` holds n=2 and whose `after` does not -- a
    walker that counted deletions but read the wrong side would still be caught.
    """
    fails: list[str] = []
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        try:
            cwd, ref, rel = _synthetic_repo_with_a_MERGE_deletion(Path(tmp))
        except RuntimeError as exc:
            fails.append(f"the synthetic merge repo could not be built: {exc}")
            return fails
        transitions, entries, err = build_transitions(ref, rel, cwd)
        if transitions is None or entries is None:
            fails.append(f"the synthetic merge walk failed: {err}")
            return fails

        merge = [e for e in entries if "merge resolution" in e["subject"]]
        if len(merge) != 1:
            fails.append(
                f"the merge commit was not read exactly once: {len(merge)} entry(s) in "
                f"{[e['subject'] for e in entries]}"
            )
            return fails
        if merge[0]["deleted"] <= 0:
            fails.append(
                "the merge resolution reports deleted=0 -- the diffstat is missing, so "
                "the row removal was never compared"
            )
            return fails

        hit = [t for t in transitions if t["sha"] == merge[0]["sha"]]
        if not hit:
            fails.append(
                "the merge resolution produced no transition: "
                f"{[t['subject'] for t in transitions]}"
            )
            return fails
        before = {r.get("n") for r in hit[0]["before"]}
        after = {r.get("n") for r in hit[0]["after"]}
        if 2 not in before:
            fails.append(f"the transition's before-side lacks the removed row: {before}")
        if 2 in after:
            fails.append(f"the transition's after-side still holds row 2: {after}")
    return fails


def probe_a_MERGE_that_only_REMINTS_does_not_raise_the_alarm() -> list[str]:
    """#301's second acceptance arm: a legal re-mint must NOT be reported as a shrink.

    The #301 ruling is explicit that "a guard that fires on a legal re-mint is worse than
    none, because the lane learns to ignore it". This probe is that arm, and it is built as
    a PAIR so the same fixture shape yields opposite verdicts on the one field that decides
    it -- whether the removed identity was on the merged-in line:

      * arm A: the removed row is ABSENT from every merged-in parent -> it never reached the
        published line, so the re-mint bound (`docs/instruments/ledger.md` §9.1) makes the
        re-mint free. The gate must be SILENT on it, and
        must PRINT that a re-mint happened (a silent excuse is indistinguishable from no
        removal at all).
      * arm B: the SAME removal with the identity PRESENT on a merged-in parent -> it was
        published and the resolution dropped it. The gate must RED.

    A probe with only arm A would pass on a walker that reports nothing; only the pair
    shows the discriminator is the merged-in line and not some incidental field.
    """
    fails: list[str] = []
    removed = _row(2, event="claim", actor="worker", subject="#488")
    successor = _row(5, event="claim", actor="worker", subject="#488")
    kept = _row(1, event="claim", actor="worker", subject="#487")

    # arm A -- never published, re-minted above the line
    legal = [
        _transition(
            SHA_A,
            [kept, removed],
            [kept, successor],
            subject="merge: reconcile origin/main — re-mint the claim",
            merged_in=[kept],
        )
    ]
    problems, excused, stale, reconciled, stale_declarations = no_shrink_problems(legal, {})
    if problems:
        fails.append(f"a legal re-mint was reported as a shrink: {problems}")
    if stale or reconciled or stale_declarations:
        fails.append(
            f"unexpected stale/reconciled on a clean re-mint: {stale} {reconciled} "
            f"{stale_declarations}"
        )
    if not any("re-mint" in line and "n=2" in line for line in excused):
        fails.append(
            "the re-mint was not PRINTED -- an excused removal must be visible, or it "
            f"reads exactly like a clean walk: {excused}"
        )

    # arm B -- the identical removal, but the identity WAS on the merged-in line
    illegal = [
        _transition(
            SHA_A,
            [kept, removed],
            [kept, successor],
            subject="merge resolution drops a published claim",
            merged_in=[kept, removed],
        )
    ]
    problems_b, excused_b, _, _, _ = no_shrink_problems(illegal, {})
    if not problems_b:
        fails.append(
            "a merge that dropped a row PRESENT on the merged-in line raised no problem -- "
            "the discriminator is not reading the merged-in line"
        )
    elif "n=2" not in problems_b[0]:
        fails.append(f"the problem does not name the dropped identity: {problems_b[0]}")
    elif "published on a merged-in line" not in problems_b[0]:
        fails.append(f"the problem does not say WHY it is a shrink: {problems_b[0]}")
    return fails


def probe_a_removal_only_on_the_MERGED_IN_line_is_DETECTED() -> list[str]:
    """The inverse #301 case: a row that existed ONLY on the merged-in line.

    `removed_identities` compares the first parent against the merge, so a row that came in
    from the other branch and vanished in the resolution appears in NEITHER side and the
    ordinary predicate cannot see it. A first-parent diff reports nothing at all for it. It
    is a published row disappearing, which is the whole predicate of this gate, so it gets
    its own leg.
    """
    fails: list[str] = []
    kept = _row(1, event="claim", actor="worker", subject="#487")
    in_only = _row(9, event="close", actor="triage", subject="#499")
    transitions = [
        _transition(
            SHA_A,
            [kept],
            [kept],
            subject="merge: reconcile origin/main — resolution loses a row",
            merged_in=[kept, in_only],
        )
    ]
    problems, _, _, _, _ = no_shrink_problems(transitions, {})
    if not problems:
        fails.append(
            "a published row present only on the merged-in line vanished with no problem "
            "raised -- the inverse leg is not reading the merged-in line"
        )
    elif "n=9" not in problems[0]:
        fails.append(f"the problem does not name the lost identity: {problems[0]}")
    return fails


def probe_a_SINGLE_PARENT_removal_needs_the_re_mint_signature() -> list[str]:
    """Shape 3 of #301: with no merged-in line, absence proves nothing.

    An authored commit has no other parent to compare against, so "absent from every
    merged-in line" is vacuously true and would excuse ANY deletion. The signature is what
    carries the law there: the same event/actor/subject must reappear at a HIGHER `n`. Both
    arms use one fixture shape and differ only in whether that successor exists, so the
    probe shows the signature -- not the commit's subject, not its parent count -- is what
    decides the verdict.
    """
    fails: list[str] = []
    removed = _row(2, event="claim", actor="worker", subject="#488")
    kept = _row(1, event="claim", actor="worker", subject="#487")

    # arm A -- the successor is present, so this is a re-mint on an unpublished line
    legal = [_transition(SHA_A, [kept, removed], [kept, _row(5, event="claim",
                                                              actor="worker",
                                                              subject="#488")])]
    problems, excused, _, _, _ = no_shrink_problems(legal, {})
    if problems:
        fails.append(f"a single-parent re-mint WITH a successor was called a shrink: {problems}")
    if not any("re-mint" in line and "n=2" in line for line in excused):
        fails.append(f"the single-parent re-mint was not printed: {excused}")

    # arm B -- the identical removal with NO successor: a bare authored deletion
    illegal = [_transition(SHA_A, [kept, removed], [kept])]
    problems_b, _, _, _, _ = no_shrink_problems(illegal, {})
    if not problems_b:
        fails.append(
            "a single-parent deletion with NO re-mint signature passed -- the signature "
            "leg is not being read, and every authored deletion would be excused"
        )
    elif "no re-mint signature" not in problems_b[0]:
        fails.append(f"the problem does not name the missing signature: {problems_b[0]}")

    # arm C -- the signature must move UP: a same-subject row at a LOWER n is not a re-mint
    downward = [_transition(SHA_A, [_row(9, event="claim", actor="worker", subject="#488")],
                            [_row(4, event="claim", actor="worker", subject="#488")])]
    problems_c, excused_c, _, _, _ = no_shrink_problems(downward, {})
    if not problems_c:
        fails.append(
            "a removal whose only same-act row sits at a LOWER n was excused as a re-mint "
            "-- a re-mint carries the number up or holds it, and moving DOWN is a different "
            "row wearing a published number"
        )
    return fails

def probe_a_SAME_n_re_stamp_is_a_re_mint_but_a_published_one_still_bites() -> list[str]:
    """#569: the ts-only re-stamp, and the arm that keeps it from being a blanket excuse.

    The shape is the live one. `e446fa9d` (2026-10-26T08:35:50Z, single parent `785dcc49`)
    re-stamped four unpublished rows before pushing them: 4307 rows either side, no `n`
    removed anywhere, all four identities re-present at the SAME `n` with the same
    `(event, actor, subject)` and only `ts` moved. The gate called that a shrink, because
    `_remint_successor` demanded `r["n"] > n` and a re-stamp does not move the number at all.

    Three arms, because a probe that only shows the widening cannot show it still bites:

      * arm A -- single parent, same `n`, `ts` moved: a RE-MINT. The gate must be SILENT and
        must PRINT it. This arm is the regression test for the `>=` half of #569's fix: with
        the old `>`, `problems` is non-empty and this arm fails.
      * arm B -- the identical successor, but the removed identity is PRESENT on a merged-in
        line, i.e. it was PUBLISHED: the gate must RED. This is the discriminator that stops
        a same-`n` re-stamp from becoming a blanket excuse -- publication is judged first,
        and a signature can never outrank it.
      * arm C -- single parent, same `n`, and the only same-act row in `after` carries a
        DIFFERENT subject: no signature, so a real authored deletion must still RED.
    """
    fails: list[str] = []

    def stamped(n: int, ts: str, event: str, actor: str, subject: str) -> dict:
        row = _row(n, event=event, actor=actor, subject=subject)
        row["ts"] = ts
        return row

    kept = _row(1, event="claim", actor="worker", subject="#487")
    before_a = [
        kept,
        stamped(4304, "2026-10-26T08:09:24Z", "ruling", "hq", "#562"),
        stamped(4307, "2026-10-26T08:15:58Z", "dispatch", "triage", "#564"),
    ]
    restamped = [
        kept,
        stamped(4304, "2026-10-26T08:34:31Z", "ruling", "hq", "#562"),
        stamped(4307, "2026-10-26T08:34:31Z", "dispatch", "triage", "#564"),
    ]

    # arm A -- the live shape: a single-parent ts-only re-stamp of UNPUBLISHED rows
    problems, excused, stale, reconciled, stale_declarations = no_shrink_problems(
        [_transition(SHA_A, before_a, restamped, subject="re-mint four unpublished rows")], {}
    )
    if problems:
        fails.append(
            "a single-parent ts-only re-stamp at the SAME n was charged as a shrink -- the "
            f"re-mint signature is not accepting a same-`n` successor: {problems}"
        )
    if not any("re-mint" in line and "n=4304" in line for line in excused):
        fails.append(
            f"the same-`n` re-mint was not PRINTED as a re-mint: excused={excused}"
        )
    if stale or reconciled or stale_declarations:
        fails.append(
            f"unexpected stale/reconciled on a lawful re-stamp: {stale} {reconciled} "
            f"{stale_declarations}"
        )

    # arm B -- the SAME successor, but the identity was published on the merged-in line
    problems_b, _, _, _, _ = no_shrink_problems(
        [
            _transition(
                SHA_B,
                before_a,
                restamped,
                subject="merge: resolution re-stamps a published row",
                merged_in=before_a,
            )
        ],
        {},
    )
    if not problems_b:
        fails.append(
            "a same-`n` re-stamp of an identity PRESENT on the merged-in line was excused -- "
            "publication must be judged before the signature, or the signature becomes a "
            "blanket excuse for any published row whose act reappears"
        )

    # arm C -- no signature: the same act is not in `after` at all
    problems_c, _, _, _, _ = no_shrink_problems(
        [
            _transition(
                SHA_A,
                before_a,
                [kept, stamped(4304, "2026-10-26T08:34:31Z", "ruling", "hq", "#999")],
                subject="authored deletion of an unpublished row",
            )
        ],
        {},
    )
    if not problems_c:
        fails.append(
            "a removal whose only same-act row in `after` carries a DIFFERENT subject was "
            "excused as a re-mint -- the signature is being matched on `n` alone"
        )
    return fails


def report_the_live_history_walk() -> str:
    """The live-history walk, REPORTED and never asserted (#169, ruling n=1128).

    It is kept because it is the only arm that reads THIS repo, and a walker that works
    on a synthetic repo and silently returns nothing here is worth seeing. It is not
    asserted because its depth is a property of the tree, not of the walker: a factory
    that has just bootstrapped has one commit and no deletions, which is the expected
    consequence of bootstrapping and not a defect. The two HARD arms are retained --
    a walk that ERRORS and a walk that finds ZERO commits are both defects of the
    tooling or the tree, and neither is a statement about history depth.

    It reads the walk's METADATA (`history_entries`), never the transitions (#510). The
    figures it prints are the population and its deletion-carrying share, both of which
    `entries` already carries; building transitions to count them made this arm a SECOND
    consumer, and a second consumer is what the retired transitions cache existed to serve
    -- at the cost of the whole history's row lists. The rows walk itself is still exercised
    on live history, by `main`'s single streaming pass, so nothing this arm used to prove
    has stopped being proved; only the retention is gone.
    """
    cwd = repo_toplevel() or REPO
    ref = PRIMARY_REF if resolvable(PRIMARY_REF, cwd) else FALLBACK_REF
    entries, err = history_entries(ref, LEDGER_PATH, cwd)
    if entries is None:
        return f"FAIL the live walk errored: {err}"
    if not entries:
        return "FAIL the live walk found zero commits touching the ledger"
    with_deletions = sum(1 for e in entries if e["deleted"] > 0)
    if not with_deletions:
        return (f"REPORTED {len(entries)} live commit(s) touch the ledger and none "
                f"carries a deletion -- shallow history, not a defect")
    return (f"REPORTED {len(entries)} live commit(s) touch the ledger, "
            f"{with_deletions} carry a deletion")


def main() -> int:
    print("ledger no-shrink — a pushed row is never removed (P11, issue #58)")
    fails: list[str] = []
    print("  synthetic probes")
    probes = (
        probe_removal_without_exemption_is_a_problem,
        probe_a_content_change_is_not_a_removal,
        probe_an_exempted_removal_is_excused_not_clean,
        probe_a_stale_exemption_is_an_error,
        probe_a_declared_reconciliation_is_reconciled_not_clean,
        probe_a_reconciliation_for_a_MERGE_removal_is_not_stale,
        probe_an_undeclared_removal_beside_a_declared_one_is_still_a_problem,
        probe_a_declaration_for_a_removal_that_did_not_happen_is_an_error,
        probe_a_stale_reconciliation_is_an_error,
        probe_a_reconciliation_whose_surviving_identity_does_not_exist_is_an_error,
        probe_the_reader_anchors_and_rejects_malformed_declarations,
        probe_the_walker_DETECTS_a_deletion_when_one_is_present,
        probe_a_MERGE_resolution_that_removes_a_row_is_DETECTED,
        probe_a_MERGE_that_only_REMINTS_does_not_raise_the_alarm,
        probe_a_removal_only_on_the_MERGED_IN_line_is_DETECTED,
        probe_a_SINGLE_PARENT_removal_needs_the_re_mint_signature,
        probe_a_SAME_n_re_stamp_is_a_re_mint_but_a_published_one_still_bites,
    )
    # The probe set is PRINTED, by count and by name, so a probe deleted from this tuple is
    # VISIBLE: a run that silently stops exercising a leg reads exactly like one that
    # exercises it and passes (#112, P29 -- a gate's population is part of its verdict).
    print(f"  examined {len(probes)} probe(s): " + ", ".join(p.__name__ for p in probes))
    for probe in probes:
        for line in probe():
            fails.append(f"{probe.__name__}: {line}")

    live = report_the_live_history_walk()
    if live.startswith("FAIL"):
        fails.append(f"report_the_live_history_walk: {live[5:].strip()}")
    else:
        print(f"  {live}")

    cwd = repo_toplevel() or REPO
    exemptions, problems = load_exemptions(cwd / EXEMPTIONS_PATH)

    ref = PRIMARY_REF if resolvable(PRIMARY_REF, cwd) else FALLBACK_REF
    if ref != PRIMARY_REF:
        print(f"  note: {PRIMARY_REF} is unreadable here — degrading to {FALLBACK_REF}")

    stream, entries, err = iter_transitions(ref, LEDGER_PATH, cwd)
    counts = {"transitions": 0, "content_only": 0}

    def _counted(rows: Iterator[dict]) -> Iterator[dict]:
        """Pass the stream through, counting the two figures the summary line prints.

        The counts are taken HERE rather than from a materialised list (#510): the summary
        needs the population's SIZE and its content-only share, never the transitions
        themselves, and retaining them to print a number is what made this gate a gigabyte.
        `removed_identities` is a pure set difference, so counting adds no retained memory --
        the two identity sets are built, compared and dropped inside the loop.
        """
        for transition in rows:
            counts["transitions"] += 1
            if not removed_identities(transition["before"], transition["after"]):
                counts["content_only"] += 1
            yield transition

    excused: list[str] = []
    reconciled: list[str] = []
    stale: list[str] = []
    stale_declarations: list[tuple] = []
    if stream is None:
        problems.append(f"could not read {LEDGER_PATH}'s committed history from {ref}: {err}")
    elif not entries:
        problems.append(
            f"no commit touches {LEDGER_PATH} on {ref} — a gate examining zero commits is "
            f"indistinguishable from one that examines zero commits and passes"
        )
    else:
        # The reconciliation declarations are read from the ledger's OWN rows at the ref
        # under examination — the ledger is the store, so a reconciliation needs no second
        # factory-data file and no sha to key on. The identity IS the key.
        tip_rows = rows_at(ref, LEDGER_PATH, cwd) or []
        declared, surviving, decl_problems = load_reconciliations(tip_rows)
        problems.extend(decl_problems)
        problems.extend(surviving_problems(surviving, tip_rows))
        # DROP THE TIP SIDE BEFORE THE WALK (#510). `surviving` holds identity tuples, not
        # rows, so nothing below reads `tip_rows` again. The local name is dropped here even
        # though `_ROWS_CACHE` may still hold the parse: that cache is bounded at two entries
        # and the walk evicts this one within its first two reads, so the tip side costs at
        # most one slot rather than being held for the whole walk.
        del tip_rows
        gate_problems, excused, stale, reconciled, stale_declarations = no_shrink_problems(
            _counted(stream), exemptions, declared
        )
        problems.extend(gate_problems)
        for line in excused:
            print(f"  excused: {line}")
        for line in reconciled:
            print(f"  reconciled: {line}")
        for sha in stale:
            problems.append(
                f"exemption {sha} matches no row removal on {ref} — a stale exemption "
                f"excuses nothing; remove it or correct the sha"
            )
        for key in stale_declarations:
            problems.append(
                f"a reconciliation row declares n={key[0]} ({key[2]} {key[3]} {key[4]}) "
                f"removed, but no commit on {ref} removes that identity — a false record "
                f"accounts for nothing; correct the declaration or remove it"
            )

    if stream is not None and entries:
        print(
            f"ledger no-shrink: examined {len(entries)} commit(s) on {ref}, "
            f"{counts['transitions']} carrying deletions, "
            f"{counts['content_only']} of them content-only"
        )

    if problems or fails:
        for line in problems:
            print(f"  FAIL {line}")
        for line in fails:
            print(f"  FAIL {line}")
        print(f"ledger no-shrink FAILED: {len(problems) + len(fails)} problem(s)")
        return 1

    if excused or reconciled:
        parts: list[str] = []
        if excused:
            parts.append(f"{len(excused)} exempted")
        if reconciled:
            parts.append(f"{len(reconciled)} reconciled")
        print(
            f"ledger no-shrink: accounted — {', '.join(parts)} removal(s) on {ref}; "
            f"this is a visible accounting, not a clean run"
        )
    else:
        print("ledger no-shrink: clean — no commit removes a row identity")
    return 0


if __name__ == "__main__":
    sys.exit(main())
