#!/usr/bin/env python3
"""Gate: every isolation variable the harness binding names is a mechanism the ledger HONOURS.

The binding (`docs/methodology/04-harness-binding.md` §10) tells a probe author to point
`tools/ledger.py` at a throwaway path instead of the live ledger, and it names the variables
that do it. That makes the binding a LAW, and a law naming a mechanism that does not exist is
#48's class: the document keeps promising an isolation seam that a rename in the tool has
already removed, and the next probe author follows it straight into the live ledger.

The failure is SILENT in both directions. Nothing reads the prose, so a stale variable name
costs nothing until a probe contaminates live state -- which is the harm this whole clause
exists to prevent, and which the factory has already paid for twice (20 rows on 2026-09-12,
one row on 2026-09-19). And a PRESENCE check would not catch it either: the name can sit in
the document and in the tool's source while the tool no longer reads it, because the read is
what has to be proven, not the mention.

So the predicate is BEHAVIOUR, and it is table-driven off the document itself rather than off
a second list kept here: for each variable the binding names, this gate sets it, appends, and
asserts the row lands at the pinned path while the tool's OWN default path stays uncreated and
the live ledger gains nothing. A variable in the document with no probe here FAILS (the
binding promises a mechanism this gate cannot show exists), and a probe here with no mention
in the document FAILS too (the gate would be testing something the law does not prescribe).

Everything runs in a throwaway tree built by `gate_fixtures.stage_tool`, because a tool copied
without its import closure cannot start and the failure would be blamed on the wrong file.
The staged tool resolves its own repository root to the temp tree, so every default path lands
inside the temp tree and never near the live ledger.

Run:  python3 -m pytest tests/test_binding_mechanism_exists.py -q
Exit: 0 all checks pass, 1 a check failed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / "tools"
TOOL = TOOLS / "ledger.py"
BINDING = REPO / "docs" / "methodology" / "04-harness-binding.md"
LIVE_LEDGER = REPO / "evidence" / "ledger.jsonl"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_fixtures import stage_tool  # noqa: E402

# Every probe row carries this marker, so "did a probe reach the live ledger?" is answered by
# CONTENT rather than by a row count. A peer lane appending lawfully during this run must not
# turn a hermetic gate RED, and a count comparison cannot tell the two apart.
MARKER = "probe-binding-seam"

# The binding states its variables in a table row shaped `| \`OC_NAME\` | what it redirects |`.
_VAR_ROW = re.compile(r"^\|\s*`(?P<name>OC_[A-Z0-9_]+)`\s*\|", re.MULTILINE)


# --------------------------------------------------------------------------- fixtures


def binding_variables() -> list[str]:
    """The isolation variable names the binding's own table prescribes."""
    if not BINDING.is_file():
        return []
    return [m.group("name") for m in _VAR_ROW.finditer(BINDING.read_text(encoding="utf-8"))]


def live_fingerprint() -> str:
    """A digest of the live ledger, so the gate can show it did not move."""
    if not LIVE_LEDGER.is_file():
        return ""
    return hashlib.sha256(LIVE_LEDGER.read_bytes()).hexdigest()


def live_has_marker() -> bool:
    """Whether any probe row reached the LIVE ledger, by content."""
    if not LIVE_LEDGER.is_file():
        return False
    return MARKER in LIVE_LEDGER.read_text(encoding="utf-8", errors="replace")


def stage(tmp: Path, tag: str) -> tuple[Path, Path]:
    """A throwaway repository root holding a runnable copy of the tool."""
    dest = tmp / tag / "tools"
    stage_tool(TOOL, dest, TOOLS)
    return tmp / tag, dest / "ledger.py"


def run(tool: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(tool), *args],
        capture_output=True,
        text=True,
        env={**os.environ, **env},
    )


def rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ----------------------------------------------------------------------------- probes
#
# One probe per variable the binding may name. Each returns a list of problems; an empty list
# is a mechanism that exists. A variable the binding names with no probe here is caught by
# `test_binding_and_probes_agree`, which names it and says what to do.


