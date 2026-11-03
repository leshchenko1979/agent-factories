"""Gate: the ruling leg — #223/#334/#243/#245/#545/#519

Split from tests/test_patrol_host_state.py by #602: one gate per leg, each
carrying its own measured budget, so one slow leg can no longer withhold a
verdict from the whole fleet.
"""

# --- imports ---------------------------------------------------------------
from __future__ import annotations
import importlib.util
import io
import json
import os
import sqlite3
import shutil
import subprocess
import tempfile
import datetime as dt
from pathlib import Path
from unittest import mock
import pytest

from patrol_fixtures import (  # noqa: F401
    REPO,
    RUNNER,
    RUNNER_PATH,
    _ALL_LIVE_COINCIDENCES,
    _DELIVERED,
    _FAILURE,
    _LIVE_MENTION_COINCIDENCES,
    _LIVE_REFUSED_COINCIDENCES,
    _NONE_DECL,
    _NO_RULING_EXEMPTIONS,
    _RECEIPT,
    _RULING_BOUND,
    _RULING_POST,
    _RULING_PRE,
    _SESSION_UUID,
    _WAKE_PROMPT,
    _comment_numeric,
    _comment_url,
    _cron,
    _declared_skip,
    _home_db,
    _issue,
    _issue_with_comments,
    _rows,
    _run,
    _stall_row,
    _swept,
    _thin,
    _tier_row,
    _SKIPS,
)


# --- this leg's own helpers -------------------------------------------------
def _log_dir(**files: str) -> Path:
    """A synthetic log surface. The live population is legitimately empty on a quiet day,
    so a probe that needs a fixture gets one rather than the box's leftovers."""
    root = Path(tempfile.mkdtemp())
    for name, text in files.items():
        (root / name.replace("__", "-")).write_text(text, encoding="utf-8")
    return root

def _notify_row(name, *, row_id="row-1", home="probe-home") -> dict:
    """An ENABLED cron row this factory declares — the rows the leg attributes by.

    The prompt is `_WAKE_PROMPT`, so the row is correctly thin and the CRON leg beside it
    stays clean: a probe for the notify leg must not red on the other leg, or the run's
    exit code would not be attributable to the defect under test.
    """
    return {"id": row_id, "name": name, "home": home, "deliver_to": "session:probe",
            "prompt": f"{_WAKE_PROMPT}\n\n{_NONE_DECL}"}

def _run_row(name, *, started, completed, status, row_id="row-1") -> dict:
    """A `cron_job_runs` row — the daemon's per-fire record, carrying the run's OWN VERDICT.

    The columns are the ones the daemon writes on that table, and the `job_id` here is
    deliberately the SAME value as the cron row's `id` in `_notify_row`: the leg keys a run
    to its row by the `(job_id, job_name)` pair, and the two surfaces spell that pair
    differently (`id`/`name` against `job_id`/`job_name`), so a probe that got the spelling
    wrong would exercise a leg that can match nothing (#306).
    """
    return {"job_id": row_id, "job_name": name, "started_at": started,
            "completed_at": completed, "status": status, "error": "", "home": "probe-home"}

def _scope_at(text: str) -> tuple:
    """A synthetic bound at `text`, in the tuple shape the leg consumes."""
    instant = dt.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    return (instant, text, "")

def _ruling_issue(number: int, created: str, *, body: str = "## RULED — a ruling.\n",
                  comment_id: str | None = None, state: str = "OPEN") -> dict:
    """A board issue carrying ONE ruling comment posted at `created`.

    `state` is a parameter because two different fixtures are needed. A leg-only probe uses
    OPEN; a probe driven through `main()` uses CLOSED, because an OPEN item carrying an
    `intake` row and no `ruling` row is the #332 board-unruled leg's own population, and a
    run that is red for THAT reason would make this file's assertions statements about
    another leg.
    """
    issue = _issue(number, state)
    issue["comments"] = [{
        "id": comment_id or f"IC_probe_{number}",
        "body": body,
        "author": {"login": "leshchenko1979"},
        "createdAt": created,
        "url": _comment_url(number),
    }]
    return issue

def _exemptions_file(tmp: str, *entries: dict) -> Path:
    """A throwaway exemption table, so no probe reads the live factory's own."""
    path = Path(tmp) / "ruling-board-exemptions.json"
    path.write_text(json.dumps({"_note": "probe", "exemptions": list(entries)}),
                    encoding="utf-8")
    return path

def _exemption(comment: str, issue: int, **over) -> dict:
    entry = {
        "comment": comment, "issue": issue, "created": _RULING_POST,
        "granted": "2026-10-05",
        "domain": RUNNER.RULING_EXEMPT_DOMAIN[0],
        "reason": "probe: NO BACKFILL bars the only repair",
        "proof": "probe: the comment exists and no `ruling` row names the issue",
    }
    entry.update(over)
    return entry

# --- this leg's tests -------------------------------------------------------
def test_the_ruling_leg_BITES_on_a_ruling_comment_with_no_row() -> None:
    """#223 acceptance, the NON-VACUITY probe: the live board is the only clean one.

    The leg's whole population is rulings that were never stamped, so a probe that only
    read a clean board would prove nothing. This supplies the defect and asserts the leg
    names it AND fails the run.
    """
    issues = [_issue_with_comments(11, "OPEN", "## RULED — shape (2), the patrol leg.\n")]
    rows = _rows(("intake", "#11", 1))
    rc, out, _ = _run(issues, rows)
    assert rc == 1, f"a ruling comment with no row must fail the run, got rc={rc}\n{out}"
    assert f"#11 carries a ruling comment on the board (comment {_comment_numeric(11)})" in out, out
    assert "but the ledger holds no `ruling` row naming it" in out, out
    assert "LEG board-ruling" in out, f"the leg must be reported at all\n{out}"

def test_a_MENTION_inside_a_comment_is_not_an_instance() -> None:
    """The discrimination that makes the leg mechanical, and the reason for the heading test.

    The loose form (`--search "RULED in:comments"`) returned 118 issues against a true
    population of 9, because every filing that says the item is NOT ruled yet scored as an
    instance. So the test is on the OPENING of the body, and this probe pins that: a mention
    mid-body and a sentence about not having ruled are both refused.
    """
    issues = [
        _issue_with_comments(21, "OPEN", "We have not ruled on this yet."),
        _issue_with_comments(22, "OPEN", "See the ## RULED section further down."),
        _issue_with_comments(23, "OPEN", "  \n## RULING — leading whitespace is tolerated."),
    ]
    rows = _rows(("intake", "#21", 1), ("intake", "#22", 2), ("intake", "#23", 3))
    rc, out, _ = _run(issues, rows)
    section = out.split("LEG board-ruling")[1].split("LEG ")[0]
    assert "examined over" in section, f"the leg must state its population\n{out}"
    assert "1 examined" in section, (
        f"EXACTLY ONE of the three must be examined — the heading one and only it: {section!r}"
    )
    assert "#21" not in section and "#22" not in section, (
        f"a mere mention must never be reported as a missing row: {section!r}"
    )

def test_a_CLOSED_item_is_still_in_the_population() -> None:
    """The class is NOT state-scoped, and the read must be the board WHOLE.

    `--state open --search` returned a DIFFERENT set from the whole-board read, because four
    of the eight originally filed had since closed. So a closed item carrying a ruling
    comment with no row is still a finding — an open-filtered read would drop it silently.
    """
    issues = [_issue_with_comments(31, "CLOSED", "## RULED — settled after the fact.\n")]
    rows = _rows(("intake", "#31", 1), ("close", "#31", 2))
    rc, out, _ = _run(issues, rows)
    assert rc == 1, f"a CLOSED item with a ruling comment and no row is still a finding: {out}"
    assert "#31 carries a ruling comment" in out, out

def test_a_ruling_row_for_the_subject_clears_it() -> None:
    """The complement: the leg is discriminating, not a blanket red.

    #511 RE-ARMED this probe. It used to clear on `number in ruled` — ANY ruling row for the
    subject — which is precisely the short-circuit the ruling removed. A row now clears the
    comment only when it NAMES it, so the fixture's row carries the pairing trailer and the
    assertion is that the pair reads clean; the `#511` test below supplies the same row
    WITHOUT the trailer and asserts the opposite verdict on the same board.
    """
    issues = [_issue_with_comments(41, "OPEN", "## RULED — stamped in the same turn.\n")]
    rows = _rows(("intake", "#41", 1),
                 ("ruling", "#41", 2, f"probe comment={_comment_numeric(41)}"))
    rc, out, _ = _run(issues, rows)
    section = out.split("LEG board-ruling")[1].split("LEG ")[0]
    assert "#41" not in section, f"a stamped ruling must not be reported: {section!r}"
    assert "1 examined" in section and "0 problem(s)" in section, (
        f"it must be EXAMINED and found clean, never skipped: {section!r}"
    )

def test_the_pairing_is_PER_ACT_not_PER_ISSUE() -> None:
    """#511, the two-arm control: ONE board, ONE issue, two ledgers, opposite verdicts.

    The defect this pins is the issue-level short-circuit — `number in ruled`, "does this
    issue carry ANY `ruling` row". Under it both arms below read CLEAN, because both carry a
    `ruling` row for #42; the only difference between them is whether that row NAMES the
    comment. A ruling is an ACT on a comment, so the trailer is the whole predicate, and the
    arm WITHOUT it is the one that must bite.

    Same fixture both sides, so the verdict is attributable to the trailer alone — the shape
    #243's bridge control used. The board is LIVE state: the false-clean direction is the
    dangerous one, so the bare arm is the arm that has to be red.
    """
    issues = [_issue_with_comments(42, "OPEN", "## RULED — a ruling.\n")]
    numeric = _comment_numeric(42)

    paired_rows = _swept(("intake", "#42", 1), ("ruling", "#42", 2, f"probe comment={numeric}"))
    rc, out, _ = _run(issues, paired_rows)
    section = out.split("LEG board-ruling")[1].split("LEG ")[0]
    assert rc == 0, f"a row NAMING the comment must clear it: {out[-3000:]}"
    assert "#42" not in section, f"a paired ruling must not be reported: {section!r}"
    assert "1 examined" in section and "0 problem(s)" in section, section

    # The SAME row, the SAME issue, the SAME comment — only the trailer is gone. This is the
    # arm the short-circuit made unreachable: the row exists, so `number in ruled` was true.
    bare_rows = _swept(("intake", "#42", 1), ("ruling", "#42", 2))
    rc, out, _ = _run(issues, bare_rows)
    section = out.split("LEG board-ruling")[1].split("LEG ")[0]
    assert rc == 1, f"a ruling row that does not NAME the comment must NOT clear it: {out[-3000:]}"
    assert "#42" in section, section
    assert "1 problem(s)" in section, section
    assert f"comment {numeric}" in section, f"the comment judged must be NAMED: {section!r}"
    assert "holds no `ruling` row naming it" in section, section

def test_the_pairing_reads_the_DECLARATION_not_a_QUOTATION() -> None:
    """#511, ARM A/B: a `comment=` in PROSE is a citation; the TRAILER is the declaration.

    The per-act test above varies WHETHER a trailer exists. This one varies WHICH token a
    scan picks, which is the defect the ruling actually names (`n=3845`) and the one a
    first-match regex hides: the row DOES name the act, and the reader reports that it does
    not. Two live rows already read wrongly under it —

      n=3029 (#455) quotes a #454 act's `comment=6091047134` in prose, then DECLARES
                    `comment=6091268072` in its canonical run; first-match pairs the citation.
      n=2135 (#297) carries the prose placeholder `comment=123456` before its trailer.

    ARM B is the half that stops the cheap fix: a reader that simply took the LAST token
    would pass ARM A and still be wrong, so the quotation is left standing with the
    declaration removed, and the row must declare NOTHING rather than fall back to prose.
    ARM C pins the placeholder shape — a non-digit value OCCUPIES the key while naming no
    comment, so it reads as ABSENT and never as a pairing.
    """
    citation, declared = "6091047134", "6091268072"

    # ARM A — prose citation AND a canonical trailer, SEPARATED BY PROSE as the live rows are.
    # The separation is the point rather than fixture decoration: `trailer_tokens` reads the
    # maximal CONTIGUOUS run of `=`-carrying tokens at the end, so two tokens written
    # back-to-back are BOTH in the run and the citation is a declaration of the same row.
    # n=3029's citation sits mid-prose with the trailer alone at the end — that is the shape
    # a reader has to get right, so that is the shape probed here.
    arm_a = _rows(("ruling", "#455", 1,
                   f"the #454 post carries comment={citation} in its own record.\n\n"
                   f"The remedy is this act's own pairing.\n\ncomment={declared}"))
    paired = RUNNER.ruling_paired_comment_ids(arm_a)
    assert declared in paired, f"the row's OWN trailer must pair: {paired!r}"
    assert citation not in paired, (
        f"a PROSE citation must never pair — it names ANOTHER act's comment: {paired!r}"
    )
    assert paired[declared] == [1], f"the pairing must name the row it found: {paired!r}"

    # ARM B — the same body with the canonical run removed. A quotation declares nothing.
    arm_b = _rows(("ruling", "#455", 1,
                   f"the #454 post carries comment={citation} in its own record, and no "
                   f"trailer follows it."))
    assert RUNNER.ruling_paired_comment_ids(arm_b) == {}, (
        "a `comment=` outside the canonical run is a QUOTATION, not a declaration — pairing "
        "it would let a citation excuse an unrecorded ruling act, the same false clean the "
        "issue-level short-circuit produced one layer up"
    )

    # ARM C — `comment=none` occupies the key and names no comment (the #297 clause 2 shape).
    arm_c = _rows(("ruling", "#297", 2, "no id known yet\n\ncomment=none"))
    assert RUNNER.ruling_paired_comment_ids(arm_c) == {}, (
        "a non-digit value occupies the key while naming no comment; it must never pair"
    )

def test_the_leg_states_its_population_and_the_board_read_instant() -> None:
    """A clean read over an examined population, never a clean read over nothing.

    The clause is two-part: the gate PRINTS the population it examined. A leg that examined
    zero must not render identically to one that examined the board and found it clean.
    """
    issues = [
        _issue_with_comments(51, "OPEN", "## RULED — one.\n"),
        _issue_with_comments(52, "OPEN", "## RULING — two.\n"),
    ]
    # Both rows NAME their comment: since #511 a `ruling` row clears a comment only when its
    # detail carries `comment=<numeric id>`, so a bare row would make this a probe about the
    # pairing instead of about the printed population.
    rows = _swept(("intake", "#51", 1), ("ruling", "#51", 2, f"probe comment={_comment_numeric(51)}"),
                 ("intake", "#52", 3), ("ruling", "#52", 4, f"probe comment={_comment_numeric(52)}"))
    rc, out, _ = _run(issues, rows)
    assert rc == 0, f"both rulings are stamped, so the run is clean: {out}"
    section = out.split("LEG board-ruling")[1].split("LEG ")[0]
    assert "2 examined" in section, f"the POPULATION must be printed: {section!r}"
    assert "board read at" in section, (
        f"the board is LIVE state — the read instant is owed: {section!r}"
    )
    assert "2 issue(s) read" in section, f"the read size must travel: {section!r}"

