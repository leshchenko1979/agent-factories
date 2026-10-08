#!/usr/bin/env python3
"""The gate-budget re-derivation leg — the standing duty that clears the staleness class.

WHY THIS EXISTS (issue #269). A declared basis in `registry/gates.json` goes STALE whenever
the command it names changes, so staleness is a **standing property of the manifest** and not
a one-off backlog: `#141`, the one-off batch that first cleared the class, is CLOSED while its
class RECURS. Before this file nothing re-derived the bases on any cadence, so the class was
reported every round and cleared by nothing. The procedure's declaration is
`docs/measurement-procedure.md` §5.2; this file is the MECHANICAL half of that declaration,
and it exists so the leg is an invocation rather than a paragraph.

WHAT IT READS, AND FROM WHERE. The containment population comes from the manifest's OWN
sweep — `gate_budget.budget_staleness()`, the one predicate for "does this basis still
describe what runs", never a private re-parse of the same field. Its two legs are the gate
file's BLOB at `measured_at` against HEAD (leg A) and the `gates_to_run.append(...)` argv its
registration declares (leg B). A third member of the population is read from an audit
report: a gate the audit reported UNKNOWN after its measured sample EXHAUSTED the declared
budget. Those are the only three triggers; a fresh sample that stays INSIDE the cap is NOT a
trigger, because `margin_x` exists to absorb exactly that variation and re-basing on every
new maximum would ratchet the cap toward the "too high hides a hung gate" direction (#128,
ruling n=823).

THE POPULATION IS PRINTED, ALWAYS, WITH ITS COUNT. The run states how many declared entries
it examined, how many were stale and by which leg, how many it could not examine at all
(`measured_at` resolving to no revision here — UNKNOWN, never clean), and how many it applied
or held. An empty population is stated as EMPTY, so a leg that ran over nothing stays
distinguishable from one that never ran.

NON-VACUITY IS ASSERTED, NOT ASSUMED. A predicate that examined nothing has reported nothing,
not "clean". The leg exits 2 — loudly, naming which population came back empty — when it
examined zero declared entries, so a green exit is never the verdict of a vacuous read. The
separate PROBE half (that this leg BITES on a stale base rather than merely exiting 0) is
driven by `tests/test_gate_registration.py`, because non-vacuity is a property of the probe
and population visibility is a property of the run.

WHAT IT WILL NOT DO. It never re-values the DEFAULT entry: what the suite does with a gate
nobody has measured is a policy choice and is HQ's, never this leg's (n=574 PART 5). It never
picks a number by feel: every applied value is `margin_for(measured_sec) x measured_sec` — the
manifest's own stated law, recomputed by the manifest's own function — and the result is
re-read through `load_gate_budgets()` before it is written, so a derivation the manifest's
loader refuses never reaches the file. It never invents a sample: an entry in the containment
population with no completed sample in the audit report is HELD and NAMED, never given a
carried-over number.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

from gate_budget import (  # noqa: E402
    gates_manifest_path,
    load_gate_budgets,
    margin_for,
)

EXIT_VACUOUS = 2
EXIT_REFUSED = 3

# THE EXHAUSTED-BUDGET MARKER. A gate whose sample exhausted its declared budget is
# reported by the audit with `unknown` set and its `duration_sec` recorded as a LOWER
# BOUND -- the flag `judge_gates` itself reads (#93, #226). That flag is the third
# containment trigger, and `_audit_samples` below reads it. It is deliberately NOT an
# exit code: 124 is the audit's own timeout path, but a gate script is free to exit 124
# for its own reasons, so the flag is the only sound marker.


@dataclass
class Population:
    """The containment population, with its own account of what it examined.

    `declared` and `examined` are separated on purpose: `declared` is the manifest's size,
    `examined` is what this run could actually reach. A population whose `examined` is zero
    has reached no verdict at all, and `note` says so in the run's own output rather than
    leaving a caller to infer it from an empty tuple.
    """

    declared: int = 0
    examined: int = 0
    stale: tuple = ()
    exhausted: tuple = ()
    not_examined: tuple = ()
    held: tuple = ()
    applied: tuple = ()
    note: str = ""
    extras: dict = field(default_factory=dict)

    @property
    def keys(self) -> tuple:
        """Every entry in the containment population, deduplicated and sorted."""
        return tuple(sorted({s.key for s in self.stale} | set(self.exhausted)))


def _audit_samples(report_path: Path) -> tuple[dict, tuple, str]:
    """The report's COMPLETED samples, the keys it reported UNKNOWN, and the report's note.

    TWO populations, returned SEPARATELY, and the separation is the whole point (#307). A
    COMPLETED sample is the only thing a basis may be derived from: it is a MEASUREMENT. An
    UNKNOWN result carries a `duration_sec` too, but that number is a LOWER BOUND on a run
    killed at the cap — using it as a basis would derive the next budget from a clipped
    number and ratchet the cap DOWN, which is the one direction the manifest's margin exists
    to prevent.

    So an UNKNOWN gate is NOT a sample — but it IS the audit's exhausted-budget trigger, and
    this function must hand it on rather than drop it. Collapsing the two into one set is
    exactly the #307 defect: the trigger was computed from the surviving samples, so the only
    gates that could satisfy it had already been filtered out and the population was empty
    for every input, forever.
    """
    if not report_path.is_file():
        return {}, (), f"no audit report at {report_path} — no fresh samples, so nothing can be applied"
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, (), f"audit report at {report_path} is unreadable ({exc}) — UNKNOWN, never clean"
    samples: dict[str, float] = {}
    exhausted: list[str] = []
    for gate in payload.get("gates") or []:
        key = gate.get("gate_key")
        duration = gate.get("duration_sec")
        if not key or not isinstance(duration, (int, float)):
            continue
        if gate.get("unknown"):
            # Killed at its cap: no verdict was taken, so this is not a sample -- but the
            # gate's declared budget was EXHAUSTED, which is the third trigger.
            exhausted.append(key)
            continue
        samples[key] = max(samples.get(key, 0.0), float(duration))
    return (
        samples,
        tuple(sorted(set(exhausted))),
        f"{len(samples)} completed sample(s) read from {report_path.name}",
    )


def containment_population(
    manifest_path: Path | None = None,
    repo_root: Path | None = None,
    audit_report: Path | None = None,
) -> Population:
    """The entries whose declared basis no longer describes what runs.

    Read through the manifest's own sweep for legs A and B, and through the audit's own
    report for the exhausted-budget trigger. The two sources are kept SEPARATE in the result
    because they answer different questions — one is about identity, the other about a
    measured cap — and a caller that wants a single list asks for `.keys`.
    """
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    path = Path(manifest_path) if manifest_path is not None else gates_manifest_path()

    if not path.is_file():
        return Population(
            note=f"NOT RUN — no manifest at {path}, so there is no declared basis to examine",
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return Population(note=f"NOT RUN — manifest at {path} is unreadable ({exc})")

    entries = data.get("gates")
    if not isinstance(entries, dict) or not entries:
        return Population(
            note=(
                f"NOT RUN — the manifest at {path} declares no per-gate basis, so there is "
                f"nothing to re-derive"
            ),
        )

    budgets = load_gate_budgets(path, root)
    stale = budgets.stale
    # NOT EXAMINED is read from the sweep's OWN answer, never re-derived here -- and never
    # re-rendered either. An entry the sweep could not reach -- no `measured_at`, or one
    # resolving to nothing -- is exactly the population `budgets.stale_note` ALREADY names by
    # key (#419: one definition), so the field below carries it and this leg appends NO clause
    # of its own (#442: one rendering, not three).
    not_examined = budgets.unreached
    examined = len(entries) - len(not_examined)

    exhausted: tuple = ()
    samples: dict = {}
    sample_note = "no audit report given — the exhausted-budget trigger was not read"
    if audit_report is not None:
        samples, exhausted_keys, sample_note = _audit_samples(Path(audit_report))
        # The trigger is the audit's OWN declaration that a declared entry exhausted its
        # budget -- the `unknown` flag -- never a comparison against the cap. It is read from
        # the UNKNOWN population, not from the completed samples: a completed sample finished
        # INSIDE its cap by definition, so the comparison this replaces could only ever be
        # vacuously false (#307).
        exhausted = tuple(key for key in exhausted_keys if key in entries)
        sample_note += (
            f" | exhausted-budget trigger: {len(exhausted)} declared entr"
            f"{'y' if len(exhausted) == 1 else 'ies'} reported UNKNOWN by the audit"
        )

    # The note is the sweep's OWN account, carried VERBATIM: it already names the
    # not-examined population once, by key, so this leg appends nothing to it (#442).
    note = budgets.stale_note

    return Population(
        declared=len(entries),
        examined=examined,
        stale=stale,
        exhausted=exhausted,
        not_examined=not_examined,
        note=note,
        extras={"samples": samples, "sample_note": sample_note, "manifest": str(path)},
    )


def _head_sha(root: Path) -> str | None:
    """HEAD's absolute sha, read from git — never composed, never a relative revision."""
    import subprocess

    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = out.stdout.strip()
    return sha if out.returncode == 0 and len(sha) == 40 else None


def _load_at_measure() -> float | None:
    """The box's 1-minute load average, read at the instant the sample is taken.

    Read here rather than carried from the manifest: `load_at_measure` is a property of the
    MEASUREMENT, and a value copied from the entry being replaced would describe the previous
    reading rather than this one.
    """
    try:
        import os

        return round(os.getloadavg()[0], 2)
    except (OSError, AttributeError):
        return None


def apply_rederivation(
    pop: Population,
    manifest_path: Path,
    root: Path,
    head: str,
) -> Population:
    """Re-derive every entry in the containment population from a completed audit sample.

    The derivation is the manifest's own law, evaluated by the manifest's own function:
    `margin_x = margin_for(measured_sec)` and `budget_sec = round(margin_x x measured_sec, 2)`.
    `measured_at` is recorded as the ABSOLUTE revision the sample was taken at, and
    `load_at_measure` as the load read at that instant.

    The result is re-read through `load_gate_budgets()` BEFORE it is written. The manifest's
    loader refuses a stated derivation its own numbers contradict, so a re-derivation that
    would land an inconsistent manifest is caught here rather than by the next audit round.
    """
    samples: dict = pop.extras.get("samples") or {}
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = data["gates"]
    load = _load_at_measure()

    applied: list = []
    held: list = []
    for key in pop.keys:
        sample = samples.get(key)
        if not isinstance(sample, (int, float)) or sample <= 0:
            if key in pop.exhausted:
                # The trigger fired: this gate's declared budget was exhausted, so the
                # audit's duration is a LOWER BOUND and may never seed a re-derivation.
                # It is HELD and NAMED -- the leg refuses rather than carry a clipped number.
                held.append(
                    (key, "budget exhausted — the audit's duration is a lower bound, never a sample")
                )
            else:
                held.append((key, "no completed sample in the audit report"))
            continue
        margin_x = margin_for(float(sample))
        entry = entries.get(key)
        if not isinstance(entry, dict):
            held.append((key, "declared entry is not an object"))
            continue
        entry["measured_sec"] = round(float(sample), 2)
        entry["margin_x"] = round(margin_x, 3)
        entry["budget_sec"] = round(margin_x * float(sample), 2)
        entry["measured_at"] = head
        if load is not None:
            entry["load_at_measure"] = load
        applied.append(key)

    if applied:
        tmp = manifest_path.with_suffix(".json.rederive-tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        # The manifest's own loader is the gate on the write: it refuses a derivation its
        # numbers contradict, so the swap only happens when the result reads back sound.
        budgets = load_gate_budgets(tmp, root)
        if budgets.gates and len(budgets.gates) < len(entries):
            tmp.unlink(missing_ok=True)
            return Population(
                declared=pop.declared,
                examined=pop.examined,
                stale=pop.stale,
                exhausted=pop.exhausted,
                not_examined=pop.not_examined,
                applied=(),
                held=tuple(held),
                note=(
                    f"REFUSED — the re-derived manifest reads back with "
                    f"{len(budgets.gates)} of {len(entries)} declared entries, so it was NOT "
                    f"written; {manifest_path} is unchanged"
                ),
                extras=pop.extras,
            )
        tmp.replace(manifest_path)

    return Population(
        declared=pop.declared,
        examined=pop.examined,
        stale=pop.stale,
        exhausted=pop.exhausted,
        not_examined=pop.not_examined,
        applied=tuple(applied),
        held=tuple(held),
        note=pop.note,
        extras=pop.extras,
    )


def render(pop: Population) -> str:
    """The population, printed with its count — the run's own account of what it examined."""
    lines = [
        f"Gate-budget re-derivation leg — {pop.declared} declared entr"
        f"{'y' if pop.declared == 1 else 'ies'}, {pop.examined} examined",
        f"  {pop.note or 'no sweep note'}",
        f"  population: {len(pop.keys)} entr{'y' if len(pop.keys) == 1 else 'ies'} "
        f"in the containment set "
        f"({len(pop.stale)} by a moved basis, {len(pop.exhausted)} by an exhausted budget)",
    ]
    for stale in pop.stale:
        lines.append(f"    [STALE] {stale.key} — legs {', '.join(stale.legs)}: {stale.detail}")
    for key in pop.exhausted:
        lines.append(
            f"    [EXHAUSTED] {key} — the audit reported it UNKNOWN: its declared budget was "
            f"exhausted"
        )
    # The not-examined population is named by `pop.note` -- the sweep's own clause, carried
    # into the note above -- so this body prints it no further: one population, one rendering
    # (#442). The FIELD `pop.not_examined` still carries it for machine readers.
    if pop.applied:
        lines.append(f"  APPLIED {len(pop.applied)}: {', '.join(pop.applied)}")
    for key, why in pop.held:
        lines.append(f"    [HELD] {key} — {why}")
    if pop.extras.get("sample_note"):
        lines.append(f"  samples: {pop.extras['sample_note']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gate-budget re-derivation leg (#269).")
    parser.add_argument("--manifest", type=str, default="", help="Manifest path (default: the live one)")
    parser.add_argument("--repo-root", type=str, default="", help="Repo root (default: this tree)")
    parser.add_argument("--audit-report", type=str, default="", help="An audit --json report to read samples from")
    parser.add_argument("--apply", action="store_true", help="Re-derive and write the manifest")
    parser.add_argument("--json", action="store_true", help="Emit the population as JSON")
    args = parser.parse_args(argv)

    manifest = Path(args.manifest) if args.manifest else gates_manifest_path()
    root = Path(args.repo_root) if args.repo_root else REPO_ROOT
    report = Path(args.audit_report) if args.audit_report else None

    pop = containment_population(manifest, root, report)

    if args.apply:
        if report is None:
            print(
                "REFUSED — --apply needs --audit-report: the leg re-derives from a COMPLETED "
                "whole-command sample and will not carry a number forward (never a value by feel)"
            )
            return EXIT_REFUSED
        head = _head_sha(root)
        if head is None:
            print(f"REFUSED — no resolvable HEAD under {root}, so `measured_at` cannot be recorded")
            return EXIT_REFUSED
        pop = apply_rederivation(pop, manifest, root, head)

    if args.json:
        print(
            json.dumps(
                {
                    "declared": pop.declared,
                    "examined": pop.examined,
                    "population": list(pop.keys),
                    "stale": [{"key": s.key, "legs": list(s.legs), "detail": s.detail} for s in pop.stale],
                    "exhausted": list(pop.exhausted),
                    "not_examined": list(pop.not_examined),
                    "applied": list(pop.applied),
                    "held": [{"key": k, "why": w} for k, w in pop.held],
                    "note": pop.note,
                },
                indent=2,
            )
        )
    else:
        print(render(pop))

    # NON-VACUITY: a predicate that examined nothing has reported nothing, not "clean".
    if pop.declared == 0 or pop.examined == 0:
        print(
            "VACUOUS — 0 declared entries examined, so this run reaches NO verdict. "
            "A green exit here would be the verdict of a read that examined nothing."
        )
        return EXIT_VACUOUS
    if pop.held:
        return EXIT_REFUSED
    return 0


if __name__ == "__main__":
    sys.exit(main())
