/*
Price Duplication Diagnostics for Fact_Market_Prices (SQL Server)
-----------------------------------------------------------------
Purpose:
1) Verify per-symbol candle counts and time ranges
2) Detect duplicate timestamps within each symbol/granularity
3) Build robust per-symbol signatures to detect identical OHLCV streams
4) Compare pairwise overlap quality between symbols
5) Show side-by-side candle samples for suspicious pairs

Assumptions:
- Tables: Fact_Market_Prices, Dim_Asset
- Columns: Asset_ID, Timestamp, Open, High, Low, Close, Volume, Granularity

Usage:
- Run whole script in SSMS.
- Optionally change @Granularity and @TopRows.
*/

SET NOCOUNT ON;

DECLARE @Granularity NVARCHAR(10) = 'H4';
DECLARE @TopRows INT = 30;

PRINT '============================================================';
PRINT 'STEP 1: Coverage per symbol for selected granularity';
PRINT '============================================================';

SELECT
    a.Asset_ID,
    a.Symbol,
    f.Granularity,
    COUNT(*) AS RowCount,
    MIN(f.[Timestamp]) AS MinTimestamp,
    MAX(f.[Timestamp]) AS MaxTimestamp
FROM Fact_Market_Prices f
JOIN Dim_Asset a ON a.Asset_ID = f.Asset_ID
WHERE f.Granularity = @Granularity
GROUP BY a.Asset_ID, a.Symbol, f.Granularity
ORDER BY a.Symbol;

PRINT '============================================================';
PRINT 'STEP 2: Duplicate timestamp check within each symbol';
PRINT '============================================================';

WITH dups AS (
    SELECT
        f.Asset_ID,
        f.Granularity,
        f.[Timestamp],
        COUNT(*) AS c
    FROM Fact_Market_Prices f
    WHERE f.Granularity = @Granularity
    GROUP BY f.Asset_ID, f.Granularity, f.[Timestamp]
    HAVING COUNT(*) > 1
)
SELECT
    a.Symbol,
    d.Granularity,
    COUNT(*) AS DuplicateTimestamps,
    SUM(d.c - 1) AS ExtraRowsFromDuplicates
FROM dups d
JOIN Dim_Asset a ON a.Asset_ID = d.Asset_ID
GROUP BY a.Symbol, d.Granularity
ORDER BY DuplicateTimestamps DESC, a.Symbol;

PRINT '============================================================';
PRINT 'STEP 3: Per-symbol OHLCV signature for duplication detection';
PRINT '============================================================';

/*
Signature design notes:
- CHECKSUM_AGG over timestamp+OHLCV rows is fast and useful.
- SUM/AVG stats are added to reduce collision risk.
- If all signature fields match across two symbols with same row count,
  data is very likely duplicated.
*/
WITH sig AS (
    SELECT
        f.Asset_ID,
        f.Granularity,
        COUNT(*) AS RowCount,
        MIN(f.[Timestamp]) AS MinTimestamp,
        MAX(f.[Timestamp]) AS MaxTimestamp,
        CHECKSUM_AGG(BINARY_CHECKSUM(
            CONVERT(BIGINT, DATEDIFF_BIG(SECOND, '2000-01-01', f.[Timestamp])),
            CONVERT(DECIMAL(18, 8), f.[Open]),
            CONVERT(DECIMAL(18, 8), f.High),
            CONVERT(DECIMAL(18, 8), f.Low),
            CONVERT(DECIMAL(18, 8), f.[Close]),
            CONVERT(DECIMAL(18, 4), f.Volume)
        )) AS RowChecksum,
        SUM(CONVERT(DECIMAL(38, 8), f.[Open])) AS SumOpen,
        SUM(CONVERT(DECIMAL(38, 8), f.High)) AS SumHigh,
        SUM(CONVERT(DECIMAL(38, 8), f.Low)) AS SumLow,
        SUM(CONVERT(DECIMAL(38, 8), f.[Close])) AS SumClose,
        SUM(CONVERT(DECIMAL(38, 4), f.Volume)) AS SumVolume,
        AVG(CONVERT(DECIMAL(38, 8), f.[Close])) AS AvgClose
    FROM Fact_Market_Prices f
    WHERE f.Granularity = @Granularity
    GROUP BY f.Asset_ID, f.Granularity
)
SELECT
    a.Symbol,
    s.Granularity,
    s.RowCount,
    s.MinTimestamp,
    s.MaxTimestamp,
    s.RowChecksum,
    s.SumOpen,
    s.SumHigh,
    s.SumLow,
    s.SumClose,
    s.SumVolume,
    s.AvgClose
