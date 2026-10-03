"""The reconstructed-claim predicate, shared by the gate and by `verify`'s printer.

**Owns:** the reconstruction vocabulary and the interval computation — which rows are
reconstructed claims, whether a row names its basis, which close row answered a claim, and
the interval recomputed from the two rows' own `ts` values.

WHY THIS MODULE EXISTS. `n=687` clause 1 moved the interval from DECLARED to
RECOMPUTED-AND-PRINTED, which puts the SAME recomputation in two places: the gate
(`tests/test_reconstructed_claim_declared.py`) judges the self-declaration and prints the
interval, and `tools/ledger.py verify` prints it beside its `excused:` lines. Two private
copies of one predicate is this factory's own ruled class (`n=405` clause 5, `n=599`): they
drift on exactly the inputs that matter, and the drift is invisible because each copy is
self-consistent. So the predicate lives HERE and both call sites import it, on the same
bare-neighbour import `tools/ledger.py` already uses for `ledger_declaration` and
`field_predicate`.

WHAT THIS MODULE DOES NOT OWN. The BOUNDARY (which rows a ruling governs) is
`ledger_declaration.boundary_for`, and the declaration's READER is `tests/ledger_boundary.py`.
The verdict — is a missing basis a problem, is an empty population a skip — belongs to the
caller. This module computes and reports; it never judges.
"""

from __future__ import annotations

from ledger_declaration import parse_ts
from field_predicate import declares_token, own_voice_text

# The token pair that puts a row in the population. Read LEXICALLY anywhere in the detail,
# scoped by the caller to event `claim` — a row of another event that merely QUOTES it is
# out of the population before the predicate is asked (`n=602`).
RECONSTRUCTION_KEY = "claim"
RECONSTRUCTION_VALUE = "reconstructed"

# The canonical marker a reconstruction names its basis under. A colon-bearing marker, not a
# `=`-bearing trailer token, and that is load-bearing: `trailer_tokens` collects only tokens
# carrying `=`, so `BASIS:` can never be part of the canonical run and can never be confused
# with a declared measurement. WHAT the basis says is prose, and prose is not this module's
# to parse — the marker's presence is all that is asked.
BASIS_MARKER = "BASIS:"


def reconstructed_claims(rows: list[dict]) -> list[dict]:
    """Every event `claim` row that declares itself a reconstruction.

    The population is DOUBLY scoped: the event scope keeps a ruling row that merely defines
    the token from reading as a reconstruction, and the token scope keeps an ordinary claim
    from reading as one. Both are required — either alone finds the wrong rows.
    """
    return [
        row
        for row in rows
        if row.get("event") == "claim"
        and declares_token(
            own_voice_text(row.get("detail", "")),
            RECONSTRUCTION_KEY,
            RECONSTRUCTION_VALUE,
        )
    ]


def names_basis(detail: str) -> bool:
    """True when this detail names the basis it rests on under the canonical marker,
    IN THE ROW'S OWN VOICE.

    The marker is read over `own_voice_text(detail)`, never the raw detail, because the two
    legs of one self-declaration must share ONE scope. The population leg asks whether the
    row declares itself reconstructed; this leg asks what it rests on. Where a row merely
    QUOTES another row's defect inside a parenthetical aside — `(… with no BASIS: marker …)`
    — the raw substring test finds a `BASIS:` that is not this row's, satisfies the basis
    leg, and MASKS the fact that the quoting row states no basis of its own. So the same
    aside that keeps a row out of the population also stops its quoted marker from answering
    the basis leg: one scope, two readers, no masking.

    Forward-only, like the population: no row is rewritten, and a row that leaves the
    population simply stops being judged here.
    """
    return BASIS_MARKER in own_voice_text(detail)


def close_row_for(claim_row: dict, rows: list[dict]) -> dict | None:
    """The close row of this claim's WORK UNIT, or None when there is none.

    Resolved by SUBJECT, never by adjacency: a row's actor is read from its own identity
    fields, and row order is not an identity field. The row number is the tie-break, and it
    is the row's OWN identity rather than a fact about its neighbour — among the close rows
    of this subject, the earliest at or after the claim row is the one that answered it.
    """
    subject = claim_row.get("subject")
    number = claim_row.get("n")
    if not isinstance(number, int):
        return None
    candidates = [
        row
        for row in rows
        if row.get("event") == "close"
        and row.get("subject") == subject
        and isinstance(row.get("n"), int)
        and row["n"] >= number
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda row: row["n"])


def interval_line(claim_row: dict, rows: list[dict]) -> str:
    """The recomputed interval for this claim, as the line a caller PRINTS.

    The interval is RECOMPUTED from the two rows' own `ts` values and printed, never
    declared and never judged. Both sides are tool-sourced — the claim's own `ts` and its
    close row's — and no expected number is typed anywhere in this function.

    A work unit with no close row yet is NOT a defect: a lane reconstructing its claim
    mid-work has not closed yet, and this line says so rather than failing the row.
    """
    number = claim_row.get("n")
    subject = claim_row.get("subject")
    close = close_row_for(claim_row, rows)
    if close is None:
        return (
            f"reconstructed claim: n={number} (subject {subject}) interval=no close row yet"
        )
    try:
        recomputed = int((parse_ts(close["ts"]) - parse_ts(claim_row["ts"])).total_seconds())
    except (ValueError, TypeError):
        return (
            f"reconstructed claim: n={number} (subject {subject}) interval=uncomputable "
            f"(an unparseable ts on n={number} or n={close.get('n')})"
        )
    return (
        f"reconstructed claim: n={number} (subject {subject}) interval={recomputed}s "
        f"(claim ts {claim_row.get('ts')} -> close n={close.get('n')} ts {close.get('ts')})"
    )
