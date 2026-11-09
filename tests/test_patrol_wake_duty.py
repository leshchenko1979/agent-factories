"""Gate: the wake-duty leg — a cron `success` is a DELIVERY receipt, never a work receipt (#612).

The defect this gate guards, measured 2026-11-03: `miidas-hq-daily-trigger` started
09:00:31.129Z, completed 09:01:21Z `status=success`, and the target factory appended NOTHING
that day. The wake landed one second before the first of nine compaction markers and the duty
was consumed before it was reached. The cron's green was true and worthless, and no leg read
it: `duty-receipt` judges only the rows THIS factory declares, so all 31 unattributed rows —
every member factory's thin wake — were unasked.

Every arm below drives the leg's own injection points, so no verdict here can be decided by
this box's files. The pair that matters is `test_a_delivered_wake_with_no_target_row` against
`test_the_same_wake_passes_when_the_target_store_moved`: they differ in ONE ledger row, so the
verdict is a function of the store rather than of the fixture.
"""

# --- imports ---------------------------------------------------------------
from __future__ import annotations
import datetime as dt
import json
import tempfile
from pathlib import Path

from patrol_fixtures import REPO, RUNNER, _thin  # noqa: F401

# --- this leg's own helpers -------------------------------------------------
_READ_AT = "2026-11-05T14:30:00Z"
_NOW = dt.datetime(2026, 11, 5, 14, 30, tzinfo=dt.timezone.utc)
# The incident's own instant, and the window the ruling gives it.
_WAKE = "2026-11-03T09:00:31.129Z"
_JOB_ID = "3f6c1a52-0000-4000-8000-00000000c612"

def _parse(text: str) -> dt.datetime:
    """Both instants the daemon writes: with and without fractional seconds."""
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return dt.datetime.strptime(text, fmt).replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"unparseable instant {text!r}")

def _fire(*, status: str = "success", started: str = _WAKE, suppressed: bool = False) -> dict:
    return {
        "job_id": _JOB_ID,
        "job_name": "probe-wake",
        "status": status,
        "started_at": started,
        "completed_at": started,
        "content": "",
        "suppressed": suppressed,
    }

def _wake(name: str, **kw) -> dict:
    """A thin wake row AS THE DAEMON REPORTS IT — carrying the cron id its fire is keyed on.

    The shared `_cron` fixture has no `id`, so a row built from it can never be paired with a
    fire and every arm would land in the NO-FIRE excuse instead of the verdict under test.
    The id is stamped here, in the one place this file builds rows.
    """
    row = _thin(name, **kw)
    row["id"] = _JOB_ID
    return row

def _stores(slug: str = "miidas", prefix: str = "probe-") -> dict:
    """One declared factory, whose `repo` points at a temp dir the probe owns."""
    return {prefix: {"slug": slug, "repo": Path(tempfile.mkdtemp())}}

def _ledger_reader(*entries: tuple[str, str]):
    """A ledger reader returning these (subject, ts) rows — the store, injected."""
    rows = [{"instant": _parse(ts), "subject": subject} for subject, ts in entries]

    def read(_path):
        return rows, ""

    return read

def _leg(rows, *, stores=None, ledger_fn=None, fires=None, window_secs=86400.0,
         read_at=_READ_AT, now=_NOW, clock_fn=None):
    return RUNNER.wake_duty_leg(
        rows,
        ["probe-home"],
        [],
        prefixes=["factory-"],
        read_at=read_at,
        fires=[_fire()] if fires is None else fires,
        factory_fn=lambda: (stores if stores is not None else _stores(), []),
        ledger_fn=ledger_fn or _ledger_reader(),
        window_secs=window_secs,
        now=now,
        clock_fn=clock_fn,
    )

# --- the pair that carries the verdict --------------------------------------
def test_a_delivered_wake_with_no_target_row_is_NO_VERDICT() -> None:
    """THE INCIDENT (#612). The wake was delivered, the target store is readable, and it
    carries nothing inside the window — so the round is NO VERDICT, never a pass."""
    leg = _leg([_wake("probe-daily-trigger")])
    assert leg["coverage"]["judged"] == 1, leg["coverage"]
    assert leg["coverage"]["missing"] == 1
    assert leg["coverage"]["passed"] == 0
    assert len(leg["problems"]) == 1, leg["problems"]
    problem = leg["problems"][0]
    assert "NO VERDICT" in problem
    # The finding must NAME the substitution, not merely count it: a reader who sees only
    # `1 problem` cannot tell this from a failed delivery.
    assert "delivered" in problem.lower()
    assert "never that the woken lane reached its declared duty" in problem

