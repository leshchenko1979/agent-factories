#!/usr/bin/env python3
"""Gate: verify the single-writer property of repository state surfaces.

State that lives only in chat is not state. Every durable state surface in the
factory must have exactly one named authoritative writer role, and every file
under evidence/ must be accounted for in the single-writer specification.

Run:  python3 tests/test_single_writer.py
Exit: 0 clean, 1 un-declared state surface or single-writer violation.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# In meta-factory repo: skills/meta-factory/SKILL.md; in template: SKILL.md or SKILL.md.tmpl
SKILL_PATHS = [
    REPO / "skills" / "meta-factory" / "SKILL.md",
    REPO / "SKILL.md",
    REPO / "SKILL.md.tmpl",
    REPO / "TEMPLATE" / "SKILL.md.tmpl",
]


def find_skill_file() -> Path | None:
    candidates = list(SKILL_PATHS) + sorted(REPO.glob("skills/*/SKILL.md"))
    for p in candidates:
        if p.is_file():
            text = p.read_text(encoding="utf-8", errors="ignore")
            if "Authoritative writer" in text:
                return p
    for p in candidates:
        if p.is_file():
            return p
    return None


def parse_single_writer_surfaces(skill_file: Path) -> dict[str, str]:
    """Extract declared single-writer state surfaces from SKILL.md table."""
    text = skill_file.read_text(encoding="utf-8")
    surfaces: dict[str, str] = {}

    in_table = False
    for line in text.splitlines():
        line = line.strip()
        if "Surface" in line and "Authoritative writer" in line:
            in_table = True
            continue
        if in_table:
            if not line or not line.startswith("|"):
                in_table = False
                continue
            if line.startswith("|---"):
                continue
            cols = [c.strip() for c in line.split("|")[1:-1]]
            if len(cols) >= 3:
                surface = cols[0].strip("`").strip()
                writer = cols[2].strip("`").strip()
                if surface and writer and surface != "Surface":
                    surfaces[surface] = writer
    return surfaces


def verify_evidence_directory(declared_surfaces: dict[str, str]) -> list[str]:
    """Verify that every file under evidence/ matches a declared single-writer surface."""
    evidence_dir = REPO / "evidence"
    if not evidence_dir.is_dir():
        return []

    errors: list[str] = []
    # Patterns to match against declared surfaces
    # e.g. evidence/ledger.jsonl, evidence/rework.md, evidence/scores/<date>.md, evidence/*.md
    for item in evidence_dir.rglob("*"):
        if not item.is_file():
            continue
        rel = item.relative_to(REPO).as_posix()

        # Check if rel matches any declared surface
        if rel.endswith(".lock"):
            continue
        matched = False
        for decl in declared_surfaces:
            if decl == rel:
                matched = True
                break
            if decl == "evidence/*.md" and rel.startswith("evidence/") and rel.endswith(".md"):
                matched = True
                break
            if "evidence/scores/" in decl and rel.startswith("evidence/scores/") and rel.endswith(".md"):
                matched = True
                break
            if "evidence/subprocesses/" in decl and rel.startswith("evidence/subprocesses/") and rel.endswith(".jsonl"):
                matched = True
                break

        if not matched:
            errors.append(f"un-declared state surface in evidence/: {rel}")

    return errors


def verify_ledger_locking() -> list[str]:
    """Verify that tools/ledger.py implements exclusive file locking."""
    ledger_py = REPO / "tools" / "ledger.py"
    if not ledger_py.is_file():
        return ["tools/ledger.py missing — cannot verify single-writer locking"]

    code = ledger_py.read_text(encoding="utf-8")
    errors: list[str] = []
    if "fcntl.flock" not in code or "LOCK_EX" not in code:
        errors.append("tools/ledger.py does not use fcntl.flock with LOCK_EX")
    if "os.fsync" not in code:
        errors.append("tools/ledger.py does not call os.fsync on append")
    return errors


def main() -> int:
    skill_file = find_skill_file()
    if not skill_file:
        print("FAIL: no SKILL.md found to parse single-writer declarations", file=sys.stderr)
        return 1

    surfaces = parse_single_writer_surfaces(skill_file)
    if not surfaces:
        print(f"FAIL: no single-writer surfaces parsed from {skill_file}", file=sys.stderr)
        return 1

    errors: list[str] = []
    errors.extend(verify_evidence_directory(surfaces))
    errors.extend(verify_ledger_locking())

    if errors:
        print(f"FAIL: single-writer state verification failed ({len(errors)} error(s)):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(f"single-writer state clean: {len(surfaces)} declared surface(s) audited, locking verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
