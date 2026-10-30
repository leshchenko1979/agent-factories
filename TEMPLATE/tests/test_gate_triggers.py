#!/usr/bin/env python3
"""Gate: the trigger map covers every gate, and an uncovered path NEVER buys a subset.

#294. The audit's pre-commit remedy was unexecutable: 54 gates / 1387.9 s measured against
5592.1 s of caps and a 600 s inline ceiling. HQ ruled the fix is to select by BLAST RADIUS
with DEFAULT-DENY -- a change names the paths it touches, the map turns those into the gates
that read them, and ANY path the map cannot cover buys the full suite rather than a guess.

Two properties are load-bearing and each is a probe here:

  * COVERAGE -- every gate the audit registers is reachable from the map (as a key, or on the
    floor). A gate missing from the map is a gate no change can ever select, which is a gate
    that has silently stopped running.
  * DEFAULT-DENY -- an uncovered path returns the FULL set. This is the one that must go RED
    the instant someone guts the branch, so the probe drives `select` with a synthetic
    mapping and compares the result against BOTH the full set and the union of matches: a
    gutted branch returns the union, and the two differ by exactly the gates the uncovered
    path could have needed.

Run: python3 tests/test_gate_triggers.py   (rc=0 clean)
"""
from __future__ import annotations

import importlib.util
import re
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GATE_SELECT = REPO / "tools" / "gate_select.py"
LIVE_MAP = REPO / "registry" / "gate_triggers.json"
EXAMPLE_MAP = REPO / "TEMPLATE" / "registry" / "gate_triggers.example.json"
AUDIT = REPO / "tools" / "audit.py"
GATE_REGISTRY = REPO / "tests" / "gate_registry.py"
REWORK_TABLE = REPO / "tests" / "rework_table.py"
GATE_BUDGET = REPO / "tools" / "gate_budget.py"

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"PASS -- {label}")
    else:
        print(f"FAIL -- {label}{': ' + detail if detail else ''}")
        FAILURES.append(label)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _selector():
    return _load("oc_gate_select_map", GATE_SELECT)


# --- the absence contract (#199 / #322) --------------------------------------------
# STATED SKIP: registry/gate_triggers.json (factory data)
# THE MAP IS FACTORY DATA. The kit ships `registry/gate_triggers.example.json`, and a
# factory copies it to the live name (TEMPLATE/BOOTSTRAP.md) — so at the SHIPPED depth
# there is no map to resolve: `load_map` looks for the example under a nested `TEMPLATE/`,
# which only the ROOT tree has, and the five probes below that read the map have no
# subject. That is the #199 class — a gate that cannot pass in the tree it ships from —
# and its remedy is the #229 shape: the absence is DECLARED, never silent. The reason is
# stated here, and `tests/test_shipped_audit_runs.py` asserts this marker line is present.
#
# BOTH INVOCATION MODES MUST REACH THE GUARD (#195). The audit invokes this gate in
# PYTEST mode, and pytest never calls `main()`, so a guard there would protect only the
# script-mode run. `pytestmark` COLLECTS the tests and skips them (exit 0); a module-level
# `pytest.skip` would exit 5, which the audit reads as a failure.
def _map_skip_reason(root: Path) -> str:
    """A stated reason when no trigger map resolves in this tree, else "".

    The predicate is the SELECTOR's OWN `load_map`, never a second parse of the same
    absence (`docs/instruments/ledger.md` §9.8 "One field, one predicate"): if the
    instrument cannot read a map, the gate that judges the map has no subject — and the two
    can never disagree about which map is in force. A MISSING SELECTOR is not a skip: that
    is a defect, and it must FAIL.
    """
    if not GATE_SELECT.is_file():
        return ""
    try:
        mapping = _selector().load_map(root)
    except Exception:  # noqa: BLE001 — an unreadable selector is a FAIL, never a skip
        return ""
    if mapping is not None:
        return ""
    return (
        "no gate trigger map resolves in this tree: neither "
        f"{root / 'registry' / 'gate_triggers.json'} nor "
        f"{root / 'TEMPLATE' / 'registry' / 'gate_triggers.example.json'} is readable. "
        "The map is FACTORY DATA — the kit ships registry/gate_triggers.example.json and a "
        "factory copies it to the live name — so the shipped tree has no map to judge"
    )


_SKIP_REASON = _map_skip_reason(REPO)
if _SKIP_REASON:
    import pytest as _pytest  # noqa: E402

    pytestmark = _pytest.mark.skipif(True, reason=_SKIP_REASON)


def _live_map() -> dict:
    """The map this tree resolves, through the SELECTOR's own loader.

    Not a direct read of `registry/gate_triggers.json`: a factory copies the shipped
    example to that path (TEMPLATE/BOOTSTRAP.md), and reading the path directly would make
    this gate fail in every tree that has not renamed the file yet — a gate that cannot
    pass where it is copied is the P36 defect. The selector resolves live-then-example, so
    the gate and the instrument cannot disagree about which map is in force.
    """
    mapping = _selector().load_map(REPO)
    if mapping is None:
        raise SystemExit(
            "FAIL -- no gate trigger map resolves in this tree: neither "
            f"{LIVE_MAP} nor {EXAMPLE_MAP} is readable. Copy the shipped map:\n"
            f"    cp {EXAMPLE_MAP} {LIVE_MAP}"
        )
    return mapping


def probe_every_registered_gate_is_covered() -> None:
    """Every gate the audit registers is a map key or sits on the floor."""
    module = _load("oc_gate_select_cover", GATE_SELECT)
    commands = module.registered_commands(REPO)
    mapping = _live_map()
    keys, floor = set(mapping.get("gates", {})), set(mapping.get("floor", []))
    missing = sorted(set(commands) - keys - floor)
    print(
        f"population: {len(commands)} registered gate(s), {len(keys)} map key(s), "
        f"{len(floor)} floor entr(y/ies)"
    )
    check(
        "the instrument can see the registration it judges",
        len(commands) > 0,
        f"registered_commands() returned {len(commands)} -- a clean verdict over an empty "
        f"population is not a verdict",
    )
    check(
        "every registered gate is reachable from the map",
        not missing,
        f"{len(missing)} gate(s) no change can select: {missing[:3]}",
    )


def probe_every_map_key_is_registered() -> None:
    """No key names a gate the audit does not register -- a stale key selects nothing."""
    module = _load("oc_gate_select_stale", GATE_SELECT)
    commands = set(module.registered_commands(REPO))
    keys = set(_live_map().get("gates", {}))
    stale = sorted(keys - commands)
    check(
        "no map key names a gate that is not registered",
        not stale,
        f"{len(stale)} stale key(s): {stale[:3]}",
    )


def probe_the_map_is_well_formed() -> None:
    """Shape: a stated default, a list floor, and non-empty string globs per gate."""
    mapping = _live_map()
    gates = mapping.get("gates", {})
    problems = [
        f"{gate}: empty or non-list globs"
        for gate, globs in gates.items()
        if not isinstance(globs, list) or not globs
    ]
    problems += [
        f"{gate}: non-string glob {glob!r}"
        for gate, globs in gates.items()
        if isinstance(globs, list)
        for glob in globs
        if not isinstance(glob, str) or not glob
    ]
    check("every gate carries at least one string glob", not problems, str(problems[:3])[:160])
    check(
        "the map DECLARES its default as `full` -- default-deny is stated, not inferred",
        mapping.get("default") == "full",
        f"default={mapping.get('default')!r}",
    )
    check(
        "the floor is a list",
        isinstance(mapping.get("floor"), list),
        f"floor={type(mapping.get('floor')).__name__}",
    )


def probe_the_example_carries_the_same_shape() -> None:
    """The shipped example is what a factory inherits -- it must name the same gates."""
    if not EXAMPLE_MAP.is_file():
        print(f"STATED SKIP -- {EXAMPLE_MAP} is absent from this tree, so the shipped shape "
              "cannot be compared; the resolved map was judged above")
        return
    example = json.loads(EXAMPLE_MAP.read_text(encoding="utf-8"))
    live = _live_map()
    check(
        "the example map names exactly the gates the live map names",
        set(example.get("gates", {})) == set(live.get("gates", {})),
        f"example={len(example.get('gates', {}))} live={len(live.get('gates', {}))}",
    )
    check(
        "the example states the same default and floor",
        example.get("default") == live.get("default")
        and set(example.get("floor", [])) == set(live.get("floor", [])),
        f"default={example.get('default')!r} floor={example.get('floor')!r}",
    )


def probe_globs_over_include_deliberately() -> None:
    """`*` crosses `/`: over-inclusion costs time, a silent miss costs correctness."""
    module = _load("oc_gate_select_glob", GATE_SELECT)
    check(
        "a `*` glob reaches a nested path",
        module.glob_matches("tools/*", "tools/nested/deep.py") is True,
        "fnmatch `*` no longer crosses `/` -- the map's coverage claim would weaken",
    )
    check(
        "and it still refuses a path outside the prefix",
        module.glob_matches("tools/*", "tests/x.py") is False,
    )


