#!/usr/bin/env python3
"""Gate: a `TEMPLATE/` gate this commit adds or modifies must be PAIRED (#488).

WHY THIS GATE EXISTS. `#459` and `#487` are one class, twice: a gate that lands in
`TEMPLATE/`, is REGISTERED in the shipped audit, and whose shipped depth cannot
satisfy its subject. The shipped audit runs it with `cwd=TEMPLATE`; the subject is
factory data the kit does not ship; the gate reds — and the verdict arrives as an
UNACCOUNTED verdict in `tests/test_shipped_audit_runs.py`, which is a CLASSIFIER.
It reads the verdict AFTER the gate has landed, so it reports the class and never
prevents one. Nothing asked, in the commit that ADDED the gate, whether the shipped
depth could carry it.

`#459`'s own `Prevented by` column declared that residual in words — *no gate asserts
that a gate ADDED to `TEMPLATE/` is paired in the same commit with the skip its
shipped depth needs, so the next such gate lands the same way* — and `#487` was that
next gate. This is the pairing, made mechanical, and it is FORWARD-ONLY: neither
closed instance is backfilled.

WHAT IT ASSERTS. For every `TEMPLATE/` gate this commit adds or MODIFIES, ONE of:

  (a) the shipped depth CAN CARRY it — run exactly as the shipped audit runs it,
      from `TEMPLATE/`, it exits 0 (the `#487` remedy: make the subject injectable);
  (b) `docs/shipped-audit-skips.json` DECLARES it, marker and all (the `#459`
      remedy: a declared skip, whose stated reason is verified against the source);
  (c) the shipped audit does not REGISTER it, so it never runs there at all.

WHY THE PREDICATE READS THE CHANGE, NEVER THE TREE STATE. This is the load-bearing
constraint. At rest both known instances are indistinguishable from ordinary
registered gates: the file is present, the registration is present, and only the
VERDICT at the shipped depth differs. A tree-wide reader cannot see the class, and
would report clean on exactly the commits this gate exists to catch.

WHY MODIFIED IS IN THE POPULATION, not only ADDED. The ORDERED remedy names "a
`TEMPLATE/` gate or leg ADDED — or its subject-root derivation CHANGES", and a leg
added to a gate that ALREADY exists changes nothing about the gate's path while
changing everything about its shipped-depth verdict. `#487` itself was a leg reading
its bound from the ambient tree, not a new file. A predicate that read only ADDED
paths would have missed its own origin case one level down, so both are read.

Run:  python3 tests/test_template_gate_pairing.py
Exit: 0 the predicate holds and every probe bit, 1 otherwise.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SHIPPED = REPO / "TEMPLATE"

# The population is a property of the SHIPPED tree: a root-only gate is never run by
# the shipped audit, so it cannot land there as an unaccounted verdict.
SHIPPED_GATE_PREFIXES = ("TEMPLATE/tests/", "TEMPLATE/tools/")

# The skip this gate itself carries at the shipped depth — criterion 4 of its own
# dispatch, so it does not become the third instance of the class it prevents. It is a
# MARKER rather than a prose note because `docs/shipped-audit-skips.json` verifies it
# against the SOURCE: pytest captures both streams from session start, so a stated
# reason never reaches the audit's log, and a skip whose reason has gone is a SILENT
# skip, which is a defect exactly as a FAIL is (#199).
STATED_SKIP = "# STATED SKIP: TEMPLATE/"

# Bound on the carrier run. A gate killed at its budget has NOT carried its subject, so
# a timeout is a report rather than a pass — the distinction `NO VERDICT` models in
# `tools/audit.py` (#206), folded into the same answer here because either way the
# shipped depth did not deliver a green.
CARRY_TIMEOUT_SECS = 300

_failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        _failures.append(name)


def _git(top: Path, *args: str) -> str | None:
    """Run git in `top`; None when it cannot be read (the leg fails OPEN)."""
    proc = subprocess.run(
        ["git", "-C", str(top), *args], capture_output=True, text=True
    )
    if proc.returncode != 0:
        return None
    return proc.stdout


def _registry():
    """This tree's OWN `tests/gate_registry.py`, loaded by path.

    IMPORTED rather than re-parsed. The registration reader is a shared predicate with
    one home, and a second implementation would drift from it silently — the class
    `tests/test_law_mechanism_same_commit.py` names for exactly this reason. Both halves
    carry the module, so the shipped copy resolves its own twin.
    """
    path = Path(__file__).resolve().parent / "gate_registry.py"
    spec = importlib.util.spec_from_file_location("_pairing_gate_registry", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def touched_shipped_gates(top: Path) -> dict[str, str]:
    """`{path: "A"|"M"}` for the shipped gates THIS COMMIT stages; {} when unreadable.

    The INDEX is the pending commit: a path staged for addition is present in it and a
    path staged for deletion is absent from it, so this reads the COMMIT and never the
    working tree. An unreadable index is not a defect in the commit, so it fails OPEN.
    """
    listing = _git(top, "diff", "--cached", "--name-status")
    if listing is None:
        return {}
    touched: dict[str, str] = {}
    for line in listing.splitlines():
        fields = line.split("\t")
        if len(fields) < 2:
            continue
        path = fields[-1]
        if path.startswith(SHIPPED_GATE_PREFIXES):
            touched[path] = fields[0][:1]
    return touched


def registered_shipped_gates(top: Path) -> dict[str, dict]:
    """`{rel_path: entry}` for every gate the shipped audit registers."""
    audit = top / "TEMPLATE" / "tools" / "audit.py"
    if not audit.is_file():
        return {}
    entries = _registry().registration_entries(audit.read_text(encoding="utf-8"))
    return {entry["target"]: entry for entry in entries}


def declared_skips(top: Path) -> dict[str, dict]:
    """The declared non-green population, keyed by shipped path; {} when absent."""
    path = top / "docs" / "shipped-audit-skips.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("skips") or {}
    except json.JSONDecodeError:
        return {}


def registered_invocation(rel: str, entry: dict) -> list[str] | None:
    """The argv the registration ITSELF declares, or None when it cannot be built here.

    The registration carries the arguments as well as the runner, and an earlier form of
    this leg rebuilt the invocation from the runner KIND alone — so a target registered
    as `tools/ledger.py verify` was run BARE, argparse exited 2 on the missing
    subcommand, and the depth was declared unable to carry a gate it carries perfectly.
    Measured: staging any touch of `TEMPLATE/tools/ledger.py` at origin reds this gate,
    with or without a change to the file (#509).

    Reading the argv is not a convenience. `gate_registry.registration_entries` projects
    it as a DECLARED FORM (literals bare, computed elements as `<expr>`), so the one
    placeholder this reader can resolve is `<sys.executable>`; any OTHER placeholder is a
    bound computed at run time, and guessing it would trade a false red for a false
    green. That case returns None, which the caller reads as "not carried" — the same
    conservative answer a timeout gets, and for the same reason.
    """
    tokens = (entry.get("argv") or "").split()
    if not tokens or rel not in tokens:
        return None
    argv: list[str] = []
    for token in tokens:
        if token == "<sys.executable>":
            argv.append(sys.executable)
        elif token.startswith("<") and token.endswith(">"):
            return None
        else:
            argv.append(token)
    return argv

def carries_at_shipped_depth(top: Path, rel: str, entry: dict) -> bool:
    """Run the gate exactly as the shipped audit would, from `TEMPLATE/`.

    The invocation comes from the registration's own ARGV rather than from a guess: a
    pytest-style target invoked as a script runs no test at all and exits 0, which would
    read here as "the depth carries it" while testing nothing (#107(d), HQ ruling n=639)
    — and a target whose registration passes SUBCOMMAND arguments run without them exits
    non-zero having tested nothing, which is the same defect with the opposite sign.
    """
    if not (top / "TEMPLATE" / rel).is_file():
        return False
    argv = registered_invocation(rel, entry)
    if argv is None:
        return False
    try:
        proc = subprocess.run(
            argv, cwd=str(top / "TEMPLATE"), capture_output=True, text=True,
            timeout=CARRY_TIMEOUT_SECS,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return proc.returncode == 0


def unpaired_gates(top: Path) -> list[str]:
    """The ONE predicate both call sites load. Empty list == the commit is clean.

    A `top` parameter rather than a module constant, so a synthetic tree can drive it:
    a rule that has only ever seen good input has not been shown to reject bad input.
    """
    touched = touched_shipped_gates(top)
    if not touched:
        return []
    registered = registered_shipped_gates(top)
    declared = declared_skips(top)
    problems: list[str] = []
    for path in sorted(touched):
        rel = path[len("TEMPLATE/"):]
        entry = registered.get(rel)
        if entry is None:
            continue  # (c) unregistered: the shipped audit never runs it there
        if rel in declared:
            continue  # (b) a declared skip, its marker verified against the source
        if carries_at_shipped_depth(top, rel, entry):
            continue  # (a) the shipped depth carries the subject
        how = "added" if touched[path] == "A" else "modified"
        problems.append(
            f"{path} ({how}) — REGISTERED in the shipped audit and UNPAIRED: it does "
            f"not carry at the shipped depth and `docs/shipped-audit-skips.json` does "
            f"not declare it"
        )
    return problems


def _write_gate(path: Path, code: int, name: str) -> None:
    """A minimal shipped-shaped gate that exits `code`."""
    path.write_text(
        f'#!/usr/bin/env python3\n"""Gate: {name}."""\n'
        "import sys\n\n\n"
        f"def main() -> int:\n    return {code}\n\n\n"
        'if __name__ == "__main__":\n    sys.exit(main())\n',
        encoding="utf-8",
    )


def _stage_only(top: Path, paths: list[str]) -> None:
    """Reset the index, then stage exactly `paths` — so each arm isolates one change."""
    _git(top, "reset", "-q")
    for path in paths:
        _git(top, "add", "--", path)


def _probe() -> list[str]:
    """Every arm, on a synthetic tree.

    The two arms that matter are criterion 2 of #488: a synthetic commit ADDING such a
    gate is reported, and the SAME gate with its skip declared is not. A control that
    passes on both arms would be the defect this item is about, one level up — so the
    arms assert the predicate both REPORTS and CLEARS.
    """
    with tempfile.TemporaryDirectory() as tmp:
        top = Path(tmp)
        (top / "TEMPLATE" / "tests").mkdir(parents=True)
        (top / "TEMPLATE" / "tools").mkdir(parents=True)
        (top / "docs").mkdir(parents=True)

        audit = top / "TEMPLATE" / "tools" / "audit.py"
        # The registrations are written in the SHIPPED audit's own form — double-quoted
        # string constants — because `gate_registry._QUOTED` reads that form and only it.
        # A single-quoted fixture would make every arm vacuous: the parser would find no
        # target, `registered_shipped_gates` would come back empty, and the predicate
        # would clear every gate by arm (c). Measured on this probe's first run.
        audit.write_text(
            'import sys\n\n'
            'gates_to_run = []\n'
            'gates_to_run.append([sys.executable, "tests/test_probe_red.py"])\n'
            'gates_to_run.append([sys.executable, "tests/test_probe_green.py"])\n',
            encoding="utf-8",
        )
        declared_path = top / "docs" / "shipped-audit-skips.json"
        declared_path.write_text(json.dumps({"skips": {}}), encoding="utf-8")

        red = top / "TEMPLATE" / "tests" / "test_probe_red.py"
        green = top / "TEMPLATE" / "tests" / "test_probe_green.py"
        other = top / "TEMPLATE" / "tests" / "test_probe_unregistered.py"
        _write_gate(red, 1, "a probe the shipped depth cannot carry")
        _write_gate(green, 0, "a probe the shipped depth carries")
        _write_gate(other, 1, "a probe the shipped audit does not register")

        _git(top, "init", "-q")
        _git(top, "config", "user.email", "probe@example.invalid")
        _git(top, "config", "user.name", "probe")
        _git(top, "add", "--", "TEMPLATE/tools/audit.py", "docs/shipped-audit-skips.json")
        _git(top, "commit", "-q", "-m", "base: the shipped audit and an empty declaration")

        # ARM 1 — the class itself: added, registered, undeclared, cannot carry.
        _stage_only(top, ["TEMPLATE/tests/test_probe_red.py"])
        check("ARM 1: an ADDED registered gate the shipped depth cannot carry is REPORTED",
              unpaired_gates(top) == [
                  "TEMPLATE/tests/test_probe_red.py (added) — REGISTERED in the shipped "
                  "audit and UNPAIRED: it does not carry at the shipped depth and "
                  "`docs/shipped-audit-skips.json` does not declare it"],
              str(unpaired_gates(top)))

        # ARM 2 — criterion 2's second half: the SAME gate, with its skip declared.
        declared_path.write_text(json.dumps({"skips": {
            "tests/test_probe_red.py": {"marker": "# STATED SKIP: probe"}}}), encoding="utf-8")
        _stage_only(top, ["TEMPLATE/tests/test_probe_red.py",
                          "docs/shipped-audit-skips.json"])
        check("ARM 2: the SAME gate with its skip DECLARED is not reported",
              unpaired_gates(top) == [], str(unpaired_gates(top)))

        # ARM 3 — the instrument can CLEAR as well as report: a gate the depth carries.
        _stage_only(top, ["TEMPLATE/tests/test_probe_green.py"])
        check("ARM 3: an ADDED registered gate the shipped depth CARRIES is not reported",
              unpaired_gates(top) == [], str(unpaired_gates(top)))

        # ARM 4 — (c): a gate the shipped audit never runs cannot red there.
        _stage_only(top, ["TEMPLATE/tests/test_probe_unregistered.py"])
        check("ARM 4: an ADDED gate the shipped audit does NOT register is not reported",
              unpaired_gates(top) == [], str(unpaired_gates(top)))

        # ARM 5 — MODIFIED, not added: the leg/subject-root case, one level down. A gate
        # already committed, edited so its shipped-depth verdict flips to red.
        _git(top, "add", "--", "TEMPLATE/tests/test_probe_green.py")
        _git(top, "commit", "-q", "-m", "the green probe lands")
        _write_gate(green, 1, "the green probe, edited to stop carrying")
        _stage_only(top, ["TEMPLATE/tests/test_probe_green.py"])
        check("ARM 5: a MODIFIED registered gate that stops carrying is REPORTED",
              unpaired_gates(top) == [
                  "TEMPLATE/tests/test_probe_green.py (modified) — REGISTERED in the "
                  "shipped audit and UNPAIRED: it does not carry at the shipped depth "
                  "and `docs/shipped-audit-skips.json` does not declare it"],
              str(unpaired_gates(top)))

        # ARM 6 — the registration's ARGUMENTS are part of the invocation (#509). A target
        # registered with a SUBCOMMAND exits 0 only when it receives it; the runner-kind
        # form ran it bare, argparse exited 2, and the depth was declared unable to carry
        # a gate it carries. The real instance is `tools/ledger.py verify`, which is
        # registered with its subcommand and reds on ANY touch of the file.
        subcmd = top / "TEMPLATE" / "tools" / "test_probe_subcmd.py"
        subcmd.write_text(
            '#!/usr/bin/env python3\n"""Gate: carries only when the registration\'s own '
            'subcommand reaches it."""\n'
            "import sys\n\n\n"
            "def main() -> int:\n"
            '    return 0 if "verify" in sys.argv else 2\n\n\n'
            'if __name__ == "__main__":\n    sys.exit(main())\n',
            encoding="utf-8",
        )
        subcmd_red = top / "TEMPLATE" / "tools" / "test_probe_subcmd_red.py"
        _write_gate(subcmd_red, 1, "registered with arguments and still red")
        placeholder = top / "TEMPLATE" / "tools" / "test_probe_placeholder.py"
        _write_gate(placeholder, 0, "carries, but its registration cannot be rebuilt")
        audit.write_text(
            audit.read_text(encoding="utf-8")
            + 'gates_to_run.append([sys.executable, "tools/test_probe_subcmd.py", "verify"])\n'
            + 'gates_to_run.append([sys.executable, "tools/test_probe_subcmd_red.py", "verify"])\n'
            + 'gates_to_run.append([sys.executable, "tools/test_probe_placeholder.py", '
              'str(SOME_BOUND)])\n',
            encoding="utf-8",
        )
        # Stage ONLY the audit: a bare `add` here would carry ARM 5's staged probe into
        # this commit, leaving the control below with an empty population to read.
        _stage_only(top, ["TEMPLATE/tools/audit.py"])
        _git(top, "commit", "-q", "-m", "the arguments-bearing registrations land")

        _stage_only(top, ["TEMPLATE/tools/test_probe_subcmd.py"])
        check("ARM 6: a registration's ARGUMENTS are honoured — a subcommand target that "
              "carries WITH them is not reported",
              unpaired_gates(top) == [], str(unpaired_gates(top)))

        _stage_only(top, ["TEMPLATE/tools/test_probe_subcmd_red.py"])
        check("ARM 7: honouring the arguments is not a blanket excuse — the same shape "
              "that still exits non-zero WITH them IS reported",
              unpaired_gates(top) == [
                  "TEMPLATE/tools/test_probe_subcmd_red.py (added) — REGISTERED in the "
                  "shipped audit and UNPAIRED: it does not carry at the shipped depth "
                  "and `docs/shipped-audit-skips.json` does not declare it"],
              str(unpaired_gates(top)))

        _stage_only(top, ["TEMPLATE/tools/test_probe_placeholder.py"])
        check("ARM 8: a registration carrying an UNRESOLVABLE placeholder is reported, "
              "never guessed — a bound computed at run time cannot be rebuilt here",
              unpaired_gates(top) == [
                  "TEMPLATE/tools/test_probe_placeholder.py (added) — REGISTERED in the "
                  "shipped audit and UNPAIRED: it does not carry at the shipped depth "
                  "and `docs/shipped-audit-skips.json` does not declare it"],
              str(unpaired_gates(top)))

        # THE WORKING-INSTRUMENT CONTROL. A zero is a verdict only from an instrument
        # that could have read non-zero: the predicate must SEE the staged population
        # before its silence on a clean index means anything. The arms above re-stage the
        # index, so it is put back to ARM 5's population rather than assumed.
        _stage_only(top, ["TEMPLATE/tests/test_probe_green.py"])
        check("CONTROL: the instrument reads the staged population it is judging",
              touched_shipped_gates(top) == {"TEMPLATE/tests/test_probe_green.py": "M"},
              str(touched_shipped_gates(top)))
        _git(top, "reset", "-q")
        check("CONTROL: an empty index is empty, not unread", unpaired_gates(top) == [],
              str(unpaired_gates(top)))

    return list(_failures)


def wiring_problems() -> list[str]:
    """The gate must be WIRED UP, or its own registration is the dead text P29 forbids."""
    problems: list[str] = []
    if not SHIPPED.is_dir():
        return problems  # the shipped depth: main() skips before this is reached
    root_audit = REPO / "tools" / "audit.py"
    shipped_audit = SHIPPED / "tools" / "audit.py"
    for label, audit in (("root", root_audit), ("shipped", shipped_audit)):
        text = audit.read_text(encoding="utf-8") if audit.is_file() else ""
        if "tests/test_template_gate_pairing.py" not in text:
            problems.append(f"the {label} audit does not register this gate")
    twin = SHIPPED / "tests" / "test_template_gate_pairing.py"
    if not twin.is_file():
        problems.append("the shipped twin of this gate is absent")
    elif twin.read_bytes() != Path(__file__).read_bytes():
        problems.append("the shipped twin of this gate is not byte-identical")
    declared = declared_skips(REPO)
    if "tests/test_template_gate_pairing.py" not in declared:
        problems.append("its own shipped depth is NOT declared in "
                        "docs/shipped-audit-skips.json (criterion 4)")
    elif STATED_SKIP not in Path(__file__).read_text(encoding="utf-8"):
        problems.append(f"the declared skip's marker {STATED_SKIP!r} is not in this source")
    return problems


def main() -> int:
    print("template gate pairing — a shipped gate this commit touches must be PAIRED (#488)")

    if not SHIPPED.is_dir():
        # The shipped depth: this tree carries no nested TEMPLATE/ and no
        # `docs/shipped-audit-skips.json`, so the population it judges is absent rather
        # than clean. A bootstrapped factory lands here too, and it inherits the template's
        # CONTENTS rather than a second copy of them.
        print(f"  {STATED_SKIP} no nested TEMPLATE/ at this depth, so there is no shipped "
              f"gate population for this leg to judge (#488)")
        return 0

    problems = wiring_problems()
    for problem in problems:
        print(f"  FAIL  {problem}")

    _probe()

    staged = unpaired_gates(REPO)
    touched = touched_shipped_gates(REPO)
    print(f"  population: {len(touched)} shipped gate(s) touched by this commit; "
          f"{len(staged)} unpaired")
    for entry in staged:
        print(f"  FAIL  {entry}")

    if problems or _failures or staged:
        print(f"template gate pairing FAILED — {len(problems)} wiring, "
              f"{len(_failures)} probe, {len(staged)} unpaired")
        return 1
    print("template gate pairing passed — every probe bit, and no touched shipped gate is "
          "unpaired")
    return 0


if __name__ == "__main__":
    sys.exit(main())
