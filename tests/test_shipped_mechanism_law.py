#!/usr/bin/env python3
r"""Gate: the shipped law STATES the preconditions of the mechanisms the kit ships.

Origin (board #170, ruled by HQ). TEMPLATE/ ships the patrol's receipt legs, the shared
field predicate and their tests, and its law stated NONE of their preconditions: measured
2026-09-28, `TEMPLATE/SKILL.md.tmpl` carried 0 occurrences of `receipt_subject`,
`duty=completed`, `retired_logs` and `named after ITS OWN JOB`, against 1/1/1/2 in the live
law. A factory bootstrapped from the template therefore inherits both legs with none of the
rules that make them work, and section 11 names the shape: a mechanism whose precondition
is undocumented is a permanent silent exclusion.

WHY NO GATE COULD SEE IT. `skills/meta-factory/SKILL.md` and `TEMPLATE/SKILL.md.tmpl` are
deliberately NOT byte-paired - they are independent documents that happen to share a
structure, with different section numbering (this factory's section 11 is State, the
template's is Escalation). So `tests/test_template_sync.py` reports clean over them by
construction, and `tests/test_law_structure.py` asserts section-numbering contiguity only,
never clause presence. Law-vs-mechanism drift in TEMPLATE/ is invisible to every gate that
existed before this one.

WHAT IT ASSERTS, AND WHY BOTH SIDES. The declaration in
`docs/shipped-mechanism-law.json` names, per entry, the MECHANISM that needs a clause, the
TOKEN the mechanism keys on, and the CLAUSE PHRASE the shipped law must carry. This gate
asserts BOTH ends:
  * the TOKEN is present in the shipped mechanism's own source, so a declaration cannot go
    stale when the mechanism changes underneath it; and
  * the CLAUSE PHRASE is present in the shipped law, so a mechanism cannot ship with its
    precondition unstated.
One-sided assertions are how this class hid for 3d19h: the mechanism existed and nothing
asked what it required.

REPO-SIDE ONLY, and the reason is stated rather than assumed. This gate asserts a property
of the tree the deliver HANDS OUT, so it catches the drift where it is CREATED. It is not a
PAIRS entry (there is no TEMPLATE half to mirror) and not in `registry/kit.json` (whose
entries are all TEMPLATE/-prefixed). Precedent: `tests/test_shipped_audit_runs.py`, which
runs the shipped tree's own audit for the same reason.

A CLAUSE IS NAMED BY ITS PHRASE, NEVER BY A SECTION NUMBER - the two law files number
differently, so a section number resolves to a DIFFERENT clause in each tree (#184, the
kit's own citation law).
"""
import json
import pathlib
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
DECLARATION = REPO / "docs" / "shipped-mechanism-law.json"


