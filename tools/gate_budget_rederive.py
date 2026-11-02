#!/usr/bin/env python3
"""The gate-budget re-derivation leg — the standing duty that clears the staleness class.

WHY THIS EXISTS (issue #269). A declared basis in `registry/gates.json` goes STALE whenever
the command it names changes, so staleness is a **standing property of the manifest** and not
a one-off backlog: `#141`, the one-off batch that first cleared the class, is CLOSED while its
class RECURS. Before this file nothing re-derived the bases on any cadence, so the class was
reported every round and cleared by nothing. The procedure's declaration is
`docs/measurement-procedure.md` docs/measurement-procedure.md §5.2; this file is the MECHANICAL half of that declaration,
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
PARTITION of the population, and `partition_problems()` REFUSES to print a breakdown whose
parts do not sum to the total it renders (#578) — the property is checked at the point of
rendering, never asserted here.

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
import os
import shlex
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

from gate_budget import (  # noqa: E402
    gates_manifest_path,
    load_gate_budgets,
    margin_for,
)
# THE ONE REGISTRATION READER, IMPORTED RATHER THAN RE-DERIVED (#604). A second
# `gates_to_run.append(...)` scan would be the drift class this factory files against itself:
# the probe must run the gate the way the AUDIT runs it, and the audit's registration is the
# only surface that says so. `gate_budget` already owns that reader; copying it here would
# give the probe its own opinion of the command.
from gate_budget import _registration_reader  # noqa: E402

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

# THE WALL-KILL RECORD, AND THE DEADLOCK IT BREAKS (#604). A gate killed at its own declared
# wall produces `unknown: true` and NO sample, so the ordinary re-derivation can never fire:
# the stale basis refuses (no fresh sample) and the wall refuses to produce one. Two
# consecutive rounds of that and the entry is locked out of its own budget -- `HELD` forever,
# with no lane told why. The record below is the DURABLE half of the escape, and it lives in
# the ENTRY for the same reason `growth_breach` does: a report is one round, so "consecutive"
# is only computable from a surface that outlives it. Written from the audit's own `unknown`
# flag on the REPORTING path, with or without `--apply`, and cleared the moment the gate
# COMPLETES (passing or failing) because a completed run breaks the streak by definition.
WALL_KILLS = "wall_kills"
# How many round identities the record keeps. A streak longer than this is still eligible;
# the count is what the reader needs, not the archaeology.
WALL_KILLS_KEEP = 5

# THE PROBE, AND ITS TWO BOUNDS (#604). A probe exists to obtain ONE completed sample for a
# gate the declared wall will not let finish. It is NOT a licence to raise a wall: the sample
# is fed to the ORDINARY derivation, which then has to license the number it produces.
#
# `PROBE_CEILING_FACTOR` is the envelope the probe may run in -- twice the declared wall. The
# measured case it is sized against (#602) needed 1496 s against a 1647.35 s declared wall,
# i.e. 0.91x, so 2x is ample for the class this serves.
#
# `PROBE_HARD_CAP_SEC` is absolute, so a wedged gate cannot turn a probe into an outage: no
# single probe runs past an hour, whatever its declared wall.
PROBE_CEILING_FACTOR = 2.0
PROBE_HARD_CAP_SEC = 3600.0
# The DECLARED fields a probe sample carries, so a machine reader -- never prose -- can tell
# it from an organic round sample. The regime travels with the number: a performance figure
# measured on a quiet box says nothing about the same gate on a loaded one.
PROBE_SAMPLE_FIELD = "probe_sample"
PROBE_REGIME_FIELD = "probe_regime"
# A REFUSED probe is recorded too, with the gate's blob at refusal time. A refusal is not a
# failure to report and re-run: probing a 25-minute gate every round to re-learn the same
# arithmetic is the cost this record removes, and the blob is what re-arms it when the gate
# itself changes (the #602 remedy is a SPLIT, which moves the blob).
PROBE_REFUSED_FIELD = "probe_refused"
# Whether the kill record was READ at all. An empty record and an unreadable manifest are
# the same value and different facts, so the renderer is given the distinction rather than
# left to infer it from an empty tuple.
WALL_KILLS_READ = "wall_kills_read"
# WHERE the kill record came from. THREE states, and collapsing them is the #595
# ordering lie in this leg: a record nobody read, a record that was read but not
# ADVANCED this round (no audit report), and a record advanced by a real round. The
# first two produce an empty tuple and so does a genuinely clean third, so the state
# is carried rather than re-derived at the render.
WALL_KILLS_SOURCE = "wall_kills_source"
KILL_SOURCE_UNREAD = "unread"
KILL_SOURCE_NO_AUDIT = "no-audit"
KILL_SOURCE_ROUND = "round"

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

@dataclass(frozen=True)
class WallKill:
    """One gate's record of being killed at its own declared wall, round after round.

    `rounds` are the audit reports' own identities (`date:head_sha`), newest LAST, deduplicated
    and capped. `consecutive` is their count: every entry in the list came from a round in
    which the gate was reported UNKNOWN, and a completed run CLEARS the list, so the count is
    an unbroken streak by construction rather than by assertion.

    `eligible` is `consecutive >= 2`. ONE kill is contention -- a loaded box, a peer's suite --
    and a mechanism that fired on it would probe every gate that ever got unlucky. Two
    consecutive kills at a wall the gate previously met is a LOCKOUT: the wall itself is what
    prevents the sample that would move it (#604).
    """

    key: str
    rounds: tuple
    consecutive: int
    declared_sec: float
    eligible: bool
    why: str = ""
    # Whether a growth breach is still outstanding on this entry. Carried so the render can
    # say WHICH conjunct refused, rather than leaving a reader to re-derive it from the wall.
    outstanding_breach: bool = False

@dataclass(frozen=True)
class ProbeSample:
    """One quiet-box probe: the sample it produced, and the regime it was taken in.

    `taken` is False when the probe did not run at all, and `why` says which of the three
    lawful refusals applied -- no registered invocation, a box that is not quiet, or a
    refusal already recorded against the SAME gate blob. An instrument that cannot observe
    its own failure class proves nothing, so a probe that did not run is REPORTED rather than
    omitted: "no sample" and "never tried" are different facts with the same shape.

    `licensed` is the derivation's verdict on the number, never the probe's: a sample is an
    INPUT to docs/measurement-procedure.md §5.2, and the wall moves only if `margin_for(sample) x sample` fits under the
    HARD CAP. That bound is deliberately not the probe ceiling: docs/measurement-procedure.md §5.2 multiplies by ~4, so a
    gate that finished just past its wall derives a wall several times its sample, and a
    ceiling-shaped licence would refuse the ordinary re-derivation it exists to produce. The
    cap refuses the shape that is an OUTAGE rather than a budget (#602: 1496 s licensing
    5984.75 s), and the entry is then left exactly where it was -- which is the whole
    difference between this mechanism and raising a wall by feel.
    """

    key: str
    invocation: str = ""
    sample_sec: float | None = None
    rc: int | None = None
    ceiling_sec: float = 0.0
    hard_cap_sec: float = 0.0
    load_at_start: float | None = None
    load_at_finish: float | None = None
    concurrent_audits: int | None = None
    taken: bool = False
    why: str = ""
    derived_sec: float | None = None
    licensed: bool = False
    licence_note: str = ""

@dataclass
class Population:
    """The containment population, with its own account of what it examined.

    `declared` and `examined` are separated on purpose: `declared` is the manifest's size,
    `examined` is what this run could actually reach. A population whose `examined` is zero
    has reached no verdict at all, and `note` says so in the run's own output rather than
    leaving a caller to infer it from an empty tuple.

    The three sources are a PARTITION (#564), and it is CHECKED rather than promised (#578):
    `stale` is read exactly as it always was, `growth` claims only the entries staleness does
    not own, and `exhausted` is narrowed against BOTH of them, so the breakdown printed beside
    the total sums to that total. `partition_problems()` is what refuses a breakdown that does
    not — this docstring is not what makes it true.
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
    # The stale entries whose growth marker THIS run cleared, because it moved their wall
    # (#593). A marker describes the wall it was recorded against, so a re-derivation makes
    # it a description of a wall that no longer exists -- and `_growth_source` sizes the
    # streak from marker PRESENCE alone, so a surviving marker arms the entry to move its
    # wall again on the very next SINGLE sample. That is precisely what the report-first
    # rule exists to prevent. Reported in the STALE arm, never folded into `reset`: an entry
    # reset by a round INSIDE the wall is a different event from one re-derived because its
    # basis moved.
    cleared: tuple = ()
    # THE WALL-KILL POPULATION (#604). Deliberately OUTSIDE `keys` and outside
    # `partition_problems`: a kill is not a fourth containment source, it is a fact ABOUT an
    # entry already owned by one of the three (usually STALE, since a killed gate's basis is
    # also refused). Folding it in would double-count every entry it names and break the
    # breakdown arithmetic #578 made a refusal. `probes` is the same shape one step later.
    kills: tuple = ()
    probes: tuple = ()
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
        # read, so BOTH remaining sets are narrowed here against the ones that outrank them:
        # an entry can be stale AND reported UNKNOWN by the same audit (a gate whose blob
        # moved and whose last run died at its wall), and narrowing `exhausted` against
        # `growth` alone left it in two partitions while `pop.keys` -- a set union -- counted
        # it once. The breakdown then rendered 5 + 1 + 11 against a population of 16, and the
        # same key printed under [STALE] and again under [EXHAUSTED] (#578, measured at
        # /tmp/rederive_1028.out:6 and :9, both tests/test_ledger_no_shrink.py).
        stale_keys = {s.key for s in stale}
        exhausted = tuple(
            key for key in exhausted if key not in growth_keys and key not in stale_keys
        )
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
                "round_id": round_id, "present": present,
                # THE RAW UNKNOWN SET, before any narrowing (#604). The containment
                # partitions are narrowed against each other by precedence, so an entry that
                # is BOTH stale and killed appears only under STALE -- and a kill record read
                # from the narrowed set would therefore miss exactly the gates this mechanism
                # exists for. These two are the audit's own account, unfiltered.
                "audit_unknown": tuple(audit.exhausted) if audit is not None else (),
                "completed": (
                    tuple(sorted(set(audit.present) - set(audit.exhausted)))
                    if audit is not None else ()
                )},
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

# ---------------------------------------------------------------------------------------
# #604 — THE WALL-KILL RECORD, THE PROBE, AND THE LICENCE
#
# THE DEADLOCK THIS BREAKS, stated once here rather than in three comments. docs/measurement-procedure.md §5.2 needs a
# COMPLETED sample to move a budget. A gate killed at its declared wall produces `unknown:
# true` and no sample. Two consecutive rounds of that leave the entry with a STALE basis (the
# old sample is refused) and NO fresh sample (the wall prevents one) — both conditions
# checked, both refusing, `HELD` forever, and no lane told why. #579 was broken by a ruling
# because no mechanism existed; #602 was broken BY HAND, outside any tool. The three pieces
# below are that mechanism, and each answers one clause of the order:
#
#   record_wall_kills  — the streak, counted from the audit's own `unknown` flag across rounds,
#                        because a report is one round and "consecutive" needs a surface that
#                        outlives it (the same argument `growth_breach` rests on).
#   run_probes         — ONE quiet-box sample per eligible gate, under a ceiling and a hard
#                        cap, labelled with its regime so the number travels with the box it
#                        was taken on.
#   the licence        — in `apply_rederivation`: the sample is an INPUT to docs/measurement-procedure.md §5.2, never a
#                        bypass, so a wall moves only if the arithmetic produces one that fits
#                        inside the envelope the probe was allowed to run in.
# ---------------------------------------------------------------------------------------

def _manifest_readable(manifest_path: Path) -> bool:
    """Whether the manifest parsed — the difference between an empty record and a blind read."""
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data.get("gates"), dict)

