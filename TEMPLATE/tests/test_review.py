#!/usr/bin/env python3
"""Tests for the Multi-Lens Review Engine (tools/review.py / P32)."""

import hashlib
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


def _fresh_cycle(cycle_id: str) -> Path:
    """Init a cycle and return its dir, for tests that need a clean tree."""
    cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]
    cycle_dir = REPO_ROOT / "reviews" / cycle_id
    if cycle_dir.exists():
        shutil.rmtree(cycle_dir)
    subprocess.run(cmd_base + ["init", cycle_id], cwd=REPO_ROOT, capture_output=True, text=True)
    return cycle_dir

def test_intake_refuses_with_no_declarations() -> None:
    """A tree that declares no input channel is REFUSED, not read as empty.

    This is the class the leg exists to prevent: nothing declared, read as
    "nobody submitted", reported as a clean pass. `init` alone creates no
    intake channel, so the refusal is the default state rather than an edge.
    """
    cycle_id = "test-intake-nodecl"
    cycle_dir = _fresh_cycle(cycle_id)
    try:
        cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]
        res = subprocess.run(cmd_base + ["intake", cycle_id], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        assert res.returncode != 0, res.stdout
        assert "INTAKE REFUSED" in res.stderr, res.stderr
        assert not (cycle_dir / "proposals").is_dir()
    finally:
        if cycle_dir.exists():
            shutil.rmtree(cycle_dir)

def test_intake_is_read_only_over_member_data(tmp_path: Path) -> None:
    """Intake reads the member's data and never writes it.

    The proposals and the ledger are the FACTORY's, not the instrument's: an
    intake that touched either would corrupt the evidence it exists to collect.
    """
    cycle_id = "test-intake-ro"
    cycle_dir = _fresh_cycle(cycle_id)
    try:
        proposals = cycle_dir / "proposals"
        proposals.mkdir(parents=True, exist_ok=True)
        (proposals / "w1.md").write_text(
            "ADD a naming criterion in docs/x.md#4 BECAUSE the census missed a shadow on 2026-09-27.\n",
            encoding="utf-8",
        )
        ledger = tmp_path / "ledger.jsonl"
        ledger.write_text(
            json.dumps({"n": 1, "kind": "proposal", "t": "2026-09-27T10:00:00Z",
                        "note": "CHANGE the cadence predicate in tools/review.py#cadence "
                                "BECAUSE the donor used a different column on 2026-09-27."}) + "\n",
            encoding="utf-8",
        )
        (cycle_dir / "intake.json").write_text(
            json.dumps({"ledger": str(ledger), "ledger_kind": "proposal"}), encoding="utf-8")

        watched = [proposals / "w1.md", ledger]
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}

        cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]
        res = subprocess.run(cmd_base + ["intake", cycle_id, "--record"], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        assert res.returncode == 0, res.stdout + res.stderr
        assert "INTAKE COMPLETE" in res.stdout
        assert "2 proposal(s)" in res.stdout

        after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}
        assert before == after, "intake wrote to factory-owned data"
    finally:
        if cycle_dir.exists():
            shutil.rmtree(cycle_dir)