def probe_ledger_path(tmp: Path) -> list[str]:
    root, tool = stage(tmp, "ledger_path")
    pinned = root / "pinned" / "ledger.jsonl"
    default = root / "evidence" / "ledger.jsonl"
    proc = run(
        tool,
        {"OC_LEDGER_PATH": str(pinned)},
        "append", "--event", "run", "--actor", "worker",
        "--subject", MARKER, "--detail", "pinned",
    )
    problems: list[str] = []
    if proc.returncode != 0:
        problems.append(
            f"OC_LEDGER_PATH pinned: append failed rc={proc.returncode} "
            f"({proc.stderr.strip()[:160]}) — the tool no longer honours the override"
        )
    if len(rows(pinned)) != 1:
        problems.append(f"OC_LEDGER_PATH pinned: expected 1 row at {pinned}, found {len(rows(pinned))}")
    if default.exists():
        problems.append(
            f"OC_LEDGER_PATH pinned: the tool's own default {default} was CREATED — the row went "
            "to the default path, so the override does not redirect"
        )
    return problems


def probe_subprocess_dir(tmp: Path) -> list[str]:
    root, tool = stage(tmp, "subprocess_dir")
    pinned = root / "pinned-sub"
    default = root / "evidence" / "subprocesses" / "domain.jsonl"
    proc = run(
        tool,
        {"OC_SUBPROCESS_DIR": str(pinned)},
        "append", "--event", "run", "--actor", "worker",
        "--subject", MARKER, "--detail", "sub", "--subprocess", "domain",
    )
    problems: list[str] = []
    if proc.returncode != 0:
        problems.append(
            f"OC_SUBPROCESS_DIR pinned: append failed rc={proc.returncode} "
            f"({proc.stderr.strip()[:160]}) — the tool no longer honours the override"
        )
    if len(rows(pinned / "domain.jsonl")) != 1:
        problems.append(
            f"OC_SUBPROCESS_DIR pinned: expected 1 row at {pinned / 'domain.jsonl'}, "
            f"found {len(rows(pinned / 'domain.jsonl'))}"
        )
    if default.exists():
        problems.append(
            f"OC_SUBPROCESS_DIR pinned: the tool's own default {default} was CREATED — the "
            "sub-ledger went to the default directory, so the override does not redirect"
        )
    return problems


def probe_actors_path(tmp: Path) -> list[str]:
    root, tool = stage(tmp, "actors_path")
    declared = root / "pinned-actors.txt"
    declared.write_text("probe-lane\n", encoding="utf-8")
    led = root / "pinned" / "ledger.jsonl"
    absent_led = root / "pinned-absent" / "ledger.jsonl"

    accepted = run(
        tool,
        {"OC_ACTORS_PATH": str(declared), "OC_LEDGER_PATH": str(led)},
        "append", "--event", "run", "--actor", "probe-lane",
        "--subject", MARKER, "--detail", "declared",
    )
    refused = run(
        tool,
        {"OC_ACTORS_PATH": str(root / "absent.txt"), "OC_LEDGER_PATH": str(absent_led)},
        "append", "--event", "run", "--actor", "probe-lane",
        "--subject", MARKER, "--detail", "undeclared",
    )

    problems: list[str] = []
    if accepted.returncode != 0:
        problems.append(
            f"OC_ACTORS_PATH pinned at a file declaring `probe-lane`: rc={accepted.returncode} "
            f"({accepted.stderr.strip()[:160]}) — a declared lane must be accepted, so the "
            "override does not redirect the vocabulary read"
        )
    if len(rows(led)) != 1:
        problems.append(f"OC_ACTORS_PATH pinned: expected 1 row at {led}, found {len(rows(led))}")
    if refused.returncode == 0:
        problems.append(
            "OC_ACTORS_PATH pinned at an ABSENT file: an undeclared actor was ACCEPTED — the "
            "override is ignored and the repository's own vocabulary is still being read"
        )
    elif "unknown actor" not in refused.stderr:
        problems.append(
            f"OC_ACTORS_PATH pinned at an ABSENT file: refused rc={refused.returncode} but the "
            f"message does not name an unknown actor ({refused.stderr.strip()[:160]})"
        )
    return problems


