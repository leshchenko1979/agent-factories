#!/usr/bin/env python3
"""Gate for the host-wide audit-tree memory ceiling (#600, owner ruling n=4645 shape (2)).

WHAT THIS GATE IS FOR. The ceiling shipped once as a function that NOTHING CALLED: it sat
in `tools/audit.py`, correct and inert, for five hours while every audit tree on the box ran
unbounded. A suite that only tested the function in isolation would have been green the
whole time -- which is exactly how the defect survived. So the FIRST arm here asserts the
WIRING, not the behaviour: `main()` must call it, and the call must precede the run lock.

THE FOUR PROPERTIES, and each has an arm that would fail without it:
  1. WIRED      -- `main()` calls `ensure_scoped(sys.argv[1:])` before `acquire_run_lock`.
  2. REACHABLE  -- `--no-scope` is REGISTERED in the parser; unregistered, argparse exits 2
                   and the escape hatch is unreachable exactly when it is needed.
  3. STATED     -- every path that declines to apply the ceiling prints WHY (#271): "no
                   ceiling was applied" and "the ceiling held" must never be one silence.
  4. APPLIED    -- on the real path the run is re-exec'd under a scope carrying
                   `MemoryMax=<declared>M` and `MemorySwapMax=0`, with the recursion marker
                   exported to the child -- and the MUTANT arm disarms that marker check to
                   prove it is the check, not the fixture, that stops the re-exec looping.

The positive control is a REAL single tree: `audit.py --json --no-gates --no-scope` must run
to completion (rc 0, parseable JSON), so a green here is never a green over nothing running.

Run: `python3 -m pytest tests/test_audit_scope.py -q`
"""
from __future__ import annotations

import ast
import json
import math
import os
import re
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AUDIT_PY = REPO / "tools" / "audit.py"
sys.path.insert(0, str(REPO / "tools"))
import audit  # noqa: E402  (path set up above)


# --------------------------------------------------------------------------- fixtures

