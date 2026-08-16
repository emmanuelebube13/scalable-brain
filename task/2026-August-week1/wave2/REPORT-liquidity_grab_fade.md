# REPORT-liquidity_grab_fade

## Implemented
An H1 mean-reversion strategy that trades false breakouts (liquidity grabs) at significant swing highs/lows. It identifies the most recent confirmed swing extreme (lag 5) and looks for a 1-hour candle whose wick sweeps past this level but whose body closes firmly back inside the range (the close must cross back over the level and the body must be >= 50% of the entire candle range). Entry is at market. The stop loss is placed with a tight 3.0 pip buffer beyond the sweeping candle's wick. The exit is a fixed 1.5R target.

## Deviations
None. The code matches the specification perfectly.

## Uncertainties
- **Sweep strictness**: The logic demands the close to be strictly back across the swing level. A close exactly on the level, or barely past it without a solid body, does not trigger.
- **Swing lag**: Standardizing on a 5-bar lag for confirmed swings means the strategy only looks at relatively mature support/resistance zones.

## Coverage
- **Pairs requested**: Any
- **Pairs declared**: EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (the 5 live pairs).
- **Pairs missing**: None
- **Pairs skipped by harness**: None. All 5 pairs were run.

## Verdict
FAIL (0.65 PF). The strategy fired 737 OOS trades across 5 pairs. The robust sample size confirms that this exact formulation of a false breakout has a highly negative expectancy. Fading H1 breakouts with a tight stop directly behind the sweeping wick means the strategy repeatedly gets stopped out by continuation pushes or wider complex sweeps before any reversal can materialize.
