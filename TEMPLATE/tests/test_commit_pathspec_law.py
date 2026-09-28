#!/usr/bin/env python3
"""Gate: the shared-tree commit rule names the invocation, on every card that commits.

Origin (issue #47). A commit written for exactly two paths landed carrying twelve — the
other ten were a peer lane's in-flight work, already sitting in the shared index. The
rule existed on two carriers and the lane obeyed **both**:

- `AGENTS.md.tmpl` — "Never `git add -A` or `git commit -a`. Stage the paths you changed."
- `roles/worker.md` — "Stage only what you changed | No `git add -A`, no `git commit -a`"

Neither forbidden form was run. The lane staged explicit paths — exactly what the law
prescribes — and then ran a bare `git commit`. So the law was **satisfiable in full while
the defect fired**: its sentence governs the *staging* step, while the hazard lives in the
*commit* step. Under P29 that is dead text, and it is why the rule survived every audit
run: prose is not a mechanism, and a rule whose mechanism is misnamed has none.

This gate is the mechanism. It reads the repo law, every role card that commits, and the
factory's own skill file, and fails when one of them states the staging rule without naming
the invocation to use, or does not carry the rule at all. That is the same regression-gate
role `tests/test_hq_delegation.py` plays for the retired HQ-alone doctrine.

The skill surface is the third family because the defect **recurred** on 2026-09-20 — #47's
shape again. The gate read the repo law and the cards and never the skill, so the lane that
commits most often (every ruling, every ledger row, every law change) had neither rule nor
gate, and this gate reported clean while a bare commit swept a peer lane's staged work into
a law commit. A rule that covers every surface except the one that fires is dead text.

It resolves its own tree, so one file serves both: run from this repo it checks
`TEMPLATE/…`; run from `TEMPLATE/` — or from a bootstrapped factory, where the copies sit
at the root — it checks the same law in place. The two copies are byte-identical and
paired by `tests/test_template_sync.py`.

Run:  python3 tests/test_commit_pathspec_law.py
Exit: 0 clean, 1 a committing surface states the rule without naming the invocation.
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# --- surfaces -----------------------------------------------------------------
# Ordered candidates: the template-repo layout first, then the bootstrapped factory
# layout, where the same law sits at the root.
REPO_LAW = ("TEMPLATE/AGENTS.md.tmpl", "AGENTS.md", "AGENTS.md.tmpl")

# Every card whose role commits. `hq.md` is deliberately absent: the HQ card carries no
# commit instruction at all (HQ implements nothing), so there is no rule to state there.
ROLE_CARDS = (
    ("worker", ("TEMPLATE/roles/worker.md", "roles/worker.md")),
    ("triage", ("TEMPLATE/roles/triage.md", "roles/triage.md")),
    ("carrier", ("TEMPLATE/roles/carrier.md", "roles/carrier.md")),
)

# The factory's own law file. It is NOT a role card — it is the surface the lane that commits
# MOST OFTEN reads: every ruling, every ledger row, every law change goes through it. It carried
# no commit rule at all when this defect RECURRED on 2026-09-20 (#47's shape again, a bare commit
# sweeping a peer's staged work into a law commit), because the gate read only the surfaces it was
# written for and never the one the committing lane actually reads. Resolved template-first, then
# by the bootstrapped factory's own skill directory, whose name the gate cannot know.
SKILL_LAW = ("TEMPLATE/SKILL.md.tmpl", "SKILL.md")
SKILL_LAW_GLOB = "skills/*/SKILL.md"

# The invocation to use. A line naming `git commit` must also carry the pathspec form,
# because `git commit -m <msg>` alone is the hazard.
INVOCATION = re.compile(r"git commit[^\n]*--\s*<paths>")

# The prohibition, stated as the reason rather than only as a flag ban. `bare` and
# `git commit` must sit together: "a bare `git commit` takes the entire index".
FORBIDS_BARE = re.compile(r"bare\s+`?git commit`?", re.IGNORECASE)

# The staging rule that is NOT sufficient on its own — the shape the defect slipped past.
STAGING_ONLY = re.compile(r"git add -A|git commit -a", re.IGNORECASE)


def states_pathspec_invocation(text: str) -> bool:
    """True when `text` names the commit invocation together with its paths.

    Factored so synthetic cards can probe it: a rule that has only ever seen good input
    has not been shown to reject bad input.
    """
    return bool(INVOCATION.search(text or ""))


def forbids_bare_commit(text: str) -> bool:
    """True when `text` states that a bare `git commit` is the hazard."""
    return bool(FORBIDS_BARE.search(text or ""))


def _resolve(candidates: tuple[str, ...]) -> Path | None:
    for rel in candidates:
        path = REPO_ROOT / rel
        if path.is_file():
            return path
    return None


def _skill_surfaces() -> list[Path]:
    """Every skill surface present in this tree, in a stable order.

    The template-repo layout first, then the bootstrapped factory's own skill directory.
    That directory's name is not knowable from here, which is why this half globs.

    `SKILL.md.tmpl` AT THIS TREE'S OWN ROOT is also a candidate (#199): from inside the
    shipped tree, the template's law is `SKILL.md.tmpl` one level up from where the repo-root
    spelling looks for it, so resolving only `TEMPLATE/SKILL.md.tmpl` reported "no skill
    surface found" in the tree that carries one.
    """
    found: list[Path] = []
    for rel in SKILL_LAW:
        path = REPO_ROOT / rel
        if path.is_file():
            found.append(path)
    own_law = REPO_ROOT / "SKILL.md.tmpl"
    if own_law.is_file() and own_law not in found:
        found.append(own_law)
    for path in sorted(REPO_ROOT.glob(SKILL_LAW_GLOB)):
        if path.is_file() and path not in found:
            found.append(path)
    return found


def _shown(path: Path) -> str:
    """Path relative to the repo when it is inside it — a probe's file is not."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def probe() -> list[str]:
    """Probe the predicates against both shapes, and report anything that is wrong."""
    failures: list[str] = []

    must_catch = [
        # The exact defect shape: the staging rule stated in full, the commit step ungoverned.
        "- **Never** `git add -A` or `git commit -a`. Stage the paths you changed.",
        "| **Stage only what you changed** | No `git add -A`, no `git commit -a` |",
    ]
    must_pass = [
        "Use `git commit -m <msg> -- <paths>`, or stage and commit in one invocation.",
        "| **Name your paths at the commit** | `git commit -m <msg> -- <paths>` |",
    ]
    for text in must_catch:
        if states_pathspec_invocation(text):
            failures.append(
                f"probe: predicate accepted a staging-only rule as naming the invocation: {text!r}"
            )
    for text in must_pass:
        if not states_pathspec_invocation(text):
            failures.append(
                f"probe: predicate rejected a rule that names the invocation: {text!r}"
            )

    if not forbids_bare_commit("In a shared tree a bare `git commit` takes the entire index."):
        failures.append("probe: prohibition predicate missed the stated bare-commit hazard")
    if forbids_bare_commit("Never run `git add -A`."):
        failures.append("probe: prohibition predicate false-positived on a staging-only rule")

    return failures


