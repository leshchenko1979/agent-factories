#!/usr/bin/env python3
"""Shared: what makes a token a FIELD, and where the trailer that holds one ENDS.

The prose-as-data class (#88; ruled at ledger `n=405` clause 5). `detail` is free
prose, and prose quotes fields: a row that REPORTS "the trailer ends
'...tokens_out=...'" writes a token a naive reader takes for telemetry. One shape,
three failure directions, each measured on a live row:

* **prose must not SATISFY a field** — `tests/test_ledger_schema.py` split the whole
  detail on whitespace and validated every `k=v` token, so a row that QUOTED a
  trailer was read as declaring it (the #87 intake row, `n=561`).
* **prose must not TERMINATE a scan** — the close-row gate's OLD whole-detail reader
  (removed by #190, which moved that leg onto this module's `declared_revision`)
  returned at the first `head=` token, so a row that DESCRIBED the field before
  naming its revision was refused. Fixed at `d244964`; the predicate it uses is the
  one below.
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

CAUSE_COUNT_TOKEN = "oc-cause-count"
"""The DECLARED summary marker a failing gate prints about ITSELF (#205, ruled shape (b)).

One line, anchored at the start, carrying the count as an integer:

    oc-cause-count: 7

It exists because a noun list is a GUESS AT ENGLISH and this factory's own tool proved it:
`tools/audit.py::reported_cause` recognises `problem|violation`, while `tools/hygiene.py`
prints `found 7 issue(s)` — so the count leg silently did nothing and the recorded cause fell
through to the output's LAST line, an INFORMATIONAL declaration line the tool prints on every
run, clean or not. A reader who trusted that headline was sent to a fix that could not clear
the gate, with the severity number dropped.

Widening the noun class was measured and REFUSED: it would have matched correctly only by
COINCIDENCE — the advisory block prints first and its noun is `item(s)`, which no widened
class matches, so a class whose first match can sit in an advisory block records a non-cause
as the cause, one noun away from the defect it was meant to close.
"""

CAUSE_COUNT_RE = re.compile(rf"^[ \t]*{CAUSE_COUNT_TOKEN}:[ \t]*(\d+)[ \t]*$", re.MULTILINE)


def declared_cause_count(text: str) -> int | None:
    """The failure count a gate DECLARES on its own output, or None when it declares none.

    Read ANCHOR-FIRST and by declaration alone: the token, then `:`, then digits, on a line
    of its own. Nothing is inferred from the surrounding prose, so a tool's phrasing cannot
    move the reading — the rule the mixed class above was written to honour.

    The bound is stated rather than implied: a tool that has NOT adopted the marker returns
    None here, and its caller keeps whatever heuristic it already had. That is why this is
    additive — no tool regresses, and each author has a lawful route that costs one line.
    """
    m = CAUSE_COUNT_RE.search(str(text))
    return int(m.group(1)) if m else None


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

def own_voice_text(detail: str) -> str:
    """`detail` with every PARENTHETICAL ASIDE removed — the row's own voice.

    The THIRD scope, and the one a reader needs when a row QUOTES a token: the canonical
    trailer is POSITIONAL and the lexical scan is ANYWHERE, so a token sitting inside a
    parenthetical aside — `n=1990 (… declared claim=reconstructed with no BASIS: marker …)`
    — reads as a declaration to every lexical reader while being, in fact, a CITATION of
    another row's defect. Scoping to the trailer alone was refused for the opposite harm
    (`declares_token` records it): a token written mid-detail would go silently invisible,
    and a declaration no reader can see is worse than one a reader can check. So the scope
    is neither positional nor unlimited — it is the text that speaks in the row's OWN VOICE.

    The rule is the one a careful reader applies and can state: a token is a DECLARATION
    when it stands at parenthetical depth 0 — in the canonical trailer or in the row's own
    mid-detail prose — and a QUOTATION when it sits inside an aside. Measured on the live
    ledger when this landed: it keeps every one of the genuine mid-detail declarations and
    drops exactly the one quotation.

    The parentheses are replaced by a SPACE, never deleted, so the tokens on either side
    cannot FUSE: deleting `(x)` from `claim=(aside)reconstructed` would mint the declaration
    `claim= reconstructed` -> `claim=reconstructed` out of nothing. An aside replaced by a
    space leaves a token boundary exactly where the original had one.

    UNBALANCED PARENTHESES FAIL OPEN, and the asymmetry is deliberate. Where the parentheses
    cannot be paired the depth of any given token is undefined, so this returns the detail
    UNCHANGED and the caller keeps the lexical reading it had before this function existed.
    Fail-open means the worst outcome is the pre-existing over-inclusion, which a human sees
    and which is the very defect this function narrows; fail-closed would mean a stray `(`
    silently DROPPING a genuine declaration, which is the false-negative the caller's
    population exists to catch and which no reader would see. Measured on the live ledger
    when this landed: ten rows carry unbalanced parentheses and NONE of them is in the
    reconstructed-claim population, so the asymmetry is unexercised on real rows and stated
    rather than hidden.

    ONE predicate, shared (`n=405` clause 5, `n=599`): the two readers that need the
    own-voice scope — `reconstruction.reconstructed_claims` and `reconstruction.names_basis`
    — import THIS function rather than each carrying a private parenthesis walk, which is
    the drift class this module exists to close. It reads the WHOLE detail and never a
    trailer: an aside removed from a trailer would be a fourth reading of the trailer, and
    `trailer_tokens` is already the one positional reader.
    """
    text = str(detail)
    if "(" not in text and ")" not in text:
        # The common case, and it is not only an optimisation: with no parentheses to pair
        # the depth is trivially zero everywhere, so the detail IS its own voice.
        return text
    out: list[str] = []
    depth = 0
    balanced = True
    for char in text:
        if char == "(":
            depth += 1
            out.append(" ")
        elif char == ")":
            if depth == 0:
                balanced = False
            else:
                depth -= 1
            out.append(" ")
        elif depth == 0:
            out.append(char)
    if depth != 0 or not balanced:
        return text
    return "".join(out)

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

# The `ruling` row's `comment=<id>` field — the BOARD COMMENT the ruling was paired with.
#
# ONE home for the key (#297). Three readers ask for it: the writer that puts it on the row
# (`tools/rule.py`), the refuser that will not stamp a `ruling` row without it
# (`tools/ledger.py append`) and the gate that judges history
# (`tests/test_ruling_row_recorded.py`). A private `PAIRING_KEY = "comment"` in any of the
# three is the defect section 11 names rather than a style preference: two copies drift in
# silence, and the drift lands on exactly the rows the pairing exists to make readable. It
# lives here because this module already owns both halves of the reader the three compose —
# `trailer_tokens` (the run is POSITIONAL, so a token quoted in prose is not a declaration)
# and `keyed_value` (a declaration carries a NON-EMPTY value).
PAIRING_KEY = "comment"

def declared_pairing(detail: str) -> str | None:
    """The `comment=` value `detail`'s CANONICAL TRAILER declares, else None.

    RAW, not filtered for well-formedness. The gate must be able to REPORT a token that is
    declared and malformed (`comment=none`) rather than read it as absent — the two are
    different defects with different remedies, and collapsing them would let a malformed
    token read as a missing one. The well-formedness test is therefore the caller's, and
    `declared_comment_id` is the filtered read the WRITE PATH asks.
    """
    for token in trailer_tokens(detail):
        value = keyed_value(token, PAIRING_KEY)
        if value:
            return value
    return None

def declared_comment_id(detail: str) -> str | None:
    """The WELL-FORMED `comment=<id>` `detail`'s canonical trailer declares, else None.

    WELL-FORMED means a run of DIGITS: the value is a board comment id, and `comment=none`
    or `comment=abc` OCCUPIES the key while naming no comment — the row is half-recorded
    exactly as if the token were absent. This is the SAME test the gate applies
    (`str.isdigit()`), asked here so the write path and the reader cannot disagree about
    what a row declares (#297 clause 2, one predicate two call sites).
    """
    value = declared_pairing(detail)
    return value if value and value.isdigit() else None

# The close row's `head=<sha>` field — the revision its receipts describe. This is its
# ONE canonical reader, shared by the gate that judges history and the write path that
# refuses to create the defect, so the two cannot disagree about what a row DECLARES.
#
# It reads the CANONICAL RUN and never the whole detail, and that half is measured rather
# than stylistic (#104, ruled at `n=620` PART 5; #187). The run IS the row's declaration,
# so a token outside it is a QUOTATION: `n=565` quotes the foreign sha `4ae1ffdb…` in
# prose while its own trailer declares `3878936a…`, so a whole-detail scan reads a
# revision that row never measured. Three live rows split the two readings — `n=1077`
# (#157), `n=1083` (#164) and `n=1091` (#158) each carry `head=` in PROSE only — which is
# why a write-path refusal reading the whole detail could be satisfied by quoting any
# hex-shaped token, and would accept a row whose revision no existence check ever reads.
REVISION_KEY = "head"
REVISION_MIN_CHARS = 7
_HEX_DIGITS = frozenset("0123456789abcdef")

def declared_revision(detail: str, min_chars: int = REVISION_MIN_CHARS) -> str | None:
    """The `head=<sha>` value `detail`'s CANONICAL RUN declares, or None.

    `None` means the run declares no readable revision — the state the write path refuses
    and the gate reports. It never means "no revision anywhere in the text", which is why
    a caller must not re-derive it with a whole-detail scan: that difference is the three
    live rows named above, and it is the difference between a declaration and a quotation.

    `min_chars` is a parameter because the gate and the write path assert the same SHAPE
    at the same floor — 7, git's short-sha minimum — and a caller needing a different floor
    would otherwise be tempted to write a second reader, which is the class this function
    exists to close. The value is read VERBATIM after stripping the punctuation a sentence
    wraps around it.
    """
    for token in trailer_tokens(detail):
        value = keyed_value(token, REVISION_KEY)
        if value is None:
            continue
        sha = value.strip(").`")
        if len(sha) >= min_chars and all(c in _HEX_DIGITS for c in sha):
            return sha
    return None

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
    reads one disposition per row. The law gives a row one token (SKILL.md §Verdicts and claims: a field carrying
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
    (two tokens for one field have no canonical reading, SKILL.md §Verdicts and claims), and
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

    The run is POSITIONAL (`trailer_tokens`), matching `declared_rework` and
    `declared_telemetry_provenance`: a value quoted mid-sentence
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


RECLOSE_KEY = "reclose"


def declared_reclose(detail: str) -> list[str]:
    """Every `reclose` value `detail`'s CANONICAL TRAILER declares, in order.

    The ONE read of this field, imported by the append path that refuses a SECOND
    `close` for a subject (#213) -- a private `token.split("=")` there would be the
    class ruled at `n=405` PART 5: one field, one predicate.

    WHY NOT `declares_field`, WHICH THE REFUSAL FIRST USED, and the defect that
    proves why this function exists: `declares_field` serves a NUMERIC key and
    TYPE-TESTS the value it finds (`_value_parses`). `reclose` carries a free-text
    REASON, so no value it can hold passes that test. Measured 2026-09-28:
    `declares_field(detail, "reclose")` is False for EVERY form tried, including
    `reclose=yes` as the last token of the trailer -- so the escape hatch the
    refusal's own message prescribed was UNREACHABLE, and every second `close` was
    refused, the lawful re-close this refusal exists to allow included. A
    behavioural probe found it; the grep that "verified" the leg did not, because a
    mechanism's EXISTENCE is not its FUNCTION.

    The run is POSITIONAL (`trailer_tokens`), matching `declared_rework`,
    `declared_duty` and `declared_telemetry_provenance`: section 11 puts a
    declaration in the canonical trailer, so a value quoted mid-sentence is prose.
    Values are read VERBATIM.

    A LIST, for `declared_rework`'s reason: a row carries one token (a field with
    two values has no canonical reading, SKILL.md section 8), and the caller must
    be able to SEE a second rather than read the first silently.
    """
    return _declared_values(detail, RECLOSE_KEY)


RECLAIM_KEY = "reclaim"

def declared_reclaim(detail: str) -> list[str]:
    """Every `reclaim` value `detail`'s CANONICAL TRAILER declares, in order.

    The ONE read of this field, imported by the append path that refuses a SECOND
    `claim` for a subject by the same actor (#246) — a private `token.split("=")` there
    would be the class ruled at `n=405` PART 5: one field, one predicate.

    IT MIRRORS `declared_reclose` DELIBERATELY, and the mirroring is the point: a claim
    and a close are the two ends of one lifecycle, so a reader that learns the close's
    declaration form should meet the claim's in the same shape. The measured population
    is what makes the token a FORMALISATION rather than a new burden: three of the eight
    multi-claim subjects already declare themselves in prose (`RE-CLAIM by the Worker
    lane … after Triage's intake at n=480`, `CLAIM #113 (fresh) — a SECOND acceptance`,
    `Re-claiming #161 after the intake leg landed`) — the convention existed and only
    lacked a token.

    WHY NOT `declares_field`: it serves a NUMERIC key and TYPE-TESTS the value it finds,
    while `reclaim` carries a free-text REASON — the defect `declared_reclose`'s own
    docstring records at length, where the escape hatch the refusal prescribed was
    UNREACHABLE for every value it could hold.

    The run is POSITIONAL (`trailer_tokens`), matching every other declared field:
    section 11 puts a declaration in the canonical trailer, so a value quoted
    mid-sentence is prose. Values are read VERBATIM.

    A LIST, for the same reason: a row carries one token (a field with two values has no
    canonical reading, SKILL.md section 8), and the caller must be able to SEE a second
    rather than read the first silently.
    """
    return _declared_values(detail, RECLAIM_KEY)

def mentions_reclaim(detail: str) -> bool:
    """True when `detail` carries the `reclaim` KEY anywhere, trailer or prose.

    The LEXICAL half of the pair above, for the ONE job `mentions_reclose` exists for: to
    let the append path NAME a malformed declaration instead of silently not seeing it. A
    `reclaim` value containing a SPACE terminates the canonical trailing run, so the row
    declares nothing at all while its author is told to write the token they believe they
    wrote.

    Deliberately NOT the guard's predicate: a LEXICAL test lets a row that merely
    DISCUSSES a re-claim satisfy its own guard, which is the #88 / `n=405` clause 5 damage
    ("prose must not SATISFY a field"). The guard reads the positional form; this answers
    only "did the author write the token somewhere I can point at?"
    """
    return any(keyed_value(token, RECLAIM_KEY) is not None
               for token in str(detail).split())

def mentions_reclose(detail: str) -> bool:
    """True when `detail` carries the `reclose` KEY anywhere, trailer or prose.

    The LEXICAL half of the pair above, and it exists for ONE job: to let the
    append path NAME a malformed declaration instead of silently not seeing it.
    `declared_reclose` reads the canonical trailing run, and a `reclose` value
    containing a SPACE terminates that run -- measured 2026-09-28,
    `trailer_tokens("... head=<sha> reclose=the subject was reopened")` is `[]`,
    so the row declares nothing at all and its author is told to declare the very
    token they believe they declared.

    It is deliberately NOT the predicate the guard uses: a LEXICAL test lets a row
    that merely DISCUSSES a re-close in prose satisfy its own guard, which is the
    #88 / `n=405` clause 5 damage ("prose must not SATISFY a field"). The guard
    reads the positional form; this answers only "did the author write the token
    somewhere I can point at?" so the refusal can say WHY it is not being seen.
    """
    return any(keyed_value(token, RECLOSE_KEY) is not None
               for token in str(detail).split())

CLAIM_KEY = "claim"

def declared_claim(detail: str) -> list[str]:
    """Every `claim` value `detail`'s CANONICAL TRAILER declares, in order.

    The ONE positional read of this field, imported by the append path that refuses a
    `claim` value outside the reconstruction vocabulary (#249) — a private
    `token.split("=")` there would be the class ruled at `n=405` PART 5: one field, one
    predicate.

    IT MIRRORS `declared_reclaim` AND `declared_reclose` DELIBERATELY, and the mirroring
    is the point: `claim` is the third of the three declarations on the claim/close
    lifecycle, so a reader who has learned the other two meets this one in the same shape.

    WHY NOT `declares_token`, WHICH THE GATE USES, and the defect that makes the
    difference load-bearing: `declares_token` asks whether ONE named value is present, so
    it answers True for a row declaring `reconstructed` and False for EVERY other value —
    and a refusal built on it would have read `claim=#220` as "nothing declared here",
    which is precisely the state it exists to refuse. The refusal must SEE the value, not
    match it, so the read is positional and returns what is there.

    The run is POSITIONAL (`trailer_tokens`), matching every other declared field: section
    11 puts a declaration in the canonical trailer, so a value quoted mid-sentence is
    prose — the `#99` class, where a private whitespace scan over the whole `detail` took
    eight prose QUOTATIONS for eight declarations and put a false population into a close
    row (`n=1785`, corrected at `n=1790`).

    A LIST, for `declared_reclaim`'s reason: a row carries one token (a field with two
    values has no canonical reading, SKILL.md section 8), and the caller must be able to
    SEE a second rather than read the first silently.
    """
    return _declared_values(detail, CLAIM_KEY)

# The `dispatch` row's `delivery=<verdict>` field — the verdict the row's author RECORDED
# for the routing the row claims (#49 shape 1, ruled at ledger n=1893).
#
# A `dispatch` row is a claim that a lane was TOLD, and until this field it was a claim
# with no receipt: the row and the `session_notify` that carries the brief are two
# independent facts, either of which can exist without the other. Measured 2026-09-18 in
# BOTH directions — `#41`/`#42` delivered with no row, `#48` a row (n=276) with no
# delivery — and the sharpest instance is `#48`'s, appended and committed by a turn a
# restart killed between the append and the notify, so the ledger reported a routing that
# had not happened.
#
# THE FIELD'S PRESENCE IS NOT THE DELIVERY, AND THE RULING SAYS SO ITSELF: `tools/ledger.py`
# can require the verdict be RECORDED; it cannot verify it is TRUE. So this read is the
# write-path SEAM and nothing more — `tools/patrol_host_state.py`'s delivery leg is the
# EVIDENCE, and a reader that takes this token as proof of delivery has re-derived the very
# error the field exists to catch.
#
# The existing convention is PROSE — 78 live dispatch rows carry the phrase
# `delivery turn-end` mid-sentence — and it is deliberately NOT the form read here. A
# verdict outside the canonical trailing run is a quotation: measured 2026-09-19, `n=276`
# (the phantom row this field exists to have caught) carries the WORDS but no token, so a
# whole-detail scan would read its prose as a declaration and admit the very row the
# refusal is aimed at. The run is POSITIONAL, matching every other declared field.
#
# A LIST, for `declared_reclaim`'s reason: a row carries one token (a field with two
# values has no canonical reading, SKILL.md section 8), and the caller must be able to SEE
# a second rather than read the first silently. The VALUE's vocabulary is NOT fixed here —
# the author records the verdict they took (`turn-end`, `interrupt`, `deferred`, `none`),
# and the leg judges it against the target's own message history.
DELIVERY_KEY = "delivery"

def declared_delivery(detail: str) -> list[str]:
    """Every `delivery` value `detail`'s CANONICAL TRAILER declares, in order.

    The ONE positional read of this field, imported by the append path that refuses a
    `dispatch` row carrying no verdict (#49 shape 1) and by the patrol leg that seeks the
    delivery each verdict claims — a private `token.split("=")` at either would be the
    class ruled at `n=405` PART 5: one field, one predicate.

    `keyed_value` carries the well-formedness half: a bare `delivery=` names no verdict,
    so it is not a declaration and the row is refused exactly as if the token were absent.
    """
    return _declared_values(detail, DELIVERY_KEY)
