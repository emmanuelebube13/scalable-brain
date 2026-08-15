# task/ — work items

**Work items only.** If it has a definition of done, it belongs here. If it explains
something, it belongs in `docs/`. See `STRUCTURE.md` for the full folder map.

```
task/
├── OPEN.md          <- START HERE. The current open-items register.
├── backlog/           Raised and scoped, not started
├── <YYYY-Www>/        One folder per ISO week of active work
└── 2026-07-28.md      Older loose session logs (superseded convention)
```

| Status | Where it goes |
|---|---|
| Current priorities | `task/OPEN.md` — **update in place, do not start a competing list** |
| Raised but not started | `task/backlog/<slug>.md` |
| Active work this week | `task/<YYYY-Www>/`, deliverables under `deliverables/` |
| Finished | **stays in its week folder** — see below |

## Finished weeks do not move

Week folders are never relocated or nested once complete. They are cited as evidence from
outside `task/`: `task/2026-W31/deliverables/T3/` appears throughout
`docs/proposed-fixes/`, and `task/2026-W31/T5-fix-package/` is cited five times in
`docs/comms/S1-HANDOFF-2026-W31.md` — **a message already sent to another machine.**

Moving a finished week breaks every one of those pointers and makes sent correspondence
inaccurate. Completion is recorded in the table below, not in the directory layout.

*(This was tried and reverted during the 2026-W33 cleanup pass — see
`2026-W33/deliverables/CLEANUP/INVENTORY.md` §7.)*

## Week status

| Week | Status | Subject |
|---|---|---|
| `2026-W31` | **Complete** | T1–T7: feedback loop, secrets, promotion, heartbeat, money layer, research engine, v1 archive |
| `2026-W32` | **In flight** | 51-strategy CSV fleet (wave 2 continuing); look-ahead audit; FIX-S1-012/013 handoff |
| `2026-W33` | **In flight** | Structure/cleanup pass (`deliverables/CLEANUP/`) |

Update this table when a week closes.
