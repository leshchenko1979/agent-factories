#!/usr/bin/env python3
"""Gate: every gate file carries an EXECUTABLE `__main__` block.

Origin (issue #542), ruled at ledger `n=4071`. This tree has TWO gate families and they
were born with different contracts:

  * the SCRIPT family -- `def main()` plus `sys.exit(main())` -- runs under
    `python3 tests/<name>.py`, which is the form this factory's own docs use to obtain a
    receipt;
  * the PYTEST family -- 24 files -- had no `__main__` block at all, so the documented
    form IMPORTED the module and executed NOTHING: rc=0, zero bytes of output, no test run.

WHY THAT IS A DEFECT AND NOT A STYLE CHOICE. `rc=0` with empty output is indistinguishable
from a pass to every reader, every log, and every lane that pipes the command. It cost a
measured three wrong diagnoses in one night: `tests/test_hygiene_placement.py` was RED and
CORRECT on main for hours, and the script form reported it green three times, because the
instrument never ran. The runner was never the problem -- `tools/audit.py` registers all 24
as `-m pytest`, so the AUDIT was sound; the defect is exactly the form the docs recommend.

THE PREDICATE IS STRUCTURAL, NOT TEXTUAL. A file satisfies this gate when `ast.parse` finds
a module-level `if` whose test is `__name__ == "__main__"`, AND whose body contains at least
one CALL. Both halves are load-bearing:

  * a SUBSTRING check passes a COMMENTED-OUT trailer, so it cannot tell a real block from a
    comment describing one. That is why control arm 4 comments a live member's trailer out
    rather than deleting it -- a deletion mutant cannot separate a structural check from a
    substring check, because both red on deletion. Only the comment form discriminates.
  * the CALL requirement catches the other way to execute nothing: a body of `pass` (or a
    docstring) satisfies "has a `__main__` block" while running no test, which is the exact
    defect this gate exists to close, wearing the fix's clothes.

WHAT THIS GATE CANNOT DO, stated so no reader over-reads a green. It proves the block is
present and calls something. It does NOT prove the called thing is `pytest.main`, and it
cannot make a SCRIPT gate loud -- a `main()` that returns 0 while printing nothing still
reads rc=0. Per-gate honesty about what a gate PRINTS is out of scope here (ruling n=4071
bounds this unit to the pytest family and to the trailer).

Population: every `tests/test_*.py`. The TEMPLATE twins are not walked separately: they are
held byte-identical to their root counterparts by `tests/test_template_sync.py`, so a twin
that drifted would red there.

Run:  python3 tests/test_gate_direct_invocation.py
Exit: 0 every gate carries an executable `__main__` block; 1 a member does not, or a control
      failed.
"""

from __future__ import annotations

import ast
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TESTS = REPO / "tests"

# The live member the control arm mutates. Chosen by MEASUREMENT rather than convenience: it
# is the file whose silent rc=0 cost three wrong diagnoses, so a control that comments ITS
# trailer out proves the predicate bites on the exact shape #542 was filed for.
CONTROL_MEMBER = "tests/test_hygiene_placement.py"


def _main_block(tree: ast.Module) -> ast.If | None:
    """The module-level `if __name__ == "__main__":` node, or None.

    Matched on the AST rather than on text, so a COMMENTED-OUT trailer is not a block. Both
    operand orders are accepted (`__name__ == "__main__"` and its mirror), because the
    guard's meaning does not depend on which side the constant sits.
    """
    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not isinstance(test, ast.Compare) or len(test.ops) != 1:
            continue
        if not isinstance(test.ops[0], ast.Eq):
            continue
        sides = [test.left, test.comparators[0]]
        names = [s for s in sides if isinstance(s, ast.Name) and s.id == "__name__"]
        consts = [s for s in sides if isinstance(s, ast.Constant) and s.value == "__main__"]
        if names and consts:
            return node
    return None


def _has_call(node: ast.If) -> bool:
    """True when the block's body CALLS something -- not merely `pass` or a docstring."""
    return any(isinstance(child, ast.Call) for child in ast.walk(node))


