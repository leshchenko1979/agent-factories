#!/usr/bin/env python3
r"""Gate: the questions instrument's selftest is INVOKED, so a green selftest is evidence it ran.

WHY THIS GATE EXISTS (board #182, item 2). `tools/questions` carries its own `selftest`
subcommand, and NOTHING invoked it: no `test_*questions*` existed anywhere, and the tool's
only appearance in `tools/audit.py` was the English word in three comments. A selftest that
no gate runs is a check nobody performs -- a green run proves nothing about a tree, because
nothing ever asks it to run. This gate is that ask.

THE POPULATION IS SYNTHETIC, and that is a requirement rather than an accident. The
instrument's selftest builds a THROWAWAY register under a temp directory and drives every
verb against it; it reads no live register, no fleet manifest and no box-local fixture. A
gate needing live state is a gate that SKIPS everywhere it ships, so this one passes in a
bootstrapped factory exactly as it does here.

WHAT IT PROVES that nothing else can: the instrument still runs END TO END -- every verb, the
register round-trip, the page build and the notify path -- after any change to it. A mutation
that breaks a verb leaves this gate red; without it, the break ships silently. The mutation
control recorded with its registration restores the #183 refusal and watches this gate fail.

WHERE THE TOOL LIVES. This gate runs in two layouts: a FACTORY, where the kit delivers the
instrument to `tools/questions`, and THIS REPO, where it lives at `TEMPLATE/tools/questions`
until delivered. Both are tried, and a tree carrying NEITHER takes the STATED SKIP below --
an absent tool is a stated skip, never a silent pass.

Run:  python3 tests/test_questions.py
Exit: 0 the selftest passed; 1 it did not; 0 with a stated skip when no tool is present.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The gate-budget reader, on the same path-insert convention `tools/audit.py` and the other
# gates use: this file runs as a script (its own dir is already on the path) and is imported
# by the suite, and both must resolve the SAME reader (#94).
sys.path.insert(0, str(REPO / "tools"))
from gate_budget import (  # noqa: E402
    GateBudgetManifestError,
    gates_manifest_path,
    load_gate_budgets,
)

# A factory layout first, then this repo's own. Both are named so a tree carrying neither
# can say WHICH two paths it looked in rather than reporting a bare absence.
CANDIDATES = (
    REPO / "tools" / "questions",
    REPO / "TEMPLATE" / "tools" / "questions",
)

# THE CAP IS DERIVED FROM THE DECLARED BUDGET IT SITS UNDER (#629 rider).
#
# The invariant, as ruled: an internal cap must be DERIVED from the declared budget it sits
# under; where no budget is declared there is NO cap, and the gate says so.
#
# Why the cap exists at all survives that form; a literal does not. Its job is to turn a
# would-be HARNESS kill into a SELF-REPORTED failure that carries a reason -- a run that hangs
# should say so HERE, with its own account, instead of being stopped by the wall above it and
# read as an UNKNOWN nobody explained. That justification only holds while the cap TRACKS the
# wall it guards, and it did not.
#
# MEASURED (#629). The cap was `2543`, justified by a docstring asserting 2543.55 was this
# gate's declared budget (`4 x 635.7 + 0.75`). The manifest was then re-measured to
# `measured_sec 843.17`, `margin_x 4.001`, `budget_sec 3373.43` -- and the literal and its
# docstring stayed behind, so the cap sat 830.43 s BELOW the budget it exists to sit under. A
# run between 2543 s and 3373 s, i.e. INSIDE its own declared allowance, was reported as a
# FAIL here. A literal plus a stated basis that has since moved is the same "a stated basis
# nothing re-derives" shape #208 and #230 both found one layer down.
#
# So the number is READ, never written: `selftest_cap()` resolves this gate's own entry
# through the shared reader and sits CAP_HEADROOM_SEC under it, which keeps the cap's
# justification (the harness never wins the race) while removing the second source for one
# number. The derivation is printed on every run, so the value is checkable rather than
# asserted.
BUDGET_KEY = "tests/test_questions.py"

CAP_HEADROOM_SEC = 1.0
"""How far under the declared wall the internal cap sits.