def test_intake_names_empty_and_incomplete() -> None:
    """Zero submissions and a malformed one are DIFFERENT named states, both non-pass."""
    cycle_id = "test-intake-states"
    cycle_dir = _fresh_cycle(cycle_id)
    try:
        cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]
        proposals = cycle_dir / "proposals"
        proposals.mkdir(parents=True, exist_ok=True)

        res = subprocess.run(cmd_base + ["intake", cycle_id], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        assert res.returncode == 1, res.stdout
        assert "INTAKE EMPTY" in res.stdout

        (proposals / "bad.md").write_text("not a proposal at all\n", encoding="utf-8")
        res = subprocess.run(cmd_base + ["intake", cycle_id], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        assert res.returncode == 1, res.stdout
        assert "INTAKE INCOMPLETE" in res.stdout
        assert "bad.md" in res.stderr and "format" in res.stderr
    finally:
        if cycle_dir.exists():
            shutil.rmtree(cycle_dir)

def test_intake_refuses_a_declared_channel_that_is_absent(tmp_path: Path) -> None:
    """A declared channel the tree cannot honour is a REFUSAL, not an empty read."""
    cycle_id = "test-intake-absent"
    cycle_dir = _fresh_cycle(cycle_id)
    try:
        (cycle_dir / "proposals").mkdir(parents=True, exist_ok=True)
        (cycle_dir / "intake.json").write_text(
            json.dumps({"ledger": str(tmp_path / "nope.jsonl")}), encoding="utf-8")
        cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]
        res = subprocess.run(cmd_base + ["intake", cycle_id], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        assert res.returncode == 2, res.stdout
        assert "INTAKE REFUSED" in res.stderr
        assert "cannot honour" in res.stderr
    finally:
        if cycle_dir.exists():
            shutil.rmtree(cycle_dir)

def test_intake_receipts_validate_against_the_schema() -> None:
    """Every key a receipt carries is DECLARED by the shipped schema."""
    cycle_id = "test-intake-schema"
    cycle_dir = _fresh_cycle(cycle_id)
    try:
        proposals = cycle_dir / "proposals"
        proposals.mkdir(parents=True, exist_ok=True)
        (proposals / "w1.md").write_text(
            "ADD a rule in docs/x.md#4 BECAUSE it was missing on 2026-09-27.\n", encoding="utf-8")
        cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]
        res = subprocess.run(cmd_base + ["intake", cycle_id, "--record"], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        assert res.returncode == 0, res.stdout + res.stderr

        schema = json.loads(subprocess.run(cmd_base + ["schema"], cwd=REPO_ROOT,
                                           capture_output=True, text=True).stdout)
        item = schema["properties"]["proposals"]["items"]
        declared = set(item["properties"])
        required = set(item["required"])
        state = json.loads((cycle_dir / "state.json").read_text(encoding="utf-8"))
        assert state["proposals"], "intake --record wrote no receipts"
        for receipt in state["proposals"]:
            undeclared = set(receipt) - declared
            assert not undeclared, f"receipt carries undeclared keys {undeclared}"
            assert required <= set(receipt), f"receipt misses required {required - set(receipt)}"
    finally:
        if cycle_dir.exists():
            shutil.rmtree(cycle_dir)

def test_shipped_executable_carries_no_donor_tokens() -> None:
    """The shipped executable names no donor surface.

    The donor's recipients, session uuids, board ids and lane names are its
    process law, not this instrument's: a member has its own lanes and its own
    board, and a shipped literal would send a member's work to the donor's.
    """
    source = (REPO_ROOT / "tools" / "review.py").read_text(encoding="utf-8")
    tokens = ["4515ea72", "d6cfd3f7", "37e71e03", "2646d31a", "30220",
              "oc-notify-fanout", "session_notify", "hq.md", "fleet-directives"]
    found = {t: source.count(t) for t in tokens if source.count(t)}
    assert not found, f"donor tokens in the shipped executable: {found}"

def test_step0_recovery_reads_state_alone_and_records_durable_evidence() -> None:
    """Step 0 is a COMMAND, and its reading survives as evidence.

    The module docstring claimed state.json IS the step-0 recovery point from
    promotion until now. A compacted session cannot execute a paragraph, so the
    claim is only real if there is something to RUN that reads state and nothing
    else — and `--record` is what makes the reading durable rather than printed.
    """
    cycle_id = "test-step0-recovery"
    cycle_dir = _fresh_cycle(cycle_id)
    try:
        cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]
        res = subprocess.run(cmd_base + ["step0", cycle_id], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        assert res.returncode == 0, res.stdout + res.stderr
        assert "Step 0 recovery" in res.stdout
        assert "frozen=no" in res.stdout
        assert "14 pending" in res.stdout
        assert "next action" in res.stdout

        res = subprocess.run(cmd_base + ["step0", cycle_id, "--record"], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        assert res.returncode == 0, res.stdout + res.stderr
        state = json.loads((cycle_dir / "state.json").read_text(encoding="utf-8"))
        assert len(state["step0_log"]) == 1, "step0 --record wrote no durable evidence"
        entry = state["step0_log"][0]
        assert entry["pending"] == 14 and entry["frozen"] is False
        assert entry["next_action"].strip(), "a recorded reading must carry its next action"
    finally:
        if cycle_dir.exists():
            shutil.rmtree(cycle_dir)

def test_frozen_cycle_refuses_a_live_channel_read() -> None:
    """A closed cycle's inputs are historical: re-reading a live channel is REFUSED.

    Both intake channels are mutable — a proposals directory grows and a ledger
    is appended to — so reading one against a closed cycle answers a different
    question than the one the cycle closed on. `--live` is the deliberate way to
    say the reader means today's bytes, and it must SAY SO rather than pass.
    """
    cycle_id = "test-frozen-refusal"
    cycle_dir = _fresh_cycle(cycle_id)
    try:
        cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]
        proposals = cycle_dir / "proposals"
        proposals.mkdir(parents=True, exist_ok=True)
        (proposals / "w1.md").write_text(
            "ADD a rule in docs/x.md#4 BECAUSE it was missing on 2026-09-27.\n", encoding="utf-8")

        res = subprocess.run(cmd_base + ["close", cycle_id, "--status", "COMPLETED"],
                             cwd=REPO_ROOT, capture_output=True, text=True)
        assert res.returncode == 0, res.stdout + res.stderr
        assert "frozen_at=" in res.stdout, "close must freeze the cycle"

        state = json.loads((cycle_dir / "state.json").read_text(encoding="utf-8"))
        assert state["frozen_at"], "close wrote no frozen_at"
        snapshot = state["inputs_snapshot"]
        assert snapshot and snapshot["channels"], "close took no inputs snapshot"
        assert snapshot["channels"][0]["sha256"], "the snapshot carries no digest"

        res = subprocess.run(cmd_base + ["intake", cycle_id], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        assert res.returncode == 2, res.stdout
        assert "FROZEN" in res.stderr and "REFUSED" in res.stderr

        res = subprocess.run(cmd_base + ["intake", cycle_id, "--live"], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        assert res.returncode == 0, res.stdout + res.stderr
        assert "WARNING" in res.stderr and "TODAY's" in res.stderr
    finally:
        if cycle_dir.exists():
            shutil.rmtree(cycle_dir)

def test_a_lens_waiver_requires_a_named_reason() -> None:
    """A waiver with no reason is the undeclared state in a declared label.

    The census's whole job is that every lens ran or was EXPLICITLY waived: a
    blank waiver saves the operator from writing X and produces a census that
    reads complete while nothing was decided.
    """
    cycle_id = "test-waiver-reason"
    cycle_dir = _fresh_cycle(cycle_id)
    try:
        cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]
        res = subprocess.run(cmd_base + ["waive", cycle_id, "A", "--reason", "   "],
                             cwd=REPO_ROOT, capture_output=True, text=True)
        assert res.returncode == 2, res.stdout
        assert "cannot be empty" in res.stderr

        res = subprocess.run(cmd_base + ["waive", cycle_id, "A", "--reason", "not applicable here"],
                             cwd=REPO_ROOT, capture_output=True, text=True)
        assert res.returncode == 0, res.stdout + res.stderr
        state = json.loads((cycle_dir / "state.json").read_text(encoding="utf-8"))
        assert state["lenses"]["A"]["status"] == "WAIVED"
        assert state["waivers"], "the waiver did not reach the log"
        assert state["waivers"][-1]["reason"] == "not applicable here"
    finally:
        if cycle_dir.exists():
            shutil.rmtree(cycle_dir)

def test_a_missing_closure_cannot_pass_verify() -> None:
    """A lens marked COMPLETED whose report file is gone is a BROKEN closure, not a pass.

    The state says COMPLETED and the tree cannot honour it, so a reader that
    trusts the status alone reports a clean census over a cycle whose evidence
    is absent — the defeated-guard-reported-as-clean class.
    """
    cycle_id = "test-missing-closure"
    cycle_dir = _fresh_cycle(cycle_id)
    try:
        cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]
        reports = cycle_dir / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        report = reports / "lens-A.md"
        report.write_text("A finding, legitimately recorded.\n", encoding="utf-8")
        res = subprocess.run(cmd_base + ["record", cycle_id, "A", str(report)],
                             cwd=REPO_ROOT, capture_output=True, text=True)
        assert res.returncode == 0, res.stdout + res.stderr

        # Break the closure: the status still claims COMPLETED, the bytes are gone.
        report.unlink()
        res = subprocess.run(cmd_base + ["verify", cycle_id], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        assert res.returncode == 1, res.stdout
        assert "file missing" in res.stdout, res.stdout
        assert "census check failed" in res.stdout
    finally:
        if cycle_dir.exists():
            shutil.rmtree(cycle_dir)

def test_migration_maps_the_donor_terminal_synonym(tmp_path: Path) -> None:
    """The donor's `COMPLETE` migrates to `COMPLETED`, so a closed cycle READS as closed.

    Measured on the donor's own tree: its cycle `status` carries SIX distinct
    values (COMPLETED 9, IN_PROGRESS 4, reports_persisted 1, intake_complete 1,
    VALIDATED 1, COMPLETE 1) and its lens entries FOUR (COMPLETED 66, COMPLETE 11,
    PENDING 7, PERSISTED 4). A migration that carries the synonym through
    unmapped leaves a CLOSED cycle reading as an unknown state, and a census that
    then reports 0 completed over a record that says otherwise.
    """
    cycle_id = "test-migrate-synonym"
    cycle_dir = REPO_ROOT / "reviews" / cycle_id
    if cycle_dir.exists():
        shutil.rmtree(cycle_dir)
    cycle_dir.mkdir(parents=True)
    (cycle_dir / "state.json").write_text(json.dumps({
        "cycle_id": cycle_id,
        "status": "COMPLETE",
        "started_at": "2026-09-25T17:24:14Z",
        "ended_at": "2026-09-25T19:00:00Z",
        "lenses": {"A": {"status": "COMPLETE", "verdict": "FINDINGS"},
                   "B": {"status": "COMPLETE", "verdict": "FINDINGS"}},
    }), encoding="utf-8")
    try:
        cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]
        res = subprocess.run(cmd_base + ["migrate", cycle_id], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        assert res.returncode == 0, res.stdout + res.stderr
        assert "status mapped: 'COMPLETE' -> 'COMPLETED'" in res.stdout, res.stdout

        state = json.loads((cycle_dir / "state.json").read_text(encoding="utf-8"))
        assert state["status"] == "COMPLETED", state["status"]
        assert state["lenses"]["A"]["status"] == "COMPLETED", state["lenses"]["A"]

        res = subprocess.run(cmd_base + ["step0", cycle_id], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        assert res.returncode == 0, res.stdout + res.stderr
        assert "2 completed" in res.stdout, res.stdout
        assert "frozen=yes" in res.stdout, res.stdout

        # The pre-image is the donor's own bytes, so nothing was rewritten in place.
        pre = json.loads((cycle_dir / "state.json.pre-v1.bak").read_text(encoding="utf-8"))
        assert pre["status"] == "COMPLETE", "the pre-image is not the donor's own state"
    finally:
        if cycle_dir.exists():
            shutil.rmtree(cycle_dir)

def test_migration_reports_values_it_cannot_map(tmp_path: Path) -> None:
    """A terminal value with no measured mapping is REPORTED, never silently absorbed.

    The donor carries `reports_persisted` and a lens `PERSISTED`. Mapping them to
    COMPLETED would over-claim: PERSISTED says a report was WRITTEN, not that the
    lens reached a verdict. So they are carried in and NAMED as unmapped, which is
    the difference between a migration and a rewrite of someone's record.
    """
    cycle_id = "test-migrate-unmapped"
    cycle_dir = REPO_ROOT / "reviews" / cycle_id
    if cycle_dir.exists():
        shutil.rmtree(cycle_dir)
    cycle_dir.mkdir(parents=True)
    (cycle_dir / "state.json").write_text(json.dumps({
        "cycle_id": cycle_id,
        "status": "reports_persisted",
        "lenses": {"J": {"status": "PERSISTED"}},
    }), encoding="utf-8")
    try:
        cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]
        res = subprocess.run(cmd_base + ["migrate", cycle_id], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        assert res.returncode == 0, res.stdout + res.stderr
        assert "UNMAPPED" in res.stdout, res.stdout
        assert "reports_persisted" in res.stdout, res.stdout
        assert "PERSISTED" in res.stdout, res.stdout

        state = json.loads((cycle_dir / "state.json").read_text(encoding="utf-8"))
        assert state["status"] == "reports_persisted", "an unmapped value must be carried, not invented"
        assert state["lenses"]["J"]["status"] == "PERSISTED"
    finally:
        if cycle_dir.exists():
            shutil.rmtree(cycle_dir)

def test_a_migrated_record_renders_without_a_recorded_digest(tmp_path: Path) -> None:
    """A donor cycle carries report PATHS and NO digest, and `status` must render it.

    Measured on the donor's own c24 record: every lens entry carries `report_path`
    with `sha256` absent, because the donor never recorded one. `status` indexed
    the missing value directly and raised `TypeError: 'NoneType' object is not
    subscriptable`, so a migrated cycle crashed on the FIRST read — on the replay
    leg that exists precisely to read donor data. The render now names the absence
    (`unrecorded`) rather than crashing on it or inventing a digest, because a
    digest nobody computed is a verification claim nobody made.
    """
    cycle_id = "test-migrate-no-digest"
    cycle_dir = REPO_ROOT / "reviews" / cycle_id
    if cycle_dir.exists():
        shutil.rmtree(cycle_dir)
    cycle_dir.mkdir(parents=True)
    (cycle_dir / "state.json").write_text(json.dumps({
        "cycle_id": cycle_id,
        "status": "COMPLETED",
        "started_at": "2026-09-25T17:24:14Z",
        "ended_at": "2026-09-25T19:00:00Z",
        "lenses": {"A": {"status": "COMPLETED", "report_path": "reports/lens-A.md",
                         "verdict": "FINDINGS"}},
    }), encoding="utf-8")
    try:
        cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]
        res = subprocess.run(cmd_base + ["status", cycle_id], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        # The defect was a CRASH, not the exit code: `status` returns 1 for any
        # cycle with a pending lens, so rc alone cannot tell a crash from an
        # incomplete cycle. Assert the two properties that can.
        assert "unrecorded" in res.stdout, res.stdout
        assert "Traceback" not in res.stderr, res.stderr
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
    test_intake_refuses_with_no_declarations()
    test_intake_is_read_only_over_member_data(Path("/tmp"))
    test_intake_names_empty_and_incomplete()
    test_intake_refuses_a_declared_channel_that_is_absent(Path("/tmp"))
    test_intake_receipts_validate_against_the_schema()
    test_shipped_executable_carries_no_donor_tokens()
    test_step0_recovery_reads_state_alone_and_records_durable_evidence()
    test_frozen_cycle_refuses_a_live_channel_read()
    test_a_lens_waiver_requires_a_named_reason()
    test_a_missing_closure_cannot_pass_verify()
    test_migration_maps_the_donor_terminal_synonym(Path("/tmp"))
    test_migration_reports_values_it_cannot_map(Path("/tmp"))
    test_a_migrated_record_renders_without_a_recorded_digest(Path("/tmp"))
    print("ALL TESTS PASSED")
