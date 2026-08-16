from typing import List, Mapping, Sequence
import numpy as np
import pandas as pd

from ..contract_v2 import (
    GRANULARITY_INTERVAL,
    ExitLeg,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
)
from ...data_access.indicators import ema, rsi


class SmartMoneySwing(StrategyV2):
    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="smart_money_swing",
            name="Smart Money Swing Strategy",
            version="0.1.0",
            author="n5-fleet",
            hypothesis="In an established trend (fast EMA above slow EMA on the swing frame, confirmed one timeframe higher by price above its EMA50, RSI above midline, and a rising EMA50), a shallow pullback that stalls inside the EMA20–EMA50 corridor and is then reclaimed by a close back above EMA20 marks the point where counter-trend profit-taking is exhausted and trend-following flow resumes; entering there, with the stop under the recent 10-bar extreme, buys trend continuation at a locally favourable price. The edge should persist because it monetises two durable behavioural patterns: herd re-entry by trend traders who sat out the pullback (the reclaim cross is their trigger too) and the liquidation of weak counter-trend positions when the corridor holds, while the higher-timeframe gate filters out the range regimes where EMA pullbacks are noise.",
            granularities=["H1", "H4", "D1"],
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="H4",
            context_granularities=("H4", "D1", "W1"),
            simulate_on="H1",
            source_row=17,
            source_url="https://www.tradingview.com/script/q3yuMvq5-Smart-Money-Swing-Strategy-All-in-One/",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["ema", "rsi", "atr"]

    @property
    def warmup_bars(self) -> int:
        return 200

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        primary_name = self.metadata.primary_granularity
        primary = frames[primary_name]

        ctx_map = {"H1": "H4", "H4": "D1", "D1": "W1"}
        ctx_name = ctx_map.get(primary_name, "D1")

        if ctx_name == "W1" and "W1" not in frames and "D1" in frames:
            # Derive W1 context causally from D1
            d1 = frames["D1"]
            # Week starts Sun 21:00. D1 bars open at 21:00 UTC. Shift to match Monday 00:00 for resampling, then shift back.
            d1_shift = d1.shift(freq="3h")
            ctx_closed = (
                d1_shift.resample("W-MON", closed="right", label="left")
                .last()
                .shift(freq="-3h")
                .dropna()
            )

            ctx = pd.DataFrame(index=ctx_closed.index)
            ctx["Close"] = ctx_closed["Close"]
        else:
            ctx = frames[ctx_name]

        ema20 = ema(primary["Close"], 20)
        ema50 = ema(primary["Close"], 50)
        rsi14 = rsi(primary["Close"], 14)

        lowest_10 = primary["Low"].rolling(10).min()
        highest_10 = primary["High"].rolling(10).max()

        ctx_ema50 = ema(ctx["Close"], 50)
        ctx_rsi14 = rsi(ctx["Close"], 14)
        ctx_ema50_slope = ctx_ema50 - ctx_ema50.shift(5)

        ctx_indicators = pd.DataFrame(
            {
                "close": ctx["Close"],
                "ema50": ctx_ema50,
                "rsi14": ctx_rsi14,
                "ema50_slope": ctx_ema50_slope,
            },
            index=ctx.index,
        )

        interval = (
            pd.Timedelta(weeks=1)
            if ctx_name == "W1"
            else GRANULARITY_INTERVAL[ctx_name]
        )

        ctx_at_close = ctx_indicators.copy()
        ctx_at_close.index = ctx_at_close.index + interval

        joined_ctx = pd.merge_asof(
            pd.DataFrame(index=primary.index),
            ctx_at_close,
            left_index=True,
            right_index=True,
            direction="backward",
        )

        close = primary["Close"].to_numpy(dtype=float)
        ema20_arr = ema20.to_numpy(dtype=float)
        ema50_arr = ema50.to_numpy(dtype=float)
        rsi14_arr = rsi14.to_numpy(dtype=float)
        lowest_10_arr = lowest_10.to_numpy(dtype=float)
        highest_10_arr = highest_10.to_numpy(dtype=float)

        j_close = joined_ctx["close"].to_numpy(dtype=float)
        j_ema50 = joined_ctx["ema50"].to_numpy(dtype=float)
        j_rsi14 = joined_ctx["rsi14"].to_numpy(dtype=float)
        j_ema50_slope = joined_ctx["ema50_slope"].to_numpy(dtype=float)

        orders: List[OrderIntent] = []

        for i in range(self.warmup_bars, len(primary)):
            if np.isnan(ema20_arr[i - 1]) or np.isnan(ema50_arr[i - 1]):
                continue
            if (
                np.isnan(j_ema50[i])
                or np.isnan(j_rsi14[i])
                or np.isnan(j_ema50_slope[i])
            ):
                continue

            long_trend = ema20_arr[i] > ema50_arr[i]
            long_pullback = ema50_arr[i - 1] < close[i - 1] < ema20_arr[i - 1]
            long_cross = (close[i] > ema20_arr[i]) and (
                close[i - 1] <= ema20_arr[i - 1]
            )
            long_rsi = 40 <= rsi14_arr[i] <= 60
            long_htf = (
                (j_close[i] > j_ema50[i])
                and (j_rsi14[i] > 50)
                and (j_ema50_slope[i] > 0)
            )

            if long_trend and long_pullback and long_cross and long_rsi and long_htf:
                stop_price = float(lowest_10_arr[i])
                r = abs(close[i] - stop_price)
                if r > 0:
                    orders.append(
                        OrderIntent(
                            decision_bar=primary.index[i],
                            direction=1,
                            entry="market",
                            entry_price=None,
                            decision_close=float(close[i]),
                            stop=StopRule(
                                price=stop_price,
                                move_to_breakeven_on="TP1",
                                breakeven_offset_pips=0.0,
                                trail_atr_multiple=2.0,
                            ),
                            exits=[
                                ExitLeg(
                                    fraction=0.5,
                                    kind="take_profit",
                                    price=close[i] + 1.0 * r,
                                    label="TP1",
                                ),
                                ExitLeg(
                                    fraction=0.5,
                                    kind="take_profit",
                                    price=close[i] + 2.0 * r,
                                    label="TP2",
                                ),
                            ],
                            expires_after_bars=None,
                            tag="smart_money_swing",
                        )
                    )
                continue

            short_trend = ema20_arr[i] < ema50_arr[i]
            short_pullback = ema20_arr[i - 1] < close[i - 1] < ema50_arr[i - 1]
            short_cross = (close[i] < ema20_arr[i]) and (
                close[i - 1] >= ema20_arr[i - 1]
            )
            short_rsi = 40 <= rsi14_arr[i] <= 60
            short_htf = (
                (j_close[i] < j_ema50[i])
                and (j_rsi14[i] < 50)
                and (j_ema50_slope[i] < 0)
            )

            if (
                short_trend
                and short_pullback
                and short_cross
                and short_rsi
                and short_htf
            ):
                stop_price = float(highest_10_arr[i])
                r = abs(close[i] - stop_price)
                if r > 0:
                    orders.append(
                        OrderIntent(
                            decision_bar=primary.index[i],
                            direction=-1,
                            entry="market",
                            entry_price=None,
                            decision_close=float(close[i]),
                            stop=StopRule(
                                price=stop_price,
                                move_to_breakeven_on="TP1",
                                breakeven_offset_pips=0.0,
                                trail_atr_multiple=2.0,
                            ),
                            exits=[
                                ExitLeg(
                                    fraction=0.5,
                                    kind="take_profit",
                                    price=close[i] - 1.0 * r,
                                    label="TP1",
                                ),
                                ExitLeg(
                                    fraction=0.5,
                                    kind="take_profit",
                                    price=close[i] - 2.0 * r,
                                    label="TP2",
                                ),
                            ],
                            expires_after_bars=None,
                            tag="smart_money_swing",
                        )
                    )

        return orders
