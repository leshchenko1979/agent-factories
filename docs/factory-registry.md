# Fleet Factory Registry

**Generated** by `tools/registry.py render` — never hand-edited; the drift gate re-renders and compares the state-bearing bytes.

**resolved at** `2026-10-03T06:17:59Z` — every binding, lane and job row below was read at that instant. The declared half ages on its own clock: a moved binding is a state change (re-rendering fixes it), while an old attestation is a process failure (re-rendering fixes nothing).

## Freshness

| Half | Source | State |
|---|---|---|
| declared | 6 fragment(s) | 6 attested, 0 awaiting an answer |
| generated | live reads | resolved `2026-10-03T06:17:59Z` |

## Announcements

Deduplicated by `id` across every fragment: several lanes noticing one fact is one statement with several declarers. An entry naming a `check` is mechanically verified; the rest rest on `review_by` alone.

### 🟡 warning (19)

- 🟡 **`ops-lane-silence-on-provider-5xx`** — An ops-profile lane can fall silent for ~1.9 h with nothing posted in its topic: when the provider fallback chain holds only the provider that is failing, five 5xx retries exhaust and the turn settles Failed producing no text. The chain is now [inferhub, openrouter], so a repeat is less likely, but the class is not closed - the daemon accepts a one-entry chain equal to its own provider and logs '1 ready, 0 skipped' with no warning.
  - affects: profile · since: 2026-10-01T19:35:04Z · review by: 2026-10-16 · declared by: infra-factory
- 🟡 **`bothelp-relay-load-bearing-on-vpn`** — vpn now serves a critical channel's live webhook: bothelp.l1979.ru/telegram is the investor bot's production Telegram webhook, terminated by Caddy on vpn and forwarded to the relay on 127.0.0.1:8770. The owner made this permanent on 2026-09-29 (it is no longer a pilot). Removing that vhost, or taking vpn down for maintenance without warning, sends Telegram's webhook to a 404 and the channel goes silent. Tell Infra Factory HQ before any vpn Caddy/kernel/reboot/address change; the designed mitigation is one command each way to return the webhook to BotHelp's own address for the window. The relay application and its channel logic are NOT this factory's - hosted here and monitored by Gatus, changed in the redevest-ai repo.
  - affects: profile · since: 2026-09-29 · declared by: infra-factory
- 🟡 **`miidas-platform-moved-to-agents-old`** — The MIIDAS platform runs on agents-old (89.125.120.5:52676), not apps; apps holds the stopped rollbacks (5 containers, Exited). Do not start the stopped apps containers. The claim forward is miidas-claim-forward.service ON apps (active + enabled), tunnelling 172.18.0.1:8765 to agents-old. The APP_HOST footgun this notice originally warned about is CLOSED: deploy_lib.sh no longer defaults to apps — it applies an environment override first and defaults to agents-old only when unset (deploy_lib.sh:21-34, :36), .master.env:34 reads agents-old, and leshchenko1979/miidas#82 is MERGED (2026-09-29T08:39:31Z), not a draft. A repo deploy with no override now lands on agents-old.
  - affects: profile · since: 2026-09-28T23:23:39Z · declared by: miidas
- 🟡 **`miidas-slot-volume-git-config-carries-remote-credential`** — Every miidas client slot volume's .git/config (mode 644) carries the template remote with an INLINE ACCOUNT-LEVEL token, and this is now ACCEPTED AS DATED by the owner (2026-09-28T09:18:36Z) — leshchenko1979/miidas#61 is closed by decision, not by fix, so no rotation is coming. The operational rule therefore stands permanently rather than pending: a peer reclaiming, copying, backing up or decommissioning a miidas slot volume must treat the VOLUME as secret-bearing — it outlives the container, the credential is readable by the client's own agent and not only by a host operator, and the agent image layer carries it too.
  - affects: profile · since: 2026-09-27T11:39:51Z · declared by: miidas
- 🟡 **`inferhub-auto-route-failure-escalation`** — Routing through the ops fallback chain remains unreliable, but the failure CLASS SHIFTED. The 2026-09-27 escalation (2,852 failures / 13.4% over 24h, concentrated on cheap iq-75-plus members) RECEDED — 09-28 22:00Z and 23:00Z each recorded 0 failures at ~1,300 requests. Live since: the gateway's STREAMING path — handshake timeouts ran 14.2% across 09-27 rising to 33.6% across 09-28, flat across every prompt band (30.6% under 50k, 31.4% above 300k) while /health answers sub-second — so it surfaces as latency (retries usually recover it), not loss, and route selection is not the cause. Tracked on #158.
  - affects: profile · since: 2026-09-27T06:36:31Z · declared by: inferhub-watch
- 🟡 **`ops-daemon-dies-at-cgroup-cap`** — An unanswered notify to an ops-profile lane may be a re-push after ANY daemon restart, not a lane declining. The ops daemon restarts constantly, and every restart opens a boot-drain window that re-pushes parked rows, so a re-push is the COMMON case and a crash the minority one. Count restarts as STARTED events; a grep for 'Started|Stopped' returns their union and reads as roughly double the true count. Check `journalctl --user -u opencrabs-ops` for a Stopping/Stopped pair (deliberate) versus `Main process exited code=dumped` (crash) before concluding indiscipline or a fault.
  - affects: profile · since: 2026-09-27T06:13:19Z · review by: 2026-10-11 · declared by: infra-factory
- 🟡 **`mac-cdp-tunnels-flap-on-sleep`** — The Mac's CDP and SSH tunnels drop because the Mac is POWERED OFF overnight, not because it sleeps: pmset reports sleep=0 (it never sleeps), and its only repeating power event is a 2:55AM WAKE, which cannot raise a machine that is off. Apple M4 (Mac16,10). Observed power-offs carry it offline for hours at a time, so any browser task through the Mac CDP path fails for the whole window - and no overlay fixes it, because a powered-off host is offline on every transport, Tailscale included.
  - affects: profile · since: 2026-09-26 · review by: 2026-10-10 · declared by: infra-factory
- 🟡 **`miidas-platform-compose-is-repo-written`** — The miidas platform compose on agents-old (/data/projects/miidas/compose/docker-compose.yml) is written from our repo: manager/deploy.sh:33, landing/deploy.sh:27 and deploy-all.sh:36 each scp the repo copy over the live one, so a host-side edit there is silently reverted by the next of those deploys. That directory deliberately carries no .env, so a hand-run `docker compose up -d` from it fails closed naming the missing variable — use the sanctioned scripts, or pass --env-file ../.master.env. The sync helper is deploy_lib.sh:157-159 and the sanctioned path is miidas_compose() at deploy_lib.sh:163.
  - affects: profile · since: 2026-09-26 · declared by: miidas
- 🟡 **`bot-repo-canonical-account-and-deploy-home`** — leshchenko1979 is the CANONICAL GitHub account for this factory (owner ruling 2026-09-25), and leshchenko1979/ai-antispam is the canonical repo: it hosts the production landing page ai-antispam.ru, publishes the image (ghcr.io/leshchenko1979/ai-antispam:main), and is where the deploy workflow is single-homed. The clone at /root/ai-antispam carries TWO remotes and pushes to BOTH, but only the leshchenko1979 push builds or deploys - a push to alexeyleshchenko/ai-antispam is skipped. The BOARD is alexeyleshchenko/ai-antispam and it is NOT where the image or the deploy live. A bare gh run from the clone resolves to leshchenko1979/ai-antispam, so pass --repo alexeyleshchenko/ai-antispam for board work.
  - affects: profile · since: 2026-09-25 · declared by: ai-antispam
- 🟡 **`gatus-config-carries-live-credentials`** — vpn/services/gatus/config/config.yaml carries live credentials in plaintext, including SSH private-key blocks. Never grep it with a context flag (-A/-B), and never print a parsed form of it - json.dumps of a single endpoint dict renders the key field verbatim. Read the KEY NAMES only; to compare a value, hash it in place. The read discipline is necessary but not sufficient: the PRINT is the second chokepoint, and it is the one that fails when the read felt safe. A third chokepoint is any TOOL whose output path renders the file's content: a diff, a checksum-and-dump, or a guard that prints a drift diff between two key-bearing copies discloses both. Read the output path before you ship the tool, not after.
  - affects: profile · since: 2026-09-23 · review by: 2026-10-07 · declared by: infra-factory
- 🟡 **`ops-fallback-chain-reordered`** — The ops-profile client fallback chain is inferhub, openrouter — two hops, inferhub first. The earlier four-hop chain (inferhub, opencode, openrouter, gemini) has been trimmed; opencode and gemini remain configured providers but are no longer in the chain. Any lane running on the ops profile reaches a provider through this order, failing over from inferhub to openrouter.
  - affects: profile · since: 2026-09-19T12:21:40Z · declared by: inferhub-watch
- 🟡 **`pacemaker-triggers-still-pass-mode-quiet`** — Pacemaker cron triggers on this box still pass `--mode quiet` for three jobs, NONE of them meta-factory's: `ai-antispam-owner-digest` and `ai-antispam-triage-sweep` (ai-antispam, both ENABLED), and `oc-triage-owner-digest` (opencrabs-dev, now DISABLED — so only TWO of the three are live; the earlier "all three enabled" is superseded). The owner re-ruling of 2026-09-19T03:34:30Z / 03:36:54Z made turn-end THE default for all lane traffic and retained quiet only for batch/fan-out notices whose ack contract is the ledger; a single-lane pacemaker is not batch/fan-out, so each of these defers instead of waking an idle lane immediately. Meta-factory's jobs were moved to explicit `--mode turn-end` on 2026-09-23 (byte-verified; schedule and next_run_at preserved): of its SEVEN `factory-*` jobs, FIVE carry it (`factory-measurement-daily`, `factory-triage-patrol`, `factory-insights-weekly`, `factory-template-weekly`, `factory-growth-map-biweekly`) and TWO carry none (`factory-registry-attest`, `factory-publish`). Infra-factory's four now read plain `--mode turn-end` with no cap flags, so the pattern is demonstrated by a second factory rather than asserted. CAUTION FOR WHOEVER FIXES THE REMAINING TWO — the cap flag cannot be dropped alone: each carries `--mode quiet --quiet-for-secs 20 --max-delay-secs 30`, and its prompt documents WHY the cap is there, namely that quiet's DEFAULT starvation cap of 1800s blocks past the tool's 120s budget and kills the trigger. That hazard is quiet-specific and vanishes under turn-end, so the mode and the cap move TOGETHER and the sentence justifying the cap must be rewritten with them, or the prompt ends up arguing for a flag it no longer carries. Live census 2026-10-02T06:19Z: of 66 cron rows, 12 carry `--mode` — 9 turn-end, 3 quiet (one of the three disabled). Prior censuses kept as the steps this one follows, never overwritten: 2026-10-01T06:07Z of 65 rows, 12 — 9 turn-end / 3 quiet; 2026-09-29T08:26Z of 64, 12 — 9/3; 2026-09-28T11:35:19Z of 63, 12 — 9/3; 2026-09-26T06:20Z of 57, 12 — 9/3; 2026-09-23T11:31Z of 55, 13 — 10/3.
  - affects: profile · since: 2026-09-19T03:36:54Z · declared by: meta-factory
- 🟡 **`cron-result-lost-on-restart`** — A cron job whose run is interrupted by an OpenCrabs daemon restart delivers its result to NO channel: boot revival resumes the turn with no job identity, run id or deliver_to, so the job output reaches nobody. Ship-chain hot-reloads make restarts frequent, so any factory relying on cron delivery is exposed.
  - affects: profile · since: 2026-09-19 · review by: 2026-10-07 · declared by: infra-factory
- 🟡 **`notify-now-mode-retired`** — session_notify's 'now' mode is RETIRED and passing it FAILS the delivery outright - it is not merely discouraged. 'turn-end' is the default and wakes an idle target immediately, so it loses nothing 'now' ever delivered; 'quiet' is retained for batch notices whose ack contract is the ledger. 'interrupt' is the URGENT tier (#393): it delivers at the SAME boundary as turn-end and adds precedence framing so the target yields its current plan and answers in that turn - never deferred, never a default, spell it explicitly. It is NOT pre-emption: no boundary exists inside a running tool call, so a mid-turn target still queues for its next tool-loop boundary. Legacy interrupt:true UPGRADES a non-quiet resolution to that tier. A 'no wake observed' confirm verdict means the target is mid-turn; never re-send on it.
  - affects: profile · since: 2026-09-19 · review by: 2026-12-19 · declared by: opencrabs-dev
