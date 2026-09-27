# Blocker record — the pacemaker adoption's last leg is an act reserved to a member's HQ

**Recorded:** 2026-09-27T18:1xZ · **Lane:** Pacemakers/Crons (`ee5cd2f5-6c1b-41bb-b031-1150a3132fb1`)
· **Instrument:** `pacemaker` · **Criterion:** the adoption scenario completes in the live
environment, i.e. at least one member row reads **ADOPTED**.

## 1. What is missing, exactly

One block in one member's fragment. Nothing else.

    registry/factories/<member-slug>.json
      "instruments": {"pacemaker": {"state": "adopted", "green": true, "measured_at": "<instant>"}}

## 2. The concrete evidence that it is missing

**The live census, all six members** (`tools/instrument_census.py`, artifact
`evidence/instrument-census-pacemaker-2026-09-27.md`):

| member | held | fragment declares | status |
|---|---|---|---|
| `ai-antispam` | 9/9 | absent | HELD-UNDECLARED |
| `inferhub-watch` | 9/9 | absent | HELD-UNDECLARED |
| `infra-factory` | 9/9 | absent | HELD-UNDECLARED |
| `meta-factory` | 9/9 | — | SOURCE |
| `miidas` | 1/9 | absent | PARTIAL-UNDECLARED |
| `opencrabs-dev` | 0/9 | absent | ABSENT |

**And no fragment has ever carried it** — nor the older `kit` field beside it:

    $ git log --oneline -S'"kit"' -- registry/factories/
    (no output — the field has not been touched in any commit in this repository's history)

## 3. Why the instrument's own lane cannot close it

`tools/registry.py`'s own docstring states the surface's rule:

> **DECLARED** — one JSON fragment per factory, **written by THAT factory's HQ and by nobody else.**

`green` is the member's own gate verdict over the member's own tree. No other lane can measure it,
so a declaration written by this lane would not be a declaration — it would be the **manufactured
adoption** the census's two-leg design exists to prevent. That is a rule, not a courtesy, and
breaking it to satisfy a criterion would corrupt the artifact the criterion is about.

## 4. What IS complete — every leg that lives in the repository

| leg | state | receipt |
|---|---|---|
| declaration surface exists | ✅ | `registry.py::validate_instruments` `:363`; live store validates rc=0, 7 fragments |
| validator accepts the shape | ✅ | rc=0 conforming; **rc=1 naming the axis** when `green` is omitted |
| reader reads it | ✅ | `tools/instrument_census.py` (owning lane's fix `84a94ba`) |
| ADOPTED path pinned by a gate | ✅ | `tests/test_instrument_census.py`, **10 arms, rc=0**, incl. the non-vacuity arm |
| the pipe reaches ADOPTED over live data | ✅ | rehearsal against `infra-factory`'s **real** tree (`/root/vds-servers`), declaration in a temp store: `held=9/9 declares=adopted · green=true -> ADOPTED` |
| the law tells members to declare | ✅ | `docs/instruments/pacemaker.md` §8 step 5 (`e49e14c`) — this step was **missing** until today, which is why the leg has no instances |
| deployment | ✅ | all on `origin/main`, ahead/behind 0/0 |

## 5. Owner, and re-entry

**Owner:** a member HQ that holds the set — `infra-factory` HQ (`6a314aac`) or `ai-antispam` HQ
(`cb06a94a`), both at 9/9. **Scribe:** the Delegate lane (`23549292`), which commits fragments from
member declarations; it has been asked to include instrument declarations in its next attestation
round, since a law file is only read by members that go looking.

**State at this record:** all three lanes had received the ask and were mid-turn on it —
`infra-factory` was explicitly *"verify[ing] the state carefully before declaring"* (18:06:54Z).

**Re-entry:** the moment one holder's fragment carries the block in §1, the census reads ADOPTED and
this record closes. Nothing else is outstanding; §4 is the receipt that the rest already works.

**The honest verdict on the criterion:** externally blocked, with a named owner and a one-block
remedy — **not** met, and not presentable as met.

## 6. Deploy receipt (c3) — the corrected tooling is live in the target environment

Captured 2026-09-27T18:1xZ:

    $ git fetch -q origin
    $ git rev-parse HEAD
    df809ecc9e93bec1ea270dc55902c5f5046c5f36
    $ git rev-parse origin/main
    df809ecc9e93bec1ea270dc55902c5f5046c5f36
    $ git rev-list --left-right --count HEAD...origin/main
    0	0

Blob-level check that the live tooling IS the corrected tooling, not a local-only edit:

    tools/instrument_census.py        origin/main blob == working tree   IDENTICAL
    tests/test_instrument_census.py   origin/main blob == working tree   IDENTICAL

And the regression gate, literal exit code:

    $ python3 tests/test_instrument_census.py
    ... 10 PASS, 0 FAIL
    instrument census gate: passed
    exit=0

## 7. Verdict — a hard blocker, stated as one

**c1 is UNMET and is a hard blocker, not a task in progress.** The declaration is an act the
governing rule reserves to a member's own HQ, no other lane may supply it, and no member has
performed it in the repository's entire history. This lane has asked both holder lanes and the
scribe lane; all three hold the ask and none has declared.

**It is not closable from this lane by any legitimate action.** The only two remaining routes are
both outside it: a holder HQ declaring, or the fleet owner directing one to. Neither is a technical
step that more work here would reach.
