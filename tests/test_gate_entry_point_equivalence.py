#!/usr/bin/env python3
"""Gate: a gate module's script entry point must reach the SAME population as its registered argv.

Origin (issue #492), ruled at ledger `n=3426`; the shape was decided at `n=3354` (q43) and
this item was named its carrier at `n=3363`. `#475` found the instance -- a module's `main()`
reached 2 of its 3 legs, so the advertised script invocation read `rc=0` over a population
that EXCLUDED `harness_binding_leg` while the registered pytest argv read `rc=1` on the SAME
bytes -- and closed it PER-MODULE. Nothing detected the next module that grew the same split.

THE PREDICATE (ruling `n=3426`). For every gate module the audit registers, the module's SCRIPT
invocation (`python3 tests/<mod>.py`) and its REGISTERED invocation (the argv `tools/audit.py`
appends for it) must agree on `rc` for the same tree. A disagreement is the defect: a lane
running the module's own documented invocation reads GREEN while the gate the audit actually
runs reads RED.

WHY THE MEASURED POPULATION IS NOT ALL 103, stated with its measurement rather than asserted.
For a `script`-mode module the registered argv IS `[python, <module>]` -- the two invocations
are the same command, so comparing them runs a command against itself and can only confirm
`x == x`. For a further class of pytest-mode modules the script form provably runs the SAME
pytest population: `pytest.main([__file__])`, a `globals()` sweep over `test_*`, or a direct
call to EVERY test the module defines. Those are declared `IDENTICAL-COMMAND` or `FULL-FILE`
with their reason PRINTED. The measured pair population is the residual whose `main()` carries
its own logic -- 17 modules at the claim's tree (`n=4126`), whose script half alone costs
~235 s, so a literal every-module double-run would be a ~20-minute gate whose first 86 runs
assert a command equals itself. That is a cost, not a proof. The population is printed beside
the verdict so a green is legible as a SCOPE, never as "all gates proved".

WHAT MAKES THIS BITE ON A GREEN TREE. An `rc` comparison alone is VACUOUS on a green tree:
both forms return 0, so the gate could only red when the module is ALREADY red. So a STATIC
leg runs first and reds on the #475 shape while every gate in the tree is green:

  * `SUBSET` -- the script form provably runs FEWER tests than the registered form: a
    `pytest.main(...)` carrying a selector, or direct calls to a STRICT subset of the module's
    `test_*` functions. A subset can agree on `rc` only by luck, so it FAILS whether or not
    the two happen to agree today.
  * `UNPROVEN` -- `main()` with its own logic, where static analysis cannot decide. These are
    MEASURED: both invocations run, their `rc` compared, and a form that exceeds its declared
    budget is reported UNMEASURED with its runtime -- never silently clean, because "clean"
    and "examined nothing" must not print the same (#116).

WHAT THIS GATE CANNOT DO, stated so no reader over-reads a green. It cannot see a subset hidden
behind dynamic dispatch it does not recognise: a `main()` that calls a subset through
`getattr`, a dict of callables, or a plugin hook reads `UNPROVEN` and is caught only if the
`rc` pair disagrees. It also does not judge whether a gate's population is the RIGHT one --
only that the two documented invocations agree about which one they run.

Run:  python3 tests/test_gate_entry_point_equivalence.py
Exit: 0 every registered module's two invocations reach the same population and agree on rc;
      1 a SUBSET, an rc disagreement, a form over budget, or a failed control; 2 the registry
      or call sites could not be read (an unreadable population is never a clean one).
"""

from __future__ import annotations

import ast
import concurrent.futures
import json
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TESTS = REPO / "tests"

# Declared, so the measured half is bounded and its shape is reviewable rather than emergent.
WORKERS = 6
EXECUTABLE_PLACEHOLDER = "<sys.executable>"