def test_the_same_wake_passes_when_the_target_store_moved() -> None:
    """THE CONTROL. Same row, same fire, same window — ONE ledger row inside the window.

    Without this arm the previous test proves only that the leg can say NO: a leg that
    always reds would pass it just as well, which is the decoration this repo refuses.
    """
    leg = _leg(
        [_wake("probe-daily-trigger")],
        ledger_fn=_ledger_reader(("daily-self-audit-2026-11-03", "2026-11-03T09:11:41Z")),
    )
    assert leg["coverage"]["judged"] == 1, leg["coverage"]
    assert leg["coverage"]["passed"] == 1
    assert leg["coverage"]["missing"] == 0
    assert leg["problems"] == [], leg["problems"]

# --- fail-closed ------------------------------------------------------------
def test_an_unreadable_target_store_is_UNKNOWN_never_a_zero() -> None:
    """A zero from an unread store is not a zero (the ruling's own fail-closed clause)."""
    leg = _leg([_wake("probe-daily-trigger")], ledger_fn=lambda _p: (None, "OSError: denied"))
    assert leg["coverage"]["unreadable_store"] == 1
    assert leg["coverage"]["judged"] == 0
    assert "UNKNOWN" in leg["problems"][0]
    assert "OSError: denied" in leg["problems"][0]

def test_the_real_ledger_reader_refuses_a_store_with_no_readable_instant() -> None:
    """The reader itself, not an injected stub: a file that opens and carries no `ts` is
    UNREADABLE rather than empty, because the two render alike in a count."""
    path = Path(tempfile.mkdtemp()) / "ledger.jsonl"
    path.write_text('{"n": 1, "event": "close"}\nnot json at all\n', encoding="utf-8")
    entries, why = RUNNER.ledger_entries(path)
    assert entries is None
    assert "not one readable `ts`" in why.lower() or "NOT ONE readable" in why

def test_the_real_ledger_reader_reads_a_ledger_and_skips_a_bad_line() -> None:
    """The positive half of the same reader: a real ledger parses, and one corrupt line does
    not discard the rows around it."""
    path = Path(tempfile.mkdtemp()) / "ledger.jsonl"
    path.write_text(
        json.dumps({"n": 1, "ts": "2026-11-03T09:11:41Z", "subject": "a"}) + "\n"
        + "garbage\n"
        + json.dumps({"n": 2, "ts": "2026-11-03T10:00:00Z", "subject": "b"}) + "\n",
        encoding="utf-8",
    )
    entries, why = RUNNER.ledger_entries(path)
    assert entries is not None, why
    assert [e["subject"] for e in entries] == ["a", "b"]

def test_a_missing_ledger_file_is_unreadable_and_names_the_path() -> None:
    missing = Path(tempfile.mkdtemp()) / "nope" / "ledger.jsonl"
    entries, why = RUNNER.ledger_entries(missing)
    assert entries is None
    assert "ledger.jsonl" in why

# --- the class split --------------------------------------------------------
def test_a_failed_delivery_is_a_DIFFERENT_class_from_a_missing_duty() -> None:
    """A wake that never arrived owes no duty. Folding the two together would report a
    transport fault as a lane that ignored its work."""
    leg = _leg([_wake("probe-daily-trigger")], fires=[_fire(status="error")])
    assert leg["coverage"]["delivery_failed"] == 1
    assert leg["coverage"]["missing"] == 0
    assert "not the #612 class" in leg["problems"][0]

def test_a_suppressed_fire_owed_no_wake_and_is_excused() -> None:
    leg = _leg([_wake("probe-daily-trigger")], fires=[_fire(suppressed=True)])
    assert leg["coverage"]["suppressed"] == 1
    assert leg["coverage"]["judged"] == 0
    assert leg["problems"] == []

def test_a_round_younger_than_the_window_is_IN_FLIGHT_and_not_judged() -> None:
    leg = _leg([_wake("probe-daily-trigger")], fires=[_fire(started="2026-11-05T14:00:00.000Z")])
    assert leg["coverage"]["in_flight"] == 1
    assert leg["coverage"]["judged"] == 0
    assert leg["problems"] == []