def probe_the_skill_surface_bites() -> list[str]:
    """The skill family is only shown to work by an input that makes it fail.

    Non-vacuity is a property of the PROBE, not of the run: a check that has only ever seen
    compliant input is indistinguishable from one that examines nothing (#112, n=657).
    """
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / "SKILL.md"
        bad.write_text(
            "**Never** `git add -A` or `git commit -a`. Stage the paths you changed.\n",
            encoding="utf-8",
        )
        if not check_surface("skill law", bad, needs_prohibition=True):
            failures.append("probe: a staging-only skill surface was reported clean")

        good = Path(tmp) / "COMPLIANT.md"
        good.write_text(
            "In a shared tree a bare `git commit` takes the entire index. "
            "Use `git commit -m <msg> -- <paths>`.\n",
            encoding="utf-8",
        )
        if check_surface("skill law", good, needs_prohibition=True):
            failures.append("probe: a compliant skill surface was reported as a problem")
    return failures


def check_surface(label: str, path: Path, *, needs_prohibition: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    problems: list[str] = []

    if not states_pathspec_invocation(text):
        if STAGING_ONLY.search(text):
            problems.append(
                f"{label} ({_shown(path)}) states the staging rule but "
                "never names the invocation — the shape the defect slipped past"
            )
        else:
            problems.append(
                f"{label} ({_shown(path)}) carries no shared-tree commit rule"
            )

    if needs_prohibition and not forbids_bare_commit(text):
        problems.append(
            f"{label} ({_shown(path)}) does not state that a bare "
            "`git commit` is the hazard"
        )

    return problems


def main() -> int:
    problems = probe()
    problems.extend(probe_the_skill_surface_bites())

    law = _resolve(REPO_LAW)
    if law is None:
        problems.append(f"repo law not found; looked for {', '.join(REPO_LAW)}")
    else:
        problems.extend(check_surface("repo law", law, needs_prohibition=True))

    for role, candidates in ROLE_CARDS:
        card = _resolve(candidates)
        if card is None:
            problems.append(f"{role} card not found; looked for {', '.join(candidates)}")
            continue
        problems.extend(check_surface(f"{role} card", card, needs_prohibition=False))

    # The skill family. Its population is PRINTED on every run, and an empty one fails
    # loudly: a clean verdict over a population nobody enumerated is not a verdict.
    surfaces = _skill_surfaces()
    if not surfaces:
        problems.append(
            "no skill surface found; looked for "
            f"{', '.join(SKILL_LAW)} and {SKILL_LAW_GLOB}"
        )
    for path in surfaces:
        problems.extend(check_surface("skill law", path, needs_prohibition=True))

    if problems:
        for line in problems:
            print(f"  FAIL {line}")
        return 1

    print(
        "commit pathspec law: clean — the repo law, every committing card "
        f"({len(ROLE_CARDS)}), and every skill surface ({len(surfaces)}) name the invocation"
    )
    for path in surfaces:
        print(f"  examined skill surface: {_shown(path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
