# The four factories — survey

Surveyed 2026-09-11 from the agents host. Every id, repo and path below was
read from live state (Telegram MTProto `get_chat_info` / `find_chats`, `gh repo
view`, `git remote -v`, the ops profile config and cron DB). Receipts:
[survey-2026-09-11.md](survey-2026-09-11.md).

---

## 1. OpenCrabs development

**Purpose.** Build, test and ship the OpenCrabs agent binary. A fork of
`adolfousier/opencrabs` is the working repo; upstream receives PRs only.

**Chat surface.** Telegram forum group **`Crabs Kanban Board`** (chat
`-1003936827469`, 3 members). ~20 topics; the load-bearing ones are
`OC DEV HQ` (30220), `Triage` (42487), `Skills` (49643), `Harvest` (39218),
`Ontology` (43993), `Role split` (42360). A legacy non-forum group `OC Dev`
(`-1003627148483`) still exists.

**Repos.**

| Repo | Role |
|---|---|
| `leshchenko1979/opencrabs` | Fork — push target, **issues home** |
| `adolfousier/opencrabs` | Upstream — **PRs only**, never a new issue |
| `leshchenko1979/opencrabs-skill` | The process law itself (public), synced from `~/.opencrabs/profiles/ops/skills/opencrabs-dev/` |
| `leshchenko1979/opencrabs-dev-state` | Private off-box durability tier: ledger, journals, receipts |

**Roles** (carved out of a single editor over time): EDITOR (per-task worktree,
signed commit, CI gate, ship), SUPERVISOR (skill set + worker ledger), TRIAGE
(intake, fix routing, enforcement), TOOLSMITH (owns `tools/` — the `oc-*` CLI).
Compiler is retired with a documented re-enable trigger.

**Process law.** `skills/opencrabs-dev/SKILL.md` (v0.4.137) = shared facts +
role router only; the procedures live in four role files loaded one at a time.
Owner rulings live in `fleet-directives.md`. The skill is git-tracked and
mirrored to GitHub.

**Mechanization.** ~30 `oc-*` CLI tools are the real interface: `oc-ledger`,
`oc-deploy` (ship/poll/swap-execute), `oc-prchecks`, `oc-order-validate`,
`oc-wt`, `oc-attrib`, `oc-smoke-evidence`, `oc-notify-fanout`, `oc-drift-check`.
Rituals that were prose became commands with documented return codes
(`tools/RC-CONTRACT.md`).

**State & trace.** `workers-ledger.json` — every claim, fanout, stamp, ack.
Ledger rows are numbered (~n=2100) and are the attribution substrate.

**Automation.** Cron `harvest-watch-4h` (upstream-shift watch + harvest census),
`oc-waiter-sweep` (every 5 min, silent unless an orphan waiter exists),
`__opencrabs_dedup_scan__` (weekly brain dedup).

**Verification.** CI gate on the PR-lane branch (`oc-prchecks`), plus a
four-leg smoke rubric: lineage, identity, CI gate, live behavioral probe.

---

## 2. InferHub Watch

**Purpose.** Probe InferHub's Chat Completions streaming shape daily and rank
routes by **IQ per $**, so the owner can act on the inference auction rather
than just watch a health light.

**Chat surface.** Telegram forum group **`Inferhub watch`** (chat
`4379632866`, 2 members). Topics: `HQ` (2), `General` (1), plus one topic per
work unit named **`Worker — #N <title>`**, flipped to **`Done — #N <title>`**
when the issue closes. A stale duplicate group (`5414677736`, 0 members) exists
and should be retired.

**Repo.** `leshchenko1979/inferhub-watch` (public). Local `/root/inferhub-watch`.
Site: `leshchenko1979.github.io/inferhub-watch` (secondary); Grafana dashboard
`inferhub-watch` is the primary observation surface.

**Roles.** HQ (process only) + one worker per forum topic. Sub-agents are
reserved strictly for review tasks, where fresh context is the point.

**Process law.** `skills/inferhub/SKILL.md` — the HQ process, and the only
process file: task intake, issue law, worker dispatch, self-improvement. Plus
two supporting files:

- `ONTOLOGY.md` — codified vocabulary with a **banned-synonyms table enforced by
  `tests/test_ontology.py`** (a route with red cells is a *failure*, never an
  "error"; a price is an *ask*).
- `WORKLOG.md` — one line per executed task; the analysis substrate.

**Laws already codified** (this factory is the most explicit about process):
issue law (the GitHub issue board *is* the task list; title prefixes
`hq:`/`probe:`/`site:`/`ops:`), delegation law ("you work on the process, not in
the process"), agent-communication law (agents are briefed with
`session_notify`; Telegram topics are for the human), ontology law,
object-link law (every GitHub reference carries a full URL), research-before-
process law, observation-surface law, self-approval law (mechanical reversible
process edits only), and the owner-ruling-vs-codified-gate law (never satisfy a
ruling by loosening a threshold).

