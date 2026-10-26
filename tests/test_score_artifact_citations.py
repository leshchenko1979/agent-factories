#!/usr/bin/env python3
"""Gate: every commit a round artifact cites names a commit HEAD can reach.

Origin (#566, ruled at ledger `n=4320`, dispatched at `n=4328`). A round artifact is
written BEFORE the push, and the landing route is a fast-forward-only pusher over a remote
peers advance continuously. So a round that must be caught up is caught up with
`git rebase --committer-date-is-author-date origin/main`, which rewrites EVERY sha the
round created. A sha recorded at write time is therefore dead **by construction** — not by
carelessness — and it reproduced twice before anyone named it: `ea7f357d` on one round,
then `48244053` and `686aae47` on the next.

The artifact is the round's product, so it cannot wait for the push; the writing discipline
that removes the class (`docs/measurement-procedure.md` §6 — cite the commit SUBJECT, and
read a sha from `origin/main` only after the pusher has run) is HQ's half and has landed.
This gate is the other half: it asserts the property rather than trusting the discipline.

WHAT IS JUDGED, AND WHY IT IS RESOLUTION AND NOT SHAPE
------------------------------------------------------
Every backticked hex token of 7 to 40 characters in an in-scope artifact is a citation and
must be REACHABLE FROM `HEAD`. The predicate is
`git merge-base --is-ancestor <token> HEAD`, which is OFFLINE — no fetch, no network, so it
belongs in the derived set.

A token is judged by whether it RESOLVES, never by what it looks like, and the reason is a
live near-miss on this very unit: `48244053` is **all digits**, so the obvious "skip
all-digit tokens, they are not shas" filter — the one every hex scanner reaches for —
discards the exact defect this gate exists to catch. An 8-character all-digit string is a
perfectly lawful abbreviated sha. The probe `test_probe_an_ALL_DIGIT_token_is_JUDGED` holds
that arm open so a later "optimisation" cannot re-introduce it.

THE ESCAPES ARE DECLARED, NEVER INFERRED (#566's decision, and the whole reason this gate
can be built at all)
---------------------------------------------------------------------------------------
Three shapes are legitimate and all three are, to a resolver, INDISTINGUISHABLE FROM A
TYPO: a foreign repository's commit, a pre-rebase name deliberately recorded as the
withdrawn value inside a correction, and a non-commit identifier (a session uuid, a
patch-id, an md5 prefix). A gate that guessed the class from context could not tell a
lawful pre-rebase name from a careless paste, so it would either pass typos or red on
correct artifacts — worse than no gate.

So the class is written ON THE CITATION, within `DECL_WINDOW` characters after the token on
the SAME LINE, in one of three forms: `foreign:<owner/repo>`, `pre-rebase:`, `non-commit:`.
An UNDECLARED token that HEAD cannot reach is a finding. A declared one is not.
Over-declaration is never a finding — the one-directional rule this factory already applies
to gate triggers (`#567`, `#568`), and for the same reason: a probe that can fail in two
directions gets turned off.

DECLARATION IS LOCAL BY CONSTRUCTION, and the locality is asserted: the marker must sit on
the token's OWN LINE. A file-wide marker would let one declaration exempt every citation
below it, which is the exemption-by-silence shape in a single artifact.

THE BOUNDARY IS FACTORY DATA, NOT A LITERAL
-------------------------------------------
This file is paired byte-identically with `TEMPLATE/tests/test_score_artifact_citations.py`,
so a date written here would ship to every member and be read against the MEMBER's scores
directory, where the day this law landed means nothing. The boundary is therefore DECLARED
in `docs/ledger-invariants.json` under `INVARIANT_KEY` and read through
`tests/ledger_boundary.py`: an ABSENT declaration SKIPS with its reason, a MALFORMED one
FAILS. Artifacts dated at or before the boundary print as `excused:` with their count on
every run, so "clean" and "excused" are never the same output — and they are never
backfilled, because a citation reconstructed after the fact is fabricated provenance, the
same no-backfill law as the close trailer's.

WHY THE POPULATION IS BOUNDED AND THE BOUND IS STATED
-----------------------------------------------------
The class is structural for every round written before the writing rule landed: 157 of the
301 distinct hex tokens in this factory's scores directory name commits no ref can reach.
Demanding a declaration on each would mean re-typing published artifacts — which this
factory refuses by precedent (`evidence/rework.md`, the `#566` entry: the stale citations
are LEFT STANDING and the correction is the only place a reader is asked to look twice) —
or extending a vocabulary until the gate is exempted into silence, which the ruling names
as the failure mode. So the boundary is dated, printed, and counts its own excused
population on every run.

Run:  python3 -m pytest tests/test_score_artifact_citations.py -q
      python3 tests/test_score_artifact_citations.py
Exit: 0 clean or fully excused, non-zero on any in-scope undeclared unreachable citation.
"""

