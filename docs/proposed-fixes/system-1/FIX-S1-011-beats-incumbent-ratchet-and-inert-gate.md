# FIX-S1-011 / FIX-S1-012 — the promotion regression gate was inert, and would have ratcheted

**Status:** PROMOTED & LIVE 2026-07-29 — shipped in bundle `2026-07-29T11-46-42Z-55dacdbf`,
which is **the first promotion in the project's history where `beats_incumbent` actually
compared anything**.

**Commits:** `177e373` (S1-011), `977375f` (S1-012)
**Evidence:** `task/2026-July-week4/deliverables/T3/`

---

## Symptom

`beats_incumbent` — the gate whose entire job is to stop a worse model taking the live
pointer — reported `true` on every promotion while never performing a comparison.

| Retrain | `regime_accuracy` | incumbent seen | gate |
|---|---:|---|---|
| 2026-07-01 | 0.717 | `None` | fail-open |
| 2026-07-19 | 0.8603 | `None` | fail-open |
| 2026-07-26 | 0.965 | `None` (`resolution: absent`) | fail-open |

## Root cause A (FIX-S1-012) — the backend was never configured

`src/common/storage/__init__.py::build_storage()` read
`os.environ.get("STORAGE_PROVIDER", "local")`, and `src/system1/scheduler/orchestrator.py`
loads `.env` nowhere. `_incumbent()` therefore resolved against the **local
`model-artifacts/` tree** — which has no `system1/` prefix — instead of GCS, found nothing,
logged `NO INCUMBENT FOUND`, and took the documented fail-open branch.

```
$ python -c "import os; from src.system1.scheduler import orchestrator; \
             print(os.environ.get('STORAGE_PROVIDER')); \
             from src.common.storage import build_storage; print(type(build_storage()).__name__)"
None
LocalFSBackend
```

This is the same producer/consumer divergence FIX-S1-007 was written to close, resurfacing by
a different route: FIX-S1-007 routed the consumer through the storage abstraction, but nothing
ensured the abstraction was *configured*. A worse model could have taken the live pointer at
any point in 2026.

**Fix:** `build_storage()` loads `.env` itself before reading `STORAGE_PROVIDER`.
`load_dotenv` does not override variables already set, so explicit test/CI overrides still win.

**Tests:** `src/common/storage/tests/test_backend_selection.py` (4), each in a subprocess with
`STORAGE_PROVIDER` scrubbed so the cold-start path is genuinely exercised — including
`test_incumbent_resolves_a_live_bundle_not_absent`, which asserts `_incumbent()` never returns
`absent` while a model is live.

## Root cause B (FIX-S1-011) — the comparison was a ratchet

`orchestrator.py` (pre-fix):

```python
gates["beats_incumbent"] = inc_acc is None or (acc is not None and acc >= inc_acc)
```

A bare `>=` with no tolerance. Because `serialize.publish` writes the **challenger's own**
metrics as the next baseline, the live accuracy is monotonically non-decreasing: a high-water
mark over a *noisy* estimate. Such a process converges on the luckiest draw ever observed and
then blocks every later challenger, including strict improvements that sampled lower. The
baseline had already climbed **0.717 → 0.8603 → 0.965**.

Combined with root cause A, the next retrain would have been the first to enforce it — against
a 0.965 bar.

**Fix:** `BEATS_INCUMBENT_TOLERANCE = 0.965`; the challenger is compared to the **currently
live** incumbent within that band, so the bar tracks what is live rather than the best ever
seen and can fall as well as rise. Downward drift stays bounded by the absolute
`REGIME_ACCURACY_FLOOR = 0.70`. `passed` is now computed over boolean gates only, so the new
`beats_incumbent_detail` evidence block can never itself count as a passing gate.

**Tests:** `src/system1/scheduler/tests/test_beats_incumbent_ratchet.py` (10), including
strictly-better promotes, marginally-worse does not flap, three successive promotions do not
raise the bar, the bar can fall, real regressions still blocked, drift bounded by the floor,
and fail-closed on a missing candidate metric.

## Note on the "0.965 factor"

The W31 task prompt described the gate as "re-armed at a 0.965 factor that ratchets".
`grep -rn '0\.965' src/` returns **nothing**. The number is the live 2026-07-26 bundle's
`regime_accuracy`, misread as a threshold constant. The ratchet concern was correct; the
mechanism was not.

## Verification in production

The 2026-07-29 promotion is the first with a real comparison:

```json
"incumbent_resolution": "prefixed",
"beats_incumbent_detail": {
  "candidate_regime_accuracy": 0.965,
  "incumbent_regime_accuracy": 0.965,
  "required": 0.931225,
  "tolerance": 0.965
}
```

## Known gaps left open

1. **`beats_incumbent` compares only `regime_accuracy`.** The promoted candidate's OOS uplift
   (0.03649) is *lower* than the incumbent's (0.03891) and no orchestrator gate noticed. A
   bundle-level uplift regression check is missing.
2. **`previous.json` is never written.** CLAUDE.md documents "superseded pointer archived to
   `previous.json`", but no code implements it — `grep -rn 'previous.json' src/` returns
   nothing. There is no one-step rollback pointer.
3. **`orchestrator` has no dry-run.** `--force` always promotes on a gate pass; an
   `--evaluate-only` flag would make gate evidence obtainable without a promotion.
