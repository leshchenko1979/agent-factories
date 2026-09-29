#!/usr/bin/env python3
"""Gate: no shipped tool references a name it never binds.

WHY THIS GATE EXISTS (#235). On 2026-09-29 `python3 tools/audit.py --report` — the cron's
own invocation — died with `NameError: name 'budgets' is not defined`. The reference sat at
three sites in `main()`, which binds `gate_budgets`; the file's only `budgets = ...` is
inside `execute_mechanical_gates()`, a different scope. The crash is POSITIONAL and that is
what made it invisible: the dated artifact write and the `internal-self-audit` run row both
come AFTER the reference, so the run died before recording anything — measured, and live on
origin for hours (landed 525a23d, live at b9c20d9).

WHY NOTHING SAW IT. Every existing arm reads a surface this path does not touch. The
shipped-audit gate (#199) drives `--json`, which returns BEFORE the text render. The
`--progress` guard covers a different flag. So the class — an undefined name reachable on a
flag no gate exercises — had NO observer at all, and the only reason it was found is that a
lane read the file.

WHAT IT ASSERTS. Every module under the repo's tool roots parses, and no SCOPE references a
name that is not bound in that scope, not found at module scope, and not a builtin. The
check is `symtable`-based rather than lexical: `symtable` already answers the question the
gate needs — for each referenced name, whether it is local, a parameter, imported, assigned,
namespace, free (a closure), or global — so no regex over source text can stand in for it and
a name mentioned in a comment or a string is never a hit by construction.

DELIBERATELY NOT A LINTER, and NOT A DEPENDENCY. `pyflakes` is not assumed present (the
kit ships no dependency list), so the check is stdlib-only and offline. It is also narrower
than a linter on purpose: it asks the one question that produced a live crash.

Run:  python3 tests/test_audit_undefined_names.py
Exit: 0 every tool binds the names it references; 1 an unresolved reference, naming the
      file, the scope and the name; 2 the population was empty (never a silent pass).
"""
from __future__ import annotations

import builtins
import symtable
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The module namespace carries these without an assignment, so a reference to one is
# bound even though no `X = ...` creates it. Named explicitly rather than by prefix so a
# future dunder is added knowingly.
MODULE_IMPLICIT = {
    "__name__", "__doc__", "__file__", "__spec__", "__package__", "__loader__",
    "__builtins__", "__annotations__", "__dict__", "__path__", "__all__",
}

BUILTINS = frozenset(dir(builtins))


def tool_roots(repo: Path) -> list[Path]:
    """Every directory holding shipped tools, in this tree.

    `tools/` exists in every factory, so the gate applies wherever it ships. `TEMPLATE/tools/`
    is present only in the repo that ships the kit, and it is a SECOND population rather than
    a substitute: a defect written into a TEMPLATE half is the same defect one commit later.
    """
    roots = [repo / "tools"]
    template_tools = repo / "TEMPLATE" / "tools"
    if template_tools.is_dir():
        roots.append(template_tools)
    return [r for r in roots if r.is_dir()]


def unresolved_references(src: str, filename: str) -> list[tuple[str, str]]:
    """Referenced names that resolve Nowhere: (scope_label, name) pairs.

    A name is RESOLVED when the scope binding it is local, a parameter, imported, assigned,
    a namespace, or free (bound by an enclosing function); or when it is found at module
    scope or among the builtins. Everything else is a reference to a name no scope supplies —
    which is what a `NameError` at that line would be.
    """
    table = symtable.symtable(src, filename, "exec")
    module_names = set(table.get_identifiers())
    hits: list[tuple[str, str]] = []

    def walk(scope, label: str) -> None:
        for name in scope.get_identifiers():
            symbol = scope.lookup(name)
            if not symbol.is_referenced():
                continue
            if (
                symbol.is_local()
                or symbol.is_parameter()
                or symbol.is_imported()
                or symbol.is_assigned()
                or symbol.is_namespace()
                or symbol.is_free()
            ):
                continue
            if name in module_names or name in BUILTINS or name in MODULE_IMPLICIT:
                continue
            hits.append((label, name))
        for child in scope.get_children():
            walk(child, f"{label}.{child.get_name()}")

    walk(table, "<module>")
    return sorted(set(hits))


def scan_file(path: Path) -> tuple[list[tuple[str, str]], str | None]:
    """(hits, syntax_error). A file that does not parse is REPORTED, never skipped."""
    try:
        src = path.read_text()
    except OSError as exc:
        return [], f"unreadable: {exc}"
    try:
        return unresolved_references(src, str(path)), None
    except SyntaxError as exc:
        return [], f"does not parse: {exc}"


def _hits(src: str) -> list[tuple[str, str]]:
    return unresolved_references(textwrap.dedent(src), "<probe>")


def probe_an_undefined_name_in_a_function_is_caught():
    hits = _hits("def f():\n    return never_bound_here\n")
    return (
        len(hits) == 1 and hits[0][1] == "never_bound_here",
        f"expected exactly one hit naming never_bound_here, got {hits}",
    )


def probe_a_builtin_reference_is_not_a_hit():
    hits = _hits("def f(items):\n    return len(sorted(items))\n")
    return (hits == [], f"a builtin must not be a hit, got {hits}")


def probe_a_module_level_name_is_not_a_hit():
    hits = _hits("LIMIT = 3\ndef f():\n    return LIMIT\n")
    return (hits == [], f"a module-level name must not be a hit, got {hits}")