def probe_a_covered_change_selects_a_subset() -> None:
    """The money shot, direction one: a covered path yields the gates that read it."""
    module = _load("oc_gate_select_subset", GATE_SELECT)
    mapping = _live_map()
    result = module.select(mapping, ["evidence/rework.md"])
    check(
        "a covered change selects a subset",
        result["mode"] == "subset" and result["default_deny"] is False,
        f"mode={result['mode']} default_deny={result['default_deny']}",
    )
    check(
        "and the floor is always in it",
        set(mapping.get("floor", [])) <= set(result["gates"]),
        f"floor absent from {result['gates'][:4]}",
    )
    full = set(mapping.get("gates", {})) | set(mapping.get("floor", []))
    check(
        "and it is a strict subset of the full set",
        len(result["gates"]) < len(full),
        f"selected {len(result['gates'])} of {len(full)}",
    )


def probe_the_default_deny_cannot_be_neutered() -> None:
    """THE NEUTER PROBE. Gut the branch and this goes RED.

    The synthetic mapping is deliberately tiny so the two sets are computable by hand:
    `full` is floor | every key, `union` is floor | the keys that actually matched. A
    `select` that has lost its default-deny branch returns the union -- and the assertion
    below is written as `== full` AND `!= union`, so neither a shortened full set nor a
    widened union can satisfy it.
    """
    module = _load("oc_gate_select_neuter", GATE_SELECT)
    mapping = {
        "default": "full",
        "floor": ["tests/test_floor.py"],
        "gates": {"tests/test_a.py": ["a/*"], "tests/test_b.py": ["b/*"]},
    }
    full = {"tests/test_floor.py", "tests/test_a.py", "tests/test_b.py"}
    union = {"tests/test_floor.py", "tests/test_a.py"}
    result = module.select(mapping, ["a/one.py", "z/nowhere.py"])
    check(
        "an uncovered path returns the FULL set",
        set(result["gates"]) == full,
        f"got {sorted(result['gates'])}",
    )
    check(
        "which is STRICTLY larger than the union of matches -- a gutted branch returns the union",
        set(result["gates"]) != union,
        "the default-deny branch is gone: an uncovered path bought a subset",
    )
    check(
        "and the verdict declares itself default-deny",
        result["default_deny"] is True,
        f"default_deny={result['default_deny']!r}",
    )
    check(
        "and names the path it could not cover",
        result["uncovered"] == ["z/nowhere.py"],
        f"uncovered={result['uncovered']!r}",
    )
    check("and the mode says WHY it went full", result["mode"] == "full", result["mode"])
    covered = module.select(mapping, ["a/one.py"])
    check(
        "the other direction still holds: a fully covered change stays a subset",
        covered["mode"] == "subset" and covered["default_deny"] is False,
        f"mode={covered['mode']}",
    )


def probe_an_unreadable_map_is_none_not_empty() -> None:
    """`None` is an instrument that cannot read its declaration -- not an empty map."""
    module = _load("oc_gate_select_load", GATE_SELECT)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        check(
            "a root with no map resolves to None",
            module.load_map(root) is None,
            repr(module.load_map(root))[:80],
        )
        (root / "registry").mkdir()
        (root / "registry" / "gate_triggers.json").write_text("{ not json", encoding="utf-8")
        check(
            "a corrupt map resolves to None rather than to a silent empty one",
            module.load_map(root) is None,
            repr(module.load_map(root))[:80],
        )


