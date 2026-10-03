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


def no_shrink_problems(
    transitions: list[dict],
    exemptions: dict[str, dict],
    declared: set[tuple] | frozenset = frozenset(),
) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    """Return `(problems, excused, stale, reconciled, stale_declarations)`.

    Each transition is `{"sha", "subject", "before", "after"}` — the row lists at a commit
    and at its parent. Pure, so a synthetic history can drive it: a rule that has only ever
    seen good input has not been shown to reject bad input.

    A removal is accounted for by an EXEMPTION (keyed by the commit's sha) or by a DECLARED
    RECONCILIATION (keyed by the removed identity itself). The two are returned separately
    and printed separately, so `clean`, `excused` and `reconciled` are never the same output.
    `declared` holds the identity tuples a reconciliation row named, and each is matched
    VERBATIM against an identity the walk observed removed.

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
        removed = removed_identities(transition["before"], transition["after"])
        if not removed:
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
        undeclared = [key for key in removed if key not in declared]
        if named:
            reconciled.append(
                f"{sha[:12]} — {len(named)} identity(ies) named by a reconciliation row: "
                + ", ".join(f"n={key[0]} ({key[2]} {key[3]} {key[4]})" for key in named)
            )
        if undeclared and entry is None:
            described = ", ".join(
                f"n={key[0]} ({key[2]} {key[3]} {key[4]})" for key in undeclared
            )
            problems.append(
                f"{sha[:12]} removes {len(undeclared)} row identity(ies) from "
                f"{LEDGER_PATH} without a sanctioning row: {described} "
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


_WALK_CACHE: dict[tuple[str, str, str], tuple] = {}


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
    """
    _key = ("history", ref, rel_path, str(cwd))
    if _key in _WALK_CACHE:
        return _WALK_CACHE[_key]

    rc, out, err = _git(
        "log", "--numstat", "--format=%x01%H%x01%s", ref, "--", rel_path, cwd=cwd
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


def rows_at(rev: str, rel_path: str, cwd: Path) -> list[dict] | None:
    """The ledger's rows at a revision, or None when the revision/path does not resolve.

    None is meaningful and never an error: for the FIRST commit touching the file, and for
    a commit that introduces it, the parent has no ledger and nothing can have been removed.
    An unparseable line is skipped rather than raised — it cannot carry an identity, so its
    disappearance is reported as the removal it is.
    """
    rc, out, _ = _git("show", f"{rev}:{rel_path}", cwd=cwd)
    if rc != 0:
        return None
    rows: list[dict] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def build_transitions(
    ref: str, rel_path: str, cwd: Path
) -> tuple[list[dict] | None, list[dict] | None, str]:
    """`(transitions, entries, error)` — a transition per commit that deleted any line."""
    _key = ("transitions", ref, rel_path, str(cwd))
    if _key in _WALK_CACHE:
        return _WALK_CACHE[_key]

    entries, err = history_entries(ref, rel_path, cwd)
    if entries is None:
        return None, None, err
    transitions: list[dict] = []
    for entry in entries:
        if entry["deleted"] <= 0:
            continue
        after = rows_at(entry["sha"], rel_path, cwd)
        if after is None:
            continue
        before = rows_at(f"{entry['sha']}^", rel_path, cwd)
        transitions.append(
            {
                "sha": entry["sha"],
                "subject": entry["subject"],
                "before": before or [],
                "after": after,
            }
        )
    _WALK_CACHE[("transitions", ref, rel_path, str(cwd))] = (transitions, entries, "")
    return transitions, entries, ""


def _transition(sha: str, before: list[dict], after: list[dict], subject: str = "s") -> dict:
    return {"sha": sha, "subject": subject, "before": before, "after": after}


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


def report_the_live_history_walk() -> str:
    """The live-history walk, REPORTED and never asserted (#169, ruling n=1128).

    It is kept because it is the only arm that reads THIS repo, and a walker that works
    on a synthetic repo and silently returns nothing here is worth seeing. It is not
    asserted because its depth is a property of the tree, not of the walker: a factory
    that has just bootstrapped has one commit and no deletions, which is the expected
    consequence of bootstrapping and not a defect. The two HARD arms are retained --
    a walk that ERRORS and a walk that finds ZERO commits are both defects of the
    tooling or the tree, and neither is a statement about history depth.
    """
    cwd = repo_toplevel() or REPO
    ref = PRIMARY_REF if resolvable(PRIMARY_REF, cwd) else FALLBACK_REF
    transitions, entries, err = build_transitions(ref, LEDGER_PATH, cwd)
    if transitions is None:
        return f"FAIL the live walk errored: {err}"
    if not entries:
        return "FAIL the live walk found zero commits touching the ledger"
    if not transitions:
        return (f"REPORTED {len(entries)} live commit(s) touch the ledger and none "
                f"carries a deletion -- shallow history, not a defect")
    return (f"REPORTED {len(entries)} live commit(s) touch the ledger, "
            f"{len(transitions)} carry a deletion")


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
        probe_an_undeclared_removal_beside_a_declared_one_is_still_a_problem,
        probe_a_declaration_for_a_removal_that_did_not_happen_is_an_error,
        probe_a_stale_reconciliation_is_an_error,
        probe_a_reconciliation_whose_surviving_identity_does_not_exist_is_an_error,
        probe_the_reader_anchors_and_rejects_malformed_declarations,
        probe_the_walker_DETECTS_a_deletion_when_one_is_present,
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

    transitions, entries, err = build_transitions(ref, LEDGER_PATH, cwd)
    excused: list[str] = []
    reconciled: list[str] = []
    stale: list[str] = []
    stale_declarations: list[tuple] = []
    if transitions is None:
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
        gate_problems, excused, stale, reconciled, stale_declarations = no_shrink_problems(
            transitions, exemptions, declared
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

    if transitions is not None and entries:
        print(
            f"ledger no-shrink: examined {len(entries)} commit(s) on {ref}, "
            f"{len(transitions)} carrying deletions, "
            f"{len(transitions) - len([t for t in transitions if removed_identities(t['before'], t['after'])])} "
            f"of them content-only"
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