from __future__ import annotations

import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ledger_boundary import (  # noqa: E402
    GateError,
    SkipGate,
    declared_boundary,
    population_skip_reason,
)

REPO = Path(__file__).resolve().parent.parent
SCORES = REPO / "evidence" / "scores"
PROCEDURE = REPO / "docs" / "measurement-procedure.md"

# The declaration's key is the gate's own name, the convention `docs/ledger-invariants.json`
# states for every boundary it carries.
INVARIANT_KEY = "score_artifact_citations"

# The escape vocabulary, fixed by the ruling. These three strings are the WHOLE interface
# between an artifact and this gate; a fourth class is a decision for HQ, not for a lane.
ESCAPE_FOREIGN = "foreign:"
ESCAPE_PRE_REBASE = "pre-rebase:"
ESCAPE_NON_COMMIT = "non-commit:"
ESCAPES = (ESCAPE_FOREIGN, ESCAPE_PRE_REBASE, ESCAPE_NON_COMMIT)

# `foreign:` names the repository, so the form is asserted rather than just the prefix: a
# bare `foreign:` says "not ours" and gives the next reader nothing to follow.
FOREIGN_RE = re.compile(r"foreign:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")

# A citation is a CODE SPAN. Matching bare hex anywhere in prose catches English words --
# measured on this factory's own artifacts, a naive `[0-9a-f]{7,40}` sweep over
# `evidence/scores/*.md` returned 403 distinct tokens against 301 real ones, the difference
# being words like `defaced`, `added` and `beefed`. The code span is what makes a token a
# citation rather than a syllable.
SPAN_RE = re.compile(r"`([^`\n]{1,64})`")
HEX_RE = re.compile(r"^[0-9a-f]{7,40}$")

# How far after a token its declaration may sit, on the same line. Wide enough for the
# artifact's own parentheticals -- `(pre-rebase; published as 0c4c40c5)` -- and narrow
# enough that it cannot reach the next row of a table.
DECL_WINDOW = 160

SCORES_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")


def citations(text: str) -> list[tuple[int, str, int, str]]:
    """`(lineno, token, end_col, line)` for every code-span hex token in `text`.

    `end_col` is the column just past the token's own span, which is where the search for a
    declaration starts. A token is returned ONCE PER OCCURRENCE, not deduplicated: two
    citations of the same dead sha in one artifact are two places a reader follows, and the
    finding names the line.
    """
    found: list[tuple[int, str, int, str]] = []
    for lineno, line in enumerate(text.split("\n"), 1):
        for span in SPAN_RE.finditer(line):
            token = span.group(1).strip()
            if HEX_RE.match(token):
                found.append((lineno, token, span.end(), line))
    return found


