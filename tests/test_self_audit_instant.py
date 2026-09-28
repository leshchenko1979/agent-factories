#!/usr/bin/env python3
"""Gate: a committed self-audit artifact NAMES the instant it read the ledger.

Origin (issue #142, ruled at ledger n=919). The self-audit reads the LEDGER, which is
appended during its own run — its own row lands after the parse, and concurrent lanes
append throughout the gate window. Its figures are therefore a property of the INSTANT
(measured on AI AntiSpam: the artifact reported `Total Ledger Events: 10` / yield 28.6%
while the live ledger held 11 rows / 37.5%), and section 8 binds that such a measurement
"must name the instant it read". The artifact named only a DATE, so it was neither
replayable from recorded inputs NOR readable as fresh.

The ORDER does not move (Q2 of the ruling): parse-before-append is the only non-circular
order, because the run row's own yield comes from that same parse, so artifact and row
are twins of ONE measurement.

Three parts, the shape `tests/test_score_artifact_sections.py` already uses:

1. **A pure predicate.** `missing_read_instant(text)` is factored out so a synthetic
   artifact can probe it — a rule that has only ever seen good input has not been shown
   to reject bad input.
2. **A forward-only requirement with a boundary.** An artifact dated strictly AFTER
   `INVARIANT_LANDED` must name the instant in a PARSEABLE form. The boundary is
   EXCLUSIVE because the artifacts for earlier days are already committed, and an instant
   written in after the fact is fabricated provenance — the no-backfill law. Pre-boundary
   artifacts are printed as `excused:` with their count, so "clean" and "excused" are
   never the same output.
3. **A coupling to the procedure.** The requirement must be stated where the RUN reads
   it, not only where the gate does: a rule stated nowhere the operator looks enforces
   nothing. The coupling probe asserts the Process 1 row in `docs/processes.md` names it.

WHY THIS SURFACE WAS UNGATED. `tests/test_score_artifact_sections.py` excludes it in its
own words — its `artifacts()` docstring reads "Every dated score artifact, oldest first.
`*-self-audit.md` is not one." — so nothing covered the artifact the procedure's most
load-bearing step produces. This gate is that covering, and it judges ONE property, the
one the ruling named.

THE LIVE POPULATION IS LEGITIMATELY EMPTY until the next instance lands, so non-vacuity
rides a PROBE and never a loud-fail-on-zero (#112). The gate still PRINTS the population
it examined, so a clean read is never indistinguishable from a read that found nothing.

Run:  python3 tests/test_self_audit_instant.py
Exit: 0 all checks pass, 1 a check failed.
"""

from __future__ import annotations

import datetime as dt
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCORES = REPO / "evidence" / "scores"
PROCEDURE = REPO / "docs" / "processes.md"
AUDIT = REPO / "tools" / "audit.py"

# The artifact's filename — `*-self-audit.md` is the ONE this gate judges.
_ARTIFACT_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-self-audit\.md$")

# The instant must be PARSEABLE, not prose: this form is the ledger's own `ts` form, so a
# reader needs no new habit. It is COUPLED to the writer — `READ_INSTANT_FORM` in
# tests/test_self_audit_instant.py asserts the two agree rather than restating the shape.
INSTANT_RE = re.compile(r"`(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)`")

# The boundary, EXCLUSIVE: the day this requirement landed. Artifacts dated at or before it
# are excused and counted; strictly after must comply. A forward-only law, never backfilled.
INVARIANT_LANDED = dt.date(2026, 9, 27)

# The coupling anchor: the Process 1 register row must name the requirement, so a lane
# reading the procedure meets it before the gate does.
COUPLING_ANCHOR = "read instant"


def artifacts() -> list[tuple[dt.date, Path]]:
    """Every committed `*-self-audit.md`, oldest first."""
    out: list[tuple[dt.date, Path]] = []
    for path in sorted(SCORES.glob("*-self-audit.md")):
        match = _ARTIFACT_RE.match(path.name)
        if match is None:
            continue
        year, month, day = (int(g) for g in match.groups())
        out.append((dt.date(year, month, day), path))
    return out


