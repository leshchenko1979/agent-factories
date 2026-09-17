#!/usr/bin/env python3
"""Tests for tools/telemetry.py — cost extraction & telemetry window computation."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.telemetry import (
    extract_task_telemetry,
    extract_window_telemetry,
    find_database_path,
    format_detail_string,
    parse_timestamp_to_epoch,
)


def create_mock_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE messages (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            role TEXT,
            content TEXT,
            sequence INTEGER,
            created_at INTEGER,
            token_count INTEGER,
            cost REAL,
            input_tokens INTEGER,
            thinking INTEGER,
            cache_creation_tokens INTEGER,
            cache_read_tokens INTEGER,
            duration_secs REAL
        );
    """)
    cur.execute("""
        CREATE TABLE usage_ledger (
            id INTEGER PRIMARY KEY,
            session_id TEXT,
            model TEXT,
            token_count INTEGER,
            cost REAL,
            created_at INTEGER,
            provider TEXT
        );
    """)

    # Insert test rows
    # Window: 1000..2000
    cur.execute("""
        INSERT INTO messages (id, session_id, role, created_at, token_count, cost, input_tokens)
        VALUES 
            ('m1', 'sess-1', 'assistant', 1200, 150, 0.015, 500),
            ('m2', 'sess-1', 'assistant', 1500, 250, 0.025, 800),
            ('m3', 'sess-2', 'assistant', 1600, 100, 0.010, 300),
            ('m4', 'sess-1', 'user', 1400, 50, 0.0, 50),
            ('m5', 'sess-1', 'assistant', 2500, 300, 0.030, 900);
    """)
    conn.commit()
    conn.close()


def test_timestamp_parsing() -> None:
    assert parse_timestamp_to_epoch(12345) == 12345
    assert parse_timestamp_to_epoch("12345") == 12345
    assert parse_timestamp_to_epoch("2026-09-17T09:00:00Z") > 0
    assert parse_timestamp_to_epoch(None) == 0


def test_window_telemetry_extraction() -> None:
    with tempfile.TemporaryDirectory() as td:
        db_file = Path(td) / "test.db"
        create_mock_db(db_file)

        # Query all sessions in window 1000..2000
        res = extract_window_telemetry(db_path=db_file, start_epoch=1000, end_epoch=2000)
        assert res["db_found"] is True
        assert res["cost_usd"] == 0.05  # 0.015 + 0.025 + 0.010
        assert res["tokens_in"] == 1600  # 500 + 800 + 300
        assert res["tokens_out"] == 500  # 150 + 250 + 100
        assert res["turns"] == 3  # 3 assistant messages

        # Query specific session 'sess-1'
        res_sess = extract_window_telemetry(db_path=db_file, session_id="sess-1", start_epoch=1000, end_epoch=2000)
        assert res_sess["cost_usd"] == 0.04  # 0.015 + 0.025
        assert res_sess["tokens_in"] == 1300  # 500 + 800
        assert res_sess["tokens_out"] == 400  # 150 + 250
        assert res_sess["turns"] == 2


def test_task_telemetry_with_mock_ledger() -> None:
    with tempfile.TemporaryDirectory() as td:
        db_file = Path(td) / "test.db"
        create_mock_db(db_file)

        ledger_file = Path(td) / "ledger.jsonl"
        with open(ledger_file, "w") as f:
            f.write(json.dumps({
                "n": 1,
                "ts": "1970-01-01T00:16:40Z",  # Epoch 1000
                "event": "intake",
                "actor": "triage",
                "subject": "#101",
                "detail": "test task"
            }) + "\n")
            f.write(json.dumps({
                "n": 2,
                "ts": "1970-01-01T00:16:40Z",  # Epoch 1000
                "event": "claim",
                "actor": "worker",
                "subject": "#101",
                "detail": "claimed task"
            }) + "\n")

        res = extract_task_telemetry("#101", ledger_path=ledger_file, db_path=db_file)
        assert res["db_found"] is True
        assert res["cost_usd"] >= 0.05


def test_format_detail_string() -> None:
    mock_data = {
        "duration_sec": 120,
        "turns": 3,
        "cost_usd": 0.0450,
        "tokens_in": 1200,
        "tokens_out": 450,
    }
    s = format_detail_string(mock_data, outcome="accepted", gate="all-pass")
    assert "duration=120s" in s
    assert "turns=3" in s
    assert "cost_usd=0.0450" in s
    assert "tokens_in=1200" in s
    assert "tokens_out=450" in s
    assert "outcome=accepted" in s
    assert "gate=all-pass" in s


if __name__ == "__main__":
    test_timestamp_parsing()
    test_window_telemetry_extraction()
    test_task_telemetry_with_mock_ledger()
    test_format_detail_string()
    print("telemetry tests clean: all assertions passed")