def test_the_readings_are_DECLARED_and_the_read_carries_comments() -> None:
    """Both halves of the mechanism are pinned, because either silently kills the leg.

    A read without `comments` makes the leg examine NOTHING and print a clean verdict over
    it — the exact false-clean the population clause exists to stop. And a heading list
    inlined at the comparison cannot be probed or changed by a factory whose board differs.

    The read's field list is pinned WHOLE, so a field dropped from it is caught here rather
    than discovered as a silent no-op on live state: `createdAt` dates the stall-census
    filing guard (#415), `assignees` is what lets the OWED line tell an
    assigned-but-unclaimed unit from an untouched one (#423), and `body` carries the item's
    own statement of what it wants, which is surface 1 of the criterion-path leg's own ruling
    — without it that leg reads only replies and is blind to the criterion (#48).
    """
    assert isinstance(RUNNER.RULING_HEADINGS, tuple) and RUNNER.RULING_HEADINGS, (
        "the headings must be a declared module tuple"
    )
    assert "## RULED" in RUNNER.RULING_HEADINGS and "## RULING" in RUNNER.RULING_HEADINGS, (
        f"both headings the board carries must be declared: {RUNNER.RULING_HEADINGS}"
    )
    source = (REPO / "tools" / "patrol_host_state.py").read_text(encoding="utf-8")
    assert '"number,state,title,createdAt,closedAt,body,comments,assignees"' in source, (
        "the board read must ask for comments, or the leg examines nothing — and for "
        "`createdAt`, without which the stall-census filing guard (#415) cannot date an "
        "item and the guard is a silent no-op on live state — and for `assignees`, "
        "without which the OWED line renders an assigned-but-unclaimed unit identically "
        "to one nobody has touched (#423) — and for `body`, without which the "
        "criterion-path leg is blind to the item's own statement of what it wants (#48)"
    )

def test_the_notify_leg_BITES_on_a_log_carrying_no_receipt() -> None:
    """THE BITE, and the acceptance criterion's probe: a log with no notification id.

    Non-vacuity here rides THIS fixture, never a loud-fail-on-zero: the live population of
    failed notifies is legitimately empty on a quiet day, so an empty read is a normal read
    (#112's shape — the opposite call from the cron-thinness leg, whose population is the
    rows the factory declares and which therefore does fail loudly).
    """
    log_dir = _log_dir(**{"factory-measurement-daily-20260921T060126.log": _FAILURE})
    rows = [_notify_row("factory-measurement-daily", row_id="55b363eb-probe")]
    rc, out, _ = _run([], [], cron_rows=rows, prefixes=["factory-"], log_dir=log_dir)
    assert rc == 1, f"a notify that produced no receipt must fail the run, got rc={rc}\n{out}"
    assert "the notify produced NO receipt" in out, out
    assert "55b363eb-probe" in out, (
        f"the report must name the cron id, so the defective JOB is resolvable\n{out}"
    )
    assert "factory-measurement-daily-20260921T060126.log" in out, (
        f"the report must name the LOG PATH the failure was read from\n{out}"
    )
    assert "transport_error" in out, (
        f"the report must quote the failure LINE, so a reader can trace it to bytes\n{out}"
    )

def test_the_notify_leg_prints_the_population_it_examined() -> None:
    """P29: a clean verdict over a population that was never named is indistinguishable
    from one that examined nothing."""
    log_dir = _log_dir(**{"factory-measurement-daily-20260921T060126.log": _RECEIPT})
    rows = [_notify_row("factory-measurement-daily")]
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home", "other-home"],
                      unreached=["gone-home: no opencrabs.db"], prefixes=["factory-"],
                      log_dir=log_dir)
    assert rc == 0, out
    assert "LEG notify-receipt — ASSERTED" in out, out
    assert "1 enabled row(s) attributed to this factory of 1 read across 2 home(s)" in out, (
        f"the jobs read, the homes read and the family they belong to must all be named\n{out}"
    )
    assert "homes unreached: 1" in out, out
    assert "gone-home" in out, (
        f"an unreached home is REPORTED — an unreachable home is not an empty one\n{out}"
    )
    assert "logs matched: 1 of 1 log(s)" in out, out
    assert "0 produced no receipt" in out, out
    assert "read at " in out, f"the read instant must travel with the count\n{out}"