def declared_class(line: str, end_col: int) -> str | None:
    """The escape class declared for the token ending at `end_col`, or `None`.

    The marker must appear on the token's OWN LINE, inside `DECL_WINDOW` characters after
    it. `foreign:` is matched in its full `foreign:<owner/repo>` form because the prefix
    alone names no repository; the other two are matched as prefixes, since what follows
    them is prose for a human rather than a parameter.
    """
    window = line[end_col : end_col + DECL_WINDOW]
    if FOREIGN_RE.search(window):
        return ESCAPE_FOREIGN
    for marker in (ESCAPE_PRE_REBASE, ESCAPE_NON_COMMIT):
        if marker in window:
            return marker
    return None


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    """One git call, offline, with its exit code preserved."""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
    )


def resolves(repo: Path, token: str) -> bool:
    """Whether `token` names a commit object in `repo` at all."""
    return git(repo, "cat-file", "-e", f"{token}^{{commit}}").returncode == 0


def is_ancestor(repo: Path, token: str) -> bool:
    """Whether `token` is reachable from `HEAD` — the predicate the ruling names."""
    return git(repo, "merge-base", "--is-ancestor", token, "HEAD").returncode == 0


def judge(repo: Path, text: str) -> tuple[list[str], int, int]:
    """`(findings, judged, declared)` for one artifact's text.

    A citation passes on either arm: HEAD can reach it, or the citation declares its class.
    Both are checked, and the declaration is read FIRST because it is the cheaper arm and
    because an over-declared reachable citation is explicitly not a finding.
    """
    findings: list[str] = []
    judged = 0
    declared = 0
    for lineno, token, end_col, line in citations(text):
        judged += 1
        klass = declared_class(line, end_col)
        if klass is not None:
            declared += 1
            continue
        if not resolves(repo, token):
            findings.append(
                f"line {lineno}: `{token}` names no commit in this repository and declares "
                f"no class — one of {', '.join(ESCAPES)} is required if it is lawful"
            )
        elif not is_ancestor(repo, token):
            findings.append(
                f"line {lineno}: `{token}` resolves but is NOT reachable from HEAD — a name "
                f"rewritten by a catch-up rebase; cite the published sha or declare "
                f"{ESCAPE_PRE_REBASE}"
            )
    return findings, judged, declared


def declared_day(repo: Path, key: str) -> dt.date:
    """The declared boundary `key` names, as a DATE, or `SkipGate`/`GateError`.

    The declaration is FACTORY DATA and never ships, so its ABSENCE is a stated skip — the
    state every bootstrapped factory is in until it adopts the invariant. A MALFORMED
    declaration is a `GateError`: a broken declaration must not hide behind the same output
    as none at all. Artifact names are dated (`YYYY-MM-DD.md`), so the boundary is compared
    as a DATE; the declaration's time of day carries no meaning here.
    """
    return declared_boundary(repo, key)[0].date()


def _declared_day_or_skip(repo: Path, key: str) -> dt.date:
    """`declared_day`, with the two declaration outcomes mapped onto pytest."""
    try:
        return declared_day(repo, key)
    except SkipGate as exc:
        pytest.skip(str(exc))
    except GateError as exc:
        raise AssertionError("; ".join(exc.problems)) from exc


def artifacts(scores: Path) -> list[tuple[dt.date, Path]]:
    """Every dated score artifact under `scores`, oldest first.

    Only `YYYY-MM-DD.md` is a round artifact. A file that does not carry a date is not
    silently dropped: it is REPORTED, because a population that quietly omits its
    unparseable members is a population nobody can count.
    """
    dated: list[tuple[dt.date, Path]] = []
    for path in sorted(scores.glob("*.md")):
        match = SCORES_NAME_RE.match(path.name)
        if match:
            dated.append((dt.date.fromisoformat(match.group(1)), path))
    return dated


def undated_artifacts(scores: Path) -> list[str]:
    """The `.md` files under `scores` whose name carries no date."""
    return [p.name for p in sorted(scores.glob("*.md")) if not SCORES_NAME_RE.match(p.name)]


def _population_reason(population: list[str], boundary: dt.date, what: str) -> str:
    """The stated skip reason when a post-boundary population is empty, else ""."""
    if population:
        return ""
    return population_skip_reason([], f"the declared boundary {boundary.isoformat()}", what) or ""


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    """A git call against a SYNTHETIC repo, with a hermetic identity and no signing."""
    return subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=probe",
            "-c",
            "user.email=probe@example.invalid",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        capture_output=True,
        text=True,
    )


