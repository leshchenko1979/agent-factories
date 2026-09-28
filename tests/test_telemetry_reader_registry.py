#!/usr/bin/env python3
r"""Gate: no module reads a telemetry field out of `detail` except through the predicate.

Origin: #99, ruled at ledger `n=599`. The class is the prose-as-data class (#88, `n=405`
clause 5) at its FIFTH call site: a module that parses `turns=`, `cost_usd=`,
`tokens_out=` and friends out of a row's free-prose `detail` with its own reading. Each
site was repaired one at a time and the class simply moved to the next module, because a
repair fixes an INSTANCE and only a mechanism fixes the CLASS. `tools/field_predicate.py`
is the one reading; this gate is what keeps it the one reading.

WHAT A CANDIDATE IS, and why the predicate is not "the file mentions a telemetry key"
------------------------------------------------------------------------------------
Triage measured the blunt form first and it does not survive contact with the live tree.
A scan for telemetry-shaped STRINGS across `tools/` reports three modules that do not
import the predicate, and only ONE is a call site:

  `tools/synthesize_insights.py`  a genuine private reader — the site #99 repaired.
  `tools/telemetry.py`            the WRITER: `format_detail_string` BUILDS the tokens.
                                  Constructing `turns=5` is the opposite of reading it.
  `tools/patrol_host_state.py`    a false positive. Line 57 carries the word `turns`
                                  inside the word "re-turns" of a prose message.

A gate that cannot tell those apart needs an allow-list for a false positive, and an
allow-list entry granted to a non-defect is a permanent weakening. So the predicate is
AST-based and reads the SHAPE, never the substring. Two candidate legs:

* **READER** (hard, no exemption surface): the module calls a `re` scanner
  (`search`/`match`/`fullmatch`/`findall`/`finditer`/`compile`/`sub`) on a LITERAL pattern
  that names a telemetry key as a word. This is the exact shape every private scan in this
  class has taken — `re.search(r"turns=(\d+)", detail)`, `re.search(r"cost_usd=([\d\.]+)")`
  — and the live trees carry ZERO of them, so the leg costs nothing and catches the shape
  wherever it next appears.
* **WRITER** (allow-listed): the module carries a non-docstring string constant holding a
  `key=` telemetry token, i.e. it constructs a trailer. A module may do this legitimately
  and the writer is named in `WRITER_MODULES` below.

Both legs demand the same discharge: the module must IMPORT the shared predicate AND
reference a name it imports. Importing without calling is the dodge this closes — the
module would read green while parsing privately.

THE ALLOW-LIST IS SOURCE, NOT FACTORY DATA — and that is a deliberate departure
--------------------------------------------------------------------------------
`tests/test_rework_relative_revision.py` and `tests/test_ledger_no_shrink.py` keep their
exemptions in `docs/*.json`, because those exemptions name pre-gate INSTANCES in a
factory's own history. This list names a CLASSIFICATION of the tools the template SHIPS:
`telemetry.py` is the writer in every tree, so its entry is structural and must travel
byte-identically with the code it describes. Hence the inline dict, and hence the
byte-identical copy — the alternative, factory data with a skeleton, would RED in a fresh
bootstrapped factory until the factory declared a writer the template already ships.

A factory that adds its own writer edits this dict in its own copy; the meta-factory's
copy stays byte-identical because the meta-factory does not carry a member's tools.

BOOTSTRAPPED-FACTORY CLASSIFICATION: the gate scans `tools/` relative to the repo root and
carries no meta-factory-only dependency, so it RUNS in a bootstrapped factory and PASSES
there — measured, not assumed: `TEMPLATE/tools/` yields the same candidate set minus
`synthesize_insights.py`, which does not ship, and its one writer is the same
`telemetry.py`. So it ships as a copy and is classified REQUIRED in
`tests/gate_registry.py`. The TEMPLATE coupling leg below runs only where a `TEMPLATE/`
tree exists, and SKIPS with its reason stated elsewhere.

Run:  python3 tests/test_telemetry_reader_registry.py
Exit: 0 every candidate discharges through the predicate or the declared writer list.
"""

from __future__ import annotations

import ast
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
from field_predicate import TELEMETRY_KEYS  # noqa: E402 — the keys, named once

PREDICATE = (
    "no module under tools/ reads a telemetry field out of a row's `detail` except "
    "through tools/field_predicate.py"
)

# The writers: modules that CONSTRUCT `key=value` trailer tokens rather than read them.
# Keyed by path relative to the scanned tools directory, with the reason it is a writer.
WRITER_MODULES: dict[str, str] = {
    "telemetry.py": (
        "the WRITER — `format_detail_string` builds the canonical trailer "
        "(`f\"turns={turns}\"`, `f\"cost_usd={cost:.4f}\"`). Constructing a token is the "
        "opposite of reading one, so there is no predicate call for it to make."
    ),
}

