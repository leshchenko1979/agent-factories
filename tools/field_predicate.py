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

import re
from typing import Iterator

# How a token is delimited: any run of non-whitespace. Named once because two readers
# need it and they must agree — `trailer_tokens` counts tokens from the end, and
# `split_canonical_run` locates the same token by character offset.
_NON_SPACE = re.compile(r"\S+")

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

def token_key(token: str) -> str | None:
    """The key `token` DECLARES, or None when it declares none.

    The KEY half of `keyed_value`, and the same declaration shape: the key, then `=`,
    then a NON-EMPTY value. It exists because a reader sometimes needs to ask WHICH
    fields a token sequence declares rather than what ONE named field's value is —
    `tools/ledger.py repair` asks it of both the row's canonical run and the text it is
    about to append, to refuse an append that re-declares a field the row already
    carries (#104, ruled at ledger `n=620` PART 4).

    A private `token.split("=")[0]` at that call site is the defect this module exists
    to close — one field, one predicate — and the difference is not stylistic: this
    form treats `head=` as a MENTION with no key, exactly as `keyed_value` treats it as
    a mention with no value, so a prose note that merely NAMES a field cannot be read as
    declaring it.

    The split is on the FIRST `=`, so a value may itself contain one.
    """
    key, sep, value = token.partition("=")
    if not sep or not key or not value:
        return None
    return key

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

def declares_token(detail: str, key: str, value: str) -> bool:
    """True when `detail` carries `key=value` exactly — a WORD-valued token.

    `declares_field` answers for a NUMERIC key and type-tests the value it finds;
    this answers for a token whose value is a word, where the type test would
    reject the only value the token may carry. Two names rather than one function
    with a flag, because the questions differ and a reader must be able to tell
    which one it is asking.

    The scan is LEXICAL, anywhere in the detail, and the CALLER scopes it by the
    row's own event: the token describes a `claim` row, so a row of another event
    that merely QUOTES it is out of the population before the predicate is asked —
    measured need, `n=602`, a ruling row whose detail states the token it defines.
    Scoping positionally to the canonical trailer was the alternative and is
    rejected: a token written mid-detail would then be silently invisible, and a
    declaration no reader can see is worse than one a reader can check.

    The token is read VERBATIM, like every other value here — punctuation is not
    stripped, so `claim=reconstructed.` is not a declaration of
    `claim=reconstructed`. The writer states the token as the token.
    """
    for token in str(detail).split():
        if keyed_value(token, key) == value:
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

def declared_keys(detail: str) -> list[str]:
    """The keys DECLARED in `detail`'s canonical trailer, in order, deduplicated.

    The question `tools/ledger.py repair` must ask twice before it writes: which fields
    does the row's run already carry, and which does the text I am about to append
    introduce? An append that answers the same key twice is refused (#104, ruled at
    ledger `n=620` PART 4), and the refusal is why the sentence "a `key=value` append
    EXTENDS the run and is safe either way" now holds only when the key is NEW.

    Both halves of the predicate compose here, and neither is optional: the run is
    POSITIONAL, so a token quoted mid-detail is not one of this row's declarations; and
    the key is read through `token_key`, so a bare `head=` MENTION contributes no key.
    A caller that scanned the whole detail, or split on `=` itself, would answer a
    different question and refuse lawful repairs.
    """
    keys: list[str] = []
    for token in trailer_tokens(detail):
        key = token_key(token)
        if key is not None and key not in keys:
            keys.append(key)
    return keys

# The close trailer's `rework` field — the disposition a close DECLARES. Its domain is
# exactly two canonical values, ruled at ledger `n=386` clause 3 (reusing #53 clauses
# 3/4): `rework=#N` names the rework entry THIS close produced, and `rework=none`
# states that it produced none. ABSENCE stays `unstated`, never read as `none` (#53
# clause 2) — an unrecorded disposition is UNKNOWN, never a value.
#
# `rework` is deliberately NOT in TELEMETRY_KEYS, and the distinction is load-bearing:
# `tools/telemetry.py::format_detail_string` never emits it, so the token is the
# AUTHOR's and its ABSENCE is the normal case, never a defect (#106). A reader must
# therefore ask whether a value was DECLARED, not whether the field is present.
REWORK_KEY = "rework"

