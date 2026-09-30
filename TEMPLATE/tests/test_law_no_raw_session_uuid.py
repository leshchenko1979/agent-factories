#!/usr/bin/env python3
"""Gate: no law file names a session by a raw uuid, except where the debt is DECLARED and printed.

THE LAW (board #254, ruling at ledger n=1810). A law file must not identify a lane by a raw
session uuid, because a uuid is a value that rots the instant the topic it names is re-opened.
Measured 2026-09-30: `skills/meta-factory/SKILL.md`'s substrate-routing table named
`d72bd52d-42aa-4dbd-ac99-5b5300770019` for OpenCrabs HQ, and that id carried ZERO bindings —
the topic it meant was bound to a different session. A reader who follows a dead uuid reaches
nobody, and the row reads exactly like the live one beside it. Section 11 already sets the rule
for lanes: the live session is the newest binding within its own profile, resolved at dispatch.
So a law file carries a topic/role NAME and the resolution happens live.

WHAT THIS GATE COVERS, AND WHAT IT DOES NOT. The population is every LAW FILE in the tree —
`skills/*/SKILL.md`, `SKILL.md.tmpl` and `TEMPLATE/SKILL.md.tmpl`: the same discovery globs
`tests/test_skill_version_contract.py` uses, so the two gates cannot drift on what a law file
IS. Everything else is NOT covered, and the not-covered set is STATED AND PRINTED ON EVERY RUN
with its reason, because an unprinted exclusion is indistinguishable from a population that was
never examined. `evidence/`, `registry/`, `docs/`, `tests/` and `tools/` legitimately carry
uuids as DATA — ledger rows, generated binding renders, fixtures — and a gate that swept them
would red on every measurement of the thing it protects.

THE EXEMPTION SURFACE, AND WHY IT IS A FILE RATHER THAN A LINE IN THIS GATE. This gate is
byte-paired into `TEMPLATE/tests/`, so a factory-specific datum — which uuids THIS factory's law
legitimately names — must not live in it: shipping one factory's debt to every new factory is
the drift the kit exists to prevent. The exemptions live in `docs/law-uuid-exemptions.json`,
keyed by `path` + `uuid` (identity, never a line number, which rots on the first insertion above
it). The rules are the ones this repo already applies to its other exemption tables: an entry
that MATCHES prints as an `excused:` line on EVERY run, so it is visible debt rather than
forgiveness; an entry that matches NOTHING is a gate ERROR, so a retired debt cannot sit in the
file looking live; a malformed or duplicated entry is an ERROR rather than a silent pass; and
absent-or-empty means no exemptions, never a failure.

WHY IT IS NOT A FRESHNESS GATE (#254 ruling). Nothing offline can read live
`session_bindings`, so no gate can assert that the NAME a law file gives still resolves. That
check belongs to the dispatch-time resolution, and it is stated here rather than faked.

NON-VACUITY (#112). A forward-only gate whose population is legitimately empty until its next
instance must not loud-fail on zero VIOLATIONS — but the FILE population is not forward-only:
zero law files examined is a broken instrument, not a clean tree, and this gate FAILS on it.
The probes below drive constructed trees (a raw uuid, an exempted one, a stale entry, a
malformed entry, a duplicate entry, and four lookalike shapes that are NOT a uuid) so the
predicate is shown to bite for each reason it names.

Run:  python3 tests/test_law_no_raw_session_uuid.py
Exit: 0 clean or excused, 1 a violation or an exemption-file error.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The law surfaces this gate covers — the SAME discovery rule `tests/test_skill_version_contract.py`
# declares in its own LAW_GLOBS, so a second law file under `skills/` is found with no edit here.
LAW_GLOBS = ("skills/*/SKILL.md", "SKILL.md.tmpl", "TEMPLATE/SKILL.md.tmpl")

EXEMPTIONS_PATH = "docs/law-uuid-exemptions.json"

# The 36-character uuid shape, boundary-checked on BOTH sides so a longer hex run (a 40-char sha,
# or a uuid with a digit appended) is not read as one. Case-insensitive: an uppercased uuid is the
# same value, and a predicate that missed it would be a shape check that only covers the tidy form.
UUID_RE = re.compile(
    r"(?<![0-9a-fA-F])[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
    r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?![0-9a-fA-F])"
)

# The declared NOT-COVERED set, printed on every run with its reason and whether it is present in
# the tree under judgement. A prefix absent here is not a silent skip: it is stated as absent.
NOT_COVERED = (
    ("evidence/", "measurement records — a uuid in a ledger row, a score or a receipt is a recorded FACT about what happened, not a routing instruction"),
    ("registry/", "generated renders of live bindings — the uuid IS the datum being published"),
    ("docs/", "proposals, generated renders and addon documentation — narrative and generated artifacts, not routing law"),
    ("tests/", "test fixtures — a uuid there is constructed input, not a lane to reach"),
    ("tools/", "program sources — a uuid there is fixture data or an example inside code"),
    ("README.md", "orientation prose"),
)


def law_files(root: Path) -> list[Path]:
    """Every law file in `root`, by the declared globs. Never a hardcoded slug."""
    found: list[Path] = []
    for pattern in LAW_GLOBS:
        found.extend(sorted(root.glob(pattern)))
    seen: set[Path] = set()
    out: list[Path] = []
    for path in found:
        if path.is_file() and path not in seen:
            seen.add(path)
            out.append(path)
    return out


def load_exemptions(path: Path) -> tuple[dict[tuple[str, str], dict], list[str]]:
    """The exemption table, plus every problem with its own shape.

    Absent-or-empty is NO EXEMPTIONS, never an error. A file that exists and cannot be read is
    an ERROR: an unreadable exemption table is indistinguishable from an empty one, and the
    difference is a live debt read as no debt.
    """
    if not path.is_file():
        return {}, []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, [f"{EXEMPTIONS_PATH}: cannot be read — {exc}"]
    if not isinstance(data, dict):
        return {}, [f"{EXEMPTIONS_PATH}: must be a JSON object"]
    entries = data.get("exempt")
    if entries is None:
        return {}, []
    if not isinstance(entries, list):
        return {}, [f"{EXEMPTIONS_PATH}: `exempt` must be a list"]
    table: dict[tuple[str, str], dict] = {}
    problems: list[str] = []
    for i, entry in enumerate(entries):
        where = f"{EXEMPTIONS_PATH} entry {i}"
        if not isinstance(entry, dict):
            problems.append(f"{where}: not an object")
            continue
        rel, uuid, reason = entry.get("path"), entry.get("uuid"), entry.get("reason")
        if not isinstance(rel, str) or not rel:
            problems.append(f"{where}: `path` must be a non-empty string")
            continue
        if not isinstance(uuid, str) or not UUID_RE.fullmatch(uuid.lower()):
            problems.append(f"{where}: `uuid` must be the full 36-character uuid shape, not {uuid!r}")
            continue
        if not isinstance(reason, str) or not reason.strip():
            problems.append(f"{where}: `reason` must be a non-empty string — an exemption states its basis")
            continue
        key = (rel, uuid.lower())
        if key in table:
            problems.append(f"{where}: DUPLICATE of an earlier entry for {rel} {uuid.lower()}")
            continue
        table[key] = entry
    return table, problems


def judge(root: Path) -> dict:
    """The predicate over `root`: occurrences, excused occurrences, violations, file problems."""
    files = law_files(root)
    table, problems = load_exemptions(root / EXEMPTIONS_PATH)
    examined: list[dict] = []
    excused: list[dict] = []
    violations: list[dict] = []
    matched: set[tuple[str, str]] = set()
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(root).as_posix()
        occurrences: list[tuple[int, str]] = []
        for lineno, line in enumerate(text.splitlines(), 1):
            for match in UUID_RE.finditer(line):
                occurrences.append((lineno, match.group(0).lower()))
        examined.append({"rel": rel, "lines": len(text.splitlines()), "occurrences": occurrences})
        for lineno, uuid in occurrences:
            key = (rel, uuid)
            if key in table:
                matched.add(key)
                excused.append({"rel": rel, "line": lineno, "uuid": uuid, "entry": table[key]})
            else:
                violations.append({"rel": rel, "line": lineno, "uuid": uuid})
    stale = [entry for key, entry in table.items() if key not in matched]
    if not files:
        problems.append(
            "the FILE population is EMPTY — no law file matched "
            f"{list(LAW_GLOBS)} under {root}. Zero files examined is a broken instrument, "
            "never a clean tree (#112)."
        )
    return {
        "root": root,
        "examined": examined,
        "excused": excused,
        "violations": violations,
        "stale": stale,
        "problems": problems,
        "declared": len(table),
        "occurrences": sum(len(rec["occurrences"]) for rec in examined),
    }


def report(result: dict) -> None:
    """Print the population, the not-covered set, the debt, and the verdict — every run."""
    examined, excused, violations = result["examined"], result["excused"], result["violations"]
    print(f"population — {len(examined)} law file(s) examined under {result['root']}:")
    for rec in examined:
        print(f"    {rec['rel']} — {rec['lines']} line(s), {len(rec['occurrences'])} uuid occurrence(s)")
    print("not covered by this gate (stated, with reason):")
    for prefix, reason in NOT_COVERED:
        state = "present" if (result["root"] / prefix.rstrip("/")).exists() else "absent in this tree"
        print(f"    {prefix} ({state}) — {reason}")
    print(
        f"exemptions — {result['declared']} declared, {len(excused)} occurrence(s) excused, "
        f"{len(result['stale'])} stale"
    )
    for item in excused:
        print(f"    excused: {item['rel']}:{item['line']} {item['uuid']} — {item['entry']['reason']}")
    for entry in result["stale"]:
        print(f"    ERROR: stale exemption for {entry.get('path')} {entry.get('uuid')} — matches nothing")
    for problem in result["problems"]:
        print(f"    ERROR: {problem}")
    for item in violations:
        print(f"    VIOLATION: {item['rel']}:{item['line']} {item['uuid']}")
    clean = not violations and not result["problems"] and not result["stale"]
    state = "CLEAN" if clean else "RED"
    tail = f", {len(excused)} excused" if excused else ""
    print(
        f"verdict: {state} — {len(violations)} violation(s) in {result['occurrences']} "
        f"occurrence(s) over {len(examined)} file(s){tail}"
    )


# ---------------------------------------------------------------------------
# Non-vacuity probes. Each drives a CONSTRUCTED tree, so the predicate is shown to bite for
# every reason it names rather than only to pass on the tree that produced it.
# ---------------------------------------------------------------------------

def _tree(tmp: Path, law_text: str, exempt: list[dict] | None) -> Path:
    (tmp / "skills" / "probe").mkdir(parents=True, exist_ok=True)
    (tmp / "skills" / "probe" / "SKILL.md").write_text(law_text, encoding="utf-8")
    if exempt is not None:
        (tmp / "docs").mkdir(parents=True, exist_ok=True)
        (tmp / "docs" / "law-uuid-exemptions.json").write_text(
            json.dumps({"exempt": exempt}), encoding="utf-8"
        )
    return tmp


# CONSTRUCTED INPUT, never this factory's own roster. This file is byte-paired into
# `TEMPLATE/tests/`, so a real lane id here would ship one factory's session table to
# every other one -- the same drift the exemption file exists to prevent, one surface
# over. The probes need A uuid shape and nothing more, so the value below is synthetic
# and resolves to no lane anywhere.
PROBE_UUID = "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"


def probe_a_raw_uuid_in_a_law_file_is_a_violation() -> None:
    """A law file naming a session by uuid, with no exemption, is a VIOLATION."""
    with tempfile.TemporaryDirectory() as tmp:
        result = judge(_tree(Path(tmp), f"# probe\n\n| lane | `{PROBE_UUID}` |\n", None))
        ok = len(result["violations"]) == 1 and result["violations"][0]["uuid"] == PROBE_UUID
        print(f"  {'ok  ' if ok else 'FAIL'} a raw uuid with no exemption is a violation")
        if not ok:
            raise SystemExit(1)


def probe_an_exempted_uuid_is_excused_not_a_violation() -> None:
    """The same file WITH an exemption is excused, and the excuse is what is reported."""
    entry = {"path": "skills/probe/SKILL.md", "uuid": PROBE_UUID, "reason": "declared debt"}
    with tempfile.TemporaryDirectory() as tmp:
        result = judge(_tree(Path(tmp), f"| lane | `{PROBE_UUID}` |\n", [entry]))
        ok = not result["violations"] and len(result["excused"]) == 1 and not result["stale"]
        print(f"  {'ok  ' if ok else 'FAIL'} an exempted uuid is excused, not a violation")
        if not ok:
            raise SystemExit(1)


def probe_a_stale_exemption_is_an_error() -> None:
    """An exemption matching NOTHING is an ERROR, so a retired debt cannot read as live."""
    entry = {"path": "skills/probe/SKILL.md", "uuid": PROBE_UUID, "reason": "no longer present"}
    with tempfile.TemporaryDirectory() as tmp:
        result = judge(_tree(Path(tmp), "# probe\n\nno uuid here\n", [entry]))
        ok = len(result["stale"]) == 1 and not result["violations"]
        print(f"  {'ok  ' if ok else 'FAIL'} an exemption that matches nothing is a stale ERROR")
        if not ok:
            raise SystemExit(1)


def probe_a_malformed_or_duplicated_entry_is_an_error() -> None:
    """A missing reason, a short uuid, and a duplicate entry are each an ERROR."""
    short = {"path": "skills/probe/SKILL.md", "uuid": "2646d31a-71ee-49f0-be81", "reason": "x"}
    no_reason = {"path": "skills/probe/SKILL.md", "uuid": PROBE_UUID, "reason": ""}
    twice = [
        {"path": "skills/probe/SKILL.md", "uuid": PROBE_UUID, "reason": "one"},
        {"path": "skills/probe/SKILL.md", "uuid": PROBE_UUID, "reason": "two"},
    ]
    results = []
    for exempt in ([short], [no_reason], twice):
        with tempfile.TemporaryDirectory() as tmp:
            results.append(bool(judge(_tree(Path(tmp), f"`{PROBE_UUID}`\n", exempt))["problems"]))
    ok = all(results)
    print(f"  {'ok  ' if ok else 'FAIL'} malformed, short-uuid and duplicated entries are errors")
    if not ok:
        raise SystemExit(1)


def probe_lookalike_shapes_are_not_uuid_hits() -> None:
    """Four shapes that are NOT a 36-char uuid, and one uppercased uuid that IS."""
    lookalikes = (
        "ffffffffffffffffffffffffffffffffffffffff",  # a 40-char sha, resolving nowhere
        "2646d31a-71ee-49f0-be81-9c8dc32d32f",      # 35 chars — one short
        f"{PROBE_UUID}0",                            # 37 chars — one long
        "2646d31a-71ee-49f0-be81-9c8dc32d32fz",      # a non-hex character
    )
    with tempfile.TemporaryDirectory() as tmp:
        clean = judge(_tree(Path(tmp), "\n".join(lookalikes) + "\n", None))
        hits = judge(_tree(Path(tmp), f"`{PROBE_UUID.upper()}`\n", None))
        ok = (not clean["violations"] and not clean["problems"]
              and len(hits["violations"]) == 1)
    print(f"  {'ok  ' if ok else 'FAIL'} lookalike shapes are not hits; an uppercased uuid is")
    if not ok:
        raise SystemExit(1)


def probe_the_live_tree_is_judged() -> dict:
    """The live leg: the real population, reported. This is the gate's own verdict."""
    result = judge(REPO)
    report(result)
    return result


def main() -> int:
    print("probes (non-vacuity) — constructed trees, one per reason the predicate names:")
    probe_a_raw_uuid_in_a_law_file_is_a_violation()
    probe_an_exempted_uuid_is_excused_not_a_violation()
    probe_a_stale_exemption_is_an_error()
    probe_a_malformed_or_duplicated_entry_is_an_error()
    probe_lookalike_shapes_are_not_uuid_hits()
    print("live tree:")
    result = probe_the_live_tree_is_judged()
    if result["violations"] or result["problems"] or result["stale"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
