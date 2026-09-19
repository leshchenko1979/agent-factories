#!/usr/bin/env python3
"""Shared: what makes a token a FIELD, and where the trailer that holds one ENDS.

The prose-as-data class (#88; ruled at ledger `n=405` clause 5). `detail` is free
prose, and prose quotes fields: a row that REPORTS "the trailer ends
'...tokens_out=...'" writes a token a naive reader takes for telemetry. One shape,
three failure directions, each measured on a live row:

* **prose must not SATISFY a field** — `tests/test_ledger_schema.py` split the whole
  detail on whitespace and validated every `k=v` token, so a row that QUOTED a
  trailer was read as declaring it (the #87 intake row, `n=561`).
* **prose must not TERMINATE a scan** — `_declared_revision` returned at the first
  `head=` token, so a row that DESCRIBED the field before naming its revision was
  refused. Fixed at `d244964`; the predicate it uses is the one below.
* **prose must not SUPPRESS a field** — `tools/ledger.py` tested `"tokens_out=" not
  in detail`, a SUBSTRING test, so a prose mention stopped the tool appending the
  measurement it had genuinely taken.

The remedy is ONE predicate, shared, so the class cannot recur per-site. Two rules,
and they answer different halves of the problem:

* **`keyed_value` — a DECLARATION carries a value that parses.** A token satisfies a
  field only when it starts with the key, then `=`, and then a value the key's own
  type accepts. `tokens_out=` is a MENTION — a writer that states no value has
  declared nothing — and so is `turns=36'`, which is a quotation of another row's
  trailer rather than a measurement this row took. Reading either as a declaration is
  how prose satisfies, terminates or suppresses a real field.
* **`trailer_tokens` — the canonical trailer is POSITIONAL.** The law defines it as
  the run of `key=value` tokens at the END of a `close` row's detail (`SKILL.md`
  section 11). A quoted trailer sits mid-sentence, so scoping to the trailing run is
  what stops a QUOTATION from being validated as a declaration.

The run is defined over tokens CARRYING `=`, not over well-formed field tokens,
because the writer's own trailer mixes the two: `n=565` ends `... duration=1845s;
board=closed; rework=unstated head=<sha> cost_usd=1.6375 tokens_out=5839849 turns=2`,
and a run that stopped at the first token failing a strict field test would drop the
telemetry that follows it. The two rules compose: scope decides WHICH tokens are
declarations, the predicate decides WHICH of those are fields.

What positional scoping does NOT do is rescue a row whose trailer is EMPTY. `n=135`,
`n=136` and `n=146` end in a bare slug AFTER their telemetry, so their trailer is
empty and NOTHING in them is validated. The law makes that correct — a trailer
followed by prose is not at the end — and no reading is lost: validation asks whether
a row's DECLARED trailer is well-formed, while a reader that wants a row's numbers
reads its detail. The two questions differ, and this module answers only the first.

Two limits, stated rather than implied away, because a claim of coverage this module
does not have is worse than the limit itself:

* **The suppression leg is LEXICAL, not positional.** `declares_field` asks "has the
  author already stated this measurement?" anywhere in the detail, while validation
  asks "is the canonical trailer well-formed?". The split is deliberate: appending a
  measurement the row already carries duplicates a field, and duplication is the worse
  error for a reader that takes the last occurrence as canonical. The cost is that a
  `close` row which QUOTES a parseable value (measured: the quoting rows are `intake`
  rows, `n=382` and `n=561`) suppresses that one append.
* **A value the key's type accepts is not a value the row took.** The predicate reads
  form, never provenance, and this module cannot tell a measurement from a number
  copied into a sentence.

This module holds no state and no tests. It is the one implementation; every call
site imports it, so a further site cannot invent a further reading.
"""

from __future__ import annotations

from typing import Iterator

# The keys `tools/ledger.py` supplies and the gates validate. `cost_usd`/`cost` are
# floats, the rest are non-negative integers. Named once, so a key added here is
# validated and appended everywhere at once.
TELEMETRY_FLOAT_KEYS: tuple[str, ...] = ("cost_usd", "cost")
TELEMETRY_INT_KEYS: tuple[str, ...] = ("tokens_in", "tokens_out", "in_tokens", "out_tokens", "turns")
TELEMETRY_KEYS: tuple[str, ...] = TELEMETRY_FLOAT_KEYS + TELEMETRY_INT_KEYS

