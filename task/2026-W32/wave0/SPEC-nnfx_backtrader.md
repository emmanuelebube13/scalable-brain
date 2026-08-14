# SPEC-nnfx_backtrader

**Source:** row 42 of forex_swing_strategies.csv · https://github.com/ddm-j/NNFX-Backtrader
**Conviction (author's):** MODERATE

**Source-fidelity note (read first).** The CSV prose for this row is a lossy summary of a
real open-source repo. For this spec the repo's master branch (`nnfx.py`,
`custom_indicators.py`, `BinaryGenerator.py`) was retrieved and read in full, so every
indicator formula in §3 is **author-specified from the author's own code**, not
reconstructed. Where the CSV prose and the repo disagree, the disagreement is logged in
§10 with the reading taken. Repo parameter values used (from `NNFX.params` in `nnfx.py`,
which override the indicator class defaults): Butterworth(period=40, poles=3),
Schaff(fast=20, slow=50, cycle=10, factor=0.5), iTrend(period=30),
Damiani(atr_fast=13, std_fast=20, atr_slow=40, std_slow=100, thresh=1.4, lag_suppress=True),
SSL(period=20), ATR(14), SL=1.5×ATR, TP=3.0×ATR.

## 1. Hypothesis

Daily-trend persistence in FX is exploitable when several *independent* trend/volatility
measurements agree: a smoothed-price baseline cross (Butterworth low-pass filter) fires the
trigger, two mathematically unrelated confirmation oscillators (Schaff Trend Cycle — a
double-smoothed stochastic of MACD; iTrend — an Ehlers instantaneous-trend IIR filter) veto
whipsaws, and a volatility-regime meter (Damiani — fast/slow ATR ratio vs fast/slow
std-dev ratio) blocks entries in flat, mean-reverting markets where daily crosses are
noise. Requiring unanimous agreement trades signal frequency for signal quality, and the
2:1 reward-to-risk bracket plus ATR trailing stop harvests the multi-week continuation
that behavioural herding and slow-moving institutional flows produce after a genuine daily
trend break. The edge should persist because the filters are all price-derived measures of
the same underlying phenomenon (regime change) with different lag/noise trade-offs, so
agreement is a cheap form of ensemble confirmation.

## 2. Scope

- **primary_granularity:** D1 (all signals and indicator values are computed on D1 only)
- **context_granularities:** none (single-timeframe strategy)
- **simulate_on:** H1 (fill resolution only; the strategy never sees H1 data)
- **pairs_requested (verbatim):** "Multi-pair FX majors and minors (iterates over all loaded data feeds)"
- **pairs_available:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (live) · GBP_JPY,
  EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD (**pending** — Wave-1
  additions; declare them, harness skips until history lands). These 13 cover "majors and
  minors" within the available universe.
- **pairs_missing:** none. "Majors and minors" names no specific pair outside the 13 above.
  No non-price data is required: the Damiani "volume" filter is, despite its NNFX role name,
  a pure ATR/standard-deviation ratio — it uses no volume series (verified in source).
  **No DATA-GAP file is required for this strategy.**

## 3. Indicators

All values below are computed on **completed D1 bars**; at decision bar `t` every input uses
only bars `≤ t`. `C[t]`, `H[t]`, `L[t]` are the close/high/low of bar t.

