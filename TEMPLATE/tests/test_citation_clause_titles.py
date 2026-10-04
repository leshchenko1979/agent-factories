#!/usr/bin/env python3
r"""Gate: a citation into a per-factory law file names the CLAUSE TITLE, never a section NUMBER.

Origin (issue #184). `TEMPLATE/` ships no `SKILL.md` at all - it ships `SKILL.md.tmpl` -
and each factory's law is authored per tree, so every factory's section numbering differs.
A citation of the form `SKILL.md §11` is therefore a coordinate into a document the
receiving tree does not carry, and it resolves to a DIFFERENT clause in each tree. The
harm is measured, not theoretical: miidas HQ received a brief asserting "your law §11
prescribes a remedy" while its §11 is its Verification law and its SKILL.md contains no
occurrence of "repair" at all. The kit's own code was violating the kit's own citation
law (meta-factory SKILL.md, "Verdicts and claims" - "a reference to another document
NAMES that document; a bare section number resolves only inside the file that holds it").

The property, in two legs
-------------------------
Leg 1, the DEFECT: no `SKILL.md §<digits>` anywhere in the scoped source set.
Leg 2, the CONVENTION: every `§` in the scoped source set is followed by a clause TITLE
that RESOLVES in this repo's law corpus, or the citation NAMES a document (in which case
the number is that document's own to keep). A title is resolved by PREFIX: the text after
`§` must START WITH a known heading title, because a citation continues past the title
into prose ("§Verdicts and claims already says verdict verbs need a receipt").

What this gate cannot do, stated rather than implied
---------------------------------------------------
It resolves a title against the law documents THIS REPO CARRIES (`skills/*/SKILL.md`,
`TEMPLATE/SKILL.md.tmpl`, `TEMPLATE/roles/*.md`). A citation whose named document is not
carried here (a member-side skill file, an ops brain file) cannot be resolved offline: the
gate reports it as an EXEMPTION with that reason and on every run, never as a pass, so
"clean" and "exempt" are never the same output. It also excludes the law files themselves
from the scan - a document citing its OWN numbered sections is the one case the scheme
exists to serve, and `TEMPLATE/SKILL.md.tmpl` legitimately does so throughout.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OWN = Path(__file__).resolve()
# This gate's own two halves. A predicate has to NAME the pattern it forbids — score the
# prose that does so, and the check can never describe its own subject without failing it.
SELF_NAMES = {OWN.name}

# Interpolation of the scope: source instruments and gates. `evidence/` -- the ledger -- is
# outside this scope by a directory boundary, and NOT by the reason that excludes prose: a
# ledger ROW numbers no sections of its own, so every `§N` it carries is a citation into
# another document. Judging that is the ledger's OWN leg, which lives with the ledger's gate
# set (`docs/instruments/ledger.md` section 5). Docs are the surface the prose reason covers:
# they may number their own sections. Neither reason moves a path into `SCOPE_DIRS` -- this
# gate keeps ONE population and ONE predicate (#262, ruled at ledger `n=2246`).
SCOPE_DIRS = ("tools", "tests", "TEMPLATE/tools", "TEMPLATE/tests")
SOURCE_SUFFIXES = (".py", "")  # extensionless executables ship too (`tools/questions`)
SKIP_DIRS = {"__pycache__", ".git"}
# The law corpus a citation may resolve against: every law document this repo carries.
LAW_GLOBS = (
    "skills/*/SKILL.md",
    "TEMPLATE/*.tmpl",
    "TEMPLATE/*.md",
    "TEMPLATE/roles/*.md",
    "ONTOLOGY.md",
)

SECTION = re.compile(r"§")
SKILL_NUMBERED = re.compile(r"SKILL\.md\s*§\s*\d")
HEADING = re.compile(r"^#{1,6}\s+(?:\d+\.\s*)?(.+?)\s*$")
# A document named on the same line, BEFORE the marker: a markdown file.
DOC_ON_LINE = re.compile(r"([A-Za-z0-9_./-]+\.md)")


def doc_titles(path: Path) -> set[str]:
    """Every section title one document carries."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        return set()
    out: set[str] = set()
    for line in lines:
        m = HEADING.match(line)
        if m:
            out.add(m.group(1).strip())
    return out


def law_corpus() -> dict[str, set[str]]:
    """{document basename: {titles}} over every law document this repo carries."""
    corpus: dict[str, set[str]] = {}
    for pattern in LAW_GLOBS:
        for p in REPO.glob(pattern):
            if p.is_file():
                corpus.setdefault(p.name, set()).update(doc_titles(p))
    # A citation may name the law as `SKILL.md` with no path: that names the READER's own
    # law file, so the title must resolve in ANY law file a tree may carry - the template's
    # (which a member's SKILL.md is bootstrapped from) or this repo's own.
    law = set()
    for name in ("SKILL.md", "SKILL.md.tmpl"):
        law |= corpus.get(name, set())
    corpus["SKILL.md"] = law
    return corpus


