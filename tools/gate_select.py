#!/usr/bin/env python3
"""Blast-radius gate selection — the gate set a change REQUIRES (issue #294).

The audit's pre-commit remedy ("run `tools/audit.py` before a commit that touches
the surface") was unexecutable: `registry/gates.json` declares 1387.9 s of measured
runtime against a 600 s inline ceiling, so the author fell back to a hand-picked
subset — and the author is structurally the least likely to pick the gate that reads
their own edit (#197's close landed RED on `main` for ~4 min that way).

This module removes the author from the SELECTION. The gate set is derived from the
CHANGED PATHS alone, through the declared map `registry/gate_triggers.json`.

**DEFAULT-DENY is the safety property, and it is not the map's completeness.** Any
changed path matching no declared glob forces the FULL gate set. An incomplete map
degrades to SLOW, never to SILENT — a subset that misses is the defect this module
exists to remove.

One predicate, several call sites: the pre-commit leg, the manual run, and
`tests/test_gate_triggers.py` all import `select()` rather than re-deriving the set.

**The set and the TREE are two questions, and #539 is the second one.** `--staged` runs the
selected gates in the working tree, because before a commit the working tree IS the change
under test. `--range` runs them in a CLEAN CHECKOUT of the range tip, because a range's
verdict must be a property of its commits: on a shared checkout a peer lane's in-flight edit
made the same command over the same ledger-only range return rc=0 and rc=1 eighteen minutes
apart, RED on a path the commit never touched. The verdict therefore NAMES the tree it judged
(`tree=worktree` or `tree=clean checkout <sha>`), so a receipt can never be ambiguous about
which tree produced it.
"""
from __future__ import annotations

import argparse
import fnmatch
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import NamedTuple

MAP_RELATIVE = "registry/gate_triggers.json"
MAP_EXAMPLE_RELATIVE = "TEMPLATE/registry/gate_triggers.example.json"
AUDIT_RELATIVE = "tools/audit.py"
BUDGET_MODULE = "gate_budget.py"
DEFAULT = "full"


def glob_matches(glob: str, path: str) -> bool:
    """Whether a changed path is covered by one declared glob.

    fnmatch semantics, so `*` also crosses `/` — over-inclusion is deliberate. A
    gate listed on a path it does not read costs only time; a gate MISSING from a
    path it reads is the silent miss this map exists to remove.
    """
    return fnmatch.fnmatchcase(path, glob)


def load_map(root: Path) -> dict | None:
    """The declared map, or None when it is absent (which the caller reads as full).

    The LIVE map is preferred; the shipped example is the fallback so a factory that
    has not yet copied it still resolves a map rather than silently selecting nothing.
    `None` is not "empty": it is an instrument that cannot read its declaration, and
    the caller turns it into the FULL set with a stated reason.
    """
    for relative in (MAP_RELATIVE, MAP_EXAMPLE_RELATIVE):
        candidate = root / relative
        if candidate.is_file():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return None
            if isinstance(data, dict) and isinstance(data.get("gates"), dict):
                return data
    return None


def select(mapping: dict, paths: list[str]) -> dict:
    """The selection for a set of changed paths — PURE, so a probe can drive it.

    Returns `{mode, gates, uncovered, default_deny}`:
      * `mode == "subset"` — every path was covered; `gates` is floor ∪ matches.
      * `mode == "full"`   — some path matched no declared glob (or the map could not
        be read); `gates` is the FULL set and `uncovered` names the offending paths,
        so the verdict says WHY it went full rather than only that it did.
    """
    gates = mapping.get("gates", {}) if isinstance(mapping, dict) else {}
    floor = set(mapping.get("floor", [])) if isinstance(mapping, dict) else set()
    selected = set(floor)
    uncovered: list[str] = []
    for path in paths:
        hit = [
            gate
            for gate, globs in gates.items()
            if any(glob_matches(str(glob), path) for glob in globs)
        ]
        if hit:
            selected.update(hit)
        else:
            uncovered.append(path)
    if uncovered:
        return {
            "mode": "full",
            "gates": sorted(floor | set(gates)),
            "uncovered": sorted(set(uncovered)),
            "default_deny": True,
        }
    return {"mode": "subset", "gates": sorted(selected), "uncovered": [], "default_deny": False}


