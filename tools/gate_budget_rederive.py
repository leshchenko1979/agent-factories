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
registration declares (leg B). Two further members of the population are read from an audit
report: a gate the audit reported UNKNOWN after its measured sample EXHAUSTED the declared
budget, and a gate that GREW — a completed PASSING sample whose own derivation
(`margin_for(sample) x sample`) now exceeds the declared wall (#564, ruling n=4308). Staleness
and exhaustion are both FAILURE-shaped, so growth was invisible to the leg at any magnitude: a
gate that passed inside its cap is neither stale nor exhausted, however far its duration has
drifted from the basis it was declared on. Those are the only four triggers; a fresh sample
that stays INSIDE the cap is NOT a trigger, because `margin_x` exists to absorb exactly that
variation and re-basing on every new maximum would ratchet the cap toward the "too high hides
a hung gate" direction (#128, ruling n=823).

GROWTH IS REPORT-FIRST, AND RE-DERIVES ONLY ON A TREND (#564). A wall that followed its own
sample would be current at every instant, so growth could never read as growth — that is the
drift guard disarmed by the act that silences it. So the FIRST breach is REPORTED and the
declared wall is left UNCHANGED; a SECOND CONSECUTIVE breach re-derives it. An outstanding
breach plus a round in which the entry produces NO completed passing sample ALSO counts as the
second breach, because the state that most needs the remedy is a gate that no longer completes
— and the derivation then uses the CARRIED sample from the round that reported the breach,
never the duration of the failure. A kill alone is not a size signal (n=3984); it becomes one
only after growth has already been flagged. The streak RESETS on any round where the derivation
stays inside the declared wall.

"CONSECUTIVE" IS READ FROM THE MANIFEST, NEVER FROM A LANE'S MEMORY. The round that reports a
breach records it IN THE ENTRY, as `growth_breach`, carrying the sample, the basis, the
derivation and the round's own identity (the report's `date` and `tree.head_sha`). A fresh
process holding the manifest and a report therefore reaches the same verdict with no history of
its own, and a re-run of the SAME round is idempotent because the identity it compares is the
one the report declares. The marker is the REPORT's durable record and is written whenever the
leg reports, with or without `--apply`; `--apply` remains the only path that changes a WALL.

PRECEDENCE, WHEN MORE THAN ONE TRIGGER FIRES. STALE outranks growth: a basis whose bytes or
argv moved describes a DIFFERENT command, and its remedy is a re-derivation from the fresh
sample whatever that sample's size, so growth never suppresses it. GROWTH outranks EXHAUSTED:
an exhausted gate has no completed sample, so the outstanding breach is the only size signal
left — exactly the deadlock the trend clause exists to break. The three sources are therefore a
PARTITION of the population, and the printed breakdown sums to the printed total.

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
import datetime
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


# THE GROWTH MARKER, AND WHY IT LIVES IN THE MANIFEST ENTRY (#564). "Second CONSECUTIVE
# breach" is a fact about two rounds, so it needs a durable home; the only two surfaces this
# leg may read are the manifest and the audit report, and a report is one round. So the round
# that REPORTS a breach writes its own record into the entry it is about, and the next round
# reads it back. A lane's memory is never the store: a fresh process, on a fresh box, in a
# fresh clone, reaches the same verdict from these two files alone.
GROWTH_MARKER = "growth_breach"

@dataclass(frozen=True)
class Growth:
    """One entry whose fresh measurement outgrew its declared wall.

    `consecutive` is the whole policy in one field: 1 means this is the round that REPORTS the
    breach and the wall must not move; 2 means the trend is established and the ordinary
    re-derivation applies. `carried` marks the deadlock arm — the round produced no completed
    passing sample, so the sample that SIZES the derivation is the one the reporting round
    recorded, never the duration of the failure.
    """

    key: str
    sample_sec: float
    basis_sec: float
    declared_sec: float
    derived_sec: float
    growth_x: float
    derived_over_declared: float
    consecutive: int = 1
    basis_revision: str = ""
    sample_revision: str | None = None
    carried: bool = False
    also_unknown: bool = False

@dataclass
class Population:
    """The containment population, with its own account of what it examined.

    `declared` and `examined` are separated on purpose: `declared` is the manifest's size,
    `examined` is what this run could actually reach. A population whose `examined` is zero
    has reached no verdict at all, and `note` says so in the run's own output rather than
    leaving a caller to infer it from an empty tuple.

    The three sources are a PARTITION (#564): `stale` and `exhausted` are read exactly as they
    always were, and `growth` claims only the entries NEITHER of them owns, so the breakdown
    printed beside the total sums to that total.
    """

    declared: int = 0
    examined: int = 0
    stale: tuple = ()
    exhausted: tuple = ()
    growth: tuple = ()
    reported: tuple = ()
    reset: tuple = ()
    not_examined: tuple = ()
    held: tuple = ()
    applied: tuple = ()
    note: str = ""
    extras: dict = field(default_factory=dict)

    @property
    def keys(self) -> tuple:
        """Every entry in the containment population, deduplicated and sorted."""
        return tuple(
            sorted(
                {s.key for s in self.stale}
                | set(self.exhausted)
                | {g.key for g in self.growth}
            )
        )


@dataclass(frozen=True)
class AuditRead:
    """One audit report, read into the four things the growth source and the triggers need.

    `present` is every gate the report MEASURED — passing, unknown, or completed-and-failed.
    That is what separates "produced no completed passing sample" from "was not run at all":
    a round that never invoked a gate has said nothing about it, and reading its silence as a
    failure would let a partial report rewrite a wall.

    `round_id` is the report's own identity — its `date` and the `tree.head_sha` it ran
    against. It is what makes "consecutive" computable from the two files alone, and it is
    what makes a re-run of the SAME report idempotent: the marker records the identity of the
    round that reported, so that round cannot count as its own successor.
    """

    samples: dict = field(default_factory=dict)
    exhausted: tuple = ()
    failed: tuple = ()
    present: tuple = ()
    note: str = ""
    revision: str | None = None
    round_id: str | None = None

def _audit_samples(report_path: Path) -> AuditRead:
    """The report's PASSING samples, the keys it reported UNKNOWN, the keys whose every
    completed sample FAILED, every key it measured, its note, the REVISION the samples were
    taken at, and the round's own identity.

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

    A COMPLETED SAMPLE MUST ALSO HAVE PASSED (#558, ruling n=4224). `unknown` alone is not
    enough: a gate that refuses structurally -- the `.audit.lock` held, a missing
    prerequisite, an import error -- COMPLETES, in a few seconds, with `passed: False` and
    `unknown: False`. Its duration measures how fast the gate REFUSED, never how long the
    work takes, and admitting it as a basis is how `margin_for(4.11) x 4.11 = 17.19 s`
    becomes the wall of a gate that needs 1008.75 s -- a 58.68x collapse that then kills the
    gate's own child every round, permanently. The field was present and unread: the same
    shape as #553, one instrument over.

    A failed-only gate is handed on SEPARATELY rather than dropped, so the leg can name it
    NOT DERIVABLE. A silent skip and a refusal look identical in a population count, and
    the count is what a reader trusts.
    """
    if not report_path.is_file():
        return AuditRead(
            note=f"no audit report at {report_path} — no fresh samples, so nothing can be applied"
        )
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return AuditRead(
            note=f"audit report at {report_path} is unreadable ({exc}) — UNKNOWN, never clean"
        )
    # The REVISION the samples were taken at, read from the report's own declaration of the
    # tree it ran against. This is what `measured_at` must record: the tree the measurement
    # came FROM, never whatever HEAD happens to be when the manifest is written. The two are
    # the same only when the leg runs immediately after the audit; a survey round writes its
    # artifact, commits, rebases and only then applies, so the write-time HEAD is a different
    # revision and stamping it names a tree the samples never saw.
    revision = (payload.get("tree") or {}).get("head_sha")
    if not isinstance(revision, str) or len(revision) != 40:
        revision = None
    # THE ROUND'S OWN IDENTITY, taken from the report rather than from the clock: two runs of
    # the SAME report are the SAME round, and a marker that recorded a timestamp instead would
    # let a re-run count as its own successor and re-derive a wall on one breach.
    declared_date = payload.get("date")
    round_id = (
        f"{declared_date}:{revision}"
        if isinstance(declared_date, str) and declared_date and revision
        else None
    )
    samples: dict[str, float] = {}
    exhausted: list[str] = []
    failed: list[str] = []
    present: list[str] = []
    for gate in payload.get("gates") or []:
        key = gate.get("gate_key")
        duration = gate.get("duration_sec")
        if not key or not isinstance(duration, (int, float)):
            continue
        # MEASURED, whatever the verdict: this is what distinguishes "produced no completed
        # passing sample" from "was never run", and only the first is a growth signal.
        present.append(key)
        if gate.get("unknown"):
            # Killed at its cap: no verdict was taken, so this is not a sample -- but the
            # gate's declared budget was EXHAUSTED, which is the third trigger.
            exhausted.append(key)
            continue
        if not gate.get("passed"):
            # COMPLETED BUT FAILED: a structural refusal, and its duration is the REFUSAL's
            # (#558). Never a basis -- named separately so the leg can print it.
            failed.append(key)
            continue
        samples[key] = max(samples.get(key, 0.0), float(duration))
    return AuditRead(
        samples=samples,
        exhausted=tuple(sorted(set(exhausted))),
        failed=tuple(sorted(set(failed))),
        present=tuple(sorted(set(present))),
        note=f"{len(samples)} passing sample(s) read from {report_path.name}"
        + (f"; {len(set(failed))} gate(s) completed and FAILED, so they carry no basis"
           if failed else ""),
        revision=revision,
        round_id=round_id,
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
    failed_only: tuple = ()
    growth: tuple = ()
    reset: tuple = ()
    samples: dict = {}
    sample_note = "no audit report given — the exhausted-budget trigger was not read"
    sample_revision: str | None = None
    round_id: str | None = None
    present: tuple = ()
    audit: AuditRead | None = None
    if audit_report is not None:
        audit = _audit_samples(Path(audit_report))
        samples = audit.samples
        sample_note = audit.note
        sample_revision = audit.revision
        round_id = audit.round_id
        present = audit.present
        # A gate whose only completed samples FAILED is NOT DERIVABLE, and it is named by
        # key rather than skipped (#558). Scoped to every DECLARED entry, never to the
        # containment population: a collapsed basis is self-consistent, so the gate it
        # starved is NOT stale and would be filtered out by exactly the blind spot this
        # clause exists to close (#558's 17.19 s entry reads clean against itself while its
        # gate dies every round). A silent skip and a refusal look identical in a count.
        failed_only = tuple(key for key in audit.failed if key in entries)
        # The trigger is the audit's OWN declaration that a declared entry exhausted its
        # budget -- the `unknown` flag -- never a comparison against the cap. It is read from
        # the UNKNOWN population, not from the completed samples: a completed sample finished
        # INSIDE its cap by definition, so the comparison this replaces could only ever be
        # vacuously false (#307).
        exhausted = tuple(key for key in audit.exhausted if key in entries)
        sample_note += (
            f" | exhausted-budget trigger: {len(exhausted)} declared entr"
            f"{'y' if len(exhausted) == 1 else 'ies'} reported UNKNOWN by the audit"
        )
        # THE THIRD SOURCE (#564). Read BEFORE the exhausted population is narrowed, because
        # a growth record has to know whether its entry ALSO reported UNKNOWN this round: the
        # two verdicts can hold at once, and precedence decides which one owns the entry in
        # the printed partition, never which one the reader is told about.
        growth, reset = _growth_source(entries, {s.key for s in stale}, audit)
        growth_keys = {g.key for g in growth}
        # PRECEDENCE: stale > growth > exhausted. Staleness was excluded inside the growth
        # read, so the two remaining sets are made disjoint here — one partition, one owner
        # per entry, and the breakdown therefore SUMS to the population it renders.
        exhausted = tuple(key for key in exhausted if key not in growth_keys)
        sample_note += (
            f" | growth trigger: {len(growth)} declared entr"
            f"{'y' if len(growth) == 1 else 'ies'} whose own derivation now exceeds the "
            f"declared wall ({sum(1 for g in growth if g.consecutive >= 2)} on a SECOND "
            f"consecutive breach, {len(reset)} reset by a round inside the wall)"
        )

    # The note is the sweep's OWN account, carried VERBATIM: it already names the
    # not-examined population once, by key, so this leg appends nothing to it (#442).
    note = budgets.stale_note

    return Population(
        declared=len(entries),
        examined=examined,
        stale=stale,
        exhausted=exhausted,
        growth=growth,
        reset=reset,
        not_examined=not_examined,
        note=note,
        extras={"samples": samples, "sample_note": sample_note, "manifest": str(path),
                "failed_only": failed_only, "sample_revision": sample_revision,
                "round_id": round_id, "present": present},
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


def _declared_sec(entry: object) -> float | None:
    """An entry's declared wall, or None when it states none a derivation could compare to."""
    value = entry.get("budget_sec") if isinstance(entry, dict) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    return float(value)

def _same_round(marker: object, round_id: str | None) -> bool:
    """True only when the marker and this report PROVABLY belong to the same round.

    Deliberately not "probably": when either side states no identity, sameness cannot be
    shown, so the round counts as a new one and the trend advances. The error that leaves is
    a re-derivation one round early on a report that declares no `date`/`tree` — visible, and
    the direction a growth guard should fail in. The error it prevents is a re-run of the
    SAME report reading as its own successor, which would re-derive a wall on ONE breach and
    turn report-first into report-never.
    """
    if not isinstance(marker, dict) or not round_id:
        return False
    return marker.get("round_id") == round_id

def _growth_for(
    key: str,
    entry: dict,
    sample: float,
    *,
    consecutive: int,
    sample_revision: str | None,
    carried: bool = False,
    also_unknown: bool = False,
) -> Growth | None:
    """One growth record, with every figure the report owes a reader.

    `derived` is recomputed from the sample by the manifest's own law rather than copied from
    the marker: a record is a reading, and the leg's authority is the function, never the
    last round's arithmetic.
    """
    declared = _declared_sec(entry)
    basis = entry.get("measured_sec")
    if declared is None or isinstance(basis, bool) or not isinstance(basis, (int, float)) or basis <= 0:
        return None
    derived = round(margin_for(float(sample)) * float(sample), 2)
    return Growth(
        key=key,
        sample_sec=round(float(sample), 2),
        basis_sec=float(basis),
        declared_sec=declared,
        derived_sec=derived,
        growth_x=round(float(sample) / float(basis), 4),
        derived_over_declared=round(derived / declared, 4),
        consecutive=consecutive,
        basis_revision=str(entry.get("measured_at") or ""),
        sample_revision=sample_revision,
        carried=carried,
        also_unknown=also_unknown,
    )

def _growth_source(
    entries: dict, stale_keys: set, audit: AuditRead | None
) -> tuple[tuple, tuple]:
    """The GROWTH source (#564), and the entries whose streak RESETS this round.

    Three conditions, and each is load-bearing:

    * COMPLETED AND PASSING ONLY. `audit.samples` is exactly that population, so a gate killed
      at its wall or a gate that refused structurally is not here — the #558 repair already
      names those `[NOT DERIVABLE]`, and folding them in would re-introduce that defect one
      population over.
    * `derived > declared`, computed by the manifest's own margin law. No new number enters.
    * NOT STALE. A basis whose bytes or argv moved describes a different command, and its
      remedy is a re-derivation whatever the sample's size, so staleness owns that entry and
      growth never suppresses it.

    The second arm is the deadlock clause: an OUTSTANDING breach (the marker) plus a round in
    which the entry was KILLED at its cap counts as the second breach, and it is sized from the
    sample the reporting round recorded. An entry the report never invoked has said nothing and
    advances nothing -- and an entry that was measured and REFUSED is excluded, because a
    refusal measures how fast the gate refused (#558), not that it grew.
    """
    if audit is None:
        return (), ()
    growth: list[Growth] = []
    reset: list[str] = []
    for key, entry in entries.items():
        if key in stale_keys:
            continue
        declared = _declared_sec(entry)
        if declared is None:
            continue
        marker = entry.get(GROWTH_MARKER)
        marker = marker if isinstance(marker, dict) else None
        sample = audit.samples.get(key)
        record: Growth | None = None
        if sample is not None:
            derived = round(margin_for(float(sample)) * float(sample), 2)
            if derived <= declared:
                # THE STREAK RESETS on any round inside the wall (#564 clause 4).
                if marker is not None:
                    reset.append(key)
                continue
            record = _growth_for(
                key,
                entry,
                float(sample),
                consecutive=2 if (marker is not None and not _same_round(marker, audit.round_id)) else 1,
                sample_revision=audit.revision,
            )
        elif marker is not None and key in audit.exhausted:
            carried_sample = marker.get("sample_sec")
            if (
                isinstance(carried_sample, bool)
                or not isinstance(carried_sample, (int, float))
                or carried_sample <= 0
            ):
                # A marker with no usable sample cannot size a derivation; the ordinary path
                # names the entry rather than inventing a number for it.
                continue
            record = _growth_for(
                key,
                entry,
                float(carried_sample),
                consecutive=2,
                sample_revision=marker.get("sample_revision"),
                carried=True,
                also_unknown=True,
            )
        elif marker is not None and key in audit.present:
            # MEASURED AND REFUSED, not killed: #558's population. A refusal measures how fast
            # the gate REFUSED, so it says the gate is BROKEN, never that it GREW -- and
            # letting it advance the trend would cash in the previous round's number on a
            # round that measured nothing. It is named NOT DERIVABLE by the ordinary path.
            continue
        if record is not None:
            growth.append(record)
    return tuple(growth), tuple(sorted(reset))

def _write_manifest(data: dict, manifest_path: Path, root: Path, entries: dict) -> bool:
    """Write the manifest through the manifest's OWN loader, or leave the file untouched.

    The loader refuses a stated derivation its own numbers contradict, so a write that would
    land an inconsistent manifest is caught here rather than by the next audit round. Returns
    True when the file was replaced.
    """
    tmp = manifest_path.with_suffix(".json.rederive-tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        budgets = load_gate_budgets(tmp, root)
    except Exception:  # noqa: BLE001 — a refused manifest is a REFUSAL, never a crash
        tmp.unlink(missing_ok=True)
        return False
    if budgets.gates and len(budgets.gates) < len(entries):
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(manifest_path)
    return True

def record_growth_state(pop: Population, manifest_path: Path) -> Population:
    """Record the REPORT's durable state: a first-breach marker, and a cleared one on reset.

    This runs on the REPORTING path, with or without `--apply`, because the marker is what
    makes the NEXT round's verdict computable from the manifest and a report alone. A report
    that left no record would be report-only-in-prose: every round would read as a first
    breach forever, the wall would never move, and the trend clause would be a promise. What
    it never does is change a WALL — `budget_sec` is untouched here, and `--apply` stays the
    only path that derives one.
    """
    if not pop.growth and not pop.reset:
        return pop
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return pop
    entries = data.get("gates")
    if not isinstance(entries, dict):
        return pop

    round_id = pop.extras.get("round_id")
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    recorded: list[str] = []
    changed = False
    for growth in pop.growth:
        if growth.consecutive != 1:
            continue  # a second breach is about to be DERIVED; no marker to leave
        entry = entries.get(growth.key)
        if not isinstance(entry, dict):
            continue
        existing = entry.get(GROWTH_MARKER)
        if (
            isinstance(existing, dict)
            and existing.get("round_id") == round_id
            and existing.get("sample_sec") == growth.sample_sec
        ):
            recorded.append(growth.key)  # already this round's record — no byte churn
            continue
        entry[GROWTH_MARKER] = {
            "sample_sec": growth.sample_sec,
            "sample_revision": growth.sample_revision,
            "basis_sec": growth.basis_sec,
            "basis_revision": growth.basis_revision,
            "declared_sec": growth.declared_sec,
            "derived_sec": growth.derived_sec,
            "growth_x": growth.growth_x,
            "derived_over_declared": growth.derived_over_declared,
            "round_id": round_id,
            "reported_at": now,
        }
        recorded.append(growth.key)
        changed = True
    for key in pop.reset:
        entry = entries.get(key)
        if isinstance(entry, dict) and GROWTH_MARKER in entry:
            entry.pop(GROWTH_MARKER, None)
            changed = True
    if changed and not _write_manifest(data, manifest_path, REPO_ROOT, entries):
        return pop
    pop.extras["marker_recorded"] = tuple(recorded)
    return pop

def apply_rederivation(
    pop: Population,
    manifest_path: Path,
    root: Path,
    head: str | None,
) -> Population:
    """Re-derive every entry in the containment population from a completed audit sample.

    The derivation is the manifest's own law, evaluated by the manifest's own function:
    `margin_x = margin_for(measured_sec)` and `budget_sec = round(margin_x x measured_sec, 2)`.
    `measured_at` is recorded as the ABSOLUTE revision the SAMPLE was taken at — the audit
    report's own `tree.head_sha` — and `load_at_measure` as the load read at that instant.

    `head` is only the FALLBACK for a report that declares no tree: a survey round writes its
    artifact, commits and rebases BEFORE it applies, so the write-time HEAD names a revision
    these samples never ran against, and stamping it would make the entry NOT EXAMINED in any
    fresh clone (`gate_budget.py`, the `measured_at` reachability read).

    The result is re-read through `load_gate_budgets()` BEFORE it is written. The manifest's
    loader refuses a stated derivation its own numbers contradict, so a re-derivation that
    would land an inconsistent manifest is caught here rather than by the next audit round.
    """
    samples: dict = pop.extras.get("samples") or {}
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = data["gates"]
    load = _load_at_measure()
    # The revision the MEASUREMENT came from, never the write-time one.
    measured_at = pop.extras.get("sample_revision") or head

    applied: list = []
    reported: list = []
    held: list = []
    growth_keys = {g.key for g in pop.growth}
    for growth in pop.growth:
        entry = entries.get(growth.key)
        if not isinstance(entry, dict):
            held.append((growth.key, "declared entry is not an object"))
            continue
        if growth.consecutive < 2:
            # REPORT-FIRST (#564 clause 2): ONE breach re-derives nothing. The figures are
            # reported and the wall is left EXACTLY as it is -- a single slow round is as
            # likely a loaded box as a grown gate, and deriving from it would move every
            # wall on noise.
            reported.append(growth.key)
            continue
        margin_x = margin_for(float(growth.sample_sec))
        entry["measured_sec"] = round(float(growth.sample_sec), 2)
        entry["margin_x"] = round(margin_x, 3)
        entry["budget_sec"] = round(margin_x * float(growth.sample_sec), 2)
        # The REVISION THE SAMPLE came from. A carried sample's revision is the round that
        # recorded it, never this one's: this round produced no completed passing sample, so
        # its tree measured nothing.
        entry["measured_at"] = growth.sample_revision or measured_at
        if load is not None:
            entry["load_at_measure"] = load
        # The streak is consumed by the derivation it produced: a marker left behind would
        # make the NEXT round read as a second breach on a wall that has already moved.
        entry.pop(GROWTH_MARKER, None)
        applied.append(growth.key)
    for key in pop.keys:
        if key in growth_keys:
            continue  # growth owns this entry; the loop above has already decided it
        sample = samples.get(key)
        if not isinstance(sample, (int, float)) or sample <= 0:
            if key in (pop.extras.get("failed_only") or ()):
                # Every completed sample FAILED, so nothing here is a measurement of the
                # work: the durations measure how fast the gate refused (#558).
                held.append(
                    (key, "NOT DERIVABLE — every completed sample FAILED, and a refused run "
                          "measures how fast the gate refused, never how long the work takes")
                )
            elif key in pop.exhausted:
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
        entry["measured_at"] = measured_at
        if load is not None:
            entry["load_at_measure"] = load
        applied.append(key)

    if applied:
        # The manifest's own loader is the gate on the write: it refuses a derivation its
        # numbers contradict, so the swap only happens when the result reads back sound.
        if not _write_manifest(data, manifest_path, root, entries):
            return Population(
                declared=pop.declared,
                examined=pop.examined,
                stale=pop.stale,
                exhausted=pop.exhausted,
                growth=pop.growth,
                reset=pop.reset,
                not_examined=pop.not_examined,
                applied=(),
                reported=tuple(reported),
                held=tuple(held),
                note=(
                    f"REFUSED — the re-derived manifest does not read back with all "
                    f"{len(entries)} declared entries, so it was NOT written; "
                    f"{manifest_path} is unchanged"
                ),
                extras=pop.extras,
            )

    return Population(
        declared=pop.declared,
        examined=pop.examined,
        stale=pop.stale,
        exhausted=pop.exhausted,
        growth=pop.growth,
        reset=pop.reset,
        not_examined=pop.not_examined,
        applied=tuple(applied),
        reported=tuple(reported),
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
        f"({len(pop.stale)} by a moved basis, {len(pop.exhausted)} by an exhausted budget, "
        f"{len(pop.growth)} by growth)",
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
    for growth in pop.growth:
        lines.append(
            f"    [GROWTH] {growth.key} — sample {growth.sample_sec} s"
            + (" CARRIED from the reporting round" if growth.carried else "")
            + f" against a basis of {growth.basis_sec} s at {growth.basis_revision[:12] or 'no revision'}: "
            f"margin_for({growth.sample_sec}) = {margin_for(growth.sample_sec):.6f}, so the derived "
            f"wall is {growth.derived_sec} s = {growth.derived_over_declared}x the declared "
            f"{growth.declared_sec} s (the sample is {growth.growth_x}x the basis)"
            + ("; the audit ALSO reported it UNKNOWN this round" if growth.also_unknown else "")
        )
        if growth.consecutive >= 2 and growth.key in pop.applied:
            lines.append(
                f"    [RE-DERIVED] {growth.key} — SECOND consecutive breach: {growth.declared_sec} s "
                f"-> {growth.derived_sec} s, measured_at {growth.sample_revision or 'unchanged'}"
            )
        elif growth.consecutive >= 2:
            lines.append(
                f"    [SECOND BREACH] {growth.key} — the trend is established; a run with --apply "
                f"re-derives {growth.declared_sec} s -> {growth.derived_sec} s"
            )
        else:
            recorded = growth.key in (pop.extras.get("marker_recorded") or ())
            lines.append(
                f"    [REPORTED] {growth.key} — FIRST breach: the declared wall is UNCHANGED at "
                f"{growth.declared_sec} s; a second CONSECUTIVE breach re-derives it to "
                f"{growth.derived_sec} s — "
                + (
                    "recorded in the manifest, so the next round can see the trend"
                    if recorded
                    else "NOT RECORDED, so the next round will read as a first breach again"
                )
            )
    for key in pop.reset:
        lines.append(
            f"    [RESET] {key} — this round came back INSIDE the declared wall, so the "
            f"breach streak is cleared"
        )
    if pop.applied:
        lines.append(f"  APPLIED {len(pop.applied)}: {', '.join(pop.applied)}")
    if pop.reported:
        lines.append(
            f"  REPORTED ONLY {len(pop.reported)}: {', '.join(pop.reported)} — a first breach "
            f"moves no wall"
        )
    held_keys = {key for key, _why in pop.held}
    for key in pop.extras.get("failed_only") or ():
        if key in held_keys:
            continue  # `--apply` already printed this key with its reason
        lines.append(
            f"    [NOT DERIVABLE] {key} — every completed sample FAILED, and a refused run "
            f"measures how fast the gate refused, never how long the work takes"
        )
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

    # THE REPORTING PATH WRITES ITS OWN RECORD (#564). Deliberately before `--apply` and not
    # behind it: a first breach is REPORTED, and the record of that report is what lets the
    # next round tell a trend from a one-off. It never touches a wall.
    pop = record_growth_state(pop, manifest)

    if args.apply:
        if report is None:
            print(
                "REFUSED — --apply needs --audit-report: the leg re-derives from a COMPLETED "
                "whole-command sample and will not carry a number forward (never a value by feel)"
            )
            return EXIT_REFUSED
        head = pop.extras.get("sample_revision") or _head_sha(root)
        if head is None:
            print(
                f"REFUSED — the audit report declares no tree and no HEAD resolves under "
                f"{root}, so `measured_at` cannot be recorded"
            )
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
                    "growth": [
                        {
                            "key": g.key,
                            "sample_sec": g.sample_sec,
                            "basis_sec": g.basis_sec,
                            "declared_sec": g.declared_sec,
                            "derived_sec": g.derived_sec,
                            "growth_x": g.growth_x,
                            "derived_over_declared": g.derived_over_declared,
                            "consecutive": g.consecutive,
                            "basis_revision": g.basis_revision,
                            "sample_revision": g.sample_revision,
                            "carried": g.carried,
                            "also_unknown": g.also_unknown,
                        }
                        for g in pop.growth
                    ],
                    "reported": list(pop.reported),
                    "reset": list(pop.reset),
                    "round_id": pop.extras.get("round_id"),
                    "marker_recorded": list(pop.extras.get("marker_recorded") or ()),
                    "not_examined": list(pop.not_examined),
                    "failed_only": list(pop.extras.get("failed_only") or ()),
                    "sample_revision": pop.extras.get("sample_revision"),
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