def _wall_kill_rounds(entry: object) -> tuple:
    """The round identities recorded against one entry, newest LAST."""
    if not isinstance(entry, dict):
        return ()
    record = entry.get(WALL_KILLS)
    if not isinstance(record, dict):
        return ()
    rounds = record.get("rounds")
    if not isinstance(rounds, list):
        return ()
    return tuple(r for r in rounds if isinstance(r, str) and r)

def _outstanding_breach(entry: object) -> bool:
    """Whether a growth breach on this entry has NOT yet moved the wall it was reported at.

    KEYED ON THE ARITHMETIC, never on marker PRESENCE — measured, live manifest, and the
    difference is the whole mechanism. 15 entries carry `growth_breach`; ONE
    (`tests/test_patrol_host_state.py`) has a CONSUMED marker because its wall moved
    1185.31 -> 1647.35 after the breach; the other 14 are outstanding. And BOTH deadlocked
    gates carry a marker — #602's is consumed, #579's is outstanding. So a predicate written
    `entry.get(GROWTH_MARKER) is None` excludes the very gate #604 exists to unblock, and
    reproduces the deadlock one layer up: an escape mechanism ineligible on every gate.

    `declared_sec` is written into the marker at report time, so this needs no git ancestry
    and no lane memory — which is what "consecutive is read from the manifest, never from a
    lane's memory" requires anyway.

    STATED RESIDUAL: a wall that moved and later returned to the SAME number reads as
    outstanding. Rare, and it errs toward NOT probing, which is the safe direction — the cost
    is an entry that stays deadlocked a round longer, never a wall moved on a remedy that was
    already working.
    """
    if not isinstance(entry, dict):
        return False
    marker = entry.get(GROWTH_MARKER)
    if not isinstance(marker, dict):
        return False
    declared = marker.get("declared_sec")
    wall = entry.get("budget_sec")
    if not isinstance(declared, (int, float)) or not isinstance(wall, (int, float)):
        # A marker whose own numbers cannot be read is not evidence either way, and the
        # refusal direction is to leave the entry to docs/measurement-procedure.md §5.2 rather than probe it.
        return False
    return abs(float(wall) - float(declared)) < 1e-9

