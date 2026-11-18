"""Shared child-timeout budget derivation (#651) — ONE parser, never two.

A gate's child timeouts are only worth having if they can fire BEFORE its declared wall. A
hung child that reaches the wall is CENSORED — killed with no verdict at all — while one
killed by its own timeout FAILS the arm it belongs to, which is a verdict. So the SUM of
every timeout is what must sit below the wall, never each site on its own: a per-site
"< wall" check is exactly what passed at 600.0 and 900.0 beside a 249.99 s wall (#651's
defect, ruled at ledger n=5134).

Two consumers, one derivation:

  * `tests/test_fixture_lifetime.py` bounds ITS OWN budget this way (criterion 2 of the
    #651 brief), reading the sum off its own call sites rather than restating constants.
  * `tests/test_gate_child_budget.py` applies the SAME derivation to every gate registered
    in `registry/gates.json`, so the next 900 s literal is caught by a gate rather than by
    the round it censors.

Keeping the parser here rather than in each gate is the `#296` law: one field, one
predicate. Two copies of an AST walk drift, and the copy that drifts is the one nobody reads.

THE WRAPPER EXPANSION IS NOT OPTIONAL. A helper holding one `_child` call and invoked five
times is five child runs, not one, so a census of SOURCE SITES understates the worst case by
that multiplier. The defect's own numbers show the gap: counting sites gives 1980.0 s
(7.9203x the wall, the figure the ruling carries), while counting RUNS — which is what this
module does — gives 2463.0 s (9.85x). The weaker number is not wrong, it is a different
question; the bound that can actually be violated is the run-counted one.
"""

import ast
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

MANIFEST = REPO / "registry" / "gates.json"


def _module_constants(tree: ast.Module) -> dict[str, float]:
    """Every module-level UPPER-CASE name bound to a numeric literal."""
    env: dict[str, float] = {}
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
            continue
        target = node.targets[0]
        if (isinstance(target, ast.Name) and target.id.isupper()
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, (int, float))):
            env[target.id] = float(node.value.value)
    return env


