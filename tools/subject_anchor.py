#!/usr/bin/env python3
"""Subject-matter anchor resolver: which declared artefact grounds each factory's D1?

Origin: board #149 (owner ruling 2026-09-26, amending board #20's implemented form). The
rubric's D1 criterion resolved against a PATH — `docs/subject/` — so four of six surveyed
factories sat at the consulting floor on the absence of a directory NAME while all four
carried real domain grounding somewhere else. A criterion that resolves against a path
measures a filename. This instrument resolves against the **declared accepted set** stated
in `docs/quality-criteria.md`, and prints, per factory, WHICH artefact resolved — the half
of the ruling (done criterion 4) that stops a floor being indistinguishable from a missing
file. That indistinguishability is how the defect stayed invisible for four runs.

The set is READ, never restated. The members, their patterns and the score mapping are
parsed out of the rubric, so moving a threshold in the rubric moves this instrument's
verdict with no second edit (the #154 discipline). Where no rubric exists — a bootstrapped
factory keeps its criteria in the template project, not locally — the set is UNDECLARED and
the instrument says so; it does not fall back to a copy that could drift from the
declaration.

The score is the COUNT of members that resolved, mapped through the rubric's own table.
A member resolves at the FIRST declared pattern that exists in the factory's own repo or in
the directory its declared skill lives in. A root that does not exist is reported by NAME,
never silently skipped: an unreached root and a root that genuinely holds nothing are
different facts and must not render the same way.

REPORTED, never asserted. Every figure here is a property of the INSTANT it was read (a
factory's tree moves), so the live reading is printed and no gate asserts on it; the gate
that guards this instrument is fixture-driven and offline by construction.

Run:  python3 tools/subject_anchor.py [--manifest P] [--rubric P] [--json]
Exit: 0 a reading was produced (including the undeclared-rubric skip)
      2 the rubric EXISTS and will not parse -- a RED, not a skip (#164's split)
      3 the manifest was named and could not be read -- no verdict, never a clean one
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUBRIC = ("docs/quality-criteria.md",)
MANIFEST = ("registry/fleet.json", "registry/fleet.example.json")

# `| **Controlled vocabulary** | the domain's nouns | `ONTOLOGY.md` · `roles/*.md` (≥2) |`
_MEMBER_ROW = re.compile(
    r"^\|\s*\*\*(?P<name>[^*]+)\*\*\s*\|\s*(?P<grounds>[^|]+?)\s*\|\s*(?P<patterns>[^|]+?)\s*\|\s*$"
)
# `| 2–3 | 3 | Measured — ... |`
_SCORE_ROW = re.compile(r"^\|\s*(?P<lo>\d+)(?:\s*[–-]\s*(?P<hi>\d+))?\s*\|\s*(?P<score>\d+)\s*\|")
# `The set has **4** members, and the score is the count that resolved:`
_MEMBER_MAX = re.compile(r"set has \*\*(\d+)\*\*\s+members")
_PATTERN_MIN = re.compile(r"^(?P<pattern>.+?)\s*\(\s*[≥>=]+\s*(?P<min>\d+)\s*\)$")
_SEPARATOR = "·"
# The accepted set lives in ONE section, and the parse is HEADING-SCOPED rather than
# row-shaped: a row-shaped predicate over the whole document matches fifteen rows -- every
# `| **Name** | x | y |` table in the rubric qualifies -- and a member count of 15 is
# exactly the confident wrong number a scoped predicate exists to prevent.
_SECTION = re.compile(r"^### The declared accepted set\b.*$", re.MULTILINE)


@dataclass(frozen=True)
class Member:
    """One facet of domain grounding, and the declared patterns that satisfy it."""

    name: str
    grounds: str
    patterns: tuple[tuple[str, int], ...]  # (pattern, minimum matches)


@dataclass
class Resolution:
    """What one factory's tree holds, and which artefact proved it."""

    slug: str
    resolved: dict[str, str] = field(default_factory=dict)  # member -> artefact
    unresolved: list[str] = field(default_factory=list)
    unreached: list[str] = field(default_factory=list)  # roots that do not exist
    roots: list[str] = field(default_factory=list)
    score: int | None = None


def parse_section(text: str) -> str | None:
    """The body of the declared-accepted-set section, or None when the heading is absent.

    An absent heading is reported AS an absent heading, never as an empty set: the two are
    different facts and must not render the same way.
    """
    m = _SECTION.search(text)
    if m is None:
        return None
    rest = text[m.end():]
    stop = re.search(r"^#{1,3} ", rest, re.MULTILINE)
    return rest[: stop.start()] if stop else rest