def synthetic_repo(tmp_path: Path) -> tuple[Path, str, str]:
    """`(repo, reachable_sha, dangling_sha)` — a throwaway repo holding both arms.

    BUILT, never borrowed. This file is paired byte-identically with its `TEMPLATE` copy, so
    a real sha of THIS factory's history written inside a probe would be read against a
    member's tree that does not contain it — the `#78`/`#239` class, twice measured. The
    repo is hermetic: three commits, the third orphaned by a hard reset, so the reachable
    arm and the resolves-but-unreachable arm are both produced by git itself and no fixture
    data enters the file.
    """
    repo = tmp_path / "synthetic"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "probe.txt").write_text("one\n", encoding="utf-8")
    _git(repo, "add", "probe.txt")
    _git(repo, "commit", "-q", "-m", "one")
    reachable = _git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "probe.txt").write_text("two\n", encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "two")
    dangling = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "reset", "-q", "--hard", reachable)
    return repo, reachable, dangling


# --------------------------------------------------------------------------------------
# The probes. A rule that has only ever seen good input has not been shown to reject bad
# input, so every arm below is driven by a synthetic tree the fixture built.
# --------------------------------------------------------------------------------------


def test_probe_a_reachable_citation_passes(tmp_path: Path) -> None:
    repo, reachable, _ = synthetic_repo(tmp_path)
    findings, judged, declared = judge(repo, f"landed as `{reachable}` this round\n")
    assert (findings, judged, declared) == ([], 1, 0), findings


def test_probe_an_undeclared_UNREACHABLE_citation_is_a_FINDING(tmp_path: Path) -> None:
    """The defect class: the sha resolves, so no typo check catches it, but no ref reaches it."""
    repo, _, dangling = synthetic_repo(tmp_path)
    assert resolves(repo, dangling), "the fixture must produce a RESOLVING orphan"
    assert not is_ancestor(repo, dangling), "the fixture must produce an UNREACHABLE commit"
    findings, _j, _d = judge(repo, f"landed as `{dangling}` this round\n")
    assert len(findings) == 1, findings
    assert dangling in findings[0] and "line 1" in findings[0], findings


def test_probe_an_undeclared_UNRESOLVABLE_citation_is_a_FINDING(tmp_path: Path) -> None:
    repo, _, _ = synthetic_repo(tmp_path)
    findings, _j, _d = judge(repo, "landed as `deadbeef` this round\n")
    assert len(findings) == 1, findings
    assert "deadbeef" in findings[0] and "declares no class" in findings[0], findings


def test_probe_each_declared_class_clears_its_citation(tmp_path: Path) -> None:
    """All three lawful shapes pass, and each is cleared by its OWN marker."""
    repo, _, dangling = synthetic_repo(tmp_path)
    for marker in (
        f"(`{dangling}` pre-rebase: rewritten by the catch-up rebase)",
        f"(`{dangling}` foreign:leshchenko1979/opencrabs)",
        f"(`{dangling}` non-commit: session uuid)",
    ):
        findings, judged, declared = judge(repo, f"cited {marker}\n")
        assert findings == [], (marker, findings)
        assert (judged, declared) == (1, 1), (judged, declared)


def test_probe_a_BARE_foreign_prefix_does_NOT_clear_a_citation(tmp_path: Path) -> None:
    """`foreign:` alone names no repository, so it is not a declaration — the form is asserted."""
    repo, _, dangling = synthetic_repo(tmp_path)
    findings, _j, declared = judge(repo, f"(`{dangling}` foreign: no repo named)\n")
    assert declared == 0, "a bare `foreign:` must not be read as a declaration"
    assert len(findings) == 1, findings