SCANNERS = ("search", "match", "fullmatch", "findall", "finditer", "compile", "sub")
TOKEN = re.compile(r"\b(" + "|".join(TELEMETRY_KEYS) + r")=")
KEY_WORD = re.compile(r"\b(" + "|".join(TELEMETRY_KEYS) + r")\b")


def _docstring_ids(tree: ast.AST) -> set[int]:
    """The `id()` of every string constant that is a DOCSTRING, so prose is never a hit.

    A module's own docstring discusses the class in full — this file's docstring names
    every telemetry key — so a scan that read docstrings would report every gate that
    documents the rule it enforces.
    """
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                found.add(id(body[0].value))
    return found


def _predicate_names_used(tree: ast.AST) -> set[str]:
    """The `field_predicate` names the module imports AND references.

    Both halves are load-bearing: `import field_predicate` alone is a line, not a call,
    and a module that imports the predicate and then parses privately would read green.
    """
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "field_predicate":
            imported.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "field_predicate":
                    imported.add(alias.asname or "field_predicate")
    if not imported:
        return set()
    referenced = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    referenced |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    return imported & referenced


def _reader_scan(tree: ast.AST) -> list[tuple[int, str]]:
    """`(lineno, pattern)` for every `re.<scanner>` call on a literal naming a telemetry key."""
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        target = node.func.value
        if not isinstance(target, ast.Name) or target.id != "re":
            continue
        if node.func.attr not in SCANNERS or not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            if KEY_WORD.search(first.value):
                hits.append((node.lineno, first.value))
    return hits


def _writer_scan(tree: ast.AST) -> list[tuple[int, str]]:
    """`(lineno, token)` for every telemetry token in a NON-docstring string constant."""
    docstrings = _docstring_ids(tree)
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstrings:
                continue
            match = TOKEN.search(node.value)
            if match:
                hits.append((node.lineno, match.group(0)))
    return hits


