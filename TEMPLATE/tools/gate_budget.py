"""Per-gate time budgets, read from `registry/gates.json` (issue #94, ruling n=744).

A gate's cap is a DECLARED MULTIPLE of a MEASURED runtime -- `budget_sec = margin_x
x measured_sec` -- never a round number. A cap picked by feel is uncalibrated in
both directions: too low, it kills a healthy gate and reports a timeout as a
verdict; too high, it hides a hung one. So each gate's cap is derived, and the
margin, the measured runtime and the ABSOLUTE revision the measurement was taken
at are declared together, so the number carries its own basis and a reader can
recompute it.

WHY A SEPARATE MODULE. `tools/registry.py` owns the FACTORY registry and validates
its manifest at import time; a gate budget is a timing concern with its own
manifest, and importing the fleet validator to read a timeout would couple two
unrelated surfaces -- `audit.py` would then fail on a missing `fleet.json` before
it ever reached a gate. This module mirrors that module's CONVENTION -- a path
constant, an environment override, a `*_path()` resolver, and a `load_*()` that
raises a named error -- without inheriting its fleet semantics.

WHERE THE TWO CONVENTIONS DIFFER, AND WHY. An ABSENT fleet manifest is an error: a
factory that declares no fleet has an unanswered question. An ABSENT gate-budget
manifest is NOT an error: a factory that has taken no measurements runs on the
declared fallback, and the audit PRINTS every gate that used it. A manifest that
EXISTS and is malformed IS an error -- an unreadable budget set is indistinguishable
from no budget set, and defaulting over it would silently re-cap every gate.

THE VALUES ARE NOT THE IMPLEMENTING LANE'S (n=574 PART 5). This module reads them;
it never invents one.

WHY A DECLARED REVISION IS NOW RESOLVED (#125, ruling n=786). `measured_at` was a
declared revision that NOTHING resolved, so an entry could describe a gate whose
command had moved under it and no reader could see it. A basis describes a COMMAND,
and a command has two halves -- the gate's own FILE, and the REGISTRATION that says
how it runs -- so both are compared against HEAD here:

  LEG A, file identity. The gate file's blob at `measured_at` against its blob at
  HEAD. Different bytes means the basis describes a DIFFERENT TEST: the entry is
  STALE-BY-GROWTH and its budget must be re-derived by the predicate above.

  LEG B, command identity. The `gates_to_run.append(...)` argv for that target, read
  from `tools/audit.py` at BOTH revisions. It moves while the gate's blob stays
  byte-identical -- measured under #124, where `5e3bfe3` re-pointed six registrations
  from the script form to `-m pytest` -- so a bytes-only check reads those entries
  CLEAN while the command it measured is gone. THE MAGNITUDE OF THAT MOVE IS NOT
  UNIFORM AND IS NOT ASSUMED. #124's own summary called it "roughly tripled their wall
  time"; re-measured at `c7773b4` from whole-command samples under the current form, the
  four of those six that had not yet been re-derived came out 0.77x / 1.37x / 1.47x /
  2.34x their declared bases -- ONE OF THEM FASTER THAN THE BASE
  IT REPLACED. So this leg asserts WHICH COMMAND was measured, never how much slower the
  new one is, and a re-derivation is taken from fresh samples under the current form
  rather than carried from any such summary. The two legs barely
  overlap: of the three gates that exhausted their budget on 2026-09-20, leg A saw
  one and leg B saw two, so a single-leg check reads two of the three as clean.

STALENESS IS NOT UNDER-BUDGET, and the two are reported apart on purpose. A basis
that no longer describes its test is a DATA fact; whether the cap still contains the
gate is a TIMING fact, and the audit's own UNKNOWN verdict is the second one. The
measured counter-example runs both ways: one gate kept its bytes, moved to the pytest
runner, and its cap stopped containing it -- while another's bytes moved and it got
FASTER, so re-deriving it would have TIGHTENED the cap. So neither leg refuses.

WHAT THIS DOES NOT DO. It never re-measures, never re-derives a budget, and never
refuses a manifest over staleness: the values are the process owner's (n=574 PART 5),
and a refusal would force the implementing lane to invent one. It REPORTS -- the
sweep's own account travels with the caps and is printed by the audit, naming the
population it examined, the revision it read, and every entry it could not reach.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

GATES_MANIFEST_PATH = REPO_ROOT / "registry" / "gates.json"
GATES_MANIFEST_ENV = "OC_GATES_MANIFEST"

# The LAST-RESORT cap, reached only when no manifest exists at all: a factory
# that carries `registry/gates.json` uses that manifest's `default.budget_sec`
# and never arrives here. It matches the value the template ships
# (`TEMPLATE/registry/gates.example.json`), so a factory that never measures
# behaves the same before and after it copies the example.
#
# It is a ROUND number, and it is NOT a declared multiple of a measured runtime.
# This is the one budget the calibration rule cannot supply, because a tree with
# no measurements has no single runtime to derive from. What upholds it is not its
# value but its VISIBILITY: the runner prints `[DEFAULT]` for every gate that
# falls through, so an uncalibrated cap is never silent, and a budget exhausted is
# UNKNOWN -- never green, never a plain failure. A factory that wants a calibrated
# cap measures its own box and declares it in its own manifest.
FALLBACK_DEFAULT_SEC = 120.0

# A timeout gets its OWN exit code -- the one `timeout(1)` uses -- so a killed gate
# is never confused with the `99` this module's caller returns for an unexpected
# exception. A gate that ran out of budget is UNKNOWN: it did not fail, it did not
# pass, and it must never be counted in a pass total.
TIMEOUT_EXIT_CODE = 124

# Every entry must carry its own BASIS, not just a number: a `budget_sec` with no
# `measured_sec` beside it is a cap picked by feel, which is the defect the law
# names. The loader refuses the shape rather than reading a bare number.
ENTRY_KEYS = ("budget_sec", "measured_sec", "measured_at", "margin_x")

# The load the `measured_sec` was taken AT -- the datum whose absence makes a kill
# unreadable, because a cap exceeded at load 13 and a cap exceeded on an idle box are the
# same number and different facts (#226). OPTIONAL, and its ABSENCE IS PRINTED rather than
# refused: the live manifest holds 48 entries and a load reading exists for 2, so a required
# key would force 46 invented values -- the very class this module exists to remove, a number
# travelling without its predicate. Forward-only: a NEW or UPDATED measurement carries the
# load it was taken at; the rest stay unmeasured and VISIBLE, never silently exempt.
LOAD_KEY = "load_at_measure"

# How far `budget_sec` may sit from `margin_x x measured_sec` before the entry is
# refused. MEASURED, not chosen: over the live 44-gate manifest the largest
# deviation is 0.014 absolute and 0.012% relative, both pure 2-decimal rounding,
# so a 1% band carries ~83x headroom over the worst real entry while still
# refusing a budget that was edited away from its stated basis.
MARGIN_LAW_TOLERANCE = 0.01

# The OTHER half of a declared basis: a budget is a cap on a COMMAND, and the audit
# is where that command is spelled out. A registration lives in one file, so the
# leg reads one path at two revisions rather than walking the whole run list.
AUDIT_SOURCE_PATH = "tools/audit.py"

# The canonical reader of those registrations is a tests-side predicate, and it is
# IMPORTED rather than re-derived. A second `gates_to_run.append(...)` scan is the
# defect this repo names as "one field, one predicate" (#99): the two agree until the
# append form changes, and then one of them reads another projection's values under
# the name it asked for. `gate_registry.registration_entries` reads the target AND the
# runner from ONE scan for exactly that reason.
REGISTRATION_MODULE = "gate_registry"

# The two legs, named so a report says WHICH half of the command moved rather than
# only that something did.
STALE_BYTES = "bytes"
STALE_RUNNER = "runner"

# Every git call below is a local object-database read that returns in milliseconds;
# the cap exists only so a wedged index lock or a corrupt repository fails the SWEEP
# instead of hanging the audit that calls it.
GIT_TIMEOUT_SEC = 20


class GateBudgetManifestError(Exception):
    """The gate-budget manifest exists but is unparseable or incomplete."""


@dataclass(frozen=True)
class StaleBudget:
    """One declared entry whose basis no longer describes the command that runs.

    `legs` names WHICH half moved, because the two have different consequences and a
    single "stale" bit would hide which file to look at. `detail` carries the evidence
    itself -- the two blob ids for leg A, the two argv forms for leg B -- so the report
    is checkable rather than an assertion a reader must take on trust.
    """

    key: str
    legs: tuple[str, ...]
    detail: str


@dataclass(frozen=True)
class GateBudgets:
    """The declared caps: a default, where that default came from, and the per-gate table."""

    default_sec: float
    default_source: str
    gates: dict[str, float] = field(default_factory=dict)
    # WHICH declared entries carry the load their `measured_sec` was taken at, and the
    # account of the population that does not. The note is the point, on the same reasoning
    # as `stale_note`: a reader meeting a kill must be able to tell a hung gate from a busy
    # box, and where no entry states its load that reader has NOTHING to tell them apart --
    # so the gap is printed beside the verdict instead of being absent from it.
    load_declared: tuple[str, ...] = ()
    load_note: str = ""
    loads: dict[str, float] = field(default_factory=dict)
    # The staleness sweep's findings and its OWN account, so a caller can print the
    # population examined beside the count found. An empty tuple with a note that says
    # why is the honest form of "nothing reported"; an empty tuple alone is not.
    stale: tuple[StaleBudget, ...] = ()
    stale_note: str = ""

    def resolve(self, key: str | None) -> tuple[float, str]:
        """The budget for a gate key, and whether it was DECLARED or fell to the default.

        The second element is the point: a gate with no entry is not an error, but
        the audit must be able to PRINT which gates used the default, because a
        declared default with a printed population is not an exempt-by-silence
        surface, while an unprinted fallback is.
        """
        if key is not None and key in self.gates:
            return self.gates[key], "declared"
        return self.default_sec, "default"


def gates_manifest_path() -> Path:
    """Where the budget manifest is read from: the environment override, else the default.

    The override exists so a probe can point the reader at a manifest it built,
    without writing into the live store.
    """
    override = os.environ.get(GATES_MANIFEST_ENV)
    return Path(override) if override else GATES_MANIFEST_PATH


def _git(repo_root: Path, *args: str, stdin: str | None = None) -> tuple[int, str, str]:
    """One git call inside `repo_root`: exit code and both streams, never through a pipe.

    OFFLINE and read-only by construction -- every caller passes an object-database read
    (`rev-parse`, `cat-file`, `show`). A missing or wedged `git` is a STATED failure
    rather than an exception, because a tree checked out without git must still be able
    to read its budgets: that failure belongs in the sweep's note, not in a traceback.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            input=stdin,
            timeout=GIT_TIMEOUT_SEC,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