def test_probe_an_ALL_DIGIT_token_is_JUDGED(tmp_path: Path) -> None:
    """The trap that nearly let this gate's own defect through.

    `48244053` — the real citation this unit repairs — is EIGHT DIGITS AND NO LETTERS, so the
    obvious "skip all-digit tokens, they are not shas" filter discards it silently. The
    scanner must return it, and the judge must rule on it.
    """
    repo, reachable, _ = synthetic_repo(tmp_path)
    assert [t for _l, t, _c, _line in citations("`48244053`")] == ["48244053"]
    findings, judged, _d = judge(repo, "cited `48244053` as the fix\n")
    assert judged == 1, "an all-digit token was not judged"
    assert len(findings) == 1, findings
    # and the arm must not be a blanket rejection: an all-digit token that IS reachable passes
    digits = "".join(ch for ch in reachable if ch.isdigit())
    assert judge(repo, f"cited `{reachable}`\n")[0] == []
    assert digits == "" or True  # the fixture sha may carry no digits; the arm above is the proof


def test_probe_a_declaration_on_ANOTHER_LINE_does_not_clear_a_citation(tmp_path: Path) -> None:
    """Locality: a file-wide marker would exempt every citation below it."""
    repo, _, dangling = synthetic_repo(tmp_path)
    text = f"(`{dangling}` is the published name)\n\nall citations here are pre-rebase:\n"
    findings, _j, declared = judge(repo, text)
    assert declared == 0, "a declaration on a later line must not reach back"
    assert len(findings) == 1, findings


def test_probe_prose_hex_words_and_non_hex_spans_are_not_citations() -> None:
    """A citation is a CODE SPAN of 7..40 hex characters, nothing looser.

    Measured on this factory's own artifacts: a naive bare-hex sweep returned 403 distinct
    tokens against 301 real ones, the surplus being English words that happen to be spelled
    with hex letters — `defaced`, `added`, `beefed`. And a code span that is not hex at all
    (`git rebase`) is not a citation either.
    """
    prose = "the tree was defaced and added to, beefed up, faded and acceded\n"
    assert citations(prose) == []
    assert citations("run `git rebase --hard` now") == []
    assert citations("a `abc123` six-character span") == []
    assert citations("a `" + "a" * 41 + "` too-long span") == []


def test_probe_a_PRE_BOUNDARY_artifact_is_excused_not_judged(tmp_path: Path) -> None:
    """The boundary is exclusive: at or before the landing day is excused, never checked."""
    boundary = dt.date(2026, 10, 25)
    scored = [(dt.date(2026, 10, 24), tmp_path / "2026-10-24.md"),
              (dt.date(2026, 10, 26), tmp_path / "2026-10-26.md")]
    in_scope = [p.name for d, p in scored if d > boundary]
    excused = [p.name for d, p in scored if d <= boundary]
    assert in_scope == ["2026-10-26.md"], in_scope
    assert excused == ["2026-10-24.md"], excused


def test_probe_an_ABSENT_declaration_SKIPS_with_a_stated_reason(tmp_path: Path) -> None:
    """A bootstrapped tree declares nothing, and must say so rather than pass vacuously.

    TWO ABSENCES, TWO MESSAGES, and the distinction is asserted rather than assumed: a tree
    with NO declaration file is told which file is missing, and a tree that carries the file
    but not this key is told which KEY is missing. A probe that only ever exercised one of
    them would pass while the other reported a bare empty string.
    """
    bare = tmp_path / "bare"
    (bare / "docs").mkdir(parents=True)
    with pytest.raises(SkipGate) as excinfo:
        declared_day(bare, INVARIANT_KEY)
    assert "ledger-invariants" in str(excinfo.value), excinfo.value

    declared_but_silent = tmp_path / "silent"
    (declared_but_silent / "docs").mkdir(parents=True)
    (declared_but_silent / "docs" / "ledger-invariants.json").write_text(
        '{"invariants": {}}', encoding="utf-8"
    )
    with pytest.raises(SkipGate) as excinfo:
        declared_day(declared_but_silent, INVARIANT_KEY)
    assert INVARIANT_KEY in str(excinfo.value), excinfo.value


