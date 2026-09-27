#!/usr/bin/env python3
"""Gate: the audit's verdict records the tree condition it read (issue #150).

Origin. `python3 tools/audit.py --json` at HEAD `ed8c98f` returned DEGRADED, naming
one failing gate whose file was **VALID at HEAD** and invalid only in a peer lane's
uncommitted working-tree edit. The gate was right and the verdict was still
misleading: the audit reads the WORKING TREE -- it must, since that is the only tree
a run has -- so a lane's half-written file produced a verdict about the repository
that the repository did not have. Settling which tree the run read was manual work
(`git status` plus `git show HEAD:<path>`), done by the run rather than by the tool,
and the same shape was hit on two consecutive runs.

The rule, in two parts:

1. **The JSON payload carries the tree condition** -- the HEAD sha, the count of
   modified tracked paths, and the paths themselves -- so a verdict carries its own
   provenance and a reader can attribute without re-deriving.
2. **The report prints it beside the verdict**, so `DEGRADED` is never readable
   without "read on a tree with N modified paths". The count comes first because it
   is the fact that decides whether the failure list describes the repository or a
   lane's mid-turn edit.

WHAT THIS GATE DOES NOT DO. It does not audit HEAD instead of the working tree, and
it does not refuse to run on a dirty tree -- a run must audit the tree it actually
has. It asks only that the verdict SAY which tree that was.

An unreadable tree is not a clean one: when git cannot answer, the sha is `None` and
the render says so rather than showing a zero modification count, which would read as
the strongest possible provenance claim on the weakest possible evidence.

The probes are pure over `tree_condition` and `render_tree_line`; the last leg drives
the real audit with `--no-gates` (metrics only, no gate recursion) and parses its JSON,
because criterion 1 is a claim about the PAYLOAD and only the payload can settle it.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

from audit import render_tree_line, tree_condition  # noqa: E402

KEYS = ("head_sha", "modified_count", "modified_paths")


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=cwd, check=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def make_dirty_repo(root: Path) -> Path:
    """A synthetic checkout with exactly one modified tracked file.

    Built rather than borrowed: the bite arm must know the modification it expects,
    which no real tree can offer -- a real tree's condition changes under the probe.
    """
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "probe@example.invalid")
    _git(root, "config", "user.name", "probe")
    (root / "tracked.txt").write_text("original\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-q", "-m", "seed")
    (root / "tracked.txt").write_text("edited\n", encoding="utf-8")
    return root


def probe_condition_reports_the_three_fields() -> None:
    cond = tree_condition(REPO)
    for k in KEYS:
        assert k in cond, f"tree_condition is missing {k!r}: {cond}"


def probe_condition_reads_a_built_dirty_tree(tmp_path: Path | None = None) -> None:
    """The predicate reads the TREE, not a constant: one known edit is named."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = make_dirty_repo(Path(td) / "repo")
        cond = tree_condition(root)
        assert cond["modified_count"] == 1, cond
        assert cond["modified_paths"] == ["tracked.txt"], cond
        assert cond["head_sha"], cond


def probe_condition_names_an_unreadable_tree() -> None:
    """Not a checkout => no sha, and that is NOT reported as a clean tree."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        cond = tree_condition(Path(td))
        assert cond["head_sha"] is None, cond
        assert cond["modified_count"] == 0, cond


def probe_render_names_the_count_and_the_paths() -> None:
    line = render_tree_line(
        {"head_sha": "a" * 40, "modified_count": 2, "modified_paths": ["x.py", "y.py"]}
    )
    assert "2 modified tracked path(s)" in line, line
    assert "x.py" in line and "y.py" in line, line
    assert "aaaa" in line, line


def probe_render_says_clean_when_clean() -> None:
    line = render_tree_line({"head_sha": "b" * 40, "modified_count": 0, "modified_paths": []})
    assert "0 modified tracked path(s)" in line, line
    assert "HEAD" in line, line


def probe_render_never_shows_zero_modifications_for_an_unreadable_tree() -> None:
    """The false-clean arm: an unreadable tree must not render as a clean one."""
    line = render_tree_line({"head_sha": None, "modified_count": 0, "modified_paths": []})
    assert "UNREADABLE" in line, line
    assert "0 modified tracked path(s)" not in line, line


def probe_json_payload_carries_the_condition() -> None:
    """Criterion 1 is a claim about the PAYLOAD, so the payload is what is read."""
    proc = subprocess.run(
        [sys.executable, str(REPO / "tools" / "audit.py"), "--json", "--no-gates"],
        cwd=REPO, capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, (proc.returncode, proc.stderr[-400:])
    payload = json.loads(proc.stdout)
    assert "tree" in payload, f"the JSON carries no tree condition: {sorted(payload)}"
    cond = payload["tree"]
    for k in KEYS:
        assert k in cond, f"the payload's tree is missing {k!r}: {cond}"
    assert cond["head_sha"] is None or isinstance(cond["head_sha"], str), cond
    assert isinstance(cond["modified_count"], int), cond
    assert isinstance(cond["modified_paths"], list), cond
    assert cond["modified_count"] == len(cond["modified_paths"]), (
        "the count and the list must describe the same population"
    )


def main() -> int:
    probes = [
        ("condition reports the three fields", probe_condition_reports_the_three_fields),
        ("condition reads a built dirty tree", probe_condition_reads_a_built_dirty_tree),
        ("condition names an unreadable tree", probe_condition_names_an_unreadable_tree),
        ("render names the count and paths", probe_render_names_the_count_and_the_paths),
        ("render says clean when clean", probe_render_says_clean_when_clean),
        ("render never fakes a clean unreadable tree",
         probe_render_never_shows_zero_modifications_for_an_unreadable_tree),
        ("JSON payload carries the condition", probe_json_payload_carries_the_condition),
    ]
    failed = 0
    for label, fn in probes:
        try:
            fn()
            print(f"  PASS  {label}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL  {label}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {label}: {type(exc).__name__}: {exc}")
    cond = tree_condition(REPO)
    print(f"audit tree condition: examined {len(probes)} probe(s); live tree reads "
          f"HEAD {str(cond['head_sha'])[:9]} with {cond['modified_count']} modified "
          f"tracked path(s)")
    if failed:
        print(f"audit tree condition: FAILED — {failed} probe(s)")
        return 1
    print("audit tree condition: passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
