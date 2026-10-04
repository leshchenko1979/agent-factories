# Lens S — Brain Scrub & Cross-Profile Cleanliness

**Cycle:** 20260927-c1  **Lens:** S (Family 6 — Meta-Governance)
**Repo under review:** `/root/agent-factories` (read-only)
**Revision audited:** `af6d92776c1dce0159256ad100c6c0abf889e480`
(commit dated 2026-10-04 21:46:07 +0000 — `review(rr-c1): record batch 3 lenses D, H, M; codify lens E Finding 1 (landed at a862d47)`)
**Revision note:** the tree is LIVE. HEAD was re-read at the top and bottom of this audit and did not
move off `af6d927`. Every shipped-law quote below is read from the commit via
`git show af6d927:<path>`, not from a possibly-dirty working tree. (`git status --porcelain` shows
pre-existing peer dirt — `docs/factory-registry.md`, `registry/factories/ai-antispam.json`,
`registry/index.json`, `registry/state.json` — none of which is measured here.)

**Brief (governing):** `/tmp/rr-c1/briefs/lens-S.md` — Scope: "Shared AGENTS.md vs factory-specific
skills." Inspection targets: (1) `AGENTS.md` carries only a minimal one-line recovery anchor;
(2) zero factory-specific rules leaked into shared profile brain files; (3) member-specific domain
rules live only in their dedicated repo skills. **Corpus (governing):** `/tmp/rr-c1/CORPUS.md` —
re-maps lens S onto `skills/meta-factory/SKILL.md` vs the factory-specific skills, and onto the
brain-file boundary; it explicitly notes that the brief's generic paths (`roles/*.md`, `processes.md`,
`AGENTS.md`) do **not** exist in this repo, which is itself finding S-5.

**Method (what produced the numbers — every count is from a command actually run):**
`git -C /root/agent-factories rev-parse HEAD` (→ `af6d927`); `git log -1`; `git show <rev>:<path>`
for every shipped-law quote; `ls -la` / `find` / `git ls-files` to enumerate the corpus;
`sed -n` and `awk` on each cited line number; `grep -nE '^## (17|18)\.'` on
`TEMPLATE/SKILL.md.tmpl`; `wc -lc` over `/root/.opencrabs/profiles/ops/*.md`;
`grep -nE 'meta-factory|agent-factories'` over the ops brain; `cat registry/fleet.json`;
`grep -n declared docs/factory-registry.md`; `grep -rniE 'leak|...' tests/*.py`;
`ls TEMPLATE/docs/instruments/` vs `ls docs/instruments/`; `cat docs/law-uuid-exemptions.json`;
`md5sum docs/addons.md TEMPLATE/docs/addons.md`; `grep -rn` for member-name leakage. Read in full:
`skills/meta-factory/SKILL.md` (496 lines), `skills/meta-factory/state.md`, `skills/meta-factory/verdicts-and-claims.md`,
`TEMPLATE/SKILL.md.tmpl` (§17–18 + heading list), all seven `docs/addons/domain/*.md`,
`docs/review-lenses.md`, `docs/projects/hygiene-surfaces.md`, `TEMPLATE/README.md`, `README.md`,
`registry/fleet.json`, `registry/factories/meta-factory.json`, and the live ops-profile brain files.
I could not measure one thing and say so in S-9: the **liveness** of the hardcoded session ids — no
offline surface reads live `session_bindings`, so their staleness is asserted from dates, not probed.

**Result: 15 findings — 4 HIGH, 6 MEDIUM, 4 LOW, 1 INFO.** The single most severe is S-1: the
meta-factory's own core-law file cites `TEMPLATE/SKILL.md.tmpl §17` for the clause that is actually
**§18**, so every reader who follows the pointer lands on the wrong law.

---

## Finding S-1 — HIGH — Dangling cross-reference: the core law points at `§17` for a clause that is `§18`

**(1) File Locator:** `skills/meta-factory/SKILL.md:33`

**(2) Verbatim quote (shipped bytes, `git show af6d927:skills/meta-factory/SKILL.md | sed -n '33p'`):**

> go in *your* skill, in *your* repo. See `TEMPLATE/SKILL.md.tmpl` §17.

**(3) Defect analysis.** The sentence tells a reader *where a factory's rules live* and sends them to
§17 of the template. Measured target:
`git show af6d927:TEMPLATE/SKILL.md.tmpl | grep -nE '^## (17|18)\.'` →
`409:## 17. Reporting language` and `425:## 18. Where this factory's rules live`. The pointer lands
on **Reporting language**, not on the rules-home clause. This is a P29 defect ("law-upholding law"):
a citation that names the wrong section is dead text — a reader following it is misled, and a reader
who notices loses trust in the whole file. `tests/test_law_structure.py` checks heading *contiguity*
only; it does not verify that a cross-reference names a real, correct target, so no gate catches this.

