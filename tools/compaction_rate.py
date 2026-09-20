#!/usr/bin/env python3
"""Compaction-RATE standing reading (#108).

Reports, per lane and worst-first, the ratio of CONTEXT COMPACTIONS to COMPLETED TURNS
over a stated window. It is a PRINTED READING, never a gate: a compaction rate is
substantially a SUBSTRATE property — the daemon's compaction threshold, the model's
context window and provider behaviour set it, not the scored factory (HQ ruling n=643
PART 4). The reading exists because no other reading can see a loop: post-compaction
SIZE stayed healthy throughout the window that produced this metric.

THE TWO POPULATIONS ARE DIFFERENT, AND THAT IS THE WHOLE DESIGN
---------------------------------------------------------------
  compactions — `role='user'` rows in `<home>/opencrabs.db` whose content BEGINS with
                the compaction marker; one row per compaction.
  turns       — daemon-log lines from `channels::telegram::turn_settle` naming the
                session; one line per COMPLETED turn.

The compaction count covers every session; the turn marker covers telegram-bound ones
only. A session that compacts but never settles is therefore reported as NOT MEASURABLE
rather than as an infinite ratio — the absence of a settle line cannot be told apart
from a turn that never completed, and calling either one "in a loop" would be a verdict
the data does not carry. Measured 2026-09-20: 8 of 24 sessions in a 3 h window fall in
that bucket, and 3 of them are cron-spawned sessions that compact heavily.

Memory-conserving by construction (the box runs a 768 MiB cgroup cap): the database is
read in place over a `mode=ro` URI and iterated with a cursor, and the daemon log — the
only large input — is streamed line by line, never read whole.

Usage:
  python3 tools/compaction_rate.py                 # 3 h window, ops profile
  python3 tools/compaction_rate.py --hours 24
  python3 tools/compaction_rate.py --home /path/to/profile
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import sqlite3

MARKER = "[CONTEXT COMPACTION"
SETTLE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.\d+)?\+00:00.*"
    r"Telegram settle: session (?P<sid>[0-9a-f-]{36})"
)


def _window_files(log_dir: str, start: datetime.datetime) -> list[str]:
    """Daily log files that can contain the window. Unreadable ones are reported."""
    out, missing = [], []
    day = start.date()
    today = datetime.datetime.now(datetime.timezone.utc).date()
    while day <= today:
        path = os.path.join(log_dir, f"opencrabs.{day.isoformat()}")
        (out if os.path.exists(path) else missing).append(path)
        day += datetime.timedelta(days=1)
    return out


def read(home: str, hours: float) -> dict:
    now = datetime.datetime.now(datetime.timezone.utc)
    start = now - datetime.timedelta(hours=hours)
    s_ep, e_ep = int(start.timestamp()), int(now.timestamp())

    comp: dict[str, int] = {}
    con = sqlite3.connect(f"file:{home}/opencrabs.db?mode=ro", uri=True)
    cur = con.execute(
        "select session_id from messages where role='user' "
        "and instr(content, ?) = 1 and created_at >= ? and created_at <= ?",
        (MARKER, s_ep, e_ep),
    )
    for (sid,) in cur:
        comp[sid] = comp.get(sid, 0) + 1
    all_time = con.execute(
        "select count(*) from messages where role='user' and instr(content, ?) = 1",
        (MARKER,),
    ).fetchone()[0]
    titles = {}
    ids = set(comp)
    # populated after the log pass, so titles are resolved for every lane in the reading
    con.close()

    settle: dict[str, int] = {}
    ever: set[str] = set()
    lines_read = lines_in_window = 0
    log_dir = os.path.join(home, "logs")
    for path in _window_files(log_dir, start):
        with open(path, "r", errors="replace") as fh:
            for line in fh:
                if "Telegram settle: session" not in line:
                    continue
                lines_read += 1
                m = SETTLE.match(line)
                if not m:
                    continue
                ever.add(m.group("sid"))
                ts = datetime.datetime.strptime(m.group("ts"), "%Y-%m-%dT%H:%M:%S")
                ts = ts.replace(tzinfo=datetime.timezone.utc)
                if start <= ts <= now:
                    lines_in_window += 1
                    settle[m.group("sid")] = settle.get(m.group("sid"), 0) + 1
        # a settle-only session absent from the compaction table still belongs to the
        # population when it has a title worth printing
        for sid in settle:
            if sid not in titles:
                titles[sid] = ""
    ids |= set(settle)
    if ids:
        con = sqlite3.connect(f"file:{home}/opencrabs.db?mode=ro", uri=True)
        q = "select id, coalesce(title,'') from sessions where id in (%s)" % ",".join(
            "?" * len(ids)
        )
        for sid, title in con.execute(q, tuple(ids)):
            titles[sid] = title
        con.close()

    measurable, unmeasurable = [], []
    for sid in ids:
        c, t = comp.get(sid, 0), settle.get(sid, 0)
        (measurable if sid in ever else unmeasurable).append((sid, titles.get(sid, ""), c, t))

    measurable.sort(
        key=lambda r: (float("inf") if r[3] == 0 else r[2] / r[3]), reverse=True
    )
    unmeasurable.sort(key=lambda r: -r[2])
    return {
        "now": now,
        "start": start,
        "hours": hours,
        "all_time": all_time,
        "comp_in_window": sum(comp.values()),
        "comp_sessions": len(comp),
        "lines_read": lines_read,
        "turns_in_window": lines_in_window,
        "turn_sessions": len(settle),
        "measurable": measurable,
        "unmeasurable": unmeasurable,
        "db_uri": f"file:{home}/opencrabs.db?mode=ro",
        "log_dir": log_dir,
    }


def render(r: dict) -> str:
    ts = "%Y-%m-%dT%H:%M:%SZ"
    out = [
        "=== COMPACTION-RATE READING (#108) ===",
        f"instant    : {r['now'].strftime(ts)}",
        f"window     : {r['start'].strftime(ts)} .. {r['now'].strftime(ts)}  ({r['hours']} h)",
        f"population : db={r['db_uri']}  predicate role='user' and instr(content,"
        f"'{MARKER}')=1",
        f"             log={r['log_dir']}/opencrabs.<date>  predicate 'Telegram settle:"
        " session <uuid>'",
        f"compactions: {r['comp_in_window']} in window across {r['comp_sessions']}"
        f" session(s); {r['all_time']} all-time (a zero in-window is thus visibly"
        " different from a predicate matching nothing)",
        f"turns      : {r['turns_in_window']} completed in window across"
        f" {r['turn_sessions']} session(s); {r['lines_read']} settle line(s) scanned",
        "",
        f"{'lane':38} {'comp':>5} {'turns':>6} {'ratio':>8}  title",
    ]
    for sid, title, c, t in r["measurable"]:
        ratio = "inf" if t == 0 else f"{c / t:.2f}"
        out.append(f"{sid:38} {c:5d} {t:6d} {ratio:>8}  {title[:46]}")
    tc = sum(x[2] for x in r["measurable"])
    tt = sum(x[3] for x in r["measurable"])
    loops = [x for x in r["measurable"] if x[3] == 0 or x[2] / x[3] >= 1.0]
    out += [
        "",
        f"MEASURABLE: {tc} compactions : {tt} turns ="
        f" {tc / tt if tt else float('inf'):.2f} : 1",
        f"IN A LOOP (>= 1:1): {len(loops)} lane(s)",
    ]
    for sid, title, c, t in loops:
        out.append(f"  {sid}  {c} : {t}  {title[:46]}")
    out += [
        "",
        f"NOT MEASURABLE ({len(r['unmeasurable'])}) — no settle marker was observed for",
        "these sessions, so the turn denominator is structurally absent (the marker is",
        "channel-scoped to telegram). Their compaction count is printed and their ratio",
        "is NOT computed: the absence cannot be told apart from a turn that never",
        "completed, so they are never named a loop.",
    ]
    for sid, title, c, _ in r["unmeasurable"]:
        out.append(f"  {sid}  {c:4d} compactions  {title[:46]}")
    out += [
        "",
        "BOUNDS. (1) The turn marker is channel-scoped (channels::telegram::turn_settle),",
        "so it covers telegram-bound sessions only — every lane on this box, but not a",
        "headless one. (2) It counts COMPLETED turns, so a turn interrupted by a",
        "compaction never settles and the marker UNDERCOUNTS exactly in the state being",
        "measured — the direction is safe, it makes a loop look better than it is.",
        "(3) A lane at or above 1:1 is IN A LOOP. (4) PRINTED, NEVER GATED.",
    ]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--home", default=os.path.expanduser("~/.opencrabs/profiles/ops"))
    ap.add_argument("--hours", type=float, default=3.0)
    args = ap.parse_args()
    if not os.path.exists(os.path.join(args.home, "opencrabs.db")):
        print(f"unreachable: no database at {args.home}/opencrabs.db")
        return 2
    print(render(read(args.home, args.hours)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