def keyed_value(token: str, key: str) -> str | None:
    """The value when `token` DECLARES `key`, else None.

    A declaration is the key, then `=`, then a NON-EMPTY value. `tokens_out=` is a
    mention of the field, not a statement of it, and returning its empty value would
    let prose satisfy or suppress the field it merely names.
    """
    prefix = f"{key}="
    if not token.startswith(prefix):
        return None
    value = token[len(prefix):]
    return value or None

def declares_field(detail: str, key: str) -> bool:
    """True when `detail` declares `key` with a value that PARSES for that key's type.

    The append guard's question — has the author already stated this measurement? —
    and both halves are load-bearing. A token that merely NAMES the key (`tokens_out=`
    in a sentence) states nothing, and neither does one carrying an unparseable value:
    `turns=36'` is a quotation of another row's trailer. In both cases the tool
    appends the measurement it genuinely took, which is the class's third direction —
    prose must not SUPPRESS a field. The leg is lexical by design; the limit is stated
    in the module docstring.
    """
    for token in str(detail).split():
        value = keyed_value(token, key)
        if value is not None and _value_parses(key, value):
            return True
    return False

def trailer_tokens(detail: str) -> list[str]:
    """The maximal run of `=`-carrying tokens at the END of `detail`, in order.

    The law's own definition (`SKILL.md` section 11): the canonical trailer is the run
    of `key=value` tokens at the end of the detail. A row whose detail ends in prose
    has an EMPTY trailer, and a row that quotes a trailer mid-sentence has one that
    excludes the quotation — which is the whole point.
    """
    run: list[str] = []
    for token in reversed(str(detail).split()):
        if "=" not in token:
            break
        run.append(token)
    run.reverse()
    return run

def declared_telemetry(detail: str) -> list[tuple[str, str]]:
    """`(key, value)` for every telemetry field DECLARED in the canonical trailer.

    Both halves of the predicate, in one place: the token must sit in the trailing run
    (positional) and must carry a non-empty value for a telemetry key (lexical).
    """
    found: list[tuple[str, str]] = []
    for token in trailer_tokens(detail):
        for key in TELEMETRY_KEYS:
            value = keyed_value(token, key)
            if value is not None:
                found.append((key, value))
    return found

def telemetry_value_problem(key: str, value: str) -> str | None:
    """The readable problem when `value` does not parse for `key`'s type, else None.

    The message text is part of the contract: the gate's self-probes assert on it, so
    it moved here verbatim rather than being reworded into a second vocabulary.
    """
    if key in TELEMETRY_FLOAT_KEYS:
        try:
            number = float(value.rstrip("$"))
        except ValueError:
            return f"invalid numeric format for cost: {value!r}"
        if number < 0:
            return f"cost cannot be negative: {value!r}"
        return None
    try:
        count = int(value)
    except ValueError:
        return f"invalid integer format for {key}: {value!r}"
    if count < 0:
        return f"count {key} cannot be negative: {value!r}"
    return None

def telemetry_problems(detail: str) -> Iterator[str]:
    """Every readable problem with the telemetry `detail` DECLARES in its trailer."""
    for key, value in declared_telemetry(detail):
        problem = telemetry_value_problem(key, value)
        if problem is not None:
            yield problem

def _value_parses(key: str, value: str) -> bool:
    """True when `value` is a value `key` accepts.

    `duration` is the one key the tool appends that is NOT telemetry: it carries its
    unit (`duration=1845s`, `tools/ledger.py`), so it is read here rather than pushed
    into `telemetry_value_problem`'s vocabulary, where a bare `1845` would parse and a
    reader of the gate's messages would find a key it never validates.
    """
    if key == "duration":
        try:
            float(value.rstrip("s"))
        except ValueError:
            return False
        return True
    return telemetry_value_problem(key, value) is None