def member_corpus() -> set[str]:
    """Titles a MEMBER tree actually receives: everything shipped under TEMPLATE/.

    A member's law is bootstrapped from `SKILL.md.tmpl`, so a citation inside a file
    that SHIPS must resolve there. This factory's own law (`skills/*/SKILL.md`) is not
    part of a member's corpus, and citing a title that lives only in it is the same
    defect as citing a section number - the receiving tree cannot resolve it.
    """
    out: set[str] = set()
    for pattern in ("TEMPLATE/*.tmpl", "TEMPLATE/*.md", "TEMPLATE/roles/*.md"):
        for p in REPO.glob(pattern):
            if p.is_file():
                out |= doc_titles(p)
    return out


def shipped_paths() -> set[str]:
    """Paths the kit delivers, read from the manifest that already answers it."""
    m = REPO / "registry" / "kit.json"
    if not m.is_file():
        return set()
    return set(json.loads(m.read_text(encoding="utf-8")).get("files", {}))


def ships(rel: str, manifest: set[str]) -> bool:
    """Does this scanned path's content reach a member tree?"""
    return (rel if rel.startswith("TEMPLATE/") else f"TEMPLATE/{rel}") in manifest


def carried_docs() -> set[str]:
    """Basenames of every markdown document this repo holds (shipped or not)."""
    return {p.name for p in REPO.rglob("*.md*") if ".git" not in p.parts}

# THE PROBES' OWN CARRIED SET, injected rather than read off the ambient tree.
#
# `carried_docs()` answers a question about THE TREE THIS GATE RUNS IN, and the shipped tree
# is not this one: `TEMPLATE/` carries `SKILL.md.tmpl` and no `SKILL.md`, so every probe that
# cites a clause of `SKILL.md` gets its citation EXEMPTED as "not carried by this repo" and
# the probe reads no problem — three probes failed exactly that way, and only in the tree the
# kit ships. A probe's subject is the PREDICATE, so it must supply its own inputs; reading
# the environment makes the probe a statement about where it happens to run.
PROBE_CARRIED = {"SKILL.md", "measurement-procedure.md"}


def scoped_files() -> list[Path]:
    out: list[Path] = []
    for d in SCOPE_DIRS:
        for p in (REPO / d).rglob("*"):
            if not p.is_file():
                continue
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            if p.suffix in SOURCE_SUFFIXES:
                out.append(p)
    return sorted(out)


