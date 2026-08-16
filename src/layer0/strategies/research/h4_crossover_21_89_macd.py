import numpy as np
import pandas as pd
from typing import List, Mapping, Sequence

from ..contract_v2 import (
    GRANULARITY_INTERVAL,
    ExitLeg,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
)
from ...data_access.indicators import get_pip_value, ema, sma, macd
from pandas.tseries.holiday import (
    AbstractHolidayCalendar,
    Holiday,
    USMartinLutherKingJr,
    USPresidentsDay,
    USMemorialDay,
    USLaborDay,
    USColumbusDay,
    USThanksgivingDay,
)


class USFederalCalendar(AbstractHolidayCalendar):
    rules = [
        Holiday("New Years Day", month=1, day=1),
        USMartinLutherKingJr,
        USPresidentsDay,
        USMemorialDay,
        Holiday("Juneteenth", month=6, day=19),
        Holiday("Independence Day", month=7, day=4),
        USLaborDay,
        USColumbusDay,
        Holiday("Veterans Day", month=11, day=11),
        USThanksgivingDay,
        Holiday("Christmas", month=12, day=25),
    ]


class H4Crossover2189Macd(StrategyV2):
    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="h4_crossover_21_89_macd",
            name="H4 Crossover 21/89 MACD",
            version="0.1.0",
            author="n5-fleet",
            hypothesis=(
                "A 21-EMA / 89-SMA cross on H4 marks a regime change in the dominant "
                "multi-day trend; the first pullback after the cross (visible as the MACD "
                "histogram flipping against the new trend) is profit-taking by early entrants, "
                "and the histogram's first flip BACK to trend colour marks the resumption of that "
                "regime. Entering on resumption — rather than at the cross itself — buys the "
                "new trend at a pullback price with momentum re-confirming. The edge should "
                "persist because FX trends are driven by slow-moving macro and rate-differential "
                "flows that do not reverse in days, while pullbacks are behavioural (profit-taking, "
                "late-entry fades) and therefore temporary; the moving-average pair and histogram "
                'are just a mechanical proxy for "regime changed, pause over." Stops anchored to '
                "D1 structure (the extreme of the prior substantial move) sit beyond the noise "
                "band of the new trend, so ordinary pullbacks do not stop the position out."
            ),
            granularities=["H4", "D1"],
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="H4",
            context_granularities=("D1",),
            simulate_on="H1",
            source_row=13,
            source_url="https://www.forexfactory.com/thread/264293-4h-crossover-swing-trading",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["ema", "sma", "macd"]

    EMA_PERIOD = 21
    SMA_PERIOD = 89
    MACD_FAST = 12
    MACD_SLOW = 26
    MACD_SIGNAL = 9
    D1_PERIOD = 20

    @property
    def warmup_bars(self) -> int:
        # Enough for SMA and D1 bars
        return max(self.SMA_PERIOD, self.D1_PERIOD * 6) + 10

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        h4 = frames["H4"]
        d1 = frames["D1"]
        pip = float(get_pip_value(self.metadata.pairs[0]))

        d1_low_min = d1["Low"].rolling(self.D1_PERIOD).min()
        d1_high_max = d1["High"].rolling(self.D1_PERIOD).max()

        d1_at_close = pd.DataFrame(
            {
                "d1_min_low": d1_low_min.to_numpy(),
                "d1_max_high": d1_high_max.to_numpy(),
            },
            index=d1.index + GRANULARITY_INTERVAL["D1"],
        )

        d1_features = pd.merge_asof(
            pd.DataFrame(index=h4.index),
            d1_at_close,
            left_index=True,
            right_index=True,
            direction="backward",
            allow_exact_matches=False,
        )

        d1_min_low = d1_features["d1_min_low"].to_numpy(dtype=float)
        d1_max_high = d1_features["d1_max_high"].to_numpy(dtype=float)

        ema21 = ema(h4["Close"], self.EMA_PERIOD).to_numpy(dtype=float)
        sma89 = sma(h4["Close"], self.SMA_PERIOD).to_numpy(dtype=float)

        macd_line, signal_line, histogram = macd(
            h4["Close"], self.MACD_FAST, self.MACD_SLOW, self.MACD_SIGNAL
        )
        hist = histogram.to_numpy(dtype=float)
        close = h4["Close"].to_numpy(dtype=float)

        cal = USFederalCalendar()
        if len(h4) > 0:
            holidays_dt = cal.holidays(start=h4.index[0], end=h4.index[-1]).date
            dates = pd.Series(h4.index).dt.date.values
            is_holiday = np.isin(dates, holidays_dt)
        else:
            is_holiday = np.zeros(0, dtype=bool)

        orders: List[OrderIntent] = []
        armed_long = False
        armed_short = False

        for i in range(self.warmup_bars, len(h4)):
            # Arming Event
            if ema21[i] > sma89[i] and ema21[i - 1] <= sma89[i - 1]:
                armed_long = True
                armed_short = False
            elif ema21[i] < sma89[i] and ema21[i - 1] >= sma89[i - 1]:
                armed_short = True
                armed_long = False

            if np.isnan(d1_min_low[i]) or np.isnan(d1_max_high[i]):
                continue

            if armed_long:
                if hist[i] > 0 and hist[i - 1] <= 0:
                    armed_long = False
                    if close[i] > ema21[i] and ema21[i] > sma89[i]:
                        sl = float(d1_min_low[i]) - 4.0 * pip
                        if sl < close[i]:
                            if not is_holiday[i]:
                                A = float(close[i])
                                risk = A - sl
                                orders.append(
                                    OrderIntent(
                                        decision_bar=h4.index[i],
                                        direction=1,
                                        entry="market",
                                        entry_price=None,
                                        stop=StopRule(
                                            price=sl, move_to_breakeven_on=None
                                        ),
                                        exits=[
                                            ExitLeg(
                                                fraction=1.0,
                                                kind="take_profit",
                                                price=A + risk,
                                                label="TP1",
                                            )
                                        ],
                                        expires_after_bars=None,
                                        tag="h4_crossover",
                                    )
                                )
            elif armed_short:
                if hist[i] < 0 and hist[i - 1] >= 0:
                    armed_short = False
                    if close[i] < ema21[i] and ema21[i] < sma89[i]:
                        sl = float(d1_max_high[i]) + 4.0 * pip
                        if sl > close[i]:
                            if not is_holiday[i]:
                                A = float(close[i])
                                risk = sl - A
                                orders.append(
                                    OrderIntent(
                                        decision_bar=h4.index[i],
                                        direction=-1,
                                        entry="market",
                                        entry_price=None,
                                        stop=StopRule(
                                            price=sl, move_to_breakeven_on=None
                                        ),
                                        exits=[
                                            ExitLeg(
                                                fraction=1.0,
                                                kind="take_profit",
                                                price=A - risk,
                                                label="TP1",
                                            )
                                        ],
                                        expires_after_bars=None,
                                        tag="h4_crossover",
                                    )
                                )

        return orders