def read_wall_kills(manifest_path: Path) -> tuple:
    """Every entry carrying a kill record, with its streak and its ELIGIBILITY.

    Read from the MANIFEST, never from a lane's memory: a fresh process holding the manifest
    reaches the same verdict with no history of its own, which is what makes the eligibility
    checkable by a peer rather than taken on trust.
    """
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    entries = data.get("gates")
    if not isinstance(entries, dict):
        return ()
    kills: list = []
    for key in sorted(entries):
        entry = entries[key]
        rounds = _wall_kill_rounds(entry)
        if not rounds:
            continue
        declared = entry.get("budget_sec") if isinstance(entry, dict) else None
        declared_sec = float(declared) if isinstance(declared, (int, float)) else 0.0
        streak = len(rounds) >= 2
        outstanding = _outstanding_breach(entry)
        # ELIGIBILITY IS THREE CONJUNCTS, and the second one is why this is not a one-liner:
        #
        #   (a) killed at its own wall in >=2 consecutive rounds — the streak above;
        #   (b) NO OUTSTANDING growth breach — because docs/measurement-procedure.md §5.2's trend clause ALREADY resolves
        #       such an entry from the CARRIED sample (breach + exhaustion = second breach).
        #       A probe there would be an alternative to a remedy that already works, and the
        #       mechanism exists for entries nothing else can move;
        #   (c) no fresh completed sample — STRUCTURAL, not a conjunct: a completed run CLEARS
        #       the record, so a surviving streak of >=2 already means none completed. Stated
        #       rather than coded, because a second check of the same fact would be a second
        #       definition that can drift from the first.
        eligible = streak and not outstanding
        if eligible:
            why = (
                f"killed at its declared wall in {len(rounds)} consecutive round(s), and no "
                f"outstanding breach: the wall is what prevents the sample that would move it"
            )
        elif not streak:
            why = (
                "killed at its declared wall in ONE round — contention is the likelier "
                "reading, and the mechanism fires only on a streak"
            )
        else:
            why = (
                f"killed in {len(rounds)} consecutive round(s) BUT a growth breach is "
                f"OUTSTANDING (the wall has not moved since it was reported), so docs/measurement-procedure.md §5.2's "
                f"trend clause already owns this entry from its carried sample — a probe "
                f"would be an alternative to a remedy that works"
            )
        kills.append(
            WallKill(
                key=key,
                rounds=rounds,
                consecutive=len(rounds),
                declared_sec=declared_sec,
                eligible=eligible,
                why=why,
                outstanding_breach=outstanding,
            )
        )
    return tuple(kills)

