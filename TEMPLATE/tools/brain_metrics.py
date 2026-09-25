#!/usr/bin/env python3
"""brain-metrics standing reading — the static law floor, and the context it is paid in.

Answers three questions in one command, and gates none of them:

  leg A  the always-injected brain files — lines, bytes, md5, share of the floor
  leg B  the factory's own `skills/*/SKILL.md` bodies against the owner's 500-line budget
  leg C  the post-compaction input-token distribution, read from the daemon log
  oracle the live figures BESIDE a DATED snapshot (2026-09-19), with the delta named — a
         snapshot is cited, never re-asserted as current, and a nonzero delta is MOVEMENT
         of the population rather than a regression

WHY THIS EXISTS. `docs/measurement-procedure.md` §5 declares the brain-metrics COMPANION
readings — "the always-injected brain-file line count, and the post-compaction input-token
figure read from the daemon log" — and until this file shipped no mechanism stood behind
them. A declared reading with no instrument is dead text (P29). What the readings describe
is a STATIC FLOOR: bytes paid before a session reads its first message, on every session.

LEG A'S POPULATION IS CITED, NOT INVENTED. It is the Tier 0 triple declared in
`docs/methodology/04-harness-binding.md` — the "Tier 0: Structural Invariants" row, "Core
brain files", names `SOUL.md`, `USER.md`, `AGENTS.md`. A harness that injects a different
set overrides `--brain-files` without editing this code. A named file that is ABSENT is
reported BY NAME — never silently dropped, which would read as a smaller law.

THE UNIT LAW. LINE is the unit for the budget (owner order 2026-09-19: "The threshold is a
LINE count, never bytes or tokens"). Bytes are printed BESIDE lines, never substituted for
them, and a token figure is labelled a PROXY at a stated ratio (3.5 chars/token for English
markdown, 1.7 for Cyrillic) — never presented as a measurement. This is the unit confusion
the ops AGENTS.md records: a limit published in TOKENS encoded as a character cap.

THE COMBINED FIGURE IS THE SUM OF THE PRINTED LEGS, never a second rounding of the summed
bytes. Two rounding paths over one population can disagree by one, and they agree often
enough — the 09-19 pair agrees under both — that the mismatch ships unnoticed.

LEG C'S ONE TRAP, carried here so it cannot be missed: the summarizer line emitted by
`src/brain/agent/service/context.rs` is the ONLY line this leg parses. The trigger line
`Context at NN percent (>65 percent)` emitted by `compaction.rs` uses a DIFFERENT
denominator (effective tokens over effective max, window minus reserves) and must never be
read as a fraction of the provider window.

LEG C'S SECOND TRAP, and the reason the count is not a growth metric: the EVENT COUNT
tracks how many lanes were awake and how many turns they ran, NOT the weight of the law.
Measured over 09-19 → 09-20, the floor GREW while the event count FELL. The floor signal is
the mean/median; the count is printed with that caveat beside it.

PRINTED, NEVER GATED. No threshold in this file fails a run — the owner judges. The only
nonzero exits are a leg that could not be TAKEN (3) and a leg whose in-window population is
EMPTY (4), both of which are failures to read rather than verdicts about the corpus.

Memory-conserving by construction (the box runs a 768 MiB cgroup cap): every file is
streamed line by line, never read whole — today's daemon log is ~109 MB and the log set is
~1.5 GB — and only integers are retained from the log pass.

Usage:
  python3 tools/brain_metrics.py
  python3 tools/brain_metrics.py --home ~/.opencrabs/profiles/ops --hours 24
  python3 tools/brain_metrics.py --log-dir /path/to/logs --window 200000
"""

from __future__ import annotations

import argparse
import datetime
import gzip
import hashlib
import os
import re
from kit_identity import VersionAction