def _fake_systemd_run(tmp_path: Path, rc: int = 0) -> tuple[Path, Path]:
    """A stand-in `systemd-run` that RECORDS its argv and exits with `rc`.

    Returns (bin_dir, record_path). Nothing real is ever scoped by this gate, so the
    assertion is about the INVOCATION the code builds, not about systemd's behaviour.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    record = tmp_path / "record.txt"
    script = bin_dir / "systemd-run"
    script.write_text(
        "#!/bin/sh\n"
        f'REC="{record}"\n'
        ': > "$REC"\n'
        'for a in "$@"; do printf "ARG=%s\\n" "$a" >> "$REC"; done\n'
        'printf "MARKER=%s\\n" "${AUDIT_TREE_SCOPED:-unset}" >> "$REC"\n'
        f"exit {rc}\n"
    )
    script.chmod(0o755)
    return bin_dir, record


def _runtime_dir(tmp_path: Path) -> Path:
    """A user-runtime dir that `audit_scope_unavailable_reason()` accepts as scopable."""
    runtime = tmp_path / "runtime"
    (runtime / "systemd" / "private").mkdir(parents=True, exist_ok=True)
    return runtime


def _env(bin_dir: Path | None, runtime: Path | None, marker: bool = False) -> dict[str, str]:
    env = dict(os.environ)
    if bin_dir is None:
        # Keep the real PATH minus any directory that carries systemd-run.
        keep = [p for p in env.get("PATH", "").split(":") if p and not (Path(p) / "systemd-run").exists()]
        env["PATH"] = ":".join(keep)
    else:
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    if runtime is None:
        env.pop("XDG_RUNTIME_DIR", None)
    else:
        env["XDG_RUNTIME_DIR"] = str(runtime)
    if marker:
        env[audit.AUDIT_SCOPE_ENV_MARKER] = "1"
    else:
        env.pop(audit.AUDIT_SCOPE_ENV_MARKER, None)
    return env


def _run_ensure(monkeypatch, env: dict[str, str], argv: list[str]) -> tuple[int | None, str]:
    """Call `ensure_scoped(argv)` under `env`, capturing stderr."""
    import io
    from contextlib import redirect_stderr

    for key in ("PATH", "XDG_RUNTIME_DIR", audit.AUDIT_SCOPE_ENV_MARKER):
        if key in env:
            monkeypatch.setenv(key, env[key])
        else:
            monkeypatch.delenv(key, raising=False)
    buf = io.StringIO()
    with redirect_stderr(buf):
        rc = audit.ensure_scoped(argv)
    return rc, buf.getvalue()


class _EnvPatch:
    """A minimal stand-in for pytest's `monkeypatch`, so `main()` can drive every arm.

    The gate ships in BOTH forms: pytest (which injects the real fixture) and
    `python3 tests/test_audit_scope.py` (which supplies this one). One arm, one body --
    a second copy of the assertions for the script form would be a fixture that drifts.
    """

    def __init__(self) -> None:
        self._saved: dict[str, str | None] = {}

    def setenv(self, key: str, value: str) -> None:
        self._saved.setdefault(key, os.environ.get(key))
        os.environ[key] = value

    def delenv(self, key: str, raising: bool = False) -> None:
        self._saved.setdefault(key, os.environ.get(key))
        os.environ.pop(key, None)

    def undo(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._saved.clear()

@contextmanager
def _sandbox():
    """Yield `(monkeypatch, tmp_path)` for the script form, then restore the environment."""
    import tempfile

    patch = _EnvPatch()
    with tempfile.TemporaryDirectory(prefix="audit-scope-gate-") as tmp:
        try:
            yield patch, Path(tmp)
        finally:
            patch.undo()

# ------------------------------------------------------------------- 1. the wiring arm

def test_ceiling_is_wired_into_main_and_precedes_the_lock():
    """#600's actual defect: the function existed and nothing called it.

    A source-level arm, because the failure mode is an ABSENT call -- no behavioural test
    of `ensure_scoped` can observe that it never ran.
    """
    tree = ast.parse(AUDIT_PY.read_text())
    main_fn = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "main"),
        None,
    )
    assert main_fn is not None, "tools/audit.py has no main()"

    calls: dict[str, int] = {}
    for node in ast.walk(main_fn):
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
            if name in ("ensure_scoped", "acquire_run_lock"):
                calls.setdefault(name, node.lineno)

    assert "ensure_scoped" in calls, (
        "main() never calls ensure_scoped(): the ceiling is dead code and every audit tree "
        "runs unbounded -- the exact #600 defect"
    )
    assert "acquire_run_lock" in calls, "main() no longer calls acquire_run_lock()?"
    assert calls["ensure_scoped"] < calls["acquire_run_lock"], (
        "ensure_scoped() is called AFTER acquire_run_lock(): the scope would then wrap only "
        "what follows the lock, and the tree the lock guards would stay unbounded"
    )


def test_no_scope_flag_is_registered_in_the_parser():
    """An unregistered flag makes argparse exit 2, so the escape hatch must be declared."""
    src = AUDIT_PY.read_text()
    assert '"--no-scope"' in src, "--no-scope is not mentioned at all"
    tree = ast.parse(src)
    registered = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if getattr(fn, "attr", "") != "add_argument":
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and arg.value == "--no-scope":
                registered = True
    assert registered, (
        'argparse never registers "--no-scope": passing it exits 2, so the documented '
        "diagnostic escape from the ceiling is unreachable (#600 gap 2)"
    )


# ------------------------------------------------- 2. stated absence, never a silence

def test_inside_the_scope_this_process_is_the_tree(monkeypatch=None, tmp_path=None):
    """Marker set: this IS the scoped tree, so it must run rather than re-exec."""
    if monkeypatch is None or tmp_path is None:
        with _sandbox() as (monkeypatch, tmp_path):
            return test_inside_the_scope_this_process_is_the_tree(monkeypatch, tmp_path)
    bin_dir, record = _fake_systemd_run(tmp_path)
    rc, err = _run_ensure(monkeypatch, _env(bin_dir, _runtime_dir(tmp_path), marker=True), [])
    assert rc is None, "an already-scoped run must carry on, not return an exit code"
    assert not record.exists(), "an already-scoped run re-exec'd itself: the marker check is dead"
    assert err == "", f"an already-scoped run should be silent, printed: {err!r}"


def test_no_scope_states_the_absence(monkeypatch=None, tmp_path=None):
    """The escape hatch must SAY it is unbounded -- a silent one is the #271 shape."""
    if monkeypatch is None or tmp_path is None:
        with _sandbox() as (monkeypatch, tmp_path):
            return test_no_scope_states_the_absence(monkeypatch, tmp_path)
    bin_dir, record = _fake_systemd_run(tmp_path)
    rc, err = _run_ensure(monkeypatch, _env(bin_dir, _runtime_dir(tmp_path)), ["--no-scope"])
    assert rc is None
    assert not record.exists(), "--no-scope must not invoke systemd-run"
    assert "NOT APPLIED" in err and "--no-scope" in err, f"stated absence missing: {err!r}"
    assert "UNBOUNDED" in err, "the line must name the consequence, not just the flag"


