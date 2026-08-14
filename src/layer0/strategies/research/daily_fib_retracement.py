"""Gp's simple daily Fibonacci retracement system — SPEC-daily_fib_retracement (row 16).

Decisions are taken at the close of every fully-closed D1 bar `k`; fills, stops and
exit legs are resolved by the engine on H1 bars. There is **no context frame** (spec
§2: `context_granularities: none`), so `closed_context_frame` / `merge_asof` do not
appear here — the trend filter is an EMA on the D1 decision frame itself, and the
Fibonacci anchor is bar `k`'s own High/Low, which is fully closed when it is read
(spec §3, §9, §10 #1). No `causal_structure` helper is needed: the author's "swing
high/low" *is* the previous day's high/low, so the confirmation lag is one D1 bar and
is already absorbed by acting from bar k+1.

Every level is pure arithmetic on bar `k`'s OHLC (spec §3, §4, §5, §6, §7):

    rng  = High[k] - Low[k]
    long : entry = High[k] - 0.618*rng   stop = High[k] - 0.750*rng
           TP_382 = High[k] - 0.382*rng
    short: entry = Low[k]  + 0.618*rng   stop = Low[k]  + 0.750*rng
           TP_382 = Low[k]  + 0.382*rng

-- NOTE A: the one place the spec is internally inconsistent -------------------
Spec §4.3 states the long zone precondition as

    Low[k] <= High[k] - 0.50*rng[k]   AND   Low[k] >= High[k] - 0.618*rng[k]

but the Fibonacci anchor (§3, §9, §10 #1) is bar k's OWN range, so bar k's Low *is*
the 100% retracement of that range. Substituting rng = High - Low:

    Low <= High - 0.50*rng    <=>  0.5*Low   <= 0.5*High     (vacuously true)
    Low >= High - 0.618*rng   <=>  0.382*Low >= 0.382*High   <=>  Low >= High

The second inequality holds only when rng <= 0, which §4.1 forbids. The short mirror
in §5.3 collapses identically (`High <= Low + 0.618*rng`  <=>  High <= Low). Taken
literally the strategy can never fire on any bar — which also means
`assert_no_lookahead_v2` rejects it outright ("emits no orders anywhere").

Repair used here — the reading the spec's own §11 states in prose: *"the zone
precondition (price must already sit in the 50-61.8% band **at the daily close**, in
an EMA50 trend)"*. Band membership is therefore tested on `Close[k]`, against the
identical levels and the identical inclusive bounds §4.3/§5.3 give:

    long : High[k] - 0.618*rng <= Close[k] <= High[k] - 0.50*rng
    short: Low[k]  + 0.50*rng  <= Close[k] <= Low[k]  + 0.618*rng

No level formula, parameter, fraction or anchor is changed; only the *price* the band
test reads (Low/High -> Close) differs from the literal §4.3/§5.3, and only because
the literal form is unsatisfiable. Two alternative repairs were rejected and are
listed in REPORT-daily_fib_retracement.md under Deviations/Uncertainties:
(a) dropping the impossible bound, which places an order on every trend day — the
    prose-only reading §10 #3 explicitly rejects;
(b) re-anchoring the fib to bar k-1 so that `Low[k]`/`High[k]` survive verbatim
    (this is what the CSV pseudocode's `prev = ...shift()` does) — rejected because
    it re-opens §10 #1, which fixes the anchor at the last fully-closed bar k, and
    because §6/§7/§9 index every level to rng[k].
This is the strategy's single load-bearing interpretation.

-- NOTE B: pending entries and the decision-bar close -------------------------
`buy_limit` must sit BELOW the decision close and `sell_limit` ABOVE it, or the
intent is an instant fill in disguise and the contract rejects it. The band test
above already implies the correct side except at exact equality (Close[k] sitting
precisely on the 61.8% level), so such a bar is SKIPPED rather than having its level
nudged into legality.

-- NOTE C: what the trailing leg does and does not carry ----------------------
The ATR(14) of §3 is the distance *unit* of the TRAIL leg only. `ExitLeg(kind=
"trailing")` accepts an `atr_multiple`, never a price, so the ATR value itself is
resolved by the engine at bar closes per F9; the strategy declares 1.5 and nothing
else. `StopRule.trail_atr_multiple` stays None (§6): the initial stop is static at
the 75% retracement and moves only to breakeven, on TP_382, at that bar's close (F8).

**Reported, not worked around:** `position_engine` rejects any intent carrying a
fractional `ExitLeg(kind="trailing")` with `TRAILING_LEG_UNSUPPORTED`, so the exit
structure spec §7 mandates cannot currently be simulated. The contract accepts it,
the engine does not. Fixing that is a shared-file change and therefore the reviewer's
call (fleet hard rule 3); see the report.
"""

from __future__ import annotations

from typing import List, Mapping, Sequence

import pandas as pd

from ..contract_v2 import (
    Direction,
    EntryKind,
    ExitLeg,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
)
from ...data_access.indicators import ema


