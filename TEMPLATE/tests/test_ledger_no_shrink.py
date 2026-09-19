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

**Zero commits examined is a FAILURE, never a pass.** A gate that silently examines nothing
is indistinguishable from a gate that examines nothing and passes. If the walk finds no
commit touching the ledger, this gate FAILS naming what it could not read.

Run:  python3 tests/test_ledger_no_shrink.py
Exit: 0 clean or fully excused, 1 on any unaccounted row removal.
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
    transitions: list[dict], exemptions: dict[str, dict]
) -> tuple[list[str], list[str], list[str]]:
    """Return `(problems, excused, stale)` for a list of revision transitions.

    Each transition is `{"sha", "subject", "before", "after"}` — the row lists at a commit
    and at its parent. Pure, so a synthetic history can drive it: a rule that has only ever
    seen good input has not been shown to reject bad input.

    `problems` names every commit that removes an identity without an exemption; `excused`
    names the exempted ones, so the two are never conflated; `stale` names exemptions that
    matched nothing, because an exemption that silently excuses nothing inflates the count
    of visible debt while weakening the gate.
    """
    problems: list[str] = []
    excused: list[str] = []
    matched: set[str] = set()

    for transition in transitions:
        sha = transition["sha"]
        removed = removed_identities(transition["before"], transition["after"])
        if not removed:
            continue
        described = ", ".join(
            f"n={key[0]} ({key[2]} {key[3]} {key[4]})" for key in removed
        )
        entry = exemptions.get(sha)
        if entry is None:
            problems.append(
                f"{sha[:12]} removes {len(removed)} row identity(ies) from "
                f"{LEDGER_PATH} without a sanctioning row: {described} "
                f"— subject: {transition['subject'][:70]}"
            )
        else:
            matched.add(sha)
            excused.append(f"{sha} — {entry.get('reason', '')}")

    stale = sorted(set(exemptions) - matched)
    return problems, excused, stale


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


def resolvable(ref: str, cwd: Path) -> bool:
    """True when a ref resolves — the `origin/main` -> `HEAD` degradation (clause 4)."""
    rc, out, _ = _git("rev-parse", "--verify", "--quiet", ref, cwd=cwd)
    return rc == 0 and bool(out.strip())


def history_entries(
    ref: str, rel_path: str, cwd: Path
) -> tuple[list[dict] | None, str]:
    """`([{sha, subject, added, deleted}], error)` for commits touching `rel_path`.

    The deletion counts are a stated OPTIMISATION, not the predicate: a row occupies at
    least one line and any change to that line counts as a deletion, so a commit with zero
    deleted lines cannot remove a row identity and needs no set comparison. The live
    history bears it out — 260 commits touch the ledger, only 8 carry deletions, and the
    full comparison runs over those 8 rather than all 260.
    """
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
    problems, excused, stale = no_shrink_problems(transitions, {})
    if not problems:
        fails.append("a removed identity raised no problem")
    elif "n=2" not in problems[0]:
        fails.append(f"the problem does not name the removed identity: {problems[0]}")
    if excused or stale:
        fails.append(f"unexpected excused/stale: {excused} {stale}")
    return fails


def probe_a_content_change_is_not_a_removal() -> list[str]:
    """The #52 tuple is the predicate: a `detail` edit preserves the identity."""
    fails: list[str] = []
    before = [_row(1), _row(2)]
    after = [_row(1), _row(2)]
    after[1]["detail"] = "corrected by a later row"
    problems, excused, stale = no_shrink_problems([_transition(SHA_A, before, after)], {})
    if problems or excused or stale:
        fails.append(f"a detail-only change was reported: {problems} {excused} {stale}")
    return fails


