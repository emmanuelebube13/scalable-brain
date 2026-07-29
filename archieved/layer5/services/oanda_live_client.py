"""Broker telemetry client for OANDA account-level open position data.

This module is read-only and designed for dashboard telemetry (Layer 5).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from dotenv import load_dotenv

load_dotenv()


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _oanda_credentials() -> tuple[str, str, str]:
    token = os.getenv("OANDA_API_KEY", "").strip()
    account_id = (
        os.getenv("OANDA_ACCOUNT_ID_DEMO") or os.getenv("OANDA_ACCOUNT_ID") or ""
    ).strip()
    env = os.getenv("OANDA_ENV", "practice").strip().lower() or "practice"
    return token, account_id, env


def is_oanda_configured() -> bool:
    token, account_id, _ = _oanda_credentials()
    return bool(token and account_id)


def get_open_positions_snapshot() -> Dict[str, Any]:
    """Return open positions and unrealized PnL from OANDA.

    Raises an exception when credentials are missing or API request fails.
    """
    token, account_id, env = _oanda_credentials()
    if not token or not account_id:
        raise RuntimeError("OANDA credentials are not configured")

    from oandapyV20 import API
    from oandapyV20.endpoints.accounts import AccountSummary
    from oandapyV20.endpoints.positions import OpenPositions

    client = API(
        access_token=token,
        environment=env if env in ("practice", "live") else "practice",
    )

    account_req = AccountSummary(accountID=account_id)
    account_resp = client.request(account_req)
    account = (account_resp or {}).get("account", {})

    open_pos_req = OpenPositions(accountID=account_id)
    open_pos_resp = client.request(open_pos_req)
    raw_positions = (open_pos_resp or {}).get("positions", [])

    normalized: List[Dict[str, Any]] = []
    for pos in raw_positions:
        instrument = str(pos.get("instrument") or "")
        for side_key, side_name in (("long", "long"), ("short", "short")):
            side = pos.get(side_key) or {}
            units = _to_int(side.get("units"), 0)
            if units == 0:
                continue
            normalized.append(
                {
                    "instrument": instrument,
                    "side": side_name,
                    "units": abs(units),
                    "avgPrice": _to_float(side.get("averagePrice"), 0.0),
                    "unrealizedPnl": _to_float(side.get("unrealizedPL"), 0.0),
                    "tradeIds": [str(t) for t in (side.get("tradeIDs") or [])],
                    "source": "oanda",
                }
            )

    unrealized = _to_float(account.get("unrealizedPL"), 0.0)
    open_count = _to_int(account.get("openPositionCount"), len(normalized))

    return {
        "source": "oanda",
        "livePositions": open_count,
        "unrealizedPnL": unrealized,
        "positions": normalized,
    }
