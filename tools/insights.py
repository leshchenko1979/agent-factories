#!/usr/bin/env python3
"""Append and verify immutable insights in evidence/insights.jsonl.

Insights record the empirical discoveries, paradoxes, and mechanisms uncovered
while operating and observing agent factories.

Usage:
  python3 tools/insights.py append <id> <topic> <stage> <naive_assumption> <empirical_reality> <mechanism> [options]
  python3 tools/insights.py list
  python3 tools/insights.py format <id> [--format=tweet|summary|full]
  python3 tools/insights.py verify
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INSIGHTS_PATH = REPO / "evidence" / "insights.jsonl"
LOCK_PATH = REPO / "evidence" / ".insights.lock"

ALLOWED_STAGES = ["stage-0", "stage-1", "stage-2", "stage-3", "stage-4", "fleet-wide"]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_insight(
    slug: str,
    topic: str,
    stage: str,
    naive_assumption: str,
    empirical_reality: str,
    mechanism: str,
    tweet_hook: str = "",
    ru_summary: str = "",
) -> dict:
    if stage not in ALLOWED_STAGES:
        raise ValueError(f"stage must be one of {ALLOWED_STAGES}, got '{stage}'")

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK_PATH, "w") as lock_f:
        fcntl.flock(lock_f, fcntl.LOCK_EX)
        try:
            entries = []
            if INSIGHTS_PATH.is_file():
                for line in INSIGHTS_PATH.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        entries.append(json.loads(line))

            # Check duplicate slug
            for e in entries:
                if e.get("id") == slug:
                    raise ValueError(f"insight with id '{slug}' already exists")

            next_n = len(entries) + 1
            entry = {
                "n": next_n,
                "id": slug,
                "ts": now_iso(),
                "topic": topic,
                "stage": stage,
                "naive_assumption": naive_assumption,
                "empirical_reality": empirical_reality,
                "mechanism": mechanism,
                "tweet_hook": tweet_hook,
                "ru_summary": ru_summary,
            }

            with open(INSIGHTS_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())

            return entry
        finally:
            fcntl.flock(lock_f, fcntl.LOCK_UN)


def verify_insights() -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not INSIGHTS_PATH.is_file():
        return True, []

    lines = [l.strip() for l in INSIGHTS_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    seen_ids = set()
    expected_n = 1

    for idx, line in enumerate(lines, start=1):
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {idx}: invalid JSON: {exc}")
            continue

        n = data.get("n")
        if n != expected_n:
            errors.append(f"line {idx}: expected n={expected_n}, got n={n}")
        expected_n += 1

        slug = data.get("id")
        if not slug:
            errors.append(f"line {idx}: missing id")
        elif slug in seen_ids:
            errors.append(f"line {idx}: duplicate id '{slug}'")
        else:
            seen_ids.add(slug)

        if data.get("stage") not in ALLOWED_STAGES:
            errors.append(f"line {idx}: invalid stage '{data.get('stage')}'")

        for req in ["topic", "naive_assumption", "empirical_reality", "mechanism"]:
            if not data.get(req):
                errors.append(f"line {idx}: missing required field '{req}'")

    return len(errors) == 0, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Insights ledger manager")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_append = sub.add_parser("append", help="Append an empirical insight")
    p_append.add_argument("id", help="Unique slug identifier (e.g. queue-lag-trap)")
    p_append.add_argument("topic", help="Topic title")
    p_append.add_argument("stage", choices=ALLOWED_STAGES, help="Factory growth stage")
    p_append.add_argument("naive_assumption", help="The common naive intuition")
    p_append.add_argument("empirical_reality", help="What empirical telemetry proved")
    p_append.add_argument("mechanism", help="The structural fix or mechanism that solved it")
    p_append.add_argument("--tweet", default="", help="Draft tweet narrative hook")
    p_append.add_argument("--ru", default="", help="Russian summary for Miidas/Ru-speaking audience")

    sub.add_parser("list", help="List all insights")
    p_verify = sub.add_parser("verify", help="Verify integrity of insights ledger")

    p_fmt = sub.add_parser("format", help="Format insight for publishing")
    p_fmt.add_argument("id", help="Insight slug")
    p_fmt.add_argument("--format", choices=["tweet", "ru", "markdown"], default="markdown")

    args = parser.parse_args()

    if args.cmd == "append":
        try:
            entry = append_insight(
                slug=args.id,
                topic=args.topic,
                stage=args.stage,
                naive_assumption=args.naive_assumption,
                empirical_reality=args.empirical_reality,
                mechanism=args.mechanism,
                tweet_hook=args.tweet,
                ru_summary=args.ru,
            )
            print(f"appended insight #{entry['n']}: {entry['id']} [{entry['stage']}]")
            return 0
        except ValueError as e:
            print(f"FAIL: {e}", file=sys.stderr)
            return 1

    elif args.cmd == "verify":
        ok, errors = verify_insights()
        if not ok:
            print("FAIL: insights verification failed:", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            return 1
        print("insights ledger clean")
        return 0

    elif args.cmd == "list":
        if not INSIGHTS_PATH.is_file():
            print("no insights recorded yet")
            return 0
        for line in INSIGHTS_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                print(f"#{d['n']} [{d['stage']}] {d['id']}: {d['topic']}")
        return 0

    elif args.cmd == "format":
        if not INSIGHTS_PATH.is_file():
            print("no insights file", file=sys.stderr)
            return 1
        target = None
        for line in INSIGHTS_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                if d.get("id") == args.id:
                    target = d
                    break
        if not target:
            print(f"insight '{args.id}' not found", file=sys.stderr)
            return 1

        if args.format == "tweet":
            print(target.get("tweet_hook") or "No tweet draft recorded.")
        elif args.format == "ru":
            print(target.get("ru_summary") or "No Russian summary recorded.")
        else:
            print(f"## Insight #{target['n']}: {target['topic']} ({target['stage']})\n")
            print(f"**Naive assumption:** {target['naive_assumption']}\n")
            print(f"**Empirical reality:** {target['empirical_reality']}\n")
            print(f"**Structural mechanism:** {target['mechanism']}\n")
            if target.get("tweet_hook"):
                print(f"**Tweet hook:**\n```\n{target['tweet_hook']}\n```\n")
            if target.get("ru_summary"):
                print(f"**Russian publication summary:**\n{target['ru_summary']}\n")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