FROM sig s
JOIN Dim_Asset a ON a.Asset_ID = s.Asset_ID
ORDER BY a.Symbol;

PRINT '============================================================';
PRINT 'STEP 4: Pairwise exact-signature matches (high confidence duplicate streams)';
PRINT '============================================================';

WITH sig AS (
    SELECT
        f.Asset_ID,
        f.Granularity,
        COUNT(*) AS RowCount,
        MIN(f.[Timestamp]) AS MinTimestamp,
        MAX(f.[Timestamp]) AS MaxTimestamp,
        CHECKSUM_AGG(BINARY_CHECKSUM(
            CONVERT(BIGINT, DATEDIFF_BIG(SECOND, '2000-01-01', f.[Timestamp])),
            CONVERT(DECIMAL(18, 8), f.[Open]),
            CONVERT(DECIMAL(18, 8), f.High),
            CONVERT(DECIMAL(18, 8), f.Low),
            CONVERT(DECIMAL(18, 8), f.[Close]),
            CONVERT(DECIMAL(18, 4), f.Volume)
        )) AS RowChecksum,
        SUM(CONVERT(DECIMAL(38, 8), f.[Open])) AS SumOpen,
        SUM(CONVERT(DECIMAL(38, 8), f.High)) AS SumHigh,
        SUM(CONVERT(DECIMAL(38, 8), f.Low)) AS SumLow,
        SUM(CONVERT(DECIMAL(38, 8), f.[Close])) AS SumClose,
        SUM(CONVERT(DECIMAL(38, 4), f.Volume)) AS SumVolume
    FROM Fact_Market_Prices f
    WHERE f.Granularity = @Granularity
    GROUP BY f.Asset_ID, f.Granularity
)
SELECT
    a1.Symbol AS Symbol1,
    a2.Symbol AS Symbol2,
    s1.Granularity,
    s1.RowCount,
    s1.MinTimestamp,
    s1.MaxTimestamp,
    s1.RowChecksum
FROM sig s1
JOIN sig s2
    ON s1.Asset_ID < s2.Asset_ID
   AND s1.Granularity = s2.Granularity
   AND s1.RowCount = s2.RowCount
   AND s1.MinTimestamp = s2.MinTimestamp
   AND s1.MaxTimestamp = s2.MaxTimestamp
   AND s1.RowChecksum = s2.RowChecksum
   AND s1.SumOpen = s2.SumOpen
   AND s1.SumHigh = s2.SumHigh
   AND s1.SumLow = s2.SumLow
   AND s1.SumClose = s2.SumClose
   AND s1.SumVolume = s2.SumVolume
JOIN Dim_Asset a1 ON a1.Asset_ID = s1.Asset_ID
JOIN Dim_Asset a2 ON a2.Asset_ID = s2.Asset_ID
ORDER BY Symbol1, Symbol2;

PRINT '============================================================';
PRINT 'STEP 5: Pairwise overlap quality (timestamp intersection comparison)';
PRINT '============================================================';

