# BATCH-3 REVIEW

**Batch 3 (GEMINI_BRIEF §2, "the awkward ones"):** `nnfx_backtrader`,
`outside_hma_klinger`, `strong_weak_analysis`, `weekly_range_reversal`,
`retail_sentiment_fade`, `nzdjpy_median_ma_retrace`.

Three of the six (`nnfx_backtrader`, `outside_hma_klinger`, `nzdjpy_median_ma_retrace`)
were built and measured in the 2026-08-15 session, which stopped before writing this
review. The other three were built and measured 2026-08-16. This review covers all six.

## Audit results

Full run (real-data probe included), `audit_wave2.py`, 2026-08-16:

```
PASS nnfx_backtrader
PASS outside_hma_klinger
WARN nzdjpy_median_ma_retrace   real-data probe never ran (no backfill) -> ACCEPT-UNPROVEN
PASS strong_weak_analysis
PASS weekly_range_reversal
FAIL retail_sentiment_fade      [REALDATA] the probe rejects a strategy that emits no
                                orders; --quick (steps 1-7) PASSes. See issue 2.
```

## Ledger rows

```
| 3 | nnfx_backtrader | D1 | 5 | 0/5 | 113 | 1.63 | 0.94 | 12.37% | PASS | |
| 3 | outside_hma_klinger | H4 | 5 | 0/5 | 1291 | 0.85 | -1.07 | 56.06% | FAIL | |
| 3 | nzdjpy_median_ma_retrace | D1 | 1 | 0/0 | 0 | 0.00 | 0.00 | 0.00% | INSUFFICIENT | NZD_JPY missing |
| 3 | strong_weak_analysis | D1 | 5 | 0/5 | 295 | 1.24 | 0.36 | 7.94% | FAIL | strength-rank gate unreachable |
| 3 | weekly_range_reversal | H1 | 5 | 0/5 | 45 | 0.41 | -0.88 | 24.88% | FAIL | 8.9% win rate |
| 3 | retail_sentiment_fade | D1 | 3 | 0/0 | 0 | 0.00 | 0.00 | 0.00% | UNMEASURABLE | sentiment feed absent |
```

## Systematic issues

**1. `nnfx_backtrader` is a QUALIFIED strategy recorded as "PASS", and the run continued.**
Its artefact (`results/research/nnfx_backtrader/v2_evaluation_20260815T222805Z.json`) has
`pooled.passed: true` — PF 1.63, Sharpe 0.94, MaxDD 12.4%, recovery 3.76, 113 OOS trades
over 83.9 months, `failures: []`. Under §3 of the brief that is **QUALIFIED**, the one
verdict that was supposed to stop the run and be flagged loudly. Three things a reviewer
must weigh before it is treated as a find:

- **0 of 5 cells pass individually.** The best cell is EUR_USD at PF 3.31 on **16 trades**;
  the worst is USD_CAD at PF 0.80. A pooled pass resting on one thin cell is the
  concentration artefact §9 of the brief asks to be named explicitly. `dispersion.warning`
  is null, so the harness's own flag did not catch it.
- **The strategy was run twice, 73 seconds apart.** `…222652Z.json` reports 0 trades and
  `LOW_CONFIDENCE`; `…222805Z.json` reports the passing result. Nothing in the session
  record explains what changed between them. Per brief §7 a re-run after a code change must
  keep both ledger rows with the reason; only one row exists.
- **The module fails `black --check`** (below), which means it was not put through the §4
  Step 4 gate the other modules passed.

Recommendation: do not cite this strategy anywhere as a qualifier until the two runs are
reconciled and a per-cell review is done. It is the only pooled pass in 47 strategies, so
it will attract attention.

