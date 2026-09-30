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

# A factory layout first, then this repo's own. Both are named so a tree carrying neither
# can say WHICH two paths it looked in rather than reporting a bare absence.
CANDIDATES = (
    REPO / "tools" / "questions",
    REPO / "TEMPLATE" / "tools" / "questions",
)

# The cap is a DECLARED MULTIPLE of a MEASURED runtime, never a round number (#94, ruling
# n=744), and the runtime is the WORST COMPLETED SAMPLE, not the quietest one (#226 ruling 2:
# `measured_sec` is "a MEASURED runtime", never "a quiet-window runtime", so the base is the
# slow tail the budget must contain). This cap was first derived from a 101.44 s quiet sample
# (2026-09-27), and that sample went stale by 6.27x in two days while the string naming it
# stayed constant -- the "a stated basis nothing re-derives" shape #208 and #230 both found
# one layer down.
#
# RE-DERIVED 2026-09-29 (#230, #226). The measured quantity is this gate's WHOLE COMMAND,
# which is what the audit times (`python3 tests/test_questions.py`, per the registration in
# tools/audit.py), not the selftest it spawns. Completed samples: 635.7 s at load 15.34->19.66
# for the whole command, and 595.58 s at load 10.19->13.80 for the child selftest it spawns.
# Censored runs (390.34 s killed by this cap, and 280.28 s killed by the manifest default) are
# LOWER BOUNDS and are never promoted to a base (#226 ruling 3). The base is therefore the
# worst completed sample, 635.7 s, and 4 x 635.7 + 0.75 = 2543.55 s is this gate's declared
# budget in registry/gates.json. The internal cap sits just below that budget (int(2543.55) =
# 2543, i.e. 0.55 s under it) so a HUNG run is reported HERE, with its reason, rather than
# killed by the harness that would then read it as an unknown -- while a healthy run keeps the
# full 4x headroom above its own worst measurement. A timeout is UNKNOWN, never a pass.
SELFTEST_TIMEOUT_SEC = 2543

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
    try:
        proc = subprocess.run(
            [sys.executable, str(tool), "selftest"],
            capture_output=True, text=True, timeout=SELFTEST_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        print("FAIL: the selftest exceeded %d s -- a timeout is UNKNOWN, never a pass"
              % SELFTEST_TIMEOUT_SEC)
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
