#!/usr/bin/env python3
"""Gate for P35 — a gate fixture must model the tree its tool runs in.

Predicate, stated with its count in this gate's own output: for every `shutil.copy2`
call in every scanned module whose SOURCE resolves to a repo tool file
(`tools/<name>.py`), that same module must obtain the tool's import closure for the
SAME source — via the shared `stage_tool(...)` helper or an explicit
`local_import_closure(...)` call. A module that copies a tool into a throwaway tree
with no closure call is a violation.

The resolver follows module-level path CONSTANTS rather than matching strings. That is
the load-bearing part: `tests/test_roadmap_transition.py` stages its tool as
`copy2(REPO_ROOT / TOOL_REL, root / TOOL_REL)` and the literal `"tools"` never appears
beside the call — a literal-only predicate reports that site clean (measured, #60).

Why the law exists: the fixture is a MODEL of the tree the tool runs in, and copying
the tool alone encodes an unstated assumption of self-containment. Nothing states it
and nothing checked it, so it held silently until the tool gained a lawful intra-repo
import — and then the gate red on a correct change (meta-factory #60, P35).
"""

from __future__ import annotations

import ast
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_fixtures import stage_tool  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

SCAN_ROOTS = (REPO_ROOT / "tests", REPO_ROOT / "TEMPLATE" / "tests")

# The one predicate, in one place — the live scan and the synthetic probes both use it,
# so the probe cannot drift from the check it is meant to be probing.
PREDICATE = (
    "a copy2 whose source resolves to tools/<name>.py must be accompanied in the same "
    "module by stage_tool/local_import_closure for that same source"
)

CLOSURE_CALLS = ("stage_tool", "local_import_closure")


