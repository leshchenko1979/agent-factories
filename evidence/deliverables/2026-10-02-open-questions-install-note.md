# Open Questions — install note

**Audience:** an OpenCrabs user standing up the Open Questions register on their own instance.
**Date:** 2026-10-02 · **Tool version:** 2.0.0

---

## What you are installing

A register where an agent parks the decisions it is blocked on, renders them as a page, and
receives your answers back into the asking session.

You need three things: **two files**, **a Node build directory**, and (only if you want an agent
to call it as a tool) **a bridge + one config entry**. There is no pip package and no installer.

---

## 1. Where the code is

The tool is **public**: `leshchenko1979/opencrabs-skill`. (The factory framework around it is not
— only this tool is.)

Pin to a commit rather than `main`, so your copy is reproducible:

| file | path in repo | bytes | blob sha |
|---|---|---|---|
| CLI | `tools/state/oc-questions` | 273392 | `6a117817c3d10f16e60351e08fce21a9f0ac012c` |
| renderer | `tools/state/oc-questions-render.mjs` | 15629 | `3d71b3812242d78a02c2875f728f1c0c13b8dfc6` |

Repo `main` at the time of writing: **`2a4081d716d5e89f45b4ecc3e533e2d0091c375e`** (2026-10-02T15:24:53Z).

---

## 2. Requirements

- **Linux.** Python **3** (standard library only — nothing to `pip install`).
- **Node.js + npm** (tested on Node `v22.22.3`, npm `10.9.8`). The page renderer needs them.
- An **OpenCrabs profile** directory. The tool finds its own state from your profile home, so no
  paths need configuring to get started.
- *Optional:* `systemd`, only if you want the page republished automatically (step 6).

---

## 3. Install the two files

**They must sit in the same directory, and the renderer's name is derived from the CLI's name.**
A CLI named `oc-questions` looks for `oc-questions-render.mjs` **beside it**. Rename one and you
must rename the other, or the renderer will not be found.

```bash
DEST=~/.opencrabs/profiles/<your-profile>/skills/opencrabs-dev/tools/state
BASE=https://raw.githubusercontent.com/leshchenko1979/opencrabs-skill/2a4081d716d5e89f45b4ecc3e533e2d0091c375e

mkdir -p "$DEST"
curl -fsSL -o "$DEST/oc-questions"             "$BASE/tools/state/oc-questions"
curl -fsSL -o "$DEST/oc-questions-render.mjs"  "$BASE/tools/state/oc-questions-render.mjs"
chmod +x "$DEST/oc-questions"
```

The `+x` is **load-bearing**, not cosmetic: the tool's own selftest re-executes the tool as a
subprocess for its concurrency leg, and the backend can invoke it directly.

---

## 4. The renderer's Node dependencies

The CLI copies the renderer into a **build directory** and runs it there, because ESM resolves a
bare import from the *importing file's* own location — so `node_modules` must live in that
directory, not next to the CLI.

- Build directory: `$OC_QUESTIONS_RENDER_DIR`, else `<store>/build`
- Store: `$OC_QUESTIONS_DIR`, else `~/.opencrabs/profiles/${OC_PROFILE:-ops}/questions`

Create the build directory and install the exact pinned set:

```bash
BUILD=~/.opencrabs/profiles/<your-profile>/questions/build
mkdir -p "$BUILD"
cat > "$BUILD/package.json" <<'JSON'
{
  "name": "oc-questions-render",
  "private": true,
  "type": "module",
  "version": "0.0.1",
  "description": "Static renderer for the Open Questions page: json-render spec -> HTML",
  "dependencies": {
    "@json-render/core": "0.21.0",
    "@json-render/react": "0.21.0",
    "react": "19.2.3",
    "react-dom": "19.2.3",
    "zod": "4.5.4"
  }
}
JSON
cd "$BUILD" && npm install
```

**This step is the one people skip, and skipping it produces a silent half-install:** the CLI
registers questions happily and publishes nothing, because every render exits non-zero for want
of a module. Nothing warns you — the render fault is reported as a reason, and the last good page
keeps serving.

---

## 5. Verify

Run the tool's own selftest:

```bash
"$DEST/oc-questions" selftest
```

It builds a scratch store in a temp directory and exercises the store, the concurrency leg, the
renderer and the refusal paths. It needs `node` and the `node_modules` from step 4 to pass.

Then a smoke test of the real path:

```bash
"$DEST/oc-questions" lint          # store + configuration sanity
"$DEST/oc-questions" --help        # the full verb surface
```

---

## 6. Configuration — the parts that are OURS, not yours

These default to the values of the instance this tool was extracted from. Change them:

| variable | default | set it to |
|---|---|---|
| `OC_QUESTIONS_BASE_URL` | `https://questions.l1979.ru` | **your own origin** — otherwise the page URL it hands out points at our host |
| `OC_QUESTIONS_TRACKER` | `leshchenko1979/opencrabs` | your own issue tracker, `owner/repo` — used by the mechanical-closure check |
| `OC_QUESTIONS_DIR` | `<profile home>/questions` | only if you want the store elsewhere |
| `OC_QUESTIONS_RENDER_DIR` | `<store>/build` | only if you want the build elsewhere |
| `OC_QUESTIONS_DB` | `<profile home>/opencrabs.db` | usually leave alone — it already points at your own instance's database |

The last one is worth knowing about: the tool resolves a lane's **display name** from the live
session binding in your instance's database, never from a value the caller supplies. On your own
profile that default is already correct.

---

## 7. Serving the page — separate from the tool

The tool writes the page **locally**, into `<store>/pages/<token>/`. Making it reachable on the
internet is your own infrastructure, and the tool does not do it.

Ours is a three-piece arrangement, for reference: a systemd `.path` unit watching the store, a
oneshot `.service` that rsyncs the pages to a small vpn host, and a web server serving them.

**Without any of that, everything still works** — you just open the page from disk.

---

## 8. Agent integration (this part is NOT in the public repo)

Calling it from the shell works with steps 1–5 alone. To let an **agent** call it as a tool you
need two more pieces, which live in our profile and are not published:

- the bridge `oc_questions_tool.py` — reads the params file, builds a strict argv, never a shell;
- a `[[tools]]` entry named `oc_questions` in your `tools.toml`, pointing at that bridge.

The bridge locates the CLI under `$OC_QUESTIONS_SKILL_ROOT/tools/state/oc-questions`, and that
variable's default is a hardcoded path in our profile — point it at yours.

---

## 9. Bounds — read these before you redistribute

- **No licence file.** The public repo carries none. Public means *readable and forkable*; it does
  not mean licensed for reuse. Ask before you pass it on.
- **The governing contract is not public.** `docs/instruments/open-questions.md` lives in the
  private factory repo. The public `tools/docs/RC-CONTRACT.md` documents the tool's exit codes and
  behaviour in detail, so you are not blind — but the contract that governs it is out of reach
  from the link.
- **htmx is fetched from unpkg at publish time** and vendored into the token directory. With no
  network the page degrades to a plain form: it still works, it just loses the inline swap.
- **Nothing tells you your copy is stale.** A copy on disk is a copy nobody compares. Re-pull from
  a newer commit when you want the fixes.
