# Advanced Charting System User Guide - Swing Trading Dashboard

> **SWING TRADING SYSTEM** | Layer 5 Dashboard — Professional Trading Charts for Swing Trade Analysis

**Trading Type:** Swing Trading | **Timeframe Focus:** H4, D1, H1

---

## Table of Contents

1. [Overview](#overview)
2. [Features Guide](#features-guide)
   - [Chart Types](#chart-types)
   - [Timeframes](#timeframes)
   - [Indicators](#indicators)
   - [Strategy Overlays](#strategy-overlays)
   - [Analysis Tools](#analysis-tools)
   - [Correlation Analysis](#correlation-analysis)
   - [Volume Profile](#volume-profile)
3. [User Interface](#user-interface)
4. [Keyboard Shortcuts](#keyboard-shortcuts)
5. [API Reference](#api-reference)
6. [Troubleshooting](#troubleshooting)

---

## Overview

The Advanced Charting System provides institutional-grade charting capabilities for trading analysis and strategy visualization. Built on top of the high-performance [Lightweight Charts™](https://tradingview.github.io/lightweight-charts/) library, it delivers smooth, responsive charting with extensive customization options.

### Key Capabilities

- **Multi-timeframe Analysis**: View data from 1-minute to 1-month timeframes
- **30+ Technical Indicators**: Complete suite of trend, momentum, volatility, and volume indicators
- **Real-time Streaming**: Live price updates via WebSocket from OANDA
- **Strategy Visualization**: Overlay entry/exit points, stop losses, and take profits
- **Drawing Tools**: Trendlines, Fibonacci retracements, support/resistance detection
- **Correlation Analysis**: Compare multiple assets simultaneously
- **Volume Profile**: Analyze volume distribution at price levels

### System Architecture

```

                    Frontend (React/TS)                      
            
  AdvancedChart   IndicatorPanel  StrategyOverlay     
            

                      WebSocket / REST

                     Backend (FastAPI)                       
            
   /api/charts    /api/indicators  /ws/oanda          
            

```

---

## Features Guide

### Chart Types

The system supports three primary chart types:

| Chart Type | Description | Best For |
|------------|-------------|----------|
| **Candlestick** | Traditional OHLC candles with wicks | Technical analysis, pattern recognition |
| **Bar** | OHLC bars without candle bodies | Price action analysis |
| **Line** | Simple closing price line | Trend overview, clean visuals |

#### Visual Styles

- **Dark Theme**: Professional dark background with high-contrast colors
  - Up candles: `#22C55E` (Green)
  - Down candles: `#EF4444` (Red)
  - Grid: Subtle white at 6% opacity
  
- **Light Theme**: Clean white background
  - Up candles: `#16A34A` (Green)
  - Down candles: `#DC2626` (Red)
  - Grid: Subtle black at 6% opacity

### Timeframes

13 timeframes are supported, ranging from 1 minute to 1 month:

| Timeframe | Code | Typical Use |
|-----------|------|-------------|
| 1 Minute | `1m` | Scalping, microstructure |
| 5 Minutes | `5m` | Short-term trading |
| 15 Minutes | `15m` | Day trading |
| 30 Minutes | `30m` | Swing trading setup |
| 1 Hour | `1h` | Primary analysis timeframe |
| 2 Hours | `2h` | Swing trading |
| 4 Hours | `4h` | Position trading |
| 6 Hours | `6h` | Medium-term analysis |
| 8 Hours | `8h` | Multi-session analysis |
| 12 Hours | `12h` | Daily context |
| 1 Day | `1d` | Long-term trends |
| 1 Week | `1w` | Macro analysis |
| 1 Month | `1M` | Strategic positioning |

**Time Visibility**: Time is shown on the x-axis for intraday timeframes (`1m` through `1h`). Higher timeframes show dates only.

### Indicators

The system includes 30+ institutional-grade technical indicators organized into categories:

#### Trend Indicators (8)

| Indicator | ID | Default Params | Description |
|-----------|-----|----------------|-------------|
| **Simple Moving Average** | `sma` | period: 20 | Arithmetic mean of closing prices |
| **Exponential Moving Average** | `ema` | period: 20 | Weighted average favoring recent prices |
| **Weighted Moving Average** | `wma` | period: 20 | Linearly weighted average |
| **Triple EMA** | `tema` | period: 10 | Triple-smoothed EMA for reduced lag |
| **Double EMA** | `dema` | period: 21 | Double-smoothed EMA |
| **MACD** | `macd` | fast: 12, slow: 26, signal: 9 | Trend-following momentum indicator |
| **Average Directional Index** | `adx` | period: 14 | Measures trend strength (0-100) |
| **MA Ribbon** | `ma_ribbon` | periods: [10,20,30,40,50] | Multiple EMAs for trend visualization |

#### Momentum Indicators (6)

| Indicator | ID | Default Params | Description | Overbought/Oversold |
|-----------|-----|----------------|-------------|---------------------|
| **Relative Strength Index** | `rsi` | period: 14 | Measures speed/magnitude of price changes | 70/30 |
| **Stochastic Oscillator** | `stochastic` | k: 14, d: 3 | Compares close to price range | 80/20 |
| **Rate of Change** | `roc` | period: 12 | Percentage change over period | N/A |
| **Commodity Channel Index** | `cci` | period: 20 | Measures price deviation from average | ±100 |
| **Williams %R** | `williams_r` | period: 14 | Momentum oscillator (inverted Stochastic) | -20/-80 |

#### Volatility Indicators (5)

| Indicator | ID | Default Params | Description |
|-----------|-----|----------------|-------------|
| **Bollinger Bands** | `bollinger_bands` | period: 20, stdDev: 2 | Volatility bands around SMA |
| **Average True Range** | `atr` | period: 14 | Measures market volatility |
| **Keltner Channel** | `keltner_channel` | period: 20, mult: 2 | ATR-based volatility bands |
| **Normalized ATR** | `natr` | period: 14 | ATR as percentage of price |
| **Historical Volatility** | `historical_volatility` | period: 20 | Annualized standard deviation |

#### Volume Indicators (5)

| Indicator | ID | Description |
|-----------|-----|-------------|
| **On-Balance Volume** | `obv` | Cumulative volume flow indicator |
| **Volume Weighted Avg Price** | `vwap` | Average price weighted by volume |
| **Volume Rate of Change** | `volume_roc` | Percentage change in volume |
| **Accumulation/Distribution** | `accumulation_distribution` | Money flow into/out of security |
| **Money Flow Index** | `mfi` | Volume-weighted RSI |

#### Trend Strength Indicators (3)

| Indicator | ID | Description |
|-----------|-----|-------------|
| **QStick** | `qstick` | Quantifies trend strength via candle bodies |
| **Vertical Horizontal Filter** | `vhf` | Distinguishes trending from ranging |
| **Mass Index** | `mass_index` | Identifies trend reversals |

#### Indicator Display

- **Main Panel**: Trend indicators overlay on price (SMA, EMA, Bollinger Bands)
- **Sub-panels**: Oscillators displayed below main chart (RSI, MACD, Stochastic, OBV, ATR, CCI, Williams %R)
- **Colors**: Automatically assigned from a palette of 10 colors per indicator instance

### Strategy Overlays

Visualize trading strategy performance directly on the price chart:

#### Entry Signals

| Signal | Visual | Description |
|--------|--------|-------------|
| Long Entry |  Green triangle | Bullish signal with confidence level |
| Short Entry |  Red triangle | Bearish signal with confidence level |

#### Trade Lines

| Type | Visual | Description |
|------|--------|-------------|
| Stop Loss | Red dashed horizontal line | Maximum loss level |
| Take Profit | Green dashed horizontal line | Profit target level |
| Entry Price | Blue dashed horizontal line | Position entry level |

#### Performance Metrics

The overlay displays:

- **Win Rate Badge**: Shows percentage of winning trades with tooltip breakdown
- **Trade Count**: Total number of completed trades
- **Average PnL**: Mean profit/loss per trade
- **Equity Curve**: Optional panel showing cumulative PnL over time

#### Trade Detail Popup

Click on any entry marker to see:
- Entry/exit prices
- PnL and pips gained
- R-multiple achieved
- Exit reason (SL hit, TP hit, timeout, manual)
- Confidence score and regime

### Analysis Tools

#### Drawing Tools

| Tool | Shortcut | Description |
|------|----------|-------------|
| **Trendline** | `T` | Draw support/resistance trendlines |
| **Fibonacci** | `F` | Draw Fibonacci retracement levels |

**Fibonacci Levels**: 0%, 23.6%, 38.2%, 50%, 61.8%, 78.6%, 100%

#### Auto-Detection Tools

| Tool | Shortcut | Description |
|------|----------|-------------|
| **Support/Resistance** | `R` | Auto-detect key levels using pivot algorithm |
| **Pattern Detection** | `P` | Detect chart patterns (H&S, triangles, channels) |
| **Divergence** | `D` | Identify price/indicator divergences |
| **Order Blocks** | `B` | Highlight consolidation zones |
| **Volume Analysis** | `V` | Toggle volume profile display |
| **Correlation** | `C` | Show correlation analysis panel |
| **MTF Analysis** | `M` | Multi-timeframe confirmation signals |

#### Support/Resistance Detection Algorithm

Parameters:
- **Left Bars**: 5 (bars to confirm pivot)
- **Right Bars**: 5 (bars to confirm pivot)
- **Zone Threshold**: 0.5% (price proximity for clustering)

Strength calculation considers:
- Number of touches
- Recency of touches
- Distance from current price

### Correlation Analysis

Compare price movements across multiple assets:

#### Features

- **Correlation Coefficient**: -1.0 to +1.0
  - +0.7 to +1.0: Strong positive (move together)
  - -0.7 to -1.0: Strong negative (move opposite)
  - -0.3 to +0.3: Weak/no correlation

- **Visual Display**:
  - Correlated assets shown as normalized percentage lines
  - Color-coded by strength
  - Toggle weak correlations on/off

- **Correlation Heatmap**: Matrix view of all asset correlations

#### Interpretation

| Correlation | Strength | Trading Implication |
|-------------|----------|---------------------|
| > 0.8 | Strong Positive | Avoid duplicate exposure |
| 0.5 - 0.8 | Moderate Positive | Confirming signals |
| -0.5 - 0.5 | Weak | Diversification benefit |
| -0.8 - -0.5 | Moderate Negative | Hedge potential |
| < -0.8 | Strong Negative | Natural hedge |

### Volume Profile

Analyze trading activity at different price levels:

#### Components

- **VPOC (Volume Point of Control)**: Price level with highest volume
- **Value Area**: Price range containing 70% of volume
- **Value Area High/Low**: Upper and lower bounds of value area

#### Display Options

- **Rows**: 10-100 price levels (default: 24)
- **Lookback**: 1-30 days of data (default: 7)
- **Side Panel**: Horizontal histogram showing volume at each price

#### Interpretation

- **VPOC as Support/Resistance**: High volume nodes often act as magnets
- **Value Area**: Represents "fair value" zone
- **Volume Gaps**: Low volume areas allow for rapid price movement

---

## User Interface

### Chart Interface Layout

```

 [Symbol] [Timeframe] [ChartType]        [Settings] []    <- Toolbar

                                                            
                     Main Chart Area                          <- Price + Indicators
                  (Candlesticks + Volume)                   
                                                            

                     RSI / MACD / etc.                        <- Sub-panel 1

                    Stochastic / OBV                          <- Sub-panel 2

```

### Toolbar Controls

#### Top Bar

| Control | Function |
|---------|----------|
| **Symbol Selector** | Change the trading instrument |
| **Timeframe Dropdown** | Select candle timeframe |
| **Chart Type Toggle** | Switch between candlestick/bar/line |
| **Volume Toggle** | Show/hide volume histogram |
| **Crosshair Toggle** | Enable/disable crosshair mode |
| **Fullscreen Button** | Expand chart to full screen |
| **Settings** | Configure chart appearance |
| **Screenshot** | Export chart as PNG image |

#### Indicator Panel

Located on the right side or in a floating panel:

1. **Add Indicator Button** — Opens indicator selector dialog
2. **Active Indicators List**:
   - Indicator name with icon (trend, momentum, volatility, volume)
   - Current parameters displayed
   - Remove button (×) to delete
   - Click to edit parameters

### Adding Indicators

1. Click the **"+ Add"** button in the Indicator Panel
2. Select a category (Trend, Momentum, Volatility, Volume)
3. Choose an indicator from the list
4. Adjust parameters using sliders:
   - Periods: 2-200
   - Standard Deviation: 0.5-4.0
   - Other values as appropriate
5. Click **"Add Indicator"** to apply

### Using Drawing Tools

#### Trendline

1. Press `T` or select Trendline tool
2. Click at starting point (time + price)
3. Drag to ending point
4. Click again to complete

#### Fibonacci Retracement

1. Press `F` or select Fibonacci tool
2. Click at swing high/low
3. Drag to swing low/high
4. Click again to place levels

#### Auto-Detection

1. Press corresponding shortcut (`R`, `P`, `D`, `B`)
2. System analyzes current chart data
3. Detected levels/patterns appear automatically
4. Click level to see details

### Reading Strategy Overlays

#### Entry Markers

- **Size**: Proportional to confidence score
- **Color**: Green (long) / Red (short)
- **Opacity**: Based on signal strength

#### Trade Lines

- Lines extend from entry time to exit time
- Dashed style indicates projected levels
- Solid style for historical trades

#### Win Rate Badge

Located in top-right corner:
- **Percentage**: Win rate rounded to 1 decimal
- **Icon**: Trending up (≥50%) or down (<50%)
- **Tooltip**: Hover for wins/losses breakdown

### Understanding Correlation Data

#### Correlation Panel

1. **Asset List**: Shows correlated instruments
2. **Coefficient**: Numeric correlation value
3. **Visual Line**: Normalized price movement
4. **Strength Indicator**: Color-coded badge

#### Filter Options

- **Hide Weak Correlations**: Toggle to show only |r| > 0.3
- **Min Correlation Slider**: Adjust threshold (0.0 - 1.0)

---

## Keyboard Shortcuts

### Chart Navigation

| Shortcut | Action |
|----------|--------|
| `+` / `=` | Zoom in |
| `-` | Zoom out |
| `` / `` | Pan left/right (when focused) |
| `Home` | Go to earliest data |
| `End` | Go to latest data |
| `Space` | Toggle play/pause (streaming) |

### Tool Activation

| Shortcut | Tool | Category |
|----------|------|----------|
| `T` | Trendline | Drawing |
| `F` | Fibonacci | Drawing |
| `R` | Support/Resistance | Analysis |
| `P` | Pattern Detection | Analysis |
| `D` | Divergence | Analysis |
| `B` | Order Blocks | Analysis |
| `V` | Volume Analysis | View |
| `C` | Correlation | View |
| `M` | MTF Analysis | View |

### Timeframe Switching

| Shortcut | Timeframe |
|----------|-----------|
| `1` | 1 Minute |
| `2` | 5 Minutes |
| `3` | 15 Minutes |
| `4` | 30 Minutes |
| `5` | 1 Hour |
| `6` | 4 Hours |
| `7` | 1 Day |
| `8` | 1 Week |

### View Controls

| Shortcut | Action |
|----------|--------|
| `F11` | Toggle fullscreen |
| `Escape` | Exit tool mode / Close dialogs |
| `Tab` | Cycle through panels |

### Drawing & Editing

| Shortcut | Action |
|----------|--------|
| `Delete` / `Backspace` | Remove selected object |
| `Ctrl/Cmd + Delete` | Clear all objects |
| `Ctrl/Cmd + Z` | Undo last action |
| `Ctrl/Cmd + Shift + Z` | Redo |
| `Ctrl/Cmd + Y` | Redo (alternate) |

### Indicator Controls

| Shortcut | Action |
|----------|--------|
| `I` | Open indicator panel |
| `Ctrl/Cmd + I` | Add new indicator |
| `Ctrl/Cmd + ` | Increase indicator period |
| `Ctrl/Cmd + ` | Decrease indicator period |

### Screenshot & Export

| Shortcut | Action |
|----------|--------|
| `Ctrl/Cmd + S` | Save chart image |
| `Ctrl/Cmd + Shift + S` | Save with custom name |

---

## API Reference

### REST Endpoints

#### Chart Data

##### Get OHLC Data
```http
GET /api/v1/charts/ohlc
```

Parameters:
| Name | Type | Required | Description |
|------|------|----------|-------------|
| symbol | string | Yes | Trading symbol (e.g., EUR_USD) |
| timeframe | string | No | Timeframe (default: 1h) |
| limit | integer | No | Candles to return (1-5000, default: 500) |
| start_date | datetime | No | Start date filter |
| end_date | datetime | No | End date filter |

Response:
```json
[
  {
    "timestamp": "2026-04-06T14:00:00Z",
    "open": 1.08500,
    "high": 1.08550,
    "low": 1.08480,
    "close": 1.08520,
    "volume": 1250
  }
]
```

##### Get Multi-Timeframe Data
```http
GET /api/v1/charts/multi-timeframe
```

Parameters:
| Name | Type | Required | Description |
|------|------|----------|-------------|
| symbol | string | Yes | Trading symbol |
| timeframes | string | No | Comma-separated (default: 1h,4h,1d) |
| limit | integer | No | Candles per timeframe (default: 100) |

##### Get Volume Profile
```http
GET /api/v1/charts/volume-profile-enhanced
```

Parameters:
| Name | Type | Required | Description |
|------|------|----------|-------------|
| symbol | string | Yes | Trading symbol |
| rows | integer | No | Price levels (10-100, default: 24) |
| lookback_days | integer | No | Days to analyze (1-30, default: 7) |

Response:
```json
{
  "symbol": "EUR_USD",
  "timeframe": "7D",
  "vpoc": {
    "price": 1.08520,
    "volume": 15420
  },
  "valueAreaHigh": 1.08650,
  "valueAreaLow": 1.08400,
  "points": [...]
}
```

##### Get Support/Resistance Levels
```http
GET /api/v1/charts/support-resistance
```

Parameters:
| Name | Type | Required | Description |
|------|------|----------|-------------|
| symbol | string | Yes | Trading symbol |
| timeframe | string | No | Timeframe (default: 1h) |
| sensitivity | integer | No | Pivot bars (1-20, default: 5) |
| lookback | integer | No | Candles to analyze (50-500, default: 100) |
| tolerance_pct | float | No | Clustering tolerance (default: 0.002) |

##### Get Analysis Metrics
```http
GET /api/v1/charts/analysis-metrics
```

Parameters:
| Name | Type | Required | Description |
|------|------|----------|-------------|
| symbol | string | Yes | Trading symbol |
| metric | string | No | Type: correlation, volatility, strength, all |
| period | string | No | 1W, 1M, 3M, 6M, 1Y (default: 1M) |
| compare_symbols | string | No | Comma-separated for correlation |

##### Get Strategy Overlay
```http
GET /api/v1/charts/strategy-overlay
```

Parameters:
| Name | Type | Required | Description |
|------|------|----------|-------------|
| symbol | string | Yes | Trading symbol |
| strategy | string | Yes | Strategy name/ID |
| timeframe | string | No | Timeframe (default: 1h) |
| lookback_days | integer | No | Days to look back (default: 30) |

#### Indicators

##### List Available Indicators
```http
GET /api/v1/indicators/list
```

Parameters:
| Name | Type | Required | Description |
|------|------|----------|-------------|
| category | string | No | Filter by category |

##### Calculate Indicator
```http
POST /api/v1/indicators/calculate
```

Parameters:
| Name | Type | Required | Description |
|------|------|----------|-------------|
| symbol | string | Yes | Trading symbol |
| indicator | string | Yes | Indicator ID |
| timeframe | string | No | Timeframe (default: 1h) |
| params | object | No | Indicator parameters |
| limit | integer | No | Data points (100-2000, default: 500) |
| skip_cache | boolean | No | Force recalculation |

Request Body:
```json
{
  "symbol": "EUR_USD",
  "indicator": "rsi",
  "timeframe": "1h",
  "params": {
    "period": 14,
    "overbought": 70,
    "oversold": 30
  }
}
```

Response:
```json
{
  "indicator": "rsi",
  "name": "RSI",
  "timestamps": [...],
  "values": [45.2, 48.1, 52.3, ...],
  "overbought": 70,
  "oversold": 30
}
```

##### Batch Calculate Indicators
```http
POST /api/v1/indicators/calculate-batch
```

Request Body:
```json
{
  "symbol": "EUR_USD",
  "timeframe": "1h",
  "indicators": [
    {"indicator": "sma", "params": {"period": 20}},
    {"indicator": "rsi", "params": {"period": 14}},
    {"indicator": "macd", "params": {"fast": 12, "slow": 26}}
  ]
}
```

##### Get Indicator Metadata
```http
GET /api/v1/indicators/metadata/{indicator_id}
```

##### Clear Indicator Cache
```http
DELETE /api/v1/indicators/cache/clear
```

Parameters:
| Name | Type | Required | Description |
|------|------|----------|-------------|
| symbol | string | No | Clear specific symbol only |

### WebSocket Protocol

#### Connection

```javascript
const ws = new WebSocket('ws://localhost:8000/api/v1/streaming/ws/oanda');
```

#### Client Messages

##### Subscribe to Symbol
```json
{
  "type": "subscribe",
  "symbol": "EUR_USD",
  "granularity": "M1"
}
```

##### Unsubscribe
```json
{
  "type": "unsubscribe",
  "symbol": "EUR_USD",
  "granularity": "M1"
}
```

##### Get Historical Candles
```json
{
  "type": "get_candles",
  "symbol": "EUR_USD",
  "granularity": "M1",
  "count": 100
}
```

##### Get Indicators
```json
{
  "type": "get_indicators",
  "symbol": "EUR_USD",
  "granularity": "M1",
  "indicators": [
    {"name": "sma", "params": {"period": 20}},
    {"name": "rsi", "params": {"period": 14}}
  ]
}
```

##### Ping
```json
{
  "type": "ping"
}
```

#### Server Messages

##### Tick Update
```json
{
  "type": "tick",
  "symbol": "EUR_USD",
  "data": {
    "time": "2026-04-06T15:00:00.123456Z",
    "bid": 1.08500,
    "ask": 1.08510,
    "mid": 1.08505
  }
}
```

##### Candle Update
```json
{
  "type": "candle",
  "symbol": "EUR_USD",
  "granularity": "M1",
  "data": {
    "timestamp": "2026-04-06T15:00:00Z",
    "open": 1.08500,
    "high": 1.08550,
    "low": 1.08480,
    "close": 1.08520,
    "volume": 125
  }
}
```

##### Indicator Data
```json
{
  "type": "indicators",
  "symbol": "EUR_USD",
  "granularity": "M1",
  "data": {
    "sma": {"values": [...]},
    "rsi": {"values": [...], "overbought": 70, "oversold": 30}
  }
}
```

##### Connection Status
```json
{
  "type": "connected",
  "client_id": "uuid-string",
  "message": "Connected to OANDA stream"
}
```

##### Error
```json
{
  "type": "error",
  "message": "Invalid symbol: XYZ"
}
```

##### Pong
```json
{
  "type": "pong"
}
```

### Streaming Endpoints

#### Get Streaming Status
```http
GET /api/v1/streaming/status
```

#### Get Health Check
```http
GET /api/v1/streaming/health
```

#### Get Available Instruments
```http
GET /api/v1/streaming/instruments
```

#### Force Reconnect
```http
POST /api/v1/streaming/reconnect
```

#### Reset Streaming
```http
POST /api/v1/streaming/reset
```

---

## Troubleshooting

### Common Issues

#### Chart Not Loading

**Symptoms**: Blank chart area, no candles displayed

**Solutions**:
1. Check browser console for JavaScript errors
2. Verify API endpoint is accessible: `GET /api/v1/charts/ohlc?symbol=EUR_USD`
3. Ensure database connection is active
4. Try refreshing the page (Ctrl/Cmd + Shift + R)
5. Check if `GENERATE_MOCK_DATA=true` environment variable is set for testing

#### Indicators Not Calculating

**Symptoms**: "No data available" error, empty indicator panel

**Solutions**:
1. Verify OHLC data exists for the symbol/timeframe
2. Check indicator parameters are within valid ranges
3. Clear indicator cache: `DELETE /api/v1/indicators/cache/clear`
4. Check Redis connection (falls back to in-memory if unavailable)
5. Review server logs for calculation errors

#### WebSocket Connection Issues

**Symptoms**: "Disconnected" status, no real-time updates

**Solutions**:
1. Check OANDA credentials are configured
2. Verify WebSocket URL is correct (check `VITE_WS_URL` env var)
3. Check firewall/proxy settings for WebSocket support
4. Review streaming status: `GET /api/v1/streaming/health`
5. Force reconnect: `POST /api/v1/streaming/reconnect`
6. Check browser console for WebSocket error codes

**Error Codes**:
| Code | Meaning | Action |
|------|---------|--------|
| 1000 | Normal closure | Reconnect if not intentional |
| 1006 | Abnormal closure | Check network, retry |
| 1011 | Server error | Check server logs |
| 1015 | TLS handshake fail | Check SSL certificates |

#### Slow Performance

**Symptoms**: Laggy scrolling, delayed updates

**Solutions**:
1. Reduce number of active indicators (max recommended: 6)
2. Lower the `limit` parameter for OHLC data (default 500)
3. Disable sub-panel indicators not in use
4. Close browser developer tools
5. Use Chrome or Edge for best performance
6. Disable browser extensions that modify page content

#### Incorrect Indicator Values

**Symptoms**: Values don't match other platforms

**Solutions**:
1. Verify parameters match exactly (period, std dev, etc.)
2. Check data source (first/last candle differences)
3. Ensure sufficient historical data for calculation warmup
4. Some indicators use Wilder's smoothing vs. standard SMA
5. Bollinger Bands use sample standard deviation (n-1)

### Performance Optimization

#### Chart Settings

| Setting | Recommendation | Impact |
|---------|---------------|--------|
| Timeframe | Use 1h+ for analysis, 1m for execution | Higher = faster |
| Candle Limit | 200-500 for most use cases | Lower = faster |
| Indicators | Max 3-4 main, 2 sub-panel | Fewer = faster |
| Correlated Assets | Max 2-3 at once | Fewer = faster |

#### Browser Optimization

1. **Enable Hardware Acceleration**:
   - Chrome: Settings  Advanced  System  "Use hardware acceleration"
   
2. **Clear Cache Regularly**:
   - Chart data caches for 5 minutes
   - Browser cache may need periodic clearing

3. **Disable Unnecessary Extensions**:
   - Ad blockers may interfere
   - Privacy extensions may block WebSocket

#### Server Optimization

1. **Redis Caching**:
   - Install Redis for persistent caching
   - Default in-memory cache limited to 1000 entries

2. **Database Indexing**:
   - Ensure `Fact_Market_Prices` has index on `(Asset_ID, Timestamp)`
   - Ensure `Fact_Live_Trades` has index on `(Asset_ID, Timestamp, Entry_Price)`

3. **OANDA Rate Limits**:
   - Max 2 connections per instrument
   - Respect 20 request/second limit for REST API

### WebSocket Reconnection Strategy

The client implements exponential backoff:

```
Attempt 1: 3 seconds
Attempt 2: 6 seconds  
Attempt 3: 12 seconds
Attempt 4: 24 seconds
Attempt 5+: 30 seconds (max)
```

**Manual Reset**:
If automatic reconnection fails after 10 attempts:
1. Click the connection status indicator
2. Select "Reset Connection"
3. Or call: `POST /api/v1/streaming/reset`

### Data Source Fallback

The system uses a three-tier fallback for OHLC data:

1. **Primary**: `Fact_Market_Prices` table
2. **Secondary**: Aggregated `Fact_Live_Trades` entry prices
3. **Tertiary**: Mock data (if `GENERATE_MOCK_DATA=true`)

Check the browser console to see which source is active.

### Debug Mode

Enable debug logging:

```javascript
// In browser console
localStorage.setItem('chart_debug', 'true');
```

This will log:
- Data source selection
- Indicator calculation timing
- WebSocket message counts
- Cache hit/miss rates

### Getting Help

1. **Check Logs**:
   - Browser console (F12)
   - Server logs: `/logs/layer5.log`
   
2. **System Status**:
   - Health: `GET /api/v1/streaming/health`
   - Metrics: `GET /api/v1/streaming/metrics`
   - Cache: `GET /api/v1/indicators/cache/stats`

3. **Support Channels**:
   - Internal Slack: `#layer5-support`
   - Documentation: See `README_LAYER5.md`
   - Issues: Create ticket in project tracker

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-04-06 | Initial release with 30+ indicators |

---

*Last Updated: 2026-04-06*
