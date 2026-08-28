# contracts/ — cross-machine message schemas

JSON schemas for every message passed between System 1, System 2, and System 3.
**These files are read at runtime** — System 1 validates outgoing messages against them.

## What is in this folder

| File | What it describes |
|---|---|
| `signal-message-contract.json` | A scored signal published to `scored_signal_queue` |
| `regime-map-contract.json` | The `regime_strategy_map.json` structure |
| `regime-status-contract.json` | A regime status publication |
| `weights-contract.json` | The `strategy_weights.json` structure |

## Rules

- **Changing a contract is a cross-system change.** System 2 and System 3 both read these.
  Before modifying any schema, agree the change with the operators of those systems and
  document it in `docs/comms/`.
- **Never add a field without a default.** Downstream consumers must be able to handle
  old messages that predate the new field.
- **Do not put documentation about the contracts here.** Explanatory prose belongs in
  `docs/design/`. This folder is code that happens to be JSON.

## Do NOT put here

- Documentation about the contracts (→ `docs/design/`)
- Draft or proposed schemas (→ `task/` with a definition of done)