def test_no_gates_is_exempt_and_that_is_principled(monkeypatch=None, tmp_path=None):
    """`--no-gates` forks no gate, so it contributes none of the load the ceiling bounds."""
    if monkeypatch is None or tmp_path is None:
        with _sandbox() as (monkeypatch, tmp_path):
            return test_no_gates_is_exempt_and_that_is_principled(monkeypatch, tmp_path)
    bin_dir, record = _fake_systemd_run(tmp_path)
    rc, err = _run_ensure(monkeypatch, _env(bin_dir, _runtime_dir(tmp_path)), ["--no-gates"])
    assert rc is None
    assert not record.exists(), "--no-gates must not be scoped"


def test_missing_systemd_run_is_stated_with_the_ceiling_it_failed_to_apply(monkeypatch=None, tmp_path=None):
    """#271: an unreadable/unavailable instrument is a stated absence, never a zero."""
    if monkeypatch is None or tmp_path is None:
        with _sandbox() as (monkeypatch, tmp_path):
            return test_missing_systemd_run_is_stated_with_the_ceiling_it_failed_to_apply(monkeypatch, tmp_path)
    rc, err = _run_ensure(monkeypatch, _env(None, _runtime_dir(tmp_path)), [])
    assert rc is None, "an unavailable systemd-run must not stop the audit running"
    assert "NOT APPLIED" in err, f"unavailable instrument was silent: {err!r}"
    assert "systemd-run" in err, f"the reason must name the missing instrument: {err!r}"
    assert str(audit.AUDIT_SCOPE_MEMORY_MAX_MIB) in err, (
        f"the stated absence must name the ceiling that was NOT enforced: {err!r}"
    )


# ------------------------------------------------------ 3. the scope, when it is applied

def test_scope_is_applied_with_the_declared_ceiling(monkeypatch=None, tmp_path=None):
    """The real path: re-exec under a scope carrying the declared caps and the marker."""
    if monkeypatch is None or tmp_path is None:
        with _sandbox() as (monkeypatch, tmp_path):
            return test_scope_is_applied_with_the_declared_ceiling(monkeypatch, tmp_path)
    bin_dir, record = _fake_systemd_run(tmp_path, rc=7)
    rc, err = _run_ensure(
        monkeypatch, _env(bin_dir, _runtime_dir(tmp_path)), ["--json", "--report"]
    )
    assert rc == 7, f"the scope's exit code must be propagated verbatim, got {rc!r}"
    assert record.exists(), "the ceiling was never applied: systemd-run was not invoked"

    lines = record.read_text().splitlines()
    args = [ln.split("=", 1)[1] for ln in lines if ln.startswith("ARG=")]
    marker = [ln.split("=", 1)[1] for ln in lines if ln.startswith("MARKER=")]

    assert "--user" in args, f"scope must be a USER scope: {args}"
    assert "--scope" in args, f"the whole tree must be in one cgroup: {args}"
    assert any(a.startswith("--unit=") for a in args), f"the scope needs a named unit: {args}"
    assert f"MemoryMax={audit.AUDIT_SCOPE_MEMORY_MAX_MIB}M" in args, (
        f"the declared ceiling is not applied: {args}"
    )
    assert f"MemorySwapMax={audit.AUDIT_SCOPE_MEMORY_SWAP_MAX}" in args, (
        f"swap must be capped or the ceiling is unenforceable: {args}"
    )
    # The re-exec target and the caller's own argv travel through unchanged.
    assert str(AUDIT_PY.resolve()) in args, f"the re-exec must target audit.py itself: {args}"
    assert "--json" in args and "--report" in args, f"argv was not passed through: {args}"
    assert marker == ["1"], f"the recursion marker must be exported to the child: {marker}"
    assert "audit scope: ceiling" in err, f"the applied ceiling must state its basis: {err!r}"
    assert audit.AUDIT_SCOPE_MEMORY_MAX_BASIS in err, "the basis must be printed on every run"


