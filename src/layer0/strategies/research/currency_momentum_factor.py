"""Currency Momentum Factor — SPEC-currency_momentum_factor.md (CSV row 43).

Quantpedia's cross-sectional currency momentum: rank the non-USD currencies by
their trailing 12-month (252 D1 bar) spot return against the dollar, go long the
top tercile and short the bottom tercile, rebalance monthly, hold ~21 D1 bars.

WHAT THE INTERFACE ALLOWS, AND WHERE THAT BITES — read before the code
-------------------------------------------------------------------------
``StrategyV2.generate_orders`` is handed ``Mapping[granularity -> DataFrame]``
for **one pair at a time** (``v2_harness.build_frames`` / ``verify_wave2.py``
loop over ``metadata.pairs`` and call the strategy once per pair), and the frames
carry no pair identity. A cross-sectional rank therefore cannot be computed
inside ``generate_orders``: the other currencies' series are not reachable, so
neither is "is this currency in the top tercile of the universe?".

Consequences, all recorded in ``task/2026-August-week1/wave2/REPORT-currency_momentum_factor.md``:

* The **rank filter is not applied** — this module emits the *absolute*
  (time-series) form of the same 12-month momentum signal on the pair it is
  handed. It is a degeneration of the spec, not the spec: in a month where the
  whole universe fell against the dollar, §4 would still buy the three strongest
  currencies, whereas this module is short all of them. Every trade is tagged
  ``mom12m_abs`` so the degradation is visible in trade-level reports.
* The two pieces the cross-sectional rule is made of are implemented here as
  public pure functions — :func:`currency_momentum` (§3) and
  :func:`net_tercile_weights` (§4.2-4.3, §5, §10 row 2, including the
  5-currency degeneracy where the median currency nets to zero) — and are
  pinned by the golden fixture. A multi-pair harness can call them unchanged;
  nothing in them is reachable from the single-pair path.

NOTE 1 — the direction mapping survives the degeneration exactly.
    §4.4/§5.4 invert the direction for USD-base pairs (USD_JPY, USD_CAD,
    USD_CHF) because buying the pair *sells* the non-USD currency, and §3
    inverts the momentum formula for the same pairs. The two inversions cancel:

        USD-quote pair (EUR_USD): mom_EUR = C(t)/C(t-252) - 1.
            mom > 0  ->  long EUR  ->  direction +1  ->  same sign as the pair.
        USD-base pair (USD_JPY):  mom_JPY = C(t-252)/C(t) - 1.
            pair up  ->  mom_JPY < 0  ->  short JPY  ->  direction +1 (§5.4).

    So ``direction = sign(pair 252-bar return)`` reproduces the spec's mapping
    under either quotation convention, which is why this module does not need to
    know which pair it was handed. The fixture asserts that identity for both
    conventions rather than trusting this comment.

NOTE 2 — the monthly cadence gate is the FIRST bar of a new calendar month,
    not §8.1's "last completed D1 bar of the month". "Last bar of month M" is
    not decidable from bar ``i`` alone: it requires knowing that no later bar
    exists in M, i.e. reading ``index[i + 1]``. Under ``assert_no_lookahead_v2``
    that is fatal, not cosmetic — when a probe truncates the frame so that a
    month-end bar is the last surviving bar, the truncated run cannot see the
    next month's bar and the order vanishes, and the probe (correctly) calls
    that look-ahead. A pure-calendar substitute ("the last weekday of the
    month") is worse: D1 FX bars are stamped at their open with a 21:00 UTC
    alignment, so no bar is stamped on a Friday and roughly a fifth of months
    would be skipped outright. ``month(index[i]) != month(index[i-1])`` uses
    only bars at or before ``i``, is truncation-stable, and fires exactly once
    per calendar month — one session later than §8.1. Reported as a deviation.

NOTE 3 — the stop is anchored to the DECISION-bar close, never to the fill
    (§6, §10 row 7). Entries are ``market``, so the fill (next bar's open) is
    unknowable at emission while ``StopRule.price`` must be an absolute float.
    ``close(t) -/+ 3.0 x ATR(D1,14)`` is knowable at the decision bar's close.
    Realised R therefore differs from declared R whenever price moves between
    the decision close and the fill — expected, and stated in the report.

NOTE 4 — the single exit leg is ``kind="time", bars=21`` (§7), measured in
    D1 bars. ``position_engine`` counts a ``time`` leg in **resolution-frame**
    bars (``time_bar = fill_bar + leg.bars``), so under the harness's H1
    resolution 21 becomes 21 hours rather than 21 trading days. That is an
    engine-semantics mismatch, not something this module may work around by
    rescaling ``bars`` (that would be a silent parameter change): the spec value
    is emitted as written and the mismatch is reported for the reviewer.
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Sequence, Tuple

import numpy as np
import pandas as pd

from ..contract_v2 import (
    Direction,
    ExitLeg,
    OrderIntent,
    StopRule,
    StrategyMetadataV2,
    StrategyV2,
)
from ...data_access.indicators import atr

#: §3: the universe's declaration order, which is also the exact-tie break
#: ("earlier-listed currency receives the better rank").
UNIVERSE_ORDER: Tuple[str, ...] = ("EUR", "GBP", "JPY", "AUD", "CAD", "NZD", "CHF")

#: §4.4: pairs quoted against the dollar — buying the pair is long the currency.
USD_QUOTE_PAIRS: Dict[str, str] = {
    "EUR_USD": "EUR",
    "GBP_USD": "GBP",
    "AUD_USD": "AUD",
    "NZD_USD": "NZD",
}

#: §5.4: pairs based on the dollar — buying the pair is SHORT the currency.
USD_BASE_PAIRS: Dict[str, str] = {
    "USD_JPY": "JPY",
    "USD_CAD": "CAD",
    "USD_CHF": "CHF",
}


def currency_momentum(close_then: float, close_now: float, *, usd_base: bool) -> float:
    """§3: trailing 12-month spot return of a currency against the dollar.

    ``close_then`` is the close 252 D1 bars before the decision bar, ``close_now``
    the decision bar's close; both are closed bars, so this is causal. For a
    USD-base pair the ratio is inverted, because a rising USD_JPY means a
    *falling* yen.

    Spot return only — the source's "total return" carry component needs rate
    data that does not exist (§10 row 3, DATA-GAP).
    """
    if close_then <= 0.0 or close_now <= 0.0:
        raise ValueError("currency_momentum: closes must be positive")
    if usd_base:
        return close_then / close_now - 1.0
    return close_now / close_then - 1.0


def net_tercile_weights(mom_by_currency: Mapping[str, float]) -> Dict[str, float]:
    """§4.2-4.3 / §5.3: rank descending, then net the long and short terciles.

    ``w_c = (1/3)*1[rank(c) <= 3] - (1/3)*1[rank(c) >= |U| - 2]``, verbatim and
    unretuned. On the live 5-currency universe the two terciles overlap at the
    median currency, whose legs cancel to ``0.0`` — the documented degeneracy of
    §2 and §10 row 2 (long-2 / short-2 / one flat), kept rather than repaired.

    Not reachable from :meth:`CurrencyMomentumFactor.generate_orders`, which is
    handed one pair at a time (see the module docstring). It is the piece a
    multi-pair harness needs, and the golden fixture pins it.
    """
    unknown = sorted(set(mom_by_currency) - set(UNIVERSE_ORDER))
    if unknown:
        raise ValueError(
            f"net_tercile_weights: currencies outside the universe {unknown}"
        )
    universe = [c for c in UNIVERSE_ORDER if c in mom_by_currency]
    ranked = sorted(
        universe,
        key=lambda c: (-float(mom_by_currency[c]), UNIVERSE_ORDER.index(c)),
    )
    size = len(ranked)
    weights: Dict[str, float] = {}
    for position, currency in enumerate(ranked):
        rank = position + 1
        long_leg = 1.0 / 3.0 if rank <= 3 else 0.0
        short_leg = 1.0 / 3.0 if rank >= size - 2 else 0.0
        weights[currency] = long_leg - short_leg
    return weights


def direction_for_currency_weight(weight: float, *, usd_base: bool) -> Direction:
    """§4.4 / §5.4: turn a net currency weight into a pair direction.

    Long the currency = buy a USD-quote pair, sell a USD-base pair. A zero
    weight has no direction and callers must not ask for one.
    """
    if weight == 0.0:
        raise ValueError(
            "direction_for_currency_weight: flat currency has no direction"
        )
    long_currency = weight > 0.0
    if usd_base:
        return -1 if long_currency else 1
    return 1 if long_currency else -1


class CurrencyMomentumFactor(StrategyV2):
    """Monthly 12-month momentum rotation on the majors against the dollar."""

    LOOKBACK_BARS = 252  # §3, §10 row 9: the CSV pseudocode's pct_change(252)
    ATR_PERIOD = 14  # §3: D1 ATR(14), used ONLY for the catastrophic stop
    STOP_ATR_MULTIPLE = 3.0  # §6, §10 row 1
    HOLD_BARS = 21  # §7, §10 row 5: one month of D1 trading days
    TERCILE_WEIGHT = 1.0 / 3.0  # §4.5, §10 row 6: equal weight, not renormalised

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> StrategyMetadataV2:
        return StrategyMetadataV2(
            strategy_id="currency_momentum_factor",
            name="Currency Momentum Factor (12-month, monthly rebalance)",
            version="0.1.0",
            author="wave2-fleet",
            hypothesis=(
                "Currencies that have appreciated against the US dollar over the "
                "trailing twelve months tend to keep appreciating over the following "
                "month, and currencies that have depreciated tend to keep falling, so "
                "a monthly-rebalanced long-short portfolio of the extreme terciles "
                "earns a persistent cross-sectional spread. The edge should persist "
                "because FX trends are driven by slow-moving macro forces — monetary-"
                "policy cycles, capital-flow reallocation, and underreaction by "
                "investors who anchor on outdated fair-value estimates — and because "
                "central banks smooth rather than jump policy, so rate-differential "
                "regimes (which pull exchange rates) persist for quarters; trend-"
                "following is compensation for bearing crash risk in sudden regime "
                "reversals. This is one of the best-documented anomalies in the "
                "currency literature (Menkhoff, Sarno, Schmeling & Schrimpf), though "
                "Quantpedia's own out-of-sample check is slightly negative, so the "
                "anomaly may be attenuating."
            ),
            granularities=["D1"],
            # §2 pairs_available only — NZD_USD and USD_CHF are Wave-1 pending
            # and must not be declared until they are backfilled.
            pairs=["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"],
            primary_granularity="D1",
            context_granularities=(),  # §2: none — everything is on the D1 frame
            simulate_on="H1",
            source_row=43,
            source_url="https://quantpedia.com/strategies/currency-momentum-factor",
        )

    @property
    def required_indicators(self) -> List[str]:
        return ["atr"]

    @property
    def warmup_bars(self) -> int:
        # §8.2: a pair is only rankable once it has 253 closed D1 bars
        # (t-252 ... t inclusive), i.e. from bar index LOOKBACK_BARS onward.
        return self.LOOKBACK_BARS

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def generate_orders(
        self, frames: Mapping[str, pd.DataFrame]
    ) -> Sequence[OrderIntent]:
        d1 = frames[self.metadata.primary_granularity]
        if len(d1) == 0:
            return []

        index = d1.index
        close = d1["Close"].to_numpy(dtype=float)
        atr_values = atr(
            d1["High"], d1["Low"], d1["Close"], period=self.ATR_PERIOD
        ).to_numpy(dtype=float)
        # Calendar month of each bar as a comparable integer. Derived per bar
        # from its own timestamp, so truncation cannot change it (NOTE 2).
        month_key = np.asarray(index.year, dtype=np.int64) * 12 + np.asarray(
            index.month, dtype=np.int64
        )

        orders: List[OrderIntent] = []
        start = max(self.warmup_bars, self.LOOKBACK_BARS, 1)
        for i in range(start, len(d1)):
            # §8.1 monthly cadence (NOTE 2): one decision per calendar month.
            if month_key[i] == month_key[i - 1]:
                continue

            close_now = float(close[i])
            close_then = float(close[i - self.LOOKBACK_BARS])
            if not (np.isfinite(close_now) and np.isfinite(close_then)):
                continue
            if close_now <= 0.0 or close_then <= 0.0:
                continue

            atr_t = float(atr_values[i])
            if not np.isfinite(atr_t) or atr_t <= 0.0:
                # No declarable stop distance -> no order (§6 needs ATR(14)).
                continue

            # NOTE 1: the pair's own 252-bar return carries the spec's direction
            # under either quotation convention.
            pair_return = close_now / close_then - 1.0
            if pair_return == 0.0:
                # Exactly flat over twelve months: neither tercile. Skip
                # (conservative — it trades less).
                continue
            direction: Direction = 1 if pair_return > 0.0 else -1

            # NOTE 3: decision-close-anchored catastrophic stop (§6).
            stop_price = close_now - direction * self.STOP_ATR_MULTIPLE * atr_t

            orders.append(
                OrderIntent(
                    decision_bar=index[i],
                    direction=direction,
                    entry="market",  # §4/§5: fills at the next bar's open (F1/F2)
                    entry_price=None,
                    decision_close=close_now,
                    stop=StopRule(price=stop_price),  # §6: no breakeven, no trail
                    exits=[
                        # §7: one time leg, fraction 1.0 (NOTE 4).
                        ExitLeg(
                            fraction=1.0,
                            kind="time",
                            bars=self.HOLD_BARS,
                            label="MONTH_END",
                        )
                    ],
                    expires_after_bars=None,  # §4: n/a for a market entry
                    size_fraction=self.TERCILE_WEIGHT,  # §4.5: 1/3 per active leg
                    tag="mom12m_abs",
                    strategy_id=self.strategy_id,
                )
            )
        return orders