def _module_defs(tree: ast.Module) -> dict[str, ast.AST]:
    """Every module-level function, by name."""
    return {
        n.name: n
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _main_guard(tree: ast.Module) -> ast.If | None:
    """The module-level `if __name__ == "__main__":` node, or None."""
    for node in tree.body:
        if isinstance(node, ast.If) and "__main__" in ast.unparse(node.test):
            return node
    return None


def _names(node: ast.AST) -> set[str]:
    """Every bare name a node MENTIONS.

    Reference, not call-graph: the #475 repair's own predicate reads the names `main()`
    references, because a leg reached through a tuple (`for leg in (a, b, c)`) or a module
    constant is reached, while a call-graph walk following only `Call` nodes misses it.
    Measured on `tests/test_question_intake.py`, whose `evaluate()` iterates a tuple of legs:
    a call-graph walk reported all three unreachable and this walk finds them.
    """
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _reachable(roots: set[str], defs: dict[str, ast.AST]) -> set[str]:
    """Every module-level function transitively referenced from `roots`."""
    seen: set[str] = set()
    stack = list(roots)
    while stack:
        name = stack.pop()
        if name in seen or name not in defs:
            continue
        seen.add(name)
        stack.extend(r for r in _names(defs[name]) if r in defs)
    return seen


def _sweeps_tests(node: ast.AST) -> bool:
    """Whether this node iterates `globals()`/`locals()` filtering a `test_` prefix.

    This is #475's own CONTRAST CASE (`tests/test_board_intake_recorded.py`) -- the pattern
    that makes the other modules' divergence a defect rather than a convention, because the
    entry point is wired to the module's own tests.
    """
    source = ast.unparse(node)
    return ("globals()" in source or "locals()" in source) and "test_" in source


def classify(source: str, registered_script: bool) -> tuple[str, list[str]]:
    """(kind, detail) for one module's script entry point.

    Kinds: `IDENTICAL-COMMAND`, `FULL-FILE`, `SUBSET`, `UNPROVEN`, `NO-GUARD`.
    """
    tree = ast.parse(source)
    defs = _module_defs(tree)
    if registered_script:
        return "IDENTICAL-COMMAND", []
    guard = _main_guard(tree)
    if guard is None:
        return "NO-GUARD", []
    tests = {name for name in defs if name.startswith("test_")}
    guard_refs = _names(guard)
    entry = _reachable(guard_refs, defs)

    # The evidence lives in whatever the guard REACHES, not in the guard's own two lines: the
    # dominant shape is `if __name__ == "__main__": sys.exit(main())`, whose entire population
    # decision is inside `main()`. Reading only the guard body would classify every such module
    # UNPROVEN and then measure it -- a correct verdict bought with 20 minutes of runtime.
    reachable_source = ast.unparse(guard) + "".join(
        ast.unparse(defs[name]) for name in sorted(entry)
    )

    if "pytest.main" in reachable_source:
        selectors = [s for s in ("-k", "--deselect", "-m ") if s in reachable_source]
        if "__file__" in reachable_source and not selectors:
            return "FULL-FILE", ["pytest.main on __file__"]
        return "SUBSET", [
            "pytest.main without __file__"
            if "__file__" not in reachable_source
            else f"pytest.main carries a selector ({', '.join(selectors)})"
        ]

    # The sweep may sit in the guard body itself or in whatever the guard reaches: both are the
    # same pattern, and looking only at reachable defs misses the guard-only form.
    if _sweeps_tests(guard) or any(_sweeps_tests(defs[name]) for name in entry):
        return "FULL-FILE", ["globals() sweep over test_*"]

    called: set[str] = set(guard_refs)
    for name in entry:
        called |= _names(defs[name])
    direct = {name for name in called if name in tests}
    if direct and direct >= tests:
        return "FULL-FILE", [f"every one of its {len(tests)} test(s) named directly"]
    if direct:
        return "SUBSET", sorted(tests - direct)
    return "UNPROVEN", []


def registered_entries(audit_text: str) -> list[dict]:
    """Every registered gate module with the COMMAND the audit runs for it.

    The registry's `modes` map says which convention the audit uses; this says which argv it
    actually appends. Both are read, because a map that drifted from the call sites would
    otherwise make the comparison compare the wrong pair -- and the runner is read from the
    append's own argument structure, never from its filename.
    """
    sys.path.insert(0, str(TESTS))
    try:
        import gate_registry  # noqa: PLC0415
    finally:
        sys.path.pop(0)
    return [
        entry
        for entry in gate_registry.registration_entries(audit_text)
        if entry["kind"] == "tests"
    ]


def argv_of(entry: dict) -> list[str]:
    """The argv the audit appends, with the executable placeholder resolved."""
    tokens = entry["argv"].split()
    if tokens and tokens[0] == EXECUTABLE_PLACEHOLDER:
        tokens = tokens[1:]
    return [sys.executable] + tokens


def _run(argv: list[str], timeout: float) -> tuple[int, str]:
    """(rc, tail) for one invocation; a timeout is its own rc, never a pass."""
    try:
        done = subprocess.run(
            argv, cwd=REPO, capture_output=True, text=True, timeout=timeout
        )
        tail = (done.stdout + done.stderr).strip().splitlines()
        return done.returncode, (tail[-1][:200] if tail else "")
    except subprocess.TimeoutExpired:
        return 124, f"exceeded its {timeout:.0f}s declared budget"


def _compare(module: str, entry: dict, timeout: float) -> dict:
    """Run BOTH invocations for one module and compare rc."""
    registered = argv_of(entry)
    script = [sys.executable, module]
    reg_rc, reg_tail = _run(registered, timeout)
    scr_rc, scr_tail = _run(script, timeout)
    return {
        "module": module,
        "registered_argv": " ".join(registered[1:]),
        "registered_rc": reg_rc,
        "script_rc": scr_rc,
        "registered_tail": reg_tail,
        "script_tail": scr_tail,
        "agree": reg_rc == scr_rc,
    }


def evaluate(repo: Path = REPO) -> dict:
    """The whole verdict: classification over every registered module, plus measured pairs."""
    registry = json.loads((repo / "registry" / "gates.json").read_text(encoding="utf-8"))
    modes: dict[str, str] = registry["modes"]
    budgets: dict[str, dict] = registry.get("gates", {})
    default_budget = float(registry.get("default", {}).get("budget_sec", 120.0))
    audit_text = (repo / "tools" / "audit.py").read_text(encoding="utf-8")
    entries = registered_entries(audit_text)

    kinds: dict[str, int] = {}
    problems: list[str] = []
    to_measure: list[tuple[str, dict, float]] = []
    examined = 0

    for entry in entries:
        module = f"tests/{entry['name']}"
        path = repo / module
        if not path.is_file():
            problems.append(f"{module}: the audit registers it but it does not exist")
            continue
        if module not in modes:
            problems.append(
                f"{module}: the audit registers it but registry/gates.json::modes does not "
                f"declare a mode, so no reader knows which form owns the verdict"
            )
            continue
        examined += 1
        kind, detail = classify(
            path.read_text(encoding="utf-8"), entry["runner"] == "script"
        )
        kinds[kind] = kinds.get(kind, 0) + 1
        if kind == "SUBSET":
            problems.append(
                f"{module}: the script entry point is a SUBSET of the registered gate "
                f"({'; '.join(detail)}) -- it can agree on rc only by luck"
            )
        elif kind == "NO-GUARD":
            problems.append(
                f"{module}: no `__main__` guard, so its script form runs nothing and exits 0"
            )
        elif kind == "UNPROVEN":
            budget = float(budgets.get(module, {}).get("budget_sec", default_budget))
            to_measure.append((module, entry, budget))

    measured: list[dict] = []
    if to_measure:
        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = [pool.submit(_compare, m, e, b) for m, e, b in to_measure]
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                measured.append(result)
                if not result["agree"]:
                    problems.append(
                        f"{result['module']}: the two invocations DISAGREE on rc -- "
                        f"registered={result['registered_rc']} "
                        f"({result['registered_tail']!r}), "
                        f"script={result['script_rc']} ({result['script_tail']!r})"
                    )
                if 124 in (result["registered_rc"], result["script_rc"]):
                    problems.append(
                        f"{result['module']}: a form exceeded its declared budget, so the pair "
                        f"is UNMEASURED rather than agreeing"
                    )

    return {
        "kinds": kinds,
        "problems": problems,
        "measured": sorted(measured, key=lambda r: r["module"]),
        "modules": examined,
    }


def controls() -> list[str]:
    """Five arms, each building the shape it judges rather than asserting around a constant."""
    problems: list[str] = []
    # The fixture is DATA, so its source is written INDENTED and dedented at use: this file
    # must carry no column-0 `def test_*`, because `tests/gate_registry.py`'s `target_form()`
    # reads a module-level test function as a PYTEST-style target and a gate registered as a
    # script that carries one is a dead-leg mismatch (direction 5). The indentation keeps the
    # predicate reading the truth: this gate's legs are its `probe_*`-style arms, not the
    # fixture's own tests.
    legs_module = textwrap.dedent("""
        import sys

        def leg_one(repo):
            return []

        def leg_two(repo):
            return ["leg two problem"]

        def test_leg_one_is_clean():
            assert leg_one(None) == []

        def test_leg_two_is_clean():
            assert leg_two(None) == []

        def main():
            problems = leg_one(None)
            for p in problems:
                print(p)
            return 1 if problems else 0

        if __name__ == "__main__":
            sys.exit(main())
    """)

    # ARM 1 -- the #475 shape, built rather than described: main() reaches leg_one only, while
    # leg_two's own test FAILS, so the script form reads rc=0 and the registered form rc=1 on
    # the same bytes. A detector that cannot see this is the defect it was written for.
    with tempfile.TemporaryDirectory() as tmp:
        broken = Path(tmp) / "test_broken_entry_point.py"
        broken.write_text(legs_module, encoding="utf-8")
        pair = _compare(
            str(broken),
            {"argv": f"{EXECUTABLE_PLACEHOLDER} -m pytest {broken}", "runner": "pytest"},
            120.0,
        )
        if pair["agree"]:
            problems.append(
                "arm 1 (the #475 shape): the two invocations agreed on rc over a module whose "
                f"entry point skips a failing leg (both {pair['registered_rc']}) -- the rc "
                "comparison does not bite"
            )
        if pair["script_rc"] != 0 or pair["registered_rc"] == 0:
            problems.append(
                "arm 1 (the #475 shape): expected script=0 against registered!=0, read "
                f"script={pair['script_rc']} registered={pair['registered_rc']}"
            )

    # ARM 2 -- the same module WIRED. Both forms must read 0, so arm 1 is not satisfied by a
    # comparison that reports disagreement unconditionally.
    with tempfile.TemporaryDirectory() as tmp:
        good = Path(tmp) / "test_wired_entry_point.py"
        good.write_text(
            legs_module.replace(
                "    problems = leg_one(None)\n",
                "    problems = leg_one(None) + leg_two(None)\n",
            ),
            encoding="utf-8",
        )
        pair = _compare(
            str(good),
            {"argv": f"{EXECUTABLE_PLACEHOLDER} -m pytest {good}", "runner": "pytest"},
            120.0,
        )
        if not pair["agree"]:
            problems.append(
                "arm 2 (wired): the two invocations disagreed over a wired module "
                f"(script={pair['script_rc']}, registered={pair['registered_rc']})"
            )

    # ARM 3 -- the CONTRAST CASE. A globals() sweep IS the wired pattern; a detector demanding
    # direct calls would red it, and it must read FULL-FILE instead.
    sweep = '''
if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
'''
    kind, detail = classify(sweep, False)
    if kind != "FULL-FILE":
        problems.append(
            f"arm 3 (globals sweep): classified {kind}, expected FULL-FILE ({detail})"
        )

    # ARM 4 -- a SCRIPT-mode module. The registered argv IS the script command, so no pair is
    # run and the module can never red: a detector demanding a `__main__` sweep of the tests
    # would red every script gate in the tree.
    kind, _ = classify("def main():\n    return 0\n", True)
    if kind != "IDENTICAL-COMMAND":
        problems.append(
            f"arm 4 (script mode): classified {kind}, expected IDENTICAL-COMMAND"
        )

    # ARM 5 -- a SELECTOR. pytest.main with `-k` runs fewer tests than the registered argv and
    # must read SUBSET even when the two agree on rc today.
    selector = '''
import pytest

if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-k", "fast"]))
'''
    kind, detail = classify(selector, False)
    if kind != "SUBSET":
        problems.append(f"arm 5 (selector): classified {kind}, expected SUBSET ({detail})")

    return problems


def main() -> int:
    result = evaluate(REPO)
    kinds = result["kinds"]
    problems = result["problems"] + controls()

    print(
        f"entry-point equivalence: examined {result['modules']} registered gate module(s) -- "
        f"{kinds.get('IDENTICAL-COMMAND', 0)} IDENTICAL-COMMAND (registered argv IS the script "
        f"form), {kinds.get('FULL-FILE', 0)} FULL-FILE (same population by construction), "
        f"{kinds.get('UNPROVEN', 0)} MEASURED under BOTH invocations, "
        f"{kinds.get('SUBSET', 0)} SUBSET, {kinds.get('NO-GUARD', 0)} NO-GUARD"
    )
    print(f"  rc pair(s) compared: {len(result['measured'])}")
    for row in result["measured"]:
        print(
            f"    {row['module']}: registered={row['registered_rc']} "
            f"script={row['script_rc']} {'AGREE' if row['agree'] else 'DISAGREE'}"
        )

    if problems:
        print(f"\n{len(problems)} problem(s):", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    print(
        f"entry-point equivalence: clean -- {result['modules']} module(s) examined, "
        f"{len(result['measured'])} rc pair(s) compared, 0 disagreement(s), 5 control arm(s) bit"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