BUDGET_LINES = 500
DEFAULT_WINDOW = 200_000
CHARS_PER_TOKEN = 3.5
CHARS_PER_TOKEN_NOTE = "3.5 chars/token English markdown, 1.7 Cyrillic"
DEFAULT_BRAIN_FILES = ("SOUL.md", "USER.md", "AGENTS.md")
TIER0_LAW = "docs/methodology/04-harness-binding.md (Tier 0: SOUL.md, USER.md, AGENTS.md)"

COMPACTION = re.compile(
    r"Compaction: sending (?P<n>\d+) / (?P<total>\d+) messages to summarizer "
    r"\((?P<input>\d+) / (?P<window>\d+) input tokens, reserving (?P<reserve>\d+) "
    r"for output\)"
)
STAMP = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})")

def _stamp(line: str):
    m = STAMP.match(line)
    if not m:
        return None
    return datetime.datetime.strptime(m.group("ts"), "%Y-%m-%dT%H:%M:%S").replace(
        tzinfo=datetime.timezone.utc
    )

def _iter_lines(path: str):
    """Stream a log file, plain or rotated (`.gz`). Never reads one whole."""
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", errors="replace") as fh:
        for line in fh:
            yield line

def _log_files(log_dir: str) -> list:
    if not os.path.isdir(log_dir):
        return []
    names = sorted(n for n in os.listdir(log_dir) if n.startswith("opencrabs."))
    return [os.path.join(log_dir, n) for n in names]

def _measure(path: str):
    """`(lines, bytes, md5[:8])` — streamed in chunks; the byte count is a stat."""
    writes = 0
    digest = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            writes += chunk.count(b"\n")
            digest.update(chunk)
    size = os.path.getsize(path)
    if size:
        with open(path, "rb") as fh:
            fh.seek(size - 1)
            if fh.read(1) != b"\n":
                # an UNTERMINATED final line is still a line, so the count does not
                # depend on the corpus happening to be newline-terminated
                writes += 1
    return writes, size, digest.hexdigest()[:8]

def leg_a(home: str, names) -> dict:
    out = {
        "leg": "A", "home": home, "names": list(names), "files": [], "missing": [],
        "lines": 0, "bytes": 0, "tokens": 0, "not_run": None,
    }
    if not os.path.isdir(home):
        out["not_run"] = f"no profile home at {home}"
        return out
    for name in names:
        path = os.path.join(home, name)
        if not os.path.isfile(path):
            out["missing"].append(name)
            continue
        lines, size, md5 = _measure(path)
        out["files"].append({"name": name, "lines": lines, "bytes": size, "md5": md5})
        out["lines"] += lines
        out["bytes"] += size
        out["tokens"] += round(size / CHARS_PER_TOKEN)
    out["files"].sort(key=lambda f: -f["lines"])
    return out

def leg_b(repo: str) -> dict:
    root = os.path.join(repo, "skills")
    out = {
        "leg": "B", "root": root, "files": [], "lines": 0, "bytes": 0, "tokens": 0,
        "not_run": None,
    }
    if not os.path.isdir(root):
        out["not_run"] = f"no skills root at {root}"
        return out
    for slug in sorted(os.listdir(root)):
        path = os.path.join(root, slug, "SKILL.md")
        if not os.path.isfile(path):
            continue
        lines, size, md5 = _measure(path)
        out["files"].append(
            {"name": f"skills/{slug}/SKILL.md", "lines": lines, "bytes": size, "md5": md5}
        )
        out["lines"] += lines
        out["bytes"] += size
        out["tokens"] += round(size / CHARS_PER_TOKEN)
    if not out["files"]:
        out["not_run"] = f"no skills/*/SKILL.md under {root}"
    return out

