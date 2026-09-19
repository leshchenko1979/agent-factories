# Fleet Factory Registry

**Generated** by `tools/registry.py render` — never hand-edited; the drift gate re-renders and compares the state-bearing bytes.

**resolved at** `2026-09-19T15:03:39Z` — every binding, lane and job row below was read at that instant. The declared half ages on its own clock: a moved binding is a state change (re-rendering fixes it), while an old attestation is a process failure (re-rendering fixes nothing).

## Freshness

| Half | Source | State |
|---|---|---|
| declared | 6 fragment(s) | 0 attested, 6 awaiting an answer |
| generated | live reads | resolved `2026-09-19T15:03:39Z` |

## Announcements

Deduplicated by `id` across every fragment: several lanes noticing one fact is one statement with several declarers. An entry naming a `check` is mechanically verified; the rest rest on `review_by` alone.

_None declared. Every field is a question until an HQ answers it._

## Reachability

| Hop | Mechanism | State |
|---|---|---|
| lane -> lane, same factory | `session_notify` (UUID) | works |
| factory -> factory, same profile | `session_notify` (UUID) | works |
| factory -> factory, other profile | `opencrabs -p <profile> session notify <uuid>` | works — the CLI posts over that profile's own A2A gateway, so it crosses a process boundary the in-session tool cannot |
| owner -> factory | Telegram topic | works — human surface only; agents do not read topics |

CLI exit contract: `0` delivered/redirected/parked · `2` unknown or dead uuid · `3` refused mid-turn · `4` transport (A2A disabled or unreachable). The CLI's `--mode` default is `now`, which **fails** delivery under the fleet's delivery-discipline law — pass `turn-end` explicitly.

## Factories

### ai-antispam — ai-antispam

| Field | Value |
|---|---|
| freshness | ⛔ INCOMPLETE — no declared half yet |
| purpose | — |
| profile | `ops` |
| repo | `/root/ai-antispam` |
| law | `/root/ai-antispam/SKILL.md` — revision 0.1.0 |
| owns | — |
| does not own | — |
| substrates owned | — |
| attested at | — |

**Services**

_None declared._

**Lanes**

| topic | thread | role | session | session title | status | channel | last active | lane announcements |
|---|---|---|---|---|---|---|---|---|
| Outreach | 10780 | outreach | `acc3fa9b-cefa-4e35-bf87-422696e558f0` | Telegram: ai-antispam / Outreach [chat:-1003993000918:topic:10780] | ambiguous | telegram | 2026-09-18T18:37:02Z | — |
| Triage | 10781 | triage | `6ca0d547-4a72-4c29-ac10-967daa98af0a` | Telegram: ai-antispam / Triage [chat:-1003993000918:topic:10781] | resolved | telegram | 2026-09-12T12:13:52Z | — |
| HQ | 10782 | hq | `cb06a94a-be02-4e8c-b6c6-c8c9f09922f4` | Telegram: ai-antispam / HQ [chat:-1003993000918:topic:10782] | resolved | telegram | 2026-09-18T18:36:19Z | — |
| ai-antispam Landing lane | 10783 | landing | `99b348f6-a040-4119-8aa8-00736c7fb61d` | ai-antispam Landing lane | resolved | telegram | 2026-09-11T21:55:58Z | — |
| Bot lane — ai-antispam service (Bot topic) | 10784 | bot | `6d921dca-fb0a-455b-bceb-dfb78dcf1f07` | Bot lane — ai-antispam service (Bot topic) | resolved | telegram | 2026-09-17T08:43:30Z | — |
| MAX domain — lane acceptance & verification | 11156 | _unstated_ | `85425045-2567-4beb-9867-100d6755e2cd` | MAX domain — lane acceptance & verification | resolved | telegram | 2026-09-15T03:45:41Z | — |

**Pacemakers**