| Indicator | Params | Source |
|---|---|---|
| ATR(14) | period=14, D1 | inventory `atr(high, low, close, 14)` |
| Butterworth baseline (private `butter`) | period=40, poles=3 | private, author-specified below |
| Schaff Trend Cycle binary (private `c1_state`) | fast=20, slow=50, cycle=10, factor=0.5 | private, author-specified below |
| iTrend binary (private `c2_state`) | period=30 | private, author-specified below |
| Damiani Volatmeter gate (private `vol_f`) | 13/20/40/100, thresh=1.4, lag_suppress=True | private, author-specified below |
| SSL channel state (private `ssl_state`) | period=20 | private, author-specified below — **documented for completeness only; its exit use is inexpressible (§7, §10 #6)** |

### 3.1 Butterworth baseline (poles=3, period=40) — from `custom_indicators.py:746-804`

```
a1 = exp(-π / 40)
b1 = 2 * a1 * cos(radians(1.738 * 180 / 40))          # = 2*a1*cos(radians(7.821°))
c  = a1²
c2 = b1 + c
c3 = -(c + b1 * c)
c4 = c²
c1 = (1 - b1 + c) * (1 - c) / 8
p[t] = (H[t] + L[t]) / 2
seed: butter[t] = p[t]  for the first 3 bars (t < 3)
butter[t] = c1*(p[t] + 3*p[t-1] + 3*p[t-2] + p[t-3])
          + c2*butter[t-1] + c3*butter[t-2] + c4*butter[t-3]
```
Baseline event signals (repo uses `bt.indicators.CrossOver(C, butter)`):
`base_up[t] = (C[t] > butter[t]) and (C[t-1] <= butter[t-1])`
`base_dn[t] = (C[t] < butter[t]) and (C[t-1] >= butter[t-1])`

### 3.2 Schaff Trend Cycle state (20/50/10/0.5) — from `custom_indicators.py:955-1006`, `BinaryGenerator.entry_indicator('schaff')`, `SignalFiller` (`custom_indicators.py:1007-1019`)

```
macd[t] = EMA(C, 20)[t] - EMA(C, 50)[t]
v1[t] = min(macd[t-9 … t]);  v2[t] = max(macd[t-9 … t]) - v1[t]
f1[t] = 100*(macd[t]-v1[t])/v2[t]      if v2[t] > 0 else f1[t-1]
pf[t] = pf[t-1] + 0.5*(f1[t] - pf[t-1])
v3[t] = min(pf[t-9 … t]);    v4[t] = max(pf[t-9 … t]) - v3[t]
f2[t] = 100*(pf[t]-v3[t])/v4[t]        if v4[t] > 0 else f2[t-1]
stc[t] = stc[t-1] + 0.5*(f2[t] - stc[t-1])
```
Binary state (SignalFiller semantics — last nonzero event persists):
`c1_state[t] = +1` if `stc[t-1] <= 25 and stc[t] > 25` (cross up through 25);
`= -1` if `stc[t-1] >= 75 and stc[t] < 75` (cross down through 75);
otherwise `c1_state[t] = c1_state[t-1]`, with `c1_state = 0` before the first event.

### 3.3 iTrend binary (period=30) — from `custom_indicators.py:37-68`, `BinaryGenerator.entry_indicator('itrend')`

```
a = 2 / (1 + 30)
seed: itrend[t] = (C[t] + 2*C[t-1] + C[t-2]) / 4   for t < 30
itrend[t] = (a - (a/2)²)*C[t] + (a²/2)*C[t-1] - (a - 3a²/4)*C[t-2]
          + 2*(1-a)*itrend[t-1] - (1-a)²*itrend[t-2]
trigger[t] = 2*itrend[t] - itrend[t-2]
c2_state[t] = +1 if trigger[t] > itrend[t];  -1 if trigger[t] < itrend[t];  0 if equal
```

### 3.4 Damiani Volatmeter gate — from `custom_indicators.py:1048-1093`, `BinaryGenerator.volume_indicator('damiani')`

```
aF[t] = WilderATR(13)[t];  aS[t] = WilderATR(40)[t]       # use inventory atr()
sF[t] = StdDev(C, 20)[t];  sS[t] = StdDev(C, 100)[t]      # population std (ddof=0)
v[t]  = aF[t]/aS[t] + 0.5*(v[t-1] - v[t-3])               # recursive lag suppression
        seed: v[t] = 0.005 for every bar before aS/sS are defined (first ~100 bars)
dv_t[t] = 1.4 - sF[t]/sS[t]
vol_f[t] = 1  if v[t] > dv_t[t]  else 0                   # "market active" gate
```
`vol_f` is a **directionless regime gate ∈ {0,1}**; it never takes negative values.

### 3.5 SSL channel state (period=20) — from `custom_indicators.py:226-252`

```
ma_hi[t] = WilderMA(H, 20)[t];  ma_lo[t] = WilderMA(L, 20)[t]   # repo mislabels these "hma"; they are Wilder smoothed MAs
ssl_state[t] = +1 if C[t] > ma_hi[t] else -1
```
Used by the original only as a signal exit; retained here for documentation (§10 #6).

### 3.6 Warm-up

IIR recursions (Butterworth 40-period, iTrend 30-period, Schaff EMA chains) converge from
their seeds only after several time constants; the Damiani gate is formally undefined for
~100 bars. **Declared warm-up: no OrderIntent may be emitted before the 150th completed D1
bar of each pair's series** (`warm_up_bars = 150`, a declared integer; covers max formal
minimum ≈ 100 for Damiani + recursion settling margin). See §10 #8.

## 4. Entry — long

At the close of D1 decision bar `t`, ALL of (conjunctive, no discretion):

1. `t ≥ warm_up_bars (150)` — the stack is out of warm-up.
2. `base_up[t]` is true — close crossed **up** through the Butterworth(40,3) baseline **on bar t** (crossover *event*, not state; §10 #1).
3. `c1_state[t] == +1` — Schaff Trend Cycle last crossed up through 25 and has not crossed down through 75 since.
4. `c2_state[t] == +1` — iTrend trigger above iTrend line.
5. `vol_f[t] == 1` — Damiani gate: market active.

- **entry type:** `market`
- **entry level:** none (market); fill per F2 at the open of bar t+1 plus F10 costs (1.0-pip spread, 0.5-pip slippage, entry only). The repo's cheat-on-close fill at `C[t]` is rejected — inexpressible under F1/F2 (§10 #3).
- **expires_after_bars:** null (market entries do not pend)
- **size_fraction:** 1.0 (r-multiple accounting only; §10 #9)
- **anchor for all geometry:** `A = C[t]` (decision-bar close, fully knowable at emission).
- One OrderIntent per qualifying bar; F12 concurrency default (1 open position per (strategy, pair, granularity)) prevents overlap — a fresh signal while a position is open is simply not admitted (§10 #5).

## 5. Entry — short

Mirror of §4, same decision bar `t`:

1. `t ≥ 150`.
2. `base_dn[t]` is true — close crossed **down** through the Butterworth baseline on bar t.
3. `c1_state[t] == -1`.
4. `c2_state[t] == -1`.
5. `vol_f[t] == 1` — **same directionless gate as longs**. The CSV prose "volume filter < 0"
   is a mirroring artifact: `vol_f ∈ {0,1}` has no negative state (§10 #2). Anchor `A = C[t]`,
   `market` entry, `expires_after_bars` null, `size_fraction` 1.0.

## 6. Stop

- **initial stop (long):** `StopRule.price = A - 1.5 * ATR14[t]` where `A = C[t]` and
  `ATR14[t]` is the inventory ATR(14) on D1 at completed bar t.
- **initial stop (short):** `StopRule.price = A + 1.5 * ATR14[t]`.
- **move_to_breakeven_on:** none (not mentioned in source).
- **trail (StopRule.trail_atr_multiple):** none — the trailing behaviour is expressed as the
  TRAIL exit leg (§7). The initial stop governs the whole position from entry; the trail
  ratchets only in the favourable direction and never widens (F9), so the effective stop is
  `max(initial stop, trailing stop)` for longs (mirror for shorts).
- **Trail definition (TRAIL leg):** for longs, at each completed D1 bar `k ≥ t`:
  `trail[k] = max(trail[k-1], C[k] - 1.5 * ATR14[k])`, seeded `trail[t] = A - 1.5*ATR14[t]`
  (i.e. the trail starts from the initial stop level at entry, F9 contract reading — §10 #4).
  Updates occur only at completed **D1** closes (the strategy sees no H1 data); between D1
  closes the level is static and is resolved against H1 bars per §3.2/F5/F6. Mirror for shorts.

## 7. Exit legs

Fractions sum to 1.0. Levels are absolute prices declarable at emission from anchor `A = C[t]`.

| Label | Fraction | Kind | Level formula (long; mirror for short) |
|---|--:|---|---|
| TP1 | 0.5 | take_profit | `price = A + 3.0 * ATR14[t]` |
| TRAIL | 0.5 | trailing | `atr_multiple = 1.5` on D1 ATR(14), updated at completed D1 closes per §6 |

- **Signal exits REJECTED (inexpressible):** the CSV's "SSL exit indicator flip closes the
  trade early" and the pseudocode's `exit = ssl_flip | opposite_signal` (repo `nnfx.py:430-441`
  closes the position when **any** of SSL/baseline/C1/C2 flips against the position) have no
  contract-v2 mechanism: there is no close-on-signal OrderIntent, and the strategy never
  observes fills or positions. The position therefore runs to stop, TP1+trail, or END_OF_DATA
  (F11). This is the largest single divergence from the original; consequences in §11 and
  §10 #6.

## 8. Filters

| Filter | Timeframe | Definition | Knowable when |
|---|---|---|---|
| Warm-up gate | D1 | bar index ≥ 150 | trivially, at bar count |
| Damiani volatility/volume gate | D1 | `vol_f[t] == 1` required for BOTH directions | at close of decision bar t |
| One-position-per-pair | engine | F12 default `max_concurrent_positions = 1` per (strategy, pair, D1) | engine-enforced |
| Session/news/time-of-day | — | none (D1 swing strategy; source has none) | — |

- **Cost model:** F10 governs (1.0-pip spread, 0.5-pip entry slippage, 0 commission). The repo
  instead models a **fixed 2-pip spread per pair** plus 0.01 % open slippage
  (`nnfx.py:89,449`). The per-pair spread is a fixed scheme, not a real spread series, so no
  data gap — but results will be ~1 pip/trade cheaper than the author's own runs (§10 #7).
- **Sizing out of scope:** "2 % equity risk per trade", "leverage capped at 20", and per-pair
  pip-value maths are System-3 concerns; System 1 emits r-multiples only (`size_fraction=1.0`).
  Recorded, not implemented (§10 #9).

## 9. Causality audit

This strategy uses **no swing points, ZigZag, pivots, or fractals** — the banned
`detect_swing_points` class of bug does not apply. All recursions are causal IIR filters.

| Rule | Inputs | Fully known at |
|---|---|---|
| Butterworth baseline & cross event | `H/L/C` of bars ≤ t; recursion state from bars < t | close of bar t (event defined by t vs t−1, both completed) |
| Schaff `c1_state` | EMA chains and 10-bar min/max windows over bars ≤ t; state machine from history | close of bar t. Confirmation lag of a *cross event*: 1 bar by construction (needs `stc[t]` vs `stc[t-1]`); the *state* then persists |
| iTrend `c2_state` | `C` of bars ≤ t, `itrend[t-2]` | close of bar t |
| Damiani `vol_f` | ATR(13)/ATR(40), StdDev(20)/StdDev(100) over bars ≤ t, recursive `v[t-1], v[t-3]` | close of bar t; formally undefined for first ~100 bars (warm-up gate covers this) |
| ATR(14) stop/TP geometry | bars ≤ t | close of bar t; anchored to `C[t]`, so every level in the OrderIntent is an absolute number at emission (fleet rule 8 satisfied) |
| MTF causality | none — single timeframe. H1 is used **only** for fill resolution (Part D); the strategy never reads H1 | n/a |
| Order admission | OrderIntent with `decision_bar = t` is admitted per §3.2 step 6 and fills from bar t+1 (F1/F2) | t+1 onward |

## 10. Ambiguities resolved

| # | Ambiguity | Conservative reading taken | Alternative rejected |
|--:|---|---|---|
| 1 | "baseline signal > 0 (price above bullish baseline)" — state-above vs crossover event | **Crossover event** (`CrossOver(C, butter)`, repo-faithful): the trigger fires only on the bar the close crosses the baseline; far fewer, later entries | State reading (`C > butter` persisting) — matches the CSV parenthetical but produces repeated entries on every bar of agreement and contradicts the author's code |
| 2 | Short gate "volume filter < 0" — Damiani `vol_f ∈ {0,1}` can never be < 0 (source bug: in the repo, direct short entries are impossible; shorts occur only via the continuation path) | **Symmetric regime gate**: `vol_f == 1` required for both directions — the NNFX "volume/volatility indicator" is directionless ("market active, not flat") | Literal `< 0` reading: transcribes the bug and makes §5 dead code, backtesting a different (long-only) strategy. Flagged: the taken reading produces *more* short trades than the buggy original; reviewer may flip to literal if bug-fidelity is preferred |
| 3 | Fill/anchor timing: repo fills at the signal bar's close (Backtrader `set_coc=True`) and sets SL/TP from that close | Decision-bar-close anchor `A = C[t]`, fill at open of t+1 + costs (F1/F2/F10). Declared R = 1.5×ATR; realised R ≠ declared R when the t+1 open gaps (F3/F6 resolve honestly) | Cheat-on-close fill at `C[t]` — inexpressible under F1/F2 |
| 4 | Trail start: repo initiates the StopTrail only **after TP1 fills**, at the TP fill event, `trailamount = 1.5×ATR` | Contract-native: TRAIL leg ratchets from entry (`trail[t]` seeded at the initial stop) at completed D1 closes, F9 | Fill-triggered trail start — depends on observing a fill event, inexpressible in the declarative contract. Taken reading tightens the stop earlier → earlier exits on the runner → conservative for a trend system |
| 5 | Repo entry refinements absent from the CSV prose: `pullback()` "too far from baseline" block (>1×ATR from baseline at cross), `bridge_too_far()` block (C1 flip >7 bars stale), and `continuation()` extra entry path (double C1 flip with C2 agreement when no fresh baseline cross) | **Excluded** — the spec implements the CSV row as written (conjunctive 4-filter entry). Including pullback/bridge would *reduce* trades but changes the strategy beyond the source row; continuation would *add* entries | Implementing the repo refinements — documented here so a reviewer can promote them to §8 filters in a follow-up variant |
| 6 | SSL-flip and opposite-signal exits | Inexpressible (no close-on-signal mechanism); replaced by SL/TP1/TRAIL only (§7) | Any proxy (e.g. time-stop after SSL flip) — invents rules not in the source |
| 7 | Cost model: repo's fixed 2-pip spread + 0.01 % open slippage vs contract F10 (1.0 + 0.5 pip) | F10 governs (inviolable; matches live cost model). Results ≈ 1 pip/trade cheaper than author's own runs — stated, not adjusted | Modelling a 2-pip spread — would break comparability with the other 50 strategies and violates F10 |
| 8 | Warm-up length for the IIR stack (not stated in source) | Declared `warm_up_bars = 150` D1 bars per pair (≥ Damiani's 100-bar formal minimum + convergence margin for Butterworth/iTrend/EMA chains) | Emitting signals as soon as formally defined (~bar 100–110) — lets unconverged IIR seeds generate entries; or whole-frame indicator initialisation (look-ahead-adjacent, banned by truncation probe) |
| 9 | "2% equity risk per trade; leverage capped at 20; spread commission per pair" | Out of scope — System 1 never sizes; `size_fraction = 1.0`, r-multiples only | Any equity-based sizing — violates contract §2.2/§10 ("No position sizing") |
| 10 | Concurrency: repo blocks new entries globally while ANY pair has an open position (`nnfx.py:344`); CSV says "one position per pair" | CSV reading + F12 default: max 1 open position per (strategy, pair, D1); cross-pair overlap allowed. The strategy cannot observe positions, so a global lock is inexpressible — flagged: results will show *more* concurrent trades than the author's code | Global one-position lock — inexpressible in contract v2 metadata |
| 11 | ATR flavour inside Damiani (Backtrader default = Wilder smoothed) vs inventory `atr` | Inventory `atr(high, low, close, period)` used for both stops and Damiani (Wilder-compatible); ddof=0 for StdDev (ratio is insensitive) | Reimplementing exact Backtrader internals — no measurable difference at these periods |

## 11. Expected behaviour

- **Trade frequency:** low. A 40-period Butterworth on D1 crosses price a handful of times
  per year per pair; requiring C1+C2+volatility agreement at the cross bar cuts that
  further. Expect roughly **2–6 entries per pair per year** (both directions), i.e. of the
  order of **10–30 trades/year across the 5 live pairs**, ~40–120 trades per pair over the
  ~20-year D1 history. First signals arrive ~7 months into each series (150-bar warm-up).
- **What would make it fail the gates:** (a) thin per-cell trade counts — 6-month OOS folds
  may hold 0–3 trades, inviting `low_confidence`; (b) the exit substitution — the original
  exits on *any* indicator flip (usually long before a 1.5-ATR stop or 3.0-ATR target), so
  the contract version runs a materially different, wider-risk 1:2-bracket-with-runner
  profile; if the flip-exit was carrying the edge, this implementation measures something
  weaker; (c) regime dependence — the Damiani gate keeps it out of flat markets, so results
  will concentrate in trending years and may fail pooled OOS consistency.
- **Is the author's MODERATE conviction justified by the rules as written?** Cautiously yes
  for the *signal stack* — all five indicators are author-specified here from the author's
  own code (no reconstruction risk), the entry is fully conjunctive with zero discretion,
  and the NNFX methodology is widely documented. Two real caveats stand: (1) the repo posts
  **no verified backtest metrics**, and its parameters visibly carry pair-specific tuning
  (it ships trading EURUSD only); (2) the inexpressible SSL/opposite-signal exit means our
  backtest measures a bracket-and-trail variant of NNFX, not the author's trade management.
  Treat a passing result as evidence for the *entry stack*, not for the full NNFX method.
