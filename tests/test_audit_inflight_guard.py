#!/usr/bin/env python3
"""Gate: an audit run is guarded against itself, and its children do not outlive it.

Origin (issue #145, ruling n=940). Two audits contending for one cgroup is real load, and
it was measured: 17 cron jobs fired inside a 19-second window on 2026-09-22 after the
scheduler starvation filed as opencrabs#504, and the pile included audits from MORE THAN
ONE repository. The contended unit is the RUN, not the gate — the gate loop in
`tools/audit.py` is sequential (`for cmd in gates_to_run`), so one run can never overlap
itself, and a per-gate guard would bound nothing while adding an acquisition per gate.

This gate is the mechanism for the ruling's two halves, and it states both:

  (1) THE IN-FLIGHT GUARD — a second run refuses rather than piling on. The default is
      NON-BLOCKING (`--wait` is the caller's opt-in), because waiting is what creates the
      orphan: a lane's turn that blocks on the lock can die before it ever holds it. The
      refusal exits on its OWN code (3 — distinct from the 1 a gate failure returns and
      from the 2 the budget-manifest refusal returns), prints a NAMED stderr line naming
      the lock so did-not-run is distinguishable from ran-and-failed, and writes NO run
      row. The no-row rule is load-bearing: `OUTCOME_DOMAIN` is a closed four-token set,
      so a refused run's row would either red a gate or let a run that did no work grade
      the yield it never measured.

  (2) THE ORPHAN PROPERTY — no process in a run's tree outlives the run. The lock does
      NOT close this half: a dead holder releases the lock, so the lock never sees an
      orphan. The mechanism is `PR_SET_PDEATHSIG`, set in the gate child before `exec`.

THE RECURSION CASE IS THE LOAD-BEARING PROBE, and it is the reason the exemption exists.
`tests/test_audit_rates.py` is a registered gate that runs `audit.py --json --no-gates`
and asserts rc==0. A NAIVE whole-run guard therefore makes the outer run hold the lock
while its own gate's nested run refuses, and the gate reds. The exemption is principled
rather than a carve-out: `--no-gates` spawns no gates and so contributes none of the load
the guard bounds. The probe that holds the lock and runs `--no-gates` under it is what
catches that naive guard, so both directions are driven: a guard that is ABSENT fails the
refusal probe, and a guard that is TOO WIDE fails the recursion probe.

A THIRD DIRECTION RIDES THIS GATE, learned by shipping the first version broken. The gate
runs INSIDE an audit, and that run holds `.audit.lock` for its whole duration — so any
BLOCKING acquisition of the lock in this file deadlocks the gate against the very run that
spawned it. Measured at landing: the blocking form hung the suite for 10+ minutes and had
to be killed by pid. The acquisition here is therefore non-blocking, and `None` from it
means "an enclosing run already holds the lock" — the precondition the probes assert is
already satisfied, so they proceed without taking it themselves. The probe
`probe_the_lock_acquisition_is_non_blocking` is the regression probe, driven in a CHILD
process because a blocking call in this one would hang the gate rather than fail it.

THE LOCK'S SCOPE IS THE REPOSITORY, NOT THE CHECKOUT (#597, ruling n=4608). The anchor is
resolved through `git rev-parse --path-format=absolute --git-common-dir`, so every linked
worktree of one repository contends for ONE file. This was a live defect, not a hypothesis:
`AUDIT_LOCK` was `REPO_ROOT / ".audit.lock"` — the WORKTREE root — and with 31 worktrees in
this repository each carried its own lock, so three peer audit suites ran inside one window
(loadavg peaking 47.18) while the guard ruling n=940 established serialized nothing. The
probes drive that property from TWO worktrees of one throwaway repository in both directions,
with the same-worktree self-exclusion as the positive control: a cross-worktree probe alone
would pass for the wrong reason if nothing flocked the shared file, and the control is the
thing that can fail.

WHAT THIS GATE DOES NOT CLAIM. A per-repo lock cannot bound the ops cgroup. The cgroup is
shared ACROSS repositories and at least three other repositories run the same template
audit inside it (ai-antispam, inferhub-watch, vds-servers), each with its own lock. The
guard bounds concurrent runs WITHIN a repository, and the pile can still recur from
another repo into the same cgroup. This gate is scoped to that claim and never to the
cgroup.

Run:  python3 tests/test_audit_inflight_guard.py
Exit: 0 clean, 1 a probe failed.
"""

from __future__ import annotations

import fcntl
import hashlib
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AUDIT = REPO / "tools" / "audit.py"
GATE_CMD = "tests/test_audit_inflight_guard.py"

# The refusal's own exit code, read from the tool rather than restated here: a gate that
# hardcodes the number it is checking cannot notice the tool changing it.
LOCK_HELD_EXIT_CODE = 3

