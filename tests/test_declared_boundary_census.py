#!/usr/bin/env python3
r"""Gate: the declared-boundary census — a live boundary is found by WHAT a gate READS.

WHY THIS GATE EXISTS (issue #431). A shipped gate that hardcodes this factory's landing
date ships to every member and is read against the MEMBER's ledger, where this factory's
commit history means nothing. Six such literals lived in five byte-paired gates until #428
converted them to declared parameters in `docs/ledger-invariants.json` — and a SEVENTH was
written while #428 sat open. The census that should have caught both cannot be the obvious
one: a sweep for the MARKER a module carries (`grep INVARIANT_LANDED`) enumerates its
population by the very name it is checking, so a boundary spelled anything else is
invisible, and that self-selection IS the defect this gate exists to close.

WHAT IT PINS. The population is enumerated by WHAT a byte-paired module READS. A module is
in the census when it reads live factory data — an `evidence/` path fragment, or the
`ledger_boundary` seam that centralises those paths (post-#428 a gate carries no
`evidence/` literal at all, so the seam is the signal that survives). WITHIN that
population, a MODULE-LEVEL date-like constant consumed by a scope that is NOT a probe is
REPORTED: a boundary that JUDGES live data is reached from the module's judging scopes
(`main`, `evaluate`, its predicates), while a fixture boundary is reached only from probes
and tree-builders. A constant confined to the probe family is out of scope — a probe is the
one place a literal belongs, and it asserts the PREDICATE rather than the factory.

SCOPE, STATED. The predicate reads MODULE-LEVEL constants, never inline literals. Measured
over the live tree (2026-10-07), 53 inline date-like literals sit in non-probe scopes and
every one is fixture data (`_row`, `write_ledger`, `_fragment`), so an inline sweep would
red the audit on its first run while reporting nothing true. The class this gate was
ordered for is the module-level constant, and the gate says so rather than implying a
sweep it does not perform.

THE CONTROLS, and why each is here. A POSITIVE control — a synthetic module reading
`evidence/ledger.jsonl` with a module-level boundary consumed by `main` — must be REPORTED;
without it the gate could pass by reporting nothing at all. A SEAM control does the same
through `ledger_boundary`, because that is how every post-#428 gate reads. A NEGATIVE
control — the same read-set with the constant reached only from the probe family
(`_probe_tree`, `probe_*`) — must NOT be reported, or the census would red on the ten modules that legitimately carry a
fixture boundary. A MARKER-ONLY control — a module carrying a boundary that reads nothing —
must NOT enter the population, which is the read-set rule itself: a census that enumerated
by the marker would report it.

NON-VACUITY. The census PRINTS its population, the number of module-level constants it
examined, and the number consumed outside a probe — so a clean run and an unexamined one
are never the same output (#116). Measured at landing (2026-10-07T17:04Z): 48 modules read
live data, 15 constants examined, 0 consumed outside a probe; the six pre-#428 literals in
five modules are all caught.

BOOTSTRAP. It reads SOURCE, never `evidence/`, so it runs identically in a bootstrapped
factory and in the TEMPLATE tree — which is also why the pairing test below cannot be a
bare `twin.exists()`.

Run:  python3 tests/test_declared_boundary_census.py
Exit: 0 the population was examined and no constant is consumed outside a probe, 1 otherwise.
"""

from __future__ import annotations

import ast
import datetime as dt
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# A date-like VALUE: an ISO-8601 string, or a `date(...)`/`datetime(...)` call of integer
# parts. Both forms are live in the tree — three of the six #428 constants were `dt.date`.
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}:\d{2}Z?)?$")

# A PROBE scope is where a fixture boundary belongs. `test_*` and `probe_*` are legs;
# `_probe_tree` and `_probe_repo` are builders. All three are named, so the test SEARCHES
# (`probe` anywhere, or a `test` prefix) rather than start-anchoring — a start-anchored
# match reads `_probe_tree` as a live scope and false-flags two clean modules.
_PROBE_SCOPE_RE = re.compile(r"(?i)^test|probe")

# What makes a module a READER of live factory data: an `evidence/` path fragment, or the
# `ledger_boundary` seam. A module carrying EITHER is in the population.
_EVIDENCE_SEAM = "ledger_boundary"


def date_like(node: ast.AST) -> str | None:
    """The FORM of a date-like value — `iso`, `date`, `datetime` — or None."""
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and _ISO_RE.match(node.value)
    ):
        return "iso"
    if isinstance(node, ast.Call):
        func = node.func
        name = (
            func.attr
            if isinstance(func, ast.Attribute)
            else (func.id if isinstance(func, ast.Name) else "")
        )
        if (
            name in ("date", "datetime")
            and node.args
            and all(isinstance(arg, ast.Constant) and isinstance(arg.value, int) for arg in node.args)
        ):
            return name
    return None


