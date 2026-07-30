import { useState, useEffect, useCallback, useMemo } from 'react';
import { CustomChart, type Granularity, type ChartTool } from '@/components/charts/CustomChart';
import { IndicatorPanel } from '@/components/charts/IndicatorPanel';
import { useChartStream } from '@/hooks/useChartStream';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Separator } from '@/components/ui/separator';
import { 
  chartAPI, 
  indicatorAPI,
} from '@/services/api';
import { oandaChartAPI, oandaIndicatorAPI, oandaTradeAPI } from '@/services/oandaApi';
import { toast } from 'sonner';
import type { 
  OHLCData, 
  IndicatorResult,
  SupportResistanceLevel,
} from '@/types';
import { 
  TrendingUp, 
  TrendingDown, 
  Activity, 
  BarChart3, 
  Layers,
  Target,
  Wifi,
  WifiOff,
  Settings,
  Filter,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  Clock,
  Scale,
  Gauge,
  DollarSign,
} from 'lucide-react';
import { cn } from '@/lib/utils';

// =============================================================================
// Types
// =============================================================================

interface ChartsViewProps {
  symbol: string;
  timeframe: string;
  onSymbolChange: (symbol: string) => void;
  onTimeframeChange: (timeframe: string) => void;
  // Optional filter by positions
  filterByPositions?: boolean;
  openPositions?: string[];
}

interface IndicatorWithData {
  id: string;
  name: string;
  params: Record<string, number>;
  color: string;
  category: 'trend' | 'momentum' | 'volatility' | 'volume';
  values?: (number | null)[];
  upper?: (number | null)[];
  middle?: (number | null)[];
  lower?: (number | null)[];
  signal?: (number | null)[];
  histogram?: (number | null)[];
  timestamps?: string[];
}

interface TradeMarker {
  id: string;
  type: 'entry' | 'sl' | 'tp' | 'win' | 'loss';
  price: number;
  timestamp: string;
  side?: 'long' | 'short';
  label?: string;
}

// =============================================================================
// CONSTANTS
// =============================================================================

// Only allow these 5 currency pairs
const ALLOWED_PAIRS = [
  { value: 'EUR_USD', label: 'EUR/USD' },
  { value: 'GBP_USD', label: 'GBP/USD' },
  { value: 'USD_JPY', label: 'USD/JPY' },
  { value: 'AUD_USD', label: 'AUD/USD' },
  { value: 'USD_CAD', label: 'USD/CAD' },
];

const TIMEFRAMES: { value: Granularity; label: string }[] = [
  { value: '1m', label: '1m' },
  { value: '5m', label: '5m' },
  { value: '15m', label: '15m' },
  { value: '30m', label: '30m' },
  { value: '1h', label: '1H' },
  { value: '4h', label: '4H' },
  { value: '1d', label: '1D' },
];

const INDICATOR_COLORS = [
  '#3B82F6', // blue
  '#F59E0B', // amber
  '#8B5CF6', // violet
  '#EC4899', // pink
  '#10B981', // emerald
  '#06B6D4', // cyan
  '#F97316', // orange
];

// =============================================================================
// COMPONENT
// =============================================================================

