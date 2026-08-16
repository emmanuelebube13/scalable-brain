"""Retail Sentiment Fade — SPEC-retail_sentiment_fade.md (CSV row 51).

Fade an extreme retail positioning skew (>= 60% of retail accounts on one side) when
the D1 SMA(20)/SMA(50) alignment says the crowd is fighting the tape, with a
1.5 x ATR stop and a 3.0 x ATR target.

THE FEED DOES NOT EXIST — read this before the code
---------------------------------------------------
`fact_sentiment` is not in the database, and no retail positioning series exists
anywhere in this repo (DATA_AVAILABILITY: "Non-price data — none of it exists").
Two consequences, both deliberate:

* **Nothing is proxied.** Tick volume, price momentum, open interest and every other
  price-derived quantity would measure a different strategy, so the sentiment gate is
  simply not satisfiable without the feed. Handed no sentiment, this strategy emits
  **zero orders** — which is the honest answer, not a bug, and is why its harness
  verdict is UNMEASURABLE rather than FAIL. See the report.
* **The rule is implemented in full anyway**, against the schema §3 and §9 specify,
  and is injected: ``RetailSentimentFade(sentiment=<frame>)``. The golden fixture
  supplies a hand-built series and pins the whole trade plan, so the code is
  reviewable today and runnable the day the feed lands. Nothing about the technical
  half is reachable without the sentiment half — there is no "degraded mode" that
  trades on the SMAs alone, because that would be a different strategy and the brief
  forbids inventing one.

NOTE 1 — the §9 rule S1 eligibility lag. An observation may be used at decision bar
    *t* only when ``published_at <= close(t) - 24h``. D1 bars are stamped at their
    OPEN and close one day later, so for D1 that reduces exactly to
    ``published_at <= index[t]`` — the bar's own open stamp. Stated as the lag, not
    as the shortcut, so the constant stays visible and a different primary
    granularity keeps the intended 24h buffer.

NOTE 2 — §6/§7's stop and target are the CSV's recommended overlay, not the source
    (the source has no exits at all, §10 #4). Both are anchored to the decision
    close: ``Close[t] -/+ 1.5 x ATR14[t]`` and ``Close[t] +/- 3.0 x ATR14[t]``.
    Entries are market, so the fill is unknowable at emission and realised R differs
    from declared R whenever bar t+1 opens away from close(t).

NOTE 3 — §10 #7: a sentiment extreme persists for days, and the strategy re-emits on
    every qualifying bar. It cannot do otherwise — a v2 strategy never observes its
    own positions — so F12 (``max_concurrent_positions = 1``) is what stops the
    second admission, and re-entry after a stop-out is intended behaviour.
"""

from __future__ import annotations

from typing import List, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from ...data_access.indicators import atr, sma
from ..contract_v2 import (
    GRANULARITY_INTERVAL,
    ExitLeg,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
)

#: §3 / §9: the columns a `fact_sentiment` extract must carry for this strategy.
#: `published_at` is when the vendor released the observation — never `observed_at`,
#: which is what the value describes rather than when it became knowable.
SENTIMENT_COLUMNS = ("published_at", "long_ratio_pct", "short_ratio_pct")


def eligible_sentiment(
    sentiment: pd.DataFrame,
    decision_closes: pd.DatetimeIndex,
    publication_lag: pd.Timedelta,
) -> pd.DataFrame:
    """§9 rule S1: the most recent observation usable at each decision-bar close.

    ``decision_closes`` are the CLOSE timestamps of the decision bars (bars are
    stamped at their open, so the caller adds one interval). An observation is
    eligible at a close *c* iff ``published_at <= c - publication_lag``; the result
    is the last such observation for each *c*, NaN before the first one.

    Pure and public: this is the piece a reviewer must check against §9, and the
    piece that becomes live the day `fact_sentiment` exists.
    """
    missing = [c for c in SENTIMENT_COLUMNS if c not in sentiment.columns]
    if missing:
        raise ValueError(f"eligible_sentiment: sentiment frame lacks {missing}")
    published = pd.DatetimeIndex(sentiment["published_at"])
    if not published.is_monotonic_increasing:
        raise ValueError("eligible_sentiment: sentiment must be sorted by published_at")
    right = pd.DataFrame(
        {
            "long_ratio_pct": sentiment["long_ratio_pct"].to_numpy(dtype=float),
            "short_ratio_pct": sentiment["short_ratio_pct"].to_numpy(dtype=float),
        },
        index=published + publication_lag,
    )
    return pd.merge_asof(
        pd.DataFrame(index=pd.DatetimeIndex(decision_closes)),
        right,
        left_index=True,
        right_index=True,
        direction="backward",
    )