def test_a_job_with_no_fire_record_is_not_judged() -> None:
    leg = _leg([_wake("probe-daily-trigger")], fires=[])
    assert leg["coverage"]["no_fire"] == 1
    assert leg["problems"] == []

# --- population discipline --------------------------------------------------
def test_a_thin_wake_no_factory_owns_is_EXCUSED_and_COUNTED_never_a_red() -> None:
    """An unowned thin wake can never be audited — and it is not THIS factory's red.

    The finding is real: a row whose prefix no factory declares has no locatable target
    store, so its duty is unauditable forever. But the row is FOREIGN — it arrived in a
    home whose prefix the manifest does not name — and a per-factory round has no authority
    over it (ruling n=610 part 3b). Reding here would turn a factory report into a box-wide
    one, and in a bootstrapped factory declaring a single prefix it would red STANDING on a
    row it can never fix. So the arm asserts BOTH halves: the gap is NAMED and COUNTED
    (`unresolved_factory`), and it moves no verdict.
    """
    leg = _leg([_wake("orphan-daily")], stores=_stores(prefix="probe-"))
    assert leg["coverage"]["unresolved_factory"] == 1, leg["coverage"]
    assert leg["problems"] == [], leg["problems"]
    assert any(
        "no factory in registry/fleet.json owns by prefix" in note
        and "OUT OF THIS FACTORY'S POPULATION" in note
        for note in leg["excused"]
    ), leg["excused"]
    assert leg["coverage"]["judged"] == 0

def test_a_self_executing_row_is_outside_the_population() -> None:
    """A job that runs its own command leaves the work in its own run record; demanding a
    second receipt from it would red rows that are already auditable."""
    row = _wake("probe-daily-trigger")
    row["prompt"] = "Run exactly ONE bash command, then stop."
    leg = _leg([row])
    assert leg["coverage"]["thin_wakes"] == 0
    assert leg["coverage"]["self_executing"] == 1
    assert leg["coverage"]["judged"] == 0

def test_a_row_this_factory_owns_belongs_to_the_duty_receipt_leg() -> None:
    """`factory-` rows are `duty-receipt`'s population. Judging them here too would put two
    verdicts on one fact."""
    leg = _leg([_wake("factory-daily")])
    assert leg["coverage"]["rows_attributed_here"] == 1
    assert leg["coverage"]["thin_wakes"] == 0

def test_the_population_counts_print_even_when_nothing_is_judged() -> None:
    """`examined 0` must never render as `found everything clean` (#126)."""
    leg = _leg([])
    assert leg["coverage"]["rows_read"] == 0
    assert leg["coverage"]["thin_wakes"] == 0
    assert leg["coverage"]["judged"] == 0
    assert leg["coverage"]["window_basis"]

# --- the strong form --------------------------------------------------------
def test_a_declared_stem_is_hunted_and_an_unrelated_row_does_NOT_pass_it() -> None:
    """The anti-laundering arm. A wake that DECLARES its duty is judged on that duty, so a
    factory doing unrelated work inside the window cannot launder a skipped duty into a pass
    — which is exactly how the 2026-11-03 round would have read had this leg used the
    factory-granularity predicate for a declaring wake."""
    row = _wake("probe-daily-trigger")
    row["prompt"] = row["prompt"].replace(
        "receipt_subject: none", "receipt_subject: daily-self-audit"
    )
    unrelated = _ledger_reader(("unrelated-123-work", "2026-11-03T10:00:00Z"))
    leg = _leg([row], ledger_fn=unrelated)
    assert leg["coverage"]["missing"] == 1, leg["coverage"]
    assert "DECLARED stem" not in leg["problems"][0]  # the FINDING is the absence, not the stem
    # ...and the same declared stem DOES pass it.
    declared = _ledger_reader(("daily-self-audit-2026-11-03", "2026-11-03T09:11:41Z"))
    leg = _leg([row], ledger_fn=declared)
    assert leg["coverage"]["passed"] == 1, leg["coverage"]