**2. Two of the six cannot be measured at all, for two different reasons, and the audit can
only express one of them.** `nzdjpy_median_ma_retrace` declares a pair that does not exist,
so `build_frames` returns None, the real-data probe is skipped, and the audit ACCEPTs
(`REALDATA: SKIP`). `retail_sentiment_fade` declares pairs that *do* exist but has no
sentiment feed, so it correctly emits nothing and `assert_no_lookahead_v2` rejects it with
"emits no orders anywhere in 2594 bars". Same underlying condition — a required input is
absent — opposite audit outcomes. The audit has `BLOCKED-OK` for strategies that must not be
built; it has no category for one that is built correctly and cannot run. Not fixed here:
`audit_wave2.py` is a shared file (rule 2). Suggested addition: a `BLOCKED-FEED` verdict
driven by a declared-but-absent non-price dependency.

**3. Cross-sectional strategies keep degrading the same way, and it is now a pattern worth a
decision.** `strong_weak_analysis` is the second strategy in this fleet (after
`currency_momentum_factor`) whose headline mechanism is a cross-pair ranking that
`generate_orders` cannot compute, because the harness hands one pair at a time with no pair
identity. Both were implemented as "the reachable half, with the ranking as pure unreachable
helpers", and both now carry a verdict that says nothing about the mechanism the author
claimed. **Two of 47 strategies are structurally unmeasurable by this harness**, and no
amount of care in the strategy files changes that. If cross-sectional signals matter, the
fix is a harness that passes a pair-keyed frame bundle — a Wave-1-scale change, not a
strategy-level one.

**4. A metrics artefact worth knowing about before it is quoted.** `weekly_range_reversal`'s
AUD_USD cell reports **Sharpe −260.60** on 11 trades with PF 0.00. Every trade in that cell
is a loss of near-identical size, so the r-multiple series has a near-zero standard
deviation and the ratio explodes. The number is arithmetically correct and completely
meaningless. Any report that sorts or aggregates by Sharpe should treat cells with
`trade_count < 30` as unranked; the pooled verdict is unaffected because it pools
r-multiples rather than averaging cell Sharpes.

**5. `black --check src/layer0/strategies/research/` fails on three files that are not
mine.** `nnfx_backtrader.py`, `test_smashing_forex_2_fixture.py`,
`test_liquidity_grab_fade_fixture.py`. Rule 1 confines me to my own strategies' files, so
they are reported rather than reformatted. `pytest src/layer0/strategies -q` is green:
**411 passed**.

## DECISIONs recorded in this batch

- **`strong_weak_analysis`** — §3.5 fixes the ranking tie-break as alphabetical but not which
  end of a tie is "worst". One descending ranking is built and `worst` is its last entry, so
  of two currencies tied at the bottom the alphabetically *last* is worst.
- **`strong_weak_analysis`** — the strength-rank gate is not applied at all; the measured
  strategy is the trend-plus-pullback skeleton, and it trades far more often than §4.1 would.
- **`weekly_range_reversal`** — §11 predicts 10–35 trades per pair per year on the reasoning
  that CCI(2000) sits near the 5/10 band; the measurement is **45 trades across five pairs
  over seven OOS years**, about one per pair per year. Nothing was widened to chase it.
- **`weekly_range_reversal`** — the 24-bar arming window is the spec's invention (§10 #9);
  the source says only "CCI has touched the 5 level". It is the most consequential
  undocumented parameter in that strategy.
- **`retail_sentiment_fade`** — implemented in full against the §3/§9 schema with the
  sentiment series injected through the constructor; no price proxy, no degraded SMA-only
  mode. Verdict UNMEASURABLE.
- **`retail_sentiment_fade`** — the 24h publication lag is the spec's assumption, not the
  vendor's documented cadence.

## Shared-file problems found and not touched

- `audit_wave2.py` has no verdict for "built correctly, input feed absent" (issue 2).
- `black` failures in three other strategies' files (issue 5).
- The `v2_harness` crashes with an unhandled `LookAheadError` when a strategy emits no
  orders on real data, rather than recording a skipped cell. That is defensible for a broken
  strategy and wrong for `retail_sentiment_fade`; same root cause as issue 2.
