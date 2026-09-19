#!/usr/bin/env python3
r"""Gate: no rework entry cites a revision by a MOVING-HEAD-relative form.

Origin: #86, ruled at ledger `n=558`. A stash-then-checkout probe ran a gate at
`HEAD~1` and read a `docs/` drift as PRE-EXISTING; a peer lane's commit landed
between the stash and the checkout, so `HEAD~1` was the lane's OWN commit rather
than its parent. The verdict was wrong in the direction that EXONERATES the change
under investigation. The law (`SKILL.md` section 8) now says an attribution to a
revision must name an ABSOLUTE sha; this is its mechanical half over the one
durable trace an investigation leaves, `evidence/rework.md` — the probe itself is
transient, its record is not.

PREDICATE, stated with its count in this gate's own output, and stated WITH ITS
SCOPE because scope is where a predicate of this shape goes wrong.

A **revision citation** is a revision ROOT carrying a caret/tilde SUFFIX, or a
rootless suffix standing alone as a token: `HEAD~`, `HEAD~N`, `HEAD^`, `@~`, `@^`,
and a bare `~N`/`^N`. A root is `HEAD`, `@`, or a hex object name of 7..40 chars.

The predicate is NOT "the cell contains a tilde". Measured on the live log before
this gate was written: `evidence/rework.md` carried 4 tildes and 7 carets, and only
6 of those 11 characters sat in a revision citation. The other five are a
home-directory path (`~/.opencrabs/profiles/...`) and four REGEXES
(`^##\s+(P\d+)\s+—` twice, `^##\s+(P\d+)\b`, `^#\d+$`). A gate matching the
character reds the live audit on its first run while reporting nothing true; the
discriminator is *is the token a revision?*, never *does the cell contain a tilde?*.

TWO TIERS, and the second is PRINTED rather than failed — that is the scope
statement. `<absolute-sha>^` and `<absolute-sha>~N` are NOT moving-HEAD forms: the
root is a named object, so the expression resolves to the same commit on every
machine and at every later HEAD. They are therefore OBSERVED and COUNTED, never
flagged. The ruling's own rationale reaches only the moving form — *resolved
against a MOVING HEAD in a shared worktree* — and flagging a deterministic
expression would assert more than the law says. The live log demonstrates the
distinction: entry `#87` writes that `21bcbac^` is the work commit `4ae1ffd` — it
cites the parent form AND names the absolute sha it resolves to, which is the
remedy the law prescribes. Reading the ruling's fifth item ("a bare caret or tilde
suffix") as the ROOTLESS form is what keeps the two tiers consistent; a rooted
suffix is a different token class. If HQ rules the rooted form barred as well, this
is a one-line change to `classify` and the count is already printed.

EXEMPTIONS ARE FACTORY DATA, NEVER SOURCE IN THIS FILE. This gate is paired
byte-identically with `TEMPLATE/tests/test_rework_relative_revision.py`, so a
pre-gate instance named inline would ship to every new factory — #78's ruling, and
the shape `docs/ledger-no-shrink-exemptions.json` already takes. The live
exemptions are in `docs/rework-relative-revision-exemptions.json`; the skeleton is
`TEMPLATE/docs/rework-relative-revision-exemptions.example.json`; absent or empty
means none, which is the shipped state of a new factory. Every matched exemption is
printed on EVERY run, so `clean` and `excused` are never the same output.

An exemption that matches nothing is a FAILURE, exactly as in
`tests/test_ledger_no_shrink.py`: an exemption that silently excuses nothing
inflates the count, and this file is a debt ledger rather than an archive. So an
entry whose quotation has been rewritten is removed in the same change that
rewrites it — the one step that keeps the list equal to the debt.

A tree with no `evidence/rework.md` SKIPS with a stated reason and exits 0: the
rework log is BOOTSTRAP-created (`TEMPLATE/BOOTSTRAP.md`), so `TEMPLATE/` — the
tree this gate ships to — legitimately has none. That is the #78 class, and a
byte-paired gate that REDs the tree it ships to is the defect that class names.

Run:  python3 tests/test_rework_relative_revision.py
Exit: 0 no governed citation outside the declared exemptions, 1 otherwise.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# The Entries parser is IMPORTED, never re-implemented: a second reader of the same
# table is how this gate and `tests/test_rework.py` come to disagree about which rows
# exist, which is the drift the audit's own reader is bound to for the same reason.
sys.path.insert(0, str(REPO / "tests"))
import test_rework  # noqa: E402 — the path above is set deliberately before this line

REWORK = REPO / "evidence" / "rework.md"
EXEMPTIONS_PATH = "docs/rework-relative-revision-exemptions.json"
COLUMNS = test_rework.COLUMNS

HEX = r"[0-9a-fA-F]{7,40}"
SUFFIX = r"(?:~{1,2}\d*|\^{1,2}\d*)"
# The lookarounds keep each match a TOKEN: a path segment or a word carrying the same
# characters is not a citation.
MOVING_CITATION = re.compile(rf"(?<![0-9A-Za-z_/])(?:HEAD|@){SUFFIX}(?![0-9A-Za-z_])")
ROOTED_CITATION = re.compile(rf"(?<![0-9A-Za-z_/]){HEX}{SUFFIX}(?![0-9A-Za-z_])")
# A rootless suffix standing alone as a whole token. The boundary class is whitespace or
# a backtick, so the `~` of a home-directory path and the `^` of a regex anchor cannot
# match, and `x^2` is excluded by the same lookbehind.
ROOTLESS_CITATION = re.compile(r"(?<![^\s`])[~^]\d*(?![^\s`])")

PREDICATE = (
    "no entry in evidence/rework.md cites a revision by a moving-HEAD-relative form "
    "(HEAD~, HEAD~N, HEAD^, @~, @^, or a rootless ~N/^N) outside the declared exemptions"
)

def citations_in(cell: str) -> list[tuple[str, str]]:
    """`(form, kind)` for every revision citation in a cell; kind is `moving`/`rooted`."""
    found: list[tuple[str, str]] = []
    found.extend((m.group(0), "moving") for m in MOVING_CITATION.finditer(cell))
    found.extend((m.group(0), "rooted") for m in ROOTED_CITATION.finditer(cell))
    found.extend((m.group(0), "moving") for m in ROOTLESS_CITATION.finditer(cell))
    return found

def entry_citations(text: str) -> tuple[list[dict], int, int]:
    """`(citations, entry rows, cells)` — the population this gate reports every run."""
    body = test_rework.section_body(text)
    if body is None:
        return [], 0, 0
    rows = test_rework.entry_rows(body)
    found: list[dict] = []
    cells = 0
    for line, values in rows:
        subject = values[COLUMNS.index("Subject")] if len(values) > COLUMNS.index("Subject") else ""
        for index, cell in enumerate(values):
            column = COLUMNS[index] if index < len(COLUMNS) else f"column {index + 1}"
            cells += 1
            for form, kind in citations_in(cell):
                found.append(
                    {"line": line, "subject": subject, "column": column,
                     "form": form, "kind": kind}
                )
    return found, len(rows), cells

def load_exemptions(repo: Path) -> tuple[list[dict], list[str]]:
    """The factory's declared exemptions, or `([], [])` when it has declared none.

    Absent or empty is the shipped state of a new factory. Anything MALFORMED is a
    problem, never a silent pass: an exemption list that quietly fails to load is
    indistinguishable from no exemptions, the vacuous-pass shape this repo forbids.
    """
    path = repo / EXEMPTIONS_PATH
    if not path.is_file():
        return [], []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], [f"{EXEMPTIONS_PATH} exists but cannot be read: {exc}"]
    if not isinstance(data, dict) or not isinstance(data.get("exemptions"), list):
        return [], [f"{EXEMPTIONS_PATH}: expected a JSON object with an 'exemptions' list"]

    entries: list[dict] = []
    problems: list[str] = []
    keys = ("subject", "column", "form", "date", "reason")
    for index, raw in enumerate(data["exemptions"], 1):
        if not isinstance(raw, dict):
            problems.append(f"{EXEMPTIONS_PATH}: exemption {index} is not an object")
            continue
        missing = [key for key in keys if not str(raw.get(key, "")).strip()]
        if missing:
            problems.append(f"{EXEMPTIONS_PATH}: exemption {index} is missing {', '.join(missing)}")
            continue
        entries.append({key: str(raw[key]).strip() for key in keys})
    return entries, problems

def classify(
    citations: list[dict], exemptions: list[dict]
) -> tuple[list[dict], list[dict], list[dict]]:
    """`(problems, excused, stale)` — governed citations split by the declared exemptions."""
    problems: list[dict] = []
    excused: list[dict] = []
    matched = [0] * len(exemptions)
    for cite in citations:
        if cite["kind"] != "moving":
            continue
        hit = next(
            (
                index
                for index, entry in enumerate(exemptions)
                if entry["subject"] == cite["subject"]
                and entry["column"] == cite["column"]
                and entry["form"] == cite["form"]
            ),
            None,
        )
        if hit is None:
            problems.append(cite)
        else:
            matched[hit] += 1
            excused.append({**cite, "date": exemptions[hit]["date"], "reason": exemptions[hit]["reason"]})
    stale = [entry for entry, count in zip(exemptions, matched) if count == 0]
    return problems, excused, stale

def report(citations: list[dict], entries: int, cells: int, exemptions: list[dict]) -> str:
    """The population line — printed on EVERY run, clean or not."""
    governed = [c for c in citations if c["kind"] == "moving"]
    rooted = [c for c in citations if c["kind"] == "rooted"]
    return (
        f"predicate — {PREDICATE}; examined {entries} entry row(s) across {cells} cell(s), "
        f"{len(citations)} revision citation(s): {len(governed)} governed (moving-HEAD), "
        f"{len(rooted)} observed (absolute-sha root, deterministic); "
        f"{len(exemptions)} exemption(s) declared"
    )

# --------------------------------------------------------------------------- probes

def synthetic_row(root_cause: str = "a mechanism", resolution: str = "abc1234") -> str:
    """One well-formed Entries row whose Root cause and Resolution cells are injectable."""
    return (
        f"| 2026-09-19 | a probe | a defect | {root_cause} | {resolution} | "
        f"a gate | #1 |"
    )

def synthetic_doc(*rows: str) -> str:
    return (
        "## Entries\n\n"
        f"{test_rework.HEADER}\n{test_rework.SEPARATOR}\n" + "\n".join(rows) + "\n"
    )

def run_doc(text: str, exemptions: list[dict] | None = None) -> tuple[list[dict], list[dict], list[dict]]:
    citations, _, _ = entry_citations(text)
    return classify(citations, list(exemptions or []))

def check(name: str, condition: bool, detail: str, failures: list[str]) -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}")
    if not condition:
        failures.append(f"{name} — {detail}")

def probe(name: str, root_cause: str, want_problem: bool, failures: list[str]) -> None:
    problems, _, _ = run_doc(synthetic_doc(synthetic_row(root_cause=root_cause)))
    check(
        name,
        bool(problems) == want_problem,
        f"problems={[p['form'] for p in problems]}",
        failures,
    )

def main() -> int:
    if not REWORK.is_file():
        print(
            f"SKIP: no {REWORK.relative_to(REPO)} in this tree — the rework log is "
            f"BOOTSTRAP-created, so a tree that has not bootstrapped yet has nothing to judge"
        )
        return 0

    text = REWORK.read_text(encoding="utf-8")
    citations, entries, cells = entry_citations(text)
    exemptions, declaration_problems = load_exemptions(REPO)
    failures: list[str] = list(declaration_problems)

    print("rework relative-revision gate — an attribution names an absolute sha (#86)")
    print(f"  {report(citations, entries, cells, exemptions)}")

    if entries == 0:
        print("FAIL  the Entries table yielded no rows — the gate examined nothing")
        return 1

    governed_problems, excused, stale = classify(citations, exemptions)
    for entry in excused:
        print(
            f"  excused: {entry['subject']} / {entry['column']} cites `{entry['form']}` "
            f"({entry['date']}) — {entry['reason']}"
        )
    stale_problems = [
        f"exemption {entry['subject']} / {entry['column']} / `{entry['form']}` matches no "
        f"citation — a stale exemption excuses nothing; remove it"
        for entry in stale
    ]

    print("\n  the gate's own probes")
    probe("a fixture citing HEAD~1 is caught", "ran the gate at `HEAD~1`", True, failures)
    probe("a fixture citing HEAD^ is caught", "diffed against `HEAD^`", True, failures)
    probe("a fixture citing HEAD~ is caught", "the lane used `HEAD~`", True, failures)
    probe("a fixture citing @~ is caught", "read `@~` as the parent", True, failures)
    probe(
        "a fixture citing a 40-char sha passes",
        "verified at `0123456789abcdef0123456789abcdef01234567`",
        False, failures,
    )
    probe(
        "a fixture citing an absolute-sha parent form passes — it is deterministic",
        "read the blob at `21bcbac^`",
        False, failures,
    )
    probe(
        "a home-directory path is not a revision",
        "`~/.opencrabs/profiles/{{PROFILE}}/skills/{{NAME}}`",
        False, failures,
    )
    probe(
        "a regex anchor is not a revision",
        "the heading pattern `^##\\s+(P\\d+)\\s+—` is loose",
        False, failures,
    )

    rooted, _, _ = entry_citations(
        synthetic_doc(synthetic_row(resolution="read the blob at `21bcbac^`"))
    )
    check(
        "an absolute-sha parent form is OBSERVED, not dropped",
        [c["kind"] for c in rooted] == ["rooted"],
        f"kinds={[c['kind'] for c in rooted]}",
        failures,
    )

    exempt = [{
        "subject": "#1", "column": "Root cause", "form": "HEAD~1",
        "date": "2026-09-19", "reason": "a probe fixture",
    }]
    _, excused_probe, stale_probe = run_doc(
        synthetic_doc(synthetic_row(root_cause="ran the gate at `HEAD~1`")), exempt
    )
    check(
        "an exempted pre-gate instance is excused, never folded into clean",
        len(excused_probe) == 1 and not stale_probe,
        f"excused={len(excused_probe)} stale={len(stale_probe)}",
        failures,
    )
    _, _, stale_probe = run_doc(synthetic_doc(synthetic_row(root_cause="a mechanism")), exempt)
    check(
        "an exemption that matches nothing is STALE — a failure, never silence",
        len(stale_probe) == 1,
        f"stale={len(stale_probe)}",
        failures,
    )

    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(tmp) / "docs"
        tree.mkdir(parents=True)
        (tree / Path(EXEMPTIONS_PATH).name).write_text("{not json", encoding="utf-8")
        _, broken = load_exemptions(Path(tmp))
    check(
        "a malformed exemption list is a problem, never a silent pass",
        len(broken) == 1,
        f"problems={broken}",
        failures,
    )

    print()
    if governed_problems or stale_problems or failures:
        print(
            f"rework relative-revision gate FAILED: {len(governed_problems)} problem(s), "
            f"{len(stale_problems)} stale exemption(s), {len(failures)} probe failure(s)"
        )
        for problem in governed_problems:
            print(
                f"  - {problem['subject']} / {problem['column']} cites "
                f"`{problem['form']}` — name the absolute sha the revision resolves to"
            )
        for problem in stale_problems:
            print(f"  - {problem}")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("rework relative-revision gate passed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