PROBES = {
    "OC_LEDGER_PATH": probe_ledger_path,
    "OC_SUBPROCESS_DIR": probe_subprocess_dir,
    "OC_ACTORS_PATH": probe_actors_path,
}


# ------------------------------------------------------------------------------ tests


def test_binding_and_probes_agree() -> None:
    """The binding names exactly the variables this gate can show are honoured."""
    if not BINDING.is_file():
        pytest.skip(f"no harness binding at {BINDING.relative_to(REPO)} — nothing to uphold in this tree")
    named = binding_variables()
    assert named, (
        f"{BINDING.relative_to(REPO)} names no isolation variable — either the `04-harness-binding.md` §10 table was "
        "removed or its row shape changed; this gate reads that table, so it would pass "
        "vacuously. Restore the table or update _VAR_ROW."
    )
    unprobed = [name for name in named if name not in PROBES]
    assert not unprobed, (
        "the binding names isolation variable(s) this gate cannot show exists: "
        + ", ".join(unprobed)
        + " — add a probe in tests/test_binding_mechanism_exists.py for each, or remove the "
        "name from the binding: a binding naming a mechanism that does not exist is #48's class"
    )
    unprescribed = [name for name in PROBES if name not in named]
    assert not unprescribed, (
        "this gate probes isolation variable(s) the binding does not name: "
        + ", ".join(unprescribed)
        + " — either document them in `04-harness-binding.md` §10 or drop the probe"
    )
    print(f"\nbinding names {len(named)} isolation variable(s): {', '.join(named)}")


def test_every_named_variable_is_honoured(tmp_path: Path) -> None:
    """Each named variable redirects for real, and the tool's own default path stays uncreated."""
    if not BINDING.is_file():
        pytest.skip(f"no harness binding at {BINDING.relative_to(REPO)} — nothing to uphold in this tree")
    named = binding_variables()
    assert named, f"{BINDING.relative_to(REPO)} names no isolation variable — nothing to examine"

    problems: list[str] = []
    for name in named:
        probe = PROBES.get(name)
        if probe is None:
            problems.append(f"{name}: the binding names it and this gate has no probe for it")
            continue
        problems.extend(probe(tmp_path))

    assert not problems, "the binding's isolation seam is not honoured:\n  - " + "\n  - ".join(problems)
    print(f"\nexamined {len(named)} isolation variable(s): {', '.join(named)} — all honoured")


def test_the_live_ledger_gained_nothing(tmp_path: Path) -> None:
    """The hermeticity claim: a staged run must never reach the live ledger."""
    if not BINDING.is_file():
        pytest.skip(f"no harness binding at {BINDING.relative_to(REPO)} — nothing to uphold in this tree")
    before = live_fingerprint()
    for name, probe in PROBES.items():
        problems = probe(tmp_path / name)
        assert not problems, f"probe {name} failed before hermeticity could be judged:\n  - " + "\n  - ".join(problems)

    assert not live_has_marker(), (
        f"a probe row carrying `{MARKER}` reached {LIVE_LEDGER.relative_to(REPO)} — a staged run "
        "is not hermetic. The isolation seam is being bypassed; find which probe wrote it before "
        "adding anything else."
    )
    if before == live_fingerprint():
        print(f"\n{LIVE_LEDGER.relative_to(REPO)} unchanged by {len(PROBES)} probe(s)")
    else:
        # A peer lane appending lawfully during this run must not read as a probe leak. The
        # marker check above is the load-bearing half; this branch only states what it saw.
        print(
            f"\n{LIVE_LEDGER.relative_to(REPO)} moved during the run and carries no `{MARKER}` row "
            "— consistent with a concurrent lawful append, not with a probe leak"
        )