# --- mutation ---------------------------------------------------------------
def test_MUTANT_without_the_absence_write_the_incident_reads_CLEAN(monkeypatch) -> None:
    """Neuter the one write that makes the incident a finding, and the arm above must RED.

    A gate that cannot fail is decoration: this proves the NO VERDICT line is what carries
    the verdict, rather than the fixture happening to red for some other reason.
    """
    source = (REPO / "tools" / "patrol_host_state.py").read_text(encoding="utf-8")
    needle = '            f"cron\'s success proves the wake ARRIVED, never that the woken lane reached its "'
    assert needle in source, "the absence write moved; re-point this mutant"
    mutant_source = source.replace(
        "        missing += 1\n        problems.append(\n            f\"{name} (cron id {job_id}, {slug}): the wake was DELIVERED",
        "        missing += 1\n        _muted = (\n            f\"{name} (cron id {job_id}, {slug}): the wake was DELIVERED",
    )
    assert mutant_source != source, "the mutant did not apply"
    namespace = RUNNER.__dict__
    saved = {key: namespace[key] for key in ("wake_duty_leg",)}
    try:
        exec(compile(mutant_source, "mutant", "exec"), namespace)  # noqa: S102
        leg = _leg([_wake("probe-daily-trigger")])
        assert leg["coverage"]["missing"] == 1
        assert leg["problems"] == [], (
            "the mutant still reds, so the absence write is not what carries the verdict"
        )
    finally:
        for key, value in saved.items():
            namespace[key] = value

# --- the three buckets ------------------------------------------------------
def test_a_wake_declaring_it_owes_NO_NAMED_receipt_is_not_hunted_for_a_stem() -> None:
    """`receipt_subject: none` is a DECLARATION, not a stem (measured while writing this gate).

    Read with `declared_receipt_stem` alone, the literal word `none` becomes the stem: the
    hunt asks every fleet ledger for a subject starting with "none", finds nothing, and
    reports a MISSING duty on a row that declared it owed no NAME — a false finding on the
    majority of the box's thin wakes, which is the fastest way to teach a reader to ignore
    this leg's red. The three-bucket reader is what keeps the word out of the predicate.
    """
    row = _wake("probe-daily-trigger")
    assert "receipt_subject: none" in row["prompt"]
    # ANY row inside the window satisfies a row that owes no named receipt.
    leg = _leg([row], ledger_fn=_ledger_reader(("unrelated-123-work", "2026-11-03T10:00:00Z")))
    assert leg["coverage"]["judged"] == 1, leg["coverage"]
    assert leg["coverage"]["passed"] == 1, leg["coverage"]
    assert leg["problems"] == []
    assert any("owes no NAMED receipt" in note for note in leg["excused"]), leg["excused"]

def test_MUTANT_reading_none_as_a_stem_reports_a_false_MISSING() -> None:
    """Neuter the bucket reader back to the single regex and this must RED.

    The mutant is the shape this gate was written against, so it is the only proof that the
    disposition reader — rather than the fixture — is what keeps `none` out of the hunt.
    """
    source = (REPO / "tools" / "patrol_host_state.py").read_text(encoding="utf-8")
    needle = '        disposition, declared_stem = declared_receipt_disposition(str(row.get("prompt") or ""))'
    assert needle in source, "the bucket read moved; re-point this mutant"
    mutant_source = source.replace(
        needle,
        '        disposition, declared_stem = "declares", declared_receipt_stem(str(row.get("prompt") or ""))',
    )
    assert mutant_source != source, "the mutant did not apply"
    namespace = RUNNER.__dict__
    saved = {key: namespace[key] for key in ("wake_duty_leg",)}
    try:
        exec(compile(mutant_source, "mutant", "exec"), namespace)  # noqa: S102
        leg = _leg(
            [_wake("probe-daily-trigger")],
            ledger_fn=_ledger_reader(("unrelated-123-work", "2026-11-03T10:00:00Z")),
        )
        assert leg["coverage"]["missing"] == 1, leg["coverage"]
        assert "NO VERDICT" in leg["problems"][0]
    finally:
        for key, value in saved.items():
            namespace[key] = value

# --- #635: a wake that POSTDATES the round's own read ------------------------
#
# MEASURED 2026-11-09, this box: the leg printed `stores read: … — read at 12:24:59Z` and
# three lines later reddened the ai-antispam lane over a wake stamped 12:25:23.938306324Z —
# 24.938 s AFTER that read. The lane had done its duty 2 m 09 s later (its own rows n=379
# claim 12:27:16Z, n=380 close / n=381 run 12:27:32Z). The old guard read
# `0 <= age < window_secs`, so a NEGATIVE age fell straight through to judging, and the leg
# demanded a receipt from a store it had read BEFORE the wake existed.
#
# The pair below differs in ONE field — the wake's instant — so the verdict is a function of
# the postdating rather than of the fixture.
_POSTDATED_WAKE = "2026-11-05T14:30:24.938306324Z"   # 24.938 s AFTER _READ_AT
_POSTDATED_RECEIPT = "2026-11-05T14:32:16Z"          # the lane's real receipt, 2 m 09 s later