**Automation.** GitHub Actions sweep at 02:00Z; cron `inferhub-watch-hq-hourly`
is a **thin trigger** — it runs one command that notifies the HQ session and
stops; `inferhub-daily-report` delivers to `telegram:-1004379632866:2`;
`inferhub-usage-logs-sync` syncs the usage-log cache hourly.

**Verification.** `python3 -m unittest discover -s . -q` (468 passing at survey
time) plus the sweep's own CI and the projection gate.

---

## 3. Miidas

**Purpose.** Multi-tenant Telegram AI platform. The landing page reserves a
warm-pool group → shared trial OpenCrabs → support converts in place to an
isolated managed bot built from `miidas-template`. Each client gets their own
bot, group and container.

**Chat surface.** Per-client Telegram groups: `МИИДАС: <client>` and the
onboarding funnel `МИИДАС · Бухгалтерия без лишнего человека` (dozens of
instances), plus a client-facing forum group `Умница Миидаша` with business
topics (Посты, Объявления, Юридические вопросы, Бухгалтерия, …).
**There is no factory chat** — no forum group where Miidas work is dispatched,
tracked and archived. This is the main structural gap.

**Repos.**

| Repo | Role |
|---|---|
| `leshchenko1979/miidas` | Platform: `agent/`, `manager/`, `landing/`, `cdp/`, `pool/`, `templates/`, `docs/` |
| `leshchenko1979/miidas-template` | The per-client OpenCrabs brain/config template (AGENTS.md, SOUL.md, TOOLS.md, tools.toml, skills/) |

**Process law.** Repo `AGENTS.md` is the single source (with `CLAUDE.md` as a
thin adapter for other agents). It carries: verification commands per changed
component, required secrets, the "edit locally only, then deploy" workflow, and
per-component ops rules. Depth lives in `docs/adr/` (numbered architecture
decisions), `docs/engineering-rules.md`, `docs/postmortems.md`, and
`manager/AGENTS.md` / `agent/AGENTS.md` / `landing/AGENTS.md`.

**State.** Runtime state is on the apps host — `pool/slots/miidas-{slug}.env`;
the client log is `docs/clients.md` in the repo.

**Verification.** Codified per component in AGENTS.md:
`cd manager && python3 -m pytest tests/ -v`, plus `landing/tests/test_claim.sh`,
`agent/tests/test_entrypoint.sh`, and a container check after `cdp/deploy.sh`.

**Deploy.** Explicitly one component at a time (`./agent/deploy.sh`,
`./manager/deploy.sh`, `./landing/deploy.sh`, `./cdp/deploy.sh`); the
all-in-one script is for full-platform work only.

---

## 4. AI AntiSpam

**Purpose.** Two things under one roof: a production LLM spam-moderation bot
(`@ai_spam_blocker_bot`) and a **monoforum outreach campaign** that pitches the
bot to channel owners (wave 0, started 2026-08-23).

**Chat surface.** Telegram group **`ai-antispam`** (`-1003993000918`, 2
members) — a **plain group, not a forum**, and today it functions almost purely
as the cron delivery sink: six campaign crons deliver there. No topics, no lane
structure. This is the main structural gap.

**Repos.**

| Repo | Role |
|---|---|
| `alexeyleshchenko/ai-antispam` | The bot + landing (public); local `/root/ai-antispam` |
| `leshchenko1979/ai-antispam-outreach` | Private campaign-ops repo: plans, recon, send logs, MTProto pipeline scripts |

**Process law.** Three layers:

- Repo `CLAUDE.md` — architecture, commands, error-handling contract (the
  two-layer Telegram retry/decorator rule with its incident note).
- `memory-bank/*.md` — activeContext, opsPlaybook, spamTactics, progress,
  techContext, systemPatterns. Read at the start of a dialog.
- `skills/outreach-reply-sweep/SKILL.md` — the single source of truth for the
  outreach crons; cron prompts are kept thin and point at it.

**State.** Postgres `ai_spam_bot` schema `outreach` on apps is the **single
operational writer**; `outreach/lib/db.py` is the only writer. The repo holds
code, plans and nightly `export/*.jsonl` snapshots. The retired reverse
direction (`etl_sends.py`) caused double-writer duplication and is gone.

**Automation.** Six crons all deliver to the `ai-antispam` group:
`wave0-reply-sweep` (daily), `wave0-unactivated-reprobe` (weekly),
`outreach-db-sync` (daily), `outreach-mining-tranche` (Mon/Wed/Fri),
`outreach-auto-kick` (daily), `outreach-watch-poll` (every 3 h).

**Verification.** `pytest tests/ -v`, `ruff check`, `uvx ty check`, plus a
codified logging contract (`docs/LOGGING.md`).