def citation_problems(
    text: str,
    corpus: dict[str, set[str]],
    carried: set[str],
    member: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    """(problems, exemptions) for one file's text.

    `corpus` maps a law document's basename to the titles it carries; `carried` is every
    markdown document this repo holds, so a citation into a document it does NOT hold is
    reported as an exemption rather than silently passing.
    """
    titles = {t for ts in corpus.values() for t in ts}
    # A shipped file's reader is a MEMBER, so its corpus is the member's, not ours.
    shipped = member is not None
    problems: list[str] = []
    exempt: list[str] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if "§" not in line:
            continue
        if SKILL_NUMBERED.search(line):
            problems.append(
                f"{lineno}: cites `SKILL.md §<number>` — the receiving tree's numbering differs, "
                f"so this names a different clause there: {line.strip()[:90]}"
            )
            continue
        for m in SECTION.finditer(line):
            after = line[m.end():].lstrip()
            if not after:
                problems.append(f"{lineno}: '§' with nothing after it: {line.strip()[:90]}")
                continue
            doc = DOC_ON_LINE.search(line[: m.start()])
            name = doc.group(1).rsplit("/", 1)[-1] if doc else None
            if name and name not in carried:
                exempt.append(
                    f"{lineno}: cites `{name}` — that document is not carried by this repo, so "
                    f"its clause cannot be resolved offline: {line.strip()[:80]}"
                )
                continue
            if after[0].isdigit():
                if name:
                    continue  # a carried document's own numbering is that document's to keep
                problems.append(
                    f"{lineno}: bare `§<number>` with no document named — unresolvable in any "
                    f"other tree: {line.strip()[:90]}"
                )
                continue
            if shipped and (name is None or name in ("SKILL.md", "SKILL.md.tmpl")):
                resolvable = member or set()
            elif name:
                resolvable = corpus.get(name, titles)
            else:
                resolvable = titles
            if not any(after.startswith(t) for t in resolvable):
                if name and not shipped:
                    where = f"`{name}`"
                elif shipped:
                    where = "the law corpus a MEMBER receives (everything under TEMPLATE/)"
                else:
                    where = "this repo's law corpus"
                problems.append(
                    f"{lineno}: `§{after[:60]}` does not start with any clause title carried by "
                    f"{where}"
                )
    return problems, exempt


def scan() -> tuple[list[str], list[str], int, int]:
    """(problems, exemptions, files_examined, citations_examined)."""
    corpus = law_corpus()
    carried = carried_docs()
    member = member_corpus()
    manifest = shipped_paths()
    problems: list[str] = []
    exempt: list[str] = []
    files = 0
    citations = 0
    for path in scoped_files():
        if path.name in SELF_NAMES:
            continue  # a predicate must name the pattern it forbids; see the docstring
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        files += 1
        citations += sum(line.count("§") for line in text.splitlines())
        rel = path.relative_to(REPO)
        p, e = citation_problems(
            text, corpus, carried, member if ships(str(rel), manifest) else None
        )
        problems.extend(f"{rel}: {x}" for x in p)
        exempt.extend(f"{rel}: {x}" for x in e)
    return problems, exempt, files, citations


def probe(
    name: str,
    text: str,
    corpus: dict[str, set[str]],
    want: bool,
    failures: list[str],
    member: set[str] | None = None,
) -> None:
    problems, _ = citation_problems(text, corpus, PROBE_CARRIED, member)
    got = bool(problems)
    if got != want:
        failures.append(f"probe {name!r}: expected problems={want}, got {problems or 'none'}")
    else:
        print(f"  PASS  {name}")


# THE PROBES' OWN CORPUS, for the same reason as PROBE_CARRIED and found the same way: two
# more probes failed only in the shipped tree. They cite clause titles of THIS factory's law
# ("The hard boundary — never do a member's work" is the meta-factory's own), and a title the
# ambient law file does not carry reads as unresolvable. A probe's subject is the PREDICATE —
# "does a citation resolve against the corpus it was given?" — so the probes supply a corpus
# with known contents, and the live scan keeps reading the real one.
PROBE_CORPUS: dict[str, set[str]] = {
    "SKILL.md": {
        "State — every surface has one writer",
        "Verdicts and claims",
        "The hard boundary — never do a member's work",
    },
}


def _probes() -> list[str]:
    failures: list[str] = []
    corpus = PROBE_CORPUS
    probe("a SKILL.md section NUMBER is the defect", "see SKILL.md §11 for the rule", corpus, True, failures)
    probe("a bare section number is the defect", "the residue §11 leaves behind", corpus, True, failures)
    probe("a TITLE that resolves is clean",
          "see SKILL.md §State — every surface has one writer for the table", corpus, False, failures)
    probe("a TITLE that resolves nothing is caught",
          "see SKILL.md §No such clause exists here", corpus, True, failures)
    probe("a citation continues past the title into prose",
          "SKILL.md §Verdicts and claims already says verdict verbs need a receipt", corpus, False, failures)
    probe("a document's own numbering is that document's to keep",
          "obligation `docs/measurement-procedure.md` §5 declares", corpus, False, failures)
    probe(
        "a SHIPPED file may not cite a title only the ORIGIN factory carries",
        "# see SKILL.md \u00a7The hard boundary \u2014 never do a member's work",
        corpus,
        True,
        failures,
        member={"Something else"},
    )
    probe(
        "a NON-shipped file may cite a title only the ORIGIN factory carries",
        "# see SKILL.md \u00a7The hard boundary \u2014 never do a member's work",
        corpus,
        False,
        failures,
        member=None,
    )
    probe("the title must be the HEAD of the citation, not a word inside it",
          "see SKILL.md §the clause named State — every surface has one writer", corpus, True, failures)
    return failures


def main() -> int:
    corpus = law_corpus()
    member = member_corpus()
    manifest = shipped_paths()
    if not corpus:
        print("citation-clause-titles gate FAILED: the law corpus yielded ZERO clause titles — "
              "a predicate that examined nothing has reported nothing")
        return 1

    failures = _probes()
    problems, exempt, files, citations = scan()

    print(f"citation clause-title gate: {files} source file(s), {citations} '§' citation(s) examined")
    print(f"  law corpus: {len(corpus)} law document(s), "
          f"{sum(len(v) for v in corpus.values())} clause title(s); "
          f"{len(member)} in the corpus a MEMBER receives; "
          f"{len(manifest)} shipped path(s)")
    for e in exempt:
        print(f"  exempt: {e}")
    for p in problems:
        print(f"  FAIL  {p}")

    if files == 0 or citations == 0:
        print("citation-clause-titles gate FAILED: the scan examined no citations — "
              "a clean verdict over an empty population is not a verdict")
        return 1
    if problems or failures:
        print(f"citation-clause-titles gate FAILED: {len(problems)} problem(s), {len(failures)} probe failure(s)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"citation-clause-titles gate passed — {citations} citation(s), "
          f"{len(exempt)} exemption(s), 0 problem(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
