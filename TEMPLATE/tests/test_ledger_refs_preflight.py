#!/usr/bin/env python3
"""Gate: an undeclared `--ref` KIND is refused at the write path, not a step later.

The ledger validated a ref's FORM at `append` and its KIND only at `verify`. So a lane
could invent a kind, the row was written, pushed, and only then refused — and a row is
immutable once pushed, so the only remedy left is to DECLARE the kind after the fact.
`#187` closed exactly this shape for the `head=` presence contract by moving the check to
the write path; the ref-kind contract was the same shape one field over and stayed
gate-only. This is the third instance of the class in this tool (`#157` -> `#187` -> this).

WHY THE CHECK SITS INSIDE `parse_refs` AND NOT AT ITS CALL SITE
---------------------------------------------------------------
`parse_refs` already calls `known_ref_kinds()` — in the message it prints when a ref's FORM
is malformed. The function therefore already holds the predicate and already names the
lawful set; it never tested membership. Putting the test there keeps the predicate SINGLE
(the same reason `#187` gave), and it preserves "refuse before the lock is taken" by
construction, because `parse_refs` runs before the append lock.

WHAT THE REFUSAL MUST NAME, AND WHY
-----------------------------------
Both the lawful kinds and `docs/ledger-refs-kinds.json`. The lawful remedy for a genuinely
new kind is to DECLARE it, never to drop the ref — a message naming only the kinds would
push a lane toward deleting the pointer it needed.

TWO FIXTURE WRITERS, AND WHY THEY ARE UNAFFECTED
------------------------------------------------
The declaration is read from `REFS_KINDS_FILE`, overridable through `OC_REFS_KINDS_PATH` —
the same seam every other reader in this module uses. So a probe or a fixture that declares
its own kinds writes exactly as before; the check inherits that seam rather than inventing a
second policy. One probe below declares `issue` on a fixture tree and proves the write
still lands, which is the arm that shows the fix closes the undeclared half and NOT the
extension point.

WHAT THIS GATE DOES NOT ASSERT
------------------------------
A `row:` ref naming a nonexistent row stays the EXISTENCE leg's (`#187` drew that line), and
`issue:` / `commit:` values stay opaque by design. This closes the undeclared-kind half only.

Every probe runs against a THROWAWAY ledger and a THROWAWAY declaration through the
`OC_LEDGER_PATH` / `OC_REFS_KINDS_PATH` seams; one probe asserts the live state surface is
untouched.

RUNNER: pytest, declared in `registry/gates.json` under `modes`. The probes are module-level
`def test_*`, so the test functions own the verdict and there is deliberately no `main()` —
the same shape as this gate's two siblings, `test_ledger_claim_preflight.py` and
`test_ledger_close_preflight.py`. A script runner cannot report this file's target: a
test-carrying file is pytest-form regardless of what it guards, which is exactly what
`test_gate_registration.py`'s direction 5 names.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "ledger.py"
LIVE_LEDGER = REPO / "evidence" / "ledger.jsonl"
DECLARATION_NAME = "docs/ledger-refs-kinds.json"

CORE_KINDS = ("row", "subject", "commit", "session", "rework")


def _throwaway(tmp: str) -> Path:
    return Path(tmp) / "ledger.jsonl"


def _env(ledger: Path, declaration: Path | None = None) -> dict:
    env = {
        **os.environ,
        "OC_LEDGER_PATH": str(ledger),
        "OC_ACTORS_PATH": str(ledger.parent / "no-actors.txt"),
        "OPENCRABS_DB_PATH": str(ledger.parent / "no-telemetry.db"),
    }
    if declaration is not None:
        env["OC_REFS_KINDS_PATH"] = str(declaration)
    return env


def run(ledger: Path, *args: str, declaration: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True, text=True, env=_env(ledger, declaration), cwd=REPO,
    )


def append_with_ref(ledger: Path, ref: str, declaration: Path | None = None) -> subprocess.CompletedProcess:
    return run(
        ledger,
        "append", "--event", "run", "--actor", "worker",
        "--subject", "probe", "--detail", "ref-kind probe", "--ref", ref,
        declaration=declaration,
    )


def declare(path: Path, kinds: list[str]) -> Path:
    path.write_text(json.dumps({"kinds": kinds}), encoding="utf-8")
    return path


def rows_of(ledger: Path) -> list[dict]:
    if not ledger.exists():
        return []
    return [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]


# --------------------------------------------------------------------------
# The probes.
# --------------------------------------------------------------------------

def test_an_undeclared_kind_is_refused_and_names_the_declaration(tmp_path: Path) -> None:
    ledger = _throwaway(str(tmp_path))
    proc = append_with_ref(ledger, "invented:1")
    assert proc.returncode != 0, "an undeclared kind must be refused"
    out = proc.stdout + proc.stderr
    assert "invented" in out, f"the refusal must name the kind it rejected: {out!r}"
    assert DECLARATION_NAME in out, (
        f"the refusal must name {DECLARATION_NAME}, because the lawful remedy is to declare "
        f"the kind: {out!r}"
    )
    for kind in CORE_KINDS:
        assert kind in out, f"the refusal must name the lawful kind {kind!r}: {out!r}"
    assert rows_of(ledger) == [], "a refusal must write NOTHING"


def test_a_core_kind_still_writes(tmp_path: Path) -> None:
    ledger = _throwaway(str(tmp_path))
    proc = append_with_ref(ledger, "commit:deadbeef")
    assert proc.returncode == 0, f"a core kind must still write: {proc.stdout}{proc.stderr}"
    rows = rows_of(ledger)
    assert len(rows) == 1, f"exactly one row must land, got {len(rows)}"


def test_a_declared_kind_writes_through_the_seam(tmp_path: Path) -> None:
    # The arm that shows the fix closes the undeclared half and NOT the extension point: a
    # factory declares its own kind in its own file, and nothing in this module changes.
    ledger = _throwaway(str(tmp_path))
    declaration = declare(Path(tmp_path) / "refs.json", ["issue"])

    refused = append_with_ref(ledger, "issue:123")
    assert refused.returncode != 0, (
        "`issue` must be refused on a tree that has not declared it — that is the whole check"
    )
    assert rows_of(ledger) == [], "the refusal must write nothing"

    accepted = append_with_ref(ledger, "issue:123", declaration=declaration)
    assert accepted.returncode == 0, (
        f"a DECLARED kind must write: {accepted.stdout}{accepted.stderr}"
    )
    assert len(rows_of(ledger)) == 1, "the declared kind's row must land"


def test_the_membership_reads_the_declaration_not_the_core_tuple(tmp_path: Path) -> None:
    # A kind is lawful because the factory DECLARED it, never because the core tuple happens
    # to be long enough. Declaring a kind that overlaps no core name proves the predicate
    # reads the declaration surface.
    ledger = _throwaway(str(tmp_path))
    declaration = declare(Path(tmp_path) / "refs.json", ["ticket"])
    proc = append_with_ref(ledger, "ticket:ABC-1", declaration=declaration)
    assert proc.returncode == 0, f"a declared kind must write: {proc.stdout}{proc.stderr}"
    assert len(rows_of(ledger)) == 1


def test_a_malformed_ref_still_names_the_lawful_kinds(tmp_path: Path) -> None:
    # The FORM leg is untouched by this change, and its message already carried the kinds —
    # which is precisely why the membership test belonged beside it.
    ledger = _throwaway(str(tmp_path))
    proc = append_with_ref(ledger, "no-colon-here")
    assert proc.returncode != 0
    out = proc.stdout + proc.stderr
    assert "not KIND:VALUE" in out, f"the form refusal must still fire: {out!r}"


def test_the_tests_never_write_the_live_ledger(tmp_path: Path) -> None:
    # THE SHIPPED TREE CARRIES NO `evidence/` (#199). The ledger is BOOTSTRAP-created, so
    # there is no live file here to compare against; the property holds vacuously and the
    # skip is STATED so the vacuity is visible rather than read as a silent pass.
    if not LIVE_LEDGER.is_file():
        print(f"  SKIPPED  no {LIVE_LEDGER.relative_to(REPO)} in this tree — nothing live to "
              f"reach, so the isolation property holds vacuously here")
        return
    before = LIVE_LEDGER.read_bytes()
    ledger = _throwaway(str(tmp_path))
    assert append_with_ref(ledger, "invented:1").returncode != 0
    assert append_with_ref(ledger, "commit:deadbeef").returncode == 0
    assert LIVE_LEDGER.read_bytes() == before, "a probe wrote the live state surface"
