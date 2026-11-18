"""Gate: a gate's child timeouts must sum BELOW its own declared wall (#651, ruling n=5134).

THE DEFECT THIS CLOSES. `tests/test_fixture_lifetime.py` declared a 249.99 s wall while its
six child timeouts summed to 1980 s by source site — 7.92x the wall — so NOT ONE of them
could ever fire. A hung child therefore reached the wall and was CENSORED: killed with no
verdict at all, which is the one outcome a timeout exists to prevent. Two of those literals
(600.0 and 900.0) looked unremarkable one at a time, which is exactly why the bound must be
the SUM: a per-site "< wall" check passes at 600 and 900 beside a 249.99 s wall.

WHAT IS ENFORCED. For every gate registered in `registry/gates.json`, the effective child
timeouts are re-derived from the module's own `_child`-style call sites — a helper carrying a
`timeout` parameter is a spawner, its default is read from its SIGNATURE, and wrappers are
expanded to RUNS so a helper invoked five times counts five times. A registered gate whose
sum is not strictly below its `budget_sec` is a problem naming that gate.

WHAT IS DISCLOSED AND NOT ENFORCED. A gate can also call a spawner DIRECTLY with a
`timeout=` literal, and that form is outside this gate's ruled scope (`_child`-style call
sites). The measured widening is printed on every run, naming each gate it would red, so the
exclusion is a NUMBER a reader can act on rather than a silence. Enforcing it is a separate
ruling: it would red six entries today, each needing its own derived child budget, and a
gate that arrives already red cannot ship.

WHY IT IS REGISTERED RATHER THAN A PROBE. Without it the next 900 s literal reappears and
nothing notices until a round is censored — which is how this defect survived two rounds.
"""

import ast
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import child_budget as CB  # noqa: E402  (path set above)

MANIFEST = REPO / "registry" / "gates.json"


def registered_gates(manifest: Path | None = None) -> dict[str, dict]:
    """{gate_key: entry} for every gate the tree's manifest registers.

    Empty when the tree carries no manifest — a bootstrapped member factory declares its own
    budgets, and an absent manifest is a documented SKIP, never a silent pass.
    """
    path = manifest if manifest is not None else MANIFEST
    if not Path(path).is_file():
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    gates = data.get("gates", {})
    return {k: v for k, v in gates.items() if isinstance(v, dict)}


def _direct_timeout_sum(tree: ast.Module, env: dict[str, float],
                        leaves: dict[str, float]) -> tuple[float, int]:
    """Sum of `timeout=` literals on calls that are NOT already counted as leaf runs.

    `(total, skipped)` — `skipped` counts kwargs whose value is a bare parameter name (a
    spawner re-passing its own bound to `communicate`), which is not a second timeout.
    """
    total, skipped = 0.0, 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id in leaves:
            continue  # counted by the leaf expansion; counting again would double it
        for kw in node.keywords:
            if kw.arg != "timeout":
                continue
            try:
                total += CB._resolve(kw.value, env, "timeout")
            except AssertionError:
                skipped += 1
    return total, skipped


def gate_child_budget_problems(repo: Path | None = None,
                               manifest: Path | None = None):
    """(population, bounded, problems, disclosed, skipped) over every registered gate."""
    root = Path(repo) if repo is not None else REPO
    # The manifest defaults to the REPO UNDER TEST's own, never this tree's: a fixture repo
    # that carries its own budgets must be judged against them, or the probe silently grades
    # the live tree while claiming to grade the fixture.
    gates = registered_gates(manifest if manifest is not None
                             else root / "registry" / "gates.json")
    problems: list[str] = []
    disclosed: list[str] = []
    bounded = 0
    skipped = 0
    for key in sorted(gates):
        module = root / key
        if not module.is_file():
            skipped += 1
            continue
        entry = gates[key]
        wall = entry.get("budget_sec")
        wall = float(wall) if isinstance(wall, (int, float)) else None
        runs, total, count, found = CB.child_budget(module, wall)
        if count:
            bounded += 1
            if found:
                problems.extend(f"{key}: {p}" for p in found)
        if wall is None:
            continue
        tree = ast.parse(module.read_text(encoding="utf-8"))
        env = CB._module_constants(tree)
        leaves = CB.leaf_defaults(tree, env)
        direct, _ = _direct_timeout_sum(tree, env, leaves)
        if direct and total + direct >= wall:
            disclosed.append(
                f"{key}: direct timeout= literal(s) sum to {direct:.1f}s"
                f"{'' if not total else f' beside {total:.1f}s of child runs'}"
                f" against a {wall:.1f}s wall")
    return len(gates), bounded, problems, disclosed, skipped


