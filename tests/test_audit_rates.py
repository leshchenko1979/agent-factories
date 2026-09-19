#!/usr/bin/env python3
"""Gate: every rate is reported in a named form, with its denominator and its coverage.

Origin, part 1 (issue #31). `tools/audit.py` emitted a single field called
`rework_rate` whose value was `rework entries ÷ closed subjects` — a per-close rate —
while `evidence/rework.md`'s Rates table used the same two words, "Rework rate", for
the *share* form, `entries ÷ (closed + entries)`. One name, two numbers, and the two
surfaces disagreed by 22 points (58.6% against 37.0%). A reader could not tell which
was meant, and neither could a diff.

Origin, part 2 (issue #34). The factory had no change fail rate at all — the O2
Stability metric the rubric asks for. Adding one is where the same defect returns one
level down, in two shapes: a numerator written by hand (it drifts from the log it
describes, and nothing notices), and a rate published bare (an under-linked numerator
of 0 reads as "nothing ever failed" when the truth is "nothing is linked").

The rules this gate enforces:

1. **Two names, never one.** `rework_rate` is gone. The payload carries
   `rework_share` and `rework_per_close`, and each is computed from the denominator
   its own name states.
2. **The forms cannot collapse.** `share` and `per_close` are equal only when the
   arithmetic is wrong, so equality is a failure rather than a coincidence.
3. **The denominator is reconciled, not assumed.** `close_events` (close rows) travels
   beside `closed_subjects` (distinct work units), and `close_events` must equal the
   close-row count read independently from the ledger — the ledger can be perfectly
   numbered and still report a close nobody took.
4. **All three rates name one population.** The change fail rate's denominator is
   `closed_subjects` — the same population the two rework forms name, never
   `close_events` (rows, not units) and never `git rev-list --count HEAD`.
5. **The change fail rate travels with its coverage.** The payload carries the
   coverage numerator and denominator beside the rate, and the coverage denominator
   is the rework entry count. A rate whose linkage is zero is refused outright: with
   entries in the log and no determinate link, 0 means "nothing is linked", not
   "nothing failed", and publishing it would state the second while meaning the first.
6. **The numerator is derived, not stated.** `test_the_rate_is_derived_not_stated`
   re-reads `evidence/rework.md` and the ledger with a *second* implementation and
   compares. That second parser deliberately reads the Subject cell as the last cell
   rather than index 7, and states its own copy of the Subject vocabulary rather than
   importing the reader's: a gate that borrows the reader's pattern cannot catch the
   reader's pattern being wrong. Independence is the point, not duplication.

**Not restated here:** the empty-Subject-cell rule. `tests/test_rework.py` already
fails on an empty cell, so this gate does not say it twice — a rule in two places
splits the next time one of them changes.

The invariant is factored into `rate_form_problems()` so it can be probed with
synthetic payloads as well as the live one: a rule that only ever sees good input has
not been shown to reject bad input.

7. **An outcome is a FIELD, read from the canonical trailer and validated.** Absent is
   UNKNOWN, never `accepted` (issue #53). The old reader scanned free prose for the first
   `outcome=` substring and never checked the value against the domain, so a sentence
   containing the word read as a verdict and a typo read as a failure. Two live shapes:
   `outcome=` alone in a claim row's prose parsed as the empty string, and a close row
   whose sentence's full stop sat inside the value — `outcome=accepted.` — silently
   dropped a genuinely accepted work unit out of the success set. A bucket key must
   therefore be a domain value, `unstated`, or an explicitly `invalid:` bucket.
8. **The population travels with the rate.** The yield is divided by the rows that STATE
   an outcome, and its coverage says how much of the ledger it speaks for. With rows
   present and none stating an outcome the ratio is null, not 1.0 — the favourable
   fabrication this clause removes. No gate rides on the coverage figure itself (clause
   6): against append-only rows a threshold would be permanently RED with no lawful
   repair.

Run:  python3 -m pytest tests/test_audit_rates.py -q
Exit: 0 clean, non-zero on any rate regression.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AUDIT = REPO / "tools" / "audit.py"
LEDGER = REPO / "evidence" / "ledger.jsonl"
REWORK = REPO / "evidence" / "rework.md"
GATE_CMD = "tests/test_audit_rates.py"

# The reader under test, imported rather than re-implemented: rule 7 is about what
# THIS function does with a detail string, so the probes call it. Its own copy of
# the domain lives below, and the two are compared.
sys.path.insert(0, str(REPO / "tools"))
import audit as audit_reader  # noqa: E402

FORBIDDEN = "rework_rate"
REQUIRED_FORMS = ("rework_share", "rework_per_close")
REQUIRED_FAIL_FIELDS = (
    "change_fail_rate",
    "change_fail_rate_numerator",
    "change_fail_rate_denominator",
    "subject_coverage",
    "subject_coverage_numerator",
    "subject_coverage_denominator",
)

# This file's own copy of the Subject column's vocabulary — see rule 6. `none` is a
# defined answer (the defect was caught before any change landed), not a placeholder.
SUBJECT_NONE = "none"
SUBJECT_WORK_UNIT_RE = re.compile(r"#\d+")

def load_audit() -> dict:
    """Read the live audit payload with the gate suite skipped.

    `--no-gates` is what makes this file safe to register as a gate: without it the
    audit would run this gate, which would run the audit, recursively. The flag
    reports `healthy: null` rather than a green, so a skipped suite is never read
    as a passing one.
    """
    res = subprocess.run(
        [sys.executable, str(AUDIT), "--json", "--no-gates"],
        cwd=REPO,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60,
    )
    assert res.returncode == 0, f"audit exited {res.returncode}: {res.stderr.strip()[:400]}"
    return json.loads(res.stdout)

def ledger_close_counts(path: Path = LEDGER) -> tuple[int, int]:
    """Return (close rows, distinct closed subjects), read straight from the ledger."""
    rows = 0
    subjects: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        ev = json.loads(line)
        if ev.get("event") == "close" and ev.get("subject"):
            rows += 1
            subjects.add(ev["subject"])
    return rows, len(subjects)

def derive_fail_linkage(rework_path: Path = REWORK, ledger_path: Path = LEDGER) -> dict:
    """Recompute the change fail rate's numerator and coverage from the raw files.

    A second implementation, on purpose — see rule 6. It reads the Subject cell as
    the last cell of the row and keeps its own vocabulary, so a slip in the audit's
    parser cannot hide in both.
    """
    closed: set[str] = set()
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        ev = json.loads(line)
        if ev.get("event") == "close" and ev.get("subject"):
            closed.add(ev["subject"])

    entries = 0
    determinate = 0
    failures = 0
    in_entries = False
    for line in rework_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_entries = stripped.lower().startswith("## entries")
            continue
        if not in_entries or not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.split("|")]
        if len(cells) < 8:
            continue
        first = cells[1]
        if not first or first.startswith("Date") or first.startswith("*") or set(first) <= {"-"}:
            continue
        subject = cells[-2]
        entries += 1
        if SUBJECT_WORK_UNIT_RE.fullmatch(subject):
            determinate += 1
            if subject in closed:
                failures += 1
        elif subject == SUBJECT_NONE:
            determinate += 1

    return {
        "closed_subjects": len(closed),
        "total_entries": entries,
        "failures": failures,
        "determinate": determinate,
    }

def derivation_problems(payload: dict, derived: dict) -> list[str]:
    """Every payload field that disagrees with an independent read of the raw files."""
    problems: list[str] = []
    rework = payload.get("rework") or {}
    for field, key in (
        ("change_fail_rate_numerator", "failures"),
        ("change_fail_rate_denominator", "closed_subjects"),
        ("subject_coverage_numerator", "determinate"),
        ("subject_coverage_denominator", "total_entries"),
    ):
        if rework.get(field) != derived[key]:
            problems.append(
                f"{field} is {rework.get(field)!r}, an independent read of the raw files says {derived[key]}"
            )
    return problems

def rate_form_problems(payload: dict) -> list[str]:
    """Every way a payload can state a rate wrongly. Empty list means sound."""
    problems: list[str] = []
    rework = payload.get("rework") or {}
    delivery = payload.get("delivery") or {}

    if FORBIDDEN in rework or FORBIDDEN in payload:
        problems.append(f"a field named {FORBIDDEN!r} is back: one name cannot carry two numbers")

    for form in REQUIRED_FORMS:
        if form not in rework:
            problems.append(f"missing named form {form!r}")

    entries = rework.get("total_entries")
    closed = rework.get("closed_subjects")
    if not isinstance(entries, int) or not isinstance(closed, int):
        problems.append("total_entries and closed_subjects must both be integers")
        return problems
    if closed <= 0:
        problems.append("closed_subjects must be positive for a rate to be defined")
        return problems

    want_share = round(entries / (closed + entries), 4)
    want_per_close = round(entries / closed, 4)
    if rework.get("rework_share") != want_share:
        problems.append(
            f"rework_share {rework.get('rework_share')!r} != {want_share} "
            "(entries / (closed subjects + entries))"
        )
    if rework.get("rework_per_close") != want_per_close:
        problems.append(
            f"rework_per_close {rework.get('rework_per_close')!r} != {want_per_close} "
            "(entries / closed subjects)"
        )
    if entries > 0 and want_share == want_per_close:
        problems.append("the two forms collapsed onto one number: they are not the same measure")

    # --- the change fail rate (#34) ---

    missing = [f for f in REQUIRED_FAIL_FIELDS if rework.get(f) is None]
    if missing:
        problems.append(
            f"the change fail rate is incomplete: missing {', '.join(missing)} — "
            "it is published as a rate with its numerator, its denominator and its linkage coverage"
        )

    cfr = rework.get("change_fail_rate")
    cfr_num = rework.get("change_fail_rate_numerator")
    cfr_den = rework.get("change_fail_rate_denominator")
    cov = rework.get("subject_coverage")
    cov_num = rework.get("subject_coverage_numerator")
    cov_den = rework.get("subject_coverage_denominator")

    if cfr_den is not None and cfr_den != closed:
        problems.append(
            f"change_fail_rate_denominator {cfr_den!r} != closed_subjects {closed!r}: "
            "the three rates must name one population"
        )
    if cov_den is not None and cov_den != entries:
        problems.append(
            f"subject_coverage_denominator {cov_den!r} != total_entries {entries!r}: "
            "the coverage is a share of the rework entries, nothing else"
        )
    if isinstance(cfr_num, int) and isinstance(cfr_den, int) and cfr_den > 0 and cfr is not None:
        want_cfr = round(cfr_num / cfr_den, 4)
        if cfr != want_cfr:
            problems.append(f"change_fail_rate {cfr!r} != {want_cfr} (numerator / denominator)")
    if isinstance(cov_num, int) and isinstance(cov_den, int) and cov_den > 0 and cov is not None:
        want_cov = round(cov_num / cov_den, 4)
        if cov != want_cov:
            problems.append(f"subject_coverage {cov!r} != {want_cov} (determinate / entries)")
    if isinstance(cfr_num, int) and isinstance(cov_num, int) and cfr_num > cov_num:
        problems.append(
            "change_fail_rate_numerator exceeds subject_coverage_numerator: "
            "a failure must be a determinate link"
        )
    if entries > 0 and cov_num == 0:
        problems.append(
            "no rework entry carries a determinate Subject: the numerator is 0 because "
            "nothing is LINKED, not because nothing failed — a rate in that state cannot "
            "be published (an empty rework log is exempt: there is nothing to link)"
        )

    # The two surfaces must name the same work unit as the denominator.
    if rework.get("closed_subjects") != delivery.get("closed_subjects"):
        problems.append("rework and delivery name different closed-subject denominators")
    if delivery.get("closed_tasks") != delivery.get("closed_subjects"):
        problems.append("closed_tasks and closed_subjects disagree")
    if delivery.get("close_events", 0) < delivery.get("closed_subjects", 0):
        problems.append("close_events < closed_subjects: a subject cannot close fewer times than it exists")
    return problems

def test_live_payload_states_both_forms():
    problems = rate_form_problems(load_audit())
    assert not problems, "; ".join(problems)

def test_close_events_reconciles_with_the_ledger():
    payload = load_audit()
    rows, subjects = ledger_close_counts()
    assert payload["delivery"]["close_events"] == rows, (
        f"audit reports {payload['delivery']['close_events']} close rows, the ledger holds {rows}"
    )
    assert payload["delivery"]["closed_subjects"] == subjects, (
        f"audit reports {payload['delivery']['closed_subjects']} closed subjects, "
        f"the ledger holds {subjects}"
    )

def test_the_rate_is_derived_not_stated():
    """The published numerator and coverage must be reproducible from the raw files."""
    problems = derivation_problems(load_audit(), derive_fail_linkage())
    assert not problems, "; ".join(problems)

def test_the_derivation_gate_rejects_a_stated_numerator():
    """The re-derivation must reject a number that was written, not computed."""
    payload = load_audit()
    derived = derive_fail_linkage()
    assert derivation_problems(payload, derived) == [], "the live payload must reproduce"

    bumped = json.loads(json.dumps(payload))
    bumped["rework"]["change_fail_rate_numerator"] += 1
    assert derivation_problems(bumped, derived), "a hand-raised numerator survived the independent read"

    zeroed = json.loads(json.dumps(payload))
    zeroed["rework"]["change_fail_rate_numerator"] = 0
    if derived["failures"] != 0:
        assert derivation_problems(zeroed, derived), "a zeroed numerator survived the independent read"

    dropped = json.loads(json.dumps(payload))
    dropped["rework"]["subject_coverage_denominator"] = 1
    assert derivation_problems(dropped, derived), "a doctored coverage denominator survived the independent read"

def test_gate_is_registered_in_the_audit():
    src = AUDIT.read_text(encoding="utf-8")
    registered = [ln for ln in src.splitlines() if GATE_CMD in ln and "gates_to_run.append" in ln]
    assert registered, f"{GATE_CMD} is not registered in the audit gate list"

def test_synthetic_probes_reject_each_regression():
    """The invariant must reject bad input, not merely accept good input."""
    good = {
        "rework": {
            "total_entries": 17,
            "closed_subjects": 29,
            "rework_share": round(17 / 46, 4),
            "rework_per_close": round(17 / 29, 4),
            "change_fail_rate": round(4 / 29, 4),
            "change_fail_rate_numerator": 4,
            "change_fail_rate_denominator": 29,
            "subject_coverage": round(9 / 17, 4),
            "subject_coverage_numerator": 9,
            "subject_coverage_denominator": 17,
        },
        "delivery": {"closed_subjects": 29, "closed_tasks": 29, "close_events": 31},
    }
    assert rate_form_problems(good) == [], "the synthetic sound payload must pass"

    # 1. The old single-name form reappears.
    single = json.loads(json.dumps(good))
    single["rework"][FORBIDDEN] = single["rework"].pop("rework_share")
    assert any(FORBIDDEN in p for p in rate_form_problems(single))

    # 2. The two forms collapse onto the per-close value.
    collapsed = json.loads(json.dumps(good))
    collapsed["rework"]["rework_share"] = collapsed["rework"]["rework_per_close"]
    assert rate_form_problems(collapsed)

    # 3. A form is renamed away entirely.
    missing = json.loads(json.dumps(good))
    del missing["rework"]["rework_per_close"]
    assert any("rework_per_close" in p for p in rate_form_problems(missing))

    # 4. The denominator disagrees between the two surfaces.
    split = json.loads(json.dumps(good))
    split["delivery"]["closed_subjects"] = 31
    assert any("denominator" in p for p in rate_form_problems(split))

    # 5. Fewer close rows than closed subjects.
    short = json.loads(json.dumps(good))
    short["delivery"]["close_events"] = 12
    assert any("close_events < closed_subjects" in p for p in rate_form_problems(short))

    # 6. The change fail rate is dropped from the payload.
    no_rate = json.loads(json.dumps(good))
    del no_rate["rework"]["change_fail_rate"]
    assert any("change_fail_rate" in p for p in rate_form_problems(no_rate))

    # 7. The coverage is dropped, leaving the rate unreadable on its own.
    no_cov = json.loads(json.dumps(good))
    del no_cov["rework"]["subject_coverage"]
    assert any("subject_coverage" in p for p in rate_form_problems(no_cov))

    # 8. The coverage denominator drifts off the entry count.
    cov_drift = json.loads(json.dumps(good))
    cov_drift["rework"]["subject_coverage_denominator"] = 46
    assert any("total_entries" in p for p in rate_form_problems(cov_drift))

    # 9. The change fail rate names a different population than the rework forms.
    other_pop = json.loads(json.dumps(good))
    other_pop["rework"]["change_fail_rate_denominator"] = 31
    other_pop["rework"]["change_fail_rate"] = round(4 / 31, 4)
    assert any("one population" in p for p in rate_form_problems(other_pop))

    # 10. The numerator claims more failures than there are determinate links.
    over = json.loads(json.dumps(good))
    over["rework"]["change_fail_rate_numerator"] = 12
    over["rework"]["change_fail_rate"] = round(12 / 29, 4)
    assert any("determinate link" in p for p in rate_form_problems(over))

    # 11. Entries exist and nothing is linked: the rate cannot be published.
    unlinked = json.loads(json.dumps(good))
    unlinked["rework"]["change_fail_rate_numerator"] = 0
    unlinked["rework"]["change_fail_rate"] = 0.0
    unlinked["rework"]["subject_coverage_numerator"] = 0
    unlinked["rework"]["subject_coverage"] = 0.0
    assert any("nothing is LINKED" in p for p in rate_form_problems(unlinked))

    # 12. A rate that does not follow from its own numerator and denominator.
    bad_math = json.loads(json.dumps(good))
    bad_math["rework"]["change_fail_rate"] = 0.9
    assert any("numerator / denominator" in p for p in rate_form_problems(bad_math))


# ---------------------------------------------------------------------------
# Rule 7/8 — the outcome reader (#53). The gate states its OWN copy of the domain:
# a gate that borrows the reader's tuple cannot notice the tuple being widened.
# ---------------------------------------------------------------------------

OUTCOME_DOMAIN = ("accepted", "reworked", "abandoned", "failed")

def outcome_reader_problems() -> list[str]:
    """The reader must read a FIELD, validate the value, and default to UNKNOWN."""
    problems: list[str] = []

    if tuple(audit_reader.OUTCOME_DOMAIN) != OUTCOME_DOMAIN:
        problems.append(
            f"the reader's outcome domain is {tuple(audit_reader.OUTCOME_DOMAIN)!r}, "
            f"this gate states {OUTCOME_DOMAIN!r}"
        )

    # An unstated outcome is UNKNOWN — never `accepted`. That default is the defect.
    bucket, problem = audit_reader.declared_outcome("HQ closes #50, verified complete.")
    if bucket != "unstated":
        problems.append(f"a row stating no outcome was bucketed {bucket!r}, expected 'unstated'")
    if problem is not None:
        problems.append("a row stating no outcome was reported as malformed; absence is not a bad value")

    # A malformed value is REPORTED, never bucketed as a verdict.
    for malformed in ("outcome=accepted.", "outcome=", "outcome=Accepted", "outcome=done"):
        bucket, problem = audit_reader.declared_outcome(f"work landed. {malformed} board=closed")
        if bucket in OUTCOME_DOMAIN:
            problems.append(f"{malformed!r} was bucketed as the verdict {bucket!r}")
        if not problem:
            problems.append(f"{malformed!r} was not reported")

    # A mention in prose is not the declaration: the writer appends its trailer LAST, so
    # the last token is canonical. The old reader took the first and parsed `and` out of
    # a dispatch row's sentence.
    bucket, _ = audit_reader.declared_outcome(
        "the outcome=accepted substring was the old reader's bug. cost_usd=1.0 outcome=failed"
    )
    if bucket != "failed":
        problems.append(
            f"the reader took an earlier prose mention over the canonical trailer: {bucket!r}"
        )

    # Every domain value must round-trip.
    for value in OUTCOME_DOMAIN:
        bucket, problem = audit_reader.declared_outcome(f"done. outcome={value} gate=all-pass")
        if bucket != value or problem:
            problems.append(f"the domain value {value!r} did not round-trip: {bucket!r} {problem!r}")

    return problems

def outcome_population_problems(payload: dict) -> list[str]:
    """The populations must reconcile, and no bucket may be a verdict nobody stated."""
    problems: list[str] = []
    delivery = payload.get("delivery", {})

    def invalid_rows(by_outcome: dict) -> int:
        return sum(n for key, n in by_outcome.items() if key.startswith("invalid:"))

    legs = (
        ("run", delivery.get("runs_by_outcome", {}), "run_events",
         "run_rows_stating_outcome", "unstated_run_rows"),
        ("close", delivery.get("close_rows_by_outcome", {}), "close_events",
         "close_rows_stating_outcome", "unstated_close_rows"),
    )
    for label, by_outcome, total_key, stated_key, unstated_key in legs:
        total = delivery.get(total_key, 0)
        stated = delivery.get(stated_key, 0)
        unstated = delivery.get(unstated_key, 0)
        if sum(by_outcome.values()) != total:
            problems.append(
                f"{label} buckets sum to {sum(by_outcome.values())}, but {total_key} is {total}"
            )
        if stated + unstated + invalid_rows(by_outcome) != total:
            problems.append(
                f"{label} rows do not partition: {stated} stating + {unstated} unstated + "
                f"{invalid_rows(by_outcome)} invalid != {total} {total_key}"
            )
        if by_outcome.get("unstated", 0) != unstated:
            problems.append(f"{label} unstated bucket {by_outcome.get('unstated', 0)} != {unstated_key} {unstated}")
        # A verdict bucket nobody stated is how the favourable default returns.
        for key in by_outcome:
            if key not in OUTCOME_DOMAIN and key != "unstated" and not key.startswith("invalid:"):
                problems.append(
                    f"{label} bucket {key!r} is neither a domain value, 'unstated', nor an invalid: bucket"
                )

    population = delivery.get("first_pass_yield_population", 0)
    if population != delivery.get("run_rows_stating_outcome", 0):
        problems.append(
            f"the yield's population {population} is not the rows stating an outcome "
            f"({delivery.get('run_rows_stating_outcome', 0)})"
        )
    coverage = delivery.get("first_pass_yield_coverage", [])
    if coverage != [population, delivery.get("run_events", 0)]:
        problems.append(
            f"the yield's coverage {coverage!r} does not state the population and the run rows"
        )
    yield_val = delivery.get("first_pass_yield")
    if population == 0 and delivery.get("run_events", 0) > 0 and yield_val is not None:
        problems.append(
            f"no run row states an outcome, yet the yield is published as {yield_val!r} — "
            "an undefined ratio must be null, never 1.0"
        )

    # The ratio must FOLLOW from the buckets the payload itself reports. Trusting the
    # published number would let a reader that divided by every run row pass every
    # structural check above while publishing a number no bucket supports.
    accepted = delivery.get("runs_by_outcome", {}).get("accepted", 0)
    if population > 0 and yield_val is not None:
        expected = round(accepted / population, 4)
        if yield_val != expected:
            problems.append(
                f"the published yield {yield_val} does not follow from {accepted} accepted "
                f"÷ {population} runs stating an outcome (expected {expected})"
            )

    # A work unit cannot succeed without a close row saying so: this is the invariant the
    # favourable default broke, and it is why a per-subject count is bounded by a row count.
    successful = delivery.get("successful_closed_tasks", 0)
    accepted_rows = delivery.get("close_rows_by_outcome", {}).get("accepted", 0)
    if successful > accepted_rows:
        problems.append(
            f"successful_closed_tasks {successful} exceeds the {accepted_rows} close rows "
            "that state an accepted outcome — a subject cannot succeed without a row saying so"
        )

    # And the cost ratio is re-derived the same way.
    if successful > 0:
        expected_cost = round(delivery.get("total_cost_usd", 0.0) / successful, 4)
        if delivery.get("cost_per_successful_task_usd") != expected_cost:
            problems.append(
                f"the published cost per successful task "
                f"{delivery.get('cost_per_successful_task_usd')} does not follow from "
                f"{delivery.get('total_cost_usd')} ÷ {successful} (expected {expected_cost})"
            )
    return problems

def test_the_outcome_reader_reads_a_field_and_validates_it():
    problems = outcome_reader_problems()
    assert not problems, "; ".join(problems)

def test_the_outcome_populations_reconcile():
    problems = outcome_population_problems(load_audit())
    assert not problems, "; ".join(problems)

def test_a_doctored_outcome_bucket_is_rejected():
    """The invariant must reject bad input, not merely accept good input."""
    payload = load_audit()
    assert outcome_population_problems(payload) == [], "the live payload must reconcile"

    # The favourable default, restored by hand: a verdict bucket no row stated.
    doctored = json.loads(json.dumps(payload))
    doctored["delivery"]["runs_by_outcome"]["accepted"] += 1
    assert outcome_population_problems(doctored), "a hand-raised accepted bucket survived"

    # A published ratio with no population behind it.
    doctored = json.loads(json.dumps(payload))
    doctored["delivery"]["first_pass_yield_population"] = 0
    doctored["delivery"]["first_pass_yield"] = 1.0
    assert outcome_population_problems(doctored), "a yield with no population survived"

def main() -> int:
    payload = load_audit()
    problems = rate_form_problems(payload)
    problems += derivation_problems(payload, derive_fail_linkage())
    problems += outcome_reader_problems()
    problems += outcome_population_problems(payload)
    if problems:
        print("rate gate FAILED:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    rows, subjects = ledger_close_counts()
    rw = payload["rework"]
    print(
        f"rate forms OK — share {rw['rework_share']} = {rw['total_entries']}/({rw['closed_subjects']}"
        f"+{rw['total_entries']}), per close {rw['rework_per_close']} = {rw['total_entries']}/{rw['closed_subjects']}"
    )
    print(
        f"change fail rate OK — {rw['change_fail_rate']} = {rw['change_fail_rate_numerator']}"
        f"/{rw['change_fail_rate_denominator']} closed work units, linkage coverage "
        f"{rw['subject_coverage_numerator']}/{rw['subject_coverage_denominator']} "
        f"({round(rw['subject_coverage'] * 100, 1)}%) — derived, not stated"
    )
    print(f"denominators reconciled — {rows} close rows over {subjects} distinct closed subjects")
    dl = payload["delivery"]
    print(
        f"outcomes read as fields — yield population {dl['first_pass_yield_population']} of "
        f"{dl['run_events']} run rows, coverage {dl['first_pass_yield_coverage']}; "
        f"{dl['unstated_run_rows']} run and {dl['unstated_close_rows']} close rows state none "
        f"(UNKNOWN, never accepted); {len(dl['invalid_outcome_reports'])} invalid value(s) reported"
    )
    return 0

if __name__ == "__main__":
    sys.exit(main())