def load_declaration(path):
    """The declared table, or an exception naming what could not be read.

    A declaration that will not parse is a BROKEN input, never an absent one: a gate that
    read it as "nothing declared" would report clean over a table it never read.
    """
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def evaluate(repo, declaration):
    """Return (problems, population).

    `problems` is a list of strings, each NAMING the entry it judged. `population` counts
    what was examined, so a clean verdict is distinguishable from an empty one.
    """
    problems = []
    declared_laws = declaration.get("law")
    laws = [declared_laws] if isinstance(declared_laws, str) else list(declared_laws or [])
    law_rel = laws[0] if len(laws) == 1 else laws
    entries = declaration.get("required_clauses") or []

    if not entries:
        return (
            ["the declaration carries 0 required clause(s) - a table that declares nothing "
             "has judged nothing, and its clean verdict would be indistinguishable from a "
             "verified one"],
            {"entries": 0, "law": law_rel},
        )

    if not laws:
        return (
            ["the declaration names no law file - the clause set cannot be judged, and a "
             "law that names nothing is not a law with no missing clauses"],
            {"entries": len(entries), "law": law_rel},
        )

    law_texts = []
    for rel in laws:
        law_path = repo / str(rel)
        if not law_path.is_file():
            return (
                [f"the declaration names the law file {rel!r}, which is ABSENT from this "
                 f"tree - the clause set cannot be judged, and an unreadable law is not a "
                 f"law with no missing clauses"],
                {"entries": len(entries), "law": law_rel},
            )
        body = law_path.read_text(encoding="utf-8")
        if not body.strip():
            return (
                [f"the law file {rel!r} is EMPTY - every clause would read as missing, and "
                 f"an empty law is not a law that states nothing"],
                {"entries": len(entries), "law": law_rel},
            )
        law_texts.append(body)
    law_text = "\n".join(law_texts)

    population = {
        "entries": len(entries),
        "law": law_rel,
        "mechanisms": set(),
        "clauses_present": 0,
        "clauses_missing": 0,
    }

    for entry in entries:
        mechanism = entry.get("mechanism") or "<unnamed mechanism>"
        clause = entry.get("clause") or "<unnamed clause>"
        token = entry.get("token") or ""
        population["mechanisms"].add(mechanism)

        mech_path = repo / "TEMPLATE" / mechanism
        if not mech_path.is_file():
            problems.append(
                f"{mechanism}: NAMED ABSENT from this tree - the declaration names a "
                f"mechanism the kit does not ship, so its clause {clause!r} is asserted "
                f"over nothing and the entry is stale"
            )
            continue

        mech_text = mech_path.read_text(encoding="utf-8")
        if token and token not in mech_text:
            problems.append(
                f"{mechanism}: the declared token {token!r} is NOT in the shipped "
                f"mechanism's own source - the declaration has drifted from the code it "
                f"describes, so its clause {clause!r} may no longer be the one required"
            )

        if clause in law_text:
            population["clauses_present"] += 1
        else:
            population["clauses_missing"] += 1
            problems.append(
                f"{mechanism}: the shipped law does NOT state {clause!r} - a member "
                f"inherits this mechanism with its precondition unstated, which section 11 "
                f"names as a permanent silent exclusion"
            )

    return problems, population