/*
For each symbol pair, this shows:
- overlap row count
- number of rows with any OHLCV mismatch on identical timestamps
- mismatch ratio (0 means perfect match)
*/
WITH base AS (
    SELECT Asset_ID, [Timestamp], [Open], High, Low, [Close], Volume
    FROM Fact_Market_Prices
    WHERE Granularity = @Granularity
),
pairs AS (
    SELECT b1.Asset_ID AS Asset1, b2.Asset_ID AS Asset2
    FROM (SELECT DISTINCT Asset_ID FROM base) b1
    JOIN (SELECT DISTINCT Asset_ID FROM base) b2
      ON b1.Asset_ID < b2.Asset_ID
),
overlap AS (
    SELECT
        p.Asset1,
        p.Asset2,
        b1.[Timestamp],
        CASE WHEN
            CONVERT(DECIMAL(18, 8), b1.[Open])  = CONVERT(DECIMAL(18, 8), b2.[Open])
        AND CONVERT(DECIMAL(18, 8), b1.High)    = CONVERT(DECIMAL(18, 8), b2.High)
        AND CONVERT(DECIMAL(18, 8), b1.Low)     = CONVERT(DECIMAL(18, 8), b2.Low)
        AND CONVERT(DECIMAL(18, 8), b1.[Close]) = CONVERT(DECIMAL(18, 8), b2.[Close])
        AND CONVERT(DECIMAL(18, 4), b1.Volume)  = CONVERT(DECIMAL(18, 4), b2.Volume)
        THEN 0 ELSE 1 END AS IsMismatch
    FROM pairs p
    JOIN base b1 ON b1.Asset_ID = p.Asset1
    JOIN base b2 ON b2.Asset_ID = p.Asset2 AND b2.[Timestamp] = b1.[Timestamp]
)
SELECT
    a1.Symbol AS Symbol1,
    a2.Symbol AS Symbol2,
    COUNT(*) AS OverlapRows,
    SUM(IsMismatch) AS MismatchRows,
    CAST(SUM(IsMismatch) * 1.0 / NULLIF(COUNT(*), 0) AS DECIMAL(10, 6)) AS MismatchRatio
FROM overlap o
JOIN Dim_Asset a1 ON a1.Asset_ID = o.Asset1
JOIN Dim_Asset a2 ON a2.Asset_ID = o.Asset2
GROUP BY a1.Symbol, a2.Symbol
ORDER BY MismatchRatio, OverlapRows DESC;

PRINT '============================================================';
PRINT 'STEP 6: Side-by-side top rows for one suspicious pair';
PRINT '============================================================';

DECLARE @SymbolA NVARCHAR(20) = 'EUR_USD';
DECLARE @SymbolB NVARCHAR(20) = 'GBP_USD';

WITH idmap AS (
    SELECT Asset_ID, Symbol
    FROM Dim_Asset
    WHERE Symbol IN (@SymbolA, @SymbolB)
),
a AS (
    SELECT TOP (@TopRows)
        f.[Timestamp], f.[Open], f.High, f.Low, f.[Close], f.Volume
    FROM Fact_Market_Prices f
    JOIN idmap m ON m.Asset_ID = f.Asset_ID AND m.Symbol = @SymbolA
    WHERE f.Granularity = @Granularity
    ORDER BY f.[Timestamp] DESC
),
b AS (
    SELECT TOP (@TopRows)
        f.[Timestamp], f.[Open], f.High, f.Low, f.[Close], f.Volume
    FROM Fact_Market_Prices f
    JOIN idmap m ON m.Asset_ID = f.Asset_ID AND m.Symbol = @SymbolB
    WHERE f.Granularity = @Granularity
    ORDER BY f.[Timestamp] DESC
)
SELECT
    COALESCE(a.[Timestamp], b.[Timestamp]) AS [Timestamp],
    a.[Open]  AS Open_A,
    b.[Open]  AS Open_B,
    a.High    AS High_A,
    b.High    AS High_B,
    a.Low     AS Low_A,
    b.Low     AS Low_B,
    a.[Close] AS Close_A,
    b.[Close] AS Close_B,
    a.Volume  AS Volume_A,
    b.Volume  AS Volume_B
FROM a
FULL OUTER JOIN b ON a.[Timestamp] = b.[Timestamp]
ORDER BY [Timestamp] DESC;

PRINT 'Done.';
