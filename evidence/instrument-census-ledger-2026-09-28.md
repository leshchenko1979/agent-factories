# Instrument adoption census — one predicate over the declared population

Read at **2026-09-28T15:30:30Z** by `tools/instrument_census.py`.

## The predicate, stated before the figures

**Predicate:** for each member, `os.path.isfile(member.repo / p)` for every path `p` the
law doc's declared-set table declares — **15 path(s)** — plus the reload link's own state.
**Scope:** the member fragments in `registry/factories/*.json`.
**Instant:** 2026-09-28T15:30:30Z.

**WHAT THIS DOES NOT MEASURE.** It is ONE predicate on file PRESENCE. A present file may
differ byte-wise from the manifest — that is `kit_pin`'s question, not this one —
and a `seed`-class absence is a declaration, not a gap. Read a `held` figure as *held*,
never as *current*.

**And `held` is a presence measurement over a WORKING TREE, so a path may be present AND
untracked.** A member can therefore read held-complete over a commit that cannot run the
instrument from a clone at all. So `held` is a reading of a live tree and is **never a
fact about the member's repository** — those are two different figures wherever a declared
path is untracked. The axis and its prohibition are template-instruments.md §7.5, not
this tool's.

**Declared set, derived from `docs/instruments/ledger.md`'s declared-set table** (the parse
guarded: zero parsed paths refuses rather than censusing an empty set):

1. `tools/ledger.py`
2. `tools/ledger-index.py`
3. `tools/ledger_declaration.py`
4. `tools/field_predicate.py`
5. `tools/reconstruction.py`
6. `tests/ledger_boundary.py`
7. `tests/gate_fixtures.py`
8. `tests/test_ledger.py`
9. `tests/test_ledger_identity.py`
10. `tests/test_ledger_schema.py`
11. `tests/test_ledger_no_shrink.py`
12. `tests/test_ledger_close_preflight.py`
13. `tests/test_ledger_commit_cites_no_rows.py`
14. `tests/test_ledger_index.py`
15. `docs/instruments/ledger.md`

## The readings

| member | held | reload link | fragment declares | status |
|---|---|---|---|---|
| `ai-antispam` | 15/15 | absent | partial · green=false | **DECLARED-PARTIAL** |
| `inferhub-watch` | 8/15 | absent | partial · green=false | **DECLARED-PARTIAL** |
| `infra-factory` | 6/15 | absent | deferred · green=true | **DECLARED-DEFERRED** |
| `meta-factory` | 15/15 | resolves | absent | **SOURCE** |
| `miidas` | 6/15 | absent | absent | **PARTIAL-UNDECLARED** |
| `opencrabs-dev` | 0/15 | absent | not-applicable · green=false | **DECLARED-NOT-APPLICABLE** |

## The two legs, and why a copy alone is not adoption

A row is **ADOPTED** only when the declared set is COMPLETE *and* the member's own
declaration says `adopted` with `green: true`. `HELD-UNDECLARED` is a member holding
every path with no decision behind it (template-instruments.md §1.3 — the files can arrive
as another
instrument's closure), and `PARTIAL-UNDECLARED` is a member holding some of them. Both
are reported as what they are: silence is a state here, never a pass.

**THE DECLARED LEG IS READ FROM `instruments.<slug>`, HQ's per-instrument surface.**
The fragment's `kit` key beside it is the **KIT's** adoption state (obligation O6) and
says nothing about this instrument, so it is never read as one: a member that declared
its kit adopted has not declared this instrument. An **absent** key is a LEGAL state —
the schema makes absence valid — so it is reported as the member's silence, which is a
reading rather than a refusal, and it is what keeps a member that considered the
instrument distinguishable from one that never did.

`SOURCE` marks the member whose repo IS the repo the instrument is authored in. It holds
the set by construction; counting it as an adoption site would report the source as its
own adopter and inflate every wave by one.

The **reload link** is the member's own act (template-instruments.md §6.1) and is never
installed from this
repo. `absent` is a declared state, not a failure — a law doc with no reload link is
perfectly readable, it is simply not re-injected after compaction.