def test_every_registered_gates_child_timeouts_sum_below_its_wall() -> None:
    population, bounded, problems, disclosed, skipped = gate_child_budget_problems()
    if not population:
        print(f"\nSKIP: {MANIFEST.relative_to(REPO)} absent — this tree declares no budgets")
        return
    print(f"\nchild-budget gate: examined {population} registered gate(s), "
          f"{bounded} carrying child runs, {skipped} module(s) absent, "
          f"{len(problems)} problem(s)")
    # Non-vacuous: a population of zero would satisfy every bound trivially, and a green over
    # nothing is the failure mode this factory has paid for repeatedly (#116).
    assert bounded >= 1, (
        f"{population} registered gate(s) examined and NONE carried a child run: the "
        "derivation lost its population, so this gate is green over nothing")
    assert not problems, problems
    for line in disclosed:
        print(f"  DISCLOSED, NOT ENFORCED (out of this gate's ruled scope): {line}")


def test_a_synthetic_gate_with_a_timeout_above_its_wall_is_NAMED() -> None:
    # The ruling's own bite requirement: a synthetic module carrying a large literal must be
    # NAMED, not tolerated. The value is CONSTRUCTED from the wall so this arm cannot match
    # its own source text and grade its own homework (#645 arm 7).
    wall = 249.99
    over = wall * 4
    with tempfile.TemporaryDirectory(prefix="childbudget-literal-") as tmp:
        root = Path(tmp)
        (root / "registry").mkdir()
        (root / "registry" / "gates.json").write_text(
            json.dumps({"gates": {"tests/test_synthetic.py": {"budget_sec": wall}}}),
            encoding="utf-8")
        (root / "tests").mkdir()
        (root / "tests" / "test_synthetic.py").write_text(
            "def _child(code, tmp, timeout=10.0):\n"
            "    return None\n"
            "def test_a():\n"
            f"    _child('x', '/tmp', timeout={over:.1f})\n",
            encoding="utf-8")
        population, bounded, problems, _, _ = gate_child_budget_problems(root)
    assert population == 1 and bounded == 1, (population, bounded)
    assert problems and "test_synthetic.py" in problems[0], problems
    assert f"{over:.1f}s" in problems[0], problems


def test_the_bound_counts_RUNS_so_a_repeated_wrapper_multiplies_its_child() -> None:
    # A census of source SITES understates the worst case by the wrapper's invocation count,
    # and that multiplier is what let a bounded-looking gate carry 2463 s of dead timeouts.
    wall = 249.99
    with tempfile.TemporaryDirectory(prefix="childbudget-wrapper-") as tmp:
        module = Path(tmp) / "mod.py"
        module.write_text(
            "CHILD = 60.0\n"
            "def _child(code, tmp, timeout=CHILD):\n"
            "    return None\n"
            "def _count(code, tmp):\n"
            "    return _child(code, tmp)\n"
            "def test_a():\n"
            "    for _ in range(5):\n"
            "        _count('x', '/tmp')\n",
            encoding="utf-8")
        runs, total, count, problems = CB.child_budget(module, wall)
    assert count == 5, (count, runs)
    assert total == 300.0, (total, runs)
    assert problems, "5 x 60s against a 249.99s wall produced no problem"


def test_an_absent_manifest_is_a_documented_SKIP_not_a_silent_pass() -> None:
    population, bounded, problems, disclosed, skipped = gate_child_budget_problems(
        REPO, REPO / "no" / "such" / "gates.json")
    assert (population, bounded, problems, disclosed, skipped) == (0, 0, [], [], 0), (
        population, bounded, problems)


if __name__ == "__main__":
    # PYTEST form: these are module-level arms, so a bare run would exit 0 having asserted
    # NOTHING — a gate whose only exits are barred.
    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