def leg_c(log_dir: str, start, now) -> dict:
    out = {
        "leg": "C", "log_dir": log_dir, "files": 0, "samples": [], "all_time": 0,
        "out_of_window": 0, "not_run": None,
    }
    if not os.path.isdir(log_dir):
        out["not_run"] = f"no log directory at {log_dir}"
        return out
    for path in _log_files(log_dir):
        out["files"] += 1
        for line in _iter_lines(path):
            if "Compaction: sending" not in line:
                continue
            m = COMPACTION.search(line)
            if not m:
                continue
            out["all_time"] += 1
            ts = _stamp(line)
            if ts is None or not (start <= ts <= now):
                out["out_of_window"] += 1
                continue
            out["samples"].append(int(m.group("input")))
    return out

def _dist(samples: list) -> dict:
    ordered = sorted(samples)
    n = len(ordered)
    if n == 0:
        return {"n": 0}
    return {
        "n": n,
        "mean": sum(ordered) // n,
        "median": ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) // 2,
        "p90": ordered[min(n - 1, int(0.90 * n))],
        "min": ordered[0],
        "max": ordered[-1],
    }

def read(args) -> dict:
    now = datetime.datetime.now(datetime.timezone.utc)
    start = now - datetime.timedelta(hours=args.hours)
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    c = leg_c(args.log_dir, start, now)
    return {
        "now": now, "start": start, "hours": args.hours, "window": args.window,
        "a": leg_a(args.home, args.brain_files),
        "b": leg_b(repo),
        "c": c,
        "dist": _dist(c["samples"]),
    }