def parse_members(text: str) -> tuple[list[Member], list[str]]:
    """`(members, problems)` — the accepted set, READ from the rubric.

    A PRESENT rubric whose member table will not parse is a problem, not an empty set: the
    two render identically otherwise, and that is exactly the failure this instrument exists
    to stop (#164's split).
    """
    body = parse_section(text)
    if body is None:
        return [], ["the declared-accepted-set section is absent -- no heading matched"]
    members: list[Member] = []
    for line in body.splitlines():
        m = _MEMBER_ROW.match(line.strip())
        if m is None:
            continue
        patterns: list[tuple[str, int]] = []
        for raw in m.group("patterns").split(_SEPARATOR):
            raw = raw.strip()
            if not raw:
                continue
            minimum = 1
            mn = _PATTERN_MIN.match(raw)
            if mn is not None:
                raw, minimum = mn.group("pattern").strip(), int(mn.group("min"))
            raw = raw.strip().strip("`").strip()
            if raw:
                patterns.append((raw, minimum))
        if patterns:
            members.append(Member(m.group("name").strip(), m.group("grounds").strip(), tuple(patterns)))

    problems: list[str] = []
    if not members:
        problems.append("the accepted-set member table did not parse -- no member row matched")
    return members, problems


def parse_score_map(text: str) -> tuple[list[tuple[int, int, int]], list[str]]:
    """`(ranges, problems)` where each range is `(lo, hi, score)`, scoped to the same section."""
    body = parse_section(text)
    if body is None:
        return [], ["the declared-accepted-set section is absent -- no score map to read"]
    ranges: list[tuple[int, int, int]] = []
    for line in body.splitlines():
        m = _SCORE_ROW.match(line.strip())
        if m is None:
            continue
        lo = int(m.group("lo"))
        hi = int(m.group("hi")) if m.group("hi") else lo
        ranges.append((lo, hi, int(m.group("score"))))
    problems: list[str] = []
    if not ranges:
        problems.append("the score mapping table did not parse -- no row matched")
    return ranges, problems


def parse_member_max(text: str) -> tuple[int | None, list[str]]:
    """The declared size of the set, so the mapping's top band can be checked against it."""
    body = parse_section(text)
    m = _MEMBER_MAX.search(body) if body is not None else None
    if m is None:
        return None, ["the declared set size did not parse -- 'The set has **N** members' is absent"]
    return int(m.group(1)), []



def score_for(count: int, ranges: list[tuple[int, int, int]]) -> int | None:
    """The score a resolved-member count earns, through the rubric's own mapping."""
    for lo, hi, score in ranges:
        if lo <= count <= hi:
            return score
    return None


def roots_of(factory: dict) -> list[str]:
    """Every directory this factory's grounding may live in: its repo, and its skill's dir."""
    roots: list[str] = []
    repo = factory.get("repo")
    if repo:
        roots.append(str(repo))
    skill = factory.get("skill")
    if skill and str(skill).endswith(".md"):
        parent = str(Path(skill).parent)
        if parent not in roots:
            roots.append(parent)
    return roots


def _brace_expand(pattern: str) -> list[str] | None:
    """`{a,b}.md` -> `['a.md', 'b.md']`; None when the pattern carries no brace group."""
    m = re.match(r"^(?P<pre>[^{]*)\{(?P<alts>[^}]+)\}(?P<post>.*)$", pattern)
    if m is None:
        return None
    return [f"{m.group('pre')}{alt}{m.group('post')}" for alt in m.group("alts").split(",")]


def resolve_member(member: Member, roots: list[str]) -> tuple[str, str] | None:
    """`(pattern, artefact)` for the FIRST declared pattern that resolves, else None.

    A pattern is one of: a literal path, a glob, or a brace group whose alternatives are
    counted against the pattern's declared minimum. A glob is likewise counted, so a
    directory that exists but is empty does not resolve a member that demands one file.
    """
    for pattern, minimum in member.patterns:
        for root in roots:
            if not Path(root).is_dir():
                continue
            alts = _brace_expand(pattern)
            if alts is not None:
                hits = [a for a in alts if Path(root, a).is_file()]
                if len(hits) >= minimum:
                    return pattern, str(Path(root, hits[0]))
                continue
            if any(ch in pattern for ch in "*?["):
                hits = sorted(glob.glob(str(Path(root, pattern)), recursive=True))
                hits = [h for h in hits if Path(h).is_file()]
                if len(hits) >= minimum:
                    return pattern, hits[0]
                continue
            if Path(root, pattern).is_file():
                return pattern, str(Path(root, pattern))
    return None


