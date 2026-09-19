#!/usr/bin/env python3
"""Gate: a close row's receipt names the revision it measured.

Origin (issue #63). A close row is the ledger's completion claim: it says a work unit is
finished. Its detail carries receipts — gate counts, row counts, verify exit codes — and
those receipts were TRUE of the working tree the author measured. Nothing required them
to name WHICH revision that was, and no gate read the receipt at all. So the row is not
false; it is UNCHECKABLE: a reader cannot tell whether "27 gates, 0 FAIL" describes the
tree that shipped or a tree that has since moved four commits.

The sharpening. SKILL.md §8 already says verdict verbs need a receipt. This adds the
missing half — the receipt must name the revision it measured. Without it a receipt
degrades into testimony: an assertion about a tree nobody can identify.

The rule, in two parts — the shape `tests/test_score_gate_recorded.py` already uses for
`score` rows, REUSED rather than reinvented:

1. **Every `close` row written on or after the invariant lands carries `head=<sha>`**,
   the revision its receipts describe. The sha makes the row checkable against the
   repository instead of a claim about a tree that has since moved.
2. **Rows written before the invariant are excused, and said so.** Reported as
   `excused:` with their count, never folded into a bare "clean" — so "clean" and
   "excused" are never the same output. Nothing is backfilled: a revision written today
   for a close that predates the rule would be a falsified record, not a repair
   (#52 clause 2(a), #53 clause 7).

The predicate reads the FIELD, never the prose
----------------------------------------------
Measured when this landed: a loose hex-shaped pattern matches 30 of 54 close rows, but
only 4 carry `head=`. A predicate that accepted any hex token would pass 30 rows whose
revision is not actually declared — and a hex-shaped token is not even necessarily a
revision. Two of the 30 (n=349, n=353) match only inside the append tool's own telemetry
trailer (`tokens_out=`), which is machine-written and names no revision at all; seven
more cite a 10-digit GitHub comment id that `git cat-file -t` does not resolve as an
object (n=10, 303, 341, 368, 370, 372, 374). So the value is validated as a FIELD: a
`head=` token whose value is hex and at least 7 chars. This is #53 clause 4's discipline,
whose three live instances there were prose misread as fields.

Why this is NOT paired into TEMPLATE
------------------------------------
`tests/test_score_gate_recorded.py` is registered in both `tools/audit.py` copies but is
NOT in `tests/test_template_sync.py`'s PAIRS and has no `TEMPLATE/tests/` twin. That is
the right shape here too, and it is deliberate rather than an accident copied forward:
this predicate reads `evidence/ledger.jsonl`, which is FACTORY DATA. A bootstrapped
factory has its own ledger, its own history and its own invariant date; shipping this
file would assert another factory's boundary against it. The audit's registration is
guarded by `is_file()`, so a factory that adopts the invariant adds the gate and its
boundary together.

Run:  python3 -m pytest tests/test_close_row_revision.py -q
Exit: 0 clean or fully excused, non-zero on any post-invariant close without a revision.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "evidence" / "ledger.jsonl"

# The moment the invariant landed: the commit introducing this gate and the SKILL.md §8
# sharpening that states it. Close rows written before this moment predate the rule and
# are excused; rows at or after it must name the revision. Nothing before it is backfilled.
INVARIANT_LANDED = "2026-09-19T05:05:49Z"

REVISION_KEY = "head="
_HEX = set("0123456789abcdef")
_MIN_SHA = 7

def _parse_ts(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))

def _declared_revision(detail: str) -> str | None:
    """The `head=<sha>` value, or None when no readable field is present.

    A FIELD, not a prose mention: the token must start with `head=`, and its value must
    be hex of at least `_MIN_SHA` chars. Both halves are probed, because a predicate that
    only checked "is a sha present somewhere" would pass a row whose revision is merely
    cited in a sentence — the pattern-inflated shape #63 measured at 30 of 54.

    The scan CONTINUES past an unreadable `head=` token rather than stopping at it, the
    shape `tests/test_score_gate_recorded.py::_has_head_sha` uses. Stopping at the first
    one is a false-RED generator: a row that DESCRIBES the field in prose before naming
    the revision ("the `head=` field is carried by only 4 rows ... head=02e9597…") does
    declare a revision, and an early return rejects it. Not hypothetical — it fired on
    this gate's own author's close row on the day it landed, and it is #53 clause 4's
    shape one layer up, prose mistaken for a field. The distinction that matters is
    readable-vs-not, so a row whose only `head=` token is unreadable is still reported,
    which `test_probe_rejects_an_unreadable_revision` pins.
    """
    for token in str(detail).replace(",", " ").replace(";", " ").split():
        if not token.startswith(REVISION_KEY):
            continue
        sha = token[len(REVISION_KEY):].strip(").`")
        if len(sha) >= _MIN_SHA and all(c in _HEX for c in sha):
            return sha
    return None

def close_row_revision_problems(
    rows: list[dict], exempt_before: str = INVARIANT_LANDED
) -> tuple[list[str], list[str]]:
    """Return (problems, excused) for the `close` rows of a ledger.

    `problems` names every post-invariant close row that does not declare a readable
    revision; `excused` names every pre-invariant row, so the two are never conflated.
    """
    boundary = _parse_ts(exempt_before)
    problems: list[str] = []
    excused: list[str] = []

    for row in rows:
        if row.get("event") != "close":
            continue
        n, ts = row.get("n"), row.get("ts", "")
        try:
            when = _parse_ts(ts)
        except (ValueError, TypeError):
            problems.append(f"n={n}: unparseable ts {ts!r}")
            continue
        if when < boundary:
            excused.append(f"n={n} ({ts}) predates the invariant ({exempt_before})")
            continue
        if _declared_revision(str(row.get("detail") or "")) is None:
            problems.append(
                f"n={n} ({ts}) does not declare the revision its receipts describe "
                f"(expected a readable {REVISION_KEY}<sha> field)"
            )

    return problems, excused

def _load_rows() -> list[dict]:
    rows: list[dict] = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows

# --- live gate -------------------------------------------------------------------

def test_live_close_rows_declare_the_revision_they_measured() -> None:
    rows = _load_rows()
    problems, excused = close_row_revision_problems(rows)
    for line in excused:
        print(f"  excused: {line}")
    if problems:
        raise AssertionError(
            "close rows written after the receipt-revision invariant must name the "
            "revision their receipts describe:\n  " + "\n  ".join(problems)
        )
    boundary = _parse_ts(INVARIANT_LANDED)
    checked = sum(
        1
        for r in rows
        if r.get("event") == "close" and _parse_ts(r.get("ts", "")) >= boundary
    )
    print(
        f"close-row revision gate: {checked} post-invariant close row(s) verified, "
        f"{len(excused)} excused (pre-invariant)"
    )

# --- probes: the invariant must reject bad input, not only accept good ------------

_OK = {
    "n": 900,
    "ts": "2026-09-19T06:00:00Z",
    "event": "close",
    "detail": "Closed. Receipts taken at head=9552947a985b0f1a6c8919c362a0a56ec7d0d42e.",
}

def test_probe_accepts_a_compliant_close_row() -> None:
    problems, excused = close_row_revision_problems([_OK])
    assert problems == [] and excused == [], (problems, excused)

def test_probe_rejects_a_close_row_with_no_revision() -> None:
    row = {**_OK, "detail": "Closed. audit -> HEALTHY (PASS), 28 gates, 0 FAIL."}
    problems, _ = close_row_revision_problems([row])
    assert problems and "does not declare the revision" in problems[0], problems

def test_probe_rejects_an_unreadable_revision() -> None:
    """A `head=` field whose value is not a sha is present-but-unreadable, not absent."""
    for bad in ("head=not-a-sha", "head=abc", "head=zzzzzzzz"):
        row = {**_OK, "detail": f"Closed. Receipts taken at {bad}."}
        problems, _ = close_row_revision_problems([row])
        assert problems, f"{bad!r} must not read as a declared revision"

def test_probe_rejects_a_prose_mention_without_the_field() -> None:
    """The pattern-inflation trap: a sha cited in a sentence is not a declared revision.

    Measured at landing: 30 of 54 close rows carry a sha-shaped token, only 4 carry the
    field. Accepting the prose form would pass rows whose revision is never declared.
    """
    row = {**_OK, "detail": "Closed. The fix landed at 9c2ed02 as clause 8 of the stream."}
    problems, _ = close_row_revision_problems([row])
    assert problems, "a sha-shaped prose token must not satisfy the field"

def test_probe_accepts_a_row_that_describes_the_field_before_naming_it() -> None:
    """The live shape that made this gate reject its own author's close row.

    n=399 read "the head= FIELD is carried by only 4 (n=283, ...)" and only later
    "head=02e9597…". An early return on the first `head=` token rejected a row that does
    declare its revision — a false RED, and #53 clause 4's shape (prose read as a field).
    """
    row = {**_OK, "detail": (
        "Closed. The head= FIELD is carried by only 4 rows; the scan must continue past "
        "this prose to the field that follows. Receipts taken at "
        "head=9552947a985b0f1a6c8919c362a0a56ec7d0d42e."
    )}
    problems, _ = close_row_revision_problems([row])
    assert problems == [], f"a row naming its revision after describing the field must pass: {problems}"

def test_probe_rejects_a_pure_digit_comment_id() -> None:
    """n=303 cites 5737030289 — a GitHub comment id, which `git cat-file -t` does not
    resolve as an object. Ten such rows are in the live population."""
    row = {**_OK, "detail": "Closed. Receipt comment 5739522839 posted to the board."}
    problems, _ = close_row_revision_problems([row])
    assert problems, "a comment id must not satisfy the revision field"

def test_probe_rejects_a_telemetry_trailer_match() -> None:
    """The append tool writes `tokens_out=<n>` into every close row — a 7+ digit run that
    a loose hex-shaped pattern matches. It names no revision: n=349 and n=353 match ONLY
    there, which is why the loose pattern would pass rows that declare nothing."""
    row = {**_OK, "detail": "Closed. gate=all-pass outcome=accepted cost_usd=4.7343 "
                            "tokens_out=16830682 turns=5 duration=308s"}
    problems, _ = close_row_revision_problems([row])
    assert problems, "the telemetry trailer must not satisfy the revision field"

def test_probe_rejects_an_unparseable_timestamp() -> None:
    row = {**_OK, "ts": "not-a-timestamp"}
    problems, _ = close_row_revision_problems([row])
    assert problems and "unparseable ts" in problems[0], problems

def test_probe_excuses_pre_invariant_rows_without_calling_them_clean() -> None:
    legacy = {
        "n": 368,
        "ts": "2026-09-19T04:01:30Z",
        "event": "close",
        "detail": "Closed. python3 tools/audit.py -> HEALTHY (PASS), 27 gates, 0 FAIL.",
    }
    problems, excused = close_row_revision_problems([legacy])
    assert problems == [], problems
    assert len(excused) == 1 and "predates the invariant" in excused[0], excused

def test_probe_ignores_non_close_events() -> None:
    other = {"n": 901, "ts": "2026-09-19T06:00:00Z", "event": "claim", "detail": "x"}
    problems, excused = close_row_revision_problems([other])
    assert problems == [] and excused == []

def test_probe_the_boundary_is_a_module_constant() -> None:
    """The boundary travels with the predicate, so a caller cannot silently re-date it."""
    assert isinstance(INVARIANT_LANDED, str) and INVARIANT_LANDED.endswith("Z")
    _parse_ts(INVARIANT_LANDED)

def test_probe_the_live_ledger_has_close_rows_to_judge() -> None:
    """A gate whose population is empty passes vacuously — state the population."""
    rows = _load_rows()
    closes = [r for r in rows if r.get("event") == "close"]
    assert len(closes) >= 50, f"expected the live ledger's close rows, found {len(closes)}"
