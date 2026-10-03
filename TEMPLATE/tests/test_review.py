#!/usr/bin/env python3
"""Tests for the Multi-Lens Review Engine (tools/review.py / P32)."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The directory the review engine writes cycles into, and it is TRACKED: `reviews/` holds 25
# committed files (two real cycles, `20260917-c1` and `20260927-c1`, and the donor replay
# `rr-donor-replay`). This gate's own probes write TEST cycles beside them and remove them.
REVIEWS_ROOT = REPO_ROOT / "reviews"

# The namespace this gate's probes write in. EVERY cycle id in this file is `test-…`
# (`test-cycle-01`, `test-intake-ro`, `test-migrate-no-digest`, …) and NO real cycle carries
# the prefix — the tracked ids are date-based or a named replay. That is what lets the JANITOR
# below tell a leaked probe dir from a legitimate cycle WITHOUT an allow-list a new test would
# silently escape.
TEST_CYCLE_PREFIX = "test-"


def repair_leaked_cycles(reviews_root: Path | None = None) -> list[str]:
    """JANITOR — remove cycle dirs a KILLED run left under the TRACKED `reviews/` (#293).

    Every test in this file creates `reviews/<test-cycle-id>` and removes it in a `finally`.
    A `finally` survives an exception and does NOT survive a `SIGKILL`, and this box runs a
    documented crash loop (`opencrabs#638`) — so a run killed mid-flight leaves the dir in the
    tree, and the next `git add -A` carries it into a commit. That is the `5b7857a` shape the
    #197 remedy fixed for `docs/factory-registry.md` (`54cc3fc`), and this is the SAME CLASS at
    a larger population: **24 cycle restores**, counted in this file rather than taken from the
    #197 report's 17 (which undercounted) — 23 at the base this issue was filed against
    (`87791dd`), plus one the review-rotation lane added (`f54cdea`) while this remedy was in
    flight. The file now carries 25 `finally` lines and exactly 24 of them are cycle restores —
    the 25th belongs to the janitor's own probe, and it restores a module global, never a cycle.

    **A repair that depends on the process that died is not a repair**, so the restore does not
    live in the probes' `finally` blocks alone: it lives HERE, and the module runs it at the
    START of every run — at MODULE LEVEL, so it fires on BOTH `python3 -m pytest
    tests/test_review.py` (import) and `python3 tests/test_review.py` (script) — before any test
    creates or removes anything. `main()` reports the result on the script path.

    The predicate is EXACT: only entries whose NAME carries `TEST_CYCLE_PREFIX` are removed, so
    a real cycle (`20260917-c1`, `rr-donor-replay`) is never touched however the gate is run.
    An absent `reviews/` — a bootstrapped member that never ran a review — returns an empty list
    with no crash. Returns the names repaired, sorted, so a caller can report them.
    """
    root = REVIEWS_ROOT if reviews_root is None else reviews_root
    if not root.is_dir():
        return []
    repaired: list[str] = []
    for entry in sorted(root.iterdir()):
        if not entry.name.startswith(TEST_CYCLE_PREFIX):
            continue
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()
        repaired.append(entry.name)
    return repaired


# THE JANITOR RUNS AT THE START OF EVERY RUN (#293). Module level, so it PRECEDES every test
# under both invocation modes — a `finally` cannot be relied on because the process it lives in
# is the one the crash loop kills. Captured, so `main()` can REPORT on the script path what a
# killed predecessor left behind rather than re-running into a silent no-op.
_JANITOR_REPAIRED_AT_IMPORT = repair_leaked_cycles()


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


def _known_lens_count() -> int:
    """The lawful lens count, read from the ENGINE -- never hardcoded.

    The core catalogue is 14, but a member may DECLARE lenses of its own at the
    instrument's extension surface (`docs/review-lenses.json`; law doc section 6),
    and a shipped gate that hardcoded 14 would red an adopter for lawfully using the
    surface it was given. `lenses --json` is the ONE reader, so the assertion is made
    against the same set every path folds in.
    """
    res = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "review.py"), "lenses", "--json"],
        cwd=REPO_ROOT, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    return len(json.loads(res.stdout)["known"])

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
        assert len(state["lenses"]) == _known_lens_count()

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

        # 4. Waive the remaining lenses. Iterated from the state rather than from a
        # hardcoded list: a member that DECLARES a lens of its own (law doc section 6)
        # would otherwise leave it PENDING and red the suite for using the surface.
        for lens in state["lenses"]:
            if lens == "A":
                continue
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
        assert len(migrated["lenses"]) == _known_lens_count()
    finally:
        if cycle_dir.exists():
            shutil.rmtree(cycle_dir)


def test_close_sets_both_durations(tmp_path: Path) -> None:
    """`close` writes an explicit terminal state and TWO distinct durations."""
    cycle_id = "test-close-01"
    # A COMPLETED close now requires the census to be complete as well as the plan
    # accounted for, so the fixture runs or waives every lens. This test's subject
    # is the two DURATIONS, which a complete census makes real rather than moot.
    cycle_dir = _lens_clean_cycle(cycle_id)
    cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]
    try:

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

        for lens in state["lenses"]:
            if lens == "A":
                continue
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

def test_intake_dates_the_mandated_instant_form() -> None:
    """An ISO-8601 instant reads DATED — the form this fleet publishes readings in.

    The dating token's trailing guard was `\\b`, which cannot match between the final
    digit of `2026-09-27` and the following `T` because both are word characters. The
    mandated instant form therefore read UNDATED while a bare date read DATED, so every
    adopter who followed the dating discipline had its evidence flagged. The guard is
    `(?!\\d)`: it admits the `T` form and still refuses a partial digit run.
    """
    cycle_id = "test-intake-instant"
    cycle_dir = _fresh_cycle(cycle_id)
    try:
        proposals = cycle_dir / "proposals"
        proposals.mkdir(parents=True, exist_ok=True)
        (proposals / "i1.md").write_text(
            "ADD a rule in docs/x.md#4 BECAUSE it was missing at 2026-09-27T21:26Z.\n",
            encoding="utf-8")
        (proposals / "i2.md").write_text(
            "ADD a rule in docs/y.md#5 BECAUSE the run at 2026-09-271 was broken.\n",
            encoding="utf-8")
        res = subprocess.run([sys.executable, str(REPO_ROOT / "tools" / "review.py"),
                              "intake", cycle_id, "--record"],
                             cwd=REPO_ROOT, capture_output=True, text=True)
        assert res.returncode == 0, res.stdout + res.stderr
        state = json.loads((cycle_dir / "state.json").read_text(encoding="utf-8"))
        dated = {r["id"]: r["dated"] for r in state["proposals"]}
        assert dated["i1"] is True, "the ISO-8601 instant form must read DATED"
        assert dated["i2"] is False, "a partial digit run must stay UNDATED"
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
        assert f"{_known_lens_count()} pending" in res.stdout
        assert "next action" in res.stdout

        res = subprocess.run(cmd_base + ["step0", cycle_id, "--record"], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        assert res.returncode == 0, res.stdout + res.stderr
        state = json.loads((cycle_dir / "state.json").read_text(encoding="utf-8"))
        assert len(state["step0_log"]) == 1, "step0 --record wrote no durable evidence"
        entry = state["step0_log"][0]
        assert entry["pending"] == _known_lens_count() and entry["frozen"] is False
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
    # Same reason as test_close_sets_both_durations: its subject is the FREEZE and
    # the live-read refusal, and reaching COMPLETED now requires a complete census.
    cycle_dir = _lens_clean_cycle(cycle_id)
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

def test_the_donor_lens_key_rename_is_mapped_and_named(tmp_path: Path) -> None:
    """The donor renames a lens-entry KEY, and the rename must be MAPPED and NAMED.

    Measured over the donor's 88 lens entries: the key shapes are
    `(report_path, status, verdict)` 73, `(path, status)` 11, `(findings_count,
    report_path, status)` 4 — so eleven entries name the report with `path`, and
    `sha256` is present in ZERO of the 88.

    Two distinct failures ride on this, and neither is a crash:
      * the migration's key filter keeps only keys the TEMPLATE has, so `path` was
        DROPPED — eleven donor lenses arrived carrying no report at all; and
      * the render read `report_path` alone, so a raw donor record printed `None`
        for a lens whose report exists — a WRONG value, which is worse than a
        crash because nothing looks broken.
    """
    cycle_id = "test-lens-key-rename"
    cycle_dir = REPO_ROOT / "reviews" / cycle_id
    if cycle_dir.exists():
        shutil.rmtree(cycle_dir)
    cycle_dir.mkdir(parents=True)
    (cycle_dir / "state.json").write_text(json.dumps({
        "cycle_id": cycle_id,
        "status": "COMPLETED",
        "started_at": "2026-09-14T00:00:00Z",
        "ended_at": "2026-09-14T01:00:00Z",
        # The donor's renamed shape, and a key with no home in the schema.
        "lenses": {"A": {"path": "reports/lens-A.md", "status": "COMPLETED"},
                   "C": {"report_path": "reports/lens-C.md", "status": "COMPLETED",
                         "findings_count": 3}},
    }), encoding="utf-8")
    try:
        cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]

        # (1) A RAW donor record still renders its report path — no migration required.
        res = subprocess.run(cmd_base + ["status", cycle_id], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        assert "reports/lens-A.md" in res.stdout, res.stdout
        assert "Lens A -> None" not in res.stdout, res.stdout

        # (2) The migration MAPS the rename and NAMES it, and NAMES what it dropped.
        res = subprocess.run(cmd_base + ["migrate", cycle_id], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        assert res.returncode == 0, res.stdout + res.stderr
        assert "'path' -> 'report_path'" in res.stdout, res.stdout
        assert "'findings_count'" in res.stdout, res.stdout

        # (3) The migrated entry CARRIES the path under the schema's own key.
        state = json.loads((cycle_dir / "state.json").read_text(encoding="utf-8"))
        assert state["lenses"]["A"]["report_path"] == "reports/lens-A.md", state["lenses"]["A"]
        assert "path" not in state["lenses"]["A"], "the renamed key must not survive beside it"
    finally:
        if cycle_dir.exists():
            shutil.rmtree(cycle_dir)

def _lens_clean_cycle(cycle_id: str) -> Path:
    """A cycle whose LENS half already passes verify, so a plan gap is the only thing left to fail.

    Records lens A with a real report and waives every other catalogued lens with
    a named reason. The point of the helper is separation: an assertion about the
    codification plan must not be able to pass or fail on the census half.
    """
    cycle_dir = _fresh_cycle(cycle_id)
    cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]
    res = subprocess.run(cmd_base + ["record", cycle_id, "A", "# Lens A\n\nA finding worth landing.\n"],
                         cwd=REPO_ROOT, capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr
    state = json.loads((cycle_dir / "state.json").read_text(encoding="utf-8"))
    for lens in state["lenses"]:
        if lens == "A":
            continue
        res = subprocess.run(cmd_base + ["waive", cycle_id, lens, "--reason", "test waiver"],
                             cwd=REPO_ROOT, capture_output=True, text=True)
        assert res.returncode == 0, res.stdout + res.stderr
    res = subprocess.run(cmd_base + ["verify", cycle_id], cwd=REPO_ROOT,
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr
    return cycle_dir


def _set_plan(cycle_dir: Path, plan: list) -> None:
    f = cycle_dir / "state.json"
    state = json.loads(f.read_text(encoding="utf-8"))
    state["codification_plan"] = plan
    f.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def test_an_unlanded_accepted_finding_cannot_complete_the_cycle() -> None:
    """The schema's own sentence, enforced: an accepted finding with no landed home is a FAILURE.

    Declared at `codification_plan` in the schema since the engine shipped, and
    read by nothing until this arm existed — so a cycle could report COMPLETED
    over a finding that went nowhere. That is the defeated-guard class: the
    contract was written down, measured, and never carried by a mechanism.
    """
    cycle_id = "test-plan-unlanded"
    cycle_dir = _lens_clean_cycle(cycle_id)
    try:
        cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]
        _set_plan(cycle_dir, [{"finding": "the plan carrier is untested",
                               "disposition": "landed", "home": None}])

        # (1) verify FAILS and NAMES the finding — a bare count is not a refusal.
        res = subprocess.run(cmd_base + ["verify", cycle_id], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        assert res.returncode == 1, res.stdout
        assert "UNLANDED" in res.stdout, res.stdout
        assert "the plan carrier is untested" in res.stdout, res.stdout

        # (2) A success close is REFUSED.
        res = subprocess.run(cmd_base + ["close", cycle_id, "--status", "COMPLETED"],
                             cwd=REPO_ROOT, capture_output=True, text=True)
        assert res.returncode == 1, res.stdout + res.stderr
        assert "cannot close COMPLETED" in res.stderr, res.stderr

        # (3) ABANDONED stays legal. Refusing it would trap a cycle that cannot
        # complete in IN_PROGRESS forever, which is worse than the pass it prevents.
        res = subprocess.run(cmd_base + ["close", cycle_id, "--status", "ABANDONED"],
                             cwd=REPO_ROOT, capture_output=True, text=True)
        assert res.returncode == 0, res.stdout + res.stderr
    finally:
        if cycle_dir.exists():
            shutil.rmtree(cycle_dir)


def test_a_landed_finding_and_a_recorded_non_fix_are_lawful() -> None:
    """The three dispositions the schema enumerates, each with its carrier, all pass.

    `rejected` with a reason is the recorded non-fix and stays legal — that is the
    narrower reading of the open owner question F5, and this arm is where that
    reading is pinned rather than left to prose. `routed` owes a home too: a route
    with no destination is indistinguishable from a drop.
    """
    cycle_id = "test-plan-lawful"
    cycle_dir = _lens_clean_cycle(cycle_id)
    try:
        cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]
        lawful = [
            {"finding": "landed here", "disposition": "landed",
             "home": "docs/instruments/review-rotation.md §7 (self-probe and non-vacuity)"},
            {"finding": "routed onward", "disposition": "routed",
             "home": "session 4515ea72 (Instruments methodology)"},
            {"finding": "not adopted", "disposition": "rejected",
             "reason": "covered by an existing clause; restating it would split the rule"},
        ]
        _set_plan(cycle_dir, lawful)
        res = subprocess.run(cmd_base + ["verify", cycle_id], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        assert res.returncode == 0, res.stdout + res.stderr
        assert "3 accepted finding(s), all accounted for" in res.stdout, res.stdout

        # A routed finding WITHOUT its destination is the same gap as an unlanded
        # one — the obligation travels with the disposition, not with the wording.
        _set_plan(cycle_dir, [dict(lawful[1], home=None)])
        res = subprocess.run(cmd_base + ["verify", cycle_id], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        assert res.returncode == 1, res.stdout
        assert "routed" in res.stdout and "owes a home" in res.stdout, res.stdout

        # A rejected finding without its reason is not a recorded non-fix, it is a
        # silent one.
        _set_plan(cycle_dir, [dict(lawful[2], reason=None)])
        res = subprocess.run(cmd_base + ["verify", cycle_id], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        assert res.returncode == 1, res.stdout
        assert "owes a reason" in res.stdout, res.stdout

        # An unclassified disposition is a gap, never a default.
        _set_plan(cycle_dir, [{"finding": "maybe", "disposition": "deferred-to-later"}])
        res = subprocess.run(cmd_base + ["verify", cycle_id], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        assert res.returncode == 1, res.stdout
        assert "is not one of" in res.stdout, res.stdout
    finally:
        if cycle_dir.exists():
            shutil.rmtree(cycle_dir)


def test_an_empty_plan_is_not_a_gap() -> None:
    """A cycle that accepted no findings owes no landing — the gate must not invent one.

    This is the arm that keeps the enforcement honest in the other direction: a
    check that fails on an absent plan would read every clean cycle as broken,
    and a gate that cannot pass is not a gate.
    """
    cycle_id = "test-plan-empty"
    cycle_dir = _lens_clean_cycle(cycle_id)
    try:
        cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]
        for plan in ([], None):
            _set_plan(cycle_dir, plan if plan is not None else [])
            res = subprocess.run(cmd_base + ["verify", cycle_id], cwd=REPO_ROOT,
                                 capture_output=True, text=True)
            assert res.returncode == 0, f"plan={plan!r} -> {res.stdout}{res.stderr}"
        res = subprocess.run(cmd_base + ["close", cycle_id, "--status", "COMPLETED"],
                             cwd=REPO_ROOT, capture_output=True, text=True)
        assert res.returncode == 0, res.stdout + res.stderr
    finally:
        if cycle_dir.exists():
            shutil.rmtree(cycle_dir)


def test_codify_records_a_finding_and_refuses_a_carrier_less_one() -> None:
    """The WRITER the enforcement needs — without it the gate watches an empty field.

    `codification_plan` had a reader (verify, close) and no writer at all, so the
    field stayed at the empty list `_empty_state` seeds and a carrier check over it
    would have read green forever. This arm pins both halves: the refusal happens
    at WRITE time (where the operator still has the finding in hand) and the
    lawful form records a plan entry that verify then accepts.
    """
    cycle_id = "test-codify-writer"
    cycle_dir = _lens_clean_cycle(cycle_id)
    try:
        cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]

        res = subprocess.run(cmd_base + ["codify", cycle_id, "--finding", "F1", "--disposition", "landed"],
                             cwd=REPO_ROOT, capture_output=True, text=True)
        assert res.returncode == 2, res.stdout + res.stderr
        assert "owes a home" in res.stderr, res.stderr

        res = subprocess.run(cmd_base + ["codify", cycle_id, "--finding", "F1", "--disposition", "rejected",
                                         "--home", "somewhere"],
                             cwd=REPO_ROOT, capture_output=True, text=True)
        assert res.returncode == 2, res.stdout + res.stderr
        assert "owes a reason" in res.stderr, res.stderr

        res = subprocess.run(cmd_base + ["codify", cycle_id, "--finding", "   ", "--disposition", "rejected",
                                         "--reason", "no"],
                             cwd=REPO_ROOT, capture_output=True, text=True)
        assert res.returncode == 2, res.stdout + res.stderr
        assert "cannot be empty" in res.stderr, res.stderr

        for disp, flag, val in (("landed", "--home", "docs/x.md §1"),
                                ("routed", "--home", "session 4515ea72"),
                                ("rejected", "--reason", "covered by an existing clause")):
            res = subprocess.run(cmd_base + ["codify", cycle_id, "--finding", f"F-{disp}",
                                             "--disposition", disp, flag, val],
                                 cwd=REPO_ROOT, capture_output=True, text=True)
            assert res.returncode == 0, res.stdout + res.stderr
        state = json.loads((cycle_dir / "state.json").read_text(encoding="utf-8"))
        assert len(state["codification_plan"]) == 3, state["codification_plan"]
        assert "codification_log" not in state, "a second home for findings is the two-homes defect"

        res = subprocess.run(cmd_base + ["verify", cycle_id], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        assert res.returncode == 0, res.stdout + res.stderr
        assert "3 accepted finding(s), all accounted for" in res.stdout, res.stdout

        res = subprocess.run(cmd_base + ["close", cycle_id, "--status", "COMPLETED"],
                             cwd=REPO_ROOT, capture_output=True, text=True)
        assert res.returncode == 0, res.stdout + res.stderr
        res = subprocess.run(cmd_base + ["codify", cycle_id, "--finding", "late", "--disposition",
                                         "rejected", "--reason", "too late"],
                             cwd=REPO_ROOT, capture_output=True, text=True)
        assert res.returncode == 2, res.stdout + res.stderr
        assert "FROZEN" in res.stderr, res.stderr
    finally:
        if cycle_dir.exists():
            shutil.rmtree(cycle_dir)


def test_close_completed_is_refused_while_the_census_is_incomplete() -> None:
    """The completion formula the donor's own law names: a census, not a timestamp.

    Measured before this arm existed: a cycle with all 14 lenses PENDING closed
    COMPLETED (rc=0) and froze — `verify` failed while `close` returned success,
    so the census apparatus was advisory. This is the worse of the two
    completion gaps because it needs no mistake: a lane that never ran the
    review reached the same terminal state as one that ran it clean.
    """
    cycle_id = "test-census-gate"
    cycle_dir = _fresh_cycle(cycle_id)
    try:
        cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]

        # A cycle with nothing run cannot be COMPLETED...
        res = subprocess.run(cmd_base + ["close", cycle_id, "--status", "COMPLETED"],
                             cwd=REPO_ROOT, capture_output=True, text=True)
        assert res.returncode == 1, res.stdout + res.stderr
        assert "neither run nor explicitly waived" in res.stderr, res.stderr
        state = json.loads((cycle_dir / "state.json").read_text(encoding="utf-8"))
        assert state["status"] == "IN_PROGRESS", "a refused close must not have moved the status"

        # ...but a WAIVED lens with no reason is a gap too, never a pass.
        res = subprocess.run(cmd_base + ["waive", cycle_id, "A", "--reason", "x"],
                             cwd=REPO_ROOT, capture_output=True, text=True)
        assert res.returncode == 0, res.stdout + res.stderr
        state = json.loads((cycle_dir / "state.json").read_text(encoding="utf-8"))
        state["lenses"]["B"] = {"status": "WAIVED", "reason": "   "}
        (cycle_dir / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        res = subprocess.run(cmd_base + ["close", cycle_id, "--status", "COMPLETED"],
                             cwd=REPO_ROOT, capture_output=True, text=True)
        assert res.returncode == 1, res.stdout + res.stderr
        assert "waived with no reason" in res.stderr, res.stderr

        # ABANDONED stays legal, so a cycle that cannot complete is not trapped.
        res = subprocess.run(cmd_base + ["close", cycle_id, "--status", "ABANDONED"],
                             cwd=REPO_ROOT, capture_output=True, text=True)
        assert res.returncode == 0, res.stdout + res.stderr
    finally:
        if cycle_dir.exists():
            shutil.rmtree(cycle_dir)


def test_a_declared_lens_extends_the_catalogue_without_forking_it(tmp_path: Path) -> None:
    """The declared extension surface: a member ADDS a lens, it never forks the core.

    The core catalogue IS the instrument's shape and is centralised (the frame,
    docs/instruments/template-instruments.md §6.4); what a member may do is DECLARE
    its own lenses in `docs/review-lenses.json` (template-instruments.md §6.5). This arm pins the whole
    contract: an addition becomes lawful on EVERY path, a declared id that collides
    with a core letter is DROPPED so the core entry keeps the law that letter
    carries, and an absent declaration leaves the core set standing alone.
    """
    decl = tmp_path / "review-lenses.json"
    decl.write_text(json.dumps({"lenses": [
        {"id": "X-anti", "family": "member", "name": "AntiSpam domain rules",
         "scope": "docs/antispam/*.md", "instructions": "1. check the factory's own domain rules"},
        {"id": "A", "family": "member", "name": "SHOULD NOT WIN",
         "scope": "hijack", "instructions": "hijack"},
    ]}) + "\n", encoding="utf-8")

    env = dict(os.environ, OC_REVIEW_LENSES_PATH=str(decl))
    cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(cmd_base + list(args), cwd=REPO_ROOT, capture_output=True,
                              text=True, env=env)

    # (1) The declaration ADDS exactly one lens; the colliding id is DROPPED.
    res = run("lenses", "--json")
    assert res.returncode == 0, res.stderr
    listed = json.loads(res.stdout)
    assert listed["core"] == ["A", "B", "G", "J", "P", "C", "E", "F", "D", "H", "M", "T", "I", "S"]
    assert listed["declared"] == ["X-ANTI"], listed["declared"]
    assert listed["known"] == listed["core"] + ["X-ANTI"]

    # (2) The declared lens briefs with ITS OWN metadata...
    res = run("brief", "x-anti", "--json")
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout)["name"] == "AntiSpam domain rules"

    # (3) ...and a declared id colliding with a core letter does NOT redefine it.
    res = run("brief", "a", "--json")
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout)["name"] == "Redundancy, Ontology & Provenance Sediment"

    # (4) init MATERIALISES the declared lens, so the cycle's census carries it.
    cycle_id = "test-declared-lens"
    cycle_dir = REPO_ROOT / "reviews" / cycle_id
    try:
        res = run("init", cycle_id)
        assert res.returncode == 0, res.stderr
        state = json.loads((cycle_dir / "state.json").read_text(encoding="utf-8"))
        assert set(state["lenses"]) == set(listed["known"]), sorted(state["lenses"])

        # (5) verify REQUIRES it: a declared lens is not decoration. Waive every
        # lens EXCEPT the declared one and the census still FAILS, naming it.
        for lens in state["lenses"]:
            if lens == "X-ANTI":
                continue
            res = run("waive", cycle_id, lens, "--reason", "test waiver")
            assert res.returncode == 0, res.stderr
        res = run("verify", cycle_id)
        assert res.returncode == 1, res.stdout
        assert "X-ANTI" in res.stdout, res.stdout
    finally:
        if cycle_dir.exists():
            shutil.rmtree(cycle_dir)

    # (6) An ABSENT declaration leaves the core catalogue standing alone -- the
    # field ships before any factory has declared a lens.
    env_absent = dict(os.environ, OC_REVIEW_LENSES_PATH=str(tmp_path / "absent.json"))
    res = subprocess.run(cmd_base + ["lenses", "--json"], cwd=REPO_ROOT,
                         capture_output=True, text=True, env=env_absent)
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout)["declared"] == []


def test_the_shipped_seed_declares_nothing() -> None:
    """The `.example.json` seed ships EMPTY, so an adopter carries no dead vocabulary.

    The frame's extension contract (docs/instruments/template-instruments.md §6.5,
    part 1): the template's copy declares nothing and the manifest tracks it, so a
    factory that declares nothing is the DEFAULT rather than a special case.
    """
    root = REPO_ROOT.parent if REPO_ROOT.name == "TEMPLATE" else REPO_ROOT
    seeds = [root / "docs" / "review-lenses.example.json"]
    template_copy = root / "TEMPLATE" / "docs" / "review-lenses.example.json"
    if template_copy.parent.is_dir():
        seeds.append(template_copy)
    for seed in seeds:
        assert seed.is_file(), seed
        assert json.loads(seed.read_text(encoding="utf-8"))["lenses"] == [], seed


def test_the_janitor_repairs_a_killed_runs_leak() -> None:
    """POSITIVE CONTROL for the JANITOR (#293 acceptance criterion 2), plus its non-vacuity arm.

    Three arms over a SYNTHETIC reviews root, so no real cycle is touched:
      (a) LEAK -> REPAIRED: a dir a killed run left (`test-leak-01/`, payload included) is gone
          after `repair_leaked_cycles()`, payload and all.
      (b) CLEAN -> UNTOUCHED: a real-shaped sibling (`20260917-c1`, no `test-` prefix) survives
          — the predicate is a NAMESPACE, never a blanket sweep of `reviews/`.
      (c) ABSENT -> NO CRASH: a root that does not exist returns `[]` rather than raising.

    The non-vacuity arm (#112) is last: with the predicate NEUTERED the SAME leak survives, so
    arm (a) is shown to bite on the janitor's own code rather than passing by construction. A
    janitor neutered to a no-op reds `main()`, which names this JANITOR.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "reviews"
        root.mkdir()

        # (a) LEAK -> REPAIRED, byte-identically: the dir and its payload are gone.
        leak = root / "test-leak-01"
        (leak / "state.json").parent.mkdir(parents=True, exist_ok=True)
        (leak / "state.json").write_text('{"cycle": "test-leak-01"}', encoding="utf-8")
        assert leak.is_dir(), "fixture: the killed run's leak must exist before the repair"
        repaired = repair_leaked_cycles(root)
        assert repaired == ["test-leak-01"], f"the JANITOR did not name the leak: {repaired}"
        assert not leak.exists(), "the JANITOR left a killed run's cycle dir in reviews/"

        # (b) CLEAN -> UNTOUCHED: a real cycle is outside the janitor's namespace.
        real = root / "20260917-c1"
        (real / "cycle.json").parent.mkdir(parents=True, exist_ok=True)
        (real / "cycle.json").write_text("{}", encoding="utf-8")
        assert repair_leaked_cycles(root) == [], "the JANITOR touched a real cycle dir"
        assert real.is_dir(), "the JANITOR removed a tracked-shaped cycle — predicate too broad"

        # (c) ABSENT -> NO CRASH.
        assert repair_leaked_cycles(Path(tmp) / "no-such-reviews") == [], (
            "the JANITOR crashed or reported a repair on an absent reviews root"
        )

        # NON-VACUITY (#112): neuter the predicate and the SAME leak survives, so arm (a) is
        # proven to bite rather than passing by construction.
        leak2 = root / "test-leak-02"
        leak2.mkdir()
        original_prefix = globals()["TEST_CYCLE_PREFIX"]
        globals()["TEST_CYCLE_PREFIX"] = "zz-never-matches-"
        try:
            assert repair_leaked_cycles(root) == [], (
                "a NEUTERED JANITOR still reported a repair — the predicate is not what bit"
            )
            assert leak2.is_dir(), (
                "the leak vanished with the JANITOR's predicate neutered — arm (a) is vacuous"
            )
        finally:
            globals()["TEST_CYCLE_PREFIX"] = original_prefix


def test_the_next_run_repairs_a_killed_runs_leak() -> None:
    """Criterion 1 — a leak a KILLED run left is repaired by the NEXT run, end to end.

    The probe above calls the janitor directly; this one proves the WIRING. The module-level
    call fires when the gate is LOADED, which is what the next `python3 -m pytest
    tests/test_review.py` or `python3 tests/test_review.py` does. A SYNTHETIC tree carries a
    copy of this file under `tests/` and a `reviews/` root holding BOTH a killed run's leak
    (`test-killed-01/`, payload included) and a real-shaped sibling; a fresh interpreter loads
    the copy, and the leak is gone while the sibling is untouched.

    The probe deliberately does NOT restore the leak in a `finally`: a `finally` does not
    survive a `SIGKILL`, which is the whole reason the janitor exists, and this tree is a
    throwaway so nothing depends on the restore. It asserts on the SUBPROCESS's own exit code
    and output, so a module that failed to import reds rather than reading as a clean repair.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(tmp)
        (tree / "tests").mkdir()
        shutil.copy2(Path(__file__).resolve(), tree / "tests" / "test_review.py")
        root = tree / "reviews"
        leak = root / "test-killed-01"
        (leak / "state.json").parent.mkdir(parents=True, exist_ok=True)
        (leak / "state.json").write_text('{"cycle": "test-killed-01"}', encoding="utf-8")
        sibling = root / "20260927-c1"
        (sibling / "cycle.json").parent.mkdir(parents=True, exist_ok=True)
        (sibling / "cycle.json").write_text("{}", encoding="utf-8")
        assert leak.is_dir(), "fixture: the killed run's leak must be on disk before the next run"

        res = subprocess.run(
            [sys.executable, "-c", _LOAD_AND_JANITOR_SNIPPET,
             str(tree / "tests" / "test_review.py")],
            cwd=tree, capture_output=True, text=True,
        )
        assert res.returncode == 0, (
            "the next run failed to load the gate: " + res.stdout + res.stderr
        )
        assert not leak.exists(), (
            "the NEXT run did not repair the killed run's leak — "
            f"{leak.relative_to(tree)} survived (janitor output: {res.stdout.strip()!r})"
        )
        assert not (leak / "state.json").exists(), "the leak's payload survived the repair"
        assert sibling.is_dir(), (
            "the next run's JANITOR removed a real-shaped cycle beside the leak"
        )


# The fresh-interpreter loader used by `test_the_next_run_repairs_a_killed_runs_leak`. It loads
# the module BY PATH, so the module-level JANITOR fires exactly as it does at the top of a real
# run, and it prints what that call repaired so the caller can see the MECHANISM, not only its
# effect.
_LOAD_AND_JANITOR_SNIPPET = (
    "import importlib.util as _u, sys\n"
    "_p = sys.argv[1]\n"
    "_s = _u.spec_from_file_location('_review_gate_next_run', _p)\n"
    "_m = _u.module_from_spec(_s)\n"
    "_s.loader.exec_module(_m)\n"
    "print('JANITOR repaired on load:', ','.join(_m._JANITOR_REPAIRED_AT_IMPORT) or 'none')\n"
)


def main() -> int:
    print("Tests for the Multi-Lens Review Engine (tools/review.py / P32)")
    print(f"  python {sys.version.split()[0]}")

    # THE JANITOR, before any check or probe (#293). The module-level call already ran it at
    # import — this REPORTS what a killed predecessor left, and re-runs it so a leak introduced
    # between import and here is caught too. A `finally` cannot do this job: the process it
    # lives in is the one the crash loop kills.
    if _JANITOR_REPAIRED_AT_IMPORT:
        print(f"  JANITOR: repaired {len(_JANITOR_REPAIRED_AT_IMPORT)} cycle dir(s) a killed run "
              f"left under reviews/: {', '.join(_JANITOR_REPAIRED_AT_IMPORT)} (#293).")
    else:
        print("  JANITOR: reviews/ carried no leaked test cycle dir (#293).")
    repair_leaked_cycles()

    # THE JANITOR'S POSITIVE CONTROL (#293 acceptance criteria 2 and 3). A failure here reds
    # the run NAMING the janitor, so a janitor neutered to a no-op cannot pass by silence.
    for _probe in (test_the_janitor_repairs_a_killed_runs_leak,
                   test_the_next_run_repairs_a_killed_runs_leak):
        try:
            _probe()
        except AssertionError as exc:
            print(f"  FAIL: JANITOR — {_probe.__name__}: {exc}", file=sys.stderr)
            return 1
    print("  ok: JANITOR — leak repaired, clean untouched, absent safe, next run repairs (#293)")

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
    test_intake_dates_the_mandated_instant_form()
    test_shipped_executable_carries_no_donor_tokens()
    test_step0_recovery_reads_state_alone_and_records_durable_evidence()
    test_frozen_cycle_refuses_a_live_channel_read()
    test_a_lens_waiver_requires_a_named_reason()
    test_a_missing_closure_cannot_pass_verify()
    test_migration_maps_the_donor_terminal_synonym(Path("/tmp"))
    test_migration_reports_values_it_cannot_map(Path("/tmp"))
    test_a_migrated_record_renders_without_a_recorded_digest(Path("/tmp"))
    test_the_donor_lens_key_rename_is_mapped_and_named(Path("/tmp"))
    test_an_unlanded_accepted_finding_cannot_complete_the_cycle()
    test_a_landed_finding_and_a_recorded_non_fix_are_lawful()
    test_an_empty_plan_is_not_a_gap()
    test_codify_records_a_finding_and_refuses_a_carrier_less_one()
    test_close_completed_is_refused_while_the_census_is_incomplete()
    test_a_declared_lens_extends_the_catalogue_without_forking_it(Path("/tmp"))
    test_the_shipped_seed_declares_nothing()
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
