#!/usr/bin/env python3
"""Gate: HQ implements nothing, and every factory has a lane to delegate to.

Owner order 2026-09-18: *"the HQ should be kept idle for incoming managerial work
and thus should not do the work items itself. It should have one or more separate
lanes to delegate the work to."*

Until that order this repo shipped the opposite doctrine — **"HQ alone is a valid
answer"**: when `ROLES` was `HQ` alone there was no lane to delegate to, so HQ was
also the factory's implementer and the factory's own repo was its to change. The
doctrine was stated across five law surfaces and upheld by **no** gate, which is
why it survived every audit run: prose is not a mechanism (P29), and a rule that
is only written down is a rule that drifts back.

This gate is that mechanism. It reads the law surfaces — the HQ card, the law
file, the bootstrap, the ontology, the best-practice entry, and each factory's own
skill — and fails when one of them permits the retired doctrine again, or when a
law that declares lanes declares none for HQ to delegate to.

It resolves its own tree, so one file serves both: run from this repo it checks
`TEMPLATE/…`; run from `TEMPLATE/` — or from a bootstrapped factory, where the
copies sit at the root — it checks the same law in place. The two copies are
byte-identical and paired by `tests/test_template_sync.py`.

Run:  python3 tests/test_hq_delegation.py
Exit: 0 clean, 1 a surface permits the doctrine or names no delegation lane.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# --- surfaces -----------------------------------------------------------------
# Ordered candidates: the template-repo layout first, then the bootstrapped
# factory layout, where the same law sits at the root.

HQ_CARD = ("TEMPLATE/roles/hq.md", "roles/hq.md")
LAW = ("TEMPLATE/SKILL.md.tmpl", "SKILL.md.tmpl", "SKILL.md")
BOOTSTRAP = ("TEMPLATE/BOOTSTRAP.md", "BOOTSTRAP.md")
ONTOLOGY = ("ONTOLOGY.md",)
BEST_PRACTICES = ("docs/best-practices.md",)
FACTORY_LAWS = "skills/*/SKILL.md"

NEGATION = re.compile(r"\b(?:not|no|nothing|never|cannot|nor|without|absent)\b", re.I)
IMPLEMENT = re.compile(r"implement", re.I)
CONDITIONAL = re.compile(r"\b(?:unless|when|if)\b", re.I)
ALONE = re.compile(r"\balone\b", re.I)
# The verbs a permission sentence is built from. Paired with a conditional and
# 'alone', they are the shape the retired exception took.
PERMISSION_VERB = re.compile(
    r"implement|absorb|takes? the work|does the work|is also the", re.I
)

# The retired sentences themselves, so a restore is caught in the letter as well
# as in shape. Each is a *positive* assertion the law no longer makes: the new
# text negates every one of them ("`HQ` alone is **not** a valid answer"), which
# is why these patterns do not match the law as it now stands.
RETIRED_DOCTRINE: list[tuple[str, str]] = [
    (r"implements?\s+(?:its|the\s+factory's)\s+own\s+repo\s+when", "HQ implements its own repo when …"),
    (r"unless\s+`?ROLES`?\s+is\s+`?HQ`?\s+alone", "unless ROLES is HQ alone"),
    (r"when\s+there\s+is\s+no\s+lane\s+to\s+delegate", "when there is no lane to delegate to"),
    (r"there\s+is\s+no\s+lane\s+to\s+delegate", "there is no lane to delegate to"),
    (r"no\s+lane\s+to\s+lose\s+it\s+to", "no lane to lose it to"),
    (r"`?HQ`?\s+alone\s+is\s+a\s+valid\s+answer", "HQ alone is a valid answer"),
    (r"`?ROLES`?\s+is\s+`?HQ`?\s+alone\s+is\s+valid", "ROLES is HQ alone is valid"),
]

# A lane-table row: | Topic | thread_id | `session-uuid` | Carries |
LANE_ROW = re.compile(
    r"^\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|\s*`?([0-9a-fA-F-]{36})`?\s*\|\s*([^|]*)\|", re.M
)

# Cards that are not an implementer: HQ rules, Triage routes, Carrier ships.
NON_IMPLEMENTER_CARDS = {"hq", "triage", "carrier", "owner"}

def _rel(path: Path) -> str:
    """A path as the reader sees it — relative to whichever tree it lives in."""
    for base in (REPO_ROOT, REPO_ROOT / "TEMPLATE"):
        try:
            return str(path.relative_to(base))
        except ValueError:
            continue
    return str(path)

def resolve(root: Path, *candidates: str) -> Path | None:
    for rel in candidates:
        candidate = root / rel
        if candidate.is_file():
            return candidate
    return None

def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def _hq_card_forbids_implementation(path: Path) -> list[str]:
    """Every mention of implementing in the HQ card must be a refusal.

    Deliberately line-local: a negation elsewhere in the file cannot excuse a
    grant stated here, and the retired card carried three unrefused mentions —
    "Implementation of the factory's own repo when `ROLES` is `HQ` alone",
    "Implements, when there is no lane to delegate to", and "HQ is also the
    factory's implementer".
    """
    problems: list[str] = []
    for lineno, line in enumerate(read(path).splitlines(), 1):
        if not IMPLEMENT.search(line) or NEGATION.search(line):
            continue
        problems.append(
            f"{_rel(path)}:{lineno}: the HQ card mentions implementing without "
            f"refusing it — {line.strip()!r}"
        )
    return problems

def _no_retired_doctrine(path: Path) -> list[str]:
    """Neither the retired sentence nor the shape it took may be restated."""
    problems: list[str] = []
    for lineno, line in enumerate(read(path).splitlines(), 1):
        for pattern, label in RETIRED_DOCTRINE:
            if re.search(pattern, line, re.I):
                problems.append(
                    f"{_rel(path)}:{lineno}: the retired doctrine {label!r} is back "
                    f"— {line.strip()!r}"
                )
        if CONDITIONAL.search(line) and ALONE.search(line) and PERMISSION_VERB.search(line):
            problems.append(
                f"{_rel(path)}:{lineno}: a conditional plus 'alone' plus a permission "
                f"verb is the shape the retired exception took ('... when/unless ROLES "
                f"is HQ alone ...'). State the requirement unconditionally "
                f"— {line.strip()!r}"
            )
    return problems

def _minimum_role_set_stated(law: Path, bootstrap: Path | None) -> list[str]:
    """The law must say HQ alone is not a factory, and its table must agree."""
    problems: list[str] = []
    text = read(law)

    if "minimum role set" not in text.lower():
        problems.append(
            f"{_rel(law)}: the law states no minimum role set — a reader cannot tell "
            f"that `ROLES` = `HQ` is an invalid answer"
        )

    if not re.search(r"^\|\s*`?Worker`?\s*\|", text, re.M):
        problems.append(
            f"{_rel(law)}: the roles table names no `Worker` — the implementation card "
            f"HQ delegates to"
        )

    hq_rows = [l for l in text.splitlines() if re.match(r"^\|\s*`?HQ`?\s*\|", l)]
    if not hq_rows:
        problems.append(f"{_rel(law)}: the roles table has no `HQ` row")
    for row in hq_rows:
        if IMPLEMENT.search(row) and not NEGATION.search(row):
            problems.append(f"{_rel(law)}: the HQ row grants implementation — {row.strip()!r}")
        elif not IMPLEMENT.search(row):
            problems.append(
                f"{_rel(law)}: the HQ row does not say HQ implements nothing — {row.strip()!r}"
            )

    if bootstrap is not None:
        roles_rows = [
            l for l in read(bootstrap).splitlines()
            if l.strip().startswith("|") and "`ROLES`" in l
        ]
        if not roles_rows:
            problems.append(f"{_rel(bootstrap)}: no ROLES row found in the shape table")
        elif "not a valid answer" not in " ".join(roles_rows):
            problems.append(
                f"{_rel(bootstrap)}: the ROLES row does not rule out `HQ` alone — "
                f"expected an explicit '`HQ` alone is not a valid answer'"
            )
    return problems

def _implementation_card_shipped(roles_dir: Path) -> list[str]:
    """A card set with no implementer leaves the first work item nowhere to go."""
    cards = sorted(p.stem for p in roles_dir.glob("*.md"))
    if [c for c in cards if c.lower() not in NON_IMPLEMENTER_CARDS]:
        return []
    return [
        f"{_rel(roles_dir)}/: ships {cards} — no card for a lane HQ can delegate to. "
        f"HQ implements nothing, so a factory with these cards alone has nowhere to "
        f"put its first work item"
    ]

def _law_names_a_delegation_lane(path: Path) -> list[str]:
    """A law that declares lanes must declare one for HQ to delegate to."""
    rows = LANE_ROW.findall(read(path))
    if not rows:
        return []  # no lane table here: nothing to assert

    problems: list[str] = []
    hq_rows = [r for r in rows if r[0].strip().strip("`") == "HQ"]
    other_rows = [r for r in rows if r[0].strip().strip("`") != "HQ"]

    if not hq_rows:
        problems.append(f"{_rel(path)}: the lane table declares no `HQ` row")
    for _topic, _tid, _uuid, carries in hq_rows:
        if IMPLEMENT.search(carries) and not NEGATION.search(carries):
            problems.append(
                f"{_rel(path)}: the HQ lane row grants implementation — {carries.strip()!r}"
            )
        elif not IMPLEMENT.search(carries):
            problems.append(
                f"{_rel(path)}: the HQ lane row does not state that HQ implements nothing"
            )

    if not other_rows:
        problems.append(
            f"{_rel(path)}: the lane table declares no lane besides HQ — HQ has nothing "
            f"to delegate to"
        )
    elif not [r for r in other_rows if IMPLEMENT.search(r[3])]:
        problems.append(
            f"{_rel(path)}: no lane besides HQ carries implementation — the order asks "
            f"for 'one or more separate lanes to delegate the work to', and the table "
            f"names none"
        )
    return problems

def check(root: Path) -> list[str]:
    """Every problem in the law tree rooted at `root`. Empty means clean."""
    problems: list[str] = []

    hq_card = resolve(root, *HQ_CARD)
    law = resolve(root, *LAW)
    bootstrap = resolve(root, *BOOTSTRAP)
    factory_laws = sorted(root.glob(FACTORY_LAWS))

    # 1. The HQ card must exist and must forbid implementation without exception.
    if hq_card is None:
        problems.append(
            "HQ card: none of "
            + ", ".join(HQ_CARD)
            + " exists — the role this gate exists to constrain is unreadable, and a "
            "silent skip would read as a pass"
        )
    else:
        problems.extend(_hq_card_forbids_implementation(hq_card))

    # 2. No surface may carry the retired doctrine, in the letter or in shape.
    surfaces = [hq_card, law, bootstrap, resolve(root, *ONTOLOGY), resolve(root, *BEST_PRACTICES)]
    surfaces.extend(factory_laws)
    for path in [p for p in surfaces if p is not None]:
        problems.extend(_no_retired_doctrine(path))

    # 3. The law must state the minimum role set, and its table must agree.
    if law is None:
        problems.append("law: no SKILL.md / SKILL.md.tmpl found — cannot check the role set")
    else:
        problems.extend(_minimum_role_set_stated(law, bootstrap))

    # 4. An implementation card must ship.
    if hq_card is not None:
        problems.extend(_implementation_card_shipped(hq_card.parent))

    # 5. Every law that declares lanes must declare one to delegate to. The root
    #    law is checked too: a bootstrapped factory carries its lane table there.
    lane_laws = {p for p in [law, *factory_laws] if p is not None}
    for path in sorted(lane_laws):
        problems.extend(_law_names_a_delegation_lane(path))

    return problems

def main() -> int:
    problems = check(REPO_ROOT)
    if problems:
        print("HQ delegation problems:\n")
        for p in problems:
            print(f"  {p}")
        print("\nThe law is that HQ implements nothing and delegates every work item to")
        print("a lane (owner order 2026-09-18). Fix the surface, not this gate.")
        return 1

    print(
        "HQ delegation clean: no law surface permits 'HQ alone', and every law that "
        "declares lanes declares one to delegate to"
    )
    return 0

def test_no_law_surface_permits_hq_alone() -> None:
    problems = check(REPO_ROOT)
    assert not problems, "law surfaces permitting the retired HQ-alone doctrine: " + "; ".join(problems)

if __name__ == "__main__":
    raise SystemExit(main())
