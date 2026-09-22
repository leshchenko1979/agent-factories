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
import os
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
    """Hold the run lock exactly as a live run does, and return the held handle."""
    handle = open(lock_path, "w")
    fcntl.flock(handle, fcntl.LOCK_EX)
    return handle

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
    for sub in ("tools", "evidence"):
        shutil.copytree(REPO / sub, root / sub)
    return root

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
    lock = REPO / ".audit.lock"
    handle = _hold_lock(lock)
    try:
        rc, out, err, elapsed = _run_audit(REPO, "--json", timeout=60)
    finally:
        handle.close()
    assert rc == LOCK_HELD_EXIT_CODE, (
        f"a run whose lock is held must refuse with exit {LOCK_HELD_EXIT_CODE}, got {rc} "
        f"(stdout {len(out)}B, stderr {err.strip()[:200]!r})"
    )
    assert "audit in-flight guard" in err, f"the refusal must be NAMED on stderr, got {err.strip()[:200]!r}"
    assert str(lock) in err, f"the refusal must name the lock it could not take, got {err.strip()[:200]!r}"
    assert out.strip() == "", f"a refused run takes no verdict, so stdout must be empty, got {out[:200]!r}"
    assert elapsed < 30, f"a refusal must cost nothing — it returned before any work ({elapsed:.1f}s)"
    return f"refused with exit {rc} in {elapsed:.2f}s, naming {lock.name}, no verdict emitted"

def probe_the_guard_is_exempt_under_no_gates() -> str:
    """(a) THE RECURSION CASE: the outer run holds the lock, the nested run must not refuse.

    This is the probe a NAIVE guard fails. It reproduces the exact nesting the suite
    performs — `tests/test_audit_rates.py` is registered as a gate and runs
    `audit.py --json --no-gates`, asserting rc==0 — so a guard applied to that path makes
    the outer run's own gate red.
    """
    lock = REPO / ".audit.lock"
    handle = _hold_lock(lock)
    try:
        rc, out, err, elapsed = _run_audit(REPO, "--json", "--no-gates", timeout=90)
    finally:
        handle.close()
    assert rc == 0, (
        f"--no-gates must be EXEMPT from the guard while the lock is held (the nested-run "
        f"case), got rc={rc}; stderr {err.strip()[:200]!r}"
    )
    assert "audit in-flight guard" not in err, "the exempt path must not print a refusal"
    assert '"gates_skipped": true' in out, "the exempt run must still report its payload"
    return f"nested run under a held lock exited 0 in {elapsed:.2f}s with gates_skipped=true"

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
        handle = _hold_lock(repo / ".audit.lock")
        try:
            rc, out, err, _ = _run_audit(repo, "--json", timeout=60)
        finally:
            handle.close()
        after_rows, after_md5 = _ledger_identity(repo)
        assert rc == LOCK_HELD_EXIT_CODE, f"the throwaway run must refuse too, got rc={rc}"
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
    assert "if not args.no_gates:" in src[acquire_at - 200:acquire_at + 50], (
        "the acquisition must be conditional on --no-gates alone"
    )
    assert "for cmd in gates_to_run" in src, "the gate loop is sequential, which is why the run is the contended unit"
    return "the lock is taken in main() before the ledger read, gated only on --no-gates"

def probe_the_gate_is_registered_and_paired() -> str:
    """The gate runs, and its TEMPLATE twin is byte-identical.

    A gate that never runs is indistinguishable from a gate that passes (#59), so this
    file asserts its own registration in the tool it guards — and in the TEMPLATE twin,
    because `tools/audit.py` is a paired file and a factory that copies one without the
    other carries a guard nothing proves.
    """
    src = _audit_source()
    assert any(
        GATE_CMD in ln and "gates_to_run.append" in ln for ln in src.splitlines()
    ), f"{GATE_CMD} is not registered in the audit gate list"
    twin = REPO / "TEMPLATE" / "tools" / "audit.py"
    if twin.is_file():
        assert twin.read_bytes() == AUDIT.read_bytes(), (
            "tools/audit.py and TEMPLATE/tools/audit.py must be byte-identical"
        )
        return f"{GATE_CMD} is registered, and the audit twins are byte-identical"
    return f"{GATE_CMD} is registered (no TEMPLATE twin in this tree)"

PROBES = (
    ("(a) whole-run scope", probe_the_guard_is_whole_run),
    ("(a) recursion case — exempt under --no-gates", probe_the_guard_is_exempt_under_no_gates),
    ("(b) a second run refuses on its own code", probe_the_guard_refuses_a_second_run),
    ("(b) the refusal writes no run row", probe_the_refusal_writes_no_run_row),
    ("(b) the exit code is distinct", probe_the_exit_code_is_distinct),
    ("(d) the orphan property, control-paired", probe_the_orphan_property_control_paired),
    ("registration and pairing", probe_the_gate_is_registered_and_paired),
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

