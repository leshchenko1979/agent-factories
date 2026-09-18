# Add-ons

The core template is deliberately minimal. An **add-on** is a pack of extra
structure a factory takes on top of the core — extra topics, roles, gates,
crons and rules, together with the failure each one prevents.

An add-on says *what structure is needed*. It never says what the factory's
work actually is.

---

## Two classes of add-on

Add-ons come in two kinds, and the difference matters more than any individual
pack:

| Class | Question | How many | Examples |
|---|---|---|---|
| **Binding** | What substrate does the factory run *on*? | **Exactly one of each kind** | `surface/telegram-forums`, `harness/opencrabs` |
| **Domain** | What does the factory *do*? | Zero or more, composable | `ship`, `outreach`, `watch`, `platform` |

A factory always runs on *some* chat surface and *some* agent harness. If it
does not name them, it has bound them implicitly and invisibly — and every rule
that depends on them is now welded into the core.

**Bindings are mandatory and singular. Domains are optional and plural.**

---

## The binding rule

> The **core** states *requirements*. A **binding** states the *mechanics* that
> satisfy them on one product.

The core says: *"a lane is briefed by a direct message to its own session, never
by a post in the shared channel."* That is a requirement, and it is true on any
surface and any harness.

The binding says: *"on OpenCrabs, that is `session_notify` — and because a
freshly spawned session has no channel binding yet, the notify parks, so the
kickoff needs a second hop with `send_input`."* That is mechanics, and it is
true only here.

Why the split is load-bearing:

- **The core survives the swap.** Change the harness and the core law is still
  correct — you swap one binding file and nothing else moves.
- **The leak becomes visible.** A product name inside the core law is a defect
  you can grep for, not a judgement call. See the leak test below.
- **Failure modes stay attributable.** The `send_input` second hop is not a
  general law of agent factories; it is a quirk of one harness. Filed in the
  core, it teaches the wrong lesson to every future factory.

### The leak test

A rule belongs in a binding if it stops being true when you replace the
product. Mechanical form:

```sh
# core files must not name a bound product
grep -rniE 'telegram|opencrabs|forum|topic|session_notify|gh |github' \
  TEMPLATE/SKILL.md.tmpl TEMPLATE/AGENTS.md.tmpl TEMPLATE/ONTOLOGY.md.tmpl
```

A hit is not automatically wrong — the core may legitimately *mention* a
binding by name as the thing it is currently bound to. A hit that states
**mechanics** is the defect: it is a rule that will be wrong the day the
substrate changes, sitting where nobody will look for it.

---

## Bindings

### Surface

| Pack | Binds | Take it when |
|---|---|---|
| [`surface/telegram-forums`](addons/surface/telegram-forums.md) | Telegram, forum-enabled group | The factory's chat is a Telegram forum. Currently true of all four factories |

A surface binding answers: where does the human watch the work, how does a work
unit get its own named place, how does a message get routed to that place.

### Harness

| Pack | Binds | Take it when |
|---|---|---|
| [`harness/opencrabs`](addons/harness/opencrabs.md) | OpenCrabs | The agents run as OpenCrabs sessions. Currently true of all four factories |

A harness binding answers: how does a session load its law, how is a session
addressed directly, what schedules a periodic process, what turns a check into a
command.

---

## Domains

| Pack | Take it when | Proven by |
|---|---|---|
| [`ship`](addons/domain/ship.md) | The factory's output is code that gets merged and released | OpenCrabs development |
| [`outreach`](addons/domain/outreach.md) | The factory contacts people outside the team and must track replies | AI AntiSpam |
| [`watch`](addons/domain/watch.md) | The factory's job is periodic probing and ranking | InferHub Watch |
| [`platform`](addons/domain/platform.md) | The factory runs a service for clients, not just for itself | Miidas |
| [`consulting`](addons/domain/consulting.md) | The factory's output is advice to other factories — surveying their process and recommending fixes | The meta-factory |
| [`roadmap`](addons/domain/roadmap.md) | The factory must show which process serves which client product, and at what stage | The meta-factory |
| [`stories`](addons/domain/stories.md) | The factory's operational history is worth publishing as case studies | The meta-factory |

They compose. A platform factory that also ships code takes `platform` +
`ship`. A factory that watches its own product takes `watch` + `ship`.

**Composition rule:** domain packs may assume a surface and a harness *exist*;
they may not assume *which*. A domain pack that names a product has the same
defect as a core file that does.

---

## Writing a new add-on

Every pack — binding or domain — is a page with these headings:

**take it when · what it binds / adds · rules · costs · what changes if you
swap it.**

A binding's last heading is the important one: it lists exactly which rules
evaporate when the bound product is replaced. If you cannot write that list,
the pack has leaked into the core somewhere.

Derive a pack from a factory that already runs it. If no factory runs it, mark
it `status: unproven` and say what would prove it.

The test of a good add-on: a factory that takes it can point at each thing it
added and say which failure it prevents. If it cannot, the add-on is decoration.
