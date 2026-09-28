#!/usr/bin/env python3
"""Append and verify immutable insights in evidence/insights.jsonl.

Insights record the empirical discoveries, paradoxes, and mechanisms uncovered
while operating and observing agent factories.

Every entry carries an AUTHOR, so the register distinguishes the owner's own
insights from a lane's. `--author` is explicit; omitted, it is DERIVED from the
writing session (`OPENCRABS_SESSION_ID`) and never defaulted — the same identity
law the ledger reads its own actor under.

Every entry also carries a CLASS, and there are exactly two:

  general         the claim stands outside this fleet: publishable content
  implementation  its subject is this fleet's own machinery: an internal
                  amendment for HQ

`--class` is required. An entry that names no audience feeds neither consumer, and
the two are read by different downstream surfaces, so an unclassified row is
unusable rather than merely tidy.

Usage:
  python3 tools/insights.py append <id> <topic> <stage> <naive_assumption> <empirical_reality> <mechanism> [options]
  python3 tools/insights.py list
  python3 tools/insights.py format <id> [--format=tweet|ru|markdown]
  python3 tools/insights.py verify
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INSIGHTS_PATH = REPO / "evidence" / "insights.jsonl"
LOCK_PATH = REPO / "evidence" / ".insights.lock"

ALLOWED_STAGES = ["stage-0", "stage-1", "stage-2", "stage-3", "stage-4", "fleet-wide"]

# The register feeds TWO consumers, so every entry names the one it serves. The values
# are deliberately coarse: an AUDIENCE split, not a topic taxonomy. A finer value would
# be a second axis pretending to be this one.
ALLOWED_CLASSES = ["general", "implementation"]

# The owner is an AUTHOR no session can stand for, so this literal is accepted
# as a first-class value and is NEVER derived.
OWNER_AUTHOR = "Alexey"

# A binding title is written by the daemon and ends with the channel reference,
# e.g. `Telegram: Factories / Insights [chat:-100…:topic:6865]`.
_TITLE_TAIL_RE = re.compile(r"\[chat:[^\]]*\]\s*$")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _lane_from_title(title: str | None) -> str | None:
    """The lane name carried by a binding title, or None.

    `Telegram: Factories / Insights [chat:-100…:topic:6865]` -> `Insights`.

    The last path segment is the lane, because the leading segments are the
    chat's and the chat is not the lane. This is the ONLY source for a topic no
    factory fragment declares, which is why it is read rather than assumed away.
    """
    text = _TITLE_TAIL_RE.sub("", str(title or "")).strip()
    if ":" in text:
        text = text.split(":", 1)[1].strip()
    lane = text.rsplit("/", 1)[-1].strip()
    return lane or None


def resolve_author(session_id: str | None = None) -> tuple[str | None, str]:
    """The authoring lane, derived from the session that is WRITING.

    Identity is DERIVED from `OPENCRABS_SESSION_ID`, never declared — the same
    rule `tools/ledger.py` reads its own actor under, so a lane cannot silently
    mislabel itself here either. Two sources, in order:

    1. the fleet registry's DECLARED lanes — a factory fragment names its topics,
       so the answer is canonical, reviewed, and versioned in the repo;
    2. the session's own BINDING TITLE — the daemon records the chat and topic
       name there, and that is the only source for a topic no fragment declares.

    Returns `(lane, reason)`. `lane` is None when neither source places the
    session, and `reason` then names what failed — never a silent fallback. A
    guessed author is worse than a missing one, because it reads as provenance.
    """
    sid = (session_id or os.environ.get("OPENCRABS_SESSION_ID") or "").strip()
    if not sid:
        return None, ("OPENCRABS_SESSION_ID is not set, so the authoring lane is "
                      "unidentifiable — pass --author")
    tools_dir = Path(__file__).resolve().parent
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    try:
        import registry  # noqa: PLC0415 — lazy: an append must not pay for it
    except Exception as exc:  # an import failure is environmental, never an identity
        return None, f"the lane resolver is unavailable (registry import failed: {exc})"
    try:
        bindings, errors = registry.all_bindings()
    except Exception as exc:
        return None, f"the lane resolver is unavailable (binding read failed: {exc})"
    if not bindings:
        detail = f" ({'; '.join(errors)})" if errors else ""
        return None, f"no live binding was readable{detail}"
    mine = [b for b in bindings if b.get("session_id") == sid]
    if not mine:
        return None, f"session {sid} holds no live channel binding"

    paths: list[str] = []
    try:
        paths = registry.live_fragment_paths([])
        for path in paths:
            data, err = registry.load_fragment(path)
            if err or not isinstance(data, dict):
                continue
            chat_id = registry.FACTORY_CHATS.get(data.get("factory"))
            for lane in data.get("lanes") or []:
                if not isinstance(lane, dict):
                    continue
                resolved = registry.resolve_lane(lane, mine, {}, chat_id)
                if resolved.get("session_id") == sid and lane.get("topic"):
                    return str(lane["topic"]), ""
    except Exception as exc:
        return None, f"the lane resolver is unavailable (fragment read failed: {exc})"

    lane = _lane_from_title(mine[0].get("session_title"))
    if lane:
        return lane, ""
    return None, (f"session {sid} matches no lane declared in {len(paths)} fragment(s) "
                  f"and its binding title carries no channel name — pass --author")


def append_insight(
    slug: str,
    topic: str,
    stage: str,
    naive_assumption: str,
    empirical_reality: str,
    mechanism: str,
    tweet_hook: str = "",
    ru_summary: str = "",
    author: str = "",
    insight_class: str = "",
) -> dict:
    if stage not in ALLOWED_STAGES:
        raise ValueError(f"stage must be one of {ALLOWED_STAGES}, got '{stage}'")
    if not str(author or "").strip():
        raise ValueError("author is required — a row with no author reads as provenance "
                         "while carrying none")
    if not str(insight_class or "").strip():
        raise ValueError("class is required — an entry that names no audience feeds "
                         "neither the content pipeline nor HQ")
    if insight_class not in ALLOWED_CLASSES:
        raise ValueError(f"class must be one of {ALLOWED_CLASSES}, got '{insight_class}'")

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
                "author": str(author).strip(),
                "class": str(insight_class).strip(),
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

        # `author` is required on every row written since the field landed. Rows
        # predating it carry no key at all and stay valid — the register is
        # append-only, so history is not rewritten to invent one. An EMPTY value
        # is a defect either way: it reads as provenance while carrying none.
        if "author" in data and not data.get("author"):
            errors.append(f"line {idx}: empty author")

        # `class` follows the same rule as `author`: rows predating the field carry no
        # key at all and stay valid, while an EMPTY value is a defect either way. An
        # UNKNOWN value is the same defect wearing a value — a typo'd class feeds
        # neither consumer while reading as a classification.
        if "class" in data:
            if not data.get("class"):
                errors.append(f"line {idx}: empty class")
            elif data["class"] not in ALLOWED_CLASSES:
                errors.append(f"line {idx}: unknown class '{data['class']}'")

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
    p_append.add_argument("--author", default="",
                          help=f"the authoring lane, or the literal {OWNER_AUTHOR} for the "
                               f"owner's own insights. Omitted: DERIVED from "
                               f"OPENCRABS_SESSION_ID, and refused when it resolves to nothing")
    p_append.add_argument("--class", dest="insight_class", default="",
                          choices=ALLOWED_CLASSES,
                          help="the audience this entry serves: 'general' for publishable "
                               "content, 'implementation' for an internal HQ amendment. "
                               "Required.")
    p_append.add_argument("--tweet", default="", help="Draft tweet narrative hook")
    p_append.add_argument("--ru", default="", help="Russian summary for Miidas/Ru-speaking audience")

    sub.add_parser("list", help="List all insights")
    sub.add_parser("verify", help="Verify integrity of insights ledger")

    p_fmt = sub.add_parser("format", help="Format insight for publishing")
    p_fmt.add_argument("id", help="Insight slug")
    p_fmt.add_argument("--format", choices=["tweet", "ru", "markdown"], default="markdown")

    args = parser.parse_args()

    if args.cmd == "append":
        author = (args.author or "").strip()
        if not author:
            author, why = resolve_author()
            if not author:
                print(f"FAIL: --author is required — {why}", file=sys.stderr)
                return 2
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
                author=author,
                insight_class=args.insight_class,
            )
            print(f"appended insight #{entry['n']}: {entry['id']} [{entry['stage']}] "
                  f"by {entry['author']} [{entry['class']}]")
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
                # A row predating the field prints `legacy` rather than a blank,
                # so "no author recorded" is never mistaken for an authored blank.
                print(f"#{d['n']} [{d['stage']}] [{d.get('class') or 'legacy'}] "
                      f"{d['id']} ({d.get('author') or 'legacy'}): {d['topic']}")
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
            print(f"**Author:** {target.get('author') or 'legacy — predates the field'}\n")
            print(f"**Class:** {target.get('class') or 'legacy — predates the field'}\n")
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