def judge(path: Path) -> str | None:
    """None when `path` carries an executable `__main__` block, else the reason it does not."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return f"does not parse: {exc}"
    block = _main_block(tree)
    if block is None:
        return (
            'has no module-level `if __name__ == "__main__":` block, so the documented '
            "form `python3 %s` imports it and executes NOTHING -- rc=0 with no output, "
            "which is indistinguishable from a pass (#542)" % path.name
        )
    if not _has_call(block):
        return (
            "has a `__main__` block that CALLS nothing (a `pass` or a bare docstring), so "
            "it executes no test while reading as a satisfied guard -- the #542 defect "
            "wearing the fix's clothes"
        )
    return None


def population() -> list[Path]:
    return sorted(TESTS.glob("test_*.py"))


def evaluate() -> tuple[list[str], int]:
    files = population()
    problems = [f"{p.relative_to(REPO)}: {why}" for p in files if (why := judge(p))]
    return problems, len(files)


def controls() -> list[str]:
    """Non-vacuity. A clean verdict is worthless unless the predicate can fail."""
    problems: list[str] = []

    # ARM 1 -- a synthetic file WITH the block passes. If this reds, the predicate is
    # stricter than the contract and every green it reports is an accident.
    good = (
        "import sys\n"
        "\n"
        "def test_x():\n"
        "    assert True\n"
        "\n"
        'if __name__ == "__main__":\n'
        "    import pytest\n"
        '    sys.exit(pytest.main([__file__, "-q"]))\n'
    )
    # ARM 2 -- the same file with the trailer COMMENTED OUT must red. This is the arm that
    # separates a structural predicate from a substring check: `"__main__" in text` is TRUE
    # for this text and would pass it.
    commented = (
        "import sys\n"
        "\n"
        "def test_x():\n"
        "    assert True\n"
        "\n"
        '# if __name__ == "__main__":\n'
        "#     import pytest\n"
        '#     sys.exit(pytest.main([__file__, "-q"]))\n'
    )
    # ARM 3 -- a block that calls nothing must red: `pass` satisfies "has a block" while
    # executing no test.
    inert = (
        "import sys\n"
        "\n"
        "def test_x():\n"
        "    assert True\n"
        "\n"
        'if __name__ == "__main__":\n'
        "    pass\n"
    )

    with tempfile.TemporaryDirectory() as tmp:
        holder = Path(tmp)
        paths = {}
        for name, text in (("good", good), ("commented", commented), ("inert", inert)):
            p = holder / f"{name}.py"
            p.write_text(text, encoding="utf-8")
            paths[name] = p

        why_good = judge(paths["good"])
        if why_good is not None:
            problems.append(
                "arm 1 (positive): a synthetic file WITH an executable block was refused "
                f"-- {why_good}"
            )
        if judge(paths["commented"]) is None:
            problems.append(
                "arm 2 (commented trailer): a COMMENTED-OUT block was accepted -- the "
                "predicate is reading text, not structure, and every green it reports is "
                "a statement about comments"
            )
        if judge(paths["inert"]) is None:
            problems.append(
                "arm 3 (inert body): a `__main__` block whose body calls nothing was "
                "accepted -- it executes no test, which is the #542 defect itself"
            )

    # ARM 4 -- the ruled discriminator, on a LIVE member: comment the real trailer out and
    # the live file must red. A fixture alone cannot prove the predicate bites on this
    # tree's actual shape, and a DELETION mutant cannot prove it is structural -- only
    # commenting out a real guard can.
    member = REPO / CONTROL_MEMBER
    if not member.is_file():
        problems.append(
            f"arm 4 (live member): {CONTROL_MEMBER} is absent, so the control that pins "
            "the predicate to a real shape examined nothing"
        )
    else:
        live_why = judge(member)
        if live_why is not None:
            problems.append(
                f"arm 4 (live member): {CONTROL_MEMBER} does not carry an executable "
                f"block, so the control has nothing to comment out -- {live_why}"
            )
        else:
            with tempfile.TemporaryDirectory() as tmp:
                mutated = Path(tmp) / member.name
                mutated.write_text(
                    "\n".join(
                        ("# " + line) if line.strip() else line
                        for line in member.read_text(encoding="utf-8").splitlines()
                    )
                    + "\n",
                    encoding="utf-8",
                )
                if judge(mutated) is None:
                    problems.append(
                        "arm 4 (live member): commenting out EVERY line of "
                        f"{CONTROL_MEMBER} still passed -- the predicate cannot tell a "
                        "guard from a comment about one"
                    )
    return problems


def main() -> int:
    problems, examined = evaluate()
    control_problems = controls()

    if not examined:
        print(
            "gate-direct-invocation gate ERROR: no tests/test_*.py found -- an empty "
            "population is not a clean verdict"
        )
        return 1

    for p in problems:
        print(f"FAIL: {p}")
    for p in control_problems:
        print(f"FAIL: {p}")

    if problems or control_problems:
        print(
            f"gate-direct-invocation gate FAILED: {len(problems)} member(s) without an "
            f"executable `__main__` block, {len(control_problems)} control failure(s), "
            f"{examined} file(s) examined"
        )
        return 1

    print(
        f"gate-direct-invocation gate passed: {examined} file(s) examined, each carrying an "
        "executable `__main__` block; 4 control arm(s) bit (positive, commented trailer, "
        "inert body, live member)"
    )
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