def test_a_receipt_bearing_log_is_EXCUSED_and_never_judged() -> None:
    """A notify that DELIVERED is not a finding — and the excuse says which token proved it."""
    log_dir = _log_dir(**{"factory-measurement-daily-20260919T060154.log": _RECEIPT})
    rows = [_notify_row("factory-measurement-daily")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-22T00:00:00Z")
    assert leg["problems"] == [], leg["problems"]
    assert len(leg["excused"]) == 1 and "carries a receipt" in leg["excused"][0], leg["excused"]

def test_prose_ABOUT_a_missing_receipt_does_not_satisfy_the_read() -> None:
    """The prose-as-data law (n=405 clause 5): a field prose can SATISFY is not a field.

    A log that merely MENTIONS the token must not read as a receipt, or the leg would go
    quiet exactly when it is being told the id is absent.
    """
    log_dir = _log_dir(**{
        "factory-measurement-daily-20000101T000000.log":
            "❌ the notify returned no notification id: transport_error (exit 4)\n",
        "factory-measurement-daily-20000101T000001.log":
            _FAILURE.replace("transport_error", "notification id absent; transport_error"),
    })
    rows = [_notify_row("factory-measurement-daily")]
    for name in sorted(p.name for p in log_dir.iterdir()):
        text = (log_dir / name).read_text(encoding="utf-8")
        assert RUNNER.read_notify_receipt(text) is None, (
            f"{name} mentions the token without naming an id and must NOT read as a "
            f"receipt — prose about a missing field is the n=405 clause 5 damage"
        )
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-22T00:00:00Z")
    assert len(leg["problems"]) == 2, (
        f"both logs carry no receipt and both must be reported: {leg['problems']}"
    )

def test_the_DELIVERED_form_reads_as_a_receipt_of_kind_delivered() -> None:
    """#139 criterion (b): the form the token-only predicate REFUSED now reads as a receipt.

    This is the whole defect. Measured on the live surface: the immediate-delivery branch
    writes `delivered to session <uuid>` and NO id, so a predicate requiring the id reported
    every successful delivery as a failed duty — permanently, and growing by one each time.
    """
    assert RUNNER.read_notify_receipt(_DELIVERED) == "delivered", (
        "the delivered form must read as kind 'delivered' — it is the STRONGER receipt, "
        "and refusing it was the defect"
    )
    log_dir = _log_dir(**{"factory-measurement-daily-20260924T060116.log": _DELIVERED})
    rows = [_notify_row("factory-measurement-daily")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-25T13:44:00Z")
    assert leg["problems"] == [], (
        f"a delivered notify is NOT a failed duty: {leg['problems']}"
    )
    assert len(leg["excused"]) == 1 and "(delivered)" in leg["excused"][0], (
        f"the verdict must NAME the kind — delivery and acceptance are different facts: "
        f"{leg['excused']}"
    )

def test_the_DEFERRED_form_reads_as_a_receipt_of_kind_deferred_with_its_id() -> None:
    """#139 criterion (c): the weaker form keeps its own kind, and its id is quoted."""
    assert RUNNER.read_notify_receipt(_RECEIPT) == "deferred", (
        "the deferred form proves ACCEPTANCE, not delivery — a different fact"
    )
    log_dir = _log_dir(**{"factory-measurement-daily-20260919T060154.log": _RECEIPT})
    rows = [_notify_row("factory-measurement-daily")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-25T13:44:00Z")
    assert leg["problems"] == [], leg["problems"]
    assert "(deferred, id f50759ea-b25f-475b-9c48-319dfa73dd8c)" in leg["excused"][0], (
        f"the kind AND the acceptance id must be named: {leg['excused']}"
    )

def test_BOTH_forms_without_a_uuid_are_NOT_receipts() -> None:
    """#139 criterion (d), the non-vacuity control, on BOTH forms.

    A phrase alone is prose. If the phrases matched without a uuid, a log that merely
    MENTIONS the wording — a finding ABOUT the forms, e.g. this file's own text — would read
    as a receipt, which is the n=405 clause 5 damage on two forms instead of one.
    """
    for phrase in ("delivered to session ", "deferred for session "):
        assert RUNNER.read_notify_receipt(f"❌ the notify {phrase}could not be written\n") is None, (
            f"{phrase!r} without a uuid must NOT read as a receipt"
        )
    for form in ("✅ delivered: delivered to session not-a-uuid\n",
                 "⚠️ deferred: deferred for session 6ca0d547-short: x\n"):
        assert RUNNER.read_notify_receipt(form) is None, (
            f"a malformed uuid must not satisfy the read: {form!r}"
        )
    # The POSITIVE arm beside the negative one, so the control cannot pass by the predicate
    # having stopped matching anything at all.
    assert RUNNER.read_notify_receipt(_DELIVERED) == "delivered", "positive arm"
    assert RUNNER.read_notify_receipt(_RECEIPT) == "deferred", "positive arm"

def test_a_log_with_NO_OUTPUT_is_reported_as_no_attempt_never_a_failed_duty() -> None:
    """#139 criterion (e): a 0-byte log is a notify that was never ATTEMPTED.

    Measured origin: a run row reading `interrupted: cleared by doctor --fix (orphaned: no
    live process owns this run)` left a 0-byte log, so no receipt could ever be written and
    every future patrol re-reported it — a detector that could never go green. It is
    REPORTED and NAMED, because an unreported absence is indistinguishable from a clean read.
    """
    log_dir = _log_dir(**{"factory-measurement-daily-20260922T085519.log": ""})
    rows = [_notify_row("factory-measurement-daily", row_id="orphaned-probe")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-25T13:44:00Z")
    assert leg["problems"] == [], (
        f"a notify never attempted is not a failed one: {leg['problems']}"
    )
    assert leg["coverage"]["logs_not_attempted"] == 1, leg["coverage"]
    assert leg["coverage"]["not_attempted_logs"][0]["job"] == "factory-measurement-daily", (
        leg["coverage"]
    )
    assert leg["coverage"]["logs_without_receipt"] == 0, (
        f"no-attempt must NOT be counted as a missing receipt\n{leg['coverage']}"
    )

def test_a_COMPLETED_runs_0_byte_log_is_a_FAILED_DUTY_never_an_excuse() -> None:
    """#306, acceptance leg 1: the run COMPLETED and its log is 0 bytes — that is a problem.

    Measured defect: the leg excused EVERY 0-byte log as "never attempted", so a run that
    completed, launched its notify, and then died leaving no output was filed as a run that
    never got there. The two facts leave an identical log, and only the run's own verdict
    separates them — which is why the fixture is a PAIR: this half flips the run row to
    `success` and the SAME log must go from excused to RED.
    """
    log_dir = _log_dir(**{"factory-measurement-daily-20260922T085519.log": ""})
    rows = [_notify_row("factory-measurement-daily", row_id="55b363eb-probe")]
    fires = [_run_row("factory-measurement-daily", row_id="55b363eb-probe",
                      started="2026-09-22T08:55:15Z", completed="2026-09-22T08:56:20Z",
                      status="success")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-25T13:44:00Z",
                                    fires=fires)
    assert len(leg["problems"]) == 1, (
        f"a COMPLETED run's 0-byte log is a failed duty, never 'not attempted': "
        f"{leg['problems']}"
    )
    assert "COMPLETED" in leg["problems"][0] and "status success" in leg["problems"][0], (
        leg["problems"][0]
    )
    assert leg["coverage"]["logs_not_attempted"] == 0, (
        f"the excuse must NOT be earned by a completed run\n{leg['coverage']}"
    )
    assert leg["coverage"]["logs_without_receipt"] == 1, leg["coverage"]
    assert leg["coverage"]["logs_completed_with_empty_log"] == 1, leg["coverage"]

def test_a_DELIVERY_FAILED_run_is_a_PROBLEM_and_never_an_excuse() -> None:
    """#306: `delivery_failed` is the daemon's own record that the notify WAS attempted.

    The ruling names `delivery_failed` as the value a run whose notify never delivered must
    carry, and 24 rows on this box carry it beside a `completed_at` and an error naming the
    failed delivery. So it is the failed duty itself, and excusing it would file a duty that
    was attempted and failed as one that never happened — the exact inversion #306 ends.
    """
    log_dir = _log_dir(**{"factory-measurement-daily-20260922T085519.log": ""})
    rows = [_notify_row("factory-measurement-daily", row_id="55b363eb-probe")]
    fires = [_run_row("factory-measurement-daily", row_id="55b363eb-probe",
                      started="2026-09-22T08:55:15Z", completed="2026-09-22T08:56:20Z",
                      status="delivery_failed")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-25T13:44:00Z",
                                    fires=fires)
    assert len(leg["problems"]) == 1, (
        f"an attempted-and-FAILED delivery is a failed duty, never an excuse: "
        f"{leg['problems']}"
    )
    assert "status delivery_failed" in leg["problems"][0], leg["problems"][0]
    assert "REACHED ITS DELIVERY" in leg["problems"][0], (
        f"the verdict must say WHICH completed status this is\n{leg['problems'][0]}"
    )
    assert leg["coverage"]["logs_not_attempted"] == 0, (
        f"the excuse must NOT be earned by a run that reached its delivery\n{leg['coverage']}"
    )
    assert leg["coverage"]["logs_completed_with_empty_log"] == 1, leg["coverage"]

def test_an_INTERRUPTED_runs_0_byte_log_is_excused_WITH_ITS_STATUS_NAMED() -> None:
    """#306, acceptance leg 2 — the other half of the pair: the run did NOT complete.

    This is the #139 case and it stays excused, because judging it made a permanent false
    positive out of a run orphaned before it ever reached its notify. What changes is that
    the excuse now CARRIES THE EVIDENCE: the status is named in the entry, so a reader can
    tell an excused log from one that was excused because nothing was read.
    """
    log_dir = _log_dir(**{"factory-measurement-daily-20260922T085519.log": ""})
    rows = [_notify_row("factory-measurement-daily", row_id="55b363eb-probe")]
    fires = [_run_row("factory-measurement-daily", row_id="55b363eb-probe",
                      started="2026-09-22T08:55:15Z", completed="",
                      status="interrupted")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-25T13:44:00Z",
                                    fires=fires)
    assert leg["problems"] == [], (
        f"a run that never reached its notify is not a failed duty: {leg['problems']}"
    )
    assert leg["coverage"]["logs_not_attempted"] == 1, leg["coverage"]
    entry = leg["coverage"]["not_attempted_logs"][0]
    assert entry["run_status"] == "interrupted", (
        f"the excuse must NAME the status it rests on\n{entry}"
    )
    assert leg["coverage"]["logs_not_attempted_unattributed"] == 0, (
        f"the run WAS matched, so this is not an unread surface\n{leg['coverage']}"
    )

def test_a_0_byte_log_matched_to_NO_run_is_PRINTED_as_a_read_not_an_excuse() -> None:
    """#306: an unmatched 0-byte log is a statement about the READ, and it is printed.

    With no run row carrying the log's stamp there is no verdict to excuse it, so the leg
    must not fold it into the bucket silently: the count of unmatched logs is printed beside
    the bucket's own predicate, because "the run did not complete" and "no run could be
    matched" are different facts and only the first is a finding about the box.
    """
    log_dir = _log_dir(**{"factory-measurement-daily-20260922T085519.log": ""})
    rows = [_notify_row("factory-measurement-daily", row_id="55b363eb-probe")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-25T13:44:00Z",
                                    fires=[])
    assert leg["problems"] == [], (
        f"an unmatched log is not itself a failed duty: {leg['problems']}"
    )
    assert leg["coverage"]["logs_not_attempted_unattributed"] == 1, leg["coverage"]
    assert leg["coverage"]["logs_not_attempted"] == 1, leg["coverage"]
    assert leg["coverage"]["not_attempted_logs"][0]["run_status"] == "", (
        f"no run was matched, so no status may be claimed\n{leg['coverage']}"
    )

def test_an_UNKNOWN_run_status_is_REPORTED_never_excused() -> None:
    """#306: the status vocabulary is closed, so a value outside it cannot be an excuse.

    A leg that excuses what it cannot read stops observing the class it is named for the
    moment the substrate moves: the daemon adds a status, every 0-byte log under it is
    excused, and the leg goes greener as its blind spot grows. The unknown value is
    reported with the vocabulary it was checked against.
    """
    log_dir = _log_dir(**{"factory-measurement-daily-20260922T085519.log": ""})
    rows = [_notify_row("factory-measurement-daily", row_id="55b363eb-probe")]
    fires = [_run_row("factory-measurement-daily", row_id="55b363eb-probe",
                      started="2026-09-22T08:55:15Z", completed="2026-09-22T08:56:20Z",
                      status="delivered_late")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-25T13:44:00Z",
                                    fires=fires)
    assert len(leg["problems"]) == 1, (
        f"an unrecognised run status must be reported: {leg['problems']}"
    )
    assert "delivered_late" in leg["problems"][0], leg["problems"][0]
    assert leg["coverage"]["logs_not_attempted"] == 0, leg["coverage"]

def test_the_runner_PRINTS_the_no_attempt_verdict_and_its_predicate() -> None:
    """#306's render leg: the report names the run's verdict, and prints the predicate.

    A bucket and its predicate must appear together (#163 half 2 (b)): a reader who sees
    "1 no-attempt log" without the predicate cannot tell whether the leg checked a run at
    all, and the count of logs matched to NO run is printed so an unread surface is never
    indistinguishable from a box with no failed notify.
    """
    log_dir = _log_dir(**{"factory-measurement-daily-20260922T085519.log": ""})
    rows = [_notify_row("factory-measurement-daily", row_id="55b363eb-probe")]
    fires = [_run_row("factory-measurement-daily", row_id="55b363eb-probe",
                      started="2026-09-22T08:55:15Z", completed="",
                      status="interrupted")]
    rc, out, _ = _run([], [], cron_rows=rows, prefixes=["factory-"], log_dir=log_dir,
                      cron_fires=fires)
    assert "no-attempt predicate:" in out, out
    assert "its run did NOT complete (status interrupted" in out, out
    assert "no-attempt logs matched to NO run: 0 of 1" in out, out

def test_a_NON_EMPTY_log_whose_stamp_NO_run_covers_is_EXCUSED_with_its_stamp() -> None:
    """#537 (ruling n=4009) ARM A — the filename nominates, the RECORD attributes.

    Measured origin, at the bytes: the 06:01:59Z patrol blamed `factory-triage-patrol` for
    `/tmp/factory-triage-patrol-20261020T124930.log` (954 B) and `…T124942.log` (948 B).
    Those are another lane's probe litter, and the job's own slots that day wrote four
    73-byte receipts at 00:01, 06:01, 12:02 and 18:00 — none at 12:49. The leg's asymmetry
    was the defect: a ZERO-byte log was reconciled against the run record while a NON-EMPTY
    one was judged on its filename alone, so any file carrying a cron stem was scored as a
    failed dispatch.

    Both files are reproduced here at their real size and their real stamps, against that
    day's four real slots. Nothing covers 12:49:30, so the leg must EXCUSE and PRINT — and
    the stamp it rests on must be in the report, or "no work since T" is indistinguishable
    from "not read".
    """
    log_dir = _log_dir(**{
        "factory-triage-patrol-20261020T124930.log": "x" * 954,
        "factory-triage-patrol-20261020T124942.log": "y" * 948,
    })
    rows = [_notify_row("factory-triage-patrol", row_id="triage-probe")]
    fires = [
        _run_row("factory-triage-patrol", row_id="triage-probe",
                 started=f"2026-10-20T{slot}:00Z", completed=f"2026-10-20T{slot}:40Z",
                 status="success")
        for slot in ("00:01", "06:01", "12:02", "18:00")
    ]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-10-21T06:02:00Z",
                                    fires=fires)
    assert leg["problems"] == [], (
        f"a file the run record does not attribute is not a failed dispatch: {leg['problems']}"
    )
    cov = leg["coverage"]
    assert cov["logs_uncorroborated"] == 2, cov
    stamps = sorted(row["stamp"] for row in cov["uncorroborated_logs"])
    assert stamps == ["2026-10-20T12:49:30+00:00", "2026-10-20T12:49:42+00:00"], stamps
    assert all(row["runs_of_job"] == 4 for row in cov["uncorroborated_logs"]), (
        f"the count of the job's OWN runs is what makes the excuse auditable\n{cov}"
    )
    assert cov["logs_without_receipt"] == 0, (
        f"an uncorroborated log is outside the judged population\n{cov}"
    )
    # The BITE, on the render: the excuse is loud, and it carries the stamp it rests on.
    rc, out, _ = _run([], [], cron_rows=rows, prefixes=["factory-"], log_dir=log_dir,
                      cron_fires=fires)
    assert rc == 0, out
    assert "2 log(s) EXCUSED as uncorroborated" in out, out
    assert "2026-10-20T12:49:30+00:00" in out, out
    assert "the filename nominates the job, the record does not attribute the file" in out, out

def test_the_SAME_bytes_INSIDE_a_runs_window_are_a_PROBLEM() -> None:
    """#537 ARM B — corroboration must not become a blanket excuse.

    The bytes, the job and the log surface are IDENTICAL to ARM A's; only the stamp moves,
    from 12:49:30 to a slot the record actually covers. So the two arms differ in exactly
    one fact and the verdict flips on it — which is the only shape that proves the
    corroboration is doing work rather than excusing everything it is shown (#112).

    A corroborated log with no receipt stays a PROBLEM: that is the duty that failed.
    """
    log_dir = _log_dir(**{"factory-triage-patrol-20261020T120215.log": "x" * 954})
    rows = [_notify_row("factory-triage-patrol", row_id="triage-probe")]
    fires = [_run_row("factory-triage-patrol", row_id="triage-probe",
                      started="2026-10-20T12:02:00Z", completed="2026-10-20T12:02:40Z",
                      status="success")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-10-21T06:02:00Z",
                                    fires=fires)
    assert len(leg["problems"]) == 1, (
        f"a log INSIDE a run's window is that run's own failed notify: {leg['problems']}"
    )
    assert "the notify produced NO receipt" in leg["problems"][0], leg["problems"][0]
    assert leg["coverage"]["logs_uncorroborated"] == 0, (
        f"corroboration succeeded, so nothing may be excused\n{leg['coverage']}"
    )
    assert leg["coverage"]["logs_without_receipt"] == 1, leg["coverage"]

def test_a_job_with_NO_run_rows_at_all_is_a_DECLARED_DEGRADATION_never_a_silent_excuse() -> None:
    """#537 — an unread run table must never render as a clean box (#271).

    `cron_run_fires` contributes NOTHING for a home it cannot read, so a naive
    "corroborate every candidate" would excuse EVERY log on a box whose runs table was
    unreadable — a leg that goes greener as its blind spot grows. The fallback is the
    filename proxy, and the leg DECLARES that it fell back and why, so the read is
    auditable.

    The control is ARM B's fixture with its run rows removed: same log, same job, and the
    only difference is that the record cannot corroborate anything at all.
    """
    log_dir = _log_dir(**{"factory-triage-patrol-20261020T120215.log": _FAILURE})
    rows = [_notify_row("factory-triage-patrol", row_id="triage-probe")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-10-21T06:02:00Z",
                                    fires=[])
    cov = leg["coverage"]
    assert cov["logs_corroboration_degraded"] == 1, cov
    assert cov["corroboration_degraded_logs"][0]["job"] == "factory-triage-patrol", cov
    assert cov["jobs_corroborable"] == 0, cov
    assert cov["logs_uncorroborated"] == 0, (
        f"no run rows exist, so nothing can be 'uncorroborated' — it is DEGRADED\n{cov}"
    )
    assert len(leg["problems"]) == 1, (
        f"the filename proxy still stands under degradation, so the failed notify is "
        f"still a problem: {leg['problems']}"
    )
    rc, out, _ = _run([], [], cron_rows=rows, prefixes=["factory-"], log_dir=log_dir,
                      cron_fires=[])
    assert rc == 1, out
    assert "1 judged on the FILENAME PROXY alone (declared degradation)" in out, out
    assert "carries NO run rows to corroborate it against" in out, out
    assert "corroboration predicate:" in out, out

def test_a_log_with_no_live_ROW_is_reported_as_history_and_never_judged() -> None:
    """A name this factory declares but that no enabled row carries is HISTORY.

    Judging it would red on a retired pacemaker's log forever, and a leg that cannot go
    green is a leg nobody reads. It is COUNTED and NAMED instead — the state resolved, not
    dropped (#126). The second half is the sharp edge: a row that WAS live and has been
    DISABLED is likewise history, because the population is enabled rows.
    """
    log_dir = _log_dir(**{"factory-triage-6h-20260922T000045.log": _FAILURE})
    rows = [_notify_row("factory-measurement-daily")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-22T00:00:00Z")
    assert leg["problems"] == [], (
        f"a retired job's log carries no live row to judge and must not be a problem: "
        f"{leg['problems']}"
    )
    assert leg["coverage"]["logs_retired"] == 1, leg["coverage"]
    assert leg["coverage"]["retired_logs"][0]["job"] == "factory-triage-6h", leg["coverage"]
    assert leg["coverage"]["logs_matched"] == 0, (
        f"a retired log is outside the judged population\n{leg['coverage']}"
    )

def test_a_log_whose_stem_is_a_LIVE_rows_DECLARED_redirect_is_JUDGED_not_retired() -> None:
    """#163 half 2 (a): a hand-typed label on a LIVE trigger must not hide its log in history.

    The leg's first key was the log's FILENAME stem looked up among the enabled rows' NAMES,
    and that parse cannot see a label that does not equal its job name. Measured origin: the
    job `factory-triage-patrol` wrote `/tmp/factory-triage-6h-<ts>.log` for 16 rounds, the
    stem matched no row, and every one of those logs landed in `retired_logs` as history —
    while the 2026-09-25T12:00:32Z fire's own redirect log carried no receipt and no
    directive reached the woken lane. The leg built to catch that reported the log clean.

    A live surface is never history: the stem its OWN prompt declares puts the log in the
    judged population, and the mismatch is NAMED.
    """
    log_dir = _log_dir(**{"factory-triage-6h-20260922T000045.log": _FAILURE})
    rows = [_thin("factory-triage-patrol",
                  prompt="/tmp/factory-triage-6h-$(date -u +%Y%m%dT%H%M%S).log")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-22T00:00:00Z")
    assert leg["coverage"]["logs_retired"] == 0, (
        f"a stem a LIVE row declares in its own prompt is not history\n{leg['coverage']}"
    )
    assert leg["coverage"]["logs_attributed_by_redirect"] == 1, leg["coverage"]
    assert leg["coverage"]["attributed_by_redirect"][0]["row"] == "factory-triage-patrol", (
        f"the log must name the LIVE row that declares it\n{leg['coverage']}"
    )
    assert leg["coverage"]["logs_without_receipt"] == 1, (
        f"judged, so its missing receipt is reported rather than filed as history\n"
        f"{leg['coverage']}"
    )
    assert len(leg["problems"]) == 1 and "factory-triage-6h" in leg["problems"][0], (
        f"the live mis-labelled log must be a NAMED problem: {leg['problems']}"
    )

def test_a_stem_NO_live_row_declares_stays_HISTORY() -> None:
    """NEGATIVE CONTROL for the arm above: the bucket is keyed on the DECLARED stem.

    A fix that moved every unmatched stem into the judged population would be worse than
    the defect — it would red forever on genuinely retired pacemakers' logs, and a leg that
    cannot go green is a leg nobody reads. So a row declaring a DIFFERENT redirect does not
    adopt this log.
    """
    log_dir = _log_dir(**{"factory-triage-6h-20260922T000045.log": _FAILURE})
    rows = [_thin("factory-measurement-daily",
                  prompt="/tmp/factory-measurement-daily-$(date -u +%Y%m%dT%H%M%S).log")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-22T00:00:00Z")
    assert leg["coverage"]["logs_retired"] == 1, (
        f"a stem no live row declares is genuinely history\n{leg['coverage']}"
    )
    assert leg["coverage"]["logs_attributed_by_redirect"] == 0, leg["coverage"]
    assert leg["problems"] == [], (
        f"history is never a problem\n{leg['problems']}"
    )

def test_a_CLASS_1_row_is_NAMED_with_its_class_never_counted() -> None:
    """#148 acceptance 1: a class-gate that prints only a COUNT fails.

    `#119` created the class and the detection worked; nothing acted on the finding, so the
    row stayed broken while every mechanical surface read clean (criterion 4 of #148, ruling
    n=1169: "a count is a fact about a population and a repairer needs an OBJECT"). The leg
    must therefore NAME the row and its class, not merely report that a class exists.
    """
    rows = [_cron("factory-broken-pacemaker", deliver_to=f"oc://session/{_SESSION_UUID}",
                  prompt=_WAKE_PROMPT)]
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home"], unreached=[],
                      prefixes=["factory-"])
    assert rc != 0, f"a class-1 row is a problem, so the run reds\n{out}"
    assert "factory-broken-pacemaker" in out, (
        f"the class-1 row must be NAMED, never folded into a count\n{out}"
    )
    assert "unbaked" in out, f"the finding must name the CLASS it belongs to\n{out}"
    assert "route: factory-broken-pacemaker — unbaked-target" in out, (
        f"and its CURRENT route must be printed per row WITH ITS CLASS, not merely the "
        f"predicate's finding — so a row that regresses into class 1 is named as class 1\n"
        f"{out}"
    )

def test_the_leg_prints_the_CURRENT_delivery_path_of_every_attributed_row() -> None:
    """#148 acceptance 2: the scheduled check asserts the state READ, not a forecast.

    The patrol runs on a cron cadence, so the current delivery path of each attributed row
    is what makes the row's health assertable by a RUN rather than predicted by a plan.
    """
    rows = [
        _cron("factory-prompt-notify",
              prompt=f"{_WAKE_PROMPT} then run session notify for the lane\n\n{_NONE_DECL}"),
        _cron("factory-session-target", deliver_to=f"session:{_SESSION_UUID}",
              prompt=f"{_WAKE_PROMPT}\n\n{_NONE_DECL}"),
    ]
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home"], unreached=[],
                      prefixes=["factory-"])
    assert rc == 0, f"both rows are thin and must be clean\n{out}"
    assert "delivery paths:" in out, f"the routes block must be printed\n{out}"
    assert "route: factory-prompt-notify — prompt-notify (no deliver_to)" in out, (
        f"each attributed row's CURRENT route must be named with the field it came from\n{out}"
    )
    assert "route: factory-session-target — session-target" in out, out
    assert "2 attributed row(s)" in out, f"the population must be printed\n{out}"

def test_a_row_this_factory_does_NOT_own_is_not_in_the_routes_block() -> None:
    """NEGATIVE CONTROL: the block's population is the ATTRIBUTED set, not every row read.

    A block that named rows this factory has no authority over would turn a per-factory
    report into a box-wide one (#101, ruling n=610 part 3b).
    """
    rows = [
        _cron("factory-mine",
              prompt=f"{_WAKE_PROMPT} then run session notify for the lane\n\n{_NONE_DECL}"),
        _cron("other-factory-job",
              prompt=f"{_WAKE_PROMPT} then run session notify for the lane\n\n{_NONE_DECL}"),
    ]
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home"], unreached=[],
                      prefixes=["factory-"])
    assert rc == 0, out
    routes_block = out.split("delivery paths:", 1)[1]
    assert "route: factory-mine" in routes_block, routes_block
    assert "other-factory-job" not in routes_block.split("homes unreached", 1)[0], (
        f"an unattributed row is REPORTED in its own bucket, never judged here\n{routes_block}"
    )

def test_the_retired_bucket_prints_its_POPULATION_and_its_PREDICATE() -> None:
    """#163 half 2 (b): "no retired logs" and "a bucket that cannot see one" must differ.

    The bucket is the leg's silent-exclusion surface, so an empty read has to PRINT the
    population it examined and the predicate that emptied it. A bare zero is
    indistinguishable from a bucket whose key can never match.
    """
    # arm 1 — nothing retired: the zero must still carry its predicate.
    rows = [_notify_row("factory-measurement-daily")]
    log_dir = _log_dir(**{"factory-measurement-daily-20260921T060126.log": _RECEIPT})
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home"], unreached=[],
                      prefixes=["factory-"], log_dir=log_dir)
    assert rc == 0, out
    assert "retired: 0 log(s)" in out, (
        f"an empty bucket must print its population rather than vanish\n{out}"
    )
    assert "names no enabled row this factory declares" in out, (
        f"the bucket's PREDICATE must be printed beside its population\n{out}"
    )

    # arm 2 — a live label mismatch: NAMED as judged, never filed as history.
    rows2 = [_thin("factory-triage-patrol",
                   prompt="/tmp/factory-triage-6h-$(date -u +%Y%m%dT%H%M%S).log")]
    log_dir2 = _log_dir(**{"factory-triage-6h-20260922T000045.log": _FAILURE})
    _, out2, _ = _run([], [], cron_rows=rows2, homes=["probe-home"], unreached=[],
                      prefixes=["factory-"], log_dir=log_dir2)
    assert "attributed by DECLARED REDIRECT" in out2, (
        f"a live label mismatch must be VISIBLE in the report\n{out2}"
    )
    assert "live label mismatch" in out2 and "factory-triage-patrol" in out2, (
        f"the mismatch must NAME the live row that owns the log\n{out2}"
    )

def test_a_log_nobody_here_declares_is_reported_and_never_judged() -> None:
    """Another factory's law is not this factory's to enforce (#101, ruling n=610 part 3b)."""
    log_dir = _log_dir(**{"sibling-some-other-job-20260922T000045.log": _FAILURE})
    rows = [_notify_row("factory-measurement-daily")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-22T00:00:00Z")
    assert leg["problems"] == [], (
        f"an unattributable log belongs in the population read, never in the problems: "
        f"{leg['problems']}"
    )
    assert leg["coverage"]["logs_unattributed"] == 1, leg["coverage"]
    assert leg["coverage"]["unattributed_logs"][0]["job"] == "sibling-some-other-job", leg["coverage"]

def test_a_log_that_exists_and_cannot_be_READ_is_a_problem_not_an_absence() -> None:
    """The #69 clause (e) shape: a declared surface that defeats the read is a defect.

    An unreadable log rendering as an absent one is the failure mode that makes a reader
    worse than useless — the notify may have failed and the leg would say nothing.

    The read failure is DRIVEN rather than simulated with a permission bit: this gate runs
    as root on this box, and root reads a `chmod 000` file happily, so a permission-bit
    probe would pass for the wrong reason here and fail in a factory that runs as a user.
    """
    log_dir = _log_dir(**{"factory-measurement-daily-20260921T060126.log": _FAILURE})
    target = log_dir / "factory-measurement-daily-20260921T060126.log"
    rows = [_notify_row("factory-measurement-daily")]
    real_read_text = Path.read_text

    def denying_read_text(self, *args, **kwargs):
        if self == target:
            raise OSError("probe: simulated read failure")
        return real_read_text(self, *args, **kwargs)

    with mock.patch.object(Path, "read_text", denying_read_text):
        leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                        log_dir=log_dir, read_at="2026-09-22T00:00:00Z")
    assert leg["problems"], "an unreadable log must be a problem, never an absence"
    assert "could not be read" in leg["problems"][0], leg["problems"]
    assert "never an absence" in leg["problems"][0], leg["problems"]
    assert leg["coverage"]["logs_without_receipt"] == 0, (
        f"the row was never JUDGED — it failed at the read, which is a different fact: "
        f"{leg['coverage']}"
    )

def test_an_absent_log_directory_is_a_NOT_RUN_with_its_reason() -> None:
    """A read that never happened must never render as a read that found nothing.

    Stated in the leg's own contract, so this is asserted against the leg rather than
    through main() — main() takes the constant path that exists.
    """
    rows = [_notify_row("factory-measurement-daily")]
    leg = RUNNER.notify_receipt_leg(rows, ["probe-home"], [], ["factory-"],
                                    log_dir=Path("/tmp/does-not-exist-probe-122"),
                                    read_at="2026-09-22T00:00:00Z")
    assert leg["status"] == "NOT RUN", leg["status"]
    assert leg["reason"] and "does not exist" in leg["reason"], leg["reason"]
    assert leg["problems"] == [], (
        f"an unread surface is NOT RUN, never a problem and never a silent pass: {leg}"
    )

def test_the_leg_finds_the_LIVE_surface_and_never_copies_it() -> None:
    """The leg reads `/tmp` IN PLACE by constant, and the constant is this tool's own.

    A copy of a live surface is stale the moment it is written, and the failure log is a
    file that the next run overwrites; there is nothing to copy and no reason to.
    """
    assert RUNNER.LOG_DIR == Path("/tmp"), f"the surface is /tmp, not {RUNNER.LOG_DIR}"
    matched, reason = RUNNER.notify_logs(RUNNER.LOG_DIR)
    assert reason is None, f"the live surface must be readable here: {reason}"
    assert all(
        RUNNER.NOTIFY_LOG_RE.match(path.name) for _, path in matched
    ), "every matched path must carry a `<job>-<stamp>.log` name"
    print(f"  live log surface: {len(matched)} matched log(s) under {RUNNER.LOG_DIR}")

def test_the_leg_shares_the_manifest_declaration_with_the_CRON_leg() -> None:
    """ONE attribution predicate, TWO legs — imported, never re-derived.

    Ownership is the manifest's declared `job_prefixes`, so a leg that re-derived it would
    judge a different population than the leg beside it and the two reports could never be
    reconciled.
    """
    rows = [
        _notify_row("factory-mine"),
        dict(_notify_row("sibling-not-mine"), home="other-home"),
    ]
    mine, nobody = RUNNER.attribute_rows(rows, ["factory-"])
    assert [r["name"] for r in mine] == ["factory-mine"], mine
    assert [r["name"] for r in nobody] == ["sibling-not-mine"], nobody

def test_the_box_read_SUPPLIES_the_id_that_resolves_each_row() -> None:
    """THE DEFECT THIS PROBE EXISTS FOR, measured live before it was written.

    The leg's first live run reported every finding as `(cron id unstated)`, because the
    box read projected only name/deliver_to/prompt and the id never reached the report.
    The probes above could not see it: they HAND the leg a row that already carries an id,
    so they fed it the very field whose absence was the bug. A criterion naming "the job
    id" is satisfied by a row that HAS one, and the read path is where it is lost.
    """
    root = Path(tempfile.mkdtemp()) / "profiles"
    (root / "ops").mkdir(parents=True)
    _home_db(root.parent / "opencrabs.db",
             ("id-in-default-home", "factory-default-home", "", "", 1))
    _home_db(root / "ops" / "opencrabs.db",
             ("id-in-ops-home", "factory-ops-home", "session:probe", _WAKE_PROMPT, 1),
             ("id-disabled", "factory-disabled", "", "", 0))
    rows, homes_read, unreached = RUNNER.box_cron_rows(root)
    assert unreached == [], unreached
    assert len(homes_read) == 2, f"both homes must be read: {homes_read}"
    by_name = {row["name"]: row for row in rows}
    assert set(by_name) == {"factory-default-home", "factory-ops-home"}, (
        f"the read is of ENABLED rows only: {sorted(by_name)}"
    )
    for name in ("factory-default-home", "factory-ops-home"):
        assert by_name[name].get("id"), (
            f"{name} was read without an id — a report cannot resolve a row it names by "
            f"a name two homes may share (#126)"
        )
    assert by_name["factory-ops-home"]["id"] == "id-in-ops-home", by_name

def test_a_finding_reports_the_id_read_from_the_box_not_a_placeholder() -> None:
    """End to end over the same throwaway shape: the id in the REPORT is the id on the ROW.

    The report is what a reader acts on. A placeholder there — `unstated`, `row 3` — is a
    finding that cannot be resolved to a cron job, which is the whole job of the line.
    """
    root = Path(tempfile.mkdtemp()) / "profiles"
    (root / "ops").mkdir(parents=True)
    _home_db(root.parent / "opencrabs.db")
    _home_db(root / "ops" / "opencrabs.db",
             ("55b363eb-live", "factory-measurement-daily", "session:probe", _WAKE_PROMPT, 1))
    rows, homes_read, unreached = RUNNER.box_cron_rows(root)
    log_dir = _log_dir(**{"factory-measurement-daily-20260921T060126.log": _FAILURE})
    leg = RUNNER.notify_receipt_leg(rows, homes_read, unreached, ["factory-"],
                                    log_dir=log_dir, read_at="2026-09-22T00:00:00Z")
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "55b363eb-live" in leg["problems"][0], leg["problems"]
    assert "unstated" not in leg["problems"][0], (
        f"the id was read from the row and must be reported, never hedged\n"
        f"{leg['problems'][0]}"
    )

def test_the_canonicality_leg_primes_ON_the_ledger_it_was_given() -> None:
    """A leg is only as good as the population it enumerates, so the population is stated.

    `rows_declaring_tier` is legitimately zero today — the field is new — and zero THERE
    is not a vacuous clean, because the enumeration asserted non-empty is `rows_read`.
    """
    rows = _rows(("intake", "#1", 1), ("close", "#1", 2))
    leg = RUNNER.canonicality_leg(rows, read_at="2026-09-23T11:00Z")
    assert leg["name"] == "canonicality-tier", leg["name"]
    assert leg["status"] == "ASSERTED", leg
    cov = leg["coverage"]
    assert cov["rows_read"] == 2, cov
    assert cov["rows_declaring_tier"] == 0, cov
    assert leg["problems"] == [], leg["problems"]

def test_a_STANDING_T4_is_reported_and_names_the_tier() -> None:
    """The probe that proves this leg BITES: force a T4, and it must not read clean.

    The declaration sits in the canonical trailer — the run of `key=value` tokens at the
    END of the detail (SKILL.md section 11). Prose after it terminates the run, which is
    the next test's subject.
    """
    rows = [_tier_row(1, "#900", "open question: which twin is canonical run=7 tier=T4")]
    leg = RUNNER.canonicality_leg(rows, read_at="2026-09-23T11:00Z")
    assert leg["problems"], "a standing T4 produced no problem — the leg is vacuous"
    joined = " ".join(leg["problems"])
    assert "tier=T4" in joined, joined
    assert "NEITHER side is canonical" in joined, joined
    assert leg["coverage"]["t4_standing"] == 1, leg["coverage"]

def test_a_T4_superseded_by_a_LATER_row_stops_reding_for_ever() -> None:
    """A leg with no exit teaches the next reader to ignore a red patrol (#139).

    The read is a SEQUENCE: once a later row for the same subject declares a resolved
    tier, the T4 is history, not a standing finding.
    """
    rows = [
        _tier_row(1, "#900", "unresolved run=7 tier=T4"),
        _tier_row(2, "#900", "resolved run=8 tier=T1"),
    ]
    leg = RUNNER.canonicality_leg(rows, read_at="2026-09-23T11:00Z")
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["t4_superseded"] == 1, leg["coverage"]
    assert leg["coverage"]["t4_standing"] == 0, leg["coverage"]

def test_a_T4_for_a_DIFFERENT_subject_is_not_superseded_by_the_wrong_row() -> None:
    """Supersession is keyed on the SUBJECT, never on mere recency.

    An earlier draft compared indices alone, which would let any later row anywhere in
    the ledger resolve any earlier T4 — the adjacency error, in a new place.
    """
    rows = [
        _tier_row(1, "#900", "unresolved run=7 tier=T4"),
        _tier_row(2, "#901", "an unrelated subject run=8 tier=T1"),
    ]
    leg = RUNNER.canonicality_leg(rows, read_at="2026-09-23T11:00Z")
    assert leg["coverage"]["t4_standing"] == 1, leg["coverage"]
    assert leg["coverage"]["unresolved_subjects"] == ["#900"], leg["coverage"]

def test_an_EMPTY_tier_population_is_NOT_a_vacuous_clean() -> None:
    """The loud-fail form is WRONG for a forward-only population, and this pins why.

    `rows_declaring_tier` is legitimately zero until the first tier lands, so failing on
    zero would red the patrol for a state that is not a defect — the permanent
    false-positive class #139 names. Section 8's own clause (#112, ruling n=657 item 8)
    makes NON-VACUITY a property of the PROBE for exactly this shape, and
    `test_a_STANDING_T4_is_reported_and_names_the_tier` above is that probe. What the
    RUN must carry is POPULATION VISIBILITY, not a synthetic finding.
    """
    leg = RUNNER.canonicality_leg([], read_at="2026-09-23T11:00Z")
    assert leg["problems"] == [], (
        "an empty tier population must not manufacture a finding — non-vacuity is the "
        f"probe's job here, and this leg is forward-only: {leg['problems']}"
    )
    assert leg["coverage"]["rows_read"] == 0, leg["coverage"]
    assert "rows_declaring_tier" in leg["coverage"], leg["coverage"]

def test_the_leg_PRINTS_the_population_it_examined() -> None:
    """Population visibility is the RUN's property: a count travelling with its predicate."""
    rows = [_tier_row(1, "#900", "settled run=7 tier=T1")]
    rc, out, _ = _run([], rows)
    assert "1 of 1 declare a tier" in out, out

def test_an_unrecognised_tier_is_a_defect_not_a_resolution() -> None:
    """`tier=T9` cannot have resolved a discrepancy, and reading it as one is the bug."""
    rows = [_tier_row(1, "#902", "nonsense run=7 tier=T9")]
    leg = RUNNER.canonicality_leg(rows, read_at="2026-09-23T11:00Z")
    assert leg["problems"], "an unrecognised tier passed"
    assert "not one of" in " ".join(leg["problems"]), leg["problems"]

def test_a_tier_OUTSIDE_the_canonical_trailer_is_a_mention_not_a_declaration() -> None:
    """The read is trailer-scoped by design, and this pins that it is not a bug.

    A detail whose trailer is terminated by prose declares nothing: the same rule that
    makes a quoted trailer mid-sentence not a declaration (#91, ruled at n=572 PART 3).
    """
    rows = [_tier_row(1, "#903", "a mention only tier=T4 and then prose follows")]
    leg = RUNNER.canonicality_leg(rows, read_at="2026-09-23T11:00Z")
    assert leg["coverage"]["rows_declaring_tier"] == 0, leg["coverage"]
    assert leg["problems"] == [], leg["problems"]

def test_the_leg_reaches_the_RENDERED_report_and_reds_the_run() -> None:
    """End to end: a standing T4 must appear in the report AND set the exit code."""
    rows = [_tier_row(1, "#900", "unresolved run=7 tier=T4")]
    rc, out, _ = _run([], rows)
    assert "LEG canonicality-tier" in out, out
    assert "tier=T4" in out, out
    assert rc == 1, f"a standing T4 must red the run, got rc={rc}\n{out}"

def test_a_clean_ledger_reads_clean_in_the_RENDERED_report() -> None:
    """The negative half: with nothing unresolved the leg must not manufacture a finding."""
    rows = [_tier_row(1, "#900", "settled run=7 tier=T1")]
    rc, out, _ = _run([], rows)
    assert "LEG canonicality-tier" in out, out
    assert "1 standing tier=T4" not in out, out
    assert "0 standing tier=T4" in out, out

def test_the_leg_reads_through_the_SHARED_predicate_never_a_private_split() -> None:
    """One field, one predicate (section 11) — a private parse is the defect it names."""
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "field_predicate" in source, "the leg does not bind to the shared predicate"
    start = source.index("def canonicality_leg")
    end = source.index("def deferred_legs")
    body = source[start:end]
    assert "trailer_tokens(" in body, "the trailer read must come from the module"
    assert "keyed_value(" in body, "the value read must come from the module"
    assert '.split("=")' not in body, "a private split is exactly what the law bars"

def test_probe_the_strict_arm_still_resolves() -> None:
    """Arm 1, and the reason the shared predicate is NOT widened: `issue_reference` is
    strictly numeric by design and its own gate depends on that."""
    pred = RUNNER.load_predicate()
    ruling = {"n": 1, "event": "ruling", "subject": "#42", "detail": "ruled"}
    issue, arm, _bridge = RUNNER.resolve_ruling_issue(ruling, [ruling], pred)
    assert (issue, arm) == (42, "strict"), (issue, arm)

def test_probe_the_BRIDGE_resolves_a_slug_subject() -> None:
    """Arm 2 — the shape the ledger really carries, and the one #243 was filed for.

    The ruling is stamped under a SLUG (`foreign-instrument-coupling`) while the issue is
    filed a row later under `#85`, so the strict form returns None and the row is invisible
    to `ruled`. The bridge is a row that POINTS AT this ruling (`ref row:<n>`, the ledger's
    declared ref form) and itself names an issue — the n=545 / n=546 shape. A row that only
    QUOTES the ruling is evidence and does not bridge (#551 remedy 2).
    """
    pred = RUNNER.load_predicate()
    ruling = {"n": 545, "event": "ruling", "subject": "foreign-instrument-coupling",
              "detail": "OWNER ORDER: do not use the instruments ..."}
    # The citing row must carry a TYPED pointer (`ref row:<n>`) before its mention of the
    # ruling's `n` counts as ownership — remedy 2 of #551's ruling, and the reason the two
    # halves landed in separate commits.
    dispatch = {"n": 546, "event": "dispatch", "subject": "#85",
                "detail": "DISPATCH #85 ... Ruling n=545 ref row:545; issue filed at https://x/issues/85"}
    issue, arm, bridge = RUNNER.resolve_ruling_issue(ruling, [ruling, dispatch], pred)
    assert (issue, arm) == (85, "bridged"), (issue, arm)
    assert bridge == {"n": 546, "event": "dispatch"}, bridge

    # A bare-number subject is ALSO a real form (n=516 carries subject `77`, which its own
    # correction row n=518 complains about) — so the bridge must read it too.
    bare = {"n": 517, "event": "dispatch", "subject": "77",
            "detail": "see Ruling n=545, ref row:545"}
    issue, arm, _bridge = RUNNER.resolve_ruling_issue(ruling, [ruling, bare], pred)
    assert (issue, arm) == (77, "bridged"), (issue, arm)

    # REMEDY 2 — the SAME mention WITHOUT the typed pointer is evidence, not ownership, so
    # the row stays unbridgeable. This is the arm that would have caught all 16
    # mis-attributions measured before the narrowing.
    quote_only = {"n": 547, "event": "dispatch", "subject": "#85",
                  "detail": "DISPATCH #85 ... Ruling n=545; issue filed at https://x/issues/85"}
    issue, arm, _bridge = RUNNER.resolve_ruling_issue(ruling, [ruling, quote_only], pred)
    assert (issue, arm) == (None, "unbridgeable"), (issue, arm)

def test_probe_the_DECLARED_arm_is_constructible_because_it_has_NO_live_instance() -> None:
    """Arm 3, driven off a FIXTURE because the token has zero live rows.

    Measured by Triage: `governs=` occurs exactly twice in the whole ledger — inside the
    ruling that PRESCRIBES it and its dispatch. So the arm is prospective, and a probe that
    could not construct it would leave the arm unexercised while reading as covered.
    """
    pred = RUNNER.load_predicate()
    ruling = {"n": 900, "event": "ruling", "subject": "some-concern",
              "detail": "a ruling that governs a concern rather than an item. governs=1234"}
    issue, arm, _bridge = RUNNER.resolve_ruling_issue(ruling, [ruling], pred)
    assert (issue, arm) == (1234, "declared"), (issue, arm)

def test_probe_an_issue_quoting_an_ORPHANED_ROW_resolves_to_unbridgeable() -> None:
    """#551 remedy 3's acceptance: a DANGLING pointer adopts nothing.

    A row can mention the ruling and still aim its typed pointer at a row this ledger does
    not hold — `ref row:949` when no 949 was ever stamped. The mention is there, so a
    substring predicate hands over the row's issue; the pointer is dangling, so ownership is
    NOT established. The ruling stays `unbridgeable` and is printed, rather than silently
    adopting `#777`.

    Driven off a FIXTURE because the live ledger carries no such pair today, and paired with
    a positive control in the same test: the refusal must come from the pointer's TARGET,
    never from a predicate that cannot resolve at all.
    """
    pred = RUNNER.load_predicate()
    ruling = {"n": 950, "event": "ruling", "subject": "slug-with-no-issue",
              "detail": "a ruling about a concern"}

    # Mentions the ruling (so the substring test PASSES) but points at an ORPHANED row.
    dangling = {"n": 951, "event": "dispatch", "subject": "#777",
                "detail": "DISPATCH #777 ... Ruling n=950; ref row:949"}
    issue, arm, bridge = RUNNER.resolve_ruling_issue(ruling, [ruling, dangling], pred)
    assert (issue, arm, bridge) == (None, "unbridgeable", None), (issue, arm, bridge)

    # Positive control: the same row, pointing at the ruling itself, DOES bridge.
    pointing = {"n": 952, "event": "dispatch", "subject": "#777",
                "detail": "DISPATCH #777 ... Ruling n=950; ref row:950"}
    issue, arm, bridge = RUNNER.resolve_ruling_issue(ruling, [ruling, pointing], pred)
    assert (issue, arm) == (777, "bridged"), (issue, arm)
    assert bridge == {"n": 952, "event": "dispatch"}, bridge

def test_probe_the_leg_PRINTS_an_unbridgeable_row_instead_of_dropping_it() -> None:
    """Clause 2: a resolver that cannot place a row must SAY SO.

    Silence here reports a smaller population than the leg examined — the leg would read
    as though every ruling resolved, which is the false-clean shape the population clause
    forbids. The count travels beside the verdict.
    """
    pred = RUNNER.load_predicate()
    ruling = {"n": 901, "event": "ruling", "subject": "no-issue-anywhere",
              "detail": "governs nothing identifiable"}
    issue, arm, _bridge = RUNNER.resolve_ruling_issue(ruling, [ruling], pred)
    assert (issue, arm) == (None, "unbridgeable"), (issue, arm)

    # ...and the leg's coverage carries them, so the print is not the only reader.
    issues = [_issue_with_comments(1, "OPEN", "## RULED — a ruling.\n")]
    rows = [ruling, {"n": 902, "event": "intake", "subject": "#1", "detail": "intake"}]
    leg = RUNNER.board_ruling_leg(issues, rows, read_at="probe", predicate=pred,
                                  scope=RUNNER.UNBOUNDED_SCOPE,
                                  exemptions_path=_NO_RULING_EXEMPTIONS)
    cov = leg["coverage"]
    assert cov["rulings_unbridgeable"] == 1, cov
    assert cov["unbridgeable_rows"] == [{"n": 901, "subject": "no-issue-anywhere"}], cov
    # The closure is over a GENUINE row counter (#545, ruling n=4096 clause 3). The line
    # that stood here compared `rulings_read` with the two numbers it was computed FROM —
    # `len(ruled) + len(unbridgeable)` — so it held on every possible input, including the
    # bug it was meant to catch: the field reported 550 against 658 rows read and the
    # assertion could not see it. The row count is stated outright now, and the partition
    # is checked against the counters that actually count rows.
    assert cov["rulings_read"] == 1, cov          # ONE `ruling` row, so ONE row read
    assert cov["rulings_resolved_rows"] == 0, cov
    assert cov["rulings_repeated"] == 0, cov
    assert cov["rulings_read"] == cov["rulings_resolved_rows"] + cov["rulings_unbridgeable"], cov

def test_probe_the_BRIDGE_is_the_thing_that_moves_the_population() -> None:
    """The NON-VACUITY control for clause 3 — re-armed by #511, on the surface it still owns.

    Neutering the bridge moves the bridged row out of the RESOLVED population. The probe
    drives the REAL leg twice over one fixture: once with the dispatch present, once without
    — so the difference is attributable to the bridge and not to the fixture.

    WHAT #511 CHANGED HERE, and why the old assertion was wrong rather than merely failing.
    This probe used to assert that dropping the bridge produced a PROBLEM, because the
    issue-level short-circuit judged a comment only when its issue resolved to a `ruling`
    row. Under per-act pairing the verdict belongs to the COMMENT ID: the row names
    `comment=<id>`, the id is globally unique, and so the act IS recorded whether or not the
    row's SUBJECT can be attributed to an issue. Keeping the old assertion would have
    restored the short-circuit it was written against — a problem invented from an
    unresolvable subject, which is the same false red one layer over. The bridge's remaining
    job is the POPULATION question, and that is what is asserted: the row is resolved, or it
    is PRINTED as unbridgeable, never silently dropped (#243 clause 2).
    """
    pred = RUNNER.load_predicate()
    issues = [_issue_with_comments(85, "OPEN", "## RULED — settled on the board.\n")]
    ruling = {"n": 545, "event": "ruling", "subject": "foreign-instrument-coupling",
              "detail": f"the clause comment={_comment_numeric(85)}"}
    dispatch = {"n": 546, "event": "dispatch", "subject": "#85",
                "detail": "Ruling n=545 ref row:545"}

    with_bridge = RUNNER.board_ruling_leg(issues, [ruling, dispatch], read_at="probe",
                                          predicate=pred,
                                          scope=RUNNER.UNBOUNDED_SCOPE,
                                          exemptions_path=_NO_RULING_EXEMPTIONS)
    assert with_bridge["problems"] == [], with_bridge["problems"]
    assert with_bridge["coverage"]["rulings_resolved"] == 1, with_bridge["coverage"]
    assert with_bridge["coverage"]["rulings_unbridgeable"] == 0, with_bridge["coverage"]
    assert with_bridge["coverage"]["rulings_paired"] == 1, with_bridge["coverage"]

    # Remove ONLY the bridge row: the row leaves the resolved population and is PRINTED.
    without = RUNNER.board_ruling_leg(issues, [ruling], read_at="probe", predicate=pred,
                                      scope=RUNNER.UNBOUNDED_SCOPE,
                                      exemptions_path=_NO_RULING_EXEMPTIONS)
    assert without["coverage"]["rulings_resolved"] == 0, without["coverage"]
    assert without["coverage"]["rulings_unbridgeable"] == 1, without["coverage"]
    assert without["coverage"]["unbridgeable_rows"] == [
        {"n": 545, "subject": "foreign-instrument-coupling"}
    ], without["coverage"]["unbridgeable_rows"]
    # The ACT is still recorded, so the comment is still paired: two questions, two surfaces.
    assert without["coverage"]["rulings_paired"] == 1, without["coverage"]
    assert without["problems"] == [], without["problems"]

def test_the_ruling_partition_BITES_on_a_RE_RULED_issue() -> None:
    """#545, ruling n=4096 clause 3 — the arm without which the closure proves nothing.

    A re-ruling is the append-only ledger WORKING, not a duplicate to drop: on the live
    ledger 646 successful row-resolves collapse to 538 distinct issue numbers, because 69
    issues carry more than one `ruling` row (`#50` six times — `n=287,289,293,299,305,311,312`
    — `#453` and `#47` four each). The defect was telemetry: `board_ruling_leg` emitted
    `rulings_read` as `len(ruled) + len(unbridgeable)`, a sum of the sets it had just built,
    so the field named for the ROWS READ reported 550 against 658 rows and under-reported by
    exactly the 108 repeats; `board_unruled_leg` printed `ruling_rows_read=658` beside
    `538 + 12`, reading 108 short of itself.

    THIS FIXTURE RE-RULES ONE ISSUE ON PURPOSE. With one ruling row per issue the derived
    sum and the true counter agree, so an arm built on single-ruling fixtures cannot tell
    them apart — it would be exactly as vacuous as the tautology it replaces. Reverting
    `rulings_read` to `len(ruled) + len(unbridgeable)` reds this arm (3 rows read, 2
    reported), and folding `rulings_repeated` to a constant zero reds it as well.
    """
    pred = RUNNER.load_predicate()
    issues = [_issue_with_comments(7, "OPEN", "## RULED — settled on the board.\n")]
    comment = _comment_numeric(7)
    rows = [
        {"n": 1, "event": "ruling", "subject": "#7",
         "detail": f"the first ruling, comment={comment}"},
        # The SAME issue, ruled AGAIN: legitimate supersession the ledger keeps.
        {"n": 2, "event": "ruling", "subject": "#7",
         "detail": f"the second ruling supersedes the first, comment={comment}"},
        {"n": 3, "event": "ruling", "subject": "no-issue-anywhere",
         "detail": "governs nothing identifiable"},
        {"n": 4, "event": "intake", "subject": "#7", "detail": "intake"},
    ]

    leg = RUNNER.board_ruling_leg(issues, rows, read_at="probe", predicate=pred,
                                  scope=RUNNER.UNBOUNDED_SCOPE,
                                  exemptions_path=_NO_RULING_EXEMPTIONS)
    cov = leg["coverage"]
    assert cov["rulings_read"] == 3, cov
    assert cov["rulings_resolved_rows"] == 2, cov
    assert cov["rulings_resolved"] == 1, cov   # DISTINCT — it feeds the population predicate
    assert cov["rulings_repeated"] == 1, cov
    assert cov["rulings_unbridgeable"] == 1, cov
    # BOTH closures the ruling names, each read off a counter that counts ROWS.
    assert cov["rulings_read"] == (
        cov["rulings_resolved_rows"] + cov["rulings_unbridgeable"]
    ), cov
    assert cov["rulings_resolved_rows"] == (
        cov["rulings_resolved"] + cov["rulings_repeated"]
    ), cov
    # The VERDICT is untouched by the partition: a repeated resolve adds nothing to a set,
    # so no unit changes side. That is the bound the ruling states — telemetry only.
    assert leg["problems"] == [], leg["problems"]

    # The SAME partition in the other ruling leg, so the two cannot drift (#545 clause 2).
    unruled = RUNNER.board_unruled_leg(issues, rows, read_at="probe", predicate=pred)
    ucov = unruled["coverage"]
    assert ucov["ruling_rows_read"] == 3, ucov
    assert ucov["rulings_resolved_rows"] == 2, ucov
    assert ucov["rulings_resolved"] == 1, ucov
    assert ucov["rulings_repeated"] == 1, ucov
    assert ucov["rulings_unbridgeable"] == 1, ucov
    assert ucov["ruling_rows_read"] == (
        ucov["rulings_resolved_rows"] + ucov["rulings_unbridgeable"]
    ), ucov
    assert ucov["rulings_resolved_rows"] == (
        ucov["rulings_resolved"] + ucov["rulings_repeated"]
    ), ucov

    # AND IT PRINTS: a reader must be able to check the closure on the run, without opening
    # the source. Both legs print the partition beside the verdict.
    rc, out, _ = _run(issues, rows, ruling_scope=RUNNER.UNBOUNDED_SCOPE,
                      ruling_exemptions_path=_NO_RULING_EXEMPTIONS)
    assert "3 ruling row(s) read" in out, out
    assert "REPEATED re-rulings" in out, out
    assert "1 unbridgeable" in out, out

def test_the_widened_head_ADMITS_the_spellings_the_board_actually_uses() -> None:
    """#245 done-when 1, the widening arm: `## Amendment` IS a ruling head.

    `#133` is the measured case — its two `## Amendment` comments ARE its ruling, while the
    strict predicate returned None for them, so the issue read as unruled from the BOARD as
    well as from the ledger. `#148` is the same spelling with a `ruling` row already stamped.
    Both arms are driven here: the new spelling is admitted, and the two original forms are
    NOT displaced by the widening.
    """
    for body in ("## RULED — shape (2), settled.\n",
                 "## RULING — the clause reads as follows.\n",
                 "## Amendment — done-when 3 resolved, and it is not conditional.\n"):
        issue = _issue_with_comments(133, "OPEN", body)
        assert RUNNER.ruling_comment(issue) is not None, f"not admitted: {body!r}"
        assert RUNNER.unmatched_heading_comments(issue) == [], body

def test_the_ruling_predicate_is_BOUNDARY_checked() -> None:
    """A prefix match admits an EXTENSION unless the boundary is checked.

    `## RULINGS — the ledger` starts with `## RULING`, so a bare `str.startswith` would read
    a DIFFERENT heading as this one — the digit-extension class this factory has filed
    repeatedly. Measured over the live board before the check was written: 0 headings extend
    an accepted form, so this arm exists so the population cannot move tomorrow, not because
    it moves today. Both sides are asserted, so the check cannot be satisfied by a predicate
    that refuses everything.
    """
    for head in ("## RULINGS — the ledger", "## RULEDLY", "## Amendment2"):
        assert not RUNNER._accepted_heading(head), head
    for head in ("## RULED", "## RULED — shape (2)", "## RULING", "## Amendment",
                 "## Amendment — x", "## RULED: a colon is a boundary"):
        assert RUNNER._accepted_heading(head), head

def test_the_leg_PRINTS_a_head_it_did_NOT_match() -> None:
    """#245 done-when 2: the clause that keeps the widening from reproducing the defect.

    A NOVEL head — one no one has written before — must surface as a printed line with its
    issue number on the run that first meets it. Without this clause the next spelling is
    simply not examined, which is indistinguishable from absent. Both halves are driven: the
    line, and the count beside the verdict.
    """
    issues = [
        _issue_with_comments(7, "OPEN", "## DISPOSITION — a spelling nobody has used yet.\n"),
        _issue_with_comments(8, "OPEN", "## RULED — an ordinary ruling.\n"),
    ]
    # `ruling` #7 is added for #332: #7 carries no ACCEPTED head, so it is the probe's own
    # point that it reads unruled — but the ROUND's population is read from the LEDGER, and
    # a row exists for it, so the patrol's board-unruled leg stays quiet here.
    rows = _swept(("intake", "#7", 1), ("ruling", "#7", 4), ("intake", "#8", 2),
                 ("ruling", "#8", 3, f"probe comment={_comment_numeric(8)}"))
    leg = RUNNER.board_ruling_leg(issues, rows, read_at="probe",
                                  predicate=RUNNER.load_predicate(),
                                  scope=RUNNER.UNBOUNDED_SCOPE,
                                  exemptions_path=_NO_RULING_EXEMPTIONS)
    cov = leg["coverage"]
    assert cov["unmatched_heads"] == [{"issue": 7, "head": "## DISPOSITION — a spelling nobody has used yet."}], cov["unmatched_heads"]
    assert cov["unmatched_heads_examined"] == 1, cov
    assert cov["canonical_heading"] == "## RULED", cov

    rc, out, _ = _run(issues, rows)
    assert "## DISPOSITION — a spelling nobody has used yet." in out, out
    assert "#7" in out, out
    assert "heading comments the ruling predicate did NOT match: 1 over 1 issue(s)" in out, out
    assert "the convention names '## RULED'" in out, out
    assert rc == 0, out

def test_the_counter_counts_ISSUES_not_COMMENTS() -> None:
    """#274: the counter's NAME and its PREDICATE are one fact, so they are gated together.

    The defect this pins was measured on the live board: three `## RULED` comments posted in
    ONE turn (#75/#227/#263) moved the counter from 79 to 81, because the leg increments once
    per ISSUE carrying an accepted heading and #75 already carried one. A reader comparing two
    runs expected +3 and went hunting for an unplaced comment that does not exist.

    The name moved to match the predicate (`ruling_comments_examined` -> `rulings_issued`) and
    the predicate STAYED per-issue. This probe is what keeps it that way: two ruling comments
    on ONE issue, and a second issue with none, must read as ONE. If the increment ever moves
    to per-comment the count reads 2 and this reds — which is the only thing that stops a
    renamed counter from drifting back under a name that no longer describes it.
    """
    issues = [
        # ONE issue, TWO ruling comments — the measured shape.
        _issue_with_comments(75, "OPEN", "## RULED — the ruling.\n", "## RULED — amended.\n"),
        _issue_with_comments(76, "OPEN", "no ruling here, only prose.\n"),
    ]
    # `ruling` #76 is added for #332: #76 carries no ruling COMMENT (which is this probe's
    # point), but the round's population is read from the LEDGER, so a row keeps the
    # board-unruled leg quiet over a fixture that is about the ruling leg.
    # #75 carries TWO ruling comments and the leg judges the LATEST act (#511), so the row
    # must name the SECOND one; #76 carries no accepted head at all, so no pairing is owed.
    rows = _swept(("intake", "#75", 1),
                 ("ruling", "#75", 2, f"probe comment={_comment_numeric(75, 2)}"),
                 ("intake", "#76", 3), ("ruling", "#76", 4))
    leg = RUNNER.board_ruling_leg(issues, rows, read_at="probe", predicate=RUNNER.load_predicate(),
                                  scope=RUNNER.UNBOUNDED_SCOPE,
                                  exemptions_path=_NO_RULING_EXEMPTIONS)
    assert leg["coverage"]["rulings_issued"] == 1, (
        f"two ruling comments on ONE issue are ONE ruling: {leg['coverage']!r}"
    )
    assert leg["problems"] == [], leg["problems"]

    rc, out, _ = _run(issues, rows)
    section = out.split("LEG board-ruling")[1].split("LEG ")[0]
    assert "1 examined over 2 issue(s) read" in section, (
        f"the printed count and the read size must both travel: {section!r}"
    )
    assert rc == 0, out

def test_the_widening_MOVES_an_amendment_only_issue_INTO_the_population() -> None:
    """The NON-VACUITY control for the widening, driven through the REAL leg.

    An issue whose ONLY head is `## Amendment` and which has no `ruling` row was invisible
    before the widening: it was not counted as examined and not reported. The same fixture
    is driven through the accepted set as it stands and against the NARROWED tuple, so the
    difference is attributable to the widening and not to the fixture — the shape #243's
    bridge control used.
    """
    pred = RUNNER.load_predicate()
    issues = [_issue_with_comments(133, "OPEN", "## Amendment — the item is ruled here.\n")]
    rows = _rows(("intake", "#133", 846), ("dispatch", "#133", 847))

    widened = RUNNER.board_ruling_leg(issues, rows, read_at="probe", predicate=pred,
                                      scope=RUNNER.UNBOUNDED_SCOPE,
                                      exemptions_path=_NO_RULING_EXEMPTIONS)
    assert widened["coverage"]["rulings_issued"] == 1, widened["coverage"]
    assert len(widened["problems"]) == 1, widened["problems"]
    assert "#133 carries a ruling comment" in widened["problems"][0], widened["problems"]

    saved = RUNNER.RULING_HEADINGS
    RUNNER.RULING_HEADINGS = ("## RULED", "## RULING")
    try:
        narrowed = RUNNER.board_ruling_leg(issues, rows, read_at="probe", predicate=pred,
                                       scope=RUNNER.UNBOUNDED_SCOPE,
                                       exemptions_path=_NO_RULING_EXEMPTIONS)
    finally:
        RUNNER.RULING_HEADINGS = saved
    assert narrowed["coverage"]["rulings_issued"] == 0, narrowed["coverage"]
    assert narrowed["problems"] == [], narrowed["problems"]

def test_the_ruling_bound_EXCUSES_a_pre_boundary_comment_and_JUDGES_a_post_boundary_one() -> None:
    """Acceptance (d), as a NON-VACUITY pair: one fixture, two instants, two verdicts.

    The leg's red must mean "a lane diverged since the mechanism", never "history exists".
    The same issue and the same ledger are driven twice with the ONLY difference the ruling
    comment's own `createdAt` — so the verdict is attributable to the bound and not to the
    fixture, which is the shape #243's bridge control used.
    """
    rows = _rows(("intake", "#1", 1))
    scope = _scope_at(_RULING_BOUND)

    pre = RUNNER.board_ruling_leg([_ruling_issue(1, _RULING_PRE)], rows, read_at="probe",
                                  scope=scope, exemptions_path=_NO_RULING_EXEMPTIONS)
    assert pre["problems"] == [], pre["problems"]
    # COUNTED, never dropped: a pre-boundary instance that vanished from the population
    # would be indistinguishable from one that was never on the board (#242).
    assert pre["coverage"]["rulings_issued"] == 1, pre["coverage"]
    assert pre["coverage"]["pre_boundary_rulings"] == 1, pre["coverage"]
    assert pre["coverage"]["bound"] == _RULING_BOUND, pre["coverage"]
    assert len(pre["excused"]) == 1, pre["excused"]
    assert "PREDATES the declared bound" in pre["excused"][0], pre["excused"]
    assert "NEVER backfilled" in pre["excused"][0], pre["excused"]

    post = RUNNER.board_ruling_leg([_ruling_issue(1, _RULING_POST)], rows, read_at="probe",
                                   scope=scope, exemptions_path=_NO_RULING_EXEMPTIONS)
    assert len(post["problems"]) == 1, post["problems"]
    assert "#1 carries a ruling comment" in post["problems"][0], post["problems"]
    assert "a lane that diverged from it" in post["problems"][0], post["problems"]
    assert post["coverage"]["pre_boundary_rulings"] == 0, post["coverage"]

def test_the_ruling_bound_reads_the_LATEST_accepted_comment_not_the_first() -> None:
    """The false-clean control for the instance's instant.

    An issue ruled BEFORE the mechanism and amended AFTER it carries two ruling acts. Dating
    the instance by the FIRST comment would excuse the post-mechanism amendment — a false
    clean, which is the worse half of the #248 class. The fixture is exactly that issue, and
    the assertion is that it is JUDGED.
    """
    issue = _issue(7, "OPEN")
    # `url` is NOT decoration: the pairing surface compares the NUMERIC id that only the URL
    # carries (#511). A fixture without it drives the fail-closed arm while reading as if it
    # drove the paired one, so this control is re-armed with the helper that supplies it.
    issue["comments"] = [
        {"id": "IC_pre", "body": "## RULED — the original.\n",
         "author": {"login": "leshchenko1979"}, "createdAt": _RULING_PRE,
         "url": _comment_url(7, 1)},
        {"id": "IC_post", "body": "## RULED — amended.\n",
         "author": {"login": "leshchenko1979"}, "createdAt": _RULING_POST,
         "url": _comment_url(7, 2)},
    ]
    leg = RUNNER.board_ruling_leg([issue], _rows(("intake", "#7", 1)), read_at="probe",
                                  scope=_scope_at(_RULING_BOUND),
                                  exemptions_path=_NO_RULING_EXEMPTIONS)
    assert len(leg["problems"]) == 1, leg["problems"]
    # The INSTANT is the amendment's and the COMMENT named is the amendment's. Reading the
    # first comment would print the pre-boundary instant, excuse the instance, and report a
    # clean leg — so the negative assertion on `_RULING_PRE` is the control, not decoration.
    assert _RULING_POST in leg["problems"][0], leg["problems"]
    assert f"comment {_comment_numeric(7, 2)}" in leg["problems"][0], leg["problems"]
    assert _RULING_PRE not in leg["problems"][0], leg["problems"]
    assert leg["excused"] == [], leg["excused"]
    assert leg["coverage"]["pre_boundary_rulings"] == 0, leg["coverage"]

def test_the_ruling_leg_REFUSES_rather_than_judging_UNBOUNDED() -> None:
    """An unreadable bound is neither a skip nor a pass — and it is not the old behaviour.

    A REFUSAL must judge NOTHING: judging every instance against no bound is exactly the
    permanent red #334 removes, and silently returning to it is the failure mode this arm
    pins. The population is still counted, so a refused run cannot read as an empty board.
    """
    refusal = "`ruling_writer_landed` is UNDECLARED — REFUSED: probe"
    leg = RUNNER.board_ruling_leg([_ruling_issue(1, _RULING_POST)], _rows(("intake", "#1", 1)),
                                  read_at="probe", scope=(None, "", refusal),
                                  exemptions_path=_NO_RULING_EXEMPTIONS)
    assert leg["problems"] == [refusal], leg["problems"]
    assert leg["coverage"]["rulings_issued"] == 1, leg["coverage"]
    assert leg["coverage"]["bound_refusal"] == refusal, leg["coverage"]
    assert leg["excused"] == [], leg["excused"]

    rc, out, _ = _run([_ruling_issue(1, _RULING_POST, state="CLOSED")],
                      _rows(("intake", "#1", 1), ("close", "#1", 2)),
                      ruling_scope=(None, "", refusal))
    assert rc == 1, (rc, out[-2000:])
    assert "NOT JUDGED, the bound is refused" in out, out[-3000:]

def test_the_ruling_bound_is_FACTORY_DATA_read_through_the_ONE_reader() -> None:
    """The instant is declared factory data, never a second constant in a shipped file.

    The runner is paired byte-identically with its TEMPLATE copy, so a date written inside it
    would judge a member tree against this factory's history — the same reason the
    boundary-reading gates declare theirs. The grep is the whole probe: no instant of the
    bound may appear in the runner, and the key must resolve through `tests/ledger_boundary.py`.
    """
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "2026-10-02T18:07:38" not in source, (
        "the bound instant is hardcoded in the leg; it belongs in docs/ledger-invariants.json")
    assert RUNNER.RULING_BOUNDARY_KEY == "ruling_writer_landed", source
    reader = RUNNER.load_module("ledger_boundary", RUNNER.LEDGER_BOUNDARY)
    try:
        _instant, text = reader.declared_boundary(REPO, RUNNER.RULING_BOUNDARY_KEY)
    except reader.SkipGate as exc:
        _declared_skip("the bound is factory data", str(exc))
        return
    except reader.GateError as exc:
        raise AssertionError(f"the boundary declaration is unreadable: {exc}") from exc
    assert text == _RULING_BOUND, f"the probes and the live declaration disagree: {text}"

def test_the_leg_PRINTS_the_bound_and_the_pre_boundary_count() -> None:
    """A bound that never reaches the report is a bound nobody can audit.

    Driven through `main()`, because the print is the property — an exclusion that is not
    printed cannot be told from a miss.
    """
    issues = [_ruling_issue(1, _RULING_PRE, state="CLOSED")]
    rows = _rows(("intake", "#1", 1), ("close", "#1", 2))
    rc, out, err = _run(issues, rows, ruling_scope=_scope_at(_RULING_BOUND))
    section = out.split("LEG board-ruling")[1].split("LEG ")[0]
    assert rc == 0, (rc, section, err)
    assert f"bound: {_RULING_BOUND} for `ruling_writer_landed`" in section, section
    assert "1 ruling comment(s) earlier than it are NOT JUDGED" in section, section
    assert "excused: 1" in section, section
    assert "PREDATES the declared bound" in section, section

def test_an_exemption_EXCUSES_a_post_boundary_instance_and_is_PRINTED() -> None:
    """The one lawful exit, and it is a VISIBLE debt rather than forgiveness.

    The instance is post-boundary, so the bound cannot excuse it; the exemption table can,
    and the run must say so on the same line it would otherwise carry the problem.
    """
    with tempfile.TemporaryDirectory() as tmp:
        issues = [_ruling_issue(282, _RULING_POST, comment_id="IC_probe_282",
                                state="CLOSED")]
        rows = _rows(("intake", "#282", 1), ("close", "#282", 2))
        path = _exemptions_file(tmp, _exemption("IC_probe_282", 282))

        leg = RUNNER.board_ruling_leg(issues, rows, read_at="probe",
                                      scope=_scope_at(_RULING_BOUND), exemptions_path=path)
        assert leg["problems"] == [], leg["problems"]
        assert leg["coverage"]["exemptions_declared"] == 1, leg["coverage"]
        assert leg["coverage"]["exemptions_matched"] == ["IC_probe_282"], leg["coverage"]
        assert len(leg["excused"]) == 1 and "EXEMPTED" in leg["excused"][0], leg["excused"]
        assert "NO BACKFILL bars the only repair" in leg["excused"][0], leg["excused"]

        rc, out, _ = _run(issues, rows, ruling_scope=_scope_at(_RULING_BOUND),
                          ruling_exemptions_path=path)
        section = out.split("LEG board-ruling")[1].split("LEG ")[0]
        assert rc == 0, (rc, section)
        assert "exemptions (ruling-board-exemptions.json): 1 declared, 1 matched" in section, section
        assert "EXEMPTED" in section, section

def test_an_exemption_is_KEYED_on_the_comment_so_a_new_ruling_cannot_inherit_it() -> None:
    """The key's whole point, as a NON-VACUITY control.

    A ruling is a COMMENT. Exempting by issue number would let a FUTURE ruling on the same
    issue inherit a grant made for a different act — the exact defect class this repo keeps
    filing. Here the table names the comment, and the board carries a DIFFERENT one on the
    same issue: the instance is judged, and the unmatched entry is reported as stale debt.
    """
    with tempfile.TemporaryDirectory() as tmp:
        issues = [_ruling_issue(282, _RULING_POST, comment_id="IC_probe_NEW")]
        rows = _rows(("intake", "#282", 1))
        path = _exemptions_file(tmp, _exemption("IC_probe_OLD", 282))

        leg = RUNNER.board_ruling_leg(issues, rows, read_at="probe",
                                      scope=_scope_at(_RULING_BOUND), exemptions_path=path)
        assert len(leg["problems"]) == 2, leg["problems"]
        assert any("#282 carries a ruling comment" in p for p in leg["problems"]), leg["problems"]
        assert any("matches NO in-scope unruled ruling comment" in p for p in leg["problems"]), (
            leg["problems"])
        assert leg["excused"] == [], leg["excused"]

def test_a_MALFORMED_exemption_is_a_PROBLEM_never_a_silent_pass() -> None:
    """Every malformed shape is reported: an entry that quietly fails to load is
    indistinguishable from no exemptions, which is the vacuous-pass shape this leg exists
    to catch."""
    cases = {
        "no comment key": {"issue": 1, "granted": "2026-10-05",
                           "domain": RUNNER.RULING_EXEMPT_DOMAIN[0], "reason": "r", "proof": "p"},
        "no reason": {"comment": "IC_x", "issue": 1, "granted": "2026-10-05",
                      "domain": RUNNER.RULING_EXEMPT_DOMAIN[0], "proof": "p"},
        "no proof": {"comment": "IC_x", "issue": 1, "granted": "2026-10-05",
                     "domain": RUNNER.RULING_EXEMPT_DOMAIN[0], "reason": "r"},
        "no issue": {"comment": "IC_x", "granted": "2026-10-05",
                     "domain": RUNNER.RULING_EXEMPT_DOMAIN[0], "reason": "r", "proof": "p"},
        "foreign domain": {"comment": "IC_x", "issue": 1, "granted": "2026-10-05",
                           "domain": "something else", "reason": "r", "proof": "p"},
    }
    for label, entry in cases.items():
        with tempfile.TemporaryDirectory() as tmp:
            path = _exemptions_file(tmp, entry)
            leg = RUNNER.board_ruling_leg([_ruling_issue(1, _RULING_POST)],
                                          _rows(("intake", "#1", 1)), read_at="probe",
                                          scope=_scope_at(_RULING_BOUND), exemptions_path=path)
            assert leg["coverage"]["exemptions_declared"] == 0, (label, leg["coverage"])
            assert leg["problems"], f"{label}: a malformed entry must be a problem"
            assert any("ruling-board-exemptions.json" in p for p in leg["problems"]), (
                label, leg["problems"])
            assert leg["excused"] == [], (label, leg["excused"])

    with tempfile.TemporaryDirectory() as tmp:
        broken = Path(tmp) / "ruling-board-exemptions.json"
        broken.write_text("not json {{{", encoding="utf-8")
        leg = RUNNER.board_ruling_leg([_ruling_issue(1, _RULING_POST)],
                                      _rows(("intake", "#1", 1)), read_at="probe",
                                      scope=_scope_at(_RULING_BOUND), exemptions_path=broken)
        assert any("unreadable or malformed JSON" in p for p in leg["problems"]), leg["problems"]

def test_an_absent_exemption_table_means_NO_exemptions_and_is_not_a_problem() -> None:
    """A new factory ships no table at all, and that is a legitimate state, not a defect.

    The counterpart to the malformed arm: absent means empty, and the leg still judges the
    population. Without this arm a leg that reported a missing file would red every factory
    that has never needed one.
    """
    leg = RUNNER.board_ruling_leg([_ruling_issue(1, _RULING_POST)], _rows(("intake", "#1", 1)),
                                  read_at="probe", scope=_scope_at(_RULING_BOUND),
                                  exemptions_path=_NO_RULING_EXEMPTIONS)
    assert leg["coverage"]["exemptions_declared"] == 0, leg["coverage"]
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "#1 carries a ruling comment" in leg["problems"][0], leg["problems"]

def test_the_undispatched_ruling_leg_BITES_and_discriminates_on_every_bucket() -> None:
    """#519 acceptance (1): a ruled, unstarted, un-dispatched item is NAMED, and every
    neighbour that looks like it stays quiet.

    The neighbours are the live false positives: an item with a dispatch row naming it in
    its SUBJECT is dispatched (the ruling's own #433 arm); an item resolved by a DECLARED
    batch act was dispatched by a batch and owes no per-item row (NO BACKFILL, n=1596); a
    CLAIMED item is started; a CLOSED item is done; an item with no `ruling` row belongs to
    `board_unruled_leg`.

    #933 is a MENTION and it is OWED (#556, ruling n=4194): a dispatch row's BODY carrying
    the token is not a dispatch, so it clears nothing. It is counted as its own class and
    printed beside the owed entry -- never as an excuse.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [
        _issue(931, "OPEN"),    # ruled, unclaimed, unclosed, un-dispatched -> OWED
        _issue(932, "OPEN"),    # ruled, and a dispatch row NAMES it in its subject
        _issue(933, "OPEN"),    # ruled, named only in a dispatch row's BODY -> mention
        _issue(934, "OPEN"),    # ruled, resolved by a DECLARED batch act
        _issue(935, "OPEN"),    # ruled, but CLAIMED -> started
        _issue(936, "CLOSED"),  # ruled, but CLOSED -> done
        _issue(937, "OPEN"),    # OPEN and un-dispatched, but carries NO ruling row
    ]
    rows = [
        _stall_row(31, "ruling", "#931", 2, now=now),
        _stall_row(32, "ruling", "#932", 2, now=now),
        _stall_row(33, "dispatch", "#932", 1.9, now=now),
        _stall_row(34, "ruling", "#933", 2, now=now),
        _stall_row(35, "dispatch", "consolidated-brief", 1.9, now=now,
                   detail="covering #933 and two other units"),
        _stall_row(36, "ruling", "#934", 2, now=now),
        _stall_row(37, "ruling", "#935", 2, now=now),
        _stall_row(38, "claim", "#935", 1.9, now=now),
        _stall_row(39, "ruling", "#936", 2, now=now),
        _stall_row(40, "close", "#936", 1.9, now=now),
    ]
    batches = {"probe-batch-2026-10-21": {
        "row": 36, "units": [934],
        "recorded_at": "2026-10-21T00:00:00Z",
        "basis": "probe: one run receipt fanned the round out, so no per-item row is owed",
    }}

    leg = RUNNER.undispatched_ruling_leg(issues, rows, read_at=read_at, batches=batches, standing={})
    named = "\n".join(leg["problems"])
    assert "#931" in named, f"the ruled-but-undispatched item must be NAMED\n{named}"
    for quiet in ("#932", "#934", "#935", "#936", "#937"):
        assert quiet not in named, (
            f"{quiet} must NOT be reported: a subject match IS a dispatch, a declared batch "
            f"resolves, a claimed item is started, a closed item is done, and an item with "
            f"no ruling row belongs to board-unruled\n{named}"
        )
    assert "#933 is OPEN" in named, (
        f"#933 is named only in a dispatch row's BODY, which is a MENTION and NOT a "
        f"dispatch: it clears nothing, so the item is OWED (#556)\n{named}"
    )
    cov = leg["coverage"]
    assert cov["items_owed_dispatch"] == 2, cov
    # THREE, not five: a subject-dispatched item (#932) is out of the population BY
    # CONSTRUCTION rather than by a later bucket, and a claimed (#935) or closed (#936) one
    # is out the same way. The population is "ruled and not started", so the buckets that
    # follow can only ever partition what this count already excluded those from.
    assert cov["population_undispatched"] == 3, cov
    assert cov["items_resolved_by_batch"] == 1, cov
    assert cov["items_named_in_body_only"] == 1, cov

def test_a_prose_MENTION_does_not_EXCUSE_a_debt_and_prints_WHAT_it_matched() -> None:
    """#556 acceptance (1)-(3) / ruling n=4194: a bare-digit coincidence is OWED, and the
    coincidence is PRINTED with its matched text and character offset.

    THE POSITIVE CONTROL IS THIS TREE'S OWN SEVEN (#556's dispatch). Each fixture row below
    reproduces one of the coincidences the live leg was excusing -- a `file:line`, a
    `max 553.73 h`, an `n=554`, a `:556` -- and a run reporting `owed` empty over this
    fixture is RED, because these seven provably carry no dispatch row. Before the fix the
    leg reported `items_owed_dispatch: 0` over exactly this population while calling itself
    ASSERTED: the #271 shape, a zero that cannot be told from a clean read.

    #534 NARROWED THE MENTION CLASS, AND THIS PROBE IS WHERE THAT SHOWS. Three of the seven
    are a `file:line`, an `n=<row>` and a bare `:<line>`: a row number and a source line are
    not issue references, so those rows mention nothing at all now. All seven remain OWED --
    the debt never depended on the mention -- but the MENTION count drops from seven to four,
    and a probe still expecting seven would be asserting the defect it was written to catch.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    numbers = sorted(_LIVE_MENTION_COINCIDENCES)
    refused = sorted(_LIVE_REFUSED_COINCIDENCES)
    all_numbers = sorted(_ALL_LIVE_COINCIDENCES)
    issues = [_issue(n, "OPEN") for n in all_numbers]
    issues.append(_issue(557, "OPEN"))   # dispatched in its SUBJECT -> out of the population
    issues.append(_issue(558, "OPEN"))   # resolved by a declared batch -> excused
    rows = []
    n = 600
    for number in all_numbers:
        subject, detail = _ALL_LIVE_COINCIDENCES[number]
        rows.append(_stall_row(n, "ruling", f"#{number}", 2, now=now))
        rows.append(_stall_row(n + 1, "dispatch", subject, 1.9, now=now, detail=detail))
        n += 2
    rows.append(_stall_row(n, "ruling", "#557", 2, now=now))
    rows.append(_stall_row(n + 1, "dispatch", "#557", 1.9, now=now))
    rows.append(_stall_row(n + 2, "ruling", "#558", 2, now=now))
    batches = {"probe-batch-2026-10-24": {
        "row": n + 3, "units": [558], "recorded_at": "2026-10-24T00:00:00Z",
        "basis": "probe: a batch act dispatched this unit, so no per-item row is owed",
    }}

    leg = RUNNER.undispatched_ruling_leg(issues, rows, read_at=read_at, batches=batches, standing={})
    cov = leg["coverage"]
    assert cov["items_owed_dispatch"] == len(all_numbers), (
        f"all seven are OWED: a mention clears nothing, and a REFUSED token was never a "
        f"mention to begin with\n{cov}"
    )
    assert cov["owed"] == all_numbers, cov
    assert cov["items_named_in_body_only"] == len(numbers), (
        f"FOUR of the seven carry an ISSUE reference; the other three carry a row number, a "
        f"source line and a bare line number, which #534 refuses\n{cov}"
    )
    assert "#557" not in cov["owed"], "a subject match IS a dispatch, not a debt"
    assert "#558" not in cov["owed"], "a declared batch act resolves, and clears the debt"
    assert cov["items_resolved_by_batch"] == 1, cov

    named = "\n".join(leg["problems"])
    for number in numbers:
        assert f"#{number} is OPEN" in named, f"#{number} must be OWED\n{named}"

    # WHAT IT MATCHED, VERBATIM, AND WHERE (#556 step 3). The offset is recomputed here from
    # the fixture's own bytes, so an offset the leg invented cannot pass.
    for number in numbers:
        _subject, detail = _LIVE_MENTION_COINCIDENCES[number]
        mention = next(e["mention"] for e in cov["owed_detail"] if e["issue"] == number)
        token = RUNNER.subject_token_re(f"#{number}").search(detail)
        assert token is not None, f"the fixture itself must carry the token for #{number}"
        assert mention["matched_text"] == token.group(0), mention
        assert mention["char_offset"] == token.start(), (
            f"#{number}'s offset must point at the occurrence that MATCHED, not at another "
            f"one in the same row\n{mention}"
        )
        assert mention["context"] and mention["context"] in named, (
            f"#{number}'s context must be PRINTED, so a coincidence is visible without "
            f"grepping the row\n{named}"
        )

    assert "max 553.73 h" in named, (
        f"the ONE coincidence still admitted -- a DECIMAL boundary, which #534 does not "
        f"touch -- must stay visible, or narrowing the class would have hidden it\n{named}"
    )
    # ... AND THE THREE REFUSED FORMS ARE NOT MENTIONS, WHILE STILL BEING OWED (#534). A
    # refusal that quietly dropped them from the debt would be the false-CLEAN twin.
    for number in refused:
        _subject, _detail = _LIVE_REFUSED_COINCIDENCES[number]
        assert f"#{number} is OPEN" in named, (
            f"#{number} must still be OWED: its dispatch row names a row number or a source "
            f"line, which is neither a dispatch nor a mention\n{named}"
        )
        assert number in cov["owed"], cov
        assert not any(e.get("mention") for e in cov["owed_detail"] if e["issue"] == number), (
            f"#{number} must carry NO mention: the token in its dispatch row is a row number "
            f"or a source line, not an issue reference\n{cov}"
        )

    # ... and the discriminating control: the SAME seven, with dispatch rows whose details do
    # NOT carry the token. The debt is identical, because a mention never decided it in
    # either direction -- before the fix it decided it, which was the defect; after the fix
    # it may not decide it the other way either.
    quiet_rows = []
    n = 700
    for number in all_numbers:
        quiet_rows.append(_stall_row(n, "ruling", f"#{number}", 2, now=now))
        quiet_rows.append(_stall_row(n + 1, "dispatch", "consolidated-brief", 1.9, now=now,
                                     detail="covering other units entirely"))
        n += 2
    quiet = RUNNER.undispatched_ruling_leg(
        [_issue(x, "OPEN") for x in all_numbers], quiet_rows, read_at=read_at, batches={}, standing={})
    assert quiet["coverage"]["owed"] == all_numbers, (
        f"the debt must not depend on the mention: the same seven are owed with no mention "
        f"present at all\n{quiet['coverage']}"
    )
    assert quiet["coverage"]["items_named_in_body_only"] == 0, quiet["coverage"]

    # AND THE RENDERED REPORT SAYS IT (#556 step 2): the coverage dict is not what a lane
    # reads -- the patrol's own print path is. A leg whose numbers are right and whose
    # output still reads `0 owed` would have fixed nothing a reader can see, so the print
    # block is asserted through the REAL `main()` rather than inspected.
    _rc, out, _err = _run(issues, rows, dispatch_batches=batches)
    assert "OWED #549 — MENTION ONLY: '#549' at offset" in out, (
        f"the owed line must carry the mention BESIDE it, with its offset\n{out}"
    )
    assert "max 553.73 h" in out, out
    for number in refused:
        assert f"OWED #{number} — MENTION ONLY" not in out, (
            f"#{number} must NOT render as a mention: its row carries a row number or a "
            f"source line (#534)\n{out}"
        )
        assert f"OWED #{number}" in [ln.strip() for ln in out.splitlines()], (
            f"#{number} must still render as plainly OWED\n{out}"
        )
    assert "it EXCUSES NOTHING: every one of them is OWED above" in out, (
        f"the mention class must declare that it excuses nothing\n{out}"
    )

def test_a_ROW_NUMBER_and_a_FILE_LINE_are_NOT_issue_references() -> None:
    """#534, ruled at ledger n=4183: the mention test admitted a row number and a file offset.

    THE DEFECT. `subject_token_re("#534")` compiles `#?534`, because a delivery is free prose
    and names its routed unit however its sender wrote it -- so THE HASH IS OPTIONAL. That
    generosity let two artifacts that are not issues at all satisfy the token: `n=534` (a
    ledger ROW number) and `src/cron/scheduler.rs:534` (a source LINE). Measured by Triage on
    the live tree at 2026-10-26T06:05Z, tree 87ff9a38: of the seven items the leg had been
    excusing, `n=554`, `docs/instruments/kit.md:548` and `_LOG_ENABLED = False at :556` were
    three such coincidences -- a unit's number appearing in a row reference or a file offset.

    THE FIX IS A REFUSAL AT THE CALL SITE, NOT A NARROWER TOKEN. The boundary discipline
    (#49, #425) is ONE home shared by the match, the locator and the header/body split, so
    widening or narrowing the pattern globally would move all three at once; what is refused
    is a MATCH WHOSE PREFIX SAYS IT IS A NUMBER. The unit stays OWED either way -- a mention
    never cleared a debt in either direction (#556 step 1) -- so the harm repaired here is a
    FALSE CLASSIFICATION, not a false clean. That is why the arms below assert the OWED set
    AND the mention count: a fix that only moved one of them would look green.

    THE POSITIVE CONTROLS ARE THE LAST TWO ARMS. A refusal that also killed a genuine `#534`
    reference would be the same defect wearing the opposite sign, and a token narrowed to
    reject the DIGITS would pass every negative arm while destroying the mention class.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # ---- arm 0: the predicate on the five shapes Triage measured, plus its own pair ----
    measured = [
        ("dispatch row n=534 carrying the ruling", False),
        ("src/cron/scheduler.rs:534 writes both", False),
        ("see #534 for the defect", True),
        ("#534's premise is false", True),
        ("n=1534 and 5340", False),
    ]
    for text, want in measured:
        got = RUNNER.mention_occurrence(text, 534) is not None
        assert got is want, (
            f"mention_occurrence({text!r}, 534) must be {want}, got {got}: a row number and "
            f"a source line are not issue references, and the boundary discipline that keeps "
            f"`1534`/`5340` out must not be the thing doing the refusing"
        )
    # THE PREFIX IS WHAT REFUSES, NOT THE DIGITS: drop the prefix and the SAME digits are a
    # reference. This pair is the discriminator inside the predicate, so a token narrowed to
    # reject the digits cannot pass it.
    assert RUNNER.mention_occurrence("row n=534", 534) is None, (
        "a `row n=` prefix is a ledger ROW reference"
    )
    assert RUNNER.mention_occurrence("row 534", 534) is not None, (
        "with no prefix the same digits are a bare reference, which the token has always "
        "accepted (#49): the refusal is about the prefix, never the number"
    )

    # ---- arms 1-4: the LEG, because the predicate is not what a lane reads -----------
    issues = [_issue(n, "OPEN") for n in (534, 535, 536, 537)]
    rows = [
        _stall_row(801, "ruling", "#534", 2, now=now),
        # a LEDGER ROW NUMBER -> not an issue reference
        _stall_row(802, "dispatch", "round-receipt-2026-10-26", 1.9, now=now,
                   detail="the round is recorded at dispatch row n=534 in the store"),
        _stall_row(803, "ruling", "#535", 2, now=now),
        # a SOURCE LINE -> not an issue reference
        _stall_row(804, "dispatch", "scheduler-audit-2026-10-26", 1.9, now=now,
                   detail="src/cron/scheduler.rs:535 writes both arms of the branch"),
        _stall_row(805, "ruling", "#536", 2, now=now),
        # a GENUINE issue reference in the body -> a MENTION, and still OWED
        _stall_row(806, "dispatch", "consolidated-brief", 1.9, now=now,
                   detail="covering #536 and two other units"),
        _stall_row(807, "ruling", "#537", 2, now=now),
        # ... and a SUBJECT that names it -> ROUTED, out of the population entirely
        _stall_row(808, "dispatch", "#537", 1.9, now=now),
    ]
    leg = RUNNER.undispatched_ruling_leg(issues, rows, read_at=read_at, batches={}, standing={})
    cov = leg["coverage"]
    named = "\n".join(leg["problems"])

    # ARMS 1 AND 2: both refused forms leave the unit OWED, and neither is a mention.
    for number in (534, 535):
        assert f"#{number} is OPEN" in named, (
            f"#{number} must be OWED: its dispatch row names a row number or a source line, "
            f"which is neither a dispatch nor a mention\n{named}"
        )
        assert number in cov["owed"], cov
        assert not any(e.get("mention") for e in cov["owed_detail"] if e["issue"] == number), (
            f"#{number} must carry NO mention entry\n{cov}"
        )
    assert cov["items_named_in_body_only"] == 1, (
        f"ONLY #536 is a mention: #534 and #535 carry a row number and a source line, which "
        f"#534 refuses, so counting them would be asserting the defect\n{cov}"
    )
    # ARM 3: a genuine reference IS a mention -- and a mention excuses nothing (#556 step 1).
    assert 536 in cov["owed"], cov
    mention = next(e["mention"] for e in cov["owed_detail"] if e["issue"] == 536)
    assert mention["matched_text"] == "#536", mention
    # ARM 4: the SUBJECT match ROUTES, so the unit is not in the population at all.
    assert 537 not in cov["owed"], cov
    assert 537 not in [e["issue"] for e in cov["owed_detail"]], cov

    # ---- and the RENDER: a refused token must never print as a mention ---------------
    _rc, out, _err = _run(issues, rows, dispatch_batches={})
    assert "OWED #536 — MENTION ONLY: '#536' at offset" in out, (
        f"the genuine reference must still print with its offset\n{out}"
    )
    for number in (534, 535):
        assert f"OWED #{number} — MENTION ONLY" not in out, (
            f"#{number} must NOT render as a mention\n{out}"
        )
        assert f"OWED #{number}" in [ln.strip() for ln in out.splitlines()], (
            f"#{number} must still render as plainly OWED, or the refusal hid a debt\n{out}"
        )
    assert "named only in a dispatch row's BODY (#467): 1 item(s)" in out, (
        f"the count must print the population it was drawn from\n{out}"
    )

def main() -> int:
    checks = [value for name, value in sorted(globals().items())
              if name.startswith("test_") and callable(value)]
    failures: list[str] = []
    for check in checks:
        try:
            check()
        except pytest.skip.Exception:
            continue
        except AssertionError as exc:
            failures.append(f"{check.__name__}: {exc}")
            print(f"  FAIL  {check.__name__} — {exc}")
        else:
            print(f"  PASS  {check.__name__}")
    print()
    if failures:
        print(f"patrol-runner gate FAILED: {len(failures)} check(s)")
        return 1
    ran = len(checks) - len(_SKIPS)
    skipped = f", {len(_SKIPS)} SKIPPED (nothing to judge)" if _SKIPS else ""
    print(f"patrol-runner gate passed: {ran} check(s){skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
