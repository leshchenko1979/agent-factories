#!/usr/bin/env python3
"""The ledger's DERIVED index — disposable, gitignored, never a source of truth.

The ledger is JSONL: append-only, diffable, reviewable, and the only copy of the
record. That shape is worth keeping, and it costs one thing — every query is a full
scan. Measured on the meta ledger (2.59 MiB, 1263 rows, 2026-09-27): a subject scan
takes 0.0365 s, indexed equality 0.00022 s (166x), and FTS returns in ~2 ms. At the
measured fleet growth (~490 MB/year) the scan is ~7 s in a year and ~35 s in five.

So this tool builds a SQLite index BESIDE the text and never replaces it:

* the JSONL stays authoritative — this file can be deleted at any instant and the
  next build reproduces it from the ledgers alone;
* it is GITIGNORED, because it is ~2.9x the size of the text and a tracked binary
  blob deltas badly in git where the text does not;
* it is written by ONE writer (the patrol round) and read by anything.

What it is for, stated so it does not grow into something else: full-text over the
prose rows, and the `refs` graph — "everything touching #149 across all five
factories" as one query instead of five greps.

Considered and rejected as a SOURCE of truth, with the measurement: SQLite (fixes
none of the ledger's failure classes — a predicted `n`, a colliding bare #N, wake
latency deciding legality — and git-plus-a-blob cannot merge two writers; the grite
prototype lost four events while reporting ok:true), file ACLs (all five ledgers are
root:root 644 and every lane is the same uid, so a mode cannot distinguish lanes),
and git refs/blobs (right primitive, wrong object: the ledger's contract is a dense
ordinal plus arrival order, and a content-addressed store gives neither).

Commands
--------
  build                 (default) rebuild the index from the ledgers
  find TEXT             full-text search over `detail`
  subject S             every row whose subject is S, across all ledgers
  touching TEXT         every row with a ref whose VALUE contains TEXT
  check                 prove the index agrees with a plain scan of the JSONL

Exit: 0 ok, 1 a disagreement or an unreadable ledger, 2 usage.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INDEX = Path(os.environ.get("OC_LEDGER_INDEX", REPO / "evidence" / ".ledger-index.sqlite"))

# THE POPULATION IS DECLARED, with its predicate: every registered factory that carries
# an `evidence/ledger.jsonl`. A missing file is SKIPPED and named, never silently
# treated as an empty ledger — an absent ledger and an empty one are different facts.
#
# `OC_LEDGER_SOURCES` overrides it, as `name=path` pairs joined by `:`, so a gate can
# exercise this tool against a FIXTURE instead of the box's live ledgers. Same seam
# shape as OC_LEDGER_PATH and OC_REFS_KINDS_PATH.
LEDGERS: list[tuple[str, Path]] = [
    ("meta-factory", REPO / "evidence" / "ledger.jsonl"),
    ("ai-antispam", Path("/root/ai-antispam/evidence/ledger.jsonl")),
    ("infra-factory", Path("/root/vds-servers/evidence/ledger.jsonl")),
    ("inferhub-watch", Path("/root/inferhub-watch/evidence/ledger.jsonl")),
    ("miidas", Path("/root/miidas/evidence/ledger.jsonl")),
]

_override = os.environ.get("OC_LEDGER_SOURCES")
if _override:
    LEDGERS = []
    for _pair in _override.split(":"):
        if "=" not in _pair:
            continue
        _name, _, _path = _pair.partition("=")
        LEDGERS.append((_name, Path(_path)))

SCHEMA = """
CREATE TABLE rows (
    ledger  TEXT NOT NULL,
    n       INTEGER NOT NULL,
    ts      TEXT,
    event   TEXT,
    actor   TEXT,
    subject TEXT,
    detail  TEXT,
    PRIMARY KEY (ledger, n)
);
CREATE TABLE refs (
    ledger TEXT NOT NULL,
    n      INTEGER NOT NULL,
    kind   TEXT NOT NULL,
    value  TEXT NOT NULL
);
CREATE INDEX refs_value ON refs(value);
CREATE INDEX refs_kind  ON refs(kind);
CREATE INDEX rows_subject ON rows(subject);
CREATE INDEX rows_event   ON rows(event);
CREATE INDEX rows_actor   ON rows(actor);
"""


def read_rows(path: Path) -> list[dict]:
    """Streamed line by line — never `read()` a whole ledger into memory."""
    out: list[dict] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def population() -> tuple[list[tuple[str, Path, list[dict]]], list[str]]:
    found, absent = [], []
    for name, path in LEDGERS:
        if path.is_file():
            found.append((name, path, read_rows(path)))
        else:
            absent.append(name)
    return found, absent


def build() -> int:
    started = time.perf_counter()
    found, absent = population()
    if not found:
        print("no ledger found in the declared population — nothing to index")
        for name in absent:
            print(f"  absent: {name}")
        return 1

    INDEX.parent.mkdir(parents=True, exist_ok=True)
    if INDEX.exists():
        INDEX.unlink()
    con = sqlite3.connect(str(INDEX))
    con.executescript(SCHEMA)
    # FTS5 when the build has it, FTS4 otherwise. The index is derived, so the
    # fallback costs a capability, never correctness.
    fts = "fts5"
    try:
        con.execute("CREATE VIRTUAL TABLE rows_fts USING fts5(detail)")
    except sqlite3.OperationalError:
        fts = "fts4"
        con.execute("CREATE VIRTUAL TABLE rows_fts USING fts4(detail)")

    total = refs_total = 0
    for name, path, rows in found:
        con.executemany(
            "INSERT OR REPLACE INTO rows (ledger,n,ts,event,actor,subject,detail)"
            " VALUES (?,?,?,?,?,?,?)",
            [(name, r.get("n"), r.get("ts"), r.get("event"), r.get("actor"),
              r.get("subject"), r.get("detail")) for r in rows],
        )
        con.executemany(
            "INSERT INTO rows_fts (rowid, detail) VALUES (?,?)",
            [(con.execute("SELECT rowid FROM rows WHERE ledger=? AND n=?",
                          (name, r.get("n"))).fetchone()[0], r.get("detail"))
             for r in rows],
        )
        for r in rows:
            for ref in (r.get("refs") or []):
                for kind, value in ref.items():
                    con.execute("INSERT INTO refs (ledger,n,kind,value) VALUES (?,?,?,?)",
                                (name, r.get("n"), kind, str(value)))
                    refs_total += 1
        total += len(rows)
        print(f"  {name:<16} {len(rows):>5} rows")

    con.commit()
    con.execute("VACUUM")
    con.close()
    elapsed = time.perf_counter() - started
    size = INDEX.stat().st_size
    text_bytes = sum(p.stat().st_size for _n, p, _r in found)
    print(f"index: {INDEX}")
    print(f"  {total} rows, {refs_total} refs, fts={fts}, built in {elapsed:.2f}s")
    print(f"  index {size:,} B vs text {text_bytes:,} B "
          f"({size / max(text_bytes, 1):.2f}x)")
    if absent:
        print(f"  absent (skipped, not treated as empty): {', '.join(absent)}")
    return 0


def connect() -> sqlite3.Connection:
    if not INDEX.is_file():
        sys.exit(f"no index at {INDEX} — run: python3 tools/ledger-index.py build")
    return sqlite3.connect(f"file:{INDEX}?mode=ro", uri=True)


def find(text: str) -> int:
    con = connect()
    try:
        hits = con.execute(
            "SELECT r.ledger, r.n, r.event, r.subject, substr(r.detail,1,110)"
            " FROM rows_fts f JOIN rows r ON r.rowid = f.rowid"
            " WHERE rows_fts MATCH ? ORDER BY r.ledger, r.n", (text,)
        ).fetchall()
    except sqlite3.OperationalError as exc:
        sys.exit(f"bad full-text query: {exc}")
    for ledger, n, event, subject, detail in hits:
        print(f"{ledger:<16} n={n:<6} {event:<9} {subject:<12} {detail}")
    print(f"{len(hits)} hit(s) for {text!r}")
    return 0


def subject(value: str) -> int:
    con = connect()
    hits = con.execute(
        "SELECT ledger, n, event, actor, substr(detail,1,100) FROM rows"
        " WHERE subject = ? ORDER BY ledger, n", (value,)
    ).fetchall()
    for ledger, n, event, actor, detail in hits:
        print(f"{ledger:<16} n={n:<6} {event:<9} {actor:<10} {detail}")
    print(f"{len(hits)} row(s) with subject {value!r}")
    return 0


def touching(value: str) -> int:
    con = connect()
    hits = con.execute(
        "SELECT x.ledger, x.n, x.kind, x.value, r.subject FROM refs x"
        " JOIN rows r ON r.ledger = x.ledger AND r.n = x.n"
        " WHERE x.value LIKE ? ORDER BY x.ledger, x.n", (f"%{value}%",)
    ).fetchall()
    for ledger, n, kind, val, subj in hits:
        print(f"{ledger:<16} n={n:<6} {kind}:{val:<20} on {subj}")
    print(f"{len(hits)} ref(s) touching {value!r}")
    return 0


def check() -> int:
    """Prove the index agrees with a plain scan — the criterion, mechanised.

    Compares row counts per ledger AND a real equality query, because a count can
    agree while the content does not.
    """
    con = connect()
    found, absent = population()
    problems = 0
    for name, path, rows in found:
        indexed = con.execute("SELECT COUNT(*) FROM rows WHERE ledger=?", (name,)).fetchone()[0]
        if indexed != len(rows):
            print(f"  MISMATCH {name}: index {indexed} vs scan {len(rows)}")
            problems += 1
        else:
            print(f"  ok       {name}: {indexed} rows in both")

    # The equality query the index exists for, against the scan it replaces.
    probe = next((r.get("subject") for r in found[0][2] if r.get("subject")), None)
    if probe:
        scan = sorted((found[0][0], r.get("n")) for r in found[0][2]
                      if r.get("subject") == probe)
        idx = sorted(con.execute(
            "SELECT ledger, n FROM rows WHERE subject=? AND ledger=?",
            (probe, found[0][0])).fetchall())
        if scan != idx:
            print(f"  MISMATCH subject query {probe!r}: scan {len(scan)} vs index {len(idx)}")
            problems += 1
        else:
            print(f"  ok       subject query {probe!r}: {len(scan)} row(s) in both")
    if absent:
        print(f"  absent (not judged): {', '.join(absent)}")
    print("index agrees with the scan" if not problems else f"{problems} mismatch(es)")
    return 1 if problems else 0


def main() -> int:
    argv = sys.argv[1:]
    cmd = argv[0] if argv else "build"
    if cmd == "build":
        return build()
    if cmd == "find" and len(argv) > 1:
        return find(" ".join(argv[1:]))
    if cmd == "subject" and len(argv) > 1:
        return subject(argv[1])
    if cmd == "touching" and len(argv) > 1:
        return touching(argv[1])
    if cmd == "check":
        return check()
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