export function ChartsView({
  symbol,
  timeframe,
  onSymbolChange,
  onTimeframeChange,
  filterByPositions = false,
  openPositions = [],
}: ChartsViewProps) {
  // ==========================================================================
  // State
  // ==========================================================================
  
  // Data state
  const [ohlcData, setOhlcData] = useState<OHLCData[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [historicalData, setHistoricalData] = useState<OHLCData[]>([]);
  
  // Indicator state
  const [activeIndicators, setActiveIndicators] = useState<IndicatorWithData[]>([]);
  const [indicatorResults, setIndicatorResults] = useState<IndicatorResult[]>([]);
  
  // Analysis state
  const [activeTool, setActiveTool] = useState<'cursor' | 'trendline' | 'horizontal' | 'fibonacci' | 'pan' | null>('cursor');
  const [drawnTools, setDrawnTools] = useState<ChartTool[]>([]);
  const [supportResistanceLevels, setSupportResistanceLevels] = useState<SupportResistanceLevel[]>([]);
  const [showSupportResistance, setShowSupportResistance] = useState(false);
  
  // Trade markers
  const [tradeMarkers, setTradeMarkers] = useState<TradeMarker[]>([]);
  const [showTradeMarkers, setShowTradeMarkers] = useState(true);
  
  // Real-time state
  const [useRealtime, setUseRealtime] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  
  // UI state
  const [showIndicatorPanel, setShowIndicatorPanel] = useState(true);
  const [currentPrice, setCurrentPrice] = useState<number>(0);

  // ==========================================================================
  // Hooks
  // ==========================================================================
  
  // Real-time WebSocket stream
  const { 
    currentPrice: streamedPrice,
    isConnected: isStreamConnected,
    connectionState,
    error: streamError,
  } = useChartStream({
    symbol,
    timeframe: timeframe as Granularity,
    enabled: useRealtime,
  });

  // ==========================================================================
  // Data Fetching
  // ==========================================================================

  // Fetch OHLC data when symbol/timeframe changes
  useEffect(() => {
    fetchOHLCData();
    fetchTradeMarkers();
  }, [symbol, timeframe]);

  // Calculate indicators when they change
  useEffect(() => {
    if (activeIndicators.length > 0 && ohlcData.length > 0) {
      calculateIndicators();
    }
  }, [activeIndicators, ohlcData]);

  // Update current price from stream
  useEffect(() => {
    if (useRealtime && streamedPrice > 0) {
      setCurrentPrice(streamedPrice);
    } else if (ohlcData.length > 0) {
      setCurrentPrice(ohlcData[ohlcData.length - 1].close);
    }
  }, [streamedPrice, ohlcData, useRealtime]);

  // ==========================================================================
  // API Functions
  // ==========================================================================

  const fetchOHLCData = async () => {
    if (!symbol || !timeframe) return;
    
    setIsLoading(true);
    try {
      // Try to get data from OANDA first for real-time data
      let data: OHLCData[] = [];
      try {
        const granularity = mapTimeframeToOanda(timeframe as Granularity);
        const oandaData = await oandaChartAPI.getOandaCandles(symbol, granularity, 500);
        if (oandaData.length > 0) {
          data = oandaData;
        }
      } catch (e) {
        // Fall back to database
        console.log('Falling back to database for OHLC data');
      }
      
      // If OANDA failed or returned empty, use database
      if (data.length === 0) {
        data = await chartAPI.getOHLC(symbol, timeframe, 500);
      }
      
      setOhlcData(data);
      if (data.length > 0) {
        setCurrentPrice(data[data.length - 1].close);
      }
    } catch (error) {
      toast.error(`Failed to load chart data for ${symbol}`);
      console.error(error);
    } finally {
      setIsLoading(false);
    }
  };

  const fetchTradeMarkers = async () => {
    if (!symbol) return;
    
    try {
      const markers = await oandaTradeAPI.getTradeMarkers(symbol);
      setTradeMarkers(markers);
    } catch (error) {
      // Silently fail - trade markers are optional
      console.warn('Failed to load trade markers:', error);
    }
  };

  const calculateIndicators = async () => {
    if (activeIndicators.length === 0) return;

    try {
      const indicators = activeIndicators.map(ind => ({
        indicator: ind.id,
        params: ind.params,
      }));

      const results = await oandaIndicatorAPI.calculateBatch(
        symbol,
        timeframe,
        indicators
      );

      // Map results to extended format
      const extendedResults: IndicatorWithData[] = results.map((result, index) => ({
        id: activeIndicators[index].id,
        name: activeIndicators[index].name,
        params: activeIndicators[index].params,
        color: activeIndicators[index].color || INDICATOR_COLORS[index % INDICATOR_COLORS.length],
        category: activeIndicators[index].category,
        values: result.values,
        upper: result.upper,
        middle: result.middle,
        lower: result.lower,
        signal: result.signal,
        histogram: result.histogram,
        timestamps: result.timestamps,
      }));

      setIndicatorResults(extendedResults);
    } catch (error) {
      toast.error('Failed to calculate indicators');
      console.error(error);
    }
  };

  const fetchSupportResistance = async () => {
    if (!showSupportResistance) return;
    
    try {
      const { support, resistance } = await oandaTradeAPI.getSupportResistance(symbol, timeframe);
      const levels: SupportResistanceLevel[] = [
        ...support.map(s => ({ ...s, type: 'support' as const })),
        ...resistance.map(r => ({ ...r, type: 'resistance' as const })),
      ];
      setSupportResistanceLevels(levels);
    } catch (error) {
      toast.error('Failed to load support/resistance levels');
    }
  };

  // ==========================================================================
  // Event Handlers
  // ==========================================================================

  const handleAddIndicator = (
    indicator: { 
      id: string; 
      name: string; 
      category: 'trend' | 'momentum' | 'volatility' | 'volume'; 
      defaultParams: Record<string, number> 
    },
    params: Record<string, number>
  ) => {
    const newIndicator: IndicatorWithData = {
      id: `${indicator.id}_${Date.now()}`,
      name: indicator.name,
      params,
      color: INDICATOR_COLORS[activeIndicators.length % INDICATOR_COLORS.length],
      category: indicator.category,
    };
    
    setActiveIndicators(prev => [...prev, newIndicator]);
    toast.success(`Added ${indicator.name}`);
  };

  const handleRemoveIndicator = (id: string) => {
    setActiveIndicators(prev => prev.filter(ind => ind.id !== id));
    setIndicatorResults(prev => prev.filter(ind => ind.id !== id));
  };

  const handleDrawTool = (tool: ChartTool) => {
    setDrawnTools(prev => [...prev, tool]);
  };

  const handleRemoveTool = (id: string) => {
    setDrawnTools(prev => prev.filter(t => t.id !== id));
  };

  // ==========================================================================
  // Derived Data
  // ==========================================================================

  const priceStats = useMemo(() => {
    if (ohlcData.length === 0) {
      return { change: 0, changePct: 0, high: 0, low: 0, volume: 0 };
    }
    
    const current = ohlcData[ohlcData.length - 1].close;
    const previous = ohlcData.length > 1 ? ohlcData[ohlcData.length - 2].close : current;
    const change = current - previous;
    const changePct = previous > 0 ? (change / previous) * 100 : 0;
    
    const high = Math.max(...ohlcData.map(d => d.high));
    const low = Math.min(...ohlcData.map(d => d.low));
    const volume = ohlcData.reduce((sum, d) => sum + d.volume, 0);
    
    return { change, changePct, high, low, volume };
  }, [ohlcData]);

  // Filter pairs if filterByPositions is enabled
  const availablePairs = useMemo(() => {
    if (filterByPositions && openPositions.length > 0) {
      return ALLOWED_PAIRS.filter(p => openPositions.includes(p.value));
    }
    return ALLOWED_PAIRS;
  }, [filterByPositions, openPositions]);

  // ==========================================================================
  // Render Helpers
  // ==========================================================================

  const formatPrice = (price: number): string => {
    const decimals = symbol.includes('JPY') ? 3 : 5;
    return price.toFixed(decimals);
  };

  // ==========================================================================
  // Render
  // ==========================================================================

  return (
    <div className={cn(
      "h-full flex flex-col gap-2 p-2",
      isFullscreen && "fixed inset-0 z-50 bg-background"
    )}>
      {/* Header Toolbar */}
      <div className="flex items-center justify-between bg-card p-3 rounded-lg border border-border shrink-0">
        <div className="flex items-center gap-6">
          {/* Symbol & Price */}
          <div className="flex items-center gap-4">
            {/* Asset Selector - Only show allowed pairs */}
            <div>
              <select
                value={symbol}
                onChange={(e) => onSymbolChange(e.target.value)}
                className="bg-muted border border-border rounded px-3 py-1.5 text-lg font-bold"
              >
                {availablePairs.map(pair => (
                  <option key={pair.value} value={pair.value}>
                    {pair.label}
                  </option>
                ))}
              </select>
              <p className="text-sm text-muted-foreground">{timeframe} Chart</p>
            </div>

            {/* Current Price */}
            <div className="flex items-center gap-4">
              <div>
                <p className="text-2xl font-mono font-semibold">
                  {formatPrice(currentPrice)}
                </p>
                <p className={cn(
                  "text-sm font-medium flex items-center gap-1",
                  priceStats.change >= 0 ? 'text-green-500' : 'text-red-500'
                )}>
                  {priceStats.change >= 0 ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                  {priceStats.change >= 0 ? '+' : ''}{priceStats.change.toFixed(symbol.includes('JPY') ? 3 : 5)} 
                  ({priceStats.changePct >= 0 ? '+' : ''}{priceStats.changePct.toFixed(2)}%)
                </p>
              </div>
            </div>
          </div>

          {/* Stats */}
          <div className="flex items-center gap-6 text-sm">
            <div className="text-right">
              <p className="text-muted-foreground text-xs">High</p>
              <p className="font-mono font-medium">{formatPrice(priceStats.high)}</p>
            </div>
            <div className="text-right">
              <p className="text-muted-foreground text-xs">Low</p>
              <p className="font-mono font-medium">{formatPrice(priceStats.low)}</p>
            </div>
            <div className="text-right">
              <p className="text-muted-foreground text-xs">Volume</p>
              <p className="font-mono font-medium">{priceStats.volume.toLocaleString()}</p>
            </div>
          </div>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-3">
          {/* Real-time Toggle */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-muted">
            {isStreamConnected ? (
              <Wifi className="h-4 w-4 text-green-500" />
            ) : (
              <WifiOff className="h-4 w-4 text-muted-foreground" />
            )}
            <span className="text-sm">Live</span>
            <Switch
              checked={useRealtime}
              onCheckedChange={setUseRealtime}
            />
          </div>

          {/* Trade Markers Toggle */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-muted">
            <Target className="h-4 w-4" />
            <span className="text-sm">Trades</span>
            <Switch
              checked={showTradeMarkers}
              onCheckedChange={setShowTradeMarkers}
            />
          </div>

          {/* S/R Toggle */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-muted">
            <Scale className="h-4 w-4" />
            <span className="text-sm">S/R</span>
            <Switch
              checked={showSupportResistance}
              onCheckedChange={(checked) => {
                setShowSupportResistance(checked);
                if (checked) fetchSupportResistance();
              }}
            />
          </div>

          {/* Fullscreen */}
          <Button
            variant="ghost"
            size="icon"
            className="h-9 w-9"
            onClick={() => setIsFullscreen(!isFullscreen)}
          >
            {isFullscreen ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      {/* Connection Status */}
      {useRealtime && connectionState !== 'connected' && (
        <div className="shrink-0">
          <Badge 
            variant={connectionState === 'connecting' ? 'outline' : 'destructive'}
            className="animate-pulse"
          >
            {connectionState === 'connecting' ? 'Connecting to OANDA...' : 'Disconnected'}
          </Badge>
        </div>
      )}

      {/* Main Content */}
      <div className="flex-1 flex gap-2 min-h-0">
        {/* Left - Chart */}
        <div className="flex-1 min-w-0 flex flex-col gap-2">
          <CustomChart
            symbol={symbol}
            timeframe={timeframe as Granularity}
            data={ohlcData}
            isLoading={isLoading}
            currentPrice={currentPrice}
            activeIndicators={indicatorResults}
            tradeMarkers={tradeMarkers}
            showTradeMarkers={showTradeMarkers}
            supportResistanceLevels={supportResistanceLevels}
            showSupportResistance={showSupportResistance}
            activeTool={activeTool}
            onToolChange={setActiveTool}
            onDrawTool={handleDrawTool}
            drawnTools={drawnTools}
            onRemoveTool={handleRemoveTool}
            onTimeframeChange={(tf) => onTimeframeChange(tf)}
            height={isFullscreen ? window.innerHeight - 200 : 500}
            showToolbar={true}
            allowFullscreen={true}
          />

          {/* Bottom Panel - Info */}
          <Card className="shrink-0">
            <CardContent className="p-3">
              <div className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-4">
                  <span className="text-muted-foreground">Data Source:</span>
                  <Badge variant="outline">
                    {useRealtime ? 'OANDA Live' : 'Database'}
                  </Badge>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-muted-foreground">Candles:</span>
                  <span className="font-mono">{ohlcData.length}</span>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-muted-foreground">Indicators:</span>
                  <span className="font-mono">{activeIndicators.length}</span>
                </div>
                {drawnTools.length > 0 && (
                  <div className="flex items-center gap-4">
                    <span className="text-muted-foreground">Drawings:</span>
                    <span className="font-mono">{drawnTools.length}</span>
                    <Button 
                      variant="ghost" 
                      size="sm" 
                      className="h-6 px-2"
                      onClick={() => setDrawnTools([])}
                    >
                      Clear
                    </Button>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right Sidebar - Indicators & Analysis */}
        <div className="w-80 shrink-0 flex flex-col gap-2">
          <Card className="flex-1 flex flex-col">
            <CardHeader className="pb-3 shrink-0">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <Activity className="h-4 w-4" />
                Technical Indicators
              </CardTitle>
            </CardHeader>
            <CardContent className="flex-1 overflow-auto">
              <IndicatorPanel
                activeIndicators={activeIndicators.map(ind => ({
                  instanceId: ind.id,
                  id: ind.id.split('_')[0],
                  name: ind.name,
                  category: ind.category,
                  defaultParams: ind.params,
                  params: ind.params,
                }))}
                onAddIndicator={handleAddIndicator}
                onRemoveIndicator={handleRemoveIndicator}
                onUpdateParams={(id, params) => {
                  setActiveIndicators(prev =>
                    prev.map(ind =>
                      ind.id === id ? { ...ind, params } : ind
                    )
                  );
                }}
              />
            </CardContent>
          </Card>

          {/* Quick Stats */}
          <Card className="shrink-0">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <Gauge className="h-4 w-4" />
                Session Stats
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">24h High</span>
                <span className="font-mono">{formatPrice(priceStats.high)}</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">24h Low</span>
                <span className="font-mono">{formatPrice(priceStats.low)}</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Volume</span>
                <span className="font-mono">{priceStats.volume.toLocaleString()}</span>
              </div>
              <Separator />
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Spread</span>
                <span className="font-mono">
                  {symbol.includes('JPY') ? '0.010' : '0.00010'}
                </span>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// Helper Functions
// =============================================================================

function mapTimeframeToOanda(timeframe: Granularity): string {
  const mapping: Record<Granularity, string> = {
    '1m': 'M1',
    '5m': 'M5',
    '15m': 'M15',
    '30m': 'M30',
    '1h': 'H1',
    '4h': 'H4',
    '1d': 'D',
  };
  return mapping[timeframe] || 'H1';
}

export default ChartsView;
