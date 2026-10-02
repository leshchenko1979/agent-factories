# Render centralisation — one canonical render call, run by the path unit

**Date:** 2026-10-02 · **Lane:** Open Questions instrument (`9f635151`) · **Plan:** 5/5
**Order:** owner, Telegram topic *Open Question Tool*, 2026-10-02 06:29 UTC — *"Start render
centralisation"*, on the standing retirement order of 2026-09-30: *"Every member factory
should use the centralized code first. They should retire their own copies."*

---

## 1. The defect this closes

The Open Questions register renders its page from a **`questions-render.mjs` asset resolved
beside the invoked binary** (`RENDER_SRC`, `oc-questions:2127`). Every member factory holds
its own copy of that asset, so **two copies can serve two different behaviours on one
path** — the shape test of `docs/instruments/template-instruments.md` §6.4 for a
tier-1 centralised element.

Measured on this box (2026-10-02), the copies in the population are **not** identical:

| copy | md5 | bytes |
|---|---|---|
| canonical (`TEMPLATE/tools/questions-render.mjs`, and the executing copy beside the CLI) | `20d924c01b7f3e7e60576b500bdc3d87` | 15629 |
| `/root/ai-antispam/tools/questions-render.mjs` | `66ed6e5976334813c6608c941ea7bcc2` | 14860 |
| `/root/miidas/tools/questions-render.mjs` | `78401d5922c61f5d2e60d345dc7801b7` | 11326 |

**The divergence is possible and unobservable on the path — not observed.** A member's own
lane can render with its own copy while the owner's tap reaches the canonical one, and
nothing on the path reports which ran. This record does **not** claim a member copy has
produced a served page: `render_via_node` copies from beside the *invoking* binary, so the
md5 sitting in a store's `build/` names which asset is *in place*, never which binary
produced a given page. The defect is that the question is unanswerable, not that it was
answered wrong.

---

## 2. The canonical path

