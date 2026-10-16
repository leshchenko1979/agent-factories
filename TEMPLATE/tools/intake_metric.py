#!/usr/bin/env python3
"""The register's INTAKE metric — how many of the owner's answers declined the question as internal.

Issue #271, ruled by HQ 2026-10-02T18:21:56Z, leg 2: *"The measurement round counts,
over a window, the answers whose text declines the question as internal, and prints
`declined-as-internal: N of M answered` beside the existing human-gate count."*

**Why the count matters.** `skills/meta-factory/state.md` §11 declares *the count of open
questions across all sets* to be the **human-gate metric**. A question that was internal
all along is human load that does not exist, so every one of them over-reports the
owner's queue by exactly the mis-routed volume. The intake clause (the instrument's own
law) is the filter that stops them being registered; this leg is what makes the leak
VISIBLE, because the clause alone is prose and prose does not report a trend.

**This is a MEASUREMENT, never a verdict.** The predicate below is a pattern set over
free text — semantics a gate cannot judge — so the number is PRINTED and the trend read
by a human. Nothing here gates, fails, or reds. `tools/audit.py` prints it; the gate
`tests/test_question_intake.py` only asserts that the printing and the law exist.

**The discriminator, and the trap it closes.** `answered_via` is the field that
separates an OWNER's answer (`page` — the page is served behind basic auth) from a LANE's
own recording (`cli`). Without it the pattern set reads a lane's decision record as a
decline: measured on this store, q25's answer text is a decision record that *quotes* the
owner — `DECIDED BY HQ under the owner's standing delegation for this class (q23/q24/q26
all answered "decide by yourself" ...)` — and a bare text scan counts it as a fifth
decline. It is `cli`; the four real declines (q21, q23, q24, q26) are `page`. Read
`answered_via` before reading a decline, or the leg reports the lane's prose as the
owner's behaviour.

**The window is a parameter, never a constant in the law.** The measurement round passes
one; the default here is 30 days.

Run:  python3 tools/intake_metric.py [--days 30] [--json]
Exit: 0 the metric was computed; 0 with a NOT RUN reason when no store is readable — an
       absent store is a factory without the instrument, not a failure (#68's lesson: a
       leg that reds a tree that legitimately has no such store teaches lanes to ignore
       red). A non-zero exit is reserved for a genuinely unreadable store.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import glob
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# The pattern set is DERIVED from the measured burst this issue was filed on
# (meta-factory set, 2026-10-02T13:50:15Z–14:05:46Z) and kept deliberately narrow: each
# entry is a phrase the owner actually used, plus the two obvious morphological variants.
# Widening it is a judgement call about language, which is why the matched NAME is
# printed beside every count — a reader audits the classification, not just the total.
DECLINE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("decide-yourself", re.compile(r"\bdecide\b[^.\n]{0,24}\b(?:it|this|that)?\s*by\s+your\s?self\b", re.I)),
    ("you-decide", re.compile(r"\byou\s+(?:should\s+)?decide\b", re.I)),
    ("internal-question", re.compile(r"\binternal\s+(?:shit|question|matter|stuff|thing)\b", re.I)),
    ("internal-shit", re.compile(r"\bsome\s+internal\b", re.I)),
    ("dont-ask-me", re.compile(r"\bdon'?t\s+ask\s+me\b", re.I)),
    ("not-owner-question", re.compile(r"\b(?:that'?s|it'?s)\s+(?:not|no)\s+(?:my|an?\s+owner)\b", re.I)),
    ("your-call", re.compile(r"\byour\s+(?:call|decision)\b", re.I)),
    # Added for the declines the owner's 2026-10-15 burst carried that the set above MISSED
    # (#489): q39 "This is outside of my human scope", q42 "I do not want to get involved in
    # this", and q31 "I dint want to be involved in this". All three sit INSIDE the same 30d
    # window the leg already reads, so the leg under-reported the very trend it exists to
    # surface -- it read 6 of 143 answered where the honest reading on that window is 9 of 143.
    # q31 was not even in the filing's count of four: `internal-question` wants a NOUN after
    # "internal" and its text says "internals", so a pattern written from the filing's list
    # would still have missed it. The two families are DIFFERENT refusals and not variants of
    # one phrase: a scope boundary says whose DOMAIN the question falls in, while a refusal to
    # engage says something about the answerer. Each carries its own name so the printed match
    # tells a reader WHICH refusal it saw.
    ("scope-boundary", re.compile(r"\b(?:outside|beyond)\b[^.\n]{0,24}\bmy\s+(?:human\s+)?(?:scope|remit)\b", re.I)),
    # The `get|be` alternation and the `dint` spelling are both MEASURED, not guessed: the
    # live burst carries "get involved" (q42) and "be involved"/"dint" (q31). Swept over the
    # whole store, this catches q31 and no other answer, and it leaves all seven
    # concept-mentioning NON-declines (q10, q12, q2, q22, q55, q6 and the "Uphold all 8
    # refusals" control) unmatched.
    ("get-involved", re.compile(
        r"\b(?:don'?t|do\s+not|won'?t|didn'?t|dint|dont)\b[^.\n]{0,30}\b(?:get|be)\s+involved\b"
        r"|\bnot\s+mine\s+to\s+(?:solve|decide|fix|answer)\b",
        re.I,
    )),
)

# The store's own `answered_via` value for an answer that arrived from the OWNER's page.
OWNER_VIA = "page"

DEFAULT_WINDOW_DAYS = 30.0


def declines_as_internal(text: str | None) -> str | None:
    """The NAME of the first pattern the text matches, or None.

    Returns the name rather than a bool so a caller can print WHICH phrase matched —
    a bare True is unauditable, and this leg exists to be audited.
    """
    if not text:
        return None
    for name, pattern in DECLINE_PATTERNS:
        if pattern.search(text):
            return name
    return None


def resolve_store(explicit: str | None = None) -> tuple[Path | None, str]:
    """Resolve the register store, or return (None, why not).

    **Resolved, never pinned** — the instrument's own open-questions.md §5.1 forbids a clause that fixes the
    path, because a vendored copy and the executing copy are not interchangeable. So the
    order is: an explicit override, then `OC_QUESTIONS_STORE`, then a glob over the
    profile homes. Two-or-more matches are NOT a hard exit here (that rule belongs to the
    CLI's own resolution); the newest mtime wins and the choice is printed, because this
    leg reports a measurement rather than executing the instrument.
    """
    if explicit:
        p = Path(explicit).expanduser()
        return (p, "") if p.is_file() else (None, f"declared store not readable: {p}")
    env = os.environ.get("OC_QUESTIONS_STORE")
    if env:
        p = Path(env).expanduser()
        return (p, "") if p.is_file() else (None, f"OC_QUESTIONS_STORE not readable: {p}")
    homes = Path.home() / ".opencrabs" / "profiles"
    found = [Path(m) for m in glob.glob(str(homes / "*" / "questions" / "open.json"))]
    found = [p for p in found if p.is_file()]
    if not found:
        return None, f"no register store under {homes}/*/questions/open.json"
    if len(found) > 1:
        found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return found[0], f"{len(found)} stores readable; newest by mtime chosen"
    return found[0], ""


def _parse_instant(value: Any) -> _dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def intake_stats(store: dict[str, Any], *, days: float, now: _dt.datetime | None = None) -> dict[str, Any]:
    """Count, over a window, the owner's answers whose text declines the question.

    Pure over the parsed store — no filesystem, no clock beyond the `now` passed in — so
    the gate can drive it with a fixture and the audit with the live store, and the two
    cannot drift.

    `answered` (M) is every answer that arrived via the owner's page inside the window;
    `declined` (N) is the subset whose text matches a decline pattern. Both numbers are
    returned with the pattern NAMES, because a rate whose numerator cannot be inspected
    is an impression with a decimal point.
    """
    now = now or _dt.datetime.now(_dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=_dt.timezone.utc)
    cutoff = now - _dt.timedelta(days=days)

    answered = 0
    declined = 0
    matched: list[dict[str, str]] = []
    by_factory: dict[str, int] = {}
    for aset in store.get("sets") or []:
        if not isinstance(aset, dict):
            continue
        factory = str(aset.get("factory") or "?")
        for q in aset.get("questions") or []:
            if not isinstance(q, dict) or q.get("status") != "answered":
                continue
            if q.get("answered_via") != OWNER_VIA:
                continue
            at = _parse_instant(q.get("answered_at"))
            if at is None or at < cutoff:
                continue
            answered += 1
            name = declines_as_internal(q.get("answer") if isinstance(q.get("answer"), str) else None)
            if name:
                declined += 1
                by_factory[factory] = by_factory.get(factory, 0) + 1
                matched.append({"qid": str(q.get("qid") or "?"), "pattern": name, "factory": factory})

    return {
        "window_days": days,
        "answered": answered,
        "declined": declined,
        "share": round(declined / answered, 4) if answered else 0.0,
        "by_factory": by_factory,
        "matched": matched,
    }


def format_line(stats: dict[str, Any], reason: str = "") -> str:
    """The one rendering of the metric. `NOT RUN` carries its reason, never a bare zero."""
    if reason and stats.get("answered") == 0 and not stats.get("matched"):
        return f"declined-as-internal: NOT RUN — {reason}"
    return (
        f"declined-as-internal: {stats['declined']} of {stats['answered']} answered"
        f" (window {stats['window_days']:g}d, share {stats['share'] * 100:.1f}%)"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Register intake metric — declines-as-internal over a window.")
    ap.add_argument("--days", type=float, default=DEFAULT_WINDOW_DAYS)
    ap.add_argument("--store", default=None, help="explicit store path (default: resolve)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    path, reason = resolve_store(args.store)
    if path is None:
        payload = {"status": "not_run", "reason": reason, "answered": 0, "declined": 0}
        print(json.dumps(payload, indent=2) if args.json else format_line(payload, reason))
        return 0

    try:
        store = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"declined-as-internal: UNREADABLE — {path}: {exc}", file=sys.stderr)
        return 1

    stats = intake_stats(store, days=args.days)
    stats["store"] = str(path)
    if args.json:
        print(json.dumps(stats, indent=2))
    else:
        print(format_line(stats, reason))
        if reason:
            print(f"  note: {reason}")
        for row in stats["matched"]:
            print(f"  {row['qid']} [{row['factory']}] {row['pattern']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
