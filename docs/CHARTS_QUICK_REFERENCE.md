# Advanced Charts Quick Reference - Swing Trading Dashboard

> **SWING TRADING SYSTEM** | One-page reference for Layer 5 swing trading charts

**Trading Type:** Swing Trading | **Platform Focus:** Real-time multi-timeframe analysis for swing entries/exits

---

## Keyboard Shortcuts

### Essential Shortcuts

| Shortcut | Action |
|----------|--------|
| `T` | Trendline tool |
| `F` | Fibonacci tool |
| `R` | Auto S/R levels |
| `P` | Pattern detection |
| `V` | Volume profile |
| `C` | Correlation panel |
| `M` | Multi-timeframe |
| `Esc` | Cancel / Exit tool |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` | Redo |

### Timeframes (`1-8`)

| Key | TF | Key | TF |
|-----|-----|-----|-----|
| `1` | 1m | `5` | 1h |
| `2` | 5m | `6` | 4h |
| `3` | 15m | `7` | 1d |
| `4` | 30m | `8` | 1w |

---

## Chart Types

| Type | Use Case |
|------|----------|
| **Candlestick** | Technical analysis, patterns |
| **Bar** | Price action, OHLC focus |
| **Line** | Clean trends, overview |

---

## Indicators by Category

###  Trend (8)

| ID | Name | Default | Panel |
|----|------|---------|-------|
| `sma` | Simple Moving Average | period: 20 | Main |
| `ema` | Exponential Moving Average | period: 20 | Main |
| `wma` | Weighted Moving Average | period: 20 | Main |
| `tema` | Triple EMA | period: 10 | Main |
| `dema` | Double EMA | period: 21 | Main |
| `macd` | MACD | 12/26/9 | Sub |
| `adx` | Average Directional Index | period: 14 | Sub |
| `ma_ribbon` | MA Ribbon | [10,20,30,40,50] | Main |

###  Momentum (5)

| ID | Name | Default | OB/OS |
|----|------|---------|-------|
| `rsi` | Relative Strength Index | period: 14 | 70/30 |
| `stochastic` | Stochastic Oscillator | 14/3/3 | 80/20 |
| `roc` | Rate of Change | period: 12 | — |
| `cci` | Commodity Channel Index | period: 20 | ±100 |
| `williams_r` | Williams %R | period: 14 | -20/-80 |

###  Volatility (5)

| ID | Name | Default | Panel |
|----|------|---------|-------|
| `bollinger_bands` | Bollinger Bands | 20, 2 | Main |
| `atr` | Average True Range | period: 14 | Sub |
| `keltner_channel` | Keltner Channel | 20, 2 | Main |
| `natr` | Normalized ATR | period: 14 | Sub |
| `historical_volatility` | Historical Volatility | 20 | Sub |

###  Volume (5)

| ID | Name | Panel |
|----|------|-------|
| `obv` | On-Balance Volume | Sub |
| `vwap` | Volume Weighted Avg Price | Main |
| `volume_roc` | Volume Rate of Change | Sub |
| `accumulation_distribution` | A/D Line | Sub |
| `mfi` | Money Flow Index | Sub |

---

## Timeframes Reference

| Code | Minutes | Use For |
|------|---------|---------|
| `1m` | 1 | Scalping |
| `5m` | 5 | Day trading |
| `15m` | 15 | Entry timing |
| `30m` | 30 | Swing setup |
| `1h` | 60 | Primary analysis |
| `2h` | 120 | Swing trading |
| `4h` | 240 | Position trading |
| `6h` | 360 | Medium-term |
| `8h` | 480 | Multi-session |
| `12h` | 720 | Daily context |
| `1d` | 1440 | Long-term |
| `1w` | 10080 | Macro analysis |
| `1M` | 43200 | Strategic |

---

## Strategy Overlay Symbols

| Symbol | Meaning | Color |
|--------|---------|-------|
|  | Long Entry | Green |
|  | Short Entry | Red |
|  (dashed) | Stop Loss | Red |
|  (dashed) | Take Profit | Green |
|  (dashed) | Entry Price | Blue |

---

## Correlation Strength

| Value | Strength | Action |
|-------|----------|--------|
| +0.8 to +1.0 | Strong Positive | Avoid duplicate |
| +0.5 to +0.8 | Moderate Positive | Confirm signal |
| -0.5 to +0.5 | Weak | Diversify |
| -0.8 to -0.5 | Moderate Negative | Hedge potential |
| -1.0 to -0.8 | Strong Negative | Natural hedge |

---

## Volume Profile Terms

| Term | Definition |
|------|------------|
| **VPOC** | Price with highest volume |
| **Value Area** | 70% of total volume range |
| **VAH** | Value Area High |
| **VAL** | Value Area Low |

---

## API Quick Calls

### Get OHLC
```http
GET /api/v1/charts/ohlc?symbol=EUR_USD&timeframe=1h&limit=500
```

### Calculate Indicator
```http
POST /api/v1/indicators/calculate
{
  "symbol": "EUR_USD",
  "indicator": "rsi",
  "timeframe": "1h",
  "params": {"period": 14}
}
```

### Get Volume Profile
```http
GET /api/v1/charts/volume-profile-enhanced?symbol=EUR_USD&rows=24
```

### Get S/R Levels
```http
GET /api/v1/charts/support-resistance?symbol=EUR_USD&timeframe=1h
```

---

## WebSocket Quick Start

```javascript
// Connect
const ws = new WebSocket('ws://localhost:8000/api/v1/streaming/ws/oanda');

// Subscribe
ws.send(JSON.stringify({
  type: "subscribe",
  symbol: "EUR_USD",
  granularity: "M1"
}));

// Handle messages
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  if (msg.type === "tick") console.log(msg.data);
  if (msg.type === "candle") console.log(msg.data);
};
```

---

## Indicator Parameters

### MACD
```json
{
  "fast": 12,      // 2-50
  "slow": 26,      // 5-200
  "signal": 9      // 2-50
}
```

### Bollinger Bands
```json
{
  "period": 20,    // 5-100
  "stdDev": 2.0    // 0.5-4.0
}
```

### RSI
```json
{
  "period": 14,    // 2-50
  "overbought": 70, // 50-90
  "oversold": 30    // 10-50
}
```

### Stochastic
```json
{
  "kPeriod": 14,   // 5-30
  "smoothK": 3,    // 1-10
  "smoothD": 3     // 1-10
}
```

---

## Color Reference

### Dark Theme
```
Background: #0B0C0F
Grid: rgba(255,255,255,0.06)
Up: #22C55E
Down: #EF4444
Text: #9CA3AF
```

### Light Theme
```
Background: #FFFFFF
Grid: rgba(0,0,0,0.06)
Up: #16A34A
Down: #DC2626
Text: #6B7280
```

---

## Common Issues

| Problem | Solution |
|---------|----------|
| Chart blank | Check API connection, refresh page |
| No indicators | Verify data exists, clear cache |
| WS disconnect | Check OANDA config, force reconnect |
| Slow performance | Reduce indicators, lower candle limit |
| Wrong values | Check params, verify data source |

---

## Cache Clear

```http
DELETE /api/v1/indicators/cache/clear
DELETE /api/v1/indicators/cache/clear?symbol=EUR_USD
```

---

## Debug Mode

```javascript
// Browser console
localStorage.setItem('chart_debug', 'true');
```

---

*Print this page and keep it handy!*
