"""Strategy: PSAR GBPJPY Daily."""

from __future__ import annotations

from typing import List, Mapping, Sequence, Tuple

import numpy as np
import pandas as pd

from ..contract_v2 import ExitLeg, OrderIntent, StopRule, StrategyMetadataV2, StrategyV2
from ...data_access.indicators import atr


def _psar_custom(
    high: np.ndarray, low: np.ndarray, close: np.ndarray
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Returns (dir_entering, dir_out, sar_out) for custom PSAR logic."""
    n = len(close)
    dir_out = np.full(n, np.nan)
    sar_out = np.full(n, np.nan)
    dir_entering = np.full(n, np.nan)

    if n < 2:
        return dir_entering, dir_out, sar_out

    # Initialization at bar index 1
    dir_1 = 1.0 if close[1] >= close[0] else -1.0
    sar_1 = float(low[0]) if dir_1 == 1.0 else float(high[0])
    ep_1 = float(high[1]) if dir_1 == 1.0 else float(low[1])
    af_1 = 0.05

    curr_dir = dir_1
    curr_sar = sar_1
    curr_ep = ep_1
    curr_af = af_1

    dir_out[1] = curr_dir
    sar_out[1] = curr_sar

    for t in range(2, n):
        dir_entering[t] = curr_dir

        is_reversal = False
        if curr_dir == 1.0 and low[t] < curr_sar:
            is_reversal = True
        elif curr_dir == -1.0 and high[t] > curr_sar:
            is_reversal = True

        if is_reversal:
            if curr_dir == 1.0:
                curr_dir = -1.0
                next_sar = curr_ep
                curr_ep = float(low[t])
                curr_af = 0.05
                curr_sar = next_sar
            else:
                curr_dir = 1.0
                next_sar = curr_ep
                curr_ep = float(high[t])
                curr_af = 0.05
                curr_sar = next_sar
        else:
            if curr_dir == 1.0 and high[t] > curr_ep:
                curr_ep = float(high[t])
                curr_af = min(curr_af + 0.075, 1.0)
            elif curr_dir == -1.0 and low[t] < curr_ep:
                curr_ep = float(low[t])
                curr_af = min(curr_af + 0.075, 1.0)

            sar_star = curr_sar + curr_af * (curr_ep - curr_sar)
            if curr_dir == 1.0:
                curr_sar = min(sar_star, float(low[t]), float(low[t - 1]))
            else:
                curr_sar = max(sar_star, float(high[t]), float(high[t - 1]))

        dir_out[t] = curr_dir
        sar_out[t] = curr_sar

    return dir_entering, dir_out, sar_out


class PsarGbpjpyDaily(StrategyV2):
    """GBP/JPY daily trends persist for weeks at a time."""

    ATR_PERIOD = 14
    TIME_EXIT_BARS = 126
    TRAIL_ATR_MULTIPLE = 2.0

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="psar_gbpjpy_daily",
            name="PSAR GBPJPY Daily",
            version="0.1.0",
            author="n5-fleet",
            hypothesis=(
                "GBP/JPY daily trends persist for weeks at a time because they are "
                "driven by slow-moving macro forces — BoJ vs. BoE policy differentials "
                "and broad risk-on/risk-off flows — which do not reverse day-to-day; "
                "an accelerating trailing stop (Wilder's Parabolic SAR with a fast AF "
                "cap of 1.0) keeps the position alive through ordinary daily noise yet "
                "locks in profit progressively as the trend matures, harvesting the fat "
                "middle of sustained JPY-cross trends while self-limiting the damage "
                "from the whipsaw that ranging regimes inflict on any trend-follower."
            ),
            granularities=["D1"],
            pairs=["GBP_JPY"],
            primary_granularity="D1",
            context_granularities=(),
            simulate_on="H1",
            source_row=21,
            source_url="https://www.tradingview.com/script/Ky2dfFEn-Parabolic-SAR-Swing-strategy-GBP-JPY-Daily-timeframe/",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["atr"]

    @property
    def warmup_bars(self) -> int:
        return 20

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        d1 = frames["D1"]

        high = d1["High"].to_numpy(dtype=float)
        low = d1["Low"].to_numpy(dtype=float)
        close = d1["Close"].to_numpy(dtype=float)

        dir_entering, dir_out, sar_out = _psar_custom(high, low, close)

        atr_series = atr(
            d1["High"],
            d1["Low"],
            d1["Close"],
            period=(
                self.ATR_ATR_PERIOD
                if hasattr(self, "ATR_ATR_PERIOD")
                else self.ATR_PERIOD
            ),
        )
        atr_values = atr_series.to_numpy(dtype=float)

        orders: List[OrderIntent] = []

        for t in range(self.warmup_bars, len(d1)):
            if (
                np.isnan(dir_entering[t])
                or np.isnan(dir_out[t])
                or np.isnan(sar_out[t])
            ):
                continue
            if np.isnan(atr_values[t]):
                continue

            # Long entry condition
            if dir_entering[t] == -1.0 and dir_out[t] == 1.0:
                orders.append(
                    OrderIntent(
                        decision_bar=d1.index[t],
                        direction=1,
                        entry="market",
                        entry_price=None,
                        stop=StopRule(
                            price=float(sar_out[t]),
                            move_to_breakeven_on=None,
                            trail_atr_multiple=self.TRAIL_ATR_MULTIPLE,
                        ),
                        exits=[
                            ExitLeg(
                                fraction=1.0,
                                kind="time",
                                bars=self.TIME_EXIT_BARS,
                                label="time-backstop",
                            )
                        ],
                        expires_after_bars=None,
                        tag="psar_long",
                        strategy_id=self.strategy_id,
                    )
                )

            # Short entry condition
            elif dir_entering[t] == 1.0 and dir_out[t] == -1.0:
                orders.append(
                    OrderIntent(
                        decision_bar=d1.index[t],
                        direction=-1,
                        entry="market",
                        entry_price=None,
                        stop=StopRule(
                            price=float(sar_out[t]),
                            move_to_breakeven_on=None,
                            trail_atr_multiple=self.TRAIL_ATR_MULTIPLE,
                        ),
                        exits=[
                            ExitLeg(
                                fraction=1.0,
                                kind="time",
                                bars=self.TIME_EXIT_BARS,
                                label="time-backstop",
                            )
                        ],
                        expires_after_bars=None,
                        tag="psar_short",
                        strategy_id=self.strategy_id,
                    )
                )

        return orders
