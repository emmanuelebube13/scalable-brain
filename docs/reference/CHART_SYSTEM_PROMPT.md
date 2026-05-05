# STATE-OF-THE-ART TRADING CHART SYSTEM - IMPLEMENTATION PROMPT

## AUTHORIZED CHANGES
This prompt is authorized to replace the current TradingView API-based chart system with a custom, high-performance charting solution. Full permission granted to modify frontend components, backend APIs, database queries, and infrastructure as needed.

---

## EXECUTIVE SUMMARY
Replace the current basic lightweight-charts implementation with a production-grade trading platform chart system featuring:
- **OANDA real-time + historical data** binding
- **Advanced technical indicators** (30+ indicators library)
- **Strategy overlay visualization**
- **Asset filtering & multi-symbol comparison**
- **Professional-grade analysis tools**
- **Real-time performance metrics**
- **Institutional-quality design**

---

## ARCHITECTURE OVERVIEW

### Frontend Stack
- **Chart Library**: TradingView Lightweight Charts 4.2+ (keep for OHLC rendering)
- **UI Framework**: React 18+ with TypeScript
- **State Management**: React Context + Hooks (or Redux for complex interactions)
- **Styling**: Tailwind CSS + custom canvas overlays
- **Real-time Updates**: WebSocket layer for live OANDA feed
- **Performance**: Virtualization for large datasets, Web Workers for calculations

