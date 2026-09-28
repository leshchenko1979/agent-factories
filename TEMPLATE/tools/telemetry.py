#!/usr/bin/env python3
"""Telemetry & Cost Extraction Tool.

Extracts token and dollar cost economics from the agent runtime substrate
(OpenCrabs SQLite database or usage ledger) for precise task attribution
and deterministic derivation of unit economics (cost per successful task).

Usage:
  python3 tools/telemetry.py --subject "#29"
  python3 tools/telemetry.py --start 2026-09-17T09:00:00Z
  python3 tools/telemetry.py --session 2646d31a-71ee-49f0-be81-9c8dc32d32fa --start-epoch 1789632000
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

# THE QUERY BUDGET, WITH ITS MEASURED BASIS (#213's upstream half).
# The windowed aggregate below scans `messages` because `created_at` carries no index
# (the only indexes are the rowid autoindex and `idx_messages_session_id`). Measured
# 2026-09-28 on 77,125 rows, same plan throughout:
#     1 h window -> 91.8 s      1 d -> 88.2 s      7 d -> 106.1 s
# The cost is the SCAN, not the window: a one-hour range costs what a week costs, so
# narrowing the range does not help and only a declared budget bounds it.
#
# WHY IT MUST BE BOUNDED AT ALL. `close` calls this while holding the ledger append
# lock, and the CALLER's budget is 120 s (the harness's bash timeout). An unbounded
# query therefore made the append exceed the caller's budget WHILE COMPLETING
# SERVER-SIDE, so the caller read the timeout as "the write did not happen" and
# retried -- writing a duplicate pair each time (measured: n=1502/1504 and
# n=1509/1511, byte-equivalent, and `verify` returns rc=0 over both because nothing
# checks uniqueness on (event, subject)).
#
# The value is a DECLARED MULTIPLE of the measured worst case: 30 s is 0.28x of the
# 106.1 s measurement, so on the measured population the query is cut off and the row
# ships the STATED ABSENCE `telemetry=unavailable` (#130) rather than a row of zeros
# (which would read as a measurement of nothing) or a caller timeout (which reads as a
# failed write). Declared, not derived: a budget the instrument cannot state is a
# budget no reader can check.
def _budget_secs(default: float = 30.0) -> float:
    """The declared budget, or `default` when the environment states none usable.

    `OC_TELEMETRY_BUDGET_S` exists so a factory can tune the bound to ITS measured
    runtime -- the law doc's principle is that a budget is a DECLARED multiple of a
    measurement, and this box's 106.1 s worst case is not every box's. A malformed or
    non-positive value falls back to the default rather than raising: this module is
    imported on the LEDGER APPEND path, so a crash here would refuse a write for a
    reason that has nothing to do with the row being written.
    """
    raw = os.environ.get("OC_TELEMETRY_BUDGET_S")
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default

TELEMETRY_QUERY_BUDGET_SEC = _budget_secs()


def find_database_path() -> Path | None:
    """Locate the active OpenCrabs SQLite database."""
    env_db = os.environ.get("OPENCRABS_DB_PATH")
    if env_db:
        p = Path(env_db)
        if p.is_file():
            return p

    profile = os.environ.get("OPENCRABS_PROFILE", "ops")
    candidates = [
        Path.home() / f".opencrabs/profiles/{profile}/opencrabs.db",
        Path.home() / ".opencrabs/profiles/ops/opencrabs.db",
        Path.home() / ".opencrabs/opencrabs.db",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def parse_timestamp_to_epoch(ts: str | int | float | None) -> int:
    """Convert ISO timestamp string or epoch number to integer epoch seconds."""
    if ts is None:
        return 0
    if isinstance(ts, (int, float)):
        return int(ts)
    ts_str = str(ts).strip()
    if ts_str.isdigit():
        return int(ts_str)
    try:
        # Replace Z with +00:00 for ISO parsing
        dt = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except Exception:
        return 0


def extract_window_telemetry(
    db_path: Path | None = None,
    session_id: str | None = None,
    start_epoch: int = 0,
    end_epoch: int | None = None,
) -> dict[str, Any]:
    """Query telemetry incurred between start_epoch and end_epoch from SQLite."""
    if end_epoch is None:
        end_epoch = int(datetime.datetime.now(datetime.timezone.utc).timestamp())

    if db_path is None:
        db_path = find_database_path()

    default_result: dict[str, Any] = {
        "cost_usd": 0.0,
        "tokens_in": 0,
        "tokens_out": 0,
        "turns": 0,
        "duration_sec": max(0, end_epoch - start_epoch),
        "db_found": False,
        "session_id": session_id,
        "start_epoch": start_epoch,
        "end_epoch": end_epoch,
    }

    if not db_path or not db_path.is_file():
        return default_result

    # DEFINED BEFORE THE TRY: the handler's except branch reads it, and a failure inside
    # `connect` itself (a vanished file, a stale `-wal`) must not raise NameError from
    # the handler that exists to make failures legible.
    _budget_exceeded = False

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        # THE BOUND (#213). A progress handler returning non-zero aborts the running
        # statement; sqlite3 raises OperationalError('interrupted'), which the handler
        # flag below turns into the STATED ABSENCE rather than a zeros row.
        _deadline = time.monotonic() + TELEMETRY_QUERY_BUDGET_SEC

        def _budget_check() -> int:
            nonlocal _budget_exceeded
            if time.monotonic() > _deadline:
                _budget_exceeded = True
                return 1
            return 0

        conn.set_progress_handler(_budget_check, 10_000)
        cur = conn.cursor()

        # Query messages table for assistant turns
        where_clauses = ["created_at >= ?", "created_at <= ?"]
        params: list[Any] = [start_epoch, end_epoch]

        if session_id:
            where_clauses.append("session_id = ?")
            params.append(session_id)

        # Check if messages table exists
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages'")
        has_messages = cur.fetchone() is not None

        cost = 0.0
        tokens_in = 0
        tokens_out = 0
        turns = 0

        if has_messages:
            msg_query = f"""
                SELECT 
                    COALESCE(SUM(cost), 0.0),
                    COALESCE(SUM(input_tokens), 0),
                    COALESCE(SUM(token_count), 0),
                    COUNT(*)
                FROM messages 
                WHERE {' AND '.join(where_clauses)} AND role = 'assistant'
            """
            cur.execute(msg_query, params)
            row = cur.fetchone()
            if row:
                cost = float(row[0] or 0.0)
                tokens_in = int(row[1] or 0)
                tokens_out = int(row[2] or 0)
                turns = int(row[3] or 0)

        # Fallback / cross-check with usage_ledger table if messages cost is 0
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='usage_ledger'")
        has_usage = cur.fetchone() is not None
        if has_usage and cost == 0.0:
            usage_query = f"""
                SELECT 
                    COALESCE(SUM(cost), 0.0),
                    COALESCE(SUM(token_count), 0)
                FROM usage_ledger 
                WHERE {' AND '.join(where_clauses)}
            """
            cur.execute(usage_query, params)
            urow = cur.fetchone()
            if urow and urow[0]:
                cost = float(urow[0] or 0.0)
                if tokens_out == 0:
                    tokens_out = int(urow[1] or 0)

        conn.close()

        return {
            "cost_usd": round(cost, 4),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "turns": turns,
            "duration_sec": max(0, end_epoch - start_epoch),
            "db_found": True,
            "session_id": session_id,
            "start_epoch": start_epoch,
            "end_epoch": end_epoch,
        }
    except sqlite3.OperationalError as e:
        # A CUT-OFF QUERY IS A STATED ABSENCE, NEVER A ZEROS ROW (#130). The five keys
        # in `default_result` are the aggregate over NOTHING, and a consumer that reads
        # them as a measurement of a window that was actually measured would be reading
        # a fabrication -- exactly the class `now - 300` was removed for. The flag lets
        # `extract_task_telemetry` return None, which every call site already renders as
        # `telemetry=unavailable`.
        if _budget_exceeded:
            default_result["budget_exceeded"] = True
            default_result["db_found"] = True
            return default_result
        default_result["error"] = str(e)
        return default_result
    except Exception as e:
        default_result["error"] = str(e)
        return default_result


def extract_task_telemetry(
    subject: str,
    ledger_path: Path | None = None,
    session_id: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any] | None:
    """Find claim time for subject in ledger and compute delta telemetry to now.

    Returns None when there is no window BASIS: no ledger file, no `claim` row for the
    subject, or an unparseable claim timestamp. None is the STATED absence (#130) --
    every call site renders it as `telemetry=unavailable`, never as a window.
    """
    if ledger_path is None:
        ledger_path = REPO_ROOT / "evidence/ledger.jsonl"

    start_epoch = 0
    if ledger_path.is_file():
        try:
            with open(ledger_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                        if row.get("subject") == subject and row.get("event") == "claim":
                            start_epoch = parse_timestamp_to_epoch(row.get("ts"))
                    except Exception:
                        pass
        except Exception:
            pass

    # NO CLAIM ROW, NO WINDOW (#130, HQ ruling part 3). This branch used to substitute
    # `now - 300` for a window it had never measured, so a close row whose subject had
    # no `claim` row shipped `duration=300s` -- a CONSTANT that every consumer read as a
    # measurement. Same class as #129 one level up: a silent absence read as a value.
    # The repair is the same shape: STATE the absence in #129's spelling rather than
    # manufacture a number. Returning None lets every call site render
    # `telemetry=unavailable`, and a reader can then tell "nothing was measured" from
    # "a measurement was taken and its value is zero" -- which `now - 300` could not.
    if start_epoch == 0:
        return None

    result = extract_window_telemetry(
        db_path=db_path,
        session_id=session_id,
        start_epoch=start_epoch,
    )
    # A CUT-OFF QUERY IS THE STATED ABSENCE, NOT A MEASUREMENT (#213, same shape as #130).
    # `extract_window_telemetry` returns the zeros default when the budget aborts the
    # scan; passing it up would ship `duration=Ns turns=0 cost_usd=0.0000` -- a row that
    # reads as a measured window of nothing. Returning None instead makes every call site
    # render `telemetry=unavailable`, so a reader can distinguish "the window was never
    # measured" from "it was measured and came back zero".
    if result.get("budget_exceeded"):
        return None
    return result


def format_detail_string(telemetry: dict[str, Any] | None, outcome: str = "accepted", gate: str = "all-pass") -> str:
    """Format key-value detail string suitable for ledger close rows.

    None is the extractor's "no window basis" return (#130); it renders as the STATED
    absence `telemetry=unavailable`, never as a row of zeros -- zeros would read as a
    measurement of nothing.
    """
    if telemetry is None:
        return "telemetry=unavailable"

    duration = telemetry.get("duration_sec", 0)
    turns = telemetry.get("turns", 0)
    cost = telemetry.get("cost_usd", 0.0)
    t_in = telemetry.get("tokens_in", 0)
    t_out = telemetry.get("tokens_out", 0)

    parts = [
        f"duration={duration}s",
        f"turns={turns}",
        f"cost_usd={cost:.4f}",
        f"tokens_in={t_in}",
        f"tokens_out={t_out}",
        f"outcome={outcome}",
        f"gate={gate}",
        # PROVENANCE, CARRIED (#130, HQ ruling part 2). The five keys above are
        # TOOL-OWNED: a consumer must be able to tell a value the tool TOOK from one an
        # author TYPED, and no structural read of a row can make that distinction -- HQ
        # measured all three candidate predicates (position, completeness, value
        # equality) and each failed. So the WRITER states it. `telemetry=` is the field
        # #129 introduced for the absence case; `measured` is its second value.
        "telemetry=measured",
    ]
    return " ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", help="Task subject (e.g. '#29') to compute delta since claim")
    parser.add_argument("--session", help="Filter by session UUID")
    parser.add_argument("--start", help="Start ISO timestamp (e.g. 2026-09-17T09:00:00Z)")
    parser.add_argument("--end", help="End ISO timestamp")
    parser.add_argument("--start-epoch", type=int, help="Start epoch timestamp in seconds")
    parser.add_argument("--end-epoch", type=int, help="End epoch timestamp in seconds")
    parser.add_argument("--format", choices=["json", "detail"], default="json", help="Output format")
    parser.add_argument("--outcome", default="accepted", help="Outcome for detail format")
    parser.add_argument("--gate", default="all-pass", help="Gate summary for detail format")

    args = parser.parse_args()

    start_epoch = args.start_epoch or parse_timestamp_to_epoch(args.start)
    end_epoch = args.end_epoch or (parse_timestamp_to_epoch(args.end) if args.end else None)

    if args.subject:
        res = extract_task_telemetry(args.subject, session_id=args.session)
    else:
        res = extract_window_telemetry(
            session_id=args.session,
            start_epoch=start_epoch,
            end_epoch=end_epoch,
        )

    if args.format == "detail":
        print(format_detail_string(res, outcome=args.outcome, gate=args.gate))
    elif res is None:
        # #130: the extractor's stated absence, in the same spelling the detail form
        # uses, so `--format json` cannot print a bare `null` that reads as data.
        print(json.dumps({"telemetry": "unavailable"}))
    else:
        print(json.dumps(res, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
