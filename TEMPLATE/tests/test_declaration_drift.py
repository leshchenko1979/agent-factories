#!/usr/bin/env python3
"""Gate: every surface the instrument docs declare is mirrored in the law table (#313).

WHY THIS GATE EXISTS. Two COMMITTED homes declare which surfaces this factory owns:
home **A**, the law table in `skills/meta-factory/SKILL.md` (the table whose header
carries `Surface` and `Authoritative writer`), and home **B**, the tables whose header's
first cell is `surface` across `docs/instruments/*.md`. `tests/test_single_writer.py`
parses **A only**, so a surface declared in **B** and never mirrored into **A** reads
clean. That is the `#311` instance: the publish receipt was declared in
`docs/instruments/pacemaker.md` and absent from the law table, and because the receipt
is gitignored the existing gate was box-local and CI-blind in exactly the direction
that hides it. Both homes here are committed, so this guard is CI-visible where the
gate it repairs is not.

THE PREDICATE IS ONE-DIRECTIONAL: `B ⊆ A`. Every token the instrument docs declare
must also appear in the law table. The reverse is NOT asserted and that is a deliberate
scope sentence: home A is the authoritative table and lawfully declares surfaces no
single instrument doc enumerates (`registry/topics/<slug>.json`,
`docs/harness-bindings.json`). Asserting `A ⊆ B` would fire on the law table's own
completeness.

THE DECLARATION GRAMMAR. A declaration enters the population iff all four hold: it
sits in a markdown table row whose header's first cell is exactly `surface`
(case-insensitive, backticks stripped); the row's first cell is a backticked token;
after normalisation it is repo-relative (no `<` placeholder, does not begin with `/`);
and after normalisation it is path-shaped. Normalisation strips backticks, splits on
` and ` (home A joins two surfaces in one cell), and splits on ` → ` keeping the left
side (home B writes `` `registry/fleet.json` → `job_prefixes` ``). The form codifies
what every shipped doc already does rather than inventing a second convention, so a
member factory adopts it by shipping the docs the kit already ships.

THE NO-INSTRUMENT-DOCS CASE. An empty population exits 0 and PRINTS
`examined 0 declaration(s) in 0 instrument doc(s)`, so an empty run is
distinguishable from a clean one — a silent green on an empty population is the
defect class `#116` already names. If home A cannot be located the guard REFUSES
with a named reason, never a green: the same shape `duty_receipt_leg` uses for an
undeclared boundary.

WHAT IT DOES NOT DO. It does not read a gitignored artifact or require one to exist;
it does not parse prose (a declaration outside the grammar is outside the population,
not a failure); it does not judge the *writer* column, which is `test_single_writer.py`'s
job; and it imposes no layout on a member's docs beyond the header cell above.

RECURSION. The arms spawn this file as a child. The depth travels in the environment
(`DRIFT_DEPTH`), and a process at depth >= 1 judges without spawning, so the guard
cannot re-arm itself whatever its arguments say. An argv flag is not a guard: it was
dropped once and forked the box 152 ways (05:57Z 2026-10-16). `--judge-only` is kept as
documentation of the child's role; the counter is what enforces it.

Run:  python3 tests/test_declaration_drift.py [--repo PATH]
Exit: 0 clean, 1 drift or refusal.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The recursion cap, and it is STRUCTURAL — carried in the ENVIRONMENT, never inferred
# from argv. The arms spawn this file as a child; a child that re-entered the arms would
# spawn another child, and the guard forked until the box starved (152 processes, load
# 8.6, 05:57Z 2026-10-16). An argv flag cannot prevent that: a single dropped or
# reordered argument re-arms it box-wide, and the hazard is a live file. So the depth
# travels in `DRIFT_DEPTH`, the parent runs the arms exactly once, and every process at
# depth >= MAX_DEPTH judges without spawning — whatever its arguments say.
DEPTH_ENV = "DRIFT_DEPTH"
MAX_DEPTH = 1

# Home A, in the order this depth prefers it: the meta-factory's own law first, then a
# member factory's law, then the template's. The root depth finds the first; the shipped
# depth (`cwd=TEMPLATE`) finds the third — the template carries the law as `.tmpl`.
LAW_CANDIDATES = ("skills/meta-factory/SKILL.md", "SKILL.md", "SKILL.md.tmpl")

INSTRUMENT_DIR = "docs/instruments"

# Rule 4: path characters only — no spaces, no parentheses.
PATH_SHAPED = re.compile(r"^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.*-]+)*$")

_SPLIT_AND = re.compile(r"\s+and\s+", re.IGNORECASE)
_SPLIT_ARROW = re.compile(r"\s*→\s*")
_SEPARATOR = re.compile(r"^:?-+:?$")


class DeclarationUnavailable(Exception):
    """Home A cannot be located — refuse with a named reason, never a green."""


_failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}{(' — ' + detail) if detail else ''}")
    if not ok:
        _failures.append(name)


def _cells(line: str) -> list[str]:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return [cell.strip() for cell in text.split("|")]


def _tables(text: str):
    """Yield (header_cells, data_rows) for every markdown table in `text`."""
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        if not lines[index].lstrip().startswith("|"):
            index += 1
            continue
        start = index
        while index < len(lines) and lines[index].lstrip().startswith("|"):
            index += 1
        block = lines[start:index]
        if len(block) < 2:
            continue
        separator = _cells(block[1])
        if not separator or not all(_SEPARATOR.match(cell) for cell in separator):
            continue
        yield _cells(block[0]), [_cells(row) for row in block[2:]]


def _header_is_surface_table(header: list[str]) -> bool:
    """Rule 1: the header's FIRST cell is exactly `surface`."""
    if not header:
        return False
    return header[0].replace("`", "").strip().lower() == "surface"


