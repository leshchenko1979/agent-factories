#!/usr/bin/env python3
r"""Gate: the subject-anchor resolver READS the accepted set, and REPORTS rather than judges.

WHAT THIS GATE UPHOLDS. Board #149's ruling (ledger n=1158) makes the D1 subject-matter
anchor a **declared accepted set** stated in `docs/quality-criteria.md`, and done criterion 4
is the load-bearing half: the measurement run must print WHICH artefact resolved per factory,
because a floor that reads the same as a missing file is how the defect stayed invisible for
four runs. `tools/subject_anchor.py` is the instrument behind that clause; this file is its
gate. A declared anchor with no instrument is dead text, and an instrument with no gate is a
reading nobody can check (P29).

WHY EVERY PROBE IS A FIXTURE, AND THE LIVE FLEET IS NEVER JUDGED. The instrument's live
figures are properties of an INSTANT: a factory's tree moves, and a member that resolves
today may not tomorrow. An acceptance criterion pinned to any of them would fail a CORRECT
instrument, so reproducibility is asserted HERE against synthetic rubrics and synthetic
manifests -- deterministic, offline, no live fleet -- and the live reading is REPORTED by the
instrument instead. This gate therefore reads no database and shells out to nothing.

THE PROBES, each aimed at the shape it forbids:

  (i)   THE SET IS READ, NEVER RESTATED. A synthetic rubric declaring two members must parse
        as exactly those two, by name. A hardcoded member list passes every live check and
        fails here -- which is what the mutation control drives.
  (ii)  THE PARSE IS SECTION-SCOPED. The rubric carries a dozen other `| **Name** | x | y |`
        tables; an unscoped row predicate matched FIFTEEN rows on the live document during
        this instrument's own construction, and a member count of 15 is a confident wrong
        number of exactly the kind a scoped predicate exists to prevent.
  (iii) THE SCORE MAPPING IS READ, not restated -- two different declared mappings over the
        same resolved count must give two different scores.
  (iv)  FIRST DECLARED PATTERN WINS, and a pattern's declared MINIMUM is enforced: a directory
        that exists but holds no file resolves nothing, and a member demanding two files is
        not satisfied by one.
  (v)   A FACTORY THAT RESOLVES NOTHING IS NAMED, member by member -- never rendered as a
        clean row. That is the #164 split: absence is reported, not swallowed.
  (vi)  AN UNREACHED ROOT IS NAMED, distinctly from a root that exists and holds nothing.
  (vii) A PRESENT RUBRIC THAT WILL NOT PARSE IS A RED (rc 2); an ABSENT one is a STATED SKIP
        (rc 0). Two different facts that must never render the same way.
  (viii) A MANIFEST NAMED AND UNREADABLE IS NO VERDICT (rc 3), never a clean read.
  (ix)  THE DECLARED SET SIZE IS CROSS-CHECKED against the member table, so a table that
        lost a row fails loudly rather than silently scoring against a shorter set.
  (x)   THE LIVE READING IS REPORTED, NEVER ASSERTED: the run's exit code does not depend on
        any measured figure, only on whether a reading could be produced at all.

Run:  python3 tests/test_subject_anchor.py [--mutation-control]
Exit: 0 every probe passed, 1 one did not.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INSTRUMENT = REPO / "tools" / "subject_anchor.py"
HEADING = "### The declared accepted set — what D1 resolves against"
_LOAD_SEQ = 0


def load_instrument(path: Path = INSTRUMENT):
    """Load the instrument BY PATH.

    The module is registered in `sys.modules` BEFORE `exec_module`, and the name is unique
    per load: the instrument declares `@dataclass(frozen=True)`, and `dataclasses._is_type`
    resolves `cls.__module__` through `sys.modules` while the class body is being processed.
    A spec-only load therefore raises `AttributeError: 'NoneType' object has no attribute
    '__dict__'` -- found by running it, not by reading it.
    """
    global _LOAD_SEQ
    _LOAD_SEQ += 1
    name = f"subject_anchor_under_test_{_LOAD_SEQ}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def check(name: str, condition: bool, detail: str, failures: list) -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}")
    if not condition:
        failures.append(f"{name} — {detail}")


def rubric_text(members, score_rows, declared_max: int, decoys: bool = True) -> str:
    """A synthetic rubric: the accepted-set section, wrapped in DECOY tables on both sides."""
    head = "# Quality criteria for an agent factory\n\n**Status: v0.5 — ADOPTED.**\n\n"
    if decoys:
        head += (
            "## Two products, two sets of measures\n\n"
            "| **The output** | Did the work land? | The customer of the factory |\n"
            "|---|---|---|\n\n"
        )
    body = f"{HEADING}\n\n| Member | What it grounds | Declared patterns |\n|---|---|---|\n"
    for name, grounds, patterns in members:
        body += f"| **{name}** | {grounds} | {patterns} |\n"
    body += f"\nThe set has **{declared_max}** members, and the score is the count that resolved:\n\n"
    body += "| Members resolved | Score | Reading |\n|---|---|---|\n"
    for lo, hi, score, reading in score_rows:
        body += f"| {lo}" + (f"–{hi}" if hi != lo else "") + f" | {score} | {reading} |\n"
    if decoys:
        body += (
            "\n## Mandatory at bootstrap\n\n"
            "| **Day-1 Mandatory** | Written law and vocabulary | Compounding errors |\n"
            "|---|---|---|\n\n"
            "| Band | Score | Reading |\n|---|---|---|\n"
            "| **Provisional** | 0–25% (0–19) | Runs on the founder's head |\n"
        )
    return head + body


DEFAULT_MEMBERS = [
    ("Controlled vocabulary", "the domain's nouns", "`ONTOLOGY.md`"),
    ("Domain model", "entities and schemas", "`docs/domain-model.md`"),
]
DEFAULT_SCORES = [(0, 0, 1, "Ad-hoc"), (1, 1, 2, "Defined"), (2, 3, 3, "Measured"), (4, 4, 4, "Self-correcting")]


def _stage(tmp: Path, name: str) -> Path:
    d = tmp / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _run_main(mod, argv: list) -> tuple:
    """`(rc, stdout)` for an in-process `main()` call; an exception is reported as its own rc."""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = mod.main(argv)
    except SystemExit as exc:  # pragma: no cover - argparse only
        rc = int(exc.code or 0)
    except Exception as exc:  # a crash is a failure, and it must be visible as one
        rc = f"EXC:{type(exc).__name__}: {exc}"
    return rc, buf.getvalue()


# --- probes, each parameterised by the module under test ----------------------


def probe_set_is_read(mod, tmp: Path, failures: list) -> None:
    d = _stage(tmp, "read")
    (d / "rubric.md").write_text(rubric_text(DEFAULT_MEMBERS, DEFAULT_SCORES, 2), encoding="utf-8")
    members, problems = mod.parse_members((d / "rubric.md").read_text(encoding="utf-8"))
    names = [m.name for m in members]
    check(
        "the set is READ from the document, by name",
        not problems and names == ["Controlled vocabulary", "Domain model"],
        f"parsed {names!r} with problems {problems!r}",
        failures,
    )


def probe_parse_is_section_scoped(mod, tmp: Path, failures: list) -> None:
    d = _stage(tmp, "scoped")
    (d / "rubric.md").write_text(rubric_text(DEFAULT_MEMBERS, DEFAULT_SCORES, 2), encoding="utf-8")
    members, _ = mod.parse_members((d / "rubric.md").read_text(encoding="utf-8"))
    check(
        "the parse is SECTION-SCOPED -- decoy tables outside it are not members",
        len(members) == 2,
        f"parsed {len(members)} member(s) from a document carrying decoy "
        f"`| **Name** | x | y |` tables -- an unscoped predicate counts them",
        failures,
    )


def probe_score_map_is_read(mod, tmp: Path, failures: list) -> None:
    d = _stage(tmp, "scores")
    live = [(0, 0, 1, "a"), (1, 1, 2, "b"), (2, 3, 3, "c"), (4, 4, 4, "d")]
    other = [(0, 0, 0, "a"), (1, 1, 1, "b"), (2, 4, 2, "c")]
    (d / "live.md").write_text(rubric_text(DEFAULT_MEMBERS, live, 2), encoding="utf-8")
    (d / "other.md").write_text(rubric_text(DEFAULT_MEMBERS, other, 2), encoding="utf-8")
    live_ranges, _ = mod.parse_score_map((d / "live.md").read_text(encoding="utf-8"))
    other_ranges, _ = mod.parse_score_map((d / "other.md").read_text(encoding="utf-8"))
    check(
        "the score mapping is READ, not restated -- two declarations, two answers",
        mod.score_for(3, live_ranges) == 3
        and mod.score_for(4, live_ranges) == 4
        and mod.score_for(4, other_ranges) == 2,
        f"live 3->{mod.score_for(3, live_ranges)} (want 3), live 4->{mod.score_for(4, live_ranges)} "
        f"(want 4), other 4->{mod.score_for(4, other_ranges)} (want 2)",
        failures,
    )


def probe_first_pattern_and_minimum(mod, tmp: Path, failures: list) -> None:
    d = _stage(tmp, "patterns")
    root = _stage(d, "factory")
    (root / "first.md").write_text("x", encoding="utf-8")
    (root / "second.md").write_text("x", encoding="utf-8")
    (root / "empty").mkdir(exist_ok=True)
    (root / "one").mkdir(exist_ok=True)
    (root / "one" / "a.md").write_text("x", encoding="utf-8")
    (root / "two").mkdir(exist_ok=True)
    (root / "two" / "a.md").write_text("x", encoding="utf-8")
    (root / "two" / "b.md").write_text("x", encoding="utf-8")
    roots = [str(root)]

    order = mod.Member("Order", "g", (("second.md", 1), ("first.md", 1)))
    check(
        "the FIRST declared pattern wins",
        (mod.resolve_member(order, roots) or ("", ""))[0] == "second.md",
        f"resolved {mod.resolve_member(order, roots)} -- the first declared pattern is second.md",
        failures,
    )

    empty = mod.Member("Empty", "g", (("empty/*.md", 1),))
    check(
        "a directory that exists but holds no file resolves NOTHING",
        mod.resolve_member(empty, roots) is None,
        f"resolved {mod.resolve_member(empty, roots)} from an empty directory",
        failures,
    )

    needs_two = mod.Member("Two", "g", (("two/*.md", 2),))
    needs_three = mod.Member("Three", "g", (("two/*.md", 3),))
    check(
        "a declared MINIMUM is enforced",
        mod.resolve_member(needs_two, roots) is not None and mod.resolve_member(needs_three, roots) is None,
        f"minimum 2 -> {mod.resolve_member(needs_two, roots)}, minimum 3 -> "
        f"{mod.resolve_member(needs_three, roots)} (want resolved / None)",
        failures,
    )


def probe_nothing_resolved_is_named(mod, tmp: Path, failures: list) -> None:
    d = _stage(tmp, "empty-factory")
    root = _stage(d, "factory")
    (d / "rubric.md").write_text(rubric_text(DEFAULT_MEMBERS, DEFAULT_SCORES, 2), encoding="utf-8")
    (d / "fleet.json").write_text(
        json.dumps({"factories": [{"slug": "bare", "repo": str(root)}]}), encoding="utf-8"
    )
    rc, out = _run_main(mod, ["--rubric", str(d / "rubric.md"), "--manifest", str(d / "fleet.json")])
    check(
        "a factory that resolves NOTHING is named, member by member",
        rc == 0 and "Controlled vocabulary" in out and "Domain model" in out and "0/2" in out,
        f"rc={rc!r}, output did not name both unresolved members:\n{out}",
        failures,
    )


def probe_unreached_root_is_named(mod, tmp: Path, failures: list) -> None:
    d = _stage(tmp, "unreached")
    (d / "rubric.md").write_text(rubric_text(DEFAULT_MEMBERS, DEFAULT_SCORES, 2), encoding="utf-8")
    (d / "fleet.json").write_text(
        json.dumps({"factories": [{"slug": "ghost", "repo": str(d / "no-such-tree")}]}), encoding="utf-8"
    )
    rc, out = _run_main(mod, ["--rubric", str(d / "rubric.md"), "--manifest", str(d / "fleet.json")])
    check(
        "an UNREACHED root is named, not silently skipped",
        rc == 0 and "UNREACHED" in out and "no-such-tree" in out,
        f"rc={rc!r}, output did not name the unreached root:\n{out}",
        failures,
    )


def probe_absent_rubric_is_a_stated_skip(mod, tmp: Path, failures: list) -> None:
    d = _stage(tmp, "absent")
    rc, out = _run_main(mod, ["--rubric", str(d / "absent.md"), "--manifest", str(d / "fleet.json")])
    check(
        "an ABSENT rubric is a STATED SKIP (rc 0), never a clean read",
        rc == 0 and "UNDECLARED" in out and "skip" in out,
        f"rc={rc!r}, output did not state the skip:\n{out}",
        failures,
    )


def probe_unparseable_rubric_is_red(mod, tmp: Path, failures: list) -> None:
    d = _stage(tmp, "unparseable")
    (d / "rubric.md").write_text(f"# Criteria\n\n{HEADING}\n\nNo member table here.\n", encoding="utf-8")
    (d / "fleet.json").write_text(json.dumps({"factories": []}), encoding="utf-8")
    rc, out = _run_main(mod, ["--rubric", str(d / "rubric.md"), "--manifest", str(d / "fleet.json")])
    check(
        "a PRESENT rubric that will not parse is a RED (rc 2)",
        rc == 2 and "FAIL" in out,
        f"rc={rc!r} (want 2), output:\n{out}",
        failures,
    )


def probe_unreadable_manifest_is_no_verdict(mod, tmp: Path, failures: list) -> None:
    d = _stage(tmp, "no-manifest")
    (d / "rubric.md").write_text(rubric_text(DEFAULT_MEMBERS, DEFAULT_SCORES, 2), encoding="utf-8")
    rc, out = _run_main(mod, ["--rubric", str(d / "rubric.md"), "--manifest", str(d / "gone.json")])
    check(
        "a manifest named and unreadable is NO VERDICT (rc 3)",
        rc == 3 and "NO VERDICT" in out,
        f"rc={rc!r} (want 3), output:\n{out}",
        failures,
    )


def probe_declared_size_is_cross_checked(mod, tmp: Path, failures: list) -> None:
    d = _stage(tmp, "size-drift")
    (d / "rubric.md").write_text(rubric_text(DEFAULT_MEMBERS, DEFAULT_SCORES, 4), encoding="utf-8")
    (d / "fleet.json").write_text(json.dumps({"factories": []}), encoding="utf-8")
    rc, out = _run_main(mod, ["--rubric", str(d / "rubric.md"), "--manifest", str(d / "fleet.json")])
    check(
        "the declared set SIZE is cross-checked against the table",
        rc == 2 and "4" in out and "2" in out,
        f"rc={rc!r} (want 2) -- a rubric declaring 4 members over a 2-row table:\n{out}",
        failures,
    )


def probe_live_reading_is_reported(mod, tmp: Path, failures: list) -> None:
    """The live tree is READ, never judged: only the ability to produce a reading is asserted."""
    rc, out = _run_main(mod, [])
    check(
        "the live reading is REPORTED, never asserted (rc depends on no measured figure)",
        rc == 0 and out.strip() != "",
        f"rc={rc!r}, output:\n{out}",
        failures,
    )
    print("  ---- live reading (reported, not judged) ----")
    for line in out.rstrip().splitlines():
        print(f"  | {line}")


PROBES = (
    probe_set_is_read,
    probe_parse_is_section_scoped,
    probe_score_map_is_read,
    probe_first_pattern_and_minimum,
    probe_nothing_resolved_is_named,
    probe_unreached_root_is_named,
    probe_absent_rubric_is_a_stated_skip,
    probe_unparseable_rubric_is_red,
    probe_unreadable_manifest_is_no_verdict,
    probe_declared_size_is_cross_checked,
    probe_live_reading_is_reported,
)

# Each mutation names the shape it reintroduces and the source text it rewrites. A probe set
# that cannot fail is not a probe set, so the control drives every mutation against a COPY of
# the instrument and requires each one to break at least one probe.
MUTATIONS: tuple[tuple[str, str, str], ...] = (
    (
        "hardcoded-set",
        "    body = parse_section(text)\n"
        '    if body is None:\n'
        '        return [], ["the declared-accepted-set section is absent -- no heading matched"]',
        '    return [Member("Hardcoded", "x", (("ONTOLOGY.md", 1),))], []\n'
        "    body = parse_section(text)\n"
        '    if body is None:\n'
        '        return [], ["unreachable"]',
    ),
    (
        "unscoped-parse",
        "    m = _SECTION.search(text)\n"
        "    if m is None:\n"
        "        return None\n"
        "    rest = text[m.end():]\n"
        '    stop = re.search(r"^#{1,3} ", rest, re.MULTILINE)\n'
        "    return rest[: stop.start()] if stop else rest",
        "    return text if _SECTION.search(text) else None",
    ),
    (
        "restated-score-map",
        "    for lo, hi, score in ranges:\n"
        "        if lo <= count <= hi:\n"
        "            return score\n"
        "    return None",
        "    return min(4, 1 + count)",
    ),
    (
        "pattern-order-reversed",
        "    for pattern, minimum in member.patterns:",
        "    for pattern, minimum in reversed(member.patterns):",
    ),
    (
        "unreached-root-silent",
        "        if not Path(root).is_dir():\n            res.unreached.append(root)",
        "        pass",
    ),
    (
        "absent-rubric-is-red",
        '            "stated skip, never a clean read."\n        )\n        return 0',
        '            "stated skip, never a clean read."\n        )\n        return 2',
    ),
)


def run_probes(mod, tmp: Path) -> list:
    failures: list = []
    for probe in PROBES:
        probe(mod, tmp, failures)
    return failures


def mutation_control(tmp: Path) -> list:
    """Every mutation must break at least one probe. A mutation that breaks NOTHING is the finding."""
    problems: list = []
    source = INSTRUMENT.read_text(encoding="utf-8")
    for name, old, new in MUTATIONS:
        if old not in source:
            problems.append(
                f"{name}: the source text this mutation rewrites is ABSENT -- the mutation is "
                "decorative and proves nothing about the probe set"
            )
            continue
        work = _stage(tmp, f"mutant-{name}")
        target = work / "subject_anchor.py"
        target.write_text(source.replace(old, new, 1), encoding="utf-8")
        try:
            mutant = load_instrument(target)
        except Exception as exc:
            problems.append(f"{name}: the mutant would not load ({exc})")
            continue
        failures = []
        with contextlib.redirect_stdout(io.StringIO()):
            failures = run_probes(mutant, _stage(work, "fixtures"))
        print(f"  {'BITES' if failures else 'SILENT'}  mutation {name}: {len(failures)} probe failure(s)")
        if not failures:
            problems.append(
                f"{name}: the mutation survived every probe -- the probe set cannot see the "
                "shape it reintroduces"
            )
    return problems


def main() -> int:
    argv = [a for a in sys.argv[1:] if a != "--mutation-control"]
    print("subject-anchor gate — probes")
    failures: list = []
    with tempfile.TemporaryDirectory(prefix="subject-anchor-gate-") as td:
        tmp = Path(td)
        failures += run_probes(load_instrument(), _stage(tmp, "live"))
        if "--mutation-control" in sys.argv:
            print()
            print("subject-anchor gate — mutation control")
            failures += mutation_control(_stage(tmp, "mutants"))

    if failures:
        print()
        for line in failures:
            print(f"  FAIL {line}")
        print(f"subject-anchor gate FAILED ({len(failures)} failure(s))")
        return 1
    print()
    print(
        f"subject-anchor gate passed ({len(PROBES)} probe(s), 0 failure(s)); the live fleet "
        "reading above is REPORTED, never judged."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