def run_self_probes():
    """Every arm driven from a fixture, never from prose that happens to be present."""
    results = []

    def check(name, condition, detail=""):
        results.append((name, bool(condition), detail))

    def fixture(entries, law_text="A law body.\n", mechanisms=None, laws=None,
                extra_laws=None):
        """A throwaway repo with a declaration, a law and the named mechanisms."""
        root = pathlib.Path(tempfile.mkdtemp(prefix="shipped-law-"))
        (root / "docs").mkdir(parents=True, exist_ok=True)
        (root / "TEMPLATE" / "tools").mkdir(parents=True, exist_ok=True)
        for rel, text in (mechanisms or {}).items():
            target = root / "TEMPLATE" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        law = root / "TEMPLATE" / "SKILL.md.tmpl"
        law.parent.mkdir(parents=True, exist_ok=True)
        law.write_text(law_text, encoding="utf-8")
        for rel, text in (extra_laws or {}).items():
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        declaration = {"law": laws if laws is not None else "TEMPLATE/SKILL.md.tmpl",
                       "required_clauses": entries}
        return root, declaration

    entry = {
        "mechanism": "tools/thing.py",
        "leg": "leg",
        "token": "TOKEN_A",
        "clause": "A clause the law must state",
        "why": "because",
    }

    # P1 - a clause the law DOES state passes, and the population counts it.
    root, decl = fixture([entry], law_text="body. A clause the law must state. more.",
                         mechanisms={"tools/thing.py": "TOKEN_A = 1\n"})
    problems, population = evaluate(root, decl)
    check("P1 a stated clause passes and is counted",
          not problems and population["clauses_present"] == 1, f"problems={problems}")

    # P2 - THE BITE: a clause the law does NOT state reds, NAMING the entry.
    root, decl = fixture([entry], law_text="body with no such clause.",
                         mechanisms={"tools/thing.py": "TOKEN_A = 1\n"})
    problems, population = evaluate(root, decl)
    check("P2 a MISSING clause reds and NAMES the mechanism and the clause",
          len(problems) == 1 and "tools/thing.py" in problems[0]
          and "A clause the law must state" in problems[0], f"problems={problems}")

    # P3 - the other side: a declared token absent from the mechanism reds.
    root, decl = fixture([entry], law_text="body. A clause the law must state.",
                         mechanisms={"tools/thing.py": "SOMETHING_ELSE = 1\n"})
    problems, _ = evaluate(root, decl)
    check("P3 a token absent from the shipped mechanism reds (the declaration has drifted)",
          any("TOKEN_A" in p and "drifted" in p for p in problems), f"problems={problems}")

    # P4 - a declaration naming a mechanism the kit does not ship is a NAMED ABSENCE.
    root, decl = fixture([entry], law_text="body. A clause the law must state.",
                         mechanisms={})
    problems, _ = evaluate(root, decl)
    check("P4 an absent mechanism is NAMED, never a silent pass",
          any("NAMED ABSENT" in p for p in problems), f"problems={problems}")

    # P5 - NON-VACUITY: an empty declaration judged nothing and must not read clean.
    root, decl = fixture([], law_text="body.")
    problems, population = evaluate(root, decl)
    check("P5 an empty declaration reds rather than reporting a clean empty population",
          len(problems) == 1 and population["entries"] == 0, f"problems={problems}")

    # P6 - an absent law file is a failure, never a clean run over zero clauses.
    root, decl = fixture([entry], mechanisms={"tools/thing.py": "TOKEN_A = 1\n"})
    (root / "TEMPLATE" / "SKILL.md.tmpl").unlink()
    problems, _ = evaluate(root, decl)
    check("P6 an absent law file reds rather than reading as no missing clauses",
          any("ABSENT" in p for p in problems), f"problems={problems}")

    # P7 - a BROKEN declaration is a failure, not an empty table.
    try:
        load_declaration(root / "docs" / "does-not-exist.json")
        check("P7 an unreadable declaration raises rather than reading as empty", False)
    except OSError:
        check("P7 an unreadable declaration raises rather than reading as empty", True)

    # P8 - `law` is a LIST: a clause stated by the SECOND named file passes. This is the
    # board #302 shape - the template law body split, so its clause tail ships in its own
    # file and the clause set is asserted over every file the declaration names.
    root, decl = fixture([entry], law_text="body with no such clause.",
                         mechanisms={"tools/thing.py": "TOKEN_A = 1\n"},
                         laws=["TEMPLATE/SKILL.md.tmpl", "TEMPLATE/state.md.tmpl"],
                         extra_laws={"TEMPLATE/state.md.tmpl": "A clause the law must state."})
    problems, population = evaluate(root, decl)
    check("P8 a clause stated by the SECOND of several named law files passes",
          not problems and population["clauses_present"] == 1, f"problems={problems}")

    # P9 - a list naming an ABSENT law file still reds, NAMING it: a multi-file law set
    # cannot be satisfied by the files that happen to exist.
    root, decl = fixture([entry], law_text="A clause the law must state.",
                         mechanisms={"tools/thing.py": "TOKEN_A = 1\n"},
                         laws=["TEMPLATE/SKILL.md.tmpl", "TEMPLATE/gone.md.tmpl"])
    problems, _ = evaluate(root, decl)
    check("P9 an absent member of a multi-file law set reds and NAMES it",
          any("TEMPLATE/gone.md.tmpl" in p and "ABSENT" in p for p in problems),
          f"problems={problems}")

    return results


def main():
    print("shipped-mechanism-law gate: the shipped law STATES its mechanisms' preconditions")
    results = run_self_probes()
    failed = [name for name, ok, _ in results if not ok]
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'} - {name}" + ("" if ok else f"  [{detail}]"))

    try:
        declaration = load_declaration(DECLARATION)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"  FAIL - the declaration {DECLARATION.name} could not be read: {exc}")
        return 1

    problems, population = evaluate(REPO, declaration)
    print(
        f"  population: {population['entries']} declared clause(s) over "
        f"{len(population.get('mechanisms', []))} mechanism(s), judged against "
        f"{population['law']} - {population.get('clauses_present', 0)} present, "
        f"{population.get('clauses_missing', 0)} missing"
    )
    for problem in problems:
        print(f"  MISSING  {problem}")

    if failed or problems:
        print(
            f"shipped-mechanism-law gate FAILED: {len(failed)} probe failure(s), "
            f"{len(problems)} clause problem(s)"
        )
        return 1
    print(
        "shipped-mechanism-law gate ok: every declared clause is stated by the shipped "
        "law and anchored on a token the mechanism carries"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