def probe_the_cli_reports_the_mode() -> None:
    """End to end: the CLI's own verdict, on the two directions, as JSON."""
    covered = subprocess.run(
        [sys.executable, "tools/gate_select.py", "--paths", "evidence/rework.md", "--json"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    uncovered = subprocess.run(
        [sys.executable, "tools/gate_select.py", "--paths", ".github/workflows/ci.yml", "--json"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    try:
        covered_data = json.loads(covered.stdout)
        uncovered_data = json.loads(uncovered.stdout)
    except json.JSONDecodeError as exc:
        check("the CLI emits parseable JSON on both directions", False, f"{exc}: {covered.stderr[:120]}")
        return
    check(
        "a covered path exits 0 and reports a subset",
        covered.returncode == 0 and covered_data.get("mode") == "subset",
        f"rc={covered.returncode} mode={covered_data.get('mode')}",
    )
    check(
        "an uncovered path reports full and says why",
        uncovered_data.get("mode") == "full"
        and uncovered_data.get("default_deny") is True
        and uncovered_data.get("uncovered"),
        f"mode={uncovered_data.get('mode')} uncovered={uncovered_data.get('uncovered')}",
    )
    full = set(_live_map().get("gates", {})) | set(_live_map().get("floor", []))
    check(
        "and it hands over the whole suite, not a guess",
        set(uncovered_data.get("gates", [])) == full,
        f"{len(uncovered_data.get('gates', []))} of {len(full)}",
    )


# The hermetic tree's audit, in the SHAPE `gate_select` reads since #436: a MODULE, not a
# text body. It mirrors the real audit's two obligations -- the interpreter is part of every
# registered argv, and the gate list is exposed through `registered_gates(repo_root)` -- and
# it re-exports the REAL `gate_key_for_cmd` from the copied `gate_budget.py` instead of
# re-implementing it, so the key law has one home even inside a fixture.
FIXTURE_AUDIT = (
    "from __future__ import annotations\n"
    "import sys\n"
    "from pathlib import Path\n"
    "\n"
    "sys.path.insert(0, str(Path(__file__).resolve().parent))\n"
    "from gate_budget import gate_key_for_cmd  # noqa: E402\n"
    "\n"
    "gates_to_run = []\n"
    'gates_to_run.append([sys.executable, "tests/fixture_script_gate.py"])\n'
    "gates_to_run.append(\n"
    '    [sys.executable, "-m", "pytest", "tests/test_fixture_gate.py"]\n'
    ")\n"
    "\n"
    "def registered_gates(repo_root):\n"
    "    return [cmd for cmd in gates_to_run if gate_key_for_cmd(cmd, repo_root)]\n"
)

def probe_the_run_mode_executes_gates_with_the_interpreter() -> None:
    """#416: `--run` must EXECUTE a gate, not die on a non-executable file.

    `run_gates` ran the registered argv with NO interpreter prefix. That argv is
    interpreter-RELATIVE -- the scan keeps only the TARGET-shaped tokens and drops the
    `sys.executable` the audit's call sites carry -- so a script gate (`tests/x.py`, mode
    100644) raised PermissionError and a pytest gate (`-m pytest`) raised FileNotFoundError:
    the exact remedy the pre-commit hook prints could run no gate at all.

    The probe drives `run_gates` over a HERMETIC tree whose audit registers BOTH forms, and
    each fixture gate WRITES A MARKER. The assertion is that the gate RAN (the marker
    exists), never merely that the call returned -- drop the prefix and nothing runs, so no
    marker is written.

    THE FIXTURE AUDIT IS A MODULE, because #436 changed what the selector reads. Until then
    it re-parsed the audit's SOURCE for quoted literals, so a bare two-line body with no
    `gates_to_run = []` and no import was enough to drive it -- and that same literals-only
    projection is what truncated the hygiene gate to a bare `--namespace`. The selector now
    EXECUTES the audit and reads its own `registered_gates`, so the fixture has to be a real
    module, and `gate_key_for_cmd` is imported from the REAL `gate_budget.py` rather than
    re-stubbed: a fixture re-implementing the key law would be a second source for it.
    """
    module = _load("oc_gate_select_run", GATE_SELECT)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "tools").mkdir()
        (root / "tests").mkdir()
        shutil.copyfile(GATE_BUDGET, root / "tools" / "gate_budget.py")
        (root / "tools" / "audit.py").write_text(FIXTURE_AUDIT, encoding="utf-8")
        script_marker = root / "script-gate-ran.txt"
        pytest_marker = root / "pytest-gate-ran.txt"
        (root / "tests" / "fixture_script_gate.py").write_text(
            "import pathlib\n"
            f"pathlib.Path({str(script_marker)!r}).write_text('ran', encoding='utf-8')\n"
            "raise SystemExit(0)\n",
            encoding="utf-8",
        )
        (root / "tests" / "test_fixture_gate.py").write_text(
            "import pathlib\n"
            "def test_ran() -> None:\n"
            f"    pathlib.Path({str(pytest_marker)!r}).write_text('ran', encoding='utf-8')\n",
            encoding="utf-8",
        )
        try:
            run = module.run_gates(
                root, ["tests/fixture_script_gate.py", "tests/test_fixture_gate.py"]
            )
        except OSError as exc:
            check(
                "run_gates executes a gate with the interpreter prefix",
                False,
                f"raised {type(exc).__name__}: {exc}",
            )
            return
        check(
            "both registered forms run to rc=0",
            run.failures == [] and run.no_verdicts == [],
            f"failures={run.failures} no_verdicts={run.no_verdicts}",
        )
        check(
            "the SCRIPT gate actually RAN (its marker exists)",
            script_marker.is_file(),
            "no marker: the script gate never executed -- the interpreter prefix is gone",
        )
        check(
            "the PYTEST gate actually RAN (its marker exists)",
            pytest_marker.is_file(),
            "no marker: the pytest gate never executed -- the interpreter prefix is gone",
        )


# --- #539: the TREE a range's gates read --------------------------------------------
#
# No stated skip: these probes build their OWN git repository, so they need no live map
# and no live ledger, and they run at the shipped depth as well as at the root.

FIXTURE_RANGE_AUDIT = (
    "from __future__ import annotations\n"
    "import sys\n"
    "from pathlib import Path\n"
    "\n"
    "sys.path.insert(0, str(Path(__file__).resolve().parent))\n"
    "from gate_budget import gate_key_for_cmd  # noqa: E402\n"
    "\n"
    "gates_to_run = []\n"
    'gates_to_run.append([sys.executable, "tests/fixture_pair_gate.py"])\n'
    "\n"
    "def registered_gates(repo_root):\n"
    "    return [cmd for cmd in gates_to_run if gate_key_for_cmd(cmd, repo_root)]\n"
)

# TEMPLATE-SYNC SHAPED on purpose: the gate resolves its tree from its own `__file__` and
# compares two files inside it -- exactly the shape whose verdict flipped on the shared
# checkout (#539). It writes the ROOT IT ACTUALLY READ into the file named by
# PAIR_GATE_MARKER, because a gate that merely exits 0 cannot distinguish a clean checkout
# from a lucky worktree, and "which tree produced this 0" is the whole question.
FIXTURE_PAIR_GATE = (
    "#!/usr/bin/env python3\n"
    "import os, pathlib, sys\n"
    "root = pathlib.Path(__file__).resolve().parent.parent\n"
    "a = (root / 'tools' / 'pair' / 'a.txt').read_text(encoding='utf-8')\n"
    "b = (root / 'tools' / 'pair' / 'b.txt').read_text(encoding='utf-8')\n"
    "marker = os.environ.get('PAIR_GATE_MARKER')\n"
    "if marker:\n"
    "    pathlib.Path(marker).write_text(str(root) + chr(10) + b, encoding='utf-8')\n"
    "if a != b:\n"
    "    print('FAIL -- the pair drifted: %r != %r' % (a, b))\n"
    "    sys.exit(1)\n"
    "print('PASS -- the pair is byte-identical')\n"
)

def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)

def _fixture_range_repo(tmp: Path, map_gates: dict | None = None) -> tuple[Path, str, str]:
    """A real two-commit repo whose TIP is clean and whose pair gate is on the map.

    Commit 1: a = b = "one". Commit 2 (the TIP): a = b = "two", and `ledger.txt` moves --
    so the RANGE selects the pair gate while the gate is GREEN at the tip. That is the
    #539 fixture precisely: the tip is clean and only the WORKTREE is allowed to drift, so
    a RED here can only come from the worktree.
    """
    root = tmp / "repo"
    for relative in ("tools/pair", "tests", "registry"):
        (root / relative).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(GATE_BUDGET, root / "tools" / "gate_budget.py")
    shutil.copyfile(GATE_SELECT, root / "tools" / "gate_select.py")
    (root / "tools" / "audit.py").write_text(FIXTURE_RANGE_AUDIT, encoding="utf-8")
    (root / "tests" / "fixture_pair_gate.py").write_text(FIXTURE_PAIR_GATE, encoding="utf-8")
    gates = map_gates if map_gates is not None else {
        "tests/fixture_pair_gate.py": ["tools/pair/*", "ledger.txt"]
    }
    (root / "registry" / "gate_triggers.json").write_text(
        json.dumps({"floor": [], "gates": gates}), encoding="utf-8"
    )
    (root / "ledger.txt").write_text("0\n", encoding="utf-8")
    for name in ("a", "b"):
        (root / "tools" / "pair" / f"{name}.txt").write_text("one\n", encoding="utf-8")

    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    }
    if _git(root, "init", "-q", "-b", "main").returncode != 0:
        _git(root, "init", "-q")
    _git(root, "add", "-A")
    subprocess.run(
        ["git", "-C", str(root), "commit", "-q", "-m", "fixture: base"],
        capture_output=True, text=True, env=env,
    )
    first = _git(root, "rev-parse", "HEAD").stdout.strip()

    for name in ("a", "b"):
        (root / "tools" / "pair" / f"{name}.txt").write_text("two\n", encoding="utf-8")
    (root / "ledger.txt").write_text("1\n", encoding="utf-8")
    _git(root, "add", "-A")
    subprocess.run(
        ["git", "-C", str(root), "commit", "-q", "-m", "fixture: tip"],
        capture_output=True, text=True, env=env,
    )
    tip = _git(root, "rev-parse", "HEAD").stdout.strip()
    return root, first, tip

def _marker_parts(marker: Path) -> tuple[str, str]:
    """The gate's own record: the tree it READ, and the b.txt bytes it found there.

    The checkout is removed before the assertions run, so the bytes have to be recorded by
    the gate rather than re-read from a directory that no longer exists.
    """
    if not marker.is_file():
        return "", ""
    lines = marker.read_text(encoding="utf-8").split("\n")
    return (lines[0].strip(), lines[1].strip() if len(lines) > 1 else "")

def _run_selector(root: Path, args: list[str], marker: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "tools/gate_select.py", *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        env={**os.environ, "PAIR_GATE_MARKER": str(marker)},
    )

def probe_the_range_judges_the_range_not_the_worktree() -> None:
    """#539: `--range` judges the RANGE, on the three arms the ruling names.

    THE DEFECT. `--range` selected its gates from the range and then ran them with
    `cwd=root` -- the WORKING TREE. On this factory's shared checkout a peer lane's
    in-flight edit made the same command over the same ledger-only range return rc=0 at
    19:19Z and rc=1 at 19:31Z, RED on `tests/test_template_sync.py` for a path the commit
    never touched, while the template pair was byte-identical AT the commit.

    THE ARMS. Arm 1 dirties a path no gate reads and asserts the run still happens and
    reflects the range. **Arm 2 is the DISCRIMINATOR** -- it dirties a SELECTED path the
    gate READS, which is the arm that fails today -- and it asserts not just rc=0 but that
    the gate ran in a DIFFERENT tree from the worktree, because a gate that exits 0 proves
    nothing about which tree produced the 0. Arm 3 asserts `--staged` is UNCHANGED: the same
    dirty file, staged, must still be judged in the worktree and must still FAIL.

    Arm 3 is why arm 2 cannot be satisfied by making both modes read the tip: that would
    make `--staged` green on a change that breaks the tree, which is the defect the
    pre-commit leg exists to catch.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root, first, tip = _fixture_range_repo(Path(tmp))
        marker = Path(tmp) / "pair-gate-root.txt"
        rev_range = f"{first}..{tip}"
        short = tip[:8]

        # --- arm 1: a NON-selected path is dirty; the gates still run, on the range.
        (root / "scratch.txt").write_text("unrelated drift\n", encoding="utf-8")
        arm1 = _run_selector(root, ["--range", rev_range, "--run"], marker)
        check(
            "arm 1 -- an unrelated dirty file does not derail the run",
            arm1.returncode == 0,
            f"rc={arm1.returncode} stderr={arm1.stderr[:200]}",
        )
        check(
            "arm 1 -- the verdict names the clean checkout it judged",
            f"tree=clean checkout {short}" in arm1.stdout,
            f"stdout={arm1.stdout.splitlines()[:1]}",
        )

        # --- arm 2: THE DISCRIMINATOR. A SELECTED path the gate READS is dirty.
        (root / "tools" / "pair" / "b.txt").write_text("three\n", encoding="utf-8")
        marker.unlink(missing_ok=True)
        arm2 = _run_selector(root, ["--range", rev_range, "--run"], marker)
        check(
            "arm 2 (discriminator) -- a dirty SELECTED path does not turn the range RED",
            arm2.returncode == 0,
            f"rc={arm2.returncode} stderr={arm2.stderr[:200]}",
        )
        check(
            "arm 2 -- the verdict names the clean checkout it judged",
            f"tree=clean checkout {short}" in arm2.stdout,
            f"stdout={arm2.stdout.splitlines()[:1]}",
        )
        ran_in, ran_b = _marker_parts(marker)
        check(
            "arm 2 -- the gate RAN (it wrote its marker)",
            bool(ran_in),
            "no marker: the gate never executed, so nothing was judged",
        )
        check(
            "arm 2 -- and it ran in a DIFFERENT tree than the worktree",
            bool(ran_in) and Path(ran_in).resolve() != root.resolve(),
            f"the gate read {ran_in!r}; the worktree is {str(root)!r}",
        )
        check(
            "arm 2 -- the tree it read carries the TIP's bytes, not the drift",
            ran_b == "two",
            f"b.txt in the judged tree read {ran_b!r}, not 'two'",
        )
        check(
            "arm 2 -- the clean checkout was REMOVED afterwards",
            len([line for line in _git(root, "worktree", "list").stdout.splitlines() if line.strip()]) == 1,
            f"worktree list={_git(root, 'worktree', 'list').stdout!r}",
        )

        # --- arm 3: `--staged` is UNCHANGED -- the same drift, staged, must still FAIL.
        _git(root, "add", "tools/pair/b.txt")
        marker.unlink(missing_ok=True)
        arm3 = _run_selector(root, ["--staged", "--run"], marker)
        check(
            "arm 3 -- `--staged` still FAILS on a change that breaks the tree",
            arm3.returncode == 1,
            f"rc={arm3.returncode} (a green here means --staged was made to lie)",
        )
        check(
            "arm 3 -- and its verdict names the WORKTREE, not a checkout",
            "tree=worktree" in arm3.stdout,
            f"stdout={arm3.stdout.splitlines()[:1]}",
        )
        staged_root, _ = _marker_parts(marker)
        check(
            "arm 3 -- the gate read the worktree, where the drift is",
            bool(staged_root) and Path(staged_root).resolve() == root.resolve(),
            f"the gate read {staged_root!r}; the worktree is {str(root)!r}",
        )

def probe_the_range_fails_a_gate_the_clean_checkout_cannot_materialise() -> None:
    """#539 clause 4: a selected gate the checkout cannot carry is a FAILURE, not a skip.

    The map is read from the WORKTREE (selection is unchanged, clause 5), so a key can name
    a gate that the RANGE TIP does not contain. `gate_key_for_cmd` resolves a key by
    requiring the file to exist, so such a gate is simply absent from `registered_commands`
    and would surface as "no registered argv in tools/audit.py" -- a message that sends the
    reader to the AUDIT when the missing thing is the TREE. The probe asserts the failure
    names the tree.

    The fixture's ghost gate is UNTRACKED in the worktree and absent from the tip, so it is
    exactly a key that cannot be materialised. Its control is the arms probe above: the same
    repository without the ghost key exits 0, so a red here is the ghost and not the fixture.
    """
    ghost_key = "tests/fixture_ghost_gate.py"
    with tempfile.TemporaryDirectory() as tmp:
        root, first, tip = _fixture_range_repo(
            Path(tmp),
            map_gates={
                "tests/fixture_pair_gate.py": ["tools/pair/*"],
                ghost_key: ["ledger.txt"],
            },
        )
        (root / ghost_key).write_text("raise SystemExit(0)\n", encoding="utf-8")
        marker = Path(tmp) / "pair-gate-root.txt"
        proc = _run_selector(root, ["--range", f"{first}..{tip}", "--run"], marker)
        check(
            "clause 4 -- a gate the clean checkout cannot materialise is rc=1",
            proc.returncode == 1,
            f"rc={proc.returncode}: a skip here would hide a gate that never ran",
        )
        check(
            "clause 4 -- the failure NAMES the tree, not just the audit",
            ghost_key in proc.stderr and "clean checkout" in proc.stderr,
            f"stderr={proc.stderr[:300]}",
        )

FIXTURE_AUDIT_544 = (
    "from __future__ import annotations\n"
    "import sys\n"
    "from pathlib import Path\n"
    "\n"
    "sys.path.insert(0, str(Path(__file__).resolve().parent))\n"
    "from gate_budget import gate_key_for_cmd  # noqa: E402\n"
    "\n"
    "gates_to_run = []\n"
    'gates_to_run.append([sys.executable, "tests/pass_gate.py"])\n'
    'gates_to_run.append([sys.executable, "tests/fail_gate.py"])\n'
    'gates_to_run.append([sys.executable, "tests/kill_gate.py"])\n'
    'gates_to_run.append([sys.executable, "tests/kill99_gate.py"])\n'
    'gates_to_run.append([sys.executable, "tests/kill124_gate.py"])\n'
    "\n"
    "def registered_gates(repo_root):\n"
    "    return [cmd for cmd in gates_to_run if gate_key_for_cmd(cmd, repo_root)]\n"
)

def _declared_kill_code() -> int:
    """The fleet kill code, READ from the declaration rather than imported.

    `gate_budget` defines a frozen dataclass, and `_load` does not register the module in
    `sys.modules` — dataclasses resolves `cls.__module__` through that registry and raises
    AttributeError. Parsing the single assignment keeps the arm honest (it reads the same
    declaration the tool reads) without dragging the module's import machinery in.
    """
    found = re.findall(r"^TIMEOUT_EXIT_CODE\s*=\s*(\d+)\s*$", GATE_BUDGET.read_text(), re.M)
    assert len(found) == 1, f"gate_budget.py must declare TIMEOUT_EXIT_CODE once, saw {found}"
    return int(found[0])

def _fixture_544(root: Path) -> None:
    """A hermetic tree whose gates return the exact codes #544 must tell apart."""
    (root / "tools").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "registry").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(GATE_BUDGET, root / "tools" / "gate_budget.py")
    (root / "tools" / "audit.py").write_text(FIXTURE_AUDIT_544, encoding="utf-8")
    kill = _declared_kill_code()
    for name, code in (
        ("pass_gate", 0),
        ("fail_gate", 1),
        ("kill_gate", kill),
        ("kill99_gate", 99),
        ("kill124_gate", 124),
    ):
        (root / "tests" / f"{name}.py").write_text(
            f"raise SystemExit({code})\n", encoding="utf-8"
        )
    (root / "registry" / "gate_triggers.json").write_text(
        json.dumps(
            {
                "default": "full",
                "floor": [],
                "gates": {
                    "tests/pass_gate.py": ["t-pass"],
                    "tests/fail_gate.py": ["t-fail"],
                    "tests/kill_gate.py": ["t-kill"],
                    "tests/kill99_gate.py": ["t-kill99"],
                    "tests/kill124_gate.py": ["t-kill124"],
                },
            }
        ),
        encoding="utf-8",
    )