class DailyFibRetracement(StrategyV2):
    """Buy/sell the 61.8% retracement of the prior D1 range, in the D1 EMA trend."""

    TREND_PERIOD = 50  # D1 EMA defining the trend (spec §3)
    ATR_PERIOD = 14  # D1 ATR(14) — the TRAIL leg's unit (spec §3, NOTE C)
    FIB_TP = 0.382  # TP_382 level (spec §7)
    FIB_ZONE_EDGE = 0.50  # shallow edge of the retracement band (§4.3/§5.3)
    FIB_ENTRY = 0.618  # deep edge of the band = the limit price (§4/§5)
    FIB_STOP = 0.75  # fixed structural stop (§6)
    TRAIL_ATR_MULTIPLE = 1.5  # TRAIL leg distance (§7)
    TP_FRACTION = 0.5  # TP_382 leg fraction (§7)
    TRAIL_FRACTION = 0.5  # TRAIL leg fraction (§7); 0.5 + 0.5 = 1.0
    EXPIRY_BARS = 24  # pending-order lifetime, H1 resolution bars (§4, §10 #7)

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="daily_fib_retracement",
            name="Daily Fibonacci Retracement (Gp's simple daily fib system)",
            version="0.1.0",
            author="wave2-fleet",
            hypothesis=(
                "In an established daily trend, the prior day's full range is a "
                "self-anchoring liquidity map: price very often retraces into the "
                "50-61.8% band of that range during the next session (yesterday's "
                "breakout participants take profit, late entrants get squeezed, and "
                "resting limit orders cluster at round retracement levels), so a "
                "patient limit order in that band buys a pullback at a structurally "
                "favourable price with a tightly defined invalidation (75% retrace), "
                "letting the trend leg that follows pay for a high stop-out rate. "
                "The claimed persistence is behavioural — mean-reverting intraday "
                "flow within trending weeks — not informational."
            ),
            granularities=["D1"],
            # Spec §2 pairs_available: the five live pairs only. The Wave-1
            # additions are marked *pending*, so they are deliberately not declared.
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="D1",
            context_granularities=(),
            simulate_on="H1",
            source_row=16,
            source_url=(
                "https://www.forexfactory.com/thread/"
                "530477-gps-simple-daily-fibonacci-based-system"
            ),
        )

    @property
    def required_indicators(self) -> List[str]:
        # "atr" is declared because the TRAIL leg is denominated in D1 ATR(14)
        # (spec §3/§7); the engine resolves that value, see NOTE C.
        return ["ema", "atr"]

    @property
    def warmup_bars(self) -> int:
        # Two full spans of the slowest lookback: the EMA50 needs ~2x its period to
        # settle, and ATR(14) is warm long before that. The spec states no warmup.
        return 2 * max(self.TREND_PERIOD, self.ATR_PERIOD)

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        d1 = frames["D1"]

        high = d1["High"].to_numpy(dtype=float)
        low = d1["Low"].to_numpy(dtype=float)
        close = d1["Close"].to_numpy(dtype=float)
        # ewm(adjust=False) is strictly trailing: EMA[i] depends on closes <= i.
        trend_ema = ema(d1["Close"], self.TREND_PERIOD).to_numpy(dtype=float)
        index = d1.index

        orders: List[OrderIntent] = []
        for i in range(self.warmup_bars, len(d1)):
            hi = float(high[i])
            lo = float(low[i])
            c = float(close[i])
            rng = hi - lo

            # §4.1 / §5.1 — non-degenerate day. A NaN bar fails this too.
            if not rng > 0.0:
                continue

            direction: Direction
            entry_kind: EntryKind
            if c > trend_ema[i]:
                # §4.2 uptrend. §4.3 zone precondition, on the close (NOTE A).
                direction = 1
                entry_kind = "buy_limit"
                band_shallow = hi - self.FIB_ZONE_EDGE * rng
                band_deep = hi - self.FIB_ENTRY * rng
                if not band_deep <= c <= band_shallow:
                    continue
                entry = band_deep  # §4 entry level = the 61.8% retracement
                stop = hi - self.FIB_STOP * rng  # §6
                take_profit = hi - self.FIB_TP * rng  # §7
            elif c < trend_ema[i]:
                # §5.2 downtrend, exact mirror. §5.3 zone precondition.
                direction = -1
                entry_kind = "sell_limit"
                band_shallow = lo + self.FIB_ZONE_EDGE * rng
                band_deep = lo + self.FIB_ENTRY * rng
                if not band_shallow <= c <= band_deep:
                    continue
                entry = band_deep  # §5 entry level = the 61.8% retracement
                stop = lo + self.FIB_STOP * rng  # §6
                take_profit = lo + self.FIB_TP * rng  # §7
            else:
                # Close exactly on the EMA (or a NaN EMA): neither §4.2 nor §5.2.
                continue

            # NOTE B — the limit must be on the far side of the decision close.
            if direction * (c - entry) <= 0.0:
                continue

            orders.append(
                OrderIntent(
                    decision_bar=index[i],
                    direction=direction,
                    entry=entry_kind,
                    entry_price=entry,
                    decision_close=c,
                    stop=StopRule(
                        price=stop,
                        move_to_breakeven_on="TP_382",  # §6; the label exists below
                        breakeven_offset_pips=0.0,
                        trail_atr_multiple=None,  # §6 — the stop itself never trails
                    ),
                    exits=[
                        ExitLeg(
                            fraction=self.TP_FRACTION,
                            kind="take_profit",
                            price=take_profit,
                            label="TP_382",
                        ),
                        ExitLeg(
                            fraction=self.TRAIL_FRACTION,
                            kind="trailing",
                            atr_multiple=self.TRAIL_ATR_MULTIPLE,
                            label="TRAIL",
                        ),
                    ],
                    expires_after_bars=self.EXPIRY_BARS,
                    size_fraction=1.0,
                    tag="daily_fib",
                    strategy_id=self.strategy_id,
                )
            )
        return orders
