"""Per-gate time budgets, read from `registry/gates.json` (issue #94, ruling n=744).

A gate's cap is a DECLARED MULTIPLE of a MEASURED runtime -- `budget_sec = margin_x
x measured_sec` -- never a round number. A cap picked by feel is uncalibrated in
both directions: too low, it kills a healthy gate and reports a timeout as a
verdict; too high, it hides a hung one. So each gate's cap is derived, and the
margin, the measured runtime and the ABSOLUTE revision the measurement was taken
at are declared together, so the number carries its own basis and a reader can
recompute it.

WHY A SEPARATE MODULE. `tools/registry.py` owns the FACTORY registry and validates
its manifest at import time; a gate budget is a timing concern with its own
manifest, and importing the fleet validator to read a timeout would couple two
unrelated surfaces -- `audit.py` would then fail on a missing `fleet.json` before
it ever reached a gate. This module mirrors that module's CONVENTION -- a path
constant, an environment override, a `*_path()` resolver, and a `load_*()` that
raises a named error -- without inheriting its fleet semantics.

WHERE THE TWO CONVENTIONS DIFFER, AND WHY. An ABSENT fleet manifest is an error: a
factory that declares no fleet has an unanswered question. An ABSENT gate-budget
manifest is NOT an error: a factory that has taken no measurements runs on the
declared fallback, and the audit PRINTS every gate that used it. A manifest that
EXISTS and is malformed IS an error -- an unreadable budget set is indistinguishable
from no budget set, and defaulting over it would silently re-cap every gate.

THE VALUES ARE NOT THE IMPLEMENTING LANE'S (n=574 PART 5). This module reads them;
it never invents one.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

GATES_MANIFEST_PATH = REPO_ROOT / "registry" / "gates.json"
GATES_MANIFEST_ENV = "OC_GATES_MANIFEST"

# The LAST-RESORT cap, used only when no manifest exists at all. It matches the
# value the template ships (`TEMPLATE/registry/gates.example.json`), so a factory
# that never measures behaves the same before and after it copies the example. It
# is deliberately the largest declared budget rather than a round number, so the
# fallback is never TIGHTER than a gate the factory did measure.
FALLBACK_DEFAULT_SEC = 120.0

# A timeout gets its OWN exit code -- the one `timeout(1)` uses -- so a killed gate
# is never confused with the `99` this module's caller returns for an unexpected
# exception. A gate that ran out of budget is UNKNOWN: it did not fail, it did not
# pass, and it must never be counted in a pass total.
TIMEOUT_EXIT_CODE = 124

# Every entry must carry its own BASIS, not just a number: a `budget_sec` with no
# `measured_sec` beside it is a cap picked by feel, which is the defect the law
# names. The loader refuses the shape rather than reading a bare number.
ENTRY_KEYS = ("budget_sec", "measured_sec", "measured_at", "margin_x")

# How far `budget_sec` may sit from `margin_x x measured_sec` before the entry is
# refused. MEASURED, not chosen: over the live 44-gate manifest the largest
# deviation is 0.014 absolute and 0.012% relative, both pure 2-decimal rounding,
# so a 1% band carries ~83x headroom over the worst real entry while still
# refusing a budget that was edited away from its stated basis.
MARGIN_LAW_TOLERANCE = 0.01


class GateBudgetManifestError(Exception):
    """The gate-budget manifest exists but is unparseable or incomplete."""


@dataclass(frozen=True)
class GateBudgets:
    """The declared caps: a default, where that default came from, and the per-gate table."""

    default_sec: float
    default_source: str
    gates: dict[str, float] = field(default_factory=dict)

    def resolve(self, key: str | None) -> tuple[float, str]:
        """The budget for a gate key, and whether it was DECLARED or fell to the default.

        The second element is the point: a gate with no entry is not an error, but
        the audit must be able to PRINT which gates used the default, because a
        declared default with a printed population is not an exempt-by-silence
        surface, while an unprinted fallback is.
        """
        if key is not None and key in self.gates:
            return self.gates[key], "declared"
        return self.default_sec, "default"


def gates_manifest_path() -> Path:
    """Where the budget manifest is read from: the environment override, else the default.

    The override exists so a probe can point the reader at a manifest it built,
    without writing into the live store.
    """
    override = os.environ.get(GATES_MANIFEST_ENV)
    return Path(override) if override else GATES_MANIFEST_PATH


def gate_key_for_cmd(cmd: list[str], repo_root: Path) -> str | None:
    """The manifest key for a gate command: the repo-relative path of the file it runs.

    THE TRAP THIS EXISTS FOR. The manifest is keyed by a gate's repo-relative path,
    but a command does NOT put that path in a fixed position: `[python, -m, pytest,
    tests/X.py]` carries it LAST, while `[python, tools/ledger.py, verify]` carries
    it FIRST. A `cmd[-1]` lookup therefore misses EVERY gate that takes arguments --
    and misses it silently, because a miss falls through to the default rather than
    failing. So the key is derived by asking which ARGUMENT resolves to a file under
    the repo root, which is the property the manifest key actually names.

    An argument that resolves OUTSIDE the repo root is skipped, and that is load
    bearing rather than defensive: `sys.executable` is an absolute path to a real
    file, so a naive `is_file()` test would return `/usr/bin/python3` as the key for
    every gate in the tree.

    The bound: the first resolving argument wins, so a command naming two gate files
    keys on the first. No registration in this tree does that.
    """
    root = Path(repo_root).resolve()
    for arg in cmd:
        if not arg or arg.startswith("-"):
            continue
        candidate = Path(arg)
        if not candidate.is_absolute():
            candidate = root / candidate
        try:
            resolved = candidate.resolve()
            if not resolved.is_file():
                continue
            return resolved.relative_to(root).as_posix()
        except (OSError, ValueError):
            continue
    return None


def load_gate_budgets(path: Path | None = None) -> GateBudgets:
    """Read the gate-budget manifest. Raises `GateBudgetManifestError` on a malformed one.

    An ABSENT manifest is not a defect and returns the declared fallback with an
    empty table; a manifest that exists and cannot be read is a defect and raises,
    because the two are otherwise the same output for a caller that only sees caps.
    """
    target = path or gates_manifest_path()
    if not target.is_file():
        return GateBudgets(
            default_sec=FALLBACK_DEFAULT_SEC,
            default_source=f"no manifest at {target} — declared fallback",
            gates={},
        )
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise GateBudgetManifestError(f"{target}: cannot read the manifest — {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GateBudgetManifestError(f"{target}: does not parse as JSON — {exc}") from exc
    if not isinstance(data, dict):
        raise GateBudgetManifestError(f"{target}: the manifest must be a JSON object")

    default = data.get("default")
    if not isinstance(default, dict):
        raise GateBudgetManifestError(f"{target}: no `default` object")
    default_sec = default.get("budget_sec")
    if not _is_positive_number(default_sec):
        raise GateBudgetManifestError(
            f"{target}: default.budget_sec must be a positive number, not {default_sec!r}"
        )

    entries = data.get("gates", {})
    if not isinstance(entries, dict):
        raise GateBudgetManifestError(f"{target}: `gates` must be a JSON object")

    gates: dict[str, float] = {}
    for key, entry in entries.items():
        where = f"{target}: gates[{key!r}]"
        if not isinstance(entry, dict):
            raise GateBudgetManifestError(f"{where} is not an object")
        for name in ENTRY_KEYS:
            if name not in entry:
                raise GateBudgetManifestError(
                    f"{where} has no `{name}` key — a budget with no stated basis is a "
                    f"cap picked by feel, which is the defect this manifest exists to fix"
                )
        for name in ("budget_sec", "measured_sec", "margin_x"):
            if not _is_positive_number(entry[name]):
                raise GateBudgetManifestError(
                    f"{where}.{name} must be a positive number, not {entry[name]!r}"
                )
        if not isinstance(entry["measured_at"], str):
            raise GateBudgetManifestError(
                f"{where}.measured_at must be a string revision, not {entry['measured_at']!r}"
            )
        declared = entry["margin_x"] * entry["measured_sec"]
        budget = entry["budget_sec"]
        if abs(budget - declared) > MARGIN_LAW_TOLERANCE * budget:
            raise GateBudgetManifestError(
                f"{where}: budget_sec {budget} is not margin_x x measured_sec "
                f"({entry['margin_x']} x {entry['measured_sec']} = {round(declared, 4)}) "
                f"within {MARGIN_LAW_TOLERANCE:.0%} — the entry states a basis its own "
                f"number does not follow"
            )
        gates[key] = float(budget)

    return GateBudgets(
        default_sec=float(default_sec),
        default_source=f"{target}:default",
        gates=gates,
    )


def _is_positive_number(value: object) -> bool:
    """True for a real number above zero. `bool` is excluded: `True` is not a budget."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0
