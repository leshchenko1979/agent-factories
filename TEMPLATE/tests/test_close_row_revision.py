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

The boundary is DECLARED, and this file SHIPS (issue #78, ruled n=515 clause 4)
-------------------------------------------------------------------------------
This file used to carry a section titled *"Why this is NOT paired into TEMPLATE"*. Its
argument was that the predicate reads `evidence/ledger.jsonl`, which is FACTORY DATA — a
bootstrapped factory has its own ledger, its own history and its own invariant date, so
shipping this file would assert another factory's boundary against it. The argument was
RIGHT about the hardcoded shape and WRONG only in concluding the gate cannot ship at all:
it is SUPERSEDED by the declared-parameter form, not discarded. The logic is universal;
the boundary is a factory parameter, and a parameter can be declared.

So the boundary moves out of this file and into `docs/ledger-invariants.json`, the
factory's own declaration, read through `tests/ledger_boundary.py` (shared with
`test_score_gate_recorded.py`, so the class has one implementation). A tree that has not
declared a boundary SKIPS with a stated reason — never a silent pass, and never a foreign
boundary. A tree with no ledger at all skips for the same reason: `TEMPLATE/evidence/`
does not exist, because the ledger is BOOTSTRAP-created.

The population guard is PROPORTIONAL (#78 clause c). The `>= 50` floor is dropped: it
fails a factory whose history is younger than 50 closes, and a floor cannot be both
universal and true. An empty post-boundary population skips with its reason instead, so
this gate either verifies a non-empty population or says why it examined nothing.

Run:  python3 -m pytest tests/test_close_row_revision.py -q
Exit: 0 clean, fully excused, or skipped-with-reason; non-zero on any post-boundary close
      without a revision, or on a declaration this tree cannot honour.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ledger_boundary import (  # noqa: E402
    GateError,
    SkipGate,
    boundary_and_rows,
    parse_ts,
    population_skip_reason,
    post_boundary_rows,
    synthetic_tree,
)

REPO = Path(__file__).resolve().parent.parent

# The ONE field predicate, shared with `tests/test_ledger_schema.py` and
# `tools/ledger.py`. Imported by module name so a staged throwaway `tools/` resolves it
# the same way — see tools/field_predicate.py.
sys.path.insert(0, str(REPO / "tools"))
from field_predicate import keyed_value, trailer_tokens  # noqa: E402

# The key this gate's boundary is declared under, in the factory's own
# `docs/ledger-invariants.json`. The key is the gate's own name, so the declaration says
# which invariant each date belongs to.
INVARIANT_KEY = "close_row_revision"

REVISION_FIELD = "head"
REVISION_KEY = f"{REVISION_FIELD}="
_HEX = set("0123456789abcdef")
_MIN_SHA = 7

# The DECLARED RETIREMENT surface: this gate's own factory data, read from the tree it
# judges and never inline in the gate — which is paired byte-identically into TEMPLATE/,
# so a factory's own row numbers must not live in a file that ships to every new factory.
# The skeleton is TEMPLATE/docs/ledger-retirements.example.json.
RETIREMENTS_PATH = "docs/ledger-retirements.json"

def _declared_revision(detail: str) -> str | None:
    """The `head=<sha>` value, or None when no readable field is present.

    A FIELD, not a prose mention: the token must DECLARE `head` — the shared
    `keyed_value` predicate in `tools/field_predicate.py`, which requires the key, then
    `=`, then a NON-EMPTY value — and that value must be hex of at least `_MIN_SHA`
    chars. Both halves are probed, because a predicate that only checked "is a sha
    present somewhere" would pass a row whose revision is merely cited in a sentence —
    the pattern-inflated shape #63 measured at 30 of 54. The shape half is the same
    predicate the telemetry gates use; only the type half is this gate's own, which is
    what makes it one class with one remedy rather than three readers (#88, n=405
    clause 5).

    The scan CONTINUES past an unreadable `head=` token rather than stopping at it, the
    shape `tests/test_score_gate_recorded.py::_has_head_sha` uses. Stopping at the first
    one is a false-RED generator: a row that DESCRIBES the field in prose before naming
    the revision ("the `head=` field is carried by only 4 rows ... head=02e9597...") does
    declare a revision, and an early return rejects it. Not hypothetical — it fired on
    this gate's own author's close row on the day it landed, and it is #53 clause 4's
    shape one layer up, prose mistaken for a field. The distinction that matters is
    readable-vs-not, so a row whose only `head=` token is unreadable is still reported,
    which `test_probe_rejects_an_unreadable_revision` pins.
    """
    for token in str(detail).replace(",", " ").replace(";", " ").split():
        value = keyed_value(token, REVISION_FIELD)
        if value is None:
            continue
        sha = value.strip(").`")
        if len(sha) >= _MIN_SHA and all(c in _HEX for c in sha):
            return sha
    return None

def _trailer_revision(detail: str) -> str | None:
    """The `head=<sha>` value from the row's CANONICAL RUN, or None when it declares none.

    The existence leg reads the run and never the whole detail, and the difference is
    MEASURED rather than theoretical (#104, ruled at `n=620` PART 5). `n=565` is the
    worked example: its prose quotes the FOREIGN sha `4ae1ffdb…`, which resolves, while
    its own trailer declares `3878936a…`. A whole-detail scan therefore reads a revision
    that row never measured — and the two failure directions are opposite: a quoted
    foreign sha REDs an honest row, and an EARLIER resolving prose token MASKS a
    fabricated trailer token, which is the defect this leg exists to catch.

    This is also §11's own definition applied literally: the canonical run IS the row's
    declaration, so a token outside it is a quotation. And it is one field with one
    predicate — the same `trailer_tokens` the repair path and the telemetry readers use.

    The value is the FIRST `head=` in the run, the same precedence `_declared_revision`
    applies; the run is short and its fields are machine-written, so a second `head=` is
    a writer defect rather than a choice this reader should resolve.
    """
    for token in trailer_tokens(detail):
        value = keyed_value(token, REVISION_FIELD)
        if value is None:
            continue
        sha = value.strip(").`")
        if len(sha) >= _MIN_SHA and all(c in _HEX for c in sha):
            return sha
    return None


def _resolves(sha: str, repo: Path) -> bool:
    """True when `sha` names a commit object in `repo`. Offline — no network, no board.

    EXISTENCE is neither ANCESTRY nor TRUTH, and the bound is stated so it is not
    oversold: a fabricated sha fails, while a real sha that is the WRONG revision
    passes. Ancestry is refused as the predicate because a history rewrite leaves an
    honest revision unreachable while its object survives, so ancestry would condemn
    exactly the rows a rewrite did not touch.
    """
    return subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", f"{sha}^{{commit}}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def read_retirements(repo: Path) -> tuple[list[dict], list[str]]:
    """`(entries, problems)` for the declared retirement surface.

    An ABSENT file means no retirements — the shipped state of a new factory, and not a
    defect. A file that exists but cannot be read is a problem: a declaration that
    quietly fails to load is indistinguishable from no declaration, which is the
    vacuous-pass shape this repo forbids. A malformed ENTRY is a problem too, for the
    same reason a malformed exemption is: it would excuse nothing while looking like it
    should.
    """
    path = repo / RETIREMENTS_PATH
    if not path.exists():
        return [], []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [], [f"{RETIREMENTS_PATH} is not valid JSON — {exc}"]
    entries = data.get("retirements") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return [], [f"{RETIREMENTS_PATH} carries no 'retirements' list"]
    problems: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            problems.append(f"{RETIREMENTS_PATH}: an entry is not an object")
            continue
        missing = [
            key
            for key in ("row", "field", "false_value", "naming_row", "true_value")
            if entry.get(key) in (None, "")
        ]
        if missing:
            problems.append(
                f"{RETIREMENTS_PATH}: an entry for row {entry.get('row')} is missing "
                f"{', '.join(missing)}"
            )
    return entries, problems


def retirement_problems(
    entries: list[dict], rows: list[dict]
) -> tuple[list[str], list[str], list[str]]:
    """`(problems, matched, prints)` for the retirement entries against `rows`.

    THE ADMISSION RULE, and it is a proof obligation rather than a lookup: an entry is
    admitted ONLY when the ledger CARRIES its naming row AND that row's detail carries
    the false value VERBATIM. The naming row is what makes a retirement auditable — it
    is the row that says "this value was wrong and here is the right one" — so a
    declaration whose naming row is absent is a gate ERROR, never a silent pass. An
    entry that matches no unresolvable token is an error too: it would inflate the
    visible debt while excusing nothing, the same shape as a stale exemption.

    `prints` is what every run shows, so clean / excused / retired are three DIFFERENT
    outputs and never the same one.
    """
    by_n = {row.get("n"): row for row in rows}
    problems: list[str] = []
    matched: list[str] = []
    prints: list[str] = []
    for entry in entries:
        row_n, naming_n = entry.get("row"), entry.get("naming_row")
        false_value, true_value = entry.get("false_value"), entry.get("true_value")
        target = by_n.get(row_n)
        naming = by_n.get(naming_n)
        if target is None:
            problems.append(
                f"{RETIREMENTS_PATH}: the entry for row {row_n} names a row this ledger "
                f"does not carry — an admission is proved against a row, never asserted"
            )
            continue
        if naming is None:
            problems.append(
                f"{RETIREMENTS_PATH}: the entry for row {row_n} names row {naming_n} as "
                f"its naming row, and this ledger does not carry it — a retirement whose "
                f"naming row is absent is not admitted"
            )
            continue
        if false_value not in str(naming.get("detail") or ""):
            problems.append(
                f"{RETIREMENTS_PATH}: the entry for row {row_n} claims row {naming_n} "
                f"names {false_value} verbatim, and that row's detail does not carry it"
            )
            continue
        if _trailer_revision(str(target.get("detail") or "")) != false_value:
            problems.append(
                f"{RETIREMENTS_PATH}: the entry for row {row_n} retires {false_value}, "
                f"which is not the value that row's canonical run declares — a stale "
                f"retirement excuses nothing"
            )
            continue
        matched.append(false_value)
        prints.append(
            f"retired: n={row_n} declares {REVISION_FIELD}={false_value} "
            f"(unresolvable), retired by n={naming_n} naming it verbatim; the row's "
            f"measured revision is {REVISION_FIELD}={true_value}"
        )
    return problems, matched, prints


def _is_git_work_tree(repo: Path) -> bool:
    """True when `repo` is inside a git work tree, so an object database exists."""
    return (
        subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--is-inside-work-tree"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def close_row_revision_existence_problems(
    population: list[dict], repo: Path, retired_values: set[str]
) -> tuple[list[str], int, str | None]:
    """`(problems, checked, reason)` over an ALREADY-SPLIT post-boundary population.

    Every row declaring a shape-valid `head=` in its canonical run must have that value
    RESOLVE to a commit object in this repository. The count examined is returned rather
    than kept, because the population is a property of the INSTANT: the ruling recorded
    33 tokens at its landing and the same read measures 37 now, so a gate that asserted
    a constant would go red for the one reason that is not a defect. It PRINTS what it
    examined, and a run that examined nothing is visible as such rather than reading as
    a clean one.

    `reason` is set when the tree under judgement carries no object database at all — a
    synthetic fixture, or a tree whose git is unavailable. That is a STATED inability to
    judge rather than a verdict: reporting "does not resolve" for every token in such a
    tree would be a false-RED generator, and returning a silent clean would be the
    vacuous pass this repo forbids. The caller turns it into a skip.

    A token equal to an ADMITTED retirement's false value is passed over here and printed
    by the caller, so clean / excused / retired stay three different outputs.
    """
    if not _is_git_work_tree(repo):
        return (
            [],
            0,
            f"the existence leg could not run: {repo} is not a git work tree, so it "
            f"carries no object database to resolve a declared revision against",
        )
    problems: list[str] = []
    checked = 0
    for row in population:
        n = row.get("n")
        sha = _trailer_revision(str(row.get("detail") or ""))
        if sha is None:
            continue
        checked += 1
        if sha in retired_values:
            continue
        if not _resolves(sha, repo):
            problems.append(
                f"n={n} declares {REVISION_KEY}{sha}, which does not resolve to a commit "
                f"in this repository — a receipt must name a revision that exists"
            )
    return problems, checked, None


def close_row_revision_problems(
    rows: list[dict], boundary_text: str
) -> tuple[list[str], list[str]]:
    """Return (problems, excused) for the `close` rows of a ledger.

    `problems` names every post-boundary close row that does not declare a readable
    revision; `excused` names every pre-boundary row, so the two are never conflated.
    `boundary_text` is the DECLARED boundary verbatim, so an excused line quotes the date
    the factory declared rather than one this file carries.
    """
    boundary = parse_ts(boundary_text)
    problems: list[str] = []
    excused: list[str] = []

    for row in rows:
        if row.get("event") != "close":
            continue
        n, ts = row.get("n"), row.get("ts", "")
        try:
            when = parse_ts(ts)
        except (ValueError, TypeError):
            problems.append(f"n={n}: unparseable ts {ts!r}")
            continue
        if when < boundary:
            excused.append(f"n={n} ({ts}) predates the declared boundary ({boundary_text})")
            continue
        if _declared_revision(str(row.get("detail") or "")) is None:
            problems.append(
                f"n={n} ({ts}) does not declare the revision its receipts describe "
                f"(expected a readable {REVISION_KEY}<sha> field)"
            )

    return problems, excused

def evaluate(repo: Path) -> tuple[str, str, list[str], list[str], int, list[str]]:
    """`(status, reason, problems, excused, checked, prints)` over `repo` — the core.

    `status` is `"pass"`, `"skip"` or `"fail"`. A real problem always outranks a skip:
    the population guard runs only on an otherwise-clean ledger, so a defect is never
    hidden behind "there was nothing to judge".

    `checked` is the EXISTENCE leg's own count — post-boundary close rows whose canonical
    run declares a shape-valid `head=` and whose value was resolved — while `excused` is
    the pre-boundary population the shape leg set aside. `prints` carries the admitted
    retirement declarations, so clean / excused / retired are three different outputs
    rather than one.
    """
    try:
        boundary, boundary_text, rows = boundary_and_rows(repo, INVARIANT_KEY)
    except SkipGate as exc:
        return "skip", str(exc), [], [], 0, []
    except GateError as exc:
        return "fail", "", list(exc.problems), [], 0, []

    problems, excused = close_row_revision_problems(rows, boundary_text)

    # The retirement surface is read from the tree UNDER JUDGEMENT, and a declaration it
    # cannot honour is a DEFECT rather than an absence — the same reason a malformed
    # boundary fails instead of skipping. The naming row is looked up in the whole ledger,
    # because a retirement is named by a `run` row rather than by a close.
    entries, retirement_read_problems = read_retirements(repo)
    retirement_issues, retired_values, prints = retirement_problems(entries, rows)
    problems = problems + retirement_read_problems + retirement_issues

    population = post_boundary_rows(rows, boundary, "close")
    existence_problems, checked, leg_reason = close_row_revision_existence_problems(
        population, repo, set(retired_values)
    )
    problems = problems + existence_problems

    if problems:
        return "fail", "", problems, excused, 0, prints

    reason = population_skip_reason(population, boundary_text, "close")
    if reason:
        return "skip", reason, [], excused, 0, prints

    # A leg that could not run is a STATED reason, never a clean verdict: the shape leg
    # judged its population and the existence leg did not, so the run must not print the
    # verdict of one that examined the population and found it clean.
    if leg_reason:
        return "skip", leg_reason, [], excused, 0, prints + [f"NOT RUN — {leg_reason}"]
    return "pass", "", [], excused, checked, prints

def _live_verdict() -> tuple[str, list[str], list[str], int, list[str]]:
    """The verdict for the tree this file is running in, skipping with its reason."""
    status, reason, problems, excused, checked, prints = evaluate(REPO)
    for line in excused:
        print(f"  excused: {line}")
    for line in prints:
        print(f"  {line}")
    if status == "skip":
        print(f"  SKIP: {reason}")
        pytest.skip(reason)
    if status == "fail":
        raise AssertionError(
            "close rows written after the declared boundary must name the revision their "
            "receipts describe, and that revision must EXIST:\n  " + "\n  ".join(problems)
        )
    return status, problems, excused, checked, prints

# --- live gate -------------------------------------------------------------------

def test_live_close_rows_declare_the_revision_they_measured() -> None:
    """The population is PRINTED, never asserted: it is a property of the INSTANT.

    The ruling recorded 33 tokens checked at its landing and the same read measures 37
    now, so a constant would go red for the one reason that is not a defect. A run that
    examined nothing is visible as `0 checked` rather than reading as a clean one.
    """
    _, _, excused, checked, prints = _live_verdict()
    print(
        f"close-row revision gate: {checked} post-boundary close row(s) declared a "
        f"revision and every one RESOLVES; {len(prints)} retired by declaration; "
        f"{len(excused)} excused (pre-boundary)"
    )

# --- probes: the tree the gate runs in, then the predicate it applies --------------

def _close(n: int, ts: str, detail: str) -> dict:
    return {
        "n": n,
        "ts": ts,
        "event": "close",
        "actor": "worker",
        "subject": "#1",
        "detail": detail,
    }

def test_probe_a_tree_with_no_ledger_skips_with_a_stated_reason(tmp_path: Path) -> None:
    """`TEMPLATE/evidence/` does not exist — the ledger is BOOTSTRAP-created. A gate
    that RAISED here was RED on the very tree it ships to (#78, #76's class)."""
    status, reason, problems, _, _, _ = evaluate(synthetic_tree(tmp_path / "bare"))
    assert status == "skip", (status, reason, problems)
    assert "evidence/ledger.jsonl" in reason and "BOOTSTRAP" in reason, reason

def test_probe_a_tree_with_no_declared_boundary_skips_with_a_stated_reason(
    tmp_path: Path,
) -> None:
    """A factory that has not adopted the invariant has no boundary to judge against —
    and that is a STATED skip, never a silent pass and never a foreign boundary."""
    tree = synthetic_tree(
        tmp_path / "undeclared",
        rows=[_close(1, "2026-09-19T06:00:00Z", "Closed. audit -> HEALTHY (PASS).")],
    )
    status, reason, _, _, _, _ = evaluate(tree)
    assert status == "skip", (status, reason)
    assert "ledger-invariants.json" in reason and "DECLARED factory parameter" in reason, reason

def test_probe_a_declaration_missing_this_key_skips(tmp_path: Path) -> None:
    """One declaration file serves every ledger invariant; a key a factory has not
    declared skips for that gate alone."""
    tree = synthetic_tree(
        tmp_path / "other-key",
        rows=[_close(1, "2026-09-19T06:00:00Z", "Closed. audit -> HEALTHY (PASS).")],
        invariants={"score_gate_recorded": "2026-09-18T10:04:05Z"},
    )
    status, reason, _, _, _, _ = evaluate(tree)
    assert status == "skip", (status, reason)
    assert INVARIANT_KEY in reason, reason

def test_probe_a_synthetic_tree_fails_a_close_row_with_no_revision(tmp_path: Path) -> None:
    """THE PROPERTY SURVIVES THE DECLARED FORM. Making the boundary a parameter must not
    cost the gate its teeth: a post-boundary close row with no revision still FAILS."""
    tree = synthetic_tree(
        tmp_path / "offending",
        rows=[_close(1, "2026-09-19T06:00:00Z", "Closed. audit -> HEALTHY (PASS).")],
        invariants={INVARIANT_KEY: "2026-09-19T05:00:00Z"},
    )
    status, _, problems, _, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert problems and "does not declare the revision" in problems[0], problems

def test_probe_a_compliant_synthetic_tree_is_not_condemned(tmp_path: Path) -> None:
    """A synthetic fixture has no object database, so the existence leg CANNOT judge it.

    The honest outcome is a STATED skip carrying that reason — never a pass it did not
    earn, and never a false RED from resolving every token against a tree that has no
    objects. (A pass is proven against the real repository by the live gate below; the
    fabricated/resolvable pair is proven directly in the probe that follows.)
    """
    tree = synthetic_tree(
        tmp_path / "compliant",
        rows=[
            _close(
                1,
                "2026-09-19T06:00:00Z",
                "Closed. Receipts taken at head=9552947a985b0f1a6c8919c362a0a56ec7d0d42e.",
            )
        ],
        invariants={INVARIANT_KEY: "2026-09-19T05:00:00Z"},
    )
    status, reason, problems, _, checked, prints = evaluate(tree)
    assert (status, problems, checked) == ("skip", [], 0), (status, reason, problems)
    assert "not a git work tree" in reason, reason
    assert any("NOT RUN" in line for line in prints), prints

def test_probe_the_boundary_comes_from_the_declaration_not_this_file(
    tmp_path: Path,
) -> None:
    """(b): the date is READ. The same row is post-boundary under one declaration and
    pre-boundary under another, and this file carries neither."""
    row = _close(1, "2026-09-19T06:00:00Z", "Closed. audit -> HEALTHY (PASS).")
    early = synthetic_tree(
        tmp_path / "early", rows=[row], invariants={INVARIANT_KEY: "2026-09-19T05:00:00Z"}
    )
    late = synthetic_tree(
        tmp_path / "late", rows=[row], invariants={INVARIANT_KEY: "2026-09-19T07:00:00Z"}
    )
    assert evaluate(early)[0] == "fail", "the declared boundary was not applied"
    status, _, problems, excused, _, _ = evaluate(late)
    assert (status, problems) == ("skip", []), (status, problems)
    assert excused and "2026-09-19T07:00:00Z" in excused[0], excused

def test_probe_an_empty_population_skips_rather_than_passing(tmp_path: Path) -> None:
    """(c), PROPORTIONAL: a young factory whose history predates the boundary — or holds
    no close at all — skips with its reason instead of passing vacuously."""
    tree = synthetic_tree(
        tmp_path / "young",
        rows=[_close(1, "2026-09-19T04:00:00Z", "Closed. no revision field.")],
        invariants={INVARIANT_KEY: "2026-09-19T05:00:00Z"},
    )
    status, reason, problems, excused, checked, _ = evaluate(tree)
    assert (status, problems, checked) == ("skip", [], 0), (status, reason, problems)
    assert "population is empty" in reason, reason
    assert len(excused) == 1, excused

def test_probe_an_empty_ledger_skips(tmp_path: Path) -> None:
    tree = synthetic_tree(
        tmp_path / "empty-ledger", rows=[], invariants={INVARIANT_KEY: "2026-09-19T05:00:00Z"}
    )
    status, reason, _, _, _, _ = evaluate(tree)
    assert status == "skip" and "carries no rows" in reason, (status, reason)

def test_probe_a_malformed_declaration_fails_rather_than_raising(tmp_path: Path) -> None:
    """A declared parameter that cannot be read is a DEFECT, not an absence: skipping it
    would hide a broken declaration behind the same output as no declaration."""
    tree = synthetic_tree(
        tmp_path / "malformed",
        rows=[_close(1, "2026-09-19T06:00:00Z", "Closed. head=9552947a985b0f1a6c8919c362a0a56ec7d0d42e")],
        declaration="{ this is not json",
    )
    status, _, problems, _, _, _ = evaluate(tree)
    assert status == "fail" and problems, (status, problems)
    assert "not valid JSON" in problems[0], problems

def test_probe_an_unreadable_declared_boundary_fails(tmp_path: Path) -> None:
    tree = synthetic_tree(
        tmp_path / "bad-date",
        rows=[_close(1, "2026-09-19T06:00:00Z", "Closed. head=9552947a985b0f1a6c8919c362a0a56ec7d0d42e")],
        invariants={INVARIANT_KEY: "yesterday"},
    )
    status, _, problems, _, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert "not a readable ISO-8601 timestamp" in problems[0], problems

def test_probe_a_corrupt_ledger_line_fails_rather_than_raising(tmp_path: Path) -> None:
    tree = synthetic_tree(
        tmp_path / "corrupt", invariants={INVARIANT_KEY: "2026-09-19T05:00:00Z"}
    )
    (tree / "evidence/ledger.jsonl").write_text('{"n": 1}\nnot a row\n', encoding="utf-8")
    status, _, problems, _, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert "is not a JSON row" in problems[0], problems

def test_probe_the_population_guard_is_proportional() -> None:
    """(c): the guard scales with the tree. An empty population is a REASON; a non-empty
    one is None, whatever its size — there is no floor left to fail a young factory."""
    assert population_skip_reason([], "2026-09-19T05:00:00Z", "close") is not None
    assert population_skip_reason([{"n": 1}], "2026-09-19T05:00:00Z", "close") is None

# --- probes: the predicate must reject bad input, not only accept good ------------

_PROBE_BOUNDARY = "2026-09-19T05:00:00Z"

_OK = {
    "n": 900,
    "ts": "2026-09-19T06:00:00Z",
    "event": "close",
    "detail": "Closed. Receipts taken at head=9552947a985b0f1a6c8919c362a0a56ec7d0d42e.",
}

def test_probe_accepts_a_compliant_close_row() -> None:
    problems, excused = close_row_revision_problems([_OK], _PROBE_BOUNDARY)
    assert problems == [] and excused == [], (problems, excused)

def test_probe_rejects_a_close_row_with_no_revision() -> None:
    row = {**_OK, "detail": "Closed. audit -> HEALTHY (PASS), 28 gates, 0 FAIL."}
    problems, _ = close_row_revision_problems([row], _PROBE_BOUNDARY)
    assert problems and "does not declare the revision" in problems[0], problems

def test_probe_rejects_an_unreadable_revision() -> None:
    """A `head=` field whose value is not a sha is present-but-unreadable, not absent."""
    for bad in ("head=not-a-sha", "head=abc", "head=zzzzzzzz"):
        row = {**_OK, "detail": f"Closed. Receipts taken at {bad}."}
        problems, _ = close_row_revision_problems([row], _PROBE_BOUNDARY)
        assert problems, f"{bad!r} must not read as a declared revision"

def test_probe_rejects_a_prose_mention_without_the_field() -> None:
    """The pattern-inflation trap: a sha cited in a sentence is not a declared revision.

    Measured at landing: 30 of 54 close rows carry a sha-shaped token, only 4 carry the
    field. Accepting the prose form would pass rows whose revision is never declared.
    """
    row = {**_OK, "detail": "Closed. The fix landed at 9c2ed02 as clause 8 of the stream."}
    problems, _ = close_row_revision_problems([row], _PROBE_BOUNDARY)
    assert problems, "a sha-shaped prose token must not satisfy the field"

def test_probe_accepts_a_row_that_describes_the_field_before_naming_it() -> None:
    """The live shape that made this gate reject its own author's close row.

    n=399 read "the head= FIELD is carried by only 4 (n=283, ...)" and only later
    "head=02e9597...". An early return on the first `head=` token rejected a row that does
    declare its revision — a false RED, and #53 clause 4's shape (prose read as a field).
    """
    row = {**_OK, "detail": (
        "Closed. The head= FIELD is carried by only 4 rows; the scan must continue past "
        "this prose to the field that follows. Receipts taken at "
        "head=9552947a985b0f1a6c8919c362a0a56ec7d0d42e."
    )}
    problems, _ = close_row_revision_problems([row], _PROBE_BOUNDARY)
    assert problems == [], f"a row naming its revision after describing the field must pass: {problems}"

def test_probe_rejects_a_pure_digit_comment_id() -> None:
    """n=303 cites 5737030289 — a GitHub comment id, which `git cat-file -t` does not
    resolve as an object. Ten such rows are in the live population."""
    row = {**_OK, "detail": "Closed. Receipt comment 5739522839 posted to the board."}
    problems, _ = close_row_revision_problems([row], _PROBE_BOUNDARY)
    assert problems, "a comment id must not satisfy the revision field"

def test_probe_rejects_a_telemetry_trailer_match() -> None:
    """The append tool writes `tokens_out=<n>` into every close row — a 7+ digit run that
    a loose hex-shaped pattern matches. It names no revision: n=349 and n=353 match ONLY
    there, which is why the loose pattern would pass rows that declare nothing."""
    row = {**_OK, "detail": "Closed. gate=all-pass outcome=accepted cost_usd=4.7343 "
                            "tokens_out=16830682 turns=5 duration=308s"}
    problems, _ = close_row_revision_problems([row], _PROBE_BOUNDARY)
    assert problems, "the telemetry trailer must not satisfy the revision field"

def test_probe_the_field_predicate_is_shared_not_reimplemented() -> None:
    """The scan's SHAPE half is the shared predicate, not a private copy (#88).

    Ledger `n=405` clause 5 ruled the class as ONE field predicate at three call sites,
    because three readings is how the class recurs: this file's own first version read
    `token.startswith("head=")` while the schema gate read every `k=v` token and the
    append guard read a substring. So the binding the scan calls must BE the shared
    function — a lookalike defined here would satisfy every behavioural probe above and
    still leave the class unfixed.
    """
    import field_predicate

    assert keyed_value is field_predicate.keyed_value, (
        "the scan must call the shared predicate, not a local re-implementation"
    )
    # And the shape the shared predicate changes at this site: a bare `head=` is a
    # MENTION. It names the field and states no value, so it declares no revision.
    row = {**_OK, "detail": "Closed. The head= field is read from the trailer; it is absent here."}
    problems, _ = close_row_revision_problems([row], _PROBE_BOUNDARY)
    assert problems, "a bare head= mention must not satisfy the revision field"

def test_probe_rejects_an_unparseable_timestamp() -> None:
    row = {**_OK, "ts": "not-a-timestamp"}
    problems, _ = close_row_revision_problems([row], _PROBE_BOUNDARY)
    assert problems and "unparseable ts" in problems[0], problems

def test_probe_excuses_pre_boundary_rows_without_calling_them_clean() -> None:
    legacy = {
        "n": 368,
        "ts": "2026-09-19T04:01:30Z",
        "event": "close",
        "detail": "Closed. python3 tools/audit.py -> HEALTHY (PASS), 27 gates, 0 FAIL.",
    }
    problems, excused = close_row_revision_problems([legacy], _PROBE_BOUNDARY)
    assert problems == [], problems
    assert len(excused) == 1 and "predates the declared boundary" in excused[0], excused

def test_probe_ignores_non_close_events() -> None:
    other = {"n": 901, "ts": "2026-09-19T06:00:00Z", "event": "claim", "detail": "x"}
    problems, excused = close_row_revision_problems([other], _PROBE_BOUNDARY)
    assert problems == [] and excused == []

# --- probes: the existence leg and the declared retirement surface (#104, PART 5) --

# The fixtures below are DERIVED from the tree under judgement, never written down. This
# gate is paired byte-identically into TEMPLATE/, so a hard-coded sha would resolve only
# in the repository it was copied from: the probe would pass here and go RED in every
# factory bootstrapped from the template. Factory data lives in the factory's own
# docs/ledger-retirements.json, which is exactly what the retirement probes exercise.

def _resolvable_sha(repo: Path) -> str:
    """`repo`'s own HEAD, read live — a revision that resolves in ANY factory."""
    out = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert _resolves(out, repo), out
    return out

def _absent_sha(repo: Path) -> str:
    """A 40-hex value `repo` does NOT carry, derived from one it does and then CHECKED
    against the object database — so the probe cannot pass by accident of which shas
    happen to exist here."""
    base = _resolvable_sha(repo)
    for i in range(len(base)):
        for ch in "0123456789abcdef":
            if ch == base[i]:
                continue
            candidate = base[:i] + ch + base[i + 1 :]
            if not _resolves(candidate, repo):
                return candidate
    raise AssertionError("every one-character mutation of HEAD resolves?")

def test_probe_a_fabricated_head_fails_and_a_resolvable_one_passes(tmp_path: Path) -> None:
    """EXISTENCE, and the bound it does NOT cover, stated so it is not oversold: a
    fabricated sha fails, while a real sha that is the WRONG revision passes. Both are
    probed against the REAL repository, so the check is shown to distinguish an absent
    OBJECT from an absent repository — a synthetic tree would fail either way."""
    fabricated = _close(
        1, "2026-09-19T06:00:00Z", f"Closed. head={_absent_sha(REPO)} board=closed"
    )
    problems, checked, reason = close_row_revision_existence_problems(
        [fabricated], REPO, set()
    )
    assert checked == 1 and problems and reason is None, (checked, problems, reason)
    assert "does not resolve" in problems[0], problems

    real = _close(
        2, "2026-09-19T06:00:00Z", f"Closed. head={_resolvable_sha(REPO)} board=closed"
    )
    problems, checked, reason = close_row_revision_existence_problems([real], REPO, set())
    assert (problems, checked, reason) == ([], 1, None), (problems, checked, reason)

    # And a tree with no object database is a STATED inability to judge, never a clean
    # verdict and never a false RED — every token in such a tree would "not resolve".
    _, checked, reason = close_row_revision_existence_problems(
        [fabricated], tmp_path, set()
    )
    assert checked == 0 and reason and "not a git work tree" in reason, (checked, reason)

def test_probe_the_existence_leg_reads_the_canonical_run_not_the_whole_detail() -> None:
    """`n=565`'s measured shape, and why the whole-detail scan is refused.

    The row's prose quotes a RESOLVING foreign sha while its own trailer declares an
    ABSENT one. A whole-detail scan reads the quotation and passes the row, which is
    the defect this leg exists to catch; the trailer read condemns it. The two directions
    are opposite and both are real: a quoted foreign sha REDs an honest row, and an
    EARLIER resolving prose token MASKS a fabricated trailer token.
    """
    absent, present = _absent_sha(REPO), _resolvable_sha(REPO)
    row = _close(
        1,
        "2026-09-19T06:00:00Z",
        f"Closed. The fix landed at {present} as described. board=closed head={absent}",
    )
    assert _trailer_revision(row["detail"]) == absent, _trailer_revision(row["detail"])
    problems, checked, reason = close_row_revision_existence_problems([row], REPO, set())
    assert checked == 1 and problems and reason is None, (checked, problems, reason)
    assert absent in problems[0], problems

def test_probe_a_declared_retirement_with_its_naming_row_passes_and_prints() -> None:
    """The admission rule SATISFIED: the ledger CARRIES the naming row and that row's
    detail carries the false value VERBATIM. The entry is then PRINTED, and the token it
    retires is passed over by the existence leg rather than condemned."""
    false_value, true_value = _absent_sha(REPO), _resolvable_sha(REPO)
    entries = [
        {
            "row": 618,
            "field": REVISION_FIELD,
            "false_value": false_value,
            "naming_row": 619,
            "true_value": true_value,
        }
    ]
    target = _close(618, "2026-09-19T06:00:00Z", f"Closed. head={false_value} board=closed")
    naming = {
        "n": 619,
        "ts": "2026-09-19T06:01:00Z",
        "event": "run",
        "actor": "worker",
        "subject": "#102",
        "detail": (
            f"CORRECTION: n=618 declares head={false_value}, which does not resolve to a "
            f"commit; the revision it measured is head={true_value}."
        ),
    }
    problems, matched, prints = retirement_problems(entries, [target, naming])
    assert (problems, matched) == ([], [false_value]), (problems, matched)
    assert prints and false_value in prints[0] and "n=619" in prints[0], prints

    problems, checked, reason = close_row_revision_existence_problems(
        [target], REPO, set(matched)
    )
    assert (problems, checked, reason) == ([], 1, None), (problems, checked, reason)

def test_probe_a_retirement_whose_naming_row_is_absent_is_an_error() -> None:
    """A retirement is AUDITABLE only through the row that names it, so a declaration
    whose naming row this ledger does not carry is a gate ERROR — never a silent pass."""
    false_value = _absent_sha(REPO)
    entries = [
        {
            "row": 618,
            "field": REVISION_FIELD,
            "false_value": false_value,
            "naming_row": 999,
            "true_value": _resolvable_sha(REPO),
        }
    ]
    target = _close(618, "2026-09-19T06:00:00Z", f"Closed. head={false_value} board=closed")
    problems, matched, prints = retirement_problems(entries, [target])
    assert problems and "naming row" in problems[0], problems
    assert matched == [] and prints == [], (matched, prints)

def test_probe_a_stale_retirement_excuses_nothing() -> None:
    """An entry matching no unresolvable token would inflate the visible debt while
    excusing nothing — the shape a stale exemption has, and an ERROR for the same reason.
    Here the naming row does carry the false value, so only the target's own run refutes
    it: the row declares a RESOLVING sha, and the entry is stale."""
    false_value, true_value = _absent_sha(REPO), _resolvable_sha(REPO)
    entries = [
        {
            "row": 618,
            "field": REVISION_FIELD,
            "false_value": false_value,
            "naming_row": 619,
            "true_value": true_value,
        }
    ]
    target = _close(618, "2026-09-19T06:00:00Z", f"Closed. head={true_value} board=closed")
    naming = {
        "n": 619,
        "ts": "2026-09-19T06:01:00Z",
        "event": "run",
        "actor": "worker",
        "subject": "#102",
        "detail": f"notes that head={false_value} was the wrong value",
    }
    problems, matched, _ = retirement_problems(entries, [target, naming])
    assert problems and "stale retirement" in problems[0], problems
    assert matched == [], matched

def test_probe_an_absent_retirement_file_is_not_a_defect() -> None:
    """A new factory ships NO retirements. The skeleton under `TEMPLATE/docs/` is the
    example, and the example itself is never read — so absence reads as absence, not as
    a gate that cannot load its data."""
    entries, problems = read_retirements(REPO / "TEMPLATE")
    assert (entries, problems) == ([], []), (entries, problems)

def test_probe_a_malformed_retirement_file_fails_rather_than_raising(tmp_path: Path) -> None:
    """A declaration that cannot be READ is indistinguishable from no declaration, which
    is the vacuous-pass shape this repo forbids."""
    tree = synthetic_tree(
        tmp_path / "bad-retirements", invariants={INVARIANT_KEY: "2026-09-19T05:00:00Z"}
    )
    (tree / RETIREMENTS_PATH).write_text("{ not json", encoding="utf-8")
    entries, problems = read_retirements(tree)
    assert problems and "not valid JSON" in problems[0], problems

def test_probe_a_tree_with_no_object_database_skips_with_its_reason(
    tmp_path: Path,
) -> None:
    """The shape leg judged its population and the existence leg could NOT, so the run
    must say NOT RUN rather than print a clean verdict — and it must not report every
    token as unresolvable, which is the false-RED direction of the same defect."""
    tree = synthetic_tree(
        tmp_path / "no-object-db",
        rows=[
            _close(
                1,
                "2026-09-19T06:00:00Z",
                "Closed. Receipts taken at head=9552947a985b0f1a6c8919c362a0a56ec7d0d42e.",
            )
        ],
        invariants={INVARIANT_KEY: "2026-09-19T05:00:00Z"},
    )
    status, reason, problems, _, checked, prints = evaluate(tree)
    assert (status, problems, checked) == ("skip", [], 0), (status, reason, problems)
    assert "not a git work tree" in reason, reason
    assert any("NOT RUN" in line for line in prints), prints

def main() -> int:
    """Script form: the same verdict, with the skip reason on STDOUT rather than in a
    pytest short summary — so a reader of the run sees WHY nothing was judged."""
    status, reason, problems, _, checked, prints = evaluate(REPO)
    if status == "skip":
        print(f"close-row revision gate: SKIP — {reason}")
        return 0
    if status == "fail":
        print("close-row revision gate FAILED:", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        return 1
    for line in prints:
        print(f"  {line}")
    print(
        f"close-row revision gate: clean — {checked} post-boundary close row(s) declared "
        f"a revision and every one RESOLVES; {len(prints)} retired by declaration"
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