def record_wall_kills(
    pop: Population,
    manifest_path: Path,
    root: Path | None = None,
) -> Population:
    """Record this round's kills, and CLEAR the streak of every gate that completed.

    THE CLEAR IS THE HALF THAT MAKES THE COUNT TRUE. A completed run — passing OR failing —
    breaks the streak by definition, so leaving the record behind would let a gate that
    finished yesterday be probed today on a streak that no longer exists. It is cleared here,
    at the record, rather than inferred at the read.

    IDEMPOTENT ON THE ROUND, never on the clock: a re-run of the SAME audit report finds its
    own `round_id` already in the record and appends nothing, so replaying a report cannot
    manufacture a second kill out of one round. That is the same property `growth_breach`
    gets from recording the reporting round's identity, and it is why the identity is the
    report's own (`date:head_sha`), not the write time.
    """
    audit_unknown = tuple(pop.extras.get("audit_unknown") or ())
    completed = tuple(pop.extras.get("completed") or ())
    round_id = pop.extras.get("round_id")
    if not audit_unknown and not completed:
        pop.kills = read_wall_kills(manifest_path)
        # `read_wall_kills` returns () for BOTH "nothing is recorded" and "the manifest could
        # not be read", and those are different facts with the same shape (#595's own class).
        # So the read state is carried explicitly and the renderer may not claim a clean
        # record it never saw.
        pop.extras[WALL_KILLS_READ] = bool(pop.kills) or _manifest_readable(manifest_path)
        # NO AUDIT REPORT means the record was NOT ADVANCED: whatever it holds is what an
        # EARLIER round left, and an empty one says nothing about this round's gates. The
        # renderer must say that, not "every declared wall was met".
        pop.extras[WALL_KILLS_SOURCE] = (
            KILL_SOURCE_NO_AUDIT if pop.extras[WALL_KILLS_READ] else KILL_SOURCE_UNREAD
        )
        return pop
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pop.kills = ()
        pop.extras[WALL_KILLS_READ] = False
        pop.extras[WALL_KILLS_SOURCE] = KILL_SOURCE_UNREAD
        return pop
    entries = data.get("gates")
    if not isinstance(entries, dict):
        pop.kills = ()
        pop.extras[WALL_KILLS_READ] = False
        pop.extras[WALL_KILLS_SOURCE] = KILL_SOURCE_UNREAD
        return pop

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    changed = False
    for key in audit_unknown:
        entry = entries.get(key)
        if not isinstance(entry, dict) or not round_id:
            continue
        rounds = list(_wall_kill_rounds(entry))
        if round_id in rounds:
            continue  # this round already counted — a re-run is not a new kill
        rounds.append(round_id)
        entry[WALL_KILLS] = {"rounds": rounds[-WALL_KILLS_KEEP:], "recorded_at": now}
        changed = True
    for key in completed:
        entry = entries.get(key)
        if isinstance(entry, dict) and entry.pop(WALL_KILLS, None) is not None:
            changed = True
    if changed:
        # `root` follows this leg's own convention (`containment_population`,
        # `apply_rederivation`): production passes nothing and the live tree is used, while a
        # probe validates its throwaway manifest against the tree it was built in.
        _write_manifest(data, manifest_path, root or REPO_ROOT, entries)
    pop.kills = read_wall_kills(manifest_path)
    pop.extras[WALL_KILLS_READ] = True
    pop.extras[WALL_KILLS_SOURCE] = KILL_SOURCE_ROUND
    return pop

def _load_avg() -> float | None:
    """The box's own load, as the regime field records it. None when it cannot be read."""
    try:
        return round(os.getloadavg()[0], 2)
    except (OSError, AttributeError):
        return None

def _concurrent_gate_processes(exclude: set) -> int:
    """How many OTHER audit or pytest processes are live on this box right now.

    THE PROBE MUST BE EXCLUSIVE, and this is the mechanical test of it: a sample taken beside
    a peer's suite measures the BOX, not the gate, and #602's own filing is what that costs —
    a runtime read at loadavg 47.18 was reported as the gate's.

    READ FROM /proc, never `pgrep -f`: a name-wide pattern matches every lane's copy of the
    same tools out of its own worktree, and it also matches the shell that typed it. Here the
    exclusion set is OUR pid and OUR parent, and nothing else is claimed about ownership.
    """
    count = 0
    try:
        procs = list(Path("/proc").iterdir())
    except OSError:
        return 0
    for path in procs:
        if not path.name.isdigit() or int(path.name) in exclude:
            continue
        try:
            raw = (path / "cmdline").read_bytes()
        except OSError:
            continue
        if not raw:
            continue
        cmd = raw.replace(b"\x00", b" ").decode("utf-8", "replace")
        if "tools/audit.py" in cmd or "pytest" in cmd:
            count += 1
    return count

def _gate_invocation(root: Path, key: str) -> str:
    """The gate's DECLARED invocation form, read from the audit's own registration.

    NEVER COMPOSED HERE. A probe that invented an argv would measure a command no round runs,
    and the number it produced would describe something else — the unit/predicate mismatch
    this manifest's own header spends a paragraph on. The registration is the surface
    `tools/audit.py` is built from, so the probe runs the gate the way the audit runs it; the
    projection carries `<sys.executable>` for the interpreter, substituted here.

    Empty string means the registration does not name this gate, and the caller REPORTS that
    rather than probing something adjacent.
    """
    try:
        text = (root / "tools" / "audit.py").read_text(encoding="utf-8")
    except OSError:
        return ""
    reader = _registration_reader()
    if reader is None:
        return ""
    for entry in reader(text):
        if entry.get("target") == key:
            return str(entry.get("argv") or "").replace("<sys.executable>", sys.executable)
    return ""