def test_mutant_disarming_the_marker_guard_reexecs(monkeypatch=None, tmp_path=None):
    """MUTANT ARM: neuter the recursion guard and the re-exec must actually happen.

    Without this arm the "already scoped is silent" assertion above could pass because the
    function is inert, not because the guard works. Here the guard is disarmed by renaming
    the marker it looks for, and the same input that was silent must now invoke the scope.
    """
    if monkeypatch is None or tmp_path is None:
        with _sandbox() as (monkeypatch, tmp_path):
            return test_mutant_disarming_the_marker_guard_reexecs(monkeypatch, tmp_path)
    bin_dir, record = _fake_systemd_run(tmp_path)
    env = _env(bin_dir, _runtime_dir(tmp_path), marker=True)

    original = audit.AUDIT_SCOPE_ENV_MARKER
    try:
        audit.AUDIT_SCOPE_ENV_MARKER = "AUDIT_SCOPE_MARKER_RENAMED_BY_MUTANT"
        rc, _ = _run_ensure(monkeypatch, env, [])
    finally:
        audit.AUDIT_SCOPE_ENV_MARKER = original

    assert rc is not None, "with the marker guard disarmed the run must be carried by a scope"
    assert record.exists(), (
        "the mutant did not change behaviour: the marker check is not what prevents the "
        "re-exec, so the silence in the arm above proves nothing"
    )


# --------------------------------------------------- 3b. the number and its basis agree

def _module_constant(name: str):
    """The literal value of a module-level assignment in `tools/audit.py`, read via AST."""
    tree = ast.parse(AUDIT_PY.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"{name} is not a module-level constant in {AUDIT_PY}")


def test_the_ceiling_is_derived_from_the_peak_its_own_basis_cites():
    """THE ARM THAT WOULD HAVE CAUGHT THE SHIPPED DEFECT. `3072` sat beside a basis claiming a
    measured peak while the measurement's only artifact read `PEAK_MIB=0 RC=1` -- a round number
    wearing a receipt. So the value must be RECOMPUTABLE from the basis it states: 2x the cited
    peak, rounded up to the next 256 MiB. A basis that cites no peak, or a value that does not
    follow from the one it cites, fails here rather than at the next OOM.
    """
    mib = _module_constant("AUDIT_SCOPE_MEMORY_MAX_MIB")
    basis = _module_constant("AUDIT_SCOPE_MEMORY_MAX_BASIS")

    peak = re.search(r"peak ([\d.]+) MiB", basis)
    assert peak, f"the basis cites no measured peak, so the ceiling is unbacked: {basis[:160]}"
    peak_mib = float(peak.group(1))

    expected = math.ceil((peak_mib * 2) / 256) * 256
    assert mib == expected, (
        f"the ceiling does not follow from its own basis: basis cites a {peak_mib} MiB peak, "
        f"so 2x rounded up to 256 is {expected} MiB, but the constant is {mib} MiB"
    )
    assert mib > peak_mib, (
        f"the ceiling {mib} MiB is BELOW the {peak_mib} MiB peak it cites: that turns a "
        "measurement duty into a reliable OOM"
    )
    for token in ("systemd-run", "MemoryPeak"):
        assert token in basis, f"the basis does not name {token}, so the figure cannot be reproduced"
    assert re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", basis), (
        "the basis carries no read instant, so a reader cannot tell when it was measured"
    )


# ------------------------------------------------------------ 4. the positive control