def _run_cli_544(root: Path, trigger: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATE_SELECT), "--repo-root", str(root), "--paths", trigger, "--run"],
        capture_output=True,
        text=True,
    )

def probe_a_kill_is_not_a_failure() -> None:
    """#544: a gate killed at its budget is NO VERDICT, never FAILED, and never rc=0.

    Measured on the live box, same run, same bytes: the gate printed `NO VERDICT ... not
    counted as a FAIL: exit 124, the fleet's kill code (#206)` while this runner reported
    `FAILED ... rc=124` one layer up. An author reading the runner concludes their change
    broke something when no verdict was ever taken on it.

    Four arms, and arm 2 is the discriminator: a change that merely adds a string and
    softens every non-zero exit would pass arms 1 and 3 while destroying the failure class.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _fixture_544(root)

        # ARM 1 — the kill reads NO VERDICT and is absent from the failures.
        killed = _run_cli_544(root, "t-kill")
        check(
            "ARM 1: a gate exiting the kill code prints NO VERDICT",
            "NO VERDICT" in killed.stderr,
            f"stderr={killed.stderr[-300:]}",
        )
        check(
            "ARM 1: ... and is NOT reported as FAILED",
            "FAILED" not in killed.stderr,
            f"stderr={killed.stderr[-300:]}",
        )
        check(
            "ARM 1: ... and the run is NOT a pass (rc must not be 0)",
            killed.returncode != 0,
            f"rc={killed.returncode}",
        )
        check(
            "ARM 1: ... and rc is the fleet's kill code, not 1",
            killed.returncode == _declared_kill_code(),
            f"rc={killed.returncode}",
        )

        # ARM 2 — THE DISCRIMINATOR: a genuine failure in the same runner still FAILS.
        failed = _run_cli_544(root, "t-fail")
        check(
            "ARM 2: a gate exiting 1 still prints FAILED",
            "FAILED" in failed.stderr,
            f"stderr={failed.stderr[-300:]}",
        )
        check(
            "ARM 2: ... and still yields a non-zero exit",
            failed.returncode != 0,
            f"rc={failed.returncode}",
        )
        check(
            "ARM 2: ... and is NOT dressed up as NO VERDICT",
            "NO VERDICT" not in failed.stderr,
            f"stderr={failed.stderr[-300:]}",
        )

        # ARM 3 — precedence: a mixed run is non-zero, and the failure owns the code.
        (root / "registry" / "gate_triggers.json").write_text(
            json.dumps(
                {
                    "default": "full",
                    "floor": [],
                    "gates": {
                        "tests/kill_gate.py": ["t-mixed"],
                        "tests/fail_gate.py": ["t-mixed"],
                    },
                }
            ),
            encoding="utf-8",
        )
        mixed = _run_cli_544(root, "t-mixed")
        check(
            "ARM 3: a mixed kill+failure run reports BOTH classes",
            "NO VERDICT" in mixed.stderr and "FAILED" in mixed.stderr,
            f"stderr={mixed.stderr[-300:]}",
        )
        check(
            "ARM 3: ... and the failure owns the exit code (1, not the kill code)",
            mixed.returncode == 1,
            f"rc={mixed.returncode}",
        )
        # The mixed arm rewrote the map; restore it so the clean arm has a subject. A
        # trigger that resolves to nothing is not a clean run — it is a run of every gate.
        _fixture_544(root)
        passed = _run_cli_544(root, "t-pass")
        check(
            "ARM 3: a clean run still exits 0 — the control that the change did not red everything",
            passed.returncode == 0,
            f"rc={passed.returncode} stderr={passed.stderr[-200:]}",
        )

        # ARM 4 — DECLARATION, NOT LITERAL: move the declaration and the class follows it.
        module = _load("oc_gate_select_544", GATE_SELECT)
        module.TIMEOUT_EXIT_CODE = 99
        run = module.run_gates(root, ["tests/kill99_gate.py", "tests/kill124_gate.py"])
        check(
            "ARM 4: the class follows the DECLARED kill code, so 99 reads NO VERDICT",
            len(run.no_verdicts) == 1 and "kill99_gate" in run.no_verdicts[0],
            f"no_verdicts={run.no_verdicts} failures={run.failures}",
        )
        check(
            "ARM 4: ... and a hardcoded 124 would report this gate as a FAILURE",
            len(run.failures) == 1 and "kill124_gate" in run.failures[0],
            f"no_verdicts={run.no_verdicts} failures={run.failures}",
        )
        module.TIMEOUT_EXIT_CODE = _declared_kill_code()

def probe_a_failed_receipt_carries_the_childs_word() -> None:
    """#552 (ruling `n=4167`), leg 1: the runner carries the child's own diagnosis.

    `tools/gate_select.py` recorded `rc=<n>` and nothing else, so the gate's own stderr --
    where it already writes `UNMEASURED` or `DISAGREE` -- died at the one surface a lane
    reads, and "a peer was running the audit" printed exactly like "your change broke this
    gate". Measured on the live box: the same commit read rc=0 solo and rc=1 under a
    concurrent peer audit (26m33s of overlap) and the receipt named neither.

    Arm 2 is the discriminator. A change that pastes the child's FIRST stderr line lands
    this tree's own `2 problem(s):` header -- a line that names no cause while looking like
    one -- so the skip is asserted rather than assumed; without that arm the receipt would
    look fixed while telling the reader nothing.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _fixture_544(root)
        (root / "tests" / "diag_gate.py").write_text(
            "import sys\n"
            "print('2 problem(s):', file=sys.stderr)\n"
            "print('  tests/example.py: the pair is UNMEASURED rather than agreeing',\n"
            "      file=sys.stderr)\n"
            "raise SystemExit(1)\n",
            encoding="utf-8",
        )
        (root / "tests" / "silent_gate.py").write_text(
            "raise SystemExit(1)\n", encoding="utf-8"
        )
        (root / "registry" / "gate_triggers.json").write_text(
            json.dumps(
                {
                    "default": "full",
                    "floor": [],
                    "gates": {
                        "tests/diag_gate.py": ["t-diag"],
                        "tests/silent_gate.py": ["t-silent"],
                    },
                }
            ),
            encoding="utf-8",
        )
        # The fixture audit's `gates_to_run` is the argv source the runner reads (#436), so a
        # gate it does not register is reported "no registered argv" and never RUN -- which is
        # how the first draft of this probe passed its negative arms while testing nothing.
        with (root / "tools" / "audit.py").open("a", encoding="utf-8") as handle:
            handle.write(
                'gates_to_run.append([sys.executable, "tests/diag_gate.py"])\n'
                'gates_to_run.append([sys.executable, "tests/silent_gate.py"])\n'
            )
        module = _load("oc_gate_select_552", GATE_SELECT)

        diag = module.run_gates(root, ["tests/diag_gate.py"])
        check(
            "ARM 1: a FAILED receipt carries the child's own diagnosis",
            len(diag.failures) == 1
            and "UNMEASURED rather than agreeing" in diag.failures[0],
            f"failures={diag.failures}",
        )
        check(
            "ARM 2 (discriminator): the bare count header is SKIPPED, never carried",
            "problem(s)" not in " ".join(diag.failures),
            f"failures={diag.failures}",
        )
        check(
            "ARM 1: ... and the receipt still names the rc it reports",
            "rc=1" in diag.failures[0],
            f"failures={diag.failures}",
        )
        check(
            "ARM 3: a plain failure is still FAILED, never reclassified as NO VERDICT",
            diag.no_verdicts == [],
            f"no_verdicts={diag.no_verdicts}",
        )

        silent = module.run_gates(root, ["tests/silent_gate.py"])
        check(
            "ARM 3: a child that wrote nothing yields the bare receipt, no dangling separator",
            silent.failures == ["tests/silent_gate.py — rc=1"],
            f"failures={silent.failures}",
        )

