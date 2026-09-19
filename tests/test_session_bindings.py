#!/usr/bin/env python3
"""Gate: session bindings and UUID integrity hold across the factory's lanes.

Verifies:
  1. SKILL.md declares session bindings for each lane.
  2. Declared session IDs are syntactically valid UUID4 strings.
  3. All declared lane sessions are distinct (no duplicate session multiplexing).
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_session_bindings_validity() -> None:
    skill_file = REPO_ROOT / "skills" / "meta-factory" / "SKILL.md"
    assert skill_file.is_file(), f"Missing {skill_file}"

    content = skill_file.read_text(encoding="utf-8")
    # Matches markdown table rows with lane sessions: | Topic | thread_id | Lane session | Carries |
    # e.g.: | HQ | 21 | `2646d31a-71ee-49f0-be81-9c8dc32d32fa` | ...
    matches = re.findall(r"\|\s*([A-Za-z0-9_\-]+)\s*\|\s*(\d+)\s*\|\s*`([a-f0-9\-]{36})`\s*\|", content)
    assert len(matches) >= 4, f"Expected at least 4 declared lanes in SKILL.md, found {len(matches)}"

    seen_uuids: set[str] = set()
    for topic, thread_id, session_uuid in matches:
        try:
            parsed = uuid.UUID(session_uuid, version=4)
            assert str(parsed) == session_uuid, f"UUID formatting mismatch: {session_uuid}"
        except ValueError as e:
            raise AssertionError(f"Invalid UUID4 for lane {topic} (thread {thread_id}): {session_uuid} ({e})")

        assert session_uuid not in seen_uuids, f"Duplicate session UUID assigned to multiple lanes: {session_uuid}"
        seen_uuids.add(session_uuid)


if __name__ == "__main__":
    test_session_bindings_validity()
    print("ALL DECLARED LANE SESSION BINDINGS ARE VALID AND DISTINCT UUID4s.")