def test_single_tree_still_runs_to_completion():
    """POSITIVE CONTROL: a real single audit tree completes, so green is never a green over
    nothing. `--no-scope` keeps the gate hermetic; `--no-gates` keeps it fast and fork-free.
    """
    # The marker must be CLEARED for the child: under the shipped audit this gate runs INSIDE
    # an applied scope, so an inherited AUDIT_TREE_SCOPED=1 makes the child read as
    # already-inside and print nothing -- the control would then red on its own inheritance
    # rather than on the code under test (measured: `1 failed, 9 passed` in TEMPLATE only).
    env = dict(os.environ)
    env.pop(audit.AUDIT_SCOPE_ENV_MARKER, None)
    proc = subprocess.run(
        [sys.executable, str(AUDIT_PY), "--json", "--no-gates", "--no-scope"],
        cwd=str(REPO), capture_output=True, text=True, timeout=600, env=env,
    )
    assert proc.returncode == 0, (
        f"a single audit tree did not complete: rc={proc.returncode}\n{proc.stderr[-2000:]}"
    )
    payload = json.loads(proc.stdout)
    assert payload.get("date"), "the run produced no dated payload"
    assert "audit scope: NOT APPLIED (--no-scope)" in proc.stderr, (
        "the control run must state that it ran unbounded, or its own green is silent"
    )

# ------------------------------------------- 6. the two-tree arm (criterion 2's other half)

def _fake_systemd_run_shared(tmp_path: Path) -> tuple[Path, Path]:
    """A stand-in `systemd-run` that APPENDS one block per invocation, tagged with its caller.

    `$PPID` is the audit tree that invoked it -- that is the identity the unit name must be
    derived from, so the record has to carry it or the assertion below is unfalsifiable.
    """
    bin_dir = tmp_path / "bin-two"
    bin_dir.mkdir(parents=True, exist_ok=True)
    record = tmp_path / "record-two.txt"
    script = bin_dir / "systemd-run"
    script.write_text(
        "#!/bin/sh\n"
        f'REC="{record}"\n'
        'printf "CHILD=%s\\n" "$PPID" >> "$REC"\n'
        'for a in "$@"; do printf "ARG=%s\\n" "$a" >> "$REC"; done\n'
        "exit 0\n"
    )
    script.chmod(0o755)
    return bin_dir, record

def _scope_blocks(record: Path) -> list[dict[str, object]]:
    """Parse the record into one block per invocation: {'child': pid, 'args': [...]}."""
    blocks: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for line in record.read_text().splitlines():
        if line.startswith("CHILD="):
            current = {"child": line.split("=", 1)[1], "args": []}
            blocks.append(current)
        elif line.startswith("ARG=") and current is not None:
            current["args"].append(line.split("=", 1)[1])  # type: ignore[union-attr]
    return blocks

def _unit_of(block: dict[str, object]) -> str | None:
    for arg in block["args"]:  # type: ignore[union-attr]
        if arg.startswith("--unit="):
            return arg.split("=", 1)[1]
    return None

def _assert_two_trees_get_two_units(blocks: list[dict[str, object]]) -> None:
    """The assertion itself, factored out so the MUTANT arm can watch it bite."""
    assert len(blocks) == 2, f"expected two scoped trees, saw {len(blocks)}"
    units = [_unit_of(block) for block in blocks]
    assert all(units), f"a tree was scoped with no unit name: {units}"
    assert units[0] != units[1], (
        "two concurrent trees shared ONE unit name -- that is a shared host lock, and "
        f"shape (1) was REFUSED by the ruling: {units}"
    )
    for block, unit in zip(blocks, units):
        assert unit is not None
        parts = unit.split("-")
        assert parts[:2] == ["audit", "tree"] and len(parts) == 4, f"unit shape: {unit}"
        assert parts[2] == str(block["child"]), (
            f"unit {unit} is not derived from its own tree's pid {block['child']}"
        )
        assert any(str(a).startswith("MemoryMax=") for a in block["args"]), (  # type: ignore[union-attr]
            f"a tree was scoped without the ceiling: {block['args']}"
        )

def _spawn_tree(tmp_path: Path, bin_dir: Path, runtime: Path, tag: str,
                module: str = "audit", module_dir: Path | None = None):
    """Start one audit tree as its OWN process, so the pid it names is genuinely its own."""
    harness = tmp_path / f"tree_{tag}.py"
    # `tools/` carries the module's own siblings (field_predicate &c.), so a neutered COPY
    # living in a scratch dir still imports cleanly; the copy's own dir wins for `import`.
    harness.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(REPO / 'tools')!r})\n"
        f"sys.path.insert(0, {str(module_dir or (REPO / 'tools'))!r})\n"
        f"import {module} as audit\n"
        "sys.exit(audit.ensure_scoped(['--json']))\n"
    )
    return subprocess.run(
        [sys.executable, str(harness)],
        env=_env(bin_dir, runtime), capture_output=True, text=True, timeout=300,
    )