- 🟡 **`inferhub-autoswitcher-retired`** — The auto-switcher is RETIRED and no automation executes a route switch (owner order 2026-09-18). AMENDED 2026-09-27: enforcement moved from a flag to an opt-in gate — scripts/sync_usage_logs.py now runs the switcher leg only under an explicit --run-switch, so --skip-switch is a DEPRECATED NO-OP that no longer prevents a switch (#152). A bare run therefore cannot reach it; do not re-arm either path.
  - affects: infra-factory · since: 2026-09-18T22:51:42Z · declared by: inferhub-watch
- 🟡 **`inferhub-root-credential-in-shared-compose`** — LIVE ROOT CREDENTIALS REMAIN COMMITTED in files this factory and infra-factory both touch: /root/inferhub-watch carries the New-API root access token (len 32, sha256_8 de0d7f4c) in scripts/sync_newapi_channels.py and scripts/sync_newapi_pricing.py, and vds-servers' new-api compose carries that token plus INITIAL_ROOT_PASSWORD and SESSION_SECRET. AMENDED 2026-09-27: THE OWNER HAS DECIDED — asked whether to rotate, he answered 'Accept the exposure as dated, no rotation' (register q4). Rotation is therefore NOT owed and NOTHING IS PENDING; do not re-raise it as an open item.
  - affects: infra-factory · since: 2026-09-17T01:08:46Z · declared by: inferhub-watch
- 🟡 **`two-files-named-skill-md`** — Two different files are named SKILL.md for this factory and they are not copies: /root/ai-antispam/SKILL.md (repo-backed, versioned with the code) and the profile router /root/.opencrabs/profiles/ops/skills/ai-antispam/SKILL.md (the law lanes actually load; it carries its own version field and moves independently of the repo file). Confirm which one you mean before editing - a change to the wrong one is invisible.
  - affects: ai-antispam · since: 2026-09-17 · declared by: ai-antispam
- 🟡 **`miidas-volume-namespace-on-apps`** — The miidas_* Docker volume namespace and the miidas-* container namespace belong to the MIIDAS factory. A peer reclaiming or pruning must match ^miidas_ and never a bare substring: miidas-pixel-data belongs to another project and is not ours. The estate spans two hosts: agents-old holds 5 RUNNING containers and 1 volume matching ^miidas_ (miidas_maple-c23a-data); apps holds 5 STOPPED containers and 1 such volume. Read 2026-10-01T06:27Z.
  - affects: profile · since: 2026-09-13T09:56:00Z · declared by: miidas
- 🟡 **`gh-pages-origin-ahead-not-diverged`** — The two gh-pages refs are NOT diverged - origin/gh-pages is a strict FAST-FORWARD ahead of alexey/gh-pages (0 ahead / 1 behind): the extra commit is 02d743b 'Delete CNAME' (2026-09-11). The CNAME file is present at alexey/gh-pages's head and absent at origin's, yet ai-antispam.ru still serves because the Pages SETTING carries the domain, not the file. So: never force-push alexey/gh-pages over origin's (it would DROP that commit), and never enable Pages from gh-pages on alexeyleshchenko/ai-antispam - that repo's gh-pages still holds a CNAME for ai-antispam.ru, so two repos would claim one domain. Pages belongs to leshchenko1979/ai-antispam, which is where it is enabled and built.
  - affects: ai-antispam · since: 2026-09-11 · declared by: ai-antispam

### 🔵 info (6)

- 🔵 **`brain-metrics-baseline-measured`** — Brain metrics are a STANDING reading with an instrument: tools/brain_metrics.py (no args needed; --home / --hours / --log-dir / --window) prints all three legs with their predicate, population and instant, and gates none of them. The clause that binds it is docs/measurement-procedure.md section 5; its gate is tests/test_brain_metrics.py. A figure in this notice is a DATED READING and never current — run the instrument.

LEG C — CORRECTED 2026-10-01; the earlier wording is SUPERSEDED, not repeated. The earlier text claimed the automatic threshold trigger was DORMANT, having "fired 0 times since the 1M window". That is FALSE on this box today, measured two ways in one turn: (a) the trigger line itself — "Context at NN% (>65%) — triggering LLM compaction", emitted at src/brain/agent/service/compaction.rs:445/460 (the earlier text cited :418; the line moved) — fired 525 times across 20 distinct sessions in the 2026-10-01 log, this lane's session among them, and this lane was compacted mid-loop today; (b) the instrument's LEG C, which parses the DIFFERENT summarizer line at context.rs, read n=159 events in its 24h window — mean 73022 tok = 36.5% of a 200000-token window, median 79677, p90 114738, max 156319. The trigger line's denominator is NOT the provider window: it is effective tokens over effective max (the window minus reserves), so the earlier notice's equation "the 65-percent gate = 650000 tokens" conflates two denominators, which the instrument's own BOUNDS section 1 forbids. Never read a trigger-line percentage as a fraction of the provider window.

CONSEQUENCES the earlier text got backwards: (a) the note pipeline is NOT starved — save_compaction_summary_to_memory is the sole writer of memory/<date>.md, and with 159 summarizer sends in 24h a note exists for any day lanes are active, so memory_search's default scope is supplied rather than blind; (b) a count of compaction events tracks how many lanes were awake and how many turns they ran, never the weight of the law.

TWO CORRECTIONS worth keeping from the earlier text, both category errors: (a) the "110423 / 1000000 input tokens" line reports the SUMMARIZER'S PAYLOAD against its own input budget (context.rs), which is NOT the trigger's reading; (b) FullWindow is a CompactionScope (WHAT gets compacted), not a trigger KIND.

Fresh reading 2026-10-01T06:08:14Z: LEG A, the always-injected Tier 0 triple (SOUL.md, USER.md, AGENTS.md; in no repository, so a leg-A reading has an INSTANT for its identity and no revision) 186 lines / 33598 B / ~9599 tok (proxy) = 4.80% of a 200000-token window. LEG B, skills/*/SKILL.md (depth 1): 841 lines / 84589 B / ~24168 tok (proxy) = 12.08%. COMBINED = ~33767 tok (proxy) = 16.88% of a 200000-token window, against ~29897 tok = 14.95% at 2026-09-19 — a delta of +1.94 points. LEG C as above. The combined figure FELL 42.95% (2026-09-26) to 33.17% (2026-09-28) to 16.88% now, because the always-injected files shrank (AGENTS.md 458 lines / 144957 B to 186 lines / 33598 B); the floor is not monotonically rising.
  - affects: profile · since: 2026-09-28T12:19:23Z · declared by: meta-factory
- 🔵 **`miidas-kit-forks-declared`** — miidas vendors the fleet kit pin (registry/kit.json, version 6ab591c618ec, 128 paths declared) and declares 19 divergences from it in registry/kit-exemptions.json. Its gate 23 (tests/test_kit_pin_member.py — a SCRIPT, run `python3 tests/test_kit_pin_member.py`; it is not a pytest module and pytest collects nothing from it) reds on any UNDECLARED divergence and passes clean today: 27 carried paths judged, 1 factory-class path excluded by class, 19 forks declared, 0 undeclared. A peer porting a kit instrument into this factory must add the exemption entry in the same change, or the factory audit goes red — that refusal is deliberate, not drift.
  - affects: profile · since: 2026-09-27T05:24:07Z · declared by: miidas
  - evidence: Measured 2026-09-27T11:44Z by the registry writer: tests/test_kit_pin_member.py rc=0, 'judged 24 carried path(s); 1 factory-class path(s) excluded by class; 17 declared exempt'; pin version 6ab591c618ec, 128 paths declared. The gate path is named in the text because the loader's `check` field names an ALLOWLISTED predicate and is never executed - a path there is refused.
- 🔵 **`board-gates-declared-inapplicable`** — Two gates in this factory suite are RED BY DESIGN and must not be reported as a regression: tests/test_board_intake_recorded.py and tests/test_close_board_recorded.py assert a board/ledger close agreement, and this factory issue board IS its ledger - ONE surface - so the two-surface predicate is INAPPLICABLE rather than failed. Declared at ledger n=611 and carried in instruments.pacemaker.reason.
  - affects: profile · since: 2026-09-27 · review by: 2026-10-12 · declared by: infra-factory
  - evidence: Ledger n=611 (two layers: the requirement origin commit d6c9d55 is absent from this repo, and SKILL.md:29 declares the issue board to be the local ledger). Independently raised as a false regression by two lanes before it was declared.
- 🔵 **`vds-servers-single-writer-route`** — /root/vds-servers is single-writer and commit-gated: peers must not commit to it, and fleet changes (host config, Gatus, cleanup, host-diag) are routed to Infra Factory HQ rather than edited in place.
  - affects: profile · since: 2026-09-19 · declared by: infra-factory
- 🔵 **`llm-gateway-per-service-user`** — The LLM gateway (llm.l1979.ru) carries a dedicated NON-root service user per consumer rather than one shared fleet credential: miidas (id 5, role 1, management credential NEWAPI_MIIDAS_TOKEN, quota 500000000000 units), alongside peer service users avito-bot and opencrabs-fleet. A factory provisioning LLM keys for its own clients should ask the gateway owner for its own service user rather than reuse the fleet root credential.
  - affects: profile · since: 2026-09-18T01:53:06Z · declared by: miidas
- 🔵 **`miidas-hq-daily-trigger-is-ours`** — cron miidas-hq-daily-trigger (0 9 * * *, enabled, delivers to session e4f96a33-45ac-412e-8788-1b678cf2addb, the HQ topic) is the MIIDAS factory's own pacemaker. Peers must not disable, repace or repoint it.
  - affects: profile · since: 2026-09-11T00:00:00Z · declared by: miidas

## Reachability

| Hop | Mechanism | State |
|---|---|---|
| lane -> lane, same factory | `session_notify` (UUID) | works |
| factory -> factory, same profile | `session_notify` (UUID) | works |
| factory -> factory, other profile | `opencrabs -p <profile> session notify <uuid>` | works — the CLI posts over that profile's own A2A gateway, so it crosses a process boundary the in-session tool cannot |
| owner -> factory | Telegram topic | works — human surface only; agents do not read topics |

CLI exit contract: `0` delivered/redirected/parked · `2` unknown or dead uuid · `4` **transport — a catch-all, not a diagnosis**. Exit `4` carries at least three causes: the A2A gateway being unreachable, `--mode now` being refused as retired, and pure **caller errors** — `--status` with no id, a missing `--text`, an empty `--text` — because there is no `EXIT_USAGE` constant for those to land in. So on rc 4 a caller **cannot tell a retryable infrastructure condition from a non-retryable caller bug**: read the reason string before retrying, and never treat rc 4 as a blanket retry. Exit `3` is retained as a constant but is **unreachable**: no CLI flag produces it, because a mid-turn target queues rather than refusing.

**Omit `--mode` entirely.** The flag's own help still reads `now (default)`, but the runtime's default is `turn-end` — verified by probe against a live target: no `--mode` at all → rc 0 `delivered`; `--mode turn-end` → rc 0 `delivered`; `--mode now` → rc 4 `delivery.mode 'now' is retired`. A route documented from the help text would hand the reader the one value that cannot work.

## Factories

### ai-antispam — ai-antispam

| Field | Value |
|---|---|
| freshness | ✅ attested 2026-10-02T06:48:32Z |
| purpose | Run the ai-antispam AI spam-blocker bot service (Telegram + MAX) and the outreach campaign that recruits channel owners to install it. |
| profile | `ops` |
| repo | `/root/ai-antispam` |
| law | `/root/ai-antispam/SKILL.md` — revision 0.1.0 |
| owns | ['the ai-antispam bot service repo /root/ai-antispam (LLM classifier, handlers, deploys)', 'the outreach campaign repo /root/ai-antispam-outreach and its Postgres state', 'Postgres ai_spam_bot on apps (schema outreach; single writer outreach/lib/db.py)', 'the MAX domain - API surface, webhook ingress, subscription, moderation port', "this factory's own chat (-1003993000918), its topics and its 19 cron rows (16 enabled, 3 disabled: ai-antispam-62-close-gate is a daily 03:15 UTC trigger-gated close gate, disabled 2026-10-01 and retired per q13; ai-antispam-day7-retire-wake and ai-antispam-watch-funnel-day7-report are 2027 one-shots)", 'the ai-gateway ai-antispam route write - its steps, step_timeout and route_timeout (q11, owner-answered 2026-10-01T10:41:21Z: HQ is the single writer; the LLM Gateway lane keeps the repo copy and the drift guard)'] |
| does not own | ['the OpenCrabs daemon, its core tools, brain/skill loading - OpenCrabs factory', 'VDS host infrastructure, fleet deploy scripts, Gatus - infra-factory', 'token provisioning, model routing (EXCEPT the ai-gateway ai-antispam route, which this factory writes per q11), inference pricing - inferhub-watch', 'the factory template and meta-factory law - meta-factory', 'Miidas accounting - miidas', 'tg_* tools (fast-mcp-telegram) and telegram_send (OpenCrabs core)'] |
| substrates owned | ['/root/ai-antispam - public repo leshchenko1979/ai-antispam (canonical, remote origin; board alexeyleshchenko/ai-antispam, second remote via SSH alias github.com-alexey)', '/root/ai-antispam-outreach - private repo leshchenko1979/ai-antispam-outreach', 'Postgres ai_spam_bot on apps - single writer outreach/lib/db.py', 'the bot container and MAX webhook route on apps'] |
| attested at | 2026-10-02T06:48:32Z |

**Services**

| name | audience | entry | cadence |
|---|---|---|---|
| ai-spam-blocker bot (Telegram + MAX moderation) | owner | apps host: /process-tg-updates and /process-max-updates webhooks | continuous, event-driven |
| ai-antispam-self-audit-daily | agent | cron f5256d96-3d12-47f7-95ab-082d8db4d741 | daily 08:50 MSK |
| ai-antispam-owner-digest | owner | cron a3a292e7-4c14-401e-8095-02e86f5530ea | daily 09:30 MSK |
| ai-antispam-bot-service-health | owner | cron d2c7e157-9370-4752-a054-c853b4bb2d3c | daily 09:00 MSK |
| ai-antispam-triage-sweep | agent | cron e1588fe5-ddbb-4f4f-84f4-b6e06513683c | every 6h UTC at :25 |
| ai-antispam-outreach-watch-poll | agent | cron cfb86dc5-4be4-4984-8331-d682504d2d1f | every 6h UTC at :07 |
| ai-antispam-stream-liveness-check | agent | cron 3384c696-7b75-4668-97c3-a73eab96e38e | every 6h UTC at :40 |
| ai-antispam-outreach-auto-kick | agent | cron e1fb18bc-0e0c-432e-a54a-1734feab7438 | daily 07:00 UTC |
| ai-antispam-outreach-mining-tranche | agent | cron f3f5f53c-d218-4cf3-9bbc-d26a12c3f9ca | Mon/Wed/Fri 06:00 UTC |
| ai-antispam-wave0-reply-sweep | agent | cron 5e515bac-fb81-41c6-b1e2-603ab824ad90 | daily 12:00 MSK |
| ai-antispam-wave0-unactivated-reprobe | agent | cron 61fcbbfc-e365-4db0-926b-2ad13873a517 | Tue 12:00 MSK |
| ai-antispam-timeout-monitor | agent | cron ai-antispam-timeout-monitor | daily 12:00 UTC |
| ai-antispam-43-close-gate | agent | cron ai-antispam-43-close-gate | daily 12:05 UTC, trigger-gated |
| ai-antispam-outreach-stream-joins | agent | cron ai-antispam-outreach-stream-joins | daily 00:00 UTC |
| ai-antispam-outreach-db-sync | agent | cron 7ddb69a4-7ec9-4140-9791-2d651cead4c4 | daily 09:00 MSK — ENABLED |
| ai-antispam-52-close-gate | agent | cron 30 11 * * * UTC, trigger-gated on date>=2026-09-28 AND #52 open | daily 11:30 UTC |
| ai-antispam-62-close-gate | agent | cron 15 3 * * * UTC, trigger-gated on date>=2026-09-29 AND #62 open | daily 03:15 UTC — DISABLED (see anomaly below) |
| ai-antispam-loss-watch | agent | cron 65b4457f-2b33-4326-8970-f1973bf77ab1 | every 30 min UTC — ENABLED |
| ai-antispam-day7-retire-wake | agent | cron 9caeac81-e355-4bd0-8704-a0e9aad27abc | disabled 2027 one-shot (22 Sep 2027 06:15 UTC) |
| ai-antispam-watch-funnel-day7-report | owner | cron 23e41198-75b4-41b4-acc0-4059a1972974 | disabled 2027 one-shot (22 Sep 2027 09:00 MSK) |

**Announcements reaching this factory**

- 🟡 **`bot-repo-canonical-account-and-deploy-home`** — leshchenko1979 is the CANONICAL GitHub account for this factory (owner ruling 2026-09-25), and leshchenko1979/ai-antispam is the canonical repo: it hosts the production landing page ai-antispam.ru, publishes the image (ghcr.io/leshchenko1979/ai-antispam:main), and is where the deploy workflow is single-homed. The clone at /root/ai-antispam carries TWO remotes and pushes to BOTH, but only the leshchenko1979 push builds or deploys - a push to alexeyleshchenko/ai-antispam is skipped. The BOARD is alexeyleshchenko/ai-antispam and it is NOT where the image or the deploy live. A bare gh run from the clone resolves to leshchenko1979/ai-antispam, so pass --repo alexeyleshchenko/ai-antispam for board work.
  - affects: profile · since: 2026-09-25 · declared by: ai-antispam
- 🟡 **`gh-pages-origin-ahead-not-diverged`** — The two gh-pages refs are NOT diverged - origin/gh-pages is a strict FAST-FORWARD ahead of alexey/gh-pages (0 ahead / 1 behind): the extra commit is 02d743b 'Delete CNAME' (2026-09-11). The CNAME file is present at alexey/gh-pages's head and absent at origin's, yet ai-antispam.ru still serves because the Pages SETTING carries the domain, not the file. So: never force-push alexey/gh-pages over origin's (it would DROP that commit), and never enable Pages from gh-pages on alexeyleshchenko/ai-antispam - that repo's gh-pages still holds a CNAME for ai-antispam.ru, so two repos would claim one domain. Pages belongs to leshchenko1979/ai-antispam, which is where it is enabled and built.
  - affects: ai-antispam · since: 2026-09-11 · declared by: ai-antispam
- 🟡 **`two-files-named-skill-md`** — Two different files are named SKILL.md for this factory and they are not copies: /root/ai-antispam/SKILL.md (repo-backed, versioned with the code) and the profile router /root/.opencrabs/profiles/ops/skills/ai-antispam/SKILL.md (the law lanes actually load; it carries its own version field and moves independently of the repo file). Confirm which one you mean before editing - a change to the wrong one is invisible.
  - affects: ai-antispam · since: 2026-09-17 · declared by: ai-antispam

**Lanes**

| topic | thread | role | session | session title | status | channel | last active | lane announcements |
|---|---|---|---|---|---|---|---|---|
| Outreach | 10780 | outreach | `acc3fa9b-cefa-4e35-bf87-422696e558f0` | Telegram: ai-antispam / Outreach [chat:-1003993000918:topic:10780] | superseded | telegram | 2026-09-26T17:30:41Z | — |
| Triage | 10781 | triage | `6ca0d547-4a72-4c29-ac10-967daa98af0a` | Telegram: ai-antispam / Triage [chat:-1003993000918:topic:10781] | resolved | telegram | 2026-10-01T11:01:30Z | — |
| HQ | 10782 | hq | `cb06a94a-be02-4e8c-b6c6-c8c9f09922f4` | Telegram: ai-antispam / HQ [chat:-1003993000918:topic:10782] | resolved | telegram | 2026-10-02T20:28:52Z | — |
| ai-antispam Landing lane | 10783 | landing | `99b348f6-a040-4119-8aa8-00736c7fb61d` | ai-antispam Landing lane | resolved | telegram | 2026-09-11T21:55:58Z | — |
| Bot lane — ai-antispam service (Bot topic) | 10784 | bot | `6d921dca-fb0a-455b-bceb-dfb78dcf1f07` | Bot lane — ai-antispam service (Bot topic) | resolved | telegram | 2026-10-02T20:29:26Z | — |
| MAX domain — lane acceptance & verification | 11156 | _unstated_ | `85425045-2567-4beb-9867-100d6755e2cd` | MAX domain — lane acceptance & verification | resolved | telegram | 2026-09-15T03:45:41Z | — |

**Pacemakers**

| job | home | cron_expr | timezone | enabled | set_goal | goal_template | next_run_at | deliver_to | trigger_cmd |
|---|---|---|---|---|---|---|---|---|---|
| `ai-antispam-43-close-gate` | ops | `5 12 * * *` | UTC | yes | 0 | **absent** | 2026-10-03T12:05:00+00:00 | session:6d921dca-fb0a-455b-bceb-dfb78dcf1f07 | [ "$(date -u +%Y%m%d)" -ge 20260927 ] && /usr/local/bin/gh issue view 4… |
| `ai-antispam-52-close-gate` | ops | `30 11 * * *` | UTC | yes | 0 | **absent** | 2026-10-03T11:30:00+00:00 | session:6d921dca-fb0a-455b-bceb-dfb78dcf1f07 | D=$(date -u +%Y%m%d); S=$(gh issue view 52 --repo alexeyleshchenko/ai-a… |
| `ai-antispam-62-close-gate` | ops | `15 3 * * *` | UTC | **no** | 0 | **absent** | 2026-10-02T03:15:00+00:00 | session:6d921dca-fb0a-455b-bceb-dfb78dcf1f07 | D=$(date -u +%Y%m%d); S=$(gh issue view 62 --repo alexeyleshchenko/ai-a… |
| `ai-antispam-bot-service-health` | ops | `15 9 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-10-04T06:15:00+00:00 | telegram:-1003993000918:10784 | — |
| `ai-antispam-day7-retire-wake` | ops | `15 6 22 9 *` | UTC | **no** | 0 | **absent** | 2027-09-22T06:15:00+00:00 | session:acc3fa9b-cefa-4e35-bf87-422696e558f0 | — |
| `ai-antispam-loss-watch` | ops | `15,45 * * * *` | UTC | yes | 0 | **absent** | 2026-10-03T06:45:00+00:00 | session:6d921dca-fb0a-455b-bceb-dfb78dcf1f07 | /usr/bin/python3 /root/ai-antispam/scripts/loss_watch.py --state /root/… |
| `ai-antispam-outreach-auto-kick` | ops | `0 7 * * *` | UTC | yes | 0 | **absent** | 2026-10-03T07:00:00+00:00 | telegram:-1003993000918:10780 | — |
| `ai-antispam-outreach-db-sync` | ops | `15 9 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-10-04T06:15:00+00:00 | telegram:-1003993000918:10780 | — |
| `ai-antispam-outreach-mining-tranche` | ops | `15 6 * * Mon,Wed,Fri` | UTC | yes | 0 | **absent** | 2026-10-05T06:15:00+00:00 | telegram:-1003993000918:10780 | — |
| `ai-antispam-outreach-stream-joins` | ops | `0 0 * * *` | UTC | yes | 0 | **absent** | 2026-10-04T00:00:00+00:00 | telegram:-1003993000918:10780 | — |
| `ai-antispam-outreach-watch-poll` | ops | `7 */6 * * *` | UTC | yes | 0 | **absent** | 2026-10-03T12:07:00+00:00 | telegram:-1003993000918:10780 | — |
| `ai-antispam-owner-digest` | ops | `30 9 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-10-03T06:30:00+00:00 | — | — |
| `ai-antispam-self-audit-daily` | ops | `50 8 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-10-04T05:50:00+00:00 | session:cb06a94a-be02-4e8c-b6c6-c8c9f09922f4 | — |
| `ai-antispam-stream-liveness-check` | ops | `40 */6 * * *` | UTC | yes | 0 | **absent** | 2026-10-03T06:40:00+00:00 | telegram:-1003993000918:10780 | timeout 25 python3 -u /root/ai-antispam-outreach/outreach/scripts/strea… |
| `ai-antispam-timeout-monitor` | ops | `0 12 * * *` | UTC | yes | 0 | **absent** | 2026-10-03T12:00:00+00:00 | telegram:-1003993000918:10784 | CT=$(ssh apps "docker ps --filter name=ai-antispam --format '{{.Names}}… |
| `ai-antispam-triage-sweep` | ops | `25 */6 * * *` | UTC | yes | 0 | **absent** | 2026-10-03T06:25:00+00:00 | — | out=$(timeout 25 /usr/bin/python3 -u /root/.opencrabs/profiles/ops/skil… |
| `ai-antispam-watch-funnel-day7-report` | ops | `0 9 22 9 *` | Europe/Moscow | **no** | 0 | **absent** | 2027-09-22T06:00:00+00:00 | telegram:-1003993000918:10780 | — |
| `ai-antispam-wave0-reply-sweep` | ops | `0 12 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-10-03T09:00:00+00:00 | telegram:-1003993000918:10780 | — |
| `ai-antispam-wave0-unactivated-reprobe` | ops | `0 12 * * 2` | Europe/Moscow | yes | 0 | **absent** | 2026-10-05T09:00:00+00:00 | telegram:-1003993000918:10780 | — |

Attribution basis: deliver_to -> chat, deliver_to -> lane, name prefix.
`trigger_cmd` is truncated to 72 characters here; the full command is in `registry/index.json`.
2 of 19 job(s) carry no explicit `deliver_to`. The column is rendered as the live row holds it; whether a null falls back to the creating session or to nothing is the scheduler's contract, and this registry does not assert it.

### inferhub-watch — Inferhub watch

| Field | Value |
|---|---|
| freshness | ✅ attested 2026-10-02T13:13:05Z |
| purpose | Give the owner timely Value-ranked route intelligence from the InferHub inference auction — which routes to use, at what measured price and reliability — and keep production gateway routing (New-API channel tiers and the client fallback chain) pointed at the best measured Value. |
| profile | `ops` |
| repo | `/root/inferhub-watch` |
| law | `/root/inferhub-watch/skills/inferhub/SKILL.md` — revision 1.0.113 |
| owns | ['leshchenko1979/inferhub-watch (/root/inferhub-watch): probe engine, sync and switcher scripts, tests, evidence ledger, and the skills/inferhub process law', 'Grafana dashboard inferhub-watch on grafana.l1979.ru — its panels and queries (datasource inferhub-pg); the dashboard JSON is ours to author', 'Postgres inferhub_logs on apps — route_metrics, usage_logs and model_rollup; this factory is their writer. model_rollup added 2026-09-23 (issue #133): a 30-row aggregate refreshed every 10 min by the no-wake host runner, same shape as route_metrics', 'The new_api channels table on apps as an AUTHORED POLICY OBJECT - the tier ladder named in an earlier fragment NO LONGER EXISTS. Live 2026-10-02: exactly THREE rows - id 43 gemini (status 1 = ENABLED, priority 300, auto_ban 1), id 44 iq-75-plus (status 1 = enabled, priority 200, auto_ban 0), id 46 iq-80-plus (status 3 = AUTO-BANNED, priority 210, auto_ban 1). id 43 is ENABLED again: re-enabled 2026-10-01T20:57:24Z (new_api.audit_logs row 1154, auth_method=session, ip 2.27.120.75) inside a ~2-minute interactive failover-tuning session that had toggled it 1->2 at 20:55:44 (row 1152) and re-enabled id 46 at 20:55:51 (row 1153) - the same self-attributing root-session pattern as the 09-25 re-enable, so it is NOT unattributed. id 46 has since been auto-banned again (status 3). Nothing scheduled writes these rows: sync_newapi_channels.py declares only the ch-tierN-* names.', 'Client-side fallback-chain order and provider settings for all OpenCrabs profiles (four live 2026-10-02: default, family, oc348probe, ops) (owner-granted 2026-09-19)', 'The Inferhub watch forum and its factory lanes (HQ thread 2, worker threads 32 and 559, Grafana thread 557)', "This factory's own crons and its daily GitHub Actions sweep"] |
| does not own | ['The New-API gateway itself — its container, config and serving behaviour on apps (Infra Factory / LLM Gateway lane). We author the channel policy; they run the gateway.', 'Grafana deployment and provisioning, and the generic /grafana skill tooling in /root/vds-servers (Infra Factory)', 'The upstream provider api.inferhub.dev — external; we measure it and never change it', 'OpenCrabs core source (/root/opencrabs): we may file fork issues for runtime anomalies we observe, but we never open PRs or edit source (external-lane boundary)', "Other member factories' repos, lanes and process law", 'Host and box infrastructure (owner)'] |
| substrates owned | ['leshchenko1979/inferhub-watch', "skills/inferhub/SKILL.md — this factory's process law; HQ-only authorship", 'Postgres inferhub_logs on apps — route_metrics, usage_logs, model_rollup', 'Grafana dashboard inferhub-watch — panels and queries', 'The new_api channels table - priority, auto_ban and model_mapping policy. Live 2026-10-02: three rows, ids 43 (ENABLED, status 1, priority 300, auto_ban 1) / 44 (enabled, status 1, priority 200, auto_ban 0) / 46 (auto-banned, status 3, priority 210, auto_ban 1); the tier ladder is gone and no automatic writer runs. id 43 was re-enabled 2026-10-01T20:57:24Z by an interactive root session (new_api.audit_logs row 1154).'] |
| attested at | 2026-10-02T13:13:05Z |

**Services**

| name | audience | entry | cadence |
|---|---|---|---|
| inferhub-usage-logs-sync | agent | cron 2d9112a6-b697-4eeb-b6ac-3e2462e23483, expr 23 */6 * * *, enabled — TAIL-ONLY: its prompt carries --skip-data --skip-scoreboard --skip-switch, so it pages no API and writes no table; the usage_logs data leg belongs to the no-wake host runner /usr/local/bin/inferhub-usage-sync.sh (*/10 — no daemon, no session, no tokens). Do NOT read this cron as the writer of route_metrics or usage_logs | 6h |
| inferhub-hq-pacemaker | agent | cron 5c960cfb-16a5-4a35-918b-5acd1d30336f, expr 10 */6 * * *, enabled, delivers to session 359fe71b | 6h |
| inferhub-daily-report | owner | cron 0120d22f-9974-4f81-a687-e1c152141bea, expr 0 8 * * *, enabled, deliver_to session:359fe71b-c7a1-420b-b856-acfb49939a7b - it delivers to the HQ lane, and its body ALSO renders into the bound topic on its own (the 1.0.105 echo leg); measured 2026-10-02 the card rendered into topic 2 as msg 4790 carrying a '(truncated)' marker (the #490 head+tail elision, working as designed), so no lane re-post is owed. | daily |
| inferhub-self-audit-daily | agent | cron 3d1d00e1-6a41-4088-a1de-aeb6e9a4863c, expr 10 9 * * *, enabled, delivers to session 359fe71b | daily |
| inferhub-auto-switcher | agent | cron fef19c4f-ab16-442e-8ee9-e041d3d0919b, expr 33 */6 * * *, DISABLED | disabled |
| watch.yml scheduled sweep | agent | host crontab dispatcher /usr/local/bin/inferhub-sweep-dispatch.sh at 17 2 * * * (declared once in repo scripts/sweep_schedule.py), which calls gh workflow run; the workflow's own on.schedule line is a deduped BACKSTOP — measured over all 27 scheduled runs to 2026-09-22 it fires +0.7 h to +12.2 h late, mean +5.2 h, and the delay tracks the declaration. Do not treat 02:17Z as GitHub-side | daily 02:17Z (host crontab) |

**Announcements reaching this factory**

- 🟡 **`ops-fallback-chain-reordered`** — The ops-profile client fallback chain is inferhub, openrouter — two hops, inferhub first. The earlier four-hop chain (inferhub, opencode, openrouter, gemini) has been trimmed; opencode and gemini remain configured providers but are no longer in the chain. Any lane running on the ops profile reaches a provider through this order, failing over from inferhub to openrouter.
  - affects: profile · since: 2026-09-19T12:21:40Z · declared by: inferhub-watch
- 🟡 **`inferhub-auto-route-failure-escalation`** — Routing through the ops fallback chain remains unreliable, but the failure CLASS SHIFTED. The 2026-09-27 escalation (2,852 failures / 13.4% over 24h, concentrated on cheap iq-75-plus members) RECEDED — 09-28 22:00Z and 23:00Z each recorded 0 failures at ~1,300 requests. Live since: the gateway's STREAMING path — handshake timeouts ran 14.2% across 09-27 rising to 33.6% across 09-28, flat across every prompt band (30.6% under 50k, 31.4% above 300k) while /health answers sub-second — so it surfaces as latency (retries usually recover it), not loss, and route selection is not the cause. Tracked on #158.
  - affects: profile · since: 2026-09-27T06:36:31Z · declared by: inferhub-watch

**Lanes**

| topic | thread | role | session | session title | status | channel | last active | lane announcements |
|---|---|---|---|---|---|---|---|---|
| HQ | 2 | hq | `359fe71b-c7a1-420b-b856-acfb49939a7b` | InferHub Watch: Fallback Publisher Diversity & Predictors | resolved | telegram | 2026-10-01T08:31:22Z | — |
| LLM Gateway | 32 | worker | `8cbe2d61-79c6-4ca7-8a71-805e2982d4b6` | Telegram: Inferhub watch / Worker — HQ cycles [chat:-1004379632866:topic:32] | resolved | telegram | 2026-10-02T21:29:56Z | — |
| Grafana | 557 | grafana | `7814fc64-e7ce-4274-a4ee-372563aa3c99` | Telegram: Inferhub watch / Worker — #23 Grafana management [chat:-1004379632866:topic:557] | resolved | telegram | 2026-09-25T14:15:57Z | — |
| Worker - InferHub Watch Lane | 559 | worker | `1122b15e-0b26-420f-a7b3-d0719479bbd5` | worker: inferhub-watch-lane | resolved | telegram | 2026-10-01T08:35:35Z | — |

**Pacemakers**

| job | home | cron_expr | timezone | enabled | set_goal | goal_template | next_run_at | deliver_to | trigger_cmd |
|---|---|---|---|---|---|---|---|---|---|
| `inferhub-auto-switcher` | ops | `33 */6 * * *` | UTC | **no** | 0 | **absent** | 2026-09-19T00:33:00+00:00 | — | — |
| `inferhub-daily-report` | ops | `0 8 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-10-04T05:00:00+00:00 | session:359fe71b-c7a1-420b-b856-acfb49939a7b | — |
| `inferhub-hq-pacemaker` | ops | `10 */6 * * *` | UTC | yes | 1 | present | 2026-10-03T12:10:00+00:00 | session:359fe71b-c7a1-420b-b856-acfb49939a7b | — |
| `inferhub-self-audit-daily` | ops | `10 9 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-10-04T06:10:00+00:00 | session:359fe71b-c7a1-420b-b856-acfb49939a7b | — |
| `inferhub-usage-logs-sync` | ops | `23 */6 * * *` | UTC | yes | 0 | **absent** | 2026-10-03T06:23:00+00:00 | — | — |

Attribution basis: deliver_to -> lane, name prefix.
2 of 5 job(s) carry no explicit `deliver_to`. The column is rendered as the live row holds it; whether a null falls back to the creating session or to nothing is the scheduler's contract, and this registry does not assert it.

### infra-factory — Infra Factory

| Field | Value |
|---|---|
| freshness | ✅ attested 2026-10-02T06:13:21Z |
| purpose | Keep the VDS fleet (vpn, apps, agents) and the services it hosts observable, healthy and self-healing: intake Gatus alerts, diagnose hosts, apply safe remediation, and own the fleet infrastructure source repo. |
| profile | `ops` |
| repo | `/root/vds-servers` |
| law | `/root/vds-servers/skills/infra-factory/SKILL.md` — revision 0.2.0 |
| owns | ['Fleet host operations on vpn, apps and agents - diagnosis (host-diag), service and container lifecycle, disk cleanup and safe remediation', 'Gatus monitoring: endpoint configuration, alert intake and recovery routing (gatus-notify on vpn)', 'The fleet infrastructure source repo /root/vds-servers - fleet configs, host scripts, the process register and the factory ledger', 'Host and workspace hygiene: the single reap policy (tools/hygiene.py), its derived gate line, and disk-threshold remediation', 'The Mac access path as fleet infrastructure - the CDP tunnel to the Mac and the route pin on its physical NIC', 'Infra Factory process law and its own lanes (HQ, Triage, Surveys)'] |
| does not own | ['OpenCrabs daemon and harness source, and its development process (/root/opencrabs) - that is opencrabs-dev', 'The factory template, cross-factory laws and fleet measurement - that is meta-factory', 'ai-antispam business logic, its outreach campaign and its Postgres state - that is ai-antispam', 'Miidas product and accounting logic - that is miidas; this factory owns only host-level uptime for its containers', 'InferHub model routing, pricing and token economics - that is inferhub-watch', 'Application logic of services hosted on the fleet (tg-scanner-hub, llm-gateway): hosted and monitored here, changed in their own repos', "Other profiles' brain files and configuration (default, family)", 'The OpenCrabs log-guard watchdog and its root-crontab line on agents (/usr/local/bin/opencrabs-log-guard.sh) - host infrastructure operated by the owner (Alexey). Its source exists in no factory repo, so no factory can declare it as code it owns; it mitigates a closed OpenCrabs daemon defect class (leshchenko1979/opencrabs#21).'] |
| substrates owned | ['/root/vds-servers - the fleet infrastructure source repo (single-writer: its ledger and evidence are appended by tools/ledger.py alone)', 'The fleet hosts vpn, apps and agents - host-level state: systemd units, containers, disk, /usr/local/bin scripts', 'Gatus monitoring configuration and alert routing on vpn', 'The Mac access path (vpn/mac-access: CDP tunnel and route pin)'] |
| attested at | 2026-10-02T06:13:21Z |

**Services**

| name | audience | entry | cadence |
|---|---|---|---|
| Gatus fleet monitoring and alert intake | owner | vpn: vpn/services/gatus/config/config.yaml, delivered by gatus-notify.service (active) | continuous; alerts on endpoint failure |
| infra-triage-patrol | agent | cron d6119dbc-95d2-4341-aeb5-dc1c839cc9ed to the Triage lane; gate /root/vds-servers/tools/triage_preflight.py | 6-hourly (0 */6 * * *) |
| infra-surveys-daily | agent | cron 73e9a3d0-8dfe-48db-a169-3fae3d2a0405 to the Surveys topic (thread 7) | daily 09:00 MSK (0 9 * * *) |
| infra-sender-logs-check | agent | cron 8198815c-45e0-40ff-87d1-bfa19d038c5b to the Triage topic (thread 5) | daily 18:05 (05 18 * * *) |
| host-diag | agent | /usr/local/bin/host-diag on vpn, apps and agents (source vpn/services/gatus/scripts/host-diag) | on demand - alert or patrol |
| Fleet disk cleanup | owner | /usr/local/bin/vds-cleanup.sh on vpn, apps and agents; delegates to /root/vds-servers/scripts/cleanup-unified.sh | weekly, Sun 03:00 (root crontab) - plus on demand at disk >=89% |
| Scratch hygiene reaper | agent | root crontab on agents: python3 /root/vds-servers/tools/hygiene.py --clean | hourly - a host script, not a lane wake |
| infra-handler-escalation-check | agent | cron be4c38ce-d8f6-4d64-b4fe-eaa711af71cc - thin trigger that wakes the TG Hub lane (a360e13f-4e34-4fac-8a1d-770644040903) when a downstream handler goes unactioned past 24 h; delivers no report of its own | daily 00:00 (0 0 * * *) |
| questions.l1979.ru answer surface | owner | vpn: /etc/caddy/Caddyfile vhost questions.l1979.ru -> reverse_proxy 127.0.0.1:8099 (/opt/questions/backend.py under questions-backend.service), serving /srv/questions; the site is basic_auth gated (401 without credentials). Pages and register are pushed agents -> vpn by the oc-questions-push.path systemd USER unit on agents. | continuous; accepts a posted answer and returns it to the asking lane session |

**Announcements reaching this factory**

- 🟡 **`cron-result-lost-on-restart`** — A cron job whose run is interrupted by an OpenCrabs daemon restart delivers its result to NO channel: boot revival resumes the turn with no job identity, run id or deliver_to, so the job output reaches nobody. Ship-chain hot-reloads make restarts frequent, so any factory relying on cron delivery is exposed.
  - affects: profile · since: 2026-09-19 · review by: 2026-10-07 · declared by: infra-factory
- 🔵 **`vds-servers-single-writer-route`** — /root/vds-servers is single-writer and commit-gated: peers must not commit to it, and fleet changes (host config, Gatus, cleanup, host-diag) are routed to Infra Factory HQ rather than edited in place.
  - affects: profile · since: 2026-09-19 · declared by: infra-factory
- 🟡 **`gatus-config-carries-live-credentials`** — vpn/services/gatus/config/config.yaml carries live credentials in plaintext, including SSH private-key blocks. Never grep it with a context flag (-A/-B), and never print a parsed form of it - json.dumps of a single endpoint dict renders the key field verbatim. Read the KEY NAMES only; to compare a value, hash it in place. The read discipline is necessary but not sufficient: the PRINT is the second chokepoint, and it is the one that fails when the read felt safe. A third chokepoint is any TOOL whose output path renders the file's content: a diff, a checksum-and-dump, or a guard that prints a drift diff between two key-bearing copies discloses both. Read the output path before you ship the tool, not after.
  - affects: profile · since: 2026-09-23 · review by: 2026-10-07 · declared by: infra-factory
- 🟡 **`mac-cdp-tunnels-flap-on-sleep`** — The Mac's CDP and SSH tunnels drop because the Mac is POWERED OFF overnight, not because it sleeps: pmset reports sleep=0 (it never sleeps), and its only repeating power event is a 2:55AM WAKE, which cannot raise a machine that is off. Apple M4 (Mac16,10). Observed power-offs carry it offline for hours at a time, so any browser task through the Mac CDP path fails for the whole window - and no overlay fixes it, because a powered-off host is offline on every transport, Tailscale included.
  - affects: profile · since: 2026-09-26 · review by: 2026-10-10 · declared by: infra-factory
- 🟡 **`ops-daemon-dies-at-cgroup-cap`** — An unanswered notify to an ops-profile lane may be a re-push after ANY daemon restart, not a lane declining. The ops daemon restarts constantly, and every restart opens a boot-drain window that re-pushes parked rows, so a re-push is the COMMON case and a crash the minority one. Count restarts as STARTED events; a grep for 'Started|Stopped' returns their union and reads as roughly double the true count. Check `journalctl --user -u opencrabs-ops` for a Stopping/Stopped pair (deliberate) versus `Main process exited code=dumped` (crash) before concluding indiscipline or a fault.
  - affects: profile · since: 2026-09-27T06:13:19Z · review by: 2026-10-11 · declared by: infra-factory
- 🔵 **`board-gates-declared-inapplicable`** — Two gates in this factory suite are RED BY DESIGN and must not be reported as a regression: tests/test_board_intake_recorded.py and tests/test_close_board_recorded.py assert a board/ledger close agreement, and this factory issue board IS its ledger - ONE surface - so the two-surface predicate is INAPPLICABLE rather than failed. Declared at ledger n=611 and carried in instruments.pacemaker.reason.
  - affects: profile · since: 2026-09-27 · review by: 2026-10-12 · declared by: infra-factory
  - evidence: Ledger n=611 (two layers: the requirement origin commit d6c9d55 is absent from this repo, and SKILL.md:29 declares the issue board to be the local ledger). Independently raised as a false regression by two lanes before it was declared.
- 🟡 **`bothelp-relay-load-bearing-on-vpn`** — vpn now serves a critical channel's live webhook: bothelp.l1979.ru/telegram is the investor bot's production Telegram webhook, terminated by Caddy on vpn and forwarded to the relay on 127.0.0.1:8770. The owner made this permanent on 2026-09-29 (it is no longer a pilot). Removing that vhost, or taking vpn down for maintenance without warning, sends Telegram's webhook to a 404 and the channel goes silent. Tell Infra Factory HQ before any vpn Caddy/kernel/reboot/address change; the designed mitigation is one command each way to return the webhook to BotHelp's own address for the window. The relay application and its channel logic are NOT this factory's - hosted here and monitored by Gatus, changed in the redevest-ai repo.
  - affects: profile · since: 2026-09-29 · declared by: infra-factory
- 🟡 **`ops-lane-silence-on-provider-5xx`** — An ops-profile lane can fall silent for ~1.9 h with nothing posted in its topic: when the provider fallback chain holds only the provider that is failing, five 5xx retries exhaust and the turn settles Failed producing no text. The chain is now [inferhub, openrouter], so a repeat is less likely, but the class is not closed - the daemon accepts a one-entry chain equal to its own provider and logs '1 ready, 0 skipped' with no warning.
  - affects: profile · since: 2026-10-01T19:35:04Z · review by: 2026-10-16 · declared by: infra-factory

**Lanes**

| topic | thread | role | session | session title | status | channel | last active | lane announcements |
|---|---|---|---|---|---|---|---|---|
| HQ | 4 | hq | `6a314aac-94db-4b11-974c-f53decc25b9d` | Telegram: Infra Factory / HQ [chat:-1004486255170:topic:4] | resolved | telegram | 2026-09-30T21:16:41Z | — |
| Gatus alert routing and fleet triage | 5 | triage | `fb67ca75-8735-4c39-80be-06b59bd4365f` | Gatus alert routing and fleet triage | resolved | telegram | 2026-09-29T10:13:20Z | — |
| Surveys | 7 | surveys | `8daa376e-367c-452d-840f-0c18d66ef60a` | Telegram: Infra Factory / Surveys [chat:-1004486255170:topic:7] | resolved | telegram | 2026-09-29T07:42:08Z | — |
| LLM Gateway | 467 | gateway | `8b278a4f-531d-4d7b-8c79-87d30f9257bd` | Telegram: Infra Factory / LLM Gateway [chat:-1004486255170:topic:467] | resolved | telegram | 2026-10-03T03:39:21Z | — |
| TG Hub | 475 | _unstated_ | `a360e13f-4e34-4fac-8a1d-770644040903` | Telegram: Infra Factory / TG Hub [chat:-1004486255170:topic:475] | resolved | telegram | 2026-10-01T00:10:26Z | — |

**Pacemakers**

| job | home | cron_expr | timezone | enabled | set_goal | goal_template | next_run_at | deliver_to | trigger_cmd |
|---|---|---|---|---|---|---|---|---|---|
| `infra-handler-escalation-check` | ops | `0 0 * * *` | UTC | yes | 0 | **absent** | 2026-10-04T00:00:00+00:00 | — | P=$(XDG_RUNTIME_DIR=/run/user/0 systemctl --user show opencrabs.service… |
| `infra-mac-backup-verify-oneshot` | ops | `15 19 28 9 *` | Europe/Moscow | **no** | 0 | **absent** | 2027-09-28T16:15:00+00:00 | telegram:-1004486255170:4 | — |
| `infra-sender-logs-check` | ops | `05 18 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-10-03T15:05:00+00:00 | — | — |
| `infra-surveys-daily` | ops | `5 9 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-10-04T06:05:00+00:00 | — | — |
| `infra-triage-patrol` | ops | `5 */6 * * *` | UTC | yes | 0 | present | 2026-10-03T12:05:00+00:00 | — | /root/vds-servers/tools/triage_preflight.py |

Attribution basis: deliver_to -> chat, name prefix.
`trigger_cmd` is truncated to 72 characters here; the full command is in `registry/index.json`.
4 of 5 job(s) carry no explicit `deliver_to`. The column is rendered as the live row holds it; whether a null falls back to the creating session or to nothing is the scheduler's contract, and this registry does not assert it.

### meta-factory — Factories

| Field | Value |
|---|---|
| freshness | ✅ attested 2026-10-02T06:20:45Z |
| purpose | Build, measure and evolve Autonomously Self-Improving Factories: maintain the ASIF template and rulebook that any repository can adopt, and consult member factories on their process health, cadence and autonomy. |
| profile | `ops` |
| repo | `/root/agent-factories` |
| law | `/root/agent-factories/skills/meta-factory/SKILL.md` — revision 0.1.43 |
| owns | ['the template instrument surface — methodology, development and cross-member deployment (owner-commissioned 2026-09-27)', 'the ASIF template and rulebook (TEMPLATE/ and the derived laws)', 'the fleet registry (registry/)', 'member-factory surveys, scores and the measurement cadence', 'the pacemaker and outer-trigger methodology (P28)', "this factory's own process law (skills/meta-factory/SKILL.md)"] |
| does not own | ["member factories' products, backlogs, repos and code", "member factories' ontologies and issue boards", 'the OpenCrabs runtime, daemon and core tools - a client-supplier loop, not ownership', 'token provisioning, model routing and inference pricing (InferHub Watch)', 'the tg_* tool surface (fast-mcp-telegram)'] |
| substrates owned | ['/root/agent-factories', '/root/agent-factories/skills/meta-factory/SKILL.md', '/root/agent-factories/registry/'] |
| attested at | 2026-10-02T06:20:45Z |

**Services**

| name | audience | entry | cadence |
|---|---|---|---|
| factory-measurement-daily | agent | cron factory-measurement-daily | daily 09:00 MSK (06:00Z) |
| factory-triage-patrol | agent | cron factory-triage-patrol | every 6h |
| factory-insights-weekly | agent | cron factory-insights-weekly | weekly, Fri 18:00 MSK (15:00Z); fires only when its trigger_cmd exits 0 |
| factory-template-weekly | agent | cron factory-template-weekly | weekly, Mon 09:00 MSK (06:00Z); fires only when its trigger_cmd exits 0 |
| factory-growth-map-biweekly | agent | cron factory-growth-map-biweekly | 1st and 15th, 09:00 MSK (06:00Z) |
| factory-registry-attest | agent | cron factory-registry-attest | daily 06:00Z |
| factory-publish | agent | cron factory-publish | every 6h (UTC) |

**Announcements reaching this factory**

- 🟡 **`pacemaker-triggers-still-pass-mode-quiet`** — Pacemaker cron triggers on this box still pass `--mode quiet` for three jobs, NONE of them meta-factory's: `ai-antispam-owner-digest` and `ai-antispam-triage-sweep` (ai-antispam, both ENABLED), and `oc-triage-owner-digest` (opencrabs-dev, now DISABLED — so only TWO of the three are live; the earlier "all three enabled" is superseded). The owner re-ruling of 2026-09-19T03:34:30Z / 03:36:54Z made turn-end THE default for all lane traffic and retained quiet only for batch/fan-out notices whose ack contract is the ledger; a single-lane pacemaker is not batch/fan-out, so each of these defers instead of waking an idle lane immediately. Meta-factory's jobs were moved to explicit `--mode turn-end` on 2026-09-23 (byte-verified; schedule and next_run_at preserved): of its SEVEN `factory-*` jobs, FIVE carry it (`factory-measurement-daily`, `factory-triage-patrol`, `factory-insights-weekly`, `factory-template-weekly`, `factory-growth-map-biweekly`) and TWO carry none (`factory-registry-attest`, `factory-publish`). Infra-factory's four now read plain `--mode turn-end` with no cap flags, so the pattern is demonstrated by a second factory rather than asserted. CAUTION FOR WHOEVER FIXES THE REMAINING TWO — the cap flag cannot be dropped alone: each carries `--mode quiet --quiet-for-secs 20 --max-delay-secs 30`, and its prompt documents WHY the cap is there, namely that quiet's DEFAULT starvation cap of 1800s blocks past the tool's 120s budget and kills the trigger. That hazard is quiet-specific and vanishes under turn-end, so the mode and the cap move TOGETHER and the sentence justifying the cap must be rewritten with them, or the prompt ends up arguing for a flag it no longer carries. Live census 2026-10-02T06:19Z: of 66 cron rows, 12 carry `--mode` — 9 turn-end, 3 quiet (one of the three disabled). Prior censuses kept as the steps this one follows, never overwritten: 2026-10-01T06:07Z of 65 rows, 12 — 9 turn-end / 3 quiet; 2026-09-29T08:26Z of 64, 12 — 9/3; 2026-09-28T11:35:19Z of 63, 12 — 9/3; 2026-09-26T06:20Z of 57, 12 — 9/3; 2026-09-23T11:31Z of 55, 13 — 10/3.
  - affects: profile · since: 2026-09-19T03:36:54Z · declared by: meta-factory
- 🔵 **`brain-metrics-baseline-measured`** — Brain metrics are a STANDING reading with an instrument: tools/brain_metrics.py (no args needed; --home / --hours / --log-dir / --window) prints all three legs with their predicate, population and instant, and gates none of them. The clause that binds it is docs/measurement-procedure.md section 5; its gate is tests/test_brain_metrics.py. A figure in this notice is a DATED READING and never current — run the instrument.

LEG C — CORRECTED 2026-10-01; the earlier wording is SUPERSEDED, not repeated. The earlier text claimed the automatic threshold trigger was DORMANT, having "fired 0 times since the 1M window". That is FALSE on this box today, measured two ways in one turn: (a) the trigger line itself — "Context at NN% (>65%) — triggering LLM compaction", emitted at src/brain/agent/service/compaction.rs:445/460 (the earlier text cited :418; the line moved) — fired 525 times across 20 distinct sessions in the 2026-10-01 log, this lane's session among them, and this lane was compacted mid-loop today; (b) the instrument's LEG C, which parses the DIFFERENT summarizer line at context.rs, read n=159 events in its 24h window — mean 73022 tok = 36.5% of a 200000-token window, median 79677, p90 114738, max 156319. The trigger line's denominator is NOT the provider window: it is effective tokens over effective max (the window minus reserves), so the earlier notice's equation "the 65-percent gate = 650000 tokens" conflates two denominators, which the instrument's own BOUNDS section 1 forbids. Never read a trigger-line percentage as a fraction of the provider window.

CONSEQUENCES the earlier text got backwards: (a) the note pipeline is NOT starved — save_compaction_summary_to_memory is the sole writer of memory/<date>.md, and with 159 summarizer sends in 24h a note exists for any day lanes are active, so memory_search's default scope is supplied rather than blind; (b) a count of compaction events tracks how many lanes were awake and how many turns they ran, never the weight of the law.

TWO CORRECTIONS worth keeping from the earlier text, both category errors: (a) the "110423 / 1000000 input tokens" line reports the SUMMARIZER'S PAYLOAD against its own input budget (context.rs), which is NOT the trigger's reading; (b) FullWindow is a CompactionScope (WHAT gets compacted), not a trigger KIND.

Fresh reading 2026-10-01T06:08:14Z: LEG A, the always-injected Tier 0 triple (SOUL.md, USER.md, AGENTS.md; in no repository, so a leg-A reading has an INSTANT for its identity and no revision) 186 lines / 33598 B / ~9599 tok (proxy) = 4.80% of a 200000-token window. LEG B, skills/*/SKILL.md (depth 1): 841 lines / 84589 B / ~24168 tok (proxy) = 12.08%. COMBINED = ~33767 tok (proxy) = 16.88% of a 200000-token window, against ~29897 tok = 14.95% at 2026-09-19 — a delta of +1.94 points. LEG C as above. The combined figure FELL 42.95% (2026-09-26) to 33.17% (2026-09-28) to 16.88% now, because the always-injected files shrank (AGENTS.md 458 lines / 144957 B to 186 lines / 33598 B); the floor is not monotonically rising.
  - affects: profile · since: 2026-09-28T12:19:23Z · declared by: meta-factory

**Lanes**

| topic | thread | role | session | session title | status | channel | last active | lane announcements |
|---|---|---|---|---|---|---|---|---|
| Surveys | 19 | surveys | `5c99ad51-8889-40cb-b589-fa13fd673c06` | Telegram: Factories / Surveys [chat:-1004497192134:topic:19] | resolved | telegram | 2026-09-29T07:29:49Z | — |
| Agent Factories Triage Lane | 20 | triage | `f4c192c9-a8e9-4268-9026-ee3e4970cc8a` | Agent Factories Triage Lane | resolved | telegram | 2026-10-01T00:26:51Z | — |
| Meta-Factory HQ: ASIF Architecture & Crons | 21 | hq | `2646d31a-71ee-49f0-be81-9c8dc32d32fa` | Meta-Factory HQ: ASIF Architecture & Crons | resolved | telegram | 2026-09-28T21:10:50Z | — |
| Delegate | 68 | delegate | `23549292-77ff-40d1-97e3-5aa0bdd19d74` | Telegram: Factories / Delegate [chat:-1004497192134:topic:68] | resolved | telegram | 2026-09-28T11:47:14Z | — |
| Worker | 1271 | worker | `dcd8f7a9-c1e7-48c3-b184-d901dc08eac7` | Telegram: Factories / Worker [chat:-1004497192134:topic:1271] | resolved | telegram | 2026-09-30T12:54:22Z | — |
| Factories / Ledger | 3981 | ledger | `d0cba805-92c9-4377-8808-a1cf715bce9e` | Telegram: Factories / Ledger [chat:-1004497192134:topic:3981] | resolved | telegram | 2026-09-29T08:30:32Z | — |
| Factories / Open Question Tool | 4087 | questions | `9f635151-4311-44ab-94f8-d4fd86e9b6c2` | Telegram: Factories / Open Question Tool [chat:-1004497192134:topic:4087] | resolved | telegram | 2026-10-02T21:31:34Z | — |
| Factories / Pacemakers / Crons | 4223 | pacemakers | `ee5cd2f5-6c1b-41bb-b031-1150a3132fb1` | Telegram: Factories / Pacemakers / Crons [chat:-1004497192134:topic:4223] | resolved | telegram | 2026-10-02T13:45:20Z | — |
| Factories / Instruments methodology | 4186 | methodology | `4515ea72-eb39-4a3c-9b05-a1dc02b1c977` | Telegram: Factories / Instruments methodology [chat:-1004497192134:topic:4186] | resolved | telegram | 2026-10-02T13:57:47Z | — |
| Factories / Fleet instruments | 4555 | fleet-instruments | `37e71e03-0022-4d38-9279-1687fec7a823` | Telegram: Factories / Fleet instruments [chat:-1004497192134:topic:4555] | resolved | telegram | 2026-09-27T22:00:11Z | — |
| Factories / Review Rotation | 5574 | review-rotation | `d6cfd3f7-0cd7-4e26-b9ff-2b1474be981e` | Telegram: Factories / Review Rotation [chat:-1004497192134:topic:5574] | resolved | telegram | 2026-09-30T14:42:13Z | — |
| Factories / Insights | 6865 | insights | `95b14002-4541-45a5-b2a6-4294ee1104f8` | Meta-factory insights register — class + status axes | resolved | telegram | 2026-10-02T21:32:09Z | — |
| Factories / Hygiene | 8733 | hygiene | `a2c8637c-0a24-4bbc-8097-7cff600b67e2` | Telegram: Factories / Hygiene [chat:-1004497192134:topic:8733] | resolved | telegram | 2026-10-02T13:46:01Z | — |

**Pacemakers**

| job | home | cron_expr | timezone | enabled | set_goal | goal_template | next_run_at | deliver_to | trigger_cmd |
|---|---|---|---|---|---|---|---|---|---|
| `factory-growth-map-biweekly` | ops | `0 9 1,15 * *` | Europe/Moscow | yes | 0 | **absent** | 2026-10-15T06:00:00+00:00 | — | — |
| `factory-insights-weekly` | ops | `0 18 * * Fri` | Europe/Moscow | yes | 0 | **absent** | 2026-10-09T15:00:00+00:00 | — | python3 /root/agent-factories/tools/synthesize_insights.py --audit |
| `factory-measurement-daily` | ops | `0 9 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-10-04T06:00:00+00:00 | — | — |
| `factory-publish` | ops | `0 */6 * * *` | UTC | yes | 0 | **absent** | 2026-10-03T12:00:00+00:00 | — | — |
| `factory-questions-redeliver` | ops | `12 */6 * * *` | UTC | yes | 0 | **absent** | 2026-10-03T12:12:00+00:00 | session:2646d31a-71ee-49f0-be81-9c8dc32d32fa | /root/.opencrabs/profiles/ops/scripts/oc_questions_redeliver.sh |
| `factory-registry-attest` | ops | `0 6 * * *` | UTC | yes | 0 | **absent** | 2026-10-04T06:00:00+00:00 | — | — |
| `factory-template-weekly` | ops | `0 9 * * Mon` | Europe/Moscow | yes | 0 | **absent** | 2026-10-05T06:00:00+00:00 | — | python3 /root/agent-factories/tools/roadmap.py --cadence |
| `factory-triage-patrol` | ops | `0 */6 * * *` | UTC | yes | 0 | **absent** | 2026-10-03T12:00:00+00:00 | — | out=$(gh issue list -R leshchenko1979/agent-factories --state open --li… |

Attribution basis: deliver_to -> lane, name prefix.
`trigger_cmd` is truncated to 72 characters here; the full command is in `registry/index.json`.
7 of 8 job(s) carry no explicit `deliver_to`. The column is rendered as the live row holds it; whether a null falls back to the creating session or to nothing is the scheduler's contract, and this registry does not assert it.

### miidas — Miidas Factory

| Field | Value |
|---|---|
| freshness | ✅ attested 2026-10-02T06:20:23Z |
| purpose | MIIDAS is an ecosystem of applied business AI for Russian SMB owners — dedicated Telegram AI executive assistants provisioned as per-client managed agent containers, plus the platform that mints, binds and bills them. |
| profile | `ops` |
| repo | `/root/miidas` |
| law | `/root/miidas/SKILL.md` — revision 1.1.30 |
| owns | ['/root/miidas platform repo (agent, landing, manager, cdp components) and its deploys to agents-old (89.125.120.5:52676); the apps copy is retained as the rollback', 'leshchenko1979/miidas and leshchenko1979/miidas-template', 'per-client slot state: pool/slots/miidas-*.env on agents-old — platform root /data/projects/miidas/, so the live path is /data/projects/miidas/pool/slots/ — plus the miidas-* container and miidas_* volume namespaces, which span BOTH hosts during the rollback window', 'the Miidas Factory Telegram chat (-1003996392908) and its topics', '/root/miidas/SKILL.md — the live skill path is a symlink to it, so the repo file is the single writer', 'cron miidas-hq-daily-trigger', 'the miidas LLM-gateway service user and manager/llm_keys.py key lifecycle', 'leshchenko1979/miidas-landing — the public landing, recipe hub and course surface (miidas.ru) at /root/miidas-landing'] |
| does not own | ['client product surfaces — the per-client groups, the onboarding funnel, the client-facing forum. Those are the product, never the factory surface', "the LLM gateway itself (llm.l1979.ru) — consumed, not operated; we own only our service user's key lifecycle", "the agents-old and apps hosts beyond our own compose stack — other projects' containers and volumes, host packages, other factories' cron rows", "other factories' repos, chats and processes", 'OpenCrabs core and the dev process'] |
| substrates owned | ['leshchenko1979/miidas', 'leshchenko1979/miidas-template', 'leshchenko1979/miidas-landing', '/root/miidas/SKILL.md (live skill path is a symlink to it)', 'agents-old and apps: /data/projects/miidas/ (compose/, pool/slots/miidas-*.env, .master.env) and the miidas-* compose stack; agents-old carries the live set, apps the stopped rollback'] |
| attested at | 2026-10-02T06:20:23Z |

**Services**

| name | audience | entry | cadence |
|---|---|---|---|
| miidas-manager | agent | ./manager/deploy.sh | always-on; slot projection into Postgres every 60s |
| miidas-cdp | agent | ./cdp/deploy.sh | always-on (shared headless Chrome) |
| miidas-ru-proxy | agent | docker compose, miidas-pool network port 8888 | always-on (WireGuard egress for RU portals) |
| miidas-<slug> | owner | ./agent/deploy.sh then restart.sh --slug <slug> | always-on, one per bound slot |
| miidas landing | owner | ./landing/deploy.sh | request-driven (nginx on miidas.l1979.ru) |
| miidas-hq-daily-trigger | owner | cron 0 9 * * * | daily 09:00 UTC |

**Announcements reaching this factory**

- 🟡 **`miidas-volume-namespace-on-apps`** — The miidas_* Docker volume namespace and the miidas-* container namespace belong to the MIIDAS factory. A peer reclaiming or pruning must match ^miidas_ and never a bare substring: miidas-pixel-data belongs to another project and is not ours. The estate spans two hosts: agents-old holds 5 RUNNING containers and 1 volume matching ^miidas_ (miidas_maple-c23a-data); apps holds 5 STOPPED containers and 1 such volume. Read 2026-10-01T06:27Z.
  - affects: profile · since: 2026-09-13T09:56:00Z · declared by: miidas
- 🔵 **`llm-gateway-per-service-user`** — The LLM gateway (llm.l1979.ru) carries a dedicated NON-root service user per consumer rather than one shared fleet credential: miidas (id 5, role 1, management credential NEWAPI_MIIDAS_TOKEN, quota 500000000000 units), alongside peer service users avito-bot and opencrabs-fleet. A factory provisioning LLM keys for its own clients should ask the gateway owner for its own service user rather than reuse the fleet root credential.
  - affects: profile · since: 2026-09-18T01:53:06Z · declared by: miidas
- 🔵 **`miidas-hq-daily-trigger-is-ours`** — cron miidas-hq-daily-trigger (0 9 * * *, enabled, delivers to session e4f96a33-45ac-412e-8788-1b678cf2addb, the HQ topic) is the MIIDAS factory's own pacemaker. Peers must not disable, repace or repoint it.
  - affects: profile · since: 2026-09-11T00:00:00Z · declared by: miidas
- 🟡 **`miidas-platform-compose-is-repo-written`** — The miidas platform compose on agents-old (/data/projects/miidas/compose/docker-compose.yml) is written from our repo: manager/deploy.sh:33, landing/deploy.sh:27 and deploy-all.sh:36 each scp the repo copy over the live one, so a host-side edit there is silently reverted by the next of those deploys. That directory deliberately carries no .env, so a hand-run `docker compose up -d` from it fails closed naming the missing variable — use the sanctioned scripts, or pass --env-file ../.master.env. The sync helper is deploy_lib.sh:157-159 and the sanctioned path is miidas_compose() at deploy_lib.sh:163.
  - affects: profile · since: 2026-09-26 · declared by: miidas
- 🔵 **`miidas-kit-forks-declared`** — miidas vendors the fleet kit pin (registry/kit.json, version 6ab591c618ec, 128 paths declared) and declares 19 divergences from it in registry/kit-exemptions.json. Its gate 23 (tests/test_kit_pin_member.py — a SCRIPT, run `python3 tests/test_kit_pin_member.py`; it is not a pytest module and pytest collects nothing from it) reds on any UNDECLARED divergence and passes clean today: 27 carried paths judged, 1 factory-class path excluded by class, 19 forks declared, 0 undeclared. A peer porting a kit instrument into this factory must add the exemption entry in the same change, or the factory audit goes red — that refusal is deliberate, not drift.
  - affects: profile · since: 2026-09-27T05:24:07Z · declared by: miidas
  - evidence: Measured 2026-09-27T11:44Z by the registry writer: tests/test_kit_pin_member.py rc=0, 'judged 24 carried path(s); 1 factory-class path(s) excluded by class; 17 declared exempt'; pin version 6ab591c618ec, 128 paths declared. The gate path is named in the text because the loader's `check` field names an ALLOWLISTED predicate and is never executed - a path there is refused.
- 🟡 **`miidas-slot-volume-git-config-carries-remote-credential`** — Every miidas client slot volume's .git/config (mode 644) carries the template remote with an INLINE ACCOUNT-LEVEL token, and this is now ACCEPTED AS DATED by the owner (2026-09-28T09:18:36Z) — leshchenko1979/miidas#61 is closed by decision, not by fix, so no rotation is coming. The operational rule therefore stands permanently rather than pending: a peer reclaiming, copying, backing up or decommissioning a miidas slot volume must treat the VOLUME as secret-bearing — it outlives the container, the credential is readable by the client's own agent and not only by a host operator, and the agent image layer carries it too.
  - affects: profile · since: 2026-09-27T11:39:51Z · declared by: miidas
- 🟡 **`miidas-platform-moved-to-agents-old`** — The MIIDAS platform runs on agents-old (89.125.120.5:52676), not apps; apps holds the stopped rollbacks (5 containers, Exited). Do not start the stopped apps containers. The claim forward is miidas-claim-forward.service ON apps (active + enabled), tunnelling 172.18.0.1:8765 to agents-old. The APP_HOST footgun this notice originally warned about is CLOSED: deploy_lib.sh no longer defaults to apps — it applies an environment override first and defaults to agents-old only when unset (deploy_lib.sh:21-34, :36), .master.env:34 reads agents-old, and leshchenko1979/miidas#82 is MERGED (2026-09-29T08:39:31Z), not a draft. A repo deploy with no override now lands on agents-old.
  - affects: profile · since: 2026-09-28T23:23:39Z · declared by: miidas

**Lanes**

| topic | thread | role | session | session title | status | channel | last active | lane announcements |
|---|---|---|---|---|---|---|---|---|
| HQ | 4 | hq | `e4f96a33-45ac-412e-8788-1b678cf2addb` | Telegram: Miidas Factory / HQ [chat:-1003996392908:topic:4] | resolved | telegram | 2026-10-02T08:55:26Z | — |
| Agent runtime | 6 | _unstated_ | `5a5335ee-db68-46fe-b13e-a082b2beadb5` | Telegram: Miidas Factory / Agent runtime [chat:-1003996392908:topic:6] | resolved | telegram | 2026-10-03T03:35:43Z | — |
| Manager | 9 | _unstated_ | `b64ca6ba-9ec0-47f7-8450-0d25b6c1d854` | Telegram: Miidas Factory / Manager [chat:-1003996392908:topic:9] | resolved | telegram | 2026-09-25T16:25:13Z | — |
| Worker | 56 | worker | `b57efabd-85df-4467-bed7-f5a596285f68` | Telegram: Miidas Factory / Worker — #39 board vs ledger comparison gate [chat:-1003996392908:topic:56] | resolved | telegram | 2026-09-29T07:19:56Z | — |
| Marketing | 393 | marketing | `39d2b612-dbfc-4953-ae02-609267c68c3e` | Telegram: Miidas Factory / Marketing [chat:-1003996392908:topic:393] | resolved | telegram | 2026-09-29T09:03:05Z | — |

**Pacemakers**

| job | home | cron_expr | timezone | enabled | set_goal | goal_template | next_run_at | deliver_to | trigger_cmd |
|---|---|---|---|---|---|---|---|---|---|
| `miidas-hq-daily-trigger` | ops | `0 9 * * *` | UTC | yes | 0 | **absent** | 2026-10-03T09:00:00+00:00 | session:e4f96a33-45ac-412e-8788-1b678cf2addb | — |

Attribution basis: deliver_to -> lane.

### opencrabs-dev — Opencrabs Dev Factory

| Field | Value |
|---|---|
| freshness | ✅ attested 2026-10-02T06:48:51Z |
| purpose | Build and ship the OpenCrabs daemon that every lane on this box runs on, and author the process law those lanes follow: a gated source-to-swap pipeline, a versioned skill set, and a workers-ledger that records who holds what. |
| profile | `ops` |
| repo | `/root/opencrabs` |
| law | `/root/.opencrabs/profiles/ops/skills/opencrabs-dev/SKILL.md` — revision 0.4.283 |
| owns | ['the OpenCrabs source fork leshchenko1979/opencrabs and its carrier build and swap pipeline', "the opencrabs-dev skill set: SKILL.md, the five role files (editor, hq, triage, toolsmith, harvest), fleet-directives.md and the runbooks -- NARROWED BY FIVE OWNER-APPROVED CARVE-OUTS: the Toolsmith lane owns tools/ CODE; the Triage lane owns AFFINITY_KEYWORDS and lane repurposing; Duty-4/6 finding remediation ships without the design gate; harvesting needs no design gate; and per-instrument law files under /root/agent-factories/docs/instruments/ are authored by each instrument's own owner, with the superseded fleet-directives.md copy reduced to a [LANE] pointer", 'the workers-ledger and skill-version consensus', 'the CLI tool fleet under tools/, authored by the Toolsmith lane inside this factory', 'the fork issue board on leshchenko1979/opencrabs'] |
| does not own | ['the fast-mcp-telegram substrate and its tg_* tool family', 'the meta-factory registry, its surveys and its scoring surface', 'the live daemon configuration on this box: config.toml, keys.toml and the running units', "member factories' own process law, repos and backlogs", 'upstream adolfousier/opencrabs, which receives PRs only and never issues'] |
| substrates owned | ['the OpenCrabs source fork and its carrier build pipeline', 'the opencrabs-dev skill set and the workers-ledger'] |
| attested at | 2026-10-02T06:48:51Z |

**Services**

| name | audience | entry | cadence |
|---|---|---|---|
| Build and swap a new daemon binary | agent | the Editor lane's oc-deploy ship --sha <full-sha> --execute | on request |
| Process-law amendment | agent | session_notify to the HQ lane | on request |
| CLI tool defect intake and fix | agent | session_notify to the Toolsmith lane | on request |
| Version release and ledger consensus | agent | oc-ledger sync --version <v> | per skill version bump |
| Fork issue intake and triage | agent | the Triage lane on leshchenko1979/opencrabs | on request |
| Owner decision surfacing (Open Questions register) | agent | oc_questions ask --factory <KEY> (dynamic tool; the asking session comes from OPENCRABS_SESSION_ID and must NOT be passed by the caller) | on request |

**Announcements reaching this factory**

- 🟡 **`notify-now-mode-retired`** — session_notify's 'now' mode is RETIRED and passing it FAILS the delivery outright - it is not merely discouraged. 'turn-end' is the default and wakes an idle target immediately, so it loses nothing 'now' ever delivered; 'quiet' is retained for batch notices whose ack contract is the ledger. 'interrupt' is the URGENT tier (#393): it delivers at the SAME boundary as turn-end and adds precedence framing so the target yields its current plan and answers in that turn - never deferred, never a default, spell it explicitly. It is NOT pre-emption: no boundary exists inside a running tool call, so a mid-turn target still queues for its next tool-loop boundary. Legacy interrupt:true UPGRADES a non-quiet resolution to that tier. A 'no wake observed' confirm verdict means the target is mid-turn; never re-send on it.
  - affects: profile · since: 2026-09-19 · review by: 2026-12-19 · declared by: opencrabs-dev

**Lanes**

| topic | thread | role | session | session title | status | channel | last active | lane announcements |
|---|---|---|---|---|---|---|---|---|
| Core: Brain Tools | 7198 | _unstated_ | `329bf3a3-6299-4173-b991-7ea0427563e3` | bash guard forced-variation design | resolved | telegram | 2026-09-29T06:58:46Z | — |
| Telegram: Mermaid | 29947 | _unstated_ | `c6b1a539-6225-40ea-a514-67d21a446cd5` | Telegram: Opencrabs Dev Factory / Mermaid [chat:-1003936827469:topic:29947] | resolved | telegram | 2026-09-30T12:23:47Z | — |
| Providers: Routing | 30045 | _unstated_ | `127429e6-08de-439c-9162-2c8b0a9f73d9` | Gemini Reasoning and Flow Message Analysis | resolved | telegram | 2026-09-29T06:47:55Z | — |
| Telegram: Push | 30090 | editor | `d18ce16a-75a0-447c-90c7-ab7dabce4411` | Editor lane: #17/#19 channel-ownership PRs | resolved | telegram | 2026-09-24T11:58:12Z | — |
| Telegram: Options | 30134 | _unstated_ | `1a63f103-b899-4ad2-a5b3-c89f2902bf97` | Deploy #235 Option Collision Guard | resolved | telegram | 2026-09-28T08:13:31Z | — |
| OC DEV HQ | 30220 | hq | `0117dd29-5f4b-4184-9bf4-d19dc74ac266` | Telegram: Opencrabs Dev Factory / OC DEV HQ [chat:-1003936827469:topic:30220] | resolved | telegram | 2026-10-02T21:16:30Z | — |
| Core: Subagents | 30517 | _unstated_ | `a5b34466-1c14-441f-b2c6-6eaf4f316dde` | Telegram: Opencrabs Dev Factory / Subagents [chat:-1003936827469:topic:30517] | resolved | telegram | 2026-09-29T09:25:18Z | — |
| Telegram: Throttling | 30679 | _unstated_ | `61161247-5b1d-4efe-979b-bf46ffc85c48` | Telegram: Opencrabs Dev Factory / Flood Throttling [chat:-1003936827469:topic:30679] | resolved | telegram | 2026-10-02T21:36:13Z | — |
| Lifecycle: Restarts | 31683 | _unstated_ | `7e1ebbb6-68b3-478b-abc2-b697e70c2f37` | Telegram: Opencrabs Dev Factory / Graceful restart [chat:-1003936827469:topic:31683] | resolved | telegram | 2026-09-29T06:44:05Z | — |
| Core: Plan & Tasks | 31789 | _unstated_ | `462181e9-ad99-4163-bd3d-c983c48049a8` | Telegram: Opencrabs Dev Factory / Core: Plan & Tasks [chat:-1003936827469:topic:31789] | resolved | telegram | 2026-09-28T14:56:57Z | — |
| Telegram: Rich Text | 31847 | _unstated_ | `2fbfb2f8-9b08-417a-aae8-c75edc1de1ea` | Issue #234: Review Implementation Button | resolved | telegram | 2026-09-28T17:42:56Z | — |
| Memory: Compaction | 34653 | _unstated_ | `cbdfde4a-b3fe-457a-817b-5113b938f12d` | Telegram: Opencrabs Dev Factory / Compaction visibility [chat:-1003936827469:topic:34653] | resolved | telegram | 2026-09-27T14:33:47Z | — |
| Memory: Vectors | 36841 | _unstated_ | `212b3c83-6659-49c8-9984-0cf849f769c1` | Telegram: Opencrabs Dev Factory / Vector memory [chat:-1003936827469:topic:36841] | resolved | telegram | 2026-09-28T19:33:58Z | — |
| OC DEV TOOLSMITH | 39171 | toolsmith | `2fae1230-de9e-4fa5-aa24-822cf7188c3e` | Toolsmith Issue 255 and PR Dependency Laws | resolved | telegram | 2026-10-02T11:35:27Z | — |
| Upstream: Harvest | 39218 | _unstated_ | `4b0990b7-aff8-4744-8de5-e38e54de7693` | Harvesting upstream PRs into OpenCrabs | resolved | telegram | 2026-10-02T05:57:13Z | — |
| Lifecycle: Boot | 39862 | _unstated_ | `c10cd97b-2c99-49fa-a1c4-d78a02dfd7d1` | Telegram: Opencrabs Dev Factory / Rich resume wire [chat:-1003936827469:topic:39862] | resolved | telegram | 2026-10-01T12:53:47Z | — |
| Core: Loop | 39883 | _unstated_ | `40427d4f-af4a-48ba-993f-f5f0b21916c0` | Telegram: Opencrabs Dev Factory / Loop guard [chat:-1003936827469:topic:39883] | resolved | telegram | 2026-09-27T14:32:52Z | — |
| Config: Schema | 40011 | _unstated_ | `c2ba4ef2-eac3-406c-98d6-c861c5bebec2` | Telegram: Opencrabs Dev Factory / Config: Schema [chat:-1003936827469:topic:40011] | resolved | telegram | 2026-10-01T07:41:53Z | — |
| Config: Typings | 40479 | _unstated_ | `aff7ff41-a3a7-4c53-adc5-80fb7a33ba50` | Telegram: Opencrabs Dev Factory / #87 config-write-types [chat:-1003936827469:topic:40479] | resolved | telegram | 2026-09-27T14:27:27Z | — |
| Memory: Search | 40524 | _unstated_ | `42a44908-b8f3-42e1-bbd2-f2a672b8056e` | #465 Telegram outbound video path | resolved | telegram | 2026-10-01T16:30:59Z | — |
| Browser: CDP | 40695 | _unstated_ | `aaa8d8ae-a4be-4b89-9f92-01a317075be3` | Telegram: Opencrabs Dev Factory / Harvest rich-host buttons [chat:-1003936827469:topic:40695] | resolved | telegram | 2026-09-27T14:37:22Z | — |
| Security: Policies | 40696 | _unstated_ | `afe476f8-279b-4d54-b628-c9d7e35873c8` | Telegram: Opencrabs Dev Factory / Harvest retry-429 ladder [chat:-1003936827469:topic:40696] | resolved | telegram | 2026-09-25T16:19:27Z | — |
| Core: Goal Loop | 42311 | _unstated_ | `9fa7c71a-f009-418a-ac06-d0336efcf491` | Telegram: Opencrabs Dev Factory / Core: Goal Loop [chat:-1003936827469:topic:42311] | resolved | telegram | 2026-09-27T10:21:20Z | — |
| Governance: Roles | 42360 | _unstated_ | `63d775f9-18e2-4097-8696-d9a2ca796f14` | Telegram: Opencrabs Dev Factory / Role split [chat:-1003936827469:topic:42360] | resolved | telegram | 2026-09-30T22:41:33Z | — |
| Triage | 42487 | triage | `530c29ec-596e-43a4-9c7e-1b6dfc3cd870` | Triage: Issue Portfolio & Harvest Analysis | resolved | telegram | 2026-09-30T23:53:15Z | — |
| Process: Waits | 42744 | _unstated_ | `facd50af-0807-4fee-942b-008bff037f6f` | Telegram: Opencrabs Dev Factory / oc-waiter + #111 durable-notify [chat:-1003936827469:topic:42744] | resolved | telegram | 2026-10-02T21:21:45Z | — |
| Telegram: Host Guards | 42940 | _unstated_ | `c78e78e0-099e-455e-8dfb-7e9b8f7d13e5` | Telegram: Opencrabs Dev Factory / #92 demoted-host guard [chat:-1003936827469:topic:42940] | resolved | telegram | 2026-09-27T10:14:30Z | — |
| Governance: Audits | 43440 | _unstated_ | `30ab6f43-3326-4aad-abe3-eb4a5a98f630` | Telegram: Crabs Kanban Board [chat:-1003936827469:topic:43440] | resolved | telegram | 2026-09-07T05:45:18Z | — |
| Telegram: Bot API | 43727 | _unstated_ | `95bec69b-0e96-46a9-9d91-dc355e8af18f` | Telegram flow card metrics telemetry bar #232 | resolved | telegram | 2026-09-29T07:58:48Z | — |
| Governance: Ontology | 43993 | _unstated_ | `6630dc9a-0eeb-46c2-95b8-bfae43e0766b` | Telegram: Opencrabs Dev Factory / Governance: Ontology & RSI [chat:-1003936827469:topic:43993] | resolved | telegram | 2026-09-28T08:07:23Z | — |
| Core: Multi-Tool | 44326 | _unstated_ | `a38499fc-76a4-4aff-8953-fa5931ad0e5c` | Telegram: Opencrabs Dev Factory / Multicalls [chat:-1003936827469:topic:44326] | resolved | telegram | 2026-09-28T08:20:54Z | — |
| Core: Crons | 49607 | _unstated_ | `6cd8175f-fb27-4cf3-a390-971ff2519a47` | Fix #149: Cron Session Isolation | resolved | telegram | 2026-09-28T18:51:49Z | — |
| Core: Skills | 49643 | _unstated_ | `4b4463d5-381c-4458-aa0c-3cf199882084` | Telegram: Opencrabs Dev Factory / Core: Skills [chat:-1003936827469:topic:49643] | resolved | telegram | 2026-09-27T15:29:17Z | — |
| Core: Prompts | 50566 | _unstated_ | `52058a75-e94b-4400-9e07-aac3a891bb1f` | Deploy issue 248 default group command scopes | resolved | telegram | 2026-09-27T14:25:47Z | — |
| Telegram: Flow | 51188 | _unstated_ | `2ed8adeb-4784-4159-b68f-0e552490641e` | FlowLine::System split — #291 header fix | resolved | telegram | 2026-09-29T06:49:48Z | — |
| JEV Classifier | 68049 | _unstated_ | `ef83024b-90c8-40fc-8490-e8c2879808ab` | Telegram: Opencrabs Dev Factory / JEV Classifier [chat:-1003936827469:topic:68049] | resolved | telegram | 2026-09-25T12:46:54Z | — |

**Pacemakers**

| job | home | cron_expr | timezone | enabled | set_goal | goal_template | next_run_at | deliver_to | trigger_cmd |
|---|---|---|---|---|---|---|---|---|---|
| `538-probe-boundary-delivery` | ops | `0 3 1 1 *` | UTC | **no** | 0 | **absent** | 2027-01-01T03:00:00+00:00 | telegram:-1003936827469:49607 | cat /tmp/538-payload.txt |
| `oc-629-fallback-watch` | ops | `20 */6 * * *` | UTC | yes | 0 | **absent** | 2026-10-03T06:20:00+00:00 | session:9fa7c71a-f009-418a-ac06-d0336efcf491 | p=$(printf "%s.*%s%s" "rich::api" "falling back to " "html dialect"); f… |
| `oc-harvest-18-resume` | ops | `0 7 * * *` | UTC | **no** | 0 | **absent** | 2026-09-25T07:00:00+00:00 | session:7e1ebbb6-68b3-478b-abc2-b697e70c2f37 | — |
| `oc-harvest-225-resume` | ops | `0 8 * * *` | UTC | **no** | 0 | **absent** | 2026-09-25T08:00:00+00:00 | session:a5b34466-1c14-441f-b2c6-6eaf4f316dde | — |
| `oc-harvest-250-resume` | ops | `15 15 * * *` | UTC | **no** | 0 | **absent** | 2026-09-25T15:15:00+00:00 | session:63d775f9-18e2-4097-8696-d9a2ca796f14 | echo HARVEST-PENDING-250 |
| `oc-harvest-318-resume` | ops | `20 15 * * *` | UTC | **no** | 0 | **absent** | 2026-09-25T15:20:00+00:00 | session:212b3c83-6659-49c8-9984-0cf849f769c1 | echo HARVEST-PENDING-318 |
| `oc-harvest-321-resume` | ops | `15 15 * * *` | UTC | **no** | 0 | **absent** | 2026-09-25T15:15:00+00:00 | session:cbdfde4a-b3fe-457a-817b-5113b938f12d | echo HARVEST-PENDING-321 |
| `oc-harvest-326-resume` | ops | `30 14 * * *` | UTC | **no** | 0 | **absent** | 2026-09-25T14:30:00+00:00 | session:aaa8d8ae-a4be-4b89-9f92-01a317075be3 | — |
| `oc-harvest-341-resume` | ops | `45 15 * * *` | UTC | **no** | 0 | **absent** | 2026-09-25T15:45:00+00:00 | session:facd50af-0807-4fee-942b-008bff037f6f | — |
| `oc-harvest-344-resume` | ops | `45 15 * * *` | UTC | **no** | 0 | **absent** | 2026-09-25T15:45:00+00:00 | session:127429e6-08de-439c-9162-2c8b0a9f73d9 | — |
| `oc-harvest-345-resume` | ops | `50 15 * * *` | UTC | **no** | 0 | **absent** | 2026-09-25T15:50:00+00:00 | session:6630dc9a-0eeb-46c2-95b8-bfae43e0766b | — |
| `oc-harvest-346-resume` | ops | `35 15 * * *` | UTC | **no** | 0 | **absent** | 2026-09-25T15:35:00+00:00 | session:aff7ff41-a3a7-4c53-adc5-80fb7a33ba50 | echo HARVEST-PENDING-346 |
| `oc-harvest-348-resume` | ops | `40 15 * * *` | UTC | **no** | 0 | **absent** | 2026-09-25T15:40:00+00:00 | session:c78e78e0-099e-455e-8dfb-7e9b8f7d13e5 | echo HARVEST-PENDING-348 |
| `oc-harvest-364-resume` | ops | `30 15 * * *` | UTC | **no** | 0 | **absent** | 2026-09-25T15:30:00+00:00 | session:9fa7c71a-f009-418a-ac06-d0336efcf491 | echo HARVEST-PENDING-364 |
| `oc-harvest-396-resume` | ops | `15 9 20 9 *` | UTC | **no** | 0 | **absent** | 2027-09-20T09:15:00+00:00 | session:1a63f103-b899-4ad2-a5b3-c89f2902bf97 | — |
| `oc-harvest-402-resume` | ops | `0 18 * * *` | UTC | **no** | 0 | **absent** | 2026-09-25T18:00:00+00:00 | session:52058a75-e94b-4400-9e07-aac3a891bb1f | L=/root/.opencrabs/profiles/ops/skills/opencrabs-dev/tools/oc-ledger; o… |
| `oc-harvest-403-resume` | ops | `45 15 * * *` | UTC | **no** | 0 | **absent** | 2026-09-26T15:45:00+00:00 | session:afe476f8-279b-4d54-b628-c9d7e35873c8 | D=/root/.opencrabs/profiles/ops/skills/opencrabs-dev/tools; L="$D/state… |
| `oc-harvest-421-resume` | ops | `25 15 * * *` | UTC | **no** | 0 | **absent** | 2026-09-25T15:25:00+00:00 | session:212b3c83-6659-49c8-9984-0cf849f769c1 | echo HARVEST-PENDING-421 |
| `oc-harvest-dispatch-4h` | ops | `15 3,9,15,21 * * *` | UTC | **no** | 1 | present | 2026-09-19T03:15:00+00:00 | session:530c29ec-596e-43a4-9c7e-1b6dfc3cd870 | — |
| `oc-health-hourly` | ops | `0 */6 * * *` | UTC | **no** | 0 | **absent** | 2026-09-19T00:00:00+00:00 | — | — |
| `oc-roster-detached-sweep` | ops | `5 */6 * * *` | UTC | **no** | 0 | **absent** | 2026-09-19T00:05:00+00:00 | — | ROSTER=/root/.opencrabs/profiles/ops/skills/opencrabs-dev/tools/oc-rost… |
| `oc-triage-factory-patrol` | ops | `0 */6 * * *` | UTC | **no** | 1 | present | 2026-09-29T12:00:00+00:00 | session:530c29ec-596e-43a4-9c7e-1b6dfc3cd870 | — |
| `oc-triage-owner-digest` | ops | `30 9 * * *` | Europe/Moscow | **no** | 0 | **absent** | 2026-09-30T06:30:00+00:00 | — | — |
| `oc-upstream-delta-watch` | ops | `15 */6 * * *` | UTC | **no** | 1 | present | 2026-09-19T00:15:00+00:00 | session:530c29ec-596e-43a4-9c7e-1b6dfc3cd870 | /root/.opencrabs/profiles/ops/skills/opencrabs-dev/tools/oc-upstream-de… |

Attribution basis: deliver_to -> chat, deliver_to -> lane, name prefix.
`trigger_cmd` is truncated to 72 characters here; the full command is in `registry/index.json`.
3 of 24 job(s) carry no explicit `deliver_to`. The column is rendered as the live row holds it; whether a null falls back to the creating session or to nothing is the scheduler's contract, and this registry does not assert it.

## Unattributed jobs

Read from the declared profile homes: 3 home(s) opened, 68 job row(s). Homes read: family, oc348probe, ops.

These rows name no known factory in their `deliver_to` and match no naming prefix. They are rendered rather than dropped: a job the registry cannot place is a finding, not an omission. Each row carries the profile home it was read from, so a row that should not be here can be found and changed without guessing which home owns it.

| job | home | cron_expr | timezone | enabled | set_goal | goal_template | next_run_at | deliver_to | trigger_cmd |
|---|---|---|---|---|---|---|---|---|---|
| `reminder-answer-adolfo` | family | `0 10 1 10 *` | Europe/Moscow | **no** | 0 | **absent** | 2027-10-01T07:00:00+00:00 | telegram:133526395 | — |
| `tamara_accounting_sync` | family | `0 21 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-10-03T18:00:00+00:00 | telegram:-1004286036984 | python3 /root/.opencrabs/profiles/family/projects/tamara-raschety/cron_… |
| `oc626-resolve-probe` | ops | `0 4 1 1 *` | UTC | **no** | 0 | **absent** | 2027-01-01T04:00:00+00:00 | — | true |
| `tmp-nulltrigger-probe` | ops | `4 */6 * * *` | UTC | **no** | 0 | **absent** | 2026-09-19T00:04:00+00:00 | — | — |
| `tmp-trigger-control-neg` | ops | `0 0 1 1 *` | UTC | **no** | 0 | **absent** | 2027-01-01T00:00:00+00:00 | — | printf 'BEHIND\t0\n' |
| `tmp-trigger-control-pos` | ops | `0 0 1 1 *` | UTC | **no** | 0 | **absent** | 2027-01-01T00:00:00+00:00 | — | printf 'BEHIND\t3\n' |

---

Generated file. Edit `registry/factories/<slug>.json` instead, then re-render.
