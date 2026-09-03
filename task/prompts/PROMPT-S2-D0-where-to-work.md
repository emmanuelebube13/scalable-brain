# D0 — where to do the work: there are TWO dashboard apps, and one of them is dead

**Read this before D1, D2, D3 or D4.** All four are dashboard changes, and the single most
common way to waste a cycle on them is to edit the app that renders nothing.

**Source:** Systems 2/3, relayed 2026-09-03. **They verified it that day by following the
imports, not from memory.** Provenance matters here because `CONNECTIONS.md` in that repo
documents the *dead* app and its panel table is wrong — a confident-looking document pointing
at the wrong tree.

---

## The live app

```
telemetry-dashboard/index.html
  └─ src/main.tsx          ← index.html loads this
       └─ src/App.tsx      ← THE LIVE APP
            └─ src/components/views/*.tsx
```

**Point the agent at `telemetry-dashboard/src/App.tsx` and the tree under it.**

Verified chain: `index.html` → `/src/main.tsx`, and `main.tsx` imports `./App.tsx`.

## Do not touch these — they render nothing

| Path | Why not |
|---|---|
| `src/App.jsx` | A whole second app. **Nothing imports it.** |
| `src/screens/*.jsx` | Belongs to the dead app |
| `src/main.jsx` | Dead — `index.html` loads `main.tsx`, not this |
| `CONNECTIONS.md` | Documents the dead app. **Its panel table is wrong.** Do not use it to locate a component |

Note the trap: the two apps differ only by extension — `App.jsx` vs `App.tsx`, `main.jsx` vs
`main.tsx`. A grep for a component name will hit both trees. **Check the extension every time.**
An edit to the `.jsx` side will look correct, pass review, change nothing when deployed, and
send someone back to re-diagnose a bug that was never fixed.

## Backend

`cloud/telemetry-web/` — FastAPI.

**Good news for D1:** it **already reads System 1's `s1_health.json` by default**, so the
`gate1` data is reachable server-side with **no new wiring**. D1 is a rendering fix, not an
integration one. Confirm the field is reaching the frontend before adding any fetch code.

## Which repo these paths are in

**These paths are in the System 2/3 repo, on their machine. They do not exist in the System 1
repo** — verified 2026-09-03: no `telemetry-dashboard/`, no `cloud/telemetry-web/`, and no
`App.tsx` or `main.tsx` anywhere under `/home/emmanuel/Documents/Scalable_Brain/`. If you are
working in the System 1 checkout and cannot find these files, nothing is missing — you are in
the wrong repo.

## The exception to the stale-mirror rule

Systems 2/3 note that **the dashboard is the exception** to their usual rule. Everything else in
their repo is a stale mirror of the VM; **for the dashboard, their checkout is authoritative and
Cloud Run is the deploy target.**

So for D1–D4: edit the checkout, deploy to Cloud Run. Do not go looking for a VM copy to
reconcile against, and do not assume the running dashboard is ahead of the checkout.

## Scope note

- **D1, D2, D3** are frontend changes under `telemetry-dashboard/src/`, possibly with a
  supporting read in `cloud/telemetry-web/`.
- **D4 is a question, not a fix.** It spans System 2's subscription and System 3's Gate-2
  counters. Its answer may not live in the dashboard at all.
- **D5 is NOT a dashboard change.** It is signal ingestion and execution — deduping trade
  intent on `signal_id`. Do not start it in `App.tsx`.

## Unresolved in the relay

The note as received ended mid-sentence: *"D1–D4 need no…"*. The intended constraint is not
known. **Confirm with Systems 2/3 before assuming D1–D4 need no VM access / no backend change /
no redeploy** — whichever it was, it was offered as a simplification and is worth having.
