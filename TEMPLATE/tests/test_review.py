#!/usr/bin/env python3
"""Tests for the Multi-Lens Review Engine (tools/review.py / P32)."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_review_lifecycle(tmp_path: Path) -> None:
    # Use isolated test directory
    cycle_id = "test-cycle-01"
    cmd_base = [sys.executable, str(REPO_ROOT / "tools" / "review.py")]

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


if __name__ == "__main__":
    test_review_lifecycle(Path("/tmp"))
    print("ALL TESTS PASSED")
