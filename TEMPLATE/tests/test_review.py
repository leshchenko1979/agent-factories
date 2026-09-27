#!/usr/bin/env python3
"""Tests for the Multi-Lens Review Engine (tools/review.py / P32)."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _schema_pair() -> list[Path]:
    """The shipped copies of the schema, relative to whichever tree this file sits in.

    In the factory, REPO_ROOT is the repo root and the pair is
    (docs/…, TEMPLATE/docs/…). In the TEMPLATE half's own checkout REPO_ROOT IS
    the TEMPLATE directory, so the pair is one level up. A bootstrapped member
    factory carries no TEMPLATE/ tree and therefore ships one copy — the same
    degradation `test_docs_sync.py` and `test_template_integrity.py` use, so the
    gate holds in a member instead of reding on a tree that was never there.
    """
    root = REPO_ROOT.parent if REPO_ROOT.name == "TEMPLATE" else REPO_ROOT
    paths = [root / "docs" / "review-cycle.schema.json"]
    template_copy = root / "TEMPLATE" / "docs" / "review-cycle.schema.json"
    if template_copy.parent.is_dir():
        paths.append(template_copy)
    return paths


def test_review_lifecycle(tmp_path: Path) -> None:
    # Use isolated test directory
    cycle_id = "test-cycle-01"
    cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]

    # 0. Brief generation (Adversarial auditor prompt)
    res = subprocess.run(cmd_base + ["brief", "A"], cwd=REPO_ROOT, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert "ADVERSARIAL AUDITOR BRIEF — LENS A" in res.stdout

    # 1. Init
    res = subprocess.run(cmd_base + ["init", cycle_id], cwd=REPO_ROOT, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr

    cycle_dir = REPO_ROOT / "reviews" / cycle_id
    try:
        assert cycle_dir.is_dir()
        state_file = cycle_dir / "state.json"
        assert state_file.is_file()

        with open(state_file, "r", encoding="utf-8") as f:
            state = json.load(f)
        assert state["cycle_id"] == cycle_id
        assert state["status"] == "IN_PROGRESS"
        assert len(state["lenses"]) == 14

        # 2. Record Lens A
        report_text = "# Lens A Review\nVerbatim quote found in role file: 'foo'\n"
        res = subprocess.run(
            cmd_base + ["record", cycle_id, "A", report_text],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, res.stderr

        # 3. Status (should indicate pending lenses)
        res = subprocess.run(cmd_base + ["status", cycle_id], cwd=REPO_ROOT, capture_output=True, text=True)
        assert res.returncode == 1  # non-zero because pending > 0

        # 4. Waive the remaining 13 lenses
        for lens in ["B", "G", "J", "P", "C", "E", "F", "D", "H", "M", "T", "I", "S"]:
            res = subprocess.run(
                cmd_base + ["waive", cycle_id, lens, "--reason", "Test waiver"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            assert res.returncode == 0, res.stderr

        # 5. Verify gate (should now pass 0)
        res = subprocess.run(cmd_base + ["verify", cycle_id], cwd=REPO_ROOT, capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        assert "census verified clean" in res.stdout

        # 6. Compile master verdict
        res = subprocess.run(cmd_base + ["compile", cycle_id], cwd=REPO_ROOT, capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        assert (cycle_dir / "verdict.md").is_file()

    finally:
        # Cleanup test cycle dir
        if cycle_dir.exists():
            shutil.rmtree(cycle_dir)


def test_schema_artifact_is_generated() -> None:
    """The shipped schema pair is byte-identical to what the tool emits.

    One authoring home: the schema is a constant in `review.py` and the shipped
    artifact is generated from it. A hand-edited artifact would drift silently,
    so this asserts the bytes rather than the JSON equality.
    """
    cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]
    res = subprocess.run(cmd_base + ["schema"], cwd=REPO_ROOT, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr

    for path in _schema_pair():
        shipped = path.read_text(encoding="utf-8")
        assert shipped == res.stdout, f"{path} is stale — regenerate it from `review.py schema`"

    schema = json.loads(res.stdout)
    assert schema["schema_version"] == 1
    for key in ("cycle_id", "status", "ended_at", "duration_review_min",
                "duration_cycle_min", "cadence", "corpus", "lenses", "waivers"):
        assert key in schema["properties"], f"schema lost {key}"
    # The terminal enum is CLOSED. A free-text status is the measured donor
    # defect this exists to prevent.
    assert schema["properties"]["status"]["enum"] == ["IN_PROGRESS", "COMPLETED", "ABANDONED"]


def test_cadence_boundary_is_anchored() -> None:
    """The cadence stamp derives from ANCHORED close rows and counts BUMP rows.

    TWO predicates, and the trap is that they look like one.  Counting anchored
    rows instead of bump rows passes every single-close fixture, because the
    close stamp is itself anchored — so the discriminating case below carries a
    SECOND close, which is the only shape that separates them.
    """
    cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]

    def run(rows: list[dict]) -> dict:
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")
            ledger = handle.name
        res = subprocess.run(
            cmd_base + ["cadence", "--ledger", ledger, "--json"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        assert res.returncode == 0, res.stderr
        return json.loads(res.stdout)

    def close(n: int, v: str) -> dict:
        return {"n": n, "ts": f"2026-09-0{n}T00:00:00Z", "event": "note",
                "detail": f"{v} ACCEPTED — Duty-6 cycle c{n} closed"}

    def bump(n: int, v: str) -> dict:
        return {"n": n, "ts": f"2026-09-1{n}T00:00:00Z", "event": "skill-bump",
                "detail": f"{v} — a landed change"}

    # No boundary at all: a NAMED state, never a silent zero.
    empty = run([])
    assert empty["boundary"]["ref"] is None
    assert empty["fires"] is False
    assert empty["boundary"]["accepted_since"] == 0

    # One anchored close, then four bumps: 4/5 WAIT.
    wait = run([
        close(1, "v0.4.1"), bump(2, "v0.4.2"), bump(3, "v0.4.3"),
        bump(4, "v0.4.4"), bump(5, "v0.4.5"),
    ])
    assert wait["boundary"]["ref"] == "n=1", wait["boundary"]
    assert wait["boundary"]["accepted_since"] == 4, wait["boundary"]
    assert wait["fires"] is False

    # A fifth bump fires — and a row that merely MENTIONS the pattern does not
    # count as either a boundary or a bump.
    fire = run([
        close(1, "v0.4.1"), bump(2, "v0.4.2"), bump(3, "v0.4.3"),
        bump(4, "v0.4.4"), bump(5, "v0.4.5"), bump(6, "v0.4.6"),
        {"n": 7, "ts": "2026-09-17T00:00:00Z", "event": "note",
         "detail": "WITHHELD: no END written; the pattern ^vN.N.N ACCEPTED is quoted here"},
    ])
    assert fire["fires"] is True, fire
    assert fire["boundary"]["accepted_since"] == 5, "an unanchored mention was harvested"

    # THE DISCRIMINATOR. A second close re-anchors the boundary, and the bumps
    # are counted from THERE — not the anchored-row total.  Under the wrong
    # predicate this reads 0; the correct answer is 1.
    two_closes = run([
        close(1, "v0.4.1"), bump(2, "v0.4.2"), close(3, "v0.4.3"), bump(4, "v0.4.4"),
    ])
    assert two_closes["boundary"]["ref"] == "n=3", two_closes["boundary"]
    assert two_closes["boundary"]["accepted_since"] == 1, (
        "the count followed the anchored rows, not the bump rows"
    )


def test_cadence_reads_both_shipped_ledger_formats(tmp_path: Path) -> None:
    """A donor-format ledger is read, never silently reported as an empty one.

    A reader that recognises only one format returns a boundary of None and a
    count of 0 for the other — indistinguishable from a genuine 0/5 WAIT.  The
    donor's ledger is a single JSON object carrying an `events` array, and its
    row kind column is `kind`, not `event`.
    """
    cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]
    donor = tmp_path / "workers-ledger.json"
    donor.write_text(json.dumps({
        "events": [
            {"n": 1, "t": "2026-09-01T00:00:00Z", "kind": "note",
             "what": "v0.4.1 ACCEPTED — Duty-6 cycle c1 closed"},
            {"n": 2, "t": "2026-09-02T00:00:00Z", "kind": "skill-bump", "what": "v0.4.2"},
            {"n": 3, "t": "2026-09-03T00:00:00Z", "kind": "skill-bump", "what": "v0.4.3"},
        ]
    }), encoding="utf-8")

    res = subprocess.run(cmd_base + ["cadence", "--ledger", str(donor), "--json"],
                         cwd=REPO_ROOT, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    stamp = json.loads(res.stdout)
    assert stamp["boundary"]["ref"] == "n=1", stamp["boundary"]
    assert stamp["boundary"]["accepted_since"] == 2, stamp["boundary"]
    # The donor's time column is `t`, not `ts`: reading only one loses the
    # timestamp silently, which is indistinguishable from an absent one.
    assert stamp["boundary"]["at"] == "2026-09-01T00:00:00Z", stamp["boundary"]


def test_legacy_state_is_refused_and_migrated_explicitly(tmp_path: Path) -> None:
    """A pre-v1 state file is never migrated as a side effect of a routine write."""
    cycle_id = "test-legacy-01"
    cycle_dir = REPO_ROOT / "reviews" / cycle_id
    cycle_dir.mkdir(parents=True, exist_ok=True)
    cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]
    legacy = {
        "cycle_id": cycle_id,
        "status": "reports_persisted",          # free text: not a v1 enum value
        "started_at": "2026-09-01T00:00:00Z",
        "lenses": {"A": {"status": "COMPLETED", "report_path": "x.md", "sha256": "ab"}},
        "waivers": {"B": {"reason": "no scope", "waived_at": "2026-09-01T01:00:00Z"}},
        "corpus_hash": "cafe1234",
    }
    try:
        (cycle_dir / "state.json").write_text(json.dumps(legacy, indent=2), encoding="utf-8")

        # A routine write REFUSES a legacy file rather than migrating it.
        res = subprocess.run(
            cmd_base + ["waive", cycle_id, "C", "--reason", "trial"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        assert res.returncode == 3, f"expected refusal rc=3, got {res.returncode}: {res.stdout}"
        assert json.loads((cycle_dir / "state.json").read_text())["status"] == "reports_persisted"

        # The migration is explicit, reports its mapping, and leaves a pre-image.
        res = subprocess.run(
            cmd_base + ["migrate", cycle_id, "--dry-run"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        assert res.returncode == 0, res.stderr
        assert "dry run: nothing written" in res.stdout
        assert "corpus_hash" in res.stdout, "the mapping did not report the folded key"

        res = subprocess.run(cmd_base + ["migrate", cycle_id], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        assert (cycle_dir / "state.json.pre-v1.bak").is_file(), "no pre-image was left"

        migrated = json.loads((cycle_dir / "state.json").read_text())
        assert migrated["schema_version"] == 1
        # The dict-shaped waivers became a LOG; the flat corpus_hash folded in.
        assert isinstance(migrated["waivers"], list) and migrated["waivers"][0]["lens"] == "B"
        assert migrated["corpus"]["hash"] == "cafe1234"
        assert "corpus_hash" not in migrated
        # Every catalog lens is materialized, so coverage is computable.
        assert len(migrated["lenses"]) == 14
    finally:
        if cycle_dir.exists():
            shutil.rmtree(cycle_dir)


def test_close_sets_both_durations(tmp_path: Path) -> None:
    """`close` writes an explicit terminal state and TWO distinct durations."""
    cycle_id = "test-close-01"
    cycle_dir = REPO_ROOT / "reviews" / cycle_id
    cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]
    try:
        res = subprocess.run(cmd_base + ["init", cycle_id], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        res = subprocess.run(cmd_base + ["record", cycle_id, "A", "# Lens A\nfinding\n"],
                             cwd=REPO_ROOT, capture_output=True, text=True)
        assert res.returncode == 0, res.stderr

        # Before close: null, never absent.
        state = json.loads((cycle_dir / "state.json").read_text())
        assert state["ended_at"] is None
        assert state["duration_cycle_min"] is None

        res = subprocess.run(cmd_base + ["close", cycle_id], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        closed = json.loads((cycle_dir / "state.json").read_text())
        assert closed["status"] == "COMPLETED"
        assert closed["ended_at"] is not None
        assert isinstance(closed["duration_cycle_min"], (int, float))
        assert isinstance(closed["duration_review_min"], (int, float))

        # Closing twice is refused: the terminal state is terminal.
        res = subprocess.run(cmd_base + ["close", cycle_id], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        assert res.returncode == 2, res.stdout
    finally:
        if cycle_dir.exists():
            shutil.rmtree(cycle_dir)


def test_verify_reports_unreceipted_lenses() -> None:
    """A COMPLETED lens with no index line is UNRECEIPTED, not clean."""
    cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]
    cycle_id = "test-receipt-01"
    cycle_dir = REPO_ROOT / "reviews" / cycle_id
    try:
        subprocess.run(cmd_base + ["init", cycle_id], cwd=REPO_ROOT, capture_output=True, text=True)
        subprocess.run(cmd_base + ["record", cycle_id, "A", "# Lens A\nfinding\n"],
                       cwd=REPO_ROOT, capture_output=True, text=True)

        # Strip the receipt marker the way a lost index line would.
        state = json.loads((cycle_dir / "state.json").read_text())
        state["lenses"]["A"]["receipt"] = None
        (cycle_dir / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")

        for lens in ["B", "G", "J", "P", "C", "E", "F", "D", "H", "M", "T", "I", "S"]:
            subprocess.run(cmd_base + ["waive", cycle_id, lens, "--reason", "trial"],
                           cwd=REPO_ROOT, capture_output=True, text=True)

        res = subprocess.run(cmd_base + ["verify", cycle_id], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        assert res.returncode == 1, res.stdout
        assert "UNRECEIPTED" in res.stdout
    finally:
        if cycle_dir.exists():
            shutil.rmtree(cycle_dir)


if __name__ == "__main__":
    test_review_lifecycle(Path("/tmp"))
    test_schema_artifact_is_generated()
    test_cadence_boundary_is_anchored()
    test_legacy_state_is_refused_and_migrated_explicitly(Path("/tmp"))
    test_close_sets_both_durations(Path("/tmp"))
    test_verify_reports_unreceipted_lenses()
    print("ALL TESTS PASSED")