def _header_is_law_table(header: list[str]) -> bool:
    """Home A's discriminator: the header carries `Surface` and `Authoritative writer`."""
    cells = [cell.replace("`", "").strip().lower() for cell in header]
    return "surface" in cells and any("authoritative writer" in cell for cell in cells)


def _normalise(cell: str) -> list[str]:
    """Strip backticks; split on ` and `; split on ` → ` keeping the left side."""
    tokens: list[str] = []
    for part in _SPLIT_AND.split(cell.replace("`", "").strip()):
        left = _SPLIT_ARROW.split(part)[0].strip()
        if left:
            tokens.append(left)
    return tokens


def _admits(token: str) -> bool:
    """Rules 3 and 4: repo-relative and path-shaped."""
    if "<" in token or token.startswith("/"):
        return False
    return bool(PATH_SHAPED.match(token))


def locate_law(repo: Path) -> Path:
    for relative in LAW_CANDIDATES:
        candidate = repo / relative
        if candidate.is_file():
            return candidate
    raise DeclarationUnavailable(
        "home A (the law table) is not locatable: none of "
        + ", ".join(f"`{name}`" for name in LAW_CANDIDATES)
        + f" exists under {repo}"
    )


def law_tokens(repo: Path) -> tuple[set[str], Path]:
    """The normalised first-cell tokens of home A's law table."""
    path = locate_law(repo)
    tokens: set[str] = set()
    found = False
    for header, rows in _tables(path.read_text(encoding="utf-8", errors="replace")):
        if not _header_is_law_table(header):
            continue
        found = True
        for row in rows:
            if row:
                tokens.update(_normalise(row[0]))
    if not found:
        raise DeclarationUnavailable(
            f"home A was located at `{path.relative_to(repo).as_posix()}` but carries no table "
            "whose header names both `Surface` and `Authoritative writer`"
        )
    return tokens, path


def instrument_declarations(repo: Path) -> tuple[list[tuple[str, str]], int]:
    """Home B's admitted declarations as (token, declaring doc), plus the docs examined."""
    declarations: list[tuple[str, str]] = []
    examined = 0
    directory = repo / INSTRUMENT_DIR
    for doc in sorted(directory.glob("*.md")) if directory.is_dir() else []:
        relative = doc.relative_to(repo).as_posix()
        carries_table = False
        for header, rows in _tables(doc.read_text(encoding="utf-8", errors="replace")):
            if not _header_is_surface_table(header):
                continue
            carries_table = True
            for row in rows:
                if not row or "`" not in row[0]:
                    continue
                for token in _normalise(row[0]):
                    if _admits(token):
                        declarations.append((token, relative))
        if carries_table:
            examined += 1
    return declarations, examined


def run(repo: Path, out=print) -> int:
    """Print the verdict for `repo`; return the exit code."""
    try:
        tokens, law_path = law_tokens(repo)
    except DeclarationUnavailable as exc:
        out(f"declaration-drift: REFUSED — {exc}")
        return 1

    declarations, examined = instrument_declarations(repo)
    out(f"examined {len(declarations)} declaration(s) in {examined} instrument doc(s)")

    law_relative = law_path.relative_to(repo).as_posix()
    missing = sorted({(token, doc) for token, doc in declarations if token not in tokens})
    if missing:
        out(f"declaration-drift: FAILED — declared in `{INSTRUMENT_DIR}/*.md`, absent from `{law_relative}`")
        for token, doc in missing:
            out(f"  {token}  — declared in {doc}, absent from {law_relative}")
        return 1

    out(f"declaration-drift: OK — every declaration in `{INSTRUMENT_DIR}/*.md` is mirrored in `{law_relative}`")
    return 0


