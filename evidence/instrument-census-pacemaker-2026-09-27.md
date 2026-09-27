# Instrument adoption census — one predicate over the declared population

Read at **2026-09-27T20:58:47Z** by `tools/instrument_census.py`.

## The predicate, stated before the figures

**Predicate:** for each member, `os.path.isfile(member.repo / p)` for every path `p` the
law doc's §2 declares — **11 path(s)** — plus the reload link's own state.
**Scope:** the member fragments in `registry/factories/*.json`.
**Instant:** 2026-09-27T20:58:47Z.

**WHAT THIS DOES NOT MEASURE.** It is ONE predicate on file PRESENCE. A present file may
differ byte-wise from the manifest — that is `kit_pin`'s question, not this one —
and a `seed`-class absence is a declaration, not a gap. Read a `held` figure as *held*,
never as *current*.

**Declared set, derived from `docs/instruments/pacemaker.md` §2** (the parse is
guarded: zero parsed paths refuses rather than censusing an empty set):

1. `tools/patrol_host_state.py`
2. `tests/test_cron_thinness.py`
3. `tests/test_patrol_host_state.py`
4. `tools/field_predicate.py`
5. `tools/kit_pin.py`
6. `tools/publish.py`
7. `tools/registry.py`
8. `tests/test_board_intake_recorded.py`
9. `tests/test_close_board_recorded.py`
10. `tests/ledger_boundary.py`
11. `tools/ledger_declaration.py`

## The readings

| member | held | reload link | fragment declares | status |
|---|---|---|---|---|
| `ai-antispam` | 11/11 | absent | adopted · green=true | **ADOPTED** |
| `inferhub-watch` | 11/11 | absent | absent | **HELD-UNDECLARED** |
| `infra-factory` | 11/11 | absent | adopted · green=true | **ADOPTED** |
| `meta-factory` | 11/11 | resolves | absent | **SOURCE** |
| `miidas` | 1/11 | absent | absent | **PARTIAL-UNDECLARED** |
| `opencrabs-dev` | 0/11 | absent | absent | **ABSENT** |

## The two legs, and why a copy alone is not adoption

A row is **ADOPTED** only when the declared set is COMPLETE *and* the member's own
declaration says `adopted` with `green: true`. `HELD-UNDECLARED` is a member holding
every path with no decision behind it (frame §1.3 — the files can arrive as another
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

The **reload link** is the member's own act (frame §6.1) and is never installed from this
repo. `absent` is a declared state, not a failure — a law doc with no reload link is
perfectly readable, it is simply not re-injected after compaction.