### Backend Services
- **Primary Data Source**: OANDA v20 API (wss://stream.oanda.com for real-time)
- **Historical Data**: SQL Server (Fact_Market_Prices table)
- **Indicator Calculation**: Python + numpy/pandas (move from frontend)
- **Analysis Engine**: Custom analytics service for correlation, pattern detection
- **Caching Layer**: Redis for 1-minute, 15-minute, hourly aggregations

### Database Schema (Enhancements)
```sql
-- Add these tables for indicator caching
CREATE TABLE Dim_Indicator_Library (
  Indicator_ID INT PRIMARY KEY IDENTITY(1,1),
  Indicator_Name NVARCHAR(100),
  Category NVARCHAR(50), -- 'Momentum', 'Trend', 'Volatility', 'Volume'
  Parameters NVARCHAR(MAX), -- JSON: {"period":14, "smoothing":"SMA"}
  Formula NVARCHAR(MAX),
  Description NVARCHAR(MAX)
);

CREATE TABLE Fact_Indicator_Values (
  Indicator_Value_ID BIGINT PRIMARY KEY IDENTITY(1,1),
  Asset_ID INT,
  Indicator_ID INT,
  Timestamp DATETIME,
  Granularity NVARCHAR(10), -- '1m', '5m', '1h', '1d'
  Value DECIMAL(18,8),
  Upper_Band DECIMAL(18,8) NULL,
  Lower_Band DECIMAL(18,8) NULL,
  Signal_Line DECIMAL(18,8) NULL,
  FOREIGN KEY (Asset_ID) REFERENCES Dim_Asset(Asset_ID),
  FOREIGN KEY (Indicator_ID) REFERENCES Dim_Indicator_Library(Indicator_ID)
);

CREATE TABLE Fact_Analysis_Metrics (
  Metric_ID BIGINT PRIMARY KEY IDENTITY(1,1),
  Asset_ID INT,
  Timestamp DATETIME,
  Granularity NVARCHAR(10),
  Correlation_With_Index DECIMAL(10,6),
  Volatility_30d DECIMAL(10,6),
  Support_Level DECIMAL(18,8),
  Resistance_Level DECIMAL(18,8),
  Average_True_Range DECIMAL(18,8),
  Strength_Index DECIMAL(10,6)
);
```

---

## FEATURE SPECIFICATIONS

### 1. CHART CORE (CustomChart Component)
**File**: `src/layer5/frontend/src/components/charts/AdvancedChart.tsx`

```typescript
// Props Interface
interface AdvancedChartProps {
  // Data binding
  symbol: string;
  timeframe: Granularity; // '1m' | '5m' | '15m' | '30m' | '1h' | '4h' | '1d' | '1w'
  dataSource: 'oanda' | 'database'; // Auto-switch based on timeframe
  
  // Indicators
  activeIndicators: {
    id: string;
    name: string;
    params: Record<string, any>;
    color: string;
    subpanel?: boolean;
  }[];
  
  // Overlays
  showStrategy: boolean;
  strategyName?: string;
  showLiveTradeLines: boolean; // Entry/SL/TP lines
  showSupportResistance: boolean;
  showVolumeProfile?: boolean;
  
  // Asset filtering
  correlatedAssets?: string[]; // Show correlation as multi-line overlay
  hideWeakCorrelations?: boolean;
  minCorrelation?: number; // 0-1
  
  // Analysis mode
  analysisTools?: AnalysisTool[];
  
  // Callbacks
  onIndicatorChange?: (indicators: any[]) => void;
  onRangeChange?: (from: Date, to: Date) => void;
}

// Key Methods
- loadHistoricalData(symbol, timeframe, limit) // From DB or cache
- subscribeToLiveData(symbol) // WebSocket connection to OANDA
- calculateIndicators(data, specifications) // Offload to Web Worker
- detectSupportResistance(data, sensitivity) // Algorithm
- analyzePattern(data, type) // Head-and-shoulders, triangles, etc.
- exportChartImage(format) // PNG, SVG with annotations
```

**Features**:
-  Smooth 60FPS rendering
-  Real-time OANDA streaming (500ms latency target)
-  Historical data: 10K+ candles without lag
-  Indicator overlay (unlimited count)
-  Synchronized timeframe switching
-  Trading signal annotation (Entry/SL/TP/Result)
-  Price action annotations (support, resistance, trendlines)
-  Multi-symbol correlation overlay
-  Volume profile analysis
-  Performance metrics display

---

### 2. INDICATOR LIBRARY (30+ Indicators)

**File**: `src/layer5/frontend/src/utils/indicators/`

#### Momentum Indicators
- RSI (Relative Strength Index) [period: 14]
- MACD (Moving Average Convergence Divergence) [fast: 12, slow: 26, signal: 9]
- Stochastic Oscillator [period: 14, smoothK: 3, smoothD: 3]
- ROC (Rate of Change) [period: 12]
- CCI (Commodity Channel Index) [period: 20]
- Williams %R [period: 14]

#### Trend Indicators
- SMA/EMA/WMA (Simple/Exponential/Weighted Moving Averages) [periods: 20, 50, 200]
- TEMA (Triple Exponential Moving Average) [period: 10]
- DEMA (Double Exponential Moving Average) [period: 21]
- ADX (Average Directional Index) [period: 14]
- Moving Average Ribbon [periods: 10, 20, 30, 40, 50]

#### Volatility Indicators
- Bollinger Bands [period: 20, stdDev: 2]
- ATR (Average True Range) [period: 14]
- Keltner Channel [period: 20, offsetMultiplier: 2]
- NATR (Normalized ATR) [period: 14]
- Historical Volatility [period: 20]

#### Volume Indicators
- OBV (On-Balance Volume)
- Volume Weighted Average Price (VWAP)
- Volume Rate of Change [period: 12]
- Accumulation/Distribution Line
- Money Flow Index [period: 14]

#### Trend Strength
- QStick [period: 10]
- VHF (Vertical Horizontal Filter) [period: 28]
- MI (Mass Index) [period: 9]

**Implementation Requirements**:
```typescript
interface IndicatorSpec {
  id: string;
  name: string;
  category: 'momentum' | 'trend' | 'volatility' | 'volume';
  inputs: {
    data: OHLCVBar[];
    params: Record<string, number | string>;
  };
  outputs: {
    values: number[];
    bands?: { upper: number[]; middle?: number[]; lower: number[] };
    signal?: number[];
    histogram?: number[];
  };
  renderSubpanel: boolean; // true = render below main chart
  colors: string[];
  yAxisPosition: 'left' | 'right';
}

// Calculate in Web Worker
function calculateIndicator(spec: IndicatorSpec): Promise<IndicatorOutput>;
```

---

### 3. STRATEGY OVERLAY SYSTEM

**File**: `src/layer5/frontend/src/components/charts/StrategyOverlay.tsx`

Visualize strategy performance directly on chart:
- **Entry signals**: Green triangles  (long) / Red triangles  (short)
- **Stop Loss lines**: Dashed red horizontal lines
- **Take Profit lines**: Dashed green horizontal lines
- **Trade outcome**: Green (win) / Red (loss) shading on bars during position hold
- **Win rate badge**: Small widget showing % wins for strategy on this symbol/timeframe
- **Equity curve**: Optional secondary panel showing cumulative PnL

```typescript
interface StrategyEntry {
  timestamp: Date;
  signal: 1 | -1; // long | short
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  confidence: number; // 0-1, controls opacity/boldness
  regime: string;
}

interface TradeResult {
  entry: StrategyEntry;
  exit_price: number;
  exit_reason: 'sl_hit' | 'tp_hit' | 'timeout' | 'manual';
  pnl: number;
  pips_gained: number;
  r_multiple: number;
}
```

---

### 4. ASSET FILTERING & CORRELATION VIEW

**File**: `src/layer5/frontend/src/components/charts/AssetCorrelationPanel.tsx`

```typescript
interface CorrelationData {
  baseAsset: string;
  correlatedAssets: Array<{
    symbol: string;
    correlation: number; // -1 to 1
    strength: 'strong_positive' | 'moderate_positive' | 'weak' | 'moderate_negative' | 'strong_negative';
    slope: 'diverging' | 'converging';
  }>;
  period: '1W' | '1M' | '3M'; // Lookback period
  refreshTime: Date;
}
```

**Features**:
- Filter assets by correlation strength (hide < 0.3)
- Show multi-asset divergence/convergence analysis
- Correlation heatmap
- Real-time correlation updates
- Suggest asset pairs for correlation trading

**Data Source**: `Fact_Analysis_Metrics.Correlation_With_Index` (calculate daily, cache for 24h)

---

### 5. ANALYSIS TOOLS TOOLBAR

**File**: `src/layer5/frontend/src/components/charts/AnalysisToolbar.tsx`

```typescript
enum AnalysisTool {
  TRENDLINE = 'trendline',           // Draw trend lines
  SUPPORT_RESISTANCE = 'sr',         // Auto-detect S/R levels
  FIBONACCI = 'fibonacci',           // Fib retracement
  PATTERN_DETECTION = 'patterns',    // H&S, triangles, channels
  DIVERGENCE = 'divergence',         // Price/indicator divergence
  ORDER_BLOCKS = 'order_blocks',     // Order block detection
  VOLUME_ANALYSIS = 'volume',        // Volume profile & breaks
  CORRELATION = 'correlation',       // Correlation analysis
  MTF_ANALYSIS = 'mtf',              // Multi-timeframe confirmation
}
```

**Implementation**:
- Drag to draw trendlines (persisted in localStorage per session)
- Auto-detect: support/resistance using pivot algorithm
- Pattern detection: ML-based shape recognition
- Divergence detection: Price vs RSI/MACD divergences
- Order block detection: Recent price consolidation blocks
- Volume analysis: Volume profile, volume breaks, VPOC

---

### 6. BACKEND API ENHANCEMENTS

**Existing**: `/api/v1/chart/ohlc` (returns Fact_Market_Prices)

**New Endpoints**:

```
POST /api/v1/chart/indicators/calculate
  Input: { symbol, timeframe, from, to, indicators: [...] }
  Output: { results: { indicator_name: { values, timestamps } } }
  NOTE: Calculate server-side, cache results in Fact_Indicator_Values

GET /api/v1/chart/indicators/library
  Output: { indicators: [...IndicatorSpecs] }

GET /api/v1/chart/support-resistance
  Input: { symbol, timeframe, sensitivity: 0-10 }
  Output: { support_levels: [], resistance_levels: [] }

GET /api/v1/chart/analysis-metrics
  Input: { symbol, metric: 'correlation'|'volatility'|'strength' }
  Output: { results: [...] }

GET /api/v1/chart/strategy-overlay?strategy=MA_Crossover&symbol=EUR_USD&timeframe=1h
  Output: { entries: [...StrategyEntry], trades: [...TradeResult] }

WS /ws/chart/oanda-stream
  Input: { action: 'subscribe', symbol: 'EUR_USD' }
  Output: { type: 'price', symbol, bid, ask, timestamp }
```

---

### 7. REAL-TIME DATA PIPELINE (OANDA  Frontend)

**Architecture**:
```
OANDA v20 API (wss://stream.oanda.com)
    
Python: layer5/services/oanda_stream_service.py
     (parse, normalize)
WebSocket Server (FastAPI/Socket.IO)
    
Frontend: useOandaStream hook
    
TradingChart component (re-render on new candle close)
```

**File**: `src/layer5/services/oanda_stream_service.py`

```python
class OandaStreamManager:
    def __init__(self, api_key: str, account_id: str):
        self.connection = v20.Connection(
            accountID=account_id,
            token=api_key,
            environment="practice"
        )
    
    def subscribe_instrument(self, symbol: str, granularity: str = "M1"):
        """Subscribe to candle/price stream"""
        # Stream real-time data via WebSocket
        # On candle close, emit to connected clients
        pass
    
    def get_candles(self, symbol: str, granularity: str, count: int = 500):
        """Fetch historical candles from OANDA"""
        pass
    
    def calculate_indicators_batch(self, symbol: str, granularity: str, indicators: list):
        """Pre-calculate and cache indicators server-side"""
        pass
```

**Frontend Hook**:
```typescript
function useOandaStream(symbol: string, granularity: string) {
  const [ohlcData, setOhlcData] = useState<OHLCData[]>([]);
  
  useEffect(() => {
    const ws = new WebSocket('wss://localhost:8000/ws/chart/oanda-stream');
    ws.send(JSON.stringify({ 
      action: 'subscribe', 
      symbol, 
      granularity,
      aggregation: 'candle' 
    }));
    
    ws.onmessage = (event) => {
      const { type, data } = JSON.parse(event.data);
      if (type === 'candle') {
        setOhlcData(prev => {
          // Merge new candle or append if closed
          const last = prev[prev.length - 1];
          if (last.timestamp === data.timestamp) {
            // Update open candle
            return [...prev.slice(0, -1), data];
          }
          return [...prev, data]; // New closed candle
        });
      }
    };
    
    return () => ws.close();
  }, [symbol, granularity]);
  
  return ohlcData;
}
```

---

### 8. PERFORMANCE OPTIMIZATION

**Target Metrics**:
- Chart initial load: < 2 seconds
- Indicator calculation: < 500ms for 1000 candles
- Real-time candle update: < 50ms latency
- Memory footprint: < 50MB for 10K candles + 5 indicators
- Frame rate: 60 FPS during pan/zoom

**Techniques**:
1. **Web Workers**: Offload indicator calculations to background thread
2. **Virtualization**: Render only visible candles (canvas optimization)
3. **Server-side Caching**: Pre-calculate and cache indicators in Redis
4. **Data Compression**: Store only delta updates for real-time stream
5. **Memoization**: React.memo + useMemo for heavy components
6. **Lazy Loading**: Load indicators on-demand, not all at startup

```typescript
// In frontend
const workerPool = new WorkerPool(4); // 4 background workers

function calculateIndicatorsAsync(data: OHLCData[], specs: IndicatorSpec[]) {
  return Promise.all(
    specs.map(spec => workerPool.execute('calculateIndicator', spec, data))
  );
}
```

---

### 9. UI/UX COMPONENTS

**Main Chart Container**:
- Large responsive chart (takes 70% of view)
- Toolbar above: Symbol selector, timeframe buttons, indicator add button, analysis tools
- Right sidebar: Indicator legend (toggle on/off per indicator)
- Bottom panel: Volume, news feed, correlation
- Mini chart: Thumbnail for position in data timeline

**Indicator Panel**:
```
 Active Indicators 
  RSI(14)            [color] [⋮]      
   Value: 67 | Overbought               
  MACD(12,26,9)      [color] [⋮]      
   Histogram: +1.23 | Bullish           
  MA(50)             [color] [⋮]      
   Price: 1.0850 | Above (bullish)      
 + Add Indicator                        

```

**Analysis Tools Menu**:
```
 Analysis Tools 
  Trendline                    
  Support/Resistance (auto)    
  Fibonacci Retracement        
  Pattern Detection (ML)       
 ≈ Divergence Detection         
 ⊡ Order Blocks                 
 ∼ Volume Profile               
  Correlation Analysis         
 ≣ Multi-Timeframe Confirmation 

```

---

### 10. DATABASE INTEGRATION

**Write Flow**:
1. Backend calculates indicators (hourly batch job per symbol)
2. Insert into `Fact_Indicator_Values` (timestamp, symbol, indicator_id, value)
3. Cache in Redis with 24h TTL
4. Query endpoint checks cache first, then DB

**Query Optimization**:
```sql
-- Get all indicators for symbol/timeframe in date range
SELECT 
  fv.Timestamp,
  fv.Indicator_ID,
  dil.Indicator_Name,
  fv.Value,
  fv.Upper_Band,
  fv.Lower_Band
FROM Fact_Indicator_Values fv
INNER JOIN Dim_Indicator_Library dil ON fv.Indicator_ID = dil.Indicator_ID
WHERE fv.Asset_ID = @asset_id
  AND fv.Granularity = @granularity
  AND fv.Timestamp BETWEEN @from AND @to
ORDER BY fv.Timestamp, fv.Indicator_ID;
```

---

## IMPLEMENTATION ROADMAP

### Phase 1: Core Chart Refactor (Week 1)
- [ ] Create AdvancedChart component with OANDA WebSocket binding
- [ ] Implement basic indicator calculation (SMA, EMA, RSI, MACD, Bollinger Bands)
- [ ] Create indicator library explorer UI
- [ ] Add backend `/api/v1/chart/indicators/calculate` endpoint

### Phase 2: Advanced Features (Week 2)
- [ ] Complete 30+ indicator library implementation
- [ ] Implement support/resistance detection algorithm
- [ ] Add strategy overlay visualization
- [ ] Create analysis tools toolbar (trendline, patterns, divergence)
- [ ] Real-time OANDA streaming via WebSocket

### Phase 3: Optimization & Polish (Week 3)
- [ ] Implement Web Workers for indicator calculation
- [ ] Add Redis caching layer
- [ ] Performance profiling & optimization
- [ ] Unit tests for all indicators
- [ ] UI/UX refinements and responsive design

### Phase 4: Integration & Deployment (Week 4)
- [ ] Integrate with existing strategy system
- [ ] Database schema updates (Fact_Indicator_Values, etc.)
- [ ] End-to-end testing with live OANDA data
- [ ] Documentation & user guide
- [ ] Production deployment

---

## TECHNOLOGY STACK DECISIONS

| Layer | Current | Proposed | Rationale |
|-------|---------|----------|-----------|
| Chart Rendering | lightweight-charts | lightweight-charts 4.2+ | Keep: it's excellent for OHLC, add canvas overlays |
| Indicators | Client-side | Server + Client (hybrid) | Reduce frontend burden, pre-cache in DB |
| Real-time Data | Polling (REST) | WebSocket (OANDA stream) | Lower latency, reduce API calls |
| State Management | React Context | Context + Zustand | Better performance for frequent updates |
| Analysis Tools | None | Canvas-based drawing lib | Custom or lightweight lib (Excalidraw concepts) |
| Caching | None | Redis + Browser IndexedDB | Instant load for repeated symbols |
| Background Tasks | None | Web Workers + Node Worker Threads | Keep UI thread at 60 FPS |

---

## TESTING REQUIREMENTS

- **Unit Tests**: All 30+ indicators against known inputs/outputs
- **Integration Tests**: Chart data flow (OANDA  Backend  Frontend)
- **Regression Tests**: Ensure existing strategy overlays still work
- **Performance Tests**: Render 10K candles with 5 indicators in < 2s
- **E2E Tests**: User workflows (symbol change, timeframe switch, indicator toggle)

---

## DEPLOYMENT CHECKLIST

- [ ] All OANDA credentials in .env (OANDA_API_KEY, OANDA_ACCOUNT_ID, OANDA_ENV)
- [ ] SQL Server schema updated with Fact_Indicator_Values, Dim_Indicator_Library
- [ ] Redis instance running (docker-compose or cloud)
- [ ] WebSocket endpoint configured (FastAPI or Socket.IO)
- [ ] Frontend build tested in production mode
- [ ] Cron job for hourly indicator pre-calculation
- [ ] Monitoring: WebSocket connection health, indicator calculation latency
- [ ] Rollback plan if OANDA API issues occur (fallback to cached data)

---

## SUCCESS METRICS

After implementation, the new chart system should achieve:
1. **Performance**: < 2s initial load, 60 FPS, < 50ms indicator calculation
2. **Features**: 30+ indicators, strategy overlays, analysis tools, real-time OANDA feed
3. **User Experience**: Intuitive toolbar, responsive controls, professional appearance
4. **Reliability**: 99.9% uptime, graceful degradation if OANDA unavailable
5. **Maintainability**: Modular code, comprehensive documentation, 80%+ test coverage

---

## HANDOFF NOTES

- This system should feel like a professional trading platform (TradingView quality)
- Prioritize user experience: smooth, responsive, no jank
- All data sources validated (OANDA vs DB vs cache)
- Keep current architecture patterns (Layer 5 API structure)
- Coordinate with existing trade execution (Layer 4) for entry/SL/TP visualization
- Consider future: live trade annotation, news feed integration, ML pattern detection

---

**Prepared by**: System Architect  
**Date**: April 6, 2026  
**Status**: Ready for Implementation  
**Permission Level**: FULL AUTHORIZATION TO MODIFY ALL COMPONENTS