def render(r: dict) -> str:
    ts = "%Y-%m-%dT%H:%M:%SZ"
    w = r["window"]
    a, b, c = r["a"], r["b"], r["c"]
    out = [
        "=== BRAIN-METRICS STANDING READING ===",
        f"instant    : {r['now'].strftime(ts)}",
        f"window     : {r['start'].strftime(ts)} .. {r['now'].strftime(ts)}  ({r['hours']} h)",
        f"provider window assumed: {w} input tokens",
        "unit law   : LINE is the primary unit; bytes are printed beside it; token figures",
        f"             are a STATED-RATIO PROXY ({CHARS_PER_TOKEN_NOTE}), never a measurement",
        "",
        f"--- LEG A: always-injected brain files @ {r['now'].strftime(ts)} ---",
        "predicate  : every named file exists on disk and is counted by newline (an",
        "             unterminated final line still counts) with its size from stat",
        f"population : {a['home']}  [law: {TIER0_LAW}]",
        f"             requested by name: {', '.join(a['names'])}",
    ]
    if a["not_run"]:
        out.append(f"NOT RUN    : {a['not_run']}")
    else:
        for f in a["files"]:
            share = 100.0 * f["lines"] / a["lines"] if a["lines"] else 0.0
            out.append(
                f"  {f['name']:14} {f['lines']:6d} lines {f['bytes']:9d} B  md5"
                f" {f['md5']}  {share:5.2f}% of injected lines"
            )
        for name in a["missing"]:
            out.append(f"  {name:14} MISSING — named in the population, absent on disk")
        out.append(
            f"leg A total: {a['lines']} lines / {a['bytes']} B / ~{a['tokens']} tok (proxy)"
            f"  = {100.0 * a['tokens'] / w:.2f}% of the window"
        )
    out.append("")
    out.append(f"--- LEG B: skills/*/SKILL.md (depth 1) @ {r['now'].strftime(ts)} ---")
    out.append(f"population : {b['root']}")
    out.append(f"budget     : {BUDGET_LINES} lines (marker only — never gates)")
    if b["not_run"]:
        out.append(f"NOT RUN    : {b['not_run']}")
    else:
        for f in b["files"]:
            over = f["lines"] - BUDGET_LINES
            state = f"OVER by {over}" if over > 0 else f"under by {-over}"
            out.append(
                f"  {f['name']:38} {f['lines']:6d} lines {f['bytes']:9d} B  md5"
                f" {f['md5']}  budget marker: {state}"
            )
        out.append(
            f"leg B total: {b['lines']} lines / {b['bytes']} B / ~{b['tokens']} tok (proxy)"
            f"  = {100.0 * b['tokens'] / w:.2f}% of the window"
        )
    out.append("")
    if a["not_run"] or b["not_run"]:
        out.append("COMBINED   : NOT RUN — a leg could not be read, so no total is stated")
    else:
        tok, lines = a["tokens"] + b["tokens"], a["lines"] + b["lines"]
        second = round((a["bytes"] + b["bytes"]) / CHARS_PER_TOKEN)
        out.append(
            f"COMBINED   : {lines} lines / {a['bytes'] + b['bytes']} B / ~{tok} tok (proxy)"
        )
        out.append(
            f"             = {100.0 * tok / w:.2f}% of a {w}-token window, paid before a"
            " session reads its first message"
        )
        out.append(
            f"             rounding paths: sum-of-printed-legs = {tok} tok;"
            f" single-rounded-sum = {second} tok; divergence = {abs(tok - second)}"
            " (the printed figure is the SUM OF THE LEGS)"
        )
    out.append("")
    out.append(f"--- LEG C: post-compaction input tokens @ {r['now'].strftime(ts)} ---")
    out.append("predicate  : daemon-log lines matching 'Compaction: sending N / N messages")
    out.append("             to summarizer (X / Y input tokens, reserving Z for output)'")
    out.append(f"population : {c['log_dir']}/opencrabs.<date>[.gz]  ({c['files']} file(s) read)")
    if c["not_run"]:
        out.append(f"NOT RUN    : {c['not_run']}")
    else:
        d = r["dist"]
        out.append(
            f"all-time   : {c['all_time']} compaction event(s) across every log present"
            f" ({c['out_of_window']} outside this window — so a zero below is visibly"
            " different from a predicate matching nothing)"
        )
        if d["n"] == 0:
            out.append(
                f"leg C EMPTY: 0 event(s) in this {r['hours']} h window. This leg examined"
                " the population and found it empty; it does NOT report a clean verdict."
            )
        else:
            out.append(f"in window  : n={d['n']} event(s)")
            out.append(
                f"  mean   {d['mean']:7d} tok  = {100.0 * d['mean'] / w:.1f}% of the window"
                "   <-- the FLOOR-sensitive figure"
            )
            out.append(f"  median {d['median']:7d} tok  = {100.0 * d['median'] / w:.1f}%")
            out.append(f"  p90    {d['p90']:7d} tok  = {100.0 * d['p90'] / w:.1f}%")
            out.append(f"  min    {d['min']:7d} tok    max {d['max']:7d} tok")
            out.append(
                "  CAVEAT: the event COUNT above tracks how many lanes were awake and how"
                " many turns they ran, NOT the weight of the law. Measured 09-19 to 09-20,"
                " the floor grew while the count fell. Read the mean/median as the floor"
                " signal; never read a rising count as 'our law got heavier'."
            )
    out.extend(oracle_block(r))
    out.append("")
    out.append("BOUNDS.")
    out.append("  1. The summarizer line is at src/brain/agent/service/context.rs and is the")
    out.append("     ONLY line leg C parses. The 'Context at NN percent (>65 percent)' trigger")
    out.append("     line at compaction.rs uses a DIFFERENT denominator (effective tokens over")
    out.append("     effective max, i.e. the window minus reserves) and must never be read as a")
    out.append("     fraction of the provider window. Conflating them overstates the floor.")
    out.append("  2. The token figures are PROXIES at a stated char/token ratio, not counts from")
    out.append("     a tokeniser — comparable across runs of THIS instrument, and not")
    out.append("     comparable to a provider's own token accounting.")
    out.append("  3. Leg A reads files that live in no repository, so a leg-A reading has an")
    out.append("     INSTANT for its identity and no revision. A revision stamp pins leg B")
    out.append("     (which is in version control) and pins nothing about leg A.")
    out.append("  4. Rotated logs are read as .gz; a day whose file is absent is UNREACHED, not")
    out.append("     quiet, and the all-time count states how many files were read.")
    out.append("  5. PRINTED, NEVER GATED. No threshold in this file fails a run.")
    return "\n".join(out)