def declared_rework(detail: str) -> list[str]:
    """Every `rework` value `detail`'s CANONICAL TRAILER declares, in order.

    The ONE positional read of this field, shared by both call sites — `tools/audit.py`
    counts declarations from it and `tests/test_rework_declared_landed.py` resolves the
    references it returns. A private `token.split("=")` at either would be the class
    `n=405` PART 5 rules: one field, one predicate. Classification of a value is NOT
    here: the vocabulary (`#N` · `none` · `unstated`) belongs beside the domain
    constants in `tools/audit.py::rework_bucket`, exactly as `declared_outcome` sits
    beside `OUTCOME_DOMAIN`.

    The run is POSITIONAL (`trailer_tokens`), so a token quoted mid-sentence is prose and
    never becomes a declaration — the reading `n=633` needed, whose false `rework=#102`
    is quoted in other rows' prose. Values are read VERBATIM, like every other value here.

    A LIST, not a single value, because the two callers differ on the multiplicity they
    can see: the resolving gate must report EVERY declaration it finds, while a count
    reads one disposition per row. The law gives a row one token (§8: a field carrying
    two values has no canonical reading, which is why `tools/ledger.py repair` refuses to
    append a key the run already declares), and the live population obeys it — measured
    0 of 92 close rows carry two at ledger `n=712`. Stated so a reader that takes
    `values[0]` knows the bound it is relying on rather than assuming it.
    """
    return _declared_values(detail, REWORK_KEY)

def split_canonical_run(detail: str) -> tuple[str, str]:
    """`(head, run)` — the detail split at the START of its canonical trailing run.

    The inverse of `trailer_tokens`, and the operation a WRITER needs: text added to a
    detail must go BEFORE the run, because text placed after it TERMINATES the run and
    the row's declared telemetry leaves the trailing run that every trailer-scoped
    reader stops at. Measured on `n=303`, whose telemetry was canonical when the row was
    written and fell outside the trailer the day a repair note was appended after it
    (#91, ruled at ledger `n=572` PART 3).

    `run` is the verbatim tail of the input, from the first run token's first character
    to the end of the string, so the caller can re-join without normalising anything:
    interior spacing, punctuation and any trailing whitespace are the author's and stay
    untouched. A detail with an empty run returns `(detail, "")` — there is nothing to
    displace, and the caller appends as it always did.
    """
    run = trailer_tokens(detail)
    if not run:
        return detail, ""
    tokens = list(_NON_SPACE.finditer(detail))
    start = tokens[len(tokens) - len(run)].start()
    return detail[:start], detail[start:]

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

def mentioned_telemetry(detail: str) -> list[tuple[str, str]]:
    """`(key, value)` for every telemetry-shaped token in `detail`, ANYWHERE.

    A MENTION, never a declaration — and the name carries that, because the two were
    once the same scan and the confusion IS the defect this module closes. This exists
    for VISIBILITY alone: a reader that wants to show a human which rows carry
    telemetry-shaped tokens OUTSIDE the canonical trailer (issue #90's exclusion
    print) needs the anywhere-scan. A reader that wants a NUMBER must use
    `declared_telemetry` and get the trailer's.

    Aggregating this list is instance (a) of the class: `n=382` is an intake row whose
    `cost_usd=26` is a CENSUS — "26 close rows carry cost_usd" — and read as a value
    it became the second-largest single cost in the ledger.
    """
    found: list[tuple[str, str]] = []
    for token in str(detail).split():
        for key in TELEMETRY_KEYS:
            value = keyed_value(token, key)
            if value is not None:
                found.append((key, value))
                break
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

def _declared_values(detail: str, key: str) -> list[str]:
    """Every `key` value `detail`'s CANONICAL TRAILER declares, in order.

    The positional read of a WORD-valued field, extracted so the two fields that need it
    share ONE loop rather than two copies — `declared_rework` and
    `declared_telemetry_provenance` differ only in the key they ask for, and a
    copy-pasted loop is how one of them silently drifts from the other.

    A LIST, not a single value, because the callers differ on the multiplicity they can
    see: a resolving gate must report EVERY declaration it finds, while a count reads one
    disposition per row.
    """
    values: list[str] = []
    for token in trailer_tokens(detail):
        value = keyed_value(token, key)
        if value is not None:
            values.append(value)
    return values