def module_problems(rel: str, source: str) -> list[str]:
    """The problems for ONE module, or `[]` when it discharges its candidates."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"tools/{rel}: cannot be parsed — {exc} (an unreadable module is not a clean one)"]

    used = _predicate_names_used(tree)
    readers = _reader_scan(tree)
    writers = _writer_scan(tree)

    if not readers and not writers:
        return []

    if used:
        return []

    problems: list[str] = []
    for lineno, pattern in readers:
        problems.append(
            f"tools/{rel}:{lineno}: PRIVATE READER — `re` scans the detail for a telemetry "
            f"key (pattern {pattern!r}) without the shared predicate. Import "
            f"`field_predicate` and read the field through `declared_telemetry`."
        )
    if writers and rel not in WRITER_MODULES:
        lines = ", ".join(str(lineno) for lineno, _ in writers)
        problems.append(
            f"tools/{rel}: constructs telemetry tokens at line(s) {lines} and neither reads "
            f"through the shared predicate nor is a DECLARED writer. A reader must import "
            f"`field_predicate`; a genuine writer is declared in `WRITER_MODULES` with its "
            f"reason."
        )
    return problems


def scan_tree(tools_dir: Path) -> tuple[list[str], list[str], list[str]]:
    """`(problems, examined, excused)` for one tools directory.

    `excused` names every allow-list entry that MATCHED, so the printed output states what
    was set aside and a clean run is never confused with an unexamined one.
    """
    problems: list[str] = []
    examined: list[str] = []
    excused: list[str] = []
    if not tools_dir.is_dir():
        return [f"{tools_dir}: no such tools directory"], examined, excused
    for path in sorted(tools_dir.glob("*.py")):
        if path.name == "field_predicate.py":
            continue  # the predicate itself: the one module that must read tokens directly
        examined.append(path.name)
        found = module_problems(path.name, path.read_text(encoding="utf-8"))
        problems.extend(found)
        if not found and path.name in WRITER_MODULES:
            excused.append(f"{path.name} — {WRITER_MODULES[path.name]}")
    return problems, examined, excused


def evaluate(repo: Path = REPO) -> tuple[list[str], list[str], list[str], list[str]]:
    """`(problems, examined, excused, notes)` over the live tree and, when present, TEMPLATE."""
    tools_dir = repo / "tools"
    problems, examined, excused = scan_tree(tools_dir)
    notes = [
        f"population: {len(examined)} module(s) under {tools_dir.name}/ "
        f"({', '.join(examined)})"
    ]

    template_tools = repo / "TEMPLATE" / "tools"
    if template_tools.is_dir():
        t_problems, t_examined, t_excused = scan_tree(template_tools)
        problems.extend(t_problems)
        notes.append(
            f"coupling leg: {len(t_examined)} module(s) under TEMPLATE/tools/ "
            f"(meta-factory-only — a bootstrapped factory has no TEMPLATE/ tree)"
        )
        excused.extend(f"TEMPLATE/{entry}" for entry in t_excused)
    else:
        notes.append(
            "coupling leg: SKIPPED — no TEMPLATE/ tree. The main leg above is the whole "
            "verdict in a bootstrapped factory, and this gate PASSES there."
        )

    for name, reason in sorted(WRITER_MODULES.items()):
        notes.append(f"allow-list: {name} — {reason}")
    return problems, examined, excused, notes


def main(repo: Path = REPO) -> int:
    """Script form: the verdict with the population and the allow-list on STDOUT.

    `repo` is a parameter so a probe can exercise the printed form against a synthetic
    tree; the population and the allow-list are printed on EVERY run, so `clean` and
    `examined nothing` are never the same output.
    """
    problems, _examined, excused, notes = evaluate(repo)
    for note in notes:
        print(f"  {note}")
    for line in excused:
        print(f"  excused: {line}")
    if problems:
        print("telemetry-reader registry gate FAILED:", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        return 1
    print(
        f"telemetry-reader registry gate: clean — {len(problems)} private reader(s), "
        f"{len(WRITER_MODULES)} declared writer(s), {len(excused)} excused"
    )
    return 0


# --- probes: a rule that has only seen good input has not been shown to reject bad input


def _probe_tree(root: Path, modules: dict[str, str]) -> Path:
    tools = root / "tools"
    tools.mkdir(parents=True, exist_ok=True)
    (tools / "field_predicate.py").write_text(
        (REPO / "tools" / "field_predicate.py").read_text(encoding="utf-8"), encoding="utf-8"
    )
    for name, source in modules.items():
        (tools / name).write_text(source, encoding="utf-8")
    return root


_PRIVATE_READER = (
    "import json\n"
    "import re\n"
    "\n"
    "def mine(path):\n"
    "    total = 0.0\n"
    "    for line in path.read_text().splitlines():\n"
    "        row = json.loads(line)\n"
    "        match = re.search(r'cost_usd=([\\d\\.]+)', row.get('detail', ''))\n"
    "        if match:\n"
    "            total += float(match.group(1))\n"
    "    return total\n"
)

_PREDICATE_READER = (
    "import json\n"
    "import field_predicate as _fields\n"
    "\n"
    "def mine(path):\n"
    "    total = 0.0\n"
    "    for line in path.read_text().splitlines():\n"
    "        row = json.loads(line)\n"
    "        for key, value in _fields.declared_telemetry(row.get('detail', '')):\n"
    "            if key == 'cost_usd':\n"
    "                total += float(value)\n"
    "    return total\n"
)

_PROSE_SUBSTRING = (
    "MESSAGE = 'set_goal over tests/ and tools/ returns only tools/registry_render.py'\n"
)


def test_probe_a_private_reader_fails(tmp_path: Path) -> None:
    """Criterion 1, negative half: a module parsing a telemetry field privately FAILS."""
    tree = _probe_tree(tmp_path / "private", {"miner.py": _PRIVATE_READER})
    problems, _examined, _excused, _notes = evaluate(tree)
    assert problems, "a private reader must be reported"
    assert "PRIVATE READER" in problems[0], problems
    # The line is DERIVED from the fixture, never hand-counted: a literal here would be a
    # second copy of the fixture's shape, and editing the fixture would silently decouple
    # the assertion from what the gate reports (the first draft asserted 5; it is 8).
    expected_line = _PRIVATE_READER[: _PRIVATE_READER.index("re.search")].count("\n") + 1
    assert f"miner.py:{expected_line}" in problems[0], problems


def test_probe_a_predicate_reader_passes(tmp_path: Path) -> None:
    """Criterion 1, positive half: the same job through the predicate PASSES."""
    tree = _probe_tree(tmp_path / "shared", {"miner.py": _PREDICATE_READER})
    problems, examined, _excused, _notes = evaluate(tree)
    assert problems == [], problems
    assert "miner.py" in examined, examined


def test_probe_an_import_without_a_call_is_not_a_discharge(tmp_path: Path) -> None:
    """The dodge the `imported AND referenced` rule closes: import the predicate, parse
    privately anyway. A gate reading only the import would pass this module."""
    source = "import field_predicate\n" + _PRIVATE_READER
    tree = _probe_tree(tmp_path / "dodge", {"miner.py": source})
    problems, _examined, _excused, _notes = evaluate(tree)
    assert problems, "importing the predicate without calling it must not discharge a reader"


def test_probe_an_undeclared_writer_fails(tmp_path: Path) -> None:
    """A module that CONSTRUCTS tokens is a candidate too, and undeclared it FAILS."""
    source = "def render(turns):\n    return f'turns={turns} cost_usd=1.0'\n"
    tree = _probe_tree(tmp_path / "writer", {"builder.py": source})
    problems, _examined, _excused, _notes = evaluate(tree)
    assert problems, "an undeclared writer must be reported"
    assert "DECLARED writer" in problems[0], problems


def test_probe_a_declared_writer_is_excused_and_printed(tmp_path: Path, capsys) -> None:
    """The allow-list is PRINTED every run, so clean and excused are never one output."""
    source = "def render(turns):\n    return f'turns={turns} cost_usd=1.0'\n"
    tree = _probe_tree(tmp_path / "declared", {"telemetry.py": source})
    problems, _examined, excused, _notes = evaluate(tree)
    assert problems == [], problems
    assert excused and "telemetry.py" in excused[0], excused
    assert main(tree) == 0
    out = capsys.readouterr().out
    assert "excused: telemetry.py" in out, out
    assert "allow-list: telemetry.py" in out, out


def test_probe_a_prose_substring_is_not_a_candidate(tmp_path: Path) -> None:
    """`patrol_host_state.py:57` carries `turns` inside "re-turns". The blunt string scan
    reported it and needed an allow-list entry to survive; the AST shape does not see it,
    so the false positive is excluded rather than excused."""
    tree = _probe_tree(tmp_path / "prose", {"patrol.py": _PROSE_SUBSTRING})
    problems, examined, excused, _notes = evaluate(tree)
    assert problems == [], problems
    assert excused == [], excused
    assert "patrol.py" in examined, "the module is still EXAMINED — it is just not a candidate"


def test_probe_an_unparseable_module_fails_rather_than_skipping(tmp_path: Path) -> None:
    """An unreadable module is not a clean one: a silent skip is the vacuous pass."""
    tree = _probe_tree(tmp_path / "broken", {"broken.py": "def (:\n"})
    problems, _examined, _excused, _notes = evaluate(tree)
    assert problems and "cannot be parsed" in problems[0], problems


def test_probe_a_docstring_naming_every_key_is_not_a_candidate(tmp_path: Path) -> None:
    """This file's own docstring names every telemetry key. A scan reading docstrings
    would report every gate that documents the rule it enforces."""
    source = '"""Docstring naming turns= and cost_usd= and tokens_out= openly."""\nX = 1\n'
    tree = _probe_tree(tmp_path / "docstring", {"doc.py": source})
    problems, _examined, excused, _notes = evaluate(tree)
    assert problems == [] and excused == [], (problems, excused)


def test_probe_the_live_trees_are_clean() -> None:
    """The verdict over the real tree — and the population is asserted non-empty, so a
    scan that examined nothing cannot report the same green as one that examined all."""
    problems, examined, _excused, _notes = evaluate(REPO)
    assert problems == [], problems
    assert len(examined) >= 8, f"population too small to be meaningful: {examined}"
    # A TOOL THAT SHIPS IN EVERY TREE, not one that happens to live here (#199).
    # `synthesize_insights.py` is repo-side only — the kit does not carry it — so naming it
    # made this probe a statement about THIS repo's layout and it failed in the tree the kit
    # ships. `audit.py` is in the scanned population of both, so the property the probe owes
    # ("the population is the real tree, not a stub") holds wherever it runs.
    assert "audit.py" in examined, examined


def test_probe_the_printed_form_states_its_population_and_allow_list(capsys) -> None:
    assert main(REPO) == 0
    out = capsys.readouterr().out
    assert "population:" in out, out
    assert "allow-list: telemetry.py" in out, out
    assert "clean —" in out, out


def test_probe_the_gate_passes_in_a_bootstrapped_factory(tmp_path: Path) -> None:
    """The classification this gate carries: it RUNS and PASSES where no TEMPLATE/ tree
    exists, which is what makes it shippable as a REQUIRED gate rather than optional."""
    tree = _probe_tree(tmp_path / "factory", {"telemetry.py": "def f(t):\n    return f'turns={t}'\n"})
    problems, examined, _excused, notes = evaluate(tree)
    assert problems == [], problems
    assert any("SKIPPED" in note for note in notes), notes
    assert "telemetry.py" in examined, examined


if __name__ == "__main__":
    raise SystemExit(main())