# --- the arms -------------------------------------------------------------------

def _fixture(root: Path, *, instruments: dict[str, str] | None, law: str | None) -> Path:
    """Build a hermetic factory: instrument docs and/or a law file."""
    if instruments:
        directory = root / INSTRUMENT_DIR
        directory.mkdir(parents=True, exist_ok=True)
        for name, text in instruments.items():
            (directory / name).write_text(text, encoding="utf-8")
    if law is not None:
        target = root / "skills" / "meta-factory" / "SKILL.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(law, encoding="utf-8")
    return root


_SURFACE_TABLE = (
    "| surface | ships as | owner |\n"
    "|---|---|---|\n"
    "| `{token}` | generated | the kit |\n"
)

_LAW_TABLE = (
    "| Surface | Holds | Authoritative writer | Everyone else |\n"
    "|---|---|---|---|\n"
    "| `evidence/ledger.jsonl` | every transition | `tools/ledger.py append` | read-only |\n"
    "{extra}"
)


def _depth() -> int:
    """The recursion depth of THIS process, read from the environment (#313 incident).

    An unparseable value is treated as TOO DEEP rather than as zero: the failure mode we
    are guarding against is a fork storm, so the fail-safe direction is "do not spawn".
    """
    try:
        return int(os.environ.get(DEPTH_ENV, "0"))
    except ValueError:
        return MAX_DEPTH


def _guard(repo: Path) -> tuple[int, str]:
    """Run this guard against `repo` exactly as an operator would, and capture its output.

    The child judges and does not spawn: it receives `DRIFT_DEPTH=<n+1>` in its
    environment, and a process at depth >= `MAX_DEPTH` never runs the arms. That cap is
    what makes the recursion impossible rather than merely unlikely — `--judge-only` is
    passed too, but as documentation: the environment is the enforcement.
    """
    depth = _depth()
    if depth >= MAX_DEPTH:
        # Refuse to spawn at all. This returns a VERDICT (a named reason), never a fork:
        # a child that re-armed would recurse until the box starved.
        return 1, (
            f"refused to spawn at {DEPTH_ENV}={depth} (cap {MAX_DEPTH}): "
            "the arms run once, in the parent, and a child judges without spawning"
        )
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--repo", str(repo), "--judge-only"],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, DEPTH_ENV: str(depth + 1)},
    )
    return completed.returncode, completed.stdout + completed.stderr