# --- #568: the DECLARED-vs-OPENED census ---------------------------------------------
#
# The trigger map is hand-maintained, so it goes stale the first time a gate grows a read,
# and the fallback does NOT save it: default-deny fires only for a path matching NO glob,
# so a PARTLY mapped path silently drops every reader the map omits. Measured both arms
# (ruling n=4321): an unmapped path forces 107 gates, while `evidence/rework.md` -- partly
# mapped -- derives 16 and `evidence/ledger.jsonl` derives 31, each without the gate that
# reads it. Nothing in this file compared the two sides before now; `#567` was that gap
# found by hand, after a commit had already gone out over a file the missing gate reds on.
#
# ONE DIRECTION ONLY. An undeclared reader is a finding; a declared glob matching nothing
# is NEVER one. The map's own note states why: over-inclusion costs only time, while a
# gate missing from a path it reads is the silent miss the map exists to remove. A probe
# that can fail in two directions gets exempted into silence.
#
# READ STATICALLY, NOT BY TRACE. A trace covers the paths a test exercised -- a sample of
# the map's coverage, never the map. The declaration is a property of the SOURCE, so this
# parses the AST and executes nothing, and it runs on any tree with no working runtime.

REPO_ROOT_SYMBOLS = frozenset({"REPO", "REPO_ROOT", "ROOT", "TREE", "BASE"})
"""The names this factory uses for a repo root. A read is repo-relative only if it starts
from one of these -- `REPO / "evidence" / "x"` is a claim about THIS tree, which is what
the map declares coverage of; `tmp / "x"` or `argv[1]` is not."""


def _div_parts(node):
    """Flatten `a / b / c` into [a, b, c], or None when the node is not a `/` chain."""
    import ast as _ast

    if not (isinstance(node, _ast.BinOp) and isinstance(node.op, _ast.Div)):
        return None
    parts = []
    while isinstance(node, _ast.BinOp) and isinstance(node.op, _ast.Div):
        parts.append(node.right)
        node = node.left
    parts.append(node)
    return list(reversed(parts))


def _repo_root_symbol(node):
    """The repo-root symbol a `/` chain starts from, or None. `REPO.parent / "x"` counts."""
    import ast as _ast

    if isinstance(node, _ast.Name) and node.id in REPO_ROOT_SYMBOLS:
        return node.id
    if isinstance(node, _ast.Attribute) and node.attr == "parent":
        inner = node.value
        while isinstance(inner, _ast.Attribute) and inner.attr == "parent":
            inner = inner.value
        if isinstance(inner, _ast.Name) and inner.id in REPO_ROOT_SYMBOLS:
            return inner.id
    return None


def opened_paths(source: str, *, filename: str = "<gate>") -> list:
    """Every MODULE-LEVEL repo-rooted path constant, as (line, symbol, repo-relative path).

    THE BOUND, printed by the probe rather than assumed: this reads a gate's DECLARED READ
    SURFACE -- a constant the module builds from the repo root -- and nothing else. A path
    assembled at runtime (`REPO / name`, an f-string, an argument, a literal handed straight
    to `open()`) is invisible here, and so is a read whose path never becomes a module-level
    constant (a function-local `ledger_file = REPO_ROOT / "evidence/ledger.jsonl"` is the
    commonest shape in `tools/`). That is why the probe prints how many gates it could speak
    about: a gate with no extracted constant is a gate this instrument has no opinion on,
    and silence there must read as a blind spot rather than as coverage.
    """
    import ast as _ast

    tree = _ast.parse(source, filename=filename)
    found = []
    for node in tree.body:
        if not isinstance(node, _ast.Assign):
            continue
        parts = _div_parts(node.value)
        if parts is None or _repo_root_symbol(parts[0]) is None:
            continue
        segments = []
        for part in parts[1:]:
            if not (isinstance(part, _ast.Constant) and isinstance(part.value, str)):
                segments = []
                break
            segments.append(part.value)
        if not segments:
            continue
        for target in node.targets:
            if isinstance(target, _ast.Name):
                found.append((node.lineno, target.id, "/".join(segments)))
    return found


