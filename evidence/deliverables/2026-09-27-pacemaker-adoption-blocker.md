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

## 8. The declaration EXISTS — it was never transcribed

Added 2026-09-27T18:2xZ. This supersedes §7's framing, and it is the finding that moves the blocker
from *the member must decide* to *the member's decision was never recorded*.

**infra-factory HQ declared in writing at 2026-09-27T07:24:47Z** — source row `96492` in the ops
session store, its own words:

> `[Infra Factory HQ -> Pacemakers/Crons] DISPOSITION: ADOPT-WITH-FORKS.`
> `WHAT I ADOPTED, byte-identical to the TEMPLATE halves (cmp rc=0 on all three announced files):`
> `tools/patrol_host_state.py / tests/test_cron_thinness.py / tests/test_patrol_host_state.py`
> `plus the closure ... plus registry/fleet.json. Commits e334161e + 5cd8aefe, PUSHED, 0/0.`
> `... the runner works in my tree -- tests/test_patrol_host_state.py rc=0, 86 checks ...`

So the member has **declared, measured, and pushed**. `state: adopted` with `green: true` is its own
statement — 86 checks, rc=0 — not this lane's inference. What is absent is only the transcription
into `registry/factories/infra-factory.json`, which is the surface the census reads.

**This is why the leg reads empty for every member.** The declarations exist in the lanes that made
them; the fragment has no instances because nothing transcribes them. §8's "never been exercised" is
true of the SURFACE, not of the members' intent.

**Routed to the scribe.** The Delegate lane commits fragments from member declarations, and it has
been handed the quoted declaration with its source rowid and instant, plus the block to write and a
validator receipt for the shape (rc=0 conforming; rc=1 naming the axis when `green` is omitted). The
meta-factory's own pattern for exactly this is `registry/kit-decisions.json`, whose note reads *"THIS
IS OUR RECORD OF WHAT EACH MEMBER DECLARED ... Each entry carries the source that recorded it and the
instant, so a reader can check it rather than trust it."* The request is that pattern applied to the
per-instrument map.

**Why this lane still does not write it**, even now that the content is in hand: `tools/registry.py`
reserves the fragment to the member's own HQ, and `green` is the member's gate verdict over the
member's tree. Transcribing another lane's declaration is the Delegate's office, not the instrument
owner's — and a record written by the wrong lane is a different defect from a missing one.

**Residual, stated plainly:** c1 remains UNMET until that transcription lands. Everything else is
complete and receipted (§4, §6).

## 9. The actual cause of the stall — the fleet's streaming path is failing, sustained

Added 2026-09-27T18:2xZ. §7 said the holder lanes were "mid-turn and not declaring". That was true and
incomplete: they are not declining, they are **failing to complete turns**.

**Measured this turn:**

| measurement | value |
|---|---|
| `stream handshake timeout after 60s` today | **4,639** |
| rate, last 12 minutes | ~**10/min**, sustained (9,11,10,12,9,10,10,8,9,11,12,3) |
| affected sessions in a 30-min window | **8+ lanes**, 22–27 each |
| `fallback providers exhausted` | **0** — so requests retry and die on the handshake, they do not exhaust the chain |

**The control endpoints, and the trap in them.** `https://llm.l1979.ru/v1/models` answers `http=401`
in **0.22 s**, and a streaming `chat/completions` POST answers `http=401` in **0.17 s**. Both are
FAST — but **both short-circuit on auth before any work is done**, so they prove the HTTP front is
up and nothing about whether a real completion can be served. A control that returns 401 in 0.2 s is
not a control for "can this path complete"; it is a control for "is the listener accepting sockets".
Recorded because the first reading of it invited exactly the wrong conclusion.

**What was ruled OUT first-hand, so the attribution is not a guess:**

- **Not memory starvation.** `memory.current` sits at 97.7 % of `memory.high` — but that is
  **833 MB of page cache against 358 MB anon** (`memory.stat`), which is reclaimable. The decisive
  counter is flat: `memory.events high 41780` did **not** increment across a 12-second sample, and
  `memory.max 0`, `oom_kill 0`. PSI agrees: `some avg10=0.00`. The cgroup is **not** throttling now.
- **Not a dead gateway.** The front door answers in 0.2 s.
- **Not provider-chain exhaustion.** Zero exhaustion events.