def _resolve(node: ast.AST, env: dict[str, float], what: str) -> float:
    """A numeric literal or a module constant, resolved the way Python would."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name) and node.id in env:
        return env[node.id]
    raise AssertionError(f"{what} is unresolvable: {ast.dump(node)[:160]}")


def leaf_defaults(tree: ast.Module, env: dict[str, float]) -> dict[str, float]:
    """Every `_child`-STYLE helper's own `timeout` default, read from its signature.

    A helper qualifies by carrying a `timeout` parameter with a default — that is what makes
    it a spawner whose timeout can silently swallow a hang. Reading the default from the
    SIGNATURE, rather than from the module constant a caller happens to use, is what makes
    this derivation able to see a REVERTED tree: with `_child`'s default back at 120.0 while
    `CHILD_TIMEOUT` still reads 18.0, a constant-keyed bound silently keeps counting 18 s
    per site and reports a bounded gate that is not bounded.
    """
    defaults: dict[str, float] = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        args, defs = node.args.args, node.args.defaults
        if not defs:
            continue
        for index, arg in enumerate(args):
            if arg.arg != "timeout":
                continue
            default_index = index - (len(args) - len(defs))
            if default_index < 0:
                break  # `timeout` is positional-required: no default to bound
            defaults[node.name] = _resolve(
                defs[default_index], env, f"{node.name}'s timeout default")
            break
    return defaults


def leaf_calls_in(node: ast.AST, leaves: dict[str, float]) -> list[ast.Call]:
    """Every call inside `node` to one of the `leaves` spawners."""
    return [n for n in ast.walk(node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id in leaves]


def timeout_of(call: ast.Call, env: dict[str, float], default: float) -> float:
    """The timeout this call will actually use, resolved the way Python would."""
    for kw in call.keywords:
        if kw.arg == "timeout":
            return _resolve(kw.value, env, f"timeout at line {call.lineno}")
    return default


def _range_bound(node: ast.AST, env: dict[str, float]) -> int:
    """`N` for a `for ... in range(N)` iterable, else 1.

    A child call inside a literal-bounded loop runs N times, and a derivation that counts
    call SITES reads that as once — the same under-count that let 2463 s of dead timeouts
    read as bounded. Only the single-argument form is resolved: `range(a, b)` and `range(a,
    b, c)` are left at 1 rather than guessed, because a wrong N is worse than a stated 1.
    """
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "range" and len(node.args) == 1):
        return 1
    try:
        return max(1, int(_resolve(node.args[0], env, "range bound")))
    except AssertionError:
        return 1


def _calls_with_mult(node: ast.AST, env: dict[str, float], mult: int = 1):
    """Yield (call, repetitions) for every call under `node`, loops multiplied in."""
    if isinstance(node, ast.For):
        bound = _range_bound(node.iter, env)
        for child in node.body:
            yield from _calls_with_mult(child, env, mult * bound)
        for child in node.orelse:
            yield from _calls_with_mult(child, env, mult)
        return
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        return  # a nested definition is walked as its own node, never inlined here
    if isinstance(node, ast.Call):
        yield (node, mult)
    for child in ast.iter_child_nodes(node):
        yield from _calls_with_mult(child, env, mult)


def _expand_arm(node: ast.AST, spawners: dict[str, ast.FunctionDef],
                env: dict[str, float], seen: tuple[str, ...],
                leaves: dict[str, float]):
    """Yield (line, timeout, runs) for every child run `node` can make."""
    # `node` IS the arm's FunctionDef, and `_calls_with_mult` deliberately skips a nested
    # definition, so the walk starts at its BODY — starting at the def itself yields nothing.
    roots = (node.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
             else [node])
    calls = [(c, m) for root in roots for c, m in _calls_with_mult(root, env)
             if isinstance(c.func, ast.Name)]
    for call, mult in calls:
        if call.func.id in leaves:
            yield (call.lineno, timeout_of(call, env, leaves[call.func.id]), mult)
    names = {c.func.id for c, _ in calls}
    for name in sorted((names & set(spawners)) - set(seen)):
        multiplier = sum(m for c, m in calls if c.func.id == name)
        for line, tmo, runs in _expand_arm(spawners[name], spawners, env, seen + (name,),
                                           leaves):
            yield (line, tmo, runs * multiplier)


def child_runs(path: Path) -> list[tuple[str, int, float, int]]:
    """(arm, line, timeout_sec, runs) for every child run `path` can make.

    A wrapper's child call is attributed to each ARM that calls the wrapper, once per
    invocation, so the worst case counts RUNS and not source sites.
    """
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    env = _module_constants(tree)
    leaves = leaf_defaults(tree, env)
    if not leaves:
        return []
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    spawners = {name: fn for name, fn in funcs.items() if leaf_calls_in(fn, leaves)}
    # An ARM is a ROOT — a function nothing else in this module calls — and NOT simply a
    # function that makes no child call itself. Those are different sets: a test that spawns
    # a child directly is BOTH an arm and a spawner, and classifying arms as "not a spawner"
    # silently dropped four of six sites on the first run of this derivation (only the two
    # wrapper callers survived), which is exactly the under-count that let 2463 s of dead
    # timeouts read as bounded.
    called = {c.func.id for fn in funcs.values() for c in ast.walk(fn)
              if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    runs: list[tuple[str, int, float, int]] = []
    for name, fn in funcs.items():
        if name in called:
            continue  # reached from an arm: its runs are counted where it is CALLED
        for line, tmo, mult in _expand_arm(fn, spawners, env, (name,), leaves):
            runs.append((name, line, tmo, mult))
    return runs


def declared_wall(gate_key: str, path: Path | None = None) -> float | None:
    """`gate_key`'s own `budget_sec`; None when the tree carries no entry for it.

    A member factory that has not declared one inherits the population default, so there is
    no tree-specific number to bound against and the caller prints a documented SKIP.
    """
    manifest = Path(path) if path is not None else MANIFEST
    if not manifest.is_file():
        return None
    data = json.loads(manifest.read_text(encoding="utf-8"))
    gates = data.get("gates", data)
    entry = gates.get(gate_key)
    if not isinstance(entry, dict):
        return None
    budget = entry.get("budget_sec")
    return float(budget) if isinstance(budget, (int, float)) else None


def child_budget(path: Path, wall: float | None):
    """(runs, total_sec, child_runs, problems) for `path` against `wall`."""
    runs = child_runs(path)
    total = sum(tmo * mult for _, _, tmo, mult in runs)
    count = sum(mult for _, _, _, mult in runs)
    problems: list[str] = []
    if wall is not None and total >= wall:
        problems.append(
            f"child timeouts sum to {total:.1f}s ({count} runs) against a {wall:.1f}s wall: a "
            "hung child is censored AT THE WALL with no verdict, instead of failing the arm it "
            "belongs to. Bound the SUM, never each site alone.")
    return runs, total, count, problems