def probe_a_function_local_is_not_a_hit():
    hits = _hits("def f():\n    local = 1\n    return local\n")
    return (hits == [], f"a local must not be a hit, got {hits}")


def probe_a_parameter_is_not_a_hit():
    hits = _hits("def f(argv):\n    return argv\n")
    return (hits == [], f"a parameter must not be a hit, got {hits}")


def probe_a_comprehension_target_is_not_a_hit():
    hits = _hits("def f(xs):\n    return [item for item in xs]\n")
    return (hits == [], f"a comprehension target must not be a hit, got {hits}")


def probe_an_enclosing_scope_binding_is_not_a_hit():
    hits = _hits("def outer():\n    held = 1\n    def inner():\n        return held\n    return inner\n")
    return (hits == [], f"a closure binding must not be a hit, got {hits}")


def probe_a_name_in_a_comment_or_string_is_not_a_hit():
    hits = _hits('NOTE = "budgets.load_note is the name"\ndef f():\n    # budgets.load_note\n    return NOTE\n')
    return (hits == [], f"a lexical mention must not be a hit, got {hits}")


def probe_the_text_render_path_completes():
    """The cron's own invocation renders TEXT; `--json` returns BEFORE the lines that died.

    This is the arm that pins the GUARD rather than the name: `main()` binds
    `gate_budgets = None` under `--no-gates`, so an unguarded `gate_budgets.load_note`
    raises `AttributeError` there, while a bare rename to `budgets` raises `NameError` on
    every text run. Driving the real text path is the only check that sees either — measured
    (#235): the three invocation sites in the suite all pass `--json`, so nothing rendered
    this path and the crash lived on origin.

    `--no-gates` is used deliberately: it renders the whole text tail without spawning the
    suite, so the probe costs seconds rather than minutes, and it is the arm that exercises
    the `None` manifest as well.
    """
    import subprocess

    tool = REPO / "tools" / "audit.py"
    if not tool.is_file():
        return False, f"{tool} is absent, so the text path could not be driven"
    try:
        proc = subprocess.run(
            [sys.executable, str(tool), "--no-gates"],
            capture_output=True, text=True, timeout=600, cwd=str(REPO),
        )
    except subprocess.TimeoutExpired:
        return False, "the text render did not finish within 600 s"
    out = (proc.stdout or "") + (proc.stderr or "")
    renders_load = "Load population" in out
    ok = proc.returncode == 0 and renders_load
    return ok, (
        f"rc={proc.returncode}, load population rendered={renders_load}; "
        f"tail={out[-240:]!r}"
    )


def probe_a_syntax_error_is_reported_not_silent():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        broken = Path(tmp) / "broken.py"
        broken.write_text("def f(:\n    pass\n")
        hits, err = scan_file(broken)
    return (
        hits == [] and err is not None and "does not parse" in err,
        f"a file that does not parse must be reported, got hits={hits} err={err}",
    )


def run_self_probes() -> list[tuple[str, bool, str]]:
    probes = [
        probe_an_undefined_name_in_a_function_is_caught,
        probe_a_builtin_reference_is_not_a_hit,
        probe_a_module_level_name_is_not_a_hit,
        probe_a_function_local_is_not_a_hit,
        probe_a_parameter_is_not_a_hit,
        probe_a_comprehension_target_is_not_a_hit,
        probe_an_enclosing_scope_binding_is_not_a_hit,
        probe_a_name_in_a_comment_or_string_is_not_a_hit,
        probe_a_syntax_error_is_reported_not_silent,
        probe_the_text_render_path_completes,
    ]
    results = []
    for probe in probes:
        try:
            ok, detail = probe()
        except Exception as exc:  # a probe that raises has not proved its property
            ok, detail = False, f"raised {type(exc).__name__}: {exc}"
        results.append((probe.__name__, ok, detail))
    return results


def main() -> int:
    print("audit-undefined-names gate: every shipped tool binds the names it references")
    results = run_self_probes()
    failed = [name for name, ok, _ in results if not ok]
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'} - {name}" + ("" if ok else f"  [{detail}]"))

    roots = tool_roots(REPO)
    files: list[Path] = []
    for root in roots:
        files.extend(sorted(root.glob("*.py")))

    # NON-VACUITY. A scan that examined nothing has reported nothing, and its clean
    # verdict would be indistinguishable from a verified one. The population is PRINTED
    # and a zero is a FAILURE rather than a pass.
    print(f"  population: {len(files)} module(s) over {len(roots)} root(s) — "
          f"{', '.join(str(r.relative_to(REPO)) for r in roots) or '(none)'}")
    if not files:
        print("  FAIL - the population was EMPTY: no tool module was examined, so no verdict is due")
        return 2

    if failed:
        print(f"audit-undefined-names gate FAILED: {len(failed)} probe failure(s)")
        return 1

    problems: list[str] = []
    for path in files:
        hits, err = scan_file(path)
        rel = path.relative_to(REPO)
        if err is not None:
            problems.append(f"{rel}: {err}")
            continue
        for scope, name in hits:
            problems.append(f"{rel}:{scope}: `{name}` is referenced and never bound")

    for problem in problems:
        print(f"  UNRESOLVED  {problem}")

    if problems:
        print(f"audit-undefined-names gate FAILED: {len(problems)} unresolved reference(s) "
              f"over {len(files)} module(s)")
        return 1
    print(f"audit-undefined-names gate ok: {len(files)} module(s) reference only names they bind")
    return 0


if __name__ == "__main__":
    sys.exit(main())
