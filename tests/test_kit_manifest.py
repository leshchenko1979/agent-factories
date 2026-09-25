#!/usr/bin/env python3
"""Gate: `registry/kit.json` describes the shipped kit, and the check BITES.

Origin: plan 2646d31a step 9, from the drift measurement of 2026-09-25 — over the
ten bootstrap-named files across five member factories, **50 cells: 1 identical
(2%), 20 drifted, 29 absent**, with three of the absent ones being the write-path
guards (`tools/gate_budget.py` and both `tools/hooks/` refusal points) that had
therefore never bound a single member. Without a manifest a drift leg can only say
that a factory DIFFERS; it cannot say what the reference is.

WHAT THIS GATE PROVES, and the half it cannot. It proves the manifest AGREES with
the tree it describes, and — by mutation on a COPY — that the check REJECTS a
drifted, a deleted and an unlisted file, each NAMED. That second half is the one
that matters: `--check` returning 0 is exactly what a vacuous implementation would
print, so a gate that only ever saw a clean tree would pass on a check that tested
nothing. It cannot prove a member factory has PORTED anything; that is a live-state
fact about other repos, and it belongs to the patrol leg (step 10), never here.

WHY THE MUTATION ARMS RUN ON A COPY. The subject under test is the check's
behaviour on a drifted tree, and producing that tree in place would mean mutating
shipped files — which another lane may be reading. The copy is built with the repo
as its source, so the tool and the manifest under test are the real ones; only the
mutation is synthetic. The live tree's digest is compared before and after, so the
hermeticity claim is measured rather than asserted.

Run:  python3 tests/test_kit_manifest.py
Exit: 0 the manifest agrees and the check bites; 1 a check failed; 0 with a stated
      SKIP when this tree carries no `TEMPLATE/` (a bootstrapped factory).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
KIT_ROOT = REPO / "TEMPLATE"
TOOL = REPO / "tools/kit_manifest.py"
MANIFEST = REPO / "registry/kit.json"
PROBE_FILE = "TEMPLATE/tools/ledger.py"
VICTIM = "TEMPLATE/roles/worker.md"
UNLISTED = "TEMPLATE/tools/escaped-probe.py"

_failures: list[str] = []

def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        _failures.append(name)

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> int:
    print("kit manifest — the shipped kit is described, and the check bites (plan 2646d31a step 9)")

    if not KIT_ROOT.is_dir():
        print(
            "kit manifest: SKIPPED — this tree carries no TEMPLATE/, so there is no shipped "
            "kit to describe. A bootstrapped factory lands here."
        )
        return 0

    for path, what in ((TOOL, "the generator"), (MANIFEST, "the manifest")):
        if not path.is_file():
            check(f"{what} exists", False, f"{path.relative_to(REPO)} is absent")
            return 1

    # ARM 1 — agreement with the LIVE tree, run from the repo itself.
    proc = subprocess.run([sys.executable, str(TOOL), "--check"], cwd=str(REPO),
                          capture_output=True, text=True)
    check("the manifest agrees with the shipped tree", proc.returncode == 0,
          proc.stdout.strip()[:120])

    declared = json.loads(MANIFEST.read_text(encoding="utf-8"))
    files = declared.get("files") or {}
    check("the manifest describes a non-empty kit", len(files) > 50, f"{len(files)} file(s)")
    check("every declared path is repo-relative and under TEMPLATE/",
          all(p.startswith("TEMPLATE/") for p in files),
          next((p for p in files if not p.startswith("TEMPLATE/")), "all under TEMPLATE/"))
    check("transient artifacts are excluded, not shipped as kit",
          not any("__pycache__" in p or p.endswith(".pyc") or ".pytest_cache" in p for p in files),
          "no cache or bytecode paths")

    # ARM 1b — THE IDENTITY QUERY, whose answer must be CHECKABLE rather than trusted.
    # `--identity` reports which copy of a shipped file the caller holds, and it is not a
    # gate (it exits 0 for a mismatch too), so nothing else here would notice it drifting
    # away from the manifest it reads. The digest it prints for a shipped file must EQUAL
    # the manifest's entry byte for byte, and it must name the kit_version — otherwise a
    # caller can only eyeball a prefix, which is the human-checkable form this project
    # exists to replace.
    proc = subprocess.run([sys.executable, str(TOOL), "--identity", "tools/ledger.py"],
                          cwd=str(REPO), capture_output=True, text=True)
    _want = files.get(PROBE_FILE, "")
    _got = re.search(r"sha256=([0-9a-f]{64})", proc.stdout)
    check("the identity query prints the FULL digest, equal to the manifest entry",
          proc.returncode == 0 and bool(_got) and _got.group(1) == _want
          and str(declared.get("kit_version", "")) in proc.stdout,
          proc.stdout.strip()[:120])

    # The specimen is a REAL file this repo carries and the kit does not ship — this
    # gate itself. A path that does not exist would land on UNREADABLE instead, which
    # is a different branch and would make this arm pass for the wrong reason.
    check("this gate's own file is a real path the kit does not ship",
          (REPO / "tests/test_kit_manifest.py").is_file()
          and not (REPO / "TEMPLATE/tests/test_kit_manifest.py").exists(),
          "tests/test_kit_manifest.py exists here and is not in TEMPLATE/")
    proc = subprocess.run([sys.executable, str(TOOL), "--identity", "tests/test_kit_manifest.py"],
                          cwd=str(REPO), capture_output=True, text=True)
    check("a real path the kit does not ship is reported, not silently matched",
          proc.returncode == 0 and "not-in-kit" in proc.stdout, proc.stdout.strip()[:120])

    live_digest_before = sha(REPO / PROBE_FILE)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        shutil.copytree(REPO, root,
                        ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))

        def run(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, str(root / "tools/kit_manifest.py"), *args],
                                  cwd=str(root), capture_output=True, text=True)

        check("CONTROL: the unmutated copy is in agreement", run("--check").returncode == 0,
              "without this the arms below cannot distinguish a working check from a broken one")

        # ARM 2 — one byte moved: the file is DRIFTED and NAMED.
        probe = root / PROBE_FILE
        probe.write_bytes(probe.read_bytes() + b"\n# drift probe\n")
        r = run("--check")
        check("a mutated file is REFUSED and named",
              r.returncode == 1 and "DRIFTED" in r.stdout and PROBE_FILE in r.stdout,
              [l.strip() for l in r.stdout.splitlines() if "DRIFTED" in l][:1] or r.stdout[:80])

        # ARM 3 — the version is CONTENT-DERIVED: it must move with the bytes, or it is a
        # number nobody can test and it drifts the moment someone edits a shipped file.
        run()  # regenerate in the copy, absorbing the mutation
        moved = json.loads((root / "registry/kit.json").read_text())["kit_version"]
        check("the kit version MOVES when the content moves",
              moved != declared.get("kit_version"), f"{declared.get('kit_version')} -> {moved}")

        # ARM 4 — a shipped file DELETED: named as MISSING.
        victim = root / VICTIM
        body = victim.read_bytes()
        victim.unlink()
        r = run("--check")
        check("a deleted shipped file is REFUSED and named",
              r.returncode == 1 and "MISSING" in r.stdout and VICTIM in r.stdout,
              [l.strip() for l in r.stdout.splitlines() if "MISSING" in l][:1] or r.stdout[:80])

        # ARM 5 — a NEW shipped file the manifest never saw: this is the direction a
        # hand-kept list hides, which is why it is a failure rather than a note.
        victim.write_bytes(body)
        (root / UNLISTED).write_text("# a shipped file the manifest never saw\n", encoding="utf-8")
        r = run("--check")
        check("a shipped file that ESCAPED the manifest is refused and named",
              r.returncode == 1 and "UNLISTED" in r.stdout and UNLISTED in r.stdout,
              [l.strip() for l in r.stdout.splitlines() if "UNLISTED" in l][:1] or r.stdout[:80])

    # ARM 6 — HERMETICITY: the mutation arms ran on a copy, so the live shipped file is
    # byte-identical. Measured rather than asserted.
    check("the live shipped file was never mutated",
          sha(REPO / PROBE_FILE) == live_digest_before, PROBE_FILE)

    if _failures:
        print(f"kit manifest FAILED: {len(_failures)} check(s)")
        return 1
    print("kit manifest passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