**Resolved at call time by the answer backend's own predicate, never by a second one**
(`docs/instruments/open-questions.md` §5.1: *"the path is resolved at call time, so no
clause in this file may pin it"*).

```
/root/.opencrabs/profiles/ops/skills/opencrabs-dev/tools/*/oc-questions
/root/.opencrabs/profiles/ops/skills/opencrabs-dev/tools/oc-questions
```

**Exactly one match, or refuse.** Zero or two-or-more is a hard failure that names the
count and every candidate — never a pick, because a pick is how a wrong renderer serves a
page silently. Authority for the rule: `/opt/questions/backend.py` (its `CLI_ROOT` default
plus the `CLI_RESOLVE` glob), mirrored in `tools/kit_census.py::answering_path`.

The **render asset** is resolved by the tool itself, beside the binary it was invoked as:
`<dir-of-invoked-oc-questions>/oc-questions-render.mjs`. Canonical asset md5 today:
`20d924c01b7f3e7e60576b500bdc3d87`, byte-identical to `TEMPLATE/tools/questions-render.mjs`
and to the executing copy in the ops skill tree.

---

## 3. The mechanism

One canonical render per mutation, run by the **existing path unit** — no new cron, no boot
leg (owner order 2026-10-01: *"don't use the boot leg. Only verb plus sweep."*).

`oc-questions-push.path` → `oc-questions-push.service` → `oc_questions_push.sh`, and inside
one activation the order is:

```
resolve  →  render  →  swap (only where different)  →  mirror  →  compare
```

| leg | what it does |
|---|---|
| **resolve** | the exactly-one glob above; refuses loudly on 0 or 2+, naming the count and each candidate |
| **render** | the canonical CLI publishes into a **scratch store** (`OC_QUESTIONS_DIR=$(mktemp -d)`), never into the live tree — so a failed render cannot leave a half-written page |
| **swap** | `rsync -a --no-times -c --delete` from the scratch page tree into the live one, **only where `diff -rq` says they differ** |
| **mirror** | the pre-existing source→vpn mirror, unchanged, still comparing source digest against served digest and exiting non-zero past its retry bound |
| **compare** | the settled test now also requires `src_pages == stage_digest`, so the loop cannot break while the live tree disagrees with the canonical render |

**Why the swap is conditional — the busy-loop hazard.** `systemd.path(5)`: *"When a service
unit triggered by a path unit terminates, monitored paths are checked immediately again, and
the service accordingly restarted instantly."* The unit watches `…/questions`,
`…/pages/latest.json` and `…/open.json`, and `publish_page` writes `index.html` and
`meta.json` **unconditionally**. So a writer inside the service re-triggers itself, and an
unconditional swap would spin. Hence: render to scratch, swap only on difference.

**Why `--no-times` — a measured finding, not a preference.** Isolated test, 2026-10-02:
`rsync -a -c` over a **byte-identical** pair emitted `.f..t......` — no data transferred,
but the `t` means it **fixed the destination mtime**, moving the watched `pages/latest.json`
and re-triggering the unit. `rsync -a --no-times -c` printed nothing and left the mtime at
its old value, while a real change still transferred (`>fcsT......`) and `--delete` still
pruned. `rsync 3.2.7`. The `-c` itself stays load-bearing for the retry (rework #207: the
default size-and-mtime quick-check skips a same-length rewrite whose mtime was restored).

---

## 4. Receipts

**Task 3 — production.** The edited script in the real systemd path, read from the journal:

```
Oct 02 14:27:05  Starting oc-questions-push.service
Oct 02 14:27:17  push: render - canonical page tree swapped in (attempt 1)
Oct 02 14:27:20  push: compare - pages src=faa1190a80887ddccad07ed3c58f6690 served=faa1190a80887ddccad07ed3c58f6690 | register src=fe8ce57374a4ef76c1054af444cff1b4 served=fe8ce57374a4ef76c1054af444cff1b4
Oct 02 14:27:21  push: ok - 8 page entries, register refreshed (attempts=1, pages=faa1190a80887ddccad07ed3c58f6690, register=fe8ce57374a4ef76c1054af444cff1b4, canonical=faa1190a80887ddccad07ed3c58f6690)
```

**The render precedes the mirror** (swap 14:27:17, compare 14:27:20) and `canonical == pages`
on the closing line. The following run had no swap line — it converged.

**Task 4 — end-to-end, `10 passed, 0 failed`.** A scratch store seeded from the live page
tree, then `ask --factory e2e-probe … --no-publish` so the **only** renderer of the new
content is the push leg's canonical render. Marker `E2E-PROBE-143650`:

```
push: render - canonical page tree swapped in (attempt 1)
push: compare - pages src=3bd23ca4632e59469708647c529a2a90 served=3bd23ca4632e59469708647c529a2a90 | register src=ac3765bd6d53b9cc76e94fc2d5ec747a served=ac3765bd6d53b9cc76e94fc2d5ec747a
```

The served tree carries `e2e-probe/` and `all/`, both holding the marker; pages, register and
canonical all agree; zero scratch directories leaked.

**Convergence, local.** Same inputs run three times: run 1 swapped, runs 2 and 3 produced no
swap. **A finding inside that result:** run 1 swapped even with the live page tree copied in,
because a rendered page embeds a **relative age string** (`asked 27.9h ago` against
`28.2h ago` — the only difference, in `all/`, `infra-factory/` and `meta-factory/`
`index.html`). So the render is **not byte-deterministic across a 0.1 h tick** — a fresh
render is expected to differ from a six-minute-old tree, and that swap is the age being kept
current rather than a staleness defect. Within one activation the tick cannot move, which is
why the guard converges.

---

## 5. Member render-copy dispositions

The population was **enumerated**, not sampled: `find /root -name 'questions-render*.mjs'`,
run to completion on 2026-10-02. Five copies exist on the box.

| copy | md5 | bytes | disposition |
|---|---|---|---|
| `TEMPLATE/tools/questions-render.mjs` (canonical) | `20d924c0…` | 15629 | **keep** — the canonical asset; the executing copy beside the CLI is byte-identical |
| `/root/ai-antispam/tools/questions-render.mjs` | `66ed6e59…` | 14860 | **retire** — ai-antispam's own act |
| `/root/miidas/tools/questions-render.mjs` | `78401d59…` | 11326 | **retire** — miidas's own act |
| `/root/quarantine/kit-deliver-20260927T1416Z/tools/questions-render.mjs` | `78401d59…` | 11326 | **no action** — already out of every live tree |
| `/root/db-quarantine/kit-deliver-inferhub-20260927/tools/questions-render.mjs` | `78401d59…` | 11326 | **no action** — already out of every live tree |

Members with **no** copy, by measurement: `infra-factory` (`/root/vds-servers`),
`inferhub-watch`, `opencrabs-dev`. `infra-factory` removed its vendored tool copy on
2026-09-27 by its own decision and reaches the centralised one; its render copy is absent on
the same basis. **ABSENT is not inert** — a member with no copy has installed nothing.

**The retirements are the members' own acts.** `docs/instruments/open-questions.md` §5.4:
*"Never install unilaterally. A copy placed where none was asked for is drift the member did
not choose."* This lane recommends and declares; the member HQ executes. A retirement that
does not happen leaves the drift live, and the declaration surface is
`registry/factories/<slug>.json` on the `instruments.open-questions` axis.

**One measured detail worth carrying forward:** both quarantines and `miidas` hold the
**same** md5 `78401d59…`, and one of the quarantines is a *kit delivery*. So miidas's
divergent copy is not a hand edit — it arrived by kit delivery, the same way
`infra-factory`'s stale law doc did. That makes the retirement a matter of declining a
delivered copy, not of correcting a local authoring mistake.

---

## 6. The landed box config

`oc_questions_push.sh` was tracked in no repository (rework #207). It now has a home:
**`tools/box/`** in this repo, with the two units beside it, byte-identical to their live
counterparts at the instant of landing.

| landed | sha256 |
|---|---|
| `tools/box/oc_questions_push.sh` | `fd786fde695c7d3d57d7630adfa069aa39d9b7fa76c35754046699c82fa7a5f2` |
| `tools/box/oc-questions-push.service` | `13850376bd57c1143a5903fcd51f2017d8f3a9205e098bc5c01f715ff1fe0b85` |
| `tools/box/oc-questions-push.path` | `7233b1c0b00758128d0f36791f3b11fdd80794789f365526d3eaa3d4e69cbc7f` |

The directory's contract — which copy is authoritative, the install direction, the drift
check, and the bound — is `tools/box/README.md`. **Edit in the tree, install to the box.**
No gate enforces freshness, because the live side is not in any tree; what upholds it is the
drift check, and that bound is stated rather than implied.

---

## 7. Bounds — what this does NOT do

- It does **not** centralise the **mutation**. The owner's words keep it member-invoked; a
  lane still publishes locally as best effort.
- It does **not** touch a member's declarations, actors, board or processes — §6.4: *"the
  mode centralises the element, not the member."*
- It does **not** re-open the `q18` blind spot (`answerable_questions()` drops a
  failed-delivery question whose answer body is empty, so it appears in neither `ready`,
  `exhausted` nor `skipped`) — reported separately to the owner.
- It does **not** adopt the toolsmith's selftest-tempdir hand-off (`TEMPLATE/tools/questions`
  `:2963` / `:5158`; 102 leaked `/tmp/questions-selftest-*` dirs) — a separate finding that
  collides with this file's line range.
- It does **not** fix the unified-log `ts` form (`+00:00` from `.isoformat()`, invisible to
  the fleet flood guard's `fromdateiso8601?`). That fix belongs **upstream** in
  `TEMPLATE/tools/questions`; it touches the same file as the law declaration and the gate,
  so it rides the same pass rather than adding a vendor delta. Answered to the toolsmith:
  **no ts fix exists at `054b2bd`, local `0938479`, or `origin/main` `ca7f1a5`** — do not
  re-vendor expecting one.

## 8. Open items

1. **Law declaration** (design step 1) — name the render a tier-1 centralised element in
   `docs/instruments/open-questions.md` **and** its `TEMPLATE/` twin (byte-identical pair,
   gated by `tests/test_docs_sync.py`), at the naming site, per frame §6.4/§6.5. Not done in
   this pass.
2. **The gate** (design step 4) — the *"#188 leg (a)"* assertion that a vendored copy differs
   from upstream only in its declared parameter layer, plus a check that the rendered page
   was produced by the canonical asset. Not done in this pass.
3. **Member retirements** — §5; each is the member's own act.
