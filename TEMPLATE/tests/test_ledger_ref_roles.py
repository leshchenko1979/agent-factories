#!/usr/bin/env python3
"""Gate: every ROLE a receipt asserts for a named row is the role that row CARRIES (#330).

`tools/ledger.py` validates a `row:` pointer for EXISTENCE only — the token must be numeric
and at most the current max `n`. A number composed from a stale read therefore passes the
write path while naming a DIFFERENT row, and a reader who follows it lands on another
lane's event and reads a green. #330's own instance is exactly that: the Triage
2026-10-05T12 patrol receipt carried eight refs six low, every one of them resolving to the
Worker lane's close rows.

Ruling n=3362 chose the predicate BY MEASUREMENT over two alternatives: "the ref's subject
is claimed in the receipt's detail" passes all eight of that receipt's refs and would red 68
of 657 row-refs, while "the noun the detail asserts for a ref is that row's EVENT" bites the
instance and its siblings at 12 of 288. So the leg judges a ROLE MATCH, over the three roles
the ruling names — `intake`, `dispatch`, `close` — and this gate is its arm set:

  * the role match BITES on a mismatch, and the problem names the actual event, because a
    reader who is told only "wrong" cannot tell whether the row moved or the prose did;
  * a MATCHING role is silent (the discriminating arm: a leg that reds everything passes
    every bite arm without it);
  * a COMPOUND label asserts neither role — `ruling/dispatch rows n=6` is not a `dispatch`
    assertion, and counting it was measured as a false positive before the lookbehind;
  * the roles OUTSIDE the ruling's scope (`run`, `ruling`, `claim`) are not judged, which is
    a declared non-goal and not an accident of the pattern;
  * the exemption store's three states are distinct — ABSENT is the shipped empty state and
    not a defect, a DECLARED entry excuses its triple and prints its reason, and a STALE
    entry is a PROBLEM, because a store that has rotted into a rubber stamp must be visible
    on the round it rots;
  * a store that cannot be honoured (unparseable, no `exempt` list, an entry with no
    reason) is a problem and never a silent excuse — an unreadable exemption would red every
    adjudicated residual while reading as an excuse;
  * the LIVE arm reconciles this factory's own store against this factory's own ledger, so
    an entry that stops describing the ledger reds the audit rather than the patrol alone.

The population PRINTS in both states: `0` must read as "this box excuses nothing" and never
as "the check did not look" — the #506 false-clean, one instrument over.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STORE = REPO / "docs" / "ledger-ref-roles-exemptions.json"
LEDGER = REPO / "evidence" / "ledger.jsonl"
RUNNER_PATH = REPO / "tools" / "patrol_host_state.py"

def load_runner():
    spec = importlib.util.spec_from_file_location("patrol_host_state_ref_roles", RUNNER_PATH)
    assert spec and spec.loader, f"cannot load {RUNNER_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def _row(n: int, event: str, detail: str = "probe") -> dict:
    return {"n": n, "ts": "2026-10-17T00:00:00Z", "event": event,
            "actor": "triage", "subject": f"#{n}", "detail": detail}

def _leg(module, rows, *, store=None):
    return module.ledger_ref_roles_leg(
        rows, read_at="2026-10-17T00:00:00Z",
        exemptions_path=store if store is not None else Path("/nonexistent/store.json"),
    )

def _store_file(payload) -> Path:
    directory = Path(tempfile.mkdtemp(prefix="ref-roles-gate-"))
    path = directory / "ledger-ref-roles-exemptions.json"
    path.write_text(
        payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8"
    )
    return path

def check(module) -> tuple[list[str], int]:
    """Every arm, in one list, plus how many cases this gate examined."""
    problems: list[str] = []
    cases = 0

    # --- arm 1: the role match BITES, and the problem names what the row actually is -----
    cases += 1
    leg = _leg(module, [
        _row(1, "intake", "INTAKE #900"),
        _row(2, "close", "CLOSE #900. Intake row n=2."),
    ])
    if not leg["problems"]:
        problems.append("arm 1: a receipt asserting `intake` of a CLOSE row read clean")
    elif "is a `close`" not in " ".join(leg["problems"]):
        problems.append(
            f"arm 1: the problem does not name the row's actual event: {leg['problems']}"
        )
    if len(leg["coverage"]["residuals"]) != 1:
        problems.append(f"arm 1: expected 1 residual, got {leg['coverage']['residuals']}")

    # --- arm 2: a MATCHING role is silent (the discriminating half) ----------------------
    cases += 1
    leg = _leg(module, [
        _row(1, "intake", "INTAKE #900"),
        _row(2, "close", "CLOSE #900. Intake row n=1."),
    ])
    if leg["problems"]:
        problems.append(f"arm 2: a CORRECT role assertion red the leg: {leg['problems']}")
    if leg["coverage"]["assertions_examined"] != 1:
        problems.append(
            f"arm 2: expected 1 assertion examined, got {leg['coverage']['assertions_examined']}"
        )

    # --- arm 3: a COMPOUND label asserts NEITHER role ------------------------------------
    cases += 1
    leg = _leg(module, [
        _row(1, "close", "CLOSE #900"),
        _row(2, "run", "ruling/dispatch rows n=1 settled"),
    ])
    if leg["coverage"]["assertions_examined"] != 0:
        problems.append(
            "arm 3: a compound label `ruling/dispatch rows n=X` was counted as an "
            f"assertion ({leg['coverage']['assertions_examined']}) — the measured false "
            "positive the lookbehind exists to keep out"
        )
    if leg["problems"]:
        problems.append(f"arm 3: a compound label red the leg: {leg['problems']}")

    # --- arm 4: the roles OUTSIDE the ruling's scope are not judged ----------------------
    cases += 1
    leg = _leg(module, [
        _row(1, "close", "CLOSE #900"),
        _row(2, "run", "run row n=1 and claim row n=1 and ruling row n=1"),
    ])
    if leg["coverage"]["assertions_examined"] != 0:
        problems.append(
            "arm 4: a role outside the judged set was examined "
            f"({leg['coverage']['assertions_examined']}) — the scope is intake/dispatch/"
            "close by ruling, and widening it is a measurement, never an accident"
        )

    # --- arm 5: an ABSENT store is the shipped empty state, not a failure ----------------
    cases += 1
    leg = _leg(module, [
        _row(1, "close", "CLOSE #900. Intake row n=1."),
    ])
    if leg["coverage"]["exemptions_declared"] != 0 or leg["coverage"]["exempted"] != 0:
        problems.append(f"arm 5: an absent store declared something: {leg['coverage']}")
    if len(leg["problems"]) != 1:
        problems.append(
            f"arm 5: an absent store must leave the residual standing, got {leg['problems']}"
        )

    # --- arm 6: a DECLARED entry excuses its triple and PRINTS its reason ----------------
    cases += 1
    store = _store_file({"exempt": [
        {"row": 2, "asserted": "intake", "asserted_row": 1,
         "reason": "CROSS-FACTORY — probe"},
    ]})
    leg = _leg(module, [
        _row(1, "close", "CLOSE #900"),
        _row(2, "run", "Intake row n=1."),
    ], store=store)
    if leg["problems"]:
        problems.append(f"arm 6: a declared exemption did not excuse: {leg['problems']}")
    if leg["coverage"]["exempted"] != 1 or leg["coverage"]["unresolved"] != 0:
        problems.append(f"arm 6: counts wrong after excusal: {leg['coverage']}")
    if not any("CROSS-FACTORY — probe" in line for line in leg["excused"]):
        problems.append(f"arm 6: the reason was not printed: {leg['excused']}")

    # --- arm 7: a STALE entry is a PROBLEM, never a silent subtraction ------------------
    cases += 1
    store = _store_file({"exempt": [
        {"row": 99, "asserted": "intake", "asserted_row": 1, "reason": "STALE — probe"},
    ]})
    leg = _leg(module, [_row(1, "close", "CLOSE #900")], store=store)
    if not any("matches no live mismatch" in p for p in leg["problems"]):
        problems.append(
            f"arm 7: a stale exemption read clean: {leg['problems']}"
        )

    # --- arm 8: an entry with NO reason is a problem (the reader's own strictness) ------
    cases += 1
    store = _store_file({"exempt": [
        {"row": 1, "asserted": "intake", "asserted_row": 2},
    ]})
    entries, store_problems = module.load_ref_role_exemptions(store)
    if not store_problems or "no `reason`" not in " ".join(store_problems):
        problems.append(
            f"arm 8: a reason-less entry was honoured or silently dropped: {store_problems}"
        )
    if entries:
        problems.append(f"arm 8: a reason-less entry still became an exemption: {entries}")

    # --- arm 9: an UNPARSEABLE store cannot silently excuse ----------------------------
    cases += 1
    store = _store_file("{not json")
    entries, store_problems = module.load_ref_role_exemptions(store)
    if not store_problems:
        problems.append("arm 9: an unparseable store produced no problem")
    if entries:
        problems.append(f"arm 9: an unparseable store still excused something: {entries}")

    # --- arm 10: the LIVE store reconciles against the LIVE ledger ----------------------
    cases += 1
    if STORE.is_file():
        if not LEDGER.is_file():
            problems.append(f"live arm: the store exists but the ledger is absent ({LEDGER})")
        else:
            rows = [json.loads(line) for line in
                    LEDGER.read_text(encoding="utf-8").splitlines() if line.strip()]
            leg = module.ledger_ref_roles_leg(
                rows, read_at="gate", exemptions_path=STORE
            )
            cov = leg["coverage"]
            if cov["exemptions_declared"] != cov["exempted"]:
                problems.append(
                    f"live arm: {cov['exemptions_declared']} declared but "
                    f"{cov['exempted']} matched a live mismatch — a stale entry excuses "
                    f"nothing: {leg['problems']}"
                )
            if cov["unresolved"]:
                problems.append(
                    f"live arm: {cov['unresolved']} unadjudicated role mismatch(es) — "
                    f"{[p for p in leg['problems'] if 'matches no live' not in p]}"
                )

    return problems, cases

def main() -> int:
    if not RUNNER_PATH.is_file():
        print(f"NOT RUN — the reader is absent: {RUNNER_PATH}", file=sys.stderr)
        return 1

    module = load_runner()
    problems, cases = check(module)

    live = "absent (empty state)"
    population = "0 assertion(s)"
    if STORE.is_file() and LEDGER.is_file():
        rows = [json.loads(line) for line in
                LEDGER.read_text(encoding="utf-8").splitlines() if line.strip()]
        leg = module.ledger_ref_roles_leg(rows, read_at="gate", exemptions_path=STORE)
        cov = leg["coverage"]
        live = f"{cov['exemptions_declared']} declared exemption(s)"
        population = (
            f"{cov['assertions_examined']} assertion(s) over {cov['rows_read']} ledger "
            f"row(s): {len(cov['residuals'])} mismatch(es), {cov['exempted']} "
            f"declared-exempt, {cov['unresolved']} unresolved"
        )

    summary = (
        f"table {live}; {population}; probe: {cases} case(s) examined"
    )
    if problems:
        print(f"FAIL — {summary}", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print(
            "\nAn exemption is a DECLARED adjudication: name the triple and state the "
            "class and the reason. Fix the store, or fix the pointer — do not leave a "
            "residual excused by an entry nobody can read.",
            file=sys.stderr,
        )
        return 1

    print(f"PASS — {summary}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