def _is_subtree(root, relative: str) -> bool:
    """Whether a repo-rooted constant names a DIRECTORY rather than a file.

    Read from the TREE, not the source: `REPO / "tools"` and `REPO / "tools/audit.py"` are
    the same AST shape and only the tree says which is a subtree. A constant naming a
    directory is a read of everything under it, so its declaration is `tools/*` -- a bare
    `tools` in the map would cover the directory entry and nothing inside it.
    """
    return (root / relative).is_dir()


def _read_is_covered(globs, relative: str, *, subtree: bool) -> bool:
    """Whether a declared glob covers this read.

    A SUBTREE read is covered only by a glob matching a CHILD under it. A bare directory
    name in the map (`TEMPLATE`) is deliberately NOT accepted: it matches no changed file
    under that directory -- `fnmatch("TEMPLATE/x", "TEMPLATE")` is False -- so it declares
    coverage while delivering none, which is precisely the silent class this census exists
    to find. Accepting it would let the census pass over a gate that no real change selects.
    """
    import fnmatch as _fnmatch

    if subtree:
        return any(_fnmatch.fnmatchcase(relative + "/x", str(glob)) for glob in globs)
    return any(_fnmatch.fnmatchcase(relative, str(glob)) for glob in globs)


def opened_vs_declared(root, mapping: dict) -> dict:
    """The one-directional census: findings, extraction counts, and the blind spot.

    Returns `{findings, constants, gates_judged, blind}`. `findings` is one dict per read
    with no covering glob, carrying the `declares` glob the map needs -- the remedy is
    copy-pasteable rather than a description of a remedy. `blind` names the gates with no
    extracted constant at all, so an empty finding list can never be mistaken for a clean
    sweep over every gate.
    """
    gates = mapping.get("gates", {}) if isinstance(mapping, dict) else {}
    findings = []
    constants = 0
    blind = []
    for gate, globs in sorted(gates.items()):
        path = root / gate
        if not path.is_file():
            continue
        try:
            reads = opened_paths(path.read_text(encoding="utf-8"), filename=gate)
        except (OSError, SyntaxError, ValueError):
            blind.append(gate)
            continue
        constants += len(reads)
        if not reads:
            blind.append(gate)
        for line, symbol, relative in reads:
            subtree = _is_subtree(root, relative)
            if _read_is_covered(globs, relative, subtree=subtree):
                continue
            findings.append({
                "gate": gate,
                "line": line,
                "symbol": symbol,
                "path": relative,
                "declares": relative + "/*" if subtree else relative,
            })
    return {
        "findings": findings,
        "constants": constants,
        "gates_judged": len([g for g in gates if (root / g).is_file()]) - len(blind),
        "blind": blind,
    }


def probe_every_read_a_gate_opens_is_declared() -> None:
    """The census: a gate that opens a repo path must be selected when that path changes.

    Five arms. Arm 1 is the POSITIVE CONTROL on the extraction, and it is the arm that makes
    every other verdict mean something: if the parser silently stopped seeing reads, arms 2
    and 4 would both pass on an empty population and this gate would be an instrument that
    reports coverage it cannot measure. Arms 4 and 5 drive a SYNTHETIC map in both
    directions, so the census is proven to bite and proven not to bite where it must not.
    """
    module = _load("oc_gate_select_census", GATE_SELECT)
    mapping = _live_map()
    root = REPO

    # ARM 1 -- the extraction, pinned to referents that do not depend on the map.
    # `tests/test_audit_rates.py:129` builds `LEDGER` from the repo root and `:130` builds
    # `REWORK`; both are the reads `#567` had to declare by hand. NOTE the coordinates: the
    # #568 dispatch names `tools/audit.py:129`/`:130` as these read sites, and that is wrong
    # -- `tools/audit.py:129` sits inside a `from gate_budget import (...)` block and holds
    # no path at all, while its own reads are at `:3432`/`:3433` and are FUNCTION-LOCAL, so
    # a module-level census does not see them and should not. The referents below are the
    # ones read at the bytes; the dispatch's line numbers were a transcription of the
    # GATE's constants against the TOOL's filename.
    control = opened_paths((REPO / "tests" / "test_audit_rates.py").read_text(encoding="utf-8"),
                           filename="tests/test_audit_rates.py")
    check(
        "CONTROL: the extraction finds tests/test_audit_rates.py:129 -> evidence/ledger.jsonl",
        (129, "LEDGER", "evidence/ledger.jsonl") in control,
        f"extracted={[c for c in control if c[1] in {'LEDGER', 'REWORK'}]}",
    )
    check(
        "CONTROL: and :130 -> evidence/rework.md -- the two reads #567 declared by hand",
        (130, "REWORK", "evidence/rework.md") in control,
        f"extracted={[c for c in control if c[1] in {'LEDGER', 'REWORK'}]}",
    )
    hermetic = opened_paths(
        "from pathlib import Path\n"
        "REPO = Path('.')\n"
        "TOP = REPO / 'docs' / 'a.md'\n"
        "def f():\n"
        "    local = REPO / 'evidence' / 'b.jsonl'\n"
        "    return REPO / 'c.md'\n",
        filename="<hermetic>",
    )
    check(
        "CONTROL: and it reads MODULE-LEVEL constants only, so a function-local read is "
        "outside it -- the stated bound, pinned rather than trusted",
        hermetic == [(3, "TOP", "docs/a.md")],
        f"extracted={hermetic}",
    )

    # ARM 2 -- the live map. Zero findings, and the population it was measured over.
    live = opened_vs_declared(root, mapping)
    check(
        "no gate opens a repo path the map does not declare for it",
        not live["findings"],
        f"{len(live['findings'])} undeclared read(s): "
        + "; ".join(f"{f['gate']}:{f['line']} {f['path']} -> needs {f['declares']}"
                    for f in live["findings"][:4]),
    )
    # THE BLIND SPOT IS PRINTED, never folded into the verdict. A gate with no module-level
    # constant is not a gate this census cleared; it is one it could not look at.
    print(
        f"STATED BOUND -- {live['gates_judged']} of {len(mapping.get('gates', {}))} mapped "
        f"gate(s) carried {live['constants']} module-level repo-rooted constant(s) and were "
        f"judged; {len(live['blind'])} had none and are OUTSIDE this census "
        f"(function-local or runtime-assembled reads are invisible to a static parse)"
    )

    # ARM 3 -- over-declaration is NEVER a finding.
    generous = json.loads(json.dumps(mapping))
    first = sorted(generous.get("gates", {}))[0]
    generous["gates"][first] = list(generous["gates"][first]) + ["no/such/path/at/all.xyz"]
    over = opened_vs_declared(root, generous)
    check(
        "ARM 3: a declared glob that matches nothing extracted is NOT a finding",
        not over["findings"],
        f"{len(over['findings'])} finding(s) appeared from over-declaration alone",
    )

    # ARM 4 -- it BITES. Undo #567's two declarations on a COPY of the live map: the census
    # must name exactly those two reads, at the lines the control just pinned.
    starved = json.loads(json.dumps(mapping))
    gate_key = "tests/test_audit_rates.py"
    starved["gates"][gate_key] = [
        glob for glob in starved["gates"][gate_key]
        if glob not in ("evidence/ledger.jsonl", "evidence/rework.md")
    ]
    bitten = [f for f in opened_vs_declared(root, starved)["findings"] if f["gate"] == gate_key]
    check(
        "ARM 4: undoing #567's two declarations is reported as EXACTLY those two reads",
        [(f["line"], f["path"]) for f in bitten]
        == [(129, "evidence/ledger.jsonl"), (130, "evidence/rework.md")],
        f"findings={[(f['line'], f['path']) for f in bitten]}",
    )

    # ARM 5 -- a subtree read is declared by its CHILDREN, not by the bare directory name.
    # `TEMPLATE` is a real directory in this tree, so the rule is driven against one rather
    # than against a fixture that could drift from what `_is_subtree` actually consults.
    check(
        "ARM 5: a bare directory glob does NOT cover a subtree read -- it needs TEMPLATE/*",
        _is_subtree(root, "TEMPLATE")
        and not _read_is_covered(["TEMPLATE"], "TEMPLATE", subtree=True)
        and _read_is_covered(["TEMPLATE/*"], "TEMPLATE", subtree=True),
        "a bare directory declaration was accepted as covering the files under it",
    )
    # ... and the REMEDY it prints is the glob the map needs, not a description of one.
    remedy = opened_vs_declared(root, {"gates": {"tests/test_binding_mechanism_exists.py": []}})
    dir_findings = [f for f in remedy["findings"] if f["path"] == "tools"]
    check(
        "ARM 5: a directory constant is reported with the subtree glob to declare",
        not dir_findings or [f["declares"] for f in dir_findings] == ["tools/*"],
        f"declares={[f['declares'] for f in dir_findings]}",
    )