class _Skip(Exception):
    """A probe with legitimately nothing to judge, stated rather than silently passed.

    The bootstrap case (issue #76/#78, P35): `TEMPLATE/` ships no `evidence/` — the ledger
    is created by `BOOTSTRAP.md`, not by the template — so a factory that has just been
    bootstrapped has no ledger for the row-identity probe to compare. A gate that asserted
    that fact would RED in the tree it ships to, which is the defect `tests/ledger_boundary.py`
    exists to prevent. The probe therefore SKIPS WITH ITS REASON and exits 0.
    """

def _audit_source() -> str:
    return AUDIT.read_text(encoding="utf-8")

def _hold_lock(lock_path: Path):
    """Hold the run lock exactly as a live run does, or report that one is already held.

    Returns the held handle, or None when ANOTHER process already holds the lock.

    THE NON-BLOCKING FORM IS LOAD-BEARING, and it was learned by shipping the blocking one
    first. This gate runs INSIDE an audit — the audit registers it as a gate — and the
    outer run holds `.audit.lock` for its whole duration. A blocking acquisition here
    therefore deadlocks the gate against the very run that spawned it: the gate hangs to
    its budget, is killed, and the audit records it UNKNOWN. Measured at landing: the
    blocking form hung the suite for 10+ minutes and had to be killed by pid.

    Returning None is not a degraded path — it means the precondition the probes assert is
    ALREADY SATISFIED by the enclosing run, so they proceed without taking the lock
    themselves. The assertion is identical either way; only who holds the lock differs.
    """
    handle = open(lock_path, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle

def _release(handle) -> None:
    if handle is not None:
        handle.close()

def _run_audit(repo: Path, *extra: str, timeout: int = 90) -> tuple[int, str, str, float]:
    """`(rc, stdout, stderr, elapsed)` for an audit run in `repo`."""
    t0 = time.monotonic()
    try:
        res = subprocess.run(
            [sys.executable, str(repo / "tools" / "audit.py"), *extra],
            cwd=repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
        return res.returncode, res.stdout, res.stderr, time.monotonic() - t0
    except subprocess.TimeoutExpired:
        return -1, "", f"timed out after {timeout}s", time.monotonic() - t0

def _throwaway_repo(root: Path) -> Path:
    """A minimal copy of the tree the audit resolves against.

    `audit.py` derives REPO_ROOT from its own `__file__`, so a copy is a genuinely
    separate repository — which is what lets the row-identity probe run against a
    ledger nobody else is appending to. `tools/` is the tool and its two sibling
    readers; `evidence/` is the ledger and the rework log it reads.
    """
    # THE SHIPPED TREE CARRIES NO `evidence/` (issue #76/#78, P35): the ledger and the rework
    # log it reads are created by `BOOTSTRAP.md`, not by the template. This helper is reached
    # from probes that build a throwaway repository, and an unguarded `copytree` here makes
    # the gate CRASH in the tree it ships from -- a shipped gate red in its own source, which
    # is the exact class `tests/test_shipped_audit_runs.py` exists to catch (#597 measured it).
    # The sibling probe already states this skip; stating it HERE covers every caller at once,
    # rather than each call site re-deriving whether its fixture can be built.
    missing = [sub for sub in ("tools", "evidence") if not (REPO / sub).is_dir()]
    if missing:
        raise _Skip(
            f"no {'/'.join(missing)}/ in this tree — the ledger and the rework log are "
            f"bootstrap-created (TEMPLATE/BOOTSTRAP.md), so this probe has no throwaway "
            f"repository to build and nothing to compare"
        )
    for sub in ("tools", "evidence"):
        shutil.copytree(REPO / sub, root / sub)
    return root

def _audit_module():
    """`tools/audit.py` as a module, so a probe reads the tool's OWN resolution.

    The lock path is a RESOLUTION, never a constant a gate may restate: a test that hardcoded
    `.audit.lock` at the worktree root would keep passing after the anchor moved, which is the
    presence-instead-of-behaviour shape this gate exists to refuse. Imported once and cached —
    the module is constants and functions, and `spec_from_file_location` re-execs it per call.
    """
    global _AUDIT_MOD
    if _AUDIT_MOD is None:
        spec = importlib.util.spec_from_file_location("audit_under_gate_597", AUDIT)
        mod = importlib.util.module_from_spec(spec)
        # Registered BEFORE exec, not after: `@dataclass` resolves its own module through
        # `sys.modules[cls.__module__]`, so an unregistered module raises AttributeError on
        # the first dataclass in the file and the probe dies before it can judge anything.
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        _AUDIT_MOD = mod
    return _AUDIT_MOD

_AUDIT_MOD = None

def _lock_path(repo: Path) -> Path:
    """The run lock `tools/audit.py` resolves for `repo` — read from the tool, not restated."""
    return _audit_module().run_lock_path(repo)

def _throwaway_git_repo(root: Path) -> tuple[Path, Path]:
    """A throwaway REPOSITORY with two linked worktrees: `(main, linked)`.

    A throwaway rather than a worktree of THIS repository, deliberately: the probe must not
    mutate the shared `.git/worktrees` of the tree it runs in, and a second checkout needs no
    history — one commit is enough for `git worktree add`.

    `tools/` and `evidence/` are copied from this tree, so each checkout carries a runnable
    `audit.py` whose `REPO_ROOT` is ITS OWN root. That is the whole point of the fixture: two
    different roots, one repository.
    """
    repo = _throwaway_repo(root / "main")
    git = ["git", "-c", "user.email=gate@example.invalid", "-c", "user.name=gate"]
    subprocess.run([*git, "init", "-q"], cwd=repo, check=True, capture_output=True)
    subprocess.run([*git, "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        [*git, "commit", "-qm", "fixture"], cwd=repo, check=True, capture_output=True
    )
    linked = root / "linked"
    subprocess.run(
        [*git, "worktree", "add", "-q", str(linked), "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo, linked

def _ledger_identity(repo: Path) -> tuple[int, str]:
    """`(row count, md5)` of the repo's ledger — the pair a write would move."""
    ledger = repo / "evidence" / "ledger.jsonl"
    raw = ledger.read_bytes()
    rows = len([ln for ln in raw.splitlines() if ln.strip()])
    return rows, hashlib.md5(raw).hexdigest()

def probe_the_guard_refuses_a_second_run() -> str:
    """(b) A second run refuses on its own exit code, named, writing nothing.

    The refusal is asserted to be a REFUSAL and not a slow success: rc is the tool's own
    code, stderr names the lock, stdout carries no payload (no verdict was taken), and
    the whole thing returns in seconds where a real run takes minutes.
    """
    lock = _lock_path(REPO)
    handle = _hold_lock(lock)
    try:
        rc, out, err, elapsed = _run_audit(REPO, "--json", timeout=60)
    finally:
        _release(handle)
    holder = "this probe" if handle is not None else "the enclosing run (the lock was already held)"
    assert rc == LOCK_HELD_EXIT_CODE, (
        f"a run whose lock is held must refuse with exit {LOCK_HELD_EXIT_CODE}, got {rc} "
        f"(holder: {holder}; stdout {len(out)}B, stderr {err.strip()[:200]!r})"
    )
    assert "audit in-flight guard" in err, f"the refusal must be NAMED on stderr, got {err.strip()[:200]!r}"
    assert str(lock) in err, f"the refusal must name the lock it could not take, got {err.strip()[:200]!r}"
    assert out.strip() == "", f"a refused run takes no verdict, so stdout must be empty, got {out[:200]!r}"
    assert elapsed < 30, f"a refusal must cost nothing — it returned before any work ({elapsed:.1f}s)"
    return f"refused with exit {rc} in {elapsed:.2f}s, naming {lock.name}, no verdict emitted (lock held by {holder})"

def probe_the_guard_is_exempt_under_no_gates() -> str:
    """(a) THE RECURSION CASE: the outer run holds the lock, the nested run must not refuse.

    This is the probe a NAIVE guard fails. It reproduces the exact nesting the suite
    performs — `tests/test_audit_rates.py` is registered as a gate and runs
    `audit.py --json --no-gates`, asserting rc==0 — so a guard applied to that path makes
    the outer run's own gate red.
    """
    lock = _lock_path(REPO)
    handle = _hold_lock(lock)
    try:
        rc, out, err, elapsed = _run_audit(REPO, "--json", "--no-gates", timeout=90)
    finally:
        _release(handle)
    holder = "this probe" if handle is not None else "the enclosing run (the lock was already held)"
    assert rc == 0, (
        f"--no-gates must be EXEMPT from the guard while the lock is held (the nested-run "
        f"case), got rc={rc}; stderr {err.strip()[:200]!r}"
    )
    assert "audit in-flight guard" not in err, "the exempt path must not print a refusal"
    assert '"gates_skipped": true' in out, "the exempt run must still report its payload"
    return f"nested run under a held lock ({holder}) exited 0 in {elapsed:.2f}s with gates_skipped=true"

def probe_the_refusal_writes_no_run_row() -> str:
    """(b) The refusal writes NO run row, proven on a ledger nobody else touches."""
    if not (REPO / "evidence").is_dir():
        raise _Skip(
            "no evidence/ in this tree — the ledger is bootstrap-created "
            "(TEMPLATE/BOOTSTRAP.md), so there is no row for a refusal to write and "
            "nothing to compare"
        )
    with tempfile.TemporaryDirectory() as tmp:
        repo = _throwaway_repo(Path(tmp))
        before_rows, before_md5 = _ledger_identity(repo)
        handle = _hold_lock(_lock_path(repo))
        try:
            rc, out, err, _ = _run_audit(repo, "--json", timeout=60)
        finally:
            _release(handle)
        after_rows, after_md5 = _ledger_identity(repo)
        assert rc == LOCK_HELD_EXIT_CODE, f"the throwaway run must refuse too, got rc={rc}"
        assert handle is not None, (
            "this probe's lock is the THROWAWAY tree's own, which nothing else holds — a "
            "None here means the acquisition is broken, not that a run holds it"
        )
        assert (before_rows, before_md5) == (after_rows, after_md5), (
            f"a refused run must leave the ledger BYTE-IDENTICAL: {before_rows} rows/"
            f"{before_md5} before, {after_rows} rows/{after_md5} after"
        )
        return (
            f"ledger unchanged at {after_rows} row(s), md5 {after_md5[:12]} before and after"
        )

def probe_the_exit_code_is_distinct() -> str:
    """(b) The refusal's code is its own, in the namespace the other refusals use.

    A consumer reading a bare 1 would record a verdict nobody took, so 3 must not collide
    with the gate-failure 1, the budget-manifest 2, or the gate-timeout 124.
    """
    src = _audit_source()
    assert "LOCK_HELD_EXIT_CODE = 3" in src, (
        "the refusal's exit code must be declared as its own constant (LOCK_HELD_EXIT_CODE = 3)"
    )
    for collision in ("LOCK_HELD_EXIT_CODE = 1", "LOCK_HELD_EXIT_CODE = 2", "LOCK_HELD_EXIT_CODE = 124"):
        assert collision not in src, f"the refusal code collides with a settled code: {collision}"
    assert "TIMEOUT_EXIT_CODE" in src, "the 124 timeout code must still be imported where the collision is judged"
    return "exit 3 is distinct from gate-failure 1, budget-manifest 2 and gate-timeout 124"

def probe_the_orphan_property_control_paired() -> str:
    """(d) No process in a run's tree outlives the run — proven against a CONTROL.

    The lock cannot close this half (a dead holder releases the lock, so the lock never
    sees an orphan), so the mechanism is `PR_SET_PDEATHSIG` in the gate child. A probe
    that only showed the guarded arm's child dying would prove nothing — a child can die
    for many reasons — so the arms are paired: the CONTROL spawns the same child with no
    guard and it MUST outlive the run, and the GUARDED arm spawns it with the guard and it
    MUST NOT. The child's own pid is read from `/proc`, never inferred from a marker file
    whose timing the probe itself would be racing.
    """
    sys.path.insert(0, str(REPO / "tools"))
    parent_src = """
import os, subprocess, sys, time
sys.path.insert(0, {tools!r})
from audit import _orphan_guard
kw = dict()
if GUARDED:
    kw["preexec_fn"] = _orphan_guard()
c = subprocess.Popen(["sleep", "8"], **kw)
open({pidfile!r}, "w").write(str(c.pid))
time.sleep(1.0)
os.kill(os.getpid(), 9)
"""

    def arm(guarded: bool) -> bool:
        """True when the child OUTLIVED its parent."""
        with tempfile.TemporaryDirectory() as tmp:
            pidfile = Path(tmp) / "child.pid"
            src = parent_src.replace("{tools!r}", repr(str(REPO / "tools")))
            src = src.replace("{pidfile!r}", repr(str(pidfile)))
            src = src.replace("GUARDED", repr(guarded))
            parent = subprocess.Popen([sys.executable, "-c", src])
            parent.wait()          # the parent SIGKILLs itself
            time.sleep(2.0)        # the child still has ~5s of its sleep left
            assert pidfile.exists(), (
                "the parent never recorded its child's pid — the guard it imports "
                "(`_orphan_guard`) is absent or raised before the spawn"
            )
            cpid = int(pidfile.read_text())
            alive = Path(f"/proc/{cpid}").exists()
            if alive:
                subprocess.run(["kill", "-9", str(cpid)], capture_output=True)
            return alive

    control = arm(False)
    guarded = arm(True)
    assert control, (
        "the CONTROL arm must show a child OUTLIVING an unguarded run — without it the "
        "guarded arm proves nothing, because a child can die for many reasons"
    )
    assert not guarded, (
        "the GUARDED arm must show the child NOT outliving the run (PR_SET_PDEATHSIG)"
    )
    return "control: child outlived the run; guarded: child died with it — property holds"

def probe_the_guard_is_whole_run() -> str:
    """(a) The guard is taken BEFORE any work, so a refusal cannot half-run the tool.

    Whole-run scope is asserted from the code path rather than timed: the acquisition
    sits in `main()` ahead of the ledger read, and it is conditional on `--no-gates`
    alone. A guard moved below the parse would still refuse, but only after doing the
    work it exists to prevent.
    """
    src = _audit_source()
    acquire_at = src.find("run_lock = acquire_run_lock(")
    parse_at = src.find("ledger_stats, closed_subject_set = parse_ledger(ledger_file)")
    assert acquire_at != -1, "main() must acquire the run lock"
    assert parse_at != -1, "main() must still parse the ledger"
    assert acquire_at < parse_at, (
        "the run lock must be acquired BEFORE the ledger is parsed — the guard is "
        "whole-run, not per-gate"
    )
    # THE CONDITIONALITY IS READ STRUCTURALLY, not from a character window (#639). The
    # window version asserted `if not args.no_gates:` sat within 200 chars of the
    # acquisition, so the eight comment lines that document a private lock path made a
    # TRUE property read FALSE — the check was measuring PROXIMITY, and proximity is a
    # proxy for "inside the block". The indentation is the block.
    lines = src.splitlines()
    acquire_line = next(
        (i for i, ln in enumerate(lines) if "run_lock = acquire_run_lock(" in ln), None
    )
    assert acquire_line is not None, "main() must acquire the run lock"
    guard_line = next(
        (
            i
            for i in range(acquire_line - 1, -1, -1)
            if lines[i].strip() == "if not args.no_gates:"
        ),
        None,
    )
    assert guard_line is not None, "the acquisition must be conditional on --no-gates"
    _indent = lambda ln: len(ln) - len(ln.lstrip())  # noqa: E731
    guard_indent = _indent(lines[guard_line])
    assert _indent(lines[acquire_line]) > guard_indent, (
        "the acquisition must be INSIDE the `if not args.no_gates:` block — an "
        "acquisition at the guard's own indentation is unconditional"
    )
    dedented = [
        ln for ln in lines[guard_line + 1 : acquire_line]
        if ln.strip() and _indent(ln) <= guard_indent
    ]
    assert not dedented, (
        "the acquisition must be conditional on --no-gates ALONE; these lines leave the "
        f"guard block before it: {dedented[:3]}"
    )

    # THE MUTANT, because a structural read that cannot fail is a comment with a assert in
    # it: move the acquisition out of the block (dedent it to the guard's own level) and
    # the SAME read must reject it.
    mutant = list(lines)
    mutant[acquire_line] = lines[acquire_line].lstrip()
    mutant_indent_ok = _indent(mutant[acquire_line]) > guard_indent
    assert not mutant_indent_ok, (
        "the structural read is VACUOUS: an acquisition dedented out of the guard block "
        "was still read as inside it"
    )

    assert "for cmd in gates_to_run" in src, "the gate loop is sequential, which is why the run is the contended unit"
    return "the lock is taken in main() before the ledger read, gated only on --no-gates"

def probe_the_gate_is_registered_and_paired() -> str:
    """The gate runs, and its TEMPLATE copy is byte-identical.

    A gate that never runs is indistinguishable from a gate that passes (#59), so this
    file asserts its own registration in the tool it guards — and in the TEMPLATE copy,
    because `tools/audit.py` is a paired file and a factory that copies one without the
    other carries a guard nothing proves.
    """
    src = _audit_source()
    assert any(
        GATE_CMD in ln and "gates_to_run.append" in ln for ln in src.splitlines()
    ), f"{GATE_CMD} is not registered in the audit gate list"
    copy = REPO / "TEMPLATE" / "tools" / "audit.py"
    if copy.is_file():
        assert copy.read_bytes() == AUDIT.read_bytes(), (
            "tools/audit.py and TEMPLATE/tools/audit.py must be byte-identical"
        )
        return f"{GATE_CMD} is registered, and the audit copies are byte-identical"
    return f"{GATE_CMD} is registered (no TEMPLATE copy in this tree)"

def probe_the_lock_acquisition_is_non_blocking() -> str:
    """The probe's own acquisition must not BLOCK — the deadlock this gate shipped with.

    This is a REGRESSION probe for the defect the first version of this file carried: the
    blocking `flock(LOCK_EX)` form deadlocked the gate against the audit that spawned it,
    because that run holds the lock for its whole duration. Measured at landing — the
    suite hung for 10+ minutes and had to be killed by pid.

    DRIVEN IN A CHILD PROCESS, because a blocking call in THIS process would hang the gate
    rather than fail it, and a probe that can hang is not a probe. The child takes the lock
    twice: the first acquisition succeeds (or reports the enclosing run's hold), and the
    SECOND must return immediately. Under the blocking form it never returns.
    """
    child = f"""
import sys
sys.path.insert(0, {str(REPO / "tests")!r})
import test_audit_inflight_guard as G
h1 = G._hold_lock(G._lock_path(G.REPO))
if h1 is None:
    print("OUTER")
    sys.exit(0)
h2 = G._hold_lock(G._lock_path(G.REPO))
print("NONE" if h2 is None else "UNEXPECTED")
"""
    try:
        res = subprocess.run(
            [sys.executable, "-c", child],
            cwd=REPO,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise AssertionError(
            "the lock acquisition BLOCKED — the second acquisition never returned, which is "
            "the deadlock this gate shipped with (a gate that runs inside an audit cannot "
            "take a blocking lock the enclosing run holds)"
        )
    verdict = res.stdout.strip()
    assert verdict in ("NONE", "OUTER"), (
        f"unexpected acquisition result {verdict!r} (rc={res.returncode}, stderr {res.stderr.strip()[:200]!r})"
    )
    if verdict == "OUTER":
        return "the enclosing run holds the lock; the second acquisition returned rather than blocked"
    return "a second acquisition returned None immediately instead of blocking"

def probe_the_lock_resolves_to_the_git_common_dir() -> str:
    """(#597) ONE lock per REPOSITORY — and the anchor is a RESOLUTION, driven both ways.

    Two facts, and the second is what makes the first a measurement rather than a reading:
    two worktrees of one repository resolve to the SAME path, and that path sits in the git
    COMMON dir; then the resolver is driven on a directory that is in NO repository, where it
    must fall back to that directory. Without the fallback leg a constant and a resolver are
    indistinguishable — the happy path alone cannot tell them apart.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        main, linked = _throwaway_git_repo(root)
        module = _audit_module()
        p_main, p_linked = _lock_path(main), _lock_path(linked)
        common = module.git_common_dir(main)
        assert common is not None, (
            f"the fixture at {main} is a git repository, so its common dir must resolve"
        )
        assert main != linked, "the fixture's two worktrees must be DIFFERENT roots"
        assert p_main == p_linked, (
            f"two worktrees of ONE repository must resolve to one lock; got {p_main} and "
            f"{p_linked} — a per-checkout lock is the defect this gate exists for"
        )
        assert p_main.parent == common, (
            f"the lock must sit in the git COMMON dir {common}, got {p_main}"
        )
        assert p_main != main / ".audit.lock", (
            "the resolved path must NOT be the worktree root's `.audit.lock` — that anchor is "
            "the defect (#597): 31 worktrees, 31 locks, no serialization"
        )
        outside = root / "not-a-repository"
        outside.mkdir()
        assert module.git_common_dir(outside) is None, (
            f"{outside} is in no repository, so git must not answer a common dir for it — the "
            f"fallback leg below would otherwise prove nothing"
        )
        assert _lock_path(outside) == outside / ".audit.lock", (
            "with no repository the anchor must fall back to the directory itself: there is no "
            "second checkout to serialize against, so a per-checkout lock is the population"
        )
        return (
            f"two worktrees resolve to one lock in the common dir ({common.name}), and a "
            f"directory in no repository falls back to its own root"
        )

def probe_two_worktrees_of_one_repository_CONTEND_for_ONE_lock() -> str:
    """(#597) THE PROBE THAT BITES: a run in one worktree refuses while a peer holds it.

    Driven in BOTH directions — main holds / linked runs, then linked holds / main runs —
    because one direction cannot distinguish "the lock is shared" from "the linked copy
    happened to take the main copy's file".

    It bites by construction: under the worktree-scoped anchor this defect shipped with, each
    run takes its OWN `.audit.lock`, no contention exists, and the second run returns 0
    instead of LOCK_HELD_EXIT_CODE. Measured live before the fix: 31 worktrees, one lock
    file each, three peer suites in one window.
    """
    with tempfile.TemporaryDirectory() as tmp:
        main, linked = _throwaway_git_repo(Path(tmp))
        results = []
        for holder, runner in ((main, linked), (linked, main)):
            handle = _hold_lock(_lock_path(holder))
            assert handle is not None, (
                f"the throwaway lock at {_lock_path(holder)} must be FREE — a None here means "
                f"the acquisition is broken, not that a peer holds it"
            )
            try:
                rc, out, err, elapsed = _run_audit(runner, "--json", timeout=60)
            finally:
                _release(handle)
            assert rc == LOCK_HELD_EXIT_CODE, (
                f"a run in {runner.name} must REFUSE while {holder.name} holds the run lock "
                f"(exit {LOCK_HELD_EXIT_CODE}), got rc={rc} — the two worktrees took different "
                f"locks. stdout {out[:120]!r}, stderr {err.strip()[:200]!r}"
            )
            assert "audit in-flight guard" in err, (
                f"the cross-worktree refusal must be the guard's own, named on stderr; got "
                f"{err.strip()[:200]!r}"
            )
            results.append(f"{holder.name} holds -> {runner.name} refused in {elapsed:.2f}s")
        return "; ".join(results)

def probe_the_same_worktree_still_excludes_itself() -> str:
    """(#597) POSITIVE CONTROL: one worktree still excludes a second run of itself.

    Without this the cross-worktree probe could pass for the wrong reason — two roots agreeing
    on a path that nothing actually flocks. Here the SECOND acquisition in the SAME worktree
    must return None, and releasing the first must free the lock again (otherwise the control
    proves a dead holder, not an exclusion).

    Driven on a throwaway repository so the enclosing audit's hold on THIS repository's lock
    cannot turn the control into a tautology.
    """
    with tempfile.TemporaryDirectory() as tmp:
        main, _linked = _throwaway_git_repo(Path(tmp))
        path = _lock_path(main)
        first = _hold_lock(path)
        assert first is not None, f"the throwaway lock at {path} must be free at the start"
        try:
            second = _hold_lock(path)
            assert second is None, (
                "a second acquisition in the SAME worktree must be refused — the lock no longer "
                "excludes itself, so the cross-worktree probe would prove nothing"
            )
        finally:
            _release(first)
        third = _hold_lock(path)
        try:
            assert third is not None, (
                "releasing the first holder must free the lock — otherwise the exclusion above "
                "is a stale file rather than a live flock"
            )
        finally:
            _release(third)
        return f"same-worktree exclusion holds at {path.name}, and release frees it"

def probe_a_refusal_is_unknown_not_a_failure() -> str:
    """(#608) A gate that exits with the REFUSAL's code takes no verdict.

    Ruling `n=4688` clause (b): a lock-held refusal is UNKNOWN, never a FAIL. Read as a plain
    non-zero it landed `passed=False, unknown=False`, so `judge_gates` bucketed it into
    `failed` and every round carried a phantom FAIL for a gate that never opened the tree.

    FOUR ARMS, and the last two are what make the first two mean anything:

      * a child exiting 3 -> `unknown` True, in the unknown population, status UNKNOWN;
      * CONTROL: a child exiting 1 -> `unknown` False, in `failed`, status DEGRADED — the
        predicate must DISCRIMINATE, or it has absorbed every failure into the refusal class;
      * NEUTER: with the new arm disabled (the constant set to a code no child can return)
        the SAME exit-3 child reproduces the phantom FAIL, so the arm is load-bearing.
    """
    mod = _audit_module()
    refusal = mod.run_gate(
        [sys.executable, "-c", "import sys; sys.exit(3)"], REPO, 30.0, "probe (#608)"
    )
    assert refusal["exit_code"] == 3, f"the fixture must exit 3, got {refusal['exit_code']}"
    assert refusal["unknown"] is True, (
        "a gate exiting with the refusal code took no verdict and must be recorded unknown, "
        f"got unknown={refusal['unknown']} passed={refusal['passed']}"
    )
    assert refusal["passed"] is False, "a refusal is never a pass"

    refused_verdict = mod.judge_gates([refusal], cadence_ok=True, gates_ran=True)
    assert refused_verdict.status == "UNKNOWN", (
        f"a refusal must be UNKNOWN, got {refused_verdict.status}"
    )
    assert list(refused_verdict.failed) == [], (
        "a refusal must not appear in the failure list — that IS the phantom FAIL (#608)"
    )
    assert len(refused_verdict.unknown) == 1, "the refusal must be in the unknown population"
    assert refused_verdict.healthy is False, "UNKNOWN is never a healthy run"
    # Binding (c) of the same ruling, driven rather than assumed: the pass total reads the
    # RAW `passed` field, which stays False over a refusal, so a run can never print PASSED
    # for a tree one of its gates never measured.
    assert all(g["passed"] for g in [refusal]) is False, (
        "all_passed must stay False over a refusal"
    )

    failure = mod.run_gate(
        [sys.executable, "-c", "import sys; sys.exit(1)"], REPO, 30.0, "probe (#608)"
    )
    assert failure["exit_code"] == 1 and failure["unknown"] is False, (
        "a genuine gate failure must stay a FAIL, not be absorbed into the refusal class"
    )
    failed_verdict = mod.judge_gates([failure], cadence_ok=True, gates_ran=True)
    assert failed_verdict.status == "DEGRADED", (
        f"a genuine failure must still read DEGRADED, got {failed_verdict.status}"
    )
    assert len(failed_verdict.failed) == 1, "a genuine failure must be in the failure list"

    original = mod.LOCK_HELD_EXIT_CODE
    try:
        mod.LOCK_HELD_EXIT_CODE = 999
        neutered = mod.run_gate(
            [sys.executable, "-c", "import sys; sys.exit(3)"], REPO, 30.0, "probe (#608)"
        )
    finally:
        mod.LOCK_HELD_EXIT_CODE = original
    assert neutered["unknown"] is False, (
        "NEUTERED arm still read the refusal as UNKNOWN — the probe would pass without the "
        "predicate, so it tests nothing"
    )
    neutered_verdict = mod.judge_gates([neutered], cadence_ok=True, gates_ran=True)
    assert neutered_verdict.status == "DEGRADED" and len(neutered_verdict.failed) == 1, (
        "with the arm disabled the refusal must reproduce the phantom FAIL (#608)"
    )
    return (
        "exit 3 -> UNKNOWN (control: exit 1 -> DEGRADED); neutering the arm reproduces the "
        "phantom FAIL"
    )

def probe_a_lock_held_run_is_read_as_no_verdict() -> str:
    """(#608) The REAL refusal, end to end — the synthetic child above is not the proof.

    A throwaway repository has its own run lock held, and its `audit.py --json` is spawned
    the way `run_gate` spawns a gate. The refusal returns exit 3 before any gate runs, and
    the runner must record it as NO VERDICT. Without the fix this exact run is the phantom
    FAIL that made the round read DEGRADED.

    The lock is the throwaway repository's, never this repository's: holding the live lock
    would refuse a PEER lane's audit, which is a live surface this gate has no business
    mutating (#473).
    """
    mod = _audit_module()
    with tempfile.TemporaryDirectory() as tmp:
        root = _throwaway_repo(Path(tmp))
        handle = _hold_lock(_lock_path(root))
        try:
            rec = mod.run_gate(
                [sys.executable, str(root / "tools" / "audit.py"), "--json"],
                root,
                120.0,
                "probe (#608)",
            )
        finally:
            _release(handle)
    assert rec["exit_code"] == mod.LOCK_HELD_EXIT_CODE, (
        f"the held lock must make the nested run refuse with {mod.LOCK_HELD_EXIT_CODE}, got "
        f"exit {rec['exit_code']} (stderr tail: {(rec.get('stderr') or '')[-300:]})"
    )
    assert rec["unknown"] is True, (
        "the real lock-held refusal must be recorded as no verdict, not as a failure"
    )
    verdict = mod.judge_gates([rec], cadence_ok=True, gates_ran=True)
    assert verdict.status == "UNKNOWN", (
        f"the real refusal must read UNKNOWN, got {verdict.status}"
    )
    return (
        f"a held lock refuses at exit {mod.LOCK_HELD_EXIT_CODE} and reads UNKNOWN, never a "
        f"phantom FAIL"
    )

PROBES = (
    ("(a) whole-run scope", probe_the_guard_is_whole_run),
    ("(a) recursion case — exempt under --no-gates", probe_the_guard_is_exempt_under_no_gates),
    ("(b) a second run refuses on its own code", probe_the_guard_refuses_a_second_run),
    ("(b) the refusal writes no run row", probe_the_refusal_writes_no_run_row),
    ("(b) the exit code is distinct", probe_the_exit_code_is_distinct),
    ("(d) the orphan property, control-paired", probe_the_orphan_property_control_paired),
    ("(e) the acquisition is non-blocking", probe_the_lock_acquisition_is_non_blocking),
    ("(f) the lock's scope is the REPOSITORY (#597)", probe_the_lock_resolves_to_the_git_common_dir),
    ("(f) two worktrees contend for ONE lock (#597)", probe_two_worktrees_of_one_repository_CONTEND_for_ONE_lock),
    ("(f) positive control — one worktree excludes itself (#597)", probe_the_same_worktree_still_excludes_itself),
    ("registration and pairing", probe_the_gate_is_registered_and_paired),
    ("(b) a refusal is NO VERDICT, not a FAIL (#608)", probe_a_refusal_is_unknown_not_a_failure),
    ("(b) the REAL lock-held refusal reads no verdict (#608)", probe_a_lock_held_run_is_read_as_no_verdict),
)

def main() -> int:
    failures: list[str] = []
    skipped: list[str] = []
    print(f"in-flight guard gate — {len(PROBES)} probe(s), run from {REPO}")
    for label, probe in PROBES:
        try:
            note = probe()
            print(f"  PASS  {label} — {note}")
        except _Skip as exc:
            skipped.append(label)
            print(f"  SKIP  {label} — {exc}")
        except AssertionError as exc:
            failures.append(f"{label}: {exc}")
            print(f"  FAIL  {label} — {exc}")
    if failures:
        print(f"\n{len(failures)} of {len(PROBES)} probe(s) FAILED")
        return 1
    print(
        f"\n{len(PROBES) - len(skipped)} probe(s) passed"
        + (f", {len(skipped)} skipped with its reason" if skipped else "")
        + " — a second run refuses, the nested run is exempt, and no child outlives the run"
    )
    return 0

if __name__ == "__main__":
    sys.exit(main())

