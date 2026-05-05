# Advanced Charting System Installation Guide - Swing Trading Dashboard

> **SWING TRADING SYSTEM** | Layer 5 Dashboard charting infrastructure for swing trade analysis

## Overview

This guide covers the installation and integration of the Advanced Charting System into the Scalable Brain swing trading platform. The advanced charting system provides real-time visualization for swing trading decisions:

- **30+ Technical Indicators** (RSI, MACD, Bollinger Bands, ADX, Stochastic, etc.)
- **13 Timeframes** (1m to 1M)
- **Professional Charting** with Lightweight Charts library
- **Alert System** for price and indicator-based notifications
- **Dark/Light Theme System**
- **Volume Profile Analysis**
- **Support/Resistance Auto-Detection**
- **Multi-Timeframe Analysis**

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Backend Installation](#2-backend-installation)
3. [Frontend Installation](#3-frontend-installation)
4. [Database Setup](#4-database-setup)
5. [Configuration](#5-configuration)
6. [Verification](#6-verification)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Prerequisites

### System Requirements

| Component | Minimum Version | Recommended |
|-----------|----------------|-------------|
| Python | 3.11+ | 3.12+ |
| Node.js | 18.x LTS | 20.x LTS |
| npm | 9.x | 10.x |
| SQL Server | 2019+ | 2022+ |
| Redis | 6.x | 7.x (optional) |

### Required Credentials

Before installation, ensure you have:

1. **OANDA API Credentials**
   - API Key (format: `xxxxxxxx-xxxxxxxxxxxxxxxx-xxxxxxxx`)
   - Account ID (format: `101-002-xxxxxxxx-001`)
   - Environment: `practice` or `live`

2. **Database Credentials**
   - Server address (e.g., `localhost` or `sql-server-host`)
   - Database name (e.g., `ForexBrainDB`)
   - Username and password with DDL permissions

### Verify Prerequisites

```bash
# Check Python version
python --version  # Should be 3.11+

# Check Node.js version
node --version    # Should be 18.x or higher

# Check npm version
npm --version     # Should be 9.x or higher

# Check database connectivity (if using SQL Server)
sqlcmd -S localhost -U sa -P your_password -Q "SELECT @@VERSION"
```

---

## 2. Backend Installation

### 2.1 New Python Dependencies

Add the following to your `requirements.txt`:

```txt
# Advanced Charting Dependencies (add to requirements.txt)
numpy>=1.24.0
pandas>=2.0.0
lightweight-charts>=4.1.6

# Optional: Redis for caching (recommended)
redis>=5.0.0
aioredis>=2.0.0

# Optional: Enhanced technical indicators
TA-Lib>=0.4.28
```

### 2.2 Install Python Dependencies

```bash
# Navigate to project root
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain

# Activate virtual environment (if using)
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate     # Windows

# Install new dependencies
pip install numpy pandas

# Optional: Install Redis client
pip install redis aioredis

# Optional: Install TA-Lib (requires system library)
# Ubuntu/Debian:
# sudo apt-get install ta-lib
# pip install TA-Lib

# macOS:
# brew install ta-lib
# pip install TA-Lib
```

### 2.3 Copy New Service Files

```bash
# Create services directory if not exists
mkdir -p src/layer5/services

# Copy new service files
cp newplannedlayer5upgrade/layer5_upgrade/services/chart_data_client.py src/layer5/services/
cp newplannedlayer5upgrade/layer5_upgrade/services/indicators_client.py src/layer5/services/
cp newplannedlayer5upgrade/layer5_upgrade/services/alerts_client.py src/layer5/services/

# Backup and update data_contracts.py
cp src/layer5/services/data_contracts.py src/layer5/services/data_contracts.py.backup
```

### 2.4 Update API Routes

```bash
# Create routes directory if not exists
mkdir -p src/layer5/api/routes

# Copy new route files
cp newplannedlayer5upgrade/layer5_upgrade/api/routes/charts.py src/layer5/api/routes/
cp newplannedlayer5upgrade/layer5_upgrade/api/routes/indicators.py src/layer5/api/routes/
cp newplannedlayer5upgrade/layer5_upgrade/api/routes/alerts.py src/layer5/api/routes/

# Backup and update main.py
cp src/layer5/api/main.py src/layer5/api/main.py.backup
cp newplannedlayer5upgrade/layer5_upgrade/api/main.py src/layer5/api/main.py
```

### 2.5 Backend File Structure After Installation

```
src/layer5/
 api/
    main.py              # UPDATED: Includes new routes
    config.py
    dependencies.py
    routes/
        __init__.py
        charts.py        # NEW: Chart data endpoints
        indicators.py    # NEW: Technical indicators
        alerts.py        # NEW: Alert management
        ... (existing routes)
 services/
     chart_data_client.py     # NEW: OHLC & volume data
     indicators_client.py     # NEW: 30+ indicators
     alerts_client.py         # NEW: Alert engine
     data_contracts.py        # UPDATED: New types
     ... (existing clients)
```

---

## 3. Frontend Installation

### 3.1 New npm Dependencies

The advanced charting system requires these additional packages:

```json
{
  "dependencies": {
    "lightweight-charts": "^4.1.6",
    "next-themes": "^0.3.0",
    "sonner": "^1.5.0"
  }
}
```

### 3.2 Install npm Dependencies

```bash
# Navigate to frontend directory
cd src/layer5/frontend

# Backup existing package.json
cp package.json package.json.backup.$(date +%Y%m%d_%H%M%S)

# Install new dependencies
npm install lightweight-charts next-themes sonner

# Verify installation
npm list lightweight-charts next-themes sonner
```

### 3.3 Copy New Components

```bash
# From project root
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain

# Backup existing components
cp -r src/layer5/frontend/src/components src/layer5/frontend/src/components.backup.$(date +%Y%m%d_%H%M%S)

# Copy new chart components
cp -r newplannedlayer5upgrade/layer5_upgrade/frontend/src/components/charts src/layer5/frontend/src/components/

# Copy new view components
cp newplannedlayer5upgrade/layer5_upgrade/frontend/src/components/views/ChartsView.tsx src/layer5/frontend/src/components/views/
cp newplannedlayer5upgrade/layer5_upgrade/frontend/src/components/views/AlertsView.tsx src/layer5/frontend/src/components/views/
cp newplannedlayer5upgrade/layer5_upgrade/frontend/src/components/views/EnhancedWatchlist.tsx src/layer5/frontend/src/components/views/

# Copy new layout components
cp newplannedlayer5upgrade/layer5_upgrade/frontend/src/components/layout/ThemeToggle.tsx src/layer5/frontend/src/components/layout/

# Copy new hooks
cp -r newplannedlayer5upgrade/layer5_upgrade/frontend/src/hooks src/layer5/frontend/src/

# Copy updated services
cp newplannedlayer5upgrade/layer5_upgrade/frontend/src/services/api.ts src/layer5/frontend/src/services/

# Copy updated types
cp newplannedlayer5upgrade/layer5_upgrade/frontend/src/types/index.ts src/layer5/frontend/src/types/
```

### 3.4 Vite Configuration Updates

The Vite configuration needs updates for Web Workers support (used for indicator calculations):

```typescript
// vite.config.ts - Key updates needed
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    // Web Workers configuration
    rollupOptions: {
      output: {
        manualChunks: {
          'lightweight-charts': ['lightweight-charts'],
        },
      },
    },
  },
  // Web Workers support
  worker: {
    format: 'es',
  },
})
```

Apply the configuration:

```bash
# Backup existing config
cp src/layer5/frontend/vite.config.ts src/layer5/frontend/vite.config.ts.backup

# Copy new config
cp newplannedlayer5upgrade/layer5_upgrade/frontend/vite.config.ts src/layer5/frontend/
```

### 3.5 TypeScript Configuration

Verify your `tsconfig.json` includes proper path mapping:

```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    },
    "lib": ["ES2020", "DOM", "DOM.Iterable", "WebWorker"],
    "target": "ES2020",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "allowSyntheticDefaultImports": true,
    "esModuleInterop": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"],
  "references": [
    { "path": "./tsconfig.node.json" }
  ]
}
```

### 3.6 Tailwind CSS Configuration

Ensure Tailwind is configured for the theme system:

```javascript
// tailwind.config.js
/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Chart colors
        chart: {
          up: "#22C55E",
          down: "#EF4444",
          grid: "rgba(255, 255, 255, 0.06)",
        },
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}
```

### 3.7 Frontend File Structure After Installation

```
src/layer5/frontend/src/
 components/
    charts/
       TradingChart.tsx       # NEW: Main chart component
       IndicatorPanel.tsx     # NEW: Indicator selector
       index.ts
    layout/
       Sidebar.tsx            # UPDATED: New nav items
       TopBar.tsx
       ThemeToggle.tsx        # NEW: Theme switcher
    views/
        ChartsView.tsx         # NEW: Full charting view
        AlertsView.tsx         # NEW: Alert management
        EnhancedWatchlist.tsx  # NEW: Watchlist upgrade
        ... (existing views)
 hooks/
    useTheme.tsx               # NEW: Theme management
    ... (existing hooks)
 services/
    api.ts                     # UPDATED: New endpoints
 types/
    index.ts                   # UPDATED: New types
 ... (existing files)
```

---

## 4. Database Setup

### 4.1 New Tables Required

The advanced charting system requires the following new tables:

#### Dim_Indicator_Library
```sql
CREATE TABLE Dim_Indicator_Library (
    Indicator_ID INT PRIMARY KEY IDENTITY(1,1),
    Indicator_Name VARCHAR(50) NOT NULL,
    Category VARCHAR(20) NOT NULL CHECK (Category IN ('trend', 'momentum', 'volatility', 'volume')),
    Description VARCHAR(500),
    Default_Params NVARCHAR(MAX),
    Is_Active BIT DEFAULT 1,
    Created_At DATETIME DEFAULT GETDATE()
);
```

#### Fact_Indicator_Values
```sql
CREATE TABLE Fact_Indicator_Values (
    Value_ID BIGINT PRIMARY KEY IDENTITY(1,1),
    Timestamp DATETIME NOT NULL,
    Asset_ID INT NOT NULL,
    Indicator_ID INT NOT NULL,
    Timeframe VARCHAR(10) NOT NULL,
    Parameters NVARCHAR(MAX),
    Values_JSON NVARCHAR(MAX),
    Created_At DATETIME DEFAULT GETDATE(),
    CONSTRAINT FK_IndicatorValues_Asset FOREIGN KEY (Asset_ID) REFERENCES Dim_Asset(Asset_ID),
    CONSTRAINT FK_IndicatorValues_Indicator FOREIGN KEY (Indicator_ID) REFERENCES Dim_Indicator_Library(Indicator_ID)
);

CREATE INDEX IX_IndicatorValues_Lookup ON Fact_Indicator_Values(Asset_ID, Indicator_ID, Timeframe, Timestamp);
```

#### Fact_Analysis_Metrics
```sql
CREATE TABLE Fact_Analysis_Metrics (
    Metric_ID BIGINT PRIMARY KEY IDENTITY(1,1),
    Timestamp DATETIME NOT NULL,
    Asset_ID INT NOT NULL,
    Metric_Type VARCHAR(20) NOT NULL CHECK (Metric_Type IN ('correlation', 'volatility', 'strength', 'momentum')),
    Period VARCHAR(10) NOT NULL,
    Value FLOAT NOT NULL,
    Unit VARCHAR(20),
    Signal VARCHAR(10),
    Threshold FLOAT,
    Created_At DATETIME DEFAULT GETDATE(),
    CONSTRAINT FK_AnalysisMetrics_Asset FOREIGN KEY (Asset_ID) REFERENCES Dim_Asset(Asset_ID)
);

CREATE INDEX IX_AnalysisMetrics_Lookup ON Fact_Analysis_Metrics(Asset_ID, Metric_Type, Period, Timestamp);
```

### 4.2 SQL Migration Script

Save this as `migrations/004_advanced_charts.sql`:

```sql
/*
=============================================================================
Migration: Advanced Charting System
Version: 1.0.0
Description: Creates tables for technical indicators and analysis metrics
=============================================================================
*/

USE ForexBrainDB;
GO

-- ==========================================
-- 1. Dimension Table: Indicator Library
-- ==========================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Dim_Indicator_Library')
BEGIN
    CREATE TABLE Dim_Indicator_Library (
        Indicator_ID INT PRIMARY KEY IDENTITY(1,1),
        Indicator_Name VARCHAR(50) NOT NULL UNIQUE,
        Category VARCHAR(20) NOT NULL CHECK (Category IN ('trend', 'momentum', 'volatility', 'volume')),
        Description VARCHAR(500),
        Formula VARCHAR(200),
        Interpretation VARCHAR(500),
        Default_Params NVARCHAR(MAX),
        Param_Ranges NVARCHAR(MAX),
        Is_Active BIT DEFAULT 1,
        Created_At DATETIME DEFAULT GETDATE(),
        Updated_At DATETIME DEFAULT GETDATE()
    );
    
    -- Insert default indicators
    INSERT INTO Dim_Indicator_Library (Indicator_Name, Category, Description, Default_Params) VALUES
    ('sma', 'trend', 'Simple Moving Average', '{"period": 20}'),
    ('ema', 'trend', 'Exponential Moving Average', '{"period": 20}'),
    ('macd', 'trend', 'Moving Average Convergence Divergence', '{"fast": 12, "slow": 26, "signal": 9}'),
    ('adx', 'trend', 'Average Directional Index', '{"period": 14}'),
    ('rsi', 'momentum', 'Relative Strength Index', '{"period": 14, "overbought": 70, "oversold": 30}'),
    ('stochastic', 'momentum', 'Stochastic Oscillator', '{"kPeriod": 14, "dPeriod": 3}'),
    ('bollinger', 'volatility', 'Bollinger Bands', '{"period": 20, "stdDev": 2.0}'),
    ('atr', 'volatility', 'Average True Range', '{"period": 14}'),
    ('obv', 'volume', 'On-Balance Volume', '{}');
END
GO

-- ==========================================
-- 2. Fact Table: Indicator Values
-- ==========================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Fact_Indicator_Values')
BEGIN
    CREATE TABLE Fact_Indicator_Values (
        Value_ID BIGINT PRIMARY KEY IDENTITY(1,1),
        Timestamp DATETIME NOT NULL,
        Asset_ID INT NOT NULL,
        Indicator_ID INT NOT NULL,
        Timeframe VARCHAR(10) NOT NULL,
        Parameters NVARCHAR(MAX),
        Values_JSON NVARCHAR(MAX),
        Created_At DATETIME DEFAULT GETDATE(),
        CONSTRAINT FK_IndicatorValues_Asset FOREIGN KEY (Asset_ID) REFERENCES Dim_Asset(Asset_ID),
        CONSTRAINT FK_IndicatorValues_Indicator FOREIGN KEY (Indicator_ID) REFERENCES Dim_Indicator_Library(Indicator_ID)
    );
    
    CREATE INDEX IX_IndicatorValues_Lookup ON Fact_Indicator_Values(Asset_ID, Indicator_ID, Timeframe, Timestamp);
    CREATE INDEX IX_IndicatorValues_Timestamp ON Fact_Indicator_Values(Timestamp);
END
GO

-- ==========================================
-- 3. Fact Table: Analysis Metrics
-- ==========================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Fact_Analysis_Metrics')
BEGIN
    CREATE TABLE Fact_Analysis_Metrics (
        Metric_ID BIGINT PRIMARY KEY IDENTITY(1,1),
        Timestamp DATETIME NOT NULL,
        Asset_ID INT NOT NULL,
        Metric_Type VARCHAR(20) NOT NULL CHECK (Metric_Type IN ('correlation', 'volatility', 'strength', 'momentum')),
        Period VARCHAR(10) NOT NULL,
        Value FLOAT NOT NULL,
        Unit VARCHAR(20),
        Signal VARCHAR(10),
        Threshold FLOAT,
        Metadata_JSON NVARCHAR(MAX),
        Created_At DATETIME DEFAULT GETDATE(),
        CONSTRAINT FK_AnalysisMetrics_Asset FOREIGN KEY (Asset_ID) REFERENCES Dim_Asset(Asset_ID)
    );
    
    CREATE INDEX IX_AnalysisMetrics_Lookup ON Fact_Analysis_Metrics(Asset_ID, Metric_Type, Period, Timestamp);
    CREATE INDEX IX_AnalysisMetrics_Timestamp ON Fact_Analysis_Metrics(Timestamp);
END
GO

-- ==========================================
-- 4. Alerts Table (if not exists)
-- ==========================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Dim_Alert_Configs')
BEGIN
    CREATE TABLE Dim_Alert_Configs (
        Alert_ID VARCHAR(50) PRIMARY KEY,
        Name VARCHAR(100) NOT NULL,
        Alert_Type VARCHAR(20) NOT NULL CHECK (Alert_Type IN ('price', 'indicator', 'pattern', 'volume')),
        Asset_ID INT NOT NULL,
        Condition_Type VARCHAR(20) NOT NULL CHECK (Condition_Type IN ('above', 'below', 'crosses_above', 'crosses_below', 'equals')),
        Target_Value FLOAT NOT NULL,
        Timeframe VARCHAR(10) DEFAULT '1h',
        Message VARCHAR(500),
        Status VARCHAR(20) DEFAULT 'active' CHECK (Status IN ('active', 'triggered', 'paused', 'expired')),
        Expires_At DATETIME,
        Created_At DATETIME DEFAULT GETDATE(),
        Triggered_At DATETIME,
        Triggered_Price FLOAT,
        CONSTRAINT FK_Alerts_Asset FOREIGN KEY (Asset_ID) REFERENCES Dim_Asset(Asset_ID)
    );
    
    CREATE INDEX IX_Alerts_Status ON Dim_Alert_Configs(Status);
    CREATE INDEX IX_Alerts_Asset ON Dim_Alert_Configs(Asset_ID);
END
GO

PRINT 'Advanced Charting System tables created successfully.';
```

### 4.3 Run Migration

```bash
# Using sqlcmd (SQL Server)
sqlcmd -S localhost -U sa -P your_password -i migrations/004_advanced_charts.sql

# Or using Python with pyodbc
python -c "
import pyodbc
with open('migrations/004_advanced_charts.sql', 'r') as f:
    script = f.read()
conn = pyodbc.connect('DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;DATABASE=ForexBrainDB;UID=sa;PWD=your_password;TrustServerCertificate=yes')
cursor = conn.cursor()
for statement in script.split('GO'):
    if statement.strip():
        cursor.execute(statement)
conn.commit()
print('Migration completed successfully')
"
```

---

## 5. Configuration

### 5.1 Environment Variables (.env)

Add these to your existing `.env` file:

```bash
# ==========================================
# Advanced Charting Configuration
# ==========================================

# Chart Data Settings
CHART_MAX_CANDLES=5000
CHART_DEFAULT_LIMIT=500
CHART_CACHE_TTL=300

# Indicator Settings
INDICATOR_MAX_PERIOD=200
INDICATOR_CACHE_ENABLED=true
INDICATOR_CACHE_TTL=600

# Alert System
ALERTS_ENABLED=true
ALERTS_CHECK_INTERVAL=30
ALERTS_RETENTION_DAYS=30

# Redis (Optional but Recommended)
REDIS_URL=redis://localhost:6379/0
REDIS_ENABLED=true
REDIS_TTL=300

# OANDA Streaming (for live chart data)
OANDA_STREAM_ENABLED=true
OANDA_STREAM_RETRY_INTERVAL=5

# Theme Default
DEFAULT_THEME=dark
```

### 5.2 OANDA API Setup

Verify your OANDA credentials in `.env`:

```bash
OANDA_API_KEY=your_api_key_here
OANDA_ACCOUNT_ID=your_account_id_here
OANDA_ENV=practice  # or 'live' for production
OANDA_URL=https://api-fxpractice.oanda.com  # or api-fxtrade.oanda.com
```

### 5.3 Redis Configuration (Optional)

If using Redis for caching:

```bash
# Install Redis
# Ubuntu/Debian:
sudo apt-get install redis-server

# macOS:
brew install redis

# Start Redis
redis-server

# Test connection
redis-cli ping
# Should return: PONG
```

Update `src/layer5/api/config.py`:

```python
# Add to config.py
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "false").lower() == "true"
CHART_CACHE_TTL = int(os.getenv("CHART_CACHE_TTL", "300"))
```

---

## 6. Verification

### 6.1 Backend Verification

```bash
# Start the backend
python src/layer5/run.py

# In another terminal, test endpoints:

# Test health endpoint
curl http://localhost:8001/health
# Expected: {"status": "ok", "layer": 5}

# Test OHLC endpoint
curl "http://localhost:8001/api/v1/charts/ohlc?symbol=EUR_USD&timeframe=1h&limit=100"
# Expected: Array of OHLC data

# Test indicators list
curl http://localhost:8001/api/v1/indicators/list
# Expected: Array of available indicators

# Test calculate indicator
curl -X POST "http://localhost:8001/api/v1/indicators/calculate?symbol=EUR_USD&indicator=rsi&timeframe=1h" \
  -H "Content-Type: application/json" \
  -d '{"period": 14}'
# Expected: RSI values with timestamps

# Test support/resistance
curl "http://localhost:8001/api/v1/charts/support-resistance?symbol=EUR_USD&timeframe=1h"
# Expected: Array of S/R levels

# Test volume profile
curl "http://localhost:8001/api/v1/charts/volume-profile?symbol=EUR_USD&rows=24"
# Expected: Volume at price data
```

### 6.2 Frontend Verification

```bash
# Navigate to frontend
cd src/layer5/frontend

# Start development server
npm run dev

# Expected output:
# VITE v5.x.x  ready in xxx ms
#   Local:   http://localhost:5173/
#   Network: use --host to expose
```

Open browser and verify:

1. **Charts View**: Navigate to `http://localhost:5173/charts`
   - Verify chart renders with candlesticks
   - Test timeframe switching (1m, 5m, 15m, 1h, etc.)
   - Test indicator addition (SMA, RSI, MACD, etc.)

2. **Alerts View**: Navigate to `http://localhost:5173/alerts`
   - Create a test alert
   - Verify alert appears in list

3. **Theme Toggle**: Click theme button in sidebar
   - Verify dark/light mode switches

### 6.3 Expected Output Examples

#### OHLC Data Response
```json
[
  {
    "timestamp": "2024-01-15T10:00:00",
    "open": 1.0850,
    "high": 1.0865,
    "low": 1.0845,
    "close": 1.0860,
    "volume": 1250
  }
]
```

#### Indicator Response
```json
{
  "indicator": "rsi",
  "name": "RSI(14)",
  "timestamps": [...],
  "values": [65.4, 62.1, 58.9, ...],
  "params": {"period": 14},
  "overbought": 70,
  "oversold": 30
}
```

#### Support/Resistance Response
```json
[
  {
    "price": 1.0850,
    "type": "support",
    "strength": 0.85,
    "touches": 5,
    "firstTouch": "2024-01-10T08:00:00",
    "lastTouch": "2024-01-15T14:00:00",
    "isActive": true,
    "distancePct": 0.5
  }
]
```

---

## 7. Troubleshooting

### Common Issues

#### Issue: `ModuleNotFoundError: No module named 'layer5'`

**Solution**: Ensure Python path is set correctly:

```bash
export PYTHONPATH="${PYTHONPATH}:/home/emmanuel/Documents/Scalable_Brain/scalable-brain/src"
# Or in Windows:
set PYTHONPATH=%PYTHONPATH%;C:\path\to\scalable-brain\src
```

#### Issue: Chart shows "No data available"

**Solution**: 
1. Verify database connection
2. Check that `Fact_Market_Prices` has data for the symbol
3. Verify OANDA credentials for live data

```sql
-- Check for price data
SELECT TOP 10 * FROM Fact_Market_Prices 
WHERE Asset_ID = (SELECT Asset_ID FROM Dim_Asset WHERE Symbol = 'EUR_USD')
ORDER BY Timestamp DESC;
```

#### Issue: Indicators not calculating

**Solution**:
1. Verify numpy/pandas installed: `pip list | grep numpy`
2. Check indicator parameters are valid
3. Review backend logs for calculation errors

#### Issue: Frontend build fails

**Solution**:
```bash
# Clear npm cache
npm cache clean --force

# Delete node_modules and reinstall
rm -rf node_modules package-lock.json
npm install

# Verify TypeScript compilation
npx tsc --noEmit
```

#### Issue: Theme not persisting

**Solution**: Check localStorage in browser DevTools:
```javascript
// In browser console
localStorage.getItem('theme')
// Should return: 'dark', 'light', or 'system'
```

#### Issue: WebSocket streaming not working

**Solution**:
1. Verify OANDA streaming is enabled in `.env`
2. Check network tab for WebSocket connections
3. Review CORS settings in backend

### Performance Tuning

#### Database Query Optimization

```sql
-- Create additional indexes for performance
CREATE INDEX IX_Prices_Lookup ON Fact_Market_Prices(Asset_ID, Timestamp DESC);
CREATE INDEX IX_Regimes_Lookup ON Fact_Market_Regime(Asset_ID, Timestamp DESC);
```

#### Frontend Optimization

```typescript
// Lazy load chart components
const TradingChart = lazy(() => import('@/components/charts/TradingChart'));

// Use React.memo for indicator panels
export const IndicatorPanel = memo(IndicatorPanelComponent);
```

### Support Resources

- **API Documentation**: `http://localhost:8001/docs` (when backend is running)
- **Frontend Issues**: Check browser console (F12)
- **Backend Issues**: Check logs in `logs/` directory
- **Database Issues**: Use SQL Server Profiler or query logs

---

## Quick Reference

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/charts/ohlc` | GET | OHLC candlestick data |
| `/api/v1/charts/price-history` | GET | Simplified price history |
| `/api/v1/charts/volume-profile` | GET | Volume at price analysis |
| `/api/v1/charts/symbols` | GET | Available symbols |
| `/api/v1/charts/multi-timeframe` | GET | Multi-TF data |
| `/api/v1/charts/support-resistance` | GET | S/R levels |
| `/api/v1/charts/analysis-metrics` | GET | Correlation, volatility, strength |
| `/api/v1/indicators/list` | GET | Available indicators |
| `/api/v1/indicators/calculate` | POST | Calculate single indicator |
| `/api/v1/indicators/calculate-batch` | POST | Calculate multiple indicators |
| `/api/v1/alerts/` | GET/POST | List/Create alerts |
| `/api/v1/alerts/{id}` | DELETE | Delete alert |
| `/api/v1/alerts/triggered` | GET | Triggered alerts |

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `1` | Overview |
| `2` | Charts |
| `3` | Assets |
| `4` | Trades |
| `5` | Strategies |
| `6` | Risk |
| `7` | Regimes |
| `8` | Model |
| `9` | Alerts |
| `R` | Refresh data |
| `F` | Toggle fullscreen chart |
| `T` | Toggle theme |

---

## Summary

After completing this installation:

1.  Backend API has new charting endpoints
2.  Frontend has professional charting components
3.  Database has indicator and metrics tables
4.  Alert system is configured
5.  Theme system is operational
6.  All Layer 1-4 connections are preserved

**Next Steps**: 
- Test with real trading data
- Configure custom indicators
- Set up price alerts
- Explore multi-timeframe analysis

For additional help, refer to:
- `UPGRADE_SUMMARY.md` - Feature overview
- `INTEGRATION_PLAN.md` - Architecture details
- API docs at `/docs` when server is running
