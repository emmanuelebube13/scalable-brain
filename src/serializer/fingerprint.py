import json
import hashlib
from src.layer0.strategies.research_data import load_ohlcv_readonly


def generate_fingerprint():
    # Repaired ranges
    repaired_ranges = {
        "W1": {"start": "1970-01-01T00:00:00Z", "end": "2099-12-31T23:59:59Z"},
        "D1": {"start": "2026-05-03T00:00:00Z", "end": "2026-07-03T23:59:59Z"},
        "H4": {"start": "2026-05-03T00:00:00Z", "end": "2026-07-03T23:59:59Z"},
        "H1": {"start": "2026-05-03T00:00:00Z", "end": "2026-07-03T23:59:59Z"},
    }

    fingerprints = {}
    instruments = ["EUR_USD"]
    granularities = ["H1", "H4", "D1", "W1"]

    for inst in instruments:
        for g in granularities:
            try:
                # Load last 100 bars, exclude the very last one to avoid boundary races
                df = load_ohlcv_readonly(inst, g, lookback_years=1)
                if df is not None and not df.empty and len(df) > 1:
                    df = df.iloc[-51:-1]  # last 50 closed bars

                    # Create string representation of (bar_time_utc, o, h, l, c)
                    # Rounding to avoid float precision issues across DBs
                    data_str = ""
                    for ts, row in df.iterrows():
                        data_str += f"{ts.isoformat()},{row['Open']:.5f},{row['High']:.5f},{row['Low']:.5f},{row['Close']:.5f}\n"

                    h = hashlib.sha256(data_str.encode("utf-8")).hexdigest()
                    fingerprints[f"{inst}_{g}"] = {
                        "sha256": h,
                        "bars_counted": len(df),
                        "start": df.index[0].isoformat(),
                        "end": df.index[-1].isoformat(),
                    }
            except Exception as e:
                pass

    return {
        "repaired_ranges_bid_as_mid": repaired_ranges,
        "fingerprints": fingerprints,
        "note": "A gate, not a log line. Must match exactly on sync.",
    }


if __name__ == "__main__":
    print(json.dumps(generate_fingerprint(), indent=2))