def _tail(node: ast.AST, consts: dict[str, list[str]]) -> list[str]:
    """The known trailing path segments of `node`, as a list of strings."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.Name):
        return list(consts.get(node.id, []))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _tail(node.left, consts) + _tail(node.right, consts)
    return []


def _joined(node: ast.AST, consts: dict[str, list[str]]) -> str | None:
    parts = _tail(node, consts)
    return "/".join(parts) if parts else None


def _is_tool(path_str: str | None) -> bool:
    return bool(path_str) and path_str.startswith("tools/") and path_str.endswith(".py")


def _module_consts(tree: ast.Module) -> dict[str, list[str]]:
    """Module-level NAME -> known path tail. Two passes so a const may name a const."""
    consts: dict[str, list[str]] = {}
    for _ in range(2):
        for stmt in tree.body:
            target = value = None
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                target, value = stmt.targets[0].id, stmt.value
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.value is not None:
                target, value = stmt.target.id, stmt.value
            if target is not None:
                consts[target] = _tail(value, consts)
    return consts


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def scan_source(text: str) -> tuple[dict[str, int], dict[str, int]]:
    """Return (copied, closed) — resolved tool paths -> first line number, for one module."""
    tree = ast.parse(text)
    consts = _module_consts(tree)
    copied: dict[str, int] = {}
    closed: dict[str, int] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        name = _call_name(node)
        if name not in ("copy2", *CLOSURE_CALLS):
            continue
        joined = _joined(node.args[0], consts)
        if not _is_tool(joined):
            continue
        assert joined is not None
        bucket = copied if name == "copy2" else closed
        bucket.setdefault(joined, node.lineno)
    return copied, closed


def scan_module(path: Path) -> tuple[dict[str, int], dict[str, int]]:
    return scan_source(path.read_text(encoding="utf-8"))


def scanned_modules() -> list[Path]:
    modules: list[Path] = []
    for root in SCAN_ROOTS:
        if root.is_dir():
            modules.extend(sorted(root.glob("*.py")))
    return modules


def closure_coverage() -> dict[str, object]:
    """The one coverage reading the gate reports and asserts on.

    A staging SITE is one distinct (module, tool) pair, however it is staged — a module
    that stages a tool only through `stage_tool` is still a site the law is about, so the
    population is the union, not the bare copies.
    """
    modules = scanned_modules()
    staging_modules = 0
    sites = 0
    violations: list[tuple[str, str, int]] = []
    for path in modules:
        copied, closed = scan_module(path)
        staged = set(copied) | set(closed)
        if not staged:
            continue
        staging_modules += 1
        sites += len(staged)
        for tool in sorted(set(copied) - set(closed)):
            try:
                rel = str(path.relative_to(REPO_ROOT))
            except ValueError:
                rel = str(path)
            violations.append((rel, tool, copied[tool]))
    return {
        "modules_scanned": len(modules),
        "modules_staging_tools": staging_modules,
        "tool_staging_sites": sites,
        "violations": violations,
    }


def report(coverage: dict[str, object]) -> str:
    violations = coverage["violations"]
    assert isinstance(violations, list)
    return (
        f"gate-fixture closure (P35): predicate — {PREDICATE}; "
        f"examined {coverage['modules_scanned']} module(s), "
        f"{coverage['modules_staging_tools']} of them staging a tool across "
        f"{coverage['tool_staging_sites']} tool-staging site(s), "
        f"{len(violations)} violation(s)"
    )


# --------------------------------------------------------------------------- probes

TOOL_REL_SOURCE = '''\
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOL_REL = "tools/roadmap.py"

def tree(root):
    shutil.copy2(REPO_ROOT / TOOL_REL, root / TOOL_REL)
    return root
'''

CLOSED_SOURCE = '''\
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "ledger.py"
LOCAL_TOOLS = REPO / "tools"

def tree(root):
    stage_tool(TOOL, root / "tools", LOCAL_TOOLS)
    return root
'''

BOTH_SHAPES_SOURCE = '''\
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "ledger.py"

def tree(root):
    shutil.copy2(TOOL, root / "tools" / TOOL.name)
    for module in local_import_closure(TOOL, REPO / "tools"):
        shutil.copy2(module, root / "tools" / module.name)
    return root
'''


def test_no_fixture_stages_a_tool_without_its_closure() -> None:
    coverage = closure_coverage()
    assert coverage["violations"] == [], f"{report(coverage)}\n" + "\n".join(
        f"  {rel}:{lineno} stages {tool} alone — the tree does not hold its import closure"
        for rel, tool, lineno in coverage["violations"]  # type: ignore[misc]
    )


def test_the_scan_is_not_vacuous() -> None:
    """A gate that examines nothing passes for the wrong reason."""
    coverage = closure_coverage()
    assert coverage["modules_scanned"] > 0, "no module was scanned"
    assert coverage["modules_staging_tools"] > 0, "no module staging a tool was found"
    assert coverage["tool_staging_sites"] > 0, "no tool-staging site was found to examine"


def test_the_resolver_follows_a_module_constant_to_a_tool_path() -> None:
    """The predicate trap: the literal string `tools` never appears beside the copy call."""
    copied, closed = scan_source(TOOL_REL_SOURCE)
    assert "tools/roadmap.py" in copied, f"resolver missed the TOOL_REL site: {copied}"
    assert closed == {}
    assert copied.keys() - closed.keys() == {"tools/roadmap.py"}


def test_a_staged_closure_is_lawful() -> None:
    copied, closed = scan_source(CLOSED_SOURCE)
    assert copied == {}, "stage_tool must not be read as a bare copy"
    assert closed == {"tools/ledger.py": 9}


def test_an_explicit_closure_loop_is_lawful() -> None:
    copied, closed = scan_source(BOTH_SHAPES_SOURCE)
    assert "tools/ledger.py" in copied and "tools/ledger.py" in closed
    assert copied.keys() - closed.keys() == set()


def test_the_helper_actually_stages_the_closure() -> None:
    """The call-site check is not enough — a broken helper must red this gate.

    Without this, `stage_tool` copying the tool alone passes every probe: the
    gate would report a lawful tree while staging an unmodelled one.
    """
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src"
        dest = Path(tmp) / "dest"
        src.mkdir()
        (src / "neighbour.py").write_text("VALUE = 1\n", encoding="utf-8")
        (src / "entry.py").write_text("import neighbour\n", encoding="utf-8")
        staged = stage_tool(src / "entry.py", dest, src)
        landed = sorted(p.name for p in dest.iterdir())
        assert landed == ["entry.py", "neighbour.py"], (
            f"stage_tool staged {landed} — the tree does not hold the import closure"
        )
        assert sorted(p.name for p in staged) == landed


def test_the_predicate_is_stated_with_its_count() -> None:
    text = report(closure_coverage())
    assert "predicate —" in text and PREDICATE in text
    for field in ("module(s)", "tool-staging site(s)", "violation(s)"):
        assert field in text, f"{field} missing from the gate's own output: {text}"


def main() -> int:
    failures: list[str] = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except AssertionError as exc:
                failures.append(f"FAIL {name}\n    {exc}")
            else:
                print(f"  PASS {name}")

    coverage = closure_coverage()
    print(report(coverage))
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("gate-fixture closure gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