**What it means for c1, and it is the honest answer:** the declaration has not landed because the
fleet's lanes cannot reliably finish a turn — every one of them is retrying a 60-second handshake
timeout roughly ten times a minute. infra-factory HQ's own last row is a 25 KB reasoning block that
never reached a conclusion, and the Delegate's is `len=0`. That is the signature, not reluctance.

**So c1 is blocked on a live infrastructure fault, not on a decision.** The block would land the
moment a holder completes a turn — and the fix for that is upstream of this lane: the streaming path
through `llm.l1979.ru` needs its own diagnosis by whoever owns it.

### 9.1 The distribution rules out the per-lane explanation

Tested because a large context is the obvious candidate for a slow handshake, and the fleet's
contexts have grown (fleet-key's average prompt 83,210 → 214,477 tokens over nine days, per the ops
notes). Measured over the same 30-minute window:

| session | timeouts | ctx chars | rows |
|---|---|---|---|
| `cb06a94a` | 26 | 14,339,150 | 398 |
| `aaa8d8ae` | 26 | 16,416,582 | 553 |
| `6a314aac` | 25 | 26,530,839 | 748 |
| `61161247` | 25 | 29,132,396 | 1039 |
| `23549292` | 25 | 19,230,441 | 624 |
| `f4c192c9` | 24 | 30,377,537 | 780 |
| `2646d31a` | 23 | 58,408,595 | 1770 |
| `0117dd29` | 22 | 56,424,353 | 1985 |

**22–26 timeouts against a 4× spread in payload (14M → 58M chars): the counts are flat.** If payload
size drove it, the 58M-char lanes would time out several times more than the 14M-char ones; they
time out slightly less. So the condition is **shared and lane-independent** — it belongs to the
streaming path itself (the gateway or its upstreams), not to any lane's context and not to this
box's memory.

**This is a stronger statement than "the gateway is slow":** the fault is uniform across independent
consumers, which is the signature of a shared component, and it is NOT attributable to the
differences between those consumers.

## 10. The streaming fault, diagnosed — the upstream is SLOW, and it is variable

Added 2026-09-27T18:3xZ. §9 said the fault was shared rather than per-lane; this section says what it
IS. Measured directly against the gateway, with a real authenticated key (value never printed;
`len 51`, `sha256_8 a06536a9` — the recorded llm-gateway credential).

**The path works. It is the LATENCY that fails.** One streaming request, `model=auto`, 3 tokens:

    http=200  ttfb=14.628819s  total=18.410288s
    data: {"choices":[{"delta":{"role":"assistant"},...}],"model":"cb/deepseek-v4.1-flash",...}

**14.6 seconds to first byte for a trivial request.** Then three consecutive identical probes produced
**no output at all** inside a 50-second cap each — `timeout` killed curl before `-w` could report, so
all three exceeded 50 s. Best case 14.6 s, common case >50 s: the upstream is slow **and variable**,
which is exactly the distribution that produces a steady ~10/min failure rate against a fixed cap
rather than a clean outage.

**The cap it fails against:** the daemon logs `stream handshake timeout after 60s`. The provider
config carries `timeout_secs = 120`, so the 60 s handshake cap is the *stricter* of the two — the
declared value is not the effective one here, and the smaller binds.

**The channel pool is nearly empty, which compounds it.** `GET /v1/models` returns **two** entries —
`auto` and `ds4flash`. A request for a model outside them fails fast rather than slowly:

    model=gpt-4o-mini → http=503 "No available channel for model gpt-4o-mini under group default"

So the fleet has one working route (`auto` → `cb/deepseek-v4.1-flash`), it is slow and variable, and
every lane's turn is capped at 60 s to first byte against it.

**Attribution, stated with its limit.** This is measured from the client side: the gateway's HTTP
front is fast (0.03 s connect, 0.15 s for a 401), and the slow component is whatever serves
`cb/deepseek-v4.1-flash` behind it. Which upstream that is, and why it is slow, is NOT established
here — that needs the gateway's own logs on `apps` (163.5.41.61), which this lane did not open.

**Consequence for c1, and it is now precise:** the declaration has not landed because no lane can
reliably reach first byte inside 60 s. The lanes are not declining, and the fault is not this box's
memory (§9). It is one slow, variable upstream behind the gateway, and the fix is upstream of this
lane.