SMALL, and its size is the whole point: a cap that is a large FRACTION of the budget turns a
slow-but-legitimate run into a FAIL, which is the defect #629 filed. One whole second is
enough to lose the race to the harness reliably, and stays negligible against a 3373 s wall.
"""


def selftest_cap() -> tuple[float | None, str]:
    """This gate's internal cap, DERIVED from its declared budget, and the derivation in words.

    `(None, reason)` when no budget is declared: the invariant says there is then no cap, and
    the gate SAYS SO rather than inventing a number -- an undeclared gate's only real bound is
    the audit's own wall, and a cap invented here would be a second, quieter wall below it.

    Raises `GateBudgetManifestError` for a manifest that exists and cannot be read, on the
    same rule `gate_budget` itself states: an unreadable budget set is indistinguishable from
    no budget set, and defaulting over it would silently re-cap every gate.
    """
    budgets = load_gate_budgets()
    budget_sec, source = budgets.resolve(BUDGET_KEY)
    if source != "declared":
        return None, (
            f"no declared budget for {BUDGET_KEY} — no internal cap, so a hung selftest is "
            f"bounded only by the audit's own wall"
        )
    cap = budget_sec - CAP_HEADROOM_SEC
    return cap, (
        f"{cap:.2f}s, derived from the declared {budget_sec:.2f}s for {BUDGET_KEY}"
    )

# NON-VACUITY FLOOR. The selftest reported 237 checks on 2026-09-27; the floor is well below
# it, so a run that STOPPED EARLY is caught without pinning a count that moves every time a
# probe is added. A clean verdict over a near-empty population must not read as a clean one.
MIN_CHECKS = 50


def main() -> int:
    tool = next((p for p in CANDIDATES if p.is_file()), None)
    if tool is None:
        print("SKIP: no questions instrument in this tree -- looked for %s and %s"
              % (CANDIDATES[0].relative_to(REPO), CANDIDATES[1].relative_to(REPO)))
        return 0

    print("gate: %s selftest" % tool.relative_to(REPO))

    # THE CAP, RESOLVED AND PRINTED (#629 rider). Printed on EVERY run, so the number is
    # checkable against the manifest beside it instead of being taken on trust -- the defect
    # was precisely a stated basis that nothing re-derived.
    try:
        cap_sec, cap_note = selftest_cap()
    except GateBudgetManifestError as exc:
        print("FAIL: the gate-budget manifest exists and cannot be read: %s" % exc)
        print("      an unreadable budget set is indistinguishable from no budget set, and")
        print("      inventing a cap over it would be the silent re-cap this gate removes")
        return 1
    print("  cap: %s" % cap_note)
    print("       manifest: %s" % gates_manifest_path())

    try:
        proc = subprocess.run(
            [sys.executable, str(tool), "selftest"],
            capture_output=True, text=True, timeout=cap_sec,
        )
    except subprocess.TimeoutExpired:
        print("FAIL: the selftest exceeded %.2f s -- a timeout is UNKNOWN, never a pass"
              % cap_sec)
        return 1

    out = (proc.stdout or "") + (proc.stderr or "")
    checks = len(re.findall(r"^  ok\b", out, re.M))
    for line in out.strip().splitlines()[-6:]:
        print(line)

    if proc.returncode != 0:
        print("FAIL: the selftest exited %d" % proc.returncode)
        return 1
    if "all checks passed" not in out:
        print("FAIL: the selftest exited 0 without reporting a clean run")
        return 1
    if checks < MIN_CHECKS:
        print("FAIL: a clean verdict over %d check(s) -- the population is non-empty by "
              "construction, so a near-zero count means the run did not happen"
              % checks)
        return 1

    print("the questions selftest passed: %d check(s) examined" % checks)
    return 0


if __name__ == "__main__":
    sys.exit(main())