def missing_read_instant(text: str) -> bool:
    """True when the artifact does NOT name a parseable ledger read instant.

    Pure: no file system, no clock — a synthetic artifact probes it directly.
    """
    return INSTANT_RE.search(text) is None


def instant_of(text: str) -> dt.datetime | None:
    """The read instant the artifact states, or None when it states none."""
    match = INSTANT_RE.search(text)
    if match is None:
        return None
    try:
        return dt.datetime.strptime(match.group(1), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=dt.timezone.utc
        )
    except ValueError:
        return None


def instant_leg() -> tuple[list[str], list[str], list[str], bool]:
    """`(excused, checked, problems, declared)` over the live tree.

    Excused artifacts are NAMED, not dropped: a reader must be able to tell the boundary's
    population from the complied population without re-deriving the dates.
    """
    excused: list[str] = []
    checked: list[str] = []
    problems: list[str] = []
    found = artifacts()
    if not found:
        return excused, checked, problems, False
    for day, path in found:
        text = path.read_text(encoding="utf-8")
        if day <= INVARIANT_LANDED:
            excused.append(path.name)
            continue
        checked.append(path.name)
        if missing_read_instant(text):
            problems.append(
                f"{path.name}: names no parseable ledger read instant — section 8 binds a "
                f"measurement of live state to name the instant it read (#142)"
            )
    return excused, checked, problems, True


# --- probes -------------------------------------------------------------------


def probe_the_predicate_BITES_on_an_artifact_naming_no_instant() -> None:
    """Non-vacuity rides THIS probe, never a loud-fail-on-zero (#112).

    The live population is legitimately empty until the next instance lands, so the probe
    is what shows the gate can reject: a synthetic artifact with a date and no instant,
    then the same artifact with the instant and the surrounding statement.
    """
    without = (
        "# Operational Process Self-Audit — 2026-09-28\n\n"
        "> **Verdict:** `PASSED` · Process 3 (Internal Self-Audit)\n"
    )
    assert missing_read_instant(without), (
        "an artifact naming only a date must be rejected — that is the whole defect"
    )
    with_instant = without.replace(
        "> **Verdict:** `PASSED`",
        "> **Ledger read at:** `2026-09-28T06:00:00Z` (1312 events) — as of that instant\n\n"
        "> **Verdict:** `PASSED`",
    )
    assert not missing_read_instant(with_instant), (
        "the instant, stated, must satisfy the read"
    )
    parsed = instant_of(with_instant)
    assert parsed == dt.datetime(2026, 9, 28, 6, 0, 0, tzinfo=dt.timezone.utc), (
        f"the instant must PARSE, not merely appear: got {parsed!r}"
    )


def probe_unparseable_or_partial_instants_are_NOT_accepted() -> None:
    """A date, a bare clock time, or a wrong shape is not an instant.

    `parseable` is the requirement, so the near-misses must fail: each one is prose a
    human reads as an instant while no reader can parse it, which is the shape that made
    the original artifact unreplayable rather than merely undocumented.
    """
    for near_miss in (
        "> **Ledger read at:** 2026-09-28 (a date, no clock)\n",
        "> **Ledger read at:** 06:00:00 (a clock, no date)\n",
        "> **Read at:** 2026-09-28T06:00:00Z (no backticks — not the stated form)\n",
        "> **Ledger read at:** `2026-09-28 06:00` (wrong form)\n",
    ):
        assert missing_read_instant(near_miss), (
            f"must not satisfy the read: {near_miss!r}"
        )
    # The positive arm beside the negatives, so this cannot pass by the predicate having
    # stopped matching at all.
    assert not missing_read_instant("> **Ledger read at:** `2026-09-28T06:00:00Z`\n")


def probe_the_boundary_excuses_earlier_artifacts_and_NAMES_them() -> None:
    """Forward-only: pre-boundary artifacts are excused and counted, never repaired."""
    excused, checked, problems, declared = instant_leg()
    names = {path.name for _day, path in artifacts()}
    assert set(excused) | set(checked) == names, (
        f"every artifact must be either excused or checked, not dropped: "
        f"excused={excused} checked={checked} vs {sorted(names)}"
    )
    assert not (set(excused) & set(checked)), "an artifact cannot be both"
    assert problems == [], f"no artifact may be missing the instant: {problems}"
    print(
        f"  population: {len(names)} artifact(s); excused {len(excused)} "
        f"(pre-boundary, at or before {INVARIANT_LANDED}); checked {len(checked)}; "
        f"declared_here={declared}"
    )
    if not names:
        print("  (no self-audit artifact has landed yet — the population is empty, and the "
              "probes above are what show this gate bites)")


