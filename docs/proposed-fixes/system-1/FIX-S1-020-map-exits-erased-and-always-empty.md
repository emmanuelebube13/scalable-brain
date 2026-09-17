# FIX-S1-020 — every map cell shipped `exits: {}`, and vet re-runs silently erased owner-designated exits

**Status:** FIXED 2026-09-16 (working tree, not committed) · **Severity:** medium today
(no in-System-1 reader of the field), high for any future consumer that trusts it ·
**Author:** Claude (Fable 5), owner-authorized · **Origin:** `issues/September-Week-3/2026-09-16.md`
(escalation of the known empty-exits latent defect in `src/vetting/CLAUDE.md`)

---

## Defect

Three interlocking pieces, all verified 2026-09-16:

1. **`src/vetting/vet.py:461` hardcoded `"exits": {}`** in the cell-construction
   comprehension that runs for EVERY cell — qualified and designated. All 8 cells in the
   current published map carry `exits: {}`.
2. **Owner-designated exits were erased on the next vetting run.** `designate.py:299`
   writes real exits (`--exits`), but `vet --live` rebuilds designated cells from scratch:
   the designation fields re-attached at vet.py:444-459 (`designated_by`, `ci_mean_r`,
   `tail_dependence`, …) did not include `exits`, so the hardcoded `{}` overwrote them.
   This actually happened between the 2026-08-17 published map (4 cells with full exit
   specs) and the 2026-09-11 map (8/8 empty).
3. **The contract could not catch it.** `contracts/regime-map-contract.json` typed
   `exits` as a bare `{"type": "object"}`, so `{}` validated at both runtime checks
   (vet.py `_validate`, designate.py D6).

## Evidence

- 2026-08-17 vs 2026-09-11 published maps (exit specs → all-empty), per the issue entry.
- Grep of `src/`: no reader of the map's `exits` — the live producer prices exits from the
  strategy's own `intent.exits` (`src/signals/build.py:405-421`) and refuses to emit
  without a priced TP. So the blast radius today is a false promise to future consumers,
  not live behaviour.
- Root cause of the erasure: designation data survives a `vet --live` rebuild ONLY through
  the in-source `vet.DESIGNATED` dict — entries `designate.py` writes into the map file
  are reconstructed from attribution + that dict on every run. Neither the CLI's `--exits`
  nor anything else ever landed exits in that dict.

## Fix (landed 2026-09-16)

- **`src/vetting/vet.py`** — a `DESIGNATED` record may now carry an `exits` key; the cell
  comprehension emits `(designation.get("exits") or None)` for designated cells and `null`
  for qualified cells. `null` is the honest value for a qualified cell: no static exit
  spec exists — exits are per-signal from the strategy intent. Empty/missing normalises
  to `null`, never `{}`. Docblock on `DESIGNATED` records the mirror requirement.
- **`src/vetting/designate.py`** — `--exits` is parsed and validated up front (must be a
  JSON object or `null`; malformed JSON and non-object values exit 1 before touching the
  DB); empty normalises to `null` so the default `"{}"` no longer trips the tightened
  contract. After a successful write with real exits, it prints a NOTE that the
  designation must be mirrored into `vet.DESIGNATED` (including `exits`) to survive the
  next vetting run.
- **`contracts/regime-map-contract.json`** — `exits` is now
  `{"type": ["object", "null"], "minProperties": 1}`: either `null` or a non-empty
  object; the lying `{}` is rejected.

**Cross-system note (for the owed P1-7 comms message):** a contract change is nominally
cross-system, but System 2 provably never parses this file — grep of their reference copy
(`work/system2Executor/`) finds zero Python references to `regime_strategy_map.json`
contents (it is downloaded and checksum-verified only; confirmed independently in the
2026-09-16 issue log). The schema tightening therefore changes no deployed consumer's
behaviour; it should still be mentioned in the next comms message so the promise-shape of
the field (`null` = no static spec, object = owner-declared spec) is on the record.

**Not restored:** the exit specs erased from the 2026-08-17 map. Re-declaring them is an
owner decision (they belong to designations whose evidence has since been re-measured —
see the withdrawn `xard_ma_cross_daily_open@H1@High-Vol` block in `vet.py`). Both current
`DESIGNATED` records carry no `exits`, so those cells will honestly publish `null`.

## Verification

- `src/vetting/tests/test_designate_and_schema.py` — FIX-S1-020 pins:
  `test_designated_exits_survive_a_vet_rerun` (3 consecutive rebuilds keep the owner's
  exits, map validates each time), `test_qualified_cells_emit_null_exits`,
  `test_designation_without_exits_emits_null_not_empty_object` (absent and `{}` both
  normalise to `null`), `test_contract_rejects_empty_exits_object`,
  `test_contract_accepts_null_and_non_empty_exits`, `test_cli_rejects_non_object_exits`.
  Base fixture updated `{}` → `null`.
- `python -m pytest src/vetting -q`: 71 passed, 1 skipped.
- Full suite (`python -m pytest src -q --ignore=src/layer0/strategies/research/tests`):
  842 passed, 1 skipped, 9 failed — all 9 in `src/signals/tests/test_ledger.py`, caused by
  a concurrent in-flight change in `src/signals/run.py` (`NameError: setup_dedup` at
  run.py:377, a missing import in someone else's uncommitted setup-dedup work; new file
  `src/signals/setup_dedup.py` untracked). Not touched — outside this fix's file scope.
- `black` clean on the three changed Python files.
- Did NOT run `vet --live` (map writes frozen; the live map is not this fix's to
  regenerate). The published map still carries `exits: {}` until the next governed
  vetting run, whose output will validate against the tightened contract.

## Not checked / follow-ups

- The deployed System 2 host (reference copy only, per CLAUDE.md) — the "never parses
  the map" claim should be re-confirmed on-host before the comms message asserts it.
- The structural gap remains that a `designate.py` map-file entry (not just its exits)
  survives only via a manual mirror into `vet.DESIGNATED`; this fix adds the printed
  reminder but does not automate the mirror.
- `src/serializer/reference_vector.json` contains an `exits` array in a signal payload —
  unrelated schema (ScoredSignal, not the map); not audited.