def probe_an_exempted_removal_is_excused_not_clean() -> list[str]:
    """An exemption excuses loudly — `clean` and `excused` must never be the same output."""
    fails: list[str] = []
    transitions = [_transition(SHA_A, [_row(1), _row(2)], [_row(1)])]
    problems, excused, stale = no_shrink_problems(
        transitions, {SHA_A: {"sha": SHA_A, "reason": "sanctioned by n=318"}}
    )
    if problems:
        fails.append(f"an exempted removal was still a problem: {problems}")
    if len(excused) != 1 or "n=318" not in excused[0]:
        fails.append(f"the exemption was not printed with its proof: {excused}")
    if stale:
        fails.append(f"a matched exemption read as stale: {stale}")
    return fails


def probe_a_stale_exemption_is_an_error() -> list[str]:
    """An exemption matching nothing inflates visible debt while excusing nothing."""
    fails: list[str] = []
    problems, _, stale = no_shrink_problems(
        [_transition(SHA_A, [_row(1)], [_row(1)])],
        {SHA_B: {"sha": SHA_B, "reason": "matches nothing"}},
    )
    if problems:
        fails.append(f"an unrelated exemption raised a problem: {problems}")
    if stale != [SHA_B]:
        fails.append(f"the stale exemption was not reported: {stale}")
    return fails


def probe_the_walker_reads_real_history() -> list[str]:
    """The walker is exercised against the live repo, not only against synthetic rows."""
    fails: list[str] = []
    cwd = repo_toplevel() or REPO
    ref = PRIMARY_REF if resolvable(PRIMARY_REF, cwd) else FALLBACK_REF
    transitions, entries, err = build_transitions(ref, LEDGER_PATH, cwd)
    if transitions is None:
        fails.append(f"the walk failed: {err}")
        return fails
    if not entries:
        fails.append("the walk found zero commits touching the ledger")
        return fails
    if not transitions:
        fails.append("no commit carried a deletion — the live history has 8")
    return fails


def main() -> int:
    print("ledger no-shrink — a pushed row is never removed (P11, issue #58)")
    fails: list[str] = []
    print("  synthetic probes")
    for probe in (
        probe_removal_without_exemption_is_a_problem,
        probe_a_content_change_is_not_a_removal,
        probe_an_exempted_removal_is_excused_not_clean,
        probe_a_stale_exemption_is_an_error,
    ):
        for line in probe():
            fails.append(f"{probe.__name__}: {line}")
    for line in probe_the_walker_reads_real_history():
        fails.append(f"probe_the_walker_reads_real_history: {line}")

    cwd = repo_toplevel() or REPO
    exemptions, problems = load_exemptions(cwd / EXEMPTIONS_PATH)

    ref = PRIMARY_REF if resolvable(PRIMARY_REF, cwd) else FALLBACK_REF
    if ref != PRIMARY_REF:
        print(f"  note: {PRIMARY_REF} is unreadable here — degrading to {FALLBACK_REF}")

    transitions, entries, err = build_transitions(ref, LEDGER_PATH, cwd)
    if transitions is None:
        problems.append(f"could not read {LEDGER_PATH}'s committed history from {ref}: {err}")
        excused: list[str] = []
        stale: list[str] = []
    elif not entries:
        problems.append(
            f"no commit touches {LEDGER_PATH} on {ref} — a gate examining zero commits is "
            f"indistinguishable from one that examines zero commits and passes"
        )
        excused, stale = [], []
    else:
        gate_problems, excused, stale = no_shrink_problems(transitions, exemptions)
        problems.extend(gate_problems)
        for line in excused:
            print(f"  excused: {line}")
        for sha in stale:
            problems.append(
                f"exemption {sha} matches no row removal on {ref} — a stale exemption "
                f"excuses nothing; remove it or correct the sha"
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

    if excused:
        print(
            f"ledger no-shrink: excused — {len(excused)} exempted removal(s) on {ref}; "
            f"this is a visible debt, not a clean run"
        )
    else:
        print("ledger no-shrink: clean — no commit removes a row identity")
    return 0


if __name__ == "__main__":
    sys.exit(main())