def probe_the_gate_prints_the_population_it_examined() -> None:
    """P29: a clean verdict over an unnamed population is indistinguishable from one that
    examined nothing."""
    assert callable(instant_leg), "the leg must be callable"
    excused, checked, problems, declared = instant_leg()
    assert isinstance(problems, list)
    assert declared == bool(artifacts()), (
        "`declared` must say whether the population existed, so an empty read is reported "
        "as empty rather than as a clean one"
    )


def probe_the_writer_and_this_gate_state_ONE_instant_form() -> None:
    """The coupling that keeps the requirement parseable: one form, two readers.

    A gate that parses a different shape from the one the writer emits is the defect it
    exists to catch, moved one file over. Both sides are read here rather than restated.
    """
    src = AUDIT.read_text(encoding="utf-8")
    assert "READ_INSTANT_FORM = \"%Y-%m-%dT%H:%M:%SZ\"" in src, (
        "the writer's instant form must live in tools/audit.py"
    )
    assert "ledger_read_at" in src, "the writer must capture the instant at the parse"
    assert 'f"> **Ledger read at:** `{ledger_read_at}`' in src, (
        "the artifact's header must render the instant"
    )
    assert "START-OF-RUN SNAPSHOT" in src, (
        "the artifact must say what kind of reading it is — a snapshot, not live state"
    )


def probe_the_procedure_STATES_the_requirement_where_the_run_reads_it() -> None:
    """Coupling: the requirement must live where the RUN reads it, not only in the gate.

    A gate whose rule is stated nowhere the operator looks enforces a rule nobody was
    told (P29's companion): the run produces the artifact, so the register row that names
    the artifact must also name this obligation.
    """
    text = PROCEDURE.read_text(encoding="utf-8")
    row = [ln for ln in text.splitlines() if "**1. Internal Self-Audit**" in ln]
    assert row, "the Process 1 register row must exist in docs/processes.md"
    assert COUPLING_ANCHOR in row[0], (
        f"the Process 1 row must name the {COUPLING_ANCHOR!r} requirement, so a lane "
        f"reading the procedure meets it before the gate does:\n  {row[0]}"
    )
    assert "self-audit.md" in row[0], (
        "the row must keep naming the artifact path the requirement attaches to"
    )


def main() -> int:
# STATED SKIP: docs/processes.md (BOOTSTRAP-created)
    # `docs/processes.md` is BOOTSTRAP-created (it is the factory's own process register), so
    # the tree the kit ships carries none and the coupling probe that reads the Process 1 row
    # has nothing to read (#199). Stated, with the artifact named, rather than a
    # FileNotFoundError out of the tree the kit ships from.
    if not PROCEDURE.is_file():
        print(
            f"self-audit-instant gate: SKIPPED — no {PROCEDURE.relative_to(REPO)} in this tree, "
            f"so the Process 1 register row the coupling probe reads does not exist here. That "
            f"file is BOOTSTRAP-created: a factory writes it, the kit does not."
        )
        return 0
    checks = [
        probe_the_predicate_BITES_on_an_artifact_naming_no_instant,
        probe_unparseable_or_partial_instants_are_NOT_accepted,
        probe_the_boundary_excuses_earlier_artifacts_and_NAMES_them,
        probe_the_gate_prints_the_population_it_examined,
        probe_the_writer_and_this_gate_state_ONE_instant_form,
        probe_the_procedure_STATES_the_requirement_where_the_run_reads_it,
    ]
    failed = 0
    for check in checks:
        try:
            check()
            print(f"  PASS  {check.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL  {check.__name__} — {exc}")
    if failed:
        print(f"self-audit instant gate FAILED: {failed} check(s)")
        return 1
    print(f"self-audit instant gate passed: {len(checks)} check(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
