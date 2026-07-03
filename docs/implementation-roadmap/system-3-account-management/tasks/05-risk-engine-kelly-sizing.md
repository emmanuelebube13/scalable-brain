# AMS-005 — Risk Engine: Kelly Sizing (Gate D–G)

- **Task ID**: AMS-005
- **System**: System 3 — Account Management
- **Priority**: P0-Critical
- **Estimated Effort**: 4d
- **Prerequisites**: AMS-004
- **External Dependencies**:
  - **DB (AMS-001)** — read `strategy_performance` (per strategy×regime win rate / win-loss ratio), `AMS_Account_State`, `risk_state`. *Why:* Layers F and G need live strategy stats and account balance.

## Objective
Implement Decision Gate Layers D–G — drawdown proximity, consecutive-loss, strategy×regime compatibility, and Quarter-Kelly position sizing with all context multipliers and a 0.1% floor.

## Current State
**New** as a gate, but the math exists and **moves here**: Quarter-Kelly sizing (`K = WinRate − (1−WinRate)/WinLossRatio`, `FRACTIONAL_KELLY=0.25`, `MAX_RISK_PERCENT=0.02`, `FIXED_WIN_RATE=0.45`) lives in `src/layer7/oanda_executor.py`. The risk engine replaces the *fixed* 45% win rate with **live strategy×regime stats** and adds the context multipliers and floor. Layer 7 will keep only order placement.

## Target State
Given a signal that passed A–C, the risk engine runs Layers D–G sequentially, computing a set of multipliers and a final risk fraction, then converts that to a position size (lots) using the ATR-based stop. The result (risk %, lots, multipliers, gate flags) is handed to Layers H–J (AMS-008). REJECT short-circuits propagate.

## Technical Specification

### Layer D — Drawdown proximity (from current_drawdown_pct)
| Drawdown | Action | DD multiplier |
|----------|--------|---------------|
| < 10% | full | 1.00 |
| 10–15% | −50% | 0.50 |
| 15–20% | −75% + **only highest-confidence** signals (else REJECT) | 0.25 |
| ≥ 20% | **CIRCUIT BREAK** → REJECT, trigger breaker (AMS-006) | — |

### Layer E — Consecutive losses (from consecutive_losses; resets on any win)
| Losses | Action | Consec multiplier |
|--------|--------|-------------------|
| 0–2 | normal | 1.00 |
| 3 | −25% | 0.75 |
| 4 | −50% | 0.50 |
| 5 | **REJECT all signals for 24h** (cooling) | — |

### Layer F — Strategy × regime compatibility (from strategy_performance for THIS strategy in THIS regime)
| Live win rate | Action | Regime multiplier |
|---------------|--------|-------------------|
| < 35% | **REJECT** (strategy mismatch) | — |
| 35–45% | −50% | 0.50 |
| > 45% | normal | 1.00 |
| no data for strategy+regime | **DEMO sizing only** → force 0.1% risk | floor |

### Layer G — Position sizing (Quarter-Kelly + context)
```
K = WinRate - ((1 - WinRate) / WinLossRatio)        # live stats; K<=0 -> REJECT (no edge)
base_risk = min(K * 0.25, MAX_RISK_PER_TRADE)       # MAX = 2.0% (config); mode cap also applies
risk_fraction = base_risk
              * drawdown_multiplier      (Layer D)
              * consecutive_multiplier   (Layer E)
              * regime_multiplier        (Layer F)
              * stage_multiplier         (demo .5 / micro .5 / small .75 / full 1.0)
              * caution_factor           (0.5 if sub_state==CAUTION, from AMS-003)
risk_fraction = max(risk_fraction, 0.001)           # HARD FLOOR 0.1%
risk_fraction = min(risk_fraction, mode_risk_cap)   # 1%/1.5%/2% by mode
risk_usd = current_balance * risk_fraction
# ATR-based stop -> lots
stop_distance_pips = atr_multiplier_for_stop * ATR  # ATR provided with signal context
lots = risk_usd / (stop_distance_pips * pip_value)
lots = min(lots, max_position_size_lots)
```
- `WinLossRatio` (avg_win/avg_loss) and `WinRate` come from `strategy_performance`. If absent/insufficient sample → Layer F forces the 0.1% demo floor (do not invent stats).
- Multipliers apply **sequentially/multiplicatively** in the order D → E → F → stage → caution.
- The 0.1% floor is applied **after** all reductions; the mode cap is applied **after** the floor (floor never exceeds cap because caps ≥ 0.1%).
- Negative/zero Kelly (no edge) → REJECT with reason `NO_EDGE`.

### Output to AMS-008
`{ risk_fraction, risk_usd, lots, multipliers:{dd,consec,regime,stage,caution}, gate_flags }` plus any REJECT short-circuit with `gate_failed` ∈ {D,E,F,G}.

### Default-safe
Missing balance/ATR/stats, or any computation error → REJECT (`STATE_UNAVAILABLE` / `INSUFFICIENT_DATA`). Never approve on uncertainty. All arithmetic uses Decimal (mirror Layer 7) to avoid float drift in money math.

## Testing & Validation
- Golden fixtures: known (WinRate, WinLossRatio, balance, ATR, drawdown, consec, regime, mode) → exact lots/risk to the cent.
- Boundary tests at every threshold: DD 9.99/10/15/15.01/20; consec 2/3/4/5; win rate 34.9/35/45/45.1.
- Floor test: a heavily-reduced size never drops below 0.1%; cap test: never exceeds the mode cap.
- No-data path forces 0.1% demo size; negative-Kelly path rejects (`NO_EDGE`).
- Drawdown ≥ 20% triggers the circuit break call into AMS-006 (verify the hook).
- Latency: D–G with cached stats < 100 ms on H1 (p95).
- Scenario (March-2020-like): rising drawdown + losing streak compounds multipliers toward the floor, then circuit-breaks at 20% — sizes shrink monotonically.

## Rollback Plan
Risk engine is pure computation feeding AMS-008; nothing executes from D–G alone. Rollback = revert to a conservative fixed-fraction sizer behind a flag (e.g. flat 0.1%), or disable the gate (DEMO logging). No persisted state is mutated except the append-only decision log via AMS-003.

## Acceptance Criteria
- [ ] Layers D, E, F produce the exact actions/multipliers in the tables, including the no-data → 0.1% and <35% → REJECT cases.
- [ ] Quarter-Kelly + sequential multipliers + 0.1% floor + mode cap match golden fixtures to the cent.
- [ ] Negative/zero Kelly and DD ≥ 20% reject (the latter triggers AMS-006).
- [ ] All money math is Decimal; no float drift across fixtures.
- [ ] D–G latency < 100 ms on H1 with cached strategy stats.

## Notes & Risks
- This is the highest-value, highest-risk math in the platform — over-sizing risks ruin. Treat the fixture suite as a contract; any change to multipliers requires updated fixtures + review.
- `strategy_performance` is produced by AMS-009; until it has data, Layer F's no-data path keeps sizes at the 0.1% floor — acceptable and safe for early DEMO.
- Keep `pip_value`/instrument metadata source explicit and consistent with Layer 7 to avoid a sizing unit mismatch.