# ---- the dated oracle: a SNAPSHOT printed beside the live reading, never gated ------
# The 2026-09-19 figures, cited from `evidence/brain-metrics-2026-09-19.md` and the
# registry claim `brain-metrics-baseline-measured`. A snapshot is CITED and DATED rather
# than re-derived: the corpus moves under it (measured 09-19 -> 09-21: leg A +82 lines in
# two days, and it moved inside a single turn's window at an unchanged revision), so a
# figure asserted as current is stale before it is committed. The only honest use of a
# snapshot is to print the live reading BESIDE it with the delta named, and to read a
# nonzero delta as MOVEMENT of the population, never as a regression.
ORACLE_AS_OF = "2026-09-19"
ORACLE_SOURCE = (
    "evidence/brain-metrics-2026-09-19.md + registry claim brain-metrics-baseline-measured"
)
ORACLE = {
    "a": {"lines": 588, "bytes": 72_393, "tokens": 20_684},
    "b": {"lines": 452, "bytes": 32_247, "tokens": 9_213},
    "combined_tokens": 29_897,
    "c": {"n": 2_011, "mean": 66_393, "median": 70_493, "p90": 97_608},
}

def _d(cur: int, ref: int) -> str:
    diff = cur - ref
    return f"{'+' if diff >= 0 else '-'}{abs(diff)}"

def oracle_block(r: dict) -> list:
    """The live reading BESIDE the dated snapshot, delta named. Printed, never gated.

    Each line states its population basis, because two of the three legs are not
    comparable figure-for-figure with the snapshot. Leg C's snapshot spanned every log
    present on 09-19 while this run reads a rolling `--hours` window, so the SHAPE is
    differenced and the count is NAMED instead -- a count is a property of its window,
    never of the corpus it is drawn from.
    """
    w = r["window"]
    a, b, dist = r["a"], r["b"], r["dist"]
    oa, ob, oc = ORACLE["a"], ORACLE["b"], ORACLE["c"]
    out = [
        "",
        "--- ORACLE: the live reading beside the dated snapshot (printed, never gated) ---",
        f"snapshot   : {ORACLE_AS_OF}  [{ORACLE_SOURCE}]",
    ]
    if a["not_run"]:
        out.append("leg A      : NOT RUN this time — no delta is stated")
    else:
        out.append(
            f"leg A      : live {a['lines']} lines / {a['bytes']} B / ~{a['tokens']} tok"
            f"   vs   {oa['lines']} / {oa['bytes']} / ~{oa['tokens']} at {ORACLE_AS_OF}"
            f"   DELTA {_d(a['lines'], oa['lines'])} lines / {_d(a['bytes'], oa['bytes'])} B"
            f" / {_d(a['tokens'], oa['tokens'])} tok (proxy)"
        )
        out.append(
            "             leg A's identity is the INSTANT, not a revision — its files are in no"
            " repository, so this delta is against a dated read, never against a commit"
        )
    if b["not_run"]:
        out.append("leg B      : NOT RUN this time — no delta is stated")
    else:
        out.append(
            f"leg B      : live {b['lines']} lines / {b['bytes']} B / ~{b['tokens']} tok over"
            f" {len(b['files'])} file(s)   vs   {ob['lines']} / {ob['bytes']} / ~{ob['tokens']}"
            f" at {ORACLE_AS_OF}"
            f"   DELTA {_d(b['lines'], ob['lines'])} lines / {_d(b['bytes'], ob['bytes'])} B"
            f" / {_d(b['tokens'], ob['tokens'])} tok (proxy)"
        )
        out.append(
            "             leg B sums EVERY skills/*/SKILL.md present, so its population grows by"
            " a new skill as well as by an edited body — the file count is printed above"
        )
    if a["not_run"] or b["not_run"]:
        out.append("combined   : NOT RUN — a leg could not be read, so no total is stated")
    else:
        tok = a["tokens"] + b["tokens"]
        ref_tok = ORACLE["combined_tokens"]
        live_pts, ref_pts = 100.0 * tok / w, 100.0 * ref_tok / DEFAULT_WINDOW
        out.append(
            f"combined   : live ~{tok} tok (proxy) = {live_pts:.2f}% of a {w}-token window"
            f"   vs   ~{ref_tok} tok = {ref_pts:.2f}% of a {DEFAULT_WINDOW}-token window at"
            f" {ORACLE_AS_OF}"
        )
        if w == DEFAULT_WINDOW:
            out.append(
                f"             DELTA {_d(tok, ref_tok)} tok (proxy) / {live_pts - ref_pts:+.2f}"
                " points of the window"
            )
        else:
            out.append(
                f"             DELTA {_d(tok, ref_tok)} tok (proxy); the SHARES are NOT"
                f" comparable across a {w}-token window and the snapshot's {DEFAULT_WINDOW}"
            )
    if dist["n"] == 0:
        out.append("leg C      : no event in this window this run — no delta is stated")
    else:
        out.append(
            f"leg C      : live n={dist['n']} / mean {dist['mean']} / median {dist['median']} /"
            f" p90 {dist['p90']} tok   vs   n={oc['n']} / {oc['mean']} / {oc['median']} /"
            f" {oc['p90']} tok at {ORACLE_AS_OF}"
        )
        out.append(
            f"             SHAPE DELTA mean {_d(dist['mean'], oc['mean'])} / median"
            f" {_d(dist['median'], oc['median'])} / p90 {_d(dist['p90'], oc['p90'])} tok — the"
            " SHAPE is compared because the count is not"
        )
        out.append(
            f"             the count is NAMED, never differenced: this run's {r['hours']:g} h"
            f" window held {dist['n']} event(s), against a snapshot that read every log present"
            f" then ({oc['n']} events, 09-12 -> 09-19). A count is a property of its window."
        )
    out.append(
        f"             A nonzero delta is MOVEMENT of the population, never a regression: the"
        f" snapshot's window closed {ORACLE_AS_OF}. Nothing in this block gates the run."
    )
    return out

