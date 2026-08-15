# task/ — work items

**Work items only.** If it has a definition of done, it belongs here. If it explains
something, it belongs in `docs/`. See `STRUCTURE.md` for the full folder map.

```
task/
├── OPEN.md               <- START HERE. The current open-items register.
├── backlog/                Raised and scoped, not started
├── 2026-July-week4/        One folder per week of active work
├── 2026-August-week1/
├── 2026-August-week2/
└── 2026-07-28.md           Older loose session log (superseded convention)
```

| Status | Where it goes |
|---|---|
| Current priorities | `task/OPEN.md` — **update in place, do not start a competing list** |
| Raised but not started | `task/backlog/<slug>.md` |
| Active work this week | `task/<YYYY>-<Month>-week<N>/`, deliverables under `deliverables/` |
| Finished | **stays in its week folder** — see below |

## Naming

`YYYY-Monthname-weekN`, where `N` is 1–4 by position in the month and the month is the one
containing that week's **Monday**. A week that straddles a month boundary is filed under
its Monday: 27 July – 2 August is `2026-July-week4`.

> **Known wrinkle:** these names sort alphabetically, not chronologically — `August`
> lands before `July` in a directory listing. Use the table below for chronological order.
> Prefixing the month number (`2026-07-July-week4`) would fix it if that ever becomes
> annoying enough to be worth another rename.

## Week status

| Order | Folder | Dates | Status | Subject |
|---|---|---|---|---|
| 1 | `2026-July-week4` | Mon 27 Jul – Sun 2 Aug | **Complete** | T1–T7: feedback loop, secrets, promotion, heartbeat, money layer, research engine, v1 archive |
| 2 | `2026-August-week1` | Mon 3 – Sun 9 Aug | **In flight** | 51-strategy CSV fleet (wave 2 continuing); look-ahead audit; FIX-S1-012/013 handoff |
| 3 | `2026-August-week2` | Mon 10 – Sun 16 Aug | **In flight** | Structure/cleanup pass (`deliverables/CLEANUP/`) |

Update this table when a week closes, and add a row when a week opens.

## Renamed from ISO week numbers — 2026-08-14

These folders were `2026-W31`/`W32`/`W33` until 2026-08-14. ISO week numbers are unreadable
without a calendar, so they were renamed to month-and-week form and all 175 in-repo
references were rewritten.

| Old | New |
|---|---|
| `task/2026-W31` | `task/2026-July-week4` |
| `task/2026-W32` | `task/2026-August-week1` |
| `task/2026-W33` | `task/2026-August-week2` |

**Computers 2 and 3 hold correspondence citing the old names** — `S1-HANDOFF-2026-W31.md`
was sent before the rename and its copies there still say `task/2026-W31/T5-fix-package/`.
Use the table above to translate. Message *filenames* and archive zip names were
deliberately left alone: those are identities, not paths.

## Finished weeks do not move

Week folders are never relocated or nested once complete. They are cited as evidence from
outside `task/`: `task/2026-July-week4/deliverables/T3/` appears throughout
`docs/proposed-fixes/`, and `task/2026-July-week4/T5-fix-package/` is cited five times in
`docs/comms/S1-HANDOFF-2026-W31.md`.

Renaming them, as above, means rewriting every one of those pointers in the same change
set. That is survivable once, deliberately. Moving a week into an `archive/` subfolder —
which was tried and reverted during this cleanup pass — buys nothing and costs the same.
Completion is recorded in the table above, not in the directory layout.

*(See `2026-August-week2/deliverables/CLEANUP/INVENTORY.md` §7.)*