def changed_paths_staged(root: Path) -> list[str] | None:
    """The index's pending paths, or None when the index cannot be read."""
    proc = subprocess.run(
        ["git", "-C", str(root), "diff", "--cached", "--name-only", "-z"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    return [p for p in proc.stdout.split("\0") if p]


def changed_paths_range(root: Path, rev_range: str) -> list[str] | None:
    """The paths a revision range touched, or None when git cannot read it."""
    proc = subprocess.run(
        ["git", "-C", str(root), "diff", "--name-only", "-z", rev_range],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    return [p for p in proc.stdout.split("\0") if p]


def _load_module(root: Path, relative: str, name: str):
    """Import a module by path — the pattern the pre-commit hook already uses.

    The module is registered in `sys.modules` BEFORE `exec_module`, and that is
    load-bearing rather than tidy (#436). `tools/audit.py` carries a module-level
    `@dataclass`, and on Python 3.14 `dataclasses` resolves the defining module through
    `sys.modules[cls.__module__]`; an unregistered module makes that lookup return `None`
    and the decorator dies with `AttributeError: 'NoneType' object has no attribute
    '__dict__'` before a single gate is read. Measured on 3.14.6: loading `tools/audit.py`
    without the registration fails exactly so, and succeeds with it.
    """
    source = root / relative
    if not source.is_file():
        return None
    spec = importlib.util.spec_from_file_location(name, source)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def declared_kill_code() -> int:
    """The fleet's kill code, READ from `tools/gate_budget.py` (#544).

    A second literal `124` in this module would be a private copy of a fleet constant, and
    a private copy goes stale silently: the day the fleet moves its kill code this runner
    keeps classifying the OLD number as a kill and reports every real kill as a FAILURE --
    the precise misreading the NO VERDICT class exists to prevent. So the declaration is
    imported, never retyped.

    Read from THIS module's own directory, not from the tree under judgement: the kill code
    is a property of the runner, and a clean checkout is not the authority on it. An
    unreadable declaration is a hard failure rather than a fallback to 124, because a
    classifier that cannot read its own vocabulary cannot say which class a run belongs to,
    and guessing the vocabulary is how the literal got here in the first place.
    """
    module = _load_module(
        Path(__file__).resolve().parent, BUDGET_MODULE, "oc_gate_budget_kill_code"
    )
    if module is None or not hasattr(module, "TIMEOUT_EXIT_CODE"):
        raise SystemExit(
            f"gate-select: cannot read {BUDGET_MODULE}, which declares the fleet's kill "
            f"code; without it a killed gate cannot be told from a failed one."
        )
    return module.TIMEOUT_EXIT_CODE

TIMEOUT_EXIT_CODE = declared_kill_code()

def declared_budget_table(root: Path) -> tuple[object | None, str]:
    """The declared walls, read ONCE per run, or the reason they could not be.

    ONE WALL, TWO PATHS (#583). The audit resolves a wall per gate and hands it to
    `run_gate(timeout=budget_sec)`, so a hung gate dies at its declared budget. This
    selector called `subprocess.run` with NO timeout at all, so the same gate ran
    unbounded here and the two sanctioned paths disagreed about whether it had finished:
    patrol receipts read `34 ran, 0 failed` for a gate the audit records as `exit 124`
    /UNKNOWN. A reader holding the green receipt concludes the gate passed; it never
    returned.

    THE WALL IS THE RESOLVED `budget_sec` — declared where the manifest declares one, and
    the manifest's own `default_sec` where it does not. What it is NEVER is
    `margin_for(measured_sec)` computed again here: the margin is already inside the
    declared value (`margin_x x measured_sec` is how the entry was derived), so re-applying
    it would make this path's wall LARGER than the audit's and re-create the disagreement
    one arithmetic layer down. Resolve the same key, take the same number.

    A DEFAULT-ORIGIN WALL IS NOT A MEASURED ONE, and this paragraph said "the declared
    `budget_sec` VERBATIM" until the population was counted: 53 of 109 gates have no entry
    and fall through to `default_sec` (69.27 s), so for those the wall is the DEFAULT's own
    derivation rather than a measurement of that gate. That is still the audit's number for
    the gate — which is all #583 requires, since the two paths must agree — but a reader who
    takes "declared" to mean "measured for THIS gate" is reading a claim the manifest does
    not make. The audit prints the fall-through population separately (`[DEFAULT]`).

    THE BASE IS `<root>/tools`, NOT `<root>` (#583). `gate_budget.py` declares
    `GATES_MANIFEST_PATH` as `Path(__file__).resolve().parent.parent / "registry" /
    "gates.json"`, so the directory the module is loaded FROM decides WHICH manifest is
    read. Loading it from the repo root misses the file entirely — `<root>/gate_budget.py`
    does not exist — and `_load_module` returns None for a missing source, which read as
    "no declared wall could be read" for EVERY gate: 33 exemptions in one patrol receipt,
    which is a receipt about the loader, not about the gates. The tree under judgement
    supplies both the code and its registry, so a worktree is judged by its own manifest.

    The KEY comes from `gate_budget.gate_key_for_cmd`, the audit's own derivation, because
    `registered_commands` already keys by it: one lookup, two callers, no drift.

    A manifest that cannot be read is NOT permission to run unbounded silently. The caller
    records a DECLARED EXEMPTION naming the gate and this reason, so the receipt says what
    it did. An unprinted absence is the bug class; a printed one is a record.
    """
    source_dir = root / "tools"
    module = _load_module(source_dir, BUDGET_MODULE, "oc_gate_budget_table")
    # THE TWO ARMS ARE DIFFERENT CAUSES AND MUST SAY SO (#583). `_load_module` answers None
    # for a source that is not there; reaching into that None raises AttributeError
    # ('NoneType' object has no attribute 'load_gate_budgets'), and a receipt carrying THAT
    # names the object that broke rather than the path that is missing — a printed mystery
    # where a printed absence was owed. So the absent module is reported as an absent module,
    # and only a module that LOADED and then failed reports the exception.
    if module is None:
        return None, f"{BUDGET_MODULE} not found under {source_dir}"
    try:
        return module.load_gate_budgets(repo_root=root), ""
    except Exception as exc:  # noqa: BLE001 — any failure here means "no declared wall"
        return None, f"{type(exc).__name__}: {exc}"

class GateRun(NamedTuple):
    """What a gate set produced: failures AND kills, kept apart on purpose (#544).

    `failures` is a positive finding -- a gate ran and returned non-zero. `no_verdicts` is
    the ABSENCE of a finding -- a gate was killed at its declared budget, so it neither
    passed nor failed. Collapsing the second into the first is what made a load-dependent
    kill read as a regression; keeping them in one object keeps a caller from silently
    reading only half the verdict.
    """

    failures: list[str]
    no_verdicts: list[str]
    # A THIRD BUCKET, never a silent omission (#583). A gate that ran with no wall because
    # the manifest could not be read is neither a pass nor a failure — it is a run whose
    # bound was ABSENT, and a caller that cannot see that reads a green receipt for a gate
    # nobody bounded. Defaulted so a caller that predates the field still constructs one.
    exemptions: tuple[str, ...] = ()
    # A RETRY MUST BE VISIBLE OR IT HIDES A SLOW GATE (#590, ruling n=4521 clause 1). A gate
    # killed once and passing on the bounded retry produces NO failure and NO no-verdict, so
    # without this bucket the retry would be invisible and "it passed" would be the whole
    # receipt -- indistinguishable from a gate that never came near its wall. A gate killed
    # AGAIN is already described in `no_verdicts`, which names both attempts.
    # Defaulted so a caller that predates the field still constructs one.
    retried: tuple[str, ...] = ()

def run_exit_code(run: GateRun) -> int:
    """The run's exit code, from its own two counts, in precedence order (#544).

    One derivation, used by the caller that RETURNS the code and by the summary line that
    STATES it (#553), so the two can never disagree: a line reading `rc=0` beside a
    process that exits 124 is the same class as the silence this unit removed.
    """
    if run.failures:
        return 1
    if run.no_verdicts:
        return TIMEOUT_EXIT_CODE
    return 0

def run_summary_line(selected: int, run: GateRun, rc: int) -> str:
    """The ONE line every `--run` exit prints, so a pass and a crash differ by its ABSENCE.

    Until #553 (ruling `n=4180`) a clean run printed nothing after its selection: the
    `FAILED` and `NO VERDICT` lines were the only verdicts in the file, and the clean path
    fell through to `return 0` in silence. So a green log and a crashed process were the
    same bytes -- a log that ends on a gate path either finished or died, and a reader had
    no way to tell. A run's own outcome is now stated on the way out:

        `gate-select: N gate(s) ran, F failed, V no-verdict — rc=0`

    THE CRASH STATE IS THE LINE'S ABSENCE (#553 clause 3, ruling `n=4180`): "a run that dies
    after printing its selection has a header, a gate list and no summary line". That is why
    the line is printed LAST and on EVERY exit path, including the clean one -- its presence
    is what makes a finished run tellable from a dead one, and a clean run that ends without
    it is exactly the two-states-not-three defect. The `rc` it carries adds #544's third
    OUTCOME beside the two the ruling names: `rc=0` passed, `rc=1` failed, `rc=124` took no
    verdict on at least one gate.

    The counts are the run's OWN: `F` is `len(run.failures)` and `V` is
    `len(run.no_verdicts)`, so the line introduces no second notion of success. `N` is the
    number of gates the run was given, and the three outcomes partition it -- a gate is
    clean, failed, or unjudged -- so `F + V` can never exceed `N`. A gate that could not be
    INVOKED (absent from the judged tree, no registered argv, an unexecutable argv) is
    counted in `F`, never left out of the accounting and never counted as clean: the
    module's standing law is that such a gate is reported, not skipped.

    An UNMEASURED gate is a no-verdict and never a pass (#552): a kill lands in
    `run.no_verdicts`, so it moves `V` and forces `rc=124`. This line restates that
    classification, it does not re-derive it.
    """
    return (
        f"gate-select: {selected} gate(s) ran, {len(run.failures)} failed, "
        f"{len(run.no_verdicts)} no-verdict — rc={rc}"
    )

def registered_commands(root: Path) -> dict[str, list[str]]:
    """`{gate key: argv}` read from the audit's OWN registration — the live list (#436).

    The argv comes from `tools/audit.py::registered_gates`, the very list
    `execute_mechanical_gates` runs, so the selector and the audit cannot disagree about
    which gates exist or how each is invoked. Until #436 the selector did not read the
    audit at all: it re-derived each argv by re-parsing the audit's SOURCE TEXT through
    `tests/gate_registry.registration_entries`, which keeps only the string LITERALS of an
    append call. An argument the audit COMPUTES is not a literal, so it survived the scan
    as nothing — `--namespace hygiene_namespace(repo_root)` arrived as a bare
    `--namespace`, argparse exited 2 ("expected one argument"), and the selector reported
    RED on a gate the audit runs green. A projection of the audit is not the audit; the
    remedy is to stop projecting.

    The key is the audit's own `gate_key_for_cmd` — the manifest's key derivation, imported
    there from `tools/gate_budget.py` — never a second parse of the argv. The argv returned
    is COMPLETE, interpreter included, because it is the audit's own list (#416's
    interpreter re-insertion is no longer needed and is gone with the projection).
    """
    audit = _load_module(root, AUDIT_RELATIVE, "oc_audit")
    if audit is None:
        return {}
    commands: dict[str, list[str]] = {}
    for cmd in audit.registered_gates(root):
        key = audit.gate_key_for_cmd(cmd, root)
        if key is None:
            continue
        commands.setdefault(key, list(cmd))
    return commands


def resolve_range_tip(root: Path, rev_range: str) -> str | None:
    """The commit at the END of the range — the tree `--range` must judge (#539).

    A range's verdict is a property of its TIP, and `A..B` means B. The expression is
    split on two-or-three dots rather than on `..` alone, because `"A...B".split("..")`
    yields `["A", ".B"]` — the leftover dot would be handed to git as a revision named
    `.B` and resolve to nothing. A range with an empty tail (`A..`) means HEAD, which is
    git's own reading of it.
    """
    tail = re.split(r"\.{2,3}", rev_range)[-1].strip() or "HEAD"
    proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--verify", f"{tail}^{{commit}}"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    sha = proc.stdout.strip()
    return sha or None

def materialise_clean_checkout(root: Path, sha: str) -> tuple[Path | None, str]:
    """A detached worktree at `sha` — the tree a range's gates read (#539).

    THE DEFECT THIS EXISTS FOR. `--range` selected its gates from the range and then ran
    them with `cwd=root`, i.e. the WORKING TREE. On this factory's shared checkout a peer
    lane holds in-flight edits for hours, so the same command over the same ledger-only
    range returned rc=0 at 19:19Z and rc=1 at 19:31Z with `FAILED tests/test_template_sync.py`
    — on a path the commit never touched, while the template pair was byte-identical AT
    the commit. A verdict that depends on who else is editing is not a verdict about the
    commits, and it cannot be repaired by refusing: refusal fires whenever any lane is
    mid-edit, which is the normal operating mode, so it leaves the author no lawful way to
    obtain a verdict at all and gets bypassed by hand-picked subsets — the exact failure
    #197/#294 built this module to remove.

    The checkout is OUTSIDE the tree, in a fresh temp directory, so it cannot be confused
    with a worktree a lane is using. The caller MUST remove it; `remove_clean_checkout`
    does that in a `finally`.
    """
    holder = Path(tempfile.mkdtemp(prefix="gate-select-"))
    target = holder / "tree"
    proc = subprocess.run(
        ["git", "-C", str(root), "worktree", "add", "--detach", str(target), sha],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        shutil.rmtree(holder, ignore_errors=True)
        return None, (proc.stderr.strip() or f"git worktree add exited {proc.returncode}")
    return target, ""

def remove_clean_checkout(root: Path, target: Path) -> None:
    """Drop the temporary worktree and its holder directory. Never raises."""
    subprocess.run(
        ["git", "-C", str(root), "worktree", "remove", "--force", str(target)],
        capture_output=True,
        text=True,
    )
    shutil.rmtree(target.parent, ignore_errors=True)

DIAGNOSIS_LIMIT = 200
"""One bound for the cause a FAILED receipt carries, so the receipt stays one readable line."""

_BARE_COUNT_HEADER = re.compile(
    r"^\d+\s+(?:problem|error|failure|issue|warning)(?:s|\(s\))?\s*:?$", re.IGNORECASE
)

def first_stderr_diagnosis(text: str | None, limit: int = DIAGNOSIS_LIMIT) -> str:
    """The first line of a failing child's stderr that STATES a cause, collapsed and BOUNDED.

    The runner recorded only `rc=<n>`, so a gate's own word -- `UNMEASURED`, `DISAGREE`, a
    pytest assertion -- died at the one surface a lane reads, and "a peer was running the
    audit" printed exactly like "your change broke this gate" (#552, ruling `n=4167`). The
    child's stderr is where it already states the cause.

    A BARE COUNT HEADER IS SKIPPED, and that is measured rather than defensive: this tree's
    own gates open stderr with `2 problem(s):` and put the cause on the lines BELOW it, so a
    literal first-line rule would land `rc=1: 2 problem(s):` in the receipt -- a line that
    names no cause while looking like a diagnosis. The skip is narrow (a line that is ONLY a
    count and a noun), so a one-line cause that happens to begin with a number survives.

    Empty when the child wrote nothing: an absent cause is stated by its absence, never by a
    dangling separator.
    """
    lines = [" ".join(line.split()) for line in (text or "").splitlines()]
    lines = [line for line in lines if line]
    if lines and _BARE_COUNT_HEADER.match(lines[0]):
        lines = lines[1:]
    return lines[0][:limit] if lines else ""

def run_gates(root: Path, gates: list[str], tree_label: str = "worktree") -> GateRun:
    """Run each gate's registered argv; return the failures, each naming the gate.

    The argv is the audit's own, interpreter included (#436), so it is executed VERBATIM —
    no interpreter is prepended and no token is dropped. Until #436 the argv was
    interpreter-RELATIVE, because the text scan kept only the TARGET-shaped literals and
    dropped the `sys.executable` the audit prefixes every append with; the interpreter was
    re-inserted here (#416) so a script gate (`tests/x.py`, mode 100644) did not die with
    PermissionError and a pytest gate (`-m pytest`) with FileNotFoundError. Reading the live
    list removes both the drop and the re-insertion.

    A gate with no registered argv is reported as a FAILURE rather than skipped: a
    gate the selector names but cannot run is an instrument that lies, and skipping it
    silently is the very class this module removes. An argv that cannot be EXECUTED is
    the same class, so it is reported rather than raised.

    A gate the clean checkout CANNOT MATERIALISE is a failure of the same class (#539
    clause 4), and it is checked BEFORE the argv lookup because the lookup cannot say
    why: `gate_key_for_cmd` resolves a key by requiring the file to exist, so a gate
    deleted at the range tip is simply absent from `registered_commands` and would be
    reported as "no registered argv" — a message that sends the reader to the audit when
    the missing thing is the tree. The check is scoped to the clean checkout: under
    `--staged` the worktree IS the change under test and its shape is not in question.

    A KILL IS NOT A FAILURE (#544). A gate that exits `TIMEOUT_EXIT_CODE` was killed at its
    declared budget: it produced no verdict, so calling it a failure asserts something the
    run never established. Measured on this box, same run, same bytes — the gate printed
    `NO VERDICT ... not counted as a FAIL: exit 124, the fleet's kill code (#206)` while
    this function reported `FAILED ... rc=124` one layer up, and an author reading the
    second concludes their change broke something. The two classes are returned separately
    so a caller cannot read one and believe it has the other.

    A FAILED RECEIPT CARRIES THE CHILD'S OWN WORD (#552, ruling `n=4167`). The line reads
    `<gate> — rc=<n>: <the child's first diagnostic stderr line>`, bounded to one line.
    The gate already writes `UNMEASURED` or `DISAGREE` there, and this function used to
    discard it -- so "a peer was running the audit" and "your change broke this gate"
    arrived as the same string, which is the whole of the filing.

    EVERY GATE RUNS UNDER ITS DECLARED WALL (#583). The audit resolves `budget_sec` per gate
    and passes it to `run_gate`, so a hung gate dies there. This function called
    `subprocess.run` with no `timeout` at all, so the SAME gate ran unbounded here while the
    audit killed it: the patrol receipt read `34 ran, 0 failed` for a gate the audit records
    as `exit 124`/UNKNOWN, and the reader holding the green receipt concludes it passed.
    A gate that never returns is not a slow gate; it is an absent verdict, and the receipt
    must say so.

    THE WALL IS THE RESOLVED `budget_sec` — the entry where the manifest declares one, the
    manifest's own `default_sec` where it does not — and never `margin_for(measured_sec)`
    computed again here. The margin is already inside the resolved number, so re-applying it
    would make this path's wall larger than the audit's and re-open the same disagreement one
    arithmetic layer down. One key (`gate_budget.gate_key_for_cmd`, the audit's own), one
    lookup (`GateBudgets.resolve`), one wall.

    A KILLED GATE LANDS IN `no_verdicts`, NOT `failures` — the #544 separation, unchanged.
    Whether the kill came from our own `timeout=` or from the child self-limiting at
    `TIMEOUT_EXIT_CODE` is not the caller's question: both are absent verdicts, and the two
    arrive in the same bucket so no caller can read one and believe it has the other.

    ONE BOUNDED RETRY, and ONLY for a timeout (#590, ruling n=4521 clause 1). This path
    appended to `no_verdicts` and moved on, while `audit.py:828` retried once per #93 ruling
    n=574 PART 4 — so the SAME gate on the SAME box at the SAME instant read PASS from the
    audit and NO VERDICT from this selector. A load-dependent timeout is transient by
    nature, so a single retry distinguishes a flake from a gate that is genuinely too slow;
    a SECOND timeout is the no-verdict it always was. The retry is bounded to exactly one
    and its occurrence is RECORDED in the no-verdict string, naming the first attempt's
    elapsed time, because an unrecorded retry becomes a way to hide a gate that is genuinely
    too slow. A non-zero exit is a VERDICT and is never retried; a child that self-kills at
    `TIMEOUT_EXIT_CODE` exits NORMALLY and is not retried either — the audit does not retry
    it and neither does this path, so both surfaces keep agreeing about what a verdict is.
    """
    commands = registered_commands(root)
    budgets, budget_note = declared_budget_table(root)
    failures: list[str] = []
    no_verdicts: list[str] = []
    exemptions: list[str] = []
    retried: list[str] = []
    for gate in gates:
        if tree_label != "worktree" and not (root / gate).is_file():
            failures.append(f"{gate} — selected, but not present in the {tree_label}")
            continue
        argv = commands.get(gate)
        if argv is None:
            failures.append(f"{gate} — no registered argv in {AUDIT_RELATIVE}")
            continue
        if budgets is None:
            timeout = None
            exemptions.append(
                f"{gate} — ran UNBOUNDED: no declared wall could be read ({budget_note})"
            )
        else:
            timeout = budgets.resolve(gate)[0]
        attempts = 0
        first_attempt_sec: float | None = None
        proc: subprocess.CompletedProcess[str] | None = None
        while True:
            attempts += 1
            started = time.monotonic()
            try:
                proc = subprocess.run(
                    list(argv), cwd=str(root), capture_output=True, text=True, timeout=timeout
                )
            except subprocess.TimeoutExpired:
                elapsed = time.monotonic() - started
                if attempts == 1:
                    first_attempt_sec = round(elapsed, 2)
                    continue
                no_verdicts.append(
                    f"{gate} — killed at its declared budget ({timeout:.2f}s) after "
                    f"running {elapsed:.2f}s, and killed AGAIN on the one bounded retry "
                    f"(first attempt {first_attempt_sec}s); it neither passed nor failed"
                )
                proc = None
            except OSError as exc:
                failures.append(f"{gate} — could not execute: {exc}")
                proc = None
            break
        if proc is None:
            continue
        if proc.returncode == TIMEOUT_EXIT_CODE:
            no_verdicts.append(
                f"{gate} — killed at its declared budget (exit {proc.returncode}); "
                f"it neither passed nor failed"
            )
        elif proc.returncode != 0:
            cause = first_stderr_diagnosis(proc.stderr)
            failures.append(
                f"{gate} — rc={proc.returncode}" + (f": {cause}" if cause else "")
            )
        if attempts == 2 and proc.returncode != TIMEOUT_EXIT_CODE:
            # A GATE THAT NEEDED ITS RETRY STILL PASSES -- AND MUST SAY SO (#590). Without
            # this line the retry is invisible whenever it works, which is exactly the case
            # it exists for: "it passed" would then be indistinguishable from a gate that
            # never came near its wall, and the retry would become a way to hide a gate
            # that is genuinely too slow. The killed-AGAIN case is NOT recorded here: its
            # no-verdict string already names both attempts, and repeating it in two
            # buckets would make one gate read as two.
            retried.append(
                f"{gate} — killed at its declared budget on the first attempt "
                f"({first_attempt_sec}s), produced its verdict on the one bounded retry"
            )
    return GateRun(failures, no_verdicts, tuple(exemptions), tuple(retried))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Select the gates a change requires.")
    parser.add_argument("--repo-root", default=None)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--staged", action="store_true")
    group.add_argument("--range", dest="rev_range")
    group.add_argument("--paths", nargs="+")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--run", action="store_true", help="run the selected gates")
    args = parser.parse_args(argv)

    root = Path(args.repo_root).resolve() if args.repo_root else Path.cwd()

    if args.paths:
        paths = args.paths
    elif args.staged:
        paths = changed_paths_staged(root)
        if paths is None:
            print("gate-select: the index could not be read; defaulting to FULL.", file=sys.stderr)
            paths = []
    else:
        paths = changed_paths_range(root, args.rev_range)
        if paths is None:
            print("gate-select: the range could not be read; defaulting to FULL.", file=sys.stderr)
            paths = []

    mapping = load_map(root)
    if mapping is None:
        # An unreadable declaration is not an empty map: state the reason and go full.
        full = sorted(set((mapping or {}).get("gates", {})))
        print("gate-select: %s could not be read; defaulting to FULL." % MAP_RELATIVE,
              file=sys.stderr)
        if args.json:
            print(json.dumps({"mode": "full", "gates": full, "uncovered": [],
                              "default_deny": True, "reason": "map unreadable"}))
        # THIS IS A `--run` EXIT TOO (#553 clause 1). It ran no gate, so it owes the summary
        # line -- and now that an ABSENT line is what marks a crash, returning silently here
        # would make an unreadable map indistinguishable from a process that died. The rc is
        # left as it was: this path is a selection failure, not a gate outcome, and giving it
        # a gate's code would be a second vocabulary. The line states the reason inline,
        # because `0 gate(s) ran ... rc=0` on its own is exactly the clean bill for work that
        # never happened (#544).
        if args.run:
            print(
                "gate-select: 0 gate(s) ran, 0 failed, 0 no-verdict \u2014 rc=0 "
                f"({MAP_RELATIVE} could not be read; NO VERDICT was taken)",
                file=sys.stderr if args.json else sys.stdout,
                flush=True,
            )
        return 0

    result = select(mapping, paths)

    # The tree the gates will read. `--range` judges the RANGE (#539): the selected gates
    # run in a clean checkout of its tip, so the verdict is a property of the COMMITS and
    # not of whoever else is mid-edit on the shared tree. `--staged` keeps reading the
    # worktree, because before a commit the worktree IS the change under test — the two
    # modes are deliberately not unified.
    judged_root = root
    tree_label = "worktree"
    checkout: Path | None = None
    if args.run and args.rev_range:
        sha = resolve_range_tip(root, args.rev_range)
        if sha is None:
            print(
                f"gate-select: the range tip of {args.rev_range!r} could not be resolved; "
                "no gate ran.",
                file=sys.stderr,
            )
            return 1
        checkout, why = materialise_clean_checkout(root, sha)
        if checkout is None:
            print(
                f"gate-select: the clean checkout of {sha[:8]} could not be materialised; "
                f"no gate ran: {why}",
                file=sys.stderr,
            )
            return 1
        judged_root = checkout
        tree_label = f"clean checkout {sha[:8]}"

    if args.json:
        print(json.dumps({**result, "tree": tree_label} if args.run else result))
    else:
        header = (
            f"gate-select: {len(result['gates'])} gate(s), mode={result['mode']}"
            + (f", tree={tree_label}" if args.run else "")
            + (f", default-deny on {len(result['uncovered'])} uncovered path(s)"
               if result["default_deny"] else "")
        )
        print(header)
        if result["default_deny"]:
            print("  DEFAULT-DENY — these paths match no declared trigger:")
            for path in result["uncovered"]:
                print(f"    {path}")
            print("  The FULL gate set is selected; run the whole audit (it exceeds the")
            print("  600 s inline ceiling, so it runs DETACHED):  python3 tools/audit.py")
        for gate in result["gates"]:
            print(gate)

    # FLUSH THE SELECTION BEFORE ANY VERDICT IS WRITTEN (#553 clause 2). stdout is
    # block-buffered when it is a file or a pipe; stderr is not. So the `FAILED` lines
    # reached the log immediately while the header naming the tree still sat in the buffer,
    # and a red run's log OPENED with verdicts about a tree it had not yet named. Flushing
    # here puts the tree first, and makes a clean run's log show its selection at once
    # instead of reading as a hang for as long as the gates take.
    sys.stdout.flush()

    if args.run:
        try:
            run = run_gates(judged_root, result["gates"], tree_label)
        finally:
            if checkout is not None:
                remove_clean_checkout(root, checkout)
        for failure in run.failures:
            print(f"gate-select: FAILED {failure}", file=sys.stderr)
        for killed in run.no_verdicts:
            print(f"gate-select: NO VERDICT {killed}", file=sys.stderr)
        # A PATH THAT DELIBERATELY RUNS UNBOUNDED MUST SAY SO (#583). When the declared
        # wall cannot be read at all, the gate still runs -- refusing would take the whole
        # selection down over a missing manifest -- but silence is the bug class this unit
        # removes: an unprinted absence reads exactly like a gate that ran under its wall.
        # So each such gate gets its own line naming the gate and the load failure, and the
        # word EXEMPTION is used rather than "warning" because it is a declared departure
        # from the registered wall, not an accident.
        for exempt in run.exemptions:
            print(f"gate-select: DECLARED EXEMPTION {exempt}", file=sys.stderr)
        # A RETRY THAT WORKED IS STILL A FACT ABOUT THE GATE (#590). It produced a verdict,
        # so it is neither a failure nor a no-verdict -- but silence here would make "it
        # passed" the whole receipt, indistinguishable from a gate that never approached its
        # wall. Printed for a clean run too, and BEFORE the summary line, so the last word
        # stays the verdict.
        for retry in run.retried:
            print(f"gate-select: RETRIED {retry}", file=sys.stderr)
        # THE EXIT CODE CARRIES THE DISTINCTION (#544). A run is not a pass just because
        # nothing failed: if a gate was killed, no verdict was taken on it, and rc=0 would
        # report a clean bill for work that never happened. The codes, in precedence order:
        #   1   — at least one gate FAILED. A positive finding outranks an absence of one,
        #         and it is the code the pre-commit leg already blocks on.
        #   124 — nothing failed, but at least one gate was KILLED. This is the fleet's kill
        #         code (#206), reused rather than invented: two vocabularies for one event
        #         is how a reader learns to trust neither. It is explicitly NOT a failure —
        #         a caller that treats it as one is doing exactly what this unit removed.
        #   0   — every selected gate ran and returned zero.
        rc = run_exit_code(run)
        if rc == 1:
            if run.no_verdicts:
                print(
                    f"gate-select: {len(run.failures)} gate(s) FAILED and "
                    f"{len(run.no_verdicts)} took NO VERDICT; the failures are reported "
                    f"above and the exit code is theirs (1).",
                    file=sys.stderr,
                )
        elif rc == TIMEOUT_EXIT_CODE:
            print(
                f"gate-select: NO VERDICT on {len(run.no_verdicts)} gate(s) — no verdict "
                f"was taken on them, so this run is NOT a pass and must not be read as "
                f"one. Exit {TIMEOUT_EXIT_CODE}, the fleet's kill code (#206), not 1: "
                f"nothing failed here, a budget fired.",
                file=sys.stderr,
            )
        # THE RUN'S LAST WORD, ON EVERY EXIT PATH (#553 clause 1). Printed after the detail
        # lines so it is the final line of the log, and printed even when nothing failed:
        # a clean run that ends without it is indistinguishable from a crash, which is the
        # whole of the filing. Under `--json` it goes to stderr, because stdout is the
        # machine-readable line and a consumer parsing it must not have to strip a
        # human sentence off the end.
        print(
            run_summary_line(len(result["gates"]), run, rc),
            file=sys.stderr if args.json else sys.stdout,
            flush=True,
        )
        return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
