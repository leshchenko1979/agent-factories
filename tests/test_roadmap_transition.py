#!/usr/bin/env python3
"""Gate: an un-onboarded factory is RED, and onboarding is the transition to GREEN.

Origin (issue #40). `tools/roadmap.py` carried the canonical product list *inside
itself* — and that tool is a **paired** file (`tests/test_template_sync.py`), copied
byte-identically into `TEMPLATE/`. So the template shipped this factory's products
as if they were law, and one of them was an artifact no bootstrapped factory can
ever have: `TEMPLATE/`. Every new factory was therefore born with a permanently RED
roadmap audit and an unsatisfiable artifact list, with no way to tell "you have not
onboarded yet" apart from "you are broken".

The owner ruling inverted the question: *every new factory should be red unless the
onboarding process has been completed.* That makes red a **specified state**, not a
defect — provided three things hold, and this gate is what holds them:

  1. The product list is **factory data**, not template law. It lives in
     `docs/products.json`, which the template does not ship. The tool reads it.
  2. A missing declaration is a **reported** state — a reason naming the fix and a
     non-zero exit — never a traceback and never a silent pass.
  3. The transition is real: **filling the declaration turns it green**, and copying
     the skeleton without filling it does not.

**The predicate.** This gate does not assert "the tree is green" — that would be
false in `TEMPLATE/`, where the absence of a declaration is the correct state. It
asserts the **correspondence**: `exit 0` if and only if the tree declares products
whose artifacts exist. A synthetic tree is driven through the real CLI to prove both
directions, and the same law is then checked against the tree this file is running
in. So one file serves the factory (declared → green) and the template (undeclared →
red) without either being special-cased.

**Why the CLI and not the function.** `tools/audit.py` consumes the *exit code*, so
the exit code is the contract. Importing `audit_products` and checking its return
value would pass on a tool whose `main()` returned 0 anyway.

Run:  python3 tests/test_roadmap_transition.py
Exit: 0 the law holds in every case, 1 one case contradicts it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

TOOL_REL = "tools/roadmap.py"
DECLARATION = "docs/products.json"
EXAMPLE = "docs/products.example.json"
TIMEOUT = 60


def run_tool(root: Path) -> tuple[int, str]:
    """Run the real CLI inside `root`; return (exit code, stderr-or-stdout)."""
    proc = subprocess.run(
        [sys.executable, str(root / TOOL_REL), "--audit"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
    )
    return proc.returncode, (proc.stderr.strip() or proc.stdout.strip())


def product(artifacts: list[str]) -> dict:
    """A declaration entry carrying every required field."""
    return {
        "id": "test-product",
        "name": "Test Product",
        "process": "Process 1: Work Delivery Pipeline",
        "owner": "hq",
        "client": "Test Client",
        "client_value": "Test value",
        "artifacts": list(artifacts),
        "cadence": "Weekly (Mon 09:00 MSK)",
        "pacemaker_job": "test-job",
        "last_receipt": "test receipt",
    }


def tree(root: Path, declaration: object = None, artifacts: tuple[str, ...] = ()) -> Path:
    """A template-shaped tree: the shipped tool, the shipped skeleton, optionally a declaration."""
    (root / "tools").mkdir(parents=True, exist_ok=True)
    (root / "docs").mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / TOOL_REL, root / TOOL_REL)
    shutil.copy2(REPO_ROOT / EXAMPLE, root / EXAMPLE)
    for art in artifacts:
        (root / art).mkdir(parents=True, exist_ok=True)
    if declaration is not None:
        text = declaration if isinstance(declaration, str) else json.dumps(declaration, indent=2)
        (root / DECLARATION).write_text(text + "\n", encoding="utf-8")
    return root


def main() -> int:
    failures: list[str] = []

    if not (REPO_ROOT / TOOL_REL).is_file():
        print(f"FAIL {TOOL_REL} is missing — cannot gate a tool that is not there", file=sys.stderr)
        return 1
    if not (REPO_ROOT / EXAMPLE).is_file():
        print(f"FAIL {EXAMPLE} is missing — the onboarding exit names a skeleton nobody ships", file=sys.stderr)
        return 1

    # The skeleton must never name an artifact a bootstrapped factory cannot have.
    # `TEMPLATE/` is the one this factory ships and no other factory does: it was the
    # original unsatisfiable entry, and it is the regression this gate exists for.
    skeleton = json.loads((REPO_ROOT / EXAMPLE).read_text(encoding="utf-8"))
    for p in skeleton.get("products", []):
        for art in p.get("artifacts", []):
            if art.startswith("TEMPLATE/"):
                failures.append(
                    f"{EXAMPLE} declares artifact {art!r} — no bootstrapped factory can "
                    f"satisfy it, so every new factory would be permanently RED"
                )

    with tempfile.TemporaryDirectory(prefix="roadmap-gate-") as tmp:
        base = Path(tmp)

        # (a) FRESH, UN-ONBOARDED: the tool and the skeleton ship, no declaration.
        #     This is a factory that has just bootstrapped. RED is correct.
        rc, msg = run_tool(tree(base / "fresh"))
        if rc == 0:
            failures.append("fresh un-onboarded tree exited 0 — an undeclared factory must be RED")
        elif "products.json" not in msg:
            failures.append(f"fresh un-onboarded tree exited 1 but the reason does not name the declaration: {msg!r}")

        # (b) ONBOARDED: a declaration whose artifacts exist. The transition, forward.
        rc, msg = run_tool(
            tree(base / "onboarded", {"products": [product(["docs/artifact"])]}, ("docs/artifact",))
        )
        if rc != 0:
            failures.append(f"onboarded tree exited {rc} — filling the declaration must turn it GREEN: {msg!r}")

        # (c) SKELETON COPIED, NOT FILLED: the exit is named, the work is not done.
        #     Copying `products.example.json` to `products.json` must NOT go green —
        #     otherwise the documented exit would be a no-op anyone could fake.
        root = tree(base / "copied")
        shutil.copy2(REPO_ROOT / EXAMPLE, root / DECLARATION)
        rc, msg = run_tool(root)
        if rc == 0:
            failures.append(
                "a verbatim copy of the skeleton exited 0 — the placeholders' artifacts do "
                "not exist, so copying the exit must not be the same as taking it"
            )

        # (d) DECLARED BUT INCOMPLETE: names an artifact that is not there.
        rc, msg = run_tool(tree(base / "incomplete", {"products": [product(["docs/absent"])]}))
        if rc == 0:
            failures.append("a declaration naming a missing artifact exited 0 — declared is not delivered")

        # (e) MALFORMED: a broken declaration is reported, not raised.
        rc, msg = run_tool(tree(base / "malformed", "{ this is not json"))
        if rc == 0:
            failures.append("a malformed declaration exited 0")
        elif "Traceback" in msg:
            failures.append(f"a malformed declaration raised instead of reporting: {msg!r}")

        # (f) EMPTY: a declaration with no products is not an onboarded factory.
        rc, msg = run_tool(tree(base / "empty", {"products": []}))
        if rc == 0:
            failures.append("a declaration with no products exited 0 — an empty list is not onboarding")

    # (g) THIS TREE: the same law, checked against wherever this file is running.
    #     In the factory that is declared → GREEN; in `TEMPLATE/` it is undeclared →
    #     RED. Asserting the correspondence is what lets one file serve both.
    declared = False
    declaration_path = REPO_ROOT / DECLARATION
    if declaration_path.is_file():
        try:
            declared = bool(json.loads(declaration_path.read_text(encoding="utf-8")).get("products"))
        except (OSError, json.JSONDecodeError):
            declared = False
    rc, msg = run_tool(REPO_ROOT)
    if declared and rc != 0:
        failures.append(f"{DECLARATION} declares products but the tool exited {rc}: {msg!r}")
    if not declared and rc == 0:
        failures.append(
            f"{DECLARATION} is absent or empty yet the tool exited 0 — an un-onboarded tree "
            f"must be RED"
        )

    if failures:
        for f in failures:
            print(f"  FAIL {f}")
        return 1

    state = "declared → GREEN" if declared else "undeclared → RED (the correct state for this tree)"
    print(
        f"roadmap transition: clean — fresh/empty/malformed/incomplete all RED, filled "
        f"declaration GREEN, skeleton-copy not GREEN; this tree: {state}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