def _resolve_commit(repo_root: Path, rev: str) -> str | None:
    """The commit a revision resolves to, or None when it does not resolve here.

    Resolved BEFORE any blob is read, and that ordering is load-bearing rather than
    tidy: `cat-file --batch-check` answers "missing" both for a path absent from a real
    tree AND for every path asked of a revision that resolves to nothing at all, so a
    sweep that skipped this step would read an unreachable `measured_at` as "every gate
    file changed" and report the entire manifest stale.
    """
    code, out, _ = _git(repo_root, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
    resolved = out.strip()
    return resolved if code == 0 and resolved else None


def _blob_ids(repo_root: Path, specs: list[str]) -> dict[str, str] | None:
    """Blob id per `<commit>:<path>` spec, for the specs that name one.

    ONE call for the whole population: a per-entry `rev-parse` would be two process
    spawns per gate, and the audit this feeds already exceeds its own runtime budget.

    None means THE OBJECT DATABASE DID NOT ANSWER, and that is a different fact from an
    empty mapping. Collapsing the two would let a failed read report as "nothing changed"
    -- a clean verdict over a population that was never examined, which is the failure
    these legs exist to remove. A spec that names no blob is simply absent from the
    result, which is the fact the caller compares.
    """
    if not specs:
        return {}
    code, out, _ = _git(
        repo_root, "cat-file", "--batch-check", stdin="\n".join(specs) + "\n"
    )
    if code != 0:
        return None
    lines = out.splitlines()
    if len(lines) != len(specs):
        return None
    ids: dict[str, str] = {}
    for spec, line in zip(specs, lines):
        parts = line.split(" ")
        if len(parts) == 3 and parts[1] in ("blob", "tree", "commit"):
            ids[spec] = parts[0]
    return ids


def _registration_reader():
    """The canonical registration predicate, imported from the tree that carries it.

    WHICH TREE: `REPO_ROOT`, never the caller's `repo_root`. That predicate parses TEXT
    -- it is a property of the DEPLOYED tree, not of the repository whose text is being
    parsed -- so a sweep over a synthetic repository still reads through the one real
    scanner, and no fixture can shadow the canonical parser with a lookalike.

    None means the predicate could not be imported, and the caller REPORTS that instead
    of passing over it: a leg that cannot judge must say so.
    """
    tests_dir = REPO_ROOT / "tests"
    try:
        if str(tests_dir) not in sys.path:
            sys.path.insert(0, str(tests_dir))
        module = __import__(REGISTRATION_MODULE)
    except ImportError:
        return None
    return getattr(module, "registration_entries", None)


def _runner_forms(repo_root: Path, commit: str) -> dict[str, tuple[str, ...]] | None:
    """`{target: argv forms}` for the audit's registrations AT ONE COMMIT.

    None means the registration source or its reader is unavailable -- an unreadable
    registration is not an empty one, so the caller reports it rather than reading it as
    "nothing moved". A target appending more than once keeps every form, so a duplicate
    registration cannot be hidden by the last one written.
    """
    reader = _registration_reader()
    if reader is None:
        return None
    code, out, _ = _git(repo_root, "show", f"{commit}:{AUDIT_SOURCE_PATH}")
    if code != 0:
        return None
    forms: dict[str, list[str]] = {}
    for entry in reader(out):
        forms.setdefault(entry["target"], []).append(entry["argv"])
    return {target: tuple(sorted(set(argv))) for target, argv in forms.items()}

def budget_staleness(
    entries: dict[str, object], repo_root: Path | None = None
) -> tuple[tuple[StaleBudget, ...], str]:
    """Which declared bases no longer describe what runs, and the sweep's own account.

    THE PREDICATE, with its population and its instant. For every declared entry the
    command its basis was measured on is reconstructed at `measured_at` and compared with
    the command the audit runs at HEAD: `measured_at` is resolved to a commit, the gate
    file's BLOB is compared (leg A), and the argv its REGISTRATION declares is compared
    (leg B). An entry whose legs both match describes an unchanged command, and a
    remaining gap between its basis and its runtime is the INSTANT -- load, reported and
    never gated.

    THE BOUND, stated because a clean sweep is otherwise overread. These legs cover the
    gate's own blob and the runner form its registration names. They do NOT see a shared
    module the gate imports, the interpreter's version, the host's load, or a target a
    registration reader cannot name. A target present on ONE side of the comparison only
    is deliberately NOT compared: a registration that appears or disappears belongs to the
    registered-set directions, and reporting it here too would make one fact look like two.

    FAIL-OPEN, AND PRINTED RATHER THAN REFUSED. A revision this clone cannot resolve
    (shallow, or a rewritten history) is UNKNOWN, never clean, and it is named in the note
    with the count it covers. Nothing here raises: a tree checked out without git must
    still be able to read its budgets, and this module's own doctrine already carries the
    pattern -- a declared fallback with a PRINTED population is not an exempt-by-silence
    surface, while an unprinted one is.

    `repo_root` defaults to REPO_ROOT and exists so a probe can aim the object-database
    reads at a throwaway repository. It is not a switch for the check, which always runs.
    """
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    if not entries:
        return (), (
            "no declared entries — this manifest declares no per-gate basis, so there is "
            "nothing to compare against HEAD"
        )

    head = _resolve_commit(root, "HEAD")
    if head is None:
        return (), (
            f"NOT RUN — no resolvable HEAD under {root}, so there is no revision to compare "
            f"a declared basis against. {len(entries)} declared entr"
            f"{'y' if len(entries) == 1 else 'ies'} left UNEXAMINED rather than reported clean."
        )

    by_rev: dict[str, list[str]] = {}
    for key, entry in entries.items():
        rev = entry.get("measured_at") if isinstance(entry, dict) else None
        if isinstance(rev, str):
            by_rev.setdefault(rev, []).append(key)

    stale: list[StaleBudget] = []
    unresolved: list[str] = []
    reached = bytes_blind = runner_blind = 0
    for rev in sorted(by_rev):
        keys = sorted(by_rev[rev])
        commit = _resolve_commit(root, rev)
        if commit is None:
            unresolved.append(f"{rev} ({len(keys)} entr{'y' if len(keys) == 1 else 'ies'})")
            continue
        reached += len(keys)

        # LEG A — the gate FILE's blob at the declared revision against its blob at HEAD.
        was = _blob_ids(root, [f"{commit}:{key}" for key in keys])
        now = _blob_ids(root, [f"{head}:{key}" for key in keys])
        bytes_moved: dict[str, str] = {}
        if was is None or now is None:
            bytes_blind += len(keys)
        else:
            for key in keys:
                before, after = was.get(f"{commit}:{key}"), now.get(f"{head}:{key}")
                if before != after:
                    bytes_moved[key] = f"blob {before or 'absent'} -> {after or 'absent'}"

        # LEG B — the argv its REGISTRATION declares, which moves while the blob does not.
        at_forms = _runner_forms(root, commit)
        head_forms = _runner_forms(root, head)
        runner_moved: dict[str, str] = {}
        if at_forms is None or head_forms is None:
            runner_blind += len(keys)
        else:
            for key in keys:
                if (
                    key in at_forms
                    and key in head_forms
                    and at_forms[key] != head_forms[key]
                ):
                    runner_moved[key] = (
                        f"registration {' '.join(at_forms[key])} -> "
                        f"{' '.join(head_forms[key])}"
                    )

        for key in sorted(set(bytes_moved) | set(runner_moved)):
            legs: list[str] = []
            evidence: list[str] = []
            if key in bytes_moved:
                legs.append(STALE_BYTES)
                evidence.append(bytes_moved[key])
            if key in runner_moved:
                legs.append(STALE_RUNNER)
                evidence.append(runner_moved[key])
            stale.append(StaleBudget(key=key, legs=tuple(legs), detail="; ".join(evidence)))

    plural = "y" if len(entries) == 1 else "ies"
    note = (
        f"{len(stale)} of {len(entries)} declared entr{plural} no longer describe what runs "
        f"— the gate's own blob and its registered argv, compared against HEAD {head[:12]}"
    )
    if unresolved:
        note += (
            " | NOT EXAMINED — measured_at resolves to nothing here for "
            + ", ".join(unresolved)
            + "; a basis whose revision is unreachable is UNKNOWN, never clean"
        )
    if bytes_blind or runner_blind:
        note += (
            f" | leg A did not answer for {bytes_blind} entr"
            f"{'y' if bytes_blind == 1 else 'ies'} and leg B for {runner_blind} — reported "
            f"rather than read as unchanged"
        )
    if reached == 0:
        note += (
            f" | NOTHING EXAMINED — 0 of {len(entries)} entries carried a reachable revision, "
            f"so this sweep reaches no verdict at all"
        )
    return tuple(stale), note


def gate_key_for_cmd(cmd: list[str], repo_root: Path) -> str | None:
    """The manifest key for a gate command: the repo-relative path of the file it runs.

    THE TRAP THIS EXISTS FOR. The manifest is keyed by a gate's repo-relative path,
    but a command does NOT put that path in a fixed position: `[python, -m, pytest,
    tests/X.py]` carries it LAST, while `[python, tools/ledger.py, verify]` carries
    it FIRST. A `cmd[-1]` lookup therefore misses EVERY gate that takes arguments --
    and misses it silently, because a miss falls through to the default rather than
    failing. So the key is derived by asking which ARGUMENT resolves to a file under
    the repo root, which is the property the manifest key actually names.

    An argument that resolves OUTSIDE the repo root is skipped, and that is load
    bearing rather than defensive: `sys.executable` is an absolute path to a real
    file, so a naive `is_file()` test would return `/usr/bin/python3` as the key for
    every gate in the tree.

    The bound: the first resolving argument wins, so a command naming two gate files
    keys on the first. No registration in this tree does that.
    """
    root = Path(repo_root).resolve()
    for arg in cmd:
        if not arg or arg.startswith("-"):
            continue
        candidate = Path(arg)
        if not candidate.is_absolute():
            candidate = root / candidate
        try:
            resolved = candidate.resolve()
            if not resolved.is_file():
                continue
            return resolved.relative_to(root).as_posix()
        except (OSError, ValueError):
            continue
    return None


# The default's own derivation. A declared entry must carry its basis -- a `budget_sec`
# with no `measured_sec` beside it is a cap picked by feel, which is the defect this
# manifest exists to fix. The DEFAULT carried a bare number until #208, and the shape it
# was missing is the same one: the value, the margin, the measured runtime it rests on, the
# absolute revision of that measurement, and the POPULATION the measurement was taken over.
# The population is what makes the derivation checkable. An undeclared gate is a gate
# NOBODY has measured, so the honest default is bounded by the gates that actually fall
# through to it -- never by the largest entry that happens to exist, which is how the
# withdrawn `_note` sentence came to be false at 8.51x (#208).
DEFAULT_BASIS_KEYS = ("margin_x", "measured_sec", "measured_at", "population")

# The margin law the manifest's own header STATES, encoded so the default's containment leg
# computes the margin the way a declared entry's recorded `margin_x` does. Measured over the
# live 48 entries: 47 reproduce this expression at 3 dp, and the 48th
# (`tests/test_shipped_mechanism_law.py`) is a STATED EXCEPTION at 8.0 rather than the law's
# 8.167, so this is the derivation rule for a fresh measurement and not a universal
# reproduction of the recorded ones. Prose cannot be recomputed: the header remains the
# statement, this is its predicate.
MARGIN_ASYMPTOTIC = 4.0
MARGIN_FIXED_SEC = 0.75


def margin_for(measured_sec: float) -> float:
    """The margin the manifest's header states for a `measured_sec`-second measurement."""
    return MARGIN_ASYMPTOTIC + MARGIN_FIXED_SEC / measured_sec


def default_basis_problems(
    default: object, tolerance: float = MARGIN_LAW_TOLERANCE
) -> list[str]:
    """Problems in the derivation the DEFAULT states. Empty when none is stated.

    SCOPED TO A STATED DERIVATION, and the scope is load-bearing rather than convenient:
    the kit ships `registry/gates.example.json` with a bare `default` ON PURPOSE, so a
    factory inherits the SHAPE and not this box's measurement. A manifest that states no
    derivation asserts no relation, and there is nothing here that can be false; a manifest
    that states one asserts all of what follows, and is refused wherever its own numbers
    contradict it.
    """
    if not isinstance(default, dict):
        return ["`default` is not an object, so no derivation can be read from it"]
    if not _is_positive_number(default.get("budget_sec")):
        return [
            f"default.budget_sec must be a positive number, not {default.get('budget_sec')!r}"
        ]
    if not any(key in default for key in DEFAULT_BASIS_KEYS):
        return []
    missing = [key for key in DEFAULT_BASIS_KEYS if key not in default]
    if missing:
        return [
            f"default states a PARTIAL derivation -- no {sorted(missing)}. A basis is stated "
            f"whole or not at all: a partial one reads as measured while the measurement it "
            f"rests on is absent"
        ]
    problems: list[str] = []
    margin, measured = default["margin_x"], default["measured_sec"]
    if not _is_positive_number(margin) or not _is_positive_number(measured):
        return [
            f"default.margin_x / default.measured_sec must be positive numbers, not "
            f"{margin!r} / {measured!r}"
        ]
    if not isinstance(default["measured_at"], str) or not default["measured_at"]:
        problems.append(
            "default.measured_at must name the ABSOLUTE revision the population was measured at"
        )
    population = default["population"]
    if not isinstance(population, dict) or not population:
        return problems + [
            "default.population must be a non-empty object of gate -> measured seconds; the "
            "population IS the derivation, and an empty one describes nothing"
        ]
    malformed = sorted(k for k, v in population.items() if not _is_positive_number(v))
    if malformed:
        return problems + [
            f"default.population carries {len(malformed)} non-positive runtime(s): "
            f"{malformed[:3]}"
        ]
    largest = max(population.values())
    if abs(measured - largest) > 0.005:
        problems.append(
            f"default.measured_sec {measured} is not the largest recorded runtime "
            f"{round(largest, 2)} -- the stated largest and the population disagree"
        )
    budget = default["budget_sec"]
    required = margin * measured
    if budget < required - tolerance * budget:
        problems.append(
            f"default.budget_sec {budget} is BELOW its own stated derivation "
            f"({margin} x {measured} = {round(required, 4)}) -- the default does not contain "
            f"the population it says it was derived from"
        )
    above = sorted(
        k for k, v in population.items() if margin_for(v) * v > budget * (1 + tolerance)
    )
    # IMPLIED, and shipped anyway for the reason the ruling names the property directly: a
    # gate above the default is the REALIZED harm, and an invariant that holds only as a
    # consequence of two others is one nobody has written down. Because margin(v) x v expands
    # to 4v + 0.75 -- monotonic in v -- the largest runtime carries the largest margin-budget,
    # so the two checks above already imply this one. Stated rather than left as a surprise
    # for a reader who finds the check unreachable in isolation.
    if above:
        problems.append(
            f"{len(above)} recorded entr(ies) sit ABOVE the default {budget}: {above[:3]} -- "
            f"each would be killed by the very cap this population is the basis of"
        )
    return problems


def default_population_problems(
    default: object, live_undeclared: object, tolerance: float = MARGIN_LAW_TOLERANCE
) -> list[str]:
    """Problems in the DEFAULT's stated population against the LIVE undeclared set.

    Split from `default_basis_problems` because the two halves need different inputs: the
    intrinsic half is readable wherever the manifest is, while this half needs the
    registration list, which only a caller that holds the tree can read. A manifest with no
    stated derivation has no population to compare, and is silent here for the same reason
    it is silent there.
    """
    if not isinstance(default, dict):
        return []
    if not any(key in default for key in DEFAULT_BASIS_KEYS):
        return []
    population = default.get("population")
    if not isinstance(population, dict) or not population:
        return []
    recorded = set(population)
    live = {key for key in (live_undeclared or ()) if isinstance(key, str)}
    problems: list[str] = []
    missing = sorted(live - recorded)
    if missing:
        problems.append(
            f"{len(missing)} gate(s) fall through to the default and are NOT in the stated "
            f"population: {missing[:3]} -- the default is re-derived whenever this "
            f"population changes"
        )
    retired = sorted(recorded - live)
    if retired:
        problems.append(
            f"{len(retired)} recorded name(s) no longer fall through to the default: "
            f"{retired[:3]}"
        )
    return problems


def load_gate_budgets(path: Path | None = None, repo_root: Path | None = None) -> GateBudgets:
    """Read the gate-budget manifest. Raises `GateBudgetManifestError` on a malformed one.

    An ABSENT manifest is not a defect and returns the declared fallback with an
    empty table; a manifest that exists and cannot be read is a defect and raises,
    because the two are otherwise the same output for a caller that only sees caps.

    Every declared entry is then swept against its OWN `measured_at` (#125), and the
    findings and the sweep's account come back with the caps. A malformed entry still
    RAISES; staleness never does, because the values are the process owner's and reporting
    is what this module owes its caller.
    """
    target = path or gates_manifest_path()
    if not target.is_file():
        return GateBudgets(
            default_sec=FALLBACK_DEFAULT_SEC,
            default_source=f"no manifest at {target} — declared fallback",
            gates={},
            stale=(),
            stale_note=f"no manifest at {target} — nothing declared to sweep",
        )
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise GateBudgetManifestError(f"{target}: cannot read the manifest — {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GateBudgetManifestError(f"{target}: does not parse as JSON — {exc}") from exc
    if not isinstance(data, dict):
        raise GateBudgetManifestError(f"{target}: the manifest must be a JSON object")

    default = data.get("default")
    if not isinstance(default, dict):
        raise GateBudgetManifestError(f"{target}: no `default` object")
    default_sec = default.get("budget_sec")
    if not _is_positive_number(default_sec):
        raise GateBudgetManifestError(
            f"{target}: default.budget_sec must be a positive number, not {default_sec!r}"
        )
    # A default that STATES its derivation must follow it, on the same terms a declared entry
    # is held to: the value is a function of its basis, and a number edited away from that
    # basis is the defect this manifest exists to remove. A default that states NONE is not
    # refused -- the shipped example carries a bare one on purpose, so a factory inherits the
    # SHAPE without this box's measurement (#208).
    if LOAD_KEY in default and not _is_positive_number(default[LOAD_KEY]):
        raise GateBudgetManifestError(
            f"{target}: default.{LOAD_KEY} must be a positive number, not "
            f"{default[LOAD_KEY]!r} -- the field states the load the measurement was taken "
            f"AT, and a value that is not a number states nothing a reader can compare"
        )
    stated_default_problems = default_basis_problems(default)
    if stated_default_problems:
        raise GateBudgetManifestError(
            f"{target}: the default's stated derivation does not hold — "
            + "; ".join(stated_default_problems)
        )

    entries = data.get("gates", {})
    if not isinstance(entries, dict):
        raise GateBudgetManifestError(f"{target}: `gates` must be a JSON object")

    gates: dict[str, float] = {}
    for key, entry in entries.items():
        where = f"{target}: gates[{key!r}]"
        if not isinstance(entry, dict):
            raise GateBudgetManifestError(f"{where} is not an object")
        for name in ENTRY_KEYS:
            if name not in entry:
                raise GateBudgetManifestError(
                    f"{where} has no `{name}` key — a budget with no stated basis is a "
                    f"cap picked by feel, which is the defect this manifest exists to fix"
                )
        if LOAD_KEY in entry and not _is_positive_number(entry[LOAD_KEY]):
            raise GateBudgetManifestError(
                f"{where}.{LOAD_KEY} must be a positive number, not {entry[LOAD_KEY]!r} -- "
                f"the field states the load the measurement was taken AT, and a value that is "
                f"not a number states nothing a reader can compare against a kill"
            )
        for name in ("budget_sec", "measured_sec", "margin_x"):
            if not _is_positive_number(entry[name]):
                raise GateBudgetManifestError(
                    f"{where}.{name} must be a positive number, not {entry[name]!r}"
                )
        if not isinstance(entry["measured_at"], str):
            raise GateBudgetManifestError(
                f"{where}.measured_at must be a string revision, not {entry['measured_at']!r}"
            )
        declared = entry["margin_x"] * entry["measured_sec"]
        budget = entry["budget_sec"]
        if abs(budget - declared) > MARGIN_LAW_TOLERANCE * budget:
            raise GateBudgetManifestError(
                f"{where}: budget_sec {budget} is not margin_x x measured_sec "
                f"({entry['margin_x']} x {entry['measured_sec']} = {round(declared, 4)}) "
                f"within {MARGIN_LAW_TOLERANCE:.0%} — the entry states a basis its own "
                f"number does not follow"
            )
        gates[key] = float(budget)

    stale, stale_note = budget_staleness(entries, repo_root)
    # The load population, printed rather than refused. `default` counts as one declarer of
    # its own, because a gate that falls through to it inherits that measurement's load.
    load_declared = tuple(sorted(k for k, e in entries.items() if LOAD_KEY in e))
    loads = {k: float(e[LOAD_KEY]) for k, e in entries.items() if LOAD_KEY in e}
    # `default` is a base in its own right: a gate that falls through to it inherits that
    # measurement, and therefore that measurement's load.
    total = len(entries)
    bases = total + 1
    on_default = LOAD_KEY in default
    declarers = len(load_declared) + (1 if on_default else 0)
    if declarers:
        where = (f"`default` + {len(load_declared)} of {total} declared entries"
                 if on_default else
                 f"none on `default`, {len(load_declared)} of {total} declared entries")
        load_note = (
            f"{LOAD_KEY}: {declarers} of {bases} declared bases carry it ({where}); the "
            f"other {bases - declarers} state none, so for those a kill cannot be told from "
            f"a busy box"
        )
    else:
        load_note = (
            f"{LOAD_KEY}: 0 of {bases} declared bases carry it (neither `default` nor any of "
            f"the {total} entries), so a kill on this manifest cannot be told from a busy box "
            f"on any gate"
        )
    return GateBudgets(
        default_sec=float(default_sec),
        default_source=f"{target}:default",
        gates=gates,
        stale=stale,
        stale_note=stale_note,
        load_declared=load_declared,
        load_note=load_note,
        loads=loads,
    )


def _is_positive_number(value: object) -> bool:
    """True for a real number above zero. `bool` is excluded: `True` is not a budget."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0
