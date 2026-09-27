# Instrument adoption census — one predicate over the declared population

Read at **2026-09-27T17:38:02Z** by `tools/instrument_census.py`.

## The predicate, stated before the figures

**Predicate:** for each member, `os.path.isfile(member.repo / p)` for every path `p` the
law doc's §2 declares — **9 path(s)** — plus the reload link's own state.
**Scope:** the member fragments in `registry/factories/*.json`.
**Instant:** 2026-09-27T17:38:02Z.

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

## The readings

| member | held | reload link | fragment declares | status |
|---|---|---|---|---|
| `ai-antispam` | 9/9 | absent | unestablished | **HELD-UNDECLARED** |
| `inferhub-watch` | 9/9 | absent | unestablished | **HELD-UNDECLARED** |
| `infra-factory` | 9/9 | absent | unestablished | **HELD-UNDECLARED** |
| `meta-factory` | 9/9 | resolves | unestablished | **SOURCE** |
| `miidas` | 1/9 | absent | unestablished | **PARTIAL-UNDECLARED** |
| `opencrabs-dev` | 0/9 | absent | unestablished | **ABSENT** |

## The two legs, and why a copy alone is not adoption

A row is **ADOPTED** only when the declared set is COMPLETE *and* the member has a
DECLARATION behind it. `HELD-UNDECLARED` is a member holding every path with no decision
behind it (frame §1.3 — the files can arrive as another instrument's closure), and
`PARTIAL-UNDECLARED` is a member holding some of them. Both are reported as what they
are: silence is a state here, never a pass.

**THE DECLARED LEG IS UNESTABLISHED, FOR EVERY MEMBER, AND THAT IS A SCHEMA FACT.**
`registry/factories/<slug>.json` carries a `kit` field whose value is the **KIT's**
adoption state (obligation O6). There is no field for a PER-INSTRUMENT disposition, so a
member that declared its kit adopted has said nothing about this instrument — and reading
one as the other would manufacture an adoption nobody decided. This census therefore
reports the leg as unestablished rather than defaulting it, and **no member can reach
ADOPTED until that surface exists or a member declares on one this census can read.**
That is HQ's schema to extend, not a member's omission.

`SOURCE` marks the member whose repo IS the repo the instrument is authored in. It holds
the set by construction; counting it as an adoption site would report the source as its
own adopter and inflate every wave by one.

The **reload link** is the member's own act (frame §6.1) and is never installed from this
repo. `absent` is a declared state, not a failure — a law doc with no reload link is
perfectly readable, it is simply not re-injected after compaction.
