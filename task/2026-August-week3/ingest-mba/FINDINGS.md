# Findings for S1

## Bug 1 Reproduction
I fetched a W1 candle written by the System-1 path (`ingest_run_id IS NOT NULL`) and an H1 candle written by the Legacy path (`ingest_run_id IS NULL`) for `EUR_USD` and compared them to OANDA's response.

### System-1 Writer (W1 row at 2026-07-31T21:00:00Z)
- OANDA `bid.c`: 1.15571
- OANDA `mid.c`: 1.15580
- DB `"Close"`: 1.15571
- **Conclusion**: The database `"Close"` exactly matches `bid.c`. Bug 1 is confirmed for the System-1 writer.

### Legacy Writer (H1 row at 2026-08-21T00:00:00Z)
- OANDA `bid.c`: 1.16825
- OANDA `mid.c`: 1.16833
- DB `"Close"`: 1.16833
- DB `bid_close`: 1.16825
- **Conclusion**: The legacy writer correctly populates the mid `"Close"` and `bid_close`.

## Affected Rows Count
- System-1 rows (`ingest_run_id IS NOT NULL`):
  - **W1**: 5,375 rows
  - No other granularities were written by the System-1 path.
- Null bid window (2026-05-03 to 2026-07-03):
  - H4: 1,350 rows
  - W1: 45 rows
  - D1: 225 rows
  - H1: 5,400 rows
  - Total: 7,020 rows

Bug 1 is successfully reproduced and affected rows are counted. Proceeding to S2.
