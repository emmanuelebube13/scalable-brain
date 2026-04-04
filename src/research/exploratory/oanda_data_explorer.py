"""
OANDA Data Explorer (Practice API)
==================================
Read-only probe script to discover what data OANDA offers and how payloads differ
across endpoints and candle price modes.

What this script explores:
1) Account tradable instruments and metadata
2) Candles payload shape for price modes: M, B, A
3) Latest pricing snapshot for selected symbols
4) Optional order book / position book endpoints

Environment variables expected in .env:
- OANDA_API_KEY
- OANDA_ACCOUNT_ID_DEMO (or OANDA_ACCOUNT_ID)

Usage examples:
- python src/oanda_data_explorer.py
- python src/oanda_data_explorer.py --symbols EUR_USD GBP_USD --granularity M15 --count 8
- python src/oanda_data_explorer.py --skip-books
"""

import argparse
import json
import os
from typing import Any, Dict, Iterable, List, Optional

import requests
from dotenv import load_dotenv


BASE_URL = "https://api-fxpractice.oanda.com/v3"
DEFAULT_SYMBOLS = ["EUR_USD", "GBP_USD", "USD_JPY"]


def pretty(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, default=str)


def _short(value: Any, max_len: int = 320) -> str:
    text = str(value)
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


class OandaClient:
    def __init__(self, token: str, account_id: str, timeout: int = 25) -> None:
        self.account_id = account_id
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        )

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{BASE_URL}{path}"
        response = self.session.get(url, params=params or {}, timeout=self.timeout)
        try:
            payload = response.json()
        except ValueError:
            payload = {"raw": response.text}

        if response.status_code >= 400:
            err = {
                "status_code": response.status_code,
                "url": response.url,
                "errorCode": payload.get("errorCode"),
                "errorMessage": payload.get("errorMessage") or payload.get("message"),
                "payload": payload,
            }
            raise requests.HTTPError(pretty(err), response=response)

        return payload


def summarize_instruments(instruments: List[Dict[str, Any]], limit: int = 15) -> None:
    print("\n[1] Tradable instruments (sample)")
    print("-" * 72)
    print(f"Total instruments returned: {len(instruments)}")
    print("Showing key fields for first instruments:")

    sample = instruments[:limit]
    for idx, inst in enumerate(sample, start=1):
        row = {
            "name": inst.get("name"),
            "type": inst.get("type"),
            "displayName": inst.get("displayName"),
            "pipLocation": inst.get("pipLocation"),
            "displayPrecision": inst.get("displayPrecision"),
            "tradeUnitsPrecision": inst.get("tradeUnitsPrecision"),
            "minimumTradeSize": inst.get("minimumTradeSize"),
            "maximumOrderUnits": inst.get("maximumOrderUnits"),
            "marginRate": inst.get("marginRate"),
        }
        print(f"{idx:02d}. {pretty(row)}")


def summarize_candles(symbol: str, candles_payload: Dict[str, Any], mode: str) -> None:
    candles = candles_payload.get("candles", [])
    print(f"\n[2] Candles for {symbol} | price mode={mode}")
    print("-" * 72)
    print(f"Candle count: {len(candles)}")

    if not candles:
        print("No candles returned.")
        return

    first = candles[0]
    print(f"Top-level keys in one candle: {sorted(first.keys())}")

    body = {
        "time": first.get("time"),
        "complete": first.get("complete"),
        "volume": first.get("volume"),
    }
    for k in ("mid", "bid", "ask"):
        if k in first:
            body[k] = first[k]

    print("First candle sample:")
    print(pretty(body))


def summarize_pricing(pricing_payload: Dict[str, Any]) -> None:
    prices = pricing_payload.get("prices", [])
    print("\n[3] Pricing snapshot")
    print("-" * 72)
    print(f"Price records: {len(prices)}")

    for p in prices[:5]:
        sample = {
            "instrument": p.get("instrument"),
            "time": p.get("time"),
            "status": p.get("status"),
            "closeoutBid": p.get("closeoutBid"),
            "closeoutAsk": p.get("closeoutAsk"),
            "tradeable": p.get("tradeable"),
            "bids_top": p.get("bids", [{}])[0],
            "asks_top": p.get("asks", [{}])[0],
        }
        print(pretty(sample))


def try_books(client: OandaClient, symbol: str) -> None:
    print(f"\n[4] Optional books for {symbol}")
    print("-" * 72)

    for name, path in (
        ("OrderBook", f"/instruments/{symbol}/orderBook"),
        ("PositionBook", f"/instruments/{symbol}/positionBook"),
    ):
        try:
            payload = client.get(path)
            key = name[0].lower() + name[1:]
            book = payload.get(key, {})
            buckets = book.get("buckets", [])
            print(
                f"{name}: success | time={book.get('time')} | price={book.get('price')} | buckets={len(buckets)}"
            )
            if buckets:
                print("First bucket sample:")
                print(pretty(buckets[0]))
        except requests.HTTPError as e:
            print(f"{name}: not available for this symbol/account -> {_short(e)}")


def run_exploration(symbols: Iterable[str], granularity: str, count: int, skip_books: bool) -> None:
    load_dotenv()

    token = os.getenv("OANDA_API_KEY")
    account_id = os.getenv("OANDA_ACCOUNT_ID_DEMO") or os.getenv("OANDA_ACCOUNT_ID")

    if not token:
        raise RuntimeError("Missing OANDA_API_KEY in environment/.env")
    if not account_id:
        raise RuntimeError("Missing OANDA_ACCOUNT_ID_DEMO (or OANDA_ACCOUNT_ID) in environment/.env")

    client = OandaClient(token=token, account_id=account_id)

    print("=" * 72)
    print("OANDA DATA EXPLORER (Practice)")
    print(f"Account: {account_id}")
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Granularity: {granularity} | Count: {count}")
    print("=" * 72)

    instruments_payload = client.get(f"/accounts/{account_id}/instruments")
    instruments = instruments_payload.get("instruments", [])
    summarize_instruments(instruments, limit=15)

    supported = {i.get("name") for i in instruments}
    unknown = [s for s in symbols if s not in supported]
    if unknown:
        print("\nWarning: some symbols are not in account tradable instruments:")
        print(", ".join(unknown))

    for symbol in symbols:
        for mode in ("M", "B", "A"):
            candles_payload = client.get(
                f"/instruments/{symbol}/candles",
                params={
                    "granularity": granularity,
                    "count": count,
                    "price": mode,
                },
            )
            summarize_candles(symbol, candles_payload, mode)

    pricing_payload = client.get(
        f"/accounts/{account_id}/pricing",
        params={"instruments": ",".join(symbols)},
    )
    summarize_pricing(pricing_payload)

    if not skip_books:
        for symbol in symbols:
            try_books(client, symbol)

    print("\nDone. This script is read-only and does not write to your DB.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Explore available data from OANDA Practice API")
    parser.add_argument("--symbols", nargs="*", default=DEFAULT_SYMBOLS, help="Instruments like EUR_USD")
    parser.add_argument("--granularity", default="H1", help="OANDA granularity, e.g., S5, M1, H1, D")
    parser.add_argument("--count", type=int, default=8, help="Candles per request per price mode")
    parser.add_argument("--skip-books", action="store_true", help="Skip order book and position book probes")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        run_exploration(
            symbols=args.symbols,
            granularity=args.granularity,
            count=args.count,
            skip_books=args.skip_books,
        )
    except requests.HTTPError as e:
        print("OANDA HTTP error:")
        print(e)
    except Exception as e:
        print(f"Unexpected error: {e}")


if __name__ == "__main__":
    main()