def _gate_blob(root: Path, key: str) -> str:
    """The gate file's blob at HEAD — what a refusal record is armed against.

    A refusal describes the gate THAT WAS PROBED. When the gate itself changes — the #602
    remedy is a SPLIT, which moves it — the refusal no longer describes what runs, and the
    blob is what re-arms the probe without anyone having to remember to clear a field.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", f"HEAD:{key}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""

def run_probes(
    pop: Population,
    manifest_path: Path,
    root: Path,
    quiet_check=None,
) -> Population:
    """Take ONE quiet-box sample per ELIGIBLE gate and hand it to the ordinary derivation.

    FOUR REFUSALS, each REPORTED rather than silently skipped, because "no sample" and "never
    tried" are different facts with the same shape:

      - no registered invocation — there is no declared command to probe;
      - a refusal already recorded against this gate's BLOB — re-probing an unchanged gate
        would re-learn the same arithmetic at the cost of a 25-minute run;
      - the box is not quiet — a sample beside a peer's suite measures the box;
      - the gate does not complete inside the probe ceiling — the envelope failed too, so
        there is still no sample to license a wall.

    A sample is taken ONLY from a run that exits 0. A FAILED run measures how fast the gate
    refused, never how long the work takes (#558), and a kill at the ceiling is the same
    lower-bound trap the audit's own `unknown` flag exists to prevent.

    `quiet_check` is the count of OTHER live audit/pytest processes, injectable because the
    precondition is ENVIRONMENTAL and the logic is what a probe can test: under a test runner
    the runner itself is always live, so the real check would refuse every probe and the
    mechanism would read as untestable rather than as tested. Production passes nothing and
    gets the /proc scan.

    The sample is injected into `extras["samples"]` so the ORDINARY derivation consumes it —
    this function decides nothing about a wall. Its own verdict is `licensed`, computed from
    the same margin law the derivation uses, so the number a reader sees here is the number
    the wall would move to.
    """
    eligible = [k for k in pop.kills if k.eligible]
    if not eligible:
        return pop
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return pop
    entries = data.get("gates")
    if not isinstance(entries, dict):
        return pop

    samples = dict(pop.extras.get("samples") or {})
    probe_samples: dict = dict(pop.extras.get("probe_samples") or {})
    probes: list = []
    for kill in eligible:
        entry = entries.get(kill.key)
        declared = entry.get("budget_sec") if isinstance(entry, dict) else None
        declared_sec = (
            float(declared) if isinstance(declared, (int, float)) else kill.declared_sec
        )
        ceiling = round(declared_sec * PROBE_CEILING_FACTOR, 2)
        effective = min(ceiling, PROBE_HARD_CAP_SEC)
        invocation = _gate_invocation(root, kill.key)
        if not invocation:
            probes.append(
                ProbeSample(
                    key=kill.key,
                    ceiling_sec=ceiling,
                    hard_cap_sec=PROBE_HARD_CAP_SEC,
                    taken=False,
                    why="no registered invocation — the audit's own registration does not name "
                        "this gate, so there is no declared command to probe",
                )
            )
            continue
        blob = _gate_blob(root, kill.key)
        refused = entry.get(PROBE_REFUSED_FIELD) if isinstance(entry, dict) else None
        if isinstance(refused, dict) and blob and refused.get("gate_blob") == blob:
            probes.append(
                ProbeSample(
                    key=kill.key,
                    invocation=invocation,
                    ceiling_sec=ceiling,
                    hard_cap_sec=PROBE_HARD_CAP_SEC,
                    sample_sec=refused.get("sample_sec"),
                    taken=False,
                    why="a REFUSED probe is already recorded against this gate's blob "
                        f"{blob[:12]}: {refused.get('why')} — re-probing an unchanged gate "
                        "would re-learn the same arithmetic",
                )
            )
            continue
        concurrent = (
            quiet_check()
            if quiet_check is not None
            else _concurrent_gate_processes({os.getpid(), os.getppid()})
        )
        load_start = _load_avg()
        if concurrent > 0:
            probes.append(
                ProbeSample(
                    key=kill.key,
                    invocation=invocation,
                    ceiling_sec=ceiling,
                    hard_cap_sec=PROBE_HARD_CAP_SEC,
                    load_at_start=load_start,
                    concurrent_audits=concurrent,
                    taken=False,
                    why=f"the box is NOT quiet — {concurrent} other audit/pytest process(es) "
                        "are live, and a sample taken beside them measures the box",
                )
            )
            continue

        started = time.monotonic()
        try:
            proc = subprocess.Popen(
                shlex.split(invocation),
                cwd=str(root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except (OSError, ValueError) as exc:
            probes.append(
                ProbeSample(
                    key=kill.key,
                    invocation=invocation,
                    ceiling_sec=ceiling,
                    hard_cap_sec=PROBE_HARD_CAP_SEC,
                    load_at_start=load_start,
                    taken=False,
                    why=f"the declared command could not be started ({exc})",
                )
            )
            continue
        try:
            rc = proc.wait(timeout=effective)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                proc.kill()
            proc.wait()
            rc = None
        elapsed = round(time.monotonic() - started, 2)
        finish_load = _load_avg()

        if rc is None:
            probes.append(
                ProbeSample(
                    key=kill.key,
                    invocation=invocation,
                    sample_sec=elapsed,
                    ceiling_sec=ceiling,
                    hard_cap_sec=PROBE_HARD_CAP_SEC,
                    load_at_start=load_start,
                    load_at_finish=finish_load,
                    concurrent_audits=0,
                    taken=False,
                    why=f"killed at the probe ceiling {effective} s — the gate does not "
                        "complete inside the envelope either, so there is still no sample",
                )
            )
            continue
        if rc != 0:
            probes.append(
                ProbeSample(
                    key=kill.key,
                    invocation=invocation,
                    sample_sec=elapsed,
                    rc=rc,
                    ceiling_sec=ceiling,
                    hard_cap_sec=PROBE_HARD_CAP_SEC,
                    load_at_start=load_start,
                    load_at_finish=finish_load,
                    concurrent_audits=0,
                    taken=False,
                    why=f"completed with rc={rc} — a FAILED run measures how fast the gate "
                        "refused, never how long the work takes (#558)",
                )
            )
            continue

        # THE TWO BOUNDS, and why they are DIFFERENT NUMBERS. The CEILING bounds how long the
        # probe may RUN; the HARD CAP bounds the WALL a sample may license. They cannot be the
        # same bound, because docs/measurement-procedure.md §5.2 multiplies by ~4: a gate that finished in 1.5 s against a
        # 1.0 s wall derives a 6.75 s wall, and a ceiling-shaped licence (2.0 s) would refuse
        # the ordinary re-derivation it exists to produce. Measured, not argued — a
        # ceiling-shaped predicate refuses every legitimate probe AND #602's, which makes it
        # a predicate that cannot discriminate and therefore proves nothing.
        #
        # #602 is refused by the CAP: margin_for(1496) = 4.000501, so 1496 s licenses 5984.75 s
        # against a 3600 s cap. That is not a budget, it is an outage, and the arithmetic says
        # so without anyone judging the case by eye.
        derived = round(margin_for(elapsed) * elapsed, 2)
        licensed = derived <= PROBE_HARD_CAP_SEC
        probe = ProbeSample(
            key=kill.key,
            invocation=invocation,
            sample_sec=elapsed,
            rc=0,
            ceiling_sec=ceiling,
            hard_cap_sec=PROBE_HARD_CAP_SEC,
            load_at_start=load_start,
            load_at_finish=finish_load,
            concurrent_audits=0,
            taken=True,
            derived_sec=derived,
            licensed=licensed,
            licence_note=(
                f"margin_for({elapsed}) = {margin_for(elapsed):.6f}, so the derivation gives "
                f"{derived} s against the hard cap of {PROBE_HARD_CAP_SEC} s — "
                + ("LICENSED" if licensed else "REFUSED, so no wall moves")
            ),
        )
        probes.append(probe)
        samples[kill.key] = max(samples.get(kill.key, 0.0), elapsed)
        probe_samples[kill.key] = probe

    pop.probes = tuple(probes)
    pop.extras["samples"] = samples
    pop.extras["probe_samples"] = probe_samples
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

    IT ALSO CLEARS THE GROWTH MARKER OF EVERY ENTRY WHOSE WALL IT MOVES (#593). A marker
    records the wall it was taken against; `_growth_source` sizes the streak from marker
    PRESENCE alone, so a marker left behind a moved wall makes the NEXT round read as a
    SECOND consecutive breach and re-derive on one sample -- the report-first rule defeated by
    a record of a breach that has already been repaired. The growth branch has always done
    this; the ordinary branch did not, and a STALE entry only ever takes the ordinary branch.
    A run WITHOUT `--apply` moves no wall and therefore clears nothing: the marker there still
    describes a live breach, and the STALE arm says so by omitting the clear.
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
    cleared: list = []
    refused: list = []
    probe_applied: list = []
    growth_keys = {g.key for g in pop.growth}
    stale_keys = {s.key for s in pop.stale}
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
        # THE LICENCE (#604). A probe sample is an INPUT to docs/measurement-procedure.md §5.2, never a bypass: the sample
        # decides nothing on its own, the arithmetic does. The probe was allowed to run for at
        # most `ceiling` seconds, so a sample taken there can only license a wall the same
        # arithmetic places INSIDE that envelope — anything larger is a number no run has ever
        # demonstrated, and writing it would make the manifest assert a wall nothing supports.
        # #602 is the instance: 4.001 x 1496 = 5984.75 s against a gate whose own wall is
        # 1496 s is not a budget, it is an outage, and the ceiling is what says so without
        # anyone having to judge the case by eye.
        probe = (pop.extras.get("probe_samples") or {}).get(key)
        if probe is not None:
            derived = round(margin_for(float(sample)) * float(sample), 2)
            if derived > PROBE_HARD_CAP_SEC:
                why = (
                    f"PROBE SAMPLE REFUSED — {round(float(sample), 2)} s licenses {derived} s "
                    f"at margin {margin_for(float(sample)):.6f}, above the hard cap "
                    f"{PROBE_HARD_CAP_SEC} s; the wall is left EXACTLY as it is"
                )
                refused.append((key, why))
                # The refusal is recorded AGAINST THE GATE'S BLOB, so the probe is not re-run
                # until the gate itself changes. A remedy that splits the gate moves the blob
                # and re-arms it; remembering to clear a field does not scale, and a record
                # that outlives its subject reads as a live verdict.
                entry[PROBE_REFUSED_FIELD] = {
                    "gate_blob": _gate_blob(root, key),
                    "sample_sec": round(float(sample), 2),
                    "derived_sec": derived,
                    "ceiling_sec": probe.ceiling_sec,
                    "why": why,
                    "recorded_at": measured_at,
                }
                entry.pop(WALL_KILLS, None)
                continue
            entry[PROBE_SAMPLE_FIELD] = True
            entry[PROBE_REGIME_FIELD] = {
                "sample_sec": probe.sample_sec,
                "ceiling_sec": probe.ceiling_sec,
                "load_at_start": probe.load_at_start,
                "load_at_finish": probe.load_at_finish,
                "concurrent_audits": probe.concurrent_audits,
                "invocation": probe.invocation,
                "taken_at": measured_at,
            }
            entry.pop(PROBE_REFUSED_FIELD, None)
            entry.pop(WALL_KILLS, None)
            probe_applied.append(key)
        else:
            # An ORGANIC sample clears the probe provenance: the wall now rests on a run the
            # ordinary audit took, so a leftover `probe_sample` flag would keep describing a
            # number that is no longer the basis — the same stale-record class as the marker.
            entry.pop(PROBE_SAMPLE_FIELD, None)
            entry.pop(PROBE_REGIME_FIELD, None)
            entry.pop(PROBE_REFUSED_FIELD, None)
        entry["measured_sec"] = round(float(sample), 2)
        entry["margin_x"] = round(margin_x, 3)
        entry["budget_sec"] = round(margin_x * float(sample), 2)
        entry["measured_at"] = measured_at
        if load is not None:
            entry["load_at_measure"] = load
        # THE MARKER DIES WITH THE WALL IT DESCRIBED (#593). A stale entry reaches this arm
        # because its BASIS moved, and its remedy is a re-derivation whatever the sample's
        # size -- so the wall below really does move, and a marker left behind would describe
        # a wall that no longer exists. `_growth_source` sizes the streak from marker PRESENCE
        # alone (`consecutive=2 if marker is not None and not _same_round(...)`), so a
        # surviving marker arms this entry to re-derive again on the NEXT SINGLE sample: the
        # report-first rule defeated by a record of a breach that has already been repaired.
        # The growth branch above has always popped for exactly this reason; this arm is the
        # one that did not.
        if key in stale_keys and entry.pop(GROWTH_MARKER, None) is not None:
            cleared.append(key)
        applied.append(key)

    pop.extras["probe_refused"] = tuple(refused)
    pop.extras["probe_applied"] = tuple(probe_applied)
    if applied or refused:
        # The manifest's own loader is the gate on the write: it refuses a derivation its
        # numbers contradict, so the swap only happens when the result reads back sound.
        # A REFUSAL ALSO WRITES (#604): the record it leaves is what stops the probe being
        # re-run against an unchanged gate, so it is state, not a message.
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
                cleared=(),
                note=(
                    f"REFUSED — the re-derived manifest does not read back with all "
                    f"{len(entries)} declared entries, so it was NOT written; "
                    f"{manifest_path} is unchanged"
                ),
                extras=pop.extras,
                kills=pop.kills,
                probes=pop.probes,
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
        cleared=tuple(cleared),
        note=pop.note,
        extras=pop.extras,
        kills=pop.kills,
        probes=pop.probes,
    )


def partition_problems(pop: Population) -> tuple:
    """The containment set's own arithmetic, CHECKED instead of asserted in prose (#578).

    `pop.keys` is a SET UNION, so it deduplicates; the printed breakdown sums three tuple
    lengths, which does not. Any entry claimed by two sources therefore makes the breakdown
    exceed the population it renders, and the same key prints twice under two headings. The
    narrowing at the read site keeps the three sources disjoint TODAY; this guard is what
    keeps the PROPERTY, because `Population` carries five further fields (`reported`,
    `reset`, `not_examined`, `held`, `applied`) and the next source added to that union
    re-opens the class silently.

    Returns the problems, never raises: a caller states them and refuses. The comment that
    used to sit above the read site claimed the sum held while it did not, which is why a
    defect this visible survived review -- a comment cannot fail, and that one did not.
    """
    breakdown = len(pop.stale) + len(pop.growth) + len(pop.exhausted)
    population = len(pop.keys)
    if breakdown == population:
        return ()
    problems = [
        f"the printed breakdown does not sum to the population it renders: "
        f"{len(pop.stale)} stale + {len(pop.growth)} growth + {len(pop.exhausted)} exhausted "
        f"= {breakdown}, against {population} entr{'y' if population == 1 else 'ies'} in the "
        f"containment set"
    ]
    seen: dict = {}
    for source, keys in (
        ("stale", [s.key for s in pop.stale]),
        ("growth", [g.key for g in pop.growth]),
        ("exhausted", list(pop.exhausted)),
    ):
        for key in keys:
            seen.setdefault(key, []).append(source)
    for key, sources in sorted(seen.items()):
        if len(sources) > 1:
            problems.append(
                f"{key} is claimed by {len(sources)} partitions ({', '.join(sources)}) — one "
                f"partition, one owner"
            )
    return tuple(problems)


def render(pop: Population) -> str:
    """The population, printed with its count — the run's own account of what it examined."""
    # NO CALLER PRINTS A BREAKDOWN THAT FAILS ITS OWN ARITHMETIC (#578). The check lives here
    # as well as in `main()` so a future caller cannot bypass it by rendering directly.
    problems = partition_problems(pop)
    if problems:
        raise ValueError(
            "refusing to render a containment breakdown that does not sum: "
            + " | ".join(problems)
        )
    lines = [
        f"Gate-budget re-derivation leg — {pop.declared} declared entr"
        f"{'y' if pop.declared == 1 else 'ies'}, {pop.examined} examined",
        f"  {pop.note or 'no sweep note'}",
        f"  population: {len(pop.keys)} entr{'y' if len(pop.keys) == 1 else 'ies'} "
        f"in the containment set "
        f"({len(pop.stale)} by a moved basis, {len(pop.exhausted)} by an exhausted budget, "
        f"{len(pop.growth)} by growth)",
    ]
    cleared_keys = set(pop.cleared)
    for stale in pop.stale:
        line = f"    [STALE] {stale.key} — legs {', '.join(stale.legs)}: {stale.detail}"
        if stale.key in cleared_keys:
            # REPORTED IN THE STALE ARM (#593): the entry is already named here, so the clear
            # costs no new population. Never folded into [RESET], which states a round that
            # came back INSIDE the wall -- a different event from a re-derivation.
            line += (
                "; its growth marker was CLEARED by this run's re-derivation — the wall it "
                "described has moved, so it no longer arms the next single sample"
            )
        lines.append(line)
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
    # ---- #604: the wall-kill streak, the probe, and what the licence decided ----
    # THE CLEAN CLAIM IS GATED ON A READ THAT HAPPENED (#595's ordering lesson, applied here
    # before it could bite twice): an empty kill record and an unreadable manifest are the
    # same value and different facts, so "no gate was killed" prints only when the record was
    # actually READ.
    kills_read = bool(pop.extras.get(WALL_KILLS_READ))
    if pop.kills:
        for kill in pop.kills:
            # THE REASON IS CARRIED, NEVER RE-DERIVED HERE. Ineligibility has TWO causes
            # (#604's ruling, n=4631): a single kill, or an outstanding growth breach that
            # docs/measurement-procedure.md §5.2 already owns. A render that printed "ONE round is contention" for both
            # would name the wrong cause on the second, and the reader would go looking for
            # a streak that was never the problem.
            lines.append(
                f"    [WALL KILL] {kill.key} — killed at its declared {kill.declared_sec} s wall "
                f"in {kill.consecutive} consecutive round(s) ({', '.join(kill.rounds)})"
                + ("" if kill.eligible else f" — NOT ELIGIBLE: {kill.why}")
            )
    elif kills_read:
        # EMPTY IS A READING, NEVER A CLEAN BILL (HQ's #604 clause, and the same ordering
        # rule #595 fixed one leg over). The record is written FROM the audit's unknown flag,
        # so it is empty BY CONSTRUCTION on the round that introduces it, and an empty record
        # asserts only that no kill has been OBSERVED — never that no wall was ever exceeded.
        # The old wording here said "every declared wall was met", which claims a history the
        # record does not have: exactly the shape that reads as current and is not.
        source = pop.extras.get(WALL_KILLS_SOURCE)
        if source == KILL_SOURCE_ROUND:
            lines.append(
                "  wall kills: no gate carries a kill record — the record was READ and "
                "advanced this round and holds nothing, which is a READING, not a clean bill: "
                "it advances only from an audit report's unknown flag, so it says no gate was "
                "OBSERVED killed, never that no wall was ever exceeded"
            )
        else:
            lines.append(
                "  wall kills: unstated (the record was NOT advanced this round) — no audit "
                "report was read, so an empty record here is an INABILITY, not a clean result"
            )
    else:
        lines.append(
            "  wall kills: unstated (not read) — the kill record could not be read, so an "
            "empty record here is an INABILITY, not a clean result"
        )
    eligible = [k for k in pop.kills if k.eligible]
    probe_applied = set(pop.extras.get("probe_applied") or ())
    for probe in pop.probes:
        regime = (
            f"load {probe.load_at_start}->{probe.load_at_finish}, "
            f"{probe.concurrent_audits} concurrent audit/pytest process(es)"
        )
        if not probe.taken:
            lines.append(
                f"    [NOT PROBED] {probe.key} — {probe.why}"
                + (f" (ceiling {probe.ceiling_sec} s, hard cap {probe.hard_cap_sec} s)" if probe.ceiling_sec else "")
            )
            continue
        lines.append(
            f"    [PROBED] {probe.key} — the declared invocation completed in "
            f"{probe.sample_sec} s on a quiet box ({regime}); {probe.licence_note}"
            + (
                ""
                if probe.licensed and probe.key in probe_applied
                else (
                    f" — a run with --apply re-derives the wall"
                    if probe.licensed
                    else " — NOTHING MOVES"
                )
            )
        )
    if eligible and not pop.probes:
        lines.append(
            "  probes: unstated (not taken) — eligible gates exist but no probe ran, so this "
            "round states no sample for them"
        )
    for key, why in pop.extras.get("probe_refused") or ():
        lines.append(f"    [LICENCE REFUSED] {key} — {why}")
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


def build_parser() -> argparse.ArgumentParser:
    """The leg's own argument surface, so a probe can assert its DEFAULTS.

    A parser buried inside `main()` is only reachable by running the whole leg, so the one
    property #604 rests on — that the probe fires when NO flag is given — could not be
    asserted without invoking it against the live manifest.
    """
    parser = argparse.ArgumentParser(description="Gate-budget re-derivation leg (#269).")
    parser.add_argument("--manifest", type=str, default="", help="Manifest path (default: the live one)")
    parser.add_argument("--repo-root", type=str, default="", help="Repo root (default: this tree)")
    parser.add_argument("--audit-report", type=str, default="", help="An audit --json report to read samples from")
    parser.add_argument("--apply", action="store_true", help="Re-derive and write the manifest")
    # DEFAULT ON, and that is the load-bearing half of #604's last clause. The issue says the
    # escape must NOT remain a hand-run one: `#602` was broken by hand, outside any tool, and
    # the next gate in this class deadlocks identically while no lane knows the escape exists.
    # A flag a caller has to remember is the same hand-run escape wearing an argument, and the
    # daily measurement round invokes this leg with NO flags — so opt-in would have shipped a
    # mechanism that never fires. It costs nothing in the ordinary case: no gate has a kill
    # record, so no probe runs. `--no-probe` turns it off explicitly.
    parser.add_argument(
        "--probe",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Take ONE quiet-box sample per gate killed at its own wall for >=2 consecutive "
            "rounds (#604). ON by default, because an escape nobody invokes is not one; "
            "use --no-probe to disable. The sample is an INPUT to the derivation, never a "
            "bypass: a wall moves only if the arithmetic fits under the hard cap."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit the population as JSON")
    return parser

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    manifest = Path(args.manifest) if args.manifest else gates_manifest_path()
    root = Path(args.repo_root) if args.repo_root else REPO_ROOT
    report = Path(args.audit_report) if args.audit_report else None

    pop = containment_population(manifest, root, report)

    # THE PARTITION IS CHECKED BEFORE ANYTHING IS PRINTED (#578). Both output paths pass
    # through here, so neither the human breakdown nor the JSON payload can report a
    # containment set whose parts contradict its total.
    partition = partition_problems(pop)
    if partition:
        print(
            "REFUSED — the containment population's own arithmetic does not hold, so this run "
            "reaches NO verdict and prints no breakdown:"
        )
        for problem in partition:
            print(f"  {problem}")
        return EXIT_REFUSED

    # THE REPORTING PATH WRITES ITS OWN RECORD (#564). Deliberately before `--apply` and not
    # behind it: a first breach is REPORTED, and the record of that report is what lets the
    # next round tell a trend from a one-off. It never touches a wall.
    pop = record_growth_state(pop, manifest)
    # THE KILL STREAK (#604), recorded on EVERY run and not behind `--apply`: the streak is
    # the eligibility evidence, and a record that only advanced on the run that acts would
    # never accumulate the two rounds it needs. It never touches a wall.
    pop = record_wall_kills(pop, manifest)

    # THE PROBE (#604) runs BEFORE `--apply`, so one invocation can take the sample and
    # re-derive from it. ON by default (see the flag's own comment): the eligibility gate is
    # what makes that safe — nothing runs until a gate has been killed at its own wall in two
    # consecutive rounds — and the quiet check refuses the sample whenever a peer's run is
    # live, which is the concurrent-run pile #597 exists to stop.
    if args.probe:
        pop = run_probes(pop, manifest, root)

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
                    "cleared": list(pop.cleared),
                    "held": [{"key": k, "why": w} for k, w in pop.held],
                    "wall_kills_read": bool(pop.extras.get(WALL_KILLS_READ)),
                    "wall_kills": [
                        {
                            "key": k.key,
                            "rounds": list(k.rounds),
                            "consecutive": k.consecutive,
                            "declared_sec": k.declared_sec,
                            "eligible": k.eligible,
                            "why": k.why,
                        }
                        for k in pop.kills
                    ],
                    "probes": [
                        {
                            "key": pr.key,
                            "invocation": pr.invocation,
                            "sample_sec": pr.sample_sec,
                            "rc": pr.rc,
                            "ceiling_sec": pr.ceiling_sec,
                            "hard_cap_sec": pr.hard_cap_sec,
                            "load_at_start": pr.load_at_start,
                            "load_at_finish": pr.load_at_finish,
                            "concurrent_audits": pr.concurrent_audits,
                            "taken": pr.taken,
                            "why": pr.why,
                            "derived_sec": pr.derived_sec,
                            "licensed": pr.licensed,
                            "licence_note": pr.licence_note,
                        }
                        for pr in pop.probes
                    ],
                    "probe_refused": [
                        {"key": k, "why": w}
                        for k, w in (pop.extras.get("probe_refused") or ())
                    ],
                    "probe_applied": list(pop.extras.get("probe_applied") or ()),
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