# The close trailer's `telemetry` field — the PROVENANCE of the measurement keys above,
# and the field #129 introduced for the absence case. `#130` (HQ ruling, three parts)
# made it the answer to a question no structural read of a row can settle: HQ measured
# all three candidate predicates — POSITION, COMPLETENESS and VALUE EQUALITY — and each
# FAILED, so provenance must be CARRIED by the row, never inferred from it. The
# requirement: a consumer must tell a value the tool TOOK from one an author TYPED
# WITHOUT re-deriving the ledger.
#
# `telemetry` is deliberately NOT in TELEMETRY_KEYS, for `rework`'s reason and one of its
# own. Like `rework` it declares no measurement, so it must not enter any aggregate that
# sums or counts the keys. Unlike `rework` its value is a WORD, so the numeric predicate
# `declares_field` can never see it — that one type-tests the value and rejects every
# word — which is why the read below is positional and why `declares_token` exists where
# a single named value is the question.
#
# Three values, and each names the WRITER:
#   * `measured`    -- the tool TOOK the values: `tools/telemetry.py::format_detail_string`
#                      emitted them, or `tools/ledger.py`'s close guard appended them.
#   * `typed`       -- the values were NOT contributed by the tool. The guard's
#                      contribution-free branch is exactly where a hand-typed row enters.
#   * `unavailable` -- nothing was measured, STATED rather than silently absent (#129).
TELEMETRY_PROVENANCE_KEY = "telemetry"
TELEMETRY_PROVENANCE_VALUES: tuple[str, ...] = ("measured", "typed", "unavailable")

def declared_telemetry_provenance(detail: str) -> list[str]:
    """Every `telemetry` value `detail`'s CANONICAL TRAILER declares, in order.

    The ONE positional read of this field, imported by both call sites — the close guard
    in `tools/ledger.py`, which must not RESTATE a provenance the detail already carries
    (two tokens for one field have no canonical reading, §8), and
    `tests/test_close_telemetry_provenance.py`, which asserts that a row declaring a
    measurement declares its provenance too. A private `token.split("=")` at either would
    be the class `n=405` PART 5 rules: one field, one predicate.

    The run is POSITIONAL (`trailer_tokens`), matching `declared_rework`: a token quoted
    mid-sentence is prose and never becomes a declaration. That is what makes both sides
    of the gate's question read from ONE surface — a row whose trailer declares
    `duration=` must declare `telemetry=` in the SAME trailer, so the population and the
    provenance can never be read from different places.

    Classification of a value is NOT here: the vocabulary is the writer's, and a reader
    that wants to know whether a value is one the writer may use compares against
    `TELEMETRY_PROVENANCE_VALUES` beside the constant, exactly as `rework_bucket` sits
    beside `OUTCOME_DOMAIN`.
    """
    return _declared_values(detail, TELEMETRY_PROVENANCE_KEY)

# The close trailer's `rows` field -- the ROW COUNT a cited `tools/ledger.py verify` receipt
# MEASURED (#96, ruled at ledger `n=745`). verify reads a subject's rows as a SEQUENCE, so a
# receipt taken before the close row exists has not seen the row it is cited for: the
# citation is structurally incapable of covering the artifact it certifies. The count is what
# makes that checkable, because a count is a NUMBER and a citation in prose is not -- a row
# declaring `n-1` has not lied, it has TOLD you its verify predated the append.
#
# THE TOKEN IS `rows`, AND IT IS NOT THIS MODULE'S TO CHOOSE. The ledger already carries it:
# `n=761` (the close of #89) declares `rows=761` in its trailer, and `n=762` is the repair row
# that put it there, stating in terms that the row "now DECLARES the row count verify measured
# (SKILL.md section 11, #96 ruling n=745)". One field, one predicate -- so the reader below is
# keyed on the spelling the data already uses, and a `verify_rows`-style second spelling would
# split the field the invariant is about. The FUNCTION is named for the question (the verify
# ROW COUNT) and the CONSTANT for the token, because the two differ here by necessity.
#
# `rows` is deliberately NOT in TELEMETRY_KEYS, for `rework`'s and `telemetry`'s reason: it
# counts ROWS READ, not work done, so it must not enter an aggregate over the measurement keys.
#
# The read is POSITIONAL, which is why it is here rather than routed through
# `declares_field`: that predicate scans the WHOLE detail and answers whether a field is
# mentioned at all, and a `rows=` token quoted mid-sentence would satisfy it. The invariant
# asks what the row DECLARES, and a declaration lives in the canonical trailer.
VERIFY_ROWS_KEY = "rows"