**(4) Remediation.** One-byte-class fix: change `§17` → `§18` on `skills/meta-factory/SKILL.md:33`.
(Optional, stronger: add a cross-reference-target assertion to `tests/test_law_structure.py` that
parses `See \`<file>\` §N` citations and fails when `§N` is not a heading in `<file>`.)

---

## Finding S-2 — HIGH — The meta-factory's own §5 routing table hardcodes three member factories into core law (leak-test class, unenforced)

**(1) File Locators:** `skills/meta-factory/SKILL.md:253-256`

**(2) Verbatim quote (shipped bytes, `git show af6d927:skills/meta-factory/SKILL.md | sed -n '253,256p'`):**

> | OpenCrabs instruments (daemon, core tools, brain/skill loading) | **OpenCrabs Kanban Board HQ** — lane `opencrabs-dev` / `hq`, topic `OC DEV HQ` (thread 30220), resolved live at dispatch; fork issues on `leshchenko1979/opencrabs` |
> | … (lines 254–256) name `inferhub-watch`, `leshchenko1979/fast-mcp-telegram`, and `src/brain/tools/telegram_send.rs` |

**(3) Defect analysis.** §5 is process law for the meta-factory. Its substrate-routing table names
three concrete member factories *and their chat topics, lane slugs and repo paths* inside the core-law
file. `TEMPLATE/README.md:37-49` defines this exact shape as the defect ("A hit that states
**mechanics** is a leak — a rule that will be wrong the day the substrate changes") and
`skills/meta-factory/SKILL.md:344-346` commands the author to "run the leak test before shipping any
core law file." The roster is the very thing the leak test exists to catch — and no test runs it
(see S-3). The rule that *should* live here is "route a defect to the repo that carries the code";
the specific member→topic→repo mapping is binding detail and belongs in an add-on.

**(4) Remediation.** Move the concrete member→substrate mapping to an add-on page (e.g.
`docs/addons/domain/consulting.md`, which already exists for "the meta-factory" domain), leaving §5
to state the *requirement* only. Then S-3's new gate keeps it out.

---

## Finding S-3 — HIGH — The "leak test" is a declared mandatory gate with NO mechanism — and two authoritative files define it inconsistently

**(1) File Locators:** `TEMPLATE/README.md:37-45` and `docs/addons.md:54-62` (byte-identical twin:
`TEMPLATE/docs/addons.md:54-62`, `md5 f378faaea8509a2c7eecd2c42e86a77d`).

**(2) Verbatim quotes (shipped bytes).**

`TEMPLATE/README.md:39-45`:
> Before you commit a change to any core file, run:
>
> ```sh
> grep -rniE 'telegram|opencrabs|forum|session_notify|github' \
>   TEMPLATE/SKILL.md.tmpl TEMPLATE/AGENTS.md.tmpl TEMPLATE/ONTOLOGY.md.tmpl \
>   docs/best-practices.md
> ```

`docs/addons.md:59-62` (the *other* definition of the same test):
> ```sh
> # core files must not name a bound product
> grep -rniE 'telegram|opencrabs|forum|topic|session_notify|gh |github' \
>   TEMPLATE/SKILL.md.tmpl TEMPLATE/AGENTS.md.tmpl TEMPLATE/ONTOLOGY.md.tmpl
> ```

**(3) Defect analysis.** Two problems, one class.

*(a) UN-GATED.* `skills/meta-factory/SKILL.md:344-346` orders "run the leak test … before shipping
any core law file," but nothing runs it. Measured:
`grep -rniE 'leak|substrate.*mechanic|forbidden.*token' tests/*.py` returns only incidental uses
(probe-leak, marker-leak, path-leak) — **no test encodes the leak test.** `docs/projects/hygiene-surfaces.md`
itself lists "**No mechanical gate**" for this class. A declared, mandatory check with no mechanism
is P29 debt: the law says "must," the tooling says nothing.

*(b) SELF-CONTRADICTORY.* The two authoritative definitions disagree on **both** the token set and
the file set. Tokens: `docs/addons.md` scans `topic` and `gh ` (7 tokens); `TEMPLATE/README.md` scans
neither (5 tokens). Files: `TEMPLATE/README.md` adds `docs/best-practices.md` (4 files);
`docs/addons.md` omits it (3 files). A reader cannot know which set is canonical — and the two differ
exactly on the surface (`best-practices.md`) that `evidence/rework.md:116` records as the reason the
file list was extended in the first place ("`best-practices.md` calls itself core law and was outside
its scope"). So the *fix* to the historical leak survives in one definition and was lost from the other.

**(4) Remediation.** Add `tests/test_leak_test.py` that runs the grep over the declared core-law file
set and fails on a hit — and make that test the single source of truth, deleting the hand-copied
`grep` from whichever doc loses. Reconcile the two token/file sets first (adopt the union:
`topic`, `gh `, and `docs/best-practices.md`), or delete the directive from `SKILL.md` if the check is
not actually intended to be binding.

---

## Finding S-4 — HIGH — Stale member count in law: "four member factories" vs six enrolled

**(1) File Locator:** `skills/meta-factory/SKILL.md:493`

**(2) Verbatim quote (shipped bytes, `git show af6d927:skills/meta-factory/SKILL.md | sed -n '493p'`):**

> | The four member factories | consulting | diagnostic findings, recommendations, template laws and scores; they own their own decisions and implementation |

**(3) Defect analysis.** A count in law with no predicate and no instant, contradicting the registry it
is derived from. Measured: `cat registry/fleet.json` lists **6** factories (ai-antispam, infra-factory,
inferhub-watch, meta-factory, miidas, opencrabs-dev); `docs/factory-registry.md:11` reads
`| declared | 6 fragment(s) | 6 attested…`; `docs/growth-stages.md:196,202` says "six" and
"0 / 6 active." The same stale "four" also appears in `docs/addons.md:78,87` and `docs/product.md:69`.
A number baked into law that no longer matches its own registry is a silent-omission defect: the
reader is told a fact that the corpus contradicts three files away.

**(4) Remediation.** Replace "the four member factories" with "the member factories" (count-free — the
set is named by the registry, not by a numeral) or "six member factories," and if a number is kept,
state the predicate and instant ("six enrolled in `registry/fleet.json` at <date>"). Sweep the
same edit through `docs/addons.md:78,87` and `docs/product.md:69`.

---

## Finding S-5 — MEDIUM — The lens catalog's own scope for Lens S names generic paths that do not exist in this repo (catalog↔corpus drift)

**(1) File Locator:** `docs/review-lenses.md:156`

**(2) Verbatim quote (`sed -n '156p' docs/review-lenses.md`):**

> - **Scope:** External agent profile brain files (`AGENTS.md`, `SOUL.md`, `TOOLS.md`) vs. factory repos.

**(3) Defect analysis.** The catalog defines Lens S against three generic brain-file *names*. The
surfaces the lens actually has to audit here are the ops-profile files
(`/root/.opencrabs/profiles/ops/AGENTS.md`, `…/CODE.md`, `…/SECURITY.md`, `…/BOOT.md` …) and the
boundary law in `skills/meta-factory/SKILL.md` §0/§11 — not bare `AGENTS.md`/`SOUL.md`/`TOOLS.md`.
The proof that the catalog drifted is the governing corpus itself: `/tmp/rr-c1/CORPUS.md` had to
re-map the lens because the brief's paths "do NOT exist in this repo." When the audit harness must
translate the catalog before an auditor can start, the catalog has drifted from the surfaces it
indexes.

**(4) Remediation.** Rewrite the Lens S entry to name the real profile brain files and the real
boundary law: "ops-profile brain files under `/root/.opencrabs/profiles/ops/*.md` vs.
`skills/meta-factory/SKILL.md` §0/§11." Same pass for the sibling lens entries if they name paths the
corpus had to re-map.

---

## Finding S-6 — MEDIUM — The one-line-pointer law (§0) is contradicted by the live shared brain file, which carries a multi-sentence meta-factory directive

**(1) File Locators:** law at `skills/meta-factory/SKILL.md:30`; live surface at
`/root/.opencrabs/profiles/ops/AGENTS.md:106` (and a routing-table mention at `…:61`).

**(2) Verbatim quotes.**

`skills/meta-factory/SKILL.md:30` (shipped bytes):
> The shared `AGENTS.md` carries a one-line pointer here and nothing more.

`/root/.opencrabs/profiles/ops/AGENTS.md:106` (live file, 132 lines / 32,986 B):
> **The meta-factory instance** (`/root/agent-factories`): its law lives in its own skill — load `/meta-factory` before surveying a member, deriving template law, scoring, briefing the Delegate lane, or answering an owner question about the factory project. **Post-compaction, reload it** before any ruling, dispatch or status claim.

**(3) Defect analysis.** §0's rule is *isolation by minimalism*: the shared brain carries a pointer,
"nothing more." The live pointer carries a load instruction plus a five-verb duty list plus a
post-compaction reload clause — operational rules, not an anchor. The hygiene-surfaces doc names the
exact hazard: `docs/projects/hygiene-surfaces.md:70` — "**No mechanical gate.** These files live in no
repository, so no repo gate can read them. One bad line here binds every lane on the box." Because no
gate can read the live brain, the divergence between the law (§0) and the surface (the actual file)
is invisible to CI and drifts unbounded.

**(4) Remediation.** Pick one and make the other agree. Either shrink `ops/AGENTS.md:106` to a
one-line pointer (e.g. "Meta-factory (`/root/agent-factories`): load `/meta-factory` before any task.")
— or amend §0 to state the true rule: the pointer may carry the load instruction and the
post-compaction reload clause, and nothing else.

---

## Finding S-7 — MEDIUM — §0 says the brain pointer is "one line … and nothing more," while §9 requires it to trigger a three-part reload protocol

**(1) File Locators:** `skills/meta-factory/SKILL.md:30-33` (§0) and `:319-331` (§9, the compaction
protocol).

**(2) Verbatim quote (`git show af6d927:skills/meta-factory/SKILL.md | sed -n '319,331p'`), closing line of §9:**

> The shared brain file carries a one-line pointer here for exactly this reason. Mechanics: `docs/methodology/04-harness-binding.md` §5–9.

**(3) Defect analysis.** Internal contradiction in one file. §0 says the shared brain carries "a
one-line pointer here and nothing more"; §9 then relies on that same pointer to fire a three-part
protocol (manifest curation → reload → re-anchor from disk) whose whole point is that the brain
*cannot* carry the protocol ("In-context instructions do not survive compaction; only what is written
to an always-injected file or a durable substrate does"). Either the pointer is one line and §9's
protocol is unreachable from the brain, or the protocol must be reachable from the brain and §0's
"nothing more" is false. The law contradicts itself about the single most load-bearing surface it has.

**(4) Remediation.** Reconcile §0 and §9: state explicitly *which* clauses the shared pointer may
carry (load instruction? reload clause? manifest-curation clause?) and edit the other section to match.
This is the same defect as S-6 seen from the law side; fixing one without the other leaves the
contradiction standing.

---

## Finding S-8 — MEDIUM — Two independent lane rosters for one factory, different membership, both claiming authority

**(1) File Locators:** `skills/meta-factory/SKILL.md:110-116` (the law's roster) and
`registry/factories/meta-factory.json` (`lanes` array).

**(2) Verbatim / measured.** `git show af6d927:skills/meta-factory/SKILL.md | sed -n '110,116p'`
tabulates **5** lanes (HQ, Worker, Delegate, Triage, Surveys). Measured from the registry fragment:
`python3 -c "import json;d=json.load(open('registry/factories/meta-factory.json'));print(len(d['lanes']))"`
→ **13** lanes (Surveys, Triage, HQ, Delegate, Worker, Ledger, Open Question Tool, Pacemakers,
Instruments methodology, Fleet instruments, Review Rotation, Insights, Hygiene).

**(3) Defect analysis.** One factory's lane set is declared twice, with different membership (5 vs 13),
in two surfaces that both read as authoritative — the law's table and the registry fragment. Nothing
states the relationship (is the registry the superset? does the law name only "process-duty" lanes?).
A reader cannot tell which is the census. `docs/review-lenses.md` is already fighting this ambiguity:
its Lens S item 1 says "Ensure factory-specific process rules do NOT leak…" — process rules that the
law's own roster doesn't enumerate.

**(4) Remediation.** State the relationship in §3: "the registry fragment
(`registry/factories/meta-factory.json`) is the full lane census; the table below names only the lanes
that carry process duties." Or regenerate the law's table from the registry so there is one source.

---

## Finding S-9 — MEDIUM — Raw session ids hardcoded in law, under a self-declared exemption whose own note admits no gate can assert they resolve

**(1) File Locators:** `skills/meta-factory/SKILL.md:112-116` (5 raw session ids in the lane roster),
declared in `docs/law-uuid-exemptions.json`.

**(2) Verbatim quote (`git show af6d927:skills/meta-factory/SKILL.md | sed -n '106,107p'`):**

> ids below were read back from `session_bindings` on 2026-09-18 12:20Z. A lane is addressed by
> its **session id**, and that id is re-read from live state before any send — never carried

**(3) Defect analysis.** The law forbids carrying a session id across turns ("re-read from live state
before any send — never carried [over]"), yet the roster hardcodes five session ids and pins them to a
read-back timestamp of 2026-09-18 — 16 days before this revision (`af6d927`, dated 2026-10-04).
`docs/law-uuid-exemptions.json` exempts exactly these five occurrences (all in
`skills/meta-factory/SKILL.md`), and its own `_note` concedes the limit: "nothing offline can read
live `session_bindings`, so no exemption and no gate can assert that a NAME still resolves." So the
file declares visible, acknowledged debt — but debt with no expiry and no gate, now 16 days stale. I
**cannot measure** liveness (no offline surface reads `session_bindings`); I can only measure the age
and the exemption. §5 of the same file already solved this problem by naming topics instead of ids.

**(4) Remediation.** Convert the roster to topic/role names (as §5 does) and resolve the id live at
dispatch, then delete the five entries from `docs/law-uuid-exemptions.json`. If ids must stay, add an
expiry timestamp to the exemption so staleness becomes a gate failure rather than a note.