# --- #583: ONE declared wall on every sanctioned path --------------------------------
#
# The audit applies a per-gate wall; this selector applied NONE, so the SAME gate ran
# unbounded here and the two receipts disagreed about whether it had finished -- the patrol
# read `34 ran, 0 failed` for a gate the audit recorded as `exit 124`/UNKNOWN. Three arms:
# the table is read from the JUDGED tree (where this broke), the wall is ENFORCED (a gate
# past it is a NO VERDICT, never a FAIL), and a table that cannot be read is a DECLARED
# EXEMPTION naming what is missing rather than an AttributeError naming a NoneType.

class _StubBudgets:
    """One wall, so the enforcement arm never depends on a live measurement."""

    default_sec = 0.25
    gates: dict = {}

    def resolve(self, key: str) -> tuple[float, str]:
        return self.default_sec, "declared"


def probe_the_wall_is_read_from_the_judged_tree() -> None:
    """ARM 1 — the base path, which is exactly where this mechanism broke.

    `gate_budget.py` derives `GATES_MANIFEST_PATH` from its own `__file__`, so loading the
    module from the repo ROOT instead of `<root>/tools` reads NO manifest, and every gate
    silently becomes an exemption -- 33 of them in one patrol receipt, which is a receipt
    about the loader and not about the gates. The discriminating assertions are the COUNT
    and the SOURCE: a table that really loaded carries the declared entries and names this
    tree's own registry. Asserting only `not None` would pass on an empty fallback.
    """
    sel = _selector()
    budgets, note = sel.declared_budget_table(REPO)
    check("the budget table loads with no exemption note", note == "", note)
    check("the budget table is not None", budgets is not None)
    if budgets is None:
        return
    check(
        "the table carries the declared entries, not an empty fallback",
        len(budgets.gates) > 50,
        f"{len(budgets.gates)} declared entries",
    )
    check(
        "the manifest read is THIS tree's, resolved through <root>/tools",
        str(REPO / "registry" / "gates.json") in budgets.default_source,
        budgets.default_source,
    )
    # THE ABSENT-MODULE ARM MUST NAME THE PATH. An AttributeError here is the printed
    # mystery this factory keeps paying for: it blames NoneType instead of the directory.
    missing, reason = sel.declared_budget_table(Path(tempfile.gettempdir()) / "no-such-tree")
    check("an unreadable table is None", missing is None)
    check(
        "the reason names the missing module AND its directory",
        "gate_budget.py" in reason and "no-such-tree" in reason,
        reason,
    )
    check(
        "the reason is not an AttributeError about a NoneType",
        "NoneType" not in reason and "AttributeError" not in reason,
        reason,
    )


def probe_a_gate_past_its_wall_is_no_verdict_and_an_absent_wall_is_declared() -> None:
    """ARM 2 and 3 — the wall is ENFORCED, and its absence is PRINTED.

    `run_gates` called `subprocess.run` with no `timeout`, so a gate that never returned
    read as a pass one layer up. Arm 2's discriminator is the BUCKET: the killed gate must
    land in `no_verdicts` and NOT in `failures` (#544), because a wall WE imposed is the
    same absence of a verdict as a child self-limiting at the kill code. Arm 3's
    discriminator is that the exemption NAMES the gate and the reason -- an unprinted
    absence is indistinguishable from a gate whose bound was met.
    """
    sel = _selector()
    slow = [sys.executable, "-c", "import time; time.sleep(30)"]
    quick = [sys.executable, "-c", "raise SystemExit(0)"]
    saved_commands, saved_table = sel.registered_commands, sel.declared_budget_table
    try:
        sel.registered_commands = lambda root: {
            "tests/slow.py": slow,
            "tests/quick.py": quick,
        }
        sel.declared_budget_table = lambda root: (_StubBudgets(), "")
        run = sel.run_gates(REPO, ["tests/slow.py", "tests/quick.py"])
        check("the fast gate under a wall is not a failure", not run.failures, str(run.failures))
        check(
            "the gate past its wall is a NO VERDICT, never a FAIL",
            len(run.no_verdicts) == 1 and "tests/slow.py" in run.no_verdicts[0],
            str(run.no_verdicts),
        )
        check(
            "the kill names the budget it died at",
            any("0.25" in killed for killed in run.no_verdicts),
            str(run.no_verdicts),
        )
        check("a run under a wall declares no exemption", not run.exemptions, str(run.exemptions))
        check(
            "the exit code separates a kill from a clean run",
            sel.run_exit_code(run) != 0,
            f"rc={sel.run_exit_code(run)}",
        )
        # ARM 3 — no readable table: the gate still RUNS, and the receipt says so.
        sel.declared_budget_table = lambda root: (
            None,
            "gate_budget.py not found under /nope/tools",
        )
        unbounded = sel.run_gates(REPO, ["tests/quick.py"])
        check(
            "an unreadable table exempts the gate BY NAME with its reason",
            len(unbounded.exemptions) == 1
            and "tests/quick.py" in unbounded.exemptions[0]
            and "/nope/tools" in unbounded.exemptions[0],
            str(unbounded.exemptions),
        )
        check(
            "an exempted gate still runs rather than being skipped",
            not unbounded.failures and not unbounded.no_verdicts,
            f"failures={unbounded.failures} no_verdicts={unbounded.no_verdicts}",
        )
    finally:
        sel.registered_commands, sel.declared_budget_table = saved_commands, saved_table


PROBES = (
    probe_every_registered_gate_is_covered,
    probe_every_map_key_is_registered,
    probe_the_map_is_well_formed,
    probe_every_read_a_gate_opens_is_declared,
    probe_the_example_carries_the_same_shape,
    probe_globs_over_include_deliberately,
    probe_a_covered_change_selects_a_subset,
    probe_the_default_deny_cannot_be_neutered,
    probe_an_unreadable_map_is_none_not_empty,
    probe_the_cli_reports_the_mode,
    probe_the_run_mode_executes_gates_with_the_interpreter,
    probe_the_range_judges_the_range_not_the_worktree,
    probe_the_range_fails_a_gate_the_clean_checkout_cannot_materialise,
    probe_a_kill_is_not_a_failure,
    probe_a_failed_receipt_carries_the_childs_word,
    probe_the_wall_is_read_from_the_judged_tree,
    probe_a_gate_past_its_wall_is_no_verdict_and_an_absent_wall_is_declared,
)


# --- #553: a run STATES its own outcome, so a pass and a crash differ -----------------
#
# No stated skip: every arm builds its OWN fixture tree and runs the real CLI as a
# SUBPROCESS with stdout and stderr on the SAME file. That is not incidental. In-process
# capture writes to a StringIO, which does not block-buffer, so the buffering defect this
# unit removes is invisible to it: the ordering arm below can only red if the child's stdout
# is a real file descriptor. A probe that captured in-process would pass on the broken code.

FIXTURE_553_AUDIT = (
    "from __future__ import annotations\n"
    "import sys\n"
    "from pathlib import Path\n"
    "\n"
    "sys.path.insert(0, str(Path(__file__).resolve().parent))\n"
    "from gate_budget import gate_key_for_cmd  # noqa: E402\n"
    "\n"
    "gates_to_run = []\n"
    'gates_to_run.append([sys.executable, "tests/fixture_clean_gate.py"])\n'
    'gates_to_run.append([sys.executable, "tests/fixture_fail_gate.py"])\n'
    'gates_to_run.append([sys.executable, "tests/fixture_kill_gate.py"])\n'
    "\n"
    "def registered_gates(repo_root):\n"
    "    return [cmd for cmd in gates_to_run if gate_key_for_cmd(cmd, repo_root)]\n"
)

FIXTURE_553_CRASHING_AUDIT = (
    "from __future__ import annotations\n"
    "import sys\n"
    "from pathlib import Path\n"
    "\n"
    "sys.path.insert(0, str(Path(__file__).resolve().parent))\n"
    "from gate_budget import gate_key_for_cmd  # noqa: E402\n"
    "\n"
    "def registered_gates(repo_root):\n"
    "    return None\n"
)

FIXTURE_553_GATES = {
    "tests/fixture_clean_gate.py": "raise SystemExit(0)\n",
    "tests/fixture_fail_gate.py": (
        "import sys\nsys.stderr.write('fixture says no\\n')\nraise SystemExit(1)\n"
    ),
    "tests/fixture_kill_gate.py": "raise SystemExit(124)\n",
}