def resolve_factory(
    factory: dict, members: list[Member], ranges: list[tuple[int, int, int]]
) -> Resolution:
    """One factory's resolution: which member resolved at which artefact."""
    res = Resolution(slug=str(factory.get("slug") or factory.get("display_name") or "?"))
    res.roots = roots_of(factory)
    for root in res.roots:
        if not Path(root).is_dir():
            res.unreached.append(root)
    for member in members:
        hit = resolve_member(member, res.roots)
        if hit is None:
            res.unresolved.append(member.name)
        else:
            res.resolved[member.name] = hit[1]
    res.score = score_for(len(res.resolved), ranges)
    return res


def load_manifest(path: Path) -> tuple[list[dict], str | None]:
    """`(factories, problem)` — a named manifest that cannot be read is a problem."""
    if not path.is_file():
        return [], f"{path}: no manifest at this path"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], f"{path}: manifest unreadable ({exc})"
    factories = data.get("factories")
    if not isinstance(factories, list):
        return [], f"{path}: manifest carries no 'factories' list"
    return factories, None


def shown(path: Path) -> str:
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def find_first(candidates: tuple[str, ...]) -> Path | None:
    return next((REPO / c for c in candidates if (REPO / c).is_file()), None)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--manifest", type=Path, default=None)
    ap.add_argument("--rubric", type=Path, default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    rubric = args.rubric or find_first(RUBRIC)
    manifest = args.manifest or find_first(MANIFEST)

    if rubric is None or not Path(rubric).is_file():
        print(
            "subject anchor: UNDECLARED -- no docs/quality-criteria.md in this tree, so the "
            "accepted set is not stated here and nothing can be resolved against it. A "
            "bootstrapped factory keeps its criteria in the template project; this is a "
            "stated skip, never a clean read."
        )
        return 0

    text = rubric.read_text(encoding="utf-8")
    members, problems = parse_members(text)
    ranges, score_problems = parse_score_map(text)
    declared_max, max_problems = parse_member_max(text)
    problems += score_problems + max_problems
    if declared_max is not None and declared_max != len(members):
        problems.append(
            f"the rubric declares {declared_max} member(s) and the table carries {len(members)}"
        )
    if problems:
        for p in problems:
            print(f"  FAIL {shown(rubric)}: {p}")
        return 2

    if manifest is None:
        print(
            "subject anchor: no fleet manifest in this tree, so there is no population to "
            "resolve against -- the accepted set parsed clean and nothing was examined."
        )
        return 0

    factories, problem = load_manifest(manifest)
    if problem is not None:
        print(f"subject anchor: NO VERDICT -- {problem}")
        return 3
    if not factories:
        print(f"subject anchor: NO VERDICT -- {shown(manifest)} names no factory")
        return 3

    results = [resolve_factory(f, members, ranges) for f in factories]

    if args.json:
        print(
            json.dumps(
                {
                    "rubric": shown(rubric),
                    "manifest": shown(manifest),
                    "members": [m.name for m in members],
                    "member_count": len(members),
                    "score_map": [{"lo": lo, "hi": hi, "score": s} for lo, hi, s in ranges],
                    "factories": [
                        {
                            "slug": r.slug,
                            "roots": r.roots,
                            "unreached": r.unreached,
                            "resolved": r.resolved,
                            "unresolved": r.unresolved,
                            "members_resolved": len(r.resolved),
                            "score": r.score,
                        }
                        for r in results
                    ],
                },
                indent=2,
            )
        )
        return 0

    width = max(len(r.slug) for r in results)
    print(f"subject anchor -- accepted set READ from {shown(rubric)} ({len(members)} members)")
    print()
    print(f"  {'factory':<{width}}  {'members':>8}  {'score':>5}  resolved artefact")
    print(f"  {'-' * width}  {'-' * 8}  {'-' * 5}  {'-' * 40}")
    for r in results:
        score = "?" if r.score is None else str(r.score)
        if r.resolved:
            first_member = next(iter(r.resolved))
            detail = f"{first_member}: {r.resolved[first_member]}"
            extra = f" (+{len(r.resolved) - 1} more)" if len(r.resolved) > 1 else ""
        else:
            detail = "NOTHING RESOLVED -- no declared artefact exists"
            extra = ""
        print(f"  {r.slug:<{width}}  {len(r.resolved):>4}/{len(members):<3}  {score:>5}  {detail}{extra}")
    print()
    for r in results:
        if r.unresolved:
            print(f"  {r.slug}: unresolved -- {', '.join(r.unresolved)}")
        for root in r.unreached:
            print(f"  {r.slug}: root UNREACHED -- {root}")
    print()
    print(
        f"  {len(results)} factory row(s) examined against {len(members)} declared member(s); "
        "a reading of THIS instant, reported and never asserted."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())