def test_a_wake_POSTDATING_the_read_is_IN_FLIGHT_never_judged() -> None:
    """#635, THE INCIDENT. `now` is left to derive from `read_at` (as the round does), so the
    wake sits in the future of the leg's own clock and the age is negative.

    It must be EXCUSED with its own count, and — the whole point — it must NOT be judged: a
    receipt the lane wrote after the read cannot exist in bytes already read.
    """
    leg = _leg(
        [_wake("probe-daily-trigger")],
        fires=[_fire(started=_POSTDATED_WAKE)],
        now=None,
        ledger_fn=_ledger_reader(("daily-self-audit-2026-11-05", _POSTDATED_RECEIPT)),
    )
    assert leg["coverage"]["postdated_read"] == 1, leg["coverage"]
    assert leg["coverage"]["judged"] == 0, leg["coverage"]
    assert leg["coverage"]["missing"] == 0, leg["coverage"]
    assert leg["problems"] == [], leg["problems"]
    note = " ".join(leg["excused"])
    assert "POSTDATES" in note, note
    assert "IN FLIGHT BY CONSTRUCTION" in note, note
    # It must name the instant it postdates, and say WHY that instant is the wrong ruler.
    assert _READ_AT in note, note
    assert "ENTRYPOINT" in note, note

def test_the_SAME_wake_a_full_window_old_still_REDS() -> None:
    """THE CONTROL, and the arm that makes the one above mean something.

    Identical fixture, identical store, identical receipt — only the wake's instant moves
    from the future to 2 days back. It must still be judged and still red, otherwise the fix
    would have excused the #612 class wholesale instead of the postdating subclass.
    """
    leg = _leg([_wake("probe-daily-trigger")], now=_NOW)
    assert leg["coverage"]["postdated_read"] == 0, leg["coverage"]
    assert leg["coverage"]["judged"] == 1, leg["coverage"]
    assert leg["coverage"]["missing"] == 1, leg["coverage"]
    assert "NO VERDICT" in leg["problems"][0]

def test_a_wake_exactly_at_the_read_instant_is_NOT_postdated() -> None:
    """THE BOUNDARY, and it is the window that decides it, not the postdating branch.

    `age == 0` means the wake exists AT the read instant: it is not postdating (that needs
    `age < 0`), and it is 0 seconds old, so the ordinary window calls it IN FLIGHT. The
    distinction matters in both directions — an off-by-one that swept `age == 0` into the
    postdating bucket would file a real round under an instrument defect, and one that let
    `age < 0` into this bucket is the original #635 bug.
    """
    leg = _leg(
        [_wake("probe-daily-trigger")],
        fires=[_fire(started=_READ_AT)],
        now=None,
    )
    cov = leg["coverage"]
    assert cov["postdated_read"] == 0, cov
    assert cov["in_flight"] == 1, cov
    assert cov["judged"] == 0, cov
    assert any("IN FLIGHT" in note for note in leg["excused"]), leg["excused"]

def test_each_store_carries_the_instant_IT_was_read() -> None:
    """#635 CRITERION 1. The printed instant beside a store name must be the instant THAT
    store was read — never the round's single entrypoint stamp, which predates every store
    read inside the round and is what made the 24.9 s gap invisible.

    The clock is injected so this arm is decided by the leg and not by wall time.
    """
    later = dt.datetime(2026, 11, 5, 14, 41, 7, tzinfo=dt.timezone.utc)
    leg = _leg(
        [_wake("probe-daily-trigger")],
        ledger_fn=_ledger_reader(("daily-self-audit-2026-11-03", "2026-11-03T09:11:41Z")),
        clock_fn=lambda: later,
    )
    at_by_store = leg["coverage"]["stores_read_at"]
    assert at_by_store == {"miidas": "2026-11-05T14:41:07Z"}, at_by_store
    # And it must be LATER than the round's stamp, which is the whole defect: an instant
    # equal to `read_at` would mean the store was read at the entrypoint, which it was not.
    assert at_by_store["miidas"] != leg["coverage"]["read_at"]