def main() -> int:
    ap = argparse.ArgumentParser(
        description="brain-metrics standing reading: the static law floor and the "
                    "post-compaction context it is paid in"
    )
    ap.add_argument("--version", action=VersionAction,
                    help="print this copy\'s identity and exit")
    ap.add_argument("--home", default=os.path.expanduser("~/.opencrabs/profiles/ops"),
                    help="profile home holding the always-injected brain files (leg A)")
    ap.add_argument("--hours", type=float, default=24.0,
                    help="leg C window, in hours back from now (default 24)")
    ap.add_argument("--log-dir", default=None,
                    help="daemon log directory (default <home>/logs)")
    ap.add_argument("--window", type=int, default=DEFAULT_WINDOW,
                    help=f"provider context window in input tokens (default {DEFAULT_WINDOW})")
    ap.add_argument("--brain-files", default=",".join(DEFAULT_BRAIN_FILES),
                    help="comma-separated Tier 0 file names (default the declared triple)")
    args = ap.parse_args()
    args.brain_files = tuple(n.strip() for n in args.brain_files.split(",") if n.strip())
    if args.log_dir is None:
        args.log_dir = os.path.join(args.home, "logs")
    r = read(args)
    print(render(r))
    if r["a"]["not_run"] or r["b"]["not_run"] or r["c"]["not_run"]:
        print("\nexit 3: a leg could not be TAKEN — reported above, not a clean verdict")
        return 3
    if r["dist"]["n"] == 0:
        print("\nexit 4: leg C saw an EMPTY in-window population — reported above, "
              "not a clean verdict")
        return 4
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