| job | cron_expr | timezone | enabled | set_goal | goal_template | next_run_at | deliver_to | trigger_cmd |
|---|---|---|---|---|---|---|---|---|
| `ai-antispam-bot-service-health` | `0 9 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-09-20T06:00:00+00:00 | telegram:-1003993000918:10784 | — |
| `ai-antispam-outreach-auto-kick` | `0 7 * * *` | UTC | yes | 0 | **absent** | 2026-09-20T07:00:00+00:00 | telegram:-1003993000918:10780 | — |
| `ai-antispam-outreach-db-sync` | `0 9 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-09-20T06:00:00+00:00 | telegram:-1003993000918:10780 | — |
| `ai-antispam-outreach-mining-tranche` | `0 6 * * Mon,Wed,Fri` | UTC | yes | 0 | **absent** | 2026-09-21T06:00:00+00:00 | telegram:-1003993000918:10780 | — |
| `ai-antispam-outreach-stream-joins` | `0 */6 * * *` | UTC | **no** | 0 | **absent** | 2026-09-19T00:00:00+00:00 | telegram:-1003993000918:10780 | — |
| `ai-antispam-outreach-watch-poll` | `7 */6 * * *` | UTC | yes | 0 | **absent** | 2026-09-19T18:07:00+00:00 | telegram:-1003993000918:10780 | — |
| `ai-antispam-owner-digest` | `30 9 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-09-20T06:30:00+00:00 | — | — |
| `ai-antispam-self-audit-daily` | `50 8 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-09-20T05:50:00+00:00 | session:cb06a94a-be02-4e8c-b6c6-c8c9f09922f4 | — |
| `ai-antispam-triage-sweep` | `25 */6 * * *` | UTC | yes | 0 | **absent** | 2026-09-19T18:25:00+00:00 | — | — |
| `ai-antispam-watch-funnel-day7-report` | `0 9 22 9 *` | Europe/Moscow | yes | 0 | **absent** | 2026-09-22T06:00:00+00:00 | telegram:-1003993000918:10780 | — |
| `ai-antispam-wave0-reply-sweep` | `0 12 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-09-20T09:00:00+00:00 | telegram:-1003993000918:10780 | — |
| `ai-antispam-wave0-unactivated-reprobe` | `0 12 * * 2` | Europe/Moscow | yes | 0 | **absent** | 2026-09-21T09:00:00+00:00 | telegram:-1003993000918:10780 | — |

Attribution basis: deliver_to -> chat, deliver_to -> lane, name prefix.
2 of 12 job(s) carry no explicit `deliver_to`. The column is rendered as the live row holds it; whether a null falls back to the creating session or to nothing is the scheduler's contract, and this registry does not assert it.

### inferhub-watch — Inferhub watch

| Field | Value |
|---|---|
| freshness | ⛔ INCOMPLETE — no declared half yet |
| purpose | — |
| profile | `ops` |
| repo | `/root/inferhub-watch` |
| law | `/root/inferhub-watch/skills/inferhub/SKILL.md` — revision 1.0.30 |
| owns | — |
| does not own | — |
| substrates owned | — |
| attested at | — |

**Services**

_None declared._

**Lanes**

| topic | thread | role | session | session title | status | channel | last active | lane announcements |
|---|---|---|---|---|---|---|---|---|
| InferHub Watch: Fallback Publisher Diversity & Predictors | 2 | _unstated_ | `359fe71b-c7a1-420b-b856-acfb49939a7b` | InferHub Watch: Fallback Publisher Diversity & Predictors | resolved | telegram | 2026-09-19T12:14:31Z | — |
| Worker — HQ cycles | 32 | worker | `8cbe2d61-79c6-4ca7-8a71-805e2982d4b6` | Telegram: Inferhub watch / Worker — HQ cycles [chat:-1004379632866:topic:32] | resolved | telegram | 2026-09-17T00:37:10Z | — |
| Grafana | 557 | grafana | `7814fc64-e7ce-4274-a4ee-372563aa3c99` | Telegram: Inferhub watch / Grafana [chat:-1004379632866:topic:557] | resolved | telegram | 2026-09-18T23:59:26Z | — |
| worker: inferhub-watch-lane | 559 | worker | `1122b15e-0b26-420f-a7b3-d0719479bbd5` | worker: inferhub-watch-lane | resolved | telegram | 2026-09-19T10:59:05Z | — |

**Pacemakers**

| job | cron_expr | timezone | enabled | set_goal | goal_template | next_run_at | deliver_to | trigger_cmd |
|---|---|---|---|---|---|---|---|---|
| `inferhub-auto-switcher` | `33 */6 * * *` | UTC | **no** | 0 | **absent** | 2026-09-19T00:33:00+00:00 | — | — |
| `inferhub-daily-report` | `0 8 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-09-20T05:00:00+00:00 | telegram:-1004379632866:2 | — |
| `inferhub-hq-pacemaker` | `0 */6 * * *` | UTC | yes | 1 | **absent** | 2026-09-19T18:00:00+00:00 | session:359fe71b-c7a1-420b-b856-acfb49939a7b | — |
| `inferhub-self-audit-daily` | `0 9 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-09-20T06:00:00+00:00 | session:359fe71b-c7a1-420b-b856-acfb49939a7b | — |
| `inferhub-usage-logs-sync` | `23 */6 * * *` | UTC | yes | 0 | **absent** | 2026-09-19T18:23:00+00:00 | — | — |

Attribution basis: deliver_to -> chat, deliver_to -> lane, name prefix.
2 of 5 job(s) carry no explicit `deliver_to`. The column is rendered as the live row holds it; whether a null falls back to the creating session or to nothing is the scheduler's contract, and this registry does not assert it.

### infra-factory — Infra Factory

| Field | Value |
|---|---|
| freshness | ⛔ INCOMPLETE — no declared half yet |
| purpose | — |
| profile | `ops` |
| repo | `/root/vds-servers` |
| law | `/root/vds-servers/skills/infra-factory/SKILL.md` — revision 0.1.0 |
| owns | — |
| does not own | — |
| substrates owned | — |
| attested at | — |

**Services**

_None declared._

**Lanes**

| topic | thread | role | session | session title | status | channel | last active | lane announcements |
|---|---|---|---|---|---|---|---|---|
| HQ | 4 | hq | `6a314aac-94db-4b11-974c-f53decc25b9d` | Telegram: Infra Factory / HQ [chat:-1004486255170:topic:4] | resolved | telegram | 2026-09-19T11:27:31Z | — |
| Gatus alert routing and fleet triage | 5 | triage | `fb67ca75-8735-4c39-80be-06b59bd4365f` | Gatus alert routing and fleet triage | resolved | telegram | 2026-09-18T21:18:06Z | — |
| Surveys | 7 | surveys | `8daa376e-367c-452d-840f-0c18d66ef60a` | Telegram: Infra Factory / Surveys [chat:-1004486255170:topic:7] | resolved | telegram | 2026-09-17T12:12:45Z | — |
| LLM Gateway | 467 | gateway | `8b278a4f-531d-4d7b-8c79-87d30f9257bd` | Telegram: Infra Factory / LLM Gateway [chat:-1004486255170:topic:467] | resolved | telegram | 2026-09-18T09:30:14Z | — |
| TG Hub | 475 | _unstated_ | `a360e13f-4e34-4fac-8a1d-770644040903` | Telegram: Infra Factory / TG Hub [chat:-1004486255170:topic:475] | resolved | telegram | 2026-09-18T18:18:07Z | — |

**Pacemakers**

| job | cron_expr | timezone | enabled | set_goal | goal_template | next_run_at | deliver_to | trigger_cmd |
|---|---|---|---|---|---|---|---|---|
| `infra-sender-logs-check` | `05 18 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-09-19T15:05:00+00:00 | telegram:-1004486255170:5 | — |
| `infra-surveys-daily` | `0 9 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-09-20T06:00:00+00:00 | telegram:-1004486255170:7 | — |
| `infra-triage-patrol` | `0 */6 * * *` | UTC | yes | 1 | present | 2026-09-19T18:00:00+00:00 | session:fb67ca75-8735-4c39-80be-06b59bd4365f | /root/vds-servers/tools/triage_preflight.py |

Attribution basis: deliver_to -> chat, deliver_to -> lane.
`trigger_cmd` is truncated to 72 characters here; the full command is in `registry/index.json`.

### meta-factory — Factories

| Field | Value |
|---|---|
| freshness | ⛔ INCOMPLETE — no declared half yet |
| purpose | — |
| profile | `ops` |
| repo | `/root/agent-factories` |
| law | `/root/agent-factories/skills/meta-factory/SKILL.md` — revision 0.1.3 |
| owns | — |
| does not own | — |
| substrates owned | — |
| attested at | — |

**Services**

_None declared._

**Lanes**

| topic | thread | role | session | session title | status | channel | last active | lane announcements |
|---|---|---|---|---|---|---|---|---|
| Surveys | 19 | surveys | `5c99ad51-8889-40cb-b589-fa13fd673c06` | Telegram: Factories / Surveys [chat:-1004497192134:topic:19] | resolved | telegram | 2026-09-15T09:06:12Z | — |
| Agent Factories Triage Lane | 20 | triage | `f4c192c9-a8e9-4268-9026-ee3e4970cc8a` | Agent Factories Triage Lane | resolved | telegram | 2026-09-17T00:40:08Z | — |
| Meta-Factory HQ: ASIF Architecture & Crons | 21 | hq | `2646d31a-71ee-49f0-be81-9c8dc32d32fa` | Meta-Factory HQ: ASIF Architecture & Crons | resolved | telegram | 2026-09-19T13:59:36Z | — |
| Delegate | 68 | delegate | `23549292-77ff-40d1-97e3-5aa0bdd19d74` | Telegram: Factories / Delegate [chat:-1004497192134:topic:68] | resolved | telegram | 2026-09-19T13:36:42Z | — |
| Worker | 1271 | worker | `dcd8f7a9-c1e7-48c3-b184-d901dc08eac7` | Telegram: Factories / Worker [chat:-1004497192134:topic:1271] | resolved | telegram | 2026-09-18T12:20:07Z | — |

**Pacemakers**

| job | cron_expr | timezone | enabled | set_goal | goal_template | next_run_at | deliver_to | trigger_cmd |
|---|---|---|---|---|---|---|---|---|
| `factory-growth-map-biweekly` | `0 9 1,15 * *` | Europe/Moscow | yes | 0 | **absent** | 2026-10-01T06:00:00+00:00 | — | — |
| `factory-insights-weekly` | `0 18 * * Fri` | Europe/Moscow | yes | 0 | **absent** | 2026-09-25T15:00:00+00:00 | — | python3 /root/agent-factories/tools/synthesize_insights.py --audit |
| `factory-measurement-daily` | `0 9 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-09-20T06:00:00+00:00 | — | — |
| `factory-template-weekly` | `0 9 * * Mon` | Europe/Moscow | yes | 0 | **absent** | 2026-09-21T06:00:00+00:00 | — | python3 /root/agent-factories/tools/roadmap.py --cadence |
| `factory-triage-patrol` | `0 */6 * * *` | UTC | yes | 0 | **absent** | 2026-09-19T18:00:00+00:00 | — | out=$(gh issue list -R leshchenko1979/agent-factories --state open --li… |

Attribution basis: name prefix.
`trigger_cmd` is truncated to 72 characters here; the full command is in `registry/index.json`.
5 of 5 job(s) carry no explicit `deliver_to`. The column is rendered as the live row holds it; whether a null falls back to the creating session or to nothing is the scheduler's contract, and this registry does not assert it.

### miidas — Miidas Factory

| Field | Value |
|---|---|
| freshness | ⛔ INCOMPLETE — no declared half yet |
| purpose | — |
| profile | `ops` |
| repo | `/root/miidas` |
| law | `/root/miidas/SKILL.md` — revision 1.1.7 |
| owns | — |
| does not own | — |
| substrates owned | — |
| attested at | — |

**Services**

_None declared._

**Lanes**

| topic | thread | role | session | session title | status | channel | last active | lane announcements |
|---|---|---|---|---|---|---|---|---|
| HQ | 4 | hq | `e4f96a33-45ac-412e-8788-1b678cf2addb` | Telegram: Miidas Factory / HQ [chat:-1003996392908:topic:4] | resolved | telegram | 2026-09-19T10:49:42Z | — |
| Agent runtime | 6 | _unstated_ | `5a5335ee-db68-46fe-b13e-a082b2beadb5` | Telegram: Miidas Factory / Agent runtime [chat:-1003996392908:topic:6] | resolved | telegram | 2026-09-17T17:49:57Z | — |
| Worker — #25 CLIENT_KIND backfill + telemetry projection | 56 | worker | `b57efabd-85df-4467-bed7-f5a596285f68` | Telegram: Miidas Factory / Worker — #25 CLIENT_KIND backfill + telemetry projection [chat:-1003996392908:topic:56] | resolved | telegram | 2026-09-19T10:46:50Z | — |
| Marketing | 393 | marketing | `39d2b612-dbfc-4953-ae02-609267c68c3e` | Telegram: Miidas Factory / Marketing [chat:-1003996392908:topic:393] | resolved | telegram | 2026-09-18T01:02:12Z | — |

**Pacemakers**

| job | cron_expr | timezone | enabled | set_goal | goal_template | next_run_at | deliver_to | trigger_cmd |
|---|---|---|---|---|---|---|---|---|
| `miidas-hq-daily-trigger` | `0 9 * * *` | UTC | yes | 0 | **absent** | 2026-09-20T09:00:00+00:00 | session:e4f96a33-45ac-412e-8788-1b678cf2addb | — |

Attribution basis: deliver_to -> lane.

### opencrabs-dev — Opencrabs Dev Factory

| Field | Value |
|---|---|
| freshness | ⛔ INCOMPLETE — no declared half yet |
| purpose | — |
| profile | `ops` |
| repo | `/root/opencrabs` |
| law | `/root/.opencrabs/profiles/ops/skills/opencrabs-dev/SKILL.md` — revision 0.4.217 |
| owns | — |
| does not own | — |
| substrates owned | — |
| attested at | — |

**Services**

_None declared._

**Lanes**

| topic | thread | role | session | session title | status | channel | last active | lane announcements |
|---|---|---|---|---|---|---|---|---|
| bash guard forced-variation design | 7198 | _unstated_ | `329bf3a3-6299-4173-b991-7ea0427563e3` | bash guard forced-variation design | resolved | telegram | 2026-09-18T10:34:13Z | — |
| Mermaid | 29947 | _unstated_ | `c6b1a539-6225-40ea-a514-67d21a446cd5` | Telegram: Opencrabs Dev Factory / Mermaid [chat:-1003936827469:topic:29947] | resolved | telegram | 2026-09-19T09:37:34Z | — |
| Gemini Reasoning and Flow Message Analysis | 30045 | _unstated_ | `127429e6-08de-439c-9162-2c8b0a9f73d9` | Gemini Reasoning and Flow Message Analysis | resolved | telegram | 2026-09-19T11:09:38Z | — |
| Editor lane: #17/#19 channel-ownership PRs | 30090 | editor | `d18ce16a-75a0-447c-90c7-ab7dabce4411` | Editor lane: #17/#19 channel-ownership PRs | resolved | telegram | 2026-09-19T11:20:04Z | — |
| OC Compiler | 30129 | _unstated_ | `1539f410-b844-4001-8e9d-b063d8469dcd` | Telegram: Crabs Kanban Board / OC Compiler [chat:-1003936827469:topic:30129] | ambiguous | telegram | 2026-08-28T17:08:16Z | — |
| Deploy #235 Option Collision Guard | 30134 | _unstated_ | `1a63f103-b899-4ad2-a5b3-c89f2902bf97` | Deploy #235 Option Collision Guard | resolved | telegram | 2026-09-19T09:36:09Z | — |
| OC DEV HQ | 30220 | hq | `0117dd29-5f4b-4184-9bf4-d19dc74ac266` | Telegram: Opencrabs Dev Factory / OC DEV HQ [chat:-1003936827469:topic:30220] | ambiguous | telegram | 2026-09-19T11:58:43Z | — |
| Subagents | 30517 | _unstated_ | `a5b34466-1c14-441f-b2c6-6eaf4f316dde` | Telegram: Opencrabs Dev Factory / Subagents [chat:-1003936827469:topic:30517] | resolved | telegram | 2026-09-19T09:17:37Z | — |
| Flood Throttling | 30679 | _unstated_ | `61161247-5b1d-4efe-979b-bf46ffc85c48` | Telegram: Opencrabs Dev Factory / Flood Throttling [chat:-1003936827469:topic:30679] | resolved | telegram | 2026-09-19T10:10:52Z | — |
| Graceful restart | 31683 | _unstated_ | `7e1ebbb6-68b3-478b-abc2-b697e70c2f37` | Telegram: Opencrabs Dev Factory / Graceful restart [chat:-1003936827469:topic:31683] | resolved | telegram | 2026-09-18T11:53:20Z | — |
| Plan tool | 31789 | _unstated_ | `462181e9-ad99-4163-bd3d-c983c48049a8` | Telegram: Opencrabs Dev Factory / Plan tool [chat:-1003936827469:topic:31789] | resolved | telegram | 2026-09-19T01:19:16Z | — |
| Issue #234: Review Implementation Button | 31847 | _unstated_ | `2fbfb2f8-9b08-417a-aae8-c75edc1de1ea` | Issue #234: Review Implementation Button | resolved | telegram | 2026-09-19T09:45:50Z | — |
| Memory: Compaction & Context | 34653 | _unstated_ | `d5863180-017d-4646-82a7-19be145e4974` | Telegram: Opencrabs Dev Factory / Memory: Compaction & Context [chat:-1003936827469:topic:34653] | resolved | telegram | 2026-09-19T11:13:00Z | — |
| Vector memory | 36841 | _unstated_ | `212b3c83-6659-49c8-9984-0cf849f769c1` | Telegram: Opencrabs Dev Factory / Vector memory [chat:-1003936827469:topic:36841] | resolved | telegram | 2026-09-19T04:02:09Z | — |
| Toolsmith Issue 255 and PR Dependency Laws | 39171 | _unstated_ | `2fae1230-de9e-4fa5-aa24-822cf7188c3e` | Toolsmith Issue 255 and PR Dependency Laws | resolved | telegram | 2026-09-19T02:50:51Z | — |
| Harvesting upstream PRs into OpenCrabs | 39218 | _unstated_ | `4b0990b7-aff8-4744-8de5-e38e54de7693` | Harvesting upstream PRs into OpenCrabs | resolved | telegram | 2026-09-16T00:10:47Z | — |
| Rich resume wire | 39862 | _unstated_ | `c10cd97b-2c99-49fa-a1c4-d78a02dfd7d1` | Telegram: Opencrabs Dev Factory / Rich resume wire [chat:-1003936827469:topic:39862] | resolved | telegram | 2026-09-18T10:34:37Z | — |
| Loop guard | 39883 | _unstated_ | `40427d4f-af4a-48ba-993f-f5f0b21916c0` | Telegram: Opencrabs Dev Factory / Loop guard [chat:-1003936827469:topic:39883] | resolved | telegram | 2026-09-19T01:43:01Z | — |
| #83 config-manager-warn | 40011 | _unstated_ | `c2ba4ef2-eac3-406c-98d6-c861c5bebec2` | Telegram: Opencrabs Dev Factory / #83 config-manager-warn [chat:-1003936827469:topic:40011] | resolved | telegram | 2026-09-14T08:05:42Z | — |
| #87 config-write-types | 40479 | _unstated_ | `aff7ff41-a3a7-4c53-adc5-80fb7a33ba50` | Telegram: Opencrabs Dev Factory / #87 config-write-types [chat:-1003936827469:topic:40479] | resolved | telegram | 2026-09-19T11:11:30Z | — |
| #89 memory-search-parity | 40524 | _unstated_ | `42a44908-b8f3-42e1-bbd2-f2a672b8056e` | Telegram: Opencrabs Dev Factory / #89 memory-search-parity [chat:-1003936827469:topic:40524] | resolved | telegram | 2026-09-14T12:49:17Z | — |
| Harvest rich-host buttons | 40695 | _unstated_ | `aaa8d8ae-a4be-4b89-9f92-01a317075be3` | Telegram: Opencrabs Dev Factory / Harvest rich-host buttons [chat:-1003936827469:topic:40695] | resolved | telegram | 2026-09-19T10:02:14Z | — |
| Harvest retry-429 ladder | 40696 | _unstated_ | `afe476f8-279b-4d54-b628-c9d7e35873c8` | Telegram: Opencrabs Dev Factory / Harvest retry-429 ladder [chat:-1003936827469:topic:40696] | resolved | telegram | 2026-09-19T11:17:38Z | — |
| streaming-guard-105-xfer | 42311 | _unstated_ | `9fa7c71a-f009-418a-ac06-d0336efcf491` | Telegram: Opencrabs Dev Factory / streaming-guard-105-xfer [chat:-1003936827469:topic:42311] | resolved | telegram | 2026-09-19T03:45:55Z | — |
| Role split | 42360 | _unstated_ | `63d775f9-18e2-4097-8696-d9a2ca796f14` | Telegram: Opencrabs Dev Factory / Role split [chat:-1003936827469:topic:42360] | resolved | telegram | 2026-09-19T10:03:57Z | — |
| Triage: Issue Portfolio & Harvest Analysis | 42487 | triage | `530c29ec-596e-43a4-9c7e-1b6dfc3cd870` | Triage: Issue Portfolio & Harvest Analysis | resolved | telegram | 2026-09-19T11:04:50Z | — |
| oc-waiter + #111 durable-notify | 42744 | _unstated_ | `facd50af-0807-4fee-942b-008bff037f6f` | Telegram: Opencrabs Dev Factory / oc-waiter + #111 durable-notify [chat:-1003936827469:topic:42744] | resolved | telegram | 2026-09-18T17:39:21Z | — |
| #92 demoted-host guard | 42940 | _unstated_ | `c78e78e0-099e-455e-8dfb-7e9b8f7d13e5` | Telegram: Opencrabs Dev Factory / #92 demoted-host guard [chat:-1003936827469:topic:42940] | resolved | telegram | 2026-09-18T17:37:25Z | — |
| Telegram flow card metrics telemetry bar #232 | 43727 | _unstated_ | `95bec69b-0e96-46a9-9d91-dc355e8af18f` | Telegram flow card metrics telemetry bar #232 | resolved | telegram | 2026-09-19T03:23:26Z | — |
| Governance: Ontology & RSI | 43993 | _unstated_ | `6630dc9a-0eeb-46c2-95b8-bfae43e0766b` | Telegram: Opencrabs Dev Factory / Governance: Ontology & RSI [chat:-1003936827469:topic:43993] | resolved | telegram | 2026-09-19T04:10:19Z | — |
| Multicalls | 44326 | _unstated_ | `a38499fc-76a4-4aff-8953-fa5931ad0e5c` | Telegram: Crabs Kanban Board / Multicalls [chat:-1003936827469:topic:44326] | resolved | telegram | 2026-09-07T12:48:39Z | — |
| Fix #149: Cron Session Isolation | 49607 | _unstated_ | `6cd8175f-fb27-4cf3-a390-971ff2519a47` | Fix #149: Cron Session Isolation | resolved | telegram | 2026-09-19T11:17:52Z | — |
| Core: Skills & Engine | 49643 | _unstated_ | `4b4463d5-381c-4458-aa0c-3cf199882084` | Telegram: Opencrabs Dev Factory / Core: Skills & Engine [chat:-1003936827469:topic:49643] | resolved | telegram | 2026-09-19T12:43:15Z | — |
| Deploy issue 248 default group command scopes | 50566 | _unstated_ | `52058a75-e94b-4400-9e07-aac3a891bb1f` | Deploy issue 248 default group command scopes | resolved | telegram | 2026-09-19T11:15:37Z | — |
| FlowLine::System split — #291 header fix | 51188 | _unstated_ | `2ed8adeb-4784-4159-b68f-0e552490641e` | FlowLine::System split — #291 header fix | resolved | telegram | 2026-09-19T14:19:56Z | — |
| 🔍 PROBE review-155 | 51714 | _unstated_ | `fcfbcd89-1392-4234-9b88-e13afc30d474` | Telegram: Opencrabs Dev Factory / 🔍 PROBE review-155 [chat:-1003936827469:topic:51714] | resolved | telegram | 2026-09-11T14:55:01Z | — |
| JEV Classifier | 68049 | _unstated_ | `ef83024b-90c8-40fc-8490-e8c2879808ab` | Telegram: Opencrabs Dev Factory / JEV Classifier [chat:-1003936827469:topic:68049] | resolved | telegram | 2026-09-19T12:38:42Z | — |

**Pacemakers**

| job | cron_expr | timezone | enabled | set_goal | goal_template | next_run_at | deliver_to | trigger_cmd |
|---|---|---|---|---|---|---|---|---|
| `oc-harvest-346-resume` | `15 9 20 9 *` | UTC | yes | 0 | **absent** | 2026-09-20T09:15:00+00:00 | session:aff7ff41-a3a7-4c53-adc5-80fb7a33ba50 | if gh issue view 346 -R leshchenko1979/opencrabs --json state -q .state… |
| `oc-harvest-dispatch-4h` | `15 3,9,15,21 * * *` | UTC | **no** | 1 | present | 2026-09-19T03:15:00+00:00 | session:530c29ec-596e-43a4-9c7e-1b6dfc3cd870 | — |
| `oc-health-hourly` | `0 */6 * * *` | UTC | **no** | 0 | **absent** | 2026-09-19T00:00:00+00:00 | — | — |
| `oc-roster-detached-sweep` | `5 */6 * * *` | UTC | **no** | 0 | **absent** | 2026-09-19T00:05:00+00:00 | — | ROSTER=/root/.opencrabs/profiles/ops/skills/opencrabs-dev/tools/oc-rost… |
| `oc-triage-factory-patrol` | `0 */6 * * *` | UTC | yes | 1 | present | 2026-09-19T18:00:00+00:00 | session:530c29ec-596e-43a4-9c7e-1b6dfc3cd870 | — |
| `oc-triage-owner-digest` | `30 9 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-09-20T06:30:00+00:00 | — | — |
| `oc-upstream-delta-watch` | `15 */6 * * *` | UTC | **no** | 1 | present | 2026-09-19T00:15:00+00:00 | session:530c29ec-596e-43a4-9c7e-1b6dfc3cd870 | /root/.opencrabs/profiles/ops/skills/opencrabs-dev/tools/oc-upstream-de… |

Attribution basis: deliver_to -> lane, name prefix.
`trigger_cmd` is truncated to 72 characters here; the full command is in `registry/index.json`.
3 of 7 job(s) carry no explicit `deliver_to`. The column is rendered as the live row holds it; whether a null falls back to the creating session or to nothing is the scheduler's contract, and this registry does not assert it.

## Unattributed jobs

These rows name no known factory in their `deliver_to` and match no naming prefix. They are rendered rather than dropped: a job the registry cannot place is a finding, not an omission.

| job | cron_expr | timezone | enabled | set_goal | goal_template | next_run_at | deliver_to | trigger_cmd |
|---|---|---|---|---|---|---|---|---|
| `__opencrabs_dedup_scan__` | `0 4 * * 1` | UTC | yes | — | **absent** | — | telegram:-1002554690655 | — |
| `__opencrabs_dedup_scan__` | `0 4 * * 1` | UTC | yes | 0 | **absent** | 2026-09-20T04:00:00+00:00 | telegram:-1002554690655 | — |
| `tamara_accounting_sync` | `0 21 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-09-19T18:00:00+00:00 | telegram:-1004286036984 | — |
| `__opencrabs_dedup_scan__` | `0 4 * * 1` | UTC | yes | 0 | **absent** | 2026-09-20T04:00:00+00:00 | telegram:-1002554690655 | — |
| `tmp-nulltrigger-probe` | `4 */6 * * *` | UTC | **no** | 0 | **absent** | 2026-09-19T00:04:00+00:00 | — | — |
| `tmp-trigger-control-neg` | `0 0 1 1 *` | UTC | **no** | 0 | **absent** | 2027-01-01T00:00:00+00:00 | — | printf 'BEHIND\t0\n' |
| `tmp-trigger-control-pos` | `0 0 1 1 *` | UTC | **no** | 0 | **absent** | 2027-01-01T00:00:00+00:00 | — | printf 'BEHIND\t3\n' |

---

Generated file. Edit `registry/factories/<slug>.json` instead, then re-render.