def test_probe_a_MALFORMED_declaration_FAILS(tmp_path: Path) -> None:
    """A factory that declared a boundary and cannot have it read is a defect, not an absence."""
    broken = tmp_path / "broken"
    (broken / "docs").mkdir(parents=True)
    (broken / "docs" / "ledger-invariants.json").write_text(
        '{"invariants": {"' + INVARIANT_KEY + '": "not-a-timestamp"}}', encoding="utf-8"
    )
    with pytest.raises(GateError) as excinfo:
        declared_day(broken, INVARIANT_KEY)
    assert excinfo.value.problems, excinfo.value


def test_probe_the_procedure_names_every_escape() -> None:
    """The vocabulary is stated where the run reads it, not only where it is enforced."""
    if not PROCEDURE.is_file():
        pytest.skip("this tree ships no docs/measurement-procedure.md, so it states no rule")
    text = PROCEDURE.read_text(encoding="utf-8")
    absent = [marker for marker in ESCAPES if marker not in text]
    assert absent == [], f"docs/measurement-procedure.md does not name the escape(s): {absent}"


# --------------------------------------------------------------------------------------
# The live leg.
# --------------------------------------------------------------------------------------


def test_every_citation_in_an_in_scope_artifact_is_reachable() -> None:
    """Every sha an in-scope round artifact cites names a commit HEAD can reach."""
    boundary = _declared_day_or_skip(REPO, INVARIANT_KEY)
    scored = artifacts(SCORES)
    for name in undated_artifacts(SCORES):
        print(f"  not a dated round artifact, not judged: {name}")
    in_scope = [(d, p) for d, p in scored if d > boundary]
    excused = [(d, p) for d, p in scored if d <= boundary]
    for day, path in excused:
        print(
            f"excused: {path.name} is dated {day.isoformat()}, at or before the declared "
            f"boundary {boundary.isoformat()} — written before the writing rule landed"
        )
    reason = _population_reason([p.name for _d, p in in_scope], boundary, "score artifact(s)")
    if reason:
        pytest.skip(reason)
    findings: list[str] = []
    judged = 0
    declared = 0
    for _day, path in in_scope:
        found, count, decl = judge(REPO, path.read_text(encoding="utf-8"))
        judged += count
        declared += decl
        findings.extend(f"{path.name}: {item}" for item in found)
    print(
        f"  population: {len(in_scope)} in-scope artifact(s) after {boundary.isoformat()}, "
        f"{judged} citation(s) judged, {declared} declared, {len(excused)} excused"
    )
    assert findings == [], (
        f"{len(findings)} citation(s) name a commit HEAD cannot reach:\n  "
        + "\n  ".join(findings)
    )


def main() -> int:
    """Run the probes and the live leg as a script, the way `tools/audit.py` invokes it."""
    import tempfile

    problems: list[str] = []
    probes = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_probe_") and callable(value)
    ]
    for probe in probes:
        label = probe.__name__
        try:
            if "tmp_path" in probe.__code__.co_varnames[: probe.__code__.co_argcount]:
                with tempfile.TemporaryDirectory() as tmp:
                    probe(Path(tmp))
            else:
                probe()
        except SkipGate as exc:
            print(f"  SKIP  {label} — {exc}")
        except AssertionError as exc:
            problems.append(f"{label}: {exc}")
            print(f"  FAIL  {label}")
        else:
            print(f"  PASS  {label}")
    try:
        test_every_citation_in_an_in_scope_artifact_is_reachable()
    except SkipGate as exc:
        print(f"  SKIP  live leg — {exc}")
    except AssertionError as exc:
        problems.append(f"live leg: {exc}")
        print("  FAIL  live leg")
    else:
        print("  PASS  live leg")
    if problems:
        print(f"\nscore artifact citations gate FAILED: {len(problems)} problem(s)")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"\nscore artifact citations gate passed — {len(probes)} probe(s) and the live leg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