def read_set(tree: ast.Module) -> tuple[str, ...]:
    """The live-data read signals a module's AST carries, sorted and de-duplicated.

    Two signals, and a module carrying EITHER is a reader: an `evidence/` path fragment it
    names itself, or an import from the `ledger_boundary` seam. The seam is not a
    convenience — #428 moved the read out of the gates and into it, so the post-#428 gates
    carry no `evidence/` literal and a signal set of one would drop them from the census.
    """
    signals: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "evidence/" in node.value or node.value == "evidence":
                signals.add("evidence path")
        elif isinstance(node, ast.ImportFrom) and node.module == _EVIDENCE_SEAM:
            signals.add("ledger_boundary seam")
    return tuple(sorted(signals))


def module_constants(tree: ast.Module) -> dict[str, tuple[int, str]]:
    """Every module-level `NAME = <date-like>` — name -> (lineno, form)."""
    found: dict[str, tuple[int, str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        form = date_like(node.value)
        if form is None:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                found[target.id] = (node.lineno, form)
    return found


def _load_scopes(tree: ast.Module, names: set[str]) -> dict[str, set[str]]:
    """For each name, the enclosing function names that LOAD it (`""` = module level)."""
    scopes: dict[str, set[str]] = {name: set() for name in names}

    def walk(node: ast.AST, scope: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                walk(child, child.name)
            else:
                if (
                    isinstance(child, ast.Name)
                    and isinstance(child.ctx, ast.Load)
                    and child.id in scopes
                ):
                    scopes[child.id].add(scope)
                walk(child, scope)

    walk(tree, "")
    return scopes


def _is_probe(scope: str) -> bool:
    """A named scope in the probe family. Module level (`""`) is NOT a probe."""
    return bool(scope) and bool(_PROBE_SCOPE_RE.search(scope))


def analyse(source: str) -> dict:
    """One module's census: what it READS, its module-level date constants, its defects.

    Pure over the source text — no filesystem, no live state — so the controls below drive
    the same predicate the live tree is judged by rather than a re-implementation of it.
    """
    tree = ast.parse(source)
    constants = module_constants(tree)
    scopes = _load_scopes(tree, set(constants))
    defects: list[dict] = []
    for name, (lineno, form) in sorted(constants.items(), key=lambda item: item[1][0]):
        live = sorted(scope for scope in scopes[name] if not _is_probe(scope))
        if live:
            defects.append({"name": name, "lineno": lineno, "form": form, "scopes": live})
    return {"reads": read_set(tree), "constants": constants, "defects": defects}


def shipped_modules(root: Path) -> list[Path]:
    """The modules under `root/tests` that are SHIPPED.

    In this factory that is every module carrying a byte-paired twin under
    `root/TEMPLATE/tests`. In the TEMPLATE tree there is no nested `TEMPLATE/`, so the tree
    IS the shipped half and every module is in — which is why this cannot be a bare
    `twin.exists()`, and why the gate runs the same in both trees.
    """
    tests = root / "tests"
    twins = root / "TEMPLATE" / "tests"
    if not twins.is_dir():
        return sorted(tests.glob("*.py"))
    return sorted(path for path in tests.glob("*.py") if (twins / path.name).is_file())


# --- the controls: a predicate that has only seen clean input has not been shown to bite

POSITIVE_SOURCE = '''#!/usr/bin/env python3
"""Gate: a synthetic reader with a hardcoded boundary (positive control)."""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "evidence" / "ledger.jsonl"
LANDED = "2026-01-01T00:00:00Z"


def rows():
    return [json.loads(line) for line in LEDGER.read_text().splitlines() if line.strip()]


def main():
    return sum(1 for row in rows() if row["ts"] > LANDED)


def probe_a_row_after_the_boundary_is_judged():
    assert main() >= 0
'''

SEAM_SOURCE = '''#!/usr/bin/env python3
"""Gate: a synthetic reader through the seam (population control)."""
from pathlib import Path

from ledger_boundary import read_rows

REPO = Path(__file__).resolve().parent.parent
LANDED = "2026-01-01T00:00:00Z"


def main():
    return [row for row in read_rows(REPO) if row["ts"] > LANDED]
'''

NEGATIVE_SOURCE = '''#!/usr/bin/env python3
"""Gate: a synthetic reader whose boundary is FIXTURE-LOCAL (negative control)."""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "evidence" / "ledger.jsonl"
_PROBE_BOUNDARY = "2026-01-01T00:00:00Z"


def _probe_tree(root):
    (root / "evidence").mkdir(parents=True, exist_ok=True)
    (root / "evidence" / "ledger.jsonl").write_text(_PROBE_BOUNDARY, encoding="utf-8")
    return root


def probe_a_row_after_the_probe_boundary_is_judged(tmp_path):
    assert _probe_tree(tmp_path)
'''

MARKER_ONLY_SOURCE = '''#!/usr/bin/env python3
"""Gate: a synthetic module carrying a boundary but READING nothing (marker control)."""
_PROBE_BOUNDARY = "2026-01-01T00:00:00Z"


def _build(root):
    (root / "x").write_text(_PROBE_BOUNDARY, encoding="utf-8")
    return root


def probe_a_fixture_is_built(tmp_path):
    assert _build(tmp_path)
'''


def check(name: str, condition: bool, detail: str, failures: list[str]) -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}")
    if not condition:
        failures.append(f"{name} — {detail}")


def main() -> int:
    read_instant = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"declared-boundary census (#431) — tree read at {read_instant}")

    population: list[tuple[str, dict]] = []
    defects: list[tuple[str, dict]] = []
    unreadable: list[tuple[str, str]] = []
    examined = 0

    for path in shipped_modules(REPO):
        try:
            result = analyse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            unreadable.append((path.name, str(exc)))
            continue
        if not result["reads"]:
            continue
        population.append((path.name, result))
        examined += len(result["constants"])
        defects.extend((path.name, defect) for defect in result["defects"])

    print(
        f"  population: {len(population)} shipped module(s) READ live factory data "
        f"(an `evidence/` path, or the `ledger_boundary` seam)"
    )
    print(f"    module-level date constant(s) examined: {examined}")
    print(f"    constant(s) consumed OUTSIDE a probe: {len(defects)}")

    failures: list[str] = []
    print("\n  the gate's own controls")
    positive = analyse(POSITIVE_SOURCE)
    seam = analyse(SEAM_SOURCE)
    negative = analyse(NEGATIVE_SOURCE)
    marker = analyse(MARKER_ONLY_SOURCE)

    check(
        "a module READING `evidence/ledger.jsonl` with a boundary consumed by `main` is REPORTED",
        positive["reads"] and [d["name"] for d in positive["defects"]] == ["LANDED"],
        f"reads={positive['reads']} defects={positive['defects']}",
        failures,
    )
    check(
        "a module reading through the `ledger_boundary` seam is in the population, and REPORTED",
        "ledger_boundary seam" in seam["reads"]
        and [d["name"] for d in seam["defects"]] == ["LANDED"],
        f"reads={seam['reads']} defects={seam['defects']}",
        failures,
    )
    check(
        "a FIXTURE-LOCAL boundary reached only from the probe family is NOT reported",
        bool(negative["reads"]) and negative["defects"] == [],
        f"reads={negative['reads']} defects={negative['defects']}",
        failures,
    )
    check(
        "a boundary in a module that READS nothing does NOT enter the population",
        marker["reads"] == () and marker["defects"] != [],
        f"reads={marker['reads']} defects={marker['defects']}",
        failures,
    )
    check(
        "the population is NON-VACUOUS — this tree's own modules were examined",
        len(population) > 0,
        f"population={len(population)}",
        failures,
    )

    print()
    for name, err in unreadable:
        print(f"  - tests/{name} could not be parsed: {err}")
    for name, defect in defects:
        print(
            f"  - tests/{name}:{defect['lineno']} `{defect['name']}` ({defect['form']}) is "
            f"consumed by {defect['scopes']} — a module-level boundary read outside a probe "
            f"is factory data: declare it in docs/ledger-invariants.json and read it through "
            f"tests/ledger_boundary.py (#428)"
        )

    if not population:
        print(
            "FAIL  the census examined nothing: no shipped module in this tree reads live "
            "factory data. Either the tree lost its gates or the read-set predicate stopped "
            "reading them — never a clean verdict (#116)"
        )
        return 1

    if defects or unreadable or failures:
        print(
            f"declared-boundary census FAILED — {len(defects)} live-boundary constant(s), "
            f"{len(unreadable)} unparseable module(s), {len(failures)} control failure(s)"
        )
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(
        f"declared-boundary census passed — {len(population)} module(s) read live factory "
        f"data, {examined} module-level date constant(s) examined, 0 consumed outside a probe"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