def _fixture_553(root: Path, selected: str | None) -> None:
    """One gate on the map, so each arm's run has exactly one outcome to report."""
    (root / "tools").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "registry").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(GATE_BUDGET, root / "tools" / "gate_budget.py")
    (root / "tools" / "audit.py").write_text(FIXTURE_553_AUDIT, encoding="utf-8")
    for relative, body in FIXTURE_553_GATES.items():
        (root / relative).write_text(body, encoding="utf-8")
    gates = {selected: ["*.txt"]} if selected else {}
    (root / "registry" / "gate_triggers.json").write_text(
        json.dumps({"gates": gates, "floor": [], "default": "full"}), encoding="utf-8"
    )

def _run_553(root: Path, log: Path) -> tuple[int, list[str]]:
    """Run the real CLI with BOTH streams on one file, so their ORDER is observable."""
    with log.open("wb") as handle:
        proc = subprocess.run(
            [sys.executable, str(GATE_SELECT), "--paths", "x.txt", "--run",
             "--repo-root", str(root)],
            stdout=handle,
            stderr=subprocess.STDOUT,
            cwd=str(root),
        )
    return proc.returncode, log.read_text(encoding="utf-8").splitlines()

def _summary_553(lines: list[str]) -> list[str]:
    return [line for line in lines if "gate-select:" in line and " gate(s) ran, " in line]

def probe_a_run_STATES_its_own_outcome() -> None:
    """#553 (ruling `n=4180`): every `--run` exit prints ONE summary line, and a crash does not.

    A clean `--run` used to print nothing after its selection: `FAILED` and `NO VERDICT` were
    the only verdicts in the file and the clean path fell through to `return 0` in silence, so
    a green log and a crashed process were the SAME BYTES. Four arms, each with its own
    fixture gate, because each state must be distinguishable from the other three:

      * pass      -- rc=0, and the line says so
      * fail      -- rc=1, and the line says so
      * no verdict -- rc=124, and the line says so; a kill is never a pass
      * crash     -- NO line at all, which is the only thing that tells it from a pass

    The ordering arm is the discriminator for the flush: stdout is block-buffered when it is a
    file and stderr is not, so on the broken code a red run's log OPENED with `FAILED` lines
    about a tree it had not yet named.
    """
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)

        pass_root = base / "pass"
        _fixture_553(pass_root, "tests/fixture_clean_gate.py")
        rc, lines = _run_553(pass_root, base / "pass.log")
        summary = _summary_553(lines)
        check(
            "a CLEAN run exits 0 and STATES it in one summary line",
            rc == 0
            and summary == ["gate-select: 1 gate(s) ran, 0 failed, 0 no-verdict \u2014 rc=0"],
            f"rc={rc} summary={summary}",
        )
        check(
            "the summary line is the LAST line of the log",
            bool(lines) and bool(summary) and lines[-1] == summary[-1],
            f"last={lines[-1] if lines else None!r} summary={summary}",
        )

        fail_root = base / "fail"
        _fixture_553(fail_root, "tests/fixture_fail_gate.py")
        rc, lines = _run_553(fail_root, base / "fail.log")
        summary = _summary_553(lines)
        check(
            "a FAILING run exits 1 and STATES the failure and the code",
            rc == 1
            and summary == ["gate-select: 1 gate(s) ran, 1 failed, 0 no-verdict \u2014 rc=1"],
            f"rc={rc} summary={summary}",
        )
        header_at = next(
            (i for i, line in enumerate(lines) if line.startswith("gate-select: 1 gate(s), mode=")),
            None,
        )
        failed_at = next(
            (i for i, line in enumerate(lines) if line.startswith("gate-select: FAILED")), None
        )
        check(
            "the selection header is FLUSHED before the verdict it introduces",
            header_at is not None and failed_at is not None and header_at < failed_at,
            f"header_at={header_at} failed_at={failed_at} (header after verdict = unflushed)",
        )

        kill_root = base / "kill"
        _fixture_553(kill_root, "tests/fixture_kill_gate.py")
        rc, lines = _run_553(kill_root, base / "kill.log")
        summary = _summary_553(lines)
        check(
            "a KILLED gate exits 124 and the line says no-verdict, never a pass",
            rc == 124
            and summary == ["gate-select: 1 gate(s) ran, 0 failed, 1 no-verdict \u2014 rc=124"],
            f"rc={rc} summary={summary}",
        )

        crash_root = base / "crash"
        _fixture_553(crash_root, "tests/fixture_clean_gate.py")
        (crash_root / "tools" / "audit.py").write_text(
            FIXTURE_553_CRASHING_AUDIT, encoding="utf-8"
        )
        rc, lines = _run_553(crash_root, base / "crash.log")
        summary = _summary_553(lines)
        check(
            "a CRASHED run prints NO summary line, which is how it differs from a pass",
            rc != 0 and summary == [],
            f"rc={rc} summary={summary} (a line here means the crash was reported as a run)",
        )

def main() -> int:
    for relative in (GATE_SELECT, AUDIT, GATE_REGISTRY, REWORK_TABLE, GATE_BUDGET):
        if not relative.is_file():
            print(f"FAIL -- required artifact missing: {relative}")
            return 1
    if _SKIP_REASON:
        # The stated skip, for the SCRIPT face: a clean exit carrying its reason, exactly
        # as the pytest face does through `pytestmark`. A silent 0 would be a skip whose
        # reason has gone, which this factory counts as a defect (#199).
        print(f"gate triggers: SKIPPED — {_SKIP_REASON}")
        return 0
    for probe in PROBES:
        print(f"\n{probe.__name__}")
        probe()
    print(f"\n{len(PROBES) - len(FAILURES)} of {len(PROBES)} probe(s) clean")
    if FAILURES:
        print("failed: " + "; ".join(FAILURES))
        return 1
    print("gate triggers: the map covers every registered gate, and an uncovered path buys the full suite")
    return 0


# --- the pytest face ---------------------------------------------------------------
# `main()` owns the SCRIPT verdict, which is how `tools/audit.py` invokes this file. The
# wrappers below make each probe reachable as its own pytest node as well, so a factory
# that wires the kit into a PYTEST-based CI collects this gate instead of reading a green
# run over a file it never imported -- the hazard `tests/test_gate_invocation_mode.py`
# exists to name. The invocation MODE stays `script`: it is derived from this file's CALL
# SITE in `tools/audit.py`, and a dual-shaped file is judged by its call site, never by
# its shape. The assertion is on the FRESH failure delta, so a node fails only for the
# probe it names and never inherits a sibling's verdict.

def _assert_probe(probe) -> None:
    before = len(FAILURES)
    probe()
    fresh = FAILURES[before:]
    assert not fresh, "; ".join(fresh)

def test_probe_every_registered_gate_is_covered() -> None:
    _assert_probe(probe_every_registered_gate_is_covered)

def test_probe_every_map_key_is_registered() -> None:
    _assert_probe(probe_every_map_key_is_registered)

def test_probe_the_map_is_well_formed() -> None:
    _assert_probe(probe_the_map_is_well_formed)

def test_probe_every_read_a_gate_opens_is_declared() -> None:
    _assert_probe(probe_every_read_a_gate_opens_is_declared)

def test_probe_the_example_carries_the_same_shape() -> None:
    _assert_probe(probe_the_example_carries_the_same_shape)

def test_probe_globs_over_include_deliberately() -> None:
    _assert_probe(probe_globs_over_include_deliberately)

def test_probe_a_covered_change_selects_a_subset() -> None:
    _assert_probe(probe_a_covered_change_selects_a_subset)

def test_probe_the_default_deny_cannot_be_neutered() -> None:
    _assert_probe(probe_the_default_deny_cannot_be_neutered)

def test_probe_an_unreadable_map_is_none_not_empty() -> None:
    _assert_probe(probe_an_unreadable_map_is_none_not_empty)

def test_probe_the_cli_reports_the_mode() -> None:
    _assert_probe(probe_the_cli_reports_the_mode)

def test_probe_the_run_mode_executes_gates_with_the_interpreter() -> None:
    _assert_probe(probe_the_run_mode_executes_gates_with_the_interpreter)

def test_probe_a_run_states_its_own_outcome() -> None:
    _assert_probe(probe_a_run_STATES_its_own_outcome)
    _assert_probe(probe_a_run_STATES_its_own_outcome)

def test_probe_the_wall_is_read_from_the_judged_tree() -> None:
    _assert_probe(probe_the_wall_is_read_from_the_judged_tree)

def test_probe_a_gate_past_its_wall_is_no_verdict_and_an_absent_wall_is_declared() -> None:
    _assert_probe(probe_a_gate_past_its_wall_is_no_verdict_and_an_absent_wall_is_declared)

if __name__ == "__main__":
    sys.exit(main())