def test_the_render_pairs_each_store_with_ITS_OWN_instant() -> None:
    """#635 CRITERION 1, at the surface a reader actually reads.

    The render is inline in `main()`, so this arm reads the source rather than calling it —
    and it asserts the SHAPE, which is what regressed: the old line was
    `stores read: <names> — read at <round stamp>`, attributing ONE instant to stores read at
    different times. The instant must come from `stores_read_at`, keyed by the store's name.
    """
    source = (REPO / "tools" / "patrol_host_state.py").read_text(encoding="utf-8")
    assert 'at_by_store = cov.get("stores_read_at") or {}' in source, (
        "the render no longer reads the per-store instants"
    )
    assert "{name} (read at {at_by_store.get(name) or 'unstated'})" in source, (
        "the render must pair each store NAME with its OWN instant"
    )
    # THE OLD SHAPE MUST BE GONE: one stamp attributed to every store. Quoted from
    # `git show HEAD:tools/patrol_host_state.py`, so the absence assertion names real bytes.
    old_one_instant = (
        "stores read: " + "{', '.join(cov['stores_read']) or 'none'} " + "\u2014 read at "
    )
    assert old_one_instant not in source, (
        "the old one-instant-for-all-stores line is still present"
    )

def test_the_render_states_a_postdating_count_when_there_is_one() -> None:
    """A count a reader cannot see is a count that did not happen: the postdating bucket gets
    its own rendered line, never a silent increment inside `in_flight`."""
    source = (REPO / "tools" / "patrol_host_state.py").read_text(encoding="utf-8")
    assert 'if cov.get("postdated_read"):' in source, (
        "the render never checks the postdating count"
    )
    assert "POSTDATING THIS READ: {cov['postdated_read']} wake(s)" in source, (
        "the postdating count is not rendered"
    )
    assert "IN FLIGHT BY CONSTRUCTION" in source

def test_MUTANT_restoring_the_old_guard_reds_the_postdated_wake() -> None:
    """THE MUTANT. Put `0 <= age < window_secs` back and the postdated wake must be JUDGED
    and RED — the exact incident. Without this arm the gate proves only that the current code
    excuses something, not that the guard was the thing excusing it."""
    source = (REPO / "tools" / "patrol_host_state.py").read_text(encoding="utf-8")
    # BOTH halves of the old guard are restored, because the defect was the PAIR: the old
    # code was a single `if 0 <= age < window_secs:` whose left bound silently dropped a
    # negative age through to judging. Disabling only the new branch would still leave the
    # window branch to catch `age < 0` and the mutant would prove nothing.
    postdating = "        if age < 0:\n"
    window = "        if age < window_secs:\n"
    assert source.count(postdating) == 1, "the postdating branch moved; re-point this mutant"
    assert source.count(window) == 1, "the window branch moved; re-point this mutant"
    mutant_source = source.replace(postdating, "        if False:\n").replace(
        window, "        if 0 <= age < window_secs:\n"
    )
    assert mutant_source != source, "the mutant did not apply"
    namespace = RUNNER.__dict__
    saved = {key: namespace[key] for key in ("wake_duty_leg",)}
    try:
        exec(compile(mutant_source, "mutant", "exec"), namespace)  # noqa: S102
        leg = _leg(
            [_wake("probe-daily-trigger")],
            fires=[_fire(started=_POSTDATED_WAKE)],
            now=None,
            # THE STORE AS IT ACTUALLY WAS: read at 14:30:00Z, so the receipt the lane went
            # on to write at 14:32:16Z is NOT in it. That is the incident in one fixture —
            # the old guard judged a round against bytes read before the round existed.
            ledger_fn=_ledger_reader(),
        )
        assert leg["coverage"]["postdated_read"] == 0, leg["coverage"]
        assert leg["coverage"]["judged"] == 1, leg["coverage"]
        assert leg["coverage"]["missing"] == 1, leg["coverage"]
        assert "NO VERDICT" in leg["problems"][0]
    finally:
        for key, value in saved.items():
            namespace[key] = value

if __name__ == "__main__":
    # PYTEST form: these are module-level arms, so a bare run would exit 0 having asserted
    # NOTHING — a gate whose only exits are barred (entry-point equivalence, #612 review).
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