class RetailSentimentFade(StrategyV2):
    """Fade a >= 60% retail skew when the D1 SMA alignment opposes the crowd."""

    FAST_PERIOD = 20  # §3, §10 #1: reconstructed — the source names no periods
    SLOW_PERIOD = 50  # §3, §10 #1
    ATR_PERIOD = 14  # §3
    EXTREME_PCT = 60.0  # §4.1/§5.1, §10 #8: inclusive, as documented
    STOP_ATR_MULTIPLE = 1.5  # §6
    TARGET_ATR_MULTIPLE = 3.0  # §7: 2 x the stop distance, 1:2 RR
    PUBLICATION_LAG = pd.Timedelta(hours=24)  # §9 S1, §10 #5

    def __init__(self, sentiment: Optional[pd.DataFrame] = None) -> None:
        """``sentiment`` carries :data:`SENTIMENT_COLUMNS`; None = the feed is absent."""
        self._sentiment = sentiment

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="retail_sentiment_fade",
            name="Retail Sentiment Fade (>=60% skew against the MA trend)",
            version="0.1.0",
            author="n5-fleet",
            hypothesis=(
                "Retail traders as a crowd are systematically wrong at positioning "
                "extremes: when at least 60% of retail accounts are short a pair, their "
                "aggregate future buy-to-cover flow plus the tendency of inexperienced "
                "traders to fight trends and average losers creates persistent pressure "
                "in the direction against the crowd. Fading an extreme retail skew, but "
                "only when the fast-versus-slow moving-average trend confirms the crowd "
                "is fighting the tape, should capture a behavioural edge that persists "
                "because it is rooted in retail loss asymmetry rather than in an "
                "arbitrage sophisticated flow can close."
            ),
            granularities=["D1"],
            pairs=["EUR_USD", "GBP_USD", "USD_JPY"],  # §2: the three named pairs
            primary_granularity="D1",
            context_granularities=(),  # §2: everything is on the D1 frame
            simulate_on="H1",
            source_row=51,
            source_url="https://www.mql5.com/en/code/62627",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["sma", "atr", "retail_sentiment(EXTERNAL — absent)"]

    @property
    def warmup_bars(self) -> int:
        return self.SLOW_PERIOD  # §3: SMA(50) is the binding input

    @property
    def max_concurrent_positions(self) -> int:
        """§8 / §10 #6 (F12): the source's 'one order per symbol' guard."""
        return 1

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        gran = self.metadata.primary_granularity
        d1 = frames[gran]
        if self._sentiment is None or len(d1) <= self.warmup_bars:
            # The feed is absent: the §4.1/§5.1 gate cannot be evaluated, so no
            # intent may be emitted. Nothing here falls back to a price proxy.
            return []

        # NOTE 1: eligibility is measured against the decision bar's CLOSE.
        closes_at = d1.index + GRANULARITY_INTERVAL[gran]
        sentiment = eligible_sentiment(self._sentiment, closes_at, self.PUBLICATION_LAG)
        short_pct = sentiment["short_ratio_pct"].to_numpy(dtype=float)
        long_pct = sentiment["long_ratio_pct"].to_numpy(dtype=float)

        fast = sma(d1["Close"], self.FAST_PERIOD).to_numpy(dtype=float)
        slow = sma(d1["Close"], self.SLOW_PERIOD).to_numpy(dtype=float)
        atr_values = atr(
            d1["High"], d1["Low"], d1["Close"], period=self.ATR_PERIOD
        ).to_numpy(dtype=float)
        close = d1["Close"].to_numpy(dtype=float)
        index = d1.index

        orders: List[OrderIntent] = []
        for i in range(self.warmup_bars, len(d1)):
            atr_t = float(atr_values[i])
            if not np.isfinite(atr_t) or atr_t <= 0.0:
                continue
            if not (np.isfinite(fast[i]) and np.isfinite(slow[i])):
                continue

            direction = 0
            # §4: crowd is short at an extreme AND the MA trend is down
            if short_pct[i] >= self.EXTREME_PCT and fast[i] < slow[i]:
                direction = 1
            # §5: the mirror. §5's note — the two are mutually exclusive on one bar.
            elif long_pct[i] >= self.EXTREME_PCT and fast[i] > slow[i]:
                direction = -1
            if direction == 0:
                continue

            close_t = float(close[i])
            orders.append(
                OrderIntent(
                    decision_bar=index[i],
                    direction=1 if direction > 0 else -1,
                    entry="market",  # §4/§5: fills at the open of bar t+1 (F2)
                    entry_price=None,
                    decision_close=close_t,
                    # NOTE 2: the CSV's recommended overlay, decision-close anchored.
                    stop=StopRule(
                        price=close_t - direction * self.STOP_ATR_MULTIPLE * atr_t
                    ),
                    exits=[
                        ExitLeg(
                            fraction=1.0,
                            kind="take_profit",
                            price=close_t
                            + direction * self.TARGET_ATR_MULTIPLE * atr_t,
                            label="TP1",
                        )
                    ],
                    expires_after_bars=None,  # §4: a market intent is never pending
                    tag="sentiment_fade",
                    strategy_id=self.strategy_id,
                )
            )
        return orders
