# P3 — `selection_basis`, the map schema bump, and the designation command

**Engineer:** Gemini Pro · **Reviewer:** Claude
**Est:** 4–5 h · **Risk:** high — changes a contract System 2 and System 3 consume.
**Needs:** P2. **Blocks:** P5.

**Read `README.md` §2 before anything else. It is the reason this task exists.**

---

## Why

Two problems, one task.

**First**, the owner intends to publish a strategy that does not pass the gates. That must
be possible without weakening the gates, and it must be impossible to mistake for a
qualification.

**Second**, `regime_strategy_map.json` entries carry `strategy_id`, `variant`, `rank`,
`composite_score`, `metrics` — **and no direction, no stop, no target.** That omission
caused the 2026-08-02 incident: System 2, given no direction, inferred one from the regime
label and took 13 of 13 shorts in a downtrend for a mean-reversion strategy. Contract v2
declares direction and exits per `OrderIntent`, so the map must carry them.

---

## Hard constraints

1. **`gates.py` is not touched.** Not now, not for this.
2. `designated` requires a human reason, a human name, and the list of gate failures. No
   defaults. Refuse to designate without them.
3. `status` and `qualification_run_id` stay mandatory (agreed with System 2, 2026-08-15).
   The schema bump must not drop them.
4. **This is a coordinated change with System 2 and System 3.** Bump `schema_version`, write
   the note, and get the owner to send it. Do not publish a changed schema and hope.
5. A consumer must reject an unrecognised `selection_basis`. Unknown is never permissive.

---

## Execution plan

### Step 1 — Extend the map schema

`contracts/regime-map-contract.json`, `schema_version` bumped. Each entry gains:

| field | rule |
|---|---|
| `selection_basis` | `"qualified"` \| `"designated"`. Required. Enum-constrained. |
| `gate_failures` | array of strings. **Required and non-empty when `designated`**, empty when qualified. |
| `designated_by` | human name. Required when designated. |
| `designated_reason` | free text. Required when designated. |
| `designated_at_utc` | timestamp. Required when designated. |
| `direction` | `"long"` \| `"short"` \| `"both"`. Required — the 2026-08-02 fix. |
| `exits` | the strategy's declared stop/target rules, enough for System 2 to place them without inference. |
| `strategy_key` | the string id, so a human can tell what it is. |

Make `gate_failures` non-empty-when-designated a **schema-level** constraint
(`if`/`then`), not a code convention — a contract that lives only in the producer is a
contract only one side can check.

### Step 2 — The designation command

```
python -m src.system1.vetting.designate --strategy kiss_h4 \
    --reason "forward test on practice; pooled PF 1.2, fails Sharpe" \
    --by "Emmanuel" --dry-run
```

Behaviour:

- resolves the strategy through P0's catalog
- **re-runs the gates and records exactly what it fails** — the failures are read from
  `gates.py`, never typed in by hand
- refuses if the strategy is in `INTEGRITY_DISQUALIFIED`. A look-ahead defect is not a
  performance shortfall and must not be designatable at any price
- refuses if it has zero OOS trades
- writes the entry into the map with `selection_basis="designated"` and every required field
- **dry-run by default**; a real write needs an explicit flag AND is recorded in `STATE.md`'s
  sign-off table

### Step 3 — Make the honest numbers travel with it

The manifest must carry, for a designated strategy, the things that unmasked the last two
false positives:

- OOS trade count
- bootstrap CI on mean R
- cells passed / cells attempted
- share of trades in the largest pair
- total R with the top 3 winners removed

If a strategy's edge evaporates when three trades are removed, whoever reads the manifest in
a month should be able to see that without re-deriving it.

### Step 4 — The note to Systems 2 and 3

`task/2026-August-week3/promotion-path/notes-for-systems-2-3/MAP-SCHEMA-BUMP.md`, in the
house style of `docs/comms/` — lead with a short numbered version, be explicit about what
action is required and what is informational.

It must say plainly: **a `designated` strategy has not passed the gates**, here is what it
fails, and System 3 should size it differently or refuse it. Do not soften this.

**Assemble it. Do not send it.** Sending is the owner's call.

### Step 5 — Tests

1. `designated` without a reason / name / failures is refused.
2. `gate_failures` empty while `selection_basis="designated"` fails schema validation.
3. An `INTEGRITY_DISQUALIFIED` strategy cannot be designated.
4. A strategy with zero OOS trades cannot be designated.
5. `qualified` cannot be set by hand — only by passing the gates.
6. An unrecognised `selection_basis` is rejected by the schema.
7. `status` and `qualification_run_id` survive the bump.
8. Direction and exits are present on every entry.
9. Dry-run writes nothing.

---

## Definition of done

- [ ] Schema bumped, `if`/`then` constraints enforced at schema level
- [ ] `designate` command, dry-run default, gate failures read from `gates.py`
- [ ] Honest metrics travel in the manifest
- [ ] Note to Systems 2/3 assembled, not sent
- [ ] Tests pass; state the count
- [ ] `gates.py` unchanged — verify and state

## Reviewer will check

- That `qualified` is unreachable except by actually passing.
- That a designated entry cannot exist without its failures attached — by trying it.
- That strategy 10 cannot be designated.

---

## Failure log

| Timestamp | Step | What went wrong | Root cause | Fix |
|---|---|---|---|---|
| | | | | |