def _probe() -> None:
    print("  --- arms ---")
    with tempfile.TemporaryDirectory() as raw:
        scratch = Path(raw)

        # ARM 1 (positive control): a declaration absent from the law table is REPORTED,
        # naming BOTH the surface and the doc that declares it.
        absent = _fixture(
            scratch / "arm1",
            instruments={"demo.md": _SURFACE_TABLE.format(token="docs/undeclared.json")},
            law=_LAW_TABLE.format(extra=""),
        )
        code, output = _guard(absent)
        check(
            "ARM 1 a declaration absent from the law table is REPORTED",
            code == 1 and "docs/undeclared.json" in output and "docs/instruments/demo.md" in output,
            f"rc={code}",
        )

        # ARM 2 (negative control): the SAME fixture exits 0 once the surface is mirrored.
        mirrored = _fixture(
            scratch / "arm2",
            instruments={"demo.md": _SURFACE_TABLE.format(token="docs/undeclared.json")},
            law=_LAW_TABLE.format(
                extra="| `docs/undeclared.json` | the mirrored surface | `HQ` | read-only |\n"
            ),
        )
        code, output = _guard(mirrored)
        check(
            "ARM 2 the same declaration is CLEARED once mirrored in the law table",
            code == 0 and "examined 1 declaration(s) in 1 instrument doc(s)" in output,
            f"rc={code}",
        )

        # ARM 3 (empty population): distinguishable from a clean run by its own print.
        empty = _fixture(scratch / "arm3", instruments=None, law=_LAW_TABLE.format(extra=""))
        code, output = _guard(empty)
        check(
            "ARM 3 an empty population exits 0 and PRINTS the examined-zero line",
            code == 0 and "examined 0 declaration(s) in 0 instrument doc(s)" in output,
            f"rc={code}",
        )

        # ARM 4 (refusal): home A unlocatable is a named refusal, never a green.
        homeless = _fixture(
            scratch / "arm4",
            instruments={"demo.md": _SURFACE_TABLE.format(token="docs/undeclared.json")},
            law=None,
        )
        code, output = _guard(homeless)
        check(
            "ARM 4 an unlocatable law table REFUSES by name, never a green",
            code == 1 and "REFUSED" in output,
            f"rc={code}",
        )

        # ARM 5 (grammar): a declaration outside the grammar is OUTSIDE the population,
        # not a failure — `<` placeholders, absolute paths, prose and non-backticked cells.
        off_grammar = _fixture(
            scratch / "arm5",
            instruments={
                "demo.md": (
                    "| surface | ships as | owner |\n"
                    "|---|---|---|\n"
                    "| `docs/thing.<name>.json` | generated | the kit |\n"
                    "| `/tmp/<job>.log` | created | the factory |\n"
                    "| the declared LEDGER path | the member's own | the factory |\n"
                    "| docs/unbackticked.json | generated | the kit |\n"
                )
            },
            law=_LAW_TABLE.format(extra=""),
        )
        code, output = _guard(off_grammar)
        check(
            "ARM 5 declarations outside the grammar are outside the population",
            code == 0 and "examined 0 declaration(s) in 1 instrument doc(s)" in output,
            f"rc={code}",
        )

        # ARM 6 (grammar, the accepting half): the three normalisations the ruling names.
        on_grammar = _fixture(
            scratch / "arm6",
            instruments={
                "demo.md": (
                    "| surface | ships as | owner |\n"
                    "|---|---|---|\n"
                    "| `registry/fleet.json` → `job_prefixes` | example | the factory |\n"
                    "| `registry/factories/*.json` | the adopter writes its own | the factory |\n"
                )
            },
            law=(
                "| Surface | Holds | Authoritative writer | Everyone else |\n"
                "|---|---|---|---|\n"
                "| `registry/fleet.json` and `registry/factories/*.json` | what each factory IS | `HQ` | read-only |\n"
            ),
        )
        code, output = _guard(on_grammar)
        check(
            "ARM 6 ` → ` keeps the left side and ` and ` splits home A's joined cell",
            code == 0 and "examined 2 declaration(s) in 1 instrument doc(s)" in output,
            f"rc={code}",
        )

        # ARM 7 (the recursion cap, #313 incident): a process that is ALREADY a child
        # (DRIFT_DEPTH=1) judges WITHOUT running the arms even when `--judge-only` is
        # DROPPED — which is exactly the argv-dependence that forked the box 152 ways at
        # 05:57Z 2026-10-16. The discriminator is the arms' own banner: a guard that
        # re-armed would print it and spawn grandchildren; a structural one never does.
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--repo", str(mirrored)],
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, DEPTH_ENV: "1"},
        )
        check(
            "ARM 7 a child at DRIFT_DEPTH=1 judges instead of re-arming (flag DROPPED)",
            completed.returncode == 0 and "--- arms ---" not in completed.stdout,
            f"rc={completed.returncode}",
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="declaration-drift guard (#313)")
    parser.add_argument("--repo", default=None, help="the tree to judge (default: this gate's own repo)")
    parser.add_argument(
        "--judge-only",
        action="store_true",
        help="judge `repo` and print the verdict without running the arms (the probe's own child)",
    )
    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve() if args.repo else REPO

    # `--judge-only` DOCUMENTS the intent; the depth counter ENFORCES it. A child that
    # arrives here with the flag dropped — or with any argv at all — still judges rather
    # than re-arming, which is what makes the fork storm structurally impossible (#313).
    if args.judge_only or _depth() >= MAX_DEPTH:
        return run(repo)

    print("declaration drift — every surface in docs/instruments/*.md must be mirrored in the law table (#313)")
    _probe()

    # The control that carries the root verdict: a clean run is a verdict only if the
    # population it examined was non-empty. ARM 1 proves the instrument bites; this
    # proves it was reading something.
    declarations, _ = instrument_declarations(repo)
    check(
        f"CONTROL this tree declares a non-empty population ({len(declarations)})",
        bool(declarations),
        "an empty population would make the clean verdict vacuous",
    )

    code = run(repo)

    if _failures or code:
        print(f"declaration drift FAILED — {len(_failures)} arm(s), exit {code}")
        return 1
    print("declaration drift passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