def test_two_trees_each_get_their_own_scope(monkeypatch=None, tmp_path=None):
    """CRITERION 2: two concurrent trees are BOTH scoped, under DISTINCT unit names.

    Shape (1) -- one host-wide lock that refuses the second tree -- was refused by the
    ruling, so a refusal here is a REGRESSION, not a safety property. Two separate
    processes, therefore two distinct `audit-tree-<pid>-<ts>` scopes, neither blocked.
    """
    if monkeypatch is None or tmp_path is None:
        with _sandbox() as (monkeypatch, tmp_path):
            return test_two_trees_each_get_their_own_scope(monkeypatch, tmp_path)
    bin_dir, record = _fake_systemd_run_shared(tmp_path)
    runtime = _runtime_dir(tmp_path)
    for tag in ("a", "b"):
        proc = _spawn_tree(tmp_path, bin_dir, runtime, tag)
        assert proc.returncode == 0, (
            f"tree {tag} was REFUSED rather than scoped: rc={proc.returncode}\n{proc.stderr}"
        )
        assert "NOT APPLIED" not in proc.stderr, (
            f"tree {tag} ran unbounded and said so: {proc.stderr}"
        )
    _assert_two_trees_get_two_units(_scope_blocks(record))

def test_mutant_a_fixed_unit_name_reddens_the_two_tree_arm(monkeypatch=None, tmp_path=None):
    """MUTANT ARM: neuter the unit derivation and the arm above must stop being green.

    Without this, "two units differ" could hold for a reason unrelated to the code -- e.g.
    a fixture that fabricates the difference. Here the CODE is copied and its unit name
    pinned to a constant, and the same assertion must now fail.
    """
    if monkeypatch is None or tmp_path is None:
        with _sandbox() as (monkeypatch, tmp_path):
            return test_mutant_a_fixed_unit_name_reddens_the_two_tree_arm(monkeypatch, tmp_path)
    bin_dir, record = _fake_systemd_run_shared(tmp_path)
    runtime = _runtime_dir(tmp_path)

    source = AUDIT_PY.read_text()
    pattern = r'unit = f"audit-tree-\{os\.getpid\(\)\}-\{int\(time\.time\(\)\)\}"'
    neutered = re.sub(pattern, 'unit = "audit-tree-0-0"', source)
    assert neutered != source, (
        "the neuter did not apply -- the unit-derivation line moved, so this mutant is inert"
    )
    module_dir = tmp_path / "mutant"
    module_dir.mkdir(parents=True, exist_ok=True)
    (module_dir / "audit_fixed_unit.py").write_text(neutered)

    for tag in ("a", "b"):
        proc = _spawn_tree(tmp_path, bin_dir, runtime, f"mut_{tag}",
                           module="audit_fixed_unit", module_dir=module_dir)
        assert proc.returncode == 0, f"mutant tree {tag}: rc={proc.returncode}\n{proc.stderr}"

    try:
        _assert_two_trees_get_two_units(_scope_blocks(record))
    except AssertionError as exc:
        assert "shared ONE unit name" in str(exc) or "not derived from its own tree" in str(exc), (
            f"the arm reddened for the wrong reason: {exc}"
        )
    else:
        raise AssertionError(
            "the two-tree arm stayed GREEN with a fixed unit name -- it does not bite"
        )


def main() -> int:
    """Run every arm with no arguments, so `python3 tests/test_audit_scope.py` bites."""
    checks = [value for name, value in sorted(globals().items())
              if name.startswith("test_") and callable(value)]
    failures: list[str] = []
    for check in checks:
        try:
            check()
        except AssertionError as exc:
            failures.append(f"{check.__name__}: {exc}")
            print(f"  FAIL  {check.__name__} -- {exc}")
        else:
            print(f"  PASS  {check.__name__}")
    print()
    if failures:
        print(f"audit-scope gate FAILED: {len(failures)} check(s)")
        return 1
    print(f"audit-scope gate passed: {len(checks)} check(s)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