def declared_verify_rows(detail: str) -> list[str]:
    """Every `rows` value `detail`'s CANONICAL TRAILER declares, in order.

    The ONE read of this field, imported by the gate that asserts its invariant -- a close
    row declares the row count verify measured, and that count must be at least the row's own
    number. A private `token.split("=")` inside the gate would be the class ruled at `n=405`
    PART 5: one field, one predicate. Section 11's law binds a NEW field exactly as it binds
    an old one, which is why the key is declared here and nowhere else.

    The run is POSITIONAL (`trailer_tokens`), matching `declared_rework` and
    `declared_telemetry_provenance`: a count quoted mid-sentence is prose and never a
    declaration, so the number a reader acts on is always the row's own. Values are read
    VERBATIM, like every other value here.

    A LIST, for `declared_rework`'s reason: the gate must be able to REPORT two declarations
    rather than read the first silently, because two tokens for one field have no canonical
    reading (SKILL.md section 8). Classification of a value -- whether it parses, and whether
    it covers the row -- is NOT here: that is the gate's question, and it is asked of the
    strings this returns.
    """
    return _declared_values(detail, VERIFY_ROWS_KEY)

# The duty receipt's `duty` field -- whether the round a thin trigger woke COMPLETED (#160,
# ruled at ledger `n=1041`). Section 11 names the ledger's SECOND object: a `run` row
# authored by the WOKEN LANE on behalf of the DUTY, not of the trigger. A trigger's own run
# row records that the trigger FIRED, so a green cron run is never evidence that the duty
# ran, and this field is what makes the difference readable.
#
# THE DECLARATION IS REQUIRED, and that is the whole reason for a distinct key rather than a
# convention. The leg's first version accepted ANY ledger row whose subject matched the
# round, so a DISPATCH record written before the round completed certified it and the leg
# reported a false clean while the round was still incomplete -- measured live on
# `registry-attest-2026-09-25`, where n=1003 (the dispatch, 06:08:53Z) stood in for the
# completion that landed later as n=1007 (06:14:25Z) under a different subject. A row that
# declares nothing is therefore NOT a receipt: the omission is the failure the mechanism
# cannot see, which is the sentence section 11 states for this leg.
#
# `duty` IS NOT `outcome`, and the two are not interchangeable. `outcome` is a WORK run's
# field: a run row declaring one ENTERS `first_pass_yield_population` (`tools/audit.py`),
# and a duty receipt is SELECTION-BIASED -- it is written by a lane that completed a duty --
# so putting receipts under `outcome` would add near-certain successes to the yield's
# denominator and make the ratio structurally optimistic (a real 1-in-25 lane failure would
# dilute from 4.0% to 1.8%). One number answering two questions is the #143 class, so the
# second object carries its own field and the yield is untouched.
DUTY_KEY = "duty"
DUTY_DOMAIN: tuple[str, ...] = ("completed", "failed", "skipped")

def declared_duty(detail: str) -> list[str]:
    """Every `duty` value `detail`'s CANONICAL TRAILER declares, in order.

    The ONE read of this field, imported by the patrol's duty-receipt leg -- a private
    `token.split("=")` there would be the class ruled at `n=405` PART 5: one field, one
    predicate. Section 11's law binds a NEW field exactly as it binds an old one, which is
    why the key is declared here and nowhere else.

    The run is POSITIONAL (`trailer_tokens`), matching `declared_rework`,
    `declared_telemetry_provenance` and `declared_verify_rows`: a value quoted mid-sentence
    is prose and never a declaration. That is load-bearing for THIS field, because the rows
    carrying it discuss completion in prose at length -- a whole-detail scan would read the
    discussion as the declaration, which is precisely the n=405 clause 5 damage.

    A LIST, for `declared_rework`'s reason: the caller must be able to REPORT two
    declarations rather than read the first silently, because two tokens for one field have
    no canonical reading (SKILL.md section 8). Classification of a value -- whether it is
    one the writer may use -- is NOT here: the domain is `DUTY_DOMAIN` beside the constant,
    exactly as `rework_bucket` sits beside `OUTCOME_DOMAIN`.
    """
    return _declared_values(detail, DUTY_KEY)
